"""The experiments tutor: a read-only skill and agent whose doctrine covers the
experiment decisions the operator asked to consult and iterate on, and which
hands every change of decision to `/experimental-deliberation`."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import tutor

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


class _Root(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()


SCHEMA = {"type": "object", "required": ["reply"], "properties": {"reply": {"type": "string"}}}


def _demo_valid(turn):
    if not (isinstance(turn, dict) and isinstance(turn.get("reply"), str)):
        raise tutor.TutorError("no reply")
    return {"reply": turn["reply"]}


def _profile(**changes) -> tutor.Profile:
    fields = dict(name="demo", folder=(".papersmith", "demo-tutor"),
                  doctrine=(".claude/agents/demo.md",), fallback="Demo doctrine.",
                  headless="Headless demo.", schema=SCHEMA, modes=("ask",),
                  context=lambda root: {"demo": True}, valid=_demo_valid)
    fields.update(changes)
    return tutor.Profile(**fields)


class ProfileTests(_Root):
    """The math tutor's machinery, generalized: each profile has its own thread
    folder, doctrine, schema and lock, and the math profile is the default."""

    def test_the_math_profile_is_the_default_and_keeps_its_folder(self) -> None:
        self.assertEqual(tutor.MATH.folder, (".papersmith", "math-tutor"))
        self.assertIs(tutor.MATH.schema, tutor.TURN_SCHEMA)
        self.assertEqual(tutor.MATH.modes, tutor.MODES)
        self.assertEqual(tutor.folder(self.root), tutor.folder(self.root, tutor.MATH))

    def test_a_profile_keeps_its_own_thread_beside_the_math_one(self) -> None:
        demo = _profile()
        seen = {}

        def fake(root, system, prompt, images):
            seen.update(system=system, prompt=prompt)
            return {"reply": "hi"}, "fake"

        turn = tutor.converse(demo, self.root, {"mode": "ask", "message": "m"},
                              lambda thread: f"turns so far: {len(thread['turns'])}", [], fake)
        self.assertEqual((turn["reply"], turn["agent"]), ("hi", "fake"))
        self.assertEqual(seen["prompt"], "turns so far: 0")
        self.assertIn("Demo doctrine.", seen["system"])
        self.assertIn("Headless demo.", seen["system"])
        saved = json.loads((self.root / ".papersmith/demo-tutor/thread.json").read_text())
        self.assertEqual([t["role"] for t in saved["turns"]], ["reader", "tutor"])
        self.assertEqual(saved["turns"][0]["message"], "m")
        self.assertEqual(tutor.load_thread(self.root)["turns"], [])
        tutor.reset_thread(self.root, demo)
        self.assertEqual(tutor.load_thread(self.root, demo)["turns"], [])

    def test_each_profile_has_its_own_lock(self) -> None:
        self.assertIsNot(_profile().lock, _profile().lock)
        self.assertIsNot(_profile().lock, tutor.MATH.lock)

    def test_the_claude_command_carries_the_profiles_schema(self) -> None:
        argv = tutor.claude_argv("/bin/claude", "S", "P", SCHEMA, ("Read", "Glob", "Grep"))
        self.assertEqual(json.loads(argv[argv.index("--json-schema") + 1]), SCHEMA)
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Glob,Grep")
        self.assertEqual(argv[argv.index("--allowedTools") + 1], "Read,Glob,Grep")
        self.assertEqual(tutor.MATH.tools, ("Read",))
        self.assertEqual(tutor.claude_argv("/bin/claude", "S", "P"),
                         tutor.claude_argv("/bin/claude", "S", "P", tutor.TURN_SCHEMA))


if __name__ == "__main__":
    unittest.main()
