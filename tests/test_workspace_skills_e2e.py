"""From-scratch skill series: every shipped skill, exercised inside the workspace.

Layer purpose. The bridge suites prove each engine against fixtures; this module
proves the *shipped copy* — the skill tree a ``smith init`` workspace
carries — declares itself, answers its front door, and runs its offline verbs
against the workspace it lives in. A skill that only works in the repository
checkout is not a shipped skill.

Boundaries stay hermetic: ``node_modules`` is symlinked (no npm install), the
deliberation engines run keyless, and nothing here reaches the network.
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from papersmith.generators import collect_commands

from workspace_series import (
    REPO_ROOT,
    link_node_modules,
    make_workspace,
    new_tmp,
    run_node,
    run_workspace_script,
)

SKILL_NAMES = (
    "datasets",
    "experiment-diagrams",
    "experimental-deliberation",
    "experimental-implementation",
    "figure-review",
    "hyperparameter-search",
    "kaggle-accounts",
    "math-tutor",
    "paper-ingestion",
    "paper-writing",
    "plausibility",
    "proposal-deliberation",
    "proposal-implementation",
    "remote-execution",
    "remote-parallelism",
    "skill-audit",
    "upgrade-project",
)

PAPER_WRITING_VERBS = (
    "scaffold", "status", "open", "substitute", "contract", "readiness",
    "order", "declare", "observe", "resolve", "bib", "validate", "plan",
    "write", "render", "verify", "place", "figure",
)


def frontmatter(path: Path) -> dict[str, str]:
    """Parse the single-line key/value frontmatter a SKILL.md carries."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].strip() == "---", f"{path} has no frontmatter"
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            value = value.strip()
            if value[:1] in {"'", '"'}:
                value = ast.literal_eval(value)
            metadata[key.strip()] = value
    return metadata


class SkillTreeTests(unittest.TestCase):

    def test_every_repository_skill_ships_in_the_workspace(self) -> None:
        workspace = make_workspace(new_tmp(self))
        repo = {path.name for path in (REPO_ROOT / "skills").iterdir() if path.is_dir()}
        shipped = {path.name for path in (workspace / "skills").iterdir() if path.is_dir()}
        self.assertEqual(shipped, repo, "the workspace must ship the whole skill tree")

    def test_every_skill_declares_itself(self) -> None:
        workspace = make_workspace(new_tmp(self))
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                skill_md = workspace / "skills" / name / "SKILL.md"
                self.assertTrue(skill_md.is_file(), f"{name} ships no SKILL.md")
                metadata = frontmatter(skill_md)
                self.assertEqual(metadata.get("name"), name)
                self.assertTrue(metadata.get("description", "").strip())

    def test_shared_engines_ship_with_the_skills(self) -> None:
        workspace = make_workspace(new_tmp(self))
        self.assertTrue((workspace / "skills/_core/deliberation/engine/cli.mjs").is_file())
        self.assertTrue((workspace / "skills/_core/implementation/engine").is_dir())

    def test_every_skill_becomes_exactly_one_slash_command(self) -> None:
        workspace = make_workspace(new_tmp(self))
        sink: list[str] = []
        names = [item["name"] for item in collect_commands(workspace, warnings=sink)]
        self.assertEqual(names, list(SKILL_NAMES))
        self.assertEqual(sink, [], "a healthy workspace skips no skill")


class SkillFrontDoorTests(unittest.TestCase):
    """Each shipped front door explains its own accepted set, offline."""

    def test_figure_review_front_door_lists_its_commands(self) -> None:
        workspace = make_workspace(new_tmp(self))
        proc = run_workspace_script(
            workspace, "skills/figure-review/scripts/review_cli.py", ["--help"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for verb in ("probe", "raster"):
            self.assertIn(verb, proc.stdout, f"review_cli must advertise {verb}")

    def test_paper_writing_front_door_lists_its_nineteen_verbs(self) -> None:
        workspace = make_workspace(new_tmp(self))
        proc = run_workspace_script(workspace, "skills/paper-writing/scripts/paper_cli.py", ["--help"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for verb in PAPER_WRITING_VERBS:
            self.assertIn(verb, proc.stdout, f"paper_cli must advertise {verb}")

    def test_implementation_front_doors_advertise_their_own_rosters(self) -> None:
        workspace = make_workspace(new_tmp(self))
        proposal = run_workspace_script(
            workspace, "skills/proposal-implementation/scripts/implementation_cli.py", ["--help"])
        self.assertEqual(proposal.returncode, 0, proposal.stderr)
        for verb in ("probe", "verify", "materialize", "walk"):
            self.assertIn(verb, proposal.stdout)
        self.assertNotIn("agree", proposal.stdout,
                         "agree belongs to the second host only")

        experiments = run_workspace_script(
            workspace, "skills/experimental-implementation/scripts/implementation_cli.py", ["--help"])
        self.assertEqual(experiments.returncode, 0, experiments.stderr)
        self.assertIn("agree", experiments.stdout)

    def test_remote_execution_front_door_lists_its_operations(self) -> None:
        workspace = make_workspace(new_tmp(self))
        proc = run_workspace_script(
            workspace, "skills/remote-execution/scripts/remote_cli.py", ["--help"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for verb in ("submit", "status", "distribute", "poll", "fetch",
                     "reconcile", "generate-job", "smoke", "readiness"):
            self.assertIn(verb, proc.stdout)

    def test_kaggle_accounts_front_door_lists_its_commands(self) -> None:
        workspace = make_workspace(new_tmp(self))
        proc = run_workspace_script(
            workspace, "skills/kaggle-accounts/scripts/accounts_cli.py", ["--help"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for verb in ("list", "discover", "validate", "remove", "materialize"):
            self.assertIn(verb, proc.stdout)

    def test_skill_audit_front_door_lists_its_commands(self) -> None:
        workspace = make_workspace(new_tmp(self))
        proc = run_workspace_script(
            workspace, "skills/skill-audit/scripts/audit_cli.py", ["--help"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for verb in ("roster", "check-report", "structure", "walkthrough"):
            self.assertIn(verb, proc.stdout)

    def test_deliberation_front_doors_report_their_objective_keyless(self) -> None:
        workspace = make_workspace(new_tmp(self))
        link_node_modules(workspace)
        proposal = run_node(
            workspace / "skills/proposal-deliberation/cli.mjs",
            '{"operation":"STATUS"}', workspace=workspace)
        self.assertEqual(proposal.returncode, 0, proposal.stderr)
        payload = json.loads(proposal.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("mathematics", payload["objective"]["purpose"])

        experiments = run_node(
            workspace / "skills/experimental-deliberation/cli.mjs",
            '{"operation":"STATUS"}', workspace=workspace)
        self.assertEqual(experiments.returncode, 0, experiments.stderr)
        payload = json.loads(experiments.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("experiments", payload["objective"]["purpose"])


class SkillWorkspaceVerbTests(unittest.TestCase):
    """The offline verbs a skill's own SKILL.md promises, run for real."""

    def test_paper_writing_scaffolds_and_reports_status_inside_the_workspace(self) -> None:
        workspace = make_workspace(new_tmp(self))
        paper = workspace / "paper"
        scaffold = run_workspace_script(
            workspace, "skills/paper-writing/scripts/paper_cli.py",
            ["scaffold", "--paper", str(paper)])
        self.assertEqual(scaffold.returncode, 0, scaffold.stderr)
        self.assertEqual(json.loads(scaffold.stdout)["status"], "ok")
        self.assertTrue((paper / "main.tex").is_file())

        status = run_workspace_script(
            workspace, "skills/paper-writing/scripts/paper_cli.py",
            ["status", "--paper", str(paper)])
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)["blocks"], [])

    def test_kaggle_accounts_store_ships_empty_and_lists_without_keys(self) -> None:
        workspace = make_workspace(new_tmp(self))
        proc = run_workspace_script(
            workspace, "skills/kaggle-accounts/scripts/accounts_cli.py", ["list"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("No accounts stored.", proc.stdout)
        self.assertFalse((workspace / "skills/kaggle-accounts/store/accounts.json").exists(),
                         "a generated workspace must never ship stored credentials")

    def test_paper_ingestion_lists_pending_pdfs_without_loading_a_model(self) -> None:
        workspace = make_workspace(new_tmp(self))
        proc = run_workspace_script(
            workspace, "skills/paper-ingestion/scripts/extract_pdf.py", ["--list"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("no loose PDFs", proc.stdout)

    def test_remote_execution_refuses_an_unresolvable_job_target(self) -> None:
        workspace = make_workspace(new_tmp(self))
        missing = workspace / "implementations" / "missing"
        proc = run_workspace_script(
            workspace, "skills/remote-execution/scripts/remote_cli.py",
            ["status", "--target", str(missing), "--entrypoint", "Notebooks/a.ipynb"])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("does not resolve to an existing directory", proc.stdout + proc.stderr)
