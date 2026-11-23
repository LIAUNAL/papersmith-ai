// The study-protocol domain's reference-integrity vocabulary: an outcome line DECLARES its
// id (`**Primary outcome:** O1 ...`), and the analysis plan or the prose CITES one
// (`[outcome:O1]`, `(Outcome O1)`). A citation of an outcome nobody declares is an
// unresolved reference the core refuses; two outcomes sharing an id are a duplicate.
//
// A fresh process, because `reference-study-protocol.ts` reads this domain's prose-citation
// pattern off the loaded profile, and the suite run is fixed to a different one.
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
const skillDir = path.join(repoRoot, 'skills/study-protocol-deliberation');
const profilePath = path.join(skillDir, 'profile.ts');
const piRoot = path.resolve('.');

const RESOLVED = `# Study protocol

**Primary outcome:** O1 -- systolic blood pressure (mmHg); time point: 12 weeks

**Secondary outcome:** O2 -- diastolic blood pressure (mmHg); time point: 12 weeks

**Primary model:** ANCOVA on arm adjusted for baseline, for [outcome:O1]

Secondary analyses report (Outcome O2) with confidence intervals.
`;

const UNRESOLVED = `# Study protocol

**Primary outcome:** O1 -- systolic blood pressure (mmHg); time point: 12 weeks

**Primary model:** ANCOVA on arm adjusted for baseline, for [outcome:O7]
`;

const DUPLICATE = `# Study protocol

**Primary outcome:** O1 -- systolic blood pressure (mmHg); time point: 12 weeks

**Secondary outcome:** O1 -- diastolic blood pressure (mmHg); time point: 12 weeks
`;

const NEITHER = '# Study protocol\n\nA paragraph about the setting, with no outcome declared or cited.\n';

// The experimental forms are not this domain's citations.
const EXPERIMENT_FORMS = '# Study protocol\n\nTested by (Exp. E1) [tests:E1].\n';

const HARNESS = `import path from 'node:path';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(piRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
    '@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
    '@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
    typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const engineDir = process.env.ENGINE_DIR;
const references = await jiti.import(process.env.REFERENCES_MODULE);
const { checkReferenceIntegrity } = await jiti.import(path.join(engineDir, 'reference-index.ts'));
const documents = JSON.parse(process.env.DOCUMENTS);
const report = {};
for (const [name, source] of Object.entries(documents)) {
    report[name] = { declares: references.declares(source), cites: references.cites(source), integrity: checkReferenceIntegrity(source, references) };
}
console.log(JSON.stringify(report));
`;

let cached;
async function loaded() {
    if (cached) return cached;
    const directory = await mkdtemp(path.join(os.tmpdir(), 'study-protocol-deliberation-references-'));
    try {
        const harnessPath = path.join(directory, 'harness.mjs');
        await writeFile(harnessPath, HARNESS, 'utf8');
        const env = {
            ...process.env,
            DELIBERATION_DOMAIN_PROFILE: profilePath,
            ENGINE_DIR: engineDir,
            REFERENCES_MODULE: path.join(skillDir, 'reference-study-protocol.ts'),
            DOCUMENTS: JSON.stringify({ RESOLVED, UNRESOLVED, DUPLICATE, NEITHER, EXPERIMENT_FORMS }),
        };
        const { stdout } = await execFileAsync('node', [harnessPath], { env });
        cached = JSON.parse(stdout.trim().split('\n').pop());
        return cached;
    } finally {
        await rm(directory, { recursive: true, force: true });
    }
}

test('each outcome line declares its id as a tag', async () => {
    const { RESOLVED: r } = await loaded();
    assert.deepEqual(r.declares, [{ kind: 'tag', value: 'O1' }, { kind: 'tag', value: 'O2' }]);
});

test('the analysis plan and the prose cite outcomes by id, explicitly and in prose', async () => {
    const { RESOLVED: r } = await loaded();
    assert.deepEqual(r.cites, [{ kind: 'ref', value: 'O1' }, { kind: 'prose', value: 'O2' }]);
});

test('every citation resolving to a declared outcome is reference-integral', async () => {
    const { RESOLVED: r } = await loaded();
    assert.equal(r.integrity.resolved, true, JSON.stringify(r.integrity));
    assert.equal(r.integrity.unique, true);
    assert.equal(r.integrity.applicable, true);
});

test('an analysis citing an outcome nobody declares is unresolved', async () => {
    const { UNRESOLVED: r } = await loaded();
    assert.deepEqual(r.integrity.declared, ['O1']);
    assert.ok(r.integrity.cited.includes('O7'));
    assert.equal(r.integrity.resolved, false, 'the core fails candidate validation on an unresolved citation');
});

test('two outcomes declaring the same id are not unique', async () => {
    const { DUPLICATE: r } = await loaded();
    assert.deepEqual(r.integrity.declared, ['O1', 'O1']);
    assert.equal(r.integrity.unique, false);
});

test('a document declaring and citing nothing reports not applicable, never a vacuous pass', async () => {
    const { NEITHER: r } = await loaded();
    assert.deepEqual(r.declares, []);
    assert.deepEqual(r.cites, []);
    assert.equal(r.integrity.applicable, false, JSON.stringify(r.integrity));
});

test('the experimental citation forms are not outcome citations', async () => {
    const { EXPERIMENT_FORMS: r } = await loaded();
    assert.deepEqual(r.cites, []);
});
