"""the-whole-cut-is-argued-before-any-section-is-claimed, U1: the pure core.

`paper_separation.claimable_sections` and `paper_separation.score_cut` --
stdlib-only, no CLI, no persistence, no corpus. A third, independent suite
alongside `tests/test_paper_writing.py` and `tests/test_paper_decisions.py`
(design.md, Decision A's own precedent: "a second class of the same name
loses tests silently" applies just as much to a third). Fixtures build real
markdown and resolve their outline through `paper_guidance.segment_markdown`
itself, never a hand-computed byte offset, so a fixture proves the same
thing a real document would.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_guidance  # noqa: E402
import paper_separation  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / "tests"))
from paper_mutation import _run_against_mutant  # noqa: E402


def _outline(markdown_text: str) -> dict:
    return paper_guidance.segment_markdown(markdown_text)


def _assert_mutation_reddened(case: unittest.TestCase, proc, *, expect_red: bool = True) -> None:
    output = proc.stdout + proc.stderr
    case.assertIn("MUTANT_IMPORTED_OK", output, output)
    if expect_red:
        case.assertNotEqual(proc.returncode, 0, output)
    else:
        case.assertEqual(proc.returncode, 0, output)


class ClaimableSectionsTests(unittest.TestCase):
    """Decision B: root-span elimination to a fixed point, then the
    shallowest remaining level, ordered by `byte_start`. No heading-level
    literal governs any of it."""

    def test_a_documents_own_title_is_excluded_its_sections_are_claimable(self):
        outline = _outline(
            "# Field Survey of Widget Alignment\n\n"
            "## 1. Background on widget metrics\n\nBody.\n\n"
            "## 2. Alignment estimators\n\nBody.\n\n"
            "## 3. Proposed alignment objective\n\nBody.\n\n"
            "## 4. Calibration procedure\n\nBody.\n\n"
            "## 5. Open problems\n\nBody.\n"
        )
        result = paper_separation.claimable_sections(outline)
        self.assertEqual(result["state"], "measured")
        self.assertEqual(result["level"], 2)
        self.assertEqual(
            result["titles"],
            (
                "1. Background on widget metrics",
                "2. Alignment estimators",
                "3. Proposed alignment objective",
                "4. Calibration procedure",
                "5. Open problems",
            ),
        )
        self.assertNotIn("Field Survey of Widget Alignment", result["titles"])

    def test_three_siblings_with_no_wrapping_title_are_all_claimable(self):
        outline = _outline(
            "# 1. Background on widget metrics\n\nBody.\n\n"
            "# 2. Alignment estimators\n\nBody.\n\n"
            "# 3. Proposed alignment objective\n\nBody.\n"
        )
        result = paper_separation.claimable_sections(outline)
        self.assertEqual(result["state"], "measured")
        self.assertEqual(result["level"], 1)
        self.assertEqual(
            result["titles"],
            (
                "1. Background on widget metrics",
                "2. Alignment estimators",
                "3. Proposed alignment objective",
            ),
        )

    def test_sections_nested_three_levels_deep_are_claimable_with_no_engine_edit(self):
        """The generality proof (design.md Decision B): a level-1 title
        wraps a level-2 divider, which wraps the real level-3 sections.
        Root-span elimination iterates twice (drop the title, then drop the
        divider) and the level-3 headings are what remains -- with no
        heading-level literal anywhere in the engine to special-case this."""
        outline = _outline(
            "# Field Survey of Widget Alignment\n\n"
            "## Overview\n\n"
            "### 1. Background on widget metrics\n\nBody.\n\n"
            "### 2. Alignment estimators\n\nBody.\n"
        )
        result = paper_separation.claimable_sections(outline)
        self.assertEqual(result["state"], "measured")
        self.assertEqual(result["level"], 3)
        self.assertEqual(
            result["titles"],
            ("1. Background on widget metrics", "2. Alignment estimators"),
        )

    def test_a_headingless_document_is_unmeasured(self):
        outline = _outline("Just prose, no headings anywhere.\n")
        result = paper_separation.claimable_sections(outline)
        self.assertEqual(result["state"], "unmeasured")
        self.assertIsNone(result["level"])
        self.assertEqual(result["titles"], ())
        self.assertEqual(result["reason"], "NO_HEADINGS")

    def test_a_single_section_document_claims_its_one_section(self):
        """Issue #184 item 6: a document with one heading (a dataset page)
        never partitions, so elimination would leave nothing and the source
        could never be bound. Its one section is claimable instead."""
        outline = _outline("# Solo Title\n\nBody only, nothing else.\n")
        result = paper_separation.claimable_sections(outline)
        self.assertEqual(result["state"], "measured")
        self.assertEqual(result["level"], 1)
        self.assertEqual(result["titles"], ("Solo Title",))
        self.assertIsNone(result["reason"])

    def test_a_chain_of_single_headings_claims_the_last_section_standing(self):
        """A title wrapping exactly one section is still eliminated; the
        section it wraps is the one claimable heading."""
        outline = _outline("# Dataset Page\n\nIntro.\n\n## Description\n\nBody.\n")
        result = paper_separation.claimable_sections(outline)
        self.assertEqual(result["state"], "measured")
        self.assertEqual(result["titles"], ("Description",))

    def test_a_multi_section_document_still_excludes_its_title(self):
        outline = _outline("# Title\n\n## A\n\nBody.\n\n## B\n\nBody.\n")
        result = paper_separation.claimable_sections(outline)
        self.assertEqual(result["titles"], ("A", "B"))
        self.assertNotIn("Title", result["titles"])

    def test_no_bare_heading_level_literal_governs_claimability(self):
        """Task 1.4's own generality check, run from within the suite too:
        `claimable_sections` may compare a heading's level only against a
        DERIVED value (the shallowest remaining level), never a literal
        integer bound like `level == 1` or `level <= 2`."""
        source = (SKILL_SCRIPTS / "paper_separation.py").read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r'"level"\]\s*(==|<=|>=|<|>)\s*\d', source),
            "a bare integer heading-level comparison governs claimability",
        )

    def test_mutation_dropping_root_span_elimination_makes_the_title_claimable(self):
        proc = _run_against_mutant(
            "remaining = _eliminate_root_spans(headings)",
            "remaining = list(headings)",
            "tests.test_paper_separation.ClaimableSectionsTests"
            ".test_a_documents_own_title_is_excluded_its_sections_are_claimable",
            source_path=SKILL_SCRIPTS / "paper_separation.py",
        )
        _assert_mutation_reddened(self, proc)

    def test_mutation_dropping_root_span_elimination_breaks_the_single_section_chain(self):
        """The second fixture: a title wrapping one section must claim the
        section, not the title, which only elimination ensures."""
        proc = _run_against_mutant(
            "remaining = _eliminate_root_spans(headings)",
            "remaining = list(headings)",
            "tests.test_paper_separation.ClaimableSectionsTests"
            ".test_a_chain_of_single_headings_claims_the_last_section_standing",
            source_path=SKILL_SCRIPTS / "paper_separation.py",
        )
        _assert_mutation_reddened(self, proc)


class ScoreCutTests(unittest.TestCase):
    """Decision D: orphan / overlap / gap, defined once, over the ordered
    claimable set. The worked example (proposal.md) reproduces exactly:
    round 1 = 4, branch A = 0, branch B = 5."""

    CLAIMABLE = (
        "1. Background on widget metrics",
        "2. Alignment estimators",
        "3. Proposed alignment objective",
        "4. Calibration procedure",
        "5. Open problems",
    )

    def test_worked_example_round_1_scores_4(self):
        claims_by_block = {
            "overview.block-a": ["1. Background on widget metrics"],
            "methods.block-b": [
                "2. Alignment estimators",
                "4. Calibration procedure",
            ],
            "methods.block-c": ["2. Alignment estimators"],
        }
        result = paper_separation.score_cut(self.CLAIMABLE, claims_by_block)
        self.assertEqual(result["total"], 4)
        self.assertEqual(
            result["orphan"],
            ["3. Proposed alignment objective", "5. Open problems"],
        )
        self.assertEqual(len(result["overlap"]), 1)
        self.assertEqual(result["overlap"][0]["title"], "2. Alignment estimators")
        self.assertEqual(result["overlap"][0]["count"], 1)
        self.assertEqual(
            set(result["overlap"][0]["blocks"]),
            {"methods.block-b", "methods.block-c"},
        )
        self.assertEqual(len(result["gap"]), 1)
        self.assertEqual(result["gap"][0]["block"], "methods.block-b")
        self.assertEqual(result["gap"][0]["title"], "3. Proposed alignment objective")

    def test_worked_example_branch_a_scores_0(self):
        claims_by_block = {
            "overview.block-a": ["1. Background on widget metrics"],
            "methods.block-b": [
                "2. Alignment estimators",
                "3. Proposed alignment objective",
            ],
            "methods.block-c": [
                "4. Calibration procedure",
                "5. Open problems",
            ],
        }
        result = paper_separation.score_cut(self.CLAIMABLE, claims_by_block)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["orphan"], [])
        self.assertEqual(result["overlap"], [])
        self.assertEqual(result["gap"], [])

    def test_worked_example_branch_b_scores_5(self):
        claims_by_block = {
            "overview.block-a": ["2. Alignment estimators"],
            "methods.block-b": [
                "2. Alignment estimators",
                "5. Open problems",
            ],
            "methods.block-c": ["1. Background on widget metrics"],
        }
        result = paper_separation.score_cut(self.CLAIMABLE, claims_by_block)
        self.assertEqual(result["total"], 5)
        self.assertEqual(len(result["orphan"]), 2)
        self.assertIn("3. Proposed alignment objective", result["orphan"])
        self.assertIn("4. Calibration procedure", result["orphan"])
        self.assertEqual(len(result["overlap"]), 1)
        self.assertEqual(result["overlap"][0]["count"], 1)
        self.assertEqual(len(result["gap"]), 2)

    def test_a_title_claimed_by_three_blocks_scores_two_not_one(self):
        """The k=3 fixture distinguishing `k - 1` from `min(k, 1)`
        (Decision D: "the proposal's 'one defect per instance' is
        ambiguous at k >= 3; this is the ruling"). A k=2 fixture cannot
        distinguish the two forms -- both equal 1 at k=2 -- which is
        exactly why this fixture, not the worked example's own two-block
        overlap, is the reachability proof for the `k - 1` formula."""
        result = paper_separation.score_cut(
            ("A",),
            {"block-x": ["A"], "block-y": ["A"], "block-z": ["A"]},
        )
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["overlap"]), 1)
        self.assertEqual(result["overlap"][0]["count"], 2)
        self.assertEqual(result["orphan"], [])
        self.assertEqual(result["gap"], [])

    def test_an_uncovered_title_is_an_orphan_and_nothing_else(self):
        result = paper_separation.score_cut(("A", "B"), {"block-x": ["A"]})
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["orphan"], ["B"])
        self.assertEqual(result["overlap"], [])
        self.assertEqual(result["gap"], [])

    def test_a_skipped_interior_title_is_a_gap_and_nothing_else(self):
        """`B` is claimed by a DIFFERENT block, so it is not an orphan --
        the only defect left is `block-x` skipping over it."""
        result = paper_separation.score_cut(
            ("A", "B", "C"),
            {"block-x": ["A", "C"], "block-y": ["B"]},
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["orphan"], [])
        self.assertEqual(result["overlap"], [])
        self.assertEqual(len(result["gap"]), 1)
        self.assertEqual(result["gap"][0], {"block": "block-x", "title": "B"})

    def test_an_unanchored_assignment_clears_no_orphan_and_creates_no_defect(self):
        """`score_cut` only ever sees already-anchored claims (Phase 2
        wires the corpus-anchoring filter before calling it); a title
        outside the claimable set passed in `claims_by_block` is simply
        never counted toward coverage, overlap or gap."""
        result = paper_separation.score_cut(
            ("A", "B"),
            {"block-x": ["A", "a-title-from-nowhere"]},
        )
        self.assertEqual(result["orphan"], ["B"])
        self.assertEqual(result["overlap"], [])
        self.assertEqual(result["gap"], [])
        self.assertEqual(result["total"], 1)

    def test_mutation_orphan_forced_empty_whenever_any_claim_exists(self):
        proc = _run_against_mutant(
            "orphan = [title for title in claimable if not claimants[title]]",
            "orphan = [title for title in claimable if not claimants[title] "
            "and not any(claimants.values())]",
            "tests.test_paper_separation.ScoreCutTests"
            ".test_an_uncovered_title_is_an_orphan_and_nothing_else",
            source_path=SKILL_SCRIPTS / "paper_separation.py",
        )
        _assert_mutation_reddened(self, proc)

    def test_mutation_overlap_k_minus_1_weakened_reddens_the_k_equals_3_fixture(self):
        """Per Decision D's own ambiguity note, `k - 1` and `min(k, 1)`
        agree at k=2 -- the worked example's own overlap instance cannot
        distinguish them. Only the k=3 fixture (1.6) can, and does."""
        proc = _run_against_mutant(
            "count = k - 1",
            "count = min(k, 1)",
            "tests.test_paper_separation.ScoreCutTests"
            ".test_a_title_claimed_by_three_blocks_scores_two_not_one",
            source_path=SKILL_SCRIPTS / "paper_separation.py",
        )
        _assert_mutation_reddened(self, proc)

    def test_mutation_overlap_k_minus_1_weakened_does_not_redden_a_two_block_fixture(self):
        """Documented honestly, not silently: at k=2, `k - 1` and
        `min(k, 1)` are the SAME value (1), so the worked example's own
        two-block overlap fixture is mathematically unable to distinguish
        this mutation -- it stays green under it. This is why 1.6 also
        demands the k=3 fixture above."""
        proc = _run_against_mutant(
            "count = k - 1",
            "count = min(k, 1)",
            "tests.test_paper_separation.ScoreCutTests.test_worked_example_round_1_scores_4",
            source_path=SKILL_SCRIPTS / "paper_separation.py",
        )
        _assert_mutation_reddened(self, proc, expect_red=False)

    def test_mutation_gap_interior_range_collapsed_to_min_min(self):
        proc = _run_against_mutant(
            "hi = claimed_indices[-1]",
            "hi = claimed_indices[0]",
            "tests.test_paper_separation.ScoreCutTests"
            ".test_a_skipped_interior_title_is_a_gap_and_nothing_else",
            source_path=SKILL_SCRIPTS / "paper_separation.py",
        )
        _assert_mutation_reddened(self, proc)


import test_paper_writing as tpw  # noqa: E402 -- the `separate` corpus fixture


class SingleSectionSeparateTests(tpw._SeparationCorpusMixin, unittest.TestCase):
    """Issue #184 item 6 through `separate` itself: a single-section source
    is bound, and a multi-section document's own title is still refused."""

    def test_a_single_section_dataset_page_settles_and_names_its_bind(self):
        (self.proposals / "field-survey-r07.md").write_text(
            "# CHB-MIT Scalp EEG Database\n\nRecordings from pediatric subjects.\n",
            encoding="utf-8",
        )
        proposal = {"lineage": "field-survey", "assignments": [
            {"block": "overview.block-a", "fact": "formulation",
             "sections": ["CHB-MIT Scalp EEG Database"]},
        ]}
        result = self._compute(proposal)
        self.assertEqual(result["total"], 0)
        self.assertEqual(len(result["bind_invocations"]), 1)
        self.assertIn("overview.block-a", result["bind_invocations"][0])
        rounds = self._read_rounds()
        self.assertEqual(len(rounds), 1)

    def test_a_multi_section_documents_title_is_still_unclaimable(self):
        proposal = {"lineage": "field-survey", "assignments": [
            {"block": "overview.block-a", "fact": "formulation",
             "sections": ["Field Survey of Widget Alignment"]},
        ]}
        with self.assertRaises(tpw.Refused) as ctx:
            self._compute(proposal)
        self.assertEqual(ctx.exception.code, "SEPARATION_SECTION_UNCLAIMABLE")
        self.assertEqual(self._read_rounds(), ())


class PurityTests(unittest.TestCase):
    """Threat Matrix: stdlib-only, offline. This module in particular must
    stay pure -- no CLI wiring, no persistence, no corpus assembly."""

    def test_the_module_imports_no_cli_or_persistence_symbol(self):
        source = (SKILL_SCRIPTS / "paper_separation.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "paper_cli", "paper_declarations", "paper_graph"):
            self.assertNotIn(forbidden, source, f"{forbidden!r} must not appear in paper_separation.py")


if __name__ == "__main__":
    unittest.main()
