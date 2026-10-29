"""`smith mcp kaggle activate|status|deactivate` and the dashboard's use of the stored token."""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "skills" / "_core"))

from papersmith.cli import main  # noqa: E402
from papersmith.core import kaggle_mcp  # noqa: E402
from command_center import terminal  # noqa: E402

TOKEN = "KGAT_test0123456789abcdef"


class _Env(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.config = self.tmp / "config"
        self.home = self.tmp / "home"
        self.home.mkdir()
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config),
                                               "HOME": str(self.home), "SHELL": "/bin/zsh"})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(kaggle_mcp.TOKEN_ENV, None)
        # The official Kaggle client's own location, shared with its CLI and SDK.
        self.token_file = self.home / ".kaggle" / "access_token"
        self.legacy_file = self.config / "papersmith" / "kaggle-mcp-token"

    def run_cli(self, *argv: str, stdin: str = "") -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = main(list(argv))
        return code, out.getvalue()


class ActivateTests(_Env):
    def test_activate_verifies_and_stores_the_token_privately(self) -> None:
        workspace = self.tmp / "ws"
        workspace.mkdir()
        with mock.patch.object(kaggle_mcp, "verify_token", return_value=(True, "quota read")):
            code, out = self.run_cli("mcp", "kaggle", "activate", "--token-stdin",
                                     "--workspace", str(workspace), stdin=TOKEN + "\n")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.token_file.read_text(encoding="utf-8").strip(), TOKEN)
        self.assertEqual(stat.S_IMODE(self.token_file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.token_file.parent.stat().st_mode), 0o700)
        self.assertNotIn(TOKEN, out)
        servers = json.loads((workspace / ".mcp.json").read_text())["mcpServers"]
        self.assertIn("kaggle", servers)
        self.assertNotIn(TOKEN, (workspace / ".mcp.json").read_text())

    def test_a_rejected_token_writes_nothing(self) -> None:
        with mock.patch.object(kaggle_mcp, "verify_token", return_value=(False, "Unauthenticated")):
            code, out = self.run_cli("mcp", "kaggle", "activate", "--token-stdin", stdin=TOKEN)
        self.assertNotEqual(code, 0)
        self.assertIn("Unauthenticated", out)
        self.assertFalse(self.token_file.exists())
        self.assertNotIn(TOKEN, out)

    def test_an_empty_token_is_refused_before_any_check(self) -> None:
        with mock.patch.object(kaggle_mcp, "verify_token") as verify:
            code, _ = self.run_cli("mcp", "kaggle", "activate", "--token-stdin", stdin="  \n")
        self.assertNotEqual(code, 0)
        verify.assert_not_called()
        self.assertFalse(self.token_file.exists())

    def test_no_verify_stores_without_a_network_call(self) -> None:
        with mock.patch.object(kaggle_mcp, "verify_token") as verify:
            code, _ = self.run_cli("mcp", "kaggle", "activate", "--token-stdin", "--no-verify",
                                   stdin=TOKEN)
        self.assertEqual(code, 0)
        verify.assert_not_called()
        self.assertTrue(self.token_file.is_file())


class StatusAndDeactivateTests(_Env):
    def test_status_reports_the_source_without_the_token(self) -> None:
        code, out = self.run_cli("mcp", "kaggle", "status")
        self.assertEqual(code, 0)
        self.assertIn("not activated", out)
        kaggle_mcp.store_token(TOKEN)
        code, out = self.run_cli("mcp", "kaggle", "status")
        self.assertIn("activated", out)
        self.assertIn(str(self.token_file), out)
        self.assertNotIn(TOKEN, out)
        with mock.patch.dict(os.environ, {kaggle_mcp.TOKEN_ENV: TOKEN}):
            code, out = self.run_cli("mcp", "kaggle", "status")
        self.assertIn(kaggle_mcp.TOKEN_ENV, out)
        self.assertNotIn(TOKEN, out)

    def test_a_readable_by_others_file_is_reported_and_never_used(self) -> None:
        kaggle_mcp.store_token(TOKEN)
        self.token_file.chmod(0o644)
        self.assertIsNone(kaggle_mcp.read_token())
        code, out = self.run_cli("mcp", "kaggle", "status")
        self.assertIn("insecure", out)

    def test_a_symlinked_token_file_is_never_followed(self) -> None:
        real = self.tmp / "elsewhere"
        real.write_text(TOKEN, encoding="utf-8")
        real.chmod(0o600)
        self.token_file.parent.mkdir(parents=True)
        self.token_file.symlink_to(real)
        self.assertIsNone(kaggle_mcp.read_token())

    def test_rewriting_an_open_file_tightens_its_mode_before_writing(self) -> None:
        self.token_file.parent.mkdir(parents=True)
        self.token_file.write_text("old", encoding="utf-8")
        self.token_file.chmod(0o644)
        kaggle_mcp.store_token(TOKEN, replace=True)
        self.assertEqual(stat.S_IMODE(self.token_file.stat().st_mode), 0o600)

    def test_a_symlinked_config_directory_is_refused(self) -> None:
        real = self.tmp / "real-dir"
        real.mkdir()
        (self.home / ".kaggle").symlink_to(real)
        code, _ = self.run_cli("mcp", "kaggle", "activate", "--token-stdin", "--no-verify", stdin=TOKEN)
        self.assertNotEqual(code, 0)
        self.assertEqual(list(real.iterdir()), [])

    def test_status_verify_without_a_token_fails(self) -> None:
        code, out = self.run_cli("mcp", "kaggle", "status", "--verify")
        self.assertEqual(code, 1)
        self.assertIn("skipped", out)

    def test_deactivate_removes_the_stored_token(self) -> None:
        kaggle_mcp.store_token(TOKEN)
        code, _ = self.run_cli("mcp", "kaggle", "deactivate")
        self.assertEqual(code, 0)
        self.assertFalse(self.token_file.exists())


class DashboardTests(_Env):
    def test_dashboard_sessions_receive_the_stored_token(self) -> None:
        kaggle_mcp.store_token(TOKEN)
        env = terminal.session_env("claude", self.tmp)
        self.assertEqual(env[kaggle_mcp.TOKEN_ENV], TOKEN)

    def test_an_exported_token_wins_over_the_stored_one(self) -> None:
        kaggle_mcp.store_token(TOKEN)
        with mock.patch.dict(os.environ, {kaggle_mcp.TOKEN_ENV: "KGAT_exported"}):
            env = terminal.session_env("shell", self.tmp)
        self.assertEqual(env[kaggle_mcp.TOKEN_ENV], "KGAT_exported")

    def test_no_token_is_injected_from_an_insecure_file(self) -> None:
        kaggle_mcp.store_token(TOKEN)
        self.token_file.chmod(0o640)
        env = terminal.session_env("claude", self.tmp)
        self.assertNotIn(kaggle_mcp.TOKEN_ENV, env)

    def test_both_sides_agree_on_the_token_location(self) -> None:
        self.assertEqual(terminal.remote_mcp_token_path(), kaggle_mcp.token_path())
        self.assertEqual(terminal.remote_mcp_token_candidates(), kaggle_mcp.token_candidates())

    def test_the_shell_offers_the_activation_commands(self) -> None:
        self.assertIn("smith mcp kaggle activate", terminal.SHELL_QUICK)
        self.assertIn("smith mcp kaggle status", terminal.SHELL_QUICK)

    def test_the_experiments_view_reports_activation_without_the_token(self) -> None:
        from command_center import experiments_view
        workspace = self.tmp / "ws"
        workspace.mkdir()
        (workspace / ".mcp.json").write_text(json.dumps({"mcpServers": {"kaggle": {}}}))
        state = experiments_view.get_experiments_view(workspace)["remote_mcp"]
        self.assertFalse(state["activated"])
        self.assertEqual(state["registered"], [".mcp.json"])
        kaggle_mcp.store_token(TOKEN)
        view = experiments_view.get_experiments_view(workspace)
        self.assertEqual(view["remote_mcp"]["source"], "file")
        self.assertNotIn(TOKEN, json.dumps(view))


class PanelTests(unittest.TestCase):
    def render(self, state: dict) -> str:
        import subprocess
        static = REPO / "skills" / "_core" / "command_center" / "static"
        script = static / "experiments-panel.js"
        en_js = static / "i18n" / "en.js"
        es_js = static / "i18n" / "es.js"
        i18n_js = static / "i18n.js"
        code = (
            "const fs = require('fs');"
            "global.window = {localStorage: {getItem: () => 'es', setItem: () => {}}};"
            "global.document = {addEventListener() {}, querySelectorAll: () => []};"
            "eval(fs.readFileSync(process.argv[3], 'utf8'));"
            "eval(fs.readFileSync(process.argv[4], 'utf8'));"
            "eval(fs.readFileSync(process.argv[5], 'utf8'));"
            "eval(fs.readFileSync(process.argv[1], 'utf8'));"
            "process.stdout.write(window.ExperimentsPanel.render({remote_mcp: JSON.parse(process.argv[2])}));"
        )
        return subprocess.run(["node", "-e", code, str(script), json.dumps(state), str(en_js), str(es_js), str(i18n_js)],
                              capture_output=True, text=True, check=True).stdout

    def test_the_panel_explains_activation_and_sends_it_to_the_cli_assistant(self) -> None:
        html = self.render({"activated": False, "problem": "absent", "registered": [".mcp.json"],
                            "activate": "smith mcp kaggle activate", "status": "smith mcp kaggle status",
                            "env": "KAGGLE_API_TOKEN", "token_path": "/home/u/.kaggle/access_token",
                            "environment": {"system": "wsl", "shell": "bash", "user": "u",
                                            "token_path": "/home/u/.kaggle/access_token",
                                            "export_command": 'export KAGGLE_API_TOKEN="$(cat ~/.kaggle/access_token)"',
                                            "profile_file": "~/.bashrc",
                                            "note": "WSL note <b>x</b>"}})
        self.assertIn("Activar Kaggle por MCP", html)
        self.assertIn('data-exp-cli="smith mcp kaggle activate"', html)
        self.assertIn('data-exp-cli="smith mcp kaggle status --verify"', html)
        self.assertIn("kaggle.com/settings", html)
        self.assertIn("sin activar", html)
        self.assertIn("export KAGGLE_API_TOKEN=&quot;$(cat ~/.kaggle/access_token)&quot;", html)
        self.assertIn("~/.bashrc", html)
        self.assertIn("WSL", html)
        self.assertNotIn("<b>x</b>", html)
        self.assertNotIn("kaggle-mcp-token", html)
        active = self.render({"activated": True, "source": "file", "registered": []})
        self.assertIn("token guardado", active)
        self.assertIn("smith upgrade", active)

    def test_clicking_a_cli_button_runs_it_in_the_shell_assistant(self) -> None:
        source = (REPO / "skills" / "_core" / "command_center" / "static" / "experiments-panel.js").read_text()
        self.assertIn("window.sendToCli(cli.getAttribute('data-exp-cli'), true, { kind: 'shell' })", source)


class OfficialLocationTests(_Env):
    def test_an_existing_different_token_is_never_overwritten_without_replace(self) -> None:
        self.token_file.parent.mkdir(mode=0o700)
        self.token_file.write_text("KGAT_other\n", encoding="utf-8")
        self.token_file.chmod(0o600)
        code, out = self.run_cli("mcp", "kaggle", "activate", "--token-stdin", "--no-verify", stdin=TOKEN)
        self.assertNotEqual(code, 0)
        self.assertIn("--replace", out)
        self.assertEqual(self.token_file.read_text().strip(), "KGAT_other")
        code, _ = self.run_cli("mcp", "kaggle", "activate", "--token-stdin", "--no-verify", "--replace",
                               stdin=TOKEN)
        self.assertEqual(code, 0)
        self.assertEqual(self.token_file.read_text().strip(), TOKEN)

    def test_a_different_token_in_a_too_open_file_is_still_protected(self) -> None:
        self.token_file.parent.mkdir(mode=0o700)
        self.token_file.write_text("KGAT_other\n", encoding="utf-8")
        self.token_file.chmod(0o644)
        code, out = self.run_cli("mcp", "kaggle", "activate", "--token-stdin", "--no-verify", stdin=TOKEN)
        self.assertNotEqual(code, 0)
        self.assertIn("--replace", out)
        self.assertEqual(self.token_file.read_text().strip(), "KGAT_other")

    def test_status_points_at_the_file_that_is_actually_insecure(self) -> None:
        txt = self.home / ".kaggle" / "access_token.txt"
        txt.parent.mkdir(mode=0o700)
        txt.write_text(TOKEN, encoding="utf-8")
        txt.chmod(0o644)
        _code, out = self.run_cli("mcp", "kaggle", "status")
        self.assertIn(f"chmod 600 {txt}", out)

    def test_a_token_left_by_the_official_client_is_used_as_is(self) -> None:
        txt = self.home / ".kaggle" / "access_token.txt"
        txt.parent.mkdir(mode=0o700)
        txt.write_text(TOKEN, encoding="utf-8")
        txt.chmod(0o600)
        self.assertEqual(kaggle_mcp.read_token(), TOKEN)
        self.assertEqual(terminal.read_remote_mcp_token(), TOKEN)

    def test_the_earlier_papersmith_location_still_reads(self) -> None:
        self.legacy_file.parent.mkdir(parents=True, mode=0o700)
        self.legacy_file.write_text(TOKEN, encoding="utf-8")
        self.legacy_file.chmod(0o600)
        self.assertEqual(kaggle_mcp.read_token(), TOKEN)
        self.assertEqual(terminal.session_env("claude", self.tmp)[kaggle_mcp.TOKEN_ENV], TOKEN)
        self.run_cli("mcp", "kaggle", "deactivate")
        self.assertFalse(self.legacy_file.exists())


class EnvironmentTests(_Env):
    CASES = [
        # (sys.platform, os.name, release, extra env, SHELL) -> expected (system, shell, export prefix, profile)
        ("darwin", "posix", "24.0.0", {}, "/bin/zsh",
         ("macos", "zsh", 'export KAGGLE_API_TOKEN="$(cat ~/.kaggle/access_token)"', "~/.zshrc")),
        ("darwin", "posix", "24.0.0", {}, "/bin/bash",
         ("macos", "bash", 'export KAGGLE_API_TOKEN="$(cat ~/.kaggle/access_token)"', "~/.bash_profile")),
        ("linux", "posix", "6.8.0-45-generic", {}, "/usr/bin/bash",
         ("linux", "bash", 'export KAGGLE_API_TOKEN="$(cat ~/.kaggle/access_token)"', "~/.bashrc")),
        ("linux", "posix", "5.15.153.1-microsoft-standard-WSL2", {}, "/bin/bash",
         ("wsl", "bash", 'export KAGGLE_API_TOKEN="$(cat ~/.kaggle/access_token)"', "~/.bashrc")),
        ("linux", "posix", "6.8.0", {"WSL_DISTRO_NAME": "Ubuntu"}, "/usr/bin/fish",
         ("wsl", "fish", "set -gx KAGGLE_API_TOKEN (cat ~/.kaggle/access_token)", "~/.config/fish/config.fish")),
        ("win32", "nt", "10", {"USERPROFILE": "C:\\Users\\u"}, "",
         ("windows", "powershell", '$env:KAGGLE_API_TOKEN = Get-Content "$HOME\\.kaggle\\access_token"', "$PROFILE")),
    ]

    def detect(self, module, case):
        platform_, osname, release, extra, shell, _ = case
        path_fn = "token_path" if module is kaggle_mcp else "remote_mcp_token_path"
        with mock.patch.object(module, path_fn, return_value=Path("/fixed/.kaggle/access_token")), \
                mock.patch.object(module.sys, "platform", platform_), \
                mock.patch.object(module.os, "name", osname), \
                mock.patch.object(module.platform, "release", return_value=release), \
                mock.patch.dict(os.environ, {"SHELL": shell, **extra}):
            if "WSL_DISTRO_NAME" not in extra:
                os.environ.pop("WSL_DISTRO_NAME", None)
            return module.detect_environment() if module is kaggle_mcp else module.remote_mcp_environment()

    def test_each_environment_gets_its_own_commands(self) -> None:
        for case in self.CASES:
            env = self.detect(kaggle_mcp, case)
            system, shell, export, profile = case[-1]
            self.assertEqual((env["system"], env["shell"], env["export_command"], env["profile_file"]),
                             (system, shell, export, profile), case)
            self.assertTrue(env["user"])
            self.assertEqual(env["note"] != "", system in ("wsl", "windows"), case)

    def test_cli_and_dashboard_detect_the_same_environment(self) -> None:
        for case in self.CASES:
            self.assertEqual(self.detect(kaggle_mcp, case), self.detect(terminal, case), case)

    def test_status_prints_the_commands_for_this_environment(self) -> None:
        code, out = self.run_cli("mcp", "kaggle", "status")
        self.assertIn('export KAGGLE_API_TOKEN="$(cat ~/.kaggle/access_token)"', out)
        self.assertIn("~/.zshrc", out)

    def test_init_and_upgrade_summary_is_offline_and_names_the_next_step(self) -> None:
        with mock.patch.object(kaggle_mcp, "verify_token") as verify, \
                mock.patch.object(kaggle_mcp.shutil, "which", return_value=None):
            lines = kaggle_mcp.summary_lines(["claude", "pi"])
        verify.assert_not_called()
        text = "\n".join(lines)
        self.assertIn("smith mcp kaggle activate", text)
        self.assertIn("npx", text)
        kaggle_mcp.store_token(TOKEN)
        with mock.patch.object(kaggle_mcp.shutil, "which", return_value="/usr/bin/npx"):
            text = "\n".join(kaggle_mcp.summary_lines(["claude", "pi"]))
        self.assertIn("activated", text)
        self.assertNotIn("npx", text)
        self.assertNotIn(TOKEN, text)


if __name__ == "__main__":
    unittest.main()
