/* Phase run tracker: what happens after "Run" on a pipeline phase.
 *
 * A run starts when a phase action is sent. From then on every status poll
 * (GET /api/status) is compared with the snapshot taken at the start:
 *   1. Command sent         — the command reached the support terminal;
 *   2. Agent working        — the terminal printed output since the start;
 *   3. Artifacts            — the phase's evidence files appeared or changed;
 *   4. Stage verified       — the server's verdict for the phase is PASS;
 *   5. Next stages          — the phases the verdict unlocked.
 * The verdict is always the server's: this file never marks a phase done.
 * Runs survive a reload through localStorage when it is available.
 *
 * The bottom-left dock lists the followed runs on every tab; a click opens
 * the run's tracking panel in place, with the same checkpoints, the way to
 * the agent's terminal and "Stop process".
 *
 * Public surface (window.phaseRuns): start, onStatus, renderTracker,
 * cardBadge, isRunning, anyRunning, dismiss, justUnlocked, renderDock,
 * openPanel, stop.
 */
(function () {
  'use strict';

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  // Phase ids are the stable "Fase N"; this is how a person reads one.
  const phaseName = (id) => {
    const match = /^Fase (\d+)$/.exec(String(id || ''));
    return match ? t('phases.number', { n: match[1] }) : String(id || '');
  };

  // One store per dashboard server: two workspaces never share runs.
  const KEY = `smith_phase_runs@${(typeof location !== 'undefined' && location.host) || 'local'}`;
  const FAST_POLL_MS = 3000;
  const QUIET_MS = 30 * 60 * 1000;
  const UNLOCK_GLOW_MS = 15000;
  const IDLE_MS = 20000;

  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (_) { return {}; }
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(runs)); } catch (_) { /* storage blocked */ }
  }

  let runs = load();
  let fastTimer = null;
  let tickTimer = null;
  const glow = {}; // stage id -> until (ms)

  const now = () => Date.now();
  const fases = (data) => (data && Array.isArray(data.fases) ? data.fases : []);
  const snapshot = (phase) => Object.fromEntries((phase.evidence || []).map((e) => [e.path, [e.count, e.mtime]]));

  function changedEvidence(run, phase) {
    return (phase.evidence || []).filter((e) => {
      const [count, mtime] = run.baseline[e.path] || [0, 0];
      return e.count > count || e.mtime > mtime;
    });
  }

  function activity() {
    return typeof window.smithTerminalActivity === 'function' ? window.smithTerminalActivity() || {} : {};
  }

  function start(phase, command) {
    if (!phase || !phase.stage_id) return;
    const status = window.currentStatus || null;
    const term = activity();
    runs[phase.stage_id] = {
      stage: phase.stage_id,
      phaseId: phase.id,
      name: phase.name,
      command: String(command || ''),
      startedAt: now(),
      baseline: snapshot(phase),
      unlockedBefore: fases(status).filter((f) => f.unlocked).map((f) => f.stage_id),
      changed: [],
      status: phase.status || 'PENDING',
      startStatus: phase.status || 'PENDING',
      verifiedAt: 0,
      expiredAt: 0,
      unlocked: [],
      lastChangeAt: now(),
      stoppedAt: 0,
      sessionId: term.sessionId || null,
      agent: term.agent || '',
    };
    save();
    ensurePolling();
    refreshTracker(phase.stage_id);
    renderDock();
  }

  function onStatus(data) {
    const list = fases(data);
    let touched = false;
    for (const run of Object.values(runs)) {
      if (run.verifiedAt) continue;
      const phase = list.find((f) => f.stage_id === run.stage);
      // A run that was stopped or stopped being followed is still reconciled
      // with the server's verdict: when its phase passes later (another
      // session, a closed dashboard), it reads verified rather than stuck.
      if (!live(run)) {
        if (phase && phase.status === 'PASS' && run.startStatus !== 'PASS') {
          run.status = phase.status;
          run.verifiedAt = now();
          run.unlocked = [];
          touched = true;
        }
        continue;
      }
      if (!phase) continue;
      const changed = changedEvidence(run, phase).map((e) => ({ label: e.label, path: e.path, count: e.count }));
      if (JSON.stringify(changed) !== JSON.stringify(run.changed)) {
        run.changed = changed;
        run.lastChangeAt = now();
        touched = true;
      }
      if (phase.status !== run.status) { run.status = phase.status; touched = true; }
      // A phase that already passed is verified again only by new evidence.
      const fresh = run.startStatus !== 'PASS' || changed.length > 0;
      // The verdict is read before the quiet expiry, so a phase that passed
      // while nobody was watching is verified, never expired.
      if (phase.status !== 'PASS' && now() - run.lastChangeAt > QUIET_MS) {
        run.expiredAt = now(); touched = true; continue;
      }
      if (phase.status === 'PASS' && fresh) {
        run.verifiedAt = now();
        run.unlocked = list
          .filter((f) => f.unlocked && !run.unlockedBefore.includes(f.stage_id))
          .map((f) => ({ stage: f.stage_id, id: f.id, name: f.name }));
        for (const u of run.unlocked) glow[u.stage] = now() + UNLOCK_GLOW_MS;
        announce(run);
        touched = true;
      }
    }
    if (touched) save();
    for (const run of Object.values(runs)) refreshTracker(run.stage);
    renderDock();
    ensurePolling();
  }

  const live = (run) => Boolean(run && !run.verifiedAt && !run.expiredAt && !run.stoppedAt);

  function isRunning(stage) {
    return live(runs[stage]);
  }

  function anyRunning() {
    return Object.values(runs).some(live);
  }

  function ensurePolling() {
    if (anyRunning() && !fastTimer && typeof window.loadStatus === 'function') {
      fastTimer = setInterval(() => window.loadStatus(), FAST_POLL_MS);
    }
    if (!anyRunning() && fastTimer) { clearInterval(fastTimer); fastTimer = null; }
    if (anyRunning() && !tickTimer) {
      tickTimer = setInterval(() => {
        for (const r of Object.values(runs)) if (live(r)) { refreshTracker(r.stage); notifyIdle(r); }
        renderDock();
      }, 1000);
    }
    if (!anyRunning() && tickTimer) { clearInterval(tickTimer); tickTimer = null; }
  }

  function elapsed(ms) {
    const s = Math.max(0, Math.round(ms / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }

  // The run's session ended or was replaced (a new agent, ⟳, an exit).
  function sessionGone(run) {
    const act = activity();
    return Boolean(run.sessionId && act.sessionId !== run.sessionId);
  }

  function terminalWorking(run) {
    const act = activity();
    if (sessionGone(run)) {
      return { state: 'warn', gone: true,
        text: t('run.sessionGone') };
    }
    if (!act.lastOutputAt || act.lastOutputAt < run.startedAt) return { state: 'wait', text: t('run.waitingOutput') };
    const ago = now() - act.lastOutputAt;
    if (ago < 5000) return { state: 'run', text: t('run.working', { agent: esc(act.agent || t('run.agent')), s: Math.round(ago / 1000) }) };
    if (ago < IDLE_MS) return { state: 'run', text: t('run.workingLast', { agent: esc(act.agent || t('run.agent')), s: Math.round(ago / 1000) }) };
    return { state: 'warn', idle: true,
      text: t('run.idle', { time: elapsed(ago) }) };
  }

  function step(state, title, body) {
    const icon = { done: '✓', run: '●', wait: '○', warn: '!' }[state] || '○';
    return `<li class="run-step run-step--${state}"><span class="run-step__icon">${icon}</span>
        <div><strong>${title}</strong>${body ? `<div class="run-step__body">${body}</div>` : ''}</div></li>`;
  }

  // options.panel: the floating panel, which also offers the phase drawer.
  function renderTracker(phase, options) {
    const run = phase && runs[phase.stage_id];
    if (!run) return '';
    const panel = Boolean(options && options.panel);
    const verified = Boolean(run.verifiedAt);
    const stopped = !verified && Boolean(run.stoppedAt);
    const term = stopped ? { state: 'warn', text: t('run.interrupted') } : terminalWorking(run);
    const quiet = !verified && !stopped && Boolean(run.expiredAt);
    const quietMin = Math.round(QUIET_MS / 60000);
    const evidence = (phase.evidence || []).map((e) => {
      const hit = run.changed.some((c) => c.path === e.path);
      return `<li class="${hit ? 'is-new' : ''}">${hit ? '✓' : '·'} ${esc(e.label)} <code>${esc(e.path)}</code>${e.count ? ` · ${e.count}` : ''}</li>`;
    }).join('');
    const unlocked = run.unlocked.length
      ? run.unlocked.map((u) => `<strong>${esc(phaseName(u.id))}</strong> ${esc(u.name)}`).join(', ')
      : (verified ? t('run.noneBlocked') : t('run.unlocksWhenVerified'));
    const head = verified
      ? `<span class="badge badge--ok">${esc(t('run.verifiedIn', { time: elapsed(run.verifiedAt - run.startedAt) }))}</span>`
      : (stopped ? `<span class="badge badge--warn">${esc(t('run.stoppedAt', { time: elapsed(run.stoppedAt - run.startedAt) }))}</span>`
        : (quiet ? `<span class="badge badge--warn">${esc(t('run.quiet'))}</span>`
          : `<span class="badge badge--info">${esc(t('run.runningFor', { time: elapsed(now() - run.startedAt) }))}</span>`));
    const running = live(run);
    return `<div class="run-tracker${verified ? ' is-verified' : ''}" data-run-stage="${esc(run.stage)}">
        <div class="run-tracker__head">
          <strong>${panel ? esc(String(run.name || '').startsWith(run.phaseId) || String(run.name || '').startsWith(phaseName(run.phaseId)) ? run.name : `${phaseName(run.phaseId)} · ${run.name}`) : esc(t('run.tracking'))}</strong>${head}
        </div>
        <ol class="run-steps">
          ${step('done', esc(t('run.step.sent')), `<code>${esc(run.command)}</code>`)}
          ${step(verified ? 'done' : term.state, esc(t('run.step.working')),
              verified && term.state === 'wait' ? esc(t('run.stageDone')) : term.text)}
          ${step(run.changed.length ? 'done' : (verified ? 'done' : 'wait'), esc(t('run.step.artifacts')), `<ul class="run-evidence">${evidence}</ul>`)}
          ${step(verified ? 'done' : (quiet || stopped ? 'warn' : 'wait'), esc(t('run.step.verified')),
              esc(verified ? t('run.serverConfirmed')
                : (stopped ? t('run.stoppedState', { status: run.status })
                  : (quiet ? t('run.quietFor', { min: quietMin }) : t('run.currentState', { status: run.status })))))}
          ${step(run.unlocked.length ? 'done' : (verified ? 'done' : 'wait'), esc(t('run.step.next')), unlocked)}
        </ol>
        <div class="run-tracker__foot">
          ${running ? `<button class="btn btn--sm btn--danger" data-run-stop="${esc(run.stage)}" title="${esc(t('run.stopTitle'))}">${esc(t('run.stop'))}</button>` : ''}
          <button class="btn btn--sm" data-run-terminal="1" title="${esc(t('run.terminalTitle'))}">${esc(t('run.terminal'))}</button>
          ${running ? `<button class="btn btn--sm" data-run-verify="1" title="${esc(t('run.verifyTitle'))}">${esc(t('run.verify'))}</button>` : ''}
          ${panel ? `<button class="btn btn--sm" data-run-pipeline="${esc(run.stage)}">${esc(t('run.openInPipeline'))}</button>` : ''}
          <button class="btn btn--sm" data-run-dismiss="${esc(run.stage)}">${esc(verified ? t('run.closeTracking') : t('run.unfollow'))}</button>
        </div>
      </div>`;
  }

  // The phase as the last status shows it; the run alone when it is missing.
  function phaseOf(stage) {
    const run = runs[stage];
    return fases(window.currentStatus).find((f) => f.stage_id === stage)
      || (run ? { stage_id: stage, id: run.phaseId, name: run.name, evidence: [] } : null);
  }

  // force: redraw even under the pointer (after the operator's own click).
  function refreshTracker(stage, force) {
    const host = document.getElementById('phaseRunTracker');
    if (host && host.dataset.stage === stage) {
      const phase = fases(window.currentStatus).find((f) => f.stage_id === stage);
      if (phase) host.innerHTML = renderTracker(phase);
    }
    const panel = document.getElementById('phaseRunPanel');
    if (panel && !panel.hidden && panel.dataset.stage === stage) renderPanel(stage, force);
  }

  // The tracking panel: floats above the dock on whatever tab is open.
  function renderPanel(stage, force) {
    const panel = document.getElementById('phaseRunPanel');
    const phase = phaseOf(stage);
    if (!panel || !phase || !runs[stage]) { closePanel(); return; }
    // Same rule as the dock: never swap the buttons under the pointer.
    if (!force && panel.matches && panel.matches(':hover')) return;
    const dock = document.getElementById('phaseRunDock');
    if (panel.style) panel.style.bottom = `${(dock && !dock.hidden ? dock.offsetHeight : 0) + 24}px`;
    panel.innerHTML = `<button class="run-panel__close" data-run-panel-close="1" aria-label="${esc(t('run.closePanel'))}">✕</button>
      ${renderTracker(phase, { panel: true })}`;
  }

  function openPanel(stage) {
    if (!runs[stage] || typeof document === 'undefined' || !document.body) return;
    let panel = document.getElementById('phaseRunPanel');
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'phaseRunPanel';
      panel.className = 'run-panel';
      panel.setAttribute('role', 'dialog');
      panel.setAttribute('aria-label', t('run.panelLabel'));
      document.body.appendChild(panel);
    }
    panel.dataset.stage = stage;
    panel.hidden = false;
    renderPanel(stage, true);
  }

  function closePanel() {
    const panel = document.getElementById('phaseRunPanel');
    if (panel) panel.hidden = true;
  }

  // "Stop process": interrupts the agent's turn and stops following the
  // run. The session stays open; the phase is run again to resume it.
  async function stop(stage) {
    const run = runs[stage];
    if (!live(run)) return false;
    if (typeof window.confirm === 'function'
      && !window.confirm(t('run.confirmStop', { phase: phaseName(run.phaseId) }))) return false;
    let sent = false;
    try {
      sent = typeof window.smithTerminalInterrupt === 'function' && !sessionGone(run)
        ? await window.smithTerminalInterrupt() : false;
    } catch (err) {
      // The agent may still be working: keep following the run.
      toast(t('run.interruptFailed', { phase: phaseName(run.phaseId), error: err.message }), 'warn');
      return false;
    }
    run.stoppedAt = now();
    save();
    ensurePolling();
    refreshTracker(stage, true);
    renderDock();
    toast(sent ? t('run.stoppedToast', { phase: phaseName(run.phaseId) })
      : t('run.unfollowedToast', { phase: phaseName(run.phaseId) }), 'warn');
    return true;
  }

  // The floating dock (bottom-left): every followed run, on any tab.
  function renderDock() {
    if (typeof document === 'undefined' || !document.body) return;
    let dock = document.getElementById('phaseRunDock');
    const recent = (at) => at && now() - at < 60000;
    const shown = Object.values(runs).filter((r) => live(r) || recent(r.verifiedAt) || recent(r.stoppedAt));
    if (!shown.length) { if (dock) dock.hidden = true; return; }
    if (!dock) {
      dock = document.createElement('div');
      dock.id = 'phaseRunDock';
      dock.className = 'run-dock';
      dock.setAttribute('role', 'status');
      document.body.appendChild(dock);
    }
    dock.hidden = false;
    const times = {};
    const markup = (withTimes) => shown.map((r) => {
      const term = terminalWorking(r);
      const state = esc(r.verifiedAt ? t('run.badge.verified') : (r.stoppedAt ? t('run.badge.stopped')
        : (term.gone ? t('run.badge.noSession') : (term.idle ? t('run.badge.waiting') : t('run.badge.running')))));
      times[r.stage] = elapsed((r.verifiedAt || r.stoppedAt || now()) - r.startedAt);
      const steps = [true, r.verifiedAt || term.state !== 'wait', r.changed.length > 0 || r.verifiedAt, r.verifiedAt, r.verifiedAt]
        .map((on) => `<i class="${on ? 'on' : ''}"></i>`).join('');
      return `<button class="run-dock__item${r.verifiedAt ? ' is-verified' : ''}" data-run-open="${esc(r.stage)}" title="${esc(t('run.viewProgress', { phase: phaseName(r.phaseId) }))}">
          <strong>${esc(phaseName(r.phaseId))}</strong><span>${state} · <span data-run-time="${esc(r.stage)}">${withTimes ? times[r.stage] : ''}</span></span><span class="run-dock__steps">${steps}</span>
        </button>`;
    }).join('');
    // The 1 s tick only moves the clocks: when nothing else changed, the
    // times are written in place instead of rebuilding every button.
    const shape = markup(false);
    if (shape === dock.dataset.shape) {
      for (const node of dock.querySelectorAll('[data-run-time]')) {
        const time = times[node.dataset.runTime];
        if (time !== undefined && node.textContent !== time) node.textContent = time;
      }
      return;
    }
    // Never swap the buttons under the pointer: a click split across the old
    // and new button would land on the dock and be lost.
    if (dock.matches && dock.matches(':hover')) return;
    dock.innerHTML = markup(true);
    dock.dataset.shape = shape;
  }

  function notifyIdle(run) {
    if (run.verifiedAt) return;
    const idle = Boolean(terminalWorking(run).idle);
    // Output resumed: a later pause gets its own notice.
    if (!idle) { if (run.idleNotified) { run.idleNotified = false; save(); } return; }
    if (run.idleNotified) return;
    run.idleNotified = true;
    save();
    toast(t('run.idleToast', { phase: phaseName(run.phaseId) }), 'warn');
  }

  function cardBadge(stage) {
    const run = runs[stage];
    if (!run) return '';
    if (run.verifiedAt) return `<span class="badge badge--ok">${esc(t('run.badge.verified'))}</span>`;
    if (run.stoppedAt) return `<span class="badge badge--warn">${esc(t('run.badge.stopped'))}</span>`;
    if (run.expiredAt) return `<span class="badge badge--warn">${esc(t('run.badge.unchanged'))}</span>`;
    return `<span class="badge badge--info run-pulse">${esc(t('run.badge.running'))}</span>`;
  }

  function justUnlocked(stage) {
    return (glow[stage] || 0) > now();
  }

  function dismiss(stage) {
    delete runs[stage];
    save();
    ensurePolling();
    const host = document.getElementById('phaseRunTracker');
    if (host && host.dataset.stage === stage) host.innerHTML = '';
    const panel = document.getElementById('phaseRunPanel');
    if (panel && panel.dataset.stage === stage) closePanel();
  }

  function announce(run) {
    const names = run.unlocked.map((u) => phaseName(u.id)).join(', ');
    toast(names ? t('run.verifiedToastUnlocked', { phase: phaseName(run.phaseId), names })
      : t('run.verifiedToast', { phase: phaseName(run.phaseId) }), 'ok');
  }

  function toast(text, tone) {
    let toast = document.getElementById('phaseToast');
    if (!toast && document.body) {
      toast = document.createElement('div');
      toast.id = 'phaseToast';
      toast.className = 'phase-toast';
      toast.setAttribute('role', 'status');
      document.body.appendChild(toast);
    }
    if (!toast) return;
    toast.textContent = text;
    toast.dataset.tone = tone || 'ok';
    toast.classList.add('is-visible');
    setTimeout(() => toast.classList.remove('is-visible'), 8000);
  }

  // Capture phase: the phase drawer stops click propagation
  // (onclick="event.stopPropagation()"), so a bubbling listener never fires.
  document.addEventListener('click', (event) => {
    const verify = event.target.closest && event.target.closest('[data-run-verify]');
    // Re-reads the status only: no audit, compile or other side effect.
    if (verify && typeof window.loadStatus === 'function') {
      window.loadStatus();
      return;
    }
    const find = (attr) => event.target.closest && event.target.closest(`[${attr}]`);
    const close = find('data-run-dismiss');
    if (close) { dismiss(close.dataset.runDismiss); renderDock(); return; }
    const halt = find('data-run-stop');
    if (halt) { stop(halt.dataset.runStop); return; }
    if (find('data-run-terminal')) {
      if (typeof window.openCliConsole === 'function') window.openCliConsole();
      return;
    }
    if (find('data-run-panel-close')) { closePanel(); return; }
    // The dock opens the run's panel on the current tab.
    const open = find('data-run-open');
    if (open) { openPanel(open.dataset.runOpen); return; }
    // The panel can still take the operator to the phase drawer.
    const drawer = find('data-run-pipeline');
    if (drawer && typeof window.openDrawer === 'function') {
      const index = fases(window.currentStatus).findIndex((f) => f.stage_id === drawer.dataset.runPipeline);
      if (index >= 0) {
        closePanel();
        if (typeof window.navigateTab === 'function') window.navigateTab('pipeline');
        window.openDrawer(index);
      }
    }
  }, true);

  window.phaseRuns = { start, onStatus, renderTracker, cardBadge, isRunning, anyRunning, dismiss, justUnlocked,
    renderDock, openPanel, stop };
  ensurePolling();
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('DOMContentLoaded', renderDock);
    // Redraw the dock and any open tracker in the new language.
    document.addEventListener('languagechange', () => {
      const dock = document.getElementById('phaseRunDock');
      if (dock) dock.dataset.shape = '';
      for (const run of Object.values(runs)) refreshTracker(run.stage, true);
      renderDock();
    });
  }
})();
