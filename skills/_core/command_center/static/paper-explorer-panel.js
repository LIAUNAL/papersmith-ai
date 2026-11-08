/* Cited papers view of the Graph Atlas tab: search everything the manuscript cites.
 *
 * GET /api/atlas/cited-papers is a live, read-only join of main.tex, refs.bib,
 * the SOTA pool, the evidence ledger and citations.json, and every one of those
 * is optional, so this view works at any phase of any paper. Search, filters
 * and sorting run in the page. Workspace text is always escaped, and a paper
 * only gets the http(s) link the server accepted. Offline: no CDN.
 *
 * The optional `clusters` of that answer (paper_clusters.py) are a computed
 * reading, not a statement of the manuscript, and the bar above the list says so.
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
    evidence: 'paper/.paper-writing/evidence', references: 'paper/.paper-writing/references.json',
    paper: 'paper/refs.bib',
  };
  const UNCLUSTERED = 'unclustered';
  const MALFORMED = 'malformed';
  const LOCATE_WAIT_MS = 5000;
  const LOCATE_RETRY_MS = 100;
  const COPY_LABEL_MS = 1200;
  let body = null;
  let failure = '';
  let activeCluster = '';
  let latestLoad = 0;
  let locateTimer = 0;
  const copyTimers = new WeakMap();

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
      paper.cluster ? (paper.cluster.terms || []).join(' ') : '',
    ].join(' '));
  }

  function clusterList(answer) {
    const clusters = answer && answer.clusters && answer.clusters.clusters;
    return Array.isArray(clusters) ? clusters : [];
  }

  // Refuses an answer with no paper list, and fills what the view reads from the rest.
  function readAnswer(answer) {
    if (!answer || !Array.isArray(answer.papers)) throw new Error(MALFORMED);
    answer.papers = answer.papers.filter((paper) => paper && typeof paper === 'object');
    answer.summary = { missing_entries: [], with_link: 0, with_abstract: 0, in_pool: 0, ...answer.summary };
    const owner = new Map();
    clusterList(answer).forEach((cluster) => (cluster.keys || []).forEach((key) => owner.set(key, cluster)));
    answer.papers.forEach((paper) => {
      paper.cluster = owner.get(paper.key) || null;
      paper.haystack = searchable(paper);
    });
    return answer;
  }

  async function loadCitedPapers() {
    const list = byId('citedPapersList');
    if (!list) return;
    if (!body) list.innerHTML = `<p class="paper-explorer__empty">${esc(t('explorer.loading'))}</p>`;
    // Only the newest request may answer: an older one can finish last.
    const load = ++latestLoad;
    let answer = null;
    let problem = '';
    try {
      const res = await fetch(API);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      answer = readAnswer(await res.json());
    } catch (err) {
      problem = err.message;
    }
    if (load !== latestLoad) return;
    body = answer;
    failure = problem;
    fillSections();
    renderNote();
    renderClusters();
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

  function clusterChip(id, label, size, hint) {
    return `<button type="button" class="paper-explorer__cluster" data-cluster="${esc(id)}"`
      + ` aria-pressed="${id === activeCluster}" title="${esc(hint)}">${label}`
      + ` <span class="paper-explorer__cluster-size">${esc(size)}</span></button>`;
  }

  function renderClusters() {
    const clusters = clusterList(body);
    const loose = clusters.length ? body.papers.filter((paper) => !paper.cluster).length : 0;
    const known = activeCluster === UNCLUSTERED ? loose > 0 : clusters.some((c) => c.id === activeCluster);
    if (!known) activeCluster = '';
    const bar = byId('citedClustersBar');
    if (!bar) return;
    bar.hidden = clusters.length === 0;
    const parts = clusters.map((cluster) => clusterChip(
      cluster.id, esc(cluster.label), cluster.size, (cluster.terms || []).join(', ')));
    if (loose) parts.push(clusterChip(UNCLUSTERED, esc(t('explorer.unclustered')), loose, ''));
    bar.innerHTML = clusters.length
      ? `<div class="paper-explorer__clusters-note">${esc(t('explorer.clustersNote'))}</div>${parts.join('')}` : '';
  }

  function toggleCluster(id) {
    activeCluster = activeCluster === id ? '' : id;
    renderClusters();
    filterCitedPapers();
  }

  const SORTS = {
    order: (a, b) => a.order - b.order,
    cites: (a, b) => b.cites - a.cites || a.order - b.order,
    year_desc: (a, b) => (Number(b.year) || 0) - (Number(a.year) || 0) || a.order - b.order,
    year_asc: (a, b) => (Number(a.year) || 9999) - (Number(b.year) || 9999) || a.order - b.order,
    title: (a, b) => fold(a.title || a.key).localeCompare(fold(b.title || b.key)),
  };

  function inCluster(paper) {
    if (!activeCluster) return true;
    if (activeCluster === UNCLUSTERED) return !paper.cluster;
    return Boolean(paper.cluster) && paper.cluster.id === activeCluster;
  }

  function matches(paper, words, origin, section) {
    if (!inCluster(paper)) return false;
    if (origin === 'pool' && !paper.in_pool) return false;
    if (origin === 'outside' && paper.in_pool) return false;
    if (section && !(paper.sections || []).some((s) => s.title === section)) return false;
    return words.every((word) => paper.haystack.includes(word));
  }

  function chips(paper) {
    const parts = [`<code>${esc(paper.key)}</code>`];
    if (paper.cluster) parts.push(`<span class="badge badge--info">${esc(paper.cluster.label)}</span>`);
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
      const error = failure === MALFORMED ? t('explorer.badAnswer') : failure;
      list.innerHTML = `<p class="paper-explorer__empty">${esc(t('explorer.loadError', { error }))}</p>`;
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
    activeCluster = '';
    renderClusters();
    filterCitedPapers();
  }

  // The frame's `src` changes when navigation starts, so only its live document
  // says whether the graph is there.
  function graphDocument(frame) {
    const doc = frame.contentDocument;
    // In the read-only snapshot the view is a file; psApiPath names its route.
    const path = doc ? (window.psApiPath ? window.psApiPath(doc.location.pathname) : doc.location.pathname) : '';
    const ready = doc && doc.readyState === 'complete' && path === GRAPH_VIEW;
    return ready && doc.querySelector('.node') ? doc : null;
  }

  const selected = (doc, nodeId) => Array.from(doc.querySelectorAll('.node.sel'))
    .some((node) => node.dataset.id === nodeId);

  // Opens the summary graph of Novelty & Findings on this paper's node. Tries
  // until the node is selected or the wait ends, once per document, so a reload
  // in between still gets the message. A newer locate or leaving that tab ends
  // the attempt.
  function locate(nodeId) {
    const frame = byId('manuscriptSummaryIframe');
    if (!frame || typeof window.openManuscriptSummary !== 'function') return;
    clearTimeout(locateTimer);
    window.openManuscriptSummary();
    const deadline = Date.now() + LOCATE_WAIT_MS;
    let told = null;
    const attempt = () => {
      if (!window.manuscriptSummaryShown()) return;
      const doc = graphDocument(frame);
      if (doc && selected(doc, nodeId)) return;
      if (doc && doc !== told) {
        told = doc;
        frame.contentWindow.postMessage({ type: 'manuscript-graph-locate', id: nodeId }, window.location.origin);
      }
      if (Date.now() < deadline) locateTimer = setTimeout(attempt, LOCATE_RETRY_MS);
    };
    attempt();
  }

  // The label comes from the catalogue, never from the button: a second click
  // would otherwise keep "Copied" for good.
  async function copyCite(button) {
    let done = true;
    try {
      await navigator.clipboard.writeText(`\\cite{${button.dataset.key}}`);
    } catch (_) {
      done = false;
    }
    button.textContent = done ? t('explorer.copied') : t('explorer.copyFailed');
    clearTimeout(copyTimers.get(button));
    copyTimers.set(button, setTimeout(() => { button.textContent = t('explorer.copy'); }, COPY_LABEL_MS));
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
    byId('citedClustersBar')?.addEventListener('click', (event) => {
      const chip = event.target.closest('button[data-cluster]');
      if (chip) toggleCluster(chip.dataset.cluster);
    });
  });
  document.addEventListener('languagechange', () => {
    if (!body && !failure) return;
    fillSections();
    renderNote();
    renderClusters();
    filterCitedPapers();
  });

  window.loadCitedPapers = loadCitedPapers;
  window.filterCitedPapers = filterCitedPapers;
  window.resetCitedFilters = resetCitedFilters;
})();
