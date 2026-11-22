"""The plausibility acceptance and the paper-type decision, on disk.

* ``.papersmith/plausibility.json``: the idea the operator accepted at the end
  of plausibility, who accepted it and when, the hash of the SOTA pool it was
  judged against, and the top references carried to ingestion.
* ``.papersmith/paper_type.json``: the deterministic scores of every catalogue
  type for that idea, the suggested type and its confidence, and, once the
  operator agrees one (``smith kind set``, paper-type-lines S5), the agreed
  type. Rescoring keeps the agreed type and flags it ``agreed_stale`` when the
  idea it was agreed for has changed.

Nothing in the applied-AI flow reads these files: a workspace without them is
``experimental``, as before. Writes are atomic (temporary file, then replace).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import registry
from . import score as scoring

PLAUSIBILITY = Path(".papersmith") / "plausibility.json"
PAPER_TYPE = Path(".papersmith") / "paper_type.json"
POOL = Path("sota-pool") / "candidates.json"
CONFIG = Path(".papersmith") / "config.json"
_AGREED_KEYS = ("agreed", "agreed_variant", "agreed_by", "agreed_at", "agreed_idea_sha256", "agreed_rationale")


class DecisionError(ValueError):
    """A refused write: no operator, no idea, or an unreadable record."""

    code = "RECORD_UNREADABLE"


class AgreeError(DecisionError):
    """An agreement the catalogue or the record cannot hold; ``code`` names it."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise DecisionError(f"{path.name} cannot be read: {error}") from error
    if not isinstance(data, dict):
        # Never overwrite a record we cannot read as ours: the operator decides.
        raise DecisionError(f"{path.name} does not hold a JSON object; move it aside and run again")
    return data


def pool_sha256(root: Path) -> str | None:
    try:
        return _sha((Path(root) / POOL).read_bytes())
    except OSError:
        return None


def pool_text(root: Path) -> str:
    """The SOTA pool's titles, abstracts and families as one text, or ``""``."""
    try:
        data = json.loads((Path(root) / POOL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    listed = data.get("candidates") if isinstance(data, dict) else data
    parts = []
    for item in listed if isinstance(listed, list) else []:
        if isinstance(item, dict):
            parts.extend(str(item.get(key) or "") for key in ("title", "abstract", "family"))
    return "\n".join(part for part in parts if part)


def read(root: Path) -> dict[str, Any]:
    root = Path(root)
    return {"plausibility": _read(root / PLAUSIBILITY), "paper_type": _read(root / PAPER_TYPE)}


def record_acceptance(root: Path, idea: str, *, by: str, top5: list[str] | None = None) -> dict:
    idea = str(idea or "").strip()
    by = str(by or "").strip()
    if not idea:
        raise DecisionError("the accepted idea is empty")
    if not by:
        raise DecisionError("name the operator who accepted the plausibility report (--by)")
    record = {"idea": idea, "idea_sha256": _sha(idea.encode("utf-8")), "accepted_by": by,
              "accepted_at": _now(), "pool_sha256": pool_sha256(root),
              "top5": [str(item) for item in top5 or []]}
    _write(Path(root) / PLAUSIBILITY, record)
    return record


def compute(root: Path, idea: str) -> dict:
    """The scores for ``idea`` against this workspace's pool, without writing."""
    idea = str(idea or "").strip()
    if not idea:
        raise DecisionError("there is no idea to score")
    result = scoring.score(idea, pool_text(root))
    return {**result, "idea_sha256": _sha(idea.encode("utf-8")), "pool_sha256": pool_sha256(root),
            "computed_at": _now()}


def record_scores(root: Path, idea: str) -> dict:
    record = compute(root, idea)
    previous = _read(Path(root) / PAPER_TYPE) or {}
    for key in _AGREED_KEYS:
        record[key] = previous.get(key)
    record["agreed_stale"] = bool(record["agreed"]) and record["agreed_idea_sha256"] != record["idea_sha256"]
    _write(Path(root) / PAPER_TYPE, record)
    return record


def current_line(root: Path) -> str:
    """The workspace's line (``paper_kind``), ``experimental`` when unset."""
    try:
        config = json.loads((Path(root) / CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "experimental"
    kind = config.get("paper_kind") if isinstance(config, dict) else None
    return kind if isinstance(kind, str) and kind else "experimental"


def agree(root: Path, type_id: str, *, by: str, variant: str | None = None, rationale: str = "") -> dict:
    """Record the type the operator agreed for the scored idea.

    ``layout`` says what the workspace must do next: ``current`` (its line is
    already this type's), ``switch:<line>`` (``smith kind set`` moves it), or
    ``planned`` (smith has no flow for this type yet; the workspace keeps its
    line until one exists)."""
    by = str(by or "").strip()
    if not by:
        raise AgreeError("OPERATOR_ABSENT", "name the operator who agreed the type with --by")
    record = _read(Path(root) / PAPER_TYPE)
    if record is None:
        raise AgreeError("SCORES_ABSENT", "score the idea first (paper_type_cli.py accept or score)")
    accepted = _read(Path(root) / PLAUSIBILITY)
    if accepted and accepted.get("idea_sha256") != record.get("idea_sha256"):
        raise AgreeError("SCORES_STALE", "the scores belong to another idea than the accepted one; "
                                         "run paper_type_cli.py score --root . first")
    try:
        item = registry.get(type_id)
    except registry.RegistryError as error:
        raise AgreeError("TYPE_UNKNOWN", str(error)) from error
    if variant and variant not in [v["id"] for v in item.get("variants", [])]:
        raise AgreeError("VARIANT_UNKNOWN", f"{type_id!r} has no variant {variant!r}")
    record.update({"agreed": type_id, "agreed_variant": variant or None, "agreed_by": by, "agreed_at": _now(),
                   "agreed_idea_sha256": record.get("idea_sha256"), "agreed_rationale": str(rationale or "").strip(),
                   "agreed_stale": False})
    _write(Path(root) / PAPER_TYPE, record)
    line = item["line"]
    layout = "planned" if line is None else ("current" if line == current_line(root) else f"switch:{line}")
    return {**record, "line": line, "layout": layout}


__all__ = ["AgreeError", "DecisionError", "agree", "current_line", "PAPER_TYPE", "PLAUSIBILITY", "compute", "pool_sha256", "pool_text", "read",
           "record_acceptance", "record_scores"]
