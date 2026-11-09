"""`smith ui --publish-pages`: the read-only snapshot on GitHub Pages (`/ui-github`).

Nothing here reaches GitHub. The workspace's `origin` is configured as a
github.com URL (which is what the owner/repo is read from) and rewritten by
`url.<bare>.insteadOf` to a local bare repository, so the push lands on disk;
`gh` is a fake on PATH that records its argv and answers the Pages API.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith import cli
from papersmith.core import init as init_module
from papersmith.core import pages
from papersmith.errors import UserError
from skills._core.command_center import static_export

REPO = Path(__file__).resolve().parents[1]

FAKE_GH = r'''#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\n")
scenario = os.environ.get("FAKE_GH_SCENARIO", "missing")
if args[:2] == ["auth", "status"]:
    sys.exit(1 if scenario == "unauthenticated" else 0)
if args[:1] == ["api"] and "-X" not in args:
    if scenario == "missing":
        print('{{"message": "Not Found"}}')
        print("gh: Not Found (HTTP 404)", file=sys.stderr)
        sys.exit(1)
    branch = "gh-pages" if scenario == "serving" else "main"
    print(json.dumps({{"html_url": "https://o.github.io/r/", "source": {{"branch": branch, "path": "/"}}}}))
    sys.exit(0)
if "-X" in args and args[args.index("-X") + 1] == "POST":
    print(json.dumps({{"html_url": "https://o.github.io/r/"}}))
    sys.exit(0)
sys.exit(0)
'''


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=str(cwd) if cwd else None, check=True,
                          capture_output=True, text=True).stdout.strip()


def tree_state(workspace: Path) -> dict:
    """HEAD, current branch, index bytes, status and every working-tree file."""
    files = {}
    for path in sorted(workspace.rglob("*")):
        if ".git" in path.relative_to(workspace).parts:
            continue
        if path.is_file() and not path.is_symlink():
            files[str(path.relative_to(workspace))] = hashlib.sha256(path.read_bytes()).hexdigest()
    index = workspace / ".git" / "index"
    return {"head": git("rev-parse", "HEAD", cwd=workspace),
            "branch": git("symbolic-ref", "HEAD", cwd=workspace),
            "index": hashlib.sha256(index.read_bytes()).hexdigest(),
            "status": git("status", "--porcelain", "--untracked-files=all", cwd=workspace),
            "files": files}


class PagesPublishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.holder = tempfile.TemporaryDirectory()
        base = Path(cls.holder.name).resolve()
        cls.base = base
        cls.workspace = base / "pages-ws"
        init_module.initialize(cls.workspace, run_npm=False, run_env=False, allow_dirty_kit=True)
        archive = cls.workspace / ".papersmith" / "ai-history"
        archive.mkdir(parents=True, exist_ok=True)
        (archive / "claude-code-0123abcd-9f8e7d6c.jsonl").write_text(json.dumps(
            {"id": "a1", "ts": "2026-01-01T00:00:00Z", "role": "user", "text": "/plausibility an idea"}) + "\n",
            encoding="utf-8")
        ws = cls.workspace
        git("init", "-q", "-b", "main", str(ws))
        git("config", "user.name", "Pages Tester", cwd=ws)
        git("config", "user.email", "pages.tester@example.com", cwd=ws)
        git("add", "papersmith.yaml", cwd=ws)
        git("commit", "-q", "-m", "init", cwd=ws)
        (ws / "papersmith.yaml").write_text((ws / "papersmith.yaml").read_text(encoding="utf-8") + "\n",
                                            encoding="utf-8")  # an unstaged edit the publish must keep
        cls.bare = base / "remote.git"
        git("init", "-q", "--bare", str(cls.bare))
        git("remote", "add", "origin", "https://github.com/o/r.git", cwd=ws)
        git("config", f"url.{cls.bare}.insteadOf", "https://github.com/o/r.git", cwd=ws)
        bindir = base / "bin"
        bindir.mkdir()
        fake = bindir / "gh"
        fake.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
        fake.chmod(0o755)
        cls.bindir = bindir

        cls.before = tree_state(ws)
        cls.first = cls.publish("--yes", scenario="missing")
        cls.first_files = cls.ls_tree()
        cls.first_manifest = json.loads(git("--git-dir", str(cls.bare), "show",
                                            "gh-pages:snapshot/manifest.json"))
        cls.first_log = git("--git-dir", str(cls.bare), "log", "--format=%H %P|%an <%ae>|%s", "gh-pages")
        cls.after = tree_state(ws)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.holder.cleanup()

    @classmethod
    def publish(cls, *flags: str, scenario: str = "missing", directory: Path | None = None) -> dict:
        log = cls.base / f"gh-{scenario}-{len(list(cls.base.glob('gh-*.log')))}.log"
        log.write_text("", encoding="utf-8")
        env = {"PATH": f"{cls.bindir}{os.pathsep}{os.environ.get('PATH', '')}",
               "FAKE_GH_LOG": str(log), "FAKE_GH_SCENARIO": scenario}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = cli.main(["ui", str(directory or cls.workspace), "--publish-pages", *flags])
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        return {"code": code, "out": out.getvalue(), "err": err.getvalue(), "gh": calls}

    @classmethod
    def ls_tree(cls) -> list[str]:
        return git("--git-dir", str(cls.bare), "ls-tree", "-r", "--name-only", "gh-pages").splitlines()

    def test_the_branch_holds_exactly_a_fresh_snapshot(self) -> None:
        self.assertEqual(self.first["code"], 0, self.first["out"] + self.first["err"])
        expected = self.base / "expected-site"
        static_export.export_snapshot(self.workspace, expected)
        names = sorted(str(p.relative_to(expected)) for p in expected.rglob("*") if p.is_file())
        self.assertEqual(sorted(self.first_files), names)
        for name in ("index.html", "snapshot/manifest.json", ".nojekyll"):
            self.assertIn(name, self.first_files)
        self.assertFalse(any(name.startswith((".papersmith/", "papersmith.yaml", "skills/"))
                             for name in self.first_files))

    def test_the_commit_is_a_single_orphan_by_the_configured_user(self) -> None:
        lines = self.first_log.splitlines()
        self.assertEqual(len(lines), 1, lines)
        ids, author, subject = lines[0].split("|")
        self.assertEqual(len(ids.split()), 1, "the commit has a parent")
        self.assertEqual(author, "Pages Tester <pages.tester@example.com>")
        self.assertRegex(subject, r"^Publish the read-only dashboard snapshot \(\d{4}-\d\d-\d\dT[\d:]+Z\)$")

    def test_the_workspace_is_left_exactly_as_it_was(self) -> None:
        self.assertEqual(self.before, self.after)
        self.assertNotIn("gh-pages", git("branch", "--list", cwd=self.workspace))

    def test_the_ai_history_is_included_by_default(self) -> None:
        self.assertTrue(any(key.startswith("/api/ai-history") for key in self.first_manifest["entries"]))
        self.assertIn("AI history: included", self.first["out"])
        self.assertIn("PUBLIC", self.first["out"])

    def test_missing_pages_site_is_created_from_the_branch(self) -> None:
        self.assertEqual(self.first["gh"], [
            ["auth", "status"],
            ["api", "repos/o/r/pages"],
            ["api", "-X", "POST", "repos/o/r/pages", "-f", "source[branch]=gh-pages", "-f", "source[path]=/"],
        ])
        self.assertIn("https://o.github.io/r/", self.first["out"])
        self.assertIn("a minute or two", self.first["out"])

    def test_no_ai_history_and_a_site_on_another_branch(self) -> None:
        result = self.publish("--yes", "--no-ai-history", scenario="wrong-branch")
        self.assertEqual(result["code"], 0, result["out"] + result["err"])
        manifest = json.loads(git("--git-dir", str(self.bare), "show", "gh-pages:snapshot/manifest.json"))
        self.assertFalse(any(key.startswith("/api/ai-history") for key in manifest["entries"]))
        self.assertIn("AI history: not included", result["out"])
        self.assertEqual(git("--git-dir", str(self.bare), "rev-list", "--count", "gh-pages"), "1")
        self.assertEqual(result["gh"], [
            ["auth", "status"],
            ["api", "repos/o/r/pages"],
            ["api", "-X", "PUT", "repos/o/r/pages", "-f", "source[branch]=gh-pages", "-f", "source[path]=/"],
        ])
        self.assertEqual(tree_state(self.workspace), self.before)

    def test_unauthenticated_gh_publishes_and_prints_the_command(self) -> None:
        result = self.publish("--yes", "--pages-branch", "site-pages", scenario="unauthenticated")
        self.assertEqual(result["code"], 0, result["err"])
        self.assertEqual(result["gh"], [["auth", "status"]])
        self.assertIn("gh api -X POST repos/o/r/pages -f 'source[branch]=site-pages' -f 'source[path]=/'",
                      result["out"])
        self.assertIn("site-pages", git("--git-dir", str(self.bare), "branch", "--list"))

    def test_refuses_without_confirmation_when_not_interactive(self) -> None:
        stale = git("--git-dir", str(self.bare), "rev-parse", "gh-pages")
        with mock.patch("sys.stdin", io.StringIO("")):
            result = self.publish(scenario="serving")
        self.assertEqual(result["code"], 1)
        self.assertIn("--yes", result["err"])
        self.assertEqual(result["gh"], [])
        self.assertEqual(git("--git-dir", str(self.bare), "rev-parse", "gh-pages"), stale)

    def test_refuses_a_missing_or_non_github_remote(self) -> None:
        result = self.publish("--yes", "--pages-remote", "upstream")
        self.assertEqual(result["code"], 1)
        self.assertIn("no git remote named 'upstream'", result["err"])
        git("remote", "add", "elsewhere", str(self.bare), cwd=self.workspace)
        try:
            result = self.publish("--yes", "--pages-remote", "elsewhere")
        finally:
            git("remote", "remove", "elsewhere", cwd=self.workspace)
        self.assertEqual(result["code"], 1)
        self.assertIn("not a GitHub repository", result["err"])
        self.assertEqual(result["gh"], [])

    def test_refuses_a_workspace_that_is_not_a_repository(self) -> None:
        plain = self.base / "plain-ws"
        init_module.initialize(plain, run_npm=False, run_env=False, allow_dirty_kit=True)
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.base)}):
            result = self.publish("--yes", directory=plain)
        self.assertEqual(result["code"], 1)
        self.assertIn("not a git repository", result["err"])

    def test_refuses_when_the_export_fails(self) -> None:
        with mock.patch("papersmith.core.ui._run_child", return_value=1):
            result = self.publish("--yes", "--pages-branch", "never-pushed")
        self.assertEqual(result["code"], 1)
        self.assertIn("export failed", result["err"])
        self.assertNotIn("never-pushed", git("--git-dir", str(self.bare), "branch", "--list"))


class RemoteUrlTests(unittest.TestCase):
    def test_github_forms(self) -> None:
        for url in ("https://github.com/o/r.git", "git@github.com:o/r.git", "https://github.com/o/r",
                    "ssh://git@github.com/o/r.git", "https://github.com/o/r/"):
            with self.subTest(url=url):
                self.assertEqual(pages.parse_github_remote(url), ("o", "r"))
        self.assertEqual(pages.parse_github_remote("https://github.com/amalvarezme/qmleegV2.git"),
                         ("amalvarezme", "qmleegV2"))

    def test_other_hosts_are_refused(self) -> None:
        for url in ("https://gitlab.com/o/r.git", "/srv/git/r.git", "git@example.com:o/r.git",
                    "https://github.com.evil.example/o/r.git", "https://github.com/o"):
            with self.subTest(url=url), self.assertRaises(UserError):
                pages.parse_github_remote(url)

    def test_default_site_url(self) -> None:
        self.assertEqual(pages.default_site_url("o", "r"), "https://o.github.io/r/")
        self.assertEqual(pages.default_site_url("o", "o.github.io"), "https://o.github.io/")


class UiGithubSkillTests(unittest.TestCase):
    def test_the_skill_names_the_flags_and_is_a_slash_command(self) -> None:
        skill = (REPO / "skills/ui-github/SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: ui-github\ndescription: \"Trigger:"))
        for needle in ("--publish-pages", "--no-ai-history", "--yes", "PUBLIC", "$ARGUMENTS"):
            with self.subTest(needle=needle):
                self.assertIn(needle, skill)
        command = (REPO / ".claude/commands/ui-github.md").read_text(encoding="utf-8")
        self.assertIn("skills/ui-github/SKILL.md", command)
        self.assertIn("$ARGUMENTS", command)


if __name__ == "__main__":
    unittest.main()
