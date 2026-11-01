/**
 * atlas-manuscript-panel.js: the manuscript layer of the SOTA atlas.
 *
 * Reads GET /api/atlas/manuscript (sota-pool/atlas.manuscript.json: which
 * atlas systems the paper cites, with their citing blocks and claims, and the
 * cited papers outside the pool) and lists it under the atlas view. The layer
 * is rebuilt by `bib build`, `verify` and a successful compile; the
 * "Rebuild" button posts /api/atlas/manuscript/build. Offline: no CDN.
 */
(function () {
  'use strict';

  const t = (key, vars) => (typeof window.t === 'function' ? window.t(key, vars) : key);
  const esc = (text) => String(text === null || text === undefined ? '' : text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  let open = false;
  let lastBody = null;

  function panel() {
    return document.getElementById('atlasManuscriptPanel');
  }

  function claimsHtml(claims) {
    if (!claims || !claims.length) return '';
    return '<ul style="margin: 0.2rem 0 0 1rem; padding: 0;">' + claims.map((c) =>
      `<li><code>${esc(c.block)}</code> · <code>${esc(c.cite_key)}</code> · ${esc(c.claim)} ` +
      `<span class="badge">${esc(c.verdict)}</span></li>`).join('') + '</ul>';
  }

  function render(body) {
    const el = panel();
    if (!el) return;
    lastBody = body;
    const head = `<div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.4rem;">` +
      `<strong>${esc(t('atlas.manuscript.title'))}</strong>` +
      `<button class="btn btn--sm" onclick="rebuildAtlasManuscript()">${esc(t('atlas.manuscript.rebuild'))}</button>` +
      `<span id="atlasManuscriptNote" style="color: var(--text-muted);"></span></div>`;
    if (!body || body.status !== 'ok' || !body.layer) {
      const key = body && body.status === 'invalid' ? 'atlas.manuscript.invalid' : 'atlas.manuscript.absent';
      el.innerHTML = head + `<div style="color: var(--text-muted);">${esc(t(key))}</div>`;
      return;
    }
    const layer = body.layer;
    const s = layer.summary || {};
    const stale = body.stale ? ` <span class="badge badge--warn">${esc(t('atlas.manuscript.stale'))}</span>` : '';
    const rows = (layer.systems || []).map((sys) => {
      const badge = sys.cited
        ? `<span class="badge badge--ok">${esc(t('atlas.manuscript.cited'))}</span>`
        : `<span class="badge">${esc(t('atlas.manuscript.uncited'))}</span>`;
      const blocks = sys.blocks && sys.blocks.length
        ? ` · ${esc(t('atlas.manuscript.blocks'))}: ${sys.blocks.map((b) => `<code>${esc(b)}</code>`).join(', ')}` : '';
      return `<li style="margin-bottom: 0.25rem;${sys.cited ? '' : ' opacity: 0.7;'}">${badge} <strong>${esc(sys.title || sys.id)}</strong>` +
        ` <span style="color: var(--text-muted);">${esc(sys.id)}</span>${blocks}${claimsHtml(sys.claims)}</li>`;
    }).join('');
    const extra = (layer.extra_systems || []).map((p) =>
      `<li style="margin-bottom: 0.25rem;"><code>${esc(p.cite_key)}</code> ${esc(p.title || '')}` +
      ` <span style="color: var(--text-muted);">${esc(p.identifier || '')}</span>${claimsHtml(p.claims)}</li>`).join('');
    el.innerHTML = head +
      `<div style="margin-bottom: 0.4rem;">${esc(t('atlas.manuscript.summary', {
        cited: s.cited_systems || 0, total: s.systems_total || 0, extra: s.extra_cited || 0,
      }))}${stale}</div>` +
      `<ul style="list-style: none; margin: 0; padding: 0;">${rows}</ul>` +
      (extra ? `<div style="margin-top: 0.5rem;"><strong>${esc(t('atlas.manuscript.extraTitle'))}</strong>` +
        `<ul style="margin: 0.2rem 0 0 1rem; padding: 0;">${extra}</ul></div>` : '');
  }

  async function refreshAtlasManuscript() {
    if (!open) return;
    try {
      const res = await fetch('/api/atlas/manuscript');
      const body = await res.json();
      if (JSON.stringify(body) !== JSON.stringify(lastBody)) render(body);
    } catch (err) {
      render({ status: 'absent' });
    }
  }

  async function rebuildAtlasManuscript() {
    const note = document.getElementById('atlasManuscriptNote');
    if (note) note.textContent = t('atlas.manuscript.rebuilding');
    try {
      const res = await fetch('/api/atlas/manuscript/build', { method: 'POST' });
      const data = await res.json();
      lastBody = null;
      await refreshAtlasManuscript();
      const after = document.getElementById('atlasManuscriptNote');
      if (after) {
        after.textContent = data.ok ? t('atlas.manuscript.rebuilt')
          : t('atlas.manuscript.rebuildFailed', { detail: data.detail || data.status || '' });
      }
    } catch (err) {
      if (note) note.textContent = t('atlas.manuscript.rebuildFailed', { detail: err.message });
    }
  }

  function toggleAtlasManuscript() {
    open = !open;
    const el = panel();
    const btn = document.getElementById('btnAtlasManuscript');
    if (el) el.style.display = open ? 'block' : 'none';
    if (btn) btn.className = open ? 'btn btn--primary' : 'btn';
    lastBody = null;
    refreshAtlasManuscript();
  }

  // The layer is rewritten by commands outside the page; poll while it is shown.
  setInterval(() => {
    if (open && !document.hidden) refreshAtlasManuscript();
  }, 5000);
  document.addEventListener('languagechange', () => {
    if (open && lastBody) render(lastBody);
  });

  window.toggleAtlasManuscript = toggleAtlasManuscript;
  window.refreshAtlasManuscript = refreshAtlasManuscript;
  window.rebuildAtlasManuscript = rebuildAtlasManuscript;
})();
