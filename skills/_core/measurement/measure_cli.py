#!/usr/bin/env python3
"""Measurement core: instruments, raw data files, uncertainty budgets, device agreement.

    measure_cli.py instrument add --id <id> --model <text> --serial <text> --resolution "<value> <unit>" \
        [--stated-uncertainty "<value> <unit>" --distribution normal|rectangular [--coverage-k <k>]] \
        --calibration-certificate <text> --calibrated <YYYY-MM-DD> --due <YYYY-MM-DD> \
        [--reason <why the record changes>] --by <operator> --root .
    measure_cli.py instrument status [--on <YYYY-MM-DD>] --root .
    measure_cli.py data register --file <csv> --quantity <name> --unit <unit> --instrument <id> \
        [--value-column <col>] [--replicate-column <col>] [--condition key=value]... \
        [--reason <why it is registered again>] --by <operator> --root .
    measure_cli.py data status --root .
    measure_cli.py uncertainty compute --quantity <name> [--condition key=value]... \
        [--sensitivity <component>=<c>]... [--coverage-k <k> | --level <p>] \
        [--allow-past-due --by <operator> --reason <text>] --root .
    measure_cli.py uncertainty status --root .
    measure_cli.py agreement compute --device-file <csv> --reference-file <csv> --pair-column <col> \
        [--value-column <col>] --root .
    measure_cli.py agreement status --root .
    measure_cli.py status [--on <YYYY-MM-DD>] --root .

The operator produces every measured value: ``data register`` binds a CSV the
operator produced by its sha256 and never writes into it, and no verb writes
or edits a measured value. ``uncertainty compute`` evaluates a direct
measurement Y = mean of the readings (JCGM 100:2008): type A from the
replicates, type B from the instrument (its stated uncertainty and its
resolution), combined with sensitivity coefficients, Welch-Satterthwaite
effective degrees of freedom and an expanded uncertainty with k from the t
distribution at ``--level`` (default 0.95) or a declared ``--coverage-k``.
``agreement compute`` pairs a device's file with a reference device's file
(Bland-Altman and ICC(2,1)). Every computation is bound to the hashes of its
inputs; a changed file or instrument record makes it stale (``status``).
Decision F1 of ``odd/tasks/paper-type-lines.md``; formulas in README.md.

Each verb prints one JSON object. A refusal prints ``{"ok": false, "error":
<CODE>, "message": ...}`` and exits 1 (usage errors exit 2). Refusal codes:
``USAGE``, ``APPROVER_MISSING``, ``FIELD_MISSING``, ``FIELDS_CONFLICT``,
``REASON_MISSING``, ``TEXT_INVALID``, ``DATE_INVALID``, ``DATE_ORDER``,
``INSTRUMENT_ID_INVALID``, ``QUANTITY_NAME_INVALID``, ``MAGNITUDE_INVALID``,
``COVERAGE_INVALID``, ``LEVEL_INVALID``, ``CONDITION_INVALID``,
``SENSITIVITY_INVALID``, ``COMPONENT_UNKNOWN``, ``INSTRUMENT_EXISTS``,
``INSTRUMENT_UNKNOWN``, ``INSTRUMENTS_MIXED``, ``RECORD_UNCHANGED``,
``PATH_OUTSIDE_WORKSPACE``, ``FILE_ABSENT``, ``CSV_INVALID``, ``CSV_EMPTY``,
``COLUMN_ABSENT``, ``VALUE_INVALID``, ``REPLICATE_DUPLICATE``,
``DATA_ALREADY_REGISTERED``, ``DATA_NOT_REGISTERED``, ``DATA_ABSENT``,
``DATA_CHANGED``, ``DATA_MISSING``, ``CONDITIONS_MIXED``, ``UNIT_MISMATCH``,
``QUANTITY_MISMATCH``, ``REPLICATES_TOO_FEW``, ``CALIBRATION_PAST_DUE``,
``PAIR_DUPLICATE``, ``PAIRS_TOO_FEW``, ``INSTRUMENTS_CORRUPT``,
``DATA_REGISTRY_CORRUPT``, ``UNCERTAINTY_CORRUPT``, ``AGREEMENT_CORRUPT``,
``INTERNAL_ERROR``.
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
import json
import math
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make `skills._core.measurement` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from skills._core.empirical.study_cli import _atomic_write, _date, _now, _operator, _out, _Parser, _text  # noqa: E402
    from skills._core.measurement import records, stats  # noqa: E402
else:
    from ..empirical.study_cli import _atomic_write, _date, _now, _operator, _out, _Parser, _text
    from . import records, stats

MeasurementError = records.MeasurementError
DEFAULT_LEVEL = 0.95
MIN_PAIRS = 3


def _write_json(root: Path, relative: str, data) -> None:
    _atomic_write(root / relative, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _required(args, fields: tuple[tuple[str, str], ...]) -> None:
    missing = [flag for key, flag in fields if not (getattr(args, key) or "").strip()]
    if missing:
        raise MeasurementError("FIELD_MISSING", f"this record needs {', '.join(missing)}")


def _name(value: str, flag: str, code: str) -> str:
    value = (value or "").strip()
    if not records.NAME.match(value):
        raise MeasurementError(code, f"{flag} {value!r} must be 1-64 letters, digits, '_' or '-', starting with a "
                                     "letter or digit")
    return value


def _finite(text: str, flag: str, code: str, positive: bool = False) -> float:
    try:
        value = float(text)
    except (TypeError, ValueError):
        value = math.nan
    if not math.isfinite(value) or (positive and value <= 0):
        raise MeasurementError(code, f"{flag} {text!r} is not a {'positive ' if positive else ''}finite number")
    return value


def _magnitude(text: str, flag: str) -> dict:
    parts = (text or "").split()
    if len(parts) != 2:
        raise MeasurementError("MAGNITUDE_INVALID", f"{flag} {text!r} is written \"<value> <unit>\", e.g. \"0.01 mm\"")
    return {"value": _finite(parts[0], flag, "MAGNITUDE_INVALID", positive=True), "unit": _text(parts[1], flag)}


def _pairs(items: list[str], flag: str, code: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key or not value or key in out:
            raise MeasurementError(code, f"{flag} {item!r} is written key=value, each key once")
        out[_text(key, flag)] = _text(value, flag)
    return out


def _workspace_file(root: Path, given: str, flag: str) -> tuple[Path, str]:
    candidate = Path(given) if Path(given).is_absolute() else root / given
    resolved, base = candidate.resolve(), root.resolve()
    if base not in resolved.parents:
        raise MeasurementError("PATH_OUTSIDE_WORKSPACE", f"{flag} {given} is outside the workspace {base}")
    if not resolved.is_file():
        raise MeasurementError("FILE_ABSENT", f"{flag} {given} is not a file")
    return resolved, resolved.relative_to(base).as_posix()


def _append_history(entries: list[dict], match, entry: dict, reason: str | None, by: str,
                    exists_code: str, subject: str) -> None:
    """Append ``entry``: identical to the latest matching one refuses, a change needs ``reason``."""
    previous = [item for item in entries if match(item)]
    if previous:
        if {k: v for k, v in previous[-1].items() if k not in records.ENTRY_META} == entry:
            raise MeasurementError("RECORD_UNCHANGED", f"{subject} is already recorded with these values")
        if not reason:
            raise MeasurementError(exists_code, f"{subject} is already recorded; --reason states why its record "
                                                "changes (the history keeps every earlier entry)")
    elif reason is not None:
        raise MeasurementError("FIELDS_CONFLICT", f"--reason goes with a change to an existing record; {subject} "
                                                  "has none")
    entries.append({"by": by, "at": _now(), **entry, **({"reason": reason} if previous else {})})


# --------------------------------------------------------------------------- instruments

INSTRUMENT_FIELDS = (("id", "--id"), ("model", "--model"), ("serial", "--serial"), ("resolution", "--resolution"),
                     ("calibration_certificate", "--calibration-certificate"), ("calibrated", "--calibrated"),
                     ("due", "--due"))


def cmd_instrument(args, root: Path) -> dict:
    if args.action == "status":
        on = dt.date.fromisoformat(_date(args.on, "--on")) if args.on else None
        return {"ok": True, "instruments": records.instruments_state(root, on)}
    by = _operator(args)
    _required(args, INSTRUMENT_FIELDS)
    ident = _name(args.id, "--id", "INSTRUMENT_ID_INVALID")
    stated = None
    if args.stated_uncertainty is None:
        if args.distribution or args.coverage_k is not None:
            raise MeasurementError("FIELDS_CONFLICT", "--distribution and --coverage-k describe "
                                                      "--stated-uncertainty, which is not given")
    else:
        stated = _magnitude(args.stated_uncertainty, "--stated-uncertainty")
        if not args.distribution:
            raise MeasurementError("FIELD_MISSING", "--stated-uncertainty needs --distribution normal|rectangular")
        if args.distribution == "normal":
            if args.coverage_k is None:
                raise MeasurementError("FIELD_MISSING", "a normal stated uncertainty needs the --coverage-k its "
                                                        "certificate states (u = U / k, GUM 4.3.3)")
            k = _finite(args.coverage_k, "--coverage-k", "COVERAGE_INVALID", positive=True)
        else:
            if args.coverage_k is not None:
                raise MeasurementError("FIELDS_CONFLICT", "a rectangular stated uncertainty is a half-width a "
                                                          "(u = a / sqrt(3), GUM 4.3.7); it takes no --coverage-k")
            k = None
        stated.update(distribution=args.distribution, coverage_k=k)
    calibrated, due = _date(args.calibrated, "--calibrated"), _date(args.due, "--due")
    if due < calibrated:
        raise MeasurementError("DATE_ORDER", f"--due {due} is before --calibrated {calibrated}")
    entry = {"id": ident, "model": _text(args.model, "--model"), "serial": _text(args.serial, "--serial"),
             "resolution": _magnitude(args.resolution, "--resolution"), "stated_uncertainty": stated,
             "calibration_certificate": _text(args.calibration_certificate, "--calibration-certificate"),
             "calibrated": calibrated, "due": due}
    reason = (_text(args.reason, "--reason") or None) if args.reason is not None else None
    data = records.read_instruments(root)
    _append_history(data["history"], lambda item: item.get("id") == ident, entry, reason, by, "INSTRUMENT_EXISTS",
                    f"instrument {ident}")
    data["schema"] = records.SCHEMA
    _write_json(root, records.INSTRUMENTS_PATH, data)
    return {"ok": True, "path": records.INSTRUMENTS_PATH, "instrument": data["history"][-1],
            "instruments": records.instruments_state(root)}


# --------------------------------------------------------------------------- raw data files


def cmd_data(args, root: Path) -> dict:
    if args.action == "status":
        return {"ok": True, "data": records.data_state(root)}
    by = _operator(args)
    _required(args, (("file", "--file"), ("quantity", "--quantity"), ("unit", "--unit"),
                     ("instrument", "--instrument")))
    quantity = _name(args.quantity, "--quantity", "QUANTITY_NAME_INVALID")
    unit = _text(args.unit, "--unit")
    conditions = _pairs(args.condition, "--condition", "CONDITION_INVALID")
    instrument = args.instrument.strip()
    if instrument not in records.current_instruments(records.read_instruments(root)["history"]):
        raise MeasurementError("INSTRUMENT_UNKNOWN", f"instrument {instrument!r} is not recorded; "
                                                     "`instrument add` records it first")
    path, rel = _workspace_file(root, args.file, "--file")
    header, body = records.read_csv(path, rel)
    value_column = (args.value_column or quantity).strip()
    records.numbers(records.column(header, body, value_column, rel), value_column, rel)
    replicate = (args.replicate_column or "").strip() or None
    if replicate:
        records.unique_ids(records.column(header, body, replicate, rel), replicate, rel, "REPLICATE_DUPLICATE")
    entry = {"path": rel, "sha256": records.sha256(path), "rows": len(body), "columns": header,
             "quantity": quantity, "unit": unit, "value_column": value_column, "replicate_column": replicate,
             "instrument": instrument, "conditions": conditions}
    reason = (_text(args.reason, "--reason") or None) if args.reason is not None else None
    data = records.read_data(root)
    _append_history(data["registrations"], lambda item: item.get("path") == rel, entry, reason, by,
                    "DATA_ALREADY_REGISTERED", rel)
    data["schema"] = records.SCHEMA
    _write_json(root, records.DATA_PATH, data)
    return {"ok": True, "path": records.DATA_PATH, "registration": data["registrations"][-1]}


def _current_file(root: Path, entry: dict) -> None:
    state = records.file_state(root, entry)
    if state == "changed":
        raise MeasurementError("DATA_CHANGED", f"{entry['path']} changed since its registration; the operator "
                                               "registers it again (`data register ... --reason`) before any "
                                               "computation uses it")
    if state == "missing":
        raise MeasurementError("DATA_MISSING", f"{entry['path']} is registered but no longer exists")


def _values(root: Path, entry: dict, value_column: str | None = None) -> tuple[list[str], list[list[str]], list[float]]:
    header, body = records.read_csv(root / entry["path"], entry["path"])
    name = value_column or entry["value_column"]
    return header, body, records.numbers(records.column(header, body, name, entry["path"]), name, entry["path"])


# --------------------------------------------------------------------------- uncertainty budget


def _calibration(args, instrument: dict) -> dict:
    today = dt.date.today()
    state = records.calibration_state(instrument, today)
    result = {"due": instrument.get("due"), "checked_on": today.isoformat(), "state": state, "override": None}
    if state == "current":
        if args.allow_past_due or (args.by or "").strip() or args.reason is not None:
            # An attestation the computation would not use is refused, never
            # silently dropped: the operator learns the override is unneeded.
            raise MeasurementError("OVERRIDE_NOT_NEEDED", f"instrument {instrument['id']} is calibrated until "
                                                          f"{instrument.get('due')}; --allow-past-due, --by and "
                                                          "--reason apply only to a past-due calibration")
        return result
    if not args.allow_past_due:
        raise MeasurementError("CALIBRATION_PAST_DUE", f"instrument {instrument['id']} was due for calibration on "
                                                       f"{instrument.get('due')}; recalibrate it (`instrument add "
                                                       "... --reason`) or, as the operator, --allow-past-due --by "
                                                       "<name> --reason <why the readings still hold>")
    by = _operator(args)
    reason = _text(args.reason or "", "--reason")
    if not reason:
        raise MeasurementError("REASON_MISSING", "--allow-past-due needs --reason: why the readings still hold")
    result["override"] = {"by": by, "at": _now(), "reason": reason}
    return result


def cmd_uncertainty(args, root: Path) -> dict:
    if args.action == "status":
        return {"ok": True, "uncertainty": records.budget_state(root)}
    _required(args, (("quantity", "--quantity"),))
    quantity = _name(args.quantity, "--quantity", "QUANTITY_NAME_INVALID")
    if args.coverage_k is not None and args.level is not None:
        raise MeasurementError("FIELDS_CONFLICT", "give --coverage-k or --level, not both")
    declared_k = None if args.coverage_k is None else _finite(args.coverage_k, "--coverage-k", "COVERAGE_INVALID",
                                                              positive=True)
    level = None
    if declared_k is None:
        level = DEFAULT_LEVEL if args.level is None else _finite(args.level, "--level", "LEVEL_INVALID")
        if not 0.5 <= level < 1.0:
            raise MeasurementError("LEVEL_INVALID", f"--level {args.level} is a coverage probability in [0.5, 1), "
                                                    "e.g. 0.95")
    sensitivities = {key: _finite(value, "--sensitivity", "SENSITIVITY_INVALID")
                     for key, value in _pairs(args.sensitivity, "--sensitivity", "SENSITIVITY_INVALID").items()}
    conditions = _pairs(args.condition, "--condition", "CONDITION_INVALID") if args.condition else None
    instruments = records.current_instruments(records.read_instruments(root)["history"])
    registrations = records.current_registrations(records.read_data(root)["registrations"])
    selected = records.select_files(registrations, quantity, conditions)
    units = sorted({entry["unit"] for entry in selected})
    if len(units) > 1:
        raise MeasurementError("UNIT_MISMATCH", f"the files of {quantity!r} use different units ({', '.join(units)})")
    used = sorted({entry["instrument"] for entry in selected})
    if len(used) > 1:
        raise MeasurementError("INSTRUMENTS_MIXED", f"the files of {quantity!r} come from different instruments "
                                                    f"({', '.join(used)}); one budget covers one instrument")
    unit, ident = units[0], used[0]
    if ident not in instruments:
        raise MeasurementError("INSTRUMENT_UNKNOWN", f"instrument {ident!r} of the registered files is not recorded")
    instrument = instruments[ident][0]
    values: list[float] = []
    for entry in selected:
        _current_file(root, entry)
        header, body, column = _values(root, entry)
        if entry.get("replicate_column"):
            records.unique_ids(records.column(header, body, entry["replicate_column"], entry["path"]),
                               entry["replicate_column"], entry["path"], "REPLICATE_DUPLICATE")
        values.extend(column)
    if len(values) < 2:
        raise MeasurementError("REPLICATES_TOO_FEW", f"{quantity!r} has {len(values)} reading; a type A evaluation "
                                                     "needs at least 2 replicates (GUM 4.2)")
    calibration = _calibration(args, instrument)
    type_a = stats.type_a(values)
    components = [{"name": "repeatability", "type": "A", "source": "replicates", "u": type_a["u"],
                   "unit": unit, "dof": type_a["dof"]}]
    stated = instrument.get("stated_uncertainty")
    if stated:
        if stated["distribution"] == "normal":
            u, how = stated["value"] / stated["coverage_k"], f"U / k = {stated['value']} / {stated['coverage_k']}"
        else:
            u, how = stated["value"] / math.sqrt(3), f"a / sqrt(3), a = {stated['value']}"
        components.append({"name": "calibration", "type": "B", "source": f"{ident} stated uncertainty ({how})",
                           "u": u, "unit": stated["unit"], "dof": None})
    resolution = instrument["resolution"]
    components.append({"name": "resolution", "type": "B",
                       "source": f"{ident} resolution {resolution['value']} / (2 sqrt(3))",
                       "u": resolution["value"] / (2 * math.sqrt(3)), "unit": resolution["unit"], "dof": None})
    names = [c["name"] for c in components]
    unknown = sorted(set(sensitivities) - set(names))
    if unknown:
        raise MeasurementError("COMPONENT_UNKNOWN", f"--sensitivity names {', '.join(unknown)}; this budget's "
                                                    f"components are {', '.join(names)}")
    for component in components:
        component["sensitivity"] = sensitivities.get(component["name"], 1.0)
        if component["unit"] != unit and component["name"] not in sensitivities:
            raise MeasurementError("UNIT_MISMATCH", f"the {component['name']} component is in {component['unit']}, "
                                                    f"the quantity in {unit}: declare its sensitivity coefficient "
                                                    f"(--sensitivity {component['name']}=<{unit} per "
                                                    f"{component['unit']}>)")
        component["contribution"] = abs(component["sensitivity"]) * component["u"]
    combined = stats.combine(components)
    cover = stats.coverage(combined["effective_dof"], level, declared_k)
    expanded = cover["k"] * combined["u_c"]
    budget = {"quantity": quantity, "unit": unit, "conditions": selected[0].get("conditions") or {},
              "computed_at": _now(), "model": "Y = mean of the readings (direct measurement)",
              "inputs": {"files": [{"path": e["path"], "sha256": e["sha256"], "rows": e["rows"]} for e in selected],
                         "instrument": {"id": ident, "entry_sha256": records.entry_digest(instrument)}},
              "type_a": type_a, "components": components,
              "combined_standard_uncertainty": combined["u_c"], "effective_dof": combined["effective_dof"],
              "coverage": cover, "expanded_uncertainty": expanded,
              "result": {"value": type_a["mean"], "expanded_uncertainty": expanded, "unit": unit, "k": cover["k"],
                         "level": cover["level"]},
              "calibration": calibration, "method": "JCGM 100:2008 (GUM)"}
    relative = records.budget_path(quantity)
    stored = records.read_budgets(root, quantity)
    stored["budgets"] = [b for b in stored["budgets"] if (b.get("conditions") or {}) != budget["conditions"]]
    stored["budgets"].append(budget)
    stored.update(schema=records.SCHEMA, quantity=quantity)
    _write_json(root, relative, stored)
    return {"ok": True, "path": relative, "budget": budget}


# --------------------------------------------------------------------------- agreement


def _registered(root: Path, registrations: dict, given: str, flag: str) -> dict:
    _, rel = _workspace_file(root, given, flag)
    entry = registrations.get(rel)
    if entry is None:
        raise MeasurementError("DATA_NOT_REGISTERED", f"{flag} {rel} is not a registered raw data file; the operator "
                                                      "registers it with `data register`")
    _current_file(root, entry)
    return entry


def _paired(root: Path, entry: dict, pair_column: str, value_column: str | None) -> tuple[list[str], dict]:
    header, body, values = _values(root, entry, value_column)
    ids = records.column(header, body, pair_column, entry["path"])
    records.unique_ids(ids, pair_column, entry["path"], "PAIR_DUPLICATE")
    return ids, dict(zip(ids, values))


def cmd_agreement(args, root: Path) -> dict:
    if args.action == "status":
        return {"ok": True, "agreement": records.agreement_state(root)}
    _required(args, (("device_file", "--device-file"), ("reference_file", "--reference-file"),
                     ("pair_column", "--pair-column")))
    registrations = records.current_registrations(records.read_data(root)["registrations"])
    device = _registered(root, registrations, args.device_file, "--device-file")
    reference = _registered(root, registrations, args.reference_file, "--reference-file")
    if device["path"] == reference["path"]:
        raise MeasurementError("FIELDS_CONFLICT", "--device-file and --reference-file name the same file")
    if device["quantity"] != reference["quantity"]:
        raise MeasurementError("QUANTITY_MISMATCH", f"the device file measures {device['quantity']!r}, the reference "
                                                    f"file {reference['quantity']!r}")
    if device["unit"] != reference["unit"]:
        raise MeasurementError("UNIT_MISMATCH", f"the device file is in {device['unit']}, the reference file in "
                                                f"{reference['unit']}")
    pair = args.pair_column.strip()
    value_column = (args.value_column or "").strip() or None
    device_ids, device_values = _paired(root, device, pair, value_column)
    reference_ids, reference_values = _paired(root, reference, pair, value_column)
    shared = [i for i in device_ids if i in reference_values]
    if len(shared) < MIN_PAIRS:
        raise MeasurementError("PAIRS_TOO_FEW", f"{len(shared)} {pair} value(s) appear in both files; agreement "
                                                f"needs at least {MIN_PAIRS} pairs")
    dev = [device_values[i] for i in shared]
    ref = [reference_values[i] for i in shared]
    instruments = records.current_instruments(records.read_instruments(root)["history"])
    warnings = []
    for role, entry in (("device", device), ("reference", reference)):
        current = instruments.get(entry["instrument"])
        if current is not None and records.calibration_state(current[0], dt.date.today()) == "past-due":
            warnings.append({"code": "CALIBRATION_PAST_DUE", "message": f"the {role} instrument {entry['instrument']} "
                                                                        f"was due on {current[0].get('due')}"})
    icc = stats.icc_2_1([[d, r] for d, r in zip(dev, ref)])
    if icc["value"] is None:
        warnings.append({"code": "ICC_UNDEFINED", "message": "the paired values hold no variance to apportion"})

    def bound(entry: dict) -> dict:
        return {"path": entry["path"], "sha256": entry["sha256"], "instrument": entry["instrument"],
                "value_column": value_column or entry["value_column"]}

    analysis = {"device": bound(device), "reference": bound(reference), "pair_column": pair,
                "quantity": device["quantity"], "unit": device["unit"], "n": len(shared),
                "unpaired": {"device": [i for i in device_ids if i not in reference_values],
                             "reference": [i for i in reference_ids if i not in device_values]},
                "bland_altman": stats.bland_altman(dev, ref), "icc": icc, "computed_at": _now(),
                "warnings": warnings}
    stored = records.read_agreement(root)
    stored["analyses"] = [a for a in stored["analyses"]
                          if ((a.get("device") or {}).get("path"), (a.get("reference") or {}).get("path"))
                          != (device["path"], reference["path"])]
    stored["analyses"].append(analysis)
    stored["schema"] = records.SCHEMA
    _write_json(root, records.AGREEMENT_PATH, stored)
    return {"ok": True, "path": records.AGREEMENT_PATH, "analysis": analysis}


def cmd_status(args, root: Path) -> dict:
    on = dt.date.fromisoformat(_date(args.on, "--on")) if args.on else None
    return {"ok": True, **records.measurement_status(root, on)}


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="measure_cli.py", description="Instruments, raw data, uncertainty budgets, agreement.")
    sub = parser.add_subparsers(dest="verb", required=True)
    verbs = {"instrument": (cmd_instrument, ("add", "status")), "data": (cmd_data, ("register", "status")),
             "uncertainty": (cmd_uncertainty, ("compute", "status")),
             "agreement": (cmd_agreement, ("compute", "status")), "status": (cmd_status, ())}
    for name, (_, actions) in verbs.items():
        verb = sub.add_parser(name)
        verb.error = parser.error  # type: ignore[method-assign]
        verb.add_argument("--root", default=".")
        if actions:
            verb.add_argument("action", choices=actions)
    instrument = sub.choices["instrument"]
    for key, flag in INSTRUMENT_FIELDS:
        instrument.add_argument(flag, dest=key, default=None)
    instrument.add_argument("--stated-uncertainty", default=None)
    instrument.add_argument("--distribution", choices=("normal", "rectangular"), default=None)
    instrument.add_argument("--coverage-k", default=None)
    instrument.add_argument("--reason", default=None)
    instrument.add_argument("--by", default="")
    instrument.add_argument("--on", default=None)
    data = sub.choices["data"]
    for flag in ("--file", "--quantity", "--unit", "--instrument", "--value-column", "--replicate-column",
                 "--reason"):
        data.add_argument(flag, default=None)
    data.add_argument("--condition", action="append", default=[])
    data.add_argument("--by", default="")
    uncertainty = sub.choices["uncertainty"]
    uncertainty.add_argument("--quantity", default=None)
    uncertainty.add_argument("--condition", action="append", default=[])
    uncertainty.add_argument("--sensitivity", action="append", default=[])
    uncertainty.add_argument("--coverage-k", default=None)
    uncertainty.add_argument("--level", default=None)
    uncertainty.add_argument("--allow-past-due", action="store_true")
    uncertainty.add_argument("--by", default="")
    uncertainty.add_argument("--reason", default=None)
    agreement = sub.choices["agreement"]
    for flag in ("--device-file", "--reference-file", "--pair-column", "--value-column"):
        agreement.add_argument(flag, default=None)
    sub.choices["status"].add_argument("--on", default=None)
    args = parser.parse_args(argv)
    try:
        result = verbs[args.verb][0](args, Path(args.root))
    except MeasurementError as error:
        return _out({"ok": False, "error": error.code, "message": error.message}, 1)
    except Exception as exc:  # a bug, reported typed so a caller can quote it
        return _out({"ok": False, "error": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"}, 1)
    return _out(result, 0 if result.get("ok") else 1)


if __name__ == "__main__":
    sys.exit(main())
