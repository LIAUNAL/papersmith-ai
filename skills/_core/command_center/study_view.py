"""The dashboard's Study tab for an empirical workspace (paper-type-lines S8, T8-O5, E10).

* ``view(root)``: what the Study tab draws, one JSON object with a section per
  panel -- ``protocol`` (the G-STUDY-PROTOCOL lock, the latest managed
  revision and the amendments), ``ethics`` and ``registration`` (the latest
  record, whether it is bound to the current lock, the retrospective flag,
  the reason when not applicable), ``data`` (the operator's own datasets:
  data-use statement, dictionary summary, QC with its domain checks and the
  de-identification and whether it is current; never a data value),
  ``analysis`` (the analysis log: every analysis with its label, outcome,
  plan and exit code, interrupted runs, repairs and warnings), ``flow`` (the
  participant flow: valid, the figure current, the sign-off current, and the
  validated counts) and ``reporting`` (the agreed type and variant, the
  guideline ``registry.checklist_for`` names for them, and, under
  ``additional_guidelines`` when there are any, the other guidelines whose data
  names this line: ``gum-reporting`` for a hardware workspace's uncertainty
  reporting).
  A ``hardware`` or ``lab-simulation`` workspace, and any workspace that holds
  measurement records, also gets the measurement sections (decision F7), read
  only through ``skills/_core/measurement/records.py``: ``instruments`` (each
  instrument's latest record and whether its calibration is current or past due
  today), ``measurements`` (each registered raw data file: quantity, unit,
  instrument, rows, conditions, current or changed; never a measured value),
  ``uncertainty`` (each budget per quantity and condition set: its type A/B
  components, combined and expanded uncertainty, effective degrees of freedom,
  coverage, current or stale with the reasons, the calibration and any
  past-due override) and ``agreement`` (device and reference files, n,
  Bland-Altman bias and limits, ICC(2,1), current or stale). The numbers are
  the summary statistics the measurement core computed, never a reading.
  A ``data-resource`` workspace, and any workspace whose registry holds a
  deposit record, also gets ``deposit`` (decision H6): every dataset of the
  resource (each registry entry but a toy set; elsewhere only the deposited
  ones) with its deposit record (repository, identifier and scheme, licence,
  landing page, version, date, who recorded it and when, the files it binds,
  earlier records) and whether it is current or stale with the reasons, read
  only through ``datasets_cli.deposit_state``.
* ``checklist(root, guideline=None)``: the reporting guideline (or another of
  the line's guidelines, ``checklist_refusal`` refusing any other) evaluated by
  the checklist engine, served on demand only (the engine runs ``paper_cli.py``
  as subprocesses).

Every record is read through the shared modules' own readers
(``skills/_core/empirical``, ``skills/_core/participant_flow``,
``skills/_core/checklists`` and the workspace's ``datasets_cli.py``, which
falls back to the dashboard's copy and says why), never re-parsed here. A
module that cannot be imported turns the sections that need it into
``{"available": false, "code": "STUDY_MODULE_UNAVAILABLE", "message"}`` and is
named in ``warnings``; a malformed record turns only its section unavailable.
The object carries machine values and the workspace's own words only; the
dashboard draws every label from its i18n catalogues.

Which workspaces are empirical: :data:`EMPIRICAL_KINDS`, the catalogue's
family ids beyond the applied-AI and review lines (decision E1: a kind id is
its catalogue family id). The core lines table (``papersmith.core.manifest``)
is not importable from a workspace skill and the command-center board
registry (``lines.py``) has no empirical attribute, so the set is local and a
test holds it equal to the catalogue and to the tab's ``data-kinds``.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import threading
from pathlib import Path
from typing import Any, Callable

from ..paper_types import decision, registry

NOT_A_STUDY_WORKSPACE = "NOT_A_STUDY_WORKSPACE"
MODULE_UNAVAILABLE = "STUDY_MODULE_UNAVAILABLE"
NO_CHECKLIST = "NO_CHECKLIST_DATA"
#: The empirical kinds, in catalogue order: line 1 and the planned ones.
EMPIRICAL_KINDS: tuple[str, ...] = (
    "observational-measurement", "experiment-intervention", "qualitative-participatory", "hardware",
    "lab-simulation", "data-resource",
)
SECTIONS = ("protocol", "ethics", "registration", "data", "analysis", "flow", "reporting")
GUIDELINE_NOT_THIS_LINE = "GUIDELINE_NOT_THIS_LINE"
#: The lines built on the measurement core (decision F1): their Study tab always shows its sections.
MEASUREMENT_KINDS: tuple[str, ...] = ("hardware", "lab-simulation")
MEASUREMENT_SECTIONS = ("instruments", "measurements", "uncertainty", "agreement")
#: The measurement core's reader module, relative to ``skills/_core``.
MEASUREMENT_MODULE = "measurement.records"
#: Its records (a test holds them equal to the module's constants): any of them
#: present shows the measurement sections in a workspace of another line.
MEASUREMENT_RECORDS = ("study/instruments.json", "study/measurements.json", "study/uncertainty",
                       "study/agreement.json")
#: The lines whose Study tab always shows the deposit section (decision H6).
DEPOSIT_KINDS: tuple[str, ...] = ("data-resource",)

#: Shared ``skills/_core`` modules, relative to that package.
MODULES: dict[str, str] = {
    "records": "empirical.records",
    "analysis_log": "empirical.analysis_log",
    "flow_model": "participant_flow.model",
    "flow_cli": "participant_flow.flow_cli",
    "engine": "checklists.engine",
}
#: The module each section reads.
NEEDS: dict[str, tuple[str, ...]] = {
    "protocol": ("records",), "ethics": ("records",), "registration": ("records",), "data": ("datasets_cli",),
    "analysis": ("analysis_log",), "flow": ("flow_model", "flow_cli"), "reporting": (),
}
DATASETS_CLI = Path("skills") / "datasets" / "scripts" / "datasets_cli.py"
DASHBOARD_DATASETS_CLI = Path(__file__).resolve().parents[2] / "datasets" / "scripts" / "datasets_cli.py"
_CORE = __package__.rsplit(".", 1)[0] if __package__ else "skills._core"
_LOADED: dict[str, tuple[str, Any | None, str | None]] = {}
_LOCK = threading.Lock()


def refusal(root: Path) -> dict[str, Any] | None:
    """The 409 body for a workspace that is not empirical, ``None`` for one that is."""
    line = decision.current_line(Path(root))
    if line in EMPIRICAL_KINDS:
        return None
    return {"ok": False, "code": NOT_A_STUDY_WORKSPACE, "paper_kind": line,
            "error": f"this is not an empirical study workspace (paper_kind: {line}); the Study tab reads "
                     "study/, analysis/, datasets/ and protocol/ records"}


# --------------------------------------------------------------------------- loading


def _module(name: str) -> tuple[Any | None, str | None]:
    """``(module, None)`` or ``(None, why)`` for a shared module of :data:`MODULES`."""
    try:
        return importlib.import_module(f"{_CORE}.{MODULES[name]}"), None
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - an absent module is reported, never raised
        return None, f"{name} ({_CORE}.{MODULES[name]}) did not load: {type(exc).__name__}: {exc}"


def _load_path(path: Path) -> tuple[Any | None, str | None] | None:
    """``(module, None)``, ``(None, why)`` when the file fails to load, ``None``
    when it does not exist. Reloaded when the file changes."""
    try:
        stamp = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
    key = str(path)
    with _LOCK:
        cached = _LOADED.get(key)
        if cached and cached[0] == stamp:
            return cached[1], cached[2]
        try:
            spec = importlib.util.spec_from_file_location(f"_papersmith_study_datasets_cli_{len(_LOADED)}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            loaded: tuple[Any | None, str | None] = (module, None)
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            loaded = (None, f"{type(exc).__name__} at {path}")
        _LOADED[key] = (stamp, *loaded)
        return loaded


def load_datasets_cli(root: Path) -> tuple[Any | None, str | None]:
    """The workspace's ``datasets_cli.py`` (else the dashboard's copy) and why
    the workspace's own copy was passed over when it exists but fails to load."""
    workspace = _load_path(Path(root) / DATASETS_CLI)
    if workspace is not None and workspace[0] is not None:
        return workspace
    warning = workspace[1] if workspace is not None else None
    bundled = _load_path(DASHBOARD_DATASETS_CLI)
    if warning:
        warning = f"the workspace's datasets_cli.py did not load ({warning}); read with the dashboard's own copy"
    return (bundled[0] if bundled is not None else None), warning


# --------------------------------------------------------------------------- helpers


def _unavailable(code: str, message: str) -> dict[str, Any]:
    return {"available": False, "code": code, "message": message}


def _failure(exc: BaseException) -> dict[str, Any]:
    code, message = getattr(exc, "code", None), getattr(exc, "message", None)
    if isinstance(code, str) and code and isinstance(message, str):
        return _unavailable(code, message)
    return _unavailable("UNREADABLE", f"{type(exc).__name__}: {exc}")


def _section(build: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return {"available": True, **build()}
    except Exception as exc:  # noqa: BLE001 - one unreadable record never breaks the tab
        return _failure(exc)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ("" if value is None else str(value))


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _warnings(value: Any) -> list[dict[str, Any]]:
    return [{key: item[key] for key in ("code", "message", "outcome", "runs") if key in item}
            for item in _list(value) if isinstance(item, dict)]


# --------------------------------------------------------------------------- sections


def _protocol(mods: dict[str, Any], root: Path) -> dict[str, Any]:
    records = mods["records"]
    state = records.protocol_state(root)
    try:
        latest, latest_problem = records.latest_revision(root), None
    except records.StudyError as error:
        latest, latest_problem = None, {"code": error.code, "message": error.message}
    amendments: list[dict[str, Any]] = []
    if state["state"] in ("current", "changed"):
        lock = records.read_lock(root) or {}
        amendments = [{"by": _text(a.get("by")), "at": _text(a.get("at")), "reason": _text(a.get("reason")),
                       "revision": _text(a.get("revision")), "from_revision": _text(a.get("from_revision"))}
                      for a in _list(lock.get("amendments")) if isinstance(a, dict)]
    return {"gate": records.GATE, "state": state["state"], "reasons": list(state.get("reasons") or []),
            "message": _text(state.get("message")), "revision": state.get("revision"),
            "sha256": state.get("sha256"), "approved_by": state.get("approved_by"),
            "approved_at": state.get("approved_at"), "latest_revision": latest, "latest_problem": latest_problem,
            "revisions": len(records.managed_revisions(root)), "amendments": amendments}


_ETHICS_FIELDS = ("committee", "code", "date", "consent")
_REGISTRATION_FIELDS = ("registry", "id", "date", "first_enrolment", "retrospective")


def _gate(gate: str, fields: tuple[str, ...]) -> Callable[[dict[str, Any], Path], dict[str, Any]]:
    def build(mods: dict[str, Any], root: Path) -> dict[str, Any]:
        records = mods["records"]
        state = records.gate_state(root, gate)
        if state is None:
            return {"recorded": False, "path": records.RECORD_PATHS[gate]}
        if state.get("state") == "corrupt":
            raise records.StudyError(f"{gate.upper()}_CORRUPT", _text(state.get("message")))
        out = {"recorded": True, "path": records.RECORD_PATHS[gate], "status": _text(state.get("status")),
               "reason": _text(state.get("reason")), "by": _text(state.get("by")), "at": _text(state.get("at")),
               "current": bool(state.get("current")), "records": state.get("records"),
               "protocol_revision": _text(state.get("protocol_revision")), "warnings": _warnings(state.get("warnings"))}
        for key in fields:
            value = state.get(key)
            out[key] = value if isinstance(value, bool) or value is None else _text(value)
        return out
    return build


def _dictionary(dc: Any, root: Path, slug: str) -> dict[str, Any]:
    try:
        found = dc.read_dictionary(root, slug)
    except dc.Refusal as refusal:
        return {"state": "unreadable", "code": refusal.code, "message": refusal.message}
    if found is None:
        return {"state": "absent"}
    columns, path = found
    try:
        raw = _list(_object(json.loads(path.read_text(encoding="utf-8"))).get("columns"))
    except (OSError, ValueError):
        raw = []
    texts = {_text(item.get("name")): item for item in raw if isinstance(item, dict)}
    return {"state": "valid", "path": path.relative_to(root).as_posix(), "pii": [c["name"] for c in columns if c["pii"]],
            "columns": [{"name": c["name"], "type": c["type"], "pii": c["pii"],
                         "unit": _text(_object(texts.get(c["name"])).get("unit")),
                         "described": bool(_text(_object(texts.get(c["name"])).get("description")).strip()),
                         "levels": len(c["levels"] or []), "range": c["range"] is not None,
                         "missing_codes": len(c["missing_codes"])} for c in columns]}


def _qc(entry: dict[str, Any], root: Path) -> dict[str, Any]:
    """The QC status and its domain checks: counts, columns and row numbers, never a value."""
    qc = _object(entry.get("qc"))
    if not qc:
        return {"status": None}
    out: dict[str, Any] = {"status": qc.get("status"), "report": _text(qc.get("report")), "reasons": [],
                           "domain_checks": []}
    path = root / out["report"] if out["report"] else None
    if path is None or not path.is_file():
        return {**out, "report_state": "absent"}
    try:
        report = _object(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        return {**out, "report_state": "unreadable", "message": f"{out['report']}: {exc}"}
    checks = [{key: item[key] for key in ("check", "column", "severity", "count", "expected", "reason") if key in item}
              | {"rows": len(_list(item.get("rows")))}
              for item in _list(report.get("domain_checks")) if isinstance(item, dict)]
    dictionary = _object(report.get("dictionary"))
    current = None
    if dictionary.get("file"):
        target = root / _text(dictionary.get("file"))
        current = target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == dictionary.get("sha256")
    return {**out, "report_state": "ok", "file": _text(report.get("file")), "checked": _text(report.get("checked")),
            "rows": report.get("rows"), "columns": report.get("columns"),
            "reasons": [_text(r) for r in _list(report.get("reasons"))], "domain_checks": checks,
            "dictionary_current": current}


def _deidentification(dc: Any, entry: dict[str, Any], root: Path) -> dict[str, Any]:
    record = _object(entry.get("deidentification"))
    warnings: list[dict] = []
    try:
        problem = dc.pii_problem(root, entry, warnings)
    except dc.Refusal as refusal:
        problem = f"{refusal.code}: {refusal.message}"
    out = {"recorded": bool(record), "statement": _text(record.get("statement")), "by": _text(record.get("by")),
           "recorded_on": _text(record.get("recorded")), "columns": [_text(c) for c in _list(record.get("columns"))],
           "pii_columns_seen": [_text(c) for c in _list(entry.get("pii_columns_seen"))],
           "problem": problem, "warnings": _warnings(warnings)}
    out["required"] = bool(out["pii_columns_seen"]) or problem is not None
    out["current"] = bool(record) and problem is None
    return out


def _data(mods: dict[str, Any], root: Path) -> dict[str, Any]:
    dc = mods["datasets_cli"]
    registry_entries = [entry for entry in dc.load_registry(root) if isinstance(entry, dict)]
    own = []
    for entry in sorted(registry_entries, key=lambda item: _text(item.get("slug"))):
        if entry.get("role") != "own":
            continue
        slug = _text(entry.get("slug"))
        data_use = _object(entry.get("data_use"))
        own.append({"slug": slug, "title": _text(entry.get("title")), "role": "own",
                    "files": [_text(f) for f in _list(entry.get("files"))],
                    "data_use": {"statement": _text(data_use.get("statement")), "by": _text(data_use.get("by")),
                                 "recorded": _text(data_use.get("recorded")),
                                 "revisions": len(_list(data_use.get("history")))},
                    "dictionary": _dictionary(dc, root, slug), "qc": _qc(entry, root),
                    "deidentification": _deidentification(dc, entry, root)})
    return {"own": own, "other": len(registry_entries) - len(own)}


_ENTRY_KEYS = ("id", "kind", "at", "outcome", "plan", "label", "exit_code", "attested", "by", "tool", "note",
               "duration_s")


def _analysis(mods: dict[str, Any], root: Path) -> dict[str, Any]:
    log = mods["analysis_log"]
    status = log.status(root)
    entries = log.analyses(log.read_log(root)) if status["log"]["state"] == "ok" else []
    rows = []
    for entry in entries:
        row = {key: entry.get(key) for key in _ENTRY_KEYS}
        reason = _object(entry.get("label_reason"))
        row["label_reason"] = {"code": _text(reason.get("code")), "message": _text(reason.get("message"))}
        row["script"] = _text(_object(entry.get("script")).get("path")) or None
        row["inputs"] = [_text(_object(item).get("path")) for item in _list(entry.get("inputs"))]
        row["outputs"] = [_text(_object(item).get("path")) for item in _list(entry.get("outputs"))]
        rows.append(row)
    return {"log": {key: status["log"].get(key) for key in ("path", "state", "entries", "message")},
            "entries": rows, "labels": status.get("labels"), "failed_runs": status.get("failed_runs") or [],
            "interrupted_runs": status.get("interrupted_runs") or [], "repairs": status.get("repairs", 0),
            "protocol_outcomes": status.get("protocol_outcomes"), "plan_entries": status.get("plan_entries"),
            "warnings": _warnings(status.get("warnings"))}


def _counts(stage: dict[str, Any], body: Any) -> dict[str, Any]:
    body = _object(body)
    groups = []
    for group in _list(stage.get("groups")):
        value = body.get(group["id"])
        if group.get("effect") == "partition":
            labels = dict((category, label) for category, label in group.get("categories") or [])
            items = [{"label": labels.get(category, category), "n": n} for category, n in _object(value).items()]
        else:
            items = [{"label": _text(_object(item).get("reason")), "n": _object(item).get("n")}
                     for item in _list(value)]
        groups.append({"id": group["id"], "label": group.get("label"), "effect": group.get("effect"), "items": items})
    return {"n": body.get("n"), "groups": groups}


def _flow(mods: dict[str, Any], root: Path) -> dict[str, Any]:
    model, cli = mods["flow_model"], mods["flow_cli"]
    status = cli.cmd_status(None, root)
    figure = root / model.FIGURE_PATH
    exists = figure.is_file()
    out = {"state": status["flow"], "template": status.get("template"), "problems": [], "stages": [],
           "path": model.FLOW_PATH, "signoff": _object(status.get("signoff")) or None,
           "figure": {"path": model.FIGURE_PATH, "state": status.get("figure"), "exists": exists,
                      "mtime": int(figure.stat().st_mtime) if exists else None}}
    if out["signoff"] is not None:
        out["signoff"] = {key: out["signoff"].get(key) for key in ("by", "at", "note", "current")}
    if status["flow"] == "absent":
        return out
    flow = cli._load_flow(root)
    problems = model.check(flow)
    if problems:
        out["problems"] = [{key: _text(p.get(key)) for key in ("code", "path", "message") if key in p}
                           for p in problems if isinstance(p, dict)]
        return out
    tpl = model.TEMPLATES[flow["template"]]
    labels = model.branch_labels(tpl, flow)
    out["guideline"] = tpl.get("guideline")
    for stage in model.stage_chain(flow):
        row = {"id": stage["id"], "band": stage.get("band"), "label": stage.get("label"), "split": bool(stage.get("split"))}
        if stage.get("split"):
            branches = _object(stage["body"].get("branches"))
            row["branches"] = [{"id": name, "label": labels.get(name, name), **_counts(stage, branches.get(name))}
                               for name in labels]
            row["basis"] = stage["body"].get("basis")
        else:
            row.update(_counts(stage, stage["body"]))
        out["stages"].append(row)
    return out


# --------------------------------------------------------------------------- measurement (decision F7)


def _measurement_shown(root: Path, line: str) -> bool:
    if line in MEASUREMENT_KINDS:
        return True
    instruments, data, uncertainty, agreement = (root / rel for rel in MEASUREMENT_RECORDS)
    return (instruments.is_file() or data.is_file() or agreement.is_file()
            or (uncertainty.is_dir() and any(uncertainty.glob("*.json"))))


class MeasurementRead(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _corrupt(state: dict[str, Any], code: str) -> None:
    if state.get("state") == "corrupt":
        raise MeasurementRead(code, _text(state.get("message")))


_INSTRUMENT_KEYS = ("id", "model", "serial", "resolution", "stated_uncertainty", "calibration_certificate",
                    "calibrated", "due", "calibration", "entries", "by", "at", "reason")


def _instruments(mods: dict[str, Any], root: Path) -> dict[str, Any]:
    state = mods["measurement"].instruments_state(root)
    _corrupt(state, "INSTRUMENTS_CORRUPT")
    rows = [{key: row.get(key) for key in _INSTRUMENT_KEYS} for row in _list(state.get("instruments"))]
    return {"state": state["state"], "path": MEASUREMENT_RECORDS[0], "on": state.get("on"), "instruments": rows,
            "past_due": list(state.get("past_due") or [])}


_FILE_KEYS = ("path", "quantity", "unit", "instrument", "rows", "conditions", "value_column", "replicate_column",
              "by", "at", "state")


def _measurements(mods: dict[str, Any], root: Path) -> dict[str, Any]:
    state = mods["measurement"].data_state(root)
    _corrupt(state, "DATA_REGISTRY_CORRUPT")
    return {"state": state["state"], "path": MEASUREMENT_RECORDS[1],
            "files": [{key: item.get(key) for key in _FILE_KEYS} for item in _list(state.get("files"))]}


_COMPONENT_KEYS = ("name", "type", "source", "u", "unit", "dof", "sensitivity", "contribution")


def _uncertainty(mods: dict[str, Any], root: Path) -> dict[str, Any]:
    records = mods["measurement"]
    state = records.budget_state(root)
    _corrupt(state, "UNCERTAINTY_CORRUPT")
    stored: dict[str, list] = {}
    rows = []
    for row in _list(state.get("budgets")):
        quantity = _text(row.get("quantity"))
        if row.get("state") == "corrupt":
            rows.append({"quantity": quantity, "state": "corrupt", "message": _text(row.get("message")),
                         "path": records.budget_path(quantity)})
            continue
        if quantity not in stored:
            stored[quantity] = _list(records.read_budgets(root, quantity).get("budgets"))
        conditions = row.get("conditions") or {}
        budget = next((b for b in stored[quantity] if isinstance(b, dict) and (b.get("conditions") or {}) == conditions),
                      {})
        type_a = _object(budget.get("type_a"))
        rows.append({key: row.get(key) for key in ("quantity", "unit", "conditions", "computed_at",
                                                   "combined_standard_uncertainty", "effective_dof",
                                                   "expanded_uncertainty", "coverage", "n", "mean", "state",
                                                   "reasons")}
                    | {"path": records.budget_path(quantity), "model": budget.get("model"),
                       "method": budget.get("method"), "sd": type_a.get("sd"),
                       "components": [{key: _object(c).get(key) for key in _COMPONENT_KEYS}
                                      for c in _list(budget.get("components"))],
                       "calibration": _calibration_record(row.get("calibration"))})
    return {"state": state["state"], "path": MEASUREMENT_RECORDS[2], "budgets": rows}


def _calibration_record(value: Any) -> dict[str, Any] | None:
    calibration = _object(value)
    if not calibration:
        return None
    override = _object(calibration.get("override"))
    return {"due": calibration.get("due"), "checked_on": calibration.get("checked_on"),
            "state": calibration.get("state"),
            "override": {key: _text(override.get(key)) for key in ("by", "at", "reason")} if override else None}


def _agreement(mods: dict[str, Any], root: Path) -> dict[str, Any]:
    state = mods["measurement"].agreement_state(root)
    _corrupt(state, "AGREEMENT_CORRUPT")
    rows = []
    for item in _list(state.get("analyses")):
        icc = _object(item.get("icc"))
        rows.append({role: {key: _object(item.get(role)).get(key) for key in ("path", "instrument", "value_column")}
                     for role in ("device", "reference")}
                    | {key: item.get(key) for key in ("pair_column", "quantity", "unit", "n", "bland_altman",
                                                      "computed_at", "state", "reasons")}
                    | {"icc": {key: icc.get(key) for key in ("form", "value", "n", "k")}})
    return {"state": state["state"], "path": MEASUREMENT_RECORDS[3], "analyses": rows}


# --------------------------------------------------------------------------- deposit (decision H6)


_DEPOSIT_KEYS = ("repository", "identifier", "scheme", "license", "url", "version", "date", "by")


def _deposit_shown(dc: Any, root: Path, line: str) -> bool:
    if line in DEPOSIT_KINDS:
        return True
    try:
        return any(isinstance(entry, dict) and entry.get("deposit") is not None for entry in dc.load_registry(root))
    except Exception:  # noqa: BLE001 - an unreadable registry is the data section's to report
        return False


def _deposit(mods: dict[str, Any], root: Path, line: str) -> dict[str, Any]:
    """Every resource dataset's deposit, as ``datasets_cli.deposit_state`` reads it."""
    dc = mods["datasets_cli"]
    rows = []
    for entry in sorted(dc.load_registry(root), key=lambda item: _text(_object(item).get("slug"))):
        if not isinstance(entry, dict) or entry.get("role") == "toy":
            continue
        if line not in DEPOSIT_KINDS and entry.get("deposit") is None:
            continue
        state = dc.deposit_state(root, entry)
        record = _object(state.get("deposit"))
        rows.append({"slug": _text(entry.get("slug")), "title": _text(entry.get("title")),
                     "role": _text(entry.get("role")), "recorded": bool(state.get("recorded")),
                     "current": bool(state.get("current")),
                     "stale": [{"reason": _text(_object(item).get("reason")), "file": _text(_object(item).get("file"))}
                               for item in _list(state.get("stale"))]}
                    | {key: (_text(record.get(key)) if record.get(key) is not None else None) for key in _DEPOSIT_KEYS}
                    | {"recorded_on": _text(record.get("recorded")) or None,
                       "files": sorted(_text(rel) for rel in _object(record.get("files"))),
                       "revisions": len(_list(record.get("history")))})
    return {"datasets": rows}


_MEASUREMENT_BUILDERS: dict[str, Callable[[dict[str, Any], Path], dict[str, Any]]] = {
    "instruments": _instruments, "measurements": _measurements, "uncertainty": _uncertainty,
    "agreement": _agreement,
}


def _guidelines_of_line(engine: Any, line: str) -> list[str]:
    """Every guideline whose data names ``line`` (``lines``), in id order; an
    invalid guideline file is skipped (the checklist engine's own tests hold them valid)."""
    found = []
    for path in sorted(Path(engine.GUIDELINES_DIR).glob("*.json")):
        try:
            data = engine.load_guideline(path.stem)
        except engine.ChecklistRefusal:
            continue
        if line in (data.get("lines") or []):
            found.append(data["id"])
    return found


def _reporting(mods: dict[str, Any], root: Path) -> dict[str, Any]:
    """The agreed type and variant, the guideline ``registry.checklist_for`` names for
    them (``None``: no data yet) and, when there are any, the line's other guidelines."""
    out = _primary_guideline(root)
    engine = mods.get("engine")
    if engine is not None:
        others = [gid for gid in _guidelines_of_line(engine, decision.current_line(root)) if gid != out["guideline"]]
        if others:
            out["additional_guidelines"] = others
    return out


def _primary_guideline(root: Path) -> dict[str, Any]:
    record = _object(decision.read(root).get("paper_type"))
    agreed, variant = record.get("agreed"), record.get("agreed_variant")
    line = decision.current_line(root)
    out = {"type": agreed, "variant": variant, "variant_name": None, "guideline": None, "stale": bool(record.get("agreed_stale")),
           "code": NO_CHECKLIST, "reason": "variant-not-agreed"}
    if not agreed:
        out["reason"] = "type-not-agreed"
        return out
    item = registry.get(agreed)
    if item.get("line") != line:
        out["reason"] = "type-not-this-line"
        return out
    variants = item.get("variants") or []
    chosen = next((v for v in variants if v["id"] == variant), None)
    if variants and chosen is None:
        return out
    if chosen is not None:
        out["variant_name"] = chosen.get("name")
    guideline = registry.checklist_for(item, variant)
    if guideline:
        out.update(guideline=guideline, code=None, reason=None)
    else:
        out["reason"] = "variant-without-checklist" if chosen is not None else "type-without-checklist"
    return out


_BUILDERS: dict[str, Callable[[dict[str, Any], Path], dict[str, Any]]] = {
    "protocol": _protocol, "ethics": _gate("ethics", _ETHICS_FIELDS),
    "registration": _gate("registration", _REGISTRATION_FIELDS), "data": _data, "analysis": _analysis,
    "flow": _flow, "reporting": _reporting,
}


# --------------------------------------------------------------------------- entry points


def _modules(root: Path) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """Every module the sections read, the reason each absent one is absent, and the warnings."""
    mods: dict[str, Any] = {}
    missing: dict[str, str] = {}
    warnings: list[str] = []
    for name in MODULES:
        module, why = _module(name)
        if module is None:
            missing[name] = why or f"{name} did not load"
            warnings.append(missing[name])
        else:
            mods[name] = module
    dc, why = load_datasets_cli(root)
    if why:
        warnings.append(why)
    if dc is None:
        missing["datasets_cli"] = "no datasets_cli.py could be loaded"
        warnings.append(missing["datasets_cli"])
    else:
        mods["datasets_cli"] = dc
    return mods, missing, warnings


def _measurement_module() -> tuple[Any | None, str | None]:
    try:
        return importlib.import_module(f"{_CORE}.{MEASUREMENT_MODULE}"), None
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - an absent module is reported, never raised
        return None, f"measurement ({_CORE}.{MEASUREMENT_MODULE}) did not load: {type(exc).__name__}: {exc}"


def view(root: Path) -> dict[str, Any]:
    root = Path(root)
    mods, missing, warnings = _modules(root)
    line = decision.current_line(root)
    out: dict[str, Any] = {"paper_kind": line, "warnings": warnings}
    for name in SECTIONS:
        absent = [missing[need] for need in NEEDS[name] if need in missing]
        if absent:
            out[name] = _unavailable(MODULE_UNAVAILABLE, "; ".join(absent))
        else:
            out[name] = _section(lambda build=_BUILDERS[name]: build(mods, root))
    if _measurement_shown(root, line):
        module, why = _measurement_module()
        if module is None:
            warnings.append(why)
        for name in MEASUREMENT_SECTIONS:
            if module is None:
                out[name] = _unavailable(MODULE_UNAVAILABLE, why or "the measurement core did not load")
            else:
                out[name] = _section(lambda build=_MEASUREMENT_BUILDERS[name]: build({"measurement": module}, root))
    dc = mods.get("datasets_cli")
    if dc is None:
        if line in DEPOSIT_KINDS:
            out["deposit"] = _unavailable(MODULE_UNAVAILABLE, missing.get("datasets_cli", "datasets_cli did not load"))
    elif _deposit_shown(dc, root, line):
        out["deposit"] = _section(lambda: _deposit(mods, root, line))
    return out


def _allowed_guidelines(root: Path, engine: Any) -> list[str]:
    primary = _primary_guideline(root)["guideline"]
    others = _guidelines_of_line(engine, decision.current_line(root)) if engine is not None else []
    return ([primary] if primary else []) + [gid for gid in others if gid != primary]


def checklist_refusal(root: Path, guideline: str | None) -> dict[str, Any] | None:
    """The 400 body when ``guideline`` is given and is not one of the line's guidelines
    (the agreed variant's or one whose data names the line), ``None`` otherwise."""
    if guideline is None:
        return None
    engine, _why = _module("engine")
    try:
        allowed = _allowed_guidelines(Path(root), engine)
    except Exception:  # noqa: BLE001 - an unreadable record allows nothing extra
        allowed = []
    if guideline in allowed:
        return None
    return {"ok": False, "code": GUIDELINE_NOT_THIS_LINE, "guideline": guideline, "allowed": allowed,
            "error": f"{guideline!r} is not a reporting guideline of this workspace's line; "
                     f"allowed: {', '.join(allowed) or 'none'}"}


def checklist(root: Path, guideline: str | None = None) -> dict[str, Any]:
    """The agreed variant's guideline, or ``guideline`` (one of the line's, see
    :func:`checklist_refusal`), through the checklist engine: slow (paper_cli
    subprocesses); call it off the event loop."""
    root = Path(root)
    engine, why = _module("engine")
    reporting = _section(lambda: _primary_guideline(root))
    if not reporting["available"]:
        return reporting
    head = {key: reporting[key] for key in ("type", "variant", "variant_name", "code", "reason")}
    chosen = guideline or reporting["guideline"]
    if guideline:
        head.update(code=None, reason=None)
    if chosen is None:
        return {"available": True, **head, "guideline": None}
    if engine is None:
        return {**_unavailable(MODULE_UNAVAILABLE, why or "the checklist engine did not load"), **head}

    def build() -> dict[str, Any]:
        return {**head, **engine.check(chosen, root)}

    return _section(build)


__all__ = ["DEPOSIT_KINDS", "EMPIRICAL_KINDS", "GUIDELINE_NOT_THIS_LINE", "MEASUREMENT_KINDS", "MEASUREMENT_MODULE",
           "MEASUREMENT_RECORDS", "MEASUREMENT_SECTIONS", "MODULE_UNAVAILABLE", "MODULES", "NOT_A_STUDY_WORKSPACE",
           "NO_CHECKLIST", "SECTIONS", "checklist", "checklist_refusal", "load_datasets_cli", "refusal", "view"]
