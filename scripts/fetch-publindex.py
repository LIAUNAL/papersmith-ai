#!/usr/bin/env python3
"""Refresh skills/journal-finder/data/publindex-ibn.json from Minciencias' Publindex.

The national journal list (IBN - Publindex) in force is read from the public API that backs
https://scienti.minciencias.gov.co/publindex/#/revistasPublindex/clasificacion:

    GET  <api>/publico/revistasPublindex/categorias/<A1|A2|B|C|RC>   the journals of a category
    GET  <api>/publico/revistasPublindex/<id>                         one journal, with its classifications

Each journal is then described from OpenAlex by its ISSNs (`/sources?filter=issn:a|b|...`, 50 per call):
its main topics with their subfield and field (English names, which the national search matches the paper
against), open-access and DOAJ state, APC and h-index. `OPENALEX_API_KEY` is sent when set.

Run it when Minciencias publishes a new classification (the file records its `valid_until`;
journal_cli.py notes when that date has passed). It only reads the public API and writes the file.

    python scripts/fetch-publindex.py [--out PATH] [--resolution 0707-2026]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import html
import json
import re
import sys
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://scienti.minciencias.gov.co/publindex/api/publico"
PAGE = "https://scienti.minciencias.gov.co/publindex/#/revistasPublindex/clasificacion"
CATEGORIES = ("A1", "A2", "B", "C", "RC")
SCOPE_CHARS = 500
OPENALEX = "https://api.openalex.org/sources"
OPENALEX_SELECT = "id,display_name,issn,is_oa,is_in_doaj,apc_usd,summary_stats,topics"
TOPICS_KEPT = 8
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "skills" / "journal-finder" / "data" / "publindex-ibn.json"


def get(url: str):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "papersmith-publindex-refresh"})
            with urllib.request.urlopen(request, timeout=40) as response:
                return json.loads(response.read())
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    return None


def issn(raw: str) -> str | None:
    compact = re.sub(r"[^0-9Xx]", "", raw or "").upper()
    return f"{compact[:4]}-{compact[4:]}" if len(compact) == 8 else None


def plain(markup: str | None, limit: int) -> str:
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", markup or ""))).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + " …"


def openalex_records(issns: list[str]) -> dict[str, dict]:
    """OpenAlex sources by ISSN; a journal OpenAlex does not know is simply absent."""
    by_issn: dict[str, dict] = {}
    key = os.environ.get("OPENALEX_API_KEY")
    for start in range(0, len(issns), 50):
        params = {"filter": "issn:" + "|".join(issns[start:start + 50]), "per-page": 200, "select": OPENALEX_SELECT}
        if key:
            params["api_key"] = key
        for source in get(f"{OPENALEX}?{urllib.parse.urlencode(params)}").get("results") or []:
            for number in source.get("issn") or []:
                by_issn.setdefault(number, source)
        time.sleep(0.2)
    return by_issn


def describe(source: dict | None) -> dict | None:
    if not source:
        return None
    topics = []
    for topic in (source.get("topics") or [])[:TOPICS_KEPT]:
        topics.append({"name": topic.get("display_name"),
                       "subfield": (topic.get("subfield") or {}).get("display_name"),
                       "field": (topic.get("field") or {}).get("display_name")})
    stats = source.get("summary_stats") or {}
    return {"id": (source.get("id") or "").rsplit("/", 1)[-1] or None, "display_name": source.get("display_name"),
            "is_oa": source.get("is_oa"), "is_in_doaj": source.get("is_in_doaj"), "apc_usd": source.get("apc_usd"),
            "h_index": stats.get("h_index"), "topics": topics}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--resolution", default=None, help="the Minciencias resolution that published the list")
    args = parser.parse_args()

    listed = [(category, row) for category in CATEGORIES for row in get(f"{API}/revistasPublindex/categorias/{category}")]
    with cf.ThreadPoolExecutor(6) as pool:
        details = list(pool.map(lambda pair: get(f"{API}/revistasPublindex/{pair[1]['id']}"), listed))

    journals, periods = [], set()
    for (category, row), detail in zip(listed, details):
        latest = max((detail or {}).get("clasificaciones") or [{}],
                     key=lambda c: (c.get("nroAnoIbn") or 0, c.get("txtSemestreIbn") or ""))
        if latest.get("txtClasificacion") not in (None, category):
            print(f"warning: {row['txtNombre']!r} is listed under {category} but classified "
                  f"{latest.get('txtClasificacion')}", file=sys.stderr)
        if latest.get("nroAnoIbn"):
            periods.add((latest["nroAnoIbn"], latest.get("txtSemestreIbn") or "", (latest.get("dtaVigencia") or "")[:10]))
        journals.append({
            "publindex_id": row["id"],
            "name": " ".join(row["txtNombre"].split()),
            "category": category,
            "issn": [i for i in (issn(x) for x in row.get("issns") or []) if i],
            "institutions": [" ".join(i.split()) for i in row.get("instituciones") or []],
            "homepage_url": (row.get("txtPaginaWeb") or "").strip() or None,
            "scope": plain((detail or {}).get("txtOrientacionEditorial"), SCOPE_CHARS),
        })
    by_issn = openalex_records(sorted({number for journal in journals for number in journal["issn"]}))
    for journal in journals:
        journal["openalex"] = describe(next((by_issn[n] for n in journal["issn"] if n in by_issn), None))
    if len(periods) != 1:
        print(f"refused: the journals carry more than one classification period: {sorted(periods)}", file=sys.stderr)
        return 2
    year, semester, valid_until = periods.pop()
    document = {
        "schema": 1,
        "source": PAGE,
        "api": API,
        "retrieved_at": dt.date.today().isoformat(),
        "period": f"{year}-{semester}" if semester else str(year),
        "resolution": args.resolution,
        "valid_until": valid_until or None,
        "categories": list(CATEGORIES),
        "journals": sorted(journals, key=lambda j: (CATEGORIES.index(j["category"]), j["name"].lower())),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    counts = {c: sum(j["category"] == c for j in journals) for c in CATEGORIES}
    print(json.dumps({"out": str(args.out), "period": document["period"], "valid_until": document["valid_until"],
                      "journals": len(journals), "by_category": counts,
                      "in_openalex": sum(j["openalex"] is not None for j in journals)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
