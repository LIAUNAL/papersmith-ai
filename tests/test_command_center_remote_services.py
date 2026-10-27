"""The Experiments tab's remote-services table: an offline, bounded probe.

``remote_services.remote_services(root)`` answers one row per service the
remote path depends on (official MCP, official CLI, token, worker accounts,
rehearsals, weekly GPU quota) without touching the network. The CLI's
version is read once per server process and cached; the token and the
accounts' usernames never reach the payload. The renderer runs under node.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import experiments_view, remote_services, server, terminal

SCRIPT_PATH = Path(server.__file__).resolve().parent / "static" / "experiments-panel.js"
TOKEN = "KGAT_secret0123456789abcdef"
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
        self.tmp = Path(holder.name)
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

    def install_cli(self) -> None:
        exe = _write(self.bin / "kaggle", "#!/bin/sh\necho 'Kaggle API 1.7.4'\n")
        exe.chmod(0o755)

    def store_token(self) -> None:
        path = _write(self.home / ".kaggle" / "access_token", TOKEN + "\n")
        path.chmod(0o600)
        path.parent.chmod(0o700)

    def register_mcp(self) -> None:
        _write(self.root / ".mcp.json", json.dumps(
            {"mcpServers": {terminal.REMOTE_MCP_SERVER: {"type": "http", "url": "https://x"}}}))

    def accounts_store(self, accounts: list[dict]) -> None:
        _write(self.root / "skills" / "acc" / "scripts" / "acc_cli.py",
               'STORE_NAME = "store"\nSTORE_FILE = "accounts.json"\n')
        _write(self.root / "skills" / "acc" / "store" / "accounts.json",
               json.dumps({"version": 1, "accounts": accounts}))

    def rows(self, **patches) -> dict:
        result = subprocess.CompletedProcess(["kaggle", "--version"], 0, "Kaggle API 1.7.4\n", "")
        with mock.patch.object(remote_services.subprocess, "run", return_value=result) as run:
            view = remote_services.remote_services(self.root)
        self.run_mock = run
        return {row["id"]: row for row in view["rows"]}


class RowTests(_Env):
    def test_every_row_is_present_in_order_with_a_note(self) -> None:
        view = remote_services.remote_services(self.root)
        self.assertEqual([row["id"] for row in view["rows"]],
                         ["mcp", "cli", "token", "accounts", "rehearsals", "quota",
                          "colab_cli", "colab_mcp", "colab_accounts", "colab_eligible", "team"])
        self.assertTrue(view["note"])
        for row in view["rows"]:
            self.assertIn(row["state"], remote_services.STATES)
            self.assertTrue(row["service"] and row["purpose"])

    def test_an_empty_environment_reports_absent_and_inactive(self) -> None:
        rows = self.rows()
        self.assertEqual(rows["mcp"]["state"], "missing")
        self.assertEqual(rows["cli"]["state"], "missing")
        self.assertEqual(rows["cli"]["action"]["command"], "pipx install kaggle")
        self.assertEqual(rows["token"]["state"], "inactive")
        self.assertEqual(rows["token"]["action"]["command"], "smith mcp kaggle activate")
        self.assertEqual(rows["accounts"]["state"], "missing")
        self.assertEqual(rows["rehearsals"]["state"], "inactive")
        self.assertIsNone(rows["rehearsals"]["action"])
        self.assertEqual(rows["quota"]["state"], "unverified")
        self.assertEqual(rows["quota"]["action"]["command"], "smith mcp kaggle status --verify")
        self.run_mock.assert_not_called()

    def test_a_present_cli_reports_its_version(self) -> None:
        self.install_cli()
        rows = self.rows()
        self.assertEqual(rows["cli"]["state"], "active")
        self.assertIn("1.7.4", rows["cli"]["detail"])
        self.assertIsNone(rows["cli"]["action"])
        argv = self.run_mock.call_args.args[0]
        self.assertEqual(argv[1:], ["--version"])
        self.assertIsNotNone(self.run_mock.call_args.kwargs.get("timeout"))

    def test_registered_mcp_with_token_is_active_and_without_token_inactive(self) -> None:
        self.register_mcp()
        rows = self.rows()
        self.assertEqual(rows["mcp"]["state"], "inactive")
        self.assertIn(".mcp.json", rows["mcp"]["detail"])
        self.assertEqual(rows["mcp"]["action"]["command"], "smith mcp kaggle activate")
        self.store_token()
        rows = self.rows()
        self.assertEqual(rows["mcp"]["state"], "active")
        self.assertEqual(rows["mcp"]["action"]["command"], "smith mcp kaggle status --verify")
        self.assertEqual(rows["token"]["state"], "active")

    def test_the_accounts_row_shows_only_a_count(self) -> None:
        self.accounts_store([{"username": "alice-worker", "key": SECRET},
                             {"username": "bob-worker", "key": SECRET}])
        rows = self.rows()
        self.assertEqual(rows["accounts"]["state"], "active")
        self.assertEqual(rows["accounts"]["count"], 2)
        self.assertEqual(rows["accounts"]["action"]["command"], "/kaggle-accounts validate")
        self.accounts_store([])
        self.assertEqual(self.rows()["accounts"]["state"], "inactive")

    def test_rehearsals_count_job_folders_and_passing_smoke(self) -> None:
        _write(self.root / "implementations" / "repo" / "tools" / "svc" / "job1" / "run-config.json", "{}")
        rows = self.rows()
        self.assertEqual(rows["rehearsals"]["state"], "inactive")
        self.assertEqual(rows["rehearsals"]["jobs"], 1)
        _write(self.root / "implementations" / "repo" / "Prod" / ".remote-execution" / "smoke.jsonl",
               json.dumps({"kind": "smokeResult", "result": "pass", "entrypoint": "e"}) + "\n")
        rows = self.rows()
        self.assertEqual(rows["rehearsals"]["state"], "active")
        self.assertEqual(rows["rehearsals"]["passed"], 1)

    def test_no_secret_reaches_the_payload(self) -> None:
        self.register_mcp()
        self.store_token()
        self.install_cli()
        self.accounts_store([{"username": "alice-worker", "key": SECRET}])
        with mock.patch.object(remote_services.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 0, "Kaggle API 1.7.4", "")):
            payload = json.dumps(experiments_view.get_experiments_view(self.root))
        self.assertNotIn(TOKEN, payload)
        self.assertNotIn(SECRET, payload)
        self.assertNotIn("alice-worker", payload)

    def test_the_version_is_read_once_across_two_views(self) -> None:
        self.install_cli()
        result = subprocess.CompletedProcess([], 0, "Kaggle API 1.7.4\n", "")
        with mock.patch.object(remote_services.subprocess, "run", return_value=result) as run:
            experiments_view.get_experiments_view(self.root)
            view = experiments_view.get_experiments_view(self.root)
        self.assertEqual(run.call_count, 1)
        cli = next(row for row in view["remote_services"]["rows"] if row["id"] == "cli")
        self.assertIn("1.7.4", cli["detail"])

    def test_a_failing_version_call_never_raises(self) -> None:
        self.install_cli()
        with mock.patch.object(remote_services.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("kaggle", 3)):
            rows = {row["id"]: row for row in remote_services.remote_services(self.root)["rows"]}
        self.assertEqual(rows["cli"]["state"], "active")

    def test_a_broken_probe_becomes_an_unverified_row(self) -> None:
        with mock.patch.object(remote_services, "remote_mcp_status", side_effect=RuntimeError("boom")):
            rows = {row["id"]: row for row in remote_services.remote_services(self.root)["rows"]}
        self.assertEqual(rows["mcp"]["state"], "unverified")
        self.assertEqual(rows["token"]["state"], "unverified")

    def test_actions_are_server_constants(self) -> None:
        commands = {row["action"]["command"] for row in remote_services.remote_services(self.root)["rows"]
                    if row["action"]}
        self.assertLessEqual(commands, set(remote_services.ACTIONS.values()))


@unittest.skipUnless(NODE, "node is required to run the panel renderer")
class VersionCacheTests(unittest.TestCase):
    """A CLI's version is probed once; past its TTL the old answer is served
    at once while one background run replaces it."""

    def setUp(self) -> None:
        remote_services.clear_cache()
        self.addCleanup(remote_services.clear_cache)

    def test_an_expired_version_is_served_while_it_refreshes(self) -> None:
        calls: list[str] = []

        def run(executable: str) -> str:
            calls.append(executable)
            if len(calls) > 1:
                time.sleep(0.5)
            return f"v{len(calls)}"

        with mock.patch.object(remote_services, "_run_version", side_effect=run):
            self.assertEqual(remote_services._cli_version("kaggle"), "v1")
            self.assertEqual(remote_services._cli_version("kaggle"), "v1")
            self.assertEqual(len(calls), 1)
            later = time.monotonic() + remote_services.VERSION_TTL + 10
            with mock.patch.object(remote_services.time, "monotonic", return_value=later):
                started = time.perf_counter()
                self.assertEqual(remote_services._cli_version("kaggle"), "v1")
                self.assertEqual(remote_services._cli_version("kaggle"), "v1")
                self.assertLess(time.perf_counter() - started, 0.3)
                deadline = time.time() + 5
                while remote_services._cli_version("kaggle") != "v2" and time.time() < deadline:
                    time.sleep(0.05)
            self.assertEqual(remote_services._cli_version("kaggle"), "v2")
            self.assertEqual(len(calls), 2)


class RenderTests(_Env):
    def render(self, view: dict) -> str:
        script = (
            "const fs=require('fs');global.window={};global.document={addEventListener(){}};"
            f"eval(fs.readFileSync({json.dumps(str(SCRIPT_PATH))},'utf8'));"
            "console.log(window.ExperimentsPanel.render(JSON.parse(fs.readFileSync(0,'utf8'))));"
        )
        return subprocess.run([NODE, "-e", script], input=json.dumps(view), capture_output=True,
                              text=True, cwd=tempfile.gettempdir(), check=True).stdout

    def test_the_table_renders_after_the_mcp_box_with_badges_and_buttons(self) -> None:
        view = experiments_view.get_experiments_view(self.root)
        view["remote_services"]["rows"][0]["detail"] = "<img src=x onerror=alert(1)>"
        out = self.render(view)
        self.assertIn("Servicios remotos (Kaggle y Colab)", out)
        self.assertLess(out.index('id="expMcpActivation"'), out.index("Servicios remotos (Kaggle y Colab)"))
        self.assertLess(out.index("Servicios remotos (Kaggle y Colab)"), out.index("Ayuda: lanzar"))
        self.assertIn('data-exp-cli="pipx install kaggle"', out)
        self.assertIn('data-exp-cli="/kaggle-accounts validate"', out)
        self.assertIn('data-exp-cli="smith mcp kaggle status --verify"', out)
        for label in ("no instalado", "inactivo", "sin verificar"):
            self.assertIn(label, out)
        self.assertNotIn("<img src=x", out)
        self.assertIn("&lt;img src=x", out)

    def test_an_active_row_shows_the_active_badge(self) -> None:
        self.install_cli()
        with mock.patch.object(remote_services.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 0, "Kaggle API 1.7.4", "")):
            view = experiments_view.get_experiments_view(self.root)
        out = self.render(view)
        self.assertIn('badge--ok">activo', out)

    def test_a_view_without_the_table_still_renders(self) -> None:
        out = self.render({"protocol": None, "products": [], "warnings": [], "remote_accounts": {}})
        self.assertIn("Ayuda: lanzar", out)


if __name__ == "__main__":
    unittest.main()
