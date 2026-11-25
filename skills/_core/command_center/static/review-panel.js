/* Review pane: the review/ records of a review workspace (paper_kind "review").
 *
 * GET /api/review answers one object with a section per panel: summary
 * (review_cli.py status), protocol and registration, the search log, the
 * screening progress (pending per reviewer, conflicts, Cohen's kappa or why it
 * is not computable), the PRISMA 2020 flow (counts and the drawn figure), the
 * extraction table, the risk of bias (appraisal scores against the protocol's
 * threshold) and the sign-offs. A section the server could not read carries
 * {available: false, code, message} and is drawn as unavailable; the others
 * still render. The 27-item PRISMA checklist is slow (it runs paper_cli.py)
 * and loads only when the operator clicks its button, from
 * GET /api/review/checklist. Every value is escaped before insertion.
 *
 * Public surface (window): refreshReviewPanel(), ReviewPanel.{html, render, act}.
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
    if (Array.isArray(v)) return v.map(fmt).join(', ');
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  };

  // Literal catalogue keys (never composed) for the machine values the server sends.
  const STAGE_KEYS = { ta: 'sysreview.stage.ta', ft: 'sysreview.stage.ft' };
  const DECISION_KEYS = {
    include: 'sysreview.decision.include', exclude: 'sysreview.decision.exclude',
    'not-retrieved': 'sysreview.decision.notRetrieved',
  };
  const APPROVAL_KEYS = {
    absent: 'sysreview.protocol.approval.absent', approved: 'sysreview.protocol.approval.approved',
    changed: 'sysreview.protocol.approval.changed', corrupt: 'sysreview.protocol.approval.corrupt',
  };
  const GATE_KEYS = { screening: 'sysreview.signoffs.screening', synthesis: 'sysreview.signoffs.synthesis' };
  const RECORD_KEYS = {
    protocol: 'sysreview.checklist.record.protocol', approval: 'sysreview.checklist.record.approval',
    searches: 'sysreview.checklist.record.searches', screening: 'sysreview.checklist.record.screening',
    extraction: 'sysreview.checklist.record.extraction', appraisal: 'sysreview.checklist.record.appraisal',
    prisma: 'sysreview.checklist.record.prisma',
  };
  // PRISMA 2020 items 1-27, in order (review_cli.py CHECKLIST).
  const ITEM_KEYS = [
    'sysreview.checklist.item.1', 'sysreview.checklist.item.2', 'sysreview.checklist.item.3', 'sysreview.checklist.item.4',
    'sysreview.checklist.item.5', 'sysreview.checklist.item.6', 'sysreview.checklist.item.7', 'sysreview.checklist.item.8',
    'sysreview.checklist.item.9', 'sysreview.checklist.item.10', 'sysreview.checklist.item.11', 'sysreview.checklist.item.12',
    'sysreview.checklist.item.13', 'sysreview.checklist.item.14', 'sysreview.checklist.item.15', 'sysreview.checklist.item.16',
    'sysreview.checklist.item.17', 'sysreview.checklist.item.18', 'sysreview.checklist.item.19', 'sysreview.checklist.item.20',
    'sysreview.checklist.item.21', 'sysreview.checklist.item.22', 'sysreview.checklist.item.23', 'sysreview.checklist.item.24',
    'sysreview.checklist.item.25', 'sysreview.checklist.item.26', 'sysreview.checklist.item.27',
  ];

  let lastView = null;
  let checklist = null;   // null (not asked), {loading: true}, or the /api/review/checklist answer
  let notice = '';        // the last action's outcome, already translated

  const stageName = (stage) => (STAGE_KEYS[stage] ? t(STAGE_KEYS[stage]) : stage);
  const decisionName = (d) => (DECISION_KEYS[d] ? t(DECISION_KEYS[d]) : fmt(d));

  function unavailable(part) {
    return `<p class="rv-error" role="alert">${esc(t('sysreview.unavailable', { code: part.code || '', message: part.message || '' }))}</p>`;
  }

  function section(id, titleKey, part, body) {
    const content = part && part.available === false ? unavailable(part) : body(part || {});
    return `<section class="rv-section" data-review-section="${esc(id)}"><h3>${esc(t(titleKey))}</h3>${content}</section>`;
  }

  function table(headers, rows) {
    return `<div class="rv-table-wrap"><table class="rv-table"><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead>`
      + `<tbody>${rows.map((cells) => `<tr>${cells.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }

  function summaryHtml(part) {
    if (!part || part.available === false) return part ? unavailable(part) : '';
    const protocol = obj(part.protocol);
    const state = part.protocol === null || part.protocol === undefined
      ? t('sysreview.summary.noProtocol')
      : t(protocol.approved ? 'sysreview.summary.approved' : (protocol.valid ? 'sysreview.summary.valid' : 'sysreview.summary.invalid'));
    const chips = [
      state,
      t('sysreview.summary.searches', { n: part.searches ?? 0 }),
      t('sysreview.summary.records', { n: part.records ?? 0 }),
      t('sysreview.summary.included', { n: part.included ?? 0 }),
      t('sysreview.summary.appraised', { n: part.appraised ?? 0 }),
      t('sysreview.summary.extracted', { n: part.extracted ?? 0 }),
    ];
    return `<ul class="rv-summary">${chips.map((c) => `<li>${esc(c)}</li>`).join('')}</ul>`;
  }

  function protocolBody(p) {
    const registration = `<p class="rv-muted">${esc(t('sysreview.protocol.registration', {
      declaration: obj(p.registration).declaration || 'review-registration', item: obj(p.registration).checklist_item || 24,
    }))}</p>`;
    const approval = obj(p.approval);
    const approvalLine = `<p class="${approval.state === 'approved' ? 'rv-ok' : 'rv-warn'}">${esc(t(APPROVAL_KEYS[approval.state] || APPROVAL_KEYS.absent, {
      by: approval.by || '', at: approval.at || '', code: approval.code || '', message: approval.message || '',
    }))}</p>`;
    const amendments = list(approval.amendments).length
      ? `<h4>${esc(t('sysreview.protocol.amendments'))}</h4><ul>${list(approval.amendments).map((a) => `<li>${esc(t('sysreview.protocol.amendment', { by: a.by, at: a.at, reason: a.reason }))}</li>`).join('')}</ul>`
      : `<p class="rv-muted">${esc(t('sysreview.protocol.noAmendments'))}</p>`;
    if (!p.present) {
      return `<p>${esc(t('sysreview.protocol.absent'))}</p>${approval.state && approval.state !== 'absent' ? approvalLine : ''}${registration}`;
    }
    const problems = p.valid ? '' : `<h4 class="rv-error">${esc(t('sysreview.protocol.problems', { n: list(p.problems).length }))}</h4>`
      + `<ul>${list(p.problems).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>`;
    const questions = list(p.research_questions).map((rq) => {
      const picoc = Object.entries(obj(rq.picoc)).filter(([, v]) => v).map(([k, v]) => `${esc(k)}: ${esc(v)}`).join(' · ');
      return `<li><strong>${esc(rq.id)}</strong> ${esc(rq.question)}${picoc ? `<span class="rv-quote">${picoc}</span>` : ''}</li>`;
    }).join('');
    const criteria = (kind, key) => `<h4>${esc(t(key))}</h4><ul>${list(obj(p.criteria)[kind]).map((c) => `<li><strong>${esc(c.id)}</strong> ${esc(c.text)}${c.reason ? ` <span class="rv-muted">(${esc(c.reason)})</span>` : ''}</li>`).join('') || `<li class="rv-muted">${esc(DASH)}</li>`}</ul>`;
    const sources = list(p.sources).length
      ? table([t('sysreview.protocol.source'), t('sysreview.protocol.query')], list(p.sources).map((s) => [esc(s.name), esc(s.query)]))
      : `<p class="rv-muted">${esc(DASH)}</p>`;
    const dates = obj(p.date_range);
    return `<p><strong>${esc(p.title)}</strong></p><p>${esc(p.objective)}</p>
      <p class="rv-muted">${esc(t('sysreview.protocol.meta', {
        type: p.review_type || DASH, guidelines: fmt(p.guidelines), from: dates.from || DASH, to: dates.to || DASH,
        languages: fmt(p.languages), types: fmt(p.publication_types), reviewers: fmt(p.reviewers),
      }))}</p>
      ${approvalLine}${amendments}${problems}
      <h4>${esc(t('sysreview.protocol.questions'))}</h4><ul>${questions || `<li class="rv-muted">${esc(DASH)}</li>`}</ul>
      ${criteria('inclusion', 'sysreview.protocol.inclusion')}${criteria('exclusion', 'sysreview.protocol.exclusion')}
      <h4>${esc(t('sysreview.protocol.sources'))}</h4>${sources}${registration}`;
  }

  function searchesBody(s) {
    const rows = list(s.rows).map((r) => [esc(r.id), esc(r.source), esc(r.query), esc(fmt(r.method)),
      esc(fmt(r.run_at)), esc(fmt(r.total)), esc(fmt(r.retrieved)), esc(fmt(r.file))]);
    const log = rows.length
      ? table([t('sysreview.searches.id'), t('sysreview.protocol.source'), t('sysreview.protocol.query'), t('sysreview.searches.method'),
        t('sysreview.searches.runAt'), t('sysreview.searches.total'), t('sysreview.searches.retrieved'), t('sysreview.searches.file')], rows)
      : `<p class="rv-muted">${esc(t('sysreview.searches.empty'))}</p>`;
    const missing = list(s.not_searched).length
      ? `<p class="rv-warn">${esc(t('sysreview.searches.notSearched', { sources: list(s.not_searched).join(', ') }))}</p>` : '';
    return `${log}<p>${esc(t('sysreview.searches.totals', { records: s.records ?? 0, duplicates: s.duplicates ?? 0, unique: s.unique ?? 0 }))}</p>${missing}`;
  }

  function kappaLine(k) {
    k = obj(k);
    if (k.value !== null && k.value !== undefined) {
      return t('sysreview.screening.kappa', { kappa: k.value, agreement: fmt(k.agreement), n: k.records ?? 0 });
    }
    if (k.code === 'REVIEWERS_AMBIGUOUS') return t('sysreview.screening.kappaReviewers', { message: k.message || '' });
    if (k.code === 'NO_SHARED_RECORDS') return t('sysreview.screening.kappaNoShared');
    return t('sysreview.screening.kappaUnavailable', { code: k.code || '', message: k.message || '' });
  }

  function stageHtml(st) {
    const pending = Object.entries(obj(st.pending_by_reviewer));
    const pendingLine = pending.length
      ? t('sysreview.screening.pending', { list: pending.map(([name, n]) => `${name}: ${n}`).join(', ') })
      : t('sysreview.screening.noReviewer');
    const decisions = Object.entries(obj(st.decisions)).map(([d, n]) => `${decisionName(d)}: ${n}`).join(', ') || DASH;
    const conflicts = list(st.conflicts).length
      ? table([t('sysreview.screening.record'), t('sysreview.screening.titleCol'), t('sysreview.screening.votes')],
        list(st.conflicts).map((c) => [esc(c.record_id), esc(c.title),
          esc(Object.entries(obj(c.votes)).map(([who, v]) => `${who}: ${decisionName(obj(v).decision)}${obj(v).reason ? ` (${obj(v).reason})` : ''}`).join('; '))]))
      : `<p class="rv-muted">${esc(t('sysreview.screening.noConflicts'))}</p>`;
    return `<h4>${esc(stageName(st.stage))}</h4>
      <p>${esc(t('sysreview.screening.totals', {
        eligible: st.eligible ?? 0, decided: st.decided ?? 0, agreed: st.agreed ?? 0, final: st.final ?? 0,
        partial: st.partial ?? 0, undecided: st.undecided ?? 0, conflicts: st.conflict_count ?? 0,
      }))}</p>
      <p>${esc(t('sysreview.screening.decisions', { list: decisions }))}</p>
      <p>${esc(pendingLine)}</p>
      <p class="${obj(st.kappa).value !== null && obj(st.kappa).value !== undefined ? '' : 'rv-warn'}">${esc(kappaLine(st.kappa))}</p>
      ${conflicts}`;
  }

  function screeningBody(s) {
    return `<p class="rv-muted">${esc(t('sysreview.screening.required', { n: s.required_reviewers ?? 2 }))}</p>${list(s.stages).map(stageHtml).join('')}`;
  }

  function prismaBody(p) {
    const flow = obj(p.flow);
    const figure = flow.exists
      ? `<div class="rv-flow"><img alt="${esc(t('sysreview.prisma.figureAlt'))}" src="/api/artifact?path=${encodeURIComponent(flow.path)}&amp;v=${esc(flow.mtime || 0)}">
          <p><a href="/api/artifact?path=${encodeURIComponent(flow.path)}" target="_blank" rel="noopener">${esc(t('sysreview.prisma.openFigure', { path: flow.path }))}</a></p></div>`
      : `<p class="rv-warn">${esc(t('sysreview.prisma.noFigure', { path: flow.path || 'paper/Figures/prisma-flow.svg' }))}</p>`;
    if (!p.counts) return `<p class="rv-muted">${esc(t('sysreview.prisma.noRecords'))}</p>${figure}`;
    const ident = obj(p.counts.identification);
    const screen = obj(p.counts.screening);
    const excluded = Object.entries(obj(screen.reports_excluded)).map(([r, n]) => `${r}: ${n}`).join(', ') || '0';
    const databases = Object.entries(obj(ident.databases)).map(([db, n]) => `${db}: ${n}`).join(', ') || DASH;
    const rows = [
      [t('sysreview.prisma.identified'), fmt(ident.records)], [t('sysreview.prisma.databases'), databases],
      [t('sysreview.prisma.duplicates'), fmt(ident.duplicates_removed)], [t('sysreview.prisma.screened'), fmt(screen.records_screened)],
      [t('sysreview.prisma.excluded'), fmt(screen.records_excluded)], [t('sysreview.prisma.sought'), fmt(screen.reports_sought)],
      [t('sysreview.prisma.notRetrieved'), fmt(screen.reports_not_retrieved)], [t('sysreview.prisma.assessed'), fmt(screen.reports_assessed)],
      [t('sysreview.prisma.reportsExcluded'), excluded], [t('sysreview.prisma.includedStudies'), fmt(obj(p.counts.included).studies)],
    ].map(([label, value]) => [esc(label), esc(value)]);
    const saved = p.saved === null || p.saved === undefined
      ? t('sysreview.prisma.notSaved')
      : (obj(p.saved).code ? t('sysreview.prisma.savedUnreadable', { code: p.saved.code, message: p.saved.message || '' })
        : t(p.saved.current ? 'sysreview.prisma.savedCurrent' : 'sysreview.prisma.savedStale', { at: p.saved.generated_at || '' }));
    const pending = p.pending ? `<p class="rv-warn">${esc(t('sysreview.prisma.provisional', { n: p.pending }))}</p>` : '';
    return `${table([t('sysreview.prisma.box'), t('sysreview.prisma.count')], rows)}${pending}
      <p class="${p.saved && p.saved.current ? 'rv-muted' : 'rv-warn'}">${esc(saved)}</p>${figure}`;
  }

  function cell(item) {
    if (!item) return `<span class="rv-muted">${esc(DASH)}</span>`;
    const source = [item.quote ? `“${item.quote}”` : '', item.page !== null && item.page !== undefined && item.page !== ''
      ? t('sysreview.extraction.page', { page: item.page }) : ''].filter(Boolean).join(' · ');
    return `${esc(fmt(item.value))}${source ? `<span class="rv-quote">${esc(source)}</span>` : ''}`;
  }

  function extractionBody(x) {
    const fields = list(x.fields);
    const studies = list(x.studies);
    const counts = `<p>${esc(t('sysreview.extraction.counts', { extracted: x.extracted ?? 0, included: x.included ?? 0 }))}</p>`;
    if (!studies.length) return `${counts}<p class="rv-muted">${esc(t('sysreview.extraction.empty'))}</p>`;
    const headers = [t('sysreview.extraction.study'), ...fields.map((f) => f.id), t('sysreview.extraction.by')];
    const rows = studies.map((s) => [
      `<strong>${esc(s.record_id)}</strong> ${esc(s.title)}${s.year ? ` (${esc(s.year)})` : ''}${s.included ? '' : `<span class="rv-quote rv-warn">${esc(t('sysreview.notIncluded'))}</span>`}`,
      ...fields.map((f) => (s.extracted ? cell(obj(s.values)[f.id]) : `<span class="rv-warn">${esc(t('sysreview.extraction.owed'))}</span>`)),
      esc(s.extracted ? `${s.extractor || DASH} · ${s.at || DASH}` : DASH),
    ]);
    const legend = fields.length
      ? `<ul class="rv-muted">${fields.map((f) => `<li><strong>${esc(f.id)}</strong> (${esc(f.type)}) ${esc(f.description)}</li>`).join('')}</ul>` : '';
    return `${counts}${table(headers, rows)}${legend}`;
  }

  function appraisalBody(a) {
    const questions = list(a.questions);
    const threshold = a.threshold === null || a.threshold === undefined
      ? t('sysreview.appraisal.noThreshold') : t('sysreview.appraisal.threshold', { threshold: a.threshold });
    const scale = Object.entries(obj(a.scale)).map(([k, v]) => `${k} = ${v}`).join(', ') || DASH;
    const head = `<p>${esc(t('sysreview.appraisal.tool', { tool: a.tool || DASH, scale }))}</p><p>${esc(threshold)}</p>
      <p class="rv-muted">${esc(t('sysreview.appraisal.basis'))}</p>`;
    const qlist = questions.length
      ? `<ul class="rv-muted">${questions.map((q) => `<li><strong>${esc(q.id)}</strong> ${esc(q.text)}</li>`).join('')}</ul>` : '';
    const studies = list(a.studies);
    const rows = studies.map((s) => [
      `<strong>${esc(s.record_id)}</strong> ${esc(s.title)}${s.included ? '' : `<span class="rv-quote rv-warn">${esc(t('sysreview.notIncluded'))}</span>`}`,
      esc(s.reviewer),
      ...questions.map((q) => esc(fmt(obj(s.answers)[q.id]))),
      esc(`${fmt(s.score)} / ${fmt(s.max_score)}`),
      s.below_threshold ? `<span class="rv-error">${esc(t('sysreview.appraisal.below'))}</span>`
        : `<span class="rv-ok">${esc(t(a.threshold === null || a.threshold === undefined ? 'sysreview.appraisal.noComparison' : 'sysreview.appraisal.atOrAbove'))}</span>`,
    ]);
    const tableHtml = rows.length
      ? table([t('sysreview.extraction.study'), t('sysreview.appraisal.reviewer'), ...questions.map((q) => q.id),
        t('sysreview.appraisal.score'), t('sysreview.appraisal.vsThreshold')], rows)
      : `<p class="rv-muted">${esc(t('sysreview.appraisal.empty'))}</p>`;
    const owed = list(a.not_appraised).length
      ? `<p class="rv-warn">${esc(t('sysreview.appraisal.owed', { list: list(a.not_appraised).join(', ') }))}</p>` : '';
    return `${head}${qlist}${tableHtml}${owed}`;
  }

  function signoffsBody(s) {
    const gates = obj(s.gates);
    return `<ul>${Object.keys(GATE_KEYS).map((gate) => {
      const g = gates[gate];
      const state = !g ? t('sysreview.signoffs.absent')
        : t(g.current ? 'sysreview.signoffs.current' : 'sysreview.signoffs.stale', { by: g.by || '', at: g.at || '' });
      return `<li><strong>${esc(t(GATE_KEYS[gate]))}</strong>: <span class="${g && g.current ? 'rv-ok' : 'rv-warn'}">${esc(state)}</span>${g && g.note ? ` <span class="rv-muted">${esc(g.note)}</span>` : ''}</li>`;
    }).join('')}</ul><p class="rv-muted">${esc(t('sysreview.signoffs.operator'))}</p>`;
  }

  function missingText(entry) {
    const [kind, ...rest] = String(entry).split(':');
    const value = rest.join(':');
    if (kind === 'record') return t('sysreview.checklist.missingRecord', { record: RECORD_KEYS[value] ? t(RECORD_KEYS[value]) : value });
    if (kind === 'text') return t('sysreview.checklist.missingText', { target: value });
    if (kind === 'declaration') return t('sysreview.checklist.missingDeclaration', { declaration: value });
    return String(entry);
  }

  function checklistHtml() {
    const button = `<button type="button" class="btn btn--sm" data-review-action="checklist"${checklist && checklist.loading ? ' disabled' : ''}>${esc(t(checklist && !checklist.loading ? 'sysreview.checklist.rerun' : 'sysreview.checklist.run'))}</button>`;
    let body = `<p class="rv-muted">${esc(t('sysreview.checklist.onDemand'))}</p>`;
    if (checklist && checklist.loading) body = `<p class="rv-muted" role="status">${esc(t('sysreview.checklist.loading'))}</p>`;
    else if (checklist && checklist.available === false) body = unavailable(checklist);
    else if (checklist) {
      const items = list(checklist.items);
      const owed = items.filter((i) => i.status === 'owed').length;
      const paper = checklist.paper_available === false
        ? `<p class="rv-warn">${esc(t('sysreview.checklist.noPaper'))}</p>` : '';
      body = `<p>${esc(t('sysreview.checklist.counts', { satisfied: items.length - owed, total: items.length, owed }))}</p>${paper}`
        + table([t('sysreview.checklist.item'), t('sysreview.checklist.topic'), t('sysreview.checklist.status'), t('sysreview.checklist.missing')],
          items.map((i) => [esc(i.item),
            esc(ITEM_KEYS[Number(i.item) - 1] ? t(ITEM_KEYS[Number(i.item) - 1]) : i.topic),
            `<span class="${i.status === 'satisfied' ? 'rv-ok' : 'rv-warn'}">${esc(t(i.status === 'satisfied' ? 'sysreview.checklist.satisfied' : 'sysreview.checklist.owed'))}</span>`,
            list(i.missing).length ? `<ul>${list(i.missing).map((m) => `<li>${esc(missingText(m))}</li>`).join('')}</ul>` : esc(DASH)]));
    }
    return `<section class="rv-section" data-review-section="checklist"><h3>${esc(t('sysreview.checklist.title'))}</h3>
      <div class="rv-actions">${button}</div>${body}</section>`;
  }

  function html(view) {
    view = obj(view);
    if (view.error) return `<p class="rv-error" role="alert">${esc(view.error)}</p>`;
    const warning = view.cli_warning
      ? `<p class="rv-warn" role="alert">${esc(t('sysreview.cliWarning', { warning: view.cli_warning }))}</p>` : '';
    const note = notice ? `<p class="rv-muted" role="status">${esc(notice)}</p>` : '';
    return `<div class="rv-actions"><button type="button" class="btn btn--sm" data-review-action="refresh">${esc(t('sysreview.refresh'))}</button></div>
      ${warning}${note}${summaryHtml(view.summary)}
      ${section('protocol', 'sysreview.protocol.title', view.protocol, protocolBody)}
      ${section('searches', 'sysreview.searches.title', view.searches, searchesBody)}
      ${section('screening', 'sysreview.screening.title', view.screening, screeningBody)}
      ${section('prisma', 'sysreview.prisma.title', view.prisma, prismaBody)}
      ${section('extraction', 'sysreview.extraction.title', view.extraction, extractionBody)}
      ${section('appraisal', 'sysreview.appraisal.title', view.appraisal, appraisalBody)}
      ${section('signoffs', 'sysreview.signoffs.title', view.signoffs, signoffsBody)}
      ${checklistHtml()}`;
  }

  function render(view) {
    lastView = view;
    const host = document.getElementById('reviewPanel');
    if (host) host.innerHTML = html(view);
  }

  async function getJson(url) {
    const response = await fetch(url, { cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = data && data.code === 'NOT_A_REVIEW_WORKSPACE'
        ? t('sysreview.notReview', { kind: data.paper_kind || '' })
        : t('sysreview.readFailed', { error: (data && (data.error || data.detail)) || `HTTP ${response.status}` });
      throw new Error(error);
    }
    return data;
  }

  async function refreshReviewPanel() {
    try {
      render(await getJson('/api/review'));
    } catch (err) {
      render({ error: err.message || String(err) });
    }
  }

  async function act(action) {
    if (action === 'refresh') {
      notice = '';
      await refreshReviewPanel();
      return;
    }
    if (action === 'checklist') {
      if (checklist && checklist.loading) return;
      checklist = { loading: true };
      render(lastView);
      try {
        checklist = await getJson('/api/review/checklist');
      } catch (err) {
        checklist = { available: false, code: 'HTTP', message: err.message || String(err) };
      }
      render(lastView);
    }
  }

  document.addEventListener('click', (event) => {
    const el = event.target && event.target.closest && event.target.closest('[data-review-action]');
    if (!el || !el.dataset || !el.dataset.reviewAction) return;
    act(el.dataset.reviewAction);
  });
  document.addEventListener('languagechange', () => { if (lastView) render(lastView); });

  window.ReviewPanel = { html, render, act };
  window.refreshReviewPanel = refreshReviewPanel;
})();
