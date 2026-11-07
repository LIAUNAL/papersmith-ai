"""The persistent AI history archive and what the graph reads from it."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

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

    def test_turns_added_later_are_read_in_time_order(self):
        early = _line("user", "first", "2026-10-03T10:00:00Z")
        late = _line("user", "third", "2026-10-03T10:02:00Z")
        self.session(early, late)
        self.sync()
        self.session(early, _line("assistant", _text("second"), "2026-10-03T10:01:00Z"), late)
        self.sync()
        turns = ai_archive.session(self.root, "claude-code:-session")
        self.assertEqual([t["text"] for t in turns], ["first", "second", "third"])

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

    def test_every_shape_of_credential_is_redacted(self):
        hexkey = "0123456789abcdef0123456789abcdef"
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        samples = [
            f'{{"username":"amarino","key":"{hexkey}"}}', "export KAGGLE_API_TOKEN=Zx9Qw7Lm2Vb4Nc6Tr8Yp",
            "GITHUB_TOKEN=ghx9Qw7Lm2Vb4Nc6Tr8Yp", "HF_TOKEN=Zx9Qw7Lm2Vb4Nc6Tr8Yp",
            "AWS_SESSION_TOKEN=Zx9Qw7Lm2Vb4Nc6Tr8Yp", "DB_PASSWORD=hunter2", "CLIENT_SECRET=Zx9Qw7Lm2Vb4Nc6Tr8Yp",
            '"password": "hunter2"', "contraseña: hunter2", jwt, "https://admin:s3cr3tpass@example.org/x",
            "postgres://user:s3cr3tpass@db:5432/app", "mongodb+srv://user:s3cr3tpass@cluster/app",
            "machine example.org login me password hunter2", "tskey-auth-kAbCdEf1CNTRL-abcdefghijkl",
            "ya29.a0AfH6SMBabcdefghijklmnop", "GOCSPX-abcdefghijklmnopqrstuvwx", "hf_abcdefghijklmnopqrstuvwxyz012345",
            "glpat-abcdefghij1234567890", "npm_abcdefghijklmnopqrstuvwxyz0123456789",
            "sk_live_abcdefghijklmnop012345", "https://hooks.slack.com/services/T000/B000/XXXXXXXXXXXXXXXX",
            "Authorization: Basic dXNlcjpwYXNzd29yZA==", "curl -u admin:s3cr3tpass https://x.org",
            "sshpass -p hunter2 ssh host", "tool --password hunter2", "tool --token Zx9Qw7Lm2Vb4Nc6Tr8Yp",
            "-----BEGIN OPENSSH PRIVATE KEY-----\nabcdef\nghijkl",
        ]
        secrets = [hexkey, "Zx9Qw7Lm2Vb4Nc6Tr8Yp", "ghx9Qw7Lm2Vb4Nc6Tr8Yp", "hunter2", "s3cr3tpass", jwt[:30],
                   "tskey-auth", "ya29.a0", "GOCSPX-a", "hf_abc", "glpat-a", "npm_abc", "sk_live_a", "XXXXXXXXXXXX",
                   "dXNlcjpwYXNzd29yZA", "abcdef\nghijkl"]
        for sample in samples:
            with self.subTest(sample=sample[:18]):
                clean = ai_archive.redact(f"before {sample} after")
                self.assertIn("[REDACTED]", clean)
                for secret in secrets:
                    self.assertNotIn(secret, clean)

    def test_a_quoted_value_with_spaces_is_redacted(self):
        for sample in ('DB_PASSWORD="my secret, phrase"', "password: 'open sesame now'", '"password": "a b;c"'):
            with self.subTest(sample=sample):
                clean = ai_archive.redact(sample)
                self.assertIn("[REDACTED]", clean)
                for word in ("secret", "sesame", "a b"):
                    self.assertNotIn(word, clean)

    def test_a_long_word_does_not_stall_the_filter(self):
        started = time.monotonic()
        ai_archive.redact("a" * 200000)
        self.assertLess(time.monotonic() - started, 2)

    def test_an_id_says_nothing_about_the_text(self):
        self.session(_line("user", "password: weak1234", "2026-10-03T10:00:00Z"))
        self.sync()
        guess = "claude-code|abcdef12-session|2026-10-03T10:00:00Z|user|password: weak1234"
        self.assertNotEqual(self.records()[0]["id"], hashlib.sha256(guess.encode()).hexdigest()[:16])
        same = ai_archive._records("claude-code", "s", [("t", "user", "a"), ("t", "user", "b")])
        other = ai_archive._records("claude-code", "s", [("t", "user", "x"), ("t", "user", "y")])
        self.assertEqual([r["id"] for r in same], [r["id"] for r in other])

    def test_ordinary_text_is_left_alone(self):
        for text in ("The password rule of section 3 and the key result, 0.683 balanced accuracy.",
                     "token: embedding", "rng_key = jax.random.split(key)", "PRIMARY_KEY=subject_id",
                     "sort_key=lambda r: r[0]", "sk-learn-compatible-pipeline-estimator",
                     "The bearer electrophysiological signal", "x_key: 0.25000",
                     "The token count is 4096 and the secret sauce is depth.", "https://arxiv.org/abs/2008.08605"):
            with self.subTest(text=text):
                self.assertEqual(ai_archive.redact(text), text)

    def test_a_new_rule_scrubs_what_is_already_archived(self):
        self.session(_line("user", "use NEWKIND-abcdef123456 now", "2026-10-03T10:00:00Z"))
        self.sync()
        rule = ai_archive.re.compile(r"NEWKIND-\w+")
        with mock.patch.object(ai_archive, "_SECRETS", (*ai_archive._SECRETS, rule)):
            ai_archive._forget_state(self.root)
            self.assertEqual(self.sync()["added"], 0)
        found = self.records()
        self.assertEqual(len(found), 1)
        self.assertNotIn("NEWKIND", found[0]["text"])

    def test_the_file_never_holds_the_secret(self):
        self.session(_line("user", "use ghp_abcdefghijklmnopqrstuvwxyz0123456789 please", "2026-10-03T10:00:00Z"))
        self.sync()
        self.assertNotIn("ghp_", self.records()[0]["text"])


class Resilience(Base):
    def test_a_broken_character_never_stops_the_other_sessions(self):
        self.session(_line("user", "first", "2026-10-03T10:00:00Z"), name="a")
        self.session(json.dumps({"type": "user", "timestamp": "2026-10-03T10:00:00Z",
                                 "message": {"role": "user", "content": "bad \ud83d end"}}), name="b")
        self.session(_line("user", "third", "2026-10-03T10:00:00Z"), name="c")
        report = self.sync()
        self.assertEqual((report["added"], report["problems"]), (3, {}))

    def test_a_line_that_cannot_be_decoded_keeps_the_others(self):
        self.session(_line("user", "kept", "2026-10-03T10:00:00Z"))
        self.sync()
        path = self.root / ".papersmith/ai-history/claude-code-abcdef12-session.jsonl"
        path.write_bytes(path.read_bytes() + b'\xff\xfe{"id": "x"\n')
        self.assertEqual([r["text"] for r in self.records_read(path)], ["kept"])

    def records_read(self, path: Path) -> list[dict]:
        return ai_archive._read(path)

    def test_a_record_written_twice_is_read_once(self):
        self.session(_line("user", "once", "2026-10-03T10:00:00Z"))
        self.sync()
        path = self.root / ".papersmith/ai-history/claude-code-abcdef12-session.jsonl"
        path.write_text(path.read_text() * 2)
        self.assertEqual(len(ai_archive._read(path)), 1)

    def test_a_symlink_in_the_archive_is_not_followed(self):
        outside = self.root.parent / "outside.jsonl"
        outside.write_text("")
        folder = self.root / ".papersmith" / "ai-history"
        folder.mkdir()
        (folder / "claude-code-abcdef12-session.jsonl").symlink_to(outside)
        self.session(_line("user", "x", "2026-10-03T10:00:00Z"))
        self.sync()
        self.assertEqual(outside.read_text(), "")

    def test_the_status_route_keeps_the_archive_current(self):
        with mock.patch.object(server.ai_archive, "sync_in_background") as sync:
            TestClient(server.create_app(self.root, history_store=None)).get("/api/status")
        sync.assert_called_once()

    def test_only_a_real_workspace_syncs_by_itself(self):
        with mock.patch.object(ai_archive, "sync") as run:
            ai_archive.sync_throttled(self.root)
            run.assert_not_called()
            (self.root / ".papersmith" / "version").write_text("0.61.3")
            ai_archive.sync_throttled(self.root)
            run.assert_called_once()

    def test_a_live_session_is_not_parsed_from_the_archive(self):
        self.session(_line("user", "/proposal-deliberation idea", "2026-10-03T10:00:00Z"))
        self.sync()
        found = list(ai_archive.archived_sessions(self.root, {"claude-code:-session"}))
        self.assertEqual(found, [])


class Privacy(Base):
    def test_personal_data_is_masked(self):
        cases = {"write to amalvarezme@unal.edu.co now": "[EMAIL]", "cc: Someone.Else+x@gmail.com": "[EMAIL]",
                 "ssh andresalvarez@100.66.178.111": "[USER]@[IP]", "server 192.168.1.20 is down": "[IP]",
                 "host 10.0.0.7": "[IP]", "/Users/andresalvarez/Documents/QMLEEG/x.py": "/Users/[USER]/",
                 "/home/andresmarino/.ssh/config": "/home/[USER]/", r"C:\Users\Ana\Desktop": r"C:\Users\[USER]",
                 "call +57 300 123 4567 today": "[PHONE]",
                 "key SHA256:Q6wckxDuKrZANF4wD7qFCFpb4/o0nlEY17B7lnF2zNY": "[FINGERPRINT]"}
        for text, mask in cases.items():
            with self.subTest(text=text):
                clean = ai_archive.redact(text)
                self.assertIn(mask, clean)
                for private in ("amalvarezme", "andresalvarez", "andresmarino", "Someone", "192.168", "100.66",
                                "300 123", "Q6wckx", "Ana"):
                    self.assertNotIn(private, clean)

    def test_technical_text_survives(self):
        for text in ("install numpy@1.26.4 and @types/node", "version 1.2.3.4 of the tool", "see Eq. 2 and 0.683",
                     "git@github.com:LIAUNAL/papersmith-ai.git", "the /home page and /Users guide",
                     "sample rate of 256 Hz over 19 channels", "doi 10.3390/technologies14070392",
                     "seed 1234567890 on 2026-11-07", "arXiv:2008.08605v2"):
            with self.subTest(text=text):
                self.assertEqual(ai_archive.redact(text), text)

    def test_a_scrub_masks_what_is_already_archived(self):
        folder = self.root / ".papersmith" / "ai-history"
        folder.mkdir()
        (folder / "pi-x.jsonl").write_text(json.dumps({"id": "a", "ts": None, "role": "user", "text": "me@site.org"}) + "\n")
        self.assertEqual(ai_archive.scrub(self.root), 1)
        self.assertNotIn("me@site.org", (folder / "pi-x.jsonl").read_text())


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


class AutoCommit(Base):
    def setUp(self) -> None:
        super().setUp()
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.email", "t@example.org")
        _git(self.root, "config", "user.name", "T")
        (self.root / ".gitignore").write_text(".papersmith/cache/\n")
        (self.root / "work.txt").write_text("one\n")
        _git(self.root, "add", "work.txt", ".gitignore")
        _git(self.root, "commit", "-q", "-m", "init")
        self.session(_line("user", "hello", "2026-10-03T10:00:00Z"))
        self.sync()

    def count(self) -> int:
        return int(_git(self.root, "rev-list", "--count", "HEAD"))

    def test_new_conversations_are_committed(self):
        report = ai_archive.commit(self.root)
        self.assertEqual(report["status"], "committed")
        self.assertEqual(self.count(), 2)
        self.assertIn("chore(history)", _git(self.root, "log", "-1", "--format=%s"))
        self.assertEqual(_git(self.root, "status", "--short"), "")

    def test_nothing_new_makes_no_commit(self):
        ai_archive.commit(self.root)
        self.assertEqual(ai_archive.commit(self.root)["status"], "unchanged")
        self.assertEqual(self.count(), 2)

    def test_the_operators_staged_work_stays_out(self):
        (self.root / "work.txt").write_text("two\n")
        _git(self.root, "add", "work.txt")
        (self.root / "other.txt").write_text("loose\n")
        ai_archive.commit(self.root)
        self.assertEqual(_git(self.root, "show", "--name-only", "--format=", "HEAD").split(),
                         ["./.papersmith/ai-history/claude-code-abcdef12-session.jsonl"[2:]])
        self.assertIn("M  work.txt", _git(self.root, "status", "--short"))

    def test_a_merge_in_progress_is_left_alone(self):
        (Path(_git(self.root, "rev-parse", "--absolute-git-dir").strip()) / "MERGE_HEAD").write_text("x\n")
        self.assertEqual(ai_archive.commit(self.root)["status"], "busy")
        self.assertEqual(self.count(), 1)

    def test_a_detached_head_is_left_alone(self):
        _git(self.root, "checkout", "-q", "--detach")
        self.assertEqual(ai_archive.commit(self.root)["status"], "busy")

    def test_a_folder_outside_git_is_fine(self):
        other = self.root.parent / "plain"
        (other / ".papersmith" / "ai-history").mkdir(parents=True)
        self.assertEqual(ai_archive.commit(other)["status"], "no-repository")

    def test_the_operator_can_turn_it_off(self):
        with mock.patch.dict("os.environ", {"PAPERSMITH_AI_HISTORY_COMMIT": "0"}):
            self.assertEqual(ai_archive.commit(self.root)["status"], "disabled")
        self.assertEqual(self.count(), 1)

    def test_a_failing_hook_is_reported_not_raised(self):
        hook = Path(_git(self.root, "rev-parse", "--absolute-git-dir").strip()) / "hooks" / "pre-commit"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        self.assertEqual(ai_archive.commit(self.root)["status"], "failed")

    def test_a_workspace_commits_after_its_sync(self):
        (self.root / ".papersmith" / "version").write_text("0.61.3")
        ai_archive._last_sync.clear()
        ai_archive._last_commit.clear()
        self.session(_line("user", "hello", "2026-10-03T10:00:00Z"), _line("user", "more", "2026-10-03T10:01:00Z"))
        real = ai_archive.sync
        with mock.patch.object(ai_archive, "sync", side_effect=lambda root: real(root, self.locations)):
            ai_archive.sync_throttled(self.root)
        self.assertEqual(self.count(), 2)
        self.assertEqual(ai_archive.last_report(self.root)["commit"]["status"], "committed")


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


class Models(Base):
    def reply(self, text: str, ts: str, model: str = "claude-opus-5-5", effort: str = "medium") -> str:
        line = json.loads(_line("assistant", _text(text), ts))
        line["message"]["model"] = model
        line["effort"] = effort
        return json.dumps(line)

    def view(self) -> dict:
        return ai_history.build_ai_history(self.root, [_fase("proposal")], sessions=self.locations)["phases"][0]

    def test_a_claude_reply_records_its_model_and_effort(self):
        self.session(_line("user", "hello", "2026-10-03T10:00:00Z"), self.reply("Hi.", "2026-10-03T10:01:00Z"))
        self.sync()
        record = self.records()[1]
        self.assertEqual((record["model"], record["effort"]), ("claude-opus-5-5", "medium"))
        self.assertNotIn("model", self.records()[0])

    def test_antigravity_matches_the_workspace_its_worktrees_and_its_parent(self):
        inside = ai_transcripts._in_workspace
        for uri, expected in (("file:///a/QML", True), ("file:///a/QML/sub", True), ("file:///a/QML-worktrees/x", True),
                              ("file:///a", True), ("file:///a/QML2", False), ("file:///b/QML", False)):
            with self.subTest(uri=uri):
                self.assertEqual(inside(json.dumps([uri]), {"/a/QML"}), expected)

    def test_a_dated_model_id_is_not_read_as_a_version(self):
        self.assertEqual(ai_transcripts.model_label("claude-code", {"model": "claude-sonnet-4-20250514"}),
                         "Claude Code · claude-sonnet-4-20250514")

    def test_the_label_reads_like_the_operator_says_it(self):
        label = ai_transcripts.model_label
        self.assertEqual(label("claude-code", {"model": "claude-opus-5-5", "effort": "medium"}),
                         "Claude Code · opus 5.5 - medium")
        self.assertEqual(label("pi", {"model": "deepseek-v4", "effort": "high"}), "Pi · deepseek-v4 - high")
        self.assertEqual(label("opencode", {"model": "glm-5.2"}), "OpenCode · glm-5.2")
        self.assertEqual(label("antigravity", {}), "Antigravity")

    def test_a_phase_shows_each_reply_with_its_model(self):
        self.session(_line("user", "/proposal-deliberation idea", "2026-10-03T10:00:00Z"),
                     self.reply("One.", "2026-10-03T10:01:00Z"),
                     _line("user", "more", "2026-10-03T10:02:00Z"),
                     self.reply("Two.", "2026-10-03T10:03:00Z", effort="high"))
        phase = self.view()
        self.assertEqual([r["model_label"] for r in phase["rounds"]],
                         ["Claude Code · opus 5.5 - medium", "Claude Code · opus 5.5 - high"])
        self.assertEqual(phase["metrics"]["models"], [{"label": "Claude Code · opus 5.5 - high", "replies": 1},
                                                      {"label": "Claude Code · opus 5.5 - medium", "replies": 1}])

    def test_the_model_survives_in_the_archive(self):
        path = self.session(_line("user", "/proposal-deliberation idea", "2026-10-03T10:00:00Z"),
                            self.reply("One.", "2026-10-03T10:01:00Z"))
        self.sync()
        path.unlink()
        ai_transcripts.clear_cache()
        self.assertEqual(self.view()["rounds"][0]["model_label"], "Claude Code · opus 5.5 - medium")

    def test_an_older_record_gains_its_model(self):
        plain = _line("assistant", _text("Hi."), "2026-10-03T10:01:00Z")
        self.session(plain)
        self.sync()
        self.assertNotIn("model", self.records()[0])
        self.session(self.reply("Hi.", "2026-10-03T10:01:00Z"))
        ai_archive._forget_state(self.root)
        self.assertEqual(self.sync()["added"], 0)
        self.assertEqual(self.records()[0]["model"], "claude-opus-5-5")

    def test_a_synthetic_message_names_no_model(self):
        self.session(self.reply("Hi.", "2026-10-03T10:01:00Z", model="<synthetic>"))
        self.sync()
        self.assertNotIn("model", self.records()[0])

    def test_pi_carries_the_thinking_level_forward(self):
        lines = [json.dumps({"type": "thinking_level_change", "thinkingLevel": "high"}),
                 json.dumps({"type": "message", "timestamp": "2026-10-03T10:00:00Z",
                             "message": {"role": "assistant", "model": "deepseek-v4", "provider": "nan",
                                         "content": _text("Hi.")}})]
        (self.chats / "pi-session.jsonl").write_text("\n".join(lines) + "\n")
        ai_archive.sync(self.root, {"pi": self.chats, "claude-code": None, "opencode": None, "antigravity": None})
        found = self.records("pi-pi-session")[0]
        self.assertEqual((found["model"], found["effort"], found["provider"]), ("deepseek-v4", "high", "nan"))

    def test_opencode_reads_the_model_of_the_message(self):
        message = json.dumps({"role": "assistant", "modelID": "glm-5.2", "providerID": "go", "variant": "high"})
        part = json.dumps({"type": "text", "text": "Hi."})
        turn = list(ai_transcripts._opencode_turns([(message, part, 1791000000000)]))[0]
        self.assertEqual(turn[3], {"model": "glm-5.2", "provider": "go", "effort": "high"})

    def test_antigravity_infers_the_model_from_its_log(self):
        folder = self.chats / "ag"
        folder.mkdir()
        (folder / "cli-20261105_163024.log").write_text(
            'I1105 16:30:26.187223     326 model_config_manager.go:363] Propagating selected model override to '
            'backend: label: "Gemini 3.8 Flash (High)"\n'
            'I1105 18:00:00.000000     326 model_config_manager.go:363] Propagating selected model override to '
            'backend: label: "Gemini 4 Argon (Medium)"\n')
        timeline = ai_transcripts.antigravity_models(folder, offset_minutes=-300)
        pick = ai_transcripts.antigravity_model_at
        self.assertEqual(pick(timeline, "2026-11-05T21:40:00Z"),
                         {"model": "Gemini 3.8 Flash", "effort": "High", "inferred": True})
        self.assertEqual(pick(timeline, "2026-11-05T23:10:00Z")["model"], "Gemini 4 Argon")
        self.assertIsNone(pick(timeline, "2026-11-05T21:00:00Z"))


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
