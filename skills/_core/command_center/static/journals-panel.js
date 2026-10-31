/* Journals and venue panel of the PDF Preview tab.
 *
 * Journal finder: a quartile range (from Q? to Q?), open-access, APC, review-time
 * and limit filters; "Search journals" runs POST /api/journals/search (the
 * journal-finder CLI in a worker thread) and "Analyze with agent" sends
 * `/journal-finder <range> [flags]` to the CLI console. The results table comes
 * from paper/journal-candidates.json (GET /api/journals): quartile with its
 * source (SJR or the labelled OpenAlex proxy), access, APC, h-index, review-time
 * estimate, fit score and its components (`fit`), facet hits and gate (`facets`),
 * flags and the similar works that justify the fit. Above the table: the scoring
 * formula (`query.scoring`) and the calls made / served from the cache per service
 * with the OpenAlex budget state (`api_calls`). "Force refresh" sends `no_cache`.
 * The field names are the journal-finder CLI's own. The SJR line links to
 * scimagojr.com and uploads the CSV.
 *
 * Venue adaptation: "Choose this journal" runs `venue select`; the "Chosen
 * journal" card shows the venue state machine and its next action, the audit
 * findings (smith side against venue side, with quote and url), the plan with
 * "Approve plan" (the operator's statement, bound to the plan's sha256) and
 * "Request changes", the agent buttons, "Build and compile venue version" and
 * the canonical / venue PDF toggle. Nothing here submits anything.
 *
 * Every value is escaped before insertion. Public surface (window):
 * refreshJournalsPanel(), JournalsPanel (the pure HTML builders and the
 * command builders, for the render tests).
 */
(function () {
  'use strict';

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const list = (v) => (Array.isArray(v) ? v : []);
  const obj = (v) => (v && typeof v === 'object' && !Array.isArray(v) ? v : {});
  const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
  const httpUrl = (v) => (/^https?:\/\/[^\s]+$/i.test(String(v ?? '')) ? String(v) : '');
  const link = (url, label) => {
    const safe = httpUrl(url);
    const text = label === undefined || label === null ? url : label;
    return safe ? `<a href="${esc(safe)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>` : esc(text);
  };
  const doiLink = (doi) => {
    const bare = String(doi ?? '').trim().replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, '');
    if (!/^10\.\d{4,9}\/\S+$/.test(bare)) return esc(doi);
    return `<a href="${esc(`https://doi.org/${encodeURI(bare)}`)}" target="_blank" rel="noopener noreferrer">${esc(bare)}</a>`;
  };
  const oneLine = (v) => String(v ?? '').replace(/\s+/g, ' ').trim();

  const QUARTILES = ['Q1', 'Q2', 'Q3', 'Q4'];
  const QUARTILE_BADGE = { Q1: 'badge--ok', Q2: 'badge--info', Q3: 'badge--warn', Q4: 'badge--bad' };
  const SEVERITY_BADGE = { blocker: 'badge--bad', major: 'badge--warn', minor: 'badge--info' };
  const SEVERITY_LABEL = {
    blocker: () => t('venue.severity.blocker'),
    major: () => t('venue.severity.major'),
    minor: () => t('venue.severity.minor'),
  };
  const RESOLVED_LABEL = {
    'operator-decision': () => t('venue.resolved.operator'),
    'text-change': () => t('venue.resolved.text'),
    build: () => t('venue.resolved.build'),
  };
  const FLAG_LABEL = {
    'no-application-evidence': () => t('journals.flag.noApplicationEvidence'),
    'apc-unknown': () => t('journals.flag.apcUnknown'),
    'review-time-unknown': () => t('journals.flag.reviewTimeUnknown'),
  };
  const STEP_LABEL = {
    selected: () => t('venue.step.selected'),
    requirements: () => t('venue.step.requirements'),
    template: () => t('venue.step.template'),
    audited: () => t('venue.step.audited'),
    planned: () => t('venue.step.planned'),
    approved: () => t('venue.step.approved'),
    built: () => t('venue.step.built'),
    compiled: () => t('venue.step.compiled'),
  };
  const NEXT_LABEL = {
    analyze: () => t('venue.next.analyze'),
    plan: () => t('venue.next.plan'),
    approve: () => t('venue.next.approve'),
    build: () => t('venue.next.build'),
    rebuild: () => t('venue.next.rebuild'),
    compile: () => t('venue.next.compile'),
    done: () => t('venue.next.done'),
  };
  const SORT_LABEL = {
    fit: () => t('journals.sort.fit'),
    review: () => t('journals.sort.review'),
    hindex: () => t('journals.sort.hindex'),
  };

  const state = {
    journals: null,        // GET /api/journals
    venues: [],            // GET /api/venues
    slug: null,            // the venue whose card is open
    detail: null,          // GET /api/venues/<slug>
    pdfView: 'canonical',
    sort: 'fit',
    busy: {},
    message: null,
    sjrMessage: null,
    statement: '',
    note: '',
    sjrYear: '',
    form: { from: 'Q1', to: 'Q2', oaOnly: false, maxApc: '', maxReview: '', limit: '15', noCache: false },
  };

  // ---------------------------------------------------------------- commands

  const rangeText = (form) => (form.from === form.to ? form.from : `${form.from}-${form.to}`);
  const rangeValid = (form) => QUARTILES.indexOf(form.from) >= 0 && QUARTILES.indexOf(form.to) >= 0
    && QUARTILES.indexOf(form.from) <= QUARTILES.indexOf(form.to);
  const wholeOrNull = (text, min, max) => {
    const raw = String(text ?? '').trim();
    if (!/^\d+$/.test(raw)) return null;
    const n = Number(raw);
    return n >= min && n <= max ? n : null;
  };
  const numberOrNull = (text) => {
    const raw = String(text ?? '').trim();
    if (!/^\d+(\.\d+)?$/.test(raw)) return null;
    return Number(raw);
  };

  // The slash command "Analyze with agent" sends.
  function agentCommand(form) {
    const parts = ['/journal-finder', rangeText(form)];
    if (form.oaOnly) parts.push('--oa-only');
    const apc = numberOrNull(form.maxApc);
    if (apc !== null) parts.push('--max-apc', String(apc));
    const days = wholeOrNull(form.maxReview, 1, 3650);
    if (days !== null) parts.push('--max-review-days', String(days));
    const limit = wholeOrNull(form.limit, 1, 50);
    if (limit !== null) parts.push('--limit', String(limit));
    return parts.join(' ');
  }

  // The JSON body of POST /api/journals/search.
  function searchBody(form) {
    const body = { quartiles: rangeText(form), oa_only: !!form.oaOnly };
    const apc = numberOrNull(form.maxApc);
    if (apc !== null) body.max_apc = apc;
    const days = wholeOrNull(form.maxReview, 1, 3650);
    if (days !== null) body.max_review_days = days;
    const limit = wholeOrNull(form.limit, 1, 50);
    if (limit !== null) body.limit = limit;
    // "Force refresh": the CLI's --no-cache, neither reading nor writing the response cache.
    if (form.noCache) body.no_cache = true;
    return body;
  }

  // Instructions for the agents. They stay in English whatever the page
  // language is: they are messages between agents and tools.
  const instructions = {
    analyze(slug, journal) {
      return `/paper-writing venue adaptation for "${slug}" (${oneLine(journal)}): use the venue-adapter agent. `
        + 'Read the journal author guidelines and its document template, then store requirements.json '
        + `(every requirement with its quote and url) and run venue requirements, venue acquire and venue diff for --slug ${slug}; `
        + 'if the audit calls for it, write the adjustment plan and store it with venue plan. '
        + 'Never edit paper/main.tex or sections/, never invent a requirement and never submit anything.';
    },
    apply(slug, sha) {
      return `/paper-writing apply the approved venue plan for "${slug}": read paper/venues/${slug}/plan.md `
        + `(sha256 ${sha}, approved by the operator). Apply its text changes only through the write loop `
        + '(redactor, contract-auditor, write --draft --audit), one block at a time, and re-run '
        + `venue diff --slug ${slug} after each item, reporting the remaining findings. `
        + 'A section the plan leaves to the operator is not invented.';
    },
    changes(slug, note) {
      return `/paper-writing revise the venue plan for "${slug}" with the venue-adapter agent. `
        + `The operator asks for these changes: ${oneLine(note)} `
        + `Rewrite the plan, keep citing the finding ids, and store it with venue plan --slug ${slug} `
        + '(storing a plan resets the approval; the operator approves its exact text again).';
    },
  };

  // ------------------------------------------------------------------ pieces

  const fixed = (v, digits) => (isNum(v) ? v.toFixed(digits) : '');
  const weeks = (days) => (Math.round((days / 7) * 10) / 10).toString();

  function quartileCell(c) {
    const q = c.quartile;
    const source = c.quartile_source;
    const badge = q
      ? `<span class="badge ${esc(QUARTILE_BADGE[q] || 'badge--info')}">${esc(q)}</span>`
      : `<span class="badge badge--absent">${esc(t('journals.quartile.none'))}</span>`;
    let detail = '';
    if (source === 'sjr') {
      const sjr = obj(c.sjr);
      detail = esc(t('journals.quartile.sjr'));
      if (isNum(sjr.value)) detail += ` ${esc(fixed(sjr.value, 3))}`;
      if (sjr.year) detail += ` · ${esc(sjr.year)}`;
      // [{name, quartile}] as the CLI writes them; a plain string is shown as is.
      const categories = list(sjr.categories).map((entry) => (entry && typeof entry === 'object'
        ? `${oneLine(entry.name)} (${oneLine(entry.quartile)})` : oneLine(entry))).filter(Boolean);
      if (categories.length) detail = `<span title="${esc(categories.join(', '))}">${detail}</span>`;
    } else if (source === 'openalex-proxy') {
      const proxy = obj(c.proxy);
      detail = `<span class="journals-proxy">${esc(t('journals.quartile.proxy'))}</span>`;
      if (isNum(proxy.percentile)) detail += ` · ${esc(t('journals.quartile.percentile', { value: fixed(proxy.percentile, 1) }))}`;
    }
    return `${badge}<div class="panel__meta">${detail}</div>`;
  }

  function accessCell(c) {
    const open = c.is_oa
      ? `<span class="badge badge--ok">${esc(t('journals.oa'))}</span>`
      : `<span class="badge badge--absent">${esc(t('journals.subscription'))}</span>`;
    const doaj = c.is_in_doaj ? ` <span class="badge badge--info">DOAJ</span>` : '';
    const apc = isNum(c.apc_usd) ? esc(t('journals.apc', { value: Math.round(c.apc_usd) })) : esc(t('journals.apc.unknown'));
    return `${open}${doaj}<div class="panel__meta">${apc}</div>`;
  }

  function reviewCell(review) {
    const r = obj(review);
    const n = isNum(r.n) ? r.n : 0;
    if (r.source === 'none' || r.source === undefined || !isNum(r.median_days)) {
      const extra = n ? ` <span class="panel__meta">n=${esc(n)}</span>` : '';
      return `<span class="panel__meta" title="${esc(t('journals.review.estimate'))}">${esc(t('journals.review.none'))}</span>${extra}`;
    }
    const value = t('journals.review.value', {
      median: weeks(r.median_days),
      p25: isNum(r.p25_days) ? weeks(r.p25_days) : '?',
      p75: isNum(r.p75_days) ? weeks(r.p75_days) : '?',
      n,
    });
    return `<span title="${esc(t('journals.review.estimate'))}">${esc(value)}</span> `
      + `<span class="badge badge--info">${esc(r.source)}</span>`;
  }

  function fitCell(c) {
    if (!isNum(c.fit_score) && !c.fit) return '<span class="panel__meta">—</span>';
    const fit = obj(c.fit);
    const parts = [
      ['journals.fit.similar', fit.similar_works], ['journals.fit.cited', fit.cited_in_paper],
      ['journals.fit.topic', fit.topic_overlap],
    ].filter(([, v]) => isNum(v)).map(([key, v]) => `${esc(t(key))} ${esc(fixed(v, 2))}`);
    const score = isNum(c.fit_score) ? `<strong>${esc(fixed(c.fit_score, 2))}</strong>` : '';
    return `${score}<div class="panel__meta">${parts.join(' · ')}</div>`;
  }

  // Hit counts are whole numbers, the overlap and the gate short decimals.
  const plain = (v) => (isNum(v) ? String(Math.round(v * 100) / 100) : oneLine(v));

  function evidenceCell(c) {
    const facets = obj(c.facets);
    const facetBits = [['method', 'journals.facet.method'], ['application', 'journals.facet.application'],
      ['application_topic_overlap', 'journals.facet.overlap']]
      .filter(([k]) => facets[k] !== undefined && facets[k] !== null)
      .map(([k, key]) => `${esc(t(key))} ${esc(plain(facets[k]))}`);
    if (isNum(facets.gate) && facets.gate < 1) {
      facetBits.push(esc(t('journals.facet.gate', { value: plain(facets.gate) })));
    }
    const flags = list(c.flags).map((flag) => {
      const label = FLAG_LABEL[flag] ? FLAG_LABEL[flag]() : flag;
      return `<span class="badge badge--warn">${esc(label)}</span>`;
    }).join(' ');
    const works = list(c.similar_works);
    const count = isNum(c.similar_works_count) ? c.similar_works_count : works.length;
    const items = works.map((w) => {
      const work = obj(w);
      const year = work.year ? ` (${esc(work.year)})` : '';
      const doi = work.doi ? ` · ${doiLink(work.doi)}` : '';
      return `<li>${esc(work.title || '—')}${year}${doi}</li>`;
    }).join('');
    const details = works.length
      ? `<details class="journals-works"><summary>${esc(t('journals.works.count', { count }))}</summary><ul>${items}</ul></details>`
      : `<span class="panel__meta">${esc(t('journals.works.none'))}</span>`;
    return `${facetBits.length ? `<div class="panel__meta">${facetBits.join(' · ')}</div>` : ''}`
      + `${flags ? `<div>${flags}</div>` : ''}${details}`;
  }

  function journalCell(c) {
    const home = httpUrl(c.homepage_url)
      ? ` <a href="${esc(c.homepage_url)}" target="_blank" rel="noopener noreferrer" title="${esc(t('journals.home'))}">↗</a>`
      : '';
    const issn = c.issn_l ? ` · ISSN ${esc(c.issn_l)}` : '';
    return `<strong>${esc(c.display_name || c.openalex_id || '—')}</strong>${home}`
      + `<div class="panel__meta">${esc(c.publisher || '')}${issn}</div>`;
  }

  function sortedCandidates(doc, sort) {
    const rows = list(doc && doc.candidates).slice();
    const fitKey = (c) => (isNum(c.fit_score) ? c.fit_score : -1);
    if (sort === 'review') {
      const days = (c) => (isNum(obj(c.review_time).median_days) && obj(c.review_time).source !== 'none'
        ? obj(c.review_time).median_days : Infinity);
      rows.sort((a, b) => days(a) - days(b) || fitKey(b) - fitKey(a));
    } else if (sort === 'hindex') {
      rows.sort((a, b) => (isNum(b.h_index) ? b.h_index : -1) - (isNum(a.h_index) ? a.h_index : -1));
    } else {
      rows.sort((a, b) => fitKey(b) - fitKey(a));
    }
    return rows;
  }

  // ------------------------------------------------------------ HTML builders

  function messageHtml(message) {
    if (!message || !message.text) return '';
    const kind = ['ok', 'warn', 'bad'].indexOf(message.kind) >= 0 ? message.kind : 'warn';
    return `<div class="journals-msg journals-msg--${kind}" role="status">${esc(message.text)}</div>`;
  }

  function formHtml(s) {
    const form = s.form;
    const options = (selected) => QUARTILES.map((q) =>
      `<option value="${q}"${q === selected ? ' selected' : ''}>${q}</option>`).join('');
    const bad = rangeValid(form) ? '' : `<div class="journals-msg journals-msg--bad">${esc(t('journals.form.rangeInvalid'))}</div>`;
    const sorts = Object.keys(SORT_LABEL).map((key) =>
      `<option value="${key}"${key === s.sort ? ' selected' : ''}>${esc(SORT_LABEL[key]())}</option>`).join('');
    return `<div class="journals-form">`
      + `<label>${esc(t('journals.form.from'))}<select data-jp-field="from">${options(form.from)}</select></label>`
      + `<label>${esc(t('journals.form.to'))}<select data-jp-field="to">${options(form.to)}</select></label>`
      + `<label class="journals-check"><input type="checkbox" data-jp-field="oaOnly"${form.oaOnly ? ' checked' : ''}> ${esc(t('journals.form.oaOnly'))}</label>`
      + `<label class="journals-check" title="${esc(t('journals.form.noCacheTitle'))}"><input type="checkbox" data-jp-field="noCache"${form.noCache ? ' checked' : ''}> ${esc(t('journals.form.noCache'))}</label>`
      + `<label>${esc(t('journals.form.maxApc'))}<input type="number" min="0" step="1" data-jp-field="maxApc" value="${esc(form.maxApc)}"></label>`
      + `<label>${esc(t('journals.form.maxReview'))}<input type="number" min="1" step="1" data-jp-field="maxReview" value="${esc(form.maxReview)}"></label>`
      + `<label>${esc(t('journals.form.limit'))}<input type="number" min="1" max="50" step="1" data-jp-field="limit" value="${esc(form.limit)}"></label>`
      + `<button type="button" class="btn btn--primary btn--sm" data-jp-action="search"${s.busy.search ? ' disabled' : ''}>`
      + `${esc(s.busy.search ? t('journals.searching') : t('journals.search'))}</button>`
      + `<button type="button" class="btn btn--sm" data-jp-action="analyze" title="${esc(t('journals.analyzeTitle'))}">${esc(t('journals.analyze'))}</button>`
      + `<label>${esc(t('journals.sort.label'))}<select data-jp-field="sort">${sorts}</select></label>`
      + `</div>${bad}`;
  }

  function sjrHtml(s) {
    const data = s.journals || {};
    const sjr = obj(data.sjr);
    const url = data.sjr_download_url || 'https://www.scimagojr.com/journalrank.php';
    const file = sjr.file ? String(sjr.file).split(/[\\/]/).pop() : '';
    const line = sjr.file
      ? esc(t('journals.sjr.file', { file, year: sjr.year ?? '?' }))
      : esc(t('journals.sjr.none'));
    return `<div class="journals-sjr"><span>${line}</span> `
      + `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(t('journals.sjr.download'))}</a> `
      + `<label>${esc(t('journals.sjr.year'))}<input type="number" min="1999" step="1" data-jp-field="sjrYear" value="${esc(s.sjrYear)}"></label> `
      + `<label class="btn btn--sm">${esc(s.busy.sjr ? t('journals.sjr.uploading') : t('journals.sjr.upload'))}`
      + `<input type="file" accept=".csv,text/csv" data-jp-field="sjrFile" hidden></label>`
      + `${messageHtml(s.sjrMessage)}</div>`;
  }

  const SERVICE_NAME = { openalex: 'OpenAlex', crossref: 'Crossref', pubmed: 'PubMed' };
  const FIT_COMPONENTS = ['similar_works', 'cited_in_paper', 'topic_overlap'];
  const money = (v) => String(Math.round(v * 10000) / 10000);

  // query.scoring: the formula the CLI ranked with, the application gate, and
  // the components no journal had a signal for (they left the formula).
  function scoringHtml(scoring) {
    const info = obj(scoring);
    if (typeof info.formula !== 'string' || !info.formula) return '';
    const lines = [esc(t('journals.scoring', { formula: info.formula }))];
    const gate = obj(info.facet_gate);
    if (typeof gate.applies === 'boolean') {
      lines.push(esc(gate.applies ? t('journals.scoring.gate', { factor: plain(gate.factor) })
        : t('journals.scoring.gateOff')));
    }
    const active = list(info.active);
    if (active.length && active.length < FIT_COMPONENTS.length) {
      const dropped = FIT_COMPONENTS.filter((name) => active.indexOf(name) < 0);
      if (dropped.length) lines.push(esc(t('journals.scoring.dropped', { names: dropped.join(', ') })));
    }
    return `<div class="panel__meta journals-scoring">${lines.map((line) => `<div>${line}</div>`).join('')}</div>`;
  }

  // api_calls: calls made and served from the cache (per service), whether the
  // cache was on, and the OpenAlex budget state; an exhausted budget is a warning.
  function apiCallsHtml(calls) {
    const info = obj(calls);
    if (!isNum(info.made) && !isNum(info.cached)) return '';
    const services = Object.keys(obj(info.by_service)).map((name) => {
      const slot = obj(obj(info.by_service)[name]);
      return `${esc(SERVICE_NAME[name] || name)} ${esc(plain(slot.made ?? 0))}/${esc(plain(slot.cached ?? 0))}`;
    });
    const line = [esc(t('journals.api', { made: info.made ?? 0, cached: info.cached ?? 0 })),
      ...(services.length ? [`<span title="${esc(t('journals.api.servicesTitle'))}">${services.join(' · ')}</span>`] : []),
      ...(obj(info.cache).enabled === false ? [esc(t('journals.api.cacheOff'))] : [])];
    const budget = obj(info.budget);
    let budgetHtml = '';
    if (budget.state === 'exhausted') {
      const retry = isNum(budget.retry_after_seconds) ? t('journals.api.retryIn', { seconds: budget.retry_after_seconds }) : '';
      budgetHtml = `<div class="journals-msg journals-msg--warn" role="status"><span class="badge badge--bad">429</span> `
        + `${esc(t('journals.api.exhausted', { retry }))}</div>`;
    } else if (budget.state === 'ok' || budget.state === 'unknown') {
      const text = budget.state === 'unknown' || !isNum(budget.remaining_usd) ? t('journals.api.budget.unknown')
        : (isNum(budget.limit_usd)
          ? t('journals.api.budget.left', { remaining: money(budget.remaining_usd), limit: money(budget.limit_usd) })
          : t('journals.api.budget.leftOnly', { remaining: money(budget.remaining_usd) }));
      budgetHtml = `<div class="panel__meta"><span class="badge ${budget.state === 'ok' ? 'badge--ok' : 'badge--absent'}">`
        + `${esc(t(`journals.api.state.${budget.state}`))}</span> ${esc(text)}</div>`;
    }
    return `<div class="panel__meta">${line.join(' · ')}</div>${budgetHtml}`;
  }

  function resultsHtml(s) {
    const data = s.journals || {};
    const doc = data.candidates;
    const error = data.candidates_error ? `<div class="journals-msg journals-msg--bad">${esc(data.candidates_error.message)}</div>` : '';
    if (!doc) {
      return `${error}<div class="agents-empty">${esc(t('journals.empty'))}</div>`;
    }
    const rows = sortedCandidates(doc, s.sort);
    const quartiles = list(doc.quartiles).join('–') || (typeof doc.quartiles === 'string' ? doc.quartiles : '');
    const summary = esc(t('journals.summary', {
      count: rows.length, quartiles, excluded: doc.excluded_count ?? 0,
      at: doc.generated_at || '',
    }));
    const titleLine = obj(doc.query).title ? `<div class="panel__meta">${esc(t('journals.paper', { title: doc.query.title }))}</div>` : '';
    const scoring = scoringHtml(obj(doc.query).scoring);
    const api = apiCallsHtml(doc.api_calls);
    const notes = list(doc.notes).map((n) => `<li>${esc(n)}</li>`).join('');
    const notesLink = data.notes_md
      ? ` · <a href="/api/artifact?path=paper/journal-candidates.md" target="_blank" rel="noopener noreferrer">${esc(t('journals.notesLink'))}</a>` : '';
    const body = rows.map((c) => `<tr>`
      + `<td>${journalCell(c)}</td><td>${quartileCell(c)}</td><td>${accessCell(c)}</td>`
      + `<td>${isNum(c.h_index) ? esc(c.h_index) : '—'}</td><td>${reviewCell(c.review_time)}</td>`
      + `<td>${fitCell(c)}</td><td>${evidenceCell(c)}</td>`
      + `<td><button type="button" class="btn btn--sm" data-jp-action="select" data-jp-id="${esc(c.openalex_id || c.id || '')}"`
      + `${s.busy.select ? ' disabled' : ''}>${esc(t('journals.select'))}</button></td></tr>`).join('');
    return `${error}<div class="panel__meta">${summary}${notesLink}</div>${titleLine}${scoring}${api}`
      + `<div class="agents-table-wrap"><table class="agents-table journals-table"><thead><tr>`
      + `<th>${esc(t('journals.col.journal'))}</th><th>${esc(t('journals.col.quartile'))}</th>`
      + `<th>${esc(t('journals.col.access'))}</th><th>${esc(t('journals.col.hindex'))}</th>`
      + `<th>${esc(t('journals.col.review'))}</th><th>${esc(t('journals.col.fit'))}</th>`
      + `<th>${esc(t('journals.col.evidence'))}</th><th></th></tr></thead>`
      + `<tbody>${body || `<tr><td colspan="8" class="agents-empty">${esc(t('journals.noRows'))}</td></tr>`}</tbody></table></div>`
      + `${notes ? `<details class="journals-notes"><summary>${esc(t('journals.notes'))}</summary><ul>${notes}</ul></details>` : ''}`;
  }

  // One side of a finding: key/value pairs, the quote and its source link.
  function sideHtml(side, venueSide) {
    const data = obj(side);
    const bits = Object.keys(data).filter((k) => k !== 'quote' && k !== 'url').map((k) => {
      const v = data[k];
      const shown = Array.isArray(v) ? v.join(', ') : (v && typeof v === 'object' ? JSON.stringify(v) : String(v ?? ''));
      return `<div><span class="panel__meta">${esc(k)}:</span> ${esc(shown.slice(0, 160))}</div>`;
    }).join('');
    const quote = venueSide && data.quote ? `<div class="journals-quote">“${esc(data.quote)}”</div>` : '';
    const source = venueSide && data.url ? `<div>${link(data.url, t('venue.audit.source'))}</div>` : '';
    return `${bits}${quote}${source}`;
  }

  function auditHtml(audit) {
    // No audit yet is not a clean audit: nothing has been measured.
    if (!audit || !Array.isArray(obj(audit).findings)) return `<div class="agents-empty">${esc(t('venue.audit.pending'))}</div>`;
    const findings = list(obj(audit).findings);
    if (!findings.length) return `<div class="agents-empty">${esc(t('venue.audit.clean'))}</div>`;
    const body = findings.map((f) => {
      const finding = obj(f);
      const severity = finding.severity;
      const badge = `<span class="badge ${esc(SEVERITY_BADGE[severity] || 'badge--info')}">`
        + `${esc(SEVERITY_LABEL[severity] ? SEVERITY_LABEL[severity]() : severity)}</span>`;
      const resolved = RESOLVED_LABEL[finding.resolved_by] ? RESOLVED_LABEL[finding.resolved_by]() : finding.resolved_by;
      const blocks = list(finding.blocks);
      return `<tr><td>${badge}</td><td><code>${esc(finding.id)}</code><div class="panel__meta">${esc(finding.message)}</div>`
        + `${blocks.length ? `<div class="panel__meta">${esc(blocks.join(', '))}</div>` : ''}</td>`
        + `<td>${sideHtml(finding.smith, false)}</td><td>${sideHtml(finding.venue, true)}</td>`
        + `<td>${esc(resolved ?? '')}</td></tr>`;
    }).join('');
    return `<div class="agents-table-wrap"><table class="agents-table"><thead><tr>`
      + `<th>${esc(t('venue.audit.severity'))}</th><th>${esc(t('venue.audit.finding'))}</th>`
      + `<th>${esc(t('venue.audit.smith'))}</th><th>${esc(t('venue.audit.venue'))}</th>`
      + `<th>${esc(t('venue.audit.resolvedBy'))}</th></tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function nextAction(status) {
    const info = obj(status);
    const done = {};
    list(info.steps).forEach((step) => { done[obj(step).step] = !!obj(step).done; });
    if (!done.requirements || !done.template || !done.audited) return 'analyze';
    if (info.audit_stale && !done.built) return 'analyze';
    if (info.blockers && !done.planned) return 'plan';
    if (info.blockers && !done.approved) return 'approve';
    if (!done.built) return 'build';
    if (info.audit_stale || info.build_stale) return 'rebuild';
    if (!done.compiled) return 'compile';
    return 'done';
  }

  function planHtml(s, detail) {
    const plan = detail.plan;
    const status = obj(detail.status);
    if (detail.plan_error) {
      return `<div class="journals-msg journals-msg--bad">${esc(detail.plan_error.message)}</div>`;
    }
    if (!plan && (!detail.audit || !Array.isArray(obj(detail.audit).findings))) {
      return `<div class="agents-empty">${esc(t('venue.plan.pending'))}</div>`;
    }
    if (!plan) {
      return `<div class="agents-empty">${esc(status.blockers ? t('venue.plan.none') : t('venue.plan.notRequired'))}</div>`;
    }
    const approval = obj(detail.approval);
    const valid = approval.valid === true;
    const approved = valid
      ? `<div class="journals-msg journals-msg--ok">${esc(t('venue.approved', {
        via: approval.via || '', at: approval.approved_at || '', statement: approval.statement || '' }))}</div>`
      : (detail.approval ? `<div class="journals-msg journals-msg--warn">${esc(t('venue.approval.stale'))}</div>` : '');
    const approve = valid ? '' : `<div class="journals-approve"><label>${esc(t('venue.approve.statement'))}`
      + `<textarea rows="2" data-jp-field="statement" placeholder="${esc(t('venue.approve.placeholder'))}">${esc(s.statement)}</textarea></label>`
      + `<button type="button" class="btn btn--primary btn--sm" data-jp-action="approve" data-jp-sha="${esc(plan.sha256)}"`
      + `${s.busy.approve ? ' disabled' : ''}>${esc(t('venue.approve'))}</button>`
      + `<div class="panel__meta">${esc(t('venue.approve.binding'))}</div></div>`;
    const changes = `<div class="journals-approve"><label>${esc(t('venue.changes.label'))}`
      + `<textarea rows="2" data-jp-field="note" placeholder="${esc(t('venue.changes.placeholder'))}">${esc(s.note)}</textarea></label>`
      + `<button type="button" class="btn btn--sm" data-jp-action="changes">${esc(t('venue.changes'))}</button></div>`;
    return `<div class="panel__meta">sha256 <code title="${esc(plan.sha256)}">${esc(String(plan.sha256).slice(0, 16))}</code></div>`
      + `<pre class="journals-plan">${esc(plan.text)}</pre>${approved}${approve}${changes}`;
  }

  function venueHtml(s) {
    const venues = list(s.venues);
    if (!venues.length) return `<div class="agents-empty">${esc(t('venue.none'))}</div>`;
    const picker = venues.length > 1
      ? `<label>${esc(t('venue.pick'))}<select data-jp-field="venueSlug">${venues.map((v) =>
        `<option value="${esc(v.slug)}"${v.slug === s.slug ? ' selected' : ''}>${esc(v.journal || v.slug)}</option>`).join('')}</select></label>`
      : '';
    const detail = s.detail;
    if (!detail || !detail.status) {
      return `${picker}<div class="agents-empty">${esc(detail && detail.message ? detail.message : t('journals.loading'))}</div>`;
    }
    const status = obj(detail.status);
    const venue = obj(detail.venue);
    const journal = obj(venue.journal);
    const slug = detail.slug || s.slug;
    const steps = list(status.steps).map((step) => {
      const info = obj(step);
      const label = STEP_LABEL[info.step] ? STEP_LABEL[info.step]() : info.step;
      return `<span class="badge ${info.done ? 'badge--ok' : 'badge--absent'}">${esc(label)}</span>`;
    }).join(' ');
    const next = nextAction(status);
    const stale = [];
    if (status.audit_stale) stale.push(t('venue.stale.audit'));
    if (status.build_stale) stale.push(t('venue.stale.build'));
    const requirements = obj(detail.requirements);
    const guidelines = list(requirements.guidelines_urls).filter(httpUrl).map((u) => link(u)).join(' · ');
    const template = obj(detail.template);
    const templateLine = template.kind
      ? `<div class="panel__meta">${esc(t('venue.template', { kind: template.kind, name: template.class || template.name || '' }))}</div>` : '';
    const approvalValid = obj(detail.approval).valid === true;
    const done = {};
    list(status.steps).forEach((step) => { done[obj(step).step] = !!obj(step).done; });
    // The venue file can be built once it is audited and no blocker is left
    // without an approved plan (the CLI enforces the same rule).
    const canBuild = !!done.audited && (!status.blockers || !!done.approved);
    const pdfButtons = ['canonical', 'venue'].map((view) => {
      const disabled = view === 'venue' && !detail.pdf;
      const active = s.pdfView === view;
      return `<button type="button" class="btn btn--sm${active ? ' btn--primary' : ''}" data-jp-action="pdf" data-jp-view="${view}"`
        + `${disabled ? ' disabled' : ''}>${esc(view === 'venue' ? t('venue.pdf.venue') : t('venue.pdf.canonical'))}</button>`;
    }).join('');
    const quartile = venue.quartile
      ? ` <span class="badge ${esc(QUARTILE_BADGE[venue.quartile] || 'badge--info')}">${esc(venue.quartile)}</span>` : '';
    return `${picker}<div class="journals-venue-head"><strong>${esc(journal.name || slug)}</strong>${quartile} `
      + `<code>${esc(slug)}</code>${journal.homepage_url ? ` ${link(journal.homepage_url, '↗')}` : ''}</div>`
      + `<div class="journals-steps">${steps}</div>`
      + `<div class="journals-next"><strong>${esc(t('venue.next'))}</strong> ${esc(NEXT_LABEL[next]())}</div>`
      + `${stale.map((text) => `<div class="journals-msg journals-msg--warn">${esc(text)}</div>`).join('')}`
      + `${guidelines ? `<div class="panel__meta">${esc(t('venue.guidelines'))}: ${guidelines}</div>` : ''}${templateLine}`
      + `<div class="journals-actions">`
      + `<button type="button" class="btn btn--sm${next === 'analyze' ? ' btn--primary' : ''}" data-jp-action="venue-analyze">${esc(t('venue.analyze'))}</button>`
      + `<button type="button" class="btn btn--sm" data-jp-action="venue-apply" data-jp-sha="${esc(obj(detail.plan).sha256 || '')}"`
      + `${approvalValid && detail.plan ? '' : ' disabled'}>${esc(t('venue.apply'))}</button>`
      + `<button type="button" class="btn btn--sm${next === 'build' || next === 'rebuild' || next === 'compile' ? ' btn--primary' : ''}" data-jp-action="build"`
      + `${canBuild && !s.busy.build ? '' : ' disabled'}>${esc(s.busy.build ? t('venue.building') : t('venue.build'))}</button>`
      + `<span class="btn-group">${pdfButtons}</span></div>`
      + `<h5>${esc(t('venue.audit.title'))}</h5>${auditHtml(detail.audit)}`
      + `<h5>${esc(t('venue.plan.title'))}</h5>${planHtml(s, detail)}`;
  }

  function panelHtml(s) {
    return `${messageHtml(s.message)}<p class="panel__meta">${esc(t('journals.meta'))}</p>`
      + `${formHtml(s)}${sjrHtml(s)}<div class="journals-results">${resultsHtml(s)}</div>`
      + `<section class="journals-venue"><h4>${esc(t('venue.title'))}</h4>${venueHtml(s)}</section>`;
  }

  // ------------------------------------------------------------------- actions

  async function api(path, method, body, raw) {
    try {
      const init = { method: method || 'GET', cache: 'no-store' };
      if (raw !== undefined) {
        init.body = raw;
      } else if (body !== undefined) {
        init.headers = { 'Content-Type': 'application/json' };
        init.body = JSON.stringify(body);
      }
      const response = await fetch(path, init);
      let data = null;
      try { data = await response.json(); } catch (_) { data = null; }
      return { status: response.status, ok: response.ok, body: data || {} };
    } catch (err) {
      return { status: 0, ok: false, body: { error: 'NETWORK', message: String((err && err.message) || err) } };
    }
  }

  const failure = (res) => {
    const body = obj(res.body);
    return `${body.code || body.error || res.status}: ${body.detail || body.message || ''}`.replace(/:\s*$/, '');
  };

  function host() {
    return typeof document !== 'undefined' && document.getElementById ? document.getElementById('journalsPanel') : null;
  }

  function render() {
    const el = host();
    if (el) el.innerHTML = panelHtml(state);
  }

  async function loadJournals() {
    const res = await api('/api/journals');
    if (res.ok) state.journals = res.body;
  }

  async function loadVenues() {
    const res = await api('/api/venues');
    state.venues = res.ok ? list(res.body.venues) : [];
    if (!state.venues.some((v) => v.slug === state.slug)) state.slug = state.venues.length ? state.venues[state.venues.length - 1].slug : null;
  }

  async function loadDetail() {
    if (!state.slug) { state.detail = null; return; }
    const res = await api(`/api/venues/${encodeURIComponent(state.slug)}`);
    state.detail = res.ok ? res.body : { message: failure(res) };
    if (res.ok && !state.detail.pdf && state.pdfView === 'venue') setPdf('canonical');
  }

  function setPdf(view) {
    state.pdfView = view === 'venue' && state.slug ? 'venue' : 'canonical';
    if (typeof window.setPdfVenue === 'function') window.setPdfVenue(state.pdfView === 'venue' ? state.slug : null);
  }

  async function refresh() {
    await Promise.all([loadJournals(), loadVenues()]);
    await loadDetail();
    render();
  }

  async function send(text) {
    if (typeof window.sendToCli !== 'function') {
      state.message = { kind: 'bad', text: t('journals.noConsole') };
      render();
      return false;
    }
    return window.sendToCli(text, true, { kind: 'slash' });
  }

  async function doSearch() {
    if (!rangeValid(state.form) || state.busy.search) return;
    state.busy.search = true;
    state.message = null;
    render();
    const res = await api('/api/journals/search', 'POST', searchBody(state.form));
    state.busy.search = false;
    if (res.ok && res.body.ok !== false) {
      await loadJournals();
      state.message = { kind: 'ok', text: t('journals.searchDone', { count: list(res.body.candidates).length }) };
    } else {
      state.message = { kind: 'bad', text: t('journals.searchFailed', { error: failure(res) }) };
    }
    render();
  }

  async function doUpload(file) {
    if (!file || state.busy.sjr) return;
    state.busy.sjr = true;
    state.sjrMessage = null;
    render();
    const year = wholeOrNull(state.sjrYear, 1999, 9999);
    const query = `name=${encodeURIComponent(file.name)}${year ? `&year=${year}` : ''}`;
    const res = await api(`/api/journals/sjr?${query}`, 'POST', undefined, file);
    state.busy.sjr = false;
    if (res.ok && res.body.ok !== false) {
      state.sjrMessage = { kind: 'ok', text: t('journals.sjr.imported', { rows: res.body.rows ?? '?', year: res.body.year ?? '?' }) };
      await loadJournals();
    } else {
      state.sjrMessage = { kind: 'bad', text: t('journals.sjr.failed', { error: failure(res) }) };
    }
    render();
  }

  async function doSelect(id) {
    if (!id || state.busy.select) return;
    state.busy.select = true;
    state.message = null;
    render();
    const res = await api('/api/venues/select', 'POST', { candidate: id });
    state.busy.select = false;
    if (res.ok) {
      state.slug = res.body.slug;
      state.message = { kind: 'ok', text: t('venue.selected', { journal: res.body.journal || res.body.slug }) };
      await loadVenues();
      state.slug = res.body.slug;
      await loadDetail();
    } else if (res.body.code === 'VENUE_EXISTS') {
      await loadVenues();
      state.message = { kind: 'warn', text: t('venue.exists') };
    } else {
      state.message = { kind: 'bad', text: t('venue.selectFailed', { error: failure(res) }) };
    }
    render();
    // The chosen journal's card sits below the results table: bring it into view.
    const card = res.ok && host() && host().querySelector ? host().querySelector('.journals-venue') : null;
    if (card && card.scrollIntoView) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function doApprove(sha) {
    const statement = String(state.statement || '').trim();
    if (!statement) {
      state.message = { kind: 'warn', text: t('venue.approve.empty') };
      render();
      return;
    }
    state.busy.approve = true;
    render();
    const res = await api(`/api/venues/${encodeURIComponent(state.slug)}/approve`, 'POST',
      { statement, plan_sha256: sha });
    state.busy.approve = false;
    if (res.ok) {
      state.statement = '';
      state.message = { kind: 'ok', text: t('venue.approve.done') };
      await loadVenues();
      await loadDetail();
    } else {
      state.message = { kind: 'bad', text: t('venue.approve.failed', { error: failure(res) }) };
    }
    render();
  }

  async function doBuild() {
    if (!state.slug || state.busy.build) return;
    const slug = state.slug;
    state.busy.build = true;
    state.message = null;
    render();
    let res = await api(`/api/venues/${encodeURIComponent(slug)}/build`, 'POST', {});
    if (res.ok) {
      res = await api(`/api/paper/compile?venue=${encodeURIComponent(slug)}`, 'POST', {});
      state.message = res.ok
        ? { kind: 'ok', text: t('venue.compiled', { message: obj(res.body).message || '' }) }
        : { kind: 'bad', text: t('venue.compileFailed', { error: failure(res) }) };
    } else {
      state.message = { kind: 'bad', text: t('venue.buildFailed', { error: failure(res) }) };
    }
    state.busy.build = false;
    await loadVenues();
    await loadDetail();
    if (res.ok && state.detail && state.detail.pdf) setPdf('venue');
    render();
  }

  async function onAction(el) {
    const action = el.getAttribute('data-jp-action');
    const detail = state.detail || {};
    const journal = obj(obj(detail.venue).journal).name || state.slug;
    if (action === 'search') return doSearch();
    if (action === 'analyze') {
      if (!rangeValid(state.form)) return undefined;
      return send(agentCommand(state.form));
    }
    if (action === 'select') return doSelect(el.getAttribute('data-jp-id'));
    if (action === 'venue-analyze') return send(instructions.analyze(state.slug, journal));
    if (action === 'venue-apply') return send(instructions.apply(state.slug, el.getAttribute('data-jp-sha')));
    if (action === 'changes') {
      if (!String(state.note || '').trim()) {
        state.message = { kind: 'warn', text: t('venue.changes.empty') };
        render();
        return undefined;
      }
      const sent = await send(instructions.changes(state.slug, state.note));
      if (sent) { state.note = ''; state.message = { kind: 'ok', text: t('venue.changes.sent') }; render(); }
      return sent;
    }
    if (action === 'approve') return doApprove(el.getAttribute('data-jp-sha'));
    if (action === 'build') return doBuild();
    if (action === 'pdf') {
      setPdf(el.getAttribute('data-jp-view'));
      render();
    }
    return undefined;
  }

  function onField(el) {
    const field = el.getAttribute('data-jp-field');
    if (field === 'from' || field === 'to' || field === 'maxApc' || field === 'maxReview' || field === 'limit') {
      state.form[field] = el.value;
      if (field === 'from' || field === 'to') render();
    } else if (field === 'oaOnly') {
      state.form.oaOnly = !!el.checked;
    } else if (field === 'noCache') {
      state.form.noCache = !!el.checked;
    } else if (field === 'sort') {
      state.sort = el.value;
      render();
    } else if (field === 'statement') {
      state.statement = el.value;
    } else if (field === 'note') {
      state.note = el.value;
    } else if (field === 'sjrYear') {
      state.sjrYear = el.value;
    } else if (field === 'venueSlug') {
      state.slug = el.value;
      setPdf('canonical');
      loadDetail().then(render);
    } else if (field === 'sjrFile') {
      doUpload(el.files && el.files[0]);
    }
  }

  function bind(el) {
    if (!el || el.__journalsBound || typeof el.addEventListener !== 'function') return;
    el.__journalsBound = true;
    el.addEventListener('click', (event) => {
      const target = event.target && event.target.closest ? event.target.closest('[data-jp-action]') : null;
      if (target && !target.disabled) onAction(target);
    });
    el.addEventListener('change', (event) => {
      const target = event.target && event.target.closest ? event.target.closest('[data-jp-field]') : null;
      if (target) onField(target);
    });
    el.addEventListener('input', (event) => {
      const target = event.target && event.target.closest ? event.target.closest('[data-jp-field]') : null;
      if (target && ['statement', 'note', 'maxApc', 'maxReview', 'limit', 'sjrYear'].indexOf(target.getAttribute('data-jp-field')) >= 0) onField(target);
    });
  }

  // Wire the events and draw the panel from what it already holds.
  function mount() {
    const el = host();
    if (!el) return;
    bind(el);
    render();
  }

  async function refreshJournalsPanel() {
    if (!host()) return;
    mount();
    await refresh();
  }

  window.JournalsPanel = {
    state, mount, agentCommand, searchBody, instructions, nextAction, rangeValid,
    formHtml, sjrHtml, resultsHtml, auditHtml, planHtml, venueHtml, panelHtml,
  };
  window.refreshJournalsPanel = refreshJournalsPanel;
  // The labels come from the catalogue: draw again in the new language.
  if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
    document.addEventListener('languagechange', () => { if (host()) render(); });
  }
})();
