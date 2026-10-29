"""The experiments tutor's card: placed in the experiments tab outside the
repainted #experimentsRoot, loaded by its own cache-busted script, rendering
model text safely and handing a change of decision to the CLI assistant as
`/experimental-deliberation` without pressing Enter."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import experiments_tutor, server

STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
SCRIPT = STATIC / "experiments-tutor.js"

TURN = {
    "role": "tutor", "agent": "claude",
    "reply": "Mira `src/demo/data.py` <img src=x onerror=alert(1)>",
    "question": "¿Qué sujetos ve la normalización?",
    "assessment": {"level": 2, "label": "justificada", "evidence": "el protocolo dice por sujeto",
                   "gaps": ["escalador ajustado con todos los sujetos"]},
    "next_step": "Lee el ajuste del escalador.",
    "decision_area": "validation",
    "evidence": ["experiments/experiments-demo-v01.md"],
    "risks": ["fuga de sujetos de prueba"],
    "deliberation_prompt": "En [exp:E1], ajusta el escalador\ndentro de cada fold.",
}


def node(body: str) -> str:
    """Run experiments-tutor.js in node with stub DOM pieces, then ``body``."""
    script = (
        "const fs=require('fs');const els={};const calls=[];"
        "global.window={mathRichText:(t)=>'<p>'+String(t).replace(/</g,'&lt;')+'</p>',"
        "sendToCli:async(...a)=>{calls.push(a);return true;}};"
        "global.document={addEventListener(){},querySelectorAll:()=>[],"
        "getElementById:(id)=>(els[id]=els[id]||{dataset:{},value:'',textContent:'',innerHTML:''})};"
        f"eval(fs.readFileSync({json.dumps(str(SCRIPT))},'utf8'));"
        + body
    )
    return subprocess.run(["node", "-e", script], capture_output=True, text=True,
                          cwd=tempfile.gettempdir(), check=True).stdout.strip()


class PageTests(unittest.TestCase):
    def pane(self) -> str:
        start = PAGE.index('<div id="pane-experiments"')
        return PAGE[start:PAGE.index("<!-- TAB 3: SECTIONS", start)]

    def card(self) -> str:
        start = PAGE.index('<section id="xtutorPanel"')
        return PAGE[start:PAGE.index("</section>", start)]

    def test_the_card_sits_in_the_experiments_tab_outside_the_repainted_root(self) -> None:
        pane = self.pane()
        self.assertIn('id="xtutorPanel"', pane)
        root = pane.index('<div id="experimentsRoot">')
        root_end = pane.index("</div>", root)
        card = pane.index('id="xtutorPanel"')
        self.assertFalse(root < card < root_end)
        for element in ("xtutorThread", "xtutorInput", "xtutorSend", "xtutorReset", "xtutorArea",
                        "xtutorMeter", "xtutorStatus"):
            self.assertIn(f'id="{element}"', self.card())

    def test_its_own_cache_busted_script_loads_after_the_rich_text_helper(self) -> None:
        tag = '<script src="./experiments-tutor.js?v='
        self.assertIn(tag, PAGE)
        self.assertLess(PAGE.index('<script src="./math-panel.js?v='), PAGE.index(tag))
        self.assertTrue(SCRIPT.is_file())

    def test_the_selector_offers_every_decision_area_and_the_modes(self) -> None:
        card = self.card()
        for area in experiments_tutor.AREAS:
            self.assertIn(f'<option value="{area}"', card)
        for mode in experiments_tutor.MODES:
            self.assertIn(f'data-xtutor-mode="{mode}"', card)
        # The math panel binds every [data-tutor-mode]; these must not be among them.
        self.assertNotIn("data-tutor-mode", card)
        self.assertIn("Tutor de experimentos", card)

    def test_opening_the_tab_loads_the_thread(self) -> None:
        start = PAGE.index("if (tabId === 'experiments') {")
        self.assertIn("window.refreshExperimentsTutor?.();", PAGE[start:PAGE.index("}", start)])


class ScriptTests(unittest.TestCase):
    def test_the_areas_match_the_backend(self) -> None:
        out = node("console.log(JSON.stringify(Object.keys(window.ExperimentsTutor.AREAS)));")
        self.assertEqual(tuple(json.loads(out)), experiments_tutor.AREAS)

    def test_a_turn_renders_safely_with_its_evidence_risks_and_deliberation(self) -> None:
        out = node(f"console.log(window.ExperimentsTutor.renderTurn({json.dumps(TURN)}, 0));")
        self.assertNotIn("<img", out)
        self.assertIn("&lt;img", out)
        for text in ("¿Qué sujetos ve la normalización?", "experiments/experiments-demo-v01.md",
                     "fuga de sujetos de prueba", "Diseño 2 · justificada", "Esquema de validación",
                     "Deliberar este cambio", 'data-xtutor-deliberate="0"'):
            self.assertIn(text, out)
        quiet = node(f"console.log(window.ExperimentsTutor.renderTurn({json.dumps({**TURN, 'deliberation_prompt': ''})}, 0));")
        self.assertNotIn("Deliberar este cambio", quiet)

    def test_a_change_is_typed_into_the_cli_as_the_deliberation_without_enter(self) -> None:
        out = node("window.ExperimentsTutor.deliberate("
                   f"{json.dumps(TURN['deliberation_prompt'])}).then(()=>console.log(JSON.stringify(calls)));")
        self.assertEqual(json.loads(out), [[
            "/experimental-deliberation En [exp:E1], ajusta el escalador dentro de cada fold.",
            False, {"kind": "slash"}]])

    def test_control_characters_never_reach_the_cli(self) -> None:
        prompt = "Fit\u001b[2J the\u0007 scaler\r\n\tinside\u0000 each\u007f fold\u001b]0;x\u0007."
        out = node("window.ExperimentsTutor.deliberate("
                   f"{json.dumps(prompt)}).then(()=>console.log(JSON.stringify([calls,"
                   f"window.ExperimentsTutor.deliberationCommand({json.dumps(prompt)})])));")
        calls, command = json.loads(out)
        self.assertEqual(command, "/experimental-deliberation Fit [2J the scaler inside each fold ]0;x .")
        self.assertEqual(calls, [[command, False, {"kind": "slash"}]])
        for char in map(chr, list(range(0x20)) + [0x7F]):
            self.assertNotIn(char, command)

    def test_a_refresh_during_a_turn_keeps_the_reading_status(self) -> None:
        out = node(
            "let answer;const seen=[];"
            "global.fetch=(url,opts)=>{if(opts&&opts.method==='POST'){return new Promise((r)=>{answer=r;});}"
            "return Promise.resolve({ok:true,status:200,json:async()=>({turns:[]})});};"
            "els.xtutorInput={value:'¿Y la fuga?'};els.xtutorArea={value:'validation'};"
            "const turn=window.ExperimentsTutor.send();"
            "(async()=>{seen.push(els.xtutorStatus.textContent);"
            "await window.refreshExperimentsTutor();seen.push(els.xtutorStatus.textContent,els.xtutorStatus.dataset.tone);"
            "answer({ok:true,status:200,json:async()=>({agent:'claude'})});await turn;"
            "seen.push(els.xtutorStatus.textContent);"
            "await window.refreshExperimentsTutor();seen.push(els.xtutorStatus.textContent);"
            "console.log(JSON.stringify(seen));})();")
        reading = "El tutor está leyendo el protocolo, el código y los resultados… (suele tardar 30–90 s)"
        self.assertEqual(json.loads(out), [reading, reading, "warn", "Respondió claude", "Listo"])

    def test_a_message_posts_its_mode_and_area_to_the_experiments_route(self) -> None:
        out = node(
            "const sent=[];global.fetch=async(url,opts)=>{sent.push([url,opts&&opts.method||'GET',opts&&opts.body]);"
            "return {ok:true,status:200,json:async()=>({turns:[],agent:'claude'})};};"
            "els.xtutorInput={value:'¿Basta el toy set?'};els.xtutorArea={value:'toy-set'};"
            "window.ExperimentsTutor.send().then(()=>console.log(JSON.stringify(sent)));")
        sent = json.loads(out)
        self.assertEqual(sent[0][:2], ["/api/terminal/tutor/experiments/turn", "POST"])
        self.assertEqual(json.loads(sent[0][2]), {"message": "¿Basta el toy set?", "mode": "ask", "area": "toy-set"})
        self.assertEqual(sent[1][:2], ["/api/terminal/tutor/experiments/thread", "GET"])


if __name__ == "__main__":
    unittest.main()
