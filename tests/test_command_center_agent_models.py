"""The model every smith agent runs on, per harness, and the alerts about it.

``agent_models`` answers, for each agent and each harness the workspace
projects it to (Claude Code, OpenCode, Pi, Antigravity), whether the agent is
pinned to a model there or inherits the harness session's model, and which
model that is when a config file says so. A judge that is not confirmed on a
top-tier model gets a warning; every inheriting agent gets a note; each alert
says how to pin another model in that harness in a way `smith upgrade` keeps.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import agent_models, agents_view

REPO = Path(__file__).resolve().parents[1]

PROJECTION = {"claude": ".claude/agents", "opencode": ".opencode/agents",
              "pi": ".pi/agents", "antigravity": ".agents/agents"}


def _agent(root: Path, name: str, model: str = "", harnesses=("claude",)) -> None:
    for harness in harnesses:
        folder = root / PROJECTION[harness]
        folder.mkdir(parents=True, exist_ok=True)
        line = f"model: {model}\n" if model and harness == "claude" else ""
        (folder / f"{name}.md").write_text(
            f'---\nname: {name}\ndescription: "Does {name}. More."\ntools: Read\n{line}---\nbody\n',
            encoding="utf-8")


def _json(path: Path, data, raw: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw if raw is not None else json.dumps(data), encoding="utf-8")


class Workspace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.root = base / "ws"
        self.home = base / "home"
        self.root.mkdir()
        self.home.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def resolve(self) -> dict:
        return agent_models.resolve_workspace(self.root, home=self.home, env={})

    def entry(self, payload: dict, name: str, harness: str) -> dict:
        agent = next(a for a in payload["agents"] if a["name"] == name)
        return next(e for e in agent["models"] if e["harness"] == harness)

    def alerts(self, payload: dict, name: str) -> list[dict]:
        return next(a for a in payload["agents"] if a["name"] == name)["alerts"]


class ClaudeResolutionTests(Workspace):
    def test_a_frontmatter_model_is_pinned(self) -> None:
        _agent(self.root, "contract-auditor", "opus")
        entry = self.entry(self.resolve(), "contract-auditor", "claude")
        self.assertEqual(entry["status"], "pinned")
        self.assertEqual(entry["model"], "opus")
        self.assertEqual(entry["source"], ".claude/agents/contract-auditor.md")

    def test_model_inherit_is_not_a_pin(self) -> None:
        _agent(self.root, "redactor", "inherit")
        self.assertEqual(self.entry(self.resolve(), "redactor", "claude")["status"], "inherits")

    def test_an_inheriting_agent_names_the_session_model_local_over_project_over_user(self) -> None:
        _agent(self.root, "redactor")
        _json(self.home / ".claude" / "settings.json", {"model": "haiku"})
        entry = self.entry(self.resolve(), "redactor", "claude")
        self.assertEqual((entry["status"], entry["model"], entry["source"]),
                         ("inherits", "haiku", "~/.claude/settings.json"))
        _json(self.root / ".claude" / "settings.json", {"model": "sonnet"})
        self.assertEqual(self.entry(self.resolve(), "redactor", "claude")["model"], "sonnet")
        _json(self.root / ".claude" / "settings.local.json", {"model": "opus"})
        entry = self.entry(self.resolve(), "redactor", "claude")
        self.assertEqual((entry["model"], entry["source"]), ("opus", ".claude/settings.local.json"))

    def test_an_unknown_session_model_says_how_to_see_it(self) -> None:
        _agent(self.root, "redactor")
        entry = self.entry(self.resolve(), "redactor", "claude")
        self.assertEqual(entry["status"], "inherits")
        self.assertIsNone(entry["model"])
        self.assertIsNone(entry["source"])
        self.assertIn("/model", entry["how_to_see"])

    def test_the_subagent_variable_reaches_inheriting_agents_and_force_reaches_pinned_ones(self) -> None:
        _agent(self.root, "redactor")
        _agent(self.root, "contract-auditor", "opus")
        _json(self.root / ".claude" / "settings.local.json",
              {"model": "opus", "env": {"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"}})
        payload = self.resolve()
        self.assertEqual(self.entry(payload, "redactor", "claude")["model"], "sonnet")
        self.assertEqual(self.entry(payload, "contract-auditor", "claude")["model"], "opus")
        _json(self.root / ".claude" / "settings.local.json",
              {"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1"}})
        entry = self.entry(self.resolve(), "contract-auditor", "claude")
        self.assertEqual((entry["status"], entry["model"]), ("pinned", "sonnet"))
        self.assertIn("CLAUDE_CODE_SUBAGENT_MODEL_FORCE", entry["source"])

    def test_credentials_in_a_settings_file_never_reach_the_payload(self) -> None:
        _agent(self.root, "redactor", harnesses=("claude", "opencode", "pi"))
        secret = "sk-ant-SECRET-never-shown"
        _json(self.root / ".claude" / "settings.local.json",
              {"model": "opus", "apiKeyHelper": secret, "env": {"ANTHROPIC_API_KEY": secret}})
        _json(self.root / "opencode.json", {"model": "a/b", "provider": {"a": {"options": {"apiKey": secret}}}})
        _json(self.root / ".pi" / "settings.json", {"defaultModel": "m", "apiKey": secret})
        self.assertNotIn(secret, json.dumps(self.resolve()))


class OtherHarnessResolutionTests(Workspace):
    def test_opencode_inherits_the_closest_config_model(self) -> None:
        _agent(self.root, "redactor", harnesses=("claude", "opencode"))
        self.assertIsNone(self.entry(self.resolve(), "redactor", "opencode")["model"])
        _json(self.home / ".config" / "opencode" / "opencode.json", {"model": "openai/gpt-x"})
        entry = self.entry(self.resolve(), "redactor", "opencode")
        self.assertEqual((entry["status"], entry["model"], entry["source"]),
                         ("inherits", "openai/gpt-x", "~/.config/opencode/opencode.json"))
        _json(self.root / "opencode.json", {"model": "anthropic/claude-sonnet-5-5"})
        self.assertEqual(self.entry(self.resolve(), "redactor", "opencode")["model"],
                         "anthropic/claude-sonnet-5-5")
        _json(self.root / ".opencode" / "opencode.jsonc", None,
              raw='{\n  // the team default\n  "model": "anthropic/claude-opus-5-5", /* pinned */\n}\n')
        entry = self.entry(self.resolve(), "redactor", "opencode")
        self.assertEqual((entry["model"], entry["source"]),
                         ("anthropic/claude-opus-5-5", ".opencode/opencode.jsonc"))

    def test_pi_override_pins_and_defaults_are_inherited_project_first(self) -> None:
        _agent(self.root, "redactor", harnesses=("claude", "pi"))
        _agent(self.root, "contract-auditor", "opus", harnesses=("claude", "pi"))
        _json(self.home / ".pi" / "agent" / "settings.json",
              {"defaultProvider": "anthropic", "defaultModel": "claude-sonnet-5-5"})
        entry = self.entry(self.resolve(), "redactor", "pi")
        self.assertEqual((entry["status"], entry["model"], entry["source"]),
                         ("inherits", "anthropic/claude-sonnet-5-5", "~/.pi/agent/settings.json"))
        _json(self.root / ".pi" / "settings.json",
              {"packages": [], "subagents": {"defaultModel": "openai/gpt-x",
                                             "agentOverrides": {"contract-auditor": {"model": "anthropic/claude-opus-5-5"}}}})
        payload = self.resolve()
        self.assertEqual(self.entry(payload, "redactor", "pi")["model"], "openai/gpt-x")
        judge = self.entry(payload, "contract-auditor", "pi")
        self.assertEqual((judge["status"], judge["model"], judge["source"]),
                         ("pinned", "anthropic/claude-opus-5-5", ".pi/settings.json"))

    def test_pi_agent_dir_follows_its_variable(self) -> None:
        _agent(self.root, "redactor", harnesses=("claude", "pi"))
        custom = self.home / "elsewhere"
        _json(custom / "settings.json", {"defaultModel": "anthropic/claude-haiku"})
        payload = agent_models.resolve_workspace(self.root, home=self.home,
                                                 env={"PI_CODING_AGENT_DIR": str(custom)})
        self.assertEqual(self.entry(payload, "redactor", "pi")["model"], "anthropic/claude-haiku")

    def test_antigravity_always_inherits_an_unreadable_session_model(self) -> None:
        _agent(self.root, "redactor", harnesses=("claude", "antigravity"))
        entry = self.entry(self.resolve(), "redactor", "antigravity")
        self.assertEqual((entry["status"], entry["model"]), ("inherits", None))
        self.assertIn("agy models", entry["how_to_see"])

    def test_only_the_harnesses_the_agent_is_projected_to_are_listed(self) -> None:
        _agent(self.root, "redactor", harnesses=("claude", "pi"))
        agent = self.resolve()["agents"][0]
        self.assertEqual([e["harness"] for e in agent["models"]], ["claude", "pi"])


class AlertTests(Workspace):
    def test_the_judge_set_matches_the_pinned_judges(self) -> None:
        from tests.test_agents import JUDGE_AGENTS
        self.assertEqual(agent_models.JUDGES, frozenset(JUDGE_AGENTS))

    def test_a_judge_on_opus_has_no_alert_and_one_that_inherits_an_unknown_model_is_warned(self) -> None:
        _agent(self.root, "paper-reviewer", "opus", harnesses=("claude", "opencode"))
        alerts = self.alerts(self.resolve(), "paper-reviewer")
        self.assertEqual([a["harness"] for a in alerts if a["level"] == "warning"], ["opencode"])
        warning = next(a for a in alerts if a["level"] == "warning")
        self.assertIn("paper-reviewer is a judge", warning["message"])
        self.assertIn("not confirmed as a top-tier model", warning["message"])
        self.assertTrue(warning["suggestion"])

    def test_a_judge_inheriting_a_strong_model_is_not_warned(self) -> None:
        _agent(self.root, "ai-auditor", "opus", harnesses=("claude", "opencode"))
        _json(self.root / "opencode.json", {"model": "anthropic/claude-opus-5-5"})
        alerts = self.alerts(self.resolve(), "ai-auditor")
        self.assertEqual([a["level"] for a in alerts], ["info"])
        self.assertIn("inherits anthropic/claude-opus-5-5", alerts[0]["message"])

    def test_a_judge_forced_onto_a_lighter_model_in_claude_is_warned(self) -> None:
        _agent(self.root, "contract-auditor", "opus")
        _json(self.root / ".claude" / "settings.local.json",
              {"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1"}})
        alerts = self.alerts(self.resolve(), "contract-auditor")
        self.assertEqual([(a["level"], a["harness"]) for a in alerts], [("warning", "claude")])
        self.assertIn("runs on sonnet", alerts[0]["message"])

    def test_every_inheriting_agent_gets_a_note_naming_its_model(self) -> None:
        _agent(self.root, "redactor", harnesses=("claude", "antigravity"))
        _agent(self.root, "math-tutor", "sonnet")
        _json(self.home / ".claude" / "settings.json", {"model": "opus"})
        payload = self.resolve()
        notes = self.alerts(payload, "redactor")
        self.assertEqual([(a["level"], a["harness"]) for a in notes], [("info", "claude"), ("info", "antigravity")])
        self.assertIn("inherits opus (~/.claude/settings.json)", notes[0]["message"])
        self.assertIn("inherits the session's model", notes[1]["message"])
        self.assertEqual(self.alerts(payload, "math-tutor"), [], "a pinned light agent needs no alert")

    def test_strong_models_are_the_top_tier_ones(self) -> None:
        for model in ("opus", "best", "fable", "opus[1m]", "claude-opus-5-5", "anthropic/claude-opus-5-5",
                      "Claude Opus 5.5 (thinking)"):
            self.assertTrue(agent_models.is_strong(model), model)
        for model in (None, "", "sonnet", "haiku", "opusplan", "openai/gpt-x", "Gemini 4 Neon"):
            self.assertFalse(agent_models.is_strong(model), model)


class SuggestionTests(unittest.TestCase):
    def test_each_harness_names_a_mechanism_that_survives_an_upgrade_or_says_there_is_none(self) -> None:
        claude = agent_models.suggestion("claude", "paper-reviewer")
        self.assertIn("`smith upgrade` rewrites `.claude/agents/paper-reviewer.md`", claude)
        self.assertIn("CLAUDE_CODE_SUBAGENT_MODEL", claude)
        self.assertIn("CLAUDE_CODE_SUBAGENT_MODEL_FORCE", claude)
        self.assertIn(".claude/settings.local.json", claude)
        opencode = agent_models.suggestion("opencode", "paper-reviewer")
        self.assertIn("no documented per-agent pin that survives `smith upgrade`", opencode)
        self.assertIn("~/.config/opencode/opencode.json", opencode)
        pi = agent_models.suggestion("pi", "paper-reviewer")
        self.assertIn("`subagents.agentOverrides.paper-reviewer.model`", pi)
        self.assertIn(".pi/settings.json", pi)
        self.assertIn("pi-subagents", pi)
        agy = agent_models.suggestion("antigravity", "paper-reviewer")
        self.assertIn("no per-agent pin that survives `smith upgrade`", agy)
        self.assertIn("agy models", agy)
        self.assertIn("/model", agy)


class TerminalTests(Workspace):
    def run_main(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = agent_models.main([str(self.root), *args], home=self.home, env={})
        return code, out.getvalue()

    def test_the_report_lists_each_agent_per_harness_with_its_alerts(self) -> None:
        _agent(self.root, "paper-reviewer", "opus", harnesses=("claude", "pi"))
        code, text = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("paper-reviewer", text)
        self.assertIn("claude: opus (pinned, .claude/agents/paper-reviewer.md)", text)
        self.assertIn("pi: inherits the session's model", text)
        self.assertIn("WARNING", text)
        self.assertIn("subagents.agentOverrides.paper-reviewer.model", text)

    def test_json_prints_the_payload(self) -> None:
        _agent(self.root, "redactor")
        code, text = self.run_main("--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["agents"][0]["name"], "redactor")

    def test_a_workspace_without_agents_says_so(self) -> None:
        code, text = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("no .claude/agents/", text)


class ViewPayloadTests(Workspace):
    def test_the_agents_view_carries_models_and_alerts(self) -> None:
        _agent(self.root, "paper-reviewer", "opus", harnesses=("claude", "opencode"))
        view = agents_view.get_agents_view(self.root, home=self.home, env={})
        agent = view["agents"][0]
        self.assertEqual(agent["model"], "opus")
        self.assertEqual([e["harness"] for e in agent["models"]], ["claude", "opencode"])
        self.assertEqual([a["level"] for a in agent["model_alerts"]], ["warning", "info"])

    def test_the_shipped_judges_are_pinned_to_opus_in_claude(self) -> None:
        view = agents_view.get_agents_view(REPO, home=Path(self._tmp.name), env={})
        by_name = {a["name"]: a for a in view["agents"]}
        for name in agent_models.JUDGES:
            claude = next(e for e in by_name[name]["models"] if e["harness"] == "claude")
            self.assertEqual((claude["status"], claude["model"]), ("pinned", "opus"), name)
            self.assertFalse([a for a in by_name[name]["model_alerts"]
                              if a["level"] == "warning" and a["harness"] == "claude"])


if __name__ == "__main__":
    unittest.main()
