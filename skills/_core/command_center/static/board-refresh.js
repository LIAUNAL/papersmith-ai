// "Update board": the topbar button regenerates every derived artifact the
// board shows (POST /api/board/refresh: the SOTA atlas, the manuscript layer
// and graph, the novelty graph, the wiring health), re-reads the status and
// tells the operator where the project stands: the current phase, its missing
// steps, the phases still locked and the open or failed gates.
//
// `smith ui` runs the same refresh once when the server starts; on load this
// script reads GET /api/board/summary and reports that start-up refresh once
// per server run (or waits for it while it is still running).
//
// Public surface: window.boardRefresh = { run, message, render, showStartup }
// and the global refreshBoard() the button calls.
(function () {
  'use strict';

  const PANEL_ID = 'boardStatus';
  const BUTTON_ID = 'boardRefreshBtn';
  const SEEN_KEY = 'papersmith-board-refresh-seen';
  const MAX_MISSING = 6;
  const POLL_MS = 3000;
  const MAX_POLLS = 100;

  const t = (key, vars) => (typeof window.t === 'function' ? window.t(key, vars) : key);

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  const STATUS_LABELS = {
    PASS: () => t('board.status.PASS'), ACTIVE: () => t('board.status.ACTIVE'),
    PENDING: () => t('board.status.PENDING'), LOCKED: () => t('board.status.LOCKED'),
    FAIL: () => t('board.status.FAIL'),
  };

  function statusLabel(status) {
    return STATUS_LABELS[status] ? STATUS_LABELS[status]() : status;
  }

  // Literal keys, so the catalogue test can see each one.
  const ARTIFACT_LABELS = {
    ideas: () => t('board.artifact.ideas'),
    atlas: () => t('board.artifact.atlas'),
    atlas_manuscript: () => t('board.artifact.atlas_manuscript'),
    manuscript_graph: () => t('board.artifact.manuscript_graph'),
    novelty_graph: () => t('board.artifact.novelty_graph'),
    health: () => t('board.artifact.health'),
  };

  function artifactLabel(id) {
    return ARTIFACT_LABELS[id] ? ARTIFACT_LABELS[id]() : id;
  }

  function names(list) {
    return list.map((item) => item.name ? `${item.id} · ${item.name}` : item.id).join(', ');
  }

  // The message for a refresh result (or a bare { summary }): a tone and its
  // HTML lines. Pure, so it is testable without a DOM.
  function message(result, origin) {
    const summary = (result && result.summary) || {};
    const artifacts = (result && result.artifacts) || [];
    const tone = summary.tone || 'info';
    const current = summary.current;
    const phase = current ? current.name : '';
    const headline = tone === 'done' ? t('board.headline.done')
      : tone === 'alert' ? t('board.headline.alert')
        : tone === 'warn' ? t('board.headline.warn', { phase })
          : t('board.headline.info', { phase });
    const lines = [];
    lines.push(t('board.progress', {
      done: summary.phases_completed || 0, total: summary.phases_total || 0,
      gates: summary.gates_passed || 0, gatesTotal: summary.gates_total || 0,
    }));
    if (current) {
      lines.push(t('board.phaseStatus', { phase: current.name, status: statusLabel(current.status) })
        + (current.detail ? ` — ${current.detail}` : ''));
      if (current.blocked_by) {
        lines.push(t('board.lockedBy', { phase: current.name, by: current.blocked_by }));
      }
    }
    const missing = summary.missing || [];
    const missingItems = missing.slice(0, MAX_MISSING).map((step) =>
      `<li><strong>${esc(step.id)}</strong> ${esc(step.name)} <em>(${esc(statusLabel(step.status))})</em>`
      + (step.detail ? ` — ${esc(step.detail)}` : '') + '</li>');
    if (missing.length > MAX_MISSING) {
      missingItems.push(`<li>${esc(t('board.moreSteps', { count: missing.length - MAX_MISSING }))}</li>`);
    }
    if (current && current.cli_command) lines.push(t('board.nextCommand', { command: current.cli_command }));
    if ((summary.failed_gates || []).length) lines.push(t('board.failedGates', { gates: names(summary.failed_gates) }));
    if ((summary.open_gates || []).length) lines.push(t('board.openGates', { gates: names(summary.open_gates) }));
    const ideas = summary.ideas;
    if (ideas && ideas.revision) {
      const count = (list) => (Array.isArray(list) ? list.length : 0);
      lines.push(t('board.ideasSynced', {
        revision: ideas.revision, added: count(ideas.added), pruned: count(ideas.pruned),
        changed: count(ideas.changed),
      }));
      if (count(ideas.pruned)) lines.push(t('board.ideasRetired', { list: ideas.pruned.join(', ') }));
      if (ideas.contribution_type_stale) lines.push(t('board.contributionTypeStale'));
    }
    const by = (state) => artifacts.filter((a) => a.state === state).map((a) => artifactLabel(a.id));
    const ok = by('ok'), skipped = by('skipped'), failed = by('failed');
    if (ok.length) lines.push(t('board.artifactsOk', { list: ok.join(', ') }));
    if (skipped.length) lines.push(t('board.artifactsSkipped', { list: skipped.join(', ') }));
    if (failed.length) {
      const details = artifacts.filter((a) => a.state === 'failed')
        .map((a) => `${artifactLabel(a.id)}: ${a.detail}`).join('; ');
      lines.push(t('board.artifactsFailed', { list: details }));
    }
    const when = origin === 'startup' ? t('board.originStartup')
      : origin === 'summary' ? t('board.originSummary')
        : t('board.originManual', { time: new Date().toLocaleTimeString() });
    const html = `<div class="board-status__head"><strong class="board-status__title">${esc(headline)}</strong>`
      + `<span class="board-status__when">${esc(when)}</span>`
      + `<button type="button" class="board-status__close" data-board-close aria-label="${esc(t('board.close'))}" title="${esc(t('board.close'))}">✕</button></div>`
      + `<ul class="board-status__lines">${lines.map((line) => `<li>${esc(line)}</li>`).join('')}</ul>`
      + (missingItems.length ? `<p class="board-status__sub">${esc(t('board.missingTitle'))}</p><ul class="board-status__missing">${missingItems.join('')}</ul>` : '');
    return { tone, html };
  }

  function panel() {
    return document.getElementById(PANEL_ID);
  }

  function render(result, origin) {
    const box = panel();
    if (!box) return;
    const { tone, html } = message(result, origin);
    box.dataset.tone = tone;
    box.innerHTML = html;
    box.hidden = false;
  }

  function notice(text, tone) {
    const box = panel();
    if (!box) return;
    box.dataset.tone = tone || 'info';
    box.innerHTML = `<div class="board-status__head"><strong class="board-status__title">${esc(text)}</strong>`
      + `<button type="button" class="board-status__close" data-board-close aria-label="${esc(t('board.close'))}" title="${esc(t('board.close'))}">✕</button></div>`;
    box.hidden = false;
  }

  function reloadViews() {
    if (typeof window.reloadBoardViews === 'function') window.reloadBoardViews();
    else if (typeof window.loadStatus === 'function') window.loadStatus();
  }

  async function run() {
    const btn = document.getElementById(BUTTON_ID);
    const label = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = t('board.refreshing'); }
    notice(t('board.refreshingNotice'), 'info');
    try {
      const res = await fetch('/api/board/refresh', { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (res.status === 409) {
        notice(t('board.busy'), 'warn');
      } else if (res.status === 403 && data && data.error === 'STATIC_SNAPSHOT') {
        notice(t('board.snapshot'), 'warn');
      } else if (!res.ok || !data.ok) {
        notice(t('board.error', { error: (data && data.detail) || res.status }), 'alert');
      } else {
        render(data, 'manual');
        markSeen(data);
      }
    } catch (err) {
      notice(t('board.error', { error: err.message }), 'alert');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = label || t('board.refreshButton'); }
      reloadViews();
    }
  }

  function seen(result) {
    try {
      return Boolean(result && result.finished_at)
        && window.sessionStorage.getItem(SEEN_KEY) === result.finished_at;
    } catch (_) {
      return false;
    }
  }

  function markSeen(result) {
    try {
      if (result && result.finished_at) window.sessionStorage.setItem(SEEN_KEY, result.finished_at);
    } catch (_) { /* storage blocked: the report may show again */ }
  }

  // On load: report the start-up refresh once per server run; while it is
  // still running, say so and wait for it.
  async function showStartup(polls) {
    polls = polls || 0;
    let data;
    try {
      const res = await fetch('/api/board/summary');
      if (!res.ok) return;
      data = await res.json();
    } catch (_) {
      return;
    }
    if (data.last_refresh) {
      if (!seen(data.last_refresh)) {
        render(data.last_refresh, 'startup');
        markSeen(data.last_refresh);
        reloadViews();
      }
      return;
    }
    if (data.refreshing && polls < MAX_POLLS) {
      if (!polls) notice(t('board.startupRefreshing'), 'info');
      setTimeout(() => showStartup(polls + 1), POLL_MS);
      return;
    }
    if (polls) render({ summary: data.summary }, 'summary');
  }

  document.addEventListener('click', (event) => {
    const close = event.target && event.target.closest && event.target.closest('[data-board-close]');
    if (close) {
      const box = panel();
      if (box) box.hidden = true;
    }
  });

  window.boardRefresh = { run, message, render, showStartup };
  window.refreshBoard = run;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => showStartup(0));
  } else {
    showStartup(0);
  }
})();
