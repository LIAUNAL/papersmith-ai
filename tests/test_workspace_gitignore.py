"""The workspace `.gitignore`: engine state is content, and user lines survive.

Two properties, both about the one rendered file a user is expected to edit.

**Engine state is content.** The template keeps research content local
("structure versioned, content local"): `proposals/*`, `experiments/*` and the
rest are ignored, only their `.gitkeep` travels. The deliberation engines keep
their state, receipts and permanent locks beside those folders, in each
domain's `sidecarRoot`, and that state embeds and hashes the very content the
template ignores, so it is meaningless without it and leaks it with it. Which
directories that covers is derived here from every `skills/*/profile.ts` the
kit ships, and confirmed by running an engine, never restated as a list.

**User lines survive `upgrade`.** `upgrade` re-renders every generated file on
every run. For `.gitignore` the framework owns a delimited block and the
workspace owns everything outside it: an upgrade rewrites the block and keeps
the rest verbatim, `status` and `audit --check-drift` compare only the block,
and a 0.13.0 file (no markers yet) is converted without losing a line the
workspace added to it.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from papersmith.cli import main
from papersmith.core import status as status_module, upgrade as upgrade_module
from papersmith.generators import (
    MANAGED_BLOCK_BEGIN,
    MANAGED_BLOCK_END,
    context_for_workspace,
    render_files,
)

from test_upgrade_v0_13_0_workspace import extract_fixture, run_upgrade
from workspace_series import REPO_ROOT, link_node_modules, make_workspace, new_tmp, run_node


def _git(workspace: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *argv], cwd=workspace, capture_output=True, text=True,
                          check=False)


def _ignored(workspace: Path, relpath: str) -> bool:
    return _git(workspace, "check-ignore", "-q", "--no-index", relpath).returncode == 0


def _rendered_gitignore(workspace: Path) -> str:
    with contextlib.redirect_stderr(io.StringIO()):
        return render_files(workspace, context_for_workspace(workspace))[".gitignore"]


def _quiet_upgrade(workspace: Path) -> dict:
    return run_upgrade(workspace)


def deliberation_artifacts() -> list[dict[str, str]]:
    """`artifact.directory` and `artifact.sidecarRoot` of every deliberation
    profile the kit ships, read through the engine's own `artifact-naming.ts`
    with each profile loaded the way its launcher loads it -- not restated
    here."""
    node = shutil.which("node")
    if node is None or not (REPO_ROOT / "node_modules").is_dir():
        raise unittest.SkipTest("node and the repository's node_modules are required")
    profiles = sorted((REPO_ROOT / "skills").glob("*/profile.ts"))
    script = (
        "import {createJiti} from 'jiti';"
        "const file=process.env.DELIBERATION_DOMAIN_PROFILE;"
        f"const jiti=createJiti({json.dumps(str(REPO_ROOT) + '/')});"
        "const artifact=(await jiti.import("
        f"{json.dumps(str(REPO_ROOT / 'skills/_core/deliberation/engine/artifact-naming.ts'))}"
        ")).artifact;"
        "process.stdout.write(JSON.stringify({profile:file,directory:artifact.directory,"
        "sidecarRoot:artifact.sidecarRoot}));"
    )
    artifacts = []
    for profile in profiles:
        # A profile loads the engine, which refuses to start without being
        # told whose profile it is -- the launcher's own `cli.mjs` sets this.
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("DELIBERATION_", "PROPOSAL_DELIBERATION_"))}
        env["DELIBERATION_DOMAIN_PROFILE"] = str(profile)
        completed = subprocess.run([node, "--input-type=module", "-e", script], cwd=REPO_ROOT,
                                   env=env, capture_output=True, text=True, check=False,
                                   timeout=180)
        if completed.returncode != 0:
            raise AssertionError(completed.stderr[-2000:])
        artifacts.append(json.loads(completed.stdout))
    if not artifacts:
        raise AssertionError("no deliberation profile found under skills/*/profile.ts")
    return artifacts


class EngineStateIsIgnoredTests(unittest.TestCase):

    def setUp(self) -> None:
        self.workspace = make_workspace(new_tmp(self))
        _git(self.workspace, "init", "-q")

    def test_every_deliberation_domains_state_is_ignored_and_its_folder_still_travels(self) -> None:
        for artifact in deliberation_artifacts():
            directory, sidecar = artifact["directory"], artifact["sidecarRoot"]
            with self.subTest(profile=artifact["profile"]):
                self.assertTrue(_ignored(self.workspace, f"{sidecar}/state/x.md.json"))
                self.assertTrue(_ignored(self.workspace, f"{sidecar}/receipts/x.md.json"))
                self.assertTrue(_ignored(self.workspace, f"{sidecar}/locks/initial-revision.lock"))
                self.assertTrue(_ignored(self.workspace, f"{directory}/x.md"))
                self.assertFalse(_ignored(self.workspace, f"{directory}/.gitkeep"))
                # The skill's own reconciliation moves revisions and their
                # sidecars here (SKILL.md, "Backups"): the same content.
                self.assertTrue(_ignored(self.workspace, f"backup/{directory}/t/x.md"))
                self.assertTrue(_ignored(self.workspace, f"backup/{directory}/t/{sidecar}/s.json"))

    def test_the_study_protocol_lines_ship_without_adding_a_folder(self) -> None:
        # T7-U1 (D4): the study-protocol skill ships to every workspace, so its revisions,
        # sidecar and backups are ignored from the start, while the experimental layout
        # gains no `protocol/` folder: the engine creates it on the first revision.
        text = (self.workspace / ".gitignore").read_text(encoding="utf-8")
        for line in ("protocol/*", "!protocol/.gitkeep", ".study-protocol-deliberation/", "backup/protocol/"):
            with self.subTest(line=line):
                self.assertIn(f"\n{line}\n", text)
        self.assertFalse((self.workspace / "protocol").exists())
        self.assertTrue(_ignored(self.workspace, "protocol/study-protocol-x-v01.md"))
        self.assertTrue(_ignored(self.workspace, ".study-protocol-deliberation/state/x.md.json"))

    def test_captured_analysis_streams_are_ignored_and_the_log_is_not(self) -> None:
        # T7-U9: `analysis_cli.py run` stores each command's stdout and stderr
        # under analysis/streams/, which may hold participant-level values; the
        # hash-chained log beside it stays tracked.
        text = (self.workspace / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("\nanalysis/streams/\n", text)
        self.assertTrue(_ignored(self.workspace, "analysis/streams/" + "0" * 64))
        self.assertFalse(_ignored(self.workspace, "analysis/log.jsonl"))

    def test_caztors_local_state_is_ignored_without_the_user_adding_it(self) -> None:
        # The in-browser editor keeps its builds, chats and provisioned guides
        # under `.caztor/`; the workspace ignores it from `smith init` on.
        text = (self.workspace / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("\n.caztor/\n", text)
        self.assertTrue(_ignored(self.workspace, ".caztor/build/main.pdf"))
        self.assertTrue(_ignored(self.workspace, ".caztor/guides/INDEX.md"))
        self.assertFalse(_ignored(self.workspace, "paper/.gitkeep"))

    def test_running_the_engine_leaves_nothing_new_for_git_to_track(self) -> None:
        link_node_modules(self.workspace)
        if not (self.workspace / "node_modules").exists() or shutil.which("node") is None:
            self.skipTest("node and the repository's node_modules are required")
        # `node_modules` is the test's own link, not something the engine wrote.
        before = set(_git(self.workspace, "status", "--porcelain", "--untracked-files=all")
                     .stdout.splitlines())
        result = run_node(self.workspace / "skills/proposal-deliberation/cli.mjs", json.dumps({
            "operation": "CREATE_INITIAL_REVISION",
            "instruction": "Smoothing estimator for noisy sequences. "
                           "We study a moving average estimator and bound its error.",
        }), workspace=self.workspace)
        self.assertEqual(json.loads(result.stdout)["status"], "created", result.stdout[-2000:])
        self.assertTrue((self.workspace / ".proposal-deliberation").is_dir())
        after = set(_git(self.workspace, "status", "--porcelain", "--untracked-files=all")
                    .stdout.splitlines())
        self.assertEqual(after - before, set())


class ManagedBlockTests(unittest.TestCase):

    def workspace(self) -> Path:
        return make_workspace(new_tmp(self))

    def test_a_fresh_workspace_holds_exactly_the_managed_block(self) -> None:
        workspace = self.workspace()
        text = (workspace / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(MANAGED_BLOCK_BEGIN + "\n"))
        self.assertTrue(text.endswith(MANAGED_BLOCK_END + "\n"))
        self.assertEqual(text.count(MANAGED_BLOCK_BEGIN), 1)

    def test_upgrade_keeps_lines_the_workspace_added_below_the_block(self) -> None:
        workspace = self.workspace()
        path = workspace / ".gitignore"
        own = "\n# this workspace's own data\nmy-data/\n!my-data/README.md\n"
        path.write_text(path.read_text(encoding="utf-8") + own, encoding="utf-8")
        edited = path.read_bytes()
        _quiet_upgrade(workspace)
        self.assertEqual(path.read_bytes(), edited)

    def test_upgrade_rewrites_the_block_and_nothing_outside_it(self) -> None:
        workspace = self.workspace()
        path = workspace / ".gitignore"
        rendered = path.read_text(encoding="utf-8")
        tampered = rendered.replace(".venv/\n", "")
        self.assertNotEqual(tampered, rendered)
        path.write_text("# above the block\nabove/\n" + tampered + "below/\n", encoding="utf-8")
        _quiet_upgrade(workspace)
        self.assertEqual(path.read_text(encoding="utf-8"),
                         "# above the block\nabove/\n" + rendered + "below/\n")

    def test_upgrade_rewrites_a_block_opened_by_the_pre_0_19_marker(self) -> None:
        # 0.19.0 renamed the command in the begin marker; a workspace made
        # before it carries the old wording and must still be upgraded.
        workspace = self.workspace()
        path = workspace / ".gitignore"
        rendered = path.read_text(encoding="utf-8")
        legacy = MANAGED_BLOCK_BEGIN.replace("`smith upgrade`", "`papersmith upgrade`")
        self.assertNotEqual(legacy, MANAGED_BLOCK_BEGIN)
        path.write_text(rendered.replace(MANAGED_BLOCK_BEGIN, legacy) + "mine/\n",
                        encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()) as err:
            _quiet_upgrade(workspace)
        self.assertNotIn(".gitignore", err.getvalue())
        self.assertEqual(path.read_text(encoding="utf-8"), rendered + "mine/\n")

    def test_user_lines_are_not_drift_and_an_edit_inside_the_block_is(self) -> None:
        workspace = self.workspace()
        path = workspace / ".gitignore"
        path.write_text(path.read_text(encoding="utf-8") + "my-data/\n", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertNotIn(".gitignore", status_module.status(workspace)["framework"]["drifted_files"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["audit", str(workspace), "--check-drift"]), 0, out.getvalue()[-1500:])

        path.write_text(path.read_text(encoding="utf-8").replace(".venv/\n", ""), encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertIn(".gitignore", status_module.status(workspace)["framework"]["drifted_files"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertNotEqual(main(["audit", str(workspace), "--check-drift"]), 0)
        self.assertIn(".gitignore", out.getvalue())

    def test_malformed_markers_are_left_alone_and_reported(self) -> None:
        """A block whose end marker is gone cannot be told apart from the
        workspace's own lines, so nothing is guessed: the file stays as it is,
        the run names it, and it stays drift until somebody repairs it."""
        workspace = self.workspace()
        path = workspace / ".gitignore"
        broken = path.read_text(encoding="utf-8").replace(MANAGED_BLOCK_END + "\n", "") + "mine/\n"
        path.write_text(broken, encoding="utf-8")
        report = _quiet_upgrade(workspace)
        self.assertEqual(path.read_text(encoding="utf-8"), broken)
        self.assertIn(".gitignore", report["unsynchronized"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertIn(".gitignore", status_module.status(workspace)["framework"]["drifted_files"])

    def test_a_second_upgrade_changes_nothing(self) -> None:
        workspace = self.workspace()
        path = workspace / ".gitignore"
        path.write_text(path.read_text(encoding="utf-8") + "my-data/\n", encoding="utf-8")
        _quiet_upgrade(workspace)
        first = path.read_bytes()
        report = _quiet_upgrade(workspace)
        self.assertEqual(path.read_bytes(), first)
        self.assertNotIn(".gitignore", report["changed_files"])


class V0130GitignoreTests(unittest.TestCase):
    """The 0.13.0 file has no markers; the fixture carries the bytes 0.13.0
    rendered."""

    def fixture(self) -> Path:
        return extract_fixture(new_tmp(self))

    def test_an_untouched_0_13_0_file_becomes_exactly_the_current_render(self) -> None:
        workspace = self.fixture()
        old = (workspace / ".gitignore").read_text(encoding="utf-8")
        self.assertNotIn(MANAGED_BLOCK_BEGIN, old)
        _quiet_upgrade(workspace)
        self.assertEqual((workspace / ".gitignore").read_text(encoding="utf-8"),
                         _rendered_gitignore(workspace))

    def test_a_markerless_file_is_replaced_whole_only_when_it_is_what_the_framework_wrote(self) -> None:
        """The stored baseline decides. A line a later release dropped from the
        template goes away when the file is exactly what the framework last
        wrote, and stays when the file is not, because then nobody can say
        whose line it is."""
        for pristine in (True, False):
            with self.subTest(pristine=pristine):
                workspace = make_workspace(new_tmp(self))
                path = workspace / ".gitignore"
                old = "# a line an older template carried\nretired-by-a-later-release/\n"
                path.write_text(old, encoding="utf-8")
                manifest_path = workspace / ".papersmith" / "manifest.json"
                stored = json.loads(manifest_path.read_text(encoding="utf-8"))
                stored["files"][".gitignore"] = (
                    hashlib.sha256(old.encode("utf-8")).hexdigest() if pristine else "0" * 64)
                manifest_path.write_text(json.dumps(stored), encoding="utf-8")
                _quiet_upgrade(workspace)
                text = path.read_text(encoding="utf-8")
                rendered = _rendered_gitignore(workspace)
                if pristine:
                    self.assertEqual(text, rendered)
                else:
                    self.assertEqual(text, rendered + "\n" + old)

    def test_lines_added_to_a_0_13_0_file_survive_its_conversion(self) -> None:
        workspace = self.fixture()
        path = workspace / ".gitignore"
        old = path.read_text(encoding="utf-8")
        # One line appended, one inserted between template lines.
        edited = old.replace(".scratch/\n", ".scratch/\nlocal-notes/\n") + "\n# mine\nmy-data/\n"
        path.write_text(edited, encoding="utf-8")
        _quiet_upgrade(workspace)
        text = path.read_text(encoding="utf-8")
        rendered = _rendered_gitignore(workspace)
        self.assertTrue(text.startswith(rendered), "the block comes first, whole")
        below = text[len(rendered):].splitlines()
        for line in ("local-notes/", "# mine", "my-data/"):
            with self.subTest(line=line):
                self.assertEqual(below.count(line), 1)
        # Nothing the 0.13.0 template already said is repeated below the block.
        for line in old.splitlines():
            if line.strip():
                self.assertNotIn(line, below)

    def test_the_upgraded_fixture_ignores_its_engine_state(self) -> None:
        workspace = self.fixture()
        _git(workspace, "init", "-q")
        self.assertFalse(_ignored(workspace, ".proposal-deliberation/receipts/x.json"))
        _quiet_upgrade(workspace)
        for relpath in (".proposal-deliberation/receipts/x.json",
                        ".experimental-deliberation/locks/initial-revision.lock"):
            with self.subTest(relpath=relpath):
                self.assertTrue(_ignored(workspace, relpath))
        digest = hashlib.sha256((workspace / ".gitignore").read_bytes()).hexdigest()
        _quiet_upgrade(workspace)
        self.assertEqual(hashlib.sha256((workspace / ".gitignore").read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
