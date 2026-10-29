"""cli-console.js routes a phase command to the right terminal agent: a slash
command to claude/opencode/pi, a shell command to the shell; it never closes a
live session without the operator's confirmation, and never answers an agent's
startup question with the command's Enter. Runs the real script in node with
a stub DOM, xterm, fetch and EventSource."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import server

SCRIPT = Path(server.__file__).resolve().parent / "static" / "cli-console.js"
STATIC = Path(server.__file__).resolve().parent / "static"
I18N_JS = STATIC / "i18n.js"
EN_JS = STATIC / "i18n" / "en.js"
ES_JS = STATIC / "i18n" / "es.js"

HARNESS = r"""
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync(0, 'utf8'));
const log = [];
const els = {};
function el(id) {
  if (!els[id]) {
    const cls = new Set();
    els[id] = { id, value: '', textContent: '', dataset: {}, disabled: false, innerHTML: '',
      classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c), contains: (c) => cls.has(c),
                   toggle: (c, on) => (on === undefined ? (cls.has(c) ? cls.delete(c) : cls.add(c)) : on ? cls.add(c) : cls.delete(c)) },
      setAttribute() {}, addEventListener() {}, appendChild() {}, focus() {} };
  }
  return els[id];
}
const store = { smith_terminal_agent: cfg.agent, 'papersmith-lang': 'es' };
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
global.document = { getElementById: el, addEventListener() {}, createElement: () => el('x' + Math.random()), querySelectorAll: () => [] };
global.ResizeObserver = class { observe() {} };
let sessions = 0;
global.fetch = async (path, opts = {}) => {
  const method = opts.method || 'GET';
  const body = opts.body ? JSON.parse(opts.body) : undefined;
  let data = {};
  if (path === '/api/terminal/agents') {
    data = { enabled: true, authorized: true, default: cfg.agent, quick: {},
             agents: ['herdr', 'claude', 'opencode', 'pi', 'shell'].map((id) => ({ id, label: id, available: cfg.available.includes(id) })) };
  } else if (path === '/api/terminal/sessions' && method === 'POST') {
    sessions += 1; data = { id: 's' + sessions }; log.push(['open', body.agent]);
  } else if (path.endsWith('/input')) {
    if ('data' in body) log.push(['input', path.split('/')[4], body.data]);
  } else if (method === 'DELETE') {
    log.push(['close', path.split('/')[4]]);
  }
  return { ok: true, json: async () => data };
};
global.EventSource = class {
  constructor() { this.l = {}; setTimeout(() => this.l.output && this.l.output({ data: JSON.stringify({ payload: { data: '' } }) }), 20); }
  addEventListener(t, fn) { this.l[t] = fn; }
  close() {}
};
global.window = {
  localStorage: global.localStorage,
  confirm: (msg) => { log.push(['confirm']); return cfg.confirm; },
  Terminal: class {
    constructor() { this.cols = 80; this.rows = 3; this.buffer = { active: { viewportY: 0, getLine: (y) => ({ translateToString: () => (cfg.screen || [])[y] || '' }) } }; }
    loadAddon() {} open() {} onData() {} onResize() {} write() {} reset() {} focus() {} clear() {}
  },
};
eval(fs.readFileSync(process.argv[2], 'utf8'));
eval(fs.readFileSync(process.argv[3], 'utf8'));
eval(fs.readFileSync(process.argv[4], 'utf8'));
eval(fs.readFileSync(process.argv[1], 'utf8'));
(async () => {
  for (const s of cfg.sends) {
    await window.sendToCli(s.text, s.run, s.kind ? { kind: s.kind, ...(s.opts || {}) } : undefined);
    log.push(['status', el('terminalStatusText').textContent]);
    log.push(['refusal', window.smithTerminalActivity().refusal]);
  }
  await new Promise((r) => setTimeout(r, 300));
  log.push(['saved', store.smith_terminal_agent]);
  console.log(JSON.stringify(log));
})();
"""


def run(**cfg) -> list:
    cfg.setdefault("confirm", True)
    out = subprocess.run(["node", "-e", HARNESS, str(SCRIPT), str(EN_JS), str(ES_JS), str(I18N_JS)], input=json.dumps(cfg),
                         capture_output=True, text=True, cwd=tempfile.gettempdir(), timeout=60, check=True)
    return json.loads(out.stdout)


def events(log: list, kind: str) -> list:
    return [entry[1:] for entry in log if entry[0] == kind]


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class CliRoutingTests(unittest.TestCase):
    def test_a_slash_command_opens_the_herdr_session_when_herdr_is_installed(self) -> None:
        log = run(agent="herdr", available=["herdr", "opencode", "pi", "shell"],
                  sends=[{"text": "/plausibility idea", "run": True, "kind": "slash"}])
        self.assertEqual(events(log, "open"), [["herdr"]])
        self.assertEqual(events(log, "input"), [["s1", "/plausibility idea"], ["s1", "\r"]])
        self.assertEqual(events(log, "confirm"), [])

    def test_the_operator_can_send_a_phase_to_herdr_explicitly(self) -> None:
        log = run(agent="claude", available=["herdr", "claude"],
                  sends=[{"text": "/plausibility idea", "run": True, "kind": "slash", "opts": {"agent": "herdr"}}])
        self.assertEqual(events(log, "open"), [["herdr"]])
        self.assertIn(["s1", "/plausibility idea"], events(log, "input"))

    def test_without_herdr_a_slash_command_opens_a_new_agent_session(self) -> None:
        log = run(agent="herdr", available=["opencode", "pi", "shell"],
                  sends=[{"text": "/plausibility idea", "run": True, "kind": "slash"}])
        self.assertEqual(events(log, "open"), [["opencode"]])
        self.assertEqual(events(log, "input"), [["s1", "/plausibility idea"], ["s1", "\r"]])

    def test_no_installed_agent_sends_nothing_and_says_why(self) -> None:
        log = run(agent="shell", available=["shell"],
                  sends=[{"text": "/plausibility idea", "run": True, "kind": "slash"}])
        self.assertEqual(events(log, "input"), [])
        self.assertIn("no hay un agente", events(log, "status")[-1][0])

    def test_a_shell_command_runs_inside_the_open_agent_session(self) -> None:
        sends = [{"text": "/plausibility idea", "run": True, "kind": "slash"},
                 {"text": "smith status .", "run": True, "kind": "shell"}]
        log = run(agent="claude", available=["claude", "shell"], sends=sends)
        self.assertEqual(events(log, "open"), [["claude"]])
        self.assertEqual(events(log, "confirm"), [])
        self.assertIn(["s1", "!smith status ."], events(log, "input"))

    def test_without_an_agent_session_a_shell_command_uses_the_shell(self) -> None:
        log = run(agent="herdr", available=["herdr", "shell"],
                  sends=[{"text": "smith status .", "run": True, "kind": "shell"}])
        self.assertEqual(events(log, "open"), [["shell"]])
        self.assertIn(["s1", "smith status ."], events(log, "input"))

    def test_the_same_agent_keeps_one_session_across_phases(self) -> None:
        sends = [{"text": "/plausibility idea", "run": True, "kind": "slash", "opts": {"agent": "claude"}},
                 {"text": "/paper-ingestion x", "run": True, "kind": "slash", "opts": {"agent": "claude"}}]
        log = run(agent="herdr", available=["herdr", "claude", "pi"], sends=sends)
        self.assertEqual(events(log, "open"), [["claude"]])
        self.assertEqual([e for e in events(log, "input") if e[1] != "\r"],
                         [["s1", "/plausibility idea"], ["s1", "/paper-ingestion x"]])
        self.assertEqual(events(log, "saved")[-1], ["claude"])

    def test_the_operator_picks_the_agent_and_a_switch_needs_confirmation(self) -> None:
        sends = [{"text": "/plausibility idea", "run": True, "kind": "slash", "opts": {"agent": "claude"}},
                 {"text": "/paper-ingestion x", "run": True, "kind": "slash", "opts": {"agent": "pi"}}]
        refused = run(agent="herdr", available=["claude", "pi"], confirm=False, sends=sends)
        self.assertEqual(events(refused, "open"), [["claude"]])
        self.assertEqual(events(refused, "close"), [])
        self.assertNotIn(["s1", "/paper-ingestion x"], events(refused, "input"))
        accepted = run(agent="herdr", available=["claude", "pi"], confirm=True, sends=sends)
        self.assertEqual(events(accepted, "open"), [["claude"], ["pi"]])
        self.assertEqual(events(accepted, "close"), [["s1"]])
        self.assertIn(["s2", "/paper-ingestion x"], events(accepted, "input"))

    def test_an_agent_that_is_not_installed_is_refused_not_replaced(self) -> None:
        log = run(agent="herdr", available=["claude"],
                  sends=[{"text": "/plausibility idea", "run": True, "kind": "slash", "opts": {"agent": "pi"}}])
        # The window opens on the current terminal to show why; no agent runs.
        self.assertNotIn(["pi"], events(log, "open"))
        self.assertNotIn(["claude"], events(log, "open"))
        self.assertEqual(events(log, "input"), [])
        self.assertIn("no está instalado", events(log, "status")[-1][0])

    def test_a_new_session_is_opened_only_when_asked(self) -> None:
        sends = [{"text": "/plausibility idea", "run": True, "kind": "slash", "opts": {"agent": "claude"}},
                 {"text": "/plausibility again", "run": True, "kind": "slash", "opts": {"agent": "claude", "fresh": True}}]
        log = run(agent="claude", available=["claude"], confirm=True, sends=sends)
        self.assertEqual(events(log, "open"), [["claude"], ["claude"]])
        self.assertEqual(events(log, "close"), [["s1"]])
        self.assertEqual(len(events(log, "confirm")), 1)

    def test_a_startup_question_is_never_answered_by_the_command(self) -> None:
        log = run(agent="claude", available=["claude"], screen=["Do you trust the files?", "Enter to confirm"],
                  sends=[{"text": "/plausibility idea", "run": True, "kind": "slash"}])
        self.assertEqual(events(log, "input"), [])
        self.assertIn("espera una confirmación", events(log, "status")[-1][0])
        self.assertIn(["refusal", "trust"], [e for e in log if e[0] == "refusal"])

    def test_without_a_kind_the_current_agent_is_kept(self) -> None:
        log = run(agent="shell", available=["claude", "shell"], sends=[{"text": "ls", "run": True}])
        self.assertEqual(events(log, "open"), [["shell"]])
        self.assertEqual(events(log, "input"), [["s1", "ls"], ["s1", "\r"]])


if __name__ == "__main__":
    unittest.main()
