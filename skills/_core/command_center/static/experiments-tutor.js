/* Experiments tutor card of the "Experiments" tab (skills/experiments-tutor).
 *
 * Each message runs one headless turn of the `experiments-tutor` agent
 * (POST /api/terminal/tutor/experiments/turn) with a mode and a decision area;
 * its structured answer is rendered with the math panel's safe rich-text
 * helper (window.mathRichText: escaped text, a Markdown subset and KaTeX). The
 * card lives outside #experimentsRoot, which experiments-panel.js repaints
 * wholesale, so the thread and the composer survive a refresh.
 *
 * "Deliberate this change" types the turn's deliberation_prompt into the CLI
 * assistant as `/experimental-deliberation …` without pressing Enter: the
 * operator reads it there first, and that skill holds the human gate.
 *
 * Public surface (window): refreshExperimentsTutor(), ExperimentsTutor.
 */
(function () {
  'use strict';

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const HEADERS = { 'Content-Type': 'application/json', 'X-Papersmith-Terminal': '1' };
  const BASE = '/api/terminal/tutor/experiments';
  // Display labels of the design scale 0-4 (experiments_tutor.LEVELS holds the stored values).
  const LEVELS = ['xtutor.level.0', 'xtutor.level.1', 'xtutor.level.2', 'xtutor.level.3', 'xtutor.level.4'];
  const level = (i) => (LEVELS[i] ? t(LEVELS[i]) : '');
  // Same ids and order as experiments_tutor.AREAS; each value is its catalogue key.
  const AREAS = {
    architecture: 'xtutor.area.architecture',
    hyperparameters: 'xtutor.area.hyperparameters',
    ablation: 'xtutor.area.ablation',
    significance: 'xtutor.area.significance',
    'toy-set': 'xtutor.area.toy-set',
    training: 'xtutor.area.training',
    'upper-bounds': 'xtutor.area.upper-bounds',
    baselines: 'xtutor.area.baselines',
    validation: 'xtutor.area.validation',
    compute: 'xtutor.area.compute',
    reproducibility: 'xtutor.area.reproducibility',
    general: 'xtutor.area.general',
  };
  const MODES = { ask: 'xtutor.mode.ask', explain: 'xtutor.mode.explain', evaluate: 'xtutor.mode.evaluate' };
  const areaLabel = (id) => (AREAS[id] ? t(AREAS[id]) : (id || ''));
  const modeLabel = (id) => (MODES[id] ? t(MODES[id]) : (id || ''));
  const state = { mode: 'ask', busy: false, turns: [] };
  const $ = (id) => document.getElementById(id);

  function escapeHtml(text) {
    return String(text ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[c]);
  }

  function rich(text) {
    return typeof window.mathRichText === 'function' ? window.mathRichText(text) : `<p>${escapeHtml(text)}</p>`;
  }
  const inline = (text) => rich(text).replace(/^<p>|<\/p>$/g, '');

  function setStatus(text, tone) {
    const el = $('xtutorStatus');
    if (!el) return;
    el.textContent = text;
    el.dataset.tone = tone || 'muted';
  }

  function renderMeter(currentLevel) {
    const meter = $('xtutorMeter');
    if (!meter) return;
    const lvl = Number.isInteger(currentLevel) ? currentLevel : 0;
    meter.innerHTML = LEVELS.slice(1).map((_, i) => `<span class="tutor-meter__dot${i < lvl ? ' is-on' : ''}" title="${i + 1} · ${escapeHtml(level(i + 1))}"></span>`).join('')
      + `<span class="tutor-meter__label">${lvl} · ${escapeHtml(level(lvl))}</span>`;
  }

  function list(label, items, code) {
    if (!(items || []).length) return '';
    const body = items.map((item) => `<li>${code ? `<code>${escapeHtml(item)}</code>` : inline(item)}</li>`).join('');
    return `<div class="xtutor-list"><span class="math-label">${escapeHtml(label)}</span><ul>${body}</ul></div>`;
  }

  function renderTurn(turn, index) {
    if (turn.role === 'reader') {
      return `<div class="tutor-msg tutor-msg--reader"><div class="tutor-msg__meta">${escapeHtml(t('tutor.you'))} · ${escapeHtml(modeLabel(turn.mode))} · ${escapeHtml(areaLabel(turn.area))}</div>${rich(turn.message || '')}</div>`;
    }
    const a = turn.assessment || {};
    const deliberation = turn.deliberation_prompt
      ? `<div class="xtutor-deliberate"><span class="math-label">${escapeHtml(t('xtutor.proposedChange'))}</span>${rich(turn.deliberation_prompt)}
         <button type="button" class="btn btn--sm" data-xtutor-deliberate="${index}" title="${escapeHtml(t('xtutor.deliberateTitle'))}">${escapeHtml(t('xtutor.deliberate'))}</button></div>`
      : '';
    return `<div class="tutor-msg tutor-msg--tutor">
      <div class="tutor-msg__meta">${escapeHtml(t('tutor.tutor'))} · ${escapeHtml(areaLabel(turn.decision_area))} · ${escapeHtml(turn.agent || '')}</div>
      ${rich(turn.reply)}
      <div class="tutor-question">${rich(turn.question)}</div>
      <div class="tutor-assess"><span>${escapeHtml(t('xtutor.design', { level: a.level }))} · ${escapeHtml(level(a.level) || a.label || '')}</span>${a.evidence ? ` — ${inline(a.evidence)}` : ''}${(a.gaps || []).length ? `<ul>${a.gaps.map((g) => `<li>${inline(g)}</li>`).join('')}</ul>` : ''}</div>
      ${list(t('xtutor.risks'), turn.risks, false)}
      ${list(t('xtutor.evidenceRead'), turn.evidence, true)}
      ${turn.next_step ? `<div class="tutor-next"><span class="math-label">${escapeHtml(t('tutor.nextStep'))}</span>${rich(turn.next_step)}</div>` : ''}
      ${deliberation}
    </div>`;
  }

  function renderThread(thread) {
    const box = $('xtutorThread');
    if (!box) return;
    state.turns = thread.turns || [];
    box.innerHTML = state.turns.length ? state.turns.map(renderTurn).join('')
      : `<p class="math-muted">${t('xtutor.emptyHtml')}</p>`;
    const last = [...state.turns].reverse().find((turn) => turn.role === 'tutor');
    renderMeter(last && last.assessment ? last.assessment.level : 0);
    box.scrollTop = box.scrollHeight;
  }

  async function loadThread() {
    try {
      const res = await fetch(`${BASE}/thread`, { headers: HEADERS });
      if (res.status === 403 || res.status === 404) {
        setStatus(res.status === 404 ? t('tutor.disabled') : t('tutor.openFromLink'), 'bad');
        renderThread({ turns: [] });
        return;
      }
      renderThread(await res.json());
      // A refresh while a turn runs keeps its "reading…" status; send() sets the outcome.
      if (!state.busy) setStatus(t('common.ready'), 'ok');
    } catch (_) { setStatus(t('tutor.offline'), 'bad'); }
  }

  async function send() {
    if (state.busy) return;
    const input = $('xtutorInput');
    const message = (input?.value || '').trim();
    if (!message) { setStatus(t('xtutor.writeQuestion'), 'bad'); return; }
    const area = $('xtutorArea')?.value || 'general';
    const button = $('xtutorSend');
    state.busy = true;
    if (button) button.disabled = true;
    setStatus(t('xtutor.thinking'), 'warn');
    try {
      const res = await fetch(`${BASE}/turn`, {
        method: 'POST', headers: HEADERS, body: JSON.stringify({ message, mode: state.mode, area }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      if (input) input.value = '';
      await loadThread();
      setStatus(t('tutor.answeredBy', { agent: body.agent }), 'ok');
    } catch (err) {
      setStatus(t('tutor.failed', { error: err.message }), 'bad');
    } finally {
      state.busy = false;
      if (button) button.disabled = false;
    }
  }

  async function resetThread() {
    if (!window.confirm(t('xtutor.confirmReset'))) return;
    await fetch(`${BASE}/thread`, { method: 'DELETE', headers: HEADERS, body: '{}' });
    loadThread();
  }

  // One line of plain text: a newline typed into the agent's prompt would submit
  // it early, and any other control character (ESC, BEL, DEL) is a terminal command.
  function deliberationCommand(prompt) {
    const text = String(prompt || '').replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim();
    return `/experimental-deliberation ${text}`;
  }

  async function deliberate(prompt) {
    if (typeof window.sendToCli !== 'function') {
      setStatus(t('xtutor.cliUnavailable'), 'bad');
      return false;
    }
    const sent = await window.sendToCli(deliberationCommand(prompt), false, { kind: 'slash' });
    setStatus(sent ? t('xtutor.cliWritten') : t('xtutor.cliFailed'), sent ? 'ok' : 'bad');
    return sent;
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('xtutorSend')?.addEventListener('click', send);
    $('xtutorReset')?.addEventListener('click', resetThread);
    $('xtutorInput')?.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send(); });
    $('xtutorThread')?.addEventListener('click', (e) => {
      const button = e.target && e.target.closest ? e.target.closest('[data-xtutor-deliberate]') : null;
      const turn = button ? state.turns[Number(button.getAttribute('data-xtutor-deliberate'))] : null;
      if (turn && turn.deliberation_prompt) deliberate(turn.deliberation_prompt);
    });
    document.querySelectorAll('[data-xtutor-mode]').forEach((b) => b.addEventListener('click', () => {
      state.mode = b.dataset.xtutorMode;
      document.querySelectorAll('[data-xtutor-mode]').forEach((x) => x.classList.toggle('is-on', x === b));
    }));
    renderMeter(0);
  });

  // Labels are drawn here; the thread itself keeps its language.
  document.addEventListener('languagechange', () => { renderThread({ turns: state.turns }); });

  window.refreshExperimentsTutor = loadThread;
  window.ExperimentsTutor = { AREAS, renderTurn, renderThread, send, deliberate, deliberationCommand };
})();
