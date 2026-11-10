#!/usr/bin/env python3
"""diagram_cli: the deterministic half of `experiment-diagrams`.

Five subcommands, each printing exactly one JSON object on stdout:

    derive --target <repo> --name <Name> --kind poc|experiments
    render --spec <path/to/diagrams/<kind>.json>
    audit --spec <path/to/diagrams/<kind>.json>
    audit-svg --svg <path/to/figure.svg>
    status --target <repo> --name <Name>
    validate --target <repo> --name <Name> --kind poc|experiments
             --png-sha256 <hex> --operator-statement "<the operator's words>"
             [--audit-override "<the operator's words>"]

`render` designs the figure at the width it prints (explicit `\\fontsize`
sizes, between 0.70 and 0.90 x the manuscript body size), refuses any overfull
box, and runs the mechanical audit (`skills/_core/figure/diagram_audit.py`)
into `diagrams/<kind>.audit.json`; `validate` requires that audit to read
`pass` for the PNG drawn now, unless the operator's own words override it.

`--target` is the cloned repository under `implementations/<repo>/` (a path,
or the bare `<repo>` name resolved under the forge's own `implementations/`);
the product folder is `<target>/<Name>/`, the same convention the shared
implementation engine uses. Every file this script writes lands inside
`<target>/<Name>/diagrams/`.

A refusal prints `{"ok": false, "error": <CODE>, "message": ...}` and exits
non-zero. Codes: `APPROVAL_ABSENT`, `PRODUCT_ABSENT`, `DIAGRAMS_OUTSIDE_PRODUCT`,
`SPEC_INVALID`, `TEX_TOOLCHAIN_ABSENT`, `TEX_COMPILE_FAILED`, `TEX_OVERFULL`,
`RASTER_TOOLCHAIN_ABSENT`, and for `validate`: `SPEC_ABSENT`, `DIAGRAM_ABSENT`,
`PNG_HASH_INVALID`, `PNG_HASH_MISMATCH`, `STATEMENT_EMPTY`, `AUDIT_NOT_PASSED`.

`derive`, `status` and `validate` use the standard library only; `render`
and `audit` load `_core/figure/diagram_audit` (pypdfium2); `audit-svg` loads
`_core/figure/svg_audit` (stdlib only). TeX runs with shell escape disabled; every process is
spawned from an argument list, never a shell string.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = FORGE_ROOT / "implementations"

KINDS = ("poc", "experiments")
#: The approval marker each kind waits for (the holder each implementation
#: skill declares in its own profile).
MARKERS = {"poc": "AGREED.md", "experiments": "Experimental_AGREED.md"}

ROLES = ("operator", "state", "focal", "evidence", "context", "group")
ROWS = ("spine", "evidence", "context")
SEMANTICS = ("data", "supervision", "feedback", "inhibition")
PROMINENCE = ("primary", "secondary")
MAX_LABEL = 56
MAX_CLAIM = 220
MAX_SPINE = 7

#: Where TeX engines and rasterizers live when PATH misses them: macOS
#: (MacTeX, Homebrew), Linux and WSL (a TeX Live install), searched newest
#: TeX Live year first. The same list is restated in
#: `skills/_core/command_center/toolchain.py` and `smith doctor`;
#: `tests/test_toolchain_search.py` fails when they drift.
TOOL_FALLBACK_DIRS: tuple[str, ...] = (
    "/Library/TeX/texbin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/local/texlive/*/bin/*",
    "/opt/texlive/*/bin/*",
    "~/texlive/*/bin/*",
)
TEX_FALLBACK_DIRS: tuple[str, ...] = TOOL_FALLBACK_DIRS
RASTER_FALLBACK_DIRS: tuple[str, ...] = TOOL_FALLBACK_DIRS
TEX_ENGINES = ("latexmk", "pdflatex", "lualatex")
RASTERIZERS = ("pdftoppm", "pdftocairo", "gs", "sips")
TEX_TIMEOUT_S = 180
RASTER_TIMEOUT_S = 60
RASTER_DPI = 200

#: kpathsea variables: no `\write18`, and TeX reads and writes only below
#: the working directory (paranoid mode).
TEX_SANDBOX_ENV = {"shell_escape": "f", "openin_any": "p", "openout_any": "p"}


class Refusal(Exception):
    def __init__(self, code: str, message: str, **extra) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


# -- paths ----------------------------------------------------------------------

def resolve_product(raw_target: str, name: str) -> Path:
    candidate = Path(raw_target).expanduser()
    if not candidate.is_dir() and os.sep not in raw_target and "/" not in raw_target:
        candidate = WORKSPACE / raw_target
    product = candidate.resolve() / name
    if not name or name in (".", "..") or "/" in name or "\\" in name or not product.is_dir():
        raise Refusal("PRODUCT_ABSENT", f"no product folder at {product}")
    return product


def diagram_paths(product: Path, kind: str) -> dict[str, Path]:
    folder = product / "diagrams"
    if folder.is_symlink() or (folder.exists() and product.resolve() not in folder.resolve().parents):
        raise Refusal("DIAGRAMS_OUTSIDE_PRODUCT",
                      f"{folder} is a link or leaves the product folder; diagrams are written only inside it")
    return {ext: folder / f"{kind}.{ext}" for ext in ("json", "tex", "pdf", "png")}


# -- operator validation ----------------------------------------------------------
#
# The operator validates a drawn diagram in one of two ways, both recording the
# same file: the dashboard's "Validar diagrama" button (`write_validation` with
# no provenance, the record shape it has always written) or an explicit
# approval in the conversation with an agent, which runs `validate` with the
# operator's words verbatim and the SHA-256 of the PNG it showed
# (`via: "chat"`). The record holds the PNG's fingerprint, so a diagram drawn
# again reads `stale` until the operator looks at it again; `render` deletes
# it. `remote-execution submit` reads `validation_state` and refuses a launch
# until every approved kind reads `validated`, whichever way it was validated.

VALIDATION_STATES = ("absent", "pending", "validated", "stale")
#: The shortest `--png-sha256` prefix `validate` accepts.
MIN_HASH_PREFIX = 12


def validation_path(product: Path, kind: str) -> Path:
    return product / "diagrams" / f"{kind}.validated.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_record(product: Path, kind: str) -> dict | None:
    try:
        record = json.loads(validation_path(product, kind).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) and record.get("kind") == kind else None


def validation_state(product: Path, kind: str) -> str:
    """`absent` (no PNG drawn), `pending` (drawn, not validated), `validated`,
    or `stale` (validated, then drawn again)."""
    png = product / "diagrams" / f"{kind}.png"
    if png.is_symlink() or not png.is_file():
        return "absent"
    record = _read_record(product, kind)
    if record is None:
        return "pending"
    return "validated" if record.get("png_sha256") == _sha256(png) else "stale"


def validation_provenance(product: Path, kind: str) -> dict | None:
    """How a `validated` diagram was validated: `via` (`chat`, or `dashboard`
    for a record the dashboard wrote, which carries no `via`), the time, and
    the operator's statement (`None` from the dashboard). `None` unless the
    diagram reads `validated`."""
    if validation_state(product, kind) != "validated":
        return None
    record = _read_record(product, kind) or {}
    via = record.get("via")
    statement = record.get("statement")
    return {"via": via if isinstance(via, str) and via else "dashboard",
            "validatedAt": record.get("validated_at"),
            "statement": statement if isinstance(statement, str) else None}


def write_validation(product: Path, kind: str, *, via: str | None = None,
                     statement: str | None = None, audit_override: str | None = None) -> dict:
    """Record that the operator validated the PNG drawn now. The dashboard
    calls it bare; `validate` passes `via="chat"` and the operator's words,
    plus `audit_override` (the operator's words) when it validated a diagram
    whose mechanical audit does not read `pass`."""
    if kind not in KINDS:
        raise Refusal("USAGE", f"kind must be one of {KINDS}, not {kind!r}")
    png = diagram_paths(product, kind)["png"]
    if png.is_symlink() or not png.is_file():
        raise Refusal("DIAGRAM_ABSENT", f"diagrams/{png.name} has not been drawn yet")
    record = {"kind": kind, "png_sha256": _sha256(png),
              "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if via is not None:
        record["via"] = via
        record["statement"] = statement
    if audit_override:
        record["audit_override"] = audit_override
    # A temporary file renamed over the record replaces a link planted there
    # instead of writing through it to wherever it points.
    target = validation_path(product, kind)
    handle, temporary = tempfile.mkstemp(prefix=f".{kind}.validated.", dir=target.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return record


# -- text -----------------------------------------------------------------------

def sentence_case(text: str) -> str:
    """Lower every capitalised word after the first, keeping acronyms and
    words with inner capitals (EEG, ADHD, PyTorch) as they are."""
    words = text.split()
    out = []
    for index, word in enumerate(words):
        core = word.strip("()[]:,.;")
        if index and re.fullmatch(r"[A-Z][a-z]+(-[A-Za-z]+)*", core):
            word = word.replace(core, core.lower())
        out.append(word)
    return " ".join(out)


def shorten(text: str, limit: int = 40) -> str:
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    text = re.sub(r"\s*\([^)]*\)$", "", text)
    if ":" in text[3:] and len(text) > limit:
        text = text[:text.index(":", 3)]
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "..."


def _is_title_case(label: str) -> bool:
    later = label.split()[1:]
    titled = [w for w in later if re.fullmatch(r"[A-Z][a-z]+", w.strip("(),.:;"))]
    return len(later) >= 2 and len(titled) == len(later)


# -- evidence -------------------------------------------------------------------

_STEP = re.compile(r"^- \[[ xX]\] \d+\.\s+(?P<text>.*?)\s*(`@step (?P<id>[^`]+)`)?\s*$")


def read_marker(path: Path) -> tuple[str | None, list[dict]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    revision = None
    found = re.search(r"revision=(\S+)", text)
    if found:
        revision = found.group(1)
    steps = []
    for line in text.splitlines():
        match = _STEP.match(line.strip())
        if match:
            steps.append({"text": match.group("text"), "id": match.group("id") or ""})
    return revision, steps


def find_revision(product: Path, revision: str | None) -> Path | None:
    if not revision or "/" in revision or "\\" in revision:
        return None
    for ancestor in list(product.parents)[:4]:
        for folder in ("proposals", "experiments"):
            candidate = ancestor / folder / revision
            if candidate.is_file():
                return candidate
    return None


def read_revision(path: Path | None) -> tuple[str | None, list[str]]:
    if path is None:
        return None, []
    title = None
    experiments = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if title is None and line.startswith("# "):
            title = line[2:].strip()
        found = re.match(r"^## Experiment \[exp:(\w+)\]\s*[—–-]+\s*(.+)$", line.strip())
        if found:
            experiments.append(f"{found.group(1)}: {sentence_case(found.group(2).strip())}")
    return title, experiments


def _relative(path: Path, product: Path) -> str:
    for base in list(product.parents)[:4]:
        try:
            return str(path.relative_to(base))
        except ValueError:
            continue
    return path.name


def derive_spec(product: Path, kind: str) -> dict:
    marker = product / MARKERS[kind]
    if not marker.is_file():
        raise Refusal("APPROVAL_ABSENT",
                      f"{MARKERS[kind]} is missing in {product}; the {kind} diagram is drawn "
                      "only once that approval is settled")
    revision_name, steps = read_marker(marker)
    revision = find_revision(product, revision_name)
    title, experiments = read_revision(revision)
    topic = sentence_case(title).rstrip(".") if title else product.name
    topic = re.split(r"\s+(?:for|with|using|via)\s+", topic, maxsplit=1)[0] if len(topic) > 60 else topic
    sources = [MARKERS[kind]] + ([_relative(revision, product)] if revision else
                                 ([revision_name] if revision_name else []))
    if kind == "poc":
        return _derive_poc(topic, steps, sources)
    return _derive_experiments(topic, steps, experiments, sources)


def _version(sources: list[str]) -> str:
    found = re.search(r"-([rv]\d+)\.md$", sources[-1]) if len(sources) > 1 else None
    return f", revision {found.group(1)}" if found else ""


def _derive_poc(topic: str, steps: list[dict], sources: list[str]) -> dict:
    chosen = steps[:4] or [{"text": "Train every arm on the toy set", "id": "train"}]
    focal_index = next((i for i, s in enumerate(chosen) if re.search(r"train|run|pilot", s["id"] + s["text"], re.I)),
                       len(chosen) // 2)
    nodes = [{"id": "data", "label": "Toy set", "role": "state", "row": "spine"}]
    for index, step in enumerate(chosen):
        nodes.append({"id": f"s{index + 1}", "label": shorten(step["text"]),
                      "role": "focal" if index == focal_index else "operator", "row": "spine"})
    nodes.append({"id": "results", "label": "Convergence and pilot tables", "role": "evidence",
                  "row": "evidence", "under": f"s{focal_index + 1}"})
    nodes.append({"id": "source", "label": shorten(f"Approved in {sources[0]}{_version(sources)}", MAX_LABEL - 4), "role": "context",
                  "row": "context", "near": "data"})
    order = ["data"] + [f"s{i + 1}" for i in range(len(chosen))]
    edges = [{"from": a, "to": b, "semantics": "data", "prominence": "primary"} for a, b in zip(order, order[1:])]
    edges.append({"from": f"s{focal_index + 1}", "to": "results", "semantics": "data", "prominence": "secondary"})
    return {
        "version": 1, "kind": "poc",
        "claim": shorten(f"A small pilot shows that {topic[:1].lower() + topic[1:]} runs end to end "
                         "and leaves evidence a person can read", MAX_CLAIM),
        "focal": f"s{focal_index + 1}", "nodes": nodes, "edges": edges, "sources": sources,
    }


def _derive_experiments(topic: str, steps: list[dict], experiments: list[str], sources: list[str]) -> dict:
    run = next((s for s in steps if re.search(r"run|train|grid", s["id"] + s["text"], re.I)), None)
    nodes = [
        {"id": "data", "label": "Official dataset", "role": "state", "row": "spine"},
        {"id": "run", "label": shorten(run["text"]) if run else "Run every arm and seed", "role": "focal", "row": "spine"},
        {"id": "test", "label": "Test each comparison", "role": "operator", "row": "spine"},
        {"id": "report", "label": "Significance table and figures", "role": "evidence", "row": "spine"},
    ]
    edges = [
        {"from": "data", "to": "run", "semantics": "data", "prominence": "primary"},
        {"from": "run", "to": "test", "semantics": "data", "prominence": "primary"},
        {"from": "test", "to": "report", "semantics": "data", "prominence": "primary"},
    ]
    for index, experiment in enumerate(experiments[:5]):
        node_id = f"e{index + 1}"
        nodes.append({"id": node_id, "label": shorten(experiment), "role": "evidence", "row": "evidence"})
        edges.append({"from": "run", "to": node_id, "semantics": "data", "prominence": "secondary"})
    nodes.append({"id": "source", "label": shorten(f"Approved in {sources[0]}{_version(sources)}", MAX_LABEL - 4), "role": "context",
                  "row": "context", "near": "data"})
    count = len(experiments)
    claim = (f"The full protocol tests {topic[:1].lower() + topic[1:]} through "
             f"{count} experiment{'s' if count != 1 else ''}, each judged by its own significance test")
    return {"version": 1, "kind": "experiments", "claim": shorten(claim, MAX_CLAIM), "focal": "run",
            "nodes": nodes, "edges": edges, "sources": sources}


# -- validation -----------------------------------------------------------------

def validate_spec(spec) -> list[str]:
    """Every problem, each naming its field; empty means valid."""
    if not isinstance(spec, dict):
        return ["spec: must be a JSON object"]
    errors: list[str] = []
    if spec.get("kind") not in KINDS:
        errors.append(f"kind: must be one of {', '.join(KINDS)}")
    claim = spec.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        errors.append("claim: the one sentence the figure must communicate is required")
    elif len(claim) > MAX_CLAIM:
        errors.append(f"claim: longer than {MAX_CLAIM} characters")
    nodes = spec.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return errors + ["nodes: a non-empty list is required"]
    ids: dict[str, dict] = {}
    for index, node in enumerate(nodes):
        where = f"nodes[{index}]"
        if not isinstance(node, dict):
            errors.append(f"{where}: must be an object")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", node_id):
            errors.append(f"{where}.id: letters, digits, '-' or '_', starting with a letter")
        elif node_id in ids:
            errors.append(f"{where}.id: duplicate id {node_id!r}")
        else:
            ids[node_id] = node
        if node.get("role") not in ROLES:
            errors.append(f"{where}.role: must be one of {', '.join(ROLES)}")
        label = node.get("label")
        if not isinstance(label, str) or not label.strip():
            errors.append(f"{where}.label: required")
        elif len(label) > MAX_LABEL:
            errors.append(f"{where}.label: longer than {MAX_LABEL} characters")
        elif _is_title_case(label):
            errors.append(f"{where}.label: use sentence case, not title case")
        if node.get("role") == "group":
            members = node.get("members")
            if not isinstance(members, list) or not members:
                errors.append(f"{where}.members: a group needs the ids it encloses")
        elif node.get("row", "spine") not in ROWS:
            errors.append(f"{where}.row: must be one of {', '.join(ROWS)}")
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        for key in ("under", "near"):
            if key in node and node[key] not in ids:
                errors.append(f"nodes[{index}].{key}: unknown node {node[key]!r}")
        if node.get("role") == "group" and isinstance(node.get("members"), list):
            for member in node["members"]:
                if member not in ids:
                    errors.append(f"nodes[{index}].members: unknown node {member!r}")
    focal = [n for n in ids.values() if n.get("role") == "focal"]
    if len(focal) != 1:
        errors.append("nodes: exactly one node takes the focal role")
    if spec.get("focal") not in ids or (focal and spec.get("focal") != focal[0].get("id")):
        errors.append("focal: must name the one node whose role is focal")
    spine = [n for n in ids.values() if n.get("role") != "group" and n.get("row", "spine") == "spine"]
    if not 2 <= len(spine) <= MAX_SPINE:
        errors.append(f"nodes: the reading spine holds 2 to {MAX_SPINE} nodes, found {len(spine)}")
    edges = spec.get("edges")
    if not isinstance(edges, list) or not edges:
        return errors + ["edges: a non-empty list is required"]
    primaries = 0
    for index, edge in enumerate(edges):
        where = f"edges[{index}]"
        if not isinstance(edge, dict):
            errors.append(f"{where}: must be an object")
            continue
        for end in ("from", "to"):
            if edge.get(end) not in ids:
                errors.append(f"{where}.{end}: unknown node {edge.get(end)!r}")
            elif ids[edge[end]].get("role") == "group":
                errors.append(f"{where}.{end}: a group is whitespace, not an endpoint")
        if edge.get("from") == edge.get("to"):
            errors.append(f"{where}.to: an edge needs two different nodes")
        if edge.get("semantics") not in SEMANTICS:
            errors.append(f"{where}.semantics: must be one of {', '.join(SEMANTICS)}")
        if edge.get("prominence") not in PROMINENCE:
            errors.append(f"{where}.prominence: must be one of {', '.join(PROMINENCE)}")
        primaries += edge.get("prominence") == "primary"
        label = edge.get("label")
        if label is not None and (not isinstance(label, str) or len(label) > 24):
            errors.append(f"{where}.label: at most 24 characters")
    if not primaries:
        errors.append("edges: the reading spine needs at least one primary edge")
    errors += _validate_print(spec.get("print"))
    return errors


#: The optional `print` block: how the manuscript includes the figure.
PRINT_BOUNDS = {"body_pt": (6.0, 14.0), "text_width_pt": (100.0, 700.0), "width_fraction": (0.2, 1.0)}


def _validate_print(block) -> list[str]:
    if block is None:
        return []
    if not isinstance(block, dict):
        return ["print: must be an object (body_pt, text_width_pt, width_fraction)"]
    errors = []
    for key, value in block.items():
        if key not in PRINT_BOUNDS:
            errors.append(f"print.{key}: unknown key; use {', '.join(PRINT_BOUNDS)}")
            continue
        low, high = PRINT_BOUNDS[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            errors.append(f"print.{key}: a number from {low:g} to {high:g}")
    return errors


# -- TeX ------------------------------------------------------------------------
#
# The figure is designed at the size it prints. Its content width is the
# declared inclusion width (`print.width_fraction` x `\textwidth`, default
# the full text width of the manuscript's body size), so it is included at
# scale ~1 and every font prints at the explicit `\fontsize` written here:
# never a relative switch (`\small`, `\footnotesize`), always between
# 0.70 and 0.90 x the body size (`_core/figure/diagram_audit.role_font_pt`:
# claim 0.88, spine 0.82, notes 0.76). Boxes
# take their width from the space the layout has; a label that does not fit
# is a spec problem (shorten it), never a reason to shrink a font.

#: papersmith's own figure library. Written from Sivia's design rules
#: (github.com/exsinger-hub/Sivia), not copied from it. Font sizes are the
#: `\ps...Font` macros `font_macros()` defines per render. `psCanvas` stays
#: defined for callers that paint their own preview; the paper export draws
#: no background.
TIKZ_LIBRARY = r"""
\definecolor{psCanvas}{HTML}{F7F3E8}
\definecolor{psInk}{HTML}{20252B}
\definecolor{psCool}{HTML}{4F7CAC}
\definecolor{psWarm}{HTML}{E09F3E}
\definecolor{psAlert}{HTML}{D96855}
\tikzset{
  ps base/.style={align=center, text=psInk, font=\psSpineFont, inner sep=4pt},
  ps operator/.style={ps base, rectangle, rounded corners=3pt, draw=psCool,
    fill=psCool!14, line width=1.5pt},
  ps state/.style={ps base, rectangle, rounded corners=8pt, draw=psInk!60, fill=psInk!7,
    line width=1.3pt},
  ps focal/.style={ps base, rectangle, rounded corners=5pt, draw=psAlert, fill=psWarm!32,
    line width=1.8pt, font=\psFocalFont},
  ps evidence/.style={ps base, rectangle, draw=psInk!45, fill=white,
    line width=1.3pt, font=\psNoteFont},
  ps context/.style={ps base, font=\psNoteFont, text=psInk!75, align=left, inner sep=2pt},
  ps group/.style={rectangle, rounded corners=6pt, fill=psCool!7, draw=psCool!30,
    line width=0.8pt, inner sep=5pt},
  ps claim/.style={font=\psClaimFont, text=psInk, align=left, inner sep=0pt},
  ps primary/.style={draw=psInk, line width=1.9pt, -{Stealth[length=3.0mm, width=2.6mm]}},
  ps secondary/.style={draw=psInk!50, line width=1.4pt, -{Stealth[length=2.4mm, width=2.1mm]}},
  ps data/.style={},
  ps supervision/.style={dash pattern=on 5pt off 3pt},
  ps feedback/.style={bend left=40},
  ps inhibition/.style={-{Bar[width=3.4mm]}},
  ps edge label/.style={font=\psNoteFont, text=psInk!80, fill=white, inner sep=1.5pt},
}
""".strip("\n")

_SPECIALS = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
             "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
             # OT1 has no glyphs for these: as text they print as ¡ ¿ and a dash.
             "<": r"\ensuremath{<}", ">": r"\ensuremath{>}", "|": r"\ensuremath{|}"}


def tex_escape(text: str) -> str:
    return "".join(_SPECIALS.get(ch, ch) for ch in text)


#: TeX points per centimetre.
PT_PER_CM = 72.27 / 2.54
#: `standalone` border (TeX pt): the page margin around the drawn content.
BORDER_PT = 2.0
#: Content width kept free of the page edge for strokes and arrow tips.
STROKE_ALLOWANCE_PT = 2.0
#: Defaults when neither the spec nor a manuscript says otherwise.
DEFAULT_BODY_PT = 10.0
#: Horizontal gap between neighbouring boxes (cm): room for an arrow tip.
GAP_CM = 0.6
#: The narrowest gap the fit pass may use when a label overflows its box.
MIN_GAP_CM = 0.45
#: The widest a spine box grows on a short spine (cm).
MAX_BOX_CM = 3.4
#: Vertical gap between the spine row and the evidence row (cm), holding
#: the shared lane the branch connectors run along.
ROW_GAP_CM = 0.9
#: Vertical gap between the spine and the context row, and above it the claim.
CONTEXT_GAP_CM = 0.35
#: Horizontal padding inside a box (TeX pt), the `inner sep` of `ps base`.
INNER_SEP_PT = 4.0


def font_macros(sizes: dict) -> list[str]:
    """The four `\\ps...Font` macros, each an explicit `\\fontsize`."""
    fontsize = _diagram_audit().fontsize_command
    return [
        f"\\newcommand{{\\psClaimFont}}{{{fontsize(sizes['claim'])}\\bfseries}}",
        f"\\newcommand{{\\psSpineFont}}{{{fontsize(sizes['spine'])}}}",
        f"\\newcommand{{\\psFocalFont}}{{{fontsize(sizes['spine'])}\\bfseries}}",
        f"\\newcommand{{\\psNoteFont}}{{{fontsize(sizes['note'])}}}",
    ]


def _diagram_audit():
    """`_core/figure/diagram_audit` (pypdfium2 behind it), loaded only by the
    verbs that draw or audit, so `derive`, `status` and `validate` stay
    standard-library only."""
    core = FORGE_ROOT / "skills" / "_core" / "figure"
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))
    import diagram_audit  # noqa: E402  (resolved above)

    return diagram_audit


def find_manuscript(product: Path) -> Path | None:
    """`paper/main.tex` of the workspace the product lives in, if any."""
    for ancestor in [product, *list(product.parents)[:5]]:
        candidate = ancestor / "paper" / "main.tex"
        if candidate.is_file():
            return candidate
    return None


def print_settings(spec: dict, product: Path | None = None) -> dict:
    """The size the figure prints at: the manuscript body size (the spec's
    `print.body_pt`, else `paper/main.tex`'s class option, else 10 pt), the
    text width (`print.text_width_pt`, else the A4 article width for that
    body size) and the inclusion fraction (`print.width_fraction`, else 1).
    Every length here is in TeX points except `printed_width_pdf_pt`."""
    audit = _diagram_audit()
    declared = spec.get("print") if isinstance(spec.get("print"), dict) else {}
    if "body_pt" in declared:
        body, source = float(declared["body_pt"]), "spec"
    else:
        manuscript = find_manuscript(product) if product is not None else None
        if manuscript is not None:
            body, source = audit.print_scale.body_font_pt(manuscript)
            source = f"{manuscript.name}:{source}"
        else:
            body, source = DEFAULT_BODY_PT, "default"
    text_width = float(declared.get("text_width_pt") or audit.default_text_width_pt(body))
    fraction = float(declared.get("width_fraction") or 1.0)
    printed = text_width * fraction
    return {
        "body_pt": body, "body_source": source, "text_width_pt": text_width,
        "width_fraction": fraction, "printed_width_pt": printed,
        "printed_width_pdf_pt": audit.print_scale.declared_width_pt(text_width, fraction),
        "fonts": audit.role_font_pt(body),
    }


def _wrap_lines(text: str, width_pt: float, font_pt: float, bold: bool = False) -> int:
    """Lines a centred label needs at `font_pt` in `width_pt` (a generous
    estimate: 0.56 em per character, 0.6 em bold)."""
    per_char = font_pt * (0.6 if bold else 0.56)
    lines, current = 1, 0.0
    for word in text.split():
        size = len(word) * per_char
        if current and current + per_char + size > width_pt:
            lines += 1
            current = size
        else:
            current = current + (per_char if current else 0.0) + size
    return lines


def _box_height_cm(label: str, text_width_cm: float, font_pt: float, bold: bool = False) -> float:
    lines = _wrap_lines(label, text_width_cm * PT_PER_CM, font_pt, bold)
    return (lines * 1.2 * font_pt + 2 * INNER_SEP_PT + 2.0) / PT_PER_CM


def plan_layout(spec: dict, settings: dict, gap_cm: float = GAP_CM) -> dict:
    """Every box's position (cm) and width, inside the content width.

    The spine runs left to right at y = 0 with one width for every box; the
    evidence row hangs below it (anchor north), the context row sits above
    it (anchor south west). Free evidence boxes share the full width; a
    box pinned `under` a spine node takes that node's column."""
    width_cm = (settings["printed_width_pt"] - 2 * BORDER_PT - STROKE_ALLOWANCE_PT) / PT_PER_CM
    fonts = settings["fonts"]
    nodes = [n for n in spec["nodes"] if n["role"] != "group"]
    inset = 0.25 if any(n["role"] == "group" for n in spec["nodes"]) else 0.0
    inner = width_cm - 2 * inset
    spine = [n for n in nodes if n.get("row", "spine") == "spine"]
    count = max(len(spine), 1)
    box = min(MAX_BOX_CM, (inner - gap_cm * (count - 1)) / count)
    used = count * box + gap_cm * (count - 1)
    start = inset + (inner - used) / 2
    text_cm = max(box - 2 * INNER_SEP_PT / PT_PER_CM - 0.07, 0.5)
    place = {}
    for index, node in enumerate(spine):
        place[node["id"]] = {"x": start + box / 2 + index * (box + gap_cm), "y": 0.0,
                             "row": "spine", "anchor": "center", "text_cm": text_cm}
    spine_h = max([_box_height_cm(n["label"], text_cm, fonts["spine"], n["role"] == "focal")
                   for n in spine] or [1.0])
    spine_h = max(spine_h, 1.0)
    evidence_top = -(spine_h / 2 + ROW_GAP_CM)
    context_bottom = spine_h / 2 + CONTEXT_GAP_CM
    targets = {e["to"]: e["from"] for e in spec["edges"]}

    for row in ("evidence", "context"):
        members = [n for n in nodes if n.get("row") == row]
        anchored = {}
        for node in members:
            pin = node.get("under") or node.get("near")
            if pin in place and place[pin]["row"] == "spine":
                anchored[node["id"]] = place[pin]["x"]
        free = [n for n in members if n["id"] not in anchored]
        if row == "evidence" and len(free) == 1 and targets.get(free[0]["id"]) in place:
            anchored[free[0]["id"]] = place[targets[free[0]["id"]]]["x"]
            free = []
        if row == "evidence":
            k = len(free)
            free_box = min(box, (inner - gap_cm * (k - 1)) / k) if k else box
            free_used = k * free_box + gap_cm * (k - 1)
            free_start = inset + (inner - free_used) / 2
            for index, node in enumerate(free):
                anchored[node["id"]] = free_start + free_box / 2 + index * (free_box + gap_cm)
            for node in members:
                width = free_box if node in free else box
                place[node["id"]] = {
                    "x": anchored[node["id"]], "y": evidence_top, "row": "evidence",
                    "anchor": "north",
                    "text_cm": max(width - 2 * INNER_SEP_PT / PT_PER_CM - 0.07, 0.5)}
        else:
            note_cm = min(inner * 0.6, 7.0)
            for index, node in enumerate(members):
                left = anchored.get(node["id"], inset + box / 2) - box / 2
                left = max(inset, min(left, inset + inner - note_cm))
                place[node["id"]] = {"x": left, "y": context_bottom, "row": "context",
                                     "anchor": "south west", "text_cm": note_cm}
    return {"width_cm": width_cm, "spine_h_cm": spine_h, "evidence_top_cm": evidence_top,
            "context_bottom_cm": context_bottom, "place": place, "gap_cm": gap_cm}


def layout(spec: dict, settings: dict | None = None) -> dict[str, tuple[float, float]]:
    """Box centres in cm (row anchors for the evidence and context rows)."""
    plan = plan_layout(spec, settings or default_settings())
    return {node_id: (p["x"], p["y"]) for node_id, p in plan["place"].items()}


def default_settings() -> dict:
    """`print_settings` with no manuscript: a 10 pt article at full width."""
    return print_settings({})


def _anchors(a: dict, b: dict) -> tuple[str, str]:
    if a["row"] == b["row"]:
        return ("east", "west") if b["x"] > a["x"] else ("west", "east")
    order = {"context": 1, "spine": 0, "evidence": -1}
    return ("south", "north") if order[b["row"]] < order[a["row"]] else ("north", "south")


def _lane_y(plan: dict, a: dict, b: dict) -> float:
    """The one horizontal lane shared by every branch between two rows."""
    rows = {a["row"], b["row"]}
    if rows == {"spine", "evidence"}:
        return -(plan["spine_h_cm"] / 2 + ROW_GAP_CM * 0.5)
    if rows == {"spine", "context"}:
        return plan["spine_h_cm"] / 2 + CONTEXT_GAP_CM * 0.5
    return (a["y"] + b["y"]) / 2


def build_tex(spec: dict, settings: dict | None = None, *, gap_cm: float = GAP_CM) -> str:
    settings = settings or default_settings()
    plan = plan_layout(spec, settings, gap_cm)
    place = plan["place"]
    spine_min_h = plan["spine_h_cm"]
    lines = [
        f"\\documentclass[border={BORDER_PT:g}pt]{{standalone}}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{arrows.meta,shapes.misc,shapes.geometric,positioning,fit,backgrounds,calc}",
        r"\renewcommand{\familydefault}{\sfdefault}",
        r"\hyphenpenalty=10000 \exhyphenpenalty=10000",
        *font_macros(settings["fonts"]),
        TIKZ_LIBRARY,
        r"\begin{document}",
        r"\begin{tikzpicture}",
        f"% figure claim: {tex_escape(spec['claim'])}",
        f"% printed width: {settings['printed_width_pt']:.1f}pt of a {settings['body_pt']:g}pt body "
        f"({settings['body_source']}); fonts {settings['fonts']}",
    ]
    for node in spec["nodes"]:
        if node["role"] == "group":
            continue
        p = place[node["id"]]
        extra = f"text width={p['text_cm']:.2f}cm"
        if p["row"] == "spine":
            extra += f", minimum height={spine_min_h:.2f}cm"
        lines.append(f"\\node[ps {node['role']}, {extra}, anchor={p['anchor']}] ({node['id']}) "
                     f"at ({p['x']:.2f},{p['y']:.2f}) {{{tex_escape(node['label'])}}};")
    for node in spec["nodes"]:
        if node["role"] == "group":
            fit = "".join(f"({m})" for m in node["members"])
            lines.append(r"\begin{scope}[on background layer]")
            lines.append(f"\\node[ps group, fit={fit}] ({node['id']}) {{}};")
            lines.append(r"\end{scope}")
            lines.append(f"\\node[ps context, anchor=south west, text width=3cm] at ({node['id']}.north west) "
                         f"{{{tex_escape(node['label'])}}};")
    lines.append(r"\coordinate (ps top) at (current bounding box.north);")
    lines.append(f"\\node[ps claim, anchor=south west, text width={plan['width_cm']:.2f}cm] "
                 f"at ($(0,0 |- ps top)+(0,{CONTEXT_GAP_CM:.2f})$) {{{tex_escape(spec['claim'])}}};")
    for edge in spec["edges"]:
        a, b = place[edge["from"]], place[edge["to"]]
        styles = [f"ps {edge['prominence']}", f"ps {edge['semantics']}"]
        if edge["semantics"] == "feedback":
            start, end = ("south", "south") if a["row"] == b["row"] else _anchors(a, b)
            path = f"({edge['from']}.{start}) to"
        else:
            start, end = _anchors(a, b)
            path = f"({edge['from']}.{start}) --"
            if start in ("south", "north") and abs(a["x"] - b["x"]) > 1e-6:
                # Orthogonal: leave vertically, run along the lane shared by
                # every edge between these two rows, enter from the facing side.
                lane = _lane_y(plan, a, b)
                path = f"({edge['from']}.{start}) -- ({edge['from']}.{start} |- 0,{lane:.2f}) -|"
        label = ""
        if edge.get("label"):
            side = "above" if start in ("east", "west") else "right"
            label = f" node[ps edge label, midway, {side}] {{{tex_escape(edge['label'])}}}"
        lines.append(f"\\draw[{', '.join(styles)}] {path}{label} ({edge['to']}.{end});")
    lines += [r"\end{tikzpicture}", r"\end{document}", ""]
    return "\n".join(lines)


# -- toolchains -----------------------------------------------------------------

def _which(name: str, path: str | None, fallback_dirs) -> str | None:
    found = shutil.which(name, path=path)
    if found:
        return found
    for pattern in fallback_dirs:
        for directory in sorted(glob.glob(os.path.expanduser(pattern)), reverse=True):
            for filename in (name, f"{name}.exe"):
                candidate = Path(directory) / filename
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return str(candidate)
    return None


def find_tex_engine(path: str | None = None) -> tuple[str, str] | None:
    for name in TEX_ENGINES:
        found = _which(name, path, TEX_FALLBACK_DIRS)
        if found:
            return name, found
    return None


def find_rasterizer(path: str | None = None) -> tuple[str, str] | None:
    for name in RASTERIZERS:
        found = _which(name, path, RASTER_FALLBACK_DIRS)
        if found:
            return name, found
    return None


def _tex_argv(name: str, binary: str, tex: Path) -> list[str]:
    if name == "latexmk":
        engine_dir = Path(binary).parent
        pdflatex = engine_dir / "pdflatex"
        engine = str(pdflatex) if pdflatex.is_file() else "pdflatex"
        return [binary, "-norc", "-g", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
                f"-pdflatex={engine} -no-shell-escape %O %S", tex.name]
    return [binary, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", tex.name]


def compile_tex(tex: Path) -> dict:
    engine = find_tex_engine()
    if engine is None:
        raise Refusal("TEX_TOOLCHAIN_ABSENT",
                      f"none of {', '.join(TEX_ENGINES)} found on PATH or in {', '.join(TEX_FALLBACK_DIRS)}",
                      tex=str(tex))
    name, binary = engine
    env = dict(os.environ, **TEX_SANDBOX_ENV)
    env["PATH"] = os.pathsep.join([str(Path(binary).parent), env.get("PATH", "")])
    try:
        proc = subprocess.run(_tex_argv(name, binary, tex), cwd=tex.parent, env=env,
                              capture_output=True, text=True, timeout=TEX_TIMEOUT_S, shell=False)
        failed = proc.returncode != 0
        tail = (proc.stdout + proc.stderr)[-1500:]
    except subprocess.TimeoutExpired:
        failed, tail = True, f"timed out after {TEX_TIMEOUT_S}s"
    pdf = tex.with_suffix(".pdf")
    if failed or not pdf.is_file():
        raise Refusal("TEX_COMPILE_FAILED", f"{name} could not compile {tex.name}: {tail}", tex=str(tex))
    # The log stays: `render` reads its overfull boxes and `audit` re-reads it.
    for ext in (".aux", ".fls", ".fdb_latexmk"):
        tex.with_suffix(ext).unlink(missing_ok=True)
    log = tex.with_suffix(".log")
    return {"engine": name, "pdf": str(pdf), "log": str(log) if log.is_file() else None}


def _raster_argv(name: str, binary: str, pdf: Path, out_dir: Path) -> tuple[list[str], Path]:
    out = out_dir / "page.png"
    if name in ("pdftoppm", "pdftocairo"):
        return [binary, "-png", "-singlefile", "-r", str(RASTER_DPI), str(pdf), str(out_dir / "page")], out
    if name == "gs":
        return [binary, "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dFirstPage=1", "-dLastPage=1",
                "-sDEVICE=png16m", f"-r{RASTER_DPI}", f"-sOutputFile={out}", str(pdf)], out
    return [binary, "-s", "format", "png", str(pdf), "--out", str(out)], out


def rasterize(pdf: Path) -> dict:
    """The first rasterizer that produces a PNG wins; a present tool that
    fails falls through to the next one."""
    tried = {}
    for name in RASTERIZERS:
        binary = _which(name, None, RASTER_FALLBACK_DIRS)
        if binary is None:
            tried[name] = "absent"
            continue
        with tempfile.TemporaryDirectory(prefix="ps-raster-") as tmp:
            argv, out = _raster_argv(name, binary, pdf.resolve(), Path(tmp))
            try:
                proc = subprocess.run(argv, capture_output=True, text=True,
                                      timeout=RASTER_TIMEOUT_S, shell=False)
                status = f"exit {proc.returncode}"
            except subprocess.TimeoutExpired:
                status = "timed out"
            if out.is_file() and out.stat().st_size:
                png = pdf.with_suffix(".png")
                shutil.copyfile(out, png)
                return {"rasterizer": name, "png": str(png)}
            tried[name] = status
    raise Refusal("RASTER_TOOLCHAIN_ABSENT",
                  "no rasterizer produced a PNG: " + ", ".join(f"{k} {v}" for k, v in tried.items()),
                  pdf=str(pdf))


# -- commands -------------------------------------------------------------------

def cmd_derive(args) -> dict:
    product = resolve_product(args.target, args.name)
    paths = diagram_paths(product, args.kind)
    if not (product / MARKERS[args.kind]).is_file():
        raise Refusal("APPROVAL_ABSENT",
                      f"{MARKERS[args.kind]} is missing in {product}; the {args.kind} diagram is "
                      "drawn only once that approval is settled")
    if paths["json"].is_file() and not args.force:
        return {"ok": True, "kind": args.kind, "spec": str(paths["json"]), "written": False,
                "message": "a spec already exists; pass --force to draft it again"}
    spec = derive_spec(product, args.kind)
    problems = validate_spec(spec)
    if problems:
        raise Refusal("SPEC_INVALID", "; ".join(problems))
    paths["json"].parent.mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True, "kind": args.kind, "spec": str(paths["json"]), "written": True}


def _read_spec(raw: str) -> tuple[Path, dict]:
    spec_path = Path(raw).expanduser().resolve()
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Refusal("SPEC_INVALID", f"spec: no file at {spec_path}")
    except (OSError, ValueError) as exc:
        raise Refusal("SPEC_INVALID", f"spec: not readable JSON ({exc})")
    problems = validate_spec(spec)
    if problems:
        raise Refusal("SPEC_INVALID", "; ".join(problems))
    return spec_path, spec


def _product_of(spec_path: Path) -> Path:
    """`<product>/diagrams/<kind>.json` -> `<product>`."""
    return spec_path.parent.parent


def audit_path(product: Path, kind: str) -> Path:
    return product / "diagrams" / f"{kind}.audit.json"


def _overfull(log: str | None) -> list[str]:
    if not log or not Path(log).is_file():
        return []
    text = Path(log).read_text(encoding="utf-8", errors="replace")
    return _diagram_audit().parse_overfull(text)


def run_audit(spec_path: Path, spec: dict) -> dict:
    """The mechanical audit of the drawn diagram (`_core/figure/diagram_audit`),
    written to `diagrams/<kind>.audit.json` and bound to the PNG it audited."""
    kind = spec["kind"]
    product = _product_of(spec_path)
    folder = spec_path.parent
    pdf, tex, png = (folder / f"{kind}.{ext}" for ext in ("pdf", "tex", "png"))
    if not pdf.is_file():
        raise Refusal("DIAGRAM_ABSENT", f"diagrams/{pdf.name} has not been drawn yet")
    settings = print_settings(spec, product)
    log = tex.with_suffix(".log")
    audit = _diagram_audit()
    report = audit.audit_diagram(
        pdf, body_pt=settings["body_pt"], printed_width_pt=settings["printed_width_pdf_pt"],
        tex_text=tex.read_text(encoding="utf-8") if tex.is_file() else None,
        log_text=log.read_text(encoding="utf-8", errors="replace") if log.is_file() else None)
    record = {
        "kind": kind,
        "verdict": report["verdict"],
        "failures": report["failures"],
        "messages": audit.failure_messages(report),
        "png_sha256": _sha256(png) if png.is_file() else None,
        "pdf_sha256": _sha256(pdf),
        "print": {key: settings[key] for key in ("body_pt", "body_source", "text_width_pt",
                                                 "width_fraction", "printed_width_pdf_pt", "fonts")},
        "audited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "report": report,
    }
    folder.joinpath(f"{kind}.audit.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def _audit_summary(record: dict, path: Path) -> dict:
    return {"verdict": record["verdict"], "failures": record["failures"],
            "messages": record["messages"], "path": str(path)}


def cmd_render(args) -> dict:
    """Write .tex, compile, refuse any overfull box, rasterize, audit.

    The fit pass: when the first compile leaves an overfull box, the boxes
    are widened once (the gap between them shrinks to `MIN_GAP_CM`); fonts
    never shrink. A box still overfull refuses `TEX_OVERFULL` naming it,
    and the Corrector shortens that label in the spec."""
    spec_path, spec = _read_spec(args.spec)
    product = _product_of(spec_path)
    tex = spec_path.with_name(f"{spec['kind']}.tex")
    settings = print_settings(spec, product)
    for stale in (tex.with_suffix(".pdf"), tex.with_suffix(".png"), tex.with_suffix(".log"),
                  tex.with_name(f"{spec['kind']}.validated.json"),
                  tex.with_name(f"{spec['kind']}.audit.json")):
        stale.unlink(missing_ok=True)
    passes = []
    overfull: list[str] = []
    compiled: dict = {}
    for gap in (GAP_CM, MIN_GAP_CM):
        tex.write_text(build_tex(spec, settings, gap_cm=gap), encoding="utf-8")
        compiled = compile_tex(tex)
        overfull = _overfull(compiled.get("log"))
        passes.append({"gap_cm": gap, "overfull": len(overfull)})
        if not overfull:
            break
    if overfull:
        raise Refusal("TEX_OVERFULL",
                      f"{len(overfull)} overfull box(es) in the picture after widening the boxes; "
                      "shorten the label TeX names (Corrector): " + " | ".join(overfull[:5]),
                      tex=str(tex), log=compiled.get("log"), fit=passes)
    raster = rasterize(Path(compiled["pdf"]))
    record = run_audit(spec_path, spec)
    return {"ok": True, "kind": spec["kind"], "spec": str(spec_path), "tex": str(tex),
            "pdf": compiled["pdf"], "png": raster["png"], "engine": compiled["engine"],
            "rasterizer": raster["rasterizer"], "log": compiled.get("log"), "fit": passes,
            "audit": _audit_summary(record, audit_path(product, spec["kind"]))}


def cmd_audit(args) -> dict:
    """Re-run the mechanical audit on the diagram drawn now. A failing audit
    is a finding, not a refused call: it exits 0 with `verdict: fail`."""
    spec_path, spec = _read_spec(args.spec)
    record = run_audit(spec_path, spec)
    summary = _audit_summary(record, audit_path(_product_of(spec_path), spec["kind"]))
    return {"ok": True, "kind": spec["kind"], **summary, "report": record["report"]}


def _svg_audit():
    """`_core/figure/svg_audit` (100% stdlib, spec S1 of
    odd/tasks/spark-to-paper-enhancements.md), loaded on demand."""
    core = FORGE_ROOT / "skills" / "_core" / "figure"
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))
    import svg_audit  # noqa: E402  (resolved above)

    return svg_audit


def cmd_audit_svg(args) -> dict:
    """Audit a standalone SVG the same way `audit` audits a drawn diagram:
    a failing audit is a finding, not a refused call; it exits 0 with
    `verdict: fail`."""
    svg = Path(args.svg)
    if not svg.is_file():
        raise Refusal("SVG_ABSENT", f"no such file: {svg}")
    report = _svg_audit().audit_svg(svg)
    return {"ok": True, "svg": str(svg), "verdict": report["verdict"],
            "failures": report["failures"],
            "messages": _svg_audit().failure_messages(report),
            "report": report}


def audit_state(product: Path, kind: str) -> dict:
    """The audit of the PNG drawn now: `verdict` is `pass`, `fail` or
    `unmeasured` from `diagrams/<kind>.audit.json`, `absent` without a
    record, or `stale` when the record audited another drawing."""
    path = audit_path(product, kind)
    png = product / "diagrams" / f"{kind}.png"
    empty = {"failures": [], "messages": [], "path": str(path)}
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"verdict": "absent", **empty}
    if not isinstance(record, dict) or record.get("kind") != kind:
        return {"verdict": "absent", **empty}
    current = _sha256(png) if png.is_file() and not png.is_symlink() else None
    verdict = record.get("verdict") if current and record.get("png_sha256") == current else "stale"
    return {"verdict": verdict, "failures": record.get("failures", []),
            "messages": record.get("messages", []), "path": str(path)}


def cmd_status(args) -> dict:
    product = resolve_product(args.target, args.name)
    kinds = {}
    for kind in KINDS:
        paths = diagram_paths(product, kind)
        entry = {"approved": (product / MARKERS[kind]).is_file(), "marker": MARKERS[kind],
                 "validation": validation_state(product, kind),
                 "provenance": validation_provenance(product, kind),
                 "audit": audit_state(product, kind)["verdict"]}
        for ext, key in (("json", "spec"), ("tex", "tex"), ("pdf", "pdf"), ("png", "png")):
            entry[key] = paths[ext].is_file()
        entry["paths"] = {key: str(paths[ext]) for ext, key in
                          (("json", "spec"), ("tex", "tex"), ("pdf", "pdf"), ("png", "png"))}
        kinds[kind] = entry
    return {"ok": True, "product": str(product), "kinds": kinds}


def cmd_validate(args) -> dict:
    """The operator approved this diagram in the conversation: record it.

    Run only after the operator explicitly approved this kind's diagram in the
    current conversation, with their words verbatim and the hash of the PNG
    the agent showed them. Every refusal writes nothing."""
    product = resolve_product(args.target, args.name)
    paths = diagram_paths(product, args.kind)
    if not (product / MARKERS[args.kind]).is_file():
        raise Refusal("APPROVAL_ABSENT",
                      f"{MARKERS[args.kind]} is missing in {product}; there is no approved "
                      f"{args.kind} diagram to validate")
    statement = args.operator_statement
    if not statement.strip():
        raise Refusal("STATEMENT_EMPTY",
                      "--operator-statement must carry the operator's own words, verbatim")
    wanted = args.png_sha256.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{%d,64}" % MIN_HASH_PREFIX, wanted):
        raise Refusal("PNG_HASH_INVALID",
                      f"--png-sha256 must be the PNG's SHA-256 in hex, or a prefix of at least "
                      f"{MIN_HASH_PREFIX} hex characters")
    if paths["json"].is_symlink() or not paths["json"].is_file():
        raise Refusal("SPEC_ABSENT", f"diagrams/{paths['json'].name} does not exist; draw the "
                      "diagram first (derive, render)")
    if paths["png"].is_symlink() or not paths["png"].is_file():
        raise Refusal("DIAGRAM_ABSENT", f"diagrams/{paths['png'].name} has not been drawn yet")
    actual = _sha256(paths["png"])
    if not actual.startswith(wanted):
        raise Refusal("PNG_HASH_MISMATCH",
                      f"diagrams/{paths['png'].name} is not the image the operator approved; "
                      "show the operator the current PNG and ask again")
    audit = audit_state(product, args.kind)
    override = (args.audit_override or "").strip()
    if args.audit_override is not None and not override:
        raise Refusal("STATEMENT_EMPTY",
                      "--audit-override must carry the operator's own words, verbatim")
    if audit["verdict"] != "pass" and not override:
        raise Refusal("AUDIT_NOT_PASSED",
                      f"the mechanical audit of diagrams/{paths['png'].name} reads {audit['verdict']!r}"
                      + (": " + "; ".join(audit["messages"][:6]) if audit["messages"] else "")
                      + "; fix the spec and render again (or run `audit`), or pass --audit-override "
                        "with the operator's explicit words accepting it as it is", audit=audit)
    record = write_validation(product, args.kind, via="chat", statement=statement,
                              audit_override=override or None)
    if record["png_sha256"] != actual:  # drawn again between the check and the write
        validation_path(product, args.kind).unlink(missing_ok=True)
        raise Refusal("PNG_HASH_MISMATCH",
                      f"diagrams/{paths['png'].name} changed while it was being validated")
    return {"ok": True, "kind": args.kind, "validation": "validated", "audit": audit,
            "record": record, "path": str(validation_path(product, args.kind))}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # one JSON object on stdout, even for usage errors
        raise Refusal("USAGE", message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="diagram_cli.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    derive = sub.add_parser("derive", help="draft a spec from the product's approved evidence")
    derive.add_argument("--target", required=True)
    derive.add_argument("--name", required=True)
    derive.add_argument("--kind", required=True, choices=KINDS)
    derive.add_argument("--force", action="store_true", help="draft again over an existing spec")
    render = sub.add_parser("render", help="validate a spec, write .tex, compile .pdf (refusing any "
                                           "overfull box), rasterize .png, audit it")
    render.add_argument("--spec", required=True)
    audit = sub.add_parser("audit", help="re-run the mechanical audit on the drawn diagram and "
                                         "write diagrams/<kind>.audit.json")
    audit.add_argument("--spec", required=True)
    audit_svg = sub.add_parser("audit-svg", help="run the stdlib SVG audit (typography hierarchy, "
                                                 "text collisions, contrast, viewbox fit) on a "
                                                 "standalone SVG and print the report")
    audit_svg.add_argument("--svg", required=True)
    status = sub.add_parser("status", help="which diagrams and approvals exist for a product")
    status.add_argument("--target", required=True)
    status.add_argument("--name", required=True)
    validate = sub.add_parser(
        "validate",
        help="record the operator's approval of a drawn diagram given in the agent chat "
             "(only after the operator explicitly approved it; never on the agent's own initiative)")
    validate.add_argument("--target", required=True)
    validate.add_argument("--name", required=True)
    validate.add_argument("--kind", required=True, choices=KINDS)
    validate.add_argument("--png-sha256", required=True,
                          help=f"SHA-256 of the PNG the operator saw: full hex or a prefix of at "
                               f"least {MIN_HASH_PREFIX} characters")
    validate.add_argument("--operator-statement", required=True,
                          help="the operator's approval, verbatim")
    validate.add_argument("--audit-override", default=None,
                          help="only when the mechanical audit does not read pass: the operator's "
                               "explicit words accepting the diagram as it is, verbatim")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = {"derive": cmd_derive, "render": cmd_render, "audit": cmd_audit,
                  "audit-svg": cmd_audit_svg,
                  "status": cmd_status, "validate": cmd_validate}[args.command](args)
    except Refusal as refusal:
        print(json.dumps({"ok": False, "error": refusal.code, "message": refusal.message, **refusal.extra},
                         ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
