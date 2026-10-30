#!/usr/bin/env python3
"""CLI over the results-discussion contract (``discussion.py`` in this folder).

    discussion_cli.py scaffold --product implementations/<repo>/<Name>
    discussion_cli.py check    --product implementations/<repo>/<Name>
    discussion_cli.py status   --product implementations/<repo>/<Name>

Each verb prints exactly one JSON object on stdout. A refusal prints
``{"ok": false, "error": <CODE>, "message": ...}`` and exits non-zero (1; usage
errors exit 2) with nothing written. The only file this tool ever writes is
``<product>/Results/discussion.json``, and only when ``scaffold`` succeeds.

Refusal codes: ``USAGE``, ``PRODUCT_ABSENT``, ``APPROVAL_ABSENT``,
``DISCUSSION_EXISTS``, ``DISCUSSION_ABSENT``, ``RESULTS_UNSAFE``,
``WRITE_FAILED``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


def _load_contract():
    path = Path(__file__).resolve().parent / "discussion.py"
    spec = importlib.util.spec_from_file_location("papersmith_results_discussion", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


contract = _load_contract()


class _Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # argparse would print to stderr and exit; the contract is JSON on stdout.
        raise _Usage(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="discussion_cli.py", description=__doc__.split("\n\n")[0])
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="{scaffold,check,status}")
    for verb, text in (("scaffold", "write a pending Results/discussion.json skeleton"),
                       ("check", "validate Results/discussion.json (non-zero when invalid or absent)"),
                       ("status", "like check, but exit 0 whenever the product exists")):
        sub = verbs.add_parser(verb, help=text)
        sub.add_argument("--product", required=True, help="implementations/<repo>/<Name>")
    return parser


def _emit(payload: dict[str, Any], code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return code


def _refuse(code: str, message: str, exit_code: int = 1) -> int:
    return _emit({"ok": False, "error": code, "message": message}, exit_code)


def _product(arg: str) -> Path | None:
    try:
        path = Path(arg).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return path if path.is_dir() else None


def _contained_dir(product: Path, folder: Path) -> bool:
    try:
        resolved = folder.resolve()
        resolved.relative_to(product)
    except (OSError, RuntimeError, ValueError):
        return False
    return resolved.is_dir()


def _scaffold(product: Path, shown: str) -> int:
    stage = contract.product_stage(product)
    if stage is None:
        return _refuse("APPROVAL_ABSENT",
                       f"{shown} has neither Experimental_AGREED.md nor AGREED.md; approve it before scaffolding")
    target = product / contract.DISCUSSION_FILE
    if os.path.lexists(target):
        return _refuse("DISCUSSION_EXISTS", f"{contract.DISCUSSION_FILE} already exists; it is never overwritten")
    results = product / "Results"
    if os.path.lexists(results) and not _contained_dir(product, results):
        return _refuse("RESULTS_UNSAFE", "Results/ is not a directory inside the product folder")
    try:
        data = contract.scaffold(product)
    except contract.DiscussionRefusal as refusal:
        return _refuse(refusal.code, refusal.message)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    try:
        results.mkdir(exist_ok=True)
        with open(target, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        return _refuse("DISCUSSION_EXISTS", f"{contract.DISCUSSION_FILE} already exists; it is never overwritten")
    except OSError as exc:
        return _refuse("WRITE_FAILED", f"could not write {contract.DISCUSSION_FILE}: {exc.strerror or exc}")
    checked = contract.check_discussion(product, data)
    warnings = list(checked["warnings"])
    if not data["protocol"]:
        warnings.append("no experiments/experiments-*-vNN.md found: add the hypotheses by hand")
    return _emit({"ok": True, "file": contract.DISCUSSION_FILE, "stage": data["stage"],
                  "protocol": data["protocol"], "hypotheses": len(data["hypotheses"]),
                  "status": checked["status"], "errors": checked["errors"], "warnings": warnings})


def _report(product: Path, verb: str) -> int:
    loaded = contract.load_and_check(product)
    if not loaded["present"]:
        if verb == "check":
            return _refuse("DISCUSSION_ABSENT", f"{contract.DISCUSSION_FILE} does not exist; run scaffold first")
    payload = {"ok": loaded["status"] in ("complete", "draft"), "status": loaded["status"],
               "errors": loaded["errors"], "warnings": loaded["warnings"], "stage": loaded["stage"]}
    failed = loaded["status"] in ("invalid", "absent")
    return _emit(payload, 1 if failed and verb == "check" else 0)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except _Usage as usage:
        return _refuse("USAGE", f"{usage}; usage: discussion_cli.py {{scaffold,check,status}} --product <path>", 2)
    except SystemExit as stop:  # --help
        return int(stop.code or 0)
    product = _product(args.product)
    if product is None:
        return _refuse("PRODUCT_ABSENT", f"{args.product} is not a product folder")
    if args.verb == "scaffold":
        return _scaffold(product, args.product)
    return _report(product, args.verb)


if __name__ == "__main__":
    sys.exit(main())
