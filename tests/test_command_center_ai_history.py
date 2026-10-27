"""The Historia con IA pane: each phase with its gate, coloured red (not run
yet), orange (errors, rework or user iterations) or green (passed directly),
and a click-through timeline of decisions, revisions and chat turns."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import ai_history, ai_transcripts, server

REPO = Path(__file__).resolve().parents[1]
PAGE = (REPO / "skills" / "_core" / "command_center" / "static" / "index.html").read_text(encoding="utf-8")


def _fase(stage: str, status: str, number: int, gate: str) -> dict:
    return {"id": f"Fase {number}", "stage_id": stage, "name": f"Fase {number}",
            "gate": gate, "status": status, "agent": "agent"}


def _line(kind: str, content, ts: str, **extra) -> str:
    return json.dumps({"type": kind, "timestamp": ts,
                       "message": {"role": kind, "content": content}, **extra})


class AiHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.root = base / "ws"
        self.root.mkdir()
        self.chats = base / "chats"
        self.chats.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _build(self, fases: list[dict]) -> dict[str, dict]:
        view = ai_history.build_ai_history(
            self.root, fases, sessions={"claude-code": self.chats, "pi": None, "opencode": None})
        return {p["stage_id"]: p for p in view["phases"]}

    def test_colours_follow_status_and_friction(self) -> None:
        (self.chats / "s1.jsonl").write_text("\n".join([
            _line("user", "<command-name>/plausibility</command-name><command-args>idea</command-args>",
                  "2026-10-01T10:00:00Z"),
            _line("assistant", [{"type": "text", "text": "Informe listo."}], "2026-10-01T10:01:00Z"),
            _line("user", "/paper-ingestion paper.pdf", "2026-10-01T11:00:00Z"),
            _line("assistant", [{"type": "text", "text": "Ingerido."}], "2026-10-01T11:01:00Z"),
            _line("user", "corrige la ecuación 3", "2026-10-01T11:02:00Z"),
            _line("user", [{"type": "tool_result", "is_error": True, "content": "boom"}],
                  "2026-10-01T11:03:00Z"),
        ]), encoding="utf-8")
        phases = self._build([
            _fase("plausibility", "PASS", 2, "G-SOTA"),
            _fase("ingestion", "PASS", 3, "G-INGEST"),
            _fase("writing", "PENDING", 8, "G-WRITING"),
        ])
        self.assertEqual(phases["plausibility"]["color"], "green")
        self.assertEqual(phases["ingestion"]["color"], "orange")
        self.assertEqual(phases["ingestion"]["counts"]["user_messages"], 1)
        self.assertEqual(phases["ingestion"]["counts"]["errors"], 1)
        self.assertEqual(phases["writing"]["color"], "red")
        self.assertEqual(phases["writing"]["gate"], "G-WRITING")
        kinds = [e["kind"] for e in phases["plausibility"]["events"]]
        self.assertEqual(kinds, ["command", "agent_reply"])

    def test_paper_writing_mark_goes_to_declarations(self) -> None:
        (self.chats / "s.jsonl").write_text(
            _line("user", "/paper-writing mark funding none", "2026-10-02T09:00:00Z"), encoding="utf-8")
        phases = self._build([_fase("declarations", "PENDING", 7, "G-DECLARATIONS"),
                              _fase("writing", "PENDING", 8, "G-WRITING")])
        self.assertEqual(phases["declarations"]["counts"]["commands"], 1)
        self.assertEqual(phases["writing"]["counts"]["commands"], 0)

    def test_several_proposal_revisions_count_as_rework(self) -> None:
        (self.root / "proposals").mkdir()
        for n in (1, 2):
            (self.root / "proposals" / f"research-concept-x-r{n:02d}.md").write_text("x", encoding="utf-8")
        phases = self._build([_fase("proposal", "PASS", 4, "G-PROP")])
        self.assertEqual(phases["proposal"]["color"], "orange")
        self.assertEqual(phases["proposal"]["counts"]["revisions"], 2)

    def test_missing_transcripts_never_fail(self) -> None:
        view = ai_history.build_ai_history(
            self.root, [_fase("harness", "PASS", 1, "G-HARNESS")],
            sessions={"claude-code": self.root / "nope", "pi": self.root / "nope",
                      "opencode": self.root / "nope.db"})
        chats = view["sources"]["chats"]
        self.assertEqual({k: v["status"] for k, v in chats.items()},
                         {"claude-code": "absent", "pi": "absent", "opencode": "absent",
                          "antigravity": "unsupported"})
        self.assertEqual(view["phases"][0]["color"], "green")

    def test_endpoint_and_tab_sit_before_telemetry(self) -> None:
        paths = {r.path for r in server.create_app(REPO).routes if hasattr(r, "path")}
        self.assertIn("/api/ai-history", paths)
        self.assertLess(PAGE.index("navigateTab('historia')"), PAGE.index("navigateTab('telemetria')"))
        self.assertIn('id="pane-historia"', PAGE)
        self.assertIn("ai-history-panel.js", PAGE)


class HarnessTranscriptTests(unittest.TestCase):
    """Claude Code, Pi and OpenCode sessions land in the same phases; the
    stores are found on macOS, Linux and WSL paths alike."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.root = self.base / "ws"
        self.root.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_every_harness_command_shape_is_recognised(self) -> None:
        shapes = {
            "<command-name>/plausibility</command-name><command-args>idea</command-args>": ("plausibility", "idea"),
            '<skill name="plausibility" location="x">body</skill>\n\nidea': ("plausibility", "idea"),
            "Read `skills/plausibility/SKILL.md` and follow it for this task. "
            "Treat the text below as `$ARGUMENTS`:\n\nidea": ("plausibility", "idea"),
            "/skill:plausibility idea": ("plausibility", "idea"),
            "/plausibility idea": ("plausibility", "idea"),
            "lee skills/plausibility/SKILL.md por favor": None,
        }
        for text, expected in shapes.items():
            with self.subTest(text=text[:30]):
                self.assertEqual(ai_transcripts.command_of(text), expected)

    def test_pi_sessions_attribute_commands_replies_and_errors(self) -> None:
        sessions = self.base / "pi"
        sessions.mkdir()
        rows = [
            {"type": "session", "cwd": str(self.root), "timestamp": "2026-10-01T00:00:00Z"},
            {"type": "message", "timestamp": "2026-10-01T00:00:01Z", "message": {"role": "user", "content": [
                {"type": "text", "text": '<skill name="paper-ingestion">x</skill>\n\npaper.pdf'}]}},
            {"type": "message", "timestamp": "2026-10-01T00:00:02Z",
             "message": {"role": "toolResult", "isError": True, "content": []}},
            {"type": "message", "timestamp": "2026-10-01T00:00:03Z", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "Ingerido."}]}},
        ]
        (sessions / "s.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        events, status = ai_transcripts.read_all(self.root, {"claude-code": None, "pi": sessions, "opencode": None})
        self.assertEqual(status["pi"], {"status": "ok", "sessions": 1})
        self.assertEqual([e["kind"] for e in events["ingestion"]], ["command", "error", "agent_reply"])

    def test_opencode_sessions_are_read_from_its_database(self) -> None:
        db = self.base / "opencode.db"
        con = sqlite3.connect(db)
        con.executescript(
            "CREATE TABLE session (id text, directory text, parent_id text, time_updated integer);"
            "CREATE TABLE message (id text, session_id text, data text);"
            "CREATE TABLE part (id text, message_id text, session_id text, time_created integer, data text);")
        con.execute("INSERT INTO session VALUES ('ses_1', ?, NULL, 1)", (str(self.root),))
        con.execute("INSERT INTO session VALUES ('ses_2', '/elsewhere', NULL, 2)")
        con.execute("INSERT INTO message VALUES ('m1', 'ses_1', ?)", (json.dumps({"role": "user"}),))
        con.execute("INSERT INTO message VALUES ('m2', 'ses_1', ?)", (json.dumps({"role": "assistant"}),))
        for pid, mid, ts, data in (
            ("p1", "m1", 1790000000000, {"type": "text", "text": "Read `skills/proposal-deliberation/SKILL.md` "
                                         "and follow it for this task. Treat the text below as `$ARGUMENTS`:\n\nr02"}),
            ("p2", "m1", 1790000000001, {"type": "text", "synthetic": True, "text": "Called the Read tool"}),
            ("p3", "m2", 1790000000002, {"type": "tool", "state": {"status": "error"}}),
            ("p4", "m2", 1790000000003, {"type": "text", "text": "Revisión lista."}),
        ):
            con.execute("INSERT INTO part VALUES (?, ?, 'ses_1', ?, ?)", (pid, mid, ts, json.dumps(data)))
        con.commit()
        con.close()
        events, status = ai_transcripts.read_all(self.root, {"claude-code": None, "pi": None, "opencode": db})
        self.assertEqual(status["opencode"], {"status": "ok", "sessions": 1})
        kinds = [e["kind"] for e in events["proposal"]]
        self.assertEqual(kinds, ["command", "error", "agent_reply"])
        self.assertTrue(events["proposal"][0]["ts"].endswith("Z"))

    def test_stores_are_found_by_slug_or_by_recorded_cwd(self) -> None:
        claude = self.base / "claude" / "projects"
        renamed = claude / "some-truncated-slug"
        renamed.mkdir(parents=True)
        (renamed / "s.jsonl").write_text(json.dumps({"type": "user", "cwd": str(self.root)}), encoding="utf-8")
        pi = self.base / "pi"
        (pi / "sessions" / "--C--Users-ana-paper--").mkdir(parents=True)
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.base / "claude"),
                                          "PI_CODING_AGENT_DIR": str(pi)}):
            os.environ.pop("PAPERSMITH_CLAUDE_CODE_SESSIONS", None)
            os.environ.pop("PAPERSMITH_PI_SESSIONS", None)
            self.assertEqual(ai_transcripts.claude_dir({str(self.root)}), renamed)
            self.assertEqual(ai_transcripts.pi_dir({"C:\\Users\\ana\\paper"}),
                             pi / "sessions" / "--C--Users-ana-paper--")


if __name__ == "__main__":
    unittest.main()
