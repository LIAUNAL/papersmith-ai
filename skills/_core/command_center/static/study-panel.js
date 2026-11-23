/* Study pane: the operator's records of an empirical study (the empirical paper lines).
 *
 * GET /api/study answers one object with a section per panel: protocol (the
 * G-STUDY-PROTOCOL lock, the latest managed revision, the amendments), ethics
 * and registration (the latest record, bound to the current lock or stale, the
 * retrospective flag, the reason when not applicable), data (the operator's own
 * datasets: data-use statement, dictionary summary, QC and its domain checks,
 * the de-identification and whether it is current; never a data value),
 * analysis (the analysis log: label, outcome, plan, exit code, interrupted runs,
 * repairs, warnings), flow (the participant flow: valid, the figure, the
 * sign-off, the validated counts) and reporting (the agreed variant and its
 * guideline). A section the server could not read carries
 * {available: false, code, message} and is drawn as unavailable; the others
 * still render. The variant's checklist is slow (the engine runs paper_cli.py)
 * and loads only when the operator clicks its button, from
 * GET /api/study/checklist. Every value is escaped before insertion.
 *
 * Public surface (window): refreshStudyPanel(), StudyPanel.{html, render, act}.
 */
(function () {
  'use strict';

  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const list = (v) => (Array.isArray(v) ? v : []);
  const obj = (v) => (v && typeof v === 'object' && !Array.isArray(v) ? v : {});
  const DASH = '—';
  const fmt = (v) => {
    if (v === null || v === undefined || v === '') return DASH;
    if (Array.isArray(v)) return v.length ? v.map(fmt).join(', ') : DASH;
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  };

  // Literal catalogue keys (never composed) for the machine values the server sends.
  const PROTOCOL_KEYS = {
    absent: 'study.protocol.absent', current: 'study.protocol.current',
    changed: 'study.protocol.changed', corrupt: 'study.protocol.corrupt',
  };
  const CHANGE_KEYS = {
    'revision-missing': 'study.protocol.reason.missing', 'revision-edited': 'study.protocol.reason.edited',
    'newer-revision': 'study.protocol.reason.newer',
  };
  const WARNING_KEYS = {
    ETHICS_STALE: 'study.warning.ethicsStale', REGISTRATION_STALE: 'study.warning.registrationStale',
    REGISTRATION_RETROSPECTIVE: 'study.warning.retrospective', FIRST_ENROLMENT_UNKNOWN: 'study.warning.firstEnrolment',
  };
  const QC_KEYS = { pass: 'study.data.qc.pass', warn: 'study.data.qc.warn', fail: 'study.data.qc.fail' };
  const LABEL_KEYS = { confirmatory: 'study.analysis.confirmatory', exploratory: 'study.analysis.exploratory' };
  const LOG_KEYS = { torn: 'study.analysis.torn', corrupt: 'study.analysis.corrupt' };
  const FIGURE_KEYS = {
    current: 'study.flow.figureCurrent', stale: 'study.flow.figureStale', absent: 'study.flow.figureAbsent',
  };
  const REASON_KEYS = {
    'type-not-agreed': 'study.reporting.typeNotAgreed', 'variant-not-agreed': 'study.reporting.variantNotAgreed',
    'type-not-this-line': 'study.reporting.typeNotThisLine',
    'variant-without-checklist': 'study.reporting.variantWithoutChecklist',
  };
  const STATUS_KEYS = {
    satisfied: 'study.checklist.satisfied', missing: 'study.checklist.missing',
    'needs-judgment': 'study.checklist.needsJudgment',
  };

  let lastView = null;
  let checklist = null;   // null (not asked), {loading: true}, or the /api/study/checklist answer
  let notice = '';        // the last action's outcome, already translated

  function unavailable(part) {
    return `<p class="rv-error" role="alert">${esc(t('study.unavailable', { code: part.code || '', message: part.message || '' }))}</p>`;
  }

  function section(id, titleKey, part, body) {
    const content = part && part.available === false ? unavailable(part) : body(part || {});
    return `<section class="rv-section" data-study-section="${esc(id)}"><h3>${esc(t(titleKey))}</h3>${content}</section>`;
  }

  function table(headers, rows) {
    return `<div class="rv-table-wrap"><table class="rv-table"><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead>`
      + `<tbody>${rows.map((cells) => `<tr>${cells.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }

  function warningsHtml(warnings) {
    const items = list(warnings).map((w) => {
      const key = WARNING_KEYS[w.code];
      return `<li>${esc(key ? t(key) : t('study.warning.generic', { code: w.code || '', message: w.message || '' }))}</li>`;
    });
    return items.length ? `<ul class="rv-warn">${items.join('')}</ul>` : '';
  }

  function protocolBody(p) {
    const reasons = list(p.reasons).map((r) => (CHANGE_KEYS[r] ? t(CHANGE_KEYS[r]) : r)).join(', ');
    const state = `<p class="${p.state === 'current' ? 'rv-ok' : (p.state === 'corrupt' ? 'rv-error' : 'rv-warn')}">${esc(t(PROTOCOL_KEYS[p.state] || PROTOCOL_KEYS.absent, {
      gate: p.gate || 'G-STUDY-PROTOCOL', revision: p.revision || '', by: p.approved_by || DASH, at: p.approved_at || DASH,
      reasons, message: p.message || '',
    }))}</p>`;
    const latest = p.latest_problem
      ? `<p class="rv-warn">${esc(t('study.protocol.latestProblem', { code: obj(p.latest_problem).code || '', message: obj(p.latest_problem).message || '' }))}</p>`
      : `<p class="rv-muted">${esc(p.latest_revision ? t('study.protocol.latest', { revision: p.latest_revision, n: p.revisions ?? 0 }) : t('study.protocol.noRevision'))}</p>`;
    const amendments = list(p.amendments).length
      ? `<h4>${esc(t('study.protocol.amendments'))}</h4><ul>${list(p.amendments).map((a) => `<li>${esc(t('study.protocol.amendment', {
        at: a.at || DASH, by: a.by || DASH, reason: a.reason || DASH, revision: a.revision || DASH,
      }))}</li>`).join('')}</ul>`
      : (p.state === 'current' || p.state === 'changed' ? `<p class="rv-muted">${esc(t('study.protocol.noAmendments'))}</p>` : '');
    return `${state}${latest}${amendments}`;
  }

  function recordedLine(g) {
    const bound = g.current
      ? `<p class="rv-ok">${esc(t('study.gate.current'))}</p>`
      : `<p class="rv-warn">${esc(t('study.gate.stale', { revision: g.protocol_revision || DASH }))}</p>`;
    return `<p class="rv-muted">${esc(t('study.gate.recorded', { by: g.by || DASH, at: g.at || DASH, n: g.records ?? 1 }))}</p>${bound}${warningsHtml(g.warnings)}`;
  }

  function ethicsBody(g) {
    if (!g.recorded) return `<p class="rv-warn">${esc(t('study.ethics.absent', { path: g.path || 'study/ethics.json' }))}</p>`;
    const main = g.status === 'not-applicable'
      ? t('study.gate.notApplicable', { reason: g.reason || DASH })
      : t('study.ethics.approved', { committee: g.committee || DASH, code: g.code || DASH, date: g.date || DASH, consent: g.consent || DASH });
    return `<p>${esc(main)}</p>${recordedLine(g)}`;
  }

  function registrationBody(g) {
    if (!g.recorded) return `<p class="rv-warn">${esc(t('study.registration.absent', { path: g.path || 'study/registration.json' }))}</p>`;
    if (g.status === 'not-applicable') return `<p>${esc(t('study.gate.notApplicable', { reason: g.reason || DASH }))}</p>${recordedLine(g)}`;
    const timing = g.retrospective === true
      ? `<p class="rv-warn">${esc(t('study.registration.retrospective'))}</p>`
      : (g.retrospective === false ? `<p class="rv-ok">${esc(t('study.registration.prospective'))}</p>` : '');
    return `<p>${esc(t('study.registration.registered', {
      registry: g.registry || DASH, id: g.id || DASH, date: g.date || DASH, first: g.first_enrolment || DASH,
    }))}</p>${timing}${recordedLine(g)}`;
  }

  function dictionaryHtml(d) {
    d = obj(d);
    if (d.state === 'absent') return `<p class="rv-warn">${esc(t('study.data.dictionaryAbsent'))}</p>`;
    if (d.state === 'unreadable') return `<p class="rv-error">${esc(t('study.data.dictionaryUnreadable', { code: d.code || '', message: d.message || '' }))}</p>`;
    const columns = list(d.columns);
    const described = columns.filter((c) => c.described).length;
    const rows = columns.map((c) => [esc(c.name), esc(c.type), esc(c.unit || DASH),
      c.pii ? `<span class="rv-warn">${esc(t('study.data.pii'))}</span>` : esc(DASH),
      esc(c.described ? t('study.data.yes') : t('study.data.no'))]);
    return `<p>${esc(t('study.data.dictionary', { path: d.path || '', n: columns.length, described, pii: fmt(d.pii) }))}</p>`
      + (rows.length ? table([t('study.data.column'), t('study.data.type'), t('study.data.unit'), t('study.data.piiCol'), t('study.data.described')], rows) : '');
  }

  function qcHtml(q) {
    q = obj(q);
    if (!q.status) return `<p class="rv-warn">${esc(t('study.data.qcAbsent'))}</p>`;
    const head = `<p class="${q.status === 'pass' ? 'rv-ok' : (q.status === 'fail' ? 'rv-error' : 'rv-warn')}">${esc(t(QC_KEYS[q.status] || 'study.data.qc.other', {
      status: q.status, file: q.file || DASH, at: q.checked || DASH,
    }))}</p>`;
    const report = q.report_state && q.report_state !== 'ok'
      ? `<p class="rv-warn">${esc(t('study.data.qcReport', { path: q.report || DASH, message: q.message || q.report_state }))}</p>` : '';
    const stale = q.dictionary_current === false ? `<p class="rv-warn">${esc(t('study.data.qcDictionaryChanged'))}</p>` : '';
    const reasons = list(q.reasons).length ? `<ul>${list(q.reasons).map((r) => `<li>${esc(r)}</li>`).join('')}</ul>` : '';
    const checks = list(q.domain_checks).length
      ? table([t('study.data.check'), t('study.data.column'), t('study.data.severity'), t('study.data.count')],
        list(q.domain_checks).map((c) => [esc(c.check), esc(c.column), esc(c.severity), esc(fmt(c.count))]))
      : '';
    return `${head}${report}${stale}${reasons}${checks}`;
  }

  function deidentificationHtml(d) {
    d = obj(d);
    if (d.recorded && d.current) {
      return `<p class="rv-ok">${esc(t('study.data.deidentified', { by: d.by || DASH, at: d.recorded_on || DASH, statement: d.statement || DASH, columns: fmt(d.columns) }))}</p>`;
    }
    if (d.recorded) {
      return `<p class="rv-warn">${esc(t('study.data.deidentificationStale', { by: d.by || DASH, at: d.recorded_on || DASH, problem: d.problem || DASH }))}</p>`;
    }
    if (d.required) return `<p class="rv-warn">${esc(t('study.data.deidentificationOwed', { problem: d.problem || DASH }))}</p>`;
    return `<p class="rv-muted">${esc(t('study.data.noPii'))}</p>`;
  }

  function dataBody(d) {
    const own = list(d.own);
    const other = d.other ? `<p class="rv-muted">${esc(t('study.data.other', { n: d.other }))}</p>` : '';
    if (!own.length) return `<p class="rv-muted">${esc(t('study.data.empty'))}</p>${other}`;
    return own.map((e) => {
      const use = obj(e.data_use);
      return `<h4>${esc(e.slug)}${e.title && e.title !== e.slug ? ` · ${esc(e.title)}` : ''}</h4>
        <p>${esc(t('study.data.use', { by: use.by || DASH, at: use.recorded || DASH, statement: use.statement || DASH }))}</p>
        ${dictionaryHtml(e.dictionary)}${qcHtml(e.qc)}${deidentificationHtml(e.deidentification)}`;
    }).join('') + other;
  }

  function analysisBody(a) {
    const log = obj(a.log);
    if (log.state === 'absent') return `<p class="rv-muted">${esc(t('study.analysis.empty'))}</p>${warningsHtml(a.warnings)}`;
    const broken = LOG_KEYS[log.state]
      ? `<p class="rv-error" role="alert">${esc(t(LOG_KEYS[log.state], { message: log.message || '' }))}</p>` : '';
    const labels = obj(a.labels);
    const counts = `<p>${esc(t('study.analysis.counts', {
      confirmatory: labels.confirmatory ?? 0, exploratory: labels.exploratory ?? 0,
      failed: list(a.failed_runs).length, interrupted: list(a.interrupted_runs).length, repairs: a.repairs ?? 0,
    }))}</p>`;
    const interrupted = list(a.interrupted_runs).length
      ? `<p class="rv-warn">${esc(t('study.analysis.interrupted', { runs: list(a.interrupted_runs).join(', ') }))}</p>` : '';
    const rows = list(a.entries).map((e) => [
      esc(e.id), esc(fmt(e.at)), esc(e.outcome), esc(fmt(e.plan)),
      `<span class="${e.label === 'confirmatory' ? 'rv-ok' : 'rv-warn'}">${esc(LABEL_KEYS[e.label] ? t(LABEL_KEYS[e.label]) : fmt(e.label))}</span>`
        + `<span class="rv-quote">${esc(obj(e.label_reason).message || '')}</span>`,
      `<span class="${e.exit_code === null || e.exit_code === undefined || e.exit_code === 0 ? '' : 'rv-error'}">${esc(fmt(e.exit_code))}</span>`,
      esc(e.attested ? t('study.analysis.attested', { by: e.by || DASH, tool: e.tool || DASH }) : fmt(e.script)),
      esc(fmt(e.note)),
    ]);
    const tableHtml = rows.length
      ? table([t('study.analysis.id'), t('study.analysis.at'), t('study.analysis.outcome'), t('study.analysis.plan'),
        t('study.analysis.label'), t('study.analysis.exitCode'), t('study.analysis.source'), t('study.analysis.note')], rows)
      : `<p class="rv-muted">${esc(t('study.analysis.noEntries'))}</p>`;
    return `${broken}${counts}${interrupted}${tableHtml}${warningsHtml(a.warnings)}`;
  }

  function countsCell(row) {
    const groups = list(row.groups).filter((g) => list(g.items).length).map((g) => `${g.label}: ${list(g.items).map((i) => `${i.label} (${fmt(i.n)})`).join('; ')}`);
    return `${esc(fmt(row.n))}${groups.length ? `<span class="rv-quote">${esc(groups.join(' · '))}</span>` : ''}`;
  }

  function flowBody(f) {
    if (f.state === 'absent') return `<p class="rv-muted">${esc(t('study.flow.absent', { path: f.path || 'study/flow.json' }))}</p>`;
    const head = f.state === 'valid'
      ? `<p class="rv-ok">${esc(t('study.flow.valid', { template: f.template || DASH }))}</p>`
      : `<p class="rv-error">${esc(t('study.flow.invalid', { template: f.template || DASH, n: list(f.problems).length }))}</p>`
        + `<ul>${list(f.problems).map((p) => `<li>${esc(`${p.code || ''}${p.path ? ` (${p.path})` : ''}: ${p.message || ''}`)}</li>`).join('')}</ul>`;
    const figure = obj(f.figure);
    const figureLine = `<p class="${figure.state === 'current' ? 'rv-ok' : 'rv-warn'}">${esc(t(FIGURE_KEYS[figure.state] || FIGURE_KEYS.absent, { path: figure.path || '' }))}</p>`;
    const signoff = f.signoff
      ? (f.signoff.current
        ? `<p class="rv-ok">${esc(t('study.flow.signed', { by: f.signoff.by || DASH, at: f.signoff.at || DASH }))}</p>`
        : `<p class="rv-warn">${esc(t('study.flow.signoffStale', { by: f.signoff.by || DASH, at: f.signoff.at || DASH }))}</p>`)
      : `<p class="rv-warn">${esc(t('study.flow.unsigned'))}</p>`;
    const rows = [];
    list(f.stages).forEach((s) => {
      if (s.split) list(s.branches).forEach((b) => rows.push([esc(s.band), esc(String(s.label || '').replace('{branch}', b.label)), countsCell(b)]));
      else rows.push([esc(s.band), esc(s.label), countsCell(s)]);
    });
    const counts = rows.length ? table([t('study.flow.band'), t('study.flow.stage'), t('study.flow.count')], rows) : '';
    const image = figure.exists
      ? `<div class="rv-flow"><img alt="${esc(t('study.flow.figureAlt'))}" src="/api/artifact?path=${encodeURIComponent(figure.path)}&amp;v=${esc(figure.mtime || 0)}">
          <p><a href="/api/artifact?path=${encodeURIComponent(figure.path)}" target="_blank" rel="noopener">${esc(t('study.flow.openFigure', { path: figure.path }))}</a></p></div>`
      : '';
    return `${head}${figureLine}${signoff}${counts}${image}`;
  }

  function reportingLine(r) {
    r = obj(r);
    if (r.guideline) {
      return `<p>${esc(t('study.reporting.agreed', { variant: r.variant_name || r.variant || DASH, type: r.type || DASH, guideline: r.guideline }))}</p>`;
    }
    const reason = REASON_KEYS[r.reason] ? ` ${t(REASON_KEYS[r.reason])}` : '';
    return `<p class="rv-warn">${esc(t('study.reporting.noData') + reason)}</p>`;
  }

  function checklistHtml(reporting) {
    const button = `<button type="button" class="btn btn--sm" data-study-action="checklist"${checklist && checklist.loading ? ' disabled' : ''}>${esc(t(checklist && !checklist.loading ? 'study.checklist.rerun' : 'study.checklist.run'))}</button>`;
    let body = `<p class="rv-muted">${esc(t('study.checklist.onDemand'))}</p>`;
    if (checklist && checklist.loading) body = `<p class="rv-muted" role="status">${esc(t('study.checklist.loading'))}</p>`;
    else if (checklist && checklist.available === false) body = unavailable(checklist);
    else if (checklist && !checklist.guideline) body = reportingLine(checklist);
    else if (checklist) {
      const items = list(checklist.items);
      const summary = obj(checklist.summary);
      const guideline = obj(checklist.guideline);
      const paper = checklist.paper_available === false ? `<p class="rv-warn">${esc(t('study.checklist.noPaper'))}</p>` : '';
      const notes = list(checklist.notes).map((n) => `<p class="rv-warn">${esc(n)}</p>`).join('');
      body = `<p>${esc(t('study.checklist.guideline', { name: guideline.name || guideline.id || DASH, version: guideline.version || DASH }))}</p>`
        + `<p>${esc(t('study.checklist.counts', {
          satisfied: list(summary.satisfied).length, missing: list(summary.missing).length,
          judgment: list(summary['needs-judgment']).length, total: items.length,
        }))}</p>${paper}${notes}`
        + table([t('study.checklist.item'), t('study.checklist.section'), t('study.checklist.topic'), t('study.checklist.status'), t('study.checklist.owed')],
          items.map((i) => [esc(i.item), esc(i.section), esc(i.topic),
            `<span class="${i.status === 'satisfied' ? 'rv-ok' : (i.status === 'missing' ? 'rv-error' : 'rv-warn')}">${esc(STATUS_KEYS[i.status] ? t(STATUS_KEYS[i.status]) : i.status)}</span>`
              + (i.question ? `<span class="rv-quote">${esc(i.question)}</span>` : ''),
            list(i.missing).length ? `<ul>${list(i.missing).map((m) => `<li>${esc(m)}</li>`).join('')}</ul>` : esc(DASH)]));
    }
    const head = reporting && reporting.available !== false ? reportingLine(reporting) : (reporting ? unavailable(reporting) : '');
    return `<section class="rv-section" data-study-section="checklist"><h3>${esc(t('study.checklist.title'))}</h3>
      ${head}<div class="rv-actions">${button}</div>${body}</section>`;
  }

  function html(view) {
    view = obj(view);
    if (view.error) return `<p class="rv-error" role="alert">${esc(view.error)}</p>`;
    const warnings = list(view.warnings).map((w) => `<p class="rv-warn" role="alert">${esc(t('study.moduleWarning', { warning: w }))}</p>`).join('');
    const note = notice ? `<p class="rv-muted" role="status">${esc(notice)}</p>` : '';
    return `<div class="rv-actions"><button type="button" class="btn btn--sm" data-study-action="refresh">${esc(t('study.refresh'))}</button></div>
      ${warnings}${note}
      ${section('protocol', 'study.protocol.title', view.protocol, protocolBody)}
      ${section('ethics', 'study.ethics.title', view.ethics, ethicsBody)}
      ${section('registration', 'study.registration.title', view.registration, registrationBody)}
      ${section('data', 'study.data.title', view.data, dataBody)}
      ${section('analysis', 'study.analysis.title', view.analysis, analysisBody)}
      ${section('flow', 'study.flow.title', view.flow, flowBody)}
      ${checklistHtml(view.reporting)}`;
  }

  function render(view) {
    lastView = view;
    const host = document.getElementById('studyPanel');
    if (host) host.innerHTML = html(view);
  }

  async function getJson(url) {
    const response = await fetch(url, { cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = data && data.code === 'NOT_A_STUDY_WORKSPACE'
        ? t('study.notStudy', { kind: data.paper_kind || '' })
        : t('study.readFailed', { error: (data && (data.error || data.detail)) || `HTTP ${response.status}` });
      throw new Error(error);
    }
    return data;
  }

  async function refreshStudyPanel() {
    try {
      render(await getJson('/api/study'));
    } catch (err) {
      render({ error: err.message || String(err) });
    }
  }

  async function act(action) {
    if (action === 'refresh') {
      notice = '';
      await refreshStudyPanel();
      return;
    }
    if (action === 'checklist') {
      if (checklist && checklist.loading) return;
      checklist = { loading: true };
      render(lastView);
      try {
        checklist = await getJson('/api/study/checklist');
      } catch (err) {
        checklist = { available: false, code: 'HTTP', message: err.message || String(err) };
      }
      render(lastView);
    }
  }

  document.addEventListener('click', (event) => {
    const el = event.target && event.target.closest && event.target.closest('[data-study-action]');
    if (!el || !el.dataset || !el.dataset.studyAction) return;
    act(el.dataset.studyAction);
  });
  document.addEventListener('languagechange', () => { if (lastView) render(lastView); });

  window.StudyPanel = { html, render, act };
  window.refreshStudyPanel = refreshStudyPanel;
})();
