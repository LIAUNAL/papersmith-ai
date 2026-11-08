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

The proposal's two concept trees raise that bar. ``novelty.problem_tree`` holds
the problem tree and each hypothesis names its ``pillars``:

    {"problem_tree": {"central": {"text": "..."},
                      "causes": [{"id": "DC1", "text": "..."}],
                      "effects": [{"id": "EF1", "text": "...", "caused_by": ["DC1"]}]},
     "pillars": [{"id": "C1", ...}], "hypotheses": [{"id": "E1", "pillars": ["C1"]}]}

``tree_findings`` checks their shape, language and wording: every statement in
English, 2 to 3 direct causes, each
reaching an effect; at least 2 pillars, each reaching a hypothesis; and a central
problem and causes that state a negative condition. The central problem and each
cause are ideas too (``problem:central``, ``cause:DC1``), and the citations of
those two kinds, of pillars and of hypotheses must be Q1 or Q2 journal articles
at most 4 years old. Quartile, work type and published year come from
``sota-pool/journal-ranks.json``, written by ``citations_cli.py rank`` from the
SJR table: a quartile from any other source does not count. A preprint also
counts when an author belongs to a lab of ``ACCEPTED_LABS``, found in OpenAlex or
confirmed by the operator with ``citations_cli.py lab``; the age limit still holds.
Layers, equations
and experiments keep the plain rule, so a foundational reference stays citable
there. What ``tree_findings`` reports owes under the proposal stage as
``tree:<node>: <reason>``, so Phase 4's citations step stays open on it.

Read-only, bounded and never raises. This module has no dependencies, so the
gates and the dashboard load it by path; the two small parsers below stay here
because ``math_view`` and ``experiments_view`` belong to the dashboard's
package, and tests hold them to the same answers.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = 1
CITATIONS_REL = ".papersmith/citations.json"
SPEC_REL = ".papersmith/model_spec.json"
POOL_REL = "sota-pool/candidates.json"
RANKS_REL = "sota-pool/journal-ranks.json"

MIN_CITATIONS = 2
MAX_CITATIONS = 5
MAX_WHY = 300
#: A citation quotes the span of its reference's abstract that holds the idea
#: (#160): verbatim, whitespace aside, between these lengths.
MIN_QUOTE = 20
MAX_QUOTE = 300
MAX_TEXT = 300
MAX_AUTHORS = 20
MAX_EQUATIONS = 40
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_POOL_BYTES = 16 * 1024 * 1024
MAX_PROTOCOL_BYTES = 1024 * 1024
MIN_CAUSES = 2
MAX_CAUSES = 3
MIN_PILLARS = 2
#: A tree statement's length in lines of this many characters: the central problem
#: takes at most four, every cause, effect, pillar and hypothesis at most three.
LINE_CHARS = 100
PROBLEM_LINES = 4
ITEM_LINES = 3
MAX_REFERENCE_AGE = 4
ACCEPTED_QUARTILES = ("Q1", "Q2")
#: Research labs whose preprints support the concept trees, by ROR id.
ACCEPTED_LABS = {
    "00njsd438": "Google", "00971b260": "Google DeepMind", "05wx9n238": "OpenAI", "056y0v115": "Anthropic",
    "00d0nc645": "Microsoft", "0300m5276": "Microsoft", "05k87vq12": "Microsoft",
    "01zbnvs85": "Meta", "02388em19": "Meta", "020ye1821": "Meta",
    "03jdj4y14": "NVIDIA", "02kr42612": "NVIDIA", "059hsda18": "Apple",
    "05hh8d621": "IBM", "0265w5591": "IBM", "005w8dd04": "IBM", "04mv4n011": "Amazon",
    "05w520734": "Allen Institute for AI", "05qj0n416": "Xanadu", "03ssvsv78": "Quantinuum",
    "0507j3z22": "Quantinuum", "02ft1jb97": "IonQ",
}
LAB_SOURCES = ("openalex", "operator")
#: The ideas of the two concept trees, whose references must pass the journal rule.
TREE_KINDS = ("problem", "cause", "pillar", "hypothesis")

#: The two stages an idea belongs to: Phase 4's step reads the proposal's,
#: the implementation actions and G-EXP-POC the experiments'.
STAGE_KINDS = {"proposal": ("problem", "cause", "pillar", "hypothesis", "layer", "equation"),
               "experiments": ("experiment",)}

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:")
_ARXIV_PREFIX = re.compile(r"^(?:https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/|arxiv:)", re.IGNORECASE)
_ARXIV_ID = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?$")
#: A managed revision, with or without a slug: research-concept-r44.md and
#: research-concept-eeg-r07.md both are, as Phase 4 reads them.
_REVISION = re.compile(r"^research-concept-(?:.+-)?r(\d+)\.md$")
_PROTOCOL = re.compile(r"^experiments-.+-v(\d+)\.md$")
#: An experiment declares [exp:<id>] in its own heading, at any level
#: (skills/_core/conventions/experiments.json), as the Experiments tab reads it.
_EXPERIMENT = re.compile(r"^#{1,6}\s+.*?\[exp:([^\]]+)\]")
_TAG = re.compile(r"\\tag\{([^{}]*)\}")
_FENCE = re.compile(r"^(```|~~~)")
_CAUSE_ID = re.compile(r"^DC\d+$")
_WORD = re.compile(r"[^\W\d_]+")
_FORMULA = re.compile(r"\$[^$]*\$")
_ACCENT = re.compile(r"[áéíóúñ]")
#: Common words of these statements, outside English prose as lowercase words,
#: and Spanish function words of which one alone can be English (``de novo``), so
#: two are needed.
_SPANISH_WORDS = frozenset({
    "datos", "ruidosos", "baja", "bajo", "sujetos", "señal", "efecto", "efectos", "circuito", "circuitos",
    "modelo", "modelos", "ganancia", "variabilidad", "profundidad", "entre", "sobre", "mediante", "según",
    "cuando", "muestra", "causa", "causas", "pilar", "pilares"})
_SPANISH_GLUE = frozenset({"de", "del", "la", "las", "el", "los", "en", "que", "con", "por", "para", "una", "un",
                           "se", "y"})
#: Openers that name an absent solution instead of a negative condition.
_ABSENCE = re.compile(r"^(?:(?:(?:the|an?)\s+)?(?:(?:lack|absence|shortage|deficiency|nonexistence)\s+of\b"
                      r"|need(?:s|ed)?\b)|there\s+(?:is|are)\s+(?:no\b|an?\s+(?:lack|absence|shortage|need)\b)"
                      r"|no\s|not\s|requires?\b|required\b|to\s+(?!date\b)\w)", re.IGNORECASE)


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
    index = 0
    fence: str | None = None
    while index < len(lines) and len(tags) < MAX_EQUATIONS:
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
        if tag and _TAG.sub("", body).strip():
            tags.append(tag.group(1).strip())
        index = end + 1
    return tags


def _experiments(root: Path) -> list[str]:
    path = _latest(root / "experiments", root, _PROTOCOL)
    text = _text(path, root, MAX_PROTOCOL_BYTES) if path else None
    matches = (_EXPERIMENT.match(line.strip()) for line in (text or "").splitlines())
    return [match.group(1).strip()[:40] for match in matches if match]


def _reads_spanish(text: str) -> bool:
    """Whether a short statement is Spanish. ``paper_language.is_spanish_prose``
    is built for paragraphs and misses most short phrases. It is a heuristic: a
    capitalized word can be a name, so it counts only as the sentence's first
    word, and the particles of a surname (``de la Cruz``) count as nothing."""
    words = _WORD.findall(_FORMULA.sub(" ", text))
    prose = [word for index, word in enumerate(words)
             if (word[0].islower() or index == 0)
             and not (index + 1 < len(words) and word.lower() in _SPANISH_GLUE
                      and (words[index + 1][0].isupper() or words[index + 1].lower() in _SPANISH_GLUE
                           and index + 2 < len(words) and words[index + 2][0].isupper()))]
    lowered = [word.lower() for word in prose]
    return (any(word[0].islower() and _ACCENT.search(word) for word in prose)
            or bool(_SPANISH_WORDS.intersection(lowered))
            or len(_SPANISH_GLUE.intersection(lowered)) >= 2)


def _language(node: str, *texts: Any) -> list[str]:
    """The tree's statements are English whatever the conversation's language."""
    if any(isinstance(text, str) and _reads_spanish(text) for text in texts):
        return [f"tree:{node}: must be written in English"]
    return []


def _names(value: Any) -> list[str]:
    """The non-blank strings of a list."""
    return [item.strip() for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def _wording(node: str, text: str) -> list[str]:
    """A tree statement names a negative condition, never a missing solution."""
    opener = text.strip()
    if not _ABSENCE.match(opener):
        return []
    return [f"tree:{node}: must state a negative condition, not open with {opener.split()[0]!r}"]


def _length(node: str, lines: int, *texts: Any) -> list[str]:
    """A tree statement is short enough to read at a glance."""
    limit = lines * LINE_CHARS
    return [f"tree:{node}: is {len(text.strip())} characters, at most {limit} ({lines} lines)"
            for text in texts if isinstance(text, str) and len(text.strip()) > limit]


def _problem_tree_findings(tree: Any) -> list[str]:
    if not isinstance(tree, dict):
        return ["tree:problem: novelty.problem_tree is missing"]
    found: list[str] = []
    central = tree.get("central") if isinstance(tree.get("central"), dict) else {}
    text = central.get("text")
    if isinstance(text, str) and text.strip():
        found += _wording("central", text) + _language("central", text) + _length("central", PROBLEM_LINES, text)
    else:
        found.append("tree:central: has no text")
    causes = _listed(tree.get("causes"), "text")
    if not MIN_CAUSES <= len(causes) <= MAX_CAUSES:
        found.append(f"tree:causes: {len(causes)} direct cause(s), needs {MIN_CAUSES} to {MAX_CAUSES}")
    ids: list[str] = []
    for position, cause in enumerate(causes, 1):
        ident = _id(cause, "DC", position)
        if not _CAUSE_ID.match(ident):
            found.append(f"tree:causes: id {ident!r} must look like DC1")
        if ident in ids:
            found.append(f"tree:causes: duplicate id {ident!r}")
        ids.append(ident)
        found += (_wording(ident, cause["text"]) + _language(ident, cause["text"])
                  + _length(ident, ITEM_LINES, cause["text"]))
    effects = _listed(tree.get("effects"), "text")
    if not effects:
        found.append("tree:effects: needs at least 1 effect")
    reached: set[str] = set()
    for position, effect in enumerate(effects, 1):
        found += (_wording(_id(effect, "EF", position), effect["text"])
                  + _language(_id(effect, "EF", position), effect["text"])
                  + _length(_id(effect, "EF", position), ITEM_LINES, effect["text"]))
        for name in _names(effect.get("caused_by")):
            if name in ids:
                reached.add(name)
            else:
                found.append(f"tree:effects: {_id(effect, 'EF', position)} names unknown cause {name}")
    if effects:
        found += [f"tree:effects: cause {ident} has no effect" for ident in ids if ident not in reached]
    return found


def tree_findings(novelty: dict[str, Any]) -> list[str]:
    """What the two concept trees of ``novelty`` still owe, ``[]`` when both hold."""
    found = _problem_tree_findings(novelty.get("problem_tree"))
    pillars = _listed(novelty.get("pillars"), "name", "summary")
    if len(pillars) < MIN_PILLARS:
        found.append(f"tree:pillars: {len(pillars)} pillar(s), needs at least {MIN_PILLARS}")
    ids = [_id(item, "P", n) for n, item in enumerate(pillars, 1)]
    for ident, item in zip(ids, pillars):
        found += _language(ident, item.get("name")) + _length(ident, ITEM_LINES, item.get("name"), item.get("summary"))
    found += [f"tree:pillars: duplicate id {ident!r}" for ident in sorted({i for i in ids if ids.count(i) > 1})]
    reached: set[str] = set()
    seen: set[str] = set()
    for position, hypothesis in enumerate(_listed(novelty.get("hypotheses"), "title", "statement"), 1):
        ident = _id(hypothesis, "H", position)
        if ident in seen:
            found.append(f"tree:hypotheses: duplicate id {ident!r}")
        seen.add(ident)
        found += (_language(ident, hypothesis.get("title"), hypothesis.get("statement"))
                  + _length(ident, ITEM_LINES, hypothesis.get("title"), hypothesis.get("statement")))
        names = _names(hypothesis.get("pillars"))
        if not names:
            found.append(f"tree:hypotheses: {ident} names no pillar")
        for name in names:
            if name in ids:
                reached.add(name)
            else:
                found.append(f"tree:hypotheses: {ident} names unknown pillar {name}")
    found += [f"tree:pillars: {ident} reaches no hypothesis" for ident in ids if ident not in reached]
    return found


def _novelty(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """The specification and its ``novelty`` block, both empty when absent."""
    spec = _json(root / SPEC_REL, root)
    spec = spec if isinstance(spec, dict) else {}
    return spec, spec.get("novelty") if isinstance(spec.get("novelty"), dict) else {}


def _tree_ideas(novelty: dict[str, Any]) -> list[tuple[str, str]]:
    tree = novelty.get("problem_tree") if isinstance(novelty.get("problem_tree"), dict) else {}
    central = tree.get("central") if isinstance(tree.get("central"), dict) else {}
    found = [("problem", "central")] if _listed([central], "text") else []
    return found + [("cause", _id(item, "DC", n)) for n, item in enumerate(_listed(tree.get("causes"), "text"), 1)]


def _ideas(root: Path) -> list[tuple[str, str]]:
    """Every ``(kind, id)`` of the workspace, in the panels' order, each once."""
    spec, novelty = _novelty(root)
    proposal = _latest(root / "proposals", root, _REVISION)
    sky = _json(proposal.with_suffix(".sky.json"), root) if proposal else None
    sky = sky if isinstance(sky, dict) else {}
    pillars = _listed(novelty.get("pillars"), "name", "summary") or _listed(sky.get("pillars"), "label", "detail")
    hypotheses = (_listed(novelty.get("hypotheses"), "title", "statement")
                  or _listed(sky.get("hypotheses"), "statement"))
    source = spec.get("concept_map") or spec.get("conceptual_map")
    layers = source.get("layers") if isinstance(source, dict) else None
    layers = [item for item in layers if isinstance(item, dict)] if isinstance(layers, list) else []
    found = _tree_ideas(novelty)
    found += [("pillar", _id(item, "P", n)) for n, item in enumerate(pillars, 1)]
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


def _ranks(root: Path) -> dict[str, dict[str, Any]]:
    """The journal ranks of ``citations_cli.py rank`` by normalized identifier."""
    data = _json(root / RANKS_REL, root, MAX_POOL_BYTES)
    ranks = data.get("ranks") if isinstance(data, dict) else None
    found: dict[str, dict[str, Any]] = {}
    for identifier, rank in ranks.items() if isinstance(ranks, dict) else []:
        identity = normalize(identifier)
        if identity and isinstance(rank, dict):
            found[identity] = rank
    return found


def _year(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _lab(rank: dict[str, Any] | None) -> str:
    """The accepted lab behind a preprint, ``""`` when it has none."""
    rank = rank or {}
    lab = rank.get("lab")
    return lab if lab in ACCEPTED_LABS.values() and rank.get("lab_source") in LAB_SOURCES else ""


def _journal_problems(key: str, label: str, record: dict[str, Any], rank: dict[str, Any] | None) -> list[str]:
    """Why a reference cannot support an idea of the concept trees."""
    rank = rank or {}
    found = []
    if _lab(rank):
        pass
    elif rank.get("work_type") == "preprint":
        found.append(f"{key}: {label!r} has no SJR quartile and no accepted lab")
    elif rank.get("quartile_source") != "sjr" or not rank.get("quartile"):
        found.append(f"{key}: {label!r} has no SJR quartile")
    elif rank.get("work_type") != "journal-article":
        found.append(f"{key}: {label!r} is not a journal article")
    elif rank["quartile"] not in ACCEPTED_QUARTILES:
        found.append(f"{key}: {label!r} is {rank['quartile']}, needs Q1 or Q2")
    year = _year(rank.get("year")) or _year(record.get("year"))
    oldest = datetime.date.today().year - MAX_REFERENCE_AGE
    if year is None:
        found.append(f"{key}: {label!r} has no publication year")
    elif year < oldest:
        found.append(f"{key}: {label!r} is from {year}, needs {oldest} or later")
    return found


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


def problems(key: str, entries: Any, pool: dict[str, dict[str, Any]],
             ranks: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """What is wrong with one idea's citations, ``[]`` when they are valid. With
    ``ranks``, the ideas of the concept trees also pass the journal rule."""
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
        else:
            if ranks is not None and key.split(":", 1)[0] in TREE_KINDS:
                found += _journal_problems(key, entry["id"].strip(), pool[identity], ranks.get(identity))
            found += _quote_problems(key, position, entry, pool[identity])
        if identity:
            seen.add(identity)
        why = entry.get("why")
        if not (isinstance(why, str) and why.strip()):
            found.append(f"{key}: entry {position} has no why")
        elif len(why) > MAX_WHY:
            found.append(f"{key}: entry {position} why is longer than {MAX_WHY} characters")
        elif ranks is not None and key.split(":", 1)[0] in TREE_KINDS and _reads_spanish(why):
            found.append(f"{key}: entry {position} why must be written in English")
    return found


def _spaced(text: Any) -> str:
    return " ".join(text.split()) if isinstance(text, str) else ""


def _quote_problems(key: str, position: int, entry: dict[str, Any], record: dict[str, Any]) -> list[str]:
    """Whether a citation quotes, verbatim, the abstract of its pool reference."""
    abstract = _spaced(record.get("abstract"))
    if not abstract:
        return [f"{key}: {entry['id'].strip()!r} has no abstract in {POOL_REL} to quote"]
    quote = entry.get("quote")
    if not (isinstance(quote, str) and quote.strip()):
        return [f"{key}: entry {position} has no quote"]
    quote = _spaced(quote)
    if len(quote) < MIN_QUOTE:
        return [f"{key}: entry {position} quote is shorter than {MIN_QUOTE} characters"]
    if len(quote) > MAX_QUOTE:
        return [f"{key}: entry {position} quote is longer than {MAX_QUOTE} characters"]
    if not _holds(abstract, quote):
        return [f"{key}: entry {position} quote is not in the abstract of {entry['id'].strip()!r}"]
    return []


def _holds(abstract: str, quote: str) -> bool:
    """Whether ``quote`` is a span of ``abstract`` that starts and ends on word
    boundaries, so a fragment of a word never counts as a quote."""
    return re.search(r"(?<!\w)" + re.escape(quote) + r"(?!\w)", abstract) is not None


def routes(recorded: dict[str, Any], pool: dict[str, dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    """The reverse map: each pool reference, in pool order, with the current
    ideas that cite it, the quote each one takes from its abstract and whether
    that quote is grounded (verbatim in the abstract, as ``check`` requires)."""
    found: dict[str, list[dict[str, str]]] = {identity: [] for identity in pool}
    for key in keys:
        entries = recorded.get(key)
        for entry in (entries if isinstance(entries, list) else [])[:MAX_CITATIONS]:
            identity = normalize(entry.get("id")) if isinstance(entry, dict) else None
            if identity in found and all(item["key"] != key for item in found[identity]):
                quote = _spaced(entry.get("quote"))
                grounded = bool(quote) and not _quote_problems(key, 0, entry, pool[identity])
                found[identity].append({"key": key, "quote": _clip(quote), "grounded": grounded})
    return [{"id": _clip(record.get("identifier")), "title": _clip(record.get("title")), "ideas": found[identity]}
            for identity, record in pool.items()]


def _clip(value: Any) -> str:
    return value.strip()[:MAX_TEXT] if isinstance(value, str) else ""


def _shown(entries: Any, pool: dict[str, dict[str, Any]],
           ranks: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """An idea's citations as the panels show them, joined to the pool's record."""
    shown = []
    for entry in (entries if isinstance(entries, list) else [])[:MAX_CITATIONS]:
        if not isinstance(entry, dict) or normalize(entry.get("id")) is None:
            continue
        record = pool.get(normalize(entry["id"]), {})
        year = record.get("year")
        authors = record.get("authors")
        lab = _lab((ranks or {}).get(normalize(entry["id"])))
        shown.append({**({"lab": lab} if lab else {}),
                      "id": _clip(entry["id"]), "why": _clip(entry.get("why")),
                      **({"quote": _clip(_spaced(entry["quote"]))} if _spaced(entry.get("quote")) else {}),
                      "title": _clip(record.get("title")),
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
        return {"ideas": [], "stages": stages, "file_problems": [], "trees": [], "routes": []}
    recorded, file_problems = _recorded(root)
    pool = _pool(root)
    ranks = _ranks(root)
    ideas = []
    for kind, ident in _ideas(root):
        key = f"{kind}:{ident}"
        entries = recorded.get(key)
        found = list(file_problems) or problems(key, entries, pool, ranks)
        ideas.append({"key": key, "kind": kind, "id": ident, "owed": bool(found), "problems": found,
                      "citations": _shown(entries, pool, ranks)})
        stage = stages["experiments" if kind in STAGE_KINDS["experiments"] else "proposal"]
        stage["ideas"] += 1
        if found:
            stage["owed"].append(key)
        else:
            stage["cited"] += 1
    trees = tree_findings(_novelty(root)[1]) if stages["proposal"]["ideas"] else []
    stages["proposal"]["owed"] += trees
    return {"ideas": ideas, "stages": stages, "file_problems": file_problems, "trees": trees,
            "routes": routes(recorded, pool, [idea["key"] for idea in ideas])}


__all__ = ["ACCEPTED_LABS", "ACCEPTED_QUARTILES", "CITATIONS_REL", "MAX_CITATIONS", "MAX_QUOTE", "MAX_REFERENCE_AGE", "MAX_WHY", "MIN_CITATIONS", "MIN_QUOTE",
           "POOL_REL", "RANKS_REL", "SCHEMA", "STAGE_KINDS", "TREE_KINDS", "normalize", "problems", "routes", "state",
           "tree_findings"]
