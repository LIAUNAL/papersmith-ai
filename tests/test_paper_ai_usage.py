"""The AI-use declaration is built from the pipeline record, never from memory.

`ai_history.build_ai_usage` turns the pipeline record into per-phase evidence
(agent roles, harness tools, sessions, approvals, revisions); `paper_ai_usage`
joins it with the blocks the agents drafted and the selected venue's
placement; `packet` attaches the result to the declaration block only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import ai_history, phase_actions

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills" / "paper-writing" / "scripts"
SECTIONS = REPO / "sections"
sys.path.insert(0, str(SCRIPTS))
import paper_ai_usage  # noqa: E402
import paper_cli  # noqa: E402
import paper_venue  # noqa: E402


def _line(kind: str, content, ts: str) -> str:
    return json.dumps({"type": kind, "timestamp": ts, "message": {"role": kind, "content": content}})


def _block(block_id: str, body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return (f"%% paper-writing block {block_id} begin sha256={digest}\n{body}"
            f"%% paper-writing block {block_id} end\n")


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.root = base / "ws"
        self.paper = self.root / "paper"
        self.paper.mkdir(parents=True)
        self.chats = base / "chats"
        self.chats.mkdir()
        self.home = base / "home"
        self.home.mkdir()
        # No harness store outside the scratch home is ever read.
        self._env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self._env.start()
        for name in ("CLAUDE_CONFIG_DIR", "PI_CODING_AGENT_DIR", "XDG_DATA_HOME"):
            os.environ.pop(name, None)

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def sessions(self) -> dict:
        return {"claude-code": self.chats, "pi": None, "opencode": None, "antigravity": None}

    def chat(self, *lines: str) -> None:
        (self.chats / "s1.jsonl").write_text("\n".join(lines), encoding="utf-8")

    def manuscript(self) -> None:
        (self.paper / "main.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            + _block("conclusions.concl-block-1", "This work introduced the method.\n")
            + _block("back-matter.bm-funding", "")
            + "\\end{document}\n", encoding="utf-8")
        ledger = self.paper / ".paper-writing" / "attempts"
        ledger.mkdir(parents=True)
        (ledger / "conclusions.concl-block-1.json").write_text(
            json.dumps({"key": "k", "attempts": 2, "fired": []}), encoding="utf-8")

    def venue(self, publisher) -> None:
        target = self.paper / "venues" / "eswa"
        target.mkdir(parents=True)
        (target / "venue.json").write_text(json.dumps(
            {"schema": 1, "slug": "eswa", "journal": {"name": "Expert Systems with Applications",
                                                      "publisher": publisher}}), encoding="utf-8")


class BuildAiUsageTests(_Workspace):
    def test_each_phase_reports_its_agent_tools_sessions_and_approvals(self) -> None:
        self.chat(
            _line("user", "<command-name>/plausibility</command-name><command-args>idea</command-args>",
                  "2026-10-01T10:00:00Z"),
            _line("assistant", [{"type": "text", "text": "Report ready."}], "2026-10-01T10:01:00Z"),
            _line("user", "aprobado", "2026-10-01T10:02:00Z"),
            _line("user", "/proposal-implementation run the poc", "2026-10-02T10:00:00Z"),
            _line("assistant", [{"type": "text", "text": "Implemented."}], "2026-10-02T10:01:00Z"),
            _line("user", "fix the seed handling", "2026-10-02T10:02:00Z"),
        )
        usage = ai_history.build_ai_usage(self.root, self.sessions())
        phases = {p["stage_id"]: p for p in usage["phases"]}

        self.assertEqual(list(phases), ["plausibility", "poc_experiments"])
        self.assertEqual(usage["harnesses"], ["claude-code"])
        plaus = phases["plausibility"]
        self.assertEqual(plaus["agent"], phase_actions.ACTIONS["plausibility"]["agent"])
        self.assertEqual(plaus["harnesses"], ["claude-code"])
        self.assertIsNone(plaus["model"])
        self.assertEqual(plaus["counts"]["sessions"], 1)
        self.assertEqual(plaus["counts"]["commands"], 1)
        self.assertEqual(plaus["counts"]["approvals"], 1)
        self.assertEqual(plaus["counts"]["user_messages"], 0)
        self.assertEqual(phases["poc_experiments"]["counts"]["user_messages"], 1)
        self.assertEqual(phases["poc_experiments"]["counts"]["approvals"], 0)

    def test_revisions_are_counted_under_the_proposal_phase(self) -> None:
        (self.root / "proposals").mkdir()
        for n in (1, 2):
            (self.root / "proposals" / f"research-concept-x-r{n:02d}.md").write_text("x", encoding="utf-8")
        usage = ai_history.build_ai_usage(self.root, self.sessions())
        phases = {p["stage_id"]: p for p in usage["phases"]}
        self.assertEqual(phases["proposal"]["counts"]["revisions"], 2)
        self.assertEqual(phases["proposal"]["harnesses"], [])

    def test_the_history_pane_is_unchanged_by_the_shared_collection(self) -> None:
        self.chat(_line("user", "/plausibility idea", "2026-10-01T10:00:00Z"),
                  _line("assistant", [{"type": "text", "text": "Done."}], "2026-10-01T10:01:00Z"))
        view = ai_history.build_ai_history(
            self.root, [{"id": "Fase 2", "stage_id": "plausibility", "status": "PASS", "gate": "G"}],
            sessions=self.sessions())
        self.assertEqual(view["phases"][0]["color"], "green")
        self.assertEqual([e["kind"] for e in view["phases"][0]["events"]], ["command", "agent_reply"])


class PaperAiUsageTests(_Workspace):
    def test_the_record_joins_drafted_blocks_tools_and_the_methods_sentence_rule(self) -> None:
        self.manuscript()
        self.chat(_line("user", "/experimental-implementation full run", "2026-10-02T10:00:00Z"),
                  _line("assistant", [{"type": "text", "text": "Ran."}], "2026-10-02T10:01:00Z"))
        record = paper_ai_usage.build(self.paper, sessions=self.sessions())

        self.assertEqual(record["pipeline"]["status"], "ok")
        self.assertEqual(record["tools"], ["claude-code"])
        self.assertTrue(record["code_or_experiments_by_agents"])
        self.assertTrue(record["methods_sentence_required"])
        self.assertEqual(record["drafted"]["sections"], ["conclusions"])
        self.assertEqual(record["drafted"]["blocks"], [{
            "id": "conclusions.concl-block-1", "section": "conclusions",
            "drafted_by": "redactor", "audited_by": "contract-auditor",
            "attempts": 2, "evidence_ledger": False,
        }])
        self.assertEqual(record["venues"], [])

    def test_without_agent_code_no_methods_sentence_is_required(self) -> None:
        self.manuscript()
        self.chat(_line("user", "/plausibility idea", "2026-10-01T10:00:00Z"))
        record = paper_ai_usage.build(self.paper, sessions=self.sessions())
        self.assertFalse(record["code_or_experiments_by_agents"])
        self.assertFalse(record["methods_sentence_required"])

    def test_the_record_names_the_framework_with_its_repository_and_version(self) -> None:
        (self.root / ".papersmith").mkdir(exist_ok=True)
        (self.root / ".papersmith" / "version").write_text("0.58.2\n", encoding="utf-8")
        record = paper_ai_usage.build(self.paper, sessions=self.sessions())
        self.assertEqual(record["framework"], {
            "name": "papersmith",
            "url": "https://github.com/LIAUNAL/papersmith-ai",
            "version": "0.58.2",
        })

    def test_without_a_recorded_version_the_framework_version_is_none(self) -> None:
        version = self.root / ".papersmith" / "version"
        if version.exists():
            version.unlink()
        record = paper_ai_usage.build(self.paper, sessions=self.sessions())
        self.assertEqual(record["framework"]["url"], "https://github.com/LIAUNAL/papersmith-ai")
        self.assertIsNone(record["framework"]["version"])

    def test_the_declaration_contract_requires_citing_the_framework_repository(self) -> None:
        contract = (REPO / "sections" / "10-back-matter.md").read_text(encoding="utf-8")
        section = contract[contract.index("## AI-use declaration"):]
        self.assertIn("https://github.com/LIAUNAL/papersmith-ai", section)

    def test_a_paper_without_main_tex_degrades_instead_of_refusing(self) -> None:
        record = paper_ai_usage.build(self.paper, sessions=self.sessions())
        self.assertEqual(record["drafted"]["status"], "unavailable")
        self.assertEqual(record["drafted"]["detail"], "PAPER_ABSENT")
        self.assertEqual(record["drafted"]["blocks"], [])

    def test_the_record_never_writes(self) -> None:
        self.manuscript()
        self.venue("Elsevier BV")
        before = sorted((p.relative_to(self.root).as_posix(), p.read_bytes())
                        for p in self.root.rglob("*") if p.is_file())
        paper_ai_usage.build(self.paper, sessions=self.sessions())
        after = sorted((p.relative_to(self.root).as_posix(), p.read_bytes())
                       for p in self.root.rglob("*") if p.is_file())
        self.assertEqual(after, before)


class VenuePlacementTests(_Workspace):
    def test_each_publisher_family_takes_its_own_placement(self) -> None:
        cases = {
            "Elsevier BV": ("elsevier", "own-section-before-references", "inside-acknowledgments"),
            "Multidisciplinary Digital Publishing Institute": ("mdpi", "inside-acknowledgments", "own-block"),
            "IEEE": ("ieee", "inside-acknowledgments-naming-sections", "inside-acknowledgments"),
            "Springer": ("neutral", "own-section-before-references", "own-block"),
            None: ("neutral", "own-section-before-references", "own-block"),
        }
        for publisher, (family, ai, funding) in cases.items():
            with self.subTest(publisher=publisher):
                self.assertEqual(paper_venue.publisher_family(publisher), family)
                self.assertEqual(paper_venue.BACK_MATTER_PLACEMENT[family]["ai_declaration"], ai)
                self.assertEqual(paper_venue.BACK_MATTER_PLACEMENT[family]["funding"], funding)

    def test_the_elsevier_declaration_carries_the_elsevier_title(self) -> None:
        self.venue("Elsevier BV")
        [placement] = paper_venue.back_matter_placement(self.paper)
        self.assertEqual(placement["slug"], "eswa")
        self.assertEqual(placement["family"], "elsevier")
        self.assertTrue(placement["highlights"])
        self.assertEqual(
            placement["ai_declaration_title"],
            "Declaration of generative AI and AI-assisted technologies in the manuscript preparation process")
        # The title the venue rule names is the one the contract states.
        self.assertIn(placement["ai_declaration_title"],
                      " ".join((SECTIONS / "10-back-matter.md").read_text(encoding="utf-8").split()))


class PacketTests(_Workspace):
    def _packet(self, section: str, block: str) -> dict:
        return paper_cli.assemble_packet(SECTIONS, self.root / "guidance", section, block,
                                         paper_dir=self.paper)

    def test_the_declaration_block_packet_carries_the_ai_usage_record(self) -> None:
        self.manuscript()
        self.venue("MDPI")
        packet = self._packet("back-matter", "bm-ai-use-declaration")
        usage = packet["ai_usage"]
        self.assertEqual(usage["schema"], 1)
        self.assertEqual(usage["drafted"]["sections"], ["conclusions"])
        self.assertEqual([v["family"] for v in usage["venues"]], ["mdpi"])
        self.assertEqual(usage["venues"][0]["ai_declaration"], "inside-acknowledgments")
        self.assertIn("## AI-use declaration", packet["contract"])

    def test_the_methods_sentence_block_packet_carries_it_too(self) -> None:
        self.manuscript()
        packet = self._packet("experimental-setup", "es-training-details")
        self.assertIn("ai_usage", packet)

    def test_every_other_packet_keeps_its_previous_shape(self) -> None:
        self.manuscript()
        packet = self._packet("back-matter", "bm-funding")
        self.assertEqual(set(packet), {"block", "section", "contract", "references",
                                       "source_sections", "source_sections_state"})


if __name__ == "__main__":
    unittest.main()
