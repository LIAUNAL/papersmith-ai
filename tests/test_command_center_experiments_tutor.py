"""The experiments tutor: a read-only skill and agent whose doctrine covers the
experiment decisions the operator asked to consult and iterate on, and which
hands every change of decision to `/experimental-deliberation`."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "experiments-tutor" / "SKILL.md"
AGENT = ROOT / ".claude" / "agents" / "experiments-tutor.md"

#: The decision areas, by the id the turn's `decision_area` carries.
AREAS = ("architecture", "hyperparameters", "ablation", "significance", "toy-set", "training",
         "ceilings", "baselines", "validation", "compute", "reproducibility")


def flat(text: str) -> str:
    return " ".join(text.split())


class DoctrineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = flat(SKILL.read_text(encoding="utf-8"))
        self.agent = AGENT.read_text(encoding="utf-8")

    def test_the_agent_reads_and_never_writes_or_runs(self) -> None:
        tools = re.search(r"^tools:\s*(.+)$", self.agent, re.MULTILINE).group(1)
        self.assertEqual([t.strip() for t in tools.split(",")], ["Read", "Glob", "Grep"])
        self.assertIn("skills/experiments-tutor/SKILL.md", self.agent)

    def test_every_decision_area_is_in_the_doctrine(self) -> None:
        for area in AREAS + ("general",):
            self.assertIn(f"`{area}`", self.skill, area)
        for topic in ("network architecture", "hyperparameter search", "ablation",
                      "statistical significance", "toy set", "training strateg", "ceiling",
                      "oracle", "baseline", "leakage", "compute budget", "reproducib"):
            self.assertIn(topic, self.skill.lower(), topic)

    def test_numbers_are_never_invented_and_secrets_never_read(self) -> None:
        self.assertIn("nothing measured yet", self.skill)
        for secret in (".papersmith/team.json", ".remote-execution", "credential"):
            self.assertIn(secret, self.skill)

    def test_a_change_of_decision_goes_to_the_deliberation(self) -> None:
        self.assertIn("/experimental-deliberation", self.skill)
        self.assertIn("deliberation_prompt", self.skill)
        self.assertIn("delegates to the `experiments-tutor` agent", self.skill)


if __name__ == "__main__":
    unittest.main()
