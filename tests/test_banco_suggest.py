"""The dashboard's thematic help: a stdlib MCP client for banco-lia and the
endpoint that turns 3 to 5 keywords into ranked LIA items, topics and a
proposed /plausibility idea. Every test talks to a fake stdio MCP server
(tests/fixtures/banco_lia/fake_mcp.py) chosen through
PAPERSMITH_BANCO_LIA_COMMAND; none needs uvx or the network."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from skills._core.command_center import banco_suggest, localize, server

FAKE = Path(__file__).resolve().parent / "fixtures" / "banco_lia" / "fake_mcp.py"
SIGNAL = ["signal", "processing", "filters"]
EEG = ["eeg", "quantum", "classification"]


def sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if re.search(r"\w", part)]


class FakeServerCase(unittest.TestCase):
    """Points the client at the fake server; ``env`` selects its misbehaviour."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "calls.jsonl"
        self.pidfile = Path(self.tmp.name) / "pid"
        self.use({})

    def use(self, extra: dict[str, str], command: list[str] | None = None) -> None:
        patcher = mock.patch.dict(os.environ, {
            "PAPERSMITH_BANCO_LIA_COMMAND": json.dumps(command or [sys.executable, str(FAKE)]),
            "FAKE_MCP_LOG": str(self.log), "FAKE_MCP_PIDFILE": str(self.pidfile), **extra})
        patcher.start()
        self.addCleanup(patcher.stop)

    def calls(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def assert_child_gone(self) -> None:
        self.assertTrue(self.pidfile.exists(), "the fake server never started")
        pid = int(self.pidfile.read_text(encoding="utf-8"))
        deadline = time.time() + 3
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        self.fail(f"child process {pid} is still running")


class KeywordValidationTests(unittest.TestCase):
    def refused(self, keywords) -> str:
        with self.assertRaises(banco_suggest.KeywordsInvalid) as ctx:
            banco_suggest.normalize_keywords(keywords)
        self.assertEqual(ctx.exception.code, "KEYWORDS_INVALID")
        return str(ctx.exception)

    def test_two_and_six_keywords_are_refused_naming_the_rule(self) -> None:
        self.assertIn("3 to 5", self.refused(["eeg", "quantum"]))
        self.assertIn("3 to 5", self.refused(["a", "b", "c", "d", "e", "f"]))

    def test_three_to_five_are_accepted_and_trimmed(self) -> None:
        self.assertEqual(banco_suggest.normalize_keywords(["  eeg ", "quantum", "svm"]), ["eeg", "quantum", "svm"])
        self.assertEqual(len(banco_suggest.normalize_keywords(list("abcde"))), 5)

    def test_duplicates_are_dropped_case_insensitively_before_counting(self) -> None:
        self.assertEqual(banco_suggest.normalize_keywords(["EEG", "eeg", "Quantum", "svm"]), ["EEG", "Quantum", "svm"])
        self.assertIn("3 to 5", self.refused(["EEG", "eeg", "quantum"]))

    def test_empty_blank_and_non_text_keywords_are_refused(self) -> None:
        self.assertIn("empty", self.refused(["eeg", "", "quantum", "svm"]))
        self.assertIn("empty", self.refused(["eeg", "   ", "quantum", "svm"]))
        self.refused("eeg quantum svm")
        self.refused(None)
        self.refused(["eeg", 7, "quantum"])

    def test_a_keyword_over_40_characters_is_refused(self) -> None:
        self.assertIn("40", self.refused(["eeg", "quantum", "x" * 41]))
        self.assertEqual(banco_suggest.normalize_keywords(["eeg", "quantum", "x" * 40])[2], "x" * 40)

    def test_suggest_refuses_before_starting_any_server(self) -> None:
        with mock.patch.dict(os.environ, {"PAPERSMITH_BANCO_LIA_COMMAND": json.dumps(["/does/not/exist"])}):
            with self.assertRaises(banco_suggest.KeywordsInvalid):
                banco_suggest.suggest(["eeg", "quantum"], "es")


class CommandResolutionTests(unittest.TestCase):
    def test_env_override_wins_then_mcp_json_then_the_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"banco-lia": {
                "command": "my-uvx", "args": ["--from", "somewhere", "banco-lia-mcp"]}}}), encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("PAPERSMITH_BANCO_LIA_COMMAND", None)
                self.assertEqual(banco_suggest.resolve_command(root), ["my-uvx", "--from", "somewhere", "banco-lia-mcp"])
                self.assertEqual(banco_suggest.resolve_command(Path(tmp) / "empty"), banco_suggest.DEFAULT_COMMAND)
                os.environ["PAPERSMITH_BANCO_LIA_COMMAND"] = json.dumps(["fake", "--x"])
                self.assertEqual(banco_suggest.resolve_command(root), ["fake", "--x"])

    def test_the_default_is_the_command_papersmith_registers_for_agents(self) -> None:
        self.assertEqual(banco_suggest.DEFAULT_COMMAND, [
            "uvx", "--from", "git+https://github.com/LIAUNAL/bancoProyectosPapersLIA", "banco-lia-mcp"])

    def test_a_broken_mcp_json_falls_back_to_the_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".mcp.json").write_text("{not json", encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("PAPERSMITH_BANCO_LIA_COMMAND", None)
                self.assertEqual(banco_suggest.resolve_command(Path(tmp)), banco_suggest.DEFAULT_COMMAND)

    def test_a_malformed_env_override_is_unavailable_not_an_exception(self) -> None:
        with mock.patch.dict(os.environ, {"PAPERSMITH_BANCO_LIA_COMMAND": "uvx banco"}):
            result = banco_suggest.suggest(EEG, "es")
        self.assertFalse(result["available"])
        self.assertIn("PAPERSMITH_BANCO_LIA_COMMAND", result["reason"])


class SuggestTests(FakeServerCase):
    def test_all_match_is_tried_first_and_kept_when_it_returns_three_items(self) -> None:
        result = banco_suggest.suggest(SIGNAL, "es")
        self.assertTrue(result["available"])
        self.assertEqual(result["match"], "all")
        self.assertEqual(result["keywords"], SIGNAL)
        searches = [c for c in self.calls() if c["name"] == "search_bank"]
        self.assertEqual([c["arguments"]["match"] for c in searches], ["all"])
        self.assertEqual(searches[0]["arguments"]["query"], "signal processing filters")
        self.assert_child_gone()

    def test_fewer_than_three_matches_fall_back_to_any(self) -> None:
        result = banco_suggest.suggest(EEG, "es")
        searches = [c["arguments"]["match"] for c in self.calls() if c["name"] == "search_bank"]
        self.assertEqual(searches, ["all", "any"])
        self.assertEqual(result["match"], "any")
        self.assertEqual([i["id"] for i in result["items"]][:3], ["A001", "A002", "H0001"])

    def test_items_are_capped_at_eight_best_first_with_the_documented_fields(self) -> None:
        items = banco_suggest.suggest(SIGNAL, "es")["items"]
        self.assertEqual(len(items), 8)
        self.assertEqual([i["id"] for i in items], [f"S{n:02d}" for n in range(1, 9)])
        scores = [i["score"] for i in items]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(set(items[0]), {"id", "kind", "title", "year", "cluster", "doi", "score", "snippet"})
        self.assertEqual(items[0]["doi"], "10.1000/signal-1")
        project = next(i for i in items if i["id"] == "S03")
        self.assertEqual(project["kind"], "proyecto")
        self.assertEqual(project["doi"], "")

    def test_topics_are_the_clusters_of_the_items_most_frequent_first_capped_at_five(self) -> None:
        topics = banco_suggest.suggest(SIGNAL, "es")["topics"]
        self.assertEqual(len(topics), 5)
        self.assertEqual(topics[0], {"id": "C01", "name": "Cluster name 1", "count": 2})
        self.assertEqual([t["id"] for t in topics], ["C01", "C02", "C03", "C04", "C05"])
        self.assertTrue(all(set(t) == {"id", "name", "count"} for t in topics))

    def test_a_failing_taxonomy_still_names_topics_by_id(self) -> None:
        with mock.patch.object(banco_suggest, "_taxonomy_names", return_value={}):
            topics = banco_suggest.suggest(SIGNAL, "es")["topics"]
        self.assertEqual(topics[0]["name"], "C01")

    def test_results_given_as_json_text_blocks_are_understood(self) -> None:
        self.use({"FAKE_MCP_MODE": "textonly"})
        result = banco_suggest.suggest(SIGNAL, "es")
        self.assertTrue(result["available"])
        self.assertEqual(len(result["items"]), 8)
        self.assertEqual(result["topics"][0]["name"], "Cluster name 1")

    def test_the_spanish_draft_has_two_sentences_and_names_keywords_topic_and_items(self) -> None:
        draft = banco_suggest.suggest(EEG, "es")["draft"]
        self.assertGreaterEqual(len(sentences(draft)), 2)
        for word in EEG:
            self.assertIn(word, draft)
        self.assertIn("Cluster name 5", draft)
        self.assertIn("EEG classification with quantum kernels", draft)
        self.assertIn("10.1000/quantum-eeg", draft)
        self.assertIn("H0001", draft)
        self.assertIn("antecedente", draft)
        self.assertNotIn("\n", draft)

    def test_the_english_draft_has_two_sentences_and_is_english(self) -> None:
        draft = banco_suggest.suggest(EEG, "en")["draft"]
        self.assertGreaterEqual(len(sentences(draft)), 2)
        for word in EEG:
            self.assertIn(word, draft)
        self.assertIn("Cluster name 5", draft)
        self.assertIn("10.1000/quantum-eeg", draft)
        self.assertIn("background", draft)
        self.assertNotIn("antecedente", draft)

    def test_every_draft_template_has_a_spanish_entry_with_the_same_placeholders(self) -> None:
        catalogue = json.loads(localize.CATALOGUE.read_text(encoding="utf-8"))
        names = re.compile(r"\{(\w+)\}")
        for template in banco_suggest.DRAFT_TEMPLATES:
            with self.subTest(template=template):
                self.assertIn(template, catalogue)
                self.assertEqual(set(names.findall(template)), set(names.findall(catalogue[template])))

    def test_the_draft_templates_do_not_translate_unrelated_display_strings(self) -> None:
        for text in ("Cats and dogs", "Install the project", "Plain text"):
            self.assertIsNone(localize.lookup(text), text)

    def test_the_draft_cites_at_most_three_items_and_never_calls_them_state_of_the_art(self) -> None:
        draft = banco_suggest.suggest(SIGNAL, "es")["draft"]
        self.assertEqual(len(re.findall(r"S\d\d|10\.1000/signal-\d", draft)), 3)
        self.assertIn("no como estado del arte", draft)
        self.assertIn("not as state of the art", banco_suggest.suggest(SIGNAL, "en")["draft"])

    def test_an_unknown_language_falls_back_to_spanish(self) -> None:
        self.assertEqual(banco_suggest.suggest(EEG, "fr")["draft"], banco_suggest.suggest(EEG, "es")["draft"])

    def test_an_empty_bank_still_drafts_an_idea_with_the_keywords(self) -> None:
        for language, note in (("es", "no tiene trabajo relacionado"), ("en", "holds no related work")):
            result = banco_suggest.suggest(["zzz", "yyy", "xxx"], language)
            self.assertTrue(result["available"])
            self.assertEqual((result["items"], result["topics"]), ([], []))
            self.assertGreaterEqual(len(sentences(result["draft"])), 2)
            for word in ("zzz", "yyy", "xxx", note):
                self.assertIn(word, result["draft"])
        self.assert_child_gone()


class UnavailableTests(FakeServerCase):
    def assert_unavailable(self, result: dict, *fragments: str) -> None:
        self.assertIs(result["available"], False)
        self.assertEqual(set(result), {"available", "reason"})
        self.assertTrue(result["reason"].strip())
        self.assertNotIn("\n", result["reason"])
        for fragment in fragments:
            self.assertIn(fragment, result["reason"])

    def test_a_missing_command_is_unavailable_and_names_the_command(self) -> None:
        self.use({}, command=["/does/not/exist/banco-lia-mcp"])
        self.assert_unavailable(banco_suggest.suggest(EEG, "es"), "banco-lia-mcp")

    def test_a_server_that_hangs_times_out_and_is_terminated(self) -> None:
        self.use({"FAKE_MCP_MODE": "hang"})
        started = time.time()
        self.assert_unavailable(banco_suggest.suggest(EEG, "es", timeout=1), "timed out")
        self.assertLess(time.time() - started, 10)
        self.assert_child_gone()

    def test_a_server_that_ignores_sigterm_is_killed(self) -> None:
        self.use({"FAKE_MCP_MODE": "stubborn"})
        with mock.patch.object(banco_suggest, "TERMINATE_GRACE", 0.3):
            self.assert_unavailable(banco_suggest.suggest(EEG, "es", timeout=1), "timed out")
        self.assert_child_gone()

    def test_malformed_json_rpc_is_unavailable(self) -> None:
        self.use({"FAKE_MCP_MODE": "malformed"})
        self.assert_unavailable(banco_suggest.suggest(EEG, "es", timeout=5), "malformed")
        self.assert_child_gone()

    def test_a_server_that_exits_at_once_is_unavailable(self) -> None:
        self.use({"FAKE_MCP_MODE": "crash"})
        self.assert_unavailable(banco_suggest.suggest(EEG, "es", timeout=5), "closed")
        self.assert_child_gone()

    def test_a_tool_error_is_unavailable_with_the_servers_message(self) -> None:
        self.use({"FAKE_MCP_MODE": "toolerror"})
        self.assert_unavailable(banco_suggest.suggest(EEG, "es", timeout=5), "index is being rebuilt")
        self.assert_child_gone()

    def test_a_command_that_is_not_an_mcp_server_is_unavailable(self) -> None:
        self.use({}, command=[sys.executable, "-c", "print('hello')"])
        self.assert_unavailable(banco_suggest.suggest(EEG, "es", timeout=5))

    def test_the_timeout_comes_from_the_environment_when_not_given(self) -> None:
        self.use({"PAPERSMITH_BANCO_LIA_TIMEOUT": "7"})
        self.assertEqual(banco_suggest.timeout_seconds(), 7.0)
        self.use({"PAPERSMITH_BANCO_LIA_TIMEOUT": "soon"})
        self.assertEqual(banco_suggest.timeout_seconds(), banco_suggest.DEFAULT_TIMEOUT)
        self.assertEqual(banco_suggest.DEFAULT_TIMEOUT, 90.0)


class SuggestEndpointTests(FakeServerCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = Path(self.tmp.name) / "workspace"
        self.root.mkdir()
        self.client = TestClient(server.create_app(self.root))

    def post(self, body, **headers):
        return self.client.post("/api/plausibility/suggest", json=body, headers=headers)

    def test_a_cross_origin_post_is_rejected(self) -> None:
        response = self.post({"keywords": EEG, "language": "es"}, origin="https://evil.example")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.calls(), [])

    def test_invalid_keywords_answer_422_with_the_refusal(self) -> None:
        response = self.post({"keywords": ["eeg", "quantum"], "language": "es"})
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["code"], "KEYWORDS_INVALID")
        self.assertIn("3 to 5", body["error"])
        self.assertEqual(self.calls(), [])

    def test_a_body_without_keywords_or_not_json_answers_422(self) -> None:
        self.assertEqual(self.post({"language": "es"}).status_code, 422)
        response = self.client.post("/api/plausibility/suggest", content=b"not json",
                                    headers={"content-type": "application/json"})
        self.assertEqual(response.status_code, 422)

    def test_a_valid_request_answers_200_with_the_suggestion(self) -> None:
        response = self.post({"keywords": EEG, "language": "en"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"available", "keywords", "match", "items", "topics", "draft"})
        self.assertTrue(body["available"])
        self.assertEqual(body["keywords"], EEG)
        self.assertEqual(body["items"][0]["id"], "A001")
        self.assertIn("background", body["draft"])

    def test_the_language_defaults_to_spanish(self) -> None:
        body = self.post({"keywords": EEG}).json()
        self.assertIn("antecedente", body["draft"])

    def test_an_unavailable_bank_is_still_a_200(self) -> None:
        self.use({"FAKE_MCP_MODE": "crash"})
        response = self.post({"keywords": EEG, "language": "es"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])
        self.assertTrue(response.json()["reason"])

    def test_the_endpoint_never_writes_to_the_workspace(self) -> None:
        self.post({"keywords": EEG, "language": "es"})
        self.assertEqual(list(self.root.rglob("*")), [])

    def test_the_workspace_mcp_json_is_the_command_when_no_override_is_set(self) -> None:
        self.use({})
        os.environ.pop("PAPERSMITH_BANCO_LIA_COMMAND")
        (self.root / ".mcp.json").write_text(json.dumps({"mcpServers": {"banco-lia": {
            "command": sys.executable, "args": [str(FAKE)]}}}), encoding="utf-8")
        body = self.post({"keywords": EEG, "language": "es"}).json()
        self.assertTrue(body["available"])
        self.assertEqual(body["items"][0]["id"], "A001")


class SkillDoctrineTests(unittest.TestCase):
    def test_the_plausibility_skill_treats_a_dashboard_draft_like_any_idea(self) -> None:
        skill = (Path(__file__).resolve().parent.parent / "skills" / "plausibility" / "SKILL.md").read_text(encoding="utf-8")
        text = " ".join(skill.split())
        self.assertIn("thematic help", text)
        self.assertIn("two-sentence minimum still applies", text)
        self.assertIn("never SOTA evidence", text)


if __name__ == "__main__":
    unittest.main()
