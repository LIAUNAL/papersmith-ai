"""`caption-length`: a figure or table caption is at most four lines.

`odd/tasks/figures-over-tables.md`, S6. `verify` counts the words of each
`\\caption{...}` in `main.tex` (braces balanced, `\\caption[short]{long}`
read on its long title): LaTeX commands are stripped while their text
arguments keep their words, `\\ref`, `\\cite` and `\\label` count as no word,
and an inline math span counts as one word. A caption over 70 words, about
four lines of a single-column caption, fails; no caption passes.
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


def words(n: int, word: str = "word") -> str:
    return " ".join([word] * n)


def figure(caption: str, label: str | None = "fig:a") -> str:
    tail = f"\\label{{{label}}}" if label else ""
    return f"\\begin{{figure}}\\includegraphics{{a.pdf}}\\caption{caption}{tail}\\end{{figure}}\n"


def check(tex: str) -> dict:
    return paper_verify.check_caption_length(Evidence("\\begin{document}\n" + tex + "\\end{document}\n"))


class RosterTests(unittest.TestCase):
    def test_the_check_is_a_mechanical_member_of_the_roster(self) -> None:
        self.assertIn("caption-length", paper_verify.CHECKS)
        self.assertNotIn("NO_CAPTION", paper_verify.UNMEASURED_REASONS)
        self.assertEqual(paper_verify.CAPTION_WORDS, 70)
        self.assertEqual(check(figure("{" + words(3) + "}"))["classification"], "mechanical")


class VerdictTests(unittest.TestCase):
    def test_captions_at_seventy_words_pass(self) -> None:
        entry = check(figure("{" + words(70) + "}") + figure("{" + words(12) + "}", "fig:b"))
        self.assertEqual(entry["verdict"], "pass")
        self.assertEqual(entry["evidence"]["captions"], 2)
        self.assertEqual(entry["evidence"]["max_words"], 70)
        self.assertEqual(entry["evidence"]["over_limit"], [])
        self.assertTrue(any("main.tex" in limit for limit in entry["limits"]), entry["limits"])

    def test_a_caption_over_seventy_words_fails_naming_its_label(self) -> None:
        entry = check(figure("{" + words(71) + "}", "fig:long") + figure("{Short title.}", "fig:b"))
        self.assertEqual(entry["verdict"], "fail")
        self.assertEqual(entry["evidence"]["over_limit"], [{"caption": "fig:long", "words": 71}])
        self.assertEqual(entry["evidence"]["max_words"], 71)
        self.assertEqual(entry["evidence"]["limit"], 70)

    def test_an_unlabelled_caption_is_named_by_its_first_five_words(self) -> None:
        entry = check(figure("{" + "Alpha beta gamma delta epsilon " + words(80) + "}", label=None))
        self.assertEqual(entry["evidence"]["over_limit"][0]["caption"], "Alpha beta gamma delta epsilon")

    def test_no_caption_passes_with_zero_words(self) -> None:
        entry = check("Prose only.\n")
        self.assertEqual(entry["verdict"], "pass")
        self.assertIsNone(entry["unmeasured_reason"])
        self.assertEqual((entry["evidence"]["captions"], entry["evidence"]["max_words"]), (0, 0))


class WordRuleTests(unittest.TestCase):
    def count(self, caption: str) -> int:
        return check(figure(caption))["evidence"]["max_words"]

    def test_nested_braces_stay_inside_the_caption(self) -> None:
        self.assertEqual(self.count("{Accuracy of \\emph{the {nested} model} per fold.}"), 7)

    def test_the_optional_short_caption_is_not_counted(self) -> None:
        self.assertEqual(self.count("[Short list entry here]{Two words.}"), 2)

    def test_an_inline_math_span_is_one_word(self) -> None:
        self.assertEqual(self.count("{Error $\\epsilon = \\|x - \\hat{x}\\|_2$ against \\(n\\) samples.}"), 5)

    def test_references_citations_and_labels_count_as_no_word(self) -> None:
        self.assertEqual(self.count("{Results of \\cite{a,b} as in Fig.~\\ref{fig:x}.\\label{fig:y}}"), 5)

    def test_a_commented_caption_never_counts(self) -> None:
        entry = check("% \\caption{" + words(80) + "}\n" + figure("{Short.}"))
        self.assertEqual((entry["evidence"]["captions"], entry["verdict"]), (1, "pass"))


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

        report = paper_verify.run(Full(figure("{Short.}")))
        entries = [entry for entry in report["checks"] if entry["check"] == "caption-length"]
        self.assertEqual([entry["verdict"] for entry in entries], ["pass"])
        self.assertEqual(paper_verify.CHECKS[-2:], ("figure-table-balance", "caption-length"))


if __name__ == "__main__":
    unittest.main()
