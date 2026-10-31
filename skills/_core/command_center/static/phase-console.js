/* Phase console: what a pipeline phase card lets the operator do.
 *
 * Each phase in GET /api/status carries `actions` (phase_actions.py):
 *   prompt   — a text box guided by the stage's rules; "Run" types
 *              `/<skill> <text>` into an agent of the support terminal;
 *   command  — a real `smith` command, run in the terminal's shell;
 *   redirect — opens the dashboard panel that owns the work.
 * A prompt flagged `keyword_help` (plausibility) also carries the thematic
 * help: 3 to 5 keywords go to POST /api/plausibility/suggest, which answers
 * Banco LIA items, topics and a proposed idea; "Approve and launch" copies the
 * (edited) idea into the card's prompt and runs the same path as "Run".
 * Every value is escaped before insertion; handlers read the action back
 * from the rendered phase, never from markup.
 *
 * Public surface (window): renderPhaseActions(phase), phaseSentenceCount(text).
 */
(function () {
  'use strict';

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  // Phase ids are the stable "Fase N"; this is how a person reads one.
  const phaseName = (id) => {
    const match = /^Fase (\d+)$/.exec(String(id || ''));
    return match ? t('phases.number', { n: match[1] }) : String(id || '');
  };
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);

  let current = [];
  let currentPhase = null;

  // How many sentences the text is worth: sentences end in . ! or ? before a
  // space or the end, and a long run-on idea counts one per WORDS_PER_SENTENCE
  // words, so a full paragraph written with commas is not refused.
  const WORDS_PER_SENTENCE = 12;
  function phaseSentenceCount(text) {
    const clean = String(text || '').trim();
    const parts = clean.split(/(?<=[.!?])\s+/).filter((p) => /\w/.test(p));
    const words = clean.split(/\s+/).filter((w) => /\w/.test(w)).length;
    return Math.max(parts.length, Math.floor(words / WORDS_PER_SENTENCE));
  }

  // ---- thematic help (keywords -> Banco LIA -> proposed idea) --------------
  const KW_MIN = 3;
  const KW_MAX = 5;
  const KW_CHARS = 40;
  const kwRequest = {};

  function kwBlock(i) {
    const inputs = Array.from({ length: KW_MAX }, (_, n) => `<input type="text" class="kw-help__input"
          id="kwInput${i}_${n}" data-kw-input="${i}" maxlength="${KW_CHARS}" autocomplete="off"
          aria-label="${esc(t('kwHelp.keyword', { n: n + 1 }))}"${n >= KW_MIN ? ' hidden' : ''}>`).join('');
    return `<details class="kw-help" id="kwHelp${i}">
        <summary>${esc(t('kwHelp.summary'))}</summary>
        <p class="kw-help__intro">${esc(t('kwHelp.intro'))}</p>
        <div class="kw-help__inputs">${inputs}
          <button type="button" class="btn btn--sm" id="kwAdd${i}" data-kw-help="add" data-kw-index="${i}"
            title="${esc(t('kwHelp.add'))}" aria-label="${esc(t('kwHelp.add'))}">+</button>
        </div>
        <div class="kw-help__bar">
          <button type="button" class="btn btn--sm btn--primary" id="kwPropose${i}" data-kw-help="propose"
            data-kw-index="${i}" disabled>${esc(t('kwHelp.propose'))}</button>
          <span class="kw-help__status" id="kwStatus${i}">${esc(t('kwHelp.needThree'))}</span>
        </div>
        <div class="kw-help__result" id="kwResult${i}" aria-live="polite" hidden></div>
      </details>`;
  }

  // The distinct, non-empty keywords typed so far (case-insensitive).
  function kwWords(i) {
    const seen = new Set();
    const words = [];
    for (let n = 0; n < KW_MAX; n += 1) {
      const word = String(document.getElementById(`kwInput${i}_${n}`)?.value ?? '').replace(/\s+/g, ' ').trim().slice(0, KW_CHARS);
      if (word && !seen.has(word.toLowerCase())) { seen.add(word.toLowerCase()); words.push(word); }
    }
    return words;
  }

  function kwState(i) {
    const count = kwWords(i).length;
    const button = document.getElementById(`kwPropose${i}`);
    const status = document.getElementById(`kwStatus${i}`);
    if (button) button.disabled = count < KW_MIN;
    if (status) status.textContent = count < KW_MIN ? t('kwHelp.needThree') : t('kwHelp.ready', { n: count });
  }

  function kwShow(i, html) {
    const box = document.getElementById(`kwResult${i}`);
    if (!box) return;
    box.innerHTML = html;
    box.hidden = !html;
  }

  const kwNote = (text) => `<p class="kw-help__note">${esc(text)}</p>`;

  function kwResultHtml(i, data) {
    if (!data.available) {
      return `<div class="kw-help__unavailable" role="alert">${esc(t('kwHelp.unavailable', { reason: data.reason || '' }))}
        <br><span>${esc(t('kwHelp.unavailableHint'))}</span></div>`;
    }
    const items = (data.items || []).map((it) => {
      const kind = it.kind === 'proyecto' ? t('kwHelp.kindProyecto') : t('kwHelp.kindArticulo');
      const doi = /^10\.\S+$/.test(String(it.doi || ''))
        ? ` · <a href="https://doi.org/${esc(it.doi)}" target="_blank" rel="noopener">DOI</a>` : '';
      return `<li><strong>${esc(it.title)}</strong>
          <span class="kw-help__meta">${esc(it.id)} · ${esc(kind)}${it.year ? ` · ${esc(it.year)}` : ''} · ${esc(t('kwHelp.score', { score: it.score }))}${doi}</span></li>`;
    }).join('');
    const topics = (data.topics || []).map((tp) => `<span class="kw-help__topic">${esc(tp.name)} (${esc(tp.count)})</span>`).join('');
    const match = data.match === 'all' ? t('kwHelp.matchAll') : t('kwHelp.matchAny');
    return `${(data.items || []).length
      ? `<h5>${esc(t('kwHelp.items'))}</h5>${kwNote(match)}<ul class="kw-help__items">${items}</ul>
         ${topics ? `<h5>${esc(t('kwHelp.topics'))}</h5><div class="kw-help__topics">${topics}</div>` : ''}
         ${kwNote(t('kwHelp.context'))}`
      : kwNote(t('kwHelp.noItems'))}
      <label class="kw-help__draftlabel" for="kwDraft${i}">${esc(t('kwHelp.draft'))}</label>
      <textarea class="phase-action__input kw-help__draft" id="kwDraft${i}" rows="6">${esc(data.draft)}</textarea>
      <div class="kw-help__actions">
        <button type="button" class="btn btn--sm btn--primary" data-kw-help="approve" data-kw-index="${i}">${esc(t('kwHelp.approve'))}</button>
        <button type="button" class="btn btn--sm" data-kw-help="discard" data-kw-index="${i}">${esc(t('kwHelp.discard'))}</button>
      </div>`;
  }

  async function kwPropose(i) {
    const words = kwWords(i);
    if (words.length < KW_MIN) return kwState(i);
    const ticket = (kwRequest[i] = (kwRequest[i] || 0) + 1);
    kwShow(i, kwNote(t('kwHelp.loading')));
    let html;
    try {
      const language = window.i18n && window.i18n.getLanguage ? window.i18n.getLanguage() : 'es';
      const response = await window.fetch('/api/plausibility/suggest', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keywords: words, language }),
      });
      const data = await response.json();
      html = response.ok
        ? kwResultHtml(i, data)
        : `<div class="kw-help__unavailable" role="alert">${esc(t('kwHelp.refused', { why: data.error || response.status }))}</div>`;
    } catch (err) {
      html = `<div class="kw-help__unavailable" role="alert">${esc(t('kwHelp.failed', { why: (err && err.message) || err }))}</div>`;
    }
    if (ticket === kwRequest[i]) kwShow(i, html);  // a newer request owns the box
  }

  // The operator's click is what launches: the (edited) idea becomes the
  // card's prompt and goes through runPrompt, so the agent selector, the
  // sentence check, the lock and the run tracking all apply.
  async function kwApprove(a, i) {
    const draft = document.getElementById(`kwDraft${i}`);
    const input = document.getElementById(`phaseInput${i}`);
    if (!draft || !input) return;
    input.value = draft.value;
    await runPrompt(a, i);
  }

  function kwAdd(i) {
    for (let n = KW_MIN; n < KW_MAX; n += 1) {
      const field = document.getElementById(`kwInput${i}_${n}`);
      if (field && field.hidden) {
        field.hidden = false;
        if (field.focus) field.focus();
        break;
      }
    }
    const last = document.getElementById(`kwInput${i}_${KW_MAX - 1}`);
    const button = document.getElementById(`kwAdd${i}`);
    if (button && last && !last.hidden) button.hidden = true;
  }

  function promptCard(a, i) {
    const guide = (a.guide || []).map((g) => `<li>${esc(g)}</li>`).join('');
    const need = a.min_sentences ? t('phaseConsole.minSentences', { n: a.min_sentences }) : (a.optional ? t('phaseConsole.optionalText') : '');
    return `<div class="phase-action phase-action--prompt">
        <div class="phase-action__head">
          <strong>${esc(a.label)}</strong>
          <code>${esc(a.slash)}${a.prefix ? ' ' + esc(a.prefix.trim()) : ''}</code>
        </div>
        <ul class="phase-action__guide">${guide}</ul>
        ${a.keyword_help ? kwBlock(i) : ''}
        <textarea class="phase-action__input" id="phaseInput${i}" rows="4"
          placeholder="${esc(a.placeholder)}" aria-label="${esc(a.label)}"></textarea>
        <div class="phase-action__error" id="phaseError${i}" role="alert" hidden></div>
        <div class="phase-action__agent">
          <label>${esc(t('phaseConsole.agent'))} <select id="phaseAgent${i}" data-phase-agent="${i}" aria-label="${esc(t('phaseConsole.agentLabel'))}"></select></label>
          <label title="${esc(t('phaseConsole.freshTitle'))}"><input type="checkbox" id="phaseFresh${i}" data-phase-agent="${i}"> ${esc(t('phaseConsole.fresh'))}</label>
          <span class="phase-action__note" id="phaseAgentNote${i}"></span>
        </div>
        <div class="phase-action__foot">
          <span class="phase-action__hint" id="phaseHint${i}">${esc(t('phaseConsole.sentToAgent'))}${esc(need)}</span>
          <button class="btn btn--primary btn--sm" data-phase-action="${i}">${esc(t('phaseConsole.run'))}</button>
        </div>
      </div>`;
  }

  // ---- agent picker --------------------------------------------------------
  const AGENT_KEY = 'smith_phase_agent';
  let agentInfo = { current: null, live: false, agents: [] };
  const remembered = () => { try { return localStorage.getItem(AGENT_KEY); } catch (_) { return null; } };
  const remember = (id) => { try { localStorage.setItem(AGENT_KEY, id); } catch (_) { /* blocked */ } };
  const label = (id) => (agentInfo.agents.find((a) => a.id === id) || {}).label || id;

  // The default keeps the session that is already following the pipeline;
  // without one, the agent the operator last chose, else the terminal's own
  // agent (herdr when installed), else claude, else the first installed.
  function defaultAgent() {
    const ids = agentInfo.agents.map((a) => a.id);
    if (agentInfo.live && ids.includes(agentInfo.current)) return agentInfo.current;
    const last = remembered();
    if (last && ids.includes(last)) return last;
    if (ids.includes(agentInfo.current)) return agentInfo.current;
    if (ids.includes('claude')) return 'claude';
    return ids[0] || '';
  }

  function agentNote(i) {
    const select = document.getElementById(`phaseAgent${i}`);
    const note = document.getElementById(`phaseAgentNote${i}`);
    if (!select || !note) return;
    const fresh = document.getElementById(`phaseFresh${i}`)?.checked;
    const same = agentInfo.live && select.value === agentInfo.current;
    note.textContent = !select.value ? t('phaseConsole.noAgents')
      : same && !fresh ? t('phaseConsole.continues', { agent: label(select.value) })
        : agentInfo.live ? t('phaseConsole.replaces', { current: label(agentInfo.current), next: fresh && same ? t('phaseConsole.aNewOne') : label(select.value) })
          : t('phaseConsole.opens', { agent: label(select.value) });
  }

  // Re-read the terminal's agent and session (they can change from the
  // terminal's own selector) and redraw every note from it.
  async function refreshAgentInfo() {
    if (typeof window.smithTerminalAgents !== 'function') return false;
    try { agentInfo = await window.smithTerminalAgents(); } catch (_) { return false; }
    current.forEach((a, i) => { if (a.kind === 'prompt') agentNote(i); });
    return true;
  }

  async function fillAgents() {
    if (!(await refreshAgentInfo())) return;
    const choice = defaultAgent();
    current.forEach((a, i) => {
      if (a.kind !== 'prompt') return;
      const select = document.getElementById(`phaseAgent${i}`);
      if (!select) return;
      select.innerHTML = agentInfo.agents
        .map((g) => `<option value="${esc(g.id)}"${g.id === choice ? ' selected' : ''}>${esc(g.label)}</option>`).join('');
      select.value = choice;
      agentNote(i);
    });
  }

  function commandCard(a, i) {
    return `<div class="phase-action phase-action--command">
        <div class="phase-action__head"><strong>${esc(a.label)}</strong></div>
        <p class="phase-action__desc">${esc(a.desc)}</p>
        <div class="phase-action__foot">
          <code class="phase-action__cmd">$ ${esc(a.command)}</code>
          <button class="btn btn--sm" data-phase-action="${i}">${esc(t('phaseConsole.runInShell'))}</button>
        </div>
      </div>`;
  }

  function redirectCard(a, i) {
    return `<button class="phase-action phase-action--redirect" data-phase-action="${i}">
        <strong>↗ ${esc(a.label)}</strong><span>${esc(a.desc)}</span>
      </button>`;
  }

  function renderPhaseActions(phase) {
    current = Array.isArray(phase && phase.actions) ? phase.actions : [];
    currentPhase = phase || null;
    if (!current.length) return '';
    const locked = phase && phase.unlocked === false;
    const lock = locked ? `<div class="phase-lock">
        <strong>${esc(t('phaseConsole.locked', { phase: phaseName(phase.blocked_by) }))}</strong>
        <span>${esc(t('phaseConsole.lockedWhy', { phase: phaseName(phase.blocked_by) }))}</span>
        <label><input type="checkbox" id="phaseOverride"> ${esc(t('phaseConsole.override'))}</label>
      </div>` : '';
    const cards = current.map((a, i) => (
      a.kind === 'prompt' ? promptCard(a, i) : a.kind === 'command' ? commandCard(a, i) : redirectCard(a, i)
    )).join('');
    setTimeout(fillAgents, 0);
    return `<div class="phase-actions">
        <h4 class="phase-actions__title">${esc(t('phaseConsole.title'))}</h4>
        ${lock}
        ${cards}
      </div>`;
  }

  // A locked phase runs only with the explicit override.
  // A visible error box under the prompt (the hint line alone was missed).
  function showError(i, msg) {
    const box = document.getElementById(`phaseError${i}`);
    const hint = document.getElementById(`phaseHint${i}`);
    if (hint) { hint.textContent = msg; hint.classList.add('is-error'); }
    if (box) {
      box.textContent = msg;
      box.hidden = false;
      if (box.scrollIntoView) box.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
    document.getElementById(`phaseInput${i}`)?.classList.add('is-invalid');
  }
  function clearError(i) {
    const box = document.getElementById(`phaseError${i}`);
    if (box) { box.hidden = true; box.textContent = ''; }
    document.getElementById(`phaseInput${i}`)?.classList.remove('is-invalid');
  }

  function blocked(i) {
    if (!currentPhase || currentPhase.unlocked !== false) return false;
    if (document.getElementById('phaseOverride')?.checked) return false;
    if (i !== null) showError(i, t('phaseConsole.blockedError', { phase: phaseName(currentPhase.blocked_by) }));
    return true;
  }

  async function send(command, run, kind, i, extra) {
    const sent = await window.sendToCli?.(command, run, { kind, ...(extra || {}) });
    if (sent && run && currentPhase && window.phaseRuns) {
      window.phaseRuns.start(currentPhase, command);
      const host = document.getElementById('phaseRunTracker');
      if (host) {
        host.dataset.stage = currentPhase.stage_id;
        host.innerHTML = window.phaseRuns.renderTracker(currentPhase);
        if (host.scrollIntoView) host.scrollIntoView({ block: 'start', behavior: 'smooth' });
      }
    } else if (sent === false && i !== undefined && i !== null) {
      const why = (window.smithTerminalActivity?.() || {}).refusal || '';
      showError(i, why === 'trust'
        ? t('phaseConsole.trust')
        : why === 'question'
          ? t('phaseConsole.question')
          : (why ? t('phaseConsole.sendFailedWhy', { why }) : t('phaseConsole.sendFailed')));
    }
    return sent;
  }

  async function runPrompt(a, i) {
    await refreshAgentInfo();
    const input = document.getElementById(`phaseInput${i}`);
    const hint = document.getElementById(`phaseHint${i}`);
    const text = String(input ? input.value : '').replace(/\s+/g, ' ').trim();
    const fail = (msg) => { showError(i, msg); input?.focus(); };
    clearError(i);
    if (blocked(i)) return;
    if (!text && !a.optional) return fail(t('phaseConsole.writeFirst'));
    if (a.min_sentences && phaseSentenceCount(text) < a.min_sentences) {
      return fail(t('phaseConsole.needSentences', { n: a.min_sentences }));
    }
    const command = [a.slash, `${a.prefix || ''}${text}`.trim()].filter(Boolean).join(' ');
    const agent = document.getElementById(`phaseAgent${i}`)?.value || undefined;
    const fresh = Boolean(document.getElementById(`phaseFresh${i}`)?.checked);
    if (agent) remember(agent);
    if (hint) { hint.textContent = t('phaseConsole.sending', { command: `${command.slice(0, 80)}${command.length > 80 ? '…' : ''}` }); hint.classList.remove('is-error'); }
    send(command, true, 'slash', i, { agent, fresh });
  }

  function redirect(a) {
    if (window.closeDrawer) window.closeDrawer();
    if (window.navigateTab) window.navigateTab(a.tab);
    if (a.tab === 'modelo' && a.section && window.filterModelView) {
      const btn = Array.from(document.querySelectorAll('.model-subnav-btn'))
        .find((b) => (b.getAttribute('onclick') || '').includes(`'${a.section}'`));
      window.filterModelView(a.section, btn);
    } else if (a.section) {
      // On any other tab the section names a panel to scroll to.
      document.getElementById(`${a.section}Panel`)?.scrollIntoView({ behavior: 'smooth' });
    }
  }

  // Capture phase: the phase drawer stops click propagation
  // (onclick="event.stopPropagation()"), so a bubbling listener never fires.
  document.addEventListener('click', (event) => {
    const help = event.target.closest('[data-kw-help]');
    if (help) {
      const i = Number(help.dataset.kwIndex);
      const a = current[i];
      if (!a || !a.keyword_help) return;
      const what = help.dataset.kwHelp;
      if (what === 'propose') kwPropose(i);
      else if (what === 'add') kwAdd(i);
      else if (what === 'approve') kwApprove(a, i);
      else if (what === 'discard') kwShow(i, '');
      return;
    }
    const el = event.target.closest('[data-phase-action]');
    if (!el) return;
    const i = Number(el.dataset.phaseAction);
    const a = current[i];
    if (!a) return;
    if (a.kind === 'prompt') runPrompt(a, i);
    else if (a.kind === 'command') {
      // A command with a <placeholder> is typed, not run: the operator fills it.
      if (blocked(null)) return;
      send(a.command, !/<[^>]+>/.test(a.command), 'shell', null);
    } else redirect(a);
  }, true);

  document.addEventListener('input', (event) => {
    const field = event.target && event.target.closest && event.target.closest('[data-kw-input]');
    if (field) kwState(Number(field.dataset.kwInput));
  }, true);
  document.addEventListener('change', (event) => {
    const el = event.target && event.target.closest && event.target.closest('[data-phase-agent]');
    if (el) refreshAgentInfo().then(() => agentNote(Number(el.dataset.phaseAgent)));
  }, true);
  document.addEventListener('focusin', (event) => {
    if (event.target && event.target.closest && event.target.closest('[data-phase-agent]')) refreshAgentInfo();
  }, true);

  window.renderPhaseActions = renderPhaseActions;
  window.phaseSentenceCount = phaseSentenceCount;
})();
