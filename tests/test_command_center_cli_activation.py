"""A dashboard page without the terminal cookie (an old tab, a bookmark, a
server restarted since its login) activates itself on a click: it asks the
server to reopen its login URL, waits for the cookie, and only then opens the
agent session. Runs the real cli-console.js in node with a stub DOM, xterm,
fetch and EventSource."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import server

SCRIPT = Path(server.__file__).resolve().parent / "static" / "cli-console.js"

HARNESS = r"""
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync(0, 'utf8'));
const log = [];
const els = {};
function el(id) {
  if (!els[id]) {
    const cls = new Set();
    els[id] = { id, value: '', textContent: '', dataset: {}, disabled: false, innerHTML: '', style: {},
      classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c), contains: (c) => cls.has(c),
                   toggle: (c) => (cls.has(c) ? cls.delete(c) : cls.add(c)) },
      setAttribute() {}, addEventListener(t, fn) { this['on_' + t] = fn; }, appendChild() {}, append() {}, focus() {},
      remove() { log.push(['bannerRemoved', this.id]); delete els[this.id]; } };
  }
  return els[id];
}
const store = { smith_terminal_agent: 'claude' };
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; },
                        removeItem: (k) => { delete store[k]; } };
const docListeners = {};
let created = 0;
global.document = {
  getElementById: (id) => els[id] || (id === 'cliActivationBanner' ? null : el(id)),
  createElement: (tag) => { created += 1; return Object.assign(el('x' + created), { tag }); },
  addEventListener: (t, fn) => { docListeners[t] = fn; },
  // The banner is found by the id the script gives it once it is shown.
  body: { appendChild(node) { log.push(['banner', node.id]); els[node.id] = node; } },
};
global.ResizeObserver = class { observe() {} };
if (cfg.pageOrigin) global.location = { origin: cfg.pageOrigin, host: cfg.pageOrigin.split('//')[1] };
// The cookie arrives `cfg.authorizeAfter` agents polls after the activation.
let activated = false;
let pollsSinceActivation = 0;
let sessions = 0;
global.fetch = async (path, opts = {}) => {
  const method = opts.method || 'GET';
  const body = opts.body ? JSON.parse(opts.body) : undefined;
  let data = {};
  let ok = true;
  if (path === '/api/terminal/agents') {
    if (activated) pollsSinceActivation += 1;
    const authorized = activated && cfg.authorizeAfter !== null && pollsSinceActivation >= cfg.authorizeAfter;
    data = { enabled: true, authorized, network: Boolean(cfg.network), default: 'claude', quick: {},
             agents: authorized ? ['claude', 'shell'].map((id) => ({ id, label: id, available: true })) : [] };
  } else if (path === '/api/terminal/activate' && method === 'POST') {
    // `activated` also stands for the operator opening the printed login
    // link in another tab, which is how a refused (network bind) page gets in.
    activated = true;
    log.push(['activate', opts.headers['X-Papersmith-Terminal']]);
    if (cfg.refuseActivation) {
      ok = false;
      data = { detail: 'refused: on a network bind, open the login URL smith ui printed when it started' };
    } else {
      data = { ok: true, opened: cfg.opened !== false, origin: 'http://127.0.0.1:8080' };
    }
  } else if (path === '/api/terminal/login' && method === 'POST') {
    log.push(['login', body.token, opts.headers['X-Papersmith-Terminal']]);
    if (body.token === cfg.secret) { activated = true; data = { ok: true }; }
    else { ok = false; data = { detail: 'invalid terminal token' }; }
  } else if (path === '/api/terminal/tools') {
    data = { tools: { ready: true, preferred_terminal: 'ghostty', missing: [] } };
  } else if (path === '/api/terminal/sessions' && method === 'POST') {
    sessions += 1; data = { id: 's' + sessions }; log.push(['open', body.agent]);
  } else if (path.endsWith('/input')) {
    if ('data' in body) log.push(['input', path.split('/')[4], body.data]);
  } else if (method === 'DELETE') {
    log.push(['close', path.split('/')[4]]);
  } else if (/^\/api\/terminal\/sessions\/[^/]+$/.test(path)) {
    ok = false; data = { detail: 'no such session' };
  }
  return { ok, status: ok ? 200 : 404, json: async () => data };
};
global.EventSource = class {
  constructor(url) {
    this.l = {};
    this.sid = url.split('/')[4];
    log.push(['stream', this.sid]);
    setTimeout(() => {
      if (this.closed) return;
      this.onopen && this.onopen();
      this.l.output && this.l.output({ data: JSON.stringify({ payload: { data: '' } }) });
    }, 10);
  }
  addEventListener(t, fn) { this.l[t] = fn; }
  close() { this.closed = true; }
};
global.window = {
  i18n: { t: (key, vars) => key + (vars ? ' ' + JSON.stringify(vars) : '') },
  confirm: () => true,
  addEventListener() {},
  phaseRuns: { anyRunning: () => false },
  Terminal: class {
    constructor() { this.cols = 80; this.rows = 3; this.buffer = { active: { viewportY: 0, getLine: () => ({ translateToString: () => '' }) } }; }
    loadAddon() {} open() {} onData() {} onResize() {} write() {} focus() {} clear() {} reset() {}
  },
};
eval(fs.readFileSync(process.argv[1], 'utf8'));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  docListeners.DOMContentLoaded();
  await wait(100);
  const out = {};
  if (cfg.action === 'fab') {
    window.toggleSmithTerminal();
    await wait(cfg.waitMs);
  } else if (cfg.action === 'login') {
    window.toggleSmithTerminal();
    await wait(300);
    out.form = Boolean(els.cliActivationBanner);
    for (const typed of cfg.typed) {
      const box = Object.values(els).find((e) => e.type === 'password');
      if (!box || !els.cliActivationBanner) break;
      box.value = typed;
      els.cliActivationBanner.on_submit({ preventDefault() {} });
      await wait(400);
    }
  } else if (cfg.action === 'phase') {
    out.sent = await window.sendToCli('/plausibility idea', true, { kind: 'slash' });
    await wait(400);
  }
  out.activity = window.smithTerminalActivity();
  out.status = els.terminalStatusText ? els.terminalStatusText.textContent : null;
  out.log = log;
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""


def run(**cfg) -> dict:
    cfg.setdefault("authorizeAfter", 1)
    cfg.setdefault("waitMs", 3000)
    done = subprocess.run(["node", "-e", HARNESS, str(SCRIPT)], input=json.dumps(cfg),
                          capture_output=True, text=True, cwd=tempfile.gettempdir(),
                          timeout=60, check=True)
    return json.loads(done.stdout)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class CliActivationTests(unittest.TestCase):
    def test_the_fab_click_activates_an_unauthorized_page_and_opens_the_agent(self) -> None:
        out = run(action="fab")
        log = out["log"]
        self.assertIn(["activate", "1"], log)
        self.assertIn(["open", "claude"], log)
        self.assertLess(log.index(["activate", "1"]), log.index(["open", "claude"]))
        self.assertIn(["bannerRemoved", "cliActivationBanner"], log)
        self.assertEqual(out["activity"]["sessionId"], "s1")

    def test_a_phase_run_activates_the_page_and_types_its_command(self) -> None:
        out = run(action="phase")
        self.assertTrue(out["sent"])
        log = out["log"]
        self.assertIn(["activate", "1"], log)
        self.assertIn(["open", "claude"], log)
        self.assertIn(["input", "s1", "/plausibility idea"], log)

    def test_no_session_opens_while_the_cookie_has_not_arrived(self) -> None:
        out = run(action="fab", authorizeAfter=None, waitMs=2000)
        log = out["log"]
        self.assertEqual([entry for entry in log if entry[0] == "activate"], [["activate", "1"]])
        self.assertNotIn("open", [entry[0] for entry in log])
        self.assertIsNone(out["activity"]["sessionId"])

    def test_a_page_under_another_host_name_is_told_where_the_terminal_opens(self) -> None:
        out = run(action="fab", pageOrigin="http://localhost:8080", waitMs=1500)
        log = out["log"]
        self.assertIn(["activate", "1"], log)
        self.assertNotIn("open", [entry[0] for entry in log])
        # "Could not open: the agent terminal opens at http://127.0.0.1:8080 …"
        self.assertIn("cli.openFailed", out["status"])
        self.assertIn("cli.activatedElsewhere", out["status"])
        self.assertIn("http://127.0.0.1:8080", out["status"])

    def test_loading_the_page_never_activates_on_its_own(self) -> None:
        out = run(action=None)
        self.assertNotIn("activate", [entry[0] for entry in out["log"]])

    def test_a_network_bind_refuses_activation_and_the_page_points_at_the_printed_link(self) -> None:
        # smith ui --network-terminal answers 403 to the self-activation: the
        # page says to open the printed login link and opens nothing meanwhile.
        out = run(action="fab", refuseActivation=True, authorizeAfter=None, waitMs=1500)
        log = out["log"]
        self.assertIn(["activate", "1"], log)
        self.assertNotIn("open", [entry[0] for entry in log])
        self.assertIn("cli.activatePrinted", out["status"])

    def test_the_refused_page_opens_the_agent_once_the_printed_link_was_used(self) -> None:
        out = run(action="fab", refuseActivation=True, authorizeAfter=2)
        self.assertIn(["open", "claude"], out["log"])
        self.assertEqual(out["activity"]["sessionId"], "s1")


    def test_a_network_page_asks_for_the_secret_instead_of_activating(self) -> None:
        # smith ui --lan: no browser on this device can be opened by the
        # server, so the page shows a password box and never posts activate.
        out = run(action="login", network=True, secret="s" * 43, typed=[], authorizeAfter=0)
        self.assertTrue(out["form"])
        self.assertNotIn("activate", [entry[0] for entry in out["log"]])
        self.assertNotIn("open", [entry[0] for entry in out["log"]])
        self.assertIn("cli.loginNeeded", out["status"])

    def test_the_pasted_secret_logs_in_and_opens_the_agent(self) -> None:
        secret = "s" * 43
        out = run(action="login", network=True, secret=secret, typed=["wrong", f"  {secret}\n"],
                  authorizeAfter=0)
        logins = [entry for entry in out["log"] if entry[0] == "login"]
        self.assertEqual(logins, [["login", "wrong", "1"], ["login", secret, "1"]])
        self.assertIn(["bannerRemoved", "cliActivationBanner"], out["log"])
        self.assertIn(["open", "claude"], out["log"])
        self.assertEqual(out["activity"]["sessionId"], "s1")
        self.assertNotIn("activate", [entry[0] for entry in out["log"]])


if __name__ == "__main__":
    unittest.main()
