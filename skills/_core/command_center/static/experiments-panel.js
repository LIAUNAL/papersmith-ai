/* Experiments tab: proof of concept and full experiments, read from disk.
 *
 * GET /api/experiments answers experiments_view.get_experiments_view(root):
 * the latest experiments protocol (expected reports approved in
 * deliberation), every product folder under implementations/ with its
 * convergence histories, figures, tables, significance tests, pinned
 * artifacts and remote runs, the datasets registry (toy and full sets with
 * their license, qc and remote state), the remote-services table (one row
 * per service with its state and activating action), the local environment
 * (workspace micromamba env, each target .venv with its libraries and device),
 * the run options (per stage and host: availability, ±20% estimate from
 * Results/timing.json or "sin medir", reason and recommendation), plus a remote-accounts
 * readiness hint, the hyperparameter studies per product (Results/hpo/<study>/
 * summary.json: best parameters, importance bars, contour/importance/history
 * figures), the team table (one account per person and service) and the
 * Colab box (official CLI headless, official MCP interactive). Convergence is
 * always drawn (inline SVG); when nothing produces it yet, the empty state
 * says which file does. Every value is escaped before insertion.
 *
 * Public surface (window): refreshExperimentsPanel(), ExperimentsPanel.render(view).
 */
(function () {
  'use strict';

  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const empty = (text) => `<p class="exp-empty">${esc(text)}</p>`;
  const artifactUrl = (path) => `/api/artifact?path=${encodeURIComponent(path)}`;
  const PALETTE = ['#38bdf8', '#f59e0b', '#10b981', '#ef4444', '#a78bfa', '#f472b6', '#14b8a6', '#eab308',
    '#60a5fa', '#fb923c', '#4ade80', '#f87171'];
  const IMAGE_EXT = /\.(png|svg|jpe?g)$/i;
  const logCharts = new Set();
  let lastView = null;

  const fmt = (v, digits = 3) => {
    if (v === null || v === undefined || v === '') return '—';
    const n = Number(v);
    if (!Number.isFinite(n)) return esc(v);
    if (n !== 0 && (Math.abs(n) < 1e-3 || Math.abs(n) >= 1e5)) return n.toExponential(2);
    return String(Number(n.toFixed(digits)));
  };

  // ---------------------------------------------------------------- charts
  // loss and val_loss share one chart; so do acc and val_acc.
  const metricFamily = (name) => String(name).replace(/^(val|train|test|valid)[_-]/i, '');
  const isLossLike = (name) => /loss|error|mse|nll|cost/i.test(name);

  function chart(id, title, xKey, series) {
    const W = 520, H = 240, L = 52, R = 12, T = 14, B = 34;
    const useLog = logCharts.has(id) && series.every((s) => s.points.some((p) => p[1] > 0));
    const ty = (y) => (useLog ? Math.log10(y) : y);
    const pts = series.map((s) => s.points.filter((p) => !useLog || p[1] > 0));
    const all = pts.flat();
    if (!all.length) return '';
    let xMin = Math.min(...all.map((p) => p[0])), xMax = Math.max(...all.map((p) => p[0]));
    let yMin = Math.min(...all.map((p) => ty(p[1]))), yMax = Math.max(...all.map((p) => ty(p[1])));
    if (xMax === xMin) { xMax += 1; }
    if (yMax === yMin) { yMax += 1; yMin -= 1; }
    const sx = (x) => L + ((x - xMin) / (xMax - xMin)) * (W - L - R);
    const sy = (y) => T + (1 - (ty(y) - yMin) / (yMax - yMin)) * (H - T - B);
    const ticks = [0, 0.25, 0.5, 0.75, 1];
    const yTicks = ticks.map((f) => {
      const v = yMin + f * (yMax - yMin);
      const y = T + (1 - f) * (H - T - B);
      const label = useLog ? fmt(10 ** v) : fmt(v);
      return `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" class="exp-grid"/>`
        + `<text x="${L - 6}" y="${y + 3}" text-anchor="end">${label}</text>`;
    }).join('');
    const xTicks = ticks.map((f) => {
      const v = xMin + f * (xMax - xMin);
      return `<text x="${sx(v)}" y="${H - B + 14}" text-anchor="middle">${fmt(v, 1)}</text>`;
    }).join('');
    const lines = series.map((s, i) => {
      const colour = PALETTE[i % PALETTE.length];
      const d = pts[i].map((p) => `${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(' ');
      return `<polyline fill="none" stroke="${colour}" stroke-width="1.6" points="${d}"><title>${esc(s.label)}</title></polyline>`;
    }).join('');
    const legend = series.map((s, i) => `<span class="exp-legend__item"><i style="background:${PALETTE[i % PALETTE.length]}"></i>${esc(s.label)}</span>`).join('');
    const canLog = series.some((s) => isLossLike(s.name));
    const toggle = canLog
      ? `<button type="button" class="btn exp-log-toggle" data-exp-log="${esc(id)}" aria-pressed="${useLog}">${useLog ? 'Escala lineal' : 'Escala log'}</button>`
      : '';
    return `<figure class="exp-chart">
      <figcaption><strong>${esc(title)}</strong>${toggle}</figcaption>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}" class="exp-chart__svg">
        <g class="exp-axis">${yTicks}${xTicks}
          <line x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/><line x1="${L}" x2="${L}" y1="${T}" y2="${H - B}"/>
          <text x="${(L + W - R) / 2}" y="${H - 4}" text-anchor="middle">${esc(xKey)}</text>
        </g>${lines}
      </svg>
      <div class="exp-legend">${legend}</div>
    </figure>`;
  }

  function convergence(product) {
    const histories = product.convergence || [];
    if (!histories.length) {
      return empty('Sin curvas de convergencia todavía: las produce Results/history*.json|jsonl|csv '
        + '(o Results/shards/*/history*) con una columna epoch o step y métricas numéricas (loss, val_loss, acc…).');
    }
    return histories.map((h, hi) => {
      const families = new Map();
      (h.series || []).forEach((s) => {
        const key = metricFamily(s.name);
        if (!families.has(key)) families.set(key, []);
        families.get(key).push({ ...s, label: s.group ? `${s.name} · ${s.group}` : s.name });
      });
      const charts = Array.from(families.entries()).map(([family, list]) => (
        chart(`${product.path}|${hi}|${family}`, `${family} — ${h.file.split('/').pop()}`, h.x_key, list)
      )).join('');
      return `<div class="exp-chart-group"><div class="exp-file">${esc(h.file)}</div><div class="exp-chart-grid">${charts}</div></div>`;
    }).join('');
  }

  // ---------------------------------------------------------------- artifacts
  function artifact(path) {
    const name = String(path).split('/').pop();
    if (IMAGE_EXT.test(path)) {
      return `<a class="exp-figure" href="${artifactUrl(path)}" target="_blank" rel="noopener">
        <img src="${artifactUrl(path)}" alt="${esc(name)}" loading="lazy"><span>${esc(name)}</span></a>`;
    }
    return `<a class="exp-figure exp-figure--file" href="${artifactUrl(path)}" target="_blank" rel="noopener">
      <span class="badge badge--info">${esc((name.split('.').pop() || '').toUpperCase())}</span><span>${esc(name)}</span></a>`;
  }

  function table(headers, rows, opts = {}) {
    const head = headers.map((h) => `<th>${esc(h)}</th>`).join('');
    const body = rows.map((r) => `<tr>${headers.map((_, i) => {
      const cell = r[i];
      return cell === '' || cell === undefined
        ? `<td class="exp-pending">${opts.pending ? 'pendiente' : ''}</td>`
        : `<td>${esc(cell)}</td>`;
    }).join('')}</tr>`).join('');
    return `<div class="table-responsive"><table class="table exp-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function tables(product) {
    const list = product.tables || [];
    if (!list.length) return '';
    return `<h4 class="exp-h4">Tablas</h4>` + list.map((t) => `<div class="exp-file">${esc(t.path)}</div>${table(t.headers || [], t.rows || [])}`).join('');
  }

  function significance(product) {
    const rows = product.significance || [];
    if (!rows.length) {
      return `<h4 class="exp-h4">Significancia estadística</h4>`
        + empty('Sin pruebas todavía: las produce Results/significance*.json (comparison, test, statistic, p_value, p_adjusted, correction, effect_size, ci_low, ci_high, n, alpha).');
    }
    const body = rows.map((r) => {
      const alpha = Number.isFinite(Number(r.alpha)) && r.alpha !== null ? Number(r.alpha) : 0.05;
      const p = r.p_adjusted ?? r.p_value;
      const sig = p !== null && p !== undefined && Number(p) < alpha;
      const ci = (r.ci_low ?? null) !== null || (r.ci_high ?? null) !== null ? `[${fmt(r.ci_low)}, ${fmt(r.ci_high)}]` : '—';
      const effect = r.effect_size === null || r.effect_size === undefined ? '—'
        : `${fmt(r.effect_size)}${r.effect_size_name ? ` <small>(${esc(r.effect_size_name)})</small>` : ''}`;
      return `<tr class="${sig ? 'exp-sig' : ''}">
        <td>${esc(r.test || '—')}</td><td>${esc(r.comparison || '—')}</td><td>${fmt(r.statistic)}</td>
        <td>${fmt(r.p_value)}</td><td>${fmt(r.p_adjusted)}${r.correction ? ` <small>${esc(r.correction)}</small>` : ''}</td>
        <td>${effect}</td><td>${ci}</td><td>${fmt(r.n, 0)}</td>
        <td>${sig ? `<span class="badge badge--ok">p &lt; ${fmt(alpha)}</span>` : `<span class="badge">n.s.</span>`}</td></tr>`;
    }).join('');
    return `<h4 class="exp-h4">Significancia estadística</h4><div class="table-responsive"><table class="table exp-table">
      <thead><tr><th>Prueba</th><th>Comparación</th><th>Estadístico</th><th>p</th><th>p ajustado</th><th>Tamaño del efecto</th><th>IC</th><th>n</th><th></th></tr></thead>
      <tbody>${body}</tbody></table></div>`;
  }

  // ------------------------------------------------- hyperparameter search
  const EVALUATOR_LABEL = { fanova: 'fANOVA', 'ped-anova': 'PED-ANOVA', 'mean-decrease-impurity': 'Mean Decrease Impurity' };
  const DIRECTION_LABEL = { maximize: 'maximizar', minimize: 'minimizar' };
  const HPO_FIGURE_LABEL = { contour: 'Contornos', importance: 'Importancia', history: 'Historia de la optimización' };
  const evaluatorName = (name) => EVALUATOR_LABEL[name] || name || 'evaluador sin declarar';

  function importanceBars(imp) {
    const entries = Object.entries((imp && imp.values) || {})
      .filter(([, v]) => Number.isFinite(Number(v))).sort((a, b) => Number(b[1]) - Number(a[1]));
    if (!entries.length) return '';
    const top = Math.max(...entries.map(([, v]) => Number(v)), 1e-12);
    const rows = entries.map(([name, v]) => {
      const width = Math.max(0, Math.min(100, (Number(v) / top) * 100)).toFixed(1);
      return `<div class="exp-hpo-bar"><span class="exp-hpo-bar__name">${esc(name)}</span>
        <span class="exp-hpo-bar__track"><i style="width:${width}%"></i></span><span class="exp-hpo-bar__value">${fmt(v)}</span></div>`;
    }).join('');
    return `<div class="exp-hpo-importance"><div class="exp-file">Importancia (${esc(evaluatorName(imp.evaluator))})</div>${rows}</div>`;
  }

  function hpoFigures(h) {
    const figures = h.figures || {};
    const notes = h.notes || [];
    const cells = Object.keys(HPO_FIGURE_LABEL).map((key) => {
      const path = figures[key];
      if (path) return `<div class="exp-hpo-figure"><div class="exp-file">${esc(HPO_FIGURE_LABEL[key])}</div>${artifact(path)}</div>`;
      const note = notes.find((n) => String(n).toLowerCase().includes(key)) || 'sin figura';
      return `<div class="exp-hpo-figure"><div class="exp-file">${esc(HPO_FIGURE_LABEL[key])}</div>${empty(note)}</div>`;
    }).join('');
    const extra = notes.length ? `<ul class="exp-hpo-notes">${notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul>` : '';
    return `<div class="exp-gallery exp-hpo-gallery">${cells}</div>${extra}`;
  }

  function hpo(product) {
    const list = product.hpo || [];
    if (!list.length) return '';
    const body = list.map((h) => {
      const obj = h.objective || {};
      const params = Object.entries(h.bestParams || {}).map(([k, v]) => `<code>${esc(k)}=${esc(typeof v === 'number' ? fmt(v, 6) : v)}</code>`).join(' ') || '—';
      const best = h.bestValue === null || h.bestValue === undefined ? '—'
        : `${fmt(h.bestValue, 4)} <small>${esc(obj.metric || '')}${obj.direction ? ` · ${esc(DIRECTION_LABEL[obj.direction] || obj.direction)}` : ''}</small>`;
      return `<tr><td><code>${esc(h.study)}</code></td><td>${esc(h.arm || '—')}</td><td>${esc(h.fold ?? '—')}</td>
        <td>${esc(h.complete ?? '—')} / ${esc(h.pruned ?? '—')}${h.failed ? ` <small>(${esc(h.failed)} fallidos)</small>` : ''}${h.nTrials ? ` <small>de ${esc(h.nTrials)}</small>` : ''}</td>
        <td>${best}</td><td>${params}</td></tr>`;
    }).join('');
    const details = list.map((h) => `<details class="exp-hpo-study"><summary><code>${esc(h.study)}</code> · ${esc(h.file)}</summary>
      ${importanceBars(h.importance)}${h.importanceCheck ? importanceBars(h.importanceCheck) : ''}
      ${hpoFigures(h)}</details>`).join('');
    return `<h4 class="exp-h4">Búsqueda de hiperparámetros (Optuna)</h4>
      <div class="table-responsive"><table class="table exp-table">
      <thead><tr><th>Estudio</th><th>Brazo</th><th>Fold</th><th>Trials completos / podados</th><th>Mejor valor</th><th>Mejores parámetros</th></tr></thead>
      <tbody>${body}</tbody></table></div>${details}`;
  }

  const STATE_LABEL = { submitted: ['badge--info', 'enviado'], returned: ['badge--ok', 'retornado'], errored: ['badge--bad', 'con error'] };
  function runs(product) {
    const r = product.runs || {};
    if (!r.count) return '<span class="badge">sin ejecuciones remotas</span>';
    const chips = Object.entries(r.by_state || {}).map(([state, n]) => {
      const [cls, label] = STATE_LABEL[state] || ['', state];
      return `<span class="badge ${cls}">${esc(label)}: ${esc(n)}</span>`;
    }).join(' ');
    const latest = (r.latest || []).map((e) => {
      const [cls, label] = STATE_LABEL[e.state] || ['', e.state];
      return `<li><span class="badge ${cls}">${esc(label)}</span> <code>${esc(e.entrypoint)}</code>
        ${e.worker ? `· ${esc(e.worker)}` : ''} ${e.ts ? `· <small>${esc(e.ts)}</small>` : ''}
        ${e.reason ? `<div class="exp-reason">${esc(e.reason)}</div>` : ''}</li>`;
    }).join('');
    return `${chips}<details class="exp-runs"><summary>Últimas ejecuciones (${esc(r.count)})</summary><ul>${latest}</ul></details>`;
  }

  // ------------------------------------------------------------ diagrams
  // One figure per approval, drawn by skills/experiment-diagrams: the proof of
  // concept first, then the full experiments. The operator verifies each one here.
  const DIAGRAM_TITLES = {
    poc: 'Diagrama de la prueba de concepto',
    experiments: 'Diagrama de los experimentos completos',
  };

  // validation: absent (not drawn), pending, validated, stale (drawn again
  // after it was validated). Nothing is launched until each one is validated.
  const DIAGRAM_STATES = {
    absent: ['PENDIENTE', 'badge--warn'],
    pending: ['POR VERIFICAR', 'badge--warn'],
    stale: ['CAMBIÓ: VERIFICAR DE NUEVO', 'badge--warn'],
    validated: ['VALIDADO', 'badge--ok'],
  };

  function diagrams(p) {
    const list = p.diagrams || [];
    if (!list.length) return '';
    const items = list.map((d) => {
      const title = DIAGRAM_TITLES[d.kind] || d.kind;
      const files = [d.png, d.pdf].filter(Boolean);
      const state = d.png ? (d.validation || 'pending') : 'absent';
      const [label, tone] = DIAGRAM_STATES[state] || DIAGRAM_STATES.pending;
      const validate = state === 'pending' || state === 'stale'
        ? `<button type="button" class="btn" data-diagram-validate="${esc(d.kind)}" data-diagram-repo="${esc(p.repo || '')}"
            data-diagram-name="${esc(p.name || '')}">Validar diagrama</button>` : '';
      const body = d.png
        ? `<div class="exp-gallery">${files.map(artifact).join('')}</div>
           <p class="exp-intro">Revísalo antes de lanzar: <code>submit</code> se niega mientras no esté validado.
            Si no refleja lo aprobado en ${esc(d.marker || '')}, pide al agente que lo corrija con
            <code>${esc(d.slash || '')}</code> o regenéralo aquí.</p>
           <div class="exp-chips">${validate}${cliButton(d.command || '', 'Regenerar diagrama')}</div>`
        : `<p class="exp-intro">Aprobado en ${esc(d.marker || '')}; el diagrama aún no existe. El agente lo dibuja con
            <code>${esc(d.slash || '')}</code>, o genera un borrador aquí y revísalo.</p>
           <div class="exp-chips">${cliButton(d.command || '', 'Generar diagrama')}</div>`;
      return `<div class="exp-diagram"><div class="exp-file">${esc(title)}
        <span class="badge ${tone}">${esc(label)}</span></div>${body}</div>`;
    }).join('');
    return `<h4 class="exp-h4">Diagramas para verificar</h4>${items}`;
  }

  async function validateDiagram(button) {
    button.disabled = true;
    try {
      const response = await fetch('/api/experiments/diagrams/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo: button.getAttribute('data-diagram-repo'),
          name: button.getAttribute('data-diagram-name'),
          kind: button.getAttribute('data-diagram-validate'),
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
    } catch (err) {
      button.disabled = false;
      button.textContent = `No se pudo validar: ${err.message}`;
      return;
    }
    refreshExperimentsPanel();
  }

  function product(p) {
    const pinned = p.pinned || [];
    const figures = (p.figures || []).filter((f) => !pinned.includes(f));
    const warnings = p.warnings || [];
    return `<article class="exp-product">
      <header class="exp-product__header">
        <div><strong>${esc(p.name)}</strong> <small class="exp-muted">${esc(p.path)}</small></div>
        <div class="exp-chips">${runs(p)}</div>
      </header>
      ${diagrams(p)}
      ${pinned.length ? `<h4 class="exp-h4">Artefactos aprobados en deliberación</h4><div class="exp-gallery">${pinned.map(artifact).join('')}</div>` : ''}
      <h4 class="exp-h4">Convergencia</h4>${convergence(p)}
      ${figures.length ? `<h4 class="exp-h4">Figuras</h4><div class="exp-gallery">${figures.map(artifact).join('')}</div>` : ''}
      ${hpo(p)}
      ${tables(p)}
      ${significance(p)}
      ${warnings.length ? `<details class="exp-warnings"><summary>${esc(warnings.length)} aviso(s) de lectura</summary><ul>${warnings.map((w) => `<li>${esc(w)}</li>`).join('')}</ul></details>` : ''}
    </article>`;
  }

  function group(title, intro, list, emptyText) {
    return `<section class="panel exp-section">
      <div class="panel__header"><div class="panel__title">${esc(title)}</div><span class="panel__meta">${esc(list.length)} producto(s)</span></div>
      <p class="exp-intro">${esc(intro)}</p>
      ${list.length ? list.map(product).join('') : empty(emptyText)}
    </section>`;
  }

  // ---------------------------------------------------------------- protocol
  function protocol(proto) {
    if (!proto) {
      return `<section class="panel exp-section"><div class="panel__header"><div class="panel__title">Protocolo experimental</div></div>
        ${empty('Sin protocolo todavía: /experimental-deliberation escribe experiments/experiments-<slug>-vNN.md.')}</section>`;
    }
    const exps = (proto.experiments || []).map((e) => {
      const reports = (e.expected_reports || []).map((r) => `<div class="exp-file">${esc(r.title)} <span class="badge badge--warn">PENDIENTE</span></div>${table(r.headers || [], r.rows || [], { pending: true })}`).join('')
        || empty('Este experimento no declara un reporte esperado.');
      return `<details class="exp-protocol-item">
        <summary><strong>${esc(e.id)}</strong> ${esc(e.title)} ${e.priority ? `<span class="badge badge--info">${esc(e.priority)}</span>` : ''}</summary>
        ${e.hypothesis ? `<p><strong>Hipótesis:</strong> ${esc(e.hypothesis)}</p>` : ''}
        ${e.success_criterion ? `<p><strong>Criterio de éxito:</strong> ${esc(e.success_criterion)}</p>` : ''}
        ${e.cost ? `<p><strong>Costo estimado:</strong> ${esc(e.cost)}</p>` : ''}
        ${reports}
      </details>`;
    }).join('');
    return `<section class="panel exp-section">
      <div class="panel__header"><div class="panel__title">Protocolo experimental</div><span class="panel__meta">${esc(proto.file)} · v${esc(String(proto.revision).padStart(2, '0'))}</span></div>
      ${proto.validation_scheme ? `<p class="exp-intro"><strong>Esquema de validación:</strong> ${esc(proto.validation_scheme)}</p>` : ''}
      <p class="exp-intro">Reportes esperados aprobados en deliberación: se llenan cuando la implementación experimental escribe sus resultados.</p>
      ${exps || empty('El protocolo no declara experimentos [exp:…].')}
    </section>`;
  }

  // ---------------------------------------------------------- MCP activation
  // The commands run in the dashboard's CLI assistant (window.sendToCli, shell
  // kind): the token is typed there into a hidden prompt, never into this page.
  // run=false types a template (placeholders such as <slug>) without pressing
  // Enter, so the person edits it in the terminal before running it.
  function cliButton(command, label, run = true) {
    return `<button type="button" class="btn" data-exp-cli="${esc(command)}"${run ? '' : ' data-exp-cli-run="0"'}>${esc(label)}</button>`;
  }

  function mcpActivation(state) {
    const st = state || {};
    const activate = st.activate || 'smith mcp kaggle activate';
    const check = st.status || 'smith mcp kaggle status';
    const env = st.environment || {};
    const envVar = st.env || 'KAGGLE_API_TOKEN';
    const tokenPath = env.token_path || st.token_path || '~/.kaggle/access_token';
    const sysLabel = { macos: 'macOS', linux: 'Linux', wsl: 'Windows (WSL)', windows: 'Windows' }[env.system] || 'desconocido';
    const badge = st.activated
      ? `<span class="badge badge--ok">activo (${st.source === 'env' ? `variable ${esc(st.env || 'KAGGLE_API_TOKEN')}` : 'token guardado'})</span>`
      : `<span class="badge badge--warn">${st.problem === 'insecure' ? 'token con permisos inseguros' : 'sin activar'}</span>`;
    const registered = (st.registered || []).length
      ? `registrado en ${(st.registered || []).map((f) => `<code>${esc(f)}</code>`).join(', ')}`
      : 'no registrado en este proyecto: ejecuta <code>smith upgrade</code>';
    return `<section class="panel exp-mcp" id="expMcpActivation">
      <h3 class="panel__title">Activar Kaggle por MCP</h3>
      <p class="exp-intro">Estado: ${badge} · servidor <code>kaggle</code> ${registered}.</p>
      ${env.system ? `<p class="exp-intro">Entorno detectado: <strong>${esc(sysLabel)}</strong> · shell <code>${esc(env.shell || 'sh')}</code>${env.user ? ` · usuario <code>${esc(env.user)}</code>` : ''}.</p>` : ''}
      ${env.note ? `<p class="exp-intro"><span class="badge badge--warn">${esc(sysLabel)}</span> ${esc(env.note)}</p>` : ''}
      <ol>
        <li>Crea un token en <a href="${esc(st.token_page || 'https://www.kaggle.com/settings')}" target="_blank" rel="noopener">kaggle.com/settings</a> → pestaña <em>Account</em> → sección <em>API</em> → <em>Generate New Token</em> (empieza por <code>KGAT_</code>).</li>
        <li>Pulsa <strong>Activar</strong>: abre el asistente CLI smith del tablero y ejecuta <code>${esc(activate)}</code>. Pega el token en la terminal (la entrada queda oculta); smith lo verifica contra Kaggle y lo guarda solo para tu usuario en <code>${esc(tokenPath)}</code>${env.system === 'windows' ? '' : ' (permisos 0600)'}, el mismo archivo que usan la CLI y el SDK oficiales de Kaggle, nunca dentro del proyecto. Si ya tenías otro token ahí, añade <code>--replace</code>.</li>
        <li>Abre una sesión nueva de Claude, OpenCode o Pi desde el asistente: el tablero le pasa <code>${esc(envVar)}</code> y el MCP <code>kaggle</code> queda autenticado. Fuera del tablero, en tu shell: <code>${esc(env.export_command || `export ${envVar}="$(cat ~/.kaggle/access_token)"`)}</code>; para que quede en cada sesión nueva, añade esa línea a <code>${esc(env.profile_file || '~/.profile')}</code>.</li>
        <li>Comprueba con <code>${esc(check)} --verify</code> (lee tu cuota semanal de GPU); <code>smith mcp kaggle deactivate</code> borra el token.</li>
      </ol>
      <div class="exp-mcp__actions">
        ${cliButton(activate, 'Activar en el asistente CLI')}
        ${cliButton(`${check} --verify`, 'Verificar')}
        <button type="button" class="btn" data-exp-refresh="1">Recargar estado</button>
      </div>
    </section>`;
  }

  // ---------------------------------------------------------- Colab
  // experiments_view's `remote_colab`: the commands are server constants; the
  // templates keep their placeholders literal and are typed, never run.
  const COLAB_ENV_NOTE = {
    windows: 'En Windows nativo el asistente CLI del tablero no está disponible: ejecuta estos comandos en PowerShell.',
    wsl: 'En WSL instala la CLI y ejecuta smith dentro de la distribución; si el consentimiento OAuth no abre el navegador, copia la URL en el navegador de Windows.',
  };

  function colabActivation(state) {
    if (!state || !state.commands) return '';
    const c = state.commands;
    const env = state.environment || {};
    const sysLabel = { macos: 'macOS', linux: 'Linux', wsl: 'Windows (WSL)', windows: 'Windows' }[env.system] || 'desconocido';
    const shellLabel = env.shell === 'powershell' ? 'PowerShell' : (env.shell || 'sh');
    const tiers = (state.paid_tiers || []).map((t) => `<code>${esc(t)}</code>`).join(', ');
    const faq = esc(state.faq || 'https://research.google.com/colaboratory/faq.html');
    const registered = (state.registered || []).length
      ? `<span class="badge badge--ok">registrado</span> en ${(state.registered || []).map((f) => `<code>${esc(f)}</code>`).join(', ')}`
      : '<span class="badge badge--warn">no registrado</span> en este proyecto: ejecuta <code>smith upgrade</code>';
    const note = COLAB_ENV_NOTE[env.system];
    return `<section class="panel exp-mcp" id="expColabActivation">
      <h3 class="panel__title">Conectar Google Colab (CLI y MCP)</h3>
      <p class="exp-intro">MCP oficial <code>${esc(state.server || 'colab')}</code>: ${registered}.</p>
      ${env.system ? `<p class="exp-intro">Entorno detectado: <strong>${esc(sysLabel)}</strong> · shell <code>${esc(shellLabel)}</code>.</p>` : ''}
      ${note ? `<p class="exp-intro"><span class="badge badge--warn">${esc(sysLabel)}</span> ${esc(note)}</p>` : ''}
      <ol>
        <li>Instala la CLI oficial de Colab con la versión fijada: <code>${esc(c.install)}</code>.</li>
        <li>Cada persona del equipo registra su propia cuenta: <code>${esc(c.team_add)}</code>. Reemplaza <code>&lt;slug&gt;</code>, <code>&lt;Nombre&gt;</code> y <code>&lt;tier&gt;</code> (<code>free</code>, ${tiers}) en la terminal: el botón escribe el comando sin ejecutarlo.</li>
        <li>Cada persona inicia sesión con su cuenta en el asistente CLI: <code>${esc(c.login)}</code>. El estado de la CLI queda en <code>~/.config/papersmith/colab/&lt;slug&gt;/</code> (permisos 0700); papersmith nunca lee ni copia esos archivos.</li>
        <li>Comprueba con <code>${esc(c.status)}</code>; <code>${esc(c.team_list)}</code> muestra el equipo.</li>
        <li>El MCP oficial de Colab es para trabajo interactivo: necesita un cuaderno de Colab abierto en el navegador, al que se conecta el agente (Claude, OpenCode o Pi). Las ejecuciones sin interfaz van por la CLI y <code>/remote-execution</code>.</li>
      </ol>
      <h4 class="exp-h4">Regla del equipo</h4>
      <ul>
        <li>Una cuenta por persona y servicio. La <a href="${faq}" target="_blank" rel="noopener">FAQ de Colab</a> no permite "using multiple accounts to work around access or resource usage restrictions" y, en entornos gratuitos sin unidades de cómputo, "running distributed computing workers".</li>
        <li>Por eso las campañas en Colab corren solo en niveles de pago (${tiers}); una cuenta <code>free</code> sirve para la prueba de concepto interactiva en una sesión, nunca como worker de una campaña repartida.</li>
        <li>El paralelismo cuenta personas distintas, no cuentas.</li>
      </ul>
      <h4 class="exp-h4">GPU por nivel</h4>
      <ul>
        <li>Gratuito: una GPU básica, sujeta a disponibilidad.</li>
        <li>De pago (Pro, Pay-As-You-Go, Enterprise): L4, A100 o H100 según las unidades de cómputo, con <code>--gpu</code> en la CLI.</li>
      </ul>
      <div class="exp-mcp__actions">
        ${cliButton(c.install, 'Instalar la CLI')}
        ${cliButton(c.team_add, 'Registrar persona (editar)', false)}
        ${cliButton(c.login, 'Iniciar sesión (editar)', false)}
        ${cliButton(c.status, 'Comprobar')}
        ${cliButton(c.team_list, 'Ver equipo')}
        <button type="button" class="btn" data-exp-refresh="1">Recargar estado</button>
      </div>
    </section>`;
  }

  // ------------------------------------------------------- remote services
  // One offline row per service (experiments_view's `remote_services`). The
  // action is a server-side constant, run in the CLI assistant like the MCP box.
  const SERVICE_STATE = {
    active: ['badge--ok', 'activo'], inactive: ['badge--warn', 'inactivo'],
    missing: ['badge--warn', 'no instalado'], unverified: ['badge--info', 'sin verificar'],
  };

  function remoteServices(state) {
    const rows = state && Array.isArray(state.rows) ? state.rows : [];
    if (!rows.length) return '';
    const body = rows.map((row) => {
      const [cls, stateLabel] = SERVICE_STATE[row.state] || SERVICE_STATE.unverified;
      const label = row.badge || stateLabel;
      const action = row.action && row.action.command
        ? cliButton(row.action.command, row.action.label || 'Ejecutar')
        : '<span class="exp-muted">—</span>';
      return `<tr><td><strong>${esc(row.service)}</strong></td><td>${esc(row.purpose)}</td>`
        + `<td><span class="badge ${esc(cls)}">${esc(label)}</span>${row.detail ? ` <small>${esc(row.detail)}</small>` : ''}</td>`
        + `<td>${action}</td></tr>`;
    }).join('');
    return `<section class="panel exp-services" id="expRemoteServices">
      <h3 class="panel__title">Servicios remotos (Kaggle y Colab)</h3>
      ${state.note ? `<p class="exp-intro">${esc(state.note)}</p>` : ''}
      <div class="table-responsive"><table class="table exp-table"><thead><tr><th>Servicio</th><th>Para qué</th><th>Estado</th><th>Acción</th></tr></thead>
      <tbody>${body}</tbody></table></div>
      <div class="exp-mcp__actions"><button type="button" class="btn" data-exp-refresh="1">Recargar estado</button></div>
    </section>`;
  }

  // ------------------------------------------------------- local environment
  // experiments_view's `local_environment`: the workspace micromamba env and
  // each target's .venv, its declared libraries (installed or missing) and device.
  const ENV_STATE = {
    ready: ['badge--ok', 'listo'], incomplete: ['badge--warn', 'faltan librerías'],
    missing: ['badge--warn', 'no instalado'], unverified: ['badge--info', 'sin verificar'],
  };

  function localEnvironment(state) {
    if (!state) return '';
    const ws = state.workspace || null;
    const targets = Array.isArray(state.targets) ? state.targets : [];
    const envBadge = (st) => {
      const [cls, label] = ENV_STATE[st] || ENV_STATE.unverified;
      return `<span class="badge ${esc(cls)}">${esc(label)}</span>`;
    };
    const rows = [];
    if (ws) {
      const mm = ws.micromamba ? `<small>micromamba en <code>${esc(ws.micromamba)}</code></small>` : '<small>micromamba no encontrado en el PATH</small>';
      rows.push(`<tr><td><strong>${esc(ws.label || 'Entorno micromamba del workspace')}</strong><br><code>${esc(ws.path)}</code></td>`
        + `<td>${esc(ws.python || '—')}</td><td>${envBadge(ws.state)} ${ws.detail ? `<small>${esc(ws.detail)}</small>` : ''}</td>`
        + `<td>${mm}</td><td><span class="exp-muted">—</span></td></tr>`);
    }
    targets.forEach((t) => {
      const libs = (t.libraries || []).map((lib) => (lib.version
        ? `<span class="badge badge--ok">${esc(lib.name)} ${esc(lib.version)}</span>`
        : `<span class="badge badge--warn">${esc(lib.name)}: falta</span>`)).join(' ')
        || (t.required && t.required.length ? `<small>${esc(t.required.join(', '))}</small>` : '<span class="exp-muted">sin librerías declaradas</span>');
      rows.push(`<tr><td><strong>${esc(t.repo)}</strong><br><code>${esc(t.path)}</code></td>`
        + `<td>${esc(t.python || '—')}</td><td>${envBadge(t.state)} ${t.detail ? `<small>${esc(t.detail)}</small>` : ''}</td>`
        + `<td>${libs}</td><td>${esc(t.device || '—')}</td></tr>`);
    });
    const body = rows.length ? rows.join('') : '';
    return `<section class="panel exp-local" id="expLocalEnv">
      <h3 class="panel__title">Entorno local</h3>
      <p class="exp-intro">El entorno micromamba del workspace y el <code>.venv</code> de cada objetivo en <code>implementations/</code>: librerías de <code>pyproject.toml</code> y <code>requirements*.txt</code>, instaladas o faltantes, y el dispositivo que ve torch.${state.note ? ` ${esc(state.note)}` : ''}</p>
      ${body ? `<div class="table-responsive"><table class="table exp-table"><thead><tr><th>Entorno</th><th>Python</th><th>Estado</th><th>Librerías</th><th>Dispositivo</th></tr></thead>
      <tbody>${body}</tbody></table></div>` : empty('Sin entornos locales: python scripts/setup_env.py crea el entorno micromamba del workspace.')}
    </section>`;
  }

  // ------------------------------------------------------------ run options
  // experiments_view's `run_options`: one row per stage and host, the estimate
  // from that host's own Results/timing.json measurements (±20%) or "sin medir".
  function runOptions(state) {
    if (!state) return '';
    const rows = Array.isArray(state.rows) ? state.rows : [];
    const recs = state.recommendations || {};
    const stages = [];
    rows.forEach((r) => { if (!stages.includes(r.stage)) stages.push(r.stage); });
    const body = stages.map((stage) => {
      const list = rows.filter((r) => r.stage === stage);
      const rec = recs[stage] || {};
      return list.map((r, i) => {
        const avail = r.available ? '<span class="badge badge--ok">sí</span>' : '<span class="badge badge--warn">no</span>';
        const est = r.estimate
          ? `${esc(r.estimate_label)}<br><small>${esc(r.estimate.measurements)} medición(es)${(r.estimate.devices || []).length ? ` · ${esc(r.estimate.devices.join(', '))}` : ''}</small>`
          : `<span class="badge badge--info">${esc(r.estimate_label || 'sin medir')}</span>`;
        const recCell = i === 0
          ? `<td rowspan="${list.length}">${rec.poc_budget === 'exceeds' ? '<span class="badge badge--warn">excede 5 h</span> ' : ''}${rec.host ? `<strong>${esc((list.find((x) => x.host === rec.host) || {}).host_label || rec.host)}</strong> ` : ''}<small>${esc(rec.text || '—')}</small></td>`
          : '';
        const stageCell = i === 0 ? `<td rowspan="${list.length}"><strong>${esc(r.stage_label || r.stage)}</strong></td>` : '';
        return `<tr>${stageCell}<td>${esc(r.host_label || r.host)}</td><td>${avail}</td><td>${est}</td><td><small>${esc(r.reason)}</small></td>${recCell}</tr>`;
      }).join('');
    }).join('');
    const hint = state.empty ? `<p class="exp-intro"><span class="badge badge--warn">sin medir</span> ${esc(state.empty_hint || 'Sin Results/timing.json: corre la sonda de tiempo de /remote-parallelism («Estimate before you scale»).')}</p>` : '';
    const sources = (state.sources || []).length
      ? `<p class="exp-intro">Mediciones: ${(state.sources || []).map((f) => `<a href="${artifactUrl(f)}" target="_blank" rel="noopener"><code>${esc(f)}</code></a>`).join(', ')}</p>`
      : '';
    return `<section class="panel exp-run-options" id="expRunOptions">
      <h3 class="panel__title">Opciones de corrida</h3>
      <p class="exp-intro">Por etapa y host: disponibilidad, estimación (rango ${esc(state.note || '±20%, single-probe extrapolation')}) desde las mediciones propias de cada host, y una recomendación. Un host sin medición propia se lee "sin medir"; nunca se escala desde la medición local.</p>
      <p class="exp-intro">Reglas: una etapa que en local tardaría más de ${esc(Math.round((state.local_limit_seconds || 1200) / 60))} min corre en la nube (Colab o Kaggle), y la prueba de concepto cabe en ${esc(Math.round((state.poc_budget_seconds || 18000) / 3600))} h donde corre; ambas leen el extremo alto del rango.</p>
      ${hint}${sources}
      ${body ? `<div class="table-responsive"><table class="table exp-table"><thead><tr><th>Etapa</th><th>Host</th><th>Disponible</th><th>Estimación</th><th>Motivo</th><th>Recomendación</th></tr></thead>
      <tbody>${body}</tbody></table></div>` : ''}
    </section>`;
  }

  // ---------------------------------------------------------------- team
  // remote_services' `team`: owner slugs and presence flags only.
  const TEAM_TIER = { free: 'badge--info', pro: 'badge--ok', payg: 'badge--ok', enterprise: 'badge--ok' };

  function team(state) {
    if (!state) return '';
    const members = Array.isArray(state.members) ? state.members : [];
    const title = '<h3 class="panel__title">Equipo (una cuenta por persona y servicio)</h3>';
    const intro = `<p class="exp-intro">Leído de <code>${esc(state.file || '.papersmith/team.json')}</code>: cada persona opera su propia cuenta de cada servicio. Solo se muestran presencias, nunca credenciales.</p>`;
    if (state.problem) {
      return `<section class="panel exp-team" id="expTeam">${title}${intro}`
        + `<p class="exp-intro"><span class="badge badge--warn">no se pudo leer</span> revisa el archivo con <code>smith team list</code>.</p></section>`;
    }
    if (!members.length) {
      return `<section class="panel exp-team" id="expTeam">${title}${intro}`
        + empty(`Sin miembros: cada persona se registra con ${state.add_command || 'smith team add'}`) + '</section>';
    }
    const rows = members.map((m) => {
      const kaggle = m.kaggle_username
        ? `<code>${esc(m.kaggle_username)}</code> ${m.kaggle_validated ? '<span class="badge badge--ok">validada</span>' : '<span class="badge badge--warn">sin validar</span>'}`
        : '<span class="exp-muted">—</span>';
      const colab = m.colab_tier
        ? `<span class="badge ${esc(TEAM_TIER[m.colab_tier] || 'badge--warn')}">${esc(m.colab_tier)}</span> ${m.colab_config_present ? '<small>sesión configurada</small>' : '<small>sin iniciar sesión</small>'}`
        : '<span class="exp-muted">—</span>';
      const names = { kaggle: 'Kaggle', colab: 'Colab' };
      const eligible = (m.eligible || []).length
        ? (m.eligible || []).map((s) => `<span class="badge badge--ok">${esc(names[s] || s)}</span>`).join(' ')
        : '<span class="badge">no</span>';
      return `<tr><td><code>${esc(m.owner)}</code></td><td>${esc(m.display_name || '')}</td><td>${kaggle}</td><td>${colab}</td><td>${eligible}</td></tr>`;
    }).join('');
    const skipped = state.skipped ? `<p class="exp-intro"><span class="badge badge--warn">${esc(state.skipped)} entrada(s) ignorada(s)</span> (propietario inválido o repetido).</p>` : '';
    return `<section class="panel exp-team" id="expTeam">${title}${intro}${skipped}
      <div class="table-responsive"><table class="table exp-table"><thead><tr><th>Propietario</th><th>Nombre</th><th>Kaggle</th><th>Colab</th><th>Elegible para campañas repartidas</th></tr></thead>
      <tbody>${rows}</tbody></table></div></section>`;
  }

  // ---------------------------------------------------------------- help
  function help(accounts) {
    const k = accounts || {};
    const status = `<p class="exp-intro">Estado local: almacén de cuentas Kaggle
      ${k.accounts_store_present ? '<span class="badge badge--ok">presente</span>' : '<span class="badge badge--warn">ausente</span>'}
      · credenciales en <code>${esc(k.inbox || 'kaggle-inbox')}/</code>: <strong>${esc(k.inbox_count ?? 0)}</strong></p>`;
    return `<details class="panel exp-help">
      <summary class="panel__title">Ayuda: lanzar y monitorear en Kaggle (CLI o MCP) y Colab, o correr en local</summary>
      ${status}
      <h4 class="exp-h4">1. Flujo: prueba de concepto vs. experimentos completos</h4>
      <ol>
        <li><code>/experimental-deliberation</code> publica el protocolo (<code>experiments/experiments-&lt;slug&gt;-vNN.md</code>).</li>
        <li><code>/datasets synth</code> crea el toy set sembrado; <code>/datasets search|license|qc|prepare</code> deja el dataset oficial.</li>
        <li>Réplica de los métodos de comparación (<code>/proposal-implementation</code> → <code>paper-replicator</code>): primero el código publicado, auditado; si no existe, reimplementación (<code>REPLICATION.md</code>).</li>
        <li><code>/proposal-implementation</code> construye la <strong>prueba de concepto</strong> (carpeta con <code>AGREED.md</code>).</li>
        <li>Sonda de tiempo corta (una época de un fold por brazo) en <code>Results/timing.json</code>, antes del piloto y otra vez antes de la corrida completa: la tabla <em>Opciones de corrida</em> estima cada etapa por host (±20%); <code>/remote-parallelism estimate</code> y luego <code>assess --owners &lt;propietarios distintos&gt;</code> deciden si repartir.</li>
        <li>Opcional, solo si la deliberación lo estimó conveniente: búsqueda de hiperparámetros con Optuna (<code>/hyperparameter-search plan|report|status</code>), anidada dentro de los sujetos de entrenamiento de cada fold externo, con el mismo presupuesto de trials para cada brazo y baseline y el evaluador de importancia declarado; sus contornos e importancias aparecen en cada producto.</li>
        <li><code>/experimental-implementation</code> construye los <strong>experimentos completos</strong> del protocolo (carpeta con <code>Experimental_AGREED.md</code>).</li>
        <li><code>experiments-reviewer</code> revisa el código (calidad, optimización, uso de GPU, pruebas estadísticas) antes de cualquier ensayo; su informe va al operador.</li>
        <li><strong>Local</strong>: corre directo con el <code>.venv</code> del objetivo o el entorno micromamba del workspace (tabla <em>Entorno local</em>); no necesita ensayo ni ledger.</li>
        <li><strong>Remoto</strong>: cada persona se registra con <code>smith team add --owner &lt;slug&gt; --name "&lt;nombre&gt;" --kaggle-username &lt;usuario&gt; --attest</code>; <code>/kaggle-accounts validate</code> comprueba que su cuenta autentica.</li>
        <li><code>/remote-execution</code>, con la forma exacta <code>python skills/remote-execution/scripts/remote_cli.py &lt;verbo&gt;</code>:
          <code>generate-job</code> → <code>submit --smoke</code> → <code>fetch --smoke</code> y <code>smoke record</code> → <code>readiness</code> → <code>gate</code> (operador, <code>implementation_cli gate</code>) → <code>submit</code> → <code>status</code> / <code>poll</code> → <code>fetch</code>.</li>
        <li>Solo el operador autoriza un lanzamiento: ningún agente ejecuta <code>gate</code> ni <code>submit</code> por su cuenta.</li>
      </ol>
      <h4 class="exp-h4">Cuentas y credenciales</h4>
      <ul>
        <li>Regla de Kaggle: una cuenta por persona. Kaggle staff: "the one account per person applies to all Kaggle site use, not just competitions" (<a href="https://www.kaggle.com/discussions/general/192527" target="_blank" rel="noopener">https://www.kaggle.com/discussions/general/192527</a>). Un segundo correo no hace una segunda persona: solo las cuentas que <code>.papersmith/team.json</code> asigna a un propietario son workers, una por persona.</li>
        <li>Workers (<code>/remote-execution</code>): usan el almacén de <code>/kaggle-accounts</code>; deja un <code>kaggle.json</code> o un archivo con una línea <code>usuario token</code> por cuenta en <code>kaggle-inbox/</code> y valida.</li>
        <li>MCP y CLI oficial: leen el token <code>KGAT_…</code> de tu cuenta en <code>~/.kaggle/access_token</code>, que escribe <code>smith mcp kaggle activate</code>; no es una credencial de worker.</li>
      </ul>
      <h4 class="exp-h4">2. GPU</h4>
      <ul>
        <li>El adaptador Kaggle de papersmith ya empuja con <code>enable_gpu: true</code> y <code>machine_shape: "NvidiaTeslaT4"</code> (una sola GPU); un <code>enable_gpu</code> solo puede caer en una P100 y fallar.</li>
        <li>Verifica en el log del job: <code>import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))</code>.</li>
        <li>Límites: los de sesión y la cuota semanal de GPU son los que Kaggle muestra en la configuración de la cuenta o en <code>get_accelerator_quota</code>; léelos ahí en vez de suponer un número. En papersmith.yaml, <code>compute_targets.kaggle-gpu-pool.max_timeout_hours</code> es un tope local que declaras, no el límite de Kaggle.</li>
      </ul>
      <h4 class="exp-h4">3. Alternativa: Kaggle CLI directo</h4>
      <pre><code>kaggle kernels push -p &lt;dir&gt;          # kernel-metadata.json con "enable_gpu": true
kaggle kernels status &lt;user/slug&gt;
kaggle kernels output &lt;user/slug&gt; -p &lt;dest&gt;</code></pre>
      <p class="exp-intro">El CLI directo no escribe el ledger: el panel no verá esas corridas.</p>
      <h4 class="exp-h4">4. MCP</h4>
      <ul>
        <li>papersmith registra el servidor MCP oficial de Kaggle (<code>https://www.kaggle.com/mcp</code>) como <code>kaggle</code> en <code>.mcp.json</code>, <code>opencode.json</code>, <code>.pi/mcp.json</code> y <code>.agents/mcp_config.json</code> al hacer <code>smith init</code> o <code>smith upgrade</code>.</li>
        <li>Las herramientas públicas (<code>search_datasets</code>, <code>search_notebooks</code>) responden sin token. Las de cuenta piden un token <code>KGAT_…</code> (Kaggle → Settings → API): actívalo con <code>smith mcp kaggle activate</code> desde el asistente CLI (recuadro <em>Activar Kaggle por MCP</em>, que muestra el comando exacto para tu sistema y tu shell); nunca lo escribas en un archivo del proyecto.</li>
        <li>Lanzar con GPU: <code>save_notebook</code> con <code>enableGpuNullable: true</code> y <code>machineShapeNullable: "NvidiaTeslaT4"</code>; monitorear con <code>get_notebook_session_status</code>, <code>list_notebook_session_output</code> y <code>download_notebook_output</code>; cuota semanal con <code>get_accelerator_quota</code>; cancelar con <code>cancel_notebook_session</code>.</li>
        <li>Úsalo para pruebas de concepto rápidas y para monitorear; solo el operador autoriza un lanzamiento.</li>
        <li>Para lanzar, prefiere la ruta CLI de papersmith: registra el ledger (<code>.remote-execution/ledger.jsonl</code>) que este panel lee.</li>
      </ul>
      <h4 class="exp-h4">5. Optimización</h4>
      <ul>
        <li>Simuladores pequeños: suelen correr más rápido en CPU o en lotes vectorizados con diferenciación automática que paso a paso; mide antes de mover algo a GPU.</li>
        <li>GPU para la parte clásica (backbone, capas densas); usa precisión mixta allí.</li>
        <li>Reparte shards entre cuentas con <code>distribute</code>.</li>
        <li>Cachea épocas preprocesadas en <code>Data/</code>; fija semillas.</li>
      </ul>
      <h4 class="exp-h4">6. Google Colab (CLI o MCP)</h4>
      <ul>
        <li>Sin interfaz: el backend Colab de <code>/remote-execution</code> usa la CLI oficial <code>colab</code> con los mismos verbos (<code>generate-job</code> → <code>submit --smoke</code> → <code>fetch --smoke</code> y <code>smoke record</code> → <code>readiness</code> → <code>gate</code> (operador, <code>implementation_cli gate</code>) → <code>submit</code> → <code>status</code> / <code>poll</code> → <code>fetch</code>); un worker por persona del equipo, cada una tras <code>smith colab login --owner &lt;slug&gt;</code>.</li>
        <li>Interactivo: el MCP oficial de Colab maneja un cuaderno abierto en el navegador; sirve para explorar y para la prueba de concepto, y no escribe el ledger que lee este panel.</li>
        <li>Regla del equipo: una cuenta por persona y servicio; las campañas repartidas en Colab solo con niveles de pago (pro, payg, enterprise); una cuenta gratuita nunca es worker de una campaña.</li>
        <li>Reproducibilidad: No mezcles shards de Kaggle y Colab en una misma campaña salvo que los sellos de entorno de cada shard sean idénticos (modelo de acelerador, CUDA, torch); por defecto, no se mezclan.</li>
      </ul>
      <h4 class="exp-h4">7. Qué prueba estadística reportar</h4>
      <ul>
        <li>2 modelos en validación cruzada: t-test de remuestreo corregido (Nadeau–Bengio) o 5x2cv.</li>
        <li>≥ 3 modelos: Friedman + post-hoc Nemenyi o Holm.</li>
        <li>Un único conjunto de prueba: McNemar (aciertos) o DeLong (AUC).</li>
        <li>Corrige comparaciones múltiples con Holm; reporta tamaño del efecto e IC.</li>
        <li>Wilcoxon necesita n ≥ 6 pares para poder alcanzar p &lt; 0.05.</li>
      </ul>
    </details>`;
  }

  // ---------------------------------------------------------------- datasets
  const DATASET_LICENSE = {
    allowed: ['badge--ok', 'permitida'], overridden: ['badge--warn', 'aceptada por el operador'],
    refused: ['badge--warn', 'rechazada'],
  };
  const DATASET_QC = { pass: ['badge--ok', 'QC ok'], warn: ['badge--warn', 'QC con avisos'], fail: ['badge--warn', 'QC falla'] };
  const badge = (pair, fallback) => {
    const [cls, label] = pair || ['badge--info', fallback];
    return `<span class="badge ${esc(cls)}">${esc(label)}</span>`;
  };

  function datasets(state) {
    const d = state || {};
    const items = Array.isArray(d.items) ? d.items : [];
    const intro = '<p class="exp-intro">Registro de <code>datasets/registry.json</code> (skill <code>/datasets</code>): el conjunto toy para la prueba de concepto y los datasets completos con su licencia, control de calidad, preparación oficial y estado remoto.</p>';
    if (!items.length) {
      return `<section class="panel exp-datasets"><h3 class="panel__title">Datasets (toy y completos)</h3>${intro}`
        + empty('Sin datasets registrados: /datasets synth crea el conjunto toy con semilla; /datasets search busca datasets reales y deja datasets/search-<fecha>.json.')
        + '</section>';
    }
    const rows = items.map((item) => {
      const remote = item.remote_ref
        ? `<code>${esc(item.remote_ref)}</code> ${badge(item.visibility === 'public' ? ['badge--warn', 'público'] : ['badge--ok', 'privado'])}${item.remote_version != null ? ` <small>v${esc(item.remote_version)}</small>` : ''}`
        : '<span class="badge badge--info">sin publicar</span>';
      const prep = item.prepared
        ? `<span class="badge badge--ok">preparado${item.preparation_version != null ? ` v${esc(item.preparation_version)}` : ''}</span>`
        : '<span class="badge badge--info">sin preparar</span>';
      return `<tr><td><code>${esc(item.slug)}</code></td>`
        + `<td>${badge(item.role === 'toy' ? ['badge--info', 'toy'] : ['badge--info', 'completo'])}</td>`
        + `<td>${esc(item.title)}</td>`
        + `<td>${badge(DATASET_LICENSE[item.license], 'sin licencia')}${item.host_license ? ` <small>${esc(item.host_license)}</small>` : ''}</td>`
        + `<td>${badge(DATASET_QC[item.qc], 'sin QC')}</td><td>${prep}</td><td>${remote}</td></tr>`;
    }).join('');
    const searches = (d.searches || []).length
      ? `<p class="exp-intro">Búsquedas: ${(d.searches || []).map((f) => `<a href="${artifactUrl(f)}" target="_blank" rel="noopener"><code>${esc(f)}</code></a>`).join(', ')}</p>`
      : '';
    return `<section class="panel exp-datasets"><h3 class="panel__title">Datasets (toy y completos)</h3>${intro}
      <div class="table-responsive"><table class="table exp-table"><thead><tr><th>Slug</th><th>Rol</th><th>Título</th><th>Licencia</th><th>QC</th><th>Preparación</th><th>Remoto</th></tr></thead>
      <tbody>${rows}</tbody></table></div>${searches}</section>`;
  }

  // ---------------------------------------------------------------- page
  function render(view) {
    const v = view || {};
    const products = v.products || [];
    const poc = products.filter((p) => p.kind === 'poc');
    const full = products.filter((p) => p.kind === 'full');
    const other = products.filter((p) => p.kind !== 'poc' && p.kind !== 'full');
    return [
      mcpActivation(v.remote_mcp),
      colabActivation(v.remote_colab),
      remoteServices(v.remote_services),
      localEnvironment(v.local_environment),
      runOptions(v.run_options),
      team(v.remote_services && v.remote_services.team),
      help(v.remote_accounts),
      datasets(v.datasets),
      group('Prueba de concepto', 'Productos de /proposal-implementation (AGREED.md): convergencia, figuras y tablas principales.',
        poc, 'Sin pruebas de concepto: /proposal-implementation crea implementations/<repo>/<Nombre>/ con AGREED.md; sus curvas salen de Results/history*.json|csv.'),
      group('Experimentos completos', 'Productos de /experimental-implementation (Experimental_AGREED.md): convergencia, tablas, figuras y significancia.',
        full, 'Sin experimentos completos: /experimental-implementation crea la carpeta con Experimental_AGREED.md; sus curvas salen de Results/history*.json|csv.'),
      other.length ? group('Sin clasificar', 'Carpetas con Results/ pero sin AGREED.md ni Experimental_AGREED.md.', other, '') : '',
      protocol(v.protocol),
    ].join('');
  }

  function paint() {
    const host = typeof document !== 'undefined' && document.getElementById
      ? document.getElementById('experimentsRoot') : null;
    if (host && lastView) host.innerHTML = render(lastView);
  }

  async function refreshExperimentsPanel() {
    const host = document.getElementById('experimentsRoot');
    if (!host) return;
    try {
      const response = await fetch('/api/experiments', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      lastView = await response.json();
      paint();
    } catch (err) {
      host.innerHTML = empty(`No se pudo leer /api/experiments: ${err.message}`);
    }
  }

  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('click', (event) => {
      const closest = (sel) => (event.target && event.target.closest ? event.target.closest(sel) : null);
      const cli = closest('[data-exp-cli]');
      if (cli) {
        if (typeof window.sendToCli === 'function') {
          if (cli.getAttribute('data-exp-cli-run') === '0') {
            window.sendToCli(cli.getAttribute('data-exp-cli'), false, { kind: 'shell' });
          } else {
            window.sendToCli(cli.getAttribute('data-exp-cli'), true, { kind: 'shell' });
          }
        }
        return;
      }
      if (closest('[data-exp-refresh]')) { refreshExperimentsPanel(); return; }
      const validate = closest('[data-diagram-validate]');
      if (validate) { validateDiagram(validate); return; }
      const button = closest('[data-exp-log]');
      if (!button) return;
      const id = button.getAttribute('data-exp-log');
      if (logCharts.has(id)) logCharts.delete(id); else logCharts.add(id);
      paint();
    });
  }

  window.refreshExperimentsPanel = refreshExperimentsPanel;
  window.ExperimentsPanel = { render, mcpActivation, colabActivation, remoteServices, localEnvironment, runOptions, team, datasets };
})();
