"""Records and side-effect-free readers of consensus rounds and MICMAC (decisions K4 and K5).

The board, the Study panel and the gates import the readers; none of them
writes, creates a directory or calls a model, and none raises on a corrupt
record (it reports ``state: corrupt``). ``consensus_cli.py`` is the only writer.

    study/consensus/panel.json    the panel: anonymised member codes and their expertise, history kept
    study/consensus/plan.json     the consensus rule (rounds, threshold, scale, agreement cut-off),
                                  bound to the study protocol lock's sha256, history kept
    study/consensus/rounds.json   each round's response file, bound by its sha256 and to the plan entry
    study/consensus/micmac.json   each MICMAC analysis, bound to the influence matrix's sha256

Every result is recomputed from the operator's files and is ``stale`` (with
its reasons) when a file, the plan or the protocol changed since it was
recorded. Response comments are counted, never stored, returned or printed.
Every stored or given path is confined to the workspace before any stat: no
absolute path, no traversal, no symbolic link out.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path

from ..empirical import records as study_records
from . import consensus_stats as stats

ConsensusError = study_records.StudyError

SCHEMA = 1
GATE = "G-ROUNDS"
CONSENSUS_DIR = "study/consensus"
PANEL_PATH = f"{CONSENSUS_DIR}/panel.json"
PLAN_PATH = f"{CONSENSUS_DIR}/plan.json"
ROUNDS_PATH = f"{CONSENSUS_DIR}/rounds.json"
MICMAC_PATH = f"{CONSENSUS_DIR}/micmac.json"
ENTRY_META = ("by", "at", "reason")
#: A panel member is a code (P01, expert-3), never a name or an address.
MEMBER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
EMAIL = re.compile(r"[^\s@]+@[^\s@]+")
RESPONSE_COLUMNS = ("member", "item", "rating")
COMMENT_COLUMN = "comment"
MATRIX_VALUES = {"0": 0, "1": 1, "2": 2, "3": 3}


# --------------------------------------------------------------------------- paths


def confined(root: Path, given: str) -> tuple[Path, str]:
    """(resolved path, workspace-relative POSIX path) of ``given``; ``PATH_OUTSIDE_WORKSPACE`` when it
    is absolute, traverses out or names a link out of the workspace. Resolves only; never stats
    the target (a ``ValueError`` from an invalid path propagates)."""
    text = str(given or "").strip()
    workspace = Path(root).resolve()
    if not text or Path(text).is_absolute():
        raise ConsensusError("PATH_OUTSIDE_WORKSPACE", f"{text!r} is not a path relative to the workspace; give "
                                                       "one relative to it, inside it")
    resolved = (workspace / text).resolve()
    if resolved == workspace or not resolved.is_relative_to(workspace):
        raise ConsensusError("PATH_OUTSIDE_WORKSPACE", f"{text} lies outside the workspace (a traversal or a link "
                                                       "out of it); keep the file inside the workspace")
    return resolved, resolved.relative_to(workspace).as_posix()


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except (OSError, ValueError):
        return False


def entry_digest(entry: dict) -> str:
    """sha256 of an entry's canonical JSON: a round binds the exact plan entry it was recorded against."""
    return hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- record files


def _load(root: Path, relative: str, code: str, valid) -> dict:
    """``{"schema", "history"}`` of a record file (empty when absent); ``code`` when malformed and
    ``PATH_OUTSIDE_WORKSPACE`` when the record path leaves the workspace."""
    path, _ = confined(root, relative)
    if not _is_file(path):
        return {"schema": SCHEMA, "history": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConsensusError(code, f"{relative} cannot be read as JSON ({exc})") from None
    if not (isinstance(data, dict) and isinstance(data.get("history"), list)
            and all(isinstance(entry, dict) and valid(entry) for entry in data["history"])):
        raise ConsensusError(code, f"{relative} is not a consensus record: a \"history\" list of well-formed entries")
    return data


def _str(entry: dict, *keys: str) -> bool:
    return all(isinstance(entry.get(key), str) for key in keys)


def _int(value, low: int | None = None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and (low is None or value >= low)


def _valid_plan(entry: dict) -> bool:
    scale = entry.get("scale")
    threshold = entry.get("threshold")
    return (_int(entry.get("rounds"), 1) and isinstance(scale, dict) and _int(scale.get("min"))
            and _int(scale.get("max")) and scale["min"] < scale["max"] and _int(entry.get("agree_from"))
            and scale["min"] < entry["agree_from"] <= scale["max"] and isinstance(threshold, (int, float))
            and not isinstance(threshold, bool) and 0 < threshold <= 100 and _str(entry, "protocol_sha256"))


def read_panel(root: Path) -> dict:
    return _load(root, PANEL_PATH, "PANEL_CORRUPT", lambda e: _str(e, "member") and bool(MEMBER.match(e["member"])))


def read_plan(root: Path) -> dict:
    return _load(root, PLAN_PATH, "PLAN_CORRUPT", _valid_plan)


def read_rounds(root: Path) -> dict:
    return _load(root, ROUNDS_PATH, "ROUNDS_CORRUPT",
                 lambda e: _int(e.get("round"), 1) and _str(e, "file", "sha256", "plan_sha256"))


def read_micmac(root: Path) -> dict:
    return _load(root, MICMAC_PATH, "MICMAC_CORRUPT", lambda e: _str(e, "file", "sha256"))


def latest_rounds(history: list[dict]) -> dict[int, dict]:
    """round number -> its latest entry, in round order."""
    out: dict[int, dict] = {}
    for entry in history:
        out[entry["round"]] = entry
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------- CSV files


def csv_rows(data: bytes, shown: str) -> list[tuple[int, list[str]]]:
    """(line number, stripped cells) of every non-blank record; ``CSV_INVALID`` or ``CSV_EMPTY``.
    Messages name the file and line numbers only, never a cell."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ConsensusError("CSV_INVALID", f"{shown} is not UTF-8 text") from None
    reader = csv.reader(io.StringIO(text))
    rows = []
    try:
        for row in reader:
            if any(cell.strip() for cell in row):
                rows.append((reader.line_num, [cell.strip() for cell in row]))
    except csv.Error:
        raise ConsensusError("CSV_INVALID", f"{shown} is not a well-formed CSV file (line {reader.line_num})") from None
    if not rows:
        raise ConsensusError("CSV_EMPTY", f"{shown} has no header row")
    return rows


def parse_responses(data: bytes, shown: str, members: set[str] | None, scale_min: int,
                    scale_max: int) -> tuple[list[tuple[str, str, int]], int]:
    """The ``(member, item, rating)`` responses of a round file and how many carry a comment.

    The header names ``member``, ``item``, ``rating`` and optionally ``comment``. ``members``
    ``None`` skips the panel check (a reader re-reading bytes validated when recorded). A refusal
    names line numbers and panel codes only, never a cell that could hold a comment."""
    rows = csv_rows(data, shown)
    header = [cell.lower() for cell in rows[0][1]]
    allowed = set(RESPONSE_COLUMNS) | {COMMENT_COLUMN}
    if len(set(header)) != len(header) or not set(RESPONSE_COLUMNS) <= set(header) <= allowed:
        raise ConsensusError("CSV_INVALID", f"{shown}: the header names the columns member, item, rating and "
                                            "optionally comment, each once")
    body = rows[1:]
    if not body:
        raise ConsensusError("CSV_EMPTY", f"{shown} has a header and no response")
    at = {name: header.index(name) for name in header}
    responses, comments, seen = [], 0, {}
    for line, row in body:
        if len(row) != len(header):
            raise ConsensusError("CSV_INVALID", f"{shown} line {line} has {len(row)} cells, the header {len(header)}")
        member, item, rating = (row[at[name]] for name in RESPONSE_COLUMNS)
        if members is not None and member not in members:
            raise ConsensusError("MEMBER_UNKNOWN", f"{shown} line {line}: the member is not a code of the panel "
                                                   f"({', '.join(sorted(members)) or 'empty'}); register members with "
                                                   "`panel add`")
        if not item:
            raise ConsensusError("ITEM_MISSING", f"{shown} line {line}: the item is empty")
        digits = rating[1:] if rating.startswith("-") else rating
        if not (digits.isascii() and digits.isdecimal()):
            raise ConsensusError("RATING_INVALID", f"{shown} line {line}: the rating is not a whole number of the "
                                                   f"scale {scale_min}-{scale_max} (the operator fixes the file; the "
                                                   "core never edits a rating)")
        value = int(rating)
        if not scale_min <= value <= scale_max:
            raise ConsensusError("RATING_OUT_OF_SCALE", f"{shown} line {line}: rating {value} lies outside the "
                                                        f"scale {scale_min}-{scale_max}")
        key = (member, item)
        if key in seen:
            raise ConsensusError("RESPONSE_DUPLICATE", f"{shown} line {line}: member {member} rates an item already "
                                                       f"rated on line {seen[key]}")
        seen[key] = line
        if COMMENT_COLUMN in at and row[at[COMMENT_COLUMN]]:
            comments += 1
        responses.append((member, item, value))
    return responses, comments


def parse_matrix(data: bytes, shown: str, p_value: int) -> tuple[list[str], list[list[int]], int]:
    """(names, matrix, number of P entries) of a square influence matrix CSV: a header row and a first
    column of the same variable names in the same order, entries 0-3 or P (counted as ``p_value``),
    a zero diagonal."""
    rows = csv_rows(data, shown)
    names = rows[0][1][1:]
    if len(names) < 2 or any(not name for name in names) or len(set(names)) != len(names):
        raise ConsensusError("MATRIX_INVALID", f"{shown}: the header row names at least two distinct variables "
                                               "after its first cell")
    body = rows[1:]
    if len(body) != len(names) or any(len(row) != len(names) + 1 for _, row in body):
        raise ConsensusError("MATRIX_NOT_SQUARE", f"{shown}: {len(names)} variables need {len(names)} rows of "
                                                  f"{len(names) + 1} cells (the name, then one entry per variable)")
    matrix, potential = [], 0
    for i, (line, row) in enumerate(body):
        if row[0] != names[i]:
            raise ConsensusError("MATRIX_NAMES_MISMATCH", f"{shown} line {line}: row {i + 1} is {row[0][:40]!r}, "
                                                          f"the header names {names[i]!r} there (same names, same order)")
        values = []
        for j, cell in enumerate(row[1:]):
            if cell.upper() == "P":
                values.append(p_value)
                potential += 1
            elif cell in MATRIX_VALUES:
                values.append(MATRIX_VALUES[cell])
            else:
                raise ConsensusError("MATRIX_ENTRY_INVALID", f"{shown} line {line}: {names[i]} -> {names[j]} is "
                                                             f"{cell[:20]!r}, not 0, 1, 2, 3 or P")
            if i == j and cell != "0":
                raise ConsensusError("DIAGONAL_NONZERO", f"{shown} line {line}: {names[i]} -> {names[i]} is "
                                                         f"{cell!r}; a variable does not influence itself (0)")
        matrix.append(values)
    return names, matrix, potential


# --------------------------------------------------------------------------- panel and plan


def panel_state(root: Path) -> dict:
    """``absent``, ``corrupt`` or ``recorded`` with every member (code, expertise, note, by, at)."""
    try:
        history = read_panel(root)["history"]
    except Exception as error:  # noqa: BLE001 - a reader never raises
        return {"state": "corrupt", "message": getattr(error, "message", str(error)), "members": [], "size": 0}
    if not history:
        return {"state": "absent", "members": [], "size": 0}
    members = [{key: entry.get(key) for key in ("member", "expertise", "note", "by", "at")} for entry in history]
    return {"state": "recorded", "members": members, "size": len(members)}


def _protocol_reasons(root: Path, protocol_sha256: str | None) -> list[str]:
    reasons = []
    try:
        lock = study_records.read_lock(root)
    except ConsensusError:
        return ["protocol-corrupt"]
    if lock is None:
        return ["protocol-absent"]
    if lock["sha256"] != protocol_sha256:
        reasons.append("protocol-amended")
    try:
        current = study_records.protocol_state(root)["state"] == "current"
    except Exception:  # noqa: BLE001 - an unreadable revision is a changed protocol
        current = False
    if not current:
        reasons.append("protocol-changed")
    return reasons


def plan_state(root: Path) -> dict:
    """``absent``, ``corrupt``, or the latest plan entry with ``state`` ``current`` (bound to the
    current protocol lock) or ``stale`` (``reasons``: ``protocol-amended``, ``protocol-changed``,
    ``protocol-absent``, ``protocol-corrupt``), its ``plan_sha256`` and how many ``changes`` it had."""
    root = Path(root)
    try:
        history = read_plan(root)["history"]
        if not history:
            return {"state": "absent"}
        entry = dict(history[-1])
        reasons = _protocol_reasons(root, entry.get("protocol_sha256"))
        warnings = []
        if reasons:
            warnings.append({"code": "PLAN_STALE", "message": f"the consensus plan covers protocol "
                                                              f"{entry.get('protocol_revision')}, which changed since "
                                                              f"({', '.join(reasons)}); the operator records it again"})
        entry.update(state="stale" if reasons else "current", current=not reasons, reasons=reasons,
                     plan_sha256=entry_digest(history[-1]), changes=len(history) - 1, warnings=warnings)
        return entry
    except Exception as error:  # noqa: BLE001 - a reader never raises
        return {"state": "corrupt", "message": getattr(error, "message", str(error))}


# --------------------------------------------------------------------------- rounds


def _file_reasons(root: Path, stored: str, digest: str) -> tuple[list[str], bytes | None]:
    """Why a bound file no longer matches, and its bytes when it still does. The confinement is
    checked before any stat, so a path out of the workspace is never followed."""
    try:
        path, _ = confined(root, stored)
    except ConsensusError:
        return ["file-outside"], None
    except (OSError, ValueError):  # a hand-edited value that is no valid path names no file
        return ["file-missing"], None
    if not _is_file(path):
        return ["file-missing"], None
    try:
        data = path.read_bytes()
    except OSError:
        return ["file-unreadable"], None
    if hashlib.sha256(data).hexdigest() != digest:
        return ["file-changed"], None
    return [], data


def round_results(root: Path, only: int | None = None) -> dict:
    """Every recorded round (its latest entry), with ``state`` ``current`` or ``stale``
    (``reasons``: ``file-outside``, ``file-missing``, ``file-unreadable``, ``file-changed``,
    ``file-invalid``, ``plan-changed``: the plan was recorded again, ``plan-stale``: the
    protocol moved under the plan, ``plan-missing``, ``beyond-plan``) and ``items``: per item n,
    agree, agreement_percent, median, q1, q3, iqr, consensus and ``change`` from the previous
    round, computed with the plan entry the round was recorded against; ``None`` when the file
    no longer holds the recorded bytes. ``only`` keeps one round. Never returns a comment."""
    root = Path(root)
    try:
        history = read_rounds(root)["history"]
    except Exception as error:  # noqa: BLE001
        return {"state": "corrupt", "message": getattr(error, "message", str(error)), "rounds": []}
    if not history:
        return {"state": "absent", "rounds": []}
    plan = plan_state(root)
    try:
        plans = {entry_digest(entry): entry for entry in read_plan(root)["history"]}
    except Exception:  # noqa: BLE001
        plans = {}
    rows, summaries = [], {}
    for k, entry in latest_rounds(history).items():
        reasons, data = _file_reasons(root, entry["file"], entry["sha256"])
        bound = plans.get(entry["plan_sha256"])
        if bound is None:
            reasons.append("plan-missing")
        if plan.get("plan_sha256") != entry["plan_sha256"]:
            reasons.append("plan-changed")
        elif plan.get("state") != "current":
            reasons.append("plan-stale")
        if isinstance(plan.get("rounds"), int) and k > plan["rounds"]:
            reasons.append("beyond-plan")
        items = None
        if data is not None and bound is not None:
            try:
                responses, _ = parse_responses(data, entry["file"], None, bound["scale"]["min"], bound["scale"]["max"])
                items = stats.round_summary(responses, bound["agree_from"], bound["threshold"])
            except Exception:  # noqa: BLE001 - bytes that no longer parse (hand-edited entry)
                reasons.append("file-invalid")
        summaries[k] = items
        row = {key: entry.get(key) for key in ("round", "file", "sha256", "responses", "items", "responders",
                                               "comments", "plan_sha256", "by", "at", "reason")}
        row["items_count"] = row.pop("items")
        row.update(state="stale" if reasons else "current", current=not reasons, reasons=reasons, items=items,
                   consensus_items=None if items is None else sum(1 for item in items if item["consensus"]))
        rows.append(row)
    for row in rows:
        previous = {item["item"]: item for item in summaries.get(row["round"] - 1) or []}
        for item in row["items"] or []:
            before = previous.get(item["item"])
            item["change"] = None if before is None else {"previous_round": row["round"] - 1,
                                                          **stats.change(item, before)}
    if only is not None:
        rows = [row for row in rows if row["round"] == only]
    return {"state": "recorded", "rounds": rows}


def rounds_state(root: Path) -> dict:
    """Gate G-ROUNDS: ``passed`` when the plan is current and every planned round is recorded and
    current. ``state``: ``absent`` (no plan), ``corrupt``, ``open`` or ``passed``; ``missing``
    the planned rounds never recorded, ``stale`` the recorded ones that are not current."""
    root = Path(root)
    try:
        plan = plan_state(root)
        base = {"gate": GATE, "passed": False, "plan": plan, "planned": None, "rounds": [], "missing": [],
                "stale": [], "warnings": []}
        results = round_results(root)
        if results["state"] == "corrupt":
            base["warnings"].append({"code": "ROUNDS_CORRUPT", "message": results["message"]})
            return base | {"state": "corrupt"}
        if plan["state"] == "corrupt":
            base["warnings"].append({"code": "PLAN_CORRUPT", "message": plan["message"]})
            return base | {"state": "corrupt"}
        if plan["state"] == "absent":
            base["warnings"].append({"code": "ROUNDS_PLAN_ABSENT", "message": "no consensus plan recorded yet "
                                                                              "(`plan record --by`)"})
            return base | {"state": "absent"}
        planned = plan["rounds"]
        by_round = {row["round"]: row for row in results["rounds"]}
        missing = [k for k in range(1, planned + 1) if k not in by_round]
        stale = [{"round": row["round"], "reasons": row["reasons"]} for row in results["rounds"] if not row["current"]]
        warnings = list(plan["warnings"])
        if missing:
            warnings.append({"code": "ROUNDS_MISSING", "message": f"planned rounds not recorded: "
                                                                  f"{', '.join(map(str, missing))}"})
        for item in stale:
            warnings.append({"code": "ROUND_STALE", "message": f"round {item['round']} is stale "
                                                               f"({', '.join(item['reasons'])}); the operator records "
                                                               "it again"})
        passed = plan["current"] and not missing and not any(item["round"] <= planned for item in stale)
        rounds = [{key: row[key] for key in ("round", "state", "reasons", "file", "responders", "items_count",
                                             "consensus_items")} for row in results["rounds"]]
        return base | {"state": "passed" if passed else "open", "passed": passed, "planned": planned,
                       "rounds": rounds, "missing": missing, "stale": stale, "warnings": warnings}
    except Exception as error:  # noqa: BLE001 - a reader never raises
        return {"gate": GATE, "state": "corrupt", "passed": False, "message": f"{type(error).__name__}: {error}",
                "rounds": [], "missing": [], "stale": [],
                "warnings": [{"code": "ROUNDS_CORRUPT", "message": f"{type(error).__name__}: {error}"}]}


# --------------------------------------------------------------------------- MICMAC


def micmac_state(root: Path) -> dict:
    """``absent``, ``corrupt``, or the latest analysis with ``state`` ``current`` or ``stale``
    (``reasons``: ``file-outside``, ``file-missing``, ``file-unreadable``, ``file-changed``)."""
    root = Path(root)
    try:
        history = read_micmac(root)["history"]
        if not history:
            return {"state": "absent"}
        entry = dict(history[-1])
        reasons, _ = _file_reasons(root, entry["file"], entry["sha256"])
        warnings = []
        if reasons:
            warnings.append({"code": "MICMAC_STALE", "message": f"the MICMAC analysis of {entry['file']} is stale "
                                                                f"({', '.join(reasons)}); compute it again"})
        entry.update(state="stale" if reasons else "current", current=not reasons, reasons=reasons,
                     records=len(history), warnings=warnings)
        return entry
    except Exception as error:  # noqa: BLE001 - a reader never raises
        return {"state": "corrupt", "message": getattr(error, "message", str(error))}


# --------------------------------------------------------------------------- everything


def consensus_status(root: Path) -> dict:
    """The panel, the plan, gate G-ROUNDS, the MICMAC analysis and every warning."""
    panel, plan, rounds, micmac = panel_state(root), plan_state(root), rounds_state(root), micmac_state(root)
    warnings = []
    if panel["state"] == "corrupt":
        warnings.append({"code": "PANEL_CORRUPT", "message": panel["message"]})
    if rounds["state"] != "absent":  # a workspace without a consensus plan owes nothing here
        warnings.extend(rounds["warnings"])
    if micmac["state"] == "corrupt":
        warnings.append({"code": "MICMAC_CORRUPT", "message": micmac["message"]})
    elif micmac["state"] == "stale":
        warnings.extend(micmac["warnings"])
    return {"panel": panel, "plan": plan, "rounds": rounds, "micmac": micmac, "warnings": warnings}
