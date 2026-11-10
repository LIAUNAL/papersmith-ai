"""A configured API key never leaves through a side door.

A bare Asta or OpenAlex key has no prefix a secret pattern knows, so the paths
that copy text out of a session mask it literally: the AI-history archive (and,
through `redact_public`, the GitHub-Pages snapshot), the journal CLI's error
tail the dashboard shows, and the MCP bridge's child environment.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith.mcp import bridge
from skills._core.command_center import ai_archive, server

from test_api_keys import KEY, OTHER, load_api_keys

api_keys = load_api_keys()


class LeakCase(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        patcher = mock.patch.dict(os.environ, {api_keys.STORE_DIR_ENV: str(self.tmp / "keys")})
        patcher.start()
        self.addCleanup(patcher.stop)
        for variable in ("ASTA_API_KEY", "OPENALEX_API_KEY"):
            os.environ.pop(variable, None)
        self.forget()
        self.addCleanup(self.forget)

    @staticmethod
    def forget() -> None:
        """The archive reads the keys at most every few seconds; start fresh."""
        ai_archive._KEY_NEEDLES.update(at=float("-inf"), values=())


class ArchiveTests(LeakCase):
    def test_a_stored_and_an_exported_key_are_masked_in_archived_text(self) -> None:
        api_keys.store("asta", KEY)
        with mock.patch.dict(os.environ, {"OPENALEX_API_KEY": OTHER}):
            self.forget()
            text = (f"I ran curl -H 'x-api-key: {KEY}' and then "
                    f"https://api.openalex.org/works?api_key={OTHER}&per-page=1")
            masked = ai_archive.redact(text)
        assert KEY not in masked and OTHER not in masked
        assert masked.count(ai_archive.REDACTED) >= 2

    def test_the_public_copy_masks_it_too(self) -> None:
        api_keys.store("openalex", OTHER)
        self.forget()
        public = ai_archive.redact_public(f"export OPENALEX_API_KEY={OTHER}", code=True)
        assert OTHER not in public

    def test_no_key_configured_changes_nothing(self) -> None:
        text = "an ordinary sentence with no secret in it"
        assert ai_archive.redact(text) == text

    def test_the_needles_live_only_in_memory(self) -> None:
        api_keys.store("asta", KEY)
        self.forget()
        ai_archive.redact("x")
        source = Path(ai_archive.__file__).read_text(encoding="utf-8")
        assert "_KEY_NEEDLES" in source and "json.dumps(_KEY_NEEDLES" not in source
        assert ai_archive._KEY_NEEDLES["values"] == (KEY,)


class BridgeTests(unittest.TestCase):
    def test_the_mcp_bridge_never_forwards_either_key(self) -> None:
        for name in ("ASTA_API_KEY", "OPENALEX_API_KEY"):
            assert bridge.env_allowed(name) is False
        env = bridge.child_env({"ASTA_API_KEY": KEY, "OPENALEX_API_KEY": OTHER, "PATH": "/bin"})
        assert "ASTA_API_KEY" not in env and "OPENALEX_API_KEY" not in env and env["PATH"] == "/bin"


class JournalTailTests(LeakCase):
    def test_an_error_tail_that_echoes_a_key_is_masked(self) -> None:
        api_keys.store("openalex", OTHER)
        echoed = subprocess.CompletedProcess(["x"], 2, "", f"rejected api_key={OTHER}: HTTP 401")
        with mock.patch.object(server.subprocess, "run", return_value=echoed):
            body, status = server._run_journal_cli(self.tmp, ["search"], timeout=5)
        assert status == 502
        assert OTHER not in body["message"] and "[REDACTED]" in body["message"]


class GitignoreTests(unittest.TestCase):
    def test_the_forge_ignores_dotenv_files_like_every_workspace(self) -> None:
        root = Path(__file__).resolve().parents[1]
        lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert ".env*" in lines


if __name__ == "__main__":
    unittest.main()
