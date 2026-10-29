"""Workspace initialization tests against the real repository kit."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from papersmith.cli import main
from papersmith.core import config, init as init_module, manifest
from papersmith.kit import resolve_and_validate
from papersmith.errors import UserError
from papersmith.generators import MANAGED_BLOCK_BEGIN, MANAGED_BLOCK_END
from papersmith.yamllite import loads


class EnvironmentProvisioningTests(unittest.TestCase):
    """`init` provisions the environment the command center's backend needs.

    The step is what makes `smith ui` work after init: the CLI's own
    interpreter is a pipx venv with no runtime dependencies, and the environment
    `scripts/setup_env.py` builds is the one thing that carries them. These
    drive the step against a script that stands in for the real one, so no test
    performs a network install.
    """

    def new_tmp(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def seed_script(self, root: Path, body: str) -> Path:
        script = root / "scripts" / "setup_env.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(body, encoding="utf-8")
        return script

    def test_the_step_runs_the_workspaces_own_script(self) -> None:
        root = self.new_tmp()
        marker = root / "invocation.txt"
        self.seed_script(
            root,
            "import pathlib, sys\n"
            f"pathlib.Path({str(marker)!r}).write_text(' '.join(sys.argv[1:]))\n",
        )

        assert init_module._run_env_install(root) is None
        assert marker.read_text(encoding="utf-8") == "install"

    def test_a_failing_script_is_reported_with_the_remedy(self) -> None:
        root = self.new_tmp()
        self.seed_script(root, "import sys\nsys.stderr.write('no network\\n')\nsys.exit(3)\n")

        warning = init_module._run_env_install(root)

        assert warning is not None
        assert "setup_env.py install" in warning, warning

    def test_a_missing_script_is_reported_rather_than_ignored(self) -> None:
        warning = init_module._run_env_install(self.new_tmp())

        assert warning is not None
        assert "upgrade" in warning, warning

    def test_init_runs_the_step_and_reports_a_failure_as_a_warning(self) -> None:
        """Wiring, driven through the real entry point with the step itself
        replaced, so the assertion is about init's contract rather than about
        provisioning a real environment inside a test."""
        root = self.new_tmp() / "paper"
        calls: list[Path] = []
        original = init_module._run_env_install
        init_module._run_env_install = (
            lambda workspace, report=None: calls.append(workspace) or "stubbed gap")
        self.addCleanup(setattr, init_module, "_run_env_install", original)

        result = init_module.initialize(root, run_npm=False, run_env=True)

        assert calls == [root.resolve()], calls
        assert any("stubbed gap" in warning for warning in result["warnings"]), result

    def test_init_skips_the_step_when_it_is_told_to(self) -> None:
        root = self.new_tmp() / "paper"
        calls: list[Path] = []
        original = init_module._run_env_install
        init_module._run_env_install = (
            lambda workspace, report=None: calls.append(workspace) or None)
        self.addCleanup(setattr, init_module, "_run_env_install", original)

        init_module.initialize(root, run_npm=False, run_env=False)

        assert calls == [], "`run_env=False` must be an offline-fast init"

    def test_init_skips_the_step_by_default(self) -> None:
        root = self.new_tmp() / "paper"
        calls: list[Path] = []
        original = init_module._run_env_install
        init_module._run_env_install = (
            lambda workspace, report=None: calls.append(workspace) or None)
        self.addCleanup(setattr, init_module, "_run_env_install", original)

        init_module.initialize(root, run_npm=False)

        assert calls == [], "default `initialize(...)` must defer environment provisioning"

    def test_cli_flags_control_provisioning(self) -> None:
        from papersmith.cli import build_parser

        parser = build_parser()
        args_default = parser.parse_args(["init", "dest"])
        assert getattr(args_default, "with_env", False) is False

        args_with = parser.parse_args(["init", "--with-env", "dest"])
        assert args_with.with_env is True

        args_no = parser.parse_args(["init", "--no-env", "dest"])
        assert args_no.no_env is True


class SuiteStaysOfflineTests(unittest.TestCase):
    """No test may provision a real environment through `init`.

    Measured defect, introduced by the change this lock belongs to: `init` gained
    an environment step that downloads a micromamba environment, and one
    JavaScript test kept calling `init` without the skip flag -- 147 leaked
    directories and 5.9 GB in the temp dir before anybody noticed, and the Node
    half silently became a network test that took minutes instead of seconds.
    A lock is cheaper than that discovery.

    The rule is read off the suite's own text: every `init` invocation here must
    carry the flag that keeps it offline. This file is excluded, because it is
    the one place that tests the provisioning step on purpose and stands in a
    script for the real one.

    A caller is a caller wherever it lives. This rule scanned `tests/` alone,
    and that blind spot is measured: `scripts/cli-paper-wiring-smoke.sh` kept
    calling `init` without `--no-env` after provisioning landed, so the wrapper
    built a real multi-gigabyte environment inside its own 180s timeout and
    died there, while the guard written to catch exactly this stayed green.
    Shell and workflow callers are swept too, on the same npm-keyed rule --
    a caller that opted into the offline `--no-npm` path opted into the
    offline environment with it. The opt-in live smoke is deliberately out of
    scope and stays that way: it carries neither flag.
    """

    REPOSITORY = Path(__file__).resolve().parent.parent

    #: Roots swept beyond `tests/`, with the suffixes that can hold an
    #: invocation there. `.github/` is included because a workflow `run:` block
    #: is a caller like any other.
    INVOKING_ROOTS = ("scripts", ".github")
    INVOKING_SUFFIXES = (".sh", ".yml", ".yaml")

    def invocations_outside_the_suite(self) -> list[str]:
        """Non-comment `init --no-npm` lines without `--no-env`, by path:line.

        Shell and workflow files write the flag bare, so the quoted matcher
        above cannot see them. Prose mentions it too -- in headers, in comments
        -- so a line opening with `#` is skipped rather than read as an
        invocation.
        """
        offenders: list[str] = []
        for root in self.INVOKING_ROOTS:
            for path in sorted((self.REPOSITORY / root).rglob("*")):
                if path.suffix not in self.INVOKING_SUFFIXES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                for match in re.finditer(r"--no-npm", text):
                    line_start = text.rfind("\n", 0, match.start()) + 1
                    if text[line_start:match.start()].lstrip().startswith("#"):
                        continue
                    # Flag order is free on a shell line, so `--no-env` may
                    # precede `--no-npm` as well as follow it.
                    line_end = text.find("\n", match.end())
                    same_line = text[line_start:line_end if line_end != -1 else len(text)]
                    if "--no-env" in same_line or "--no-env" in text[match.end():match.end() + 120]:
                        continue
                    relpath = path.relative_to(self.REPOSITORY).as_posix()
                    line = text[:match.start()].count("\n") + 1
                    offenders.append(f"{relpath}:{line}")
        return offenders

    def test_every_cli_init_in_the_suite_skips_provisioning(self) -> None:
        offenders = []
        for path in sorted((self.REPOSITORY / "tests").rglob("*")):
            if path.suffix not in (".py", ".mjs", ".js") or path.name == Path(__file__).name:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r'"--no-npm"', text):
                if "--no-env" not in text[match.end():match.end() + 120]:
                    offenders.append(f"{path.name}:{text[:match.start()].count(chr(10)) + 1}")
        offenders += self.invocations_outside_the_suite()

        assert offenders == [], (
            "these test-suite `init` invocations skip the npm step and not the "
            "environment step, so each one performs a multi-gigabyte network "
            "install and leaks it into the temp dir: " + ", ".join(offenders))

    def test_the_mcp_init_tool_skips_provisioning_unless_asked(self) -> None:
        """The MCP tool reaches `init` through a builder, not a literal.

        The text scan above reads `"--no-npm"` out of test sources, so it cannot
        see an invocation assembled by `_build_init`. That blind spot let
        `test_init_actually_creates_a_workspace_under_the_bound_root` provision a
        real 3.6 GB micromamba environment into the temp dir. The tool already
        keeps npm opt-in (`allow_npm`); an agent calling it must not trigger a
        multi-gigabyte download unannounced either, so the environment step is
        opt-in too.
        """
        from papersmith.mcp.registry import _build_init

        workspace = Path(tempfile.mkdtemp(prefix="papersmith-mcp-init-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(workspace, ignore_errors=True))

        default = _build_init({"name": "child"}, workspace).tokens
        assert "--no-env" in default, (
            "the MCP init tool provisions an environment by default: " + " ".join(default))
        assert "--no-npm" in default

        opted_in = _build_init({"name": "child", "allow_env": True}, workspace).tokens
        assert "--no-env" not in opted_in
        assert "--no-npm" in opted_in, "allow_env must not also enable npm"

    def test_every_api_init_in_the_suite_states_its_environment_intent(self) -> None:
        offenders = []
        for path in sorted((self.REPOSITORY / "tests").glob("*.py")):
            if path.name == Path(__file__).name:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r"run_npm=False", text):
                if "run_env" not in text[match.end():match.end() + 40]:
                    offenders.append(f"{path.name}:{text[:match.start()].count(chr(10)) + 1}")

        assert offenders == [], (
            "these `initialize(...)` calls state no environment intent, so they "
            "inherit the provisioning default and install an environment inside "
            "a test: " + ", ".join(offenders))


class ShippedCrossReferenceTests(unittest.TestCase):
    """A shipped document must not cite a path that exists only in the forge.

    Measured defect: seven paragraphs across two skills sent the reader to
    `.pi/README.md` for the harnesses with no Task-tool delegation. That file is
    tracked here and ships nowhere -- it is not a kit entry and nothing generates
    it -- so an agent in an initialized workspace, which is the only place these
    documents are read, was handed a cross-reference that cannot resolve. It
    looked plausible to whoever wrote it precisely because it exists in this
    repository.

    The rule: a dot-directory path a shipped document cites, and that this
    repository TRACKS, must also exist in a workspace the framework creates.
    Scoped that way deliberately -- runtime state a skill creates at run time
    (`.implementation/position.jsonl`) and gitignored paths (`.venv/bin/python`)
    are not tracked, so they are excluded rather than reported as defects.
    """

    CITATION = re.compile(r"`(\.[a-z][\w.-]*/[^`\s]+)`")
    REPOSITORY = Path(__file__).resolve().parent.parent

    def is_tracked(self, relative: str) -> bool:
        return subprocess.run(
            ["git", "ls-files", "--error-unmatch", relative],
            cwd=str(self.REPOSITORY), capture_output=True,
        ).returncode == 0

    def test_every_tracked_dot_directory_citation_resolves_in_a_workspace(self) -> None:
        citations: dict[str, set[str]] = {}
        for document in sorted((self.REPOSITORY / "skills").rglob("*.md")):
            text = document.read_text(encoding="utf-8", errors="replace")
            for match in self.CITATION.finditer(text):
                path = match.group(1)
                if "<" in path:                      # a placeholder, not a path
                    continue
                citations.setdefault(path, set()).add(
                    str(document.relative_to(self.REPOSITORY)))

        assert citations, "no dot-directory citation was found, so this lock checks nothing"
        tracked = {path: sorted(sources) for path, sources in citations.items()
                   if self.is_tracked(path)}
        assert tracked, (
            "no TRACKED citation was found, so the rule below would pass over an "
            "empty set and prove nothing")

        with tempfile.TemporaryDirectory() as holder:
            workspace = Path(holder).resolve() / "paper"
            init_module.initialize(workspace, run_npm=False, run_env=False)
            unresolved = {path: sources for path, sources in tracked.items()
                          if not (workspace / path).exists()}

        assert unresolved == {}, (
            "these shipped documents cite paths that exist in this repository "
            f"and reach no workspace, so a reader there cannot resolve them: {unresolved}")


class InitTests(unittest.TestCase):
    def new_tmp(self) -> Path:
        """Scratch directory, resolved -- see BridgesTests.new_tmp for why."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def test_initialize_creates_the_workspace_contract(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "sparse-ae"
        result = init_module.initialize(
            workspace,
            title="Sparse Autoencoder Audit",
            topic="mechanistic interpretability",
            tools=("claude", "opencode", "pi", "antigravity"),
            remote="kaggle",
            run_npm=False, run_env=False,
        )

        assert result["name"] == "sparse-ae"
        # Derived, not restated. This read `== "0.1.0"` and passed for more
        # than a thousand commits because the version never moved; the first
        # real bump broke it, which is what a copied literal always does
        # eventually. What the test means is that init records the version
        # the kit carries, so it asks the kit.
        assert result["version"] == manifest.kit_version(resolve_and_validate())
        assert result["default_target"] == "kaggle-gpu-pool"
        for relpath in (
            ".papersmith/version",
            ".papersmith/manifest.json",
            ".papersmith/config.json",
            ".papersmith/runs_ledger.jsonl",
            ".claude/agents/paper-ingestion.md",
            "skills/paper-ingestion/SKILL.md",
            "skills/proposal-deliberation/cli.mjs",
            "skills/kaggle-accounts/store/.gitignore",
            "scripts/setup-harnesses.sh",
            "sections/01-materials-and-methods.md",
            "guidance/paper-guide",
            "guidance/reference-papers",
            "guidance/data-paper",
            "proposals",
            "paper",
            "experiments",
            "implementations",
            "kaggle-inbox",
            "papersmith.yaml",
            "package.json",
            "README.md",
            "CLAUDE.md",
            "OPENCODE.md",
            ".pi/APPEND_SYSTEM.md",
            ".pi/gentle-ai/persona.json",
            ".agents/AGENTS.md",
            ".gitignore",
        ):
            assert (workspace / relpath).exists(), relpath

        # The old nested proposals/ shape and the journal/DECISIONS.md pair are
        # both gone: this repository's own layout is flat and keeps no journal.
        assert not (workspace / "proposals/drafts").exists()
        assert not (workspace / "proposals/deliberated").exists()
        assert not (workspace / "proposals/receipts").exists()
        assert not (workspace / "journal").exists()
        assert not (workspace / "DECISIONS.md").exists()
        assert (workspace / "proposals/.gitkeep").exists()

        # Credentials are never copied from the kit store.
        assert not (workspace / "skills/kaggle-accounts/store/accounts.json").exists()
        assert "paper-ingestion" in (workspace / "CLAUDE.md").read_text(encoding="utf-8")
        assert "mechanistic interpretability" in (workspace / "OPENCODE.md").read_text(encoding="utf-8")
        assert json.loads((workspace / ".pi/gentle-ai/persona.json").read_text()) == {"mode": "gentleman"}

        yaml = config.load_papersmith_yaml(workspace)
        assert yaml["name"] == "sparse-ae"
        assert yaml["title"] == "Sparse Autoencoder Audit"
        assert yaml["topic"] == "mechanistic interpretability"
        assert yaml["paper_ingestion"]["mode"] == "fast"
        assert yaml["compute_targets"]["default"] == "kaggle-gpu-pool"
        assert set(yaml["execution_profiles"]) == {
            "smoke_and_invariants", "sweep_training", "benchmark_evaluation"
        }

        cfg = config.load_workspace_config(workspace)
        assert cfg["project_name"] == "sparse-ae"
        assert cfg["active_tools"] == ["claude", "opencode", "pi", "antigravity"]
        assert cfg["execution_engine"]["active_compute_target"] == "kaggle-gpu-pool"

        stored_manifest = json.loads((workspace / ".papersmith/manifest.json").read_text())
        assert stored_manifest["kind"] == "workspace"
        assert stored_manifest["version"] == manifest.kit_version(resolve_and_validate())
        expected = manifest.workspace_framework_files(workspace, Path(__file__).parents[1])
        assert stored_manifest["files"] == expected

    def test_initialize_wires_harness_skill_symlinks(self) -> None:
        # `scripts/setup-harnesses.sh` projects the canonical `skills/` tree
        # into every harness for THIS repository's own checkout; a freshly
        # generated workspace must not need that manual step re-run before
        # pi/OpenCode/Antigravity can read a skill at all.
        tmp_path = self.new_tmp()
        workspace = tmp_path / "sparse-ae"
        result = init_module.initialize(
            workspace,
            tools=("claude", "opencode", "pi", "antigravity"),
            run_npm=False, run_env=False,
        )
        canonical = (workspace / "skills").resolve()
        for relpath in (
            ".claude/skills", ".opencode/skills", ".pi/skills",
            ".agents/skills",
        ):
            link = workspace / relpath
            assert link.is_symlink(), f"{relpath} is not a symlink"
            assert not link.readlink().is_absolute(), f"{relpath} must be a relative link"
            assert link.resolve() == canonical, relpath
            # A wired harness link is reported the same way every other kit
            # file is, so a filesystem that cannot create it shows up here.
            assert relpath in result["copied_files"], relpath

    def test_link_harness_skills_never_deletes_real_content_and_scopes_to_tools(self) -> None:
        tmp_path = self.new_tmp()
        (tmp_path / "skills").mkdir()
        real = tmp_path / ".opencode" / "skills"
        real.mkdir(parents=True)
        (real / "keep.txt").write_text("mine")
        linked = manifest.link_harness_skills(tmp_path, tools=("claude", "opencode"))
        assert ".opencode/skills" not in linked
        assert (real / "keep.txt").read_text() == "mine"
        assert (tmp_path / ".claude/skills").is_symlink()
        assert not (tmp_path / ".pi/skills").exists()

    def test_link_harness_skills_antigravity_wires_only_the_documented_path(self) -> None:
        tmp_path = self.new_tmp()
        (tmp_path / "skills").mkdir()
        linked = manifest.link_harness_skills(tmp_path, tools=("antigravity",))
        assert sorted(linked) == [".agents/skills"]
        for relpath in linked:
            assert (tmp_path / relpath).resolve() == (tmp_path / "skills").resolve()

    def test_link_harness_skills_filters_on_the_explicit_tool_not_the_path(self) -> None:
        tmp_path = self.new_tmp()
        (tmp_path / "skills").mkdir()
        # `.agents/skills` belongs to antigravity even though no path segment says so.
        assert manifest.link_harness_skills(tmp_path, tools=("claude",)) == [".claude/skills"]
        assert not (tmp_path / ".agents/skills").exists()
        assert not (tmp_path / ".antigravity/skills").exists()
        assert manifest.link_harness_skills(tmp_path, tools=("pi",)) == [".pi/skills"]

    def test_link_harness_skills_repairs_a_stale_symlink(self) -> None:
        tmp_path = self.new_tmp()
        (tmp_path / "skills").mkdir()
        (tmp_path / "elsewhere").mkdir()
        link = tmp_path / ".claude" / "skills"
        link.parent.mkdir(parents=True)
        link.symlink_to("../elsewhere")
        linked = manifest.link_harness_skills(tmp_path, tools=("claude",))
        assert linked == [".claude/skills"]
        assert link.resolve() == (tmp_path / "skills").resolve()

    def test_link_report_names_a_path_whose_link_creation_failed(self) -> None:
        tmp_path = self.new_tmp()
        (tmp_path / "skills").mkdir()
        real_symlink_to = Path.symlink_to

        def fail_for_pi(self_path, *args, **kwargs):
            if ".pi" in self_path.parts:
                raise PermissionError("simulated: symlinks not permitted")
            return real_symlink_to(self_path, *args, **kwargs)

        with mock.patch.object(Path, "symlink_to", fail_for_pi):
            report = manifest.link_harness_skills_report(tmp_path, tools=("claude", "pi"))
        assert report.linked == [".claude/skills"]
        assert report.failed == [".pi/skills"]
        assert report.blocked == []
        assert not (tmp_path / ".pi/skills").exists()

    def test_link_report_names_a_real_directory_occupying_the_link_path(self) -> None:
        tmp_path = self.new_tmp()
        (tmp_path / "skills").mkdir()
        real = tmp_path / ".opencode" / "skills"
        real.mkdir(parents=True)
        (real / "keep.txt").write_text("mine")
        report = manifest.link_harness_skills_report(tmp_path, tools=("opencode",))
        assert report.blocked == [".opencode/skills"]
        assert report.linked == [] and report.failed == []
        assert (real / "keep.txt").read_text() == "mine"
        assert not real.is_symlink()

    def test_link_report_never_copies_files_as_a_fallback(self) -> None:
        tmp_path = self.new_tmp()
        (tmp_path / "skills").mkdir()
        (tmp_path / "skills" / "one.txt").write_text("x")
        with mock.patch.object(Path, "symlink_to", side_effect=OSError("no symlinks")):
            report = manifest.link_harness_skills_report(tmp_path, tools=("claude",))
        assert report.failed == [".claude/skills"]
        assert not (tmp_path / ".claude/skills").exists()

    def test_link_report_leaves_a_correct_link_out_of_every_bucket(self) -> None:
        tmp_path = self.new_tmp()
        (tmp_path / "skills").mkdir()
        manifest.link_harness_skills_report(tmp_path, tools=("claude",))
        again = manifest.link_harness_skills_report(tmp_path, tools=("claude",))
        assert again == manifest.LinkReport(linked=[], failed=[], blocked=[])

    def test_wrapper_still_returns_only_the_linked_paths(self) -> None:
        tmp_path = self.new_tmp()
        (tmp_path / "skills").mkdir()
        (tmp_path / ".opencode" / "skills").mkdir(parents=True)
        linked = manifest.link_harness_skills(tmp_path, tools=("claude", "opencode"))
        assert linked == [".claude/skills"]

    def test_init_warns_once_per_failed_or_blocked_link_and_still_succeeds(self) -> None:
        tmp_path = self.new_tmp()
        report = manifest.LinkReport(linked=[], failed=[".pi/skills"], blocked=[".opencode/skills"])
        with mock.patch.object(manifest, "link_harness_skills_report", return_value=report):
            result = init_module.initialize(tmp_path / "ws", run_npm=False, run_env=False)
        joined = "\n".join(result["warnings"])
        assert joined.count(".pi/skills") == 1
        assert joined.count(".opencode/skills") == 1
        assert "not linked" in joined

    def test_remote_selects_the_declared_default_target(self) -> None:
        tmp_path = self.new_tmp()
        for remote, target in [
            ("local", "local-workstation"),
            ("kaggle", "kaggle-gpu-pool"),
            ("slurm", "slurm-cluster"),
        ]:
            with self.subTest(remote=remote):
                workspace = tmp_path / remote
                init_module.initialize(workspace, remote=remote, run_npm=False, run_env=False)
                data = config.load_papersmith_yaml(workspace)
                assert data["compute_targets"]["default"] == target
                cfg = config.load_workspace_config(workspace)
                assert cfg["execution_engine"]["active_compute_target"] == target

    def test_initialize_rejects_unknown_tools(self) -> None:
        tmp_path = self.new_tmp()
        with self.assertRaisesRegex(UserError, "unsupported runtime"):
            init_module.initialize(tmp_path / "paper", tools=("claude", "wat"), run_npm=False, run_env=False)

    def test_initialize_rejects_nonempty_destination(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "paper"
        workspace.mkdir()
        (workspace / "notes.md").write_text("keep")
        with self.assertRaisesRegex(UserError, "must be empty"):
            init_module.initialize(workspace, run_npm=False, run_env=False)

    def test_cli_import_existing_files_preserves_originals(self) -> None:
        workspace = self.new_tmp() / "existing"
        (workspace / "guidance" / "reference-papers").mkdir(parents=True)
        original = workspace / "guidance" / "reference-papers" / "source.pdf"
        original.write_bytes(b"original paper bytes")
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["init", str(workspace), "--import-existing", "--no-npm", "--no-env"]) == 0
        assert original.read_bytes() == b"original paper bytes"
        assert (workspace / ".papersmith" / "manifest.json").is_file()
        assert (workspace / "papersmith.yaml").is_file()
        for path in (workspace / "papersmith.yaml", workspace / ".papersmith" / "config.json",
                     workspace / ".papersmith" / "manifest.json"):
            assert b"papersmith-init-" not in path.read_bytes(), path

    def test_import_refuses_collision_without_mutating_destination(self) -> None:
        workspace = self.new_tmp() / "existing"
        workspace.mkdir()
        original = workspace / "CLAUDE.md"
        original.write_bytes(b"my own instructions")
        (workspace / ".gitignore").write_bytes(b"data/\n")
        with self.assertRaisesRegex(UserError, "import collision.*CLAUDE.md"):
            init_module.initialize(workspace, import_existing=True, run_npm=False, run_env=False)
        assert original.read_bytes() == b"my own instructions"
        assert (workspace / ".gitignore").read_bytes() == b"data/\n"
        assert sorted(p.name for p in workspace.iterdir()) == [".gitignore", "CLAUDE.md"]

    def test_import_keeps_readme_and_merges_gitignore(self) -> None:
        workspace = self.new_tmp() / "repo"
        workspace.mkdir()
        (workspace / "README.md").write_bytes(b"# My repo\n")
        (workspace / ".gitignore").write_bytes(b"data/\n*.log\n")
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["init", str(workspace), "--import-existing", "--no-npm", "--no-env"]) == 0
        assert (workspace / "README.md").read_bytes() == b"# My repo\n"
        ignore = (workspace / ".gitignore").read_text(encoding="utf-8")
        assert ignore.startswith(MANAGED_BLOCK_BEGIN)
        assert MANAGED_BLOCK_END in ignore
        assert ignore.split(MANAGED_BLOCK_END, 1)[1].split() == ["data/", "*.log"]
        assert not list(workspace.glob(".*.papersmith-import"))
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["audit", str(workspace), "--check-drift"]) == 0

    def test_a_fresh_workspace_ignores_both_tutors_threads_and_uploads(self) -> None:
        """The tutors keep the reader's conversation and hand-written pages
        under `.papersmith/`; they are the reader's, and never travel."""
        workspace = self.new_tmp() / "paper"
        init_module.initialize(workspace, title="T", topic="t", tools=("claude",),
                               run_npm=False, run_env=False)
        ignore = (workspace / ".gitignore").read_text(encoding="utf-8")
        block = ignore.split(MANAGED_BLOCK_BEGIN, 1)[1].split(MANAGED_BLOCK_END, 1)[0].splitlines()
        for entry in (".papersmith/math-tutor/", ".papersmith/experiments-tutor/"):
            assert entry in block, entry
        if not (workspace / ".git").exists():
            subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
        for rel in (".papersmith/math-tutor/thread.json", ".papersmith/math-tutor/images/0123.png",
                    ".papersmith/experiments-tutor/thread.json"):
            done = subprocess.run(["git", "check-ignore", "-q", rel], cwd=workspace, check=False)
            assert done.returncode == 0, rel
        # This repository holds itself to the same contract.
        own = (Path(__file__).parents[1] / ".gitignore").read_text(encoding="utf-8").splitlines()
        for entry in (".papersmith/math-tutor/", ".papersmith/experiments-tutor/"):
            assert entry in own, entry

    def test_import_refuses_gitignore_with_malformed_markers(self) -> None:
        workspace = self.new_tmp() / "repo"
        workspace.mkdir()
        broken = f"{MANAGED_BLOCK_BEGIN}\ndata/\n".encode()
        (workspace / ".gitignore").write_bytes(broken)
        with self.assertRaisesRegex(UserError, "import collision.*gitignore"):
            init_module.initialize(workspace, import_existing=True, run_npm=False, run_env=False)
        assert (workspace / ".gitignore").read_bytes() == broken
        assert sorted(p.name for p in workspace.iterdir()) == [".gitignore"]

    def test_cli_init_defaults_to_the_current_directory(self) -> None:
        workspace = self.new_tmp() / "here"
        workspace.mkdir()
        with contextlib.chdir(workspace), contextlib.redirect_stdout(io.StringIO()):
            assert main(["init", "--no-npm", "--no-env"]) == 0
        assert (workspace / "papersmith.yaml").is_file()
        assert (workspace / ".papersmith" / "manifest.json").is_file()

    def test_cli_init_in_a_nonempty_current_directory_points_to_import(self) -> None:
        workspace = self.new_tmp() / "here"
        workspace.mkdir()
        (workspace / "notes.md").write_text("keep")
        with contextlib.chdir(workspace), contextlib.redirect_stderr(io.StringIO()) as err:
            assert main(["init", "--no-npm", "--no-env"]) != 0
        assert re.search("must be empty.*--import-existing", err.getvalue())
        assert sorted(p.name for p in workspace.iterdir()) == ["notes.md"]

    def test_init_declares_pi_web_access_for_pi_workspaces(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "paper"
        init_module.initialize(workspace, run_npm=False, run_env=False)
        settings = json.loads((workspace / ".pi" / "settings.json").read_text())
        assert settings == {"packages": ["npm:pi-web-access"]}
        other = tmp_path / "claude-only"
        init_module.initialize(other, tools=("claude",), run_npm=False, run_env=False)
        assert not (other / ".pi" / "settings.json").exists()

    def test_init_registers_the_banco_lia_mcp_for_every_declared_harness(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "paper"
        init_module.initialize(workspace, run_npm=False, run_env=False)
        args = ["--from", "git+https://github.com/LIAUNAL/bancoProyectosPapersLIA", "banco-lia-mcp"]
        claude = json.loads((workspace / ".mcp.json").read_text())
        assert claude["mcpServers"]["banco-lia"] == {"type": "stdio", "command": "uvx", "args": args}
        for relpath in (".pi/mcp.json", ".agents/mcp_config.json"):
            servers = json.loads((workspace / relpath).read_text())["mcpServers"]
            assert servers["banco-lia"] == {"command": "uvx", "args": args}, relpath
        opencode = json.loads((workspace / "opencode.json").read_text())
        assert opencode["mcp"]["banco-lia"] == {
            "type": "local", "command": ["uvx", *args], "enabled": True}
        other = tmp_path / "claude-only"
        init_module.initialize(other, tools=("claude",), run_npm=False, run_env=False)
        assert (other / ".mcp.json").is_file()
        for relpath in (".pi/mcp.json", ".agents/mcp_config.json", "opencode.json"):
            assert not (other / relpath).exists(), relpath

    def test_init_registers_the_kaggle_mcp_for_every_declared_harness(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "paper"
        init_module.initialize(workspace, run_npm=False, run_env=False)
        claude = json.loads((workspace / ".mcp.json").read_text())
        assert claude["mcpServers"]["kaggle"] == {
            "type": "http", "url": "https://www.kaggle.com/mcp",
            "headers": {"Authorization": "Bearer ${KAGGLE_API_TOKEN:-}"}}
        bridge = ["-y", "mcp-remote@0.14.3", "https://www.kaggle.com/mcp",
                  "--header", "Authorization:Bearer ${KAGGLE_API_TOKEN}"]
        for relpath in (".pi/mcp.json", ".agents/mcp_config.json"):
            servers = json.loads((workspace / relpath).read_text())["mcpServers"]
            assert servers["kaggle"] == {"command": "npx", "args": bridge}, relpath
            assert "banco-lia" in servers, relpath
        opencode = json.loads((workspace / "opencode.json").read_text())
        assert opencode["mcp"]["kaggle"] == {
            "type": "remote", "url": "https://www.kaggle.com/mcp",
            "headers": {"Authorization": "Bearer {env:KAGGLE_API_TOKEN}"}, "enabled": True}
        assert "banco-lia" in opencode["mcp"]

    def test_init_registers_the_colab_mcp_for_every_declared_harness(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "paper"
        init_module.initialize(workspace, run_npm=False, run_env=False)
        args = ["git+https://github.com/googlecolab/colab-mcp@b9ab3899e0f1fa493390b1fd6d54aa2e464ecdf1"]
        claude = json.loads((workspace / ".mcp.json").read_text())
        assert claude["mcpServers"]["colab"] == {
            "type": "stdio", "command": "uvx", "args": args, "timeout": 30000}
        assert {"banco-lia", "kaggle"} <= set(claude["mcpServers"])
        for relpath in (".pi/mcp.json", ".agents/mcp_config.json"):
            servers = json.loads((workspace / relpath).read_text())["mcpServers"]
            assert servers["colab"] == {"command": "uvx", "args": args}, relpath
            assert {"banco-lia", "kaggle"} <= set(servers), relpath
        opencode = json.loads((workspace / "opencode.json").read_text())
        assert opencode["mcp"]["colab"] == {
            "type": "local", "command": ["uvx", *args], "enabled": True}
        assert {"banco-lia", "kaggle"} <= set(opencode["mcp"])

    def test_import_keeps_the_repository_mcp_servers_and_adds_banco_lia(self) -> None:
        workspace = self.new_tmp() / "repo"
        workspace.mkdir()
        own = {"mcpServers": {"mine": {"command": "my-server", "args": []}}}
        (workspace / ".mcp.json").write_text(json.dumps(own), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["init", str(workspace), "--import-existing", "--no-npm", "--no-env"]) == 0
        servers = json.loads((workspace / ".mcp.json").read_text())["mcpServers"]
        assert servers["mine"] == own["mcpServers"]["mine"]
        assert servers["banco-lia"]["command"] == "uvx"

    def test_import_refuses_symlink_directory_without_following_it(self) -> None:
        parent = self.new_tmp()
        workspace = parent / "existing"
        workspace.mkdir()
        external = parent / "outside"
        external.mkdir()
        (workspace / "guidance").symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(UserError, "import collision.*guidance"):
            init_module.initialize(workspace, import_existing=True, run_npm=False, run_env=False)
        assert list(external.iterdir()) == []
        assert sorted(p.name for p in workspace.iterdir()) == ["guidance"]

    def test_import_parent_swap_does_not_write_outside_destination(self) -> None:
        parent = self.new_tmp()
        workspace = parent / "existing"
        reference = workspace / "guidance" / "reference-papers"
        reference.mkdir(parents=True)
        (reference / "source.pdf").write_bytes(b"original")
        external = parent / "outside"
        external.mkdir()
        original_open = init_module.os.open
        reference_inode = reference.stat().st_ino
        swapped = False

        def swap_before_open(path, *args, **kwargs):
            nonlocal swapped
            fd = kwargs.get("dir_fd")
            if (path == ".gitkeep" and fd is not None and not swapped
                    and init_module.os.fstat(fd).st_ino == reference_inode):
                swapped = True
                reference.rename(workspace / "parked-reference-papers")
                reference.symlink_to(external, target_is_directory=True)
            return original_open(path, *args, **kwargs)

        with mock.patch.object(init_module.os, "open", swap_before_open):
            with self.assertRaises(UserError):
                init_module.initialize(workspace, import_existing=True, run_npm=False, run_env=False)
        assert swapped, "the attack must reach the post-preflight file-create boundary"
        assert list(external.iterdir()) == []
        assert (workspace / "parked-reference-papers" / "source.pdf").read_bytes() == b"original"

    def test_import_copy_failure_rolls_back_new_paths_only(self) -> None:
        parent = self.new_tmp()
        workspace = parent / "existing"
        workspace.mkdir()
        original = workspace / "notes.txt"
        original.write_bytes(b"keep")
        staged = parent / "stage"
        (staged / "newdir").mkdir(parents=True)
        (staged / "newdir" / "a.txt").write_bytes(b"a")
        (staged / "newdir" / "b.txt").write_bytes(b"b")
        real_copy = shutil.copyfileobj
        calls = 0

        def fail_second(inp, out):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated copy failure")
            return real_copy(inp, out)

        with mock.patch.object(init_module.shutil, "copyfileobj", side_effect=fail_second):
            with self.assertRaisesRegex(UserError, "import failed"):
                init_module._import_staged(workspace, staged)
        assert original.read_bytes() == b"keep"
        assert sorted(p.name for p in workspace.iterdir()) == ["notes.txt"]

    def test_cli_init_help_describes_import_opt_in(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as exit_info:
                main(["init", "--help"])
        assert exit_info.exception.code == 0
        assert "--import-existing" in output.getvalue()

    def test_cli_init_routes_flags_and_prints_summary(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "cli-paper"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            assert main([
                "init", str(workspace), "--title", "CLI Paper", "--topic", "testing",
                "--tools", "claude,pi", "--remote", "local", "--no-npm",
            "--no-env",
            ]) == 0
        output = buffer.getvalue()
        assert "Initialized papersmith workspace" in output
        assert config.load_workspace_config(workspace)["active_tools"] == ["claude", "pi"]

    def test_generated_yaml_is_parseable_without_third_party_yaml(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "paper"
        init_module.initialize(workspace, run_npm=False, run_env=False)
        parsed = loads((workspace / "papersmith.yaml").read_text(encoding="utf-8"))
        assert parsed["execution_profiles"]["sweep_training"]["sharding"]["values"] == [
            42, 1337, 2026, 9999
        ]

    def test_initialize_seeds_paper_writing_roles(self) -> None:
        # A fresh workspace must carry the connector roles `paper_cli.py
        # resolve` reads: without them it refuses RESOLVER_ROLE_EMPTY and
        # literature scouting cannot start. The block is opaque to the
        # orchestrator's own validation, so this asserts through it.
        tmp_path = self.new_tmp()
        workspace = tmp_path / "paper"
        init_module.initialize(workspace, run_npm=False, run_env=False)
        yaml = config.load_papersmith_yaml(workspace)
        assert yaml["paper_writing"]["roles"]["resolution"] == [
            "openalex", "crossref", "arxiv",
        ], yaml.get("paper_writing")
        assert yaml["paper_writing"]["roles"]["full-text"] == [
            "openalex", "arxiv",
        ], yaml.get("paper_writing")


class WorkspaceSetupEnvTests(unittest.TestCase):
    """`setup_env.py install` inside a workspace must not `pip install -e` it.

    Measured defect: the kit ships `scripts/setup_env.py` into workspaces, and
    `cmd_install` unconditionally ran `pip install -e PROJECT_ROOT` with
    `check=True`. A workspace is not a Python project (no `pyproject.toml` or
    `setup.py`), so pip failed and aborted provisioning before the ingestion engine,
    leaving `OCR Engine Missing`. These load a *copy* of the real script into
    a bare dir -- exactly the workspace situation -- with the process boundary
    stubbed, so no test touches the network.
    """

    REAL_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "setup_env.py"

    def load_copy(self, root: Path):
        dest = root / "scripts" / "setup_env.py"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.REAL_SCRIPT, dest)
        spec = importlib.util.spec_from_file_location("_setup_env_under_test", dest)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def install_calls(self, root: Path, *, no_ingestion: bool = False) -> list[list[str]]:
        module = self.load_copy(root)
        calls: list[list[str]] = []
        module.find_micromamba = lambda: Path("/fake/mm")
        module.env_exists = lambda name: False
        module.detect_cuda = lambda: False
        module.run = lambda mm, args, env: calls.append(list(args))
        args = argparse.Namespace(name="papersmith", cpu=True, cuda=False,
                                  no_ingestion=no_ingestion)
        assert module.cmd_install(args) == 0
        return calls

    def new_bare_root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="papersmith-ws-")).resolve()
        self.addCleanup(shutil.rmtree, root, True)
        return root

    def test_workspace_without_python_project_skips_editable_install(self) -> None:
        calls = self.install_calls(self.new_bare_root())
        assert not any("-e" in call for call in calls), calls
        assert any("docling==2.141.0" in call for call in calls), calls

    def test_build_cli_is_provisioned_even_without_ingestion(self) -> None:
        calls = self.install_calls(self.new_bare_root(), no_ingestion=True)
        conda = [call for call in calls if call[0] in ("create", "install")]
        assert len(conda) == 1, calls
        assert "python-build" in conda[0], calls
        assert not any("docling==2.141.0" in call for call in calls), calls

    def test_checkout_with_pyproject_keeps_editable_install(self) -> None:
        root = self.new_bare_root()
        (root / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        calls = self.install_calls(root)
        editable = [call for call in calls if "-e" in call]
        assert len(editable) == 1, calls
        assert str(root) in editable[0], editable

    def test_initialize_with_agy_alias_resolves_to_antigravity(self) -> None:
        tmp_path = Path(tempfile.mkdtemp(prefix="papersmith-ws-")).resolve()
        self.addCleanup(shutil.rmtree, tmp_path, True)
        workspace = tmp_path / "agy-paper"
        result = init_module.initialize(
            workspace,
            tools=("agy",),
            run_npm=False,
            run_env=False,
        )
        assert result["active_tools"] == ["antigravity"]
        assert (workspace / ".agents/AGENTS.md").is_file()
        assert (workspace / ".agents/skills").is_symlink()
        cfg = json.loads((workspace / ".papersmith/config.json").read_text(encoding="utf-8"))
        assert cfg["active_tools"] == ["antigravity"]
