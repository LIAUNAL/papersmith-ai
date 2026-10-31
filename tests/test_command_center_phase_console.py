"""The phase drawer's console: guided prompts that send the stage's slash
command to an agent, real shell commands, and redirects to the owning panel."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

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
// Assigning innerHTML that holds the proposal's <textarea id="kwDraftN"> creates that
// field with the unescaped text, as a browser would.
function el(id) {
  return els[id] || (els[id] = {
    id, value: '', textContent: '', _html: '', hidden: false, disabled: false, classList: { add(){}, remove(){} }, focus(){},
    get innerHTML() { return this._html; },
    set innerHTML(v) {
      this._html = v;
      const m = /<textarea[^>]*id="(kwDraft\d+)"[^>]*>([\s\S]*?)<\/textarea>/.exec(v);
      if (m) el(m[1]).value = m[2].replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
    },
  });
}
const fetches = [];
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
global.window.fetch = async (url, init) => {
  fetches.push([url, JSON.parse(init.body)]);
  if (input.fetchError) throw new Error(input.fetchError);
  const r = input.fetchResponse || { status: 200, body: {} };
  return { ok: r.status < 400, status: r.status, json: async () => r.body };
};
if (input.agents) agents = input.agents;
refusal = input.refusal || '';
if (input.override) el('phaseOverride').checked = true;
(async () => {
const html = window.renderPhaseActions(input.phase);
await new Promise((r) => setTimeout(r, 20));
if (input.pick) el('phaseAgent0').value = input.pick;
if (input.fresh) el('phaseFresh0').checked = true;
function click(i) {
  listeners.click({ target: { closest: (sel) => (sel.includes('data-kw-help') ? null : { dataset: { phaseAction: String(i) } }) } });
}
for (const step of input.steps) {
  if (step.kw) {
    step.kw.forEach((word, n) => { el('kwInput' + step.i + '_' + n).value = word; });
    listeners.input({ target: { closest: () => ({ dataset: { kwInput: String(step.i) } }) } });
  }
  if (step.draft !== undefined) el('kwDraft' + step.i).value = step.draft;
  if (step.type) el('phaseInput' + step.i).value = step.type;
  if (step.help) {
    listeners.click({ target: { closest: (sel) => (sel.includes('data-kw-help') ? { dataset: { kwHelp: step.help, kwIndex: String(step.i) } } : null) } });
  } else if (!step.kw) click(step.i);
  await new Promise((r) => setTimeout(r, 10));
}
console.log(JSON.stringify({ html, calls, options, fetches, select: el('phaseAgent0').innerHTML, note: el('phaseAgentNote0').textContent, hints: Object.fromEntries(Object.entries(els).map(([k, v]) => [k, v.textContent])), els: Object.fromEntries(Object.entries(els).map(([k, v]) => [k, { value: v.value, textContent: v.textContent, innerHTML: v.innerHTML, hidden: v.hidden, disabled: v.disabled }])) }));
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


SUGGESTION = {
    "available": True, "keywords": ["eeg", "quantum", "classification"], "match": "any",
    "items": [
        {"id": "A023", "kind": "articulo", "title": "Quantum <img src=x onerror=alert(1)> EEG", "year": 2025,
         "cluster": "C05", "doi": "10.3390/computers14110475", "score": 11.48, "snippet": "…[quantum]…"},
        {"id": "H0042", "kind": "proyecto", "title": "Interfaz cerebro-computador", "year": 2020,
         "cluster": "C02", "doi": "", "score": 4.2, "snippet": ""},
    ],
    "topics": [{"id": "C05", "name": "Quantum <b>ML</b>", "count": 1}, {"id": "C02", "name": "Señales", "count": 1}],
    "draft": "Propongo explorar EEG y quantum. Parto del proyecto H0042 como antecedente. La idea probaría algo nuevo.",
}
KEYWORDS = ["eeg", "quantum", "classification"]


def suggest(steps: list[dict], status: int = 200, body: dict | None = None, **extra) -> dict:
    response = {"status": status, "body": SUGGESTION if body is None else body}
    return run(phase("plausibility"), steps, fetchResponse=response, **extra)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ThematicHelpTests(unittest.TestCase):
    def test_only_the_plausibility_card_gets_the_help_block(self) -> None:
        html = run(phase("plausibility"), [])["html"]
        self.assertIn('id="kwHelp0"', html)
        self.assertIn("Ayuda temática (palabras clave)", html)
        for stage in ("harness", "ingestion", "proposal", "declarations", "writing"):
            self.assertNotIn("kwHelp", run(phase(stage), [])["html"], stage)
        flagged = [(stage, a["label"]) for stage, spec in phase_actions.ACTIONS.items()
                   for a in spec["actions"] if a.get("keyword_help")]
        self.assertEqual(flagged, [("plausibility", "Explore the plausibility of the idea")])

    def test_the_guide_mentions_the_help_and_the_block_is_collapsible(self) -> None:
        guide = " ".join(phase_actions.ACTIONS["plausibility"]["actions"][0]["guide"])
        self.assertIn("Thematic help", guide)
        html = run(phase("plausibility"), [])["html"]
        self.assertRegex(html, r'<details class="kw-help"[^>]*id="kwHelp0"|<details[^>]*id="kwHelp0"')
        self.assertIn("<summary>", html)

    def test_three_inputs_show_and_two_more_open_up_to_five(self) -> None:
        html = run(phase("plausibility"), [])["html"]
        for n in range(5):
            self.assertIn(f'id="kwInput0_{n}"', html)
        for n in (3, 4):
            self.assertRegex(html, rf'<input[^>]*id="kwInput0_{n}"[^>]*hidden')
        for n in (0, 1, 2):
            self.assertNotRegex(html, rf'<input[^>]*id="kwInput0_{n}"[^>]*hidden')
        self.assertIn('maxlength="40"', html)
        self.assertIn('id="kwAdd0"', html)
        self.assertRegex(html, r'<button[^>]*id="kwPropose0"[^>]*disabled')

    def test_the_button_is_disabled_under_three_distinct_keywords(self) -> None:
        for words, disabled in ((["eeg", "quantum"], True), (["eeg", "quantum", "svm"], False),
                                (["eeg", "EEG", "quantum"], True), (["eeg", " ", "quantum"], True),
                                (["a", "b", "c", "d", "e"], False)):
            with self.subTest(words=words):
                result = suggest([{"i": 0, "kw": words}])
                self.assertIs(result["els"]["kwPropose0"]["disabled"], disabled)

    def test_proposing_with_too_few_keywords_calls_nothing(self) -> None:
        result = suggest([{"i": 0, "kw": ["eeg", "quantum"]}, {"i": 0, "help": "propose"}])
        self.assertEqual(result["fetches"], [])
        self.assertEqual(result["calls"], [])

    def test_the_plus_button_reveals_the_next_input(self) -> None:
        result = suggest([{"i": 0, "help": "add"}, {"i": 0, "help": "add"}, {"i": 0, "help": "add"}])
        self.assertIs(result["els"]["kwInput0_3"]["hidden"], False)
        self.assertIs(result["els"]["kwInput0_4"]["hidden"], False)
        self.assertIs(result["els"]["kwAdd0"]["hidden"], True)

    def test_a_response_renders_items_topics_and_the_draft_escaped(self) -> None:
        result = suggest([{"i": 0, "kw": KEYWORDS}, {"i": 0, "help": "propose"}])
        self.assertEqual(result["fetches"], [["/api/plausibility/suggest", {"keywords": KEYWORDS, "language": "es"}]])
        shown = result["els"]["kwResult0"]
        self.assertIs(shown["hidden"], False)
        html = shown["innerHTML"]
        self.assertNotIn("<img", html)
        self.assertNotIn("<b>", html)
        self.assertIn("&lt;img", html)
        self.assertIn("Quantum &lt;b&gt;ML&lt;/b&gt;", html)
        self.assertIn("Señales", html)
        self.assertIn("2025", html)
        self.assertIn("11.48", html)
        self.assertIn("Artículo", html)
        self.assertIn("Proyecto", html)
        self.assertIn('href="https://doi.org/10.3390/computers14110475"', html)
        self.assertEqual(html.count("doi.org"), 1)
        self.assertIn('id="kwDraft0"', html)
        self.assertIn("Propongo explorar EEG y quantum.", html)
        self.assertIn("no estado del arte", html)
        self.assertIn('data-kw-help="approve"', html)
        self.assertIn('data-kw-help="discard"', html)

    def test_a_hostile_draft_and_doi_are_inert(self) -> None:
        body = dict(SUGGESTION, draft='Idea </textarea><script>alert(1)</script>. Segunda oración.')
        body["items"] = [dict(SUGGESTION["items"][0], doi='"><script>alert(2)</script>')]
        html = suggest([{"i": 0, "kw": KEYWORDS}, {"i": 0, "help": "propose"}], body=body)["els"]["kwResult0"]["innerHTML"]
        self.assertNotIn("<script>", html)
        self.assertNotIn("</textarea><", html)

    def test_nothing_is_launched_until_the_operator_approves(self) -> None:
        result = suggest([{"i": 0, "kw": KEYWORDS}, {"i": 0, "help": "propose"}])
        self.assertEqual(result["calls"], [])
        self.assertEqual(result["els"].get("phaseInput0", {}).get("value", ""), "")

    def test_approve_fills_the_prompt_and_goes_through_the_run_path(self) -> None:
        edited = "Mi versión editada del problema. Y lo que propongo con QML híbrido."
        result = suggest([{"i": 0, "kw": KEYWORDS}, {"i": 0, "help": "propose"},
                          {"i": 0, "draft": edited, "help": "approve"}])
        self.assertEqual(result["els"]["phaseInput0"]["value"], edited)
        self.assertEqual(result["calls"], [["send", "/plausibility " + edited, True, "slash"]])
        self.assertEqual(result["options"][-1]["kind"], "slash")

    def test_approve_uses_the_selected_agent_like_the_run_button(self) -> None:
        agents = {"current": "pi", "live": True,
                  "agents": [{"id": "claude", "label": "Claude Code"}, {"id": "pi", "label": "Pi"}]}
        result = suggest([{"i": 0, "kw": KEYWORDS}, {"i": 0, "help": "propose"}, {"i": 0, "help": "approve"}],
                         agents=agents, pick="claude")
        self.assertEqual(result["options"][-1], {"kind": "slash", "agent": "claude", "fresh": False})
        self.assertEqual(result["calls"][0][1], "/plausibility " + SUGGESTION["draft"])

    def test_the_sentence_check_still_applies_to_an_edited_draft(self) -> None:
        result = suggest([{"i": 0, "kw": KEYWORDS}, {"i": 0, "help": "propose"},
                          {"i": 0, "draft": "Una sola idea.", "help": "approve"}])
        self.assertEqual(result["calls"], [])
        self.assertIn("al menos 2 oraciones", result["hints"]["phaseError0"])

    def test_a_locked_phase_does_not_launch_from_the_help(self) -> None:
        locked = dict(phase("plausibility"), unlocked=False, blocked_by="Fase 1")
        result = run(locked, [{"i": 0, "kw": KEYWORDS}, {"i": 0, "help": "propose"}, {"i": 0, "help": "approve"}],
                     fetchResponse={"status": 200, "body": SUGGESTION})
        self.assertEqual(result["calls"], [])
        self.assertIn("primero verifica Fase 1", result["hints"]["phaseHint0"])

    def test_discard_clears_the_proposal_and_launches_nothing(self) -> None:
        result = suggest([{"i": 0, "kw": KEYWORDS}, {"i": 0, "help": "propose"}, {"i": 0, "help": "discard"}])
        self.assertEqual(result["els"]["kwResult0"]["innerHTML"], "")
        self.assertIs(result["els"]["kwResult0"]["hidden"], True)
        self.assertEqual(result["calls"], [])

    def test_an_unavailable_bank_shows_the_reason_and_the_install_hint(self) -> None:
        body = {"available": False, "reason": "cannot start uvx: No such file <or directory>"}
        result = suggest([{"i": 0, "kw": KEYWORDS}, {"i": 0, "help": "propose"}], body=body)
        html = result["els"]["kwResult0"]["innerHTML"]
        self.assertIn("cannot start uvx: No such file &lt;or directory&gt;", html)
        self.assertIn(".mcp.json", html)
        self.assertIn("docs/mcp.md", html)
        self.assertNotIn('data-kw-help="approve"', html)

    def test_a_refusal_from_the_server_is_shown(self) -> None:
        body = {"ok": False, "code": "KEYWORDS_INVALID", "error": "give 3 to 5 different keywords (got 2)"}
        result = suggest([{"i": 0, "kw": KEYWORDS}, {"i": 0, "help": "propose"}], status=422, body=body)
        self.assertIn("give 3 to 5 different keywords", result["els"]["kwResult0"]["innerHTML"])
        self.assertEqual(result["calls"], [])

    def test_a_failed_request_is_reported_in_the_block(self) -> None:
        result = run(phase("plausibility"), [{"i": 0, "kw": KEYWORDS}, {"i": 0, "help": "propose"}],
                     fetchError="offline")
        self.assertIn("offline", result["els"]["kwResult0"]["innerHTML"])
        self.assertEqual(result["calls"], [])

    def test_the_catalogues_cover_every_help_text_in_both_languages(self) -> None:
        en, es = EN_JS.read_text(encoding="utf-8"), ES_JS.read_text(encoding="utf-8")
        self.assertIn('"kwHelp.summary": "Thematic help (keywords)"', en)
        self.assertIn('"kwHelp.summary": "Ayuda temática (palabras clave)"', es)
        self.assertIn('"kwHelp.approve": "Aprobar y lanzar"', es)
        self.assertIn('"kwHelp.approve": "Approve and launch"', en)


class PhaseTwoDescriptionTests(unittest.TestCase):
    def test_the_phase_two_description_mentions_the_optional_thematic_help(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fases = TestClient(server.create_app(tmp)).get("/api/status").json()["fases"]
        desc = next(f for f in fases if f["id"] == "Fase 2")["desc"]
        self.assertIn("thematic help", desc)
        self.assertIn("Banco LIA", desc)


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
