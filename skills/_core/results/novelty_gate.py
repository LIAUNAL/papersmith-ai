"""The novelty-gate contract: `.papersmith/novelty_gate.json` (schema 1).

Between completing experiments (Phase 5) and beginning manuscript scaffolding
and drafting (Phase 6), the operator evaluates whether empirical evidence
actually supports the proposal's novelty claims, contrasts findings with SOTA,
conducts an adversarial reviewer audit, and commits a gate decision:

    - "approved": empirical evidence supports the core novelty; proceed to paper writing.
    - "iterating_experiments": results inconclusive or ablations missing; return to experiments.
    - "iterating_proposal": mathematical formulation or claims need revision; return to proposal.
    - "iterating_plausibility": literature landscape or core framing shifted; return to plausibility.

Before the full experiments start, the operator also verifies the proof of
concept: its results and the hypotheses it contrasted. That PoC-stage decision
is the ``poc`` sub-record beside the top-level (full-stage) decision,
``{"status": "approved" | "iterating" | "pending", "decided_at", "actor",
"rationale"}``; approving it refuses ``POC_DISCUSSION_INCOMPLETE`` unless at
least one proof-of-concept product (a folder with ``AGREED.md`` and no
``Experimental_AGREED.md``) has a ``complete`` ``Results/discussion.json``
(``discussion.py``). The dashboard's G-EXP-POC gate passes on that approval and
the full experiments unlock after it. A file without the sub-record reads as a
pending PoC decision, and each stage's write keeps the other's record.

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

#: The two decision stages: the PoC verification and the full-stage novelty gate.
STAGES = ("poc", "full")
POC_STATUSES = ("pending", "approved", "iterating")
#: PoC-stage actions; the full-stage ``iterate_*`` names read as ``iterate``.
POC_ACTIONS = {"approve": "approved", "iterate": "iterating", "reset": "pending",
               "iterate_experiments": "iterating", "iterate_proposal": "iterating",
               "iterate_plausibility": "iterating"}
#: Where a PoC decision sends the work: an iteration returns to the stage the
#: operator named (bare `iterate` stays in the experiments), an approval opens
#: the full experiments.
POC_TARGETS = {"approve": "full_experiments", "iterate": "poc_experiments",
               "iterate_experiments": "poc_experiments", "iterate_proposal": "proposal",
               "iterate_plausibility": "plausibility", "reset": None}

MAX_RATIONALE_LENGTH = 4000
MAX_HISTORY_ENTRIES = 50
MAX_LIMITATIONS = 50
MAX_LIMITATION_LENGTH = 600
MAX_HYPOTHESES_PER_PRODUCT = 100


class NoveltyRefusal(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def gate_path(root: Path) -> Path:
    return root / ".papersmith" / GATE_FILENAME


def default_poc() -> dict[str, Any]:
    return {"status": "pending", "decided_at": None, "actor": None, "rationale": "",
            "target_stage": None}


def _read_poc(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return default_poc()
    status = raw.get("status") if raw.get("status") in POC_STATUSES else "pending"
    return {"status": status, "decided_at": raw.get("decided_at"), "actor": raw.get("actor"),
            "rationale": str(raw.get("rationale") or "")[:MAX_RATIONALE_LENGTH],
            "target_stage": raw.get("target_stage") if raw.get("target_stage") in POC_TARGETS.values() else None}


def default_gate() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "pending",
        "decided_at": None,
        "actor": None,
        "rationale": "",
        "target_stage": None,
        "history": [],
        "poc": default_poc(),
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
            "poc": _read_poc(data.get("poc")),
        }
    except (OSError, ValueError):
        return default_gate()


def _discussion_module():
    """The results-discussion contract (``discussion.py``), loaded by path: the
    one owner of what a ``complete`` ``Results/discussion.json`` is."""
    import importlib.util
    import sys

    name = "papersmith_results_discussion"
    if name not in sys.modules:
        path = Path(__file__).resolve().parent / "discussion.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return sys.modules[name]


def _products(root: Path) -> list[Path]:
    folder = Path(root) / "implementations"
    out: list[Path] = []
    try:
        for repo in sorted(folder.iterdir()) if folder.is_dir() else []:
            if repo.is_dir() and not repo.name.startswith("."):
                out.extend(p for p in sorted(repo.iterdir()) if p.is_dir() and not p.name.startswith("."))
    except OSError:
        pass
    return out


def complete_poc_discussions(root: Path) -> int:
    """How many proof-of-concept products (``AGREED.md``, no
    ``Experimental_AGREED.md``) close with a ``complete`` discussion; never raises."""
    count = 0
    for product in _products(root):
        if not (product / "AGREED.md").is_file() or (product / "Experimental_AGREED.md").is_file():
            continue
        try:
            if _discussion_module().load_and_check(product).get("status") == "complete":
                count += 1
        except Exception:  # noqa: BLE001 - an unreadable discussion is not complete
            continue
    return count


def _write(root: Path, record: dict[str, Any]) -> None:
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


def judge_state(root: Path) -> dict[str, dict[str, Any]]:
    """Per stage, how many products close with a ``complete`` discussion and
    which of them still lack the paper-reviewer's valid ``contribution_type``
    (the NeurIPS judge); never raises. A malformed type alone makes a discussion
    fail its check, so a discussion is judged here without that field: one that
    is complete apart from its type owes the judge, a draft owes nothing."""
    state: dict[str, dict[str, Any]] = {stage: {"complete": 0, "owed": []} for stage in STAGES}
    for product in _products(root):
        try:
            result = _discussion_module().load_and_check(product)
            data = result["data"]
            if not isinstance(data, dict):
                continue
            malformed = ("contribution_type" in data
                         and bool(_contribution_type().problems(data["contribution_type"])))
            if malformed:
                bare = {key: value for key, value in data.items() if key != "contribution_type"}
                result = _discussion_module().check_discussion(product, bare)
            if result["status"] != "complete":
                continue
            kind = None if malformed else _contribution_type().normalize(data.get("contribution_type"))
        except Exception:  # noqa: BLE001 - an unreadable discussion is not complete
            continue
        stage = state["full" if (product / "Experimental_AGREED.md").is_file() else "poc"]
        stage["complete"] += 1
        if not kind:
            stage["owed"].append(product.name)
    return state


def _require_judge(root: Path, stage: str) -> None:
    """Refuse an approval while a product of ``stage`` still owes the NeurIPS judge."""
    owed = judge_state(root)[stage]["owed"]
    if owed:
        raise NoveltyRefusal(
            "NEURIPS_JUDGE_OWED",
            f"run the NeurIPS judge first: {', '.join(owed)} has a complete discussion and no "
            "contribution_type; launch it from the Novelty & Findings tab, or hand the discussion "
            "to the paper-reviewer agent in its findings mode",
        )


def _record_poc(root: Path, action: str, rationale: str, actor: str) -> dict[str, Any]:
    if action not in POC_ACTIONS:
        raise NoveltyRefusal(
            "INVALID_ACTION",
            f"a PoC-stage action must be one of {sorted(POC_ACTIONS)}, got {action!r}",
        )
    status = POC_ACTIONS[action]
    if status == "approved" and complete_poc_discussions(root) == 0:
        raise NoveltyRefusal(
            "POC_DISCUSSION_INCOMPLETE",
            "no proof of concept has a complete Results/discussion.json yet; verify its results and "
            "hypotheses with `python skills/_core/results/discussion_cli.py check --product <path>` first",
        )
    if status == "approved":
        _require_judge(root, "poc")
    record = read_gate(root)
    record["poc"] = {
        "status": status,
        "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "actor": actor,
        "rationale": str(rationale or "").strip()[:MAX_RATIONALE_LENGTH],
        "target_stage": POC_TARGETS[action],
    }
    _write(root, record)
    return record


def record_decision(
    root: Path,
    action: str,
    rationale: str = "",
    actor: str = "operator",
    stage: str = "full",
) -> dict[str, Any]:
    """Record a novelty gate decision atomically. Refuses invalid actions.

    ``stage="full"`` (the default) is the novelty gate before writing;
    ``stage="poc"`` records the proof-of-concept verification in the ``poc``
    sub-record and refuses an approval without a complete PoC discussion. An
    approval of either stage refuses while one of its products owes the NeurIPS
    judge."""
    if stage not in STAGES:
        raise NoveltyRefusal("INVALID_STAGE", f"stage must be one of {list(STAGES)}, got {stage!r}")
    if stage == "poc":
        return _record_poc(root, action, rationale, actor)
    if action not in VALID_ACTIONS:
        raise NoveltyRefusal(
            "INVALID_ACTION",
            f"action must be one of {sorted(VALID_ACTIONS.keys())}, got {action!r}",
        )

    if action == "approve":
        _require_judge(root, "full")

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
        "poc": current.get("poc") or default_poc(),
    }
    _write(root, record)
    return record


def _contribution_type():
    """The shared contribution-type contract (``contribution_type.py``), loaded by path."""
    import importlib.util
    import sys

    name = "papersmith_contribution_type"
    if name not in sys.modules:
        path = Path(__file__).resolve().parent / "contribution_type.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


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
    limitations: list[dict[str, Any]] = []
    normalize_type = _contribution_type().normalize

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
                                "contribution_type": normalize_type(disc_data.get("contribution_type")),
                            }
                            discussions.append(disc_summary)

                            # Limitations the discussion records, bounded
                            raw_limits = disc_data.get("limitations")
                            for item in raw_limits if isinstance(raw_limits, list) else []:
                                text = item.strip() if isinstance(item, str) else ""
                                if text and len(limitations) < MAX_LIMITATIONS:
                                    limitations.append({
                                        "product": prod_name,
                                        "stage": stage,
                                        "text": text[:MAX_LIMITATION_LENGTH],
                                    })

                            # Hypotheses
                            raw_hyps = disc_data.get("hypotheses")
                            for h in (raw_hyps if isinstance(raw_hyps, list) else [])[:MAX_HYPOTHESES_PER_PRODUCT]:
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
            for k in ("leak", "group", "subject", "held-out", "holdout", "disjoint"))
        for h in hypotheses
    )
    has_statistical_testing = any(bool(h.get("test")) for h in hypotheses)
    has_supported_hypotheses = any(h.get("verdict") in ("supported", "partially_supported") for h in hypotheses)
    all_hypotheses_decided = bool(hypotheses) and all(h.get("verdict") not in ("pending", "inconclusive") for h in hypotheses)

    rigor_audit = [
        {
            "id": "leakage_free",
            "title": "Leakage-free split at the unit of replication",
            "passed": has_leakage_free_validation,
            "detail": "The discussion hypotheses describe a group-wise or held-out evaluation." if has_leakage_free_validation else "Recommend verifying that no unit of replication is shared between training and evaluation splits.",
        },
        {
            "id": "statistical_rigor",
            "title": "Statistical significance testing (Significance Testing)",
            "passed": has_statistical_testing,
            "detail": "The hypotheses name the statistical test that decides them." if has_statistical_testing else "Formal statistical significance tests should be cited for all hypotheses.",
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

    # 4. The paper-reviewer's NeurIPS contribution type for the findings:
    # the full stage's over the pilot's, the first product in order otherwise.
    typed = [d for d in discussions if d["contribution_type"]]
    typed.sort(key=lambda d: d["stage"] != "full")
    contribution_type = ({**typed[0]["contribution_type"], "product": typed[0]["product"],
                          "stage": typed[0]["stage"]} if typed else None)

    return {
        "gate": gate,
        "contribution_type": contribution_type,
        "judge": judge_state(root),
        "discussions": discussions,
        "hypotheses": hypotheses,
        "novelty_claims": novelty_claims,
        "limitations": limitations,
        "sota": {
            "candidates_count": candidates_count,
            "families": sota_families,
            "atlas_exists": atlas_file.is_file(),
        },
        "rigor_audit": rigor_audit,
        "ready_to_approve": bool(discussions) and has_supported_hypotheses,
        "poc_verification": {
            "discussed": complete_poc_discussions(root),
            "decision": gate.get("poc") or default_poc(),
        },
    }
