// The study-protocol skill's own domain profile, exercised through the shared core that reads it.
//
// Every scenario spawns a FRESH Node process with `DELIBERATION_DOMAIN_PROFILE` pointed at
// `skills/study-protocol-deliberation/profile.ts`: the suite run is fixed to ONE profile by
// `package.json`'s `test` script, and `domain-profile.ts` reads the variable once, at import
// time (the technique `experimental-deliberation-domain-profile.test.mjs` established).
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

const REQUIRED = ['deriveBase', 'baseLabel', 'baseLabelLong', 'exampleSlug', 'names', 'proseReferencePattern', 'vocabulary', 'artifact', 'preservation', 'references', 'sources', 'objective'];
const ARTIFACT_REQUIRED = ['directory', 'stem', 'revisionPattern', 'revisionLabel', 'sidecarRoot', 'marker'];
const VOCABULARY_REQUIRED = ['conceptualTerms', 'expertPattern', 'displayNounPattern', 'displayNounStripPattern', 'subjectPattern', 'subjectTerms', 'subjectLocusDescription', 'subjectEvidenceLabel'];

const LINEAGE = 'walking-hypertension';

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
const { DOMAIN } = await jiti.import(path.join(engineDir, 'domain-profile.ts'));
const naming = await jiti.import(path.join(engineDir, 'artifact-naming.ts'));
const { buildStructuralIndex } = await jiti.import(path.join(engineDir, 'document-index.ts'));
const lineage = ${JSON.stringify(LINEAGE)};

const header = DOMAIN.artifact.changeHeader.render({ what: 'Amended the eligibility criteria.', why: 'The ethics committee asked for it.' });
const document = \`# Study protocol\\n\\n\${header}## Fields\\n\\nBody paragraph.\\n\`;
const bytes = Buffer.from(document, 'utf8');
const headingEntry = buildStructuralIndex(document).entries.find((entry) =>
    ['section', 'subsection', 'heading'].includes(entry.type)
    && bytes.subarray(entry.startByte, entry.endByte).toString('utf8').split(/\\r?\\n/, 1)[0].replace(/^#{1,6}\\s+/, '').trim() === DOMAIN.artifact.changeHeader.heading);

console.log(JSON.stringify({
    missingRequired: ${JSON.stringify(REQUIRED)}.filter((key) => DOMAIN[key] === undefined),
    missingArtifact: ${JSON.stringify(ARTIFACT_REQUIRED)}.filter((key) => DOMAIN.artifact[key] === undefined),
    missingVocabulary: ${JSON.stringify(VOCABULARY_REQUIRED)}.filter((key) => DOMAIN.vocabulary[key] === undefined),
    marker: DOMAIN.artifact.marker,
    directory: DOMAIN.artifact.directory,
    stem: DOMAIN.artifact.stem,
    sidecarRoot: DOMAIN.artifact.sidecarRoot,
    initial: naming.initialRevisionFilename(lineage),
    second: naming.managedRevisionFilename(lineage, 2),
    tenth: naming.managedRevisionFilename(lineage, 10),
    isInitial: naming.isInitialRevision(naming.initialRevisionFilename(lineage)),
    strict: naming.strictManagedRevision(naming.managedRevisionFilename(lineage, 2)),
    documentPath: naming.documentPath(naming.initialRevisionFilename(lineage)),
    statePath: naming.statePath(naming.initialRevisionFilename(lineage)),
    receiptPath: naming.receiptPath(naming.initialRevisionFilename(lineage)),
    heading: DOMAIN.artifact.changeHeader.heading,
    header,
    headerSpan: headingEntry ? bytes.subarray(headingEntry.startByte, headingEntry.endByte).toString('utf8') : null,
    sources: DOMAIN.sources,
    authorityNames: DOMAIN.sourceAuthority.names,
    authoritySeverity: DOMAIN.sourceAuthority.severity,
    conflictOnStatedResult: DOMAIN.sourceAuthority.detectConflicts('# Study protocol\\n\\nThe programme was significantly more effective than usual care (p < 0.01).\\n'),
    conflictOnPlannedWork: DOMAIN.sourceAuthority.detectConflicts('# Study protocol\\n\\nThe trial will compare systolic pressure between arms at 12 weeks.\\n'),
    objectiveStages: DOMAIN.objective.stages.map((stage) => stage.stage),
    objectiveArrival: DOMAIN.objective.arrival,
    objectivePurpose: DOMAIN.objective.purpose,
    objectiveEntrances: DOMAIN.objective.entrances ?? null,
    objectiveHumanStops: DOMAIN.objective.humanStops,
}));
`;

let cached;
async function loaded() {
    if (cached) return cached;
    const directory = await mkdtemp(path.join(os.tmpdir(), 'study-protocol-deliberation-profile-'));
    try {
        const harnessPath = path.join(directory, 'harness.mjs');
        await writeFile(harnessPath, HARNESS, 'utf8');
        const env = { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, ENGINE_DIR: engineDir };
        const { stdout } = await execFileAsync('node', [harnessPath], { env });
        cached = JSON.parse(stdout.trim().split('\n').pop());
        return cached;
    } finally {
        await rm(directory, { recursive: true, force: true });
    }
}

test('the profile satisfies the full REQUIRED contract the core refuses a domain for missing', async () => {
    const result = await loaded();
    assert.deepEqual(result.missingRequired, []);
    assert.deepEqual(result.missingArtifact, []);
    assert.deepEqual(result.missingVocabulary, []);
});

test('a managed revision renders as study-protocol-<slug>-v01.md and increments to v02', async () => {
    const result = await loaded();
    assert.equal(result.initial, `study-protocol-${LINEAGE}-v01.md`);
    assert.equal(result.second, `study-protocol-${LINEAGE}-v02.md`);
    assert.equal(result.tenth, `study-protocol-${LINEAGE}-v10.md`);
    assert.equal(result.isInitial, true);
    assert.equal(result.strict, true);
});

test('the managed document lives under protocol/ and its sidecars under .study-protocol-deliberation/', async () => {
    const result = await loaded();
    assert.equal(result.directory, 'protocol');
    assert.equal(result.stem, 'study-protocol');
    assert.equal(result.sidecarRoot, '.study-protocol-deliberation');
    assert.equal(result.documentPath, `protocol/study-protocol-${LINEAGE}-v01.md`);
    assert.equal(result.statePath, `.study-protocol-deliberation/state/study-protocol-${LINEAGE}-v01.md.json`);
    assert.equal(result.receiptPath, `.study-protocol-deliberation/receipts/study-protocol-${LINEAGE}-v01.md.json`);
    assert.ok(result.marker.startsWith('<!--') && result.marker.endsWith('-->\n'));
});

test('every amendment carries a change header occupying exactly the span the core replaces', async () => {
    const result = await loaded();
    assert.equal(result.header.split('\n', 1)[0].replace(/^#{1,6}\s+/, '').trim(), result.heading);
    assert.ok(result.header.endsWith('\n\n'), 'document-index.ts folds the trailing blank line into a heading span');
    assert.match(result.header, /Amended the eligibility criteria\./);
    assert.equal(result.headerSpan, result.header);
});

test('every declared source is well formed and optional: no flow calls this skill until its line arrives', async () => {
    const result = await loaded();
    assert.ok(result.sources.length > 0);
    for (const source of result.sources) {
        assert.equal(typeof source.path, 'string');
        assert.ok(source.path.length > 0 && !source.path.startsWith('/') && !source.path.split('/').includes('..'));
        assert.equal(source.required, false, `${source.path}: a protocol is drafted with the operator, not from a source it cannot start without`);
    }
});

test('a result stated as achieved conflicts with the bound at advisory severity; planned work does not', async () => {
    const result = await loaded();
    assert.equal(result.authoritySeverity, 'advisory');
    assert.equal(result.authorityNames.length, 1);
    assert.ok(result.sources.some((source) => source.path === result.authorityNames[0]));
    assert.equal(result.conflictOnStatedResult.length, 1, JSON.stringify(result.conflictOnStatedResult));
    assert.equal(result.conflictOnStatedResult[0].sourceName, result.authorityNames[0]);
    assert.match(result.conflictOnStatedResult[0].evidence, /p < 0\.01/);
    assert.deepEqual(result.conflictOnPlannedWork, []);
});

test('the north is its own, declares no entrance, and keeps acceptance and the primary outcome human', async () => {
    const result = await loaded();
    assert.deepEqual(result.objectiveStages, ['bound', 'validated', 'deliberated', 'composed', 'published']);
    assert.doesNotMatch(result.objectivePurpose, /mathematics|experiments/i);
    assert.equal(result.objectiveEntrances, null);
    assert.ok(result.objectiveHumanStops.some((stop) => /accepting the change/.test(stop)));
    assert.ok(result.objectiveHumanStops.some((stop) => /main endpoint/.test(stop)), "the choice of the primary outcome stays human");
});

const cliPath = path.join(skillDir, 'cli.mjs');

test('STATUS through the skill launcher reports this domain\'s north and no revisions in an empty project', async () => {
    const directory = await mkdtemp(path.join(os.tmpdir(), 'study-protocol-deliberation-cli-'));
    try {
        const env = { ...process.env, PROPOSAL_DELIBERATION_PROJECT_ROOT: directory };
        delete env.DELIBERATION_DOMAIN_PROFILE;
        const { stdout } = await execFileAsync('node', [cliPath, '{"operation":"STATUS"}'], { env });
        const result = JSON.parse(stdout);
        assert.equal(result.status, 'ok');
        assert.deepEqual(result.objective.stages.map((stage) => stage.stage), ['bound', 'validated', 'deliberated', 'composed', 'published']);
        assert.match(result.objective.purpose, /study protocol/);
    } finally {
        await rm(directory, { recursive: true, force: true });
    }
});

test('a malformed request through the launcher still carries this domain\'s north on its error path', async () => {
    const directory = await mkdtemp(path.join(os.tmpdir(), 'study-protocol-deliberation-cli-err-'));
    try {
        const env = { ...process.env, PROPOSAL_DELIBERATION_PROJECT_ROOT: directory };
        delete env.DELIBERATION_DOMAIN_PROFILE;
        let result;
        try {
            await execFileAsync('node', [cliPath, '{"operation":"NOT_A_REAL_OP"}'], { env });
            assert.fail('expected the CLI to exit non-zero on an unknown operation');
        } catch (error) {
            result = JSON.parse(error.stdout);
        }
        assert.equal(result.status, 'error');
        assert.match(result.objective.purpose, /study protocol/);
    } finally {
        await rm(directory, { recursive: true, force: true });
    }
});
