// First-version creation under the study-protocol profile, through the real host tool.
//
// A protocol is drafted with the operator, so its fields arrive in the idea text
// (CREATE_INITIAL_REVISION's instruction), not from a required source. v1 is checked by
// the same canonical-form gate as every successor: a draft with zero or two primary
// outcomes, a sample size without its justification, or an analysis plan without a
// primary model is refused before anything is written.
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

const FIELDS = {
    question: '**Research question:** In adults with stage 1 hypertension, does a 12-week supervised walking programme lower systolic blood pressure compared with usual care?',
    primary: '**Primary outcome:** O1 -- change in seated systolic blood pressure (mmHg) from baseline; time point: 12 weeks',
    secondary: '**Secondary outcome:** O2 -- change in diastolic blood pressure (mmHg); time point: 12 weeks',
    design: '**Design:** two-arm, parallel-group randomised controlled trial, 1:1 allocation, assessor-blinded',
    eligibility: '**Eligibility:** adults aged 40 to 70 with untreated stage 1 hypertension',
    size: '**Sample size:** 148 participants (74 per arm)',
    justification: '**Sample size justification:** a two-sided t-test at alpha 0.05 with 80% power detects a 5 mmHg difference (assumed SD 10 mmHg) at 64 per arm, inflated by 15% for attrition',
    model: '**Primary model:** ANCOVA of the 12-week systolic change on arm, adjusted for baseline, for [outcome:O1]',
    covariates: '**Covariates:** baseline systolic blood pressure, age, sex',
    missing: '**Missing data:** multiple imputation by chained equations under missing at random',
    multiplicity: '**Multiplicity:** not applicable to the single primary outcome',
};

/** An idea of two sentences (title and section heading) followed by the drafted field block. */
function idea(overrides = {}, extra = []) {
    const fields = Object.values({ ...FIELDS, ...overrides }).filter((line) => line !== null);
    return ['Supervised walking for stage 1 hypertension. Protocol fields agreed with the operator.', '', ...[...fields, ...extra].flatMap((line) => [line, ''])].join('\n').trim();
}

const HARNESS = `import path from 'node:path';
import { readdir, readFile } from 'node:fs/promises';
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
const workspace = await jiti.import(path.join(engineDir, 'proposal-workspace.ts'));
const { DOMAIN } = await jiti.import(path.join(engineDir, 'domain-profile.ts'));
const projectRoot = process.env.PROJECT_ROOT;
const guard = workspace.createDocumentOperationGuard(projectRoot);
const tools = [];
workspace.createProposalDeliberationExtension({ projectRoot, operationGuard: guard })({ registerTool: (candidate) => tools.push(candidate), on: () => {} });
const tool = tools.find((candidate) => candidate.name === 'proposal_deliberation_execute');
const ctx = { model: { provider: 'anthropic', id: 'unused' }, sessionManager: { getSessionId: () => 'initial-revision-session' }, modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'unused', headers: {}, env: {} }) } };
const { details } = await tool.execute('initial-revision', { operation: 'CREATE_INITIAL_REVISION', instruction: process.env.IDEA }, undefined, undefined, ctx);
const managedDirectory = path.join(projectRoot, DOMAIN.artifact.directory);
const onDisk = await readdir(managedDirectory).catch(() => []);
const written = details.targetFilename ? await readFile(path.join(managedDirectory, details.targetFilename), 'utf8') : null;
console.log(JSON.stringify({ profile: { stem: DOMAIN.artifact.stem, directory: DOMAIN.artifact.directory }, details, onDisk: onDisk.sort(), written }));
`;

async function createInitialRevision(ideaText) {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'study-protocol-deliberation-initial-'));
    const scratch = await mkdtemp(path.join(os.tmpdir(), 'study-protocol-deliberation-initial-harness-'));
    try {
        const harnessPath = path.join(scratch, 'harness.mjs');
        await writeFile(harnessPath, HARNESS, 'utf8');
        const { stdout } = await execFileAsync('node', [harnessPath], {
            env: { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, ENGINE_DIR: engineDir, PROJECT_ROOT: projectRoot, IDEA: ideaText },
            maxBuffer: 32 * 1024 * 1024,
        });
        return JSON.parse(stdout.trim().split('\n').pop());
    } finally {
        await rm(projectRoot, { recursive: true, force: true });
        await rm(scratch, { recursive: true, force: true });
    }
}

let cleanRun;
const clean = async () => (cleanRun ??= await createInitialRevision(idea()));

function assertRefused(details, onDisk, rule) {
    assert.equal(details.status, 'blocked', JSON.stringify(details));
    assert.deepEqual(details.blockers?.map((blocker) => blocker.code), ['INITIAL_REVISION_CANONICAL_FORM_VIOLATION'], JSON.stringify(details.blockers));
    assert.match(details.blockers[0].message, new RegExp(rule));
    assert.deepEqual(onDisk, [], 'nothing may be written when the composed candidate is refused');
    assert.equal(details.mutations, 0);
}

test('the creation runs under the study-protocol profile, not the one the suite is fixed to', async () => {
    const { profile } = await clean();
    assert.equal(profile.stem, 'study-protocol');
    assert.equal(profile.directory, 'protocol');
});

test('a drafted protocol with every required field becomes protocol/study-protocol-<slug>-v01.md', async () => {
    const { details, onDisk, written } = await clean();
    assert.equal(details.status, 'created', JSON.stringify(details));
    assert.equal(details.targetRevision, 'v01');
    assert.match(details.targetFilename, /^study-protocol-[a-z0-9-]+-v01\.md$/, details.targetFilename);
    assert.deepEqual(onDisk, [details.targetFilename]);
    assert.ok(written.includes(FIELDS.primary), 'the primary outcome line reaches v1 verbatim');
    assert.ok(written.includes('## Changes'), 'v1 carries the change header every amendment rewrites');
});

test('a draft with no primary outcome refuses the first revision', async () => {
    const { details, onDisk } = await createInitialRevision(idea({ primary: null, model: '**Primary model:** ANCOVA on arm adjusted for baseline' }));
    assertRefused(details, onDisk, 'primary-outcome-missing');
});

test('a draft with two primary outcomes refuses the first revision', async () => {
    const { details, onDisk } = await createInitialRevision(idea({}, ['**Primary outcome:** O3 -- home systolic blood pressure (mmHg); time point: 12 weeks']));
    assertRefused(details, onDisk, 'primary-outcome-repeated');
});

test('a sample size without its justification refuses the first revision', async () => {
    const { details, onDisk } = await createInitialRevision(idea({ justification: null }));
    assertRefused(details, onDisk, 'sample-size-without-justification');
});

test('an analysis plan without a primary model refuses the first revision', async () => {
    const { details, onDisk } = await createInitialRevision(idea({ model: null }));
    assertRefused(details, onDisk, 'analysis-plan-without-primary-model');
});

test('a field stating a result as already achieved refuses the first revision', async () => {
    const { details, onDisk } = await createInitialRevision(idea({ justification: '**Sample size justification:** we observed a 5 mmHg effect in the pilot, so 74 per arm' }));
    assertRefused(details, onDisk, 'field-states-result');
});
