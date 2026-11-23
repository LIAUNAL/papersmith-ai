"""The analysis log of an empirical study: every analysis run, labelled.

    analysis/log.jsonl        one JSON object per line, append-only, each line
                              chained to the one before it by ``prev`` (the
                              sha256 of that line's bytes)
    analysis/streams/<sha>    the stdout and stderr of a wrapped run, stored
                              under their own sha256

An entry's ``label`` is computed here and never accepted from a caller
(decision D7 of ``odd/tasks/paper-type-lines.md``): ``confirmatory`` when the
protocol lock is current and the outcome (and the plan entry, when one is
named) is in the locked revision; ``exploratory`` otherwise, with the reason.
A run before any lock is exploratory, and only an amendment of the protocol
makes a later run of a new outcome confirmatory; an entry already written
keeps its label.

The outcome ids and the analysis plan are read by the study protocol's single
parser, ``skills/study-protocol-deliberation/protocol-fields.ts``, through its
``fields.mjs`` entry point under ``node``: this module never parses the
Markdown. ``analysis_cli.py`` is the only writer of the log; the readers here
(``read_log``, ``summary``, ``manuscript_inputs``) write nothing.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

if __package__ in (None, ""):  # loaded by path: make `skills._core.empirical` importable
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from skills._core.empirical import records  # noqa: E402
else:
    from . import records

StudyError = records.StudyError

SCHEMA = 1
LOG_PATH = "analysis/log.jsonl"
STREAMS_DIR = "analysis/streams"
LABELS = ("confirmatory", "exploratory")
#: The analysis-plan entries a protocol names, by the key `parseProtocol` reports them under.
PLAN_ENTRIES = {"primary-model": "primaryModel", "covariates": "covariates",
                "missing-data": "missingData", "multiplicity": "multiplicity"}
_NOT_PLANNED = ("none", "not applicable", "n/a")
OUTCOME_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
FIELDS_SCRIPT = Path(__file__).resolve().parents[2] / "study-protocol-deliberation" / "fields.mjs"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- the protocol, through its parser


def parse_protocols(sources: dict[str, bytes]) -> dict[str, dict]:
    """``{key: {"primary", "secondary", "outcomes", "analysisPlan"}}`` from the protocol parser.
    ``PROTOCOL_PARSER_UNAVAILABLE`` when node or the parser cannot answer."""
    if not sources:
        return {}
    node = shutil.which("node")
    if node is None or not FIELDS_SCRIPT.is_file():
        missing = "node is not on PATH" if node is None else f"{FIELDS_SCRIPT.name} is not shipped"
        raise StudyError("PROTOCOL_PARSER_UNAVAILABLE", f"the protocol's outcomes are read by the study protocol "
                                                        f"parser under node, and {missing}; install node 22.18+")
    payload = json.dumps({key: data.decode("utf-8", errors="replace") for key, data in sources.items()})
    try:
        proc = subprocess.run([node, str(FIELDS_SCRIPT)], input=payload, capture_output=True, text=True,
                              timeout=60, check=False)
        parsed = json.loads(proc.stdout) if proc.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        parsed = None
        proc = None
    if not isinstance(parsed, dict) or set(parsed) != set(sources):
        detail = (proc.stderr or proc.stdout).strip()[-300:] if proc is not None else "node did not answer"
        raise StudyError("PROTOCOL_PARSER_UNAVAILABLE", f"the study protocol parser did not answer ({detail}); "
                                                        "it needs node 22.18+ (TypeScript type stripping)")
    return parsed


def _locked_bytes(root: Path, revision: str, digest: str) -> bytes | None:
    path = Path(root) / revision
    if not path.is_file():
        return None
    data = path.read_bytes()
    return data if sha256_bytes(data) == digest else None


def locked_protocol(root: Path) -> dict:
    """The lock's state and, when the locked bytes are still on disk, the locked revision parsed:
    ``{"state", "revision", "sha256", "reasons", "fields"}`` (``fields`` None when unreadable)."""
    state = records.protocol_state(root)
    view = {"state": state["state"], "revision": state.get("revision"), "sha256": state.get("sha256"),
            "reasons": state.get("reasons", []), "fields": None}
    if state["state"] in ("current", "changed"):
        data = _locked_bytes(root, state["revision"], state["sha256"])
        if data is not None:
            view["fields"] = parse_protocols({"locked": data})["locked"]
    return view


def plan_entries(fields: dict) -> list[str]:
    """The analysis-plan entries the protocol declares with a planned analysis."""
    plan = fields.get("analysisPlan") or {}
    return [entry for entry, key in PLAN_ENTRIES.items()
            if isinstance(plan.get(key), str) and plan[key].strip().lower().rstrip(".") not in _NOT_PLANNED]


def protocol_outcomes(fields: dict) -> list[str]:
    return ([fields["primary"]] if fields.get("primary") else []) + list(fields.get("secondary") or [])


def compute_label(root: Path, outcome: str, plan: str | None) -> tuple[str, dict, dict]:
    """``(label, reason, protocol)`` for an analysis of ``outcome`` (and ``plan``) now."""
    state = records.protocol_state(root)
    view = locked_protocol(root) if state["state"] == "current" else None
    protocol = {"state": state["state"], "revision": state.get("revision"), "sha256": state.get("sha256"),
                "amendments": state.get("amendments", 0)}

    def exploratory(code: str, message: str):
        return "exploratory", {"code": code, "message": message}, protocol

    if state["state"] == "absent":
        return exploratory("no-protocol-lock", f"the protocol is not approved (gate {records.GATE}): an analysis "
                                               "before the lock is exploratory")
    if state["state"] == "corrupt":
        return exploratory("protocol-lock-corrupt", state.get("message", "the protocol lock cannot be read"))
    if state["state"] == "changed":
        return exploratory("protocol-changed", f"the protocol changed after its approval "
                                               f"({', '.join(state['reasons'])}) and no amendment records it")
    fields = view["fields"] if view else None
    if fields is None:
        return exploratory("protocol-changed", "the locked revision's bytes are not on disk")
    outcomes = protocol_outcomes(fields)
    if outcome not in outcomes:
        return exploratory("outcome-not-in-protocol", f"{outcome} is not an outcome of the locked protocol "
                                                      f"({', '.join(outcomes) or 'none'}); only an amendment "
                                                      "that adds it makes a later analysis confirmatory")
    if plan is not None:
        entries = plan_entries(fields)
        if plan not in entries:
            return exploratory("plan-entry-not-in-protocol", f"the locked protocol plans no {plan!r} analysis "
                                                             f"(it plans {', '.join(entries) or 'none'})")
        if plan == "primary-model" and outcome != fields.get("primary"):
            return exploratory("primary-model-not-for-outcome", f"the primary model analyses {fields.get('primary')}, "
                                                                f"not {outcome}")
    where = f"the {plan} analysis of " if plan else ""
    return "confirmatory", {"code": "in-locked-protocol",
                            "message": f"{where}{outcome} is pre-specified in {state['revision']}"}, protocol


# --------------------------------------------------------------------------- the log


def read_log(root: Path) -> list[dict]:
    """Every entry, oldest first; ``ANALYSIS_LOG_CORRUPT`` when a line is not an entry or the
    chain of ``prev`` hashes is broken (a line edited, removed or inserted)."""
    path = Path(root) / LOG_PATH
    if not path.is_file():
        return []
    entries, prev = [], None
    for number, line in enumerate(path.read_bytes().split(b"\n"), start=1):
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            entry = None
        if not isinstance(entry, dict) or entry.get("label") not in LABELS:
            raise StudyError("ANALYSIS_LOG_CORRUPT", f"{LOG_PATH} line {number} is not an analysis entry; the log "
                                                     "is append-only, so restore the log from its copy")
        if entry.get("prev") != prev or entry.get("seq") != len(entries) + 1:
            raise StudyError("ANALYSIS_LOG_CORRUPT", f"{LOG_PATH} line {number} breaks the chain of entries (an "
                                                     "entry was edited, removed or inserted); restore the log")
        entries.append(entry)
        prev = sha256_bytes(line)
    return entries


def summary(entries: list[dict]) -> dict:
    """Per outcome, how many entries of each label, and the label of its first entry."""
    outcomes: dict[str, dict] = {}
    for entry in entries:
        counts = outcomes.setdefault(entry["outcome"], {"confirmatory": 0, "exploratory": 0,
                                                        "first": entry["label"]})
        counts[entry["label"]] += 1
    return outcomes


def log_state(root: Path) -> dict:
    """``{"state": "absent" | "ok" | "corrupt", "entries", "outcomes"}`` (``message`` when corrupt)."""
    if not (Path(root) / LOG_PATH).is_file():
        return {"state": "absent", "entries": 0, "outcomes": {}}
    try:
        entries = read_log(root)
    except StudyError as error:
        return {"state": "corrupt", "message": error.message, "entries": None, "outcomes": {}}
    return {"state": "ok", "entries": len(entries), "outcomes": summary(entries)}


def status(root: Path) -> dict:
    """The log, the lock and the warnings a reader acts on."""
    root = Path(root)
    log = log_state(root)
    warnings = []
    try:
        view = locked_protocol(root)
        parser = None
    except StudyError as error:
        view, parser = None, {"code": error.code, "message": error.message}
        warnings.append(parser)
    if log["state"] == "corrupt":
        warnings.append({"code": "ANALYSIS_LOG_CORRUPT", "message": log["message"]})
    fields = view["fields"] if view else None
    planned = protocol_outcomes(fields) if fields else None
    entries = read_log(root) if log["state"] == "ok" else []
    labels = {label: sum(1 for entry in entries if entry["label"] == label) for label in LABELS}
    if planned is not None:
        for outcome in planned:
            if log["outcomes"].get(outcome, {}).get("confirmatory", 0) == 0:
                warnings.append({"code": "PROTOCOL_OUTCOME_NOT_ANALYSED", "outcome": outcome,
                                 "message": f"no confirmatory analysis of {outcome} is logged"})
        for outcome, counts in log["outcomes"].items():
            if outcome not in planned:
                warnings.append({"code": "OUTCOME_NOT_IN_PROTOCOL", "outcome": outcome,
                                 "message": f"{outcome} was analysed ({counts['exploratory']} exploratory "
                                            "entries) but is not an outcome of the locked protocol"})
            elif counts["first"] == "exploratory" and counts["confirmatory"]:
                warnings.append({"code": "OUTCOME_ADDED_AFTER_ANALYSIS", "outcome": outcome,
                                 "message": f"{outcome} was analysed as exploratory before the protocol named it: "
                                            "report when it was added and why (HARKing risk)"})
    failed = [entry["id"] for entry in entries if entry.get("exit_code") not in (None, 0)]
    return {"log": {"path": LOG_PATH, **log}, "protocol": records.protocol_state(root),
            "protocol_outcomes": None if fields is None else {"primary": fields.get("primary"),
                                                              "secondary": fields.get("secondary") or []},
            "plan_entries": plan_entries(fields) if fields else None,
            "labels": labels, "failed_runs": failed, "warnings": warnings}


# --------------------------------------------------------------------------- verify's disk read


def _amendment_history(root: Path, lock: dict) -> list[dict]:
    """The primary outcome at the approval and after each amendment: ``{"revision", "sha256",
    "primary", "measure", "amendment"}`` (``primary`` None when those bytes are no longer on disk)."""
    amendments = lock["amendments"]
    steps = [{"revision": amendments[0]["from_revision"], "sha256": amendments[0]["from_sha256"], "amendment": None}
             if amendments else {"revision": lock["revision"], "sha256": lock["sha256"], "amendment": None}]
    for index, amendment in enumerate(amendments, start=1):
        steps.append({"revision": amendment.get("revision"), "sha256": amendment.get("sha256"), "amendment": index,
                      "by": amendment.get("by"), "at": amendment.get("at"), "reason": amendment.get("reason")})
    sources = {}
    for index, step in enumerate(steps):
        data = _locked_bytes(root, step["revision"], step["sha256"]) if step["revision"] and step["sha256"] else None
        if data is not None:
            sources[str(index)] = data
    parsed = parse_protocols(sources)
    for index, step in enumerate(steps):
        fields = parsed.get(str(index))
        primary = next((o for o in (fields or {}).get("outcomes", []) if o["role"] == "primary"), None)
        step["primary"] = fields.get("primary") if fields else None
        step["measure"] = primary["measure"] if primary else None
    return steps


def manuscript_inputs(root: Path) -> dict | None:
    """What `paper_cli.py verify` hands the study checks, read once from disk; ``None`` when the
    workspace has no study protocol (no managed revision, no lock, no analysis log), so an
    applied-AI or review workspace gets no study check at all."""
    root = Path(root)
    try:
        has_lock = (root / records.LOCK_PATH).is_file()
        if not (records.managed_revisions(root) or has_lock or (root / LOG_PATH).is_file()):
            return None
    except OSError:
        return None
    out = {"protocol": None, "locked": None, "history": [], "parser": None, "log": log_state(root)}
    state = records.protocol_state(root)
    out["protocol"] = {key: state.get(key) for key in ("state", "revision", "sha256", "reasons")}
    try:
        view = locked_protocol(root)
        out["locked"] = view["fields"]
        if view["fields"] is not None:
            out["history"] = _amendment_history(root, records.read_lock(root))
    except StudyError as error:
        out["parser"] = {"code": error.code, "message": error.message}
    except Exception as exc:  # noqa: BLE001 -- verify reports the gap; it never aborts on it
        out["parser"] = {"code": "CHECK_FAILED", "message": f"{type(exc).__name__}: {exc}"[:300]}
    return out
