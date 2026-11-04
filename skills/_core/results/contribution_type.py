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
reason>}``. This module has no dependencies so every loader can read it by
path.
"""

from __future__ import annotations

from typing import Any

TYPES = ("General", "Theory", "Use-Inspired", "Concept & Feasibility", "Negative Results")
MAX_WHY = 600
KEYS = {"type", "why"}


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
    return found


def normalize(raw: Any) -> dict[str, str] | None:
    """``{"type", "why"}`` when ``raw`` names a known type with a reason, else None.

    Readers (the dashboard) are lenient about extra keys and trim an
    over-long reason; the discussion check is the strict gate."""
    if not isinstance(raw, dict):
        return None
    kind, why = raw.get("type"), raw.get("why")
    if not (isinstance(kind, str) and kind in TYPES and isinstance(why, str) and why.strip()):
        return None
    return {"type": kind, "why": why.strip()[:MAX_WHY]}


__all__ = ["TYPES", "MAX_WHY", "problems", "normalize"]
