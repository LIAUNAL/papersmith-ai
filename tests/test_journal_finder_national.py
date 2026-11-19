"""journal-finder --scope national: Colombian journals from the bundled Publindex IBN list.

The national scope ranks the journals of Minciencias' IBN - Publindex classification
(skills/journal-finder/data/publindex-ibn.json) by their lexical fit with the paper and by
the paper's own references. It reads no network: every provider URL points at a closed port.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from test_journal_finder import CLI, ROOT, SKILL_MD, JournalFinderCase, load_module

DATA = ROOT / "skills" / "journal-finder" / "data" / "publindex-ibn.json"
CLOSED = "http://127.0.0.1:9"
OFFLINE = {name: CLOSED for name in (
    "PAPERSMITH_OPENALEX_URL", "PAPERSMITH_CROSSREF_URL", "PAPERSMITH_PUBMED_URL", "PAPERSMITH_EUROPEPMC_URL",
    "PAPERSMITH_DOAJ_URL", "PAPERSMITH_SEMANTICSCHOLAR_URL", "PAPERSMITH_ASTA_URL")}

FIXTURE_LIST = {
    "schema": 1, "source": "https://scienti.minciencias.gov.co/publindex/#/revistasPublindex/clasificacion",
    "period": "2026-II", "resolution": "0707-2026", "valid_until": "2099-12-31",
    "categories": ["A1", "A2", "B", "C", "RC"],
    "journals": [
        {"publindex_id": 1, "name": "Revista de Neurociencia Computacional", "category": "A2",
         "issn": ["1111-1111"], "institutions": ["UNIVERSIDAD UNO"], "homepage_url": "https://uno.example/rnc",
         "scope": "Publica investigación en electroencefalografía, aprendizaje profundo y clasificación de "
                  "señales cerebrales."},
        {"publindex_id": 2, "name": "Boletín de Historia Natural", "category": "A1",
         "issn": ["2222-2222"], "institutions": ["UNIVERSIDAD DOS"], "homepage_url": "https://dos.example/bhn",
         "scope": "Entomología, ornitología y ecología de los bosques andinos."},
        {"publindex_id": 3, "name": "Ingeniería y Señales", "category": "B",
         "issn": ["3333-3333"], "institutions": ["UNIVERSIDAD TRES"], "homepage_url": None,
         "scope": "Procesamiento de señales, clasificación de patrones, electrónica e ingeniería eléctrica.",
         # like the bundled list, where 514 of 515 journals carry their OpenAlex topics (English)
         "openalex": {"topics": [{"name": "Image Processing Hardware", "subfield": "Electrical and Electronic Engineering",
                                  "field": "Engineering"}]}},
        {"publindex_id": 4, "name": "Revista Reconocida de Educación", "category": "C",
         "issn": ["4444-4444"], "institutions": ["UNIVERSIDAD CUATRO"], "homepage_url": None,
         "scope": "Pedagogía y didáctica."},
    ],
}

PAPER = r"""\documentclass{article}
\title{Deep learning classification of electroencephalography signals}
\begin{document}
\maketitle
\begin{abstract}
We classify electroencephalography signals with deep learning and compare signal processing pipelines.
\end{abstract}
\begin{keywords}
electroencephalography; deep learning; classification; signals
\end{keywords}
\end{document}
"""


class NationalCase(JournalFinderCase):
    def setUp(self):
        super().setUp()
        (self.workspace / "paper" / "main.tex").write_text(PAPER, encoding="utf-8")
        self.list_file = self.tmp / "publindex.json"
        self.write_list(FIXTURE_LIST)

    def write_list(self, document: dict) -> None:
        self.list_file.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    def national(self, *extra: str, list_file: Path | None = None) -> "object":
        env = {**OFFLINE, "PAPERSMITH_PUBLINDEX_FILE": str(list_file or self.list_file)}
        return self.run_cli("search", "--workspace", str(self.workspace), "--scope", "national", *extra,
                            extra_env=env)

    def written(self) -> dict:
        return json.loads(self.out_file.read_text(encoding="utf-8"))


class NationalSearchTests(NationalCase):
    def test_national_scope_ranks_the_publindex_list_without_network(self):
        result = self.national()
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        doc = self.written()
        self.assertEqual(doc["scope"], "national")
        self.assertEqual(doc["source"], "publindex")
        self.assertEqual(doc["providers"]["metadata"], ["publindex"])
        self.assertEqual(doc["providers"]["quartile"], "publindex")
        self.assertEqual(doc["publindex"]["period"], "2026-II")
        self.assertEqual(doc["publindex"]["resolution"], "0707-2026")
        names = [c["display_name"] for c in doc["candidates"]]
        self.assertEqual(names[0], "Revista de Neurociencia Computacional")
        self.assertEqual(names.index("Ingeniería y Señales"), 1)
        first = doc["candidates"][0]
        self.assertEqual(first["id"], "publindex:1")
        self.assertEqual(first["quartile_source"], "publindex")
        self.assertIsNone(first["quartile"])
        self.assertEqual(first["publindex"]["category"], "A2")
        self.assertEqual(first["publindex"]["period"], "2026-II")
        self.assertEqual(first["sources"], ["publindex"])
        self.assertEqual(first["issn_l"], "1111-1111")
        self.assertEqual(first["publisher"], "UNIVERSIDAD UNO")
        self.assertEqual(first["rank"], 1)
        self.assertGreater(first["fit_score"], doc["candidates"][1]["fit_score"])
        self.assertIn("electroencephalography", first["matched_terms"])
        self.assertEqual(first["review_time"]["source"], "none")
        # the national match ranks A1, A2 and B journals only
        self.assertEqual(doc["quartiles"], ["A1", "A2", "B"])
        self.assertNotIn("Revista Reconocida de Educación", names)
        self.assertEqual(doc["excluded_reasons"]["category_range"], 1)
        self.assertEqual(doc["quartile_source_summary"], {"publindex": len(doc["candidates"])})
        # stdout carries the same document
        self.assertTrue(result.json["ok"])
        self.assertEqual(result.json["scope"], "national")

    def test_journals_without_topical_evidence_are_left_out_not_ranked_last(self):
        doc = (self.national(), self.written())[1]
        scores = [c["fit_score"] for c in doc["candidates"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        names = [c["display_name"] for c in doc["candidates"]]
        self.assertEqual(names, ["Revista de Neurociencia Computacional", "Ingeniería y Señales"])
        self.assertEqual(doc["excluded_reasons"]["off_topic"], 1)  # the natural-history bulletin
        self.assertTrue(all(c["fit_score"] > 0 for c in doc["candidates"]))

    def test_categories_range_keeps_only_those_categories(self):
        result = self.national("--categories", "A1-A2")
        self.assertEqual(result.code, 0, result.stdout)
        doc = self.written()
        self.assertEqual({c["publindex"]["category"] for c in doc["candidates"]}, {"A2"})
        self.assertEqual(doc["quartiles"], ["A1", "A2"])
        self.assertEqual(doc["excluded_reasons"]["category_range"], 2)
        # the A1 natural-history bulletin is in range but off topic
        self.assertEqual(doc["excluded_reasons"]["off_topic"], 1)
        self.assertEqual(doc["excluded_count"], 3)
        self.assertEqual(doc["filters"]["categories"], ["A1", "A2"])

    def test_one_category_and_lowercase_are_accepted(self):
        result = self.national("--categories", "b")
        self.assertEqual(result.code, 0, result.stdout)
        self.assertEqual([c["display_name"] for c in self.written()["candidates"]], ["Ingeniería y Señales"])

    def test_a_bad_category_range_is_refused_and_writes_nothing(self):
        for bad in ("Q1", "B-A1", "A3", "", "A1-", "C", "RC", "A1-C", "B-RC"):
            with self.subTest(bad=bad):
                result = self.national("--categories", bad)
                self.assertEqual(result.code, 2, result.stdout)
                self.assertEqual(result.json["error"], "CATEGORY_RANGE_INVALID")
                self.assertFalse(self.out_file.exists())

    def test_limit_applies(self):
        self.assertEqual(self.national("--limit", "2").code, 0)
        self.assertEqual(len(self.written()["candidates"]), 2)

    def test_a_journal_cited_in_refs_bib_counts(self):
        (self.workspace / "paper" / "refs.bib").write_text(
            "@article{a, title={X}, journal={Ingenieria y Senales}, year={2024}}\n"
            "@article{b, title={Y}, journal={Boletin de Historia Natural}, year={2023}}\n", encoding="utf-8")
        self.assertEqual(self.national().code, 0)
        doc = self.written()
        by_name = {c["display_name"]: c for c in doc["candidates"]}
        self.assertEqual(by_name["Ingeniería y Señales"]["cited_in_paper_count"], 1)
        self.assertEqual(by_name["Revista de Neurociencia Computacional"]["cited_in_paper_count"], 0)
        # a journal the paper cites is on topic even when no term or subfield is shared
        self.assertEqual(by_name["Boletín de Historia Natural"]["cited_in_paper_count"], 1)

    def test_openalex_and_website_survey_data_fill_the_candidate(self):
        listing = json.loads(json.dumps(FIXTURE_LIST))
        education = listing["journals"][1]
        education["openalex"] = {"id": "S42", "is_oa": True, "is_in_doaj": True, "apc_usd": 0, "h_index": 7,
                                 "topics": [{"name": "Electroencephalography Signal Analysis", "subfield": "Neurology",
                                             "field": "Medicine"}]}
        education["review_time"] = {"surveyed_at": "2026-11-15", "status": "ok", "url": "https://cuatro.example",
                                    "measured": {"n": 9, "median_days": 120, "p25_days": 90, "p75_days": 200,
                                                 "accept_median_days": None, "years": [2026]},
                                    "declared": [{"quote": "Review takes 8 weeks", "url": "https://cuatro.example/about"}]}
        listing["journals"][2]["review_time"] = {"surveyed_at": "2026-11-15", "status": "no-dates",
                                                 "measured": {"n": 3, "median_days": 50}, "declared": []}
        listing["journals"][0]["review_time"] = {"surveyed_at": "2026-11-15", "status": "ok",
                                                 "measured": {"n": 8, "median_days": 2, "p25_days": 1, "p75_days": 4},
                                                 "declared": []}
        self.write_list(listing)
        self.assertEqual(self.national().code, 0)
        by_name = {c["display_name"]: c for c in self.written()["candidates"]}
        filled = by_name["Boletín de Historia Natural"]
        self.assertEqual((filled["openalex_id"], filled["is_oa"], filled["is_in_doaj"], filled["apc_usd"],
                          filled["h_index"]), ("S42", True, True, 0, 7))
        self.assertEqual(filled["topics"], ["Electroencephalography Signal Analysis"])
        self.assertIn("electroencephalography", filled["matched_terms"])  # English topic names are matched too
        review = filled["review_time"]
        self.assertEqual((review["source"], review["n"], review["median_days"], review["p25_days"], review["p75_days"]),
                         ("journal-website", 9, 120, 90, 200))
        self.assertEqual(review["basis"], "submission-to-publication")
        self.assertEqual(review["declared"], [{"quote": "Review takes 8 weeks", "url": "https://cuatro.example/about"}])
        few = by_name["Ingeniería y Señales"]["review_time"]
        self.assertEqual((few["source"], few["n"], few["median_days"], few["survey_status"]), ("none", 3, None, "no-dates"))
        # a peer-reviewed journal does not publish within days of submission: OJS loaded the article later
        quick = by_name["Revista de Neurociencia Computacional"]["review_time"]
        self.assertEqual((quick["source"], quick["median_days"], quick["survey_status"], quick["measured_median_days"],
                          quick["n"]), ("none", None, "implausible-dates", 2, 8))

    def test_unsurveyed_journal_reads_not_surveyed(self):
        self.assertEqual(self.national().code, 0)
        review = {c["display_name"]: c for c in self.written()["candidates"]}["Ingeniería y Señales"]["review_time"]
        self.assertEqual((review["source"], review["survey_status"]), ("none", "not-surveyed"))

    def test_languages_the_journal_receives_ride_on_the_candidate(self):
        listing = json.loads(json.dumps(FIXTURE_LIST))
        listing["journals"][0]["languages"] = {
            "accepts": ["en", "es"], "basis": "declared",
            "published": {"shares": {"es": 0.7, "en": 0.3}, "works": 40, "since": "2023-01-01"},
            "declared": [{"quote": "Las contribuciones pueden ser escritas en español o inglés",
                          "url": "https://uno.example/about", "languages": ["en", "es"]}]}
        listing["journals"][2]["languages"] = {"accepts": ["es"], "basis": "published",
                                               "published": {"shares": {"es": 1.0}, "works": 12}, "declared": []}
        # on topic here, so the journal without language data is ranked and shown
        listing["journals"][1]["scope"] += " Clasificación de señales de electroencefalografía."
        self.write_list(listing)
        self.assertEqual(self.national().code, 0)
        by_name = {c["display_name"]: c for c in self.written()["candidates"]}
        both = by_name["Revista de Neurociencia Computacional"]["languages"]
        self.assertEqual((both["accepts"], both["basis"], both["spanish"], both["english"]),
                         (["en", "es"], "declared", True, True))
        self.assertEqual(both["published"], {"es": 0.7, "en": 0.3})
        self.assertEqual(both["declared"][0]["quote"], "Las contribuciones pueden ser escritas en español o inglés")
        spanish = by_name["Ingeniería y Señales"]["languages"]
        self.assertEqual((spanish["accepts"], spanish["basis"], spanish["spanish"], spanish["english"]),
                         (["es"], "published", True, False))
        unknown = by_name["Boletín de Historia Natural"]["languages"]
        self.assertEqual((unknown["accepts"], unknown["basis"], unknown["spanish"], unknown["english"]),
                         ([], "unknown", None, None))

    def test_the_bundled_a1_a2_b_journals_carry_their_languages(self):
        doc = json.loads(DATA.read_text(encoding="utf-8"))
        ranked = [j for j in doc["journals"] if j["category"] in ("A1", "A2", "B")]
        self.assertEqual(len(ranked), 174)
        self.assertTrue(all("languages" in j for j in ranked))
        self.assertGreater(sum(j["languages"]["basis"] != "unknown" for j in ranked), 150)

    def test_an_expired_list_adds_a_note(self):
        self.write_list({**FIXTURE_LIST, "valid_until": "2020-01-01"})
        self.assertEqual(self.national().code, 0)
        self.assertTrue(any("2020-01-01" in note and "fetch-publindex" in note for note in self.written()["notes"]))

    def test_an_unreadable_list_is_refused(self):
        self.list_file.write_text("{not json", encoding="utf-8")
        result = self.national()
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "PUBLINDEX_DATA_INVALID")

    def test_international_only_options_are_refused_with_the_national_scope(self):
        for extra in (("--quartiles", "Q1"), ("--oa-only",), ("--max-apc", "10"), ("--max-review-days", "30"),
                      ("--source", "crossref"), ("--include-unknown-quartile",), ("--no-cache",)):
            with self.subTest(extra=extra):
                result = self.national(*extra)
                self.assertEqual(result.code, 2, result.stdout)
                self.assertEqual(result.json["error"], "FILTER_INVALID")
                self.assertIn("--scope international", result.json["message"])

    def test_categories_are_refused_with_the_international_scope(self):
        result = self.run_cli("search", "--workspace", str(self.workspace), "--quartiles", "Q1",
                              "--categories", "A1", extra_env=OFFLINE)
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "FILTER_INVALID")
        self.assertIn("--scope national", result.json["message"])

    def test_international_still_requires_quartiles(self):
        for scope in ((), ("--scope", "international")):
            with self.subTest(scope=scope):
                result = self.run_cli("search", "--workspace", str(self.workspace), *scope, extra_env=OFFLINE)
                self.assertEqual(result.code, 2)
                self.assertEqual(result.json["error"], "USAGE")

    def test_status_reads_a_national_result(self):
        self.assertEqual(self.national().code, 0)
        result = self.run_cli("status", "--workspace", str(self.workspace))
        self.assertEqual(result.code, 0, result.stdout)
        self.assertEqual(result.json["candidates"]["count"], 2)
        self.assertEqual(result.json["candidates"]["scope"], "national")


class BundledListTests(unittest.TestCase):
    def test_the_bundled_list_is_the_2026_ibn(self):
        doc = json.loads(DATA.read_text(encoding="utf-8"))
        self.assertEqual(doc["period"], "2026-II")
        self.assertEqual(doc["resolution"], "0707-2026")
        self.assertEqual(doc["valid_until"], "2026-12-31")
        counts = {c: sum(j["category"] == c for j in doc["journals"]) for c in doc["categories"]}
        self.assertEqual(counts, {"A1": 12, "A2": 30, "B": 132, "C": 199, "RC": 142})
        for journal in doc["journals"]:
            self.assertTrue(journal["name"] and journal["issn"], journal)

    def test_the_cli_reads_the_bundled_list_by_default(self):
        module = load_module()
        self.assertEqual(Path(module.publindex_file()).resolve(), DATA.resolve())


class NationalSkillTextTests(unittest.TestCase):
    def test_the_skill_documents_the_national_scope(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        for phrase in ("--scope national", "--categories", "Publindex", "IBN", "publindex-ibn.json", "A1-B",
                       "fetch-publindex-languages.py", "languages.accepts",
                       "fetch-publindex.py", "category_range", "CATEGORY_RANGE_INVALID", "PUBLINDEX_DATA_INVALID"):
            self.assertIn(phrase, text, phrase)


ONE_WORD_JOURNAL = {"publindex_id": 5, "name": "Cuestiones de Teología", "category": "B", "issn": ["5555-5555"],
                    "institutions": ["UNIVERSIDAD CINCO"], "homepage_url": None,
                    "scope": "Teología pastoral y clasificación de textos sagrados."}


def _with_topics(document: dict, subfields: dict[int, list[str]]) -> dict:
    """The fixture list with OpenAlex topics whose subfields are given per publindex_id."""
    journals = []
    for journal in document["journals"]:
        topics = [{"name": f"{name} topic", "subfield": name, "field": "Field"}
                  for name in subfields.get(journal["publindex_id"], [])]
        journals.append({**journal, "openalex": {"topics": topics}} if topics else journal)
    return {**document, "journals": journals}


class SubfieldOpenAlex:
    """A stand-in OpenAlex answering `group_by=primary_topic.subfield.id` for any works search."""

    def __init__(self, groups):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import parse_qs, urlparse
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                params = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
                outer.requests.append(params)
                body = json.dumps({"meta": {"count": 100}, "group_by": groups}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/openalex"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class NationalTopicalFitTests(NationalCase):
    """Spec S2 of odd/tasks/journal-scope-and-fit.md: suggested journals match the paper's topic."""

    GROUPS = [{"key": "https://openalex.org/subfields/2805", "key_display_name": "Cognitive Neuroscience", "count": 70},
              {"key": "https://openalex.org/subfields/1711", "key_display_name": "Signal Processing", "count": 30}]

    def setUp(self):
        super().setUp()
        document = {**FIXTURE_LIST, "journals": FIXTURE_LIST["journals"] + [ONE_WORD_JOURNAL]}
        self.write_list(_with_topics(document, {1: ["Cognitive Neuroscience"], 2: ["Insect Science"],
                                                 3: ["Signal Processing"],
                                                 5: ["Religious studies"]}))
        self.openalex = SubfieldOpenAlex(self.GROUPS)
        self.addCleanup(self.openalex.close)

    def with_openalex(self, *extra):
        env = {**OFFLINE, "PAPERSMITH_PUBLINDEX_FILE": str(self.list_file),
               "PAPERSMITH_OPENALEX_URL": self.openalex.url, "PAPERSMITH_OPENALEX_MIN_INTERVAL": "0"}
        return self.run_cli("search", "--workspace", str(self.workspace), "--scope", "national", *extra,
                            extra_env=env)

    def test_the_paper_subfields_rank_the_journals_and_off_topic_ones_are_left_out(self):
        result = self.with_openalex()
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        doc = self.written()
        names = [c["display_name"] for c in doc["candidates"]]
        self.assertEqual(names, ["Revista de Neurociencia Computacional", "Ingeniería y Señales"])
        self.assertEqual(doc["excluded_reasons"]["off_topic"], 2)  # natural history and theology
        self.assertEqual(doc["query"]["subfields"][0], {"name": "Cognitive Neuroscience", "share": 0.7})
        self.assertIn("subfield_affinity", doc["query"]["scoring"]["active"])
        first = doc["candidates"][0]
        self.assertGreater(first["fit"]["subfield_affinity"], 0)
        self.assertTrue(self.openalex.requests)
        self.assertTrue(all(r.get("group_by") == "primary_topic.subfield.id" for r in self.openalex.requests))

    def test_the_subfield_profile_is_cached_in_the_workspace(self):
        self.assertEqual(self.with_openalex().code, 0)
        asked = len(self.openalex.requests)
        self.assertTrue((self.workspace / "paper" / ".journal-subfields.json").is_file())
        self.assertEqual(self.national().code, 0)  # every provider closed: the cached profile answers
        self.assertEqual(len(self.openalex.requests), asked)
        doc = self.written()
        self.assertEqual(doc["excluded_reasons"]["off_topic"], 2)
        self.assertEqual(doc["query"]["subfields"][0]["name"], "Cognitive Neuroscience")

    def test_without_openalex_one_shared_word_is_not_a_fit(self):
        result = self.national()
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        doc = self.written()
        names = [c["display_name"] for c in doc["candidates"]]
        self.assertNotIn("Cuestiones de Teología", names)  # shares only "clasificación" with the paper
        self.assertIn("Revista de Neurociencia Computacional", names)
        self.assertEqual(doc["query"]["subfields"], [])
        self.assertTrue(any("two distinct paper terms" in note for note in doc["notes"]))

    def test_each_scope_keeps_its_own_result_beside_the_latest_one(self):
        self.assertEqual(self.with_openalex().code, 0)
        scoped = self.workspace / "paper" / "journal-candidates-national.json"
        self.assertEqual(json.loads(scoped.read_text(encoding="utf-8")), self.written())


if __name__ == "__main__":
    unittest.main()
