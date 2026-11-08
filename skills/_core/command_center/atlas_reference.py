"""What the SOTA constellation knows about one cited reference.

A panel shows a citation by its pool identifier (``.papersmith/citations.json``
joined to ``sota-pool/candidates.json``). The constellation
(``sota-pool/atlas.json``) draws a system per reference, and every planet names
the reference it came from in ``evidence.origin``, which equals a candidate's
``identifier``, ``source_url`` or ``url``. This module joins the two, after the
citations contract's own normalization, so a click on a citation can centre its
system in the atlas and show its topic, problem, novelty and the rest.
Read-only: it never writes a file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import atlas_manuscript, phase_steps

ATLAS_REL = Path("sota-pool") / "atlas.json"
POOL_REL = Path("sota-pool") / "candidates.json"
#: The slots a card shows, in the order a reader meets them.
SLOTS = ("topic_app", "topic_ai", "problem", "application", "family", "branch", "novelty",
         "contribution", "result", "conclusion")
MAX_TEXT = 600
MAX_BYTES = 16 * 1024 * 1024


def _json(path: Path) -> Any:
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None


def _text(value: Any) -> str:
    return value.strip()[:MAX_TEXT] if isinstance(value, str) else ""


def _record(candidate: dict) -> dict[str, Any]:
    authors = candidate.get("authors")
    return {
        "title": _text(candidate.get("title")),
        "year": candidate.get("year") if isinstance(candidate.get("year"), (int, str)) else "",
        "authors": [_text(a) for a in authors[:20]] if isinstance(authors, list) else _text(authors),
        "venue": _text(candidate.get("venue")),
        "url": _text(candidate.get("url") or candidate.get("source_url")),
    }


def _keys(normalize, *values: Any) -> set[str]:
    return {key for key in (normalize(v) for v in values if isinstance(v, str) and v.strip()) if key}


def _system(system: dict) -> dict[str, Any]:
    planets = [p for p in system.get("planets") or [] if isinstance(p, dict)]
    sun = next((p for p in planets if p.get("slot") == "sun"), planets[0] if planets else {})
    slots: dict[str, list[dict[str, str]]] = {}
    for slot in SLOTS:
        found = [{"label": _text(p.get("label")), "detail": _text(p.get("detail"))}
                 for p in planets if p.get("slot") == slot and _text(p.get("label"))]
        if found:
            slots[slot] = found
    return {"id": _text(system.get("id")), "title": _text(system.get("title")),
            "key": f"{_text(system.get('id'))}.{_text(sun.get('id'))}", "slots": slots}


def reference(root: Path | str, ident: str) -> dict[str, Any]:
    """``{"id", "record", "system"}`` for one cited identifier: its pool record
    (empty when the pool lacks it) and its constellation system with the
    planets' labels by slot (``None`` when the constellation does not draw it)."""
    root = Path(root)
    normalize = phase_steps._citations().normalize
    wanted = normalize(ident)
    candidates = atlas_manuscript._candidate_list(_json(root / POOL_REL))
    record: dict[str, Any] = {}
    for candidate in candidates:
        if wanted and wanted in _keys(normalize, candidate.get("identifier"), candidate.get("source_url"),
                                      candidate.get("url")):
            record = _record(candidate)
            break
    found = None
    atlas = _json(root / ATLAS_REL)
    systems = atlas.get("systems") if isinstance(atlas, dict) else None
    for system in systems if isinstance(systems, list) and wanted else []:
        if not isinstance(system, dict):
            continue
        origins = atlas_manuscript._system_origins(system)
        keys = _keys(normalize, *origins)
        for candidate in atlas_manuscript._system_candidates(origins, candidates):
            keys |= _keys(normalize, candidate.get("identifier"), candidate.get("source_url"), candidate.get("url"))
        if wanted in keys:
            found = _system(system)
            break
    return {"id": _text(ident), "record": record, "system": found}
