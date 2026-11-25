"""Caztor, the LaTeX editor of the dashboard's PDF tab, run as a sidecar.

Caztor is a Node.js application kept in this repository's ``caztor/`` folder:
a file tree, a LaTeX editor, a PDF compiled by Tectonic and an assistant chat.
A papersmith install carries it prebuilt in ``papersmith/_caztor`` (its server
bundled into one file, so only ``node`` is needed); a checkout whose
``caztor/`` is set up runs that source instead. ``smith ui`` names the copy in
``CAZTOR_HOME``, which an operator may also set. The dashboard starts its server on this
workspace with ``--embed-origin <the dashboard's origin>`` (and again with its loopback
twin: ``127.0.0.1`` and ``localhost`` on the same port are the same dashboard) and shows
it in a frame. In that mode Caztor stays on this one workspace, hides its project
navigator, and only those origins may frame it.

Each launch gets a frame key, a random secret passed in ``CAZTOR_EMBED_KEY`` (the
environment, not the command line, which ``ps`` shows to every local user). Caztor
hands its page, and with it its launch token, only to a request whose ``k`` query
parameter is that key; the dashboard returns the key only to the browser that holds
its terminal login (server.py), and the PDF tab loads ``<url>/?k=<key>``.

Fetching ``node`` and ``tectonic`` the first time can take minutes, so it happens
outside the sidecar's lock: ``stop`` (the editor switch, shutdown) never waits for a
download or for a starting server. Concurrent requests share one download, and a
failed one is not tried again for `FAILED_TOOL_RETRY_SECONDS`.

Caztor always binds loopback here: the exposure variables of the operator's
environment are not passed on. Nothing is started until the PDF tab asks, and
the process is stopped when the dashboard shuts down. The tab's "LaTeX editor"
switch turns it off in that browser: the tab shows the PDF viewer instead and
Caztor is stopped until the switch is turned on again.
"""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import threading
import importlib.util
import time
from collections import deque
from pathlib import Path
from typing import Callable, Mapping

try:  # imported as a package module by the server, as a plain module by the tests
    from . import caztor_tools
except ImportError:  # pragma: no cover
    import caztor_tools  # type: ignore[no-redef]

CAZTOR_HOME_ENV = "CAZTOR_HOME"
#: Where the repository keeps Caztor, beside ``src/papersmith``.
BUNDLED_DIR = "caztor"
#: The command, run in the papersmith checkout, that installs Caztor's dependencies and builds its web app.
SETUP_COMMAND = "npm run setup:caztor"
SERVER_ENTRY = Path("apps") / "server-local" / "src" / "main.ts"
#: The server built into one file, as a papersmith install ships it.
SERVER_BUNDLE = Path("apps") / "server-local" / "dist" / "main.mjs"
WEB_INDEX = Path("apps") / "web" / "dist" / "index.html"

#: The line Caztor prints once it listens, naming the address to open.
READY_LINE = re.compile(r"Caztor is running at (http://(?:127\.0\.0\.1|localhost|\[::1\]):\d+) for ")
#: A browser origin as the dashboard is reached: scheme, host and optional port, nothing else.
ORIGIN = re.compile(r"^https?://(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::\d{1,5})?$")
#: The variable that carries the frame key to Caztor.
EMBED_KEY_ENV = "CAZTOR_EMBED_KEY"
#: Variables that would expose Caztor beyond loopback, move its project folder, or fix its frame key.
DROPPED_ENV = ("CAZTOR_HOST", "CAZTOR_PUBLIC_NAME", "CAZTOR_SECURE", "CAZTOR_EMBED_ORIGIN", EMBED_KEY_ENV, "INIT_CWD")
#: How long a program that could not be found or fetched is not tried again.
FAILED_TOOL_RETRY_SECONDS = 300.0
STOPPED_REASON = "Caztor was stopped while it started."
_LOOPBACK_TWIN = re.compile(r"^(https?)://(127\.0\.0\.1|localhost)((?::\d{1,5})?)$")


def origin_twins(origin: str) -> tuple[str, ...]:
    """``origin`` and, for ``127.0.0.1`` or ``localhost``, the other name on the same scheme and port:
    both reach the same dashboard, so one Caztor serves both."""
    match = _LOOPBACK_TWIN.match(origin)
    if match is None:
        return (origin,)
    scheme, host, port = match.groups()
    return (origin, f"{scheme}://{'localhost' if host == '127.0.0.1' else '127.0.0.1'}{port}")


def bundled_home() -> Path | None:
    """The ``caztor/`` folder of the papersmith checkout smith is installed from, when there is one."""
    try:
        spec = importlib.util.find_spec("papersmith")
    except (ImportError, ValueError):
        return None
    if spec is None or spec.origin is None:
        return None
    package = Path(spec.origin).resolve().parent
    # An editable install: <checkout>/src/papersmith/__init__.py, with <checkout>/caztor set up.
    checkout = package.parent.parent / BUNDLED_DIR
    if server_entry(checkout) is not None:
        return checkout
    packaged = package / "_caztor"
    return packaged if server_entry(packaged) is not None else None


def server_entry(home: Path) -> Path | None:
    """The file ``node`` runs for the Caztor copy in ``home``: its source when its dependencies are
    installed (a checkout), else its one-file bundle (an install), else nothing."""
    if (home / SERVER_ENTRY).is_file() and (home / "node_modules").is_dir():
        return home / SERVER_ENTRY
    if (home / SERVER_BUNDLE).is_file():
        return home / SERVER_BUNDLE
    return None


class _Lookup:
    """One search for the programs, shared by every request that arrives while it runs."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.result: tuple[str | None, str | None, str | None] = (None, None, "Caztor's programs were not looked up.")


class CaztorSidecar:
    """One Caztor server for one workspace, started on demand.

    Three locks, never held across a download: ``_lock`` guards the process fields and is held only briefly, so
    `stop` never waits; ``_start_lock`` lets one request start a server at a time (the others then find it
    running); ``_tools_lock`` guards the shared program lookup and the remembered failures.
    """

    def __init__(self, root: Path | str, *, env: Mapping[str, str] | None = None,
                 startup_timeout: float = 60.0,
                 bundled: Callable[[], Path | None] | None = None,
                 tools: "caztor_tools.Tools | None" = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.root = Path(root)
        self.bundled = bundled_home if bundled is None else bundled
        self.env = dict(os.environ if env is None else env)
        self.startup_timeout = startup_timeout
        self._tools = tools
        self._clock = clock
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._tools_lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        #: Bumped whenever the server is detached: a start that began under another generation was ended meanwhile.
        self._generation = 0
        #: Bumped by every `stop`: a request that began before it does not start a server after it.
        self._stops = 0
        self._origins: tuple[str, ...] = ()
        self._url: str | None = None
        self._key: str | None = None
        self._tail: deque[str] = deque(maxlen=12)
        self._lookup: _Lookup | None = None
        #: Per program: when it last could not be found or fetched, and why.
        self._failures: dict[str, tuple[float, str]] = {}

    def locate(self) -> tuple[Path | None, str | None]:
        """The Caztor copy to run, or why there is none."""
        configured = self.env.get(CAZTOR_HOME_ENV)
        home = Path(configured).expanduser() if configured else self.bundled()
        if home is None:
            return None, ("Caztor was not found: smith is not installed from a papersmith checkout "
                          f"with its {BUNDLED_DIR}/ folder. Set {CAZTOR_HOME_ENV} to a Caztor copy and "
                          "reload the dashboard.")
        if not (home / SERVER_ENTRY).is_file() and not (home / SERVER_BUNDLE).is_file():
            return None, (f"Caztor was not found in {home}. Set {CAZTOR_HOME_ENV} to a Caztor copy "
                          "and reload the dashboard.")
        if not (home / WEB_INDEX).is_file() or server_entry(home) is None:
            return None, (f"Caztor is not set up in {home}. Run `{SETUP_COMMAND}` in the papersmith "
                          "checkout, then reload.")
        return home, None

    def ensure(self, origin: str) -> dict:
        """Caztor's address, instance and frame key for a dashboard page at ``origin``, starting or restarting it
        as needed. The loopback twin of the origin it runs for does not restart it."""
        if not ORIGIN.match(origin):
            return {"available": False, "reason": f"The dashboard origin is not a plain origin: {origin!r}."}
        running = self._running_for(origin)
        if running is not None:
            return running
        with self._lock:
            stops = self._stops
        home, reason = self.locate()
        if home is None:
            return {"available": False, "reason": reason}
        # The first time on a machine without them, this downloads node and tectonic: outside every lock.
        node, tectonic, reason = self._programs()
        if node is None:
            return {"available": False, "reason": reason}
        with self._start_lock:
            running = self._running_for(origin)  # another request may have started it meanwhile
            if running is not None:
                return running
            with self._lock:
                if self._stops != stops:  # the editor was turned off while the programs were looked up
                    return {"available": False, "reason": STOPPED_REASON}
                previous = self._detach_locked()
            _terminate(previous)
            return self._start(node, home, origin, [node] + ([tectonic] if tectonic else []))

    def stop(self) -> None:
        """Stop Caztor, also one still starting. Never waits for a download or a starting server, only for the
        process to end (its terminate and kill budget)."""
        with self._lock:
            self._stops += 1
            process = self._detach_locked()
        _terminate(process)

    # -- internals ---------------------------------------------------------

    def _alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _running_for(self, origin: str) -> dict | None:
        with self._lock:
            if self._alive() and self._url is not None and origin in self._origins:
                return self._answer_locked()
        return None

    def _answer_locked(self) -> dict:
        assert self._process is not None
        # A restarted server has a new launch token: the page reloads its frame when the instance changes.
        return {"available": True, "url": self._url, "instance": self._process.pid, "key": self._key}

    def _programs(self) -> tuple[str | None, str | None, str | None]:
        """``(node, tectonic, reason)``: node (or None with the reason) and tectonic (None when missing; Caztor
        still opens and its compile reports the missing engine). One lookup at a time, shared by every request
        that arrives while it runs."""
        with self._tools_lock:
            lookup, owner = self._lookup, False
            if lookup is None:
                lookup, owner = _Lookup(), True
                self._lookup = lookup
        if not owner:
            lookup.done.wait()
            return lookup.result
        try:
            lookup.result = self._find_programs()
        finally:
            with self._tools_lock:
                self._lookup = None
            lookup.done.set()
        return lookup.result

    def _find_programs(self) -> tuple[str | None, str | None, str | None]:
        tools = self._tools or caztor_tools.Tools(self.env)
        node, why = self._find(tools, "node")
        if node is None:
            return None, None, f"Caztor needs Node.js 26: {why}"
        tectonic, _ = self._find(tools, "tectonic")
        return node, tectonic, None

    def _find(self, tools: "caztor_tools.Tools", name: str) -> tuple[str | None, str | None]:
        """The program, or None and why; a failure is remembered and not tried again for a while."""
        with self._tools_lock:
            failed = self._failures.get(name)
        if failed is not None and self._clock() - failed[0] < FAILED_TOOL_RETRY_SECONDS:
            return None, failed[1]
        try:
            found = tools.find(name)
        except caztor_tools.ToolError as error:
            with self._tools_lock:
                self._failures[name] = (self._clock(), str(error))
            return None, str(error)
        with self._tools_lock:
            self._failures.pop(name, None)
        return found, None

    def _start(self, node: str, home: Path, origin: str, programs: list[str]) -> dict:
        env = {k: v for k, v in self.env.items() if k not in DROPPED_ENV}
        # Caztor runs `tectonic` (and its agents `node`) by name: a downloaded program's folder goes first.
        # A program already on the PATH leaves the PATH as it is, so other names keep resolving as before.
        on_path = set((env.get("PATH") or "").split(os.pathsep))
        folders = list(dict.fromkeys(str(Path(program).parent) for program in programs
                                     if str(Path(program).parent) not in on_path))
        env["PATH"] = os.pathsep.join([*folders, *([env["PATH"]] if env.get("PATH") else [])])
        key = secrets.token_urlsafe(32)
        env[EMBED_KEY_ENV] = key
        origins = origin_twins(origin)
        argv = [node, str(server_entry(home)), str(self.root)]
        for allowed in origins:
            argv += ["--embed-origin", allowed]
        tail: deque[str] = deque(maxlen=12)
        ready = threading.Event()
        found: list[str] = []
        with self._lock:
            generation = self._generation
            try:
                process = subprocess.Popen(
                    argv, cwd=str(home), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                )
            except OSError as error:
                return {"available": False, "reason": f"Caztor could not be started: {error}"}
            # Known before it is ready, so a stop meanwhile ends it.
            self._process, self._tail = process, tail

        def read() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                line = line.rstrip()
                tail.append(line)
                match = READY_LINE.search(line)
                if match and not ready.is_set():
                    found.append(match.group(1))
                    ready.set()
            ready.set()

        threading.Thread(target=read, name="caztor-output", daemon=True).start()
        deadline = time.monotonic() + self.startup_timeout
        while not ready.wait(0.05):
            if time.monotonic() > deadline or self._generation != generation:
                break
        with self._lock:
            if self._generation != generation:
                return {"available": False, "reason": STOPPED_REASON}
            if found:
                self._origins, self._url, self._key = origins, found[0], key
                return self._answer_locked()
            stale = self._detach_locked()
        _terminate(stale)
        last = " ".join(line for line in tail if line) or "no output"
        return {"available": False, "reason": f"Caztor did not start: {last}"}

    def _detach_locked(self) -> "subprocess.Popen[str] | None":
        """Forget the running (or starting) server and return it, to be ended outside the lock."""
        process, self._process = self._process, None
        self._origins, self._url, self._key = (), None, None
        self._generation += 1
        return process


def _terminate(process: "subprocess.Popen[str] | None") -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
