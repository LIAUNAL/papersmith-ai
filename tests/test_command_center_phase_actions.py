"""Each pipeline phase card runs its stage: a guided slash command, a real
``smith`` command, or a redirect to the panel that owns the work."""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
import unittest
from pathlib import Path

from papersmith.cli import build_parser
from skills._core.command_center import phase_actions, server

REPO = Path(__file__).resolve().parents[1]
PAGE = (REPO / "skills/_core/command_center/static/index.html").read_text(encoding="utf-8")
TABS = set(re.findall(r"onclick=\"navigateTab\('([a-z]+)'\)\"", PAGE))
SECTIONS = set(re.findall(r"onclick=\"filterModelView\('([a-z]+)', this\)\"", PAGE))


def _subcommands() -> set[str]:
    parser = build_parser()
    sub = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    return set(sub.choices)


class PhaseActionCatalogueTests(unittest.TestCase):
    def test_every_phase_has_an_action(self) -> None:
        self.assertEqual(set(phase_actions.ACTIONS), set(phase_actions.STAGES))
        for stage, entry in phase_actions.ACTIONS.items():
            with self.subTest(stage=stage):
                self.assertTrue(entry["actions"])

    def test_every_slash_command_is_projected_to_every_harness(self) -> None:
        for stage, entry in phase_actions.ACTIONS.items():
            for action in entry["actions"]:
                if action["kind"] != "prompt":
                    continue
                name = action["slash"].lstrip("/")
                with self.subTest(stage=stage, slash=name):
                    self.assertTrue(action["guide"])
                    for folder in (".claude/commands", ".opencode/commands", ".pi/prompts"):
                        self.assertTrue((REPO / folder / f"{name}.md").is_file(), folder)
                    self.assertTrue((REPO / "skills" / name / "SKILL.md").is_file())

    def test_every_shell_command_is_a_smith_subcommand(self) -> None:
        known = _subcommands()
        for stage, entry in phase_actions.ACTIONS.items():
            for action in entry["actions"]:
                if action["kind"] == "command":
                    words = action["command"].split()
                    with self.subTest(command=action["command"]):
                        self.assertEqual(words[0], "smith")
                        self.assertIn(words[1], known)

    def test_every_redirect_names_a_tab_and_section_that_exist(self) -> None:
        for stage, entry in phase_actions.ACTIONS.items():
            for action in entry["actions"]:
                if action["kind"] == "redirect":
                    with self.subTest(stage=stage, tab=action["tab"]):
                        self.assertIn(action["tab"], TABS)
                        if action["section"] and action["tab"] == "modelo":
                            self.assertIn(action["section"], SECTIONS)
                        elif action["section"]:
                            self.assertIn(f'id="{action["section"]}Panel"', PAGE)

    def test_plausibility_asks_for_the_idea_in_two_sentences(self) -> None:
        prompt = phase_actions.ACTIONS["plausibility"]["actions"][0]
        self.assertEqual((prompt["kind"], prompt["slash"], prompt["min_sentences"]),
                         ("prompt", "/plausibility", 2))
        self.assertIn("dos oraciones", " ".join(prompt["guide"]))

    def test_the_concept_map_and_math_are_reached_from_the_proposal_phase(self) -> None:
        redirects = {(a["tab"], a["section"]) for a in phase_actions.ACTIONS["proposal"]["actions"]
                     if a["kind"] == "redirect"}
        self.assertEqual(redirects, {("modelo", "mapa"), ("modelo", "matematico")})

    def test_the_poc_redirect_opens_the_experiments_tab(self) -> None:
        redirects = {(a["tab"], a["section"]) for a in phase_actions.ACTIONS["poc_experiments"]["actions"]
                     if a["kind"] == "redirect"}
        self.assertEqual(redirects, {("experiments", "")})

    def test_the_experiments_phase_offers_kaggle_accounts_for_remote_runs(self) -> None:
        entry = phase_actions.ACTIONS["poc_experiments"]
        self.assertIn("kaggle-accounts", entry["skills"])
        remote = next(a for a in entry["actions"] if a.get("slash") == "/remote-execution")
        self.assertIn("/kaggle-accounts", " ".join(remote["guide"]))

    def test_the_experiments_phase_offers_the_estimate_step_before_remote_runs(self) -> None:
        actions = phase_actions.ACTIONS["poc_experiments"]["actions"]
        labels = [a["label"] for a in actions]
        estimate = actions[labels.index("Estimar tiempo y elegir dónde correr")]
        self.assertEqual((estimate["kind"], estimate["tab"]), ("redirect", "experiments"))
        self.assertIn("Results/timing.json", estimate["desc"])
        remote = next(i for i, a in enumerate(actions) if a.get("slash") == "/remote-execution")
        poc = labels.index("Implementar la prueba de concepto")
        full = next(i for i, a in enumerate(actions) if a.get("slash") == "/experimental-implementation")
        # The estimate runs before the pilot and again before the full run.
        self.assertLess(poc, labels.index("Estimar tiempo y elegir dónde correr"))
        self.assertLess(labels.index("Estimar tiempo y elegir dónde correr"), full)
        self.assertLess(full, remote)

    def test_the_experiments_phase_offers_an_optional_hyperparameter_search(self) -> None:
        entry = phase_actions.ACTIONS["poc_experiments"]
        self.assertIn("hyperparameter-search", entry["skills"])
        actions = entry["actions"]
        labels = [a["label"] for a in actions]
        search = actions[labels.index("Búsqueda de hiperparámetros (Optuna)")]
        self.assertEqual((search["kind"], search["slash"], search["optional"]),
                         ("prompt", "/hyperparameter-search", True))
        self.assertLess(labels.index("Estimar tiempo y elegir dónde correr"), labels.index(search["label"]))
        self.assertLess(labels.index(search["label"]), labels.index("Implementar y medir los experimentos"))
        guide = " ".join(search["guide"]).lower()
        for phrase in ("deliberación", "fold externo", "mismo presupuesto", "variable independiente",
                       "semilla", "ped-anova", "contornos", "solo el operador"):
            self.assertIn(phrase, guide)

    def test_the_gates_live_in_the_pipeline_tab_and_doctor_follows_telemetry(self) -> None:
        tabs = re.findall(r"onclick=\"navigateTab\('([a-z]+)'\)\">", PAGE)
        self.assertNotIn("gates", tabs)
        self.assertEqual(tabs[-3:], ["artifacts", "telemetria", "doctor"])
        pipeline = PAGE.split('<div id="pane-pipeline"', 1)[1].split('<div id="pane-', 1)[0]
        self.assertIn('id="gatesGrid"', pipeline)
        self.assertNotIn('id="pane-gates"', PAGE)
        audit = phase_actions.ACTIONS["audit"]["actions"]
        self.assertIn(("pipeline", "gates"),
                      {(a["tab"], a["section"]) for a in audit if a["kind"] == "redirect"})

    def test_the_experiments_phase_offers_data_and_replication_steps(self) -> None:
        entry = phase_actions.ACTIONS["poc_experiments"]
        data = next(a for a in entry["actions"] if a.get("slash") == "/datasets")
        self.assertTrue(data["label"].startswith("Datos: toy set siempre y dataset oficial"))
        guide = " ".join(data["guide"])
        for verb in ("synth", "search", "license", "qc", "prepare", "publish"):
            self.assertIn(verb, guide)
        self.assertIn("dataset-scout", guide)
        self.assertIn("dataset-curator", guide)
        self.assertIn("consentimiento", guide)
        replica = next(a for a in entry["actions"] if a.get("label") == "Réplica de métodos de comparación")
        self.assertEqual(replica["slash"], "/proposal-implementation")
        guide = " ".join(replica["guide"])
        self.assertIn("paper-replicator", guide)
        self.assertIn("código publicado", guide)

    def test_phase_ids_resolve_to_stages(self) -> None:
        self.assertEqual(phase_actions.stage_for("Fase 8"), "writing")
        self.assertEqual(phase_actions.stage_for("Fase 10"), "paper")
        self.assertEqual(phase_actions.stage_for("plausibility"), "plausibility")
        self.assertIsNone(phase_actions.stage_for("Fase 12"))
        self.assertIsNone(phase_actions.stage_for("nonsense"))
        # Keywords earlier releases accepted still route.
        self.assertEqual(phase_actions.stage_for("compile"), "paper")
        self.assertEqual(phase_actions.stage_for("figure"), "figures")
        self.assertEqual(phase_actions.stage_for("sota"), "plausibility")
        for keyword, stage in phase_actions.LEGACY_IDS.items():
            self.assertEqual(phase_actions.stage_for(keyword.upper()), stage)
            self.assertIn(stage, phase_actions.STAGES)
        self.assertIsNone(phase_actions.stage_for("compile pdf"))


class Req:
    def __init__(self, body):
        self.body = body
        self.headers = {}  # origin_is_same reads it; no Origin header, as from curl

    async def json(self):
        return self.body


class ServerPhaseTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve() / "fresh-paper"
        self.root.mkdir()
        self.app = server.create_app(self.root, history_store=None)

    def route(self, path: str, method: str = "GET"):
        return next(r.endpoint for r in self.app.routes
                    if getattr(r, "path", None) == path and method in (getattr(r, "methods", None) or ()))

    def run_phase(self, phase_id: str) -> dict:
        response = asyncio.run(self.route("/api/phase/run", "POST")(Req({"phase_id": phase_id})))
        return json.loads(bytes(response.body))

    def test_the_status_carries_actions_and_real_commands(self) -> None:
        status = json.loads(bytes(self.route("/api/status")().body))
        self.assertEqual([f["stage_id"] for f in status["fases"]], list(phase_actions.STAGES))
        for phase in status["fases"]:
            with self.subTest(phase=phase["id"]):
                self.assertTrue(phase["actions"])
                self.assertNotIn("--stage", phase["cli_command"])
        self.assertEqual(status["fases"][1]["cli_command"], "/plausibility <texto>")

    def test_phase_five_lists_data_and_replication_sub_phases_in_order(self) -> None:
        status = json.loads(bytes(self.route("/api/status")().body))
        fase5 = next(f for f in status["fases"] if f["stage_id"] == "poc_experiments")
        ids = [s["id"] for s in fase5["subfases"]]
        self.assertEqual(ids, [f"5.{i}" for i in range(1, len(ids) + 1)])
        names = [s["name"] for s in fase5["subfases"]]
        data = names.index("Datos: toy set siempre y dataset oficial")
        replica = names.index("Réplica de métodos de comparación")
        build = names.index("Prueba de concepto")
        self.assertLess(data, build)
        self.assertLess(replica, build)
        self.assertIn("paper-replicator", fase5["subfases"][replica]["detail"])
        estimate = names.index("Estimar tiempo y elegir dónde correr")
        full = names.index("Experimentos completos")
        remote = names.index("Ensayo remoto y autorización del lanzamiento (operador)")
        self.assertLess(build, estimate)
        self.assertLess(estimate, full)
        self.assertLess(full, remote)
        self.assertIn("Results/timing.json", fase5["subfases"][estimate]["detail"])
        self.assertEqual(fase5["subfases"][remote]["id"], "5.13")
        search = names.index("Búsqueda de hiperparámetros (Optuna, opcional)")
        self.assertLess(estimate, search)
        self.assertLess(search, full)
        self.assertIn("/hyperparameter-search", fase5["subfases"][search]["detail"])
        self.assertIn("/datasets", fase5["subfases"][data]["detail"])

    def test_each_phase_runs_its_own_check(self) -> None:
        self.assertIn("bloques en paper/main.tex", self.run_phase("Fase 8")["message"])
        self.assertIn("figuras", self.run_phase("Fase 9")["message"])
        self.assertIn("candidatos", self.run_phase("plausibility")["message"])
        self.assertIn("auditoría", self.run_phase("Fase 11")["message"])
        self.assertIn("No hay paper/main.tex", self.run_phase("Fase 10")["message"])

    def test_an_unknown_phase_is_refused(self) -> None:
        response = asyncio.run(self.route("/api/phase/run", "POST")(Req({"phase_id": "Fase 99"})))
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
