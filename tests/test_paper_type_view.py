"""The dashboard side of the paper type (paper-type-lines S4, T4).

`GET /api/paper-type` joins the catalogue, the accepted idea, the scores and
the workspace line; `POST /api/paper-type/score` rescores the accepted idea and
`POST /api/paper-type/agree` records the operator's choice. Phase 2 gains the
advisory sub-step 2.5 "Paper Type", which locks nothing."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import paper_type_view, server
from skills._core.paper_types import decision, registry

SURVEY_IDEA = ("Encuestamos 368 jóvenes rurales de tres municipios de Caldas. Con una encuesta y regresión "
               "Probit estudiamos qué determina que la población joven permanezca en el campo.")
AI_IDEA = ("Current EEG classifiers lose accuracy across subjects. I propose a neural network architecture "
           "that outperforms the state-of-the-art baselines with a new deep learning algorithm.")


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "ws"
        self.root.mkdir()

    def accept(self, idea: str = SURVEY_IDEA) -> None:
        decision.record_acceptance(self.root, idea, by="op")
        decision.record_scores(self.root, idea)


class SubPhaseTests(Case):
    def test_no_accepted_idea(self) -> None:
        sub = paper_type_view.subphase(self.root)
        self.assertEqual((sub["id"], sub["name"], sub["status"]), ("2.5", "Paper Type", "PENDING"))
        self.assertEqual(sub["detail"], "No accepted idea yet: accept the plausibility report first")

    def test_suggested_then_agreed_then_stale(self) -> None:
        self.accept()
        sub = paper_type_view.subphase(self.root)
        self.assertEqual(sub["status"], "PENDING")
        self.assertEqual(sub["detail"], "Suggested paper type: observational-measurement, awaiting the operator's agreement")
        decision.agree(self.root, "observational-measurement", by="op", variant="observational")
        sub = paper_type_view.subphase(self.root)
        self.assertEqual((sub["status"], sub["detail"]), ("PASS", "Agreed paper type: observational-measurement"))
        decision.record_acceptance(self.root, AI_IDEA, by="op")
        decision.record_scores(self.root, AI_IDEA)
        sub = paper_type_view.subphase(self.root)
        self.assertEqual((sub["status"], sub["detail"]),
                         ("PENDING", "The idea changed after the paper type was agreed; agree it again"))

    def test_no_clear_suggestion(self) -> None:
        decision.record_acceptance(self.root, "Una idea sin señales.", by="op")
        decision.record_scores(self.root, "Una idea sin señales.")
        self.assertEqual(paper_type_view.subphase(self.root)["detail"],
                         "No clear paper type yet: discuss it with the agent")

    def test_an_unreadable_record_is_reported_not_raised(self) -> None:
        path = self.root / ".papersmith" / "paper_type.json"
        path.parent.mkdir()
        path.write_text("{broken", encoding="utf-8")
        self.assertEqual(paper_type_view.subphase(self.root)["detail"], "The paper-type record cannot be read")

    def test_phase_two_carries_the_sub_step_and_its_status_is_unchanged(self) -> None:
        client = TestClient(server.create_app(self.root))
        fase2 = client.get("/api/status").json()["fases"][1]
        self.assertEqual([s["id"] for s in fase2["subfases"]], ["2.1", "2.2", "2.3", "2.4", "2.5"])
        self.assertEqual(fase2["status"], "PENDING")
        spanish = client.get("/api/status?lang=es").json()["fases"][1]["subfases"][4]
        self.assertEqual(spanish["name"], "Tipo de paper")
        self.assertEqual(spanish["detail"], "Aún no hay una idea aceptada: acepte primero el reporte de plausibilidad")


class EndpointTests(Case):
    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(server.create_app(self.root))

    def test_view_of_an_empty_workspace(self) -> None:
        body = self.client.get("/api/paper-type").json()
        self.assertEqual([t["id"] for t in body["catalogue"]], [t["id"] for t in registry.load()])
        self.assertIsNone(body["plausibility"])
        self.assertIsNone(body["decision"])
        self.assertEqual(body["line"], "experimental")
        self.assertEqual(body["subphase"]["status"], "PENDING")

    def test_view_joins_scores_and_the_accepted_idea(self) -> None:
        self.accept()
        body = self.client.get("/api/paper-type").json()
        self.assertEqual(body["plausibility"]["idea"], SURVEY_IDEA)
        self.assertEqual(body["decision"]["suggested"], "observational-measurement")
        self.assertEqual(len(body["decision"]["scores"]), len(body["catalogue"]))

    def test_rescore_uses_the_accepted_idea(self) -> None:
        self.assertEqual(self.client.post("/api/paper-type/score", json={}).json()["code"], "IDEA_ABSENT")
        decision.record_acceptance(self.root, AI_IDEA, by="op")
        body = self.client.post("/api/paper-type/score", json={}).json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["decision"]["suggested"], "applied-ai")

    def test_agree_records_and_answers_the_layout(self) -> None:
        self.accept()
        body = self.client.post("/api/paper-type/agree", json={
            "type": "observational-measurement", "variant": "observational", "by": "op",
            "rationale": "own survey"}).json()
        self.assertTrue(body["ok"], body)
        self.assertEqual(body["layout"], "switch:observational-measurement")
        self.assertEqual(json.loads((self.root / ".papersmith" / "paper_type.json").read_text())["agreed"],
                         "observational-measurement")

    def test_agree_refusals_are_typed(self) -> None:
        self.accept()
        refused = self.client.post("/api/paper-type/agree", json={"type": "poetry", "by": "op"})
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(refused.json()["code"], "TYPE_UNKNOWN")
        self.assertEqual(self.client.post("/api/paper-type/agree", json={"type": "review"}).json()["code"],
                         "OPERATOR_ABSENT")

    def test_spanish_templated_details(self) -> None:
        self.accept()
        detail = self.client.get("/api/status?lang=es").json()["fases"][1]["subfases"][4]["detail"]
        self.assertEqual(detail, "Tipo de paper sugerido: observational-measurement, a la espera del acuerdo del operador")
        decision.agree(self.root, "observational-measurement", by="op")
        detail = self.client.get("/api/status?lang=es").json()["fases"][1]["subfases"][4]["detail"]
        self.assertEqual(detail, "Tipo de paper acordado: observational-measurement")

    def test_a_status_never_breaks_on_the_sub_step(self) -> None:
        from unittest import mock
        with mock.patch.object(paper_type_view, "subphase", side_effect=RuntimeError("boom")):
            response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["fases"][1]["subfases"][4]["detail"], "The paper-type record cannot be read")

    def test_rescore_failures_are_typed(self) -> None:
        decision.record_acceptance(self.root, AI_IDEA, by="op")
        (self.root / ".papersmith" / "paper_type.json").write_text("[]", encoding="utf-8")
        response = self.client.post("/api/paper-type/score", json={})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "RECORD_UNREADABLE")

    def test_writes_refuse_cross_origin(self) -> None:
        for path in ("/api/paper-type/score", "/api/paper-type/agree"):
            with self.subTest(path=path):
                response = self.client.post(path, json={}, headers={"origin": "https://evil.example"})
                self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
