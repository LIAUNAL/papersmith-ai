"""Side-effect-free readers of a qualitative study's operator records (decisions K2, K3, K5, K8).

The board, the Study tab and ``paper_cli.py verify`` import these; none of them
writes, creates a directory or calls a model, and none raises on a corrupt
record (it reads as ``corrupt``). ``qual_cli.py`` is the only writer.

    study/transcripts.json   gate G-TRANSCRIPTS: every de-identified transcript or
                             field note the operator registered, bound by its sha256
                             and character count, with the participant code, how
                             consent was given and how it was de-identified
    study/codebook.json      every codebook version the operator recorded (sha256)
    study/themes.json        gate G-ANALYSIS: the operator's sign-off of the themes,
                             bound to the themes file, the codebook version and the
                             sha256 of every registered transcript

**No reader returns a transcript's text.** Transcripts are hashed and counted;
``check_quotes`` reads them only to tell whether a quote of the paper occurs in
them verbatim, and reports the paper's quote, never the transcript around it.

Every stored path is confined to the workspace before anything is read: an
absolute path, a path that traverses out or a link that points out reads as
``file-outside`` and is never followed, hashed or stat'ed.

Quote syntax (decision K3): a participant quote in the paper's ``.tex`` sources
is written ``\\pquote{<participant code>}{<verbatim text>}``. It may span lines;
a ``%`` comment hides it. The text is compared after normalising whitespace
(runs of blanks, line breaks, ``~`` and ``\\ ``) and quote ligatures (````, '',
`, ' and the typographic quotes) and unescaping the LaTeX specials ``\\% \\& \\#
\\$ \\_ \\{ \\}``; nothing else, so a polished or invented quote does not match.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA = 1
TRANSCRIPTS_PATH = "study/transcripts.json"
CODEBOOK_PATH = "study/codebook.json"
THEMES_PATH = "study/themes.json"
TRANSCRIPTS_GATE = "G-TRANSCRIPTS"
ANALYSIS_GATE = "G-ANALYSIS"
KINDS = ("interview", "focus-group", "field-note", "document")
PARTICIPANT_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
QUOTE_MACRO = "pquote"
#: The paper's translations hold translated quotes, never verbatim ones.
EXCLUDED_PAPER_DIRS = ("translations",)
QUOTE_SHOWN = 300  # characters of a failing quote echoed back


class QualitativeError(Exception):
    """A typed refusal: ``code`` is an uppercase identifier, ``message`` says what to do."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- paths


def confine(root: Path, stored: str) -> Path | None:
    """The resolved path of a workspace-relative ``stored`` path, or ``None`` when it is
    absolute, traverses out of the workspace, names a link pointing out, or is no valid
    path. Checked before any stat of the target, so an outside path is never followed."""
    if not isinstance(stored, str) or not stored or Path(stored).is_absolute():
        return None
    try:
        workspace = Path(root).resolve()
        path = (workspace / stored).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    return path if path.is_relative_to(workspace) and path != workspace else None


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except (OSError, ValueError):
        return False


def file_reason(root: Path, stored: str, sha256: str) -> str | None:
    """``None`` when the stored file still holds the bytes of ``sha256``; otherwise
    ``file-outside``, ``file-missing``, ``file-unreadable`` or ``file-changed``."""
    path = confine(root, stored)
    if path is None:
        return "file-outside"
    if not _is_file(path):
        return "file-missing"
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "file-unreadable"
    return None if digest == sha256 else "file-changed"


# --------------------------------------------------------------------------- record files


def _read_history(root: Path, relative: str, code: str, fields: tuple[str, ...]) -> dict:
    """``{"schema", "history"}``, an empty history when absent; ``code`` when malformed.
    Every entry must carry each of ``fields`` as a non-empty string."""
    path = Path(root) / relative
    if not _is_file(path):
        return {"schema": SCHEMA, "history": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QualitativeError(code, f"{relative} cannot be read as JSON ({exc})") from None
    if not (isinstance(data, dict) and isinstance(data.get("history"), list)
            and all(isinstance(entry, dict) for entry in data["history"])):
        raise QualitativeError(code, f"{relative} is not a record: a \"history\" list of objects")
    for number, entry in enumerate(data["history"], 1):
        missing = [key for key in fields if not (isinstance(entry.get(key), str) and entry[key])]
        if missing:
            raise QualitativeError(code, f"{relative} entry {number} lacks {', '.join(missing)}")
    return data


def read_transcripts(root: Path) -> dict:
    return _read_history(root, TRANSCRIPTS_PATH, "TRANSCRIPTS_CORRUPT", ("participant", "file", "sha256"))


def read_codebook(root: Path) -> dict:
    return _read_history(root, CODEBOOK_PATH, "CODEBOOK_CORRUPT", ("file", "sha256"))


def read_themes(root: Path) -> dict:
    data = _read_history(root, THEMES_PATH, "THEMES_CORRUPT", ("file", "sha256"))
    for number, entry in enumerate(data["history"], 1):
        if not (isinstance(entry.get("codebook"), dict) and isinstance(entry.get("transcripts"), list)):
            raise QualitativeError("THEMES_CORRUPT", f"{THEMES_PATH} entry {number} lacks its codebook "
                                                     "and transcripts bindings")
        if not all(isinstance(t, dict) and all(isinstance(t.get(key), str) for key in ("participant", "file", "sha256"))
                   for t in entry["transcripts"]):
            raise QualitativeError("THEMES_CORRUPT", f"{THEMES_PATH} entry {number} binds a transcript without "
                                                     "a participant, file and sha256 string")
    return data


def registered(history: list[dict]) -> list[dict]:
    """The registered transcripts: the latest entry of each (participant, file), in the
    order they were first registered."""
    latest: dict[tuple[str, str], dict] = {}
    for entry in history:
        latest[(entry["participant"], entry["file"])] = entry
    return list(latest.values())


def binding(entries: list[dict]) -> list[dict]:
    """What a sign-off binds of each registered transcript: its code, file and sha256."""
    return [{"participant": e["participant"], "file": e["file"], "sha256": e["sha256"]} for e in entries]


# --------------------------------------------------------------------------- states


_SHOWN = ("participant", "file", "kind", "characters", "consent", "deidentified", "note", "by", "at")


def transcripts_state(root: Path) -> dict:
    """``state`` ``absent`` (none registered), ``current`` (each registered file holds the
    bytes it was registered with), ``stale`` or ``corrupt`` (``message``). ``passed`` is
    gate G-TRANSCRIPTS: at least one transcript and every one current. Each transcript
    carries its code, file, kind, character count, consent and de-identification
    statements, ``state`` and ``reasons``; never its text."""
    root = Path(root)
    try:
        history = read_transcripts(root)["history"]
    except QualitativeError as error:
        return {"state": "corrupt", "gate": TRANSCRIPTS_GATE, "passed": False, "message": error.message}
    if not history:
        return {"state": "absent", "gate": TRANSCRIPTS_GATE, "passed": False, "transcripts": [],
                "counts": {"transcripts": 0, "current": 0, "stale": 0, "participants": 0, "kinds": {}},
                "warnings": []}
    items = []
    for entry in registered(history):
        reason = file_reason(root, entry["file"], entry["sha256"])
        item = {key: entry.get(key) for key in _SHOWN}
        item.update(sha256=entry["sha256"], state="stale" if reason else "current",
                    reasons=[reason] if reason else [])
        items.append(item)
    stale = [item for item in items if item["state"] == "stale"]
    kinds: dict[str, int] = {}
    for item in items:
        kinds[str(item["kind"])] = kinds.get(str(item["kind"]), 0) + 1
    warnings = [{"code": "TRANSCRIPT_STALE",
                 "message": f"{item['file']} ({item['participant']}) is {item['reasons'][0]} since it was "
                            "registered; the operator registers it again with `transcripts add --replace`"}
                for item in stale]
    return {"state": "stale" if stale else "current", "gate": TRANSCRIPTS_GATE, "passed": not stale,
            "transcripts": items,
            "counts": {"transcripts": len(items), "current": len(items) - len(stale), "stale": len(stale),
                       "participants": len({item["participant"] for item in items}), "kinds": kinds},
            "records": len(history), "warnings": warnings}


def codebook_state(root: Path) -> dict:
    """``absent``, ``corrupt`` (``message``), or the latest codebook version with ``state``
    ``current`` or ``stale`` (``reasons``: its file changed, missing, unreadable or outside)."""
    root = Path(root)
    try:
        history = read_codebook(root)["history"]
    except QualitativeError as error:
        return {"state": "corrupt", "message": error.message}
    if not history:
        return {"state": "absent"}
    entry = dict(history[-1])
    reason = file_reason(root, entry["file"], entry["sha256"])
    warnings = [] if reason is None else [
        {"code": "CODEBOOK_STALE", "message": f"the codebook {entry['file']} is {reason} since version "
                                              f"{len(history)} was recorded; `codebook record --by` records it"}]
    entry.update(state="stale" if reason else "current", reasons=[reason] if reason else [],
                 version=len(history), versions=len(history), warnings=warnings)
    return entry


def themes_state(root: Path) -> dict:
    """``absent``, ``corrupt`` (``message``), or the latest sign-off with ``state`` ``current``
    or ``stale`` and ``reasons``: ``themes-file-*`` (changed, missing, unreadable, outside),
    ``codebook-changed`` (another codebook version was recorded), ``codebook-stale`` (the
    codebook file changed or its record is unreadable), ``transcript-changed`` (a signed
    transcript was replaced or its file changed), ``transcript-added`` (one registered since).
    ``passed`` is gate G-ANALYSIS: a current sign-off."""
    root = Path(root)
    try:
        history = read_themes(root)["history"]
    except QualitativeError as error:
        return {"state": "corrupt", "gate": ANALYSIS_GATE, "passed": False, "message": error.message}
    if not history:
        return {"state": "absent", "gate": ANALYSIS_GATE, "passed": False}
    entry = dict(history[-1])
    reasons = []
    themes_reason = file_reason(root, entry["file"], entry["sha256"])
    if themes_reason:
        reasons.append(f"themes-{themes_reason}")
    codebook = codebook_state(root)
    signed_codebook = entry["codebook"]
    if codebook["state"] in ("current", "stale") and (codebook.get("sha256") != signed_codebook.get("sha256")
                                                      or codebook.get("file") != signed_codebook.get("file")):
        reasons.append("codebook-changed")
    if codebook["state"] != "current":
        reasons.append("codebook-stale")
    transcripts = transcripts_state(root)
    if transcripts["state"] == "corrupt":
        reasons.append("transcript-changed")
    else:
        signed = {(t.get("participant"), t.get("file")): t.get("sha256") for t in entry["transcripts"]
                  if isinstance(t, dict)}
        now = {(t["participant"], t["file"]): t["sha256"] for t in transcripts["transcripts"]}
        if any(key not in signed for key in now):
            reasons.append("transcript-added")
        if (any(signed.get(key) != sha for key, sha in now.items() if key in signed)
                or any(key not in now for key in signed) or transcripts["state"] == "stale"):
            reasons.append("transcript-changed")
    warnings = [] if not reasons else [
        {"code": "THEMES_STALE", "message": f"the themes sign-off of {entry['file']} is stale "
                                            f"({', '.join(reasons)}); the operator signs the themes off again"}]
    entry.update(state="stale" if reasons else "current", gate=ANALYSIS_GATE, passed=not reasons,
                 reasons=reasons, signoffs=len(history), warnings=warnings)
    return entry


def qualitative_status(root: Path) -> dict:
    """The transcripts, codebook and themes states and their warnings, in that order."""
    transcripts, codebook, themes = transcripts_state(root), codebook_state(root), themes_state(root)
    warnings = []
    for name, state in (("TRANSCRIPTS", transcripts), ("CODEBOOK", codebook), ("THEMES", themes)):
        if state["state"] == "corrupt":
            warnings.append({"code": f"{name}_CORRUPT", "message": state["message"]})
        else:
            warnings.extend(state.get("warnings") or [])
    return {"transcripts": transcripts, "codebook": codebook, "themes": themes, "warnings": warnings}


# --------------------------------------------------------------------------- quotes


_LIGATURES = (("``", '"'), ("''", '"'), ("“", '"'), ("”", '"'), ("„", '"'), ("‟", '"'),
              ("`", "'"), ("‘", "'"), ("’", "'"), ("‚", "'"), ("‛", "'"))
_LATEX_SPECIALS = re.compile(r"\\([%&#$_{}])")
_LATEX_SPACES = re.compile(r"~|\\ ")
_BLANKS = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Whitespace runs to one space, quote ligatures to ``"`` and ``'``; nothing else."""
    for ligature, plain in _LIGATURES:
        text = text.replace(ligature, plain)
    return _BLANKS.sub(" ", text).strip()


_TURN = re.compile(r"^[ \t]*([^\s:][^:\n]{0,39}?)[ \t]*:[ \t]", re.MULTILINE)


def speaker_turns(text: str, participant: str) -> list[str]:
    """The turns of ``text`` spoken by ``participant``: a turn starts at a line labelled
    ``<speaker>:`` and runs to the next labelled line. Empty when no line names them, so
    a quote is searched within one turn of its own speaker, never across turns."""
    marks = list(_TURN.finditer(text))
    return [text[mark.end():(marks[i + 1].start() if i + 1 < len(marks) else len(text))]
            for i, mark in enumerate(marks) if mark.group(1) == participant]


def quote_text(latex: str) -> str:
    """A quote's LaTeX source as the words it prints: specials unescaped, ties and control
    spaces read as blanks, then ``normalise``."""
    return normalise(_LATEX_SPECIALS.sub(r"\1", _LATEX_SPACES.sub(" ", latex)))


def _strip_comments(source: str) -> str:
    """``source`` with every ``%`` comment blanked to the end of its line (an escaped
    ``\\%`` is text), keeping every offset and line number."""
    out = []
    for line in source.split("\n"):
        backslashes = 0
        cut = None
        for index, char in enumerate(line):
            if char == "\\":
                backslashes += 1
                continue
            if char == "%" and backslashes % 2 == 0:
                cut = index
                break
            backslashes = 0
        out.append(line if cut is None else line[:cut] + " " * (len(line) - cut))
    return "\n".join(out)


def _group(source: str, start: int) -> tuple[str, int] | None:
    """The text of the brace group opening at or after ``start`` (blanks skipped) and the
    offset after it; ``None`` when no group opens there or it never closes."""
    index = start
    while index < len(source) and source[index] in " \t\n":
        index += 1
    if index >= len(source) or source[index] != "{":
        return None
    depth, cursor = 0, index
    while cursor < len(source):
        char = source[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[index + 1:cursor], cursor + 1
        cursor += 1
    return None


_MACRO = re.compile(r"\\" + QUOTE_MACRO + r"(?![A-Za-z@])")


def find_quotes(source: str) -> list[dict]:
    """Every ``\\pquote{code}{text}`` of a ``.tex`` source outside comments: ``line`` (1-based,
    where the macro starts), ``participant``, ``latex`` (the text as written), or
    ``malformed`` true when a group is missing or never closes."""
    clean = _strip_comments(source)
    quotes = []
    for match in _MACRO.finditer(clean):
        line = clean.count("\n", 0, match.start()) + 1
        code = _group(clean, match.end())
        text = _group(clean, code[1]) if code else None
        if code is None or text is None:
            quotes.append({"line": line, "participant": (code[0].strip() if code else ""), "latex": "",
                           "malformed": True})
            continue
        quotes.append({"line": line, "participant": code[0].strip(), "latex": text[0], "malformed": False})
    return quotes


def _tex_files(root: Path, paper: Path) -> list[Path]:
    workspace = root.resolve()
    found = []
    for path in sorted(paper.rglob("*.tex")):
        relative = path.relative_to(paper)
        if relative.parts and relative.parts[0] in EXCLUDED_PAPER_DIRS:
            continue
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError):
            continue
        if resolved.is_relative_to(workspace) and _is_file(resolved):
            found.append(path)
    return found


def check_quotes(root: Path, paper_dir: Path) -> dict:
    """Check every participant quote of the paper's ``.tex`` sources (``translations/``
    excluded) against the registered, current transcripts of its participant.

    Returns ``{"quotes", "verified", "transcripts", "failures", "files"}`` where each failure
    is ``{file, line, participant, reason, quote}`` (``reason``: ``not-found``,
    ``participant-not-registered``, ``transcript-stale``, ``speaker-not-labelled``, ``quote-empty``,
    ``quote-malformed``;
    ``quote`` is the paper's text, at most 300 characters), or ``{"corrupt": <message>}`` when
    ``study/transcripts.json`` is unreadable. Reads the transcripts only to search them;
    never returns their text. ``paper_dir`` must lie in the workspace (the caller checks)."""
    root = Path(root)
    paper = Path(paper_dir)
    workspace = root.resolve()
    try:
        history = read_transcripts(root)["history"]
    except QualitativeError as error:
        return {"corrupt": error.message}
    texts: dict[str, list[str]] = {}
    stale: set[str] = set()
    unlabelled: set[str] = set()
    entries = registered(history)
    sharing: dict[str, int] = {}
    for entry in entries:
        sharing[entry["file"]] = sharing.get(entry["file"], 0) + 1
    for entry in entries:
        texts.setdefault(entry["participant"], [])
        if file_reason(root, entry["file"], entry["sha256"]) is not None:
            stale.add(entry["participant"])
            continue
        path = confine(root, entry["file"])
        try:
            raw = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError, AttributeError):
            stale.add(entry["participant"])
            continue
        own = speaker_turns(raw, entry["participant"])
        if own:
            texts[entry["participant"]].extend(normalise(turn) for turn in own)
        elif sharing[entry["file"]] == 1:
            texts[entry["participant"]].append(normalise(raw))
        else:  # a shared file whose turns do not name this participant cannot attribute a quote
            unlabelled.add(entry["participant"])
    quotes = verified = 0
    failures = []
    files = []
    for path in _tex_files(root, paper):
        shown = path.resolve().relative_to(workspace).as_posix()
        try:
            source = path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        found = find_quotes(source)
        if found:
            files.append(shown)
        for quote in found:
            quotes += 1
            text = quote_text(quote["latex"])
            reason = None
            if quote["malformed"]:
                reason = "quote-malformed"
            elif not text:
                reason = "quote-empty"
            elif quote["participant"] not in texts:
                reason = "participant-not-registered"
            elif not any(text in transcript for transcript in texts[quote["participant"]]):
                reason = ("transcript-stale" if quote["participant"] in stale
                          else "speaker-not-labelled" if quote["participant"] in unlabelled else "not-found")
            if reason is None:
                verified += 1
            else:
                failures.append({"file": shown, "line": quote["line"], "participant": quote["participant"],
                                 "reason": reason, "quote": text[:QUOTE_SHOWN]})
    current = sum(len(items) for items in texts.values())
    return {"quotes": quotes, "verified": verified, "transcripts": current, "failures": failures, "files": files}
