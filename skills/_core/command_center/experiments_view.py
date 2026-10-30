"""Read-only view behind the dashboard's Experiments tab.

``get_experiments_view(root)`` gathers, without writing anything:

* the latest experiments protocol (``experiments/experiments-*-vNN.md``): its
  validation scheme and, per experiment, the expected report tables approved
  in deliberation;
* every product folder ``implementations/<repo>/<Name>/`` — a proof of concept
  when it holds ``AGREED.md``, a full experiment when it holds
  ``Experimental_AGREED.md`` — with its convergence histories, figures,
  tables, significance tests, pinned artifacts and remote runs folded from
  its ``.remote-execution/ledger.jsonl`` (also per worker: each worker's
  lanes -- entrypoint and concurrent slot -- with state, units and service), plus one row per hyperparameter
  study the ``hyperparameter-search`` skill reported under
  ``Results/hpo/<study>/summary.json`` (schema 1) with its figures;
* the ``datasets`` skill's registry (``datasets/registry.json``): per dataset
  its role (toy or full), title, license decision, qc status, preparation
  version and remote ref/visibility, plus the search files beside it;
* a cheap remote-accounts readiness hint (the credential store its owning
  skill declares is present; credential files waiting in the drop-zone that
  skill declares), read through ``state_extractor``'s declaration readers so
  no service name is restated here;
* the remote-services table (``remote_services``): one offline, bounded row
  per service the remote path depends on, with its state and the one action
  that activates it, plus the team table (one account per person and service);
* the local environment (``local_env``): the workspace micromamba env and
  each target's ``.venv`` with its declared libraries, installed or missing,
  and the device torch sees;
* the run options (``run_options``): per stage (proof of concept, full) and
  host family, availability and an estimate from each product's
  ``Results/timing.json`` (±20%), plus one recommendation per stage;
* the Colab box state (``terminal.colab_mcp_status``): which MCP files register
  the official Colab MCP, the box's constant commands and the environment.

Every read is bounded (files per product, bytes per file, points per series,
series per history) and contained under ``root``: a symlink resolving outside
the workspace is skipped, never read. Malformed files never raise; they are
recorded in ``warnings``. Returned paths are relative to ``root`` so
``/api/artifact`` can serve them.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone, timedelta
import importlib.util
import io
import json
import math
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

from .atlas import _locate
from .state_extractor import credentials_store, inbox_directory
from .terminal import colab_mcp_status, remote_mcp_status
from .remote_services import remote_services, service_of_worker
from .local_env import local_environment
from .run_options import parse_plan, parse_timing, run_options
from .decisions import LEDGER_MAX_BYTES, MAX_LEDGER_LINES, _discover_ledgers, _read_bytes

MAX_PRODUCTS = 50
MAX_FILES_PER_PRODUCT = 200
#: Bound on the files one product's walk visits, shown or not (run records count here only).
MAX_SCANNED_FILES = 20000
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_POINTS = 500
MAX_SERIES = 24
MAX_HISTORIES = 12
MAX_FIGURES = 60
MAX_TABLES = 30
MAX_TABLE_ROWS = 200
MAX_TABLE_COLS = 30
MAX_SIGNIFICANCE_ROWS = 200
MAX_PINNED = 30
MAX_LATEST_RUNS = 10
MAX_REMOTE_WORKERS = 24
MAX_WORKER_LANES = 20
MAX_LANE_UNITS = 50
MAX_WARNINGS = 100
MAX_DATASETS = 100
MAX_SEARCHES = 20
MAX_PROTOCOL_BYTES = 1024 * 1024
MAX_HPO_STUDIES = 24
MAX_HPO_PARAMS = 40
MAX_HPO_NOTES = 10
HPO_FIGURES = ("contour", "importance", "history")
TEXT_MAX = 600

FIGURE_EXTS = {".png", ".svg", ".jpg", ".jpeg", ".pdf"}
TABLE_EXTS = {".csv", ".md", ".json"}
HISTORY_EXTS = {".json", ".jsonl", ".csv"}
GROUP_KEYS = ("model", "variant", "fold", "seed")
X_KEYS = ("epoch", "step")
SIGNIFICANCE_KEYS = ("comparison", "test", "statistic", "p_value", "p_adjusted", "correction",
                     "effect_size", "effect_size_name", "ci_low", "ci_high", "n", "alpha")

_PROTOCOL_RE = re.compile(r"^experiments-.+-v(\d+)\.md$")
_EXPERIMENT_RE = re.compile(r"^##\s+Experiment\s+\[exp:([^\]]+)\]\s*[—–-]?\s*(.*)$")
_REPORT_RE = re.compile(r"^###\s+Expected Report:?\s*(.*)$")
_BULLET_RE = re.compile(r"^-\s+\*\*([^*]+?):?\*\*:?\s*(.*)$")
_SCHEME_RE = re.compile(r"^\*\*Validation scheme:?\*\*:?\s*(.*)$", re.IGNORECASE)
_BULLET_FIELDS = {
    "hypothesis": "hypothesis",
    "priority": "priority",
    "success criterion": "success_criterion",
    "estimated cost": "cost",
}


def _clip(value: Any, limit: int = TEXT_MAX) -> str:
    text = str(value if value is not None else "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


class _Reader:
    """Contained, bounded reads that note every refusal instead of raising."""

    def __init__(self, root: Path, warnings: list[str]) -> None:
        self.root = root
        self.warnings = warnings

    def warn(self, message: str) -> None:
        if len(self.warnings) < MAX_WARNINGS:
            self.warnings.append(message)

    def text(self, path: Path, cap: int = MAX_FILE_BYTES) -> str | None:
        status, resolved, _size, _mtime = _locate(self.root, path, cap)
        label = self.label(path)
        if status == "unsafe":
            return None  # Escapes the workspace: neither read nor reported by path.
        if status == "too_large":
            self.warn(f"{label}: larger than {cap // 1024} KiB, not read")
            return None
        if status != "ok" or resolved is None:
            self.warn(f"{label}: unreadable")
            return None
        data = _read_bytes(resolved, cap)
        if data is None:
            self.warn(f"{label}: unreadable")
            return None
        return data.decode("utf-8", errors="replace")

    def json(self, path: Path) -> Any:
        text = self.text(path)
        if text is None:
            return None
        try:
            return json.loads(text)
        except ValueError:
            self.warn(f"{self.label(path)}: malformed JSON")
            return None

    def contained(self, path: Path) -> bool:
        status, _resolved, _size, _mtime = _locate(self.root, path, MAX_FILE_BYTES * 64)
        return status in ("ok", "too_large")

    def label(self, path: Path) -> str:
        try:
            return _rel(self.root, path)
        except ValueError:
            return path.name


# --------------------------------------------------------------------------
# protocol
# --------------------------------------------------------------------------
def _split_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [_clip(c.strip(), 200) for c in cells][:MAX_TABLE_COLS]


def _is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", line.strip()))


def _markdown_tables(lines: list[str]) -> list[dict[str, Any]]:
    """Every pipe table in ``lines`` as ``{headers, rows}``."""
    tables: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            headers = _split_row(line)
            rows: list[list[str]] = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                if len(rows) < MAX_TABLE_ROWS:
                    row = _split_row(lines[i])
                    rows.append((row + [""] * len(headers))[: len(headers)])
                i += 1
            tables.append({"headers": headers, "rows": rows})
            continue
        i += 1
    return tables


def _latest_protocol(root: Path) -> Path | None:
    folder = root / "experiments"
    best: tuple[int, str] | None = None
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                match = _PROTOCOL_RE.match(entry.name)
                if match and entry.is_file(follow_symlinks=True):
                    key = (int(match.group(1)), entry.name)
                    if best is None or key > best:
                        best = key
    except OSError:
        return None
    return folder / best[1] if best else None


def _parse_protocol(root: Path, reader: _Reader) -> dict[str, Any] | None:
    path = _latest_protocol(root)
    if path is None:
        return None
    text = reader.text(path, MAX_PROTOCOL_BYTES)
    if text is None:
        return None
    revision = int(_PROTOCOL_RE.match(path.name).group(1))  # type: ignore[union-attr]
    lines = text.splitlines()
    scheme = ""
    experiments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    report_title: str | None = None
    report_lines: list[str] = []

    def close_report() -> None:
        nonlocal report_title, report_lines
        if current is not None and report_title is not None:
            for table in _markdown_tables(report_lines)[:1]:
                current["expected_reports"].append({"title": _clip(report_title, 200), **table})
        report_title, report_lines = None, []

    for line in lines:
        stripped = line.strip()
        scheme_match = _SCHEME_RE.match(stripped)
        if scheme_match and not scheme:
            scheme = _clip(scheme_match.group(1))
            continue
        exp_match = _EXPERIMENT_RE.match(stripped)
        if exp_match:
            close_report()
            current = {"id": _clip(exp_match.group(1), 40), "title": _clip(exp_match.group(2), 200),
                       "priority": "", "hypothesis": "", "success_criterion": "", "cost": "",
                       "expected_reports": []}
            experiments.append(current)
            continue
        if stripped.startswith("## "):
            close_report()
            current = None
            continue
        report_match = _REPORT_RE.match(stripped)
        if report_match and current is not None:
            close_report()
            report_title = report_match.group(1) or "Expected Report"
            continue
        if stripped.startswith("### "):
            close_report()
            continue
        if report_title is not None:
            report_lines.append(line)
            continue
        bullet = _BULLET_RE.match(stripped)
        if bullet and current is not None:
            field = _BULLET_FIELDS.get(bullet.group(1).strip().lower())
            if field and not current[field]:
                current[field] = _clip(bullet.group(2))
    close_report()
    return {"file": _rel(root, path), "revision": revision, "validation_scheme": scheme,
            "experiments": experiments}


# --------------------------------------------------------------------------
# histories
# --------------------------------------------------------------------------
def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _records(data: Any) -> list[dict[str, Any]] | None:
    """Row records from a list of dicts, a {history|records: [...]} wrapper,
    or a column dict of equal-length lists (Keras ``History.history``)."""
    if isinstance(data, dict):
        for key in ("history", "records", "rows"):
            if isinstance(data.get(key), list):
                return _records(data[key])
        columns = {k: v for k, v in data.items() if isinstance(v, list)}
        if columns:
            length = max(len(v) for v in columns.values())
            return [{k: (v[i] if i < len(v) else None) for k, v in columns.items()}
                    for i in range(length)]
        return None
    if isinstance(data, list):
        rows = [r for r in data if isinstance(r, dict)]
        return rows if rows else None
    return None


def _downsample(points: list[list[float]]) -> list[list[float]]:
    if len(points) <= MAX_POINTS:
        return points
    last = len(points) - 1
    picks = sorted({round(i * last / (MAX_POINTS - 1)) for i in range(MAX_POINTS)})
    return [points[i] for i in picks]


def _x_value(x: float) -> float | int:
    return int(x) if float(x).is_integer() else x


def _series(rows: list[dict[str, Any]], label: str, reader: _Reader) -> dict[str, Any] | None:
    keys: list[str] = []
    for row in rows[:50]:
        for key in row:
            if key not in keys:
                keys.append(key)
    x_key = next((k for k in X_KEYS if k in keys), None)
    group_keys = [k for k in keys if k in GROUP_KEYS]
    metrics = [k for k in keys if k != x_key and k not in group_keys
               and any(_number(r.get(k)) is not None for r in rows[:50])]
    if not metrics:
        reader.warn(f"{label}: no numeric series")
        return None
    buckets: dict[tuple[str, str], list[list[float]]] = {}
    for index, row in enumerate(rows):
        x = _number(row.get(x_key)) if x_key else float(index)
        if x is None:
            continue
        group = ", ".join(f"{k}={_clip(row.get(k), 40)}" for k in sorted(group_keys)
                          if row.get(k) not in (None, ""))
        for metric in metrics:
            y = _number(row.get(metric))
            if y is None:
                continue
            bucket = buckets.get((metric, group))
            if bucket is None:
                if len(buckets) >= MAX_SERIES:
                    continue
                bucket = buckets[(metric, group)] = []
            bucket.append([_x_value(x), y])
    if len(buckets) >= MAX_SERIES:
        reader.warn(f"{label}: series capped at {MAX_SERIES}")
    series = [{"name": metric, "group": group,
               "points": _downsample(sorted(points, key=lambda p: p[0]))}
              for (metric, group), points in buckets.items() if points]
    if not series:
        reader.warn(f"{label}: no numeric points")
        return None
    return {"file": label, "x_key": x_key or "index", "series": series}


def _read_history(path: Path, reader: _Reader) -> dict[str, Any] | None:
    label = reader.label(path)
    text = reader.text(path)
    if text is None:
        return None
    ext = path.suffix.lower()
    rows: list[dict[str, Any]] | None
    if ext == ".csv":
        try:
            rows = list(csv.DictReader(io.StringIO(text)))
        except csv.Error:
            rows = None
    elif ext == ".jsonl":
        rows = []
        bad = 0
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if isinstance(value, dict):
                rows.append(value)
        if bad:
            reader.warn(f"{label}: {bad} malformed line(s) skipped")
    else:
        try:
            rows = _records(json.loads(text))
        except ValueError:
            reader.warn(f"{label}: malformed JSON")
            return None
    if not rows:
        reader.warn(f"{label}: no records")
        return None
    return _series(rows, label, reader)


# --------------------------------------------------------------------------
# tables, significance, pinned
# --------------------------------------------------------------------------
def _flatten(data: dict[str, Any], prefix: str = "", depth: int = 0) -> list[list[str]]:
    rows: list[list[str]] = []
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict) and depth < 1:
            rows.extend(_flatten(value, f"{name}.", depth + 1))
        elif isinstance(value, (dict, list)):
            rows.append([_clip(name, 200), _clip(json.dumps(value)[:200], 200)])
        else:
            rows.append([_clip(name, 200), _clip(value, 200)])
        if len(rows) >= MAX_TABLE_ROWS:
            break
    return rows[:MAX_TABLE_ROWS]


def _read_table(path: Path, reader: _Reader) -> dict[str, Any] | None:
    label = reader.label(path)
    ext = path.suffix.lower()
    text = reader.text(path)
    if text is None:
        return None
    if ext == ".csv":
        try:
            parsed = list(csv.reader(io.StringIO(text)))
        except csv.Error:
            reader.warn(f"{label}: malformed CSV")
            return None
        if not parsed:
            return None
        headers = [_clip(h, 200) for h in parsed[0][:MAX_TABLE_COLS]]
        rows = [[_clip(c, 200) for c in row[:MAX_TABLE_COLS]] for row in parsed[1:MAX_TABLE_ROWS + 1]]
        return {"path": label, "format": "csv", "headers": headers, "rows": rows}
    if ext == ".md":
        tables = _markdown_tables(text.splitlines())
        if not tables:
            return None
        return {"path": label, "format": "md", **tables[0]}
    try:
        data = json.loads(text)
    except ValueError:
        reader.warn(f"{label}: malformed JSON")
        return None
    if isinstance(data, list) and data and all(isinstance(r, dict) for r in data):
        headers: list[str] = []
        for row in data[:MAX_TABLE_ROWS]:
            for key in row:
                if key not in headers and len(headers) < MAX_TABLE_COLS:
                    headers.append(key)
        rows = [[_clip(row.get(h, ""), 200) for h in headers] for row in data[:MAX_TABLE_ROWS]]
        return {"path": label, "format": "json", "headers": [_clip(h, 200) for h in headers],
                "rows": rows}
    if isinstance(data, dict):
        return {"path": label, "format": "json", "headers": ["key", "value"], "rows": _flatten(data)}
    reader.warn(f"{label}: not a table")
    return None


def _read_significance(path: Path, reader: _Reader) -> list[dict[str, Any]]:
    data = reader.json(path)
    if data is None:
        return []
    if isinstance(data, dict):
        data = next((data[k] for k in ("tests", "comparisons", "results") if isinstance(data.get(k), list)),
                    [data])
    if not isinstance(data, list):
        reader.warn(f"{reader.label(path)}: not a list of tests")
        return []
    rows: list[dict[str, Any]] = []
    for item in data[:MAX_SIGNIFICANCE_ROWS]:
        if not isinstance(item, dict):
            continue
        row: dict[str, Any] = {"file": reader.label(path)}
        for key in SIGNIFICANCE_KEYS:
            value = item.get(key)
            if key in ("comparison", "test", "correction", "effect_size_name"):
                row[key] = _clip(value, 200) if value is not None else None
            else:
                row[key] = _number(value)
        rows.append(row)
    return rows


def _pinned(root: Path, product: Path, reader: _Reader, panel: Path | None) -> list[str]:
    if panel is None:
        return []
    data = reader.json(panel)
    entries = data.get("pinned") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        if data is not None:
            reader.warn(f"{reader.label(panel)}: expected {{\"pinned\": [...]}}")
        return []
    out: list[str] = []
    for entry in entries[:MAX_PINNED]:
        if not isinstance(entry, str) or not entry or entry.startswith("/"):
            continue
        base = root if entry.startswith("implementations/") else product
        candidate = base / entry
        status, resolved, _size, _mtime = _locate(root, candidate, MAX_FILE_BYTES * 64)
        if status in ("ok", "too_large") and resolved is not None:
            rel = _rel(root, resolved)
            if rel not in out:
                out.append(rel)
    return out


# --------------------------------------------------------------------------
# remote runs
# --------------------------------------------------------------------------
def _fold_runs(root: Path, ledger: Path | None, reader: _Reader) -> dict[str, Any]:
    empty = {"count": 0, "by_state": {}, "latest": []}
    if ledger is None:
        return empty
    text = reader.text(ledger, LEDGER_MAX_BYTES)
    if text is None:
        return empty
    by_id: dict[str, str] = {}
    runs: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    bad = 0
    for line in text.splitlines()[:MAX_LEDGER_LINES]:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if not isinstance(event, dict):
            bad += 1
            continue
        kind = event.get("kind")
        sid = _clip(event.get("submissionId"), 120)
        if kind == "submitted":
            entry = _clip(event.get("entrypoint"), 200) or sid or "?"
            if sid:
                by_id[sid] = entry
            runs[entry] = {"entrypoint": entry, "state": "submitted", "worker": _clip(event.get("worker"), 80),
                           "submission_id": sid, "ts": _clip(event.get("ts"), 40), "reason": ""}
            if entry in order:
                order.remove(entry)
            order.append(entry)
        elif kind in ("returned", "errored"):
            entry = by_id.get(sid)
            if entry is None or entry not in runs:
                continue
            runs[entry].update(state=kind, ts=_clip(event.get("ts"), 40),
                               reason=_clip(event.get("reason"), 300) if kind == "errored" else "")
            order.remove(entry)
            order.append(entry)
    if bad:
        reader.warn(f"{reader.label(ledger)}: {bad} malformed line(s) skipped")
    by_state: dict[str, int] = {}
    for run in runs.values():
        by_state[run["state"]] = by_state.get(run["state"], 0) + 1
    latest = [runs[e] for e in reversed(order)][:MAX_LATEST_RUNS]
    return {"count": len(runs), "by_state": dict(sorted(by_state.items())), "latest": latest}


def _ledger_text(root: Path, ledger: Path | None) -> str | None:
    """The ledger's text read a second time, silently: ``_fold_runs`` already
    reported anything unreadable or malformed about this same file."""
    if ledger is None:
        return None
    status, resolved, _size, _mtime = _locate(root, ledger, LEDGER_MAX_BYTES)
    if status != "ok" or resolved is None:
        return None
    data = _read_bytes(resolved, LEDGER_MAX_BYTES)
    return None if data is None else data.decode("utf-8", errors="replace")


def _slot_of(event: dict) -> int:
    slot = event.get("slot")
    return slot if isinstance(slot, int) and not isinstance(slot, bool) and slot >= 2 else 1


def _units_of(event: dict) -> list[str] | None:
    units = event.get("units")
    if not isinstance(units, list):
        return None
    return [_clip(unit, 80) for unit in units[:MAX_LANE_UNITS]]


def _fold_workers(root: Path, ledger: Path | None) -> list[dict[str, Any]]:
    """Remote runs per worker (S6). One lane per ``(entrypoint, worker,
    slot)`` -- the remote-execution ledger's own ``lane_key``: a slot of 2 or
    more is its own lane, a later submission to a lane supersedes the earlier
    one. Lanes are grouped under their worker; workers come most recently
    updated first. Bounded by MAX_REMOTE_WORKERS and MAX_WORKER_LANES."""
    text = _ledger_text(root, ledger)
    if text is None:
        return []
    lanes: dict[tuple[str, str, int], dict[str, Any]] = {}
    by_id: dict[str, tuple[str, str, int]] = {}
    touched: list[str] = []
    for line in text.splitlines()[:MAX_LEDGER_LINES]:
        try:
            event = json.loads(line) if line.strip() else None
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("kind")
        sid = _clip(event.get("submissionId"), 120)
        if kind == "submitted":
            worker = _clip(event.get("worker"), 80)
            entry = _clip(event.get("entrypoint"), 200) or sid or "?"
            key = (entry, worker, _slot_of(event))
            granted = event.get("grantedCapacity")
            lanes[key] = {"entrypoint": entry, "slot": key[2], "state": "submitted", "submission_id": sid,
                          "units": _units_of(event),
                          "granted": granted if isinstance(granted, int) and not isinstance(granted, bool) else None,
                          "ts": _clip(event.get("ts"), 40), "reason": ""}
            if sid:
                by_id[sid] = key
        elif kind in ("returned", "errored"):
            key = by_id.get(sid)
            lane = lanes.get(key) if key else None
            if lane is None or lane["submission_id"] != sid:
                continue  # unknown, or a superseded submission of its lane
            lane.update(state=kind, ts=_clip(event.get("ts"), 40),
                        reason=_clip(event.get("reason"), 300) if kind == "errored" else "")
            worker = key[1]
        else:
            continue
        if worker in touched:
            touched.remove(worker)
        touched.append(worker)
    workers: list[dict[str, Any]] = []
    for worker in reversed(touched):
        if len(workers) >= MAX_REMOTE_WORKERS:
            break
        own = [lanes[key] for key in sorted(k for k in lanes if k[1] == worker)]
        by_state: dict[str, int] = {}
        for lane in own:
            by_state[lane["state"]] = by_state.get(lane["state"], 0) + 1
        workers.append({"worker": worker, "service": service_of_worker(worker),
                        "last_update": max((lane["ts"] for lane in own), default=""),
                        "by_state": dict(sorted(by_state.items())), "lane_count": len(own),
                        "lanes": own[:MAX_WORKER_LANES]})
    return workers


# --------------------------------------------------------------------------
# products
# --------------------------------------------------------------------------
def _scan(folder: Path, cap: int, skip: tuple[str, ...] = (), keep=None) -> tuple[list[Path], str | None]:
    """Files under ``folder`` without following directory symlinks; top-level
    directories named in ``skip`` are read by their own reader instead.

    ``keep(path)`` selects the files that count against ``cap``: files the
    panel never shows (a campaign's run records) are walked past without using
    it up. The walk itself stops after ``MAX_SCANNED_FILES`` files. The second
    value names the bound that cut the scan, or is None.
    """
    found: list[Path] = []
    if not folder.is_dir() or folder.is_symlink():
        return found, None
    visited = 0
    for current, dirs, files in os.walk(folder, followlinks=False):
        top = Path(current) == folder
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (top and d in skip))
        for name in sorted(files):
            visited += 1
            if visited > MAX_SCANNED_FILES:
                return found, "visited"
            path = Path(current) / name
            if keep is not None and not keep(path):
                continue
            if len(found) >= cap:
                return found, "kept"
            found.append(path)
    return found, None


def _result_kind(results: Path, path: Path) -> str | None:
    """What the panel shows a file under ``Results/`` as, or None.

    A figure or a table sits in a ``figures`` or ``tables`` folder at any depth
    (``Results/figures`` or ``Results/<experiment>/figures``); a summary is
    ``Results/summary.json`` or ``Results/<experiment>/summary.json``.
    """
    parts = path.relative_to(results).parts
    name, ext = path.name.lower(), path.suffix.lower()
    folders = parts[:-1]
    if len(parts) == 1 and name == "panel.json":
        return "panel"
    if name.startswith("history") and ext in HISTORY_EXTS:
        return "history"
    if name.startswith("significance") and ext == ".json":
        return "significance"
    if "figures" in folders and ext in FIGURE_EXTS:
        return "figure"
    if ("tables" in folders and ext in TABLE_EXTS) or (len(parts) <= 2 and name == "summary.json"):
        return "table"
    return None


# --------------------------------------------------------------------------
# hyperparameter search
# --------------------------------------------------------------------------
def _scalar(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return _clip(value, 200)
    return _clip(json.dumps(value)[:200], 200)


def _importance(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    values = data.get("values")
    pairs = values.items() if isinstance(values, dict) else ()
    clean = {_clip(k, 80): n for k, v in list(pairs)[:MAX_HPO_PARAMS] if (n := _number(v)) is not None}
    return {"evaluator": _clip(data.get("evaluator"), 60) or None, "values": clean}


def _hpo_figure(root: Path, study: Path, value: Any, reader: _Reader) -> str | None:
    """A figure path relative to the study folder, kept only while it stays a
    contained figure file inside that folder."""
    if not isinstance(value, str) or not value:
        return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() not in FIGURE_EXTS:
        reader.warn(f"{reader.label(study)}: a figure path leaving its study folder was refused")
        return None
    candidate = study / relative
    status, _resolved, _size, _mtime = _locate(root, candidate, MAX_FILE_BYTES * 64)
    if status not in ("ok", "too_large"):
        if status != "unsafe":
            reader.warn(f"{reader.label(candidate)}: figure missing")
        return None
    return _rel(root, candidate)


def _hpo_studies(root: Path, results: Path, reader: _Reader) -> list[dict[str, Any]]:
    """One row per ``Results/hpo/<study>/summary.json`` (schema 1); never raises."""
    folder = results / "hpo"
    if not folder.is_dir() or folder.is_symlink():
        return []
    try:
        folder.resolve(strict=True).relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return []  # Results/ itself resolves outside the workspace.
    try:
        names = sorted(e.name for e in os.scandir(folder)
                       if e.is_dir(follow_symlinks=False) and not e.name.startswith("."))
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for name in names:
        study = folder / name
        path = study / "summary.json"
        if not path.is_file() and not path.is_symlink():
            continue
        if len(out) >= MAX_HPO_STUDIES:
            reader.warn(f"{reader.label(folder)}: studies capped at {MAX_HPO_STUDIES}")
            break
        data = reader.json(path)
        if data is None:
            continue
        if not isinstance(data, dict) or data.get("schema") != 1:
            reader.warn(f"{reader.label(path)}: not a schema-1 hyperparameter summary")
            continue
        objective = data.get("objective") if isinstance(data.get("objective"), dict) else {}
        params = data.get("bestParams") if isinstance(data.get("bestParams"), dict) else {}
        figures = data.get("figures") if isinstance(data.get("figures"), dict) else {}
        notes = data.get("notes") if isinstance(data.get("notes"), list) else []
        contour = data.get("contourParams") if isinstance(data.get("contourParams"), list) else []
        fold = data.get("fold")
        count = lambda key: int(n) if (n := _number(data.get(key))) is not None else None  # noqa: E731
        out.append({
            "study": _clip(data.get("study") or name, 120),
            "arm": _clip(data.get("arm"), 120),
            "fold": fold if isinstance(fold, int) and not isinstance(fold, bool) else None,
            "nTrials": count("nTrials"),
            "complete": count("complete"),
            "pruned": count("pruned"),
            "failed": count("failed"),
            "bestValue": _number(data.get("bestValue")),
            "bestParams": {_clip(k, 80): _scalar(v) for k, v in list(params.items())[:MAX_HPO_PARAMS]},
            "objective": {"metric": _clip(objective.get("metric"), 120) or None,
                          "direction": _clip(objective.get("direction"), 20) or None},
            "importance": _importance(data.get("importance")),
            "importanceCheck": _importance(data.get("importanceCheck")),
            "contourParams": [_clip(p, 80) for p in contour[:MAX_HPO_PARAMS] if isinstance(p, str)],
            "figures": {key: _hpo_figure(root, study, figures.get(key), reader) for key in HPO_FIGURES},
            "notes": [_clip(n) for n in notes[:MAX_HPO_NOTES] if isinstance(n, str)],
            "file": _rel(root, path),
        })
    return out


def _product_dirs(root: Path, reader: _Reader) -> list[tuple[str, Path]]:
    top = root / "implementations"
    if not top.is_dir():
        return []
    try:
        top.resolve(strict=True).relative_to(root)
    except (OSError, RuntimeError, ValueError):
        reader.warn("implementations/ is outside the workspace")
        return []
    out: list[tuple[str, Path]] = []
    try:
        repos = sorted(e.name for e in os.scandir(top) if e.is_dir(follow_symlinks=False)
                       and not e.name.startswith("."))
    except OSError:
        return []
    for repo in repos:
        try:
            names = sorted(e.name for e in os.scandir(top / repo) if e.is_dir(follow_symlinks=False)
                           and not e.name.startswith("."))
        except OSError:
            continue
        for name in names:
            folder = top / repo / name
            if any((folder / marker).is_file() for marker in ("AGREED.md", "Experimental_AGREED.md")) \
                    or (folder / "Results").is_dir():
                out.append((repo, folder))
                if len(out) >= MAX_PRODUCTS:
                    reader.warn(f"products capped at {MAX_PRODUCTS}")
                    return out
    return out


#: The approvals that call for an experiment diagram, in the order the operator
#: verifies them: the proof of concept, then the full experiments.
DIAGRAM_KINDS = (("poc", "AGREED.md"), ("experiments", "Experimental_AGREED.md"))
DIAGRAM_CLI = "skills/experiment-diagrams/scripts/diagram_cli.py"


def _diagrams(root: Path, repo: str, folder: Path, reader: _Reader) -> list[dict[str, Any]]:
    """One entry per approval the product holds, with the PNG and PDF that
    `experiment-diagrams` drew under ``<product>/diagrams/`` (``None`` when
    missing or linked outside the workspace) and the command that draws them."""
    out: list[dict[str, Any]] = []
    for kind, marker in DIAGRAM_KINDS:
        if not (folder / marker).is_file():
            continue
        files: dict[str, str | None] = {}
        for ext in ("png", "pdf"):
            path = folder / "diagrams" / f"{kind}.{ext}"
            files[ext] = _rel(root, path) if path.is_file() and reader.contained(path) else None
        spec = _rel(root, folder / "diagrams" / f"{kind}.json")
        command = (f"python3 {DIAGRAM_CLI} derive --target {shlex.quote(repo)} "
                   f"--name {shlex.quote(folder.name)} --kind {kind}"
                   f"{' --force' if files['png'] else ''} && "
                   f"python3 {DIAGRAM_CLI} render --spec {shlex.quote(spec)}")
        validation = diagram_cli().validation_state(folder, kind) if files["png"] else "absent"
        provenance = (diagram_cli().validation_provenance(folder, kind)
                      if validation == "validated" else None)
        out.append({"kind": kind, "approved": True, "marker": marker, "png": files["png"],
                    "pdf": files["pdf"], "command": command,
                    "slash": f"/experiment-diagrams {kind}",
                    "validation": validation,
                    # `chat` (the operator approved it in an agent conversation)
                    # or `dashboard` ("Validar diagrama"); `None` until validated.
                    "validatedVia": provenance["via"] if provenance else None})
    return out


def diagram_cli():
    """The kit's `diagram_cli.py`, the one owner of the validation record."""
    name = "papersmith_experiment_diagram_cli"
    if name not in sys.modules:
        script = Path(__file__).resolve().parents[2] / "experiment-diagrams" / "scripts" / "diagram_cli.py"
        spec = importlib.util.spec_from_file_location(name, script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def validate_diagram(root: Path, repo: str, name: str, kind: str) -> tuple[int, dict[str, Any]]:
    """The dashboard's "Validar diagrama": record the operator's validation of
    one drawn diagram of one listed product. Returns ``(http status, body)``."""
    markers = dict(DIAGRAM_KINDS)
    if kind not in markers:
        return 422, {"ok": False, "error": f"unknown diagram kind: {kind!r}"}
    reader = _Reader(root, [])
    folder = next((f for r, f in _product_dirs(root, reader) if r == repo and f.name == name), None)
    if folder is None:
        return 404, {"ok": False, "error": f"no product {repo}/{name} under implementations/"}
    if not (folder / markers[kind]).is_file():
        return 409, {"ok": False, "error": f"{markers[kind]} is absent: nothing to validate yet"}
    png = folder / "diagrams" / f"{kind}.png"
    if not png.is_file() or not reader.contained(png):
        return 409, {"ok": False, "error": "the diagram has not been drawn yet"}
    cli = diagram_cli()
    try:
        record = cli.write_validation(folder, kind)
    except cli.Refusal as exc:
        return 409, {"ok": False, "error": str(exc)}
    return 200, {"ok": True, "validation": "validated", "record": record}


STAGE_DURATIONS_FULL: dict[str, int] = {
    "hpo_search": 2100,
    "full_time_probe": 900,
    "e1_run": 6300,
    "e2_run": 3000,
    "e3_run": 4800,
    "e3_gradvar": 60,
    "e4_saliency": 480,
    "e1_report": 90,
    "e2_report": 90,
    "e3_report": 90,
    "e4_report": 90,
}

STAGE_DURATIONS_POC: dict[str, int] = {
    "time_probe": 120,
    "poc_train": 900,
    "poc_report": 120,
    "e5_time_probe": 180,
    "e5_run_fixed": 1500,
    "e5_run_end_to_end": 2400,
    "e5_report": 180,
}


def _format_duration_label(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    mins = int(round(seconds / 60))
    hrs = mins // 60
    rem_mins = mins % 60
    if hrs > 0:
        return f"{hrs}h {rem_mins}m" if rem_mins > 0 else f"{hrs}h"
    return f"{mins}m"


def _execution_monitor(root: Path, folder: Path, kind: str, ledger: Path | None,
                       reader: _Reader) -> dict[str, Any] | None:
    """Track the execution ladder (PoC or Full), estimating stage durations, remaining time, and ETA."""
    agreed_file = folder / ("Experimental_AGREED.md" if kind == "full" else "AGREED.md")
    if not agreed_file.is_file():
        fallback = folder / ("AGREED.md" if kind == "full" else "Experimental_AGREED.md")
        if fallback.is_file():
            agreed_file = fallback
            kind = "poc" if agreed_file.name == "AGREED.md" else "full"
        else:
            return None

    text = reader.text(agreed_file)
    if not text:
        return None

    durations = STAGE_DURATIONS_FULL if kind == "full" else STAGE_DURATIONS_POC

    active_steps: set[str] = set()
    if ledger and ledger.is_file():
        try:
            raw_ledger = reader.text(ledger, cap=LEDGER_MAX_BYTES)
            if raw_ledger:
                for line in raw_ledger.splitlines():
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if entry.get("kind") == "submitted":
                        ep = entry.get("entrypoint", "")
                        step_stem = Path(ep).parent.name if "/" in ep else ""
                        if step_stem:
                            active_steps.add(step_stem)
                    elif entry.get("kind") in ("returned", "errored"):
                        ep = entry.get("entrypoint", "")
                        step_stem = Path(ep).parent.name if "/" in ep else ""
                        active_steps.discard(step_stem)
        except Exception:
            pass

    stages: list[dict[str, Any]] = []
    line_re = re.compile(r"^\s*-\s*\[([ x])\]\s*(\d+)\.\s*(.*?)(?:\s*`?@([a-z]+)\s+([^`\s]+)`?)?\s*$")
    for line in text.splitlines():
        m = line_re.match(line)
        if not m:
            continue
        checked = (m.group(1) == "x")
        idx = int(m.group(2))
        desc = m.group(3).strip()
        step_type = m.group(4) or "step"
        raw_tag = m.group(5) or ""
        tag = re.sub(r"[^a-zA-Z0-9_\-\./]", "", raw_tag)
        step_stem = Path(tag).stem if tag else ""

        if step_type == "rehearsal":
            sec = 660
            category = "smoke"
        elif "report" in step_stem:
            sec = 90
            category = "report"
        elif "gradvar" in step_stem:
            sec = 60
            category = "analysis"
        elif "saliency" in step_stem:
            sec = 480
            category = "analysis"
        else:
            sec = durations.get(step_stem, 1800)
            category = "training" if ("run" in step_stem or "train" in step_stem) else "probe"

        is_running = not checked and (step_stem in active_steps or any(step_stem in s for s in active_steps))
        status = "completed" if checked else ("running" if is_running else "pending")

        stages.append({
            "index": idx,
            "name": desc,
            "category": category,
            "kind": step_type,
            "tag": tag,
            "step": step_stem,
            "status": status,
            "estimated_seconds": sec,
            "estimated_duration": _format_duration_label(sec),
        })

    if not stages:
        return None

    total_stages = len(stages)
    completed_stages = sum(1 for s in stages if s["status"] == "completed")
    progress_percent = round((completed_stages / total_stages) * 100, 1) if total_stages else 0.0
    remaining_seconds = sum(s["estimated_seconds"] for s in stages if s["status"] != "completed")

    now = datetime.now(timezone.utc)
    completion_dt = now + timedelta(seconds=remaining_seconds) if remaining_seconds > 0 else now
    estimated_completion_iso = completion_dt.isoformat()
    estimated_completion_label = completion_dt.strftime("%Y-%m-%d %H:%M UTC")

    overall_status = "completed" if completed_stages == total_stages else (
        "running" if any(s["status"] == "running" for s in stages) else "in_progress"
    )

    current_stage = next((s["name"] for s in stages if s["status"] == "running"), None)
    if not current_stage:
        current_stage = next((s["name"] for s in stages if s["status"] == "pending"), None)

    return {
        "kind": kind,
        "status": overall_status,
        "current_stage": current_stage,
        "total_stages": total_stages,
        "completed_stages": completed_stages,
        "progress_percent": progress_percent,
        "remaining_seconds": remaining_seconds,
        "remaining_duration": _format_duration_label(remaining_seconds),
        "estimated_completion_iso": estimated_completion_iso,
        "estimated_completion_label": estimated_completion_label,
        "stages": stages,
    }


def _product(root: Path, repo: str, folder: Path, ledger: Path | None,
             global_warnings: list[str]) -> dict[str, Any]:
    warnings: list[str] = []
    reader = _Reader(root, warnings)
    if (folder / "Experimental_AGREED.md").is_file():
        kind = "full"
    elif (folder / "AGREED.md").is_file():
        kind = "poc"
    else:
        kind = "unknown"
    results = folder / "Results"
    files, cut = _scan(results, MAX_FILES_PER_PRODUCT, skip=("hpo",),
                       keep=lambda path: _result_kind(results, path) is not None)
    if cut == "kept":
        reader.warn(f"{reader.label(results)}: only the first {MAX_FILES_PER_PRODUCT} files were scanned")
    elif cut == "visited":
        reader.warn(f"{reader.label(results)}: the scan stopped after {MAX_SCANNED_FILES} files were visited")
    convergence: list[dict[str, Any]] = []
    figures: list[str] = []
    tables: list[dict[str, Any]] = []
    significance: list[dict[str, Any]] = []
    panel: Path | None = None
    for path in files:
        if not reader.contained(path):
            continue  # A symlink leaving the workspace is ignored outright.
        role = _result_kind(results, path)
        if role == "panel":
            panel = path
        elif role == "history":
            if len(convergence) < MAX_HISTORIES:
                entry = _read_history(path, reader)
                if entry:
                    convergence.append(entry)
        elif role == "significance":
            significance.extend(_read_significance(path, reader))
        elif role == "figure":
            if len(figures) < MAX_FIGURES:
                figures.append(_rel(root, path))
        elif role == "table":
            if len(tables) < MAX_TABLES:
                table = _read_table(path, reader)
                if table:
                    tables.append(table)
    timing = None
    timing_path = results / "timing.json"
    if timing_path.is_file() or timing_path.is_symlink():
        timing = parse_timing(reader.json(timing_path))
        if timing is not None:
            timing["file"] = _rel(root, timing_path)
        else:
            reader.warn(f"{reader.label(timing_path)}: not a schema 1 or 2 timing record")
    placement_plan = _placement_plan(root, folder, reader)
    hpo = _hpo_studies(root, results, reader)
    reviewer = None
    for rev_candidate in ("reviewer_report.json", "reviewer-report.json"):
        rev_path = results / rev_candidate
        if rev_path.is_file() or rev_path.is_symlink():
            rev_data = reader.json(rev_path)
            if isinstance(rev_data, dict):
                reviewer = rev_data
                reviewer["file"] = _rel(root, rev_path)
                break
    for message in warnings:
        if len(global_warnings) < MAX_WARNINGS:
            global_warnings.append(message)
    return {
        "repo": repo,
        "name": folder.name,
        "kind": kind,
        "path": _rel(root, folder),
        "convergence": convergence,
        "figures": figures,
        "tables": tables,
        "significance": significance[:MAX_SIGNIFICANCE_ROWS],
        "pinned": _pinned(root, folder, reader, panel),
        "runs": _fold_runs(root, ledger, reader),
        "remote_workers": _fold_workers(root, ledger),
        "timing": timing,
        "placement_plan": placement_plan,
        "hpo": hpo,
        "reviewer": reviewer,
        "diagrams": _diagrams(root, repo, folder, reader),
        "execution_monitor": _execution_monitor(root, folder, kind, ledger, reader),
        "warnings": warnings,
    }


#: `plan-<date>.json` or `plan-<date>-<n>.json`, as `remote-parallelism plan --record` names them.
_PLAN_RECORD = re.compile(r"^plan-(\d{4}-\d{2}-\d{2})(?:-(\d+))?\.json$")


def _placement_plan(root: Path, folder: Path, reader: Any) -> dict[str, Any] | None:
    """The latest `plan` recorded in the product's `.remote-parallelism/`, reduced."""
    records = folder / ".remote-parallelism"
    if not records.is_dir():
        return None  # Each record is vetted below: one resolving outside the workspace is skipped.
    found = []
    for path in records.iterdir():
        match = _PLAN_RECORD.match(path.name)
        if match and path.is_file() and reader.contained(path):
            found.append(((match.group(1), int(match.group(2) or 1)), path))
    if not found:
        return None
    path = max(found)[1]
    plan = parse_plan(reader.json(path))
    if plan is None:
        reader.warn(f"{reader.label(path)}: not a remote-parallelism plan record")
        return None
    plan["file"] = _rel(root, path)
    return plan


def _remote_accounts(root: Path) -> dict[str, Any]:
    store = credentials_store(root)
    inbox_name = inbox_directory(root)
    count = 0
    if inbox_name:
        try:
            with os.scandir(root / inbox_name) as entries:
                for entry in entries:
                    if entry.name.endswith(".json") and entry.is_file(follow_symlinks=False):
                        count += 1
        except OSError:
            pass
    return {"accounts_store_present": bool(store and store.is_file()),
            "inbox": inbox_name, "inbox_count": count}


def _datasets(root: Path, reader: _Reader) -> dict[str, Any]:
    """The ``datasets`` registry as one row per dataset; never raises."""
    folder = root / "datasets"
    path = folder / "registry.json"
    out: dict[str, Any] = {"registry": None, "items": [], "searches": []}
    if not path.is_file() and not path.is_symlink():
        return out
    data = reader.json(path)
    if isinstance(data, list):
        out["registry"] = _rel(root, path)
        for entry in data[:MAX_DATASETS]:
            if not isinstance(entry, dict) or not isinstance(entry.get("slug"), str):
                continue
            pick = lambda key: entry.get(key) if isinstance(entry.get(key), dict) else {}  # noqa: E731
            lic, qc, prep, remote = pick("license"), pick("qc"), pick("preparation"), pick("remote")
            out["items"].append({
                "slug": _clip(entry["slug"], 80),
                "role": _clip(entry.get("role"), 20),
                "title": _clip(entry.get("title"), 200),
                "license": lic.get("decision") or None,
                "host_license": lic.get("host_license") or None,
                "qc": qc.get("status") or None,
                "prepared": bool(prep),
                "preparation_version": prep.get("version"),
                "remote_ref": remote.get("ref") or None,
                "visibility": remote.get("visibility") or None,
                "remote_version": remote.get("version"),
            })
        out["items"].sort(key=lambda item: item["slug"])
    elif data is not None:
        reader.warn(f"{_rel(root, path)}: not a list")
    try:
        searches = sorted((p for p in folder.glob("search-*.json") if reader.contained(p)),
                          key=lambda p: (p.stat().st_mtime, p.name))
    except OSError:
        searches = []
    out["searches"] = [_rel(root, p) for p in searches[-MAX_SEARCHES:]]
    return out


def get_experiments_view(root: Path | str) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    warnings: list[str] = []
    reader = _Reader(root, warnings)
    protocol = _parse_protocol(root, reader)
    ledgers, _cut, _escaped = _discover_ledgers(root)
    by_folder = {path.parent.parent: path for path in ledgers}
    products = [_product(root, repo, folder, by_folder.get(folder), warnings)
                for repo, folder in _product_dirs(root, reader)]
    view = {"protocol": protocol, "products": products, "datasets": _datasets(root, reader),
            "remote_accounts": _remote_accounts(root),
            "remote_mcp": remote_mcp_status(root), "remote_colab": colab_mcp_status(root),
            "remote_services": remote_services(root),
            "warnings": warnings}
    try:
        view["local_environment"] = local_environment(root)
    except Exception:  # noqa: BLE001 - a failing probe is an empty table, never an error
        view["local_environment"] = {"workspace": None, "targets": [], "note": "No se pudo sondear."}
    try:
        view["run_options"] = run_options(root, view)
    except Exception:  # noqa: BLE001
        view["run_options"] = {"rows": [], "recommendations": {}, "note": "", "sources": [],
                               "empty": True, "empty_hint": ""}
    return view
