/* Cited papers view of the Graph Atlas tab: search everything the manuscript cites.
 *
 * GET /api/atlas/cited-papers is a live, read-only join of main.tex, refs.bib,
 * the SOTA pool, the evidence ledger and citations.json, and every one of those
 * is optional, so this view works at any phase of any paper. Search, filters
 * and sorting run in the page. Workspace text is always escaped, and a paper
 * only gets the http(s) link the server accepted. Offline: no CDN.
 */
(function () {
  'use strict';

  const t = (key, vars) => (typeof window.t === 'function' ? window.t(key, vars) : key);
  const API = '/api/atlas/cited-papers';
  const GRAPH_VIEW = '/api/atlas/manuscript-graph/view';
  const SCHOLAR = 'https://scholar.google.com/scholar?q=';
  const SOURCES = {
    modules: 'paper-writing scripts', manuscript: 'paper/main.tex', bibliography: 'paper/refs.bib',
    pool: 'sota-pool', graph: 'sota-pool/atlas.json', ideas: '.papersmith/citations.json',
    evidence: 'paper/.paper-writing/evidence',
  };
  let body = null;
  let failure = '';

  const byId = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  // Accents and case never decide a match.
  const fold = (value) => String(value ?? '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();

  function searchable(paper) {
    return fold([
      paper.key, paper.title, (paper.authors || []).join(' '), paper.year, paper.venue, paper.family,
      paper.abstract, (paper.keywords || []).join(' '), paper.link,
      (paper.sections || []).map((s) => s.title).join(' '),
      (paper.claims || []).map((c) => c.claim).join(' '),
      (paper.ideas || []).map((i) => `${i.idea} ${i.why}`).join(' '),
    ].join(' '));
  }

  async function loadCitedPapers() {
    const list = byId('citedPapersList');
    if (!list) return;
    if (!body) list.innerHTML = `<p class="paper-explorer__empty">${esc(t('explorer.loading'))}</p>`;
    try {
      const res = await fetch(API);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      body = await res.json();
      body.papers.forEach((paper) => { paper.haystack = searchable(paper); });
      failure = '';
    } catch (err) {
      body = null;
      failure = err.message;
    }
    fillSections();
    renderNote();
    filterCitedPapers();
  }

  function fillSections() {
    const select = byId('citedSectionFilter');
    if (!select) return;
    const chosen = select.value;
    const titles = [];
    ((body && body.papers) || []).forEach((paper) => (paper.sections || []).forEach((section) => {
      if (section.title && !titles.includes(section.title)) titles.push(section.title);
    }));
    select.innerHTML = `<option value="">${esc(t('explorer.allSections'))}</option>`
      + titles.map((title) => `<option value="${esc(title)}">${esc(title)}</option>`).join('');
    select.value = titles.includes(chosen) ? chosen : '';
    select.hidden = titles.length === 0;
  }

  function renderNote() {
    const note = byId('citedPapersNote');
    if (!note) return;
    const lines = [];
    if (body && body.cite_source === 'refs.bib') lines.push(t('explorer.fromBib'));
    const missing = body ? body.summary.missing_entries : [];
    if (missing.length) lines.push(t('explorer.missingEntries', { n: missing.length, keys: missing.join(', ') }));
    ((body && body.warnings) || []).forEach((warning) => {
      lines.push(t('explorer.warning', { source: SOURCES[warning.code] || warning.code, detail: warning.detail }));
    });
    note.innerHTML = lines.map((line) => `<div>${esc(line)}</div>`).join('');
    note.hidden = lines.length === 0;
  }

  const SORTS = {
    order: (a, b) => a.order - b.order,
    cites: (a, b) => b.cites - a.cites || a.order - b.order,
    year_desc: (a, b) => (Number(b.year) || 0) - (Number(a.year) || 0) || a.order - b.order,
    year_asc: (a, b) => (Number(a.year) || 9999) - (Number(b.year) || 9999) || a.order - b.order,
    title: (a, b) => fold(a.title || a.key).localeCompare(fold(b.title || b.key)),
  };

  function matches(paper, words, origin, section) {
    if (origin === 'pool' && !paper.in_pool) return false;
    if (origin === 'outside' && paper.in_pool) return false;
    if (section && !(paper.sections || []).some((s) => s.title === section)) return false;
    return words.every((word) => paper.haystack.includes(word));
  }

  function chips(paper) {
    const parts = [`<code>${esc(paper.key)}</code>`];
    if (paper.family) parts.push(`<span class="badge">${esc(paper.family)}</span>`);
    parts.push(`<span class="badge">${esc(t(paper.in_pool ? 'explorer.inPool' : 'explorer.outsidePool'))}</span>`);
    if (!paper.has_entry) parts.push(`<span class="badge badge--warn">${esc(t('explorer.noEntry'))}</span>`);
    (paper.sections || []).forEach((section) => {
      if (section.title) parts.push(`<span class="badge">${esc(section.title)} ×${esc(section.count)}</span>`);
    });
    return parts.join(' ');
  }

  function details(paper) {
    const parts = [];
    if (paper.abstract) parts.push(`<p>${esc(paper.abstract)}</p>`);
    if ((paper.keywords || []).length) {
      parts.push(`<p><strong>${esc(t('explorer.keywords'))}:</strong> ${esc(paper.keywords.join(', '))}</p>`);
    }
    if ((paper.ideas || []).length) {
      parts.push(`<strong>${esc(t('explorer.ideas'))}</strong><ul>${paper.ideas.map((item) => (
        `<li><code>${esc(item.idea)}</code> ${esc(item.why)}</li>`)).join('')}</ul>`);
    }
    if ((paper.claims || []).length) {
      parts.push(`<strong>${esc(t('explorer.claims'))}</strong><ul>${paper.claims.map((item) => (
        `<li>${esc(item.claim)} <span class="badge">${esc(item.verdict)}</span></li>`)).join('')}</ul>`);
    }
    if (!parts.length) return '';
    return `<details><summary>${esc(t('explorer.more'))}</summary>${parts.join('')}</details>`;
  }

  function card(paper) {
    const title = esc(paper.title || paper.key);
    const meta = [(paper.authors || []).join(', '), paper.venue, paper.year].filter(Boolean).join(' · ');
    const heading = paper.link
      ? `<a href="${esc(paper.link)}" target="_blank" rel="noopener noreferrer">${title} ↗</a>` : title;
    const actions = [];
    if (paper.title) {
      const scholar = SCHOLAR + encodeURIComponent(paper.title);
      actions.push(`<a class="btn btn--sm" href="${esc(scholar)}" target="_blank" rel="noopener noreferrer">${esc(t('explorer.scholar'))}</a>`);
    }
    actions.push(`<button class="btn btn--sm" data-action="copy" data-key="${esc(paper.key)}">${esc(t('explorer.copy'))}</button>`);
    if (paper.node_id) {
      actions.push(`<button class="btn btn--sm" data-action="locate" data-node="${esc(paper.node_id)}">${esc(t('explorer.locate'))}</button>`);
    }
    return `<article class="paper-card"><h4 class="paper-card__title">${heading}</h4>`
      + (meta ? `<div class="paper-card__meta">${esc(meta)}</div>` : '')
      + `<div class="paper-card__chips">${chips(paper)}</div>${details(paper)}`
      + `<div class="paper-card__actions">${actions.join('')}</div></article>`;
  }

  function filterCitedPapers() {
    const list = byId('citedPapersList');
    const count = byId('citedPapersCount');
    if (!list) return;
    if (failure) {
      list.innerHTML = `<p class="paper-explorer__empty">${esc(t('explorer.loadError', { error: failure }))}</p>`;
      if (count) count.textContent = '';
      return;
    }
    if (!body) return;
    const papers = body.papers;
    const words = fold(byId('citedSearchInput')?.value || '').split(/\s+/).filter(Boolean);
    const origin = byId('citedOriginFilter')?.value || '';
    const section = byId('citedSectionFilter')?.value || '';
    const sort = SORTS[byId('citedSortSelect')?.value] || SORTS.order;
    const shown = papers.filter((paper) => matches(paper, words, origin, section)).sort(sort);
    if (count) {
      count.textContent = t('explorer.showing', {
        n: shown.length, total: papers.length, links: body.summary.with_link,
        abstracts: body.summary.with_abstract, pool: body.summary.in_pool,
      });
    }
    const empty = papers.length ? t('explorer.noMatches') : t('explorer.empty');
    list.innerHTML = shown.length ? shown.map(card).join('')
      : `<p class="paper-explorer__empty">${esc(empty)}</p>`;
  }

  function resetCitedFilters() {
    ['citedSearchInput', 'citedOriginFilter', 'citedSectionFilter'].forEach((id) => {
      const field = byId(id);
      if (field) field.value = '';
    });
    const sort = byId('citedSortSelect');
    if (sort) sort.value = 'order';
    filterCitedPapers();
  }

  // Opens the summary graph on this paper's node, loading the view when needed.
  function locate(nodeId) {
    const frame = byId('graphIframe');
    if (!frame || typeof window.switchGraph !== 'function') return;
    const loaded = new URL(frame.src, window.location.href).pathname === GRAPH_VIEW;
    const send = () => frame.contentWindow.postMessage(
      { type: 'manuscript-graph-locate', id: nodeId }, window.location.origin);
    window.switchGraph('summary');
    if (loaded) send();
    else frame.addEventListener('load', send, { once: true });
  }

  async function copyCite(button) {
    const label = button.textContent;
    try {
      await navigator.clipboard.writeText(`\\cite{${button.dataset.key}}`);
      button.textContent = t('explorer.copied');
    } catch (_) {
      button.textContent = t('explorer.copyFailed');
    }
    setTimeout(() => { button.textContent = label; }, 1200);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const list = byId('citedPapersList');
    if (!list) return;
    list.addEventListener('click', (event) => {
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      if (button.dataset.action === 'copy') copyCite(button);
      else locate(button.dataset.node);
    });
  });
  document.addEventListener('languagechange', () => {
    if (!body && !failure) return;
    fillSections();
    renderNote();
    filterCitedPapers();
  });

  window.loadCitedPapers = loadCitedPapers;
  window.filterCitedPapers = filterCitedPapers;
  window.resetCitedFilters = resetCitedFilters;
})();
