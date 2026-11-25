"""The idea brief: ``.papersmith/idea_brief.json``, the record of the idea-shaping phase.

Schema 1 (every key always present after :func:`load`)::

    {"schema": 1, "updated_at": iso,
     "bank": {"choice": "banco-lia"|"other"|"none"|null, "server": str|null, "compatible": bool|null,
              "tools": [str], "available": bool|null, "reason": str|null, "checked_at": iso|null},
     "profile": {"orcid", "openalex_author", "scholar_url", "display_name", "works_count",
                 "topics": [{"name", "count"}], "source": "openalex"|"none"|null, "reason"},
     "experience": {"level": "student"|"early-career"|"experienced"|"senior"|null,
                    "methods": [str], "resources": [str], "time": str|null},
     "interests": {"keywords": [str], "domain": str|null, "admired_paper": str|null},
     "topics": [{"id": "t1", "title", "rationale", "keywords": [str],
                 "evidence": [{"source": "bank:<server>"|"openalex"|"profile"|"operator"|"guide",
                               "detail", "count", "url"}]}],
     "chosen": {"topic_ids": [str], "note": str|null},
     "draft": {"text", "source_topics": [str], "gate": {"ok", "score", "missing": [str]},
               "approved": bool, "approved_at": iso|null},
     "history": [{"at": iso, "step": str}]}

:func:`record` merges one step and appends a ``history`` event. ``bank``,
``profile``, ``topics`` and ``draft`` are replaced whole (each is the result of
one lookup, proposal or composition); ``experience``, ``interests`` and
``chosen`` merge the fields given into the ones recorded, so answering one
question keeps the others. Writes are atomic (a temporary file in the same
folder, then ``os.replace``). A refusal raises :class:`IdeaError` with a code.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PATH = ".papersmith/idea_brief.json"
SCHEMA = 1
LEVELS = ("student", "early-career", "experienced", "senior")
STEPS = ("bank", "profile", "experience", "interests", "topics", "chosen", "draft")
#: Steps whose new data replaces the recorded one; the others merge.
REPLACED = frozenset({"bank", "profile", "topics", "draft"})
MAX_TEXT = 4000

EMPTY: dict[str, Any] = {
    "schema": SCHEMA,
    "updated_at": None,
    "bank": {"choice": None, "server": None, "compatible": None, "tools": [], "available": None,
             "reason": None, "checked_at": None},
    "profile": {"orcid": None, "openalex_author": None, "scholar_url": None, "display_name": None,
                "works_count": None, "topics": [], "source": None, "reason": None},
    "experience": {"level": None, "methods": [], "resources": [], "time": None},
    "interests": {"keywords": [], "domain": None, "admired_paper": None},
    "topics": [],
    "chosen": {"topic_ids": [], "note": None},
    "draft": {"text": "", "source_topics": [], "gate": {"ok": False, "score": None, "missing": []},
              "approved": False, "approved_at": None},
    "history": [],
}


class IdeaError(ValueError):
    """A refusal of the idea-shaping engine: ``code`` names it, ``str()`` explains it."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path(root: Path | str) -> Path:
    return Path(root) / PATH


def empty() -> dict[str, Any]:
    return copy.deepcopy(EMPTY)


def _complete(data: dict[str, Any]) -> dict[str, Any]:
    """``data`` with every schema key present (missing ones from :data:`EMPTY`)."""
    brief = empty()
    for key, value in data.items():  # a damaged field (wrong type) keeps its default
        default = brief.get(key)
        if isinstance(default, dict):
            if isinstance(value, dict):
                brief[key] = {**default, **value}
        elif isinstance(default, list):
            if isinstance(value, list):
                brief[key] = value
        else:
            brief[key] = value
    brief["schema"] = SCHEMA
    return brief


def load(root: Path | str) -> dict[str, Any]:
    """The recorded brief, or an empty one when absent. An existing file that
    is not a JSON object refuses (``BRIEF_UNREADABLE``) rather than being
    silently replaced by the next write."""
    target = path(root)
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return empty()
    except OSError as exc:
        raise IdeaError("BRIEF_UNREADABLE", f"cannot read {PATH}: {exc.strerror or exc}") from None
    try:
        data = json.loads(text)
    except ValueError:
        raise IdeaError("BRIEF_UNREADABLE", f"{PATH} is not valid JSON; fix or remove it") from None
    if not isinstance(data, dict):
        raise IdeaError("BRIEF_UNREADABLE", f"{PATH} is not a JSON object; fix or remove it")
    return _complete(data)


def save(root: Path | str, brief: dict[str, Any]) -> dict[str, Any]:
    """Write ``brief`` atomically and return it."""
    target = path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=target.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(brief, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return brief


# --------------------------------------------------------------------------
# Field normalisation
# --------------------------------------------------------------------------
def text_or_none(value: Any, limit: int = MAX_TEXT) -> str | None:
    if value is None:
        return None
    clean = " ".join(str(value).split())[:limit]
    return clean or None


def words(value: Any) -> list[str]:
    """A list of short entries from a list or a comma/semicolon separated text,
    trimmed, without empty entries or case-insensitive duplicates."""
    if value is None:
        return []
    raw = value if isinstance(value, (list, tuple)) else str(value).replace(";", ",").split(",")
    found: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        word = text_or_none(entry, 120)
        if word and word.casefold() not in seen:
            seen.add(word.casefold())
            found.append(word)
    return found


def _level(value: Any) -> str | None:
    level = text_or_none(value)
    if level is None:
        return None
    level = level.lower().replace("_", "-").replace(" ", "-")
    if level not in LEVELS:
        raise IdeaError("LEVEL_UNKNOWN", f"level must be one of {', '.join(LEVELS)} (got {value!r})")
    return level


def _normalized(step: str, data: dict[str, Any]) -> dict[str, Any]:
    """Only the fields ``data`` gives, in their schema shape."""
    out: dict[str, Any] = {}
    if step == "experience":
        if "level" in data:
            out["level"] = _level(data["level"])
        for key in ("methods", "resources"):
            if key in data:
                out[key] = words(data[key])
        if "time" in data:
            out["time"] = text_or_none(data["time"], 200)
    elif step == "interests":
        if "keywords" in data:
            out["keywords"] = words(data["keywords"])
        for key in ("domain", "admired_paper"):
            if key in data:
                out[key] = text_or_none(data[key], 400)
    elif step == "chosen":
        if "topic_ids" in data:
            out["topic_ids"] = words(data["topic_ids"])
        if "note" in data:
            out["note"] = text_or_none(data["note"], 1000)
    else:
        out = dict(data)
    return out


def record(root: Path | str, step: str, data: Any) -> dict[str, Any]:
    """Merge one step into the brief, append a ``history`` event, save
    atomically and return the whole brief."""
    if step not in STEPS:
        raise IdeaError("STEP_UNKNOWN", f"unknown step {step!r}; expected one of {', '.join(STEPS)}")
    brief = load(root)
    stamp = now()
    if step == "topics":
        if not isinstance(data, list):
            raise IdeaError("STEP_INVALID", "topics must be a list")
        brief["topics"] = data
    else:
        if not isinstance(data, dict):
            raise IdeaError("STEP_INVALID", f"{step} must be an object")
        fields = _normalized(step, data)
        base = EMPTY[step] if step in REPLACED else brief[step]
        brief[step] = {**copy.deepcopy(base), **fields}
    brief["updated_at"] = stamp
    brief["history"] = [*brief.get("history", []), {"at": stamp, "step": step}]
    return save(root, brief)


__all__ = ["EMPTY", "IdeaError", "LEVELS", "PATH", "SCHEMA", "STEPS", "empty", "load", "now", "path",
           "record", "save", "text_or_none", "words"]
