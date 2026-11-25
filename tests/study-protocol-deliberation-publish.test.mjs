// The resolve -> preview -> accept cycle under the study-protocol profile, against a real
// project: an amendment publishes as study-protocol-<lineage>-v02.md, and an amendment that
// switches the primary outcome is visible as a lost atom that must be acknowledged by id
// before it publishes (the guard against silent outcome switching).
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, 'skills/_core/deliberation/engine');
const profilePath = path.join(repoRoot, 'skills/study-protocol-deliberation/profile.ts');
const piRoot = path.resolve('.');

const LINEAGE = 'walking-hypertension';
const SOURCE_FILENAME = `study-protocol-${LINEAGE}-v01.md`;
const TARGET_FILENAME = `study-protocol-${LINEAGE}-v02.md`;

const SEED = `# Supervised walking for stage 1 hypertension

## Changes

**What:** Seeded the first version of this protocol.

**Why:** A lineage needs a starting point.

## Question and outcomes

**Research question:** In adults with stage 1 hypertension, does a 12-week supervised walking programme lower systolic blood pressure compared with usual care?

**Primary outcome:** O1 -- change in seated systolic blood pressure (mmHg) from baseline; time point: 12 weeks

**Secondary outcomes:** none

## Design and participants

**Design:** two-arm, parallel-group randomised controlled trial, 1:1 allocation

**Eligibility:** adults aged 40 to 70 with untreated stage 1 hypertension

## Sample size

**Sample size:** 148 participants (74 per arm)

**Sample size justification:** a two-sided t-test at alpha 0.05 with 80% power detects a 5 mmHg difference (assumed SD 10 mmHg), inflated by 15% for attrition

## Analysis plan

**Primary model:** ANCOVA of the 12-week systolic change on arm, adjusted for baseline, for [outcome:O1]

**Covariates:** baseline systolic blood pressure

**Missing data:** multiple imputation under missing at random

**Multiplicity:** not applicable to the single primary outcome
`;

const ELIGIBILITY_AMENDMENT = '## Design and participants\n\n**Design:** two-arm, parallel-group randomised controlled trial, 1:1 allocation\n\n**Eligibility:** adults aged 40 to 75 with untreated stage 1 hypertension\n\n';
const OUTCOME_SWITCH = '## Question and outcomes\n\n**Research question:** In adults with stage 1 hypertension, does a 12-week supervised walking programme lower systolic blood pressure compared with usual care?\n\n**Primary outcome:** O1 -- change in home systolic blood pressure (mmHg) from baseline; time point: 12 weeks\n\n**Secondary outcomes:** none\n\n';

const HARNESS = `import path from 'node:path';
import os from 'node:os';
import { mkdir, mkdtemp, readdir, rm } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(piRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const engineDir = process.env.ENGINE_DIR;
const workspaceModule = await jiti.import(path.join(engineDir, 'proposal-workspace.ts'));
const v2 = await jiti.import(path.join(engineDir, 'exports.ts'));
const { DOMAIN } = await jiti.import(path.join(engineDir, 'domain-profile.ts'));
const fixtures = ${JSON.stringify({ LINEAGE, SEED, ELIGIBILITY_AMENDMENT, OUTCOME_SWITCH })};

async function seededRoot() {
	const root = await mkdtemp(path.join(os.tmpdir(), 'study-protocol-deliberation-publish-'));
	await mkdir(path.join(root, DOMAIN.artifact.directory), { recursive: true });
	await workspaceModule.createProposalWorkspaceTool(root)
		.execute('seed', { action: 'write', resource: 'proposal', slug: \`\${fixtures.LINEAGE}-v01\`, content: fixtures.SEED });
	return root;
}

function orchestratorFor(root, replacementText) {
	const guard = workspaceModule.createDocumentOperationGuard(root);
	const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'study-protocol-deliberation-publish');
	const planner = { plan: async (input) => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText }], unresolvedQuestions: [] }) };
	return new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
}

async function amend(heading, replacementText, acknowledge) {
	const root = await seededRoot();
	const orchestrator = orchestratorFor(root, replacementText);
	const request = {
		operation: 'CREATE_SUCCESSOR', editIntent: 'MODIFY', sourceFilename: \`\${DOMAIN.artifact.stem}-\${fixtures.LINEAGE}-v01.md\`,
		instruction: \`Modifica la sección \${heading}.\`,
		changeSummary: { what: 'Amended the protocol.', why: 'The operator asked for it.' },
	};
	const preview = await orchestrator.execute(request);
	const lost = (preview.preservationDelta?.lost ?? []).map((atom) => atom.id);
	const accept = preview.status === 'awaiting_acceptance'
		? await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken, ...(acknowledge ? { acknowledgedRemovals: lost } : {}) })
		: null;
	const onDisk = (await readdir(path.join(root, DOMAIN.artifact.directory))).sort();
	await rm(root, { recursive: true, force: true });
	return {
		preview: { status: preview.status, reason: preview.reason ?? null, targetFilename: preview.targetFilename ?? null, preservationApplicable: preview.validation?.preservationApplicable ?? null, lost },
		accept: accept ? { status: accept.status, reason: accept.reason ?? null, targetFilename: accept.published?.targetFilename ?? null, targetRevision: accept.published?.targetRevision ?? null } : null,
		onDisk,
	};
}

console.log(JSON.stringify({
	stem: DOMAIN.artifact.stem,
	eligibility: await amend('Design and participants', fixtures.ELIGIBILITY_AMENDMENT, false),
	switchUnacknowledged: await amend('Question and outcomes', fixtures.OUTCOME_SWITCH, false),
	switchAcknowledged: await amend('Question and outcomes', fixtures.OUTCOME_SWITCH, true),
}));
`;

let cached;
async function cycle() {
    if (cached) return cached;
    const scratch = await mkdtemp(path.join(os.tmpdir(), 'study-protocol-deliberation-publish-harness-'));
    try {
        const harnessPath = path.join(scratch, 'harness.mjs');
        await writeFile(harnessPath, HARNESS, 'utf8');
        const { stdout } = await execFileAsync('node', [harnessPath], {
            env: { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, ENGINE_DIR: engineDir },
            maxBuffer: 32 * 1024 * 1024,
        });
        cached = JSON.parse(stdout.trim().split('\n').pop());
        return cached;
    } finally {
        await rm(scratch, { recursive: true, force: true });
    }
}

test('the cycle runs under the study-protocol profile', async () => {
    assert.equal((await cycle()).stem, 'study-protocol');
});

test('an eligibility amendment previews, loses only the eligibility atom, and the accept turn waits for its acknowledgement', async () => {
    const { eligibility: r } = await cycle();
    assert.equal(r.preview.status, 'awaiting_acceptance', JSON.stringify(r.preview));
    assert.equal(r.preview.targetFilename, TARGET_FILENAME);
    assert.equal(r.preview.preservationApplicable, true);
    assert.equal(r.preview.lost.length, 1, JSON.stringify(r.preview.lost));
    assert.match(r.preview.lost[0], /^eligibility:/);
    assert.equal(r.accept.status, 'blocked', 'an unacknowledged lost atom blocks the accept turn');
});

test('switching the primary outcome is a lost primary-outcome atom, and the accept turn refuses it unacknowledged', async () => {
    const { switchUnacknowledged: r } = await cycle();
    assert.equal(r.preview.status, 'awaiting_acceptance', JSON.stringify(r.preview));
    assert.deepEqual(r.preview.lost.filter((id) => id.startsWith('primary-outcome:O1:')).length, 1, JSON.stringify(r.preview.lost));
    assert.equal(r.accept.status, 'blocked', JSON.stringify(r.accept));
    assert.equal(r.accept.reason, 'MATH_REMOVALS_NOT_ACKNOWLEDGED');
    assert.deepEqual(r.onDisk, [SOURCE_FILENAME], 'nothing is published while the switch is unacknowledged');
});

test('an acknowledged primary-outcome switch publishes as study-protocol-<lineage>-v02.md at revision v02', async () => {
    const { switchAcknowledged: r } = await cycle();
    assert.equal(r.accept.status, 'published', JSON.stringify(r.accept));
    assert.equal(r.accept.targetFilename, TARGET_FILENAME);
    assert.equal(r.accept.targetRevision, 'v02');
    assert.deepEqual(r.onDisk, [SOURCE_FILENAME, TARGET_FILENAME]);
});
