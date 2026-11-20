"""journal-finder second stage (odd/tasks/journal-two-stage-match.md S1-S4).

After the first-stage ranking, the top N journals (--refine-top, default 5) each have their recent articles
like the paper sampled from OpenAlex; the paper and those articles get a lexical research profile
(approach, AI use, contribution kind, math depth) and the top N are re-ordered by refined_score."""
from __future__ import annotations

import json
import unittest

from test_journal_finder import FakeApi, JournalFinderCase
from test_journal_finder_national import FIXTURE_LIST, OFFLINE, NationalCase, SubfieldOpenAlex

QUANT_AI = ("We propose a deep learning method for electroencephalography decoding: a neural network trained on a "
            "dataset of 200 subjects reaches 0.88 accuracy under cross-validation with variational circuits.")
QUALITATIVE = ("A qualitative study of teachers based on interviews and focus groups; a thematic analysis "
               "describes their experience.")


def work(number: int, title: str, abstract: str) -> dict:
    index: dict[str, list[int]] = {}
    for position, word in enumerate(abstract.split()):
        index.setdefault(word, []).append(position)
    return {"id": f"https://openalex.org/W9{number}", "title": title, "publication_year": 2025,
            "doi": f"https://doi.org/10.9/{number}", "abstract_inverted_index": index}


def short(candidate: dict) -> str:
    return str(candidate["openalex_id"]).rstrip("/").rsplit("/", 1)[-1]


class InternationalRefinementTests(JournalFinderCase):
    def baseline(self, api: FakeApi) -> list[dict]:
        result = self.search("--no-cache")
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        self.assertNotIn("refinement", result.json["candidates"][0])
        self.assertFalse(api.hits("/openalex/works") and any(
            "primary_location.source.id" in r["params"].get("filter", "") for r in api.hits("/openalex/works")))
        return result.json["candidates"]

    def refined(self, *extra: str):
        result = self.search("--no-cache", "--refine-top", "5", *extra)
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        return result.json

    def test_the_top_journals_are_reordered_by_their_articles_like_the_paper(self):
        api = self.start_api()
        first, second = self.baseline(api)[:2]
        api.source_works = {short(first): [work(1, "Rural teachers", QUALITATIVE), work(2, "Schools", QUALITATIVE)],
                            short(second): [work(3, "EEG decoding with quantum circuits", QUANT_AI),
                                            work(4, "Neural decoding of EEG", QUANT_AI)]}
        doc = self.refined()
        by_id = {short(c): c for c in doc["candidates"]}
        good, bad = by_id[short(second)], by_id[short(first)]
        self.assertGreater(good["refinement"]["style_match"], bad["refinement"]["style_match"])
        self.assertEqual(good["refinement"]["status"], "similar")
        self.assertEqual(good["refinement"]["works_sampled"], 2)
        self.assertEqual(good["refinement"]["works"][0]["approach"], "quantitative")
        self.assertTrue(good["refinement"]["works"][0]["ai"])
        self.assertEqual(bad["refinement"]["shares"]["approach"], {"qualitative": 1.0})
        self.assertEqual((good["fit_score"], bad["fit_score"]), (second["fit_score"], first["fit_score"]),
                         "the first-stage fit is kept as it was")
        head = doc["candidates"][:5]
        keys = [c["refined_score"] if c["refined_score"] is not None else c["fit_score"] / head_best(head)
                for c in head]
        self.assertEqual(keys, sorted(keys, reverse=True))
        self.assertLess(good["rank"], bad["rank"])
        self.assertEqual([c["rank"] for c in doc["candidates"]], list(range(1, len(doc["candidates"]) + 1)))
        refinement = doc["query"]["refinement"]
        self.assertTrue(refinement["applied"])
        self.assertEqual(refinement["top"], 5)
        self.assertEqual(refinement["paper"]["approach"], "quantitative")
        self.assertTrue(refinement["paper"]["ai"])
        self.assertTrue(all("refinement" not in c for c in doc["candidates"][5:]))
        source_calls = [r for r in api.hits("/openalex/works")
                        if "primary_location.source.id" in r["params"].get("filter", "")]
        self.assertTrue(all("type:article" in r["params"]["filter"] for r in source_calls))
        self.assertTrue(any(r["params"].get("search", "").startswith('"') for r in source_calls),
                        "the paper's key phrases pick the similar articles")
        self.assertTrue(any("Second stage" in note for note in doc["notes"]))

    def test_a_journal_with_no_similar_article_is_read_from_its_latest(self):
        api = self.start_api()
        first = self.baseline(api)[0]
        api.source_works = {short(first): [work(1, "EEG decoding", QUANT_AI)]}
        api.source_misses = {short(first)}
        doc = self.refined()
        entry = next(c for c in doc["candidates"] if short(c) == short(first))
        self.assertEqual(entry["refinement"]["status"], "latest")
        self.assertEqual(entry["refinement"]["works_sampled"], 1)
        latest = [r for r in api.hits("/openalex/works")
                  if short(first) in r["params"].get("filter", "") and "search" not in r["params"]]
        self.assertEqual(latest[0]["params"]["sort"], "publication_date:desc")

    def test_a_journal_openalex_does_not_answer_for_keeps_its_place_with_a_note(self):
        api = self.start_api()
        first = self.baseline(api)[0]
        api.script = {}
        api.source_works = {}
        original = api.answer

        def failing(path, params):
            if short(first) in params.get("filter", ""):
                return 503, {"error": "down"}
            return original(path, params)

        api.answer = failing
        doc = self.refined()
        entry = next(c for c in doc["candidates"] if short(c) == short(first))
        self.assertEqual(entry["refinement"]["status"], "unavailable")
        self.assertIsNone(entry["refinement"]["style_match"])
        self.assertIsNone(entry["refined_score"])
        self.assertEqual(doc["query"]["refinement"]["unavailable"], 1)
        self.assertTrue(any("did not answer the similar-papers sample" in n for n in doc["notes"]))

    def test_the_recorded_contribution_type_sets_the_paper_kind(self):
        self.start_api()
        (self.workspace / ".papersmith").mkdir()
        (self.workspace / ".papersmith" / "model_spec.json").write_text(
            json.dumps({"contribution_type": {"type": "Use-Inspired", "why": "clinical need"}}), encoding="utf-8")
        paper = self.refined()["query"]["refinement"]["paper"]
        self.assertEqual((paper["kind"], paper["kind_basis"]), ("use-inspired", "contribution_type"))

    def test_without_openalex_the_second_stage_is_skipped_with_a_note(self):
        api = self.start_api()
        doc = self.refined("--source", "crossref", "--include-unknown-quartile")
        self.assertTrue(doc["candidates"])
        self.assertFalse(doc["query"]["refinement"]["applied"])
        self.assertTrue(any(n.startswith("Second stage skipped") for n in doc["notes"]))
        self.assertFalse(api.hits("/openalex/works"))

    def test_refine_top_out_of_range_is_refused(self):
        self.start_api()
        for value in ("11", "-1", "two"):
            result = self.search("--refine-top", value)
            self.assertEqual(result.code, 2, value)
            self.assertEqual(result.json["error"], "FILTER_INVALID", value)
        self.assertFalse(self.out_file.exists())

    def test_refine_top_zero_keeps_the_first_stage(self):
        api = self.start_api()
        result = self.search("--no-cache", "--refine-top", "0")
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        self.assertFalse(result.json["query"]["refinement"]["applied"])
        self.assertTrue(all("refinement" not in c for c in result.json["candidates"]))
        self.assertFalse(any("primary_location.source.id" in r["params"].get("filter", "")
                             for r in api.hits("/openalex/works")))


def head_best(head: list[dict]) -> float:
    return max(c["fit_score"] for c in head) or 1.0


class NationalRefinementTests(NationalCase):
    GROUPS = [{"key": "https://openalex.org/subfields/2805", "key_display_name": "Cognitive Neuroscience", "count": 70},
              {"key": "https://openalex.org/subfields/1711", "key_display_name": "Signal Processing", "count": 30}]

    def setUp(self):
        super().setUp()
        ids = {1: "S11", 3: "S33"}
        subfields = {1: "Cognitive Neuroscience", 3: "Signal Processing", 2: "Insect Science"}
        journals = []
        for journal in FIXTURE_LIST["journals"]:
            number = journal["publindex_id"]
            openalex = {"topics": [{"name": "t", "subfield": subfields[number], "field": "F"}]} \
                if number in subfields else {}
            if number in ids:
                openalex["id"] = ids[number]
            journals.append({**journal, "openalex": openalex} if openalex else journal)
        self.write_list({**FIXTURE_LIST, "journals": journals})
        eeg = ("Clasificación de electroencefalografía con deep learning: una red neuronal sobre señales "
               "cerebrales de 80 sujetos alcanza 0.9 de exactitud.")
        self.openalex = SubfieldOpenAlex(self.GROUPS, source_works={
            "S11": [work(1, "Experiencias docentes", QUALITATIVE), work(2, "Narrativas", QUALITATIVE)],
            "S33": [work(3, "Electroencefalografía y deep learning", eeg)]})
        self.addCleanup(self.openalex.close)

    def run_national(self, *extra):
        env = {**OFFLINE, "PAPERSMITH_PUBLINDEX_FILE": str(self.list_file),
               "PAPERSMITH_OPENALEX_URL": self.openalex.url, "PAPERSMITH_OPENALEX_MIN_INTERVAL": "0"}
        result = self.run_cli("search", "--workspace", str(self.workspace), "--scope", "national", *extra,
                              extra_env=env)
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        return self.written()

    def test_national_journals_are_reordered_by_their_articles_like_the_paper(self):
        before = self.run_national("--refine-top", "0")
        names = [c["display_name"] for c in before["candidates"]]
        self.assertEqual(names, ["Revista de Neurociencia Computacional", "Ingeniería y Señales"])
        after = self.run_national("--refine-top", "5")
        self.assertEqual([c["display_name"] for c in after["candidates"]],
                         ["Ingeniería y Señales", "Revista de Neurociencia Computacional"])
        engineering, neuro = after["candidates"]
        self.assertEqual(engineering["refinement"]["dimensions"]["ai"], 1.0)
        self.assertEqual(neuro["refinement"]["dimensions"]["ai"], 0.0)
        self.assertEqual(engineering["fit_score"], before["candidates"][1]["fit_score"])
        self.assertTrue(after["query"]["refinement"]["applied"])
        self.assertEqual(after["filters"]["refine_top"], 5)

    def test_offline_the_national_order_stays_and_says_why(self):
        result = self.national("--refine-top", "5")
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        doc = self.written()
        self.assertFalse(doc["query"]["refinement"]["applied"])
        self.assertTrue(all(c.get("refinement", {}).get("status") in ("unavailable", "no-record", None)
                            for c in doc["candidates"]))


class SecondStageDocsTests(unittest.TestCase):
    def test_the_skill_and_the_cli_help_document_the_second_stage(self):
        from test_journal_finder import CLI, SKILL_MD
        text = SKILL_MD.read_text(encoding="utf-8")
        for phrase in ("--refine-top", "refined_score", "style_match", "research_profile.py", "query.refinement",
                       "PAPERSMITH_JOURNAL_REFINE_TOP", "contribution_type", "quantitative", "qualitative", "mixed",
                       "use-inspired", "mathematical", "descriptive"):
            self.assertIn(phrase, text, phrase)
        cli = CLI.read_text(encoding="utf-8")
        for phrase in ("--refine-top", "PAPERSMITH_JOURNAL_REFINE_TOP", "refined_score"):
            self.assertIn(phrase, cli, phrase)


if __name__ == "__main__":
    unittest.main()
