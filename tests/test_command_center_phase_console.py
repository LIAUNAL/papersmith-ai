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
// Assigning innerHTML that holds the reviewer's <textarea id="gateDraftN"> creates that
// field with the unescaped text, as a browser would.
function el(id) {
  return els[id] || (els[id] = {
    id, value: '', textContent: '', _html: '', hidden: false, disabled: false, classList: { add(){}, remove(){} }, focus(){},
    get innerHTML() { return this._html; },
    set innerHTML(v) {
      this._html = v;
      const m = /<textarea[^>]*id="(gateDraft\d+)"[^>]*>([\s\S]*?)<\/textarea>/.exec(v);
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
  const path = url.split('?')[0];
  const queued = path === '/api/prompt/review' && input.reviewSequence && input.reviewSequence.length
    ? input.reviewSequence.shift() : null;
  const r = queued || (input.fetchResponses || {})[path] || input.fetchResponse || { status: 200, body: {} };
  if (path === '/api/prompt/review' && input.reviewDelay) await new Promise((res) => setTimeout(res, input.reviewDelay));
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
  listeners.click({ target: { closest: (sel) => (sel.includes('data-idea-link') ? null : { dataset: { phaseAction: String(i) } }) } });
}
for (const step of input.steps) {
  if (step.wait) await new Promise((r) => setTimeout(r, step.wait));
  if (step.type) el('phaseInput' + step.i).value = step.type;
  if (step.values) Object.entries(step.values).forEach(([id, v]) => { el(id).value = v; });
  if (step.checks) step.checks.forEach((id) => { el(id).checked = true; });
  if (step.gate) {
    listeners.click({ target: { closest: (sel) => (sel.includes('data-gate') ? { dataset: { gate: step.gate, gateIndex: String(step.i) } } : null) } });
  } else if (step.link) {
    listeners.click({ target: { closest: (sel) => (sel.includes('data-idea-link') ? { dataset: { ideaLink: String(step.i) } } : null) } });
  } else click(step.i);
  await new Promise((r) => setTimeout(r, 10));
}
if (input.settle) await new Promise((r) => setTimeout(r, input.settle));
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


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class IdeaLinkTests(unittest.TestCase):
    """The thematic help moved to the Idea tab (idea-shaping S6): the Phase 2
    card links to it instead of carrying an inline keyword box."""

    def test_only_the_plausibility_card_links_to_the_idea_tab(self) -> None:
        html = run(phase("plausibility"), [])["html"]
        self.assertIn('data-idea-link="0"', html)
        self.assertIn("Construir la idea primero", html)
        self.assertIn("La pestaña Idea lo guía", html)
        for stage in ("harness", "ingestion", "proposal", "declarations", "writing"):
            self.assertNotIn("data-idea-link", run(phase(stage), [])["html"], stage)
        flagged = [(stage, a["label"]) for stage, spec in phase_actions.ACTIONS.items()
                   for a in spec["actions"] if a.get("keyword_help")]
        self.assertEqual(flagged, [("plausibility", "Explore the plausibility of the idea")])

    def test_the_inline_keyword_box_is_gone(self) -> None:
        html = run(phase("plausibility"), [])["html"]
        for gone in ("kwHelp", "kwInput", "kwPropose", "data-kw-help", "/api/plausibility/suggest"):
            self.assertNotIn(gone, html)
        script = (STATIC / "phase-console.js").read_text(encoding="utf-8")
        self.assertNotIn("/api/plausibility/suggest", script)

    def test_the_link_closes_the_drawer_and_opens_the_idea_tab_without_launching(self) -> None:
        result = run(phase("plausibility"), [{"i": 0, "link": True}])
        self.assertEqual(result["calls"], [["close"], ["tab", "idea"]])
        self.assertEqual(result["fetches"], [])

    def test_the_card_still_launches_plausibility_from_its_own_prompt(self) -> None:
        idea = "Current models lose accuracy outside their domain. I propose a domain-adaptive method."
        result = run(phase("plausibility"), [{"i": 0, "type": idea}],
                     fetchResponse={"status": 200, "body": {"verdict": "pass", "score": 90}})
        self.assertEqual(result["calls"][0][:3], ["send", "/plausibility " + idea, True])

    def test_the_catalogues_carry_the_link_in_both_languages(self) -> None:
        en, es = EN_JS.read_text(encoding="utf-8"), ES_JS.read_text(encoding="utf-8")
        self.assertIn('"phaseConsole.ideaLink": "Shape the idea first"', en)
        self.assertIn('"phaseConsole.ideaLink": "Construir la idea primero"', es)
        self.assertNotIn('"kwHelp.', en)
        self.assertNotIn('"kwHelp.', es)


class PhaseTwoDescriptionTests(unittest.TestCase):
    def test_the_phase_two_description_mentions_the_optional_idea_tab(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fases = TestClient(server.create_app(tmp)).get("/api/status").json()["fases"]
        desc = next(f for f in fases if f["id"] == "Fase 2")["desc"]
        self.assertIn("optional Idea tab", desc)
        self.assertIn("/idea-shaping", desc)
        self.assertIn("knowledge bank", desc)


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



# ---- prompt quality gate in the phase cards ---------------------------------
GATE_FAIL = {"status": 200, "body": {"ok": True, "verdict": "fail", "score": 50, "threshold": 60, "critical": True,
                                     "issues": [{"id": "figure", "severity": "critical",
                                                 "message": "Missing: the id of a compiled figure."}]}}
GATE_PASS = {"status": 200, "body": {"ok": True, "verdict": "pass", "score": 100, "threshold": 60, "issues": []}}
IMPROVED = "Review the compiled figure fig-architecture and report whether it reads on its own."
REVIEW_IMPROVE = {"status": 200, "body": {
    "ok": True, "available": True, "verdict": "improve", "reply": "The figure id was missing.",
    "issues": ["No figure id."], "improved_prompt": IMPROVED, "preserved_requirements": ["review"],
    "questions": [], "improved_check": {"score": 100}}}
REVIEW_CLARIFY = {"status": 200, "body": {
    "ok": True, "available": True, "verdict": "clarify", "reply": "Which figure?", "issues": ["No figure id."],
    "improved_prompt": "", "preserved_requirements": [],
    "questions": [{"id": "q1", "question": "Which figure?", "options": ["fig-architecture", "fig-results"]}]}}


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PromptGateCardTests(unittest.TestCase):
    TEXT = "review the main picture"

    def gate(self, result: dict) -> str:
        return result["els"].get("phaseGate0", {}).get("innerHTML", "")

    def test_a_passing_prompt_launches_unchanged_after_the_check(self) -> None:
        result = run(phase("figures"), [{"i": 0, "type": self.TEXT}],
                     fetchResponses={"/api/prompt/check": GATE_PASS})
        self.assertEqual(result["fetches"][0], ["/api/prompt/check?lang=es",
                                                {"skill": "figure-review", "text": self.TEXT, "optional": False}])
        self.assertEqual(result["calls"], [["send", "/figure-review " + self.TEXT, True, "slash"]])

    def test_a_failed_prompt_is_held_with_an_alert_and_a_suggestion(self) -> None:
        result = run(phase("figures"), [{"i": 0, "type": self.TEXT}],
                     fetchResponses={"/api/prompt/check": GATE_FAIL, "/api/prompt/review": REVIEW_IMPROVE})
        self.assertEqual(result["calls"], [], "nothing launches before the operator decides")
        html = self.gate(result)
        self.assertIn("no es lo bastante claro para /figure-review (puntaje 50/100, umbral 60)", html)
        self.assertIn("Missing: the id of a compiled figure.", html)
        self.assertIn('id="gateDraft0"', html)
        self.assertIn(IMPROVED, html)
        self.assertIn('data-gate="approve"', html)
        self.assertIn('data-gate="asis"', html)
        self.assertIn('data-gate="cancel"', html)
        self.assertEqual([f[0] for f in result["fetches"]], ["/api/prompt/check?lang=es", "/api/prompt/review?lang=es"])
        self.assertEqual(result["fetches"][1][1]["text"], self.TEXT)

    def test_approve_launches_the_edited_suggestion_with_the_marker(self) -> None:
        edited = IMPROVED + " Be brief."
        result = run(phase("figures"), [{"i": 0, "type": self.TEXT},
                                        {"i": 0, "values": {"gateDraft0": edited}, "gate": "approve"}],
                     fetchResponses={"/api/prompt/check": GATE_FAIL, "/api/prompt/review": REVIEW_IMPROVE})
        self.assertEqual(result["calls"],
                         [["send", f"/figure-review {edited} [prompt-gate: approved]", True, "slash"]])
        self.assertEqual(result["els"]["phaseInput0"]["value"], edited)
        self.assertNotIn("prompt-gate", result["hints"]["phaseHint0"])

    def test_launch_as_is_sends_the_original_with_the_marker(self) -> None:
        result = run(phase("figures"), [{"i": 0, "type": self.TEXT}, {"i": 0, "gate": "asis"}],
                     fetchResponses={"/api/prompt/check": GATE_FAIL, "/api/prompt/review": REVIEW_IMPROVE})
        self.assertEqual(result["calls"],
                         [["send", f"/figure-review {self.TEXT} [prompt-gate: approved]", True, "slash"]])

    def test_cancel_launches_nothing(self) -> None:
        result = run(phase("figures"), [{"i": 0, "type": self.TEXT}, {"i": 0, "gate": "cancel"}],
                     fetchResponses={"/api/prompt/check": GATE_FAIL, "/api/prompt/review": REVIEW_IMPROVE})
        self.assertEqual(result["calls"], [])
        self.assertEqual(self.gate(result), "")

    def test_questions_render_with_options_and_a_free_answer(self) -> None:
        result = run(phase("figures"), [{"i": 0, "type": self.TEXT}],
                     fetchResponses={"/api/prompt/check": GATE_FAIL, "/api/prompt/review": REVIEW_CLARIFY})
        html = self.gate(result)
        self.assertIn("Which figure?", html)
        self.assertIn('id="gateOpt0_0_0"', html)
        self.assertIn('value="fig-results"', html)
        self.assertIn('id="gateFree0_0"', html)
        self.assertIn('data-gate="compose"', html)
        self.assertEqual(result["calls"], [])

    def test_compose_without_an_answer_asks_for_one(self) -> None:
        result = run(phase("figures"), [{"i": 0, "type": self.TEXT}, {"i": 0, "gate": "compose"}],
                     fetchResponses={"/api/prompt/check": GATE_FAIL, "/api/prompt/review": REVIEW_CLARIFY})
        self.assertEqual(result["calls"], [])
        self.assertIn("Responde al menos una pregunta", result["hints"]["phaseHint0"])

    def test_a_free_answer_wins_over_the_option(self) -> None:
        result = run(phase("figures"), [
            {"i": 0, "type": self.TEXT},
            {"i": 0, "checks": ["gateOpt0_0_0"], "values": {"gateFree0_0": "fig-pipeline"}, "gate": "compose"},
        ], fetchResponses={"/api/prompt/check": GATE_FAIL}, reviewSequence=[REVIEW_CLARIFY, REVIEW_IMPROVE])
        reviews = [f for f in result["fetches"] if f[0].startswith("/api/prompt/review")]
        self.assertEqual(reviews[1][1]["answers"][0]["answer"], "fig-pipeline")

    def test_compose_sends_the_answers_and_launches_the_built_prompt(self) -> None:
        # The first review returns questions; answering and composing posts the
        # chosen option, and an improve answer launches with the marker.
        result = run(phase("figures"), [
            {"i": 0, "type": self.TEXT},
            {"i": 0, "checks": ["gateOpt0_0_0"], "gate": "compose"},
        ], fetchResponses={"/api/prompt/check": GATE_FAIL, "/api/prompt/review": REVIEW_CLARIFY},
            reviewSequence=[REVIEW_CLARIFY, REVIEW_IMPROVE])
        reviews = [f for f in result["fetches"] if f[0].startswith("/api/prompt/review")]
        self.assertEqual(reviews[1][1]["answers"],
                         [{"id": "q1", "question": "Which figure?", "answer": "fig-architecture"}])
        self.assertEqual(result["calls"],
                         [["send", f"/figure-review {IMPROVED} [prompt-gate: approved]", True, "slash"]])

    def test_an_unavailable_reviewer_offers_edit_launch_or_cancel(self) -> None:
        down = {"status": 200, "body": {"ok": True, "available": False, "reason": "no agent CLI found"}}
        result = run(phase("figures"), [{"i": 0, "type": self.TEXT}],
                     fetchResponses={"/api/prompt/check": GATE_FAIL, "/api/prompt/review": down})
        html = self.gate(result)
        self.assertIn("no agent CLI found", html)
        self.assertIn('data-gate="edit"', html)
        self.assertIn('data-gate="asis"', html)
        self.assertEqual(result["calls"], [])

    def test_an_unreachable_check_never_blocks_the_launch(self) -> None:
        result = run(phase("figures"), [{"i": 0, "type": self.TEXT}], fetchError="offline")
        self.assertEqual(result["calls"], [["send", "/figure-review " + self.TEXT, True, "slash"]])

    def test_cancel_while_the_reviewer_works_drops_its_answer(self) -> None:
        result = run(phase("figures"), [{"i": 0, "type": self.TEXT}, {"i": 0, "gate": "cancel"}],
                     fetchResponses={"/api/prompt/check": GATE_FAIL, "/api/prompt/review": REVIEW_IMPROVE},
                     reviewDelay=60, settle=120)
        self.assertEqual(result["calls"], [])
        self.assertEqual(self.gate(result), "", "a late answer does not reopen a cancelled box")

    def test_launch_as_is_is_offered_while_the_reviewer_works(self) -> None:
        result = run(phase("figures"), [{"i": 0, "type": self.TEXT}, {"i": 0, "gate": "asis"}],
                     fetchResponses={"/api/prompt/check": GATE_FAIL, "/api/prompt/review": REVIEW_IMPROVE},
                     reviewDelay=60, settle=120)
        self.assertEqual(result["calls"],
                         [["send", f"/figure-review {self.TEXT} [prompt-gate: approved]", True, "slash"]])
        self.assertEqual(self.gate(result), "")

    def test_cancel_while_composing_launches_nothing(self) -> None:
        result = run(phase("figures"), [
            {"i": 0, "type": self.TEXT},
            {"i": 0, "wait": 80, "checks": ["gateOpt0_0_0"], "gate": "compose"},
            {"i": 0, "gate": "cancel"},
        ], fetchResponses={"/api/prompt/check": GATE_FAIL}, reviewSequence=[REVIEW_CLARIFY, REVIEW_IMPROVE],
            reviewDelay=40, settle=150)
        reviews = [f for f in result["fetches"] if f[0].startswith("/api/prompt/review")]
        self.assertEqual(len(reviews), 2, "the compose request was sent")
        self.assertEqual(result["calls"], [])

    def test_the_card_marker_is_the_gate_marker(self) -> None:
        from skills._core.command_center import prompt_gate
        self.assertIn(f"const GATE_MARKER = '{prompt_gate.APPROVED_MARKER}';",
                      (STATIC / "phase-console.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
