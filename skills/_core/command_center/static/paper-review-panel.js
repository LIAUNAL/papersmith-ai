/* Final judge panel of the PDF Preview tab.
 *
 * Shows the paper-reviewer's passes over the assembled manuscript, read from
 * .papersmith/paper_review.json through GET /api/paper/review: per round the
 * overall score (1-6), confidence (1-5), recommendation and the four 1-4
 * ratings; the verdict on each item the previous round raised; the remaining
 * revisions with their status; and the full report text. Its one button types
 * the next round's request into the agent terminal (/paper-writing hands the
 * compiled paper to the paper-reviewer and records the round with
 * `paper_cli.py review`); nothing here writes the review file or the paper.
 *
 * Every value is escaped before insertion. Public surface (window):
 * refreshPaperReview(), launchPaperJudge(), PaperReviewPanel (the pure HTML
 * builder, for tests).
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

  // The round the button asks for: one past the highest recorded (1 when none);
  // 0 while the review file cannot be read, so nothing is launched.
  let nextRound = 0;

  // What the button types into the agent terminal (agent input stays English).
  function judgeCommand(round) {
    const previous = round > 1
      ? ` This round must judge every revision the previous round raised (one verdict per rank in items).`
      : '';
    return `/paper-writing Run the final judge, round ${round}: hand the compiled paper/main.tex to the paper-reviewer agent `
      + `for its full main-track review. Save the round JSON it returns to a scratch file and record it with `
      + `python skills/paper-writing/scripts/paper_cli.py review --input <file>; on a refusal, send the round back `
      + `to the agent with the refusal detail instead of editing it.${previous}`;
  }

  function launchPaperJudge() {
    if (nextRound > 0 && typeof window.sendToCli === 'function') window.sendToCli(judgeCommand(nextRound), false, { kind: 'slash' });
  }

  function judgeAction(rounds) {
    const label = rounds.length ? t('review.launchAgain').replace('{round}', String(nextRound)) : t('review.launch');
    return `<div class="review-launch" style="display:flex;flex-wrap:wrap;gap:0.5rem;align-items:center;margin-bottom:0.6rem;">
        <button type="button" class="btn ${rounds.length ? '' : 'btn--primary '}btn--sm" data-paper-judge="${nextRound}" onclick="window.launchPaperJudge()">${esc(label)}</button>
        <span class="panel__meta">${esc(t('review.launchHint'))}</span>
      </div>`;
  }

  function render(state) {
    const s = obj(state);
    nextRound = 0;
    if (s.status && s.status !== 'ok' && s.status !== 'absent') return `<p class="banner banner--warn">${esc(t('review.invalid'))}${esc(s.status)}</p>`;
    const rounds = list(s.rounds).slice().sort((a, b) => Number(b.round) - Number(a.round));
    const highest = rounds.length ? Number(rounds[0].round) : 0;
    nextRound = Number.isFinite(highest) && highest > 0 ? Math.floor(highest) + 1 : rounds.length + 1;
    if (!rounds.length) return `${judgeAction(rounds)}<p class="panel__empty">${esc(t('review.empty'))}</p>`;
    const [latest, ...older] = rounds;
    return `${judgeAction(rounds)}
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
  window.launchPaperJudge = launchPaperJudge;
  window.PaperReviewPanel = { render };
  document.addEventListener('languagechange', refreshPaperReview);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', refreshPaperReview);
  else refreshPaperReview();
})();
