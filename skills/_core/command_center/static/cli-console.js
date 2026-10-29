/* Smith CLI assistant (the "support CLI") for the Paper Command Center.
 *
 * A floating xterm.js window, opened from the bottom-right FAB, bound to one
 * PTY session on the backend (skills/_core/command_center/terminal.py): herdr
 * (default), claude, opencode, pi or a login shell, started in the project
 * root. Output arrives over SSE; keys, resizes and closes go out as
 * same-origin JSON requests carrying the X-Papersmith-Terminal header, and the
 * server also requires the per-server cookie set by its printed login URL.
 *
 * The session outlives the window: closing it only hides it, and a reload
 * while a phase run is live keeps the session and reattaches to it.
 *
 * Public surface (window): toggleSmithTerminal(), openCliConsole(),
 * closeCliConsole(), sendToCli(text, run), smithTerminalInterrupt().
 */
(function () {
  'use strict';

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const HEADERS = { 'Content-Type': 'application/json', 'X-Papersmith-Terminal': '1' };
  const AGENT_KEY = 'smith_terminal_agent';
  const INPUT_FLUSH_MS = 6;
  // One remembered session per dashboard server, for a reload to reattach.
  const SESSION_KEY = `smith_terminal_session@${(typeof location !== 'undefined' && location.host) || 'local'}`;
  // Output replayed on reconnect is not the agent working.
  const REPLAY_QUIET_MS = 800;

  const state = {
    info: null,        // GET /api/terminal/agents
    tools: null,       // GET /api/terminal/tools
    term: null,
    fit: null,
    sessionId: null,
    source: null,
    agent: null,
    starting: null,
    exited: false,
    pendingInput: '',
    flushTimer: null,
    lastOutputAt: 0,
    startedAt: 0,
    refusal: '',       // why the last sendToCli did not send, for the caller
    quietUntil: 0,     // replayed output before this does not count as activity
    resuming: null,    // the reattach attempt started on load
    said: null,        // the last status as { key, vars, tone }, redrawn on a language switch
  };

  const $ = (id) => document.getElementById(id);

  function readAgent() {
    try { return localStorage.getItem(AGENT_KEY); } catch (_) { return null; }
  }
  function saveAgent(agent) {
    try { localStorage.setItem(AGENT_KEY, agent); } catch (_) { /* storage blocked */ }
  }
  function rememberSession(id, agent) {
    try { localStorage.setItem(SESSION_KEY, JSON.stringify({ id, agent })); } catch (_) { /* storage blocked */ }
  }
  function storedSession() {
    try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null'); } catch (_) { return null; }
  }
  function forgetSession(id) {
    const stored = storedSession();
    if (id && stored && stored.id !== id) return;
    try { localStorage.removeItem(SESSION_KEY); } catch (_) { /* storage blocked */ }
  }

  async function api(path, method, body) {
    const res = await fetch(path, {
      method, headers: HEADERS, body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = {};
    try { data = await res.json(); } catch (_) { /* empty body */ }
    if (!res.ok) throw new Error(data.detail || data.error || `HTTP ${res.status}`);
    return data;
  }

  // ---- status: header dot, FAB badge and footer agent ---------------------
  function setStatus(text, tone) {
    const label = $('terminalStatusText');
    if (label) label.textContent = text;
    const dot = $('terminalStatusDot');
    if (dot) {
      dot.classList.toggle('is-connected', tone === 'ok');
      dot.classList.toggle('is-connecting', tone === 'warn');
      dot.title = text;
    }
    const badge = $('smithFabBadge');
    if (badge) badge.dataset.tone = tone || 'off';
  }

  // A status from the catalogue, remembered so a language switch redraws it.
  function say(key, vars, tone) {
    state.said = { key, vars, tone };
    setStatus(t(key, vars), tone);
  }

  function agentLabel(id) {
    const agent = ((state.info && state.info.agents) || []).find((a) => a.id === id);
    return agent ? agent.label : id;
  }

  function renderFooter() {
    const agentEl = $('terminalFooterAgent');
    if (agentEl) agentEl.textContent = agentLabel(state.agent);
    const runEl = $('terminalFooterRun');
    if (runEl && state.tools) runEl.textContent = state.tools.monitored_path || '';
  }

  // ---- agents, tools and quick commands ------------------------------------
  async function loadInfo() {
    if (state.info) return state.info;
    const res = await fetch('/api/terminal/agents');
    state.info = res.ok ? await res.json() : { enabled: false, agents: [], quick: {} };
    const available = (state.info.agents || []).filter((a) => a.available).map((a) => a.id);
    const saved = readAgent();
    state.agent = available.includes(saved) ? saved : (state.info.default || available[0] || 'shell');
    const select = $('terminalAgentSelect');
    if (select) {
      select.innerHTML = '';
      for (const agent of state.info.agents || []) {
        const opt = document.createElement('option');
        opt.value = agent.id;
        opt.textContent = agent.available ? agent.label : t('cli.notInstalled', { agent: agent.label });
        opt.disabled = !agent.available;
        opt.title = agent.desc || '';
        select.appendChild(opt);
      }
      select.value = state.agent;
    }
    renderQuick();
    if (!state.info.enabled) {
      say('cli.disabled', null, 'bad');
    } else if (!state.info.authorized) {
      say('cli.openFromLink', null, 'bad');
    } else {
      loadTools();
    }
    renderFooter();
    return state.info;
  }

  async function loadTools() {
    try {
      const data = await api('/api/terminal/tools', 'GET');
      state.tools = data.tools;
    } catch (_) {
      state.tools = null;
    }
    const btn = $('btnLaunchExternalTerm');
    if (btn && state.tools) {
      const name = state.tools.preferred_terminal === 'wezterm' ? 'WezTerm' : 'Ghostty';
      btn.textContent = `🖥️ ${name}`;
      btn.disabled = !state.tools.ready;
      btn.title = state.tools.ready
        ? t('cli.openHerdrIn', { terminal: name })
        : t('cli.missingTools', { missing: (state.tools.missing || []).join(', ') });
    }
    renderFooter();
  }

  function renderQuick() {
    const select = $('terminalQuickSelect');
    if (!select || !state.info) return;
    const quick = state.info.quick || {};
    const items = state.agent === 'shell' ? (quick.shell || []) : (quick.agent || []);
    select.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = t('cli.quickPlaceholder');
    select.appendChild(placeholder);
    for (const cmd of items) {
      const opt = document.createElement('option');
      opt.value = cmd;
      opt.textContent = cmd;
      select.appendChild(opt);
    }
    select.disabled = items.length === 0;
  }

  // ---- xterm ---------------------------------------------------------------
  function flushInput() {
    state.flushTimer = null;
    const data = state.pendingInput;
    state.pendingInput = '';
    if (data && state.sessionId) {
      api(`/api/terminal/sessions/${state.sessionId}/input`, 'POST', { data }).catch(() => {});
    }
  }

  // Keystrokes are coalesced for a few milliseconds: one request per burst
  // (a paste, a held key) instead of one per character.
  function queueInput(data) {
    if (!state.sessionId) {
      if (!state.exited) start().catch(() => {});
      return;
    }
    state.pendingInput += data;
    if (!state.flushTimer) state.flushTimer = setTimeout(flushInput, INPUT_FLUSH_MS);
  }

  function sendResize(redraw) {
    if (!state.sessionId || !state.term) return;
    api(`/api/terminal/sessions/${state.sessionId}/input`, 'POST', {
      cols: state.term.cols, rows: state.term.rows, redraw: Boolean(redraw),
    }).catch(() => {});
  }

  function refit(redraw) {
    try { state.fit && state.fit.fit(); } catch (_) { /* hidden container */ }
    if (redraw) sendResize(true);
  }

  function ensureTerm() {
    if (state.term) return state.term;
    if (!window.Terminal) {
      say('cli.noXterm', null, 'bad');
      return null;
    }
    const term = new window.Terminal({
      cursorBlink: true, fontSize: 13, lineHeight: 1.25, scrollback: 5000,
      // Nerd Fonts first, when installed, so herdr/opencode icons render.
      fontFamily: '"IosevkaTerm Nerd Font", "JetBrainsMono Nerd Font", "MesloLGS NF", '
        + '"Symbols Nerd Font Mono", ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
      theme: {
        background: '#080c14', foreground: '#f1f5f9', cursor: '#38bdf8',
        selectionBackground: 'rgba(56, 189, 248, 0.35)',
        black: '#1e293b', red: '#f87171', green: '#4ade80', yellow: '#facc15',
        blue: '#60a5fa', magenta: '#c084fc', cyan: '#22d3ee', white: '#e2e8f0',
        brightBlack: '#475569', brightRed: '#fca5a5', brightGreen: '#86efac',
        brightYellow: '#fde047', brightBlue: '#93c5fd', brightMagenta: '#d8b4fe',
        brightCyan: '#67e8f9', brightWhite: '#f8fafc',
      },
    });
    const fit = window.FitAddon ? new window.FitAddon.FitAddon() : null;
    if (fit) term.loadAddon(fit);
    const container = $('terminalContainer');
    term.open(container);
    container.addEventListener('mousedown', () => term.focus());
    term.onData(queueInput);
    term.onResize(() => sendResize(false));
    state.term = term;
    state.fit = fit;
    new ResizeObserver(() => refit(false)).observe(container);
    return term;
  }

  function decode(b64) {
    const raw = atob(b64);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    return bytes;
  }

  // Every connect streams the session from its start. A reconnect (and a
  // reattach after a reload) clears the screen first, so the replay is drawn
  // once, and its burst is not read as the agent working.
  function attach(sessionId, replay) {
    if (state.source) state.source.close();
    const source = new EventSource(`/api/terminal/sessions/${sessionId}/stream`);
    let opened = false;
    source.addEventListener('output', (event) => {
      if (Date.now() >= state.quietUntil) state.lastOutputAt = Date.now();
      state.term.write(decode(JSON.parse(event.data).payload.data));
    });
    source.addEventListener('exit', () => {
      source.close();
      // Release the ended session so it stops counting toward the cap.
      api(`/api/terminal/sessions/${sessionId}`, 'DELETE', {}).catch(() => {});
      forgetSession(sessionId);
      if (state.sessionId === sessionId) {
        state.sessionId = null;
        state.exited = true;
        state.term.write(`\r\n\x1b[90m[Smith] ${t('cli.sessionEndedLine')}\x1b[0m\r\n`);
        say('cli.sessionEnded', null, 'off');
      }
    });
    source.onerror = () => { if (state.sessionId === sessionId) say('cli.reconnecting', null, 'warn'); };
    source.onopen = () => {
      if (opened || replay) {
        state.term.reset();
        state.quietUntil = Date.now() + REPLAY_QUIET_MS;
      }
      opened = true;
      say('cli.connected', { agent: agentLabel(state.agent) }, 'ok');
    };
    state.source = source;
  }

  // After a reload: reattach to the remembered session if it is still alive.
  async function resume() {
    const stored = storedSession();
    if (!stored || !stored.id) return;
    try {
      const info = await loadInfo();
      if (!info.enabled || !info.authorized) return;
      const session = await api(`/api/terminal/sessions/${encodeURIComponent(stored.id)}`, 'GET');
      if (!session.alive || state.sessionId) { if (!session.alive) forgetSession(stored.id); return; }
      if (!ensureTerm()) return;
      state.agent = session.agent;
      const select = $('terminalAgentSelect');
      if (select) select.value = session.agent;
      renderQuick();
      renderFooter();
      state.sessionId = session.id;
      state.exited = false;
      state.startedAt = Date.now();
      attach(session.id, true);
    } catch (err) {
      // Only a session the server no longer has is forgotten; a transient
      // failure keeps the record so the next load can still reattach.
      if (/no such session/.test(err.message)) forgetSession(stored.id);
    }
  }

  async function start() {
    if (state.resuming) await state.resuming;
    if (state.sessionId) return state.sessionId;
    if (state.starting) return state.starting;
    state.starting = (async () => {
      const info = await loadInfo();
      if (!info.enabled) throw new Error(t('cli.errDisabled'));
      if (!info.authorized) throw new Error(t('cli.errNoAccess'));
      const term = ensureTerm();
      if (!term) throw new Error(t('cli.errNoXterm'));
      refit(false);
      say('cli.opening', { agent: agentLabel(state.agent) }, 'warn');
      state.startedAt = Date.now();
      state.lastOutputAt = 0;
      const created = await api('/api/terminal/sessions', 'POST', {
        agent: state.agent, cols: term.cols, rows: term.rows,
      });
      state.sessionId = created.id;
      state.exited = false;
      rememberSession(created.id, state.agent);
      attach(created.id, false);
      term.focus();
      return created.id;
    })();
    try {
      return await state.starting;
    } catch (err) {
      say('cli.openFailed', { error: err.message }, 'bad');
      throw err;
    } finally {
      state.starting = null;
    }
  }

  async function stop() {
    const sid = state.sessionId;
    state.sessionId = null;
    if (state.source) { state.source.close(); state.source = null; }
    forgetSession(sid);
    if (sid) {
      try { await api(`/api/terminal/sessions/${sid}`, 'DELETE', {}); } catch (_) { /* gone */ }
    }
    say('cli.noSession', null, 'off');
  }

  async function restart() {
    await stop();
    if (state.term) state.term.reset();
    state.exited = false;
    start().catch(() => {});
  }

  // ---- window --------------------------------------------------------------
  function isOpen() {
    const win = $('smithTerminalWindow');
    return Boolean(win && win.classList.contains('is-open'));
  }

  function openCliConsole() {
    const win = $('smithTerminalWindow');
    if (!win) return;
    win.classList.add('is-open');
    win.setAttribute('aria-hidden', 'false');
    $('smithAssistantFab')?.classList.add('is-active');
    // A session detached while hidden is streamed again (and replayed once).
    if (state.sessionId && !state.source && ensureTerm()) attach(state.sessionId, true);
    loadInfo().then((info) => {
      if (!ensureTerm()) return;
      setTimeout(() => {
        refit(true);
        if (info.enabled && info.authorized && !state.sessionId && !state.exited) start().catch(() => {});
        state.term.focus();
      }, 100);
    });
  }

  function phaseRunLive() {
    return Boolean(window.phaseRuns && typeof window.phaseRuns.anyRunning === 'function'
      && window.phaseRuns.anyRunning());
  }

  // Stops streaming a hidden session nobody follows; the session keeps
  // running on the server. While a phase runs the stream stays open, because
  // the run tracker reads the agent's activity from it.
  function detachIfIdle() {
    if (!state.source || isOpen() || phaseRunLive()) return;
    state.source.close();
    state.source = null;
  }

  // Hides the window only: the session keeps running behind the FAB.
  function closeCliConsole() {
    const win = $('smithTerminalWindow');
    if (!win) return;
    win.classList.remove('is-open');
    win.setAttribute('aria-hidden', 'true');
    $('smithAssistantFab')?.classList.remove('is-active');
    detachIfIdle();
  }

  function toggleSmithTerminal() {
    if (isOpen()) closeCliConsole(); else openCliConsole();
  }

  function toggleMaximize() {
    const win = $('smithTerminalWindow');
    if (!win) return;
    const maximized = win.classList.toggle('is-maximized');
    const btn = $('btnTerminalMaximize');
    if (btn) btn.textContent = maximized ? '🗗' : '⛶';
    setTimeout(() => refit(true), 150);
  }

  async function launchExternal() {
    try {
      const result = await api('/api/terminal/launch-external', 'POST', {});
      say('cli.herdrOpened', { terminal: result.terminal }, 'ok');
    } catch (err) {
      say('cli.externalFailed', { error: err.message }, 'bad');
    }
  }

  // Agents a phase slash command can be typed into. herdr comes first: its
  // workspace mirrors the agent pane, so a phase runs in the herdr session by
  // default and only falls to a new claude/opencode/pi session without herdr.
  // The plain shell is not one of them.
  const SLASH_AGENTS = ['herdr', 'claude', 'opencode', 'pi', 'antigravity'];
  // Agents with a `!command` shell escape, so a shell phase can run inside
  // their open session instead of closing it.
  const SHELL_ESCAPE_AGENTS = ['claude', 'opencode', 'pi'];

  // Which agent runs a phase command, keeping the open session whenever it can:
  //  - slash: the agent the operator picked (options.agent), else the open
  //    slash agent, else the first installed one (herdr when installed);
  //  - shell: an open slash-agent session runs it as `!command` (every one of
  //    claude, opencode and pi has a shell escape), so one session follows the
  //    whole pipeline; otherwise the plain shell.
  // A different agent, or options.fresh, ends the open session: never without
  // the operator's confirmation. Returns { switched, prefix }.
  async function useAgent(kind, options) {
    const opts = options || {};
    const info = await loadInfo();
    const available = (info.agents || []).filter((a) => a.available).map((a) => a.id);
    const live = Boolean(state.sessionId);
    let wanted = state.agent;
    if (kind === 'shell') {
      if (live && SHELL_ESCAPE_AGENTS.includes(state.agent)) return { switched: false, prefix: '!' };
      wanted = 'shell';
    }
    if (kind === 'slash') {
      if (opts.agent && !(SLASH_AGENTS.includes(opts.agent) && available.includes(opts.agent))) {
        throw new Error(t('cli.errAgentMissing', { agent: agentLabel(opts.agent) }));
      }
      if (opts.agent) wanted = opts.agent;
      else if (!(SLASH_AGENTS.includes(state.agent) && available.includes(state.agent))) {
        wanted = SLASH_AGENTS.find((id) => available.includes(id)) || null;
      }
      if (!wanted) throw new Error(t('cli.errNoAgent'));
    }
    const restart = wanted !== state.agent || (opts.fresh && live);
    if (!restart) return { switched: false, prefix: '' };
    if (live && !window.confirm(wanted === state.agent
      ? t('cli.confirmFresh', { agent: agentLabel(state.agent) })
      : t('cli.confirmSwitch', { agent: agentLabel(state.agent), next: agentLabel(wanted) }))) {
      throw new Error(t('cli.errKept', { agent: agentLabel(state.agent) }));
    }
    state.agent = wanted;
    if (kind === 'slash') saveAgent(wanted);
    const select = $('terminalAgentSelect');
    if (select) select.value = wanted;
    renderQuick();
    renderFooter();
    await stop();
    if (state.term) state.term.reset();
    return { switched: true, prefix: '' };
  }

  // What the phase drawer offers: the installed slash agents and the session
  // a phase would continue in.
  async function smithTerminalAgents() {
    const info = await loadInfo();
    const agents = (info.agents || []).filter((a) => a.available && SLASH_AGENTS.includes(a.id))
      .map((a) => ({ id: a.id, label: a.label }));
    return { current: state.agent, live: Boolean(state.sessionId), agents };
  }

  // A freshly started agent paints its prompt before it reads input: wait for
  // its first output and then a short quiet spell (bounded), so the text is
  // typed into the agent rather than lost while it boots.
  // Output that arrived since the session started counts, even if it came
  // before this wait began.
  async function settle(maxMs) {
    const began = Date.now();
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    while (Date.now() - began < maxMs) {
      await sleep(250);
      if (state.lastOutputAt >= state.startedAt && state.lastOutputAt > 0
          && Date.now() - state.lastOutputAt > 900) return;
    }
  }

  // The visible screen, as text, so a startup question is never answered by
  // the Enter meant for the command.
  function screenText() {
    const buffer = state.term && state.term.buffer && state.term.buffer.active;
    if (!buffer) return '';
    const lines = [];
    for (let y = 0; y < state.term.rows; y++) {
      const line = buffer.getLine(buffer.viewportY + y);
      if (line) lines.push(line.translateToString(true));
    }
    return lines.join('\n');
  }
  const STARTUP_QUESTIONS = /trust this folder|Do you trust|Enter to confirm/i;

  // Types `text` into the session (opening one if needed). run=true also sends
  // Enter, as a separate write so an agent does not read it as a paste.
  // options.kind: 'slash' runs it in an agent, 'shell' as a shell command;
  // options.agent picks the slash agent; options.fresh asks for a new session.
  async function sendToCli(text, run, options) {
    try {
      const kind = options && options.kind;
      // Choose the agent before opening the window, which starts a session.
      const choice = kind ? await useAgent(kind, options) : { switched: false, prefix: '' };
      const switched = choice.switched;
      text = choice.prefix + text;
      openCliConsole();
      const fresh = switched || !state.sessionId;
      const sid = await start();
      if (fresh && state.agent !== 'shell') await settle(12000);
      state.refusal = '';
      if (kind === 'slash' && STARTUP_QUESTIONS.test(screenText())) {
        state.refusal = /trust/i.test(screenText()) ? 'trust' : 'question';
        say('cli.awaitingConfirmation', null, 'warn');
        state.term.focus();
        return false;
      }
      await api(`/api/terminal/sessions/${sid}/input`, 'POST', { data: text });
      if (run) {
        setTimeout(() => {
          api(`/api/terminal/sessions/${sid}/input`, 'POST', { data: '\r' }).catch(() => {});
        }, 200);
      }
      state.term.focus();
      return true;
    } catch (err) {
      state.refusal = err.message;
      if (!isOpen()) openCliConsole();
      say('cli.sendFailed', { error: err.message }, 'bad');
      return false;
    }
  }

  // "Stop process": interrupts the agent's turn (Esc) or the shell's command
  // (Ctrl-C). The session stays open for the next phase. Resolves false when
  // there is no session; rejects when the key could not be delivered.
  async function interrupt() {
    if (state.resuming) await state.resuming;
    const sid = state.sessionId;
    if (!sid) return false;
    const key = state.agent === 'shell' || state.agent === 'herdr' ? '\x03' : '\x1b';
    await api(`/api/terminal/sessions/${sid}/input`, 'POST', { data: key });
    return true;
  }

  // What the phase run tracker reads to show whether the agent is working.
  function smithTerminalActivity() {
    return { sessionId: state.sessionId, agent: state.agent, lastOutputAt: state.lastOutputAt,
             refusal: state.refusal };
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('smithAssistantFab')?.addEventListener('click', toggleSmithTerminal);
    $('btnTerminalClose')?.addEventListener('click', closeCliConsole);
    $('btnTerminalMaximize')?.addEventListener('click', toggleMaximize);
    $('btnTerminalRestart')?.addEventListener('click', restart);
    $('btnLaunchExternalTerm')?.addEventListener('click', launchExternal);
    $('btnTerminalClear')?.addEventListener('click', () => state.term && state.term.clear());
    const agentSelect = $('terminalAgentSelect');
    agentSelect?.addEventListener('change', () => {
      state.agent = agentSelect.value;
      saveAgent(state.agent);
      renderQuick();
      renderFooter();
      restart();
    });
    const quick = $('terminalQuickSelect');
    quick?.addEventListener('change', () => {
      if (quick.value) sendToCli(quick.value, true);
      quick.value = '';
    });
    // Back on the tab or window: refit and ask the program to repaint.
    const wake = () => { if (isOpen() && state.sessionId) refit(true); };
    // Leaving the page also drops the stream of a closed console once no
    // phase runs any more (a run that ended after the console was closed).
    document.addEventListener('visibilitychange', () => { if (document.hidden) detachIfIdle(); else wake(); });
    window.addEventListener('focus', wake);
    window.addEventListener('resize', () => { if (isOpen()) refit(false); });
    // A reload keeps the session of a running phase (and reattaches to it);
    // otherwise it ends the session so it never lingers unseen.
    window.addEventListener('beforeunload', () => {
      const running = window.phaseRuns && typeof window.phaseRuns.anyRunning === 'function'
        && window.phaseRuns.anyRunning();
      if (state.sessionId && !running) {
        forgetSession(state.sessionId);
        fetch(`/api/terminal/sessions/${state.sessionId}`, { method: 'DELETE', headers: HEADERS, body: '{}', keepalive: true });
      }
    });
    say('cli.noSession', null, 'off');
    state.resuming = resume().finally(() => { state.resuming = null; });
  });

  // Agent descriptions come from the server in the chosen language: read them
  // again, and redraw the status line.
  document.addEventListener('languagechange', () => {
    state.info = null;
    if (state.said) setStatus(t(state.said.key, state.said.vars), state.said.tone);
    loadInfo().catch(() => {});
  });

  window.toggleSmithTerminal = toggleSmithTerminal;
  window.openCliConsole = openCliConsole;
  window.closeCliConsole = closeCliConsole;
  window.sendToCli = sendToCli;
  window.smithTerminalActivity = smithTerminalActivity;
  window.smithTerminalAgents = smithTerminalAgents;
  window.smithTerminalInterrupt = interrupt;
})();
