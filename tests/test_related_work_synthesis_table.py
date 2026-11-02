"""Related-work synthesis table: 7 to 12 works (spec S1 of
`odd/tasks/manuscript-polish-0-54.md`).

The count is deterministic and cheap, so the contract-audit stage cross-checks
the auditor's account against the draft: a `clear` verdict on the row-count
disqualifier over a table that places fewer than 7 or more than 12 works is
not trusted and is reported as `undecidable` with the measured count. The
check never blocks a write on its own.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "paper-writing" / "scripts"))

import paper_audit  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
_CONTRACT = _ROOT / "sections" / "05-related-work.md"


def _table(works: int, *, grouped: bool = False) -> str:
    rows = []
    for index in range(works):
        if grouped and index % 3 == 0:
            rows.append(rf"\multicolumn{{4}}{{l}}{{\emph{{Family {index // 3}}}}} \\")
        rows.append(rf"Work{index} \cite{{w{index}}} & F{index % 3} & \checkmark & -- \\")
    body = "\n".join(rows)
    return (
        "\\begin{table}[t]\n\\caption{Legend: \\checkmark{} holds; -- absent.}\n"
        "\\begin{tabularx}{\\linewidth}{lXcc}\n\\toprule\n"
        "Work & Family & Online & Calibrated \\\\\n\\midrule\n"
        f"{body}\n\\midrule\nProposed & -- & \\checkmark & \\checkmark \\\\\n"
        "\\bottomrule\n\\end{tabularx}\n\\end{table}\n"
    )


def _contract_with_row_bullet() -> str:
    return (
        "# Related Work\n\n## Disqualifiers\n\n"
        f"- {paper_audit.ROW_COUNT_BULLET}\n"
        "- An equation.\n"
    )


def _verdicts(row_verdict: str, span: str = "") -> list[dict]:
    return [
        {"bullet": paper_audit.ROW_COUNT_BULLET, "verdict": row_verdict, "span": span},
        {"bullet": "An equation.", "verdict": "clear", "span": ""},
    ]


class SynthesisTableWorkCountTests(unittest.TestCase):
    def test_counts_works_excluding_header_and_proposal_rows(self) -> None:
        self.assertEqual(paper_audit.count_table_works(_table(9)), 9)

    def test_family_group_rows_are_not_works(self) -> None:
        self.assertEqual(paper_audit.count_table_works(_table(9, grouped=True)), 9)

    def test_a_draft_without_a_table_measures_nothing(self) -> None:
        self.assertIsNone(paper_audit.count_table_works("Prose with no table."))

    def test_out_of_range_counts_are_reported(self) -> None:
        self.assertIsNone(paper_audit.row_count_finding(_table(7)))
        self.assertIsNone(paper_audit.row_count_finding(_table(12)))
        self.assertIn("6", paper_audit.row_count_finding(_table(6)))
        self.assertIn("13", paper_audit.row_count_finding(_table(13)))


class SynthesisTableAuditCrossCheckTests(unittest.TestCase):
    def test_clear_over_too_few_works_is_reported_undecidable_and_does_not_block(self) -> None:
        result = paper_audit.audit(_contract_with_row_bullet(), _table(5), _verdicts("clear"))
        entry = result["verdicts"][0]
        self.assertEqual(entry["verdict"], "undecidable")
        self.assertIn("5", entry["deterministic"])
        self.assertFalse(result["blocks"])

    def test_clear_over_too_many_works_is_reported_undecidable(self) -> None:
        result = paper_audit.audit(_contract_with_row_bullet(), _table(14), _verdicts("clear"))
        self.assertEqual(result["verdicts"][0]["verdict"], "undecidable")

    def test_clear_over_an_in_range_table_stays_clear_without_extra_keys(self) -> None:
        result = paper_audit.audit(_contract_with_row_bullet(), _table(10), _verdicts("clear"))
        self.assertEqual(result["verdicts"][0], {
            "bullet": paper_audit.ROW_COUNT_BULLET, "verdict": "clear", "span": "",
        })

    def test_a_fires_verdict_with_a_real_span_still_blocks(self) -> None:
        draft = _table(5)
        result = paper_audit.audit(_contract_with_row_bullet(), draft, _verdicts("fires", "Work0"))
        self.assertTrue(result["blocks"])

    def test_other_bullets_are_never_cross_checked(self) -> None:
        result = paper_audit.audit(_contract_with_row_bullet(), _table(3), _verdicts("clear"))
        self.assertEqual(result["verdicts"][1], {"bullet": "An equation.", "verdict": "clear", "span": ""})


class ShippedContractCarriesTheRuleTests(unittest.TestCase):
    def test_contract_05_lists_the_row_count_bullet_verbatim(self) -> None:
        bullets = paper_audit.extract_disqualifiers(_CONTRACT.read_text(encoding="utf-8"))
        self.assertIn(paper_audit.ROW_COUNT_BULLET, bullets)

    def test_contract_05_lists_the_family_column_and_prose_disqualifiers(self) -> None:
        bullets = paper_audit.extract_disqualifiers(_CONTRACT.read_text(encoding="utf-8"))
        joined = "\n".join(bullets)
        self.assertIn("A family of this section with no row in the synthesis table.", bullets)
        self.assertIn("not tied to a pillar, contribution or property", joined)
        self.assertIn("prose in a synthesis-table cell", joined)


if __name__ == "__main__":
    unittest.main()
