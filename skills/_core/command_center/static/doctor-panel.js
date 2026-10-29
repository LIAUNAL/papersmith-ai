/* Smith Doctor pane: the project's health table.
 *
 * GET /api/doctor answers the same {summary, rows} that `smith doctor --json`
 * prints: one row per framework version, package, tool, skill, agent and
 * phase, each with a state (ok, absent, warn, fail). The table groups rows by
 * area and shows a badge per state. "Check again" asks for a fresh
 * measurement (?fresh=1) instead of the cached one. Every value is escaped
 * before insertion.
 *
 * Public surface (window): refreshDoctorPanel(fresh), DoctorPanel.render(report).
 */
(function () {
  'use strict';

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const list = (v) => (Array.isArray(v) ? v : []);

  const AREAS = [
    ['framework', 'doctor.area.framework'],
    ['packages', 'doctor.area.packages'],
    ['tools', 'doctor.area.tools'],
    ['skills', 'doctor.area.skills'],
    ['agents', 'doctor.area.agents'],
    ['flows', 'doctor.area.flows'],
  ];
  const STATES = {
    ok: ['badge--ok', 'doctor.state.ok'],
    absent: ['badge--absent', 'doctor.state.absent'],
    warn: ['badge--warn', 'doctor.state.warn'],
    fail: ['badge--bad', 'doctor.state.fail'],
  };

  const stateLabel = (state) => (STATES[state] ? t(STATES[state][1]) : state);
  const badge = (state) => {
    const cls = STATES[state] ? STATES[state][0] : 'badge--info';
    return `<span class="badge ${esc(cls)}">${esc(stateLabel(state))}</span>`;
  };
  let lastReport = null;

  function render(report) {
    lastReport = report;
    const host = document.getElementById('doctorPanel');
    if (!host) return;
    const summary = (report && report.summary) || {};
    const rows = list(report && report.rows);
    const counts = summary.counts || {};
    const known = new Set(AREAS.map(([key]) => key));
    const areas = AREAS.map(([key, label]) => [key, t(label)]).concat([...new Set(rows.map((r) => r.area))]
      .filter((a) => !known.has(a)).map((a) => [a, a]));
    const body = areas.map(([key, label]) => {
      const group = rows.filter((r) => r.area === key);
      if (!group.length) return '';
      return `<tr class="doctor-group"><th colspan="3">${esc(label)} (${group.length})</th></tr>`
        + group.map((r) => `<tr><td><code>${esc(r.item)}</code></td><td>${badge(r.state)}</td>`
          + `<td class="doctor-detail">${esc(r.detail)}</td></tr>`).join('');
    }).join('');
    const tally = Object.keys(STATES)
      .map((s) => `${esc(stateLabel(s))}: ${esc(counts[s] ?? 0)}`).join(' · ');
    const when = summary.generated_at ? ` · ${esc(t('doctor.checkedAt', { at: summary.generated_at }))}` : '';
    const error = report && report.error ? `<ul class="agents-warnings"><li>${esc(report.error)}</li></ul>` : '';
    host.innerHTML = `<div class="doctor-summary">${esc(t('doctor.overall'))} ${badge(summary.state)}`
      + `<span class="panel__meta">${tally}${when}</span>`
      + `<button type="button" class="btn" id="doctorRecheck">${esc(t('doctor.recheck'))}</button></div>${error}`
      + `<div class="agents-table-wrap"><table class="agents-table"><thead><tr>`
      + `<th>${esc(t('doctor.col.item'))}</th><th>${esc(t('doctor.col.state'))}</th><th>${esc(t('doctor.col.detail'))}</th></tr></thead>`
      + `<tbody>${body || `<tr><td colspan="3" class="agents-empty">${esc(t('doctor.noRows'))}</td></tr>`}</tbody>`
      + `</table></div>`;
    const button = host.querySelectorAll('#doctorRecheck')[0];
    if (button) button.addEventListener('click', () => refreshDoctorPanel(true));
  }

  async function refreshDoctorPanel(fresh) {
    const host = document.getElementById('doctorPanel');
    const button = host && host.querySelectorAll('#doctorRecheck')[0];
    if (button) { button.disabled = true; button.textContent = t('doctor.checking'); }
    try {
      const response = await fetch(fresh ? '/api/doctor?fresh=1' : '/api/doctor', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    } catch (err) {
      render({ summary: { state: 'warn' }, rows: [],
        error: t('doctor.readFailed', { error: err.message || err }) });
    }
  }

  window.DoctorPanel = { render };
  window.refreshDoctorPanel = refreshDoctorPanel;
  // Details come from the server in the chosen language: fetch again once shown.
  document.addEventListener('languagechange', () => { if (lastReport) refreshDoctorPanel(); });
})();
