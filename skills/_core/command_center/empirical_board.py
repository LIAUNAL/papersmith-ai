"""The command center's board for the empirical paper lines (S8, decision E5).

One board serves every empirical line. A line is a :class:`LineTable`: its
steps in order (drawn from the shared :data:`STEPS` library), the gates its
board lists, its phase locks and the step that is transversal. This module
fills the table of ``observational-measurement``
(``src/papersmith/templates/paper-flow-observational-measurement.md.tpl``); a
later line adds its own table to :data:`LINE_TABLES` (reusing the library's
steps and adding the ones only it has) and is registered with the rest at the
end of this module. ``review_board`` stays the review line's own board.

Every status is read from evidence on disk, never computed from a model:

* G-STUDY-PROTOCOL: ``records.protocol_state`` is ``current``;
* G-ETHICS and G-REGISTRATION: ``records.gate_state`` is recorded and bound
  to the current lock (a not-applicable record counts as passed);
* G-DATA-QC: every own dataset's ``datasets/<slug>/qc.json`` matches the
  sha256 of its data file and of its current data dictionary, its status is
  not ``fail``, and ``datasets_cli.pii_problem`` finds nothing left to
  de-identify (what ``publish`` refuses as ``pii-not-deidentified``);
* G-FLOW: the participant flow sign-off is current (``flow_cli`` status).

The operator records every one of them with ``--by``; the board only reads
(decision E8). The analysis actions wait for the protocol, the ethics and
registration records and the data QC; the writing waits for the flow
sign-off.

The shared modules are read through their own functions, loaded by path the
way ``review_board`` loads ``review_cli.py``: the workspace's copy first, else
the dashboard's own, with a visible note on every step that read it when the
workspace's copy exists but fails to load. A package module is loaded inside a
private package of its own directory, so its relative imports resolve to its
siblings and nothing is added to ``sys.path`` for it. Every label is English;
the dashboard's Spanish comes from ``static/i18n/server-es.json``.
"""

from __future__ import annotations

import argparse
import copy
import functools
import hashlib
import importlib.util
import itertools
import json
import re
import sys
import threading
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from . import lines, phase_actions, review_board
from . import state_extractor as _ex
from .phase_actions import _command, _prompt, _redirect, _requires

try:
    from ..paper_types import decision, registry as paper_types
except ImportError:  # imported as top-level ``command_center`` (see state_extractor)
    from paper_types import decision, registry as paper_types  # type: ignore[no-redef]

# --------------------------------------------------------------------------- the shared modules

#: The dashboard's own ``skills/`` tree: the fallback for every module below.
DASHBOARD_SKILLS = Path(__file__).resolve().parents[2]

#: name -> its path under ``skills/`` (in the workspace and in the dashboard).
MODULES: dict[str, str] = {
    "records": "_core/empirical/records.py",
    "analysis_log": "_core/empirical/analysis_log.py",
    "flow_cli": "_core/participant_flow/flow_cli.py",
    "datasets_cli": "datasets/scripts/datasets_cli.py",
    "checklists": "_core/checklists/engine.py",
}

_CACHE_LOCK = threading.Lock()
#: path -> (stamp of its directory's modules, module or ``None``, why it did not load);
#: a failed load is cached too, so a broken file is not re-executed per request.
_LOADED: dict[str, tuple[str, Any, str | None]] = {}
_PACKAGES = itertools.count()


def _stamp(path: Path) -> str:
    """The sha256 of the module and its sibling modules: a sibling it imports
    (``records`` beside ``analysis_log``) reloads it too."""
    digest = hashlib.sha256(path.read_bytes())
    for sibling in sorted(path.parent.glob("*.py")):
        if sibling != path:
            digest.update(sibling.name.encode("utf-8") + b"\0" + sibling.read_bytes())
    return digest.hexdigest()


def _exec(path: Path) -> Any:
    package = f"_papersmith_empirical_{next(_PACKAGES)}"
    holder = types.ModuleType(package)
    holder.__path__ = [str(path.parent)]  # type: ignore[attr-defined]
    sys.modules[package] = holder
    spec = importlib.util.spec_from_file_location(f"{package}.{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load(path: Path) -> tuple[Any | None, str | None] | None:
    """``(module, None)``, ``(None, why)`` when the file fails to load, or
    ``None`` when it does not exist. Reloaded when it or a sibling changes."""
    try:
        stamp = _stamp(path)
    except OSError:
        return None
    key = str(path)
    with _CACHE_LOCK:
        cached = _LOADED.get(key)
        if cached and cached[0] == stamp:
            return cached[1], cached[2]
        try:
            loaded: tuple[Any | None, str | None] = (_exec(path), None)
        except (Exception, SystemExit) as exc:
            loaded = (None, f"{type(exc).__name__} at {path}")
        _LOADED[key] = (stamp, *loaded)
        return loaded


def load_module(root: Path, name: str) -> tuple[Any | None, str | None]:
    """The workspace's copy of module ``name`` (else the dashboard's own), or
    ``None`` when neither loads, and why the workspace's copy was passed over
    when it exists but fails to load (``None`` otherwise)."""
    rel = MODULES[name]
    workspace = _load(Path(root) / "skills" / rel)
    if workspace is not None and workspace[0] is not None:
        return workspace
    warning = workspace[1] if workspace is not None else None
    bundled = _load(DASHBOARD_SKILLS / rel)
    return (bundled[0] if bundled is not None else None), warning


# --------------------------------------------------------------------------- commands

STUDY_CLI = "python skills/_core/empirical/study_cli.py"
ANALYSIS_CLI = "python skills/_core/empirical/analysis_cli.py"
FLOW_CLI = "python skills/_core/participant_flow/flow_cli.py"
DATASETS_CLI = "python skills/datasets/scripts/datasets_cli.py --root ."
CHECKLIST_CLI = "python skills/_core/checklists/checklist_cli.py"

PROTOCOL_GATE, ETHICS_GATE, REGISTRATION_GATE = "G-STUDY-PROTOCOL", "G-ETHICS", "G-REGISTRATION"
DATA_GATE, FLOW_GATE = "G-DATA-QC", "G-FLOW"
#: What an analysis waits for: the protocol, the ethics and registration records and the data QC.
ANALYSIS_GATES = (PROTOCOL_GATE, ETHICS_GATE, REGISTRATION_GATE, DATA_GATE)
_OPERATOR = '"<operator name>"'

TELEMETRY_NOTE = "No telemetry is recorded for the study steps yet"

# --------------------------------------------------------------------------- the step library


@dataclass
class Context:
    """One status request: the workspace, the server's paper-tree facts, the
    line's table and the modules and gates read once for every step."""

    root: Path
    facts: dict[str, Any]
    table: "LineTable"
    modules: dict[str, tuple[Any | None, str | None]] = field(default_factory=dict)
    gates: dict[str, dict[str, str]] = field(default_factory=dict)

    def module(self, name: str) -> Any | None:
        if name not in self.modules:
            self.modules[name] = load_module(self.root, name)
        return self.modules[name][0]

    def warning(self, name: str) -> str | None:
        return self.modules.get(name, (None, None))[1]


@dataclass(frozen=True)
class Step:
    """One step a line's board may show. ``read(ctx)`` answers ``status``,
    ``detail``, optionally ``progress``, and ``subfases`` as (name, status,
    detail) triples the board numbers; ``modules`` are the shared modules it
    reads, whose absence or fallback its detail reports."""

    id: str
    label: str
    title: str
    desc: str
    tools: tuple[str, ...]
    outputs: tuple[str, ...]
    gate: str
    actions: dict[str, Any]
    evidence: tuple[tuple[str, str], ...]
    read: Callable[[Context], dict[str, Any]]
    modules: tuple[str, ...] = ()


def _state(done: int, total: int, started: bool = False) -> str:
    if total and done >= total:
        return "PASS"
    return "ACTIVE" if done or started else "PENDING"


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _harness(ctx: Context) -> dict[str, Any]:
    status = "PASS" if ctx.facts["harness_ok"] else "PENDING"
    detail = "Harness projections in place" if status == "PASS" else "Environment awaiting initialization"
    return {"status": status, "detail": detail, "subfases": [
        ("Workspace & Manifest", status, "papersmith.yaml and the versioned base structure"),
        ("Agent Projection", status, "Symbolic links to the operational harnesses"),
    ]}


def agreed_type(root: Path) -> dict[str, Any]:
    """The agreed paper type and variant from ``.papersmith/paper_type.json``,
    with the catalogue's ``line`` and the variant's ``checklist``
    (``has_variants`` says whether the type chooses one)."""
    record = decision.read(root)["paper_type"] or {}
    type_id, variant = record.get("agreed"), record.get("agreed_variant")
    out = {"type": type_id, "variant": variant, "by": record.get("agreed_by"),
           "stale": bool(record.get("agreed_stale")), "line": None, "has_variants": False, "checklist": None}
    if not type_id:
        return out
    try:
        item = paper_types.get(type_id)
    except Exception:  # an unknown or unreadable catalogue entry: the type alone is shown
        return out
    variants = {v["id"]: v for v in item.get("variants") or []}
    out.update(line=item.get("line"), has_variants=bool(variants))
    if variant in variants:
        out["checklist"] = variants[variant].get("checklist")
    return out


def _plausibility_type(ctx: Context) -> dict[str, Any]:
    root, kind = ctx.root, ctx.table.kind
    pool = (root / "sota-pool" / "candidates.json").is_file()
    accepted = decision.read(root)["plausibility"]
    agreed = agreed_type(root)
    type_status = "PENDING"
    if not accepted:
        status = "ACTIVE" if pool else "PENDING"
        detail = ("SOTA candidates found; the plausibility report awaits the operator's acceptance" if pool
                  else "No plausibility report accepted yet (/plausibility)")
    elif not agreed["type"]:
        status = "ACTIVE"
        detail = (f"Plausibility accepted by {accepted.get('accepted_by') or '?'}; "
                  "the paper type awaits the operator's agreement (/paper-type)")
    elif agreed["stale"]:
        status = type_status = "ACTIVE"
        detail = "The agreed paper type belongs to an earlier idea: agree it again (/paper-type)"
    elif agreed["line"] != kind:
        status = type_status = "ACTIVE"
        detail = f"The agreed paper type ({agreed['type']}) is not this workspace's line ({kind})"
    elif agreed["has_variants"] and not agreed["variant"]:
        status = type_status = "ACTIVE"
        detail = (f"Paper type {agreed['type']} agreed with no variant: "
                  "the variant chooses the reporting checklist (/paper-type)")
    else:
        status = type_status = "PASS"
        detail = (f"Paper type {agreed['type']} ({agreed['variant']}) agreed by {agreed['by'] or '?'}"
                  if agreed["variant"] else f"Paper type {agreed['type']} agreed by {agreed['by'] or '?'}")
    return {"status": status, "detail": detail, "subfases": [
        ("SOTA scouting (sota-pool/candidates.json)", "PASS" if pool else "PENDING",
         "About 25 SOTA references scouted by /plausibility"),
        ("Plausibility accepted (operator)", "PASS" if accepted else "PENDING",
         "Recorded in .papersmith/plausibility.json when the operator accepts the report"),
        ("Paper type and variant agreed (operator)", type_status,
         "Recorded in .papersmith/paper_type.json by /paper-type; the variant chooses the checklist"),
    ]}


# ----- the gates, read once per request


def _protocol_gate(ctx: Context) -> dict[str, str]:
    state = ctx.module("records").protocol_state(ctx.root)
    if state["state"] == "current":
        return {"status": "PASS", "detail": (f"Protocol {state['revision']} approved by "
                                             f"{state.get('approved_by') or '?'}; {state['amendments']} amendment(s)")}
    if state["state"] == "changed":
        return {"status": "ACTIVE", "detail": (f"The protocol changed after its approval ({', '.join(state['reasons'])}): "
                                               "record an amendment (study_cli.py protocol amend)")}
    if state["state"] == "corrupt":
        return {"status": "FAIL", "detail": f"The protocol lock is unreadable: {state['message']}"}
    return {"status": "PENDING", "detail": "Not approved yet (study_cli.py protocol approve)"}


def _record_gate(ctx: Context, gate: str) -> dict[str, str]:
    entry = ctx.module("records").gate_state(ctx.root, gate)
    if entry is None:
        return {"status": "PENDING", "detail": f"No {gate} record yet (study_cli.py {gate} record)"}
    if entry.get("state") == "corrupt":
        return {"status": "FAIL", "detail": f"The {gate} record is unreadable: {entry['message']}"}
    if not entry.get("current"):
        return {"status": "ACTIVE", "detail": (f"Stale: the {gate} record covers an earlier protocol lock; "
                                               "the operator records it again")}
    by = entry.get("by") or "?"
    if entry.get("status") == "not-applicable":
        return {"status": "PASS", "detail": f"Not applicable, recorded by {by}: {entry.get('reason') or ''}"}
    if gate == "ethics":
        return {"status": "PASS", "detail": (f"Approved by {entry.get('committee')} ({entry.get('code')}) on "
                                             f"{entry.get('date')}; recorded by {by}")}
    where = f"Registered in {entry.get('registry')} ({entry.get('id')}) on {entry.get('date')}"
    if entry.get("retrospective") is True:
        return {"status": "PASS", "detail": f"{where}, after the first enrolment; recorded by {by}"}
    return {"status": "PASS", "detail": f"{where}; recorded by {by}"}


def _dataset_problem(dc: Any, root: Path, entry: dict) -> tuple[str, str | None]:
    """(``ok`` | ``fail`` | ``owed``, why not passed) of one own dataset."""
    slug = entry["slug"]
    try:
        found = dc.read_dictionary(root, slug)
    except dc.Refusal as refusal:
        return "owed", f"{slug}: the data dictionary is invalid: {refusal.message}"
    if found is None:
        return "owed", f"{slug}: no data dictionary (datasets_cli.py dictionary init)"
    qc_path = dc.datasets_dir(root) / slug / "qc.json"
    if not qc_path.is_file():
        return "owed", f"{slug}: no quality check yet (datasets_cli.py qc)"
    try:
        report = json.loads(qc_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "owed", f"{slug}: datasets/{slug}/qc.json is unreadable: run the quality check again"
    if not isinstance(report, dict):
        return "owed", f"{slug}: datasets/{slug}/qc.json is unreadable: run the quality check again"
    data = root / str(report.get("file") or "")
    if not report.get("file") or _sha(data) != report.get("sha256"):
        return "owed", f"{slug}: the data file changed after its quality check: run it again"
    checked = report.get("dictionary") if isinstance(report.get("dictionary"), dict) else {}
    if checked.get("sha256") != _sha(found[1]):
        return "owed", f"{slug}: the quality check did not use the current data dictionary: run it again"
    if report.get("status") == "fail":
        return "fail", f"{slug}: the quality check failed (datasets/{slug}/qc.json)"
    try:
        pii = dc.pii_problem(root, entry)
    except dc.Refusal as refusal:
        pii = refusal.message
    if pii:
        return "owed", f"{slug}: personal data not de-identified ({pii})"
    return "ok", None


def own_datasets(dc: Any, root: Path) -> list[dict[str, Any]]:
    """Every own dataset with its dictionary, QC and de-identification state."""
    out = []
    for entry in dc.load_registry(root):
        if entry.get("role") != "own":
            continue
        try:
            dictionary = dc.read_dictionary(root, entry["slug"]) is not None
        except dc.Refusal:
            dictionary = False
        try:
            pii_clear = dc.pii_problem(root, entry) is None
        except dc.Refusal:
            pii_clear = False
        state, why = _dataset_problem(dc, root, entry)
        out.append({"slug": entry["slug"], "dictionary": dictionary, "pii_clear": pii_clear,
                    "state": state, "why": why})
    return out


def _data_gate(ctx: Context) -> dict[str, str]:
    owned = own_datasets(ctx.module("datasets_cli"), ctx.root)
    if not owned:
        return {"status": "PENDING", "detail": "No own dataset registered yet (datasets_cli.py own)"}
    failed = [d for d in owned if d["state"] == "fail"]
    owed = [d for d in owned if d["state"] != "ok"]
    if not owed:
        return {"status": "PASS", "detail": (f"{len(owned)} own dataset(s): quality checked on the current data "
                                             "and dictionary, no personal data left to de-identify")}
    return {"status": "FAIL" if failed else "ACTIVE", "detail": (failed or owed)[0]["why"]}


def _flow_status(ctx: Context) -> dict[str, Any]:
    flow_cli = ctx.module("flow_cli")
    return flow_cli.cmd_status(argparse.Namespace(root=str(ctx.root)), ctx.root)


def _flow_gate(ctx: Context) -> dict[str, str]:
    try:
        signoff = _flow_status(ctx)["signoff"]
    except ctx.module("flow_cli").FlowError as error:
        return {"status": "FAIL", "detail": f"The participant flow records are unreadable ({error.code}): {error.message}"}
    if signoff is None:
        return {"status": "PENDING", "detail": "Not signed off yet: valid counts and a current figure first"}
    if not signoff["current"]:
        return {"status": "ACTIVE", "detail": "Stale: the counts or the figure changed after the sign-off"}
    return {"status": "PASS", "detail": f"Signed off by {signoff.get('by') or '?'} at {signoff.get('at') or '?'}"}


@dataclass(frozen=True)
class Gate:
    """One operator gate the board lists: read from evidence, never passed by the board."""

    id: str
    name: str
    criteria: str
    step: str
    read: Callable[[Context], dict[str, str]]
    module: str | None = None


GATES: dict[str, Gate] = {gate.id: gate for gate in (
    Gate(PROTOCOL_GATE, "Study Protocol Approval Gate",
         "The operator approved a managed revision of protocol/study-protocol-<slug>-vNN.md (study_cli.py protocol "
         "approve --by <name>), pinned by its sha256 in study/protocol.lock.json; it stays current while that "
         "revision is unchanged and no newer one exists, and a change is an amendment with its reason. No analysis "
         "is confirmatory before it.", "study_protocol", _protocol_gate, "records"),
    Gate(ETHICS_GATE, "Ethics Record Gate",
         "The operator recorded the ethics approval (committee, code, date, consent route) or why none applies "
         "(study_cli.py ethics record --by <name>), bound to the current protocol lock; an amendment makes it stale "
         "until it is recorded again.", "ethics_registration", lambda ctx: _record_gate(ctx, "ethics"), "records"),
    Gate(REGISTRATION_GATE, "Registration Record Gate",
         "The operator recorded the study registration (registry, id, date, first enrolment) or why none applies "
         "(study_cli.py registration record --by <name>), bound to the current protocol lock; an amendment makes it "
         "stale until it is recorded again.", "ethics_registration",
         lambda ctx: _record_gate(ctx, "registration"), "records"),
    Gate(DATA_GATE, "Data Quality Gate",
         "Every own dataset has its quality check (datasets/<slug>/qc.json) run on its current data file against "
         "its current data dictionary, with no failed status, and every column the dictionary flags as personal "
         "data is covered by a current de-identification record. Read from the files; the board never records it.",
         "data", _data_gate, "datasets_cli"),
    Gate(FLOW_GATE, "Participant Flow Sign-off Gate",
         "The participant flow counts in study/flow.json are valid, paper/Figures/participant-flow.svg is drawn from "
         "them and the operator signed them off (flow_cli.py signoff --by <name>); it stays current while the "
         "counts and the figure are unchanged. The writing starts after it.",
         "participant_flow", _flow_gate, "flow_cli"),
)}


# ----- the steps that read the gates and the records


def _study_protocol(ctx: Context) -> dict[str, Any]:
    gate = ctx.gates[PROTOCOL_GATE]
    revisions = ctx.module("records").managed_revisions(ctx.root)
    if gate["status"] == "PENDING":
        status = "ACTIVE" if revisions else "PENDING"
        detail = (f"{len(revisions)} protocol revision(s); awaiting the operator's approval (G-STUDY-PROTOCOL)"
                  if revisions else "No study protocol revision yet (/study-protocol-deliberation)")
    else:
        status = "PASS" if gate["status"] == "PASS" else "ACTIVE"
        detail = gate["detail"]
    return {"status": status, "detail": detail, "subfases": [
        ("Protocol revisions (protocol/study-protocol-*.md)", "PASS" if revisions else "PENDING",
         f"{len(revisions)} managed revision(s); latest {revisions[-1][1]}" if revisions
         else "No managed revision yet"),
        ("Operator approval (G-STUDY-PROTOCOL)", gate["status"], gate["detail"]),
    ]}


def _ethics_registration(ctx: Context) -> dict[str, Any]:
    ethics, registration = ctx.gates[ETHICS_GATE], ctx.gates[REGISTRATION_GATE]
    passed = sum(1 for gate in (ethics, registration) if gate["status"] == "PASS")
    started = any(gate["status"] != "PENDING" for gate in (ethics, registration))
    return {"status": _state(passed, 2, started),
            "detail": f"{passed} of 2 operator records current (ethics, registration)", "subfases": [
        ("Ethics approval (G-ETHICS, operator)", ethics["status"], ethics["detail"]),
        ("Registration (G-REGISTRATION, operator)", registration["status"], registration["detail"]),
    ]}


def _data(ctx: Context) -> dict[str, Any]:
    gate = ctx.gates[DATA_GATE]
    owned = own_datasets(ctx.module("datasets_cli"), ctx.root)
    n = len(owned)
    dictionaries = sum(1 for d in owned if d["dictionary"])
    clear = sum(1 for d in owned if d["pii_clear"])
    status = "PASS" if gate["status"] == "PASS" else ("ACTIVE" if owned else "PENDING")
    # One unit per own dataset's dictionary, QC and de-identification.
    done = dictionaries + clear + sum(1 for d in owned if d["state"] == "ok")
    return {"status": status, "detail": gate["detail"],
            "progress": round(done / (3 * n), 3) if status == "ACTIVE" else None, "subfases": [
        ("Own data registered (data-use statement)", "PASS" if owned else "PENDING",
         f"{n} own dataset(s) in datasets/registry.json"),
        ("Data dictionary (datasets/<slug>/dictionary.json)", _state(dictionaries, n),
         f"{dictionaries} of {n} own dataset(s) with a valid data dictionary"),
        ("Quality check (G-DATA-QC)", gate["status"], gate["detail"]),
        ("De-identification of personal data", _state(clear, n),
         f"{clear} of {n} own dataset(s) with no personal data left to de-identify"),
    ]}


def _analysis(ctx: Context) -> dict[str, Any]:
    log_module = ctx.module("analysis_log")
    log = log_module.log_state(ctx.root)
    if log["state"] == "absent":
        return {"status": "PENDING", "detail": "No analysis logged yet (analysis/log.jsonl)", "subfases": [
            ("Analysis log (analysis/log.jsonl)", "PENDING", "No analysis logged yet (analysis/log.jsonl)")]}
    if log["state"] != "ok":
        detail = f"The analysis log is unreadable: {log['message']}"
        return {"status": "ACTIVE", "detail": detail,
                "subfases": [("Analysis log (analysis/log.jsonl)", "ACTIVE", detail)]}
    entries = log_module.read_log(ctx.root)
    analyses = log_module.analyses(entries)
    stopped = log_module.interrupted(entries)
    failed = [entry for entry in analyses if entry.get("exit_code") not in (None, 0)]
    confirmatory = sum(1 for entry in analyses if entry.get("label") == "confirmatory")
    exploratory = len(analyses) - confirmatory
    status = "PASS" if confirmatory and not stopped else ("ACTIVE" if entries else "PENDING")
    return {"status": status,
            "detail": f"{len(analyses)} analysis entries logged: {confirmatory} confirmatory, {exploratory} exploratory",
            "subfases": [
        ("Analysis log (analysis/log.jsonl)", "PASS" if analyses else "ACTIVE",
         f"{len(entries)} entries, hash chain intact"),
        ("Confirmatory analyses (outcomes of the locked protocol)", "PASS" if confirmatory else "PENDING",
         f"{confirmatory} confirmatory, {exploratory} exploratory; the label is computed, never chosen"),
        ("Interrupted or failed runs", "ACTIVE" if stopped or failed else "PASS",
         f"{len(stopped)} interrupted, {len(failed)} failed"),
    ]}


_FIGURE_TEXT = {"current": "Drawn from the current counts", "stale": "Stale: drawn from other counts",
                "absent": "Not drawn yet (flow_cli.py render)"}


def _participant_flow(ctx: Context) -> dict[str, Any]:
    gate = ctx.gates[FLOW_GATE]
    state = _flow_status(ctx)
    figure = state["figure"]
    if state["flow"] == "absent":
        status = "PENDING"
        detail = "No participant flow yet (flow_cli.py template <id> --write)"
        counts = "No study/flow.json yet"
    else:
        counts = f"Template {state['template']}; {state['problems']} arithmetic problem(s)"
        status = "PASS" if gate["status"] == "PASS" else "ACTIVE"
        if gate["status"] == "PASS":
            detail = gate["detail"]
        elif state["flow"] == "invalid":
            detail = f"The participant flow has {state['problems']} arithmetic problem(s) (flow_cli.py check)"
        elif figure != "current":
            detail = "Counts valid; draw the flow figure again (flow_cli.py render)"
        elif gate["status"] == "ACTIVE":
            detail = "The flow changed after its sign-off: sign it off again (flow_cli.py signoff)"
        else:
            detail = "Counts valid and drawn; awaiting the operator's sign-off (G-FLOW)"
    return {"status": status, "detail": detail, "subfases": [
        ("Counts entered and checked (study/flow.json)", "PASS" if state["flow"] == "valid" else
         ("ACTIVE" if state["flow"] == "invalid" else "PENDING"), counts),
        ("Flow figure (paper/Figures/participant-flow.svg)", "PASS" if figure == "current" else
         ("ACTIVE" if figure == "stale" else "PENDING"), _FIGURE_TEXT.get(figure, figure)),
        ("Participant flow sign-off (G-FLOW, operator)", gate["status"], gate["detail"]),
    ]}


def _writing(ctx: Context) -> dict[str, Any]:
    facts = ctx.facts
    done, total = facts["blocks_written"], facts["blocks_total"]
    blocks = f"{done}/{total} canonical blocks written ({facts['words']} words)"
    if total and done >= total:
        status = "PASS"
    else:
        status = "ACTIVE" if facts["has_scaffold"] or done else "PENDING"
    detail = blocks if facts["has_scaffold"] else "paper/main.tex awaiting scaffolding"
    return {"status": status, "detail": detail,
            "progress": round(done / max(1, total), 3) if status == "ACTIVE" else None, "subfases": [
        ("Scaffolding from the study contracts", "PASS" if facts["has_scaffold"] else "PENDING",
         "paper/main.tex opened from the section contracts in sections/"),
        ("Declarations (study-registration and ethics-approval included)",
         "PASS" if facts["has_decl"] else "PENDING",
         "Recorded with /paper-writing mark; they repeat what the ethics and registration records hold"),
        ("Blocks written", _state(done, total), blocks),
    ]}


def _paper(ctx: Context) -> dict[str, Any]:
    facts = ctx.facts
    if facts["pdf_exists"]:
        status = "PASS"
        detail = f"PDF manuscript compiled ({facts['pdf_pages']} pages, {facts['pdf_kb']} KB)"
    else:
        status = "ACTIVE" if facts["figures"] else "PENDING"
        detail = "paper/main.pdf not compiled yet"
    return {"status": status, "detail": detail, "subfases": [
        ("Figures reviewed (/figure-review)", "PASS" if facts["figures"] else "PENDING",
         f"{facts['figures']} vector figure(s) in paper/Figures/"),
        ("Compiled PDF (paper/main.pdf)", "PASS" if facts["pdf_exists"] else "PENDING", detail),
    ]}


def checklist_detail(ctx: Context) -> tuple[str, str]:
    """(sub-step name, detail) of the reporting checklist the agreed variant chooses."""
    agreed = agreed_type(ctx.root)
    if not agreed["type"] or (agreed["has_variants"] and not agreed["variant"]):
        return ("Reporting checklist", "No variant agreed yet (/paper-type): the variant chooses the reporting "
                                       "checklist")
    checklist = agreed["checklist"]
    if not checklist:
        return ("Reporting checklist", f"No checklist data yet for the {agreed['variant'] or agreed['type']} "
                                       "variant: the items are checked by hand")
    name, items = checklist, None
    engine = ctx.module("checklists")
    if engine is not None:
        try:
            guideline = engine.load_guideline(checklist)
            name, items = guideline["name"], len(guideline["items"])
        except Exception:  # an unshipped or invalid guideline: its id alone is named
            pass
    command = f"checklist_cli.py check --guideline {checklist} --root ."
    detail = (f"{name}: {items} items, computed on demand ({command}), never on the board's refresh"
              if items is not None else f"Computed on demand ({command}), never on the board's refresh")
    return (f"Reporting checklist ({checklist})", detail)


def _reporting(ctx: Context) -> dict[str, Any]:
    verdict = ctx.facts["audit"]
    status = "PASS" if verdict is True else "PENDING"
    detail = ("Cross-cutting audit run and passed" if verdict is True else
              "The last audit failed: check .papersmith/audit.json" if verdict is False else
              "Cross-cutting audit pending")
    name, checklist = checklist_detail(ctx)
    return {"status": status, "detail": detail, "subfases": [
        (name, "PENDING", checklist),
        ("Workspace audit (smith audit .)", status, detail),
    ]}


_WRITING_ACTIONS = {
    "skills": ["paper-writing"],
    "agent": "paper-writing",
    "actions": [
        *copy.deepcopy(phase_actions.ACTIONS["scaffolding"]["actions"][:1]),
        *copy.deepcopy(phase_actions.ACTIONS["declarations"]["actions"][:1]),
        *copy.deepcopy(phase_actions.ACTIONS["writing"]["actions"]),
    ],
}

#: Every step an empirical line may show, by id.
STEPS: dict[str, Step] = {step.id: step for step in (
    Step("harness", "Harness", "Environment Setup & Harness",
         "Workspace structure, harness projections (.claude, .opencode, .pi, .agents), the micromamba environment and runtime validation.",
         ("read", "bash"), (".papersmith/", "papersmith.yaml"), "G-HARNESS",
         copy.deepcopy(phase_actions.ACTIONS["harness"]), phase_actions.EVIDENCE["harness"], _harness),
    Step("plausibility_type", "Plausibility and paper type", "Plausibility & Paper Type",
         "The state of the art scouted around the idea, the plausibility report accepted by the operator, and the paper type and variant agreed with /paper-type; the variant chooses the reporting checklist.",
         ("read", "write", "http"), ("sota-pool/candidates.json", ".papersmith/paper_type.json"), "G-PAPER-TYPE", {
             "skills": ["plausibility", "paper-type"],
             "agent": "plausibility, paper-type-advisor & operator",
             "actions": [
                 _prompt("/plausibility", "Explore the plausibility of the idea", [
                     "Write the idea in at least two sentences: the question and the data the study holds or will collect.",
                     "The agent scouts about 25 SOTA references by their abstracts and grades the claims with verbatim quotes.",
                     "Nothing moves on until you accept the report.",
                 ], "E.g.: Hospital admissions for asthma rise after wildfire smoke episodes. We hold five years of admissions …",
                     min_sentences=2),
                 _prompt("/paper-type", "Agree the paper type and its variant", [
                     "The agent scores the idea against the paper types and discusses its suggestion with you.",
                     "You agree the type and the variant: observational (STROBE), diagnostic validation (STARD 2015) or measurement instrument (COSMIN).",
                     "The variant chooses the reporting checklist of step 10.",
                 ], "E.g.: discuss whether this is an observational or a measurement-instrument study.", optional=True),
                 _redirect("View the paper types", "papertype", "Every paper type with its score, guideline and variants."),
             ],
         }, (("Candidate pool", "sota-pool/candidates.json"), ("Plausibility acceptance", ".papersmith/plausibility.json"),
             ("Agreed paper type", ".papersmith/paper_type.json")), _plausibility_type),
    Step("study_protocol", "Study protocol", "Study Protocol (G-STUDY-PROTOCOL)",
         "The study protocol as managed revisions: the research question, exactly one primary outcome, the secondary outcomes, the design, the eligibility, the sample size with its justification and the analysis plan. The operator approves a revision before any analysis; a later change is an amendment with its reason.",
         ("read", "write"), ("protocol/study-protocol-<slug>-vNN.md", "study/protocol.lock.json"), PROTOCOL_GATE, {
             "skills": ["study-protocol-deliberation"],
             "agent": "study-protocol-deliberation & operator",
             "actions": [
                 _prompt("/study-protocol-deliberation", "Deliberate the protocol with the agent", [
                     "The agent drafts the protocol with you as labelled fields: question, one primary outcome, secondary outcomes, design, eligibility, sample size and analysis plan.",
                     "The choice of the primary outcome is yours; the agent never invents data or a sample size from data it has not seen.",
                     "Each accepted change is published as a new managed revision under protocol/.",
                 ], "E.g.: draft the first protocol for the asthma admissions study.", optional=True),
                 _command(f"{STUDY_CLI} protocol status --root .", "Protocol lock status",
                          "Whether the approved revision is current, changed or absent."),
                 _command(f"{STUDY_CLI} protocol approve --root . --by {_OPERATOR}",
                          "Approve the protocol (operator, G-STUDY-PROTOCOL)",
                          "Only the operator approves; the approval pins the revision's sha256."),
                 _command(f'{STUDY_CLI} protocol amend --root . --by {_OPERATOR} --reason "<why>"',
                          "Record an amendment", "A change after the approval, with its reason; the methods report it."),
             ],
         }, (("Protocol revisions", "protocol/study-protocol-*.md"),
             ("Protocol approval (G-STUDY-PROTOCOL)", "study/protocol.lock.json")), _study_protocol, ("records",)),
    Step("ethics_registration", "Ethics and registration", "Ethics & Registration Records",
         "The ethics approval and the study registration, each recorded by the operator against the approved protocol, or recorded as not applicable with the reason; an amendment of the protocol makes them stale.",
         ("read", "write"), ("study/ethics.json", "study/registration.json"), ETHICS_GATE, {
             "skills": [],
             "agent": "operator",
             "actions": [
                 _command(f'{STUDY_CLI} ethics record --root . --by {_OPERATOR} --committee "<committee>" '
                          f'--code "<approval code>" --date <YYYY-MM-DD> --consent "<consent route>"',
                          "Record the ethics approval (operator, G-ETHICS)",
                          "The committee, the approval code, its date and the consent route."),
                 _command(f'{STUDY_CLI} ethics record --root . --by {_OPERATOR} --not-applicable --reason "<why>"',
                          "Record that no ethics approval applies (operator)", "With the reason, in your words."),
                 _command(f'{STUDY_CLI} registration record --root . --by {_OPERATOR} --registry "<registry>" '
                          f'--id "<registration id>" --date <YYYY-MM-DD> --first-enrolment <YYYY-MM-DD>',
                          "Record the registration (operator, G-REGISTRATION)",
                          "A registration after the first enrolment is reported as retrospective."),
                 _command(f'{STUDY_CLI} registration record --root . --by {_OPERATOR} --not-applicable --reason "<why>"',
                          "Record that no registration applies (operator)", "With the reason, in your words."),
                 _command(f"{STUDY_CLI} status --root .", "Study records status",
                          "The protocol, ethics and registration states and their warnings."),
             ],
         }, (("Ethics record (G-ETHICS)", "study/ethics.json"), ("Registration record (G-REGISTRATION)", "study/registration.json")),
         _ethics_registration, ("records",)),
    Step("data", "Data", "Own Data, Dictionary & Quality (G-DATA-QC)",
         "The data the operator collected, registered with its data-use statement, described by a data dictionary, measured by a quality check against it, and de-identified where the dictionary flags personal data. The assistant never generates or edits data.",
         ("read", "write"), ("datasets/registry.json", "datasets/<slug>/dictionary.json", "datasets/<slug>/qc.json"), DATA_GATE, {
             "skills": ["datasets"],
             "agent": "datasets & operator",
             "actions": [
                 _command(f'{DATASETS_CLI} own --slug <slug> --by {_OPERATOR} --statement "<how the data may be used>"',
                          "Register your own data (operator)", "Its data-use statement, in your words."),
                 _command(f"{DATASETS_CLI} dictionary init --slug <slug> --file <data.csv>",
                          "Scaffold the data dictionary", "One entry per column; you complete every type, unit, range and PII flag."),
                 _command(f"{DATASETS_CLI} dictionary check --slug <slug>", "Check the data dictionary",
                          "Validates datasets/<slug>/dictionary.json."),
                 _command(f"{DATASETS_CLI} qc --slug <slug> --file <data.csv>", "Run the quality check (G-DATA-QC)",
                          "Measures the data against its dictionary into datasets/<slug>/qc.json."),
                 _command(f'{DATASETS_CLI} deidentify --slug <slug> --by {_OPERATOR} --statement "<how the PII columns were removed>"',
                          "Record the de-identification (operator)", "How the columns flagged as personal data were removed or transformed."),
                 _command(f"{DATASETS_CLI} status", "Datasets status", "Every registered dataset with its QC status."),
             ],
         }, (("Dataset registry", "datasets/registry.json"), ("Data dictionaries", "datasets/*/dictionary.json"),
             ("Quality checks (G-DATA-QC)", "datasets/*/qc.json")), _data, ("datasets_cli",)),
    Step("analysis", "Analysis", "Analysis Log",
         "Every analysis through the append-only, hash-chained log: a wrapped script or the operator's entry for a GUI tool. The label is computed, never chosen: confirmatory only for an outcome and plan entry of the current locked protocol, exploratory otherwise.",
         ("read", "bash"), ("analysis/log.jsonl",), "G-ANALYSIS", {
             "skills": [],
             "agent": "analysis log & operator",
             "actions": [
                 _requires(_command(f"{ANALYSIS_CLI} run --root . --outcome <outcome-id> --input <data-file> "
                                    "--output <result-file> -- <command>", "Run a logged analysis",
                                    "Hashes the script, the inputs and the outputs and labels the run."), *ANALYSIS_GATES),
                 _requires(_command(f'{ANALYSIS_CLI} record --root . --outcome <outcome-id> --by {_OPERATOR} '
                                    '--tool "<tool name>"', "Record a GUI analysis (operator)",
                                    "Your attested entry for an analysis run outside a script."), *ANALYSIS_GATES),
                 _command(f"{ANALYSIS_CLI} status --root .", "Analysis log status",
                          "The runs with their labels and the protocol outcomes still unanalysed."),
             ],
         }, (("Analysis log", "analysis/log.jsonl"),), _analysis, ("analysis_log",)),
    Step("participant_flow", "Participant flow", "Participant Flow (G-FLOW)",
         "The participant flow counts the operator enters (STROBE or STARD 2015 template), checked for their arithmetic, drawn as the flow figure and signed off by the operator; any later edit makes the sign-off stale.",
         ("read", "write"), ("study/flow.json", "paper/Figures/participant-flow.svg", "study/flow-signoffs.json"), FLOW_GATE, {
             "skills": [],
             "agent": "participant flow & operator",
             "actions": [
                 _command(f"{FLOW_CLI} template <strobe|stard-2015> --root . --write", "Write the empty flow",
                          "study/flow.json with no counts; you enter every count."),
                 _command(f"{FLOW_CLI} check --root .", "Check the counts", "Every arithmetic problem of the flow."),
                 _command(f"{FLOW_CLI} render --root .", "Draw the flow figure",
                          "Writes paper/Figures/participant-flow.svg from valid counts."),
                 _command(f"{FLOW_CLI} signoff --root . --by {_OPERATOR}", "Sign the flow off (operator, G-FLOW)",
                          "Refused on invalid counts or a missing or stale figure."),
                 _command(f"{FLOW_CLI} status --root .", "Participant flow status",
                          "The counts' validity, the figure and the latest sign-off."),
             ],
         }, (("Participant flow counts", "study/flow.json"), ("Participant flow figure", "paper/Figures/participant-flow.svg"),
             ("Participant flow sign-offs (G-FLOW)", "study/flow-signoffs.json")), _participant_flow, ("flow_cli",)),
    Step("writing", "Scaffolding, declarations and writing", "Scaffolding, Declarations & Writing",
         "The paper/ tree opened from the study's section contracts, the declarations recorded (study-registration and ethics-approval included) and one block written at a time; every number is copied from a record.",
         ("read", "write"), ("paper/main.tex", "sections/*.md"), "G-WRITING", _WRITING_ACTIONS,
         (("Manuscript", "paper/main.tex"), ("Section contracts", "sections/*.md")), _writing),
    Step("paper", "Figures and paper", "Figures & PDF Manuscript",
         "Every figure reviewed with /figure-review and paper/main.tex compiled to paper/main.pdf.",
         ("read", "bash", "latexmk"), ("paper/Figures/", "paper/main.pdf"), "G-PDF", {
             "skills": ["figure-review", "paper-writing"],
             "agent": "figure-review & pdflatex",
             "actions": [
                 *copy.deepcopy(phase_actions.ACTIONS["figures"]["actions"][:1]),
                 *copy.deepcopy(phase_actions.ACTIONS["paper"]["actions"]),
             ],
         }, (("Compiled figures", "paper/Figures/*.pdf"), ("Compiled PDF", "paper/main.pdf")), _paper),
    Step("reporting_audit", "Reporting check and audit", "Reporting Check & Audit",
         "The reporting checklist of the agreed variant (item by item: satisfied, missing or needs judgment), the study checks of paper_cli.py verify, the final judge and the cross-cutting audit; audits report, they never repair.",
         ("read", "bash"), (".papersmith/audit.json",), "G-AUDIT", {
             "skills": ["skill-audit"],
             "agent": "checklist engine, skill-audit & smith audit",
             "actions": [
                 _command(f"{CHECKLIST_CLI} check --guideline <checklist-id> --root .", "Reporting checklist",
                          "The variant's checklist item by item: satisfied, missing or needs judgment."),
                 *copy.deepcopy(phase_actions.ACTIONS["audit"]["actions"]),
             ],
         }, phase_actions.EVIDENCE["audit"], _reporting, ("checklists",)),
)}


# --------------------------------------------------------------------------- line tables


@dataclass(frozen=True)
class LineTable:
    """One empirical line's board: its steps (ids of :data:`STEPS`) in order,
    the gates it lists (ids of :data:`GATES`), the operator gate each step
    waits for on top of the step before it, the steps that wait for nothing
    and the transversal step a later step never waits for."""

    kind: str
    steps: tuple[str, ...]
    gates: tuple[str, ...]
    phase_gates: Mapping[str, str]
    ungated: frozenset[str]
    transversal: str
    #: The flow diagram ``/api/flow`` serves; per-line diagrams are deferred (E11).
    flow_html: str = "papersmith-flow.html"


#: kind -> its table. A later line adds its own here.
LINE_TABLES: dict[str, LineTable] = {
    "observational-measurement": LineTable(
        kind="observational-measurement",
        steps=("harness", "plausibility_type", "study_protocol", "ethics_registration", "data", "analysis",
               "participant_flow", "writing", "paper", "reporting_audit"),
        gates=(PROTOCOL_GATE, ETHICS_GATE, REGISTRATION_GATE, DATA_GATE, FLOW_GATE),
        phase_gates={"analysis": DATA_GATE, "writing": FLOW_GATE},
        ungated=frozenset({"harness", "reporting_audit"}),
        transversal="reporting_audit",
    ),
}


def _fallback_note(detail: str, module: str, warning: str) -> str:
    return f"{detail} (the workspace's {module} did not load ({warning}); read with the dashboard's own copy)"


def _absent(module: str) -> str:
    return f"{module} is not available in this workspace or the dashboard; the study records cannot be read"


def _failure(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None) or str(exc)
    return f"Study records unreadable ({code if isinstance(code, str) else type(exc).__name__}): {message}"


def _read_gates(ctx: Context) -> None:
    for gate_id in ctx.table.gates:
        gate = GATES[gate_id]
        if gate.module and ctx.module(gate.module) is None:
            ctx.gates[gate_id] = {"status": "PENDING", "detail": _absent(Path(MODULES[gate.module]).name)}
            continue
        try:
            ctx.gates[gate_id] = gate.read(ctx)
        except Exception as exc:  # a corrupt record fails its gate, never the board
            ctx.gates[gate_id] = {"status": "FAIL", "detail": _failure(exc)}


def board(table: LineTable, root: Path, facts: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The line's phase cards and gates, before ``phase_actions.attach``.

    ``facts`` are the paper-tree values the server already measured (see
    ``review_board.board``)."""
    ctx = Context(root=Path(root), facts=facts, table=table)
    _read_gates(ctx)
    fases = []
    for number, stage in enumerate(table.steps, 1):
        step = STEPS[stage]
        missing = [name for name in step.modules if ctx.module(name) is None]
        if missing:
            info: dict[str, Any] = {"status": "PENDING", "detail": _absent(Path(MODULES[missing[0]]).name),
                                    "subfases": []}
        else:
            try:
                info = step.read(ctx)
            except Exception as exc:  # an unreadable record degrades its step, not the board
                info = {"status": "PENDING", "detail": _failure(exc), "subfases": []}
        for name in step.modules:
            warning = ctx.warning(name)
            if warning:
                info["detail"] = _fallback_note(info["detail"], Path(MODULES[name]).name, warning)
        status = info["status"]
        progress = info.get("progress")
        if progress is None:
            progress = 1.0 if status == "PASS" else (0.5 if status == "ACTIVE" else 0.0)
        subfases = [review_board._sub(f"{number}.{index}", name, sub_status, detail)
                    for index, (name, sub_status, detail) in enumerate(info["subfases"], 1)]
        fases.append({
            "id": f"Fase {number}", "stage_id": stage, "name": f"Phase {number}: {step.title}", "gate": step.gate,
            "desc": step.desc, "tools": list(step.tools), "outputs": list(step.outputs),
            "status": status, "progress": progress, "detail": info["detail"],
            "subfases": subfases or [review_board._sub(f"{number}.1", step.label, status, info["detail"])],
        })
    return fases, _gates(ctx)


def _gates(ctx: Context) -> list[dict[str, Any]]:
    table, facts = ctx.table, ctx.facts
    position = {stage: f"Fase {number}" for number, stage in enumerate(table.steps, 1)}
    out = [{"id": gate_id, "name": GATES[gate_id].name, "status": ctx.gates[gate_id]["status"],
            "criteria": GATES[gate_id].criteria, "reviewer": "operator", "phase": position[GATES[gate_id].step]}
           for gate_id in table.gates]
    done, total = facts["blocks_written"], facts["blocks_total"]
    writing, paper = position.get("writing"), position.get("paper")
    return out + [
        {"id": "G1", "name": "Writing Readiness Gate", "status": "PASS" if facts["has_scaffold"] else "PENDING",
         "criteria": "Section contracts validated with a closed grammar and resolved dependencies.",
         "reviewer": "contract-auditor", "phase": writing},
        {"id": "G2", "name": "Coupling Verification Gate", "status": "PASS" if facts["has_decl"] else "PENDING",
         "criteria": "Demanded facts (formulation, design, results) coupled with the authorship and funding declarations.",
         "reviewer": "paper-graph-auditor", "phase": writing},
        {"id": "G3", "name": "Grounding & Style Leak Gate",
         "status": "PASS" if total and done >= total else ("ACTIVE" if done else "PENDING"),
         "criteria": "No empty citations or placeholders; strict isolation of bibliographic sources.",
         "reviewer": "grounding-auditor", "phase": writing},
        {"id": "G4", "name": "Diagram & Raster Gate", "status": "PASS" if facts["figures"] else "PENDING",
         "criteria": "Compilation check of TikZ diagrams, methodological schemes and vector figures.",
         "reviewer": "figure-auditor", "phase": paper},
    ]


# --------------------------------------------------------------------------- the rest of the status


def telemetry(fases: list[dict[str, Any]], date: str) -> list[dict[str, Any]]:
    """One row per started step, in the experimental shape, with no numbers."""
    return [{"fase": phase["name"], "gate": phase["gate"], "tool_uses": None, "duracion": None, "tokens": None,
             "veredicto": phase["status"], "fecha": date, "note": TELEMETRY_NOTE}
            for phase in fases if phase["status"] in ("PASS", "ACTIVE")]


#: (folder or file, glob, category): the study's records shown as artifacts.
_ARTIFACTS = (
    ("protocol", "*", "Study Protocol"),
    ("study", "*", "Study Records"),
    ("analysis", "log.jsonl", "Analysis Log"),
    ("datasets", "*/qc.json", "Data Quality"),
    ("paper/Figures", "participant-flow.svg", "Participant Flow"),
)


def artifacts(root: Path) -> list[dict[str, Any]]:
    """The study's records: ``protocol/*``, ``study/*``, ``analysis/log.jsonl``,
    ``datasets/*/qc.json`` and the participant flow figure."""
    root = Path(root)
    out = []
    for folder, pattern, category in _ARTIFACTS:
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.glob(pattern)):
            if path.name.startswith(".") or not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            name = rel[len("datasets/"):] if folder == "datasets" else path.name
            out.append({"rel_path": rel, "name": name, "category": category,
                        "size_kb": round(path.stat().st_size / 1024, 1)})
    return out


#: A contract's ``mode`` -> how it relates to the rest of the paper.
_MODE_RELATIONS = {
    "transposition": "Transcribes the study's records: every number and fact comes from a record on disk.",
    "argument": "Argues from the results and the cited literature; it adds no number the records do not hold.",
}
_DEFAULT_RELATION = "Written from the study's records and the cited literature."
_VARIANT = re.compile(r"variant\s+`(?P<variant>[^`]+)`")
_EXTENT = re.compile(r"^\*\*Extent\*\*(?P<rest>.*)$", re.M)


def _role(block: dict, rest: str) -> str:
    optional = bool(block.get("optional")) or "optional" in rest
    variant = _VARIANT.search(rest)
    if variant:
        return (f"Optional study block of the {variant.group('variant')} variant" if optional
                else f"Study block of the {variant.group('variant')} variant")
    return "Optional study block" if optional else "Study block"


def _contract(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    meta, body = _ex._split_frontmatter(text)
    section = meta.get("section") if isinstance(meta, dict) else None
    if not isinstance(section, str):
        return None
    after_title = re.split(r"^#\s.*$", body, maxsplit=1, flags=re.M)
    principles = review_board._first_sentence(after_title[-1])
    mode = meta.get("mode") if isinstance(meta.get("mode"), dict) else {}
    extent = _EXTENT.search(body)
    extent_text = extent.group("rest").lower() if extent else ""
    headings = {m.group("id"): m for m in review_board._HEADING.finditer(body)}
    blocks = []
    for block in _ex._blocks_of(meta):
        block_id = str(block.get("id"))
        heading = headings.get(block_id)
        question = ""
        if heading:
            following = body[heading.end():]
            nxt = re.search(r"^#{1,6}\s", following, re.M)
            question = review_board._first_sentence(following[: nxt.start()] if nxt else following)
        blocks.append({"id": f"{section}.{block_id}", "role": _role(block, heading.group("rest") if heading else ""),
                       "question": question or block_id})
    return {"principles": principles,
            "cross_relations": _MODE_RELATIONS.get(str(mode.get("value")), _DEFAULT_RELATION),
            "has_figures": "figure" in extent_text and "belongs to" not in extent_text,
            "blocks": blocks}


def section_metadata(root: Path) -> dict[str, dict[str, Any]]:
    """The line's contracts' metadata keyed by file stem, read from each
    contract (its opening sentence, its mode, its extent and its blocks); the
    shared back matter keeps the experimental entry (the server's)."""
    out = {}
    for path in sorted((Path(root) / "sections").glob("*.md")):
        found = _contract(path)
        if found is not None:
            out[path.stem] = found
    return out


def stage_for(table: LineTable, phase_id: str) -> str | None:
    """The step a ``/api/phase/run`` id names: a step id or ``Fase N``."""
    text = str(phase_id or "").strip()
    if text in table.steps:
        return text
    parts = text.split()
    if len(parts) == 2 and parts[0].lower() == "fase" and parts[1].isdigit():
        index = int(parts[1]) - 1
        if 0 <= index < len(table.steps):
            return table.steps[index]
    return None


def board_for(table: LineTable) -> lines.Board:
    """The registry entry of ``table``'s line."""
    steps = [STEPS[stage] for stage in table.steps]
    return lines.Board(
        kind=table.kind,
        stages=table.steps,
        labels={step.id: step.label for step in steps},
        actions={step.id: step.actions for step in steps},
        evidence={step.id: step.evidence for step in steps},
        ungated=table.ungated,
        phase_gates=table.phase_gates,
        transversal=table.transversal,
        section_order=(),
        flow_html=table.flow_html,
        stage_for=functools.partial(stage_for, table),
        build=functools.partial(board, table),
        artifacts=artifacts,
        section_metadata=section_metadata,
        telemetry=telemetry,
        shared_checks={"writing": "writing", "paper": "paper", table.transversal: "audit"},
        blocks_total=None,
        decision_stages={"declarations": "writing"},
        revisions_stage=None,
    )


for _table in LINE_TABLES.values():
    if not lines.registered(_table.kind):
        lines.register(board_for(_table))


__all__ = ["ANALYSIS_GATES", "DASHBOARD_SKILLS", "GATES", "LINE_TABLES", "LineTable", "MODULES", "STEPS", "Step",
           "TELEMETRY_NOTE", "agreed_type", "artifacts", "board", "board_for", "checklist_detail", "load_module",
           "own_datasets", "section_metadata", "stage_for", "telemetry"]
