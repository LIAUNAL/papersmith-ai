#!/usr/bin/env python3
"""PRISMA 2020 systematic review records for a review workspace.

Every stage of a systematic review leaves a record under ``<root>/review/``,
so the methods and the flow diagram are transcribed from what was run, never
from memory:

    protocol.json        objective, research questions (PICOC), criteria,
                         sources with their query strings, date range,
                         appraisal checklist, extraction fields
    protocol.lock.json   the operator's approval (gate G-PROTOCOL) and its
                         amendments, pinned to the protocol's sha256
    searches.jsonl       one line per search or import: date, source, exact
                         query, total hits, records kept
    records.jsonl        one line per record identified, with its
                         ``duplicate_of`` once deduplicated
    screening.jsonl      one line per decision: stage (ta = title/abstract,
                         ft = full text), reviewer, decision, reason
    appraisal.jsonl      quality / risk-of-bias answers per included study
    extraction.jsonl     extracted data items, each with the quote holding it
    prisma.json          the flow counts; biblio.json the bibliometrics;
    scope.json           the existing reviews found while scoping

Verbs (every one prints one JSON object; a refusal exits 2):

    init | protocol check|approve|amend | scope | search | import | dedupe |
    queue | screen | conflicts | kappa | appraise | extract | prisma | flow |
    biblio | checklist | status

Environment: PAPERSMITH_CONTACT_EMAIL (polite pool), OPENALEX_API_KEY,
PAPERSMITH_OPENALEX_URL, PAPERSMITH_CROSSREF_URL, PAPERSMITH_EUROPEPMC_URL
(base URLs, tests point them at a local server), PAPERSMITH_HTTP_TIMEOUT.
Stdlib only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import itertools
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

SCHEMA = 1
SOURCES = ("openalex", "crossref", "europepmc")
STAGES = ("ta", "ft")
DECISIONS = {"ta": ("include", "exclude"), "ft": ("include", "exclude", "not-retrieved")}
OPENALEX_DEFAULT = "https://api.openalex.org"
CROSSREF_DEFAULT = "https://api.crossref.org"
EUROPEPMC_DEFAULT = "https://www.ebi.ac.uk/europepmc/webservices/rest"
DEFAULT_MAX = 2000
PRISMA_URL = "https://www.prisma-statement.org"


class Refusal(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- files


def review_dir(root: Path) -> Path:
    return root / "review"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        # mkstemp creates 0600; a review record is an ordinary file of the
        # workspace, readable like the jsonl files appended beside it.
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(temp, 0o666 & ~umask)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _write_json(path: Path, data) -> None:
    _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _read_json(path: Path, code: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Refusal(code, f"{path} does not exist") from None
    except (OSError, ValueError) as exc:
        raise Refusal(code, f"{path} cannot be read as JSON ({exc})") from None


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError as exc:
            raise Refusal("RECORDS_CORRUPT", f"{path}:{number} is not JSON ({exc})") from None
    return rows


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def _rewrite_jsonl(path: Path, rows: list[dict]) -> None:
    _atomic_write(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


# --------------------------------------------------------------------------- protocol

PROTOCOL_TEMPLATE = {
    "schema": SCHEMA,
    "title": "<topic> in <scope>: a systematic review",
    "objective": "<one sentence: what the review maps, compares or concludes>",
    "review_type": "systematic review",
    "guidelines": ["PRISMA 2020"],
    "research_questions": [
        {"id": "RQ1", "question": "<research question>",
         "picoc": {"population": "", "intervention": "", "comparison": "", "outcomes": "", "context": ""}},
    ],
    "criteria": {
        "inclusion": [{"id": "I1", "text": "<criterion>", "reason": "<why>"}],
        "exclusion": [{"id": "E1", "text": "<criterion>", "reason": "<why>"}],
    },
    "sources": [
        {"name": "openalex", "query": "<query string as run on OpenAlex search>"},
        {"name": "crossref", "query": "<query string as run on Crossref>"},
    ],
    "date_range": {"from": "2015-01-01", "to": "2025-12-31"},
    "languages": ["en"],
    "publication_types": ["journal article", "conference paper"],
    "screening": {"reviewers": 2, "stages": ["title-abstract", "full-text"]},
    "appraisal": {
        "tool": "Kitchenham and Charters quality checklist",
        "questions": [{"id": "QA1", "text": "Are the aims of the study clearly stated?"}],
        "scale": {"yes": 1, "partly": 0.5, "no": 0},
        "threshold": None,
    },
    "extraction": {
        "fields": [{"id": "method", "description": "<what to extract>", "type": "text"}],
    },
    "amendments": [],
}


def protocol_path(root: Path) -> Path:
    return review_dir(root) / "protocol.json"


def lock_path(root: Path) -> Path:
    return review_dir(root) / "protocol.lock.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ids(entries, prefix: str, owner: str, problems: list[str]) -> list[str]:
    ids = []
    for index, entry in enumerate(entries or []):
        if not isinstance(entry, dict) or not str(entry.get("id", "")).strip():
            problems.append(f"{owner}[{index}] has no id")
            continue
        ids.append(entry["id"])
        if not re.fullmatch(rf"{prefix}\d+", entry["id"]):
            problems.append(f"{owner}[{index}] id {entry['id']!r} is not {prefix}<n>")
    if len(set(ids)) != len(ids):
        problems.append(f"{owner} repeats an id")
    return ids


def _placeholder(value) -> bool:
    return isinstance(value, str) and ("<" in value and ">" in value)


def check_protocol(protocol) -> list[str]:
    problems: list[str] = []
    if not isinstance(protocol, dict):
        return ["the protocol is not a JSON object"]
    for key in ("title", "objective"):
        if not isinstance(protocol.get(key), str) or not protocol[key].strip() or _placeholder(protocol[key]):
            problems.append(f"{key} is missing or still a placeholder")
    rqs = protocol.get("research_questions")
    if not isinstance(rqs, list) or not rqs:
        problems.append("research_questions is empty")
    else:
        _ids(rqs, "RQ", "research_questions", problems)
        for rq in rqs:
            if isinstance(rq, dict) and (not str(rq.get("question", "")).strip() or _placeholder(rq.get("question"))):
                problems.append(f"{rq.get('id', '?')} has no question")
    criteria = protocol.get("criteria") if isinstance(protocol.get("criteria"), dict) else {}
    for kind, prefix in (("inclusion", "I"), ("exclusion", "E")):
        entries = criteria.get(kind)
        if not isinstance(entries, list) or not entries:
            problems.append(f"criteria.{kind} is empty")
            continue
        _ids(entries, prefix, f"criteria.{kind}", problems)
        for entry in entries:
            if isinstance(entry, dict) and (not str(entry.get("text", "")).strip() or _placeholder(entry.get("text"))):
                problems.append(f"criterion {entry.get('id', '?')} has no text")
    sources = protocol.get("sources")
    if not isinstance(sources, list) or not sources:
        problems.append("sources is empty")
    else:
        names = []
        for index, source in enumerate(sources):
            if not isinstance(source, dict) or not str(source.get("name", "")).strip():
                problems.append(f"sources[{index}] has no name")
                continue
            names.append(source["name"])
            if not str(source.get("query", "")).strip() or _placeholder(source.get("query")):
                problems.append(f"source {source['name']} has no query string")
        if len(set(names)) != len(names):
            problems.append("sources repeats a name")
    dates = protocol.get("date_range") if isinstance(protocol.get("date_range"), dict) else {}
    for key in ("from", "to"):
        try:
            dt.date.fromisoformat(str(dates.get(key)))
        except ValueError:
            problems.append(f"date_range.{key} is not YYYY-MM-DD")
    appraisal = protocol.get("appraisal") if isinstance(protocol.get("appraisal"), dict) else {}
    if not isinstance(appraisal.get("questions"), list) or not appraisal["questions"]:
        problems.append("appraisal.questions is empty")
    else:
        _ids(appraisal["questions"], "QA", "appraisal.questions", problems)
    scale = appraisal.get("scale")
    if not isinstance(scale, dict) or not scale or not all(isinstance(v, (int, float)) for v in scale.values()):
        problems.append("appraisal.scale must map each answer to a number")
    fields = (protocol.get("extraction") or {}).get("fields") if isinstance(protocol.get("extraction"), dict) else None
    if not isinstance(fields, list) or not fields:
        problems.append("extraction.fields is empty")
    else:
        seen = set()
        for index, field in enumerate(fields):
            if not isinstance(field, dict) or not re.fullmatch(r"[a-z][a-z0-9_]*", str(field.get("id", ""))):
                problems.append(f"extraction.fields[{index}] needs a snake_case id")
                continue
            if field["id"] in seen:
                problems.append(f"extraction field {field['id']} repeats")
            seen.add(field["id"])
            if field.get("type", "text") not in ("text", "number", "category", "list"):
                problems.append(f"extraction field {field['id']} has an unknown type")
            if field.get("type") == "category" and not field.get("options"):
                problems.append(f"extraction field {field['id']} is a category without options")
    reviewers = (protocol.get("screening") or {}).get("reviewers", 2) if isinstance(protocol.get("screening"), dict) else 2
    if not isinstance(reviewers, int) or reviewers < 1:
        problems.append("screening.reviewers must be a positive integer")
    return problems


def load_protocol(root: Path) -> dict:
    protocol = _read_json(protocol_path(root), "PROTOCOL_ABSENT")
    problems = check_protocol(protocol)
    if problems:
        raise Refusal("PROTOCOL_INVALID", "; ".join(problems))
    return protocol


def require_approved(root: Path) -> dict:
    protocol = load_protocol(root)
    lock = lock_path(root)
    if not lock.is_file():
        raise Refusal("PROTOCOL_NOT_APPROVED",
                      "the operator has not approved review/protocol.json (gate G-PROTOCOL): "
                      "run `protocol approve --by <name>` after reading it")
    data = _read_json(lock, "PROTOCOL_LOCK_CORRUPT")
    if data.get("sha256") != _sha256(protocol_path(root)):
        raise Refusal("PROTOCOL_CHANGED",
                      "review/protocol.json changed after its approval; record the change with "
                      "`protocol amend --by <name> --reason <why>`")
    return protocol


def cmd_init(args) -> dict:
    root = Path(args.root)
    path = protocol_path(root)
    if path.exists() and not args.force:
        raise Refusal("PROTOCOL_EXISTS", f"{path} already exists; edit it, or pass --force to start over")
    template = json.loads(json.dumps(PROTOCOL_TEMPLATE))
    if args.title:
        template["title"] = args.title
    _write_json(path, template)
    return {"ok": True, "path": str(path), "next": "fill every <placeholder>, then `protocol check`"}


def cmd_protocol(args) -> dict:
    root = Path(args.root)
    if args.action == "check":
        protocol = _read_json(protocol_path(root), "PROTOCOL_ABSENT")
        problems = check_protocol(protocol)
        approved = None
        if lock_path(root).is_file():
            lock = _read_json(lock_path(root), "PROTOCOL_LOCK_CORRUPT")
            approved = {"by": lock.get("approved_by"), "at": lock.get("approved_at"),
                        "current": lock.get("sha256") == _sha256(protocol_path(root))}
        return {"ok": not problems, "problems": problems, "approval": approved}
    if not args.by or not args.by.strip():
        raise Refusal("APPROVER_MISSING", "--by names the operator who approves the protocol")
    protocol = load_protocol(root)
    digest = _sha256(protocol_path(root))
    if args.action == "approve":
        if lock_path(root).is_file():
            raise Refusal("PROTOCOL_ALREADY_APPROVED",
                          "the protocol is already approved; a later change is an amendment (`protocol amend`)")
        lock = {"approved_by": args.by.strip(), "approved_at": _now(), "sha256": digest, "amendments": []}
    else:  # amend
        if not args.reason or not args.reason.strip():
            raise Refusal("AMENDMENT_REASON_MISSING", "--reason states why the protocol changed")
        lock = _read_json(lock_path(root), "PROTOCOL_NOT_APPROVED")
        if lock.get("sha256") == digest:
            raise Refusal("PROTOCOL_UNCHANGED", "the protocol has not changed since its approval")
        lock.setdefault("amendments", []).append(
            {"by": args.by.strip(), "at": _now(), "reason": args.reason.strip(),
             "from_sha256": lock.get("sha256"), "sha256": digest})
        lock["sha256"] = digest
    _write_json(lock_path(root), lock)
    return {"ok": True, "approval": lock, "research_questions": len(protocol["research_questions"])}


# --------------------------------------------------------------------------- HTTP


def _base(env: str, default: str) -> str:
    return (os.environ.get(env, "").strip() or default).rstrip("/")


def _http_json(url: str) -> dict:
    email = os.environ.get("PAPERSMITH_CONTACT_EMAIL", "").strip()
    agent = "papersmith-systematic-review/1" + (f" (mailto:{email})" if email else "")
    request = urllib.request.Request(url, headers={"User-Agent": agent, "Accept": "application/json"})
    timeout = float(os.environ.get("PAPERSMITH_HTTP_TIMEOUT", "30") or 30)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise Refusal("SOURCE_UNAVAILABLE", f"{url.split('?')[0]} answered HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise Refusal("SOURCE_UNAVAILABLE", f"{url.split('?')[0]} failed ({exc})") from None


def _inverted_abstract(index) -> str:
    if not isinstance(index, dict):
        return ""
    words = sorted((position, word) for word, positions in index.items() for position in positions)
    return " ".join(word for _, word in words)


def _strip_tags(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


def normalize_doi(value) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", text)
    return text


def _record(source: str, **fields) -> dict:
    return {"source": source, "title": " ".join(str(fields.get("title") or "").split()),
            "abstract": fields.get("abstract") or "", "authors": fields.get("authors") or [],
            "year": fields.get("year"), "venue": fields.get("venue") or "",
            "doi": normalize_doi(fields.get("doi")), "keywords": fields.get("keywords") or [],
            "url": fields.get("url") or "", "type": fields.get("type") or ""}


def search_openalex(query: str, date_from: str, date_to: str, limit: int, *, extra_filter: str = "") -> tuple[int, list]:
    base = _base("PAPERSMITH_OPENALEX_URL", OPENALEX_DEFAULT)
    filters = f"from_publication_date:{date_from},to_publication_date:{date_to}" + (f",{extra_filter}" if extra_filter else "")
    cursor, total, out = "*", 0, []
    key = os.environ.get("OPENALEX_API_KEY", "").strip()
    while cursor and len(out) < limit:
        params = {"search": query, "filter": filters, "per-page": str(min(200, limit - len(out))), "cursor": cursor}
        if key:
            params["api_key"] = key
        data = _http_json(f"{base}/works?{urllib.parse.urlencode(params)}")
        total = int((data.get("meta") or {}).get("count") or 0)
        results = data.get("results") or []
        for work in results:
            source = ((work.get("primary_location") or {}).get("source") or {})
            out.append(_record(
                "openalex", title=work.get("display_name") or work.get("title"),
                abstract=_inverted_abstract(work.get("abstract_inverted_index")),
                authors=[(a.get("author") or {}).get("display_name", "") for a in work.get("authorships") or []],
                year=work.get("publication_year"), venue=source.get("display_name"), doi=work.get("doi"),
                keywords=[k.get("display_name", "") for k in work.get("keywords") or []],
                url=work.get("id"), type=work.get("type")))
        cursor = (data.get("meta") or {}).get("next_cursor")
        if not results:
            break
    return total, out[:limit]


def search_crossref(query: str, date_from: str, date_to: str, limit: int) -> tuple[int, list]:
    base = _base("PAPERSMITH_CROSSREF_URL", CROSSREF_DEFAULT)
    cursor, total, out = "*", 0, []
    while cursor and len(out) < limit:
        params = {"query": query, "filter": f"from-pub-date:{date_from},until-pub-date:{date_to}",
                  "rows": str(min(500, limit - len(out))), "cursor": cursor}
        email = os.environ.get("PAPERSMITH_CONTACT_EMAIL", "").strip()
        if email:
            params["mailto"] = email
        message = _http_json(f"{base}/works?{urllib.parse.urlencode(params)}").get("message") or {}
        total = int(message.get("total-results") or 0)
        items = message.get("items") or []
        for item in items:
            parts = ((item.get("issued") or {}).get("date-parts") or [[None]])[0]
            out.append(_record(
                "crossref", title=(item.get("title") or [""])[0], abstract=_strip_tags(item.get("abstract", "")),
                authors=[" ".join(filter(None, (a.get("given"), a.get("family")))) for a in item.get("author") or []],
                year=parts[0] if parts else None, venue=(item.get("container-title") or [""])[0],
                doi=item.get("DOI"), keywords=item.get("subject") or [], url=item.get("URL"), type=item.get("type")))
        cursor = message.get("next-cursor")
        if not items:
            break
    return total, out[:limit]


def search_europepmc(query: str, date_from: str, date_to: str, limit: int) -> tuple[int, list]:
    base = _base("PAPERSMITH_EUROPEPMC_URL", EUROPEPMC_DEFAULT)
    full = f"({query}) AND FIRST_PDATE:[{date_from} TO {date_to}]"
    cursor, total, out = "*", 0, []
    while cursor and len(out) < limit:
        params = {"query": full, "format": "json", "resultType": "core",
                  "pageSize": str(min(1000, limit - len(out))), "cursorMark": cursor}
        data = _http_json(f"{base}/search?{urllib.parse.urlencode(params)}")
        total = int(data.get("hitCount") or 0)
        results = (data.get("resultList") or {}).get("result") or []
        for item in results:
            keywords = ((item.get("keywordList") or {}).get("keyword")) or []
            out.append(_record(
                "europepmc", title=item.get("title"), abstract=_strip_tags(item.get("abstractText", "")),
                authors=[a.strip() for a in str(item.get("authorString", "")).rstrip(".").split(",") if a.strip()],
                year=int(item["pubYear"]) if str(item.get("pubYear", "")).isdigit() else None,
                venue=((item.get("journalInfo") or {}).get("journal") or {}).get("title", ""),
                doi=item.get("doi"), keywords=keywords,
                url=f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id', '')}",
                type=item.get("pubType", "")))
        next_cursor = data.get("nextCursorMark")
        cursor = None if not results or next_cursor == cursor else next_cursor
    return total, out[:limit]


SEARCHERS = {"openalex": search_openalex, "crossref": search_crossref, "europepmc": search_europepmc}


# --------------------------------------------------------------------------- identification


def _next_id(rows: list[dict], key: str, prefix: str, width: int) -> int:
    numbers = [int(row[key][len(prefix):]) for row in rows if str(row.get(key, "")).startswith(prefix)
               and row[key][len(prefix):].isdigit()]
    return max(numbers, default=0) + 1


def _store_search(root: Path, *, source: str, query: str, total: int, records: list[dict], method: str,
                  file: str | None = None) -> dict:
    searches_path = review_dir(root) / "searches.jsonl"
    records_path = review_dir(root) / "records.jsonl"
    searches = _read_jsonl(searches_path)
    existing = _read_jsonl(records_path)
    search_id = f"S{_next_id(searches, 'id', 'S', 1)}"
    first = _next_id(existing, "id", "R", 4)
    stored = []
    for offset, record in enumerate(records):
        stored.append({"id": f"R{first + offset:04d}", "search_id": search_id, **record, "duplicate_of": None})
    entry = {"id": search_id, "source": source, "query": query, "method": method, "run_at": _now(),
             "total": total, "retrieved": len(stored)}
    if file:
        entry["file"] = file
    _append_jsonl(records_path, stored)
    _append_jsonl(searches_path, [entry])
    return entry


def cmd_scope(args) -> dict:
    root = Path(args.root)
    if len(args.query.split()) < 2:
        raise Refusal("QUERY_TOO_SHORT", "describe the topic in a few words at least")
    today = dt.date.today().isoformat()
    total, works = search_openalex(args.query, "1900-01-01", today, args.limit, extra_filter="type:review")
    document = {"generated_at": _now(), "query": args.query, "source": "openalex (type:review)",
                "total": total, "reviews": works}
    _write_json(review_dir(root) / "scope.json", document)
    return {"ok": True, "path": str(review_dir(root) / "scope.json"), "total": total,
            "reviews": [{"title": w["title"], "year": w["year"], "venue": w["venue"], "doi": w["doi"]}
                        for w in works]}


def cmd_search(args) -> dict:
    root = Path(args.root)
    protocol = require_approved(root)
    entry = next((s for s in protocol["sources"] if s["name"] == args.source), None)
    if entry is None:
        raise Refusal("SOURCE_NOT_IN_PROTOCOL",
                      f"the protocol has no source named {args.source!r}; add it (an amendment) first")
    dates = protocol["date_range"]
    total, records = SEARCHERS[args.source](entry["query"], dates["from"], dates["to"], args.max)
    logged = _store_search(root, source=args.source, query=entry["query"], total=total, records=records,
                           method="api")
    notes = []
    if total > len(records):
        notes.append(f"{args.source} reports {total} hits but {len(records)} were retrieved (--max {args.max}); "
                     "PRISMA counts what was retrieved, so narrow the query or raise --max")
    return {"ok": True, "search": logged, "notes": notes}


def _ris_records(text: str) -> list[dict]:
    records, current = [], {}
    for line in text.splitlines():
        match = re.match(r"^([A-Z][A-Z0-9])  - ?(.*)$", line)
        if not match:
            continue
        tag, value = match.group(1), match.group(2).strip()
        if tag == "ER":
            if current:
                records.append(current)
            current = {}
            continue
        current.setdefault(tag, []).append(value)
    if current:
        records.append(current)
    out = []
    for item in records:
        first = lambda *tags: next((item[t][0] for t in tags if item.get(t)), "")  # noqa: E731
        year = re.search(r"(19|20)\d{2}", first("PY", "Y1", "DA") or "")
        out.append({"title": first("TI", "T1", "CT"), "abstract": first("AB", "N2"),
                    "authors": item.get("AU", []) + item.get("A1", []),
                    "year": int(year.group(0)) if year else None, "venue": first("T2", "JO", "JF", "JA", "BT"),
                    "doi": first("DO"), "keywords": item.get("KW", []), "url": first("UR"), "type": first("TY")})
    return out


def _bibtex_records(text: str) -> list[dict]:
    out = []
    for match in re.finditer(r"@(\w+)\s*\{\s*[^,]*,", text):
        start, depth, index = match.end(), 1, match.end()
        while index < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[index], 0)
            index += 1
        body = text[start:index - 1]
        fields = {}
        position = 0
        while True:
            found = re.compile(r"\s*([A-Za-z][\w-]*)\s*=\s*").match(body, position)
            if not found:
                break
            name, cursor = found.group(1).lower(), found.end()
            if cursor < len(body) and body[cursor] == "{":
                level, end = 0, cursor
                while end < len(body):
                    level += {"{": 1, "}": -1}.get(body[end], 0)
                    end += 1
                    if level == 0:
                        break
                value = body[cursor + 1:end - 1]
            elif cursor < len(body) and body[cursor] == '"':
                end = body.index('"', cursor + 1) + 1
                value = body[cursor + 1:end - 1]
            else:
                end = cursor
                while end < len(body) and body[end] not in ",\n":
                    end += 1
                value = body[cursor:end]
            fields[name] = " ".join(value.replace("{", "").replace("}", "").split())
            comma = body.find(",", end)
            if comma < 0:
                break
            position = comma + 1
        year = re.search(r"(19|20)\d{2}", fields.get("year", ""))
        out.append({"title": fields.get("title", ""), "abstract": fields.get("abstract", ""),
                    "authors": [a.strip() for a in fields.get("author", "").split(" and ") if a.strip()],
                    "year": int(year.group(0)) if year else None,
                    "venue": fields.get("journal") or fields.get("booktitle", ""), "doi": fields.get("doi", ""),
                    "keywords": [k.strip() for k in re.split(r"[;,]", fields.get("keywords", "")) if k.strip()],
                    "url": fields.get("url", ""), "type": match.group(1).lower()})
    return out


def cmd_import(args) -> dict:
    root = Path(args.root)
    require_approved(root)
    path = Path(args.file).expanduser()
    if not path.is_file():
        raise Refusal("IMPORT_FILE_ABSENT", f"{path} does not exist")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    kind = args.format or ("bibtex" if path.suffix.lower() in (".bib", ".bibtex") else "ris")
    parsed = _bibtex_records(text) if kind == "bibtex" else _ris_records(text)
    if not parsed:
        raise Refusal("IMPORT_EMPTY", f"{path} holds no {kind} record")
    if not args.query.strip():
        raise Refusal("QUERY_MISSING", "--query is the exact query string run on that database")
    records = [_record(args.source, **item) for item in parsed]
    logged = _store_search(root, source=args.source, query=args.query.strip(), total=len(records),
                           records=records, method=f"import:{kind}", file=path.name)
    return {"ok": True, "search": logged}


def normalize_title(title: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).split())


def cmd_dedupe(args) -> dict:
    root = Path(args.root)
    path = review_dir(root) / "records.jsonl"
    records = _read_jsonl(path)
    if not records:
        raise Refusal("NO_RECORDS", "no record has been identified yet; run `search` or `import`")
    by_doi, by_title, removed = {}, {}, 0
    for record in records:
        if record.get("duplicate_of"):
            continue
        keys = []
        if record.get("doi"):
            keys.append(("doi", record["doi"]))
        title = normalize_title(record.get("title", ""))
        if title:
            keys.append(("title", (title, record.get("year"))))
        original = None
        for kind, key in keys:
            original = (by_doi if kind == "doi" else by_title).get(key)
            if original:
                break
        if original:
            record["duplicate_of"] = original
            removed += 1
            continue
        for kind, key in keys:
            (by_doi if kind == "doi" else by_title).setdefault(key, record["id"])
    _rewrite_jsonl(path, records)
    unique = sum(1 for r in records if not r.get("duplicate_of"))
    return {"ok": True, "records": len(records), "duplicates_marked": removed,
            "duplicates_total": len(records) - unique, "unique": unique}


# --------------------------------------------------------------------------- screening


def _unique_records(root: Path) -> list[dict]:
    return [r for r in _read_jsonl(review_dir(root) / "records.jsonl") if not r.get("duplicate_of")]


def _screening(root: Path) -> list[dict]:
    return _read_jsonl(review_dir(root) / "screening.jsonl")


def stage_outcomes(root: Path, stage: str, required: int) -> dict[str, dict]:
    """record id -> {"decision": include|exclude|not-retrieved|None, "state", "reason", "by"}."""
    latest: dict[str, dict[str, dict]] = {}
    final: dict[str, dict] = {}
    for row in _screening(root):
        if row.get("stage") != stage:
            continue
        if row.get("final"):
            final[row["record_id"]] = row
        else:
            latest.setdefault(row["record_id"], {})[row["reviewer"]] = row
    outcomes = {}
    for record_id in set(latest) | set(final):
        if record_id in final:
            row = final[record_id]
            outcomes[record_id] = {"decision": row["decision"], "state": "final", "reason": row.get("reason")}
            continue
        votes = latest[record_id]
        decisions = {row["decision"] for row in votes.values()}
        if len(decisions) > 1:
            outcomes[record_id] = {"decision": None, "state": "conflict", "reason": None}
        elif len(votes) < required:
            outcomes[record_id] = {"decision": None, "state": "partial", "reason": None}
        else:
            decision = decisions.pop()
            reasons = sorted({row.get("reason") for row in votes.values() if row.get("reason")})
            outcomes[record_id] = {"decision": decision, "state": "agreed", "reason": reasons[0] if reasons else None}
    return outcomes


def _required_reviewers(root: Path) -> int:
    try:
        protocol = load_protocol(root)
    except Refusal:
        return 2
    return int((protocol.get("screening") or {}).get("reviewers", 2))


def _eligible(root: Path, stage: str) -> list[dict]:
    unique = _unique_records(root)
    if stage == "ta":
        return unique
    ta = stage_outcomes(root, "ta", _required_reviewers(root))
    return [r for r in unique if (ta.get(r["id"]) or {}).get("decision") == "include"]


def cmd_queue(args) -> dict:
    root = Path(args.root)
    eligible = _eligible(root, args.stage)
    done = {row["record_id"] for row in _screening(root)
            if row.get("stage") == args.stage and (row.get("reviewer") == args.reviewer or row.get("final"))}
    pending = [r for r in eligible if r["id"] not in done]
    shown = pending[: args.limit] if args.limit else pending
    return {"ok": True, "stage": args.stage, "reviewer": args.reviewer, "pending": len(pending),
            "records": [{"id": r["id"], "title": r["title"], "year": r["year"], "venue": r["venue"],
                         "doi": r["doi"], "abstract": r["abstract"] if args.stage == "ta" else ""}
                        for r in shown]}


def cmd_screen(args) -> dict:
    root = Path(args.root)
    protocol = require_approved(root)
    if args.decision not in DECISIONS[args.stage]:
        raise Refusal("DECISION_INVALID", f"--decision at stage {args.stage} is one of {', '.join(DECISIONS[args.stage])}")
    eligible = {r["id"] for r in _eligible(root, args.stage)}
    if args.record not in eligible:
        raise Refusal("RECORD_NOT_ELIGIBLE",
                      f"{args.record} is not a record awaiting {args.stage} screening "
                      "(unknown, a duplicate, or not included at title/abstract)")
    exclusion_ids = {c["id"] for c in protocol["criteria"]["exclusion"]}
    if args.decision == "exclude":
        if args.stage == "ft" and not args.reason:
            raise Refusal("REASON_MISSING", "a full-text exclusion names the protocol's exclusion criterion (--reason E<n>)")
        if args.reason and args.reason not in exclusion_ids:
            raise Refusal("REASON_UNKNOWN", f"{args.reason} is not an exclusion criterion of the protocol")
    elif args.reason:
        raise Refusal("REASON_UNEXPECTED", "only an exclusion carries a reason")
    if not args.reviewer.strip():
        raise Refusal("REVIEWER_MISSING", "--reviewer names who decided")
    row = {"record_id": args.record, "stage": args.stage, "reviewer": args.reviewer.strip(),
           "decision": args.decision, "reason": args.reason, "note": args.note or "", "final": bool(args.final),
           "at": _now()}
    _append_jsonl(review_dir(root) / "screening.jsonl", [row])
    outcome = stage_outcomes(root, args.stage, int(protocol["screening"].get("reviewers", 2))).get(args.record)
    return {"ok": True, "recorded": row, "outcome": outcome}


def cmd_conflicts(args) -> dict:
    root = Path(args.root)
    outcomes = stage_outcomes(root, args.stage, _required_reviewers(root))
    rows = _screening(root)
    conflicts = []
    for record_id, outcome in sorted(outcomes.items()):
        if outcome["state"] != "conflict":
            continue
        votes = {}
        for row in rows:
            if row.get("stage") == args.stage and row["record_id"] == record_id and not row.get("final"):
                votes[row["reviewer"]] = {"decision": row["decision"], "reason": row.get("reason"), "note": row.get("note")}
        conflicts.append({"record_id": record_id, "votes": votes})
    return {"ok": True, "stage": args.stage, "conflicts": conflicts}


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    labels = sorted({label for pair in pairs for label in pair})
    n = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / n
    first, second = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(first[label] * second[label] for label in labels) / (n * n)
    if expected == 1:
        return 1.0
    return round((observed - expected) / (1 - expected), 4)


def cmd_kappa(args) -> dict:
    root = Path(args.root)
    latest: dict[str, dict[str, str]] = {}
    for row in _screening(root):
        if row.get("stage") == args.stage and not row.get("final"):
            decision = "exclude" if row["decision"] == "not-retrieved" else row["decision"]
            latest.setdefault(row["reviewer"], {})[row["record_id"]] = decision
    reviewers = args.reviewers.split(",") if args.reviewers else sorted(latest)
    if len(reviewers) != 2:
        raise Refusal("REVIEWERS_AMBIGUOUS",
                      f"kappa compares two reviewers; found {', '.join(sorted(latest)) or 'none'} (use --reviewers a,b)")
    a, b = (latest.get(name, {}) for name in reviewers)
    shared = sorted(set(a) & set(b))
    pairs = [(a[record], b[record]) for record in shared]
    kappa = cohen_kappa(pairs)
    agreement = round(sum(1 for x, y in pairs if x == y) / len(pairs), 4) if pairs else None
    return {"ok": True, "stage": args.stage, "reviewers": reviewers, "records": len(pairs),
            "agreement": agreement, "kappa": kappa}


# --------------------------------------------------------------------------- appraisal and extraction


def _included(root: Path) -> list[dict]:
    ft = stage_outcomes(root, "ft", _required_reviewers(root))
    return [r for r in _unique_records(root) if (ft.get(r["id"]) or {}).get("decision") == "include"]


def _parse_json_arg(text: str, flag: str):
    try:
        return json.loads(text)
    except ValueError as exc:
        raise Refusal("ARGUMENT_INVALID", f"{flag} is not JSON ({exc})") from None


def cmd_appraise(args) -> dict:
    root = Path(args.root)
    protocol = require_approved(root)
    if args.record not in {r["id"] for r in _included(root)}:
        raise Refusal("RECORD_NOT_INCLUDED", f"{args.record} is not included after full-text screening")
    answers = _parse_json_arg(args.answers, "--answers")
    questions = [q["id"] for q in protocol["appraisal"]["questions"]]
    scale = protocol["appraisal"]["scale"]
    if not isinstance(answers, dict) or sorted(answers) != sorted(questions):
        raise Refusal("ANSWERS_INCOMPLETE", f"--answers maps every question ({', '.join(questions)}) to an answer")
    unknown = sorted({v for v in answers.values() if v not in scale})
    if unknown:
        raise Refusal("ANSWER_UNKNOWN", f"answers must be one of {', '.join(scale)}; got {', '.join(map(str, unknown))}")
    score = sum(scale[answers[q]] for q in questions)
    row = {"record_id": args.record, "reviewer": args.reviewer, "answers": answers, "score": score,
           "max_score": max(scale.values()) * len(questions), "note": args.note or "", "at": _now()}
    _append_jsonl(review_dir(root) / "appraisal.jsonl", [row])
    threshold = protocol["appraisal"].get("threshold")
    return {"ok": True, "recorded": row,
            "below_threshold": threshold is not None and score < threshold}


def cmd_extract(args) -> dict:
    root = Path(args.root)
    protocol = require_approved(root)
    if args.record not in {r["id"] for r in _included(root)}:
        raise Refusal("RECORD_NOT_INCLUDED", f"{args.record} is not included after full-text screening")
    data = _parse_json_arg(args.data, "--data")
    fields = {f["id"]: f for f in protocol["extraction"]["fields"]}
    if not isinstance(data, dict):
        raise Refusal("DATA_INVALID", "--data maps field ids to {value, quote}")
    unknown = sorted(set(data) - set(fields))
    if unknown:
        raise Refusal("FIELD_UNKNOWN", f"not extraction fields of the protocol: {', '.join(unknown)}")
    problems = []
    for name, item in data.items():
        if not isinstance(item, dict) or "value" not in item:
            problems.append(f"{name} needs a value")
            continue
        if not str(item.get("quote", "")).strip() and not item.get("page"):
            problems.append(f"{name} needs the quote or page of the study that holds it")
        field = fields[name]
        value = item["value"]
        if field.get("type") == "number" and not isinstance(value, (int, float)):
            problems.append(f"{name} is a number")
        if field.get("type") == "category" and value not in field.get("options", []):
            problems.append(f"{name} is one of {', '.join(field['options'])}")
        if field.get("type") == "list" and not isinstance(value, list):
            problems.append(f"{name} is a list")
    if problems:
        raise Refusal("DATA_INVALID", "; ".join(problems))
    row = {"record_id": args.record, "extractor": args.extractor, "data": data, "at": _now()}
    _append_jsonl(review_dir(root) / "extraction.jsonl", [row])
    missing = sorted(set(fields) - set(data))
    return {"ok": True, "recorded": row, "fields_missing": missing}


# --------------------------------------------------------------------------- synthesis


def prisma_counts(root: Path) -> dict:
    records = _read_jsonl(review_dir(root) / "records.jsonl")
    if not records:
        raise Refusal("NO_RECORDS", "no record has been identified yet; run `search` or `import`")
    required = _required_reviewers(root)
    by_source = Counter(r["source"] for r in records)
    duplicates = sum(1 for r in records if r.get("duplicate_of"))
    unique = [r for r in records if not r.get("duplicate_of")]
    ta = stage_outcomes(root, "ta", required)
    ft = stage_outcomes(root, "ft", required)
    ta_decided = {rid: o["decision"] for rid, o in ta.items() if o["decision"]}
    ft_decided = {rid: o["decision"] for rid, o in ft.items() if o["decision"]}
    unique_ids = {r["id"] for r in unique}
    sought = [rid for rid in unique_ids if ta_decided.get(rid) == "include"]
    ft_excluded = Counter(ft[rid]["reason"] or "unspecified" for rid in sought if ft_decided.get(rid) == "exclude")
    return {
        "generated_at": _now(),
        "identification": {"databases": dict(sorted(by_source.items())), "records": len(records),
                           "duplicates_removed": duplicates},
        "screening": {
            "records_screened": len(unique),
            "records_excluded": sum(1 for rid in unique_ids if ta_decided.get(rid) == "exclude"),
            "records_pending": sum(1 for rid in unique_ids if rid not in ta_decided),
            "reports_sought": len(sought),
            "reports_not_retrieved": sum(1 for rid in sought if ft_decided.get(rid) == "not-retrieved"),
            "reports_assessed": sum(1 for rid in sought if ft_decided.get(rid) in ("include", "exclude")),
            "reports_excluded": dict(sorted(ft_excluded.items())),
            "reports_pending": sum(1 for rid in sought if rid not in ft_decided),
        },
        "included": {"studies": sum(1 for rid in sought if ft_decided.get(rid) == "include")},
    }


def cmd_prisma(args) -> dict:
    root = Path(args.root)
    counts = prisma_counts(root)
    _write_json(review_dir(root) / "prisma.json", counts)
    pending = counts["screening"]["records_pending"] + counts["screening"]["reports_pending"]
    notes = [f"{pending} record(s) still await a screening decision; the counts are provisional"] if pending else []
    return {"ok": True, "path": str(review_dir(root) / "prisma.json"), "counts": counts, "notes": notes}


def _criterion_text(root: Path, reason: str) -> str:
    try:
        protocol = load_protocol(root)
    except Refusal:
        return reason
    for criterion in protocol["criteria"]["exclusion"]:
        if criterion["id"] == reason:
            text = criterion["text"]
            return f"{reason}: {text[:48] + '…' if len(text) > 49 else text}"
    return reason


def flow_svg(counts: dict, criteria: dict[str, str]) -> str:
    ident, screen, included = counts["identification"], counts["screening"], counts["included"]

    def box(x, y, w, lines, *, bold=False):
        h = 16 * len(lines) + 16
        text = "".join(
            f'<text x="{x + 10}" y="{y + 22 + 16 * i}" font-size="12"'
            f'{" font-weight=\"bold\"" if bold and i == 0 else ""}>{html.escape(line)}</text>'
            for i, line in enumerate(lines))
        return h, f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fff" stroke="#000"/>' + text

    def arrow(x1, y1, x2, y2):
        return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#000" marker-end="url(#a)"/>'

    parts, left, right, width = [], 140, 470, 300
    y = 20
    source_lines = [f"  {name} (n = {n})" for name, n in ident["databases"].items()]
    h1, b1 = box(left, y, width, ["Records identified from:", f"Databases (n = {ident['records']})"] + source_lines)
    h1r, b1r = box(right, y, width, ["Records removed before screening:",
                                     f"Duplicate records removed (n = {ident['duplicates_removed']})"])
    parts += [b1, b1r, arrow(left + width, y + h1 / 2, right, y + h1r / 2)]
    y2 = y + max(h1, h1r) + 30
    h2, b2 = box(left, y2, width, [f"Records screened (n = {screen['records_screened']})"])
    h2r, b2r = box(right, y2, width, [f"Records excluded (n = {screen['records_excluded']})"])
    parts += [arrow(left + width / 2, y + h1, left + width / 2, y2), b2, b2r,
              arrow(left + width, y2 + h2 / 2, right, y2 + h2r / 2)]
    y3 = y2 + max(h2, h2r) + 30
    h3, b3 = box(left, y3, width, [f"Reports sought for retrieval (n = {screen['reports_sought']})"])
    h3r, b3r = box(right, y3, width, [f"Reports not retrieved (n = {screen['reports_not_retrieved']})"])
    parts += [arrow(left + width / 2, y2 + h2, left + width / 2, y3), b3, b3r,
              arrow(left + width, y3 + h3 / 2, right, y3 + h3r / 2)]
    y4 = y3 + max(h3, h3r) + 30
    excluded_lines = [f"  {criteria.get(reason, reason)} (n = {n})" for reason, n in screen["reports_excluded"].items()]
    h4, b4 = box(left, y4, width, [f"Reports assessed for eligibility (n = {screen['reports_assessed']})"])
    h4r, b4r = box(right, y4, width, ["Reports excluded:"] + (excluded_lines or ["  (n = 0)"]))
    parts += [arrow(left + width / 2, y3 + h3, left + width / 2, y4), b4, b4r,
              arrow(left + width, y4 + h4 / 2, right, y4 + h4r / 2)]
    y5 = y4 + max(h4, h4r) + 30
    h5, b5 = box(left, y5, width, [f"Studies included in review (n = {included['studies']})"], bold=True)
    parts += [arrow(left + width / 2, y4 + h4, left + width / 2, y5), b5]
    total_h = y5 + h5 + 20
    labels = [("Identification", y, y + max(h1, h1r)), ("Screening", y2, y4 + max(h4, h4r)),
              ("Included", y5, y5 + h5)]
    for label, top, bottom in labels:
        mid = (top + bottom) / 2
        parts.append(f'<rect x="20" y="{top}" width="34" height="{bottom - top}" fill="#cfe2f3" stroke="#000"/>'
                     f'<text x="37" y="{mid}" font-size="12" font-weight="bold" text-anchor="middle" '
                     f'transform="rotate(-90 37 {mid})">{label}</text>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="{h}" viewBox="0 0 800 {h}" '
            'font-family="Helvetica, Arial, sans-serif">'
            '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
            '<path d="M0,0 L8,4 L0,8 z"/></marker></defs>'
            '<rect width="100%" height="100%" fill="#fff"/>{body}</svg>\n').format(h=total_h, body="".join(parts))


def cmd_flow(args) -> dict:
    root = Path(args.root)
    counts = prisma_counts(root)
    _write_json(review_dir(root) / "prisma.json", counts)
    reasons = {reason: _criterion_text(root, reason) for reason in counts["screening"]["reports_excluded"]}
    out = Path(args.out) if args.out else root / "paper" / "Figures" / "prisma-flow.svg"
    if not out.is_absolute():
        out = root / out
    _atomic_write(out, flow_svg(counts, reasons))
    return {"ok": True, "path": str(out), "counts": counts}


def cmd_biblio(args) -> dict:
    root = Path(args.root)
    included = _included(root)
    population, basis = (included, "included studies") if included else (_unique_records(root), "screened records")
    if not population:
        raise Refusal("NO_RECORDS", "no record has been identified yet; run `search` or `import`")
    years = Counter(r["year"] for r in population if r.get("year"))
    venues = Counter(r["venue"] for r in population if r.get("venue"))
    keyword_sets = [sorted({k.strip().lower() for k in r.get("keywords") or [] if k and k.strip()})
                    for r in population]
    keywords = Counter(k for ks in keyword_sets for k in ks)
    pairs = Counter(pair for ks in keyword_sets for pair in itertools.combinations(ks, 2))
    document = {
        "generated_at": _now(), "basis": basis, "count": len(population),
        "per_year": {str(y): n for y, n in sorted(years.items())},
        "top_venues": [{"venue": v, "count": n} for v, n in venues.most_common(args.top)],
        "top_keywords": [{"keyword": k, "count": n} for k, n in keywords.most_common(args.top)],
        "keyword_cooccurrence": [{"a": a, "b": b, "count": n} for (a, b), n in pairs.most_common(args.top)],
    }
    _write_json(review_dir(root) / "biblio.json", document)
    return {"ok": True, "path": str(review_dir(root) / "biblio.json"), **{k: document[k] for k in ("basis", "count", "per_year")}}


#: PRISMA 2020 main checklist (Page et al., 2021): item, topic, the section
#: blocks or sections that report it, and the review/ record that evidences it.
CHECKLIST = [
    (1, "Title", ("title-and-keywords.title",), None),
    (2, "Abstract", ("abstract",), None),
    (3, "Rationale", ("introduction.intro-rationale",), None),
    (4, "Objectives", ("introduction.intro-objectives",), "protocol"),
    (5, "Eligibility criteria", ("methods.m-eligibility",), "protocol"),
    (6, "Information sources", ("methods.m-information-sources",), "searches"),
    (7, "Search strategy", ("methods.m-search-strategy",), "searches"),
    (8, "Selection process", ("methods.m-selection-process",), "screening"),
    (9, "Data collection process", ("methods.m-data-collection",), "extraction"),
    (10, "Data items", ("methods.m-data-collection",), "protocol"),
    (11, "Study risk of bias assessment", ("methods.m-risk-of-bias",), "appraisal"),
    (12, "Effect measures", ("methods.m-synthesis",), None),
    (13, "Synthesis methods", ("methods.m-synthesis",), None),
    (14, "Reporting bias assessment", ("methods.m-certainty",), None),
    (15, "Certainty assessment", ("methods.m-certainty",), None),
    (16, "Study selection", ("results.r-study-selection",), "prisma"),
    (17, "Study characteristics", ("results.r-study-characteristics",), "extraction"),
    (18, "Risk of bias in studies", ("results.r-risk-of-bias",), "appraisal"),
    (19, "Results of individual studies", ("results.r-research-questions",), "extraction"),
    (20, "Results of syntheses", ("results.r-research-questions",), None),
    (21, "Reporting biases", ("results.r-research-questions",), None),
    (22, "Certainty of evidence", ("results.r-research-questions",), None),
    (23, "Discussion", ("discussion", "limitations"), None),
    (24, "Registration and protocol", ("methods.m-protocol-registration",), "approval"),
    (25, "Support", ("back-matter.bm-funding",), None),
    (26, "Competing interests", ("back-matter.bm-conflicts-of-interest",), None),
    (27, "Availability of data, code and other materials", ("back-matter.bm-data-availability",), None),
]

#: The digest paper-writing records for an opened block that holds no text.
_EMPTY_BODY = hashlib.sha256(b"").hexdigest()


def _evidence(root: Path) -> dict[str, bool]:
    base = review_dir(root)
    protocol_ok = protocol_path(root).is_file() and not check_protocol(
        _read_json(protocol_path(root), "PROTOCOL_ABSENT"))
    stages = {row.get("stage") for row in _screening(root)}
    return {
        "protocol": protocol_ok,
        "approval": lock_path(root).is_file(),
        "searches": bool(_read_jsonl(base / "searches.jsonl")),
        "screening": {"ta", "ft"} <= stages,
        "appraisal": bool(_read_jsonl(base / "appraisal.jsonl")),
        "extraction": bool(_read_jsonl(base / "extraction.jsonl")),
        "prisma": (base / "prisma.json").is_file() and (root / "paper" / "Figures" / "prisma-flow.svg").is_file(),
    }


def _paper_cli(root: Path, verb: str) -> dict | None:
    cli = root / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
    if not cli.is_file() or not (root / "paper" / "main.tex").is_file():
        return None
    try:
        completed = subprocess.run([sys.executable, str(cli), verb], cwd=root, capture_output=True,
                                   text=True, timeout=120)
        payload = json.loads(completed.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return payload if isinstance(payload, dict) and payload.get("status") == "ok" else None


def paper_state(root: Path) -> dict:
    """Which blocks of paper/main.tex hold text, and which declarations are
    recorded, as paper-writing itself reports them (`status`, `phases`)."""
    status = _paper_cli(root, "status")
    if status is None:
        return {"available": False, "written": set(), "declarations": set()}
    written = {block["id"] for block in status.get("blocks", []) if block.get("digest") != _EMPTY_BODY}
    phases = _paper_cli(root, "phases") or {}
    declared = set((phases.get("declared") or {}).get("declarations") or [])
    return {"available": True, "written": written, "declarations": declared}


def _target_written(target: str, written: set[str]) -> bool:
    if "." in target:
        return target in written
    return any(block.startswith(target + ".") for block in written)


def cmd_checklist(args) -> dict:
    root = Path(args.root)
    evidence = _evidence(root)
    paper = paper_state(root)
    items = []
    for number, topic, targets, record in CHECKLIST:
        missing = []
        if record is not None and not evidence[record]:
            missing.append(f"record:{record}")
        missing += [f"text:{target}" for target in targets if not _target_written(target, paper["written"])]
        if number == 24 and "review-registration" not in paper["declarations"]:
            missing.append("declaration:review-registration")
        items.append({"item": number, "topic": topic, "reported_in": list(targets), "record": record,
                      "status": "owed" if missing else "satisfied", "missing": missing})
    owed = [item["item"] for item in items if item["status"] == "owed"]
    notes = [] if paper["available"] else [
        "paper/main.tex is not scaffolded yet (`/paper-writing`), so every item still owes its text"]
    return {"ok": not owed, "checklist": "PRISMA 2020 (27 items)", "source": PRISMA_URL, "owed": owed,
            "notes": notes, "items": items}


def cmd_status(args) -> dict:
    root = Path(args.root)
    base = review_dir(root)
    protocol = None
    if protocol_path(root).is_file():
        problems = check_protocol(_read_json(protocol_path(root), "PROTOCOL_ABSENT"))
        protocol = {"valid": not problems, "problems": problems, "approved": lock_path(root).is_file()}
    searches = _read_jsonl(base / "searches.jsonl")
    summary = {"ok": True, "protocol": protocol,
               "searches": [{"id": s["id"], "source": s["source"], "retrieved": s["retrieved"], "run_at": s["run_at"]}
                            for s in searches]}
    if _read_jsonl(base / "records.jsonl"):
        summary["prisma"] = prisma_counts(root)
    summary["appraised"] = len({r["record_id"] for r in _read_jsonl(base / "appraisal.jsonl")})
    summary["extracted"] = len({r["record_id"] for r in _read_jsonl(base / "extraction.jsonl")})
    return summary


# --------------------------------------------------------------------------- entry point


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # type: ignore[override]
        raise Refusal("USAGE", message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description="PRISMA 2020 systematic review records under <root>/review/.")
    parser.add_argument("--root", default=".", help="the review workspace (default: the current directory)")
    sub = parser.add_subparsers(dest="verb", required=True, parser_class=_Parser)
    # `--root` is accepted after the verb too (`review_cli.py search --root .`).
    common = _Parser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS)
    add_parser = sub.add_parser
    sub.add_parser = lambda *a, **k: add_parser(*a, parents=[common], **k)  # type: ignore[method-assign]

    p = sub.add_parser("init", help="write a review/protocol.json template")
    p.add_argument("--title", default=None)
    p.add_argument("--force", action="store_true", help="overwrite an existing protocol")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("protocol", help="check, approve (G-PROTOCOL) or amend the protocol")
    p.add_argument("action", choices=("check", "approve", "amend"))
    p.add_argument("--by", default=None, help="the operator approving or amending")
    p.add_argument("--reason", default=None, help="why the protocol was amended")
    p.set_defaults(func=cmd_protocol)

    p = sub.add_parser("scope", help="find existing reviews on the topic (OpenAlex, type:review)")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_scope)

    p = sub.add_parser("search", help="run the protocol's query on one source and log it")
    p.add_argument("--source", required=True, choices=SOURCES)
    p.add_argument("--max", type=int, default=DEFAULT_MAX, help=f"records retrieved at most (default {DEFAULT_MAX})")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("import", help="import a RIS or BibTeX export (Scopus, Web of Science, IEEE, ACM)")
    p.add_argument("--file", required=True)
    p.add_argument("--source", required=True, help="the database the export came from, e.g. scopus")
    p.add_argument("--query", required=True, help="the exact query string run on that database")
    p.add_argument("--format", choices=("ris", "bibtex"), default=None)
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("dedupe", help="mark duplicates by DOI, then by normalized title and year")
    p.set_defaults(func=cmd_dedupe)

    for name, func, text in (("queue", cmd_queue, "records a reviewer still owes a decision on"),
                             ("conflicts", cmd_conflicts, "records the reviewers disagree on")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--stage", required=True, choices=STAGES)
        if name == "queue":
            p.add_argument("--reviewer", required=True)
            p.add_argument("--limit", type=int, default=20)
        p.set_defaults(func=func)

    p = sub.add_parser("screen", help="record one reviewer's decision on one record")
    p.add_argument("--stage", required=True, choices=STAGES)
    p.add_argument("--record", required=True)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--decision", required=True)
    p.add_argument("--reason", default=None, help="the protocol's exclusion criterion, E<n>")
    p.add_argument("--note", default=None)
    p.add_argument("--final", action="store_true", help="the consensus decision that settles a conflict")
    p.set_defaults(func=cmd_screen)

    p = sub.add_parser("kappa", help="Cohen's kappa between two reviewers at one stage")
    p.add_argument("--stage", required=True, choices=STAGES)
    p.add_argument("--reviewers", default=None, help="a,b (default: the two reviewers on record)")
    p.set_defaults(func=cmd_kappa)

    p = sub.add_parser("appraise", help="record the quality / risk-of-bias answers for an included study")
    p.add_argument("--record", required=True)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--answers", required=True, help='JSON: {"QA1": "yes", ...}')
    p.add_argument("--note", default=None)
    p.set_defaults(func=cmd_appraise)

    p = sub.add_parser("extract", help="record extracted data items for an included study")
    p.add_argument("--record", required=True)
    p.add_argument("--extractor", required=True)
    p.add_argument("--data", required=True, help='JSON: {"field": {"value": ..., "quote": "..."}}')
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("prisma", help="count the PRISMA 2020 flow into review/prisma.json")
    p.set_defaults(func=cmd_prisma)

    p = sub.add_parser("flow", help="draw the PRISMA 2020 flow diagram (SVG)")
    p.add_argument("--out", default=None, help="default paper/Figures/prisma-flow.svg")
    p.set_defaults(func=cmd_flow)

    p = sub.add_parser("biblio", help="counts per year and venue, keyword co-occurrence")
    p.add_argument("--top", type=int, default=20)
    p.set_defaults(func=cmd_biblio)

    p = sub.add_parser("checklist", help="the 27 PRISMA 2020 items and what each still owes")
    p.set_defaults(func=cmd_checklist)

    p = sub.add_parser("status", help="summarise the review's records")
    p.set_defaults(func=cmd_status)
    return parser


def _emit(document) -> None:
    sys.stdout.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")


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
