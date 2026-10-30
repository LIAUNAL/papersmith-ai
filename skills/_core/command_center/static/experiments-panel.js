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
 * Results/timing.json or "unmeasured", reason and recommendation), plus a remote-accounts
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

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  // A label by machine value; an unknown value shows as itself.
  const labelOf = (prefix, value) => (window.i18n && window.i18n.has(`${prefix}.${value}`) ? t(`${prefix}.${value}`) : String(value ?? ''));
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
      ? `<button type="button" class="btn exp-log-toggle" data-exp-log="${esc(id)}" aria-pressed="${useLog}">${esc(useLog ? t('exp.linearScale') : t('exp.logScale'))}</button>`
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
      return empty(t('exp.noConvergence'));
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
        ? `<td class="exp-pending">${opts.pending ? esc(t('exp.pendingCell')) : ''}</td>`
        : `<td>${esc(cell)}</td>`;
    }).join('')}</tr>`).join('');
    return `<div class="table-responsive"><table class="table exp-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function tables(product) {
    const list = product.tables || [];
    if (!list.length) return '';
    return `<h4 class="exp-h4">${esc(t('exp.tables'))}</h4>` + list.map((tab) => `<div class="exp-file">${esc(tab.path)}</div>${table(tab.headers || [], tab.rows || [])}`).join('');
  }

  function significance(product) {
    const rows = product.significance || [];
    if (!rows.length) {
      return `<h4 class="exp-h4">${esc(t('exp.significance'))}</h4>`
        + empty(t('exp.noSignificance'));
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
    return `<h4 class="exp-h4">${esc(t('exp.significance'))}</h4><div class="table-responsive"><table class="table exp-table">
      <thead><tr><th>${esc(t('exp.sig.test'))}</th><th>${esc(t('exp.sig.comparison'))}</th><th>${esc(t('exp.sig.statistic'))}</th><th>p</th><th>${esc(t('exp.sig.pAdjusted'))}</th><th>${esc(t('exp.sig.effect'))}</th><th>${esc(t('exp.sig.ci'))}</th><th>n</th><th></th></tr></thead>
      <tbody>${body}</tbody></table></div>`;
  }

  // ------------------------------------------------- hyperparameter search
  const EVALUATOR_LABEL = { fanova: 'fANOVA', 'ped-anova': 'PED-ANOVA', 'mean-decrease-impurity': 'Mean Decrease Impurity' };
  const HPO_FIGURES = ['contour', 'importance', 'history'];
  const evaluatorName = (name) => EVALUATOR_LABEL[name] || name || t('exp.hpo.noEvaluator');

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
    return `<div class="exp-hpo-importance"><div class="exp-file">${esc(t('exp.hpo.importanceOf', { evaluator: evaluatorName(imp.evaluator) }))}</div>${rows}</div>`;
  }

  function hpoFigures(h) {
    const figures = h.figures || {};
    const notes = h.notes || [];
    const cells = HPO_FIGURES.map((key) => {
      const path = figures[key];
      const title = t(`exp.hpo.figure.${key}`);
      if (path) return `<div class="exp-hpo-figure"><div class="exp-file">${esc(title)}</div>${artifact(path)}</div>`;
      const note = notes.find((n) => String(n).toLowerCase().includes(key)) || t('exp.hpo.noFigure');
      return `<div class="exp-hpo-figure"><div class="exp-file">${esc(title)}</div>${empty(note)}</div>`;
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
        : `${fmt(h.bestValue, 4)} <small>${esc(obj.metric || '')}${obj.direction ? ` · ${esc(labelOf('exp.hpo.direction', obj.direction))}` : ''}</small>`;
      return `<tr><td><code>${esc(h.study)}</code></td><td>${esc(h.arm || '—')}</td><td>${esc(h.fold ?? '—')}</td>
        <td>${esc(h.complete ?? '—')} / ${esc(h.pruned ?? '—')}${h.failed ? ` <small>${esc(t('exp.hpo.failed', { n: h.failed }))}</small>` : ''}${h.nTrials ? ` <small>${esc(t('exp.hpo.ofTrials', { n: h.nTrials }))}</small>` : ''}</td>
        <td>${best}</td><td>${params}</td></tr>`;
    }).join('');
    const details = list.map((h) => `<details class="exp-hpo-study"><summary><code>${esc(h.study)}</code> · ${esc(h.file)}</summary>
      ${importanceBars(h.importance)}${h.importanceCheck ? importanceBars(h.importanceCheck) : ''}
      ${hpoFigures(h)}</details>`).join('');
    return `<h4 class="exp-h4">${esc(t('exp.hpo.title'))}</h4>
      <div class="table-responsive"><table class="table exp-table">
      <thead><tr><th>${esc(t('exp.hpo.study'))}</th><th>${esc(t('exp.hpo.arm'))}</th><th>Fold</th><th>${esc(t('exp.hpo.trials'))}</th><th>${esc(t('exp.hpo.best'))}</th><th>${esc(t('exp.hpo.bestParams'))}</th></tr></thead>
      <tbody>${body}</tbody></table></div>${details}`;
  }

  const STATE_CLASS = { submitted: 'badge--info', returned: 'badge--ok', errored: 'badge--bad' };
  const stateBadge = (state) => [STATE_CLASS[state] || '', labelOf('exp.runState', state)];
  function runs(product) {
    const r = product.runs || {};
    if (!r.count) return `<span class="badge">${esc(t('exp.noRemoteRuns'))}</span>`;
    const chips = Object.entries(r.by_state || {}).map(([state, n]) => {
      const [cls, label] = stateBadge(state);
      return `<span class="badge ${cls}">${esc(label)}: ${esc(n)}</span>`;
    }).join(' ');
    const latest = (r.latest || []).map((e) => {
      const [cls, label] = stateBadge(e.state);
      return `<li><span class="badge ${cls}">${esc(label)}</span> <code>${esc(e.entrypoint)}</code>
        ${e.worker ? `· ${esc(e.worker)}` : ''} ${e.ts ? `· <small>${esc(e.ts)}</small>` : ''}
        ${e.reason ? `<div class="exp-reason">${esc(e.reason)}</div>` : ''}</li>`;
    }).join('');
    return `${chips}<details class="exp-runs"><summary>${esc(t('exp.latestRuns', { n: r.count }))}</summary><ul>${latest}</ul></details>`;
  }

  // Remote runs per worker (S6): each worker's lanes -- entrypoint and
  // concurrent slot -- folded from the ledger, slots grouped under their worker.
  function remoteWorkers(product) {
    const workers = product.remote_workers || [];
    if (!workers.length) return '';
    const body = workers.map((w) => {
      const lanes = w.lanes || [];
      const more = (w.lane_count || 0) > lanes.length
        ? `<tr><td colspan="6"><small class="exp-muted">${esc(t('exp.moreLanes', { n: w.lane_count - lanes.length }))}</small></td></tr>` : '';
      return lanes.map((lane, index) => {
        const [cls, label] = stateBadge(lane.state);
        const units = Array.isArray(lane.units) ? esc(lane.units.join(', '))
          : `<span class="exp-muted">${lane.granted != null ? esc(t('exp.capacity', { n: lane.granted })) : '—'}</span>`;
        const head = index === 0
          ? `<td rowspan="${lanes.length}"><strong>${esc(w.worker)}</strong><br><small>${esc(w.service || '—')}</small></td>` : '';
        return `<tr>${head}<td><code>${esc(lane.entrypoint)}</code> <small>slot ${esc(lane.slot)}</small></td>
          <td><span class="badge ${cls}">${esc(label)}</span>${lane.reason ? `<div class="exp-reason">${esc(lane.reason)}</div>` : ''}</td>
          <td><small>${units}</small></td><td><code>${esc(lane.submission_id)}</code></td><td><small>${esc(lane.ts)}</small></td></tr>`;
      }).join('') + more;
    }).join('');
    return `<details class="exp-runs exp-workers"><summary>${esc(t('exp.workers', { n: workers.length }))}</summary>
      <div class="table-responsive"><table class="table exp-table">
      <thead><tr><th>${esc(t('exp.workers.worker'))}</th><th>Entrypoint / slot</th><th>${esc(t('exp.col.state'))}</th><th>${esc(t('exp.workers.units'))}</th><th>${esc(t('exp.workers.submission'))}</th><th>${esc(t('exp.workers.updated'))}</th></tr></thead>
      <tbody>${body}</tbody></table></div></details>`;
  }

  // ------------------------------------------------------------ diagrams
  // One figure per approval, drawn by skills/experiment-diagrams: the proof of
  // concept first, then the full experiments. The operator verifies each one here.
  const DIAGRAM_TITLES = {
    poc: 'exp.diagram.title.poc',
    experiments: 'exp.diagram.title.experiments',
  };

  // validation: absent (not drawn), pending, validated, stale (drawn again
  // after it was validated). Nothing is launched until each one is validated.
  const DIAGRAM_STATES = {
    absent: ['exp.diagram.state.absent', 'badge--warn'],
    pending: ['exp.diagram.state.pending', 'badge--warn'],
    stale: ['exp.diagram.state.stale', 'badge--warn'],
    validated: ['exp.diagram.state.validated', 'badge--ok'],
  };

  // How a validated diagram was validated: in an agent conversation (the
  // experiment-diagrams `validate` verb) or with this tab's button.
  const DIAGRAM_VIA = {
    chat: 'exp.diagram.via.chat',
    dashboard: 'exp.diagram.via.dashboard',
  };

  function diagramAnchor(p) {
    return esc(`exp-diagrams-${p.repo || ''}-${p.name || ''}`);
  }

  // What blocks a launch, above the setup sections: a server still running
  // the code of an older release, and every diagram not validated yet.
  function attention(v) {
    const notes = [];
    const dash = v.dashboard || {};
    if (dash.stale) {
      notes.push(`<p>${t('exp.staleServerHtml', { started: esc(dash.startedVersion || '?'), workspace: esc(dash.workspaceVersion || '?') })}</p>`);
    }
    const open = [];
    (v.products || []).forEach((p) => (p.diagrams || []).forEach((d) => {
      const state = d.png ? (d.validation || 'pending') : 'absent';
      if (state === 'validated') return;
      const [label] = DIAGRAM_STATES[state] || DIAGRAM_STATES.pending;
      open.push(`<li><a href="#${diagramAnchor(p)}">${esc(p.name || '')}: ${esc(DIAGRAM_TITLES[d.kind] ? t(DIAGRAM_TITLES[d.kind]) : d.kind)}</a>
        <span class="badge badge--warn">${esc(t(label))}</span></li>`);
    }));
    if (open.length) {
      notes.push(`<p>${esc(t('exp.nothingLaunches'))}</p><ul>${open.join('')}</ul>`);
    }
    return notes.length
      ? `<section class="panel exp-attention" role="status"><h3 class="panel__title">${esc(t('exp.beforeLaunch'))}</h3>${notes.join('')}</section>`
      : '';
  }

  function diagrams(p) {
    const list = p.diagrams || [];
    if (!list.length) return '';
    const items = list.map((d) => {
      const title = DIAGRAM_TITLES[d.kind] ? t(DIAGRAM_TITLES[d.kind]) : d.kind;
      const files = [d.png, d.pdf].filter(Boolean);
      const state = d.png ? (d.validation || 'pending') : 'absent';
      const [label, tone] = DIAGRAM_STATES[state] || DIAGRAM_STATES.pending;
      const validate = state === 'pending' || state === 'stale'
        ? `<button type="button" class="btn" data-diagram-validate="${esc(d.kind)}" data-diagram-repo="${esc(p.repo || '')}"
            data-diagram-name="${esc(p.name || '')}">${esc(t('exp.diagram.validate'))}</button>` : '';
      const body = d.png
        ? `<div class="exp-gallery">${files.map(artifact).join('')}</div>
           <p class="exp-intro">${t('exp.diagram.reviewHtml', { marker: esc(d.marker || ''), slash: `<code>${esc(d.slash || '')}</code>` })}</p>
           <div class="exp-chips">${validate}${cliButton(d.command || '', t('exp.diagram.regenerate'))}</div>`
        : `<p class="exp-intro">${t('exp.diagram.missingHtml', { marker: esc(d.marker || ''), slash: `<code>${esc(d.slash || '')}</code>` })}</p>
           <div class="exp-chips">${cliButton(d.command || '', t('exp.diagram.generate'))}</div>`;
      const via = state === 'validated' && d.validatedVia
        ? ` <small class="exp-muted">${esc(DIAGRAM_VIA[d.validatedVia] ? t(DIAGRAM_VIA[d.validatedVia]) : t('exp.diagram.via.other', { via: d.validatedVia }))}</small>` : '';
      return `<div class="exp-diagram"><div class="exp-file">${esc(title)}
        <span class="badge ${tone}">${esc(t(label))}</span>${via}</div>${body}</div>`;
    }).join('');
    return `<h4 class="exp-h4" id="${diagramAnchor(p)}">${esc(t('exp.diagram.toVerify'))}</h4>${items}`;
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
      button.textContent = t('exp.diagram.validateFailed', { error: err.message });
      return;
    }
    refreshExperimentsPanel();
  }

  function reviewerAudit(p) {
    if (!p || !p.reviewer) return '';
    const r = p.reviewer;
    const s = r.summary || {};
    const findings = r.findings || [];
    const isClean = s.blockers_resolved === s.blockers && (s.blockers ?? 0) > 0;
    const badgeColor = isClean ? 'badge--ok' : 'badge--warn';
    const statusLabel = r.status === 'resolved' ? t('exp.reviewer.status.resolved') : r.status;
    return `<div class="exp-reviewer-card" style="margin: 1rem 0; padding: 0.85rem; background: var(--surface-2, rgba(255,255,255,0.03)); border: 1px solid var(--border); border-radius: var(--radius);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
        <div>
          <strong style="color: var(--accent);">${esc(t('exp.reviewer.title'))} (${esc(r.agent || 'experiments-reviewer')})</strong>
          <span class="badge ${badgeColor}" style="margin-left: 0.5rem;">${esc(statusLabel)}</span>
        </div>
        <small class="exp-muted">${esc(r.generated_at ? r.generated_at.split('T')[0] : '')}</small>
      </div>
      <div style="font-size: 0.85rem; margin-bottom: 0.5rem;">
        ${esc(t('exp.reviewer.blockers'))}: <strong>${esc(s.blockers_resolved ?? 0)}/${esc(s.blockers ?? 0)} ${esc(t('exp.reviewer.resolved'))}</strong> · 
        ${esc(t('exp.reviewer.majors'))}: <strong>${esc(s.majors ?? 0)}</strong> · 
        ${esc(t('exp.reviewer.minors'))}: <strong>${esc(s.minors ?? 0)}</strong> · 
        Tests: <strong>${esc(s.tests_passed ?? 0)}/${esc(s.tests_total ?? 0)} ${esc(t('exp.reviewer.passed'))}</strong>
      </div>
      <details style="font-size: 0.85rem;">
        <summary style="cursor: pointer; color: var(--accent);">${esc(t('exp.reviewer.viewFindings', { count: findings.length }))}</summary>
        <ul style="margin: 0.5rem 0 0.5rem 1.25rem; padding: 0;">
          ${findings.map((f) => `<li style="margin-bottom: 0.35rem;">
            <span class="badge ${f.severity === 'blocker' ? 'badge--bad' : f.severity === 'major' ? 'badge--warn' : 'badge--info'}">${esc(f.severity)}</span>
            <strong>${esc(f.path)}:${esc(f.line)}</strong>: ${esc(f.description)}
            ${f.resolution ? `<br><small style="color: var(--accent-success, #4ade80);">↳ ${esc(t('exp.reviewer.solution'))}: ${esc(f.resolution)} (${esc(f.resolved_in || '')})</small>` : ''}
          </li>`).join('')}
        </ul>
      </details>
    </div>`;
  }

  function executionMonitor(p) {
    if (!p || !p.execution_monitor) return '';
    const m = p.execution_monitor;
    const stages = m.stages || [];
    const isCompleted = m.status === 'completed';
    const isRunning = m.status === 'running';
    const badgeCls = isCompleted ? 'badge--ok' : (isRunning ? 'badge--info' : 'badge--warn');
    const statusText = isCompleted ? (t('exp.monitor.status.completed') || 'Completado')
      : (isRunning ? (t('exp.monitor.status.running') || 'En ejecución')
      : (t('exp.monitor.status.inProgress') || 'En progreso'));

    const etaText = isCompleted
      ? `<span style="color: var(--accent-success, #4ade80); font-weight: 600;">✓ ${esc(t('exp.monitor.allCompleted') || 'Todas las etapas finalizadas')}</span>`
      : `<span><strong>${esc(t('exp.monitor.eta') || 'Finalización estimada')}:</strong> ${esc(m.estimated_completion_label || '—')} <span class="badge badge--info" style="margin-left: 0.35rem;">~${esc(m.remaining_duration || '—')} ${esc(t('exp.monitor.remaining') || 'restantes')}</span></span>`;

    const stageRows = stages.map((s) => {
      const sCls = s.status === 'completed' ? 'badge--ok' : (s.status === 'running' ? 'badge--info' : 'badge--warn');
      const sStatusLabel = s.status === 'completed' ? '✓ ' + (t('exp.monitor.stage.done') || 'Listo')
        : (s.status === 'running' ? '⚡ ' + (t('exp.monitor.stage.running') || 'Corriendo')
        : (t('exp.monitor.stage.pending') || 'Pendiente'));
      const catCls = s.category === 'smoke' ? 'badge--info' : (s.category === 'training' ? 'badge--warn' : '');
      return `<tr>
        <td><strong>#${esc(s.index)}</strong></td>
        <td><code>${esc(s.step || s.tag || s.kind)}</code> <small class="exp-muted">(${esc(s.kind)})</small><br><small>${esc(s.name)}</small></td>
        <td><span class="badge ${sCls}">${esc(sStatusLabel)}</span></td>
        <td><span class="badge ${catCls}">${esc(s.category)}</span></td>
        <td><strong>~${esc(s.estimated_duration)}</strong></td>
      </tr>`;
    }).join('');

    return `<div class="exp-monitor-card" style="margin: 1rem 0; padding: 0.85rem; background: var(--surface-2, rgba(255,255,255,0.03)); border: 1px solid var(--border); border-radius: var(--radius);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; flex-wrap: wrap; gap: 0.5rem;">
        <div>
          <strong style="color: var(--accent); font-size: 1rem;">📊 ${esc(t('exp.monitor.title') || 'Monitor de Ejecución y Tiempos Estimados')}</strong>
          <span class="badge ${badgeCls}" style="margin-left: 0.5rem;">${esc(statusText)}</span>
        </div>
        <div style="font-size: 0.85rem;">${etaText}</div>
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; margin-top: 0.25rem;">
        <span>${esc(t('exp.monitor.progress') || 'Progreso')}: <strong>${esc(m.completed_stages)}/${esc(m.total_stages)} ${esc(t('exp.monitor.stages') || 'etapas')} (${esc(m.progress_percent)}%)</strong></span>
        ${m.current_stage ? `<small class="exp-muted">${esc(t('exp.monitor.current') || 'Etapa actual')}: <em>${esc(m.current_stage)}</em></small>` : ''}
      </div>
      <div style="background: rgba(255,255,255,0.1); border-radius: 999px; height: 7px; overflow: hidden; margin: 0.5rem 0 0.85rem 0;">
        <div style="background: ${isCompleted ? 'var(--accent-success, #4ade80)' : 'var(--accent, #3b82f6)'}; height: 100%; width: ${Math.min(100, Math.max(0, m.progress_percent))}%; transition: width 0.3s ease;"></div>
      </div>
      <details style="font-size: 0.85rem;">
        <summary style="cursor: pointer; color: var(--accent);">${esc(t('exp.monitor.viewStages') || 'Ver desglose de tiempos por etapa')} (${esc(stages.length)} etapas)</summary>
        <div class="table-responsive" style="margin-top: 0.5rem;">
          <table class="table exp-table" style="font-size: 0.82rem;">
            <thead><tr><th>#</th><th>${esc(t('exp.monitor.col.stage') || 'Etapa / Descripción')}</th><th>${esc(t('exp.monitor.col.status') || 'Estado')}</th><th>${esc(t('exp.monitor.col.type') || 'Tipo')}</th><th>${esc(t('exp.monitor.col.duration') || 'Duración est.')}</th></tr></thead>
            <tbody>${stageRows}</tbody>
          </table>
        </div>
      </details>
    </div>`;
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
      ${remoteWorkers(p)}
      ${executionMonitor(p)}
      ${diagrams(p)}
      ${reviewerAudit(p)}
      ${pinned.length ? `<h4 class="exp-h4">${esc(t('exp.pinned'))}</h4><div class="exp-gallery">${pinned.map(artifact).join('')}</div>` : ''}
      <h4 class="exp-h4">${esc(t('exp.convergence'))}</h4>${convergence(p)}
      ${figures.length ? `<h4 class="exp-h4">${esc(t('exp.figures'))}</h4><div class="exp-gallery">${figures.map(artifact).join('')}</div>` : ''}
      ${hpo(p)}
      ${tables(p)}
      ${significance(p)}
      ${warnings.length ? `<details class="exp-warnings"><summary>${esc(t('exp.readWarnings', { n: warnings.length }))}</summary><ul>${warnings.map((w) => `<li>${esc(w)}</li>`).join('')}</ul></details>` : ''}
    </article>`;
  }

  function group(title, intro, list, emptyText) {
    return `<section class="panel exp-section">
      <div class="panel__header"><div class="panel__title">${esc(title)}</div><span class="panel__meta">${esc(t('exp.products', { n: list.length }))}</span></div>
      <p class="exp-intro">${esc(intro)}</p>
      ${list.length ? list.map(product).join('') : empty(emptyText)}
    </section>`;
  }

  // ---------------------------------------------------------------- protocol
  function protocol(proto) {
    if (!proto) {
      return `<section class="panel exp-section"><div class="panel__header"><div class="panel__title">${esc(t('exp.protocol'))}</div></div>
        ${empty(t('exp.noProtocol'))}</section>`;
    }
    const exps = (proto.experiments || []).map((e) => {
      const reports = (e.expected_reports || []).map((r) => `<div class="exp-file">${esc(r.title)} <span class="badge badge--warn">${esc(t('exp.diagram.state.absent'))}</span></div>${table(r.headers || [], r.rows || [], { pending: true })}`).join('')
        || empty(t('exp.noReport'));
      return `<details class="exp-protocol-item">
        <summary><strong>${esc(e.id)}</strong> ${esc(e.title)} ${e.priority ? `<span class="badge badge--info">${esc(e.priority)}</span>` : ''}</summary>
        ${e.hypothesis ? `<p><strong>${esc(t('exp.hypothesis'))}</strong> ${esc(e.hypothesis)}</p>` : ''}
        ${e.success_criterion ? `<p><strong>${esc(t('exp.successCriterion'))}</strong> ${esc(e.success_criterion)}</p>` : ''}
        ${e.cost ? `<p><strong>${esc(t('exp.estimatedCost'))}</strong> ${esc(e.cost)}</p>` : ''}
        ${reports}
      </details>`;
    }).join('');
    return `<section class="panel exp-section">
      <div class="panel__header"><div class="panel__title">${esc(t('exp.protocol'))}</div><span class="panel__meta">${esc(proto.file)} · v${esc(String(proto.revision).padStart(2, '0'))}</span></div>
      ${proto.validation_scheme ? `<p class="exp-intro"><strong>${esc(t('exp.validationScheme'))}</strong> ${esc(proto.validation_scheme)}</p>` : ''}
      <p class="exp-intro">${esc(t('exp.expectedReports'))}</p>
      ${exps || empty(t('exp.noExperiments'))}
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
    const sysLabel = { macos: 'macOS', linux: 'Linux', wsl: 'Windows (WSL)', windows: 'Windows' }[env.system] || t('exp.unknownSystem');
    const badge = st.activated
      ? `<span class="badge badge--ok">${esc(st.source === 'env' ? t('exp.mcp.activeEnv', { env: st.env || 'KAGGLE_API_TOKEN' }) : t('exp.mcp.activeSaved'))}</span>`
      : `<span class="badge badge--warn">${esc(st.problem === 'insecure' ? t('exp.mcp.insecure') : t('exp.mcp.inactive'))}</span>`;
    const files = (st.registered || []).map((f) => `<code>${esc(f)}</code>`).join(', ');
    const registered = (st.registered || []).length ? t('exp.mcp.registeredIn', { files }) : t('exp.mcp.notRegisteredHtml');
    return `<section class="panel exp-mcp" id="expMcpActivation">
      <h3 class="panel__title">${esc(t('exp.mcp.title'))}</h3>
      <p class="exp-intro">${t('exp.mcp.stateHtml', { badge, registered })}</p>
      ${env.system ? `<p class="exp-intro">${t('exp.envDetectedHtml', { system: esc(sysLabel), shell: esc(env.shell || 'sh') })}${env.user ? ` · ${t('exp.envUserHtml', { user: esc(env.user) })}` : ''}.</p>` : ''}
      ${env.note ? `<p class="exp-intro"><span class="badge badge--warn">${esc(sysLabel)}</span> ${esc(env.note)}</p>` : ''}
      <ol>
        <li>${t('exp.mcp.step1Html', { page: esc(st.token_page || 'https://www.kaggle.com/settings') })}</li>
        <li>${t('exp.mcp.step2Html', { command: `<code>${esc(activate)}</code>`, path: `<code>${esc(tokenPath)}</code>`, perms: env.system === 'windows' ? '' : t('exp.mcp.perms') })}</li>
        <li>${t('exp.mcp.step3Html', { env: `<code>${esc(envVar)}</code>`, export: `<code>${esc(env.export_command || `export ${envVar}="$(cat ~/.kaggle/access_token)"`)}</code>`, profile: `<code>${esc(env.profile_file || '~/.profile')}</code>` })}</li>
        <li>${t('exp.mcp.step4Html', { command: `<code>${esc(check)} --verify</code>` })}</li>
      </ol>
      <div class="exp-mcp__actions">
        ${cliButton(activate, t('exp.mcp.activate'))}
        ${cliButton(`${check} --verify`, t('exp.mcp.verify'))}
        <button type="button" class="btn" data-exp-refresh="1">${esc(t('exp.reloadState'))}</button>
      </div>
    </section>`;
  }

  // ---------------------------------------------------------- Colab
  // experiments_view's `remote_colab`: the commands are server constants; the
  // templates keep their placeholders literal and are typed, never run.
  const COLAB_ENV_NOTE = { windows: 'exp.colab.note.windows', wsl: 'exp.colab.note.wsl' };

  function colabActivation(state) {
    if (!state || !state.commands) return '';
    const c = state.commands;
    const env = state.environment || {};
    const sysLabel = { macos: 'macOS', linux: 'Linux', wsl: 'Windows (WSL)', windows: 'Windows' }[env.system] || t('exp.unknownSystem');
    const shellLabel = env.shell === 'powershell' ? 'PowerShell' : (env.shell || 'sh');
    const tiers = (state.paid_tiers || []).map((tier) => `<code>${esc(tier)}</code>`).join(', ');
    const faq = esc(state.faq || 'https://research.google.com/colaboratory/faq.html');
    const registered = (state.registered || []).length
      ? t('exp.colab.registeredHtml', { files: (state.registered || []).map((f) => `<code>${esc(f)}</code>`).join(', ') })
      : t('exp.colab.notRegisteredHtml');
    const note = COLAB_ENV_NOTE[env.system] ? t(COLAB_ENV_NOTE[env.system]) : '';
    return `<section class="panel exp-mcp" id="expColabActivation">
      <h3 class="panel__title">${esc(t('exp.colab.title'))}</h3>
      <p class="exp-intro">${t('exp.colab.officialHtml', { server: esc(state.server || 'colab'), registered })}</p>
      ${env.system ? `<p class="exp-intro">${t('exp.envDetectedHtml', { system: esc(sysLabel), shell: esc(shellLabel) })}.</p>` : ''}
      ${note ? `<p class="exp-intro"><span class="badge badge--warn">${esc(sysLabel)}</span> ${esc(note)}</p>` : ''}
      <ol>
        <li>${t('exp.colab.step1Html', { command: `<code>${esc(c.install)}</code>` })}</li>
        <li>${t('exp.colab.step2Html', { command: `<code>${esc(c.team_add)}</code>`, tiers })}</li>
        <li>${t('exp.colab.step3Html', { command: `<code>${esc(c.login)}</code>` })}</li>
        <li>${t('exp.colab.step4Html', { status: `<code>${esc(c.status)}</code>`, list: `<code>${esc(c.team_list)}</code>` })}</li>
        <li>${t('exp.colab.step5Html')}</li>
      </ol>
      <h4 class="exp-h4">${esc(t('exp.colab.teamRule'))}</h4>
      <ul>
        <li>${t('exp.colab.rule1Html', { faq })}</li>
        <li>${t('exp.colab.rule2Html', { tiers })}</li>
        <li>${esc(t('exp.colab.rule3'))}</li>
      </ul>
      <h4 class="exp-h4">${esc(t('exp.colab.gpuByTier'))}</h4>
      <ul>
        <li>${esc(t('exp.colab.gpuFree'))}</li>
        <li>${t('exp.colab.gpuPaidHtml')}</li>
      </ul>
      <div class="exp-mcp__actions">
        ${cliButton(c.install, t('exp.colab.install'))}
        ${cliButton(c.team_add, t('exp.colab.addPerson'), false)}
        ${cliButton(c.login, t('exp.colab.login'), false)}
        ${cliButton(c.status, t('exp.colab.check'))}
        ${cliButton(c.team_list, t('exp.colab.team'))}
        <button type="button" class="btn" data-exp-refresh="1">${esc(t('exp.reloadState'))}</button>
      </div>
    </section>`;
  }

  // ------------------------------------------------------- remote services
  // One offline row per service (experiments_view's `remote_services`). The
  // action is a server-side constant, run in the CLI assistant like the MCP box.
  const SERVICE_STATE = {
    active: ['badge--ok', 'exp.service.active'], inactive: ['badge--warn', 'exp.service.inactive'],
    missing: ['badge--warn', 'exp.service.missing'], unverified: ['badge--info', 'exp.service.unverified'],
  };

  function remoteServices(state) {
    const rows = state && Array.isArray(state.rows) ? state.rows : [];
    if (!rows.length) return '';
    const body = rows.map((row) => {
      const [cls, stateLabel] = SERVICE_STATE[row.state] || SERVICE_STATE.unverified;
      const label = row.badge || t(stateLabel);
      const action = row.action && row.action.command
        ? cliButton(row.action.command, row.action.label || t('exp.run'))
        : '<span class="exp-muted">—</span>';
      return `<tr><td><strong>${esc(row.service)}</strong></td><td>${esc(row.purpose)}</td>`
        + `<td><span class="badge ${esc(cls)}">${esc(label)}</span>${row.detail ? ` <small>${esc(row.detail)}</small>` : ''}</td>`
        + `<td>${action}</td></tr>`;
    }).join('');
    return `<section class="panel exp-services" id="expRemoteServices">
      <h3 class="panel__title">${esc(t('exp.services.title'))}</h3>
      ${state.note ? `<p class="exp-intro">${esc(state.note)}</p>` : ''}
      <div class="table-responsive"><table class="table exp-table"><thead><tr><th>${esc(t('exp.services.service'))}</th><th>${esc(t('exp.services.purpose'))}</th><th>${esc(t('exp.col.state'))}</th><th>${esc(t('exp.services.action'))}</th></tr></thead>
      <tbody>${body}</tbody></table></div>
      <div class="exp-mcp__actions"><button type="button" class="btn" data-exp-refresh="1">${esc(t('exp.reloadState'))}</button></div>
    </section>`;
  }

  // ------------------------------------------------------- local environment
  // experiments_view's `local_environment`: the workspace micromamba env and
  // each target's .venv, its declared libraries (installed or missing) and device.
  const ENV_STATE = {
    ready: ['badge--ok', 'exp.env.ready'], incomplete: ['badge--warn', 'exp.env.incomplete'],
    missing: ['badge--warn', 'exp.service.missing'], unverified: ['badge--info', 'exp.service.unverified'],
  };

  function localEnvironment(state) {
    if (!state) return '';
    const ws = state.workspace || null;
    const targets = Array.isArray(state.targets) ? state.targets : [];
    const envBadge = (st) => {
      const [cls, label] = ENV_STATE[st] || ENV_STATE.unverified;
      return `<span class="badge ${esc(cls)}">${esc(t(label))}</span>`;
    };
    const rows = [];
    if (ws) {
      const mm = ws.micromamba ? `<small>${t('exp.env.micromambaAtHtml', { path: esc(ws.micromamba) })}</small>` : `<small>${esc(t('exp.env.noMicromamba'))}</small>`;
      rows.push(`<tr><td><strong>${esc(ws.label || t('exp.env.workspace'))}</strong><br><code>${esc(ws.path)}</code></td>`
        + `<td>${esc(ws.python || '—')}</td><td>${envBadge(ws.state)} ${ws.detail ? `<small>${esc(ws.detail)}</small>` : ''}</td>`
        + `<td>${mm}</td><td><span class="exp-muted">—</span></td></tr>`);
    }
    targets.forEach((target) => {
      const libs = (target.libraries || []).map((lib) => (lib.version
        ? `<span class="badge badge--ok">${esc(lib.name)} ${esc(lib.version)}</span>`
        : `<span class="badge badge--warn">${esc(t('exp.env.libMissing', { name: lib.name }))}</span>`)).join(' ')
        || (target.required && target.required.length ? `<small>${esc(target.required.join(', '))}</small>` : `<span class="exp-muted">${esc(t('exp.env.noLibs'))}</span>`);
      rows.push(`<tr><td><strong>${esc(target.repo)}</strong><br><code>${esc(target.path)}</code></td>`
        + `<td>${esc(target.python || '—')}</td><td>${envBadge(target.state)} ${target.detail ? `<small>${esc(target.detail)}</small>` : ''}</td>`
        + `<td>${libs}</td><td>${esc(target.device || '—')}</td></tr>`);
    });
    const body = rows.length ? rows.join('') : '';
    return `<section class="panel exp-local" id="expLocalEnv">
      <h3 class="panel__title">${esc(t('exp.env.title'))}</h3>
      <p class="exp-intro">${t('exp.env.introHtml')}${state.note ? ` ${esc(state.note)}` : ''}</p>
      ${body ? `<div class="table-responsive"><table class="table exp-table"><thead><tr><th>${esc(t('exp.env.col.env'))}</th><th>Python</th><th>${esc(t('exp.col.state'))}</th><th>${esc(t('exp.env.col.libs'))}</th><th>${esc(t('exp.env.col.device'))}</th></tr></thead>
      <tbody>${body}</tbody></table></div>` : empty(t('exp.env.none'))}
    </section>`;
  }

  // ------------------------------------------------------------ run options
  // experiments_view's `run_options`: one row per stage and host, the estimate
  // from that host's own Results/timing.json measurements (±20%) or "unmeasured".
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
        const avail = r.available ? `<span class="badge badge--ok">${esc(t('common.yes'))}</span>` : `<span class="badge badge--warn">${esc(t('common.no'))}</span>`;
        const est = r.estimate
          ? `${esc(r.estimate_label)}<br><small>${esc(t('exp.runs.measurements', { n: r.estimate.measurements }))}${(r.estimate.devices || []).length ? ` · ${esc(r.estimate.devices.join(', '))}` : ''}</small>`
          : `<span class="badge badge--info">${esc(r.estimate_label || t('exp.unmeasured'))}</span>`;
        const recCell = i === 0
          ? `<td rowspan="${list.length}">${rec.poc_budget === 'exceeds' ? `<span class="badge badge--warn">${esc(t('exp.runs.exceeds5h'))}</span> ` : ''}${rec.host ? `<strong>${esc((list.find((x) => x.host === rec.host) || {}).host_label || rec.host)}</strong> ` : ''}<small>${esc(rec.text || '—')}</small></td>`
          : '';
        const stageCell = i === 0 ? `<td rowspan="${list.length}"><strong>${esc(r.stage_label || r.stage)}</strong></td>` : '';
        return `<tr>${stageCell}<td>${esc(r.host_label || r.host)}</td><td>${avail}</td><td>${est}</td><td><small>${esc(r.reason)}</small></td>${recCell}</tr>`;
      }).join('');
    }).join('');
    const hint = state.empty ? `<p class="exp-intro"><span class="badge badge--warn">${esc(t('exp.unmeasured'))}</span> ${esc(state.empty_hint || t('exp.runs.emptyHint'))}</p>` : '';
    const sources = (state.sources || []).length
      ? `<p class="exp-intro">${esc(t('exp.runs.sources'))} ${(state.sources || []).map((f) => `<a href="${artifactUrl(f)}" target="_blank" rel="noopener"><code>${esc(f)}</code></a>`).join(', ')}</p>`
      : '';
    const candidates = runCandidates(state, stages.length ? stages : ['poc', 'full'], rows);
    return `<section class="panel exp-run-options" id="expRunOptions">
      <h3 class="panel__title">${esc(t('exp.runs.title'))}</h3>
      <p class="exp-intro">${esc(t('exp.runs.intro', { note: state.note || '±20%, single-probe extrapolation' }))}</p>
      <p class="exp-intro">${esc(t('exp.runs.rules', { min: Math.round((state.local_limit_seconds || 1200) / 60), hours: Math.round((state.poc_budget_seconds || 18000) / 3600) }))}</p>
      ${hint}${sources}
      ${body ? `<div class="table-responsive"><table class="table exp-table"><thead><tr><th>${esc(t('exp.runs.stage'))}</th><th>Host</th><th>${esc(t('exp.runs.available'))}</th><th>${esc(t('exp.runs.estimate'))}</th><th>${esc(t('exp.runs.reason'))}</th><th>${esc(t('exp.runs.recommendation'))}</th></tr></thead>
      <tbody>${body}</tbody></table></div>` : ''}
      ${candidates}
    </section>`;
  }

  // run_options' `candidates` and `plan_picks`: one row per candidate (measured
  // or not) and the latest recorded `plan`'s pick per stage, with its reason.
  function runCandidates(state, stages, rows) {
    const list = Array.isArray(state.candidates) ? state.candidates : [];
    if (!list.length) return '';
    const picks = state.plan_picks || {};
    const stageLabel = (stage) => ((rows.find((r) => r.stage === stage) || {}).stage_label || stage);
    const settings = (value) => Object.entries(value || {}).map(([k, v]) => `${esc(k)}=${esc(v)}`).join(', ');
    const anyPick = stages.some((stage) => picks[stage]);
    const pickLines = stages.map((stage) => {
      const pick = picks[stage];
      if (!pick) return '';
      const where = pick.processes > 1 ? ` · ${esc(t('exp.cand.processes', { n: pick.processes }))}` : '';
      const accounts = (pick.accounts || []).length ? ` · ${esc(t('exp.cand.accounts', { list: pick.accounts.join(', ') }))}` : '';
      return `<p class="exp-intro"><strong>${esc(stageLabel(stage))}</strong> · Plan: <strong>${esc(pick.option)}</strong> (${esc(pick.device || '—')}${where}${accounts}), ${esc(pick.label || '—')}${settings(pick.settings) ? ` · ${settings(pick.settings)}` : ''}<br><small>${esc(pick.reason || '')}</small></p>`;
    }).join('');
    const body = stages.map((stage) => list.filter((c) => c.stage === stage).map((c, i, all) => {
      const status = c.status === 'measured'
        ? `<span class="badge badge--ok">${esc(labelOf('exp.cand.status', c.status))}</span>`
        : `<span class="badge badge--info">${esc(labelOf('exp.cand.status', c.status || 'unmeasured'))}</span>`;
      const plan = c.plan === 'recommended' ? `<span class="badge badge--ok">${esc(labelOf('exp.cand.plan', c.plan))}</span>` : `<small>${esc(c.plan || '')}</small>`;
      const detail = [c.processes ? esc(t('exp.cand.processCount', { n: c.processes })) : '', settings(c.settings),
        c.load_share != null ? esc(t('exp.cand.load', { pct: Math.round(c.load_share * 100) })) : ''].filter(Boolean).join(' · ');
      const stageCell = i === 0 ? `<td rowspan="${all.length}"><strong>${esc(stageLabel(stage))}</strong></td>` : '';
      return `<tr>${stageCell}<td><code>${esc(c.candidate)}</code></td><td>${esc(c.device || '—')}</td><td>${status}</td><td>${esc(c.estimate_label || t('exp.unmeasured'))}</td><td><small>${detail || '—'}</small></td><td><small>${esc(c.reason || '')}</small></td><td>${plan}</td></tr>`;
    }).join('')).join('');
    return `<h4 class="exp-h4">${esc(t('exp.cand.title'))}</h4>
      <p class="exp-intro">${t('exp.cand.introHtml')}</p>
      ${anyPick ? pickLines : `<p class="exp-intro"><span class="badge badge--warn">${esc(t('exp.cand.noPlan'))}</span> ${esc(state.plan_hint || t('exp.cand.noPlanRecorded'))}</p>`}
      <div class="table-responsive"><table class="table exp-table"><thead><tr><th>${esc(t('exp.runs.stage'))}</th><th>${esc(t('exp.cand.candidate'))}</th><th>${esc(t('exp.env.col.device'))}</th><th>${esc(t('exp.col.state'))}</th><th>${esc(t('exp.cand.estimate'))}</th><th>${esc(t('exp.cand.settings'))}</th><th>${esc(t('exp.runs.reason'))}</th><th>Plan</th></tr></thead>
      <tbody>${body}</tbody></table></div>`;
  }

  // ---------------------------------------------------------------- team
  // remote_services' `team`: owner slugs and presence flags only.
  const TEAM_TIER = { free: 'badge--info', pro: 'badge--ok', payg: 'badge--ok', enterprise: 'badge--ok' };

  function team(state) {
    if (!state) return '';
    const members = Array.isArray(state.members) ? state.members : [];
    const title = `<h3 class="panel__title">${esc(t('exp.team.title'))}</h3>`;
    const intro = `<p class="exp-intro">${t('exp.team.introHtml', { file: esc(state.file || '.papersmith/team.json') })}</p>`;
    if (state.problem) {
      return `<section class="panel exp-team" id="expTeam">${title}${intro}`
        + `<p class="exp-intro">${t('exp.team.unreadableHtml')}</p></section>`;
    }
    if (!members.length) {
      return `<section class="panel exp-team" id="expTeam">${title}${intro}`
        + empty(t('exp.team.noMembers', { command: state.add_command || 'smith team add' })) + '</section>';
    }
    const rows = members.map((m) => {
      const kaggle = m.kaggle_username
        ? `<code>${esc(m.kaggle_username)}</code> ${m.kaggle_validated ? `<span class="badge badge--ok">${esc(t('exp.team.validated'))}</span>` : `<span class="badge badge--warn">${esc(t('exp.team.notValidated'))}</span>`}`
        : '<span class="exp-muted">—</span>';
      const colab = m.colab_tier
        ? `<span class="badge ${esc(TEAM_TIER[m.colab_tier] || 'badge--warn')}">${esc(m.colab_tier)}</span> ${m.colab_config_present ? `<small>${esc(t('exp.team.sessionSet'))}</small>` : `<small>${esc(t('exp.team.notSignedIn'))}</small>`}`
        : '<span class="exp-muted">—</span>';
      const names = { kaggle: 'Kaggle', colab: 'Colab' };
      const eligible = (m.eligible || []).length
        ? (m.eligible || []).map((s) => `<span class="badge badge--ok">${esc(names[s] || s)}</span>`).join(' ')
        : `<span class="badge">${esc(t('common.no'))}</span>`;
      return `<tr><td><code>${esc(m.owner)}</code></td><td>${esc(m.display_name || '')}</td><td>${kaggle}</td><td>${colab}</td><td>${eligible}</td></tr>`;
    }).join('');
    const skipped = state.skipped ? `<p class="exp-intro"><span class="badge badge--warn">${esc(t('exp.team.skipped', { n: state.skipped }))}</span> ${esc(t('exp.team.skippedWhy'))}</p>` : '';
    return `<section class="panel exp-team" id="expTeam">${title}${intro}${skipped}
      <div class="table-responsive"><table class="table exp-table"><thead><tr><th>${esc(t('exp.team.owner'))}</th><th>${esc(t('exp.team.name'))}</th><th>Kaggle</th><th>Colab</th><th>${esc(t('exp.team.eligible'))}</th></tr></thead>
      <tbody>${rows}</tbody></table></div></section>`;
  }

  // ---------------------------------------------------------------- help
  function help(accounts) {
    const k = accounts || {};
    const status = `<p class="exp-intro">${esc(t('exp.help.localState'))}
      ${k.accounts_store_present ? `<span class="badge badge--ok">${esc(t('exp.help.present'))}</span>` : `<span class="badge badge--warn">${esc(t('exp.help.absent'))}</span>`}
      · ${t('exp.help.inboxHtml', { inbox: esc(k.inbox || 'kaggle-inbox'), n: esc(k.inbox_count ?? 0) })}</p>`;
    return `<details class="panel exp-help">
      <summary class="panel__title">${esc(t('exp.help.title'))}</summary>
      ${status}
      ${t('exp.help.bodyHtml')}
    </details>`;
  }

  // ---------------------------------------------------------------- datasets
  const DATASET_LICENSE = {
    allowed: ['badge--ok', 'exp.ds.license.allowed'], overridden: ['badge--warn', 'exp.ds.license.overridden'],
    refused: ['badge--warn', 'exp.ds.license.refused'],
  };
  const DATASET_QC = { pass: ['badge--ok', 'exp.ds.qc.pass'], warn: ['badge--warn', 'exp.ds.qc.warn'], fail: ['badge--warn', 'exp.ds.qc.fail'] };
  // pair: [badge class, catalogue key]; fallback: a catalogue key too.
  const badge = (pair, fallback) => {
    const [cls, key] = pair || ['badge--info', fallback];
    return `<span class="badge ${esc(cls)}">${esc(t(key))}</span>`;
  };

  function datasets(state) {
    const d = state || {};
    const items = Array.isArray(d.items) ? d.items : [];
    const intro = `<p class="exp-intro">${t('exp.ds.introHtml')}</p>`;
    if (!items.length) {
      return `<section class="panel exp-datasets"><h3 class="panel__title">${esc(t('exp.ds.title'))}</h3>${intro}`
        + empty(t('exp.ds.none'))
        + '</section>';
    }
    const rows = items.map((item) => {
      const remote = item.remote_ref
        ? `<code>${esc(item.remote_ref)}</code> ${badge(item.visibility === 'public' ? ['badge--warn', 'exp.ds.public'] : ['badge--ok', 'exp.ds.private'])}${item.remote_version != null ? ` <small>v${esc(item.remote_version)}</small>` : ''}`
        : `<span class="badge badge--info">${esc(t('exp.ds.unpublished'))}</span>`;
      const prep = item.prepared
        ? `<span class="badge badge--ok">${esc(t('exp.ds.prepared'))}${item.preparation_version != null ? ` v${esc(item.preparation_version)}` : ''}</span>`
        : `<span class="badge badge--info">${esc(t('exp.ds.unprepared'))}</span>`;
      return `<tr><td><code>${esc(item.slug)}</code></td>`
        + `<td>${badge(item.role === 'toy' ? ['badge--info', 'exp.ds.toy'] : ['badge--info', 'exp.ds.full'])}</td>`
        + `<td>${esc(item.title)}</td>`
        + `<td>${badge(DATASET_LICENSE[item.license], 'exp.ds.noLicense')}${item.host_license ? ` <small>${esc(item.host_license)}</small>` : ''}</td>`
        + `<td>${badge(DATASET_QC[item.qc], 'exp.ds.noQc')}</td><td>${prep}</td><td>${remote}</td></tr>`;
    }).join('');
    const searches = (d.searches || []).length
      ? `<p class="exp-intro">${esc(t('exp.ds.searches'))} ${(d.searches || []).map((f) => `<a href="${artifactUrl(f)}" target="_blank" rel="noopener"><code>${esc(f)}</code></a>`).join(', ')}</p>`
      : '';
    return `<section class="panel exp-datasets"><h3 class="panel__title">${esc(t('exp.ds.title'))}</h3>${intro}
      <div class="table-responsive"><table class="table exp-table"><thead><tr><th>Slug</th><th>${esc(t('exp.ds.role'))}</th><th>${esc(t('exp.ds.titleCol'))}</th><th>${esc(t('exp.ds.license'))}</th><th>QC</th><th>${esc(t('exp.ds.preparation'))}</th><th>${esc(t('exp.ds.remote'))}</th></tr></thead>
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
      attention(v),
      mcpActivation(v.remote_mcp),
      colabActivation(v.remote_colab),
      remoteServices(v.remote_services),
      localEnvironment(v.local_environment),
      runOptions(v.run_options),
      team(v.remote_services && v.remote_services.team),
      help(v.remote_accounts),
      datasets(v.datasets),
      group(t('exp.group.poc'), t('exp.group.pocIntro'), poc, t('exp.group.pocEmpty')),
      group(t('exp.group.full'), t('exp.group.fullIntro'), full, t('exp.group.fullEmpty')),
      other.length ? group(t('exp.group.other'), t('exp.group.otherIntro'), other, '') : '',
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
      host.innerHTML = empty(t('exp.readFailed', { error: err.message }));
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

  // Server labels come back in the chosen language: fetch again once drawn.
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('languagechange', () => { if (lastView) refreshExperimentsPanel(); });
  }

  window.refreshExperimentsPanel = refreshExperimentsPanel;
  window.ExperimentsPanel = { render, mcpActivation, colabActivation, remoteServices, localEnvironment, runOptions, team, datasets };
})();
