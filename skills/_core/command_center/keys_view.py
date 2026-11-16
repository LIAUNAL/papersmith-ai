"""The dashboard's API keys: what the Doctor tab's keys panel reads and writes.

The keys themselves — Ai2's Asta and OpenAlex — and every rule about them live
in ``skills/_core/api_keys.py`` (one file the skill scripts and ``smith keys``
load too); this module adapts it to the server. The server exposes it only
behind the support terminal's guard: a bind where the terminal is offered (a
loopback one, or a network one started with ``--network-terminal``), the
session cookie its login URL sets and, for writes, a same-origin request
carrying ``Origin`` — a key typed into a page anybody on the network can reach
would not stay a secret. Over plain HTTP on a network bind the key still
crosses the network unencrypted, as everything typed into the terminal does.

Nothing here returns a key. ``status_payload`` says whether and from where;
``secret_values`` exists for redaction (the AI-history archive, the static
export, error tails) and its result is never persisted; ``session_additions``
hands the stored keys to the sessions the CLI assistant starts, where the
harness's MCP entries read them from the environment.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Mapping

#: The module name every in-process consumer loads ``api_keys.py`` under.
MODULE_NAME = "papersmith_api_keys"
SOURCE = Path(__file__).resolve().parents[1] / "api_keys.py"
#: Largest request body a key route reads; a key is far shorter.
MAX_BODY_BYTES = 4096


def api_keys():
    """``skills/_core/api_keys.py``, loaded once."""
    module = sys.modules.get(MODULE_NAME)
    if module is None:
        spec = importlib.util.spec_from_file_location(MODULE_NAME, SOURCE)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {SOURCE}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[MODULE_NAME] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(MODULE_NAME, None)
            raise
    return module


def _environment() -> dict[str, str]:
    from .terminal import remote_mcp_environment

    try:
        env = remote_mcp_environment()
    except Exception:  # noqa: BLE001 - the panel still renders
        return {"system": "", "shell": "sh", "profile_file": "~/.profile", "note": ""}
    return {key: env.get(key, "") for key in ("system", "shell", "profile_file", "note")}


def status_payload(sessions_open: int = 0, root: Path | None = None) -> dict[str, Any]:
    """What the keys panel shows. Never a key. With the workspace ``root``, also
    which harness files register the Asta MCP server the agents search."""
    keys = api_keys()
    environment = _environment()
    states = []
    for provider in keys.providers():
        state = keys.status(provider)
        state["export_command"] = keys.export_command(provider, environment["shell"] or "sh")
        states.append(state)
    payload = {"ok": True, "store_dir": str(keys.store_dir()),
               "override": bool(states and states[0]["override"]),
               "environment": environment, "keys": states, "sessions_open": int(sessions_open)}
    if root is not None:
        from .terminal import asta_mcp_status

        payload["asta_mcp"] = asta_mcp_status(root)
    return payload


def store(provider: str, value: Any, *, verify: bool = False) -> tuple[int, dict[str, Any]]:
    """Validate, optionally verify, then store. ``(http status, body)``."""
    keys = api_keys()
    if provider not in keys.providers():
        return 404, {"ok": False, "error": "UNKNOWN_PROVIDER"}
    if not isinstance(value, str):
        return 422, {"ok": False, "error": "KEY_INVALID", "reason": "EMPTY",
                     "detail": "the body must be {\"value\": \"<key>\"}"}
    try:
        cleaned = keys.validate(value)
    except keys.KeyRefused as exc:
        return 422, {"ok": False, "error": "KEY_INVALID", "reason": exc.code, "detail": str(exc)}
    checked = None
    if verify:
        checked = keys.verify(provider, cleaned)
        if checked["state"] == "refused":
            return 422, {"ok": False, "error": "KEY_REFUSED", "verify": checked}
        if checked["state"] != "ok":
            return 503, {"ok": False, "error": "VERIFY_UNREACHABLE", "verify": checked}
    try:
        keys.store(provider, cleaned)
    except keys.KeyRefused as exc:
        return 409, {"ok": False, "error": exc.code, "detail": str(exc)}
    state = keys.status(provider)
    return 200, {"ok": True, "status": state, "verify": checked,
                 "shadowed_by_env": bool(state["shadowed"])}


def clear(provider: str) -> tuple[int, dict[str, Any]]:
    keys = api_keys()
    if provider not in keys.providers():
        return 404, {"ok": False, "error": "UNKNOWN_PROVIDER"}
    try:
        removed = keys.clear(provider)
    except keys.KeyRefused as exc:
        return 409, {"ok": False, "error": exc.code, "detail": str(exc)}
    return 200, {"ok": True, "removed": removed, "status": keys.status(provider)}


def verify(provider: str) -> tuple[int, dict[str, Any]]:
    """Verify the CONFIGURED key: never one sent in a request body."""
    keys = api_keys()
    if provider not in keys.providers():
        return 404, {"ok": False, "error": "UNKNOWN_PROVIDER"}
    return 200, {"ok": True, "verify": keys.verify(provider)}


def secret_values() -> tuple[str, ...]:
    """Every configured key, for literal redaction. Never raises; never persist it."""
    try:
        return tuple(api_keys().secret_values())
    except Exception:  # noqa: BLE001
        return ()


def scrub(text: str) -> str:
    for value in secret_values():
        text = text.replace(value, "[REDACTED]")
    return text


def session_additions(env: Mapping[str, str]) -> dict[str, str]:
    """Stored keys for a new session, each only if ``env`` does not export it."""
    try:
        return dict(api_keys().session_env(env))
    except Exception:  # noqa: BLE001 - a broken store never stops a session
        return {}


__all__ = ["MODULE_NAME", "MAX_BODY_BYTES", "api_keys", "status_payload", "store", "clear",
           "verify", "secret_values", "scrub", "session_additions"]
