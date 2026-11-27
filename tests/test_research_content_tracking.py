"""`track_research_content`: a workspace may opt in to versioning its research.

By default the managed `.gitignore` block keeps research content local
("structure versioned, content local"), and that default must not move by a
byte. A workspace that sets `track_research_content: true` in its
`papersmith.yaml` gets a block that versions the paper, proposals,
experiments, guidance and protocol, and still ignores what a build or a run
regenerates. `smith upgrade` renders the block from the current setting, both
ways, and the drift check accepts each render for its own setting.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import subprocess
import unittest
from pathlib import Path

from papersmith.cli import main
from papersmith.core import status as status_module
from papersmith.generators import (
    MANAGED_BLOCK_BEGIN,
    MANAGED_BLOCK_END,
    context_for_workspace,
    render_files,
)

from test_upgrade_v0_13_0_workspace import run_upgrade
from workspace_series import make_workspace, new_tmp

#: SHA-256 of the default managed block as 0.85.0 rendered it. The opt-in must
#: leave the private block byte-identical; a deliberate edit of the private
#: section of `gitignore.tpl` updates this digest in the same change.
PRIVATE_BLOCK_SHA256 = "da0aa2564824035b0414ec58b291d528ba0f4b06157af45494ef26585a35dfa7"

#: Research sources a tracking workspace versions.
TRACKED_SOURCES = (
    "paper/main.tex",
    "paper/figures/fig-1.pdf",
    "paper/supplement/supplement.tex",
    "paper/venues/ieee/main.tex",
    "paper/.paper-writing/references.json",
    "proposals/research-concept-r01.md",
    "experiments/protocol.md",
    "guidance/paper-guide/notes.md",
    "protocol/study-protocol.md",
    "sota-pool/atlas.json",
    "sota-pool/candidates.json",
)

#: What a tracking workspace still keeps local: build products, backups,
#: separate repositories, worker returns, and local state.
STILL_IGNORED = (
    "paper/main.aux",
    "paper/main.log",
    "paper/main.out",
    "paper/main.fdb_latexmk",
    "paper/main.fls",
    "paper/main.synctex.gz",
    "paper/main.blg",
    "paper/main.spl",
    "paper/main.toc",
    "paper/main.lof",
    "paper/main.lot",
    "paper/venues/ieee/main.aux",
    "paper/venues/ieee/main.log",
    "paper/.paper-writing/main.tex.before-20261127T120000Z",
    "paper/scripts/__pycache__/plot.cpython-312.pyc",
    "sota-pool/atlas.html",
    "implementations/my-repo/src/model.py",
    "kaggle-inbox/run-1/output.json",
    ".scratch/runs/x.log",
    ".papersmith/team.json",
    ".papersmith/math-tutor/thread.json",
    "analysis/streams/run-1.stdout",
    ".proposal-deliberation/state.json",
)


def _git(workspace: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *argv], cwd=workspace, capture_output=True, text=True,
                          check=False)


def _ignored(workspace: Path, relpath: str) -> bool:
    return _git(workspace, "check-ignore", "-q", "--no-index", relpath).returncode == 0


def _set_tracking(workspace: Path, value: str | None) -> None:
    """Write ``track_research_content: <value>`` into papersmith.yaml, or
    remove the key when ``value`` is None."""
    path = workspace / "papersmith.yaml"
    lines = [line for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
             if not line.startswith("track_research_content:")]
    if value is not None:
        lines.append(f"track_research_content: {value}\n")
    path.write_text("".join(lines), encoding="utf-8")


def _block(text: str) -> str:
    begin = text.index(MANAGED_BLOCK_BEGIN)
    end = text.index(MANAGED_BLOCK_END) + len(MANAGED_BLOCK_END) + 1
    return text[begin:end]


def _rendered(workspace: Path) -> str:
    with contextlib.redirect_stderr(io.StringIO()):
        return render_files(workspace, context_for_workspace(workspace))[".gitignore"]


def _drifted(workspace: Path) -> list[str]:
    """`status`'s drift: the file against what the framework last wrote."""
    with contextlib.redirect_stderr(io.StringIO()):
        return status_module.status(workspace)["framework"]["drifted_files"]


def _audit_drift(workspace: Path) -> str:
    """`audit --check-drift`'s report when it fails, "" when it passes: it
    also renders the block from the current setting and compares the two."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        rc = main(["audit", str(workspace), "--check-drift"])
    return "" if rc == 0 else out.getvalue()


class ResearchContentTrackingTests(unittest.TestCase):

    def workspace(self) -> Path:
        workspace = make_workspace(new_tmp(self))
        _git(workspace, "init", "-q")
        return workspace

    def test_the_default_block_is_byte_identical_to_the_private_render(self) -> None:
        workspace = self.workspace()
        text = (workspace / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), PRIVATE_BLOCK_SHA256)
        for value in (None, "false"):
            with self.subTest(track_research_content=value):
                _set_tracking(workspace, value)
                self.assertEqual(_rendered(workspace), text)
        for relpath in TRACKED_SOURCES[:-2]:
            with self.subTest(relpath=relpath):
                self.assertTrue(_ignored(workspace, relpath), relpath)

    def test_a_fresh_workspace_declares_the_setting_off(self) -> None:
        workspace = self.workspace()
        yaml = (workspace / "papersmith.yaml").read_text(encoding="utf-8")
        self.assertIn("\ntrack_research_content: false\n", yaml)

    def test_tracking_versions_the_sources_and_ignores_the_build_products(self) -> None:
        workspace = self.workspace()
        _set_tracking(workspace, "true")
        run_upgrade(workspace)
        text = (workspace / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(text, _rendered(workspace))
        self.assertNotIn("\npaper/*\n", text)
        self.assertNotIn("#@", text)
        for relpath in TRACKED_SOURCES:
            with self.subTest(tracked=relpath):
                self.assertFalse(_ignored(workspace, relpath), relpath)
        for relpath in STILL_IGNORED:
            with self.subTest(ignored=relpath):
                self.assertTrue(_ignored(workspace, relpath), relpath)

    def test_toggling_and_upgrading_rewrites_the_block_both_ways(self) -> None:
        workspace = self.workspace()
        path = workspace / ".gitignore"
        private = path.read_text(encoding="utf-8")
        own = "# this workspace's own data\nmy-data/\n"
        path.write_text(private + own, encoding="utf-8")

        self.assertEqual(_audit_drift(workspace), "")
        _set_tracking(workspace, "true")
        self.assertIn(".gitignore", _audit_drift(workspace))
        run_upgrade(workspace)
        tracked = path.read_text(encoding="utf-8")
        self.assertNotEqual(_block(tracked), private)
        self.assertEqual(_block(tracked), _rendered(workspace))
        self.assertTrue(tracked.endswith(own))
        self.assertNotIn(".gitignore", _drifted(workspace))
        self.assertEqual(_audit_drift(workspace), "")
        self.assertFalse(_ignored(workspace, "paper/main.tex"))

        _set_tracking(workspace, "false")
        self.assertIn(".gitignore", _audit_drift(workspace))
        run_upgrade(workspace)
        self.assertEqual(path.read_text(encoding="utf-8"), private + own)
        self.assertNotIn(".gitignore", _drifted(workspace))
        self.assertEqual(_audit_drift(workspace), "")
        self.assertTrue(_ignored(workspace, "paper/main.tex"))


if __name__ == "__main__":
    unittest.main()


class TrackResearchContentSchemaTests(unittest.TestCase):
    """S3: the setting is a boolean; anything else is refused, not read as off."""

    def _root(self, value) -> dict:
        return {"version": "1", "name": "w", "track_research_content": value}

    def test_a_boolean_is_accepted(self) -> None:
        # The minimal root lacks compute targets, so validation may stop later on
        # them; it must never stop on this key.
        from papersmith.errors import UserError
        from papersmith.schema import validate_papersmith_yaml
        for value in (True, False):
            try:
                validate_papersmith_yaml(self._root(value), require_compute=False)
            except UserError as exc:
                self.assertNotIn("track_research_content", str(exc))

    def test_a_non_boolean_is_refused(self) -> None:
        from papersmith.errors import UserError
        from papersmith.schema import validate_papersmith_yaml
        for value in ("yes", 1, "true"):
            with self.assertRaises(UserError):
                validate_papersmith_yaml(self._root(value), require_compute=False)
