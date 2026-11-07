"""The problem tree and the pillar and hypothesis tree of a proposal."""

from __future__ import annotations

import contextlib
import datetime
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.results import citations_cli

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


citations = _load("citations_under_test", "skills/_core/results/citations.py")
THIS_YEAR = datetime.date.today().year


def novelty() -> dict:
    return {
        "problem_statement": "Degraded balanced accuracy of shallow encoders in pediatric EEG.",
        "problem_tree": {
            "central": {"text": "Degraded balanced accuracy of shallow encoders in pediatric EEG."},
            "causes": [{"id": "DC1", "text": "Noisy channel statistics across subjects."},
                       {"id": "DC2", "text": "Unstable gradients in deep parameterized circuits."}],
            "effects": [{"id": "EF1", "text": "Unreliable subject-level screening.", "caused_by": ["DC1", "DC2"]}],
        },
        "pillars": [{"id": "C1", "name": "Re-uploading"}, {"id": "C2", "name": "Spectral readout"}],
        "hypotheses": [{"id": "E1", "title": "Gain", "pillars": ["C1"]},
                       {"id": "E2", "title": "Stability", "pillars": ["C1", "C2"]}],
    }


def tree_keys() -> list[str]:
    return ["problem:central", "cause:DC1", "cause:DC2", "pillar:C1", "pillar:C2", "hypothesis:E1", "hypothesis:E2"]


class Workspace(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        (self.root / ".papersmith").mkdir()
        (self.root / "sota-pool").mkdir()
        self.ids = ["10.1000/a", "10.1000/b"]

    def write(self, data: dict, year: int | None = None, rank: dict | None = None, cited: bool = True) -> dict:
        year = THIS_YEAR - 1 if year is None else year
        (self.root / ".papersmith" / "model_spec.json").write_text(json.dumps({"novelty": data}))
        (self.root / "sota-pool" / "candidates.json").write_text(json.dumps(
            {"candidates": [{"identifier": i, "title": i, "year": year} for i in self.ids]}))
        good = {"work_type": "journal-article", "quartile": "Q1", "quartile_source": "sjr"}
        (self.root / "sota-pool" / "journal-ranks.json").write_text(json.dumps(
            {"schema": 1, "ranks": {i: {**good, **(rank or {})} for i in self.ids}}))
        entries = [{"id": i, "why": "Supports it."} for i in self.ids]
        ideas = {key: entries for key in tree_keys()} if cited else {}
        (self.root / ".papersmith" / "citations.json").write_text(json.dumps({"schema": 1, "ideas": ideas}))
        return citations.state(self.root)

    def owed(self, state: dict) -> list[str]:
        return state["stages"]["proposal"]["owed"]


class ProblemTree(Workspace):
    def test_a_complete_tree_owes_nothing(self):
        state = self.write(novelty())
        self.assertEqual(self.owed(state), [])
        self.assertEqual(state["stages"]["proposal"]["cited"], 7)
        self.assertEqual(state["trees"], [])

    def test_a_workspace_without_a_tree_owes_it(self):
        data = novelty()
        del data["problem_tree"]
        self.assertIn("tree:problem: novelty.problem_tree is missing", self.owed(self.write(data)))

    def test_the_central_problem_owes_two_references(self):
        state = self.write(novelty(), cited=False)
        self.assertIn("problem:central", self.owed(state))

    def test_one_cause_is_too_few(self):
        data = novelty()
        data["problem_tree"]["causes"] = data["problem_tree"]["causes"][:1]
        data["problem_tree"]["effects"][0]["caused_by"] = ["DC1"]
        self.assertIn("tree:causes: 1 direct cause(s), needs 2 to 3", self.owed(self.write(data)))

    def test_four_causes_are_too_many(self):
        data = novelty()
        extra = [{"id": f"DC{n}", "text": "Noisy labels."} for n in (3, 4)]
        data["problem_tree"]["causes"] += extra
        data["problem_tree"]["effects"][0]["caused_by"] = ["DC1", "DC2", "DC3", "DC4"]
        self.assertIn("tree:causes: 4 direct cause(s), needs 2 to 3", self.owed(self.write(data)))

    def test_every_cause_owes_two_references(self):
        state = self.write(novelty(), cited=False)
        self.assertIn("cause:DC1", self.owed(state))
        self.assertIn("cause:DC2", self.owed(state))

    def test_every_cause_reaches_an_effect(self):
        data = novelty()
        data["problem_tree"]["effects"][0]["caused_by"] = ["DC1"]
        self.assertIn("tree:effects: cause DC2 has no effect", self.owed(self.write(data)))

    def test_an_effect_names_known_causes(self):
        data = novelty()
        data["problem_tree"]["effects"][0]["caused_by"] = ["DC1", "DC2", "DC9"]
        self.assertIn("tree:effects: EF1 names unknown cause DC9", self.owed(self.write(data)))

    def test_forbidden_openers_are_refused_in_the_problem_and_the_causes(self):
        for opener in ("Lack of data", "Absence of labels", "No method exists", "Need for scale",
                       "Requires more data", "There is no benchmark", "To improve accuracy"):
            with self.subTest(opener=opener):
                data = novelty()
                data["problem_tree"]["central"]["text"] = opener
                data["problem_tree"]["causes"][0]["text"] = opener
                owed = self.owed(self.write(data))
                self.assertIn("tree:central: must state a negative condition, not open with "
                              f"{opener.split()[0]!r}", owed)
                self.assertIn("tree:DC1: must state a negative condition, not open with "
                              f"{opener.split()[0]!r}", owed)

    def test_a_leading_article_does_not_hide_a_forbidden_opener(self):
        for text, word in (("The lack of labels", "The"), ("A lack of data", "A"), ("The need for tools", "The"),
                           ("There is a lack of data", "There")):
            with self.subTest(text=text):
                data = novelty()
                data["problem_tree"]["central"]["text"] = text
                self.assertIn(f"tree:central: must state a negative condition, not open with {word!r}",
                              self.owed(self.write(data)))

    def test_technical_wording_is_not_mistaken_for_a_forbidden_opener(self):
        for text in ("No-reference metrics degrade across sites.", "To date, error stays high.",
                     "Noisy channels.", "Non-stationary signals.", "Tomographic artifacts."):
            with self.subTest(text=text):
                data = novelty()
                data["problem_tree"]["central"]["text"] = text
                self.assertEqual(self.owed(self.write(data)), [])

    def test_an_effect_is_not_a_missing_solution(self):
        data = novelty()
        data["problem_tree"]["effects"][0]["text"] = "Lack of tools"
        self.assertIn("tree:EF1: must state a negative condition, not open with 'Lack'", self.owed(self.write(data)))

    def test_a_cause_needs_a_stable_id(self):
        data = novelty()
        data["problem_tree"]["causes"][0]["id"] = "C1"
        self.assertIn("tree:causes: id 'C1' must look like DC1", self.owed(self.write(data)))


class PillarTree(Workspace):
    def test_one_pillar_is_too_few(self):
        data = novelty()
        data["pillars"] = data["pillars"][:1]
        data["hypotheses"] = [{"id": "E1", "title": "Gain", "pillars": ["C1"]}]
        self.assertIn("tree:pillars: 1 pillar(s), needs at least 2", self.owed(self.write(data)))

    def test_two_pillars_cannot_share_an_id(self):
        data = novelty()
        data["pillars"][1]["id"] = "C1"
        self.assertIn("tree:pillars: duplicate id 'C1'", self.owed(self.write(data)))

    def test_two_hypotheses_cannot_share_an_id(self):
        data = novelty()
        data["hypotheses"][1]["id"] = "E1"
        self.assertIn("tree:hypotheses: duplicate id 'E1'", self.owed(self.write(data)))

    def test_a_pillar_owes_two_references(self):
        self.assertIn("pillar:C1", self.owed(self.write(novelty(), cited=False)))

    def test_a_hypothesis_owes_two_references(self):
        self.assertIn("hypothesis:E1", self.owed(self.write(novelty(), cited=False)))

    def test_a_hypothesis_names_its_pillars(self):
        data = novelty()
        del data["hypotheses"][0]["pillars"]
        self.assertIn("tree:hypotheses: E1 names no pillar", self.owed(self.write(data)))

    def test_a_hypothesis_names_known_pillars(self):
        data = novelty()
        data["hypotheses"][0]["pillars"] = ["C9"]
        self.assertIn("tree:hypotheses: E1 names unknown pillar C9", self.owed(self.write(data)))

    def test_every_pillar_reaches_a_hypothesis(self):
        data = novelty()
        data["hypotheses"] = [{"id": "E1", "title": "Gain", "pillars": ["C1"]}]
        self.assertIn("tree:pillars: C2 reaches no hypothesis", self.owed(self.write(data)))


class References(Workspace):
    def problems(self, state: dict, key: str) -> list[str]:
        return next(idea["problems"] for idea in state["ideas"] if idea["key"] == key)

    def test_q2_is_accepted(self):
        self.assertEqual(self.owed(self.write(novelty(), rank={"quartile": "Q2"})), [])

    def test_q3_is_refused(self):
        found = self.problems(self.write(novelty(), rank={"quartile": "Q3"}), "pillar:C1")
        self.assertIn("pillar:C1: '10.1000/a' is Q3, needs Q1 or Q2", found)

    def test_an_unverified_quartile_is_refused(self):
        found = self.problems(self.write(novelty(), rank={"quartile_source": "openalex-proxy"}), "cause:DC1")
        self.assertIn("cause:DC1: '10.1000/a' has no SJR quartile", found)

    def test_a_conference_paper_is_refused(self):
        found = self.problems(self.write(novelty(), rank={"work_type": "proceedings-article"}), "problem:central")
        self.assertIn("problem:central: '10.1000/a' is not a journal article", found)

    def test_a_reference_of_exactly_four_years_is_accepted(self):
        self.assertEqual(self.owed(self.write(novelty(), year=THIS_YEAR - 4)), [])

    def test_a_reference_older_than_four_years_is_refused(self):
        found = self.problems(self.write(novelty(), year=THIS_YEAR - 5), "hypothesis:E1")
        self.assertIn(f"hypothesis:E1: '10.1000/a' is from {THIS_YEAR - 5}, needs {THIS_YEAR - 4} or later", found)

    def test_a_published_year_in_the_rank_wins_over_the_pool(self):
        self.assertEqual(self.owed(self.write(novelty(), year=THIS_YEAR - 9, rank={"year": THIS_YEAR - 1})), [])

    def test_an_infinite_year_never_raises(self):
        self.write(novelty())
        path = self.root / "sota-pool" / "journal-ranks.json"
        path.write_text(path.read_text().replace('"quartile": "Q1"', '"quartile": "Q1", "year": 1e999'))
        self.assertIn("pillar:C1", self.owed(citations.state(self.root)) + ["pillar:C1"])

    def test_a_reference_without_a_rank_is_refused(self):
        self.write(novelty())
        (self.root / "sota-pool" / "journal-ranks.json").unlink()
        found = self.problems(citations.state(self.root), "pillar:C1")
        self.assertIn("pillar:C1: '10.1000/a' has no SJR quartile", found)

    def test_a_layer_keeps_the_old_rule(self):
        data = {"novelty": novelty(), "concept_map": {"layers": [{"name": "Encoder"}]}}
        self.write(novelty(), year=THIS_YEAR - 9, rank={"quartile": "Q4"})
        (self.root / ".papersmith" / "model_spec.json").write_text(json.dumps(data))
        ideas = json.loads((self.root / ".papersmith" / "citations.json").read_text())
        ideas["ideas"]["layer:Encoder"] = [{"id": i, "why": "Foundation."} for i in self.ids]
        (self.root / ".papersmith" / "citations.json").write_text(json.dumps(ideas))
        self.assertEqual(self.problems(citations.state(self.root), "layer:Encoder"), [])

    def test_the_cap_of_five_still_holds(self):
        self.ids = [f"10.1000/{n}" for n in range(6)]
        found = self.problems(self.write(novelty()), "pillar:C1")
        self.assertIn("pillar:C1: 6 citation(s), needs 2 to 5", found)


class ExistingBehavior(Workspace):
    def test_problems_without_ranks_keeps_its_answer(self):
        pool = {citations.normalize(i): {"identifier": i} for i in self.ids}
        entries = [{"id": i, "why": "Supports it."} for i in self.ids]
        self.assertEqual(citations.problems("pillar:P1", entries, pool), [])

    def test_a_workspace_with_no_ideas_owes_no_tree(self):
        state = citations.state(self.root)
        self.assertEqual(state["stages"]["proposal"], {"ideas": 0, "cited": 0, "owed": []})


class Cli(Workspace):
    def run_cli(self, *args: str) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = citations_cli.main([*args, "--root", str(self.root)])
        return code, json.loads(out.getvalue())

    def sjr(self) -> Path:
        path = self.root / "scimagojr-2025.csv"
        path.write_text("Title;Issn;SJR;SJR Best Quartile;Categories;Publisher\n"
                        "Good Journal;12345678;2,1;Q1;Neuroscience (Q1);Pub\n"
                        "Weak Journal;87654321;0,2;Q3;Neuroscience (Q3);Pub\n", encoding="utf-8")
        return path

    def rank(self, works: dict) -> tuple[int, dict, dict]:
        with mock.patch.object(citations_cli, "_crossref", side_effect=works.get):
            code, body = self.run_cli("rank", "--sjr", str(self.sjr()))
        written = self.root / "sota-pool" / "journal-ranks.json"
        return code, body, json.loads(written.read_text()) if written.is_file() else {}

    def test_check_fails_while_only_the_tree_owes(self):
        data = novelty()
        data["pillars"].append({"id": "C3", "name": "Unlinked"})
        self.write(data)
        ideas = json.loads((self.root / ".papersmith" / "citations.json").read_text())
        ideas["ideas"]["pillar:C3"] = [{"id": i, "why": "Supports it."} for i in self.ids]
        (self.root / ".papersmith" / "citations.json").write_text(json.dumps(ideas))
        code, body = self.run_cli("check")
        self.assertEqual((code, body["ok"], body["error"]), (1, False, "SOTA_CITATIONS_OWED"))
        self.assertEqual(body["owed"], [])
        self.assertEqual(body["trees"], ["tree:pillars: C3 reaches no hypothesis"])

    def test_rank_records_the_sjr_quartile_of_a_journal_article(self):
        self.write(novelty())
        code, body, written = self.rank({"10.1000/a": {"type": "journal-article", "issn": ["1234-5678"], "year": 2024},
                                         "10.1000/b": {"type": "journal-article", "issn": ["8765-4321"], "year": 2023}})
        self.assertEqual((code, body["ok"], body["ranked"], body["unresolved"]), (0, True, 2, []))
        self.assertEqual(written["ranks"]["10.1000/a"],
                         {"work_type": "journal-article", "issn": ["1234-5678"], "year": 2024, "quartile": "Q1",
                          "quartile_source": "sjr", "sjr_year": 2025})
        self.assertEqual(written["ranks"]["10.1000/b"]["quartile"], "Q3")

    def test_rank_leaves_a_journal_outside_the_table_without_quartile(self):
        self.write(novelty())
        _, _, written = self.rank({"10.1000/a": {"type": "journal-article", "issn": ["0000-0000"], "year": 2024},
                                   "10.1000/b": {"type": "proceedings-article", "issn": [], "year": 2024}})
        self.assertEqual((written["ranks"]["10.1000/a"]["quartile"], written["ranks"]["10.1000/a"]["quartile_source"]),
                         (None, "unknown"))
        self.assertEqual(written["ranks"]["10.1000/b"]["work_type"], "proceedings-article")

    def test_rank_reports_what_crossref_did_not_answer(self):
        self.write(novelty())
        (self.root / "sota-pool" / "journal-ranks.json").unlink()
        code, body, written = self.rank({"10.1000/a": {"type": "journal-article", "issn": ["1234-5678"], "year": 2024}})
        self.assertEqual((code, body["ranked"], body["unresolved"]), (0, 1, ["10.1000/b"]))
        self.assertNotIn("10.1000/b", written["ranks"])

    def test_rank_skips_a_preprint_without_a_doi(self):
        self.ids = ["10.1000/a", "arXiv:2008.08605"]
        self.write(novelty())
        code, body, written = self.rank({"10.1000/a": {"type": "journal-article", "issn": ["1234-5678"], "year": 2024}})
        self.assertEqual((code, body["skipped"], body["unresolved"]), (0, ["arXiv:2008.08605"], []))
        self.assertEqual(list(written["ranks"]), ["10.1000/a"])

    def test_rank_keeps_the_rank_of_what_crossref_did_not_answer(self):
        self.write(novelty())
        code, body, written = self.rank({})
        self.assertEqual((code, body["ranked"], body["unresolved"]), (0, 0, self.ids))
        self.assertEqual(written["ranks"]["10.1000/a"]["quartile"], "Q1")
        self.assertEqual(self.owed(citations.state(self.root)), [])

    def test_rank_refreshes_a_rank_crossref_answers(self):
        self.write(novelty())
        _, _, written = self.rank({"10.1000/a": {"type": "journal-article", "issn": ["8765-4321"], "year": 2024}})
        self.assertEqual(written["ranks"]["10.1000/a"]["quartile"], "Q3")
        self.assertEqual(written["ranks"]["10.1000/b"]["quartile"], "Q1")

    def test_a_malformed_crossref_answer_is_unresolved(self):
        for payload in (b'{"message": []}', b'{"message": {"issued": {"date-parts": [[]]}}}', b"not json"):
            with self.subTest(payload=payload):
                response = mock.MagicMock()
                response.__enter__.return_value = io.BytesIO(payload)
                with mock.patch.object(citations_cli.urllib.request, "urlopen", return_value=response):
                    work = citations_cli._crossref("10.1000/a")
                self.assertTrue(work is None or work["year"] is None)

    def test_check_keeps_its_message_when_no_tree_owes(self):
        (self.root / "experiments").mkdir()
        (self.root / "experiments" / "experiments-x-v01.md").write_text("## Experiment [exp:E1]\n")
        _, body = self.run_cli("check")
        self.assertEqual(body["message"], "1 idea(s) owe 2 to 5 SOTA citations in .papersmith/citations.json")

    def test_rank_refuses_without_a_table(self):
        self.write(novelty())
        ranks = self.root / "sota-pool" / "journal-ranks.json"
        ranks.unlink()
        with mock.patch.dict("os.environ", {"PAPERSMITH_SJR_DIR": str(self.root / "none")}):
            code, body = self.run_cli("rank")
        self.assertEqual((code, body["ok"], body["error"]), (1, False, "SJR_TABLE_ABSENT"))
        self.assertFalse(ranks.exists())


if __name__ == "__main__":
    unittest.main()
