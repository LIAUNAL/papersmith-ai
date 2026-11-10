/* Model tab modules drawn from the workspace's own specification.
 *
 * GET /api/model answers `.papersmith/model_spec.json` when the workspace has
 * one, else a neutral specification named after `papersmith.yaml`. This file
 * renders its problem tree (direct causes, central problem, effects), its tree
 * of pillars and hypotheses, novelty pillars, hypotheses, concept-map layers and proof-of-
 * concept experiments, each idea with its SOTA citations (citations.js), and the contribution type the paper-reviewer
 * assigned to the proposal (`contribution_type`); when a part is absent it says what produces it instead
 * of showing anybody else's content. Every value is escaped before insertion;
 * prose fields go through math-panel.js's richText, so $…$ compiles with KaTeX.
 *
 * A specification the server flags with `language_notice` (its prose is not
 * English) is still drawn as written, under a notice in the dashboard's
 * language. A language switch repaints the panel from the last spec.
 *
 * Above the modules, a stepper (GET /api/model/steps) forces Phase 4's order:
 * the problem and its pillars, then the hypotheses, then the mathematics, then
 * the SOTA citations, then the judge-reviewer. Each step's button types `/proposal-deliberation <the
 * step's instruction>` into the agent terminal (window.sendToCli); the
 * mathematics step also offers `/math-tutor`, and the judge's button repeats on
 * the contribution-type card, where its verdict appears. A locked step's
 * buttons are disabled and say what the step requires.
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

  // An idea's SOTA citations, drawn beside it (citations.js).
  const cites = (key) => (window.Citations ? window.Citations.block(key) : '');
  const ideaId = (item, prefix, n) => String(item.id ?? '').trim() || `${prefix}${n}`;

  const treeNode = (kind, label, text, key, extra = '') => `<div class="concept-tree__node concept-tree__node--${kind}">
      <span class="badge">${esc(label)}</span>
      <p>${rich(text)}</p>
      ${extra}${key ? cites(key) : ''}
    </div>`;
  const treeRow = (title, nodes) => `<div class="concept-tree__level">
      <h5>${esc(title)}</h5>
      <div class="concept-tree__row">${nodes}</div>
    </div>`;
  const listed = (value) => (Array.isArray(value) ? value.map((v) => String(v)) : []);

  // What the two trees still owe, as citations.py words it.
  function treeFindings() {
    const found = window.Citations ? window.Citations.trees() : [];
    if (!found.length) return '';
    return `<div class="model-step__reason">⚠ ${esc(t('conceptTree.findings'))}
        <ul style="margin: 0.25rem 0 0; padding-left: 1rem;">${found.map((f) => `<li>${esc(f)}</li>`).join('')}</ul>
      </div>`;
  }

  const centralText = (spec) => {
    const tree = (spec.novelty || {}).problem_tree;
    return tree && tree.central ? String(tree.central.text || '').trim() : '';
  };

  // Morfeo's tree, read from the top: direct causes, central problem, effects.
  function problemTree(spec) {
    const central = centralText(spec);
    if (!central) return treeFindings();
    const tree = spec.novelty.problem_tree;
    const entries = (value) => (Array.isArray(value) ? value : []);
    const effects = entries(tree.effects).filter((e) => e && e.text).map((e, i) => {
      const from = listed(e.caused_by).join(', ');
      return treeNode('effect', ideaId(e, 'EF', i + 1), e.text, '',
        from ? `<small>${esc(t('conceptTree.causedBy', { ids: from }))}</small>` : '');
    }).join('');
    const causes = entries(tree.causes).filter((c) => c && c.text).map((c, i) => {
      const id = ideaId(c, 'DC', i + 1);
      return treeNode('cause', id, c.text, `cause:${id}`);
    }).join('');
    return `<div class="concept-tree">
        <h4 class="concept-tree__title">${esc(t('conceptTree.problem'))}</h4>
        ${treeRow(t('conceptTree.causes'), causes)}
        ${treeRow(t('conceptTree.central'), treeNode('central', t('conceptTree.centralBadge'), central, 'problem:central'))}
        ${treeRow(t('conceptTree.effects'), effects)}
      </div>${treeFindings()}`;
  }

  // Pillars over hypotheses, an arrow from each pillar to every hypothesis it
  // supports. The arrows are drawn after layout, from the boxes' real edges
  // (drawNoveltyArrows), so they meet the boxes at any text size or width.
  function noveltyTree(spec) {
    const novelty = spec.novelty || {};
    const pillarList = (novelty.pillars || []).filter((p) => p && (p.name || p.summary));
    const hypothesisList = (novelty.hypotheses || []).filter((h) => h && (h.title || h.statement));
    const ids = pillarList.map((p, i) => ideaId(p, 'P', i + 1));
    const tones = pillarList.map((p, i) => colour(p.color, ['#38bdf8', '#a78bfa', '#34d399', '#f59e0b', '#f472b6'][i % 5]));
    const hids = hypothesisList.map((h, j) => ideaId(h, 'H', j + 1));
    const links = hypothesisList.flatMap((h, j) => listed(h.pillars)
      .filter((name) => ids.includes(name))
      .map((name) => ({ from: name, to: hids[j], tone: tones[ids.indexOf(name)] })));
    if (!links.length) return '';
    const kind = (label, id, extra = '') => `<div class="concept-tree__kind"><span>${esc(t(label))} · ${esc(id)}</span>${extra}</div>`;
    const pillarNodes = pillarList.map((p, i) => {
      const to = links.filter((link) => link.from === ids[i]).map((link) => link.to);
      return `<div class="concept-tree__node concept-tree__node--pillar" data-tree-node="${esc(ids[i])}" style="--tone: ${tones[i]};">
        ${kind('conceptTree.pillar', ids[i], p.badge ? `<span class="concept-tree__tag">${esc(p.badge)}</span>` : '')}
        <p class="concept-tree__name">${rich(p.name || p.summary)}</p>
        ${p.name && p.summary ? `<p class="concept-tree__text">${rich(p.summary)}</p>` : ''}
        ${to.length ? `<small>${esc(t('conceptTree.supports', { ids: to.join(', ') }))}</small>` : ''}
      </div>`;
    }).join('');
    const hypothesisNodes = hypothesisList.map((h, j) => {
      const from = listed(h.pillars).filter((name) => ids.includes(name));
      return `<div class="concept-tree__node concept-tree__node--hypothesis" data-tree-node="${esc(hids[j])}">
        ${kind('conceptTree.hypothesis', hids[j])}
        <p class="concept-tree__name">${rich(h.title || h.statement)}</p>
        ${h.title && h.statement ? `<p class="concept-tree__text">${rich(h.statement)}</p>` : ''}
        ${from.length ? `<small>${esc(t('conceptTree.supportedBy', { ids: from.join(', ') }))}</small>` : ''}
      </div>`;
    }).join('');
    const markers = tones.map((tone, i) => `<marker id="ctArrow${i}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${tone}"></path></marker>`).join('');
    const arrows = links.map((link) => `<path class="concept-tree__arrow" data-from="${esc(link.from)}" data-to="${esc(link.to)}" style="stroke: ${link.tone};" marker-end="url(#ctArrow${ids.indexOf(link.from)})"></path>`).join('');
    return `<div class="concept-tree concept-tree--novelty" data-novelty-tree>
        <h4 class="concept-tree__title">${esc(t('conceptTree.novelty'))}</h4>
        <p class="concept-tree__legend">${esc(t('conceptTree.legend'))}</p>
        <div class="concept-tree__level"><h5>${esc(t('conceptTree.pillarsLevel'))}</h5>
          <div class="concept-tree__grid">${pillarNodes}</div></div>
        <div class="concept-tree__level"><h5>${esc(t('conceptTree.hypothesesLevel'))}</h5>
          <div class="concept-tree__grid">${hypothesisNodes}</div></div>
        <svg class="concept-tree__arrows" aria-hidden="true"><defs>${markers}</defs>${arrows}</svg>
      </div>`;
  }

  // Each arrow leaves the bottom edge of its pillar and lands on the top edge
  // of its hypothesis; several arrows on one edge spread apart so none hides
  // another. Pointing at a box brings its arrows forward.
  function drawNoveltyArrows() {
    if (typeof document === 'undefined' || !document.querySelectorAll) return;
    document.querySelectorAll('[data-novelty-tree]').forEach((tree) => {
      const svg = tree.querySelector('.concept-tree__arrows');
      const box = tree.getBoundingClientRect();
      if (!svg || !box.width) return;
      // One column (a phone, or very large text): arrows would run behind the
      // boxes, so the "Supports" and "Supported by" lines carry the links.
      const pillarBoxes = Array.from(tree.querySelectorAll('.concept-tree__node--pillar'), (node) => node.getBoundingClientRect());
      const stacked = pillarBoxes.length > 1 && pillarBoxes.every((rect) => Math.abs(rect.left - pillarBoxes[0].left) < 1);
      tree.classList.toggle('is-stacked', stacked);
      if (stacked) return;
      svg.setAttribute('viewBox', `0 0 ${box.width} ${box.height}`);
      const nodes = new Map(Array.from(tree.querySelectorAll('[data-tree-node]'),
        (node) => [node.dataset.treeNode, node.getBoundingClientRect()]));
      const paths = Array.from(svg.querySelectorAll('.concept-tree__arrow'));
      const spread = (key) => {
        const group = paths.reduce((acc, path) => { (acc[path.dataset[key]] = acc[path.dataset[key]] || []).push(path); return acc; }, {});
        return (path) => {
          const peers = group[path.dataset[key]];
          return (peers.indexOf(path) - (peers.length - 1) / 2) * 12;
        };
      };
      const out = spread('from');
      const into = spread('to');
      paths.forEach((path) => {
        const a = nodes.get(path.dataset.from);
        const b = nodes.get(path.dataset.to);
        if (!a || !b) return;
        const x1 = a.left + a.width / 2 - box.left + out(path);
        const y1 = a.bottom - box.top;
        const x2 = b.left + b.width / 2 - box.left + into(path);
        const y2 = b.top - box.top - 2;
        const bend = Math.max(18, (y2 - y1) / 2);
        path.setAttribute('d', `M${x1},${y1} C${x1},${y1 + bend} ${x2},${y2 - bend} ${x2},${y2}`);
      });
      if (!tree.dataset.arrowsWired) {
        tree.dataset.arrowsWired = '1';
        if (typeof ResizeObserver === 'function') new ResizeObserver(() => drawNoveltyArrows()).observe(tree);
        tree.addEventListener('mouseover', (event) => {
          const node = event.target.closest && event.target.closest('[data-tree-node]');
          const id = node ? node.dataset.treeNode : '';
          tree.classList.toggle('has-focus', Boolean(id));
          tree.querySelectorAll('.concept-tree__arrow').forEach((path) => {
            path.classList.toggle('is-focus', Boolean(id) && (path.dataset.from === id || path.dataset.to === id));
          });
        });
        tree.addEventListener('mouseleave', () => {
          tree.classList.remove('has-focus');
          tree.querySelectorAll('.concept-tree__arrow.is-focus').forEach((path) => path.classList.remove('is-focus'));
        });
      }
    });
  }
  if (typeof window !== 'undefined' && window.addEventListener) window.addEventListener('resize', drawNoveltyArrows);

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
        ${cites(`pillar:${ideaId(p, 'P', i + 1)}`)}
      </div>`;
    }).join('');
  }

  function hypotheses(spec) {
    const list = ((spec.novelty || {}).hypotheses || []).filter((h) => h && (h.title || h.statement));
    if (!list.length) return empty(t('modelPanel.noHypotheses'));
    return list.map((h, i) => `<div class="model-hypothesis-card">
        <div style="display: flex; justify-content: space-between; gap: 0.5rem;">
          <strong>${esc(h.id || '')} ${rich(h.title || '')}</strong>
          ${h.status ? `<span class="badge">${esc(h.status)}</span>` : ''}
        </div>
        <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.45;">${rich(h.statement)}</p>
        ${h.evidence ? `<p style="font-size: 0.76rem; color: var(--text-muted);">${rich(h.evidence)}</p>` : ''}
        ${cites(`hypothesis:${ideaId(h, 'H', i + 1)}`)}
      </div>`).join('');
  }

  // The five contribution types and their catalogue keys.
  const CONTRIBUTION_TYPE_KEYS = {
    'General': 'contribution.type.General',
    'Theory': 'contribution.type.Theory',
    'Use-Inspired': 'contribution.type.Use-Inspired',
    'Concept & Feasibility': 'contribution.type.Concept & Feasibility',
    'Negative Results': 'contribution.type.Negative Results',
  };

  // The button that launches the judge, on the card its verdict lands on. Until
  // the stepper answers, or while the citations are missing, it stays disabled.
  function judgeButton(judged) {
    const step = (lastSteps || []).find((s) => s.id === 'judge_review');
    const open = step && step.status !== 'LOCKED';
    const off = open ? '' : ' disabled aria-disabled="true"';
    const reason = step && !open
      ? `<p class="model-step__reason">🔒 ${esc(t('modelSteps.requires', { step: t('modelSteps.sotaCitations') }))}</p>` : '';
    return `${reason}<div class="model-step__actions" style="margin-top: 0.6rem;">
        <button type="button" class="btn ${judged ? '' : 'btn--primary '}btn--sm" data-model-step="judge_review"${off}>${esc(t(judged ? 'modelSteps.judgeAgain' : 'modelSteps.judge'))}</button>
      </div>`;
  }

  // The paper-reviewer's contribution type for the proposal, after
  // the hypotheses it was read from.
  function contributionType(spec) {
    const ct = spec.contribution_type;
    const head = `<h4 style="font-size: 0.78rem; text-transform: uppercase; color: var(--text-dim); letter-spacing: 0.04em; margin-bottom: 0.6rem;">${esc(t('contribution.title'))}</h4>`;
    if (!ct || !CONTRIBUTION_TYPE_KEYS[ct.type]) return head + empty(t('contribution.owed', { artifact: '.papersmith/model_spec.json' })) + judgeButton(false);
    return `${head}<div class="model-hypothesis-card">
        <span class="badge">${esc(t(CONTRIBUTION_TYPE_KEYS[ct.type]))}</span>
        <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.45;"><strong>${esc(t('contribution.why'))}</strong> ${esc(ct.why)}</p>
        ${window.ContributionAffinity ? window.ContributionAffinity.html(ct) : ''}
      </div>${judgeButton(true)}`;
  }

  function layers(spec) {
    const source = spec.concept_map || spec.conceptual_map || {};
    const list = (source.layers || []).filter(Boolean);
    if (!list.length) return empty(t('modelPanel.noLayers'));
    return list.map((layer, i) => {
      const c = colour(layer.color, '#38bdf8');
      const name = layer.name || layer.layer || t('modelPanel.layerN', { n: i + 1 });
      const key = String(layer.name || '').trim() || String(layer.layer || '').trim() || `L${i + 1}`;
      const nodes = (layer.nodes || []).map((n) => `<div class="concept-node" title="${esc(n.desc)}">
          <strong>${rich(n.name)}</strong>${n.desc ? `<span>${rich(n.desc)}</span>` : ''}</div>`).join('');
      return `<div class="concept-layer-card" style="--tone: ${c}; border-left: 4px solid ${c};">
          <div style="display: flex; justify-content: space-between; gap: 0.5rem; align-items: baseline;">
            <strong class="tone-ink">${rich(name)}</strong>
            ${layer.tag ? `<span class="badge">${esc(layer.tag)}</span>` : ''}
          </div>
          <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.45;">${rich(layer.description || layer.desc || '')}</p>
          ${nodes ? `<div class="concept-node-grid">${nodes}</div>` : ''}
          ${cites(`layer:${key}`)}
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
  let lastSteps = null;

  function renderModelModules(spec) {
    lastSpec = spec || {};
    const put = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
    put('modelProblemTree', problemTree(lastSpec));
    put('modelNoveltyTree', noveltyTree(lastSpec));
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(drawNoveltyArrows);
    const statement = document.getElementById('modelProblemStatementText');
    if (statement) statement.hidden = Boolean(centralText(lastSpec));
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
    sota_citations: 'modelSteps.sotaCitations',
    judge_review: 'modelSteps.judgeReview',
  };
  const STATUS_LABELS = {
    PASS: 'modelSteps.status.pass',
    ACTIVE: 'modelSteps.status.active',
    LOCKED: 'modelSteps.status.locked',
  };
  // What each button types into the agent terminal (agent input stays English).
  const STEP_COMMANDS = {
    problem_pillars: '/proposal-deliberation Let us define the central problem and its pillars first: '
      + 'build the problem tree in novelty.problem_tree, in technical English (the central problem, 2 to 3 direct '
      + 'causes and their effects), '
      + 'and decompose it into at least 2 novelty pillars before any hypothesis.',
    hypotheses: '/proposal-deliberation Now the hypotheses: for each agreed pillar, the testable prediction it makes, '
      + 'naming its pillars, in technical English, and record them in the revision and in .papersmith/model_spec.json.',
    mathematics: '/proposal-deliberation Now the mathematics: formalize the agreed hypotheses as $$ ... \\tag{N} $$ '
      + 'display blocks in the next revision.',
    sota_citations: '/proposal-deliberation Justify the proposal with SOTA citations now: in .papersmith/citations.json, '
      + 'give the central problem, every direct cause, pillar, hypothesis, concept-map layer and numbered equation '
      + '2 to 5 references of sota-pool/candidates.json, each with the reason it supports the idea and a verbatim quote of its abstract that holds it; the problem, '
      + 'causes, pillars and hypotheses take Q1 or Q2 journal articles at most 4 years old, so run '
      + '`python skills/_core/results/citations_cli.py rank --root .` first. Then fix what '
      + '`python skills/_core/results/citations_cli.py check --root .` still reports for them.',
    judge_review: '/proposal-deliberation Run the judge-reviewer now: hand the latest revision to the paper-reviewer '
      + 'agent in its proposal mode and record its contribution_type verbatim in .papersmith/model_spec.json.',
    'math-tutor': '/math-tutor Walk me through the equations of the latest proposal revision.',
  };
  const STEP_OF_BUTTON = { 'math-tutor': 'mathematics' };

  function stepEvidence(step) {
    const e = step.evidence || {};
    if (step.id === 'problem_pillars') {
      return t('modelSteps.evidence.problemPillars', {
        problem: t(e.problem ? 'modelSteps.evidence.yes' : 'modelSteps.evidence.no'), n: Number(e.pillars) || 0 });
    }
    if (step.id === 'hypotheses') return t('modelSteps.evidence.hypotheses', { n: Number(e.hypotheses) || 0 });
    if (step.id === 'sota_citations') {
      return t('modelSteps.evidence.sotaCitations', { cited: Number(e.cited) || 0, ideas: Number(e.ideas) || 0 });
    }
    if (step.id === 'judge_review') {
      return e.type && CONTRIBUTION_TYPE_KEYS[e.type]
        ? t('modelSteps.evidence.judgeReview', { type: t(CONTRIBUTION_TYPE_KEYS[e.type]) })
        : t('modelSteps.evidence.judgeOwed');
    }
    return t('modelSteps.evidence.mathematics', { n: Number(e.equations) || 0 });
  }

  function stepButton(step) {
    if (step.id === 'judge_review') return step.done ? 'modelSteps.judgeAgain' : 'modelSteps.judge';
    if (step.id === 'sota_citations') return step.done ? 'modelSteps.citeAgain' : 'modelSteps.cite';
    return 'modelSteps.generate';
  }

  function renderModelSteps(steps) {
    lastSteps = Array.isArray(steps) ? steps : [];
    const card = document.getElementById('modelContributionType');
    if (card && lastSpec) card.innerHTML = contributionType(lastSpec);
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
            <button type="button" class="btn btn--primary btn--sm" data-model-step="${esc(step.id)}"${off}>${esc(t(stepButton(step)))}</button>
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

  window.renderModelModules = (spec) => {
    renderModelModules(spec);
    refreshModelSteps();
    if (window.Citations) window.Citations.load();
  };
  if (window.Citations) window.Citations.onChange(() => { if (lastSpec) renderModelModules(lastSpec); });
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
