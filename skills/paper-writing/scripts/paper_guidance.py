"""paper_guidance: per-folder `guidance/<folder>` class registry.

Classifies each folder under `guidance/` as `style-reference` or `evidence`
by reading a per-folder marker file, `guidance/<folder>/.paper-writing.json`
— never by reading the folder's name. A folder carrying no marker is
reported `unclassified`, including every folder on a fresh clone, where no
marker files exist yet. That is designed behavior, not a default and not a
fault (`specs/guidance-registry/spec.md`).

`guidance/` is not a fact source (`design.md`, `A fact the agent may
observe is a partition, not a guideline`); this registry feeds the
style/evidence classification `plan` reports AND, since
`the-skill-stops-trusting-memory` item 2/3, gates `validate --source-md`:
`classify_source_md` is what `paper_cli._build_evidence_record` calls to
refuse a quote sourced from a `style-reference`-classed folder and accept
one sourced from an `evidence`-classed folder -- the classification's own
first real consumer, not merely a label `plan` echoes back.

`ingested_papers(guidance_dir)` (`the-phases-are-derived-not-remembered`)
is a second, independent walk -- two levels deep, gitignore-blind by
`Path.iterdir()`'s own construction -- feeding `plan`/`packet`'s report of
which papers actually sit under `guidance/`.

`segment_markdown`/`read_markdown_outline` (unit 8, `redactor-packet`
spec) are a third, independent capability: a heading OUTLINE -- never
reference prose -- over one ingested paper's own markdown, which is what
lets `packet` hand the style-sampler agent a map of every reference
paper's structure without ever carrying a byte of its substantive
content itself (design.md, Decision D5).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_marker  # noqa: E402
import paper_scaffold  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: The closed two-value vocabulary a marker's `class` may hold
#: (`specs/guidance-registry/spec.md`, `Requirement: Per-Folder Marker
#: File`).
CLASSES: tuple[str, ...] = ("style-reference", "evidence")

_MARKER_NAME = ".paper-writing.json"
#: Derived from `paper_marker.SEAL_KEY`, never re-spelled as a second
#: literal (design.md Decision B; tasks.md 3.1) -- the source-root marker's
#: own `_SOURCE_MARKER_TOP_KEY` + `SEAL_KEY` pair is this module's sibling.
_MARKER_ALLOWED_KEYS = ("class", paper_marker.SEAL_KEY)


def resolve_guidance_dir(
    guidance_arg: str | None, *, forge_root: Path = paper_scaffold.FORGE_ROOT
) -> Path:
    """Resolve `--guidance <dir>` (or the default `<forge_root>/guidance`).

    Refuses `GUIDANCE_OUTSIDE_REPOSITORY` (invocation-defect) when the
    resolved path does not sit under `forge_root` — mirrors
    `paper_contract.resolve_sections_dir` exactly, at the same directory
    depth from this file.
    """
    root = forge_root.resolve()
    target = Path(guidance_arg).resolve() if guidance_arg else (root / "guidance")
    try:
        target.relative_to(root)
    except ValueError:
        raise Refused(
            "GUIDANCE_OUTSIDE_REPOSITORY",
            f"{target} does not resolve inside the repository root {root}",
        )
    return target


def _validate_class_obj(obj, marker_path) -> str:
    """The `class` shape-checking body `_classify` used to carry inline,
    extracted unchanged (tasks.md 3.2: a PURE extraction, zero behavior
    change here). The seal key is entirely this function's caller's own
    concern -- stripped from `obj` before this ever runs, so this
    function's own grammar is exactly what it was before sealing existed:
    exactly one admitted key, `class`, nothing else. Returns the validated
    class value. Refuses `MALFORMED_GUIDANCE_MARKER` naming the offending
    file and the missing or unknown key, or `UNKNOWN_GUIDANCE_CLASS` naming
    the offending value -- byte-identical to this reader's own prior inline
    body."""
    if not isinstance(obj, dict):
        raise Refused("MALFORMED_GUIDANCE_MARKER", f"{marker_path}: must be a JSON object")
    unknown = [key for key in obj if key not in _MARKER_ALLOWED_KEYS]
    if unknown:
        raise Refused(
            "MALFORMED_GUIDANCE_MARKER", f"{marker_path}: carries unknown key {unknown[0]!r}"
        )
    if "class" not in obj:
        raise Refused("MALFORMED_GUIDANCE_MARKER", f"{marker_path}: missing required key 'class'")
    value = obj["class"]
    if value not in CLASSES:
        raise Refused(
            "UNKNOWN_GUIDANCE_CLASS",
            f"{marker_path}: {value!r} is not one of the declared classes {CLASSES}",
        )
    return value


def _read_marker(folder: Path) -> dict | None:
    """The marker-reading body `_classify` and `declaration_state` (tasks.md
    5.15) BOTH need -- extracted so the shape check and the seal comparison
    exist exactly once, never as two independently drifting copies. Returns
    `None` when the marker file does not exist at all; otherwise
    `{"class": str, "sealed": bool}` -- `sealed` is `True` only once the
    recorded seal has ALREADY been checked to match (design.md Decision C):
    by the time this returns, a sealed marker's seal is known good, never
    merely present.

    Refuses `MALFORMED_GUIDANCE_MARKER` (work-state) when the marker file
    is not valid UTF-8, not valid JSON, not a JSON object, carries any key
    other than `class`/`seal_sha256`, omits `class`, or carries a
    `seal_sha256` that is not a 64-character lowercase hex string. Refuses
    `UNKNOWN_GUIDANCE_CLASS` (work-state) when `class` holds a value outside
    `CLASSES` — this never silently degrades to `unclassified`; only a
    genuinely absent marker file does that.

    When `seal_sha256` IS present and shape-valid, it is compared against
    `paper_marker.computed_seal` of the marker's own remaining bytes; a
    mismatch refuses `GUIDANCE_DECLARATION_HAND_EDITED` (work-state), naming
    the file, the recorded digest, the computed digest, and the seal's own
    real strength — with no `--adopt` escape (design.md Decision E, guidance
    half). This check runs inside THIS function, reached by every gating
    verb already (`validate --source-md` via `classify_source_md` via
    `read_registry`, and now `declaration_state`) — never only inside the
    read-only `plan` verb (design.md Decision C, invariant 4).
    """
    marker_path = folder / _MARKER_NAME
    if not marker_path.is_file():
        return None
    try:
        raw_text = marker_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise Refused("MALFORMED_GUIDANCE_MARKER", f"{marker_path}: not valid utf-8: {exc}")
    try:
        obj = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise Refused("MALFORMED_GUIDANCE_MARKER", f"{marker_path}: invalid JSON: {exc.msg}")
    if isinstance(obj, dict):
        seal_error = paper_marker.seal_shape_error(obj)
        if seal_error is not None:
            raise Refused("MALFORMED_GUIDANCE_MARKER", f"{marker_path}: {seal_error}")
        body = {key: value for key, value in obj.items() if key != paper_marker.SEAL_KEY}
    else:
        body = obj
    value = _validate_class_obj(body, marker_path)
    sealed = isinstance(obj, dict) and paper_marker.is_sealed(obj)
    if sealed:
        recorded = obj[paper_marker.SEAL_KEY]
        computed = paper_marker.computed_seal(obj)
        if recorded != computed:
            raise Refused(
                "GUIDANCE_DECLARATION_HAND_EDITED",
                f"{marker_path}: recorded seal {recorded!r} does not match computed seal "
                f"{computed!r}. {paper_marker.SEAL_STRENGTH} Re-run `mark class` to reseal; "
                "there is no --adopt.",
            )
    return {"class": value, "sealed": sealed}


def _classify(folder: Path) -> str:
    """One folder's class, or `unclassified` when it carries no marker.

    A thin wrapper over `_read_marker` (tasks.md 5.15's own extraction of
    what used to be this function's entire body) — `unclassified` is
    exactly `_read_marker` returning `None`; every refusal `_read_marker`
    raises propagates through this function unchanged."""
    result = _read_marker(folder)
    return "unclassified" if result is None else result["class"]


def declaration_state(folder: Path) -> str:
    """One `guidance/` folder's declaration state -- the SAME
    `'undeclared'` | `'declared-unsealed'` | `'declared-sealed'` vocabulary
    `paper_declarations.declaration_state` reports for a `PROSE` source
    root (`'n/a'` never applies here: every LISTED `guidance/` folder is
    classifiable, unlike a `REPOSITORY`/`INGESTED` source root, which
    carries no revisions rule at all). Reuses `_read_marker`, the SAME
    shape-check-then-seal-compare `_classify` itself runs, so an absent
    marker, a malformed one, or a hand-edited one propagate identically
    through both callers — never a second, drifting notion of whether a
    folder's own marker is good (design.md Decision C/I;
    `specs/source-declaration-authoring/spec.md`, `Requirement: The
    Position Report Names Every Declarable Root's And Every Guidance
    Folder's Declaration State`; tasks.md 5.15)."""
    result = _read_marker(folder)
    if result is None:
        return "undeclared"
    return "declared-sealed" if result["sealed"] else "declared-unsealed"


def declare_class(
    guidance_dir: Path, folder: str, value: str, *, sealed: bool = True,
) -> dict:
    """`mark class`'s own engine (design.md Decision F, guidance half;
    `specs/guidance-registry/spec.md`). Mirrors `paper_declarations.
    declare_revisions` (S2) for the OTHER marker kind.

    In order: `folder` must directly name a directory under `guidance_dir`,
    enumerated the SAME way `read_registry` enumerates. Otherwise refuses
    `GUIDANCE_FOLDER_ABSENT`, naming every folder that is there. **Nothing
    creates the folder.** `value` must be in `CLASSES`, otherwise refuses
    `UNKNOWN_GUIDANCE_CLASS` (reused verbatim). Multiple evidence folders
    are allowed; ingested document identities remain unique across them.
    The candidate is
    round-tripped through `_validate_class_obj` before `paper_marker.write`
    ever runs, so this verb can never produce a marker its own reader would
    refuse.

    Deliberately does NOT refuse an `evidence` folder holding zero ingested
    papers -- `_ingested_root_status` already rules that state an earlier
    stage, never a fault (design.md Decision F).

    Always writes, regardless of whether a marker already exists at that
    path or whether its current seal matches (design.md Decision E) -- no
    `--reopen`/`--adopt`, and this function never reads `folder`'s own
    previous marker at all.

    Returns `{"folder", "class", "sealed"}` (design.md, Interfaces)."""
    present = (
        sorted(entry.name for entry in guidance_dir.iterdir() if entry.is_dir())
        if guidance_dir.is_dir() else []
    )
    if folder not in present:
        raise Refused(
            "GUIDANCE_FOLDER_ABSENT",
            f"--folder must name a directory directly under {guidance_dir}; "
            f"{folder!r} is not one of {present}",
        )
    if value not in CLASSES:
        raise Refused(
            "UNKNOWN_GUIDANCE_CLASS",
            f"{value!r} is not one of the declared classes {CLASSES}",
        )
    marker_path = guidance_dir / folder / _MARKER_NAME
    candidate = {"class": value}
    _validate_class_obj(candidate, marker_path)
    paper_marker.write(marker_path, candidate, sealed=sealed)
    return {"folder": folder, "class": value, "sealed": sealed}


def ingested_papers(guidance_dir: Path) -> dict:
    """`{root: [{"folder": paper_folder_name, "markdown": str(path)}, ...]}`
    for every `guidance/<root>/<paper>/<paper>.md` two levels under
    `guidance_dir` (`the-phases-are-derived-not-remembered`, design.md D4).

    `read_registry` above enumerates ONE level (`guidance/<root>`), so the
    eight ingested papers actually sitting two levels down
    (`guidance/<root>/<paper>/<paper>.md`) are invisible to it -- and
    `guidance/*/*` is a `.gitignore` pattern, so `fd`/`rg` report the whole
    tree empty. `Path.iterdir()` is gitignore-blind BY CONSTRUCTION -- the
    mechanism, not an instruction (`specs/skeleton-startup/spec.md`,
    `Requirement: Disk Presence Checks Include Ignored Paths`) -- so this
    walks with it, never `fd`/`rg`/a shell call.

    A root directory holding no ingested papers reports an empty list, not
    an absence -- the point is exactly that a populated-but-ignored
    directory must never be reported as empty; an EMPTY root is a true,
    honestly reported empty list. A non-existent `guidance_dir` reports an
    empty registry, matching `read_registry`'s own precedent.
    """
    if not guidance_dir.is_dir():
        return {}
    registry: dict = {}
    for root_entry in sorted(guidance_dir.iterdir()):
        if not root_entry.is_dir():
            continue
        papers = []
        for paper_entry in sorted(root_entry.iterdir()):
            if not paper_entry.is_dir():
                continue
            markdown_path = paper_entry / f"{paper_entry.name}.md"
            if markdown_path.is_file():
                papers.append({"folder": paper_entry.name, "markdown": str(markdown_path)})
        registry[root_entry.name] = papers
    return registry


def section_citation_status(guidance_dir: Path, section_id: str) -> dict:
    """One SECTION's own citation folder (`guidance/<section-id>/`) --
    ADDITIVE to whatever pre-existing function-named folders `read_registry`
    already reports: a folder becomes a section's own citation folder
    exactly when its name equals a section id the parsed corpus declares
    (`paper_graph.assemble_corpus(...).sections`), never a hand-listed
    tuple -- and every other `guidance/` folder keeps flowing through
    `read_registry`/`classify_source_md` completely unchanged
    (`no-citation-before-its-paper-is-ingested`, item 1; `SKILL.md`, "Two
    kinds of guidance folder").

    Reports `{"section": section_id, "exists": bool, "classification":
    str | None, "ingested": [...same shape as `ingested_papers`'s own
    per-root list...], "pending_pdfs": [...]}`. `classification` is `None`
    exactly when the folder does not exist yet -- there is nothing to
    classify. `pending_pdfs` is every loose `*.pdf` sitting DIRECTLY under
    the folder: `paper-ingestion`'s own contract is that a folder holding a
    loose PDF is a root to scan, and ingestion MOVES that PDF into
    `<paper>/<paper>.pdf` once it is processed -- so a name surviving here
    is exactly a citation this section still owes an ingestion pass
    (`.claude/skills/paper-ingestion/SKILL.md`).

    `write`'s own citation gate (`paper_cli._guard_section_citations_ready`)
    is the real caller: it reads this status for one block's own section,
    before that block is ever drafted, and refuses by name when a stage is
    missing -- never a second, independent walk of the same folder.
    """
    folder = guidance_dir / section_id
    if not folder.is_dir():
        return {
            "section": section_id, "exists": False, "classification": None,
            "ingested": [], "pending_pdfs": [],
        }
    ingested = []
    for paper_entry in sorted(folder.iterdir()):
        if not paper_entry.is_dir():
            continue
        markdown_path = paper_entry / f"{paper_entry.name}.md"
        if markdown_path.is_file():
            ingested.append({"folder": paper_entry.name, "markdown": str(markdown_path)})
    pending_pdfs = sorted(
        entry.name for entry in folder.iterdir()
        if entry.is_file() and entry.suffix.lower() == ".pdf"
    )
    return {
        "section": section_id, "exists": True, "classification": _classify(folder),
        "ingested": ingested, "pending_pdfs": pending_pdfs,
    }


def section_citation_folders(guidance_dir: Path, section_ids) -> dict:
    """`{section_id: section_citation_status(guidance_dir, section_id)}`
    for every id in `section_ids` -- the discovery half of the per-section
    citation-folder capability (item 1). `section_ids` is always derived
    by the caller from the parsed corpus (`plan`'s own
    `set(paper_graph.assemble_corpus(sections_dir).sections)`), never a
    hand-listed tuple: the exact anti-pattern this change's own launch
    context names ("one went stale silently in this repository the day
    the skill grew past its first three verbs") is what handing this
    function a derived set, rather than a literal, rules out. Wired into
    `plan` (`paper_cli.compute_plan`) so an operator sees every section's
    own citation-folder status in one read, the same place `guidance`'s
    function-named-folder registry already reports.
    """
    return {
        section_id: section_citation_status(guidance_dir, section_id)
        for section_id in sorted(section_ids)
    }


#: One ATX heading (`#` through `######`), anchored at the start of a
#: line (`re.MULTILINE`, never `str.splitlines()`'s own broader notion of
#: a line boundary -- exotic Unicode separators must never move a byte
#: offset away from what `md_path.read_bytes()` itself would report). A
#: run of more than six `#` never matches: CommonMark caps heading depth
#: at 6, and the mandatory `[ \t]+` separator after the captured run
#: rejects a bare `#comment`-style line with no space.
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$", re.MULTILINE)


def segment_markdown(body: str) -> dict:
    """Every ATX heading in `body`, each carrying its own `{title, level,
    byte_start, byte_end}` -- byte offsets into `body.encode("utf-8")`,
    the same convention `paper_evidence.EvidenceSpan` already uses, so a
    caller can slice `body.encode("utf-8")[byte_start:byte_end]` and get
    exactly this heading's own span, never anything this function itself
    hands back as text (`redactor-packet` spec, design.md Decision D5:
    "the packet carries locators, never reference prose").

    A heading's own span ends at the next heading whose level is **less
    than or equal to** its own -- same level OR shallower -- never "the
    next heading of the SAME level", which is what swallowed a deeper
    appendix here before: a section followed later by a shallower heading
    (with no intervening same-level heading first) would otherwise extend
    all the way to EOF under a same-level-only rule, folding that
    shallower heading's whole nested tree -- including whatever appendix
    it contains -- into the wrong span (tasks.md 8.2-8.3; design.md, D5's
    own "Segmentation, and the appendix it must not swallow"). Heading
    DISCOVERY is one independent pass over the whole body before any span
    is computed, so a deeper, nested heading is always found regardless
    of how any ancestor's own span resolves -- only the ancestor's
    `byte_end` is at stake under the old rule, never whether the nested
    heading is reported at all.

    A headingless body reports `{"headings": [], "reason": "NO_HEADINGS"}`
    -- a reported state, like `unclassified`, never a silently empty list
    that could also mean "not checked yet" (tasks.md 8.4).
    """
    matches = list(_HEADING_RE.finditer(body))
    if not matches:
        return {"headings": [], "reason": "NO_HEADINGS"}

    total_bytes = len(body.encode("utf-8"))
    raw = [
        {
            "level": len(match.group(1)),
            "title": match.group(2).strip(),
            "byte_start": len(body[:match.start()].encode("utf-8")),
        }
        for match in matches
    ]

    headings = []
    for index, heading in enumerate(raw):
        byte_end = total_bytes
        for later in raw[index + 1:]:
            if later["level"] <= heading["level"]:
                byte_end = later["byte_start"]
                break
        headings.append({**heading, "byte_end": byte_end})
    return {"headings": headings}


def read_markdown_outline(md_path: Path) -> dict:
    """`segment_markdown`'s own disk-reading boundary. Refuses
    `GUIDANCE_MARKDOWN_UNREADABLE` (work-state) when `md_path` cannot be
    read or is not valid UTF-8 -- `segment_markdown` itself stays a pure
    function over already-decoded text, the same separation `paper_
    evidence.EvidenceSpan.locate` already keeps between disk I/O and its
    own pure byte search (`redactor-packet` spec, `packet`'s outline-
    assembly requirement)."""
    try:
        body = md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Refused("GUIDANCE_MARKDOWN_UNREADABLE", f"{md_path}: {exc}")
    return segment_markdown(body)


def read_registry(guidance_dir: Path) -> dict:
    """`{folder_name: class-or-"unclassified"}` for every directory
    directly under `guidance_dir`.

    Enumerated from disk (`sorted(guidance_dir.iterdir())`); no folder name
    is ever referenced as a constant anywhere in this module — the
    anti-pattern this registry exists to keep out
    (`_core/deliberation/engine/proposal-workspace.ts:49`'s hardcoded
    `GUIDE_DIRECTORY`, named as precedent, not repaired here). A
    non-existent `guidance_dir` reports an empty registry rather than
    refusing — a repository that has never created the folder has simply
    classified nothing yet.
    """
    if not guidance_dir.is_dir():
        return {}
    registry: dict = {}
    for entry in sorted(guidance_dir.iterdir()):
        if not entry.is_dir():
            continue
        registry[entry.name] = _classify(entry)
    return registry


def classify_source_md(source_md: Path, guidance_dir: Path) -> str | None:
    """Which `guidance/<root>` folder (per `read_registry`'s own
    classification) `source_md` resolves inside, or `None` when it does not
    resolve under `guidance_dir` at all -- a quote sourced from outside the
    guidance registry entirely is not this function's business, and every
    caller treats `None` as "no classification to enforce", never as a
    class of its own.

    Read-only, like every other function in this module: no marker file is
    ever written here. Reuses `read_registry` verbatim rather than a second
    walk of `guidance_dir` (`the-skill-stops-trusting-memory`, item 2/3:
    `validate --source-md` is the first REAL caller of the registry this
    module has ever had -- `plan`'s own read never gated anything on the
    result).
    """
    try:
        resolved = source_md.resolve()
        relative = resolved.relative_to(guidance_dir.resolve())
    except (OSError, ValueError):
        return None
    if not relative.parts:
        return None
    root_name = relative.parts[0]
    registry = read_registry(guidance_dir)
    return registry.get(root_name, "unclassified")


def is_ingested_source(source_md: Path | str, guidance_dir: Path) -> bool:
    """Does `source_md` resolve to a REAL, currently-present ingested
    paper -- `guidance/<root>/<paper>/<paper>.md`, the exact two-level
    shape `ingested_papers` above walks? The one structural definition of
    "ingested" every caller shares (`paper_bib._require_ingested`, item 2
    of `no-citation-before-its-paper-is-ingested`): never a second,
    independently drifting notion of the same shape.

    Never a guess from an identifier or a folder name -- `source_md` is
    expected to be the exact path an evidence span was already located
    against (`paper_evidence.EvidenceSpan.locate`), so this only confirms
    that path still resolves to a real ingested file; it resolves no
    other correspondence and refuses nothing itself.
    """
    try:
        resolved = Path(source_md).resolve()
        relative = resolved.relative_to(guidance_dir.resolve())
    except (OSError, ValueError):
        return False
    parts = relative.parts
    return len(parts) == 3 and parts[-1] == f"{parts[-2]}.md" and resolved.is_file()
