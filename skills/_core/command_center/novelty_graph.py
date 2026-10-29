"""3D semantic novelty graph of a paper workspace.

The graph a workspace provides in ``.papersmith/novelty_graph.json`` (nodes,
links, groups; the shape ``build_novelty_graph`` returns) is drawn as-is.
Without it, a neutral initial graph named after the workspace is drawn, whose
nodes the deliberation phases populate. No project's graph ships with the
framework; the test suite carries one worked example under ``tests/fixtures/``.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from . import localize

#: The display fields of the graph (localize.py): labels the framework wrote.
#: Ids, groups, colours, links' ends, file references and page numbers are
#: never touched.
NOVELTY_FIELDS = frozenset({
    "title", "target_journal", "authors", "summary", "nodes.label", "nodes.category", "nodes.badge",
    "nodes.desc", "nodes.rhetorical_question", "nodes.paragraph_text", "nodes.metrics",
    "nodes.novelty_claim", "nodes.thesis_ref", "nodes.section_ref", "links.label",
})

def build_novelty_graph(root_path: Path | None = None) -> dict[str, Any]:
    """The workspace's own ``.papersmith/novelty_graph.json`` when it holds a
    graph, else a neutral initial graph named after the workspace."""
    if root_path is not None:
        own = Path(root_path) / ".papersmith" / "novelty_graph.json"
        try:
            data = json.loads(own.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("nodes"), list):
                return data
        except (OSError, ValueError):
            pass

    project_name = root_path.name if root_path else "Paper"
    return {
        "title": f"3D Graph of the Manuscript's Novelty and Ideas — {project_name}",
        "target_journal": "Editorial Target",
        "authors": "Research Team",
        "project": project_name,
        "summary": f"Conceptual structure at an initial stage for {project_name}. The semantic nodes are populated during phases 2 (SOTA), 4 (Proposal Deliberation) and 5 (Experimental PoC).",
        "nodes": [
            {
                "id": "core-project",
                "label": f"{project_name}: Proposal under Deliberation",
                "group": "core",
                "color": "#38bdf8",
                "size": 9.0,
                "category": "Overall Contribution",
                "badge": "MAIN ARCHITECTURE",
                "desc": f"Working and research framework for {project_name}, at an initial formulation stage.",
                "rhetorical_question": f"What is the central hypothesis and expected contribution of {project_name}?",
                "paragraph_text": f"The {project_name} project is at an initial stage of scientific proposal deliberation and coupling with the state of the art.",
                "metrics": "Phase 1 complete (Harness). Deliberation and experimentation phases pending.",
                "novelty_claim": "Methodological and theoretical innovation under formalization.",
                "thesis_ref": "Inputs in guidance/",
                "pdf_page": 1,
                "section_ref": "Section 1 (Introduction)",
                "paper_blocks": ["title-and-keywords.title", "abstract.slot-1", "introduction.block-1"]
            },
            {
                "id": "hub-problem",
                "label": "Problem & Technical Gap",
                "group": "problem",
                "color": "#ef4444",
                "size": 7.0,
                "category": "Challenges",
                "badge": "SCIENTIFIC GAP",
                "desc": "Limitations and bottlenecks in current approaches.",
                "rhetorical_question": "What fundamental unsolved problem does this research address?",
                "paragraph_text": "Pending formalization during Phase 4.",
                "metrics": "Pending",
                "novelty_claim": "Rigorous definition of the scientific gap.",
                "thesis_ref": "proposals/",
                "pdf_page": 1,
                "section_ref": "Section 1 (Introduction)",
                "paper_blocks": ["abstract.slot-2", "introduction.block-2"]
            },
            {
                "id": "hub-sota",
                "label": "SOTA Constellation & Baselines",
                "group": "sota",
                "color": "#10b981",
                "size": 7.0,
                "category": "State of the Art",
                "badge": "Q1 LITERATURE",
                "desc": "Mapping of comparison systems and reference papers.",
                "rhetorical_question": "Which reference baselines will the proposal be contrasted against?",
                "paragraph_text": "3D atlas under construction in sota-pool/.",
                "metrics": "Pending",
                "novelty_claim": "Comparative taxonomy with specialized literature.",
                "thesis_ref": "sota-pool/atlas.json",
                "pdf_page": 3,
                "section_ref": "Section 2 (Related Work)",
                "paper_blocks": ["related-work.rw-preamble", "related-work.rw-panorama"]
            },
            {
                "id": "hub-novelty",
                "label": "Methodology & Architecture",
                "group": "novelty",
                "color": "#f59e0b",
                "size": 7.0,
                "category": "Innovation",
                "badge": "METHODOLOGICAL PILLAR",
                "desc": "Components, mathematical formulation and system design.",
                "rhetorical_question": "What methodology or architecture is proposed to close the gap?",
                "paragraph_text": "Pending formal specification.",
                "metrics": "Pending",
                "novelty_claim": "Algorithmic / architectural innovation.",
                "thesis_ref": "sections/01-materials-and-methods.md",
                "pdf_page": 4,
                "section_ref": "Section 3 (Materials and Methods)",
                "paper_blocks": ["materials-and-methods.mm-preamble", "materials-and-methods.mm-proposal"]
            },
            {
                "id": "hub-eval",
                "label": "Empirical Validation & Experiments",
                "group": "eval",
                "color": "#a855f7",
                "size": 7.0,
                "category": "Metrology",
                "badge": "POC PROTOCOL",
                "desc": "Experimental design, success metrics and empirical contrasts.",
                "rhetorical_question": "How will the work's hypotheses be validated quantitatively?",
                "paragraph_text": "Experimental plan in experiments/.",
                "metrics": "Pending",
                "novelty_claim": "Reproducible success criteria.",
                "thesis_ref": "experiments/",
                "pdf_page": 5,
                "section_ref": "Section 4 (Experimental Setup)",
                "paper_blocks": ["experimental-setup.es-preamble", "results-and-discussion.rd-general-task"]
            }
        ],
        "links": [
            {"source": "core-project", "target": "hub-problem", "label": "addresses", "value": 3.0},
            {"source": "core-project", "target": "hub-sota", "label": "surpasses", "value": 3.0},
            {"source": "core-project", "target": "hub-novelty", "label": "implements", "value": 4.0},
            {"source": "core-project", "target": "hub-eval", "label": "validates with", "value": 3.5}
        ]
    }


def build_novelty_viewer_html(root_path: Path | None = None, lang: str = "en") -> str:
    """Generate the full responsive 3D WebGL viewer for the novelty graph,
    matching the exact style, typography, libraries, and constellation aesthetics of SOTA Atlas.

    English, or Spanish with ``lang="es"``: the page's labels and the graph's
    display fields go through ``localize`` (the graph's ids and links do not).
    """
    data = localize.localize(build_novelty_graph(root_path), lang, NOVELTY_FIELDS)
    page_lang = "es" if lang in localize.LANGUAGES else "en"
    # Escaped so the JSON can never close the page's <script>.
    graph_json = (json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
                  .replace(">", "\\u003e").replace("&", "\\u0026"))
    graph_title = html.escape(str(data.get("title") or localize.translate("3D Graph of the Manuscript's Novelty and Ideas", lang)))
    graph_subtitle = html.escape(f"{data.get('target_journal', '')} · {data.get('project', '')}")
    core_label = json.dumps(str(data.get("project") or localize.translate("Project", lang)), ensure_ascii=False)
    # Every label of the page, translated once; the f-string below only
    # indexes these (3.11 f-strings take no backslashes or nested quotes).
    _html = [html.escape(localize.translate(text, lang)) for text in (
        "Drag with the mouse to rotate (smooth orbit), wheel for a sensitive 3D zoom, right click to pan. Click any node to inspect its evidence and paragraphs. Use the colour chips to filter by the 8 key dimensions.",
        "8 Key Dimensions:",
        "Links:",
        "overall architecture",
        "claimed novelty",
        "closes a gap",
        "experimental evidence",
        "comparative metrics",
        "Move the camera closer",
        "Move the camera away",
        "Reset to the centred view",
        "Pause or resume the camera's smooth rotation",
        "⏸️ Pause rotation",
        "Switch what the mouse wheel does",
        "🖱️ Wheel: 3D Zoom",
        "🔍 Search a node, metric or paragraph...",
        "Category",
        "✕ close",
        "Node Name",
        "Detailed description of the node and its role in the research.",
        "📜 Excerpt of the Manuscript Paragraph (LaTeX)",
        "❓ Rhetorical Question It Answers",
        "🎯 Answer to the Novelty (Elsevier BSPC)",
        "⚡ Quantitative Metric / Fact",
        "📖 Grounding in the Thesis",
        "📑 Canonical Blocks and Location",
        "📄 Go to this Section in the PDF Viewer",
        "p. 1",
    )]
    labels_json = json.dumps({
        "pause": localize.translate("⏸️ Pause rotation", lang),
        "resume": localize.translate("▶️ Resume rotation", lang),
        "wheelZoom": localize.translate("🖱️ Wheel: 3D Zoom", lang),
        "wheelPage": localize.translate("📜 Wheel: Page Scroll", lang),
        "thesis": localize.translate("Master's Thesis", lang),
        "pageShort": localize.translate("p.", lang),
        "manuscript": localize.translate("Manuscript", lang),
        "location": localize.translate("Location in the document: page", lang),
        "gApp": localize.translate("1. Applications", lang),
        "gProblem": localize.translate("2. Central Problem", lang),
        "gSota": localize.translate("3. Nearby SOTA Ideas", lang),
        "gNovelty": localize.translate("4. Novelty", lang),
        "gDataset": localize.translate("5. Datasets Tested", lang),
        "gEval": localize.translate("6. Metrics & Comparison", lang),
        "gConclusion": localize.translate("7. Conclusions", lang),
        "gFuture": localize.translate("8. Future Work", lang),
    }, ensure_ascii=False).replace("<", "\\u003c")
    
    return f"""<!DOCTYPE html>
<html lang="{page_lang}">
<head>
  <meta charset="utf-8">
  <title>{graph_title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://unpkg.com/3d-force-graph@1.73.3/dist/3d-force-graph.min.js"></script>
  <style>
    html, body {{
      height: 100%;
      margin: 0;
      padding: 10px 14px;
      box-sizing: border-box;
      background: #0a0a10;
      color: #e4e4ed;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}
    h1 {{
      font-size: 16px;
      font-weight: 600;
      margin: 0 0 4px;
      letter-spacing: .02em;
      color: #f1f5f9;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    h1 small {{
      font-size: 11px;
      font-weight: 400;
      color: #64748b;
      letter-spacing: 0;
    }}
    #panel {{
      color: #9aa3bd;
      font-size: 12px;
      margin: 0 0 6px;
      line-height: 1.35;
    }}
    #famlegend, #rellegend, #toolbar {{
      margin: 0 0 5px;
      font-size: 12px;
      color: #9aa3bd;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
    }}
    #famlegend em, #rellegend em {{
      font-style: normal;
      font-weight: 600;
      margin-right: 6px;
      color: #cbd5e1;
    }}
    .famchip {{
      margin: 2px 4px 2px 0;
      padding: 2.5px 10px;
      cursor: pointer;
      border-radius: 12px;
      border: 1px solid #334155;
      background: #14172a;
      color: #e4e4ed;
      font-size: 11.5px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: all 0.15s ease;
      user-select: none;
    }}
    .famchip:hover {{
      background: #1e243d;
      border-color: #475569;
    }}
    .famchip.on {{
      font-weight: 700;
      box-shadow: 0 0 10px currentColor;
    }}
    .famchip-dot {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
      display: inline-block;
    }}
    .dot {{
      display: inline-block;
      width: 14px;
      height: 0;
      border-top: 2px solid;
      margin: 0 3px 2px 8px;
      vertical-align: middle;
    }}
    #toolbar {{
      gap: 6px;
    }}
    #toolbar button {{
      font-size: 12px;
      padding: 3.5px 11px;
      cursor: pointer;
      background: #14172a;
      color: #e4e4ed;
      border: 1px solid #2a3350;
      border-radius: 6px;
      transition: background 0.15s, border-color 0.15s;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    #toolbar button:hover {{
      background: #1e243d;
      border-color: #38bdf8;
    }}
    #toolbar button.active {{
      background: #0284c7;
      border-color: #38bdf8;
      color: #fff;
    }}
    #nodeSearchInput {{
      background: #14172a;
      border: 1px solid #2a3350;
      border-radius: 6px;
      padding: 3px 10px;
      font-size: 12px;
      color: #e4e4ed;
      outline: none;
      margin-left: 6px;
      width: 220px;
    }}
    #nodeSearchInput:focus {{
      border-color: #38bdf8;
      box-shadow: 0 0 8px rgba(56, 189, 248, 0.3);
    }}
    .sky {{
      flex: 1 1 auto;
      min-height: 420px;
      width: 100%;
      background: #0a0a10;
      border: 1px solid #1e2236;
      border-radius: 10px;
      overflow: hidden;
      position: relative;
      cursor: grab;
    }}
    .sky:active {{
      cursor: grabbing;
    }}
    #3d-graph {{
      width: 100%;
      height: 100%;
    }}

    /* Side Inspector Card (Modal Style matching SOTA Atlas) */
    .inspector-card {{
      position: absolute;
      top: 12px;
      right: 12px;
      width: 440px;
      max-width: calc(100vw - 28px);
      max-height: calc(100% - 24px);
      background: #11131f;
      border: 1px solid #2a3350;
      border-radius: 10px;
      padding: 16px 18px;
      overflow-y: auto;
      z-index: 20;
      box-shadow: 0 0 40px rgba(14, 165, 233, 0.2);
      display: none;
      scrollbar-width: thin;
    }}
    .inspector-card__header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      padding-bottom: 6px;
      border-bottom: 1px solid #1e243d;
    }}
    .inspector-badge {{
      display: inline-block;
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .inspector-close {{
      background: #1a1d2e;
      border: 1px solid #2a3350;
      color: #e4e4ed;
      font-size: 13px;
      padding: 1px 8px;
      border-radius: 4px;
      cursor: pointer;
    }}
    .inspector-close:hover {{
      background: #2a3350;
    }}
    .inspector-title {{
      font-size: 15px;
      font-weight: 700;
      color: #fff;
      margin-bottom: 6px;
      line-height: 1.3;
    }}
    .inspector-desc {{
      font-size: 12px;
      color: #94a3b8;
      line-height: 1.5;
      margin-bottom: 12px;
    }}
    .quote {{
      font-style: italic;
      color: #b9c4de;
      border-left: 3px solid #10b981;
      margin: 10px 0;
      padding: 8px 12px;
      background: rgba(16, 185, 129, 0.05);
      border-radius: 0 6px 6px 0;
      font-family: Georgia, serif;
      line-height: 1.55;
      font-size: 12.5px;
    }}
    .inspector-meta-block {{
      margin-bottom: 10px;
      font-size: 12px;
      line-height: 1.45;
    }}
    .inspector-meta-block strong {{
      color: #cbd5e1;
      display: block;
      margin-bottom: 3px;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .inspector-meta-block em {{
      color: #38bdf8;
      font-style: normal;
    }}
    .inspector-meta-block span {{
      color: #94a3b8;
    }}
    .inspector-blocks {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 4px;
    }}
    .block-pill {{
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.25);
      color: #38bdf8;
      padding: 1px 6px;
      border-radius: 3px;
      font-size: 10.5px;
      font-family: monospace;
    }}
    .btn-action-jump {{
      width: 100%;
      background: #0284c7;
      color: #fff;
      border: 1px solid #38bdf8;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      margin-top: 10px;
      transition: background 0.15s, transform 0.15s;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
    }}
    .btn-action-jump:hover {{
      background: #0369a1;
      transform: translateY(-1px);
    }}
  </style>
</head>
<body>

  <!-- Top Title and Instructions (Atlas Style) -->
  <h1>
    <span>🕸️ {graph_title}</span>
    <small>{graph_subtitle}</small>
  </h1>
  <div id="panel">{_html[0]}</div>

  <!-- Legend & Color Grouping Chips (Atlas Style) -->
  <div id="famlegend"><em>{_html[1]}</em> <span id="famchips"></span></div>
  <div id="rellegend"><em>{_html[2]}</em> <span class="dot" style="border-color:#38bdf8"></span>{_html[3]} <span class="dot" style="border-color:#10b981"></span>{_html[4]} <span class="dot" style="border-color:#f43f5e"></span>{_html[5]} <span class="dot" style="border-color:#a855f7"></span>{_html[6]} <span class="dot" style="border-color:#eab308"></span>{_html[7]}</div>

  <!-- Toolbar Controls (Atlas Style) -->
  <div id="toolbar">
    <button id="zoomin" title="{_html[8]}">🔍 Zoom +</button>
    <button id="zoomout" title="{_html[9]}">🔍 Zoom −</button>
    <button id="zoomreset" title="{_html[10]}">↺ Reset</button>
    <button id="btnAutoRotate" class="active" title="{_html[11]}">{_html[12]}</button>
    <button id="btnWheelMode" title="{_html[13]}">{_html[14]}</button>
    <input type="text" id="nodeSearchInput" placeholder="{_html[15]}" oninput="searchNodes(this.value)">
  </div>

  <!-- Sky Canvas Container -->
  <div id="sky" class="sky">
    <div id="3d-graph"></div>

    <!-- Side Inspector Drawer / Modal -->
    <aside class="inspector-card" id="inspectorCard">
      <div class="inspector-card__header">
        <span class="inspector-badge" id="inspBadge">{_html[16]}</span>
        <button class="inspector-close" onclick="closeInspector()">{_html[17]}</button>
      </div>
      <div class="inspector-title" id="inspTitle">{_html[18]}</div>
      <p class="inspector-desc" id="inspDesc">{_html[19]}</p>
      
      <!-- Excerpt of the manuscript paragraph -->
      <div id="inspParagraphBox" style="display: none; margin-bottom: 10px;">
        <strong style="font-size: 11px; text-transform: uppercase; color: #cbd5e1; letter-spacing: 0.04em;">{_html[20]}</strong>
        <div class="quote" id="inspParagraphText">—</div>
      </div>

      <!-- Rhetorical question it answers -->
      <div class="inspector-meta-block" id="inspQuestionBox">
        <strong>{_html[21]}</strong>
        <em id="inspQuestion">—</em>
      </div>

      <!-- Answer to the novelty -->
      <div class="inspector-meta-block">
        <strong>{_html[22]}</strong>
        <span id="inspNovelty">—</span>
      </div>

      <!-- Quantitative metric -->
      <div class="inspector-meta-block">
        <strong>{_html[23]}</strong>
        <span id="inspMetrics">—</span>
      </div>

      <!-- Grounding in the thesis -->
      <div class="inspector-meta-block">
        <strong>{_html[24]}</strong>
        <span id="inspThesis">—</span>
      </div>

      <!-- Canonical blocks and location -->
      <div class="inspector-meta-block">
        <strong>{_html[25]}</strong>
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;" id="inspLocation">—</div>
        <div class="inspector-blocks" id="inspBlocks"></div>
      </div>

      <button class="btn-action-jump" id="btnJumpPdf" onclick="jumpToPaperPreview()">
        {_html[26]} (<span id="inspPdfPage">{_html[27]}</span>) ↗
      </button>
    </aside>
  </div>

  <script>
    const graphData = {graph_json};
    const L = {labels_json};

    let isRotating = true;
    let selectedNode = null;
    let activeGroup = null;
    let hoverNode = null;
    let targetPdfPage = 1;
    let wheelMode = 'zoom'; // 'zoom' | 'page'

    const highlightNodes = new Set();
    const highlightLinks = new Set();

    const elem = document.getElementById('3d-graph');
    const Graph = ForceGraph3D()(elem)
      .graphData(graphData)
      .backgroundColor('#0a0a10')
      .showNavInfo(false)
      .nodeLabel(node => `${{node.label}} [${{node.category}}]`)
      .nodeVal(node => node.size || 5)
      .nodeResolution(24)
      .nodeColor(node => {{
        if (highlightNodes.size > 0 && !highlightNodes.has(node.id)) {{
          return 'rgba(45, 52, 75, 0.22)';
        }}
        return node.color || '#38bdf8';
      }})
      .linkWidth(link => {{
        if (highlightLinks.size > 0 && !highlightLinks.has(link)) return 0.5;
        return link.value ? link.value * 0.7 : 1.2;
      }})
      .linkColor(link => {{
        if (highlightLinks.size > 0 && !highlightLinks.has(link)) {{
          return 'rgba(25, 30, 48, 0.08)';
        }}
        if (link.source && (link.source.group === 'novelty' || link.source === 'novelty')) return 'rgba(16, 185, 129, 0.55)';
        if (link.source && (link.source.group === 'problem' || link.source === 'problem')) return 'rgba(244, 63, 94, 0.45)';
        return 'rgba(56, 189, 248, 0.35)';
      }})
      .linkDirectionalParticles(2)
      .linkDirectionalParticleWidth(link => {{
        if (highlightLinks.size > 0 && !highlightLinks.has(link)) return 0;
        return 1.6;
      }})
      .linkDirectionalParticleSpeed(0.005)
      .linkDirectionalParticleColor(link => {{
        if (link.source && (link.source.group === 'novelty' || link.source === 'novelty')) return '#10b981';
        if (link.source && (link.source.group === 'problem' || link.source === 'problem')) return '#f43f5e';
        return '#38bdf8';
      }})
      .linkLabel(link => link.label)
      .onNodeHover(node => {{
        elem.style.cursor = node ? 'pointer' : null;
        hoverNode = node;
        updateHighlight();
        Graph.nodeColor(Graph.nodeColor()).linkColor(Graph.linkColor()).linkWidth(Graph.linkWidth());
      }})
      .onNodeClick(node => {{
        selectNode(node);
      }})
      .onBackgroundClick(() => {{
        closeInspector();
      }});

    // Configure OrbitControls for maximum responsiveness, buttery smooth damping, and non-blocking auto-rotate
    setTimeout(() => {{
      const controls = Graph.controls();
      if (controls) {{
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
        controls.rotateSpeed = 0.85;
        controls.zoomSpeed = 1.35;
        controls.panSpeed = 0.85;
        controls.enableZoom = true;
        controls.autoRotate = isRotating;
        controls.autoRotateSpeed = 0.7;

        // Yield auto-rotation gently when user starts manipulating
        controls.addEventListener('start', () => {{
          if (isRotating) {{
            controls.autoRotate = false;
          }}
        }});
        controls.addEventListener('end', () => {{
          if (isRotating && !selectedNode) {{
            controls.autoRotate = true;
          }}
        }});
      }}
    }}, 200);

    function updateHighlight() {{
      highlightNodes.clear();
      highlightLinks.clear();

      if (hoverNode) {{
        highlightNodes.add(hoverNode.id);
        graphData.links.forEach(l => {{
          const sId = typeof l.source === 'object' ? l.source.id : l.source;
          const tId = typeof l.target === 'object' ? l.target.id : l.target;
          if (sId === hoverNode.id || tId === hoverNode.id) {{
            highlightLinks.add(l);
            highlightNodes.add(sId);
            highlightNodes.add(tId);
          }}
        }});
      }} else if (activeGroup) {{
        graphData.nodes.forEach(n => {{
          if (n.group === activeGroup || n.group === 'core') {{
            highlightNodes.add(n.id);
          }}
        }});
        graphData.links.forEach(l => {{
          const sId = typeof l.source === 'object' ? l.source.id : l.source;
          const tId = typeof l.target === 'object' ? l.target.id : l.target;
          if (highlightNodes.has(sId) && highlightNodes.has(tId)) {{
            highlightLinks.add(l);
          }}
        }});
      }}
    }}

    function toggleRotate() {{
      isRotating = !isRotating;
      const controls = Graph.controls();
      if (controls) {{
        controls.autoRotate = isRotating;
      }}
      const btn = document.getElementById('btnAutoRotate');
      btn.textContent = isRotating ? L.pause : L.resume;
      btn.classList.toggle('active', isRotating);
    }}
    document.getElementById('btnAutoRotate').addEventListener('click', toggleRotate);

    function toggleWheelMode() {{
      wheelMode = (wheelMode === 'zoom') ? 'page' : 'zoom';
      const btn = document.getElementById('btnWheelMode');
      btn.textContent = wheelMode === 'zoom' ? L.wheelZoom : L.wheelPage;
      btn.classList.toggle('active', wheelMode === 'page');
    }}
    document.getElementById('btnWheelMode').addEventListener('click', toggleWheelMode);

    // Mouse wheel delegate: forward to parent page scroll when hovering UI, holding Shift, or in page scroll mode
    window.addEventListener('wheel', (e) => {{
      const isUI = e.target.closest('#famlegend, #rellegend, #toolbar, h1, #panel, .inspector-card');
      if (wheelMode === 'page' || e.shiftKey || isUI) {{
        if (window.parent && window.parent !== window) {{
          window.parent.postMessage({{ type: 'page_scroll', deltaY: e.deltaY }}, '*');
        }}
      }}
    }}, {{ passive: true }});

    document.getElementById('zoomin').addEventListener('click', () => {{
      const pos = Graph.cameraPosition();
      Graph.cameraPosition({{ x: pos.x * 0.72, y: pos.y * 0.72, z: pos.z * 0.72 }}, null, 350);
    }});

    document.getElementById('zoomout').addEventListener('click', () => {{
      const pos = Graph.cameraPosition();
      Graph.cameraPosition({{ x: pos.x * 1.35, y: pos.y * 1.35, z: pos.z * 1.35 }}, null, 350);
    }});

    document.getElementById('zoomreset').addEventListener('click', () => {{
      isRotating = true;
      const controls = Graph.controls();
      if (controls) controls.autoRotate = true;
      document.getElementById('btnAutoRotate').textContent = L.pause;
      document.getElementById('btnAutoRotate').classList.add('active');
      activeGroup = null;
      document.querySelectorAll('.famchip').forEach(c => {{
        c.classList.remove('on');
        c.style.background = '#14172a';
        c.style.color = '#e4e4ed';
      }});
      updateHighlight();
      Graph.nodeColor(Graph.nodeColor()).linkColor(Graph.linkColor()).linkWidth(Graph.linkWidth());
      Graph.cameraPosition({{ x: 0, y: 30, z: 420 }}, {{ x: 0, y: 0, z: 0 }}, 800);
    }});

    function selectNode(node) {{
      selectedNode = node;
      const controls = Graph.controls();
      if (controls) controls.autoRotate = false;

      const dist = 160;
      Graph.cameraPosition(
        {{ x: node.x + dist * 0.7, y: node.y + dist * 0.35, z: node.z + dist * 0.7 }},
        {{ x: node.x, y: node.y, z: node.z }},
        900
      );

      const card = document.getElementById('inspectorCard');
      card.style.display = 'block';
      
      const badge = document.getElementById('inspBadge');
      badge.textContent = node.badge || node.category;
      badge.style.background = `${{node.color}}25`;
      badge.style.color = node.color;
      badge.style.border = `1px solid ${{node.color}}`;

      document.getElementById('inspTitle').textContent = node.label;
      document.getElementById('inspDesc').textContent = node.desc;
      document.getElementById('inspMetrics').textContent = node.metrics || '—';
      document.getElementById('inspNovelty').textContent = node.novelty_claim || '—';
      document.getElementById('inspThesis').textContent = node.thesis_ref || L.thesis;

      const paraBox = document.getElementById('inspParagraphBox');
      const paraText = document.getElementById('inspParagraphText');
      if (node.paragraph_text) {{
        paraBox.style.display = 'block';
        paraText.textContent = `"${{node.paragraph_text}}"`;
      }} else {{
        paraBox.style.display = 'none';
      }}

      const qBox = document.getElementById('inspQuestionBox');
      const qText = document.getElementById('inspQuestion');
      if (node.rhetorical_question) {{
        qBox.style.display = 'block';
        qText.textContent = `"${{node.rhetorical_question}}"`;
      }} else {{
        qBox.style.display = 'none';
      }}

      targetPdfPage = node.pdf_page || 1;
      document.getElementById('inspPdfPage').textContent = `${{L.pageShort}} ${{targetPdfPage}}`;
      document.getElementById('inspLocation').textContent = `${{node.section_ref || L.manuscript}} · ${{L.location}} ${{targetPdfPage}}`;

      const blocksContainer = document.getElementById('inspBlocks');
      blocksContainer.innerHTML = '';
      (node.paper_blocks || []).forEach(b => {{
        const pill = document.createElement('span');
        pill.className = 'block-pill';
        pill.textContent = b;
        blocksContainer.appendChild(pill);
      }});
    }}

    function closeInspector() {{
      document.getElementById('inspectorCard').style.display = 'none';
      selectedNode = null;
      const controls = Graph.controls();
      if (controls && isRotating) {{
        controls.autoRotate = true;
      }}
    }}

    // Build Family Legend Chips (Exact 8 Pillars matching the User Specification)
    const GROUPS_META = [
      {{ id: 'core', label: {core_label}, color: '#38bdf8' }},
      {{ id: 'app', label: L.gApp, color: '#0ea5e9' }},
      {{ id: 'problem', label: L.gProblem, color: '#f43f5e' }},
      {{ id: 'sota', label: L.gSota, color: '#fb7185' }},
      {{ id: 'novelty', label: L.gNovelty, color: '#10b981' }},
      {{ id: 'dataset', label: L.gDataset, color: '#a855f7' }},
      {{ id: 'eval', label: L.gEval, color: '#eab308' }},
      {{ id: 'conclusion', label: L.gConclusion, color: '#06b6d4' }},
      {{ id: 'future', label: L.gFuture, color: '#ec4899' }}
    ];

    const chipsContainer = document.getElementById('famchips');
    GROUPS_META.forEach(g => {{
      const count = graphData.nodes.filter(n => n.group === g.id).length;
      if (count === 0) return;
      const chip = document.createElement('span');
      chip.className = 'famchip';
      chip.dataset.group = g.id;
      chip.style.borderColor = g.color;
      chip.innerHTML = `<span class="famchip-dot" style="background:${{g.color}}"></span>${{g.label}} (${{count}})`;
      
      chip.addEventListener('click', () => {{
        if (activeGroup === g.id) {{
          activeGroup = null;
          chip.classList.remove('on');
          chip.style.background = '#14172a';
          chip.style.color = '#e4e4ed';
        }} else {{
          activeGroup = g.id;
          document.querySelectorAll('.famchip').forEach(c => {{
            c.classList.remove('on');
            c.style.background = '#14172a';
            c.style.color = '#e4e4ed';
          }});
          chip.classList.add('on');
          chip.style.background = g.color;
          chip.style.color = '#0a0a10';
        }}
        updateHighlight();
        Graph.nodeColor(Graph.nodeColor()).linkColor(Graph.linkColor()).linkWidth(Graph.linkWidth());
      }});

      chipsContainer.appendChild(chip);
    }});

    function searchNodes(query) {{
      if (!query || !query.trim()) {{
        activeGroup = null;
        updateHighlight();
        Graph.nodeColor(Graph.nodeColor()).linkColor(Graph.linkColor()).linkWidth(Graph.linkWidth());
        return;
      }}
      const q = query.toLowerCase().trim();
      const match = graphData.nodes.find(n => 
        n.label.toLowerCase().includes(q) ||
        (n.desc && n.desc.toLowerCase().includes(q)) ||
        (n.paragraph_text && n.paragraph_text.toLowerCase().includes(q)) ||
        (n.metrics && n.metrics.toLowerCase().includes(q)) ||
        (n.novelty_claim && n.novelty_claim.toLowerCase().includes(q))
      );
      if (match) {{
        selectNode(match);
      }}
    }}

    function jumpToPaperPreview() {{
      if (window.parent && window.parent.jumpToPdfPage) {{
        window.parent.jumpToPdfPage(targetPdfPage);
      }} else if (window.parent && window.parent.navigateTab) {{
        window.parent.navigateTab('preview');
      }} else {{
        window.open('/#preview', '_blank');
      }}
    }}
  </script>
</body>
</html>"""
