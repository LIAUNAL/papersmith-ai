"""The dashboard's Review tab for a review workspace (paper-type-lines S6, T6b).

* ``view(root)``: what the Review tab draws, one JSON object with a section
  per panel -- ``summary`` (``review_cli.py status``), ``protocol`` (questions,
  criteria, sources, approval, amendments and where the registration is
  recorded), ``searches`` (the search log), ``screening`` (per stage totals,
  pending per reviewer, conflicts, Cohen's kappa or why it is not
  computable), ``prisma`` (the PRISMA 2020 counts, the saved
  ``review/prisma.json`` and the flow figure), ``extraction`` (the protocol's
  fields by included study, each value with its quote or page), ``appraisal``
  (the risk of bias: the per-study appraisal scores against the protocol's
  threshold; the protocol defines no risk-of-bias domains, so none are
  shown) and ``signoffs``.
* ``checklist(root)``: the 27 PRISMA 2020 items, served on demand only: the
  verb runs ``paper_cli.py`` as subprocesses and can take minutes.

Every record is read through the workspace's own ``review_cli.py`` (loaded by
:func:`review_board.load_review_cli`, which falls back to the dashboard's copy
and says why), never re-parsed here. Each section degrades on its own: a
malformed or absent record turns that section ``{"available": false, "code",
"message"}`` and the rest still answers. The object carries machine values
and the workspace's own words only (ids, states, codes, the protocol's text,
review_cli's diagnostics); the dashboard draws every label from its i18n
catalogues.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from ..paper_types import decision
from .review_board import load_review_cli

NOT_A_REVIEW_WORKSPACE = "NOT_A_REVIEW_WORKSPACE"
CLI_UNAVAILABLE = "REVIEW_CLI_UNAVAILABLE"
FLOW_FIGURE = "paper/Figures/prisma-flow.svg"
#: Where PRISMA item 24's registration is recorded (a /paper-writing declaration).
REGISTRATION = {"declaration": "review-registration", "checklist_item": 24}
SECTIONS = ("summary", "protocol", "searches", "screening", "prisma", "extraction", "appraisal", "signoffs")


def refusal(root: Path) -> dict[str, Any] | None:
    """The 409 body for a workspace that is not a review, ``None`` for a review."""
    line = decision.current_line(Path(root))
    if line == "review":
        return None
    return {"ok": False, "code": NOT_A_REVIEW_WORKSPACE, "paper_kind": line,
            "error": f"this is not a review workspace (paper_kind: {line}); the Review tab reads review/ records"}


# --------------------------------------------------------------------------- helpers


def _unavailable(code: str, message: str) -> dict[str, Any]:
    return {"available": False, "code": code, "message": message}


def _failure(rc: Any, exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, rc.Refusal):
        return _unavailable(exc.code, exc.message)
    return _unavailable("UNREADABLE", f"{type(exc).__name__}: {exc}")


def _section(rc: Any, build: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return {"available": True, **build()}
    except Exception as exc:  # noqa: BLE001 - one unreadable record never breaks the tab
        return _failure(rc, exc)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ("" if value is None else str(value))


def _texts(value: Any) -> list[str]:
    return [_text(item) for item in value] if isinstance(value, list) else []


def _entries(value: Any, *keys: str) -> list[dict[str, str]]:
    return [{key: _text(entry.get(key)) for key in keys} for entry in value if isinstance(entry, dict)] \
        if isinstance(value, list) else []


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _protocol_data(rc: Any, root: Path) -> dict[str, Any]:
    """The protocol as written (valid or not), ``{}`` when it is absent."""
    path = rc.protocol_path(root)
    return _object(rc._read_json(path, "PROTOCOL_ABSENT")) if path.is_file() else {}


def _safe_protocol(rc: Any, root: Path) -> dict[str, Any]:
    try:
        return _protocol_data(rc, root)
    except Exception:  # noqa: BLE001 - the protocol section reports it
        return {}


def _titles(rc: Any, root: Path) -> dict[str, dict[str, Any]]:
    return {record.get("id"): record for record in rc._unique_records(root)}


def _latest(rows: list[dict], *keys: str) -> dict[tuple, dict]:
    """The last row per ``keys`` (the records are append-only)."""
    out: dict[tuple, dict] = {}
    for row in rows:
        if isinstance(row, dict):
            out[tuple(row.get(key) for key in keys)] = row
    return out


# --------------------------------------------------------------------------- sections


def _summary(rc: Any, root: Path) -> dict[str, Any]:
    status = rc.cmd_status(argparse.Namespace(root=str(root)))
    prisma = status.get("prisma") or {}
    return {"protocol": status.get("protocol"), "searches": len(status.get("searches") or []),
            "records": (prisma.get("identification") or {}).get("records", 0),
            "included": (prisma.get("included") or {}).get("studies", 0),
            "appraised": status.get("appraised", 0), "extracted": status.get("extracted", 0)}


def _approval(rc: Any, root: Path) -> dict[str, Any]:
    lock_file = rc.lock_path(root)
    if not lock_file.is_file():
        return {"state": "absent", "amendments": []}
    try:
        lock = rc._read_json(lock_file, "PROTOCOL_LOCK_CORRUPT")
    except rc.Refusal as exc:
        return {"state": "corrupt", "code": exc.code, "message": exc.message, "amendments": []}
    if not isinstance(lock, dict):
        return {"state": "corrupt", "code": "PROTOCOL_LOCK_CORRUPT",
                "message": f"{lock_file} is not a JSON object", "amendments": []}
    path = rc.protocol_path(root)
    current = path.is_file() and lock.get("sha256") == rc._sha256(path)
    return {"state": "approved" if current else "changed", "by": _text(lock.get("approved_by")),
            "at": _text(lock.get("approved_at")),
            "amendments": _entries(lock.get("amendments"), "by", "at", "reason")}


def _protocol(rc: Any, root: Path) -> dict[str, Any]:
    if not rc.protocol_path(root).is_file():
        return {"present": False, "approval": _approval(rc, root), "registration": REGISTRATION}
    raw = rc._read_json(rc.protocol_path(root), "PROTOCOL_ABSENT")
    problems = rc.check_protocol(raw)
    data = _object(raw)
    questions = [{"id": _text(rq.get("id")), "question": _text(rq.get("question")),
                  "picoc": {key: _text(value) for key, value in _object(rq.get("picoc")).items()}}
                 for rq in data.get("research_questions") or [] if isinstance(rq, dict)] \
        if isinstance(data.get("research_questions"), list) else []
    criteria = _object(data.get("criteria"))
    dates = _object(data.get("date_range"))
    reviewers = _object(data.get("screening")).get("reviewers", 2)
    return {
        "present": True, "valid": not problems, "problems": problems,
        "title": _text(data.get("title")), "objective": _text(data.get("objective")),
        "review_type": _text(data.get("review_type")), "guidelines": _texts(data.get("guidelines")),
        "research_questions": questions,
        "criteria": {kind: _entries(criteria.get(kind), "id", "text", "reason") for kind in ("inclusion", "exclusion")},
        "sources": _entries(data.get("sources"), "name", "query"),
        "date_range": {"from": _text(dates.get("from")), "to": _text(dates.get("to"))},
        "languages": _texts(data.get("languages")), "publication_types": _texts(data.get("publication_types")),
        "reviewers": reviewers if isinstance(reviewers, int) else None,
        "approval": _approval(rc, root), "registration": REGISTRATION,
    }


def _searches(rc: Any, root: Path) -> dict[str, Any]:
    base = rc.review_dir(root)
    searches = rc._read_jsonl(base / "searches.jsonl")
    records = rc._read_jsonl(base / "records.jsonl")
    duplicates = sum(1 for record in records if record.get("duplicate_of"))
    rows = [{"id": row.get("id"), "source": row.get("source"), "query": row.get("query"),
             "method": row.get("method"), "run_at": row.get("run_at"), "total": row.get("total"),
             "retrieved": row.get("retrieved"), "file": row.get("file")} for row in searches]
    searched = {row["source"] for row in rows}
    planned = [source["name"] for source in _entries(_safe_protocol(rc, root).get("sources"), "name")]
    return {"rows": rows, "records": len(records), "duplicates": duplicates, "unique": len(records) - duplicates,
            "not_searched": [name for name in planned if name and name not in searched]}


def _kappa(rc: Any, root: Path, stage: str) -> dict[str, Any]:
    try:
        result = rc.cmd_kappa(argparse.Namespace(root=str(root), stage=stage, reviewers=None))
    except rc.Refusal as exc:
        return {"value": None, "code": exc.code, "message": exc.message, "records": 0, "agreement": None}
    out = {"value": result.get("kappa"), "agreement": result.get("agreement"), "records": result.get("records", 0),
           "reviewers": result.get("reviewers"), "code": None}
    if out["value"] is None:
        out["code"] = "NO_SHARED_RECORDS"
    return out


def _screening(rc: Any, root: Path) -> dict[str, Any]:
    required = rc._required_reviewers(root)
    rows = rc._screening(root)
    titles = _titles(rc, root)
    stages = []
    for stage in rc.STAGES:
        ids = [record["id"] for record in rc._eligible(root, stage)]
        outcomes = rc.stage_outcomes(root, stage, required)
        states = Counter((outcomes.get(rid) or {}).get("state") or "undecided" for rid in ids)
        decisions = Counter(outcomes[rid]["decision"] for rid in ids if (outcomes.get(rid) or {}).get("decision"))
        reviewers = sorted({row["reviewer"] for row in rows
                            if row.get("stage") == stage and not row.get("final") and row.get("reviewer")})
        pending = {name: rc.cmd_queue(argparse.Namespace(root=str(root), stage=stage, reviewer=name,
                                                         limit=0))["pending"] for name in reviewers}
        conflicts = [{"record_id": conflict["record_id"],
                      "title": _text((titles.get(conflict["record_id"]) or {}).get("title")),
                      "votes": conflict["votes"]}
                     for conflict in rc.cmd_conflicts(argparse.Namespace(root=str(root), stage=stage))["conflicts"]]
        stages.append({"stage": stage, "eligible": len(ids), "decided": sum(decisions.values()),
                       "decisions": dict(sorted(decisions.items())), "agreed": states["agreed"],
                       "final": states["final"], "partial": states["partial"], "undecided": states["undecided"],
                       "conflict_count": states["conflict"], "conflicts": conflicts, "reviewers": reviewers,
                       "pending_by_reviewer": pending, "kappa": _kappa(rc, root, stage)})
    return {"required_reviewers": required, "stages": stages}


def _without_stamp(counts: Any) -> Any:
    return {key: value for key, value in counts.items() if key != "generated_at"} if isinstance(counts, dict) else counts


def _prisma(rc: Any, root: Path) -> dict[str, Any]:
    base = rc.review_dir(root)
    counts = _without_stamp(rc.prisma_counts(root)) if rc._read_jsonl(base / "records.jsonl") else None
    saved = None
    if (base / "prisma.json").is_file():
        try:
            data = rc._read_json(base / "prisma.json", "PRISMA_CORRUPT")
            if not isinstance(data, dict):
                raise rc.Refusal("PRISMA_CORRUPT", f"{base / 'prisma.json'} is not a JSON object")
            saved = {"generated_at": _text(data.get("generated_at")), "current": _without_stamp(data) == counts}
        except rc.Refusal as exc:
            saved = {"code": exc.code, "message": exc.message, "current": False}
    figure = Path(root) / FLOW_FIGURE
    exists = figure.is_file()
    screen = (counts or {}).get("screening") or {}
    return {"counts": counts, "saved": saved,
            "pending": screen.get("records_pending", 0) + screen.get("reports_pending", 0),
            "flow": {"path": FLOW_FIGURE, "exists": exists, "mtime": int(figure.stat().st_mtime) if exists else None}}


def _extraction(rc: Any, root: Path) -> dict[str, Any]:
    protocol = _safe_protocol(rc, root)
    fields = [{"id": _text(field.get("id")), "description": _text(field.get("description")),
               "type": _text(field.get("type") or "text"), "options": _texts(field.get("options"))}
              for field in _object(protocol.get("extraction")).get("fields") or [] if isinstance(field, dict)]
    included = [record["id"] for record in rc._included(root)]
    latest = _latest(rc._read_jsonl(rc.review_dir(root) / "extraction.jsonl"), "record_id")
    titles = _titles(rc, root)
    order = included + sorted(key[0] for key in latest if key[0] not in included)
    studies = []
    for record_id in order:
        row = latest.get((record_id,))
        values = {name: {"value": item.get("value"), "quote": _text(item.get("quote")), "page": item.get("page")}
                  for name, item in _object((row or {}).get("data")).items() if isinstance(item, dict)}
        record = titles.get(record_id) or {}
        studies.append({"record_id": record_id, "title": _text(record.get("title")), "year": record.get("year"),
                        "included": record_id in included, "extracted": row is not None,
                        "extractor": _text((row or {}).get("extractor")), "at": _text((row or {}).get("at")),
                        "values": values})
    return {"fields": fields, "studies": studies, "included": len(included),
            "extracted": sum(1 for study in studies if study["included"] and study["extracted"])}


def _appraisal(rc: Any, root: Path) -> dict[str, Any]:
    appraisal = _object(_safe_protocol(rc, root).get("appraisal"))
    threshold = appraisal.get("threshold")
    threshold = threshold if isinstance(threshold, (int, float)) and not isinstance(threshold, bool) else None
    scale = {_text(key): value for key, value in _object(appraisal.get("scale")).items()}
    included = [record["id"] for record in rc._included(root)]
    titles = _titles(rc, root)
    studies = []
    for (record_id, reviewer), row in _latest(rc._read_jsonl(rc.review_dir(root) / "appraisal.jsonl"),
                                              "record_id", "reviewer").items():
        score = row.get("score")
        numeric = isinstance(score, (int, float)) and not isinstance(score, bool)
        studies.append({"record_id": record_id, "title": _text((titles.get(record_id) or {}).get("title")),
                        "reviewer": _text(reviewer), "answers": _object(row.get("answers")), "score": score,
                        "max_score": row.get("max_score"), "note": _text(row.get("note")), "at": _text(row.get("at")),
                        "included": record_id in included,
                        "below_threshold": threshold is not None and numeric and score < threshold})
    studies.sort(key=lambda study: (included.index(study["record_id"]) if study["included"] else len(included),
                                    _text(study["record_id"]), study["reviewer"]))
    appraised = {study["record_id"] for study in studies}
    return {"tool": _text(appraisal.get("tool")), "questions": _entries(appraisal.get("questions"), "id", "text"),
            "scale": scale, "threshold": threshold, "studies": studies,
            "not_appraised": [record_id for record_id in included if record_id not in appraised]}


def _signoffs(rc: Any, root: Path) -> dict[str, Any]:
    return {"gates": rc.signoff_status(root)}


_BUILDERS: dict[str, Callable[[Any, Path], dict[str, Any]]] = {
    "summary": _summary, "protocol": _protocol, "searches": _searches, "screening": _screening,
    "prisma": _prisma, "extraction": _extraction, "appraisal": _appraisal, "signoffs": _signoffs,
}


# --------------------------------------------------------------------------- entry points


def view(root: Path) -> dict[str, Any]:
    root = Path(root)
    rc, warning = load_review_cli(root)
    out: dict[str, Any] = {"paper_kind": decision.current_line(root), "cli_warning": warning}
    for name in SECTIONS:
        if rc is None:
            out[name] = _unavailable(CLI_UNAVAILABLE, "no review_cli.py could be loaded"
                                     + (f" ({warning})" if warning else ""))
        else:
            out[name] = _section(rc, lambda build=_BUILDERS[name]: build(rc, root))
    return out


def checklist(root: Path) -> dict[str, Any]:
    """``review_cli.py checklist``: slow (paper_cli subprocesses); call it off the event loop."""
    root = Path(root)
    rc, warning = load_review_cli(root)
    if rc is None:
        return {**_unavailable(CLI_UNAVAILABLE, "no review_cli.py could be loaded"
                               + (f" ({warning})" if warning else "")), "cli_warning": warning}

    def build() -> dict[str, Any]:
        result = rc.cmd_checklist(argparse.Namespace(root=str(root)))
        # cmd_checklist adds its one note exactly when paper-writing cannot report.
        return {**result, "paper_available": not result.get("notes"), "cli_warning": warning}

    return _section(rc, build)


__all__ = ["CLI_UNAVAILABLE", "FLOW_FIGURE", "NOT_A_REVIEW_WORKSPACE", "SECTIONS", "checklist", "refusal", "view"]
