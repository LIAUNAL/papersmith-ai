"""The per-user key store for the literature connectors (Asta, OpenAlex).

`skills/_core/api_keys.py` is loaded by path by the skill scripts, the dashboard
and `smith`, so it is tested the same way. Every case moves the store into a
throwaway directory with `PAPERSMITH_KEYS_DIR`, as the suite's conftest already
does for the whole run: no test may read or write the operator's own keys.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "skills" / "_core" / "api_keys.py"
POSIX = os.name != "nt"


def load_api_keys():
    name = "papersmith_api_keys"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


api_keys = load_api_keys()
KEY = "asta-key-0123456789abcdef"
OTHER = "openalex-key-ABCDEFGH"


class StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        self.dir = self.tmp / "keys"
        patcher = mock.patch.dict(os.environ, {api_keys.STORE_DIR_ENV: str(self.dir)})
        patcher.start()
        self.addCleanup(patcher.stop)
        for variable in ("ASTA_API_KEY", "OPENALEX_API_KEY"):
            os.environ.pop(variable, None)

    def export(self, variable: str, value: str) -> None:
        patcher = mock.patch.dict(os.environ, {variable: value})
        patcher.start()
        self.addCleanup(patcher.stop)


class ProviderTableTests(StoreCase):
    def test_the_two_providers_and_their_variables(self) -> None:
        assert api_keys.providers() == ("asta", "openalex")
        assert api_keys.env_var("asta") == "ASTA_API_KEY"
        assert api_keys.env_var("openalex") == "OPENALEX_API_KEY"
        assert api_keys.PROVIDERS["asta"]["license_url"] == "https://allenai.org/asta-corpus-license"
        assert api_keys.PROVIDERS["openalex"]["request_url"] == "https://openalex.org/settings/api-key"

    def test_an_unknown_provider_is_refused_by_name(self) -> None:
        for call in (lambda: api_keys.env_var("crossref"), lambda: api_keys.path("x"),
                     lambda: api_keys.store("x", KEY), lambda: api_keys.status("x")):
            with self.assertRaises(api_keys.KeyRefused) as caught:
                call()
            assert caught.exception.code == "UNKNOWN_PROVIDER"

    def test_the_store_directory_follows_the_override_then_xdg_then_home(self) -> None:
        assert api_keys.store_dir() == self.dir
        with mock.patch.dict(os.environ, {api_keys.STORE_DIR_ENV: "", "XDG_CONFIG_HOME": str(self.tmp)}):
            assert api_keys.store_dir() == self.tmp / "papersmith" / "keys"
        with mock.patch.dict(os.environ, {api_keys.STORE_DIR_ENV: "", "XDG_CONFIG_HOME": "",
                                          "HOME": str(self.tmp / "home")}):
            assert api_keys.store_dir() == self.tmp / "home" / ".config" / "papersmith" / "keys"


class StoreAndReadTests(StoreCase):
    def test_store_writes_a_private_file_in_a_private_directory(self) -> None:
        path = api_keys.store("asta", f"  {KEY}\n")

        assert path == self.dir / "asta"
        assert path.read_text(encoding="utf-8") == KEY + "\n"
        if POSIX:
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            assert stat.S_IMODE(self.dir.stat().st_mode) == 0o700
        assert api_keys.read("asta") == KEY
        assert api_keys.source("asta") == "store"
        assert api_keys.configured("asta") is True
        assert list(self.dir.glob(".asta.*")) == []  # no temporary file left behind

    def test_store_replaces_a_symlink_without_writing_through_it(self) -> None:
        self.dir.mkdir(mode=0o700)
        elsewhere = self.tmp / "elsewhere"
        elsewhere.write_text("someone else's file\n", encoding="utf-8")
        (self.dir / "asta").symlink_to(elsewhere)

        api_keys.store("asta", KEY)

        assert elsewhere.read_text(encoding="utf-8") == "someone else's file\n"
        assert not (self.dir / "asta").is_symlink()
        assert api_keys.read("asta") == KEY

    @unittest.skipUnless(POSIX, "POSIX symlink and mode semantics")
    def test_store_refuses_a_symlinked_directory(self) -> None:
        real = self.tmp / "real"
        real.mkdir()
        self.dir.symlink_to(real, target_is_directory=True)
        with self.assertRaises(api_keys.KeyRefused) as caught:
            api_keys.store("asta", KEY)
        assert caught.exception.code == "INSECURE_DIRECTORY"
        assert list(real.iterdir()) == []

    def test_a_directory_where_the_file_belongs_is_refused(self) -> None:
        (self.dir / "asta").mkdir(parents=True)
        for call in (lambda: api_keys.store("asta", KEY), lambda: api_keys.clear("asta")):
            with self.assertRaises(api_keys.KeyRefused) as caught:
                call()
            assert caught.exception.code == "NOT_A_FILE"

    @unittest.skipUnless(POSIX, "POSIX mode bits")
    def test_a_file_others_can_read_is_never_used(self) -> None:
        path = api_keys.store("asta", KEY)
        path.chmod(0o644)
        assert api_keys.read("asta") is None
        assert api_keys.status("asta")["problem"] == "insecure: mode 0644, expected 0600"

    @unittest.skipUnless(POSIX, "POSIX symlinks")
    def test_a_symlinked_key_file_is_never_used(self) -> None:
        self.dir.mkdir(mode=0o700)
        real = self.tmp / "real-key"
        real.write_text(KEY + "\n", encoding="utf-8")
        real.chmod(0o600)
        (self.dir / "asta").symlink_to(real)
        assert api_keys.read("asta") is None

    @unittest.skipUnless(POSIX and hasattr(os, "getuid"), "POSIX ownership")
    def test_a_file_owned_by_someone_else_is_never_used(self) -> None:
        api_keys.store("asta", KEY)
        with mock.patch.object(os, "getuid", return_value=os.getuid() + 1):
            assert api_keys.read("asta") is None
            assert api_keys.file_problem(self.dir / "asta") == "insecure: owned by another user"

    def test_an_exported_variable_wins_over_the_store(self) -> None:
        api_keys.store("asta", KEY)
        self.export("ASTA_API_KEY", "exported-key-99999999")
        assert api_keys.read("asta") == "exported-key-99999999"
        state = api_keys.status("asta")
        assert state["source"] == "env" and state["stored"] is True and state["shadowed"] is True

    def test_a_blank_or_malformed_export_does_not_count(self) -> None:
        api_keys.store("asta", KEY)
        for value, problem in (("   ", "blank"), ("has a space in it", "invalid")):
            with self.subTest(value=value):
                with mock.patch.dict(os.environ, {"ASTA_API_KEY": value}):
                    assert api_keys.read("asta") == KEY
                    assert api_keys.source("asta") == "store"
                    assert api_keys.status("asta")["env_problem"] == problem

    def test_nothing_configured_reads_as_none(self) -> None:
        assert api_keys.read("asta") is None
        assert api_keys.source("asta") == "none"
        state = api_keys.status("asta")
        assert state["configured"] is False and state["problem"] is None

    def test_read_never_raises(self) -> None:
        blocker = self.tmp / "a-file"
        blocker.write_text("x", encoding="utf-8")
        with mock.patch.dict(os.environ, {api_keys.STORE_DIR_ENV: str(blocker / "keys")}):
            assert api_keys.read("asta") is None
            assert api_keys.source("asta") == "none"
        with mock.patch.object(api_keys, "_stored_value", side_effect=RuntimeError("boom")):
            assert api_keys.read("asta") is None

    def test_clear_removes_the_file_and_never_follows_a_link(self) -> None:
        assert api_keys.clear("asta") is False
        api_keys.store("asta", KEY)
        assert api_keys.clear("asta") is True
        assert api_keys.read("asta") is None
        if POSIX:
            target = self.tmp / "target"
            target.write_text("keep me\n", encoding="utf-8")
            (self.dir / "asta").symlink_to(target)
            assert api_keys.clear("asta") is True
            assert target.read_text(encoding="utf-8") == "keep me\n"


class ValidationTests(StoreCase):
    def test_each_refusal_names_the_rule_never_the_value(self) -> None:
        cases = {"": "EMPTY", "   ": "EMPTY", "short": "TOO_SHORT", "x" * 513: "TOO_LONG",
                 "has a space-1234": "BAD_CHARACTERS", "line\nbreak-1234": "BAD_CHARACTERS",
                 "clé-unicode-1234": "BAD_CHARACTERS"}
        for value, code in cases.items():
            with self.subTest(code=code, length=len(value)):
                with self.assertRaises(api_keys.KeyRefused) as caught:
                    api_keys.store("asta", value)
                assert caught.exception.code == code
                if value.strip():
                    assert value.strip() not in str(caught.exception)
        assert not (self.dir / "asta").exists()

    def test_non_string_input_is_empty(self) -> None:
        with self.assertRaises(api_keys.KeyRefused):
            api_keys.validate(None)  # type: ignore[arg-type]


class NeverTheValueTests(StoreCase):
    def test_status_carries_no_key(self) -> None:
        api_keys.store("asta", KEY)
        self.export("OPENALEX_API_KEY", OTHER)
        rendered = json.dumps(api_keys.statuses())
        assert KEY not in rendered and OTHER not in rendered

    def test_export_command_names_the_file_never_the_key(self) -> None:
        api_keys.store("asta", KEY)
        path = str(self.dir / "asta")
        assert api_keys.export_command("asta", "bash") == f'export ASTA_API_KEY="$(cat "{path}")"'
        assert api_keys.export_command("asta", "fish") == f'set -gx ASTA_API_KEY (cat "{path}")'
        assert api_keys.export_command("asta", "powershell") == f'$env:ASTA_API_KEY = Get-Content "{path}"'
        for shell in ("bash", "zsh", "sh", "fish", "powershell"):
            assert KEY not in api_keys.export_command("asta", shell)


class RedactionAndSessionTests(StoreCase):
    def test_secret_values_and_scrub_cover_stored_and_exported_keys(self) -> None:
        api_keys.store("asta", KEY)
        self.export("OPENALEX_API_KEY", OTHER)
        assert api_keys.secret_values() == (KEY, OTHER)  # longest first
        text = f"curl -H 'x-api-key: {KEY}' 'https://x/?api_key={OTHER}'"
        scrubbed = api_keys.scrub(text)
        assert KEY not in scrubbed and OTHER not in scrubbed
        assert scrubbed.count("[REDACTED]") == 2

    def test_session_env_adds_stored_keys_the_session_does_not_export(self) -> None:
        api_keys.store("asta", KEY)
        api_keys.store("openalex", OTHER)
        assert api_keys.session_env({}) == {"ASTA_API_KEY": KEY, "OPENALEX_API_KEY": OTHER}
        assert api_keys.session_env({"ASTA_API_KEY": "mine-exported-1234"}) == {"OPENALEX_API_KEY": OTHER}
        assert api_keys.session_env({"ASTA_API_KEY": "  "}) == {"ASTA_API_KEY": KEY,
                                                                "OPENALEX_API_KEY": OTHER}

    @unittest.skipUnless(POSIX, "POSIX mode bits")
    def test_session_env_ignores_an_insecure_file(self) -> None:
        api_keys.store("asta", KEY).chmod(0o640)
        assert api_keys.session_env({}) == {}


class ParityAndShapeTests(StoreCase):
    @unittest.skipUnless(POSIX, "POSIX file checks")
    def test_file_checks_match_the_kaggle_token_checks(self) -> None:
        """Two copies of one rule (the skills cannot import `src/`): held equal."""
        from papersmith.core.kaggle_mcp import token_file_problem

        self.dir.mkdir(mode=0o700)
        private = self.dir / "private"
        private.write_text(KEY, encoding="utf-8")
        private.chmod(0o600)
        loose = self.dir / "loose"
        loose.write_text(KEY, encoding="utf-8")
        loose.chmod(0o644)
        link = self.dir / "link"
        link.symlink_to(private)
        folder = self.dir / "folder"
        folder.mkdir()
        linked_dir = self.tmp / "linked"
        linked_dir.symlink_to(self.dir, target_is_directory=True)
        cases = [private, loose, link, folder, self.dir / "absent", linked_dir / "private"]
        for case in cases:
            with self.subTest(case=case.name):
                assert api_keys.file_problem(case) == token_file_problem(case)

    def test_it_imports_only_the_standard_library(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                roots.add(node.module.split(".")[0])
        assert roots <= set(sys.stdlib_module_names), roots - set(sys.stdlib_module_names)

    def test_the_suite_never_reads_the_operators_store(self) -> None:
        """conftest moves the store for the whole run; a test that forgot to
        would otherwise read real keys."""
        conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
        assert 'os.environ["PAPERSMITH_KEYS_DIR"] = tempfile.mkdtemp(' in conftest
        assert '"ASTA_API_KEY", "OPENALEX_API_KEY"' in conftest


if __name__ == "__main__":
    unittest.main()
