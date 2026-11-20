"""Caztor, the LaTeX editor of the dashboard's PDF tab, run as a sidecar.

Caztor is a Node.js application kept in this repository's ``caztor/`` folder:
a file tree, a LaTeX editor, a PDF compiled by Tectonic and an assistant chat.
The dashboard runs the ``caztor/`` of the papersmith checkout smith is
installed from (``CAZTOR_HOME`` names another copy), starts its server on this
workspace with ``--embed-origin <the dashboard's origin>`` and shows it in a
frame. In that mode Caztor stays on this one workspace, hides its project
navigator, and only the dashboard's origin may frame it.

Caztor always binds loopback here: the exposure variables of the operator's
environment are not passed on. Nothing is started until the PDF tab asks, and
the process is stopped when the dashboard shuts down.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import importlib.util
import time
from collections import deque
from pathlib import Path
from typing import Callable, Mapping

CAZTOR_HOME_ENV = "CAZTOR_HOME"
#: Where the repository keeps Caztor, beside ``src/papersmith``.
BUNDLED_DIR = "caztor"
#: The command, run in the papersmith checkout, that installs Caztor's dependencies and builds its web app.
SETUP_COMMAND = "npm run setup:caztor"
SERVER_ENTRY = Path("apps") / "server-local" / "src" / "main.ts"
WEB_INDEX = Path("apps") / "web" / "dist" / "index.html"

#: The line Caztor prints once it listens, naming the address to open.
READY_LINE = re.compile(r"Caztor is running at (http://(?:127\.0\.0\.1|localhost|\[::1\]):\d+) for ")
#: A browser origin as the dashboard is reached: scheme, host and optional port, nothing else.
ORIGIN = re.compile(r"^https?://(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::\d{1,5})?$")
#: Variables that would expose Caztor beyond loopback or move its project folder.
DROPPED_ENV = ("CAZTOR_HOST", "CAZTOR_PUBLIC_NAME", "CAZTOR_SECURE", "CAZTOR_EMBED_ORIGIN", "INIT_CWD")


def bundled_home() -> Path | None:
    """The ``caztor/`` folder of the papersmith checkout smith is installed from, when there is one."""
    try:
        spec = importlib.util.find_spec("papersmith")
    except (ImportError, ValueError):
        return None
    if spec is None or spec.origin is None:
        return None
    # An editable install: <checkout>/src/papersmith/__init__.py.
    for parent in Path(spec.origin).resolve().parents[:4]:
        if (parent / BUNDLED_DIR / SERVER_ENTRY).is_file():
            return parent / BUNDLED_DIR
    return None


class CaztorSidecar:
    """One Caztor server for one workspace, started on demand."""

    def __init__(self, root: Path | str, *, env: Mapping[str, str] | None = None,
                 startup_timeout: float = 60.0,
                 bundled: Callable[[], Path | None] | None = None) -> None:
        self.root = Path(root)
        self.bundled = bundled_home if bundled is None else bundled
        self.env = dict(os.environ if env is None else env)
        self.startup_timeout = startup_timeout
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._origin: str | None = None
        self._url: str | None = None
        self._tail: deque[str] = deque(maxlen=12)

    def locate(self) -> tuple[Path | None, str | None]:
        """The Caztor copy to run, or why there is none."""
        configured = self.env.get(CAZTOR_HOME_ENV)
        home = Path(configured).expanduser() if configured else self.bundled()
        if home is None:
            return None, ("Caztor was not found: smith is not installed from a papersmith checkout "
                          f"with its {BUNDLED_DIR}/ folder. Set {CAZTOR_HOME_ENV} to a Caztor copy and "
                          "reload the dashboard.")
        if not (home / SERVER_ENTRY).is_file():
            return None, (f"Caztor was not found in {home}. Set {CAZTOR_HOME_ENV} to a Caztor copy "
                          "and reload the dashboard.")
        if not (home / WEB_INDEX).is_file() or not (home / "node_modules").is_dir():
            return None, (f"Caztor is not set up in {home}. Run `{SETUP_COMMAND}` in the papersmith "
                          "checkout, then reload.")
        return home, None

    def ensure(self, origin: str) -> dict:
        """Caztor's address for a dashboard page at ``origin``, starting or restarting it as needed."""
        if not ORIGIN.match(origin):
            return {"available": False, "reason": f"The dashboard origin is not a plain origin: {origin!r}."}
        with self._lock:
            if self._alive() and self._origin == origin and self._url is not None:
                return {"available": True, "url": self._url, "instance": self._process.pid}
            self._stop_locked()
            home, reason = self.locate()
            if home is None:
                return {"available": False, "reason": reason}
            node = shutil.which("node", path=self.env.get("PATH", ""))
            if node is None:
                return {"available": False, "reason": "Node.js (`node`) is not on the PATH; Caztor needs Node.js 26."}
            return self._start(node, home, origin)

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    # -- internals ---------------------------------------------------------

    def _alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _start(self, node: str, home: Path, origin: str) -> dict:
        env = {k: v for k, v in self.env.items() if k not in DROPPED_ENV}
        self._tail.clear()
        ready = threading.Event()
        found: list[str] = []
        try:
            process = subprocess.Popen(
                [node, str(home / SERVER_ENTRY), str(self.root), "--embed-origin", origin],
                cwd=str(home), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            )
        except OSError as error:
            return {"available": False, "reason": f"Caztor could not be started: {error}"}

        def read() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                line = line.rstrip()
                self._tail.append(line)
                match = READY_LINE.search(line)
                if match and not ready.is_set():
                    found.append(match.group(1))
                    ready.set()
            ready.set()

        threading.Thread(target=read, name="caztor-output", daemon=True).start()
        deadline = time.monotonic() + self.startup_timeout
        while not ready.wait(0.05):
            if time.monotonic() > deadline:
                break
        if not found:
            self._process = process
            self._stop_locked()
            last = " ".join(line for line in self._tail if line) or "no output"
            return {"available": False, "reason": f"Caztor did not start: {last}"}
        self._process, self._origin, self._url = process, origin, found[0]
        # A restarted server has a new launch token: the page reloads its frame when the instance changes.
        return {"available": True, "url": found[0], "instance": process.pid}

    def _stop_locked(self) -> None:
        process, self._process = self._process, None
        self._origin = self._url = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
