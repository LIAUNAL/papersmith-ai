#!/usr/bin/env python3
"""journal-finder: rank journals that publish work like this paper.

Stdlib only. One JSON object on stdout per call; a refusal is
`{"ok": false, "error": CODE, "message": ...}` with exit 2 and nothing written.

    journal_cli.py search --workspace <dir> --quartiles <range> [--oa-only]
                          [--max-apc N] [--max-review-days N] [--limit N]
                          [--sjr <csv>] [--out <path>]
    journal_cli.py sjr-import --file <path> [--year YYYY]
    journal_cli.py status --workspace <dir>

`search` reads the paper's title, abstract and keywords, asks OpenAlex for
works like it, keeps the journals those works appeared in, scores each by how
many similar works it published, attaches a quartile (SCImago SJR when a CSV
was imported, an OpenAlex citedness proxy otherwise, always labelled), a
review-time estimate (Crossref, then PubMed) and writes
`paper/journal-candidates.json` (schema 1). Nothing is ever submitted.

Fit score
    similar-works count of the journal / the largest count among the journals
    the search found, so the best-represented journal scores 1.0.

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
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
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
DEFAULT_MAX_WORKS = 200
WORKS_PAGE_SIZE = 100
MAX_SOURCES = 60
MIN_SOURCES = 30
WORKERS = 4
REVIEW_SAMPLE = 40
REVIEW_YEARS = 3
REVIEW_MIN_N = 5
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
    def __init__(self, message: str, status: int | None = None, deadline: bool = False):
        super().__init__(message)
        self.status = status
        self.deadline = deadline


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


class Http:
    def __init__(self, deadline: Deadline):
        self.deadline = deadline
        self.timeout = _env_float("PAPERSMITH_HTTP_TIMEOUT", 15.0)
        self.retries = max(0, _env_int("PAPERSMITH_HTTP_RETRIES", 3))
        self.backoff = max(0.0, _env_float("PAPERSMITH_HTTP_BACKOFF", 0.5))
        contact = _contact()
        agent = "papersmith-journal-finder/1.0"
        self.user_agent = f"{agent} (mailto:{contact})" if contact else agent

    def get_json(self, url: str, params: dict, limiter: RateLimiter | None = None) -> dict:
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
            try:
                with urllib.request.urlopen(request, timeout=max(0.05, min(self.timeout, remaining))) as response:
                    raw = response.read()
                try:
                    return json.loads(raw.decode("utf-8"))
                except ValueError as exc:
                    raise HttpFailure(f"answer is not JSON ({exc})", status=200) from exc
            except urllib.error.HTTPError as exc:
                if exc.code != 429 and not 500 <= exc.code <= 599:
                    raise HttpFailure(f"HTTP {exc.code} from {urllib.parse.urlsplit(url).netloc}",
                                      status=exc.code) from exc
                last = f"HTTP {exc.code}"
                try:
                    retry_after = min(10.0, float(exc.headers.get("Retry-After", "0")))
                except (TypeError, ValueError):
                    retry_after = 0.0
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
    "therefore since then there here whose among across per".split())


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
    def __init__(self, deadline: Deadline):
        self.http = Http(deadline)
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
        return self.http.get_json(f"{self.openalex}{path}", params, self.openalex_limiter)

    def crossref_get(self, path: str, params: dict) -> dict:
        params = dict(params)
        if _contact():
            params["mailto"] = _contact()
        return self.http.get_json(f"{self.crossref}{path}", params, self.crossref_limiter)

    def pubmed_get(self, path: str, params: dict) -> dict:
        params = {**params, "tool": "papersmith"}
        if _contact():
            params["email"] = _contact()
        if os.environ.get("NCBI_API_KEY"):
            params["api_key"] = os.environ["NCBI_API_KEY"]
        return self.http.get_json(f"{self.pubmed}{path}", params, self.pubmed_limiter)


def _short_id(url: str) -> str:
    return str(url).rstrip("/").rsplit("/", 1)[-1]


def fetch_similar_sources(services: Services, terms: list[str], max_works: int) -> tuple[list[dict], int]:
    """Journals hosting works like the paper: [{id, name, count, works: [...]}], plus works scanned."""
    per_page = max(1, min(WORKS_PAGE_SIZE, max_works))
    sources: dict[str, dict] = {}
    scanned = 0
    page = 1
    while scanned < max_works:
        data = services.openalex_get("/works", {
            "search": " ".join(terms), "filter": "primary_location.source.type:journal,type:article",
            "per-page": per_page, "page": page,
            "select": "id,title,publication_year,doi,primary_location"})
        results = data.get("results") or []
        for work in results:
            scanned += 1
            source = ((work.get("primary_location") or {}).get("source")) or {}
            if source.get("type") != "journal" or not source.get("id"):
                continue
            entry = sources.setdefault(source["id"], {
                "id": source["id"], "name": source.get("display_name") or "", "count": 0, "works": [],
                "first": len(sources)})
            entry["count"] += 1
            if len(entry["works"]) < 3:
                doi = work.get("doi")
                entry["works"].append({
                    "title": work.get("title") or "", "year": work.get("publication_year"),
                    "doi": re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi) if doi else None})
        if len(results) < per_page:
            break
        page += 1
    return list(sources.values()), scanned


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
    out = Path(args.out).expanduser() if args.out else workspace / "paper" / "journal-candidates.json"

    max_works = max(1, _env_int("PAPERSMITH_JOURNAL_MAX_WORKS", DEFAULT_MAX_WORKS))
    services = Services(Deadline(_env_float("PAPERSMITH_JOURNAL_DEADLINE", 300.0)))
    try:
        sources, scanned = fetch_similar_sources(services, terms, max_works)
    except HttpFailure as exc:
        raise Refusal("NETWORK_UNAVAILABLE", f"OpenAlex could not be reached: {exc}") from exc

    excluded = 0
    candidates: list[dict] = []
    if not sources:
        notes.append("no journal-hosted works matched the paper's terms in OpenAlex")
    else:
        best = max(s["count"] for s in sources)
        sources.sort(key=lambda s: (-s["count"], s["first"]))
        pool_size = min(MAX_SOURCES, max(MIN_SOURCES, filters["limit"] * 3))
        if len(sources) > pool_size:
            notes.append(f"{len(sources) - pool_size} journals with fewer similar works were not evaluated "
                         f"(the top {pool_size} by similar-works count were)")
        pool = sources[:pool_size]
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
            detail["fit_score"] = round(detail["similar_works_count"] / best, 4)

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
                detail["flags"] = []
                if filters["max_apc"] is not None and detail["apc_usd"] is None:
                    detail["flags"].append("apc-unknown")
                eligible.append(detail)
        eligible.sort(key=lambda d: (-d["fit_score"], -d["similar_works_count"], d["display_name"].lower()))

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
        "query": {"title": profile["title"], "keywords": profile["keywords"], "terms": terms},
        "quartiles": [f"Q{n}" for n in range(low, high + 1)],
        "filters": filters,
        "quartile_source_summary": summary,
        "sjr": sjr_info,
        "candidates": candidates,
        "excluded_count": excluded,
        "notes": notes,
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
