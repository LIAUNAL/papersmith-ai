#!/usr/bin/env python3
"""Participant flow diagram: the operator's counts, checked, drawn and signed.

    flow_cli.py template <consort-2025|strobe|stard-2015> [--arm <name> ...] [--write] --root .
    flow_cli.py check   --root .
    flow_cli.py render  --root .
    flow_cli.py signoff --by <operator> [--note <text>] --root .
    flow_cli.py status  --root .

The counts live in ``study/flow.json``, entered by the operator; no verb ever
writes a count. ``template`` prints an empty flow (``--write`` saves it, never
over an existing file); ``check`` reports every arithmetic problem;
``render`` writes ``paper/Figures/participant-flow.svg`` only from valid
counts; ``signoff`` records, in ``study/flow-signoffs.json``, the operator who
signs and the sha256 of the counts (timestamp keys aside) together with the
figure, refusing invalid counts, a missing or stale figure and an unchanged
state. An agent never signs on the operator's behalf. ``status`` reports the
flow's validity, the figure (absent, current, stale) and the latest sign-off
(current or stale).

Each verb prints one JSON object. A refusal prints ``{"ok": false, "error":
<CODE>, "message": ...}`` and exits 1 (usage errors exit 2). Refusal codes:
``USAGE``, ``TEMPLATE_UNKNOWN``, ``ARMS_NOT_APPLICABLE``, ``BRANCHES_INVALID``,
``TEXT_INVALID`` (`template` arms checked as `check` does), ``FLOW_EXISTS``,
``FLOW_ABSENT``, ``FLOW_UNREADABLE``, ``FLOW_INVALID`` (with ``problems``),
``FIGURE_ABSENT``, ``FIGURE_STALE``, ``OPERATOR_ABSENT``, ``SIGNOFF_UNCHANGED``,
``SIGNOFFS_CORRUPT``.
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
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make `skills._core.participant_flow` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from skills._core.participant_flow import model, render  # noqa: E402
else:
    from . import model, render

FlowError = model.FlowError


def _out(payload: dict, code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return code


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SystemExit(_out({"ok": False, "error": "USAGE", "message": message}, 2))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(temp, 0o666 & ~umask)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _write_json(path: Path, data) -> None:
    _atomic_write(path, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _load_flow(root: Path):
    path = root / model.FLOW_PATH
    if not path.is_file():
        raise FlowError("FLOW_ABSENT", f"{model.FLOW_PATH} does not exist; `template <id> --write` "
                                       "creates it for the operator to fill")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FlowError("FLOW_UNREADABLE", f"{model.FLOW_PATH} cannot be read as JSON ({exc})") from None


def _valid_flow(root: Path) -> dict:
    flow = _load_flow(root)
    problems = model.check(flow)
    if problems:
        error = FlowError("FLOW_INVALID", f"{len(problems)} problem(s) in {model.FLOW_PATH}; "
                                          "the operator corrects the counts")
        error.problems = problems  # type: ignore[attr-defined]
        raise error
    return flow


def _figure_state(root: Path, flow: dict | None) -> str:
    figure = root / model.FIGURE_PATH
    if not figure.is_file():
        return "absent"
    if flow is None:
        return "stale"
    return "current" if figure.read_bytes() == render.render_svg(flow).encode("utf-8") else "stale"


def _basis(root: Path, flow: dict) -> str:
    digest = hashlib.sha256(model.flow_sha256(flow).encode("ascii"))
    digest.update(b"\0")
    digest.update((root / model.FIGURE_PATH).read_bytes())
    return digest.hexdigest()


def _signoffs(root: Path) -> dict:
    path = root / model.SIGNOFFS_PATH
    if not path.is_file():
        return {"schema": model.SCHEMA, "signoffs": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FlowError("SIGNOFFS_CORRUPT", f"{model.SIGNOFFS_PATH} cannot be read as JSON ({exc})") from None
    if not isinstance(data, dict) or not isinstance(data.get("signoffs"), list):
        raise FlowError("SIGNOFFS_CORRUPT", f"{model.SIGNOFFS_PATH} is not a sign-off record: "
                                            "a \"signoffs\" list")
    return data


def _latest(root: Path, current_basis: str | None) -> dict | None:
    entries = _signoffs(root)["signoffs"]
    last = entries[-1] if entries and isinstance(entries[-1], dict) else None
    if last is None:
        return None
    return {"by": last.get("by"), "at": last.get("at"), "note": last.get("note", ""),
            "sha256": last.get("sha256"),
            "current": bool(last.get("sha256")) and last.get("sha256") == current_basis}


# --------------------------------------------------------------------------- verbs


def cmd_template(args, root: Path) -> dict:
    flow = model.empty_flow(args.id, args.arm)
    if args.write:
        path = root / model.FLOW_PATH
        if path.exists():
            raise FlowError("FLOW_EXISTS", f"{model.FLOW_PATH} already exists; it is never overwritten")
        _write_json(path, flow)
    tpl = model.TEMPLATES[args.id]
    return {"ok": True, "template": args.id, "guideline": tpl["guideline"], "url": tpl["url"],
            "path": model.FLOW_PATH, "written": bool(args.write), "flow": flow}


def cmd_check(args, root: Path) -> dict:
    flow = _load_flow(root)
    problems = model.check(flow)
    out = {"ok": not problems, "valid": not problems, "template": flow.get("template")
           if isinstance(flow, dict) else None, "problems": problems}
    if problems:
        out.update(error="FLOW_INVALID", message=f"{len(problems)} problem(s) in {model.FLOW_PATH}")
    return out


def cmd_render(args, root: Path) -> dict:
    flow = _valid_flow(root)
    _atomic_write(root / model.FIGURE_PATH, render.render_svg(flow).encode("utf-8"))
    return {"ok": True, "path": model.FIGURE_PATH, "template": flow["template"],
            "flow_sha256": model.flow_sha256(flow)}


def cmd_signoff(args, root: Path) -> dict:
    by = (args.by or "").strip()
    if not by:
        raise FlowError("OPERATOR_ABSENT", "--by names the operator who signs; an agent never signs "
                                           "on the operator's behalf")
    flow = _valid_flow(root)
    state = _figure_state(root, flow)
    if state == "absent":
        raise FlowError("FIGURE_ABSENT", f"{model.FIGURE_PATH} does not exist; `render` draws it")
    if state == "stale":
        raise FlowError("FIGURE_STALE", f"{model.FIGURE_PATH} does not show the current counts; "
                                        "`render` draws it again")
    digest = _basis(root, flow)
    data = _signoffs(root)
    entries = data["signoffs"]
    if entries and isinstance(entries[-1], dict) and entries[-1].get("sha256") == digest:
        raise FlowError("SIGNOFF_UNCHANGED", "the participant flow sign-off is already current: "
                                             "nothing changed since it was signed")
    entries.append({"by": by, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
                    .replace("+00:00", "Z"), "note": (args.note or "").strip(), "sha256": digest,
                    "template": flow["template"], "basis": f"{model.FLOW_PATH} + {model.FIGURE_PATH}"})
    data["schema"] = model.SCHEMA
    _write_json(root / model.SIGNOFFS_PATH, data)
    return {"ok": True, "path": model.SIGNOFFS_PATH, "signoff": _latest(root, digest)}


def cmd_status(args, root: Path) -> dict:
    try:
        flow = _load_flow(root)
    except FlowError as error:
        if error.code != "FLOW_ABSENT":
            raise
        return {"ok": True, "flow": "absent", "template": None, "problems": 0,
                "figure": _figure_state(root, None), "signoff": _latest(root, None)}
    problems = model.check(flow)
    valid = None if problems else flow
    figure = _figure_state(root, valid)
    basis = _basis(root, flow) if valid is not None and figure == "current" else None
    return {"ok": True, "flow": "invalid" if problems else "valid",
            "template": flow.get("template") if isinstance(flow, dict) else None,
            "problems": len(problems), "figure": figure, "signoff": _latest(root, basis)}


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="flow_cli.py", description="Participant flow: template, check, render, signoff, status.")
    sub = parser.add_subparsers(dest="verb", required=True)
    verbs = {"template": cmd_template, "check": cmd_check, "render": cmd_render,
             "signoff": cmd_signoff, "status": cmd_status}
    for name in verbs:
        verb = sub.add_parser(name)
        verb.error = parser.error  # type: ignore[method-assign]
        verb.add_argument("--root", default=".")
    sub.choices["template"].add_argument("id")
    sub.choices["template"].add_argument("--arm", action="append", default=None)
    sub.choices["template"].add_argument("--write", action="store_true")
    sub.choices["signoff"].add_argument("--by", default="")
    sub.choices["signoff"].add_argument("--note", default="")
    args = parser.parse_args(argv)
    try:
        result = verbs[args.verb](args, Path(args.root))
    except FlowError as error:
        payload = {"ok": False, "error": error.code, "message": error.message}
        if getattr(error, "problems", None):
            payload["problems"] = error.problems  # type: ignore[attr-defined]
        return _out(payload, 1)
    except Exception as exc:  # a bug, reported typed so a caller can quote it
        return _out({"ok": False, "error": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"}, 1)
    return _out(result, 0 if result.get("ok") else 1)


if __name__ == "__main__":
    sys.exit(main())
