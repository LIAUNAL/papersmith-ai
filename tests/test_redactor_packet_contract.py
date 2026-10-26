"""The redactor's input count is stated once, by the redactor agent (#70).

`paper-writing/SKILL.md` once said the orchestrator assembles "four" redactor
inputs while the agent (and every harness projection of it) takes five. The
count is read from the canonical agent's own description; any other place
that restates a redactor input count must agree with it.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / ".claude" / "agents" / "redactor.md"
PROJECTIONS = [ROOT / ".agents" / "agents" / "redactor.md",
               ROOT / ".opencode" / "agents" / "redactor.md"]
SKILL = ROOT / "skills" / "paper-writing" / "SKILL.md"
WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten".split())}
ORDINALS = {w: i for i, w in enumerate(
    "zeroth first second third fourth fifth sixth seventh eighth".split())}
COUNT = re.compile(r"\b(" + "|".join(WORDS) + r")\s+(?:redactor\s+)?inputs\b",
                   re.IGNORECASE)


def declared_count() -> int:
    match = re.search(r"exactly (\w+) inputs", AGENT.read_text(encoding="utf-8"))
    assert match, "the redactor agent declares no input count"
    return WORDS[match.group(1).lower()]


def counts_in(text: str) -> set[int]:
    return {WORDS[m.group(1).lower()] for m in COUNT.finditer(text)}


class RedactorPacketContractTest(unittest.TestCase):
    def test_redactor_packet_contract_matches_agent_inputs(self) -> None:
        n = declared_count()
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("redactor", skill)
        self.assertEqual(sorted(counts_in(skill) - {n}), [],
                         "paper-writing/SKILL.md restates a redactor input "
                         f"count other than the agent's {n}")

    def test_every_redactor_projection_declares_the_canonical_count(self) -> None:
        n = declared_count()
        for path in [AGENT, *PROJECTIONS]:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertEqual(counts_in(text), {n})
                beyond = {ORDINALS[w.lower()] for w in re.findall(
                    r"\b(\w+) input\b", text) if w.lower() in ORDINALS}
                self.assertEqual(beyond, {n + 1},
                                 "the prohibition names the input past the last")


if __name__ == "__main__":
    unittest.main()
