/* Final judge panel of the PDF Preview tab.
 *
 * Shows the paper-reviewer's passes over the assembled manuscript, read from
 * .papersmith/paper_review.json through GET /api/paper/review: per round the
 * overall score (1-6), confidence (1-5), recommendation and the four 1-4
 * ratings; the verdict on each item the previous round raised; the remaining
 * revisions with their status; and the full report text. A round judged on
 * the systematic-review rubric (`rubric: "systematic-review"`, review papers)
 * shows instead its AMSTAR 2 overall confidence, critical flaws and
 * non-critical weaknesses, the 16 item answers and the PRISMA 2020 reporting
 * gaps; a round without `rubric` renders exactly as before. A round judged on
 * the empirical-study rubric (`rubric: "empirical-study"`, the empirical lines)
 * shows its overall risk of bias, its protocol adherence and deviations, its
 * design validity, the risk of bias per domain and the reporting-checklist
 * gaps. A round judged on the measurement-science rubric
 * (`rubric: "measurement-science"`, the hardware and lab-simulation lines)
 * shows its derived overall rating, its five criteria (design validity,
 * calibration and traceability, uncertainty, reproducibility and open
 * materials, agreement or validation) and the gaps against the line's
 * checklist. Read-only: nothing here launches the judge or edits the paper.
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

  const isReview = (r) => r.rubric === 'systematic-review';
  const key = (v) => String(v ?? '').replace(/ /g, '_');
  const ANSWER_BADGE = { yes: 'badge--ok', 'partial yes': 'badge--warn', no: 'badge--bad', 'not applicable': 'badge--info' };
  const LEVEL_BADGE = { high: 'badge--ok', moderate: 'badge--warn', low: 'badge--bad', 'critically low': 'badge--bad' };
  const answerBadge = (a) => `<span class="badge ${ANSWER_BADGE[a] || 'badge--info'}">${esc(t(`review.amstar2.answer.${key(a)}`))}</span>`;
  const levelText = (v) => t(`review.amstar2.level.${key(v)}`);
  const itemList = (v) => (list(v).length ? list(v).map(esc).join(', ') : esc(t('review.amstar2.none')));

  // The systematic-review rubric (AMSTAR 2 and PRISMA 2020): head and tables.
  function reviewSummary(r) {
    const answers = list(r.amstar2).map((a) => `<tr><td>${esc(a.item)}</td>
      <td>${a.critical ? `<span class="badge badge--info">${esc(t('review.amstar2.critical'))}</span>` : ''}</td>
      <td>${answerBadge(a.answer)}</td><td>${esc(a.justification || '')}</td></tr>`);
    const gaps = list(r.prisma_gaps).map((g) => `<tr><td>${esc(g.item)}</td><td>${esc(g.gap || '')}</td></tr>`);
    return `
      <div class="review-round__head" style="display:flex;flex-wrap:wrap;gap:0.5rem;align-items:center;">
        <strong>${esc(t('review.round'))} ${esc(r.round)}</strong>
        <span class="panel__meta">${esc(r.date || '')}</span>
        <span class="badge badge--info">${esc(t('review.rubric.systematic'))}</span>
        <span class="badge ${LEVEL_BADGE[r.overall_confidence] || 'badge--info'}">${esc(t('review.amstar2.confidence'))}: ${esc(levelText(r.overall_confidence))}</span>
      </div>
      <p style="margin:0.4rem 0;"><strong>${esc(t('review.recommendation'))}:</strong> ${esc(r.recommendation || '')}</p>
      <p style="margin:0.3rem 0;"><strong>${esc(t('review.amstar2.flaws'))}:</strong> ${itemList(r.critical_flaws)}
        · <strong>${esc(t('review.amstar2.weaknesses'))}:</strong> ${itemList(r.non_critical_weaknesses)}</p>
      ${answers.length ? `<h4 style="margin:0.8rem 0 0.3rem;">${esc(t('review.amstar2.items'))}</h4>${table([t('review.amstar2.item'), t('review.amstar2.critical'), t('review.amstar2.answer'), t('review.amstar2.justification')], answers)}` : ''}
      ${gaps.length ? `<h4 style="margin:0.8rem 0 0.3rem;">${esc(t('review.prisma.gaps'))}</h4>${table([t('review.prisma.item'), t('review.prisma.gap')], gaps)}` : ''}`;
  }

  // The empirical-study rubric: protocol adherence, design validity, risk of bias, checklist gaps.
  const isEmpirical = (r) => r.rubric === 'empirical-study';
  const BIAS_BADGE = { low: 'badge--ok', 'some concerns': 'badge--warn', high: 'badge--bad' };
  const DESIGN_BADGE = { adequate: 'badge--ok', limited: 'badge--warn', inadequate: 'badge--bad' };
  const ADHERENCE_BADGE = { followed: 'badge--ok', deviated: 'badge--warn', 'no protocol': 'badge--bad' };
  const keyed = (map, prefix, v) => `<span class="badge ${map[v] || 'badge--info'}">${esc(t(`${prefix}.${key(v)}`))}</span>`;
  const biasText = (v) => t(`review.empirical.level.${key(v)}`);

  function empiricalSummary(r) {
    const adherence = obj(r.protocol_adherence);
    const design = obj(r.design_validity);
    const deviations = list(adherence.deviations).map((d) => `<tr><td>${esc(d.deviation || '')}</td>
      <td>${keyed({ true: 'badge--ok', false: 'badge--bad' }, 'review.empirical.declared', String(d.declared === true))}</td></tr>`);
    const domains = list(r.risk_of_bias).map((d) => `<tr><td>${esc(t(`review.empirical.domain.${key(d.domain)}`))}</td>
      <td>${keyed(BIAS_BADGE, 'review.empirical.level', d.rating)}</td><td>${esc(d.justification || '')}</td></tr>`);
    const gaps = list(r.checklist_gaps).map((g) => `<tr><td>${esc(g.item)}</td><td>${esc(g.gap || '')}</td></tr>`);
    return `
      <div class="review-round__head" style="display:flex;flex-wrap:wrap;gap:0.5rem;align-items:center;">
        <strong>${esc(t('review.round'))} ${esc(r.round)}</strong>
        <span class="panel__meta">${esc(r.date || '')}</span>
        <span class="badge badge--info">${esc(t('review.rubric.empirical'))}</span>
        <span class="badge ${BIAS_BADGE[r.overall_risk_of_bias] || 'badge--info'}">${esc(t('review.empirical.overall'))}: ${esc(biasText(r.overall_risk_of_bias))}</span>
      </div>
      <p style="margin:0.4rem 0;"><strong>${esc(t('review.recommendation'))}:</strong> ${esc(r.recommendation || '')}</p>
      <p style="margin:0.3rem 0;"><strong>${esc(t('review.empirical.adherence'))}:</strong>
        ${esc(t('review.empirical.primary_outcome'))} ${keyed(ADHERENCE_BADGE, 'review.empirical.adherence', adherence.primary_outcome)}
        · ${esc(t('review.empirical.analysis_plan'))} ${keyed(ADHERENCE_BADGE, 'review.empirical.adherence', adherence.analysis_plan)}
        · ${esc(t('review.empirical.undeclared'))}: ${esc(adherence.undeclared_deviations ?? 0)}</p>
      ${adherence.justification ? `<p class="panel__meta" style="margin:0.2rem 0;">${esc(adherence.justification)}</p>` : ''}
      <p style="margin:0.3rem 0;"><strong>${esc(t('review.empirical.design'))}:</strong> ${keyed(DESIGN_BADGE, 'review.empirical.design', design.rating)}
        ${esc(design.justification || '')}</p>
      ${deviations.length ? `<h4 style="margin:0.8rem 0 0.3rem;">${esc(t('review.empirical.deviations'))}</h4>${table([t('review.empirical.deviation'), t('review.empirical.declared')], deviations)}` : ''}
      ${domains.length ? `<h4 style="margin:0.8rem 0 0.3rem;">${esc(t('review.empirical.bias'))}</h4>${table([t('review.empirical.domain'), t('review.empirical.rating'), t('review.empirical.justification')], domains)}` : ''}
      ${gaps.length ? `<h4 style="margin:0.8rem 0 0.3rem;">${esc(t('review.empirical.gaps'))}${r.checklist ? ` (${esc(r.checklist)})` : ''}</h4>${table([t('review.empirical.item'), t('review.empirical.gap')], gaps)}` : ''}`;
  }

  // The measurement-science rubric: five rated criteria, the derived overall, checklist gaps.
  const isMeasurement = (r) => r.rubric === 'measurement-science';
  const MEASUREMENT_CRITERIA = ['design_validity', 'calibration_traceability', 'uncertainty', 'reproducibility', 'agreement'];
  const RATING_BADGE = { adequate: 'badge--ok', limited: 'badge--warn', inadequate: 'badge--bad', 'not applicable': 'badge--info' };
  const OVERALL_BADGE = { sound: 'badge--ok', 'minor concerns': 'badge--warn', 'major concerns': 'badge--bad' };
  const measurementText = (v) => t(`review.measurement.overall.${key(v)}`);

  function measurementSummary(r) {
    const criteria = MEASUREMENT_CRITERIA.map((name) => {
      const c = obj(r[name]);
      return `<tr><td>${esc(t(`review.measurement.criterion.${name}`))}</td>
      <td>${keyed(RATING_BADGE, 'review.measurement.rating', c.rating)}</td><td>${esc(c.justification || '')}</td></tr>`;
    });
    const gaps = list(r.checklist_gaps).map((g) => `<tr><td>${esc(g.item)}</td><td>${esc(g.gap || '')}</td></tr>`);
    return `
      <div class="review-round__head" style="display:flex;flex-wrap:wrap;gap:0.5rem;align-items:center;">
        <strong>${esc(t('review.round'))} ${esc(r.round)}</strong>
        <span class="panel__meta">${esc(r.date || '')}</span>
        <span class="badge badge--info">${esc(t('review.rubric.measurement'))}</span>
        <span class="badge ${OVERALL_BADGE[r.overall_rating] || 'badge--info'}">${esc(t('review.measurement.overall'))}: ${esc(measurementText(r.overall_rating))}</span>
      </div>
      <p style="margin:0.4rem 0;"><strong>${esc(t('review.recommendation'))}:</strong> ${esc(r.recommendation || '')}</p>
      <h4 style="margin:0.8rem 0 0.3rem;">${esc(t('review.measurement.criteria'))}</h4>${table([t('review.measurement.criterion'), t('review.measurement.rating'), t('review.measurement.justification')], criteria)}
      ${gaps.length ? `<h4 style="margin:0.8rem 0 0.3rem;">${esc(t('review.measurement.gaps'))}${r.checklist ? ` (${esc(r.checklist)})` : ''}</h4>${table([t('review.measurement.item'), t('review.measurement.gap')], gaps)}` : ''}`;
  }

  const summary = (r) => (isMeasurement(r) ? measurementSummary(r)
    : isEmpirical(r) ? empiricalSummary(r) : isReview(r) ? reviewSummary(r) : roundSummary(r));
  const headline = (r) => (isMeasurement(r) ? esc(measurementText(r.overall_rating))
    : isEmpirical(r) ? esc(biasText(r.overall_risk_of_bias))
    : isReview(r) ? esc(levelText(r.overall_confidence)) : `${esc(r.overall)}/6`);

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
      <div class="review-round">${summary(latest)}${roundDetail(latest)}</div>
      ${older.length ? `<h4 style="margin:1rem 0 0.3rem;">${esc(t('review.history'))}</h4>${older.map((r) => `
        <details class="review-round" style="margin:0.3rem 0;"><summary>${esc(t('review.round'))} ${esc(r.round)} · ${headline(r)} · ${esc(r.recommendation || '')}</summary>
          ${summary(r)}${roundDetail(r)}</details>`).join('')}` : ''}`;
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
