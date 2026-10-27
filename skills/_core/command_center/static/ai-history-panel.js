/* Historia con IA pane.
 *
 * GET /api/ai-history answers ai_history.build_ai_history(root, fases): per
 * phase its gate, colour (red: not run yet, orange: errors, rework or user
 * iterations, green: passed directly) and a timeline of decisions, revisions
 * and chat turns. The diagram draws the phases in order, each followed by its
 * gate; clicking a phase (or Enter on it) shows its summarised history and
 * the phase's artifacts. Every artifact path is a link that opens the file in
 * a window over the dashboard: text rendered by the Artefactos viewer's own
 * renderArtifactDoc (web view, with a raw source toggle), PDFs and images
 * embedded, HTML as its source. A modified click (Cmd/Ctrl) keeps the link's
 * new tab. Files come from /api/artifact, which serves only workspace files.
 * Every value is escaped before insertion.
 *
 * Public surface (window): refreshAiHistoryPanel(), AiHistoryPanel.render(view).
 */
(function () {
  'use strict';

  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const list = (v) => (Array.isArray(v) ? v : []);

  const COLOR_LABELS = {
    green: 'Pasó de forma directa',
    orange: 'Errores, refactorizaciones o iteraciones',
    red: 'Falta por ejecutar',
  };
  const KIND_LABELS = {
    command: 'Comando', user_message: 'Operador', agent_reply: 'Agente', error: 'Error',
    revision: 'Revisión', revision_receipt: 'Edición', lifecycle_transition: 'Transición',
    submitted: 'Envío remoto', returned: 'Retorno remoto', errored: 'Error remoto',
    declaration: 'Declaración', fact_resolved: 'Hecho resuelto', fact_declined: 'Hecho rechazado',
  };

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
    + ` data-artifact="${esc(path)}" title="Abrir ${esc(path)}">${esc(text ?? path)}</a>`;
  const kb = (bytes) => `${(Math.max(0, Number(bytes) || 0) / 1024).toFixed(1)} KB`;

  let lastView = { phases: [] };
  let selected = null;

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
      parts.push(`<g class="aih-gate aih--${gc}"><title>${esc(phase.gate)}: ${esc(COLOR_LABELS[gc])}</title>`
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
        + ` role="button" tabindex="0" aria-label="${esc(phase.id)} ${esc(phase.label)}: ${esc(COLOR_LABELS[phase.color])}">`
        + `<rect x="${p.x}" y="${p.y}" width="${BOX_W}" height="${BOX_H}" rx="8"/>`
        + `<text x="${p.x + 10}" y="${p.y + 20}" class="aih-box__id">${esc(phase.id)}</text>`
        + `<text x="${p.x + 10}" y="${p.y + 38}" class="aih-box__label">${esc(clip(phase.label, 22))}</text>`
        + `<title>${esc(phase.name || phase.label)}</title>`
        + `<text x="${p.x + 10}" y="${p.y + 55}" class="aih-box__meta">${events} evento(s) · ${esc(phase.status)}</text>`
        + '</g>');
    });
    return `<svg class="aih-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Fases y compuertas del flujo">`
      + '<defs><marker id="aihArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
      + '<path d="M0,0 L10,5 L0,10 z" class="aih-arrow"/></marker></defs>'
      + parts.join('') + '</svg>';
  }

  function stamp(ts) {
    if (!ts) return 'sin fecha';
    const d = new Date(ts);
    return Number.isNaN(d.getTime()) ? esc(ts) : d.toLocaleString();
  }

  function detail(phase) {
    if (!phase) {
      return '<p class="aih-hint">Haz clic en una fase para ver su historial resumido.</p>';
    }
    const c = phase.counts || {};
    const chips = [
      ['Comandos', c.commands], ['Iteraciones', c.user_messages], ['Decisiones', c.decisions],
      ['Revisiones', c.revisions], ['Errores', c.errors],
    ].map(([k, v]) => `<span class="badge">${esc(k)}: ${Number(v) || 0}</span>`).join(' ');
    const events = list(phase.events).slice().reverse();
    const shown = events.length < (Number(phase.total_events) || 0)
      ? `<p class="aih-hint">Se muestran los ${events.length} eventos más recientes de ${esc(phase.total_events)}.</p>` : '';
    const items = events.length
      ? '<ol class="aih-timeline">' + events.map((e) => `<li class="aih-ev aih-ev--${esc(e.kind)}">`
        + `<span class="aih-ev__kind">${esc(KIND_LABELS[e.kind] || e.kind)}</span>`
        + `<span class="aih-ev__when">${stamp(e.ts)} · ${esc(e.actor || e.source)}</span>`
        + `<div class="aih-ev__text">${esc(e.summary)}</div>`
        + (e.path ? `<div class="aih-ev__ref">📄 ${fileLink(e.path)}${e.ref && e.ref !== e.path ? ` <code>${esc(e.ref.slice(e.path.length))}</code>` : ''}</div>`
          : e.ref ? `<code class="aih-ev__ref">${esc(e.ref)}</code>` : '')
        + '</li>').join('') + '</ol>'
      : '<p class="aih-hint">Sin interacciones registradas para esta fase.</p>';
    return `<div class="aih-detail__head"><strong>${esc(phase.name || phase.label)}</strong>`
      + ` <span class="badge aih-badge--${esc(phase.color)}">${esc(COLOR_LABELS[phase.color])}</span></div>`
      + `<p class="aih-detail__meta">Compuerta <code>${esc(phase.gate)}</code> · Agente: ${esc(phase.agent || '—')}</p>`
      + `<p class="aih-detail__meta">${list(phase.reasons).map(esc).join(' · ')}</p>`
      + `<div class="aih-chips">${chips}</div>${artifacts(phase)}`
      + `<h4 class="aih-section">Interacciones</h4>${shown}${items}`;
  }

  function artifacts(phase) {
    const files = list(phase.artifacts);
    if (!files.length) {
      return '<h4 class="aih-section">Artefactos de la fase</h4><p class="aih-hint">Sin artefactos en disco todavía.</p>';
    }
    return `<h4 class="aih-section">Artefactos de la fase (${files.length})</h4><ul class="aih-files">`
      + files.map((a) => `<li>📄 ${fileLink(a.path)} <span class="aih-ev__when">${esc(a.label)} · ${kb(a.size)}`
        + ` · ${a.mtime ? new Date(a.mtime).toLocaleString() : ''}</span></li>`).join('')
      + '</ul>';
  }

  // A text artifact opens in the Artefactos viewer; modified clicks and
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
      + '<button type="button" class="btn aih-modal__mode" data-mode="web">✨ Vista web</button>'
      + '<button type="button" class="btn aih-modal__mode" data-mode="raw">📝 Código fuente</button>'
      + '<button type="button" class="btn" data-action="artifacts" title="Abrir en la pestaña Artefactos">📂 Artefactos</button>'
      + '<a class="btn" data-action="tab" target="_blank" rel="noopener" title="Abrir en una pestaña nueva">↗</a>'
      + '<button type="button" class="btn aih-modal__close" data-close="1" aria-label="Cerrar">✕</button>'
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
    document.addEventListener('keydown', (ev) => {
      if (!modal.hidden && ev.key === 'Escape') closeArtifact();
    });
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
    modal.querySelector('.aih-modal__meta').textContent = `Ruta: ${path}`;
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
      body.innerHTML = `<p class="aih-hint">Este tipo de archivo no se puede previsualizar aquí. Ábrelo en una pestaña nueva con ↗.</p>`;
      return;
    }
    body.innerHTML = '<p class="aih-hint">Cargando artefacto…</p>';
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      let text = await res.text();
      const size = text.length;
      const cut = size > TEXT_MAX_BYTES;
      if (cut) text = text.slice(0, TEXT_MAX_BYTES);
      if (loaded.path !== path) return;
      modal.querySelector('.aih-modal__meta').textContent = `Ruta: ${path} · ${kb(size)} · `
        + `${text.split('\n').length} líneas${cut ? ' · se muestra el inicio' : ''}`;
      loaded = { path, text };
      if (cut) viewMode = 'raw';
      renderText();
    } catch (err) {
      body.innerHTML = `<p class="aih-hint">No se pudo abrir el artefacto: ${esc(err.message)}</p>`;
    }
  }

  function legend() {
    return '<div class="aih-legend">' + ['green', 'orange', 'red']
      .map((c) => `<span><i class="aih-dot aih--${c}"></i>${esc(COLOR_LABELS[c])}</span>`).join('')
      + '<span><i class="aih-dot aih-dot--gate"></i>Compuerta</span></div>';
  }

  function sourcesNote(view) {
    const chats = (view.sources || {}).chats || {};
    const names = { 'claude-code': 'Claude Code', pi: 'Pi', opencode: 'OpenCode', antigravity: 'Antigravity' };
    const parts = Object.entries(chats).map(([key, info]) => {
      const s = info || {};
      const state = s.status === 'ok' ? `${Number(s.sessions) || 0} sesión(es)`
        : s.status === 'unsupported' ? 'no legible' : s.status === 'absent' ? 'sin sesiones' : 'error de lectura';
      return `<span title="${esc(s.detail || '')}">${esc(names[key] || key)}: ${esc(state)}</span>`;
    });
    return `<p class="aih-hint">${esc(view.note || '')}${parts.length ? ` Chats — ${parts.join(' · ')}.` : ''}</p>`;
  }

  function render(view) {
    lastView = view && typeof view === 'object' ? view : { phases: [] };
    const host = document.getElementById('aiHistoryPanel');
    if (!host) return;
    const phases = list(lastView.phases);
    if (!phases.length) {
      host.innerHTML = '<p class="aih-hint">No hay fases que mostrar todavía.</p>';
      return;
    }
    const current = phases.find((p) => p.stage_id === selected) || null;
    host.innerHTML = legend() + `<div class="aih-diagram">${diagram(phases)}</div>`
      + `<div class="aih-detail" aria-live="polite">${detail(current)}</div>` + sourcesNote(lastView);
    host.querySelector('.aih-detail')?.addEventListener('click', openArtifact);
    host.querySelectorAll('.aih-box').forEach((box) => {
      const pick = () => {
        selected = box.getAttribute('data-stage');
        render(lastView);
        host.querySelector('.aih-detail')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      };
      box.addEventListener('click', pick);
      box.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(); }
      });
    });
  }

  async function refresh() {
    const host = document.getElementById('aiHistoryPanel');
    if (!host) return;
    try {
      const res = await fetch('/api/ai-history', { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      render(await res.json());
    } catch (err) {
      host.innerHTML = `<p class="aih-hint">No se pudo cargar la historia: ${esc(err.message)}</p>`;
    }
  }

  window.AiHistoryPanel = { render, showArtifact };
  window.refreshAiHistoryPanel = refresh;
})();
