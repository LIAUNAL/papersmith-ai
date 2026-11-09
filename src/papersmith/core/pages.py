"""``smith ui --publish-pages``: publish the read-only dashboard snapshot to GitHub Pages.

The snapshot itself is written by the workspace's own kit
(``skills/_core/command_center/static_export.py``, run through
``smith ui --export-snapshot``). This module only moves those files to GitHub:

1. it commits the snapshot directory as ONE orphan commit, built with git
   plumbing against a temporary index file (``GIT_INDEX_FILE``) and the
   snapshot as the work tree, so the workspace's HEAD, index, current branch
   and working tree are never touched and no workspace file can enter the
   commit;
2. it force-pushes that commit to ``refs/heads/<branch>`` of the workspace's
   remote (``gh-pages`` of ``origin`` by default);
3. it asks ``gh api`` whether GitHub Pages serves that branch, enables it
   (``POST``) or repoints it (``PUT``) when needed, and reports the site URL.

A Pages site is public even when the repository is private, so the caller
prints what is about to be published and requires an explicit confirmation.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..errors import UserError

DEFAULT_BRANCH = "gh-pages"
DEFAULT_REMOTE = "origin"

#: ``https://github.com/o/r(.git)``, ``ssh://git@github.com/o/r.git``,
#: ``git@github.com:o/r.git``. Anything else is not a GitHub remote.
_GITHUB_REMOTE = re.compile(
    r"^(?:(?:https?|ssh|git)://(?:[^@/]+@)?github\.com(?::\d+)?/"
    r"|(?:[^@/]+@)?github\.com:)"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)/(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?/?$"
)

Runner = Callable[..., subprocess.CompletedProcess]


def parse_github_remote(url: str) -> tuple[str, str]:
    """Return ``(owner, repo)`` of a GitHub remote URL, or refuse."""
    match = _GITHUB_REMOTE.match(url.strip())
    if not match or match.group("repo") in ("", ".", ".."):
        raise UserError(
            f"the remote URL {url!r} is not a GitHub repository; GitHub Pages can only "
            "publish to a github.com remote (https://github.com/<owner>/<repo>.git or "
            "git@github.com:<owner>/<repo>.git)"
        )
    return match.group("owner"), match.group("repo")


def _git(args: list[str], *, cwd: Path, env: dict[str, str] | None = None,
         run: Runner = subprocess.run) -> subprocess.CompletedProcess:
    return run(["git", *args], cwd=str(cwd), env=env, capture_output=True, text=True)


def remote_url(workspace: Path, remote: str, *, run: Runner = subprocess.run) -> str:
    """The URL configured for ``remote`` in the workspace's repository, or refuse.

    Read from the configuration as written (``remote.<name>.url``), not through
    ``git remote get-url``, which applies ``url.<base>.insteadOf`` rewrites: the
    GitHub owner and repository are the ones the operator configured.
    """
    inside = _git(["rev-parse", "--is-inside-work-tree"], cwd=workspace, run=run)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise UserError(f"{workspace} is not a git repository, so it has no remote "
                        f"{remote!r} to publish GitHub Pages to; add one with "
                        "`git remote add origin https://github.com/<owner>/<repo>.git`")
    found = _git(["config", "--get", f"remote.{remote}.url"], cwd=workspace, run=run)
    url = found.stdout.strip()
    if found.returncode != 0 or not url:
        raise UserError(f"{workspace} has no git remote named {remote!r}; add one with "
                        f"`git remote add {remote} https://github.com/<owner>/<repo>.git` "
                        "or pass --pages-remote <name>")
    return url


def site_summary(site: Path) -> dict:
    """File count, total bytes, and whether the snapshot carries the AI history."""
    files = [path for path in site.rglob("*") if path.is_file() and not path.is_symlink()]
    total = sum(path.stat().st_size for path in files)
    ai_history = False
    manifest = site / "snapshot" / "manifest.json"
    try:
        entries = json.loads(manifest.read_text(encoding="utf-8")).get("entries", {})
        ai_history = any(str(key).startswith("/api/ai-history") for key in entries)
    except (OSError, ValueError, AttributeError):
        pass
    return {"files": len(files), "bytes": total, "ai_history": ai_history}


def human_size(count: int) -> str:
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{count} B"  # pragma: no cover


def commit_message(now: datetime | None = None) -> str:
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return f"Publish the read-only dashboard snapshot ({moment.strftime('%Y-%m-%dT%H:%M:%SZ')})"


def push_snapshot(workspace: Path, site: Path, *, remote: str = DEFAULT_REMOTE,
                  branch: str = DEFAULT_BRANCH, now: datetime | None = None,
                  run: Runner = subprocess.run) -> str:
    """Commit ``site`` as a single orphan commit and force-push it to ``remote``.

    Returns the commit id. The commit is built with a temporary index file and
    ``site`` as the work tree: the workspace's own index, HEAD, branches and
    files are left as they were (only new objects enter its object store).
    """
    git_dir_found = _git(["rev-parse", "--absolute-git-dir"], cwd=workspace, run=run)
    if git_dir_found.returncode != 0:
        raise UserError(f"{workspace} is not a git repository: {git_dir_found.stderr.strip()}")
    git_dir = git_dir_found.stdout.strip()
    with tempfile.TemporaryDirectory(prefix="smith-pages-index-") as holder:
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = str(Path(holder) / "index")
        base = ["--git-dir", git_dir, "--work-tree", str(site)]

        def step(args: list[str]) -> str:
            done = _git(base + args, cwd=site, env=env, run=run)
            if done.returncode != 0:
                raise UserError(f"git {' '.join(args[:2])} failed while publishing the snapshot: "
                                f"{(done.stderr or done.stdout).strip()}")
            return done.stdout.strip()

        # --force: a global excludes file must not silently drop snapshot files.
        step(["add", "--all", "--force", "."])
        tree = step(["write-tree"])
        sha = step(["commit-tree", tree, "-m", commit_message(now)])
        step(["push", "--force", remote, f"{sha}:refs/heads/{branch}"])
    return sha


def pages_commands(owner: str, repo: str, branch: str, *, method: str = "POST") -> list[str]:
    return ["api", "-X", method, f"repos/{owner}/{repo}/pages",
            "-f", f"source[branch]={branch}", "-f", "source[path]=/"]


def _shell(argv: list[str]) -> str:
    return " ".join(arg if re.fullmatch(r"[A-Za-z0-9_./:=@-]+", arg) else f"'{arg}'" for arg in argv)


def default_site_url(owner: str, repo: str) -> str:
    if repo.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner}.github.io/"
    return f"https://{owner}.github.io/{repo}/"


def ensure_pages(owner: str, repo: str, branch: str = DEFAULT_BRANCH, *,
                 run: Runner = subprocess.run, report=print) -> tuple[bool, str]:
    """Make GitHub Pages serve ``branch`` at ``/``; return ``(ok, site url)``.

    ``ok`` is False only when ``gh`` answered with an error other than "no
    site yet"; a missing or unauthenticated ``gh`` is reported with the exact
    command to run and still counts as ok, since the branch is published.
    """
    fallback = default_site_url(owner, repo)
    manual = "gh " + _shell(pages_commands(owner, repo, branch))
    if shutil.which("gh") is None:
        report(f"smith ui: `gh` is not installed, so GitHub Pages was not configured. "
               f"Enable it once with:\n  {manual}\n"
               f"(or Settings > Pages > Deploy from a branch > {branch} / root)")
        return True, fallback

    def gh(args: list[str]) -> subprocess.CompletedProcess:
        return run(["gh", *args], capture_output=True, text=True)

    if gh(["auth", "status"]).returncode != 0:
        report(f"smith ui: `gh` is not authenticated (`gh auth login`), so GitHub Pages was not "
               f"configured. Enable it once with:\n  {manual}")
        return True, fallback

    current = gh(["api", f"repos/{owner}/{repo}/pages"])
    if current.returncode != 0:
        if "404" not in (current.stderr or "") and "Not Found" not in (current.stdout or ""):
            report(f"smith ui: `gh api repos/{owner}/{repo}/pages` failed: "
                   f"{(current.stderr or current.stdout).strip()}\nEnable Pages with:\n  {manual}")
            return False, fallback
        created = gh(pages_commands(owner, repo, branch, method="POST"))
        if created.returncode != 0:
            report(f"smith ui: enabling GitHub Pages failed: "
                   f"{(created.stderr or created.stdout).strip()}\n"
                   f"(a private repository needs GitHub Pro, Team or Enterprise for Pages)\n"
                   f"Enable it with:\n  {manual}")
            return False, fallback
        report(f"smith ui: enabled GitHub Pages for {owner}/{repo} from {branch} /")
        return True, _html_url(created.stdout) or fallback

    site = _parse(current.stdout)
    source = site.get("source") or {}
    url = _html_url(current.stdout) or fallback
    if source.get("branch") == branch and source.get("path", "/") == "/":
        report(f"smith ui: GitHub Pages already serves {owner}/{repo} from {branch} /")
        return True, url
    updated = gh(pages_commands(owner, repo, branch, method="PUT"))
    if updated.returncode != 0:
        report(f"smith ui: pointing GitHub Pages at {branch} failed: "
               f"{(updated.stderr or updated.stdout).strip()}\nRun:\n  "
               f"gh {_shell(pages_commands(owner, repo, branch, method='PUT'))}")
        return False, url
    report(f"smith ui: GitHub Pages for {owner}/{repo} now serves {branch} / "
           f"(it served {source.get('branch') or 'nothing'} {source.get('path') or ''})".rstrip())
    return True, url


def _parse(text: str) -> dict:
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _html_url(text: str) -> str | None:
    url = _parse(text).get("html_url")
    return url if isinstance(url, str) and url.startswith("https://") else None


__all__ = [
    "DEFAULT_BRANCH", "DEFAULT_REMOTE", "parse_github_remote", "remote_url", "site_summary",
    "push_snapshot", "ensure_pages", "commit_message", "default_site_url", "pages_commands",
]
