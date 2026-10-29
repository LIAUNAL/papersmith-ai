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

    def test_operator_rounds_form_a_decision_graph(self) -> None:
        (self.chats / "s.jsonl").write_text("\n".join([
            _line("user", "/proposal-deliberation idea", "2026-10-03T10:00:00Z"),
            _line("user", "<task-notification><task-id>a1</task-id><status>completed</status></task-notification>",
                  "2026-10-03T10:00:30Z"),
            _line("assistant", [{"type": "text", "text": "Revisión r01 lista."}], "2026-10-03T10:01:00Z"),
            _line("user", "corrige la ecuación 3, está mal", "2026-10-03T10:02:00Z"),
            _line("assistant", [{"type": "text", "text": "Corregida."}], "2026-10-03T10:03:00Z"),
            _line("user", "ahora añade la hipótesis H2", "2026-10-03T10:04:00Z"),
            _line("assistant", [{"type": "text", "text": "Añadida."}], "2026-10-03T10:05:00Z"),
            _line("user", "aprobado", "2026-10-03T10:06:00Z"),
            _line("user", "/paper-writing intro", "2026-10-03T11:00:00Z"),
            _line("user", [{"type": "tool_result", "is_error": True, "content": "boom"}],
                  "2026-10-03T11:01:00Z"),
            _line("user", "reintenta la intro", "2026-10-03T11:02:00Z"),
            _line("assistant", [{"type": "text", "text": "Intro escrita."}], "2026-10-03T11:03:00Z"),
        ]), encoding="utf-8")
        view = ai_history.build_ai_history(
            self.root, [_fase("proposal", "PASS", 4, "G-PROP"), _fase("writing", "ACTIVE", 8, "G-WRITING")],
            sessions={"claude-code": self.chats, "pi": None, "opencode": None})
        proposal, writing = view["phases"]

        rounds = proposal["rounds"]
        self.assertEqual([r["outcome"] for r in rounds], ["rework", "iteration", "success"])
        self.assertEqual([r["prompt"] for r in rounds],
                         ["/proposal-deliberation idea", "corrige la ecuación 3, está mal",
                          "ahora añade la hipótesis H2"])
        self.assertEqual([r["reply"] for r in rounds], ["Revisión r01 lista.", "Corregida.", "Añadida."])
        self.assertIn("approved", rounds[2]["reason"].lower())
        self.assertEqual(proposal["decision_summary"],
                         {"success": 1, "rework": 1, "iteration": 1, "pending": 0})
        # Each round names its events, and every operator turn and the reply
        # that answers it are the phase's main interactions.
        by_id = {e["id"]: e for e in proposal["events"]}
        self.assertEqual([by_id[i]["kind"] for i in rounds[0]["events"]], ["command", "agent_reply"])
        self.assertEqual({e["round"] for e in proposal["events"]}, {1, 2, 3})
        self.assertTrue(all(e["key"] for e in proposal["events"]))

        self.assertEqual([r["outcome"] for r in writing["rounds"]], ["rework", "pending"])
        self.assertIn("error", writing["rounds"][0]["reason"].lower())
        self.assertEqual(view["decision_summary"],
                         {"success": 1, "rework": 2, "iteration": 1, "pending": 1})
        self.assertEqual(view["pending"], [{"stage_id": "writing", "id": "Fase 8", "round": 2,
                                            "prompt": "reintenta la intro"}])

    def test_persisted_decisions_open_their_own_rounds(self) -> None:
        def ev(kind: str, ts, summary: str, source: str = "experiment") -> dict:
            return {"ts": ts, "source": source, "kind": kind, "summary": summary, "ref": ""}
        events = [
            ev("revision_receipt", "2026-10-04T09:00:00Z", "Created initial revision r01"),
            ev("submitted", "2026-10-04T10:00:00Z", "Submitted run.py to kaggle", "remote-execution"),
            ev("errored", "2026-10-04T10:05:00Z", "Errored: OOM", "remote-execution"),
            ev("submitted", "2026-10-04T11:00:00Z", "Submitted run.py to kaggle", "remote-execution"),
            ev("returned", "2026-10-04T12:00:00Z", "Returned s2", "remote-execution"),
            ev("revision_receipt", None, "Revision r01 -> r02 (tighten), 3 patches"),
            ev("revision", None, "Revisión r02 de la propuesta", "revisions"),
        ]
        rounds = ai_history.decision_rounds("ACTIVE", events)
        self.assertEqual([(r["kind"], r["outcome"]) for r in rounds],
                         [("decision", "iteration"), ("decision", "rework"),
                          ("decision", "iteration"), ("decision", "pending")])
        self.assertEqual(rounds[2]["reply"], "Returned s2")
        self.assertTrue(events[4]["key"])
        self.assertIsNone(events[-1]["round"])

    def test_decision_graph_is_drawn_and_filters_main_interactions(self) -> None:
        panel = (REPO / "skills" / "_core" / "command_center" / "static" / "ai-history-panel.js").read_text(encoding="utf-8")
        self.assertIn('class="aih-dgraph', panel)
        self.assertIn("aih.mainOnly", panel)
        self.assertIn("aih-ev--hl", panel)
        self.assertIn(".aih-round {", PAGE)

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

    def test_events_and_phase_artifacts_carry_openable_paths(self) -> None:
        (self.root / "proposals").mkdir()
        for n in (1, 2):
            (self.root / "proposals" / f"research-concept-x-r{n:02d}.md").write_text("x", encoding="utf-8")
        (self.root / "proposals" / ".hidden.md").write_text("x", encoding="utf-8")
        (self.root / "proposals" / "x.sky.json").write_text("{}", encoding="utf-8")
        phase = self._build([_fase("proposal", "PASS", 4, "G-PROP")])["proposal"]
        self.assertEqual({e["path"] for e in phase["events"] if e["kind"] == "revision"},
                         {"proposals/research-concept-x-r01.md", "proposals/research-concept-x-r02.md"})
        self.assertEqual(sorted(a["path"] for a in phase["artifacts"]),
                         ["proposals/research-concept-x-r01.md", "proposals/research-concept-x-r02.md",
                          "proposals/x.sky.json"])
        self.assertEqual({a["label"] for a in phase["artifacts"]},
                         {"Proposal revisions", "Proposal sky"})

    def test_a_matched_directory_lists_its_files(self) -> None:
        impl = self.root / "implementations" / "Model"
        impl.mkdir(parents=True)
        (impl / "train.py").write_text("x", encoding="utf-8")
        phase = self._build([_fase("poc_experiments", "ACTIVE", 5, "G-EXP-POC")])["poc_experiments"]
        self.assertEqual([a["path"] for a in phase["artifacts"]], ["implementations/Model/train.py"])

    def test_only_files_inside_the_workspace_get_a_path(self) -> None:
        (self.root / "paper").mkdir()
        (self.root / "paper" / "main.tex").write_text("x", encoding="utf-8")
        (self.root.parent / "secret.txt").write_text("x", encoding="utf-8")
        resolve = ai_history._workspace_file
        root = self.root.resolve()
        self.assertEqual(resolve(root, "paper/main.tex#funding"), "paper/main.tex")
        for ref in ("../secret.txt", "paper", "claude-code:abcd1234", "nope.md", None, ""):
            with self.subTest(ref=ref):
                self.assertIsNone(resolve(root, ref))

    def test_missing_transcripts_never_fail(self) -> None:
        view = ai_history.build_ai_history(
            self.root, [_fase("harness", "PASS", 1, "G-HARNESS")],
            sessions={"claude-code": self.root / "nope", "pi": self.root / "nope",
                      "opencode": self.root / "nope.db"})
        chats = view["sources"]["chats"]
        self.assertEqual({k: v["status"] for k, v in chats.items()},
                         {"claude-code": "absent", "pi": "absent", "opencode": "absent",
                          "antigravity": "absent"})
        self.assertEqual(view["phases"][0]["color"], "green")

    def test_endpoint_and_tab_sit_before_telemetry(self) -> None:
        paths = {r.path for r in server.create_app(REPO).routes if hasattr(r, "path")}
        self.assertIn("/api/ai-history", paths)
        self.assertLess(PAGE.index("navigateTab('historia')"), PAGE.index("navigateTab('telemetria')"))
        self.assertIn('id="pane-historia"', PAGE)
        self.assertIn("ai-history-panel.js", PAGE)

    def test_artifact_links_open_in_a_window_styled_like_the_artefactos_viewer(self) -> None:
        panel = (REPO / "skills" / "_core" / "command_center" / "static" / "ai-history-panel.js").read_text(encoding="utf-8")
        self.assertIn('role="dialog"', panel)
        self.assertIn("window.renderArtifactDoc(text, path)", panel)
        self.assertIn('class="artifact-web-article"', panel)
        self.assertIn("/api/artifact?file=", panel)
        self.assertIn(".aih-modal {", PAGE)
        self.assertIn("function renderArtifactDoc(", PAGE)


class HarnessTranscriptTests(unittest.TestCase):
    """Claude Code, Pi and OpenCode sessions land in the same phases; the
    stores are found on macOS, Linux and WSL paths alike."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.root = self.base / "ws"
        self.root.mkdir()
        ai_transcripts.clear_cache()
        self.addCleanup(ai_transcripts.clear_cache)

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

    def test_session_reads_are_incremental(self) -> None:
        path = self.base / "s.jsonl"
        first = _line("user", "/plausibility idea", "2026-10-01T10:00:00Z")
        path.write_text(first + "\n", encoding="utf-8")
        reader, markers = ai_transcripts.LINE_READERS["claude-code"]
        self.assertEqual(len(ai_transcripts.session_turns(path, reader, markers)), 1)
        reply = _line("assistant", [{"type": "text", "text": "Listo."}], "2026-10-01T10:01:00Z")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(reply + "\n" + reply[:20])  # a complete line and a half-written one
        with mock.patch.object(ai_transcripts.json, "loads", wraps=json.loads) as loads:
            turns = ai_transcripts.session_turns(path, reader, markers)
        self.assertEqual([t[1] for t in turns], ["user", "assistant"])
        self.assertEqual(loads.call_count, 2)  # the new line, and the half one that fails
        with path.open("a", encoding="utf-8") as handle:
            handle.write(reply[20:] + "\n")
        self.assertEqual(len(ai_transcripts.session_turns(path, reader, markers)), 3)
        path.write_text(first + "\n", encoding="utf-8")  # replaced by a shorter session
        self.assertEqual(len(ai_transcripts.session_turns(path, reader, markers)), 1)

    def test_lines_without_a_turn_are_skipped_before_parsing(self) -> None:
        path = self.base / "s.jsonl"
        noise = json.dumps({"type": "progress", "data": "x" * 50})
        path.write_text("\n".join([noise] * 50 + [_line("user", "/plausibility idea", "t")]) + "\n",
                        encoding="utf-8")
        reader, markers = ai_transcripts.LINE_READERS["claude-code"]
        with mock.patch.object(ai_transcripts.json, "loads", wraps=json.loads) as loads:
            turns = ai_transcripts.session_turns(path, reader, markers)
        self.assertEqual(len(turns), 1)
        self.assertEqual(loads.call_count, 1)

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
