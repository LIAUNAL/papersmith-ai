/* AI History pane.
 *
 * GET /api/ai-history answers ai_history.build_ai_history(root, fases): per
 * phase its gate, colour (red: not run yet, orange: errors, rework or user
 * iterations, green: passed directly) and a timeline of decisions, revisions
 * and chat turns. The diagram draws the phases in order, each followed by its
 * gate; clicking a phase (or Enter on it) shows its summarised history and
 * the phase's artifacts. Every artifact path is a link that opens the file in
 * a window over the dashboard: text rendered by the Artifacts viewer's own
 * renderArtifactDoc (web view, with a raw source toggle), PDFs and images
 * embedded, HTML as its source. A modified click (Cmd/Ctrl) keeps the link's
 * new tab. Files come from /api/artifact, which serves only workspace files.
 *
 * Decisions: every phase also carries its operator rounds (an operator turn
 * and what answered it), each classified as success, rework, iteration or
 * pending. A strip above the diagram totals them and lists the phases still
 * waiting on a decision; the selected phase draws them as a decision graph
 * (a chain of rounds, with a loop back over every round that needed rework).
 * Clicking a round highlights its events in the timeline, and the timeline
 * shows only the main interactions (operator turns, the replies that answer
 * them, errors) unless the operator asks for everything.
 * Every value is escaped before insertion.
 *
 * Public surface (window): refreshAiHistoryPanel(), AiHistoryPanel.render(view).
 */
(function () {
  'use strict';

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  // Phase ids are the stable "Fase N"; this is how a person reads one.
  const phaseName = (id) => {
    const match = /^Fase (\d+)$/.exec(String(id || ''));
    return match ? t('phases.number', { n: match[1] }) : String(id || '');
  };
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const list = (v) => (Array.isArray(v) ? v : []);

  // Labels by machine value; an unknown value shows as itself.
  const labelOf = (prefix, value) => (window.i18n && window.i18n.has(`${prefix}.${value}`) ? t(`${prefix}.${value}`) : String(value ?? ''));
  const colorLabel = (c) => labelOf('aih.color', c);
  const kindLabel = (kind) => labelOf('aih.kind', kind);
  const outcomeLabel = (o) => labelOf('aih.outcome', o);
  const OUTCOME_GLYPHS = { success: '✓', rework: '↺', iteration: '⋯', pending: '?' };
  const OUTCOMES = Object.keys(OUTCOME_GLYPHS);

  const PER_ROW = 4;
  const BOX_W = 190, BOX_H = 64, GATE = 26, GAP_X = 120, GAP_Y = 64, PAD = 16;
  const clip = (v, n) => (String(v ?? '').length > n ? `${String(v).slice(0, n - 1)}…` : String(v ?? ''));

  // How the window shows a file, by extension.
  const WEB_EXT = /\.(md|markdown|txt|json|tex|bib|ya?ml|toml|csv|tsv|log|ini|cfg)$/i;
  const SOURCE_EXT = /\.(jsonl|py|ts|js|mjs|sh|r|ipynb|html?|xml|sty|cls|lock)$/i;
  const PDF_EXT = /\.pdf$/i;
  const IMAGE_EXT = /\.(png|jpe?g|gif|webp|svg)$/i;
  const TEXT_MAX_BYTES = 1536 * 1024;
  const rawUrl = (path) => `/api/artifact?file=${encodeURIComponent(path)}`;
  const fileLink = (path, text) => `<a class="aih-file" href="${esc(rawUrl(path))}" target="_blank" rel="noopener"`
    + ` data-artifact="${esc(path)}" title="${esc(t('aih.open', { path }))}">${esc(text ?? path)}</a>`;
  const kb = (bytes) => `${(Math.max(0, Number(bytes) || 0) / 1024).toFixed(1)} KB`;

  let lastView = { phases: [] };
  let selected = null;
  let selectedRound = null;
  let mainOnly = true;

  function layout(n) {
    const slot = BOX_W + GAP_X;
    return Array.from({ length: n }, (_, i) => {
      const row = Math.floor(i / PER_ROW);
      const col = row % 2 === 0 ? i % PER_ROW : PER_ROW - 1 - (i % PER_ROW);
      return { x: PAD + col * slot, y: PAD + row * (BOX_H + GAP_Y), row, col };
    });
  }

  function gateColor(phase) {
    if (phase.status !== 'PASS') return 'red';
    return phase.color === 'orange' ? 'orange' : 'green';
  }

  function diagram(phases) {
    const pos = layout(phases.length);
    const rows = Math.ceil(phases.length / PER_ROW) || 1;
    const width = PAD * 2 + PER_ROW * BOX_W + (PER_ROW - 1) * GAP_X;
    const height = PAD * 2 + rows * BOX_H + (rows - 1) * GAP_Y;
    const parts = [];
    phases.forEach((phase, i) => {
      const p = pos[i];
      const next = pos[i + 1];
      const gc = gateColor(phase);
      // The gate sits on the way out of the phase, toward the next one.
      let gx, gy, line = '', vertical = false;
      if (!next) {
        // The last phase's gate closes the flow, past the box along its row.
        const dir = p.row % 2 === 0 ? 1 : -1;
        gx = dir > 0 ? p.x + BOX_W + GAP_X / 2 : p.x - GAP_X / 2;
        gy = p.y + BOX_H / 2;
        line = `<line class="aih-edge" x1="${dir > 0 ? p.x + BOX_W : p.x}" y1="${gy}" x2="${gx - dir * GATE / 2}" y2="${gy}"/>`;
      } else if (next.row === p.row) {
        const dir = next.col > p.col ? 1 : -1;
        gx = dir > 0 ? p.x + BOX_W + GAP_X / 2 : p.x - GAP_X / 2;
        gy = p.y + BOX_H / 2;
        const x1 = dir > 0 ? p.x + BOX_W : p.x;
        const x2 = dir > 0 ? next.x : next.x + BOX_W;
        line = `<line class="aih-edge" x1="${x1}" y1="${gy}" x2="${x2}" y2="${gy}" marker-end="url(#aihArrow)"/>`;
      } else {
        gx = p.x + BOX_W / 2;
        gy = p.y + BOX_H + GAP_Y / 2;
        vertical = true;
        line = `<line class="aih-edge" x1="${gx}" y1="${p.y + BOX_H}" x2="${gx}" y2="${next.y}" marker-end="url(#aihArrow)"/>`;
      }
      parts.push(line);
      const h = GATE / 2;
      parts.push(`<g class="aih-gate aih--${gc}"><title>${esc(phase.gate)}: ${esc(colorLabel(gc))}</title>`
        + `<polygon points="${gx},${gy - h} ${gx + h},${gy} ${gx},${gy + h} ${gx - h},${gy}"/>`
        + (vertical
          ? `<text x="${gx + h + 6}" y="${gy + 3}" class="aih-gate__label aih-gate__label--side">${esc(phase.gate || '')}</text>`
          : `<text x="${gx}" y="${gy - h - 5}" class="aih-gate__label">${esc(phase.gate || '')}</text>`)
        + '</g>');
    });
    phases.forEach((phase, i) => {
      const p = pos[i];
      const active = selected === phase.stage_id ? ' aih-box--selected' : '';
      const events = Number(phase.total_events) || 0;
      parts.push(`<g class="aih-box aih--${esc(phase.color)}${active}" data-stage="${esc(phase.stage_id)}"`
        + ` role="button" tabindex="0" aria-label="${esc(phaseName(phase.id))} ${esc(phase.label)}: ${esc(colorLabel(phase.color))}">`
        + `<rect x="${p.x}" y="${p.y}" width="${BOX_W}" height="${BOX_H}" rx="8"/>`
        + `<text x="${p.x + 10}" y="${p.y + 20}" class="aih-box__id">${esc(phaseName(phase.id))}</text>`
        + `<text x="${p.x + 10}" y="${p.y + 38}" class="aih-box__label">${esc(clip(phase.label, 22))}</text>`
        + `<title>${esc(phase.name || phase.label)}</title>`
        + `<text x="${p.x + 10}" y="${p.y + 55}" class="aih-box__meta">${events} ev · ${summaryGlyphs(phase.decision_summary)}${esc(phase.status)}</text>`
        + '</g>');
    });
    return `<svg class="aih-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(t('aih.diagramLabel'))}">`
      + '<defs><marker id="aihArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
      + '<path d="M0,0 L10,5 L0,10 z" class="aih-arrow"/></marker></defs>'
      + parts.join('') + '</svg>';
  }

  function summaryGlyphs(summary) {
    const s = summary || {};
    const parts = OUTCOMES.filter((o) => Number(s[o]) > 0).map((o) => `${OUTCOME_GLYPHS[o]}${Number(s[o])}`);
    return parts.length ? `${parts.join(' ')} · ` : '';
  }

  // The rounds of one phase as a chain; a round that needed rework gets a
  // loop from the round after it back over it.
  const R = 15, STEP = 74, DG_PAD = 22;
  function decisionGraph(phase) {
    const rounds = list(phase.rounds);
    if (!rounds.length) return `<p class="aih-hint">${esc(t('aih.noRounds'))}</p>`;
    const cx = (i) => DG_PAD + R + i * STEP;
    const cy = DG_PAD + 30;
    const width = DG_PAD * 2 + R * 2 + (rounds.length - 1) * STEP;
    const parts = [];
    rounds.forEach((r, i) => {
      if (i + 1 < rounds.length) {
        parts.push(`<line class="aih-edge" x1="${cx(i) + R}" y1="${cy}" x2="${cx(i + 1) - R - 2}" y2="${cy}" marker-end="url(#aihArrow2)"/>`);
      }
      if (r.outcome === 'rework' && i + 1 < rounds.length) {
        const x1 = cx(i + 1), x0 = cx(i);
        parts.push(`<path class="aih-dg-loop" d="M${x1},${cy - R} C${x1},${cy - R - 28} ${x0},${cy - R - 28} ${x0},${cy - R - 2}"`
          + ` marker-end="url(#aihArrow2)"><title>${esc(t('aih.rework'))}</title></path>`);
      }
    });
    rounds.forEach((r, i) => {
      const on = selectedRound === r.n ? ' aih-dg-node--selected' : '';
      parts.push(`<g class="aih-dg-node aih-dg--${esc(r.outcome)}${on}" data-round="${esc(r.n)}" role="button" tabindex="0"`
        + ` aria-label="${esc(t('aih.round', { n: r.n }))}: ${esc(outcomeLabel(r.outcome))}">`
        + `<title>R${esc(r.n)} · ${esc(outcomeLabel(r.outcome))}: ${esc(r.prompt)}</title>`
        + (r.kind === 'decision'
          ? `<rect x="${cx(i) - R}" y="${cy - R}" width="${R * 2}" height="${R * 2}" rx="4"/>`
          : `<circle cx="${cx(i)}" cy="${cy}" r="${R}"/>`)
        + `<text x="${cx(i)}" y="${cy + 4}" class="aih-dg-glyph">${esc(OUTCOME_GLYPHS[r.outcome] || '')}</text>`
        + `<text x="${cx(i)}" y="${cy + R + 14}" class="aih-dg-label">R${esc(r.n)}</text></g>`);
    });
    const more = (Number(phase.total_rounds) || 0) > rounds.length
      ? `<p class="aih-hint">${esc(t('aih.recentRounds', { n: rounds.length, total: phase.total_rounds }))}</p>` : '';
    return `${more}<div class="aih-dgraph-wrap"><svg class="aih-dgraph" width="${width}" height="${cy + R + 24}"`
      + ` viewBox="0 0 ${width} ${cy + R + 24}" role="group" aria-label="${esc(t('aih.decisionGraphLabel'))}">`
      + '<defs><marker id="aihArrow2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
      + '<path d="M0,0 L10,5 L0,10 z" class="aih-arrow"/></marker></defs>'
      + parts.join('') + '</svg></div>';
  }

  function roundCard(phase) {
    const r = list(phase.rounds).find((x) => x.n === selectedRound);
    if (!r) return `<p class="aih-hint">${esc(t('aih.pickRound'))}</p>`;
    const decision = r.kind === 'decision';
    return `<div class="aih-round aih-round--${esc(r.outcome)}">`
      + `<div><strong>${esc(t('aih.round', { n: r.n }))}</strong> <span class="badge aih-dgbadge--${esc(r.outcome)}">`
      + `${esc(OUTCOME_GLYPHS[r.outcome] || '')} ${esc(outcomeLabel(r.outcome))}</span>`
      + ` <span class="aih-ev__when">${stamp(r.ts)} · ${esc(r.reason)}</span></div>`
      + `<div class="aih-round__turn"><span class="aih-ev__kind">${esc(decision ? t('aih.decision') : t('aih.kind.user_message'))}</span>${esc(r.prompt)}</div>`
      + `<div class="aih-round__turn"><span class="aih-ev__kind">${esc(decision ? t('aih.result') : t('aih.ai'))}</span>`
      + `${r.reply ? esc(r.reply) : `<em>${esc(t('aih.noReply'))}</em>`}</div>`
      + '</div>';
  }

  function decisionStrip(view) {
    const totals = view.decision_summary || {};
    const chips = OUTCOMES.map((o) => `<span class="badge aih-dgbadge--${o}">${OUTCOME_GLYPHS[o]} ${esc(outcomeLabel(o))}: ${Number(totals[o]) || 0}</span>`).join(' ');
    const pending = list(view.pending).map((p) => `<button type="button" class="btn aih-pending" data-stage="${esc(p.stage_id)}"`
      + ` data-round="${esc(p.round)}" title="${esc(p.prompt)}">${esc(phaseName(p.id))} · R${esc(p.round)}</button>`).join(' ');
    return `<div class="aih-strip"><span class="aih-strip__title">${esc(t('aih.decisionsWithAi'))}</span> ${chips}`
      + (pending ? ` <span class="aih-strip__title">${esc(t('aih.pending'))}</span> ${pending}` : '') + '</div>';
  }

  function stamp(ts) {
    if (!ts) return esc(t('aih.noDate'));
    const d = new Date(ts);
    return Number.isNaN(d.getTime()) ? esc(ts) : d.toLocaleString();
  }

  function detail(phase) {
    if (!phase) {
      return `<p class="aih-hint">${esc(t('aih.pickPhase'))}</p>`;
    }
    const c = phase.counts || {};
    const chips = [
      [t('aih.count.commands'), c.commands], [t('aih.count.iterations'), c.user_messages], [t('aih.count.decisions'), c.decisions],
      [t('aih.count.revisions'), c.revisions], [t('aih.count.errors'), c.errors],
    ].map(([k, v]) => `<span class="badge">${esc(k)}: ${Number(v) || 0}</span>`).join(' ');
    const all = list(phase.events).slice().reverse();
    const events = mainOnly ? all.filter((e) => e.key) : all;
    const shown = all.length < (Number(phase.total_events) || 0)
      ? `<p class="aih-hint">${esc(t('aih.recentEvents', { n: all.length, total: phase.total_events }))}</p>` : '';
    const toggle = `<label class="aih-toggle"><input type="checkbox" data-main-only${mainOnly ? ' checked' : ''}>`
      + ` ${esc(t('aih.mainOnly', { n: all.filter((e) => e.key).length, total: all.length }))}</label>`;
    const items = events.length
      ? '<ol class="aih-timeline">' + events.map((e) => `<li class="aih-ev aih-ev--${esc(e.kind)}`
        + `${e.key ? ' aih-ev--key' : ''}${selectedRound !== null && e.round === selectedRound ? ' aih-ev--hl' : ''}"`
        + ` data-ev-round="${esc(e.round ?? '')}">`
        + (e.round ? `<span class="aih-ev__round" data-round="${esc(e.round)}" title="${esc(t('aih.round', { n: e.round }))}">R${esc(e.round)}</span>` : '')
        + `<span class="aih-ev__kind">${esc(kindLabel(e.kind))}</span>`
        + `<span class="aih-ev__when">${stamp(e.ts)} · ${esc(e.actor || e.source)}</span>`
        + `<div class="aih-ev__text">${esc(e.summary)}</div>`
        + (e.path ? `<div class="aih-ev__ref">📄 ${fileLink(e.path)}${e.ref && e.ref !== e.path ? ` <code>${esc(e.ref.slice(e.path.length))}</code>` : ''}</div>`
          : e.ref ? `<code class="aih-ev__ref">${esc(e.ref)}</code>` : '')
        + '</li>').join('') + '</ol>'
      : `<p class="aih-hint">${esc(t('aih.noInteractions'))}</p>`;
    return `<div class="aih-detail__head"><strong>${esc(phase.name || phase.label)}</strong>`
      + ` <span class="badge aih-badge--${esc(phase.color)}">${esc(colorLabel(phase.color))}</span></div>`
      + `<p class="aih-detail__meta">${esc(t('aih.gate'))} <code>${esc(phase.gate)}</code> · ${esc(t('aih.agent', { agent: phase.agent || '—' }))}</p>`
      + `<p class="aih-detail__meta">${list(phase.reasons).map(esc).join(' · ')}</p>`
      + `<div class="aih-chips">${chips}</div>`
      + `<h4 class="aih-section">${esc(t('aih.decisionGraph', { n: list(phase.rounds).length }))}</h4>`
      + `<div class="aih-chips">${summaryGlyphs(phase.decision_summary).replace(/ · $/, '') || '—'}</div>`
      + `${decisionGraph(phase)}${roundCard(phase)}${artifacts(phase)}`
      + `<h4 class="aih-section">${esc(t('aih.interactions'))}</h4>${toggle}${shown}${items}`;
  }

  function artifacts(phase) {
    const files = list(phase.artifacts);
    if (!files.length) {
      return `<h4 class="aih-section">${esc(t('aih.artifacts'))}</h4><p class="aih-hint">${esc(t('aih.noArtifacts'))}</p>`;
    }
    return `<h4 class="aih-section">${esc(t('aih.artifactsN', { n: files.length }))}</h4><ul class="aih-files">`
      + files.map((a) => `<li>📄 ${fileLink(a.path)} <span class="aih-ev__when">${esc(a.label)} · ${kb(a.size)}`
        + ` · ${a.mtime ? new Date(a.mtime).toLocaleString() : ''}</span></li>`).join('')
      + '</ul>';
  }

  // A text artifact opens in the Artifacts viewer; modified clicks and
  // binary files keep the link's own behaviour (a new tab).
  function openArtifact(ev) {
    const link = ev.target.closest('a[data-artifact]');
    if (!link) return;
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button !== 0) return;
    ev.preventDefault();
    showArtifact(link.getAttribute('data-artifact'), link);
  }

  // --- the artifact window ------------------------------------------------

  let modal = null;
  let keysBound = false;
  let returnFocus = null;
  let viewMode = 'web';
  let loaded = { path: '', text: null };

  function ensureModal() {
    if (modal) return modal;
    modal = document.createElement('div');
    modal.className = 'aih-modal';
    modal.hidden = true;
    modal.innerHTML = '<div class="aih-modal__backdrop" data-close="1"></div>'
      + '<section class="aih-modal__dialog panel" role="dialog" aria-modal="true" aria-labelledby="aihModalTitle">'
      + '<header class="aih-modal__head">'
      + '<div class="aih-modal__titles"><div id="aihModalTitle" class="panel__title"></div>'
      + '<div class="aih-modal__meta panel__meta"></div></div>'
      + '<div class="aih-modal__actions">'
      + `<button type="button" class="btn aih-modal__mode" data-mode="web">${esc(t('aih.modal.web'))}</button>`
      + `<button type="button" class="btn aih-modal__mode" data-mode="raw">${esc(t('aih.modal.raw'))}</button>`
      + `<button type="button" class="btn" data-action="artifacts" title="${esc(t('aih.modal.artifactsTitle'))}">${esc(t('aih.modal.artifacts'))}</button>`
      + `<a class="btn" data-action="tab" target="_blank" rel="noopener" title="${esc(t('aih.modal.newTab'))}">↗</a>`
      + `<button type="button" class="btn aih-modal__close" data-close="1" aria-label="${esc(t('aih.modal.close'))}">✕</button>`
      + '</div></header>'
      + '<div class="aih-modal__body"></div></section>';
    document.body.appendChild(modal);
    modal.addEventListener('click', (ev) => {
      if (ev.target.closest('[data-close]')) { closeArtifact(); return; }
      const mode = ev.target.closest('[data-mode]');
      if (mode) { viewMode = mode.getAttribute('data-mode'); renderText(); return; }
      if (ev.target.closest('[data-action="artifacts"]') && typeof window.loadArtifact === 'function') {
        const path = loaded.path;
        closeArtifact();
        window.navigateTab?.('artifacts');
        window.loadArtifact(path);
      }
    });
    if (!keysBound) {
      keysBound = true;
      document.addEventListener('keydown', (ev) => {
        if (modal && !modal.hidden && ev.key === 'Escape') closeArtifact();
      });
    }
    return modal;
  }

  function closeArtifact() {
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    document.body.classList.remove('aih-modal-open');
    modal.querySelector('.aih-modal__body').innerHTML = '';
    returnFocus?.focus?.();
  }

  function setModes(enabled) {
    modal.querySelectorAll('.aih-modal__mode').forEach((b) => {
      b.hidden = !enabled;
      b.classList.toggle('btn--primary', b.getAttribute('data-mode') === viewMode);
    });
  }

  function renderText() {
    const body = modal.querySelector('.aih-modal__body');
    const { path, text } = loaded;
    if (text === null) return;
    const web = WEB_EXT.test(path) && viewMode === 'web' && typeof window.renderArtifactDoc === 'function';
    setModes(WEB_EXT.test(path));
    body.innerHTML = web
      ? `<div class="artifact-web-article">${window.renderArtifactDoc(text, path)}</div>`
      : `<pre class="aih-modal__raw">${esc(text)}</pre>`;
    body.scrollTop = 0;
  }

  async function showArtifact(path, opener) {
    ensureModal();
    returnFocus = opener || document.activeElement;
    loaded = { path, text: null };
    viewMode = 'web';
    const url = rawUrl(path);
    modal.querySelector('#aihModalTitle').textContent = path.split('/').pop();
    modal.querySelector('.aih-modal__meta').textContent = t('artifacts.path', { path });
    modal.querySelector('[data-action="tab"]').setAttribute('href', url);
    const body = modal.querySelector('.aih-modal__body');
    setModes(false);
    modal.hidden = false;
    document.body.classList.add('aih-modal-open');
    modal.querySelector('.aih-modal__close').focus();
    if (PDF_EXT.test(path)) {
      body.innerHTML = `<iframe class="aih-modal__frame" src="${esc(url)}" title="${esc(path)}"></iframe>`;
      return;
    }
    if (IMAGE_EXT.test(path)) {
      body.innerHTML = `<div class="aih-modal__image"><img src="${esc(url)}" alt="${esc(path)}"></div>`;
      return;
    }
    if (!WEB_EXT.test(path) && !SOURCE_EXT.test(path) && /\.[a-z0-9]+$/i.test(path)) {
      body.innerHTML = `<p class="aih-hint">${esc(t('aih.noPreview'))}</p>`;
      return;
    }
    body.innerHTML = `<p class="aih-hint">${esc(t('aih.loadingArtifact'))}</p>`;
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      let text = await res.text();
      const size = text.length;
      const cut = size > TEXT_MAX_BYTES;
      if (cut) text = text.slice(0, TEXT_MAX_BYTES);
      if (loaded.path !== path) return;
      modal.querySelector('.aih-modal__meta').textContent = t(cut ? 'aih.metaCut' : 'aih.meta',
        { path, size: kb(size), lines: text.split('\n').length });
      loaded = { path, text };
      if (cut) viewMode = 'raw';
      renderText();
    } catch (err) {
      body.innerHTML = `<p class="aih-hint">${esc(t('aih.openFailed', { error: err.message }))}</p>`;
    }
  }

  function legend() {
    return '<div class="aih-legend">' + ['green', 'orange', 'red']
      .map((c) => `<span><i class="aih-dot aih--${c}"></i>${esc(colorLabel(c))}</span>`).join('')
      + `<span><i class="aih-dot aih-dot--gate"></i>${esc(t('aih.gate'))}</span>`
      + OUTCOMES.map((o) => `<span><b class="aih-dg-key aih-dg--${o}">${OUTCOME_GLYPHS[o]}</b>${esc(outcomeLabel(o))}</span>`).join('')
      + '</div>';
  }

  function sourcesNote(view) {
    const chats = (view.sources || {}).chats || {};
    const names = { 'claude-code': 'Claude Code', pi: 'Pi', opencode: 'OpenCode', antigravity: 'Antigravity' };
    const parts = Object.entries(chats).map(([key, info]) => {
      const s = info || {};
      const state = s.status === 'ok' ? t('aih.sessions', { n: Number(s.sessions) || 0 })
        : s.status === 'unsupported' ? t('aih.unreadable') : s.status === 'absent' ? t('aih.noSessions') : t('aih.readError');
      return `<span title="${esc(s.detail || '')}">${esc(names[key] || key)}: ${esc(state)}</span>`;
    });
    return `<p class="aih-hint">${esc(view.note || '')}${parts.length ? ` ${esc(t('aih.chats'))} — ${parts.join(' · ')}.` : ''}</p>`;
  }

  function render(view) {
    lastView = view && typeof view === 'object' ? view : { phases: [] };
    const host = document.getElementById('aiHistoryPanel');
    if (!host) return;
    const phases = list(lastView.phases);
    if (!phases.length) {
      host.innerHTML = `<p class="aih-hint">${esc(t('aih.noPhases'))}</p>`;
      return;
    }
    const current = phases.find((p) => p.stage_id === selected) || null;
    host.innerHTML = legend() + decisionStrip(lastView) + `<div class="aih-diagram">${diagram(phases)}</div>`
      + `<div class="aih-detail" aria-live="polite">${detail(current)}</div>` + sourcesNote(lastView);
    const detailEl = host.querySelector('.aih-detail');
    detailEl?.addEventListener('click', (ev) => {
      const round = ev.target.closest('[data-round]');
      if (round) { pickRound(Number(round.getAttribute('data-round'))); return; }
      openArtifact(ev);
    });
    detailEl?.addEventListener('change', (ev) => {
      if (ev.target.matches('[data-main-only]')) { mainOnly = ev.target.checked; render(lastView); }
    });
    detailEl?.querySelectorAll('.aih-dg-node').forEach((node) => node.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pickRound(Number(node.getAttribute('data-round'))); }
    }));
    const pick = (stage, round = null) => {
      if (selected !== stage) selectedRound = null;
      selected = stage;
      if (round !== null) selectedRound = round;
      render(lastView);
      host.querySelector(round !== null ? '.aih-round' : '.aih-detail')
        ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    };
    host.querySelectorAll('.aih-pending').forEach((btn) => btn.addEventListener('click',
      () => pick(btn.getAttribute('data-stage'), Number(btn.getAttribute('data-round')))));
    host.querySelectorAll('.aih-box').forEach((box) => {
      box.addEventListener('click', () => pick(box.getAttribute('data-stage')));
      box.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(box.getAttribute('data-stage')); }
      });
    });
  }

  // Selecting a round (again to clear it) highlights its events; the first
  // one scrolls into view, the rest stay where the timeline puts them.
  function pickRound(n) {
    selectedRound = selectedRound === n ? null : n;
    render(lastView);
    const host = document.getElementById('aiHistoryPanel');
    host?.querySelector('.aih-ev--hl')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    host?.querySelector(`.aih-dg-node[data-round="${selectedRound}"]`)?.focus({ preventScroll: true });
  }

  async function refresh() {
    const host = document.getElementById('aiHistoryPanel');
    if (!host) return;
    try {
      const res = await fetch('/api/ai-history', { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      render(await res.json());
    } catch (err) {
      host.innerHTML = `<p class="aih-hint">${esc(t('aih.loadFailed', { error: err.message }))}</p>`;
    }
  }

  // Labels and notes come from the server in the chosen language: fetch again
  // when the panel has been drawn.
  document.addEventListener('languagechange', () => {
    if (list(lastView.phases).length) refresh();
    // A closed window is rebuilt with the new labels the next time it opens.
    if (modal && modal.hidden) { modal.remove(); modal = null; }
  });

  window.AiHistoryPanel = { render, showArtifact };
  window.refreshAiHistoryPanel = refresh;
})();
