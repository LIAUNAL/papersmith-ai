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
 * guideline, plus the line's other guidelines: gum-reporting for hardware).
 * A hardware or lab-simulation workspace (or any holding measurement records)
 * also answers instruments, measurements (registered raw data files, never a
 * reading), uncertainty (GUM budgets with their components) and agreement
 * (Bland-Altman and ICC(2,1)); the numbers are the core's summary statistics.
 * A data-resource workspace (or any with a deposit record) also answers deposit:
 * each dataset's repository, identifier and scheme, licence, landing page,
 * version, date and who recorded it, current or stale with the reasons.
 * A section the server could not read carries
 * {available: false, code, message} and is drawn as unavailable; the others
 * still render. The variant's checklist is slow (the engine runs paper_cli.py)
 * and loads only when the operator clicks its button, from
 * GET /api/study/checklist (another of the line's guidelines from
 * ?guideline=<id>). Every value is escaped before insertion.
 *
 * Public surface (window): refreshStudyPanel(), StudyPanel.{html, render, act(action, guideline)}.
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
    'type-without-checklist': 'study.reporting.typeWithoutChecklist',
  };
  const ADDITIONAL_KEYS = { 'gum-reporting': 'study.reporting.gumReporting' };
  const RECORD_KEYS = { absent: 'study.measure.absent' };
  const CALIBRATION_KEYS = {
    current: 'study.instruments.current', 'past-due': 'study.instruments.pastDue', unknown: 'study.instruments.unknown',
  };
  const FILE_KEYS = {
    current: 'study.measurements.current', changed: 'study.measurements.changed', missing: 'study.measurements.missing',
  };
  const COMPUTED_KEYS = { current: 'study.measure.current', stale: 'study.measure.stale' };
  const STALE_KEYS = {
    'input-missing': 'study.measure.reason.inputMissing', 'input-changed': 'study.measure.reason.inputChanged',
    'registration-changed': 'study.measure.reason.reregistered', 'inputs-added': 'study.measure.reason.inputsAdded',
    'instrument-changed': 'study.measure.reason.instrumentChanged',
    'device-missing': 'study.measure.reason.deviceMissing', 'device-changed': 'study.measure.reason.deviceChanged',
    'device-reregistered': 'study.measure.reason.deviceReregistered',
    'reference-missing': 'study.measure.reason.referenceMissing',
    'reference-changed': 'study.measure.reason.referenceChanged',
    'reference-reregistered': 'study.measure.reason.referenceReregistered',
  };
  const COVERAGE_KEYS = {
    'student-t': 'study.uncertainty.coverage.t', normal: 'study.uncertainty.coverage.normal',
    declared: 'study.uncertainty.coverage.declared',
  };
  const COMPONENT_KEYS = {
    repeatability: 'study.uncertainty.component.repeatability', calibration: 'study.uncertainty.component.calibration',
    resolution: 'study.uncertainty.component.resolution',
  };
  const MEASUREMENT_SECTIONS = ['instruments', 'measurements', 'uncertainty', 'agreement'];
  const DEPOSIT_REASON_KEYS = {
    'file-changed': 'study.deposit.reason.changed', 'file-added': 'study.deposit.reason.added',
    'file-missing': 'study.deposit.reason.missing',
  };
  const STATUS_KEYS = {
    satisfied: 'study.checklist.satisfied', missing: 'study.checklist.missing',
    'needs-judgment': 'study.checklist.needsJudgment',
  };

  let lastView = null;
  // Per guideline ('' is the agreed variant's): null (not asked), {loading: true}, or the /api/study/checklist answer.
  const checklists = {};
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

  // Four significant digits: the summary statistics, never a reading.
  const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? String(Number(v.toPrecision(4))) : fmt(v));
  const magnitude = (m) => (m && typeof m === 'object' ? `${num(m.value)} ${m.unit || ''}`.trim() : DASH);
  const conditionsText = (c) => {
    const keys = Object.keys(obj(c)).sort();
    return keys.length ? keys.map((k) => `${k}=${c[k]}`).join(', ') : t('study.measure.noConditions');
  };
  const reasonsText = (reasons) => list(reasons).map((r) => (STALE_KEYS[r] ? t(STALE_KEYS[r]) : r)).join(', ');
  const stateClass = (ok) => (ok ? 'rv-ok' : 'rv-warn');

  function computedState(item) {
    return `<span class="${stateClass(item.state === 'current')}">${esc(t(COMPUTED_KEYS[item.state] || COMPUTED_KEYS.stale, { reasons: reasonsText(item.reasons) || DASH }))}</span>`;
  }

  function absentRecord(part, fallback) {
    return `<p class="rv-muted">${esc(t(RECORD_KEYS.absent, { path: part.path || fallback }))}</p>`;
  }

  function instrumentsBody(p) {
    if (p.state === 'absent') return absentRecord(p, 'study/instruments.json');
    const rows = list(p.instruments).map((i) => {
      const stated = i.stated_uncertainty
        ? t('study.instruments.stated', { value: magnitude(i.stated_uncertainty), distribution: i.stated_uncertainty.distribution || DASH, k: fmt(i.stated_uncertainty.coverage_k) })
        : DASH;
      return [esc(i.id), esc(fmt(i.model)), esc(fmt(i.serial)), esc(magnitude(i.resolution)), esc(stated),
        esc(fmt(i.calibration_certificate)), esc(fmt(i.calibrated)), esc(fmt(i.due)),
        `<span class="${i.calibration === 'current' ? 'rv-ok' : 'rv-warn'}">${esc(t(CALIBRATION_KEYS[i.calibration] || CALIBRATION_KEYS.unknown))}</span>`];
    });
    const pastDue = list(p.past_due).length
      ? `<p class="rv-warn">${esc(t('study.instruments.pastDueList', { ids: list(p.past_due).join(', ') }))}</p>` : '';
    return `<p class="rv-muted">${esc(t('study.instruments.on', { on: p.on || DASH }))}</p>${pastDue}`
      + table([t('study.instruments.id'), t('study.instruments.model'), t('study.instruments.serial'),
        t('study.instruments.resolution'), t('study.instruments.statedCol'), t('study.instruments.certificate'),
        t('study.instruments.calibrated'), t('study.instruments.due'), t('study.instruments.calibration')], rows);
  }

  function measurementsBody(p) {
    if (p.state === 'absent') return absentRecord(p, 'study/measurements.json');
    const rows = list(p.files).map((f) => [esc(f.path), esc(fmt(f.quantity)), esc(fmt(f.unit)), esc(fmt(f.instrument)),
      esc(fmt(f.rows)), esc(conditionsText(f.conditions)),
      `<span class="${stateClass(f.state === 'current')}">${esc(t(FILE_KEYS[f.state] || FILE_KEYS.changed))}</span>`]);
    return `<p class="rv-muted">${esc(t('study.measurements.note'))}</p>`
      + table([t('study.measurements.path'), t('study.measurements.quantity'), t('study.measurements.unit'),
        t('study.measurements.instrument'), t('study.measurements.rows'), t('study.measurements.conditions'),
        t('study.measurements.state')], rows);
  }

  function calibrationHtml(c) {
    if (!c) return '';
    const head = `<p class="${c.state === 'current' ? 'rv-muted' : 'rv-warn'}">${esc(t('study.uncertainty.calibration', {
      state: t(CALIBRATION_KEYS[c.state] || CALIBRATION_KEYS.unknown), due: c.due || DASH, on: c.checked_on || DASH,
    }))}</p>`;
    const override = c.override
      ? `<p class="rv-warn">${esc(t('study.uncertainty.override', { by: c.override.by || DASH, at: c.override.at || DASH, reason: c.override.reason || DASH }))}</p>` : '';
    return head + override;
  }

  function budgetHtml(b) {
    const title = `<h4>${esc(t('study.uncertainty.budget', { quantity: b.quantity || DASH, conditions: conditionsText(b.conditions) }))}</h4>`;
    if (b.state === 'corrupt') {
      return `${title}<p class="rv-error">${esc(t('study.uncertainty.corrupt', { path: b.path || DASH, message: b.message || '' }))}</p>`;
    }
    const coverage = obj(b.coverage);
    const result = `<p>${esc(t('study.uncertainty.result', {
      n: fmt(b.n), mean: num(b.mean), uc: num(b.combined_standard_uncertainty), unit: b.unit || '',
      dof: num(b.effective_dof), k: num(coverage.k), U: num(b.expanded_uncertainty),
      coverage: COVERAGE_KEYS[coverage.method] ? t(COVERAGE_KEYS[coverage.method], { level: num(coverage.level), dof: fmt(coverage.dof_used) }) : fmt(coverage.method),
    }))}</p>`;
    const rows = list(b.components).map((c) => [esc(COMPONENT_KEYS[c.name] ? t(COMPONENT_KEYS[c.name]) : fmt(c.name)),
      esc(fmt(c.type)), esc(fmt(c.source)), esc(num(c.u)), esc(fmt(c.unit)), esc(num(c.dof)), esc(num(c.sensitivity)),
      esc(num(c.contribution))]);
    const components = rows.length
      ? table([t('study.uncertainty.component'), t('study.uncertainty.type'), t('study.uncertainty.source'),
        t('study.uncertainty.u'), t('study.uncertainty.unit'), t('study.uncertainty.dof'),
        t('study.uncertainty.sensitivity'), t('study.uncertainty.contribution')], rows) : '';
    return `${title}<p>${computedState(b)}</p>${result}${calibrationHtml(b.calibration)}${components}`
      + `<p class="rv-muted">${esc(t('study.uncertainty.computed', { at: b.computed_at || DASH, method: b.method || DASH }))}</p>`;
  }

  function uncertaintyBody(p) {
    if (p.state === 'absent') return absentRecord(p, 'study/uncertainty/');
    return list(p.budgets).map(budgetHtml).join('');
  }

  function agreementBody(p) {
    if (p.state === 'absent') return absentRecord(p, 'study/agreement.json');
    const rows = list(p.analyses).map((a) => {
      const ba = obj(a.bland_altman);
      const device = obj(a.device);
      const reference = obj(a.reference);
      return [esc(`${device.path || DASH} (${device.instrument || DASH})`), esc(`${reference.path || DASH} (${reference.instrument || DASH})`),
        esc(`${a.quantity || DASH} [${a.unit || DASH}]`), esc(fmt(a.n)), esc(num(ba.bias)),
        esc(t('study.agreement.limits', { lower: num(ba.loa_lower), upper: num(ba.loa_upper) })),
        esc(num(obj(a.icc).value)), computedState(a)];
    });
    return table([t('study.agreement.device'), t('study.agreement.reference'), t('study.agreement.quantity'),
      t('study.agreement.n'), t('study.agreement.bias'), t('study.agreement.loa'), t('study.agreement.icc'),
      t('study.agreement.state')], rows);
  }

  function depositHtml(d) {
    const title = `<h4>${esc(d.slug)}${d.title && d.title !== d.slug ? ` · ${esc(d.title)}` : ''}</h4>`;
    if (!d.recorded) return `${title}<p class="rv-warn">${esc(t('study.deposit.absent'))}</p>`;
    const stale = list(d.stale);
    let state;
    if (d.current) state = `<p class="rv-ok">${esc(t('study.deposit.current'))}</p>`;
    else if (stale.length) {
      const reasons = stale.map((r) => (DEPOSIT_REASON_KEYS[r.reason]
        ? t(DEPOSIT_REASON_KEYS[r.reason], { file: r.file || DASH }) : `${r.reason || ''} ${r.file || ''}`.trim())).join(', ');
      state = `<p class="rv-warn">${esc(t('study.deposit.stale', { reasons }))}</p>`;
    } else state = `<p class="rv-warn">${esc(t('study.deposit.malformed'))}</p>`;
    const url = /^https?:\/\//i.test(d.url || '')
      ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.url)}</a>` : esc(fmt(d.url));
    const identifier = d.identifier ? t('study.deposit.scheme', { identifier: d.identifier, scheme: d.scheme || DASH }) : DASH;
    const row = [esc(fmt(d.repository)), esc(identifier), esc(fmt(d.license)), url, esc(fmt(d.version)),
      esc(fmt(d.date)), esc(fmt(list(d.files)))];
    return `${title}${state}`
      + table([t('study.deposit.repository'), t('study.deposit.identifier'), t('study.deposit.license'),
        t('study.deposit.url'), t('study.deposit.version'), t('study.deposit.date'), t('study.deposit.files')], [row])
      + `<p class="rv-muted">${esc(t('study.deposit.recorded', { by: d.by || DASH, at: d.recorded_on || DASH, n: d.revisions ?? 0 }))}</p>`;
  }

  function depositBody(p) {
    const datasets = list(p.datasets);
    const note = `<p class="rv-muted">${esc(t('study.deposit.note'))}</p>`;
    if (!datasets.length) return `${note}<p class="rv-muted">${esc(t('study.deposit.empty'))}</p>`;
    return note + datasets.map(depositHtml).join('');
  }

  function reportingLine(r) {
    r = obj(r);
    const additional = list(r.additional_guidelines).map((g) => `<p>${esc(ADDITIONAL_KEYS[g] ? t(ADDITIONAL_KEYS[g]) : t('study.reporting.additional', { guideline: g }))}</p>`).join('');
    if (r.guideline) {
      const agreed = r.variant
        ? t('study.reporting.agreed', { variant: r.variant_name || r.variant, type: r.type || DASH, guideline: r.guideline })
        : t('study.reporting.agreedType', { type: r.type || DASH, guideline: r.guideline });
      return `<p>${esc(agreed)}</p>${additional}`;
    }
    const reason = REASON_KEYS[r.reason] ? ` ${t(REASON_KEYS[r.reason])}` : '';
    return `<p class="rv-warn">${esc(t('study.reporting.noData') + reason)}</p>${additional}`;
  }

  function checklistBody(checklist) {
    if (!checklist) return `<p class="rv-muted">${esc(t('study.checklist.onDemand'))}</p>`;
    if (checklist.loading) return `<p class="rv-muted" role="status">${esc(t('study.checklist.loading'))}</p>`;
    if (checklist.available === false) return unavailable(checklist);
    if (!checklist.guideline) return reportingLine(checklist);
    const items = list(checklist.items);
    const summary = obj(checklist.summary);
    const guideline = obj(checklist.guideline);
    const paper = checklist.paper_available === false ? `<p class="rv-warn">${esc(t('study.checklist.noPaper'))}</p>` : '';
    const notes = list(checklist.notes).map((n) => `<p class="rv-warn">${esc(n)}</p>`).join('');
    return `<p>${esc(t('study.checklist.guideline', { name: guideline.name || guideline.id || DASH, version: guideline.version || DASH }))}</p>`
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

  function checklistButton(guideline) {
    const state = checklists[guideline] || null;
    const attr = guideline ? ` data-study-guideline="${esc(guideline)}"` : '';
    const label = guideline
      ? t(state && !state.loading ? 'study.checklist.rerunGuideline' : 'study.checklist.runGuideline', { guideline })
      : t(state && !state.loading ? 'study.checklist.rerun' : 'study.checklist.run');
    return `<button type="button" class="btn btn--sm" data-study-action="checklist"${attr}${state && state.loading ? ' disabled' : ''}>${esc(label)}</button>`;
  }

  function checklistHtml(reporting) {
    const head = reporting && reporting.available !== false ? reportingLine(reporting) : (reporting ? unavailable(reporting) : '');
    const others = reporting && reporting.available !== false ? list(reporting.additional_guidelines) : [];
    const extra = others.map((g) => `<div data-study-checklist="${esc(g)}"><h4>${esc(g)}</h4>
      <div class="rv-actions">${checklistButton(g)}</div>${checklistBody(checklists[g] || null)}</div>`).join('');
    return `<section class="rv-section" data-study-section="checklist"><h3>${esc(t('study.checklist.title'))}</h3>
      ${head}<div class="rv-actions">${checklistButton('')}</div>${checklistBody(checklists[''] || null)}${extra}</section>`;
  }

  const MEASUREMENT_TITLES = {
    instruments: 'study.instruments.title', measurements: 'study.measurements.title',
    uncertainty: 'study.uncertainty.title', agreement: 'study.agreement.title',
  };
  const MEASUREMENT_BODIES = {
    instruments: instrumentsBody, measurements: measurementsBody, uncertainty: uncertaintyBody, agreement: agreementBody,
  };

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
      ${MEASUREMENT_SECTIONS.filter((name) => view[name]).map((name) => section(name, MEASUREMENT_TITLES[name], view[name], MEASUREMENT_BODIES[name])).join('')}
      ${section('analysis', 'study.analysis.title', view.analysis, analysisBody)}
      ${view.deposit ? section('deposit', 'study.deposit.title', view.deposit, depositBody) : ''}
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

  async function act(action, guideline) {
    if (action === 'refresh') {
      notice = '';
      await refreshStudyPanel();
      return;
    }
    if (action === 'checklist') {
      const key = guideline || '';
      if (checklists[key] && checklists[key].loading) return;
      checklists[key] = { loading: true };
      render(lastView);
      try {
        checklists[key] = await getJson(key ? `/api/study/checklist?guideline=${encodeURIComponent(key)}` : '/api/study/checklist');
      } catch (err) {
        checklists[key] = { available: false, code: 'HTTP', message: err.message || String(err) };
      }
      render(lastView);
    }
  }

  document.addEventListener('click', (event) => {
    const el = event.target && event.target.closest && event.target.closest('[data-study-action]');
    if (!el || !el.dataset || !el.dataset.studyAction) return;
    act(el.dataset.studyAction, el.dataset.studyGuideline);
  });
  document.addEventListener('languagechange', () => { if (lastView) render(lastView); });

  window.StudyPanel = { html, render, act };
  window.refreshStudyPanel = refreshStudyPanel;
})();
