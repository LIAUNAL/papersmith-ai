/* Smith Doctor pane: the project's health table.
 *
 * GET /api/doctor answers the same {summary, rows} that `smith doctor --json`
 * prints: one row per framework version, package, tool, skill, agent and
 * phase, each with a state (ok, absent, warn, fail). The table groups rows by
 * area and shows a badge per state. "Volver a revisar" asks for a fresh
 * measurement (?fresh=1) instead of the cached one. Every value is escaped
 * before insertion.
 *
 * Public surface (window): refreshDoctorPanel(fresh), DoctorPanel.render(report).
 */
(function () {
  'use strict';

  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const list = (v) => (Array.isArray(v) ? v : []);

  const AREAS = [
    ['framework', 'Framework y versiones'],
    ['packages', 'Paquetes de Python'],
    ['tools', 'Herramientas del sistema'],
    ['skills', 'Skills'],
    ['agents', 'Agentes'],
    ['flows', 'Flujos (fases)'],
  ];
  const STATES = {
    ok: ['badge--ok', 'OK'],
    absent: ['badge--absent', 'Ausente'],
    warn: ['badge--warn', 'Revisar'],
    fail: ['badge--bad', 'Falla'],
  };

  const badge = (state) => {
    const [cls, label] = STATES[state] || ['badge--info', state];
    return `<span class="badge ${esc(cls)}">${esc(label)}</span>`;
  };

  function render(report) {
    const host = document.getElementById('doctorPanel');
    if (!host) return;
    const summary = (report && report.summary) || {};
    const rows = list(report && report.rows);
    const counts = summary.counts || {};
    const known = new Set(AREAS.map(([key]) => key));
    const areas = AREAS.concat([...new Set(rows.map((r) => r.area))]
      .filter((a) => !known.has(a)).map((a) => [a, a]));
    const body = areas.map(([key, label]) => {
      const group = rows.filter((r) => r.area === key);
      if (!group.length) return '';
      return `<tr class="doctor-group"><th colspan="3">${esc(label)} (${group.length})</th></tr>`
        + group.map((r) => `<tr><td><code>${esc(r.item)}</code></td><td>${badge(r.state)}</td>`
          + `<td class="doctor-detail">${esc(r.detail)}</td></tr>`).join('');
    }).join('');
    const tally = Object.keys(STATES)
      .map((s) => `${esc(STATES[s][1])}: ${esc(counts[s] ?? 0)}`).join(' · ');
    const when = summary.generated_at ? ` · revisado ${esc(summary.generated_at)}` : '';
    const error = report && report.error ? `<ul class="agents-warnings"><li>${esc(report.error)}</li></ul>` : '';
    host.innerHTML = `<div class="doctor-summary">Estado general ${badge(summary.state)}`
      + `<span class="panel__meta">${tally}${when}</span>`
      + `<button type="button" class="btn" id="doctorRecheck">Volver a revisar</button></div>${error}`
      + `<div class="agents-table-wrap"><table class="agents-table"><thead><tr>`
      + `<th>Elemento</th><th>Estado</th><th>Detalle</th></tr></thead>`
      + `<tbody>${body || '<tr><td colspan="3" class="agents-empty">Sin filas de diagnóstico.</td></tr>'}</tbody>`
      + `</table></div>`;
    const button = host.querySelectorAll('#doctorRecheck')[0];
    if (button) button.addEventListener('click', () => refreshDoctorPanel(true));
  }

  async function refreshDoctorPanel(fresh) {
    const host = document.getElementById('doctorPanel');
    const button = host && host.querySelectorAll('#doctorRecheck')[0];
    if (button) { button.disabled = true; button.textContent = 'Revisando…'; }
    try {
      const response = await fetch(fresh ? '/api/doctor?fresh=1' : '/api/doctor', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    } catch (err) {
      render({ summary: { state: 'warn' }, rows: [],
        error: `No se pudo leer /api/doctor: ${err.message || err}` });
    }
  }

  window.DoctorPanel = { render };
  window.refreshDoctorPanel = refreshDoctorPanel;
})();
