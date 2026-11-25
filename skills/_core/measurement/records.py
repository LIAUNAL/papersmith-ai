"""Side-effect-free readers of the measurement core's records.

The board, the Study panel and the gates import these; none of them writes,
creates a directory or calls a model. ``measure_cli.py`` is the only writer.

    study/instruments.json          every instrument record, history kept
    study/measurements.json         every registration of a raw data file, bound by sha256
    study/uncertainty/<q>.json      the uncertainty budgets of quantity <q>, one per condition set
    study/agreement.json            device-versus-reference agreement analyses

A budget or an agreement analysis is bound to the sha256 of its input files
and to the instrument record it used: when one of them changes it is
``stale`` and names why. Decision F1 of ``odd/tasks/paper-type-lines.md``.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import math
import re
from pathlib import Path

from ..empirical.records import StudyError, sha256

MeasurementError = StudyError

SCHEMA = 1
INSTRUMENTS_PATH = "study/instruments.json"
DATA_PATH = "study/measurements.json"
UNCERTAINTY_DIR = "study/uncertainty"
AGREEMENT_PATH = "study/agreement.json"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
ENTRY_META = ("by", "at", "reason")


def _load(root: Path, relative: str, code: str, key: str) -> dict | None:
    path = Path(root) / relative
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MeasurementError(code, f"{relative} cannot be read as JSON ({exc})") from None
    if not (isinstance(data, dict) and isinstance(data.get(key), list)
            and all(isinstance(item, dict) for item in data[key])):
        raise MeasurementError(code, f"{relative} is not a measurement record: a \"{key}\" list of objects")
    return data


def entry_digest(entry: dict) -> str:
    """sha256 of an instrument entry's canonical JSON: a budget binds the exact record it used."""
    return hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- instruments


def read_instruments(root: Path) -> dict:
    """The instrument history, empty when absent; ``INSTRUMENTS_CORRUPT`` when malformed."""
    data = _load(root, INSTRUMENTS_PATH, "INSTRUMENTS_CORRUPT", "history")
    if data is None:
        return {"schema": SCHEMA, "history": []}
    if not all(isinstance(entry.get("id"), str) for entry in data["history"]):
        raise MeasurementError("INSTRUMENTS_CORRUPT", f"{INSTRUMENTS_PATH} holds an entry without an id")
    return data


def current_instruments(history: list[dict]) -> dict[str, tuple[dict, int]]:
    """id -> (its latest entry, how many entries it has)."""
    out: dict[str, tuple[dict, int]] = {}
    for entry in history:
        out[entry["id"]] = (entry, out.get(entry["id"], (None, 0))[1] + 1)
    return out


def calibration_state(entry: dict, on: dt.date) -> str:
    """``current`` up to and including the due date, ``past-due`` after it."""
    try:
        due = dt.date.fromisoformat(str(entry.get("due")))
    except ValueError:
        return "unknown"
    return "current" if on <= due else "past-due"


def instruments_state(root: Path, on: dt.date | None = None) -> dict:
    """``absent``, ``corrupt`` or ``recorded`` with every instrument's latest entry and its
    calibration state on ``on`` (today by default)."""
    try:
        history = read_instruments(root)["history"]
    except MeasurementError as error:
        return {"state": "corrupt", "message": error.message}
    if not history:
        return {"state": "absent"}
    on = on or dt.date.today()
    rows = []
    for ident, (entry, count) in current_instruments(history).items():
        rows.append({**entry, "calibration": calibration_state(entry, on), "entries": count,
                     "entry_sha256": entry_digest(entry)})
    return {"state": "recorded", "on": on.isoformat(), "instruments": rows,
            "past_due": [row["id"] for row in rows if row["calibration"] == "past-due"]}


# --------------------------------------------------------------------------- raw data files


def read_data(root: Path) -> dict:
    """The registrations of raw data files, empty when absent; ``DATA_REGISTRY_CORRUPT`` when malformed."""
    data = _load(root, DATA_PATH, "DATA_REGISTRY_CORRUPT", "registrations")
    if data is None:
        return {"schema": SCHEMA, "registrations": []}
    if not all(isinstance(entry.get("path"), str) and isinstance(entry.get("sha256"), str)
               for entry in data["registrations"]):
        raise MeasurementError("DATA_REGISTRY_CORRUPT", f"{DATA_PATH} holds a registration without a path or sha256")
    return data


def current_registrations(registrations: list[dict]) -> dict[str, dict]:
    """path -> its latest registration, in first-registration order."""
    out: dict[str, dict] = {}
    for entry in registrations:
        out[entry["path"]] = entry
    return out


def file_state(root: Path, entry: dict) -> str:
    """``current`` (the bytes hash as registered), ``changed`` or ``missing``."""
    path = Path(root) / entry["path"]
    if not path.is_file():
        return "missing"
    return "current" if sha256(path) == entry["sha256"] else "changed"


def data_state(root: Path) -> dict:
    try:
        registrations = read_data(root)["registrations"]
    except MeasurementError as error:
        return {"state": "corrupt", "message": error.message, "files": []}
    if not registrations:
        return {"state": "absent", "files": []}
    files = []
    for entry in current_registrations(registrations).values():
        files.append({key: entry.get(key) for key in ("path", "sha256", "rows", "quantity", "unit", "value_column",
                                                      "replicate_column", "instrument", "conditions", "by", "at")}
                     | {"state": file_state(root, entry)})
    return {"state": "recorded", "files": files}


def read_csv(path: Path, shown: str) -> tuple[list[str], list[list[str]]]:
    """Header and data rows of a CSV the operator produced; ``CSV_INVALID`` or ``CSV_EMPTY``."""
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise MeasurementError("CSV_INVALID", f"{shown} cannot be read as UTF-8 text ({exc})") from None
    try:
        rows = [row for row in csv.reader(io.StringIO(text)) if any(cell.strip() for cell in row)]
    except csv.Error as exc:
        raise MeasurementError("CSV_INVALID", f"{shown} is not a CSV file ({exc})") from None
    if not rows:
        raise MeasurementError("CSV_EMPTY", f"{shown} has no header row")
    header = [cell.strip() for cell in rows[0]]
    if any(not name for name in header) or len(set(header)) != len(header):
        raise MeasurementError("CSV_INVALID", f"{shown} needs a header of distinct, non-empty column names")
    body = rows[1:]
    if not body:
        raise MeasurementError("CSV_EMPTY", f"{shown} has a header and no data row")
    for number, row in enumerate(body, start=2):
        if len(row) != len(header):
            raise MeasurementError("CSV_INVALID", f"{shown} row {number} has {len(row)} cells, the header {len(header)}")
    return header, body


def column(header: list[str], body: list[list[str]], name: str, shown: str) -> list[str]:
    if name not in header:
        raise MeasurementError("COLUMN_ABSENT", f"{shown} has no column {name!r}; its columns are {', '.join(header)}")
    index = header.index(name)
    return [row[index].strip() for row in body]


def numbers(cells: list[str], name: str, shown: str) -> list[float]:
    """The column's cells as finite numbers; ``VALUE_INVALID`` names the first that is not one.
    A missing value is refused, never dropped: the core does not edit measured data."""
    out = []
    for number, cell in enumerate(cells, start=2):
        try:
            value = float(cell)
        except ValueError:
            value = math.nan
        if not math.isfinite(value):
            raise MeasurementError("VALUE_INVALID", f"{shown} row {number}, column {name!r}: {cell!r} is not a "
                                                    "finite number (the operator fixes the file; the core never "
                                                    "edits or drops a measured value)")
        out.append(value)
    return out


def unique_ids(cells: list[str], name: str, shown: str, code: str) -> None:
    seen = set()
    for number, cell in enumerate(cells, start=2):
        if not cell:
            raise MeasurementError(code, f"{shown} row {number}: column {name!r} is empty")
        if cell in seen:
            raise MeasurementError(code, f"{shown} row {number}: {name} {cell!r} appears twice")
        seen.add(cell)


def select_files(registrations: dict[str, dict], quantity: str, conditions: dict | None) -> list[dict]:
    """The current registrations of ``quantity``: those with exactly ``conditions`` when given,
    otherwise all of them, which must then share one condition set (``CONDITIONS_MIXED``)."""
    chosen = [entry for entry in registrations.values() if entry.get("quantity") == quantity
              and (conditions is None or (entry.get("conditions") or {}) == conditions)]
    if not chosen:
        where = "" if conditions is None else f" under {condition_label(conditions) or 'no condition'}"
        raise MeasurementError("DATA_ABSENT", f"no registered raw data file holds {quantity!r}{where}; the operator "
                                              "registers one with `data register`")
    sets = {condition_label(entry.get("conditions") or {}) for entry in chosen}
    if len(sets) > 1:
        raise MeasurementError("CONDITIONS_MIXED", f"the files of {quantity!r} were measured under different "
                                                   f"conditions ({'; '.join(sorted(sets))}); name one set with "
                                                   "--condition key=value")
    return chosen


def condition_label(conditions: dict) -> str:
    return ", ".join(f"{key}={conditions[key]}" for key in sorted(conditions))


# --------------------------------------------------------------------------- budgets


def budget_path(quantity: str) -> str:
    return f"{UNCERTAINTY_DIR}/{quantity}.json"


def read_budgets(root: Path, quantity: str) -> dict:
    data = _load(root, budget_path(quantity), "UNCERTAINTY_CORRUPT", "budgets")
    return data if data is not None else {"schema": SCHEMA, "quantity": quantity, "budgets": []}


def _input_reasons(root: Path, bound: list[dict], registrations: dict[str, dict]) -> list[str]:
    reasons = []
    for item in bound:
        path = Path(root) / item["path"]
        if not path.is_file():
            reasons.append("input-missing")
        elif sha256(path) != item["sha256"]:
            reasons.append("input-changed")
        elif (registrations.get(item["path"]) or {}).get("sha256") != item["sha256"]:
            reasons.append("registration-changed")
    return list(dict.fromkeys(reasons))


def budget_staleness(root: Path, budget: dict, registrations: dict[str, dict],
                     instruments: dict[str, tuple[dict, int]]) -> list[str]:
    """Why a budget no longer matches its inputs; empty when it is current."""
    bound = budget.get("inputs", {}).get("files") or []
    reasons = _input_reasons(root, bound, registrations)
    try:
        selected = {entry["path"] for entry in select_files(registrations, budget.get("quantity"),
                                                            budget.get("conditions") or {})}
    except MeasurementError:
        selected = set()
    if selected - {item["path"] for item in bound}:
        reasons.append("inputs-added")
    instrument = budget.get("inputs", {}).get("instrument") or {}
    current = instruments.get(instrument.get("id"))
    if current is None or entry_digest(current[0]) != instrument.get("entry_sha256"):
        reasons.append("instrument-changed")
    return reasons


def budget_state(root: Path) -> dict:
    """Every stored budget with ``state`` ``current`` or ``stale`` (``reasons``), or ``corrupt``."""
    folder = Path(root) / UNCERTAINTY_DIR
    files = sorted(folder.glob("*.json")) if folder.is_dir() else []
    if not files:
        return {"state": "absent", "budgets": []}
    try:
        registrations = current_registrations(read_data(root)["registrations"])
        instruments = current_instruments(read_instruments(root)["history"])
    except MeasurementError as error:
        return {"state": "corrupt", "message": error.message, "budgets": []}
    rows = []
    for path in files:
        quantity = path.stem
        try:
            budgets = read_budgets(root, quantity)["budgets"]
        except MeasurementError as error:
            rows.append({"quantity": quantity, "state": "corrupt", "message": error.message})
            continue
        for budget in budgets:
            reasons = budget_staleness(root, budget, registrations, instruments)
            rows.append({key: budget.get(key) for key in (
                "quantity", "unit", "conditions", "computed_at", "combined_standard_uncertainty", "effective_dof",
                "expanded_uncertainty")}
                | {"mean": (budget.get("type_a") or {}).get("mean"), "n": (budget.get("type_a") or {}).get("n"),
                   "coverage": budget.get("coverage"), "calibration": budget.get("calibration"),
                   "state": "stale" if reasons else "current", "reasons": reasons})
    return {"state": "recorded", "budgets": rows}


# --------------------------------------------------------------------------- agreement


_ROLE_REASON = {"input-missing": "missing", "input-changed": "changed", "registration-changed": "reregistered"}


def read_agreement(root: Path) -> dict:
    data = _load(root, AGREEMENT_PATH, "AGREEMENT_CORRUPT", "analyses")
    return data if data is not None else {"schema": SCHEMA, "analyses": []}


def agreement_state(root: Path) -> dict:
    """Every agreement analysis with ``state`` ``current`` or ``stale`` (``reasons``: ``device-``
    or ``reference-`` ``changed``, ``missing`` or ``reregistered``)."""
    try:
        analyses = read_agreement(root)["analyses"]
        registrations = current_registrations(read_data(root)["registrations"])
    except MeasurementError as error:
        return {"state": "corrupt", "message": error.message, "analyses": []}
    if not analyses:
        return {"state": "absent", "analyses": []}
    rows = []
    for analysis in analyses:
        reasons = []
        for role in ("device", "reference"):
            bound = analysis.get(role) or {}
            found = _input_reasons(root, [bound], registrations) if bound.get("path") else ["input-missing"]
            reasons.extend(f"{role}-{_ROLE_REASON[reason]}" for reason in found)
        rows.append({key: analysis.get(key) for key in ("device", "reference", "pair_column", "quantity", "unit",
                                                        "n", "bland_altman", "icc", "computed_at")}
                    | {"state": "stale" if reasons else "current", "reasons": reasons})
    return {"state": "recorded", "analyses": rows}


# --------------------------------------------------------------------------- everything


def measurement_status(root: Path, on: dt.date | None = None) -> dict:
    """Instruments, data files, budgets and agreement analyses, and every warning."""
    instruments = instruments_state(root, on)
    data = data_state(root)
    budgets = budget_state(root)
    agreement = agreement_state(root)
    warnings = []
    for code, state in (("INSTRUMENTS_CORRUPT", instruments), ("DATA_REGISTRY_CORRUPT", data),
                        ("UNCERTAINTY_CORRUPT", budgets), ("AGREEMENT_CORRUPT", agreement)):
        if state["state"] == "corrupt":
            warnings.append({"code": code, "message": state["message"]})
    for ident in instruments.get("past_due", []):
        warnings.append({"code": "CALIBRATION_PAST_DUE", "message": f"instrument {ident} is past its calibration "
                                                                    f"due date on {instruments['on']}"})
    for item in data["files"]:
        if item["state"] != "current":
            warnings.append({"code": f"DATA_{item['state'].upper()}",
                             "message": f"{item['path']} is {item['state']} since its registration; every "
                                        "computation based on it is stale"})
    for budget in budgets["budgets"]:
        if budget["state"] == "corrupt":
            warnings.append({"code": "UNCERTAINTY_CORRUPT", "message": budget["message"]})
        elif budget["state"] == "stale":
            label = condition_label(budget.get("conditions") or {})
            warnings.append({"code": "BUDGET_STALE", "message": f"the budget of {budget['quantity']}"
                                                                f"{' (' + label + ')' if label else ''} is stale "
                                                                f"({', '.join(budget['reasons'])}); recompute it"})
    for analysis in agreement["analyses"]:
        if analysis["state"] == "stale":
            warnings.append({"code": "AGREEMENT_STALE",
                             "message": f"the agreement of {(analysis['device'] or {}).get('path')} with "
                                        f"{(analysis['reference'] or {}).get('path')} is stale "
                                        f"({', '.join(analysis['reasons'])}); recompute it"})
    return {"instruments": instruments, "data": data, "uncertainty": budgets, "agreement": agreement,
            "warnings": warnings}
