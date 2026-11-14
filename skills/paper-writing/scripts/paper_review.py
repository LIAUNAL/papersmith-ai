"""The final judge's rounds: `.papersmith/paper_review.json`.

The `paper-reviewer` agent reviews the assembled manuscript and returns one
round to `/paper-writing`; it never writes a file. This module is the one
writer of that round: it validates it, numbers and dates it, checks that it
judges every revision the previous round asked for, and appends it, so the
dashboard's final-judge panel (`GET /api/paper/review`, read-only) shows how
the manuscript moved from round to round.

The file is `{"rounds": [...]}`. Each round:

- `round` (assigned here: previous + 1) and `date` (assigned here, ISO day);
- `overall` 1-6, `confidence` 1-5, `recommendation` (non-empty text);
- `ratings`: exactly `Quality`, `Clarity`, `Significance`, `Originality`, 1-4;
- `items`: one verdict per revision of the previous round, `{"rank",
  "verdict", "evidence"}`, `verdict` one of `resolved`, `partly`,
  `not resolved`; `item` is filled here from that revision's text. A first
  round carries none;
- `revisions`: what this round asks for, `{"rank", "text", "status",
  "note"}`, `status` defaulting to `pending`;
- `excluded` (optional list of text) and `report` (the full review form).

A refused round leaves the file byte for byte as it was, and a file that is
already malformed is reported, never overwritten.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: The same cap the dashboard reads under (`server.PAPER_REVIEW_MAX_BYTES`):
#: a file the panel would refuse to read is never written.
MAX_BYTES = 2 * 1024 * 1024
RATINGS = ("Quality", "Clarity", "Significance", "Originality")
ITEM_VERDICTS = ("resolved", "partly", "not resolved")
REVISION_STATUSES = ("pending", "done", "applied", "not done", "skipped")


def review_path(paper_dir: Path) -> Path:
    """The workspace's review file: `<paper>/../.papersmith/paper_review.json`."""
    return paper_dir.parent / ".papersmith" / "paper_review.json"


def _int_in(value, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _text(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def load_rounds(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        if path.stat().st_size > MAX_BYTES:
            raise Refused("REVIEW_FILE_INVALID", f"{path} exceeds {MAX_BYTES} bytes")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refused("REVIEW_FILE_INVALID", f"{path} cannot be read as JSON: {exc}")
    rounds = data.get("rounds") if isinstance(data, dict) else None
    if not isinstance(rounds, list):
        raise Refused("REVIEW_FILE_INVALID", f'{path} holds no "rounds" list')
    return [r for r in rounds if isinstance(r, dict)]


def read_input(raw: str) -> dict:
    try:
        text = sys.stdin.read() if raw == "-" else Path(raw).read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refused("REVIEW_INPUT_UNREADABLE", f"{raw}: {exc}")
    if not isinstance(data, dict):
        raise Refused("REVIEW_INPUT_UNREADABLE", f"{raw}: the round must be a JSON object")
    return data


def _validate(data: dict) -> list[str]:
    errors = []
    if not _int_in(data.get("overall"), 1, 6):
        errors.append("overall must be an integer 1-6")
    if not _int_in(data.get("confidence"), 1, 5):
        errors.append("confidence must be an integer 1-5")
    if not _text(data.get("recommendation")):
        errors.append("recommendation must be non-empty text")
    ratings = data.get("ratings")
    if not isinstance(ratings, dict) or sorted(ratings) != sorted(RATINGS):
        errors.append(f"ratings must hold exactly {', '.join(RATINGS)}")
    else:
        errors += [f"ratings.{k} must be an integer 1-4" for k in RATINGS if not _int_in(ratings[k], 1, 4)]
    items = data.get("items", [])
    if not isinstance(items, list):
        errors.append("items must be a list")
    else:
        for n, item in enumerate(items, 1):
            if not isinstance(item, dict) or not _int_in(item.get("rank"), 1, 10**6):
                errors.append(f"items[{n}] needs an integer rank")
            elif item.get("verdict") not in ITEM_VERDICTS:
                errors.append(f"items[{n}].verdict must be one of {', '.join(ITEM_VERDICTS)}")
    revisions = data.get("revisions", [])
    if not isinstance(revisions, list):
        errors.append("revisions must be a list")
    else:
        ranks = []
        for n, rev in enumerate(revisions, 1):
            if not isinstance(rev, dict) or not _int_in(rev.get("rank"), 1, 10**6) or not _text(rev.get("text")):
                errors.append(f"revisions[{n}] needs an integer rank and non-empty text")
                continue
            ranks.append(rev["rank"])
            if rev.get("status", "pending") not in REVISION_STATUSES:
                errors.append(f"revisions[{n}].status must be one of {', '.join(REVISION_STATUSES)}")
        if len(ranks) != len(set(ranks)):
            errors.append("revisions ranks must be distinct")
    excluded = data.get("excluded", [])
    if not isinstance(excluded, list) or not all(isinstance(e, str) for e in excluded):
        errors.append("excluded must be a list of text")
    if not _text(data.get("report")):
        errors.append("report must be non-empty text (the full review form)")
    return errors


def _judged_items(items: list[dict], previous: dict | None) -> list[dict]:
    raised = {r["rank"]: r.get("text", "") for r in (previous or {}).get("revisions", [])
              if isinstance(r, dict) and "rank" in r}
    unknown = sorted({i["rank"] for i in items} - set(raised))
    if unknown:
        raise Refused("REVIEW_ITEM_UNKNOWN",
                      f"verdicts on revisions the previous round did not raise: {unknown}")
    missing = sorted(set(raised) - {i["rank"] for i in items})
    if missing:
        raise Refused("REVIEW_ITEMS_MISSING",
                      f"the previous round's revisions {missing} carry no verdict")
    return [{"rank": i["rank"], "item": raised[i["rank"]], "verdict": i["verdict"],
             "evidence": str(i.get("evidence", ""))} for i in sorted(items, key=lambda i: i["rank"])]


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def record(paper_dir: Path, data: dict, *, today: _dt.date | None = None) -> dict:
    """Validate one round, number and date it, and append it to the file."""
    path = review_path(paper_dir)
    rounds = load_rounds(path)
    errors = _validate(data)
    if errors:
        raise Refused("REVIEW_ROUND_INVALID", "; ".join(errors))
    previous = rounds[-1] if rounds else None
    number = (max((r.get("round") for r in rounds if _int_in(r.get("round"), 1, 10**6)), default=0)) + 1
    entry = {
        "round": number,
        "date": (today or _dt.date.today()).isoformat(),
        "overall": data["overall"],
        "confidence": data["confidence"],
        "recommendation": data["recommendation"].strip(),
        "ratings": {k: data["ratings"][k] for k in RATINGS},
        "items": _judged_items(data.get("items", []), previous),
        "revisions": [{"rank": r["rank"], "text": r["text"].strip(), "status": r.get("status", "pending"),
                       "note": str(r.get("note", ""))} for r in sorted(data.get("revisions", []),
                                                                     key=lambda r: r["rank"])],
        "excluded": list(data.get("excluded", [])),
        "report": data["report"],
    }
    payload = (json.dumps({"rounds": rounds + [entry]}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise Refused("REVIEW_FILE_INVALID", f"recording this round would exceed {MAX_BYTES} bytes")
    _atomic_write(path, payload)
    return {"round": number, "path": str(path), "rounds": len(rounds) + 1,
            "pending_revisions": sum(1 for r in entry["revisions"] if r["status"] == "pending")}
