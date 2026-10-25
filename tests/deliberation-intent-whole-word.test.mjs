// #75: destructive intent is parsed from whole words, never from substrings
// inside ordinary words ("borrador" contains "borra", "preliminares" contains
// "elimina").
import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
const { createJiti } = await import('jiti');
const jiti = createJiti(import.meta.url);
const v2 = await jiti.import(path.resolve('skills/_core/deliberation/engine/exports.ts'));

test('ordinary words that contain a destructive verb do not resolve to DELETE', () => {
  for (const instruction of [
    'Revisa el borrador de la sección de resultados',
    'Mejora los resultados preliminares',
    'Describe el quitasol de la figura 3',
  ]) {
    const intent = v2.resolveIntent(instruction);
    assert.notEqual(intent.intent, 'DELETE', instruction);
    assert.equal(intent.destructiveIntent, false, instruction);
  }
});

test('ambiguous wording without an explicit operation asks for clarification', () => {
  const intent = v2.resolveIntent('Revisa el borrador de la sección de resultados');
  assert.equal(intent.intent, 'AMBIGUOUS');
  assert.equal(intent.confidence, 0);
  assert.deepEqual(intent.pendingQuestions, ['Indicá el fragmento o alcance exacto.']);
});

test('explicit delete requests still resolve to DELETE, including infinitive forms', () => {
  for (const instruction of [
    'elimina esta sección',
    'Elimina el párrafo final.',
    'borra este párrafo',
    'quita la oración repetida',
    'eliminar el párrafo de métodos',
    'suprime la última frase',
    'eliminalo del texto',
  ]) {
    const intent = v2.resolveIntent(instruction);
    assert.equal(intent.intent, 'DELETE', instruction);
    assert.equal(intent.destructiveIntent, true, instruction);
  }
});

test('a verb inside another verb does not select its operation ("mueve" in "remueve")', () => {
  const intent = v2.resolveIntent('remueve la tabla 2');
  assert.equal(intent.intent, 'DELETE');
  assert.equal(intent.removeSource, false);
});
