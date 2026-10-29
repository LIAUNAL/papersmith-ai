"""The local environment the Experiments tab reports, probed offline.

``local_environment(root)`` answers whether a proof of concept or a full
experiment can run on this machine:

* the workspace env (``.micromamba/envs/papersmith/bin/python``) and the
  ``micromamba`` binary: present, Python version;
* each implementation target ``implementations/<repo>/``: its
  ``.venv/bin/python`` (present, Python version), the libraries it declares
  (names only, from ``pyproject.toml`` ``[project].dependencies`` and every
  ``requirements*.txt``), the installed version of each and the missing list,
  and the device torch sees (cuda, mps or cpu) when torch is installed.

Each interpreter is asked ONCE, through one subprocess running the fixed
inline ``PROBE_SCRIPT`` in isolated mode (``-I``: no ``PYTHON*`` variables, no
script directory or cwd on ``sys.path``) from a neutral working directory
outside the workspace, with a short timeout. Nothing the target ships is run
or imported other than what that script imports from the interpreter's own
installed packages (``importlib.metadata`` and, for the device, ``torch``). A
probe that fails, times out or prints garbage becomes "unverified", never
an exception. Results are cached per process for ``CACHE_TTL`` seconds, keyed
by the interpreter path, its mtime and the names asked, so a reinstalled venv
is probed again. No network.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from .terminal import find_executable

WORKSPACE_PYTHON = Path(".micromamba") / "envs" / "papersmith" / "bin" / "python"
TARGET_PYTHON = Path(".venv") / "bin" / "python"
MICROMAMBA = "micromamba"

PROBE_TIMEOUT = 5.0
CACHE_TTL = 300.0
MAX_TARGETS = 20
MAX_NAMES = 200
MAX_REQUIREMENT_FILES = 10
MAX_FILE_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 256 * 1024
MAX_TEXT = 120
UNVERIFIED = "unverified"

#: The one script any interpreter is asked to run. argv[1] is a JSON list of
#: distribution names; argv[2] is "1" when the device should be read.
PROBE_SCRIPT = """\
import json, platform, sys
from importlib import metadata
names = json.loads(sys.argv[1])
out = {"python": platform.python_version(), "installed": {}, "device": None}
for name in names:
    try:
        out["installed"][name] = metadata.version(name)
    except Exception:
        out["installed"][name] = None
if sys.argv[2] == "1":
    try:
        metadata.version("torch")
    except Exception:
        pass
    else:
        try:
            import torch
            device = {"cuda": bool(torch.cuda.is_available()), "mps": False}
            if device["cuda"]:
                device["cuda_name"] = str(torch.cuda.get_device_name(0))
            mps = getattr(torch.backends, "mps", None)
            device["mps"] = bool(mps is not None and mps.is_available())
            out["device"] = device
        except Exception as error:
            out["device"] = {"error": type(error).__name__}
print(json.dumps(out))
"""

_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_cache: dict[tuple[str, float, tuple[str, ...], bool], tuple[float, dict[str, Any] | None]] = {}
_lock = threading.Lock()
_refreshing: set[tuple[str, float, tuple[str, ...], bool]] = set()


def clear_cache() -> None:
    """Forget every cached probe (tests, or a fresh install)."""
    with _lock:
        _cache.clear()


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(line: str) -> str | None:
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith("-") or "://" in line:
        return None
    match = _NAME.match(line)
    return _canonical(match.group(1)) if match else None


def _read(path: Path) -> str | None:
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _pyproject_names(path: Path) -> list[str] | None:
    text = _read(path)
    if text is None or sys.version_info < (3, 11):
        return None
    import tomllib
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return None
    project = data.get("project") if isinstance(data, dict) else None
    deps = project.get("dependencies") if isinstance(project, dict) else None
    if not isinstance(deps, list):
        return []
    return [name for item in deps if isinstance(item, str) and (name := _requirement_name(item))]


def required_libraries(target: Path) -> dict[str, list[str]]:
    """The distribution names a target declares, sorted; never raises."""
    names: set[str] = set()
    sources: list[str] = []
    found = _pyproject_names(target / "pyproject.toml")
    if found is not None:
        names.update(found)
        sources.append("pyproject.toml")
    try:
        files = sorted(p for p in target.glob("requirements*.txt") if p.is_file())
    except OSError:
        files = []
    for path in files[:MAX_REQUIREMENT_FILES]:
        text = _read(path)
        if text is None:
            continue
        sources.append(path.name)
        names.update(n for line in text.splitlines() if (n := _requirement_name(line)))
    return {"names": sorted(names)[:MAX_NAMES], "sources": sorted(sources)}


def _run_probe(python: Path, names: list[str], device: bool) -> dict[str, Any] | None:
    try:
        done = subprocess.run([str(python), "-I", "-c", PROBE_SCRIPT, json.dumps(names), "1" if device else "0"],
                              capture_output=True, text=True, timeout=PROBE_TIMEOUT, check=False,
                              cwd=tempfile.gettempdir(), stdin=subprocess.DEVNULL)
        output = (done.stdout or "")[:MAX_OUTPUT_BYTES].strip().splitlines()
        parsed = json.loads(output[-1]) if done.returncode == 0 and output else None
        return parsed if isinstance(parsed, dict) and isinstance(parsed.get("python"), str) else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _refresh(key: tuple[str, float, tuple[str, ...], bool], python: Path, names: list[str],
             device: bool) -> None:
    try:
        answer = _run_probe(python, names, device)
        with _lock:
            _cache[key] = (time.monotonic(), answer)
    finally:
        with _lock:
            _refreshing.discard(key)


def _probe(python: Path, names: list[str], device: bool) -> dict[str, Any] | None:
    """The interpreter's answer to ``PROBE_SCRIPT``, cached; None when unverifiable.

    An expired answer is still served while a background probe replaces it,
    so a panel reload never waits on the interpreter once it answered once.
    """
    try:
        mtime = python.stat().st_mtime
    except OSError:
        return None
    key = (str(python), mtime, tuple(names), device)
    now = time.monotonic()
    with _lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]
        if cached:
            if key not in _refreshing:
                _refreshing.add(key)
                threading.Thread(target=_refresh, args=(key, python, names, device),
                                 name="local-env-probe", daemon=True).start()
            return cached[1]
    answer = _run_probe(python, names, device)
    with _lock:
        _cache[key] = (now, answer)
    return answer


def _text(value: Any) -> str | None:
    return value.strip()[:MAX_TEXT] or None if isinstance(value, str) else None


def _device(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    if raw.get("error"):
        return UNVERIFIED
    if raw.get("cuda"):
        name = _text(raw.get("cuda_name"))
        return f"cuda:{name}" if name else "cuda"
    return "mps" if raw.get("mps") else "cpu"


def _interpreter(root: Path, rel: Path) -> tuple[Path, bool]:
    path = root / rel
    try:
        return path, path.is_file()
    except OSError:
        return path, False


def _workspace(root: Path) -> dict[str, Any]:
    python, present = _interpreter(root, WORKSPACE_PYTHON)
    row: dict[str, Any] = {"label": "Workspace micromamba environment", "path": WORKSPACE_PYTHON.as_posix(),
                           "present": present, "python": None, "state": "missing",
                           "micromamba": find_executable(MICROMAMBA)}
    if not present:
        row["detail"] = "No environment: python scripts/setup_env.py creates it with micromamba."
        return row
    answer = _probe(python, [], False)
    if answer is None:
        row.update(state="unverified", detail=f"Interpreter present; version {UNVERIFIED}.")
    else:
        row.update(state="ready", python=_text(answer.get("python")), detail="Interpreter present.")
    return row


def _target(root: Path, folder: Path) -> dict[str, Any]:
    rel = folder.relative_to(root)
    declared = required_libraries(folder)
    names = declared["names"]
    python, present = _interpreter(folder, TARGET_PYTHON)
    row: dict[str, Any] = {"repo": folder.name, "path": (rel / TARGET_PYTHON).as_posix(), "present": present,
                           "python": None, "state": "missing", "required": names,
                           "sources": declared["sources"], "libraries": [], "missing": [], "device": None}
    if not present:
        row["detail"] = "No .venv: the implementation creates it on its first pass."
        return row
    answer = _probe(python, names, "torch" in names)
    if answer is None:
        row.update(state="unverified", device=UNVERIFIED,
                   detail=f"Interpreter present; libraries {UNVERIFIED} (the probe failed or exceeded "
                          f"{PROBE_TIMEOUT:g} s).")
        return row
    installed = answer.get("installed") if isinstance(answer.get("installed"), dict) else {}
    libraries = [{"name": name, "version": _text(installed.get(name))} for name in names]
    missing = [lib["name"] for lib in libraries if lib["version"] is None]
    row.update(python=_text(answer.get("python")), libraries=libraries, missing=missing,
               device=_device(answer.get("device")), state="incomplete" if missing else "ready")
    row["detail"] = (f"{len(missing)} library(ies) missing: {', '.join(missing[:12])}." if missing
                     else f"{len(names)} declared library(ies) installed.")
    return row


def _targets(root: Path) -> list[Path]:
    top = root / "implementations"
    try:
        if not top.is_dir() or top.is_symlink():
            return []
        return sorted(p for p in top.iterdir()
                      if p.is_dir() and not p.is_symlink() and not p.name.startswith("."))[:MAX_TARGETS]
    except OSError:
        return []


def local_environment(root: Path | str) -> dict[str, Any]:
    """The workspace env and every target venv, bounded and offline; never raises."""
    root = Path(root)
    try:
        workspace = _workspace(root)
    except Exception:  # noqa: BLE001 - a failing probe is a row, never an error
        workspace = {"label": "Workspace micromamba environment", "path": WORKSPACE_PYTHON.as_posix(),
                     "present": False, "python": None, "state": "unverified", "micromamba": None,
                     "detail": "Could not be probed."}
    targets: list[dict[str, Any]] = []
    for folder in _targets(root):
        try:
            targets.append(_target(root, folder))
        except Exception:  # noqa: BLE001
            targets.append({"repo": folder.name, "path": "", "present": False, "python": None,
                            "state": "unverified", "required": [], "sources": [], "libraries": [],
                            "missing": [], "device": UNVERIFIED, "detail": "Could not be probed."})
    note = (f"Offline local probe: one subprocess per interpreter (at most {PROBE_TIMEOUT:g} s), "
            f"cached for {CACHE_TTL / 60:g} minutes or until the interpreter changes.")
    return {"workspace": workspace, "targets": targets, "note": note}
