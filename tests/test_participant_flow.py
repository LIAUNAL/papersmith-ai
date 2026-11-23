"""Participant flow diagrams for empirical studies (paper-type-lines S7, T7-U5, decision D14).

The operator enters the flow counts in `study/flow.json` from one of three
templates (CONSORT 2025, STROBE, STARD 2015); `flow_cli.py` checks the
arithmetic, renders `paper/Figures/participant-flow.svg` only from valid
counts, and records the operator's sign-off bound to the hash of the counts
and the figure. Every test goes through the CLI, as an operator or an agent
would."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "skills" / "_core" / "participant_flow" / "flow_cli.py"
SVG_NS = "{http://www.w3.org/2000/svg}"


def reasons(*pairs) -> list[dict]:
    return [{"reason": reason, "n": n} for reason, n in pairs]


CONSORT = {
    "schema": 1, "template": "consort-2025", "branches": ["Intervention", "Control"],
    "stages": {
        "assessed": {"n": 120},
        "randomised": {"n": 100, "excluded": reasons(("Not meeting inclusion criteria", 12),
                                                     ("Declined to participate", 6), ("Other reasons", 2))},
        "allocated": {"branches": {
            "Intervention": {"n": 50, "not_received": reasons(("Withdrew before the first session", 2))},
            "Control": {"n": 50, "not_received": []}}},
        "follow_up": {"branches": {
            "Intervention": {"n": 46, "lost": reasons(("Moved away", 4)),
                             "discontinued": reasons(("Adverse event", 1))},
            "Control": {"n": 47, "lost": reasons(("No response", 3)), "discontinued": []}}},
        "analysed": {"basis": "follow_up", "branches": {
            "Intervention": {"n": 45, "excluded": reasons(("Missing baseline measure", 1))},
            "Control": {"n": 47, "excluded": []}}},
    },
}

STROBE = {
    "schema": 1, "template": "strobe",
    "stages": {
        "potentially_eligible": {"n": 500},
        "examined": {"n": 450, "excluded": reasons(("Could not be contacted", 50))},
        "eligible": {"n": 400, "excluded": reasons(("Did not meet the criteria", 50))},
        "included": {"n": 350, "excluded": reasons(("Declined to take part", 50))},
        "followed": {"n": 330, "excluded": reasons(("Lost to follow-up", 20))},
        "analysed": {"n": 320, "excluded": reasons(("Missing exposure data", 10))},
    },
}

STARD = {
    "schema": 1, "template": "stard-2015",
    "stages": {
        "potentially_eligible": {"n": 300},
        "eligible": {"n": 260, "excluded": reasons(("Prior diagnosis", 40))},
        "index_test": {"n": 250, "excluded": reasons(("Sample unusable", 10))},
        "index_result": {"branches": {"positive": {"n": 80}, "negative": {"n": 160},
                                      "inconclusive": {"n": 10}}},
        "reference": {"branches": {
            "positive": {"n": 78, "no_reference": reasons(("Declined biopsy", 2)),
                         "outcome": {"target_present": 70, "target_absent": 6, "inconclusive": 2}},
            "negative": {"n": 150, "no_reference": reasons(("Lost before the reference test", 10)),
                         "outcome": {"target_present": 5, "target_absent": 144, "inconclusive": 1}},
            "inconclusive": {"n": 10, "no_reference": [],
                             "outcome": {"target_present": 3, "target_absent": 6, "inconclusive": 1}}}},
    },
}

FILLED = {"consort-2025": CONSORT, "strobe": STROBE, "stard-2015": STARD}


def counts_and_reasons(flow: dict) -> tuple[set[int], set[str]]:
    """Every count and every reason text a filled flow holds."""
    numbers, texts = set(), set()

    def walk(node) -> None:
        if isinstance(node, dict):
            if "reason" in node:
                texts.add(node["reason"])
            for key, value in node.items():
                if isinstance(value, int) and not isinstance(value, bool) and key != "schema":
                    numbers.add(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(flow["stages"])
    return numbers, texts


class FlowWorkspace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="participant-flow-")
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_cli(self, *args: str) -> tuple[int, dict]:
        proc = subprocess.run([sys.executable, str(CLI), *args, "--root", str(self.root)],
                              capture_output=True, text=True, cwd=str(REPO))
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, f"one JSON object expected, got {proc.stdout!r} / {proc.stderr!r}")
        return proc.returncode, json.loads(lines[0])

    def write_flow(self, flow: dict) -> None:
        path = self.root / "study" / "flow.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(flow, indent=2), encoding="utf-8")

    def problems(self, flow: dict) -> list[dict]:
        self.write_flow(flow)
        code, out = self.run_cli("check")
        if out["valid"]:
            self.assertEqual((code, out["ok"]), (0, True))
        else:
            self.assertEqual((code, out["ok"], out["error"]), (1, False, "FLOW_INVALID"))
        return out["problems"]

    def codes(self, flow: dict) -> set[str]:
        return {problem["code"] for problem in self.problems(flow)}

    @property
    def figure(self) -> Path:
        return self.root / "paper" / "Figures" / "participant-flow.svg"


class TemplateTests(FlowWorkspace):
    def test_each_template_prints_an_empty_flow_with_its_stages_in_order(self) -> None:
        expected = {
            "consort-2025": ["assessed", "randomised", "allocated", "follow_up", "analysed"],
            "strobe": ["potentially_eligible", "examined", "eligible", "included", "followed", "analysed"],
            "stard-2015": ["potentially_eligible", "eligible", "index_test", "index_result", "reference"],
        }
        for template, stages in expected.items():
            with self.subTest(template=template):
                code, out = self.run_cli("template", template)
                self.assertEqual((code, out["ok"]), (0, True))
                self.assertEqual(out["flow"]["template"], template)
                self.assertEqual(list(out["flow"]["stages"]), stages)
                self.assertEqual(out["path"], "study/flow.json")
                self.assertFalse((self.root / "study" / "flow.json").exists(), "template only prints")

    def test_an_empty_template_holds_no_count_and_check_says_every_count_is_missing(self) -> None:
        for template in FILLED:
            with self.subTest(template=template):
                _, out = self.run_cli("template", template)
                self.assertEqual(counts_and_reasons(out["flow"])[0], set())
                self.assertEqual(self.codes(out["flow"]), {"COUNT_MISSING"})

    def test_consort_arms_are_named_by_the_operator(self) -> None:
        _, out = self.run_cli("template", "consort-2025", "--arm", "Exercise", "--arm", "Usual care",
                              "--arm", "Waiting list")
        self.assertEqual(out["flow"]["branches"], ["Exercise", "Usual care", "Waiting list"])
        self.assertEqual(list(out["flow"]["stages"]["allocated"]["branches"]),
                         ["Exercise", "Usual care", "Waiting list"])
        code, out = self.run_cli("template", "stard-2015", "--arm", "A")
        self.assertEqual((code, out["error"]), (1, "ARMS_NOT_APPLICABLE"))

    def test_write_saves_the_template_once_and_never_overwrites(self) -> None:
        code, out = self.run_cli("template", "strobe", "--write")
        self.assertEqual((code, out["ok"]), (0, True))
        saved = json.loads((self.root / "study" / "flow.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, out["flow"])
        code, out = self.run_cli("template", "consort-2025", "--write")
        self.assertEqual((code, out["error"]), (1, "FLOW_EXISTS"))
        self.assertEqual(json.loads((self.root / "study" / "flow.json").read_text())["template"], "strobe")

    def test_an_unknown_template_is_refused(self) -> None:
        code, out = self.run_cli("template", "prisma-2020")
        self.assertEqual((code, out["ok"], out["error"]), (1, False, "TEMPLATE_UNKNOWN"))
        self.assertIn("consort-2025", out["message"])
        flow = copy.deepcopy(STROBE)
        flow["template"] = "prisma-2020"
        self.assertEqual(self.codes(flow), {"TEMPLATE_UNKNOWN"})

    def test_usage_errors_are_typed(self) -> None:
        proc = subprocess.run([sys.executable, str(CLI), "explode"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["error"], "USAGE")


class ArithmeticTests(FlowWorkspace):
    def test_the_filled_flows_of_every_template_are_valid(self) -> None:
        for template, flow in FILLED.items():
            with self.subTest(template=template):
                self.assertEqual(self.problems(flow), [])

    def test_a_stage_must_equal_the_previous_stage_minus_its_exclusions(self) -> None:
        flow = copy.deepcopy(STROBE)
        flow["stages"]["eligible"]["n"] = 401
        problems = self.problems(flow)
        # Each transition is checked against the counts as entered: the next stage no longer follows either.
        self.assertEqual([(p["code"], p["where"]) for p in problems],
                         [("COUNT_MISMATCH", "stages.eligible.n"), ("COUNT_MISMATCH", "stages.included.n")])
        self.assertIn("expected 400", problems[0]["message"])
        flow = copy.deepcopy(CONSORT)
        flow["stages"]["follow_up"]["branches"]["Control"]["lost"][0]["n"] = 2
        self.assertEqual(self.codes(flow), {"COUNT_MISMATCH"})

    def test_the_arms_must_sum_to_the_randomised_total(self) -> None:
        flow = copy.deepcopy(CONSORT)
        flow["stages"]["allocated"]["branches"]["Control"]["n"] = 51
        self.assertIn("BRANCH_SUM_MISMATCH", self.codes(flow))
        flow = copy.deepcopy(STARD)
        flow["stages"]["index_result"]["branches"]["negative"]["n"] = 150
        self.assertIn("BRANCH_SUM_MISMATCH", self.codes(flow))

    def test_analysed_may_not_exceed_followed(self) -> None:
        flow = copy.deepcopy(CONSORT)
        flow["stages"]["analysed"]["branches"]["Control"]["n"] = 48
        problems = self.problems(flow)
        self.assertEqual([p["code"] for p in problems], ["EXCEEDS_PREVIOUS_STAGE"])
        self.assertEqual(problems[0]["where"], "stages.analysed.branches.Control.n")

    def test_an_intention_to_treat_analysis_counts_from_the_allocated_arm(self) -> None:
        flow = copy.deepcopy(CONSORT)
        flow["stages"]["analysed"] = {"basis": "allocated", "branches": {
            "Intervention": {"n": 50, "excluded": []}, "Control": {"n": 50, "excluded": []}}}
        self.assertEqual(self.problems(flow), [])
        flow["stages"]["analysed"]["basis"] = "randomised"
        self.assertEqual(self.codes(flow), {"BASIS_INVALID"})

    def test_counts_must_be_non_negative_integers(self) -> None:
        for bad in (-1, 2.5, "40", True):
            with self.subTest(value=bad):
                flow = copy.deepcopy(STROBE)
                flow["stages"]["eligible"]["excluded"][0]["n"] = bad
                self.assertIn("COUNT_INVALID", self.codes(flow))

    def test_a_note_cannot_count_more_people_than_its_arm(self) -> None:
        flow = copy.deepcopy(CONSORT)
        flow["stages"]["follow_up"]["branches"]["Intervention"]["discontinued"][0]["n"] = 47
        self.assertEqual(self.codes(flow), {"NOTE_EXCEEDS_COUNT"})

    def test_reference_standard_results_must_partition_the_branch(self) -> None:
        flow = copy.deepcopy(STARD)
        flow["stages"]["reference"]["branches"]["positive"]["outcome"]["target_absent"] = 7
        self.assertEqual(self.codes(flow), {"PARTITION_MISMATCH"})
        del flow["stages"]["reference"]["branches"]["positive"]["outcome"]["target_absent"]
        self.assertIn("SCHEMA_INVALID", self.codes(flow))

    def test_each_reason_is_named_once(self) -> None:
        flow = copy.deepcopy(STROBE)
        flow["stages"]["eligible"]["excluded"] = reasons(("", 50))
        self.assertEqual(self.codes(flow), {"REASON_MISSING"})
        flow["stages"]["eligible"]["excluded"] = reasons(("Too young", 25), ("Too young", 25))
        self.assertEqual(self.codes(flow), {"REASON_DUPLICATE"})

    def test_operator_text_holds_no_control_characters(self) -> None:
        flow = copy.deepcopy(STROBE)
        flow["stages"]["eligible"]["excluded"][0]["reason"] = "Did not\x07meet\nthe criteria"
        self.assertEqual(self.codes(flow), {"TEXT_INVALID"})
        flow = copy.deepcopy(CONSORT)
        flow["branches"] = ["Drug\x00", "Control"]
        self.assertEqual(self.codes(flow), {"TEXT_INVALID"})

    def test_the_branches_of_a_split_stage_are_the_declared_arms(self) -> None:
        flow = copy.deepcopy(CONSORT)
        flow["stages"]["follow_up"]["branches"]["Placebo"] = flow["stages"]["follow_up"]["branches"].pop("Control")
        self.assertIn("BRANCH_MISMATCH", self.codes(flow))
        flow = copy.deepcopy(CONSORT)
        flow["branches"] = ["Intervention"]
        self.assertIn("BRANCHES_INVALID", self.codes(flow))

    def test_structure_errors_are_typed(self) -> None:
        flow = copy.deepcopy(STROBE)
        del flow["stages"]["included"]
        self.assertIn("SCHEMA_INVALID", self.codes(flow))
        flow = copy.deepcopy(STROBE)
        flow["stages"]["eligible"]["excludded"] = []
        self.assertIn("SCHEMA_INVALID", self.codes(flow))
        self.assertEqual(self.codes(["not", "an", "object"]), {"SCHEMA_INVALID"})

    def test_strobe_follow_up_is_optional_for_a_cross_sectional_study(self) -> None:
        flow = copy.deepcopy(STROBE)
        del flow["stages"]["followed"]
        flow["stages"]["analysed"]["n"] = 340
        self.assertEqual(self.problems(flow), [])

    def test_check_refuses_without_a_readable_flow(self) -> None:
        code, out = self.run_cli("check")
        self.assertEqual((code, out["error"]), (1, "FLOW_ABSENT"))
        (self.root / "study").mkdir()
        (self.root / "study" / "flow.json").write_text("{not json", encoding="utf-8")
        code, out = self.run_cli("check")
        self.assertEqual((code, out["error"]), (1, "FLOW_UNREADABLE"))


class RenderTests(FlowWorkspace):
    def render(self, flow: dict) -> ET.Element:
        self.write_flow(flow)
        code, out = self.run_cli("render")
        self.assertEqual((code, out["ok"]), (0, True), out)
        self.assertEqual(out["path"], "paper/Figures/participant-flow.svg")
        return ET.fromstring(self.figure.read_bytes())

    def test_every_template_renders_valid_svg_holding_every_count_and_reason(self) -> None:
        for template, flow in FILLED.items():
            with self.subTest(template=template):
                svg = self.render(flow)
                self.assertEqual(svg.tag, f"{SVG_NS}svg")
                text = " ".join("".join(node.itertext()) for node in svg.iter(f"{SVG_NS}text"))
                rows = ["".join(node.itertext()) for node in svg.iter(f"{SVG_NS}text")]
                numbers, texts = counts_and_reasons(flow)
                for number in numbers:  # each count whole on one row, never wrapped apart
                    self.assertTrue(any(f"(n = {number})" in row for row in rows), number)
                for reason in texts:
                    self.assertIn(reason, text)

    def test_operator_text_is_escaped(self) -> None:
        flow = copy.deepcopy(CONSORT)
        flow["branches"] = ["Drug <A> & co", "Control"]
        flow["stages"]["randomised"]["excluded"][2]["reason"] = 'Other "reasons" </text><script>'
        for stage in ("allocated", "follow_up", "analysed"):
            branches = flow["stages"][stage]["branches"]
            branches["Drug <A> & co"] = branches.pop("Intervention")
        svg = self.render(flow)
        raw = self.figure.read_text(encoding="utf-8")
        self.assertNotIn("<script>", raw)
        self.assertEqual(list(svg.iter("script")) + list(svg.iter(f"{SVG_NS}script")), [])
        text = " ".join("".join(node.itertext()) for node in svg.iter(f"{SVG_NS}text"))
        self.assertIn('Other "reasons" </text><script>', text)
        self.assertIn("Drug <A> & co", text)

    def test_rendering_is_deterministic(self) -> None:
        self.render(STARD)
        first = self.figure.read_bytes()
        self.render(STARD)
        self.assertEqual(self.figure.read_bytes(), first)

    def test_print_readability(self) -> None:
        svg = self.render(CONSORT)
        sizes = {float(node.get("font-size")) for node in svg.iter(f"{SVG_NS}text")}
        self.assertGreaterEqual(min(sizes), 11)
        self.assertEqual(svg.get("viewBox").split()[:2], ["0", "0"])
        self.assertIsNotNone(svg.find(f"{SVG_NS}title"))

    def test_invalid_counts_are_never_rendered(self) -> None:
        flow = copy.deepcopy(STROBE)
        flow["stages"]["eligible"]["n"] = 401
        self.write_flow(flow)
        code, out = self.run_cli("render")
        self.assertEqual((code, out["error"]), (1, "FLOW_INVALID"))
        self.assertEqual(out["problems"][0]["code"], "COUNT_MISMATCH")
        self.assertFalse(self.figure.exists())


class SignoffTests(FlowWorkspace):
    def signed(self, flow: dict) -> dict:
        self.write_flow(flow)
        self.assertEqual(self.run_cli("render")[0], 0)
        code, out = self.run_cli("signoff", "--by", "Dr. Operator", "--note", "counts from the trial log")
        self.assertEqual((code, out["ok"]), (0, True), out)
        return out

    def test_signoff_requires_the_operator(self) -> None:
        self.write_flow(STROBE)
        self.run_cli("render")
        for args in ((), ("--by", "  ")):
            with self.subTest(args=args):
                code, out = self.run_cli("signoff", *args)
                self.assertEqual((code, out["error"]), (1, "OPERATOR_ABSENT"))
        self.assertFalse((self.root / "study" / "flow-signoffs.json").exists())

    def test_signoff_records_the_hash_and_status_reports_it_current(self) -> None:
        out = self.signed(CONSORT)
        self.assertEqual(out["signoff"]["by"], "Dr. Operator")
        self.assertEqual(out["signoff"]["note"], "counts from the trial log")
        self.assertEqual(len(out["signoff"]["sha256"]), 64)
        self.assertTrue(out["signoff"]["current"])
        code, status = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertEqual((status["flow"], status["template"], status["figure"]), ("valid", "consort-2025", "current"))
        self.assertTrue(status["signoff"]["current"])

    def test_an_unchanged_state_is_not_signed_twice(self) -> None:
        self.signed(STROBE)
        code, out = self.run_cli("signoff", "--by", "Dr. Operator")
        self.assertEqual((code, out["error"]), (1, "SIGNOFF_UNCHANGED"))

    def test_a_count_edit_makes_the_signoff_stale_until_signed_again(self) -> None:
        self.signed(STROBE)
        flow = copy.deepcopy(STROBE)
        flow["stages"]["analysed"]["n"] = 325
        flow["stages"]["analysed"]["excluded"][0]["n"] = 5
        self.write_flow(flow)
        _, status = self.run_cli("status")
        self.assertEqual((status["flow"], status["figure"]), ("valid", "stale"))
        self.assertFalse(status["signoff"]["current"])
        code, out = self.run_cli("signoff", "--by", "Dr. Operator")
        self.assertEqual((code, out["error"]), (1, "FIGURE_STALE"))
        self.assertEqual(self.run_cli("render")[0], 0)
        _, status = self.run_cli("status")
        self.assertFalse(status["signoff"]["current"])
        code, out = self.run_cli("signoff", "--by", "Second Operator")
        self.assertEqual(code, 0)
        record = json.loads((self.root / "study" / "flow-signoffs.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["by"] for entry in record["signoffs"]], ["Dr. Operator", "Second Operator"])

    def test_timestamps_in_the_flow_do_not_change_the_signed_state(self) -> None:
        self.signed(STARD)
        flow = copy.deepcopy(STARD)
        flow["updated_at"] = "2026-11-22T10:00:00Z"
        self.write_flow(flow)
        _, status = self.run_cli("status")
        self.assertEqual((status["flow"], status["figure"]), ("valid", "current"))
        self.assertTrue(status["signoff"]["current"])

    def test_signoff_refuses_invalid_counts_and_a_missing_figure(self) -> None:
        self.write_flow(STROBE)
        code, out = self.run_cli("signoff", "--by", "Dr. Operator")
        self.assertEqual((code, out["error"]), (1, "FIGURE_ABSENT"))
        flow = copy.deepcopy(STROBE)
        flow["stages"]["eligible"]["n"] = 401
        self.write_flow(flow)
        code, out = self.run_cli("signoff", "--by", "Dr. Operator")
        self.assertEqual((code, out["error"]), (1, "FLOW_INVALID"))
        self.assertFalse((self.root / "study" / "flow-signoffs.json").exists())

    def test_a_hand_edited_figure_is_stale(self) -> None:
        self.signed(CONSORT)
        self.figure.write_text(self.figure.read_text(encoding="utf-8").replace("n = 120", "n = 130"),
                               encoding="utf-8")
        _, status = self.run_cli("status")
        self.assertEqual(status["figure"], "stale")
        self.assertFalse(status["signoff"]["current"])

    def test_status_of_an_empty_workspace(self) -> None:
        code, status = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertEqual((status["flow"], status["figure"], status["signoff"]), ("absent", "absent", None))
        self.write_flow({"schema": 1, "template": "strobe", "stages": {}})
        _, status = self.run_cli("status")
        self.assertEqual(status["flow"], "invalid")
        self.assertGreater(status["problems"], 0)


if __name__ == "__main__":
    unittest.main()
