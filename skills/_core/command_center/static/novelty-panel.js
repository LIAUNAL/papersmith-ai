/**
 * novelty-panel.js: Novelty & Findings Assessment Panel and Decision Gate.
 *
 * Renders the 4 core subsections:
 *   1. Hypothesis vs Empirical Evidence matrix (tests, metrics, verdicts).
 *   2. Novelty Assessment & Scientific Sobriety vs SOTA.
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

  async function sendGateDecision(action) {
    const notesEl = document.getElementById('noveltyGateNotes');
    const notes = notesEl ? notesEl.value.trim() : '';
    const statusEl = document.getElementById('noveltyGateActionStatus');
    if (statusEl) {
      statusEl.textContent = 'Recording decision…';
      statusEl.style.color = 'var(--text-muted)';
    }

    try {
      const res = await fetch('/api/novelty/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, notes, actor: 'operator' }),
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

  function renderNoveltyPanel(data) {
    const root = document.getElementById('noveltyRoot');
    if (!root) return;

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

    // ----------------------------------------------------
    // SUBSECTION 4: DECISION GATE CARD (Highlighted at top)
    // ----------------------------------------------------
    html += `
      <section class="panel" style="border: 2px solid ${status === 'approved' ? 'var(--ok)' : 'var(--accent)'}; margin-bottom: 1.5rem; background: var(--surface);">
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

          <div style="display:flex; flex-wrap:wrap; gap:0.6rem; align-items:center;">
            <button type="button" class="btn btn--primary" onclick="window.sendNoveltyDecision('approve')" style="background:var(--ok); border-color:var(--ok); color:#fff; font-weight:700;">
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
      <section class="panel" style="margin-bottom: 1.5rem;">
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

    // ----------------------------------------------------
    // SUBSECTION 2: NOVELTY & SCIENTIFIC SOBRIETY VS SOTA
    // ----------------------------------------------------
    const sota = data.sota || {};
    const noveltyClaims = data.novelty_claims || [];
    html += `
      <section class="panel" style="margin-bottom: 1.5rem;">
        <div class="panel__header">
          <div class="panel__title">
            2. ${t('novelty.sota.title', 'Novelty Assessment & Scientific Sobriety vs. SOTA')}
          </div>
          <span class="panel__meta">${sota.candidates_count || 0} ${t('novelty.sota.candidates_meta', 'candidates in SOTA pool')}</span>
        </div>
        <div style="padding: 0.75rem 0;">
          <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap:1rem; margin-bottom:1rem;">
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

            <div style="background:var(--surface); border:1px solid var(--border); padding:1rem; border-radius:6px;">
              <div style="font-weight:700; color:var(--accent); margin-bottom:0.5rem;">⚖️ ${t('novelty.sota.sobriety', 'Scientific Sobriety & Dispelling Hype')}</div>
              <ul style="font-size:0.85rem; line-height:1.5; padding-left:1.2rem; color:var(--text);">
                <li>${t('novelty.sota.sobriety_entanglement', 'Entanglement vs. Separability: If quantum topology does not statistically outperform separable layers (p = 1.0), report with rigorous sobriety, affirming that quantum value lies in analytical interpretability and harmonic expressivity, not brute supremacy.')}</li>
                <li>${t('novelty.sota.sobriety_leakage', 'Data Leakage in Prior Literature: Contrast with inflated claims (>99% accuracy) stemming from random trial-level splitting rather than subject-level GroupKFold.')}</li>
                <li>${t('novelty.sota.sobriety_plateaus', 'Barren Plateau Boundary: Transparent circuit depth limits (L <= 3) justified by exponential gradient variance collapse (< 10^-5).')}</li>
              </ul>
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
      <section class="panel" style="margin-bottom: 1.5rem;">
        <div class="panel__header">
          <div class="panel__title">
            3. ${t('novelty.rigor.title', 'Scientific Rigor & Reviewer Defense Audit')}
          </div>
          <span class="panel__meta">${t('novelty.rigor.meta', 'Adversarial defense')}</span>
        </div>
        <div style="padding: 0.75rem 0;">
          <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:0.75rem;">
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
  }

  // Export to window
  window.refreshNoveltyPanel = fetchNoveltyOverview;
  window.sendNoveltyDecision = sendGateDecision;
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