"""The Agents Office state: one measured snapshot of the smith agents at work.

The office never invents: an agent's model is `None` unless something measured
it, an unavailable piece reports why, and the Engram memory ring only holds
command lines actually observed in live terminal output.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "command_center"))
import office  # noqa: E402


CATALOG = [
    {"id": "herdr", "label": "Herdr", "desc": "the orchestrator's own terminal", "available": True},
    {"id": "claude", "label": "Claude Code", "desc": "Anthropic's coding CLI", "available": True},
    {"id": "shell", "label": "Shell", "desc": "a login shell", "available": True},
    {"id": "antigravity", "label": "Antigravity", "desc": "", "available": False},
]

SESSIONS = {
    "s1": {"agent": "claude", "alive": True},
    "s2": {"agent": "shell", "alive": False},
}


class RosterTests(unittest.TestCase):

    def test_every_catalog_agent_gets_a_desk(self) -> None:
        roster = office.agent_roster(CATALOG, SESSIONS)
        self.assertEqual([a["id"] for a in roster], ["herdr", "claude", "shell", "antigravity"])

    def test_role_is_the_agent_description_and_never_invented(self) -> None:
        roster = office.agent_roster(CATALOG, SESSIONS)
        by_id = {a["id"]: a for a in roster}
        self.assertEqual(by_id["claude"]["role"], "Anthropic's coding CLI")
        self.assertEqual(by_id["antigravity"]["role"], "")

    def test_model_is_none_until_something_measures_it(self) -> None:
        for agent in office.agent_roster(CATALOG, SESSIONS):
            self.assertIsNone(agent["model"], agent["id"])

    def test_a_live_session_attaches_and_a_dead_one_reports(self) -> None:
        by_id = {a["id"]: a for a in office.agent_roster(CATALOG, SESSIONS)}
        self.assertEqual(by_id["claude"]["session"], {"id": "s1", "alive": True})
        self.assertEqual(by_id["shell"]["session"], {"id": "s2", "alive": False})
        self.assertIsNone(by_id["herdr"]["session"])

    def test_one_agent_is_not_two_desks(self) -> None:
        roster = office.agent_roster(CATALOG, {"a": {"agent": "claude", "alive": True},
                                               "b": {"agent": "claude", "alive": False}})
        claude = [a for a in roster if a["id"] == "claude"]
        self.assertEqual(len(claude), 1)
        self.assertTrue(claude[0]["session"]["alive"] or claude[0]["session"]["id"] == "a")


class MemoryDetectionTests(unittest.TestCase):

    def test_a_mem_command_in_the_tail_is_detected(self) -> None:
        tail = "user@host:~$ mem_search \"herdr agents\"\n42 results\n"
        self.assertEqual(office.detect_memory_interaction(tail),
                         'mem_search "herdr agents"')

    def test_an_engram_command_is_detected_case_insensitively(self) -> None:
        self.assertEqual(office.detect_memory_interaction("$ Engram search x"),
                         "Engram search x")

    def test_plain_output_is_not_memory(self) -> None:
        self.assertIsNone(office.detect_memory_interaction("pdflatex main.tex\nOutput written"))
        self.assertIsNone(office.detect_memory_interaction("member list"))

    def test_the_last_match_wins(self) -> None:
        tail = "mem_save one\nmem_search two\n"
        self.assertEqual(office.detect_memory_interaction(tail), "mem_search two")

    def test_the_ring_is_bounded(self) -> None:
        ring: list = []
        for i in range(office.MEMORY_EVENTS_MAX + 5):
            office.memory_ring_push(ring, {"line": f"mem_save {i}", "at": i})
        self.assertEqual(len(ring), office.MEMORY_EVENTS_MAX)
        self.assertEqual(ring[-1]["line"], f"mem_save {office.MEMORY_EVENTS_MAX + 4}")


class StateTests(unittest.TestCase):

    def test_disabled_terminal_answers_honestly(self) -> None:
        state = office.office_state(catalog=CATALOG, session_facts=[], ring=[],
                                    engram_path=None, enabled=False, authorized=False)
        self.assertFalse(state["enabled"])
        self.assertFalse(state["orchestrator"]["present"])
        self.assertEqual(state["agents"], [])
        self.assertEqual(state["memory"]["interactions"], [])

    def test_unauthorized_keeps_the_roster_private_but_measures_the_host(self) -> None:
        state = office.office_state(catalog=CATALOG, session_facts=[], ring=[],
                                    engram_path="/usr/bin/engram", enabled=True,
                                    authorized=False)
        self.assertTrue(state["enabled"])
        self.assertFalse(state["authorized"])
        self.assertEqual(state["agents"], [])
        self.assertEqual(state["memory"]["engram_path"], "/usr/bin/engram")

    def test_authorized_state_carries_desks_sessions_and_memory(self) -> None:
        state = office.office_state(
            catalog=CATALOG,
            session_facts=[{"agent": "claude", "alive": True, "tail": "$ mem_search x\n"}],
            ring=[], engram_path="/usr/bin/engram", enabled=True, authorized=True)
        self.assertTrue(state["orchestrator"]["present"])
        self.assertEqual(len(state["agents"]), 4)
        by_id = {a["id"]: a for a in state["agents"]}
        self.assertEqual(by_id["claude"]["session"]["alive"], True)
        self.assertEqual(state["memory"]["engram_path"], "/usr/bin/engram")
        self.assertEqual(state["memory"]["interactions"], [])
        self.assertIn("generated_at", state)

    def test_observed_memory_lines_enter_the_ring(self) -> None:
        ring: list = []
        office.observe_memory(ring, [
            {"agent": "claude", "alive": True, "tail": "$ mem_search herdr\n"},
            {"agent": "shell", "alive": True, "tail": "ls\n"},
        ])
        self.assertEqual(len(ring), 1)
        self.assertEqual(ring[0]["agent"], "claude")
        self.assertIn("mem_search", ring[0]["line"])
        self.assertIn("at", ring[0])


class WiringTests(unittest.TestCase):
    """The dashboard serves the office and the page mounts it."""

    def test_the_server_route_exists_and_is_measured(self) -> None:
        source = (FORGE_ROOT / "skills" / "_core" / "command_center" / "server.py").read_text()
        self.assertIn('"/api/office/state"', source)
        self.assertIn("office.office_state", source)

    def test_the_manager_can_report_session_facts(self) -> None:
        source = (FORGE_ROOT / "skills" / "_core" / "command_center" / "terminal.py").read_text()
        self.assertIn("def session_facts", source)

    def test_the_page_mounts_the_office_panel(self) -> None:
        page = (FORGE_ROOT / "skills" / "_core" / "command_center" / "static" / "index.html").read_text()
        self.assertIn("navigateTab('office')", page)
        self.assertIn('id="pane-office"', page)
        self.assertIn("office-panel.js?v=", page)
        self.assertIn('id="officeCanvas"', page)

    def test_the_panel_is_vanilla_canvas_without_a_3d_library(self) -> None:
        panel = (FORGE_ROOT / "skills" / "_core" / "command_center" / "static" / "office-panel.js").read_text()
        self.assertIn("getContext('2d')", panel)
        self.assertNotIn("three.js", panel.lower())
        self.assertNotIn("import ", panel.split("\n")[0])

    def test_the_panel_reads_state_and_phases(self) -> None:
        panel = (FORGE_ROOT / "skills" / "_core" / "command_center" / "static" / "office-panel.js").read_text()
        self.assertIn("/api/office/state", panel)
        self.assertIn("window.phaseRuns", panel)
        self.assertIn("openCliConsole", panel)


if __name__ == "__main__":
    unittest.main()
