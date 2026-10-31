"""The dashboard's graph toolbar and its links to the PDF and artifacts.

The page is a hand-written static file, so these pin its wiring: the two
graph buttons, the atlas message contract, and the panels that must survive
(the concept map and the smith phase flow)."""

from __future__ import annotations

import unittest
from pathlib import Path

from skills._core.command_center import server

STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
ES_CATALOGUE = (STATIC / "i18n" / "es.js").read_text(encoding="utf-8")


class GraphToolbarTests(unittest.TestCase):
    def test_regenerate_and_group_layout_buttons_sit_in_the_graph_toolbar(self) -> None:
        self.assertIn('id="btnBuildGraph" class="btn" onclick="triggerBuildAtlas()"', PAGE)
        # The label is rendered through the i18n catalogue: the page carries
        # the English default and the key, the Spanish copy lives in es.js.
        self.assertIn('data-i18n="atlas.build">⚡ Regenerate graph</button>', PAGE)
        self.assertIn('"atlas.build": "⚡ Regenerar grafo"', ES_CATALOGUE)
        self.assertIn('id="btnGroupLayout" class="btn" onclick="toggleAtlasGroupLayout()"', PAGE)
        self.assertIn('data-i18n="atlas.group">🧩 Group layout</button>', PAGE)
        self.assertIn('"atlas.group": "🧩 Disposición de grupos"', ES_CATALOGUE)

    def test_regenerate_posts_to_the_build_route_and_reloads_the_frame(self) -> None:
        self.assertIn("fetch('/api/atlas/build', { method: 'POST' })", PAGE)
        self.assertIn("iframe.src = `/api/atlas/view?v=${Date.now()}`", PAGE)

    def test_the_3d_view_loads_with_its_tab_not_with_the_page(self) -> None:
        self.assertIn('<iframe id="graphIframe" class="iframe-viewer" src="about:blank" onload="if (this.getAttribute(\'src\') !== \'about:blank\' &amp;&amp; activeTab !== \'atlas\') postToGraph({ type: \'atlas-command\', command: \'pause\' })"></iframe>', PAGE)
        self.assertIn("if (tabId === 'atlas' && graphFramePath() === 'blank') {", PAGE)

    def test_the_atlas_stops_drawing_while_its_tab_is_not_shown(self) -> None:
        self.assertIn("postToGraph({ type: 'atlas-command', command: tabId === 'atlas' ? 'resume' : 'pause' });", PAGE)
        assets = Path(server.__file__).resolve().parents[2] / "plausibility"
        page = (assets / "scripts" / "render_atlas.py").read_text(encoding="utf-8")
        # The page also pauses while the browser hides it, so the dashboard's
        # pause and the page's own visibility combine in applyVisibility().
        self.assertIn("'pause': () => { dashboardPaused = true; applyVisibility(); },", page)
        self.assertIn("'resume': () => { dashboardPaused = false; applyVisibility(); },", page)

    def test_the_native_pdf_viewer_loads_only_when_it_is_shown(self) -> None:
        self.assertIn('<iframe id="pdfNativeIframe" class="iframe-viewer" src="about:blank"', PAGE)
        self.assertIn("showNativePdfFallback();", PAGE)
        self.assertIn("if (iframe.getAttribute('src') === 'about:blank') iframe.src = `/api/pdf?t=${Date.now()}`;", PAGE)
        self.assertIn("if (native && isNativePdfViewer) native.src = `/api/pdf?v=${token}`;", PAGE)

    def test_the_atlas_contract_is_spoken_and_heard(self) -> None:
        self.assertIn("postToGraph({ type: 'atlas-command', command: 'toggle-layout' })", PAGE)
        self.assertIn("e.source !== iframe.contentWindow", PAGE)
        self.assertIn("data.type === 'atlas-layout'", PAGE)
        self.assertIn("data.type === 'atlas-planet-selected'", PAGE)

    def test_a_selected_node_links_to_the_pdf_and_its_artifact(self) -> None:
        self.assertIn('onclick="atlasSelectionToPdf()"', PAGE)
        self.assertIn("findTextInPdf([atlasSelection.label, atlasSelection.systemTitle])", PAGE)
        self.assertIn("jumpToArtifact('sota-pool/atlas.json')", PAGE)


class PreservedPanelsTests(unittest.TestCase):
    def test_the_concept_map_panel_is_still_there(self) -> None:
        self.assertIn('id="pane-modelo"', PAGE)
        self.assertIn('data-i18n="nav.model">🧠 Concept Map &amp; Model</button>', PAGE)
        self.assertIn('"nav.model": "🧠 Mapa Conceptual & Modelo"', ES_CATALOGUE)

    def test_the_graph_switches_and_smith_phase_run_are_unchanged(self) -> None:
        for kind in ("atlas", "novelty", "papers"):
            self.assertIn(f"onclick=\"switchGraph('{kind}')\"", PAGE)
        self.assertIn("fetch('/api/phase/run', {", PAGE)
        self.assertIn("onclick=\"triggerRunPhase('${escapeHtml(p.id)}', this)\"", PAGE)

    def test_the_archify_flow_tab_comes_first_and_opens_by_default(self) -> None:
        order = ["flow", "pipeline", "modelo", "sections", "atlas",
                 "preview", "artifacts", "telemetria"]
        positions = [PAGE.index(f"onclick=\"navigateTab('{tab}')\"") for tab in order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('<button class="tab-nav__btn active" onclick="navigateTab(\'flow\')" data-i18n="nav.flow">', PAGE)
        self.assertIn('id="pane-flow" class="tab-pane active"', PAGE)
        self.assertIn('id="pane-pipeline" class="tab-pane"', PAGE)
        self.assertIn("let activeTab = 'flow';", PAGE)

if __name__ == "__main__":
    unittest.main()
