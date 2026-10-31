"""``smith novelty status|approve|iterate|reset`` — Novelty & Findings Gate CLI.

Evaluates whether empirical results support the proposal's novelty claims,
contrasts with SOTA, audits scientific rigor, and commits the gate decision
before advancing to manuscript drafting.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ..errors import UserError
from .exit_codes import SUCCESS


def _get_novelty_gate(root: Path | None = None):
    """Dynamically resolve and import the novelty_gate engine."""
    name = "papersmith_novelty_gate"
    if name in sys.modules:
        return sys.modules[name]

    candidates: list[Path] = []
    if root:
        candidates.append(root / "skills" / "_core" / "results" / "novelty_gate.py")
    try:
        from ..kit import resolve_kit_root
        kit_root = resolve_kit_root()
        candidates.append(kit_root / "skills" / "_core" / "results" / "novelty_gate.py")
    except Exception:
        pass

    # Repo fallback (when running directly from a papersmith-ai clone)
    repo_cand = Path(__file__).resolve().parents[3] / "skills" / "_core" / "results" / "novelty_gate.py"
    candidates.append(repo_cand)

    for script in candidates:
        if script.is_file():
            import importlib.util
            spec = importlib.util.spec_from_file_location(name, script)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                return module

    try:
        from skills._core.results import novelty_gate  # type: ignore
        return novelty_gate
    except ImportError:
        pass

    raise UserError("could not locate novelty_gate module (skills/_core/results/novelty_gate.py)")


def workspace_root(raw: str | None) -> Path:
    root = Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()
    if not (root / ".papersmith").is_dir():
        raise UserError(f"{root} is not a papersmith workspace (no .papersmith/); "
                        "run `smith init` first or pass --workspace")
    return root


def run_status(args) -> int:
    root = workspace_root(args.workspace)
    gate_mod = _get_novelty_gate(root)
    overview = gate_mod.get_novelty_overview(root)
    if getattr(args, "json", False):
        print(json.dumps(overview, indent=2, ensure_ascii=False))
        return SUCCESS

    gate = overview.get("gate", {})
    status = gate.get("status", "pending").upper()
    print(f"=== Novelty & Findings Gate: [{status}] ===")
    if gate.get("decided_at"):
        print(f"Decided at: {gate['decided_at']} by {gate.get('actor', 'operator')}")
    if gate.get("rationale"):
        print(f"Rationale: {gate['rationale']}")
    if gate.get("target_stage"):
        print(f"Target stage: {gate['target_stage']}")

    # Hypotheses summary
    hypotheses = overview.get("hypotheses", [])
    print(f"\nHypotheses evaluated: {len(hypotheses)}")
    for h in hypotheses:
        v = h.get("verdict", "pending").upper()
        print(f"  [{v}] {h.get('id')}: {h.get('statement')}")
        if h.get("test"):
            print(f"      Test: {h.get('test')} | Observed: {h.get('observed')}")

    # Scientific rigor checklist
    rigor = overview.get("rigor_audit", [])
    print(f"\nScientific Rigor Checklist ({sum(1 for r in rigor if r.get('passed'))}/{len(rigor)} passed):")
    for r in rigor:
        mark = "✓" if r.get("passed") else "✗"
        print(f"  [{mark}] {r.get('title')}: {r.get('detail')}")

    print("\nActions available:")
    print("  smith novelty approve [--notes '...']")
    print("  smith novelty iterate --stage {experiments|proposal|plausibility} [--notes '...']")
    print("  smith novelty reset")
    return SUCCESS


def run_approve(args) -> int:
    root = workspace_root(args.workspace)
    gate_mod = _get_novelty_gate(root)
    try:
        record = gate_mod.record_decision(root, "approve", rationale=args.notes)
    except gate_mod.NoveltyRefusal as exc:
        raise UserError(f"could not approve novelty gate: {exc.message}") from exc

    print("Novelty gate APPROVED: empirical evidence supports proposal novelty.")
    print(f"Recorded at: {record['decided_at']}")
    if record.get("rationale"):
        print(f"Rationale: {record['rationale']}")
    print("Next step: proceed to Phase 6 (Manuscript Scaffolding & Writing).")
    return SUCCESS


def run_iterate(args) -> int:
    root = workspace_root(args.workspace)
    gate_mod = _get_novelty_gate(root)
    action = f"iterate_{args.stage}"
    try:
        record = gate_mod.record_decision(root, action, rationale=args.notes)
    except gate_mod.NoveltyRefusal as exc:
        raise UserError(f"could not record iteration: {exc.message}") from exc

    stage_names = {
        "experiments": "Phase 5 (Experiments & PoC)",
        "proposal": "Phase 4 (Proposal Deliberation)",
        "plausibility": "Phase 2 (Plausibility & SOTA)",
    }
    target = stage_names.get(args.stage, args.stage)
    print(f"Novelty gate decision: ITERATE -> returned to {target}.")
    print(f"Recorded at: {record['decided_at']}")
    if record.get("rationale"):
        print(f"Instructions: {record['rationale']}")
    return SUCCESS


def run_reset(args) -> int:
    root = workspace_root(args.workspace)
    gate_mod = _get_novelty_gate(root)
    try:
        record = gate_mod.record_decision(root, "reset", rationale="Gate reset to pending")
    except gate_mod.NoveltyRefusal as exc:
        raise UserError(f"could not reset gate: {exc.message}") from exc

    print("Novelty gate RESET: status is now [PENDING].")
    print(f"Recorded at: {record['decided_at']}")
    return SUCCESS


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "novelty",
        help="novelty assessment and findings gate (hypotheses vs SOTA, reviewer defense, gate decision)",
    )
    cmd_sub = parser.add_subparsers(dest="novelty_subcommand", required=True)

    # status
    p_status = cmd_sub.add_parser("status", help="show novelty assessment overview and gate status")
    p_status.add_argument("--workspace", "-w", help="target workspace root (defaults to cwd)")
    p_status.add_argument("--json", action="store_true", help="output JSON format")
    p_status.set_defaults(handler=run_status)

    # approve
    p_approve = cmd_sub.add_parser("approve", help="approve novelty and unlock manuscript scaffolding")
    p_approve.add_argument("--workspace", "-w", help="target workspace root (defaults to cwd)")
    p_approve.add_argument("--notes", "-n", default="Empirical evidence supports core claims",
                           help="justification / rationale for approval")
    p_approve.set_defaults(handler=run_approve)

    # iterate
    p_iterate = cmd_sub.add_parser("iterate", help="reject novelty or request iteration before manuscript drafting")
    p_iterate.add_argument("--stage", "-s", choices=["experiments", "proposal", "plausibility"],
                           default="experiments", help="target stage to iterate on")
    p_iterate.add_argument("--workspace", "-w", help="target workspace root (defaults to cwd)")
    p_iterate.add_argument("--notes", "-n", default="", help="iteration guidelines and requested remedies")
    p_iterate.set_defaults(handler=run_iterate)

    # reset
    p_reset = cmd_sub.add_parser("reset", help="reset gate status to pending")
    p_reset.add_argument("--workspace", "-w", help="target workspace root (defaults to cwd)")
    p_reset.set_defaults(handler=run_reset)
