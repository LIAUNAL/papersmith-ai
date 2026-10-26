"""Debounced filesystem watching and a thread-safe SSE broadcast bus.

The watcher is deliberately narrow: it watches the directories that carry
paper state (``sections/``, ``openspec/``, ``experiments/`` and
``papersmith.yaml``), ignores build and VCS noise, and coalesces a burst of
writes into one 300 ms flush so a single editor save does not fan out into a
dozen recomputations.

The bus lets the watcher thread publish into asyncio queues owned by the
server's SSE subscribers without reaching into their event loop directly.
"""

from __future__ import annotations

import asyncio
import platform
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Iterable

#: Watch targets, relative to the workspace root. ``paper/`` is included
#: because the drafting stage, the word counts, the citation signals and the
#: figure gate all read `paper/main.tex`, `paper/refs.bib` and
#: `paper/Figures/`; without it the live channel is blind to the one artifact
#: the drafting stage is about.
WATCH_TARGETS = ("sections", "openspec", "experiments", "paper", "papersmith.yaml")

#: Health surfaces watched in addition to the state targets. These are the
#: concrete projections whose drift the health payload reports -- targeted at
#: subdirectories so the `.claude/skills` / `.pi/skills` symlinks are not
#: followed into a duplicate of the skills tree. Without at least one of these
#: the health branch of the flush callback can never fire, since
#: ``HEALTH_PREFIXES`` and ``WATCH_TARGETS`` would be disjoint.
HEALTH_WATCH_TARGETS = (
    ".claude/agents",
    ".claude/commands",
    ".opencode/commands",
    ".opencode/plugins",
    ".agents",
    ".pi",
    "scripts",
    "requirements.txt",
)

#: Directory names never worth waking for.
IGNORED_DIRS = frozenset({
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".pytest_cache", ".micromamba", ".mypy_cache", ".ruff_cache",
    "dist", "build", ".scratch", "worktrees",
})

#: LaTeX and editor artifacts that change on every compile or save.
IGNORED_SUFFIXES = (
    ".aux", ".log", ".fls", ".synctex.gz", ".fdb_latexmk", ".out", ".toc",
    ".bbl", ".blg", ".nav", ".snm", ".vrb", ".bcf", ".run.xml", ".swp", ".tmp",
)

#: Paths that change the health payload rather than the paper state.
HEALTH_PREFIXES = (
    "skills", ".claude", ".opencode", ".pi", ".agents", "scripts", "requirements.txt",
)


def is_ignored(path: Path, root: Path) -> bool:
    """Whether a changed path is noise the dashboard must never react to."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        relative = path
    parts = relative.parts
    if any(part in IGNORED_DIRS for part in parts):
        return True
    name = path.name
    if name.endswith(".synctex.gz"):
        return True
    return name.endswith(IGNORED_SUFFIXES)


def is_health_path(path: Path, root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return bool(relative.parts) and relative.parts[0] in HEALTH_PREFIXES


class EventBus:
    """Fan out events from any thread to the server's asyncio subscribers."""

    def __init__(self, max_queue: int = 128) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._max_queue = max_queue

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        with self._lock:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(queue)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def publish(self, event_type: str, payload: Any) -> None:
        """Publish from any thread. A closed or absent loop drops the event."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        message = {"event": event_type, "data": payload}
        with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                loop.call_soon_threadsafe(self._offer, queue, message)
            except RuntimeError:
                # The loop shut down between the check and the call.
                return

    @staticmethod
    def _offer(queue: asyncio.Queue, message: dict[str, Any]) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass


def _is_wsl() -> bool:
    """WSL, identified by its kernel release (as the server does)."""
    return sys.platform == "linux" and "microsoft" in platform.release().lower()


def needs_polling(root: Path, *, wsl: bool | None = None) -> bool:
    """Whether ``watchfiles`` must poll ``root`` instead of using inotify.

    Under WSL, ``/mnt/<letter>/`` is a Windows drive mounted over 9P: changes
    made from Windows raise no inotify event, so the live channel would stay
    silent. Polling costs a little CPU and works there; the Linux filesystem
    (``~/...``) keeps native notifications.
    """
    if not (_is_wsl() if wsl is None else wsl):
        return False
    parts = Path(root).resolve().parts
    return (len(parts) >= 3 and parts[0] == "/" and parts[1] == "mnt"
            and len(parts[2]) == 1 and parts[2].isalpha())


class WorkspaceWatcher:
    """Run ``watchfiles`` in a daemon thread and call ``on_flush`` per burst."""

    def __init__(
        self,
        root: Path,
        on_flush: Callable[[list[Path]], None],
        *,
        debounce_ms: int = 300,
        targets: Iterable[str] = WATCH_TARGETS,
    ) -> None:
        self.root = Path(root)
        self.on_flush = on_flush
        self.debounce_ms = debounce_ms
        self._targets = tuple(targets)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def watch_paths(self) -> list[Path]:
        """The existing targets to watch; never an unreadable or absent path."""
        paths: list[Path] = []
        for relative in self._targets:
            candidate = self.root / relative
            if candidate.exists():
                paths.append(candidate)
        for relative in HEALTH_WATCH_TARGETS:
            candidate = self.root / relative
            if candidate.exists() and candidate not in paths:
                paths.append(candidate)
        skills_dir = self.root / "skills"
        if skills_dir.is_dir():
            paths.extend(
                path for path in sorted(skills_dir.glob("*/SKILL.md")) if path not in paths
            )
        if not paths:
            paths.append(self.root)
        return paths

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="papersmith-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        self._thread = None

    def _run(self) -> None:
        try:
            from watchfiles import watch
        except ModuleNotFoundError:
            return
        paths = self.watch_paths()
        try:
            for changes in watch(
                *[str(path) for path in paths],
                debounce=self.debounce_ms,
                step=50,
                stop_event=self._stop,
                recursive=True,
                raise_interrupt=False,
                # None keeps watchfiles' own default (and its
                # WATCHFILES_FORCE_POLLING variable) off a Windows drive.
                force_polling=True if needs_polling(self.root) else None,
            ):
                if self._stop.is_set():
                    break
                touched = [
                    Path(path) for _change, path in changes
                    if not is_ignored(Path(path), self.root)
                ]
                if touched:
                    try:
                        self.on_flush(touched)
                    except Exception:
                        # A callback failure must not kill the watcher thread.
                        continue
        except Exception:
            # watchfiles can raise when a watched path vanishes; the server
            # keeps serving and the next restart re-establishes the watch.
            return
