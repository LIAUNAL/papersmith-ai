"""Watcher ignore rules and the thread-safe event bus."""

from __future__ import annotations

import asyncio
import tempfile
import threading
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
