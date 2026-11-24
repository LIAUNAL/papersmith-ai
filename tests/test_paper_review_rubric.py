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


CRITERIA = ("design_validity", "calibration_traceability", "uncertainty", "reproducibility", "agreement")


def criterion(rating: str = "adequate", why: str = "Section 4 and the calibration certificate.") -> dict:
    return {"rating": rating, "justification": why}


def measurement_round(**overrides) -> dict:
    """A measurement-science round, every criterion `adequate` unless overridden."""
    data = {
        "rubric": "measurement-science",
        "recommendation": "Minor revision",
        **{name: criterion() for name in CRITERIA},
        "checklist_gaps": [{"item": "7b", "gap": "The expanded uncertainty omits its coverage factor."},
                           {"item": 3, "gap": "x"}],
        "revisions": [{"rank": 1, "text": "State the coverage factor of every expanded uncertainty."}],
        "report": "Measurement-science appraisal: ...",
    }
    data.update(overrides)
    return data


DESCRIPTOR_CRITERIA = ("documentation_completeness", "collection_consent", "technical_validation",
                       "access_licence", "reuse_potential")


def descriptor_round(**overrides) -> dict:
    """A data-descriptor round, every criterion `adequate` unless overridden."""
    data = {
        "rubric": "data-descriptor",
        "recommendation": "Minor revision",
        **{name: criterion(why="Data Records and the datasheet.") for name in DESCRIPTOR_CRITERIA},
        "checklist_gaps": [{"item": "4b", "gap": "The labelling procedure omits inter-annotator agreement."},
                           {"item": 2, "gap": "x"}],
        "revisions": [{"rank": 1, "text": "Report the inter-annotator agreement of the labels."}],
        "report": "Data-descriptor appraisal: ...",
    }
    data.update(overrides)
    return data


QUALITATIVE_COMMON = ("reflexivity", "sampling_sufficiency", "analytic_rigour", "quote_claim_fit",
                      "transferability")
QUALITATIVE_BLOCKS = {
    "qualitative-mixed": (),
    "consensus-foresight": ("panel_composition", "consensus_threshold", "rounds_feedback", "dissent_reported"),
    "experience-report": ("context", "what_was_done", "what_it_taught", "honest_limits"),
}


def qualitative_round(variant: str = "qualitative-mixed", **overrides) -> dict:
    """A qualitative-study round of one variant, its criteria `adequate` unless overridden."""
    data = {
        "rubric": "qualitative-study",
        "variant": variant,
        "recommendation": "Minor revision",
        **{name: criterion(why="Methods 3.2 and the codebook v03.")
           for name in QUALITATIVE_COMMON + QUALITATIVE_BLOCKS.get(variant, ())},
        "checklist_gaps": ([] if variant == "experience-report" else
                           [{"item": "6b", "gap": "The researcher's relationship to participants is not stated."},
                            {"item": 9, "gap": "x"}]),
        "revisions": [{"rank": 1, "text": "State the researchers' position towards the participants."}],
        "report": "Qualitative-study appraisal: ...",
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

    def test_a_rubric_that_is_not_text_is_refused_not_crashed(self) -> None:
        # A list or object as `rubric` must be a typed refusal, never a TypeError.
        self.set_line("review")
        for value in (["systematic-review"], {"id": "systematic-review"}):
            with self.subTest(value=value):
                self.assertRefusedUnchanged(ml_round(rubric=value),
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
        self.set_line("experiment-intervention")
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
        self.assertEqual(list(review.RUBRICS),
                         ["ml-conference", "systematic-review", "empirical-study", "measurement-science",
                          "data-descriptor", "qualitative-study"])
        self.assertEqual(review.RUBRICS["ml-conference"].lines, ("experimental",))
        self.assertEqual(review.RUBRICS["systematic-review"].lines, ("review",))
        self.assertEqual(review.RUBRICS["empirical-study"].lines,
                         ("observational-measurement", "experiment-intervention"))
        self.assertEqual(review.RUBRICS["measurement-science"].lines, ("hardware", "lab-simulation"))
        self.assertEqual(review.RUBRICS["data-descriptor"].lines, ("data-resource",))
        self.assertEqual(review.RUBRICS["qualitative-study"].lines, ("qualitative-participatory",))
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


    # --- the measurement-science rubric (F6) -----------------------------------

    def test_hardware_and_lab_simulation_are_judged_on_measurement_science(self) -> None:
        for line in ("hardware", "lab-simulation"):
            with self.subTest(line=line):
                self.set_line(line)
                self.assertRefusedUnchanged(empirical_round(), 'the line\'s rubric is "measurement-science"',
                                            code="RUBRIC_KIND_MISMATCH")
                data = measurement_round()
                del data["rubric"]
                code, out = self.record(data)
                self.assertEqual((code, out["status"]), (0, "ok"), out)
                self.assertEqual(self.rounds()[0]["rubric"], "measurement-science")
                self.file.unlink()
        self.set_line("observational-measurement")
        self.assertRefusedUnchanged(measurement_round(), 'the line\'s rubric is "empirical-study"',
                                    code="RUBRIC_KIND_MISMATCH")
        self.set_line("experimental")
        self.assertRefusedUnchanged(measurement_round(), 'rubric "measurement-science" does not serve the line',
                                    code="RUBRIC_KIND_MISMATCH")

    def test_a_measurement_round_is_stored_with_its_derived_overall_and_the_lines_checklist(self) -> None:
        self.set_line("hardware")
        code, out = self.record(measurement_round(uncertainty=criterion("limited", "  No type B budget.  "),
                                                  agreement=criterion("not applicable", "No reference device.")))
        self.assertEqual((code, out["status"], out["round"], out["pending_revisions"]), (0, "ok", 1, 1))
        entry = self.rounds()[0]
        self.assertEqual(list(entry), ["round", "date", "rubric", "recommendation", *CRITERIA, "overall_rating",
                                       "checklist", "checklist_gaps", "items", "revisions", "excluded", "report"])
        self.assertEqual(entry["rubric"], "measurement-science")
        self.assertEqual(entry["design_validity"], criterion())
        self.assertEqual(entry["uncertainty"], {"rating": "limited", "justification": "No type B budget."})
        self.assertEqual(entry["agreement"], {"rating": "not applicable", "justification": "No reference device."})
        self.assertEqual(entry["overall_rating"], "minor concerns")
        self.assertEqual(entry["checklist"], "hardwarex")
        self.assertEqual(entry["checklist_gaps"], [
            {"item": "7b", "gap": "The expanded uncertainty omits its coverage factor."}, {"item": 3, "gap": "x"}])
        for absent in ("overall", "confidence", "ratings", "amstar2", "risk_of_bias", "protocol_adherence"):
            self.assertNotIn(absent, entry)
        self.file.unlink()
        self.set_line("lab-simulation")
        code, _ = self.record(measurement_round(checklist="gum-reporting"))
        self.assertEqual((code, self.rounds()[0]["checklist"]), (0, "gum-reporting"))

    def test_the_overall_rating_follows_the_stated_rule(self) -> None:
        self.set_line("lab-simulation")
        cases = [
            ({}, "sound"),
            ({"agreement": "not applicable"}, "sound"),
            ({"reproducibility": "limited"}, "minor concerns"),
            ({"design_validity": "limited", "agreement": "not applicable"}, "minor concerns"),
            ({"uncertainty": "inadequate"}, "major concerns"),
            ({"calibration_traceability": "inadequate", "reproducibility": "limited"}, "major concerns"),
        ]
        for ratings, expected in cases:
            with self.subTest(ratings=ratings):
                if self.file.exists():
                    self.file.unlink()
                code, _ = self.record(measurement_round(**{k: criterion(v) for k, v in ratings.items()}))
                self.assertEqual((code, self.rounds()[0]["overall_rating"]), (0, expected))

    def test_an_asserted_overall_rating_must_match_the_rule(self) -> None:
        self.set_line("hardware")
        self.assertRefusedUnchanged(measurement_round(uncertainty=criterion("inadequate"), overall_rating="sound"),
                                    'overall_rating "sound" does not match the rule: major concerns')
        code, _ = self.record(measurement_round(uncertainty=criterion("inadequate"), overall_rating="major concerns"))
        self.assertEqual(code, 0)

    def test_every_criterion_needs_a_rating_on_its_scale_and_a_justification(self) -> None:
        self.set_line("hardware")
        for name in CRITERIA:
            with self.subTest(name=name):
                self.assertRefusedUnchanged(measurement_round(**{name: None}), f"{name} must be an object")
                self.assertRefusedUnchanged(measurement_round(**{name: criterion("fine")}),
                                            f"{name}.rating must be one of adequate, limited, inadequate")
                self.assertRefusedUnchanged(measurement_round(**{name: criterion(why=" ")}),
                                            f"{name} needs a non-empty justification")
        for name in CRITERIA[:-1]:
            with self.subTest(not_applicable=name):
                self.assertRefusedUnchanged(measurement_round(**{name: criterion("not applicable")}),
                                            f"{name}.rating must be one of adequate, limited, inadequate")
        self.assertRefusedUnchanged(measurement_round(agreement=criterion("not applicable", "")),
                                    "agreement needs a non-empty justification")

    def test_checklist_gaps_name_an_item_of_the_lines_checklist(self) -> None:
        self.set_line("hardware")
        self.assertRefusedUnchanged(measurement_round(checklist="gum-reporting"),
                                    'checklist must be the line\'s checklist "hardwarex"')
        self.assertRefusedUnchanged(measurement_round(checklist="STROBE"),
                                    'checklist must be the line\'s checklist "hardwarex"')
        self.assertRefusedUnchanged(measurement_round(checklist_gaps=[{"item": "a12", "gap": "x"}]),
                                    "checklist_gaps[1] needs an item number")
        self.assertRefusedUnchanged(measurement_round(checklist_gaps=[{"item": 2, "gap": ""}]),
                                    "checklist_gaps[1] needs an item number")
        self.assertRefusedUnchanged(measurement_round(checklist_gaps="none"), "checklist_gaps must be a list")
        code, _ = self.record(measurement_round(checklist_gaps=[], checklist="hardwarex"))
        self.assertEqual((code, self.rounds()[0]["checklist_gaps"]), (0, []))

    def test_the_shared_fields_still_apply_to_a_measurement_round(self) -> None:
        self.set_line("lab-simulation")
        self.assertRefusedUnchanged(measurement_round(report=""), "report must be non-empty text")
        self.assertRefusedUnchanged(measurement_round(recommendation=""), "recommendation must be non-empty text")
        self.record(measurement_round())
        self.assertRefusedUnchanged(measurement_round(), "[1]", code="REVIEW_ITEMS_MISSING")
        code, out = self.record(measurement_round(items=[{"rank": 1, "verdict": "resolved", "evidence": "Table 3."}],
                                                  revisions=[]))
        self.assertEqual((code, out["round"]), (0, 2))
        self.assertEqual(self.rounds()[1]["items"][0]["item"],
                         "State the coverage factor of every expanded uncertainty.")


    # --- the data-descriptor rubric (H5) ---------------------------------------

    def test_data_resource_is_judged_on_data_descriptor(self) -> None:
        self.set_line("data-resource")
        self.assertRefusedUnchanged(empirical_round(), 'the line\'s rubric is "data-descriptor"',
                                    code="RUBRIC_KIND_MISMATCH")
        self.assertRefusedUnchanged(measurement_round(), 'the line\'s rubric is "data-descriptor"',
                                    code="RUBRIC_KIND_MISMATCH")
        data = descriptor_round()
        del data["rubric"]
        code, out = self.record(data)
        self.assertEqual((code, out["status"]), (0, "ok"), out)
        self.assertEqual(self.rounds()[0]["rubric"], "data-descriptor")
        self.file.unlink()
        for line, expected in (("observational-measurement", "empirical-study"), ("hardware", "measurement-science"),
                               ("review", "systematic-review")):
            with self.subTest(line=line):
                self.set_line(line)
                self.assertRefusedUnchanged(descriptor_round(), f'the line\'s rubric is "{expected}"',
                                            code="RUBRIC_KIND_MISMATCH")
        self.set_line("experimental")
        self.assertRefusedUnchanged(descriptor_round(), 'rubric "data-descriptor" does not serve the line',
                                    code="RUBRIC_KIND_MISMATCH")

    def test_a_descriptor_round_is_stored_with_its_derived_overall_and_the_datasheets_checklist(self) -> None:
        self.set_line("data-resource")
        code, out = self.record(descriptor_round(reuse_potential=criterion("limited", "  No usage notes.  ")))
        self.assertEqual((code, out["status"], out["round"], out["pending_revisions"]), (0, "ok", 1, 1))
        entry = self.rounds()[0]
        self.assertEqual(list(entry), ["round", "date", "rubric", "recommendation", *DESCRIPTOR_CRITERIA,
                                       "overall_rating", "checklist", "checklist_gaps", "items", "revisions",
                                       "excluded", "report"])
        self.assertEqual(entry["rubric"], "data-descriptor")
        self.assertEqual(entry["documentation_completeness"], criterion(why="Data Records and the datasheet."))
        self.assertEqual(entry["reuse_potential"], {"rating": "limited", "justification": "No usage notes."})
        self.assertEqual(entry["overall_rating"], "minor concerns")
        self.assertEqual(entry["checklist"], "datasheets")
        self.assertEqual(entry["checklist_gaps"], [
            {"item": "4b", "gap": "The labelling procedure omits inter-annotator agreement."},
            {"item": 2, "gap": "x"}])
        for absent in ("overall", "confidence", "ratings", "amstar2", "risk_of_bias", "protocol_adherence",
                       "design_validity", "agreement"):
            self.assertNotIn(absent, entry)
        self.file.unlink()
        code, _ = self.record(descriptor_round(checklist="datasheets"))
        self.assertEqual((code, self.rounds()[0]["checklist"]), (0, "datasheets"))

    def test_the_descriptor_overall_rating_follows_the_stated_rule(self) -> None:
        self.set_line("data-resource")
        cases = [
            ({}, "sound"),
            ({"access_licence": "limited"}, "minor concerns"),
            ({"documentation_completeness": "limited", "reuse_potential": "limited"}, "minor concerns"),
            ({"collection_consent": "inadequate"}, "major concerns"),
            ({"technical_validation": "inadequate", "access_licence": "limited"}, "major concerns"),
        ]
        for ratings, expected in cases:
            with self.subTest(ratings=ratings):
                if self.file.exists():
                    self.file.unlink()
                code, _ = self.record(descriptor_round(**{k: criterion(v) for k, v in ratings.items()}))
                self.assertEqual((code, self.rounds()[0]["overall_rating"]), (0, expected))

    def test_an_asserted_descriptor_overall_rating_must_match_the_rule(self) -> None:
        self.set_line("data-resource")
        self.assertRefusedUnchanged(
            descriptor_round(access_licence=criterion("inadequate"), overall_rating="minor concerns"),
            'overall_rating "minor concerns" does not match the rule: major concerns')
        code, _ = self.record(descriptor_round(access_licence=criterion("inadequate"),
                                               overall_rating="major concerns"))
        self.assertEqual((code, self.rounds()[0]["overall_rating"]), (0, "major concerns"))

    def test_every_descriptor_criterion_needs_a_rating_on_its_scale_and_a_justification(self) -> None:
        self.set_line("data-resource")
        for name in DESCRIPTOR_CRITERIA:
            with self.subTest(name=name):
                self.assertRefusedUnchanged(descriptor_round(**{name: None}), f"{name} must be an object")
                self.assertRefusedUnchanged(descriptor_round(**{name: criterion("fine")}),
                                            f"{name}.rating must be one of adequate, limited, inadequate")
                self.assertRefusedUnchanged(descriptor_round(**{name: criterion("not applicable")}),
                                            f"{name}.rating must be one of adequate, limited, inadequate")
                self.assertRefusedUnchanged(descriptor_round(**{name: criterion(why=" ")}),
                                            f"{name} needs a non-empty justification")

    def test_descriptor_checklist_gaps_name_an_item_of_datasheets(self) -> None:
        self.set_line("data-resource")
        for other in ("STROBE", "hardwarex", ""):
            with self.subTest(checklist=other):
                self.assertRefusedUnchanged(descriptor_round(checklist=other),
                                            'checklist must be the line\'s checklist "datasheets"')
        self.assertRefusedUnchanged(descriptor_round(checklist_gaps=[{"item": "a12", "gap": "x"}]),
                                    "checklist_gaps[1] needs an item number")
        self.assertRefusedUnchanged(descriptor_round(checklist_gaps=[{"item": 2, "gap": ""}]),
                                    "checklist_gaps[1] needs an item number")
        self.assertRefusedUnchanged(descriptor_round(checklist_gaps="none"), "checklist_gaps must be a list")
        code, _ = self.record(descriptor_round(checklist_gaps=[]))
        self.assertEqual((code, self.rounds()[0]["checklist_gaps"]), (0, []))

    def test_the_shared_fields_still_apply_to_a_descriptor_round(self) -> None:
        self.set_line("data-resource")
        self.assertRefusedUnchanged(descriptor_round(report=""), "report must be non-empty text")
        self.assertRefusedUnchanged(descriptor_round(recommendation=""), "recommendation must be non-empty text")
        self.record(descriptor_round())
        self.assertRefusedUnchanged(descriptor_round(), "[1]", code="REVIEW_ITEMS_MISSING")
        code, out = self.record(descriptor_round(items=[{"rank": 1, "verdict": "partly", "evidence": "Table 2."}],
                                                 revisions=[]))
        self.assertEqual((code, out["round"]), (0, 2))
        self.assertEqual(self.rounds()[1]["items"][0]["item"], "Report the inter-annotator agreement of the labels.")


    # --- the qualitative-study rubric (K6) -------------------------------------

    def agree_variant(self, variant, type_id: str = "qualitative-participatory") -> None:
        """Write `.papersmith/paper_type.json` as `paper_type_cli.py agree` leaves it."""
        path = self.root / ".papersmith" / "paper_type.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"scores": [], "suggested": type_id, "agreed": type_id,
                                    "agreed_variant": variant, "agreed_by": "op"}), encoding="utf-8")

    def test_qualitative_participatory_is_judged_on_qualitative_study(self) -> None:
        self.set_line("qualitative-participatory")
        for other in (empirical_round(), measurement_round(), descriptor_round()):
            with self.subTest(rubric=other["rubric"]):
                self.assertRefusedUnchanged(other, 'the line\'s rubric is "qualitative-study"',
                                            code="RUBRIC_KIND_MISMATCH")
        data = qualitative_round()
        del data["rubric"]
        code, out = self.record(data)
        self.assertEqual((code, out["status"]), (0, "ok"), out)
        self.assertEqual(self.rounds()[0]["rubric"], "qualitative-study")
        self.file.unlink()
        for line, expected in (("observational-measurement", "empirical-study"), ("data-resource", "data-descriptor"),
                               ("experimental", "ml-conference")):
            with self.subTest(line=line):
                self.set_line(line)
                self.assertRefusedUnchanged(qualitative_round(), f'the line\'s rubric is "{expected}"',
                                            code="RUBRIC_KIND_MISMATCH")

    def test_a_round_of_each_variant_is_stored_with_its_criteria_derived_overall_and_checklist(self) -> None:
        self.set_line("qualitative-participatory")
        cases = (("qualitative-mixed", "srqr"), ("consensus-foresight", "accord"), ("experience-report", None))
        for variant, checklist in cases:
            with self.subTest(variant=variant):
                self.file.unlink(missing_ok=True)
                code, out = self.record(qualitative_round(variant, transferability=criterion("limited", "  Site?  ")))
                self.assertEqual((code, out["status"], out["round"], out["pending_revisions"]), (0, "ok", 1, 1), out)
                entry = self.rounds()[0]
                criteria = QUALITATIVE_COMMON + QUALITATIVE_BLOCKS[variant]
                self.assertEqual(list(entry), ["round", "date", "rubric", "recommendation", "variant", *criteria,
                                               "overall_rating", "checklist", "checklist_gaps", "items",
                                               "revisions", "excluded", "report"])
                self.assertEqual((entry["rubric"], entry["variant"]), ("qualitative-study", variant))
                self.assertEqual(entry["reflexivity"], criterion(why="Methods 3.2 and the codebook v03."))
                self.assertEqual(entry["transferability"], {"rating": "limited", "justification": "Site?"})
                self.assertEqual(entry["overall_rating"], "minor concerns")
                self.assertEqual(entry["checklist"], checklist)
                self.assertEqual(len(entry["checklist_gaps"]), 0 if checklist is None else 2)
                for absent in ("overall", "confidence", "ratings", "amstar2", "risk_of_bias", "protocol_adherence",
                               "design_validity", "agreement", "documentation_completeness"):
                    self.assertNotIn(absent, entry)

    def test_a_qualitative_mixed_round_may_name_coreq_instead_of_srqr(self) -> None:
        self.set_line("qualitative-participatory")
        code, _ = self.record(qualitative_round(checklist="coreq"))
        self.assertEqual((code, self.rounds()[0]["checklist"]), (0, "coreq"))
        self.file.unlink()
        code, _ = self.record(qualitative_round(checklist="srqr"))
        self.assertEqual((code, self.rounds()[0]["checklist"]), (0, "srqr"))

    def test_the_qualitative_overall_rating_follows_the_stated_rule(self) -> None:
        self.set_line("qualitative-participatory")
        cases = [
            ("qualitative-mixed", {}, "sound"),
            ("qualitative-mixed", {"reflexivity": "limited"}, "minor concerns"),
            ("qualitative-mixed", {"quote_claim_fit": "inadequate", "reflexivity": "limited"}, "major concerns"),
            ("consensus-foresight", {"dissent_reported": "limited"}, "minor concerns"),
            ("consensus-foresight", {"consensus_threshold": "inadequate"}, "major concerns"),
            ("experience-report", {"honest_limits": "inadequate"}, "major concerns"),
            ("experience-report", {"quote_claim_fit": "not applicable", "sampling_sufficiency": "not applicable"},
             "sound"),
            ("experience-report", {"quote_claim_fit": "not applicable", "what_it_taught": "limited"},
             "minor concerns"),
        ]
        for variant, ratings, expected in cases:
            with self.subTest(variant=variant, ratings=ratings):
                self.file.unlink(missing_ok=True)
                code, out = self.record(qualitative_round(variant, **{k: criterion(v) for k, v in ratings.items()}))
                self.assertEqual((code, self.rounds()[0]["overall_rating"]), (0, expected), out)

    def test_an_asserted_qualitative_overall_rating_must_match_the_rule(self) -> None:
        self.set_line("qualitative-participatory")
        self.assertRefusedUnchanged(
            qualitative_round(analytic_rigour=criterion("inadequate"), overall_rating="sound"),
            'overall_rating "sound" does not match the rule: major concerns')
        code, _ = self.record(qualitative_round(analytic_rigour=criterion("inadequate"),
                                                overall_rating="major concerns"))
        self.assertEqual((code, self.rounds()[0]["overall_rating"]), (0, "major concerns"))

    def test_every_criterion_of_the_variant_needs_a_rating_on_its_scale_and_a_justification(self) -> None:
        self.set_line("qualitative-participatory")
        for variant, block in QUALITATIVE_BLOCKS.items():
            for name in QUALITATIVE_COMMON + block:
                with self.subTest(variant=variant, name=name):
                    self.assertRefusedUnchanged(qualitative_round(variant, **{name: None}), f"{name} must be an object")
                    self.assertRefusedUnchanged(qualitative_round(variant, **{name: criterion("fine")}),
                                                f"{name}.rating must be one of adequate, limited, inadequate")
                    self.assertRefusedUnchanged(qualitative_round(variant, **{name: criterion(why=" ")}),
                                                f"{name} needs a non-empty justification")

    def test_not_applicable_only_for_sampling_and_quotes_in_an_experience_report(self) -> None:
        self.set_line("qualitative-participatory")
        for variant, block in QUALITATIVE_BLOCKS.items():
            for name in QUALITATIVE_COMMON + block:
                if variant == "experience-report" and name in ("sampling_sufficiency", "quote_claim_fit"):
                    continue
                with self.subTest(variant=variant, name=name):
                    self.assertRefusedUnchanged(qualitative_round(variant, **{name: criterion("not applicable")}),
                                                f"{name}.rating must be one of adequate, limited, inadequate")
        self.assertRefusedUnchanged(
            qualitative_round("experience-report", quote_claim_fit=criterion("not applicable", "")),
            "quote_claim_fit needs a non-empty justification (the reason when not applicable)")
        self.assertRefusedUnchanged(
            qualitative_round("experience-report", sampling_sufficiency=criterion("fine")),
            "sampling_sufficiency.rating must be one of adequate, limited, inadequate, not applicable")
        code, _ = self.record(qualitative_round("experience-report",
                                                quote_claim_fit=criterion("not applicable", "No participant data.")))
        self.assertEqual(code, 0)
        self.assertEqual(self.rounds()[0]["quote_claim_fit"],
                         {"rating": "not applicable", "justification": "No participant data."})

    def test_another_variants_criteria_are_refused(self) -> None:
        self.set_line("qualitative-participatory")
        self.assertRefusedUnchanged(qualitative_round(panel_composition=criterion()),
                                    "panel_composition does not apply to the qualitative-mixed variant")
        self.assertRefusedUnchanged(qualitative_round("consensus-foresight", honest_limits=criterion()),
                                    "honest_limits does not apply to the consensus-foresight variant")
        self.assertRefusedUnchanged(qualitative_round("experience-report", rounds_feedback=criterion()),
                                    "rounds_feedback does not apply to the experience-report variant")

    def test_the_variant_is_declared_or_agreed_and_never_contradicts_the_agreed_one(self) -> None:
        self.set_line("qualitative-participatory")
        for value in ("delphi", "", 3, None):
            with self.subTest(variant=value):
                self.assertRefusedUnchanged(qualitative_round(variant=value),
                                            "variant must be one of qualitative-mixed, consensus-foresight, "
                                            "experience-report")
        missing = qualitative_round()
        del missing["variant"]
        self.assertRefusedUnchanged(missing, "no variant is agreed in .papersmith/paper_type.json")
        self.agree_variant("consensus-foresight")
        self.assertRefusedUnchanged(qualitative_round("qualitative-mixed"),
                                    'variant "qualitative-mixed" is not the agreed variant "consensus-foresight"')
        data = qualitative_round("consensus-foresight")
        del data["variant"]
        code, out = self.record(data)
        self.assertEqual((code, self.rounds()[0]["variant"], self.rounds()[0]["checklist"]),
                         (0, "consensus-foresight", "accord"), out)
        self.file.unlink()
        # A variant recorded for another type, or none, leaves the round's own declaration in charge.
        for variant, type_id in (("observational", "observational-measurement"), (None, "qualitative-participatory")):
            with self.subTest(agreed=(type_id, variant)):
                self.agree_variant(variant, type_id)
                code, _ = self.record(qualitative_round("experience-report"))
                self.assertEqual((code, self.rounds()[0]["variant"]), (0, "experience-report"))
                self.file.unlink()
        (self.root / ".papersmith" / "paper_type.json").write_text("{not json", encoding="utf-8")
        self.assertRefusedUnchanged(missing, "no variant is agreed in .papersmith/paper_type.json")

    def test_qualitative_checklist_and_gaps_follow_the_variant(self) -> None:
        self.set_line("qualitative-participatory")
        for variant, other, allowed in (("qualitative-mixed", "accord", '"srqr", "coreq"'),
                                        ("qualitative-mixed", "STROBE", '"srqr", "coreq"'),
                                        ("consensus-foresight", "srqr", '"accord"')):
            with self.subTest(variant=variant, checklist=other):
                self.assertRefusedUnchanged(qualitative_round(variant, checklist=other),
                                            f"checklist must be one of the {variant} variant's checklists {allowed}")
        self.assertRefusedUnchanged(qualitative_round("experience-report", checklist="srqr"),
                                    "the experience-report variant has no reporting checklist")
        self.assertRefusedUnchanged(
            qualitative_round("experience-report", checklist_gaps=[{"item": 3, "gap": "x"}]),
            "checklist_gaps must be empty: the experience-report variant has no reporting checklist")
        self.assertRefusedUnchanged(qualitative_round(checklist_gaps=[{"item": "a12", "gap": "x"}]),
                                    "checklist_gaps[1] needs an item number")
        self.assertRefusedUnchanged(qualitative_round(checklist_gaps="none"), "checklist_gaps must be a list")
        code, _ = self.record(qualitative_round(checklist_gaps=[]))
        self.assertEqual((code, self.rounds()[0]["checklist_gaps"]), (0, []))

    def test_the_shared_fields_still_apply_to_a_qualitative_round(self) -> None:
        self.set_line("qualitative-participatory")
        self.assertRefusedUnchanged(qualitative_round(report=""), "report must be non-empty text")
        self.assertRefusedUnchanged(qualitative_round(recommendation=""), "recommendation must be non-empty text")
        self.record(qualitative_round())
        self.assertRefusedUnchanged(qualitative_round(), "[1]", code="REVIEW_ITEMS_MISSING")
        code, out = self.record(qualitative_round(items=[{"rank": 1, "verdict": "resolved", "evidence": "4.1."}],
                                                  revisions=[]))
        self.assertEqual((code, out["round"]), (0, 2))
        self.assertEqual(self.rounds()[1]["items"][0]["item"],
                         "State the researchers' position towards the participants.")


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

    def test_a_measurement_round_renders_its_criteria_escaped(self) -> None:
        entry = {"round": 2, "rubric": "measurement-science", "recommendation": "Major revision",
                 "design_validity": {"rating": "adequate", "justification": "<b>bench</b> rig"},
                 "calibration_traceability": {"rating": "limited", "justification": "Certificate expired."},
                 "uncertainty": {"rating": "inadequate", "justification": "<i>No budget</i>"},
                 "reproducibility": {"rating": "adequate", "justification": "CERN-OHL files."},
                 "agreement": {"rating": "not applicable", "justification": "No reference device."},
                 "overall_rating": "major concerns", "checklist": "hardwarex",
                 "checklist_gaps": [{"item": "7b", "gap": "<script>k</script>"}], "report": "r"}
        html = render({"status": "ok", "rounds": [entry]})
        for fragment in ("review.rubric.measurement", "review.measurement.overall",
                         "review.measurement.overall.major_concerns", "review.measurement.criteria",
                         "review.measurement.criterion.calibration_traceability",
                         "review.measurement.criterion.agreement", "review.measurement.rating.not_applicable",
                         "review.measurement.rating.inadequate", "review.measurement.gaps", "hardwarex", "7b",
                         "&lt;b&gt;bench&lt;/b&gt;", "&lt;i&gt;No budget&lt;/i&gt;", "&lt;script&gt;k"):
            self.assertIn(fragment, html)
        for absent in ("<b>bench", "<script>k", "/6", "review.amstar2", "review.empirical"):
            self.assertNotIn(absent, html)
        older = render({"status": "ok", "rounds": [entry, {**entry, "round": 3}]})
        self.assertIn("review.measurement.overall.major_concerns · Major revision", older)

    def test_a_descriptor_round_renders_its_criteria_escaped(self) -> None:
        entry = {"round": 2, "rubric": "data-descriptor", "recommendation": "Major revision",
                 "documentation_completeness": {"rating": "adequate", "justification": "<b>dictionary</b> full"},
                 "collection_consent": {"rating": "limited", "justification": "Consent form not shared."},
                 "technical_validation": {"rating": "inadequate", "justification": "<i>No QC</i>"},
                 "access_licence": {"rating": "adequate", "justification": "CC BY 4.0, DOI minted."},
                 "reuse_potential": {"rating": "limited", "justification": "No usage notes."},
                 "overall_rating": "major concerns", "checklist": "datasheets",
                 "checklist_gaps": [{"item": "4b", "gap": "<script>k</script>"}], "report": "r"}
        html = render({"status": "ok", "rounds": [entry]})
        for fragment in ("review.rubric.descriptor", "review.descriptor.overall",
                         "review.descriptor.overall.major_concerns", "review.descriptor.criteria",
                         "review.descriptor.criterion.documentation_completeness",
                         "review.descriptor.criterion.collection_consent",
                         "review.descriptor.criterion.technical_validation",
                         "review.descriptor.criterion.access_licence", "review.descriptor.criterion.reuse_potential",
                         "review.descriptor.rating.adequate", "review.descriptor.rating.limited",
                         "review.descriptor.rating.inadequate", "review.descriptor.criterion",
                         "review.descriptor.justification", "review.descriptor.gaps", "review.descriptor.item",
                         "review.descriptor.gap", "datasheets", "4b",
                         "&lt;b&gt;dictionary&lt;/b&gt;", "&lt;i&gt;No QC&lt;/i&gt;", "&lt;script&gt;k"):
            self.assertIn(fragment, html)
        for absent in ("<b>dictionary", "<script>k", "/6", "review.amstar2", "review.empirical",
                       "review.measurement"):
            self.assertNotIn(absent, html)
        older = render({"status": "ok", "rounds": [entry, {**entry, "round": 3}]})
        self.assertIn("review.descriptor.overall.major_concerns · Major revision", older)

    def test_a_qualitative_round_renders_its_variant_criteria_escaped(self) -> None:
        common = {name: {"rating": "adequate", "justification": f"{name} ok"} for name in QUALITATIVE_COMMON}
        entry = {"round": 2, "rubric": "qualitative-study", "variant": "consensus-foresight",
                 "recommendation": "Major revision", **common,
                 "reflexivity": {"rating": "limited", "justification": "<b>insider</b> role"},
                 "panel_composition": {"rating": "adequate", "justification": "21 experts."},
                 "consensus_threshold": {"rating": "inadequate", "justification": "<i>Set after round 1</i>"},
                 "rounds_feedback": {"rating": "adequate", "justification": "Medians fed back."},
                 "dissent_reported": {"rating": "limited", "justification": "Non-consensus items omitted."},
                 "overall_rating": "major concerns", "checklist": "accord",
                 "checklist_gaps": [{"item": "5b", "gap": "<script>k</script>"}], "report": "r"}
        html = render({"status": "ok", "rounds": [entry]})
        for fragment in ("review.rubric.qualitative", "review.qualitative.overall",
                         "review.qualitative.overall.major_concerns", "review.qualitative.variant",
                         "review.qualitative.variant.consensus_foresight", "review.qualitative.criteria",
                         "review.qualitative.criterion", "review.qualitative.rating",
                         "review.qualitative.justification",
                         *(f"review.qualitative.criterion.{n}" for n in QUALITATIVE_COMMON),
                         *(f"review.qualitative.criterion.{n}" for n in QUALITATIVE_BLOCKS["consensus-foresight"]),
                         "review.qualitative.rating.adequate", "review.qualitative.rating.limited",
                         "review.qualitative.rating.inadequate", "review.qualitative.gaps",
                         "review.qualitative.item", "review.qualitative.gap", "accord", "5b",
                         "&lt;b&gt;insider&lt;/b&gt;", "&lt;i&gt;Set after round 1&lt;/i&gt;", "&lt;script&gt;k"):
            self.assertIn(fragment, html)
        for absent in ("<b>insider", "<script>k", "/6", "review.amstar2", "review.empirical", "review.measurement",
                       "review.descriptor", "review.qualitative.criterion.honest_limits"):
            self.assertNotIn(absent, html)
        older = render({"status": "ok", "rounds": [entry, {**entry, "round": 3}]})
        self.assertIn("review.qualitative.overall.major_concerns · Major revision", older)
        report = {**{k: v for k, v in entry.items() if k not in QUALITATIVE_BLOCKS["consensus-foresight"]},
                  "variant": "experience-report", "checklist": None, "checklist_gaps": [],
                  "quote_claim_fit": {"rating": "not applicable", "justification": "No participant data."},
                  **{n: {"rating": "adequate", "justification": "j"} for n in QUALITATIVE_BLOCKS["experience-report"]}}
        html = render({"status": "ok", "rounds": [report]})
        for fragment in ("review.qualitative.variant.experience_report", "review.qualitative.rating.not_applicable",
                         *(f"review.qualitative.criterion.{n}" for n in QUALITATIVE_BLOCKS["experience-report"])):
            self.assertIn(fragment, html)
        for absent in ("review.qualitative.gaps", "review.qualitative.criterion.panel_composition", "null"):
            self.assertNotIn(absent, html)

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
        self.assertNotIn("review.measurement", html)
        self.assertNotIn("review.descriptor", html)
        self.assertNotIn("review.qualitative", html)

if __name__ == "__main__":
    unittest.main()
