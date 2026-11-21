#!/usr/bin/env python3
"""The paper-type catalogue: the kinds of paper smith knows, in one data file.

``paper_types.json`` next to this file is the single source of truth the
paper-type advisor, the dashboard's Paper type panel, plausibility and the docs
read. Each type names what kind of contribution it is, where its novelty lies,
its canonical stages, the reporting guidelines journals expect, the words that
signal it in an idea, and whether smith already has a flow (``line``) for it:

* ``available`` types map to a workspace line (``experimental`` or ``review``,
  the ``paper_kind`` values ``smith init --kind`` accepts);
* ``planned`` types have no line yet (``line`` is null).

Names and summaries are English; the dashboard translates its own labels.
Signals are lowercase ASCII stems matched against the folded idea text.

    python -m skills._core.paper_types.registry list   # one JSON object
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

CATALOGUE = Path(__file__).resolve().parent / "paper_types.json"
STATUSES = ("available", "planned")
LINES = ("experimental", "review")
MAX_NAME = 48
MAX_SUMMARY = 200
_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_SIGNAL_RE = re.compile(r"^[a-z0-9][a-z0-9 +-]*$")
_REQUIRED = ("id", "name", "status", "line", "summary", "novelty", "stages", "guidelines", "signals")


class RegistryError(ValueError):
    """The catalogue is malformed, or a type it does not hold was asked for."""


def _fail(type_id: str, message: str) -> None:
    raise RegistryError(f"paper type {type_id!r}: {message}")


def _check(item: Any) -> dict:
    if not isinstance(item, dict):
        raise RegistryError("every paper type must be a JSON object")
    type_id = str(item.get("id", "?"))
    for field in _REQUIRED:
        if field not in item:
            _fail(type_id, f"missing field {field!r}")
    if not isinstance(item["id"], str) or not _ID_RE.match(item["id"]):
        _fail(type_id, "id must be lowercase kebab-case")
    if item["status"] not in STATUSES:
        _fail(type_id, f"status must be one of {', '.join(STATUSES)}")
    if item["status"] == "available" and item["line"] not in LINES:
        _fail(type_id, f"an available type needs a line in {', '.join(LINES)}")
    if item["status"] == "planned" and item["line"] is not None:
        _fail(type_id, "a planned type has no line yet (line must be null)")
    for field, limit in (("name", MAX_NAME), ("summary", MAX_SUMMARY), ("novelty", MAX_SUMMARY)):
        if not isinstance(item[field], str) or not item[field].strip() or len(item[field]) > limit:
            _fail(type_id, f"{field} must be non-empty text of at most {limit} characters")
    if not isinstance(item["stages"], list) or not item["stages"] or not all(
            isinstance(s, str) and s.strip() for s in item["stages"]):
        _fail(type_id, "stages must be a non-empty list of text")
    if not isinstance(item["guidelines"], list):
        _fail(type_id, "guidelines must be a list")
    for guideline in item["guidelines"]:
        if not isinstance(guideline, dict) or not str(guideline.get("name") or "").strip():
            _fail(type_id, "each guideline needs a name")
        if not str(guideline.get("url") or "").startswith("https://"):
            _fail(type_id, "each guideline url must start with https://")
    if not isinstance(item["signals"], list) or not item["signals"] or not all(
            isinstance(s, str) and _SIGNAL_RE.match(s) for s in item["signals"]):
        _fail(type_id, "signals must be a non-empty list of lowercase ASCII stems")
    return item


def validate(document: Any) -> list[dict]:
    """The types of a catalogue document, in order, or ``RegistryError``."""
    if not isinstance(document, dict) or not isinstance(document.get("types"), list):
        raise RegistryError("the catalogue must be an object with a `types` list")
    types = [_check(item) for item in document["types"]]
    seen: set[str] = set()
    for item in types:
        if item["id"] in seen:
            _fail(item["id"], "duplicate id")
        seen.add(item["id"])
    return types


def load(path: Path | None = None) -> list[dict]:
    """The validated catalogue, in display order."""
    source = Path(path) if path else CATALOGUE
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RegistryError(f"cannot read the paper-type catalogue {source.name}: {error}") from error
    return validate(document)


def get(type_id: str, path: Path | None = None) -> dict:
    for item in load(path):
        if item["id"] == type_id:
            return item
    raise RegistryError(f"unknown paper type {type_id!r}")


def available(path: Path | None = None) -> list[dict]:
    return [item for item in load(path) if item["status"] == "available"]


def by_line(line: str, path: Path | None = None) -> dict:
    """The available type a workspace line (``paper_kind``) stands for."""
    for item in available(path):
        if item["line"] == line:
            return item
    raise RegistryError(f"no available paper type for line {line!r}")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["list"]:
        sys.stdout.write(json.dumps({"ok": False, "error": "USAGE",
                                     "message": "usage: python -m skills._core.paper_types.registry list"}) + "\n")
        return 2
    try:
        types = load()
    except RegistryError as error:
        sys.stdout.write(json.dumps({"ok": False, "error": "CATALOGUE_INVALID", "message": str(error)}) + "\n")
        return 1
    sys.stdout.write(json.dumps({"ok": True, "types": types}, ensure_ascii=False) + "\n")
    return 0


__all__ = ["CATALOGUE", "LINES", "MAX_SUMMARY", "RegistryError", "STATUSES", "available", "by_line", "get",
           "load", "main", "validate"]

if __name__ == "__main__":
    raise SystemExit(main())
