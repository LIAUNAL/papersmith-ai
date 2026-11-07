"""The persistent AI history archive and what the graph reads from it."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import ai_archive, ai_history, ai_transcripts, server

LONG = "explain the gradient " * 40
NONE = {"pi": None, "opencode": None, "antigravity": None}


def _line(kind: str, content, ts: str, **extra) -> str:
    return json.dumps({"type": kind, "timestamp": ts, "message": {"role": kind, "content": content}, **extra})


def _text(text: str) -> list[dict]:
    return [{"type": "text", "text": text}]


def _fase(stage: str, status: str = "PASS") -> dict:
    return {"id": "Fase 4", "stage_id": stage, "name": "Fase 4", "gate": "G", "status": status, "agent": "a"}


class Base(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.addCleanup(ai_transcripts.clear_cache)
        base = Path(holder.name)
        self.root = base / "ws"
        (self.root / ".papersmith").mkdir(parents=True)
        self.chats = base / "chats"
        self.chats.mkdir()
        self.locations = {"claude-code": self.chats, **NONE}

    def session(self, *lines: str, name: str = "abcdef12-session") -> Path:
        path = self.chats / f"{name}.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def sync(self) -> dict:
        return ai_archive.sync(self.root, self.locations)

    def records(self, name: str = "claude-code-abcdef12-session") -> list[dict]:
        path = self.root / ".papersmith" / "ai-history" / f"{name}.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class Store(Base):
    def test_every_prompt_and_every_reply_are_kept_in_full(self):
        self.session(_line("user", LONG, "2026-10-03T10:00:00Z"),
                     _line("assistant", _text("first " + LONG), "2026-10-03T10:01:00Z"),
                     _line("assistant", _text("second " + LONG), "2026-10-03T10:02:00Z"))
        self.assertEqual(self.sync()["added"], 3)
        found = self.records()
        self.assertEqual([r["role"] for r in found], ["user", "assistant", "assistant"])
        self.assertEqual(found[0]["text"], LONG)
        self.assertEqual(found[2]["text"], "second " + LONG)

    def test_a_second_sync_adds_nothing(self):
        self.session(_line("user", "hello there", "2026-10-03T10:00:00Z"))
        self.sync()
        ai_archive._forget_state(self.root)
        self.assertEqual(self.sync()["added"], 0)
        self.assertEqual(len(self.records()), 1)

    def test_only_new_turns_are_appended(self):
        lines = [_line("user", "one", "2026-10-03T10:00:00Z")]
        self.session(*lines)
        self.sync()
        self.session(*lines, _line("assistant", _text("two"), "2026-10-03T10:01:00Z"))
        self.assertEqual(self.sync()["added"], 1)
        self.assertEqual([r["text"] for r in self.records()], ["one", "two"])

    def test_the_archive_outlives_the_harness_session(self):
        self.session(_line("user", "/proposal-deliberation idea", "2026-10-03T10:00:00Z"),
                     _line("assistant", _text("Done."), "2026-10-03T10:01:00Z")).parent
        self.sync()
        (self.chats / "abcdef12-session.jsonl").unlink()
        ai_transcripts.clear_cache()
        view = ai_history.build_ai_history(self.root, [_fase("proposal")], sessions=self.locations)
        self.assertEqual([r["reply"] for r in view["phases"][0]["rounds"]], ["Done."])

    def test_a_session_is_not_counted_twice_when_live_and_archived(self):
        self.session(_line("user", "/proposal-deliberation idea", "2026-10-03T10:00:00Z"))
        self.sync()
        view = ai_history.build_ai_history(self.root, [_fase("proposal")], sessions=self.locations)
        self.assertEqual(view["phases"][0]["counts"]["commands"], 1)

    def test_a_session_file_is_one_per_machine_safe_name(self):
        self.assertEqual(ai_archive._file_name("claude-code", "a/../b"), "claude-code-a-b.jsonl")

    def test_a_workspace_tracks_the_archive_in_git(self):
        template = Path(server.__file__).resolve().parents[3] / "src/papersmith/templates"
        ignore = "\n".join(p.read_text(encoding="utf-8") for p in template.glob("gitignore*"))
        self.assertNotIn("ai-history", ignore)
        self.assertNotIn("\n.papersmith/\n", ignore)


class Secrets(Base):
    def test_secrets_are_redacted_before_saving(self):
        samples = ["sk-ant-api03-abcdefghijklmnopqrstuvwxyz012345", "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
                   "AKIAABCDEFGHIJKLMNOP", "KGAT_0123456789abcdef0123456789abcdef", "Authorization: Bearer abcdefghijklmnop1234567890",
                   'password = "hunter2hunter2"', "KAGGLE_KEY=0123456789abcdef0123456789abcdef",
                   "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"]
        for sample in samples:
            with self.subTest(sample=sample[:12]):
                self.assertIn("[REDACTED]", ai_archive.redact(f"before {sample} after"))
                self.assertNotIn(sample, ai_archive.redact(f"before {sample} after"))

    def test_ordinary_text_is_left_alone(self):
        text = "The password rule of section 3 and the key result, 0.683 balanced accuracy."
        self.assertEqual(ai_archive.redact(text), text)

    def test_the_file_never_holds_the_secret(self):
        self.session(_line("user", "use ghp_abcdefghijklmnopqrstuvwxyz0123456789 please", "2026-10-03T10:00:00Z"))
        self.sync()
        self.assertNotIn("ghp_", self.records()[0]["text"])


class LostTurns(Base):
    def test_turns_before_a_phase_command_are_kept_unassigned(self):
        self.session(_line("user", "what does this repo do", "2026-10-03T10:00:00Z"),
                     _line("assistant", _text("It writes papers."), "2026-10-03T10:01:00Z"),
                     _line("user", "/proposal-deliberation idea", "2026-10-03T10:02:00Z"))
        view = ai_history.build_ai_history(self.root, [_fase("proposal")], sessions=self.locations)
        self.assertEqual((view["unassigned"]["prompts"], view["unassigned"]["replies"]), (1, 1))
        self.assertEqual(view["phases"][0]["counts"]["commands"], 1)

    def test_a_skill_the_agent_loads_opens_its_phase(self):
        skill = [{"type": "tool_use", "name": "Skill", "input": {"skill": "proposal-deliberation"}}]
        self.session(_line("user", "let us work on the proposal", "2026-10-03T10:00:00Z"),
                     _line("assistant", skill, "2026-10-03T10:00:10Z"),
                     _line("assistant", _text("Working."), "2026-10-03T10:01:00Z"),
                     _line("user", "add H2", "2026-10-03T10:02:00Z"))
        view = ai_history.build_ai_history(self.root, [_fase("proposal", "ACTIVE")], sessions=self.locations)
        self.assertEqual(view["unassigned"]["prompts"], 1)
        self.assertEqual(view["phases"][0]["metrics"]["prompts"], 1)
        self.assertEqual(view["phases"][0]["metrics"]["replies"], 1)

    def test_a_prompt_queued_while_the_agent_works_is_kept(self):
        queued = json.dumps({"type": "attachment", "timestamp": "2026-10-03T10:00:00Z",
                             "attachment": {"type": "queued_command", "prompt": "and also this"}})
        self.session(queued)
        self.sync()
        self.assertEqual([r["text"] for r in self.records()], ["and also this"])

    def test_a_queued_prompt_that_reappears_is_kept_once(self):
        queued = json.dumps({"type": "attachment", "timestamp": "2026-10-03T10:00:00Z",
                             "attachment": {"type": "queued_command", "prompt": "same"}})
        self.session(queued, _line("user", "same", "2026-10-03T10:00:01Z"))
        self.sync()
        self.assertEqual(len(self.records()), 1)

    def test_a_prompt_behind_an_injected_block_is_kept(self):
        self.session(_line("user", "<system-reminder>note</system-reminder>\nthe real prompt", "2026-10-03T10:00:00Z"))
        self.sync()
        self.assertEqual(self.records()[0]["text"], "the real prompt")

    def test_a_non_phase_command_keeps_its_arguments(self):
        self.session(_line("user", "<command-name>/review</command-name><command-args>the intro</command-args>",
                           "2026-10-03T10:00:00Z"))
        self.sync()
        self.assertEqual(self.records()[0]["text"], "/review the intro")

    def test_harness_turns_are_not_operator_turns(self):
        self.session(_line("user", "summary of the session", "2026-10-03T10:00:00Z", isCompactSummary=True),
                     _line("user", "[Request interrupted by user]", "2026-10-03T10:00:01Z"),
                     _line("user", "<bash-input>ls</bash-input>", "2026-10-03T10:00:02Z"),
                     _line("assistant", _text("API Error: 500"), "2026-10-03T10:00:03Z", isApiErrorMessage=True),
                     _line("user", "a real one", "2026-10-03T10:00:04Z"))
        self.sync()
        self.assertEqual([r["text"] for r in self.records()], ["a real one"])

    def test_subagent_answers_are_kept_apart(self):
        self.session(_line("user", "main", "2026-10-03T10:00:00Z"))
        folder = self.chats / "abcdef12-session" / "subagents"
        folder.mkdir(parents=True)
        (folder / "agent-1.jsonl").write_text(
            _line("assistant", _text("from the worker"), "2026-10-03T10:00:30Z", isSidechain=True) + "\n")
        self.sync()
        self.assertEqual([r["text"] for r in self.records("claude-code-abcdef12-session-sub-agent-1")],
                         ["from the worker"])

    def test_tutor_threads_are_kept(self):
        folder = self.root / ".papersmith" / "math-tutor"
        folder.mkdir()
        (folder / "thread.json").write_text(json.dumps({"turns": [
            {"role": "reader", "at": "2026-10-03T10:00:00Z", "mode": "ask", "message": "why this bound", "images": []},
            {"role": "tutor", "at": "2026-10-03T10:01:00Z", "mode": "ask", "message": "Because of Eq. 2", "images": []},
        ]}))
        self.sync()
        self.assertEqual([(r["role"], r["text"]) for r in self.records("tutor-math-tutor")],
                         [("user", "why this bound"), ("assistant", "Because of Eq. 2")])

    def test_sessions_of_a_subdirectory_are_found(self):
        base = self.chats.parent / "config" / "projects"
        slug = "-" + str(self.root).strip("/").replace("/", "-").replace(".", "-").replace("_", "-")
        inner = base / (slug + "-implementations-x")
        inner.mkdir(parents=True)
        (inner / "s.jsonl").write_text(json.dumps({"type": "user", "cwd": str(self.root / "implementations/x"),
                                                   "timestamp": "2026-10-03T10:00:00Z",
                                                   "message": {"role": "user", "content": "inside"}}) + "\n")
        found = ai_transcripts.related_dirs(base, {str(self.root)})
        self.assertEqual(found, [inner])


class Graph(Base):
    def build(self, status: str = "PASS") -> dict:
        return ai_history.build_ai_history(self.root, [_fase("proposal", status)],
                                           sessions=self.locations)["phases"][0]

    def test_a_tool_error_the_agent_recovers_from_is_not_rework(self):
        self.session(_line("user", "/proposal-deliberation idea", "2026-10-03T10:00:00Z"),
                     _line("user", [{"type": "tool_result", "is_error": True, "content": "x"}], "2026-10-03T10:00:30Z"),
                     _line("assistant", _text("Done anyway."), "2026-10-03T10:01:00Z"))
        phase = self.build()
        self.assertEqual(phase["rounds"][0]["outcome"], "success")
        self.assertEqual(phase["metrics"]["tool_errors"], 1)

    def test_an_approval_alone_does_not_paint_friction(self):
        self.session(_line("user", "/proposal-deliberation idea", "2026-10-03T10:00:00Z"),
                     _line("assistant", _text("Done."), "2026-10-03T10:01:00Z"),
                     _line("user", "aprobado", "2026-10-03T10:02:00Z"))
        phase = self.build()
        self.assertEqual(phase["color"], "green")
        self.assertEqual(phase["metrics"]["approvals"], 1)

    def test_metrics_separate_iterations_corrections_and_success(self):
        self.session(_line("user", "/proposal-deliberation idea", "2026-10-03T10:00:00Z"),
                     _line("assistant", _text("One."), "2026-10-03T10:01:00Z"),
                     _line("user", "corrige la ecuación", "2026-10-03T10:02:00Z"),
                     _line("assistant", _text("Two."), "2026-10-03T10:03:00Z"),
                     _line("user", "añade H2", "2026-10-03T10:04:00Z"),
                     _line("assistant", _text("Three."), "2026-10-03T10:05:00Z"))
        metrics = self.build()["metrics"]
        self.assertEqual({k: metrics[k] for k in ("rounds", "prompts", "replies", "corrections", "success", "rework")},
                         {"rounds": 3, "prompts": 3, "replies": 3, "corrections": 1, "success": 1, "rework": 1})
        self.assertEqual(metrics["first_pass_rate"], 0.67)

    def test_two_different_remote_runs_are_not_rework(self):
        events = [{"ts": "2026-10-03T10:00:00Z", "kind": "submitted", "summary": "run A", "source": "remote-execution"},
                  {"ts": "2026-10-03T11:00:00Z", "kind": "submitted", "summary": "run B", "source": "remote-execution"}]
        self.assertEqual(ai_history.decision_rounds("PASS", events)[0]["outcome"], "iteration")

    def test_the_same_remote_run_again_is_rework(self):
        events = [{"ts": "2026-10-03T10:00:00Z", "kind": "submitted", "summary": "run A", "source": "remote-execution"},
                  {"ts": "2026-10-03T11:00:00Z", "kind": "submitted", "summary": "run A", "source": "remote-execution"}]
        self.assertEqual(ai_history.decision_rounds("PASS", events)[0]["outcome"], "rework")


class Interfaces(Base):
    def client(self) -> TestClient:
        return TestClient(server.create_app(self.root, history_store=None))

    def test_the_session_route_answers_the_full_text(self):
        self.session(_line("user", LONG, "2026-10-03T10:00:00Z"))
        self.sync()
        body = self.client().get("/api/ai-history/session", params={"ref": "claude-code:-session"}).json()
        self.assertEqual(body["turns"][0]["text"], LONG)

    def test_the_session_route_refuses_an_unknown_ref(self):
        response = self.client().get("/api/ai-history/session", params={"ref": "claude-code:../../x"})
        self.assertEqual(response.status_code, 404)

    def test_the_cli_syncs_and_reports(self):
        code = ai_archive.main(["sync", "--root", str(self.root)])
        self.assertEqual(code, 0)

    def test_sync_never_raises_on_a_broken_store(self):
        (self.chats / "bad.jsonl").write_bytes(b"\xff\xfe not json\n")
        self.assertEqual(self.sync()["added"], 0)


if __name__ == "__main__":
    unittest.main()
