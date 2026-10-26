"""Backend half of the Smith Doctor (``smith doctor``, ``GET /api/doctor``).

The rows themselves are built by ``papersmith.core.doctor.build_report``; this
module supplies the part only the workspace interpreter can measure: its own
Python and packages, the wiring health and the dashboard's phases. It imports
no third-party module at load time, so ``smith doctor`` can run it as

    python -m skills._core.command_center.doctor_view <dir>

and read one JSON object from stdout.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .health_inspector import get_wiring_health

#: ``(distribution, import name, required)``: what the forge's provisioned
#: environment holds (``scripts/setup_env.py``), the command center included.
KEY_PACKAGES = (
    ("numpy", "numpy", True),
    ("pyyaml", "yaml", True),
    ("jsonschema", "jsonschema", True),
    ("requests", "requests", True),
    ("pypdfium2", "pypdfium2", True),
    ("nbformat", "nbformat", True),
    ("nbclient", "nbclient", True),
    ("ipykernel", "ipykernel", True),
    ("pytest", "pytest", True),
    ("fastapi", "fastapi", True),
    ("uvicorn", "uvicorn", True),
    ("watchfiles", "watchfiles", True),
    ("pydantic", "pydantic", True),
    ("kagglesdk", "kagglesdk", False),
    ("docling", "docling", False),
)


#: Set by ``smith ui`` to the CLI's own interpreter. The dashboard runs under
#: the workspace's environment, which does not hold ``papersmith`` (the CLI is
#: installed in its own venv), so the rows are built there instead.
CLI_PYTHON_ENV = "PAPERSMITH_CLI_PYTHON"
CLI_TIMEOUT_SECONDS = 60
_BUILD_REPORT = ("import json, sys\n"
                 "from papersmith.core.doctor import build_report\n"
                 "print(json.dumps(build_report(sys.argv[1], backend=json.load(sys.stdin))))")


def package_report() -> list[dict[str, Any]]:
    rows = []
    for name, module, required in KEY_PACKAGES:
        try:
            present = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            present = False
        version = None
        if present:
            try:
                version = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                version = None
        rows.append({"name": name, "module": module, "present": present,
                     "version": version, "required": required})
    return rows


def flow_phases(root: Path) -> tuple[list[dict[str, Any]] | None, str | None]:
    """The phases ``/api/status`` reports, or None and why not."""
    try:
        from . import server
    except Exception as exc:  # noqa: BLE001 - fastapi absent is a reading, not a crash
        return None, f"command center not importable: {type(exc).__name__}: {exc}"
    try:
        app = server.create_app(root, history_store=None)
        endpoint = next(route.endpoint for route in app.routes
                        if getattr(route, "path", None) == "/api/status")
        return json.loads(bytes(endpoint().body)).get("fases") or [], None
    except Exception as exc:  # noqa: BLE001
        return None, f"/api/status failed: {type(exc).__name__}: {exc}"


def backend_payload(root: Path | str, *, wiring: dict[str, Any] | None = None,
                    phases: list[dict[str, Any]] | None = None,
                    phases_error: str | None = None) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    if phases is None and phases_error is None:
        phases, phases_error = flow_phases(root_path)
    return {
        "interpreter": sys.executable,
        "python": {"version": ".".join(str(p) for p in sys.version_info[:3]),
                   "ok": sys.version_info >= (3, 11)},
        "packages": package_report(),
        "wiring": wiring if wiring is not None else get_wiring_health(root_path),
        "phases": phases,
        "phases_error": phases_error,
    }


def _report_via_cli(root: Path | str, payload: dict[str, Any]) -> dict[str, Any] | str:
    """The report built by the CLI's interpreter, or why it could not be."""
    interpreter = os.environ.get(CLI_PYTHON_ENV)
    if not interpreter:
        return (f"papersmith is not importable by {sys.executable}; "
                "run `smith doctor` from a shell")
    try:
        done = subprocess.run([interpreter, "-c", _BUILD_REPORT, str(root)],
                              input=json.dumps(payload), capture_output=True, text=True,
                              timeout=CLI_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"the papersmith CLI interpreter {interpreter} could not run: {exc}"
    if done.returncode != 0:
        tail = (done.stderr.strip().splitlines() or ["no output"])[-1]
        return f"the papersmith CLI interpreter {interpreter} failed: {tail}"
    try:
        return json.loads(done.stdout)
    except ValueError as exc:
        return f"the papersmith CLI interpreter {interpreter} printed no report: {exc}"


def get_doctor_view(root: Path | str, **backend: Any) -> dict[str, Any]:
    """``{summary, rows}``, the same rows ``smith doctor`` prints."""
    payload = backend_payload(root, **backend)
    try:
        from papersmith.core.doctor import build_report  # type: ignore
    except Exception:  # noqa: BLE001 - the usual case under the workspace's environment
        report = _report_via_cli(root, payload)
        if isinstance(report, dict):
            return report
        return {"summary": {"state": "warn", "counts": {"warn": 1}, "total": 1,
                            "workspace": str(root), "generated_at": None},
                "rows": [{"area": "framework", "item": "papersmith", "state": "warn",
                          "detail": report}]}
    return build_report(root, backend=payload)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0] if args else ".")
    print(json.dumps(backend_payload(root), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
