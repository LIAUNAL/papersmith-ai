"""The command center's board for the empirical paper lines (S8, decisions E5, F2, F3, F8).

One board serves every empirical line. A line is a :class:`LineTable`: its
steps in order (drawn from the shared :data:`STEPS` library), the gates its
board lists, its phase locks and the step that is transversal. This module
fills the tables of ``observational-measurement``, ``hardware``,
``lab-simulation``, ``data-resource`` and ``experiment-intervention``
(``src/papersmith/templates/paper-flow-<kind>.md.tpl``); a
later line adds its own table to :data:`LINE_TABLES` (reusing the library's
steps and adding the ones only it has) and is registered with the rest at the
end of this module. ``review_board`` stays the review line's own board.

Every status is read from evidence on disk, never computed from a model:

* G-STUDY-PROTOCOL, and G-SPEC for hardware (the signed specifications are
  the study protocol's lock): ``records.protocol_state`` is ``current``;
* G-ETHICS and G-REGISTRATION: ``records.gate_state`` is recorded and bound
  to the current lock (a not-applicable record counts as passed);
* G-DATA-QC: every own dataset's ``datasets/<slug>/qc.json`` matches the
  sha256 of its data file and of its current data dictionary, its status is
  not ``fail``, and ``datasets_cli.pii_problem`` finds nothing left to
  de-identify (what ``publish`` refuses as ``pii-not-deidentified``);
* G-FLOW: the participant flow sign-off is current (``flow_cli`` status);
* G-CALIBRATION: every instrument the registered raw data files use is
  recorded and not past its calibration due date today, and every registered
  quantity has a current uncertainty budget (the measurement core's
  ``instruments_state``, ``data_state`` and ``budget_state``);
* G-AGREEMENT: an agreement analysis in ``study/agreement.json`` is current
  (``agreement_state``: bound to the registered device and reference files);
* data-resource's own G-ETHICS (:data:`RESOURCE_ETHICS`, through
  ``LineTable.gate_defs``): the ethics record as above, plus the right to
  release every dataset of the resource (each registry entry but a toy set):
  the own-data statement, or a source licence decision that is exactly
  ``allowed`` (a deposit redistributes the data, so an override does not count);
* G-DEPOSIT: ``datasets_cli.deposit_state`` is current for every dataset of
  the resource (stale once a registered file changes, is added or goes missing).
* G-ALLOCATION: ``records.allocation_state`` is current (the operator's
  allocation list unchanged since its record and the protocol not amended);
  the board shows the record's method, row count and concealment and the
  stale reasons, never the list;
* experiment-intervention's own G-REGISTRATION and G-FLOW
  (:data:`TRIAL_REGISTRATION`, :data:`TRIAL_FLOW`), decided by the agreed
  variant (:func:`trial_variant`): a trial with people (``human-trial``)
  needs a current registration made on or before its first enrolment (ICMJE;
  retrospective, unknown and not-applicable records fail with their reason)
  and the signed-off participant flow; a field experiment passes with any
  current registration record and keeps the flow optional (it passes, saying
  so, and never blocks the writing). With no variant agreed (no type, a stale
  agreement or the type without its variant) the human-trial rules apply,
  the stricter case, and both gates say so.

The operator records every one of them with ``--by``; the board only reads
(decision E8). Observational: the analysis actions wait for the protocol, the
ethics and registration records and the data QC; the writing waits for the
flow sign-off. Hardware: the agreement waits for G-CALIBRATION and the writing
for G-AGREEMENT; the ethics, registration and flow gates are listed only once
the operator declares a validation with people (an ethics or registration
record that is not "not applicable", or a participant flow). Lab-simulation:
the uncertainty step waits for the calibration against known values and the
writing for G-CALIBRATION, whose budgets that step computes. Data-resource:
the baselines wait for G-DATA-QC (their actions and their phase lock) and the
writing for G-DEPOSIT; the deposit step waits for nothing in the chain (a
resource is deposited whether or not it has baselines) but its record action
waits for G-DATA-QC. Experiment-intervention: the pre-specified analyses
wait for G-DATA-QC (their phase lock) and their actions for the protocol,
ethics, registration and allocation records too; the writing waits for G-FLOW.

Steps a step after them cannot wait for: a step waits for the one before it,
so a step whose only record appears later must not hold the line. The
hardware's design files are evidenced by the ``repository-url`` declaration,
which ``paper/main.tex`` holds, so the calibration step (the instrument and
reading records) waits for nothing; the open-files steps pass on the
registered raw files unchanged and show the declaration beside them.

The shared modules are read through their own functions, loaded by path the
way ``review_board`` loads ``review_cli.py``: the workspace's copy first, else
the dashboard's own, with a visible note on every step that read it when the
workspace's copy exists but fails to load. A package module is loaded inside a
private package of its own directory, so its relative imports resolve to its
siblings and nothing is added to ``sys.path`` for it; the measurement core,
which imports ``..empirical``, is loaded one level up, inside a private
package of ``skills/_core``. The ``repository-url`` declaration is read with
paper-writing's own ``paper_declarations.read_declaration`` (the dashboard's
copy, as ``manuscript_graph`` reads facts). Every label is English; the
dashboard's Spanish comes from ``static/i18n/server-es.json``.
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
    "measurement": "_core/measurement/records.py",
}

#: name -> the sibling packages under ``skills/_core`` its relative imports
#: reach (``from ..empirical.records import ...``): it is loaded inside a
#: private package of its parent's parent, and those packages' modules count
#: in its stamp.
_NESTED: dict[str, tuple[str, ...]] = {"measurement": ("empirical",)}

_CACHE_LOCK = threading.Lock()
#: path -> (stamp of its directory's modules, module or ``None``, why it did not load);
#: a failed load is cached too, so a broken file is not re-executed per request.
_LOADED: dict[str, tuple[str, Any, str | None]] = {}
_PACKAGES = itertools.count()


def _stamp(path: Path, reaches: tuple[str, ...] = ()) -> str:
    """The sha256 of the module and its sibling modules: a sibling it imports
    (``records`` beside ``analysis_log``) reloads it too, and so does a module
    of a package its relative imports ``reach`` (beside its own package)."""
    digest = hashlib.sha256(path.read_bytes())
    others = [sibling for sibling in sorted(path.parent.glob("*.py")) if sibling != path]
    for package in reaches:
        others += sorted((path.parent.parent / package).glob("*.py"))
    for other in others:
        digest.update(f"{other.parent.name}/{other.name}".encode("utf-8") + b"\0" + other.read_bytes())
    return digest.hexdigest()


def _exec(path: Path, nested: bool = False) -> Any:
    package = f"_papersmith_empirical_{next(_PACKAGES)}"
    holder = types.ModuleType(package)
    holder.__path__ = [str(path.parent.parent if nested else path.parent)]  # type: ignore[attr-defined]
    sys.modules[package] = holder
    if nested:
        inner = types.ModuleType(f"{package}.{path.parent.name}")
        inner.__path__ = [str(path.parent)]  # type: ignore[attr-defined]
        sys.modules[inner.__name__] = inner
        package = inner.__name__
    spec = importlib.util.spec_from_file_location(f"{package}.{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load(path: Path, reaches: tuple[str, ...] | None = None) -> tuple[Any | None, str | None] | None:
    """``(module, None)``, ``(None, why)`` when the file fails to load, or
    ``None`` when it does not exist. Reloaded when it or a sibling changes.
    ``reaches`` (not ``None``) loads it one package level up (see :data:`_NESTED`)."""
    try:
        stamp = _stamp(path, reaches or ())
    except OSError:
        return None
    key = str(path)
    with _CACHE_LOCK:
        cached = _LOADED.get(key)
        if cached and cached[0] == stamp:
            return cached[1], cached[2]
        try:
            loaded: tuple[Any | None, str | None] = (_exec(path, reaches is not None), None)
        except (Exception, SystemExit) as exc:
            loaded = (None, f"{type(exc).__name__} at {path}")
        _LOADED[key] = (stamp, *loaded)
        return loaded


def load_module(root: Path, name: str) -> tuple[Any | None, str | None]:
    """The workspace's copy of module ``name`` (else the dashboard's own), or
    ``None`` when neither loads, and why the workspace's copy was passed over
    when it exists but fails to load (``None`` otherwise)."""
    rel, reaches = MODULES[name], _NESTED.get(name)
    workspace = _load(Path(root) / "skills" / rel, reaches)
    if workspace is not None and workspace[0] is not None:
        return workspace
    warning = workspace[1] if workspace is not None else None
    bundled = _load(DASHBOARD_SKILLS / rel, reaches)
    return (bundled[0] if bundled is not None else None), warning


# --------------------------------------------------------------------------- commands

STUDY_CLI = "python skills/_core/empirical/study_cli.py"
ANALYSIS_CLI = "python skills/_core/empirical/analysis_cli.py"
FLOW_CLI = "python skills/_core/participant_flow/flow_cli.py"
DATASETS_CLI = "python skills/datasets/scripts/datasets_cli.py --root ."
CHECKLIST_CLI = "python skills/_core/checklists/checklist_cli.py"
MEASURE_CLI = "python skills/_core/measurement/measure_cli.py"
PAPER_CLI = "python skills/paper-writing/scripts/paper_cli.py"

PROTOCOL_GATE, ETHICS_GATE, REGISTRATION_GATE = "G-STUDY-PROTOCOL", "G-ETHICS", "G-REGISTRATION"
DATA_GATE, FLOW_GATE = "G-DATA-QC", "G-FLOW"
SPEC_GATE, CALIBRATION_GATE, AGREEMENT_GATE = "G-SPEC", "G-CALIBRATION", "G-AGREEMENT"
DEPOSIT_GATE, ALLOCATION_GATE = "G-DEPOSIT", "G-ALLOCATION"
#: The gates a hardware board lists only when people take part in its validation.
PEOPLE_GATES = (ETHICS_GATE, REGISTRATION_GATE, FLOW_GATE)
#: What an analysis waits for: the protocol, the ethics and registration records and the data QC.
ANALYSIS_GATES = (PROTOCOL_GATE, ETHICS_GATE, REGISTRATION_GATE, DATA_GATE)
#: What a pre-specified analysis of an experiment or intervention waits for: the allocation record too.
TRIAL_ANALYSIS_GATES = (PROTOCOL_GATE, ETHICS_GATE, REGISTRATION_GATE, ALLOCATION_GATE, DATA_GATE)
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
    #: Whether the operator declared a validation with people (see :func:`with_people`).
    people: bool = False

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
    with the catalogue's ``line`` and its reporting ``checklist``
    (``registry.checklist_for``: the variant's, or the family's own for a type
    without variants; ``has_variants`` says whether the type chooses one)."""
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
    out.update(line=item.get("line"), has_variants=bool(item.get("variants")),
               checklist=paper_types.checklist_for(item, variant))
    return out


def _line_has_variants(kind: str) -> bool:
    """Whether the catalogue types of line ``kind`` choose a variant (``True``
    when the catalogue cannot say: the variant wording is the default)."""
    try:
        items = [item for item in paper_types.load() if item.get("line") == kind]
    except Exception:  # an unreadable catalogue: the default wording
        return True
    return not items or any(item.get("variants") for item in items)


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


# ----- the data resource (data-resource)


_NO_RESOURCE = "No dataset registered yet (datasets_cli.py own, or license for a third-party source)"


def resource_datasets(dc: Any, root: Path) -> list[dict[str, Any]]:
    """The registry entries the data resource releases: every one but a toy set."""
    return [entry for entry in dc.load_registry(root) if isinstance(entry, dict) and entry.get("role") != "toy"]


def _combine(*parts: dict[str, str]) -> str:
    """The status of several parts: FAIL if any fails, PASS if all pass,
    PENDING if none started, ACTIVE otherwise."""
    states = [part["status"] for part in parts]
    if "FAIL" in states:
        return "FAIL"
    if all(state == "PASS" for state in states):
        return "PASS"
    return "PENDING" if all(state == "PENDING" for state in states) else "ACTIVE"


_REDISTRIBUTES = "a data resource redistributes its data, so only an allowed licence counts"
_REFUSED_LICENCE = {"refused": "{slug}: the licence was refused: " + _REDISTRIBUTES,
                    "overridden": "{slug}: the licence was accepted by an override: " + _REDISTRIBUTES}
_NO_LICENCE = "{slug}: no licence decision yet (datasets_cli.py license)"


def _release_part(ctx: Context) -> dict[str, str]:
    """The right to release every resource dataset: the own-data statement, or
    a source licence decision that is exactly ``allowed`` (a deposit
    redistributes the data, so an override does not count)."""
    dc = ctx.module("datasets_cli")
    if dc is None:
        return {"status": "PENDING", "detail": _absent(Path(MODULES["datasets_cli"]).name)}
    entries = resource_datasets(dc, ctx.root)
    if not entries:
        return {"status": "PENDING", "detail": _NO_RESOURCE}
    granted = []
    for entry in sorted(entries, key=lambda item: str(item.get("slug"))):
        slug = entry.get("slug")
        licence = entry.get("license") if isinstance(entry.get("license"), dict) else {}
        decision = licence.get("decision") or "missing"
        data_use = entry.get("data_use") if isinstance(entry.get("data_use"), dict) else {}
        if entry.get("role") == "own":
            if not data_use.get("statement") or decision != "allowed":
                return {"status": "ACTIVE", "detail": (f"{slug}: no data-use statement yet "
                                                       "(datasets_cli.py own --by <name>)")}
            granted.append(f"{slug}: own data, data-use statement by {data_use.get('by') or '?'}")
        elif decision != "allowed":
            return {"status": "ACTIVE", "detail": _REFUSED_LICENCE.get(decision, _NO_LICENCE).format(slug=slug)}
        else:
            granted.append(f"{slug}: licence {licence.get('source_name') or '?'} allowed")
    return {"status": "PASS", "detail": "; ".join(granted)}


def _ethics_licence_gate(ctx: Context) -> dict[str, str]:
    ethics, release = _record_gate(ctx, "ethics"), _release_part(ctx)
    status = _combine(ethics, release)
    if status == "PASS":
        n = len(resource_datasets(ctx.module("datasets_cli"), ctx.root))
        return {"status": status, "detail": f"{n} dataset(s) with the right to release; ethics: {ethics['detail']}"}
    return {"status": status, "detail": next(part["detail"] for part in (ethics, release) if part["status"] != "PASS")}


_DEPOSIT_REASONS = {"file-changed": "{file} changed since the deposit",
                    "file-added": "{file} registered after the deposit",
                    "file-missing": "{file} missing since the deposit"}


def _deposit_gate(ctx: Context) -> dict[str, str]:
    """Every resource dataset's deposit, read through ``datasets_cli.deposit_state``."""
    dc = ctx.module("datasets_cli")
    entries = sorted(resource_datasets(dc, ctx.root), key=lambda item: str(item.get("slug")))
    if not entries:
        return {"status": "PENDING", "detail": _NO_RESOURCE}
    current, owed = [], []
    for entry in entries:
        slug, state = entry.get("slug"), dc.deposit_state(ctx.root, entry)
        record = state["deposit"] if isinstance(state.get("deposit"), dict) else {}
        if state["current"]:
            current.append(f"{slug} in {record.get('repository') or '?'} "
                           f"({record.get('scheme') or '?'} {record.get('identifier') or '?'})")
        elif not state["recorded"]:
            owed.append((False, f"{slug}: no deposit recorded yet (datasets_cli.py deposit --by <name>)"))
        elif state["stale"]:
            reasons = "; ".join(_DEPOSIT_REASONS.get(item.get("reason"), "{file}").format(file=item.get("file"))
                                for item in state["stale"])
            owed.append((True, f"{slug}: the deposit is stale ({reasons}): deposit the new version and record it "
                               "again (datasets_cli.py deposit)"))
        else:
            owed.append((True, f"{slug}: the deposit record is malformed: record it again (datasets_cli.py deposit)"))
    if not owed:
        return {"status": "PASS", "detail": f"{len(current)} dataset(s) deposited and current: {'; '.join(current)}"}
    started = bool(current) or any(recorded for recorded, _ in owed)
    return {"status": "ACTIVE" if started else "PENDING", "detail": owed[0][1]}


# ----- the experiment or intervention (experiment-intervention)

TRIAL_KIND = "experiment-intervention"
HUMAN_TRIAL, FIELD_EXPERIMENT = "human-trial", "field-experiment"
_NO_VARIANT = "No variant agreed yet, treated as a trial with people (the stricter case): {detail}"


def trial_variant(root: Path) -> tuple[str, bool]:
    """(variant, assumed) of an experiment-intervention workspace: the variant
    the operator agreed (``human-trial`` or ``field-experiment``), else
    ``human-trial`` with ``assumed`` true: no type agreed, another line's type,
    a stale agreement or the type agreed without its variant get the stricter
    rules (a prospective registration and a signed-off flow), and the gates
    say so."""
    agreed = agreed_type(root)
    if agreed["line"] == TRIAL_KIND and not agreed["stale"] and agreed["variant"] in (HUMAN_TRIAL, FIELD_EXPERIMENT):
        return agreed["variant"], False
    return HUMAN_TRIAL, True


def _assumed(gate: dict[str, str], assumed: bool) -> dict[str, str]:
    return {**gate, "detail": _NO_VARIANT.format(detail=gate["detail"])} if assumed else gate


def _trial_registration_gate(ctx: Context) -> dict[str, str]:
    """G-REGISTRATION of the line (decision J3). A field experiment keeps the
    shared reading (any current registration, or not applicable). A trial with
    people needs a current registration made on or before its first enrolment
    (ICMJE): retrospective, unknown (no first-enrolment date) and not-applicable
    records fail with their reason."""
    variant, assumed = trial_variant(ctx.root)
    shared = _record_gate(ctx, "registration")
    if variant == FIELD_EXPERIMENT:
        return shared
    entry = ctx.module("records").gate_state(ctx.root, "registration")
    if entry is None or entry.get("state") == "corrupt" or not entry.get("current"):
        return _assumed(shared, assumed)
    by = entry.get("by") or "?"
    if entry.get("status") == "not-applicable":
        out = {"status": "FAIL", "detail": (f"A trial with people must be registered on or before its first "
                                            f"enrolment (ICMJE): a not-applicable record does not count (recorded "
                                            f"by {by}: {entry.get('reason') or ''})")}
        return _assumed(out, assumed)
    registry, ident, date = entry.get("registry"), entry.get("id"), entry.get("date")
    first = entry.get("first_enrolment")
    if entry.get("retrospective") is True:
        out = {"status": "FAIL", "detail": (f"Retrospective registration: {registry} ({ident}) on {date}, after the "
                                            f"first enrolment on {first}; ICMJE requires a trial with people to be "
                                            f"registered on or before its first enrolment, so the paper states it as "
                                            f"retrospective (recorded by {by})")}
    elif entry.get("retrospective") is None:
        out = {"status": "FAIL", "detail": (f"Registered in {registry} ({ident}) on {date} with no first-enrolment "
                                            f"date recorded: whether it was prospective cannot be checked, and ICMJE "
                                            f"requires a trial with people to be registered on or before its first "
                                            f"enrolment; record it again with --first-enrolment (recorded by {by})")}
    else:
        out = {"status": "PASS", "detail": (f"Registered in {registry} ({ident}) on {date}, on or before the first "
                                            f"enrolment on {first} (prospective); recorded by {by}")}
    return _assumed(out, assumed)


_OPTIONAL_FLOW = "Optional for a field experiment (not blocking): {detail}"
_NO_FLOW_KEPT = "no participant flow kept; the experimental units are reported in a table"


def _trial_flow_gate(ctx: Context) -> dict[str, str]:
    """G-FLOW of the line (decision J4): the shared sign-off, required for a
    trial with people; for a field experiment it always passes (it never
    blocks the writing) and says how the flow stands, if one is kept."""
    variant, assumed = trial_variant(ctx.root)
    shared = _flow_gate(ctx)
    if variant != FIELD_EXPERIMENT:
        return _assumed(shared, assumed)
    if shared["status"] == "PASS":
        return shared
    kept = (ctx.root / "study" / "flow.json").is_file()
    return {"status": "PASS", "detail": _OPTIONAL_FLOW.format(detail=shared["detail"] if kept else _NO_FLOW_KEPT)}


_ALLOCATION_REASONS = {
    "file-changed": "the allocation list changed since it was recorded",
    "file-missing": "the allocation list is missing",
    "file-unreadable": "the allocation list is unreadable",
    "file-outside": "the recorded path of the allocation list leaves the workspace and is not read",
    "protocol-amended": "the protocol was amended since it was recorded",
    "protocol-changed": "the protocol changed after its approval and is not current",
}


def _allocation_gate(ctx: Context) -> dict[str, str]:
    """G-ALLOCATION: ``records.allocation_state`` is current. It reads the
    record (method, concealment, row count, hashes), never the list."""
    state = ctx.module("records").allocation_state(ctx.root)
    if state["state"] == "absent":
        return {"status": "PENDING", "detail": "No allocation record yet (study_cli.py allocation record)"}
    if state["state"] == "corrupt":
        return {"status": "FAIL", "detail": f"The allocation record is unreadable: {state['message']}"}
    if not state.get("current"):
        reasons = "; ".join(_ALLOCATION_REASONS.get(reason, reason) for reason in state.get("reasons") or ())
        return {"status": "ACTIVE", "detail": (f"Stale ({reasons}): the operator records the allocation again "
                                               "against the current list and protocol (study_cli.py allocation "
                                               "record)")}
    return {"status": "PASS", "detail": (f"Allocation recorded by {state.get('by') or '?'}: method "
                                         f"{state.get('method')}, {state.get('rows')} row(s); concealment: "
                                         f"{state.get('concealment')}")}


# ----- the measurement core (hardware and lab-simulation)


def _instrument_part(ctx: Context) -> dict[str, str]:
    """Every instrument the registered raw files use: recorded, calibrated and not
    past its due date today (the first half of G-CALIBRATION)."""
    core = ctx.module("measurement")
    instruments, data = core.instruments_state(ctx.root), core.data_state(ctx.root)
    if instruments["state"] == "corrupt":
        return {"status": "FAIL", "detail": f"The instrument records are unreadable: {instruments['message']}"}
    if data["state"] == "corrupt":
        return {"status": "FAIL", "detail": f"The raw data registrations are unreadable: {data['message']}"}
    if instruments["state"] == "absent":
        return {"status": "PENDING", "detail": "No instrument recorded yet (measure_cli.py instrument add)"}
    if data["state"] == "absent":
        return {"status": "PENDING", "detail": "No raw data file registered yet (measure_cli.py data register)"}
    rows = {row["id"]: row for row in instruments["instruments"]}
    used = sorted({str(item.get("instrument")) for item in data["files"]})
    for ident in used:
        row = rows.get(ident)
        if row is None:
            return {"status": "ACTIVE", "detail": f"Instrument {ident} of the registered data is not recorded "
                                                  "(measure_cli.py instrument add)"}
        if row["calibration"] == "past-due":
            return {"status": "ACTIVE", "detail": (f"Instrument {ident} is past its calibration due date "
                                                   f"({row.get('due')}) on {instruments['on']}: recalibrate it "
                                                   "(measure_cli.py instrument add --reason)")}
        if row["calibration"] != "current":
            return {"status": "ACTIVE", "detail": f"Instrument {ident} has no readable calibration due date"}
    return {"status": "PASS", "detail": (f"{len(used)} instrument(s) used by the registered data, calibrated and "
                                         f"not past due on {instruments['on']}")}


def _budget_part(ctx: Context) -> dict[str, str]:
    """Every registered quantity with a current uncertainty budget and no stale
    budget (the second half of G-CALIBRATION)."""
    core = ctx.module("measurement")
    data, budgets = core.data_state(ctx.root), core.budget_state(ctx.root)
    if data["state"] == "corrupt":
        return {"status": "FAIL", "detail": f"The raw data registrations are unreadable: {data['message']}"}
    if budgets["state"] == "corrupt":
        return {"status": "FAIL", "detail": f"The uncertainty budgets are unreadable: {budgets['message']}"}
    rows = budgets["budgets"]
    broken = next((row for row in rows if row["state"] == "corrupt"), None)
    if broken is not None:
        return {"status": "FAIL", "detail": f"An uncertainty budget is unreadable: {broken['message']}"}
    stale = next((row for row in rows if row["state"] == "stale"), None)
    if stale is not None:
        return {"status": "ACTIVE", "detail": (f"The uncertainty budget of {stale['quantity']} is stale "
                                               f"({', '.join(stale['reasons'])}): recompute it "
                                               "(measure_cli.py uncertainty compute)")}
    quantities = list(dict.fromkeys(str(item.get("quantity")) for item in data["files"]))
    if not quantities:
        return {"status": "PENDING", "detail": "No raw data file registered yet (measure_cli.py data register)"}
    budgeted = {row["quantity"] for row in rows if row["state"] == "current"}
    owed = [quantity for quantity in quantities if quantity not in budgeted]
    if owed:
        return {"status": "ACTIVE",
                "detail": f"No current uncertainty budget for {owed[0]} (measure_cli.py uncertainty compute)"}
    return {"status": "PASS", "detail": (f"{len(rows)} uncertainty budget(s) current for {len(quantities)} "
                                         "registered quantity(ies)")}


def _calibration_gate(ctx: Context) -> dict[str, str]:
    instruments = _instrument_part(ctx)
    if instruments["status"] != "PASS":
        return instruments
    budgets = _budget_part(ctx)
    if budgets["status"] != "PASS":
        return {"status": "FAIL" if budgets["status"] == "FAIL" else "ACTIVE", "detail": budgets["detail"]}
    return {"status": "PASS", "detail": f"{instruments['detail']}; {budgets['detail']}"}


def _agreement_gate(ctx: Context) -> dict[str, str]:
    state = ctx.module("measurement").agreement_state(ctx.root)
    if state["state"] == "corrupt":
        return {"status": "FAIL", "detail": f"The agreement records are unreadable: {state['message']}"}
    if state["state"] == "absent":
        return {"status": "PENDING", "detail": "No agreement analysis yet (measure_cli.py agreement compute)"}

    def pair(analysis: dict) -> tuple[str, str]:
        return (str((analysis.get("device") or {}).get("path")), str((analysis.get("reference") or {}).get("path")))

    current = [analysis for analysis in state["analyses"] if analysis["state"] == "current"]
    if current:
        device, reference = pair(current[-1])
        return {"status": "PASS", "detail": (f"Agreement of {device} with {reference} current "
                                             f"({current[-1].get('n')} pairs)")}
    stale = state["analyses"][-1]
    device, reference = pair(stale)
    return {"status": "ACTIVE", "detail": (f"The agreement of {device} with {reference} is stale "
                                           f"({', '.join(stale['reasons'])}): recompute it "
                                           "(measure_cli.py agreement compute)")}


def _data_files(ctx: Context) -> dict[str, Any]:
    """The registered raw files: ``status``, ``detail`` and their count ``n``."""
    data = ctx.module("measurement").data_state(ctx.root)
    if data["state"] == "corrupt":
        return {"status": "ACTIVE", "detail": f"The raw data registrations are unreadable: {data['message']}", "n": 0}
    files = data["files"]
    if not files:
        return {"status": "PENDING", "detail": "No raw data file registered yet (measure_cli.py data register)",
                "n": 0}
    moved = next((item for item in files if item["state"] != "current"), None)
    if moved is not None:
        detail = (f"{moved['path']} changed since its registration: the operator registers it again "
                  "(measure_cli.py data register --reason)" if moved["state"] == "changed" else
                  f"{moved['path']} is registered but no longer exists")
        return {"status": "ACTIVE", "n": len(files), "detail": detail}
    return {"status": "PASS", "n": len(files),
            "detail": f"{len(files)} registered raw data file(s), unchanged since their registration"}


def _paper_declarations() -> Any:
    """paper-writing's ``paper_declarations`` (the dashboard's copy), imported the
    way ``manuscript_graph`` imports it."""
    scripts = DASHBOARD_SKILLS / "paper-writing" / "scripts"
    for path in (scripts, DASHBOARD_SKILLS / "_core" / "implementation"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import paper_declarations  # noqa: PLC0415

    return paper_declarations


def _repository_url(ctx: Context) -> dict[str, str]:
    """The ``repository-url`` declaration, read from ``paper/main.tex`` (never written)."""
    if not (ctx.root / "paper" / "main.tex").is_file():
        return {"status": "PENDING", "detail": ("No repository-url declaration yet: it is recorded with paper_cli.py "
                                                "declare once paper/main.tex exists")}
    try:
        value = _paper_declarations().read_declaration(ctx.root / "paper", "repository-url")
    except Exception as exc:  # a hand-edited or unreadable region: shown, never repaired
        code = getattr(exc, "code", None)
        return {"status": "ACTIVE", "detail": (f"The declarations of paper/main.tex are unreadable "
                                               f"({code if isinstance(code, str) else type(exc).__name__})")}
    if not value:
        return {"status": "PENDING", "detail": ("No repository-url declaration yet (paper_cli.py declare "
                                                "--declaration repository-url)")}
    return {"status": "PASS", "detail": f"Repository declared (repository-url): {value}"}


def with_people(ctx: Context) -> bool:
    """Whether the operator declared a validation with people: an ethics or a
    registration record that is not "not applicable", or a participant flow in
    ``study/flow.json``. A bench-only validation records both as not applicable."""
    if (ctx.root / "study" / "flow.json").is_file():
        return True
    records = ctx.module("records")
    if records is None:
        return False
    for gate in ("ethics", "registration"):
        entry = records.gate_state(ctx.root, gate)
        if entry and entry.get("state") == "recorded" and entry.get("status") != "not-applicable":
            return True
    return False


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
    Gate(SPEC_GATE, "Specifications Signature Gate",
         "The operator signed the hardware's requirements and specifications by approving a managed revision of "
         "protocol/study-protocol-<slug>-vNN.md (study_cli.py protocol approve --by <name>), pinned by its sha256 in "
         "study/protocol.lock.json; it stays current while that revision is unchanged and no newer one exists, and a "
         "change is an amendment with its reason. The specifications table reports the hardware against these "
         "signed values.", "specifications", _protocol_gate, "records"),
    Gate(CALIBRATION_GATE, "Calibration & Uncertainty Gate",
         "Every instrument the registered raw data files use is recorded from its calibration certificate and is "
         "not past its calibration due date on today's date (measure_cli.py instrument add --by <name>), and every "
         "registered quantity has a current uncertainty budget in study/uncertainty/ (measure_cli.py uncertainty "
         "compute), bound to the files and the instrument record it used. Read from the records; the board never "
         "records it.", "calibration", _calibration_gate, "measurement"),
    Gate(AGREEMENT_GATE, "Agreement Gate",
         "An agreement analysis of the device against the reference device (Bland-Altman bias and limits of "
         "agreement, ICC(2,1)) in study/agreement.json is current: computed from registered raw data files that "
         "have not changed since (measure_cli.py agreement compute). The writing starts after it.",
         "agreement", _agreement_gate, "measurement"),
    Gate(DEPOSIT_GATE, "Deposit Record Gate",
         "The operator deposited every dataset of the resource in a repository and recorded the persistent "
         "identifier and the licence (datasets_cli.py deposit --by <name>), bound to the sha256 of every registered "
         "file; a file changed, added or missing since makes it stale until the new version is deposited and "
         "recorded again. Read from the registry; the board never records it. The writing starts after it.",
         "deposit", _deposit_gate, "datasets_cli"),
    Gate(ALLOCATION_GATE, "Allocation Record Gate",
         "The operator generated and concealed the allocation sequence with their own tool or service and recorded it "
         "(study_cli.py allocation record --by <name>): the method, the concealment and the list's sha256 and row "
         "count, bound to the current protocol lock. It stays current while the list is unchanged and the protocol "
         "is not amended; the board reads the record, never the list. The pre-specified analyses wait for it.",
         "allocation", _allocation_gate, "records"),
)}

#: The data-resource line's G-ETHICS: the ethics record plus the right to release the data.
RESOURCE_ETHICS = Gate(
    ETHICS_GATE, "Ethics, Consent & Licence Gate",
    "The operator recorded the ethics approval and the consent route, or why none applies (study_cli.py ethics "
    "record --by <name>), bound to the current protocol lock, and the right to release every dataset of the "
    "resource: the own-data statement (datasets_cli.py own --by <name>) or a source licence decision that is "
    "allowed (datasets_cli.py license); an overridden or refused licence does not count, since a deposit "
    "redistributes the data.", "ethics_licence", _ethics_licence_gate, "records")

#: The experiment-intervention line's G-REGISTRATION: prospective for a trial with people (J3).
TRIAL_REGISTRATION = Gate(
    REGISTRATION_GATE, "Prospective Registration Gate",
    "The operator recorded the registration (registry, id, date, first enrolment) with study_cli.py registration "
    "record --by <name>, bound to the current protocol lock. A trial with people (human-trial, and any workspace "
    "with no variant agreed, the stricter case) passes only with a current registration made on or before its first "
    "enrolment, as ICMJE requires: a retrospective registration, one with no first-enrolment date and a "
    "not-applicable record fail, and the paper states a retrospective registration as such. A field experiment "
    "passes with any current registration record, or one recorded as not applicable.",
    "protocol_registration", _trial_registration_gate, "records")

#: The experiment-intervention line's G-FLOW: required for a trial with people, optional for a field experiment (J4).
TRIAL_FLOW = Gate(
    FLOW_GATE, "Participant Flow Sign-off Gate",
    "Required for a trial with people (human-trial, and any workspace with no variant agreed): the CONSORT 2025 "
    "participant flow counts in study/flow.json are valid, paper/Figures/participant-flow.svg is drawn from them and "
    "the operator signed them off (flow_cli.py signoff --by <name>); the writing starts after it. Optional for a "
    "field experiment, which may report its experimental units in a table: it never blocks the writing, and a flow "
    "that is kept is shown as it stands.",
    "flow_units", _trial_flow_gate, "flow_cli")


def gate_definition(table: "LineTable", gate_id: str) -> Gate:
    """The gate ``gate_id`` as ``table``'s line defines it: its own, else the shared one."""
    return table.gate_defs.get(gate_id) or GATES[gate_id]


# ----- the steps that read the gates and the records


def _protocol_step(ctx: Context, gate_id: str, awaiting: str, none: str, approval: str) -> dict[str, Any]:
    """A step whose gate is the study protocol's lock: G-STUDY-PROTOCOL, or G-SPEC for hardware."""
    gate = ctx.gates[gate_id]
    revisions = ctx.module("records").managed_revisions(ctx.root)
    if gate["status"] == "PENDING":
        status = "ACTIVE" if revisions else "PENDING"
        detail = f"{len(revisions)} {awaiting}" if revisions else none
    else:
        status = "PASS" if gate["status"] == "PASS" else "ACTIVE"
        detail = gate["detail"]
    return {"status": status, "detail": detail, "subfases": [
        ("Protocol revisions (protocol/study-protocol-*.md)", "PASS" if revisions else "PENDING",
         f"{len(revisions)} managed revision(s); latest {revisions[-1][1]}" if revisions
         else "No managed revision yet"),
        (approval, gate["status"], gate["detail"]),
    ]}


def _study_protocol(ctx: Context) -> dict[str, Any]:
    return _protocol_step(ctx, PROTOCOL_GATE, "protocol revision(s); awaiting the operator's approval (G-STUDY-PROTOCOL)",
                          "No study protocol revision yet (/study-protocol-deliberation)",
                          "Operator approval (G-STUDY-PROTOCOL)")


def _specifications(ctx: Context) -> dict[str, Any]:
    return _protocol_step(ctx, SPEC_GATE, "protocol revision(s); awaiting the operator's signature of the "
                                          "specifications (G-SPEC)",
                          "No specifications yet: the protocol holds them (/study-protocol-deliberation)",
                          "Specifications signed (G-SPEC, operator)")


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


# ----- the data-resource steps


def _ethics_licence(ctx: Context) -> dict[str, Any]:
    gate, ethics, release = ctx.gates[ETHICS_GATE], _record_gate(ctx, "ethics"), _release_part(ctx)
    status = "PASS" if gate["status"] == "PASS" else ("PENDING" if gate["status"] == "PENDING" else "ACTIVE")
    return {"status": status, "detail": gate["detail"], "subfases": [
        ("Ethics approval and consent (G-ETHICS, operator)", ethics["status"], ethics["detail"]),
        ("Right to release: own-data statement or allowed licence (G-ETHICS, operator)", release["status"],
         release["detail"]),
    ]}


def _curation(ctx: Context) -> dict[str, Any]:
    dc = ctx.module("datasets_cli")
    entries = sorted(resource_datasets(dc, ctx.root), key=lambda item: str(item.get("slug")))
    if not entries:
        return {"status": "PENDING", "detail": _NO_RESOURCE, "subfases": [
            ("Data files written by the operator", "PENDING", _NO_RESOURCE),
            ("Data dictionary (datasets/<slug>/dictionary.json)", "PENDING", _NO_RESOURCE)]}
    problems = []
    for entry in entries:
        slug = entry.get("slug")
        try:
            found = dc.read_dictionary(ctx.root, slug)
        except dc.Refusal as refusal:
            problems.append(f"{slug}: the data dictionary is invalid: {refusal.message}")
            continue
        if found is None:
            problems.append(f"{slug}: no data dictionary (datasets_cli.py dictionary init)")
    n, valid = len(entries), len(entries) - len(problems)
    files = sum(1 for entry in entries if entry.get("files"))
    status = "PASS" if not problems else "ACTIVE"
    detail = f"{valid} dataset(s) with a valid data dictionary" if not problems else problems[0]
    return {"status": status, "detail": detail, "subfases": [
        ("Data files written by the operator", _state(files, n),
         f"{files} of {n} dataset(s) with a registered data file; the assistant never writes or edits one"),
        ("Data dictionary (datasets/<slug>/dictionary.json)", status,
         f"{valid} of {n} dataset(s) with a valid data dictionary"),
    ]}


def _quality(ctx: Context) -> dict[str, Any]:
    gate = ctx.gates[DATA_GATE]
    owned = own_datasets(ctx.module("datasets_cli"), ctx.root)
    n = len(owned)
    clear = sum(1 for d in owned if d["pii_clear"])
    status = "PASS" if gate["status"] == "PASS" else ("ACTIVE" if owned else "PENDING")
    return {"status": status, "detail": gate["detail"], "subfases": [
        ("Quality check (G-DATA-QC)", gate["status"], gate["detail"]),
        ("De-identification of personal data", _state(clear, n),
         f"{clear} of {n} own dataset(s) with no personal data left to de-identify"),
    ]}


def _baselines(ctx: Context) -> dict[str, Any]:
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
    status = "PASS" if analyses and not stopped else ("ACTIVE" if entries else "PENDING")
    return {"status": status,
            "detail": f"{len(analyses)} analysis entries logged: {confirmatory} confirmatory, {exploratory} exploratory",
            "subfases": [
        ("Analysis log (analysis/log.jsonl)", "PASS" if analyses else "ACTIVE",
         f"{len(entries)} entries, hash chain intact"),
        ("Baselines labelled by the locked protocol", "PASS" if analyses else "PENDING",
         f"{confirmatory} confirmatory, {exploratory} exploratory; the label is computed, never chosen"),
        ("Interrupted or failed runs", "ACTIVE" if stopped or failed else "PASS",
         f"{len(stopped)} interrupted, {len(failed)} failed"),
    ]}


def _deposit(ctx: Context) -> dict[str, Any]:
    gate, repository = ctx.gates[DEPOSIT_GATE], _repository_url(ctx)
    status = "PASS" if gate["status"] == "PASS" else ("PENDING" if gate["status"] == "PENDING" else "ACTIVE")
    return {"status": status, "detail": gate["detail"], "subfases": [
        ("Deposit recorded and current (G-DEPOSIT, operator)", gate["status"], gate["detail"]),
        ("Repository declared (repository-url)", repository["status"], repository["detail"]),
    ]}


# ----- the experiment-intervention steps


def _gate_step(gate: dict[str, str]) -> str:
    """A step whose state is one gate's: PASS, PENDING, or ACTIVE (started, stale or failed)."""
    return gate["status"] if gate["status"] in ("PASS", "PENDING") else "ACTIVE"


def _protocol_registration(ctx: Context) -> dict[str, Any]:
    info = _study_protocol(ctx)
    registration = ctx.gates[REGISTRATION_GATE]
    info["subfases"].append(("Registration (G-REGISTRATION, operator)", registration["status"],
                             registration["detail"]))
    if info["status"] == "PASS":
        info["status"] = "PASS" if registration["status"] == "PASS" else "ACTIVE"
        info["detail"] = registration["detail"]
    return info


def _ethics_consent(ctx: Context) -> dict[str, Any]:
    gate = ctx.gates[ETHICS_GATE]
    return {"status": _gate_step(gate), "detail": gate["detail"], "subfases": [
        ("Ethics approval and consent route (G-ETHICS, operator)", gate["status"], gate["detail"]),
    ]}


def _allocation(ctx: Context) -> dict[str, Any]:
    gate, protocol = ctx.gates[ALLOCATION_GATE], ctx.gates[PROTOCOL_GATE]
    return {"status": _gate_step(gate), "detail": gate["detail"], "subfases": [
        ("Blocks, plots and sample size in the locked protocol (G-STUDY-PROTOCOL)", protocol["status"],
         protocol["detail"]),
        ("Allocation record (G-ALLOCATION, operator)", gate["status"], gate["detail"]),
    ]}


def _flow_units(ctx: Context) -> dict[str, Any]:
    """The participant flow step; for a field experiment it never holds the
    line: it passes with the optional gate's reading."""
    info = _participant_flow(ctx)
    if trial_variant(ctx.root)[0] == FIELD_EXPERIMENT and info["status"] != "PASS":
        info.update(status="PASS", detail=ctx.gates[FLOW_GATE]["detail"], progress=None)
    return info


# ----- the hardware and lab-simulation steps


def _design_files(ctx: Context) -> dict[str, Any]:
    repository = _repository_url(ctx)
    return {"status": repository["status"], "detail": repository["detail"], "subfases": [
        ("Editable design files and bill of materials (operator)", repository["status"],
         "Kept by the operator in an open repository with a DOI; the assistant never estimates a price or invents "
         "a part"),
        ("Repository declared (repository-url)", repository["status"], repository["detail"]),
    ]}


def _build(ctx: Context) -> dict[str, Any]:
    files = _data_files(ctx)
    built = files["n"] > 0
    status = "PASS" if built else "PENDING"
    detail = (f"{files['n']} raw measurement file(s) registered: the hardware is built and measuring" if built
              else "No record of the build yet: the first registered raw measurement file shows the hardware "
                   "measuring")
    return {"status": status, "detail": detail, "subfases": [
        ("Build steps, photographs and design decisions (operator)", status,
         "Kept by the operator for the build and operation instructions"),
        ("First raw measurement file registered (study/measurements.json)", status, detail),
    ]}


def _calibration(ctx: Context) -> dict[str, Any]:
    gate = ctx.gates[CALIBRATION_GATE]
    instruments, budgets, files = _instrument_part(ctx), _budget_part(ctx), _data_files(ctx)
    started = instruments["status"] != "PENDING" or files["n"] > 0
    status = "PASS" if gate["status"] == "PASS" else ("ACTIVE" if started else "PENDING")
    return {"status": status, "detail": gate["detail"], "subfases": [
        ("Instruments calibrated, not past due (study/instruments.json)", instruments["status"], instruments["detail"]),
        ("Raw data files registered (study/measurements.json)", files["status"], files["detail"]),
        ("Uncertainty budgets (study/uncertainty/)", budgets["status"], budgets["detail"]),
        ("Calibration and uncertainty (G-CALIBRATION, operator records)", gate["status"], gate["detail"]),
    ]}


def _agreement(ctx: Context) -> dict[str, Any]:
    gate = ctx.gates[AGREEMENT_GATE]
    status = "PASS" if gate["status"] == "PASS" else ("PENDING" if gate["status"] == "PENDING" else "ACTIVE")
    return {"status": status, "detail": gate["detail"], "subfases": [
        ("Agreement with the reference device (G-AGREEMENT)", gate["status"], gate["detail"]),
    ]}


def _field_validation(ctx: Context) -> dict[str, Any]:
    ethics, registration = ctx.gates[ETHICS_GATE], ctx.gates[REGISTRATION_GATE]
    subfases = [("Ethics approval (G-ETHICS, operator)", ethics["status"], ethics["detail"]),
                ("Registration (G-REGISTRATION, operator)", registration["status"], registration["detail"])]
    if ctx.people:
        flow = ctx.gates[FLOW_GATE]
        subfases.append(("Participant flow sign-off (G-FLOW, operator)", flow["status"], flow["detail"]))
        passed = sum(1 for gate in (ethics, registration, flow) if gate["status"] == "PASS")
        return {"status": _state(passed, 3, True),
                "detail": f"Validation with people: {passed} of 3 operator records current (ethics, registration, "
                          "participant flow)", "subfases": subfases}
    passed = sum(1 for gate in (ethics, registration) if gate["status"] == "PASS")
    if passed == 2:
        detail = "Bench-only validation: ethics and registration recorded as not applicable"
    elif all(gate["status"] == "PENDING" for gate in (ethics, registration)):
        detail = ("No validation declared yet: record ethics and registration (as not applicable for a bench-only "
                  "validation)")
    else:
        detail = f"{passed} of 2 operator records current (ethics, registration)"
    started = any(gate["status"] != "PENDING" for gate in (ethics, registration))
    return {"status": _state(passed, 2, started), "detail": detail, "subfases": subfases}


def _open_files(ctx: Context) -> dict[str, Any]:
    files, repository = _data_files(ctx), _repository_url(ctx)
    return {"status": files["status"], "detail": files["detail"], "subfases": [
        ("Registered raw data files unchanged (study/measurements.json)", files["status"], files["detail"]),
        ("Repository declared (repository-url)", repository["status"], repository["detail"]),
    ]}


def _sample_model(ctx: Context) -> dict[str, Any]:
    revisions = ctx.module("records").managed_revisions(ctx.root)
    status = "PASS" if revisions else "PENDING"
    detail = (f"{len(revisions)} protocol revision(s) hold the sample matrix or the model; the operator approves "
              "one in the next step" if revisions else
              "No protocol revision yet: the sample matrix or the model is written into the protocol "
              "(/study-protocol-deliberation)")
    return {"status": status, "detail": detail, "subfases": [
        ("Sample matrix or model definition (operator)", status, detail),
    ]}


def _observables(ctx: Context) -> dict[str, Any]:
    files = _data_files(ctx)
    return {"status": files["status"], "detail": files["detail"], "subfases": [
        ("Raw data files registered (study/measurements.json)", files["status"], files["detail"]),
    ]}


def _known_values(ctx: Context) -> dict[str, Any]:
    instruments = _instrument_part(ctx)
    status = "ACTIVE" if instruments["status"] == "FAIL" else instruments["status"]
    return {"status": status, "detail": instruments["detail"], "subfases": [
        ("Instruments calibrated, not past due (study/instruments.json)", instruments["status"], instruments["detail"]),
    ]}


def _uncertainty(ctx: Context) -> dict[str, Any]:
    gate, budgets = ctx.gates[CALIBRATION_GATE], _budget_part(ctx)
    log_module = ctx.module("analysis_log")
    log = log_module.log_state(ctx.root)
    if log["state"] == "absent":
        entries, stopped, log_status, log_detail = [], [], "PENDING", "No analysis logged yet (analysis/log.jsonl)"
    elif log["state"] != "ok":
        entries, stopped = [], []
        log_status, log_detail = "ACTIVE", f"The analysis log is unreadable: {log['message']}"
    else:
        entries = log_module.read_log(ctx.root)
        stopped = log_module.interrupted(entries)
        analyses = log_module.analyses(entries)
        confirmatory = sum(1 for entry in analyses if entry.get("label") == "confirmatory")
        log_status = "ACTIVE" if stopped else "PASS"
        log_detail = (f"{len(analyses)} analysis entries logged: {confirmatory} confirmatory, "
                      f"{len(analyses) - confirmatory} exploratory")
    if gate["status"] == "PASS" and log_status != "ACTIVE":
        status, detail = "PASS", gate["detail"]
    else:
        started = budgets["status"] != "PENDING" or bool(entries)
        status = "ACTIVE" if started else "PENDING"
        detail = gate["detail"] if gate["status"] != "PASS" else log_detail
    return {"status": status, "detail": detail, "subfases": [
        ("Uncertainty budgets (study/uncertainty/)", budgets["status"], budgets["detail"]),
        ("Calibration and uncertainty (G-CALIBRATION, operator records)", gate["status"], gate["detail"]),
        ("Analysis log (analysis/log.jsonl)", log_status, log_detail),
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
    """(sub-step name, detail) of the reporting checklist the agreed type chooses
    (through its variant when it has variants)."""
    agreed = agreed_type(ctx.root)
    if not agreed["type"] and not _line_has_variants(ctx.table.kind):
        return ("Reporting checklist", "No paper type agreed yet (/paper-type): the type names the reporting "
                                       "checklist")
    if not agreed["type"] or (agreed["has_variants"] and not agreed["variant"]):
        return ("Reporting checklist", "No variant agreed yet (/paper-type): the variant chooses the reporting "
                                       "checklist")
    checklist = agreed["checklist"]
    if not checklist:
        return ("Reporting checklist", f"No checklist data yet for the {agreed['variant'] or agreed['type']} "
                                       "variant: the items are checked by hand")
    return _guideline_detail(ctx, checklist)


def _guideline_detail(ctx: Context, checklist: str) -> tuple[str, str]:
    """(sub-step name, detail) of guideline ``checklist``: its name and item count."""
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
    extras = [_guideline_detail(ctx, extra) for extra in ctx.table.extra_checklists]
    return {"status": status, "detail": detail, "subfases": [
        (name, "PENDING", checklist),
        *((extra_name, "PENDING", extra_detail) for extra_name, extra_detail in extras),
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
    # ----- hardware (src/papersmith/templates/paper-flow-hardware.md.tpl)
    Step("plausibility_hardware", "Plausibility and paper type", "Plausibility & Paper Type",
         "The state of the art and the comparable devices scouted around the idea, the plausibility report accepted by the operator, and the hardware paper type agreed with /paper-type; the type names the hardwarex checklist and every uncertainty is checked against gum-reporting.",
         ("read", "write", "http"), ("sota-pool/candidates.json", ".papersmith/paper_type.json"), "G-PAPER-TYPE", {
             "skills": ["plausibility", "paper-type"],
             "agent": "plausibility, paper-type-advisor & operator",
             "actions": [
                 _prompt("/plausibility", "Explore the plausibility of the idea", [
                     "Write the idea in at least two sentences: what the hardware measures or does, for whom, and the reference it is validated against.",
                     "The agent scouts about 25 SOTA references and comparable devices by their abstracts and grades the claims with verbatim quotes.",
                     "Nothing moves on until you accept the report.",
                 ], "E.g.: A low-cost load cell for field force measurement, validated against a laboratory dynamometer …",
                     min_sentences=2),
                 _prompt("/paper-type", "Agree the paper type", [
                     "The agent scores the idea against the paper types and discusses its suggestion with you.",
                     "The hardware type has no variants: its reporting checklist is hardwarex (the HardwareX article template).",
                     "Every uncertainty is also checked against gum-reporting (GUM clause 7).",
                 ], "E.g.: discuss whether this is a hardware paper or a measurement-instrument study.", optional=True),
                 _redirect("View the paper types", "papertype", "Every paper type with its score, guideline and variants."),
             ],
         }, (("Candidate pool", "sota-pool/candidates.json"), ("Plausibility acceptance", ".papersmith/plausibility.json"),
             ("Agreed paper type", ".papersmith/paper_type.json")), _plausibility_type),
    Step("specifications", "Requirements and specifications", "Requirements & Specifications (G-SPEC)",
         "The hardware's protocol as managed revisions: what it must measure or do and for whom, the primary performance outcome with its acceptance criterion, the secondary specifications, the validation design, the operating conditions, the units, replicates and paired readings, and the analysis plan. The operator signs the specifications by approving a revision; a later change is an amendment with its reason.",
         ("read", "write"), ("protocol/study-protocol-<slug>-vNN.md", "study/protocol.lock.json"), SPEC_GATE, {
             "skills": ["study-protocol-deliberation"],
             "agent": "study-protocol-deliberation & operator",
             "actions": [
                 _prompt("/study-protocol-deliberation", "Deliberate the specifications with the agent", [
                     "The agent drafts the protocol with you: requirements, the primary performance outcome and its acceptance criterion, secondary specifications, validation design, units and replicates, and the analysis plan.",
                     "The acceptance criterion and the primary outcome are yours; the agent never invents a specification or a measured value.",
                     "Each accepted change is published as a new managed revision under protocol/.",
                 ], "E.g.: draft the specifications of the load cell: range, resolution and the limits of agreement allowed.",
                     optional=True),
                 _command(f"{STUDY_CLI} protocol status --root .", "Protocol lock status",
                          "Whether the approved revision is current, changed or absent."),
                 _command(f"{STUDY_CLI} protocol approve --root . --by {_OPERATOR}",
                          "Sign the specifications (operator, G-SPEC)",
                          "Only the operator signs; the approval pins the revision's sha256."),
                 _command(f'{STUDY_CLI} protocol amend --root . --by {_OPERATOR} --reason "<why>"',
                          "Record an amendment", "A change after the approval, with its reason; the methods report it."),
             ],
         }, (("Protocol revisions", "protocol/study-protocol-*.md"),
             ("Specifications signature (G-SPEC)", "study/protocol.lock.json")), _specifications, ("records",)),
    Step("design_files", "Design files and bill of materials", "Design Files & Bill of Materials",
         "The editable design files (CAD, schematic and layout projects, firmware and software sources) and the bill of materials with its purchase records, kept by the operator in an open repository with a DOI and recorded as the repository-url declaration. The assistant never estimates a price or invents a part.",
         ("read", "write"), ("paper/main.tex (repository-url)",), "G-DESIGN", {
             "skills": ["hardware", "paper-writing"],
             "agent": "hardware & operator",
             "actions": [
                 _prompt("/hardware", "Ask where the hardware stands", [
                     "The agent reads the study, measurement and checklist records and reports each stage with its state.",
                     "It names the first stage that is not done and the command that does it.",
                 ], "E.g.: status", optional=True),
                 _command(f'{PAPER_CLI} declare --declaration repository-url --value "<DOI or URL>"',
                          "Declare the repository (operator)",
                          "The DOI or URL of the open repository that holds the design files and the bill of materials."),
             ],
         }, (("Declarations (repository-url)", "paper/main.tex"),), _design_files),
    Step("build", "Build", "Build",
         "The operator builds the hardware and keeps the build steps, the photographs and the design decisions the build instructions will report; the first registered raw measurement file shows it measuring.",
         ("read",), ("study/measurements.json",), "G-BUILD", {
             "skills": ["hardware"],
             "agent": "operator",
             "actions": [
                 _prompt("/hardware", "Ask where the hardware stands", [
                     "The agent reads the study, measurement and checklist records and reports each stage with its state.",
                     "It names the first stage that is not done and the command that does it.",
                 ], "E.g.: status", optional=True),
                 _command(f"{MEASURE_CLI} data status --root .", "Registered raw data files",
                          "Each registered file with its sha256, current or changed."),
             ],
         }, (("Raw data registrations", "study/measurements.json"),), _build, ("measurement",)),
    Step("calibration", "Calibration and uncertainty", "Calibration & Uncertainty (G-CALIBRATION)",
         "Every reference and test instrument recorded from its calibration certificate, each raw measurement file the operator produced registered by its sha256, and an uncertainty budget per quantity computed from those files and instruments (type A from the replicates, type B from the instrument records, expanded with its coverage factor). A past-due instrument needs the operator's override.",
         ("read", "write", "bash"), ("study/instruments.json", "study/measurements.json", "study/uncertainty/<quantity>.json"),
         CALIBRATION_GATE, {
             "skills": ["hardware"],
             "agent": "measurement core & operator",
             "actions": [
                 _command(f'{MEASURE_CLI} instrument add --root . --id <id> --model "<model>" --serial "<serial>" '
                          f'--resolution "<value unit>" --calibration-certificate "<certificate>" --calibrated <YYYY-MM-DD> '
                          f'--due <YYYY-MM-DD> --by {_OPERATOR}',
                          "Record an instrument (operator)", "From its calibration certificate; a new calibration is a new entry with --reason."),
                 _command(f"{MEASURE_CLI} data register --root . --file <data.csv> --quantity <name> --unit <unit> "
                          f"--instrument <id> --by {_OPERATOR}",
                          "Register a raw data file (operator)", "Bound by its sha256; the core never writes into it."),
                 _command(f"{MEASURE_CLI} uncertainty compute --root . --quantity <name>", "Compute an uncertainty budget",
                          "The GUM budget of the quantity into study/uncertainty/<quantity>.json."),
                 _command(f'{MEASURE_CLI} uncertainty compute --root . --quantity <name> --allow-past-due --by {_OPERATOR} '
                          '--reason "<why the readings still hold>"',
                          "Override a past-due calibration (operator)", "Your decision, with its reason; the budget records it."),
                 _command(f"{MEASURE_CLI} status --root .", "Measurement records status",
                          "Instruments, data files, budgets and agreement in one object, with every warning."),
             ],
         }, (("Instruments", "study/instruments.json"), ("Raw data registrations", "study/measurements.json"),
             ("Uncertainty budgets (G-CALIBRATION)", "study/uncertainty/*.json")), _calibration, ("measurement",)),
    Step("agreement", "Agreement with a reference device", "Agreement with a Reference Device (G-AGREEMENT)",
         "The device's and the reference device's paired readings, each registered first, give the Bland-Altman bias, the limits of agreement and ICC(2,1); the analysis is stale when either file changes.",
         ("read", "bash"), ("study/agreement.json",), AGREEMENT_GATE, {
             "skills": ["hardware"],
             "agent": "measurement core & operator",
             "actions": [
                 _requires(_command(f"{MEASURE_CLI} agreement compute --root . --device-file <device.csv> "
                                    "--reference-file <reference.csv> --pair-column <column>",
                                    "Compute the agreement", "Bland-Altman and ICC(2,1) from the two registered files."),
                           CALIBRATION_GATE),
                 _command(f"{MEASURE_CLI} agreement status --root .", "Agreement status",
                          "Each analysis with its bias, limits and ICC, current or stale."),
             ],
         }, (("Agreement analyses (G-AGREEMENT)", "study/agreement.json"),), _agreement, ("measurement",)),
    Step("field_validation", "Field or user validation", "Field or User Validation",
         "When people take part (users in a field trial, a usability study, measurements on participants), the operator records the ethics approval and the registration, and the participant flow is signed off; a bench-only validation records both as not applicable.",
         ("read", "write"), ("study/ethics.json", "study/registration.json", "study/flow.json"), "G-VALIDATION", {
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
                 _command(f"{FLOW_CLI} template strobe --root . --write", "Write the empty participant flow",
                          "study/flow.json with no counts; you enter every count."),
                 _command(f"{FLOW_CLI} signoff --root . --by {_OPERATOR}", "Sign the flow off (operator, G-FLOW)",
                          "Refused on invalid counts or a missing or stale figure."),
             ],
         }, (("Ethics record (G-ETHICS)", "study/ethics.json"), ("Registration record (G-REGISTRATION)", "study/registration.json"),
             ("Participant flow counts", "study/flow.json")), _field_validation, ("records",)),
    Step("open_files", "Open design files and data", "Open Design Files & Data",
         "Before writing, the repository holds the final design files, the firmware, the bill of materials and the raw measurement files registered in study/measurements.json, under the open licenses the specifications table states.",
         ("read",), ("study/measurements.json", "paper/main.tex (repository-url)"), "G-OPEN", {
             "skills": ["hardware", "paper-writing"],
             "agent": "operator",
             "actions": [
                 _command(f"{MEASURE_CLI} data status --root .", "Registered raw data files",
                          "Each registered file with its sha256, current or changed."),
                 _command(f'{PAPER_CLI} declare --declaration repository-url --value "<DOI or URL>"',
                          "Declare the repository (operator)",
                          "The DOI or URL of the open repository that holds the design files and the bill of materials."),
             ],
         }, (("Raw data registrations", "study/measurements.json"), ("Declarations (repository-url)", "paper/main.tex")),
         _open_files, ("measurement",)),
    Step("reporting_hardware", "Reporting check and audit", "Reporting Check, Final Judge & Audit",
         "The hardwarex checklist the type names and the gum-reporting checklist (item by item: satisfied, missing or needs judgment), the paper checks of paper_cli.py verify, the measurement-science final judge and the cross-cutting audit; audits report, they never repair.",
         ("read", "bash"), (".papersmith/audit.json",), "G-AUDIT", {
             "skills": ["skill-audit"],
             "agent": "checklist engine, skill-audit & smith audit",
             "actions": [
                 _command(f"{CHECKLIST_CLI} check --guideline hardwarex --root .", "HardwareX checklist",
                          "The HardwareX article template item by item: satisfied, missing or needs judgment."),
                 _command(f"{CHECKLIST_CLI} check --guideline gum-reporting --root .", "GUM uncertainty reporting checklist",
                          "GUM clause 7 item by item: satisfied, missing or needs judgment."),
                 *copy.deepcopy(phase_actions.ACTIONS["audit"]["actions"]),
             ],
         }, phase_actions.EVIDENCE["audit"], _reporting, ("checklists",)),
    # ----- lab-simulation (src/papersmith/templates/paper-flow-lab-simulation.md.tpl)
    Step("plausibility_lab", "Plausibility and paper type", "Plausibility & Paper Type",
         "The state of the art scouted around the idea, the plausibility report accepted by the operator, and the lab-simulation paper type and variant agreed with /paper-type: materials or modelling-simulation, both reported on gum-reporting.",
         ("read", "write", "http"), ("sota-pool/candidates.json", ".papersmith/paper_type.json"), "G-PAPER-TYPE", {
             "skills": ["plausibility", "paper-type"],
             "agent": "plausibility, paper-type-advisor & operator",
             "actions": [
                 _prompt("/plausibility", "Explore the plausibility of the idea", [
                     "Write the idea in at least two sentences: what the study makes, measures or simulates, and the observable it reports.",
                     "The agent scouts about 25 SOTA references by their abstracts and grades the claims with verbatim quotes.",
                     "Nothing moves on until you accept the report.",
                 ], "E.g.: Annealing temperature controls the grain size of sputtered copper films. We deposit and characterize …",
                     min_sentences=2),
                 _prompt("/paper-type", "Agree the paper type and its variant", [
                     "The agent scores the idea against the paper types and discusses its suggestion with you.",
                     "You agree the type and the variant: materials (synthesis, deposition or processing) or modelling-simulation (an analytical or numerical model).",
                     "Both variants report on the gum-reporting checklist (GUM clause 7).",
                 ], "E.g.: discuss whether this is a materials or a modelling-simulation study.", optional=True),
                 _redirect("View the paper types", "papertype", "Every paper type with its score, guideline and variants."),
             ],
         }, (("Candidate pool", "sota-pool/candidates.json"), ("Plausibility acceptance", ".papersmith/plausibility.json"),
             ("Agreed paper type", ".papersmith/paper_type.json")), _plausibility_type),
    Step("sample_model", "Sample matrix or model definition", "Sample Matrix or Model Definition",
         "What the study varies and holds fixed, decided by the operator: the samples, compositions, process conditions and characterization techniques (materials), or the model, its solver, its parameters and their sources and the convergence criteria (modelling-simulation), written into the protocol.",
         ("read", "write"), ("protocol/study-protocol-<slug>-vNN.md",), "G-DESIGN", {
             "skills": ["study-protocol-deliberation"],
             "agent": "study-protocol-deliberation & operator",
             "actions": [
                 _prompt("/study-protocol-deliberation", "Write the sample matrix or the model into the protocol", [
                     "The agent drafts the design with you: the sample matrix or the model, its parameters and their sources.",
                     "The choice is yours; the agent never chooses a parameter grid or a sample for you.",
                     "Each accepted change is published as a new managed revision under protocol/.",
                 ], "E.g.: three annealing temperatures, five films each, measured by XRD and four-point probe.",
                     optional=True),
             ],
         }, (("Protocol revisions", "protocol/study-protocol-*.md"),), _sample_model, ("records",)),
    Step("lab_protocol", "Synthesis or simulation protocol", "Synthesis or Simulation Protocol (G-STUDY-PROTOCOL)",
         "The protocol as managed revisions: the research question, exactly one primary observable, the secondary observables, the design, the replicates per condition or the parameter grid with its justification and the analysis plan. The operator approves a revision; a later change is an amendment with its reason. Samples from people or animals need the ethics record.",
         ("read", "write"), ("protocol/study-protocol-<slug>-vNN.md", "study/protocol.lock.json"), PROTOCOL_GATE, {
             "skills": ["study-protocol-deliberation"],
             "agent": "study-protocol-deliberation & operator",
             "actions": [
                 _prompt("/study-protocol-deliberation", "Deliberate the protocol with the agent", [
                     "The agent drafts the protocol with you as labelled fields: question, one primary observable, secondary observables, design, replicates or parameter grid, and analysis plan.",
                     "The choice of the primary observable is yours; the agent never invents data or a sample size from data it has not seen.",
                     "Each accepted change is published as a new managed revision under protocol/.",
                 ], "E.g.: draft the first protocol of the annealing study.", optional=True),
                 _command(f"{STUDY_CLI} protocol status --root .", "Protocol lock status",
                          "Whether the approved revision is current, changed or absent."),
                 _command(f"{STUDY_CLI} protocol approve --root . --by {_OPERATOR}",
                          "Approve the protocol (operator, G-STUDY-PROTOCOL)",
                          "Only the operator approves; the approval pins the revision's sha256."),
                 _command(f'{STUDY_CLI} protocol amend --root . --by {_OPERATOR} --reason "<why>"',
                          "Record an amendment", "A change after the approval, with its reason; the methods report it."),
                 _command(f'{STUDY_CLI} ethics record --root . --by {_OPERATOR} --committee "<committee>" '
                          f'--code "<approval code>" --date <YYYY-MM-DD> --consent "<consent route>"',
                          "Record the ethics approval (operator, G-ETHICS)",
                          "The committee, the approval code, its date and the consent route."),
             ],
         }, (("Protocol revisions", "protocol/study-protocol-*.md"),
             ("Protocol approval (G-STUDY-PROTOCOL)", "study/protocol.lock.json")), _study_protocol, ("records",)),
    Step("observables", "Characterization or observables", "Characterization or Observables",
         "The operator measures the samples or runs the model and registers each raw data file by its sha256, with its quantity, unit, instrument, replicate column and conditions; the core never writes into a registered file.",
         ("read", "write"), ("study/measurements.json",), "G-DATA", {
             "skills": ["lab-simulation"],
             "agent": "measurement core & operator",
             "actions": [
                 _command(f'{MEASURE_CLI} instrument add --root . --id <id> --model "<model>" --serial "<serial>" '
                          f'--resolution "<value unit>" --calibration-certificate "<certificate>" --calibrated <YYYY-MM-DD> '
                          f'--due <YYYY-MM-DD> --by {_OPERATOR}',
                          "Record an instrument (operator)", "From its calibration certificate; a new calibration is a new entry with --reason."),
                 _command(f"{MEASURE_CLI} data register --root . --file <data.csv> --quantity <name> --unit <unit> "
                          f"--instrument <id> --replicate-column <column> --condition <key=value> --by {_OPERATOR}",
                          "Register a raw data file with its conditions (operator)",
                          "Bound by its sha256, one --condition per condition it was taken under."),
                 _command(f"{MEASURE_CLI} data status --root .", "Registered raw data files",
                          "Each registered file with its sha256, current or changed."),
             ],
         }, (("Raw data registrations", "study/measurements.json"),), _observables, ("measurement",)),
    Step("known_values", "Calibration against known values", "Calibration against Known Values (G-CALIBRATION)",
         "Every instrument recorded from its calibration certificate and current on today's date; the readings of a reference material or a standard sample are registered like any data file and compared with the known value, and a simulation reproduces an analytical solution or a benchmark case first.",
         ("read", "write"), ("study/instruments.json",), CALIBRATION_GATE, {
             "skills": ["lab-simulation"],
             "agent": "measurement core & operator",
             "actions": [
                 _command(f'{MEASURE_CLI} instrument add --root . --id <id> --model "<model>" --serial "<serial>" '
                          f'--resolution "<value unit>" --calibration-certificate "<certificate>" --calibrated <YYYY-MM-DD> '
                          f'--due <YYYY-MM-DD> --by {_OPERATOR}',
                          "Record an instrument (operator)", "From its calibration certificate; a new calibration is a new entry with --reason."),
                 _command(f"{MEASURE_CLI} data register --root . --file <reference.csv> --quantity <name> --unit <unit> "
                          f"--instrument <id> --condition reference=<material> --by {_OPERATOR}",
                          "Register the readings of a reference material (operator)",
                          "Compared with the known value of the material or the standard sample."),
                 _command(f"{MEASURE_CLI} instrument status --root .", "Instrument calibration status",
                          "Each instrument with its calibration current or past due today."),
             ],
         }, (("Instruments", "study/instruments.json"),), _known_values, ("measurement",)),
    Step("uncertainty", "Uncertainty, replicates or statistical error", "Uncertainty, Replicates or Statistical Error",
         "The GUM budget of every registered quantity (type A from the replicates, type B from the instrument records, combined, effective degrees of freedom and expanded with its coverage factor) and every fit, comparison and sweep through the append-only analysis log, labelled confirmatory or exploratory by the locked protocol.",
         ("read", "write", "bash"), ("study/uncertainty/<quantity>.json", "analysis/log.jsonl"), "G-UNCERTAINTY", {
             "skills": ["lab-simulation"],
             "agent": "measurement core, analysis log & operator",
             "actions": [
                 _command(f"{MEASURE_CLI} uncertainty compute --root . --quantity <name> --condition <key=value>",
                          "Compute an uncertainty budget",
                          "The GUM budget of the quantity into study/uncertainty/<quantity>.json."),
                 _command(f'{MEASURE_CLI} uncertainty compute --root . --quantity <name> --allow-past-due --by {_OPERATOR} '
                          '--reason "<why the readings still hold>"',
                          "Override a past-due calibration (operator)", "Your decision, with its reason; the budget records it."),
                 _command(f"{ANALYSIS_CLI} run --root . --outcome <outcome-id> --input <data-file> "
                          "--output <result-file> -- <command>", "Run a logged analysis",
                          "Hashes the script, the inputs and the outputs and labels the run."),
                 _command(f'{ANALYSIS_CLI} record --root . --outcome <outcome-id> --by {_OPERATOR} '
                          '--tool "<tool name>"', "Record a GUI analysis (operator)",
                          "Your attested entry for an analysis run outside a script."),
                 _command(f"{MEASURE_CLI} status --root .", "Measurement records status",
                          "Instruments, data files, budgets and agreement in one object, with every warning."),
             ],
         }, (("Uncertainty budgets (G-CALIBRATION)", "study/uncertainty/*.json"), ("Analysis log", "analysis/log.jsonl")),
         _uncertainty, ("measurement", "analysis_log")),
    Step("open_data", "Open data and code", "Open Data & Code",
         "The operator deposits the registered raw data files, the model and analysis code and the budgets in a repository, named by the repository-url declaration of the back matter (data and code availability).",
         ("read",), ("study/measurements.json", "paper/main.tex (repository-url)"), "G-OPEN", {
             "skills": ["lab-simulation", "paper-writing"],
             "agent": "operator",
             "actions": [
                 _command(f"{MEASURE_CLI} data status --root .", "Registered raw data files",
                          "Each registered file with its sha256, current or changed."),
                 _command(f'{PAPER_CLI} declare --declaration repository-url --value "<DOI or URL>"',
                          "Declare the data and code repository (operator)",
                          "The DOI or URL of the repository that holds the raw data, the code and the budgets."),
             ],
         }, (("Raw data registrations", "study/measurements.json"), ("Declarations (repository-url)", "paper/main.tex")),
         _open_files, ("measurement",)),
    Step("reporting_lab", "Reporting check and audit", "Reporting Check, Final Judge & Audit",
         "The gum-reporting checklist of the agreed variant (item by item: satisfied, missing or needs judgment), the study checks of paper_cli.py verify, the measurement-science final judge and the cross-cutting audit; audits report, they never repair.",
         ("read", "bash"), (".papersmith/audit.json",), "G-AUDIT", {
             "skills": ["skill-audit"],
             "agent": "checklist engine, skill-audit & smith audit",
             "actions": [
                 _command(f"{CHECKLIST_CLI} check --guideline gum-reporting --root .", "GUM uncertainty reporting checklist",
                          "GUM clause 7 item by item: satisfied, missing or needs judgment."),
                 *copy.deepcopy(phase_actions.ACTIONS["audit"]["actions"]),
             ],
         }, phase_actions.EVIDENCE["audit"], _reporting, ("checklists",)),
    # ----- data-resource (src/papersmith/templates/paper-flow-data-resource.md.tpl)
    Step("plausibility_resource", "Plausibility and paper type", "Plausibility & Paper Type",
         "The state of the art and the closest existing resources scouted around the idea, the plausibility report accepted by the operator, and the data-resource paper type agreed with /paper-type; the type names the datasheets checklist.",
         ("read", "write", "http"), ("sota-pool/candidates.json", ".papersmith/paper_type.json"), "G-PAPER-TYPE", {
             "skills": ["plausibility", "paper-type"],
             "agent": "plausibility, paper-type-advisor & operator",
             "actions": [
                 _prompt("/plausibility", "Explore the plausibility of the idea", [
                     "Write the idea in at least two sentences: what the resource holds, how it was collected, and the questions it lets others answer.",
                     "The agent scouts about 25 SOTA references and the closest existing resources by their abstracts and grades the claims with verbatim quotes.",
                     "Nothing moves on until you accept the report.",
                 ], "E.g.: We release a corpus of annotated clinical notes for asthma triage, collected under consent …",
                     min_sentences=2),
                 _prompt("/paper-type", "Agree the paper type", [
                     "The agent scores the idea against the paper types and discusses its suggestion with you.",
                     "The data-resource type has no variants: its reporting checklist is datasheets (Datasheets for Datasets).",
                     "The final judge reads the paper on the data-descriptor rubric.",
                 ], "E.g.: discuss whether this is a data resource or an observational study on the same data.",
                     optional=True),
                 _redirect("View the paper types", "papertype", "Every paper type with its score, guideline and variants."),
             ],
         }, (("Candidate pool", "sota-pool/candidates.json"), ("Plausibility acceptance", ".papersmith/plausibility.json"),
             ("Agreed paper type", ".papersmith/paper_type.json")), _plausibility_type),
    Step("collection_protocol", "Collection protocol", "Collection Protocol (G-STUDY-PROTOCOL)",
         "The collection protocol as managed revisions: the purpose of the resource, the sources or participants and how they are sampled, the planned records and their size with its justification, the annotation scheme, the primary outcome the resource is built to measure and the analysis plan of any baseline. The operator approves a revision; a later change is an amendment with its reason.",
         ("read", "write"), ("protocol/study-protocol-<slug>-vNN.md", "study/protocol.lock.json"), PROTOCOL_GATE, {
             "skills": ["study-protocol-deliberation"],
             "agent": "study-protocol-deliberation & operator",
             "actions": [
                 _prompt("/study-protocol-deliberation", "Deliberate the collection protocol with the agent", [
                     "The agent drafts the protocol with you as labelled fields: purpose, sources or participants and their sampling, planned records and their size, annotation scheme, primary outcome and the analysis plan of any baseline.",
                     "The sources, the annotation scheme and the primary outcome are yours; the agent never invents a record or a size from data it has not seen.",
                     "Each accepted change is published as a new managed revision under protocol/.",
                 ], "E.g.: draft the first collection protocol of the clinical notes corpus.", optional=True),
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
    Step("ethics_licence", "Ethics, consent and licence", "Ethics, Consent & Licence (G-ETHICS)",
         "The ethics approval and the consent route, recorded by the operator against the approved protocol or recorded as not applicable with the reason, and the right to release every dataset: the operator's own-data statement or the allowed licence of a third-party source.",
         ("read", "write"), ("study/ethics.json", "datasets/registry.json"), ETHICS_GATE, {
             "skills": ["datasets"],
             "agent": "operator",
             "actions": [
                 _command(f'{STUDY_CLI} ethics record --root . --by {_OPERATOR} --committee "<committee>" '
                          f'--code "<approval code>" --date <YYYY-MM-DD> --consent "<consent route>"',
                          "Record the ethics approval (operator, G-ETHICS)",
                          "The committee, the approval code, its date and the consent route."),
                 _command(f'{STUDY_CLI} ethics record --root . --by {_OPERATOR} --not-applicable --reason "<why>"',
                          "Record that no ethics approval applies (operator)", "With the reason, in your words."),
                 _command(f'{DATASETS_CLI} own --slug <slug> --by {_OPERATOR} --statement "<how the data may be used>"',
                          "Register your own data (operator)", "Its data-use statement, in your words."),
                 _command(f'{DATASETS_CLI} license --slug <slug> --source-license "<licence as the source states it>"',
                          "Record the licence of a third-party source",
                          "Only an allowed licence lets the resource redistribute it."),
                 _command(f"{STUDY_CLI} status --root .", "Study records status",
                          "The protocol, ethics and registration states and their warnings."),
             ],
         }, (("Ethics record (G-ETHICS)", "study/ethics.json"), ("Dataset registry", "datasets/registry.json")),
         _ethics_licence, ("records", "datasets_cli")),
    Step("curation", "Collection, curation and documentation", "Collection, Curation & Documentation",
         "The operator collects the records and writes every data file; the assistant never collects, writes or edits one. Each dataset is described by a data dictionary, scaffolded from a file's header and completed by the operator (type, unit, allowed values, missing codes, personal-data flags).",
         ("read", "write"), ("datasets/<slug>/dictionary.json",), "G-DOCUMENTATION", {
             "skills": ["datasets"],
             "agent": "datasets & operator",
             "actions": [
                 _command(f"{DATASETS_CLI} dictionary init --slug <slug> --file <data.csv>",
                          "Scaffold the data dictionary", "One entry per column; you complete every type, unit, range and PII flag."),
                 _command(f"{DATASETS_CLI} dictionary check --slug <slug>", "Check the data dictionary",
                          "Validates datasets/<slug>/dictionary.json."),
                 _command(f"{DATASETS_CLI} status", "Datasets status", "Every registered dataset with its QC status."),
             ],
         }, (("Dataset registry", "datasets/registry.json"), ("Data dictionaries", "datasets/*/dictionary.json")),
         _curation, ("datasets_cli",)),
    Step("quality", "Quality checks", "Quality Checks (G-DATA-QC)",
         "Each own dataset measured by a quality check against its current data dictionary, and de-identified where the dictionary flags personal data, with the operator's statement of how.",
         ("read", "write"), ("datasets/<slug>/qc.json",), DATA_GATE, {
             "skills": ["datasets"],
             "agent": "datasets & operator",
             "actions": [
                 _command(f"{DATASETS_CLI} qc --slug <slug> --file <data.csv>", "Run the quality check (G-DATA-QC)",
                          "Measures the data against its dictionary into datasets/<slug>/qc.json."),
                 _command(f'{DATASETS_CLI} deidentify --slug <slug> --by {_OPERATOR} --statement "<how the PII columns were removed>"',
                          "Record the de-identification (operator)", "How the columns flagged as personal data were removed or transformed."),
                 _command(f"{DATASETS_CLI} status", "Datasets status", "Every registered dataset with its QC status."),
             ],
         }, (("Quality checks (G-DATA-QC)", "datasets/*/qc.json"),), _quality, ("datasets_cli",)),
    Step("baselines", "Baselines", "Baselines & Analysis Log",
         "Every preprocessing step, labeling script, agreement statistic and baseline through the append-only, hash-chained log: a wrapped script or the operator's entry for a GUI tool. A baseline is confirmatory only when the locked protocol names its outcome and plan, exploratory otherwise.",
         ("read", "bash"), ("analysis/log.jsonl",), "G-ANALYSIS", {
             "skills": [],
             "agent": "analysis log & operator",
             "actions": [
                 _requires(_command(f"{ANALYSIS_CLI} run --root . --outcome <outcome-id> --input <data-file> "
                                    "--output <result-file> -- <command>", "Run a logged analysis",
                                    "Hashes the script, the inputs and the outputs and labels the run."), DATA_GATE),
                 _requires(_command(f'{ANALYSIS_CLI} record --root . --outcome <outcome-id> --by {_OPERATOR} '
                                    '--tool "<tool name>"', "Record a GUI analysis (operator)",
                                    "Your attested entry for an analysis run outside a script."), DATA_GATE),
                 _command(f"{ANALYSIS_CLI} status --root .", "Analysis log status",
                          "The runs with their labels and the protocol outcomes still unanalysed."),
             ],
         }, (("Analysis log", "analysis/log.jsonl"),), _baselines, ("analysis_log",)),
    Step("deposit", "Deposit", "Deposit with a Persistent Identifier (G-DEPOSIT)",
         "The operator deposits the files in a repository and records the persistent identifier and the licence, bound to the sha256 of every registered file; the assistant never uploads. A file changed, added or missing since makes the deposit stale until the new version is deposited and recorded again.",
         ("read", "write"), ("datasets/registry.json",), DEPOSIT_GATE, {
             "skills": ["datasets"],
             "agent": "operator",
             "actions": [
                 _requires(_command(f'{DATASETS_CLI} deposit --slug <slug> --repository "<repository>" '
                                    f'--identifier "<DOI or other identifier>" --license "<licence>" --by {_OPERATOR}',
                                    "Record the deposit (operator, G-DEPOSIT)",
                                    "After you deposited the files: the repository, the persistent identifier and the licence; add --scheme for a non-DOI identifier."),
                           DATA_GATE),
                 _command(f"{DATASETS_CLI} status", "Datasets status",
                          "Every registered dataset with its deposit, current or stale."),
                 _command(f'{PAPER_CLI} declare --declaration repository-url --value "<DOI or URL>"',
                          "Declare the data repository (operator)",
                          "The DOI or URL of the deposit, named in the data and code availability statement."),
             ],
         }, (("Deposit records (G-DEPOSIT)", "datasets/registry.json"), ("Declarations (repository-url)", "paper/main.tex")),
         _deposit, ("datasets_cli",)),
    Step("reporting_resource", "Reporting check and audit", "Reporting Check, Final Judge & Audit",
         "The datasheets checklist the type names (item by item: satisfied, missing or needs judgment), the study checks of paper_cli.py verify, the data-descriptor final judge and the cross-cutting audit; audits report, they never repair.",
         ("read", "bash"), (".papersmith/audit.json",), "G-AUDIT", {
             "skills": ["skill-audit"],
             "agent": "checklist engine, skill-audit & smith audit",
             "actions": [
                 _command(f"{CHECKLIST_CLI} check --guideline datasheets --root .", "Datasheets checklist",
                          "Datasheets for Datasets item by item: satisfied, missing or needs judgment."),
                 *copy.deepcopy(phase_actions.ACTIONS["audit"]["actions"]),
             ],
         }, phase_actions.EVIDENCE["audit"], _reporting, ("checklists",)),
)}

# ----- experiment-intervention (src/papersmith/templates/paper-flow-experiment-intervention.md.tpl)
STEPS.update({step.id: step for step in (
    Step("plausibility_intervention", "Plausibility and paper type", "Plausibility & Paper Type",
         "The state of the art scouted around the idea, the plausibility report accepted by the operator, and the experiment-intervention paper type and its variant agreed with /paper-type: a trial with people (CONSORT 2025) or a field experiment (ARRIVE 2.0). The variant chooses the reporting checklist and whether the registration must be prospective and the participant flow signed off.",
         ("read", "write", "http"), ("sota-pool/candidates.json", ".papersmith/paper_type.json"), "G-PAPER-TYPE", {
             "skills": ["plausibility", "paper-type"],
             "agent": "plausibility, paper-type-advisor & operator",
             "actions": [
                 _prompt("/plausibility", "Explore the plausibility of the idea", [
                     "Write the idea in at least two sentences: the intervention, its comparator and the outcome it should change.",
                     "The agent scouts about 25 SOTA references by their abstracts and grades the claims with verbatim quotes.",
                     "Nothing moves on until you accept the report.",
                 ], "E.g.: A reading programme raises reading scores in primary schools. We randomise two schools' classes to the programme or to usual teaching …",
                     min_sentences=2),
                 _prompt("/paper-type", "Agree the paper type and its variant", [
                     "The agent scores the idea against the paper types and discusses its suggestion with you.",
                     "You agree the variant: a trial with people (CONSORT 2025) or a field experiment with plots, crops or animals (ARRIVE 2.0).",
                     "Until a variant is agreed the board applies the trial rules: a prospective registration and a signed-off participant flow.",
                 ], "E.g.: discuss whether this is a trial with people or a field experiment.", optional=True),
                 _redirect("View the paper types", "papertype", "Every paper type with its score, guideline and variants."),
             ],
         }, (("Candidate pool", "sota-pool/candidates.json"), ("Plausibility acceptance", ".papersmith/plausibility.json"),
             ("Agreed paper type", ".papersmith/paper_type.json")), _plausibility_type),
    Step("protocol_registration", "Protocol and registration", "Protocol & Registration (G-STUDY-PROTOCOL, G-REGISTRATION)",
         "The protocol as managed revisions: the research question, the intervention and the comparator, exactly one primary outcome, the secondary outcomes and the harms, the design, the eligibility, the sample size with its justification and the analysis plan. The operator approves a revision, then records the registration; a trial with people is registered on or before its first enrolment.",
         ("read", "write"), ("protocol/study-protocol-<slug>-vNN.md", "study/protocol.lock.json", "study/registration.json"),
         PROTOCOL_GATE, {
             "skills": ["study-protocol-deliberation"],
             "agent": "study-protocol-deliberation & operator",
             "actions": [
                 _prompt("/study-protocol-deliberation", "Deliberate the protocol with the agent", [
                     "The agent drafts the protocol with you as labelled fields: question, intervention and comparator, one primary outcome, secondary outcomes and harms, design, eligibility, sample size and analysis plan.",
                     "The intervention, the comparator and the primary outcome are yours; the agent never invents data or a sample size from data it has not seen.",
                     "Each accepted change is published as a new managed revision under protocol/.",
                 ], "E.g.: draft the first protocol of the reading programme trial.", optional=True),
                 _command(f"{STUDY_CLI} protocol status --root .", "Protocol lock status",
                          "Whether the approved revision is current, changed or absent."),
                 _command(f"{STUDY_CLI} protocol approve --root . --by {_OPERATOR}",
                          "Approve the protocol (operator, G-STUDY-PROTOCOL)",
                          "Only the operator approves; the approval pins the revision's sha256."),
                 _command(f'{STUDY_CLI} protocol amend --root . --by {_OPERATOR} --reason "<why>"',
                          "Record an amendment", "A change after the approval, with its reason; the methods report it."),
                 _command(f'{STUDY_CLI} registration record --root . --by {_OPERATOR} --registry "<registry>" '
                          f'--id "<registration id>" --date <YYYY-MM-DD> --first-enrolment <YYYY-MM-DD>',
                          "Record the registration (operator, G-REGISTRATION)",
                          "A trial with people passes only when registered on or before its first enrolment (ICMJE)."),
                 _command(f'{STUDY_CLI} registration record --root . --by {_OPERATOR} --not-applicable --reason "<why>"',
                          "Record that no registration applies (operator)",
                          "For a field experiment without a registry; a trial with people must be registered."),
             ],
         }, (("Protocol revisions", "protocol/study-protocol-*.md"),
             ("Protocol approval (G-STUDY-PROTOCOL)", "study/protocol.lock.json"),
             ("Registration record (G-REGISTRATION)", "study/registration.json")),
         _protocol_registration, ("records",)),
    Step("ethics_consent", "Ethics and consent", "Ethics & Consent (G-ETHICS)",
         "The approval of the ethics or animal ethics committee and the consent route, recorded by the operator against the approved protocol, or recorded as not applicable with the reason; an amendment of the protocol makes it stale.",
         ("read", "write"), ("study/ethics.json",), ETHICS_GATE, {
             "skills": [],
             "agent": "operator",
             "actions": [
                 _command(f'{STUDY_CLI} ethics record --root . --by {_OPERATOR} --committee "<committee>" '
                          f'--code "<approval code>" --date <YYYY-MM-DD> --consent "<consent route>"',
                          "Record the ethics approval (operator, G-ETHICS)",
                          "The committee, the approval code, its date and the consent route."),
                 _command(f'{STUDY_CLI} ethics record --root . --by {_OPERATOR} --not-applicable --reason "<why>"',
                          "Record that no ethics approval applies (operator)", "With the reason, in your words."),
                 _command(f"{STUDY_CLI} status --root .", "Study records status",
                          "The protocol, ethics and registration states and their warnings."),
             ],
         }, (("Ethics record (G-ETHICS)", "study/ethics.json"),), _ethics_consent, ("records",)),
    Step("allocation", "Allocation", "Allocation, Blocks & Sample Size (G-ALLOCATION)",
         "The operator generates the allocation sequence with their own tool or service, keeps it concealed and records it: the method, the concealment and the list's sha256 and row count, bound to the protocol lock. The assistant never generates, reads out or alters the sequence; a field experiment's blocks, plots and units are part of the locked protocol.",
         ("read", "write"), ("study/allocation.json",), ALLOCATION_GATE, {
             "skills": [],
             "agent": "operator",
             "actions": [
                 _command(f'{STUDY_CLI} allocation record --root . --by {_OPERATOR} --file <allocation-list.csv> '
                          '--method block --block-size <n> --concealment "<how the sequence was concealed>"',
                          "Record the allocation (operator, G-ALLOCATION)",
                          "Method simple, block, stratified, minimisation or cluster (--strata for stratified and minimisation); the list stays yours."),
                 _command(f"{STUDY_CLI} allocation status --root .", "Allocation record status",
                          "Whether the record is current or stale: the list changed or removed, or the protocol amended."),
             ],
         }, (("Allocation record (G-ALLOCATION)", "study/allocation.json"),
             ("Protocol approval (G-STUDY-PROTOCOL)", "study/protocol.lock.json")), _allocation, ("records",)),
    Step("intervention_followup", "Intervention and follow-up", "Intervention, Follow-up & Data Quality (G-DATA-QC)",
         "The operator delivers the intervention and collects the follow-up data, registered with its data-use statement, described by a data dictionary, measured by a quality check against it and de-identified where the dictionary flags personal data. The assistant never generates or edits data.",
         ("read", "write"), ("datasets/registry.json", "datasets/<slug>/dictionary.json", "datasets/<slug>/qc.json"),
         DATA_GATE, copy.deepcopy(STEPS["data"].actions), STEPS["data"].evidence, _data, ("datasets_cli",)),
    Step("prespecified_analysis", "Pre-specified analysis", "Pre-specified Analysis Log",
         "Every analysis through the append-only, hash-chained log, after the allocation is recorded: a wrapped script or the operator's entry for a GUI tool. The label is computed, never chosen: confirmatory only for an outcome and plan entry of the current locked protocol, exploratory otherwise.",
         ("read", "bash"), ("analysis/log.jsonl",), "G-ANALYSIS", {
             "skills": [],
             "agent": "analysis log & operator",
             "actions": [
                 _requires(_command(f"{ANALYSIS_CLI} run --root . --outcome <outcome-id> --input <data-file> "
                                    "--output <result-file> -- <command>", "Run a logged analysis",
                                    "Hashes the script, the inputs and the outputs and labels the run."),
                           *TRIAL_ANALYSIS_GATES),
                 _requires(_command(f'{ANALYSIS_CLI} record --root . --outcome <outcome-id> --by {_OPERATOR} '
                                    '--tool "<tool name>"', "Record a GUI analysis (operator)",
                                    "Your attested entry for an analysis run outside a script."), *TRIAL_ANALYSIS_GATES),
                 _command(f"{ANALYSIS_CLI} status --root .", "Analysis log status",
                          "The runs with their labels and the protocol outcomes still unanalysed."),
             ],
         }, (("Analysis log", "analysis/log.jsonl"),), _analysis, ("analysis_log",)),
    Step("flow_units", "Flow of units", "Flow of Units (G-FLOW)",
         "The CONSORT 2025 participant flow with one column per arm: the operator enters every count, the arithmetic is checked, the figure drawn and the operator signs it off; any later edit makes the sign-off stale. Required for a trial with people; a field experiment may keep it or report its experimental units in a table.",
         ("read", "write"), ("study/flow.json", "paper/Figures/participant-flow.svg", "study/flow-signoffs.json"), FLOW_GATE, {
             "skills": [],
             "agent": "participant flow & operator",
             "actions": [
                 _command(f"{FLOW_CLI} template consort-2025 --root . --arm <arm> --arm <arm> --write",
                          "Write the empty CONSORT flow",
                          "study/flow.json with one column per arm and no counts; you enter every count."),
                 _command(f"{FLOW_CLI} check --root .", "Check the counts", "Every arithmetic problem of the flow."),
                 _command(f"{FLOW_CLI} render --root .", "Draw the flow figure",
                          "Writes paper/Figures/participant-flow.svg from valid counts."),
                 _command(f"{FLOW_CLI} signoff --root . --by {_OPERATOR}", "Sign the flow off (operator, G-FLOW)",
                          "Refused on invalid counts or a missing or stale figure."),
                 _command(f"{FLOW_CLI} status --root .", "Participant flow status",
                          "The counts' validity, the figure and the latest sign-off."),
             ],
         }, (("Participant flow counts", "study/flow.json"), ("Participant flow figure", "paper/Figures/participant-flow.svg"),
             ("Participant flow sign-offs (G-FLOW)", "study/flow-signoffs.json")), _flow_units, ("flow_cli",)),
    Step("reporting_intervention", "Reporting check and audit", "Reporting Check, Final Judge & Audit",
         "The checklist of the agreed variant (consort-2025 for a trial with people, arrive-2 for a field experiment; item by item: satisfied, missing or needs judgment), the study checks of paper_cli.py verify, the empirical-study final judge and the cross-cutting audit; audits report, they never repair.",
         ("read", "bash"), (".papersmith/audit.json",), "G-AUDIT", {
             "skills": ["skill-audit"],
             "agent": "checklist engine, skill-audit & smith audit",
             "actions": [
                 _command(f"{CHECKLIST_CLI} check --guideline consort-2025 --root .", "CONSORT 2025 checklist",
                          "For a trial with people, item by item: satisfied, missing or needs judgment."),
                 _command(f"{CHECKLIST_CLI} check --guideline arrive-2 --root .", "ARRIVE 2.0 checklist",
                          "For a field experiment, item by item; a plot or crop experiment answers the design and analysis items that apply."),
                 *copy.deepcopy(phase_actions.ACTIONS["audit"]["actions"]),
             ],
         }, phase_actions.EVIDENCE["audit"], _reporting, ("checklists",)),
)})


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
    #: Gates listed only when the operator declared a validation with people
    #: (:func:`with_people`); they are read always, so a step can show them.
    conditional_gates: frozenset[str] = frozenset()
    #: gate id -> the step this line lists it under, when not the gate's own ``step``.
    gate_steps: Mapping[str, str] = field(default_factory=dict)
    #: Reporting checklists the line names beside the agreed type's own.
    extra_checklists: tuple[str, ...] = ()
    #: gate id -> the line's own definition of a shared gate id (see :func:`gate_definition`).
    gate_defs: Mapping[str, Gate] = field(default_factory=dict)


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
    # The calibration step waits for nothing: its instrument and reading records
    # are the first the board can read after the specifications (the design files'
    # repository-url declaration lives in paper/main.tex, opened at the writing).
    "hardware": LineTable(
        kind="hardware",
        steps=("harness", "plausibility_hardware", "specifications", "design_files", "build", "calibration",
               "agreement", "field_validation", "open_files", "writing", "paper", "reporting_hardware"),
        gates=(SPEC_GATE, CALIBRATION_GATE, AGREEMENT_GATE, *PEOPLE_GATES),
        phase_gates={"agreement": CALIBRATION_GATE, "writing": AGREEMENT_GATE},
        ungated=frozenset({"harness", "calibration", "reporting_hardware"}),
        transversal="reporting_hardware",
        conditional_gates=frozenset(PEOPLE_GATES),
        gate_steps={gate: "field_validation" for gate in PEOPLE_GATES},
        extra_checklists=("gum-reporting",),
    ),
    # G-CALIBRATION completes with the budgets of the uncertainty step, so it is
    # listed there; that step waits for the calibration against known values.
    "lab-simulation": LineTable(
        kind="lab-simulation",
        steps=("harness", "plausibility_lab", "sample_model", "lab_protocol", "observables", "known_values",
               "uncertainty", "open_data", "writing", "paper", "reporting_lab"),
        gates=(PROTOCOL_GATE, CALIBRATION_GATE),
        phase_gates={"writing": CALIBRATION_GATE},
        ungated=frozenset({"harness", "reporting_lab"}),
        transversal="reporting_lab",
        gate_steps={PROTOCOL_GATE: "lab_protocol", CALIBRATION_GATE: "uncertainty"},
    ),
    # G-ETHICS is the line's own (the ethics record plus the right to release).
    # The deposit waits for nothing in the chain but its record waits for
    # G-DATA-QC: a resource is deposited whether or not it has baselines.
    "data-resource": LineTable(
        kind="data-resource",
        steps=("harness", "plausibility_resource", "collection_protocol", "ethics_licence", "curation", "quality",
               "baselines", "deposit", "writing", "paper", "reporting_resource"),
        gates=(PROTOCOL_GATE, ETHICS_GATE, DATA_GATE, DEPOSIT_GATE),
        phase_gates={"baselines": DATA_GATE, "writing": DEPOSIT_GATE},
        ungated=frozenset({"harness", "deposit", "reporting_resource"}),
        transversal="reporting_resource",
        gate_steps={PROTOCOL_GATE: "collection_protocol", DATA_GATE: "quality"},
        gate_defs={ETHICS_GATE: RESOURCE_ETHICS},
    ),
    # G-REGISTRATION and G-FLOW are the line's own: the agreed variant decides
    # them (J3, J4), the stricter human-trial rules when none is agreed. The
    # pre-specified analyses also wait for G-ALLOCATION (their actions).
    TRIAL_KIND: LineTable(
        kind=TRIAL_KIND,
        steps=("harness", "plausibility_intervention", "protocol_registration", "ethics_consent", "allocation",
               "intervention_followup", "prespecified_analysis", "flow_units", "writing", "paper",
               "reporting_intervention"),
        gates=(PROTOCOL_GATE, REGISTRATION_GATE, ETHICS_GATE, ALLOCATION_GATE, DATA_GATE, FLOW_GATE),
        phase_gates={"prespecified_analysis": DATA_GATE, "writing": FLOW_GATE},
        ungated=frozenset({"harness", "reporting_intervention"}),
        transversal="reporting_intervention",
        gate_steps={PROTOCOL_GATE: "protocol_registration", ETHICS_GATE: "ethics_consent",
                    DATA_GATE: "intervention_followup"},
        gate_defs={REGISTRATION_GATE: TRIAL_REGISTRATION, FLOW_GATE: TRIAL_FLOW},
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
        gate = gate_definition(ctx.table, gate_id)
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
    if table.conditional_gates:
        try:
            ctx.people = with_people(ctx)
        except Exception:  # an unreadable record: the people gates stay unlisted, the step shows why
            ctx.people = False
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
    defined = {gate_id: gate_definition(table, gate_id) for gate_id in table.gates}
    out = [{"id": gate_id, "name": defined[gate_id].name, "status": ctx.gates[gate_id]["status"],
            "criteria": defined[gate_id].criteria, "reviewer": "operator",
            "phase": position[table.gate_steps.get(gate_id, defined[gate_id].step)]}
           for gate_id in table.gates if ctx.people or gate_id not in table.conditional_gates]
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
    ("study/uncertainty", "*.json", "Uncertainty Budgets"),
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


__all__ = ["ANALYSIS_GATES", "DASHBOARD_SKILLS", "GATES", "LINE_TABLES", "LineTable", "MODULES", "PEOPLE_GATES",
           "RESOURCE_ETHICS", "STEPS", "Step", "TELEMETRY_NOTE", "TRIAL_ANALYSIS_GATES", "TRIAL_FLOW",
           "TRIAL_REGISTRATION", "agreed_type", "artifacts", "board", "board_for", "checklist_detail",
           "gate_definition", "load_module", "own_datasets", "resource_datasets", "section_metadata", "stage_for",
           "telemetry", "trial_variant", "with_people"]
