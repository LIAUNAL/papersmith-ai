"""Paper-type identification, deterministic half (paper-type-lines S3, T2).

The idea (and, more lightly, the SOTA pool plausibility gathered) is matched
against each catalogue type's signals: on word boundaries, folding case and
accents, the longest matching signal winning where two overlap. Each type gets
a 0-100 match score; the clear leader is suggested. The plausibility acceptance
and the scores are persisted in `.papersmith/plausibility.json` and
`.papersmith/paper_type.json`, which nothing in the applied-AI flow reads."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from skills._core.paper_types import decision, registry, score

REPO = Path(__file__).resolve().parents[1]
CLI = ["skills/_core/paper_types/paper_type_cli.py"]

AI_IDEA = ("Current EEG classifiers lose accuracy across subjects. I propose a neural network architecture "
           "that outperforms the state-of-the-art baselines with a new deep learning algorithm.")
SURVEY_IDEA = ("Encuestamos 368 jóvenes rurales de tres municipios de Caldas. Con una encuesta y regresión "
               "Probit estudiamos qué determina que la población joven permanezca en el campo.")
SIM_IDEA = ("We study spin reorientation in thin manganite films with Monte Carlo simulation of a Heisenberg "
            "Hamiltonian, sweeping anisotropy and thickness.")


def by_type(result: dict) -> dict:
    return {row["type"]: row for row in result["scores"]}


class ScoreTests(unittest.TestCase):
    def test_every_catalogue_type_gets_a_score_in_catalogue_order(self) -> None:
        result = score.score(AI_IDEA)
        self.assertEqual([row["type"] for row in result["scores"]], [t["id"] for t in registry.load()])
        for row in result["scores"]:
            self.assertTrue(0 <= row["score"] <= 100)
            self.assertEqual(set(row), {"type", "score", "raw", "matched", "pool_matched", "status", "line", "variant"})

    def test_the_clear_leader_is_suggested(self) -> None:
        for idea, expected in ((AI_IDEA, "applied-ai"), (SURVEY_IDEA, "observational-measurement"),
                               (SIM_IDEA, "lab-simulation")):
            with self.subTest(expected=expected):
                result = score.score(idea)
                self.assertEqual(result["suggested"], expected, result["scores"])
                self.assertEqual(by_type(result)[expected]["score"], 100)

    def test_accents_and_inflections_match(self) -> None:
        matched = by_type(score.score("Simulación con dinámica molecular de nanopartículas"))["lab-simulation"]["matched"]
        self.assertIn("dinamica molecular", matched)
        self.assertIn("simulacion", matched)

    def test_matches_start_on_a_word_boundary(self) -> None:
        # "sem" (materials) must not fire inside "semantic" or "assembly".
        self.assertNotIn("sem", by_type(score.score("semantic assembly of documents"))["lab-simulation"]["matched"])

    def test_the_longest_overlapping_signal_wins(self) -> None:
        rows = by_type(score.score("A numerical model of heat flow"))
        self.assertIn("numerical model", rows["lab-simulation"]["matched"])
        self.assertNotIn("model", rows["applied-ai"]["matched"])

    def test_no_signal_suggests_nothing(self) -> None:
        result = score.score("Hola, quiero escribir algo interesante.")
        self.assertIsNone(result["suggested"])
        self.assertEqual(result["confidence"], "low")
        self.assertTrue(all(row["score"] == 0 for row in result["scores"]))

    def test_a_tie_suggests_nothing(self) -> None:
        result = score.score("survey and simulation")
        self.assertIsNone(result["suggested"])

    def test_the_pool_adds_a_light_bounded_weight(self) -> None:
        idea_only = by_type(score.score(SURVEY_IDEA))
        with_pool = by_type(score.score(SURVEY_IDEA, pool_text="cohort survey prevalence households " * 20))
        gained = with_pool["observational-measurement"]["raw"] - idea_only["observational-measurement"]["raw"]
        self.assertGreater(gained, 0)
        self.assertLessEqual(gained, score.POOL_CAP)
        self.assertTrue(with_pool["observational-measurement"]["pool_matched"])

    def test_confidence_reflects_the_margin(self) -> None:
        self.assertEqual(score.score(AI_IDEA)["confidence"], "high")
        self.assertEqual(score.score("a sensor")["confidence"], "low")
        self.assertEqual(score.score("a low-cost sensor prototype")["confidence"], "high")


class CatalogueDiscriminationTests(unittest.TestCase):
    """Ideas shaped like the studies the catalogue was drawn from each reach
    their own type (paper-type-lines L8-L10)."""

    IDEAS = {
        ("observational-measurement", "observational"): "Cohorte retrospectiva de 124 pacientes con estado migrañoso atendidos en sala de infusión; "
                         "describimos la respuesta y sus predictores clínicos.",
        ("experiment-intervention", "human-trial"): "Ensayo aleatorizado en dos colegios: un grupo control y un grupo con una intervención de "
                        "aprendizaje basado en proyectos; medimos el rendimiento antes y después.",
        ("qualitative-participatory", "qualitative-mixed"): "Estudio de caso de la cadena de la panela con entrevistas semiestructuradas, talleres "
                             "participativos y análisis temático.",
        ("observational-measurement", "diagnostic-validation"): "Validamos una medida automática de inteligibilidad del habla contra la evaluación "
                                 "clínica de referencia, con concordancia y sensibilidad en tres idiomas.",
        ("hardware", None): "Diseñamos un prototipo de bajo costo de adquisición EEG con microcontrolador y lo comparamos "
                    "con un equipo comercial.",
        ("lab-simulation", "materials"): "Películas delgadas de CuInSe2 depositadas por sputtering RF a distintas temperaturas; "
                     "caracterizamos por XRD, XPS y UV-Vis el band gap.",
        ("lab-simulation", "modelling-simulation"): "Simulación Monte Carlo de un hamiltoniano de Heisenberg en nanotubos magnéticos variando "
                         "la anisotropía.",
        ("data-resource", None): "Presentamos un corpus de grabaciones de habla en español, con su protocolo de anotación "
                         "y resultados de referencia.",
        ("observational-measurement", "measurement-instrument"): "Construimos un índice de pobreza multidimensional con indicadores y ponderación "
                           "acordados con la alcaldía para la política pública.",
        ("review", None): "Revisión sistemática del estado del arte sobre biomarcadores de habla, siguiendo PRISMA.",
        ("applied-ai", None): AI_IDEA,
    }

    def test_each_idea_reaches_its_family_and_variant(self) -> None:
        for (family, variant), idea in self.IDEAS.items():
            with self.subTest(family=family, variant=variant):
                result = score.score(idea)
                self.assertEqual(result["suggested"], family, result["scores"])
                self.assertEqual(by_type(result)[family]["variant"], variant)

    def test_extra_variants_reach_their_family(self) -> None:
        cases = {
            ("experiment-intervention", "field-experiment"):
                "Ensayo en parcelas con diseño de bloques para comparar dos cultivares de café.",
            ("qualitative-participatory", "consensus-foresight"):
                "Un panel de expertos con método Delphi y análisis MICMAC construye escenarios para la cadena del cacao.",
            ("qualitative-participatory", "experience-report"):
                "Relatamos una experiencia docente de enseñanza de física en el aula con guías de laboratorio.",
        }
        for (family, variant), idea in cases.items():
            with self.subTest(variant=variant):
                result = score.score(idea)
                self.assertEqual(result["suggested"], family, result["scores"])
                self.assertEqual(by_type(result)[family]["variant"], variant)

    def test_each_word_of_a_multi_word_signal_may_inflect(self) -> None:
        self.assertIn("pelicula delgada", by_type(score.score("peliculas delgadas de oro"))["lab-simulation"]["matched"])


class DecisionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_acceptance_is_recorded_with_its_idea_and_pool_hash(self) -> None:
        pool = self.root / "sota-pool" / "candidates.json"
        pool.parent.mkdir()
        pool.write_text(json.dumps({"candidates": [{"title": "A cohort survey", "abstract": "households"}]}),
                        encoding="utf-8")
        record = decision.record_acceptance(self.root, SURVEY_IDEA, by="operator", top5=["c1", "c2"])
        stored = json.loads((self.root / ".papersmith" / "plausibility.json").read_text(encoding="utf-8"))
        self.assertEqual(stored, record)
        self.assertEqual(stored["idea"], SURVEY_IDEA)
        self.assertEqual(stored["accepted_by"], "operator")
        self.assertEqual(stored["top5"], ["c1", "c2"])
        self.assertEqual(len(stored["pool_sha256"]), 64)

    def test_acceptance_refuses_without_an_operator_or_an_idea(self) -> None:
        for idea, by in (("", "operator"), (SURVEY_IDEA, " ")):
            with self.subTest(idea=idea[:5], by=by), self.assertRaises(decision.DecisionError):
                decision.record_acceptance(self.root, idea, by=by)

    def test_scores_are_stored_and_an_agreed_type_survives_a_rescore(self) -> None:
        first = decision.record_scores(self.root, SURVEY_IDEA)
        self.assertEqual(first["suggested"], "observational-measurement")
        path = self.root / ".papersmith" / "paper_type.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update({"agreed": "observational-measurement", "agreed_by": "operator", "agreed_idea_sha256": data["idea_sha256"]})
        path.write_text(json.dumps(data), encoding="utf-8")
        same = decision.record_scores(self.root, SURVEY_IDEA)
        self.assertEqual(same["agreed"], "observational-measurement")
        self.assertFalse(same["agreed_stale"])
        changed = decision.record_scores(self.root, SIM_IDEA)
        self.assertEqual(changed["agreed"], "observational-measurement")
        self.assertTrue(changed["agreed_stale"], "the idea changed after the type was agreed")

    def test_read_of_an_empty_workspace_is_empty(self) -> None:
        self.assertEqual(decision.read(self.root), {"plausibility": None, "paper_type": None})


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def run_cli(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, *CLI, *args], cwd=REPO, input=stdin,
                              capture_output=True, text=True, check=False)

    def test_score_reads_the_idea_from_stdin_and_writes_the_decision(self) -> None:
        done = self.run_cli("score", "--root", str(self.root), "--idea-file", "-", stdin=SIM_IDEA)
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["suggested"], "lab-simulation")
        self.assertTrue((self.root / ".papersmith" / "paper_type.json").is_file())

    def test_dry_run_writes_nothing(self) -> None:
        done = self.run_cli("score", "--root", str(self.root), "--dry-run", "--idea-file", "-", stdin=SIM_IDEA)
        self.assertEqual(json.loads(done.stdout)["suggested"], "lab-simulation")
        self.assertFalse((self.root / ".papersmith").exists())

    def test_accept_records_the_acceptance_then_scores_from_it(self) -> None:
        done = self.run_cli("accept", "--root", str(self.root), "--by", "operator", "--idea-file", "-",
                            stdin=SURVEY_IDEA)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["suggested"], "observational-measurement")
        rescored = self.run_cli("score", "--root", str(self.root))  # no stdin: the accepted idea
        self.assertEqual(json.loads(rescored.stdout)["suggested"], "observational-measurement")
        shown = json.loads(self.run_cli("show", "--root", str(self.root)).stdout)
        self.assertEqual(shown["plausibility"]["accepted_by"], "operator")
        self.assertEqual(shown["paper_type"]["suggested"], "observational-measurement")

    def test_score_without_any_idea_is_a_typed_refusal(self) -> None:
        done = self.run_cli("score", "--root", str(self.root))
        self.assertEqual(done.returncode, 1)
        self.assertEqual(json.loads(done.stdout)["error"], "IDEA_ABSENT")

    def test_stdin_is_read_only_when_asked(self) -> None:
        done = self.run_cli("score", "--root", str(self.root), stdin=SIM_IDEA)
        self.assertEqual(json.loads(done.stdout)["error"], "IDEA_ABSENT")

    def test_accept_refusals(self) -> None:
        no_operator = self.run_cli("accept", "--root", str(self.root), "--idea-file", "-", stdin=SIM_IDEA)
        self.assertEqual(json.loads(no_operator.stdout)["error"], "OPERATOR_ABSENT")
        unreadable = self.run_cli("accept", "--root", str(self.root), "--by", "op", "--idea-file",
                                  str(self.root / "missing.txt"))
        self.assertEqual(json.loads(unreadable.stdout)["error"], "IDEA_UNREADABLE")
        self.assertFalse((self.root / ".papersmith").exists(), "a refusal writes nothing")

    def test_a_record_that_is_not_an_object_is_never_overwritten(self) -> None:
        path = self.root / ".papersmith" / "paper_type.json"
        path.parent.mkdir()
        path.write_text("[1, 2]", encoding="utf-8")
        done = self.run_cli("score", "--root", str(self.root), "--idea-file", "-", stdin=SIM_IDEA)
        self.assertEqual(json.loads(done.stdout)["error"], "RECORD_UNREADABLE")
        self.assertEqual(path.read_text(encoding="utf-8"), "[1, 2]")

    def test_usage_error(self) -> None:
        done = self.run_cli("nope")
        self.assertEqual(done.returncode, 2)
        self.assertEqual(json.loads(done.stdout)["error"], "USAGE")


if __name__ == "__main__":
    unittest.main()
