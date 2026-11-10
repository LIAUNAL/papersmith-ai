/* Agents Office: the smith agents and their orchestrator at work, in 3D.
 *
 * Spec odd/tasks/agents-office-3d.md. The roster is every agent defined in
 * the workspace (.claude/agents) plus the orchestrator, served measured by
 * GET /api/terminal/office (under the terminal cookie's path); office3d.js (a module on the vendored three.js
 * 0.183.0, weherd's office) draws it. This controller polls while the tab is
 * open, marks the agents of a running phase (the phase runs this browser
 * tracks in localStorage), keeps the legend and the status line honest, and
 * opens a read-only card on click. Nothing here closes, interrupts or writes
 * to a session; "Open console" only opens the existing CLI console.
 *
 * Public surface (window): officeWake(), officeModel (pure helpers, tested).
 */
(function () {
  'use strict';

  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const STATES = ['working', 'saving', 'loading', 'available'];
  const POLL_MS = 2000;

  const state = { info: null, error: null, card: null, mounted: false, sceneError: null, timer: null };

  // ---- pure model (window.officeModel) -------------------------------------
  function phaseRunsStore(storage, host) {
    try {
      return JSON.parse(storage.getItem(`smith_phase_runs@${host}`) || '{}') || {};
    } catch (_) {
      return {};
    }
  }

  /** Phase runs still running: started, neither stopped nor verified. */
  function runningRuns(runs) {
    return Object.values(runs || {}).filter((r) => r && r.stage && !r.stoppedAt && !r.verifiedAt);
  }

  /** The snapshot the scene draws: each agent gains `inPhase` when its
   *  dashboard stage is running; the orchestrator gains the running runs. */
  function decorate(info, runs) {
    const live = runningRuns(runs);
    const stages = new Set(live.map((r) => r.stage));
    const agents = ((info && info.agents) || []).map((a) => ({
      ...a, inPhase: (a.stages || []).some((s) => stages.has(s)),
    }));
    return { ...(info || {}), agents, runs: live };
  }

  function counts(info) {
    const out = { working: 0, saving: 0, loading: 0, available: 0 };
    for (const a of (info && info.agents) || []) if (a.state in out) out[a.state] += 1;
    return out;
  }

  /** What the card says the agent is doing right now, from measured facts. */
  function taskOf(agent, info) {
    const memory = ((info && info.memory) || {}).interactions || [];
    const last = [...memory].reverse().find((m) => m.agent === agent.id);
    if (agent.state === 'saving' || agent.state === 'loading') {
      return t(`office.task.${agent.state}`, { line: last ? last.line : '' });
    }
    if (agent.state === 'working') return t('office.task.working');
    if (agent.id === 'orchestrator') {
      const run = (info.runs || [])[0];
      if (run) return t('office.phaseTask', { phase: run.name || run.stage, command: run.command || '' });
    }
    if (agent.inPhase) return t('office.task.inPhase');
    return t('office.noTask');
  }

  window.officeModel = { phaseRunsStore, runningRuns, decorate, counts, taskOf };

  // ---- data ----------------------------------------------------------------
  function host() {
    return (typeof location !== 'undefined' && location.host) || 'local';
  }

  async function refresh() {
    try {
      const res = await fetch('/api/terminal/office');
      const info = res.ok ? await res.json() : null;
      state.info = info ? decorate(info, phaseRunsStore(localStorage, host())) : null;
      state.error = res.ok ? null : `HTTP ${res.status}`;
    } catch (error) {
      state.error = String(error);
    }
    render();
  }

  // ---- rendering -----------------------------------------------------------
  function mountScene() {
    if (state.mounted) return;
    if (!window.officeScene) {
      // Module scripts run before DOMContentLoaded: no scene now means the
      // three.js module failed to load (no WebGL-capable module support).
      state.sceneError = 'three.js module not loaded';
      return;
    }
    const host = document.getElementById('officeStage');
    if (!host) return;
    try {
      window.officeScene.mount(host, {
        select: (id, event) => showCard(id, event),
      });
      state.mounted = true;
    } catch (error) {
      state.sceneError = String(error && error.message ? error.message : error);
    }
  }

  function render() {
    const info = state.info;
    const status = document.getElementById('officeStatus');
    const legend = document.getElementById('officeLegend');
    if (status) {
      let text;
      if (state.error) text = `${t('office.error')}: ${state.error}`;
      else if (!info) text = t('office.loading');
      else if (state.sceneError) text = t('office.noWebgl');
      else if (!info.enabled) text = t('office.disabled');
      else if (!info.authorized) text = t('office.unauthorized');
      else {
        const c = counts(info);
        text = t('office.status', {
          total: info.agents.length, working: c.working, memory: c.saving + c.loading,
          orchestrator: t(`office.state.${info.orchestrator.state}`),
        });
      }
      status.textContent = text;
    }
    if (legend && info) {
      const c = counts(info);
      legend.innerHTML = STATES.map((s) => `<span class="office-legend__item office-legend__item--${s}">`
        + `<i></i>${esc(t(`office.state.${s}`))} <b>${c[s]}</b></span>`).join('')
        + `<span class="office-legend__item office-legend__item--engram"><i></i>${esc(t('office.brain'))}`
        + ` <b>${esc(info.memory && info.memory.engram_path ? t('office.engramFound') : t('office.engramMissing'))}</b></span>`;
    }
    if (info && state.mounted) window.officeScene.update(info);
    if (state.card && info) refreshCard();
  }

  function findAgent(id) {
    const info = state.info || {};
    if (id === 'orchestrator') return { id, label: t('office.orchestrator'), ...(info.orchestrator || {}) };
    return (info.agents || []).find((a) => a.id === id) || null;
  }

  function cardHtml(agent) {
    const info = state.info || {};
    const s = agent.state || 'available';
    const rows = [];
    if (agent.id === 'orchestrator') {
      rows.push([t('office.role'), t('office.orchestratorRole')]);
      rows.push([t('office.cli'), (agent.clis || []).join(', ') || t('office.none')]);
    } else {
      rows.push([t('office.role'), agent.role || agent.id]);
      rows.push([t('office.model'), agent.model || t('office.modelInherited')]);
      rows.push([t('office.tramo'), agent.tramo || t('office.none')]);
      rows.push([t('office.phases'), (agent.phases || []).join(', ').replace(/<[^>]*>/g, '') || t('office.none')]);
    }
    rows.push([t('office.task'), taskOf(agent, info)]);
    return `<div class="office-card" role="dialog" aria-label="${esc(agent.label)}">
        <button type="button" class="office-card__close" data-office-close aria-label="${esc(t('office.close'))}">✕</button>
        <h4>${esc(agent.label)} <span class="office-card__status office-card__status--${esc(s)}">${esc(t(`office.state.${s}`))}</span></h4>
        ${rows.map(([k, v]) => `<p><strong>${esc(k)}:</strong> ${esc(v)}</p>`).join('')}
        <button type="button" class="office-card__open" data-office-open>${esc(t('office.openConsole'))}</button>
      </div>`;
  }

  function showCard(id, event) {
    const agent = findAgent(id);
    const host = document.getElementById('officeCardHost');
    if (!agent || !host) return;
    state.card = id;
    if (window.officeScene) window.officeScene.focus(id);
    host.innerHTML = cardHtml(agent);
    const stage = document.getElementById('officeStage');
    if (event && stage) {
      const rect = stage.getBoundingClientRect();
      host.style.left = `${Math.max(8, Math.min(rect.width - 310, event.clientX - rect.left + 12))}px`;
      host.style.top = `${Math.max(8, Math.min(rect.height - 200, event.clientY - rect.top + 12))}px`;
    }
    host.querySelector('[data-office-close]').addEventListener('click', closeCard);
    host.querySelector('[data-office-open]').addEventListener('click', () => {
      if (typeof window.openCliConsole === 'function') window.openCliConsole();
    });
  }

  function refreshCard() {
    const agent = findAgent(state.card);
    const host = document.getElementById('officeCardHost');
    if (!agent || !host || !host.firstElementChild) return;
    const left = host.style.left; const top = host.style.top;
    showCard(state.card);
    host.style.left = left; host.style.top = top;
  }

  function closeCard() {
    state.card = null;
    const host = document.getElementById('officeCardHost');
    if (host) host.innerHTML = '';
    if (window.officeScene) window.officeScene.focus(null);
  }

  // ---- lifecycle -----------------------------------------------------------
  function paneActive() {
    const pane = document.getElementById('pane-office');
    return !!(pane && pane.classList.contains('active') && document.visibilityState === 'visible');
  }

  function sync() {
    if (paneActive()) {
      mountScene();
      if (state.mounted) window.officeScene.start();
      if (!state.timer) { refresh(); state.timer = window.setInterval(refresh, POLL_MS); }
    } else {
      if (state.mounted) window.officeScene.stop();
      if (state.timer) { window.clearInterval(state.timer); state.timer = null; }
    }
  }

  window.officeWake = () => { closeCard(); sync(); refresh(); };

  document.addEventListener('DOMContentLoaded', () => {
    const pane = document.getElementById('pane-office');
    if (!pane) return;
    new MutationObserver(sync).observe(pane, { attributes: true, attributeFilter: ['class'] });
    document.addEventListener('visibilitychange', sync);
    window.addEventListener('office-scene-ready', sync);
    sync();
  });
})();
