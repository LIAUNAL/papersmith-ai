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

# Import the contract engine
try:
    from skills._core.results import novelty_gate
except ImportError:
    # Direct import when skills is under kit or relative
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "_core" / "results"))
    import novelty_gate  # type: ignore


def workspace_root(raw: str | None) -> Path:
    root = Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()
    if not (root / ".papersmith").is_dir():
        raise UserError(f"{root} is not a papersmith workspace (no .papersmith/); "
                        "run `smith init` first or pass --workspace")
    return root


def run_status(args) -> int:
    root = workspace_root(args.workspace)
    overview = novelty_gate.get_novelty_overview(root)
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

    # Rigor summary
    print("\nScientific Rigor & Reviewer Defense Audit:")
    for item in overview.get("rigor_audit", []):
        mark = "✓" if item.get("passed") else "✗"
        print(f"  [{mark}] {item.get('title')}: {item.get('detail')}")

    print("\nActions:")
    print("  Approve: `smith novelty approve [--notes \"...\"]`")
    print("  Iterate: `smith novelty iterate --stage {experiments|proposal|plausibility} [--notes \"...\"]`")
    return SUCCESS


def run_approve(args) -> int:
    root = workspace_root(args.workspace)
    try:
        record = novelty_gate.record_decision(root, "approve", rationale=args.notes)
    except novelty_gate.NoveltyRefusal as exc:
        raise UserError(f"could not approve novelty gate: {exc.message}") from exc

    print("Novelty gate APPROVED: empirical evidence supports proposal novelty.")
    print(f"Recorded at: {record['decided_at']}")
    if record.get("rationale"):
        print(f"Rationale: {record['rationale']}")
    print("Next step: proceed to Phase 6 (Manuscript Scaffolding & Writing).")
    return SUCCESS


def run_iterate(args) -> int:
    root = workspace_root(args.workspace)
    action = f"iterate_{args.stage}"
    try:
        record = novelty_gate.record_decision(root, action, rationale=args.notes)
    except novelty_gate.NoveltyRefusal as exc:
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
    try:
        record = novelty_gate.record_decision(root, "reset", rationale="Gate reset to pending")
    except novelty_gate.NoveltyRefusal as exc:
        raise UserError(f"could not reset gate: {exc.message}") from exc

    print("Novelty gate reset to PENDING.")
    return SUCCESS


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "novelty",
        help="novelty evaluation & gate: assess empirical support and authorize paper writing",
    )
    commands = parser.add_subparsers(dest="novelty_command", required=True)

    status = commands.add_parser("status", help="view consolidated novelty status, hypotheses, and gate")
    status.add_argument("--json", action="store_true", help="output as machine-readable JSON")
    status.add_argument("--workspace", default=None, help="workspace root (default: current directory)")
    status.set_defaults(handler=run_status)

    approve = commands.add_parser("approve", help="approve novelty and authorize manuscript writing")
    approve.add_argument("--notes", default="", help="rationale supporting the approval")
    approve.add_argument("--workspace", default=None, help="workspace root (default: current directory)")
    approve.set_defaults(handler=run_approve)

    iterate = commands.add_parser("iterate", help="record need for further iteration before drafting")
    iterate.add_argument(
        "--stage",
        required=True,
        choices=["experiments", "proposal", "plausibility"],
        help="target stage to iterate on",
    )
    iterate.add_argument("--notes", default="", help="reason or instructions for iteration")
    iterate.add_argument("--workspace", default=None, help="workspace root (default: current directory)")
    iterate.set_defaults(handler=run_iterate)

    reset = commands.add_parser("reset", help="reset novelty gate status to pending")
    reset.add_argument("--workspace", default=None, help="workspace root (default: current directory)")
    reset.set_defaults(handler=run_reset)
