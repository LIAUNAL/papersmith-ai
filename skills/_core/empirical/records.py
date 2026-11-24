"""Side-effect-free readers of an empirical study's operator records.

The analysis log, the dashboard and the checklist engine import these; none
of them writes, creates a directory or calls a model. ``study_cli.py`` is the
only writer of these records (``analysis_cli.py`` writes the analysis log).

    study/protocol.lock.json   gate G-STUDY-PROTOCOL: the approved revision of
                               protocol/study-protocol-<slug>-vNN.md, its sha256
                               and the amendments that moved it
    study/ethics.json          the ethics approval (or why none applies)
    study/registration.json    the study registration (or why none applies)
    study/allocation.json      gate G-ALLOCATION: the operator's allocation list,
                               bound by its sha256 and row count, never its content

The ethics, registration and allocation entries are bound to the lock's sha256:
after an amendment they are stale, which is a warning (decision D5), never a
refusal. The allocation reader hashes the operator's allocation list and counts
its rows; it never returns, prints or alters what the list holds (decision J2).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA = 1
GATE = "G-STUDY-PROTOCOL"
PROTOCOL_DIR = "protocol"
LOCK_PATH = "study/protocol.lock.json"
RECORD_PATHS = {"ethics": "study/ethics.json", "registration": "study/registration.json"}
ALLOCATION_PATH = "study/allocation.json"
ALLOCATION_GATE = "G-ALLOCATION"
# The engine writes these bytes first in every managed revision (profile.ts `artifact.marker`).
MANAGED_MARKER = b"<!-- proposal-workspace:artifact:v1 -->\n"
REVISION_NAME = re.compile(r"^study-protocol-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)-v(?P<version>\d{2,})\.md$")


class StudyError(Exception):
    """A typed refusal: ``code`` is an uppercase identifier, ``message`` says what to do."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision_version(relative: str) -> int | None:
    match = REVISION_NAME.match(Path(relative).name)
    return int(match.group("version")) if match else None


def managed_revisions(root: Path) -> list[tuple[int, str]]:
    """(version, ``protocol/<name>``) of every managed revision, oldest first."""
    folder = Path(root) / PROTOCOL_DIR
    if not folder.is_dir():
        return []
    found = []
    for path in folder.iterdir():
        match = REVISION_NAME.match(path.name)
        if match and path.is_file() and path.read_bytes().startswith(MANAGED_MARKER):
            found.append((int(match.group("version")), f"{PROTOCOL_DIR}/{path.name}"))
    return sorted(found)


def latest_revision(root: Path) -> str | None:
    """The managed revision with the highest version; refuses two lineages tied at it."""
    revisions = managed_revisions(root)
    if not revisions:
        return None
    top = revisions[-1][0]
    tied = [name for version, name in revisions if version == top]
    if len(tied) > 1:
        raise StudyError("REVISION_AMBIGUOUS", f"{len(tied)} managed revisions share version v{top:02d} "
                                               f"({', '.join(tied)}); name one with --revision")
    return tied[0]


def read_lock(root: Path) -> dict | None:
    """The lock, ``None`` when absent; ``PROTOCOL_LOCK_CORRUPT`` when it is not a lock."""
    path = Path(root) / LOCK_PATH
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StudyError("PROTOCOL_LOCK_CORRUPT", f"{LOCK_PATH} cannot be read as JSON ({exc})") from None
    if not (isinstance(data, dict) and isinstance(data.get("revision"), str) and isinstance(data.get("sha256"), str)
            and isinstance(data.get("amendments"), list)):
        raise StudyError("PROTOCOL_LOCK_CORRUPT", f"{LOCK_PATH} is not a protocol lock: a revision, its sha256 "
                                                  "and an amendments list")
    return data


def protocol_state(root: Path) -> dict:
    """``state``: ``absent`` (never approved), ``current``, ``changed`` (``reasons``: the locked
    revision was edited or removed, or a newer managed revision exists) or ``corrupt``."""
    root = Path(root)
    try:
        lock = read_lock(root)
    except StudyError as error:
        return {"state": "corrupt", "message": error.message}
    if lock is None:
        return {"state": "absent"}
    reasons = []
    path = root / lock["revision"]
    if not path.is_file():
        reasons.append("revision-missing")
    elif sha256(path) != lock["sha256"]:
        reasons.append("revision-edited")
    locked_version = revision_version(lock["revision"]) or 0
    newer = [name for version, name in managed_revisions(root) if version > locked_version]
    if newer:
        reasons.append("newer-revision")
    return {"state": "changed" if reasons else "current", "reasons": reasons, "revision": lock["revision"],
            "sha256": lock["sha256"], "approved_by": lock.get("approved_by"), "approved_at": lock.get("approved_at"),
            "amendments": len(lock["amendments"]), "latest": newer[-1] if newer else lock["revision"]}


def require_current_lock(root: Path) -> dict:
    """The lock when it is current; ``PROTOCOL_NOT_APPROVED``, ``PROTOCOL_LOCK_CORRUPT`` or
    ``PROTOCOL_CHANGED`` otherwise."""
    lock = read_lock(root)
    if lock is None:
        raise StudyError("PROTOCOL_NOT_APPROVED", "the operator has not approved the study protocol (gate "
                                                  f"{GATE}): run `protocol approve --by <name>` after reading it")
    state = protocol_state(root)
    if state["state"] != "current":
        raise StudyError("PROTOCOL_CHANGED", f"the study protocol changed after its approval ({', '.join(state['reasons'])}); "
                                             "record the change with `protocol amend --by <name> --reason <why>`")
    return lock


def _read_history(root: Path, relative: str, code: str) -> dict:
    path = Path(root) / relative
    if not path.is_file():
        return {"schema": SCHEMA, "history": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StudyError(code, f"{relative} cannot be read as JSON ({exc})") from None
    if not (isinstance(data, dict) and isinstance(data.get("history"), list)
            and all(isinstance(entry, dict) for entry in data["history"])):
        raise StudyError(code, f"{relative} is not a record: a \"history\" list of objects")
    return data


def read_record(root: Path, gate: str) -> dict:
    """The gate's record file, an empty history when absent; ``<GATE>_CORRUPT`` when malformed."""
    if gate not in RECORD_PATHS:
        raise ValueError(f"unknown gate {gate!r}; expected one of {sorted(RECORD_PATHS)}")
    return _read_history(root, RECORD_PATHS[gate], f"{gate.upper()}_CORRUPT")


def read_allocation(root: Path) -> dict:
    """``study/allocation.json``, an empty history when absent; ``ALLOCATION_CORRUPT`` when malformed."""
    return _read_history(root, ALLOCATION_PATH, "ALLOCATION_CORRUPT")


def count_rows(data: bytes) -> int:
    """The non-blank lines of an allocation list (a header line counts); its content is never kept."""
    return sum(1 for line in data.splitlines() if line.strip())


def allocation_state(root: Path) -> dict:
    """``{"state": "absent"}`` when never recorded, ``{"state": "corrupt", "message"}``, or the latest
    entry with ``state`` ``current`` (the file's bytes unchanged and the lock current and the one it
    is bound to) or ``stale``, ``current``, ``reasons`` (``file-missing``, ``file-unreadable``,
    ``file-changed``, ``file-outside``: the stored path leaves the workspace and is never hashed,
    ``protocol-amended``: the lock moved since; ``protocol-changed``: the protocol
    is not current), ``records`` and ``warnings``. Hashes the file; never returns its content."""
    root = Path(root)
    try:
        history = read_allocation(root)["history"]
    except StudyError as error:
        return {"state": "corrupt", "message": error.message}
    if not history:
        return {"state": "absent"}
    entry = dict(history[-1])
    reasons = []
    stored = str(entry.get("file") or "")
    # The same confinement as `allocation record`: a stored path that is absolute, traverses
    # out or names a link pointing out of the workspace is never followed nor hashed.
    workspace = root.resolve()
    path = (root / stored).resolve() if stored else root
    if stored and (Path(stored).is_absolute() or not path.is_relative_to(workspace)):
        reasons.append("file-outside")
    elif not stored or not path.is_file():
        reasons.append("file-missing")
    else:
        try:
            if sha256(path) != entry.get("sha256"):
                reasons.append("file-changed")
        except OSError:
            reasons.append("file-unreadable")
    try:
        lock = read_lock(root)
    except StudyError:
        lock = None
    if lock is not None and lock["sha256"] != entry.get("protocol_sha256"):
        reasons.append("protocol-amended")
    if protocol_state(root)["state"] != "current":
        reasons.append("protocol-changed")
    warnings = []
    if reasons:
        warnings.append({"code": "ALLOCATION_STALE",
                         "message": f"the allocation record of {entry.get('file')} is stale ({', '.join(reasons)}); "
                                    "the operator records it again against the current file and lock"})
    entry.update(state="stale" if reasons else "current", current=not reasons, reasons=reasons,
                 records=len(history), warnings=warnings)
    return entry


def _warnings(gate: str, entry: dict, current: bool) -> list[dict]:
    out = []
    if not current:
        out.append({"code": f"{gate.upper()}_STALE",
                    "message": f"the {gate} record covers protocol {entry.get('protocol_revision')}, "
                               "amended since; the operator records it again against the current lock"})
    if gate == "registration" and entry.get("status") == "registered":
        if entry.get("retrospective") is True:
            out.append({"code": "REGISTRATION_RETROSPECTIVE",
                        "message": f"registered on {entry.get('date')}, after the first enrolment on "
                                   f"{entry.get('first_enrolment')} (ICMJE asks for registration before it)"})
        elif entry.get("retrospective") is None:
            out.append({"code": "FIRST_ENROLMENT_UNKNOWN",
                        "message": "no first-enrolment date recorded: whether the registration was prospective "
                                   "cannot be checked (`--first-enrolment`)"})
    return out


def gate_state(root: Path, gate: str) -> dict | None:
    """``None`` when ``gate`` (``ethics`` or ``registration``) was never recorded; otherwise
    its latest entry with ``current`` (bound to the lock's sha256) and ``warnings``, or
    ``{"state": "corrupt"}``."""
    try:
        history = read_record(root, gate)["history"]
    except StudyError as error:
        return {"state": "corrupt", "message": error.message}
    if not history:
        return None
    entry = dict(history[-1])
    try:
        lock = read_lock(root)
    except StudyError:
        lock = None
    current = lock is not None and entry.get("protocol_sha256") == lock["sha256"]
    entry.update(state="recorded", current=current, records=len(history), warnings=_warnings(gate, entry, current))
    return entry


def study_status(root: Path) -> dict:
    """The protocol, ethics, registration and allocation states and every warning, in that order.
    An absent allocation is not a warning: only an intervention study allocates."""
    protocol = protocol_state(root)
    gates = {gate: gate_state(root, gate) for gate in RECORD_PATHS}
    warnings = []
    if protocol["state"] == "absent":
        warnings.append({"code": "PROTOCOL_NOT_APPROVED", "message": f"gate {GATE} has not been passed"})
    elif protocol["state"] == "corrupt":
        warnings.append({"code": "PROTOCOL_LOCK_CORRUPT", "message": protocol["message"]})
    elif protocol["state"] == "changed":
        warnings.append({"code": "PROTOCOL_CHANGED",
                         "message": f"the protocol changed since its approval ({', '.join(protocol['reasons'])})"})
    for gate, state in gates.items():
        if state is None:
            if protocol["state"] != "absent":
                warnings.append({"code": f"{gate.upper()}_ABSENT", "message": f"no {gate} record yet"})
        elif state["state"] == "corrupt":
            warnings.append({"code": f"{gate.upper()}_CORRUPT", "message": state["message"]})
        else:
            warnings.extend(state["warnings"])
    allocation = allocation_state(root)
    if allocation["state"] == "corrupt":
        warnings.append({"code": "ALLOCATION_CORRUPT", "message": allocation["message"]})
    elif allocation["state"] != "absent":
        warnings.extend(allocation["warnings"])
    return {"protocol": protocol, **gates, "allocation": allocation, "warnings": warnings}
