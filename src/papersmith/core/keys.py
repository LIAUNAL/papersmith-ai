"""``smith keys`` — your Asta and OpenAlex API keys, stored once, never printed.

Both literature services answer without a key. Asta's (Ai2) searches stall
without one, and once its key is set Asta is asked first wherever the
workspace's ``papersmith.yaml`` roles name it; an OpenAlex key raises the daily
OpenAlex budget. The dashboard asks for both keys in Doctor → API keys; this
command is the same store from a terminal, for headless machines and for
binds where the dashboard cannot take a secret.

Every rule — where the key lives, who may read the file, that an exported
variable wins, that nothing prints a value — is in the kit's
``skills/_core/api_keys.py``, loaded here by path because the dashboard and the
skill scripts load that same file. This module only parses arguments and
prints what the store says.
"""

from __future__ import annotations

import getpass
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

from ..errors import SourceError, UserError
from .exit_codes import SUCCESS, USER_ERROR

#: The providers the parser offers, kept here so that ``smith --help`` never
#: loads the kit. A test holds it equal to ``api_keys.PROVIDERS``.
KNOWN_PROVIDERS = ("asta", "openalex")
#: The name the kit's file is loaded under in this process.
MODULE_NAME = "papersmith_kit_api_keys"
MIN_API_VERSION = 1
#: One line of stdin, at most.
MAX_STDIN_BYTES = 4096


def load_api_keys():
    """The kit's ``skills/_core/api_keys.py``, loaded once."""
    module = sys.modules.get(MODULE_NAME)
    if module is not None:
        return module
    from ..kit import resolve_and_validate

    source = resolve_and_validate() / "skills" / "_core" / "api_keys.py"
    if not source.is_file():
        raise SourceError(f"{source} is missing: run `smith upgrade`, or reinstall papersmith-ai")
    spec = importlib.util.spec_from_file_location(MODULE_NAME, source)
    if spec is None or spec.loader is None:
        raise SourceError(f"cannot load {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - a broken kit file is a source error
        sys.modules.pop(MODULE_NAME, None)
        raise SourceError(f"cannot load {source}: {type(exc).__name__}: {exc}") from None
    if getattr(module, "API_VERSION", 0) < MIN_API_VERSION:
        sys.modules.pop(MODULE_NAME, None)
        raise SourceError(f"{source} is older than this smith expects: run `smith upgrade`")
    return module


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "keys", help="store, check or remove your Asta and OpenAlex API keys (never printed)",
        description="Per-user API keys for the literature connectors, kept outside every "
                    "workspace (mode 0600). An exported ASTA_API_KEY / OPENALEX_API_KEY wins over "
                    "the stored key. No command prints a key or takes one as an argument.")
    commands = parser.add_subparsers(dest="keys_command", required=True, metavar="<action>")

    store = commands.add_parser("set", help="store a key for this user (hidden prompt or --stdin)")
    store.add_argument("provider", choices=KNOWN_PROVIDERS)
    store.add_argument("--stdin", action="store_true",
                       help="read the key from one line of stdin instead of a hidden prompt")
    store.add_argument("--verify", action="store_true",
                       help="check the key with the service first and store it only if accepted")
    store.add_argument("--json", action="store_true", dest="as_json", help="print the result as JSON")
    store.set_defaults(handler=run_set)

    status = commands.add_parser("status", help="whether each key is configured and from where")
    status.add_argument("provider", nargs="?", choices=KNOWN_PROVIDERS, default=None)
    status.add_argument("--verify", action="store_true",
                        help="also make one read-only call per configured key")
    status.add_argument("--json", action="store_true", dest="as_json",
                        help="print JSON; with a provider, that provider's status object")
    status.set_defaults(handler=run_status)

    clear = commands.add_parser("clear", help="remove a stored key")
    clear.add_argument("provider", choices=KNOWN_PROVIDERS)
    clear.add_argument("--json", action="store_true", dest="as_json", help="print the result as JSON")
    clear.set_defaults(handler=run_clear)


def _shell() -> str:
    from .kaggle_mcp import detect_environment

    try:
        return detect_environment()["shell"]
    except Exception:  # noqa: BLE001 - the recipe falls back to POSIX sh
        return "sh"


def _refused(error: Exception, what: str) -> UserError:
    return UserError(f"{error}; {what}")


def _read_value(args, keys, meta: dict[str, str]) -> str:
    if args.stdin:
        return sys.stdin.readline(MAX_STDIN_BYTES + 1)
    if not sys.stdin.isatty():
        # getpass would fall back to an echoing read, and the key could land in
        # an agent's transcript.
        raise UserError("no terminal to prompt on: pipe the key in with --stdin "
                        "(a key is never a command-line argument)")
    print(f"Request a key at {meta['request_url']}")
    if meta.get("license"):
        print(meta["license"])
    return getpass.getpass(f"{meta['label']} API key (hidden): ")


def run_set(args) -> int:
    keys = load_api_keys()
    meta = keys.PROVIDERS[args.provider]
    raw = _read_value(args, keys, meta)
    try:
        value = keys.validate(raw)
    except keys.KeyRefused as exc:
        raise _refused(exc, "nothing was stored") from None
    verified = None
    if args.verify:
        verified = keys.verify(args.provider, value)
        if verified["state"] != "ok":
            raise UserError(f"{meta['label']}: {verified['state']} ({verified['detail']}); nothing was "
                            "stored. Re-run without --verify to store it anyway.")
    try:
        path = keys.store(args.provider, value)
    except keys.KeyRefused as exc:
        raise _refused(exc, "nothing was stored") from None
    state = keys.status(args.provider)
    if args.as_json:
        print(json.dumps({"ok": True, "status": state, "verify": verified}, indent=2))
        return SUCCESS
    if verified is not None:
        print(f"verified: {verified['detail']}")
    print(f"stored: {path}" + (" (mode 0600)" if os.name != "nt" else ""))
    if state["shadowed"]:
        print(f"note: {state['env']} is exported in this shell and wins over the stored key")
    print(f"Sessions the dashboard starts from now on get {state['env']}; restart open ones.")
    print(f"outside the dashboard: {keys.export_command(args.provider, _shell())}")
    return SUCCESS


def _describe(state: dict[str, Any]) -> str:
    if state["source"] == "env":
        line = f"configured (exported {state['env']})"
        if state["stored"]:
            line += "; the stored key is shadowed"
        return line
    if state["source"] == "store":
        return f"configured (stored at {state['path']})"
    if state["problem"]:
        return f"not configured: stored file ignored ({state['problem']}): chmod 600 {state['path']}"
    return (f"not configured (optional): `smith keys set {state['provider']}` or the dashboard's "
            f"Doctor → API keys; request one at {state['request_url']}")


def run_status(args) -> int:
    keys = load_api_keys()
    names = [args.provider] if args.provider else list(keys.PROVIDERS)
    shell = _shell()
    states = []
    for name in names:
        state = keys.status(name)
        state["export_command"] = keys.export_command(name, shell)
        states.append(state)
    checks: list[dict[str, Any]] = []
    code = SUCCESS
    if args.verify:
        for state in states:
            if not state["configured"]:
                if args.provider:
                    code = USER_ERROR
                continue
            result = keys.verify(state["provider"])
            checks.append(result)
            if result["state"] != "ok":
                code = USER_ERROR
        if args.provider is None and not checks:
            code = USER_ERROR
    if args.as_json:
        if args.provider:
            payload: dict[str, Any] = dict(states[0])
            if args.verify:
                payload["verify"] = checks[0] if checks else None
        else:
            payload = {"ok": code == SUCCESS, "store_dir": str(keys.store_dir()),
                       "override": bool(os.environ.get(keys.STORE_DIR_ENV, "").strip()),
                       "keys": states}
            if args.verify:
                payload["verify"] = checks
        print(json.dumps(payload, indent=2))
        return code
    for state in states:
        print(f"{state['provider']} key: {_describe(state)}")
        if state["env_problem"]:
            print(f"  note: {state['env']} is exported but {state['env_problem']}; it is ignored")
    for result in checks:
        budget = result.get("budget") or {}
        extra = (f"; budget {budget.get('remaining_usd')} of {budget.get('limit_usd')} USD today"
                 if budget.get("remaining_usd") else "")
        print(f"verify {result['provider']}: {result['state']} ({result['detail']}{extra})")
    if args.verify and not checks:
        print("verify: skipped, no configured key")
    for state in states:
        if state["source"] == "store":
            print(f"outside the dashboard: {state['export_command']}")
    return code


def run_clear(args) -> int:
    keys = load_api_keys()
    try:
        removed = keys.clear(args.provider)
    except keys.KeyRefused as exc:
        raise _refused(exc, "nothing was removed") from None
    state = keys.status(args.provider)
    if args.as_json:
        print(json.dumps({"ok": True, "removed": removed, "status": state}, indent=2))
        return SUCCESS
    print(f"removed: {state['path']}" if removed else f"nothing to remove: {state['path']}")
    if state["source"] == "env":
        print(f"note: {state['env']} is still exported in this shell")
    return SUCCESS


def key_rows() -> list[dict[str, str]]:
    """Offline ``smith doctor`` rows: one per provider, never a value, never ``fail``."""
    try:
        keys = load_api_keys()
    except Exception as exc:  # noqa: BLE001 - doctor reports, never raises
        return [{"area": "tools", "item": f"{name} key", "state": "warn",
                 "detail": f"key store unavailable: {exc}"} for name in KNOWN_PROVIDERS]
    rows = []
    for name in KNOWN_PROVIDERS:
        try:
            state = keys.status(name)
        except Exception as exc:  # noqa: BLE001
            rows.append({"area": "tools", "item": f"{name} key", "state": "warn",
                         "detail": f"key store unavailable: {exc}"})
            continue
        if state["configured"]:
            detail = ("configured (exported " + state["env"] + ")" if state["source"] == "env"
                      else "configured (stored key)")
            if state["shadowed"]:
                detail += "; the stored key is shadowed by the exported variable"
            rows.append({"area": "tools", "item": f"{name} key", "state": "ok", "detail": detail})
        elif state["problem"]:
            rows.append({"area": "tools", "item": f"{name} key", "state": "warn",
                         "detail": f"stored key ignored ({state['problem']}): chmod 600 {state['path']}"})
        else:
            default = "OpenAlex stays the default" if name == "asta" else "keyless budget"
            rows.append({"area": "tools", "item": f"{name} key", "state": "absent",
                         "detail": f"not configured (optional; {default}): `smith keys set {name}` "
                                   "or Doctor → API keys"})
    return rows


__all__ = ["KNOWN_PROVIDERS", "load_api_keys", "register", "run_set", "run_status", "run_clear",
           "key_rows"]
