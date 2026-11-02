/**
 * manuscript-qa-panel.js: the visual QA of the compiled manuscript, shown in
 * the PDF preview tab.
 *
 * Reads GET /api/paper/qa (paper/.qa/qa.json, written after every successful
 * dashboard compile and by `smith paper qa`) and lists its findings by page:
 * text, images or drawings past the text block, figure and table text that
 * prints below 0.70 times the body size, and Overfull boxes from main.log.
 * Each page shows its thumbnail from GET /api/paper/qa/page?n=<page>. The
 * report is flagged stale when main.pdf changed since it was measured.
 * Read-only and offline: no CDN.
 */
(function () {
  'use strict';

  const t = (key, vars) => (typeof window.t === 'function' ? window.t(key, vars) : key);
  const KINDS = ['overflow', 'figure-font', 'table-font', 'overfull'];

  function el(tag, attrs, text) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([name, value]) => node.setAttribute(name, value));
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function kindLabel(kind) {
    return KINDS.includes(kind) ? t(`qa.kind.${kind}`) : kind;
  }

  function detail(finding) {
    if (finding.kind === 'overfull') {
      return t('qa.detail.overfull', {
        excess: finding.excess_pt, start: finding.lines[0], end: finding.lines[1],
      });
    }
    if (finding.kind === 'overflow') {
      return t('qa.detail.overflow', { object: finding.object, excess: finding.excess_pt });
    }
    // A text span outside [0.70, 0.90] x body names the bound it violated:
    // a span above the cap is shown against the cap, never the floor.
    if (finding.bound === 'cap') {
      return t('qa.detail.fontCap', { printed: finding.printed_pt, cap: finding.max_printed_pt });
    }
    return t('qa.detail.font', { printed: finding.printed_pt, floor: finding.min_printed_pt });
  }

  function renderPage(page, findings) {
    const card = el('div', { class: 'qa-page', 'data-page': String(page.page) });
    const head = el('div', { class: 'qa-page__head' });
    head.appendChild(el('strong', {}, t('qa.page', { page: page.page })));
    head.appendChild(el('span', { class: 'badge badge--bad' }, t('qa.pageFindings', { count: findings.length })));
    card.appendChild(head);
    const body = el('div', { class: 'qa-page__body' });
    if (page.png) {
      const img = el('img', {
        class: 'qa-page__thumb', loading: 'lazy',
        src: `/api/paper/qa/page?n=${page.page}`, alt: t('qa.thumbAlt', { page: page.page }),
      });
      body.appendChild(img);
    }
    const list = el('ul', { class: 'qa-page__list' });
    findings.forEach((finding) => {
      const item = el('li', { class: 'qa-finding' });
      item.appendChild(el('span', { class: 'badge badge--warn' }, kindLabel(finding.kind)));
      item.appendChild(el('span', { class: 'qa-finding__detail' }, ` ${detail(finding)}`));
      if (finding.snippet) item.appendChild(el('code', { class: 'qa-finding__snippet' }, finding.snippet));
      list.appendChild(item);
    });
    body.appendChild(list);
    card.appendChild(body);
    return card;
  }

  function render(container, data) {
    container.textContent = '';
    if (!data || data.status !== 'ok' || !data.report) {
      container.appendChild(el('p', { class: 'qa-empty' },
        t(data && data.status === 'invalid' ? 'qa.invalid' : 'qa.absent')));
      return;
    }
    const report = data.report;
    const summary = report.summary || {};
    const status = el('p', { class: 'qa-status' });
    status.appendChild(el('span', { class: `badge ${summary.findings ? 'badge--bad' : 'badge--ok'}` },
      summary.findings ? t('qa.findings', { count: summary.findings }) : t('qa.clean')));
    status.appendChild(el('span', { class: 'qa-status__meta' },
      ` ${t('qa.meta', {
        pages: summary.pages || 0, body: report.body_pt,
        floor: report.min_printed_pt, cap: report.max_printed_pt,
      })}`));
    if (data.stale) status.appendChild(el('span', { class: 'badge badge--warn' }, t('qa.stale')));
    container.appendChild(status);
    (report.warnings || []).forEach((warning) => {
      container.appendChild(el('p', { class: 'qa-warning' }, warning));
    });
    const byPage = new Map();
    (report.findings || []).forEach((finding) => {
      if (!byPage.has(finding.page)) byPage.set(finding.page, []);
      byPage.get(finding.page).push(finding);
    });
    (report.pages || []).forEach((page) => {
      const findings = byPage.get(page.page);
      if (findings && findings.length) container.appendChild(renderPage(page, findings));
    });
  }

  async function refreshManuscriptQa() {
    const container = document.getElementById('manuscriptQaPanel');
    if (!container) return;
    container.textContent = t('qa.loading');
    try {
      const res = await fetch('/api/paper/qa');
      render(container, await res.json());
    } catch (err) {
      container.textContent = t('qa.failed', { detail: err.message });
    }
  }

  document.addEventListener('languagechange', () => {
    const details = document.getElementById('manuscriptQaDetails');
    if (details && details.open) refreshManuscriptQa();
  });

  window.refreshManuscriptQa = refreshManuscriptQa;
})();
