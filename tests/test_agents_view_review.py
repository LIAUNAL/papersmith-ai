"""The agents table follows the workspace's paper line: in a review workspace
each agent's phases are the review steps that use it (``review_board``'s
actions), numbered and labelled like the review board, and the table lists only
those agents; the experimental line keeps its table byte for byte."""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from papersmith.core.init import initialize
from skills._core.command_center import agents_view, review_board

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "skills" / "_core" / "command_center" / "static" / "agents-panel.js"

_TEMPLATES: dict[str, Path] = {}


def _workspace(kind: str) -> Path:
    if kind not in _TEMPLATES:
        ws = Path(tempfile.mkdtemp(prefix=f"t6c-agents-{kind}-")) / "ws"
        extra = {"kind": "review"} if kind == "review" else {}
        initialize(ws, tools=("claude",), run_npm=False, run_env=False, **extra)
        _TEMPLATES[kind] = ws
    return _TEMPLATES[kind]


def tearDownModule() -> None:  # noqa: N802 - unittest hook
    for ws in _TEMPLATES.values():
        shutil.rmtree(ws.parent, ignore_errors=True)


def _label(step: str) -> str:
    return f"Phase {review_board.REVIEW_STAGES.index(step) + 1} — {review_board.REVIEW_LABELS[step]}"


#: Computed on the code before the review line read its own steps.
#: The experimental table's structure (agents, their phases, order and every
#: field but the prose an agent file states about itself, `role` and
#: `description`), computed with the pre-T6c code. An agent's own wording may
#: change with its file; which agents appear and under which phases may not.
# `models` and `model_alerts` read the harness configs under the user's home, so
# they are environment, not structure.
_PROSE_FIELDS = ("role", "description", "models", "model_alerts")
# Moved once, on purpose: the idea-shaping feature added the `idea-guide` agent
# under Phase 2. Without that one agent the view still hashes to the earlier
# pin, 23e55db8f11c4e0eb8a623a8c48f891d04402162992c02e584466e3750936ffc.
# Moved again, on purpose: the four writing judges now pin `model: opus`
# (efficiency stage B, S5), which changes their `model` field.
EXPERIMENTAL_VIEW_SHA256 = "8e265535cb4d034464c87484f02038717bd7f9dcaa193902fa1cd0548ed85683"


class ExperimentalAgentsUnchangedTests(unittest.TestCase):
    def test_the_experimental_view_is_pinned(self) -> None:
        view = agents_view.get_agents_view(_workspace("experimental"))
        self.assertNotIn("paper_kind", view)
        by_name = {a["name"]: a for a in view["agents"]}
        self.assertEqual(by_name["sota-scout"]["phases"], ["Phase 2 — Plausibility"])
        structure = {**view, "agents": [{k: v for k, v in a.items() if k not in _PROSE_FIELDS}
                                        for a in view["agents"]]}
        digest = hashlib.sha256(json.dumps(structure, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        self.assertEqual(digest, EXPERIMENTAL_VIEW_SHA256)


class ReviewAgentsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.view = agents_view.get_agents_view(_workspace("review"))
        self.by_name = {a["name"]: a for a in self.view["agents"]}

    def test_the_view_declares_the_review_line(self) -> None:
        self.assertEqual(self.view["paper_kind"], "review")

    def test_agents_carry_the_review_steps_that_use_them(self) -> None:
        self.assertEqual(self.by_name["paper-ingestion"]["phases"], [_label("screening")])
        self.assertEqual(self.by_name["diagram-author"]["phases"], [_label("synthesis"), _label("paper")])
        self.assertEqual(self.by_name["redactor"]["phases"], [_label("writing")])
        self.assertEqual(self.by_name["insumos-observer"]["phases"], [_label("writing")])
        self.assertEqual(self.by_name["venue-adapter"]["phases"], [_label("paper")])
        self.assertEqual(self.by_name["paper-reviewer"]["phases"], [_label("reporting_audit")])
        self.assertEqual(self.by_name["audit-report"]["phases"], [_label("reporting_audit")])
        prompts = [s for s in review_board.REVIEW_STAGES
                   if any(a["kind"] == "prompt" for a in review_board.REVIEW_ACTIONS[s]["actions"])]
        self.assertEqual(self.by_name["prompt-reviewer"]["phases"], [_label(s) for s in prompts])

    def test_agents_no_review_step_uses_have_no_phase(self) -> None:
        for name in ("sota-scout", "novelty-screener", "math-tutor", "dataset-scout", "experiments-build",
                     "paper-replicator", "paper-type-advisor"):
            with self.subTest(agent=name):
                self.assertEqual(self.by_name[name]["phases"], [])

    def test_phase_labels_follow_the_review_board_numbering(self) -> None:
        for agent in self.view["agents"]:
            numbers = [int(re.match(r"Phase (\d+) — ", p).group(1)) for p in agent["phases"]]
            self.assertEqual(numbers, sorted(set(numbers)), agent["name"])
            for phase in agent["phases"]:
                number = int(phase.split()[1])
                self.assertEqual(phase, _label(review_board.REVIEW_STAGES[number - 1]))

    def test_the_line_is_read_from_the_workspace_on_every_call(self) -> None:
        base = Path(tempfile.mkdtemp(prefix="t6c-agents-switch-"))
        try:
            ws = base / "ws"
            shutil.copytree(_workspace("review"), ws, symlinks=True)
            config = ws / ".papersmith" / "config.json"
            data = json.loads(config.read_text(encoding="utf-8"))
            data["paper_kind"] = "experimental"
            config.write_text(json.dumps(data), encoding="utf-8")
            view = agents_view.get_agents_view(ws)
            self.assertNotIn("paper_kind", view)
            sota = next(a for a in view["agents"] if a["name"] == "sota-scout")
            self.assertEqual(sota["phases"], ["Phase 2 — Plausibility"])
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_the_table_lists_only_the_review_agents(self) -> None:
        node = shutil.which("node", path="/usr/bin") or shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        script = r"""
const fs = require('fs');
const vm = require('vm');
const host = { innerHTML: '', querySelectorAll: () => [] };
const ctx = { window: { i18n: { t: (key, vars) => key + JSON.stringify(vars || {}) } }, document: { getElementById: () => host, addEventListener() {} }, console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const view = JSON.parse(fs.readFileSync(0, 'utf8'));
ctx.window.AgentsPanel.render(view);
const names = [...host.innerHTML.matchAll(/<tr><td><code>([^<]+)<\/code>/g)].map((m) => m[1]);
process.stdout.write(JSON.stringify({ names, html: host.innerHTML }));
"""
        out = subprocess.run([node, "-e", script, str(PANEL)], input=json.dumps(self.view),
                             capture_output=True, text=True, timeout=60, check=True)
        shown = json.loads(out.stdout)
        expected = sorted(a["name"] for a in self.view["agents"] if a["phases"])
        self.assertEqual(sorted(shown["names"]), expected)
        self.assertNotIn("sota-scout", shown["names"])
        self.assertIn(f'agents.count{{"n":{len(expected)},"total":{len(expected)}}}', html.unescape(shown["html"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
