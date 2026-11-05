"""The SOTA citations that justify each idea: `.papersmith/citations.json` (schema 1).

Every idea of the proposal and of the experimental protocol names 2 to 5
references of the SOTA pool and says how each one supports it:

    {"schema": 1, "ideas": {"pillar:P1": [{"id": "<pool identifier>", "why": "<reason>"}],
                            "hypothesis:H1": [...], "layer:<layer name>": [...],
                            "equation:1": [...], "experiment:E1": [...]}}

The ideas are read from the workspace, never from this file:

- pillars and hypotheses from ``.papersmith/model_spec.json`` (``novelty``), or
  the latest revision's ``.sky.json`` overlay when the specification has none;
  an idea without an ``id`` takes its position (``P1``, ``H1``);
- layers from ``concept_map`` or ``conceptual_map`` in that specification;
- equations from the ``\\tag{N}`` display blocks of the latest revision, the
  same blocks ``command_center/math_view.py`` counts;
- experiments from the ``## Experiment [exp:<id>]`` headings of the latest
  ``experiments/experiments-<slug>-vNN.md``, as ``experiments_view.py`` parses them.

A valid idea has 2 to 5 entries with distinct ids, each id in
``sota-pool/candidates.json`` (``candidates[].identifier``, compared normalized
with the semantics of ``paper_bib.source_identity``) and a non-blank ``why`` of
at most 300 characters. An idea absent from the file owes its citations; a key
for an idea that no longer exists is ignored; a kind with no ideas owes nothing.
Validity means pool membership and a stated reason: it does not prove that the
reference supports the idea.

Read-only, bounded and never raises. This module has no dependencies, so the
gates and the dashboard load it by path; the two small parsers below stay here
because ``math_view`` and ``experiments_view`` belong to the dashboard's
package, and tests hold them to the same answers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA = 1
CITATIONS_REL = ".papersmith/citations.json"
SPEC_REL = ".papersmith/model_spec.json"
POOL_REL = "sota-pool/candidates.json"

MIN_CITATIONS = 2
MAX_CITATIONS = 5
MAX_WHY = 300
MAX_TEXT = 300
MAX_AUTHORS = 20
MAX_EQUATIONS = 40
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_POOL_BYTES = 16 * 1024 * 1024
MAX_PROTOCOL_BYTES = 1024 * 1024

#: The two stages an idea belongs to: Phase 4's step reads the proposal's,
#: the implementation actions and G-EXP-POC the experiments'.
STAGE_KINDS = {"proposal": ("pillar", "hypothesis", "layer", "equation"), "experiments": ("experiment",)}

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:")
_ARXIV_PREFIX = re.compile(r"^(?:https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/|arxiv:)", re.IGNORECASE)
_ARXIV_ID = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?$")
_REVISION = re.compile(r"^research-concept-.+-r(\d+)\.md$")
_PROTOCOL = re.compile(r"^experiments-.+-v(\d+)\.md$")
_EXPERIMENT = re.compile(r"^##\s+Experiment\s+\[exp:([^\]]+)\]")
_TAG = re.compile(r"\\tag\{([^{}]*)\}")
_FENCE = re.compile(r"^(```|~~~)")


def normalize(identifier: Any) -> str | None:
    """The one comparable form of a pool identifier, ``None`` when it names
    nothing: a DOI loses its URL or ``doi:`` prefix and its case; an arXiv id
    loses its ``arXiv:`` prefix or URL and a trailing ``.pdf`` and keeps its
    version. A DOI never equals an arXiv id."""
    if not isinstance(identifier, str) or not identifier.strip():
        return None
    text = identifier.strip()
    if _ARXIV_PREFIX.match(text):
        return "arxiv:" + _bare_arxiv(_ARXIV_PREFIX.sub("", text))
    lowered = text.lower()
    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            return "doi:" + lowered[len(prefix):]
    if lowered.startswith("10."):
        return "doi:" + lowered
    bare = _bare_arxiv(text)
    return ("arxiv:" + bare) if _ARXIV_ID.match(bare) else ("other:" + lowered)


def _bare_arxiv(text: str) -> str:
    lowered = text.lower()
    return lowered[:-4] if lowered.endswith(".pdf") else lowered


def _text(path: Path, root: Path, limit: int) -> str | None:
    """A bounded read of a file that resolves inside the workspace."""
    try:
        if not path.resolve().is_relative_to(root) or not path.is_file() or path.stat().st_size > limit:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def _json(path: Path, root: Path, limit: int = MAX_FILE_BYTES) -> Any:
    try:
        return json.loads(_text(path, root, limit) or "null")
    except (ValueError, RecursionError):
        return None


def _latest(folder: Path, root: Path, pattern: re.Pattern[str]) -> Path | None:
    """The highest numbered file of ``folder`` whose name matches ``pattern``."""
    ranked = []
    try:
        for path in folder.iterdir():
            match = pattern.match(path.name)
            if match and path.is_file() and path.resolve().is_relative_to(root):
                ranked.append((int(match.group(1)), path.name, path))
    except OSError:
        return None
    return max(ranked)[2] if ranked else None


def _listed(value: Any, *fields: str) -> list[dict[str, Any]]:
    """The entries of a list that are objects with a non-blank field."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and any(
        isinstance(item.get(f), str) and item[f].strip() for f in fields)]


def _id(item: dict[str, Any], prefix: str, position: int) -> str:
    value = item.get("id")
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return f"{prefix}{position}"


def _tags(text: str) -> list[str]:
    """The ``\\tag{N}`` of each closed ``$$`` display block, as
    ``math_view.tagged_equation_count`` counts them: a fenced block only shows
    LaTeX, and an unclosed one ends the reading."""
    lines = text.splitlines()
    tags: list[str] = []
    blocks = 0
    index = 0
    fence: str | None = None
    while index < len(lines) and blocks < MAX_EQUATIONS:
        line = lines[index].strip()
        fence_match = _FENCE.match(line)
        if fence_match and (fence is None or fence_match.group(1) == fence):
            fence = None if fence else fence_match.group(1)
            index += 1
            continue
        if fence or line != "$$":
            index += 1
            continue
        end = next((j for j in range(index + 1, len(lines)) if lines[j].strip() == "$$"), None)
        if end is None:
            break
        body = "\n".join(lines[index + 1:end]).strip()
        tag = _TAG.search(body)
        if _TAG.sub("", body).strip():
            blocks += 1
            if tag:
                tags.append(tag.group(1).strip())
        index = end + 1
    return tags


def _experiments(root: Path) -> list[str]:
    path = _latest(root / "experiments", root, _PROTOCOL)
    text = _text(path, root, MAX_PROTOCOL_BYTES) if path else None
    matches = (_EXPERIMENT.match(line.strip()) for line in (text or "").splitlines())
    return [match.group(1).strip()[:40] for match in matches if match]


def _ideas(root: Path) -> list[tuple[str, str]]:
    """Every ``(kind, id)`` of the workspace, in the panels' order, each once."""
    spec = _json(root / SPEC_REL, root)
    spec = spec if isinstance(spec, dict) else {}
    novelty = spec.get("novelty") if isinstance(spec.get("novelty"), dict) else {}
    proposal = _latest(root / "proposals", root, _REVISION)
    sky = _json(proposal.with_suffix(".sky.json"), root) if proposal else None
    sky = sky if isinstance(sky, dict) else {}
    pillars = _listed(novelty.get("pillars"), "name", "summary") or _listed(sky.get("pillars"), "label", "detail")
    hypotheses = (_listed(novelty.get("hypotheses"), "title", "statement")
                  or _listed(sky.get("hypotheses"), "statement"))
    source = spec.get("concept_map") or spec.get("conceptual_map")
    layers = source.get("layers") if isinstance(source, dict) else None
    layers = [item for item in layers if isinstance(item, dict)] if isinstance(layers, list) else []
    found = [("pillar", _id(item, "P", n)) for n, item in enumerate(pillars, 1)]
    found += [("hypothesis", _id(item, "H", n)) for n, item in enumerate(hypotheses, 1)]
    for n, layer in enumerate(layers, 1):
        name = next((layer[f].strip() for f in ("name", "layer")
                     if isinstance(layer.get(f), str) and layer[f].strip()), f"L{n}")
        found.append(("layer", name))
    revision = _text(proposal, root, MAX_FILE_BYTES) if proposal else None
    found += [("equation", tag) for tag in _tags(revision or "")]
    found += [("experiment", exp) for exp in _experiments(root)]
    return list(dict.fromkeys(found))


def _pool(root: Path) -> dict[str, dict[str, Any]]:
    """The pool's references by their normalized identifier."""
    data = _json(root / POOL_REL, root, MAX_POOL_BYTES)
    entries = data.get("candidates") if isinstance(data, dict) else None
    pool: dict[str, dict[str, Any]] = {}
    for entry in entries if isinstance(entries, list) else []:
        identity = normalize(entry.get("identifier")) if isinstance(entry, dict) else None
        if identity:
            pool.setdefault(identity, entry)
    return pool


def _recorded(root: Path) -> tuple[dict[str, Any], list[str]]:
    """The ``ideas`` of the citations file and what is wrong with the file; a
    file that is not there is no problem, its ideas simply owe citations."""
    path = root / CITATIONS_REL
    try:
        if not path.exists():
            return {}, []
    except OSError:
        return {}, [f"{CITATIONS_REL}: unreadable"]
    data = _json(path, root)
    if not isinstance(data, dict):
        return {}, [f"{CITATIONS_REL}: must be a JSON object within {MAX_FILE_BYTES} bytes"]
    if data.get("schema") != SCHEMA:
        return {}, [f"{CITATIONS_REL}: schema must be {SCHEMA}"]
    if not isinstance(data.get("ideas"), dict):
        return {}, [f"{CITATIONS_REL}: ideas must be an object"]
    return data["ideas"], []


def problems(key: str, entries: Any, pool: dict[str, dict[str, Any]]) -> list[str]:
    """What is wrong with one idea's citations, ``[]`` when they are valid."""
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        return [f"{key}: must be a list of citations"]
    found = []
    if not MIN_CITATIONS <= len(entries) <= MAX_CITATIONS:
        found.append(f"{key}: {len(entries)} citation(s), needs {MIN_CITATIONS} to {MAX_CITATIONS}")
    seen: set[str] = set()
    for position, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            found.append(f"{key}: entry {position} is not an object")
            continue
        identity = normalize(entry.get("id"))
        if identity is None:
            found.append(f"{key}: entry {position} has no id")
        elif identity in seen:
            found.append(f"{key}: duplicate id {entry['id'].strip()!r}")
        elif identity not in pool:
            found.append(f"{key}: {entry['id'].strip()!r} is not in {POOL_REL}")
        if identity:
            seen.add(identity)
        why = entry.get("why")
        if not (isinstance(why, str) and why.strip()):
            found.append(f"{key}: entry {position} has no why")
        elif len(why) > MAX_WHY:
            found.append(f"{key}: entry {position} why is longer than {MAX_WHY} characters")
    return found


def _clip(value: Any) -> str:
    return value.strip()[:MAX_TEXT] if isinstance(value, str) else ""


def _shown(entries: Any, pool: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """An idea's citations as the panels show them, joined to the pool's record."""
    shown = []
    for entry in (entries if isinstance(entries, list) else [])[:MAX_CITATIONS]:
        if not isinstance(entry, dict) or normalize(entry.get("id")) is None:
            continue
        record = pool.get(normalize(entry["id"]), {})
        year = record.get("year")
        authors = record.get("authors")
        shown.append({"id": _clip(entry["id"]), "why": _clip(entry.get("why")), "title": _clip(record.get("title")),
                      "year": year if isinstance(year, int) and not isinstance(year, bool) else _clip(year),
                      "authors": ([_clip(a) for a in authors[:MAX_AUTHORS]] if isinstance(authors, list)
                                  else _clip(authors)),
                      "venue": _clip(record.get("venue"))})
    return shown


def state(root: Path | str) -> dict[str, Any]:
    """Each idea with its citations and problems, and per stage how many ideas
    there are, how many are cited and which keys still owe."""
    stages: dict[str, dict[str, Any]] = {name: {"ideas": 0, "cited": 0, "owed": []} for name in STAGE_KINDS}
    try:
        root = Path(root).expanduser().resolve()
    except (OSError, RuntimeError):
        return {"ideas": [], "stages": stages, "file_problems": []}
    recorded, file_problems = _recorded(root)
    pool = _pool(root)
    ideas = []
    for kind, ident in _ideas(root):
        key = f"{kind}:{ident}"
        entries = recorded.get(key)
        found = list(file_problems) or problems(key, entries, pool)
        ideas.append({"key": key, "kind": kind, "id": ident, "owed": bool(found), "problems": found,
                      "citations": _shown(entries, pool)})
        stage = stages["experiments" if kind in STAGE_KINDS["experiments"] else "proposal"]
        stage["ideas"] += 1
        if found:
            stage["owed"].append(key)
        else:
            stage["cited"] += 1
    return {"ideas": ideas, "stages": stages, "file_problems": file_problems}


__all__ = ["CITATIONS_REL", "MAX_CITATIONS", "MAX_WHY", "MIN_CITATIONS", "POOL_REL", "SCHEMA", "STAGE_KINDS",
           "normalize", "problems", "state"]
