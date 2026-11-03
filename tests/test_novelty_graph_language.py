"""The 3D novelty graph says when its workspace file is not English.

`.papersmith/novelty_graph.json` is the workspace's own graph, drawn as written.
An agent wrote QMLEEG's in Spanish, so the novelty view showed Spanish with the
dashboard in English -- and an accent search over the page missed it, because
the scene travels as ASCII-escaped JSON. The graph now carries the same
`language_notice` as the model specification, the viewer states it in the
dashboard's language, and proposal-deliberation owns the file in English.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import novelty_graph

REPO = Path(__file__).resolve().parents[1]

SPANISH_GRAPH = {
    "title": "Grafo 3D de Novedad", "project": "QMLEEG",
    "summary": "Estructura conceptual y metodológica formalizada en la revisión de la propuesta.",
    "nodes": [{"id": "core", "group": "core", "label": "Red Híbrida", "color": "#38bdf8",
               "desc": "Clasificador híbrido cuántico-clásico con reinyectado de datos para el diagnóstico de TDAH.",
               "rhetorical_question": "¿Cómo clasificar TDAH desde EEG superando la limitación de expresividad?"}],
    "links": [],
}
ENGLISH_GRAPH = {
    "title": "3D Novelty Graph", "project": "QMLEEG",
    "summary": "Conceptual structure of the proposal.",
    "nodes": [{"id": "core", "group": "core", "label": "Hybrid network",
               "desc": "A hybrid classifier with data re-uploading for ADHD diagnosis.",
               "rhetorical_question": "How can ADHD be classified from EEG beyond the expressivity limit?"}],
    "links": [],
}


def workspace(graph: dict | None) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "papersmith.yaml").write_text("title: Fresh\n", encoding="utf-8")
    if graph is not None:
        (root / ".papersmith").mkdir()
        (root / ".papersmith" / "novelty_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    return root


class NoticeTests(unittest.TestCase):
    def test_a_spanish_graph_names_its_file_and_fields(self) -> None:
        notice = novelty_graph.build_novelty_graph(workspace(SPANISH_GRAPH))["language_notice"]
        self.assertEqual(notice["file"], ".papersmith/novelty_graph.json")
        for field in ("summary", "nodes.desc", "nodes.rhetorical_question"):
            self.assertIn(field, notice["fields"])

    def test_an_english_or_neutral_graph_has_no_notice(self) -> None:
        self.assertNotIn("language_notice", novelty_graph.build_novelty_graph(workspace(ENGLISH_GRAPH)))
        self.assertNotIn("language_notice", novelty_graph.build_novelty_graph(workspace(None)))

    def test_the_viewer_states_the_notice_in_the_dashboard_language(self) -> None:
        root = workspace(SPANISH_GRAPH)
        english = novelty_graph.build_novelty_viewer_html(root, "en")
        self.assertIn('id="langnote"', english)
        self.assertIn("is not written in English", english)
        self.assertIn(".papersmith/novelty_graph.json", english)
        spanish = novelty_graph.build_novelty_viewer_html(root, "es")
        self.assertIn("no está escrito en inglés", spanish)

    def test_an_english_graph_draws_no_notice(self) -> None:
        page = novelty_graph.build_novelty_viewer_html(workspace(ENGLISH_GRAPH), "en")
        self.assertNotIn('id="langnote"', page)


class OwnershipTests(unittest.TestCase):
    def test_proposal_deliberation_owns_the_novelty_graph_in_english(self) -> None:
        skill = (REPO / "skills" / "proposal-deliberation" / "SKILL.md").read_text(encoding="utf-8")
        start = skill.index("`.papersmith/novelty_graph.json`")
        section = " ".join(skill[start:start + 1500].split())
        self.assertIn("English", section)
        self.assertIn("rhetorical_question", section)


if __name__ == "__main__":
    unittest.main()
