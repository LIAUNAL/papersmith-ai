#!/usr/bin/env python3
"""The paper-type catalogue: the kinds of paper smith knows, in one data file.

``paper_types.json`` next to this file is the single source of truth the
paper-type advisor, the dashboard's Paper type panel, plausibility and the docs
read. Each type names what kind of contribution it is, where its novelty lies,
its canonical stages, the reporting guidelines journals expect, the words that
signal it in an idea, and whether smith already has a flow (``line``) for it:

* ``available`` types map to a workspace line (``experimental``, ``review``,
  ``observational-measurement``, ``hardware``, ``lab-simulation`` or
  ``data-resource``, the ``paper_kind`` values ``smith init --kind``
  accepts);
* ``planned`` types have no line yet (``line`` is null).

A type may group ``variants`` (each with its own name, summary, guidelines
and signals): the family is one flow and the variant chooses its checklist.
A variant may name ``checklist`` (the id of a reporting guideline the
checklist engine ships, ``skills/_core/checklists/guidelines/<id>.json``) and
``flow_template`` (a harness flow template); null or absent means none, and
the family's flow template. A type without variants may name its
``checklist`` on the family instead; a type with variants never does, its
variants choose. ``checklist_for`` reads either.
A family's signals are its own plus its variants'; no signal appears twice in
the catalogue. Names and summaries are English; the dashboard translates its
own labels. Signals are lowercase ASCII stems matched against the folded idea.

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
LINES = ("experimental", "review", "observational-measurement", "hardware", "lab-simulation", "data-resource")
GUIDELINES = Path(__file__).resolve().parent.parent / "checklists" / "guidelines"
MAX_NAME = 48
MAX_SUMMARY = 200
_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_SIGNAL_RE = re.compile(r"^[a-z0-9][a-z0-9 +-]*$")
_FLOW_TEMPLATE_RE = re.compile(r"^paper-flow[a-z0-9-]*\.md\.tpl$")
_REQUIRED = ("id", "name", "status", "line", "summary", "novelty", "stages", "guidelines", "signals")
_VARIANT_REQUIRED = ("id", "name", "summary", "guidelines", "signals")


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
    _check_guidelines(type_id, item["guidelines"])
    variants = item.get("variants", [])
    if not isinstance(variants, list):
        _fail(type_id, "variants must be a list")
    for variant in variants:
        if not isinstance(variant, dict):
            _fail(type_id, "each variant must be an object")
        for field in _VARIANT_REQUIRED:
            if field not in variant:
                _fail(type_id, f"variant {variant.get('id', '?')!r} is missing {field!r}")
        if not isinstance(variant["id"], str) or not _ID_RE.match(variant["id"]):
            _fail(type_id, "a variant id must be lowercase kebab-case")
        for field, limit in (("name", MAX_NAME), ("summary", MAX_SUMMARY)):
            if not isinstance(variant[field], str) or not variant[field].strip() or len(variant[field]) > limit:
                _fail(type_id, f"variant {variant['id']!r}: {field} must be non-empty text of at most {limit} characters")
        _check_guidelines(type_id, variant["guidelines"])
        _check_signals(type_id, variant["signals"], allow_empty=False)
        _check_variant_flow(type_id, variant)
    if "checklist" in item:
        if variants:
            _fail(type_id, "a type with variants names its checklist on each variant, not on the family")
        _check_checklist(type_id, "checklist", item["checklist"])
    _check_signals(type_id, item["signals"], allow_empty=bool(variants))
    every = all_signals(item)
    if len(set(every)) != len(every):
        _fail(type_id, "signals must not repeat")
    return item


def _check_guidelines(type_id: str, guidelines: Any) -> None:
    if not isinstance(guidelines, list):
        _fail(type_id, "guidelines must be a list")
    for guideline in guidelines:
        if not isinstance(guideline, dict) or not str(guideline.get("name") or "").strip():
            _fail(type_id, "each guideline needs a name")
        if not str(guideline.get("url") or "").startswith("https://"):
            _fail(type_id, "each guideline url must start with https://")


def _check_variant_flow(type_id: str, variant: dict) -> None:
    """A variant's optional ``checklist`` and ``flow_template``, each null or named.

    ``checklist`` must be the id of a guideline file in ``GUIDELINES``.
    ``flow_template`` is checked only against the ``paper-flow*.md.tpl`` name
    pattern: this registry ships to workspaces, which do not hold the package's
    templates, so the repository test
    ``test_every_variant_flow_template_is_a_shipped_template`` checks that the
    named template exists in ``src/papersmith/templates/``.
    """
    _check_checklist(type_id, f"variant {variant['id']!r}: checklist", variant.get("checklist"))
    template = variant.get("flow_template")
    if template is not None and (not isinstance(template, str) or not _FLOW_TEMPLATE_RE.match(template)):
        _fail(type_id, f"variant {variant['id']!r}: flow_template must be null or a paper-flow*.md.tpl "
                       f"template name (got {template!r})")


def _check_checklist(type_id: str, where: str, checklist: Any) -> None:
    """A ``checklist``: null, or the id of a guideline file in ``GUIDELINES``."""
    if checklist is not None and (not isinstance(checklist, str) or not _ID_RE.match(checklist)
                                  or not (GUIDELINES / f"{checklist}.json").is_file()):
        _fail(type_id, f"{where} must be null or the id of a guideline in "
                       f"skills/_core/checklists/guidelines/ (got {checklist!r})")


def checklist_for(item: dict, variant: str | None) -> str | None:
    """The reporting checklist of a type and its agreed variant: the variant's
    ``checklist`` when the type has variants (``None`` while none is agreed or
    the variant names none), else the family's own ``checklist``."""
    variants = item.get("variants") or []
    if variants:
        chosen = next((v for v in variants if v["id"] == variant), None)
        return chosen.get("checklist") if chosen else None
    return item.get("checklist")


def _check_signals(type_id: str, signals: Any, *, allow_empty: bool) -> None:
    if not isinstance(signals, list) or (not signals and not allow_empty) or not all(
            isinstance(s, str) and _SIGNAL_RE.match(s) for s in signals):
        _fail(type_id, "signals must be a non-empty list of lowercase ASCII stems")


def all_signals(item: dict) -> list[str]:
    """The family's own signals followed by every variant's, in order."""
    return list(item["signals"]) + [s for variant in item.get("variants", []) for s in variant["signals"]]


def validate(document: Any) -> list[dict]:
    """The types of a catalogue document, in order, or ``RegistryError``."""
    if not isinstance(document, dict) or not isinstance(document.get("types"), list):
        raise RegistryError("the catalogue must be an object with a `types` list")
    types = [_check(item) for item in document["types"]]
    seen: set[str] = set()
    for item in types:
        for any_id in [item["id"]] + [v["id"] for v in item.get("variants", [])]:
            if any_id in seen:
                _fail(item["id"], f"duplicate id {any_id!r}")
            seen.add(any_id)
    owner: dict[str, str] = {}
    for item in types:
        for signal in all_signals(item):
            if signal in owner and owner[signal] != item["id"]:
                _fail(item["id"], f"signal {signal!r} is also a signal of {owner[signal]!r}")
            owner[signal] = item["id"]
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


__all__ = ["CATALOGUE", "GUIDELINES", "LINES", "MAX_SUMMARY", "RegistryError", "STATUSES", "all_signals", "available", "by_line",
           "checklist_for", "get", "load", "main", "validate"]

if __name__ == "__main__":
    raise SystemExit(main())
