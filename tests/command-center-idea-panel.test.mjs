// The dashboard's Idea tab (idea-shaping S6): the pure decisions of idea-panel.js (keyword chips, which
// step a reload opens, evidence labels, the bank chip, when the thematic help queries a bank, when
// "Launch plausibility" is enabled and the line it types). Runs the shipped sources in node with a stub DOM.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const STATIC = new URL('../skills/_core/command_center/static/', import.meta.url);
const read = (name) => readFileSync(new URL(name, STATIC), 'utf8');

function load(lang = 'en') {
  const store = { 'papersmith-lang': lang };
  const window = { localStorage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } } };
  const document = {
    documentElement: {}, readyState: 'complete', getElementById: () => null, querySelectorAll: () => [],
    addEventListener: () => {}, dispatchEvent: () => {},
  };
  const context = { window, document, CustomEvent: function CustomEvent() {}, setTimeout, clearTimeout };
  for (const file of ['i18n/en.js', 'i18n/es.js', 'i18n.js', 'idea-panel.js']) vm.runInNewContext(read(file), context);
  return window.IdeaPanel.logic;
}
// Objects built inside the vm context have that context's prototypes: compare their JSON.
const plain = (value) => JSON.parse(JSON.stringify(value));

test('keyword chips split on commas, trim, drop duplicates and stop at the cap', () => {
  const { addChips } = load();
  assert.deepEqual(plain(addChips([], ' eeg ,  domain shift; EEG,, graphs', 0)), ['eeg', 'domain shift', 'graphs']);
  assert.deepEqual(plain(addChips(['a', 'b', 'c', 'd'], 'e, f, g', 5)), ['a', 'b', 'c', 'd', 'e']);
  assert.deepEqual(plain(addChips(['a'], '   ', 5)), ['a']);
});

test('a reload opens the first unanswered step, and an unreachable bank keeps step 1 open', () => {
  const { firstOpenStep, stepDone } = load();
  assert.equal(firstOpenStep({}), 1);
  const brief = {
    bank: { choice: 'none' }, profile: { source: 'none' }, experience: { level: 'student', methods: [] },
    interests: { keywords: ['eeg'] }, chosen: { topic_ids: [] }, draft: { approved: false },
  };
  assert.equal(firstOpenStep(brief), 5);
  assert.equal(stepDone({ bank: { choice: 'banco-lia', available: false } }, 1), false);
  assert.equal(firstOpenStep({ ...brief, chosen: { topic_ids: ['t1'] }, draft: { approved: true } }), 6);
  // A skipped (optional) profile is not reopened once a later step is answered.
  assert.equal(firstOpenStep({ ...brief, profile: { source: null } }), 5);
  assert.equal(firstOpenStep({ bank: { choice: 'none' } }), 2);
});

test('every evidence source is named for a person, in both languages', () => {
  assert.deepEqual(['bank:labbank', 'openalex', 'profile', 'operator', 'guide', 'other'].map(load().evidenceLabel),
    ['Bank: labbank', 'OpenAlex', 'Profile', 'You', 'Guide', 'other']);
  assert.equal(load('es').evidenceLabel('operator'), 'Usted');
});

test('the bank chip says available, compatible, guide-only, unreachable or none', () => {
  const { bankChip } = load();
  assert.equal(bankChip({}), null);
  assert.deepEqual(plain(bankChip({ choice: 'none' })), ['badge--info', 'No bank is queried']);
  assert.deepEqual(plain(bankChip({ choice: 'banco-lia', available: true })), ['badge--ok', 'Available']);
  assert.deepEqual(plain(bankChip({ choice: 'banco-lia', available: false, reason: 'offline' })),
    ['badge--bad', 'Unreachable: offline']);
  assert.equal(bankChip({ choice: 'other', server: 'lab', available: true, compatible: true })[1],
    'lab: compatible, queried like banco-lia');
  assert.equal(bankChip({ choice: 'other', server: 'notes', available: true, compatible: false })[0], 'badge--warn');
});

test('the thematic help queries banco-lia or a compatible bank, never none or a conversation-only one', () => {
  const { suggestKind } = load();
  assert.equal(suggestKind({ choice: 'banco-lia', available: true }), 'banco-lia');
  assert.equal(suggestKind({ choice: 'banco-lia', available: false }), null);
  assert.equal(suggestKind({ choice: 'other', compatible: true, available: true }), 'other');
  assert.equal(suggestKind({ choice: 'other', compatible: false, available: true }), null);
  assert.equal(suggestKind({ choice: 'none' }), null);
});

test('launch needs the approved draft unchanged in the editor and carries the gate marker', () => {
  const { canLaunch, launchLine } = load();
  const text = 'A problem. A proposal.';
  const view = { ready: true, handoff: `/plausibility ${text}`, brief: { draft: { approved: true, text } } };
  assert.equal(canLaunch(view, text), true);
  assert.equal(canLaunch(view, `${text}  `), true);
  assert.equal(canLaunch(view, `${text} Edited.`), false);
  assert.equal(canLaunch({ ...view, ready: false }, text), false);
  assert.equal(launchLine(view.handoff), `/plausibility ${text} [prompt-gate: approved]`);
});
