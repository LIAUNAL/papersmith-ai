"""Per-user API keys for the literature connectors: Ai2's Asta and OpenAlex.

Both services answer without a key; a key buys Asta's searches (they stall
without one) and OpenAlex a larger daily budget. The operator gives each key
once — in the dashboard's API keys panel or with ``smith keys set`` — and it is
kept outside every workspace, where no commit, archive or export can reach it:
``$XDG_CONFIG_HOME/papersmith/keys/<provider>`` (``~/.config/...`` by default;
directory ``0700``, file ``0600``), beside the remote-MCP token an earlier
release kept there.

One implementation for three interpreters. The skill scripts run under the
workspace's bare Python, the dashboard under the workspace environment, and
``smith`` in its own venv; the only tree all three reach is the kit's
``skills/``, so this file is standard library only and every consumer loads it
by path under one module name (``papersmith_api_keys``).

Rules every function keeps:

* an exported variable (:data:`PROVIDERS` ``env``) wins over the stored file,
  exactly as for the remote-MCP token; a blank or malformed one does not count;
* a stored file is used only when it is a regular file this user owns, mode
  ``0600``, in a directory that is not a symlink — the checks and wording of
  the remote-MCP token's own check in ``papersmith.core`` (a test holds them
  equal);
* no function returns, prints or logs a key except :func:`read` and
  :func:`session_env`, whose callers send it only to the service it belongs
  to; :func:`status` says *whether* and *from where*, never *what*;
* :func:`read` never raises: a consumer without a usable key behaves exactly
  as it did before keys existed.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

#: Bumped when a consumer-visible function changes shape.
API_VERSION = 1
#: Moves the store; for tests and CI only (the suite must never read the
#: operator's own keys).
STORE_DIR_ENV = "PAPERSMITH_KEYS_DIR"

PROVIDERS: dict[str, dict[str, str]] = {
    "asta": {
        "env": "ASTA_API_KEY",
        "label": "Asta (Ai2, Semantic Scholar corpus)",
        "unlocks": "Asta searches for discovery, resolution and journal-finder; "
                   "without it Asta is skipped and OpenAlex answers as before",
        "request_url": "https://share.hsforms.com/1L4hUh20oT3mu8iXJQMV77w3ioxm",
        "license_url": "https://allenai.org/asta-corpus-license",
        "license": "Asta Scientific Corpus Tool License: academic and non-commercial use only; "
                   "acknowledge Ai2's Asta in what you publish; never share the key.",
    },
    "openalex": {
        "env": "OPENALEX_API_KEY",
        "label": "OpenAlex",
        "unlocks": "a larger daily OpenAlex budget for resolution, journal-finder and citation ranks",
        "request_url": "https://openalex.org/settings/api-key",
        "license_url": "",
        "license": "",
    },
}

MIN_KEY_CHARS = 8
MAX_KEY_CHARS = 512
#: Largest stored file read; a key is far shorter.
MAX_FILE_BYTES = 4096

#: The wall time of one verify, every attempt included: an Asta lookup left
#: silent for ``asta_protocol.LOOKUP_ATTEMPT_SECONDS`` is asked again.
VERIFY_DEADLINE_SECONDS = 30.0
VERIFY_READ_TIMEOUT_SECONDS = 10.0
#: A paper Asta holds: answered in under a second keyless, and keyed in under
#: a second or after 30 s or more (2026-11-11), hence the repeated attempts.
ASTA_VERIFY_PAPER = "DOI:10.1088/1741-2552/aace8c"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
USER_AGENT = "papersmith-ai (api-keys verify)"

#: Why a key could not be stored, as :attr:`KeyRefused.code`.
REFUSAL_CODES = ("UNKNOWN_PROVIDER", "EMPTY", "TOO_SHORT", "TOO_LONG", "BAD_CHARACTERS",
                 "INSECURE_DIRECTORY", "NOT_A_FILE", "WRITE_FAILED")


class KeyRefused(ValueError):
    """A refused store, clear or lookup. Its message never holds a key."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _posix() -> bool:
    return os.name != "nt"


def providers() -> tuple[str, ...]:
    return tuple(PROVIDERS)


def _provider(provider: str) -> dict[str, str]:
    try:
        return PROVIDERS[provider]
    except (KeyError, TypeError):
        raise KeyRefused("UNKNOWN_PROVIDER",
                         f"unknown provider; expected one of {', '.join(PROVIDERS)}") from None


def env_var(provider: str) -> str:
    return _provider(provider)["env"]


def store_dir() -> Path:
    """Where keys are stored, read on every call (tests move it)."""
    override = os.environ.get(STORE_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME", "").strip() or str(Path.home() / ".config")
    return Path(base).expanduser() / "papersmith" / "keys"


def path(provider: str) -> Path:
    _provider(provider)
    return store_dir() / provider


def file_problem(file: Path) -> str | None:
    """Why ``file`` may not be used, or ``None`` when it may.

    Same checks and wording as the remote-MCP token's check in ``papersmith.core``.
    """
    try:
        info = file.lstat()
    except FileNotFoundError:
        return "absent"
    except OSError as exc:
        return f"unreadable ({exc.strerror})"
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return "insecure: not a regular file"
    if _posix():
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            return "insecure: owned by another user"
        if stat.S_IMODE(info.st_mode) & 0o077:
            return f"insecure: mode {stat.S_IMODE(info.st_mode):04o}, expected 0600"
        if file.parent.is_symlink():
            return "insecure: its directory is a symlink"
    return None


def validate(value: str) -> str:
    """``value`` stripped, or :class:`KeyRefused` naming what is wrong with it.

    Printable ASCII without spaces (``0x21``-``0x7e``), :data:`MIN_KEY_CHARS` to
    :data:`MAX_KEY_CHARS` characters: what an HTTP header and a query parameter
    carry safely. The message describes the rule, never the value.
    """
    if not isinstance(value, str):
        raise KeyRefused("EMPTY", "no key given")
    value = value.strip()
    if not value:
        raise KeyRefused("EMPTY", "no key given")
    if len(value) < MIN_KEY_CHARS:
        raise KeyRefused("TOO_SHORT", f"a key has at least {MIN_KEY_CHARS} characters")
    if len(value) > MAX_KEY_CHARS:
        raise KeyRefused("TOO_LONG", f"a key has at most {MAX_KEY_CHARS} characters")
    if any(not 0x21 <= ord(character) <= 0x7E for character in value):
        raise KeyRefused("BAD_CHARACTERS",
                         "a key is printable ASCII with no spaces or line breaks")
    return value


def _valid(value: str | None) -> str | None:
    try:
        return validate(value) if value is not None else None
    except KeyRefused:
        return None


def _env_value(provider: str) -> str | None:
    return _valid(os.environ.get(env_var(provider)))


def _env_problem(provider: str) -> str | None:
    raw = os.environ.get(env_var(provider))
    if raw is None:
        return None
    if not raw.strip():
        return "blank"
    return None if _valid(raw) else "invalid"


def _stored_value(provider: str) -> str | None:
    """The stored key, only from a private regular file this user owns."""
    file = path(provider)
    if file_problem(file) is not None:
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(file, flags)
    except OSError:
        return None
    try:
        # Checked again on the open descriptor: a file swapped in between the
        # lstat above and the open is caught here.
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return None
        if _posix() and (stat.S_IMODE(info.st_mode) & 0o077
                         or (hasattr(os, "getuid") and info.st_uid != os.getuid())):
            return None
        raw = os.read(fd, MAX_FILE_BYTES + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    if len(raw) > MAX_FILE_BYTES:
        return None
    try:
        return _valid(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return None


def read(provider: str) -> str | None:
    """The key to send to ``provider``, or ``None``. Never raises."""
    try:
        return _env_value(provider) or _stored_value(provider)
    except Exception:  # noqa: BLE001 - a consumer without a key works as before
        return None


def configured(provider: str) -> bool:
    return read(provider) is not None


def source(provider: str) -> str:
    """``env``, ``store`` or ``none``: where :func:`read` finds the key."""
    try:
        if _env_value(provider):
            return "env"
        if _stored_value(provider):
            return "store"
    except Exception:  # noqa: BLE001
        pass
    return "none"


def status(provider: str) -> dict[str, Any]:
    """Whether ``provider`` has a key and from where. Never the key itself."""
    meta = _provider(provider)
    file = path(provider)
    problem = file_problem(file)
    stored = problem is None and _stored_value(provider) is not None
    where = source(provider)
    return {
        "provider": provider,
        "label": meta["label"],
        "unlocks": meta["unlocks"],
        "env": meta["env"],
        "configured": where != "none",
        "source": where,
        "stored": stored,
        "shadowed": stored and where == "env",
        # "absent" is not a problem; an unusable file is.
        "problem": None if problem in (None, "absent") else problem,
        "env_problem": _env_problem(provider),
        "path": str(file),
        "override": bool(os.environ.get(STORE_DIR_ENV, "").strip()),
        "request_url": meta["request_url"],
        "license_url": meta["license_url"],
        "license": meta["license"],
    }


def statuses() -> list[dict[str, Any]]:
    return [status(provider) for provider in PROVIDERS]


def _private_directory(directory: Path) -> None:
    """Create ``directory`` 0700 and refuse one that is a symlink or not ours."""
    if directory.is_symlink():
        raise KeyRefused("INSECURE_DIRECTORY", f"{directory} is a symlink; refusing to store a key through it")
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = directory.lstat()
    except OSError as exc:
        raise KeyRefused("WRITE_FAILED", f"could not create {directory}: {exc.strerror}") from None
    if not stat.S_ISDIR(info.st_mode):
        raise KeyRefused("INSECURE_DIRECTORY", f"{directory} is not a directory")
    if _posix():
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise KeyRefused("INSECURE_DIRECTORY", f"{directory} belongs to another user")
        try:
            os.chmod(directory, 0o700)
        except OSError as exc:
            raise KeyRefused("WRITE_FAILED", f"could not restrict {directory}: {exc.strerror}") from None


def store(provider: str, value: str) -> Path:
    """Store ``value`` for ``provider``: validated, atomic, mode 0600."""
    _provider(provider)
    key = validate(value)
    directory = store_dir()
    _private_directory(directory)
    target = directory / provider
    if target.is_dir() and not target.is_symlink():
        raise KeyRefused("NOT_A_FILE", f"{target} is a directory; remove it by hand")
    try:
        fd, temporary = tempfile.mkstemp(dir=directory, prefix=f".{provider}.", suffix=".tmp")
    except OSError as exc:
        raise KeyRefused("WRITE_FAILED", f"could not write in {directory}: {exc.strerror}") from None
    try:
        if _posix():
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(key + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        # Replaces a symlink at `target` with the file; never writes through it.
        os.replace(temporary, target)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise KeyRefused("WRITE_FAILED", f"could not write {target}: {exc.strerror}") from None
    return target


def clear(provider: str) -> bool:
    """Remove the stored key (a file or a symlink, never followed)."""
    target = path(provider)
    if target.is_dir() and not target.is_symlink():
        raise KeyRefused("NOT_A_FILE", f"{target} is a directory; remove it by hand")
    if not (target.is_symlink() or target.exists()):
        return False
    try:
        target.unlink()
    except OSError as exc:
        raise KeyRefused("WRITE_FAILED", f"could not remove {target}: {exc.strerror}") from None
    return True


def secret_values() -> tuple[str, ...]:
    """Every usable key (exported or stored), longest first, for literal
    redaction. Never persist the result."""
    found: set[str] = set()
    for provider in PROVIDERS:
        for value in (_env_value(provider), _stored_value(provider)):
            if value and len(value) >= MIN_KEY_CHARS:
                found.add(value)
    return tuple(sorted(found, key=lambda value: (-len(value), value)))


def scrub(text: str, replacement: str = "[REDACTED]") -> str:
    for value in secret_values():
        text = text.replace(value, replacement)
    return text


def session_env(base: Mapping[str, str]) -> dict[str, str]:
    """Variables to add to a session started with ``base``: each stored key
    whose variable ``base`` does not already export (an export wins)."""
    additions: dict[str, str] = {}
    for provider, meta in PROVIDERS.items():
        if (base.get(meta["env"]) or "").strip():
            continue
        value = _stored_value(provider)
        if value:
            additions[meta["env"]] = value
    return additions


def export_command(provider: str, shell: str) -> str:
    """The line that exports ``provider``'s stored key in ``shell``: it names
    the file, never the key."""
    variable, file = env_var(provider), path(provider)
    if shell == "powershell":
        return f'$env:{variable} = Get-Content "{file}"'
    if shell == "fish":
        return f'set -gx {variable} (cat "{file}")'
    return f'export {variable}="$(cat "{file}")"'


# --------------------------------------------------------------------------
# verify: one explicit, read-only call per provider
# --------------------------------------------------------------------------
class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Follow no redirect: the request carries the key, and a redirect would
    hand it to whatever host ``Location`` names (#106)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


_OPENER = urllib.request.build_opener(_RefuseRedirects)


def _asta_protocol():
    name = "papersmith_asta_protocol"
    module = sys.modules.get(name)
    if module is None:
        source_file = Path(__file__).resolve().parent / "literature" / "asta_protocol.py"
        spec = importlib.util.spec_from_file_location(name, source_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {source_file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return module


def _result(provider: str, state: str, detail: str, origin: str, started: float,
            budget: dict[str, str] | None = None) -> dict[str, Any]:
    return {"provider": provider, "state": state, "detail": detail, "source": origin,
            "budget": budget, "elapsed_ms": int((time.monotonic() - started) * 1000)}


def _verify_asta(key: str, url: str | None, deadline: float, started: float,
                 origin: str) -> dict[str, Any]:
    protocol = _asta_protocol()
    endpoint, body, headers = protocol.request(
        "get_paper", {"paper_id": ASTA_VERIFY_PAPER, "fields": "title,year"},
        key=key, endpoint=url or protocol.ENDPOINT)
    until = started + deadline
    attempts = 0
    while True:
        attempts += 1
        request = urllib.request.Request(endpoint, data=body, method="POST",
                                         headers={"User-Agent": USER_AGENT, **headers})
        now = time.monotonic()
        # A keyed lookup answers within a second or only after 30 s or more:
        # one silent this long is asked again, until the deadline.
        attempt_until = min(until, now + protocol.LOOKUP_ATTEMPT_SECONDS)
        try:
            timeout = max(0.1, min(VERIFY_READ_TIMEOUT_SECONDS, attempt_until - now))
            with _OPENER.open(request, timeout=timeout) as response:
                message = protocol.read_message(response.readline, deadline=attempt_until)
            protocol.tool_texts(message)
        except protocol.AstaError as exc:
            if exc.kind == protocol.REFUSED:
                return _result("asta", "refused", "Asta refused the key", origin, started)
            if exc.kind == protocol.NOT_FOUND:
                return _result("asta", "ok", "key accepted", origin, started)
            if not exc.timed_out:
                return _result("asta", "unreachable", _short(exc.detail), origin, started)
            reason = exc.detail
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                return _result("asta", "refused", f"HTTP {exc.code}", origin, started)
            if 300 <= exc.code < 400:
                return _result("asta", "unreachable", f"HTTP {exc.code}: redirect refused", origin, started)
            return _result("asta", "unreachable", f"HTTP {exc.code}", origin, started)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if not _timed_out(exc):
                return _result("asta", "unreachable", _reason(exc), origin, started)
            reason = _reason(exc)
        else:
            return _result("asta", "ok", "key accepted", origin, started)
        if until - time.monotonic() < 0.5:
            return _result("asta", "unreachable", f"{_short(reason)} ({attempts} attempts in "
                           f"{deadline:g} s)", origin, started)


def _timed_out(exc: BaseException) -> bool:
    """A read or a connection that ran out of time, not a refusal."""
    return isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)


def _verify_openalex(key: str, url: str | None, started: float, deadline: float,
                     origin: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"per-page": "1", "select": "id", "api_key": key})
    request = urllib.request.Request(f"{url or OPENALEX_WORKS_URL}?{query}",
                                     headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        timeout = max(0.1, min(VERIFY_READ_TIMEOUT_SECONDS, deadline))
        with _OPENER.open(request, timeout=timeout) as response:
            headers = response.headers
            response.read(65536)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return _result("openalex", "refused", f"HTTP {exc.code}: OpenAlex refused the key",
                           origin, started)
        if 300 <= exc.code < 400:
            return _result("openalex", "unreachable", f"HTTP {exc.code}: redirect refused", origin, started)
        return _result("openalex", "unreachable", f"HTTP {exc.code}", origin, started)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return _result("openalex", "unreachable", _reason(exc), origin, started)
    budget = {name: headers.get(f"x-ratelimit-{name}-usd")
              for name in ("remaining", "limit") if headers.get(f"x-ratelimit-{name}-usd")}
    return _result("openalex", "ok", "key accepted", origin, started,
                   budget={"remaining_usd": budget.get("remaining"), "limit_usd": budget.get("limit")}
                   if budget else None)


def _short(text: str) -> str:
    return " ".join(str(text).split())[:160]


def _reason(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None) or exc
    return _short(f"unreachable: {type(reason).__name__ if not str(reason) else reason}")


def verify(provider: str, value: str | None = None, *, url: str | None = None,
           deadline: float = VERIFY_DEADLINE_SECONDS) -> dict[str, Any]:
    """Ask ``provider`` whether a key works: one read-only call, no redirect.

    ``value`` verifies a key before it is stored; otherwise the configured one.
    ``url`` is a test seam. The result never carries the key, the URL or a
    response body: ``{provider, state: ok|refused|unreachable|unconfigured,
    detail, source, budget, elapsed_ms}``.
    """
    _provider(provider)
    started = time.monotonic()
    if value is not None:
        key, origin = validate(value), "given"
    else:
        key, origin = read(provider), source(provider)
    if not key:
        return _result(provider, "unconfigured", "no key configured", "none", started)
    if provider == "asta":
        outcome = _verify_asta(key, url, deadline, started, origin)
    else:
        outcome = _verify_openalex(key, url, started, deadline, origin)
    outcome["detail"] = _short(outcome["detail"].replace(key, "<redacted>"))
    return outcome


__all__ = ["API_VERSION", "STORE_DIR_ENV", "PROVIDERS", "KeyRefused", "providers", "env_var",
           "store_dir", "path", "file_problem", "validate", "read", "configured", "source", "status",
           "statuses", "store", "clear", "secret_values", "scrub", "session_env", "export_command",
           "verify"]
