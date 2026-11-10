/* Agents Office: a measured, spatial view of the smith agents at work.
 *
 * Spec S2/S3 of odd/tasks/agents-office-panel.md. Inspired by Weherd's 3D
 * office, rebuilt as a vanilla 2.5D canvas so the dashboard ships no 3D
 * library and no new dependency: floor, the orchestrator's desk, one desk
 * per smith agent, and a grand-brain memory area for Engram. Everything
 * drawn comes from GET /api/office/state (roster, live sessions, observed
 * Engram interactions) plus the phase runs this browser already tracks in
 * localStorage. The panel is read-only: clicking a desk opens a card with
 * the agent's role, model and current task, and can open the existing CLI
 * console on that agent — it never closes, interrupts or writes to a
 * session (Weherd's shotgun is deliberately excluded).
 *
 * Honest states: a disabled terminal or an unauthorized page says so instead
 * of drawing fiction; a model nobody measured shows as "not measured".
 *
 * Public surface (window): officeWake().
 */
(function () {
  'use strict';

  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);

  const state = { info: null, error: null, card: null };
  const DESK_W = 128, DESK_H = 74;
  const COLORS = {
    floor: 'rgba(148,163,184,0.14)', desk: '#111827', deskEdge: '#374151',
    working: '#34d399', idle: '#9ca3af', off: '#4b5563', text: '#e5e7eb',
    dim: '#9ca3af', line: '#38bdf8', brain: '#a78bfa', brainGlow: 'rgba(167,139,250,',
  };

  // ---- data --------------------------------------------------------------
  function phaseRunsStore() {
    try {
      const host = (typeof location !== 'undefined' && location.host) || 'local';
      return JSON.parse(localStorage.getItem(`smith_phase_runs@${host}`) || '{}') || {};
    } catch (_) {
      return {};
    }
  }

  function activeRunFor(agentId) {
    const runs = Object.values(phaseRunsStore());
    const live = runs.filter((r) => r && r.agent === agentId && !r.stoppedAt);
    if (!live.length) return null;
    return live.sort((a, b) => (b.startedAt || 0) - (a.startedAt || 0))[0];
  }

  function statusOf(agent) {
    if (agent.session && agent.session.alive) return 'working';
    if (!agent.available) return 'off';
    return 'idle';
  }

  async function refresh() {
    try {
      const res = await fetch('/api/office/state');
      state.info = res.ok ? await res.json() : null;
      state.error = res.ok ? null : `HTTP ${res.status}`;
    } catch (error) {
      state.error = String(error);
    }
  }

  // ---- geometry ----------------------------------------------------------
  function layout(width, height) {
    const info = state.info || {};
    const agents = info.agents || [];
    const spots = [{ x: width / 2, y: height * 0.16 }];
    const cols = Math.min(agents.length, 4);
    const rows = Math.ceil(agents.length / cols) || 1;
    agents.forEach((agent, i) => {
      const row = Math.floor(i / cols);
      const inRow = Math.min(agents.length - row * cols, cols);
      const col = i % cols;
      const y = height * (0.40 + 0.26 * (rows > 1 ? row : 0.5));
      const x = width * ((col + 1) / (inRow + 1));
      spots.push({ x, y });
    });
    return {
      orchestrator: { x: width / 2, y: height * 0.14 },
      desks: spots.slice(1),
      brain: { x: width * 0.82, y: height * 0.88, r: Math.min(64, height * 0.11) },
    };
  }

  function deskBox(spot) {
    return { x: spot.x - DESK_W / 2, y: spot.y - DESK_H / 2, w: DESK_W, h: DESK_H };
  }

  // ---- drawing -----------------------------------------------------------
  function roundRect(ctx, box, r) {
    ctx.beginPath();
    ctx.moveTo(box.x + r, box.y);
    ctx.arcTo(box.x + box.w, box.y, box.x + box.w, box.y + box.h, r);
    ctx.arcTo(box.x + box.w, box.y + box.h, box.x, box.y + box.h, r);
    ctx.arcTo(box.x, box.y + box.h, box.x, box.y, r);
    ctx.arcTo(box.x, box.y, box.x + box.w, box.y, r);
    ctx.closePath();
  }

  function truncate(ctx, text, maxWidth) {
    if (ctx.measureText(text).width <= maxWidth) return text;
    while (text.length > 1 && ctx.measureText(`${text}…`).width > maxWidth) text = text.slice(0, -1);
    return `${text}…`;
  }

  function drawFloor(ctx, width, height) {
    ctx.strokeStyle = COLORS.floor;
    ctx.lineWidth = 1;
    const step = 56;
    for (let x = -height; x < width + height; x += step) {
      ctx.beginPath();
      ctx.moveTo(x, height);
      ctx.lineTo(x + height * 0.5, 0);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x + height * 0.5, height);
      ctx.stroke();
    }
  }

  function drawDesk(ctx, spot, agent, ts) {
    const box = deskBox(spot);
    const status = statusOf(agent);
    const color = status === 'working' ? COLORS.working : (status === 'idle' ? COLORS.idle : COLORS.off);
    const pulse = status === 'working' ? 0.5 + 0.5 * Math.cos(ts / 400) : 0;
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    roundRect(ctx, { x: box.x + 4, y: box.y + 5, w: box.w, h: box.h }, 10);
    ctx.fill();
    ctx.fillStyle = COLORS.desk;
    ctx.strokeStyle = color;
    ctx.lineWidth = status === 'working' ? 2 + pulse : 1.5;
    roundRect(ctx, box, 10);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = COLORS.text;
    ctx.font = '600 13px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(truncate(ctx, agent.label, box.w - 14), box.x + box.w / 2, box.y + 19);
    ctx.font = '11px system-ui, sans-serif';
    ctx.fillStyle = COLORS.dim;
    ctx.fillText(truncate(ctx, agent.role || agent.id, box.w - 12), box.x + box.w / 2, box.y + 34);
    ctx.fillText(t('office.model') + ': ' + (agent.model == null ? t('office.modelUnknown') : agent.model),
      box.x + box.w / 2, box.y + 48);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(box.x + 12, box.y + box.h - 12, 4 + (status === 'working' ? pulse : 0), 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = COLORS.dim;
    ctx.font = '10px system-ui, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(t(`office.${status}`), box.x + 20, box.y + box.h - 9);
    ctx.restore();
  }

  function drawFlowLine(ctx, from, to, color, ts, active) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.globalAlpha = active ? 0.8 : 0.15;
    ctx.lineWidth = active ? 1.6 : 1;
    if (active) ctx.setLineDash([6, 8]);
    ctx.lineDashOffset = -ts / 40;
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.quadraticCurveTo((from.x + to.x) / 2, (from.y + to.y) / 2 + 30, to.x, to.y);
    ctx.stroke();
    ctx.restore();
  }

  function drawBrain(ctx, brain, ts) {
    const interactions = ((state.info || {}).memory || {}).interactions || [];
    const last = interactions[interactions.length - 1];
    const recent = last && (Date.now() / 1000 - (last.at || 0)) < 120;
    const glow = recent ? 0.35 + 0.2 * Math.cos(ts / 300) : 0.12;
    ctx.save();
    ctx.fillStyle = COLORS.brainGlow + glow + ')';
    ctx.beginPath();
    ctx.arc(brain.x, brain.y, brain.r * (recent ? 1.12 : 1), 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = COLORS.brain;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(brain.x, brain.y, brain.r, 0, Math.PI * 2);
    ctx.stroke();
    for (let i = 0; i < 8; i++) {
      const angle = (i / 8) * Math.PI * 2 + ts / 4000;
      ctx.fillStyle = COLORS.brain;
      ctx.beginPath();
      ctx.arc(brain.x + Math.cos(angle) * brain.r * 0.5,
        brain.y + Math.cos(angle - Math.PI / 2) * brain.r * 0.5, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.fillStyle = COLORS.text;
    ctx.font = '600 12px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(t('office.brain'), brain.x, brain.y + brain.r + 16);
    ctx.font = '10px system-ui, sans-serif';
    ctx.fillStyle = COLORS.dim;
    const line = recent && last ? t('office.brainLast', { line: truncate(ctx, last.line || '', 40) })
      : t('office.brainEmpty');
    ctx.fillText(line, brain.x, brain.y + brain.r + 30);
    ctx.restore();
    return recent;
  }

  function drawStatusLine(ctx, width) {
    const info = state.info;
    ctx.save();
    ctx.font = '12px system-ui, sans-serif';
    ctx.textAlign = 'left';
    if (state.error && !info) {
      ctx.fillStyle = '#f87171';
      ctx.fillText(`${t('office.error')}: ${state.error}`, 12, 20);
      ctx.restore();
      return;
    }
    if (!info) {
      ctx.fillStyle = COLORS.dim;
      ctx.fillText(t('office.loading'), 12, 20);
      ctx.restore();
      return;
    }
    if (!info.enabled) {
      ctx.fillStyle = '#fbbf24';
      ctx.fillText(t('office.disabled'), 12, 20);
      ctx.restore();
      return;
    }
    if (!info.authorized) {
      ctx.fillStyle = '#fbbf24';
      ctx.fillText(t('office.unauthorized'), 12, 20);
      ctx.restore();
      return;
    }
    const working = (info.agents || []).filter((a) => statusOf(a) === 'working').length;
    ctx.fillStyle = COLORS.dim;
    ctx.fillText(t('office.status', {
      working, total: (info.agents || []).length,
      memories: ((info.memory || {}).interactions || []).length,
    }), 12, 20);
    ctx.restore();
  }

  function draw(ts) {
    const canvas = document.getElementById('officeCanvas');
    const pane = document.getElementById('pane-office');
    if (!canvas || !pane || !pane.classList.contains('active')) return;
    const width = canvas.clientWidth, height = canvas.clientHeight;
    if (!width || !height) return;
    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr;
      canvas.height = height * dpr;
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    drawFloor(ctx, width, height);
    const geo = layout(width, height);
    const info = state.info || {};
    const agents = info.agents || [];
    const anyWorking = agents.some((a) => statusOf(a) === 'working');
    drawDesk(ctx, geo.orchestrator, {
      label: t('office.orchestrator'), role: 'smith',
      model: null, available: info.authorized, session: anyWorking ? { alive: true } : null,
    }, ts);
    agents.forEach((agent, i) => {
      const spot = geo.desks[i];
      if (!spot) return;
      drawFlowLine(ctx, geo.orchestrator, spot, COLORS.line, ts, statusOf(agent) === 'working');
    });
    agents.forEach((agent, i) => {
      const spot = geo.desks[i];
      if (spot) drawDesk(ctx, spot, agent, ts);
    });
    const brainActive = drawBrain(ctx, geo.brain, ts);
    drawFlowLine(ctx, geo.orchestrator, { x: geo.brain.x, y: geo.brain.y - geo.brain.r },
      COLORS.brain, ts, brainActive);
    drawStatusLine(ctx, width);
  }

  // ---- interaction -------------------------------------------------------
  function showCard(agent, spot) {
    state.card = agent.id;
    const host = document.getElementById('officeCardHost');
    if (!host) return;
    const run = activeRunFor(agent.id);
    const task = run
      ? t('office.phaseTask', { phase: run.name || run.stage || '', command: run.command || '' })
      : (agent.session && agent.session.alive ? t('office.sessionTask') : t('office.noTask'));
    const status = statusOf(agent);
    host.innerHTML = `<div class="office-card" role="dialog" aria-label="${esc(agent.label)}">
        <button type="button" class="office-card__close" aria-label="${esc(t('office.close'))}"
          onclick="document.getElementById('officeCardHost').innerHTML='';">✕</button>
        <h4>${esc(agent.label)} <span class="office-card__status office-card__status--${status}">${esc(t(`office.${status}`))}</span></h4>
        <p><strong>${esc(t('office.role'))}:</strong> ${esc(agent.role || agent.id)}</p>
        <p><strong>${esc(t('office.model'))}:</strong> ${agent.model == null ? esc(t('office.modelUnknown')) : esc(agent.model)}</p>
        <p><strong>${esc(t('office.task'))}:</strong> ${esc(task)}</p>
        ${agent.available
          ? `<button type="button" class="office-card__open" data-office-open="${esc(agent.id)}">${esc(t('office.openConsole'))}</button>`
          : ''}
      </div>`;
    host.style.left = `${Math.max(8, spot.x - 140)}px`;
    host.style.top = `${Math.max(8, spot.y + DESK_H)}px`;
    host.querySelectorAll('[data-office-open]').forEach((btn) => {
      btn.addEventListener('click', () => openConsoleOn(btn.getAttribute('data-office-open')));
    });
  }

  function openConsoleOn(agentId) {
    const select = document.getElementById('terminalAgentSelect');
    if (select && select.value !== agentId) {
      select.value = agentId;
      select.dispatchEvent(new Event('change'));
    }
    if (typeof window.openCliConsole === 'function') window.openCliConsole();
  }

  function onCanvasClick(event) {
    const canvas = document.getElementById('officeCanvas');
    if (!canvas || !(state.info || {}).authorized) return;
    const rect = canvas.getBoundingClientRect();
    const mx = event.clientX - rect.left, my = event.clientY - rect.top;
    const geo = layout(rect.width, rect.height);
    const agents = (state.info || {}).agents || [];
    for (let i = 0; i < agents.length; i++) {
      const spot = geo.desks[i];
      if (!spot) continue;
      const box = deskBox(spot);
      if (mx >= box.x && mx <= box.x + box.w && my >= box.y && my <= box.y + box.h) {
        showCard(agents[i], spot);
        return;
      }
    }
  }

  // ---- lifecycle ---------------------------------------------------------
  function startLoop() {
    const tick = (ts) => {
      draw(ts);
      window.requestAnimationFrame(tick);
    };
    window.requestAnimationFrame(tick);
  }

  function pollWhileActive() {
    const pane = document.getElementById('pane-office');
    if (pane && pane.classList.contains('active')
      && document.visibilityState === 'visible') {
      refresh();
    }
  }

  window.officeWake = () => {
    refresh();
    const host = document.getElementById('officeCardHost');
    if (host) host.innerHTML = '';
    state.card = null;
  };

  document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('officeCanvas');
    if (!canvas) return;
    canvas.addEventListener('click', onCanvasClick);
    startLoop();
    refresh();
    window.setInterval(pollWhileActive, 2000);
  });
})();
