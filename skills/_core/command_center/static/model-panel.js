/* Model tab modules drawn from the workspace's own specification.
 *
 * GET /api/model answers `.papersmith/model_spec.json` when the workspace has
 * one, else a neutral specification named after `papersmith.yaml`. This file
 * renders its novelty pillars, hypotheses, concept-map layers and proof-of-
 * concept experiments; when a part is absent it says what produces it instead
 * of showing anybody else's content. Every value is escaped before insertion;
 * prose fields go through math-panel.js's richText, so $…$ compiles with KaTeX.
 *
 * Public surface (window): renderModelModules(spec).
 */
(function () {
  'use strict';

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
    if (!list.length) return empty('Los pilares de la novedad aparecen cuando la propuesta se delibera (proposals/).');
    return list.map((p, i) => {
      const c = colour(p.color, '#38bdf8');
      return `<div class="model-pillar-card" style="--tone: ${c}; border-top: 3px solid ${c};">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="badge tone-ink" style="font-weight: 700;">${esc(p.badge || 'PILAR')}</span>
          <span class="tone-ink" style="font-size: 0.75rem; font-weight: 700;">PILAR ${i + 1}</span>
        </div>
        <h3 style="font-size: 0.95rem; font-weight: 700; color: var(--text);">${rich(p.name)}</h3>
        <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.45;">${rich(p.summary)} ${rich(p.details)}</p>
      </div>`;
    }).join('');
  }

  function hypotheses(spec) {
    const list = ((spec.novelty || {}).hypotheses || []).filter((h) => h && (h.title || h.statement));
    if (!list.length) return empty('Hipótesis pendientes de deliberación (proposals/ y experiments/).');
    return list.map((h) => `<div class="model-hypothesis-card">
        <div style="display: flex; justify-content: space-between; gap: 0.5rem;">
          <strong>${esc(h.id || '')} ${rich(h.title || '')}</strong>
          ${h.status ? `<span class="badge">${esc(h.status)}</span>` : ''}
        </div>
        <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.45;">${rich(h.statement)}</p>
        ${h.evidence ? `<p style="font-size: 0.76rem; color: var(--text-muted);">${rich(h.evidence)}</p>` : ''}
      </div>`).join('');
  }

  function layers(spec) {
    const source = spec.concept_map || spec.conceptual_map || {};
    const list = (source.layers || []).filter(Boolean);
    if (!list.length) return empty('El mapa conceptual se construye durante la deliberación de la propuesta.');
    return list.map((layer, i) => {
      const c = colour(layer.color, '#38bdf8');
      const name = layer.name || layer.layer || `Capa ${i + 1}`;
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

  function renderModelModules(spec) {
    const put = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
    put('modelPillarGrid', pillars(spec || {}));
    put('modelHypothesisGrid', hypotheses(spec || {}));
    put('modelConceptLayers', layers(spec || {}));
  }

  window.renderModelModules = renderModelModules;
})();
