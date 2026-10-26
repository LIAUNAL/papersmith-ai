#!/usr/bin/env python3
"""diagram_cli: the deterministic half of `experiment-diagrams`.

Three subcommands, each printing exactly one JSON object on stdout:

    derive --target <repo> --name <Name> --kind poc|experiments
    render --spec <path/to/diagrams/<kind>.json>
    status --target <repo> --name <Name>

`--target` is the cloned repository under `implementations/<repo>/` (a path,
or the bare `<repo>` name resolved under the forge's own `implementations/`);
the product folder is `<target>/<Name>/`, the same convention the shared
implementation engine uses. Every file this script writes lands inside
`<target>/<Name>/diagrams/`.

A refusal prints `{"ok": false, "error": <CODE>, "message": ...}` and exits
non-zero. Codes: `APPROVAL_ABSENT`, `PRODUCT_ABSENT`, `SPEC_INVALID`,
`TEX_TOOLCHAIN_ABSENT`, `TEX_COMPILE_FAILED`, `RASTER_TOOLCHAIN_ABSENT`.

Standard library only. TeX runs with shell escape disabled; every process is
spawned from an argument list, never a shell string.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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

#: Where a TeX distribution usually lives when it is not on PATH: macOS
#: (MacTeX), Linux and WSL (distribution packages, a TeX Live install).
TEX_FALLBACK_DIRS: tuple[str, ...] = (
    "/Library/TeX/texbin",
    "/usr/local/texlive/*/bin/*",
    "~/texlive/*/bin/*",
    "/usr/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
)
RASTER_FALLBACK_DIRS: tuple[str, ...] = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
)
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
    return errors


# -- TeX ------------------------------------------------------------------------

#: papersmith's own figure library. Written from Sivia's design rules
#: (github.com/exsinger-hub/Sivia), not copied from it.
TIKZ_LIBRARY = r"""
\definecolor{psCanvas}{HTML}{F7F3E8}
\definecolor{psInk}{HTML}{20252B}
\definecolor{psCool}{HTML}{4F7CAC}
\definecolor{psWarm}{HTML}{E09F3E}
\definecolor{psAlert}{HTML}{D96855}
\tikzset{
  ps base/.style={align=center, text=psInk, font=\small, inner sep=5pt},
  ps operator/.style={ps base, rectangle, rounded corners=3pt, draw=psCool,
    fill=psCool!14, line width=1.5pt, text width=2.6cm, minimum height=1.25cm},
  ps state/.style={ps base, rounded rectangle, draw=psInk!60, fill=psInk!7,
    line width=1.3pt, text width=2.2cm, minimum height=0.8cm},
  ps focal/.style={ps base, ellipse, draw=psAlert, fill=psWarm!32,
    line width=1.8pt, text width=2.6cm, minimum width=3.4cm, minimum height=2.1cm,
    inner sep=1pt, font=\small\bfseries},
  ps evidence/.style={ps base, rectangle, draw=psInk!45, fill=white,
    line width=1.3pt, text width=2.6cm, minimum height=1.0cm, font=\footnotesize},
  ps context/.style={ps base, font=\footnotesize, text=psInk!75, text width=5.2cm,
    align=left, inner sep=2pt},
  ps group/.style={rectangle, rounded corners=6pt, fill=psCool!7, draw=psCool!30,
    line width=0.8pt, inner sep=10pt},
  ps claim/.style={font=\large\bfseries, text=psInk, align=left, inner sep=0pt},
  ps primary/.style={draw=psInk, line width=1.9pt, -{Stealth[length=3.4mm, width=2.8mm]}},
  ps secondary/.style={draw=psInk!50, line width=1.4pt, -{Stealth[length=2.6mm, width=2.2mm]}},
  ps data/.style={},
  ps supervision/.style={dash pattern=on 5pt off 3pt},
  ps feedback/.style={bend left=40},
  ps inhibition/.style={-{Bar[width=3.4mm]}},
  ps edge label/.style={font=\footnotesize, text=psInk!80, fill=psCanvas, inner sep=1.5pt},
}
""".strip("\n")

_SPECIALS = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
             "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
             # OT1 has no glyphs for these: as text they print as ¡ ¿ and a dash.
             "<": r"\ensuremath{<}", ">": r"\ensuremath{>}", "|": r"\ensuremath{|}"}


def tex_escape(text: str) -> str:
    return "".join(_SPECIALS.get(ch, ch) for ch in text)


SPINE_STEP = 4.0
EVIDENCE_Y = -3.2
CONTEXT_Y = 2.1


def layout(spec: dict) -> dict[str, tuple[float, float]]:
    """Coordinates in cm: the spine left to right at y=0, evidence below,
    context above."""
    nodes = [n for n in spec["nodes"] if n["role"] != "group"]
    spine = [n for n in nodes if n.get("row", "spine") == "spine"]
    pos = {n["id"]: (i * SPINE_STEP, 0.0) for i, n in enumerate(spine)}
    span = (len(spine) - 1) * SPINE_STEP
    sources = {e["to"]: e["from"] for e in spec["edges"]}
    for row, y in (("evidence", EVIDENCE_Y), ("context", CONTEXT_Y)):
        members = [n for n in nodes if n.get("row") == row]
        anchored = {n["id"]: pos[n.get("under") or n.get("near")][0] for n in members
                    if (n.get("under") or n.get("near")) in pos}
        free = [n for n in members if n["id"] not in anchored]
        if len(free) == 1 and sources.get(free[0]["id"]) in pos:
            anchored[free[0]["id"]] = pos[sources[free[0]["id"]]][0]
            free = []
        if free:
            gap = max(span / max(len(free) - 1, 1), 3.2) if len(free) > 1 else 0.0
            start = span / 2 - gap * (len(free) - 1) / 2
            for i, node in enumerate(free):
                anchored[node["id"]] = start + i * gap
        for node_id, x in anchored.items():
            pos[node_id] = (x, y)
    return pos


def _anchors(a: tuple[float, float], b: tuple[float, float]) -> tuple[str, str]:
    if abs(a[1] - b[1]) < 1e-6:
        return ("east", "west") if b[0] > a[0] else ("west", "east")
    return ("south", "north") if b[1] < a[1] else ("north", "south")


def build_tex(spec: dict) -> str:
    pos = layout(spec)
    lines = [
        r"\documentclass[border=0pt]{standalone}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{arrows.meta,shapes.misc,shapes.geometric,positioning,fit,backgrounds,calc}",
        r"\renewcommand{\familydefault}{\sfdefault}",
        r"\hyphenpenalty=10000 \exhyphenpenalty=10000",
        TIKZ_LIBRARY,
        r"\begin{document}",
        r"\begin{tikzpicture}[show background rectangle, inner frame sep=14pt,",
        r"  background rectangle/.style={fill=psCanvas, draw=none}]",
        f"% figure claim: {tex_escape(spec['claim'])}",
    ]
    ys = [y for _, y in pos.values()]
    top = max(ys) + (1.2 if max(ys) > 0 else 2.2)
    xs = [x for x, _ in pos.values()]
    width = max(max(xs) - min(xs) + 3.0, 9.0)
    lines.append(f"\\node[ps claim, anchor=south west, text width={width:.1f}cm] "
                 f"at ({min(xs) - 1.5:.2f},{top:.2f}) {{{tex_escape(spec['claim'])}}};")
    for node in spec["nodes"]:
        if node["role"] == "group":
            continue
        x, y = pos[node["id"]]
        lines.append(f"\\node[ps {node['role']}] ({node['id']}) at ({x:.2f},{y:.2f}) "
                     f"{{{tex_escape(node['label'])}}};")
    for node in spec["nodes"]:
        if node["role"] == "group":
            fit = "".join(f"({m})" for m in node["members"])
            lines.append(r"\begin{scope}[on background layer]")
            lines.append(f"\\node[ps group, fit={fit}] ({node['id']}) {{}};")
            lines.append(f"\\node[ps context, anchor=south west, text width=3cm] at ({node['id']}.north west) "
                         f"{{{tex_escape(node['label'])}}};")
            lines.append(r"\end{scope}")
    for edge in spec["edges"]:
        a, b = pos[edge["from"]], pos[edge["to"]]
        styles = [f"ps {edge['prominence']}", f"ps {edge['semantics']}"]
        if edge["semantics"] == "feedback":
            start, end = ("south", "south") if abs(a[1] - b[1]) < 1e-6 else _anchors(a, b)
            path = f"({edge['from']}.{start}) to"
        else:
            start, end = _anchors(a, b)
            path = f"({edge['from']}.{start}) --"
            if start in ("south", "north") and abs(a[0] - b[0]) > 1e-6:
                # Orthogonal: leave vertically, run along a shared lane
                # halfway between the rows, enter the target from its facing side.
                lane_y = a[1] + (b[1] - a[1]) * 0.6   # one lane per row pair, shared by every edge
                path = f"({edge['from']}.{start}) -- ({edge['from']}.{start} |- 0,{lane_y:.2f}) -|"
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
        for directory in sorted(glob.glob(os.path.expanduser(pattern))):
            candidate = Path(directory) / name
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
    for ext in (".aux", ".log", ".fls", ".fdb_latexmk"):
        tex.with_suffix(ext).unlink(missing_ok=True)
    return {"engine": name, "pdf": str(pdf)}


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


def cmd_render(args) -> dict:
    spec_path = Path(args.spec).expanduser().resolve()
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Refusal("SPEC_INVALID", f"spec: no file at {spec_path}")
    except (OSError, ValueError) as exc:
        raise Refusal("SPEC_INVALID", f"spec: not readable JSON ({exc})")
    problems = validate_spec(spec)
    if problems:
        raise Refusal("SPEC_INVALID", "; ".join(problems))
    tex = spec_path.with_name(f"{spec['kind']}.tex")
    tex.write_text(build_tex(spec), encoding="utf-8")
    for stale in (tex.with_suffix(".pdf"), tex.with_suffix(".png")):
        stale.unlink(missing_ok=True)
    compiled = compile_tex(tex)
    raster = rasterize(Path(compiled["pdf"]))
    return {"ok": True, "kind": spec["kind"], "spec": str(spec_path), "tex": str(tex),
            "pdf": compiled["pdf"], "png": raster["png"], "engine": compiled["engine"],
            "rasterizer": raster["rasterizer"]}


def cmd_status(args) -> dict:
    product = resolve_product(args.target, args.name)
    kinds = {}
    for kind in KINDS:
        paths = diagram_paths(product, kind)
        entry = {"approved": (product / MARKERS[kind]).is_file(), "marker": MARKERS[kind]}
        for ext, key in (("json", "spec"), ("tex", "tex"), ("pdf", "pdf"), ("png", "png")):
            entry[key] = paths[ext].is_file()
        entry["paths"] = {key: str(paths[ext]) for ext, key in
                          (("json", "spec"), ("tex", "tex"), ("pdf", "pdf"), ("png", "png"))}
        kinds[kind] = entry
    return {"ok": True, "product": str(product), "kinds": kinds}


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
    render = sub.add_parser("render", help="validate a spec, write .tex, compile .pdf, rasterize .png")
    render.add_argument("--spec", required=True)
    status = sub.add_parser("status", help="which diagrams and approvals exist for a product")
    status.add_argument("--target", required=True)
    status.add_argument("--name", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = {"derive": cmd_derive, "render": cmd_render, "status": cmd_status}[args.command](args)
    except Refusal as refusal:
        print(json.dumps({"ok": False, "error": refusal.code, "message": refusal.message, **refusal.extra},
                         ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
