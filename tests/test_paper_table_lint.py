"""Source lint for tables in the paper-writing write path (spec S5 of
`odd/tasks/figure-and-table-quality.md`).

A table never shrinks to fit: no `\\resizebox`/`\\scalebox`/`adjustbox`
below 0.85 or to a width, and no size switch inside a table that prints
below 0.70 times the body size. Spec S2 of
`odd/tasks/manuscript-polish-0-54.md` adds the cap: a table's text
prints at most 0.90 times the body size, so a table left at the body size
(no size switch: `\\normalsize`) is warned too. The lint warns; it never
refuses a write.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))
import paper_bindings  # noqa: E402
import paper_latex  # noqa: E402
import paper_write  # noqa: E402

CLEAN = r"""
\begin{table}[t]
\footnotesize
\caption{search ranges}
\begin{tabularx}{\textwidth}{lX}
\toprule
knob & range \\
\midrule
rate & small to large \\
\bottomrule
\end{tabularx}
\end{table}
"""


def rules(latex: str, body_pt: float = 10.0) -> list[str]:
    return [finding["rule"] for finding in paper_latex.lint_tables(latex, body_pt)]


class TableScalingLintTests(unittest.TestCase):
    def test_a_clean_booktabs_table_has_no_findings(self) -> None:
        self.assertEqual(rules(CLEAN), [])

    def test_resizebox_of_a_tabular_is_flagged(self) -> None:
        latex = r"\resizebox{\textwidth}{!}{\begin{tabular}{ll}\footnotesize a & b\\\end{tabular}}"
        self.assertEqual(rules(latex), ["table-scaled-to-width"])

    def test_scalebox_below_the_floor_is_flagged_and_above_it_is_not(self) -> None:
        low = r"\scalebox{0.7}{\begin{tabular}{l}\footnotesize a\\\end{tabular}}"
        high = r"\scalebox{0.9}{\begin{tabular}{l}\footnotesize a\\\end{tabular}}"
        self.assertEqual(rules(low), ["table-scaled-below-floor"])
        self.assertEqual(rules(high), [])

    def test_adjustbox_width_and_low_scale_are_flagged(self) -> None:
        width = r"\begin{adjustbox}{width=\textwidth}\begin{tabular}{l}\footnotesize a\\\end{tabular}\end{adjustbox}"
        scale = r"\begin{adjustbox}{scale=0.8}\begin{tabular}{l}\footnotesize a\\\end{tabular}\end{adjustbox}"
        self.assertEqual(rules(width), ["table-scaled-to-width"])
        self.assertEqual(rules(scale), ["table-scaled-below-floor"])

    def test_scaling_that_wraps_no_table_is_not_a_table_finding(self) -> None:
        self.assertEqual(rules(r"\scalebox{0.5}{$x$} and \resizebox{2cm}{!}{text}"), [])


class TableFontFloorLintTests(unittest.TestCase):
    def test_tiny_inside_a_table_with_an_eleven_point_body_is_flagged(self) -> None:
        latex = CLEAN.replace(r"\caption", r"\tiny\caption")
        findings = paper_latex.lint_tables(latex, 11.0)
        self.assertEqual([f["rule"] for f in findings], ["table-font-below-floor"])
        self.assertEqual(findings[0]["command"], r"\tiny")
        self.assertLess(findings[0]["size_pt"], findings[0]["min_printed_pt"])
        self.assertEqual(findings[0]["line"], 4)

    def test_scriptsize_meets_the_floor_at_ten_points_but_not_at_twelve(self) -> None:
        latex = CLEAN.replace(r"\toprule", r"\scriptsize\toprule")
        self.assertEqual(rules(latex, 10.0), [])
        self.assertEqual(rules(latex, 12.0), ["table-font-below-floor"])

    def test_a_size_switch_outside_any_table_is_not_a_table_finding(self) -> None:
        self.assertEqual(rules(r"\tiny some footnote text" + CLEAN, 11.0), [])


class TableFontCapLintTests(unittest.TestCase):
    """S2 of `manuscript-polish-0-54`: a table's text prints at most 0.90 x
    the body size."""

    def test_a_table_at_the_body_size_is_flagged_once_at_its_opening(self) -> None:
        latex = CLEAN.replace("\\footnotesize\n", "")
        findings = paper_latex.lint_tables(latex, 10.0)
        self.assertEqual([f["rule"] for f in findings], ["table-font-above-cap"])
        self.assertEqual(findings[0]["command"], "\\normalsize (default)")
        self.assertEqual(findings[0]["line"], 2)
        self.assertEqual((findings[0]["size_pt"], findings[0]["max_printed_pt"]), (10.0, 9.0))

    def test_an_explicit_normalsize_or_larger_switch_is_flagged(self) -> None:
        for switch in ("normalsize", "large"):
            with self.subTest(switch=switch):
                latex = CLEAN.replace("\\footnotesize", "\\" + switch)
                self.assertEqual(rules(latex), ["table-font-above-cap"])

    def test_small_sits_at_the_cap_at_ten_points_but_above_it_at_eleven(self) -> None:
        latex = CLEAN.replace("\\footnotesize", "\\small")
        self.assertEqual(rules(latex, 10.0), [])
        self.assertEqual(rules(latex, 11.0), ["table-font-above-cap"])

    def test_an_explicit_fontsize_is_judged_by_its_size(self) -> None:
        inside = CLEAN.replace("\\footnotesize", "\\fontsize{8}{9.5}\\selectfont")
        above = CLEAN.replace("\\footnotesize", "\\fontsize{10}{12}\\selectfont")
        self.assertEqual(rules(inside), [])
        self.assertEqual(rules(above), ["table-font-above-cap"])

    def test_a_bare_tabular_outside_a_table_float_is_judged_too(self) -> None:
        self.assertEqual(rules("\\begin{tabular}{l}a\\\\\\end{tabular}"), ["table-font-above-cap"])

    def test_a_size_switch_wrapping_the_float_from_outside_does_not_count(self) -> None:
        self.assertEqual(rules("{\\footnotesize\n" + CLEAN.replace("\\footnotesize\n", "") + "}"),
                         ["table-font-above-cap"])


class WritePathTableLintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.paper_dir = Path(tempfile.mkdtemp(prefix="table-lint-"))
        self.addCleanup(shutil.rmtree, self.paper_dir, ignore_errors=True)
        (self.paper_dir / "main.tex").write_text(
            "\\documentclass[11pt]{article}\n"
            "%% paper-writing block intro begin sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n"
            "%% paper-writing block intro end\n",
            encoding="utf-8",
        )
        self.contract = paper_write.BlockContract(
            block_id="intro", contract_prose="## Disqualifiers\n- None.\n",
            contract_source="contract.md", citations_regime="none", mode="argument",
            requires_facts=(), evidence_set=(),
        )
        self.audit = {"verdicts": [{"bullet": "None.", "verdict": "clear"}]}

    def _write(self, latex: str) -> dict:
        text = "The table below lists the search ranges.\n" + latex
        draft = {"latex": text, "bindings": [
            {"sentence": sentence, "binding": "structural"}
            for sentence in paper_bindings.segment_sentences(text)]}
        return paper_write.write_block(self.paper_dir, self.contract, draft, self.audit)

    def test_a_scaled_table_is_written_with_a_warning_never_refused(self) -> None:
        latex = CLEAN.replace(r"\caption", r"\tiny\caption")
        result = self._write(latex)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["tableLint"]["status"], "warnings")
        self.assertEqual(result["tableLint"]["bodyPt"], 11.0)
        self.assertEqual([f["rule"] for f in result["tableLint"]["findings"]],
                         ["table-font-below-floor"])
        self.assertIn(r"\tiny", (self.paper_dir / "main.tex").read_text(encoding="utf-8"))

    def test_a_clean_table_reports_clean_and_the_prior_envelope_is_unchanged(self) -> None:
        result = self._write(CLEAN)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["tableLint"], {
            "status": "clean", "bodyPt": 11.0, "bodySource": "option",
            "minPrintedPt": 7.7, "maxPrintedPt": 9.9, "findings": []})
        for key in ("block", "verdicts", "styleChannel", "sourceFidelity",
                    "sourceGrounding", "styleQuality", "aiStylometry"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()
