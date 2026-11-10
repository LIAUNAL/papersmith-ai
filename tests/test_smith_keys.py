"""`smith keys`: the terminal side of the per-user key store.

The store's rules are tested in tests/test_api_keys.py; these pin what the
command adds on top: it never takes a key as an argument, never prompts with an
echo, never prints a value, makes no network call unless asked, and works
outside a workspace.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith import cli
from papersmith.core import doctor, keys as keys_command

from test_api_keys import KEY, OTHER, load_api_keys

api_keys = load_api_keys()
ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str], *, stdin: str | None = None, tty: bool = False) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    fake_stdin = io.StringIO(stdin or "")
    fake_stdin.isatty = lambda: tty  # type: ignore[method-assign]
    with mock.patch("sys.stdin", fake_stdin), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exc:  # argparse
            code = int(exc.code or 0)
    return code, out.getvalue(), err.getvalue()


class KeysCommandCase(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        self.store = self.tmp / "keys"
        patcher = mock.patch.dict(os.environ, {api_keys.STORE_DIR_ENV: str(self.store)})
        patcher.start()
        self.addCleanup(patcher.stop)
        for variable in ("ASTA_API_KEY", "OPENALEX_API_KEY"):
            os.environ.pop(variable, None)
        # Outside any workspace: the command does not need one.
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)
        # No test here may reach the network unless it says so.
        opener = mock.patch.object(keys_command.load_api_keys()._OPENER, "open",
                                   side_effect=AssertionError("network call"))
        opener.start()
        self.addCleanup(opener.stop)


class SetTests(KeysCommandCase):
    def test_stdin_stores_a_private_key_and_prints_no_value(self) -> None:
        code, out, err = run(["keys", "set", "asta", "--stdin"], stdin=KEY + "\n")

        assert code == 0, err
        assert (self.store / "asta").read_text(encoding="utf-8") == KEY + "\n"
        if os.name != "nt":
            assert oct((self.store / "asta").stat().st_mode & 0o777) == oct(0o600)
        assert KEY not in out + err
        assert "stored:" in out and "outside the dashboard:" in out

    def test_without_a_terminal_it_refuses_rather_than_echo(self) -> None:
        code, out, err = run(["keys", "set", "asta"], stdin=KEY + "\n", tty=False)
        assert code == 1
        assert "--stdin" in err
        assert not (self.store / "asta").exists()

    def test_the_hidden_prompt_path(self) -> None:
        with mock.patch("getpass.getpass", return_value=KEY) as prompt:
            code, out, err = run(["keys", "set", "asta"], tty=True)
        assert code == 0, err
        prompt.assert_called_once()
        assert api_keys.PROVIDERS["asta"]["request_url"] in out
        assert "non-commercial" in out
        assert api_keys.read("asta") == KEY

    def test_a_key_is_never_a_command_line_argument(self) -> None:
        code, _out, _err = run(["keys", "set", "asta", KEY])
        assert code == 2
        assert not (self.store / "asta").exists()

    def test_an_invalid_key_is_refused_without_echoing_it(self) -> None:
        code, out, err = run(["keys", "set", "openalex", "--stdin"], stdin="bad key value\n")
        assert code == 1
        assert "nothing was stored" in err and "bad key value" not in out + err

    def test_verify_stores_only_an_accepted_key(self) -> None:
        refused = {"provider": "asta", "state": "refused", "detail": "Asta refused the key",
                   "source": "given", "budget": None, "elapsed_ms": 1}
        with mock.patch.object(api_keys, "verify", return_value=refused), \
                mock.patch.object(keys_command.load_api_keys(), "verify", return_value=refused):
            code, _out, err = run(["keys", "set", "asta", "--stdin", "--verify"], stdin=KEY)
        assert code == 1 and "nothing was" in err
        assert not (self.store / "asta").exists()

        accepted = dict(refused, state="ok", detail="key accepted")
        with mock.patch.object(keys_command.load_api_keys(), "verify", return_value=accepted):
            code, out, err = run(["keys", "set", "asta", "--stdin", "--verify", "--json"], stdin=KEY)
        assert code == 0, err
        payload = json.loads(out)
        assert payload["verify"]["state"] == "ok" and payload["status"]["source"] == "store"
        assert KEY not in out


class StatusTests(KeysCommandCase):
    def test_status_is_offline_and_never_prints_a_key(self) -> None:
        api_keys.store("asta", KEY)
        with mock.patch.dict(os.environ, {"OPENALEX_API_KEY": OTHER}):
            code, out, err = run(["keys", "status"])
        assert code == 0, err
        assert "asta key: configured (stored at" in out
        assert "openalex key: configured (exported OPENALEX_API_KEY)" in out
        assert KEY not in out and OTHER not in out

    def test_one_provider_as_json_is_its_status_object(self) -> None:
        """The shape the sota-scout gate parses: `configured` and `source`."""
        code, out, _err = run(["keys", "status", "asta", "--json"])
        assert code == 0
        state = json.loads(out)
        assert state["provider"] == "asta" and state["configured"] is False and state["source"] == "none"
        api_keys.store("asta", KEY)
        state = json.loads(run(["keys", "status", "asta", "--json"])[1])
        assert state["configured"] is True and state["source"] == "store"
        with mock.patch.dict(os.environ, {"ASTA_API_KEY": KEY}):
            state = json.loads(run(["keys", "status", "asta", "--json"])[1])
        assert state["source"] == "env" and KEY not in json.dumps(state)

    def test_all_providers_as_json_is_an_envelope(self) -> None:
        payload = json.loads(run(["keys", "status", "--json"])[1])
        assert [state["provider"] for state in payload["keys"]] == ["asta", "openalex"]
        assert payload["store_dir"] == str(self.store) and payload["override"] is True

    def test_verify_with_nothing_configured_fails_without_calling_out(self) -> None:
        code, out, _err = run(["keys", "status", "--verify"])
        assert code == 1 and "skipped" in out
        assert run(["keys", "status", "asta", "--verify"])[0] == 1

    def test_verify_reports_each_configured_key(self) -> None:
        api_keys.store("openalex", OTHER)
        ok = {"provider": "openalex", "state": "ok", "detail": "key accepted", "source": "store",
              "budget": {"remaining_usd": "0.9", "limit_usd": "1"}, "elapsed_ms": 3}
        with mock.patch.object(keys_command.load_api_keys(), "verify", return_value=ok) as verify:
            code, out, _err = run(["keys", "status", "--verify"])
        assert code == 0
        verify.assert_called_once_with("openalex")
        assert "verify openalex: ok (key accepted; budget 0.9 of 1 USD today)" in out


class ClearTests(KeysCommandCase):
    def test_clear_removes_the_stored_key(self) -> None:
        api_keys.store("asta", KEY)
        code, out, _err = run(["keys", "clear", "asta"])
        assert code == 0 and "removed:" in out
        assert api_keys.read("asta") is None
        code, out, _err = run(["keys", "clear", "asta"])
        assert code == 0 and "nothing to remove" in out

    def test_clear_notes_a_variable_still_exported(self) -> None:
        with mock.patch.dict(os.environ, {"ASTA_API_KEY": KEY}):
            out = run(["keys", "clear", "asta"])[1]
        assert "still exported" in out


class ShapeTests(KeysCommandCase):
    def test_the_parser_knows_exactly_the_stores_providers(self) -> None:
        assert keys_command.KNOWN_PROVIDERS == tuple(api_keys.PROVIDERS)

    def test_the_command_is_documented(self) -> None:
        docs = (ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
        assert "| `keys` |" in docs
        assert "### `smith keys {set,status,clear} [<provider>]`" in docs


class DoctorKeyRowsTests(KeysCommandCase):
    def rows(self) -> dict[str, dict[str, str]]:
        return {row["item"]: row for row in keys_command.key_rows()}

    def test_rows_are_offline_tools_rows_that_never_fail(self) -> None:
        rows = self.rows()
        assert set(rows) == {"asta key", "openalex key"}
        assert all(row["area"] == "tools" for row in rows.values())
        assert rows["asta key"]["state"] == "absent"
        assert "OpenAlex stays the default" in rows["asta key"]["detail"]

        api_keys.store("asta", KEY)
        with mock.patch.dict(os.environ, {"OPENALEX_API_KEY": OTHER}):
            rows = self.rows()
        assert rows["asta key"]["state"] == "ok" and "stored" in rows["asta key"]["detail"]
        assert rows["openalex key"]["state"] == "ok" and "exported" in rows["openalex key"]["detail"]
        assert KEY not in json.dumps(rows) and OTHER not in json.dumps(rows)

    @unittest.skipUnless(os.name != "nt", "POSIX mode bits")
    def test_an_insecure_file_warns(self) -> None:
        api_keys.store("asta", KEY).chmod(0o644)
        row = self.rows()["asta key"]
        assert row["state"] == "warn" and "chmod 600" in row["detail"]

    def test_build_report_carries_the_key_rows(self) -> None:
        assert doctor.key_rows is keys_command.key_rows


if __name__ == "__main__":
    unittest.main()
