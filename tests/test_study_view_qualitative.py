"""The Study tab's qualitative sections (paper-type-lines S8, T8-B6, decision K8).

A `qualitative-participatory` workspace answers three more sections of
`GET /api/study`, read only through the qualitative core's side-effect-free
readers:

* `transcripts` (gate G-TRANSCRIPTS, `records.transcripts_state`): every
  registered transcript or field note with its participant code, kind, file,
  character count, short sha256, consent and de-identification statements, who
  registered it and when, current or stale with the reasons, and the totals;
* `themes` (gate G-ANALYSIS, `records.codebook_state` and `themes_state`): the
  codebook versions and the operator's theme sign-off (the codebook version and
  the number of transcripts it covers), current or stale with the reasons;
* `consensus` (gate G-ROUNDS, `consensus.panel_state`, `plan_state`,
  `round_results`, `rounds_state`, `micmac_state`): the panel, the plan, per
  round and item the agreement computed from the operator's response files, and
  the MICMAC ranking and quadrant per variable with the power used.

K8: "never a transcript's text"; a response file's comment or an individual
rating never reaches the view either. A corrupt record turns its part into its
corrupt state, never a failed `/api/study`. A workspace of another line shows a
section only once its record exists. Every record is written by the real CLIs.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from skills._core.command_center import server, study_view
from skills._core.qualitative import consensus, records as qual
from tests.test_qualitative_consensus import MATRIX, PANEL, ROUND_1, ROUND_2, SECRET
from tests.test_study_view import REPO, cli, lock, revision, workspace, write

KIND = "qualitative-participatory"
QUAL = REPO / "skills" / "_core" / "qualitative" / "qual_cli.py"
CONSENSUS = REPO / "skills" / "_core" / "qualitative" / "consensus_cli.py"
#: Recognizable words of the transcripts and of a response comment: none may reach the view.
TOKENS = ("ZEBRAQUILL7731", "MARMOTLANTERN4410", "OTTERBEACON2208", SECRET)
INTERVIEW = (f"Interviewer: How was the harvest?\nP01: The rains came late and {TOKENS[0]} was all we had.\n"
             f"P01: The co-op helped more than the ministry. {TOKENS[1]}\n")
FOCUS_GROUP = f"Moderator: What changed?\nP02: Prices.\nP03: The road, {TOKENS[2]}.\n"
CONSENT = "Written consent <form C-12>"
DEIDENTIFIED = "Names and places replaced by codes"


def register(root: Path, file: str, participant: str, *extra: str, kind: str = "interview") -> None:
    cli(QUAL, root, "transcripts", "add", "--file", file, "--participant", participant, "--kind", kind,
        "--consent", CONSENT, "--deidentified", DEIDENTIFIED, "--by", "Ana Ruiz", *extra)


def transcripts(root: Path) -> None:
    write(root, "data/p01.txt", INTERVIEW)
    write(root, "data/fg1.txt", FOCUS_GROUP)
    register(root, "data/p01.txt", "P01")
    register(root, "data/fg1.txt", "P02", kind="focus-group")
    register(root, "data/fg1.txt", "P03", kind="focus-group")


def codebook(root: Path, text: str = "Codes: cost, access, trust\n") -> None:
    write(root, "analysis/codebook.md", text)
    cli(QUAL, root, "codebook", "record", "--file", "analysis/codebook.md", "--by", "Ana Ruiz")


def signoff(root: Path) -> None:
    write(root, "analysis/themes.md", "Theme 1: late rains\nTheme 2: the co-op\n")
    cli(QUAL, root, "themes", "signoff", "--file", "analysis/themes.md", "--by", "Luis Mora")


def consensus_records(root: Path, micmac: bool = True) -> None:
    lock(root)
    for member in PANEL:
        cli(CONSENSUS, root, "panel", "add", "--member", member, "--expertise", "nurse <primary care>",
            "--note", "recruited via a cooperative", "--by", "Ana Ruiz")
    cli(CONSENSUS, root, "plan", "record", "--rounds", "2", "--threshold", "75", "--scale", "1-5",
        "--agree-from", "4", "--by", "Ana Ruiz")
    for k, rows in ((1, ROUND_1), (2, ROUND_2)):
        write(root, f"data/round{k}.csv", "member,item,rating,comment\n" + "\n".join(rows) + "\n")
        cli(CONSENSUS, root, "round", "record", "--round", str(k), "--file", f"data/round{k}.csv", "--by", "Ana Ruiz")
    if micmac:
        write(root, "data/matrix.csv", "\n".join(MATRIX) + "\n")
        cli(CONSENSUS, root, "micmac", "compute", "--file", "data/matrix.csv", "--by", "Ana Ruiz")


class QualitativeCase(unittest.TestCase):
    def get(self, root: Path, route: str = "/api/study") -> dict:
        response = TestClient(server.create_app(root)).get(route)
        self.assertEqual(response.status_code, 200, response.text)
        for token in TOKENS:
            self.assertNotIn(token, response.text, "a transcript's text or a comment leaked into the view")
        return response.json()

    def section(self, view: dict, name: str) -> dict:
        self.assertIn(name, view)
        self.assertTrue(view[name]["available"], view[name])
        return view[name]


class TranscriptsTests(QualitativeCase):
    def test_absent_in_a_qualitative_workspace(self) -> None:
        view = self.get(workspace(self, KIND))
        self.assertEqual(view["paper_kind"], KIND)
        self.assertEqual(view["warnings"], [])
        self.assertEqual(self.section(view, "transcripts"), {
            "available": True, "gate": "G-TRANSCRIPTS", "state": "absent", "passed": False,
            "path": "study/transcripts.json", "transcripts": [],
            "counts": {"participants": 0, "transcripts": 0, "current": 0, "stale": 0}, "kinds": {}, "records": 0,
            "warnings": []})
        for name in study_view.SECTIONS:
            self.assertIn(name, view)

    def test_every_registration_and_the_totals(self) -> None:
        root = workspace(self, KIND)
        transcripts(root)
        section = self.section(self.get(root), "transcripts")
        rows = section.pop("transcripts")
        self.assertEqual(section, {
            "available": True, "gate": "G-TRANSCRIPTS", "state": "current", "passed": True,
            "path": "study/transcripts.json",
            "counts": {"participants": 3, "transcripts": 3, "current": 3, "stale": 0},
            "kinds": {"interview": 1, "focus-group": 2}, "records": 3, "warnings": []})
        for row in rows:
            self.assertTrue(row.pop("at"))
        digest = qual.transcripts_state(root)["transcripts"][0]["sha256"]
        self.assertEqual(rows[0], {"participant": "P01", "kind": "interview", "file": "data/p01.txt",
                                   "characters": len(INTERVIEW), "sha256": digest[:12], "consent": CONSENT,
                                   "deidentified": DEIDENTIFIED, "by": "Ana Ruiz", "state": "current",
                                   "reasons": []})
        self.assertEqual([(r["participant"], r["file"], r["kind"]) for r in rows[1:]],
                         [("P02", "data/fg1.txt", "focus-group"), ("P03", "data/fg1.txt", "focus-group")])

    def test_a_changed_and_a_missing_file_make_it_stale(self) -> None:
        root = workspace(self, KIND)
        transcripts(root)
        write(root, "data/p01.txt", INTERVIEW + "P01: one more line.\n")
        (root / "data/fg1.txt").unlink()
        section = self.section(self.get(root), "transcripts")
        self.assertEqual((section["state"], section["passed"], section["counts"]["stale"]), ("stale", False, 3))
        self.assertEqual([r["reasons"] for r in section["transcripts"]],
                         [["file-changed"], ["file-missing"], ["file-missing"]])
        self.assertEqual({w["code"] for w in section["warnings"]}, {"TRANSCRIPT_STALE"})

    def test_a_corrupt_record_never_breaks_the_view(self) -> None:
        root = workspace(self, KIND)
        write(root, "study/transcripts.json", "{not json")
        view = self.get(root)
        section = self.section(view, "transcripts")
        self.assertEqual((section["state"], section["code"], section["passed"]),
                         ("corrupt", "TRANSCRIPTS_CORRUPT", False))
        self.assertTrue(section["message"])
        self.assertTrue(view["protocol"]["available"])
        self.assertTrue(self.section(view, "themes"))

    def test_the_state_is_read_through_transcripts_state(self) -> None:
        root = workspace(self, KIND)
        calls = []

        def spy(where):
            calls.append(Path(where))
            return {"state": "stale", "gate": "G-TRANSCRIPTS", "passed": False, "records": 2,
                    "counts": {"transcripts": 1, "current": 0, "stale": 1, "participants": 1, "kinds": {"document": 1}},
                    "transcripts": [{"participant": "D1", "file": "d.txt", "kind": "document", "characters": 9,
                                     "sha256": "a" * 64, "state": "stale", "reasons": ["file-outside"],
                                     "text": TOKENS[0]}]}

        with mock.patch.object(qual, "transcripts_state", spy):
            section = self.section(self.get(root), "transcripts")
        self.assertIn(root, calls)
        row = section["transcripts"][0]
        self.assertEqual((row["sha256"], row["reasons"], row["characters"]), ("a" * 12, ["file-outside"], 9))
        self.assertNotIn("text", row)


class ThemesTests(QualitativeCase):
    def test_absent(self) -> None:
        self.assertEqual(self.section(self.get(workspace(self, KIND)), "themes"), {
            "available": True, "gate": "G-ANALYSIS", "passed": False,
            "codebook": {"state": "absent", "path": "study/codebook.json"},
            "signoff": {"state": "absent", "path": "study/themes.json"}, "warnings": []})

    def test_codebook_versions_and_a_current_signoff(self) -> None:
        root = workspace(self, KIND)
        transcripts(root)
        codebook(root, "v1\n")
        codebook(root, "v2\n")
        signoff(root)
        section = self.section(self.get(root), "themes")
        book, sign = section["codebook"], section["signoff"]
        self.assertTrue(section["passed"])
        versions = book.pop("versions")
        self.assertEqual([(v["version"], v["file"], v["by"], len(v["sha256"])) for v in versions],
                         [(1, "analysis/codebook.md", "Ana Ruiz", 12), (2, "analysis/codebook.md", "Ana Ruiz", 12)])
        self.assertTrue(all(v["at"] for v in versions))
        self.assertNotEqual(versions[0]["sha256"], versions[1]["sha256"])
        self.assertTrue(book.pop("at"))
        self.assertEqual(book, {"state": "current", "path": "study/codebook.json", "version": 2,
                                "file": "analysis/codebook.md", "sha256": versions[1]["sha256"], "by": "Ana Ruiz",
                                "reasons": []})
        self.assertTrue(sign.pop("at"))
        self.assertEqual(len(sign.pop("sha256")), 12)
        self.assertEqual(sign, {"state": "current", "path": "study/themes.json", "file": "analysis/themes.md",
                                "by": "Luis Mora", "codebook_version": 2, "codebook_sha256": versions[1]["sha256"],
                                "transcripts": 3, "reasons": [], "signoffs": 1})
        self.assertEqual(section["warnings"], [])

    def test_a_new_codebook_and_a_new_transcript_make_the_signoff_stale(self) -> None:
        root = workspace(self, KIND)
        transcripts(root)
        codebook(root)
        signoff(root)
        codebook(root, "Codes: cost, access, trust, roads\n")
        write(root, "data/p04.txt", "P04: fine.\n")
        register(root, "data/p04.txt", "P04")
        section = self.section(self.get(root), "themes")
        self.assertEqual(section["codebook"]["state"], "current")
        self.assertEqual((section["signoff"]["state"], section["signoff"]["reasons"], section["passed"]),
                         ("stale", ["codebook-changed", "transcript-added"], False))
        self.assertEqual(section["signoff"]["codebook_version"], 1)
        self.assertEqual([w["code"] for w in section["warnings"]], ["THEMES_STALE"])

    def test_a_changed_codebook_file_is_stale(self) -> None:
        root = workspace(self, KIND)
        codebook(root)
        write(root, "analysis/codebook.md", "edited\n")
        section = self.section(self.get(root), "themes")
        self.assertEqual((section["codebook"]["state"], section["codebook"]["reasons"]), ("stale", ["file-changed"]))
        self.assertEqual([w["code"] for w in section["warnings"]], ["CODEBOOK_STALE"])

    def test_corrupt_records_never_break_the_view(self) -> None:
        root = workspace(self, KIND)
        write(root, "study/codebook.json", "[]")
        write(root, "study/themes.json", '{"history": [{"file": "t.md", "sha256": "x"}]}')
        view = self.get(root)
        section = self.section(view, "themes")
        self.assertEqual((section["codebook"]["state"], section["codebook"]["code"]), ("corrupt", "CODEBOOK_CORRUPT"))
        self.assertEqual((section["signoff"]["state"], section["signoff"]["code"]), ("corrupt", "THEMES_CORRUPT"))
        self.assertTrue(section["codebook"]["message"] and section["signoff"]["message"])
        self.assertTrue(self.section(view, "transcripts"))


class ConsensusTests(QualitativeCase):
    def test_absent(self) -> None:
        section = self.section(self.get(workspace(self, KIND)), "consensus")
        self.assertEqual(section, {
            "available": True, "gate": "G-ROUNDS", "state": "absent", "passed": False, "planned": None,
            "missing": [], "panel": {"state": "absent", "path": "study/consensus/panel.json", "size": 0, "members": []},
            "plan": {"state": "absent", "path": "study/consensus/plan.json"},
            "rounds": {"state": "absent", "path": "study/consensus/rounds.json", "rounds": []},
            "micmac": {"state": "absent", "path": "study/consensus/micmac.json"}, "warnings": []})

    def test_panel_plan_rounds_and_micmac(self) -> None:
        root = workspace(self, KIND)
        consensus_records(root)
        section = self.section(self.get(root), "consensus")
        self.assertEqual((section["state"], section["passed"], section["planned"], section["missing"]),
                         ("passed", True, 2, []))
        self.assertEqual(section["panel"], {"state": "recorded", "path": "study/consensus/panel.json", "size": 4,
                                            "members": [{"member": m, "expertise": "nurse <primary care>"}
                                                        for m in PANEL]})
        plan = section["plan"]
        self.assertTrue(plan.pop("at"))
        self.assertEqual(plan, {"state": "current", "path": "study/consensus/plan.json", "rounds": 2, "threshold": 75,
                                "scale": {"min": 1, "max": 5}, "agree_from": 4,
                                "protocol_revision": "protocol/study-protocol-walking-v01.md", "by": "Ana Ruiz",
                                "reasons": [], "changes": 0})
        rounds = section["rounds"]
        self.assertEqual(rounds["state"], "recorded")
        first, second = rounds["rounds"]
        self.assertEqual((first["round"], first["state"], first["file"], first["responders"], first["responses"],
                          first["items_count"], first["consensus_items"], first["by"], len(first["sha256"])),
                         (1, "current", "data/round1.csv", 4, 8, 2, 1, "Ana Ruiz", 12))
        self.assertEqual(first["items"][0], {"item": "I1", "n": 4, "agree": 3, "agreement_percent": 75, "median": 4,
                                             "q1": 3.5, "q3": 4.25, "iqr": 0.75, "consensus": True, "change": None})
        self.assertEqual(second["items"], [{"item": "I2", "n": 4, "agree": 3, "agreement_percent": 75, "median": 4,
                                            "q1": 3.75, "q3": 4.25, "iqr": 0.5, "consensus": True,
                                            "change": {"previous_round": 1, "agreement_percent": 50, "median": 1.5,
                                                       "iqr": -1, "consensus_previous": False}}])
        micmac = section["micmac"]
        self.assertTrue(micmac.pop("at"))
        variables = micmac.pop("variables")
        self.assertEqual(len(micmac.pop("sha256")), 12)
        self.assertEqual(micmac, {"state": "current", "path": "study/consensus/micmac.json", "file": "data/matrix.csv",
                                  "by": "Ana Ruiz", "power": 3, "power_mode": "until-stable", "stable": True,
                                  "p_value": 4, "p_entries": 1, "reasons": [], "records": 1})
        self.assertEqual(variables[0], {
            "name": "A",
            "direct": {"influence": 8, "dependence": 2, "influence_rank": 1, "dependence_rank": 3,
                       "quadrant": "influential"},
            "indirect": {"influence": 104, "dependence": 32, "influence_rank": 1, "dependence_rank": 3,
                         "quadrant": "influential"}})
        self.assertEqual([(v["name"], v["direct"]["quadrant"], v["indirect"]["quadrant"],
                           v["indirect"]["influence_rank"], v["indirect"]["dependence_rank"]) for v in variables],
                         [("A", "influential", "influential", 1, 3), ("B", "relay", "relay", 2, 2),
                          ("C", "dependent", "dependent", 3, 1), ("D", "autonomous", "autonomous", 3, 4)])
        self.assertEqual(section["warnings"], [])

    def test_no_comment_and_no_individual_rating_reach_the_view(self) -> None:
        root = workspace(self, KIND)
        consensus_records(root, micmac=False)
        section = self.section(self.get(root), "consensus")
        for row in section["rounds"]["rounds"]:
            self.assertNotIn("comments", row)
            for item in row["items"]:
                self.assertEqual(set(item), {"item", "n", "agree", "agreement_percent", "median", "q1", "q3", "iqr",
                                             "consensus", "change"})
        blob = json.dumps(section)
        self.assertNotIn("recruited via a cooperative", blob)  # the panel's notes stay in the record
        self.assertNotIn("rating", blob)

    def test_a_changed_round_file_and_an_amended_protocol(self) -> None:
        root = workspace(self, KIND)
        consensus_records(root, micmac=False)
        write(root, "data/round2.csv", "member,item,rating\nP01,I2,1\n")
        section = self.section(self.get(root), "consensus")
        self.assertEqual((section["state"], section["passed"]), ("open", False))
        second = section["rounds"]["rounds"][1]
        self.assertEqual((second["state"], second["reasons"], second["items"]), ("stale", ["file-changed"], None))
        self.assertIn("ROUND_STALE", [w["code"] for w in section["warnings"]])
        revision(root, 2, "\nAmended.\n")
        cli(REPO / "skills/_core/empirical/study_cli.py", root, "protocol", "amend", "--by", "Ana Ruiz", "--reason",
            "wider panel")
        plan = self.section(self.get(root), "consensus")["plan"]
        self.assertEqual((plan["state"], plan["reasons"]), ("stale", ["protocol-amended"]))

    def test_a_missing_round_leaves_the_gate_open(self) -> None:
        root = workspace(self, KIND)
        consensus_records(root, micmac=False)
        data = json.loads((root / consensus.ROUNDS_PATH).read_text(encoding="utf-8"))
        data["history"] = data["history"][:1]
        write(root, consensus.ROUNDS_PATH, json.dumps(data))
        section = self.section(self.get(root), "consensus")
        self.assertEqual((section["state"], section["missing"], len(section["rounds"]["rounds"])), ("open", [2], 1))

    def test_corrupt_records_never_break_the_view(self) -> None:
        root = workspace(self, KIND)
        for path in (consensus.PANEL_PATH, consensus.PLAN_PATH, consensus.ROUNDS_PATH, consensus.MICMAC_PATH):
            write(root, path, "{not json")
        view = self.get(root)
        section = self.section(view, "consensus")
        self.assertEqual(section["state"], "corrupt")
        self.assertEqual([(section[part]["state"], section[part]["code"]) for part in ("panel", "plan", "rounds", "micmac")],
                         [("corrupt", "PANEL_CORRUPT"), ("corrupt", "PLAN_CORRUPT"), ("corrupt", "ROUNDS_CORRUPT"),
                          ("corrupt", "MICMAC_CORRUPT")])
        self.assertTrue(all(section[part]["message"] for part in ("panel", "plan", "rounds", "micmac")))
        self.assertTrue(view["protocol"]["available"])

    def test_the_readers_are_used(self) -> None:
        root = workspace(self, KIND)
        seen = []

        def spy(name, value):
            def reader(where, *args, **kwargs):
                seen.append(name)
                return value
            return reader

        with mock.patch.object(consensus, "panel_state", spy("panel", {"state": "absent", "members": [], "size": 0})), \
                mock.patch.object(consensus, "micmac_state", spy("micmac", {"state": "absent"})), \
                mock.patch.object(consensus, "round_results", spy("rounds", {"state": "absent", "rounds": []})):
            self.section(self.get(root), "consensus")
        self.assertTrue({"panel", "micmac", "rounds"} <= set(seen), seen)

    def test_a_reader_that_raises_turns_only_its_section_unavailable(self) -> None:
        root = workspace(self, KIND)

        def boom(where, *args, **kwargs):
            raise RuntimeError("reader <failed>")

        with mock.patch.object(consensus, "micmac_state", boom):
            view = self.get(root)
        self.assertEqual((view["consensus"]["available"], view["consensus"]["code"]), (False, "UNREADABLE"))
        self.assertTrue(view["transcripts"]["available"])


class LineTests(QualitativeCase):
    def test_another_line_shows_a_section_only_with_its_record(self) -> None:
        root = workspace(self)
        view = self.get(root)
        for name in study_view.QUALITATIVE_SECTIONS:
            self.assertNotIn(name, view)
        transcripts(root)
        view = self.get(root)
        self.assertEqual(self.section(view, "transcripts")["state"], "current")
        self.assertNotIn("themes", view)
        self.assertNotIn("consensus", view)
        codebook(root)
        self.assertEqual(self.section(self.get(root), "themes")["codebook"]["state"], "current")
        write(root, "data/matrix.csv", "\n".join(MATRIX) + "\n")
        cli(CONSENSUS, root, "micmac", "compute", "--file", "data/matrix.csv", "--by", "Ana Ruiz")
        self.assertEqual(self.section(self.get(root), "consensus")["micmac"]["state"], "current")

    def test_an_absent_core_turns_the_sections_unavailable(self) -> None:
        root = workspace(self, KIND)
        real = study_view._qualitative_module

        def without(name):
            return (None, f"{name} did not load") if name == "qualitative" else real(name)

        with mock.patch.object(study_view, "_qualitative_module", without):
            view = TestClient(server.create_app(root)).get("/api/study").json()
        self.assertEqual([(view[name]["available"], view[name].get("code")) for name in ("transcripts", "themes")],
                         [(False, study_view.MODULE_UNAVAILABLE)] * 2)
        self.assertTrue(view["consensus"]["available"])
        self.assertIn("qualitative did not load", view["warnings"])
        other = workspace(self)
        with mock.patch.object(study_view, "_qualitative_module", without):
            view = TestClient(server.create_app(other)).get("/api/study").json()
        self.assertNotIn("transcripts", view)
        self.assertEqual(view["warnings"], [])

    def test_the_view_carries_no_server_label_to_translate(self) -> None:
        root = workspace(self, KIND)
        transcripts(root)
        consensus_records(root)
        self.assertEqual(self.get(root, "/api/study?lang=es"), self.get(root))

    def test_the_sections_belong_to_the_qualitative_line(self) -> None:
        self.assertEqual(study_view.QUALITATIVE_KINDS, (KIND,))
        self.assertEqual(study_view.QUALITATIVE_SECTIONS, ("transcripts", "themes", "consensus"))
        self.assertIn(KIND, study_view.EMPIRICAL_KINDS)
        self.assertEqual(study_view.QUALITATIVE_RECORDS,
                         (qual.TRANSCRIPTS_PATH, qual.CODEBOOK_PATH, qual.THEMES_PATH, consensus.PANEL_PATH,
                          consensus.PLAN_PATH, consensus.ROUNDS_PATH, consensus.MICMAC_PATH))


if __name__ == "__main__":
    unittest.main()
