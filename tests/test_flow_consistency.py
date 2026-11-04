"""The paper-construction flow reads the same everywhere.

Phase 5 never passes over an unverified proof of concept, its sub-phases run in
the order the harness entrypoints state (protocol → toy set → replication →
proof of concept → its verification → timing → optional search → full
experiments → review → rehearsal and launch), the workspace board's tramos
follow that order and map onto the eleven dashboard phases, and the Archify
diagram numbers its lanes by those same phases."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from skills._core.command_center import agents_view, phase_actions, state_extractor
from skills._core.results import novelty_gate
from tests.test_phase5_review import _Status

REPO = Path(__file__).resolve().parents[1]
BUILD = REPO / "docs" / "diagrams" / "papersmith-pi-flow.build.mjs"


class Phase5NeedsTheVerifiedPocTests(_Status):
    def gate(self, gate_id: str) -> dict:
        return next(g for g in self.status()["gates"] if g["id"] == gate_id)

    def everything_but_the_verification(self) -> None:
        self.protocol()
        self.product("Poc", "AGREED.md", discussion="complete")
        self.product("Full", "Experimental_AGREED.md", discussion="complete")

    def test_phase_5_is_not_pass_over_an_unverified_poc(self) -> None:
        self.everything_but_the_verification()
        fase = self.fase5()
        self.assertEqual(fase["status"], "ACTIVE")
        self.assertIn("PoC verified (G-EXP-POC): no", fase["detail"])
        novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertEqual((self.fase5()["status"], self.fase5()["progress"]), ("PASS", 1.0))

    def test_the_next_phase_stays_locked_over_an_unverified_poc(self) -> None:
        self.everything_but_the_verification()
        scaffolding = next(f for f in self.status()["fases"] if f["stage_id"] == "scaffolding")
        self.assertFalse(scaffolding["unlocked"])
        self.assertEqual(scaffolding["blocked_by"], "Fase 5")

    def test_g_novelty_opens_only_after_phase_5_passes(self) -> None:
        self.everything_but_the_verification()
        self.assertEqual(self.gate("G-NOVELTY")["status"], "PENDING")
        novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertEqual(self.gate("G-NOVELTY")["status"], "ACTIVE")

    def test_the_progress_counts_four_checks(self) -> None:
        self.protocol()
        self.assertAlmostEqual(self.fase5()["progress"], 0.25, places=3)

    def test_the_verification_is_its_own_sub_phase_after_the_poc(self) -> None:
        names = [s["name"] for s in self.fase5()["subfases"]]
        poc = names.index("Proof of concept")
        verify = next(i for i, n in enumerate(names) if n.startswith("Proof-of-concept verification"))
        timing = next(i for i, n in enumerate(names) if n.startswith("Estimate the time"))
        self.assertEqual((verify, timing), (poc + 1, poc + 2))
        self.assertIn("G-EXP-POC", names[verify])
        self.assertEqual(self.sub("Proof-of-concept verification")["status"], "PENDING")
        self.product("Poc", "AGREED.md", discussion="complete")
        self.assertEqual(self.sub("Proof-of-concept verification")["status"], "ACTIVE")
        novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertEqual(self.sub("Proof-of-concept verification")["status"], "PASS")


class Phase4SubPhasesNameTheirStepsTests(_Status):
    def test_the_first_three_sub_phases_are_the_three_steps_in_order(self) -> None:
        fase4 = next(f for f in self.status()["fases"] if f["stage_id"] == "proposal")
        names = [s["name"] for s in fase4["subfases"][:3]]
        self.assertEqual(names, ["Step 1: Problem and pillars", "Step 2: Hypotheses", "Step 3: Mathematics"])


class BoardFollowsTheFlowTests(unittest.TestCase):
    STAGES = [stage for stage, _ in state_extractor.PIPELINE_STAGES]

    def phase_of(self, tramo: str) -> str:
        if tramo in phase_actions.STAGES:
            return tramo
        (phase,) = agents_view.TRAMO_PHASES[tramo]
        return phase

    def test_the_protocol_comes_before_the_proof_of_concept(self) -> None:
        self.assertLess(self.STAGES.index("experimental-deliberation"), self.STAGES.index("implementation"))
        self.assertLess(self.STAGES.index("implementation"), self.STAGES.index("experimental-implementation"))
        chain = [(a, b) for a, b, _ in state_extractor.PIPELINE_CHAIN]
        self.assertIn(("proposal", "experimental-deliberation"), chain)
        self.assertIn(("experimental-deliberation", "implementation"), chain)
        self.assertIn(("implementation", "experimental-implementation"), chain)

    def test_every_tramo_maps_onto_one_dashboard_phase_in_order(self) -> None:
        phases = [self.phase_of(tramo) for tramo in self.STAGES]
        collapsed = [p for i, p in enumerate(phases) if i == 0 or phases[i - 1] != p]
        self.assertEqual(collapsed, list(phase_actions.STAGES))

    def test_the_extractor_names_the_real_diagram_source(self) -> None:
        source = Path(state_extractor.__file__).read_text(encoding="utf-8")
        self.assertFalse(".archify/" in source, "state_extractor.py names a throwaway .archify/ source")
        self.assertTrue("docs/diagrams/papersmith-pi-flow.build.mjs" in source)
        self.assertTrue(BUILD.is_file())


class DiagramNumbersTheDashboardPhasesTests(unittest.TestCase):
    def lanes(self) -> list[str]:
        block = BUILD.read_text(encoding="utf-8").split("const lanes=[", 1)[1].split("].map(", 1)[0]
        return re.findall(r"\['[^']+','([^']+)'\]", block)

    def test_the_numbered_lanes_are_the_eleven_phases(self) -> None:
        numbered = [m.group(1) for label in self.lanes() if (m := re.match(r"^(\d+) · ", label))]
        self.assertEqual(numbered, [str(i) for i in range(1, len(phase_actions.STAGES) + 1)])
        for i, stage in enumerate(phase_actions.STAGES, 1):
            label = next(l for l in self.lanes() if l.startswith(f"{i} · "))
            with self.subTest(stage=stage):
                self.assertIn(phase_actions.PHASE_LABELS[stage].lower(), label.lower())

    def test_sub_lanes_hang_off_a_numbered_phase(self) -> None:
        for label in self.lanes():
            with self.subTest(label=label):
                self.assertRegex(label, r"^\d+[a-z]? · ")

    def test_the_two_phase_5_gates_are_drawn(self) -> None:
        text = BUILD.read_text(encoding="utf-8")
        for gate in ("'G-EXP-POC'", "'G-NOVELTY'"):
            self.assertIn(gate, text)


class DocsStateTheSameFlowTests(unittest.TestCase):
    def test_the_readme_names_revisions_with_their_slug(self) -> None:
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("research-concept-rNN", readme)
        self.assertIn("research-concept-<slug>-rNN.md", readme)

    def test_the_diagram_readme_no_longer_counts_twelve_tramos(self) -> None:
        text = (REPO / "docs" / "diagrams" / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("twelve", text)
        self.assertIn("eleven", text)

    def test_phase_5_reads_in_one_order_everywhere(self) -> None:
        needles = ("/experimental-deliberation", "/datasets", "replication", "/proposal-implementation",
                   "G-EXP-POC", "timing", "/hyperparameter-search", "/experimental-implementation")
        sources = {
            "CLAUDE.md": (REPO / "CLAUDE.md").read_text(encoding="utf-8"),
            "paper-flow.md.tpl": (REPO / "src/papersmith/templates/paper-flow.md.tpl").read_text(encoding="utf-8"),
        }
        for name, text in sources.items():
            phase5 = text[text.index("5. **"):text.index("6. **")]
            head = phase5.split("   - ", 1)[0]
            with self.subTest(source=name):
                positions = [head.find(n) for n in needles]
                self.assertNotIn(-1, positions, dict(zip(needles, positions)))
                self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
