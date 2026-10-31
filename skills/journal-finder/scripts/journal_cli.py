#!/usr/bin/env python3
"""journal-finder: rank journals that publish work like this paper.

Stdlib only. One JSON object on stdout per call; a refusal is
`{"ok": false, "error": CODE, "message": ...}` with exit 2 and nothing written.

    journal_cli.py search --workspace <dir> --quartiles <range> [--oa-only]
                          [--max-apc N] [--max-review-days N] [--limit N]
                          [--sjr <csv>] [--out <path>] [--no-cache]
    journal_cli.py sjr-import --file <path> [--year YYYY]
    journal_cli.py status --workspace <dir>

`search` reads the paper's title, abstract, keywords and references, asks OpenAlex
for works like it, keeps the journals those works (and the paper's references)
appeared in, scores each by topical fit, attaches a quartile (SCImago SJR when a CSV
was imported, an OpenAlex citedness proxy otherwise, always labelled), a
review-time estimate (Crossref, then PubMed) and writes
`paper/journal-candidates.json` (schema 1). Nothing is ever submitted.

Fit score (`fit`, `fit_score`, `query.scoring`)
    fit_score = 0.45 * similar_works + 0.3 * cited_in_paper + 0.25 * topic_overlap
    similar_works   works like the paper that the journal published (one OpenAlex OR query of quoted key
                    phrases, last 6 years), over the largest count among the journals evaluated
    cited_in_paper  references of paper/refs.bib published in the journal (DOIs and arXiv ids in batches of
                    50, else exact journal name), over the largest count
    topic_overlap   histogram intersection between the paper's OpenAlex topic distribution (matched works
                    blended with cited works) and the journal's, over the largest overlap
    A component that is zero for every journal drops out and the other weights are rescaled to sum to 1.
    A journal the paper cites is kept even when no similar work was published there.
    Facets: the title's tail after "for" is the application, the rest the method; each gets its own OR query
    of at most 5 phrases and half the works budget. When both were searched, a journal with no application
    hit and application-topic overlap < 0.05 gets fit_score * 0.5 and the flag no-application-evidence.

Proxy quartile (`quartile_source: "openalex-proxy"`)
    share = journals of the same OpenAlex field (core journals with a
    positive 2-year mean citedness) that beat this journal's 2-year mean
    citedness / all of them. share < 0.25 is Q1, < 0.50 Q2, < 0.75 Q3, else Q4.
    It is an approximation of a citation percentile, never an SJR quartile.

Review time (`review_time`)
    Latest 40 research articles of the last 3 years. Days from `received` to
    `accepted` (Crossref `assertion` entries, else PubMed `esummary` history).
    Fewer than 5 dated articles reads as `source: "none"` with `n` kept. It
    estimates submission-to-acceptance including revisions, not time to first
    decision. Quartiles use linear interpolation between closest ranks.

Search
    Key phrases (keywords, title runs of content words, abstract bigrams seen twice; hyphenated compounds
    whole) are sent as `"phrase one" OR "phrase two" ...` with a last-6-years filter. OpenAlex `search`
    supports boolean OR; with plain terms it requires every one, so when the OR query matches fewer than 50
    works (or there are no phrases) the paper's top 10 terms (weight: 3 in keywords, 2 in title, plus
    abstract frequency) are tried 6 at a time, dropping the lowest-weighted until 50 works match (never
    below 2 terms). `query.phrases`, `query.terms` and `query.search_mode` say which ran.

Budget and cache
    OpenAlex's keyless budget is USD 0.10/day per IP. Successful answers are cached on disk (1 day for
    searches, 7 for lookups; never errors; --no-cache bypasses). A 429 asking for more than 60 s is a spent
    quota: no retry, NETWORK_UNAVAILABLE naming OPENALEX_API_KEY. `api_calls` reports calls made/cached
    and the budget state.

Environment
    PAPERSMITH_OPENALEX_URL / _CROSSREF_URL / _PUBMED_URL   base URLs (tests)
    PAPERSMITH_CONTACT_EMAIL     polite `mailto`/User-Agent/NCBI `email` (never hard-coded)
    NCBI_API_KEY, OPENALEX_API_KEY                         sent only when set
    PAPERSMITH_SJR_DIR           SJR cache (default ~/.cache/papersmith/sjr)
    PAPERSMITH_HTTP_TIMEOUT      per-request seconds (default 15)
    PAPERSMITH_HTTP_RETRIES      retries on 429/5xx/transport errors (default 3)
    PAPERSMITH_HTTP_BACKOFF      first backoff in seconds, doubling (default 0.5)
    PAPERSMITH_JOURNAL_DEADLINE  total seconds for one search (default 300)
    PAPERSMITH_JOURNAL_MAX_WORKS works fetched from OpenAlex (default 200)
    PAPERSMITH_OPENALEX_MIN_INTERVAL  seconds between OpenAlex calls (default 0.11)
    PAPERSMITH_JOURNAL_CACHE_DIR response cache (default ~/.cache/papersmith/journal-finder/http)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import http.client
import io
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCHEMA = 1
DEFAULT_LIMIT = 15
MAX_LIMIT = 50
MAX_TERMS = 10
START_TERMS = 6
MIN_TERMS = 2
MIN_MATCHES = 50
DEFAULT_MAX_WORKS = 200
WORKS_PAGE_SIZE = 100
MAX_SOURCES = 60
MIN_SOURCES = 30
RECENT_YEARS = 6
MAX_PHRASES = 10
MAX_PHRASE_WORDS = 4
NAME_LOOKUP_RESULTS = 25
MIN_BIGRAM_COUNT = 2
DOI_BATCH = 50
MAX_DOI_BATCHES = 4
MAX_NAME_LOOKUPS = 15
MAX_CITED_ONLY = 20
WORK_TOPICS_PER_WORK = 3
SOURCE_TOPICS_SHOWN = 5
FIT_WEIGHTS = {"similar_works": 0.45, "cited_in_paper": 0.30, "topic_overlap": 0.25}
WORK_SELECT = "id,title,publication_year,doi,primary_location,topics"
WORKERS = 4
REVIEW_SAMPLE = 40
REVIEW_YEARS = 3
REVIEW_MIN_N = 5
QUOTA_RETRY_AFTER = 60.0   # a 429 asking for a longer wait than this is a spent quota, not a burst
CACHE_TTL_SEARCH = 86400.0
CACHE_TTL_LOOKUP = 7 * 86400.0
VOLATILE_PARAMS = ("api_key", "mailto", "email")
FACET_GATE = 0.5
APP_TOPIC_MIN = 0.05
OPENALEX_DEFAULT = "https://api.openalex.org"
CROSSREF_DEFAULT = "https://api.crossref.org"
PUBMED_DEFAULT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
SJR_DOWNLOAD_URL = "https://www.scimagojr.com/journalrank.php"
PUBMED_MIN_INTERVAL = 0.34  # strictly under 3 requests per second
CROSSREF_MIN_INTERVAL = 0.2
SJR_FIRST_YEAR = 1999
SJR_REQUIRED = ("Title", "Issn", "SJR", "SJR Best Quartile", "Categories", "Publisher")
SOURCE_SELECT = ("id,display_name,issn_l,issn,type,host_organization_name,is_oa,is_in_doaj,"
                 "apc_usd,homepage_url,summary_stats,topics")

REFUSAL_CODES = (
    "QUARTILE_RANGE_INVALID", "PAPER_ABSENT", "NETWORK_UNAVAILABLE", "SJR_FILE_INVALID",
    "WORKSPACE_ABSENT", "FILTER_INVALID", "CANDIDATES_UNREADABLE", "USAGE", "INTERNAL_ERROR",
)


class Refusal(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class HttpFailure(Exception):
    def __init__(self, message: str, status: int | None = None, deadline: bool = False, quota: bool = False):
        super().__init__(message)
        self.status = status
        self.deadline = deadline
        self.quota = quota


# --------------------------------------------------------------------------- environment


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _contact() -> str:
    return os.environ.get("PAPERSMITH_CONTACT_EMAIL", "").strip()


def _base(name: str, default: str) -> str:
    return os.environ.get(name, "").strip().rstrip("/") or default


def sjr_dir() -> Path:
    override = os.environ.get("PAPERSMITH_SJR_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "papersmith" / "sjr"


# --------------------------------------------------------------------------- HTTP


class RateLimiter:
    """Spaces calls at least `min_interval` apart across threads."""

    def __init__(self, min_interval: float, clock=time.monotonic, sleep=time.sleep):
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            if self._last is not None:
                gap = self.min_interval - (self._clock() - self._last)
                if gap > 0:
                    self._sleep(gap)
            self._last = self._clock()


class Deadline:
    def __init__(self, seconds: float):
        self.seconds = seconds
        self._end = time.monotonic() + seconds

    def remaining(self) -> float:
        return self._end - time.monotonic()


def cache_dir() -> Path:
    override = os.environ.get("PAPERSMITH_JOURNAL_CACHE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "papersmith" / "journal-finder" / "http"


class ResponseCache:
    """Successful JSON answers on disk, keyed by URL without credentials.

    A search (`search` or `term` parameter) lives CACHE_TTL_SEARCH, any other lookup CACHE_TTL_LOOKUP. Errors
    are never stored and a cache that cannot be read or written is silently a miss.
    """

    def __init__(self, directory: Path, enabled: bool = True):
        self.directory = directory
        self.enabled = enabled

    @staticmethod
    def _canonical(url: str, params: dict) -> str:
        kept = sorted((k, str(v)) for k, v in (params or {}).items() if k not in VOLATILE_PARAMS)
        return f"{url}?{urllib.parse.urlencode(kept)}" if kept else url

    @staticmethod
    def _ttl(params: dict) -> float:
        return CACHE_TTL_SEARCH if ("search" in params or "term" in params) else CACHE_TTL_LOOKUP

    def _path(self, canonical: str) -> Path:
        return self.directory / (hashlib.sha256(canonical.encode("utf-8")).hexdigest() + ".json")

    def get(self, url: str, params: dict):
        if not self.enabled:
            return None
        try:
            document = json.loads(self._path(self._canonical(url, params)).read_text(encoding="utf-8"))
            if time.time() - float(document["fetched_at"]) <= self._ttl(params):
                return document["data"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def put(self, url: str, params: dict, data) -> None:
        if not self.enabled:
            return
        canonical = self._canonical(url, params)
        try:
            _atomic_write(self._path(canonical), json.dumps(
                {"fetched_at": time.time(), "url": canonical, "data": data}).encode("utf-8"))
        except (OSError, TypeError, ValueError):
            pass


class CallStats:
    """How many HTTP requests were made or served from the cache, per service, and the OpenAlex budget."""

    SERVICES = ("openalex", "crossref", "pubmed")

    def __init__(self):
        self._lock = threading.Lock()
        self.counts = {name: {"made": 0, "cached": 0} for name in self.SERVICES}
        self.remaining_usd: float | None = None
        self.limit_usd: float | None = None
        self.retry_after: int | None = None

    def record(self, service: str, cached: bool) -> None:
        with self._lock:
            slot = self.counts.setdefault(service, {"made": 0, "cached": 0})
            slot["cached" if cached else "made"] += 1

    def note_headers(self, headers) -> None:
        try:
            remaining = headers.get("x-ratelimit-remaining-usd")
            limit = headers.get("x-ratelimit-limit-usd")
            with self._lock:
                if remaining is not None:
                    self.remaining_usd = float(remaining)
                if limit is not None:
                    self.limit_usd = float(limit)
        except (AttributeError, TypeError, ValueError):
            pass

    def note_exhausted(self, retry_after: float) -> None:
        with self._lock:
            self.retry_after = int(retry_after)

    def summary(self, cache: ResponseCache) -> dict:
        with self._lock:
            made = sum(v["made"] for v in self.counts.values())
            cached = sum(v["cached"] for v in self.counts.values())
            if self.retry_after is not None or (self.remaining_usd is not None and self.remaining_usd <= 0):
                state = "exhausted"
            elif self.remaining_usd is not None:
                state = "ok"
            else:
                state = "unknown"
            return {"made": made, "cached": cached,
                    "by_service": {k: dict(v) for k, v in self.counts.items()},
                    "cache": {"enabled": cache.enabled, "dir": str(cache.directory)},
                    "budget": {"state": state, "remaining_usd": self.remaining_usd,
                               "limit_usd": self.limit_usd, "retry_after_seconds": self.retry_after}}


class Http:
    def __init__(self, deadline: Deadline, cache: ResponseCache | None = None, stats: CallStats | None = None):
        self.deadline = deadline
        self.cache = cache or ResponseCache(cache_dir(), enabled=False)
        self.stats = stats or CallStats()
        self.timeout = _env_float("PAPERSMITH_HTTP_TIMEOUT", 15.0)
        self.retries = max(0, _env_int("PAPERSMITH_HTTP_RETRIES", 3))
        self.backoff = max(0.0, _env_float("PAPERSMITH_HTTP_BACKOFF", 0.5))
        contact = _contact()
        agent = "papersmith-journal-finder/1.0"
        self.user_agent = f"{agent} (mailto:{contact})" if contact else agent

    def get_json(self, url: str, params: dict, limiter: RateLimiter | None = None,
                 service: str = "http") -> dict:
        cached = self.cache.get(url, params)
        if cached is not None:
            self.stats.record(service, cached=True)
            return cached
        full = f"{url}?{urllib.parse.urlencode(params)}" if params else url
        request = urllib.request.Request(
            full, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        last = "no attempt made"
        for attempt in range(self.retries + 1):
            remaining = self.deadline.remaining()
            if remaining <= 0:
                raise HttpFailure(f"total deadline of {self.deadline.seconds:g}s exceeded", deadline=True)
            if limiter is not None:
                limiter.wait()
            retry_after = 0.0
            self.stats.record(service, cached=False)
            try:
                with urllib.request.urlopen(request, timeout=max(0.05, min(self.timeout, remaining))) as response:
                    raw = response.read()
                    self.stats.note_headers(response.headers)
                try:
                    data = json.loads(raw.decode("utf-8"))
                except ValueError as exc:
                    raise HttpFailure(f"answer is not JSON ({exc})", status=200) from exc
                self.cache.put(url, params, data)
                return data
            except urllib.error.HTTPError as exc:
                self.stats.note_headers(exc.headers)
                if exc.code != 429 and not 500 <= exc.code <= 599:
                    raise HttpFailure(f"HTTP {exc.code} from {urllib.parse.urlsplit(url).netloc}",
                                      status=exc.code) from exc
                last = f"HTTP {exc.code}"
                try:
                    asked = float(exc.headers.get("Retry-After", "0"))
                except (TypeError, ValueError):
                    asked = 0.0
                if exc.code == 429 and asked > QUOTA_RETRY_AFTER:
                    self.stats.note_exhausted(asked)
                    raise HttpFailure(f"HTTP 429 from {urllib.parse.urlsplit(url).netloc}: the request quota is "
                                      f"spent, retry after {int(asked)} s", status=429, quota=True) from exc
                retry_after = min(10.0, asked)
                status = exc.code
            except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
                reason = getattr(exc, "reason", exc)
                last = f"{type(reason).__name__}: {reason}"
                status = None
            if attempt < self.retries:
                pause = min(max(self.backoff * (2 ** attempt), retry_after), max(0.0, self.deadline.remaining()))
                if pause > 0:
                    time.sleep(pause)
        raise HttpFailure(f"{last} from {urllib.parse.urlsplit(url).netloc} after "
                          f"{self.retries + 1} attempt(s)", status=status)


# --------------------------------------------------------------------------- quartile range


def parse_quartile_range(text: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*Q([1-4])\s*(?:-\s*Q?([1-4])\s*)?", text or "", re.IGNORECASE)
    if match:
        low = int(match.group(1))
        high = int(match.group(2) or low)
        if low <= high:
            return low, high
    raise Refusal("QUARTILE_RANGE_INVALID",
                  f"{text!r} is not a quartile or an ascending contiguous range such as Q1, Q2-Q3 or Q1-Q4")


def proxy_quartile(share_above: float) -> str:
    if share_above < 0.25:
        return "Q1"
    if share_above < 0.50:
        return "Q2"
    if share_above < 0.75:
        return "Q3"
    return "Q4"


# --------------------------------------------------------------------------- dates and statistics

_DATE_FORMATS = ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y")


def parse_date(text) -> dt.date | None:
    if not isinstance(text, str):
        return None
    cleaned = text.strip().replace(".", "").replace("Sept ", "Sep ")
    if not cleaned:
        return None
    cleaned = re.split(r"[T ](?=\d{1,2}:\d{2})", cleaned)[0].strip()
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def percentile(sorted_values: list[float], fraction: float) -> float:
    position = fraction * (len(sorted_values) - 1)
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return float(sorted_values[low])
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def summarize_days(values: list[float]) -> tuple[float, float, float]:
    ordered = sorted(values)
    return tuple(round(percentile(ordered, f), 1) for f in (0.5, 0.25, 0.75))  # type: ignore[return-value]


def crossref_item_dates(item: dict) -> tuple:
    found: dict[str, dt.date | None] = {}
    for assertion in item.get("assertion") or []:
        name = str(assertion.get("name", "")).lower()
        if name in ("received", "accepted", "first_online") and name not in found:
            found[name] = parse_date(assertion.get("value"))
    return found.get("received"), found.get("accepted"), found.get("first_online")


def pubmed_history_dates(history) -> tuple:
    found: dict[str, dt.date | None] = {}
    for entry in history or []:
        status = str(entry.get("pubstatus", "")).lower()
        if status in ("received", "accepted", "epublish") and status not in found:
            found[status] = parse_date(entry.get("date"))
    return found.get("received"), found.get("accepted"), found.get("epublish")


def review_deltas(triples) -> tuple[list[int], list[int]]:
    """Received->accepted days per article, and accepted->online days for those same articles."""
    review: list[int] = []
    online: list[int] = []
    for received, accepted, first_online in triples:
        if received is None or accepted is None or accepted < received:
            continue
        review.append((accepted - received).days)
        if first_online is not None and first_online >= accepted:
            online.append((first_online - accepted).days)
    return review, online


# --------------------------------------------------------------------------- paper profile


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _strip_comments(tex: str) -> str:
    return re.sub(r"(?<!\\)%[^\n]*", "", tex)


def _brace_argument(tex: str, open_index: int) -> str:
    depth = 0
    for index in range(open_index, len(tex)):
        char = tex[index]
        if char == "\\":
            continue
        if char == "{" and tex[index - 1:index] != "\\":
            depth += 1
        elif char == "}" and tex[index - 1:index] != "\\":
            depth -= 1
            if depth == 0:
                return tex[open_index + 1:index]
    return tex[open_index + 1:]


_DROPPED = re.compile(r"\\(?:cite[a-z]*|ref|eqref|label|footnote|thanks|url|href)\*?(?:\[[^\]]*\])?\{[^{}]*\}")


def _tex_to_text(tex: str) -> str:
    text = re.sub(r"\$\$.*?\$\$|\$[^$]*\$|\\\(.*?\\\)", " ", tex, flags=re.DOTALL)
    text = _DROPPED.sub(" ", text)
    text = re.sub(r"\\[\"'`^~=.]\{?([A-Za-z])\}?", r"\1", text)
    text = re.sub(r"\\(?:begin|end)\{[^}]*\}", " ", text)
    text = text.replace("\\\\", " ")
    text = re.sub(r"\\([%&_#$])", r"\1", text)
    text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?", " ", text)
    text = text.replace("~", " ").replace("{", " ").replace("}", " ")
    return re.sub(r"\s+", " ", text).strip()


_KEYWORD_LINE = re.compile(
    r"^[ \t]*(?:\\noindent\s*)?(?:\\(?:textbf|emph|textit)\{)?\s*(?:Key\s?words?|Index Terms)\s*[:.\u2014\u2013-]*"
    r"\s*\}?\s*[:.\u2014\u2013-]*\s*(?P<rest>\S.*)$", re.IGNORECASE | re.MULTILINE)


def _split_keywords(raw: str) -> list[str]:
    prepared = re.sub(r"\\(?:sep|and)\b", ",", raw)
    cleaned = _tex_to_text(prepared)
    out = []
    for piece in re.split(r"[,;\u00b7\u2022]", cleaned):
        piece = piece.strip().rstrip(".").strip()
        if piece:
            out.append(piece)
    return out


def _find_title(tex: str) -> str:
    match = re.search(r"\\title\s*(?:\[[^\]]*\])?\s*\{", tex)
    if not match:
        return ""
    return _tex_to_text(_brace_argument(tex, match.end() - 1))


def _find_abstract(tex: str) -> str:
    match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.DOTALL)
    return _tex_to_text(match.group(1)) if match else ""


def _find_keywords(tex: str) -> list[str]:
    match = re.search(r"\\keywords\s*\{", tex)
    if match:
        return _split_keywords(_brace_argument(tex, match.end() - 1))
    match = re.search(r"\\begin\{(?:keyword|keywords|IEEEkeywords)\}(.*?)\\end\{(?:keyword|keywords|IEEEkeywords)\}",
                      tex, re.DOTALL)
    if match:
        return _split_keywords(match.group(1))
    match = _KEYWORD_LINE.search(tex)
    if match:
        return _split_keywords(match.group("rest"))
    return []


def _profile_from_sections(workspace: Path) -> dict:
    title, abstract, keywords = "", "", []
    folder = workspace / "paper" / "sections"
    for path in sorted(folder.glob("*")) if folder.is_dir() else []:
        if not path.is_file() or path.suffix.lower() not in (".tex", ".md", ".txt"):
            continue
        name = path.stem.lower()
        text = _strip_comments(_read_text(path)) if path.suffix.lower() == ".tex" else _read_text(path)
        if "title" in name and not title:
            title = _find_title(text)
            if not title:
                heading = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
                first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
                title = _tex_to_text((heading.group(1) if heading else first).strip())
        if "abstract" in name and not abstract:
            abstract = _find_abstract(text)
            if not abstract:
                body = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)
                abstract = _tex_to_text(body)
        if ("keyword" in name or "title" in name) and not keywords:
            keywords = _find_keywords(text)
    return {"title": title, "abstract": abstract, "keywords": keywords}


def extract_profile(workspace: Path) -> dict:
    tex = _strip_comments(_read_text(workspace / "paper" / "main.tex"))
    profile = {"title": _find_title(tex), "abstract": _find_abstract(tex), "keywords": _find_keywords(tex)}
    if not (profile["title"] and profile["abstract"] and profile["keywords"]):
        fallback = _profile_from_sections(workspace)
        for key in profile:
            if not profile[key]:
                profile[key] = fallback[key]
    if not profile["title"] and not profile["abstract"]:
        raise Refusal("PAPER_ABSENT", f"no title and no abstract could be read from {workspace}/paper/main.tex "
                                      "or paper/sections/")
    return profile


_STOPWORDS = frozenset(
    "a an and are as at be been but by can could did do does for from had has have how in into is it its may more "
    "most of on or our such than that the their these this those to under using use used via was we were what when "
    "which while who will with within without not also both each other over between through towards toward based "
    "new approach method methods results show shows paper study proposed propose present presented however thus "
    "therefore since then there here whose among across per data analysis model models network networks system "
    "systems performance feature features framework algorithm algorithms accuracy evaluation experiments "
    "experimental novel improve improved improves achieve achieves achieved reach reaches subjects "
    "cohort demonstrate demonstrates".split())


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3 and not t.isdigit()
            and t not in _STOPWORDS]


def build_terms(profile: dict) -> list[str]:
    """Top MAX_TERMS tokens by weight: 3 if in the keywords, 2 if in the title, plus abstract frequency."""
    weights: dict[str, float] = {}
    order: dict[str, int] = {}

    def see(token: str) -> None:
        order.setdefault(token, len(order))

    keyword_tokens = [t for k in profile.get("keywords", []) for t in _tokens(k)]
    title_tokens = _tokens(profile.get("title", ""))
    abstract_tokens = _tokens(profile.get("abstract", ""))
    for token in keyword_tokens:
        see(token)
    for token in title_tokens:
        see(token)
    for token in abstract_tokens:
        see(token)
    for token in set(keyword_tokens):
        weights[token] = weights.get(token, 0) + 3
    for token in set(title_tokens):
        weights[token] = weights.get(token, 0) + 2
    for token in abstract_tokens:
        weights[token] = weights.get(token, 0) + 1
    ranked = sorted(weights, key=lambda t: (-weights[t], order[t]))
    return ranked[:MAX_TERMS]


# --------------------------------------------------------------------------- key phrases

_PHRASE_KEEP = frozenset("data model models network networks system systems feature features framework "
                         "algorithm algorithms analysis".split())
#: words that end a phrase; the generic nouns above stay inside phrases ("data re-uploading")
_PHRASE_BREAKS = _STOPWORDS - _PHRASE_KEEP
_PHRASE_WORD = re.compile(r"[^\W_]+(?:-[^\W_]+)*")
_PHRASE_SPLIT = re.compile(r"[.,;:!?()\[\]{}\"\u201c\u201d/\u2014\u2013|]+|\s-\s")
_PARENTHETICAL = re.compile(r"\(([^()]*)\)")


def _phrase_chunks(text: str) -> list[list[str]]:
    """Runs of content words between punctuation and function words; hyphenated compounds stay whole."""
    chunks: list[list[str]] = []
    for segment in _PHRASE_SPLIT.split(text.lower()):
        run: list[str] = []
        for token in _PHRASE_WORD.findall(segment):
            if len(token) < 2 or token.isdigit() or token in _PHRASE_BREAKS:
                if run:
                    chunks.append(run)
                run = []
            else:
                run.append(token)
        if run:
            chunks.append(run)
    return chunks


def _pieces(chunk: list[str], size: int) -> list[list[str]]:
    """The chunk itself, or consecutive non-overlapping pieces of `size` words when it is longer."""
    return [chunk[i:i + size] for i in range(0, len(chunk), size)]


def _ranked_phrases(profile: dict) -> tuple[list[tuple[str, ...]], set[tuple[str, ...]]]:
    """Every surviving candidate phrase, best first, and the phrases that come from application keywords.

    Keywords weigh 3 (a keyword may be a single word), title chunks 2 (two words or more, or one hyphenated
    compound), abstract bigrams their frequency when at least MIN_BIGRAM_COUNT and sharing a word with a
    keyword or title phrase (boilerplate such as "statistically significant" never qualifies). A chunk longer
    than MAX_PHRASE_WORDS is cut into consecutive pieces. A phrase inside a longer keyword or title phrase is
    dropped, except that only a longer keyword absorbs a keyword; so is a title or abstract phrase that
    contains a multi-word keyword (every work matching it matches the keyword). Ties prefer longer phrases,
    then first appearance.
    """
    weights: dict[tuple[str, ...], float] = {}
    from_keywords: set[tuple[str, ...]] = set()
    from_title: set[tuple[str, ...]] = set()
    application_keywords: set[tuple[str, ...]] = set()
    order: dict[tuple[str, ...], int] = {}
    app_words = application_words(profile.get("title") or "")

    def add(words: list[str], weight: float, origin: set[tuple[str, ...]] | None) -> None:
        key = tuple(words)
        order.setdefault(key, len(order))
        weights[key] = weights.get(key, 0.0) + weight
        if origin is not None:
            origin.add(key)

    def multi(words: list[str]) -> bool:
        return len(words) > 1 or "-" in words[0]

    for keyword in profile.get("keywords") or []:
        pieces = [_PARENTHETICAL.sub(" ", keyword), *_PARENTHETICAL.findall(keyword)]
        in_application = bool(app_words & {w for c in _phrase_chunks(keyword) for w in c})
        for piece in pieces:
            for chunk in _phrase_chunks(piece):
                for words in _pieces(chunk, MAX_PHRASE_WORDS):
                    add(words, 3.0, from_keywords)
                    if in_application:
                        application_keywords.add(tuple(words))
    for chunk in _phrase_chunks(profile.get("title") or ""):
        for words in _pieces(chunk, MAX_PHRASE_WORDS):
            if multi(words):
                add(words, 2.0, from_title)
    declared_words = from_keywords | from_title
    bigrams: dict[tuple[str, ...], int] = {}
    for chunk in _phrase_chunks(profile.get("abstract") or ""):
        for i in range(len(chunk) - 1):
            pair = tuple(chunk[i:i + 2])
            bigrams[pair] = bigrams.get(pair, 0) + 1
    topical = {word for key in declared_words for word in key}
    for pair, count in bigrams.items():
        if count >= MIN_BIGRAM_COUNT and topical.intersection(pair):
            add(list(pair), float(count), None)

    def inside(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
        return len(long) > len(short) and any(long[i:i + len(short)] == short
                                              for i in range(len(long) - len(short) + 1))

    declared = from_keywords | from_title

    def subsumed(key: tuple[str, ...]) -> bool:
        # a keyword is only absorbed by a longer keyword; anything else by any longer keyword or title phrase
        if any(inside(key, other) for other in (from_keywords if key in from_keywords else declared)):
            return True
        # a non-keyword phrase that contains a multi-word keyword adds nothing to an OR query
        return key not in from_keywords and any(inside(kw, key) for kw in from_keywords if multi(list(kw)))

    kept = [k for k in weights if not subsumed(k)]

    def rank(key: tuple[str, ...]):
        single = not multi(list(key))
        return (-(weights[key] - (1 if single else 0)), -len(key), order[key])

    kept.sort(key=rank)
    return kept, application_keywords


_APPLICATION_MARKER = re.compile(r"\s(?:applied to|towards?|for)\s", re.IGNORECASE)


def application_tail(title: str) -> str | None:
    """The part of the title after its first ` for `, ` applied to `, ` towards ` or ` toward `, if any."""
    match = _APPLICATION_MARKER.search(title or "")
    if not match or not _phrase_chunks(title[:match.start()]):
        return None
    tail = title[match.end():].strip()
    return tail or None


def application_words(title: str) -> set[str]:
    tail = application_tail(title)
    return {w for chunk in _phrase_chunks(tail) for w in chunk} if tail else set()


def build_phrase_facets(profile: dict) -> dict[str, list[str]]:
    """Key phrases split into the paper's `method` and `application` facets.

    The application is the title's tail (`... for <application>`): a phrase belongs to it when it shares a
    word with the tail, or comes from a keyword that does (so "Electroencephalography (EEG)" follows its
    acronym). When both facets have phrases each keeps at most MAX_PHRASES // 2, so neither can take more
    than half of the query; otherwise the one facet keeps up to MAX_PHRASES.
    """
    ranked, application_keywords = _ranked_phrases(profile)
    app_words = application_words(profile.get("title") or "")
    facets: dict[str, list[tuple[str, ...]]] = {"method": [], "application": []}
    for key in ranked:
        in_application = key in application_keywords or bool(app_words & set(key))
        facets["application" if in_application else "method"].append(key)
    both = bool(facets["method"]) and bool(facets["application"])
    cap = MAX_PHRASES // 2 if both else MAX_PHRASES
    return {name: [" ".join(k).replace('"', "") for k in keys[:cap]] for name, keys in facets.items() if keys}


def build_phrases(profile: dict) -> list[str]:
    return [phrase for phrases in build_phrase_facets(profile).values() for phrase in phrases]


def or_query(phrases: list[str]) -> str:
    return " OR ".join(f'"{p}"' for p in phrases)


def recency_start(today: dt.date, years: int = RECENT_YEARS) -> dt.date:
    try:
        return today.replace(year=today.year - years)
    except ValueError:  # 29 February
        return today.replace(year=today.year - years, day=28)


# --------------------------------------------------------------------------- SJR


def normalize_issn(value) -> str:
    return re.sub(r"[\s-]", "", str(value or "")).upper()


def year_from_name(name: str) -> int | None:
    match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", name)
    return int(match.group(1)) if match else None


class SjrTable:
    def __init__(self, rows: int, by_issn: dict[str, dict]):
        self.rows = rows
        self.by_issn = by_issn

    def lookup(self, issns) -> dict | None:
        for issn in issns or []:
            hit = self.by_issn.get(normalize_issn(issn))
            if hit is not None:
                return dict(hit)
        return None


def _parse_categories(cell: str) -> list[dict]:
    out = []
    for segment in cell.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        match = re.fullmatch(r"(.*?)\s*\((Q[1-4])\)", segment)
        out.append({"name": match.group(1), "quartile": match.group(2)} if match
                   else {"name": segment, "quartile": None})
    return out


def _invalid(message: str) -> Refusal:
    return Refusal("SJR_FILE_INVALID", message)


def read_sjr(path: Path) -> SjrTable:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise _invalid(f"{path} cannot be read ({exc.strerror or exc})") from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _invalid(f"{path} is not UTF-8 text; download the CSV again from {SJR_DOWNLOAD_URL}") from exc
    if not text.strip() or "\x00" in text:
        raise _invalid(f"{path} is empty or not a CSV")
    header_line = text.splitlines()[0]
    delimiter = ";" if header_line.count(";") >= header_line.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = [h.strip().lower() for h in next(reader, [])]
    missing = [name for name in SJR_REQUIRED if name.lower() not in header]
    if missing:
        raise _invalid(f"{path} lacks the SCImago column(s): {', '.join(missing)}; use "
                       f"'Download data' at {SJR_DOWNLOAD_URL}")
    column = {name: header.index(name.lower()) for name in SJR_REQUIRED}
    rows = 0
    by_issn: dict[str, dict] = {}
    for record in reader:
        if not any(cell.strip() for cell in record):
            continue
        rows += 1

        def cell(name: str) -> str:
            index = column[name]
            return record[index].strip() if index < len(record) else ""

        quartile = cell("SJR Best Quartile").upper()
        try:
            value = float(cell("SJR").replace(",", "."))
        except ValueError:
            value = None
        row = {"title": cell("Title"), "publisher": cell("Publisher"), "value": value,
               "quartile": quartile if re.fullmatch(r"Q[1-4]", quartile) else None,
               "categories": _parse_categories(cell("Categories"))}
        for issn in re.split(r"[,;\s]+", cell("Issn")):
            key = normalize_issn(issn)
            if key:
                by_issn.setdefault(key, row)
    if rows == 0:
        raise _invalid(f"{path} has a header but no journal rows")
    return SjrTable(rows, by_issn)


def latest_cached_sjr() -> tuple[Path, int] | None:
    folder = sjr_dir()
    best: tuple[Path, int] | None = None
    for path in folder.glob("scimagojr-*.csv") if folder.is_dir() else []:
        year = year_from_name(path.name)
        if year is not None and (best is None or year > best[1]):
            best = (path, year)
    return best


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def cmd_sjr_import(args: argparse.Namespace) -> dict:
    source = Path(args.file).expanduser()
    if not source.is_file():
        raise _invalid(f"{source} does not exist")
    table = read_sjr(source)
    year = args.year if args.year is not None else year_from_name(source.name)
    if year is None:
        raise _invalid(f"the year of {source.name} is unknown; pass --year YYYY")
    if not SJR_FIRST_YEAR <= year <= dt.date.today().year + 1:
        raise _invalid(f"year {year} is outside {SJR_FIRST_YEAR}..{dt.date.today().year + 1}")
    destination = sjr_dir() / f"scimagojr-{year}.csv"
    _atomic_write(destination, source.read_bytes())
    return {"ok": True, "rows": table.rows, "year": year, "path": str(destination)}


# --------------------------------------------------------------------------- OpenAlex


class Services:
    def __init__(self, deadline: Deadline, cache: ResponseCache | None = None):
        self.stats = CallStats()
        self.cache = cache or ResponseCache(cache_dir(), enabled=False)
        self.http = Http(deadline, self.cache, self.stats)
        self.openalex = _base("PAPERSMITH_OPENALEX_URL", OPENALEX_DEFAULT)
        self.crossref = _base("PAPERSMITH_CROSSREF_URL", CROSSREF_DEFAULT)
        self.pubmed = _base("PAPERSMITH_PUBMED_URL", PUBMED_DEFAULT)
        self.openalex_limiter = RateLimiter(max(0.0, _env_float("PAPERSMITH_OPENALEX_MIN_INTERVAL", 0.11)))
        self.crossref_limiter = RateLimiter(CROSSREF_MIN_INTERVAL)
        self.pubmed_limiter = RateLimiter(PUBMED_MIN_INTERVAL)

    def openalex_get(self, path: str, params: dict) -> dict:
        params = dict(params)
        if _contact():
            params["mailto"] = _contact()
        if os.environ.get("OPENALEX_API_KEY"):
            params["api_key"] = os.environ["OPENALEX_API_KEY"]
        try:
            return self.http.get_json(f"{self.openalex}{path}", params, self.openalex_limiter, "openalex")
        except HttpFailure as exc:
            if exc.quota:
                raise HttpFailure(f"{exc}; set OPENALEX_API_KEY (a free key has its own daily budget) or wait "
                                  "for the reset", status=429, quota=True) from exc
            raise

    def crossref_get(self, path: str, params: dict) -> dict:
        params = dict(params)
        if _contact():
            params["mailto"] = _contact()
        return self.http.get_json(f"{self.crossref}{path}", params, self.crossref_limiter, "crossref")

    def pubmed_get(self, path: str, params: dict) -> dict:
        params = {**params, "tool": "papersmith"}
        if _contact():
            params["email"] = _contact()
        if os.environ.get("NCBI_API_KEY"):
            params["api_key"] = os.environ["NCBI_API_KEY"]
        return self.http.get_json(f"{self.pubmed}{path}", params, self.pubmed_limiter, "pubmed")


def _short_id(url: str) -> str:
    return str(url).rstrip("/").rsplit("/", 1)[-1]


def fetch_similar_sources(services: Services, facets: dict[str, list[str]], terms: list[str], max_works: int,
                          today: dt.date, title: str = "") -> dict:
    """Journals hosting works like the paper, and the topics of those works.

    One OR query of quoted phrases per facet (journal articles of the last RECENT_YEARS), each with an equal
    share of `max_works`. A facet whose query matches fewer than MIN_MATCHES works is dropped; when none
    survives (or there are no phrases) the AND relaxation of `terms` runs instead. Returns {sources: [{id,
    name, count, works, first, ids, facet_ids}], scanned, terms, phrases, mode, notes, queries,
    topics_by_facet, topic_names, tail}.
    """
    notes: list[str] = []
    used = terms[:START_TERMS]
    base_filter = "primary_location.source.type:journal,type:article"

    def request(search: str, flt: str, page: int, per_page: int) -> dict:
        return services.openalex_get("/works", {
            "search": search, "filter": flt, "per-page": per_page, "page": page, "select": WORK_SELECT})

    kept: list[dict] = []
    names = [name for name, phrases in facets.items() if phrases]
    share = max(1, max_works // max(1, len(names)))
    recent = base_filter + f",from_publication_date:{recency_start(today).isoformat()}"
    for name in names:
        per_page = max(1, min(WORKS_PAGE_SIZE, share))
        search = or_query(facets[name])
        first = request(search, recent, 1, per_page)
        count = (first.get("meta") or {}).get("count")
        if count is None or count >= MIN_MATCHES:
            kept.append({"facet": name, "phrases": list(facets[name]), "search": search, "filter": recent,
                         "per_page": per_page, "data": first, "matched": count})
        else:
            notes.append(f"the {name} phrase query matched only {count} works (fewer than {MIN_MATCHES}) and "
                         "was dropped")
    if not kept:
        search, per_page = " ".join(used), max(1, min(WORKS_PAGE_SIZE, max_works))
        data = request(search, base_filter, 1, per_page)
        while len(used) > MIN_TERMS:
            count = (data.get("meta") or {}).get("count")
            if count is None or count >= MIN_MATCHES:
                break
            dropped = used.pop()
            notes.append(f"only {count} works matched every term; dropped '{dropped}' and searched again")
            search = " ".join(used)
            data = request(search, base_filter, 1, per_page)
        if names:
            notes.append("no phrase query matched enough works; fell back to the AND relaxation of single terms")
        kept.append({"facet": "all", "phrases": [], "search": search, "filter": base_filter,
                     "per_page": per_page, "data": data, "matched": (data.get("meta") or {}).get("count")})
    mode = "phrases-or" if names and kept[0]["facet"] != "all" else "terms-and-relaxation"
    budget = max(1, max_works // len(kept))
    sources: dict[str, dict] = {}
    topics_by_facet: dict[str, dict[str, float]] = {}
    topic_names: dict[str, str] = {}
    queries: list[dict] = []
    scanned = 0
    for query in kept:
        topics = topics_by_facet.setdefault(query["facet"], {})
        read = 0
        page = 1
        data = query["data"]
        while True:
            results = data.get("results") or []
            for work in results:
                scanned += 1
                read += 1
                for tid, name, score in _top_topics(work):
                    topics[tid] = topics.get(tid, 0.0) + score
                    topic_names.setdefault(tid, name)
                source = ((work.get("primary_location") or {}).get("source")) or {}
                if source.get("type") != "journal" or not source.get("id"):
                    continue
                entry = sources.setdefault(source["id"], {
                    "id": source["id"], "name": source.get("display_name") or "", "count": 0, "works": [],
                    "first": len(sources), "ids": set(), "facet_ids": {}})
                key = work.get("id") or f"{source['id']}#{scanned}"
                entry["facet_ids"].setdefault(query["facet"], set()).add(key)
                if key in entry["ids"]:
                    continue
                entry["ids"].add(key)
                entry["count"] += 1
                if len(entry["works"]) < 3:
                    doi = work.get("doi")
                    entry["works"].append({
                        "title": work.get("title") or "", "year": work.get("publication_year"),
                        "doi": re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi) if doi else None})
            if len(results) < query["per_page"] or read >= budget:
                break
            page += 1
            data = request(query["search"], query["filter"], page, query["per_page"])
        queries.append({"facet": query["facet"], "phrases": query["phrases"], "matched": query["matched"],
                        "works_read": read})
    return {"sources": list(sources.values()), "scanned": scanned,
            "terms": used if mode != "phrases-or" else terms,
            "phrases": [p for q in queries for p in q["phrases"]], "mode": mode, "notes": notes,
            "queries": [q for q in queries if q["facet"] != "all"],
            "topics_by_facet": topics_by_facet, "topic_names": topic_names,
            "tail": application_tail(title)}


def _issn_list(source: dict) -> list[str]:
    seen, out = set(), []
    for issn in [source.get("issn_l"), *(source.get("issn") or [])]:
        key = normalize_issn(issn)
        if key and key not in seen:
            seen.add(key)
            out.append(issn)
    return out


def fetch_source(services: Services, entry: dict) -> tuple[dict | None, str | None]:
    sid = _short_id(entry["id"])
    try:
        data = services.openalex_get(f"/sources/{sid}", {"select": SOURCE_SELECT})
    except HttpFailure as exc:
        return None, f"source {sid} ({entry['name']}) could not be fetched: {exc}; skipped"
    stats = data.get("summary_stats") or {}
    topics = data.get("topics") or []
    shares = _source_shares(data)
    field = (topics[0].get("field") or {}) if topics else {}
    return {
        "openalex_id": data.get("id") or entry["id"],
        "display_name": data.get("display_name") or entry["name"],
        "issn_l": data.get("issn_l"),
        "issn": data.get("issn") or [],
        "publisher": data.get("host_organization_name"),
        "is_oa": bool(data.get("is_oa")),
        "is_in_doaj": bool(data.get("is_in_doaj")),
        "apc_usd": data.get("apc_usd"),
        "homepage_url": data.get("homepage_url"),
        "h_index": stats.get("h_index"),
        "mean_citedness_2yr": stats.get("2yr_mean_citedness"),
        "field": field.get("display_name"),
        "field_id": _short_id(field["id"]) if field.get("id") else None,
        "similar_works_count": entry["count"],
        "similar_works": entry["works"],
        "cited_count": entry.get("cited", 0),
        "facet_hits": {name: len(entry.get("facet_ids", {}).get(name, ())) for name in ("method", "application")},
        "topics": [{"id": _short_id(t["id"]), "name": t.get("display_name") or "",
                    "share": round(shares[_short_id(t["id"])], 4)}
                   for t in sorted(topics, key=lambda t: -(t.get("count") or 0))[:SOURCE_TOPICS_SHOWN]
                   if t.get("id") and _short_id(t["id"]) in shares],
        "topic_shares": shares,
    }, None


def proxy_for(services: Services, candidate: dict) -> tuple[dict | None, str | None]:
    citedness, field_id = candidate.get("mean_citedness_2yr"), candidate.get("field_id")
    name = candidate["display_name"]
    if citedness is None or not field_id:
        return None, f"{name}: no 2-year citedness or field in OpenAlex, no quartile derivable"
    base = f"type:journal,is_core:true,topics.field.id:{field_id}"
    try:
        total = services.openalex_get("/sources", {
            "filter": f"{base},summary_stats.2yr_mean_citedness:>0", "per-page": 1, "select": "id"})
        above = services.openalex_get("/sources", {
            "filter": f"{base},summary_stats.2yr_mean_citedness:>{citedness!r}", "per-page": 1, "select": "id"})
    except HttpFailure as exc:
        return None, f"{name}: proxy quartile could not be computed ({exc})"
    population = int((total.get("meta") or {}).get("count") or 0)
    greater = int((above.get("meta") or {}).get("count") or 0)
    if population <= 0:
        return None, f"{name}: no comparison journals in field {candidate['field']}"
    share = greater / population
    return {"field": candidate["field"], "field_id": field_id, "journals_in_field": population,
            "share_of_field_above": round(share, 4), "percentile": round(100 * (1 - share), 1),
            "quartile": proxy_quartile(share),
            "basis": "2yr_mean_citedness against OpenAlex core journals of the same field"}, None


# --------------------------------------------------------------------------- references the paper cites

_BIB_START = re.compile(r"@([A-Za-z]+)\s*[{(]")
_BIB_SKIPPED = ("comment", "string", "preamble")
_DOI_PATTERN = re.compile(r"10\.\d+/\S+")
_ARXIV_NEW = re.compile(r"(?<![\d.])(\d{4}\.\d{4,5})(?:v\d+)?(?![\d])")
_ARXIV_OLD = re.compile(r"(?<![\w/-])([a-z-]+(?:\.[A-Za-z]{2})?/\d{7})(?:v\d+)?(?!\d)")
_REPOSITORY_NAME = re.compile(r"\b(?:arxiv|biorxiv|medrxiv|chemrxiv|techrxiv|preprint|preprints|dataport|ssrn|"
                              r"zenodo|figshare|osf|thesis|dissertation)\b", re.IGNORECASE)


def normalize_doi(value) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text, flags=re.IGNORECASE)
    text = text.strip().rstrip(".,;").lower()
    return text if _DOI_PATTERN.fullmatch(text) else None


def is_repository_name(name: str) -> bool:
    return bool(_REPOSITORY_NAME.search(name or ""))


def _arxiv_doi(*texts) -> str | None:
    for text in texts:
        if not text:
            continue
        match = _ARXIV_NEW.search(str(text)) or _ARXIV_OLD.search(str(text))
        if match:
            return f"10.48550/arxiv.{match.group(1).lower()}"
    return None


def _balanced(text: str, open_index: int) -> tuple[str, int]:
    """Inner text of the {...} or (...) group opening at `open_index`, and the index after its close."""
    opener = text[open_index]
    closer = "}" if opener == "{" else ")"
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if text[index - 1:index] == "\\":
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[open_index + 1:index], index + 1
    return text[open_index + 1:], len(text)


def _bib_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    pos = 0
    pattern = re.compile(r"\s*,?\s*([A-Za-z][\w:-]*)\s*=\s*")
    while True:
        match = pattern.match(body, pos)
        if not match:
            break
        name, pos = match.group(1).lower(), match.end()
        if pos >= len(body):
            break
        if body[pos] == "{":
            value, pos = _balanced(body, pos)
        elif body[pos] == '"':
            end, depth = pos + 1, 0
            while end < len(body) and not (body[end] == '"' and depth == 0 and body[end - 1] != "\\"):
                depth += {"{": 1, "}": -1}.get(body[end], 0)
                end += 1
            value, pos = body[pos + 1:end], end + 1
        else:
            end = body.find(",", pos)
            end = len(body) if end < 0 else end
            value, pos = body[pos:end].strip(), end
        fields.setdefault(name, re.sub(r"\s+", " ", value).strip())
    return fields


def _plain(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\\([&%$#_])", r"\1", value).replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip() or None


def parse_bib(text: str) -> list[dict]:
    """Entries of a BibTeX file as {key, title, journal, doi}; `doi` falls back to the arXiv DOI."""
    entries: list[dict] = []
    pos = 0
    while True:
        start = _BIB_START.search(text, pos)
        if not start:
            return entries
        body, pos = _balanced(text, start.end() - 1)
        if start.group(1).lower() in _BIB_SKIPPED:
            continue
        key, _, rest = body.partition(",")
        fields = _bib_fields(rest)
        journal = _plain(fields.get("journal") or fields.get("journaltitle"))
        url = fields.get("url") or ""
        doi = normalize_doi(fields.get("doi")) or normalize_doi(url if "doi.org/" in url else None)
        if doi is None:
            eprint = fields.get("eprint")
            arxiv_flag = "arxiv" in (fields.get("archiveprefix", "") + fields.get("eprinttype", "")).lower()
            doi = _arxiv_doi(eprint if eprint and (arxiv_flag or _ARXIV_NEW.fullmatch(eprint)
                                                   or _ARXIV_OLD.fullmatch(eprint)) else None,
                             url if "arxiv.org/" in url else None,
                             journal if journal and re.search(r"arxiv", journal, re.IGNORECASE) else None)
        entries.append({"key": key.strip(), "title": fields.get("title") or "", "journal": journal, "doi": doi})


def load_bibliography(workspace: Path) -> tuple[str | None, list[dict]]:
    folder = workspace / "paper"
    preferred = folder / "refs.bib"
    candidates = [preferred] if preferred.is_file() else sorted(folder.glob("*.bib"))
    if not candidates:
        return None, []
    return f"paper/{candidates[0].name}", parse_bib(_read_text(candidates[0]))


def _name_key(name: str) -> str:
    text = re.sub(r"^the\s+", "", (name or "").lower().replace("&", " and "))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _top_topics(work: dict) -> list[tuple[str, str, float]]:
    ranked = sorted((t for t in work.get("topics") or [] if t.get("id")),
                    key=lambda t: -(t.get("score") or 0))[:WORK_TOPICS_PER_WORK]
    return [(_short_id(t["id"]), t.get("display_name") or "", float(t.get("score") or 0)) for t in ranked]


def _source_shares(source: dict) -> dict[str, float]:
    counts = {_short_id(t["id"]): float(t.get("count") or 0) for t in source.get("topics") or [] if t.get("id")}
    total = sum(counts.values())
    return {tid: c / total for tid, c in counts.items() if c > 0} if total > 0 else {}


def resolve_cited(services: "Services", entries: list[dict], notes: list[str]) -> dict:
    """Journals the paper's references were published in, with the topics of the cited works.

    DOIs (and arXiv ids as 10.48550/arxiv.<id>) are resolved in OpenAlex batches of DOI_BATCH; a reference
    that stays unresolved but names a journal is looked up by exact name. Failures degrade into notes.
    """
    journals: dict[str, dict] = {}
    topics: dict[str, float] = {}
    names: dict[str, str] = {}
    stats = {"entries": len(entries), "resolved_by_doi": 0, "resolved_by_journal_name": 0}
    resolved: set[int] = set()

    def count(source: dict, index: int) -> None:
        sid = source["id"]
        slot = journals.setdefault(sid, {"openalex_id": sid, "display_name": source.get("display_name") or "",
                                         "count": 0})
        slot["count"] += 1
        resolved.add(index)

    dois = list(dict.fromkeys(e["doi"] for e in entries if e["doi"]))
    if len(dois) > DOI_BATCH * MAX_DOI_BATCHES:
        notes.append(f"cited venues: only the first {DOI_BATCH * MAX_DOI_BATCHES} of {len(dois)} DOIs were resolved")
        dois = dois[:DOI_BATCH * MAX_DOI_BATCHES]
    works: dict[str, dict] = {}
    for start in range(0, len(dois), DOI_BATCH):
        batch = dois[start:start + DOI_BATCH]
        try:
            data = services.openalex_get("/works", {"filter": "doi:" + "|".join(batch), "per-page": len(batch),
                                                   "select": "id,doi,primary_location,topics"})
        except HttpFailure as exc:
            notes.append(f"cited venues: the DOI lookup failed ({exc}); the references were not resolved by DOI")
            break
        for work in data.get("results") or []:
            key = normalize_doi(work.get("doi"))
            if key:
                works[key] = work
    for index, entry in enumerate(entries):
        work = works.get(entry["doi"] or "")
        source = ((work or {}).get("primary_location") or {}).get("source") or {}
        if work and source.get("type") == "journal" and source.get("id"):
            count(source, index)
            stats["resolved_by_doi"] += 1
            for tid, name, score in _top_topics(work):
                topics[tid] = topics.get(tid, 0.0) + score
                names.setdefault(tid, name)

    pending = [(i, e) for i, e in enumerate(entries)
               if i not in resolved and e["journal"] and not is_repository_name(e["journal"])]
    lookups: dict[str, dict | None] = {}
    for _, entry in pending:
        key = _name_key(entry["journal"])
        if key in lookups or len(lookups) >= MAX_NAME_LOOKUPS:
            continue
        try:
            data = services.openalex_get("/sources", {
                "search": entry["journal"], "filter": "type:journal", "per-page": NAME_LOOKUP_RESULTS,
                "select": "id,display_name,type,topics"})
        except HttpFailure as exc:
            notes.append(f"cited venues: the journal-name lookup failed ({exc}); stopped looking names up")
            break
        lookups[key] = next((r for r in data.get("results") or []
                             if r.get("type") == "journal" and r.get("id")
                             and _name_key(r.get("display_name")) == key), None)
    for index, entry in pending:
        source = lookups.get(_name_key(entry["journal"]))
        if source:
            count(source, index)
            stats["resolved_by_journal_name"] += 1
            for tid, share in _source_shares(source).items():
                topics[tid] = topics.get(tid, 0.0) + share
            for topic in source.get("topics") or []:
                if topic.get("id"):
                    names.setdefault(_short_id(topic["id"]), topic.get("display_name") or "")
    if len(pending) > 0 and len({_name_key(e["journal"]) for _, e in pending}) > MAX_NAME_LOOKUPS:
        notes.append(f"cited venues: only {MAX_NAME_LOOKUPS} distinct journal names were looked up")
    stats["unresolved"] = len(entries) - len(resolved)
    ranked = sorted(journals.values(), key=lambda j: (-j["count"], j["display_name"].lower()))
    return {"journals": journals, "topics": topics, "topic_names": names, "summary": {
        **stats, "journals": ranked[:10]}}


# --------------------------------------------------------------------------- the combined fit score


def blend_topics(*weighted: dict[str, float]) -> dict[str, float]:
    """The paper's topic distribution: each non-empty part (facet, cited works) weighs the same."""
    parts = []
    for weights in weighted:
        total = sum(weights.values())
        if total > 0:
            parts.append({tid: w / total for tid, w in weights.items() if w > 0})
    if not parts:
        return {}
    blended: dict[str, float] = {}
    for part in parts:
        for tid, share in part.items():
            blended[tid] = blended.get(tid, 0.0) + share / len(parts)
    return blended


def topic_overlap(paper: dict[str, float], journal: dict[str, float]) -> float:
    """Histogram intersection of two topic distributions: 0 (disjoint) .. 1 (identical)."""
    return sum(min(share, journal[tid]) for tid, share in paper.items() if tid in journal)


def facet_gate(application_hits: int, application_topic_overlap: float) -> float:
    """1.0 when the journal shows application evidence, else FACET_GATE: no work found by the application
    phrases and topics that barely overlap those of the works those phrases found."""
    if application_hits > 0 or application_topic_overlap >= APP_TOPIC_MIN:
        return 1.0
    return FACET_GATE


def apply_fit(details: list[dict]) -> dict:
    """Set `fit` (three components in 0..1) and `fit_score` on each detail; return the scoring description.

    Each component is divided by its maximum over the evaluated journals. A component that is zero for every
    journal (no references file, no OpenAlex topics) drops out and the remaining weights are rescaled to 1.
    """
    raw = {"similar_works": [d["similar_works_count"] for d in details],
           "cited_in_paper": [d["cited_count"] for d in details],
           "topic_overlap": [d["topic_raw"] for d in details]}
    peak = {name: max(values, default=0) for name, values in raw.items()}
    active = [name for name in FIT_WEIGHTS if peak[name] > 0]
    total = sum(FIT_WEIGHTS[name] for name in active)
    weights = {name: round(FIT_WEIGHTS[name] / total, 6) if name in active else 0.0 for name in FIT_WEIGHTS}
    for position, detail in enumerate(details):
        detail["fit"] = {name: round(raw[name][position] / peak[name], 4) if peak[name] > 0 else 0.0
                         for name in FIT_WEIGHTS}
        detail["fit_score"] = round(sum(weights[name] * detail["fit"][name] for name in FIT_WEIGHTS), 4)
    formula = "fit_score = " + " + ".join(f"{w:g} * {name}" for name, w in FIT_WEIGHTS.items())
    return {"formula": formula, "weights": weights, "active": active,
            "normalization": "each component is divided by its maximum over the evaluated journals; a "
                             "component that is zero for every journal drops out and the remaining weights "
                             "are rescaled to sum to 1",
            "facet_gate": {"applies": False, "factor": FACET_GATE, "rule": (
                "when the paper has a method and an application facet and both were searched, a journal none "
                "of whose similar works matched an application phrase, and whose topics overlap the "
                f"application works' topics by less than {APP_TOPIC_MIN:g}, has fit_score multiplied by "
                f"{FACET_GATE:g} and is flagged no-application-evidence")}}


# --------------------------------------------------------------------------- review time


def _empty_review(n: int, window: dict) -> dict:
    return {"median_days": None, "p25_days": None, "p75_days": None, "n": n,
            "accept_to_online_median_days": None, "accept_to_online_n": 0, "source": "none",
            "kind": "submission-to-acceptance-estimate", "window": window}


def _review_result(source: str, review: list[int], online: list[int], window: dict) -> dict:
    median, p25, p75 = summarize_days(review)
    return {"median_days": median, "p25_days": p25, "p75_days": p75, "n": len(review),
            "accept_to_online_median_days": summarize_days(online)[0] if online else None,
            "accept_to_online_n": len(online), "source": source,
            "kind": "submission-to-acceptance-estimate", "window": window}


def estimate_review_time(services: Services, candidate: dict, today: dt.date) -> tuple[dict, list[str]]:
    start = today - dt.timedelta(days=365 * REVIEW_YEARS)
    window = {"from": start.isoformat(), "to": today.isoformat()}
    issns = _issn_list(candidate)
    name = candidate["display_name"]
    notes: list[str] = []
    best_n = 0

    for issn in issns:
        try:
            data = services.crossref_get(f"/journals/{urllib.parse.quote(issn)}/works", {
                "rows": REVIEW_SAMPLE, "select": "DOI,assertion,issued", "sort": "issued", "order": "desc",
                "filter": f"from-pub-date:{start.isoformat()},until-pub-date:{today.isoformat()},"
                          "type:journal-article"})
        except HttpFailure as exc:
            if exc.status == 404:
                continue
            notes.append(f"review time: Crossref failed for {name} ({exc})")
            break
        items = ((data.get("message") or {}).get("items")) or []
        if not items:
            continue
        review, online = review_deltas(crossref_item_dates(i) for i in items)
        best_n = max(best_n, len(review))
        if len(review) >= REVIEW_MIN_N:
            return _review_result("crossref", review, online, window), notes
        break

    for issn in issns:
        try:
            found = services.pubmed_get("/esearch.fcgi", {
                "db": "pubmed", "term": f'"{issn}"[is]', "datetype": "pdat",
                "mindate": start.strftime("%Y/%m/%d"), "maxdate": today.strftime("%Y/%m/%d"),
                "retmax": REVIEW_SAMPLE, "retmode": "json", "sort": "pub date"})
            ids = ((found.get("esearchresult") or {}).get("idlist")) or []
            if not ids:
                continue
            summary = services.pubmed_get("/esummary.fcgi", {
                "db": "pubmed", "id": ",".join(ids), "retmode": "json"})
        except HttpFailure as exc:
            notes.append(f"review time: PubMed failed for {name} ({exc})")
            break
        result = summary.get("result") or {}
        review, online = review_deltas(
            pubmed_history_dates((result.get(uid) or {}).get("history")) for uid in result.get("uids") or [])
        best_n = max(best_n, len(review))
        if len(review) >= REVIEW_MIN_N:
            return _review_result("pubmed", review, online, window), notes
        break
    return _empty_review(best_n, window), notes


# --------------------------------------------------------------------------- search


def _number(text, name: str, integer: bool = False):
    if text is None:
        return None
    try:
        value = float(text)
    except (TypeError, ValueError):
        raise Refusal("FILTER_INVALID", f"{name} must be a number, got {text!r}") from None
    if not math.isfinite(value):
        raise Refusal("FILTER_INVALID", f"{name} must be finite")
    if integer:
        if value != int(value):
            raise Refusal("FILTER_INVALID", f"{name} must be a whole number")
        return int(value)
    return int(value) if value == int(value) else value


def _validated_filters(args: argparse.Namespace) -> tuple[dict, list[str]]:
    notes: list[str] = []
    limit = DEFAULT_LIMIT if args.limit is None else _number(args.limit, "--limit", integer=True)
    if limit < 1:
        raise Refusal("FILTER_INVALID", "--limit must be at least 1")
    if limit > MAX_LIMIT:
        notes.append(f"--limit {limit} exceeds the maximum; capped at {MAX_LIMIT}")
        limit = MAX_LIMIT
    max_apc = _number(args.max_apc, "--max-apc")
    if max_apc is not None and max_apc < 0:
        raise Refusal("FILTER_INVALID", "--max-apc must not be negative")
    max_days = _number(args.max_review_days, "--max-review-days")
    if max_days is not None and max_days <= 0:
        raise Refusal("FILTER_INVALID", "--max-review-days must be positive")
    return {"oa_only": bool(args.oa_only), "max_apc": max_apc, "max_review_days": max_days,
            "limit": limit}, notes


def _load_sjr(args: argparse.Namespace, notes: list[str]) -> tuple[SjrTable | None, dict | None]:
    if args.sjr:
        path = Path(args.sjr).expanduser()
        return read_sjr(path), {"file": str(path), "year": year_from_name(path.name)}
    cached = latest_cached_sjr()
    if cached is None:
        notes.append(f"No SJR file imported: quartiles are the openalex-proxy approximation. Download the CSV "
                     f"from {SJR_DOWNLOAD_URL} ('Download data') and run `journal_cli.py sjr-import`.")
        return None, None
    path, year = cached
    try:
        return read_sjr(path), {"file": str(path), "year": year}
    except Refusal as exc:
        notes.append(f"cached SJR file ignored: {exc.message}")
        return None, None


def _write_json(path: Path, document: dict) -> None:
    _atomic_write(path, (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def cmd_search(args: argparse.Namespace) -> dict:
    low, high = parse_quartile_range(args.quartiles)
    filters, notes = _validated_filters(args)
    workspace = Path(args.workspace).expanduser()
    if not workspace.is_dir():
        raise Refusal("WORKSPACE_ABSENT", f"{workspace} is not a directory")
    table, sjr_info = _load_sjr(args, notes)
    profile = extract_profile(workspace)
    terms = build_terms(profile)
    facets = build_phrase_facets(profile)
    out = Path(args.out).expanduser() if args.out else workspace / "paper" / "journal-candidates.json"

    max_works = max(1, _env_int("PAPERSMITH_JOURNAL_MAX_WORKS", DEFAULT_MAX_WORKS))
    services = Services(Deadline(_env_float("PAPERSMITH_JOURNAL_DEADLINE", 300.0)),
                        ResponseCache(cache_dir(), enabled=not args.no_cache))
    try:
        found = fetch_similar_sources(services, facets, terms, max_works, dt.date.today(),
                                      profile["title"])
    except HttpFailure as exc:
        raise Refusal("NETWORK_UNAVAILABLE", f"OpenAlex could not be reached: {exc}") from exc
    sources, scanned, terms = found["sources"], found["scanned"], found["terms"]
    notes.extend(found["notes"])

    references_file, entries = load_bibliography(workspace)
    if references_file is None:
        notes.append("no references file (paper/refs.bib) was found: the cited-venues signal is inactive")
    elif not entries:
        notes.append(f"{references_file} holds no entries: the cited-venues signal is inactive")
    cited = resolve_cited(services, entries, notes) if entries else {
        "journals": {}, "topics": {}, "topic_names": {}, "summary": {
            "entries": 0, "resolved_by_doi": 0, "resolved_by_journal_name": 0, "unresolved": 0, "journals": []}}
    matched_topics = blend_topics(*found["topics_by_facet"].values())
    topic_profile = blend_topics(matched_topics, cited["topics"])
    queried = {q["facet"] for q in found["queries"]}
    gate_applies = {"method", "application"} <= queried
    application_profile = blend_topics(found["topics_by_facet"].get("application", {}))
    topic_names = {**cited["topic_names"], **found["topic_names"]}

    excluded = 0
    candidates: list[dict] = []
    scoring = apply_fit([])
    if not sources:
        notes.append("no journal-hosted works matched the paper's terms in OpenAlex")
    by_id = {s["id"]: s for s in sources}
    ranked_sources = sorted(sources, key=lambda s: (-s["count"], s["first"]))
    pool_size = min(MAX_SOURCES, max(MIN_SOURCES, filters["limit"] * 3))
    pool = ranked_sources[:pool_size]
    in_pool = {s["id"] for s in pool}
    cited_ranked = sorted(cited["journals"].values(), key=lambda j: (-j["count"], j["display_name"].lower()))
    for journal in cited_ranked[:MAX_CITED_ONLY]:
        entry = by_id.get(journal["openalex_id"]) or {
            "id": journal["openalex_id"], "name": journal["display_name"], "count": 0, "works": [],
            "first": len(sources) + len(in_pool)}
        entry["cited"] = journal["count"]
        if entry["id"] not in in_pool:
            pool.append(entry)
            in_pool.add(entry["id"])
    left_out = len(sources) - sum(1 for s in sources if s["id"] in in_pool)
    if left_out > 0:
        notes.append(f"{left_out} journals with fewer similar works were not evaluated "
                     f"(the top {pool_size} by similar-works count, plus the cited journals, were)")
    if pool:
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            fetched = list(executor.map(lambda e: fetch_source(services, e), pool))
        details = [d for d, _ in fetched if d is not None]
        for _, note in fetched:
            if note:
                notes.append(note)
        excluded += len(fetched) - len(details)
        if not details:
            raise Refusal("NETWORK_UNAVAILABLE", "OpenAlex answered no journal record; see the search notes: "
                          + "; ".join(n for _, n in fetched if n)[:300])
        for detail in details:
            shares = detail.pop("topic_shares")
            detail["topic_raw"] = topic_overlap(topic_profile, shares)
            detail["application_overlap"] = topic_overlap(application_profile, shares)
        scoring = apply_fit(details)
        scoring["facet_gate"]["applies"] = gate_applies
        for detail in details:
            detail["cited_in_paper_count"] = detail.pop("cited_count")
            detail.pop("topic_raw")
            hits = detail.pop("facet_hits")
            overlap = detail.pop("application_overlap")
            gate = facet_gate(hits["application"], overlap) if gate_applies else 1.0
            detail["facets"] = {"method": hits["method"], "application": hits["application"],
                                "application_topic_overlap": round(overlap, 4), "gate": gate}
            detail["fit_score"] = round(detail["fit_score"] * gate, 4)

        def resolve_quartile(detail: dict) -> tuple[dict, str | None]:
            hit = table.lookup(_issn_list(detail)) if table else None
            if hit and hit["quartile"]:
                detail.update(quartile=hit["quartile"], quartile_source="sjr", proxy=None, sjr={
                    "value": hit["value"], "year": sjr_info["year"], "best_quartile": hit["quartile"],
                    "categories": hit["categories"]})
                return detail, None
            proxy, note = proxy_for(services, detail)
            detail["sjr"] = None
            if proxy is None:
                detail.update(quartile=None, quartile_source="none", proxy=None)
                return detail, note
            detail.update(quartile=proxy["quartile"], quartile_source="openalex-proxy", proxy=proxy)
            return detail, None

        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            resolved = list(executor.map(resolve_quartile, details))
        eligible: list[dict] = []
        for detail, note in resolved:
            if note:
                notes.append(note)
            number = int(detail["quartile"][1]) if detail["quartile"] else None
            if number is None or not low <= number <= high:
                excluded += 1
            elif filters["oa_only"] and not detail["is_oa"]:
                excluded += 1
            elif filters["max_apc"] is not None and detail["apc_usd"] is not None \
                    and detail["apc_usd"] > filters["max_apc"]:
                excluded += 1
            else:
                detail["flags"] = ["no-application-evidence"] if detail["facets"]["gate"] < 1.0 else []
                if filters["max_apc"] is not None and detail["apc_usd"] is None:
                    detail["flags"].append("apc-unknown")
                eligible.append(detail)
        eligible.sort(key=lambda d: (-d["fit_score"], -d["cited_in_paper_count"], -d["similar_works_count"],
                                     d["display_name"].lower()))

        today = dt.date.today()
        index = 0
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            while index < len(eligible) and len(candidates) < filters["limit"]:
                batch = eligible[index:index + (filters["limit"] - len(candidates))]
                index += len(batch)
                estimates = list(executor.map(lambda c: estimate_review_time(services, c, today), batch))
                for candidate, (review, review_notes) in zip(batch, estimates):
                    notes.extend(review_notes)
                    candidate["review_time"] = review
                    limit_days = filters["max_review_days"]
                    if limit_days is not None:
                        if review["source"] == "none":
                            candidate["flags"].append("review-time-unknown")
                        elif review["median_days"] > limit_days:
                            excluded += 1
                            continue
                    candidates.append(candidate)
        if index < len(eligible):
            notes.append(f"{len(eligible) - index} further matching journals ranked below the limit were not "
                         "evaluated for review time")

    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank
        candidate.pop("field_id", None)
    summary = {"sjr": 0, "openalex-proxy": 0}
    for candidate in candidates:
        summary[candidate["quartile_source"]] = summary.get(candidate["quartile_source"], 0) + 1
    if summary["openalex-proxy"]:
        notes.append("Candidates labelled openalex-proxy carry an approximate quartile from OpenAlex citedness "
                     "percentiles within the field; it is not an SJR quartile.")
    if sjr_info and sjr_info["year"] and dt.date.today().year - sjr_info["year"] > 2:
        notes.append(f"The SJR file in use is from {sjr_info['year']}, older than two years; import a fresher "
                     f"download from {SJR_DOWNLOAD_URL}.")
    if any(c["review_time"]["source"] != "none" for c in candidates):
        notes.append("review_time estimates submission-to-acceptance from public article histories, "
                     "including revision rounds; it is not the time to first decision.")
    notes = list(dict.fromkeys(notes))
    document = {
        "schema": SCHEMA,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "query": {
            "title": profile["title"], "keywords": profile["keywords"], "terms": terms,
            "phrases": found["phrases"], "search_mode": found["mode"],
            "facets": {"tail": found["tail"], "queries": found["queries"]},
            "topics": [{"id": tid, "name": topic_names.get(tid, ""), "weight": round(weight, 4)}
                       for tid, weight in sorted(topic_profile.items(), key=lambda kv: -kv[1])[:5]],
            "cited": {"references_file": references_file, **cited["summary"]},
            "scoring": scoring},
        "quartiles": [f"Q{n}" for n in range(low, high + 1)],
        "filters": filters,
        "quartile_source_summary": summary,
        "sjr": sjr_info,
        "candidates": candidates,
        "excluded_count": excluded,
        "notes": notes,
        "api_calls": services.stats.summary(services.cache),
    }
    _write_json(out, document)
    return {"ok": True, "out": str(out), "works_scanned": scanned, **document}


# --------------------------------------------------------------------------- status


def cmd_status(args: argparse.Namespace) -> dict:
    workspace = Path(args.workspace).expanduser()
    if not workspace.is_dir():
        raise Refusal("WORKSPACE_ABSENT", f"{workspace} is not a directory")
    path = workspace / "paper" / "journal-candidates.json"
    summary = None
    if path.is_file():
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            summary = {"path": str(path), "generated_at": document["generated_at"],
                       "count": len(document["candidates"]), "quartiles": document["quartiles"],
                       "filters": document["filters"],
                       "quartile_source_summary": document["quartile_source_summary"],
                       "excluded_count": document.get("excluded_count"),
                       "title": (document.get("query") or {}).get("title"), "sjr": document.get("sjr")}
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise Refusal("CANDIDATES_UNREADABLE", f"{path} cannot be read as journal candidates ({exc})") from exc
    cached = latest_cached_sjr()
    sjr = {"file": str(cached[0]), "year": cached[1]} if cached else None
    return {"ok": True, "candidates": summary, "sjr": sjr}


# --------------------------------------------------------------------------- entry point


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # type: ignore[override]
        raise Refusal("USAGE", message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description="Rank journals that publish work like this paper (never submits anything).")
    sub = parser.add_subparsers(dest="verb", required=True, parser_class=_Parser)

    search = sub.add_parser("search", help="rank journals for the paper in a workspace")
    search.add_argument("--workspace", required=True)
    search.add_argument("--quartiles", required=True, help="Q1, Q2-Q3, Q1-Q4 ...")
    search.add_argument("--oa-only", action="store_true", help="fully open-access journals only")
    search.add_argument("--max-apc", default=None, help="maximum APC in USD (unknown APC is kept, flagged)")
    search.add_argument("--max-review-days", default=None,
                        help="drop journals whose median submission-to-acceptance exceeds N days")
    search.add_argument("--limit", default=None, help=f"default {DEFAULT_LIMIT}, max {MAX_LIMIT}")
    search.add_argument("--sjr", default=None, help="a SCImago CSV to use instead of the cache")
    search.add_argument("--out", default=None, help="default <workspace>/paper/journal-candidates.json")
    search.add_argument("--no-cache", action="store_true",
                        help="neither read nor write the on-disk response cache")
    search.set_defaults(func=cmd_search)

    imp = sub.add_parser("sjr-import", help="validate and cache a SCImago 'Download data' CSV")
    imp.add_argument("--file", required=True)
    imp.add_argument("--year", type=int, default=None)
    imp.set_defaults(func=cmd_sjr_import)

    status = sub.add_parser("status", help="summarise the candidates file and the SJR file in use")
    status.add_argument("--workspace", required=True)
    status.set_defaults(func=cmd_status)
    return parser


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        _emit(args.func(args))
        return 0
    except Refusal as refusal:
        _emit({"ok": False, "error": refusal.code, "message": refusal.message})
        return 2
    except Exception as exc:  # a bug, reported typed so a caller can quote it
        _emit({"ok": False, "error": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    sys.exit(main())
