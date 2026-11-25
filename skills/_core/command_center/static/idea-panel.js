/* Idea pane: the optional guided phase before /plausibility (idea-shaping S6).
 *
 * GET /api/idea answers the brief (.papersmith/idea_brief.json), the bank
 * choices (banco-lia and the workspace's other MCP servers) and whether the
 * draft is approved, with its `/plausibility <draft>` hand-off line. A stepper
 * walks the six steps; each one posts to its route (/api/idea/bank, profile,
 * experience, interests, topics, choose, draft, approve), which records the
 * step and answers the whole state again, so a reload resumes where the
 * operator left off:
 *   1 Sources    — banco-lia, another bank MCP server, or none;
 *   2 Profile    — ORCID, OpenAlex author, a Google Scholar link (only to find
 *                  the author) or a name, looked up in OpenAlex;
 *   3 Experience — level, methods and resources (chips), time;
 *   4 Interests  — 3 to 5 keyword chips, domain, an admired paper; with a
 *                  bank that can be queried, the bank's related items (the
 *                  thematic help: /api/plausibility/suggest for banco-lia);
 *   5 Topics     — candidate topics with their evidence, each item labelled
 *                  by its source; pick one or several to combine;
 *   6 Draft      — compose, edit with the prompt gate's live score, approve,
 *                  then "Launch plausibility" types `/plausibility <draft>`
 *                  with the gate's approval marker into the agent.
 * "Talk to the guide" types /idea-shaping into the agent without running it.
 * Every value is escaped before insertion.
 *
 * Public surface (window): refreshIdeaPanel(), IdeaPanel.{html, render, act, logic}.
 */
(function () {
  'use strict';

  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const list = (v) => (Array.isArray(v) ? v : []);
  const clean = (v) => String(v ?? '').replace(/\s+/g, ' ').trim();

  const GATE_MARKER = '[prompt-gate: approved]';
  const MANAGED = 'banco-lia';
  const KW_MIN = 3;
  const KW_MAX = 5;
  const CHIP_CHARS = 120;

  // Literal catalogue keys (never a composed key).
  const STEP_KEYS = [
    ['idea.step.sources', 'idea.step.sourcesHint'],
    ['idea.step.profile', 'idea.step.profileHint'],
    ['idea.step.experience', 'idea.step.experienceHint'],
    ['idea.step.interests', 'idea.step.interestsHint'],
    ['idea.step.topics', 'idea.step.topicsHint'],
    ['idea.step.draft', 'idea.step.draftHint'],
  ];
  const LEVEL_KEYS = {
    student: 'idea.level.student', 'early-career': 'idea.level.earlyCareer',
    experienced: 'idea.level.experienced', senior: 'idea.level.senior',
  };
  const CHIP_FIELDS = { methods: 'ideaMethods', resources: 'ideaResources', keywords: 'ideaKeywords' };
  // The text fields kept across renders until saved.
  const FIELDS = ['ideaProfileText', 'ideaLevel', 'ideaTime', 'ideaDomain', 'ideaAdmired', 'ideaNote',
    'ideaDraft', 'ideaOtherServer', 'ideaServerName', 'ideaServerSpec',
    'ideaMethodsInput', 'ideaResourcesInput', 'ideaKeywordsInput'];

  // ---- pure logic (tests/command-center-idea-panel.test.mjs) ----------------
  // Entries of `text` (comma or semicolon separated) added to `chips`, trimmed,
  // without case-insensitive duplicates, at most `max` in all.
  function addChips(chips, text, max) {
    const out = list(chips).slice();
    const seen = new Set(out.map((c) => String(c).toLowerCase()));
    for (const part of String(text ?? '').split(/[,;]/)) {
      const word = clean(part).slice(0, CHIP_CHARS);
      if (!word || seen.has(word.toLowerCase())) continue;
      if (max && out.length >= max) break;
      seen.add(word.toLowerCase());
      out.push(word);
    }
    return out;
  }

  // Whether step n (1..6) holds an answer in the brief.
  function stepDone(brief, n) {
    const b = brief || {};
    // An unreachable bank keeps the step open, so a reload shows its reason and Retry.
    if (n === 1) return Boolean(b.bank && b.bank.choice && b.bank.available !== false);
    if (n === 2) return Boolean(b.profile && b.profile.source);
    if (n === 3) return Boolean(b.experience && (b.experience.level || list(b.experience.methods).length));
    if (n === 4) return list(b.interests && b.interests.keywords).length > 0;
    if (n === 5) return list(b.chosen && b.chosen.topic_ids).length > 0;
    if (n === 6) return Boolean(b.draft && b.draft.approved);
    return false;
  }

  // The step a reload opens: the first one without an answer (the draft when all are answered).
  // The profile is optional: once a later step is answered, a skipped profile is not reopened.
  function firstOpenStep(brief) {
    const later = [3, 4, 5, 6].some((n) => stepDone(brief, n));
    for (let n = 1; n <= 6; n += 1) {
      if (n === 2 && later) continue;
      if (!stepDone(brief, n)) return n;
    }
    return 6;
  }

  // An evidence item's source as a person reads it.
  function evidenceLabel(source) {
    const s = String(source || '');
    if (s.startsWith('bank:')) return t('idea.source.bank', { server: s.slice('bank:'.length) });
    if (s === 'openalex') return t('idea.source.openalex');
    if (s === 'profile') return t('idea.source.profile');
    if (s === 'operator') return t('idea.source.operator');
    if (s === 'guide') return t('idea.source.guide');
    return s;
  }

  // The bank state's chip: [badge class, text] or null before a choice.
  function bankChip(bank) {
    const b = bank || {};
    if (!b.choice) return null;
    if (b.choice === 'none') return ['badge--info', t('idea.bank.chipNone')];
    if (b.available === false) return ['badge--bad', t('idea.bank.chipUnreachable', { reason: b.reason || '' })];
    if (b.choice === 'banco-lia') return ['badge--ok', t('idea.bank.chipAvailable')];
    if (b.compatible) return ['badge--ok', t('idea.bank.chipCompatible', { server: b.server || '' })];
    return ['badge--warn', t('idea.bank.chipGuideOnly', { server: b.server || '' })];
  }

  // Which bank the thematic help queries: 'banco-lia', 'other' or null.
  function suggestKind(bank) {
    const b = bank || {};
    if (b.choice === 'banco-lia' && b.available !== false) return 'banco-lia';
    if (b.choice === 'other' && b.compatible && b.available !== false) return 'other';
    return null;
  }

  // "Launch plausibility" sends the approved draft only while the editor still holds it.
  function canLaunch(view, editorText) {
    const draft = view && view.brief && view.brief.draft;
    if (!view || !view.ready || !view.handoff || !draft || !draft.approved) return false;
    return editorText === undefined || clean(editorText) === clean(draft.text);
  }

  // The line typed into the agent: the hand-off with the prompt gate's approval marker.
  const launchLine = (handoff) => `${clean(handoff)} ${GATE_MARKER}`;

  // ---- state ----------------------------------------------------------------
  let lastView = null;
  let step = null;          // the open step (1..6); null until the first view
  let notice = '';          // the last action's outcome, already translated
  let noticeBad = false;
  let busy = '';            // the action in flight
  let bankPick = null;      // the radio card the operator selected
  let picks = null;         // the topic ids ticked (a Set)
  let chips = null;         // {methods, resources, keywords} while editing
  let suggestion = null;    // the bank's answer to the keywords
  let gate = null;          // the live prompt-gate result of the editor's text
  let checkTimer = null;
  let checkTicket = 0;
  const drafts = {};        // typed text kept across renders

  const host = () => document.getElementById('ideaPanel');
  const val = (id, fallback) => (drafts[id] !== undefined ? drafts[id] : (fallback ?? ''));

  function capture() {
    const panel = host();
    const markup = panel ? String(panel.innerHTML || '') : '';
    for (const id of FIELDS) {
      if (!markup.includes(`id="${id}"`)) continue;
      const el = document.getElementById(id);
      if (el && typeof el.value === 'string') drafts[id] = el.value;
    }
  }

  function seed(view) {
    const b = (view && view.brief) || {};
    if (!chips) {
      chips = {
        methods: list(b.experience && b.experience.methods).slice(),
        resources: list(b.experience && b.experience.resources).slice(),
        keywords: list(b.interests && b.interests.keywords).slice(),
      };
    }
    if (!picks) picks = new Set(list(b.chosen && b.chosen.topic_ids));
    if (bankPick === null) bankPick = (b.bank && b.bank.choice) || null;
    if (step === null) step = firstOpenStep(b);
  }

  // ---- markup -----------------------------------------------------------------
  const button = (action, label, opts) => {
    const o = opts || {};
    return `<button type="button" class="btn btn--sm${o.primary ? ' btn--primary' : ''}" data-idea-action="${esc(action)}"${o.arg !== undefined ? ` data-idea-arg="${esc(o.arg)}"` : ''}${o.disabled ? ' disabled aria-disabled="true"' : ''}${o.title ? ` title="${esc(o.title)}"` : ''}>${esc(label)}</button>`;
  };
  const badge = (cls, text) => `<span class="badge ${esc(cls)}">${esc(text)}</span>`;

  function chipEditor(field, label, hint, max) {
    const items = list(chips && chips[field]);
    const id = CHIP_FIELDS[field];
    const full = max && items.length >= max;
    return `<div class="idea-field">
        <label for="${id}Input">${esc(label)}</label>
        <div class="idea-chips" id="${id}">${items.map((c, i) => `<span class="idea-chip">${esc(c)}<button type="button" class="idea-chip__x" data-idea-action="chip-remove" data-idea-arg="${esc(field)}:${i}" aria-label="${esc(t('idea.chipRemove', { chip: c }))}">×</button></span>`).join('')}</div>
        <div class="idea-row">
          <input type="text" id="${id}Input" data-idea-chip="${esc(field)}" value="${esc(val(`${id}Input`))}" placeholder="${esc(hint)}" autocomplete="off"${full ? ' disabled' : ''}>
          ${button('chip-add', t('idea.chipAdd'), { arg: field, disabled: full })}
        </div>
      </div>`;
  }

  function stepper(b) {
    return `<ol class="idea-stepper" role="list">${STEP_KEYS.map(([key], i) => {
      const n = i + 1;
      const done = stepDone(b, n);
      return `<li><button type="button" class="idea-stepper__btn${n === step ? ' is-active' : ''}${done ? ' is-done' : ''}" data-idea-action="go" data-idea-arg="${n}"${n === step ? ' aria-current="step"' : ''}>
          <span class="idea-stepper__n">${done ? '✓' : n}</span> ${esc(t(key))}</button></li>`;
    }).join('')}</ol>`;
  }

  function stepSources(view) {
    const b = view.brief.bank || {};
    const others = list(view.choices && view.choices.others);
    const chip = bankChip(b);
    const pick = bankPick || b.choice || '';
    const card = (value, title, body, extra) => `<label class="idea-radio${pick === value ? ' is-picked' : ''}">
        <input type="radio" name="ideaBank" value="${esc(value)}" data-idea-bank="${esc(value)}"${pick === value ? ' checked' : ''}>
        <span class="idea-radio__body"><strong>${esc(title)}</strong><span class="idea-muted">${esc(body)}</span>${extra || ''}</span>
      </label>`;
    const status = (value) => (chip && b.choice === value
      ? `<span class="idea-status">${badge(chip[0], chip[1])}${b.available === false ? button('bank-retry', t('idea.bank.retry')) : ''}</span>` : '');
    const options = others.map((o) => `<option value="${esc(o.server)}"${(val('ideaOtherServer', b.server) === o.server) ? ' selected' : ''}>${esc(o.server)} (${esc(o.transport === 'http' ? o.url : [o.command, ...list(o.args)].join(' '))})</option>`).join('');
    const otherBody = `${others.length
      ? `<span class="idea-row"><select id="ideaOtherServer" aria-label="${esc(t('idea.bank.otherSelect'))}">${options}</select></span>`
      : `<span class="idea-muted">${esc(t('idea.bank.noOthers'))}</span>`}
      <span class="idea-add">
        <input type="text" id="ideaServerName" value="${esc(val('ideaServerName'))}" placeholder="${esc(t('idea.bank.addName'))}" aria-label="${esc(t('idea.bank.addName'))}">
        <input type="text" id="ideaServerSpec" value="${esc(val('ideaServerSpec'))}" placeholder="${esc(t('idea.bank.addSpec'))}" aria-label="${esc(t('idea.bank.addSpec'))}">
        ${button('bank-add', t('idea.bank.add'))}
      </span>
      <span class="idea-muted">${esc(t('idea.bank.otherNote'))}</span>`;
    return `<div class="idea-radios" role="radiogroup" aria-label="${esc(t('idea.step.sources'))}">
        ${card('banco-lia', t('idea.bank.managedTitle'), t('idea.bank.managedBody'), status('banco-lia'))}
        ${card('other', t('idea.bank.otherTitle'), t('idea.bank.otherBody'), otherBody + status('other'))}
        ${card('none', t('idea.bank.noneTitle'), t('idea.bank.noneBody'), status('none'))}
      </div>
      <div class="idea-actions">${button('bank-choose', t('idea.bank.choose'), { primary: true, disabled: !pick })}</div>`;
  }

  function stepProfile(view) {
    const p = view.brief.profile || {};
    const typed = [p.orcid, p.openalex_author && !p.display_name ? p.openalex_author : '', p.scholar_url].find(Boolean) || '';
    let result = '';
    if (p.source === 'openalex') {
      const topics = list(p.topics).map((x) => `<span class="idea-chip idea-chip--static">${esc(x.name)} · ${esc(x.count)}</span>`).join('');
      result = `<div class="idea-card">
          <strong>${esc(p.display_name || p.openalex_author || '')}</strong>
          <span class="idea-muted">${esc(t('idea.profile.works', { n: p.works_count ?? '—' }))}${p.orcid ? ` · ORCID ${esc(p.orcid)}` : ''}${p.openalex_author ? ` · OpenAlex ${esc(p.openalex_author)}` : ''}</span>
          ${topics ? `<div class="idea-chips">${topics}</div>` : `<span class="idea-muted">${esc(t('idea.profile.noTopics'))}</span>`}
        </div>`;
    } else if (p.source === 'none') {
      result = `<div class="idea-card idea-card--warn" role="alert">${esc(t('idea.profile.notFound', { reason: p.reason || '' }))}</div>`;
    }
    return `<div class="idea-field">
        <label for="ideaProfileText">${esc(t('idea.profile.label'))}</label>
        <div class="idea-row">
          <input type="text" id="ideaProfileText" value="${esc(val('ideaProfileText', typed))}" placeholder="${esc(t('idea.profile.placeholder'))}" autocomplete="off">
          ${button('profile-find', t('idea.profile.find'), { primary: true })}
        </div>
        <p class="idea-muted">${esc(t('idea.profile.scholarNote'))}</p>
      </div>
      ${result}
      <div class="idea-actions">${button('go', t('idea.skip'), { arg: 3 })}</div>`;
  }

  function stepExperience(view) {
    const e = view.brief.experience || {};
    const levels = list(view.levels).length ? view.levels : Object.keys(LEVEL_KEYS);
    const level = val('ideaLevel', e.level || '');
    return `<div class="idea-grid">
        <div class="idea-field">
          <label for="ideaLevel">${esc(t('idea.experience.level'))}</label>
          <select id="ideaLevel"><option value="">${esc(t('idea.experience.levelNone'))}</option>${levels.map((l) => `<option value="${esc(l)}"${level === l ? ' selected' : ''}>${esc(LEVEL_KEYS[l] ? t(LEVEL_KEYS[l]) : l)}</option>`).join('')}</select>
        </div>
        <div class="idea-field">
          <label for="ideaTime">${esc(t('idea.experience.time'))}</label>
          <input type="text" id="ideaTime" value="${esc(val('ideaTime', e.time || ''))}" placeholder="${esc(t('idea.experience.timePlaceholder'))}">
        </div>
      </div>
      ${chipEditor('methods', t('idea.experience.methods'), t('idea.experience.methodsPlaceholder'))}
      ${chipEditor('resources', t('idea.experience.resources'), t('idea.experience.resourcesPlaceholder'))}
      <div class="idea-actions">${button('experience-save', t('idea.saveNext'), { primary: true })}</div>`;
  }

  function suggestionHtml() {
    if (!suggestion) return '';
    if (suggestion.loading) return `<p class="idea-muted" role="status">${esc(t('idea.suggest.loading'))}</p>`;
    const data = suggestion.data || {};
    if (suggestion.error || data.available === false) {
      return `<div class="idea-card idea-card--warn" role="alert">${esc(t('idea.suggest.unavailable', { reason: suggestion.error || data.reason || '' }))}</div>`;
    }
    const items = list(data.items || data.hits).map((it) => `<li><strong>${esc(it.title)}</strong>
        <span class="idea-muted">${esc(it.id || '')}${it.year ? ` · ${esc(it.year)}` : ''}${it.kind ? ` · ${esc(it.kind)}` : ''}</span></li>`).join('');
    const topics = list(data.topics).map((x) => `<span class="idea-chip idea-chip--static">${esc(x.name || x.id)}${x.count ? ` · ${esc(x.count)}` : ''}</span>`).join('');
    const draftText = clean(data.draft);
    return `<div class="idea-card">
        ${items ? `<ul class="idea-items">${items}</ul>` : `<span class="idea-muted">${esc(t('idea.suggest.noItems'))}</span>`}
        ${topics ? `<div class="idea-chips">${topics}</div>` : ''}
        <span class="idea-muted">${esc(t('idea.suggest.background'))}</span>
        ${draftText ? `<p class="idea-quote">${esc(draftText)}</p>${button('suggest-use', t('idea.suggest.useDraft'))}` : ''}
      </div>`;
  }

  function stepInterests(view) {
    const i = view.brief.interests || {};
    const kind = suggestKind(view.brief.bank);
    const count = list(chips && chips.keywords).length;
    const help = kind ? `<div class="idea-help">
        <strong>${esc(t('idea.suggest.title'))}</strong>
        <span class="idea-muted">${esc(kind === 'banco-lia' ? t('idea.suggest.introManaged') : t('idea.suggest.introOther', { server: view.brief.bank.server || '' }))}</span>
        <div class="idea-actions">${button('suggest', t('idea.suggest.ask'), { disabled: count < KW_MIN || count > KW_MAX })}</div>
        ${suggestionHtml()}
      </div>` : '';
    return `${chipEditor('keywords', t('idea.interests.keywords'), t('idea.interests.keywordsPlaceholder'), KW_MAX)}
      <p class="idea-muted">${esc(t('idea.interests.count', { n: count, min: KW_MIN, max: KW_MAX }))}</p>
      <div class="idea-grid">
        <div class="idea-field">
          <label for="ideaDomain">${esc(t('idea.interests.domain'))}</label>
          <input type="text" id="ideaDomain" value="${esc(val('ideaDomain', i.domain || ''))}" placeholder="${esc(t('idea.interests.domainPlaceholder'))}">
        </div>
        <div class="idea-field">
          <label for="ideaAdmired">${esc(t('idea.interests.admired'))}</label>
          <input type="text" id="ideaAdmired" value="${esc(val('ideaAdmired', i.admired_paper || ''))}" placeholder="${esc(t('idea.interests.admiredPlaceholder'))}">
        </div>
      </div>
      <div class="idea-actions">${button('interests-save', t('idea.saveNext'), { primary: true })}</div>
      ${help}`;
  }

  function evidenceItem(e) {
    const url = /^https?:\/\//.test(String(e.url || '')) ? String(e.url) : '';
    const detail = esc(e.detail || '');
    return `<li><span class="badge badge--info idea-source">${esc(evidenceLabel(e.source))}</span>
        ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${detail}</a>` : detail}</li>`;
  }

  function stepTopics(view) {
    const topics = list(view.brief.topics);
    const note = view.brief.chosen && view.brief.chosen.note;
    const cards = topics.map((topic) => {
      const on = picks && picks.has(topic.id);
      return `<article class="idea-topic${on ? ' is-picked' : ''}" data-idea-topic-card="${esc(topic.id)}">
          <label class="idea-topic__head"><input type="checkbox" data-idea-topic="${esc(topic.id)}"${on ? ' checked' : ''}>
            <strong>${esc(topic.title)}</strong></label>
          <p class="idea-muted">${esc(topic.rationale || '')}</p>
          ${list(topic.keywords).length ? `<div class="idea-chips">${list(topic.keywords).map((k) => `<span class="idea-chip idea-chip--static">${esc(k)}</span>`).join('')}</div>` : ''}
          <ul class="idea-evidence">${list(topic.evidence).map(evidenceItem).join('')}</ul>
        </article>`;
    }).join('');
    return `<div class="idea-actions">${button('propose', topics.length ? t('idea.topics.again') : t('idea.topics.propose'), { primary: !topics.length })}</div>
      ${topics.length ? `<p class="idea-muted">${esc(t('idea.topics.pickHint'))}</p><div class="idea-topics">${cards}</div>
        <div class="idea-field">
          <label for="ideaNote">${esc(t('idea.topics.note'))}</label>
          <input type="text" id="ideaNote" value="${esc(val('ideaNote', note || ''))}" placeholder="${esc(t('idea.topics.notePlaceholder'))}">
        </div>
        <div class="idea-actions">${button('choose', t('idea.topics.choose'), { primary: true, disabled: !(picks && picks.size) })}</div>`
        : `<p class="idea-muted">${esc(t('idea.topics.empty'))}</p>`}`;
  }

  function gateHtml(g) {
    if (!g) return '';
    const missing = list(g.missing);
    return `<div class="idea-gate${g.ok ? ' is-ok' : ''}" role="status">
        ${badge(g.ok ? 'badge--ok' : 'badge--warn', g.ok ? t('idea.draft.gatePass', { score: g.score ?? '—' }) : t('idea.draft.gateFail', { score: g.score ?? '—' }))}
        ${missing.length ? `<ul>${missing.map((m) => `<li>${esc(m)}</li>`).join('')}</ul>` : ''}
      </div>`;
  }

  function stepDraft(view) {
    const d = view.brief.draft || {};
    const text = val('ideaDraft', d.text || '');
    const shownGate = gate || (d.text ? d.gate : null);
    const launchable = canLaunch(view, text);
    return `<div class="idea-actions">${button('compose', t('idea.draft.compose'), { primary: !d.text })}</div>
      <div class="idea-field">
        <label for="ideaDraft">${esc(t('idea.draft.label'))}</label>
        <textarea id="ideaDraft" rows="6" placeholder="${esc(t('idea.draft.placeholder'))}">${esc(text)}</textarea>
      </div>
      <div id="ideaGate">${gateHtml(shownGate)}</div>
      ${d.approved ? `<p class="idea-ok">${esc(t('idea.draft.approved', { at: d.approved_at || '' }))}</p>` : ''}
      <div class="idea-actions">
        ${button('approve', t('idea.draft.approve'), { primary: !d.approved, disabled: !clean(text) })}
        ${button('launch', t('idea.draft.launch'), { primary: launchable, disabled: !launchable, title: launchable ? '' : t('idea.draft.launchNeedsApproval') })}
      </div>`;
  }

  const STEPS = [stepSources, stepProfile, stepExperience, stepInterests, stepTopics, stepDraft];

  function html(view) {
    if (!view || view.ok === false || !view.brief) {
      const why = (view && (view.message || view.error)) || '';
      return `<div class="idea-card idea-card--warn" role="alert">${esc(t('idea.readFailed', { error: why }))}</div>`;
    }
    seed(view);
    const n = Math.min(6, Math.max(1, Number(step) || 1));
    const [title, hint] = STEP_KEYS[n - 1];
    const note = busy ? `<p class="idea-notice" role="status">${esc(t('idea.working'))}</p>`
      : (notice ? `<p class="idea-notice${noticeBad ? ' is-bad' : ''}" role="${noticeBad ? 'alert' : 'status'}">${esc(notice)}</p>` : '');
    return `<div class="idea-head">
        <p class="idea-muted">${esc(t('idea.intro'))}</p>
        <div class="idea-actions">${button('guide', t('idea.guide'))}</div>
      </div>
      ${stepper(view.brief)}
      <section class="idea-step" data-idea-step="${n}">
        <h4>${esc(t('idea.stepOf', { n, total: 6 }))} · ${esc(t(title))}</h4>
        <p class="idea-muted">${esc(t(hint))}</p>
        ${note}
        ${STEPS[n - 1](view)}
        <div class="idea-nav">
          ${n > 1 ? button('go', t('idea.back'), { arg: n - 1 }) : '<span></span>'}
          ${n < 6 ? button('go', t('idea.next'), { arg: n + 1 }) : ''}
        </div>
      </section>`;
  }

  function render(view) {
    if (view !== undefined) lastView = view;
    const panel = host();
    if (!panel) return;
    capture();
    panel.innerHTML = html(lastView);
  }

  // ---- requests ---------------------------------------------------------------
  async function post(url, body) {
    try {
      const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}) });
      const data = await response.json().catch(() => ({}));
      return { ok: response.ok && data.ok !== false, data };
    } catch (err) {
      return { ok: false, data: { message: (err && err.message) || String(err) } };
    }
  }

  // Posts one step; on success the answer is the new state.
  async function stepPost(url, body, done) {
    busy = url;
    notice = '';
    render();
    const { ok, data } = await post(url, body);
    busy = '';
    if (ok && data.brief) {
      lastView = data;
      notice = done ? done(data) : '';
      noticeBad = false;
    } else {
      notice = t('idea.refused', { error: data.message || data.error || data.code || '' });
      noticeBad = true;
    }
    render();
    return ok ? data : null;
  }

  async function refreshIdeaPanel() {
    try {
      const response = await fetch('/api/idea', { cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
      render(data);
    } catch (err) {
      render({ ok: false, message: (err && err.message) || String(err) });
    }
  }

  function scheduleCheck() {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(checkNow, 400);
  }

  async function checkNow() {
    const text = clean(document.getElementById('ideaDraft')?.value);
    const ticket = (checkTicket += 1);
    if (!text) { gate = null; showGate(); return; }
    const { ok, data } = await post('/api/idea/draft', { action: 'check', text });
    if (ticket !== checkTicket) return;  // a newer check owns the box
    gate = ok && data.result ? data.result.gate : null;
    showGate();
  }

  // The live score replaces only its box and the launch button's state, so the caret stays put.
  function showGate() {
    const box = document.getElementById('ideaGate');
    if (box) box.innerHTML = gateHtml(gate);
  }

  function goStep(n) {
    step = Math.min(6, Math.max(1, Number(n) || 1));
    notice = '';
    render();
  }

  function chipAdd(field) {
    const id = `${CHIP_FIELDS[field]}Input`;
    const input = document.getElementById(id);
    const text = input ? input.value : drafts[id];
    chips[field] = addChips(chips[field], text, field === 'keywords' ? KW_MAX : 0);
    drafts[id] = '';
    if (input) input.value = '';
    render();
  }

  // ---- actions ------------------------------------------------------------------
  async function act(action, arg) {
    if (!lastView || !lastView.brief) {
      if (action !== 'guide') return;
    } else {
      seed(lastView);
      capture();
    }
    if (action === 'go') return goStep(arg);
    if (action === 'guide') {
      window.sendToCli?.('/idea-shaping', false, { kind: 'slash' });
      notice = t('idea.guideSent');
      noticeBad = false;
      return render();
    }
    if (action === 'bank-pick') { bankPick = arg; return render(); }
    if (action === 'chip-add') return chipAdd(arg);
    if (action === 'chip-remove') {
      const [field, index] = String(arg).split(':');
      chips[field] = list(chips[field]).filter((_, i) => i !== Number(index));
      return render();
    }
    if (action === 'topic-toggle') {
      if (picks.has(arg)) picks.delete(arg); else picks.add(arg);
      return render();
    }
    if (action === 'bank-choose' || action === 'bank-retry') {
      const brief = lastView.brief.bank || {};
      const choice = action === 'bank-retry' ? brief.choice : bankPick;
      if (!choice) return undefined;
      const server = choice === 'other'
        ? clean(action === 'bank-retry' ? brief.server : val('ideaOtherServer', brief.server)) : undefined;
      if (choice === 'other' && !server) {
        notice = t('idea.bank.pickServer');
        noticeBad = true;
        return render();
      }
      return stepPost('/api/idea/bank', { action: 'choose', choice, server }, (data) => {
        const b = data.brief.bank || {};
        if (b.available === false) return t('idea.bank.savedUnreachable');
        if (choice === 'none' || b.compatible || choice === 'banco-lia') step = 2;
        return t('idea.bank.saved');
      });
    }
    if (action === 'bank-add') {
      const name = clean(val('ideaServerName'));
      const spec = clean(val('ideaServerSpec'));
      const body = /^https?:\/\//.test(spec) ? { action: 'add', name, url: spec } : { action: 'add', name, command: spec };
      const data = await stepPost('/api/idea/bank', body, () => t('idea.bank.added', { server: name }));
      if (data) {
        bankPick = 'other';
        drafts.ideaServerName = '';
        drafts.ideaServerSpec = '';
        drafts.ideaOtherServer = name;
        render();
      }
      return undefined;
    }
    if (action === 'profile-find') {
      const text = clean(val('ideaProfileText'));
      if (!text) { notice = t('idea.profile.needText'); noticeBad = true; return render(); }
      return stepPost('/api/idea/profile', { text }, (data) => (data.brief.profile.source === 'openalex'
        ? t('idea.profile.found') : ''));
    }
    if (action === 'experience-save') {
      const pending = clean(val('ideaMethodsInput')) || clean(val('ideaResourcesInput'));
      if (pending) {
        chips.methods = addChips(chips.methods, val('ideaMethodsInput'), 0);
        chips.resources = addChips(chips.resources, val('ideaResourcesInput'), 0);
        drafts.ideaMethodsInput = '';
        drafts.ideaResourcesInput = '';
      }
      const data = await stepPost('/api/idea/experience', {
        level: val('ideaLevel') || null, methods: chips.methods, resources: chips.resources, time: clean(val('ideaTime')) || null,
      }, () => t('idea.saved'));
      if (data) goStep(4);
      return undefined;
    }
    if (action === 'interests-save' || action === 'suggest') {
      if (clean(val('ideaKeywordsInput'))) {
        chips.keywords = addChips(chips.keywords, val('ideaKeywordsInput'), KW_MAX);
        drafts.ideaKeywordsInput = '';
      }
      const data = await stepPost('/api/idea/interests', {
        keywords: chips.keywords, domain: clean(val('ideaDomain')) || null, admired_paper: clean(val('ideaAdmired')) || null,
      }, () => t('idea.saved'));
      if (!data) return undefined;
      if (action === 'interests-save') return goStep(5);
      return suggest(data);
    }
    if (action === 'suggest-use') {
      const text = clean(suggestion && suggestion.data && suggestion.data.draft);
      if (!text) return undefined;
      const data = await stepPost('/api/idea/draft', { action: 'text', text }, () => t('idea.suggest.used'));
      if (data) { delete drafts.ideaDraft; gate = null; goStep(6); }
      return undefined;
    }
    if (action === 'propose') {
      const data = await stepPost('/api/idea/topics', { n: 3 }, (d) => t('idea.topics.proposed', { n: list(d.brief.topics).length }));
      if (data) picks = new Set();
      render();
      return undefined;
    }
    if (action === 'choose') {
      const data = await stepPost('/api/idea/choose', { topic_ids: Array.from(picks), note: clean(val('ideaNote')) || null },
        () => t('idea.topics.chosen'));
      if (data) goStep(6);
      return undefined;
    }
    if (action === 'compose') {
      const data = await stepPost('/api/idea/draft', { action: 'compose' }, () => t('idea.draft.composed'));
      if (data) { delete drafts.ideaDraft; gate = null; render(); }
      return undefined;
    }
    if (action === 'approve') {
      const text = clean(val('ideaDraft'));
      if (!text) return undefined;
      if (text !== clean(lastView.brief.draft && lastView.brief.draft.text)) {
        const stored = await stepPost('/api/idea/draft', { action: 'text', text });
        if (!stored) return undefined;
      }
      const data = await stepPost('/api/idea/approve', {}, () => t('idea.draft.approvedNotice'));
      if (data) { delete drafts.ideaDraft; gate = null; render(); }
      return undefined;
    }
    if (action === 'launch') {
      if (!canLaunch(lastView, val('ideaDraft', lastView.brief.draft && lastView.brief.draft.text))) return undefined;
      const sent = await window.sendToCli?.(launchLine(lastView.handoff), true, { kind: 'slash' });
      notice = sent === false ? t('idea.draft.launchFailed') : t('idea.draft.launched');
      noticeBad = sent === false;
      return render();
    }
    return undefined;
  }

  async function suggest(view) {
    const kind = suggestKind(view.brief.bank);
    const words = list(view.brief.interests && view.brief.interests.keywords);
    if (!kind || words.length < KW_MIN || words.length > KW_MAX) return;
    suggestion = { loading: true };
    render();
    if (kind === 'banco-lia') {
      const lang = window.i18n && window.i18n.getLanguage ? window.i18n.getLanguage() : 'en';
      const { ok, data } = await post('/api/plausibility/suggest', { keywords: words, language: lang === 'es' ? 'es' : 'en' });
      suggestion = ok ? { data } : { error: data.error || data.message || data.code || '' };
    } else {
      const { ok, data } = await post('/api/idea/bank', { action: 'search', query: words.join(' ') });
      suggestion = ok ? { data: data.result || {} } : { error: data.message || data.error || '' };
    }
    render();
  }

  document.addEventListener('click', (event) => {
    const el = event.target && event.target.closest && event.target.closest('[data-idea-action]');
    if (!el || !el.dataset || !el.dataset.ideaAction || el.disabled) return;
    act(el.dataset.ideaAction, el.dataset.ideaArg);
  });
  document.addEventListener('change', (event) => {
    const target = event.target;
    if (!target || !target.dataset) return;
    if (target.dataset.ideaBank) act('bank-pick', target.dataset.ideaBank);
    else if (target.dataset.ideaTopic) act('topic-toggle', target.dataset.ideaTopic);
  });
  document.addEventListener('keydown', (event) => {
    const target = event.target;
    if (!target || !target.dataset || !target.dataset.ideaChip) return;
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault();
      act('chip-add', target.dataset.ideaChip);
    }
  });
  document.addEventListener('input', (event) => {
    if (event.target && event.target.id === 'ideaDraft') {
      drafts.ideaDraft = event.target.value;
      const launch = document.querySelector?.('[data-idea-action="launch"]');
      if (launch) launch.disabled = !canLaunch(lastView, event.target.value);
      scheduleCheck();
    }
  });
  document.addEventListener('languagechange', () => { if (lastView) render(); });

  window.IdeaPanel = {
    html, render, act,
    logic: { addChips, stepDone, firstOpenStep, evidenceLabel, bankChip, suggestKind, canLaunch, launchLine },
    reset() {  // a fresh panel state (tests)
      lastView = null; step = null; notice = ''; noticeBad = false; busy = ''; bankPick = null; picks = null;
      chips = null; suggestion = null; gate = null;
      Object.keys(drafts).forEach((k) => delete drafts[k]);
    },
  };
  window.refreshIdeaPanel = refreshIdeaPanel;
})();
