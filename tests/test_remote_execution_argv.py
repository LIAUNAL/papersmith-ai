"""#56: a `repo_url` never reaches git as an option or through a helper transport.

`generate-job` without `--commit` asks `git ls-remote <repo_url> <repo_ref>`
whether the published tip carries the same clone-path content
(`_published_equivalent`), and the `pin-published` condition runs
`git fetch --dry-run --depth 1 <repo_url> <commit>`. Before the fix both
passed `repo_url` positionally with no `--`, so `--upload-pack=<cmd>` ran
`<cmd>`, and with no protocol restriction an `ext::<cmd>` remote ran `<cmd>`
wherever the target's own config admitted `ext`.

Every fixture is inert: the "command" is a script that only writes a marker
file, and the assertion is that the marker never appears.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REMOTE_CLI_SCRIPT = REPOSITORY_ROOT / "skills/remote-execution/scripts/remote_cli.py"


class RepoUrlArgvBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.origin = self.root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.origin)], check=True)
        self.target = self.root / "target"
        subprocess.run(["git", "init", "-q", str(self.target)], check=True)
        package = self.target / "src" / "pkg"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "harness.py").write_text("def run():\n    return {}\n", encoding="utf-8")
        self.git = ["git", "-C", str(self.target), "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run([*self.git, "add", "-A"], check=True)
        subprocess.run([*self.git, "commit", "-q", "-m", "published"], check=True)
        subprocess.run([*self.git, "remote", "add", "origin", str(self.origin)], check=True)
        subprocess.run([*self.git, "push", "-q", "origin", "HEAD:refs/heads/main"], check=True)
        self.published = subprocess.run(
            [*self.git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        self.marker = self.root / "helper-ran"
        self.helper = self.root / "helper.py"
        self.helper.write_text(
            f"#!{sys.executable}\nopen({str(self.marker)!r}, 'w').close()\nraise SystemExit(1)\n",
            encoding="utf-8",
        )
        self.helper.chmod(0o755)

    def generate(self, repo_url: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REMOTE_CLI_SCRIPT), "generate-job",
             "--target", str(self.target), "--service", "kaggle",
             "--job-name", "probe-job", "--product", "Product",
             f"--repo-url={repo_url}", "--repo-ref", "main",
             "--clone-path", "src/pkg",
             "--run-module", "pkg.harness", "--run-function", "run"],
            capture_output=True, text=True, cwd=str(self.target))

    def test_an_option_like_repo_url_is_never_read_as_a_git_option(self) -> None:
        completed = self.generate(f"--upload-pack={self.helper}")
        self.assertFalse(
            self.marker.exists(),
            "repo_url reached git as --upload-pack and ran a command: "
            + (completed.stdout + completed.stderr)[:300],
        )
        self.assertNotEqual(completed.returncode, 0)

    def test_a_helper_transport_repo_url_is_refused_at_the_git_boundary(self) -> None:
        # The target's own config admits `ext`, as a hostile clone's could.
        subprocess.run([*self.git, "config", "protocol.ext.allow", "always"], check=True)
        completed = self.generate(f"ext::{self.helper}")
        self.assertFalse(
            self.marker.exists(),
            "an ext:: remote ran a command: " + (completed.stdout + completed.stderr)[:300],
        )
        self.assertNotEqual(completed.returncode, 0)

    def test_a_local_published_remote_still_pins_its_tip(self) -> None:
        completed = self.generate(str(self.origin))
        self.assertEqual(completed.returncode, 0, (completed.stdout + completed.stderr)[:300])
        self.assertEqual(json.loads(completed.stdout)["commit"], self.published)


if __name__ == "__main__":
    unittest.main()


class RemoteTransportAdmissibilityTests(unittest.TestCase):
    """Review follow-up: only the helper form `<transport>::` is refused, not a
    `::` inside an IPv6 literal, and the git+ssh spellings stay admissible.
    This is the transport gate the submit-time probe uses; `generate-job`
    refuses SSH remotes by policy before it (tests/test_remote_url_policy.py)."""

    def setUp(self) -> None:
        import importlib.util

        path = REPOSITORY_ROOT / "skills/remote-execution/scripts/jobfolder.py"
        sys.path.insert(0, str(path.parent))
        self.addCleanup(sys.path.remove, str(path.parent))
        spec = importlib.util.spec_from_file_location("jobfolder_admissibility", path)
        self.jobfolder = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.jobfolder  # dataclasses resolve their module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(self.jobfolder)

    def test_ipv6_literals_and_git_ssh_schemes_are_admissible(self) -> None:
        for url in ("https://[2001:db8::1]/o/r.git", "ssh://git@[::1]/r.git",
                    "git+ssh://host/r.git", "ssh+git://host/r.git", "git@host:o/r.git"):
            self.assertTrue(self.jobfolder._remote_transport_admissible(url), url)

    def test_helper_transports_and_options_stay_refused(self) -> None:
        for url in ("ext::sh -c x", "fd::3", "EXT::x", "-u", "--upload-pack=x", "ftp://h/r", ""):
            self.assertFalse(self.jobfolder._remote_transport_admissible(url), url)
