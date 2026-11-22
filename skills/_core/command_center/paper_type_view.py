"""The paper type in the dashboard (paper-type-lines S4).

* ``view(root)``: what the Paper type panel draws -- the catalogue, the accepted
  idea (``.papersmith/plausibility.json``), the scores and any agreement
  (``.papersmith/paper_type.json``), the workspace line and the sub-step below.
* ``subphase(root)``: Phase 2's advisory sub-step 2.5 "Paper Type". It passes
  once the operator agreed a type for the current idea and locks nothing: the
  applied-AI flow goes on with or without it.
* ``rescore`` and ``agree`` are the panel's two writes, each an explicit
  operator click.

Labels are English; ``static/i18n/server-es.json`` holds their Spanish.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..paper_types import decision, registry

SUB_ID = "2.5"
SUB_NAME = "Paper Type"


def _records(root: Path) -> tuple[dict | None, dict | None, str | None]:
    try:
        records = decision.read(root)
    except decision.DecisionError:
        return None, None, "The paper-type record cannot be read"
    return records["plausibility"], records["paper_type"], None


def subphase(root: Path) -> dict[str, str]:
    accepted, record, error = _records(Path(root))
    status, detail = "PENDING", error
    if error is None:
        if not accepted:
            detail = "No accepted idea yet: accept the plausibility report first"
        elif record and record.get("agreed") and not record.get("agreed_stale"):
            status, detail = "PASS", f"Agreed paper type: {record['agreed']}"
        elif record and record.get("agreed"):
            detail = "The idea changed after the paper type was agreed; agree it again"
        elif record and record.get("suggested"):
            detail = f"Suggested paper type: {record['suggested']}, awaiting the operator's agreement"
        else:
            detail = "No clear paper type yet: discuss it with the agent"
    return {"id": SUB_ID, "name": SUB_NAME, "status": status, "detail": detail}


def view(root: Path) -> dict[str, Any]:
    root = Path(root)
    accepted, record, error = _records(root)
    try:
        catalogue = registry.load()
        catalogue_error = None
    except registry.RegistryError as exc:
        catalogue, catalogue_error = [], str(exc)
    return {"catalogue": catalogue, "plausibility": accepted, "decision": record,
            "line": decision.current_line(root), "subphase": subphase(root),
            "error": error or catalogue_error}


def rescore(root: Path) -> dict[str, Any]:
    """Score the accepted idea again (the pool may have changed)."""
    accepted, _record, error = _records(Path(root))
    if error:
        return {"ok": False, "code": "RECORD_UNREADABLE", "error": error}
    if not accepted or not str(accepted.get("idea") or "").strip():
        return {"ok": False, "code": "IDEA_ABSENT", "error": "accept the plausibility report first"}
    return {"ok": True, "decision": decision.record_scores(Path(root), accepted["idea"])}


def agree(root: Path, payload: Any) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    result = decision.agree(Path(root), str(payload.get("type") or ""), by=str(payload.get("by") or ""),
                            variant=(str(payload["variant"]) if payload.get("variant") else None),
                            rationale=str(payload.get("rationale") or ""))
    return {"ok": True, **result}


__all__ = ["SUB_ID", "SUB_NAME", "agree", "rescore", "subphase", "view"]
