"""paper_translate: the Spanish translation of the finished English manuscript.

Spec S2-S6 of `odd/tasks/manuscript-translation-es.md`. The English paper
(`paper/main.tex`, its blocks under `%% paper-writing block` markers) stays
the canonical source. The translation is a derived artifact under
`paper/translations/<lang>/` and nothing here ever writes `paper/main.tex`:

- `translation.json` -- schema 1: the language, the sha256 of the `main.tex`
  it was planned from, one record per block (`source_digest`: the English
  body digest the Spanish body was translated from; `state`; `stored_at`;
  the block's style summary) and the glossary of protected terms;
- `blocks/<id>.tex` -- the Spanish body of each canonical block;
- `main.tex` -- the built file: canonical `main.tex` with every block body
  replaced by its Spanish body, the block markers rewritten to
  `%% paper-writing translation <id> source <digest> begin|end` (so no
  canonical parser ever reads it as a block) and Spanish declared as the
  main language;
- `audit.json` -- the last `audit`: `paper_style_es.audit_document` over the
  stored blocks plus `paper_style_es.compare_facts` per block against the
  current English.

A block is `missing` (no Spanish body), `current` (stored against the English
digest the block has now) or `stale` (the English changed after the store).
A block whose English body has no prose (an equation, a figure with no
caption) has nothing to translate: `plan` carries it over as `current`.

Fragments are the prose `main.tex` holds outside every block: `\\title`,
the sectioning titles (`\\section` to `\\paragraph`, starred or not, the
optional short title being a fragment of its own) and `\\caption`. Each has
a stable id `<kind>-<n>-<sha8>` (`n` counts that kind in document order,
`sha8` is the start of the English text's sha256). Its Spanish text lives in
`translation.json` under `fragments`; it is `missing`, `current` (stored
against the English it has now) or `stale` (the fragment at that place
changed its English, so its id changed too).

Every refusal raises before any byte is written.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_block  # noqa: E402
import paper_language  # noqa: E402
import paper_style_es  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

SCHEMA = 1
#: Languages a translation can target. Only Spanish has a style catalog.
SUPPORTED_LANGUAGES = ("es",)
STATES = ("missing", "current", "stale")

#: Placeholder markers a stored translation may not carry. `pendiente` is
#: left out on purpose: in Spanish it is also the word for a slope.
_PLACEHOLDERS = tuple((marker, pattern) for marker, pattern in paper_language.PLACEHOLDER_PATTERNS
                      if marker != "pendiente")
#: English function words; a text with several of them and no Spanish reads as English.
_ENGLISH_WORDS = frozenset(
    "the of and to in is are we this that with for by which on as an be from our these it was were "
    "has have not but its their than then when where while".split())
_ACRONYM_RE = re.compile(r"\(([A-Z][A-Za-z0-9-]*[A-Z0-9]s?)\)")
_TERM_COMMAND_RE = re.compile(r"\\(?:texttt|textsc)\{([^{}]+)\}")
FRAGMENT_KINDS = ("title", "section", "subsection", "subsubsection", "paragraph", "caption")
_FRAGMENT_RE = re.compile(r"\\(" + "|".join(FRAGMENT_KINDS) + r")(?![A-Za-z@])\*?")
_COMMENT_RE = re.compile(r"(?<!\\)%.*$", re.M)


# --- Paths and small I/O ------------------------------------------------------

def check_language(lang: str) -> None:
    if lang not in SUPPORTED_LANGUAGES:
        raise Refused("TRANSLATION_LANGUAGE_UNSUPPORTED",
                      f"--lang {lang!r} is not supported; supported: {', '.join(SUPPORTED_LANGUAGES)}")


def translation_dir(paper_dir: Path, lang: str) -> Path:
    return paper_dir / "translations" / lang


def _shown(paper_dir: Path, path: Path) -> str:
    """A path as the workspace sees it: `paper/translations/es/...`."""
    return f"{paper_dir.name}/{path.relative_to(paper_dir).as_posix()}"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _write_json(path: Path, value: dict) -> None:
    _atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _read_record(paper_dir: Path, lang: str) -> dict | None:
    path = translation_dir(paper_dir, lang) / "translation.json"
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) and record.get("schema") == SCHEMA else None


def _require_record(paper_dir: Path, lang: str) -> dict:
    record = _read_record(paper_dir, lang)
    if record is None:
        raise Refused("TRANSLATION_NOT_PLANNED",
                      f"{_shown(paper_dir, translation_dir(paper_dir, lang) / 'translation.json')} is absent "
                      f"or unreadable; run `translate plan --lang {lang}` first")
    return record


# --- The English source -------------------------------------------------------

def _english(paper_dir: Path, *, strict: bool) -> tuple[bytes, list[dict]]:
    """`main.tex` bytes and its blocks in document order: id, body, the digest
    of the body on disk, and the marker lines. `strict` refuses a hand-edited
    block (`BLOCK_HAND_EDITED`): a translation is made from what the canonical
    pipeline wrote, never from bytes it does not know."""
    data = paper_block.resolve_main_tex(paper_dir).read_bytes()
    parsed = paper_block.parse(data)
    blocks = []
    for block_id in parsed.order:
        begin, end = parsed.pairs[block_id]
        body = data[begin["end"]:end["start"]]
        digest = hashlib.sha256(body).hexdigest()
        if strict and digest != begin["digest"]:
            raise Refused("BLOCK_HAND_EDITED",
                          f"{block_id!r}: expected sha256={begin['digest']}, found sha256={digest}")
        blocks.append({"id": block_id, "body": body.decode("utf-8"), "digest": digest,
                       "begin": begin, "end": end})
    return data, blocks


def _has_prose(tex: str) -> bool:
    return bool(paper_language.prose_lines(tex))


def derive_glossary(blocks: list[dict]) -> list[str]:
    """Protected terms the paper itself names: acronyms in parentheses and
    `\\texttt`/`\\textsc` terms. They stay byte-identical in the translation
    and the style audit never counts them as repetition."""
    terms: list[str] = []
    for block in blocks:
        for match in list(_ACRONYM_RE.finditer(block["body"])) + list(_TERM_COMMAND_RE.finditer(block["body"])):
            term = match.group(1).strip()
            if sum(1 for c in term if c.isupper()) >= 2 or match.re is _TERM_COMMAND_RE:
                if term and term not in terms:
                    terms.append(term)
    return terms


def _states(paper_dir: Path, lang: str, blocks: list[dict], record: dict | None) -> list[dict]:
    stored = (record or {}).get("blocks") or {}
    folder = translation_dir(paper_dir, lang) / "blocks"
    rows = []
    for block in blocks:
        entry = stored.get(block["id"]) if isinstance(stored.get(block["id"]), dict) else None
        if entry is None or not (folder / f"{block['id']}.tex").is_file():
            state = "missing"
            entry = None
        else:
            state = "current" if entry.get("source_digest") == block["digest"] else "stale"
        rows.append({"id": block["id"], "state": state,
                     "source_digest": entry.get("source_digest") if entry else None,
                     "stored_at": entry.get("stored_at") if entry else None})
    return rows


def _summary(audit: dict) -> dict:
    keys = ("index", "style_score", "flow_score", "redundancy_score", "verdict")
    return {**{key: audit[key] for key in keys}, "findings": len(audit["findings"])}


# --- Verbs ----------------------------------------------------------------------

def plan(paper_dir: Path, lang: str, *, terms: list[str] | None = None) -> dict:
    """Writes or refreshes `translation.json` and lists the per-block work."""
    check_language(lang)
    data, blocks = _english(paper_dir, strict=True)
    if not blocks:
        raise Refused("TRANSLATION_NO_BLOCKS",
                      f"{_shown(paper_dir, paper_dir / 'main.tex')} holds no paper-writing block; "
                      f"write the English paper first")
    scan = paper_language.scan(data.decode("utf-8"))
    if scan["placeholders"]:
        listed = "; ".join(f"line {p['line']}: {p['marker']} ({p['text'][:60]})" for p in scan["placeholders"])
        raise Refused("TRANSLATION_SOURCE_PLACEHOLDER",
                      f"the English paper still carries placeholder text: {listed}")
    empty = [b["id"] for b in blocks if not _COMMENT_RE.sub("", b["body"]).strip()]
    if empty:
        raise Refused("TRANSLATION_SOURCE_INCOMPLETE",
                      f"these English blocks are empty; finish and verify the English paper first: {', '.join(empty)}")

    folder = translation_dir(paper_dir, lang)
    previous = _read_record(paper_dir, lang) or {}
    user_terms = [t for t in (previous.get("glossary_user") or []) if isinstance(t, str)]
    for term in terms or ():
        term = term.strip()
        if term and term not in user_terms:
            user_terms.append(term)
    glossary = derive_glossary(blocks)
    glossary += [t for t in user_terms if t not in glossary]

    stored = dict(previous.get("blocks") or {})
    carried = []
    now = _now()
    for block in blocks:
        if not _has_prose(block["body"]):
            entry = stored.get(block["id"]) or {}
            if entry.get("source_digest") != block["digest"] or not (folder / "blocks" / f"{block['id']}.tex").is_file():
                carried.append(block)
                stored[block["id"]] = {"source_digest": block["digest"], "state": "current", "stored_at": now,
                                       "carried_over": True}
    record = {"schema": SCHEMA, "language": lang,
              "source_main_sha256": hashlib.sha256(data).hexdigest(),
              "blocks": {}, "glossary": glossary, "glossary_user": user_terms}
    if isinstance(previous.get("built"), dict):
        record["built"] = previous["built"]
    # One entry per block main.tex holds now, in its order; a block that left
    # main.tex leaves the record (its stored body stays on disk, unread).
    record["blocks"] = {b["id"]: dict(stored.get(b["id"]) or {"source_digest": None, "stored_at": None})
                        for b in blocks}
    rows = _states_after(paper_dir, lang, blocks, record, carried)
    for row in rows:
        record["blocks"][row["id"]]["state"] = row["state"]
    # One entry per fragment main.tex holds now. A fragment whose English
    # changed got a new id; it keeps the Spanish stored for its place, `stale`.
    fragments = fragments_of(data, blocks)
    fragment_rows = _fragment_states(previous, fragments)
    record["fragments"] = {}
    for fragment, row in zip(fragments, fragment_rows):
        entry = {"kind": fragment["kind"], "english": fragment["english"], "source_sha": fragment["source_sha"],
                 "state": row["state"]}
        stored_entry = _fragment_entry(previous, fragment)
        if stored_entry is not None:
            entry.update({key: stored_entry[key] for key in ("spanish", "spanish_source_sha", "stored_at")
                          if key in stored_entry})
        record["fragments"][fragment["id"]] = entry

    for block in carried:
        _atomic_write(folder / "blocks" / f"{block['id']}.tex", block["body"].encode("utf-8"))
    _write_json(folder / "translation.json", record)

    work = []
    for block, row in zip(blocks, rows):
        text = " ".join(t for _, t in paper_language.prose_lines(block["body"]))
        work.append({"id": block["id"], "state": row["state"], "source": _shown(paper_dir, paper_dir / "main.tex"),
                     "lines": [block["begin"]["line"] + 1, block["end"]["line"] - 1],
                     "excerpt": (text or block["body"].strip())[:160],
                     "spanish": _shown(paper_dir, folder / "blocks" / f"{block['id']}.tex")})
    listed = [{"id": f["id"], "kind": f["kind"], "state": row["state"], "english": f["english"], "line": f["line"]}
              for f, row in zip(fragments, fragment_rows)]
    return {"ok": True, "lang": lang, "translation": _shown(paper_dir, folder / "translation.json"),
            "blocks": work, "counts": _counts(rows), "fragments": listed,
            "fragment_counts": _counts(fragment_rows), "glossary": glossary}


def _states_after(paper_dir: Path, lang: str, blocks: list[dict], record: dict, carried: list[dict]) -> list[dict]:
    """States as they will be once the carried-over bodies are on disk."""
    rows = _states(paper_dir, lang, blocks, record)
    carried_ids = {b["id"] for b in carried}
    for row in rows:
        if row["id"] in carried_ids:
            entry = record["blocks"][row["id"]]
            row.update(state="current", source_digest=entry["source_digest"], stored_at=entry["stored_at"])
    return rows


def _counts(rows: list[dict]) -> dict:
    return {"total": len(rows), **{state: sum(1 for r in rows if r["state"] == state) for state in STATES[1:]},
            "missing": sum(1 for r in rows if r["state"] == "missing")}


def _group_end(text: str, position: int) -> int:
    """Index just after the [..] or {..} group opening at `position`, or -1."""
    opening = text[position]
    closing = "]" if opening == "[" else "}"
    depth, i = 0, position
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == opening:
            depth += 1
        elif text[i] == closing:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _masked(text: str, data: bytes, blocks: list[dict]) -> str:
    """`text` with every block region and every comment blanked, offsets kept."""
    chars = list(text)
    for block in blocks:
        start = len(data[:block["begin"]["start"]].decode("utf-8"))
        end = len(data[:block["end"]["end"]].decode("utf-8"))
        chars[start:end] = " " * (end - start)
    masked = "".join(chars)
    return _COMMENT_RE.sub(lambda m: " " * len(m.group(0)), masked)


def fragments_of(data: bytes, blocks: list[dict]) -> list[dict]:
    """Every translatable fragment outside the blocks, in document order:
    `{id, kind, english, source_sha, start, end, line}`, where `start:end` is
    the argument's text without its delimiters (character offsets)."""
    text = data.decode("utf-8")
    masked = _masked(text, data, blocks)
    found, counters = [], {}
    for match in _FRAGMENT_RE.finditer(masked):
        kind = match.group(1)
        position = match.end()
        while position < len(masked) and masked[position] in " \t":
            position += 1
        spans = []
        if position < len(masked) and masked[position] == "[":
            end = _group_end(masked, position)
            if end < 0:
                continue
            spans.append((position + 1, end - 1))
            position = end
            while position < len(masked) and masked[position] in " \t":
                position += 1
        if position >= len(masked) or masked[position] != "{":
            continue
        end = _group_end(masked, position)
        if end < 0:
            continue
        spans.append((position + 1, end - 1))
        for start, stop in spans:
            english = text[start:stop]
            if "#" in english or not paper_language.prose_lines(english):
                continue
            counters[kind] = counters.get(kind, 0) + 1
            sha = hashlib.sha256(english.encode("utf-8")).hexdigest()
            found.append({"id": f"{kind}-{counters[kind]}-{sha[:8]}", "kind": kind, "english": english,
                          "source_sha": sha, "start": start, "end": stop,
                          "line": text.count("\n", 0, start) + 1})
    return found


def _fragment_entry(record: dict | None, fragment: dict) -> dict | None:
    """The stored record answering `fragment`: its own id, or the record of the
    fragment that held its place (same kind and ordinal) before its English
    changed."""
    stored = (record or {}).get("fragments") or {}
    entry = stored.get(fragment["id"])
    if isinstance(entry, dict) and entry.get("spanish"):
        return entry
    prefix = fragment["id"].rsplit("-", 1)[0] + "-"
    for key, entry in stored.items():
        if key.startswith(prefix) and isinstance(entry, dict) and entry.get("spanish"):
            return entry
    return None


def _fragment_states(record: dict | None, fragments: list[dict]) -> list[dict]:
    rows = []
    for fragment in fragments:
        entry = _fragment_entry(record, fragment)
        if entry is None:
            state = "missing"
        else:
            state = "current" if entry.get("spanish_source_sha") == fragment["source_sha"] else "stale"
        rows.append({"id": fragment["id"], "kind": fragment["kind"], "state": state})
    return rows


def _looks_english(prose: str) -> bool:
    words = [w.lower() for w in paper_language.WORD.findall(prose)]
    english = sum(1 for w in words if w in _ENGLISH_WORDS)
    return english >= 2 and (len(words) >= 12 or english >= 3)


def store(paper_dir: Path, lang: str, block_id: str, file: Path) -> dict:
    """Validates one block's Spanish body and stores it against the English
    digest the block has now."""
    check_language(lang)
    paper_block.validate_block_id(block_id)
    record = _require_record(paper_dir, lang)
    _, blocks = _english(paper_dir, strict=True)
    block = next((b for b in blocks if b["id"] == block_id), None)
    if block is None:
        raise Refused("BLOCK_ABSENT", f"no block named {block_id!r} in {_shown(paper_dir, paper_dir / 'main.tex')}")
    text = _read_spanish(file, f"block {block_id!r}")
    _gate(text, block["body"], f"block {block_id!r}")

    glossary = [t for t in record.get("glossary") or [] if isinstance(t, str)]
    audit = paper_style_es.audit_text(text, glossary=glossary)
    body = text if text.endswith("\n") else text + "\n"
    folder = translation_dir(paper_dir, lang)
    now = _now()
    record.setdefault("blocks", {})[block_id] = {"source_digest": block["digest"], "state": "current",
                                                 "stored_at": now,
                                                 "spanish_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                                                 "audit": _summary(audit)}
    _atomic_write(folder / "blocks" / f"{block_id}.tex", body.encode("utf-8"))
    _write_json(folder / "translation.json", record)
    return {"ok": True, "lang": lang, "id": block_id, "state": "current", "source_digest": block["digest"],
            "stored_at": now, "path": _shown(paper_dir, folder / "blocks" / f"{block_id}.tex"), "audit": audit}


def _read_spanish(file: Path, what: str) -> str:
    try:
        text = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Refused("TARGET_UNREADABLE", f"{file}: {exc}")
    if not text.strip():
        raise Refused("TRANSLATION_EMPTY", f"{file} holds no text for {what}")
    return text


def _gate(text: str, english: str, what: str, *, fragment: bool = False) -> None:
    """The checks every stored Spanish text passes: no marker line, no
    placeholder, reads as Spanish, keeps the English facts. A fragment is one
    argument of one command: it keeps its braces balanced, holds no blank
    line, is never the English text unchanged, and has no paragraph rule."""
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("%% paper-writing"):
            raise Refused("CONTENT_CARRIES_MARKER",
                          f"the Spanish text for {what} carries a marker-shaped line {number}: {line!r}")
    prose = paper_language.prose_lines(text)
    hits = [(n, marker, t) for n, t in prose for marker, pattern in _PLACEHOLDERS if pattern.search(t)]
    if hits:
        listed = "; ".join(f"line {n}: {marker} ({t[:60]})" for n, marker, t in hits)
        raise Refused("TRANSLATION_PLACEHOLDER_TEXT", f"the Spanish text for {what} carries placeholders: {listed}")
    joined = " ".join(t for _, t in prose)
    unchanged = fragment and " ".join(text.split()) == " ".join(english.split()) and any(
        c.islower() for c in english)
    if unchanged or (joined and not paper_language.is_spanish_prose(joined) and _looks_english(joined)):
        raise Refused("TRANSLATION_NOT_SPANISH", f"the text stored for {what} does not read as Spanish: {joined[:120]!r}")
    differences = paper_style_es.compare_facts(english, text)
    if fragment:
        differences = [d for d in differences if not d.startswith("paragraphs:")]
        stripped = text.strip()
        if re.search(r"\n\s*\n", stripped):
            differences.append("a fragment is one paragraph: remove the blank line")
        depth = 0
        for i, char in enumerate(stripped):
            if char in "{}" and (i == 0 or stripped[i - 1] != "\\"):
                depth += 1 if char == "{" else -1
                if depth < 0:
                    break
        if depth != 0:
            differences.append("braces: the fragment's { and } do not balance")
    if differences:
        raise Refused("TRANSLATION_FIDELITY",
                      f"the Spanish text for {what} does not keep the English facts: " + " | ".join(differences))


def store_fragment(paper_dir: Path, lang: str, fragment_id: str, file: Path) -> dict:
    """Validates one fragment's Spanish text and stores it in `translation.json`
    against the English the fragment has now."""
    check_language(lang)
    record = _require_record(paper_dir, lang)
    data, blocks = _english(paper_dir, strict=True)
    fragment = next((f for f in fragments_of(data, blocks) if f["id"] == fragment_id), None)
    if fragment is None:
        raise Refused("TRANSLATION_FRAGMENT_UNKNOWN",
                      f"no fragment {fragment_id!r} outside the blocks of {_shown(paper_dir, paper_dir / 'main.tex')}; "
                      f"`translate plan` lists the current ids")
    text = _read_spanish(file, f"fragment {fragment_id!r}")
    _gate(text, fragment["english"], f"fragment {fragment_id!r}", fragment=True)
    spanish = text.strip()
    now = _now()
    fragments = record.setdefault("fragments", {})
    prefix = fragment_id.rsplit("-", 1)[0] + "-"
    for key in [k for k in fragments if k.startswith(prefix) and k != fragment_id]:
        del fragments[key]
    fragments[fragment_id] = {"kind": fragment["kind"], "english": fragment["english"],
                              "source_sha": fragment["source_sha"], "state": "current", "spanish": spanish,
                              "spanish_source_sha": fragment["source_sha"], "stored_at": now}
    _write_json(translation_dir(paper_dir, lang) / "translation.json", record)
    return {"ok": True, "lang": lang, "id": fragment_id, "kind": fragment["kind"], "state": "current",
            "stored_at": now, "english": fragment["english"], "spanish": spanish}


_BABEL_RE = re.compile(r"\\usepackage\[([^\]]*)\]\{babel\}")
_SETMAIN_RE = re.compile(r"\\setmainlanguage(\[[^\]]*\])?\{([^}]+)\}")
_SPANISH_BABEL = ["main=spanish", "es-noshorthands", "es-tabla"]


def _declare_spanish(preamble: str) -> str:
    """Spanish as the main language: babel's `main=spanish` beside the
    languages already loaded, polyglossia's `\\setmainlanguage{spanish}`, or a
    babel line after `\\documentclass` when neither is there. `es-noshorthands`
    keeps `<`, `>` and `"` inert so math and TikZ compile as in English."""
    match = _SETMAIN_RE.search(preamble)
    if match:
        other = match.group(2).strip()
        tail = "" if other.lower() == "spanish" else f"\n\\setotherlanguage{{{other}}}"
        return preamble[:match.start()] + "\\setmainlanguage{spanish}" + tail + preamble[match.end():]
    match = _BABEL_RE.search(preamble)
    if match:
        options = [o.strip() for o in match.group(1).split(",") if o.strip()]
        options = [o for o in options if not o.lower().startswith(("main=", "es-")) and o.lower() != "spanish"]
        line = f"\\usepackage[{','.join(options + _SPANISH_BABEL)}]{{babel}}"
        return preamble[:match.start()] + line + preamble[match.end():]
    line = f"\\usepackage[{','.join(['english'] + _SPANISH_BABEL)}]{{babel}}\n"
    return _after_documentclass(preamble, line)


def _after_documentclass(preamble: str, line: str) -> str:
    match = re.search(r"\\documentclass(?:\[[^\]]*\])?\{[^}]*\}[^\n]*\n?", preamble)
    if match is None:
        return line + preamble
    end = match.end()
    head = preamble[:end] if preamble[:end].endswith("\n") else preamble[:end] + "\n"
    return head + line + preamble[end:]


def _relocate(text: str, paper_dir: Path) -> str:
    """The built file sits two directories under `paper/`: inputs, graphics and
    the bibliography resolve from there as they do from `paper/`."""
    def up(entry: str) -> str:
        entry = entry.strip()
        return entry if not entry or entry.startswith(("/", "../", "~")) or re.match(r"[A-Za-z]:", entry) else "../../" + entry

    text = re.sub(r"\\bibliography\{([^}]*)\}",
                  lambda m: "\\bibliography{" + ",".join(up(e) for e in m.group(1).split(",")) + "}", text)
    text = re.sub(r"\\addbibresource(\[[^\]]*\])?\{([^}]*)\}",
                  lambda m: f"\\addbibresource{m.group(1) or ''}{{{up(m.group(2))}}}", text)
    text = re.sub(r"\\graphicspath\{((?:\{[^}]*\})*)\}",
                  lambda m: "\\graphicspath{" + "".join("{" + up(d) + "}" for d in re.findall(r"\{([^}]*)\}", m.group(1)))
                  + "}", text)
    text = re.sub(r"\\bibliographystyle\{([^}]*)\}",
                  lambda m: "\\bibliographystyle{" + (up(m.group(1)) if (paper_dir / f"{m.group(1)}.bst").is_file()
                                                       else m.group(1)) + "}", text)
    return text


def build(paper_dir: Path, lang: str) -> dict:
    """Writes `translations/<lang>/main.tex`; refuses while any block is
    missing or stale. Never writes `paper/main.tex`."""
    check_language(lang)
    record = _require_record(paper_dir, lang)
    data, blocks = _english(paper_dir, strict=True)
    rows = _states(paper_dir, lang, blocks, record)
    fragments = fragments_of(data, blocks)
    fragment_rows = _fragment_states(record, fragments)
    pending = [f"{r['id']} ({r['state']})" for r in rows + fragment_rows if r["state"] != "current"]
    if pending:
        raise Refused("TRANSLATION_INCOMPLETE",
                      f"{len(pending)} block(s) or fragment(s) are not current; store each one first: "
                      f"{', '.join(pending)}")

    folder = translation_dir(paper_dir, lang)
    source = data.decode("utf-8")

    def offset(byte_offset: int) -> int:
        return len(data[:byte_offset].decode("utf-8"))

    replacements = []
    for block in blocks:
        begin, end = block["begin"], block["end"]
        line = data[end["start"]:end["end"]]
        terminator = "\r\n" if line.endswith(b"\r\n") else "\n" if line.endswith(b"\n") else ""
        body = (folder / "blocks" / f"{block['id']}.tex").read_text(encoding="utf-8")
        if body and not body.endswith("\n"):
            body += "\n"
        replacements.append((offset(begin["start"]), offset(end["end"]),
                             f"%% paper-writing translation {block['id']} source {block['digest']} begin\n"
                             f"{body}%% paper-writing translation {block['id']} end{terminator}"))
    for fragment in fragments:
        replacements.append((fragment["start"], fragment["end"], _fragment_entry(record, fragment)["spanish"]))
    out, cursor = [], 0
    for start, stop, replacement in sorted(replacements):
        out.append(source[cursor:start])
        out.append(replacement)
        cursor = stop
    out.append(source[cursor:])
    text = "".join(out)
    marker = "\\begin{document}"
    if marker in text:
        preamble, rest = text.split(marker, 1)
        preamble = _declare_spanish(preamble)
        preamble = _after_documentclass(preamble, "\\makeatletter\\def\\input@path{{../../}}\\makeatother\n")
        text = preamble + marker + rest
    text = _relocate(text, paper_dir)

    target = folder / "main.tex"
    record["built"] = {"at": _now(), "source_main_sha256": hashlib.sha256(data).hexdigest(),
                       "blocks": {b["id"]: b["digest"] for b in blocks},
                       "fragments": [f["id"] for f in fragments]}
    _atomic_write(target, text.encode("utf-8"))
    _write_json(folder / "translation.json", record)
    return {"ok": True, "lang": lang, "main_tex": _shown(paper_dir, target),
            "blocks": len(blocks), "language": paper_language.declared_language(text),
            "fragments": len(fragments),
            "compile": f"from {_shown(paper_dir, folder)}: pdflatex main, bibtex main, pdflatex main (twice)"}


def audit(paper_dir: Path, lang: str) -> dict:
    """The style audit of the stored Spanish blocks and the fidelity of each one
    against the current English; writes `audit.json`."""
    check_language(lang)
    record = _require_record(paper_dir, lang)
    _, blocks = _english(paper_dir, strict=False)
    folder = translation_dir(paper_dir, lang)
    stored = {b["id"]: (folder / "blocks" / f"{b['id']}.tex").read_text(encoding="utf-8")
              for b in blocks if (folder / "blocks" / f"{b['id']}.tex").is_file()}
    if not stored:
        raise Refused("TRANSLATION_NOTHING_STORED",
                      f"no Spanish block is stored under {_shown(paper_dir, folder / 'blocks')}; "
                      f"run `translate store` first")
    glossary = [t for t in record.get("glossary") or [] if isinstance(t, str)]
    report = paper_style_es.audit_document(stored, glossary=glossary)
    english = {b["id"]: b["body"] for b in blocks}
    fidelity = []
    for block_id, text in stored.items():
        differences = paper_style_es.compare_facts(english[block_id], text)
        fidelity.append({"id": block_id, "ok": not differences, "differences": differences})
    result = {"ok": True, "lang": lang, "generated_at": _now(), "notice": paper_style_es.NOTICE,
              "document": report["document"], "blocks": report["blocks"],
              "cross_block_redundancy": report["cross_block_redundancy"], "fidelity": fidelity}
    _write_json(folder / "audit.json", result)
    return result


def status(paper_dir: Path, lang: str) -> dict:
    """Read-only: every block's state, whether the Spanish file is built for the
    current English, the built and compiled paths, and the last audit."""
    check_language(lang)
    data, blocks = _english(paper_dir, strict=False)
    record = _read_record(paper_dir, lang)
    rows = _states(paper_dir, lang, blocks, record)
    folder = translation_dir(paper_dir, lang)
    main_tex = folder / "main.tex"
    pdf = folder / "main.pdf"
    built_record = (record or {}).get("built") if isinstance((record or {}).get("built"), dict) else {}
    fragment_rows = _fragment_states(record, fragments_of(data, blocks))
    stored_at = [r["stored_at"] for r in rows if r["stored_at"]] + [
        e.get("stored_at") for e in ((record or {}).get("fragments") or {}).values()
        if isinstance(e, dict) and e.get("stored_at")]
    built = (main_tex.is_file() and built_record.get("source_main_sha256") == hashlib.sha256(data).hexdigest()
             and all(r["state"] == "current" for r in rows + fragment_rows)
             and all(at <= (built_record.get("at") or "") for at in stored_at))
    last = None
    audit_path = folder / "audit.json"
    if audit_path.is_file():
        try:
            saved = json.loads(audit_path.read_text(encoding="utf-8"))
            document = saved.get("document") or {}
            last = {"generated_at": saved.get("generated_at"), "index": document.get("index"),
                    "verdict": document.get("verdict")}
        except (OSError, ValueError, AttributeError):
            last = None
    return {"ok": True, "lang": lang, "blocks": rows, "counts": _counts(rows), "built": bool(built),
            "main_tex": _shown(paper_dir, main_tex) if main_tex.is_file() else None,
            "pdf": _shown(paper_dir, pdf) if pdf.is_file() else None, "audit": last,
            "fragments": fragment_rows, "fragment_counts": _counts(fragment_rows)}
