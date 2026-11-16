"""`smith colab login|status`: the official Colab CLI, one state directory per owner.

A fake `colab` executable on PATH logs its argv and the HOME it was given, so
the tests read what papersmith asked the CLI to do without a network or a
Google account. The CLI 0.7.5 keeps its oauth token at
`~/.config/colab-cli/token.json` whatever `--config` says (that flag only
moves `sessions.json`), so per-owner isolation is the child's HOME. Nothing in
papersmith may open a file inside an owner's configDir: every in-process open
is recorded and checked.
"""

from __future__ import annotations

import builtins
import contextlib
import io
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from papersmith.cli import main  # noqa: E402
from papersmith.core import colab, team  # noqa: E402

FAKE = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "calls.jsonl"), "a") as log:
        log.write(json.dumps({{"argv": sys.argv[1:], "home": os.environ.get("HOME"),
                              "env": sorted(os.environ)}}) + "\\n")
    mode = open(os.path.join(here, "mode")).read().strip()
    if sys.argv[1:] == ["version"]:
        print("Version: 0.7.5")
        sys.exit(0)
    if mode == "hang":
        import time
        time.sleep(30)
    sys.exit(0 if mode == "signed-in" else 1)
''')


class _Env(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.config = self.tmp / "config"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        exe = self.bin / "colab"
        exe.write_text(FAKE.format(python=sys.executable), encoding="utf-8")
        exe.chmod(0o755)
        self.set_mode("signed-in")
        patcher = mock.patch.dict(os.environ, {
            "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.config),
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
            "SECRET_SHOULD_NOT_LEAK": "x", "SHELL": "/bin/zsh"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ws = self.tmp / "ws"
        (self.ws / ".papersmith").mkdir(parents=True)
        self.team(["add", "--owner", "ana", "--name", "Ana", "--colab", "--colab-tier", "pro", "--attest"])
        self.team(["add", "--owner", "bo", "--name", "Bo", "--colab", "--colab-tier", "free", "--attest"])
        self.team(["add", "--owner", "cy", "--name", "Cy", "--kaggle-username", "cy-k", "--attest"])
        self.ana_dir = self.config / "papersmith" / "colab" / "ana"

    def set_mode(self, mode: str) -> None:
        (self.bin / "mode").write_text(mode, encoding="utf-8")

    def team(self, argv: list[str]) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["team", *argv, "--workspace", str(self.ws)]) == 0

    def calls(self) -> list[dict]:
        log = self.bin / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    def run_cli(self, *argv: str) -> tuple[int, str, list[str]]:
        """Run `smith colab ...`, returning every path papersmith itself opened."""
        opened: list[str] = []
        real_open, real_io_open, real_os_open = builtins.open, io.open, os.open

        def spy(opener):
            def wrapped(file, *args, **kwargs):
                if isinstance(file, (str, bytes, os.PathLike)):
                    opened.append(os.path.realpath(os.fsdecode(file)))
                return opener(file, *args, **kwargs)
            return wrapped

        out = io.StringIO()
        with mock.patch("builtins.open", spy(real_open)), mock.patch("io.open", spy(real_io_open)), \
                mock.patch("os.open", spy(real_os_open)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = main(["colab", *argv, "--workspace", str(self.ws)])
        return code, out.getvalue(), opened

    def assert_nothing_opened_inside_config_dirs(self, opened: list[str]) -> None:
        root = os.path.realpath(self.config / "papersmith" / "colab")
        self.assertIn(os.path.realpath(self.ws / ".papersmith" / "team.json"), opened,
                      "the open spy saw nothing, so it proves nothing")
        inside = [path for path in opened if path == root or path.startswith(root + os.sep)]
        self.assertEqual(inside, [])


class LoginTests(_Env):
    def test_login_runs_the_cli_consent_with_the_owner_state(self) -> None:
        code, out, opened = self.run_cli("login", "--owner", "ana")
        self.assertEqual(code, 0, out)
        [call] = [c for c in self.calls() if c["argv"] != ["version"]]
        sessions = str(self.ana_dir / ".config" / "colab-cli" / "sessions.json")
        self.assertEqual(call["argv"], ["--config", sessions, "sessions"])
        self.assertEqual(call["home"], str(self.ana_dir))
        self.assertNotIn("SECRET_SHOULD_NOT_LEAK", call["env"])
        self.assertIn("Ana", out)
        self.assertIn("browser", out.lower())
        self.assert_nothing_opened_inside_config_dirs(opened)

    def test_login_print_command_runs_nothing(self) -> None:
        code, out, _ = self.run_cli("login", "--owner", "ana", "--print-command")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.calls(), [])
        self.assertIn(f"HOME={self.ana_dir}", out)
        self.assertIn("--config", out)

    def test_login_passes_the_cli_failure_through(self) -> None:
        self.set_mode("signed-out")
        code, out, _ = self.run_cli("login", "--owner", "ana")
        self.assertNotEqual(code, 0)

    def test_login_for_an_owner_without_colab_refuses(self) -> None:
        code, out, _ = self.run_cli("login", "--owner", "cy")
        self.assertNotEqual(code, 0)
        self.assertIn("cy", out)
        code, out, _ = self.run_cli("login", "--owner", "nobody")
        self.assertNotEqual(code, 0)
        self.assertEqual(self.calls(), [])

    def test_login_without_the_cli_prints_the_pinned_install_command(self) -> None:
        with mock.patch.dict(os.environ, {"PATH": str(self.tmp / "empty")}):
            code, out, _ = self.run_cli("login", "--owner", "ana")
        self.assertNotEqual(code, 0)
        self.assertIn(colab.INSTALL_COMMAND, out)
        self.assertIn("google-colab-cli==0.8.0", colab.INSTALL_COMMAND)


class StatusTests(_Env):
    def test_status_reports_each_colab_owner_from_the_cli_exit_status(self) -> None:
        code, out, opened = self.run_cli("status", "--json")
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(payload["cli"]["found"], True)
        self.assertEqual(payload["cli"]["version"], "0.7.5")
        owners = {row["owner"]: row for row in payload["owners"]}
        self.assertEqual(sorted(owners), ["ana", "bo"])
        self.assertEqual(owners["ana"]["signedIn"], "yes")
        self.assertEqual(owners["ana"]["tier"], "pro")
        self.assertTrue(owners["ana"]["splitCampaignEligible"])
        self.assertFalse(owners["bo"]["splitCampaignEligible"])
        self.assertTrue(owners["ana"]["configDirExists"])
        probes = [c for c in self.calls() if c["argv"] != ["version"]]
        self.assertEqual(sorted(c["home"] for c in probes),
                         sorted([str(self.ana_dir), str(self.config / "papersmith" / "colab" / "bo")]))
        self.assert_nothing_opened_inside_config_dirs(opened)

    def test_status_signed_out_and_filtered_by_owner(self) -> None:
        self.set_mode("signed-out")
        code, out, _ = self.run_cli("status", "--owner", "ana")
        self.assertEqual(code, 0, out)
        self.assertIn("ana", out)
        self.assertIn("not signed in", out)
        self.assertNotIn("  bo:", out)
        self.assertEqual(len([c for c in self.calls() if c["argv"] != ["version"]]), 1)

    def test_status_times_out_rather_than_hanging(self) -> None:
        self.set_mode("hang")
        with mock.patch.object(colab, "STATUS_TIMEOUT_SECONDS", 1):
            code, out, _ = self.run_cli("status", "--owner", "ana", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["owners"][0]["signedIn"], "unknown")

    def test_status_without_the_cli(self) -> None:
        with mock.patch.dict(os.environ, {"PATH": str(self.tmp / "empty")}):
            code, out, _ = self.run_cli("status", "--json")
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertFalse(payload["cli"]["found"])
        self.assertEqual(payload["cli"]["install"], colab.INSTALL_COMMAND)
        self.assertEqual({row["signedIn"] for row in payload["owners"]}, {"unknown"})

    def test_a_missing_config_dir_is_reported_and_not_probed(self) -> None:
        import shutil
        shutil.rmtree(self.ana_dir)
        code, out, _ = self.run_cli("status", "--owner", "ana", "--json")
        row = json.loads(out)["owners"][0]
        self.assertFalse(row["configDirExists"])
        self.assertEqual(row["signedIn"], "no")
        self.assertEqual([c for c in self.calls() if c["argv"] != ["version"]], [])


class ConventionTests(unittest.TestCase):
    def test_the_state_directory_follows_xdg(self) -> None:
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/x/cfg"}):
            self.assertEqual(team.colab_config_dir("ana"), Path("/x/cfg/papersmith/colab/ana"))

    def test_the_login_ritual_is_one_module_constant(self) -> None:
        self.assertEqual(colab.LOGIN_ARGS, ("sessions",))
        self.assertEqual(colab.PINNED_VERSION, "0.8.0")


if __name__ == "__main__":
    unittest.main()


class InstallPinTests(unittest.TestCase):
    def test_one_install_line_for_the_cli_the_adapter_and_the_dashboard(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(repo / "skills" / "_core"))
        from command_center import terminal
        skill = (repo / "skills" / "remote-execution" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(colab.INSTALL_COMMAND, skill)
        self.assertEqual(terminal.COLAB_CLI_INSTALL, colab.INSTALL_COMMAND)
