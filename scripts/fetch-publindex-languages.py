#!/usr/bin/env python3
"""Record the manuscript languages of the Publindex journals the national search ranks (A1, A2 and B).

For each such journal of skills/journal-finder/data/publindex-ibn.json it stores, under `languages`:

* **published**: the share of each language among the journal's works since `--since` in OpenAlex
  (`/works?filter=primary_location.source.id:<id>,from_publication_date:<since>&group_by=language`),
  with the number of works counted.
* **declared**: sentences the journal publishes about the languages it receives, quoted from its own
  "about", submissions or author-guidelines pages with their URL, and the language codes they name.
* **accepts**: the languages it receives: the declared ones when the journal states them, else the
  languages that make up at least 10% of what it published (`basis` says which).

Only public pages are read. `OPENALEX_API_KEY` is sent when set.

    python scripts/fetch-publindex-languages.py [--file PATH] [--since 2023-01-01] [--categories A1,A2,B]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import importlib.util
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_FILE = HERE.parent / "skills" / "journal-finder" / "data" / "publindex-ibn.json"
OPENALEX = "https://api.openalex.org/works"
PUBLISHED_SHARE = 0.10
PAGES = ("about/submissions", "about", "about/editorialPolicies", "information/authors")
LANGUAGE_WORDS = {
    "es": r"espa[ñn]ol|castellano|spanish",
    "en": r"ingl[eé]s|english",
    "pt": r"portugu[eé]s|portuguese",
    "fr": r"franc[eé]s|french",
}
#: The sentence must speak of receiving or writing manuscripts in a language...
CONTEXT = re.compile(
    r"(?:art[ií]culos|manuscrit\w*|trabajos|contribuciones|papers|manuscripts|articles|submissions)\b.{0,90}"
    r"(?:recib|acept|accept|publica|escrit|redact|written|submitted|presentad|enviad)"
    r"|(?:recib|acept|accept|publica|escrib|escrit|redact|written|submit)\w*.{0,70}"
    r"(?:art[ií]culos|manuscrit|trabajos|papers|manuscripts|articles|contribuciones)"
    r"|idiomas? (?:de|para) (?:la )?publicaci|publication languages?|languages? of publication"
    r"|(?:en|in) (?:los |the )?(?:siguientes )?(?:idiomas|languages)", re.IGNORECASE)
#: ...and is neither the site's language switcher nor a rule about titles, abstracts or keywords.
EXCLUDE = re.compile(r"t[ií]tulo|\btitle|resumen|abstract|palabras clave|keywords|\(espa[ñn]a\)"
                     r"|(?:idioma|language)\s+(?:espa[ñn]ol|english)", re.IGNORECASE)
SENTENCE = re.compile(r"[^.!?\n]{0,240}(?:" + "|".join(LANGUAGE_WORDS.values()) + r")[^.!?\n]{0,240}", re.IGNORECASE)

_spec = importlib.util.spec_from_file_location("review_times", HERE / "fetch-publindex-review-times.py")
review_times = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review_times)


def get_json(url: str) -> dict | None:
    for _ in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "papersmith-publindex-languages"})
            with urllib.request.urlopen(request, timeout=40) as response:
                return json.loads(response.read())
        except Exception:
            time.sleep(2)
    return None


def published_languages(openalex_id: str, since: str) -> dict:
    params = {"filter": f"primary_location.source.id:{openalex_id},from_publication_date:{since}",
              "group_by": "language"}
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    data = get_json(f"{OPENALEX}?{urllib.parse.urlencode(params)}")
    groups = [(g.get("key") or "").rsplit("/", 1)[-1] for g in (data or {}).get("group_by") or []]
    counts = [g.get("count") or 0 for g in (data or {}).get("group_by") or []]
    total = sum(counts)
    shares = {code: round(count / total, 3) for code, count in zip(groups, counts) if code and total and count}
    return {"shares": dict(sorted(shares.items(), key=lambda kv: -kv[1])), "works": total, "since": since}


def declared_languages(base: str | None, home: str | None, interval: float) -> list[dict]:
    pages = [f"{base}/{page}" for page in PAGES] if base else []
    if home:
        pages.append(home)
    found, seen = [], set()
    for url in pages:
        page, final = review_times.fetch(url, interval)
        if not page:
            continue
        for match in SENTENCE.finditer(review_times.visible(page)):
            sentence = match.group(0).strip(" ,;:-")
            codes = sorted(code for code, rx in LANGUAGE_WORDS.items() if re.search(rx, sentence, re.IGNORECASE))
            if not codes or not CONTEXT.search(sentence) or EXCLUDE.search(sentence) or sentence.lower() in seen or len(sentence) > 480:
                continue
            seen.add(sentence.lower())
            found.append({"quote": sentence[:400], "url": final, "languages": codes})
            if len(found) >= 3:
                return found
    return found


def survey(journal: dict, since: str, interval: float) -> dict:
    openalex = journal.get("openalex") or {}
    published = published_languages(openalex["id"], since) if openalex.get("id") else {"shares": {}, "works": 0}
    review = journal.get("review_time") or {}
    declared = declared_languages(review.get("ojs_base"), review.get("url"), interval)
    named = sorted({code for quote in declared for code in quote["languages"]})
    if named:
        accepts, basis = named, "declared"
    else:
        accepts = [code for code, share in published["shares"].items() if share >= PUBLISHED_SHARE]
        basis = "published" if accepts else "unknown"
    return {"accepts": accepts, "basis": basis, "published": published, "declared": declared,
            "surveyed_at": dt.date.today().isoformat()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--since", default=f"{dt.date.today().year - 3}-01-01")
    parser.add_argument("--categories", default="A1,A2,B")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--interval", type=float, default=0.7)
    args = parser.parse_args()
    document = json.loads(args.file.read_text(encoding="utf-8"))
    wanted = set(args.categories.split(","))
    journals = [j for j in document["journals"] if j["category"] in wanted]
    with cf.ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(survey, j, args.since, args.interval): j for j in journals}
        for future in cf.as_completed(futures):
            journal = futures[future]
            try:
                journal["languages"] = future.result()
            except Exception as exc:  # one broken site never stops the survey
                journal["languages"] = {"accepts": [], "basis": "unknown", "error": f"{type(exc).__name__}: {exc}"}
    args.file.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    bases: dict[str, int] = {}
    for journal in journals:
        basis = journal["languages"]["basis"]
        bases[basis] = bases.get(basis, 0) + 1
    print(json.dumps({"surveyed": len(journals), "basis": bases,
                      "accepts_es_en": sum({"es", "en"} <= set(j["languages"]["accepts"]) for j in journals)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
