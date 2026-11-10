"""A populated 0.13.0 workspace upgrades to this release and keeps everything.

The workspace under test is `tests/fixtures/workspace_v0_13_0/workspace.tar.gz`,
produced by `scripts/build-v0_13_0-fixture.py` driving the 0.13.0 tree's own
CLI and engines (see `tests/fixtures/README.md`). It holds what a paper in
progress accumulates: two managed proposal revisions and one experiments
revision with their receipts, state and locks, and an implementation target
carrying the scaffold receipt, the kit's seal file, both implementation
skills' declared holders with settled items, and their position ledger.

One upgrade with today's CLI must leave every one of those bytes alone, apply
or find satisfied every registered migration, leave `audit --check-drift`
clean, and leave the engines able to read what they wrote.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from papersmith import __version__
from papersmith.cli import main
from papersmith.core import migrations, upgrade as upgrade_module

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "workspace_v0_13_0"
TARGET = "implementations/Smoother"
PACKAGE = "Smoother"

#: Every fixture file the upgrade is meant to rewrite, and why. Anything else
#: the fixture holds must come out byte-identical.
INTENDED_CHANGES = {
    ".papersmith/config.json": "upgrade rewrites `updated_at` on every run",
    ".papersmith/manifest.json": "the baseline now records this release's files",
    ".papersmith/version": "the marker moves to this release once migrations finish",
    ".gitignore": "0.14.0 wraps the framework's lines in a managed block and ignores the "
                  "deliberation engines' state (tests/test_workspace_gitignore.py)",
    "papersmith.yaml": "the paper-writing-asta-roles migration names Ai2's Asta first in the "
                       "resolution and discovery roles, used only with its key "
                       "(tests/test_connector_roles_migration.py)",
}

#: The deliberation engines and the profile each reads.
DELIBERATION_SKILLS = ("proposal-deliberation", "experimental-deliberation")
IMPLEMENTATION_HOLDERS = {
    "proposal-implementation": f"{PACKAGE}/AGREED.md",
    "experimental-implementation": f"{PACKAGE}/Experimental_AGREED.md",
}


def _listing() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in (FIXTURE / "contents.sha256").read_text(encoding="utf-8").splitlines():
        digest, relpath = line.split("  ", 1)
        entries[relpath] = digest
    return entries


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_fixture(destination: Path) -> Path:
    """The 0.13.0 workspace, extracted into ``destination/workspace``."""
    workspace = destination / "workspace"
    workspace.mkdir(parents=True)
    with tarfile.open(FIXTURE / "workspace.tar.gz") as tar:
        tar.extractall(workspace, filter="data")
    return workspace


def _fixture_text(relpath: str) -> str:
    """One file of the 0.13.0 workspace as it was shipped, before any upgrade."""
    with tempfile.TemporaryDirectory() as holder:
        return (extract_fixture(Path(holder)) / relpath).read_text(encoding="utf-8")


def run_upgrade(workspace: Path) -> dict:
    """Today's upgrade, the dirty-kit override passed explicitly: the
    checkout this suite runs from may carry uncommitted edits."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return upgrade_module.upgrade(workspace, allow_dirty_kit=True)


class UpgradeOfAPopulatedV0130WorkspaceTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._holder = tempfile.TemporaryDirectory()
        cls.workspace = extract_fixture(Path(cls._holder.name).resolve())
        cls.before = {relpath: _sha256(cls.workspace / relpath) for relpath in _listing()}
        cls.recorded_before = (cls.workspace / ".papersmith" / "version").read_text(
            encoding="utf-8").strip()
        cls.report = run_upgrade(cls.workspace)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._holder.cleanup()

    def test_the_fixture_is_what_its_listing_says(self) -> None:
        """The archive and the reviewable listing agree, and the workspace
        really was recorded at 0.13.0."""
        self.assertEqual(self.before, _listing())
        self.assertEqual(self.recorded_before, "0.13.0")

    def test_the_fixture_holds_every_kind_of_artifact_it_is_meant_to_test(self) -> None:
        listed = set(_listing())
        expected_prefixes = (
            ".proposal-deliberation/receipts/", ".proposal-deliberation/state/",
            ".proposal-deliberation/locks/", ".experimental-deliberation/receipts/",
            ".experimental-deliberation/state/", ".experimental-deliberation/locks/",
            "proposals/research-concept-", "experiments/experiments-",
            f"{TARGET}/.implementation/materialization.json",
            f"{TARGET}/src/{PACKAGE}/report_digest.py",
            f"{TARGET}/{PACKAGE}/.implementation/position.jsonl",
            *(f"{TARGET}/{holder}" for holder in IMPLEMENTATION_HOLDERS.values()),
        )
        for prefix in expected_prefixes:
            with self.subTest(prefix=prefix):
                self.assertTrue(any(path.startswith(prefix) for path in listed), prefix)
        revisions = [path for path in listed if path.startswith("proposals/research-concept-")]
        self.assertGreaterEqual(len(revisions), 2, "a v1 and one successor")

    def test_the_connector_roles_name_asta_first_and_keep_everything_else(self) -> None:
        from papersmith import yamllite

        text = (self.workspace / "papersmith.yaml").read_text(encoding="utf-8")
        roles = yamllite.loads(text)["paper_writing"]["roles"]
        self.assertEqual(roles["resolution"], ["asta", "openalex", "crossref", "arxiv"])
        self.assertEqual(roles["discovery"], ["asta"])
        self.assertEqual(roles["full-text"], ["openalex", "arxiv"])
        # Only the two role lists moved: every other line of the operator's file is kept.
        before = _fixture_text("papersmith.yaml").splitlines()
        after = text.splitlines()
        self.assertEqual([line for line in after if line not in ("      - asta", "    discovery:")],
                         [line for line in before if line != "    discovery: []"])

    def test_nothing_the_workspace_made_changes_except_what_is_listed_as_intended(self) -> None:
        changed = {relpath for relpath, digest in self.before.items()
                   if _sha256(self.workspace / relpath) != digest}
        self.assertEqual(changed, set(INTENDED_CHANGES))

    def test_the_marker_reaches_this_release(self) -> None:
        self.assertEqual(self.report["recorded_version"], __version__)

    def test_every_registered_migration_applies_or_is_already_satisfied(self) -> None:
        outcome = self.report["migrations"]
        self.assertEqual(outcome["failures"], [])
        self.assertEqual(outcome["undetermined"], [])
        reached = {entry["id"] for entry in outcome["applied"]} | set(outcome["satisfied"])
        self.assertEqual(reached, {migration.id for migration in migrations.REGISTRY})
        for entry in outcome["applied"]:
            self.assertEqual(entry["failures"], [], entry["id"])

    def test_audit_reports_no_drift_after_one_upgrade(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main(["audit", str(self.workspace), "--check-drift"])
        self.assertEqual(code, 0, out.getvalue()[-2000:])
        self.assertIn("drift: clean", out.getvalue())

    def test_each_implementation_skill_still_reads_its_own_holder(self) -> None:
        # Each launcher must reach its OWN profile, the one it defaults to. An
        # inherited IMPLEMENTATION_DOMAIN_PROFILE is an explicit override
        # that wins over that default, so it is not passed on (X8b): one
        # left in this process by an earlier test made the experimental
        # launcher read the proposal skill's holder.
        env = {key: value for key, value in os.environ.items()
               if key != "IMPLEMENTATION_DOMAIN_PROFILE"}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        for skill, holder in IMPLEMENTATION_HOLDERS.items():
            with self.subTest(skill=skill):
                completed = subprocess.run(
                    [sys.executable, f"skills/{skill}/scripts/implementation_cli.py", "verify",
                     "--target", TARGET, "--name", PACKAGE],
                    cwd=self.workspace, capture_output=True, text=True, check=False,
                    env=env)
                self.assertEqual(completed.returncode, 0, completed.stdout[-2000:])
                payload = json.loads(completed.stdout)
                self.assertNotEqual(payload.get("status"), "refused", payload.get("detail"))
                self.assertEqual(payload["agreements"]["holders"], [holder])
                self.assertEqual(len(payload["agreements"]["open"]), 1)
                self.assertIn(f"({skill})", payload["agreements"]["open"][0])
                self.assertEqual(payload["position"]["holder"], holder)
                self.assertEqual(payload["fidelity"]["missingProvenance"], [],
                                 "the kit's seal file still owes no provenance")

    def test_each_deliberation_engine_audits_its_own_tree_clean(self) -> None:
        node = shutil.which("node")
        modules = REPO_ROOT / "node_modules"
        if node is None or not modules.is_dir():
            self.skipTest("node and the repository's node_modules are required for this leg")
        link = self.workspace / "node_modules"
        link.symlink_to(modules, target_is_directory=True)
        self.addCleanup(link.unlink)
        script = (
            "import {createJiti} from 'jiti';"
            "const root=process.cwd();"
            "const jiti=createJiti(root+'/');"
            "const audit=await jiti.import(root+'/skills/_core/deliberation/engine/consistency-audit.ts');"
            "const result=await audit.runConsistencyAudit({projectRoot:root});"
            "process.stdout.write(JSON.stringify({status:result.status,failures:result.failures}));"
        )
        for skill in DELIBERATION_SKILLS:
            with self.subTest(skill=skill):
                env = {key: value for key, value in os.environ.items()
                       if not key.startswith(("DELIBERATION_", "PROPOSAL_DELIBERATION_"))}
                env["DELIBERATION_DOMAIN_PROFILE"] = str(
                    self.workspace / "skills" / skill / "profile.ts")
                completed = subprocess.run([node, "--input-type=module", "-e", script],
                                           cwd=self.workspace, env=env, capture_output=True,
                                           text=True, check=False, timeout=180)
                self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
                result = json.loads(completed.stdout)
                self.assertEqual(result, {"status": "PASS", "failures": []})

    def test_the_experiments_revision_takes_a_successor_after_upgrade(self) -> None:
        """X15: 0.13.0 pasted the published proposal revisions into the experiments v1
        verbatim, reserved artifact marker lines included, and no successor could be
        accepted from it. Its bytes stay as they are; a successor that keeps the copied
        markers is refused with the sections that hold them, and one that replaces those
        sections without the marker lines is published. Runs on a copy, so the other
        tests keep reading the upgraded workspace untouched."""
        node = shutil.which("node")
        modules = REPO_ROOT / "node_modules"
        if node is None or not modules.is_dir():
            self.skipTest("node and the repository's node_modules are required for this leg")
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        workspace = Path(holder.name).resolve() / "workspace"
        shutil.copytree(self.workspace, workspace, symlinks=True)
        (workspace / "node_modules").symlink_to(modules, target_is_directory=True)
        source = "experiments-smoothing-window-sweep-v01.md"
        before = _sha256(workspace / "experiments" / source)
        self.assertEqual(before, _listing()[f"experiments/{source}"])
        self.assertEqual((workspace / "experiments" / source).read_text(
            encoding="utf-8").count("proposal-workspace:artifact"), 3,
            "the fixture's v1 carries its own marker and two copied ones")

        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("DELIBERATION_", "PROPOSAL_DELIBERATION_"))}
        upstream = "proposals/research-concept-smoothing-estimator-for-noisy-sequences"
        loci = {
            "insert": [("window length estimator error", lambda entry: {
                "kind": "insert", "anchorEntryId": entry, "position": "after",
                "content": "## Experiment [exp:E1] -- window sweep\n\nOne declared experiment.\n\n"})],
            "repair": [
                (f"### {upstream}-r01.md", lambda entry: {
                    "kind": "replace", "targetEntryId": entry,
                    "replacementText": f"### {upstream}-r01.md\n\n"}),
                (f"### {upstream}-r02.md", lambda entry: {
                    "kind": "replace", "targetEntryId": entry,
                    "replacementText": f"### {upstream}-r02.md\n\nThe estimator averages a fixed window "
                                       "of past observations.\n\n"}),
            ],
        }

        def successor(name: str) -> tuple[dict, dict | None]:
            process = subprocess.Popen(
                [node, "skills/experimental-deliberation/cli.mjs", "--serve"], cwd=workspace,
                env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

            def call(request: dict) -> dict:
                process.stdin.write(json.dumps(request) + "\n")
                process.stdin.flush()
                return json.loads(process.stdout.readline())

            try:
                decisions = []
                for query, decision in loci[name]:
                    resolved = call({"operation": "RESOLVE_TARGET", "sourceFilename": source, "query": query})
                    self.assertEqual(resolved.get("status"), "resolved", resolved)
                    decisions.append(decision(resolved["entryId"]))
                queries = [query for query, _ in loci[name]]
                request = {
                    "operation": "CREATE_SUCCESSOR", "sourceFilename": source,
                    **({"selectedEntryId": queries[0]} if len(queries) == 1 else {"selectedEntryIds": queries}),
                    "resolvedDecisions": decisions, "instruction": "Revise the named sections.",
                    "changeSummary": {"what": "Revised the named sections.", "why": "Upgrade check."},
                }
                preview = call(request)
                accepted = None
                if preview.get("status") == "awaiting_acceptance":
                    accepted = call({**request, "acceptSuccessor": True,
                                     "successorAcceptanceToken": preview["acceptanceToken"]})
                return preview, accepted
            finally:
                process.stdin.close()
                process.wait(timeout=180)

        preview, _ = successor("insert")
        self.assertEqual(preview.get("status"), "blocked", preview)
        self.assertEqual(preview.get("nextAction"), "repair_candidate", preview)
        self.assertEqual([b["code"] for b in preview.get("blockers", [])],
                         ["successor-copied-artifact-marker"], preview)
        for name in ("r01", "r02"):
            self.assertIn(f"{upstream}-{name}.md", preview["blockers"][0]["message"])

        preview, accepted = successor("repair")
        self.assertEqual(preview.get("status"), "awaiting_acceptance", preview)
        self.assertEqual(accepted and accepted.get("status"), "published", accepted)
        written = (workspace / "experiments" / accepted["targetFilename"]).read_text(encoding="utf-8")
        self.assertEqual(written.count("proposal-workspace:artifact"), 1)
        self.assertEqual(_sha256(workspace / "experiments" / source), before,
                         "the 0.13.0 revision is never rewritten")


if __name__ == "__main__":
    unittest.main()
