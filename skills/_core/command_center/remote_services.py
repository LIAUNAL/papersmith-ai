"""The remote services the Experiments tab lists, probed offline.

``remote_services(root)`` answers one row per service the remote path of a
proof of concept or a full experiment depends on: the official Kaggle MCP
server, the official ``kaggle`` CLI, the account token both read, the worker
accounts the ``kaggle-accounts`` skill stores, the rehearsal evidence the
``remote-execution`` skill writes, the weekly GPU quota, and then Colab: the
official ``colab`` CLI, the official Colab MCP registration, the team's Colab
accounts, the owners a split campaign may use, and the team as a whole.

The team comes from ``.papersmith/team.json`` (one account per person and
service). Only owner slugs, display names, the declared Kaggle username and
the Colab tier leave it. A member's Colab ``configDir`` is checked for
existence only, never listed or opened (it holds the CLI's credentials), and
the accounts store answers one yes/no per declared username. Parallelism
counts distinct owners; a ``free`` Colab account is never a campaign worker.

Nothing here touches the network: the dashboard polls this view, and a probe
that reached the service on every poll would be slow and would spend the
operator's rate limit. The quota is therefore always "unverified" and its row
names the command that reads it. The one subprocess (``kaggle --version``) has
a short timeout and is cached per server process for ``VERSION_TTL`` seconds.

Every probe is bounded and never raises: a probe that fails becomes an
"unverified" row. The token is never returned, and the accounts store is
reduced to a count, never a username. Each row's action is a constant from
``ACTIONS``, never text read from a workspace file, because the dashboard
types it into the CLI assistant.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .state_extractor import credentials_store
from .terminal import (COLAB_CLI_INSTALL, COLAB_COMMANDS, COLAB_MCP_SERVER, COLAB_PAID_TIERS,
                       REMOTE_MCP_TOKEN_ENV, find_executable, registered_mcp_files, remote_mcp_status)

#: Row states; the panel maps them to "activo", "inactivo", "no instalado"
#: and "sin verificar".
STATES = ("active", "inactive", "missing", "unverified")

MCP_URL = "https://www.kaggle.com/mcp"
CLI_NAME = "kaggle"

#: The only commands a row may offer. Typed by the dashboard into the CLI
#: assistant, so they are constants here and never read from the workspace.
ACTIONS = {
    "activate": "smith mcp kaggle activate",
    "verify": "smith mcp kaggle status --verify",
    "install_cli": "pipx install kaggle",
    "validate_accounts": "/kaggle-accounts validate",
    "install_colab_cli": COLAB_CLI_INSTALL,
    "colab_status": COLAB_COMMANDS["status"],
    "team_list": COLAB_COMMANDS["team_list"],
}

COLAB_CLI_NAME = "colab"
COLAB_TIERS = ("free", *COLAB_PAID_TIERS)
TEAM_FILE = Path(".papersmith") / "team.json"
#: The empty team table names this; the placeholders are literal.
TEAM_ADD_COMMAND = 'smith team add --owner <slug> --name "<Nombre>" --attest ...'
MAX_TEAM_BYTES = 256 * 1024
MAX_MEMBERS = 64
_OWNER = re.compile(r"[a-z0-9-]{1,40}")

VERSION_TTL = 300.0
VERSION_TIMEOUT = 3.0
MAX_STORE_BYTES = 1024 * 1024
MAX_JOBS = 500
MAX_SMOKE_FILES = 200
MAX_SMOKE_BYTES = 256 * 1024
MAX_TEXT = 120

_JOB_GLOBS = ("implementations/*/tools/*/*/run-config.json",
              "implementations/*/*/tools/*/*/run-config.json")
_SMOKE_GLOBS = ("implementations/*/.remote-execution/smoke.jsonl",
                "implementations/*/*/.remote-execution/smoke.jsonl")
_SMOKE_RESULT_KIND = "smokeResult"

_version_cache: dict[str, tuple[float, str | None]] = {}
_version_lock = threading.Lock()
_version_refreshing: set[str] = set()


def clear_cache() -> None:
    """Forget every cached CLI version (tests, or a fresh install)."""
    with _version_lock:
        _version_cache.clear()


def _action(key: str, label: str) -> dict[str, str]:
    return {"command": ACTIONS[key], "label": label}


def _row(row_id: str, service: str, purpose: str, state: str, detail: str,
         action: dict[str, str] | None, **extra: Any) -> dict[str, Any]:
    return {"id": row_id, "service": service, "purpose": purpose, "state": state,
            "detail": detail, "action": action, **extra}


def _run_version(executable: str) -> str | None:
    try:
        done = subprocess.run([executable, "--version"], capture_output=True, text=True,
                              timeout=VERSION_TIMEOUT, check=False)
        text = (done.stdout or done.stderr or "").strip().splitlines()
        return text[0][:MAX_TEXT] if text else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _refresh_version(executable: str) -> None:
    try:
        version = _run_version(executable)
        with _version_lock:
            _version_cache[executable] = (time.monotonic(), version)
    finally:
        with _version_lock:
            _version_refreshing.discard(executable)


def _cli_version(executable: str) -> str | None:
    """``<executable> --version``, cached; an expired answer is served while
    a background run replaces it, so the panel never waits on a CLI twice."""
    now = time.monotonic()
    with _version_lock:
        cached = _version_cache.get(executable)
        if cached and now - cached[0] < VERSION_TTL:
            return cached[1]
        if cached:
            if executable not in _version_refreshing:
                _version_refreshing.add(executable)
                threading.Thread(target=_refresh_version, args=(executable,),
                                 name="cli-version", daemon=True).start()
            return cached[1]
    version = _run_version(executable)
    with _version_lock:
        _version_cache[executable] = (now, version)
    return version


def _mcp_row(status: dict[str, Any]) -> dict[str, Any]:
    registered = [str(item) for item in status.get("registered") or []]
    activated = bool(status.get("activated"))
    if not registered:
        state, detail = "missing", "No registrado en los archivos MCP del proyecto (smith upgrade lo registra)."
    elif activated:
        state, detail = "active", f"Registrado en {', '.join(registered)}; token activo."
    else:
        state, detail = "inactive", f"Registrado en {', '.join(registered)}; falta el token de cuenta."
    action = _action("verify", "Verificar") if activated else _action("activate", "Activar")
    return _row("mcp", f"MCP oficial ({MCP_URL})",
                "Buscar datasets y notebooks, lanzar y monitorear desde el agente.",
                state, detail, action)


def _token_row(status: dict[str, Any]) -> dict[str, Any]:
    if status.get("activated"):
        where = f"variable {REMOTE_MCP_TOKEN_ENV}" if status.get("source") == "env" else "~/.kaggle/access_token"
        state, detail, action = "active", f"Token presente ({where}).", None
    else:
        problem = status.get("problem")
        detail = ("El archivo del token tiene permisos inseguros." if problem == "insecure"
                  else f"Sin token en ~/.kaggle/access_token ni en {REMOTE_MCP_TOKEN_ENV}.")
        state, action = "inactive", _action("activate", "Activar")
    return _row("token", "Token de cuenta", "Autentica el MCP, la CLI y el SDK oficiales.",
                state, detail, action)


def _cli_row() -> dict[str, Any]:
    purpose = "Empujar kernels y descargar salidas desde la terminal."
    executable = find_executable(CLI_NAME)
    if not executable:
        return _row("cli", f"CLI oficial ({CLI_NAME})", purpose, "missing",
                    "No se encontró en el PATH.", _action("install_cli", "Instalar"))
    version = _cli_version(executable)
    detail = f"{version} en {executable}" if version else f"Encontrado en {executable} (versión no leída)."
    return _row("cli", f"CLI oficial ({CLI_NAME})", purpose, "active", detail[:2 * MAX_TEXT], None)


def _accounts_row(root: Path) -> dict[str, Any]:
    purpose = "Cuentas worker para repartir ejecuciones remotas."
    action = _action("validate_accounts", "Validar cuentas")
    store = credentials_store(root)
    if store is None:
        return _row("accounts", "Cuentas worker", purpose, "missing",
                    "La skill de cuentas no está instalada en este proyecto.", action, count=0)
    count = 0
    try:
        if store.is_file() and store.stat().st_size <= MAX_STORE_BYTES:
            data = json.loads(store.read_text(encoding="utf-8"))
            accounts = data.get("accounts") if isinstance(data, dict) else None
            count = len(accounts) if isinstance(accounts, list) else 0
    except (OSError, ValueError):
        count = 0
    if count:
        return _row("accounts", "Cuentas worker", purpose, "active",
                    f"{count} cuenta(s) guardada(s); valida que autentican.", action, count=count)
    return _row("accounts", "Cuentas worker", purpose, "inactive",
                "Sin cuentas guardadas.", action, count=0)


def _bounded_glob(root: Path, patterns: tuple[str, ...], cap: int) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        for path in root.glob(pattern):
            if len(found) >= cap:
                return found
            if path.is_file() and not path.is_symlink():
                found.append(path)
    return found


def _smoke_passed(path: Path) -> bool:
    """Whether the latest rehearsal verdict in one ``smoke.jsonl`` is a pass."""
    try:
        with path.open("rb") as handle:
            size = path.stat().st_size
            handle.seek(max(0, size - MAX_SMOKE_BYTES))
            lines = handle.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return False
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("kind") == _SMOKE_RESULT_KIND:
            return event.get("result") == "pass"
    return False


def _rehearsals_row(root: Path) -> dict[str, Any]:
    jobs = len(_bounded_glob(root, _JOB_GLOBS, MAX_JOBS))
    passed = sum(1 for path in _bounded_glob(root, _SMOKE_GLOBS, MAX_SMOKE_FILES) if _smoke_passed(path))
    if passed:
        state, detail = "active", f"{passed} ensayo(s) aprobado(s); {jobs} trabajo(s) generado(s)."
    elif jobs:
        state, detail = "inactive", f"{jobs} trabajo(s) generado(s), sin ensayo aprobado."
    else:
        state, detail = "inactive", "Sin trabajos generados."
    return _row("rehearsals", "Ensayos remotos",
                "Evidencia smoke que habilita un lanzamiento (remote_cli readiness).",
                state, detail, None, jobs=jobs, passed=passed)


_LEDGER_GLOBS = ("implementations/*/.remote-execution/ledger.jsonl",
                 "implementations/*/*/.remote-execution/ledger.jsonl")
MAX_LEDGERS = 200


def launch_evidence(root: Path | str) -> dict[str, int]:
    """Counts of the remote path's evidence on disk: generated jobs, passed
    rehearsals, and ledgers holding at least one recorded event (a submit
    reached the ledger). Bounded; never raises."""
    root = Path(root)
    try:
        jobs = len(_bounded_glob(root, _JOB_GLOBS, MAX_JOBS))
        smokes = _bounded_glob(root, _SMOKE_GLOBS, MAX_SMOKE_FILES)
        passed = sum(1 for path in smokes if _smoke_passed(path))
        ledgers = 0
        for path in _bounded_glob(root, _LEDGER_GLOBS, MAX_LEDGERS):
            try:
                with path.open("rb") as handle:
                    ledgers += bool(handle.read(MAX_SMOKE_BYTES).strip())
            except OSError:
                continue
        return {"jobs": jobs, "smokes": len(smokes), "rehearsals_passed": passed, "launched": ledgers}
    except Exception:  # noqa: BLE001 - evidence that cannot be read is no evidence
        return {"jobs": 0, "smokes": 0, "rehearsals_passed": 0, "launched": 0}


def _quota_row() -> dict[str, Any]:
    return _row("quota", "Cuota GPU semanal", "Horas de GPU disponibles esta semana.",
                "unverified", "No se consulta en cada sondeo (requiere red).",
                _action("verify", "Leer cuota"))


def _colab_cli_row() -> dict[str, Any]:
    purpose = "Ejecución sin interfaz (headless) en Colab, por la ruta de remote-execution."
    executable = find_executable(COLAB_CLI_NAME)
    if not executable:
        return _row("colab_cli", f"CLI oficial de Colab ({COLAB_CLI_NAME})", purpose, "missing",
                    "No instalado: instala la versión fijada que documenta remote-execution.",
                    _action("install_colab_cli", "Instalar"))
    version = _cli_version(executable)
    detail = f"{version} en {executable}" if version else f"Encontrado en {executable} (versión no leída)."
    return _row("colab_cli", f"CLI oficial de Colab ({COLAB_CLI_NAME})", purpose, "active",
                detail[:2 * MAX_TEXT], _action("colab_status", "Comprobar"))


def _colab_mcp_row(root: Path) -> dict[str, Any]:
    purpose = "Trabajo interactivo: el agente maneja un cuaderno de Colab abierto en el navegador."
    registered = registered_mcp_files(root, COLAB_MCP_SERVER)
    if registered:
        return _row("colab_mcp", "MCP oficial de Colab", purpose, "active",
                    f"Registrado en {', '.join(registered)}; necesita el cuaderno abierto en el navegador.",
                    None, badge="registrado")
    return _row("colab_mcp", "MCP oficial de Colab", purpose, "inactive",
                "No registrado en los archivos MCP del proyecto (smith upgrade lo registra); "
                "necesita un cuaderno abierto en el navegador.", None, badge="no registrado")


def _store_usernames(root: Path) -> set[str]:
    store = credentials_store(root)
    try:
        if store is None or not store.is_file() or store.stat().st_size > MAX_STORE_BYTES:
            return set()
        data = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, list):
        return set()
    return {entry["username"] for entry in accounts
            if isinstance(entry, dict) and isinstance(entry.get("username"), str)}


def _text(value: Any, limit: int = MAX_TEXT) -> str | None:
    return value.strip()[:limit] or None if isinstance(value, str) else None


def _config_present(value: Any) -> bool:
    """Whether a member's Colab config directory exists: one stat, never a listing."""
    if not isinstance(value, str) or not value.strip():
        return False
    path = Path(value.strip()).expanduser()
    try:
        return path.is_absolute() and path.is_dir()
    except OSError:
        return False


def team_members(root: Path | str) -> dict[str, Any]:
    """The team registry reduced to what the table shows; never raises."""
    root = Path(root)
    out: dict[str, Any] = {"file": TEAM_FILE.as_posix(), "present": False, "problem": None,
                           "members": [], "skipped": 0, "add_command": TEAM_ADD_COMMAND}
    path = root / TEAM_FILE
    try:
        if not path.is_file() or path.is_symlink():
            return out
        out["present"] = True
        if path.stat().st_size > MAX_TEAM_BYTES:
            out["problem"] = "too_large"
            return out
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        out["problem"] = "invalid"
        return out
    members = data.get("members") if isinstance(data, dict) else None
    if not isinstance(members, list) or data.get("schema") != 1:
        out["problem"] = "invalid"
        return out
    stored = _store_usernames(root)
    seen: set[str] = set()
    for entry in members[:MAX_MEMBERS]:
        owner = entry.get("owner") if isinstance(entry, dict) else None
        if not isinstance(owner, str) or not _OWNER.fullmatch(owner) or owner in seen:
            out["skipped"] += 1
            continue
        seen.add(owner)
        accounts = entry.get("accounts") if isinstance(entry.get("accounts"), dict) else {}
        kaggle = accounts.get("kaggle") if isinstance(accounts.get("kaggle"), dict) else None
        colab = accounts.get("colab") if isinstance(accounts.get("colab"), dict) else None
        username = _text(kaggle.get("username"), 80) if kaggle else None
        tier = colab.get("tier") if colab else None
        tier = tier if tier in COLAB_TIERS else ("unknown" if colab else None)
        validated = (username in stored) if username else None
        eligible = [service for service, ok in (("kaggle", bool(validated)),
                                                 ("colab", tier in COLAB_PAID_TIERS)) if ok]
        out["members"].append({
            "owner": owner, "display_name": _text(entry.get("displayName"), 80),
            "kaggle_username": username, "kaggle_validated": validated,
            "colab_tier": tier, "colab_config_present": _config_present(colab.get("configDir")) if colab else None,
            "eligible": eligible,
        })
    out["skipped"] += max(0, len(members) - MAX_MEMBERS)
    # The remote backends refuse a registry with a repeated or malformed owner
    # or one Kaggle username under two owners, so the dashboard must not call
    # it ready either: one account per person is the rule both enforce.
    usernames = [m["kaggle_username"].lower() for m in out["members"] if m["kaggle_username"]]
    if out["skipped"] or len(usernames) != len(set(usernames)):
        out["problem"] = "rejected"
    return out


def _team_rows(team: dict[str, Any]) -> list[dict[str, Any]]:
    list_action = _action("team_list", "Ver equipo")
    purposes = {"colab_accounts": "Una cuenta Colab por persona del equipo.",
                "colab_eligible": "Propietarios con cómputo de pago: pueden repartir una campaña.",
                "team": "Personas distintas: el paralelismo cuenta propietarios, no cuentas."}
    services = {"colab_accounts": "Cuentas Colab del equipo", "colab_eligible": "Elegibles para campañas",
                "team": "Equipo"}
    if team["problem"]:
        detail = f"{team['file']} no se pudo leer; revisa con smith team list."
        return [_row(row_id, services[row_id], purposes[row_id], "unverified", detail, list_action)
                for row_id in ("colab_accounts", "colab_eligible", "team")]
    members = team["members"]
    colab = [m for m in members if m["colab_tier"]]
    paid = [m["owner"] for m in colab if m["colab_tier"] in COLAB_PAID_TIERS]
    free = sum(1 for m in colab if m["colab_tier"] == "free")
    kaggle = sum(1 for m in members if m["kaggle_username"])
    if colab:
        accounts = _row("colab_accounts", services["colab_accounts"], purposes["colab_accounts"], "active",
                        f"{len(colab)} cuenta(s): {len(paid)} de pago, {free} gratuita(s).", list_action,
                        count=len(colab), paid=len(paid), free=free)
    else:
        accounts = _row("colab_accounts", services["colab_accounts"], purposes["colab_accounts"], "inactive",
                        "Sin cuentas Colab en el equipo.", list_action, count=0, paid=0, free=0)
    if paid:
        shown = ", ".join(paid[:12]) + (" …" if len(paid) > 12 else "")
        eligible = _row("colab_eligible", services["colab_eligible"], purposes["colab_eligible"], "active",
                        f"{len(paid)} propietario(s) de pago: {shown}. Las gratuitas solo para trabajo "
                        "interactivo en una sesión.", _action("colab_status", "Comprobar"), owners=paid)
    else:
        eligible = _row("colab_eligible", services["colab_eligible"], purposes["colab_eligible"], "inactive",
                        "Ningún propietario con nivel de pago (pro, payg o enterprise): sin campañas "
                        "repartidas en Colab.", _action("colab_status", "Comprobar"), owners=[])
    state = "active" if members else "inactive"
    detail = (f"{len(members)} persona(s): {kaggle} con Kaggle, {len(colab)} con Colab."
              if members else f"Sin {team['file']}: cada persona se registra con smith team add.")
    whole = _row("team", services["team"], purposes["team"], state, detail, list_action,
                 owners=len(members), kaggle=kaggle, colab=len(colab))
    return [accounts, eligible, whole]


# --------------------------------------------------------------------------
# run hosts (read by run_options, which names no service itself)
# --------------------------------------------------------------------------
#: Host families a run may be placed on. Each id is the prefix of a timing
#: record's ``host`` (``local``, ``kaggle:<owner>``, ``colab:<owner>``).
RUN_HOSTS = ("local", "kaggle", "colab")
HOST_LABELS = {"local": "Local", "kaggle": "Kaggle", "colab": "Colab"}


def remote_host_readiness(services: Any, stage: str) -> dict[str, dict[str, Any]]:
    """Whether each remote host family can take ``stage`` (``poc`` or ``full``).

    Read from the rows ``remote_services`` already built, never re-probed.
    Kaggle needs an active token, the official CLI and at least one worker:
    when the team registry maps an owner to a Kaggle username, a worker is a
    mapped owner whose account is validated (one per owner, the rule the
    remote-execution backend applies); with no mapping, a stored account. Colab needs the official CLI and at least one team owner
    signed in (their config directory exists); a full run also needs one of
    them on a paid tier. Never raises.
    """
    services = services if isinstance(services, dict) else {}
    rows = {row.get("id"): row for row in services.get("rows") or [] if isinstance(row, dict)}
    team = services.get("team") if isinstance(services.get("team"), dict) else {}
    members = [m for m in team.get("members") or [] if isinstance(m, dict)]

    def active(row_id: str) -> bool:
        return (rows.get(row_id) or {}).get("state") == "active"

    # Same rule as the remote-execution backend: when the team registry maps
    # at least one owner to a Kaggle username, only those owners' validated
    # accounts are workers (one per owner); otherwise every stored account is.
    mapped = [m for m in members if m.get("kaggle_username")]
    if team.get("problem"):
        workers, worker_text = 0, "registro del equipo ilegible (smith team list)"
        counted = "0 propietario(s) con cuenta validada"
    elif mapped:
        workers = sum(1 for m in mapped if m.get("kaggle_validated") is True)
        counted = worker_text = f"{workers} propietario(s) con cuenta validada"
    else:
        stored = (rows.get("accounts") or {}).get("count")
        workers = stored if isinstance(stored, int) else 0
        counted = worker_text = (f"{workers} cuenta(s) worker guardada(s); sin propietarios Kaggle en el "
                                 "registro del equipo, cada cuenta guardada es un worker")
    gaps = [text for ok, text in ((active("token"), "sin token activo"),
                                  (active("cli"), "CLI oficial no instalada"),
                                  (workers >= 1, worker_text)) if not ok]
    kaggle = {"available": not gaps, "workers": workers,
              "reason": (f"Token activo, CLI oficial y {counted}." if not gaps
                         else "Kaggle: " + "; ".join(gaps) + ".")}
    signed = [m for m in members if m.get("colab_tier") and m.get("colab_config_present")]
    paid = [m for m in signed if m.get("colab_tier") in COLAB_PAID_TIERS]
    gaps = [] if active("colab_cli") else ["CLI oficial de Colab no instalada"]
    if not signed:
        gaps.append("ningún propietario del equipo con sesión iniciada")
    elif stage == "full" and not paid:
        gaps.append("ningún propietario con sesión en un nivel de pago (pro, payg o enterprise)")
    owners = len(paid) if stage == "full" else len(signed)
    colab = {"available": not gaps,
             "reason": (f"CLI oficial y {owners} propietario(s) con sesión"
                        f"{' en nivel de pago' if stage == 'full' else ''}." if not gaps
                        else "Colab: " + "; ".join(gaps) + ".")}
    return {"kaggle": kaggle, "colab": colab}


def _guarded(row_id: str, service: str, probe: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return probe()
    except Exception:  # noqa: BLE001 - a failing probe is a row, never an error
        return _row(row_id, service, "", "unverified", "No se pudo sondear.", None)


def remote_services(root: Path | str) -> dict[str, Any]:
    """One row per remote service, offline and bounded; never raises."""
    root = Path(root)
    try:
        status = remote_mcp_status(root)
    except Exception:  # noqa: BLE001
        status = None

    def from_status(build: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[], dict[str, Any]]:
        def probe() -> dict[str, Any]:
            if status is None:
                raise RuntimeError("status unavailable")
            return build(status)
        return probe

    rows = [
        _guarded("mcp", "MCP oficial", from_status(_mcp_row)),
        _guarded("cli", "CLI oficial", _cli_row),
        _guarded("token", "Token de cuenta", from_status(_token_row)),
        _guarded("accounts", "Cuentas worker", lambda: _accounts_row(root)),
        _guarded("rehearsals", "Ensayos remotos", lambda: _rehearsals_row(root)),
        _guarded("quota", "Cuota GPU semanal", _quota_row),
        _guarded("colab_cli", "CLI oficial de Colab", _colab_cli_row),
        _guarded("colab_mcp", "MCP oficial de Colab", lambda: _colab_mcp_row(root)),
    ]
    try:
        team = team_members(root)
    except Exception:  # noqa: BLE001 - never raises; the rows say so
        team = {"file": TEAM_FILE.as_posix(), "present": False, "problem": "invalid", "members": [],
                "skipped": 0, "add_command": TEAM_ADD_COMMAND}
    try:
        rows.extend(_team_rows(team))
    except Exception:  # noqa: BLE001
        rows.extend(_row(row_id, service, "", "unverified", "No se pudo sondear.", None)
                    for row_id, service in (("colab_accounts", "Cuentas Colab del equipo"),
                                            ("colab_eligible", "Elegibles para campañas"),
                                            ("team", "Equipo")))
    for row in rows:
        row["purpose"] = row["purpose"] or "—"
    note = ("Sondeo local sin red: la cuota y la autenticación de las cuentas se leen "
            "con su acción. La versión de la CLI se guarda en caché por 5 minutos.")
    return {"rows": rows, "note": note, "team": team}
