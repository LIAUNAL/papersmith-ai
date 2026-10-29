"""The Flujo Archify pane lists every agent the workspace ships: its role, its
bound skill, its stretch, its tools, the phase(s) it acts in and the harnesses
it is projected to. Read from `.claude/agents/*.md`, never from a hand list."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import agents_view, phase_actions, server
from skills._core.command_center.state_extractor import AGENT_STAGES

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "skills" / "_core" / "command_center" / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
SHIPPED = sorted(p.stem for p in (REPO / ".claude" / "agents").glob("*.md"))


def _routes(app) -> dict:
    return {route.path: route.endpoint for route in app.routes
            if hasattr(route, "path") and hasattr(route, "endpoint")}


class AgentsViewTests(unittest.TestCase):
    def test_the_view_lists_exactly_the_shipped_agents(self) -> None:
        view = agents_view.get_agents_view(REPO)
        self.assertEqual([a["name"] for a in view["agents"]], SHIPPED)
        self.assertEqual(view["warnings"], [])

    def test_every_agent_has_role_skill_tools_and_at_least_one_phase(self) -> None:
        for agent in agents_view.get_agents_view(REPO)["agents"]:
            with self.subTest(agent=agent["name"]):
                self.assertTrue(agent["role"])
                self.assertTrue(agent["description"].startswith(agent["role"].rstrip(".")[:20]))
                self.assertTrue((REPO / "skills" / agent["skill"] / "SKILL.md").is_file())
                self.assertTrue(agent["tools"])
                self.assertEqual(agent["tramo"], AGENT_STAGES[agent["name"]])
                self.assertTrue(agent["phases"])
                for phase in agent["phases"]:
                    self.assertRegex(phase, r"^(?:Phase|Fase) \d+ — \S")
                self.assertIn(".claude/agents", agent["harnesses"])

    def test_phases_follow_the_dashboard_numbering(self) -> None:
        by_name = {a["name"]: a for a in agents_view.get_agents_view(REPO)["agents"]}
        number = lambda name: [int(re.match(r"(?:Phase|Fase) (\d+)", p).group(1)) for p in by_name[name]["phases"]]
        self.assertEqual(number("sota-scout"), [2])
        self.assertEqual(number("paper-ingestion"), [3])
        self.assertEqual(number("math-tutor"), [4])
        self.assertEqual(number("experiments-tutor"), [5])
        self.assertEqual(number("paper-replicator"), [5])
        self.assertEqual(number("dataset-scout"), [5])
        self.assertEqual(number("dataset-curator"), [5])
        self.assertEqual(number("experiments-walk"), [5])
        self.assertEqual(number("insumos-observer"), [7, 8])
        self.assertEqual(number("redactor"), [8])
        self.assertEqual(number("diagram-author"), [9])
        self.assertEqual(number("audit-report"), [11])
        label = phase_actions.PHASE_LABELS["poc_experiments"]
        self.assertEqual(by_name["paper-replicator"]["phases"], [f"Phase 5 — {label}"])
        self.assertEqual(by_name["paper-replicator"]["skill"], "proposal-implementation")
        self.assertEqual(by_name["paper-replicator"]["stretch"], "fidelity")

    def test_phase_labels_cover_every_stage(self) -> None:
        self.assertEqual(tuple(phase_actions.PHASE_LABELS), phase_actions.STAGES)

    def test_harnesses_name_the_projections_that_exist(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        (root / ".claude" / "agents").mkdir(parents=True)
        (root / ".pi" / "agents").mkdir(parents=True)
        src = REPO / ".claude" / "agents" / "redactor.md"
        shutil.copy(src, root / ".claude" / "agents" / "redactor.md")
        shutil.copy(src, root / ".pi" / "agents" / "redactor.md")
        view = agents_view.get_agents_view(root)
        self.assertEqual(view["agents"][0]["harnesses"], [".claude/agents", ".pi/agents"])

    def test_a_broken_workspace_never_raises(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        self.assertEqual(agents_view.get_agents_view(root)["agents"], [])
        self.assertTrue(agents_view.get_agents_view(root)["warnings"])
        (root / ".claude" / "agents").mkdir(parents=True)
        (root / ".claude" / "agents" / "mystery.md").write_bytes(b"\xff\xfe no frontmatter")
        view = agents_view.get_agents_view(root)
        self.assertEqual([a["name"] for a in view["agents"]], ["mystery"])
        self.assertEqual(view["agents"][0]["phases"], [])
        self.assertTrue(view["warnings"])

    def test_the_route_returns_the_view(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        (root / ".claude").mkdir()
        shutil.copytree(REPO / ".claude" / "agents", root / ".claude" / "agents")
        app = server.create_app(root, history_store=None)
        payload = json.loads(bytes(_routes(app)["/api/agents"]().body))
        self.assertEqual([a["name"] for a in payload["agents"]], SHIPPED)


class AgentsPanelTests(unittest.TestCase):
    def test_the_page_loads_the_script_and_holds_the_table_inside_the_flow_pane(self) -> None:
        self.assertIn('<script src="./agents-panel.js?v=', PAGE)
        head = PAGE[:PAGE.index("</head>")]
        self.assertIn("agents-panel.js", head)
        start = PAGE.index('<div id="pane-flow"')
        pane = PAGE[start:PAGE.index('<div id="pane-modelo"')]
        self.assertIn('id="flowIframe"', pane)
        self.assertIn('id="agentsPanel"', pane)
        self.assertTrue("Agentes del proyecto smith" in pane or "Agents of the smith project" in pane)
        self.assertLess(pane.index('id="flowIframe"'), pane.index('id="agentsPanel"'))

    def test_showing_the_flow_tab_refreshes_the_table(self) -> None:
        body = PAGE[PAGE.index("function navigateTab"):]
        self.assertIn("refreshAgentsPanel", body[:body.index("function filterModelView")])

    def render(self, agents: list[dict]) -> str:
        i18n_js = STATIC / "i18n.js"
        en_js = STATIC / "i18n" / "en.js"
        es_js = STATIC / "i18n" / "es.js"
        script = (
            "const fs=require('fs');const els={};"
            "global.window={localStorage:{getItem:()=>'es',setItem:()=>{}}};"
            "global.document={addEventListener(){},"
            "getElementById:(id)=>(els[id]=els[id]||{innerHTML:'',querySelectorAll:()=>[]})};"
            f"eval(fs.readFileSync({json.dumps(str(en_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(es_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(i18n_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(STATIC / 'agents-panel.js'))},'utf8'));"
            "window.AgentsPanel.render(JSON.parse(fs.readFileSync(0,'utf8')));"
            "console.log(els.agentsPanel.innerHTML);"
        )
        return subprocess.run(["node", "-e", script], input=json.dumps({"agents": agents, "warnings": []}),
                              capture_output=True, text=True, cwd=tempfile.gettempdir(),
                              check=True).stdout

    def test_render_shows_every_column_and_escapes_hostile_text(self) -> None:
        out = self.render([{
            "name": "evil<agent>", "role": "Role <img src=x onerror=alert(1)>",
            "description": "Full \"desc\" <script>x</script>", "skill": "s<k>",
            "stretch": "st<r>", "tools": ["Read", "<b>Bash</b>"], "tramo": "writing",
            "phases": ["Fase 8 — <i>Redacción</i>"], "harnesses": [".claude/agents"],
        }])
        for header in ("Agente", "Rol", "Skill", "Etapa", "Herramientas", "Fase(s)", "Harness"):
            self.assertIn(header, out)
        for raw in ("<img", "<script>", "<agent>", "<b>Bash", "<i>Redacción", "<k>", "<r>"):
            self.assertNotIn(raw, out)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", out)
        self.assertIn("evil&lt;agent&gt;", out)
        self.assertIn("Fase 8 — &lt;i&gt;Redacción&lt;/i&gt;", out)


if __name__ == "__main__":
    unittest.main()
