"""`figure-table-balance`: in Methods and Results, data figures outnumber tables.

`odd/tasks/figures-over-tables.md`, S3. `verify` counts the figure
environments (`figure`, `figure*`) and the table environments (`table`,
`table*`, `longtable`) inside the blocks of the line's Methods and
Results/Discussion sections, and passes when figures / (figures + tables)
is at least 0.6. With no table there is nothing to violate: it passes. A manuscript whose
block markers carry no section falls back to the body before the back matter.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))

import paper_verify  # noqa: E402


class Evidence:
    """The one field the check reads."""

    def __init__(self, tex: str) -> None:
        self.main_tex_bytes = tex.encode("utf-8")


def block(block_id: str, body: str) -> str:
    return (f"%% paper-writing block {block_id} begin sha256={'0' * 64}\n{body}"
            f"%% paper-writing block {block_id} end\n")


FIGURE = "\\begin{figure}[t]\\centering\\includegraphics{a.pdf}\\caption{A.}\\end{figure}\n"
FIGURE_WIDE = "\\begin{figure*}\\includegraphics{b.pdf}\\caption{B.}\\end{figure*}\n"
TABLE = "\\begin{table}\\begin{tabular}{lll}a&b&c\\\\\\end{tabular}\\caption{T.}\\end{table}\n"
TABLE_WIDE = "\\begin{table*}\\begin{tabular}{lll}a&b&c\\\\\\end{tabular}\\end{table*}\n"
LONGTABLE = "\\begin{longtable}{lll}a&b&c\\\\\\end{longtable}\n"


def paper(*blocks: str, tail: str = "") -> str:
    return ("\\documentclass{article}\n\\begin{document}\n" + "".join(blocks)
            + "\\bibliography{refs}\n" + tail + "\\end{document}\n")


def check(tex: str) -> dict:
    return paper_verify.check_figure_table_balance(Evidence(tex))


class RosterTests(unittest.TestCase):
    def test_the_check_is_a_mechanical_member_of_the_roster(self) -> None:
        self.assertIn("figure-table-balance", paper_verify.CHECKS)
        self.assertNotIn("NO_FLOAT_IN_METHODS_RESULTS", paper_verify.UNMEASURED_REASONS)
        self.assertEqual(check(paper(block("methods.m-1", FIGURE)))["classification"], "mechanical")


class VerdictTests(unittest.TestCase):
    def test_three_figures_and_two_tables_pass_at_the_threshold(self) -> None:
        tex = paper(block("methods.m-1", FIGURE + TABLE),
                    block("results.r-1", FIGURE + FIGURE_WIDE + TABLE_WIDE))
        entry = check(tex)
        self.assertEqual(entry["verdict"], "pass")
        self.assertIsNone(entry["unmeasured_reason"])
        self.assertEqual(entry["evidence"]["figures"], 3)
        self.assertEqual(entry["evidence"]["tables"], 2)
        self.assertEqual(entry["evidence"]["ratio"], 0.6)
        self.assertEqual(entry["evidence"]["threshold"], 0.6)
        self.assertEqual(entry["evidence"]["blocks"], ["methods.m-1", "results.r-1"])
        self.assertEqual(entry["evidence"]["scope"], "sections")

    def test_a_table_heavy_results_section_fails(self) -> None:
        tex = paper(block("materials-and-methods.mm-1", TABLE),
                    block("results-and-discussion.rd-1", FIGURE + TABLE + TABLE_WIDE))
        entry = check(tex)
        self.assertEqual(entry["verdict"], "fail")
        self.assertEqual((entry["evidence"]["figures"], entry["evidence"]["tables"]), (1, 3))
        self.assertEqual(entry["evidence"]["ratio"], 0.25)

    def test_sections_with_no_float_pass_vacuously(self) -> None:
        tex = paper(block("methods.m-1", "Prose only.\n"),
                    block("introduction.block-2", TABLE + TABLE))
        entry = check(tex)
        self.assertEqual(entry["verdict"], "pass")
        self.assertIsNone(entry["unmeasured_reason"])
        self.assertEqual((entry["evidence"]["figures"], entry["evidence"]["tables"]), (0, 0))
        self.assertIsNone(entry["evidence"]["ratio"])

    def test_figures_only_pass(self) -> None:
        entry = check(paper(block("results.r-1", FIGURE + FIGURE_WIDE)))
        self.assertEqual(entry["verdict"], "pass")
        self.assertEqual((entry["evidence"]["figures"], entry["evidence"]["tables"], entry["evidence"]["ratio"]),
                         (2, 0, 1.0))

    def test_a_longtable_counts_as_a_table(self) -> None:
        entry = check(paper(block("results.r-1", FIGURE + LONGTABLE)))
        self.assertEqual((entry["evidence"]["figures"], entry["evidence"]["tables"]), (1, 1))
        self.assertEqual(entry["verdict"], "fail")


class CountingTests(unittest.TestCase):
    def test_only_methods_and_results_blocks_count(self) -> None:
        tex = paper(block("introduction.block-2", TABLE + TABLE + TABLE),
                    block("results.r-1", FIGURE),
                    block("limitations.lim-1", TABLE),
                    block("back-matter.bm-appendices", TABLE))
        entry = check(tex)
        self.assertEqual((entry["evidence"]["figures"], entry["evidence"]["tables"]), (1, 0))
        self.assertEqual(entry["verdict"], "pass")
        self.assertEqual(entry["evidence"]["blocks"], ["results.r-1"])

    def test_every_line_names_its_methods_and_results_sections(self) -> None:
        for section in ("materials-and-methods", "experimental-setup", "results-and-discussion",
                        "methods", "results", "discussion", "data-records", "technical-validation",
                        "hardware-description", "validation-characterization"):
            with self.subTest(section=section):
                entry = check(paper(block(f"{section}.b-1", FIGURE)))
                self.assertEqual(entry["evidence"]["figures"], 1)

    def test_a_commented_float_never_counts(self) -> None:
        tex = paper(block("results.r-1", FIGURE + "% \\begin{table}\n%\\begin{longtable}{l}\n"))
        self.assertEqual(check(tex)["evidence"]["tables"], 0)

    def test_an_unqualified_manuscript_falls_back_to_the_body_and_says_so(self) -> None:
        tex = paper(block("block-2", FIGURE + FIGURE), block("rd-1", TABLE),
                    tail="\\appendix\n" + TABLE + TABLE)
        entry = check(tex)
        self.assertEqual(entry["evidence"]["scope"], "body")
        self.assertEqual((entry["evidence"]["figures"], entry["evidence"]["tables"]), (2, 1))
        self.assertEqual(entry["verdict"], "pass")
        self.assertTrue(any("back matter" in limit for limit in entry["limits"]), entry["limits"])

    def test_the_body_fallback_stops_at_the_first_back_matter_block(self) -> None:
        tex = ("\\begin{document}\n" + FIGURE + TABLE + TABLE
               + block("back-matter.bm-funding", FIGURE + FIGURE + FIGURE)
               + "\\end{document}\n")
        entry = check(tex)
        self.assertEqual(entry["evidence"]["scope"], "body")
        self.assertEqual((entry["evidence"]["figures"], entry["evidence"]["tables"]), (1, 2))


class RunTests(unittest.TestCase):
    def test_run_reports_the_check_once(self) -> None:
        class Full(Evidence):
            refs_bib_bytes = b""
            record: dict = {}
            provenance = None
            contract_drift: dict = {}
            block_bodies: dict = {}
            blocks_by_fact: dict = {}
            figure_semantics = None
            producers_by_fact: dict = {}

        report = paper_verify.run(Full(paper(block("results.r-1", FIGURE))))
        entries = [entry for entry in report["checks"] if entry["check"] == "figure-table-balance"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["verdict"], "pass")


if __name__ == "__main__":
    unittest.main()
