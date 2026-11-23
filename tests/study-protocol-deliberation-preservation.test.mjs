// The study-protocol domain's preservation gate and field parser: which atoms a protocol
// declares (a lost one must be acknowledged by id before a successor publishes), the
// canonical-form rules that block outright, and the parsed fields later units read (the
// analysis log and verify need the outcome ids).
//
// Loaded IN PROCESS: `preservation-study-protocol.ts` and `protocol-fields.ts` import only
// `types.js` (for `sha256`), never `domain-profile.js`, so nothing here touches the single
// `DELIBERATION_DOMAIN_PROFILE` the whole suite run is fixed to.
import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const repoRoot = process.cwd();
const piRoot = path.resolve('.');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
    '@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
    '@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
    typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const skillDir = path.join(repoRoot, 'skills/study-protocol-deliberation');
const { extractAtoms, violations } = await jiti.import(path.join(skillDir, 'preservation-study-protocol.ts'));
const { parseProtocol, outcomeIds } = await jiti.import(path.join(skillDir, 'protocol-fields.ts'));

const rules = (source) => violations(source).map((entry) => entry.rule).sort();
const kinds = (source) => [...new Set([...extractAtoms(source).values()].map((atom) => atom.kind))].sort();

const FIELDS = {
    question: '**Research question:** In adults with stage 1 hypertension, does a 12-week supervised walking programme lower systolic blood pressure compared with usual care?',
    primary: '**Primary outcome:** O1 -- change in seated systolic blood pressure (mmHg) from baseline; time point: 12 weeks',
    secondary: '**Secondary outcome:** O2 -- change in diastolic blood pressure (mmHg); time point: 12 weeks',
    design: '**Design:** two-arm, parallel-group randomised controlled trial, 1:1 allocation, assessor-blinded',
    eligibility: '**Eligibility:** adults aged 40 to 70 with untreated stage 1 hypertension; exclusion: unstable cardiovascular disease',
    size: '**Sample size:** 148 participants (74 per arm)',
    justification: '**Sample size justification:** a two-sided t-test at alpha 0.05 with 80% power detects a 5 mmHg difference with an assumed SD of 10 mmHg at 64 per arm, inflated by 15% for attrition',
    model: '**Primary model:** ANCOVA of the 12-week systolic change on arm, adjusted for baseline, for [outcome:O1]',
    covariates: '**Covariates:** baseline systolic blood pressure, age, sex',
    missing: '**Missing data:** multiple imputation by chained equations under missing at random, 20 imputations',
    multiplicity: '**Multiplicity:** not applicable to the single primary outcome; secondary outcomes reported with 95% confidence intervals only',
};

/** A protocol carrying every required field once, with `overrides` replacing (or, with null, dropping) a field. */
function protocol(overrides = {}, extra = []) {
    const fields = { ...FIELDS, ...overrides };
    const lines = Object.values(fields).filter((line) => line !== null);
    return `# Study protocol\n\n## Fields\n\n${[...lines, ...extra].join('\n\n')}\n`;
}

const VALID = protocol();

// ---------------------------------------------------------------------------
// The genuine pass and the parsed fields
// ---------------------------------------------------------------------------

test('a protocol declaring every required field once breaks no rule', () => {
    assert.deepEqual(violations(VALID), []);
});

test('parseProtocol exposes the primary and secondary outcomes with their ids, measures and time points', () => {
    const parsed = parseProtocol(VALID);
    assert.equal(parsed.primaryOutcomeId, 'O1');
    assert.deepEqual(parsed.outcomes.map(({ id, role, measure, timePoint }) => ({ id, role, measure, timePoint })), [
        { id: 'O1', role: 'primary', measure: 'change in seated systolic blood pressure (mmHg) from baseline', timePoint: '12 weeks' },
        { id: 'O2', role: 'secondary', measure: 'change in diastolic blood pressure (mmHg)', timePoint: '12 weeks' },
    ]);
    assert.deepEqual(outcomeIds(VALID), { primary: 'O1', secondary: ['O2'] });
    assert.equal(parsed.sampleSize.value, '148 participants (74 per arm)');
    assert.match(parsed.sampleSize.justification, /80% power/);
    assert.match(parsed.analysisPlan.primaryModel, /^ANCOVA/);
    assert.equal(parsed.analysisPlan.covariates, 'baseline systolic blood pressure, age, sex');
    assert.match(parsed.analysisPlan.missingData, /multiple imputation/);
    assert.match(parsed.analysisPlan.multiplicity, /not applicable/);
    assert.match(parsed.researchQuestion, /walking programme/);
    assert.match(parsed.design, /randomised controlled trial/);
    assert.match(parsed.eligibility, /aged 40 to 70/);
});

test('a label written with the colon outside the bold, or carried by a bullet, is the same declaration', () => {
    const source = protocol({ design: '- **Design**: two-arm parallel-group randomised controlled trial' });
    assert.deepEqual(violations(source), []);
    assert.equal(parseProtocol(source).design, 'two-arm parallel-group randomised controlled trial');
});

// ---------------------------------------------------------------------------
// D3: exactly one primary outcome
// ---------------------------------------------------------------------------

test('a protocol with no primary outcome is refused', () => {
    const source = protocol({ primary: null, model: '**Primary model:** ANCOVA of the systolic change on arm' });
    assert.deepEqual(rules(source), ['primary-outcome-missing']);
    assert.equal(parseProtocol(source).primaryOutcomeId, null);
});

test('a protocol with two primary outcomes is refused, not reduced to the first', () => {
    const second = '**Primary outcome:** O3 -- home systolic blood pressure (mmHg); time point: 12 weeks';
    const found = violations(protocol({}, [second]));
    assert.deepEqual(found.map((entry) => entry.rule), ['primary-outcome-repeated']);
    assert.match(found[0].detail, /exactly one/);
    assert.equal(parseProtocol(protocol({}, [second])).primaryOutcomeId, null, 'two candidates name no primary outcome');
});

test('an outcome without an id, without a measure or without a time point is refused', () => {
    assert.deepEqual(rules(protocol({ primary: '**Primary outcome:** systolic blood pressure; time point: 12 weeks' })), ['outcome-without-id']);
    assert.deepEqual(rules(protocol({ primary: '**Primary outcome:** O1 -- TBD; time point: 12 weeks' })), ['outcome-without-measure']);
    assert.deepEqual(rules(protocol({ primary: '**Primary outcome:** O1 -- systolic blood pressure (mmHg)' })), ['outcome-without-time-point']);
    assert.deepEqual(rules(protocol({ secondary: '**Secondary outcome:** O2 -- diastolic blood pressure; time point: pending' })), ['outcome-without-time-point']);
});

test('two outcomes sharing one id are refused', () => {
    assert.deepEqual(rules(protocol({ secondary: '**Secondary outcome:** O1 -- diastolic blood pressure; time point: 12 weeks' })), ['outcome-id-repeated']);
});

test('secondary outcomes are declared: one or more lines, or an explicit none, never silence or both', () => {
    assert.deepEqual(rules(protocol({ secondary: null })), ['secondary-outcomes-undeclared']);
    assert.deepEqual(violations(protocol({ secondary: '**Secondary outcomes:** none' })), []);
    assert.deepEqual(outcomeIds(protocol({ secondary: '**Secondary outcomes:** none' })), { primary: 'O1', secondary: [] });
    assert.deepEqual(rules(protocol({}, ['**Secondary outcomes:** none'])), ['secondary-outcomes-contradictory']);
});

// ---------------------------------------------------------------------------
// D3: sample size with its justification; analysis plan with its primary model
// ---------------------------------------------------------------------------

test('a sample size without a justification is refused', () => {
    assert.deepEqual(rules(protocol({ justification: null })), ['sample-size-without-justification']);
    assert.deepEqual(rules(protocol({ justification: '**Sample size justification:** TBD' })), ['sample-size-without-justification']);
});

test('a sample size naming no number, or no sample size at all, is refused', () => {
    assert.deepEqual(rules(protocol({ size: '**Sample size:** as many as can be recruited' })), ['sample-size-without-number']);
    assert.deepEqual(rules(protocol({ size: null })), ['sample-size-declaration-missing']);
});

test('an analysis plan without a primary model is refused', () => {
    assert.deepEqual(rules(protocol({ model: null })), ['analysis-plan-without-primary-model']);
    assert.deepEqual(rules(protocol({ model: '**Primary model:** to be decided' })), ['analysis-plan-without-primary-model']);
});

test('covariates, missing data and multiplicity are each declared; an explicit none is a decision, a placeholder is not', () => {
    assert.deepEqual(rules(protocol({ covariates: null, missing: null, multiplicity: null })),
        ['covariates-declaration-missing', 'missing-data-declaration-missing', 'multiplicity-declaration-missing']);
    assert.deepEqual(violations(protocol({ covariates: '**Covariates:** none (unadjusted analysis)' })), []);
    assert.deepEqual(rules(protocol({ multiplicity: '**Multiplicity:** TBD' })), ['multiplicity-declaration-missing']);
});

test('the question, the design and the eligibility are each declared exactly once', () => {
    assert.deepEqual(rules(protocol({ question: null, design: null, eligibility: null })),
        ['design-declaration-missing', 'eligibility-declaration-missing', 'research-question-declaration-missing']);
    assert.deepEqual(rules(protocol({}, ['**Design:** a second design line'])), ['design-declaration-repeated']);
});

test('a missing declaration reports line 1, and violations come back in line order', () => {
    const found = violations(protocol({ question: null }, ['See https://example.org/spirit']));
    assert.deepEqual(found.map((entry) => entry.rule), ['research-question-declaration-missing', 'url-without-verification-marker']);
    assert.equal(found[0].line, 1);
    assert.ok(found[1].line > 1);
});

// ---------------------------------------------------------------------------
// No result stated as already achieved
// ---------------------------------------------------------------------------

test('a field that states a result as already achieved is refused', () => {
    const found = violations(protocol({ primary: '**Primary outcome:** O1 -- systolic blood pressure, which was significantly reduced (p = 0.03); time point: 12 weeks' }));
    assert.deepEqual(found.map((entry) => entry.rule), ['field-states-result']);
    assert.deepEqual(rules(protocol({ question: '**Research question:** We found that walking lowers systolic pressure; does it?' })), ['field-states-result']);
});

test('planning fields may cite thresholds and prior evidence without being refused', () => {
    // A significance threshold, a past-tense eligibility criterion and a pilot
    // estimate behind a sample size are planning language, not this study's
    // result: only the outcome fields and the research question refuse.
    assert.deepEqual(violations(protocol({ justification: '**Sample size justification:** two-sided test at p < 0.05 with 80% power; in our pilot we observed an SD of 10 mmHg, so 64 per arm plus 15% attrition' })), []);
    assert.deepEqual(violations(protocol({ eligibility: '**Eligibility:** adults whose readings were higher than 140 mmHg at two screening visits' })), []);
});

test('prose outside the labelled fields is not refused for result language (the source bound reports it instead)', () => {
    assert.deepEqual(violations(protocol({}, ['A previous trial reported that walking was associated with lower pressure.'])), []);
});

test('a hypothesis written in the future tense is not a stated result', () => {
    assert.deepEqual(violations(protocol({ question: '**Research question:** Will a 12-week walking programme lower systolic pressure more than usual care?' })), []);
});

// ---------------------------------------------------------------------------
// URLs carry a verification tag (the experimental convention)
// ---------------------------------------------------------------------------

test('a URL carries [pending-verification] or [verified: YYYY-MM-DD] immediately after it', () => {
    assert.deepEqual(rules(protocol({}, ['SPIRIT 2025: https://example.org/spirit'])), ['url-without-verification-marker']);
    assert.deepEqual(violations(protocol({}, ['SPIRIT 2025: https://example.org/spirit [pending-verification]'])), []);
    assert.deepEqual(violations(protocol({}, ['[SPIRIT 2025](https://example.org/spirit) [verified: 2026-11-20]'])), []);
});

// ---------------------------------------------------------------------------
// Atoms: what must never vanish in silence
// ---------------------------------------------------------------------------

test('every field atom kind is extracted from a protocol that declares it', () => {
    assert.deepEqual(kinds(protocol({}, ['https://example.org/spirit [pending-verification]'])), [
        'design', 'eligibility', 'primary-model', 'primary-outcome', 'research-question', 'sample-size', 'secondary-outcome', 'url',
    ]);
});

test('a document with no protocol field declares no atoms, which the core reports as not applicable', () => {
    assert.equal(extractAtoms('# Study protocol\n\nA paragraph about the setting.\n').size, 0);
});

test('switching the primary outcome measure under the same id is a lost atom, not a silent edit', () => {
    const before = extractAtoms(VALID);
    const after = extractAtoms(protocol({ primary: '**Primary outcome:** O1 -- home systolic blood pressure (mmHg); time point: 12 weeks' }));
    const lost = [...before.keys()].filter((id) => !after.has(id));
    assert.equal(lost.length, 1, JSON.stringify(lost));
    assert.match(lost[0], /^primary-outcome:O1:/);
});

test('rewording a field by whitespace or case alone keeps its atom id', () => {
    const before = [...extractAtoms(VALID).keys()].sort();
    const reflowed = protocol({ primary: '**Primary outcome:**   O1 --  Change in seated systolic blood pressure (mmHg) from baseline;  time point: 12 weeks' });
    assert.deepEqual([...extractAtoms(reflowed).keys()].sort(), before);
});

test('the sample-size atom is keyed by its legible value, so a changed N is a loss a caller echoes back', () => {
    const ids = [...extractAtoms(VALID).keys()];
    assert.ok(ids.includes('sample-size:148 participants (74 per arm)'), JSON.stringify(ids));
});
