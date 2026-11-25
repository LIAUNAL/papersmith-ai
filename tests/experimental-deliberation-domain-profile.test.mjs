// This skill's own domain profile, exercised through the shared core that reads it.
//
// Every scenario here spawns a FRESH Node process with `DELIBERATION_DOMAIN_PROFILE`
// pointed at `skills/experimental-deliberation/profile.ts`. The whole suite
// run is fixed to ONE profile by `package.json`'s `test` script, and
// `domain-profile.ts` reads the variable once, at module-import time, so a second
// `jiti.import()` in this process would silently answer for the other domain --
// the same technique `proposal-deliberation-required-sources.test.mjs` and
// `proposal-deliberation-change-header.test.mjs` already established.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, 'skills/_core/deliberation/engine');
const skillDir = path.join(repoRoot, 'skills/experimental-deliberation');
const profilePath = path.join(skillDir, 'profile.ts');
const piRoot = path.resolve('.');

// Exactly the top-level keys `domain-profile.ts` refuses a profile for omitting (finding
// M6 fixed this to actually match the comment below: `vocabulary.*` used to be listed here
// with no core enforcement behind it at all -- `domain-profile.ts` refused a profile for
// NONE of these eight fields, so this constant only ever proved this PROFILE declares them,
// never that the core would refuse one that did not; see
// `tests/proposal-deliberation-domain-profile-vocabulary.test.mjs` for that refusal proven
// directly against the core), plus the six nested `artifact.*` fields it checks separately.
// `proseReferenceText` is deliberately absent (finding L5): it is optional now, and this
// profile no longer declares a renderer it never invoked -- `preservation-experimental.ts`
// has no "ref" atom kind and `reference-experimental.ts` needs only the raw matched value.
const REQUIRED = ['deriveBase', 'baseLabel', 'baseLabelLong', 'exampleSlug', 'names', 'proseReferencePattern', 'vocabulary', 'artifact', 'preservation', 'references', 'sources', 'objective'];
const ARTIFACT_REQUIRED = ['directory', 'stem', 'revisionPattern', 'revisionLabel', 'sidecarRoot', 'marker'];
const VOCABULARY_REQUIRED = ['conceptualTerms', 'expertPattern', 'displayNounPattern', 'displayNounStripPattern', 'subjectPattern', 'subjectTerms', 'subjectLocusDescription', 'subjectEvidenceLabel'];

const LINEAGE = 'domain-shift-baseline-sweep';

const RICH = `# Experiments

## Reported results

| Arm | Accuracy |
| --- | --- |
| Source only |  |
| Adapted |  |

![Accuracy against labelled examples](figures/accuracy.png)
`;
const RICH_WITHOUT_FIGURE = RICH.replace('![Accuracy against labelled examples](figures/accuracy.png)\n', '');
const PLAIN = '# Experiments\n\nTraining runs use a learning rate of 3e-4 over 5 seeds on the 2018 split.\n';

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
const preservation = await jiti.import(path.join(engineDir, 'preservation.ts'));

const RICH = ${JSON.stringify(RICH)};
const RICH_WITHOUT_FIGURE = ${JSON.stringify(RICH_WITHOUT_FIGURE)};
const PLAIN = ${JSON.stringify(PLAIN)};
const lineage = ${JSON.stringify(LINEAGE)};

const header = DOMAIN.artifact.changeHeader.render({ what: 'Added the ablation table.', why: 'The proposal claims it.' });
// A document shaped like a published revision: the header block, then the next
// heading. \`target-resolver.ts\` locates the header by its heading text and replaces
// its natural structural span, so that span must be exactly what \`render\` produced.
const document = \`# Experiments\\n\\n\${header}## Protocol\\n\\nBody paragraph.\\n\`;
const bytes = Buffer.from(document, 'utf8');
const headingEntry = buildStructuralIndex(document).entries.find((entry) =>
    ['section', 'subsection', 'heading'].includes(entry.type)
    && bytes.subarray(entry.startByte, entry.endByte).toString('utf8').split(/\\r?\\n/, 1)[0].replace(/^#{1,6}\\s+/, '').trim() === DOMAIN.artifact.changeHeader.heading);

const conflictOnAchievedResult = DOMAIN.sourceAuthority.detectConflicts(
    '# Experiments\\n\\nThe adapted model outperforms every published baseline on this task.\\n');
const conflictOnPlannedWork = DOMAIN.sourceAuthority.detectConflicts(
    '# Experiments\\n\\nThe run will report accuracy for the adapted model against the source-only baseline.\\n');
// The \`## <sourceReferenceHeading>\` section holds verbatim fragments of the data paper
// rendered at v1 and carried into every successor: the source quoting itself is not the
// plan asserting an outcome. Detection resumes at the next level-2 heading.
const QUOTED = 'Measurements were obtained from a nearby weather station.';
const referenceHeading = DOMAIN.artifact.sourceReferenceHeading;
const conflictInReferenceSources = DOMAIN.sourceAuthority.detectConflicts(
    \`# Experiments\\n\\n## \${referenceHeading}\\n\\n\${QUOTED}\\n\\n### Data paper\\n\\n\${QUOTED} Again.\\n\`);
const conflictInExperiment = DOMAIN.sourceAuthority.detectConflicts(
    \`# Experiments\\n\\n## Experiment [exp:E1] Station\\n\\n\${QUOTED}\\n\`);
const conflictAfterReferenceSources = DOMAIN.sourceAuthority.detectConflicts(
    \`# Experiments\\n\\n## \${referenceHeading}\\n\\n\${QUOTED}\\n\\n## Changes\\n\\nThe adapted model outperforms every baseline.\\n\`);

console.log(JSON.stringify({
    missingRequired: ${JSON.stringify(REQUIRED)}.filter((key) => DOMAIN[key] === undefined),
    missingArtifact: ${JSON.stringify(ARTIFACT_REQUIRED)}.filter((key) => DOMAIN.artifact[key] === undefined),
    missingVocabulary: ${JSON.stringify(VOCABULARY_REQUIRED)}.filter((key) => DOMAIN.vocabulary[key] === undefined),
    marker: DOMAIN.artifact.marker,
    directory: DOMAIN.artifact.directory,
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
    conflictOnAchievedResult,
    conflictOnPlannedWork,
    conflictInReferenceSources,
    conflictInExperiment,
    conflictAfterReferenceSources,
    richAtoms: preservation.atoms(RICH).size,
    plainAtoms: preservation.atoms(PLAIN).size,
    lostFigure: preservation.delta(RICH, RICH_WITHOUT_FIGURE).lost.map((atom) => atom.kind),
    lostNothing: preservation.delta(RICH, RICH).lost.length,
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
    const directory = await mkdtemp(path.join(os.tmpdir(), 'experimental-deliberation-profile-'));
    const harnessPath = path.join(directory, 'harness.mjs');
    await writeFile(harnessPath, HARNESS, 'utf8');
    const env = { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, ENGINE_DIR: engineDir };
    const { stdout } = await execFileAsync('node', [harnessPath], { env });
    cached = JSON.parse(stdout.trim().split('\n').pop());
    return cached;
}

test('the profile satisfies the full REQUIRED contract the core refuses a domain for missing', async () => {
    const result = await loaded();
    assert.deepEqual(result.missingRequired, []);
    assert.deepEqual(result.missingArtifact, []);
    assert.deepEqual(result.missingVocabulary, []);
});

test('a managed revision renders as experiments-<slug>-v01.md and increments to v02', async () => {
    const result = await loaded();
    assert.equal(result.initial, `experiments-${LINEAGE}-v01.md`);
    assert.equal(result.second, `experiments-${LINEAGE}-v02.md`);
    assert.equal(result.tenth, `experiments-${LINEAGE}-v10.md`);
    assert.equal(result.isInitial, true, 'the first revision must satisfy the core INITIAL matcher, which pins revisionLabel(1)');
    assert.equal(result.strict, true, 'a successor must satisfy the core STRICT matcher, which demands two ordinal digits');
});

test('the managed document and its sidecars land under this skill\'s own namespace', async () => {
    const result = await loaded();
    assert.equal(result.directory, 'experiments');
    assert.equal(result.sidecarRoot, '.experimental-deliberation');
    assert.equal(result.documentPath, `experiments/experiments-${LINEAGE}-v01.md`);
    assert.equal(result.statePath, `.experimental-deliberation/state/experiments-${LINEAGE}-v01.md.json`);
    assert.equal(result.receiptPath, `.experimental-deliberation/receipts/experiments-${LINEAGE}-v01.md.json`);
});

test('this domain declares its own artifact marker and no core file spells one', async () => {
    const result = await loaded();
    // This test used to assert the opposite: that the profile COPIES a literal
    // `patch-compiler.ts`, `draft-materialization.ts` and `revision-lifecycle-store.ts`
    // each spelled, "byte for byte". That was the defect written down as a lock -- a
    // second domain was required to copy a hardcode, and any domain that declared a
    // different marker was silently broken by all three sites.
    //
    // All three now read the profile, so there is nothing left to copy and nothing to
    // keep in sync. What is left to check is that no core file has quietly grown a
    // fourth copy, and that this domain's own declaration is a real marker.
    const spelled = [];
    for (const file of ['patch-compiler.ts', 'draft-materialization.ts', 'revision-lifecycle-store.ts']) {
        const source = await readFile(path.join(engineDir, file), 'utf8');
        const code = source.split('\n').filter((line) => !line.trimStart().startsWith('//')).join('\n');
        if (/Buffer\.from\('<!--/.test(code)) spelled.push(file);
    }
    assert.deepEqual(spelled, [], `core files spelling a marker literal again: ${spelled.join(', ')}`);
    assert.ok(result.marker.startsWith('<!--') && result.marker.endsWith('-->\n'),
        `this domain's declared marker is not a comment ending in a newline: ${JSON.stringify(result.marker)}`);
});
test('the change header renders its own heading line and ends with a trailing blank line', async () => {
    const result = await loaded();
    assert.equal(result.header.split('\n', 1)[0].replace(/^#{1,6}\s+/, '').trim(), result.heading);
    assert.ok(result.header.endsWith('\n\n'), 'document-index.ts folds the trailing blank line into a heading span');
    assert.match(result.header, /Added the ablation table\./);
    assert.match(result.header, /The proposal claims it\./);
});

test('the rendered header occupies exactly the structural span the core will replace', async () => {
    const result = await loaded();
    assert.equal(result.headerSpan, result.header,
        'the header must be locatable by its heading text and span exactly the bytes render produced');
    // The consumer of the trailing blank line: `successor-markdown-block-safety` refuses a
    // replacement whose bytes fuse with the block after them, and the block after the header
    // span is the next heading. This is the byte property that requirement reduces to.
    assert.match(`${result.header}## Protocol`, /(?:\r?\n){2}##/,
        'the replaced header span must keep blank-line separation from the block that follows it');
});

// Asserts PROPERTIES, never a count. A count here once read as a requirement and was only
// a transcription: it froze an optional source nobody had authorized, and removing that
// source turned this test red for defending a choice rather than a behaviour. What follows
// must stay true whichever optional sources this domain later gains or drops.
test('every declared source is well formed, and the two the domain cannot draft without are required', async () => {
    const result = await loaded();
    assert.ok(result.sources.length > 0, 'a domain with no declared source loads nothing');
    for (const source of result.sources) {
        assert.equal(typeof source.path, 'string');
        assert.ok(source.path.length > 0, 'an empty path names no directory');
        assert.equal(typeof source.required, 'boolean', 'required is a decision, never absent');
        assert.ok(!source.path.startsWith('/') && !source.path.split('/').includes('..'),
            `${source.path} must stay a repository-relative path`);
    }
    const required = result.sources.filter((source) => source.required).map((source) => source.path);
    assert.ok(required.some((path) => path.endsWith('data-paper')),
        'the data paper bounds what may be claimed, so drafting without it is not allowed');
    assert.ok(required.includes('proposals'),
        'the claims come from the managed proposal, so drafting without it is not allowed');
});

test('the data-paper source is the declared bound on claims, at advisory severity', async () => {
    const result = await loaded();
    assert.equal(result.authoritySeverity, 'advisory');
    assert.equal(result.authorityNames.length, 1, 'exactly one source bounds what may be claimed');
    assert.ok(result.sources.some((source) => source.path === result.authorityNames[0] && source.required),
        'the bounding source must be one of the declared sources, and a required one');
});

test('a claim of an achieved result conflicts with the bound; describing planned work does not', async () => {
    const result = await loaded();
    assert.equal(result.conflictOnAchievedResult.length, 1, JSON.stringify(result.conflictOnAchievedResult));
    assert.equal(result.conflictOnAchievedResult[0].sourceName, result.authorityNames[0]);
    assert.ok(result.conflictOnAchievedResult[0].id);
    assert.match(result.conflictOnAchievedResult[0].evidence, /outperforms/);
    assert.deepEqual(result.conflictOnPlannedWork, []);
});

test('the data paper quoted under the reference-sources heading is not a source-authority conflict', async () => {
    const result = await loaded();
    assert.deepEqual(result.conflictInReferenceSources, [],
        'a verbatim data-paper fragment inside the reference-sources section must not raise SOURCE_AUTHORITY_CONFLICT');
    assert.equal(result.conflictInExperiment.length, 1, JSON.stringify(result.conflictInExperiment));
    assert.match(result.conflictInExperiment[0].evidence, /obtained from a nearby weather station/);
    assert.equal(result.conflictAfterReferenceSources.length, 1, JSON.stringify(result.conflictAfterReferenceSources));
    assert.match(result.conflictAfterReferenceSources[0].evidence, /outperforms every baseline/);
});

test('the core reports not-applicable on a document with no experimental structure, and a real loss otherwise', async () => {
    const result = await loaded();
    assert.equal(result.plainAtoms, 0, 'core computes preservationApplicable as `atoms(before).size > 0`');
    assert.ok(result.richAtoms > 0);
    assert.deepEqual(result.lostFigure, ['figure'], 'dropping the figure placeholder must be reported as a lost atom');
    assert.equal(result.lostNothing, 0, 'an unchanged document loses nothing, which is a pass and not a vacuous one');
});

// Phase 2 (change 11, "a north a second domain can hold"): this domain declares
// its OWN north -- bound -> validated -> deliberated -> composed -> published --
// not the mathematical sibling's stages read back through a shared engine const.
test('the profile declares its own north: bound, validated, deliberated, composed, published -- not the mathematical stages', async () => {
    const result = await loaded();
    assert.deepEqual(result.objectiveStages, ['bound', 'validated', 'deliberated', 'composed', 'published']);
    assert.doesNotMatch(result.objectivePurpose, /mathematics/i, 'the experimental north must not carry the mathematical sibling\'s subject');
    assert.doesNotMatch(result.objectiveArrival, /mathematics/i, 'the experimental north must not carry the mathematical sibling\'s subject');
});

test('the north declares no entrance: proposals/ is a required source, not a mid-flow arrival', async () => {
    const result = await loaded();
    assert.equal(result.objectiveEntrances, null, 'this domain has no handoff producing a finding the way the mathematical sibling does');
});

test('the north declares at least one human stop', async () => {
    const result = await loaded();
    assert.ok(result.objectiveHumanStops.length >= 1);
});

// Spec scenario "The experimental profile declares its own north"
// (specs/deliberation-objective-flow/spec.md): runs the REAL launcher this
// skill ships, not a harness that imports the profile directly, so this
// proves the whole wiring end to end -- launcher, engine, `STATUS`, and both
// error paths all resolve back to this domain's own text.
const cliPath = path.join(skillDir, 'cli.mjs');

test('runStatus on the experimental CLI emits the experimental stages, not the mathematical ones', async () => {
    const directory = await mkdtemp(path.join(os.tmpdir(), 'experimental-deliberation-cli-'));
    const env = { ...process.env, PROPOSAL_DELIBERATION_PROJECT_ROOT: directory };
    delete env.DELIBERATION_DOMAIN_PROFILE;
    const { stdout } = await execFileAsync('node', [cliPath, '{"operation":"STATUS"}'], { env });
    const result = JSON.parse(stdout);
    assert.equal(result.status, 'ok');
    assert.deepEqual(result.objective.stages.map((stage) => stage.stage), ['bound', 'validated', 'deliberated', 'composed', 'published']);
    assert.doesNotMatch(result.objective.purpose, /mathematics/i);
});

test('a malformed request on the experimental CLI still carries the experimental north on its error path', async () => {
    const directory = await mkdtemp(path.join(os.tmpdir(), 'experimental-deliberation-cli-err-'));
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
    assert.deepEqual(result.objective.stages.map((stage) => stage.stage), ['bound', 'validated', 'deliberated', 'composed', 'published']);
});
