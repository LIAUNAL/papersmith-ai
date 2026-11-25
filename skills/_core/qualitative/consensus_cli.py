#!/usr/bin/env python3
"""Consensus rounds (Delphi and kin) and MICMAC structural analysis, recorded by the operator.

    consensus_cli.py panel add --member <anonymised code> --expertise "<text>" [--note <text>] \
        --by <operator> --root .
    consensus_cli.py plan record --rounds <n> --threshold <percent> --scale <min>-<max> \
        --agree-from <value> [--reason <why the plan changes>] --by <operator> --root .
    consensus_cli.py round record --round <k> --file <responses CSV> [--reason <why recorded again>] \
        --by <operator> --root .
    consensus_cli.py round status [--round <k>] --root .
    consensus_cli.py micmac compute --file <influence matrix CSV> [--power <k>] [--p-value <n>] \
        --by <operator> --root .
    consensus_cli.py micmac status --root .
    consensus_cli.py status --root .

``panel add`` registers a panel member in ``study/consensus/panel.json`` by an
anonymised code (letters, digits, ``_`` or ``-``; never a name or an email
address) with their expertise. ``plan record`` records the consensus rule in
``study/consensus/plan.json``: the planned rounds, the threshold (percent of a
member's ratings at or above ``--agree-from`` on the ``--scale``), refused
until the study protocol is approved and current (gate G-STUDY-PROTOCOL) and
bound to the lock's sha256, so an amendment makes it stale; changing a
recorded plan needs ``--reason``. ``round record`` binds the operator's
response file for round k (columns ``member,item,rating[,comment]``) by its
sha256 to the current plan in ``study/consensus/rounds.json``: every member
must be in the panel, every rating a whole number on the scale, the rounds
recorded in order and within the plan. ``round status`` computes per item, from
the files: n, percent agreement (ratings >= agree-from), median, IQR (quantiles
of Hyndman and Fan type 7), whether consensus is reached (percent >=
threshold) and the change from the previous round; a round is stale when its
file, the plan or the protocol changed (gate G-ROUNDS: the plan current and
every planned round recorded and current). ``micmac compute`` reads the
operator's square influence matrix (a header row and a first column of the
same variable names, entries 0-3 or P, a zero diagonal; P counts as
``--p-value``, 4 by default), and records in ``study/consensus/micmac.json``,
bound to its sha256, the direct and indirect influence and dependence (row
and column sums of M and of M^k), the ranking stability per power (``--power``
fixes k in 2-10; by default M is raised until both rankings are stable, at
most 10) and each variable's quadrant by the means (influential, relay,
dependent, autonomous). MACTOR and scenarios stay narrative: no command.

The operator produces every rating and every influence: the core never writes
into a response file or a matrix, the assistant never enters or edits a
rating, and no output carries a response comment (comments are only counted).
Every path is relative to the workspace and confined to it. Decisions K4 and
K5 of ``odd/tasks/paper-type-lines.md``.

Each verb prints one JSON object. A refusal prints ``{"ok": false, "error":
<CODE>, "message": ...}`` and exits 1 (usage errors exit 2). Refusal codes:
``USAGE``, ``APPROVER_MISSING``, ``TEXT_INVALID``, ``FIELD_MISSING``,
``REASON_MISSING``, ``RECORD_UNCHANGED``, ``MEMBER_ID_INVALID``,
``MEMBER_ID_EMAIL``, ``TEXT_HAS_EMAIL``, ``MEMBER_EXISTS``, ``ROUNDS_INVALID``,
``THRESHOLD_INVALID``, ``SCALE_INVALID``, ``AGREE_FROM_INVALID``,
``PROTOCOL_NOT_APPROVED``, ``PROTOCOL_CHANGED``, ``PROTOCOL_LOCK_CORRUPT``,
``PLAN_ABSENT``, ``PLAN_STALE``, ``PANEL_ABSENT``, ``ROUND_INVALID``,
``ROUND_BEYOND_PLAN``, ``ROUND_OUT_OF_ORDER``, ``ROUND_NOT_RECORDED``,
``PATH_OUTSIDE_WORKSPACE``, ``FILE_ABSENT``, ``FILE_UNREADABLE``,
``CSV_INVALID``, ``CSV_EMPTY``, ``MEMBER_UNKNOWN``, ``ITEM_MISSING``,
``RATING_INVALID``, ``RATING_OUT_OF_SCALE``, ``RESPONSE_DUPLICATE``,
``MATRIX_INVALID``, ``MATRIX_NOT_SQUARE``, ``MATRIX_NAMES_MISMATCH``,
``MATRIX_ENTRY_INVALID``, ``DIAGONAL_NONZERO``, ``POWER_INVALID``,
``P_VALUE_INVALID``, ``PANEL_CORRUPT``, ``PLAN_CORRUPT``, ``ROUNDS_CORRUPT``,
``MICMAC_CORRUPT``, ``INTERNAL_ERROR``.
"""

from __future__ import annotations

import sys as _floor_sys
if _floor_sys.version_info < (3, 11):  # the package floor (pyproject requires-python >=3.11)
    _floor_sys.stdout.write('{"ok": false, "error": "PYTHON_VERSION_UNSUPPORTED", "message": "this skill needs '
                            'Python 3.11+; the running interpreter is %d.%d. Run it with the workspace '
                            'environment (.micromamba/envs/papersmith/bin/python) or the smith interpreter."}\n'
                            % _floor_sys.version_info[:2])
    raise SystemExit(2)

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make `skills._core.qualitative` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from skills._core.empirical import records as study_records  # noqa: E402
    from skills._core.empirical.study_cli import _atomic_write, _now, _operator, _out, _Parser, _text  # noqa: E402
    from skills._core.qualitative import consensus, consensus_stats as stats  # noqa: E402
else:
    from ..empirical import records as study_records
    from ..empirical.study_cli import _atomic_write, _now, _operator, _out, _Parser, _text
    from . import consensus, consensus_stats as stats

ConsensusError = consensus.ConsensusError
MAX_ROUNDS = 20
SCALE = re.compile(r"^\s*(-?\d+)\s*-\s*(-?\d+)\s*$")


def _write(root: Path, relative: str, data: dict) -> None:
    path, _ = consensus.confined(root, relative)
    data["schema"] = consensus.SCHEMA
    _atomic_write(path, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _whole(text: str | None) -> int | None:
    text = (text or "").strip()
    digits = text[1:] if text.startswith("-") else text
    return int(text) if digits.isascii() and digits.isdecimal() else None


def _no_email(value: str, flag: str) -> str:
    if consensus.EMAIL.search(value):
        raise ConsensusError("TEXT_HAS_EMAIL", f"{flag} holds an email address; the panel record keeps members "
                                               "anonymous")
    return value


def _reason(args) -> str | None:
    return None if args.reason is None else (_text(args.reason, "--reason") or None)


def _unchanged(last: dict | None, entry: dict, subject: str) -> None:
    if last is not None and {k: v for k, v in last.items() if k not in consensus.ENTRY_META} == \
            {k: v for k, v in entry.items() if k not in consensus.ENTRY_META}:
        raise ConsensusError("RECORD_UNCHANGED", f"the {subject} record is already current: nothing changed since "
                                                 "it was recorded")


def _workspace_file(root: Path, given: str | None) -> tuple[str, bytes]:
    """(workspace-relative path, bytes) of an operator file, confined before any stat."""
    if not (given or "").strip():
        raise ConsensusError("FIELD_MISSING", "--file names the operator's file, relative to the workspace")
    path, relative = consensus.confined(root, given)
    if not consensus._is_file(path):
        raise ConsensusError("FILE_ABSENT", f"{relative} is not a file of the workspace")
    try:
        return relative, path.read_bytes()
    except OSError as error:
        raise ConsensusError("FILE_UNREADABLE", f"{relative} cannot be read ({error.strerror or error})") from None


# --------------------------------------------------------------------------- panel


def cmd_panel(args, root: Path) -> dict:
    by = _operator(args)
    member = (args.member or "").strip()
    if not member:
        raise ConsensusError("FIELD_MISSING", "--member gives the member's anonymised code (e.g. P01)")
    if "@" in member:
        raise ConsensusError("MEMBER_ID_EMAIL", "--member looks like an email address; give an anonymised code "
                                                "(e.g. P01) and keep the key to names outside the workspace")
    if not consensus.MEMBER.match(member):
        raise ConsensusError("MEMBER_ID_INVALID", "--member is an anonymised code: 1-32 letters, digits, '_' or "
                                                  "'-', no spaces (e.g. P01), never a name")
    expertise = _no_email(_text(args.expertise or "", "--expertise"), "--expertise")
    if not expertise:
        raise ConsensusError("FIELD_MISSING", "--expertise states the member's field and experience")
    note = None if args.note is None else (_no_email(_text(args.note, "--note"), "--note") or None)
    consensus.confined(root, consensus.PANEL_PATH)
    data = consensus.read_panel(root)
    if any(entry["member"] == member for entry in data["history"]):
        raise ConsensusError("MEMBER_EXISTS", f"{member} is already in the panel")
    data["history"].append({"member": member, "expertise": expertise, "note": note, "by": by, "at": _now()})
    _write(root, consensus.PANEL_PATH, data)
    return {"ok": True, "path": consensus.PANEL_PATH, "panel": consensus.panel_state(root)}


# --------------------------------------------------------------------------- plan


def _plan_entry(args) -> dict:
    rounds = _whole(args.rounds)
    if rounds is None or not 1 <= rounds <= MAX_ROUNDS:
        raise ConsensusError("ROUNDS_INVALID", f"--rounds is a whole number from 1 to {MAX_ROUNDS}")
    try:
        threshold = float((args.threshold or "").strip())
    except ValueError:
        threshold = math.nan
    if not (math.isfinite(threshold) and 0 < threshold <= 100):
        raise ConsensusError("THRESHOLD_INVALID", "--threshold is a percentage above 0 and at most 100")
    scale = SCALE.match(args.scale or "")
    low, high = (int(scale.group(1)), int(scale.group(2))) if scale else (0, 0)
    if not scale or low >= high:
        raise ConsensusError("SCALE_INVALID", "--scale is written <min>-<max> with whole numbers, min below max "
                                              "(e.g. 1-9; --scale=-3-3 for a scale below zero)")
    agree_from = _whole(args.agree_from)
    if agree_from is None or not low < agree_from <= high:
        raise ConsensusError("AGREE_FROM_INVALID", f"--agree-from is the lowest rating that counts as agreement, a "
                                                   f"whole number above {low} and at most {high}")
    return {"rounds": rounds, "threshold": int(threshold) if threshold.is_integer() else threshold,
            "scale": {"min": low, "max": high}, "agree_from": agree_from}


def cmd_plan(args, root: Path) -> dict:
    by = _operator(args)
    entry = _plan_entry(args)
    reason = _reason(args)
    consensus.confined(root, consensus.PLAN_PATH)
    data = consensus.read_plan(root)
    history = data["history"]
    lock = study_records.require_current_lock(root)
    entry.update(protocol_revision=lock["revision"], protocol_sha256=lock["sha256"])
    _unchanged(history[-1] if history else None, entry, "consensus plan")
    if history and not reason:
        raise ConsensusError("REASON_MISSING", "--reason states why the recorded consensus plan changes; its "
                                               "rounds become stale until recorded again")
    history.append({"by": by, "at": _now(), **entry, **({"reason": reason} if reason else {})})
    _write(root, consensus.PLAN_PATH, data)
    return {"ok": True, "path": consensus.PLAN_PATH, "plan": consensus.plan_state(root)}


# --------------------------------------------------------------------------- rounds


def cmd_round(args, root: Path) -> dict:
    if args.action == "status":
        return _round_status(args, root)
    by = _operator(args)
    k = _whole(args.round)
    if k is None or k < 1:
        raise ConsensusError("ROUND_INVALID", "--round is the round number, a whole number from 1")
    reason = _reason(args)
    consensus.confined(root, consensus.ROUNDS_PATH)
    plan = consensus.plan_state(root)
    if plan["state"] == "absent":
        raise ConsensusError("PLAN_ABSENT", "no consensus plan is recorded: `plan record --by` comes first")
    if plan["state"] == "corrupt":
        raise ConsensusError("PLAN_CORRUPT", plan["message"])
    study_records.require_current_lock(root)
    if not plan["current"]:
        raise ConsensusError("PLAN_STALE", f"the consensus plan covers an earlier protocol ({', '.join(plan['reasons'])}); "
                                           "the operator records the plan again with `plan record --reason`")
    if k > plan["rounds"]:
        raise ConsensusError("ROUND_BEYOND_PLAN", f"the plan has {plan['rounds']} round(s); a further round is a "
                                                  "plan change (`plan record --rounds <n> --reason`)")
    data = consensus.read_rounds(root)
    recorded = consensus.latest_rounds(data["history"])
    if k not in recorded and k != max(recorded, default=0) + 1:
        raise ConsensusError("ROUND_OUT_OF_ORDER", f"round {k} cannot come before round "
                                                   f"{max(recorded, default=0) + 1}: rounds are recorded in order")
    if k in recorded and not reason:
        raise ConsensusError("REASON_MISSING", f"round {k} is already recorded: --reason states why its response "
                                               "file is recorded again")
    members = {entry["member"] for entry in consensus.read_panel(root)["history"]}
    if not members:
        raise ConsensusError("PANEL_ABSENT", "the panel is empty: register each member with `panel add` first")
    relative, raw = _workspace_file(root, args.file)
    responses, comments = consensus.parse_responses(raw, relative, members, plan["scale"]["min"],
                                                    plan["scale"]["max"])
    entry = {"round": k, "file": relative, "sha256": hashlib.sha256(raw).hexdigest(), "responses": len(responses),
             "items": len({item for _, item, _ in responses}), "responders": len({m for m, _, _ in responses}),
             "comments": comments, "plan_sha256": plan["plan_sha256"]}
    _unchanged(recorded.get(k), entry, f"round {k}")
    data["history"].append({"by": by, "at": _now(), **entry, **({"reason": reason} if reason else {})})
    _write(root, consensus.ROUNDS_PATH, data)
    return {"ok": True, "path": consensus.ROUNDS_PATH,
            "round": consensus.round_results(root, only=k)["rounds"][0], "gate": consensus.rounds_state(root)}


def _round_status(args, root: Path) -> dict:
    only = None
    if args.round is not None:
        only = _whole(args.round)
        if only is None or only < 1:
            raise ConsensusError("ROUND_INVALID", "--round is the round number, a whole number from 1")
    results = consensus.round_results(root, only)
    if only is not None and results["state"] != "corrupt" and not results["rounds"]:
        raise ConsensusError("ROUND_NOT_RECORDED", f"round {only} is not recorded")
    return {"ok": True, "plan": consensus.plan_state(root), "quantile_method": stats.QUANTILE_METHOD,
            "state": results["state"], **({"message": results["message"]} if "message" in results else {}),
            "rounds": results["rounds"], "gate": consensus.rounds_state(root)}


# --------------------------------------------------------------------------- MICMAC


def cmd_micmac(args, root: Path) -> dict:
    if args.action == "status":
        return {"ok": True, "micmac": consensus.micmac_state(root)}
    by = _operator(args)
    power = None
    if args.power is not None:
        power = _whole(args.power)
        if power is None or not 2 <= power <= stats.MAX_POWER:
            raise ConsensusError("POWER_INVALID", f"--power is a whole number from 2 to {stats.MAX_POWER} (leave it "
                                                  "out to raise the matrix until the ranking is stable)")
    p_value = stats.P_DEFAULT
    if args.p_value is not None:
        p_value = _whole(args.p_value)
        if p_value is None or not 0 <= p_value <= 9:
            raise ConsensusError("P_VALUE_INVALID", "--p-value is the whole number from 0 to 9 a potential "
                                                    "influence (P) counts as")
    consensus.confined(root, consensus.MICMAC_PATH)
    data = consensus.read_micmac(root)
    relative, raw = _workspace_file(root, args.file)
    names, matrix, potential = consensus.parse_matrix(raw, relative, p_value)
    entry = {"file": relative, "sha256": hashlib.sha256(raw).hexdigest(), "variables": names, "p_value": p_value,
             "p_entries": potential, "power_requested": power, **stats.micmac(names, matrix, power)}
    _unchanged(data["history"][-1] if data["history"] else None, entry, "MICMAC")
    data["history"].append({"by": by, "at": _now(), **entry})
    _write(root, consensus.MICMAC_PATH, data)
    return {"ok": True, "path": consensus.MICMAC_PATH, "micmac": consensus.micmac_state(root)}


def cmd_status(args, root: Path) -> dict:
    return {"ok": True, **consensus.consensus_status(root)}


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="consensus_cli.py", description="Consensus panel, plan and rounds; MICMAC.")
    sub = parser.add_subparsers(dest="verb", required=True)
    verbs = {"panel": (cmd_panel, ("add",)), "plan": (cmd_plan, ("record",)),
             "round": (cmd_round, ("record", "status")), "micmac": (cmd_micmac, ("compute", "status")),
             "status": (cmd_status, ())}
    actions: dict[tuple[str, str], argparse.ArgumentParser] = {}
    for name, (_, names) in verbs.items():
        verb = sub.add_parser(name)
        verb.error = parser.error  # type: ignore[method-assign]
        verb.add_argument("--root", default=".")
        if not names:
            continue
        # Each action is a subparser of its own so `status` refuses a record option (a usage
        # error); `--root` is accepted before or after the action (SUPPRESS keeps an absent one
        # from overriding the value given before it).
        group = verb.add_subparsers(dest="action", required=True)
        for action_name in names:
            action = group.add_parser(action_name)
            action.error = parser.error  # type: ignore[method-assign]
            action.add_argument("--root", default=argparse.SUPPRESS)
            actions[(name, action_name)] = action
    panel = actions[("panel", "add")]
    for flag in ("--member", "--expertise", "--note"):
        panel.add_argument(flag, default=None)
    panel.add_argument("--by", default="")
    plan = actions[("plan", "record")]
    for flag in ("--rounds", "--threshold", "--scale", "--agree-from", "--reason"):
        plan.add_argument(flag, default=None)
    plan.add_argument("--by", default="")
    record = actions[("round", "record")]
    for flag in ("--round", "--file", "--reason"):
        record.add_argument(flag, default=None)
    record.add_argument("--by", default="")
    actions[("round", "status")].add_argument("--round", default=None)
    compute = actions[("micmac", "compute")]
    for flag in ("--file", "--power", "--p-value"):
        compute.add_argument(flag, default=None)
    compute.add_argument("--by", default="")
    args = parser.parse_args(argv)
    try:
        result = verbs[args.verb][0](args, Path(args.root))
    except ConsensusError as error:
        return _out({"ok": False, "error": error.code, "message": error.message}, 1)
    except Exception as exc:  # a bug, reported typed so a caller can quote it
        return _out({"ok": False, "error": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"}, 1)
    return _out(result, 0 if result.get("ok") else 1)


if __name__ == "__main__":
    sys.exit(main())
