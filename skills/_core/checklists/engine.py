"""Reporting-guideline checklist engine (paper-type-lines S7, decisions D11-D13).

A guideline is one data file, ``guidelines/<id>.json``: its id, name, version,
URL and items. Each item stores its number, a short PARAPHRASED topic, the
blocks or sections that report it for each paper line, deterministic evidence
rules and, when a reader must decide, the question that reader answers. The
item text of a guideline is never stored (copyright; see README.md).

The engine evaluates a workspace into one result per item:

    satisfied        every rule passed and the item has no judgment question
                     (only items whose content a rule fully checks)
    missing          a target is not written (or does not exist in this
                     workspace), a record is absent, or a content rule failed
    needs-judgment   everything checkable passed; a reader answers
                     ``question``. Never promoted to satisfied by the engine.

Each result also carries ``presence`` (the targets, records, files, commands
and declarations alone), which for PRISMA 2020 equals ``review_cli.py
checklist``'s satisfied/owed verdict on the same workspace.

Rule kinds (the predicate vocabulary):

    text         implicit: every target of the item's line holds text
    file         {"path"}: the file exists
    record       {"path", "pointer"?, "field"?, "values"?}: the JSON document
                 (or JSONL rows) exists and is non-empty; with ``pointer`` the
                 dotted path holds a non-empty value; with ``field``/``values``
                 the rows' ``field`` covers every value
    declaration  {"name"}: paper-writing records that declaration
    command      {"script", "argv", "expect"}: a workspace skill CLI
                 (``skills/**.py``) run with ``argv`` (``{root}`` substituted)
                 prints a JSON object whose keys equal ``expect``
    number       {"path", "pointer", "in"?}: the number the record holds at
                 ``pointer`` appears in the text of the targets
    term         {"any", "in"?}: one of the terms appears in the text of the
                 targets (case, accents and dashes folded, whole words)

``text``, ``file``, ``record``, ``declaration`` and ``command`` are presence
rules; ``number`` and ``term`` are content rules. ``in`` defaults to the
item's targets for the workspace's line.

Blocks and declarations are read the way ``review_cli.py`` reads them: the
workspace's own ``skills/paper-writing/scripts/paper_cli.py status`` and
``phases`` run as subprocesses (the same version of paper-writing the
workspace writes with, no import of its modules into this process), and a
block's text is the slice of ``paper/main.tex`` between its markers at the
region ``status`` reports. Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = 1
GUIDELINES_DIR = Path(__file__).resolve().parent / "guidelines"
#: Copyright guard: a topic is a short label and a question a one-line
#: paraphrase, never the guideline's item text.
TOPIC_MAX = 60
QUESTION_MAX = 200
DEFAULT_LINE = "experimental"
STATUSES = ("satisfied", "missing", "needs-judgment")
PRESENCE_KINDS = ("file", "record", "declaration", "command")
CONTENT_KINDS = ("number", "term")
RULE_KEYS = {
    "file": ({"path"}, set()),
    "record": ({"path"}, {"pointer", "field", "values"}),
    "declaration": ({"name"}, set()),
    "command": ({"script", "argv", "expect"}, set()),
    "number": ({"path", "pointer"}, {"in"}),
    "term": ({"any"}, {"in"}),
}
ITEM_KEYS = {"number", "section", "topic", "targets", "evidence", "question"}
TOP_KEYS = {"schema", "id", "name", "version", "url", "citation", "item_count", "items", "lines"}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_TARGET_RE = re.compile(r"^[a-z0-9][a-z0-9-]*(\.[A-Za-z0-9_-]+)?$")
#: The digest paper-writing records for an opened block that holds no text.
_EMPTY_BODY = hashlib.sha256(b"").hexdigest()
COMMAND_TIMEOUT = 120


class ChecklistRefusal(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class WorkspaceState:
    """What the engine reads from a workspace: its paper line, the blocks of
    ``paper/main.tex`` with their text, the recorded declarations and the
    sections (with their block ids) its ``sections/`` contracts declare."""

    root: Path
    line: str
    paper_available: bool
    blocks: dict[str, str]
    declarations: set[str]
    sections: dict[str, set[str]]
    notes: list[str] = field(default_factory=list)
    #: Why the block reader failed on a scaffolded paper (``None``: it did not fail).
    paper_error: str | None = None
    #: Why the declaration reader failed (``None``: it did not fail).
    declarations_error: str | None = None


# --------------------------------------------------------------------------- data files


def _relative_path_problem(value) -> str | None:
    if not isinstance(value, str) or not value or value.startswith(("/", "\\")) or ":" in value:
        return f"{value!r} is not a relative path inside the workspace"
    if any(part in ("..", "") for part in value.replace("\\", "/").split("/")):
        return f"{value!r} is not a relative path inside the workspace"
    return None


def _rule_problems(where: str, rule) -> list[str]:
    if not isinstance(rule, dict):
        return [f"{where}: a rule is not an object"]
    kind = rule.get("kind")
    if kind not in RULE_KEYS:
        return [f"{where}: unknown rule kind {kind!r}"]
    required, optional = RULE_KEYS[kind]
    problems = [f"{where}: {kind} rule lacks {key!r}" for key in sorted(required - set(rule))]
    problems += [f"{where}: {kind} rule has unknown key {key!r}"
                 for key in sorted(set(rule) - required - optional - {"kind"})]
    if "path" in rule and (problem := _relative_path_problem(rule["path"])):
        problems.append(f"{where}: {problem}")
    if kind == "command":
        script = rule.get("script")
        if (_relative_path_problem(script) or not script.startswith("skills/") or not script.endswith(".py")):
            problems.append(f"{where}: command script must be a .py file under skills/ ({script!r})")
        if not isinstance(rule.get("argv"), list) or not all(isinstance(a, str) for a in rule.get("argv", [])):
            problems.append(f"{where}: command argv must be a list of strings")
        if not isinstance(rule.get("expect"), dict) or not rule.get("expect"):
            problems.append(f"{where}: command expect must be a non-empty object")
    if kind == "term":
        terms = rule.get("any")
        if not isinstance(terms, list) or not terms or not all(isinstance(t, str) and t.strip() for t in terms):
            problems.append(f"{where}: term rule 'any' must be a non-empty list of terms")
    if kind == "record" and ("field" in rule) != ("values" in rule):
        problems.append(f"{where}: record rule takes 'field' and 'values' together")
    if kind == "record" and "values" in rule:
        values = rule["values"]
        if (not isinstance(values, list) or not values
                or not all(isinstance(v, (str, int, float)) and not isinstance(v, bool) for v in values)):
            problems.append(f"{where}: record rule 'values' must be a non-empty list of strings or numbers")
    for key in ("pointer", "field", "name"):
        if key in rule and (not isinstance(rule[key], str) or not rule[key].strip()):
            problems.append(f"{where}: {key} must be a non-empty string")
    if "in" in rule and (not isinstance(rule["in"], list) or not rule["in"]
                         or not all(isinstance(t, str) and _TARGET_RE.match(t) for t in rule["in"])):
        problems.append(f"{where}: 'in' must be a non-empty list of section or section.block names")
    return problems


def validate_guideline(data, *, expected_id: str | None = None) -> list[str]:
    """Every problem with a guideline data file; an empty list means valid."""
    if not isinstance(data, dict):
        return ["the guideline is not a JSON object"]
    problems = [f"missing key {key!r}" for key in ("schema", "id", "name", "version", "url", "item_count", "items")
                if key not in data]
    problems += [f"unknown key {key!r}" for key in sorted(set(data) - TOP_KEYS)]
    if data.get("schema") != SCHEMA:
        problems.append(f"schema is {data.get('schema')!r}, expected {SCHEMA}")
    gid = data.get("id")
    if not isinstance(gid, str) or not _ID_RE.match(gid):
        problems.append(f"id {gid!r} is not a lowercase slug")
    elif expected_id is not None and gid != expected_id:
        problems.append(f"id {gid!r} does not match its file name {expected_id!r}")
    for key in ("name", "version"):
        if not isinstance(data.get(key), str) or not data.get(key, "").strip():
            problems.append(f"{key} must be a non-empty string")
    if not isinstance(data.get("url"), str) or not data["url"].startswith(("https://", "http://")):
        problems.append("url must be an http(s) URL")
    if "lines" in data and (not isinstance(data["lines"], list)
                            or not all(isinstance(line, str) and _ID_RE.match(line) for line in data["lines"])):
        problems.append("lines must be a list of paper line ids")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return problems + ["items must be a non-empty list"]
    if data.get("item_count") != len(items):
        problems.append(f"item_count {data.get('item_count')!r} but {len(items)} items")
    seen: set = set()
    for index, entry in enumerate(items, 1):
        where = f"item {entry.get('number', f'#{index}') if isinstance(entry, dict) else f'#{index}'}"
        if not isinstance(entry, dict):
            problems.append(f"{where}: not an object")
            continue
        problems += [f"{where}: unknown key {key!r}" for key in sorted(set(entry) - ITEM_KEYS)]
        number = entry.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            problems.append(f"{where}: number must be a positive integer")
        elif number in seen:
            problems.append(f"{where}: number {number} repeats")
        else:
            seen.add(number)
            if number != index:
                problems.append(f"{where}: items are not numbered 1..n in order (position {index})")
        for key, limit in (("section", TOPIC_MAX), ("topic", TOPIC_MAX)):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{where}: {key} must be a non-empty string")
            elif len(value) > limit:
                problems.append(f"{where}: {key} is longer than {limit} characters (paraphrase, never item text)")
        question = entry.get("question")
        if question is not None and (not isinstance(question, str) or not question.strip()):
            problems.append(f"{where}: question must be a non-empty string")
        elif isinstance(question, str) and len(question) > QUESTION_MAX:
            problems.append(f"{where}: question is longer than {QUESTION_MAX} characters")
        targets = entry.get("targets")
        if not isinstance(targets, dict) or not targets:
            problems.append(f"{where}: targets must map a paper line (or 'default') to its targets")
        else:
            for line, names in targets.items():
                if not isinstance(names, list) or not names or not all(
                        isinstance(n, str) and _TARGET_RE.match(n) for n in names):
                    problems.append(f"{where}: targets[{line!r}] must be a non-empty list of section names")
        rules = entry.get("evidence", [])
        if not isinstance(rules, list):
            problems.append(f"{where}: evidence must be a list")
            rules = []
        for rule in rules:
            problems += _rule_problems(where, rule)
        has_content = any(isinstance(r, dict) and r.get("kind") in CONTENT_KINDS for r in rules)
        if not has_content and question is None:
            problems.append(f"{where}: neither a content rule nor a question (presence alone never satisfies)")
    return problems


def _guideline_path(gid: str, directory: Path | None) -> Path:
    if not isinstance(gid, str) or not _ID_RE.match(gid):
        raise ChecklistRefusal("GUIDELINE_UNKNOWN", f"{gid!r} is not a guideline id (see `checklist_cli.py list`)")
    path = (directory or GUIDELINES_DIR) / f"{gid}.json"
    if not path.is_file():
        known = ", ".join(sorted(p.stem for p in (directory or GUIDELINES_DIR).glob("*.json"))) or "none"
        raise ChecklistRefusal("GUIDELINE_UNKNOWN", f"no guideline {gid!r}; known: {known}")
    return path


def load_guideline(gid: str, *, directory: Path | None = None) -> dict:
    path = _guideline_path(gid, directory)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ChecklistRefusal("GUIDELINE_INVALID", f"{path} cannot be read as JSON ({exc})") from None
    problems = validate_guideline(data, expected_id=gid)
    if problems:
        raise ChecklistRefusal("GUIDELINE_INVALID", f"{path}: " + "; ".join(problems))
    return data


def list_guidelines(*, directory: Path | None = None) -> list[dict]:
    listing = []
    for path in sorted((directory or GUIDELINES_DIR).glob("*.json")):
        data = load_guideline(path.stem, directory=directory)
        listing.append({"id": data["id"], "name": data["name"], "version": data["version"], "url": data["url"],
                        "items": len(data["items"])})
    return listing


# --------------------------------------------------------------------------- workspace reading


def paper_line(root: Path) -> str:
    """The paper line from ``.papersmith/config.json`` (absent: experimental)."""
    try:
        data = json.loads((root / ".papersmith" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_LINE
    kind = data.get("paper_kind") if isinstance(data, dict) else None
    return kind if isinstance(kind, str) and kind else DEFAULT_LINE


_PAPER_CLI = Path("skills") / "paper-writing" / "scripts" / "paper_cli.py"


def _paper_cli(root: Path, verb: str) -> tuple[dict | None, str | None]:
    """``review_cli._paper_cli``'s contract, copied rather than imported
    (review_cli is a workspace skill script; ``PrismaParityTests`` pins the
    two together): the workspace's own paper_cli, run only once
    ``paper/main.tex`` exists.

    Answers ``(payload, None)`` for an ``ok`` payload, ``(None, None)`` when
    the paper is not scaffolded, and ``(None, reason)`` when the reader failed
    on a scaffolded paper (crash, timeout, output that is not JSON, a non-ok
    answer), so a failure is never reported as "not scaffolded"."""
    if not (root / _PAPER_CLI).is_file() or not (root / "paper" / "main.tex").is_file():
        return None, None
    try:
        completed = subprocess.run([sys.executable, str(root / _PAPER_CLI), verb], cwd=root, capture_output=True,
                                   text=True, timeout=COMMAND_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"paper_cli.py {verb} failed ({type(exc).__name__}: {exc})"
    try:
        payload = json.loads(completed.stdout)
    except ValueError:
        tail = (completed.stderr or completed.stdout).strip().splitlines()[-1:] or [""]
        return None, (f"paper_cli.py {verb} failed (exit {completed.returncode}, output is not JSON"
                      + (f": {tail[0][:160]}" if tail[0] else "") + ")")
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        why = (payload.get("message") or payload.get("error")) if isinstance(payload, dict) else None
        return None, f"paper_cli.py {verb} failed (not an ok answer" + (f": {str(why)[:160]}" if why else "") + ")"
    return payload, None


def _block_body(region: bytes) -> str:
    """The text between a block's begin-marker line and its end-marker line."""
    _, _, rest = region.partition(b"\n")
    rest = rest.rstrip(b"\r\n")
    cut = rest.rfind(b"\n")
    return rest[:cut + 1].decode("utf-8", errors="replace") if cut >= 0 else ""


def contract_sections(root: Path) -> dict[str, set[str]]:
    """Section id -> block ids, from the JSON front matter of ``sections/*.md``."""
    sections: dict[str, set[str]] = {}
    for path in sorted((root / "sections").glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
            head = json.loads(text.split("\n---\n", 1)[0].removeprefix("---\n")) if text.startswith("---\n") else {}
        except (OSError, ValueError):
            continue
        section = head.get("section") if isinstance(head, dict) else None
        listed = head.get("blocks", []) if isinstance(head, dict) else []
        if isinstance(section, str) and isinstance(listed, list):
            blocks = {b.get("id") for b in listed if isinstance(b, dict) and isinstance(b.get("id"), str)}
            sections.setdefault(section, set()).update(blocks)
    return sections


def read_workspace(root: Path) -> WorkspaceState:
    root = Path(root).resolve()
    if not (root / ".papersmith").is_dir():
        raise ChecklistRefusal("NOT_A_WORKSPACE", f"{root} is not a papersmith workspace (no .papersmith/)")
    notes: list[str] = []
    blocks: dict[str, str] = {}
    declarations: set[str] = set()
    declarations_error = None
    status, paper_error = _paper_cli(root, "status")
    if paper_error:
        notes.append(f"{paper_error}; the blocks of paper/main.tex could not be read")
    elif status is None:
        notes.append("paper/main.tex is not scaffolded yet (`/paper-writing`), so every item still owes its text")
    else:
        data = (root / "paper" / "main.tex").read_bytes()
        for block in status.get("blocks", []):
            start, end = block.get("region", [0, 0])
            blocks[block["id"]] = "" if block.get("digest") == _EMPTY_BODY else _block_body(data[start:end])
        phases, declarations_error = _paper_cli(root, "phases")
        if declarations_error:
            notes.append(f"{declarations_error}; the recorded declarations could not be read")
        declarations = set(((phases or {}).get("declared") or {}).get("declarations") or [])
    return WorkspaceState(root=root, line=paper_line(root), paper_available=status is not None, blocks=blocks,
                          declarations=declarations, sections=contract_sections(root), notes=notes,
                          paper_error=paper_error, declarations_error=declarations_error)


# --------------------------------------------------------------------------- predicates


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[-‐-―~]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _target_text(state: WorkspaceState, target: str) -> str:
    if "." in target:
        return state.blocks.get(target, "")
    return "\n".join(text for bid, text in state.blocks.items() if bid.startswith(target + "."))


def _check_target(state: WorkspaceState, target: str) -> dict:
    section, _, block = target.partition(".")
    entry = {"rule": "text", "target": target}
    if block:
        known = block in state.sections.get(section, set()) or target in state.blocks
    else:
        known = section in state.sections or any(b.startswith(section + ".") for b in state.blocks)
    # Written means a non-empty body, the test review_cli applies (its digest
    # differs from the empty body's), so the PRISMA presence verdicts agree.
    written = bool(state.blocks.get(target)) if block else any(
        text for bid, text in state.blocks.items() if bid.startswith(section + "."))
    if written:
        return {**entry, "ok": True, "detail": "written"}
    if state.paper_error:
        detail = state.paper_error
    elif not state.paper_available:
        detail = "paper/main.tex is not scaffolded yet"
    elif not known:
        what = f"no block '{target}'" if block else f"no section '{section}'"
        declared = ", ".join(sorted(state.sections)) or "none"
        detail = f"unresolved target: this workspace has {what} (sections/ declares: {declared})"
    else:
        detail = "not written yet"
    return {**entry, "ok": False, "detail": detail}


def _read_rows(path: Path) -> list:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                raise ValueError(f"line {number} is not JSON") from None
    return rows


def _pointer(value, pointer: str):
    for part in pointer.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise KeyError(pointer)
    return value


def _empty(value) -> bool:
    return value is None or (isinstance(value, (str, list, dict)) and not (value.strip() if isinstance(value, str) else value))


def _rule_label(rule: dict) -> str:
    kind = rule["kind"]
    if kind == "record":
        label = f"record:{rule['path']}"
        if "pointer" in rule:
            label += f"#{rule['pointer']}"
        if "field" in rule:
            label += f"[{rule['field']}={','.join(map(str, rule['values']))}]"
        return label
    if kind == "number":
        return f"number:{rule['path']}#{rule['pointer']}"
    if kind == "term":
        return "term:" + "|".join(rule["any"])
    if kind == "declaration":
        return f"declaration:{rule['name']}"
    if kind == "command":
        return f"command:{rule['script']}"
    return f"file:{rule['path']}"


def _record(root: Path, rule: dict) -> tuple[bool, str]:
    path = root / rule["path"]
    if not path.is_file():
        return False, f"{rule['path']} does not exist"
    try:
        document = _read_rows(path) if path.suffix == ".jsonl" else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, f"{rule['path']} cannot be read: {exc}"
    if "field" in rule:
        rows = document if isinstance(document, list) else []
        seen = {row.get(rule["field"]) for row in rows if isinstance(row, dict)}
        owed = [v for v in rule["values"] if v not in seen]
        return (not owed, "every value present" if not owed
                else f"{rule['path']} has no row with {rule['field']} = {', '.join(map(str, owed))}")
    if "pointer" in rule:
        try:
            value = _pointer(document, rule["pointer"])
        except KeyError:
            return False, f"{rule['path']} has no {rule['pointer']}"
        return (not _empty(value), "non-empty" if not _empty(value) else f"{rule['path']}#{rule['pointer']} is empty")
    return (not _empty(document), "non-empty" if not _empty(document) else f"{rule['path']} is empty")


def _command(root: Path, rule: dict, cache: dict) -> tuple[bool, str]:
    script = root / rule["script"]
    if not script.is_file():
        return False, f"{rule['script']} does not exist in this workspace"
    argv = [arg.replace("{root}", str(root)) for arg in rule["argv"]]
    key = (rule["script"], tuple(argv))
    if key not in cache:
        try:
            completed = subprocess.run([sys.executable, str(script), *argv], cwd=root, capture_output=True,
                                       text=True, timeout=COMMAND_TIMEOUT)
            cache[key] = json.loads(completed.stdout)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            cache[key] = exc
    payload = cache[key]
    if not isinstance(payload, dict):
        return False, f"{rule['script']} did not answer one JSON object ({payload})"
    for name, expected in rule["expect"].items():
        if payload.get(name) != expected:
            reason = payload.get("message") or payload.get("problems") or payload.get("error")
            return False, f"{rule['script']} {' '.join(rule['argv'])}: {name!r} is {payload.get(name)!r}, expected " \
                          f"{expected!r}" + (f" ({reason})" if reason else "")
    return True, "answered as expected"


_NUMBER_RE = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w])|(?<![\w.,])\d+(?:\.\d+)?(?![\w])")


def numbers_in(text: str) -> list[float]:
    # Written as escapes on purpose: U+202F (narrow no-break space, a thousands
    # separator) is deleted; U+00A0 (no-break space, between a number and its
    # word) becomes a plain space so the trailing word boundary still matches.
    text = text.replace("{,}", ",").replace("\\,", "").replace("\u202f", "").replace("\u00a0", " ")
    return [float(token.replace(",", "")) for token in _NUMBER_RE.findall(text)]


def _number(state: WorkspaceState, rule: dict, targets: list[str]) -> dict:
    path = state.root / rule["path"]
    out = {"value": None}
    try:
        value = _pointer(json.loads(path.read_text(encoding="utf-8")), rule["pointer"])
    except FileNotFoundError:
        return {**out, "ok": False, "detail": f"{rule['path']} does not exist"}
    except (OSError, ValueError) as exc:
        return {**out, "ok": False, "detail": f"{rule['path']} cannot be read: {exc}"}
    except KeyError:
        value = None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return {**out, "ok": False, "detail": f"{rule['path']}#{rule['pointer']} is not a number ({value!r})"}
    text = "\n".join(_target_text(state, t) for t in targets)
    found = numbers_in(text)
    if any(n == float(value) for n in found):
        return {"value": value, "ok": True, "detail": f"{value} appears in {', '.join(targets)}"}
    shown = ", ".join(f"{n:g}" for n in found[:12]) or "none"
    return {"value": value, "ok": False,
            "detail": f"{rule['path']}#{rule['pointer']} is {value}; the text of {', '.join(targets)} "
                      f"states {shown}"}


def _term(state: WorkspaceState, rule: dict, targets: list[str]) -> dict:
    text = _fold("\n".join(_target_text(state, t) for t in targets))
    for term in rule["any"]:
        if re.search(r"(?<!\w)" + re.escape(_fold(term)) + r"(?!\w)", text):
            return {"matched": term, "ok": True, "detail": f"'{term}' appears in {', '.join(targets)}"}
    return {"matched": None, "ok": False,
            "detail": f"none of {', '.join(repr(t) for t in rule['any'])} appears in {', '.join(targets)}"}


# --------------------------------------------------------------------------- evaluation


def _evaluate_item(entry: dict, state: WorkspaceState, cache: dict) -> dict:
    targets = entry["targets"].get(state.line, entry["targets"].get("default"))
    evidence: list[dict] = []
    missing: list[str] = []
    if targets is None:
        evidence.append({"rule": "text", "target": None, "ok": False,
                         "detail": f"no target for the '{state.line}' line (guideline names: "
                                   f"{', '.join(sorted(entry['targets']))})"})
        missing.append(f"line:{state.line}")
        targets = []
    for target in targets:
        result = _check_target(state, target)
        evidence.append(result)
        if not result["ok"]:
            missing.append(f"text:{target}")
    presence_ok = not missing
    content_ok = True
    for rule in entry.get("evidence", []):
        kind = rule["kind"]
        record = {"rule": kind, "label": _rule_label(rule)}
        if kind == "file":
            ok = (state.root / rule["path"]).is_file()
            record.update(ok=ok, detail="exists" if ok else f"{rule['path']} does not exist")
        elif kind == "record":
            ok, detail = _record(state.root, rule)
            record.update(ok=ok, detail=detail)
        elif kind == "declaration":
            ok = rule["name"] in state.declarations
            record.update(ok=ok, detail="recorded" if ok else state.declarations_error or state.paper_error or
                          f"`paper_cli.py declare --declaration {rule['name']}` has not been recorded")
        elif kind == "command":
            ok, detail = _command(state.root, rule, cache)
            record.update(ok=ok, detail=detail)
        else:
            scope = rule.get("in", targets)
            record.update(_number(state, rule, scope) if kind == "number" else _term(state, rule, scope))
            record["in"] = list(scope)
        evidence.append(record)
        if not record["ok"]:
            missing.append(record["label"])
            if kind in PRESENCE_KINDS:
                presence_ok = False
            else:
                content_ok = False
    if not (presence_ok and content_ok):
        status = "missing"
    elif entry.get("question"):
        status = "needs-judgment"
    else:
        status = "satisfied"
    result = {"item": entry["number"], "section": entry["section"], "topic": entry["topic"], "status": status,
              "presence": "satisfied" if presence_ok else "missing", "targets": list(targets),
              "missing": missing, "evidence": evidence}
    if entry.get("question"):
        result["question"] = entry["question"]
    return result


def evaluate(guideline: dict, state: WorkspaceState) -> dict:
    cache: dict = {}
    items = [_evaluate_item(entry, state, cache) for entry in guideline["items"]]
    summary = {status: [i["item"] for i in items if i["status"] == status] for status in STATUSES}
    return {"ok": True,
            "guideline": {key: guideline.get(key) for key in ("id", "name", "version", "url", "citation")},
            "line": state.line, "paper_available": state.paper_available, "summary": summary,
            "notes": list(state.notes), "items": items}


def check(gid: str, root: Path, *, directory: Path | None = None) -> dict:
    guideline = load_guideline(gid, directory=directory)
    return evaluate(guideline, read_workspace(Path(root)))
