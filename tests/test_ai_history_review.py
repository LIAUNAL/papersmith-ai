"""The AI History pane and the AI-usage record follow the workspace's paper
line: a review workspace (``smith init --kind review``) reads its chat sessions
against the ten review steps (``review_board.REVIEW_STAGES``), so a
``/systematic-review <verb>`` session lands on the step that verb runs, and the
experimental line keeps its phases byte for byte."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from papersmith.core.init import initialize
from skills._core.command_center import ai_history, ai_transcripts, phase_actions, review_board

_TEMPLATES: dict[str, Path] = {}


def _template(kind: str) -> Path:
    """One initialized workspace per kind, copied by each test."""
    if kind not in _TEMPLATES:
        base = Path(tempfile.mkdtemp(prefix=f"t6c-{kind}-"))
        ws = base / "ws"
        if kind == "review":
            initialize(ws, tools=("claude",), run_npm=False, run_env=False, kind="review")
        else:
            initialize(ws, tools=("claude",), run_npm=False, run_env=False)
        _TEMPLATES[kind] = ws
    return _TEMPLATES[kind]


def tearDownModule() -> None:  # noqa: N802 - unittest hook
    for ws in _TEMPLATES.values():
        shutil.rmtree(ws.parent, ignore_errors=True)


def _line(kind: str, content, ts: str) -> str:
    return json.dumps({"type": kind, "timestamp": ts, "message": {"role": kind, "content": content}})


def _reply(text: str, ts: str) -> str:
    return _line("assistant", [{"type": "text", "text": text}], ts)


#: The same operator session in both lines: the phase commands of each.
SESSION = [
    _line("user", "<command-name>/plausibility</command-name><command-args>an idea in two sentences</command-args>",
          "2026-10-01T10:00:00Z"),
    _reply("Plausibility report ready.", "2026-10-01T10:01:00Z"),
    _line("user", "/systematic-review scope Graph networks predict molecular properties. Which ones?",
          "2026-10-01T10:02:00Z"),
    _reply("Twelve existing reviews found.", "2026-10-01T10:03:00Z"),
    _line("user", "<command-name>/systematic-review</command-name><command-args>protocol draft it</command-args>",
          "2026-10-01T10:04:00Z"),
    _reply("Protocol drafted.", "2026-10-01T10:05:00Z"),
    _line("user", "/systematic-review search every open source", "2026-10-01T10:06:00Z"),
    _reply("Three searches logged.", "2026-10-01T10:07:00Z"),
    _line("user", "/systematic-review screen the ta queue", "2026-10-01T10:08:00Z"),
    _reply("Twenty records screened.", "2026-10-01T10:09:00Z"),
    _line("user", "corrige la decisión del registro R0003", "2026-10-01T10:10:00Z"),
    _reply("Corrected.", "2026-10-01T10:11:00Z"),
    _line("user", "/systematic-review extract R0001", "2026-10-01T10:12:00Z"),
    _reply("Extracted.", "2026-10-01T10:13:00Z"),
    _line("user", "/systematic-review synthesize the themes", "2026-10-01T10:14:00Z"),
    _reply("Themes proposed.", "2026-10-01T10:15:00Z"),
    _line("user", "/paper-ingestion paper.pdf", "2026-10-01T10:16:00Z"),
    _reply("Ingested.", "2026-10-01T10:17:00Z"),
    _line("user", "/paper-writing mark language: English", "2026-10-01T10:18:00Z"),
    _reply("Declaration recorded.", "2026-10-01T10:19:00Z"),
    _line("user", "/paper-writing write introduction", "2026-10-01T10:20:00Z"),
    _reply("Block written.", "2026-10-01T10:21:00Z"),
    _line("user", "/figure-review prisma-flow", "2026-10-01T10:22:00Z"),
    _reply("Figure checked.", "2026-10-01T10:23:00Z"),
    _line("user", "/systematic-review checklist", "2026-10-01T10:24:00Z"),
    _reply("Checklist: 20 of 27 items.", "2026-10-01T10:25:00Z"),
]


class _Workspace(unittest.TestCase):
    kind = "experimental"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.root = base / "ws"
        shutil.copytree(_template(self.kind), self.root, symlinks=True)
        self.chats = base / "chats"
        self.chats.mkdir()
        (self.chats / "s1.jsonl").write_text("\n".join(SESSION) + "\n", encoding="utf-8")
        self.sessions = {"claude-code": self.chats, "pi": None, "opencode": None, "antigravity": None}
        ai_transcripts.clear_cache()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def history(self, fases: list[dict]) -> dict:
        return ai_history.build_ai_history(self.root, fases, sessions=self.sessions)

    def usage(self) -> dict:
        return ai_history.build_ai_usage(self.root, sessions=self.sessions)


def _fases(stages, gate_of=lambda s: f"G-{s.upper()}") -> list[dict]:
    return [{"id": f"Fase {n}", "stage_id": stage, "name": f"Phase {n}", "gate": gate_of(stage),
             "status": "PENDING", "agent": "agent"} for n, stage in enumerate(stages, start=1)]


FIXED_MTIME = 1_790_000_000


def _canonical(view: dict) -> str:
    """The view without the artifacts' sizes: the kit's provenance, written
    into the workspace's files, sets them."""
    view = json.loads(json.dumps(view))
    for phase in view.get("phases", []):
        for artifact in phase.get("artifacts", []):
            artifact.pop("size", None)
    return json.dumps(view, sort_keys=True, ensure_ascii=False)


class ExperimentalLineUnchangedTests(_Workspace):
    kind = "experimental"

    def setUp(self) -> None:
        super().setUp()
        (self.root / "proposals").mkdir(exist_ok=True)
        (self.root / "proposals" / "research-concept-r01.md").write_text("# r01\n", encoding="utf-8")
        # One modification time for every file: the artifacts list newest first.
        for path in self.root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                os.utime(path, (FIXED_MTIME, FIXED_MTIME))

    def test_ai_history_output_is_pinned(self) -> None:
        view = self.history(_fases(phase_actions.STAGES))
        by_stage = {p["stage_id"]: p for p in view["phases"]}
        self.assertEqual([p["stage_id"] for p in view["phases"]], list(phase_actions.STAGES))
        self.assertEqual(by_stage["plausibility"]["metrics"]["rounds"], 2)
        self.assertEqual(by_stage["declarations"]["events"][0]["summary"], "/paper-writing mark language: English")
        self.assertEqual(by_stage["writing"]["events"][0]["summary"], "/paper-writing write introduction")
        # The /systematic-review turns are no experimental phase's: they follow the
        # plausibility round until the next experimental command.
        self.assertEqual(by_stage["plausibility"]["counts"]["user_messages"], 1)
        digest = hashlib.sha256(_canonical(view).encode("utf-8")).hexdigest()
        self.assertEqual(digest, EXPERIMENTAL_HISTORY_SHA256)

    def test_ai_usage_output_is_pinned(self) -> None:
        usage = self.usage()
        self.assertEqual([p["stage_id"] for p in usage["phases"]],
                         ["plausibility", "ingestion", "proposal", "declarations", "writing", "figures"])
        self.assertEqual([p["label"] for p in usage["phases"]],
                         ["Plausibility", "Ingestion", "Proposal deliberation", "Declarations", "Writing",
                          "Figures"])
        digest = hashlib.sha256(json.dumps(usage, sort_keys=True).encode("utf-8")).hexdigest()
        self.assertEqual(digest, EXPERIMENTAL_USAGE_SHA256)


EXPERIMENTAL_HISTORY_SHA256 = "1cf6cb21a62e5fdac743cb251b007546371bc5bf2fba679f0c2e9ce3583685d1"
#: Both computed on the code before the review line read its own steps.
EXPERIMENTAL_USAGE_SHA256 = "96a807fb479e927a2f51186cb702cb1ad8fa7c75468caec26eb31b031cf9ba9e"


class ReviewLineTests(_Workspace):
    kind = "review"

    def test_systematic_review_verbs_map_to_their_review_steps(self) -> None:
        view = self.history(_fases(review_board.REVIEW_STAGES))
        by_stage = {p["stage_id"]: p for p in view["phases"]}
        commands = {stage: [e["summary"] for e in phase["events"] if e["kind"] == "command"]
                    for stage, phase in by_stage.items()}
        self.assertEqual(commands["scoping"],
                         ["/systematic-review scope Graph networks predict molecular properties. Which ones?"])
        self.assertEqual(commands["protocol"], ["/systematic-review protocol draft it"])
        self.assertEqual(commands["identification"], ["/systematic-review search every open source"])
        self.assertEqual(commands["screening"], ["/systematic-review screen the ta queue",
                                                 "/paper-ingestion paper.pdf"])
        self.assertEqual(commands["appraisal_extraction"], ["/systematic-review extract R0001"])
        self.assertEqual(commands["synthesis"], ["/systematic-review synthesize the themes"])
        self.assertEqual(commands["writing"], ["/paper-writing mark language: English",
                                               "/paper-writing write introduction"])
        self.assertEqual(commands["paper"], ["/figure-review prisma-flow"])
        self.assertEqual(commands["reporting_audit"], ["/systematic-review checklist"])
        self.assertEqual(commands["harness"], [])
        # The operator's follow-up stays on the step whose command opened its round.
        self.assertEqual(by_stage["screening"]["counts"]["user_messages"], 1)
        self.assertEqual(by_stage["screening"]["color"], "orange")

    def test_phases_carry_the_review_step_labels_and_evidence(self) -> None:
        (self.root / "review").mkdir(exist_ok=True)
        (self.root / "review" / "protocol.json").write_text("{}", encoding="utf-8")
        view = self.history(_fases(review_board.REVIEW_STAGES))
        self.assertEqual([p["label"] for p in view["phases"]],
                         [review_board.REVIEW_LABELS[s] for s in review_board.REVIEW_STAGES])
        protocol = next(p for p in view["phases"] if p["stage_id"] == "protocol")
        self.assertEqual([a["path"] for a in protocol["artifacts"]], ["review/protocol.json"])
        self.assertEqual(protocol["artifacts"][0]["label"], "Review protocol")

    def test_a_plausibility_session_is_no_review_step(self) -> None:
        view = self.history(_fases(review_board.REVIEW_STAGES))
        self.assertEqual(view["unassigned"]["prompts"], 0)
        reported = [e["summary"] for p in view["phases"] for e in p["events"]]
        self.assertNotIn("/plausibility an idea in two sentences", reported)

    def test_ai_usage_iterates_the_review_steps(self) -> None:
        usage = self.usage()
        self.assertEqual([p["stage_id"] for p in usage["phases"]],
                         ["scoping", "protocol", "identification", "screening", "appraisal_extraction",
                          "synthesis", "writing", "paper", "reporting_audit"])
        self.assertEqual([p["label"] for p in usage["phases"]],
                         [review_board.REVIEW_LABELS[p["stage_id"]] for p in usage["phases"]])
        screening = next(p for p in usage["phases"] if p["stage_id"] == "screening")
        self.assertEqual(screening["agent"], review_board.REVIEW_ACTIONS["screening"]["agent"])
        self.assertEqual(screening["harnesses"], ["claude-code"])
        self.assertEqual(screening["counts"]["commands"], 2)
        self.assertEqual(screening["counts"]["user_messages"], 1)

    def test_the_line_is_read_from_the_workspace_on_every_call(self) -> None:
        self.assertEqual(self.usage()["phases"][0]["stage_id"], "scoping")
        config = self.root / ".papersmith" / "config.json"
        data = json.loads(config.read_text(encoding="utf-8"))
        data["paper_kind"] = "experimental"
        config.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual([p["stage_id"] for p in self.usage()["phases"]][:2], ["plausibility", "ingestion"])
        data["paper_kind"] = "review"
        config.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.usage()["phases"][0]["stage_id"], "scoping")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
