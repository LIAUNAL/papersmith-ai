/* Model tab modules drawn from the workspace's own specification.
 *
 * GET /api/model answers `.papersmith/model_spec.json` when the workspace has
 * one, else a neutral specification named after `papersmith.yaml`. This file
 * renders its novelty pillars, hypotheses, concept-map layers and proof-of-
 * concept experiments, and the NeurIPS contribution type the paper-reviewer
 * assigned to the proposal (`contribution_type`); when a part is absent it says what produces it instead
 * of showing anybody else's content. Every value is escaped before insertion;
 * prose fields go through math-panel.js's richText, so $…$ compiles with KaTeX.
 *
 * A specification the server flags with `language_notice` (its prose is not
 * English) is still drawn as written, under a notice in the dashboard's
 * language. A language switch repaints the panel from the last spec.
 *
 * Above the modules, a stepper (GET /api/model/steps) forces Phase 4's order:
 * the problem and its pillars, then the hypotheses, then the mathematics. Each
 * step's "Generate & deliberate" button types `/proposal-deliberation <the
 * step's instruction>` into the agent terminal (window.sendToCli); the
 * mathematics step also offers `/math-tutor`. A locked step's buttons are
 * disabled and say what the step requires.
 *
 * Public surface (window): renderModelModules(spec), renderModelSteps(steps),
 * refreshModelSteps().
 */
(function () {
  'use strict';

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  // Only a #rgb/#rrggbb colour from the spec reaches a style attribute.
  const colour = (v, fallback) => (/^#[0-9a-fA-F]{3,8}$/.test(String(v || '')) ? v : fallback);
  const empty = (text) => `<p class="model-empty">${esc(text)}</p>`;
  // Escaped prose with $…$ / $$…$$ math, flattened to inline HTML.
  const rich = (v) => (window.mathRichText
    ? window.mathRichText(v).replace(/^<p>|<\/p>$/g, '').replace(/<\/p><p>/g, '<br>')
    : esc(v));

  function pillars(spec) {
    const list = ((spec.novelty || {}).pillars || []).filter((p) => p && (p.name || p.summary));
    if (!list.length) return empty(t('modelPanel.noPillars'));
    return list.map((p, i) => {
      const c = colour(p.color, '#38bdf8');
      return `<div class="model-pillar-card" style="--tone: ${c}; border-top: 3px solid ${c};">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="badge tone-ink" style="font-weight: 700;">${esc(p.badge || t('modelPanel.pillar'))}</span>
          <span class="tone-ink" style="font-size: 0.75rem; font-weight: 700;">${esc(t('modelPanel.pillarN', { n: i + 1 }))}</span>
        </div>
        <h3 style="font-size: 0.95rem; font-weight: 700; color: var(--text);">${rich(p.name)}</h3>
        <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.45;">${rich(p.summary)} ${rich(p.details)}</p>
      </div>`;
    }).join('');
  }

  function hypotheses(spec) {
    const list = ((spec.novelty || {}).hypotheses || []).filter((h) => h && (h.title || h.statement));
    if (!list.length) return empty(t('modelPanel.noHypotheses'));
    return list.map((h) => `<div class="model-hypothesis-card">
        <div style="display: flex; justify-content: space-between; gap: 0.5rem;">
          <strong>${esc(h.id || '')} ${rich(h.title || '')}</strong>
          ${h.status ? `<span class="badge">${esc(h.status)}</span>` : ''}
        </div>
        <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.45;">${rich(h.statement)}</p>
        ${h.evidence ? `<p style="font-size: 0.76rem; color: var(--text-muted);">${rich(h.evidence)}</p>` : ''}
      </div>`).join('');
  }

  // The five NeurIPS 2026 contribution types and their catalogue keys.
  const CONTRIBUTION_TYPE_KEYS = {
    'General': 'contribution.type.General',
    'Theory': 'contribution.type.Theory',
    'Use-Inspired': 'contribution.type.Use-Inspired',
    'Concept & Feasibility': 'contribution.type.Concept & Feasibility',
    'Negative Results': 'contribution.type.Negative Results',
  };

  // The paper-reviewer's NeurIPS contribution type for the proposal, after
  // the hypotheses it was read from.
  function contributionType(spec) {
    const ct = spec.contribution_type;
    const head = `<h4 style="font-size: 0.78rem; text-transform: uppercase; color: var(--text-dim); letter-spacing: 0.04em; margin-bottom: 0.6rem;">${esc(t('contribution.title'))}</h4>`;
    if (!ct || !CONTRIBUTION_TYPE_KEYS[ct.type]) return head + empty(t('contribution.owed', { artifact: '.papersmith/model_spec.json' }));
    return `${head}<div class="model-hypothesis-card">
        <span class="badge">${esc(t(CONTRIBUTION_TYPE_KEYS[ct.type]))}</span>
        <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.45;"><strong>${esc(t('contribution.why'))}</strong> ${esc(ct.why)}</p>
      </div>`;
  }

  function layers(spec) {
    const source = spec.concept_map || spec.conceptual_map || {};
    const list = (source.layers || []).filter(Boolean);
    if (!list.length) return empty(t('modelPanel.noLayers'));
    return list.map((layer, i) => {
      const c = colour(layer.color, '#38bdf8');
      const name = layer.name || layer.layer || t('modelPanel.layerN', { n: i + 1 });
      const nodes = (layer.nodes || []).map((n) => `<div class="concept-node" title="${esc(n.desc)}">
          <strong>${rich(n.name)}</strong>${n.desc ? `<span>${rich(n.desc)}</span>` : ''}</div>`).join('');
      return `<div class="concept-layer-card" style="--tone: ${c}; border-left: 4px solid ${c};">
          <div style="display: flex; justify-content: space-between; gap: 0.5rem; align-items: baseline;">
            <strong class="tone-ink">${rich(name)}</strong>
            ${layer.tag ? `<span class="badge">${esc(layer.tag)}</span>` : ''}
          </div>
          <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.45;">${rich(layer.description || layer.desc || '')}</p>
          ${nodes ? `<div class="concept-node-grid">${nodes}</div>` : ''}
        </div>`;
    }).join('');
  }

  function languageNotice(spec) {
    const notice = spec.language_notice;
    if (!notice) return '';
    return esc(t('modelPanel.languageNotice', {
      file: notice.file || '.papersmith/model_spec.json',
      fields: (notice.fields || []).join(', '),
    }));
  }

  let lastSpec = null;

  function renderModelModules(spec) {
    lastSpec = spec || {};
    const put = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
    put('modelPillarGrid', pillars(lastSpec));
    put('modelHypothesisGrid', hypotheses(lastSpec));
    put('modelContributionType', contributionType(lastSpec));
    put('modelConceptLayers', layers(lastSpec));
    const notice = document.getElementById('modelLanguageNotice');
    if (notice) {
      notice.innerHTML = languageNotice(lastSpec);
      notice.hidden = !notice.innerHTML;
    }
  }

  // ---- Phase 4 stepper ------------------------------------------------------
  // Literal catalogue keys per step (never a composed key).
  const STEP_LABELS = {
    problem_pillars: 'modelSteps.problemPillars',
    hypotheses: 'modelSteps.hypotheses',
    mathematics: 'modelSteps.mathematics',
  };
  const STATUS_LABELS = {
    PASS: 'modelSteps.status.pass',
    ACTIVE: 'modelSteps.status.active',
    LOCKED: 'modelSteps.status.locked',
  };
  // What each button types into the agent terminal (agent input stays English).
  const STEP_COMMANDS = {
    problem_pillars: '/proposal-deliberation Let us define the central problem and its pillars first: '
      + 'state the problem and the gap, and decompose it into the novelty pillars before any hypothesis.',
    hypotheses: '/proposal-deliberation Now the hypotheses: for each agreed pillar, the testable prediction it makes, '
      + 'and record them in the revision and in .papersmith/model_spec.json.',
    mathematics: '/proposal-deliberation Now the mathematics: formalize the agreed hypotheses as $$ ... \\tag{N} $$ '
      + 'display blocks in the next revision.',
    'math-tutor': '/math-tutor Walk me through the equations of the latest proposal revision.',
  };
  const STEP_OF_BUTTON = { 'math-tutor': 'mathematics' };

  let lastSteps = null;

  function stepEvidence(step) {
    const e = step.evidence || {};
    if (step.id === 'problem_pillars') {
      return t('modelSteps.evidence.problemPillars', {
        problem: t(e.problem ? 'modelSteps.evidence.yes' : 'modelSteps.evidence.no'), n: Number(e.pillars) || 0 });
    }
    if (step.id === 'hypotheses') return t('modelSteps.evidence.hypotheses', { n: Number(e.hypotheses) || 0 });
    return t('modelSteps.evidence.mathematics', { n: Number(e.equations) || 0 });
  }

  function renderModelSteps(steps) {
    lastSteps = Array.isArray(steps) ? steps : [];
    const host = document.getElementById('modelFlowSteps');
    if (!host) return;
    if (!lastSteps.length) { host.innerHTML = ''; return; }
    const cards = lastSteps.map((step, i) => {
      if (!STEP_LABELS[step.id]) return '';
      const locked = step.status === 'LOCKED';
      const tone = step.status === 'PASS' ? 'ok' : (locked ? 'warn' : 'info');
      const off = locked ? ' disabled aria-disabled="true"' : '';
      const reason = locked && STEP_LABELS[step.requires]
        ? `<p class="model-step__reason">🔒 ${esc(t('modelSteps.requires', { step: t(STEP_LABELS[step.requires]) }))}</p>` : '';
      const tutor = step.id === 'mathematics'
        ? `<button type="button" class="btn btn--sm" data-model-step="math-tutor"${off}>${esc(t('modelSteps.tutor'))}</button>` : '';
      return `<div class="model-step model-step--${esc(String(step.status || '').toLowerCase())}">
          <div class="model-step__head">
            <strong>${i + 1}. ${esc(t(STEP_LABELS[step.id]))}</strong>
            <span class="badge badge--${tone}">${esc(t(STATUS_LABELS[step.status] || 'modelSteps.status.active'))}</span>
          </div>
          <p class="model-step__evidence">${esc(stepEvidence(step))}</p>
          ${reason}
          <div class="model-step__actions">
            <button type="button" class="btn btn--primary btn--sm" data-model-step="${esc(step.id)}"${off}>${esc(t('modelSteps.generate'))}</button>
            ${tutor}
          </div>
        </div>`;
    }).join('');
    host.innerHTML = `<div class="model-steps">
        <h4 class="model-steps__title">${esc(t('modelSteps.title'))}</h4>
        <p class="model-steps__hint">${esc(t('modelSteps.hint'))}</p>
        <div class="model-steps__row">${cards}</div>
      </div>`;
  }

  async function refreshModelSteps() {
    if (typeof fetch !== 'function') return;
    try {
      const res = await fetch('/api/model/steps');
      if (!res.ok) return;
      const body = await res.json();
      renderModelSteps(body.steps || []);
    } catch (_) { /* the stepper stays as it was */ }
  }

  function onStepClick(event) {
    const btn = event.target && event.target.closest && event.target.closest('[data-model-step]');
    if (!btn) return;
    const id = btn.dataset.modelStep;
    const step = (lastSteps || []).find((s) => s.id === (STEP_OF_BUTTON[id] || id));
    if (!step || step.status === 'LOCKED' || !STEP_COMMANDS[id]) return;
    if (typeof window.sendToCli === 'function') window.sendToCli(STEP_COMMANDS[id], false, { kind: 'slash' });
  }

  window.renderModelModules = (spec) => { renderModelModules(spec); refreshModelSteps(); };
  window.renderModelSteps = renderModelSteps;
  window.refreshModelSteps = refreshModelSteps;
  // The empty states, the notice and the stepper come from the catalogue: repaint them.
  if (typeof document.addEventListener === 'function') {
    document.addEventListener('languagechange', () => {
      if (lastSpec) renderModelModules(lastSpec);
      if (lastSteps) renderModelSteps(lastSteps);
    });
    document.addEventListener('click', onStepClick);
  }
})();
