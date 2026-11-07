"""The NeurIPS contribution type a paper-reviewer pass assigns to one phase's ideas.

The `paper-reviewer` agent reads the work the way a NeurIPS 2026 main-track
reviewer would, and field 2 of that form is the contribution type the paper
fits. Two phases record it, each on the artifact the phase already owns:

- the proposal (concept map and mathematics): ``contribution_type`` in
  ``.papersmith/model_spec.json``, classified from the accepted revision's
  hypotheses, mathematics and claimed novelty;
- the findings (novelty and findings): ``contribution_type`` in each
  product's ``Results/discussion.json``, classified from the checked
  hypothesis verdicts and novelty verdict.

The shape is the same in both: ``{"type": <one of TYPES>, "why": <short
reason>, "affinity": {<each of TYPES>: {"score": <0-100>, "why": <short
reason>}}}``. ``affinity`` says how well the work fits each type; the chosen
type holds the highest score. It is optional, so a verdict written before it
existed stays valid. This module has no dependencies so every loader can read
it by path.
"""

from __future__ import annotations

from typing import Any

TYPES = ("General", "Theory", "Use-Inspired", "Concept & Feasibility", "Negative Results")
MAX_WHY = 600
MAX_AFFINITY_WHY = 300
KEYS = {"type", "why", "affinity"}


def problems(raw: Any) -> list[str]:
    """What is wrong with a ``contribution_type`` value, ``[]`` when it is valid."""
    if not isinstance(raw, dict):
        return ["contribution_type: must be an object with type and why"]
    found = []
    kind = raw.get("type")
    if not (isinstance(kind, str) and kind in TYPES):
        found.append(f"contribution_type.type: must be one of {', '.join(TYPES)}")
    why = raw.get("why")
    if not (isinstance(why, str) and why.strip()):
        found.append("contribution_type.why: required and non-empty")
    elif len(why) > MAX_WHY:
        found.append(f"contribution_type.why: longer than {MAX_WHY} characters")
    for key in sorted(set(raw) - KEYS):
        found.append(f"contribution_type: unknown key {key[:60]!r}")
    if "affinity" in raw:
        found += _affinity_problems(raw["affinity"], kind)
    return found


def _score(entry: Any) -> int | None:
    score = entry.get("score") if isinstance(entry, dict) else None
    return score if isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 100 else None


def _affinity_problems(affinity: Any, kind: Any) -> list[str]:
    if not isinstance(affinity, dict):
        return ["contribution_type.affinity: must be an object keyed by type"]
    found = []
    missing = [name for name in TYPES if name not in affinity]
    if missing:
        found.append(f"contribution_type.affinity: must score every type; missing {', '.join(missing)}")
    for key in sorted(set(affinity) - set(TYPES)):
        found.append(f"contribution_type.affinity: unknown type {key[:60]!r}")
    for name in TYPES:
        entry = affinity.get(name)
        if name not in affinity:
            continue
        if _score(entry) is None:
            found.append(f"contribution_type.affinity.{name}.score: must be an integer from 0 to 100")
        why = entry.get("why") if isinstance(entry, dict) else None
        if not (isinstance(why, str) and why.strip()) or len(why) > MAX_AFFINITY_WHY:
            found.append(f"contribution_type.affinity.{name}.why: required, at most {MAX_AFFINITY_WHY} characters")
    scores = [_score(affinity.get(name)) for name in TYPES]
    if kind in TYPES and None not in scores and _score(affinity[kind]) < max(scores):
        found.append(f"contribution_type.affinity: the chosen type {kind} must hold the highest score")
    return found


def normalize(raw: Any) -> dict[str, Any] | None:
    """``{"type", "why"}`` when ``raw`` names a known type with a reason, else None,
    plus ``affinity`` when it is valid.

    Readers (the dashboard) are lenient about extra keys and trim an
    over-long reason, and drop a broken affinity rather than the type; the
    discussion check is the strict gate."""
    if not isinstance(raw, dict):
        return None
    kind, why = raw.get("type"), raw.get("why")
    if not (isinstance(kind, str) and kind in TYPES and isinstance(why, str) and why.strip()):
        return None
    found: dict[str, Any] = {"type": kind, "why": why.strip()[:MAX_WHY]}
    if "affinity" in raw and not _affinity_problems(raw["affinity"], kind):
        found["affinity"] = {name: {"score": raw["affinity"][name]["score"],
                                    "why": raw["affinity"][name]["why"].strip()} for name in TYPES}
    return found


__all__ = ["TYPES", "MAX_WHY", "MAX_AFFINITY_WHY", "problems", "normalize"]
