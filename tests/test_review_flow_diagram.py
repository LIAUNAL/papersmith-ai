"""The review line has its own Archify flow diagram, and the dashboard serves it.

`/api/flow` serves a workspace's own `docs/papersmith-flow.html` when there is
one, for either line; otherwise a review workspace (`paper_kind: review`) gets
the review flow shipped with the dashboard
(`static/papersmith-review-flow.html`, a copy of
`docs/diagrams/papersmith-review-flow.html`) and an experimental workspace keeps
the Pi flow (`static/papersmith-flow.html`), unchanged. The drawing's lanes are
the ten review steps of the board, and every `review_cli.py` verb and `review/`
record it names exists, so the diagram cannot drift from the code silently."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from papersmith.core import init as init_module
from skills._core.command_center import review_board, server

REPO = Path(__file__).resolve().parents[1]
STATIC = Path(server.__file__).resolve().parent / "static"
BUILD = REPO / "docs" / "diagrams" / "papersmith-review-flow.build.mjs"
REVIEW_CLI = REPO / "skills" / "systematic-review" / "scripts" / "review_cli.py"


class _Workspace(unittest.TestCase):
    def workspace(self, kind: str) -> Path:
        holder = tempfile.TemporaryDirectory(prefix=f"review-flow-{kind}-", ignore_cleanup_errors=True)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name) / "ws"
        init_module.initialize(root, tools=("claude",), run_npm=False, run_env=False, kind=kind)
        return root

    def flow(self, root: Path):
        return TestClient(server.create_app(root)).get("/api/flow")


class ApiFlowFollowsTheLineTests(_Workspace):
    def test_a_review_workspace_gets_the_review_flow(self) -> None:
        response = self.flow(self.workspace("review"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/html"))
        self.assertEqual(response.text, (STATIC / "papersmith-review-flow.html").read_text(encoding="utf-8"))

    def test_an_experimental_workspace_keeps_the_pi_flow(self) -> None:
        response = self.flow(self.workspace("experimental"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/html"))
        self.assertEqual(response.text, (STATIC / "papersmith-flow.html").read_text(encoding="utf-8"))

    def test_a_workspace_own_flow_wins_for_both_lines(self) -> None:
        for kind in ("experimental", "review"):
            with self.subTest(kind=kind):
                root = self.workspace(kind)
                own = root / "docs" / "papersmith-flow.html"
                own.parent.mkdir(parents=True, exist_ok=True)
                own.write_text(f"<html><body>own {kind} flow</body></html>", encoding="utf-8")
                response = self.flow(root)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.text, own.read_text(encoding="utf-8"))


class ReviewFlowArtifactTests(unittest.TestCase):
    def test_the_review_flow_ships_with_the_dashboard_and_matches_the_docs(self) -> None:
        self.assertEqual((STATIC / "papersmith-review-flow.html").read_bytes(),
                         (REPO / "docs" / "diagrams" / "papersmith-review-flow.html").read_bytes())

    def test_the_lanes_are_the_ten_review_steps_in_order(self) -> None:
        source = BUILD.read_text(encoding="utf-8")
        lanes = re.findall(r"\['[a-z]+','(\d+) · ([^']+)'\]", source)
        self.assertEqual([int(number) for number, _ in lanes], list(range(1, 11)))
        labels = [review_board.REVIEW_LABELS[stage] for stage in review_board.REVIEW_STAGES]
        for (_, label), expected in zip(lanes, labels):
            self.assertTrue(label.startswith(expected), (label, expected))

    def test_the_three_operator_gates_are_drawn(self) -> None:
        source = BUILD.read_text(encoding="utf-8")
        for gate in ("G-PROTOCOL", "G-SCREENING", "G-SYNTHESIS"):
            self.assertIn(f"'{gate}'", source)

    def test_every_review_cli_verb_drawn_exists(self) -> None:
        source = BUILD.read_text(encoding="utf-8")
        verbs = set(re.findall(r"review_cli\.py ([a-z]+)", source))
        self.assertTrue(verbs)
        defined = set(re.findall(r'sub\.add_parser\("([a-z]+)"', REVIEW_CLI.read_text(encoding="utf-8")))
        defined |= {"queue", "conflicts"}  # registered in a loop
        self.assertEqual(verbs - defined, set())

    def test_every_review_record_drawn_is_a_record_the_cli_or_board_names(self) -> None:
        source = BUILD.read_text(encoding="utf-8")
        drawn = set(re.findall(r"review/([a-z.]+\.jsonl?)", source))
        known = set(re.findall(r'"([a-z.]+\.jsonl?)"', REVIEW_CLI.read_text(encoding="utf-8")))
        self.assertTrue({"protocol.json", "protocol.lock.json", "searches.jsonl", "records.jsonl",
                         "screening.jsonl", "appraisal.jsonl", "extraction.jsonl", "prisma.json",
                         "signoffs.json", "biblio.json", "prioritization.json"} <= drawn)
        self.assertEqual(drawn - known, set())
        self.assertIn("paper/Figures/prisma-flow.svg", source)


if __name__ == "__main__":
    unittest.main()
