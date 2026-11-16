"""`reorder` (#184 item 4, odd/tasks/daprosero-backlog.md S6.4): move canonical
back-matter blocks into the order `verify`'s `back-matter-order` check expects
(declarations before the reference list, appendices after it).

Byte-preserving block moves, a report by default and a write only with
`--apply`, idempotent, and a refusal (`REORDER_LAYOUT_AMBIGUOUS`) when the
layout gives no single place to move a block to. Every test goes through
`paper_cli.main`; fixtures live under the git-ignored `.scratch/` because the
paper must resolve inside the repository.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))
import paper_cli  # noqa: E402
import paper_verify  # noqa: E402


def _run_cli(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with mock.patch("sys.stdout", buf):
        exit_code = paper_cli.main(argv)
    return exit_code, json.loads(buf.getvalue())


def _block(block_id: str, body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return (f"%% paper-writing block {block_id} begin sha256={digest}\n"
            f"{body}%% paper-writing block {block_id} end\n")


_CONCLUSIONS = _block("conclusions.findings", "We found two things.\n")
_FUNDING = _block("back-matter.bm-funding", "\\section*{Funding}\nNone.\r\n")
_DATA = _block("back-matter.bm-data", "\\section*{Data availability}\nOn request.\n")
_APPENDIX = _block("back-matter.bm-appendices", "\\appendix\n\\section{Proofs}\nLong proof.\n")
_HEAD = "\\documentclass{article}\n\\begin{document}\n"
_BIB = "\\bibliographystyle{plain}\n\\bibliography{refs}\n"
_TAIL = "\\end{document}\n"


class _ReorderFixture(unittest.TestCase):
    def setUp(self) -> None:
        scratch_root = REPO / ".scratch"
        scratch_root.mkdir(exist_ok=True)
        holder = tempfile.TemporaryDirectory(dir=scratch_root, prefix="reorder-")
        self.addCleanup(holder.cleanup)
        self.paper_dir = Path(holder.name) / "paper"
        self.paper_dir.mkdir()
        self.main_tex = self.paper_dir / "main.tex"
        self.rel = str(self.paper_dir.relative_to(REPO))

    def write(self, text: str) -> None:
        self.main_tex.write_bytes(text.encode("utf-8"))

    def verify_order(self) -> str:
        """`verify`'s own back-matter-order check over the bytes on disk."""
        evidence = SimpleNamespace(main_tex_bytes=self.main_tex.read_bytes())
        return paper_verify.check_back_matter_order(evidence)["verdict"]


class ReorderTests(_ReorderFixture):
    misplaced = _HEAD + _CONCLUSIONS + _FUNDING + _APPENDIX + _BIB + _DATA + _TAIL
    canonical = _HEAD + _CONCLUSIONS + _FUNDING + _DATA + _BIB + _APPENDIX + _TAIL

    def test_report_mode_lists_the_moves_and_writes_nothing(self) -> None:
        self.write(self.misplaced)
        code, payload = _run_cli(["reorder", "--paper", self.rel])
        self.assertEqual(code, 0, payload)
        self.assertFalse(payload["applied"])
        self.assertTrue(payload["changed"])
        self.assertEqual(
            [(m["block"], m["to"]) for m in payload["moves"]],
            # Document order of the misplaced blocks.
            [("back-matter.bm-appendices", "after-references"),
             ("back-matter.bm-data", "before-references")],
        )
        self.assertEqual(self.main_tex.read_bytes(), self.misplaced.encode("utf-8"))
        self.assertFalse((self.paper_dir / ".paper-writing").exists())

    def test_apply_moves_the_blocks_byte_for_byte_into_the_verified_order(self) -> None:
        self.write(self.misplaced)
        self.assertEqual(self.verify_order(), "fail")
        code, payload = _run_cli(["reorder", "--paper", self.rel, "--apply"])
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["applied"])
        self.assertEqual(payload["back_matter_order"], "pass")
        self.assertEqual(self.main_tex.read_bytes(), self.canonical.encode("utf-8"))
        self.assertEqual(self.verify_order(), "pass")
        prev = self.paper_dir / ".paper-writing" / "main.tex.prev"
        self.assertEqual(prev.read_bytes(), self.misplaced.encode("utf-8"))

    def test_a_second_apply_is_a_no_op(self) -> None:
        self.write(self.canonical)
        code, payload = _run_cli(["reorder", "--paper", self.rel, "--apply"])
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["moves"], [])
        self.assertFalse(payload["changed"])
        self.assertFalse(payload["applied"])
        self.assertEqual(self.main_tex.read_bytes(), self.canonical.encode("utf-8"))
        self.assertFalse((self.paper_dir / ".paper-writing").exists())

    def test_a_hand_bibliography_environment_keeps_appendices_after_its_end(self) -> None:
        bib = "\\begin{thebibliography}{1}\n\\bibitem{a} A.\n\\end{thebibliography}\n"
        self.write(_HEAD + _APPENDIX + bib + _TAIL)
        code, payload = _run_cli(["reorder", "--paper", self.rel, "--apply"])
        self.assertEqual(code, 0, payload)
        self.assertEqual(self.main_tex.read_text(encoding="utf-8"), _HEAD + bib + _APPENDIX + _TAIL)


    def test_the_front_door_reports_an_ordered_paper_as_ok(self) -> None:
        self.write(self.canonical)
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            exit_code = paper_cli.main(["reorder", "--paper", self.rel])
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(buf.getvalue()),
                         {"status": "ok", "command": "reorder", "moves": [], "changed": False,
                          "applied": False, "back_matter_order": "pass"})


class ReorderRefusalTests(_ReorderFixture):
    def assert_refused(self, text: str, fragment: str) -> None:
        self.write(text)
        code, payload = _run_cli(["reorder", "--paper", self.rel, "--apply"])
        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], "REORDER_LAYOUT_AMBIGUOUS")
        self.assertIn(fragment, payload["detail"])
        self.assertEqual(self.main_tex.read_bytes(), text.encode("utf-8"))
        self.assertFalse((self.paper_dir / ".paper-writing").exists())

    def test_no_reference_list_refuses(self) -> None:
        self.assert_refused(_HEAD + _APPENDIX + _FUNDING + _TAIL, "no reference list")

    def test_two_reference_lists_refuse(self) -> None:
        self.assert_refused(_HEAD + _APPENDIX + _BIB + _FUNDING + "\\printbibliography\n" + _TAIL,
                            "2 reference lists")

    def test_a_reference_list_inside_a_block_refuses(self) -> None:
        self.assert_refused(
            _HEAD + _APPENDIX + _block("back-matter.bm-refs", "\\bibliography{refs}\n") + _TAIL,
            "inside block 'back-matter.bm-refs'",
        )

    def test_an_unpaired_marker_still_refuses_its_own_code(self) -> None:
        text = _HEAD + "%% paper-writing block back-matter.bm-data begin sha256=" + "0" * 64 + "\n" + _BIB + _TAIL
        self.write(text)
        code, payload = _run_cli(["reorder", "--paper", self.rel])
        self.assertEqual(code, 2)
        self.assertEqual(payload["code"], "BLOCK_UNPAIRED")


class ReorderHelpTests(unittest.TestCase):
    def test_the_verb_and_its_apply_flag_are_documented(self) -> None:
        parser = paper_cli.build_parser()
        sub = next(a for a in parser._actions if a.dest == "command")
        text = sub.choices["reorder"].format_help()
        self.assertIn("--apply", text)
        self.assertIn("back-matter", text)


if __name__ == "__main__":
    unittest.main()
