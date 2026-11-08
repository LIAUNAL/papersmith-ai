/**
 * contribution-affinity.js: the "affinity by contribution type" subsection of
 * the judge-reviewer's analysis, shared by the Concept Map & Model card and the
 * Novelty & Findings card.
 *
 * The paper-reviewer scores how well the work fits each of the five
 * contribution types (0-100) with a short reason. Each type is a
 * <details> row: its green bar fills to the score, and opening it shows the
 * reviewer guide's definition of the type and the reason for the score.
 */
(function () {
  'use strict';

  const t = (key, vars) => (typeof window.t === 'function' ? window.t(key, vars) : key);
  const esc = (value) => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  // The five types, in the reviewer guide's order, and their definition keys.
  const TYPES = [
    ['General', 'general'],
    ['Theory', 'theory'],
    ['Use-Inspired', 'useInspired'],
    ['Concept & Feasibility', 'conceptFeasibility'],
    ['Negative Results', 'negativeResults'],
  ];

  function scoreOf(entry) {
    const score = entry ? Number(entry.score) : NaN;
    return Number.isInteger(score) && score >= 0 && score <= 100 ? score : null;
  }

  function html(ct) {
    const affinity = ct && ct.affinity && typeof ct.affinity === 'object' ? ct.affinity : null;
    const rows = TYPES.map(([name, slug]) => {
      const entry = affinity ? affinity[name] : null;
      const score = scoreOf(entry);
      const chosen = ct && ct.type === name ? ' ct-affinity__row--chosen' : '';
      const fill = score === null ? '' : `<span class="ct-affinity__fill" style="width: ${score}%"></span>`;
      const reason = score === null ? ''
        : `<p><strong>${esc(t('contribution.affinity.why'))}</strong> ${esc(entry.why)}</p>`;
      return `<details class="ct-affinity__row${chosen}" data-affinity-type="${name}">
          <summary>
            <span class="ct-affinity__name">${esc(t(`contribution.type.${name}`))}</span>
            <span class="ct-affinity__track">${fill}</span>
            <span class="ct-affinity__score">${score === null ? '—' : `${score}%`}</span>
          </summary>
          <div class="ct-affinity__box">
            <p><strong>${esc(t('contribution.affinity.definition'))}</strong> ${esc(t(`contribution.def.${slug}`))}</p>
            ${reason}
          </div>
        </details>`;
    }).join('');
    const note = affinity ? '' : `<p class="ct-affinity__note">${esc(t('contribution.affinity.unscored'))}</p>`;
    return `<div class="ct-affinity">
        <h5 class="ct-affinity__title">${esc(t('contribution.affinity.title'))}</h5>
        ${note}${rows}
      </div>`;
  }

  window.ContributionAffinity = { html };
})();
