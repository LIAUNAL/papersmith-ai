// Does a deliberation skill give one candidate the same verdict at every point that judges it?
//
// Three points judge a managed document before it exists on disk: first-version creation
// (CREATE_INITIAL_REVISION), the CREATE_SUCCESSOR preview, and the accept turn that publishes.
// They used to run three different validation sets. The accept turn ran the workspace's full
// pre-publish set (`derive_successor`); the preview ran only `candidate-validator.ts`; v1 ran
// only the canonical-form rules. And the shared standalone-ATX check read a backtick code span
// such as `## Results` as a heading fused with prose. The result: v1 published a line with an
// inline-code `## `, the successor preview answered `awaiting_acceptance` with no warning, and
// the accept turn refused `atx-heading-standalone` -- so no successor could ever be published
// until unrelated text was reworded.
//
// This file pins both halves of the repair, for EVERY deliberation skill:
//  - a code span is not a heading: the inline-code fixture passes v1, preview and accept;
//  - a genuinely fused heading outside code still refuses, and with the SAME code
//    (`atx-heading-standalone`) at all three points -- the check was fixed, not weakened.
//
// Each profile runs in its own child process: `domain-profile.ts` reads
// `DELIBERATION_DOMAIN_PROFILE` once at import time, so one process can only answer for one
// domain (the technique `experimental-deliberation-publish.test.mjs` established).
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

const IDEA = 'Measure the sweep across three seeds. Then compare the arms.';
// The declarations satisfy the experiments domain's canonical form and the study-protocol
// domain's (each ignores the other's labels); the mathematical domain recognizes nothing in
// them. The first line is the subject under test.
const DECLARATIONS = [
	'**Dataset:** Synthetic-Blobs, train/test split as distributed',
	'**Validation scheme:** paired t-test, 5 seeds, 10 repetitions',
	'**Research question:** Does the sweep change the error between the arms?',
	'**Primary outcome:** O1 -- held-out error rate; time point: end of the sweep',
	'**Secondary outcomes:** none',
	'**Design:** two-arm comparison over a fixed sweep',
	'**Eligibility:** every configuration of the sweep',
	'**Sample size:** 10 repetitions per arm',
	'**Sample size justification:** the repetition count the validation scheme fixes',
	'**Primary model:** paired t-test of the error between the arms',
	'**Covariates:** none',
	'**Missing data:** a failed run is repeated, never imputed',
	'**Multiplicity:** not applicable to the single primary outcome',
].join('\n\n');
const INLINE_CODE_GUIDE = `Each log marks its boundary with \`## Results\` inline.\n\n${DECLARATIONS}`;
const FUSED_GUIDE = `Each log marks its boundary with ## Results inline.\n\n${DECLARATIONS}`;
// v1 derives this heading from the idea's second sentence, terminal punctuation dropped.
const SECTION = '## Then compare the arms';
const CLEAN_REPLACEMENT = `${SECTION}\n\nCompare the arms over three seeds.\n\n`;
const CODE_SPAN_REPLACEMENT = `${SECTION}\n\nCompare the arms once the \`## Results\` marker appears.\n\n`;
const FUSED_REPLACEMENT = `${SECTION}\n\nCompare the arms ## Fused heading here.\n\n`;

const HARNESS = `import path from 'node:path';
import os from 'node:os';
import { mkdir, mkdtemp, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(repoRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const engineDir = process.env.ENGINE_DIR;
const ws = await jiti.import(path.join(engineDir, 'proposal-workspace.ts'));
const v2 = await jiti.import(path.join(engineDir, 'exports.ts'));
const { DOMAIN } = await jiti.import(path.join(engineDir, 'domain-profile.ts'));
const fixtures = ${JSON.stringify({ IDEA, INLINE_CODE_GUIDE, FUSED_GUIDE, SECTION, CLEAN_REPLACEMENT, CODE_SPAN_REPLACEMENT, FUSED_REPLACEMENT })};

async function freshRoot() {
	const root = await mkdtemp(path.join(os.tmpdir(), 'deliberation-validation-parity-'));
	await mkdir(path.join(root, DOMAIN.artifact.directory), { recursive: true });
	return root;
}

/** Point 1: CREATE_INITIAL_REVISION through the production filesystem publication port. */
async function createV1(root, guide) {
	const service = new v2.InitialRevisionCreationService({ hasManagedProposal: async () => false }, v2.createFilesystemInitialRevisionPublicationPort(root));
	const result = await service.execute({ idea: fixtures.IDEA, guideFragments: [{ path: 'notes.md', content: guide }] });
	return { status: result.status, code: result.code ?? null, refusal: result.candidateValidation?.code ?? null, filename: result.filename ?? null };
}

/** Points 2 and 3: CREATE_SUCCESSOR preview, then accept with the preview's own token. */
async function successor(root, filename, replacementText) {
	const guard = ws.createDocumentOperationGuard(root);
	const adapter = new v2.ProposalWorkspaceAdapter(root, guard, ws.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'deliberation-validation-parity');
	const planner = { plan: async (input) => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText }], unresolvedQuestions: [] }) };
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	const request = {
		operation: 'CREATE_SUCCESSOR', editIntent: 'MODIFY', sourceFilename: filename,
		instruction: 'Modify the section Then compare the arms.',
		...(DOMAIN.artifact.changeHeader ? { changeSummary: { what: 'Fixed the comparison.', why: 'One run does not separate noise from effect.' } } : {}),
	};
	const preview = await orchestrator.execute(request);
	const accept = preview.status === 'awaiting_acceptance'
		? await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken })
		: null;
	return {
		preview: { status: preview.status, reason: preview.reason ?? null, refusal: preview.validation?.candidateValidation?.code ?? null },
		accept: accept ? { status: accept.status, reason: accept.reason ?? null, refusal: refusalCode(accept) } : null,
	};
}

function refusalCode(result) {
	const text = JSON.stringify(result);
	const match = text.match(/\\\\?"code\\\\?":\\\\?"([a-z-]+)\\\\?"/);
	return match ? match[1] : null;
}

/** Point 3 alone: the accept turn's own pre-publish validation, \`derive_successor\`, over the same composed candidate. */
async function deriveDirect(root, filename, replacementText) {
	const bytes = await readFile(path.join(root, DOMAIN.artifact.directory, filename));
	const text = bytes.toString('utf8');
	const start = text.indexOf(fixtures.SECTION);
	const next = text.indexOf('\\n## ', start + 1);
	const oldText = text.slice(start, next + 1);
	const nextFilename = ws.nextSuccessorTarget(filename);
	try {
		await ws.createProposalWorkspaceTool(root).execute('derive', {
			action: 'derive_successor', resource: 'proposal', source: filename,
			sourceSha256: createHash('sha256').update(bytes).digest('hex'),
			slug: nextFilename.slice(DOMAIN.artifact.stem.length + 1, -3),
			patches: [{ id: 'replace-section', kind: 'replace', oldText, newText: replacementText }],
		});
		return { status: 'published', refusal: null };
	} catch (error) {
		return { status: 'refused', refusal: error.candidateValidation?.code ?? String(error.message).slice(0, 200) };
	}
}

const out = { profile: { stem: DOMAIN.artifact.stem, revisionPattern: DOMAIN.artifact.revisionPattern } };
{
	const root = await freshRoot();
	const v1 = await createV1(root, fixtures.INLINE_CODE_GUIDE);
	out.inlineCodeInV1 = { v1, ...(v1.filename ? await successor(root, v1.filename, fixtures.CLEAN_REPLACEMENT) : {}) };
}
{
	const root = await freshRoot();
	const v1 = await createV1(root, fixtures.INLINE_CODE_GUIDE.replace(/\`## Results\`/, 'the results marker'));
	out.inlineCodeInSuccessor = { v1, ...(v1.filename ? await successor(root, v1.filename, fixtures.CODE_SPAN_REPLACEMENT) : {}) };
}
{
	const root = await freshRoot();
	out.fusedInV1 = { v1: await createV1(root, fixtures.FUSED_GUIDE) };
}
{
	const root = await freshRoot();
	const v1 = await createV1(root, fixtures.INLINE_CODE_GUIDE.replace(/\`## Results\`/, 'the results marker'));
	out.fusedInSuccessor = { v1, ...(v1.filename ? await successor(root, v1.filename, fixtures.FUSED_REPLACEMENT) : {}), derive: v1.filename ? await deriveDirect(root, v1.filename, fixtures.FUSED_REPLACEMENT) : null };
}
console.log(JSON.stringify(out));
`;

const cache = new Map();
async function run(skill) {
	if (cache.has(skill)) return cache.get(skill);
	const promise = (async () => {
		const scratch = await mkdtemp(path.join(os.tmpdir(), 'deliberation-validation-parity-harness-'));
		const harnessPath = path.join(scratch, 'harness.mjs');
		await writeFile(harnessPath, HARNESS, 'utf8');
		try {
			const { stdout } = await execFileAsync('node', [harnessPath], {
				env: { ...process.env, DELIBERATION_DOMAIN_PROFILE: path.join(repoRoot, `skills/${skill}/profile.ts`), ENGINE_DIR: engineDir },
				maxBuffer: 32 * 1024 * 1024,
			});
			return JSON.parse(stdout.trim().split('\n').pop());
		} finally {
			await rm(scratch, { recursive: true, force: true });
		}
	})();
	cache.set(skill, promise);
	return promise;
}

for (const [skill, stem] of [['proposal-deliberation', 'research-concept'], ['experimental-deliberation', 'experiments'], ['study-protocol-deliberation', 'study-protocol']]) {
	test(`${skill}: the child answers for its own profile`, async () => {
		const { profile } = await run(skill);
		assert.equal(profile.stem, stem, 'DELIBERATION_DOMAIN_PROFILE must reach the child, or this file certifies the wrong skill');
	});

	test(`${skill}: an inline-code "## " in v1 passes v1 creation, the successor preview and the accept turn`, async () => {
		const { inlineCodeInV1: r } = await run(skill);
		assert.equal(r.v1.status, 'created', `v1: ${JSON.stringify(r.v1)}`);
		assert.equal(r.preview.status, 'awaiting_acceptance', `preview: ${JSON.stringify(r.preview)}`);
		assert.equal(r.accept?.status, 'published', `accept: ${JSON.stringify(r.accept)}`);
	});

	test(`${skill}: an inline-code "## " introduced by a successor passes the preview and the accept turn`, async () => {
		const { inlineCodeInSuccessor: r } = await run(skill);
		assert.equal(r.v1.status, 'created', `v1: ${JSON.stringify(r.v1)}`);
		assert.equal(r.preview.status, 'awaiting_acceptance', `preview: ${JSON.stringify(r.preview)}`);
		assert.equal(r.accept?.status, 'published', `accept: ${JSON.stringify(r.accept)}`);
	});

	test(`${skill}: a heading fused with prose outside code refuses v1 creation with atx-heading-standalone`, async () => {
		const { fusedInV1: r } = await run(skill);
		assert.equal(r.v1.status, 'blocked', `v1: ${JSON.stringify(r.v1)}`);
		assert.equal(r.v1.code, 'INITIAL_REVISION_CANDIDATE_VALIDATION_FAILED');
		assert.equal(r.v1.refusal, 'atx-heading-standalone');
	});

	test(`${skill}: a heading fused with prose by a successor refuses at the preview and at the accept turn with the same code`, async () => {
		const { fusedInSuccessor: r } = await run(skill);
		assert.equal(r.v1.status, 'created', `v1: ${JSON.stringify(r.v1)}`);
		// The preview now runs the accept turn's own validation, so it refuses instead of
		// handing out an acceptance token that can never be spent.
		assert.equal(r.preview.status, 'blocked', `preview: ${JSON.stringify(r.preview)}`);
		assert.equal(r.preview.reason, 'CANDIDATE_VALIDATION_FAILED', `preview: ${JSON.stringify(r.preview)}`);
		assert.equal(r.preview.refusal, 'atx-heading-standalone', `preview: ${JSON.stringify(r.preview)}`);
		assert.equal(r.accept, null, 'a refused preview issues no acceptance token');
		// The accept turn's pre-publish validation, driven directly over the same composed
		// candidate, refuses with the identical code.
		assert.equal(r.derive?.status, 'refused', `derive: ${JSON.stringify(r.derive)}`);
		assert.equal(r.derive?.refusal, 'atx-heading-standalone', `derive: ${JSON.stringify(r.derive)}`);
	});
}
