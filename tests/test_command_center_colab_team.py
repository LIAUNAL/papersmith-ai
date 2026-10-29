"""The Experiments tab's Colab rows, team table and Colab activation box.

``remote_services.remote_services(root)`` adds Colab rows beside the Kaggle
ones (official ``colab`` CLI, the official Colab MCP registration, the team's
Colab accounts and how many of them a split campaign may use) and a team
table read from ``.papersmith/team.json``. The team registry holds owner
slugs and display names only; a member's Colab ``configDir`` is checked for
existence and never opened, and the Kaggle accounts store contributes a
yes/no per declared username, never another username. Every command the
panel offers is a server-side constant. The renderer runs under node.
"""

from __future__ import annotations

import builtins
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import experiments_view, remote_services, server, terminal

SCRIPT_PATH = Path(server.__file__).resolve().parent / "static" / "experiments-panel.js"
REMOTE_EXECUTION_DOC = Path(server.__file__).resolve().parents[2] / "remote-execution" / "SKILL.md"
SECRET = "store-secret-value"
NODE = shutil.which("node")


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class _Env(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.root = self.tmp / "ws"
        self.root.mkdir()
        env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.tmp / "config"),
               "PATH": str(self.bin)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(terminal.REMOTE_MCP_TOKEN_ENV, None)
        dirs = mock.patch.object(terminal, "TOOL_DIRS", ())
        dirs.start()
        self.addCleanup(dirs.stop)
        remote_services.clear_cache()
        self.addCleanup(remote_services.clear_cache)

    def fake_colab(self, directory: Path) -> Path:
        exe = _write(directory / "colab", "#!/bin/sh\necho 'colab 0.7.5'\n")
        exe.chmod(0o755)
        return exe

    def register_colab_mcp(self) -> None:
        _write(self.root / ".mcp.json", json.dumps({"mcpServers": {"colab": {
            "type": "stdio", "command": "uvx", "args": ["git+https://example.invalid/colab-mcp"]}}}))

    def kaggle_store(self, usernames: list[str]) -> None:
        _write(self.root / "skills" / "acc" / "scripts" / "acc_cli.py",
               'STORE_NAME = "store"\nSTORE_FILE = "accounts.json"\n')
        _write(self.root / "skills" / "acc" / "store" / "accounts.json",
               json.dumps({"version": 1, "accounts": [{"username": u, "key": SECRET} for u in usernames]}))

    def config_dir(self, owner: str, *, create: bool) -> Path:
        path = self.tmp / "config" / "papersmith" / "colab" / owner
        if create:
            _write(path / "token.json", json.dumps({"refresh_token": SECRET}))
        return path

    def team(self, members: list[dict]) -> None:
        _write(self.root / ".papersmith" / "team.json", json.dumps({"schema": 1, "members": members}))

    def standard_team(self) -> None:
        self.kaggle_store(["alice-k", "zed-hidden"])
        self.alice_dir = self.config_dir("alice", create=True)
        self.bob_dir = self.config_dir("bob", create=False)
        attest = {"attestedAt": "2026-10-25",
                  "attestation": "owns and operates exactly one account per service listed here"}
        self.team([
            {"owner": "alice", "displayName": "Alice A.", **attest, "accounts": {
                "kaggle": {"username": "alice-k"},
                "colab": {"tier": "pro", "configDir": str(self.alice_dir)}}},
            {"owner": "bob", "displayName": "Bob B.", **attest, "accounts": {
                "colab": {"tier": "free", "configDir": str(self.bob_dir)}}},
            {"owner": "carol", "displayName": "Carol C.", **attest, "accounts": {
                "kaggle": {"username": "carol-k"}}},
        ])

    def view(self) -> dict:
        result = subprocess.CompletedProcess(["colab", "--version"], 0, "colab 0.7.5\n", "")
        with mock.patch.object(remote_services.subprocess, "run", return_value=result) as run:
            view = remote_services.remote_services(self.root)
        self.run_mock = run
        return view

    def rows(self) -> dict:
        return {row["id"]: row for row in self.view()["rows"]}


class ColabRowTests(_Env):
    def test_the_colab_and_team_rows_follow_the_kaggle_rows(self) -> None:
        ids = [row["id"] for row in self.view()["rows"]]
        self.assertEqual(ids, ["mcp", "cli", "token", "accounts", "rehearsals", "quota",
                               "colab_cli", "colab_mcp", "colab_accounts", "colab_eligible", "team"])

    def test_an_absent_cli_offers_the_pinned_install_command(self) -> None:
        rows = self.rows()
        self.assertEqual(rows["colab_cli"]["state"], "missing")
        self.assertEqual(rows["colab_cli"]["action"]["command"], remote_services.ACTIONS["install_colab_cli"])
        self.run_mock.assert_not_called()

    def test_the_install_command_is_the_pin_remote_execution_documents(self) -> None:
        text = REMOTE_EXECUTION_DOC.read_text(encoding="utf-8")
        pins = [line.strip() for line in text.splitlines()
                if line.strip().startswith("uv tool install") and "google-colab-cli" in line]
        self.assertTrue(pins, "remote-execution no longer documents a pinned Colab CLI install")
        self.assertIn(terminal.COLAB_CLI_INSTALL, pins)
        self.assertEqual(remote_services.ACTIONS["install_colab_cli"], terminal.COLAB_CLI_INSTALL)

    def test_a_cli_on_path_reports_its_version_once(self) -> None:
        self.fake_colab(self.bin)
        rows = self.rows()
        self.assertEqual(rows["colab_cli"]["state"], "active")
        self.assertIn("0.7.5", rows["colab_cli"]["detail"])
        self.assertEqual(self.run_mock.call_args.args[0][1:], ["--version"])
        self.assertIsNotNone(self.run_mock.call_args.kwargs.get("timeout"))
        self.rows()
        self.run_mock.assert_not_called()  # cached for VERSION_TTL

    def test_a_cli_in_a_tool_dir_is_found_without_path(self) -> None:
        tools = self.tmp / "tools"
        self.fake_colab(tools)
        with mock.patch.object(terminal, "TOOL_DIRS", (tools,)):
            rows = self.rows()
        self.assertEqual(rows["colab_cli"]["state"], "active")
        self.assertIn(str(tools), rows["colab_cli"]["detail"])

    def test_the_mcp_row_says_registered_or_not(self) -> None:
        rows = self.rows()
        self.assertEqual(rows["colab_mcp"]["badge"], "not registered")
        self.assertNotEqual(rows["colab_mcp"]["state"], "active")
        self.register_colab_mcp()
        rows = self.rows()
        self.assertEqual(rows["colab_mcp"]["state"], "active")
        self.assertEqual(rows["colab_mcp"]["badge"], "registered")
        self.assertIn(".mcp.json", rows["colab_mcp"]["detail"])
        self.assertIn("browser", rows["colab_mcp"]["detail"])

    def test_a_kaggle_registration_is_not_a_colab_one(self) -> None:
        _write(self.root / ".mcp.json", json.dumps({"mcpServers": {"kaggle": {"type": "http", "url": "x"}}}))
        self.assertEqual(self.rows()["colab_mcp"]["badge"], "not registered")

    def test_without_a_team_file_the_team_rows_are_inactive(self) -> None:
        rows = self.rows()
        for row_id in ("colab_accounts", "colab_eligible", "team"):
            self.assertEqual(rows[row_id]["state"], "inactive", row_id)
        self.assertEqual(rows["colab_accounts"]["action"]["command"], "smith team list")

    def test_team_counts_come_from_the_registry(self) -> None:
        self.standard_team()
        rows = self.rows()
        self.assertEqual(rows["colab_accounts"]["state"], "active")
        self.assertEqual(rows["colab_accounts"]["count"], 2)
        self.assertEqual(rows["colab_accounts"]["paid"], 1)
        self.assertEqual(rows["colab_accounts"]["free"], 1)
        self.assertEqual(rows["colab_eligible"]["state"], "active")
        self.assertEqual(rows["colab_eligible"]["owners"], ["alice"])
        self.assertIn("alice", rows["colab_eligible"]["detail"])
        self.assertNotIn("bob", rows["colab_eligible"]["detail"])
        self.assertEqual(rows["team"]["state"], "active")
        self.assertEqual(rows["team"]["owners"], 3)
        self.assertEqual(rows["team"]["kaggle"], 2)
        self.assertEqual(rows["team"]["colab"], 2)

    def test_only_free_accounts_leave_no_campaign_worker(self) -> None:
        attest = {"attestedAt": "2026-10-25", "attestation": "x"}
        self.team([{"owner": "bob", "displayName": "Bob", **attest,
                    "accounts": {"colab": {"tier": "free", "configDir": "/nowhere"}}}])
        rows = self.rows()
        self.assertEqual(rows["colab_eligible"]["state"], "inactive")
        self.assertEqual(rows["colab_eligible"]["owners"], [])

    def test_a_malformed_registry_is_unverified_and_never_raises(self) -> None:
        _write(self.root / ".papersmith" / "team.json", "{not json")
        rows = self.rows()
        self.assertEqual(rows["colab_accounts"]["state"], "unverified")
        self.assertEqual(rows["team"]["state"], "unverified")
        self.assertEqual(self.view()["team"]["problem"], "invalid")

    def test_invalid_and_duplicate_owners_are_skipped(self) -> None:
        self.team([
            {"owner": "ok-1", "displayName": "A", "accounts": {"colab": {"tier": "pro", "configDir": "/x"}}},
            {"owner": "ok-1", "displayName": "B", "accounts": {"colab": {"tier": "pro", "configDir": "/y"}}},
            {"owner": "Bad Slug!", "displayName": "C", "accounts": {}},
            {"owner": "z" * 41, "displayName": "D", "accounts": {}},
            "not a member",
        ])
        team = self.view()["team"]
        self.assertEqual([m["owner"] for m in team["members"]], ["ok-1"])
        self.assertEqual(team["members"][0]["display_name"], "A")
        self.assertEqual(team["skipped"], 4)

    def test_actions_are_server_constants(self) -> None:
        self.standard_team()
        self.fake_colab(self.bin)
        commands = {row["action"]["command"] for row in self.view()["rows"] if row["action"]}
        self.assertLessEqual(commands, set(remote_services.ACTIONS.values()))
        self.assertIn("smith colab status", commands)


class TeamTableTests(_Env):
    def test_one_row_per_member_with_presence_flags_only(self) -> None:
        self.standard_team()
        members = {m["owner"]: m for m in self.view()["team"]["members"]}
        self.assertEqual(list(members), ["alice", "bob", "carol"])
        alice, bob, carol = members["alice"], members["bob"], members["carol"]
        self.assertEqual(alice["display_name"], "Alice A.")
        self.assertEqual(alice["kaggle_username"], "alice-k")
        self.assertIs(alice["kaggle_validated"], True)
        self.assertEqual(alice["colab_tier"], "pro")
        self.assertIs(alice["colab_config_present"], True)
        self.assertEqual(alice["eligible"], ["kaggle", "colab"])
        self.assertIsNone(bob["kaggle_username"])
        self.assertIsNone(bob["kaggle_validated"])
        self.assertEqual(bob["colab_tier"], "free")
        self.assertIs(bob["colab_config_present"], False)
        self.assertEqual(bob["eligible"], [])
        self.assertIs(carol["kaggle_validated"], False)
        self.assertIsNone(carol["colab_tier"])
        self.assertIsNone(carol["colab_config_present"])
        self.assertEqual(carol["eligible"], [])

    def test_no_secret_store_username_or_config_path_reaches_the_payload(self) -> None:
        self.standard_team()
        payload = json.dumps(experiments_view.get_experiments_view(self.root))
        self.assertNotIn(SECRET, payload)
        self.assertNotIn("zed-hidden", payload)
        self.assertNotIn(str(self.alice_dir), payload)
        self.assertNotIn("token.json", payload)

    def test_no_file_inside_a_config_dir_is_opened_or_listed(self) -> None:
        self.standard_team()
        guarded = str(self.alice_dir)
        touched: list[str] = []

        def spy(real):
            def wrapper(target, *args, **kwargs):
                if isinstance(target, (str, os.PathLike)):
                    touched.append(os.fspath(target))
                return real(target, *args, **kwargs)
            return wrapper

        patches = [mock.patch.object(builtins, "open", spy(builtins.open)),
                   mock.patch.object(io, "open", spy(io.open)),
                   mock.patch.object(os, "open", spy(os.open)),
                   mock.patch.object(os, "scandir", spy(os.scandir)),
                   mock.patch.object(os, "listdir", spy(os.listdir))]
        for patcher in patches:
            patcher.start()
        try:
            members = {m["owner"]: m for m in self.view()["team"]["members"]}
        finally:
            for patcher in reversed(patches):
                patcher.stop()
        self.assertIs(members["alice"]["colab_config_present"], True)
        self.assertTrue(touched, "the spy saw no file access at all")
        self.assertEqual([p for p in touched if p.startswith(guarded)], [])

    def test_the_empty_state_names_the_add_command(self) -> None:
        team = self.view()["team"]
        self.assertEqual(team["members"], [])
        self.assertTrue(team["add_command"].startswith('smith team add --owner <slug> --name "<Name>"'))
        self.assertIn("--attest", team["add_command"])


class ColabStatusTests(_Env):
    def test_the_box_state_carries_constants_and_the_environment(self) -> None:
        self.register_colab_mcp()
        state = terminal.colab_mcp_status(self.root)
        self.assertEqual(state["registered"], [".mcp.json"])
        self.assertEqual(state["commands"], terminal.COLAB_COMMANDS)
        self.assertEqual(state["commands"]["install"], terminal.COLAB_CLI_INSTALL)
        self.assertIn("system", state["environment"])
        self.assertEqual(state["paid_tiers"], ["pro", "payg", "enterprise"])

    def test_the_experiments_view_carries_the_box_state(self) -> None:
        view = experiments_view.get_experiments_view(self.root)
        self.assertEqual(view["remote_colab"]["commands"], terminal.COLAB_COMMANDS)
        self.assertIn("team", view["remote_services"])

    def test_the_shell_quick_commands_include_colab_and_team(self) -> None:
        self.assertIn("smith colab status", terminal.SHELL_QUICK)
        self.assertIn("smith team list", terminal.SHELL_QUICK)
        self.assertIn("smith mcp kaggle activate", terminal.SHELL_QUICK)


@unittest.skipUnless(NODE, "node is required to run the panel renderer")
class RenderTests(_Env):
    def render(self, view: dict) -> str:
        i18n_js = SCRIPT_PATH.parent / "i18n.js"
        en_js = SCRIPT_PATH.parent / "i18n" / "en.js"
        es_js = SCRIPT_PATH.parent / "i18n" / "es.js"
        script = (
            "const fs=require('fs');"
            "global.window={localStorage:{getItem:()=>'es',setItem:()=>{}}};"
            "global.document={addEventListener(){},querySelectorAll:()=>[]};"
            f"eval(fs.readFileSync({json.dumps(str(en_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(es_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(i18n_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(SCRIPT_PATH))},'utf8'));"
            "console.log(window.ExperimentsPanel.render(JSON.parse(fs.readFileSync(0,'utf8'))));"
        )
        return subprocess.run([NODE, "-e", script], input=json.dumps(view), capture_output=True,
                              text=True, cwd=tempfile.gettempdir(), check=True).stdout

    def test_the_sections_render_in_order(self) -> None:
        out = self.render(experiments_view.get_experiments_view(self.root))
        order = ['id="expMcpActivation"', 'id="expColabActivation"', "Servicios remotos (Kaggle y Colab)",
                 "Equipo (una cuenta por persona y servicio)", "Ayuda: lanzar"]
        positions = [out.index(marker) for marker in order]
        self.assertEqual(positions, sorted(positions))

    def test_every_button_runs_a_server_constant(self) -> None:
        self.standard_team()
        out = self.render(experiments_view.get_experiments_view(self.root))
        allowed = set(remote_services.ACTIONS.values()) | set(terminal.COLAB_COMMANDS.values()) | {
            "smith mcp kaggle activate", "smith mcp kaggle status --verify"}
        unescape = lambda s: (s.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")  # noqa: E731
                              .replace("&#39;", "'").replace("&amp;", "&"))
        found = {unescape(value) for value in re.findall(r'data-exp-cli="([^"]*)"', out)}
        self.assertLessEqual(found, allowed)
        for key in ("install", "team_add", "login", "status", "team_list"):
            self.assertIn(terminal.COLAB_COMMANDS[key], found, key)

    def test_template_commands_are_typed_not_run(self) -> None:
        out = self.render(experiments_view.get_experiments_view(self.root))
        for key in ("team_add", "login"):
            attr = f'data-exp-cli="{self._esc(terminal.COLAB_COMMANDS[key])}" data-exp-cli-run="0"'
            self.assertIn(attr, out, key)
        status = f'data-exp-cli="{terminal.COLAB_COMMANDS["status"]}" data-exp-cli-run="0"'
        self.assertNotIn(status, out)

    @staticmethod
    def _esc(text: str) -> str:
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;").replace("'", "&#39;"))

    def test_the_box_states_the_team_rule_and_the_tiers(self) -> None:
        out = self.render(experiments_view.get_experiments_view(self.root))
        box = out[out.index('id="expColabActivation"'):out.index("Servicios remotos (Kaggle y Colab)")]
        self.assertIn("using multiple accounts to work around access or resource usage restrictions", box)
        self.assertIn("running distributed computing workers", box)
        self.assertIn("navegador", box)
        for gpu in ("L4", "A100", "H100"):
            self.assertIn(gpu, box)
        self.assertIn("solo en niveles de pago", box)

    def test_the_box_follows_the_environment(self) -> None:
        view = experiments_view.get_experiments_view(self.root)
        view["remote_colab"]["environment"] = {"system": "windows", "shell": "powershell"}
        out = self.render(view)
        box = out[out.index('id="expColabActivation"'):out.index("Servicios remotos (Kaggle y Colab)")]
        self.assertIn("Windows", box)
        self.assertIn("PowerShell", box)

    def test_a_hostile_display_name_is_escaped(self) -> None:
        self.team([{"owner": "eve", "displayName": "<img src=x onerror=alert(1)>",
                    "accounts": {"colab": {"tier": "pro", "configDir": "/none"}}}])
        out = self.render(experiments_view.get_experiments_view(self.root))
        self.assertNotIn("<img src=x", out)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", out)

    def test_the_team_table_renders_members_and_the_empty_state(self) -> None:
        out = self.render(experiments_view.get_experiments_view(self.root))
        self.assertIn("smith team add --owner &lt;slug&gt; --name &quot;&lt;Name&gt;&quot; --attest", out)
        self.standard_team()
        out = self.render(experiments_view.get_experiments_view(self.root))
        team = out[out.index("Equipo (una cuenta por persona y servicio)"):out.index("Ayuda: lanzar")]
        for text in ("alice", "Alice A.", "alice-k", "bob", "carol", "pro", "free"):
            self.assertIn(text, team)

    def test_the_help_box_has_a_colab_section(self) -> None:
        out = self.render({"protocol": None, "products": [], "warnings": [], "remote_accounts": {}})
        help_box = out[out.index("Ayuda: lanzar"):]
        self.assertIn("Colab", help_box)
        self.assertIn("No mezcles", help_box)
        self.assertIn("smith colab login", help_box)


if __name__ == "__main__":
    unittest.main()
