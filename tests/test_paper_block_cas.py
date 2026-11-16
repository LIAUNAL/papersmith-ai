"""Compare-and-swap on a block's base digest (#185, odd/tasks/daprosero-backlog.md S7)
and the `humanize --draft` containment refusal naming `--replacement` (#184 item 1, S6.1).

`substitute`, `humanize --apply` and `write` accept `--expect-digest <sha256>`: the
digest the block's begin marker recorded when the caller read it (what `status`
lists). When the block's recorded digest differs, the call refuses
`BLOCK_CHANGED_SINCE_READ` and `main.tex` keeps every byte. Without the flag the
previous behaviour holds exactly.

Every test goes through `paper_cli.main`. The paper must sit inside the
repository (`PAPER_OUTSIDE_REPOSITORY`), so each fixture lives under the
git-ignored `.scratch/` directory and is removed afterwards.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))
import paper_cli  # noqa: E402

_BODY = "We study 12 metrics \\cite{smith2025}.\n"
_NEWER = "We study 12 metrics on two datasets \\cite{smith2025}.\n"


def _run_cli(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with mock.patch("sys.stdout", buf):
        exit_code = paper_cli.main(argv)
    return exit_code, json.loads(buf.getvalue())


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _main_tex(block_id: str, body: str) -> str:
    return (
        "\\documentclass{article}\n\\begin{document}\n"
        f"%% paper-writing block {block_id} begin sha256={_digest(body)}\n"
        f"{body}%% paper-writing block {block_id} end\n"
        "\\end{document}\n"
    )


class _PaperFixture(unittest.TestCase):
    block_id = "b1"

    def setUp(self) -> None:
        scratch_root = REPO / ".scratch"
        scratch_root.mkdir(exist_ok=True)
        holder = tempfile.TemporaryDirectory(dir=scratch_root, prefix="cas-")
        self.addCleanup(holder.cleanup)
        self.paper_dir = Path(holder.name) / "paper"
        self.paper_dir.mkdir()
        self.main_tex = self.paper_dir / "main.tex"
        self.main_tex.write_text(_main_tex(self.block_id, _BODY), encoding="utf-8")
        self.rel = str(self.paper_dir.relative_to(REPO))
        self.body_file = Path(holder.name) / "body.tex"
        self.body_file.write_text(_NEWER, encoding="utf-8")

    def read_digest(self) -> str:
        code, payload = _run_cli(["status", "--paper", self.rel])
        self.assertEqual(code, 0)
        return {b["id"]: b["digest"] for b in payload["blocks"]}[self.block_id]


class SubstituteExpectDigestTests(_PaperFixture):
    def test_substitute_writes_when_the_expected_digest_is_the_one_read(self) -> None:
        read = self.read_digest()
        code, payload = _run_cli(["substitute", "--paper", self.rel, "--block", "b1",
                                  "--body", str(self.body_file), "--expect-digest", read])
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["digest"], _digest(_NEWER))
        self.assertEqual(self.main_tex.read_text(encoding="utf-8"), _main_tex("b1", _NEWER))

    def test_substitute_refuses_when_the_block_changed_since_it_was_read(self) -> None:
        stale = self.read_digest()
        # A second session writes the block after this one read it.
        self.main_tex.write_text(_main_tex("b1", _NEWER), encoding="utf-8")
        before = self.main_tex.read_bytes()
        self.body_file.write_text("A stale rewrite of 12 metrics \\cite{smith2025}.\n", encoding="utf-8")
        code, payload = _run_cli(["substitute", "--paper", self.rel, "--block", "b1",
                                  "--body", str(self.body_file), "--expect-digest", stale])
        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], "BLOCK_CHANGED_SINCE_READ")
        self.assertIn(stale, payload["detail"])
        self.assertIn(_digest(_NEWER), payload["detail"])
        self.assertEqual(self.main_tex.read_bytes(), before)
        self.assertFalse((self.paper_dir / ".paper-writing" / "main.tex.prev").exists())

    def test_substitute_without_the_flag_behaves_as_before(self) -> None:
        # The other session's write still lands unguarded: the flag is opt-in.
        self.main_tex.write_text(_main_tex("b1", _NEWER), encoding="utf-8")
        replacement = "Previous behaviour: 12 metrics \\cite{smith2025}.\n"
        self.body_file.write_text(replacement, encoding="utf-8")
        code, payload = _run_cli(["substitute", "--paper", self.rel, "--block", "b1",
                                  "--body", str(self.body_file)])
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload, {"status": "ok", "command": "substitute", "block": "b1",
                                   "digest": _digest(replacement), "rendering": "unproven"})
        self.assertEqual(self.main_tex.read_text(encoding="utf-8"), _main_tex("b1", replacement))

    def test_a_malformed_expected_digest_is_a_usage_error(self) -> None:
        before = self.main_tex.read_bytes()
        with mock.patch("sys.stderr", io.StringIO()) as err, self.assertRaises(SystemExit) as ctx:
            paper_cli.main(["substitute", "--paper", self.rel, "--block", "b1",
                            "--body", str(self.body_file), "--expect-digest", "abc"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("--expect-digest", err.getvalue())
        self.assertEqual(self.main_tex.read_bytes(), before)

    def test_the_flag_is_documented_in_the_substitute_help(self) -> None:
        parser = paper_cli.build_parser()
        sub = next(a for a in parser._actions if a.dest == "command")
        self.assertIn("--expect-digest", sub.choices["substitute"].format_help())
        self.assertIn("--expect-digest", sub.choices["humanize"].format_help())
        self.assertIn("--expect-digest", sub.choices["write"].format_help())


class HumanizeExpectDigestTests(_PaperFixture):
    def test_humanize_apply_refuses_when_the_block_changed_since_it_was_read(self) -> None:
        stale = self.read_digest()
        self.main_tex.write_text(_main_tex("b1", _NEWER), encoding="utf-8")
        before = self.main_tex.read_bytes()
        code, payload = _run_cli(["humanize", "--paper", self.rel, "--block", "b1",
                                  "--replacement", "Here we study 12 metrics on two datasets \\cite{smith2025}.\n",
                                  "--apply", "--force", "--expect-digest", stale])
        self.assertEqual(code, 2)
        self.assertEqual(payload["code"], "BLOCK_CHANGED_SINCE_READ")
        self.assertEqual(self.main_tex.read_bytes(), before)

    def test_humanize_apply_writes_when_the_expected_digest_is_the_one_read(self) -> None:
        read = self.read_digest()
        draft = "Here we study 12 metrics \\cite{smith2025}.\n"
        code, payload = _run_cli(["humanize", "--paper", self.rel, "--block", "b1",
                                  "--replacement", draft, "--apply", "--force", "--expect-digest", read])
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["applied"])
        self.assertIn("Here we study 12 metrics", self.main_tex.read_text(encoding="utf-8"))


class WriteExpectDigestTests(_PaperFixture):
    block_id = "introduction.intro-context"

    def test_write_refuses_a_stale_base_before_any_gate_or_attempt(self) -> None:
        stale = self.read_digest()
        self.main_tex.write_text(_main_tex(self.block_id, _NEWER), encoding="utf-8")
        before = self.main_tex.read_bytes()
        code, payload = _run_cli(["write", "--paper", self.rel, "--section", "introduction",
                                  "--block", "intro-context", "--draft", "absent.json",
                                  "--audit", "absent.json", "--expect-digest", stale])
        self.assertEqual(code, 2)
        self.assertEqual(payload["code"], "BLOCK_CHANGED_SINCE_READ")
        self.assertEqual(self.main_tex.read_bytes(), before)
        self.assertFalse((self.paper_dir / ".paper-writing").exists())


class HumanizeDraftOutsideRepositoryTests(unittest.TestCase):
    def test_the_refusal_names_replacement_as_the_alternative(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            draft = Path(outside) / "draft.tex"
            draft.write_text(_BODY, encoding="utf-8")
            code, payload = _run_cli(["humanize", "--block", "b1", "--draft", str(draft)])
        self.assertEqual(code, 2)
        self.assertEqual(payload["code"], "PAPER_OUTSIDE_REPOSITORY")
        self.assertIn("--replacement", payload["detail"])
        self.assertIn(str(draft.resolve()), payload["detail"])


if __name__ == "__main__":
    unittest.main()
