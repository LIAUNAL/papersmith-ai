"""Watcher ignore rules and the thread-safe event bus."""

from __future__ import annotations

import asyncio
import tempfile
import threading
import time
import unittest
from pathlib import Path

from skills._core.command_center import watcher


class IgnoreRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()

    def test_git_and_virtualenv_are_ignored(self) -> None:
        assert watcher.is_ignored(self.root / ".git" / "HEAD", self.root)
        assert watcher.is_ignored(self.root / ".venv" / "lib" / "x.py", self.root)
        assert watcher.is_ignored(self.root / "node_modules" / "pkg" / "i.js", self.root)

    def test_latex_compilation_artifacts_are_ignored(self) -> None:
        for name in ("main.aux", "main.log", "main.fls", "main.synctex.gz", "main.fdb_latexmk"):
            assert watcher.is_ignored(self.root / "paper" / name, self.root), name

    def test_a_real_section_edit_is_not_ignored(self) -> None:
        assert not watcher.is_ignored(self.root / "sections" / "01-materials-and-methods.md", self.root)
        assert not watcher.is_ignored(self.root / "papersmith.yaml", self.root)

    def test_health_paths_are_classified(self) -> None:
        assert watcher.is_health_path(self.root / "skills" / "paper-writing" / "SKILL.md", self.root)
        assert watcher.is_health_path(self.root / ".claude" / "agents" / "redactor.md", self.root)
        assert not watcher.is_health_path(self.root / "sections" / "01-x.md", self.root)


class EventBusTests(unittest.TestCase):
    def test_publish_reaches_a_subscriber(self) -> None:
        async def scenario() -> dict:
            bus = watcher.EventBus()
            bus.bind_loop(asyncio.get_running_loop())
            queue = bus.subscribe()
            bus.publish("state_update", {"revision": 1})
            return await asyncio.wait_for(queue.get(), timeout=1.0)

        message = asyncio.run(scenario())
        assert message == {"event": "state_update", "data": {"revision": 1}}

    def test_unsubscribed_queues_stop_receiving(self) -> None:
        async def scenario() -> int:
            bus = watcher.EventBus()
            bus.bind_loop(asyncio.get_running_loop())
            queue = bus.subscribe()
            bus.unsubscribe(queue)
            bus.publish("state_update", {})
            await asyncio.sleep(0.05)
            return bus.subscriber_count()

        assert asyncio.run(scenario()) == 0

    def test_publish_from_another_thread_is_delivered(self) -> None:
        async def scenario() -> dict:
            bus = watcher.EventBus()
            bus.bind_loop(asyncio.get_running_loop())
            queue = bus.subscribe()
            thread = threading.Thread(target=bus.publish, args=("health_update", {"ok": True}))
            thread.start()
            thread.join()
            return await asyncio.wait_for(queue.get(), timeout=1.0)

        message = asyncio.run(scenario())
        assert message["event"] == "health_update"

    def test_publish_without_a_bound_loop_is_a_noop(self) -> None:
        bus = watcher.EventBus()
        bus.publish("state_update", {"x": 1})  # must not raise


class WorkspaceWatcherTests(unittest.TestCase):
    def test_watch_paths_are_only_the_existing_targets(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        (root / "sections").mkdir()
        (root / "papersmith.yaml").write_text("name: x\n", encoding="utf-8")

        workspace_watcher = watcher.WorkspaceWatcher(root, lambda paths: None)
        names = {path.name for path in workspace_watcher.watch_paths()}

        assert names == {"sections", "papersmith.yaml"}

    def test_watch_paths_cover_the_sota_pool(self) -> None:
        """The atlas and its manuscript layer live in `sota-pool/`: a rebuilt
        layer must wake the dashboard."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        (root / "sota-pool").mkdir()

        workspace_watcher = watcher.WorkspaceWatcher(root, lambda paths: None)

        assert "sota-pool" in watcher.WATCH_TARGETS
        assert workspace_watcher.watch_paths() == [root / "sota-pool"]
        assert not watcher.is_ignored(root / "sota-pool" / "atlas.manuscript.json", root)

    def test_watch_paths_fall_back_to_the_root(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()

        workspace_watcher = watcher.WorkspaceWatcher(root, lambda paths: None)

        assert workspace_watcher.watch_paths() == [root]

    def test_watch_paths_include_health_surfaces(self) -> None:
        """Harness dirs and skill manifests are watched so the health branch of
        the flush callback is reachable at all."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        (root / "sections").mkdir()
        (root / "papersmith.yaml").write_text("name: x\n", encoding="utf-8")
        (root / ".claude" / "agents").mkdir(parents=True)
        skill = root / "skills" / "paper-writing"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# paper-writing\n", encoding="utf-8")

        paths = watcher.WorkspaceWatcher(root, lambda paths: None).watch_paths()

        assert (root / ".claude" / "agents") in paths
        assert (skill / "SKILL.md") in paths
        assert root / "paper" not in paths  # absent, so never watched

    def test_stop_is_idempotent(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        workspace_watcher = watcher.WorkspaceWatcher(root, lambda paths: None)

        workspace_watcher.stop()
        workspace_watcher.stop()


class LiveRefreshTests(unittest.TestCase):
    """The board refreshes by itself: every directory that carries a phase's
    evidence is watched, including ones created after the server started, and
    the files the server writes while answering a request never wake it."""

    def new_root(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def test_every_phase_evidence_directory_is_a_target(self) -> None:
        for target in ("proposals", "implementations", "guidance", "kaggle-inbox", "review", ".papersmith",
                       "experiments", "paper", "sota-pool", "sections"):
            assert target in watcher.WATCH_TARGETS, target

    def test_the_servers_own_writes_are_ignored(self) -> None:
        root = self.new_root()
        assert watcher.is_ignored(root / ".papersmith" / "ai-history" / "claude.jsonl", root)
        assert watcher.is_ignored(root / ".papersmith" / "cache" / "ai-archive-state.json", root)
        assert not watcher.is_ignored(root / ".papersmith" / "model_spec.json", root)
        assert not watcher.is_ignored(root / ".papersmith" / "cachedir-lookalike.json", root)

    def run_watcher(self, root: Path) -> tuple[list[list[Path]], threading.Event]:
        flushes: list[list[Path]] = []
        woke = threading.Event()

        def on_flush(paths: list[Path]) -> None:
            flushes.append(paths)
            woke.set()

        workspace_watcher = watcher.WorkspaceWatcher(root, on_flush, debounce_ms=50)
        workspace_watcher.start()
        self.addCleanup(workspace_watcher.stop)
        return flushes, woke

    def test_a_target_created_after_start_is_watched(self) -> None:
        root = self.new_root()
        (root / "sections").mkdir()
        flushes, woke = self.run_watcher(root)
        time.sleep(0.5)
        (root / "proposals").mkdir()
        time.sleep(watcher.RESCAN_SECONDS * 2 + 0.5)  # the rescan picks the new folder up
        woke.clear()
        (root / "proposals" / "research-concept-r01.md").write_text("# r01\n", encoding="utf-8")
        assert woke.wait(watcher.RESCAN_SECONDS * 3), "a write in a folder created later never woke the board"
        assert any(path.name == "research-concept-r01.md" for batch in flushes for path in batch)

    def test_a_file_written_with_its_new_target_is_announced(self) -> None:
        """mkdir and the first write land before the watch covers the folder:
        no event exists for them, so the rescan announces the target itself."""
        root = self.new_root()
        (root / "sections").mkdir()
        flushes, woke = self.run_watcher(root)
        time.sleep(0.5)
        (root / "review").mkdir()
        (root / "review" / "protocol.json").write_text("{}\n", encoding="utf-8")
        assert woke.wait(watcher.RESCAN_SECONDS * 3), "a new target with a file in it was never announced"
        announced = {path for batch in flushes for path in batch}
        assert root / "review" in announced or root / "review" / "protocol.json" in announced

    def test_an_archive_write_does_not_wake_the_board(self) -> None:
        root = self.new_root()
        (root / ".papersmith" / "ai-history").mkdir(parents=True)
        flushes, woke = self.run_watcher(root)
        time.sleep(0.5)
        (root / ".papersmith" / "ai-history" / "claude.jsonl").write_text("{}\n", encoding="utf-8")
        assert not woke.wait(watcher.MIN_FLUSH_SECONDS + 1.5)
        (root / ".papersmith" / "citations.json").write_text("{}\n", encoding="utf-8")
        assert woke.wait(watcher.RESCAN_SECONDS * 3)
        assert [path.name for batch in flushes for path in batch] == ["citations.json"]

    def test_a_stream_of_writes_flushes_at_most_once_per_interval(self) -> None:
        root = self.new_root()
        (root / "experiments").mkdir()
        flushes, woke = self.run_watcher(root)
        time.sleep(0.5)
        started = time.monotonic()
        while time.monotonic() - started < 2.5:
            with (root / "experiments" / "metrics.csv").open("a", encoding="utf-8") as stream:
                stream.write("step\n")
            time.sleep(0.08)
        time.sleep(watcher.RESCAN_SECONDS + 0.5)
        assert 1 <= len(flushes) <= int(2.5 / watcher.MIN_FLUSH_SECONDS) + 2


class DashboardSubscribesTests(unittest.TestCase):
    """The served page listens to the live channel instead of waiting for a
    manual refresh."""

    PAGE = (Path(__file__).resolve().parents[1] / "skills" / "_core" / "command_center" / "static"
            / "index.html").read_text(encoding="utf-8")

    def test_the_page_opens_the_event_stream_and_reacts_to_state_updates(self) -> None:
        assert "new EventSource('/api/events')" in self.PAGE
        assert "addEventListener('state_update'" in self.PAGE
        assert "LIVE_TAB_REFRESH[activeTab]" in self.PAGE

    def test_the_open_final_judge_panel_refreshes_with_the_preview_tab(self) -> None:
        preview = self.PAGE.split("preview: () =>", 1)[1].split("\n      },", 1)[0]
        assert "paperReviewDetails" in preview and "refreshPaperReview" in preview

    def test_subphases_change_the_redraw_signature(self) -> None:
        assert "sub: (data.fases || []).map(f => JSON.stringify([f.subfases || null, f.steps || null]))" in self.PAGE
