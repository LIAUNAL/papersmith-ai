"""The plausibility flow keeps what `resolve` caches inside `sota-pool/`.

`sota-scout` and `novelty-screener` borrow paper-writing's `resolve` to confirm
a candidate's metadata. `resolve` caches every answer, and by default under
`paper/.paper-writing/metadata/` -- so scouting an idea, before any paper
exists, started a paper tree. The agents now pass `--cache-dir`, naming the
pool they already write everything else into; paper-writing's own calls pass
nothing and keep caching under `paper/`, where `bib` and `full_text` look.

The invocation exercised here is read out of each agent's own definition, not
restated, and it runs against the copy of `paper_cli.py` a workspace ships,
from the workspace root, the way an agent runs it. The network is replaced by
an in-process opener (`paper_resolve.OPENER`, the seam the offline tests use).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from workspace_series import REPO_ROOT, make_workspace, new_tmp

AGENTS = ("sota-scout", "novelty-screener")
IDENTIFIER = "10.1000/example"

#: Run inside the workspace: imports the workspace's own `paper_cli`, so its
#: `FORGE_ROOT` and `papersmith.yaml` are the workspace's, and answers every
#: request with one canned OpenAlex record.
DRIVER = r'''
import io, json, sys
from pathlib import Path
workspace = Path(sys.argv[1])
sys.path.insert(0, str(workspace / "skills" / "paper-writing" / "scripts"))
import paper_cli, paper_resolve

class Answer:
    def open(self, request, timeout=None):
        # BytesIO is already a context manager whose read() is the body.
        return io.BytesIO(json.dumps({"title": "A Paper", "doi": "10.1000/example",
                                      "publication_year": 2024}).encode())

paper_resolve.OPENER = Answer()
sys.exit(paper_cli.main(sys.argv[2:]))
'''


def agent_invocation(agent: str) -> list[str]:
    """The `paper_cli.py resolve` command an agent's definition tells it to
    run, as argv, with its placeholders filled for one identifier."""
    text = (REPO_ROOT / ".claude" / "agents" / f"{agent}.md").read_text(encoding="utf-8")
    spans = [span for span in re.findall(r"`([^`]*)`", text, flags=re.S)
             if "paper_cli.py resolve" in span]
    if len(spans) != 1:
        raise AssertionError(f"{agent}: expected one resolve invocation, found {spans}")
    argv = spans[0].split()
    filled = {"<id>": IDENTIFIER, "{openalex,crossref,arxiv}": "openalex"}  # an older wording
    argv = [filled.get(token, token) for token in argv]
    if argv[:2] != ["python", "skills/paper-writing/scripts/paper_cli.py"]:
        raise AssertionError(f"{agent}: unexpected launcher {argv[:2]}")
    return argv[2:]


def _tree(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


class PlausibilityResolveCacheTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = new_tmp(self)
        self.workspace = make_workspace(self.tmp)
        self.driver = self.tmp / "driver.py"
        self.driver.write_text(DRIVER, encoding="utf-8")

    def run_resolve(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(self.driver), str(self.workspace), *argv],
            cwd=self.workspace, capture_output=True, text=True, check=False)

    def test_each_agents_invocation_caches_in_the_pool_and_leaves_paper_alone(self) -> None:
        for agent in AGENTS:
            with self.subTest(agent=agent):
                paper_before = _tree(self.workspace / "paper")
                completed = self.run_resolve(agent_invocation(agent))
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                digest = json.loads(completed.stdout)["metadata_digest"]
                self.assertEqual(_tree(self.workspace / "paper"), paper_before,
                                 "scouting must not start a paper tree")
                cached = list((self.workspace / "sota-pool").rglob(f"{digest}.json"))
                self.assertEqual(len(cached), 1, _tree(self.workspace / "sota-pool"))
                self.assertEqual(json.loads(cached[0].read_text(encoding="utf-8"))["title"],
                                 "A Paper")

    def test_paper_writing_resolve_still_caches_under_paper(self) -> None:
        completed = self.run_resolve(["resolve", "--identifier", IDENTIFIER,
                                      "--resolver", "openalex", "--role", "resolution"])
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        digest = json.loads(completed.stdout)["metadata_digest"]
        cached = self.workspace / "paper" / ".paper-writing" / "metadata" / f"{digest}.json"
        self.assertTrue(cached.is_file())
        self.assertFalse((self.workspace / "sota-pool" / "metadata").exists())

    def test_a_cache_dir_outside_the_repository_refuses_before_any_request(self) -> None:
        outside = self.tmp / "elsewhere"
        completed = self.run_resolve(["resolve", "--identifier", IDENTIFIER,
                                      "--resolver", "openalex", "--cache-dir", str(outside)])
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["code"], "PAPER_OUTSIDE_REPOSITORY")
        self.assertFalse(outside.exists())

    def test_paper_and_cache_dir_are_one_choice_not_two(self) -> None:
        completed = self.run_resolve(["resolve", "--identifier", IDENTIFIER,
                                      "--resolver", "openalex", "--paper", "paper",
                                      "--cache-dir", "sota-pool/metadata"])
        self.assertEqual(completed.returncode, 2)
        self.assertIn("not allowed with argument", completed.stderr)
        self.assertEqual(_tree(self.workspace / "paper"), [".gitkeep"])


if __name__ == "__main__":
    unittest.main()
