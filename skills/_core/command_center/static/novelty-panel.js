/**
 * novelty-panel.js: Novelty & Findings Assessment Panel and Decision Gate.
 *
 * Renders the 4 core subsections:
 *   1. Hypothesis vs Empirical Evidence matrix (tests, metrics, verdicts), followed by
 *      the paper-reviewer's contribution type for the findings, with the
 *      button that launches that judge (a stage's approval waits for it).
 *   2. Novelty Assessment & Scientific Sobriety vs SOTA (claims, limits, unsupported findings).
 *   3. Scientific Rigor & Reviewer Defense Audit checklist.
 *   4. Novelty Decision Gate with interactive action buttons (Approve, Iterate).
 */
(function () {
  'use strict';

  const esc = (text) => {
    if (text === null || text === undefined) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  const t = (key, fallback) => {
    if (window.i18n && typeof window.i18n.t === 'function') {
      const val = window.i18n.t(key);
      if (val && val !== key) return val;
    }
    return fallback || key;
  };

  const VERDICT_BADGES = {
    supported: '<span class="badge badge--ok">SUPPORTED</span>',
    partially_supported: '<span class="badge badge--warn">PARTIALLY SUPPORTED</span>',
    not_supported: '<span class="badge badge--bad">NOT SUPPORTED</span>',
    inconclusive: '<span class="badge badge--info">INCONCLUSIVE</span>',
    pending: '<span class="badge">PENDING</span>',
  };

  const GATE_STATUS_BADGES = {
    pending: '<span class="badge badge--warn">⏳ PENDING DECISION</span>',
    approved: '<span class="badge badge--ok">✅ NOVELTY APPROVED</span>',
    iterating_experiments: '<span class="badge badge--info">🔄 ITERATING EXPERIMENTS</span>',
    iterating_proposal: '<span class="badge badge--info">🔄 ITERATING PROPOSAL</span>',
    iterating_plausibility: '<span class="badge badge--info">🔄 ITERATING PLAUSIBILITY</span>',
  };

  const STATEMENT_CLIP = 160;
  const clip = (text, max) => {
    const value = String(text === null || text === undefined ? '' : text);
    return value.length > max ? `${value.slice(0, max)}…` : value;
  };

  const verdictLabel = (family, verdict) => t(`${family}.${verdict}`, String(verdict));

  // What the product discussions record against the claims: their limitations,
  // the hypotheses that were not supported or left inconclusive, and a novelty
  // verdict that is not (fully) justified. Nothing here is written by the forge.
  function sobrietyListItems(data) {
    const item = (kind, who, body) => `<li><strong>${esc(kind)}</strong>${who ? ` <span class="badge badge--sm">${esc(who)}</span>` : ''} ${body}</li>`;
    const detail = (rationale) => (rationale
      ? ` <span style="color:var(--text-muted);"><em>${esc(t('novelty.hypotheses.rationale_label', 'Rationale:'))}</em> ${esc(rationale)}</span>` : '');
    const items = [];
    (data.limitations || []).forEach((l) => {
      items.push(item(t('novelty.sota.sobriety_limitation', 'Limitation'), l.product, esc(l.text)));
    });
    (data.hypotheses || []).forEach((h) => {
      if (h.verdict !== 'not_supported' && h.verdict !== 'inconclusive') return;
      items.push(item(
        `${t('novelty.sota.sobriety_hypothesis', 'Hypothesis')} ${h.id}`, h.product,
        `${esc(clip(h.statement, STATEMENT_CLIP))} <span class="badge badge--sm">${esc(verdictLabel('exp.disc.verdict', h.verdict))}</span>${detail(h.rationale)}`,
      ));
    });
    (data.discussions || []).forEach((d) => {
      if (d.verdict !== 'not_justified' && d.verdict !== 'partially_justified') return;
      items.push(item(
        t('exp.disc.noveltyTitle', 'Novelty'), d.product,
        `<span class="badge badge--sm">${esc(verdictLabel('exp.disc.novelty', d.verdict))}</span>${detail(d.rationale)}`,
      ));
    });
    return items;
  }

  let currentOverview = null;

  async function fetchNoveltyOverview() {
    try {
      const res = await fetch('/api/novelty/status');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      currentOverview = await res.json();
      renderNoveltyPanel(currentOverview);
    } catch (err) {
      const root = document.getElementById('noveltyRoot');
      if (root) {
        root.innerHTML = `<div class="alert alert--bad">Error loading novelty overview: ${esc(err.message)}</div>`;
      }
    }
  }

  // What the judge's buttons type into the agent terminal (agent input stays
  // English). A stage's approval stays locked while one of its products owes it.
  const JUDGE_SKILLS = {
    poc: ['/proposal-implementation', 'proof-of-concept'],
    full: ['/experimental-implementation', 'full-experiment'],
  };
  const JUDGE_RECORD = 'to the paper-reviewer agent in its findings mode, write its contribution_type '
    + 'into Results/discussion.json and re-run discussion_cli.py check.';
  function judgeCommand(stage) {
    const [skill, name] = JUDGE_SKILLS[stage];
    return judgeOwed(stage).length
      ? `${skill} Run the judge-reviewer now: hand each ${name} discussion that is complete apart from a missing or invalid contribution_type ${JUDGE_RECORD} Leave drafts untouched.`
      : `${skill} Run the judge-reviewer again: hand every complete ${name} discussion ${JUDGE_RECORD}`;
  }
  const JUDGE_LABELS = {
    poc: { launch: 'novelty.judge.launchPoc', again: 'novelty.judge.againPoc' },
    full: { launch: 'novelty.judge.launchFull', again: 'novelty.judge.againFull' },
  };
  let judgeState = {};
  let experimentCitationsOwed = [];

  function judgeOwed(stage) {
    const owed = (judgeState[stage] || {}).owed;
    return Array.isArray(owed) ? owed : [];
  }

  function launchNoveltyJudge(stage) {
    if (!JUDGE_SKILLS[stage] || !(Number((judgeState[stage] || {}).complete) > 0)) return;
    if (typeof window.sendToCli === 'function') window.sendToCli(judgeCommand(stage), false, { kind: 'slash' });
  }

  // One button per stage with a complete discussion, on the card its verdict
  // lands on; without any, one disabled button saying what it waits for.
  function judgeActions() {
    const stages = ['poc', 'full'].filter((stage) => Number((judgeState[stage] || {}).complete) > 0);
    if (!stages.length) {
      return `<p class="model-step__reason">🔒 ${esc(t('novelty.judge.needsDiscussion'))}</p>
        <button type="button" class="btn btn--sm" data-novelty-judge="none" disabled aria-disabled="true">${esc(t('novelty.judge.launchPoc'))}</button>`;
    }
    return stages.map((stage) => {
      const owed = judgeOwed(stage);
      const note = owed.length
        ? `<p style="font-size:0.85rem; color:var(--warn); margin:0.5rem 0 0.35rem;">${esc(t('novelty.judge.owed').replace('{products}', owed.join(', ')))}</p>` : '';
      return `${note}<button type="button" class="btn ${owed.length ? 'btn--primary ' : ''}btn--sm" data-novelty-judge="${stage}" onclick="window.launchNoveltyJudge('${stage}')">${esc(t(owed.length ? JUDGE_LABELS[stage].launch : JUDGE_LABELS[stage].again))}</button>`;
    }).join(' ');
  }

  function approvalLock(stage) {
    const keys = [];
    if (judgeOwed(stage).length) keys.push('novelty.judge.approvalLocked');
    if (stage === 'poc' && experimentCitationsOwed.length) keys.push('novelty.citations.approvalLocked');
    return keys.length
      ? { attr: ' disabled aria-disabled="true"',
          note: keys.map((key) => `<p class="model-step__reason">🔒 ${esc(t(key))}</p>`).join('') }
      : { attr: '', note: '' };
  }

  // `stage` "poc" records the proof-of-concept verification (G-EXP-POC) from
  // its own card; without it, the full-stage novelty gate.
  async function sendGateDecision(action, stage) {
    const poc = stage === 'poc';
    const notesEl = document.getElementById(poc ? 'noveltyPocNotes' : 'noveltyGateNotes');
    const notes = notesEl ? notesEl.value.trim() : '';
    const statusEl = document.getElementById(poc ? 'noveltyPocActionStatus' : 'noveltyGateActionStatus');
    if (statusEl) {
      statusEl.textContent = 'Recording decision…';
      statusEl.style.color = 'var(--text-muted)';
    }

    try {
      const res = await fetch('/api/novelty/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, notes, actor: 'operator', stage: poc ? 'poc' : 'full' }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.message || data.error || 'Failed to record decision');
      }
      if (statusEl) {
        statusEl.textContent = 'Decision successfully recorded!';
        statusEl.style.color = 'var(--ok)';
      }
      // Refresh panel and workspace status
      await fetchNoveltyOverview();
      if (typeof window.refreshDashboardState === 'function') {
        window.refreshDashboardState();
      }
    } catch (err) {
      if (statusEl) {
        statusEl.textContent = `Error: ${err.message}`;
        statusEl.style.color = 'var(--bad)';
      }
    }
  }

  // The five contribution types and their catalogue keys.
  const CONTRIBUTION_TYPE_KEYS = {
    'General': 'contribution.type.General',
    'Theory': 'contribution.type.Theory',
    'Use-Inspired': 'contribution.type.Use-Inspired',
    'Concept & Feasibility': 'contribution.type.Concept & Feasibility',
    'Negative Results': 'contribution.type.Negative Results',
  };

  // Literal catalogue keys per PoC decision state (never a composed key).
  const POC_STATE_KEYS = {
    approved: 'novelty.poc.state.approved',
    iterating: 'novelty.poc.state.iterating',
    pending: 'novelty.poc.state.pending',
  };

  // Before the full experiments: the operator verifies a proof of concept
  // whose discussion is complete (its results and the hypotheses it
  // contrasted, listed below) and approves it or asks for another iteration.
  function pocVerificationCard(data) {
    const verification = data.poc_verification || {};
    if (!(Number(verification.discussed) > 0)) return '';
    const decision = verification.decision || {};
    const state = POC_STATE_KEYS[decision.status] ? decision.status : 'pending';
    const tone = state === 'approved' ? 'ok' : (state === 'iterating' ? 'info' : 'warn');
    const pocHypotheses = (data.hypotheses || []).filter((h) => h && h.stage === 'poc');
    return `
      <section data-fold="novelty:poc" data-fold-title="novelty.poc.title" data-fold-open id="noveltyPocVerify" class="panel" style="border: 2px solid var(--${state === 'approved' ? 'ok' : 'accent'}); margin-bottom: 1.5rem; background: var(--surface);">
        <div class="panel__header">
          <div class="panel__title" style="font-size:1.05rem; font-weight:700; color:var(--text);">🧪 ${esc(t('novelty.poc.title', 'Verify the proof of concept'))}</div>
          <span class="badge badge--${tone}">${esc(t(POC_STATE_KEYS[state]))}</span>
        </div>
        <div style="padding: 1rem 0;">
          <p style="font-size:0.9rem; line-height:1.5; margin-bottom:0.75rem;">${esc(t('novelty.poc.desc'))}</p>
          <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:0.75rem;">${esc(t('novelty.poc.count'))} ${esc(String(verification.discussed))} · ${esc(t('novelty.poc.hypotheses'))} ${esc(String(pocHypotheses.length))}</p>
          ${decision.rationale ? `<p style="font-size:0.85rem; margin-bottom:0.75rem;"><strong>${esc(t('novelty.gate.current_rationale', 'Current rationale:'))}</strong> ${esc(decision.rationale)}</p>` : ''}
          <textarea id="noveltyPocNotes" rows="2" class="form-control" style="width:100%; font-size:0.85rem; padding:0.5rem; background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:4px; margin-bottom:0.6rem;" placeholder="${esc(t('novelty.poc.notes_placeholder'))}"></textarea>
          ${approvalLock('poc').note}
          <div style="display:flex; flex-wrap:wrap; gap:0.6rem; align-items:center;">
            <button type="button" class="btn btn--primary"${approvalLock('poc').attr} onclick="window.sendNoveltyDecision('approve', 'poc')">✓ ${esc(t('novelty.poc.approve'))}</button>
            <button type="button" class="btn" onclick="window.sendNoveltyDecision('iterate', 'poc')">🔄 ${esc(t('novelty.poc.iterate'))}</button>
            <span id="noveltyPocActionStatus" style="font-size:0.85rem; font-weight:600; margin-left:auto;"></span>
          </div>
        </div>
      </section>`;
  }

  function renderNoveltyPanel(data) {
    const root = document.getElementById('noveltyRoot');
    if (!root) return;

    judgeState = data.judge || {};
    experimentCitationsOwed = Array.isArray(data.experiment_citations_owed) ? data.experiment_citations_owed : [];
    const gate = data.gate || {};
    const status = gate.status || 'pending';
    const statusBadge = GATE_STATUS_BADGES[status] || `<span class="badge">${esc(status)}</span>`;

    let html = `
      <div class="panel" style="margin-bottom: 1.5rem;">
        <div class="panel__header" style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <div class="panel__title" style="font-size:1.25rem; font-weight:700;">
              ✨ ${t('novelty.title', 'Novelty & Findings Assessment')}
            </div>
            <div style="font-size:0.85rem; color:var(--text-muted); margin-top:0.25rem;">
              ${t('novelty.subtitle', 'Empirical hypothesis contrast, SOTA grounding, and formal gate decision before manuscript drafting.')}
            </div>
          </div>
          <div style="display:flex; gap:0.75rem; align-items:center;">
            ${statusBadge}
            <button type="button" class="btn btn--sm" onclick="window.refreshNoveltyPanel()">${t('common.refresh', 'Refresh')}</button>
          </div>
        </div>
      </div>
    `;

    html += pocVerificationCard(data);

    // ----------------------------------------------------
    // SUBSECTION 4: DECISION GATE CARD (Highlighted at top)
    // ----------------------------------------------------
    html += `
      <section data-fold="novelty:gate" data-fold-title="novelty.gate.title" data-fold-open class="panel" style="border: 2px solid ${status === 'approved' ? 'var(--ok)' : 'var(--accent)'}; margin-bottom: 1.5rem; background: var(--surface);">
        <div class="panel__header">
          <div class="panel__title" style="font-size:1.05rem; font-weight:700; color:var(--text);">
            🚪 ${t('novelty.gate.title', 'Novelty Decision Gate')}
          </div>
          <span style="font-size:0.85rem; font-family:var(--font-mono); color:var(--text-muted);">
            ${gate.decided_at ? `${t('novelty.gate.last_decision', 'Last decision:')} ${esc(gate.decided_at)} (${esc(gate.actor || 'operator')})` : t('novelty.gate.no_decision', 'No decision recorded yet')}
          </span>
        </div>
        <div style="padding: 1rem 0;">
          <p style="font-size:0.9rem; line-height:1.5; margin-bottom:1rem;">
            ${t('novelty.gate.desc', 'Before proceeding with manuscript scaffolding (Phase 6), assess whether the experiments firmly support the proposed novelty or if an iteration is required in experiments, theoretical proposal, or plausibility.')}
          </p>

          ${gate.rationale ? `
            <div style="background:var(--bg); border-left:4px solid var(--accent); padding:0.75rem 1rem; border-radius:4px; margin-bottom:1rem; font-size:0.9rem;">
              <strong>${t('novelty.gate.current_rationale', 'Current rationale:')}</strong> ${esc(gate.rationale)}
            </div>
          ` : ''}

          <div style="margin-bottom:1rem;">
            <label for="noveltyGateNotes" style="display:block; font-size:0.85rem; font-weight:600; margin-bottom:0.4rem;">
              ${t('novelty.gate.notes_label', 'Decision notes / rationale:')}
            </label>
            <textarea id="noveltyGateNotes" rows="2" class="form-control" style="width:100%; font-family:var(--font-sans); font-size:0.85rem; padding:0.5rem; background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:4px;" placeholder="${t('novelty.gate.notes_placeholder', 'Describe empirical justification, reasons for approval, or iteration guidelines…')}"></textarea>
          </div>

          ${approvalLock('full').note}
          <div style="display:flex; flex-wrap:wrap; gap:0.6rem; align-items:center;">
            <button type="button" class="btn btn--primary"${approvalLock('full').attr} onclick="window.sendNoveltyDecision('approve')" style="background:var(--ok); border-color:var(--ok); color:#fff; font-weight:700;">
              ✓ ${t('novelty.actions.approve', 'Approve Novelty & Proceed to Writing')}
            </button>
            <button type="button" class="btn" onclick="window.sendNoveltyDecision('iterate_experiments')">
              🔄 ${t('novelty.actions.iterate_exp', 'Iterate in Experiments')}
            </button>
            <button type="button" class="btn" onclick="window.sendNoveltyDecision('iterate_proposal')">
              🔄 ${t('novelty.actions.iterate_prop', 'Iterate in Proposal / Model')}
            </button>
            <button type="button" class="btn" onclick="window.sendNoveltyDecision('iterate_plausibility')">
              🔄 ${t('novelty.actions.iterate_plaus', 'Iterate in Plausibility / SOTA')}
            </button>
            <button type="button" class="btn btn--sm" style="opacity:0.7;" onclick="window.sendNoveltyDecision('reset')">
              ↩ ${t('novelty.actions.reset', 'Reset to Pending')}
            </button>
            <span id="noveltyGateActionStatus" style="font-size:0.85rem; font-weight:600; margin-left:auto;"></span>
          </div>
        </div>
      </section>
    `;

    // ----------------------------------------------------
    // SUBSECTION 1: HYPOTHESES VS EVIDENCE MATRIX
    // ----------------------------------------------------
    const hypotheses = data.hypotheses || [];
    html += `
      <section data-fold="novelty:hypotheses" data-fold-title="novelty.hypotheses.title" class="panel" style="margin-bottom: 1.5rem;">
        <div class="panel__header">
          <div class="panel__title">
            1. ${t('novelty.hypotheses.title', 'Hypotheses vs. Empirical Evidence')}
          </div>
          <span class="panel__meta">${hypotheses.length} ${t('novelty.hypotheses.count', 'hypotheses evaluated')}</span>
        </div>
        <div class="table-responsive" style="margin-top:0.75rem;">
          <table class="table" style="font-size:0.85rem;">
            <thead>
              <tr>
                <th style="width:70px;">${t('novelty.hypotheses.th_id', 'ID')}</th>
                <th style="width:70px;">${t('novelty.hypotheses.th_stage', 'Stage')}</th>
                <th>${t('novelty.hypotheses.th_statement', 'Hypothesis Statement')}</th>
                <th>${t('novelty.hypotheses.th_metric', 'Metric / Criterion')}</th>
                <th>${t('novelty.hypotheses.th_observed', 'Observed Result & Statistical Test')}</th>
                <th style="width:140px;">${t('novelty.hypotheses.th_verdict', 'Verdict')}</th>
              </tr>
            </thead>
            <tbody>
    `;

    if (hypotheses.length === 0) {
      html += `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:1.5rem;">${t('novelty.hypotheses.empty', 'No hypotheses recorded in Results/discussion.json yet.')}</td></tr>`;
    } else {
      hypotheses.forEach((h) => {
        const vBadge = VERDICT_BADGES[h.verdict] || `<span class="badge">${esc(h.verdict)}</span>`;
        html += `
          <tr>
            <td><strong>${esc(h.id)}</strong></td>
            <td><span class="badge badge--sm">${esc(h.stage || 'full')}</span></td>
            <td>
              <div>${esc(h.statement)}</div>
              ${h.rationale ? `<div style="font-size:0.78rem; color:var(--text-muted); margin-top:0.25rem;"><em>${t('novelty.hypotheses.rationale_label', 'Rationale:')}</em> ${esc(h.rationale)}</div>` : ''}
            </td>
            <td>
              <div><strong>${esc(h.metric)}</strong></div>
              <div style="font-size:0.78rem; color:var(--text-muted);">${esc(h.criterion)}</div>
            </td>
            <td>
              <div style="font-family:var(--font-mono); font-size:0.8rem;">${esc(h.observed)}</div>
              ${h.test ? `<div style="font-size:0.78rem; color:var(--accent); margin-top:0.2rem;"><code>${esc(h.test)}</code></div>` : ''}
            </td>
            <td>${vBadge}</td>
          </tr>
        `;
      });
    }

    html += `
            </tbody>
          </table>
        </div>
      </section>
    `;

    // contribution type the paper-reviewer read from the checked findings
    const ct = data.contribution_type;
    html += `
      <section data-fold="novelty:contribution" data-fold-title="contribution.title" data-fold-open id="noveltyContributionType" class="panel" style="margin-bottom: 1.5rem;">
        <div class="panel__header">
          <div class="panel__title">${esc(t('contribution.title', 'contribution type'))}</div>
          ${ct && ct.product ? `<span class="panel__meta">${esc(ct.product)} · ${esc(ct.stage)}</span>` : ''}
        </div>
        ${ct && CONTRIBUTION_TYPE_KEYS[ct.type] ? `
          <div style="margin-top:0.75rem; font-size:0.9rem; line-height:1.5;">
            <span class="badge">${esc(t(CONTRIBUTION_TYPE_KEYS[ct.type], ct.type))}</span>
            <p style="margin-top:0.5rem;"><strong>${esc(t('contribution.why', 'Why:'))}</strong> ${esc(ct.why)}</p>
            ${window.ContributionAffinity ? window.ContributionAffinity.html(ct) : ''}
          </div>` : `
          <p style="margin-top:0.75rem; font-size:0.85rem; color:var(--text-muted);">${esc(t('contribution.owed', 'paper-reviewer').replace('{artifact}', 'Results/discussion.json'))}</p>`}
        <div style="margin-top:0.6rem;">${judgeActions()}</div>
      </section>
    `;

    // ----------------------------------------------------
    // SUBSECTION 2: NOVELTY & SCIENTIFIC SOBRIETY VS SOTA
    // ----------------------------------------------------
    const sota = data.sota || {};
    const noveltyClaims = data.novelty_claims || [];
    const sobrietyItems = sobrietyListItems(data);
    html += `
      <section data-fold="novelty:sota" data-fold-title="novelty.sota.title" class="panel" style="margin-bottom: 1.5rem;">
        <div class="panel__header">
          <div class="panel__title">
            2. ${t('novelty.sota.title', 'Novelty Assessment & Scientific Sobriety vs. SOTA')}
          </div>
          <span class="panel__meta">${sota.candidates_count || 0} ${t('novelty.sota.candidates_meta', 'candidates in SOTA pool')}</span>
        </div>
        <div style="padding: 0.75rem 0;">
          <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr)); gap:1rem; margin-bottom:1rem;">
            <div style="background:var(--surface); border:1px solid var(--border); padding:1rem; border-radius:6px;">
              <div style="font-weight:700; color:var(--accent); margin-bottom:0.5rem;">🌟 ${t('novelty.sota.core_claim', 'Core Novelty Claims')}</div>
              ${noveltyClaims.length > 0 ? noveltyClaims.map(nc => `
                <div style="margin-bottom:0.75rem;">
                  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.25rem;">
                    <strong>${esc(nc.product)}</strong>
                    <span class="badge ${nc.verdict === 'justified' ? 'badge--ok' : 'badge--warn'}">${esc(nc.verdict)}</span>
                  </div>
                  <div style="font-size:0.85rem; line-height:1.4;">${esc(nc.claim)}</div>
                  ${nc.rationale ? `<div style="font-size:0.78rem; color:var(--text-muted); margin-top:0.3rem;">${esc(nc.rationale)}</div>` : ''}
                </div>
              `).join('') : `<p style="font-size:0.85rem; color:var(--text-muted);">${t('novelty.sota.empty_claims', 'No formalized claims in discussion.json.')}</p>`}
            </div>

            <div id="noveltySobriety" style="background:var(--surface); border:1px solid var(--border); padding:1rem; border-radius:6px;">
              <div style="font-weight:700; color:var(--accent); margin-bottom:0.5rem;">⚖️ ${t('novelty.sota.sobriety', 'Sobriety: limits and unsupported claims')}</div>
              ${sobrietyItems.length > 0
                ? `<ul style="font-size:0.85rem; line-height:1.5; padding-left:1.2rem; color:var(--text);">${sobrietyItems.join('')}</ul>`
                : `<p style="font-size:0.85rem; color:var(--text-muted);">${t('novelty.sota.sobriety_empty', 'No limitations or unsupported hypotheses recorded in Results/discussion.json.')}</p>`}
            </div>
          </div>
        </div>
      </section>
    `;

    // ----------------------------------------------------
    // SUBSECTION 3: SCIENTIFIC RIGOR & REVIEWER DEFENSE
    // ----------------------------------------------------
    const rigor = data.rigor_audit || [];
    html += `
      <section data-fold="novelty:rigor" data-fold-title="novelty.rigor.title" class="panel" style="margin-bottom: 1.5rem;">
        <div class="panel__header">
          <div class="panel__title">
            3. ${t('novelty.rigor.title', 'Scientific Rigor & Reviewer Defense Audit')}
          </div>
          <span class="panel__meta">${t('novelty.rigor.meta', 'Adversarial defense')}</span>
        </div>
        <div style="padding: 0.75rem 0;">
          <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr)); gap:0.75rem;">
            ${rigor.map(r => `
              <div style="background:var(--surface); border:1px solid ${r.passed ? 'var(--ok)' : 'var(--warn)'}; padding:0.85rem; border-radius:6px;">
                <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.4rem;">
                  <span style="font-size:1.1rem; color:${r.passed ? 'var(--ok)' : 'var(--warn)'};">${r.passed ? '✓' : '⚠️'}</span>
                  <strong style="font-size:0.85rem;">${esc(r.title)}</strong>
                </div>
                <div style="font-size:0.8rem; color:var(--text-muted); line-height:1.4;">${esc(r.detail)}</div>
              </div>
            `).join('')}
          </div>
        </div>
      </section>
    `;

    // History of decisions if available
    if (gate.history && gate.history.length > 0) {
      html += `
        <details class="panel" style="margin-bottom:1rem;">
          <summary style="cursor:pointer; font-size:0.85rem; font-weight:600; padding:0.5rem 0; color:var(--text-muted);">
            📜 ${t('novelty.history.title', 'View previous decision history')} (${gate.history.length})
          </summary>
          <div style="margin-top:0.75rem;">
            ${gate.history.map((h, idx) => `
              <div style="font-size:0.8rem; padding:0.4rem 0; border-bottom:1px solid var(--border);">
                <strong>#${idx + 1} [${esc(h.status)}]</strong> by ${esc(h.actor || 'operator')} at ${esc(h.decided_at || '')}:
                <em>${esc(h.rationale || t('novelty.history.no_notes', 'No notes'))}</em>
              </div>
            `).join('')}
          </div>
        </details>
      `;
    }

    root.innerHTML = html;
    if (window.SectionFolds) window.SectionFolds.wrap(root);
  }

  // Export to window
  window.refreshNoveltyPanel = fetchNoveltyOverview;
  window.sendNoveltyDecision = sendGateDecision;
  window.launchNoveltyJudge = launchNoveltyJudge;
  window.NoveltyPanel = {
    fetch: fetchNoveltyOverview,
    sendDecision: sendGateDecision,
    render: renderNoveltyPanel,
  };

  // Auto-init when tab is opened
  window.addEventListener('DOMContentLoaded', () => {
    if (window.location.hash === '#novelty') {
      fetchNoveltyOverview();
    }
  });

  // Hook into navigateTab
  const origNav = window.navigateTab;
  if (typeof origNav === 'function') {
    window.navigateTab = function (tabId) {
      origNav(tabId);
      if (tabId === 'novelty') {
        fetchNoveltyOverview();
      }
    };
  }
})();