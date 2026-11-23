"""The command center's kind -> board registry (paper-type-lines S8, T8-G2).

Every place that used to branch on ``paper_kind == "review"`` (the status
board, `/api/phase/run`, `/api/flow`, the sections, the AI history, the agents
table and the page) looks the workspace's line up in one registry,
``command_center.lines``. The experimental and review lines keep exactly the
board they had (their own pins hold that); a line registered with
``lines.register`` gets its own board with no other change; and a line with no
board shows the experimental board with a visible notice instead of silently
pretending to be experimental.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from papersmith.core.init import initialize
from skills._core.command_center import (agents_view, ai_history, ai_transcripts, lines, paper_preview,
                                         phase_actions, review_board, server, state_extractor)

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "skills" / "_core" / "command_center" / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
UNREGISTERED = "unregistered-test-line"
REGISTERED = "registered-test-line"

_TEMPLATES: dict[str, Path] = {}


def _template(kind: str) -> Path:
    """One initialized workspace per kit kind, copied by each test."""
    if kind not in _TEMPLATES:
        ws = Path(tempfile.mkdtemp(prefix=f"t8g2-{kind}-")) / "ws"
        initialize(ws, tools=("claude",), run_npm=False, run_env=False,
                   **({"kind": "review"} if kind == "review" else {}))
        _TEMPLATES[kind] = ws
    return _TEMPLATES[kind]


def tearDownModule() -> None:  # noqa: N802 - unittest hook
    for ws in _TEMPLATES.values():
        shutil.rmtree(ws.parent, ignore_errors=True)


def _set_kind(root: Path, kind: str) -> None:
    config = root / ".papersmith" / "config.json"
    data = json.loads(config.read_text(encoding="utf-8"))
    data["paper_kind"] = kind
    config.write_text(json.dumps(data), encoding="utf-8")


class _Case(unittest.TestCase):
    def workspace(self, kit: str = "experimental", kind: str | None = None) -> Path:
        holder = tempfile.TemporaryDirectory(prefix="t8g2-case-", ignore_cleanup_errors=True)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name) / "ws"
        shutil.copytree(_template(kit), root, symlinks=True)
        if kind is not None:
            _set_kind(root, kind)
        return root

    def status(self, root: Path, lang: str = "") -> dict:
        response = TestClient(server.create_app(root)).get("/api/status" + (f"?lang={lang}" if lang else ""))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()


class RegistryTests(unittest.TestCase):
    def test_the_two_existing_lines_are_registered_from_their_modules(self) -> None:
        self.assertIn("experimental", lines.BOARDS)
        self.assertIn("review", lines.BOARDS)
        experimental = lines.board("experimental")
        self.assertEqual(experimental.kind, "experimental")
        self.assertIs(experimental.actions, phase_actions.ACTIONS)
        self.assertIs(experimental.evidence, phase_actions.EVIDENCE)
        self.assertEqual(experimental.stages, phase_actions.STAGES)
        self.assertEqual(experimental.phase_gates, phase_actions.PHASE_GATES)
        self.assertEqual(experimental.section_order, state_extractor.SECTION_ORDER)
        self.assertEqual(experimental.flow_html, "papersmith-flow.html")
        review = lines.board("review")
        self.assertEqual(review.stages, review_board.REVIEW_STAGES)
        self.assertIs(review.actions, review_board.REVIEW_ACTIONS)
        self.assertEqual(review.labels, review_board.REVIEW_LABELS)
        self.assertEqual(review.section_order, state_extractor.REVIEW_SECTION_ORDER)
        self.assertEqual(review.flow_html, "papersmith-review-flow.html")
        self.assertIsNone(experimental.notice)
        self.assertIsNone(review.notice)

    def test_a_line_without_a_board_falls_back_visibly(self) -> None:
        fallback = lines.board(UNREGISTERED)
        self.assertFalse(lines.registered(UNREGISTERED))
        self.assertEqual(fallback.kind, "experimental")
        self.assertEqual(fallback.stages, phase_actions.STAGES)
        self.assertIn(UNREGISTERED, fallback.notice)
        self.assertIn("no board yet", fallback.notice)
        # Its contracts are listed as they are on disk, never as missing experimental ones.
        self.assertEqual(fallback.section_order, ())

    def test_register_refuses_a_second_board_for_the_same_kind(self) -> None:
        with self.assertRaises(ValueError):
            lines.register(dataclasses.replace(lines.board("review"), kind="review"))

    def test_the_section_order_follows_the_line(self) -> None:
        for kind, expected in (("experimental", state_extractor.SECTION_ORDER),
                               ("review", state_extractor.REVIEW_SECTION_ORDER), (UNREGISTERED, ())):
            with self.subTest(kind=kind):
                root = Path(tempfile.mkdtemp(prefix="t8g2-order-"))
                self.addCleanup(shutil.rmtree, root, True)
                (root / ".papersmith").mkdir()
                (root / ".papersmith" / "config.json").write_text(json.dumps({"paper_kind": kind}),
                                                                   encoding="utf-8")
                self.assertEqual(state_extractor.section_order(root), expected)

    def test_phase_actions_reads_the_registry(self) -> None:
        fases = [{"id": f"Fase {n}", "stage_id": s, "status": "PENDING"}
                 for n, s in enumerate(phase_actions.STAGES, start=1)]
        experimental = phase_actions.attach(json.loads(json.dumps(fases)), None, kind="experimental")
        unknown = phase_actions.attach(json.loads(json.dumps(fases)), None, kind=UNREGISTERED)
        self.assertEqual(unknown, experimental)
        self.assertEqual(phase_actions.primary_command("harness", UNREGISTERED),
                         phase_actions.primary_command("harness"))
        self.assertEqual(ai_transcripts.skill_stages(UNREGISTERED), ai_transcripts.skill_stages("experimental"))
        self.assertEqual(ai_transcripts.command_verbs("review"), ai_transcripts.review_verbs())
        self.assertEqual(ai_transcripts.command_verbs(UNREGISTERED), {})


class UnregisteredLineStatusTests(_Case):
    def test_the_status_shows_the_experimental_board_with_a_notice(self) -> None:
        experimental = self.status(self.workspace())
        self.assertNotIn("board_notice", experimental)
        self.assertNotIn("board_kind", experimental)
        root = self.workspace(kind=UNREGISTERED)
        (root / "sections" / "02-experimental-setup.md").unlink()
        status = self.status(root)
        self.assertEqual(status["paper_kind"], UNREGISTERED)
        self.assertEqual(status["board_kind"], "experimental")
        self.assertIn(UNREGISTERED, status["board_notice"])
        self.assertEqual([f["stage_id"] for f in status["fases"]], list(phase_actions.STAGES))
        self.assertEqual([g["id"] for g in status["gates"]], [g["id"] for g in experimental["gates"]])
        # The contracts on disk, in order; none reported missing.
        ids = [s["id"] for s in status["sections"]]
        self.assertNotIn("02-experimental-setup", ids)
        self.assertEqual(ids, sorted(ids))
        self.assertEqual([s["id"] for s in paper_preview.build_preview(root)["sections"]], ids)
        self.assertEqual(self.status(root, "es")["board_kind"], "experimental")

    def test_the_other_routes_answer_without_error(self) -> None:
        root = self.workspace(kind=UNREGISTERED)
        client = TestClient(server.create_app(root))
        flow = client.get("/api/flow")
        self.assertEqual(flow.status_code, 200)
        self.assertEqual(flow.text, (STATIC / "papersmith-flow.html").read_text(encoding="utf-8"))
        for number in (1, 6):
            with self.subTest(phase=number):
                response = client.post("/api/phase/run", json={"phase_id": f"Fase {number}"})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["stage"], phase_actions.STAGES[number - 1])
        self.assertEqual(client.get("/api/paper/preview").status_code, 200)
        self.assertEqual(client.get("/api/agents").status_code, 200)


class RegisteredLineTests(_Case):
    """Registering a board is all a new line needs (what O4 will do)."""

    def setUp(self) -> None:
        lines.register(dataclasses.replace(lines.board("review"), kind=REGISTERED))
        self.addCleanup(lines.BOARDS.pop, REGISTERED, None)

    def test_a_registered_line_gets_its_board_everywhere(self) -> None:
        review_root = self.workspace("review")
        root = self.workspace("review", kind=REGISTERED)
        review, status = self.status(review_root), self.status(root)
        self.assertEqual(status["paper_kind"], REGISTERED)
        self.assertNotIn("board_notice", status)
        self.assertEqual([f["stage_id"] for f in status["fases"]], list(review_board.REVIEW_STAGES))
        self.assertEqual([g["id"] for g in status["gates"]], [g["id"] for g in review["gates"]])
        self.assertEqual([s["id"] for s in status["sections"]], [s["id"] for s in review["sections"]])
        client = TestClient(server.create_app(root))
        self.assertEqual(client.get("/api/flow").text,
                         (STATIC / "papersmith-review-flow.html").read_text(encoding="utf-8"))
        body = client.post("/api/phase/run", json={"phase_id": "Fase 3"}).json()
        self.assertEqual(body["stage"], review_board.REVIEW_STAGES[2])
        view = agents_view.get_agents_view(root)
        self.assertEqual(view["paper_kind"], REGISTERED)
        reference = agents_view.get_agents_view(review_root)
        self.assertEqual([a["phases"] for a in view["agents"]], [a["phases"] for a in reference["agents"]])


class HistoryAndAgentsTests(_Case):
    SESSION = [
        json.dumps({"type": "user", "timestamp": "2026-10-01T10:00:00Z",
                    "message": {"role": "user", "content": "/paper-writing mark language: English"}}),
        json.dumps({"type": "assistant", "timestamp": "2026-10-01T10:01:00Z",
                    "message": {"role": "assistant", "content": [{"type": "text", "text": "Recorded."}]}}),
    ]

    def sessions(self) -> dict:
        holder = tempfile.TemporaryDirectory(prefix="t8g2-chats-")
        self.addCleanup(holder.cleanup)
        chats = Path(holder.name)
        (chats / "s1.jsonl").write_text("\n".join(self.SESSION) + "\n", encoding="utf-8")
        ai_transcripts.clear_cache()
        return {"claude-code": chats, "pi": None, "opencode": None, "antigravity": None}

    def test_ai_history_of_an_unregistered_line_uses_the_experimental_phases_and_says_so(self) -> None:
        fases = [{"id": f"Fase {n}", "stage_id": s, "name": f"Phase {n}", "gate": "G", "status": "PENDING",
                  "agent": "a"} for n, s in enumerate(phase_actions.STAGES, start=1)]
        sessions = self.sessions()
        experimental = ai_history.build_ai_history(self.workspace(), fases, sessions=sessions)
        unknown = ai_history.build_ai_history(self.workspace(kind=UNREGISTERED), fases, sessions=sessions)
        self.assertNotIn("board_notice", experimental)
        self.assertIn(UNREGISTERED, unknown.pop("board_notice"))
        self.assertEqual([(p["stage_id"], p["label"], p["total_events"]) for p in unknown["phases"]],
                         [(p["stage_id"], p["label"], p["total_events"]) for p in experimental["phases"]])
        declarations = next(p for p in unknown["phases"] if p["stage_id"] == "declarations")
        self.assertGreater(declarations["total_events"], 0)
        usage = ai_history.build_ai_usage(self.workspace(kind=UNREGISTERED), sessions=sessions)
        self.assertEqual([p["stage_id"] for p in usage["phases"]],
                         [p["stage_id"] for p in ai_history.build_ai_usage(self.workspace(),
                                                                           sessions=sessions)["phases"]])

    def test_agents_of_an_unregistered_line_keep_the_experimental_phases_and_say_so(self) -> None:
        experimental = agents_view.get_agents_view(self.workspace())
        unknown = agents_view.get_agents_view(self.workspace(kind=UNREGISTERED))
        self.assertNotIn("paper_kind", unknown)
        self.assertNotIn("board_notice", experimental)
        self.assertIn(UNREGISTERED, unknown.pop("board_notice"))
        self.assertEqual([(a["name"], a["phases"]) for a in unknown["agents"]],
                         [(a["name"], a["phases"]) for a in experimental["agents"]])


class PageTests(unittest.TestCase):
    def test_the_page_shows_the_notice_and_applies_the_board_kind(self) -> None:
        body = PAGE[PAGE.index("function applyPaperKind"):PAGE.index("function navigateTab")]
        self.assertIn("board_kind", body)
        self.assertNotIn("kind === 'review' ? 'review' : 'experimental'", body)
        self.assertIn("board_notice", PAGE)
        self.assertIn("'board.noBoard'", PAGE)
        for name in ("en.js", "es.js"):
            with self.subTest(catalogue=name):
                self.assertIn('"board.noBoard":', (STATIC / "i18n" / name).read_text(encoding="utf-8"))

    def test_the_agents_table_filters_under_any_line_but_the_experimental(self) -> None:
        source = (STATIC / "agents-panel.js").read_text(encoding="utf-8")
        self.assertNotIn("view.paper_kind === 'review'", source)
        node = shutil.which("node", path="/usr/bin") or shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        script = r"""
const fs = require('fs');
const vm = require('vm');
const host = { innerHTML: '', querySelectorAll: () => [] };
const ctx = { window: { i18n: { t: (key) => key } }, document: { getElementById: () => host, addEventListener() {} }, console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const agents = [{ name: 'with-step', phases: ['Phase 1 — X'] }, { name: 'without-step', phases: [] }];
const out = {};
for (const kind of [null, 'experimental', 'review', 'some-line']) {
  const view = kind ? { agents, warnings: [], paper_kind: kind } : { agents, warnings: [] };
  ctx.window.AgentsPanel.render(view);
  out[String(kind)] = [...host.innerHTML.matchAll(/<tr><td><code>([^<]+)<\/code>/g)].map((m) => m[1]).sort();
}
process.stdout.write(JSON.stringify(out));
"""
        result = subprocess.run([node, "-e", script, str(STATIC / "agents-panel.js")], capture_output=True,
                                text=True, timeout=60, check=True)
        shown = json.loads(result.stdout)
        both, filtered = ["with-step", "without-step"], ["with-step"]
        self.assertEqual(shown, {"null": both, "experimental": both, "review": filtered, "some-line": filtered})


if __name__ == "__main__":
    unittest.main()
