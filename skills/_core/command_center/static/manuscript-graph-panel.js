/**
 * manuscript-graph-panel.js: the manuscript summary diagram of the Novelty &
 * Findings tab.
 *
 * The graph itself is drawn by GET /api/atlas/manuscript-graph/view (offline
 * HTML in its own iframe: topic | problem and pillars | hypotheses | SOTA |
 * base and novelty math | experiments | findings | conclusions). This file
 * keeps the badge above it current: it polls
 * GET /api/atlas/manuscript-graph while the tab is shown, reloads the iframe
 * when the stored graph changes, flags a stale graph, and rebuilds it on
 * demand through POST /api/atlas/manuscript-graph/build. Offline: no CDN.
 */
(function () {
  'use strict';

  const t = (key, vars) => (typeof window.t === 'function' ? window.t(key, vars) : key);
  const withLang = (url) => (window.i18n ? window.i18n.withLanguage(url) : url);
  const VIEW = '/api/atlas/manuscript-graph/view';
  let active = false;
  let lastDigest = null;

  function badge(text, tone) {
    const el = document.getElementById('manuscriptSummaryBadge');
    if (!el) return;
    el.style.color = tone === 'ok' ? 'var(--ok)' : (tone === 'bad' ? 'var(--bad)' : 'var(--text-muted)');
    el.textContent = text;
  }

  function iframe() {
    return document.getElementById('manuscriptSummaryIframe');
  }

  function reloadView() {
    const frame = iframe();
    if (frame) frame.src = withLang(`${VIEW}?v=${Date.now()}`);
  }

  function describe(body) {
    if (!body || body.status !== 'ok' || !body.graph) {
      badge(t(body && body.status === 'invalid' ? 'atlas.summary.invalid' : 'atlas.summary.absent'), 'muted');
      return;
    }
    const missing = (body.graph.summary && body.graph.summary.missing) || [];
    const text = missing.length
      ? t('atlas.summary.missing', { kinds: missing.join(', ') })
      : t('atlas.summary.complete');
    badge(body.stale ? `${text} · ${t('atlas.summary.stale')}` : text, body.stale ? 'bad' : 'ok');
  }

  async function poll() {
    if (!active) return;
    try {
      const res = await fetch('/api/atlas/manuscript-graph');
      const body = await res.json();
      const digest = JSON.stringify(body.graph ? body.graph.generated_from : null) + String(body.stale);
      if (lastDigest !== null && digest !== lastDigest) reloadView();
      lastDigest = digest;
      describe(body);
    } catch (err) {
      badge(t('atlas.summary.absent'), 'muted');
    }
  }

  function showManuscriptGraph() {
    active = true;
    lastDigest = null;
    const frame = iframe();
    if (frame && new URL(frame.src, window.location.href).pathname !== VIEW) frame.src = withLang(VIEW);
    poll();
  }

  function hideManuscriptGraph() {
    active = false;
  }

  // Shows the diagram from another tab, as the cited-papers explorer does.
  function openManuscriptSummary() {
    if (typeof window.navigateTab === 'function') window.navigateTab('novelty');
    else showManuscriptGraph();
  }

  async function rebuildManuscriptGraph() {
    badge(t('atlas.summary.rebuilding'), 'muted');
    try {
      const res = await fetch('/api/atlas/manuscript-graph/build', { method: 'POST' });
      const data = await res.json();
      if (!data.ok) {
        badge(t('atlas.summary.rebuildFailed', { detail: data.detail || data.status || '' }), 'bad');
        return;
      }
      lastDigest = null;
      reloadView();
      await poll();
    } catch (err) {
      badge(t('atlas.summary.rebuildFailed', { detail: err.message }), 'bad');
    }
  }

  // The view's labels are English with a data-i18n key each; the iframe is
  // same-origin, so the dashboard's catalogue translates them in place.
  function translateView() {
    const frame = iframe();
    if (!active || !frame) return;
    let doc;
    try { doc = frame.contentDocument; } catch (_) { return; }
    if (!doc || !doc.getElementById('graph-data')) return;
    doc.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      const text = t(key);
      if (text && text !== key) el.textContent = text;
    });
    frame.contentWindow.MG_LABELS = {
      source: t('atlas.summaryView.source'), blocks: t('atlas.summaryView.blocks'),
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    const frame = iframe();
    if (frame) frame.addEventListener('load', translateView);
  });

  // The graph is rewritten by commands outside the page; poll while it is shown.
  setInterval(() => {
    if (active && !document.hidden) poll();
  }, 5000);
  document.addEventListener('languagechange', () => {
    if (active) reloadView();
  });

  window.showManuscriptGraph = showManuscriptGraph;
  window.hideManuscriptGraph = hideManuscriptGraph;
  window.rebuildManuscriptGraph = rebuildManuscriptGraph;
  window.openManuscriptSummary = openManuscriptSummary;
  window.manuscriptSummaryShown = () => active;
})();
