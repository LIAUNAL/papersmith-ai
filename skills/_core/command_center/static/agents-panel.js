/* Agents table of the Archify Flow pane.
 *
 * GET /api/agents answers agents_view.get_agents_view(root): every agent of
 * the workspace's .claude/agents/ with its role, bound skill, stretch, tools,
 * the dashboard phase(s) it acts in and the harness projections that carry it.
 * The table sorts by any column and filters by free text. Every value is
 * escaped before insertion.
 *
 * Public surface (window): refreshAgentsPanel(), AgentsPanel.render(view).
 */
(function () {
  'use strict';

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const list = (v) => (Array.isArray(v) ? v : []);
  const phaseNumber = (a) => {
    const m = /(?:Phase|Fase) (\d+)/.exec(list(a.phases)[0] || '');
    return m ? Number(m[1]) : 99;
  };

  const COLUMNS = [
    { key: 'name', label: () => t('agents.col.name'), value: (a) => a.name },
    { key: 'role', label: () => t('agents.col.role'), value: (a) => a.role },
    { key: 'skill', label: () => 'Skill', value: (a) => a.skill },
    { key: 'stretch', label: () => t('agents.col.stretch'), value: (a) => a.stretch },
    { key: 'tools', label: () => t('agents.col.tools'), value: (a) => list(a.tools).join(', ') },
    { key: 'phases', label: () => t('agents.col.phases'), value: (a) => list(a.phases).join(' · '), sort: phaseNumber },
    { key: 'harnesses', label: () => 'Harness', value: (a) => list(a.harnesses).join(' ') },
  ];

  let lastView = { agents: [], warnings: [] };
  let sortKey = 'phases';
  let sortDir = 1;
  let filter = '';

  function rows(view) {
    const needle = filter.trim().toLowerCase();
    const col = COLUMNS.find((c) => c.key === sortKey) || COLUMNS[0];
    const keyOf = col.sort || ((a) => String(col.value(a) ?? '').toLowerCase());
    return list(view.agents)
      .filter((a) => !needle || COLUMNS.some((c) => String(c.value(a) ?? '').toLowerCase().includes(needle))
        || String(a.description ?? '').toLowerCase().includes(needle))
      .sort((x, y) => {
        const kx = keyOf(x), ky = keyOf(y);
        if (kx < ky) return -sortDir;
        if (kx > ky) return sortDir;
        return String(x.name).localeCompare(String(y.name));
      });
  }

  function cell(agent, col) {
    if (col.key === 'role') {
      return `<td class="agents-role" title="${esc(agent.description)}">${esc(agent.role)}`
        + (agent.description && agent.description !== agent.role
          ? `<details><summary>${esc(t('agents.fullDescription'))}</summary><p>${esc(agent.description)}</p></details>` : '')
        + '</td>';
    }
    if (col.key === 'name') return `<td><code>${esc(agent.name)}</code></td>`;
    if (col.key === 'skill') return `<td>${agent.skill ? `<code>${esc(agent.skill)}</code>` : '—'}</td>`;
    if (col.key === 'phases') {
      return `<td>${list(agent.phases).map((p) => `<span class="agents-phase">${esc(p)}</span>`).join(' ') || '—'}</td>`;
    }
    const text = col.value(agent);
    return `<td>${text ? esc(text) : '—'}</td>`;
  }

  function render(view) {
    lastView = view && typeof view === 'object' ? view : { agents: [], warnings: [] };
    const host = document.getElementById('agentsPanel');
    if (!host) return;
    const shown = rows(lastView);
    const head = COLUMNS.map((c) => {
      const mark = c.key === sortKey ? (sortDir > 0 ? ' ▲' : ' ▼') : '';
      return `<th data-sort="${esc(c.key)}" role="button" tabindex="0">${esc(c.label())}${mark}</th>`;
    }).join('');
    const body = shown.length
      ? shown.map((a) => `<tr>${COLUMNS.map((c) => cell(a, c)).join('')}</tr>`).join('')
      : `<tr><td colspan="${COLUMNS.length}" class="agents-empty">${esc(t('agents.noMatch'))}</td></tr>`;
    const warnings = list(lastView.warnings).length
      ? `<ul class="agents-warnings">${list(lastView.warnings).map((w) => `<li>${esc(w)}</li>`).join('')}</ul>` : '';
    host.innerHTML = `<div class="agents-toolbar">`
      + `<input type="search" id="agentsFilter" placeholder="${esc(t('agents.filter'))}" value="${esc(filter)}">`
      + `<span class="panel__meta">${esc(t('agents.count', { n: shown.length, total: list(lastView.agents).length }))}</span></div>`
      + `<div class="agents-table-wrap"><table class="agents-table"><thead><tr>${head}</tr></thead>`
      + `<tbody>${body}</tbody></table></div>${warnings}`;
    bind(host);
  }

  function bind(host) {
    host.querySelectorAll('th[data-sort]').forEach((th) => {
      const toggle = () => {
        const key = th.getAttribute('data-sort');
        sortDir = key === sortKey ? -sortDir : 1;
        sortKey = key;
        render(lastView);
      };
      th.addEventListener('click', toggle);
      th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
    });
    const input = host.querySelectorAll('#agentsFilter')[0];
    if (input) {
      input.addEventListener('input', () => {
        filter = input.value;
        const pos = input.selectionStart;
        render(lastView);
        const again = document.getElementById('agentsFilter');
        if (again && again.focus) { again.focus(); try { again.setSelectionRange(pos, pos); } catch (_) { /* ignore */ } }
      });
    }
  }

  async function refreshAgentsPanel() {
    try {
      const response = await fetch('/api/agents', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    } catch (err) {
      render({ agents: [], warnings: [t('agents.readFailed', { error: err.message || err })] });
    }
  }

  window.AgentsPanel = { render };
  window.refreshAgentsPanel = refreshAgentsPanel;
  document.addEventListener('DOMContentLoaded', () => { refreshAgentsPanel(); });
  // Phase labels come from the server in the chosen language: fetch again.
  document.addEventListener('languagechange', () => { refreshAgentsPanel(); });
})();
