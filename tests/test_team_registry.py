"""`smith team list|add|remove`: the team registry `.papersmith/team.json`.

One account per person per service: every member is a distinct owner who
attests owning and operating the accounts listed under them. The registry
holds no secret; it is git-ignored because it names people.
"""

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

from papersmith.cli import main  # noqa: E402
from papersmith.core import team  # noqa: E402


class _Env(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.config = self.tmp / "config"
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.home),
                                               "XDG_CONFIG_HOME": str(self.config)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ws = self.tmp / "ws"
        (self.ws / ".papersmith").mkdir(parents=True)
        (self.ws / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        self.registry = self.ws / ".papersmith" / "team.json"

    def run_cli(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = main(["team", *argv, "--workspace", str(self.ws)])
        return code, out.getvalue()

    def add(self, *extra: str) -> tuple[int, str]:
        return self.run_cli("add", *extra)

    def members(self) -> list[dict]:
        return json.loads(self.registry.read_text(encoding="utf-8"))["members"]


class AddTests(_Env):
    def test_add_records_a_member_in_the_declared_schema(self) -> None:
        code, out = self.add("--owner", "ana", "--name", "Ana Pérez",
                             "--kaggle-username", "ana-k", "--colab", "--colab-tier", "pro",
                             "--attest")
        self.assertEqual(code, 0, out)
        data = json.loads(self.registry.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 1)
        [member] = data["members"]
        config_dir = self.config / "papersmith" / "colab" / "ana"
        self.assertEqual(member["owner"], "ana")
        self.assertEqual(member["displayName"], "Ana Pérez")
        self.assertRegex(member["attestedAt"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(member["attestation"],
                         "owns and operates exactly one account per service listed here")
        self.assertEqual(member["accounts"], {
            "kaggle": {"username": "ana-k"},
            "colab": {"tier": "pro", "configDir": str(config_dir)}})
        self.assertTrue(config_dir.is_dir())
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(config_dir.stat().st_mode), 0o700)

    def test_a_member_may_list_one_service_only(self) -> None:
        code, out = self.add("--owner", "bo", "--name", "Bo", "--kaggle-username", "bo-k", "--attest")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.members()[0]["accounts"], {"kaggle": {"username": "bo-k"}})
        self.assertFalse((self.config / "papersmith" / "colab" / "bo").exists())

    def test_add_without_attest_refuses_and_writes_nothing(self) -> None:
        code, out = self.add("--owner", "ana", "--name", "Ana", "--kaggle-username", "ana-k")
        self.assertNotEqual(code, 0)
        self.assertIn("--attest", out)
        self.assertFalse(self.registry.exists())

    def test_add_without_any_service_refuses(self) -> None:
        code, out = self.add("--owner", "ana", "--name", "Ana", "--attest")
        self.assertNotEqual(code, 0)
        self.assertFalse(self.registry.exists())

    def test_colab_needs_its_tier_and_a_known_one(self) -> None:
        code, _ = self.add("--owner", "ana", "--name", "Ana", "--colab", "--attest")
        self.assertNotEqual(code, 0)
        code, _ = self.add("--owner", "ana", "--name", "Ana", "--colab-tier", "pro", "--attest")
        self.assertNotEqual(code, 0)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.add("--owner", "ana", "--name", "Ana", "--colab", "--colab-tier", "gold",
                         "--attest")
        self.assertFalse(self.registry.exists())

    def test_an_invalid_owner_slug_refuses(self) -> None:
        for slug in ("Ana", "a b", "../x", "", "x" * 41):
            code, _ = self.add("--owner", slug, "--name", "N", "--kaggle-username", "u", "--attest")
            self.assertNotEqual(code, 0, slug)
        self.assertFalse(self.registry.exists())

    def test_duplicate_owner_refuses(self) -> None:
        self.assertEqual(self.add("--owner", "ana", "--name", "Ana", "--kaggle-username", "a1",
                                  "--attest")[0], 0)
        code, out = self.add("--owner", "ana", "--name", "Ana 2", "--kaggle-username", "a2", "--attest")
        self.assertNotEqual(code, 0)
        self.assertIn("ana", out)
        self.assertEqual(len(self.members()), 1)

    def test_the_same_kaggle_username_under_two_owners_refuses(self) -> None:
        self.assertEqual(self.add("--owner", "ana", "--name", "Ana", "--kaggle-username", "shared",
                                  "--attest")[0], 0)
        code, out = self.add("--owner", "bo", "--name", "Bo", "--kaggle-username", "Shared", "--attest")
        self.assertNotEqual(code, 0)
        self.assertIn("one account per person", out)
        self.assertEqual([m["owner"] for m in self.members()], ["ana"])

    def test_the_same_colab_config_dir_under_two_owners_refuses(self) -> None:
        config_dir = self.config / "papersmith" / "colab" / "bo"
        self.registry.write_text(json.dumps({"schema": 1, "members": [{
            "owner": "ana", "displayName": "Ana", "attestedAt": "2026-10-25",
            "attestation": team.ATTESTATION,
            "accounts": {"colab": {"tier": "pro", "configDir": str(config_dir)}}}]}), encoding="utf-8")
        code, out = self.add("--owner", "bo", "--name", "Bo", "--colab", "--colab-tier", "pro", "--attest")
        self.assertNotEqual(code, 0)
        self.assertIn("configDir", out)
        self.assertEqual(len(self.members()), 1)

    def test_add_git_ignores_the_registry_once(self) -> None:
        self.add("--owner", "ana", "--name", "Ana", "--kaggle-username", "a1", "--attest")
        self.add("--owner", "bo", "--name", "Bo", "--kaggle-username", "b1", "--attest")
        lines = (self.ws / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines.count(".papersmith/team.json"), 1)
        self.assertIn("node_modules/", lines)

    def test_add_with_email_records_email_and_validates_format(self) -> None:
        code, out = self.add("--owner", "ana", "--name", "Ana", "--email", "bad-email",
                             "--kaggle-username", "a1", "--attest")
        self.assertNotEqual(code, 0)
        self.assertIn("not a valid email address", out)
        code, out = self.add("--owner", "ana", "--name", "Ana", "--email", "ana@example.com",
                             "--kaggle-username", "a1", "--attest")
        self.assertEqual(code, 0, out)
        [member] = self.members()
        self.assertEqual(member.get("email"), "ana@example.com")

    def test_multiple_accounts_for_same_service_allowed_with_distinct_emails(self) -> None:
        code, out = self.add("--owner", "ana-work", "--name", "Ana Work", "--email", "ana@work.org",
                             "--kaggle-username", "ana_work", "--attest")
        self.assertEqual(code, 0, out)
        code, out = self.add("--owner", "ana-personal", "--name", "Ana Personal", "--email", "ana@personal.com",
                             "--kaggle-username", "ana_pers", "--attest")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.members()), 2)

    def test_duplicate_email_for_same_service_refuses(self) -> None:
        self.add("--owner", "ana-work", "--name", "Ana Work", "--email", "ana@shared.org",
                 "--kaggle-username", "ana_work", "--attest")
        code, out = self.add("--owner", "ana-other", "--name", "Ana Other", "--email", "ana@shared.org",
                             "--kaggle-username", "ana_other", "--attest")
        self.assertNotEqual(code, 0)
        self.assertIn("already belongs to owner 'ana-work' for Kaggle", out)
        self.assertEqual(len(self.members()), 1)

    def test_same_email_across_different_services_allowed(self) -> None:
        self.add("--owner", "ana-k", "--name", "Ana", "--email", "ana@shared.org",
                 "--kaggle-username", "ana_work", "--attest")
        code, out = self.add("--owner", "ana-c", "--name", "Ana", "--email", "ana@shared.org",
                             "--colab", "--colab-tier", "pro", "--attest")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.members()), 2)

    def test_add_outside_a_workspace_refuses(self) -> None:
        other = self.tmp / "plain"
        other.mkdir()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = main(["team", "add", "--owner", "ana", "--name", "Ana", "--kaggle-username", "a",
                         "--attest", "--workspace", str(other)])
        self.assertNotEqual(code, 0)
        self.assertFalse((other / ".papersmith").exists())


class ListTests(_Env):
    def test_list_prints_members_and_no_secret(self) -> None:
        self.add("--owner", "ana", "--name", "Ana", "--kaggle-username", "ana-k",
                 "--colab", "--colab-tier", "free", "--attest")
        code, out = self.run_cli("list")
        self.assertEqual(code, 0, out)
        self.assertIn("ana", out)
        self.assertIn("ana-k", out)
        self.assertIn("free", out)
        code, out = self.run_cli("list", "--json")
        payload = json.loads(out)
        self.assertEqual(payload["members"][0]["owner"], "ana")
        self.assertNotIn("token", out.lower())

    def test_list_includes_email_when_present(self) -> None:
        self.add("--owner", "ana", "--name", "Ana", "--email", "ana@example.com",
                 "--kaggle-username", "ana-k", "--attest")
        code, out = self.run_cli("list")
        self.assertEqual(code, 0, out)
        self.assertIn("ana@example.com", out)
        code, out = self.run_cli("list", "--json")
        payload = json.loads(out)
        self.assertEqual(payload["members"][0]["email"], "ana@example.com")

    def test_list_on_an_empty_registry(self) -> None:
        code, out = self.run_cli("list")
        self.assertEqual(code, 0, out)
        self.assertIn("no team members", out.lower())

    def test_list_flags_stored_kaggle_usernames_no_owner_claims(self) -> None:
        self.add("--owner", "ana", "--name", "Ana", "--kaggle-username", "ana-k", "--attest")
        with mock.patch.object(team, "stored_kaggle_usernames", return_value=["ana-k", "ghost"]):
            code, out = self.run_cli("list", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["unmappedKaggleUsernames"], ["ghost"])
        with mock.patch.object(team, "stored_kaggle_usernames", return_value=["ana-k", "ghost"]):
            code, out = self.run_cli("list")
        self.assertIn("ghost", out)
        self.assertIn("no owner", out)

    def test_stored_usernames_come_from_the_accounts_skill_list_verb(self) -> None:
        script = self.ws / "skills" / "kaggle-accounts" / "scripts" / "accounts_cli.py"
        script.parent.mkdir(parents=True)
        script.write_text(
            "import json, sys\n"
            "assert sys.argv[1:] == ['list', '--json'], sys.argv\n"
            "print(json.dumps({'accounts': [{'username': 'u1'}, {'username': 'u2'}]}))\n",
            encoding="utf-8")
        self.assertEqual(team.stored_kaggle_usernames(self.ws), ["u1", "u2"])

    def test_stored_usernames_without_the_skill_are_empty(self) -> None:
        self.assertEqual(team.stored_kaggle_usernames(self.ws), [])


class RemoveTests(_Env):
    def test_remove_deletes_the_entry_and_never_the_credentials(self) -> None:
        self.add("--owner", "ana", "--name", "Ana", "--kaggle-username", "ana-k",
                 "--colab", "--colab-tier", "pro", "--attest")
        config_dir = self.config / "papersmith" / "colab" / "ana"
        marker = config_dir / "keep-me"
        marker.write_text("x", encoding="utf-8")
        code, out = self.run_cli("remove", "--owner", "ana")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.members(), [])
        self.assertTrue(marker.exists())
        self.assertIn(str(config_dir), out)
        self.assertIn("ana-k", out)

    def test_removing_an_unknown_owner_refuses(self) -> None:
        code, out = self.run_cli("remove", "--owner", "nobody")
        self.assertNotEqual(code, 0)
        self.assertIn("nobody", out)


if __name__ == "__main__":
    unittest.main()


class ReusedStateDirTests(unittest.TestCase):
    def test_re_adding_an_owner_whose_state_dir_exists_warns(self) -> None:
        import contextlib, io, tempfile, unittest.mock
        from papersmith.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(os.path.realpath(tmp))
            ws = tmp / "ws"
            (ws / ".papersmith").mkdir(parents=True)
            with unittest.mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp / "cfg"), "HOME": str(tmp / "home")}):
                state = tmp / "cfg" / "papersmith" / "colab" / "cai"
                state.mkdir(parents=True, mode=0o700)
                (tmp / "cfg").chmod(0o700)
                out = io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                    code = main(["team", "add", "--workspace", str(ws), "--owner", "cai", "--name", "Cai",
                                 "--colab", "--colab-tier", "free", "--attest"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("already existed", out.getvalue())
