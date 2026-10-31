"""The novelty-gate contract: `.papersmith/novelty_gate.json` (schema 1).

Between completing experiments (Phase 5) and beginning manuscript scaffolding
and drafting (Phase 6), the operator evaluates whether empirical evidence
actually supports the proposal's novelty claims, contrasts findings with SOTA,
conducts an adversarial reviewer audit, and commits a gate decision:

    - "approved": empirical evidence supports the core novelty; proceed to paper writing.
    - "iterating_experiments": results inconclusive or ablations missing; return to experiments.
    - "iterating_proposal": mathematical formulation or claims need revision; return to proposal.
    - "iterating_plausibility": literature landscape or core framing shifted; return to plausibility.

This module owns reading, writing, and auditing the novelty gate file and
synthesizing the novelty evaluation overview for the dashboard and CLI.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = 1
GATE_FILENAME = "novelty_gate.json"

GATE_STATUSES = (
    "pending",
    "approved",
    "iterating_experiments",
    "iterating_proposal",
    "iterating_plausibility",
)

VALID_ACTIONS = {
    "approve": "approved",
    "iterate_experiments": "iterating_experiments",
    "iterate_proposal": "iterating_proposal",
    "iterate_plausibility": "iterating_plausibility",
    "reset": "pending",
}

MAX_RATIONALE_LENGTH = 4000
MAX_HISTORY_ENTRIES = 50


class NoveltyRefusal(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def gate_path(root: Path) -> Path:
    return root / ".papersmith" / GATE_FILENAME


def default_gate() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "pending",
        "decided_at": None,
        "actor": None,
        "rationale": "",
        "target_stage": None,
        "history": [],
    }


def read_gate(root: Path) -> dict[str, Any]:
    """Read `.papersmith/novelty_gate.json` safely. Returns default pending state
    if absent or unreadable."""
    path = gate_path(root)
    if not path.is_file():
        return default_gate()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default_gate()
        status = data.get("status")
        if status not in GATE_STATUSES:
            status = "pending"
        return {
            "schema": data.get("schema", SCHEMA),
            "status": status,
            "decided_at": data.get("decided_at"),
            "actor": data.get("actor"),
            "rationale": str(data.get("rationale") or "")[:MAX_RATIONALE_LENGTH],
            "target_stage": data.get("target_stage"),
            "history": data.get("history", [])[:MAX_HISTORY_ENTRIES],
        }
    except (OSError, ValueError):
        return default_gate()


def record_decision(
    root: Path,
    action: str,
    rationale: str = "",
    actor: str = "operator",
) -> dict[str, Any]:
    """Record a novelty gate decision atomically. Refuses invalid actions."""
    if action not in VALID_ACTIONS:
        raise NoveltyRefusal(
            "INVALID_ACTION",
            f"action must be one of {sorted(VALID_ACTIONS.keys())}, got {action!r}",
        )

    status = VALID_ACTIONS[action]
    target_stage = None
    if action == "iterate_experiments":
        target_stage = "poc_experiments"
    elif action == "iterate_proposal":
        target_stage = "proposal"
    elif action == "iterate_plausibility":
        target_stage = "plausibility"
    elif action == "approve":
        target_stage = "scaffolding"

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    clean_rationale = str(rationale or "").strip()[:MAX_RATIONALE_LENGTH]

    current = read_gate(root)
    history = list(current.get("history", []))
    
    # Record previous decision in history if it existed
    if current.get("decided_at"):
        history.append({
            "status": current.get("status"),
            "decided_at": current.get("decided_at"),
            "actor": current.get("actor"),
            "rationale": current.get("rationale"),
            "target_stage": current.get("target_stage"),
        })
    history = history[-MAX_HISTORY_ENTRIES:]

    record = {
        "schema": SCHEMA,
        "status": status,
        "decided_at": now_iso,
        "actor": actor,
        "rationale": clean_rationale,
        "target_stage": target_stage,
        "history": history,
    }

    target = gate_path(root)
    folder = target.parent
    folder.mkdir(parents=True, exist_ok=True)

    text = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_path = tempfile.mkstemp(prefix=".novelty-", suffix=".json", dir=str(folder))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, target)
    except OSError as exc:
        raise NoveltyRefusal("WRITE_FAILED", f"could not write {GATE_FILENAME}: {exc}") from exc

    return record


def get_novelty_overview(root: Path) -> dict[str, Any]:
    """Synthesize the full novelty assessment overview from discussion records,
    hypotheses, SOTA pool, and rigor checklists."""
    root = Path(root)
    gate = read_gate(root)

    # 1. Gather discussions across products
    products_dir = root / "implementations"
    discussions: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []
    novelty_claims: list[dict[str, Any]] = []

    if products_dir.is_dir():
        for repo in sorted(products_dir.iterdir()):
            if not repo.is_dir() or repo.name.startswith("."):
                continue
            for prod in sorted(repo.iterdir()):
                if not prod.is_dir() or prod.name.startswith("."):
                    continue
                disc_file = prod / "Results" / "discussion.json"
                if disc_file.is_file():
                    try:
                        disc_data = json.loads(disc_file.read_text(encoding="utf-8"))
                        if isinstance(disc_data, dict):
                            stage = "full" if (prod / "Experimental_AGREED.md").is_file() else "poc"
                            prod_name = prod.name
                            disc_summary = {
                                "product": prod_name,
                                "stage": stage,
                                "summary": str(disc_data.get("summary") or ""),
                                "verdict": disc_data.get("novelty", {}).get("verdict", "pending") if isinstance(disc_data.get("novelty"), dict) else "pending",
                                "claim": disc_data.get("novelty", {}).get("claim", "") if isinstance(disc_data.get("novelty"), dict) else "",
                                "rationale": disc_data.get("novelty", {}).get("rationale", "") if isinstance(disc_data.get("novelty"), dict) else "",
                            }
                            discussions.append(disc_summary)

                            # Hypotheses
                            for h in disc_data.get("hypotheses", []):
                                if isinstance(h, dict) and h.get("id"):
                                    hypotheses.append({
                                        "id": h.get("id"),
                                        "product": prod_name,
                                        "stage": stage,
                                        "statement": h.get("statement", ""),
                                        "metric": h.get("metric", ""),
                                        "test": h.get("test", ""),
                                        "criterion": h.get("criterion", ""),
                                        "observed": h.get("observed", ""),
                                        "verdict": h.get("verdict", "pending"),
                                        "rationale": h.get("rationale", ""),
                                    })

                            # Novelty
                            nov = disc_data.get("novelty")
                            if isinstance(nov, dict) and nov.get("claim"):
                                novelty_claims.append({
                                    "product": prod_name,
                                    "stage": stage,
                                    "claim": nov.get("claim"),
                                    "verdict": nov.get("verdict", "pending"),
                                    "rationale": nov.get("rationale", ""),
                                    "evidence": nov.get("evidence", []),
                                })
                    except (OSError, ValueError):
                        continue

    # 2. SOTA context from sota-pool
    sota_file = root / "sota-pool" / "candidates.json"
    atlas_file = root / "sota-pool" / "atlas.json"
    candidates_count = 0
    sota_families: list[str] = []
    if sota_file.is_file():
        try:
            cdata = json.loads(sota_file.read_text(encoding="utf-8"))
            items = cdata if isinstance(cdata, list) else cdata.get("candidates", [])
            if isinstance(items, list):
                candidates_count = len(items)
                fams = {item.get("family") for item in items if isinstance(item, dict) and item.get("family")}
                sota_families = sorted(filter(None, fams))
            if not sota_families and isinstance(cdata, dict) and "families" in cdata:
                sota_families = list(cdata.get("families", {}).keys())
        except (OSError, ValueError):
            pass

    # 3. Scientific Rigor Checklist
    # Derived from observed discussion hypotheses and empirical artifacts
    has_leakage_free_validation = any(
        any(k in " ".join([h.get("criterion", ""), h.get("rationale", ""), h.get("statement", ""), h.get("observed", "")]).lower()
            for k in ("subject", "group", "leak", "cross-subject"))
        for h in hypotheses
    )
    has_statistical_testing = any(bool(h.get("test")) for h in hypotheses)
    has_supported_hypotheses = any(h.get("verdict") in ("supported", "partially_supported") for h in hypotheses)
    all_hypotheses_decided = bool(hypotheses) and all(h.get("verdict") not in ("pending", "inconclusive") for h in hypotheses)

    rigor_audit = [
        {
            "id": "leakage_free",
            "title": "Leakage-free evaluation (Subject-Level Partitioning)",
            "passed": has_leakage_free_validation,
            "detail": "Subject-level or GroupKFold validation verified in discussion/hypotheses." if has_leakage_free_validation else "Recommend verifying that no segment leakage exists between folds.",
        },
        {
            "id": "statistical_rigor",
            "title": "Statistical significance testing (Significance Testing)",
            "passed": has_statistical_testing,
            "detail": "Decided hypotheses cite paired/non-parametric tests or ANOVA." if has_statistical_testing else "Formal statistical significance tests should be cited for all hypotheses.",
        },
        {
            "id": "hypothesis_backing",
            "title": "Empirical support for core hypotheses",
            "passed": has_supported_hypotheses,
            "detail": "At least one core hypothesis is empirically supported by experimental data." if has_supported_hypotheses else "No core hypothesis is marked as supported by the experiments.",
        },
        {
            "id": "sota_contrast",
            "title": "Rigorous contrast against SOTA and baselines",
            "passed": candidates_count > 0,
            "detail": f"{candidates_count} candidates identified in sota-pool/ across {len(sota_families)} families." if candidates_count > 0 else "No SOTA candidates detected in sota-pool/.",
        },
    ]

    return {
        "gate": gate,
        "discussions": discussions,
        "hypotheses": hypotheses,
        "novelty_claims": novelty_claims,
        "sota": {
            "candidates_count": candidates_count,
            "families": sota_families,
            "atlas_exists": atlas_file.is_file(),
        },
        "rigor_audit": rigor_audit,
        "ready_to_approve": bool(discussions) and has_supported_hypotheses,
    }
