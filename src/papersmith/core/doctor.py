"""`smith doctor`: one table of project health rows for a workspace.

Every row is ``{area, item, state, detail}`` with ``state`` one of ``ok``,
``absent`` (an optional piece that is not there), ``warn`` or ``fail``; the
summary carries the worst state. The command is read-only and best-effort: a
missing tool, an unreadable backend or a damaged ledger becomes a row, never a
crash.

Rows come from two places, and the dashboard's ``GET /api/doctor`` builds the
same rows from the same function (:func:`build_report`):

* **Here, in the CLI's process**: the framework versions and drift (the
  machinery behind ``smith status`` and ``smith audit --check-drift``) and the
  external tools (``shutil.which`` plus the known TeX Live directories, so
  discovery works on macOS, Linux and Windows under WSL).
* **The backend payload**: the workspace interpreter's Python and packages,
  the wiring health (``health_inspector.get_wiring_health``: harness sync,
  skills, CLI front doors, agents) and the dashboard's phases. The CLI asks the
  workspace interpreter for it (``python -m
  skills._core.command_center.doctor_view <dir>``), the way ``smith ui`` runs
  the backend; the dashboard computes it in-process.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .. import __version__
from ..errors import PapersmithError, UserError
from . import fs, manifest
from .exit_codes import EXECUTION_ERROR, SUCCESS

#: Row states from best to worst; the summary is the worst one present.
STATES = ("ok", "absent", "warn", "fail")

#: Every area a report carries, in table order.
AREAS = ("framework", "packages", "tools", "skills", "agents", "flows")

#: Where TeX distributions put their binaries when PATH misses them: MacTeX's
#: symlink farm and TeX Live's per-year, per-platform trees (Linux, WSL).
TEX_DIRS = (
    "/Library/TeX/texbin",
    "/usr/local/texlive/*/bin/*",
    "/opt/texlive/*/bin/*",
    "~/texlive/*/bin/*",
)

#: ``(tool, group, state when missing, purpose)``. A group with no member
#: found adds one ``warn`` row of its own (``TeX engine``, ``rasterizer``).
TOOLS = (
    ("git", None, "warn", "version control"),
    ("node", None, "warn", "proposal-deliberation engine"),
    ("micromamba", None, "warn", "ingestion and experiment runtime"),
    ("latexmk", None, "absent", "paper build driver"),
    ("lualatex", "TeX engine", "absent", "TeX engine"),
    ("pdflatex", "TeX engine", "absent", "TeX engine"),
    ("pdftoppm", "rasterizer", "absent", "PDF rasterizer (poppler)"),
    ("pdftocairo", "rasterizer", "absent", "PDF rasterizer (poppler)"),
    ("gs", "rasterizer", "absent", "PDF rasterizer (Ghostscript)"),
    ("sips", "rasterizer", "absent", "PDF rasterizer (macOS only)"),
)

#: How long the CLI waits for the workspace interpreter's backend payload.
BACKEND_TIMEOUT_SECONDS = 180

#: Dashboard phase status -> row state. A pending phase is project progress,
#: not ill health, so it reads ``absent``.
PHASE_STATES = {"PASS": "ok", "ACTIVE": "ok", "PENDING": "absent"}


def worst(states: Iterable[str]) -> str:
    """The worst of ``states`` (``ok`` for none)."""
    rank = {state: index for index, state in enumerate(STATES)}
    return max(states, key=lambda state: rank.get(state, len(STATES)), default="ok")


def _row(area: str, item: str, state: str, detail: str) -> dict[str, str]:
    return {"area": area, "item": item, "state": state, "detail": detail}


# --------------------------------------------------------------------------
# tools
# --------------------------------------------------------------------------
def find_tool(name: str, *, which: Callable[[str], str | None] = shutil.which,
              extra_dirs: Iterable[str] = TEX_DIRS) -> str | None:
    """The path of ``name`` on PATH, else in a known TeX directory, else None."""
    found = which(name)
    if found:
        return found
    for pattern in extra_dirs:
        for directory in sorted(glob.glob(os.path.expanduser(pattern)), reverse=True):
            for candidate in (name, f"{name}.exe"):
                path = Path(directory) / candidate
                if path.is_file() and os.access(path, os.X_OK):
                    return str(path)
    return None


def _local_micromamba(root: Path) -> str | None:
    for name in ("micromamba.exe", "micromamba"):
        path = root / ".micromamba" / "bin" / name
        if fs.is_regular_file(path):
            return str(path)
    return None


def tool_rows(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    groups: dict[str, bool] = {}
    for name, group, missing, purpose in TOOLS:
        path = (_local_micromamba(root) if name == "micromamba" else None) or find_tool(name)
        if group is not None:
            groups[group] = groups.get(group, False) or path is not None
        rows.append(_row("tools", name, "ok" if path else missing,
                         path if path else f"not found ({purpose})"))
    for group, present in groups.items():
        rows.append(_row("tools", group, "ok" if present else "warn",
                         "available" if present else
                         f"no {group} found: install TeX Live/MacTeX or poppler"))
    return rows


# --------------------------------------------------------------------------
# framework
# --------------------------------------------------------------------------
def _drift(root: Path, kit_root: Path, stored: dict[str, Any]) -> list[str]:
    """Generator, manifest and surplus drift, as ``smith audit --check-drift``."""
    from ..bridges.audit import _surplus_static_files
    from ..generators import check_generated, context_for_workspace, workspace_tools

    active = workspace_tools(root)
    found = [f"generator: {path}" for path in
             check_generated(root, context_for_workspace(root), active, warnings=[])]
    current = manifest.workspace_framework_files(root, kit_root, notes=[])
    found += [f"manifest: {path}" for path in sorted({
        path for path in set(current) | set(stored.get("files", {}))
        if current.get(path) != stored.get("files", {}).get(path)})]
    found += [f"surplus: {path}" for path in _surplus_static_files(root, active)]
    return found


def framework_rows(root: Path, stored: dict[str, Any]) -> list[dict[str, str]]:
    from ..generators import read_workspace_version
    from ..kit import resolve_and_validate
    from .status import _migration_status

    rows = [_row("framework", "installed CLI", "ok", __version__)]
    workspace_version = read_workspace_version(root, "unknown")
    try:
        kit_root = resolve_and_validate()
        kit_version = manifest.kit_version(kit_root)
    except PapersmithError as exc:
        rows.append(_row("framework", "kit", "fail", str(exc)))
        rows.append(_row("framework", "workspace", "warn", workspace_version))
        return rows
    rows.append(_row("framework", "kit", "ok", f"{kit_version} ({kit_root})"))
    match = workspace_version == kit_version
    rows.append(_row("framework", "workspace", "ok" if match else "warn",
                     workspace_version if match else
                     f"{workspace_version}; kit is {kit_version}: run `smith upgrade`"))
    try:
        drift = _drift(root, kit_root, stored)
    except PapersmithError as exc:
        rows.append(_row("framework", "drift", "warn", f"could not be measured: {exc}"))
    else:
        rows.append(_row("framework", "drift", "warn" if drift else "ok",
                         "; ".join(drift) if drift else "none"))
    migrations = _migration_status(root, kit_version)
    if migrations["warning"]:
        rows.append(_row("framework", "migrations", "warn", migrations["warning"]))
    else:
        pending = migrations["pending"]
        rows.append(_row("framework", "migrations", "warn" if pending else "ok",
                         ", ".join(pending) if pending else "none pending"))
    return rows


# --------------------------------------------------------------------------
# backend payload: packages, wiring, phases
# --------------------------------------------------------------------------
_HARNESS_STATES = {"IN_SYNC": "ok"}
_AGENT_DIRS_FALLBACK = {
    "claude": ".claude/agents", "opencode": ".opencode/agents",
    "pi": ".pi/agents", "antigravity": ".agents/agents",
}


def _enabled_harnesses(root: Path) -> list[str]:
    try:
        from ..generators import workspace_tools
        return list(workspace_tools(root))
    except PapersmithError:
        return []


def _missing_projections(root: Path, tools: list[str], relative: Callable[[str], str | None]) -> list[str]:
    missing = []
    for tool in tools:
        path = relative(tool)
        if path is not None and not (root / path).exists():
            missing.append(tool)
    return missing


def _skill_rows(root: Path, wiring: dict[str, Any], tools: list[str]) -> list[dict[str, str]]:
    from .manifest import HARNESS_SKILL_LINKS

    links = dict(HARNESS_SKILL_LINKS)
    clis = {row.get("skill"): row for row in wiring.get("cli_entrypoints", [])}
    rows = []
    for skill in wiring.get("skills", []):
        name = skill.get("name", "?")
        if skill.get("state") != "WIRED":
            rows.append(_row("skills", name, "fail", f"{skill.get('path')} absent"))
            continue
        unprojected = _missing_projections(
            root, tools, lambda tool: f"{links[tool]}/{name}/SKILL.md" if tool in links else None)
        cli = clis.get(name)
        problems = []
        if unprojected:
            problems.append("not projected to " + ", ".join(unprojected))
        if cli is not None and cli.get("state") != "WIRED":
            problems.append(f"{cli.get('path')} --help failed: {cli.get('detail')}")
        detail = "; ".join(problems) if problems else (
            "present and projected" + (f"; {cli.get('path')} answers --help" if cli else ""))
        rows.append(_row("skills", name, "warn" if problems else "ok", detail))
    return rows


def _agent_rows(root: Path, wiring: dict[str, Any], tools: list[str]) -> list[dict[str, str]]:
    try:
        from ..generators import AGENT_DIRS
    except ImportError:  # pragma: no cover - the table ships with the package
        AGENT_DIRS = _AGENT_DIRS_FALLBACK
    rows = []
    for agent in wiring.get("agents", []):
        name = agent.get("name", "?")
        state = agent.get("state")
        if state == "MISSING":
            rows.append(_row("agents", name, "fail", agent.get("detail") or "absent"))
            continue
        problems = [] if state == "WIRED" else [agent.get("detail") or str(state)]
        unprojected = _missing_projections(
            root, tools, lambda tool: f"{AGENT_DIRS[tool]}/{name}.md" if tool in AGENT_DIRS else None)
        if unprojected:
            problems.append("not projected to " + ", ".join(unprojected))
        rows.append(_row("agents", name, "warn" if problems else "ok",
                         "; ".join(problems) if problems else "present and projected"))
    return rows


def _harness_rows(wiring: dict[str, Any]) -> list[dict[str, str]]:
    return [_row("framework", f"harness {h.get('tool')}",
                 _HARNESS_STATES.get(h.get("state"), "warn"),
                 f"{h.get('state')}: {h.get('detail')}")
            for h in wiring.get("harness_sync", {}).get("harnesses", [])]


def _package_rows(backend: dict[str, Any]) -> list[dict[str, str]]:
    python = backend.get("python") or {}
    rows = [_row("packages", "python", "ok" if python.get("ok") else "warn",
                 f"{python.get('version')} ({backend.get('interpreter')})"
                 + ("" if python.get("ok") else "; the forge needs Python >= 3.11"))]
    for package in backend.get("packages", []):
        if package.get("present"):
            rows.append(_row("packages", package["name"], "ok", package.get("version") or "installed"))
        else:
            rows.append(_row("packages", package["name"],
                             "warn" if package.get("required") else "absent",
                             "not importable: run `smith env install`" if package.get("required")
                             else "optional, not installed"))
    return rows


def _flow_rows(backend: dict[str, Any]) -> list[dict[str, str]]:
    phases = backend.get("phases")
    if phases is None:
        return [_row("flows", "phases", "warn",
                     f"could not be read: {backend.get('phases_error') or 'unknown error'}")]
    rows = []
    for phase in phases:
        status = str(phase.get("status", "")).upper()
        rows.append(_row("flows", str(phase.get("name") or phase.get("id")),
                         PHASE_STATES.get(status, "warn"),
                         f"{status}: {phase.get('detail') or ''}".rstrip(": ")))
    return rows


def backend_rows(root: Path, backend: dict[str, Any] | None,
                 error: str | None = None) -> list[dict[str, str]]:
    if backend is None:
        reason = f"backend unavailable: {error or 'unknown error'}"
        return [_row(area, "backend", "warn", reason)
                for area in ("packages", "skills", "agents", "flows")]
    wiring = backend.get("wiring") or {}
    tools = _enabled_harnesses(root)
    return (_harness_rows(wiring) + _package_rows(backend)
            + _skill_rows(root, wiring, tools) + _agent_rows(root, wiring, tools)
            + _flow_rows(backend))


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
def build_report(workspace: str | Path, *, backend: dict[str, Any] | None,
                 backend_error: str | None = None) -> dict[str, Any]:
    """``{summary, rows}`` for a workspace and a backend payload."""
    root = Path(workspace).expanduser().resolve()
    stored = manifest.load_manifest(root)
    if stored is None:
        raise UserError(f"not a papersmith workspace: missing {root / '.papersmith/manifest.json'}")
    rows = framework_rows(root, stored) + tool_rows(root) + backend_rows(root, backend, backend_error)
    order = {area: index for index, area in enumerate(AREAS)}
    rows.sort(key=lambda row: order[row["area"]])  # stable: keeps each area's own order
    counts = {state: sum(1 for row in rows if row["state"] == state) for state in STATES}
    return {
        "summary": {
            "state": worst(row["state"] for row in rows),
            "counts": counts,
            "total": len(rows),
            "workspace": str(root),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "rows": rows,
    }


def load_backend(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Ask the workspace interpreter for the backend payload."""
    from .ui import workspace_interpreter

    if not fs.is_regular_file(root / "skills" / "_core" / "command_center" / "doctor_view.py"):
        return None, "skills/_core/command_center/doctor_view.py is absent: run `smith upgrade`"
    interpreter = workspace_interpreter(root)
    try:
        done = subprocess.run(
            [interpreter, "-m", "skills._core.command_center.doctor_view", str(root)],
            cwd=str(root), capture_output=True, text=True, timeout=BACKEND_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{interpreter}: {type(exc).__name__}: {exc}"
    lines = (done.stdout or "").strip().splitlines()
    try:
        payload = json.loads(lines[-1]) if lines else None
    except json.JSONDecodeError:
        payload = None
    if done.returncode != 0 or not isinstance(payload, dict):
        tail = (done.stderr or done.stdout or "").strip().splitlines()
        return None, f"{interpreter} exited {done.returncode}: {tail[-1] if tail else 'no output'}"
    return payload, None


def diagnose(workspace: str | Path = ".") -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    if manifest.load_manifest(root) is None:
        raise UserError(f"not a papersmith workspace: missing {root / '.papersmith/manifest.json'}")
    backend, error = load_backend(root)
    return build_report(root, backend=backend, backend_error=error)


def format_table(report: dict[str, Any]) -> str:
    headers = ("AREA", "ITEM", "STATE", "DETAIL")
    body = [(r["area"], r["item"], r["state"].upper(), r["detail"]) for r in report["rows"]]
    widths = [max(len(str(line[i])) for line in [headers, *body]) for i in range(3)]
    lines = []
    for line in [headers, *body]:
        lines.append("  ".join(str(line[i]).ljust(widths[i]) for i in range(3)) + "  " + str(line[3]))
    summary = report["summary"]
    counts = ", ".join(f"{state} {summary['counts'][state]}" for state in STATES)
    lines.append("")
    lines.append(f"Summary: {summary['state'].upper()} ({counts})")
    return "\n".join(lines)


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "doctor", help="check the workspace's health: framework, packages, tools, skills, agents, phases",
        description="Print one table of project health rows (ok, absent, warn, fail). "
                    f"Exits {SUCCESS} unless a row fails, then {EXECUTION_ERROR}.")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="print {summary, rows} as JSON")
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    report = diagnose(args.directory)
    if args.as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_table(report))
    sys.stdout.flush()
    return EXECUTION_ERROR if report["summary"]["state"] == "fail" else SUCCESS
