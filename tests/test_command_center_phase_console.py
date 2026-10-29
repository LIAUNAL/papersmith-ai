"""The phase drawer's console: guided prompts that send the stage's slash
command to an agent, real shell commands, and redirects to the owning panel."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import phase_actions, server

STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
I18N_JS = STATIC / "i18n.js"
EN_JS = STATIC / "i18n" / "en.js"
ES_JS = STATIC / "i18n" / "es.js"

# A minimal DOM: the drawer's inputs and hints, a click dispatcher, and spies
# for sendToCli / navigateTab / filterModelView / closeDrawer.
HARNESS = r"""
const fs = require('fs');
const calls = [];
const els = {};
const listeners = {};
function el(id) { return els[id] || (els[id] = { id, value: '', textContent: '', classList: { add(){}, remove(){} }, focus(){} }); }
let sendResult;
const options = [];
let agents = { current: 'herdr', live: false, agents: [] };
let refusal = '';
const store = { 'papersmith-lang': 'es' };
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
global.window = {
  localStorage: global.localStorage,
  smithTerminalActivity: () => ({ refusal }),
  smithTerminalAgents: async () => agents,
  sendToCli: (t, r, o) => { calls.push(['send', t, r, o && o.kind]); options.push(o); return sendResult; },
  navigateTab: (t) => calls.push(['tab', t]),
  filterModelView: (s) => calls.push(['section', s]),
  closeDrawer: () => calls.push(['close']),
};
global.document = {
  getElementById: el,
  querySelectorAll: () => [],
  addEventListener: (type, fn) => { listeners[type] = fn; },
};
eval(fs.readFileSync(process.argv[2], 'utf8'));
eval(fs.readFileSync(process.argv[3], 'utf8'));
eval(fs.readFileSync(process.argv[4], 'utf8'));
eval(fs.readFileSync(process.argv[1], 'utf8'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
global.localStorage = {
  getItem: (k) => (k === 'papersmith-lang' ? 'es' : (input.remembered ?? null)),
  setItem: () => {}
};
global.window.localStorage = global.localStorage;
sendResult = input.sendResult;
if (input.agents) agents = input.agents;
refusal = input.refusal || '';
if (input.override) el('phaseOverride').checked = true;
(async () => {
const html = window.renderPhaseActions(input.phase);
await new Promise((r) => setTimeout(r, 20));
if (input.pick) el('phaseAgent0').value = input.pick;
if (input.fresh) el('phaseFresh0').checked = true;
function click(i) {
  listeners.click({ target: { closest: () => ({ dataset: { phaseAction: String(i) } }) } });
}
for (const step of input.steps) {
  if (step.type) el('phaseInput' + step.i).value = step.type;
  click(step.i);
  await new Promise((r) => setTimeout(r, 10));
}
console.log(JSON.stringify({ html, calls, options, select: el('phaseAgent0').innerHTML, note: el('phaseAgentNote0').textContent, hints: Object.fromEntries(Object.entries(els).map(([k, v]) => [k, v.textContent])) }));
})();
"""


def run(phase: dict, steps: list[dict], override: bool = False, **extra) -> dict:
    out = subprocess.run(["node", "-e", HARNESS, str(STATIC / "phase-console.js"), str(EN_JS), str(ES_JS), str(I18N_JS)],
                         input=json.dumps({"phase": phase, "steps": steps, "override": override, **extra}),
                         capture_output=True, text=True, cwd=tempfile.gettempdir(), check=True)
    return json.loads(out.stdout)


def phase(stage: str) -> dict:
    return {"stage_id": stage, "actions": phase_actions.ACTIONS[stage]["actions"]}


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PhaseConsoleTests(unittest.TestCase):
    def test_plausibility_shows_its_rules_and_refuses_a_one_sentence_idea(self) -> None:
        result = run(phase("plausibility"), [{"i": 0, "type": "Una sola idea."}])
        self.assertTrue("two sentences" in result["html"] or "dos oraciones" in result["html"])
        self.assertIn('id="phaseInput0"', result["html"])
        self.assertEqual(result["calls"], [])
        self.assertIn("al menos 2 oraciones", result["hints"]["phaseHint0"])

    def test_a_long_idea_written_as_one_run_on_sentence_is_accepted(self) -> None:
        # The operator's own wording: one period-free paragraph with a URL.
        idea = ("Revisa el paper https://www.mdpi.com/2227-7080/14/7/392, con base a esa idea, vamos a "
                "construir un paper en esa misma linea pero utilizando QML hibrido, vas a explorar como "
                "incluir una o par de capas tipo DRU al final, para clasificar tdah desde erg, buscando "
                "aprovechar la capacidad de representación de los QML , enfocándose en un buen rendimiento, "
                "explorar estrategias QML hibridas y preservando interpretabilidad")
        result = run(phase("plausibility"), [{"i": 0, "type": idea}])
        self.assertEqual(result["calls"], [["send", "/plausibility " + idea, True, "slash"]])

    def test_the_drawer_continues_the_open_session_by_default(self) -> None:
        agents = {"current": "pi", "live": True,
                  "agents": [{"id": "claude", "label": "Claude Code"}, {"id": "pi", "label": "Pi"}]}
        idea = "One sentence here. And a second one."
        result = run(phase("plausibility"), [{"i": 0, "type": idea}], agents=agents, remembered="claude")
        self.assertIn('value="pi" selected', result["select"])
        self.assertIn("Continúa en la sesión abierta de Pi", result["note"])
        self.assertEqual(result["options"][0], {"kind": "slash", "agent": "pi", "fresh": False})

    def test_without_a_session_the_last_chosen_agent_is_offered(self) -> None:
        agents = {"current": "herdr", "live": False,
                  "agents": [{"id": "claude", "label": "Claude Code"}, {"id": "opencode", "label": "OpenCode"}]}
        result = run(phase("plausibility"), [], agents=agents, remembered="opencode")
        self.assertIn('value="opencode" selected', result["select"])
        self.assertIn("Abrirá una sesión de OpenCode", result["note"])

    def test_without_history_the_terminal_herdr_session_is_the_default(self) -> None:
        agents = {"current": "herdr", "live": False,
                  "agents": [{"id": "herdr", "label": "Herdr"}, {"id": "claude", "label": "Claude Code"}]}
        idea = "One sentence here. And a second one."
        result = run(phase("plausibility"), [{"i": 0, "type": idea}], agents=agents)
        self.assertIn('value="herdr" selected', result["select"])
        self.assertIn("Abrirá una sesión de Herdr", result["note"])
        self.assertEqual(result["options"][0], {"kind": "slash", "agent": "herdr", "fresh": False})

    def test_without_herdr_the_default_opens_a_new_claude_session(self) -> None:
        agents = {"current": "herdr", "live": False,
                  "agents": [{"id": "opencode", "label": "OpenCode"}, {"id": "claude", "label": "Claude Code"}]}
        result = run(phase("plausibility"), [], agents=agents)
        self.assertIn('value="claude" selected', result["select"])
        self.assertIn("Abrirá una sesión de Claude Code", result["note"])

    def test_the_note_warns_before_closing_the_open_session(self) -> None:
        agents = {"current": "claude", "live": True,
                  "agents": [{"id": "claude", "label": "Claude Code"}, {"id": "pi", "label": "Pi"}]}
        idea = "One sentence here. And a second one."
        result = run(phase("plausibility"), [{"i": 0, "type": idea}], agents=agents, pick="pi")
        self.assertIn("Cerrará la sesión de Claude Code y abrirá Pi", result["note"])
        result = run(phase("plausibility"), [{"i": 0, "type": idea}], agents=agents, fresh=True)
        self.assertIn("Cerrará la sesión de Claude Code y abrirá una nueva", result["note"])

    def test_a_new_session_is_requested_only_when_ticked(self) -> None:
        agents = {"current": "claude", "live": True, "agents": [{"id": "claude", "label": "Claude Code"}]}
        idea = "One sentence here. And a second one."
        result = run(phase("plausibility"), [{"i": 0, "type": idea}], agents=agents, fresh=True)
        self.assertEqual(result["options"][0], {"kind": "slash", "agent": "claude", "fresh": True})

    def test_a_folder_trust_question_is_named_in_the_drawer(self) -> None:
        idea = "One sentence here. And a second one."
        result = run(phase("plausibility"), [{"i": 0, "type": idea}], sendResult=False, refusal="trust")
        self.assertIn("Yes, I trust this folder", result["hints"]["phaseError0"])
        result = run(phase("plausibility"), [{"i": 0, "type": idea}], sendResult=False, refusal="question")
        self.assertIn("espera una confirmación", result["hints"]["phaseError0"])

    def test_a_refusal_is_shown_in_a_visible_error_box(self) -> None:
        result = run(phase("plausibility"), [{"i": 0, "type": "Una sola idea."}])
        self.assertIn('id="phaseError0"', result["html"])
        self.assertIn("al menos 2 oraciones", result["hints"]["phaseError0"])

    def test_plausibility_sends_the_idea_as_one_slash_command_line(self) -> None:
        idea = "EEG models fail across subjects.\nI propose a quantum kernel."
        result = run(phase("plausibility"), [{"i": 0, "type": idea}])
        self.assertEqual(result["calls"], [[
            "send", "/plausibility EEG models fail across subjects. I propose a quantum kernel.", True, "slash"]])

    def test_a_prefixed_prompt_and_an_optional_one(self) -> None:
        result = run(phase("declarations"), [{"i": 0, "type": "idioma: inglés"}])
        self.assertEqual(result["calls"][0][1], "/paper-writing mark idioma: inglés")
        result = run(phase("harness"), [{"i": 2}])
        self.assertEqual(result["calls"], [["send", "/upgrade-project", True, "slash"]])

    def test_a_required_prompt_left_empty_sends_nothing(self) -> None:
        result = run(phase("writing"), [{"i": 0}])
        self.assertEqual(result["calls"], [])
        self.assertIn("Escribe lo que pide la guía", result["hints"]["phaseHint0"])

    def test_commands_run_in_the_shell_and_placeholders_are_only_typed(self) -> None:
        result = run(phase("harness"), [{"i": 0}])
        self.assertEqual(result["calls"], [["send", "smith status .", True, "shell"]])
        result = run(phase("ingestion"), [{"i": 1}])
        self.assertEqual(result["calls"], [["send", "smith ingest <path-or-url> .", False, "shell"]])

    def test_the_concept_map_redirect_opens_its_section(self) -> None:
        result = run(phase("proposal"), [{"i": 1}])
        self.assertEqual(result["calls"], [["close"], ["tab", "modelo"], ["section", "mapa"]])

    def test_phase_text_is_escaped(self) -> None:
        hostile = {"actions": [{"kind": "redirect", "label": "<img src=x onerror=alert(1)>",
                                "tab": "atlas", "section": "", "desc": "\"><script>"}]}
        html = run(hostile, [])["html"]
        self.assertNotIn("<img", html)
        self.assertNotIn("<script>", html)

    def test_a_locked_phase_runs_only_with_the_override(self) -> None:
        locked = dict(phase("plausibility"), unlocked=False, blocked_by="Fase 1")
        idea = "One sentence here. And a second one."
        result = run(locked, [{"i": 0, "type": idea}])
        self.assertIn("Bloqueada: requiere Fase 1", result["html"])
        self.assertEqual(result["calls"], [])
        self.assertIn("primero verifica Fase 1", result["hints"]["phaseHint0"])
        result = run(locked, [{"i": 0, "type": idea}], override=True)
        self.assertEqual(result["calls"][0][1], "/plausibility " + idea)

    def test_a_phase_without_actions_renders_nothing(self) -> None:
        self.assertEqual(run({"actions": []}, [])["html"], "")


class PageWiringTests(unittest.TestCase):
    def test_drawer_clicks_reach_the_phase_handlers(self) -> None:
        # The drawer stops click propagation, so a bubbling document listener
        # never sees "Ejecutar": both scripts must listen in the capture phase.
        self.assertIn('<div class="drawer" onclick="event.stopPropagation()">', PAGE)
        for name in ("phase-console.js", "phase-run.js"):
            script = (STATIC / name).read_text(encoding="utf-8")
            start = script.index("document.addEventListener('click', (event) => {")
            self.assertIn("}, true);", script[start:start + 2500], name)

    def test_the_drawer_renders_the_phase_actions(self) -> None:
        self.assertIn('<script src="./phase-console.js?v=', PAGE)
        self.assertIn("window.renderPhaseActions ? window.renderPhaseActions(p) : ''", PAGE)
        self.assertNotIn("smith run --stage", PAGE)

    def test_slash_commands_switch_the_terminal_to_an_agent(self) -> None:
        script = (STATIC / "cli-console.js").read_text(encoding="utf-8")
        self.assertIn("const SLASH_AGENTS = ['herdr', 'claude', 'opencode', 'pi', 'antigravity'];", script)
        self.assertIn("async function sendToCli(text, run, options)", script)
        # A startup question (folder trust) is never answered by the command's Enter.
        self.assertIn("const STARTUP_QUESTIONS = /trust this folder|Do you trust|Enter to confirm/i;", script)
        self.assertIn("if (kind === 'slash' && STARTUP_QUESTIONS.test(screenText()))", script)


if __name__ == "__main__":
    unittest.main()
