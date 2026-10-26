"""#56 acceptance refinement: a credential embedded in `repo_url` never travels.

`run-config.json` is committed with the target and uploaded with the job, so a
URL such as `https://<user>:<token>@host/r.git` would put a secret into a
persisted artifact, into git's argv and into refusal text. Generation refuses
it before any git call or write, and every read of a job folder refuses it
again. Every credential below is an inert dummy; no git process may start
(`GIT_TRACE` would record one).
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "skills/remote-execution/scripts"
REMOTE_CLI_SCRIPT = SCRIPTS / "remote_cli.py"
DUMMY_SECRET = "psmith-inert-dummy-token-56"


def _load_jobfolder():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("jobfolder_url_policy", SCRIPTS / "jobfolder.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RepoUrlUserinfoTests(unittest.TestCase):
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
        git = ["git", "-C", str(self.target), "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "published"], check=True)
        subprocess.run([*git, "push", "-q", str(self.origin), "HEAD:refs/heads/main"], check=True)
        self.trace = self.root / "git-trace.log"

    def generate(self, repo_url: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "GIT_TRACE": str(self.trace)}
        return subprocess.run(
            [sys.executable, str(REMOTE_CLI_SCRIPT), "generate-job",
             "--target", str(self.target), "--service", "kaggle",
             "--job-name", "probe-job", "--product", "Product",
             f"--repo-url={repo_url}", "--repo-ref", "main",
             "--clone-path", "src/pkg",
             "--run-module", "pkg.harness", "--run-function", "run"],
            capture_output=True, text=True, cwd=str(self.target), env=env)

    def test_repository_url_userinfo_is_rejected_before_persistence(self) -> None:
        for url in (f"https://psmith-user:{DUMMY_SECRET}@example.invalid/r.git",
                    f"https://{DUMMY_SECRET}@example.invalid/r.git",
                    f"ssh://git:{DUMMY_SECRET}@example.invalid/r.git",
                    f"git:{DUMMY_SECRET}@example.invalid:o/r.git"):
            with self.subTest(url=url):
                completed = self.generate(url)
                output = completed.stdout + completed.stderr
                self.assertNotEqual(completed.returncode, 0, output[:300])
                self.assertIn("credential", output)
                self.assertNotIn(DUMMY_SECRET, output)
                self.assertFalse(self.trace.exists(), "a git process started")
                self.assertFalse((self.target / "tools").exists(), "a job folder was written")
                leaked = [p for p in self.root.rglob("*")
                          if p.is_file() and DUMMY_SECRET.encode() in p.read_bytes()]
                self.assertEqual(leaked, [])

    def test_a_job_folder_carrying_userinfo_is_refused_when_read(self) -> None:
        completed = self.generate(str(self.origin))
        self.assertEqual(completed.returncode, 0, (completed.stdout + completed.stderr)[:300])
        config_path = self.target / "tools" / "kaggle" / "probe-job" / "run-config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["repo"]["url"] = f"https://psmith-user:{DUMMY_SECRET}@example.invalid/r.git"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        jobfolder = _load_jobfolder()
        with self.assertRaises(jobfolder.JobFolderError) as caught:
            jobfolder.read(config_path.parent)
        self.assertIn("credential", str(caught.exception))
        self.assertNotIn(DUMMY_SECRET, str(caught.exception))

    def test_ssh_login_names_and_plain_urls_stay_admissible(self) -> None:
        jobfolder = _load_jobfolder()
        for url in ("git@github.com:o/r.git", "ssh://git@host/r.git",
                    "https://example.invalid/r.git", "https://[2001:db8::1]/r.git",
                    "/srv/repos/a@b.git", str(self.origin)):
            jobfolder.refuse_repo_url_credentials(url, where="test")


if __name__ == "__main__":
    unittest.main()
