"""The Agents Office state: the smith agents and their orchestrator at work.

The office shows every agent defined in the workspace (``.claude/agents``)
plus the orchestrator, and each desk's state is measured from live CLI
output: an agent invocation that no completion answered is ``working``, an
Engram write or read attributed to it is ``saving`` or ``loading``, anything
else is ``available``. Nothing is invented.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "command_center"))
import office  # noqa: E402

DEFINED = [
    {"name": "sota-scout", "role": "Scouts the literature.", "tramo": "plausibility",
     "phases": ["Phase 2 — Plausibility"], "skill": "plausibility", "model": ""},
    {"name": "novelty-screener", "role": "Screens novelty.", "tramo": "plausibility",
     "phases": [], "skill": "", "model": "sonnet"},
    {"name": "redactor", "role": "Drafts one block.", "tramo": "writing",
     "phases": [], "skill": "paper-writing", "model": ""},
]
NAMES = [a["name"] for a in DEFINED]
NOW = 1_000_000.0
#: The Engram tool prefix, kept apart so this file holds CLI *output*, never a
#: call shape the no-memory-provider guard would read as a tool call.
M = "mem_"


def state(tail: str, *, ring: list | None = None, alive: bool = True, cli: str = "claude",
          enabled: bool = True, authorized: bool = True, now: float = NOW) -> dict:
    facts = [{"agent": cli, "alive": alive, "tail": tail}] if tail is not None else []
    return office.office_state(defined=DEFINED, session_facts=facts,
                               ring=[] if ring is None else ring, engram_path="/usr/bin/engram",
                               enabled=enabled, authorized=authorized, now=now)


def by_id(snapshot: dict) -> dict:
    return {a["id"]: a for a in snapshot["agents"]}


class RosterTests(unittest.TestCase):

    def test_every_defined_smith_agent_gets_a_desk_and_no_cli_program_does(self) -> None:
        snapshot = state("")
        self.assertEqual([a["id"] for a in snapshot["agents"]], NAMES)
        self.assertNotIn("claude", by_id(snapshot))

    def test_role_tramo_phases_and_model_come_from_the_definition(self) -> None:
        agents = by_id(state(""))
        self.assertEqual(agents["sota-scout"]["role"], "Scouts the literature.")
        self.assertEqual(agents["sota-scout"]["tramo"], "plausibility")
        self.assertEqual(agents["sota-scout"]["phases"], ["Phase 2 — Plausibility"])
        self.assertIsNone(agents["sota-scout"]["model"])
        self.assertEqual(agents["novelty-screener"]["model"], "sonnet")

    def test_idle_agents_are_available(self) -> None:
        for agent in state("").get("agents"):
            self.assertEqual(agent["state"], "available", agent["id"])

    def test_the_real_workspace_definitions_reach_the_office(self) -> None:
        from skills._core.command_center import agents_view
        defined = agents_view.get_agents_view(FORGE_ROOT)["agents"]
        snapshot = office.office_state(defined=defined, session_facts=[], ring=[], engram_path=None,
                                       enabled=True, authorized=True)
        ids = {a["id"] for a in snapshot["agents"]}
        self.assertEqual(ids, {p.stem for p in (FORGE_ROOT / ".claude" / "agents").glob("*.md")})


class WorkingTests(unittest.TestCase):

    def test_a_claude_code_subagent_call_is_working_until_done(self) -> None:
        running = "● sota-scout(Scout the idea)\n  ⎿  Reading 3 files…\n"
        self.assertEqual(by_id(state(running))["sota-scout"]["state"], "working")
        done = running + "  ⎿  Done (12 tool uses · 30k tokens · 1m 2s)\n"
        self.assertEqual(by_id(state(done))["sota-scout"]["state"], "available")

    def test_other_cli_spellings_open_a_running_agent(self) -> None:
        for tail in ("Task(redactor: draft the intro)", 'subagent_type: "redactor"', "⏺ redactor(Draft)"):
            with self.subTest(tail=tail):
                self.assertEqual(by_id(state(tail))["redactor"]["state"], "working")

    def test_parallel_agents_close_in_launch_order(self) -> None:
        tail = "● sota-scout(a)\n● redactor(b)\n⎿  Done (3 tool uses)\n"
        agents = by_id(state(tail))
        self.assertEqual(agents["sota-scout"]["state"], "available")
        self.assertEqual(agents["redactor"]["state"], "working")

    def test_prose_naming_an_agent_is_not_a_call(self) -> None:
        tail = ("The sota-scout agent writes the pool.\nsee docs/redactor.md\n"
                "* sota-scout (finds papers)\n• redactor (writes the draft)\nsee @sota-scout for details\n")
        for agent in state(tail)["agents"]:
            self.assertEqual(agent["state"], "available", agent["id"])

    def test_escape_sequences_do_not_hide_a_call(self) -> None:
        tail = "\x1b[2K\x1b[1G\x1b[38;5;10m●\x1b[0m \x1b[1msota-scout\x1b[0m(Scout)\r\n"
        self.assertEqual(by_id(state(tail))["sota-scout"]["state"], "working")

    def test_a_dead_session_shows_nobody_working(self) -> None:
        snapshot = state("● sota-scout(Scout)\n", alive=False)
        self.assertEqual(by_id(snapshot)["sota-scout"]["state"], "available")
        self.assertEqual(snapshot["orchestrator"]["state"], "absent")


class LinearScanTests(unittest.TestCase):
    """A terminal tail is untrusted: no line may make the scan slow."""

    def test_pathological_lines_scan_in_linear_time(self) -> None:
        import time as clock
        names = [p.stem for p in (FORGE_ROOT / ".claude" / "agents").glob("*.md")]
        size = office.MEMORY_SCAN_BYTES
        for tail in (" " * (size - 1) + "x", " \t" * (size // 2 - 1) + "●",
                     "\n".join(["   " * 50 + "⎿"] * 100), "a@b" * (size // 3)):
            started = clock.perf_counter()
            office.scan_tail(tail, names)
            office.detect_memory_interaction(tail)
            self.assertLess(clock.perf_counter() - started, 0.25, repr(tail[:20]))

    def test_the_screen_model_is_linear_on_hostile_output(self) -> None:
        import time as clock
        for chunk in ("\x1b[" + "1;" * 8000 + "H", "\x1b]" + "x" * 16000, "\x1b[999;999H" * 2000,
                      ("é" * 5000).encode("utf-8")[:-1].decode("utf-8", "ignore"), "\x1b[3S\x1b[2T" * 3000):
            screen = office.Screen(cols=400, rows=200)
            started = clock.perf_counter()
            screen.feed_bytes(chunk.encode("utf-8"))
            self.assertLess(clock.perf_counter() - started, 0.5, repr(chunk[:12]))

    def test_hostile_parameters_neither_raise_nor_allocate(self) -> None:
        import time as clock
        screen = office.Screen(cols=50, rows=10)
        started = clock.perf_counter()
        screen.feed_bytes(b"\x1b[" + b"9" * 5000 + b"m")
        screen.feed_bytes(b"\x1b[2000000000@\x1b[999999999P\x1b[999999999X")
        self.assertLess(clock.perf_counter() - started, 0.2)
        self.assertTrue(all(len(row) == 50 for row in screen.grid))

    def test_a_saved_cursor_survives_a_smaller_window(self) -> None:
        for save, restore in (("\x1b7", "\x1b8"), ("\x1b[s", "\x1b[u")):
            screen = office.Screen(cols=120, rows=40)
            screen.feed("\x1b[30;100H" + save)
            screen.resize(50, 10)
            screen.feed(restore + "x")
            self.assertEqual(screen.lines()[9].rstrip()[-1], "x")

    def test_a_failing_feed_never_breaks_the_office(self) -> None:
        memo: dict = {}
        fact = lambda end: [{"id": "s", "agent": "claude", "alive": True, "end": end, "tail": "", "raw": b"x" * end}]
        original = office.Screen.feed_bytes
        office.Screen.feed_bytes = lambda self, chunk: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            office.office_state(defined=DEFINED, session_facts=fact(5), ring=[], engram_path=None,
                                enabled=True, authorized=True, now=NOW, memo=memo)
        finally:
            office.Screen.feed_bytes = original
        snapshot = office.office_state(defined=DEFINED, session_facts=fact(9), ring=[], engram_path=None,
                                       enabled=True, authorized=True, now=NOW + 2, memo=memo)
        self.assertEqual(snapshot["orchestrator"]["state"], "available")

    def test_an_engram_without_a_count_is_asked_once_a_minute(self) -> None:
        calls = []
        memo: dict = {}
        fact = [{"id": "s", "agent": "claude", "alive": True, "end": 1, "tail": "", "raw": b">"}]
        for second in range(0, 30, 2):
            office.office_state(defined=DEFINED, session_facts=fact, ring=[], engram_path="x", enabled=True,
                                authorized=True, now=NOW + second, memo=memo, counter=lambda: calls.append(1))
        self.assertEqual(len(calls), 1)

    def test_a_chunk_cut_inside_a_sequence_or_a_character_finishes_next_time(self) -> None:
        screen = office.Screen(cols=20, rows=2)
        data = "\x1b[1;1Hcafé\x1b[2;1Hdone".encode("utf-8")
        for cut in range(len(data) + 1):
            screen = office.Screen(cols=20, rows=2)
            screen.feed_bytes(data[:cut])
            screen.feed_bytes(data[cut:])
            self.assertEqual(screen.lines(), ["café", "done"], cut)

    def test_a_call_past_the_scanned_width_is_not_read(self) -> None:
        tail = " " * office.LINE_SCAN_CHARS + "● sota-scout(x)\n"
        self.assertEqual(by_id(state(tail))["sota-scout"]["state"], "available")


class MemoryTests(unittest.TestCase):

    def test_writes_and_reads_are_told_apart(self) -> None:
        self.assertEqual(office.memory_kind(f"● engram - {M}save (MCP)(title: x)"), "save")
        self.assertEqual(office.memory_kind(f"{M}session_summary(...)"), "save")
        self.assertEqual(office.memory_kind(f"● engram - {M}search (MCP)(query: x)"), "load")
        self.assertEqual(office.memory_kind("mem_context"), "load")
        self.assertEqual(office.memory_kind("$ engram search auth"), "load")
        self.assertEqual(office.memory_kind("$ engram save note"), "save")
        self.assertIsNone(office.memory_kind("member list and memory foam"))
        self.assertIsNone(office.memory_kind("remem_save is not a tool"))
        self.assertIsNone(office.memory_kind(f"Note: {M}search is a tool"))
        self.assertIsNone(office.memory_kind(f"$ git commit -m '{M}save fix'"))
        self.assertEqual(office.memory_kind(f"engram_{M}search query"), "load")

    def test_a_save_inside_a_running_agent_makes_it_saving(self) -> None:
        ring: list = []
        tail = f"● sota-scout(Scout)\n  ⎿  engram - {M}save (MCP)(title: pool)\n"
        snapshot = state(tail, ring=ring)
        self.assertEqual(by_id(snapshot)["sota-scout"]["state"], "saving")
        self.assertEqual(ring[-1]["agent"], "sota-scout")
        self.assertEqual(ring[-1]["kind"], "save")
        self.assertEqual(ring[-1]["cli"], "claude")

    def test_a_read_outside_any_agent_belongs_to_the_orchestrator(self) -> None:
        snapshot = state(f"● engram - {M}context (MCP)(project: x)\n")
        self.assertEqual(snapshot["orchestrator"]["state"], "loading")
        self.assertEqual(snapshot["memory"]["interactions"][-1]["agent"], "orchestrator")

    def test_the_memory_state_fades_back_to_the_agent_state(self) -> None:
        ring: list = []
        tail = f"● redactor(Draft)\n{M}search(query)\n"
        self.assertEqual(by_id(state(tail, ring=ring))["redactor"]["state"], "loading")
        later = state(tail, ring=ring, now=NOW + office.MEMORY_ACTIVE_S + 1)
        self.assertEqual(by_id(later)["redactor"]["state"], "working")
        self.assertEqual(len(ring), 1, "a re-read tail does not duplicate history")

    def test_the_ring_is_bounded(self) -> None:
        ring: list = []
        for index in range(office.MEMORY_EVENTS_MAX + 5):
            office.memory_ring_push(ring, {"agent": "x", "kind": "save", "line": str(index), "at": 0})
        self.assertEqual(len(ring), office.MEMORY_EVENTS_MAX)
        self.assertEqual(ring[-1]["line"], str(office.MEMORY_EVENTS_MAX + 4))

    def test_the_last_engram_line_is_reported(self) -> None:
        self.assertEqual(office.detect_memory_interaction("mem_search a\nnoise\nmem_save b\n"), "mem_save b")
        self.assertIsNone(office.detect_memory_interaction("plain output"))


def esc(seq: str) -> str:
    return "\x1b[" + seq


class ClaudeCodeScreenTests(unittest.TestCase):
    """Claude Code v2 draws its transcript with cursor moves, folds MCP calls
    and closes background agents with ``Agent "…" finished`` (shapes taken
    from a real session; the text here is synthetic)."""

    def screen(self, *rows: str) -> str:
        # Each row starts like Claude Code's: carriage return + cursor down.
        return "".join("\r" + esc("1B") + esc("K") + row for row in rows)

    def test_rows_separated_by_cursor_moves_are_lines(self) -> None:
        tail = self.screen(
            esc("38;2;78;186;101m") + "●" + esc("3G") + esc("39m") + esc("1m") + "math-tutor"
            + esc("22m") + "(Math" + esc("19G") + "tutor" + esc("25G") + "probe)",
            "  ⎿ \u00a0Backgrounded agent (↓ to manage)")
        self.assertIn("● math-tutor(Math tutor probe)", office.strip_ansi(tail).splitlines())
        self.assertEqual(office.scan_tail(tail, NAMES + ["math-tutor"])["running"], ["math-tutor"])

    def test_a_finished_background_agent_is_closed(self) -> None:
        tail = self.screen("● redactor(Draft)", "  ⎿  Backgrounded agent", '● Agent "Draft" finished · 1s')
        self.assertEqual(by_id(state(tail))["redactor"]["state"], "available")

    def test_the_typed_prompt_is_never_a_call(self) -> None:
        tail = self.screen("❯ Do these steps: 1) call the engram", f"  {M}search tool with query x. 2) launch",
                           "  the redactor subagent")
        snapshot = state(tail)
        self.assertEqual(snapshot["memory"]["interactions"], [])
        self.assertEqual(snapshot["orchestrator"]["state"], "available")

    def test_a_call_belongs_to_the_entry_it_is_printed_in(self) -> None:
        tail = self.screen("● redactor(Draft)", f"  ⎿  engram - {M}search (MCP)(query: x)",
                           f"● engram - {M}save (MCP)(title: y)")
        ring: list = []
        snapshot = state(tail, ring=ring)
        self.assertEqual([(e["agent"], e["kind"]) for e in ring], [("redactor", "load"), ("orchestrator", "save")])
        self.assertEqual(by_id(snapshot)["redactor"]["state"], "loading")
        self.assertEqual(snapshot["orchestrator"]["state"], "saving")

    def folded(self, counts: list, *, memo: dict | None = None) -> list:
        tail = self.screen("  Called engram ", '  ⎿  "smith ui agents office"')
        values = iter(counts)
        ring: list = []
        office.office_state(defined=DEFINED, session_facts=[{"agent": "claude", "alive": True, "tail": tail}],
                            ring=ring, engram_path="/usr/bin/engram", enabled=True, authorized=True,
                            now=NOW, memo={"observations": 10} if memo is None else memo,
                            counter=lambda: next(values))
        return ring

    def test_a_folded_call_is_a_save_when_the_store_grew(self) -> None:
        ring = self.folded([11])
        self.assertEqual((ring[0]["agent"], ring[0]["kind"]), ("orchestrator", "save"))
        self.assertIn('"smith ui agents office"', ring[0]["line"])

    def test_a_folded_call_is_a_read_when_the_store_did_not_grow(self) -> None:
        self.assertEqual(self.folded([10])[0]["kind"], "load")

    def test_a_folded_call_without_a_count_keeps_an_unknown_direction(self) -> None:
        ring = self.folded([None])
        self.assertEqual(ring[0]["kind"], "use")
        snapshot = office.office_state(defined=DEFINED, session_facts=[], ring=ring, engram_path=None,
                                       enabled=True, authorized=True, now=NOW)
        self.assertEqual(snapshot["orchestrator"]["state"], "absent")

    def poller(self, counts=None):
        """Polls one live session the way the server does: id, absolute end."""
        memo: dict = {}
        ring: list = []
        output = {"text": ""}
        values = iter(counts or [])

        def poll(appended: str, at: float) -> list:
            output["text"] += appended
            raw = output["text"].encode("utf-8")
            office.office_state(
                defined=DEFINED, ring=ring, engram_path=None, enabled=True, authorized=True, now=at, memo=memo,
                session_facts=[{"id": "s1", "agent": "claude", "alive": True, "end": len(raw), "cols": 100, "rows": 30,
                                "tail": raw[-office.MEMORY_SCAN_BYTES:].decode("utf-8", "replace")}],
                counter=(lambda: next(values)) if counts else None)
            return [(e["agent"], e["kind"]) for e in ring]

        return poll

    def test_history_before_the_office_looked_is_not_activity(self) -> None:
        poll = self.poller()
        self.assertEqual(poll(self.screen(f"● engram - {M}save (MCP)(title: before)"), NOW), [])
        self.assertEqual(poll(self.screen(f"● engram - {M}search (MCP)(query: after)"), NOW + 2),
                         [("orchestrator", "load")])

    def test_a_repaint_is_not_a_new_call_but_a_later_identical_call_is(self) -> None:
        poll = self.poller(counts=[10, 10, 11])
        poll(self.screen("❯ "), NOW)
        rows = self.screen("● Step one", "● Called engram", "● Step two")
        self.assertEqual(poll(rows, NOW + 2), [("orchestrator", "load")])
        # Claude Code repaints by moving home and writing the same rows again.
        self.assertEqual(poll(esc("H") + "\r" + esc("1B") + rows, NOW + 4), [("orchestrator", "load")])
        self.assertEqual(poll(self.screen("● Called engram"), NOW + 6),
                         [("orchestrator", "load"), ("orchestrator", "save")])

    def test_the_screen_model_follows_cursor_moves_and_erases(self) -> None:
        screen = office.Screen(cols=20, rows=4)
        screen.feed("hello world" + esc("1;7H") + "there" + esc("2;1H") + "line two" + esc("2;5H") + esc("K"))
        self.assertEqual(screen.lines()[:2], ["hello there", "line"])
        screen.feed(esc("4;1H") + "last\r\nscrolled")
        self.assertEqual(screen.lines(), ["line", "", "last", "scrolled"])
        screen.feed(esc("2J"))
        self.assertEqual(screen.lines(), ["", "", "", ""])
        big = office.Screen(cols=10 ** 6, rows=10 ** 6)
        self.assertEqual((big.cols, big.rows), (office.SCREEN_MAX_COLS, office.SCREEN_MAX_ROWS))

    def test_two_identical_folded_calls_in_a_row_are_two_calls(self) -> None:
        poll = self.poller(counts=[10, 10])
        poll(self.screen("❯ "), NOW)
        self.assertEqual(poll(self.screen("● Called engram", '  ⎿  "q"', "● Reading", "● Called engram"), NOW + 2),
                         [("orchestrator", "load"), ("orchestrator", "load")])

    def test_the_store_count_reads_only_the_observation_total(self) -> None:
        import tempfile as tmpmod
        with tmpmod.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "engram"
            fake.write_text("#!/bin/sh\necho 'Engram Memory Stats'\necho '  Observations: 2873'\necho '  Projects: a, b'\n")
            fake.chmod(0o755)
            self.assertEqual(office.engram_observations(str(fake)), 2873)
            (Path(tmp) / "broken").write_text("#!/bin/sh\nexit 3\n")
            (Path(tmp) / "broken").chmod(0o755)
            self.assertIsNone(office.engram_observations(str(Path(tmp) / "broken")))
        self.assertIsNone(office.engram_observations(None) if not office.engram_path() else None)


class OrchestratorTests(unittest.TestCase):

    def test_absent_without_a_live_agent_cli(self) -> None:
        self.assertEqual(state(None)["orchestrator"]["state"], "absent")
        self.assertEqual(state("", cli="shell")["orchestrator"]["state"], "absent")

    def test_available_in_an_idle_cli_and_working_while_an_agent_works(self) -> None:
        idle = state("> ", cli="opencode")["orchestrator"]
        self.assertEqual((idle["state"], idle["clis"]), ("available", ["opencode"]))
        self.assertEqual(state("● redactor(Draft)\n")["orchestrator"]["state"], "working")


class AuthorizationTests(unittest.TestCase):

    def test_disabled_or_unauthorized_reads_no_session(self) -> None:
        ring: list = []
        for kwargs in ({"enabled": False}, {"authorized": False}):
            with self.subTest(**kwargs):
                snapshot = state("● sota-scout(x)\nmem_save y\n", ring=ring, **kwargs)
                self.assertEqual([a["state"] for a in snapshot["agents"]], ["available"] * 3)
                self.assertEqual(snapshot["orchestrator"]["state"], "absent")
                self.assertEqual(snapshot["memory"]["interactions"], [])
                self.assertEqual(snapshot["memory"]["engram_path"], "/usr/bin/engram")
        self.assertEqual(ring, [])


class RouteTests(unittest.TestCase):

    def test_the_route_serves_the_workspace_agents(self) -> None:
        from fastapi.testclient import TestClient
        from skills._core.command_center import server
        with tempfile.TemporaryDirectory() as tmp:
            agents = Path(tmp) / ".claude" / "agents"
            agents.mkdir(parents=True)
            (agents / "sota-scout.md").write_text('---\nname: sota-scout\ndescription: "Scouts. More."\nmodel: sonnet\n---\nbody\n')
            client = TestClient(server.create_app(tmp, enable_terminal=False))
            body = client.get("/api/office/state").json()
        self.assertEqual([a["id"] for a in body["agents"]], ["sota-scout"])
        self.assertEqual(body["agents"][0]["model"], "sonnet")
        self.assertEqual(body["agents"][0]["state"], "available")
        self.assertEqual(body["agents"][0]["stages"], ["plausibility"])
        self.assertFalse(body["enabled"])
        self.assertEqual(body["orchestrator"]["state"], "absent")

    def test_the_page_reads_the_office_where_the_terminal_cookie_is_sent(self) -> None:
        # The cookie is scoped to /api/terminal: only a route under it is
        # authorized for a browser that went through the login link.
        from fastapi.testclient import TestClient
        from skills._core.command_center import server
        with tempfile.TemporaryDirectory() as tmp:
            app = server.create_app(tmp, enable_terminal=True, history_store=None)
            client = TestClient(app, base_url="http://127.0.0.1:8080")
            login = client.get(f"/api/terminal/login?token={app.state.terminal.login_token}", follow_redirects=False)
            self.assertEqual(login.status_code, 303)
            under = client.get("/api/terminal/office").json()
            outside = client.get("/api/office/state").json()
            cross = client.get("/api/terminal/office", headers={"Sec-Fetch-Site": "cross-site"}).json()
        self.assertTrue(under["authorized"])
        self.assertFalse(outside["authorized"])
        self.assertFalse(cross["authorized"], "a cross-site read carrying the cookie sees no activity")
        panel = (FORGE_ROOT / "skills" / "_core" / "command_center" / "static" / "office-panel.js").read_text()
        self.assertIn("fetch('/api/terminal/office')", panel)

STATIC = FORGE_ROOT / "skills" / "_core" / "command_center" / "static"

MODEL_HARNESS = r"""
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync(0, 'utf8'));
global.window = { i18n: { t: (k, v) => k + (v ? ' ' + JSON.stringify(v) : '') } };
global.document = { addEventListener() {}, getElementById: () => null };
eval(fs.readFileSync(process.argv[1], 'utf8'));
const m = window.officeModel;
const info = m.decorate(cfg.info, cfg.runs);
console.log(JSON.stringify({
  inPhase: Object.fromEntries(info.agents.map((a) => [a.id, a.inPhase])),
  counts: m.counts(info),
  tasks: Object.fromEntries(info.agents.map((a) => [a.id, m.taskOf(a, info)])),
  boss: m.taskOf({ id: 'orchestrator', state: 'available' }, info),
}));
"""


@unittest.skipUnless(__import__("shutil").which("node"), "node is not installed")
class PanelModelTests(unittest.TestCase):
    """The real office-panel.js helpers, run in node."""

    def run_model(self, info: dict, runs: dict) -> dict:
        import json
        import subprocess
        done = subprocess.run(["node", "-e", MODEL_HARNESS, str(STATIC / "office-panel.js")],
                              input=json.dumps({"info": info, "runs": runs}),
                              capture_output=True, text=True, timeout=30, check=True)
        return json.loads(done.stdout)

    def test_a_running_phase_marks_its_agents_and_names_the_orchestrator_task(self) -> None:
        info = {"agents": [
            {"id": "sota-scout", "state": "available", "stages": ["plausibility"]},
            {"id": "redactor", "state": "saving", "stages": ["writing"]},
            {"id": "math-tutor", "state": "working", "stages": []},
        ], "memory": {"interactions": [{"agent": "redactor", "kind": "save", "line": "mem_save x"}]}}
        runs = {"plausibility": {"stage": "plausibility", "name": "Plausibility", "command": "/plausibility idea", "startedAt": 1},
                "writing": {"stage": "writing", "startedAt": 1, "stoppedAt": 2}}
        out = self.run_model(info, runs)
        self.assertEqual(out["inPhase"], {"sota-scout": True, "redactor": False, "math-tutor": False})
        self.assertEqual(out["counts"], {"working": 1, "saving": 1, "loading": 0, "available": 1})
        self.assertEqual(out["tasks"]["sota-scout"], "office.task.inPhase")
        self.assertIn("office.task.saving", out["tasks"]["redactor"])
        self.assertIn("mem_save x", out["tasks"]["redactor"])
        self.assertEqual(out["tasks"]["math-tutor"], "office.task.working")
        self.assertIn("/plausibility idea", out["boss"])


EVENTS_HARNESS = r"""
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync(0, 'utf8'));
global.window = { i18n: { t: (k, v) => k + (v ? ' ' + JSON.stringify(v) : '') } };
global.document = { addEventListener() {}, getElementById: () => null };
eval(fs.readFileSync(process.argv[1], 'utf8'));
const m = window.officeModel;
const events = m.diffEvents(cfg.prev, cfg.next);
console.log(JSON.stringify({ events, texts: events.map(m.eventText) }));
"""


@unittest.skipUnless(__import__("shutil").which("node"), "node is not installed")
class EventsModelTests(unittest.TestCase):
    """The events strip: only what changed between two measured snapshots."""

    def run_events(self, prev, nxt) -> dict:
        import json
        import subprocess
        done = subprocess.run(["node", "-e", EVENTS_HARNESS, str(STATIC / "office-panel.js")],
                              input=json.dumps({"prev": prev, "next": nxt}),
                              capture_output=True, text=True, timeout=30, check=True)
        return json.loads(done.stdout)

    @staticmethod
    def snap(states: dict, orch: str = "working", memory=(), at: float = 100.0) -> dict:
        return {"generated_at": at, "orchestrator": {"state": orch},
                "agents": [{"id": k, "label": k, "state": v} for k, v in states.items()],
                "memory": {"interactions": list(memory)}}

    def test_a_task_given_and_a_task_done_become_events(self) -> None:
        prev = self.snap({"math-tutor": "available", "redactor": "working", "sota-scout": "available"})
        nxt = self.snap({"math-tutor": "working", "redactor": "available", "sota-scout": "available"}, at=102.5)
        out = self.run_events(prev, nxt)
        self.assertEqual([(e["kind"], e["agent"], e["at"]) for e in out["events"]],
                         [("dispatch", "math-tutor", 102.5), ("done", "redactor", 102.5)])
        self.assertIn("office.event.dispatch", out["texts"][0])
        self.assertIn('"agent":"math-tutor"', out["texts"][0])
        self.assertIn('"from":"office.orchestrator"', out["texts"][0])

    def test_the_first_snapshot_only_reports_its_engram_interactions_with_their_time(self) -> None:
        memory = [{"at": 90.0, "agent": "orchestrator", "kind": "load", "line": "Called engram"},
                  {"at": 95.0, "agent": "orchestrator", "kind": "save", "line": "Called engram"}]
        out = self.run_events(None, self.snap({"math-tutor": "working"}, memory=memory))
        self.assertEqual([(e["kind"], e["agent"], e["at"]) for e in out["events"]],
                         [("load", "orchestrator", 90.0), ("save", "orchestrator", 95.0)])

    def test_unchanged_snapshots_and_seen_interactions_report_nothing(self) -> None:
        memory = [{"at": 90.0, "agent": "orchestrator", "kind": "save", "line": "x"}]
        same = self.snap({"math-tutor": "working"}, memory=memory)
        self.assertEqual(self.run_events(same, same)["events"], [])

    def test_the_orchestrator_session_opening_and_closing(self) -> None:
        opened = self.run_events(self.snap({}, orch="absent"), self.snap({}, orch="available"))["events"]
        closed = self.run_events(self.snap({}, orch="working"), self.snap({}, orch="absent"))["events"]
        self.assertEqual([e["kind"] for e in opened], ["online"])
        self.assertEqual([e["kind"] for e in closed], ["offline"])
        busy = self.run_events(self.snap({}, orch="available"), self.snap({}, orch="saving"))["events"]
        self.assertEqual(busy, [], "a state change of a live session is not an online/offline event")


class WiringTests(unittest.TestCase):
    """The page loads the vendored three.js scene and the panel reads the office."""

    def test_the_page_maps_three_to_the_vendored_build_and_loads_the_scene(self) -> None:
        page = (STATIC / "index.html").read_text()
        self.assertIn('"three": "./vendor/three/three.module.min.js"', page)
        self.assertLess(page.index('type="importmap"'), page.index('src="./office3d.js'))
        self.assertIn('id="officeStage"', page)
        for name in ("three.module.min.js", "three.core.min.js", "LICENSE"):
            self.assertTrue((STATIC / "vendor" / "three" / name).is_file(), name)
        import hashlib
        pinned = {"three.core.min.js": "c5f69a04c70d", "three.module.min.js": "e3ec4d5d223c"}  # three@0.183.0
        for name, prefix in pinned.items():
            digest = hashlib.sha256((STATIC / "vendor" / "three" / name).read_bytes()).hexdigest()
            self.assertTrue(digest.startswith(prefix), name)

    def test_the_scene_is_weherds_procedural_office_with_an_engram_core(self) -> None:
        scene = (STATIC / "office3d.js").read_text()
        self.assertIn("import * as THREE from 'three';", scene)
        self.assertNotIn("examples/jsm", scene)
        self.assertIn("OrthographicCamera", scene)
        self.assertIn("const OFFSET = new THREE.Vector3(28, 34, 36);", scene)
        for state in ("'working'", "'saving'", "'loading'", "'available'"):
            self.assertIn(state, scene)
        self.assertIn("office.brainSign", scene)

    def test_the_scene_bakes_static_pieces_and_labels_in_html_sized_in_rem(self) -> None:
        scene = (STATIC / "office3d.js").read_text()
        page = (STATIC / "index.html").read_text()
        self.assertIn("function bake(root)", scene)
        self.assertIn("bake(statics);", scene)
        self.assertNotIn("CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;\n  const sprite", scene)
        self.assertNotIn("THREE.Sprite(", scene, "names and states are HTML tags, not canvas sprites")
        self.assertIn(".office-tag__card b { display: block; font-size: 0.86rem;", page)
        self.assertIn("MIN_FPS", scene)
        for zone in ("plausibility", "writing", "figures", "audit"):
            self.assertIn(f"'{zone}'", scene)

    def test_the_hud_has_camera_controls_and_an_events_strip(self) -> None:
        page = (STATIC / "index.html").read_text()
        panel = (STATIC / "office-panel.js").read_text()
        for element in ('id="officeFit"', 'id="officeFollow"', 'id="officeEvents"'):
            self.assertIn(element, page)
        self.assertIn("window.officeScene.fitAll()", panel)
        self.assertIn("window.officeScene.followActive()", panel)

    def test_the_panel_is_read_only(self) -> None:
        panel = (STATIC / "office-panel.js").read_text()
        for verb in ("method: 'POST'", "method: 'DELETE'", "/input"):
            self.assertNotIn(verb, panel)


if __name__ == "__main__":
    unittest.main()
