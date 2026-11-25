"""The Idea tab's routes (idea-shaping S6, T3): `GET /api/idea` and the step
POSTs, through the dashboard app on a temporary workspace. The engine's seams
are faked (`bank.CONNECT` answers an in-process MCP session, `profile.FETCH`
an in-process OpenAlex), so nothing reaches the network or starts a process."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from skills._core.command_center import banco_suggest, idea_view, server
from skills._core.idea import bank, brief, profile

HITS = [{"id": "P1", "kind": "articulo", "title": "Graph models for EEG transfer", "year": 2024, "cluster": "K1",
         "doi": "10.1/x", "score": 0.9},
        {"id": "P2", "kind": "proyecto", "title": "Domain shift in clinical EEG", "year": 2022, "cluster": "K1",
         "score": 0.5}]
TWO_SENTENCES = ("Current EEG classifiers lose accuracy when the recording site changes, which limits clinical use. "
                 "I propose a domain-adaptive graph model that keeps its accuracy across hospitals.")


class FakeSession:
    """An MCP session that lists ``tools`` and answers ``search_bank`` with HITS."""

    def __init__(self, tools: list[str]) -> None:
        self._tools = tools

    def tools(self) -> list[str]:
        return list(self._tools)

    def call(self, name: str, arguments: dict) -> object:
        if name == "search_bank":
            return HITS
        if name == "taxonomy":
            return {"clusters": [{"id": "K1", "name": "EEG transfer"}]}
        raise AssertionError(f"unexpected tool {name}")

    def close(self) -> None:
        pass


class FakeOpenAlex:
    def __init__(self, offline: bool = False) -> None:
        self.offline = offline
        self.calls: list[str] = []

    def __call__(self, url: str) -> dict:
        self.calls.append(url)
        if self.offline:
            raise OSError("network is unreachable")
        if "/works?" in url:
            return {"meta": {"count": 12}}
        if "/authors?" in url:
            return {"results": [{"id": "https://openalex.org/A5023888391", "display_name": "Ada Lovelace",
                                 "works_count": 42, "orcid": "https://orcid.org/0000-0002-1825-0097",
                                 "topics": [{"display_name": "Brain-computer interfaces", "count": 9}]}]}
        raise AssertionError(f"unexpected OpenAlex request {url}")


class Case(unittest.TestCase):
    servers: dict[str, list[str]] = {"banco-lia": ["search_bank", "taxonomy"], "labbank": ["search_bank"],
                                     "notes": ["read_note"]}

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "ws"
        (self.root / ".papersmith").mkdir(parents=True)
        (self.root / ".mcp.json").write_text(json.dumps({"mcpServers": {
            "banco-lia": {"command": "uvx", "args": ["banco-lia"]},
            "asta": {"type": "http", "url": "https://asta.example/mcp"},
            "labbank": {"command": "python", "args": ["labbank.py"]},
            "notes": {"type": "http", "url": "https://notes.example/mcp"},
        }}), encoding="utf-8")
        self.connected: list[str] = []
        self.unreachable: set[str] = set()
        self.openalex = FakeOpenAlex()
        for patcher in (mock.patch.object(bank, "CONNECT", self.connect),
                        mock.patch.object(profile, "FETCH", self.openalex)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(server.create_app(self.root))

    def connect(self, root, name, timeout=None):
        self.connected.append(name)
        if name in self.unreachable:
            raise banco_suggest.Unavailable(f"cannot start {name}: No such file or directory")
        return FakeSession(self.servers.get(name, []))

    def post(self, route: str, body: dict | None = None, **headers):
        return self.client.post(f"/api/idea/{route}", json=body or {}, headers=headers)

    def ok(self, route: str, body: dict | None = None) -> dict:
        response = self.post(route, body)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("brief", data)
        return data

    def stored(self) -> dict:
        return json.loads((self.root / brief.PATH).read_text(encoding="utf-8"))


class ViewTests(Case):
    def test_an_empty_workspace_answers_an_empty_brief_and_the_bank_choices(self) -> None:
        body = self.client.get("/api/idea").json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["brief"]["bank"]["choice"], None)
        self.assertEqual(body["choices"]["managed"], "banco-lia")
        self.assertEqual([o["server"] for o in body["choices"]["others"]], ["labbank", "notes"])
        self.assertEqual(body["levels"], ["student", "early-career", "experienced", "senior"])
        self.assertEqual((body["ready"], body["handoff"]), (False, None))
        self.assertFalse((self.root / brief.PATH).exists())

    def test_an_unreadable_brief_answers_409_with_its_code(self) -> None:
        (self.root / brief.PATH).write_text("{broken", encoding="utf-8")
        response = self.client.get("/api/idea")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "BRIEF_UNREADABLE")
        self.assertIn("not valid JSON", response.json()["message"])


class BankTests(Case):
    def test_choose_none_records_it_and_queries_no_bank(self) -> None:
        data = self.ok("bank", {"action": "choose", "choice": "none"})
        self.assertEqual(data["result"]["choice"], "none")
        self.assertEqual(data["brief"]["bank"]["choice"], "none")
        self.assertEqual(self.stored()["bank"]["choice"], "none")
        self.assertEqual(self.connected, [])

    def test_choose_banco_lia_probes_it(self) -> None:
        data = self.ok("bank", {"action": "choose", "choice": "banco-lia"})
        bank_state = data["brief"]["bank"]
        self.assertEqual((bank_state["choice"], bank_state["available"], bank_state["compatible"]),
                         ("banco-lia", True, True))
        self.assertEqual(self.connected, ["banco-lia"])

    def test_an_unreachable_banco_lia_is_recorded_with_its_reason(self) -> None:
        self.unreachable.add("banco-lia")
        data = self.ok("bank", {"action": "choose", "choice": "banco-lia"})
        self.assertFalse(data["brief"]["bank"]["available"])
        self.assertIn("cannot start banco-lia", data["brief"]["bank"]["reason"])

    def test_another_compatible_bank_and_a_conversation_only_one(self) -> None:
        compatible = self.ok("bank", {"action": "choose", "choice": "other", "server": "labbank"})["brief"]["bank"]
        self.assertEqual((compatible["choice"], compatible["server"], compatible["compatible"]),
                         ("other", "labbank", True))
        search = self.ok("bank", {"action": "search", "query": "eeg transfer"})["result"]
        self.assertTrue(search["available"])
        self.assertEqual([h["id"] for h in search["hits"]], ["P1", "P2"])
        guide_only = self.ok("bank", {"action": "choose", "choice": "other", "server": "notes"})["brief"]["bank"]
        self.assertEqual((guide_only["available"], guide_only["compatible"]), (True, False))
        self.assertIn("mcp__notes__*", guide_only["reason"])

    def test_probe_answers_without_recording(self) -> None:
        result = self.ok("bank", {"action": "probe", "server": "notes"})["result"]
        self.assertEqual((result["server"], result["available"], result["compatible"]), ("notes", True, False))
        self.assertFalse((self.root / brief.PATH).exists())

    def test_add_writes_mcp_json_keeps_the_others_and_chooses_it(self) -> None:
        data = self.ok("bank", {"action": "add", "name": "mybank", "url": "https://bank.example/mcp"})
        self.assertEqual(data["result"]["added"]["server"], "mybank")
        self.assertEqual(data["brief"]["bank"]["server"], "mybank")
        servers = json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
        self.assertEqual(list(servers), ["banco-lia", "asta", "labbank", "notes", "mybank"])
        self.assertIn("mybank", [o["server"] for o in data["choices"]["others"]])

    def test_refusals_answer_422_with_code_and_message(self) -> None:
        for body, code in (({"action": "choose", "choice": "asta"}, "SERVER_MANAGED"),
                           ({"action": "choose", "choice": "other", "server": "ghost"}, "SERVER_UNKNOWN"),
                           ({"action": "add", "name": "x", "command": "a", "url": "https://b"}, "SERVER_SPEC"),
                           ({"action": "explode"}, "ACTION_UNKNOWN")):
            with self.subTest(code=code):
                response = self.post("bank", body)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["ok"], False)
                self.assertEqual(response.json()["code"], code)
                self.assertTrue(response.json()["message"])

    def test_bank_add_refuses_non_string_fields(self) -> None:
        before = (self.root / ".mcp.json").read_bytes()
        for body in ({"action": "add", "name": 123, "command": ["a"]},
                     {"action": "add", "name": "x", "command": ["a"]},
                     {"action": "add", "name": "x", "url": {"u": "https://b"}},
                     {"action": "add", "name": ["x"], "url": "https://b.example/mcp"},
                     {"action": "choose", "choice": {"c": 1}},
                     {"action": "choose", "choice": "other", "server": ["labbank"]},
                     {"action": "probe", "server": 7},
                     {"action": "search", "query": ["eeg"]},
                     {"action": ["add"]}):
            with self.subTest(body=body):
                response = self.post("bank", body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual((response.json()["ok"], response.json()["code"]), (False, "FIELD_TYPE"))
                self.assertTrue(response.json()["message"])
        self.assertEqual((self.root / ".mcp.json").read_bytes(), before)
        self.assertFalse((self.root / brief.PATH).exists())
        self.assertEqual(self.connected, [])


class ProfileTests(Case):
    def test_a_name_is_looked_up_in_openalex(self) -> None:
        data = self.ok("profile", {"text": "Ada Lovelace"})
        found = data["brief"]["profile"]
        self.assertEqual((found["source"], found["display_name"], found["works_count"]),
                         ("openalex", "Ada Lovelace", 42))
        self.assertEqual(found["topics"], [{"name": "Brain-computer interfaces", "count": 9}])

    def test_offline_answers_the_reason_and_records_it(self) -> None:
        self.openalex.offline = True
        data = self.ok("profile", {"text": "0000-0002-1825-0097"})
        found = data["brief"]["profile"]
        self.assertEqual((found["source"], found["orcid"]), ("none", "0000-0002-1825-0097"))
        self.assertIn("OpenAlex could not be reached", found["reason"])
        self.assertEqual(self.stored()["profile"]["source"], "none")

    def test_a_scholar_link_is_never_fetched(self) -> None:
        data = self.ok("profile", {"text": "https://scholar.google.com/citations?user=AbC123"})
        self.assertEqual(data["brief"]["profile"]["source"], "none")
        self.assertIn("carries no author name", data["brief"]["profile"]["reason"])
        self.assertEqual(self.openalex.calls, [])

    def test_nothing_given_is_refused(self) -> None:
        response = self.post("profile", {"text": "  "})
        self.assertEqual((response.status_code, response.json()["code"]), (422, "PROFILE_MISSING"))

    def test_draft_and_profile_refuse_non_string_text(self) -> None:
        for route, body in (("draft", {"action": "text", "text": {"a": 1}}),
                            ("draft", {"action": "check", "text": ["two", "sentences"]}),
                            ("draft", {"action": {"x": 1}}),
                            ("profile", {"text": {"name": "Ada"}}),
                            ("profile", {"name": 42}),
                            ("profile", {"orcid": ["0000-0002-1825-0097"]}),
                            ("experience", {"level": 3}),
                            ("experience", {"methods": {"a": 1}}),
                            ("experience", {"resources": ["gpu", 2]}),
                            ("experience", {"time": ["six months"]}),
                            ("interests", {"keywords": [1, 2]}),
                            ("interests", {"domain": {"d": 1}}),
                            ("interests", {"admired_paper": 9}),
                            ("choose", {"topic_ids": [1]}),
                            ("choose", {"topic_ids": ["t1"], "note": {"n": 1}})):
            with self.subTest(route=route, body=body):
                response = self.post(route, body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual((response.json()["ok"], response.json()["code"]), (False, "FIELD_TYPE"))
        self.assertFalse((self.root / brief.PATH).exists())
        self.assertEqual(self.openalex.calls, [])


class AnswerTests(Case):
    def test_experience_merges_and_validates_the_level(self) -> None:
        self.ok("experience", {"level": "student", "methods": ["deep learning", "surveys"]})
        data = self.ok("experience", {"time": "six months"})
        self.assertEqual(data["brief"]["experience"],
                         {"level": "student", "methods": ["deep learning", "surveys"], "resources": [],
                          "time": "six months"})
        response = self.post("experience", {"level": "wizard"})
        self.assertEqual((response.status_code, response.json()["code"]), (422, "LEVEL_UNKNOWN"))

    def test_interests_are_recorded(self) -> None:
        data = self.ok("interests", {"keywords": ["eeg", "domain shift", "graphs"], "domain": "neurology",
                                     "admired_paper": "Attention is all you need"})
        self.assertEqual(data["result"]["keywords"], ["eeg", "domain shift", "graphs"])
        self.assertEqual(self.stored()["interests"]["domain"], "neurology")


class TopicsAndDraftTests(Case):
    def setUp(self) -> None:
        super().setUp()
        self.ok("bank", {"action": "choose", "choice": "other", "server": "labbank"})
        self.ok("interests", {"keywords": ["eeg", "domain shift", "graphs"], "domain": "neurology"})

    def test_topics_carry_evidence_labelled_by_source(self) -> None:
        data = self.ok("topics", {"n": 3})
        topics = data["brief"]["topics"]
        self.assertEqual([t["id"] for t in topics], ["t1", "t2", "t3"][:len(topics)])
        sources = {e["source"] for t in topics for e in t["evidence"]}
        self.assertIn("operator", sources)
        self.assertIn("openalex", sources)
        self.assertIn("bank:labbank", sources)
        self.assertEqual(data["result"], topics)

    def test_choose_then_compose_check_and_approve(self) -> None:
        self.ok("topics", {"n": 3})
        chosen = self.ok("choose", {"topic_ids": ["t1", "t2"], "note": "low-cost sensors"})
        self.assertEqual(chosen["brief"]["chosen"], {"topic_ids": ["t1", "t2"], "note": "low-cost sensors"})
        composed = self.ok("draft", {"action": "compose"})
        self.assertTrue(composed["brief"]["draft"]["text"])
        self.assertFalse(composed["brief"]["draft"]["approved"])
        approved = self.ok("approve")
        self.assertTrue(approved["brief"]["draft"]["approved"])
        self.assertTrue(approved["ready"])
        self.assertEqual(approved["handoff"], "/plausibility " + approved["brief"]["draft"]["text"])
        self.assertEqual(self.client.get("/api/idea").json()["handoff"], approved["handoff"])

    def test_check_refuses_one_sentence_without_recording(self) -> None:
        result = self.ok("draft", {"action": "check", "text": "Graphs for EEG."})["result"]
        self.assertFalse(result["gate"]["ok"])
        self.assertTrue(result["gate"]["missing"])
        self.assertEqual(self.stored()["draft"]["text"], "")
        passing = self.ok("draft", {"action": "check", "text": TWO_SENTENCES})["result"]
        self.assertTrue(passing["gate"]["ok"], passing)

    def test_approve_refuses_while_the_gate_fails(self) -> None:
        self.ok("draft", {"action": "text", "text": "Graphs for EEG."})
        response = self.post("approve")
        self.assertEqual((response.status_code, response.json()["code"]), (422, "DRAFT_GATE_FAILED"))
        self.assertFalse(self.stored()["draft"]["approved"])
        self.ok("draft", {"action": "text", "text": TWO_SENTENCES})
        self.assertTrue(self.ok("approve")["ready"])

    def test_compose_without_a_pick_and_an_unknown_topic_are_refused(self) -> None:
        self.ok("topics", {"n": 3})
        self.assertEqual(self.post("draft", {"action": "compose"}).json()["code"], "TOPIC_MISSING")
        self.assertEqual(self.post("choose", {"topic_ids": ["t9"]}).json()["code"], "TOPIC_UNKNOWN")


class GuardTests(Case):
    def test_every_post_rejects_a_cross_origin_request(self) -> None:
        for route in ("bank", "profile", "experience", "interests", "topics", "choose", "draft", "approve"):
            with self.subTest(route=route):
                response = self.post(route, {"action": "choose", "choice": "none"}, Origin="https://evil.example")
                self.assertEqual(response.status_code, 403)
        self.assertFalse((self.root / brief.PATH).exists())

    def test_idea_posts_reject_foreign_origin(self) -> None:
        mcp_before = (self.root / ".mcp.json").read_bytes()
        bodies = {"bank": {"action": "add", "name": "evilbank", "url": "https://evil.example/mcp"},
                  "profile": {"text": "Ada Lovelace"}, "experience": {"level": "student"},
                  "interests": {"keywords": ["eeg"]}, "topics": {"n": 3}, "choose": {"topic_ids": ["t1"]},
                  "draft": {"action": "text", "text": TWO_SENTENCES}, "approve": {}}
        for origin in ("https://evil.example", "http://127.0.0.1.evil.example", "null"):
            for route, body in bodies.items():
                with self.subTest(origin=origin, route=route):
                    response = self.post(route, body, Origin=origin)
                    self.assertEqual(response.status_code, 403)
                    self.assertFalse(response.json()["ok"])
        self.assertEqual((self.root / ".mcp.json").read_bytes(), mcp_before)
        self.assertFalse((self.root / brief.PATH).exists())
        self.assertEqual((self.connected, self.openalex.calls), ([], []))

    def test_a_body_that_is_not_json_is_an_empty_request(self) -> None:
        response = self.client.post("/api/idea/experience", content=b"not json",
                                    headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse((self.root / brief.PATH).exists())

    def test_status_codes_of_refusals(self) -> None:
        self.assertEqual(idea_view.status_of(brief.IdeaError("BRIEF_UNREADABLE", "x")), 409)
        self.assertEqual(idea_view.status_of(brief.IdeaError("MCP_CONFIG_UNREADABLE", "x")), 409)
        self.assertEqual(idea_view.status_of(brief.IdeaError("TOPIC_MISSING", "x")), 422)

    def test_the_plausibility_suggest_route_still_answers(self) -> None:
        response = self.client.post("/api/plausibility/suggest", json={"keywords": ["eeg"]})
        self.assertEqual((response.status_code, response.json()["code"]), (422, "KEYWORDS_INVALID"))


if __name__ == "__main__":
    unittest.main()
