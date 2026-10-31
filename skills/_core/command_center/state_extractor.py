"""Read-only derivation of a PaperSmith workspace's observable state.

``get_workspace_state(root)`` walks the workspace once and returns one JSON
payload describing paper metadata, the section lifecycle, the four quality
gates, the pipeline stages, and the evidence/inbox ledgers.

Design rules, in priority order:

1. **Read-only.** Nothing here opens a file for writing, creates a directory,
   or resolves a lock. The command center observes a paper; it never edits one.
2. **Best-effort.** A malformed contract, an unreadable draft, or a missing
   workspace config degrades exactly one field. Every reader is guarded and the
   payload always carries the documented top-level keys.
3. **Honest status.** ``SCAFFOLDED``/``CONTRACTED``/``DRAFTING``/``AUDITED``/
   ``SEALED`` are derived from bytes on disk (frontmatter, block markers,
   citation placeholders, compiled outputs), never inferred from a task list.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import functools
import importlib.util
import json
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: Sections a paper always declares, in rendering order.
SECTION_ORDER = (
    "01-materials-and-methods",
    "02-experimental-setup",
    "03-results-and-discussion",
    "04-limitations",
    "05-related-work",
    "06-introduction",
    "07-conclusions",
    "08-abstract",
    "09-title-and-keywords",
    "10-back-matter",
)

#: The pipeline's stages, in the order the architecture diagram fixes them.
#:
#: The diagram is `docs/diagrams/papersmith-pi-flow.html`, generated from
#: `.archify/architecture-papersmith-pi-20261004-173559/build.mjs`; its twelve
#: numbered tramos are these, lane for lane, followed by the transversal audit
#: lane it draws beside them. The board used to ship six stages invented in this
#: directory, and nothing compared the two.
PIPELINE_STAGES = (
    ("harness", "Harness"),
    ("plausibility", "Plausibility"),
    ("ingestion", "Ingestion"),
    ("proposal", "Proposal deliberation"),
    ("implementation", "Proof of concept"),
    ("experimental-deliberation", "Experimental deliberation"),
    ("experimental-implementation", "Experimental implementation"),
    ("credentials", "Credentials"),
    ("remote", "Remote execution"),
    ("writing", "Writing"),
    ("figures", "Figures and grounding"),
    ("paper", "Paper"),
    ("audit", "Audit (transversal)"),
)

#: The diagram's main chain, `(from, to, label)`, in its order. The drawing
#: reads this instead of carrying a chain of its own, which is what let the
#: board and the diagram disagree in the first place.
PIPELINE_CHAIN = (
    ("plausibility", "ingestion", "top-5 to ingest"),
    ("ingestion", "proposal", "guidance/"),
    ("proposal", "implementation", "rNN revision"),
    ("implementation", "experimental-deliberation", "proof of concept"),
    ("experimental-deliberation", "experimental-implementation", "protocol + repo"),
    ("experimental-implementation", "credentials", "job ready"),
    ("credentials", "remote", "accounts validated"),
    ("remote", "writing", "measured facts"),
    ("writing", "figures", "sections"),
    ("figures", "paper", "anchors"),
)

#: Where each quality gate hangs in that flow: the stage whose work it checks.
#: The gate itself feeds the transversal audit lane, so nothing here names it.
#:
#: These are the **verdict** gates: a checker reads artifacts and returns a
#: verdict that lands in the audit lane. The **human stops** the drawing shows
#: inline -- the plausibility report's acceptance, the two deliberation
#: acceptances, the launch authorization -- are a different family and are absent
#: by decision, not by omission. An acceptance leaves no artifact to read: the
#: plausibility skill states it in its own words, the gate approves the reading
#: and "publishes nothing" and "files nothing." A `gate_links` entry for it could
#: only ever report a verdict the board cannot compute.
GATE_SOURCES = {
    "writing-readiness": ("proposal", "contracts"),
    "coupling-verification": ("writing", "facts"),
    "grounding-style-leak": ("writing", "citations"),
    "diagram-raster": ("figures", "figures"),
}

#: The placeholders a scaffold leaves inside a drop zone so the folder travels.
#: They are not artifacts, and counting one would light a tramo with the only
#: file the scaffold put there -- a board reporting work nobody did.
PLACEHOLDER_FILES = (".gitkeep", ".gitignore")

#: The transversal lane every quality gate's verdict lands in, which is where
#: the diagram draws the audit lane relative to the numbered tramos.
AUDIT_STAGE = "audit"

#: The harness projections a wired workspace carries, one per harness.
HARNESS_PROJECTIONS = (".claude", ".pi", ".opencode", ".agents")

#: The plausibility flow's own artifacts, under `sota-pool/`.
SOTA_POOL_ARTIFACTS = ("atlas.json", "atlas.html", "candidates.json")

#: The declarations a skill makes when it owns a credential store: module-level
#: string constants naming the directory and the file inside it. Same rule as
#: `INBOX_DECLARATION`, and for the same reason -- the skill that owns the store
#: stays its single source of truth, so the forge ships no target's own
#: vocabulary into every workspace.
STORE_DECLARATION = "STORE_NAME"
STORE_FILE_DECLARATION = "STORE_FILE"

#: The experimental deliberation's sidecar, written beside `experiments/`.
EXPERIMENTAL_DELIBERATION = ".experimental-deliberation"

#: The experimental implementation's revisions, under `experiments/`.
EXPERIMENTAL_REVISION_GLOB = "experiments-*.md"

#: The sky graph the proposal deliberation draws beside a published revision:
#: the SOTA constellation with the proposal inside it, rendered by the
#: plausibility flow's own renderer. It is a second artifact of the same tramo,
#: not a second tramo -- a revision can be published before its graph exists.
PROPOSAL_GRAPH_GLOB = "*.graph.html"

#: Persona -> pipeline stage, used for the "active worker" pills. Read off the
#: diagram's own lane placement of each agent, not off the old six stages, and
#: **every shipped definition belongs here**: an agent nobody maps is dropped
#: from its tramo without a word, which is how the three plausibility ones went
#: missing while the drawing showed them.
AGENT_STAGES = {
    "sota-scout": "plausibility",
    "sota-grapher": "plausibility",
    "novelty-screener": "plausibility",
    "paper-ingestion": "ingestion",
    "deliberation-publish": "proposal",
    # Tutors the proposal's own mathematics and novelty from the math panel.
    "math-tutor": "proposal",
    "experimental-publish": "experimental-deliberation",
    "experimental-validation": "experimental-deliberation",
    # Tutors the experiment decisions from the experiments panel; hands changes to the deliberation.
    "experiments-tutor": "experimental-deliberation",
    "experiments-build": "experimental-implementation",
    "experiments-walk": "experimental-implementation",
    "experiments-reviewer": "experimental-implementation",
    "implementation-build": "implementation",
    "implementation-walk": "implementation",
    "paper-replicator": "implementation",
    "dataset-scout": "implementation",
    "dataset-curator": "implementation",
    "insumos-observer": "writing",
    "redactor": "writing",
    "contract-auditor": "writing",
    "style-sampler": "writing",
    # Reviews the compiled paper against the NeurIPS review form.
    "paper-reviewer": "audit",
    "diagram-author": "figures",
    "figure-auditor": "figures",
    "section-grounding-auditor": "figures",
    "audit-report": "audit",
    # Adapts the finished manuscript to the chosen journal: reads the guidelines,
    # audits smith's template against them and proposes the plan the operator
    # approves; the venue build lands beside the paper, never over it.
    "venue-adapter": "paper",
}

_EXTENT_RE = re.compile(
    r"\*\*Extent\*\*\s*(?P<min>\d+)\s*(?:[–—]|--|-|to)\s*(?P<max>\d+)\s*words",
    re.IGNORECASE,
)
_BEGIN_RE = re.compile(
    r"^%% paper-writing block (?P<id>[A-Za-z0-9._-]+) begin sha256=(?P<digest>[0-9a-f]{64})\s*$"
)
_END_RE = re.compile(r"^%% paper-writing block (?P<id>[A-Za-z0-9._-]+) end\s*$")
_CITE_RE = re.compile(r"\\cite[a-zA-Z]*\{(?P<keys>[^}]*)\}")
_BIB_KEY_RE = re.compile(r"^@\w+\{(?P<key>[^,\s]+)\s*,", re.MULTILINE)
_PLACEHOLDER_TOKENS = ("\\todo{", "TODO(", "[[", "{{", "???")
_FIGURE_OBLIGATION_RE = re.compile(
    r"(^\s*[-*]\s*\*\*Figure\b)|(\bobligation:\s*figure\b)|(^\s*figure:\s*\S+)",
    re.IGNORECASE | re.MULTILINE,
)

#: The five external fact ids documented by
#: ``openspec/specs/fact-production/spec.md``: every one resolves through
#: ``paper_declarations.FACT_SOURCE_ROOT`` (an external source), never through
#: a block's ``produces_facts``. Used as a fallback when the workspace's own
#: ``paper-writing/scripts/`` copy is unavailable.
_EXTERNAL_FACT_IDS = frozenset({
    "formulation",
    "dataset",
    "experimental-design",
    "implementation",
    "results",
})

#: Structural facts resolved outside the producer/external split: ``skeleton``
#: is resolved by skeleton-startup and is owned by no section contract.
_STRUCTURAL_FACT_IDS = frozenset({"skeleton"})


# --------------------------------------------------------------------------
# guarded primitive readers
# --------------------------------------------------------------------------
def _read_text(path: Path) -> str | None:
    """Return file text, or ``None`` for anything that is not a readable file."""
    try:
        if not path.is_file() or path.is_symlink() and not path.exists():
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


#: Parsed results keyed by (kind, path, extra); each entry carries the file's
#: stat signature, so a saved file is parsed again on the next read. The
#: dashboard polls the state every few seconds and most inputs never change.
_FILE_MEMO: dict[tuple[str, str, Any], tuple[tuple[int, int, int, int], Any]] = {}
_FILE_MEMO_LOCK = threading.Lock()
#: How long a file must stay unchanged before its parse is reused.
MEMO_SETTLE_NS = 2_000_000_000


def clear_file_memo() -> None:
    with _FILE_MEMO_LOCK:
        _FILE_MEMO.clear()


def memo_by_file(kind: str, path: Path, compute: Callable[[], Any], extra: Any = None) -> Any:
    """``compute()`` for ``path``, reused while its stat signature holds.

    The signature is mtime, ctime (moved by a permission change too), size and
    inode. A missing file is never remembered, and neither is a file changed
    in the last ``MEMO_SETTLE_NS``: two saves inside one timestamp tick can
    share a signature, so a fresh file is parsed every time until it settles.
    Callers get a deep copy, so mutating a result cannot change what the next
    caller sees.
    """
    try:
        stat = path.stat()
    except OSError:
        return compute()
    signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
    key = (kind, str(path), extra)
    with _FILE_MEMO_LOCK:
        hit = _FILE_MEMO.get(key)
    if hit is not None and hit[0] == signature:
        return copy.deepcopy(hit[1])
    value = compute()
    settled = time.time_ns() - stat.st_mtime_ns >= MEMO_SETTLE_NS
    with _FILE_MEMO_LOCK:
        if settled:
            _FILE_MEMO[key] = (signature, value)
        else:
            _FILE_MEMO.pop(key, None)
    return copy.deepcopy(value)


def _load_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML mapping, tolerating a missing parser or a damaged file."""
    return memo_by_file("yaml", path, lambda: _parse_yaml(path))


def _parse_yaml(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    if text is None:
        return {}
    try:
        import yaml  # PyYAML; a kit dependency, imported lazily
    except ModuleNotFoundError:
        return _scalar_yaml(text)
    try:
        data = yaml.safe_load(text)
    except Exception:
        return _scalar_yaml(text)
    return data if isinstance(data, dict) else {}


def _scalar_yaml(text: str) -> dict[str, Any]:
    """Stdlib fallback: top-level ``key: scalar`` pairs only.

    Enough for the workspace metadata this payload exposes when PyYAML is not
    installed in the interpreter running the server. Nested mappings are
    deliberately ignored rather than guessed at.
    """
    result: dict[str, Any] = {}
    for line in text.splitlines():
        if not line or line[0] in " \t#-":
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.strip()
        if not value or value[0] in "[{":
            continue
        result[key.strip()] = value.strip("\"'")
    return result


def _load_json(path: Path) -> Any:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------
def _split_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """Split a section contract into its JSON/YAML frontmatter and body.

    A contract opens with a ``---`` fence; the frontmatter an earlier writer
    emitted is JSON, so that is tried first and YAML is the fallback for
    hand-authored contracts.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None, text
    raw = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :])
    meta: Any = None
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml
            meta = yaml.safe_load(raw)
        except Exception:
            meta = None
    return (meta if isinstance(meta, dict) else None), body


def _extent(body: str) -> tuple[int | None, int | None]:
    match = _EXTENT_RE.search(body)
    if match is None:
        return None, None
    return int(match.group("min")), int(match.group("max"))


def _blocks_of(meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(meta, dict):
        return []
    blocks = meta.get("blocks")
    if not isinstance(blocks, list):
        return []
    return [block for block in blocks if isinstance(block, dict)]


def _mapping_get(value: Any, key: str) -> Any:
    """Read ``key`` from a mapping, or ``None`` for any non-mapping value.

    Frontmatter is hand-authorable, so a scalar where a mapping is expected
    (``mode: argument``) must degrade exactly one field to ``None`` rather
    than abort the whole payload.
    """
    return value.get(key) if isinstance(value, dict) else None


def _facts_of(block: dict[str, Any], key: str) -> list[str]:
    values = block.get(key)
    if not isinstance(values, list):
        return []
    names: list[str] = []
    for value in values:
        if isinstance(value, dict) and isinstance(value.get("value"), str):
            names.append(value["value"])
        elif isinstance(value, str):
            names.append(value)
    return names


def _parse_main_tex(path: Path) -> dict[str, dict[str, Any]]:
    """Map every ``%% paper-writing block`` id to its body text and word count.

    The grammar is the one ``skills/paper-writing/scripts/paper_block.py``
    writes: a ``begin sha256=`` line and a matching ``end`` line. A block whose
    end marker is missing contributes nothing, so a half-written draft never
    inflates a word count.
    """
    text = _read_text(path)
    if text is None:
        return {}
    blocks: dict[str, dict[str, Any]] = {}
    open_id: str | None = None
    buffer: list[str] = []
    for line in text.splitlines():
        begin = _BEGIN_RE.match(line)
        if begin is not None and open_id is None:
            open_id = begin.group("id")
            buffer = []
            continue
        end = _END_RE.match(line)
        if end is not None and open_id is not None and end.group("id") == open_id:
            body = "\n".join(buffer)
            blocks[open_id] = {"body": body, "words": _word_count(body), "has_body": bool(body.strip())}
            open_id = None
            buffer = []
            continue
        if open_id is not None:
            buffer.append(line)
    return blocks


def _bib_keys(path: Path) -> set[str]:
    text = _read_text(path)
    if text is None:
        return set()
    return {match.group("key") for match in _BIB_KEY_RE.finditer(text)}


def _citation_signals(body: str, bib: set[str]) -> tuple[int, int, list[str]]:
    """Return ``(verified, placeholders, unresolved_keys)`` for one body."""
    verified = 0
    placeholders = 0
    unresolved: list[str] = []
    for match in _CITE_RE.finditer(body):
        for key in (part.strip() for part in match.group("keys").split(",")):
            if not key:
                continue
            if key.startswith("?") or key.startswith("TODO") or key in bib:
                if key in bib:
                    verified += 1
                else:
                    placeholders += 1
                    unresolved.append(key)
            else:
                placeholders += 1
                unresolved.append(key)
    for token in _PLACEHOLDER_TOKENS:
        placeholders += body.count(token)
    return verified, placeholders, sorted(set(unresolved))


def _section_status(
    meta: dict[str, Any] | None,
    blocks: list[dict[str, Any]],
    draft: dict[str, dict[str, Any]],
    placeholders: int,
    sealed: bool,
) -> str:
    """Derive one section's lifecycle state from bytes on disk."""
    if not blocks:
        return "SCAFFOLDED"
    if not meta:
        return "SCAFFOLDED"
    section_name = meta.get("section")
    own = {
        block_id: value
        for block_id, value in draft.items()
        if not isinstance(section_name, str)
        or block_id.startswith(f"{section_name}.") or block_id == section_name
    }
    written = [value for value in own.values() if value["has_body"]]
    if not written:
        return "CONTRACTED"
    required = [b for b in blocks if not b.get("optional")]
    if len(written) < len(required):
        return "DRAFTING"
    if placeholders:
        return "DRAFTING"
    if sealed:
        return "SEALED"
    return "AUDITED"


def _section_payload(root: Path, path: Path, draft: dict[str, dict[str, Any]],
                     bib: set[str]) -> dict[str, Any]:
    text = _read_text(path) or ""
    meta, body = _split_frontmatter(text)
    blocks = _blocks_of(meta)
    min_words, max_words = _extent(body)
    section_name = meta.get("section") if isinstance(meta, dict) else None
    section_name = section_name if isinstance(section_name, str) else path.stem

    demands: list[str] = []
    produces: list[str] = []
    declarations: list[str] = []
    for block in blocks:
        demands.extend(_facts_of(block, "requires_facts"))
        produces.extend(_facts_of(block, "produces_facts"))
        declarations.extend(_facts_of(block, "requires_declarations"))

    own_draft = {
        block_id: value
        for block_id, value in draft.items()
        if block_id.startswith(f"{section_name}.") or block_id == section_name
    }
    word_count = sum(value["words"] for value in own_draft.values())
    # Citation signals come from the DRAFT only. The contract body is guidance
    # prose and carries deliberate `\cite{...}` examples; counting those would
    # report a leak that no draft ever wrote.
    verified = 0
    placeholders = 0
    unresolved: list[str] = []
    for value in own_draft.values():
        v, p, u = _citation_signals(value["body"], bib)
        verified += v
        placeholders += p
        unresolved.extend(u)

    sealed = _load_json(root / "paper" / "verdict.json") is not None
    status = _section_status(meta, blocks, draft, placeholders, sealed)

    return {
        "id": path.stem,
        "file": f"sections/{path.name}",
        "section": section_name,
        "position": meta.get("position") if isinstance(meta, dict) else None,
        "mode": _mapping_get(meta.get("mode") if isinstance(meta, dict) else None, "value"),
        "status": status,
        "has_contract": meta is not None,
        "extent": {"min_words": min_words, "max_words": max_words},
        "word_count": word_count,
        "blocks": [
            {
                "id": block.get("id"),
                "optional": bool(block.get("optional", False)),
                "citations": block.get("citations"),
                "requires_facts": _facts_of(block, "requires_facts"),
                "produces_facts": _facts_of(block, "produces_facts"),
                "requires_declarations": _facts_of(block, "requires_declarations"),
                "written": bool(own_draft.get(str(block.get("id")), {}).get("has_body")),
            }
            for block in blocks
        ],
        "facts": {
            "demands": sorted(set(demands)),
            "produces": sorted(set(produces)),
            "declarations": sorted(set(declarations)),
        },
        "citations": {
            "verified": verified,
            "placeholders": placeholders,
            "unresolved_keys": sorted(set(unresolved)),
        },
        "blocks_total": len(blocks),
        "blocks_written": len([value for value in own_draft.values() if value["has_body"]]),
    }


# --------------------------------------------------------------------------
# gates
# --------------------------------------------------------------------------
def _gate_writing_readiness(sections: list[dict[str, Any]]) -> dict[str, Any]:
    missing = [s["id"] for s in sections if not s["has_contract"]]
    no_blocks = [s["id"] for s in sections if s["has_contract"] and s["blocks_total"] == 0]
    if not sections:
        state, reasons = "VERIFYING", ["no section contracts found under sections/"]
    elif missing:
        state, reasons = "BLOCKED", [f"contract missing or malformed: {name}" for name in missing]
    elif no_blocks:
        state, reasons = "BLOCKED", [f"contract declares no blocks: {name}" for name in no_blocks]
    else:
        state, reasons = "PASSED", []
    return {
        "id": "writing-readiness",
        "name": "Writing Readiness Gate",
        "state": state,
        "reasons": reasons,
        "parts": {"contracts_total": len(sections), "contracts_ok": len(sections) - len(missing)},
    }


@contextlib.contextmanager
def _no_bytecode():
    """Load a workspace module without leaving bytecode inside the workspace.

    This loader runs in the SERVER process, so the child environment's
    ``PYTHONDONTWRITEBYTECODE`` cannot reach it -- ``sys.dont_write_bytecode``
    is the in-process equivalent, and it is restored afterwards because the rest
    of the process has no business inheriting the setting.

    Measured before this existed: the first ``/api/state`` derivation created 12
    ``__pycache__`` paths inside the paper folder the extractor claims only to
    observe, which falsified three shipped read-only claims at once. The
    workspace's own ``.gitignore`` hides ``__pycache__``, which is why no gate
    saw it.
    """
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous


@functools.lru_cache(maxsize=None)
def _external_fact_ids(workspace: str) -> frozenset[str]:
    """Read the external fact vocabulary, never fatal to the payload.

    Prefers ``paper_declarations.FACT_SOURCE_ROOT`` from the workspace's own
    ``skills/paper-writing/scripts/`` tree so a widened vocabulary is honored,
    and falls back to the five documented external fact ids when that module is
    missing or cannot be imported. The import is read-only and best-effort: a
    failure must degrade this gate's vocabulary, never raise. Results are
    cached per workspace because the loader runs on every state derivation.
    """
    module_path = (
        Path(workspace) / "skills" / "paper-writing" / "scripts" / "paper_declarations.py"
    )
    try:
        spec = importlib.util.spec_from_file_location(
            "_papersmith_command_center_declarations", module_path
        )
        if spec is None or spec.loader is None:
            return _EXTERNAL_FACT_IDS
        module = importlib.util.module_from_spec(spec)
        with _no_bytecode():
            spec.loader.exec_module(module)
        roots = getattr(module, "FACT_SOURCE_ROOT", None)
        if isinstance(roots, dict) and roots:
            return frozenset(str(fact) for fact in roots)
    except Exception:
        return _EXTERNAL_FACT_IDS
    return _EXTERNAL_FACT_IDS


def _gate_coupling_verification(root: Path, sections: list[dict[str, Any]]) -> dict[str, Any]:
    produced = {fact for s in sections for fact in s["facts"]["produces"]}
    demanded = sorted({fact for s in sections for fact in s["facts"]["demands"]})
    declared = {fact for s in sections for fact in s["facts"]["declarations"]}
    external = _external_fact_ids(str(root))
    # A demanded fact is resolved when any block produces it, when an external
    # ``FACT_SOURCE_ROOT`` route owns it, or when it is the structural
    # ``skeleton`` fact. Only a fact with no route at all blocks the gate --
    # reporting an externally resolvable fact as BLOCKED is a false negative no
    # writing action could clear.
    resolvable = produced | external | _STRUCTURAL_FACT_IDS
    unmatched = [fact for fact in demanded if fact not in resolvable]
    if not sections:
        state, reasons = "VERIFYING", ["no section contracts found under sections/"]
    elif unmatched:
        state, reasons = "BLOCKED", [
            f"fact {fact!r} is demanded but no section produces it" for fact in unmatched
        ]
    else:
        state, reasons = "PASSED", []
    return {
        "id": "coupling-verification",
        "name": "Coupling Verification Gate",
        "state": state,
        "reasons": reasons,
        "parts": {
            "produced": sorted(produced),
            "external": sorted(external),
            "demanded": demanded,
            "declarations": sorted(declared),
            "unmatched": unmatched,
        },
    }


def _gate_grounding_style(sections: list[dict[str, Any]]) -> dict[str, Any]:
    leaked = [
        {"section": s["id"], "placeholders": s["citations"]["placeholders"],
         "unresolved_keys": s["citations"]["unresolved_keys"]}
        for s in sections
        if s["citations"]["placeholders"]
    ]
    reasons = [
        f"{item['section']}: {item['placeholders']} unverified citation placeholder(s)"
        for item in leaked
    ]
    if not sections:
        state = "VERIFYING"
        reasons = ["no section contracts found under sections/"]
    else:
        state = "BLOCKED" if leaked else "PASSED"
    return {
        "id": "grounding-style-leak",
        "name": "Grounding & Style Leak Gate",
        "state": state,
        "reasons": reasons,
        "parts": {
            "verified_citations": sum(s["citations"]["verified"] for s in sections),
            "placeholder_citations": sum(s["citations"]["placeholders"] for s in sections),
            "leaks": leaked,
        },
    }


def _gate_diagram_raster(root: Path, sections: list[dict[str, Any]]) -> dict[str, Any]:
    obligations = 0
    for section in sections:
        text = _read_text(root / section["file"]) or ""
        obligations += len(_FIGURE_OBLIGATION_RE.findall(text))
    figures_dir = root / "paper" / "Figures"
    compiled = sorted(p.name for p in figures_dir.glob("*.pdf")) if figures_dir.is_dir() else []
    rasters = sorted(p.name for p in figures_dir.glob("*.png")) if figures_dir.is_dir() else []
    if obligations and not compiled:
        state = "BLOCKED"
        reasons = [f"{obligations} diagram obligation(s) declared but paper/Figures/ holds no compiled PDF"]
    else:
        state = "PASSED"
        reasons = []
    return {
        "id": "diagram-raster",
        "name": "Diagram & Raster Gate",
        "state": state,
        "reasons": reasons,
        "parts": {"obligations": obligations, "compiled": compiled, "rasters": rasters},
    }


def _gates(root: Path, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _gate_writing_readiness(sections),
        _gate_coupling_verification(root, sections),
        _gate_grounding_style(sections),
        _gate_diagram_raster(root, sections),
    ]


# --------------------------------------------------------------------------
# pipeline stages
# --------------------------------------------------------------------------
def _count_markdown(root: Path, *relative: str) -> int:
    total = 0
    for rel in relative:
        directory = root / rel
        if directory.is_dir():
            total += sum(1 for p in directory.rglob("*.md") if p.is_file())
    return total


def _count_matching(directory: Path, pattern: str) -> int:
    """Regular files under ``directory`` matching one glob.

    Placeholders never count: they are what lets an empty drop zone travel, and
    reporting one as an artifact would light a tramo with nothing in it.
    """
    if not directory.is_dir():
        return 0
    return sum(
        1 for path in directory.glob(pattern)
        if path.is_file() and path.name not in PLACEHOLDER_FILES
    )


def _count_entries(directory: Path) -> int:
    """Entries in a drop-zone directory, the placeholders aside."""
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.iterdir() if path.name not in PLACEHOLDER_FILES)


def _count_recursive(directory: Path) -> int:
    """Regular files anywhere under ``directory``, the placeholders aside."""
    if not directory.is_dir():
        return 0
    return sum(
        1 for path in directory.rglob("*")
        if path.is_file() and path.name not in PLACEHOLDER_FILES
    )


def _active_agents(root: Path) -> dict[str, list[str]]:
    by_stage: dict[str, list[str]] = {stage: [] for stage, _ in PIPELINE_STAGES}
    agents_dir = root / ".claude" / "agents"
    if not agents_dir.is_dir():
        return by_stage
    for path in sorted(agents_dir.glob("*.md")):
        stage = AGENT_STAGES.get(path.stem)
        if stage:
            by_stage[stage].append(path.stem)
    return by_stage


def _pipeline_stages(root: Path, sections: list[dict[str, Any]],
                     gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One node per tramo, lit only by bytes the workspace actually holds.

    Every reader below answers a question about a file or a directory; none of
    them infers progress from a task list. A stage whose artifact is absent
    reports ``active: False`` and a detail that says what is missing, which is
    the honest answer and the one the board needs to be trusted.
    """
    agents = _active_agents(root)
    harness_dirs = [name for name in HARNESS_PROJECTIONS if (root / name).is_dir()]
    sota = [name for name in SOTA_POOL_ARTIFACTS if (root / "sota-pool" / name).is_file()]
    guidance_files = _count_markdown(root, "guidance")
    proposals = _count_matching(root / "proposals", "*.md")
    proposal_graphs = _count_matching(root / "proposals", PROPOSAL_GRAPH_GLOB)
    implementations = _count_entries(root / "implementations")
    deliberation_records = _count_recursive(root / EXPERIMENTAL_DELIBERATION)
    experimental_revisions = _count_matching(root / "experiments",
                                             EXPERIMENTAL_REVISION_GLOB)
    store = credentials_store(root)
    credentials = store is not None and store.is_file()
    inbox = _inbox(root)
    figures = _figures(root)
    blocks_total = sum(s["blocks_total"] for s in sections)
    blocks_written = sum(s["blocks_written"] for s in sections)
    gates_passed = sum(1 for g in gates if g["state"] == "PASSED")
    pdf = (root / "paper" / "main.pdf").is_file()
    main_tex = (root / "paper" / "main.tex").is_file()

    def ratio(done: int, total: int) -> float:
        if total <= 0:
            return 1.0 if done else 0.0
        return round(min(1.0, done / total), 3)

    #: The proposal tramo holds two kinds of artifact, and both are named even
    #: when one is zero: a revision published without its sky graph is exactly
    #: the half-done state worth showing, and a detail that only reported the
    #: revision would read as finished.
    proposal_progress = ratio((1 if proposals else 0) + (1 if proposal_graphs else 0), 2)
    proposal_detail = (
        f"{proposals} proposal(s), {proposal_graphs} sky graph(s)"
        if proposals or proposal_graphs else "no proposal revision"
    )

    definitions = {
        "harness": (
            bool(harness_dirs), ratio(len(harness_dirs), len(HARNESS_PROJECTIONS)),
            f"{len(harness_dirs)}/{len(HARNESS_PROJECTIONS)} harness projection(s)",
        ),
        "plausibility": (
            bool(sota), ratio(len(sota), len(SOTA_POOL_ARTIFACTS)),
            "sota-pool/: " + ", ".join(sota) if sota else "no sota-pool artifact",
        ),
        "ingestion": (guidance_files > 0, ratio(1 if guidance_files else 0, 1),
                      f"{guidance_files} guidance file(s)"),
        "proposal": (proposals > 0 or proposal_graphs > 0, proposal_progress,
                     proposal_detail),
        "implementation": (implementations > 0, ratio(min(implementations, 1), 1),
                           f"{implementations} implementation(s)"),
        "experimental-deliberation": (
            deliberation_records > 0, ratio(min(deliberation_records, 1), 1),
            f"{deliberation_records} deliberation record(s)",
        ),
        "experimental-implementation": (
            experimental_revisions > 0, ratio(min(experimental_revisions, 1), 1),
            f"{experimental_revisions} experimental revision(s)",
        ),
        "credentials": (
            credentials, 1.0 if credentials else 0.0,
            f"{store.parent.name}/{store.name} present" if store is not None and credentials
            else "no validated credentials",
        ),
        "remote": (inbox["count"] > 0, ratio(min(inbox["count"], 1), 1),
                   f"{inbox['count']} inbox entry(ies)"),
        "writing": (blocks_written > 0, ratio(blocks_written, blocks_total),
                    f"{blocks_written}/{blocks_total} blocks written"),
        "figures": (figures["count"] > 0, ratio(min(figures["count"], 1), 1),
                    f"{figures['count']} figure file(s)"),
        "paper": (
            main_tex, 1.0 if pdf else (0.5 if main_tex else 0.0),
            "paper/main.tex + main.pdf" if pdf else (
                "paper/main.tex present" if main_tex else "paper/main.tex absent"),
        ),
        "audit": (
            bool(gates) and gates_passed == len(gates),
            ratio(gates_passed, len(gates)),
            f"{gates_passed}/{len(gates)} gates passed",
        ),
    }
    stages: list[dict[str, Any]] = []
    for stage, title in PIPELINE_STAGES:
        active, progress, detail = definitions[stage]
        if stage == "writing" and not main_tex and sections:
            progress = 0.0
        stages.append({
            "id": stage,
            "title": title,
            "active": active,
            "progress": progress,
            "detail": detail,
            "workers": agents.get(stage, []),
        })
    return stages


# --------------------------------------------------------------------------
# evidence, figures, inbox, workspace metadata
# --------------------------------------------------------------------------
def _experiments(root: Path) -> dict[str, Any]:
    directory = root / "experiments"
    if not directory.is_dir():
        return {"count": 0, "files": []}
    files = sorted(
        str(p.relative_to(root)) for p in directory.rglob("*")
        if p.is_file() and p.name != ".gitkeep"
    )
    return {"count": len(files), "files": files}


def _figures(root: Path) -> dict[str, Any]:
    directory = root / "paper" / "Figures"
    if not directory.is_dir():
        return {"count": 0, "pdf": [], "rasters": []}
    return {
        "count": len(list(directory.glob("*"))),
        "pdf": sorted(p.name for p in directory.glob("*.pdf")),
        "rasters": sorted(p.name for p in directory.glob("*.png")),
    }


#: The declaration a skill makes when it owns a drop-zone directory: a
#: module-level constant whose value is that directory's name. The command center
#: reads the owner's declaration instead of restating the name, so the forge
#: ships no target's own vocabulary into every workspace and the skill that owns
#: the drop-zone stays its single source of truth. No declaration means no inbox
#: to report -- which is the honest answer, not a fallback to a remembered name.
INBOX_DECLARATION = "INBOX_NAME"


def _module_string_constants(script: Path, names: tuple[str, ...]) -> dict[str, str]:
    """Module-level string constants of one script, by name.

    Parsed with `ast`, never grepped: a name mentioned in a docstring or an
    error message is not a declaration, and a scanner that could not tell them
    apart would pick up whichever it met first.
    """
    return memo_by_file("constants", script, lambda: _parse_string_constants(script, names), names)


def _parse_string_constants(script: Path, names: tuple[str, ...]) -> dict[str, str]:
    try:
        tree = ast.parse(script.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return {}
    found: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            name = getattr(target, "id", None)
            if name in names:
                found[name] = node.value.value
    return found


def inbox_directory(root: Path) -> str | None:
    """The drop-zone directory the workspace's own skills declare, if any."""
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return None
    for script in sorted(skills_dir.glob("*/scripts/*.py")):
        declared = _module_string_constants(script, (INBOX_DECLARATION,))
        if INBOX_DECLARATION in declared:
            return declared[INBOX_DECLARATION]
    return None


def credentials_store(root: Path) -> Path | None:
    """The credential store the workspace's own skill declares, if any.

    The store's owner names its directory and its file, and this reads both
    rather than restating either. A restated path is the same one this reader
    would have had to spell out, and it would put one target's vocabulary inside
    a file every workspace receives.
    """
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return None
    wanted = (STORE_DECLARATION, STORE_FILE_DECLARATION)
    for script in sorted(skills_dir.glob("*/scripts/*.py")):
        declared = _module_string_constants(script, wanted)
        if set(declared) == set(wanted):
            # parents[1] is the skill directory the script's own `scripts/` sits in.
            return script.parents[1] / declared[STORE_DECLARATION] / declared[STORE_FILE_DECLARATION]
    return None


def _inbox(root: Path) -> dict[str, Any]:
    name = inbox_directory(root)
    if name is None:
        return {"count": 0, "paths": [], "directory": None}
    directory = root / name
    if not directory.is_dir():
        return {"count": 0, "paths": [], "directory": name}
    paths = sorted(
        str(path.relative_to(directory)) for path in directory.iterdir()
        if path.name not in PLACEHOLDER_FILES
    )
    return {"count": len(paths), "paths": paths, "directory": name}


def _papersmith_yaml(root: Path) -> dict[str, Any]:
    return _load_yaml(root / "papersmith.yaml")


def _paper_metadata(root: Path) -> dict[str, Any]:
    # A workspace config that is valid JSON but not an object (a list, a bare
    # string) must degrade the metadata, not abort `/api/state` with a 500.
    config = _load_json(root / ".papersmith" / "config.json")
    config = config if isinstance(config, dict) else {}
    yaml_data = _papersmith_yaml(root)
    yaml_data = yaml_data if isinstance(yaml_data, dict) else {}
    compute = config.get("execution_engine") if isinstance(config.get("execution_engine"), dict) else {}
    authors = yaml_data.get("authors")
    if not isinstance(authors, list):
        authors = []
    return {
        "name": yaml_data.get("name") or config.get("project_name") or root.name,
        "title": yaml_data.get("title") or config.get("project_name") or root.name,
        "topic": yaml_data.get("topic", "unspecified"),
        "venue_target": yaml_data.get("venue_target", "unspecified"),
        "authors": [a for a in authors if isinstance(a, (str, dict))],
        "domain_profile": yaml_data.get("domain_profile") or yaml_data.get("profile") or "unspecified",
        "tools": config.get("active_tools", []),
        "compute_target": compute.get("active_compute_target", "unspecified"),
    }


def _workspace(root: Path) -> dict[str, Any]:
    version = _read_text(root / ".papersmith" / "version")
    return {
        "root": str(root),
        "name": root.name,
        "version": (version or "").strip() or None,
    }


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------
def get_workspace_state(root: Path | str) -> dict[str, Any]:
    """Derive the full read-only state payload for a workspace.

    ``root`` is the initialized paper directory. A non-existent root is not an
    error: the dashboard still renders an empty, explicitly-empty workspace.
    """
    root_path = Path(root).expanduser()
    sections_dir = root_path / "sections"
    bib = _bib_keys(root_path / "paper" / "refs.bib")
    draft = _parse_main_tex(root_path / "paper" / "main.tex")

    paths: list[Path] = []
    present = sorted(sections_dir.glob("*.md")) if sections_dir.is_dir() else []
    by_name = {path.stem: path for path in present}
    canonical = set(SECTION_ORDER)
    # The ten canonical slots are always rendered, whether or not their
    # contract file exists. A partially scaffolded sections/ directory must
    # report the missing contracts instead of passing readiness over the files
    # it happens to hold.
    paths = [
        by_name.get(name, root_path / "sections" / f"{name}.md")
        for name in SECTION_ORDER
    ]
    paths.extend(path for path in present if path.stem not in canonical)

    sections = [_section_payload(root_path, path, draft, bib) for path in paths]
    gates = _gates(root_path, sections)
    stages = _pipeline_stages(root_path, sections, gates)

    drafted_words = sum(s["word_count"] for s in sections)
    placeholders = sum(s["citations"]["placeholders"] for s in sections)
    return {
        "generated_at": _utc_now(),
        "workspace": _workspace(root_path),
        "paper_metadata": _paper_metadata(root_path),
        "sections": sections,
        "gates": gates,
        "pipeline_stages": stages,
        "pipeline_chain": [
            {"from": source, "to": target, "label": label}
            for source, target, label in PIPELINE_CHAIN
        ],
        "gate_links": {
            gate_id: {"from": source, "label": label, "consumed_by": AUDIT_STAGE}
            for gate_id, (source, label) in GATE_SOURCES.items()
        },
        "experiments": _experiments(root_path),
        "figures": _figures(root_path),
        "inbox": _inbox(root_path),
        "totals": {
            "sections": len(sections),
            "blocks_total": sum(s["blocks_total"] for s in sections),
            "blocks_written": sum(s["blocks_written"] for s in sections),
            "word_count": drafted_words,
            "placeholder_citations": placeholders,
            "gates_passed": sum(1 for g in gates if g["state"] == "PASSED"),
            "gates_total": len(gates),
        },
    }
