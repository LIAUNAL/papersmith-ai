"""journal-finder: the skill, its CLI and the review-time estimate.

Everything network-shaped talks to a local fake HTTP server (threading
`http.server`) that serves canned OpenAlex, Crossref and PubMed answers from
`tests/fixtures/journal_finder/`; nothing here reaches the real services.

Fixture world (see the JSON files):

* S1001 Neural Fixtures Letters  -- proxy Q1 (citedness 9.0), SJR Q1 through its
  *second* ISSN, closed access, Crossref review times (n=6: 10..60 days).
* S1002 Open Signal Processing   -- proxy Q2 (6.0), not in the SJR file, OA/DOAJ,
  APC 1500, Crossref only 4 dated articles -> falls through to PubMed (n=6).
* S1003 Biomedical Fixture Reports -- proxy Q3 (3.0), OA, APC 3200, Crossref 404,
  PubMed only 3 dated articles -> `source: "none"`, `n: 3`.
* S1004 Obscure Quarterly        -- proxy Q4 (1.0) but SJR says Q2, no data anywhere.
* the field population (core journals of field 17) is 0.1 .. 10.0 in steps of 0.1,
  so a citedness of 9.0 has 10% of the field above it, 6.0 has 40%, 3.0 has 70%.
"""

from __future__ import annotations

import contextlib
import datetime
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "journal-finder"
SKILL_MD = SKILL_DIR / "SKILL.md"
CLI = SKILL_DIR / "scripts" / "journal_cli.py"
FIXTURES = ROOT / "tests" / "fixtures" / "journal_finder"

#: Environment variables that would change the CLI's behaviour; scrubbed per run.
SCRUBBED = (
    "PAPERSMITH_CONTACT_EMAIL", "NCBI_API_KEY", "OPENALEX_API_KEY", "PAPERSMITH_SJR_DIR",
    "PAPERSMITH_OPENALEX_URL", "PAPERSMITH_CROSSREF_URL", "PAPERSMITH_PUBMED_URL",
    "PAPERSMITH_HTTP_TIMEOUT", "PAPERSMITH_HTTP_RETRIES", "PAPERSMITH_HTTP_BACKOFF",
    "PAPERSMITH_JOURNAL_DEADLINE", "PAPERSMITH_JOURNAL_MAX_WORKS",
    "PAPERSMITH_OPENALEX_MIN_INTERVAL",
)


def load_module():
    spec = importlib.util.spec_from_file_location("journal_cli_under_test", CLI)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- fake server


class FakeApi:
    """One server standing in for OpenAlex, Crossref and PubMed.

    Routes by path prefix: `/openalex/...`, `/crossref/...`, `/pubmed/...`.
    `script` maps a request path to a list of statuses to answer with before
    the real answer (`[429]` fails the first call once).
    """

    def __init__(self, *, script: dict[str, list] | None = None, max_terms_matching: int | None = None,
                 or_count: int | None = None, topics: bool = False):
        self.max_terms_matching = max_terms_matching
        #: when set, a quoted-phrase (OR) works query matches this many works and returns none
        self.or_count = or_count
        #: attach OpenAlex `topics` to the matched works, by hosting source
        self.topics = topics
        self.cited = fixture("openalex_cited_works.json")
        self.requests: list[dict] = []
        self.lock = threading.Lock()
        self.script = {key: list(value) for key, value in (script or {}).items()}
        self.population = fixture("openalex_field_population.json")
        self.summaries = fixture("pubmed_esummary.json")
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def do_GET(self):
                parsed = urlparse(self.path)
                params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                entry = {"t": time.monotonic(), "path": parsed.path, "params": params,
                         "headers": dict(self.headers)}
                with api.lock:
                    api.requests.append(entry)
                    queued = api.script.get(parsed.path)
                    status = queued.pop(0) if queued else None
                if status is not None:
                    body = json.dumps({"error": "scripted"}).encode()
                    self.send_response(status)
                    self.send_header("Retry-After", "0")
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                code, payload = api.answer(parsed.path, params)
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    # -- URLs for the env overrides
    @property
    def env(self) -> dict[str, str]:
        base = f"http://127.0.0.1:{self.port}"
        return {
            "PAPERSMITH_OPENALEX_URL": f"{base}/openalex",
            "PAPERSMITH_CROSSREF_URL": f"{base}/crossref",
            "PAPERSMITH_PUBMED_URL": f"{base}/pubmed",
        }

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def hits(self, prefix: str) -> list[dict]:
        return [r for r in self.requests if r["path"].startswith(prefix)]

    # -- canned answers
    WORK_TOPICS = {"S1004": [("T3", 0.9)], "default": [("T1", 0.9), ("T2", 0.1)]}

    def _cited_works(self, wanted: str) -> dict:
        dois = {d.lower() for d in wanted.split("|") if d}
        assert len(dois) <= 50, f"DOI batch of {len(dois)} exceeds the 50 OpenAlex allows"
        results = [r for r in self.cited["results"] if r["doi"].split("doi.org/")[1].lower() in dois]
        return {"meta": {"count": len(results)}, "results": results}

    def _source_search(self, params: dict) -> dict:
        wanted = params["search"].strip().lower()
        results = [{"id": "https://openalex.org/S9999", "display_name": f"{params['search']} Supplement",
                    "type": "journal", "topics": []}]
        for target in sorted(FIXTURES.glob("openalex_source_S*.json")):
            record = json.loads(target.read_text(encoding="utf-8"))
            if record["display_name"].lower() == wanted:
                results.append(record)
        return {"meta": {"count": len(results)}, "results": results}

    def _with_topics(self, page: dict) -> dict:
        for work in page["results"]:
            sid = ((work.get("primary_location") or {}).get("source") or {}).get("id", "").rsplit("/", 1)[-1]
            work["topics"] = [{"id": f"https://openalex.org/{tid}", "display_name": f"Topic {tid}", "score": score}
                              for tid, score in self.WORK_TOPICS.get(sid, self.WORK_TOPICS["default"])]
        return page

    def answer(self, path: str, params: dict):
        if path == "/openalex/works":
            if params.get("filter", "").startswith("doi:"):
                return 200, self._cited_works(params["filter"][4:])
            if params.get("search", "").lstrip().startswith('"') and self.or_count is not None:
                return 200, {"meta": {"count": self.or_count}, "results": []}
            if int(params.get("page", "1")) > 1 or "zzqx" in params.get("search", ""):
                return 200, {"meta": {"count": 0}, "results": []}
            if self.max_terms_matching is not None and len(params.get("search", "").split()) > self.max_terms_matching:
                return 200, {"meta": {"count": 3}, "results": []}
            page = fixture("openalex_works_page1.json")
            per_page = int(params.get("per-page", "100"))
            page["results"] = page["results"][:per_page]
            return 200, self._with_topics(page) if self.topics else page
        if path == "/openalex/sources":
            if "search" in params:
                return 200, self._source_search(params)
            return 200, {"meta": {"count": self._count(params.get("filter", ""))}, "results": []}
        if path.startswith("/openalex/sources/"):
            sid = path.rsplit("/", 1)[1]
            target = FIXTURES / f"openalex_source_{sid}.json"
            if target.is_file():
                return 200, json.loads(target.read_text(encoding="utf-8"))
            return 404, {"error": "not found"}
        if path.startswith("/crossref/journals/") and path.endswith("/works"):
            issn = path.split("/")[3]
            target = FIXTURES / f"crossref_{issn}.json"
            if target.is_file():
                return 200, json.loads(target.read_text(encoding="utf-8"))
            return 404, {"status": "failed", "message": "Resource not found."}
        if path == "/pubmed/esearch.fcgi":
            term = params.get("term", "")
            issn = term.split("[")[0].strip('"')
            target = FIXTURES / f"pubmed_esearch_{issn}.json"
            if target.is_file():
                return 200, json.loads(target.read_text(encoding="utf-8"))
            return 200, {"esearchresult": {"count": "0", "idlist": []}}
        if path == "/pubmed/esummary.fcgi":
            wanted = [i for i in params.get("id", "").split(",") if i]
            result = {"uids": [i for i in wanted if i in self.summaries["result"]]}
            for uid in result["uids"]:
                result[uid] = self.summaries["result"][uid]
            return 200, {"result": result}
        return 404, {"error": "unrouted", "path": path}

    def _count(self, filter_text: str) -> int:
        assert "type:journal" in filter_text and "is_core:true" in filter_text, filter_text
        field = filter_text.split("topics.field.id:")[1].split(",")[0]
        values = self.population[field]
        for clause in filter_text.split(","):
            if clause.startswith("summary_stats.2yr_mean_citedness:>"):
                floor = float(clause.split(">")[1])
                return sum(1 for v in values if v > floor)
        return len(values)


# --------------------------------------------------------------------------- helpers


class Result:
    def __init__(self, completed: subprocess.CompletedProcess):
        self.code = completed.returncode
        self.stdout = completed.stdout
        self.stderr = completed.stderr
        try:
            self.json = json.loads(completed.stdout)
        except ValueError:
            self.json = None


class JournalFinderCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="journal-finder-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.sjr_dir = self.tmp / "sjr-cache"
        self.workspace = self.tmp / "ws"
        (self.workspace / "paper").mkdir(parents=True)
        shutil.copy(FIXTURES / "paper_main.tex", self.workspace / "paper" / "main.tex")
        self.api: FakeApi | None = None

    def start_api(self, **kwargs) -> FakeApi:
        self.api = FakeApi(**kwargs)
        self.addCleanup(self.api.close)
        return self.api

    def run_cli(self, *args: str, extra_env: dict | None = None, use_api: bool = True,
                timeout: int = 120) -> Result:
        env = {k: v for k, v in os.environ.items() if k not in SCRUBBED}
        env.update({
            "PAPERSMITH_SJR_DIR": str(self.sjr_dir),
            "PAPERSMITH_HTTP_BACKOFF": "0",
            "PAPERSMITH_OPENALEX_MIN_INTERVAL": "0",
            "PAPERSMITH_HTTP_RETRIES": "2",
            "HOME": str(self.tmp / "home"),
        })
        if use_api and self.api is not None:
            env.update(self.api.env)
        env.update(extra_env or {})
        completed = subprocess.run(
            [sys.executable, "-I", str(CLI), *args], capture_output=True, text=True,
            env=env, timeout=timeout)
        return Result(completed)

    def search(self, *extra: str, quartiles: str = "Q1-Q4", extra_env: dict | None = None) -> Result:
        return self.run_cli("search", "--workspace", str(self.workspace), "--quartiles", quartiles,
                            *extra, extra_env=extra_env)

    @property
    def out_file(self) -> Path:
        return self.workspace / "paper" / "journal-candidates.json"

    def import_fixture_sjr(self) -> None:
        result = self.run_cli("sjr-import", "--file", str(FIXTURES / "scimagojr-2019.csv"))
        self.assertEqual(result.code, 0, result.stdout + result.stderr)

    def tree_snapshot(self) -> dict[str, bytes]:
        return {str(p.relative_to(self.tmp)): p.read_bytes()
                for p in sorted(self.tmp.rglob("*")) if p.is_file()}

    def names(self, result: Result) -> list[str]:
        return [c["display_name"] for c in result.json["candidates"]]


# --------------------------------------------------------------------------- S1 skill


class SkillFileTests(unittest.TestCase):
    def setUp(self):
        self.text = SKILL_MD.read_text(encoding="utf-8")

    def test_frontmatter_matches_the_other_top_level_skills(self):
        self.assertTrue(self.text.startswith("---\n"))
        front = self.text.split("---", 2)[1]
        self.assertIn("name: journal-finder", front)
        description = next(line for line in front.splitlines() if line.startswith("description:"))
        self.assertTrue(description.startswith('description: "Trigger:'), description)
        self.assertTrue(description.endswith('"'))

    def test_the_skill_states_its_flow_refusals_and_what_it_never_does(self):
        for heading in ("## What this skill never does", "## Refusals"):
            self.assertIn(heading, self.text)
        for phrase in ("/journal-finder Q1-Q2", "paper/journal-candidates.md",
                       "openalex-proxy", "journal_cli.py", "never submits",
                       "declared by the journal"):
            self.assertIn(phrase, self.text, phrase)
        lowered = self.text.lower()
        for invented in ("quartile", "impact factor", "apc", "acceptance rate"):
            self.assertIn(invented, lowered)

    def test_every_refusal_code_the_cli_can_emit_is_documented(self):
        module = load_module()
        missing = [code for code in module.REFUSAL_CODES if f"`{code}`" not in self.text]
        self.assertEqual(missing, [])

    def test_the_skill_documents_the_three_fit_signals_and_the_formula(self):
        for phrase in ("cited_in_paper", "topic_overlap", "similar_works", "query.scoring", "refs.bib",
                       "phrases-or", "terms-and-relaxation", "fit_score ="):
            self.assertIn(phrase, self.text, phrase)
        module = load_module()
        for name, weight in module.FIT_WEIGHTS.items():
            self.assertIn(f"{weight:g} * {name}", self.text.replace("×", "*"), name)

    def test_every_verb_is_documented(self):
        for verb in ("search", "sjr-import", "status"):
            self.assertIn(f"journal_cli.py {verb}", self.text)


# --------------------------------------------------------------------------- units


class RangeAndDateUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_quartile_range_parsing(self):
        parse = self.mod.parse_quartile_range
        self.assertEqual(parse("Q1"), (1, 1))
        self.assertEqual(parse("q2-q3"), (2, 3))
        self.assertEqual(parse("Q1-Q4"), (1, 4))
        self.assertEqual(parse(" Q3 - Q4 "), (3, 4))
        self.assertEqual(parse("Q2-3"), (2, 3))

    def test_quartile_range_refusals(self):
        for bad in ("", "Q0", "Q5", "Q3-Q2", "Q1,Q3", "Q1-Q2-Q3", "2", "Q", "all", "Q1-"):
            with self.subTest(bad=bad):
                with self.assertRaises(self.mod.Refusal) as ctx:
                    self.mod.parse_quartile_range(bad)
                self.assertEqual(ctx.exception.code, "QUARTILE_RANGE_INVALID")

    def test_date_formats_of_both_sources(self):
        d = self.mod.parse_date
        want = datetime.date(2024, 3, 21)
        for text in ("21 March 2024", "21 Mar 2024", "2024-03-21", "2024/03/21",
                     "2024/03/21 00:00", "2024-03-21T10:11:12Z", "March 21, 2024", "  21 March 2024 "):
            with self.subTest(text=text):
                self.assertEqual(d(text), want)
        for text in ("", "soon", "2024-13-45", None, "2024"):
            with self.subTest(text=text):
                self.assertIsNone(d(text))

    def test_percentile_and_summary_arithmetic(self):
        summary = self.mod.summarize_days
        self.assertEqual(summary([10, 20, 30, 40, 50, 60]), (35.0, 22.5, 47.5))
        self.assertEqual(summary([60, 10, 30, 20, 50]), (30.0, 20.0, 50.0))
        self.assertEqual(summary([7]), (7.0, 7.0, 7.0))
        self.assertEqual(self.mod.percentile([1.0, 2.0, 3.0, 4.0], 0.5), 2.5)

    def test_issn_normalisation(self):
        n = self.mod.normalize_issn
        self.assertEqual(n("1523-2867"), "15232867")
        self.assertEqual(n(" 1111-111x "), "1111111X")
        self.assertEqual(n("15232867"), "15232867")
        self.assertEqual(n(""), "")
        self.assertEqual(n(None), "")

    def test_proxy_quartile_boundaries(self):
        q = self.mod.proxy_quartile
        self.assertEqual(q(0.0), "Q1")
        self.assertEqual(q(0.10), "Q1")
        self.assertEqual(q(0.2499), "Q1")
        self.assertEqual(q(0.25), "Q2")
        self.assertEqual(q(0.49), "Q2")
        self.assertEqual(q(0.50), "Q3")
        self.assertEqual(q(0.75), "Q4")
        self.assertEqual(q(1.0), "Q4")

    def test_pubmed_calls_are_spaced_by_the_rate_limiter(self):
        now = [0.0]
        slept: list[float] = []

        def sleep(seconds: float) -> None:
            slept.append(seconds)
            now[0] += seconds

        limiter = self.mod.RateLimiter(1 / 3, clock=lambda: now[0], sleep=sleep)
        stamps = []
        for _ in range(7):
            limiter.wait()
            stamps.append(now[0])
        gaps = [b - a for a, b in zip(stamps, stamps[1:])]
        self.assertTrue(all(g >= 1 / 3 - 1e-9 for g in gaps), gaps)
        # never more than three calls inside any one second
        for i in range(len(stamps) - 3):
            self.assertGreaterEqual(stamps[i + 3] - stamps[i], 1.0 - 1e-9)


class ProfileUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def make(self, main_tex: str | None = None, sections: dict[str, str] | None = None) -> Path:
        root = Path(tempfile.mkdtemp(prefix="jf-profile-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "paper").mkdir()
        if main_tex is not None:
            (root / "paper" / "main.tex").write_text(main_tex, encoding="utf-8")
        for name, text in (sections or {}).items():
            target = root / "paper" / "sections" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        return root

    def test_profile_from_main_tex(self):
        root = self.make((FIXTURES / "paper_main.tex").read_text(encoding="utf-8"))
        profile = self.mod.extract_profile(root)
        self.assertEqual(profile["title"], "Hybrid Quantum-Classical Networks with Data Re-Uploading "
                                           "for Interpretable EEG Biomarker Discovery in ADHD")
        self.assertIn("variational circuits under circular data re-uploading", profile["abstract"])
        self.assertIn("motivating objective biomarkers", profile["abstract"])
        self.assertNotIn("paper-writing block", profile["abstract"])
        self.assertNotIn("$", profile["abstract"])
        self.assertEqual(profile["keywords"][0], "Quantum Machine Learning")
        self.assertIn("Electroencephalography (EEG)", profile["keywords"])
        self.assertEqual(len(profile["keywords"]), 5)

    def test_keyword_block_variants(self):
        base = "\\title{T}\\begin{document}\\begin{abstract}A short abstract here.\\end{abstract}%s\\end{document}"
        cases = {
            "\\keywords{alpha beta, gamma; delta}": ["alpha beta", "gamma", "delta"],
            "\\begin{keyword}one \\sep two \\sep three\\end{keyword}": ["one", "two", "three"],
            "\\begin{IEEEkeywords}red, green\\end{IEEEkeywords}": ["red", "green"],
        }
        for block, expected in cases.items():
            with self.subTest(block=block):
                root = self.make(base % block)
                self.assertEqual(self.mod.extract_profile(root)["keywords"], expected)

    def test_title_only_or_abstract_only_is_enough(self):
        only_title = self.make("\\title{A lonely title}\n")
        self.assertEqual(self.mod.extract_profile(only_title)["title"], "A lonely title")
        only_abstract = self.make("\\begin{abstract}Just an abstract of some length.\\end{abstract}")
        self.assertEqual(self.mod.extract_profile(only_abstract)["title"], "")

    def test_falls_back_to_rendered_sections(self):
        root = self.make("\\documentclass{article}\n\\begin{document}\\end{document}\n", {
            "title.md": "# Graph neural networks for sleep staging\n",
            "abstract.tex": "\\begin{abstract}We stage sleep with graph networks.\\end{abstract}",
        })
        profile = self.mod.extract_profile(root)
        self.assertEqual(profile["title"], "Graph neural networks for sleep staging")
        self.assertIn("stage sleep with graph networks", profile["abstract"])

    def test_paper_absent(self):
        for main in (None, "\\documentclass{article}\n\\begin{document}\\end{document}\n",
                     "\\title{}\n\\begin{abstract}\n\\end{abstract}\n"):
            with self.subTest(main=main):
                root = self.make(main)
                with self.assertRaises(self.mod.Refusal) as ctx:
                    self.mod.extract_profile(root)
                self.assertEqual(ctx.exception.code, "PAPER_ABSENT")

    def test_terms_come_from_keywords_title_and_abstract_not_the_body(self):
        root = self.make((FIXTURES / "paper_main.tex").read_text(encoding="utf-8"))
        profile = self.mod.extract_profile(root)
        terms = self.mod.build_terms(profile)
        self.assertLessEqual(len(terms), self.mod.MAX_TERMS)
        self.assertEqual(len(terms), len(set(terms)))
        self.assertIn("quantum", terms)
        self.assertIn("eeg", terms)
        for stop in ("the", "with", "for", "and", "under"):
            self.assertNotIn(stop, terms)
        self.assertNotIn("zebra", terms)


class SjrUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_real_scimago_format_is_read(self):
        table = self.mod.read_sjr(FIXTURES / "scimagojr-2019.csv")
        self.assertEqual(table.rows, 5)
        hit = table.lookup(["1111-111X", "2222-2222"])
        self.assertEqual(hit["quartile"], "Q1")
        self.assertAlmostEqual(hit["value"], 2.345)
        self.assertEqual(hit["categories"], [{"name": "Artificial Intelligence", "quartile": "Q1"},
                                             {"name": "Software", "quartile": "Q2"}])
        # a quoted multi-ISSN cell matches on any of its ISSNs
        self.assertEqual(table.lookup(["6666-6666"])["quartile"], "Q2")
        self.assertEqual(table.lookup(["5555-5555"])["categories"][1],
                         {"name": "General Medicine", "quartile": "Q3"})
        # a category name that itself contains parentheses survives
        self.assertEqual(table.lookup(["5555-5555"])["categories"][0]["name"],
                         "Neuroscience (miscellaneous)")
        # "-" is an unrated quartile, not a value
        self.assertIsNone(table.lookup(["7777-7777"])["quartile"])
        # a title match is never enough
        self.assertIsNone(table.lookup(["3333-3333"]))
        self.assertIsNone(table.lookup([]))

    def test_comma_delimited_and_case_insensitive_headers(self):
        tmp = Path(tempfile.mkdtemp(prefix="jf-sjr-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = tmp / "scimagojr 2022.csv"
        path.write_text(
            'title,issn,sjr,sjr best quartile,categories,publisher\n'
            '"Comma Journal","12345678","1.250",Q3,"Software (Q3)","Pub"\n', encoding="utf-8")
        table = self.mod.read_sjr(path)
        hit = table.lookup(["1234-5678"])
        self.assertEqual((hit["quartile"], hit["value"]), ("Q3", 1.25))

    def test_year_from_the_file_name(self):
        y = self.mod.year_from_name
        self.assertEqual(y("scimagojr 2023.csv"), 2023)
        self.assertEqual(y("scimagojr-2021.csv"), 2021)
        self.assertEqual(y("scimagojr_2019_export.csv"), 2019)
        self.assertIsNone(y("download.csv"))


# --------------------------------------------------------------------------- S2/S3 sjr-import


class SjrImportTests(JournalFinderCase):
    def test_import_stores_the_file_and_prints_rows_year_path(self):
        result = self.run_cli("sjr-import", "--file", str(FIXTURES / "scimagojr-2019.csv"))
        self.assertEqual(result.code, 0, result.stdout)
        self.assertTrue(result.json["ok"])
        self.assertEqual(result.json["rows"], 5)
        self.assertEqual(result.json["year"], 2019)
        stored = self.sjr_dir / "scimagojr-2019.csv"
        self.assertEqual(Path(result.json["path"]), stored)
        self.assertEqual(stored.read_bytes(), (FIXTURES / "scimagojr-2019.csv").read_bytes())

    def test_year_flag_overrides_when_the_name_has_none(self):
        src = self.tmp / "download.csv"
        shutil.copy(FIXTURES / "scimagojr-2019.csv", src)
        result = self.run_cli("sjr-import", "--file", str(src), "--year", "2022")
        self.assertEqual(result.code, 0, result.stdout)
        self.assertEqual(result.json["year"], 2022)
        self.assertTrue((self.sjr_dir / "scimagojr-2022.csv").is_file())

    def test_default_cache_location_is_under_home(self):
        env = {k: v for k, v in os.environ.items() if k not in SCRUBBED}
        env["HOME"] = str(self.tmp / "home")
        done = subprocess.run(
            [sys.executable, "-I", str(CLI), "sjr-import", "--file", str(FIXTURES / "scimagojr-2019.csv")],
            capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.tmp / "home" / ".cache" / "papersmith" / "sjr" / "scimagojr-2019.csv").is_file())

    def refuses(self, *args: str) -> Result:
        before = self.tree_snapshot()
        result = self.run_cli("sjr-import", *args)
        self.assertEqual(result.code, 2, result.stdout)
        self.assertFalse(result.json["ok"])
        self.assertEqual(result.json["error"], "SJR_FILE_INVALID")
        self.assertTrue(result.json["message"])
        self.assertEqual(self.tree_snapshot(), before, "a refusal writes nothing")
        self.assertFalse(self.sjr_dir.exists())
        return result

    def test_missing_required_column_is_refused(self):
        bad = self.tmp / "scimagojr-2020.csv"
        bad.write_text("Title;Issn;SJR;Categories;Publisher\n\"A\";\"12345678\";\"1,0\";\"X (Q1)\";\"P\"\n",
                       encoding="utf-8")
        result = self.refuses("--file", str(bad))
        self.assertIn("SJR Best Quartile", result.json["message"])

    def test_not_a_csv_empty_header_only_and_absent_are_refused(self):
        binary = self.tmp / "scimagojr-2020.csv"
        binary.write_bytes(b"\x00\x01\x02\xff\xfe")
        self.refuses("--file", str(binary))
        empty = self.tmp / "empty-2020.csv"
        empty.write_text("", encoding="utf-8")
        self.refuses("--file", str(empty))
        header_only = self.tmp / "header-2020.csv"
        header_only.write_text("Title;Issn;SJR;SJR Best Quartile;Categories;Publisher\n", encoding="utf-8")
        self.refuses("--file", str(header_only))
        self.refuses("--file", str(self.tmp / "nope-2020.csv"))

    def test_year_unknown_is_refused(self):
        src = self.tmp / "download.csv"
        shutil.copy(FIXTURES / "scimagojr-2019.csv", src)
        result = self.refuses("--file", str(src))
        self.assertIn("--year", result.json["message"])

    def test_absurd_year_is_refused(self):
        self.refuses("--file", str(FIXTURES / "scimagojr-2019.csv"), "--year", "1850")


# --------------------------------------------------------------------------- S2 search


class SearchSchemaTests(JournalFinderCase):
    def test_proxy_search_writes_schema_one_and_prints_the_same_object(self):
        self.start_api()
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        self.assertTrue(result.json["ok"])
        doc = json.loads(self.out_file.read_text(encoding="utf-8"))
        for key in ("generated_at", "query", "quartiles", "filters", "quartile_source_summary",
                    "sjr", "candidates", "excluded_count", "notes"):
            self.assertIn(key, doc)
            self.assertEqual(result.json[key], doc[key])
        self.assertEqual(doc["schema"], 1)
        datetime.datetime.fromisoformat(doc["generated_at"].replace("Z", "+00:00"))
        self.assertTrue(doc["query"]["title"].startswith("Hybrid Quantum-Classical"))
        self.assertIn("Quantum Machine Learning", doc["query"]["keywords"])
        self.assertIn("quantum", doc["query"]["terms"])
        self.assertEqual(doc["quartiles"], ["Q1", "Q2", "Q3", "Q4"])
        self.assertIsNone(doc["sjr"])
        self.assertEqual(Path(result.json["out"]), self.out_file)

    def test_journals_only_and_aggregation_with_examples(self):
        api = self.start_api()
        result = self.search()
        self.assertEqual(self.names(result), ["Neural Fixtures Letters", "Open Signal Processing",
                                               "Biomedical Fixture Reports", "Obscure Quarterly"])
        top = result.json["candidates"][0]
        self.assertEqual(top["similar_works_count"], 5)
        self.assertEqual(len(top["similar_works"]), 3)
        self.assertEqual(top["similar_works"][0], {"title": "Quantum circuits for EEG decoding",
                                                   "year": 2024, "doi": "10.1111/nfl.1"})
        second = result.json["candidates"][1]
        self.assertEqual(second["similar_works_count"], 3)
        self.assertIsNone(second["similar_works"][2]["doi"])
        # repository, conference and source-less works never reach /sources
        fetched = {r["path"] for r in api.hits("/openalex/sources/")}
        self.assertEqual(fetched, {f"/openalex/sources/S100{i}" for i in (1, 2, 3, 4)})

    def test_fit_score_is_normalised_similar_works_count(self):
        self.start_api()
        result = self.search()
        scores = [c["fit_score"] for c in result.json["candidates"]]
        self.assertEqual(scores, [1.0, 0.6, 0.4, 0.2])
        self.assertEqual([c["rank"] for c in result.json["candidates"]], [1, 2, 3, 4])

    def test_source_fields_come_from_the_sources_endpoint(self):
        self.start_api()
        result = self.search()
        by_name = {c["display_name"]: c for c in result.json["candidates"]}
        osp = by_name["Open Signal Processing"]
        self.assertEqual(osp["openalex_id"], "https://openalex.org/S1002")
        self.assertEqual(osp["issn_l"], "3333-3333")
        self.assertEqual(osp["issn"], ["3333-3333"])
        self.assertEqual(osp["publisher"], "Open Fixture Society")
        self.assertTrue(osp["is_oa"])
        self.assertTrue(osp["is_in_doaj"])
        self.assertEqual(osp["apc_usd"], 1500)
        self.assertEqual(osp["homepage_url"], "https://open-signal.example/")
        self.assertEqual(osp["h_index"], 60)
        self.assertEqual(osp["mean_citedness_2yr"], 6.0)
        self.assertEqual(osp["field"], "Computer Science")
        self.assertIsNone(by_name["Neural Fixtures Letters"]["apc_usd"])


class ProxyQuartileTests(JournalFinderCase):
    def test_proxy_is_labelled_and_computed_from_the_field_percentile(self):
        api = self.start_api()
        result = self.search()
        proxy = {c["display_name"]: (c["quartile"], c["quartile_source"]) for c in result.json["candidates"]}
        self.assertEqual(proxy, {
            "Neural Fixtures Letters": ("Q1", "openalex-proxy"),
            "Open Signal Processing": ("Q2", "openalex-proxy"),
            "Biomedical Fixture Reports": ("Q3", "openalex-proxy"),
            "Obscure Quarterly": ("Q4", "openalex-proxy"),
        })
        first = result.json["candidates"][0]
        self.assertIsNone(first["sjr"])
        self.assertEqual(first["proxy"]["field"], "Computer Science")
        self.assertAlmostEqual(first["proxy"]["share_of_field_above"], 0.10, places=4)
        self.assertEqual(first["proxy"]["journals_in_field"], 100)
        self.assertEqual(result.json["quartile_source_summary"], {"sjr": 0, "openalex-proxy": 4})
        # exactly two count queries per source, restricted to journals of the field
        counts = [r for r in api.requests if r["path"] == "/openalex/sources"]
        self.assertEqual(len(counts), 8)
        for call in counts:
            self.assertIn("topics.field.id:17", call["params"]["filter"])
            self.assertEqual(call["params"]["per-page"], "1")
        self.assertTrue(any("not an SJR quartile" in n or "proxy" in n.lower()
                            for n in result.json["notes"]))

    def test_range_filter_on_the_proxy(self):
        self.start_api()
        for quartiles, expected in (("Q1", ["Neural Fixtures Letters"]),
                                    ("Q2-Q3", ["Open Signal Processing", "Biomedical Fixture Reports"]),
                                    ("q4", ["Obscure Quarterly"]),
                                    ("Q1-Q2", ["Neural Fixtures Letters", "Open Signal Processing"])):
            with self.subTest(quartiles=quartiles):
                result = self.search(quartiles=quartiles)
                self.assertEqual(self.names(result), expected)
                self.assertEqual(result.json["excluded_count"], 4 - len(expected))


class SjrSearchTests(JournalFinderCase):
    def test_sjr_wins_over_proxy_and_matches_any_issn(self):
        self.start_api()
        self.import_fixture_sjr()
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout)
        by_name = {c["display_name"]: c for c in result.json["candidates"]}
        letters = by_name["Neural Fixtures Letters"]  # matched by its *second* ISSN
        self.assertEqual((letters["quartile"], letters["quartile_source"]), ("Q1", "sjr"))
        self.assertEqual(letters["sjr"]["value"], 2.345)
        self.assertEqual(letters["sjr"]["year"], 2019)
        self.assertEqual(letters["sjr"]["categories"][1], {"name": "Software", "quartile": "Q2"})
        self.assertIsNone(letters["proxy"])
        obscure = by_name["Obscure Quarterly"]  # proxy would say Q4
        self.assertEqual((obscure["quartile"], obscure["quartile_source"]), ("Q2", "sjr"))
        # a journal absent from the file falls back to the proxy, labelled as such
        self.assertEqual(by_name["Open Signal Processing"]["quartile_source"], "openalex-proxy")
        self.assertEqual(result.json["quartile_source_summary"], {"sjr": 2, "openalex-proxy": 2})
        self.assertEqual(result.json["sjr"]["year"], 2019)
        self.assertTrue(result.json["sjr"]["file"].endswith("scimagojr-2019.csv"))

    def test_title_match_alone_never_assigns_an_sjr_quartile(self):
        # the fixture has an impostor "Open Signal Processing" with Q1 and other ISSNs
        self.start_api()
        self.import_fixture_sjr()
        result = self.search()
        osp = next(c for c in result.json["candidates"] if c["display_name"] == "Open Signal Processing")
        self.assertEqual(osp["quartile_source"], "openalex-proxy")
        self.assertEqual(osp["quartile"], "Q2")

    def test_the_range_filters_on_the_sjr_quartile(self):
        self.start_api()
        self.import_fixture_sjr()
        result = self.search(quartiles="Q2")
        self.assertEqual(self.names(result), ["Open Signal Processing", "Obscure Quarterly"])

    def test_explicit_sjr_flag_beats_the_cache_and_latest_year_wins(self):
        self.start_api()
        self.import_fixture_sjr()
        newer = self.tmp / "scimagojr-2024.csv"
        newer.write_text(
            "Rank;Sourceid;Title;Type;Issn;SJR;SJR Best Quartile;H index;Publisher;Categories\n"
            '1;1;"Open Signal Processing";journal;"33333333";"4,000";Q1;60;"OFS";"Signal Processing (Q1)"\n',
            encoding="utf-8")
        shutil.copy(newer, self.sjr_dir / "scimagojr-2024.csv")
        latest = self.search()
        self.assertEqual(latest.json["sjr"]["year"], 2024)
        osp = next(c for c in latest.json["candidates"] if c["display_name"] == "Open Signal Processing")
        self.assertEqual((osp["quartile"], osp["quartile_source"]), ("Q1", "sjr"))
        explicit = self.search("--sjr", str(FIXTURES / "scimagojr-2019.csv"))
        self.assertEqual(explicit.json["sjr"]["year"], 2019)
        osp = next(c for c in explicit.json["candidates"] if c["display_name"] == "Open Signal Processing")
        self.assertEqual(osp["quartile_source"], "openalex-proxy")

    def test_an_old_file_adds_a_note_and_a_recent_one_does_not(self):
        self.start_api()
        self.import_fixture_sjr()
        stale = self.search()
        self.assertTrue(any("2019" in n and "older" in n for n in stale.json["notes"]), stale.json["notes"])
        year = datetime.date.today().year
        shutil.copy(FIXTURES / "scimagojr-2019.csv", self.sjr_dir / f"scimagojr-{year}.csv")
        fresh = self.search()
        self.assertFalse(any("older" in n for n in fresh.json["notes"]), fresh.json["notes"])

    def test_invalid_explicit_sjr_file_is_refused_before_any_request(self):
        api = self.start_api()
        bad = self.tmp / "bad.csv"
        bad.write_text("a;b\n1;2\n", encoding="utf-8")
        result = self.search("--sjr", str(bad))
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "SJR_FILE_INVALID")
        self.assertEqual(api.requests, [])
        self.assertFalse(self.out_file.exists())


class FilterTests(JournalFinderCase):
    def test_oa_only(self):
        self.start_api()
        result = self.search("--oa-only")
        self.assertEqual(self.names(result), ["Open Signal Processing", "Biomedical Fixture Reports"])
        self.assertEqual(result.json["filters"]["oa_only"], True)
        self.assertEqual(result.json["excluded_count"], 2)

    def test_max_apc_keeps_unknown_apc_and_flags_it(self):
        self.start_api()
        result = self.search("--max-apc", "2000")
        self.assertEqual(self.names(result), ["Neural Fixtures Letters", "Open Signal Processing",
                                               "Obscure Quarterly"])
        flags = {c["display_name"]: c["flags"] for c in result.json["candidates"]}
        self.assertIn("apc-unknown", flags["Neural Fixtures Letters"])
        self.assertNotIn("apc-unknown", flags["Open Signal Processing"])
        self.assertEqual(result.json["filters"]["max_apc"], 2000)

    def test_filters_combine(self):
        self.start_api()
        result = self.search("--oa-only", "--max-apc", "2000", quartiles="Q2-Q3")
        self.assertEqual(self.names(result), ["Open Signal Processing"])

    def test_limit_default_cap_and_validation(self):
        self.start_api()
        self.assertEqual(self.search().json["filters"]["limit"], 15)
        two = self.search("--limit", "2")
        self.assertEqual(len(two.json["candidates"]), 2)
        self.assertEqual(two.json["candidates"][0]["rank"], 1)
        capped = self.search("--limit", "99")
        self.assertEqual(capped.code, 0)
        self.assertEqual(capped.json["filters"]["limit"], 50)
        self.assertTrue(any("50" in n for n in capped.json["notes"]))

    def test_invalid_filter_values_are_refused_and_write_nothing(self):
        api = self.start_api()
        for args in (("--limit", "0"), ("--limit", "abc"), ("--max-apc", "-5"),
                     ("--max-review-days", "0"), ("--max-apc", "x")):
            with self.subTest(args=args):
                result = self.search(*args)
                self.assertEqual(result.code, 2, result.stdout)
                self.assertFalse(result.json["ok"])
                self.assertEqual(result.json["error"], "FILTER_INVALID")
        self.assertEqual(api.requests, [])
        self.assertFalse(self.out_file.exists())

    def test_out_flag_redirects_the_write(self):
        self.start_api()
        target = self.tmp / "elsewhere" / "cands.json"
        result = self.search("--out", str(target))
        self.assertEqual(result.code, 0, result.stdout)
        self.assertTrue(target.is_file())
        self.assertFalse(self.out_file.exists())
        self.assertEqual(Path(result.json["out"]), target)


class CapsAndEtiquetteTests(JournalFinderCase):
    def test_max_works_is_bounded(self):
        api = self.start_api()
        result = self.search(extra_env={"PAPERSMITH_JOURNAL_MAX_WORKS": "5"})
        self.assertEqual(result.code, 0, result.stdout)
        work_calls = api.hits("/openalex/works")
        self.assertEqual([r["params"]["per-page"] for r in work_calls], ["5"])
        self.assertEqual(self.names(result), ["Neural Fixtures Letters"])
        self.assertEqual(result.json["candidates"][0]["similar_works_count"], 5)

    def test_works_search_asks_for_journal_articles_with_the_profile_phrases(self):
        api = self.start_api()
        result = self.search()
        calls = api.hits("/openalex/works")
        self.assertEqual(len(calls), 1, "the phrase query matched 50+ works, so nothing was relaxed")
        call = calls[0]
        self.assertIn('"data re-uploading"', call["params"]["search"])
        self.assertIn(" OR ", call["params"]["search"])
        self.assertIn("primary_location.source.type:journal", call["params"]["filter"])
        self.assertIn("topics", call["params"]["select"])
        self.assertEqual(result.json["query"]["search_mode"], "phrases-or")

    def test_terms_are_relaxed_one_by_one_until_enough_works_match(self):
        api = self.start_api(max_terms_matching=4, or_count=0)
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout)
        calls = api.hits("/openalex/works")
        self.assertIn(" OR ", calls[0]["params"]["search"])
        searches = [r["params"]["search"].split() for r in calls[1:]]
        self.assertEqual([len(s) for s in searches], [6, 5, 4])
        self.assertEqual(searches[1], searches[0][:5])
        self.assertEqual(result.json["query"]["terms"], searches[2])
        self.assertEqual(result.json["query"]["search_mode"], "terms-and-relaxation")
        self.assertEqual(len(result.json["candidates"]), 4)
        self.assertTrue(any("dropped" in n for n in result.json["notes"]), result.json["notes"])

    def test_relaxation_stops_at_two_terms(self):
        api = self.start_api(max_terms_matching=0, or_count=0)
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout)
        self.assertEqual([len(r["params"]["search"].split()) for r in api.hits("/openalex/works")[1:]],
                         [6, 5, 4, 3, 2])
        self.assertEqual(result.json["candidates"], [])

    def test_contact_email_is_used_when_set_and_absent_otherwise(self):
        api = self.start_api()
        self.search()
        for request in api.requests:
            self.assertNotIn("mailto", request["params"], request["path"])
            self.assertNotIn("email", request["params"], request["path"])
            self.assertNotIn("api_key", request["params"], request["path"])
            self.assertNotIn("@", request["headers"].get("User-Agent", ""))
        api.requests.clear()
        self.search(extra_env={"PAPERSMITH_CONTACT_EMAIL": "ops@example.org"})
        for request in api.hits("/openalex"):
            self.assertEqual(request["params"].get("mailto"), "ops@example.org", request["path"])
            self.assertIn("mailto:ops@example.org", request["headers"]["User-Agent"])
        for request in api.hits("/pubmed"):
            self.assertEqual(request["params"].get("email"), "ops@example.org")

    def test_the_cli_source_never_hard_codes_an_email(self):
        text = CLI.read_text(encoding="utf-8")
        self.assertNotIn("unal.edu.co", text)
        self.assertEqual(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text), [])

    def test_ncbi_etiquette_tool_and_api_key(self):
        api = self.start_api()
        self.search(extra_env={"NCBI_API_KEY": "k-123", "PAPERSMITH_CONTACT_EMAIL": "ops@example.org"})
        pubmed = api.hits("/pubmed")
        self.assertTrue(pubmed)
        for request in pubmed:
            self.assertEqual(request["params"]["tool"], "papersmith")
            self.assertEqual(request["params"]["api_key"], "k-123")
        api.requests.clear()
        self.search()
        for request in api.hits("/pubmed"):
            self.assertEqual(request["params"]["tool"], "papersmith")
            self.assertNotIn("api_key", request["params"])

    def test_pubmed_requests_stay_under_three_per_second(self):
        api = self.start_api()
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout)
        stamps = sorted(r["t"] for r in api.hits("/pubmed"))
        self.assertGreaterEqual(len(stamps), 4)
        for i in range(len(stamps) - 3):
            self.assertGreaterEqual(stamps[i + 3] - stamps[i], 0.9, stamps)


class NetworkTests(JournalFinderCase):
    def test_unreachable_openalex_is_a_typed_refusal_and_writes_nothing(self):
        before = self.tree_snapshot()
        result = self.run_cli("search", "--workspace", str(self.workspace), "--quartiles", "Q1-Q2",
                              extra_env={"PAPERSMITH_OPENALEX_URL": "http://127.0.0.1:9/openalex",
                                         "PAPERSMITH_HTTP_RETRIES": "1"}, use_api=False)
        self.assertEqual(result.code, 2, result.stdout)
        self.assertEqual(result.json["error"], "NETWORK_UNAVAILABLE")
        self.assertFalse(self.out_file.exists())
        self.assertEqual(self.tree_snapshot(), before)

    def test_a_429_is_retried_with_backoff_and_then_succeeds(self):
        api = self.start_api(script={"/openalex/works": [429], "/openalex/sources/S1001": [503]})
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        self.assertEqual(len(api.hits("/openalex/works")), 2)
        self.assertEqual(len(api.hits("/openalex/sources/S1001")), 2)
        self.assertEqual(len(result.json["candidates"]), 4)

    def test_persistent_429_exhausts_retries_into_network_unavailable(self):
        api = self.start_api(script={"/openalex/works": [429] * 10})
        result = self.search()
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "NETWORK_UNAVAILABLE")
        # one try plus two retries (PAPERSMITH_HTTP_RETRIES=2), never unbounded
        self.assertEqual(len(api.hits("/openalex/works")), 3)
        self.assertFalse(self.out_file.exists())

    def test_a_client_error_is_not_retried(self):
        api = self.start_api(script={"/openalex/works": [400]})
        result = self.search()
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "NETWORK_UNAVAILABLE")
        self.assertEqual(len(api.hits("/openalex/works")), 1)

    def test_total_deadline_stops_the_search(self):
        self.start_api()
        result = self.search(extra_env={"PAPERSMITH_JOURNAL_DEADLINE": "0"})
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "NETWORK_UNAVAILABLE")
        self.assertIn("deadline", result.json["message"])
        self.assertFalse(self.out_file.exists())

    def test_a_request_timeout_is_bounded(self):
        # a server that never answers within the timeout
        import socket
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(5)
        self.addCleanup(sock.close)
        port = sock.getsockname()[1]
        started = time.monotonic()
        result = self.run_cli("search", "--workspace", str(self.workspace), "--quartiles", "Q1",
                              extra_env={"PAPERSMITH_OPENALEX_URL": f"http://127.0.0.1:{port}",
                                         "PAPERSMITH_HTTP_TIMEOUT": "0.5",
                                         "PAPERSMITH_HTTP_RETRIES": "0"}, use_api=False)
        self.assertEqual(result.json["error"], "NETWORK_UNAVAILABLE")
        self.assertLess(time.monotonic() - started, 20)

    def test_a_dead_source_endpoint_drops_that_journal_with_a_note(self):
        api = self.start_api()
        api.script["/openalex/sources/S1004"] = [404]
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout)
        self.assertNotIn("Obscure Quarterly", self.names(result))
        self.assertTrue(any("S1004" in n for n in result.json["notes"]), result.json["notes"])


class SearchRefusalTests(JournalFinderCase):
    def test_invalid_range_writes_nothing_and_never_calls_the_network(self):
        api = self.start_api()
        before = self.tree_snapshot()
        for bad in ("Q3-Q1", "Q5", "banana", ""):
            with self.subTest(bad=bad):
                result = self.search(quartiles=bad)
                self.assertEqual(result.code, 2)
                self.assertEqual(result.json["error"], "QUARTILE_RANGE_INVALID")
                self.assertTrue(result.json["message"])
        self.assertEqual(api.requests, [])
        self.assertEqual(self.tree_snapshot(), before)

    def test_paper_absent(self):
        api = self.start_api()
        (self.workspace / "paper" / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
        before = self.tree_snapshot()
        result = self.search()
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "PAPER_ABSENT")
        self.assertEqual(api.requests, [])
        self.assertEqual(self.tree_snapshot(), before)

    def test_workspace_absent(self):
        result = self.run_cli("search", "--workspace", str(self.tmp / "missing"), "--quartiles", "Q1")
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "WORKSPACE_ABSENT")

    def test_usage_errors_are_typed_too(self):
        for args in ((), ("search",), ("frobnicate",), ("search", "--workspace", str(self.workspace))):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.code, 2)
                self.assertFalse(result.json["ok"])
                self.assertEqual(result.json["error"], "USAGE")

    def test_an_empty_openalex_answer_is_a_valid_empty_result(self):
        self.start_api()
        (self.workspace / "paper" / "main.tex").write_text(
            "\\title{zzqx}\\begin{abstract}Some words here for the zzqx query.\\end{abstract}", encoding="utf-8")
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout)
        self.assertEqual(result.json["candidates"], [])
        self.assertTrue(any("no journal" in n.lower() for n in result.json["notes"]))


# --------------------------------------------------------------------------- S8 review time


class ReviewTimeTests(JournalFinderCase):
    def by_name(self, result: Result) -> dict:
        return {c["display_name"]: c for c in result.json["candidates"]}

    def test_crossref_assertions_give_median_iqr_and_accept_to_online(self):
        api = self.start_api()
        result = self.search()
        review = self.by_name(result)["Neural Fixtures Letters"]["review_time"]
        self.assertEqual(review["source"], "crossref")
        self.assertEqual(review["n"], 6)
        self.assertEqual(review["median_days"], 35.0)
        self.assertEqual(review["p25_days"], 22.5)
        self.assertEqual(review["p75_days"], 47.5)
        self.assertEqual(review["accept_to_online_median_days"], 7.0)
        window = review["window"]
        today = datetime.date.today()
        self.assertEqual(window["to"], today.isoformat())
        start = datetime.date.fromisoformat(window["from"])
        self.assertAlmostEqual((today - start).days, 3 * 365, delta=2)
        self.assertEqual(review["kind"], "submission-to-acceptance-estimate")
        # a journal answered by Crossref never touches PubMed
        crossref = [r for r in api.hits("/crossref/journals/") if "1111-111X" in r["path"]]
        self.assertEqual(len(crossref), 1)
        self.assertEqual(crossref[0]["params"]["rows"], "40")
        self.assertIn("from-pub-date:", crossref[0]["params"]["filter"])
        self.assertIn("type:journal-article", crossref[0]["params"]["filter"])
        esearches = [r for r in api.hits("/pubmed/esearch.fcgi")]
        terms = " ".join(r["params"]["term"] for r in esearches)
        self.assertNotIn("1111-111X", terms)

    def test_fewer_than_five_dated_crossref_articles_falls_through_to_pubmed(self):
        api = self.start_api()
        result = self.search()
        review = self.by_name(result)["Open Signal Processing"]["review_time"]
        self.assertEqual(review["source"], "pubmed")
        self.assertEqual(review["n"], 6)
        self.assertEqual(review["median_days"], 105.0)
        self.assertEqual(review["p25_days"], 67.5)
        self.assertEqual(review["p75_days"], 142.5)
        self.assertEqual(review["accept_to_online_median_days"], 4.0)
        self.assertTrue(api.hits("/crossref/journals/3333-3333/works"))
        esearch = [r for r in api.hits("/pubmed/esearch.fcgi") if "3333-3333" in r["params"]["term"]]
        self.assertEqual(len(esearch), 1)
        self.assertIn("[is]", esearch[0]["params"]["term"])
        summaries = api.hits("/pubmed/esummary.fcgi")
        self.assertTrue(any("900001" in r["params"]["id"] for r in summaries))

    def test_below_threshold_everywhere_reads_none_with_n_kept(self):
        self.start_api()
        result = self.search()
        review = self.by_name(result)["Biomedical Fixture Reports"]["review_time"]
        self.assertEqual(review["source"], "none")
        self.assertEqual(review["n"], 3)
        self.assertIsNone(review["median_days"])
        self.assertIsNone(review["p25_days"])
        self.assertIsNone(review["p75_days"])
        self.assertIsNone(review["accept_to_online_median_days"])

    def test_no_data_at_all_reads_none_with_zero(self):
        self.start_api()
        result = self.search()
        review = self.by_name(result)["Obscure Quarterly"]["review_time"]
        self.assertEqual(review["source"], "none")
        self.assertEqual(review["n"], 0)
        self.assertIn("from", review["window"])

    def test_every_candidate_carries_a_review_time_shape(self):
        self.start_api()
        result = self.search()
        for candidate in result.json["candidates"]:
            review = candidate["review_time"]
            for key in ("median_days", "p25_days", "p75_days", "n",
                        "accept_to_online_median_days", "source", "window"):
                self.assertIn(key, review)
            self.assertIn(review["source"], ("crossref", "pubmed", "none"))

    def test_max_review_days_filters_slow_journals_and_keeps_unknown_flagged(self):
        self.start_api()
        result = self.search("--max-review-days", "60")
        self.assertEqual(self.names(result), ["Neural Fixtures Letters", "Biomedical Fixture Reports",
                                               "Obscure Quarterly"])
        flags = {c["display_name"]: c["flags"] for c in result.json["candidates"]}
        self.assertNotIn("review-time-unknown", flags["Neural Fixtures Letters"])
        self.assertIn("review-time-unknown", flags["Biomedical Fixture Reports"])
        self.assertIn("review-time-unknown", flags["Obscure Quarterly"])
        self.assertEqual(result.json["filters"]["max_review_days"], 60)
        self.assertEqual(result.json["excluded_count"], 1)

    def test_without_the_filter_nothing_is_flagged_for_review_time(self):
        self.start_api()
        result = self.search()
        for candidate in result.json["candidates"]:
            self.assertNotIn("review-time-unknown", candidate["flags"])

    def test_review_time_failures_degrade_to_none_with_a_note(self):
        api = self.start_api(script={
            f"/crossref/journals/{issn}/works": [500] * 10 for issn in ("1111-111X", "2222-2222", "3333-3333")})
        api.script["/pubmed/esearch.fcgi"] = [500] * 20
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        for candidate in result.json["candidates"]:
            self.assertEqual(candidate["review_time"]["source"], "none")
        self.assertTrue(any("review" in n.lower() for n in result.json["notes"]), result.json["notes"])
        self.assertTrue(self.out_file.is_file())

    def test_unreachable_crossref_and_pubmed_never_fail_the_search(self):
        self.start_api()
        result = self.search(extra_env={"PAPERSMITH_CROSSREF_URL": "http://127.0.0.1:9/x",
                                        "PAPERSMITH_PUBMED_URL": "http://127.0.0.1:9/y",
                                        "PAPERSMITH_HTTP_RETRIES": "0"})
        self.assertEqual(result.code, 0, result.stdout)
        self.assertEqual({c["review_time"]["source"] for c in result.json["candidates"]}, {"none"})


class ReviewTimeUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_crossref_item_dates(self):
        item = {"assertion": [
            {"name": "received", "value": "1 March 2024"},
            {"name": "accepted", "value": "2024-03-11"},
            {"name": "first_online", "value": "13 Mar 2024"}]}
        self.assertEqual(self.mod.crossref_item_dates(item), (
            datetime.date(2024, 3, 1), datetime.date(2024, 3, 11), datetime.date(2024, 3, 13)))
        self.assertEqual(self.mod.crossref_item_dates({}), (None, None, None))

    def test_pubmed_history_dates(self):
        history = [{"pubstatus": "received", "date": "2025/04/02 00:00"},
                   {"pubstatus": "accepted", "date": "2025/09/24 00:00"},
                   {"pubstatus": "epublish", "date": "2025/10/01 00:00"},
                   {"pubstatus": "pubmed", "date": "2025/10/16 12:31"}]
        self.assertEqual(self.mod.pubmed_history_dates(history), (
            datetime.date(2025, 4, 2), datetime.date(2025, 9, 24), datetime.date(2025, 10, 1)))
        self.assertEqual(self.mod.pubmed_history_dates(None), (None, None, None))

    def test_deltas_skip_incomplete_and_negative_articles(self):
        d = datetime.date
        triples = [(d(2024, 1, 1), d(2024, 1, 11), None), (None, d(2024, 1, 11), None),
                   (d(2024, 2, 1), d(2024, 1, 1), None), (d(2024, 1, 1), d(2024, 1, 31), d(2024, 2, 4))]
        review, accept = self.mod.review_deltas(triples)
        self.assertEqual(review, [10, 30])
        self.assertEqual(accept, [4])


# --------------------------------------------------------------------------- status


# --------------------------------------------------------------------------- S2 topical fit units


class PhraseUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()
        tex = (FIXTURES / "paper_main.tex").read_text(encoding="utf-8")
        root = Path(tempfile.mkdtemp(prefix="jf-phrase-"))
        (root / "paper").mkdir()
        (root / "paper" / "main.tex").write_text(tex, encoding="utf-8")
        cls.profile = cls.mod.extract_profile(root)
        shutil.rmtree(root, ignore_errors=True)

    def test_phrases_come_from_keywords_and_title_and_keep_hyphenated_compounds_whole(self):
        phrases = self.mod.build_phrases(self.profile)
        self.assertLessEqual(len(phrases), self.mod.MAX_PHRASES)
        self.assertEqual(len(phrases), len(set(phrases)))
        for expected in ("data re-uploading", "variational quantum circuits", "quantum machine learning"):
            self.assertIn(expected, phrases)
        for fragment in ("re", "uploading", "re uploading"):
            self.assertNotIn(fragment, phrases)
        self.assertTrue(any("quantum-classical" in p for p in phrases), phrases)
        self.assertNotIn("zebra giraffe", " ".join(phrases))

    def test_phrases_are_multi_word_unless_the_author_declared_them_as_keywords(self):
        phrases = self.mod.build_phrases(self.profile)
        keywords = {k.lower() for k in self.profile["keywords"]}
        for phrase in phrases:
            single = len(phrase.split()) == 1 and "-" not in phrase
            if single:
                self.assertTrue(any(phrase in k for k in keywords), f"{phrase!r} is a bare word, not a keyword")
        for phrase in phrases:
            self.assertFalse(set(phrase.split()) <= self.mod._PHRASE_BREAKS, phrase)

    def test_frequent_abstract_bigrams_join_and_one_off_bigrams_do_not(self):
        profile = {"title": "", "keywords": [], "abstract": (
            "Graph attention helps. We use graph attention here and graph attention again. "
            "A lone pair appears once.")}
        phrases = self.mod.build_phrases(profile)
        self.assertIn("graph attention", phrases)
        self.assertNotIn("lone pair", phrases)

    def test_a_bigram_inside_a_declared_longer_phrase_is_dropped(self):
        profile = {"title": "", "keywords": ["Variational Quantum Circuits"],
                   "abstract": "Quantum circuits matter. Quantum circuits scale. Quantum circuits win."}
        phrases = self.mod.build_phrases(profile)
        self.assertIn("variational quantum circuits", phrases)
        self.assertNotIn("quantum circuits", phrases)

    def test_quotes_never_survive_into_a_phrase_and_nothing_comes_from_nothing(self):
        profile = {"title": 'The "quoted" thing', "keywords": ['say "hi" there'], "abstract": ""}
        for phrase in self.mod.build_phrases(profile):
            self.assertNotIn('"', phrase)
        self.assertEqual(self.mod.build_phrases({"title": "zzqx", "keywords": [], "abstract": ""}), [])

    def test_the_or_query_quotes_every_phrase(self):
        self.assertEqual(self.mod.or_query(["data re-uploading", "adhd"]), '"data re-uploading" OR "adhd"')

    def test_recency_window_is_six_years_and_survives_leap_day(self):
        start = self.mod.recency_start
        self.assertEqual(start(datetime.date(2026, 10, 31)), datetime.date(2020, 10, 31))
        self.assertEqual(start(datetime.date(2028, 2, 29)), datetime.date(2022, 2, 28))
        self.assertEqual(self.mod.RECENT_YEARS, 6)


class BibliographyUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_entries_fields_in_braces_quotes_and_bare_numbers(self):
        entries = self.mod.parse_bib((FIXTURES / "refs.bib").read_text(encoding="utf-8"))
        self.assertEqual([e["key"] for e in entries], ["k1", "k2", "k3", "k4", "k5", "k6", "k7"])
        by_key = {e["key"]: e for e in entries}
        self.assertEqual(by_key["k1"]["journal"], "Neural Fixtures Letters")
        self.assertEqual(by_key["k1"]["title"], "Quantum circuits for {EEG} decoding")
        self.assertEqual(by_key["k2"]["journal"], "Cited Only Journal")
        self.assertEqual(by_key["k5"]["journal"], "Obscure Quarterly")
        self.assertIsNone(by_key["k5"]["doi"])

    def test_doi_forms_are_normalised_and_arxiv_ids_become_arxiv_dois(self):
        entries = {e["key"]: e for e in self.mod.parse_bib((FIXTURES / "refs.bib").read_text(encoding="utf-8"))}
        self.assertEqual(entries["k1"]["doi"], "10.1111/nfl.1")
        self.assertEqual(entries["k2"]["doi"], "10.5555/cited.1")
        self.assertEqual(entries["k4"]["doi"], "10.48550/arxiv.2101.00001")
        for raw, want in (("https://doi.org/10.1/AbC.", "10.1/abc"), ("doi:10.1/x", "10.1/x"),
                          (" 10.1/y ", "10.1/y"), ("not a doi", None), ("", None), (None, None)):
            with self.subTest(raw=raw):
                self.assertEqual(self.mod.normalize_doi(raw), want)

    def test_comment_blocks_and_nested_braces_do_not_leak_entries(self):
        text = "@comment{@article{ghost, doi={10.0/ghost}}}\n@string{x = {y}}\n" \
               "@article{real, title={{ADHDeepNet} {A {nested}} title}, journal={J}, doi={10.2/real}}"
        entries = self.mod.parse_bib(text)
        self.assertEqual([e["key"] for e in entries], ["real"])
        self.assertEqual(entries[0]["title"], "{ADHDeepNet} {A {nested}} title")

    def test_arxiv_style_journal_names_are_not_looked_up(self):
        skip = self.mod.is_repository_name
        for name in ("arXiv preprint arXiv:1234.5678", "IEEE Dataport", "bioRxiv", "SSRN Electronic Journal",
                     "Zenodo"):
            with self.subTest(name=name):
                self.assertTrue(skip(name))
        for name in ("Quantum", "Physical Review A", "Nature Communications"):
            with self.subTest(name=name):
                self.assertFalse(skip(name))


class FitUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_topic_overlap_is_the_histogram_intersection(self):
        overlap = self.mod.topic_overlap
        self.assertAlmostEqual(overlap({"A": 0.5, "B": 0.5}, {"A": 0.25, "C": 0.75}), 0.25)
        self.assertAlmostEqual(overlap({"A": 1.0}, {"A": 1.0}), 1.0)
        self.assertEqual(overlap({"A": 1.0}, {"B": 1.0}), 0.0)
        self.assertEqual(overlap({}, {"B": 1.0}), 0.0)

    def test_topic_profile_blends_matched_and_cited_works_and_normalises(self):
        profile = self.mod.blend_topics({"A": 3.0, "B": 1.0}, {"B": 2.0})
        self.assertAlmostEqual(sum(profile.values()), 1.0)
        self.assertAlmostEqual(profile["A"], 0.375)
        self.assertAlmostEqual(profile["B"], 0.625)
        self.assertEqual(self.mod.blend_topics({"A": 2.0}, {}), {"A": 1.0})
        self.assertEqual(self.mod.blend_topics({}, {}), {})

    def test_weights_sum_to_one_and_cited_venues_are_strong_evidence(self):
        weights = self.mod.FIT_WEIGHTS
        self.assertEqual(set(weights), {"similar_works", "cited_in_paper", "topic_overlap"})
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertGreaterEqual(weights["cited_in_paper"], weights["topic_overlap"])

    def test_apply_fit_normalises_each_component_by_its_maximum_and_weights_them(self):
        details = [{"similar_works_count": 4, "cited_count": 0, "topic_raw": 0.2},
                   {"similar_works_count": 2, "cited_count": 2, "topic_raw": 0.4},
                   {"similar_works_count": 0, "cited_count": 1, "topic_raw": 0.1}]
        scoring = self.mod.apply_fit(details)
        w = self.mod.FIT_WEIGHTS
        self.assertEqual(details[0]["fit"], {"similar_works": 1.0, "cited_in_paper": 0.0, "topic_overlap": 0.5})
        self.assertEqual(details[1]["fit"], {"similar_works": 0.5, "cited_in_paper": 1.0, "topic_overlap": 1.0})
        self.assertEqual(details[2]["fit"], {"similar_works": 0.0, "cited_in_paper": 0.5, "topic_overlap": 0.25})
        expected = round(w["similar_works"] * 0.5 + w["cited_in_paper"] * 1.0 + w["topic_overlap"] * 1.0, 4)
        self.assertEqual(details[1]["fit_score"], expected)
        self.assertEqual(scoring["active"], ["similar_works", "cited_in_paper", "topic_overlap"])
        self.assertIn("formula", scoring)

    def test_a_component_with_no_signal_anywhere_drops_out_and_the_rest_are_rescaled(self):
        details = [{"similar_works_count": 4, "cited_count": 0, "topic_raw": 0.0},
                   {"similar_works_count": 2, "cited_count": 0, "topic_raw": 0.0}]
        scoring = self.mod.apply_fit(details)
        self.assertEqual(scoring["active"], ["similar_works"])
        self.assertEqual([d["fit_score"] for d in details], [1.0, 0.5])
        self.assertEqual(details[0]["fit"]["cited_in_paper"], 0.0)
        self.assertAlmostEqual(sum(scoring["weights"].values()), 1.0)
        self.assertEqual(scoring["weights"]["cited_in_paper"], 0.0)

    def test_an_empty_pool_scores_nothing_and_does_not_divide_by_zero(self):
        self.assertEqual(self.mod.apply_fit([])["active"], [])


# --------------------------------------------------------------------------- S2 topical fit, end to end


class PhraseSearchTests(JournalFinderCase):
    def test_the_works_query_ors_quoted_phrases_with_a_six_year_recency_filter(self):
        api = self.start_api()
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        call = api.hits("/openalex/works")[0]
        search = call["params"]["search"]
        quoted = re.findall(r'"([^"]+)"', search)
        self.assertGreaterEqual(len(quoted), 3)
        self.assertEqual(search, " OR ".join(f'"{p}"' for p in quoted))
        self.assertIn("data re-uploading", quoted)
        today = datetime.date.today()
        self.assertIn(f"from_publication_date:{today.replace(year=today.year - 6).isoformat()}",
                      call["params"]["filter"])
        self.assertIn("type:article", call["params"]["filter"])
        self.assertEqual(result.json["query"]["phrases"], quoted)
        self.assertEqual(result.json["query"]["search_mode"], "phrases-or")
        self.assertLessEqual(len(quoted), 8)

    def test_a_phrase_query_with_too_few_matches_falls_back_to_the_relaxation_with_a_note(self):
        api = self.start_api(or_count=3, max_terms_matching=100)
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout)
        self.assertEqual(result.json["query"]["search_mode"], "terms-and-relaxation")
        self.assertTrue(any("phrase" in n.lower() and "3" in n for n in result.json["notes"]), result.json["notes"])
        self.assertEqual(result.json["query"]["phrases"], [])
        self.assertEqual(len(api.hits("/openalex/works")), 2)

    def test_a_paper_without_phrases_goes_straight_to_the_relaxation(self):
        api = self.start_api()
        (self.workspace / "paper" / "main.tex").write_text(
            "\\title{zzqx}\\begin{abstract}Some words here for the zzqx query.\\end{abstract}", encoding="utf-8")
        result = self.search()
        self.assertEqual(result.json["query"]["search_mode"], "terms-and-relaxation")
        self.assertTrue(all('"' not in r["params"]["search"] for r in api.hits("/openalex/works")))


class CitedVenueTests(JournalFinderCase):
    def with_refs(self, text: str | None = None) -> None:
        target = self.workspace / "paper" / "refs.bib"
        target.write_text(text if text is not None else (FIXTURES / "refs.bib").read_text(encoding="utf-8"),
                          encoding="utf-8")

    def by_name(self, result: Result) -> dict:
        return {c["display_name"]: c for c in result.json["candidates"]}

    def test_dois_are_resolved_in_one_batched_call_and_count_the_journals_cited(self):
        api = self.start_api()
        self.with_refs()
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        doi_calls = [r for r in api.hits("/openalex/works") if r["params"].get("filter", "").startswith("doi:")]
        self.assertEqual(len(doi_calls), 1)
        batch = doi_calls[0]["params"]["filter"][4:].split("|")
        self.assertEqual(sorted(batch), sorted({"10.1111/nfl.1", "10.5555/cited.1", "10.5555/cited.2",
                                                "10.48550/arxiv.2101.00001", "10.9999/dataset"}))
        self.assertLessEqual(int(doi_calls[0]["params"]["per-page"]), 50)
        names = self.by_name(result)
        self.assertEqual(names["Neural Fixtures Letters"]["cited_in_paper_count"], 1)
        self.assertEqual(names["Open Signal Processing"]["cited_in_paper_count"], 1, "through its arXiv DOI")
        self.assertEqual(names["Cited Only Journal"]["cited_in_paper_count"], 2)
        self.assertEqual(names["Biomedical Fixture Reports"]["cited_in_paper_count"], 0)

    def test_a_journal_only_the_paper_cites_is_kept_with_zero_similar_works(self):
        self.start_api()
        self.with_refs()
        result = self.search()
        cited_only = self.by_name(result)["Cited Only Journal"]
        self.assertEqual(cited_only["similar_works_count"], 0)
        self.assertEqual(cited_only["similar_works"], [])
        self.assertEqual(cited_only["fit"]["similar_works"], 0.0)
        self.assertEqual(cited_only["fit"]["cited_in_paper"], 1.0)
        self.assertGreater(cited_only["fit_score"], 0.0)
        self.assertEqual(cited_only["quartile_source"], "openalex-proxy")
        self.assertEqual(cited_only["quartile"], "Q3")

    def test_citing_a_journal_raises_its_rank_against_the_same_search_without_refs(self):
        self.start_api()
        without = self.search()
        rank_without = {c["display_name"]: c["rank"] for c in without.json["candidates"]}
        self.assertEqual(rank_without["Obscure Quarterly"], 4)
        self.assertEqual(rank_without["Biomedical Fixture Reports"], 3)
        self.with_refs()
        with_refs = self.search()
        ranks = {c["display_name"]: c["rank"] for c in with_refs.json["candidates"]}
        self.assertLess(ranks["Obscure Quarterly"], ranks["Biomedical Fixture Reports"],
                        "one similar work plus one citation beats two similar works and none")
        scores = [c["fit_score"] for c in with_refs.json["candidates"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_references_without_dois_fall_back_to_an_exact_journal_name_lookup(self):
        api = self.start_api()
        self.with_refs()
        result = self.search()
        lookups = api.hits("/openalex/sources")
        lookups = [r for r in lookups if "search" in r["params"]]
        self.assertEqual([r["params"]["search"] for r in lookups], ["Obscure Quarterly"])
        self.assertIn("type:journal", lookups[0]["params"]["filter"])
        names = self.by_name(result)
        self.assertEqual(names["Obscure Quarterly"]["cited_in_paper_count"], 1, "the Supplement decoy is not it")
        self.assertNotIn("Obscure Quarterly Supplement", names)

    def test_the_cited_summary_is_reported_in_the_query(self):
        self.start_api()
        self.with_refs()
        cited = self.search().json["query"]["cited"]
        self.assertEqual(cited["references_file"], "paper/refs.bib")
        self.assertEqual(cited["entries"], 7)
        self.assertEqual(cited["resolved_by_doi"], 4)
        self.assertEqual(cited["resolved_by_journal_name"], 1)
        self.assertEqual(cited["unresolved"], 2)
        top = cited["journals"][0]
        self.assertEqual((top["display_name"], top["count"]), ("Cited Only Journal", 2))

    def test_only_journal_hosted_cited_works_count(self):
        self.start_api()
        self.with_refs()
        result = self.search()
        self.assertNotIn("arXiv (Cornell University)", self.by_name(result))
        self.assertEqual(result.json["query"]["cited"]["unresolved"], 2, "the dataset and the arXiv-named journal")

    def test_doi_batches_are_at_most_fifty_and_bounded(self):
        api = self.start_api()
        self.with_refs("\n".join(f"@article{{r{i}, doi={{10.7777/n.{i}}}, title={{T{i}}}}}" for i in range(260)))
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        doi_calls = [r for r in api.hits("/openalex/works") if r["params"].get("filter", "").startswith("doi:")]
        self.assertLessEqual(len(doi_calls), 4)
        self.assertGreaterEqual(len(doi_calls), 2)
        for call in doi_calls:
            self.assertLessEqual(len(call["params"]["filter"][4:].split("|")), 50)

    def test_journal_name_lookups_are_bounded(self):
        api = self.start_api()
        self.with_refs("\n".join(f"@article{{r{i}, journal={{Journal Number {i}}}, title={{T{i}}}}}"
                                 for i in range(60)))
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        lookups = [r for r in api.hits("/openalex/sources") if "search" in r["params"]]
        self.assertLessEqual(len(lookups), 15)
        self.assertGreaterEqual(len(lookups), 1)

    def test_a_failing_cited_lookup_degrades_with_a_note_and_never_fails_the_search(self):
        api = self.start_api(script={"/openalex/works": [None, 404]})
        self.with_refs()
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        self.assertTrue(any("cited" in n.lower() for n in result.json["notes"]), result.json["notes"])
        self.assertTrue(result.json["candidates"])

    def test_no_references_file_is_a_note_and_the_signal_is_inactive(self):
        self.start_api()
        result = self.search()
        self.assertIsNone(result.json["query"]["cited"]["references_file"])
        self.assertNotIn("cited_in_paper", result.json["query"]["scoring"]["active"])
        self.assertTrue(any("references" in n.lower() for n in result.json["notes"]), result.json["notes"])
        for candidate in result.json["candidates"]:
            self.assertEqual(candidate["cited_in_paper_count"], 0)

    def test_a_workspace_bib_other_than_refs_bib_is_used_when_refs_bib_is_absent(self):
        self.start_api()
        (self.workspace / "paper" / "library.bib").write_text(
            (FIXTURES / "refs.bib").read_text(encoding="utf-8"), encoding="utf-8")
        result = self.search()
        self.assertEqual(result.json["query"]["cited"]["references_file"], "paper/library.bib")


class TopicTests(JournalFinderCase):
    def test_matched_work_topics_form_the_paper_profile_and_boost_journals_that_share_them(self):
        api = self.start_api(topics=True)
        result = self.search()
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        topics = result.json["query"]["topics"]
        self.assertEqual(topics[0]["id"], "T1")
        self.assertAlmostEqual(sum(t["weight"] for t in topics), 1.0, places=2)
        by_name = {c["display_name"]: c for c in result.json["candidates"]}
        self.assertEqual(by_name["Neural Fixtures Letters"]["fit"]["topic_overlap"], 1.0)
        self.assertLess(by_name["Obscure Quarterly"]["fit"]["topic_overlap"],
                        by_name["Neural Fixtures Letters"]["fit"]["topic_overlap"])
        for candidate in result.json["candidates"]:
            self.assertTrue(0.0 <= candidate["fit"]["topic_overlap"] <= 1.0)
            self.assertTrue(candidate["topics"], "each candidate shows its main topics")
            self.assertEqual(set(candidate["topics"][0]), {"id", "name", "share"})

    def test_cited_work_topics_pull_the_profile_toward_the_cited_literature(self):
        self.start_api(topics=True)
        without = self.search().json["query"]["topics"]
        (self.workspace / "paper" / "refs.bib").write_text(
            (FIXTURES / "refs.bib").read_text(encoding="utf-8"), encoding="utf-8")
        with_refs = self.search().json["query"]["topics"]
        self.assertNotIn("T3", [t["id"] for t in without])
        self.assertIn("T3", [t["id"] for t in with_refs])

    def test_without_topics_the_signal_is_inactive(self):
        self.start_api(topics=False)
        result = self.search()
        self.assertNotIn("topic_overlap", result.json["query"]["scoring"]["active"])
        self.assertEqual(result.json["query"]["topics"], [])


class FitContractTests(JournalFinderCase):
    def test_every_candidate_exposes_its_components_and_the_documented_formula_holds(self):
        self.start_api(topics=True)
        (self.workspace / "paper" / "refs.bib").write_text(
            (FIXTURES / "refs.bib").read_text(encoding="utf-8"), encoding="utf-8")
        result = self.search()
        scoring = result.json["query"]["scoring"]
        self.assertEqual(set(scoring), {"formula", "weights", "active", "normalization"})
        self.assertAlmostEqual(sum(scoring["weights"].values()), 1.0, places=6)
        self.assertEqual(scoring["active"], ["similar_works", "cited_in_paper", "topic_overlap"])
        for candidate in result.json["candidates"]:
            fit = candidate["fit"]
            self.assertEqual(set(fit), {"similar_works", "cited_in_paper", "topic_overlap"})
            self.assertEqual(candidate["fit_score"], round(sum(scoring["weights"][k] * fit[k] for k in fit), 4))
        ordered = [c["fit_score"] for c in result.json["candidates"]]
        self.assertEqual(ordered, sorted(ordered, reverse=True))
        self.assertEqual([c["rank"] for c in result.json["candidates"]], list(range(1, len(ordered) + 1)))

    def test_with_the_proxy_world_only_the_similar_works_signal_is_active(self):
        self.start_api()
        result = self.search()
        self.assertEqual(result.json["query"]["scoring"]["active"], ["similar_works"])
        self.assertEqual([c["fit_score"] for c in result.json["candidates"]], [1.0, 0.6, 0.4, 0.2])
        self.assertEqual([c["fit"]["similar_works"] for c in result.json["candidates"]], [1.0, 0.6, 0.4, 0.2])

    def test_a_refusal_with_references_present_still_writes_nothing(self):
        api = self.start_api()
        (self.workspace / "paper" / "refs.bib").write_text(
            (FIXTURES / "refs.bib").read_text(encoding="utf-8"), encoding="utf-8")
        before = self.tree_snapshot()
        for args in (("--quartiles", "Q3-Q1"),):
            result = self.run_cli("search", "--workspace", str(self.workspace), *args)
            self.assertEqual(result.code, 2)
            self.assertEqual(result.json["error"], "QUARTILE_RANGE_INVALID")
        self.assertEqual(api.requests, [])
        self.assertEqual(self.tree_snapshot(), before)

    def test_unreachable_openalex_with_references_is_still_network_unavailable(self):
        (self.workspace / "paper" / "refs.bib").write_text(
            (FIXTURES / "refs.bib").read_text(encoding="utf-8"), encoding="utf-8")
        before = self.tree_snapshot()
        result = self.run_cli("search", "--workspace", str(self.workspace), "--quartiles", "Q1",
                              extra_env={"PAPERSMITH_OPENALEX_URL": "http://127.0.0.1:9",
                                         "PAPERSMITH_HTTP_RETRIES": "0", "PAPERSMITH_HTTP_TIMEOUT": "0.5"},
                              use_api=False)
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "NETWORK_UNAVAILABLE")
        self.assertEqual(self.tree_snapshot(), before)


class StatusTests(JournalFinderCase):
    def test_status_without_candidates_or_sjr(self):
        result = self.run_cli("status", "--workspace", str(self.workspace))
        self.assertEqual(result.code, 0, result.stdout)
        self.assertTrue(result.json["ok"])
        self.assertIsNone(result.json["candidates"])
        self.assertIsNone(result.json["sjr"])

    def test_status_summarises_the_candidates_and_the_sjr_in_use(self):
        self.start_api()
        self.import_fixture_sjr()
        self.assertEqual(self.search("--oa-only").code, 0)
        result = self.run_cli("status", "--workspace", str(self.workspace))
        self.assertEqual(result.code, 0, result.stdout)
        summary = result.json["candidates"]
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["quartiles"], ["Q1", "Q2", "Q3", "Q4"])
        self.assertEqual(summary["filters"]["oa_only"], True)
        self.assertEqual(summary["quartile_source_summary"], {"sjr": 0, "openalex-proxy": 2})
        self.assertTrue(summary["generated_at"])
        self.assertEqual(Path(summary["path"]), self.out_file)
        self.assertEqual(result.json["sjr"]["year"], 2019)
        self.assertTrue(result.json["sjr"]["file"].endswith("scimagojr-2019.csv"))

    def test_status_reads_only(self):
        self.start_api()
        self.assertEqual(self.search().code, 0)
        before = self.tree_snapshot()
        self.run_cli("status", "--workspace", str(self.workspace))
        self.assertEqual(self.tree_snapshot(), before)

    def test_corrupt_candidates_file_is_a_typed_refusal(self):
        self.out_file.write_text("{not json", encoding="utf-8")
        result = self.run_cli("status", "--workspace", str(self.workspace))
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "CANDIDATES_UNREADABLE")

    def test_status_workspace_absent(self):
        result = self.run_cli("status", "--workspace", str(self.tmp / "missing"))
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "WORKSPACE_ABSENT")


class StdoutContractTests(JournalFinderCase):
    def test_stdout_is_exactly_one_json_object_for_every_verb(self):
        self.start_api()
        runs = [
            self.run_cli("sjr-import", "--file", str(FIXTURES / "scimagojr-2019.csv")),
            self.search(),
            self.run_cli("status", "--workspace", str(self.workspace)),
            self.search(quartiles="nope"),
        ]
        for result in runs:
            with self.subTest(stdout=result.stdout[:60]):
                self.assertIsInstance(result.json, dict)
                self.assertEqual(len(result.stdout.strip().splitlines()), 1)
                self.assertIn("ok", result.json)
                if not result.json["ok"]:
                    self.assertIn("error", result.json)
                    self.assertIn("message", result.json)


if __name__ == "__main__":
    unittest.main()
