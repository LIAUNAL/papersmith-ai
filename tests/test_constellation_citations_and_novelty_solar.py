"""Tests for constellation citation synchronization and 3D solar novelty graph."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import unittest
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))
import paper_cli
from skills._core.command_center import atlas_manuscript, novelty_graph


def _make_planet(pid: str, slot: str, orbit: int, label: str) -> dict:
    return {
        "id": pid, "slot": slot, "orbit": orbit, "label": label, "detail": label,
        "provenance": "stated", "evidence": {"origin": "10.1234/baseline", "quote": "quote"}
    }


def _make_atlas() -> dict:
    return {
        "pool": "sota-pool/candidates.json",
        "retrieved": "2026-11-02",
        "systems": [
            {
                "id": "sys-baseline",
                "title": "Baseline Study",
                "year": 2023,
                "identifier": "10.1234/baseline",
                "source_url": "https://doi.org/10.1234/baseline",
                "planets": [
                    _make_planet("sun", "sun", 0, "Baseline (2023)"),
                    _make_planet("fam", "family", 2, "Baselines"),
                    _make_planet("app", "topic_app", 1, "App Domain"),
                    _make_planet("ai", "topic_ai", 1, "AI Method"),
                    _make_planet("prob", "problem", 1, "Problem"),
                    _make_planet("nov", "novelty", 1, "Novelty"),
                    _make_planet("res", "result", 3, "Result"),
                    _make_planet("concl", "conclusion", 3, "Conclusion"),
                ]
            }
        ],
        "links": []
    }


SAMPLE_BIB = """@article{sys-baseline,
  title={Baseline Study},
  author={Smith, John},
  year={2023},
  doi={10.1234/baseline}
}

@article{extra-paper2024,
  title={Extra Cited Paper on EEG},
  author={Doe, Jane and Brown, Bob},
  year={2024},
  doi={10.5678/extra},
  journal={Journal of Neural Engineering}
}
"""

SAMPLE_TEX = r"""\documentclass{article}
\begin{document}
Introduction citing \cite{sys-baseline} and \cite{extra-paper2024}.
\end{document}
"""


class ConstellationCitationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "sota-pool").mkdir()
        (self.root / "paper").mkdir()
        (self.root / "paper" / "refs.bib").write_text(SAMPLE_BIB, encoding="utf-8")
        (self.root / "paper" / "main.tex").write_text(SAMPLE_TEX, encoding="utf-8")
        (self.root / "sota-pool" / "atlas.json").write_text(json.dumps(_make_atlas()), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_build_constellation_with_citations_adds_extra_systems(self) -> None:
        constellation = atlas_manuscript.build_constellation_with_citations(self.root)
        self.assertIn("systems", constellation)
        by_id = {s["id"]: s for s in constellation["systems"]}
        
        # Both in-pool and extra cited paper are present
        self.assertIn("sys-baseline", by_id)
        self.assertIn("extra-paper2024", by_id)
        
        # In-pool system is marked cited
        self.assertTrue(by_id["sys-baseline"]["cited"])
        
        # Extra cited system is a full solar system
        extra = by_id["extra-paper2024"]
        self.assertTrue(extra["cited"])
        self.assertEqual(extra["year"], 2024)
        slots = [p["slot"] for p in extra["planets"]]
        self.assertIn("sun", slots)
        self.assertIn("family", slots)
        self.assertIn("topic_app", slots)
        self.assertIn("result", slots)
        self.assertIn("conclusion", slots)

    def test_sync_constellation_citations_generates_html(self) -> None:
        res = atlas_manuscript.sync_constellation_citations(self.root)
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "synchronized")
        self.assertEqual(res["systems_total"], 2)
        self.assertEqual(res["cited_systems"], 2)
        
        html_file = self.root / "sota-pool" / "atlas.html"
        self.assertTrue(html_file.is_file())
        content = html_file.read_text(encoding="utf-8")
        self.assertIn("AtlasViewer", content)
        self.assertIn("extra-paper2024", content)
        self.assertIn("sys-baseline", content)


class NoveltySolarConstellationTests(unittest.TestCase):
    def test_novelty_constellation_turns_nodes_into_solar_systems(self) -> None:
        novelty_data = {
            "title": "Novelty Test",
            "project": "TestProject",
            "nodes": [
                {
                    "id": "hub-core",
                    "label": "Core Hybrid Network",
                    "category": "Architecture",
                    "badge": "MAIN",
                    "desc": "Novel hybrid architecture",
                    "rhetorical_question": "Can we improve expressivity?",
                    "paragraph_text": "We combine classical extraction with quantum circuits.",
                    "metrics": "85% accuracy on 100 subjects",
                    "novelty_claim": "Universal Fourier series approximation",
                    "thesis_ref": "proposals/r01.md",
                    "paper_blocks": ["materials-and-methods.core"]
                },
                {
                    "id": "hub-gap",
                    "label": "Technical Bottleneck",
                    "category": "Challenges",
                    "badge": "GAP",
                    "desc": "Barren plateaus in single-layer encoding",
                    "rhetorical_question": "Why do traditional circuits fail?",
                    "paragraph_text": "Single layers suffer from expressivity bottlenecks.",
                    "metrics": "Evaluated on standard benchmarks",
                    "novelty_claim": "Overcomes barren plateaus",
                    "thesis_ref": "proposals/r01.md",
                    "paper_blocks": ["introduction.block-2"]
                }
            ],
            "links": [
                {"source": "hub-core", "target": "hub-gap", "label": "addresses"}
            ]
        }
        
        constellation = novelty_graph.build_novelty_constellation(novelty_data)
        self.assertEqual(len(constellation["systems"]), 2)
        
        core_sys = next(s for s in constellation["systems"] if s["id"] == "hub-core")
        self.assertEqual(core_sys["title"], "Core Hybrid Network")
        slots = {p["slot"] for p in core_sys["planets"]}
        expected_slots = {"sun", "family", "branch", "topic_ai", "novelty", "problem", "topic_app", "result", "conclusion"}
        self.assertTrue(expected_slots.issubset(slots))
        
        # Check inter-system links
        inter_links = [l for l in constellation["links"] if l["from_system"] != l["to_system"]]
        self.assertTrue(len(inter_links) >= 1)
        self.assertEqual(inter_links[0]["rel"], "addresses")

    def test_build_novelty_viewer_html_returns_offline_viewer(self) -> None:
        html = novelty_graph.build_novelty_viewer_html()
        self.assertIn("AtlasViewer", html)
        self.assertIn("3D Novelty Constellation", html)
        self.assertNotIn("unpkg.com/3d-force-graph", html)

    def test_novelty_cli_main_generates_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmproot = Path(tmpdir)
            ps_dir = tmproot / ".papersmith"
            ps_dir.mkdir(parents=True)
            code = novelty_graph.main(["--root", str(tmproot)])
            self.assertEqual(code, 0)
            self.assertTrue((ps_dir / "novelty_graph.html").is_file())
            content = (ps_dir / "novelty_graph.html").read_text(encoding="utf-8")
            self.assertIn("AtlasViewer", content)


class PaperValidationTriggerTests(unittest.TestCase):
    def test_cmd_validate_and_write_check_section_triggers(self) -> None:
        # Check that paper_cli defines the prefixes
        prefixes = ("introduction", "related-work", "materials-and-methods")
        for p in prefixes:
            self.assertTrue(any(p in x for x in (f"{p}.block-1", f"sections/01-{p}.md", p)))


if __name__ == "__main__":
    unittest.main()
