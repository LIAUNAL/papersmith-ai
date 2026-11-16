/* Final judge panel of the PDF Preview tab.
 *
 * Shows the paper-reviewer's passes over the assembled manuscript, read from
 * .papersmith/paper_review.json through GET /api/paper/review: per round the
 * overall score (1-6), confidence (1-5), recommendation and the four 1-4
 * ratings; the verdict on each item the previous round raised; the remaining
 * revisions with their status; and the full report text. Read-only: nothing
 * here launches the judge or edits the paper.
 *
 * Every value is escaped before insertion. Public surface (window):
 * refreshPaperReview(), PaperReviewPanel (the pure HTML builder, for tests).
 */
(function () {
  'use strict';

  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const list = (v) => (Array.isArray(v) ? v : []);
  const obj = (v) => (v && typeof v === 'object' && !Array.isArray(v) ? v : {});

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key) => (window.i18n ? window.i18n.t(key) : key);

  const VERDICT_BADGE = {
    resolved: 'badge--ok', partly: 'badge--warn', 'not resolved': 'badge--bad',
    done: 'badge--ok', applied: 'badge--ok', pending: 'badge--warn', 'not done': 'badge--bad', skipped: 'badge--info',
  };
  const badge = (v) => `<span class="badge ${VERDICT_BADGE[String(v).toLowerCase()] || 'badge--info'}">${esc(v)}</span>`;

  function roundSummary(r) {
    const ratings = obj(r.ratings);
    const chips = Object.keys(ratings).map((k) => `<span class="badge badge--info">${esc(k)} ${esc(ratings[k])}/4</span>`).join(' ');
    return `
      <div class="review-round__head" style="display:flex;flex-wrap:wrap;gap:0.5rem;align-items:center;">
        <strong>${esc(t('review.round'))} ${esc(r.round)}</strong>
        <span class="panel__meta">${esc(r.date || '')}</span>
        <span class="badge ${Number(r.overall) >= 5 ? 'badge--ok' : Number(r.overall) >= 4 ? 'badge--warn' : 'badge--bad'}">${esc(t('review.overall'))} ${esc(r.overall)}/6</span>
        <span class="badge badge--info">${esc(t('review.confidence'))} ${esc(r.confidence)}/5</span>
      </div>
      <p style="margin:0.4rem 0;"><strong>${esc(t('review.recommendation'))}:</strong> ${esc(r.recommendation || '')}</p>
      ${chips ? `<p style="margin:0.3rem 0;"><strong>${esc(t('review.ratings'))}:</strong> ${chips}</p>` : ''}`;
  }

  function table(head, rows) {
    if (!rows.length) return '';
    return `<div class="table-responsive"><table class="data-table"><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead>
      <tbody>${rows.join('')}</tbody></table></div>`;
  }

  function roundDetail(r) {
    const items = list(r.items).map((i) => `<tr><td>${esc(i.item)}</td><td>${badge(i.verdict)}</td><td>${esc(i.evidence || '')}</td></tr>`);
    const revs = list(r.revisions).map((v) => `<tr><td>${esc(v.rank)}</td><td>${esc(v.text)}</td><td>${badge(v.status || 'pending')}</td><td>${esc(v.note || '')}</td></tr>`);
    const excluded = list(r.excluded);
    return `
      ${items.length ? `<h4 style="margin:0.8rem 0 0.3rem;">${esc(t('review.items'))}</h4>${table([t('review.item'), t('review.verdict'), t('review.evidence')], items)}` : ''}
      ${revs.length ? `<h4 style="margin:0.8rem 0 0.3rem;">${esc(t('review.revisions'))}</h4>${table(['#', t('review.item'), t('review.status'), t('review.evidence')], revs)}` : ''}
      ${excluded.length ? `<p class="panel__meta" style="margin-top:0.5rem;"><strong>${esc(t('review.excluded'))}:</strong> ${excluded.map(esc).join('; ')}</p>` : ''}
      ${r.report ? `<details style="margin-top:0.6rem;"><summary>${esc(t('review.report'))}</summary>
        <pre style="white-space:pre-wrap;font-size:0.78rem;max-height:520px;overflow:auto;">${esc(r.report)}</pre></details>` : ''}`;
  }

  function render(state) {
    const s = obj(state);
    if (s.status && s.status !== 'ok' && s.status !== 'absent') return `<p class="banner banner--warn">${esc(t('review.invalid'))}${esc(s.status)}</p>`;
    const rounds = list(s.rounds).slice().sort((a, b) => Number(b.round) - Number(a.round));
    if (!rounds.length) return `<p class="panel__empty">${esc(t('review.empty'))}</p>`;
    const [latest, ...older] = rounds;
    return `
      <div class="review-round">${roundSummary(latest)}${roundDetail(latest)}</div>
      ${older.length ? `<h4 style="margin:1rem 0 0.3rem;">${esc(t('review.history'))}</h4>${older.map((r) => `
        <details class="review-round" style="margin:0.3rem 0;"><summary>${esc(t('review.round'))} ${esc(r.round)} · ${esc(r.overall)}/6 · ${esc(r.recommendation || '')}</summary>
          ${roundSummary(r)}${roundDetail(r)}</details>`).join('')}` : ''}`;
  }

  async function refreshPaperReview() {
    const host = document.getElementById('paperReviewPanel');
    if (!host) return;
    try {
      const res = await fetch('/api/paper/review', { cache: 'no-store' });
      host.innerHTML = render(await res.json());
    } catch (e) {
      host.innerHTML = `<p class="banner banner--warn">${esc(t('review.invalid'))}${esc(e && e.message)}</p>`;
    }
  }

  window.refreshPaperReview = refreshPaperReview;
  window.PaperReviewPanel = { render };
  document.addEventListener('languagechange', refreshPaperReview);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', refreshPaperReview);
  else refreshPaperReview();
})();
