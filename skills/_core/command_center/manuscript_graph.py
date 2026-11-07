"""The manuscript summary graph: the paper's argument as typed nodes and edges.

Read-only over the workspace except for its own output,
``.papersmith/manuscript_graph.json``. Every node comes from an artifact a
phase already wrote; a source that does not exist yet becomes one ``missing``
node naming the reason and the phase that fills it. Nothing is invented: no
text is generated, and an edge is drawn only from an explicit reference.

Node types and sources (first present source wins):

``topic``           ``papersmith.yaml`` ``topic`` (else ``title``), else the
                    latest proposal sky's ``sun``; ``topic_app``/``topic_ai``
                    planets as detail.
``problem``         fact ``problem-statement`` (declarations region of
                    ``paper/main.tex``), else the sky's ``problem`` planet.
``pillar``          the sky's ``pillars`` (checked by
                    ``merge_proposal_sky.pillars_and_hypotheses``), else
                    ``.papersmith/model_spec.json`` ``novelty.pillars``.
``hypothesis``      the sky's ``hypotheses``; each protocol experiment no sky
                    hypothesis names brings its own ``Hypothesis`` bullet.
``sota``            ``atlas_manuscript.cited_systems``: cited atlas systems
                    and cited papers outside the pool.
``base_concept``    displayed equations of
                    ``materials-and-methods.mm-borrowed-machinery``.
``novelty_concept`` displayed equations of ``materials-and-methods.mm-proposal``
                    (else the latest proposal's ``$$ … \\tag{N} $$`` blocks), plus
                    the declared contributions (``couplings.json``
                    ``facts.contributions``, else fact ``contributions``).
``experiment``      the latest protocol's ``## Experiment [exp:<id>]``
                    entries, else fact ``experimental-design``.
``finding``         every product's ``Results/discussion.json`` hypothesis
                    (full stage over proof of concept) and its novelty verdict.
``conclusion``      the first sentence of each ``conclusions.concl-block-*``,
                    else the latest discussion ``summary``.

Edges (``rel``): topic→problem ``frames``; problem→pillar
``decomposes_into``; pillar→hypothesis ``predicts``; sota→pillar (the pillar's
contribution planet is linked to that system in the sky) or
sota→novelty_concept (a contribution planet with that name), carrying the
sky link's own ``rel`` (``extends``, ``contradicts``, ``supports``…); a cited
system with no sky link reaches the novelty concepts of the blocks that cite
it as ``cited_by``; base_concept→novelty_concept ``builds_on`` (the proposal
references the borrowed equation's ``\\label``); novelty_concept→hypothesis
``tested_by`` (the statement names the concept); hypothesis→experiment
``tested_in``; experiment→finding ``yields`` (with the finding's outcome);
finding→conclusion ``summarized_in`` (the conclusion names the hypothesis id
or one of the observed numbers).

Public functions: ``build_graph(root)``, ``write_graph(root)``,
``refresh(root)`` (the trigger next to ``atlas_manuscript.refresh``; ``None``
outside a workspace, never raises), ``read_graph(root)`` and
``render_html(graph, lang)``. Run standalone from a workspace root::

    python -m skills._core.command_center.manuscript_graph [--root .] [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import atlas_manuscript, experiments_view, math_view

SCHEMA = "papersmith.manuscript-graph/v1"
GRAPH_REL = ".papersmith/manuscript_graph.json"
TEXT_MAX = 600
MAX_BYTES = 8 * 1024 * 1024

NODE_TYPES = ("topic", "problem", "pillar", "hypothesis", "sota", "base_concept",
              "novelty_concept", "experiment", "finding", "conclusion")
BASE_BLOCK = "materials-and-methods.mm-borrowed-machinery"
NOVELTY_BLOCK = "materials-and-methods.mm-proposal"
CONCLUSION_PREFIX = "conclusions.concl-block-"

#: Which phase fills each node type when its source is missing.
PHASES = {
    "topic": "smith init (papersmith.yaml topic) or proposal-deliberation (sky sun)",
    "problem": "paper-writing (mark fact problem-statement) or proposal-deliberation (sky problem)",
    "pillar": "proposal-deliberation (pillars in the revision's .sky.json)",
    "hypothesis": "proposal-deliberation (sky hypotheses) or experimental-deliberation (protocol)",
    "sota": "paper-writing (citations in paper/main.tex) over the plausibility atlas",
    "base_concept": f"paper-writing ({BASE_BLOCK})",
    "novelty_concept": f"paper-writing ({NOVELTY_BLOCK}) or proposal-deliberation (equations)",
    "experiment": "experimental-deliberation (experiments/experiments-*-vNN.md)",
    "finding": "proposal-implementation / experimental-implementation (Results/discussion.json)",
    "conclusion": "paper-writing (conclusions.concl-block-*)",
}
#: Discussion verdicts folded to the graph's three outcomes.
OUTCOMES = {"supported": "supported", "partially_supported": "supported",
            "justified": "supported", "partially_justified": "supported",
            "not_supported": "refuted", "not_justified": "refuted"}

_HERE = Path(__file__).resolve()
_PAPER_SCRIPTS = _HERE.parents[2] / "paper-writing" / "scripts"
_IMPLEMENTATION = _HERE.parents[1] / "implementation"
_MERGER = _HERE.parents[2] / "proposal-deliberation" / "scripts" / "merge_proposal_sky.py"

_EQUATION = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray|displaymath)(\*?)\}(.*?)\\end\{\1\2\}"
    r"|\\\[(.*?)\\\]", re.S)
_LABEL = re.compile(r"\\label\{([^{}]+)\}")
_REF = re.compile(r"\\(?:eq|c|C|auto)?ref\{([^{}]+)\}")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_CITE = re.compile(r"\\[A-Za-z]*cite[a-z]*\*?(?:\[[^\]]*\])*\{[^{}]*\}")


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _clip(value: Any, limit: int = TEXT_MAX) -> str:
    return " ".join(str(value or "").split())[:limit]


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.name


def _read_bytes(path: Path) -> bytes | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        return path.read_bytes()
    except OSError:
        return None


def _read_json(path: Path) -> Any:
    data = _read_bytes(path)
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def _node(kind: str, key: str, label: str, *, detail: str = "", path: str = "", locator: str = "",
          blocks: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return {"id": f"{kind}:{key}" if key else kind, "type": kind, "label": _clip(label),
            "detail": _clip(detail, 2000), "source": {"path": path, "locator": locator},
            "paper_blocks": list(blocks or []), "status": {"state": "present"}, **extra}


def _missing(kind: str, reason: str) -> dict[str, Any]:
    return {"id": f"{kind}:missing", "type": kind, "label": "", "detail": "",
            "source": {"path": "", "locator": ""}, "paper_blocks": [],
            "status": {"state": "missing", "reason": reason, "phase": PHASES[kind]}}


def _norm_exp(value: Any) -> str:
    text = str(value or "").strip()
    return text[4:].strip() if text.lower().startswith("exp:") else text


def _paper_modules():
    for path in (_PAPER_SCRIPTS, _IMPLEMENTATION):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import paper_block  # noqa: PLC0415
    import paper_declarations  # noqa: PLC0415
    return paper_block, paper_declarations


def _merger():
    name = "papersmith_merge_proposal_sky"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, _MERGER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    return sys.modules[name]


# --------------------------------------------------------------------------
# sources
# --------------------------------------------------------------------------
class _Sources:
    """Every input, read once; ``files`` is what ``generated_from`` digests."""

    def __init__(self, root: Path, paper_dir: Path) -> None:
        self.root, self.paper = root, paper_dir
        self.files: list[Path] = [root / "papersmith.yaml", root / ".papersmith" / "model_spec.json",
                                  paper_dir / "main.tex", paper_dir / "refs.bib",
                                  paper_dir / "couplings.json",
                                  root / "sota-pool" / "atlas.json",
                                  root / "sota-pool" / "candidates.json"]
        self.proposal = math_view._latest_proposal(root)
        self.sky_path = self.proposal.with_suffix(".sky.json") if self.proposal else None
        self.sky = _read_json(self.sky_path) if self.sky_path else None
        if self.proposal:
            self.files += [self.proposal, self.sky_path]
        self.warnings: list[str] = []
        reader = experiments_view._Reader(root, self.warnings)
        self.protocol = experiments_view._parse_protocol(root, reader)
        protocol_path = experiments_view._latest_protocol(root)
        if protocol_path:
            self.files.append(protocol_path)
        self.products = experiments_view._product_dirs(root, reader)
        self.files += [folder / "Results" / "discussion.json" for _repo, folder in self.products]
        self.blocks, self.blocks_problem = self._blocks()
        #: ``(path, text)`` of the latest discussion summary, set by ``_findings``.
        self.summary: tuple[str, str] | None = None

    def _blocks(self) -> tuple[dict[str, str], str]:
        data = _read_bytes(self.paper / "main.tex")
        if data is None:
            return {}, "paper/main.tex does not exist yet"
        paper_block, _ = _paper_modules()
        try:
            parsed = paper_block.parse(data)
        except Exception as exc:  # noqa: BLE001 - a malformed paper degrades, never raises
            return {}, f"paper/main.tex blocks unreadable: {getattr(exc, 'code', type(exc).__name__)}"
        bodies = {}
        for block_id in parsed.order:
            begin, end = parsed.pairs[block_id]
            bodies[block_id] = data[begin["end"]:end["start"]].decode("utf-8", errors="replace")
        return bodies, ""

    def fact(self, fact_id: str) -> str | None:
        if not (self.paper / "main.tex").is_file():
            return None
        _, paper_declarations = _paper_modules()
        try:
            value = paper_declarations.read_fact(self.paper, fact_id)
        except Exception:  # noqa: BLE001 - a hand-edited region reads as absent
            return None
        return value if isinstance(value, str) and value.strip() else None

    def planets(self, slot: str) -> list[dict]:
        system = self.sky.get("system") if isinstance(self.sky, dict) else None
        planets = system.get("planets") if isinstance(system, dict) else None
        return [p for p in planets or [] if isinstance(p, dict) and p.get("slot") == slot
                and isinstance(p.get("label"), str)]

    def sky_rel(self) -> str:
        return _rel(self.root, self.sky_path) if self.sky_path else ""

    def digests(self) -> dict[str, str]:
        out = {}
        for path in sorted(set(self.files), key=str):
            data = _read_bytes(path)
            if data is not None:
                out[_rel(self.root, path)] = hashlib.sha256(data).hexdigest()
        evidence = atlas_manuscript._evidence_digest(self.paper)
        if evidence:
            out["paper/.paper-writing/evidence"] = evidence
        return out


def _equations(body: str) -> list[dict[str, Any]]:
    """Each displayed equation with its label and the references in the prose
    leading up to it (since the previous equation)."""
    found, cursor = [], 0
    for match in _EQUATION.finditer(body):
        latex = (match.group(3) if match.group(3) is not None else match.group(4)) or ""
        labels = _LABEL.findall(latex)
        lead = body[cursor:match.start()] + latex
        cursor = match.end()
        clean = _LABEL.sub("", latex).strip()
        if clean:
            found.append({"label": labels[0].strip() if labels else "", "latex": clean,
                          "refs": [r.strip() for group in _REF.findall(lead) for r in group.split(",")]})
    return found


def _prose(body: str) -> str:
    """A block's LaTeX as one line of prose: comments and citations dropped."""
    lines = [re.sub(r"(?<!\\)%.*$", "", line) for line in body.splitlines()]
    return " ".join(_CITE.sub("", " ".join(lines)).replace("~", " ").split())


# --------------------------------------------------------------------------
# the graph
# --------------------------------------------------------------------------
def _topic(src: _Sources) -> dict[str, Any]:
    details = [p["label"] for slot in ("topic_app", "topic_ai") for p in src.planets(slot)]
    detail = "; ".join(details)
    for key in ("topic", "title"):
        value = math_view._yaml_field(src.root, key)
        if value:
            return _node("topic", "", value, detail=detail, path="papersmith.yaml", locator=key)
    sun = src.planets("sun")
    if sun:
        return _node("topic", "", sun[0]["label"], detail=detail, path=src.sky_rel(),
                     locator=f"planet {sun[0].get('id')} (slot sun)")
    return _missing("topic", "no topic in papersmith.yaml and no proposal sky")


def _problem(src: _Sources) -> dict[str, Any]:
    stated = src.fact("problem-statement")
    if stated:
        return _node("problem", "", stated, detail=stated, path=_rel(src.root, src.paper / "main.tex"),
                     locator="declarations: fact problem-statement")
    planets = src.planets("problem")
    if planets:
        planet = planets[0]
        return _node("problem", "", planet["label"], detail=str(planet.get("detail") or ""),
                     path=src.sky_rel(), locator=f"planet {planet.get('id')} (slot problem)")
    return _missing("problem", "fact problem-statement not declared and no sky problem planet")


def _pillars(src: _Sources) -> tuple[list[dict], list[dict], str]:
    """(pillar nodes, sky hypotheses, refusal)."""
    refusal = ""
    if isinstance(src.sky, dict):
        found, refusal = _merger().pillars_and_hypotheses(src.sky)
        if found and found["pillars"]:
            nodes = [_node("pillar", p["id"], p["label"], detail=p.get("detail", ""),
                           path=src.sky_rel(), locator=f"pillars[{i}]",
                           contribution=p.get("contribution", ""))
                     for i, p in enumerate(found["pillars"])]
            return nodes, found["hypotheses"], ""
    spec = _read_json(src.root / ".papersmith" / "model_spec.json")
    novelty = spec.get("novelty") if isinstance(spec, dict) else None
    pillars = novelty.get("pillars") if isinstance(novelty, dict) else None
    named = [p for p in pillars or [] if isinstance(p, dict) and str(p.get("name") or "").strip()]
    if named:
        nodes = [_node("pillar", f"spec-{i + 1}", p["name"], detail=str(p.get("summary") or ""),
                       path=".papersmith/model_spec.json", locator=f"novelty.pillars[{i}]")
                 for i, p in enumerate(named)]
        return nodes, [], ""
    reason = (f"the proposal sky's pillars are refused: {refusal}" if refusal else
              "no pillars in the latest proposal sky nor in .papersmith/model_spec.json")
    return [_missing("pillar", reason)], [], refusal or ""


def _hypotheses_and_experiments(src: _Sources, sky_hypotheses: list[dict]):
    hyp_nodes: list[dict] = []
    exp_nodes: list[dict] = []
    edges: list[dict] = []
    protocol = src.protocol or {}
    experiments = protocol.get("experiments") or []
    named: set[str] = set()
    for i, hyp in enumerate(sky_hypotheses):
        node = _node("hypothesis", hyp["id"], hyp["statement"], detail=hyp["statement"],
                     path=src.sky_rel(), locator=f"hypotheses[{i}]", pillar=hyp["pillar"])
        hyp_nodes.append(node)
        edges.append({"from": f"pillar:{hyp['pillar']}", "to": node["id"], "rel": "predicts"})
        for exp in hyp.get("experiments", []):
            named.add(_norm_exp(exp))
            edges.append({"from": node["id"], "to": f"experiment:{_norm_exp(exp)}", "rel": "tested_in"})
    for exp in experiments:
        exp_id = _norm_exp(exp.get("id"))
        detail = "; ".join(x for x in (exp.get("hypothesis") and f"Hypothesis: {exp['hypothesis']}",
                                        exp.get("success_criterion")
                                        and f"Success criterion: {exp['success_criterion']}") if x)
        exp_nodes.append(_node("experiment", exp_id, exp.get("title") or exp_id, detail=detail,
                               path=protocol.get("file", ""), locator=f"[exp:{exp_id}]"))
        if exp_id not in named and exp.get("hypothesis"):
            node = _node("hypothesis", f"exp-{exp_id}", exp["hypothesis"], detail=exp["hypothesis"],
                         path=protocol.get("file", ""), locator=f"[exp:{exp_id}] Hypothesis")
            hyp_nodes.append(node)
            edges.append({"from": node["id"], "to": f"experiment:{exp_id}", "rel": "tested_in"})
    if not exp_nodes:
        design = src.fact("experimental-design")
        if design:
            exp_nodes.append(_node("experiment", "design", design, detail=design,
                                   path=_rel(src.root, src.paper / "main.tex"),
                                   locator="declarations: fact experimental-design"))
    if not hyp_nodes:
        hyp_nodes.append(_missing("hypothesis", "no hypotheses in the proposal sky nor in the "
                                                "experiments protocol"))
    if not exp_nodes:
        exp_nodes.append(_missing("experiment", "no experiments protocol and no fact "
                                                "experimental-design"))
    return hyp_nodes, exp_nodes, edges


def _concepts(src: _Sources) -> tuple[list[dict], list[dict], list[dict]]:
    base, novelty, edges = [], [], []
    main_rel = _rel(src.root, src.paper / "main.tex")
    base_labels: dict[str, str] = {}
    for i, eq in enumerate(_equations(src.blocks.get(BASE_BLOCK, ""))):
        key = eq["label"] or f"base-{i + 1}"
        node = _node("base_concept", key, eq["label"] or f"Equation {i + 1}", detail=eq["latex"],
                     path=main_rel, locator=f"{BASE_BLOCK} equation {i + 1}",
                     blocks=[BASE_BLOCK], concept_kind="equation")
        base.append(node)
        if eq["label"]:
            base_labels[eq["label"]] = node["id"]
    for i, eq in enumerate(_equations(src.blocks.get(NOVELTY_BLOCK, ""))):
        key = eq["label"] or f"novelty-{i + 1}"
        node = _node("novelty_concept", key, eq["label"] or f"Equation {i + 1}", detail=eq["latex"],
                     path=main_rel, locator=f"{NOVELTY_BLOCK} equation {i + 1}",
                     blocks=[NOVELTY_BLOCK], concept_kind="equation")
        novelty.append(node)
        for ref in eq["refs"]:
            if ref in base_labels:
                edges.append({"from": base_labels[ref], "to": node["id"], "rel": "builds_on"})
    if not novelty and src.proposal is not None:
        text = math_view._read(src.proposal, src.root) or ""
        for eq in math_view.equations_from_markdown(text):
            label = f"({eq['tag']}) {eq['heading']}".strip()
            novelty.append(_node("novelty_concept", f"proposal-{eq['tag']}", label, detail=eq["latex"],
                                 path=_rel(src.root, src.proposal), locator=f"\\tag{{{eq['tag']}}}",
                                 concept_kind="equation"))
    record = _read_json(src.paper / "couplings.json")
    facts = record.get("facts") if isinstance(record, dict) else None
    names = facts.get("contributions") if isinstance(facts, dict) else None
    source = (_rel(src.root, src.paper / "couplings.json"), "facts.contributions")
    if not (isinstance(names, list) and names):
        declared = src.fact("contributions")
        names = [n.strip() for n in re.split(r"[;\n]", declared or "") if n.strip()]
        source = (main_rel, "declarations: fact contributions")
    for name in [n for n in names if isinstance(n, str) and n.strip()]:
        novelty.append(_node("novelty_concept", f"contribution:{name.strip()}", name.strip(),
                             path=source[0], locator=source[1], concept_kind="contribution"))
    if not base:
        base.append(_missing("base_concept", f"no displayed equation in {BASE_BLOCK}"
                             + (f" ({src.blocks_problem})" if src.blocks_problem else "")))
    if not novelty:
        novelty.append(_missing("novelty_concept", f"no displayed equation in {NOVELTY_BLOCK}, no "
                                "proposal equation and no declared contributions"))
    return base, novelty, edges


def _sota(src: _Sources) -> tuple[list[dict], str]:
    try:
        joined = atlas_manuscript.cited_systems(src.root, paper_dir=src.paper)
    except Exception as exc:  # noqa: BLE001 - an unreadable atlas degrades
        return [], f"the citation join failed: {type(exc).__name__}"
    nodes = []
    for system in joined["systems"]:
        if system["cited"]:
            claims = "; ".join(c["claim"] for c in system["claims"])
            nodes.append(_node("sota", system["id"], system["title"] or system["id"], detail=claims,
                               path=atlas_manuscript.LAYER_REL, locator=f"systems[{system['id']}]",
                               blocks=system["blocks"], cite_keys=system["cite_keys"]))
    for paper in joined["extra_systems"]:
        claims = "; ".join(c["claim"] for c in paper["claims"])
        nodes.append(_node("sota", f"cite:{paper['cite_key']}", paper["title"] or paper["cite_key"],
                           detail=claims, path="paper/refs.bib", locator=paper["cite_key"],
                           blocks=paper["blocks"], cite_keys=[paper["cite_key"]], outside_pool=True))
    return nodes, "" if nodes else "the manuscript cites no reference yet"


def _sota_edges(src: _Sources, sota: list[dict], pillars: list[dict], novelty: list[dict]):
    edges, linked = [], set()
    by_contribution = {p.get("contribution"): p["id"] for p in pillars if p.get("contribution")}
    planets = {p.get("id"): p for p in src.planets("contribution") + src.planets("novelty")}
    contributions = {n["label"].lower(): n["id"] for n in novelty if n.get("concept_kind") == "contribution"}
    present = {n["id"] for n in sota}
    links = src.sky.get("links") if isinstance(src.sky, dict) else None
    for link in links if isinstance(links, list) else []:
        if not isinstance(link, dict) or f"sota:{link.get('to_system')}" not in present:
            continue
        source = f"sota:{link['to_system']}"
        target = by_contribution.get(link.get("from"))
        if target is None and link.get("from") in planets:
            target = contributions.get(planets[link["from"]]["label"].lower())
        if target:
            edges.append({"from": source, "to": target, "rel": str(link.get("rel") or "cited_by")})
            linked.add(source)
    for node in sota:
        if node["id"] in linked:
            continue
        for concept in novelty:
            if set(concept["paper_blocks"]) & set(node["paper_blocks"]):
                edges.append({"from": node["id"], "to": concept["id"], "rel": "cited_by"})
    return edges


def _findings(src: _Sources) -> tuple[list[dict], str]:
    discussion = experiments_view.results_discussion()
    chosen: dict[str, tuple[int, dict]] = {}
    summaries: list[tuple[int, str, str]] = []
    for _repo, folder in src.products:
        result = discussion.load_and_check(folder)
        data = result.get("data")
        if not isinstance(data, dict):
            continue
        rank = 1 if (result.get("stage") or data.get("stage")) == "full" else 0
        path = _rel(src.root, folder / discussion.DISCUSSION_FILE)
        for i, hyp in enumerate(h for h in data.get("hypotheses") or [] if isinstance(h, dict)):
            key = str(hyp.get("id") or f"{path}#{i}")
            if key not in chosen or rank > chosen[key][0]:
                chosen[key] = (rank, {**hyp, "_path": path, "_index": i,
                                      "_status": result.get("status")})
        novelty = data.get("novelty")
        if isinstance(novelty, dict) and novelty.get("verdict"):
            if "novelty" not in chosen or rank > chosen["novelty"][0]:
                chosen["novelty"] = (rank, {"statement": novelty.get("claim"), "verdict": novelty["verdict"],
                                            "observed": novelty.get("rationale"), "_path": path,
                                            "_index": "novelty", "_status": result.get("status")})
        if isinstance(data.get("summary"), str) and data["summary"].strip():
            summaries.append((rank, path, data["summary"]))
    nodes = []
    for key, (_rank, hyp) in sorted(chosen.items()):
        verdict = str(hyp.get("verdict") or "pending")
        detail = "; ".join(x for x in (hyp.get("statement"), hyp.get("observed")
                                        and f"Observed: {hyp['observed']}") if x)
        locator = "novelty" if key == "novelty" else f"hypotheses[{hyp['_index']}]"
        nodes.append(_node("finding", key, f"{key}: {verdict}", detail=detail, path=hyp["_path"],
                           locator=locator, verdict=verdict,
                           outcome=OUTCOMES.get(verdict, "inconclusive"),
                           experiment=_norm_exp(hyp.get("experiment")),
                           observed=_clip(hyp.get("observed")), discussion_status=hyp["_status"]))
    src.summary = max(summaries)[1:] if summaries else None
    return nodes, "" if nodes else "no Results/discussion.json with hypotheses yet"


def _conclusions(src: _Sources) -> list[dict]:
    main_rel = _rel(src.root, src.paper / "main.tex")
    nodes = []
    for block_id, body in src.blocks.items():
        if block_id.startswith(CONCLUSION_PREFIX):
            prose = _prose(body)
            if prose:
                nodes.append(_node("conclusion", block_id, math_view._first_sentence(prose),
                                   detail=prose, path=main_rel, locator=block_id, blocks=[block_id]))
    if not nodes and src.summary:
        path, summary = src.summary
        nodes.append(_node("conclusion", "discussion-summary", math_view._first_sentence(summary),
                           detail=summary, path=path, locator="summary", fallback=True))
    return nodes or [_missing("conclusion", "no conclusions.concl-block-* written and no "
                                            "discussion summary" + (f" ({src.blocks_problem})"
                                                                     if src.blocks_problem else ""))]


def _mentions(text: str, finding: dict) -> bool:
    lowered = text.lower()
    key = finding["id"].split(":", 1)[1]
    if key != "novelty" and re.search(rf"(?<![\w.]){re.escape(key.lower())}(?![\w])", lowered):
        return True
    return any(re.search(rf"(?<![\d.]){re.escape(n)}(?![\d])", text)
               for n in _NUMBER.findall(finding.get("observed") or "") if "." in n or len(n) > 1)


def build_graph(root: Path | str, *, paper_dir: Path | str | None = None) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    paper = root / "paper" if paper_dir is None else Path(paper_dir).expanduser().resolve()
    src = _Sources(root, paper)
    topic, problem = _topic(src), _problem(src)
    pillars, sky_hypotheses, _refusal = _pillars(src)
    hypotheses, experiments, edges = _hypotheses_and_experiments(src, sky_hypotheses)
    sota, sota_reason = _sota(src)
    base, novelty, concept_edges = _concepts(src)
    findings, finding_reason = _findings(src)
    conclusions = _conclusions(src)
    edges += concept_edges
    edges.append({"from": topic["id"], "to": problem["id"], "rel": "frames"})
    edges += [{"from": problem["id"], "to": p["id"], "rel": "decomposes_into"} for p in pillars]
    edges += _sota_edges(src, sota, pillars, novelty)
    for concept in novelty:
        name = concept["label"].lower()
        if concept.get("concept_kind") == "contribution" or concept["source"]["path"].endswith("main.tex"):
            for hyp in hypotheses:
                if name and name in hyp["label"].lower():
                    edges.append({"from": concept["id"], "to": hyp["id"], "rel": "tested_by"})
    for finding in findings:
        if finding.get("experiment"):
            edges.append({"from": f"experiment:{finding['experiment']}", "to": finding["id"],
                          "rel": "yields", "verdict": finding["outcome"]})
        for conclusion in conclusions:
            if conclusion["status"]["state"] == "present" and _mentions(conclusion["detail"], finding):
                edges.append({"from": finding["id"], "to": conclusion["id"], "rel": "summarized_in"})
    nodes = [topic, problem, *pillars, *hypotheses,
             *(sota or [_missing("sota", sota_reason)]), *base, *novelty, *experiments,
             *(findings or [_missing("finding", finding_reason)]), *conclusions]
    present = {n["id"] for n in nodes if n["status"]["state"] == "present"}
    unique, seen = [], set()
    for edge in edges:
        key = (edge["from"], edge["to"], edge["rel"])
        if edge["from"] in present and edge["to"] in present and key not in seen:
            seen.add(key)
            unique.append(edge)
    missing = [kind for kind in NODE_TYPES
               if not any(n["type"] == kind and n["status"]["state"] == "present" for n in nodes)]
    counts = {kind: sum(1 for n in nodes if n["type"] == kind and n["status"]["state"] == "present")
              for kind in NODE_TYPES}
    return {"schema": SCHEMA, "generated_from": src.digests(),
            "summary": {"counts": counts, "missing": missing, "edges": len(unique)},
            "nodes": nodes, "edges": unique}


# --------------------------------------------------------------------------
# disk
# --------------------------------------------------------------------------
def write_graph(root: Path | str, *, paper_dir: Path | str | None = None) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    graph = build_graph(root, paper_dir=paper_dir)
    target = root / GRAPH_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.resolve().relative_to(root)  # ValueError when .papersmith escapes the workspace
    text = json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".manuscript_graph.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return {"ok": True, "status": "written", "path": GRAPH_REL, "summary": graph["summary"]}


def refresh(root: Path | str, *, paper_dir: Path | str | None = None) -> dict[str, Any] | None:
    """Rebuild after a manuscript event; ``None`` outside a workspace
    (no ``papersmith.yaml``). Never raises."""
    try:
        root = Path(root).expanduser().resolve()
        if not (root / "papersmith.yaml").is_file():
            return None
        return write_graph(root, paper_dir=paper_dir)
    except Exception as exc:  # noqa: BLE001 - a trigger never fails its command
        return {"ok": False, "status": "error", "path": GRAPH_REL,
                "warning": f"manuscript graph not rebuilt: {type(exc).__name__}: {exc}"[:300]}


def read_graph(root: Path | str, *, paper_dir: Path | str | None = None) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    path = root / GRAPH_REL
    if not path.is_file():
        return {"status": "absent", "stale": None, "graph": None}
    graph = _read_json(path)
    if not isinstance(graph, dict):
        return {"status": "invalid", "stale": None, "graph": None}
    try:
        paper = root / "paper" if paper_dir is None else Path(paper_dir).expanduser().resolve()
        stale = graph.get("generated_from") != _Sources(root, paper).digests()
    except Exception:  # noqa: BLE001 - staleness unknown
        stale = None
    return {"status": "ok", "stale": stale, "graph": graph}


def describe(result: dict[str, Any]) -> str:
    if result.get("ok"):
        missing = result["summary"]["missing"]
        return (f"manuscript graph: {result['summary']['edges']} edges, "
                f"missing: {', '.join(missing) or 'none'} -> {result['path']}")
    return f"manuscript graph not written ({result.get('status')}): " \
           f"{result.get('detail') or result.get('warning')}"


# --------------------------------------------------------------------------
# the offline view
# --------------------------------------------------------------------------
COLUMNS = (("topic", ("topic",)), ("problem", ("problem", "pillar")), ("hypothesis", ("hypothesis",)),
           ("sota", ("sota",)), ("math", ("base_concept", "novelty_concept")),
           ("experiment", ("experiment",)), ("finding", ("finding",)), ("conclusion", ("conclusion",)))
#: English display labels. The dashboard translates them in place through each
#: element's ``data-i18n`` key (``atlas.summaryView.<key>`` in ``static/i18n``).
LABELS = {
    "en": {"title": "Manuscript summary graph", "topic": "Topic", "problem": "Problem and pillars",
           "hypothesis": "Hypotheses", "sota": "Main SOTA", "math": "Base and novelty math",
           "experiment": "Experiments", "finding": "Findings", "conclusion": "Conclusions",
           "missing": "missing", "filledBy": "filled by", "source": "Source", "blocks": "Blocks",
           "stale": "Inputs changed since this graph was written: rebuild it.",
           "live": "Not written yet: a live reading (smith atlas summary writes it).",
           "pick": "Click a node to see its detail, source and paper blocks.",
           "base_concept": "base", "novelty_concept": "novelty", "pillar": "pillar"},
}
_COLORS = {"topic": "#38bdf8", "problem": "#f43f5e", "pillar": "#fb923c", "hypothesis": "#facc15",
           "sota": "#fb7185", "base_concept": "#94a3b8", "novelty_concept": "#10b981",
           "experiment": "#a855f7", "finding": "#22d3ee", "conclusion": "#e2e8f0"}


def _card(node: dict, L: dict[str, str]) -> str:
    esc = html.escape
    color = _COLORS[node["type"]]
    if node["status"]["state"] == "missing":
        return (f'<div class="node node--missing" data-id="{esc(node["id"])}" style="--c:{color}">'
                f'<span class="tag" data-i18n="atlas.summaryView.missing">{esc(L["missing"])}</span> '
                f'{esc(node["status"]["reason"])}<div class="phase">'
                f'<span data-i18n="atlas.summaryView.filledBy">{esc(L["filledBy"])}</span>: '
                f'{esc(node["status"]["phase"])}</div></div>')
    badge = ""
    if node["type"] in ("pillar", "base_concept", "novelty_concept"):
        badge = (f'<span class="tag" data-i18n="atlas.summaryView.{node["type"]}">'
                 f'{esc(L[node["type"]])}</span> ')
    if node["type"] == "finding":
        badge = f'<span class="tag tag--{esc(node.get("outcome", ""))}">{esc(node.get("outcome", ""))}</span> '
    return (f'<div class="node" tabindex="0" data-id="{esc(node["id"])}" style="--c:{color}">'
            f'{badge}{esc(node["label"])}</div>')


def render_html(graph: dict[str, Any], lang: str = "en", *, note: str = "") -> str:
    """``note`` is a ``LABELS`` key (``stale`` or ``live``) or empty. Labels are
    English; ``lang`` only sets the document language the dashboard translates to."""
    L = LABELS["en"]
    esc = html.escape
    lang = lang if lang in ("en", "es") else "en"
    columns = []
    for key, kinds in COLUMNS:
        cards = "".join(_card(n, L) for n in graph["nodes"] if n["type"] in kinds)
        columns.append(f'<section class="col"><h2 data-i18n="atlas.summaryView.{key}">{esc(L[key])}</h2>'
                       f'{cards}</section>')
    payload = json.dumps({"nodes": graph["nodes"], "edges": graph["edges"],
                          "labels": {k: L[k] for k in ("source", "blocks", "missing", "filledBy")}},
                         ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e") \
        .replace("&", "\\u0026")
    banner = (f'<div class="note" data-i18n="atlas.summaryView.{note}">{esc(L[note])}</div>'
              if note else "")
    return f"""<!DOCTYPE html>
<html lang="{esc(lang)}"><head><meta charset="utf-8"><title>{esc(L['title'])}</title>
<style>
body {{ margin: 0; background: #0b0f19; color: #e2e8f0; font: 13px/1.4 system-ui, sans-serif; }}
.note {{ padding: 6px 12px; background: #3b2f0b; color: #facc15; }}
#wrap {{ position: relative; }}
#edges {{ position: absolute; inset: 0; pointer-events: none; }}
#cols {{ display: grid; grid-template-columns: repeat(8, minmax(150px, 1fr)); gap: 14px; padding: 12px; }}
.col h2 {{ font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #94a3b8; margin: 0 0 8px; }}
.node {{ position: relative; border: 1px solid var(--c); border-left-width: 4px; border-radius: 6px;
  padding: 6px 8px; margin-bottom: 8px; background: #111827; cursor: pointer; }}
.node.sel {{ box-shadow: 0 0 0 2px var(--c); }}
.node--missing {{ border-style: dashed; opacity: .75; cursor: default; color: #94a3b8; }}
.phase {{ font-size: 11px; margin-top: 4px; }}
.tag {{ font-size: 10px; text-transform: uppercase; padding: 0 4px; border-radius: 3px; background: #1f2937; }}
.tag--supported {{ color: #10b981; }} .tag--refuted {{ color: #f43f5e; }} .tag--inconclusive {{ color: #facc15; }}
#detail {{ margin: 0 12px 12px; padding: 8px 10px; border: 1px solid #1f2937; border-radius: 6px; background: #111827; }}
#detail code {{ color: #93c5fd; }}
</style></head><body>
{banner}<div id="wrap"><svg id="edges"></svg><div id="cols">{''.join(columns)}</div></div>
<div id="detail" data-i18n="atlas.summaryView.pick">{esc(L['pick'])}</div>
<script type="application/json" id="graph-data">{payload}</script>
<script>
(function () {{
  const data = JSON.parse(document.getElementById('graph-data').textContent);
  const byId = new Map(data.nodes.map((n) => [n.id, n]));
  const esc = (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const svg = document.getElementById('edges');
  function draw() {{
    const box = document.getElementById('wrap').getBoundingClientRect();
    svg.setAttribute('width', box.width); svg.setAttribute('height', box.height);
    const parts = [];
    for (const e of data.edges) {{
      const a = document.querySelector(`.node[data-id="${{CSS.escape(e.from)}}"]`);
      const b = document.querySelector(`.node[data-id="${{CSS.escape(e.to)}}"]`);
      if (!a || !b) continue;
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      const x1 = ra.right - box.left, y1 = ra.top + ra.height / 2 - box.top;
      const x2 = rb.left - box.left, y2 = rb.top + rb.height / 2 - box.top;
      const color = e.verdict === 'refuted' ? '#f43f5e' : (e.verdict === 'supported' ? '#10b981' : '#475569');
      const mid = (x1 + x2) / 2;
      parts.push(`<path d="M${{x1}},${{y1}} C${{mid}},${{y1}} ${{mid}},${{y2}} ${{x2}},${{y2}}" fill="none" stroke="${{color}}" stroke-width="1.2" opacity=".7"><title>${{esc(e.rel)}}</title></path>`);
    }}
    svg.innerHTML = parts.join('');
  }}
  function select(el) {{
    const node = byId.get(el.dataset.id);
    if (!node || node.status.state !== 'present') return;
    document.querySelectorAll('.node.sel').forEach((n) => n.classList.remove('sel'));
    el.classList.add('sel');
    const L = Object.assign({{}}, data.labels, window.MG_LABELS || {{}});
    const blocks = (node.paper_blocks || []).map((b) => `<code>${{esc(b)}}</code>`).join(', ');
    document.getElementById('detail').innerHTML = `<strong>${{esc(node.label)}}</strong>` +
      (node.detail ? `<div>${{esc(node.detail)}}</div>` : '') +
      `<div>${{esc(L.source)}}: <code>${{esc(node.source.path)}}</code> ${{esc(node.source.locator)}}</div>` +
      (blocks ? `<div>${{esc(L.blocks)}}: ${{blocks}}</div>` : '');
    if (window.parent !== window) {{
      window.parent.postMessage({{ type: 'atlas-planet-selected', key: node.id, label: node.label,
        slot: node.type, system: {{ id: (node.paper_blocks || []).join(', '), title: node.source.path }} }}, '*');
    }}
  }}
  document.querySelectorAll('.node').forEach((el) => {{
    el.addEventListener('click', () => select(el));
    el.addEventListener('keydown', (ev) => {{ if (ev.key === 'Enter') select(el); }});
  }});
  // The cited-papers view asks to show one paper's node.
  window.addEventListener('message', (e) => {{
    if (e.source !== window.parent || !e.data || e.data.type !== 'manuscript-graph-locate') return;
    const el = Array.from(document.querySelectorAll('.node')).find((n) => n.dataset.id === e.data.id);
    if (!el) return;
    select(el);
    el.scrollIntoView({{ block: 'center', inline: 'center' }});
  }});
  window.addEventListener('resize', draw);
  window.addEventListener('wheel', (e) => {{
    if (window.parent !== window) window.parent.postMessage({{ type: 'page_scroll', deltaY: e.deltaY }}, '*');
  }}, {{ passive: true }});
  draw();
}})();
</script></body></html>
"""


def view_html(root: Path | str, lang: str = "en") -> str:
    """The stored graph (with a stale note), else a live, unwritten reading."""
    read = read_graph(root)
    if read["status"] == "ok":
        return render_html(read["graph"], lang, note="stale" if read["stale"] else "")
    return render_html(build_graph(root), lang, note="live")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skills._core.command_center.manuscript_graph",
        description="Write .papersmith/manuscript_graph.json: the manuscript summary graph.")
    parser.add_argument("--root", default=".", help="workspace root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)
    try:
        result = write_graph(args.root)
    except Exception as exc:  # noqa: BLE001 - reported, exit 1
        result = {"ok": False, "status": "error", "path": GRAPH_REL,
                  "detail": f"{type(exc).__name__}: {exc}"[:300]}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["ok"]:
        print(describe(result))
    if not result["ok"]:
        print(describe(result), file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
