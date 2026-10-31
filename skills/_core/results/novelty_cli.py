#!/usr/bin/env python3
"""CLI over the novelty-gate contract (``novelty_gate.py``).

Usage:
    novelty_cli.py status  [--root <dir>]
    novelty_cli.py approve [--root <dir>] [--notes "..."] [--actor <name>]
    novelty_cli.py iterate [--root <dir>] --stage {experiments,proposal,plausibility} [--notes "..."] [--actor <name>]
    novelty_cli.py reset   [--root <dir>]

Prints JSON on stdout. Refusals emit ``{"ok": false, "error": <CODE>, "message": ...}``
and exit non-zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from . import novelty_gate
except ImportError:
    import novelty_gate  # type: ignore


def _emit(data: dict, code: int = 0) -> int:
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return code


def _refuse(code: str, message: str, exit_code: int = 1) -> int:
    return _emit({"ok": False, "error": code, "message": message}, exit_code)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="novelty_cli.py", description="Novelty & Evidence Gate CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = sub.add_parser("status", help="Get consolidated novelty overview and gate state")
    p_status.add_argument("--root", default=".", help="Workspace root (default: current dir)")

    # approve
    p_approve = sub.add_parser("approve", help="Approve novelty and authorize paper writing")
    p_approve.add_argument("--root", default=".", help="Workspace root")
    p_approve.add_argument("--notes", default="", help="Rationale or justification notes")
    p_approve.add_argument("--actor", default="operator", help="Deciding actor")

    # iterate
    p_iterate = sub.add_parser("iterate", help="Record iteration decision and target stage")
    p_iterate.add_argument("--root", default=".", help="Workspace root")
    p_iterate.add_argument(
        "--stage",
        required=True,
        choices=["experiments", "proposal", "plausibility"],
        help="Stage to iterate on",
    )
    p_iterate.add_argument("--notes", default="", help="Rationale or instructions for iteration")
    p_iterate.add_argument("--actor", default="operator", help="Deciding actor")

    # reset
    p_reset = sub.add_parser("reset", help="Reset gate status to pending")
    p_reset.add_argument("--root", default=".", help="Workspace root")

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    if args.command == "status":
        overview = novelty_gate.get_novelty_overview(root)
        return _emit({"ok": True, **overview})

    if args.command == "approve":
        try:
            record = novelty_gate.record_decision(root, "approve", rationale=args.notes, actor=args.actor)
            return _emit({"ok": True, "action": "approve", "gate": record})
        except novelty_gate.NoveltyRefusal as ref:
            return _refuse(ref.code, ref.message)

    if args.command == "iterate":
        action = f"iterate_{args.stage}"
        try:
            record = novelty_gate.record_decision(root, action, rationale=args.notes, actor=args.actor)
            return _emit({"ok": True, "action": action, "gate": record})
        except novelty_gate.NoveltyRefusal as ref:
            return _refuse(ref.code, ref.message)

    if args.command == "reset":
        try:
            record = novelty_gate.record_decision(root, "reset", rationale="Gate reset to pending", actor="operator")
            return _emit({"ok": True, "action": "reset", "gate": record})
        except novelty_gate.NoveltyRefusal as ref:
            return _refuse(ref.code, ref.message)

    return _refuse("UNKNOWN_COMMAND", f"command {args.command} not recognized")


if __name__ == "__main__":
    sys.exit(main())
