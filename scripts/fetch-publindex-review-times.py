#!/usr/bin/env python3
"""Estimate submission-to-publication times for the journals of the Publindex list.

For each journal of skills/journal-finder/data/publindex-ibn.json this script visits the journal's own
website and stores, under `review_time`:

* **measured**: the median, p25 and p75 days from submission to publication over up to
  `--articles` recent articles. Most Colombian journals run Open Journal Systems (OJS), whose article
  pages carry `DC.Date.dateSubmitted` and `DC.Date.issued` (or `citation_publication_date`) meta tags;
  when the page prints "Recibido/Received" and "Aceptado/Accepted" dates those are kept too
  (`accept_median_days`). Articles come from the newest issues of `<base>/issue/archive`.
* **declared**: sentences the journal itself publishes about its review or publication times, quoted
  from its "about", policies or submissions pages, with their URL. Never paraphrased.

A site that cannot be reached is recorded as such (`status`), never guessed. Only public pages are
read, at most one request per `--interval` seconds per host.

    python scripts/fetch-publindex-review-times.py [--file PATH] [--articles 12] [--workers 12]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import html
import json
import re
import ssl
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_FILE = Path(__file__).resolve().parents[1] / "skills" / "journal-finder" / "data" / "publindex-ibn.json"
USER_AGENT = "Mozilla/5.0 (papersmith journal-finder; review-time survey)"
ABOUT_PAGES = ("about", "about/editorialPolicies", "about/submissions", "about/editorialTeam")
TIME_WORD = r"(?:d[ií]as?|days?|semanas?|weeks?|mes(?:es)?|months?)"
CONTEXT = (r"(?:evaluaci[oó]n|revisi[oó]n|review|arbitraje|pares|peer|dictamen|respuesta|decisi[oó]n|decision|"
           r"publicaci[oó]n|publication|aceptaci[oó]n|acceptance|proceso editorial|editorial process)")
DECLARED = re.compile(rf"(?:[^.!?\n]|\.(?=\d)){{0,220}}?(?<![\d.,])\d{{1,3}}(?:[.,]\d+)?"
                      rf"(?:\s*(?:a|-|–|y|to|and)\s*\d{{1,3}})?\s*{TIME_WORD}\b(?:[^.!?\n]|\.(?=\d)){{0,160}}",
                      re.IGNORECASE)
MONTHS = {m: i for i, names in enumerate((
    ("enero", "january", "jan", "ene"), ("febrero", "february", "feb"), ("marzo", "march", "mar"),
    ("abril", "april", "apr", "abr"), ("mayo", "may"), ("junio", "june", "jun"), ("julio", "july", "jul"),
    ("agosto", "august", "aug", "ago"), ("septiembre", "setiembre", "september", "sep", "sept"),
    ("octubre", "october", "oct"), ("noviembre", "november", "nov"), ("diciembre", "december", "dec", "dic")),
    start=1) for m in names}
DATE_TEXT = r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{1,2}\s+(?:de\s+)?[a-záéíóú]+\.?\s+(?:de\s+)?\d{4}|[a-z]+\.?\s+\d{1,2},?\s+\d{4})"
RECEIVED = re.compile(r"(?:recibido|received|fecha de recepci[oó]n|submitted)\s*(?:el|on|:)?\s*:?\s*" + DATE_TEXT, re.IGNORECASE)
ACCEPTED = re.compile(r"(?:aceptado|accepted|aprobado|fecha de aceptaci[oó]n)\s*(?:el|on|:)?\s*:?\s*" + DATE_TEXT, re.IGNORECASE)

_ssl = ssl.create_default_context()
_ssl_loose = ssl.create_default_context()
_ssl_loose.check_hostname = False
_ssl_loose.verify_mode = ssl.CERT_NONE  # many university sites ship broken chains; we only read public pages
_host_locks: dict[str, threading.Lock] = {}
_host_last: dict[str, float] = {}
_guard = threading.Lock()


def fetch(url: str, interval: float) -> tuple[str | None, str]:
    """(text, final url); text is None when the page cannot be read."""
    host = urllib.parse.urlsplit(url).netloc
    with _guard:
        lock = _host_locks.setdefault(host, threading.Lock())
    with lock:
        wait = _host_last.get(host, 0) + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            for context in (_ssl, _ssl_loose):
                try:
                    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "es,en"})
                    with urllib.request.urlopen(request, timeout=25, context=context) as response:
                        if "html" not in (response.headers.get("Content-Type") or "html"):
                            return None, response.geturl()
                        return response.read(2_000_000).decode("utf-8", "replace"), response.geturl()
                except urllib.error.URLError as exc:
                    if isinstance(getattr(exc, "reason", None), ssl.SSLError) and context is _ssl:
                        continue
                    raise
        except Exception:
            return None, url
        finally:
            _host_last[host] = time.monotonic()
    return None, url


def parse_date(text: str) -> dt.date | None:
    text = text.strip().lower().replace(",", " ")
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    words = re.findall(r"[a-záéíóú]+|\d+", text)
    numbers = [int(w) for w in words if w.isdigit()]
    month = next((MONTHS[w.rstrip(".")] for w in words if w.rstrip(".") in MONTHS), None)
    year = next((n for n in numbers if 1990 <= n <= 2100), None)
    day = next((n for n in numbers if 1 <= n <= 31), None)
    if month and year and day:
        try:
            return dt.date(year, month, day)
        except ValueError:
            return None
    return None


def meta(page: str, *names: str) -> str | None:
    for name in names:
        match = re.search(rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]*content=["\']([^"\']+)', page, re.IGNORECASE) \
            or re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*name=["\']{re.escape(name)}["\']', page, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def visible(page: str) -> str:
    page = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def ojs_base(url: str, page: str | None) -> str | None:
    links = re.findall(r'href=["\']([^"\']*index\.php/[^"\'/?#]+)', page or "")[:8]
    # relative links ("/index.php/raccefyn") resolve against the page that holds them
    for candidate in [url] + [urllib.parse.urljoin(url, href) for href in links]:
        match = re.match(r"(https?://[^?#]*?/index\.php/[^/?#]+)", candidate)
        if match and not match.group(1).rstrip("/").endswith(("index.php/index", "index.php/user")):
            return match.group(1)
    return None


def url_variants(url: str) -> list[str]:
    """The address as registered, then https, then with "www." toggled."""
    parts = urllib.parse.urlsplit(url)
    host = parts.netloc
    other = host[4:] if host.startswith("www.") else "www." + host
    out = []
    for scheme, netloc in ((parts.scheme, host), ("https", host), ("https", other), ("http", other)):
        candidate = urllib.parse.urlunsplit((scheme, netloc, parts.path, parts.query, ""))
        if candidate not in out:
            out.append(candidate)
    return out


def homepages(raw: str | None) -> list[str]:
    urls = []
    for part in re.split(r"[;\s,]+", raw or ""):
        part = part.strip()
        if not part or "." not in part:
            continue
        urls.append(part if part.startswith("http") else "http://" + part)
    return urls


def declared_times(base: str, home: str | None, interval: float) -> list[dict]:
    found, seen = [], set()
    pages = [f"{base}/{p}" for p in ABOUT_PAGES] if base else []
    if home:
        pages.append(home)
    for url in pages:
        page, final = fetch(url, interval)
        if not page:
            continue
        for match in DECLARED.finditer(visible(page)):
            sentence = match.group(0).strip(" ,;:-")
            if not re.search(CONTEXT, sentence, re.IGNORECASE) or sentence.lower() in seen:
                continue
            seen.add(sentence.lower())
            found.append({"quote": sentence[:400], "url": final})
            if len(found) >= 4:
                return found
    return found


def article_urls(base: str, limit: int, interval: float) -> list[str]:
    page, _ = fetch(f"{base}/issue/archive", interval)
    issues = list(dict.fromkeys(re.findall(r'href=["\']([^"\']*/issue/view/[^"\'#?]+)', page or "")))
    if not issues:
        current, _ = fetch(f"{base}/issue/current", interval)
        issues, page = [], current
        articles = list(dict.fromkeys(re.findall(r'href=["\']([^"\']*/article/view/\d+)["\']', current or "")))
        return articles[:limit]
    articles: list[str] = []
    for issue in issues[:4]:
        listing, _ = fetch(urllib.parse.urljoin(base + "/", issue), interval)
        for href in re.findall(r'href=["\']([^"\']*/article/view/\d+)["\']', listing or ""):
            url = urllib.parse.urljoin(base + "/", href)
            if url not in articles:
                articles.append(url)
        if len(articles) >= limit:
            break
    return articles[:limit]


def quantiles(values: list[int]) -> dict:
    values = sorted(values)
    if len(values) < 2:
        return {"median_days": values[0] if values else None, "p25_days": None, "p75_days": None}
    q = statistics.quantiles(values, n=4, method="inclusive")
    return {"median_days": int(statistics.median(values)), "p25_days": int(q[0]), "p75_days": int(q[2])}


def measure(articles: list[str], interval: float) -> dict:
    to_publication, to_acceptance, years = [], [], []
    for url in articles:
        page, _ = fetch(url, interval)
        if not page:
            continue
        submitted = parse_date(meta(page, "DC.Date.dateSubmitted") or "")
        published = parse_date(meta(page, "citation_publication_date", "DC.Date.issued", "citation_date") or "")
        text = visible(page)
        received_text, accepted_text = RECEIVED.search(text), ACCEPTED.search(text)
        received = parse_date(received_text.group(1)) if received_text else None
        accepted = parse_date(accepted_text.group(1)) if accepted_text else None
        start = received or submitted
        if start and published and 0 < (published - start).days < 3 * 365:
            to_publication.append((published - start).days)
            years.append(published.year)
        if start and accepted and 0 < (accepted - start).days < 3 * 365:
            to_acceptance.append((accepted - start).days)
    result = {"n": len(to_publication), **quantiles(to_publication),
              "accept_n": len(to_acceptance), "accept_median_days": quantiles(to_acceptance)["median_days"],
              "articles_read": len(articles), "years": sorted(set(years))}
    return result


def survey(journal: dict, articles: int, interval: float) -> dict:
    urls = homepages(journal.get("homepage_url"))
    if not urls:
        return {"status": "no-website"}
    page, final, base = None, urls[0], None
    first: tuple[str, str] | None = None
    # The registered address is often stale (a parked "www." host, plain http): try its variants until one
    # of them is an OJS site, and fall back to the first page that answered.
    for url in [variant for url in urls for variant in url_variants(url)]:
        page, final = fetch(url, interval)
        if not page:
            continue
        first = first or (page, final)
        base = ojs_base(final, page)
        if base:
            break
    if not base and first:
        page, final = first
    if not page:
        return {"status": "unreachable", "url": urls[0]}
    measured = measure(article_urls(base, articles, interval), interval) if base else None
    declared = declared_times(base, final, interval)
    status = "ok" if (measured and measured["n"]) or declared else ("no-dates" if base else "not-ojs")
    return {"status": status, "url": final, "ojs_base": base, "measured": measured, "declared": declared}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--articles", type=int, default=12)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--interval", type=float, default=0.7, help="seconds between requests to one host")
    parser.add_argument("--only", default=None, help="comma-separated publindex_ids to survey")
    args = parser.parse_args()

    document = json.loads(args.file.read_text(encoding="utf-8"))
    wanted = {int(x) for x in args.only.split(",")} if args.only else None
    journals = [j for j in document["journals"] if wanted is None or j["publindex_id"] in wanted]
    today = dt.date.today().isoformat()
    done = 0
    with cf.ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(survey, j, args.articles, args.interval): j for j in journals}
        for future in cf.as_completed(futures):
            journal = futures[future]
            try:
                journal["review_time"] = {"surveyed_at": today, **future.result()}
            except Exception as exc:  # one broken site never stops the survey
                journal["review_time"] = {"surveyed_at": today, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            done += 1
            if done % 25 == 0:
                print(f"{done}/{len(journals)}", file=sys.stderr, flush=True)
    args.file.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    statuses: dict[str, int] = {}
    for journal in journals:
        status = journal["review_time"]["status"]
        statuses[status] = statuses.get(status, 0) + 1
    measured = [j for j in journals if (j["review_time"].get("measured") or {}).get("n", 0) >= 5]
    print(json.dumps({"surveyed": len(journals), "status": statuses, "measured_n_ge_5": len(measured),
                      "declared": sum(bool(j["review_time"].get("declared")) for j in journals)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
