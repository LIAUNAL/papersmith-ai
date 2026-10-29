/* Experiments tutor card of the "Experimentos" tab (skills/experiments-tutor).
 *
 * Each message runs one headless turn of the `experiments-tutor` agent
 * (POST /api/terminal/tutor/experiments/turn) with a mode and a decision area;
 * its structured answer is rendered with the math panel's safe rich-text
 * helper (window.mathRichText: escaped text, a Markdown subset and KaTeX). The
 * card lives outside #experimentsRoot, which experiments-panel.js repaints
 * wholesale, so the thread and the composer survive a refresh.
 *
 * "Deliberar este cambio" types the turn's deliberation_prompt into the CLI
 * assistant as `/experimental-deliberation …` without pressing Enter: the
 * operator reads it there first, and that skill holds the human gate.
 *
 * Public surface (window): refreshExperimentsTutor(), ExperimentsTutor.
 */
(function () {
  'use strict';

  const HEADERS = { 'Content-Type': 'application/json', 'X-Papersmith-Terminal': '1' };
  const BASE = '/api/terminal/tutor/experiments';
  const LEVELS = ['sin evidencia', 'declarada', 'justificada', 'controlada', 'defendible'];
  // Same ids and order as experiments_tutor.AREAS.
  const AREAS = {
    architecture: 'Arquitectura de la red',
    hyperparameters: 'Hiperparámetros y búsqueda',
    ablation: 'Estudios de ablación',
    significance: 'Pruebas de significancia estadística',
    'toy-set': 'Propósito del toy set',
    training: 'Estrategias de entrenamiento',
    ceilings: 'Techos (cotas y oráculos)',
    baselines: 'Métodos a comparar y su implementación',
    validation: 'Esquema de validación y fuga de datos',
    compute: 'Presupuesto de cómputo y sesión',
    reproducibility: 'Reproducibilidad',
    general: 'General',
  };
  const MODES = { ask: 'preguntar', explain: 'explícame', evaluate: 'evalúame' };
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

  function renderMeter(level) {
    const meter = $('xtutorMeter');
    if (!meter) return;
    const lvl = Number.isInteger(level) ? level : 0;
    meter.innerHTML = LEVELS.slice(1).map((label, i) => `<span class="tutor-meter__dot${i < lvl ? ' is-on' : ''}" title="${i + 1} · ${label}"></span>`).join('')
      + `<span class="tutor-meter__label">${lvl} · ${LEVELS[lvl]}</span>`;
  }

  function list(label, items, code) {
    if (!(items || []).length) return '';
    const body = items.map((item) => `<li>${code ? `<code>${escapeHtml(item)}</code>` : inline(item)}</li>`).join('');
    return `<div class="xtutor-list"><span class="math-label">${label}</span><ul>${body}</ul></div>`;
  }

  function renderTurn(turn, index) {
    if (turn.role === 'reader') {
      return `<div class="tutor-msg tutor-msg--reader"><div class="tutor-msg__meta">Tú · ${escapeHtml(MODES[turn.mode] || turn.mode || '')} · ${escapeHtml(AREAS[turn.area] || turn.area || '')}</div>${rich(turn.message || '')}</div>`;
    }
    const a = turn.assessment || {};
    const deliberation = turn.deliberation_prompt
      ? `<div class="xtutor-deliberate"><span class="math-label">Cambio propuesto para la deliberación</span>${rich(turn.deliberation_prompt)}
         <button type="button" class="btn btn--sm" data-xtutor-deliberate="${index}" title="Escribe la instrucción en el asistente CLI como /experimental-deliberation; revísala y pulsa Enter allí">Deliberar este cambio</button></div>`
      : '';
    return `<div class="tutor-msg tutor-msg--tutor">
      <div class="tutor-msg__meta">Tutor · ${escapeHtml(AREAS[turn.decision_area] || turn.decision_area || '')} · ${escapeHtml(turn.agent || '')}</div>
      ${rich(turn.reply)}
      <div class="tutor-question">${rich(turn.question)}</div>
      <div class="tutor-assess"><span>Diseño ${escapeHtml(a.level)} · ${escapeHtml(LEVELS[a.level] || a.label || '')}</span>${a.evidence ? ` — ${inline(a.evidence)}` : ''}${(a.gaps || []).length ? `<ul>${a.gaps.map((g) => `<li>${inline(g)}</li>`).join('')}</ul>` : ''}</div>
      ${list('Riesgos', turn.risks, false)}
      ${list('Evidencia leída', turn.evidence, true)}
      ${turn.next_step ? `<div class="tutor-next"><span class="math-label">Siguiente paso</span>${rich(turn.next_step)}</div>` : ''}
      ${deliberation}
    </div>`;
  }

  function renderThread(thread) {
    const box = $('xtutorThread');
    if (!box) return;
    state.turns = thread.turns || [];
    box.innerHTML = state.turns.length ? state.turns.map(renderTurn).join('')
      : '<p class="math-muted">Elige una decisión y pregunta. El tutor lee el protocolo de <code>experiments/</code>, las aprobaciones, el código y los resultados de <code>implementations/</code> antes de responder, hace una pregunta a la vez y evalúa el diseño. Si aún no hay resultados, lo dice: nunca inventa números. Un cambio de decisión se lleva a <code>/experimental-deliberation</code>.</p>';
    const last = [...state.turns].reverse().find((t) => t.role === 'tutor');
    renderMeter(last && last.assessment ? last.assessment.level : 0);
    box.scrollTop = box.scrollHeight;
  }

  async function loadThread() {
    try {
      const res = await fetch(`${BASE}/thread`, { headers: HEADERS });
      if (res.status === 403 || res.status === 404) {
        setStatus(res.status === 404 ? 'Tutor deshabilitado (solo en 127.0.0.1)' : 'Abre el tablero desde el enlace de acceso de smith ui', 'bad');
        renderThread({ turns: [] });
        return;
      }
      renderThread(await res.json());
      setStatus('Listo', 'ok');
    } catch (_) { setStatus('Sin conexión con el servidor', 'bad'); }
  }

  async function send() {
    if (state.busy) return;
    const input = $('xtutorInput');
    const message = (input?.value || '').trim();
    if (!message) { setStatus('Escribe una pregunta sobre el diseño', 'bad'); return; }
    const area = $('xtutorArea')?.value || 'general';
    const button = $('xtutorSend');
    state.busy = true;
    if (button) button.disabled = true;
    setStatus('El tutor está leyendo el protocolo, el código y los resultados… (suele tardar 30–90 s)', 'warn');
    try {
      const res = await fetch(`${BASE}/turn`, {
        method: 'POST', headers: HEADERS, body: JSON.stringify({ message, mode: state.mode, area }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      if (input) input.value = '';
      await loadThread();
      setStatus(`Respondió ${body.agent}`, 'ok');
    } catch (err) {
      setStatus(`El tutor no pudo responder: ${err.message}`, 'bad');
    } finally {
      state.busy = false;
      if (button) button.disabled = false;
    }
  }

  async function resetThread() {
    if (!window.confirm('¿Empezar una conversación nueva? El hilo actual del tutor de experimentos se borra.')) return;
    await fetch(`${BASE}/thread`, { method: 'DELETE', headers: HEADERS, body: '{}' });
    loadThread();
  }

  // One line: a newline typed into the agent's prompt would submit it early.
  function deliberationCommand(prompt) {
    return `/experimental-deliberation ${String(prompt || '').replace(/\s+/g, ' ').trim()}`;
  }

  async function deliberate(prompt) {
    if (typeof window.sendToCli !== 'function') {
      setStatus('El asistente CLI no está disponible en esta página', 'bad');
      return false;
    }
    const sent = await window.sendToCli(deliberationCommand(prompt), false, { kind: 'slash' });
    setStatus(sent ? 'Instrucción escrita en el asistente CLI: revísala y pulsa Enter allí' : 'No se pudo escribir en el asistente CLI', sent ? 'ok' : 'bad');
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

  window.refreshExperimentsTutor = loadThread;
  window.ExperimentsTutor = { AREAS, renderTurn, renderThread, send, deliberate, deliberationCommand };
})();
