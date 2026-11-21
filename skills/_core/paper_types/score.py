"""Deterministic paper-type match score (paper-type-lines S3).

Each catalogue type (``paper_types.json``) lists the words that signal it. The
idea is folded (lowercase, accents removed) and every signal is searched for
from the start of a word (each word of a multi-word signal may inflect); a
signal of four characters or fewer (an acronym such
as ``xrd`` or ``sem``) must also end a word. Where two signals overlap, the
longest wins, so ``numerical model`` counts for the computational type and its
``model`` does not count for applied AI. A type earns 1 per distinct signal in
the idea and :data:`POOL_WEIGHT` per distinct signal in the SOTA pool's titles,
abstracts and families, at most :data:`POOL_CAP` from the pool.

Scores are relative: the leading type scores 100 and the others their share of
it. The leader is suggested only when it leads strictly; ``confidence`` says
how clearly. No model is called; the advisor agent reads this and argues.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from . import registry

POOL_WEIGHT = 0.25
POOL_CAP = 1.0
SHORT_SIGNAL = 4


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(text or ""))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _pattern(signal: str) -> re.Pattern[str]:
    # Every word but the last may inflect ("peliculas delgadas" for "pelicula delgada").
    body = r"[a-z]*[\s-]+".join(re.escape(part) for part in signal.split())
    tail = r"(?![a-z0-9])" if len(signal) <= SHORT_SIGNAL else ""
    return re.compile(r"(?<![a-z0-9])" + body + tail)


def matches(text: str, types: list[dict]) -> dict[str, list[str]]:
    """Distinct signals found per type, longest first where spans overlap."""
    folded = fold(text)
    found = []
    for item in types:
        for signal in item["signals"]:
            for hit in _pattern(signal).finditer(folded):
                found.append((hit.end() - hit.start(), hit.start(), hit.end(), item["id"], signal))
    found.sort(key=lambda f: (-f[0], f[1]))
    taken: list[tuple[int, int]] = []
    out: dict[str, list[str]] = {item["id"]: [] for item in types}
    for _length, start, end, type_id, signal in found:
        if any(start < e and s < end for s, e in taken):
            continue
        taken.append((start, end))
        if signal not in out[type_id]:
            out[type_id].append(signal)
    return out


def score(idea: str, pool_text: str = "", types: list[dict] | None = None) -> dict[str, Any]:
    types = types if types is not None else registry.load()
    in_idea = matches(idea, types)
    in_pool = matches(pool_text, types) if pool_text else {item["id"]: [] for item in types}
    raw = {item["id"]: len(in_idea[item["id"]]) + min(POOL_CAP, POOL_WEIGHT * len(in_pool[item["id"]]))
           for item in types}
    best = max(raw.values()) if raw else 0
    rows = [{
        "type": item["id"], "status": item["status"], "line": item["line"],
        "score": round(100 * raw[item["id"]] / best) if best else 0,
        "raw": raw[item["id"]], "matched": in_idea[item["id"]], "pool_matched": in_pool[item["id"]],
    } for item in types]
    ranked = sorted(raw.values(), reverse=True)
    second = ranked[1] if len(ranked) > 1 else 0
    leader = [item["id"] for item in types if raw[item["id"]] == best]
    suggested = leader[0] if best > 0 and len(leader) == 1 else None
    if best >= 3 and best >= 1.5 * second:
        confidence = "high"
    elif best >= 2 and best > second:
        confidence = "medium"
    else:
        confidence = "low"
    return {"scores": rows, "suggested": suggested, "confidence": confidence}


__all__ = ["POOL_CAP", "POOL_WEIGHT", "fold", "matches", "score"]
