"""The Doctor tab's API keys panel, rendered under node with a minimal DOM.

The panel asks for the Asta and OpenAlex keys: a password input per provider,
the request links and Asta's license notice, and a status badge read from
`GET /api/terminal/keys`, which never carries a key. Saving sends one PUT with
the terminal's headers and clears the input before the request returns.
Elsewhere in the page, `[data-keys-prompt]` placeholders ask for a missing key.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from papersmith import __version__

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "skills" / "_core" / "command_center" / "static"
PANEL = STATIC / "keys-panel.js"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")

ALLOWED_TAGS = {"div", "span", "strong", "a", "p", "code", "details", "summary", "form", "label",
                "input", "button"}

PRELUDE = r"""
const fs = require('fs');
const store = {};
global.window = global;
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
const node = (extra) => Object.assign({ innerHTML: '', hidden: true, dataset: {}, value: '',
  querySelectorAll: () => [], addEventListener() {}, focus() {} }, extra || {});
const panel = node({ id: 'keysPanel' });
const inputs = { asta: node({ value: '' }), openalex: node({ value: '' }) };
const prompts = [node({ dataset: { keysPrompt: 'asta' } }), node({ dataset: { keysPrompt: 'openalex' } })];
global.document = { readyState: 'complete', body: null,
  querySelectorAll: (sel) => (sel === '[data-keys-prompt]' ? prompts : []),
  addEventListener() {},
  getElementById: (id) => (id === 'keysPanel' ? panel : id.startsWith('keysInput-') ? inputs[id.slice(10)]
    : id.startsWith('keysResult-') ? (global.__results[id] = global.__results[id] || node()) : null) };
global.__results = {};
global.__routes = [];
const calls = [];
global.fetch = async (url, init) => {
  const method = (init && init.method) || 'GET';
  calls.push({ url, method, headers: init && init.headers, body: init && init.body,
               inputAtSend: Object.fromEntries(Object.entries(inputs).map(([k, v]) => [k, v.value])) });
  const route = global.__routes.find((r) => r[0] === method && url.startsWith(r[1]));
  const reply = route ? route[2] : { status: 404, body: {} };
  return { ok: reply.status < 400, status: reply.status, json: async () => reply.body };
};
global.confirm = () => true;
const sent = [];
global.sendToCli = async (text, run, options) => { sent.push({ text, run, options }); return true; };
const out = (value) => console.log(JSON.stringify(value));
const tick = () => new Promise((r) => setTimeout(r, 0));
"""


def state(provider: str, **overrides) -> dict:
    base = {"provider": provider, "label": provider, "unlocks": "", "env": f"{provider.upper()}_API_KEY",
            "configured": False, "source": "none", "stored": False, "shadowed": False, "problem": None,
            "env_problem": None, "path": f"/home/u/.config/papersmith/keys/{provider}", "override": False,
            "request_url": {"asta": "https://share.hsforms.com/1L4hUh20oT3mu8iXJQMV77w3ioxm",
                            "openalex": "https://openalex.org/settings/api-key"}[provider],
            "license_url": "https://allenai.org/asta-corpus-license" if provider == "asta" else "",
            "license": "", "export_command": f'export {provider.upper()}_API_KEY="$(cat "/x/{provider}")"'}
    base.update(overrides)
    return base


def payload(*states: dict, sessions: int = 0) -> dict:
    return {"ok": True, "store_dir": "/home/u/.config/papersmith/keys", "override": False,
            "environment": {"shell": "bash"}, "keys": list(states), "sessions_open": sessions}


@unittest.skipUnless(shutil.which("node"), "node is required to run the panel")
class KeysPanelTests(unittest.TestCase):
    def node(self, body: str, *, routes: list | None = None, lang: str = "en", prefix: str = ""):
        """Run ``body`` after the panel loaded. Order matters: the fakes, the
        routes and ``prefix`` exist before the panel's own load-time GET."""
        files = "".join(f"eval(fs.readFileSync({json.dumps(str(path))}, 'utf8'));"
                        for path in (STATIC / "i18n" / "en.js", STATIC / "i18n" / "es.js",
                                     STATIC / "i18n.js", PANEL))
        script = (PRELUDE + f"global.__routes.push(...{json.dumps(routes or [])});\n" + prefix + "\n"
                  + files + f"window.i18n.setLanguage({json.dumps(lang)});\n"
                  + "(async () => { await tick(); await tick();" + body
                  + "})().catch((error) => { console.error(error); process.exit(1); });")
        done = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                              cwd=tempfile.gettempdir(), check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def assert_only_known_markup(self, html: str) -> None:
        tags = set(re.findall(r"</?([a-zA-Z][a-zA-Z0-9]*)", html))
        self.assertLessEqual(tags, ALLOWED_TAGS, f"unexpected tags: {tags - ALLOWED_TAGS}")
        for href in re.findall(r'href="([^"]*)"', html):
            self.assertRegex(href, r"^https://", href)

    def test_both_providers_render_with_password_inputs_links_and_the_license(self) -> None:
        routes = [["GET", "/api/terminal/keys", {"status": 200, "body": payload(state("asta"), state("openalex"))}]]
        html = self.node("out(panel.innerHTML);", routes=routes)
        self.assert_only_known_markup(html)
        assert html.count('type="password"') == 2
        assert 'autocomplete="off"' in html and 'maxlength="512"' in html
        for text in ("Asta (Ai2)", "OpenAlex", "Not configured", "Request a key ↗",
                     "https://share.hsforms.com/1L4hUh20oT3mu8iXJQMV77w3ioxm",
                     "https://openalex.org/settings/api-key", "https://allenai.org/asta-corpus-license",
                     "academic and non-commercial use only", "Set in terminal"):
            assert text in html, text
        # Verify and Remove wait for something to verify or remove.
        assert re.search(r'data-keys-verify="asta" disabled', html)
        assert re.search(r'data-keys-remove="asta" disabled', html)

    def test_each_state_has_its_badge(self) -> None:
        routes = [["GET", "/api/terminal/keys", {"status": 200, "body": payload(
            state("asta", configured=True, source="env", stored=True, shadowed=True),
            state("openalex", problem="insecure: mode 0644, expected 0600"))}]]
        html = self.node("out(panel.innerHTML);", routes=routes, lang="es")
        assert "Guardada, pero gana la ASTA_API_KEY exportada" in html
        assert "Archivo guardado ignorado (insecure: mode 0644, expected 0600)" in html
        routes[0][2]["body"] = payload(state("asta", configured=True, source="store", stored=True),
                                       state("openalex", configured=True, source="env"))
        html = self.node("out(panel.innerHTML);", routes=routes)
        assert "Stored" in html and "Exported as OPENALEX_API_KEY" in html
        assert "Outside the dashboard" in html and 'export ASTA_API_KEY=' in html

    def test_saving_sends_one_put_and_clears_the_input_before_it_leaves(self) -> None:
        stored = payload(state("asta", configured=True, source="store", stored=True), state("openalex"))
        routes = [["PUT", "/api/terminal/keys/asta", {"status": 200, "body": {
                       "ok": True, "status": stored["keys"][0], "verify": None, "sessions_open": 1}}],
                  ["GET", "/api/terminal/keys", {"status": 200, "body": stored}]]
        result = self.node("""
          inputs.asta.value = 'asta-key-0123456789abcdef';
          await KeysPanel.save('asta', false);
          out({ calls, input: inputs.asta.value, html: panel.innerHTML,
                result: __results['keysResult-asta'] && __results['keysResult-asta'].textContent });""",
                           routes=routes)
        put = [call for call in result["calls"] if call["method"] == "PUT"]
        assert len(put) == 1
        assert put[0]["headers"] == {"Content-Type": "application/json", "X-Papersmith-Terminal": "1"}
        assert json.loads(put[0]["body"]) == {"value": "asta-key-0123456789abcdef", "verify": False}
        assert put[0]["inputAtSend"]["asta"] == ""  # cleared before the request left
        assert result["input"] == ""
        assert "asta-key-0123456789abcdef" not in result["html"]
        assert "Sessions started from now on get ASTA_API_KEY" in result["result"]

    def test_an_empty_input_sends_nothing(self) -> None:
        routes = [["GET", "/api/terminal/keys", {"status": 200, "body": payload(state("asta"), state("openalex"))}]]
        result = self.node("await KeysPanel.save('asta', true); out(calls.map((c) => c.method));", routes=routes)
        assert result == ["GET"]

    def test_the_asta_card_says_where_agents_reach_the_server(self) -> None:
        body = payload(state("asta"), state("openalex"))
        body["asta_mcp"] = {"server": "asta", "registered": [".mcp.json", "opencode.json"]}
        html = self.node("out(panel.innerHTML);", routes=[["GET", "/api/terminal/keys", {"status": 200, "body": body}]])
        assert "registered in: .mcp.json, opencode.json" in html
        body["asta_mcp"]["registered"] = []
        html = self.node("out(panel.innerHTML);", routes=[["GET", "/api/terminal/keys", {"status": 200, "body": body}]])
        assert "run smith upgrade" in html

    def test_a_refused_route_says_to_use_the_terminal(self) -> None:
        routes = [["GET", "/api/terminal/keys", {"status": 403, "body": {"detail": "refused"}}]]
        html = self.node("out(panel.innerHTML);", routes=routes)
        assert "smith keys set asta" in html and "smith keys set openalex" in html

    def test_prompts_ask_only_for_a_missing_key_until_dismissed(self) -> None:
        routes = [["GET", "/api/terminal/keys", {"status": 200, "body": payload(
            state("asta"), state("openalex", configured=True, source="store", stored=True))}]]
        result = self.node("out(prompts.map((p) => [p.hidden, p.innerHTML]));", routes=routes)
        (asta_hidden, asta_html), (alex_hidden, alex_html) = result
        assert asta_hidden is False and "Doctor → API keys" in asta_html and "Asta" in asta_html
        assert alex_hidden is True and alex_html == ""
        result = self.node("out(prompts.map((p) => p.hidden));", routes=routes,
                           prefix="store['papersmith-keys-dismissed:asta'] = '1';")
        assert result == [True, True]

    def test_a_snapshot_renders_nothing_and_calls_nothing(self) -> None:
        result = self.node("out({ calls, panel: typeof window.KeysPanel });",
                           prefix="window.PAPERSMITH_SNAPSHOT_MANIFEST = { entries: {} };")
        assert result == {"calls": [], "panel": "undefined"}


class PageWiringTests(unittest.TestCase):
    def test_the_page_loads_the_panel_inside_the_doctor_tab(self) -> None:
        assert f'<script src="./keys-panel.js?v={__version__}"></script>' in PAGE
        doctor = PAGE.index('id="pane-doctor"')
        assert doctor < PAGE.index('id="keysCard"') < PAGE.index('id="doctorPanel"')
        assert "window.refreshKeysPanel?.();" in PAGE

    def test_a_snapshot_hides_every_key_control(self) -> None:
        snapshot = (STATIC / "snapshot.js").read_text(encoding="utf-8")
        for selector in ("'#keysCard'", "'[data-keys-prompt]'", "'[data-keys-terminal]'"):
            assert selector in snapshot, selector

    def test_the_plausibility_card_and_the_journals_panel_carry_a_prompt(self) -> None:
        console = (STATIC / "phase-console.js").read_text(encoding="utf-8")
        assert "a.slash === '/plausibility'" in console and 'data-keys-prompt="asta"' in console
        journals = (STATIC / "journals-panel.js").read_text(encoding="utf-8")
        assert 'data-keys-prompt="openalex"' in journals


if __name__ == "__main__":
    unittest.main()
