/* Paper type pane: which kind of paper the accepted idea becomes.
 *
 * GET /api/paper-type answers the catalogue (paper_types.json), the idea the
 * operator accepted at the end of plausibility, the deterministic score of
 * every type and any agreement. One card per type shows its name, summary,
 * score, availability, reporting guidelines and how the idea relates to it
 * (the signal words it matched). The operator can rescore the idea, discuss it
 * with the agent (types /paper-type into the terminal) or agree a type and
 * variant; nothing is agreed without that click and a name. Every value is
 * escaped before insertion.
 *
 * Public surface (window): refreshPaperTypePanel(), PaperTypePanel.html(view).
 */
(function () {
  'use strict';

  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const list = (v) => (Array.isArray(v) ? v : []);

  // Literal catalogue keys per type and variant (never a composed key).
  const TYPE_KEYS = {
    'applied-ai': ['paperType.type.appliedAi.name', 'paperType.type.appliedAi.summary'],
    review: ['paperType.type.review.name', 'paperType.type.review.summary'],
    'observational-measurement': ['paperType.type.observational.name', 'paperType.type.observational.summary'],
    'experiment-intervention': ['paperType.type.experiment.name', 'paperType.type.experiment.summary'],
    'qualitative-participatory': ['paperType.type.qualitative.name', 'paperType.type.qualitative.summary'],
    hardware: ['paperType.type.hardware.name', 'paperType.type.hardware.summary'],
    'lab-simulation': ['paperType.type.labSimulation.name', 'paperType.type.labSimulation.summary'],
    'data-resource': ['paperType.type.dataResource.name', 'paperType.type.dataResource.summary'],
  };
  const VARIANT_KEYS = {
    observational: 'paperType.variant.observational',
    'diagnostic-validation': 'paperType.variant.diagnosticValidation',
    'measurement-instrument': 'paperType.variant.measurementInstrument',
    'human-trial': 'paperType.variant.humanTrial',
    'field-experiment': 'paperType.variant.fieldExperiment',
    'qualitative-mixed': 'paperType.variant.qualitativeMixed',
    'consensus-foresight': 'paperType.variant.consensusForesight',
    'experience-report': 'paperType.variant.experienceReport',
    materials: 'paperType.variant.materials',
    'modelling-simulation': 'paperType.variant.modellingSimulation',
  };
  const CONFIDENCE_KEYS = {
    high: 'paperType.confidence.high', medium: 'paperType.confidence.medium', low: 'paperType.confidence.low',
  };
  const LAYOUT_KEYS = {
    current: 'paperType.layout.current', planned: 'paperType.layout.planned', switch: 'paperType.layout.switch',
  };

  // A catalogue entry's translated label, or the catalogue's own English.
  const typeName = (type) => (TYPE_KEYS[type.id] ? t(TYPE_KEYS[type.id][0]) : type.name);
  const typeSummary = (type) => (TYPE_KEYS[type.id] ? t(TYPE_KEYS[type.id][1]) : type.summary);
  const variantName = (type, id) => {
    if (!id) return '';
    if (VARIANT_KEYS[id]) return t(VARIANT_KEYS[id]);
    const found = list(type && type.variants).find((v) => v.id === id);
    return found ? found.name : id;
  };

  let lastView = null;
  let openAgree = null;   // the type id whose agreement form is open
  let notice = '';        // the last action's outcome, already translated

  function relation(row) {
    const words = list(row && row.matched);
    if (words.length) return t('paperType.relation.matched', { words: words.join(', ') });
    return t('paperType.relation.none');
  }

  function card(type, row, record) {
    const suggested = record && record.suggested === type.id;
    const agreed = record && record.agreed === type.id;
    const score = row ? Number(row.score) || 0 : 0;
    const status = type.status === 'available'
      ? `<span class="badge badge--ok">${esc(t('paperType.status.available'))}</span>`
      : `<span class="badge badge--info">${esc(t('paperType.status.planned'))}</span>`;
    const marks = (suggested ? `<span class="badge badge--warn">${esc(t('paperType.suggestedBadge'))}</span>` : '')
      + (agreed ? `<span class="badge badge--ok">${esc(t('paperType.agreedBadge'))}</span>` : '');
    const guidelines = list(type.guidelines).map((g) => esc(g.name)).join(', ');
    const variants = list(type.variants);
    const variantLine = row && row.variant
      ? `<p class="pt-card__variant">${esc(t('paperType.variantMatched', { variant: variantName(type, row.variant) }))}</p>` : '';
    const form = openAgree === type.id ? `<div class="pt-agree">
        <label>${esc(t('paperType.agreeBy'))} <input type="text" id="ptBy" autocomplete="name"></label>
        ${variants.length ? `<label>${esc(t('paperType.agreeVariant'))} <select id="ptVariant">${variants.map((v) => `<option value="${esc(v.id)}"${row && row.variant === v.id ? ' selected' : ''}>${esc(variantName(type, v.id))}</option>`).join('')}</select></label>` : ''}
        <label>${esc(t('paperType.agreeRationale'))} <input type="text" id="ptRationale"></label>
        <div class="pt-agree__actions">
          <button type="button" class="btn btn--primary btn--sm" data-pt-action="agree-confirm" data-pt-type="${esc(type.id)}">${esc(t('paperType.agreeConfirm'))}</button>
          <button type="button" class="btn btn--sm" data-pt-action="agree-cancel">${esc(t('paperType.cancel'))}</button>
        </div>
      </div>` : '';
    return `<article class="pt-card${suggested ? ' pt-card--suggested' : ''}${agreed ? ' pt-card--agreed' : ''}" data-pt-card="${esc(type.id)}">
        <header class="pt-card__head"><strong>${esc(typeName(type))}</strong> ${status} ${marks}</header>
        <p class="pt-card__summary">${esc(typeSummary(type))}</p>
        <div class="pt-bar" title="${esc(t('paperType.scoreTitle', { score }))}"><span style="width:${Math.max(0, Math.min(100, score))}%"></span></div>
        <p class="pt-card__score">${esc(t('paperType.score', { score }))}</p>
        <p class="pt-card__relation">${esc(relation(row))}</p>
        ${variantLine}
        ${guidelines ? `<p class="pt-card__guidelines">${esc(t('paperType.guidelines'))}: ${guidelines}</p>` : ''}
        ${form || (record ? `<button type="button" class="btn btn--sm" data-pt-action="agree-open" data-pt-type="${esc(type.id)}">${esc(t('paperType.agree'))}</button>` : '')}
      </article>`;
  }

  function html(view) {
    const catalogue = list(view && view.catalogue);
    const accepted = view && view.plausibility;
    const record = view && view.decision;
    const error = view && view.error ? `<div class="pt-error" role="alert">${esc(view.error)}</div>` : '';
    const note = notice ? `<p class="pt-notice" role="status">${esc(notice)}</p>` : '';
    if (!accepted) {
      return `${error}${note}<div class="pt-empty"><p>${esc(t('paperType.empty'))}</p>
        <button type="button" class="btn btn--sm" data-pt-action="go-plausibility">${esc(t('paperType.goPlausibility'))}</button></div>`;
    }
    const rows = new Map(list(record && record.scores).map((row) => [row.type, row]));
    const byId = new Map(catalogue.map((type) => [type.id, type]));
    const suggested = record && record.suggested ? byId.get(record.suggested) : null;
    const suggestion = suggested
      ? t('paperType.suggested', {
        type: typeName(suggested),
        variant: variantName(suggested, (rows.get(suggested.id) || {}).variant) || '—',
        confidence: t(CONFIDENCE_KEYS[record.confidence] || 'paperType.confidence.low'),
      })
      : t('paperType.noSuggestion');
    const agreedType = record && record.agreed ? byId.get(record.agreed) : null;
    const agreedLine = agreedType ? `<p class="pt-agreed">${esc(t('paperType.agreed', {
      type: typeName(agreedType), variant: variantName(agreedType, record.agreed_variant) || '—', by: record.agreed_by || '',
    }))}</p>` : '';
    const stale = record && record.agreed_stale ? `<p class="pt-error" role="alert">${esc(t('paperType.stale'))}</p>` : '';
    const idea = String(accepted.idea || '');
    return `${error}${note}<div class="pt-head">
        <p class="pt-idea"><strong>${esc(t('paperType.idea'))}</strong> ${esc(idea.length > 400 ? `${idea.slice(0, 400)}…` : idea)}</p>
        <p class="panel__meta">${esc(t('paperType.acceptedBy', { by: accepted.accepted_by || '', at: accepted.accepted_at || '' }))}</p>
        <p class="pt-suggestion">${esc(suggestion)}</p>${agreedLine}${stale}
        <div class="pt-actions">
          <button type="button" class="btn btn--sm" data-pt-action="rescore">${esc(t('paperType.rescore'))}</button>
          <button type="button" class="btn btn--sm btn--primary" data-pt-action="discuss">${esc(t('paperType.discuss'))}</button>
        </div>
      </div>
      <div class="pt-grid">${catalogue.map((type) => card(type, rows.get(type.id), record)).join('')}</div>`;
  }

  function render(view) {
    lastView = view;
    const host = document.getElementById('paperTypePanel');
    if (host) host.innerHTML = html(view);
  }

  async function post(url, body) {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}) });
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok && data.ok !== false, data };
  }

  async function refreshPaperTypePanel() {
    try {
      const response = await fetch('/api/paper-type', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    } catch (err) {
      render({ catalogue: [], error: t('paperType.readFailed', { error: err.message || err }) });
    }
  }

  async function act(action, typeId) {
    if (action === 'go-plausibility') {
      window.navigateTab?.('pipeline');
      return;
    }
    if (action === 'discuss') {
      window.sendToCli?.('/paper-type', false, { kind: 'slash' });
      notice = t('paperType.discussSent');
      render(lastView);
      return;
    }
    if (action === 'agree-open') { openAgree = typeId; notice = ''; render(lastView); return; }
    if (action === 'agree-cancel') { openAgree = null; render(lastView); return; }
    if (action === 'rescore') {
      const { ok, data } = await post('/api/paper-type/score');
      notice = ok ? t('paperType.rescored') : t('paperType.refused', { error: data.error || data.code || '' });
      await refreshPaperTypePanel();
      return;
    }
    if (action === 'agree-confirm') {
      const by = String(document.getElementById('ptBy')?.value || '').trim();
      if (!by) { notice = t('paperType.agreeByFirst'); render(lastView); return; }
      const variant = document.getElementById('ptVariant')?.value || '';
      const rationale = String(document.getElementById('ptRationale')?.value || '').trim();
      const { ok, data } = await post('/api/paper-type/agree', { type: typeId, variant, by, rationale });
      if (ok) {
        const layout = String(data.layout || '');
        const kind = layout.startsWith('switch:') ? 'switch' : layout;
        notice = t(LAYOUT_KEYS[kind] || 'paperType.layout.current', { line: layout.slice('switch:'.length), type: typeId, by });
        openAgree = null;
      } else {
        notice = t('paperType.refused', { error: data.error || data.code || '' });
      }
      await refreshPaperTypePanel();
    }
  }

  document.addEventListener('click', (event) => {
    const el = event.target && event.target.closest && event.target.closest('[data-pt-action]');
    if (!el || !el.dataset || !el.dataset.ptAction) return;
    act(el.dataset.ptAction, el.dataset.ptType);
  });
  document.addEventListener('languagechange', () => { if (lastView) render(lastView); });

  window.PaperTypePanel = { html, render, act };
  window.refreshPaperTypePanel = refreshPaperTypePanel;
})();
