"""The final judge's rubric per paper line (paper-type-lines S6, T6d).

A round declares its rubric: `ml-conference` (the default when `rubric` is
absent, the main-track form of a machine-learning conference) or
`systematic-review` (AMSTAR 2, Shea et al., 2017, BMJ 358:j4008, plus the
PRISMA 2020 reporting gaps, Page et al., 2021, BMJ 372:n71). For the
systematic-review rubric `paper_cli.py review` derives the overall confidence
from the AMSTAR 2 answers itself; an asserted rating that disagrees with the
rule is refused. A refused round leaves `.papersmith/paper_review.json` byte
for byte as it was.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import server

FORGE_ROOT = Path(__file__).resolve().parents[1]
CLI = FORGE_ROOT / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
STATIC = Path(server.__file__).resolve().parent / "static"

CRITICAL = (2, 4, 7, 9, 11, 13, 15)


def ml_round(**overrides) -> dict:
    data = {
        "overall": 4, "confidence": 3, "recommendation": "Borderline accept",
        "ratings": {"Quality": 3, "Clarity": 2, "Significance": 3, "Originality": 3},
        "revisions": [{"rank": 1, "text": "Report variance across the five seeds.", "note": None}],
        "excluded": ["Appendix C"],
        "report": "Summary: ... (full review form)",
    }
    data.update(overrides)
    return data


def amstar(no=(), partial=(), na=()) -> list[dict]:
    def answer(item: int) -> str:
        if item in no:
            return "no"
        if item in partial:
            return "partial yes"
        if item in na:
            return "not applicable"
        return "yes"
    return [{"item": i, "answer": answer(i), "justification": f"Methods section, item {i}."} for i in range(1, 17)]


def review_round(**overrides) -> dict:
    data = {
        "rubric": "systematic-review",
        "recommendation": "Major revision",
        "amstar2": amstar(),
        "prisma_gaps": [{"item": 24, "gap": "The registration number is not given."}],
        "revisions": [{"rank": 1, "text": "State the protocol registration."}],
        "report": "AMSTAR 2 appraisal and PRISMA 2020 reporting check: ...",
    }
    data.update(overrides)
    return data


DOMAINS = ("selection", "measurement", "confounding", "missing data", "reporting")


def bias(**ratings) -> list[dict]:
    """One risk-of-bias judgement per domain, `low` unless named (spaces as `_`)."""
    return [{"domain": d, "rating": ratings.get(d.replace(" ", "_"), "low"),
             "justification": f"Methods, {d}."} for d in DOMAINS]


def empirical_round(**overrides) -> dict:
    data = {
        "rubric": "empirical-study",
        "recommendation": "Minor revision",
        "protocol_adherence": {
            "primary_outcome": "followed", "analysis_plan": "deviated",
            "deviations": [{"deviation": "Covariate age added to the primary model.", "declared": True},
                           {"deviation": "Per-protocol analysis reported first.", "declared": False}],
            "justification": "Methods 2.4 against protocol v02.",
        },
        "design_validity": {"rating": "adequate", "justification": "A cross-sectional design answers the question."},
        "risk_of_bias": bias(),
        "checklist": "STROBE",
        "checklist_gaps": [{"item": "12b", "gap": "Subgroup methods not described."}, {"item": 19, "gap": "x"}],
        "revisions": [{"rank": 1, "text": "Declare the covariate change as an amendment."}],
        "report": "Empirical-study appraisal: ...",
    }
    data.update(overrides)
    return data


class RubricRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        # `paper_cli.py` refuses a paper outside the repository, so the workspace
        # lives under the git-ignored `.scratch/` and is removed after the test.
        scratch = FORGE_ROOT / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix=".paper-review-rubric-", dir=scratch))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.paper_dir.mkdir(parents=True)
        self.file = self.root / ".papersmith" / "paper_review.json"

    def set_line(self, line: str) -> None:
        """Write the workspace's `paper_kind`, the line `record` checks the rubric against."""
        config = self.root / ".papersmith" / "config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"paper_kind": line}), encoding="utf-8")

    def record(self, payload) -> tuple[int, dict]:
        source = self.root / f"round-{uuid.uuid4().hex[:6]}.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(CLI), "review", "--paper", str(self.paper_dir), "--input", str(source)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.stderr, "")
        return proc.returncode, json.loads(proc.stdout)

    def rounds(self) -> list:
        return json.loads(self.file.read_text(encoding="utf-8"))["rounds"]

    def assertRefusedUnchanged(self, payload, fragment: str, code: str = "REVIEW_ROUND_INVALID") -> None:
        before = self.file.read_bytes() if self.file.exists() else None
        rc, out = self.record(payload)
        self.assertEqual((rc, out["status"], out["code"]), (2, "refused", code), out)
        self.assertIn(fragment, out["detail"])
        after = self.file.read_bytes() if self.file.exists() else None
        self.assertEqual(before, after)

    # --- the default rubric is today's, byte for byte -------------------------

    def test_a_round_without_a_rubric_is_stored_exactly_as_before(self) -> None:
        code, out = self.record(ml_round())
        self.assertEqual((code, out["status"], out["round"], out["pending_revisions"]), (0, "ok", 1, 1))
        entry = self.rounds()[0]
        date = entry["date"]
        self.assertEqual(entry, {
            "round": 1, "date": date, "overall": 4, "confidence": 3, "recommendation": "Borderline accept",
            "ratings": {"Quality": 3, "Clarity": 2, "Significance": 3, "Originality": 3},
            "items": [],
            "revisions": [{"rank": 1, "text": "Report variance across the five seeds.", "status": "pending",
                           "note": ""}],
            "excluded": ["Appendix C"], "report": "Summary: ... (full review form)",
        })
        self.assertEqual(list(entry), ["round", "date", "overall", "confidence", "recommendation", "ratings",
                                       "items", "revisions", "excluded", "report"])

    def test_the_ml_conference_rubric_named_explicitly_is_the_default(self) -> None:
        self.record(ml_round(rubric="ml-conference"))
        self.assertNotIn("rubric", self.rounds()[0])
        self.assertRefusedUnchanged(ml_round(rubric="ml-conference", ratings={"Quality": 3}),
                                    "ratings must hold exactly")

    def test_an_unknown_rubric_is_refused(self) -> None:
        self.assertRefusedUnchanged(ml_round(rubric="neurips"), "rubric must be one of ml-conference, systematic-review")

    # --- the systematic-review rubric -----------------------------------------

    def test_a_review_round_is_stored_with_its_derived_confidence(self) -> None:
        self.set_line("review")
        code, out = self.record(review_round(amstar2=amstar(partial=(2, 8), na=(11, 12, 15))))
        self.assertEqual((code, out["status"], out["round"]), (0, "ok", 1))
        entry = self.rounds()[0]
        self.assertEqual(entry["rubric"], "systematic-review")
        self.assertEqual(entry["overall_confidence"], "high")
        self.assertEqual((entry["critical_flaws"], entry["non_critical_weaknesses"]), ([], []))
        self.assertEqual([a["item"] for a in entry["amstar2"]], list(range(1, 17)))
        self.assertEqual([a["item"] for a in entry["amstar2"] if a["critical"]], list(CRITICAL))
        self.assertEqual(entry["amstar2"][1]["answer"], "partial yes")
        self.assertEqual(entry["prisma_gaps"], [{"item": 24, "gap": "The registration number is not given."}])
        self.assertEqual(entry["revisions"][0]["status"], "pending")
        for absent in ("overall", "confidence", "ratings"):
            self.assertNotIn(absent, entry)

    def test_the_overall_confidence_follows_the_amstar2_rule(self) -> None:
        self.set_line("review")
        cases = [
            ((), "high"),
            ((1,), "high"),
            ((1, 3), "moderate"),
            ((4,), "low"),
            ((4, 1, 3, 5), "low"),
            ((4, 9), "critically low"),
        ]
        for no, expected in cases:
            with self.subTest(no=no):
                self.file.unlink(missing_ok=True)
                code, _ = self.record(review_round(amstar2=amstar(no=no)))
                entry = self.rounds()[0]
                self.assertEqual((code, entry["overall_confidence"]), (0, expected))
                self.assertEqual(entry["critical_flaws"], sorted(i for i in no if i in CRITICAL))
                self.assertEqual(entry["non_critical_weaknesses"], sorted(i for i in no if i not in CRITICAL))

    def test_an_asserted_confidence_must_match_the_rule(self) -> None:
        self.set_line("review")
        self.assertRefusedUnchanged(review_round(amstar2=amstar(no=(7,)), overall_confidence="high"),
                                    'overall_confidence "high" does not match the AMSTAR 2 rule: low')
        code, _ = self.record(review_round(amstar2=amstar(no=(7,)), overall_confidence="low"))
        self.assertEqual(code, 0)

    def test_every_amstar2_item_needs_one_answer_with_a_justification(self) -> None:
        self.set_line("review")
        missing = amstar()[:-1]
        self.assertRefusedUnchanged(review_round(amstar2=missing), "amstar2 must answer each item 1-16 once")
        twice = amstar() + [{"item": 3, "answer": "yes", "justification": "again"}]
        self.assertRefusedUnchanged(review_round(amstar2=twice), "amstar2 must answer each item 1-16 once")
        bad = amstar()
        bad[0]["answer"] = "maybe"
        self.assertRefusedUnchanged(review_round(amstar2=bad), "amstar2 item 1 answer must be one of")
        blank = amstar()
        blank[4]["justification"] = " "
        self.assertRefusedUnchanged(review_round(amstar2=blank), "amstar2 item 5 needs a non-empty justification")
        self.assertRefusedUnchanged(review_round(amstar2=None), "amstar2 must answer each item 1-16 once")

    def test_partial_yes_and_not_applicable_only_where_amstar2_offers_them(self) -> None:
        self.set_line("review")
        self.assertRefusedUnchanged(review_round(amstar2=amstar(partial=(1,))),
                                    'amstar2 item 1 cannot be "partial yes"')
        self.assertRefusedUnchanged(review_round(amstar2=amstar(na=(9,))),
                                    'amstar2 item 9 cannot be "not applicable"')

    # --- AMSTAR 2 items 9 and 13 in a review that appraises no risk of bias (L59 a) --

    def set_protocol(self, review_type) -> None:
        """Write `review/protocol.json` with this `review_type` (the systematic-review skill's file)."""
        protocol = self.root / "review" / "protocol.json"
        protocol.parent.mkdir(parents=True, exist_ok=True)
        protocol.write_text(json.dumps({"title": "t", "review_type": review_type}), encoding="utf-8")

    def test_items_9_and_13_may_be_not_applicable_in_a_scoping_or_bibliometric_review(self) -> None:
        self.set_line("review")
        for review_type in ("scoping review", "Bibliometric analysis", "systematic scoping review"):
            with self.subTest(review_type=review_type):
                self.file.unlink(missing_ok=True)
                self.set_protocol(review_type)
                code, out = self.record(review_round(amstar2=amstar(na=(9, 11, 12, 13, 15))))
                self.assertEqual((code, out["status"]), (0, "ok"), out)
                entry = self.rounds()[0]
                self.assertEqual(entry["overall_confidence"], "high")
                self.assertEqual((entry["critical_flaws"], entry["non_critical_weaknesses"]), ([], []))
                self.assertEqual([a["answer"] for a in entry["amstar2"] if a["item"] in (9, 13)],
                                 ["not applicable", "not applicable"])
                self.assertEqual(entry["amstar2_basis"],
                                 {"protocol": "review/protocol.json", "review_type": review_type,
                                  "risk_of_bias_not_applicable": True})
        self.file.unlink()
        code, _ = self.record(review_round(amstar2=amstar(no=(4, 1), na=(9, 13))))
        entry = self.rounds()[0]
        self.assertEqual((code, entry["overall_confidence"]), (0, "low"))
        self.assertEqual((entry["critical_flaws"], entry["non_critical_weaknesses"]), ([4], [1]))

    def test_items_9_and_13_stay_applicable_in_any_other_review(self) -> None:
        self.set_line("review")
        for review_type in ("systematic review", "meta-analysis", None, 7):
            with self.subTest(review_type=review_type):
                self.set_protocol(review_type)
                self.assertRefusedUnchanged(review_round(amstar2=amstar(na=(9,))),
                                            'amstar2 item 9 cannot be "not applicable"')
                self.assertRefusedUnchanged(review_round(amstar2=amstar(na=(13,))),
                                            'amstar2 item 13 cannot be "not applicable"')
        (self.root / "review" / "protocol.json").write_text("{not json", encoding="utf-8")
        self.assertRefusedUnchanged(review_round(amstar2=amstar(na=(9,))), 'amstar2 item 9 cannot be "not applicable"')
        (self.root / "review" / "protocol.json").unlink()
        self.assertRefusedUnchanged(review_round(amstar2=amstar(na=(13,))),
                                    'amstar2 item 13 cannot be "not applicable"')
        code, _ = self.record(review_round())
        self.assertEqual(code, 0)
        self.assertEqual(self.rounds()[0]["amstar2_basis"],
                         {"protocol": "review/protocol.json", "review_type": None,
                          "risk_of_bias_not_applicable": False})
        self.set_protocol("systematic review")
        code, _ = self.record(review_round(items=[{"rank": 1, "verdict": "resolved"}], revisions=[]))
        self.assertEqual(code, 0)
        self.assertEqual(self.rounds()[1]["amstar2_basis"]["review_type"], "systematic review")
        self.assertFalse(self.rounds()[1]["amstar2_basis"]["risk_of_bias_not_applicable"])

    def test_a_scoping_protocol_changes_no_other_rubric(self) -> None:
        self.set_protocol("scoping review")
        self.record(ml_round())
        self.assertNotIn("amstar2_basis", self.rounds()[0])
        self.set_line("observational-measurement")
        self.file.unlink()
        self.record(empirical_round())
        self.assertNotIn("amstar2_basis", self.rounds()[0])

    def test_prisma_gaps_name_a_prisma_2020_item(self) -> None:
        self.set_line("review")
        self.assertRefusedUnchanged(review_round(prisma_gaps=[{"item": 28, "gap": "x"}]),
                                    "prisma_gaps[1] needs an item 1-27 and non-empty gap text")
        self.assertRefusedUnchanged(review_round(prisma_gaps="none"), "prisma_gaps must be a list")
        code, _ = self.record(review_round(prisma_gaps=[]))
        self.assertEqual(code, 0)

    def test_the_shared_fields_still_apply_to_a_review_round(self) -> None:
        self.set_line("review")
        self.assertRefusedUnchanged(review_round(report=""), "report must be non-empty text")
        self.assertRefusedUnchanged(review_round(recommendation=""), "recommendation must be non-empty text")

    def test_a_second_review_round_judges_the_previous_revisions(self) -> None:
        self.set_line("review")
        self.record(review_round())
        self.assertRefusedUnchanged(review_round(), "[1]", code="REVIEW_ITEMS_MISSING")
        code, out = self.record(review_round(items=[{"rank": 1, "verdict": "resolved", "evidence": "PROSPERO id."}],
                                             revisions=[]))
        self.assertEqual((code, out["round"]), (0, 2))
        self.assertEqual(self.rounds()[1]["items"][0]["item"], "State the protocol registration.")

    def test_the_dashboard_reads_a_review_round_unchanged(self) -> None:
        self.record(ml_round())
        self.set_line("review")
        self.record(review_round(amstar2=amstar(no=(4,)),
                                 items=[{"rank": 1, "verdict": "partly", "evidence": "Seeds listed."}]))
        state = TestClient(server.create_app(self.root)).get("/api/paper/review").json()
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["rounds"], self.rounds())


    # --- the rubric must serve the workspace's line (D15) ---------------------

    def test_a_rubric_that_does_not_serve_the_line_is_refused(self) -> None:
        self.assertRefusedUnchanged(review_round(), 'rubric "systematic-review" does not serve the line "experimental"',
                                    code="RUBRIC_KIND_MISMATCH")
        self.assertRefusedUnchanged(empirical_round(), 'the line\'s rubric is "ml-conference"',
                                    code="RUBRIC_KIND_MISMATCH")
        self.set_line("review")
        self.assertRefusedUnchanged(ml_round(rubric="ml-conference"), 'the line\'s rubric is "systematic-review"',
                                    code="RUBRIC_KIND_MISMATCH")
        self.set_line("observational-measurement")
        self.assertRefusedUnchanged(ml_round(rubric="ml-conference"), 'the line\'s rubric is "empirical-study"',
                                    code="RUBRIC_KIND_MISMATCH")

    def test_an_unknown_rubric_is_refused_before_the_line_is_checked(self) -> None:
        self.set_line("review")
        self.assertRefusedUnchanged(ml_round(rubric="neurips"),
                                    "rubric must be one of ml-conference, systematic-review, empirical-study")

    def test_a_line_no_rubric_serves_is_refused(self) -> None:
        self.set_line("poetry")
        self.assertRefusedUnchanged(ml_round(), 'no rubric serves the line "poetry"', code="RUBRIC_LINE_UNKNOWN")

    def test_a_round_without_a_rubric_takes_its_lines_rubric(self) -> None:
        self.set_line("experimental")
        self.record(ml_round())
        self.assertNotIn("rubric", self.rounds()[0])
        self.file.unlink()
        self.set_line("review")
        data = review_round()
        del data["rubric"]
        code, _ = self.record(data)
        self.assertEqual((code, self.rounds()[0]["rubric"]), (0, "systematic-review"))
        self.file.unlink()
        self.assertRefusedUnchanged(ml_round(), "amstar2 must answer each item 1-16 once")
        self.set_line("hardware")
        data = empirical_round()
        del data["rubric"]
        code, _ = self.record(data)
        self.assertEqual((code, self.rounds()[0]["rubric"]), (0, "empirical-study"))

    def test_an_unreadable_config_is_the_experimental_line(self) -> None:
        config = self.root / ".papersmith" / "config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("{not json", encoding="utf-8")
        code, _ = self.record(ml_round())
        self.assertEqual(code, 0)
        self.assertNotIn("rubric", self.rounds()[0])

    def test_the_registry_maps_each_line_to_one_rubric_by_data(self) -> None:
        review = load_paper_review()
        self.assertEqual(list(review.RUBRICS), ["ml-conference", "systematic-review", "empirical-study"])
        self.assertEqual(review.RUBRICS["ml-conference"].lines, ("experimental",))
        self.assertEqual(review.RUBRICS["systematic-review"].lines, ("review",))
        self.assertEqual(review.RUBRICS["empirical-study"].lines,
                         ("observational-measurement", "experiment-intervention", "qualitative-participatory",
                          "hardware", "lab-simulation", "data-resource"))
        for rubric_id, rubric in review.RUBRICS.items():
            for line in rubric.lines:
                self.assertEqual(review.rubric_for_line(line), rubric_id)
        self.assertIsNone(review.rubric_for_line("poetry"))

    # --- the empirical-study rubric -------------------------------------------

    def test_an_empirical_round_is_stored_with_its_derived_risk_of_bias(self) -> None:
        self.set_line("observational-measurement")
        shuffled = list(reversed(bias(confounding="some concerns")))
        code, out = self.record(empirical_round(risk_of_bias=shuffled))
        self.assertEqual((code, out["status"], out["round"], out["pending_revisions"]), (0, "ok", 1, 1))
        entry = self.rounds()[0]
        self.assertEqual(list(entry), ["round", "date", "rubric", "recommendation", "protocol_adherence",
                                       "design_validity", "risk_of_bias", "overall_risk_of_bias", "checklist",
                                       "checklist_gaps", "items", "revisions", "excluded", "report"])
        self.assertEqual(entry["rubric"], "empirical-study")
        self.assertEqual(entry["protocol_adherence"], {
            "primary_outcome": "followed", "analysis_plan": "deviated",
            "deviations": [{"deviation": "Covariate age added to the primary model.", "declared": True},
                           {"deviation": "Per-protocol analysis reported first.", "declared": False}],
            "undeclared_deviations": 1, "justification": "Methods 2.4 against protocol v02.",
        })
        self.assertEqual(entry["design_validity"],
                         {"rating": "adequate", "justification": "A cross-sectional design answers the question."})
        self.assertEqual([d["domain"] for d in entry["risk_of_bias"]], list(DOMAINS))
        self.assertEqual(entry["risk_of_bias"][2], {"domain": "confounding", "rating": "some concerns",
                                                    "justification": "Methods, confounding."})
        self.assertEqual(entry["overall_risk_of_bias"], "some concerns")
        self.assertEqual(entry["checklist"], "STROBE")
        self.assertEqual(entry["checklist_gaps"], [{"item": "12b", "gap": "Subgroup methods not described."},
                                                   {"item": 19, "gap": "x"}])
        for absent in ("overall", "confidence", "ratings", "amstar2"):
            self.assertNotIn(absent, entry)

    def test_the_overall_risk_of_bias_follows_the_stated_rule(self) -> None:
        self.set_line("observational-measurement")
        cases = [
            ({}, "low"),
            ({"reporting": "some concerns"}, "some concerns"),
            ({"selection": "some concerns", "missing_data": "some concerns"}, "some concerns"),
            ({"measurement": "high"}, "high"),
            ({"measurement": "high", "selection": "some concerns"}, "high"),
        ]
        for ratings, expected in cases:
            with self.subTest(ratings=ratings):
                self.file.unlink(missing_ok=True)
                code, _ = self.record(empirical_round(risk_of_bias=bias(**ratings)))
                self.assertEqual((code, self.rounds()[0]["overall_risk_of_bias"]), (0, expected))

    def test_an_asserted_overall_risk_must_match_the_rule(self) -> None:
        self.set_line("observational-measurement")
        self.assertRefusedUnchanged(empirical_round(risk_of_bias=bias(confounding="high"), overall_risk_of_bias="low"),
                                    'overall_risk_of_bias "low" does not match the rule: high')
        code, _ = self.record(empirical_round(risk_of_bias=bias(confounding="high"), overall_risk_of_bias="high"))
        self.assertEqual(code, 0)

    def test_every_bias_domain_needs_one_rating_with_a_justification(self) -> None:
        self.set_line("observational-measurement")
        names = "selection, measurement, confounding, missing data, reporting"
        self.assertRefusedUnchanged(empirical_round(risk_of_bias=bias()[:-1]),
                                    f"risk_of_bias must rate each domain once: {names}")
        self.assertRefusedUnchanged(empirical_round(risk_of_bias=bias() + bias()[:1]),
                                    f"risk_of_bias must rate each domain once: {names}")
        self.assertRefusedUnchanged(empirical_round(risk_of_bias=None), "risk_of_bias must rate each domain once")
        bad = bias()
        bad[1]["rating"] = "moderate"
        self.assertRefusedUnchanged(empirical_round(risk_of_bias=bad),
                                    "risk_of_bias measurement rating must be one of low, some concerns, high")
        blank = bias()
        blank[3]["justification"] = " "
        self.assertRefusedUnchanged(empirical_round(risk_of_bias=blank),
                                    "risk_of_bias missing data needs a non-empty justification")

    def test_protocol_adherence_and_design_validity_are_validated(self) -> None:
        self.set_line("observational-measurement")
        adherence = empirical_round()["protocol_adherence"]
        self.assertRefusedUnchanged(empirical_round(protocol_adherence=None), "protocol_adherence must be an object")
        self.assertRefusedUnchanged(empirical_round(protocol_adherence={**adherence, "primary_outcome": "mostly"}),
                                    "protocol_adherence.primary_outcome must be one of followed, deviated, no protocol")
        self.assertRefusedUnchanged(empirical_round(protocol_adherence={**adherence, "deviations": []}),
                                    "protocol_adherence lists no deviation although analysis_plan is deviated")
        self.assertRefusedUnchanged(
            empirical_round(protocol_adherence={**adherence, "deviations": [{"deviation": "x", "declared": "yes"}]}),
            "protocol_adherence.deviations[1] needs non-empty deviation text and declared true or false")
        self.assertRefusedUnchanged(empirical_round(protocol_adherence={**adherence, "justification": ""}),
                                    "protocol_adherence needs a non-empty justification")
        self.assertRefusedUnchanged(empirical_round(design_validity={"rating": "fine", "justification": "x"}),
                                    "design_validity.rating must be one of adequate, limited, inadequate")
        self.assertRefusedUnchanged(empirical_round(design_validity={"rating": "limited"}),
                                    "design_validity needs a non-empty justification")

    def test_checklist_gaps_name_an_item_of_the_lines_checklist(self) -> None:
        self.set_line("observational-measurement")
        self.assertRefusedUnchanged(empirical_round(checklist_gaps=[{"item": "a12", "gap": "x"}]),
                                    "checklist_gaps[1] needs an item number (e.g. 12 or 12b) and non-empty gap text")
        self.assertRefusedUnchanged(empirical_round(checklist_gaps=[{"item": 0, "gap": "x"}]),
                                    "checklist_gaps[1] needs an item number")
        self.assertRefusedUnchanged(empirical_round(checklist_gaps="none"), "checklist_gaps must be a list")
        self.assertRefusedUnchanged(empirical_round(checklist=""),
                                    "checklist must name the reporting checklist the gaps refer to")
        data = empirical_round(checklist_gaps=[])
        del data["checklist"]
        code, _ = self.record(data)
        self.assertEqual((code, self.rounds()[0]["checklist"], self.rounds()[0]["checklist_gaps"]), (0, "", []))

    def test_the_shared_fields_still_apply_to_an_empirical_round(self) -> None:
        self.set_line("observational-measurement")
        self.assertRefusedUnchanged(empirical_round(report=""), "report must be non-empty text")
        self.assertRefusedUnchanged(empirical_round(recommendation=""), "recommendation must be non-empty text")
        self.record(empirical_round())
        self.assertRefusedUnchanged(empirical_round(), "[1]", code="REVIEW_ITEMS_MISSING")
        code, out = self.record(empirical_round(items=[{"rank": 1, "verdict": "partly", "evidence": "Amendment 1."}],
                                                revisions=[]))
        self.assertEqual((code, out["round"]), (0, 2))
        self.assertEqual(self.rounds()[1]["items"][0]["item"], "Declare the covariate change as an amendment.")


HARNESS = r"""
const fs = require('fs');
const els = {};
global.window = {};
global.document = {
  readyState: 'complete', getElementById: (id) => els[id] || (els[id] = { id, innerHTML: '' }),
  addEventListener: () => {},
};
global.fetch = async () => ({ json: async () => ({ status: 'ok', rounds: [] }) });
for (const file of process.argv.slice(1)) eval(fs.readFileSync(file, 'utf8'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
console.log(JSON.stringify({ html: window.PaperReviewPanel.render(input) }));
"""


def load_paper_review():
    """`paper_review.py` in process, for its registry (the CLI covers its behaviour)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "paper_review_under_test", FORGE_ROOT / "skills" / "paper-writing" / "scripts" / "paper_review.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


def render(state: dict) -> str:
    done = subprocess.run(["node", "-e", HARNESS, str(STATIC / "paper-review-panel.js")], capture_output=True,
                          text=True, check=True, input=json.dumps(state), cwd=tempfile.gettempdir())
    return json.loads(done.stdout)["html"]


def node_works() -> bool:
    if not shutil.which("node"):
        return False
    try:
        return subprocess.run(["node", "-e", "0"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@unittest.skipUnless(node_works(), "node is not installed or does not run")
class RubricPanelTests(unittest.TestCase):
    """The panel renders either rubric; keys show bare where i18n is not loaded."""

    def test_an_ml_conference_round_renders_its_scores(self) -> None:
        html = render({"status": "ok", "rounds": [{"round": 1, "overall": 4, "confidence": 3,
                                                    "recommendation": "Borderline accept",
                                                    "ratings": {"Quality": 3}, "report": "r"}]})
        self.assertIn("review.overall 4/6", html)
        self.assertIn("review.confidence 3/5", html)
        self.assertIn("Quality 3/4", html)
        self.assertNotIn("review.amstar2", html)

    def test_a_review_round_renders_amstar2_and_the_prisma_gaps_escaped(self) -> None:
        entry = {"round": 1, "rubric": "systematic-review", "recommendation": "Major revision",
                 "overall_confidence": "low", "critical_flaws": [4], "non_critical_weaknesses": [],
                 "amstar2": [{"item": 4, "critical": True, "answer": "no",
                              "justification": "<script>alert(1)</script>"}],
                 "prisma_gaps": [{"item": 24, "gap": "No registration."}], "report": "r"}
        html = render({"status": "ok", "rounds": [entry]})
        self.assertIn("review.amstar2.confidence", html)
        self.assertIn("review.amstar2.level.low", html)
        self.assertIn("review.amstar2.critical", html)
        self.assertIn("No registration.", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("/6", html)


    def test_an_empirical_round_renders_its_risk_of_bias_escaped(self) -> None:
        entry = {"round": 2, "rubric": "empirical-study", "recommendation": "Minor revision",
                 "protocol_adherence": {"primary_outcome": "followed", "analysis_plan": "deviated",
                                        "deviations": [{"deviation": "<b>age</b> added", "declared": False}],
                                        "undeclared_deviations": 1, "justification": "Methods 2.4."},
                 "design_validity": {"rating": "limited", "justification": "Single site."},
                 "risk_of_bias": [{"domain": "missing data", "rating": "high", "justification": "<i>30%</i> lost"}],
                 "overall_risk_of_bias": "high", "checklist": "STROBE",
                 "checklist_gaps": [{"item": "12b", "gap": "Subgroups."}], "report": "r"}
        html = render({"status": "ok", "rounds": [entry]})
        for fragment in ("review.rubric.empirical", "review.empirical.overall", "review.empirical.level.high",
                         "review.empirical.domain.missing_data", "review.empirical.adherence.deviated",
                         "review.empirical.design.limited", "review.empirical.undeclared", "STROBE", "12b",
                         "Subgroups.", "&lt;b&gt;age&lt;/b&gt;", "&lt;i&gt;30%&lt;/i&gt;"):
            self.assertIn(fragment, html)
        self.assertNotIn("<b>age", html)
        self.assertNotIn("/6", html)
        self.assertNotIn("review.amstar2", html)
        older = render({"status": "ok", "rounds": [entry, {**entry, "round": 3}]})
        self.assertIn("review.empirical.level.high · Minor revision", older)

    def test_the_ml_and_review_renderings_are_unchanged(self) -> None:
        ml = {"round": 1, "date": "2026-01-01", "overall": 4, "confidence": 3, "recommendation": "Accept",
              "ratings": {"Quality": 3}, "items": [{"item": "x", "verdict": "resolved", "evidence": "e"}],
              "revisions": [{"rank": 1, "text": "t", "status": "pending", "note": ""}],
              "excluded": ["A"], "report": "r"}
        review = {"round": 2, "rubric": "systematic-review", "recommendation": "Major revision",
                  "overall_confidence": "low", "critical_flaws": [4], "non_critical_weaknesses": [],
                  "amstar2": [{"item": 4, "critical": True, "answer": "no", "justification": "j"}],
                  "prisma_gaps": [{"item": 24, "gap": "g"}], "report": "r"}
        html = render({"status": "ok", "rounds": [ml, review]})
        self.assertIn("review.overall 4/6", html)
        self.assertIn("review.amstar2.level.low", html)
        self.assertNotIn("review.empirical", html)

if __name__ == "__main__":
    unittest.main()
