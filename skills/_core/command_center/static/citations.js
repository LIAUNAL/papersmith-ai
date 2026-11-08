/* The SOTA citations of each idea, shared by the proposal and experiment panels.
 *
 * GET /api/citations answers results/citations.py state(root): every idea of the
 * workspace, keyed `pillar:P1`, `hypothesis:H1`, `layer:<name>`, `equation:<tag>`
 * or `experiment:E1`, with its citations (title, year and why, joined to the
 * SOTA pool) and whether it still owes them. The panels call block(key) beside
 * an idea and mark(key) where the idea is collapsed, and repaint from
 * onChange(fn) when load() answers. A key the server does not list is no idea of
 * this workspace, a placeholder of the neutral specification for instance, and
 * draws nothing. Every value is escaped before insertion.
 *
 * Public surface (window.Citations): load(), block(key), mark(key), trees(), onChange(fn).
 */
(function () {
  'use strict';

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);

  let ideas = new Map();
  let trees = [];
  let pending = null;
  const listeners = [];

  const owedNote = () => `<p class="model-step__reason" style="margin: 0.35rem 0 0;">⚠ ${esc(t('citations.owed'))}</p>`;

  function entry(c) {
    const year = c.year ? ` <span style="color: var(--text-dim);">(${esc(c.year)})</span>` : '';
    const lab = c.lab ? ` <span class="badge">${esc(c.lab)}</span>` : '';
    // The reference opens on the SOTA constellation (atlas-reference.js).
    return `<li style="margin-top: 0.25rem;"><button type="button" class="cite-link" data-atlas-ref="${esc(c.id)}" title="${esc(t('citations.openInAtlas'))}"><strong>${esc(c.title || c.id)}</strong></button>${year}${lab}
        ${c.why ? `<span style="color: var(--text-muted);"> — ${esc(c.why)}</span>` : ''}
        ${c.quote ? `<blockquote class="cite-quote" style="margin: 0.2rem 0 0 0.8rem; font-style: italic; color: var(--text-dim);">“${esc(c.quote)}”</blockquote>` : ''}</li>`;
  }

  function block(key) {
    const idea = ideas.get(key);
    if (!idea) return '';
    const list = idea.citations || [];
    return `<div class="idea-citations" style="margin-top: 0.5rem; font-size: 0.76rem; line-height: 1.4;">
        <strong style="color: var(--text-dim);">${esc(t('citations.title'))}</strong>
        ${list.length ? `<ul style="margin: 0; padding-left: 1rem;">${list.map(entry).join('')}</ul>` : ''}
        ${idea.owed ? owedNote() : ''}
      </div>`;
  }

  function mark(key) {
    const idea = ideas.get(key);
    return idea && idea.owed ? `<span class="badge badge--warn">${esc(t('citations.owed'))}</span>` : '';
  }

  async function fetchState() {
    try {
      const res = await fetch('/api/citations', { cache: 'no-store' });
      if (!res.ok) return;
      const body = await res.json();
      ideas = new Map((body.ideas || []).map((idea) => [idea.key, idea]));
      trees = Array.isArray(body.trees) ? body.trees : [];
      listeners.forEach((fn) => fn());
    } catch (_) { /* offline: keep what is shown */ }
  }

  // One request at a time: three panels ask for it as they load.
  function load() {
    if (typeof fetch !== 'function') return Promise.resolve();
    if (!pending) pending = fetchState().finally(() => { pending = null; });
    return pending;
  }

  window.Citations = { load, block, mark, trees: () => trees, onChange: (fn) => { listeners.push(fn); } };
})();
