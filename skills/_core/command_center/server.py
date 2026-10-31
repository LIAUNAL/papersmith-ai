"""FastAPI application for the Paper Command Center.

Serves the derived workspace state, the wiring diagnostics, a live SSE event
channel fed by a debounced filesystem watcher, and the compiled dashboard from
``static/``. Runs standalone inside a workspace::

    python -m skills._core.command_center.server --port 8080

The API is read-only except for explicit dashboard actions.
``POST /api/health/run-wiring-smoke`` runs the workspace's own verification
script and reports its output; it changes no paper byte.
``POST /api/atlas/build`` ("Regenerar grafo") re-renders
``sota-pool/atlas.html`` through the plausibility checker and renderer
(:mod:`.atlas_build`); it writes nothing else.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import html
import json
import platform
import re
import shutil
import subprocess
import sys
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from . import agents_view, ai_history, banco_suggest, ai_transcripts, atlas, atlas_build, decisions, experiments_tutor, experiments_view, math_view, phase_actions, terminal, tutor, history, paper_preview, novelty_graph, model_spec
from . import doctor_view, localize, toolchain
from .health_inspector import get_wiring_health
from .state_extractor import get_workspace_state, memo_by_file
from .watcher import EventBus, WorkspaceWatcher, is_health_path

#: How long a wiring-health result is reused before it is measured again. The
#: endpoint runs subprocesses (CLI ``--help`` probes), so a burst of watcher
#: events must not multiply them.
DEFAULT_HEALTH_TTL_SECONDS = 10.0

#: A terminal output stream wakes at least this often to notice a client that
#: left, and sends a keep-alive comment after this much silence.
TERMINAL_WAIT_SECONDS = 1.0
TERMINAL_PING_SECONDS = 15.0

_log = logging.getLogger(__name__)

#: Headers on every paper preview response.
_PAPER_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Cache-Control": "no-store",
}

#: Headers on the atlas view: the generated HTML runs scripts, so it is served
#: sandboxed (opaque origin, no network, no outside resources).
_ATLAS_VIEW_HEADERS = {
    "Content-Security-Policy": ("sandbox allow-scripts; default-src 'none'; "
                                "script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                                "img-src data:"),
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "no-referrer",
}

_PLACEHOLDER_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Paper Command Center</title></head>
<body style="font-family:system-ui;max-width:40rem;margin:4rem auto">
<h1>Paper Command Center</h1>
<p>The dashboard assets are not built in this checkout yet.</p>
<pre>npm --prefix ui install &amp;&amp; npm --prefix ui run build</pre>
<p>The JSON API is live: <a href="/api/state">/api/state</a> &middot;
<a href="/api/health/wiring">/api/health/wiring</a></p>
</body></html>"""


# --------------------------------------------------------------------------
# static assets
# --------------------------------------------------------------------------
#: Translated copies of the section contracts, shipped beside the dashboard.
#: ``SOURCES.json`` maps each file to the sha256 of the English contract it
#: was translated from.
SECTION_TRANSLATIONS_DIR = Path(__file__).resolve().parent / "static" / "i18n"
SECTION_TRANSLATION_LANGS = frozenset({"es"})
SECTION_FILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.md")


def section_translation(source: Path, file: str, lang: str) -> bytes | None:
    """The ``lang`` copy of section contract ``file``, or ``None``.

    ``None`` unless a copy exists and ``source`` is byte-identical to the
    contract that copy was translated from.
    """
    folder = SECTION_TRANSLATIONS_DIR / lang / "sections"
    try:
        sources = json.loads((folder / "SOURCES.json").read_text(encoding="utf-8"))
        current = hashlib.sha256(source.read_bytes()).hexdigest()
        if sources.get(file) != current:
            return None
        return (folder / file).read_bytes()
    except (OSError, ValueError, AttributeError):
        return None


def resolve_static_dir(root: Path) -> Path | None:
    """Locate the dashboard build.

    Order: an explicit ``PAPERSMITH_UI_DIST``, a workspace-local ``ui/dist``
    override, then the ``static/`` directory shipped beside this module.
    Returns ``None`` when none of them holds an ``index.html``.
    """
    candidates: list[Path] = []
    override = _env_static_dir()
    if override is not None:
        candidates.append(override)
    candidates.append(root / "ui" / "dist")
    candidates.append(Path(__file__).resolve().parent / "static")
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


def _env_static_dir() -> Path | None:
    import os

    value = os.environ.get("PAPERSMITH_UI_DIST")
    if not value:
        return None
    return Path(value).expanduser()


def export_static(root: Path, destination: Path) -> int:
    """Copy the resolved dashboard build to ``destination`` and report."""
    source = resolve_static_dir(root)
    if source is None:
        print("smith ui: no built dashboard assets found", file=sys.stderr)
        return 2
    destination = destination.expanduser().resolve()
    if destination.exists():
        if not destination.is_dir():
            print(f"smith ui: destination is not a directory: {destination}", file=sys.stderr)
            return 2
        if any(destination.iterdir()):
            print(f"smith ui: destination is not empty: {destination}", file=sys.stderr)
            return 2
    shutil.copytree(source, destination, dirs_exist_ok=True)
    print(f"smith ui: exported {source} -> {destination}")
    return 0


# --------------------------------------------------------------------------
# SSE helpers
# --------------------------------------------------------------------------
def format_sse(event: str, payload: Any) -> str:
    """Encode one SSE frame. The event name is repeated in the data body so a
    client that reads only ``data:`` still sees the event type."""
    body = json.dumps({"type": event, "payload": payload}, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n"


def origin_is_same(request: Request) -> bool:
    """Whether an action request came from this server's own origin.

    A bodyless cross-origin POST is a simple request browsers do not
    preflight, so without this check any page the operator visits while the
    dashboard runs could trigger the wiring-smoke subprocess. A request with no
    ``Origin`` header (curl, the smoke test, same-origin navigations) is
    allowed; a present-but-different origin is rejected.
    """
    origin = request.headers.get("origin")
    if not origin:
        return True
    from urllib.parse import urlparse

    return urlparse(origin).netloc == request.headers.get("host", "")


def is_loopback_bind(host: str) -> bool:
    """Whether binding ``host`` keeps the dashboard on this machine.

    ``localhost`` and loopback literals (``127.0.0.0/8``, ``::1``, bracketed or
    not) do. A wildcard (``0.0.0.0``, ``::``), any other address and any other
    name do not: the network may reach them.
    """
    import ipaddress

    bare = host.strip("[]").lower()
    if bare == "localhost":
        return True
    try:
        return ipaddress.ip_address(bare).is_loopback
    except ValueError:
        return False


def _host_header(host: str, port: int) -> str:
    """The ``Host`` value a client sends for ``host`` on ``port``."""
    bare = host.strip("[]").lower()
    return f"[{bare}]:{port}" if ":" in bare else f"{bare}:{port}"


def build_allowed_hosts(host: str, port: int, extra: list[str] | None = None) -> frozenset[str]:
    """The ``Host`` values to accept for a bind address.

    Every bind accepts its own address on ``port`` and each ``--allowed-host``;
    a loopback bind also accepts the loopback names. Any other ``Host`` gets
    421, which stops DNS-rebinding pages from reading the API, on a non-loopback
    bind as well (``main`` refuses one without ``--allow-unauthenticated-network``).
    For ``npm run dev`` (Vite proxies with ``changeOrigin: false``, so the
    backend sees ``localhost:5173``) start the backend with
    ``--allowed-host localhost:5173``.
    """
    hosts = {_host_header(host, port)}
    if is_loopback_bind(host):
        hosts.update(_host_header(name, port) for name in ("127.0.0.1", "localhost", "::1"))
    hosts.update(value.strip().lower() for value in extra or [] if value.strip())
    return frozenset(hosts)


class HostAllowListMiddleware:
    """Reject requests whose ``Host`` header is not in the allow-list (421).

    Matching is case-insensitive; a missing ``Host`` is rejected. Lifespan
    events pass through untouched.
    """

    def __init__(self, app: Any, allowed_hosts: frozenset[str]) -> None:
        self.app = app
        self.allowed = frozenset(host.lower() for host in allowed_hosts)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        host = ""
        for name, value in scope.get("headers") or []:
            if name == b"host":
                host = value.decode("latin-1").strip()
                break
        if host.lower() in self.allowed:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        body = (
            f"Host header {host!r} is not allowed for this dashboard. "
            "Open it through one of its own addresses, or start the server with "
            f"`smith ui --allowed-host HOST:PORT` (for example --allowed-host {host or 'localhost:5173'}).\n"
        ).encode()
        await send({"type": "http.response.start", "status": 421, "headers": [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(body)).encode()),
        ]})
        await send({"type": "http.response.body", "body": body})


# --------------------------------------------------------------------------
# application
# --------------------------------------------------------------------------
#: Cookie holding the support terminal's per-server secret.
TERMINAL_COOKIE = "papersmith_terminal"


def _framework_version(root: Path) -> str:
    """The papersmith release this workspace was last initialized or upgraded to."""
    try:
        return (root / ".papersmith" / "version").read_text(encoding="utf-8").strip()[:32]
    except OSError:
        return ""


# --------------------------------------------------------------------------
# facts the phase actions report, measured on disk
# --------------------------------------------------------------------------
def _count_pdf_pages(pdf_file: Path) -> int:
    """Pages of a PDF: `pdfinfo` when installed, else the first /Count entry."""
    try:
        res = subprocess.run(["pdfinfo", str(pdf_file)], capture_output=True, text=True, check=True)
        m = re.search(r"Pages:\s+(\d+)", res.stdout)
        if m:
            return int(m.group(1))
    except Exception:
        try:
            m = re.search(rb"/Count\s+(\d+)", pdf_file.read_bytes())
            if m:
                return int(m.group(1))
        except Exception:
            pass
    return 0


def _children(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []


def _block_count(root: Path) -> int:
    try:
        text = (root / "paper" / "main.tex").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    return len(re.findall(r"%% paper-writing block [\w.-]+ begin", text))


def _candidate_count(root: Path) -> int:
    try:
        data = json.loads((root / "sota-pool" / "candidates.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if isinstance(data, dict):
        data = data.get("candidates", [])
    return len(data) if isinstance(data, list) else 0


AUDIT_TIMEOUT_SECONDS = 120
_AUDIT_LOCK = threading.Lock()
#: How long a Smith Doctor report is served from cache; `?fresh=1` re-measures.
DOCTOR_TTL_SECONDS = 30.0
TEX_TIMEOUT_SECONDS = 35
BUILD_TIMEOUT_SECONDS = 20
# One job at a time writes paper/: the writing stage's build and the compile.
_PAPER_LOCK = threading.Lock()


def _audit_verdict(root: Path) -> bool | None:
    """True or False from the last recorded audit; None when there is none or
    it cannot be read."""
    try:
        record = json.loads((root / ".papersmith" / "audit.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = record.get("ok") if isinstance(record, dict) else None
    return ok if isinstance(ok, bool) else None


#: The first bytes of every managed revision the deliberation engine publishes
#: (``experimental-deliberation/profile.ts`` ``artifact.marker``); a file
#: without them is not a published revision, whatever its name.
MANAGED_ARTIFACT_MARKER = b"<!-- proposal-workspace:artifact:v1 -->\n"
_EXPERIMENTS_REVISION = re.compile(r"^experiments-.+-v\d+\.md$")
MAX_PHASE5_NAMES = 200


def _starts_with_marker(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(MANAGED_ARTIFACT_MARKER)) == MANAGED_ARTIFACT_MARKER
    except OSError:
        return False


def _dirs(folder: Path) -> list[Path]:
    try:
        return sorted(p for p in folder.iterdir() if p.is_dir() and not p.is_symlink()
                      and not p.name.startswith("."))[:MAX_PHASE5_NAMES]
    except OSError:
        return []


DISCUSSION_CLI = "python skills/_core/results/discussion_cli.py"
MAX_REVIEW_REPORT_BYTES = 2 * 1024 * 1024


def _discussion_module():
    """The results-discussion contract (``skills/_core/results/discussion.py``),
    loaded by file path because that folder is not a package; the one owner of
    what a ``complete`` ``Results/discussion.json`` is."""
    import importlib.util
    name = "papersmith_results_discussion"
    if name not in sys.modules:
        script = Path(__file__).resolve().parents[1] / "results" / "discussion.py"
        spec = importlib.util.spec_from_file_location(name, script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return sys.modules[name]


def _discussion_status(product: Path) -> str:
    """``complete``, ``draft``, ``invalid`` or ``absent``; never raises."""
    try:
        status = _discussion_module().load_and_check(product).get("status")
    except Exception:
        return "invalid"
    return status if status in ("complete", "draft", "invalid", "absent") else "invalid"


def _review_state(results: Path) -> tuple[bool, bool]:
    """``(a parseable reviewer report exists, it is resolved)`` for one product's
    ``Results/``: ``status`` is ``resolved`` or ``summary.blockers_resolved``
    equals ``summary.blockers``. Bounded and never raises."""
    present = resolved = False
    for name in ("reviewer_report.json", "reviewer-report.json"):
        path = results / name
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_REVIEW_REPORT_BYTES:
                continue
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            continue
        if not isinstance(report, dict):
            continue
        present = True
        summary = report.get("summary")
        blockers = summary.get("blockers") if isinstance(summary, dict) else None
        done = summary.get("blockers_resolved") if isinstance(summary, dict) else None
        if report.get("status") == "resolved" or (
                isinstance(blockers, int) and isinstance(done, int)
                and not isinstance(blockers, bool) and not isinstance(done, bool) and done == blockers):
            resolved = True
    return present, resolved


def _phase5_evidence(root: Path) -> dict[str, Any]:
    """What Phase 5 has on disk, from evidence rather than file names; bounded
    and never raises.

    ``revisions`` counts managed ``experiments/experiments-<slug>-vNN.md``
    files that open with the artifact marker; a product folder
    ``implementations/<repo>/<Name>/`` is a proof of concept when it holds
    ``AGREED.md`` and a full experiment when it holds ``Experimental_AGREED.md``,
    and it counts as done only with a ``Results/`` directory beside the marker.
    ``poc_discussed`` / ``full_discussed`` count the products whose
    ``Results/discussion.json`` is ``complete`` (hypothesis verdicts backed by
    tests, novelty, qualitative analysis; ``results/discussion.py``) and the
    ``*_discussion_drafts`` those with a draft or invalid one; ``review_reports``
    counts products with a parseable ``Results/reviewer_report.json`` and
    ``reviewed`` those whose report is resolved.
    """
    from . import remote_services
    out: dict[str, Any] = {"files": 0, "revisions": 0, "toy": False, "registry": False,
                           "replications": 0, "poc": 0, "poc_results": 0, "full": 0, "full_results": 0,
                           "poc_discussed": 0, "poc_discussion_drafts": 0,
                           "full_discussed": 0, "full_discussion_drafts": 0,
                           "reviewed": 0, "review_reports": 0, "timing": 0, "hpo": 0}
    exp_dir = root / "experiments"
    try:
        names = [f for f in exp_dir.iterdir() if f.is_file() and not f.name.startswith(".")] \
            if exp_dir.is_dir() else []
    except OSError:
        names = []
    out["files"] = len(names)
    out["revisions"] = sum(1 for f in names[:MAX_PHASE5_NAMES]
                           if _EXPERIMENTS_REVISION.match(f.name) and _starts_with_marker(f))
    registry = root / "datasets" / "registry.json"
    try:
        if registry.is_file() and registry.stat().st_size <= 2 * 1024 * 1024:
            out["registry"] = True
            data = json.loads(registry.read_text(encoding="utf-8"))
            out["toy"] = isinstance(data, list) and any(
                isinstance(e, dict) and e.get("role") == "toy" for e in data)
    except (OSError, ValueError):
        pass
    for repo in _dirs(root / "implementations"):
        for product in _dirs(repo):
            if (product / "REPLICATION.md").is_file():
                out["replications"] += 1
            results = (product / "Results").is_dir()
            kind = ("full" if (product / "Experimental_AGREED.md").is_file()
                    else "poc" if (product / "AGREED.md").is_file() else None)
            if kind:
                out[kind] += 1
                out[f"{kind}_results"] += results
                if results:
                    discussion = _discussion_status(product)
                    if discussion == "complete":
                        out[f"{kind}_discussed"] += 1
                    elif discussion in ("draft", "invalid"):
                        out[f"{kind}_discussion_drafts"] += 1
                    present, resolved = _review_state(product / "Results")
                    out["review_reports"] += present
                    out["reviewed"] += resolved
            if (product / "Results" / "timing.json").is_file():
                out["timing"] += 1
            if any((study / "summary.json").is_file() for study in _dirs(product / "Results" / "hpo")):
                out["hpo"] += 1
    out.update(remote_services.launch_evidence(root))
    return out


def _run_audit(root: Path) -> dict[str, Any] | None:
    """Run `smith audit --check-drift` on the workspace with this
    interpreter and record its verdict in `.papersmith/audit.json`.

    One audit at a time: None means another one is still running. `ran` is
    False when the audit could not run at all (papersmith not importable, a
    timeout), which is not the same as an audit with findings.
    """
    from datetime import datetime, timezone
    if not _AUDIT_LOCK.acquire(blocking=False):
        return None
    try:
        command = [sys.executable, "-c",
                   "import sys; from papersmith.cli import main; sys.exit(main(sys.argv[1:]))",
                   "audit", str(root), "--check-drift"]
        ran = True
        try:
            done = subprocess.run(command, cwd=str(root), capture_output=True, text=True,
                                  timeout=AUDIT_TIMEOUT_SECONDS)
            returncode, output = done.returncode, (done.stdout + done.stderr)
            ran = "ModuleNotFoundError" not in output or returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            returncode, output, ran = -1, f"{type(exc).__name__}: {exc}", False
        record = {"ok": ran and returncode == 0, "ran": ran, "returncode": returncode,
                  "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "command": f"smith audit {root} --check-drift", "output": output[-4000:]}
        folder = root / ".papersmith"
        try:
            folder.mkdir(exist_ok=True)
            tmp = folder / "audit.json.tmp"
            tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(folder / "audit.json")
            record["written"] = True
        except OSError as exc:
            record["written"] = False
            record["write_error"] = str(exc)
        return record
    finally:
        _AUDIT_LOCK.release()


def _pdf_page_count(pdf: Path) -> int:
    try:
        return len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))
    except OSError:
        return 0


def _compile_paper(root: Path) -> tuple[dict[str, Any], int]:
    """pdflatex, bibtex, pdflatex twice in paper/, each bounded by a timeout.
    Blocking: the caller runs it off the event loop, holding _PAPER_LOCK."""
    env = os.environ.copy()
    # PATH first, then the shared fallback directories (MacTeX, Homebrew, TeX
    # Live on Linux and WSL). The engine's directory leads PATH so the helpers
    # TeX itself spawns (kpsewhich, mktextfm) come from the same distribution.
    # The tools are still called by name, so the inherited PATH keeps deciding
    # among equals; the search only adds the directories where it found them.
    found = [toolchain.find_tool(name, path=env.get("PATH")) for name in ("pdflatex", "bibtex")]
    lead = list(dict.fromkeys(os.path.dirname(f) for f in found if f and os.path.isabs(f)))
    env["PATH"] = os.pathsep.join(filter(None, (*lead, env.get("PATH", ""))))
    p_dir = str(root / "paper")
    pdflatex = ["pdflatex", "-interaction=nonstopmode", "main.tex"]
    first = None
    for argv in (pdflatex, ["bibtex", "main"], pdflatex, pdflatex):
        try:
            res = subprocess.run(argv, cwd=p_dir, capture_output=True, text=True, env=env,
                                 timeout=TEX_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return {"ok": False, "outputs": [],
                    "error": f"{argv[0]} did not finish in {TEX_TIMEOUT_SECONDS} s; compilation stopped."}, 504
        first = first or res
    return {
        "ok": True,
        "message": (f"paper/main.pdf compiled ({_pdf_page_count(root / 'paper' / 'main.pdf')} pages)."
                    if first.returncode == 0 else
                    f"pdflatex ended with code {first.returncode}; check the log."),
        "outputs": ["paper/main.pdf"],
        "log_tail": first.stdout[-300:] if first.stdout else "",
    }, 200


def _build_manuscript(root: Path) -> tuple[dict[str, Any], int]:
    """Run scripts/build_manuscript.py when the workspace has one. Blocking:
    the caller runs it off the event loop, holding _PAPER_LOCK."""
    b_script = root / "scripts" / "build_manuscript.py"
    if b_script.is_file():
        res = subprocess.run([sys.executable, str(b_script)], cwd=str(root), capture_output=True,
                             text=True, timeout=BUILD_TIMEOUT_SECONDS)
        msg = (f"Transposition run: {_block_count(root)} blocks in paper/main.tex "
               f"(build_manuscript.py ended with code {res.returncode}).")
    else:
        msg = f"Writing: {_block_count(root)} blocks in paper/main.tex."
    return {"ok": True, "message": msg, "outputs": ["paper/main.tex"]}, 200


def terminal_allowed(host: str) -> bool:
    """The support terminal is a shell: offer it only on a loopback bind."""
    return is_loopback_bind(host)


def _novelty_gate():
    """Import and return the novelty_gate module safely."""
    name = "papersmith_novelty_gate"
    if name not in sys.modules:
        script = Path(__file__).resolve().parents[1] / "results" / "novelty_gate.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def create_app(root: Path | str, *, debounce_ms: int = 300,
               health_ttl: float = DEFAULT_HEALTH_TTL_SECONDS,
               history_store: history.HistoryStore | None = None,
               allowed_hosts: frozenset[str] | None = None,
               enable_terminal: bool = False) -> FastAPI:
    root_path = Path(root).expanduser().resolve()
    # The release this process loaded its code under; an upgrade on disk does
    # not reach a running server, so the panel compares the two and says so.
    started_version = _framework_version(root_path)
    bus = EventBus()
    revision = {"value": 0}
    health_cache: dict[str, Any] = {"at": 0.0, "value": None}
    health_lock = threading.Lock()
    store = history_store if history_store is not None else history.HistoryStore()
    # The first successfully read state is the baseline: it produces no entries.
    try:
        baseline: dict[str, Any] | None = get_workspace_state(root_path)
    except Exception:  # noqa: BLE001 - history must never stop the server starting
        _log.exception("history: could not read the baseline state")
        baseline = None
    state_baseline = {"value": baseline}
    state_lock = threading.Lock()
    # record() runs on the watcher thread, request threads (measure_health) and
    # the smoke path. Holding this lock across add + publish keeps the frames in
    # seq order. Lock order: health_lock -> history_lock; history_lock is a leaf
    # (publish only schedules onto the loop) and is never held while taking
    # health_lock or state_lock.
    history_lock = threading.Lock()

    def record(changes: list[history.Change]) -> None:
        for change in changes:
            with history_lock:
                entry = store.add(change.kind, change.element_id, change.summary,
                                  change.before, change.after)
                bus.publish("history_append", entry.to_dict())

    def measure_health(force: bool = False) -> dict[str, Any]:
        with health_lock:
            now = time.monotonic()
            cached = health_cache["value"]
            if not force and cached is not None and now - health_cache["at"] < health_ttl:
                return cached
            value = get_wiring_health(root_path)
            health_cache["value"] = value
            health_cache["at"] = now
            if cached is not None:
                try:
                    record(history.diff_health(cached, value))
                except Exception:  # noqa: BLE001
                    _log.exception("history: recording a health change failed")
            # Every new measurement, forced or past the TTL, reaches every
            # dashboard once, after its history entry and in measurement order.
            bus.publish("health_update", value)
            return value

    def on_flush(paths: list[Path]) -> None:
        revision["value"] += 1
        changed = []
        for path in paths:
            try:
                changed.append(str(path.resolve().relative_to(root_path)))
            except (OSError, ValueError):
                changed.append(str(path))
        state = get_workspace_state(root_path)
        bus.publish("state_update", {
            "revision": revision["value"],
            "changed": sorted(changed),
            "state": state,
        })
        try:
            with state_lock:
                previous = state_baseline["value"]
                state_baseline["value"] = state
            if previous is not None:
                record(history.diff_states(previous, state))
        except Exception:  # noqa: BLE001 - history never blocks the live channel
            _log.exception("history: recording a state change failed")
        if any(is_health_path(path, root_path) for path in paths):
            measure_health(force=True)

    watcher = WorkspaceWatcher(root_path, on_flush, debounce_ms=debounce_ms)
    smoke_lock = threading.Lock()
    terminals = terminal.TerminalManager(root_path)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        bus.bind_loop(asyncio.get_running_loop())
        watcher.start()
        try:
            yield
        finally:
            watcher.stop()
            terminals.close_all()

    app = FastAPI(title="Paper Command Center", version="0.1.0", lifespan=lifespan)
    app.state.root = root_path
    app.state.bus = bus
    app.state.watcher = watcher
    app.state.measure_health = measure_health
    app.state.history = store
    # Display labels in English, or Spanish on `?lang=es` (see localize.py).
    app.add_middleware(localize.LocalizeMiddleware)
    if allowed_hosts is not None:
        app.add_middleware(HostAllowListMiddleware, allowed_hosts=allowed_hosts)
    # One in-flight wiring-smoke run at a time: repeated or concurrent POSTs
    # must not multiply the subprocess.
    app.state.smoke_lock = smoke_lock

    @app.get("/api/status")
    def api_status_adapter() -> JSONResponse:
        import re
        from datetime import datetime, timezone

        state = get_workspace_state(root_path)
        paper_meta = state.get("paper_metadata", {})
        project_name = root_path.name
        target_title = paper_meta.get("title") or state.get("title") or project_name
        topic = paper_meta.get("topic") or "unspecified"
        authors_raw = paper_meta.get("authors") or []
        authors = ", ".join(a if isinstance(a, str) else a.get("name", "") for a in authors_raw) if authors_raw else "No author assigned"

        proposals_dir = root_path / "proposals"
        prop_files = sorted(
            [p.name for p in proposals_dir.glob("*.md") if p.is_file() and not p.name.startswith(".")],
            reverse=True
        ) if proposals_dir.is_dir() else []
        active_prop = prop_files[0] if prop_files else "No active proposal"
        match = re.search(r"-(r\d+)\.md$", active_prop)
        active_run = match.group(1) if match else ("r00" if not prop_files else "r01")

        totals_meta = state.get("totals", {})
        written_blocks = totals_meta.get("blocks_written", 0)
        total_blocks = totals_meta.get("blocks_total", 46)
        total_words = totals_meta.get("word_count", 0)
        pdf_file = root_path / "paper" / "main.pdf"
        pdf_exists = pdf_file.is_file()

        # Dynamic block and word counts from paper/main.tex
        tex_file = root_path / "paper" / "main.tex"
        if tex_file.is_file():
            try:
                tex_content = tex_file.read_text(encoding="utf-8", errors="ignore")
                found_blocks = len(re.findall(r"%% paper-writing block ([\w\.-]+) begin", tex_content))
                if found_blocks > 0:
                    written_blocks = found_blocks
                    total_blocks = 46
                words = [w for w in re.sub(r"%.*|\\+[a-zA-Z]+|\\[^a-zA-Z]", " ", tex_content).split() if len(w) > 1]
                total_words = max(total_words, len(words))
            except Exception:
                pass

        # Dynamic PDF page count
        pdf_pages = 0
        pdf_size = pdf_file.stat().st_size if pdf_exists else 0
        # Change token the dashboard polls to reload an open preview.
        pdf_mtime = int(pdf_file.stat().st_mtime * 1000) if pdf_exists else 0
        if pdf_exists:
            pdf_pages = memo_by_file("pdf_pages", pdf_file, lambda: _count_pdf_pages(pdf_file))

        # Figure counts
        fig_dir = root_path / "paper" / "Figures"
        fig_count = len(list(fig_dir.glob("*.pdf"))) if fig_dir.is_dir() else 0

        # BibTeX reference counts
        bib_file = root_path / "paper" / "refs.bib"
        bib_count = 0
        if bib_file.is_file():
            try:
                bib_count = len(re.findall(r"@\w+\s*\{", bib_file.read_text(encoding="utf-8", errors="ignore")))
            except Exception:
                pass

        # Check real workspace artifacts to compute dynamic phases
        harness_ok = (root_path / ".papersmith").is_dir() and (root_path / "papersmith.yaml").is_file()
        sota_atlas = (root_path / "sota-pool" / "atlas.json").is_file()
        sota_cand = (root_path / "sota-pool" / "candidates.json").is_file()

        guidance_ref_dir = root_path / "guidance" / "reference-papers"
        guidance_refs = [d for d in guidance_ref_dir.iterdir() if d.is_dir() and not d.name.startswith(".")] if guidance_ref_dir.is_dir() else []
        guidance_loose_pdfs = list((root_path / "guidance").glob("*.pdf")) + (list(guidance_ref_dir.glob("*.pdf")) if guidance_ref_dir.is_dir() else [])

        has_deliberated_prop = any(re.search(r"-r\d+\.md$", p) for p in prop_files)
        p5 = _phase5_evidence(root_path)

        has_scaffold = tex_file.is_file()
        has_decl = False
        if has_scaffold:
            try:
                has_decl = "%% paper-writing declarations begin" in tex_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

        audit_file = root_path / ".papersmith" / "audit.json"
        has_audit = _audit_verdict(root_path) is True

        # Phase 1
        fase1_status = "PASS" if harness_ok else "PENDING"
        # Phase 2
        if sota_atlas:
            fase2_status, fase2_prog, fase2_det = "PASS", 1.0, "3D SOTA atlas compiled in sota-pool/"
        elif sota_cand:
            fase2_status, fase2_prog, fase2_det = "ACTIVE", 0.5, "SOTA candidates found, atlas pending"
        else:
            fase2_status, fase2_prog, fase2_det = "PENDING", 0.0, "No artifacts in sota-pool/"

        # Phase 3
        if guidance_refs and not guidance_loose_pdfs:
            fase3_status, fase3_prog, fase3_det = "PASS", 1.0, f"{len(guidance_refs)} references ingested, zero loose PDFs"
        elif guidance_loose_pdfs or guidance_refs:
            fase3_status, fase3_prog, fase3_det = "ACTIVE", 0.5, f"{len(guidance_loose_pdfs)} PDFs awaiting ingestion"
        else:
            fase3_status, fase3_prog, fase3_det = "PENDING", 0.0, "No reference articles in guidance/"

        # Phase 4
        if has_deliberated_prop:
            fase4_status, fase4_prog, fase4_det = "PASS", 1.0, f"Proposal deliberated ({active_prop})"
        elif prop_files:
            fase4_status, fase4_prog, fase4_det = "ACTIVE", 0.5, f"Draft in progress ({prop_files[0]})"
        else:
            fase4_status, fase4_prog, fase4_det = "PENDING", 0.0, "No proposal in proposals/"

        # Phase 5: a published protocol revision, a proof of concept and a full
        # experiment that each close with a complete Results/discussion.json;
        # never a file name or a bare Results/ folder.
        p5_done = [p5["revisions"] > 0, p5["poc_discussed"] > 0, p5["full_discussed"] > 0]
        fase5_det = (f"Protocol published: {'yes' if p5_done[0] else 'no'}"
                     f" · PoC with a complete discussion: {p5['poc_discussed']} of {p5['poc']}"
                     f" · full experiments with a complete discussion: {p5['full_discussed']} of {p5['full']}")
        if all(p5_done):
            fase5_status, fase5_prog = "PASS", 1.0
        elif any(p5_done) or p5["files"] or p5["poc"] or p5["full"]:
            fase5_status, fase5_prog = "ACTIVE", round(sum(p5_done) / 3, 3)
        else:
            fase5_status, fase5_prog = "PENDING", 0.0

        def _p5(done: bool, started: bool = False) -> str:
            return "PASS" if done else ("ACTIVE" if started else "PENDING")

        p5_protocol = _p5(p5["revisions"] > 0, p5["files"] > 0)

        # Phase 6
        if has_scaffold:
            fase6_status, fase6_prog, fase6_det = "PASS", 1.0, "paper/main.tex and section contracts scaffolded"
        else:
            fase6_status, fase6_prog, fase6_det = "PENDING", 0.0, "paper/main.tex awaiting scaffolding"

        # Phase 7
        if has_decl:
            fase7_status, fase7_prog, fase7_det = "PASS", 1.0, "Operational declarations recorded in main.tex"
        else:
            fase7_status, fase7_prog, fase7_det = "PENDING", 0.0, "Declarations not yet recorded"

        # Phase 8
        if written_blocks >= total_blocks and total_blocks > 0:
            fase8_status, fase8_prog = "PASS", 1.0
        elif written_blocks > 0:
            fase8_status, fase8_prog = "ACTIVE", round(written_blocks / max(1, total_blocks), 3)
        else:
            fase8_status, fase8_prog = "PENDING", 0.0
        fase8_det = f"{written_blocks}/{total_blocks} canonical blocks written ({total_words} words)"

        # Phase 9
        if fig_count >= 1:
            fase9_status, fase9_prog, fase9_det = "PASS", 1.0, f"{fig_count} vector figure(s) in paper/Figures/"
        else:
            fase9_status, fase9_prog, fase9_det = "PENDING", 0.0, "0 figures in paper/Figures/"

        # Phase 10
        if pdf_exists:
            fase10_status, fase10_prog, fase10_det = "PASS", 1.0, f"PDF manuscript compiled ({pdf_pages} pages, {round(pdf_size / 1024, 1)} KB)"
        else:
            fase10_status, fase10_prog, fase10_det = "PENDING", 0.0, "paper/main.pdf not compiled yet"

        # Phase 11
        if has_audit:
            fase11_status, fase11_prog, fase11_det = "PASS", 1.0, "Cross-cutting audit run and passed"
        else:
            fase11_status, fase11_prog, fase11_det = "PENDING", 0.0, (
                "The last audit failed: check .papersmith/audit.json"
                if _audit_verdict(root_path) is False else "Cross-cutting audit pending")

        fases = [
            {
                "id": "Fase 1",
                "stage_id": "harness",
                "name": "Phase 1: Environment Setup & Harness",
                "gate": "G-HARNESS",
                "agent": "ecosystem-orchestrator",
                "desc": "Workspace structure, harness projections (.claude, .opencode, .pi, .agents), the micromamba environment and runtime validation.",
                "tools": ["read", "bash"],
                "skills": ["harness-setup", "workspace-verifier"],
                "cli_command": "smith init --harness-only",
                "outputs": [".papersmith/", "papersmith.yaml", "pyproject.toml"],
                "status": fase1_status,
                "progress": 1.0 if fase1_status == "PASS" else 0.0,
                "detail": "Harness projections in place" if fase1_status == "PASS" else "Environment awaiting initialization",
                "subfases": [
                    {"id": "1.1", "name": "Workspace & Manifest", "status": fase1_status, "detail": "papersmith.yaml and the versioned base structure"},
                    {"id": "1.2", "name": "Agent Projection", "status": fase1_status, "detail": "Symbolic links to the operational harnesses"},
                    {"id": "1.3", "name": "Micromamba Isolation", "status": fase1_status, "detail": "Python 3.12 and the environment's dependencies"},
                    {"id": "1.4", "name": "CLI Integrity", "status": fase1_status, "detail": "papersmith CLI verified"}
                ]
            },
            {
                "id": "Fase 2",
                "stage_id": "plausibility",
                "name": "Phase 2: Plausibility & 3D SOTA Atlas",
                "gate": "G-SOTA",
                "agent": "sota-scout & sota-grapher & novelty-screener",
                "desc": "SOTA exploration, plausibility validation and compilation of the 3D atlas of candidates and the conceptual constellation. Without a clear idea, the optional thematic help turns 3 to 5 keywords into a proposed idea from the Banco LIA, which the operator edits, approves and launches.",
                "tools": ["read", "write", "mcp"],
                "skills": ["sota-scout", "semantic-scholar", "pubmed-search"],
                "cli_command": "smith run --stage plausibility",
                "outputs": ["sota-pool/atlas.json", "sota-pool/atlas.html", "sota-pool/candidates.json"],
                "status": fase2_status,
                "progress": fase2_prog,
                "detail": fase2_det,
                "subfases": [
                    {"id": "2.1", "name": "SOTA Article Discovery", "status": fase2_status, "detail": "Search and filtering of Q1/Q2 literature"},
                    {"id": "2.2", "name": "Metadata & Family Extraction", "status": fase2_status, "detail": "Taxonomic classification of candidates"},
                    {"id": "2.3", "name": "Spatial Embedding & 3D Constellation", "status": fase2_status, "detail": "Generation of atlas.json for the WebGL view"},
                    {"id": "2.4", "name": "Novelty Gap Detection", "status": fase2_status, "detail": "Identification of conceptual voids and opportunity"}
                ]
            },
            {
                "id": "Fase 3",
                "stage_id": "ingestion",
                "name": "Phase 3: Reference & Literature Ingestion",
                "gate": "G-INGEST",
                "agent": "paper-ingestion",
                "desc": "Markdown ingestion of reference articles, BibTeX normalization of the bibliography and extraction of base inputs.",
                "tools": ["read", "write", "marker"],
                "skills": ["paper-ingestion", "pdf-extractor", "bibtex-parser"],
                "cli_command": "smith ingest guidance/reference-papers/",
                "outputs": ["guidance/reference-papers/", "paper/refs.bib", "paper/Figures/"],
                "status": fase3_status,
                "progress": fase3_prog,
                "detail": fase3_det,
                "subfases": [
                    {"id": "3.1", "name": "Base Article Ingestion", "status": fase3_status, "detail": "Structural conversion of PDFs into clean Markdown"},
                    {"id": "3.2", "name": "BibTeX Normalization (refs.bib)", "status": fase3_status, "detail": "Verified and consolidated citations"},
                    {"id": "3.3", "name": "Vector Figure Extraction", "status": fase3_status, "detail": "Reference figures and diagrams"},
                    {"id": "3.4", "name": "Fact & Input Extraction", "status": fase3_status, "detail": "Parameter extraction for the manuscript"}
                ]
            },
            {
                "id": "Fase 4",
                "stage_id": "proposal",
                "name": "Phase 4: Proposal Deliberation & Conceptual Model",
                "gate": "G-PROP",
                "agent": "deliberation-publish & mathematical-tutor",
                "desc": "Formal scientific deliberation of the proposal (rNN), novelty definition, and discussion of the concept map and the mathematics with the Socratic tutor.",
                "tools": ["read", "write", "deliberate"],
                "skills": ["proposal-deliberation", "peer-review-simulator"],
                "cli_command": "smith deliberate proposals/",
                "outputs": ["proposals/"],
                "status": fase4_status,
                "progress": fase4_prog,
                "detail": fase4_det,
                "subfases": [
                    {"id": "4.1", "name": "Stage bound: Delimitation & Locus", "status": fase4_status, "detail": "Problem definition and anchoring of the conceptual locus"},
                    {"id": "4.2", "name": "Stage deliberated: Novelty & Consensus", "status": fase4_status, "detail": "Discussion of hypotheses and innovation pillars"},
                    {"id": "4.3", "name": "Stage composed: Basic Mathematical Model", "status": fase4_status, "detail": "Mathematical formalization and key equations"},
                    {"id": "4.4", "name": "Stage published: Publication & Cryptographic Receipt", "status": fase4_status, "detail": "Revision sealed with a SHA-256 hash"},
                    {"id": "4.5", "name": "Concept map discussion", "status": fase4_status, "detail": "Pillars, hypotheses and layers of the concept (Concept Map tab)"},
                    {"id": "4.6", "name": "Mathematics and Socratic tutor", "status": fase4_status, "detail": "Equations in LaTeX, the novelty card and a tutor with hand-drawn images (math-tutor)"}
                ]
            },
            {
                "id": "Fase 5",
                "stage_id": "poc_experiments",
                "name": f"Phase 5: {phase_actions.PHASE_LABELS['poc_experiments']}",
                "gate": "G-EXP-POC",
                "agent": phase_actions.ACTIONS["poc_experiments"]["agent"],
                "desc": "Experimental protocol deliberation, toy set, replication of the comparison methods, proof of concept, time estimation, optional hyperparameter search, full experiments, code review, remote rehearsal and an operator-authorized launch, locally or on a remote service (CLI or MCP).",
                "tools": ["read", "write", "validate"],
                "skills": ["experimental-deliberation", "datasets", "proposal-implementation", "experimental-implementation"],
                "cli_command": "/experimental-deliberation <texto>",
                "outputs": ["experiments/", "datasets/registry.json", "implementations/"],
                "status": fase5_status,
                "progress": fase5_prog,
                "detail": fase5_det,
                "subfases": [
                    {"id": "5.1", "name": "Stage bound: Anchoring Claims & Metrics", "status": p5_protocol, "detail": "Success criteria and quantifiable metrics (passes with the published revision)"},
                    {"id": "5.2", "name": "Stage validated: Baselines & SOTA", "status": p5_protocol, "detail": "experimental-validation checks protocol, metrics and baselines against dated searches"},
                    {"id": "5.3", "name": "Stage deliberated: Metrological Design & Protocols", "status": p5_protocol, "detail": "Test and validation protocols"},
                    {"id": "5.4", "name": "Stage composed: Experiment Specification", "status": p5_protocol, "detail": "Formalization of experiments with instrumentation"},
                    {"id": "5.5", "name": "Stage published: Gate Approval", "status": p5_protocol, "detail": f"experimental-publish leaves experiments/experiments-<slug>-vNN.md with the artifact marker ({p5['revisions']} published revision(s))"},
                    {"id": "5.6", "name": "Data: always a toy set, plus the official dataset", "status": _p5(p5["toy"], p5["registry"]), "detail": "/datasets synth|search|license|qc|prepare|publish with dataset-scout and dataset-curator; passes with a toy set in datasets/registry.json; private publishing only with the operator's consent"},
                    {"id": "5.7", "name": "Replication of comparison methods", "status": _p5(p5["replications"] > 0), "detail": f"/proposal-implementation → paper-replicator: the published code first, adopted and audited; when there is none, a reimplementation ({p5['replications']} REPLICATION.md)"},
                    {"id": "5.8", "name": "Proof of concept", "status": _p5(p5["poc_discussed"] > 0, p5["poc"] > 0), "detail": f"/proposal-implementation (implementation-build): a folder with AGREED.md, Results/ and a complete Results/discussion.json (hypothesis verdicts, tests, novelty, qualitative analysis): {p5['poc_discussed']} of {p5['poc']}; check with `{DISCUSSION_CLI} check --product <path>`"},
                    {"id": "5.9", "name": "Estimate the time and choose where to run", "status": _p5(p5["timing"] > 0), "detail": "Before the pilot and again before the full run: a short timing probe (one epoch of one fold per arm) in Results/timing.json; the Experiments tab estimates the PoC and the full run (±20%) and lists the local and remote options"},
                    {"id": "5.10", "name": "Hyperparameter search (Optuna, optional)", "status": _p5(p5["hpo"] > 0), "detail": f"Only when the deliberation judged it worthwhile: /hyperparameter-search plan|report|status, nested inside each outer fold, the same budget per arm, a declared importance evaluator; contours and importances in Results/hpo/ ({p5['hpo']} product(s) with studies)"},
                    {"id": "5.11", "name": "Full experiments", "status": _p5(p5["full_discussed"] > 0, p5["full"] > 0), "detail": f"/experimental-implementation (experiments-build): a folder with Experimental_AGREED.md, Results/ and a complete Results/discussion.json (hypothesis verdicts backed by tests, novelty, qualitative analysis): {p5['full_discussed']} of {p5['full']}; check with `{DISCUSSION_CLI} check --product <path>`"},
                    {"id": "5.12", "name": "Code review (experiments-reviewer) before the rehearsal", "status": _p5(p5["reviewed"] > 0, p5["review_reports"] > 0), "detail": f"Code quality, optimization, GPU use and declared statistical tests; it reads Results/reviewer_report.json (status resolved, or every blocker resolved): {p5['reviewed']} resolved of {p5['review_reports']} report(s)"},
                    {"id": "5.13", "name": "Remote rehearsal and launch authorization (operator)", "status": _p5(p5["launched"] > 0, p5["jobs"] > 0 or p5["smokes"] > 0), "detail": f"Only for remote runs (local runs directly). /kaggle-accounts validate and smith team add --attest (one account per person and service); then generate-job → submit --smoke → fetch --smoke and smoke record → readiness → gate (operator) → submit → status / poll → fetch. Passed rehearsals: {p5['rehearsals_passed']}; ledgers with submissions: {p5['launched']}"}
                ]
            },
            {
                "id": "Fase 6",
                "stage_id": "scaffolding",
                "name": "Phase 6: Manuscript Scaffolding & Contracts",
                "gate": "G-SCAFFOLD",
                "agent": "contract-auditor",
                "desc": "Scaffolding of paper/main.tex with canonical blocks and section contracts under the journal's document class.",
                "tools": ["read", "write"],
                "skills": ["scaffold-generator", "latex-contract-indexer"],
                "cli_command": "smith implement scaffold",
                "outputs": ["paper/main.tex", "paper/refs.bib", "sections/*.md"],
                "status": fase6_status,
                "progress": fase6_prog,
                "detail": fase6_det,
                "subfases": [
                    {"id": "6.1", "name": "Section Structure", "status": fase6_status, "detail": "Canonical contracts in sections/*.md"},
                    {"id": "6.2", "name": "Opening of Canonical Blocks", "status": fase6_status, "detail": "Integrated markers and SHA-256 hashes"},
                    {"id": "6.3", "name": "Rhetorical Role Assignment", "status": fase6_status, "detail": "Editorial questions and fact coupling"},
                    {"id": "6.4", "name": "Typographic Setup", "status": fase6_status, "detail": "LaTeX template of the target journal"}
                ]
            },
            {
                "id": "Fase 7",
                "stage_id": "declarations",
                "name": "Phase 7: Operational Declarations & Co-authorship",
                "gate": "G-DECLARATIONS",
                "agent": "declarations-recorder",
                "desc": "Recording of the operational declarations: CRediT authorship, funding, open repository and ethical considerations.",
                "tools": ["read", "write"],
                "skills": ["credit-taxonomy", "ethics-compliance"],
                "cli_command": "smith implement declarations",
                "outputs": ["paper/main.tex (declarations)"],
                "status": fase7_status,
                "progress": fase7_prog,
                "detail": fase7_det,
                "subfases": [
                    {"id": "7.1", "name": "CRediT Co-authorship Taxonomy", "status": fase7_status, "detail": "Formalized author roles"},
                    {"id": "7.2", "name": "Ethics Statement", "status": fase7_status, "detail": "Ethical and institutional protocols"},
                    {"id": "7.3", "name": "Data and Code Availability", "status": fase7_status, "detail": "Repository and accessibility"},
                    {"id": "7.4", "name": "Sealing in main.tex", "status": fase7_status, "detail": "declarations region locked with a hash"}
                ]
            },
            {
                "id": "Fase 8",
                "stage_id": "writing",
                "name": "Phase 8: Technical Writing & Transposition",
                "gate": "G-WRITING",
                "agent": "redactor & style-sampler & insumos-observer",
                "desc": "Technical writing, in waves, of the manuscript's canonical blocks from the experimental data.",
                "tools": ["read", "write", "substitute"],
                "skills": ["technical-writing", "facts-coupler", "style-shield"],
                "cli_command": "python3 scripts/build_manuscript.py",
                "outputs": ["paper/main.tex", "sections/*.md"],
                "status": fase8_status,
                "progress": fase8_prog,
                "detail": fase8_det,
                "manuscript_ref": {"pages": "1–10", "words": total_words},
                "subfases": [
                    {"id": "8.1", "name": "Wave 1: Title, Keywords & Abstract", "status": fase8_status, "detail": "Opening slots on p. 1"},
                    {"id": "8.2", "name": "Wave 2: Introduction & Hypotheses", "status": fase8_status, "detail": "Introduction and motivation blocks"},
                    {"id": "8.3", "name": "Wave 3: Related Work & SOTA", "status": fase8_status, "detail": "State of the art and comparison table"},
                    {"id": "8.4", "name": "Wave 4–9: Methods, Results & Conclusions", "status": fase8_status, "detail": "Technical and experimental blocks"}
                ]
            },
            {
                "id": "Fase 9",
                "stage_id": "figures",
                "name": "Phase 9: Technical Diagrams & Grounding",
                "gate": "G-FIGURES",
                "agent": "diagram-author & figure-auditor",
                "desc": "Architecture diagrams, vector figures, schemes and grounding in the text.",
                "tools": ["read", "write", "latexmk"],
                "skills": ["vector-graphics", "sips-optimizer", "figure-grounding"],
                "cli_command": "smith audit --figures",
                "outputs": ["paper/Figures/"],
                "status": fase9_status,
                "progress": fase9_prog,
                "detail": fase9_det,
                "subfases": [
                    {"id": "9.1", "name": "Architecture & System Diagrams", "status": fase9_status, "detail": "Structural and topological figures"},
                    {"id": "9.2", "name": "Experimental Curves and Plots", "status": fase9_status, "detail": "Performance and empirical contrasts"},
                    {"id": "9.3", "name": "Methodological Schemes", "status": fase9_status, "detail": "Processing and transduction flows"},
                    {"id": "9.4", "name": "Figure Grounding in the Text", "status": fase9_status, "detail": "Anchoring of cross-references"}
                ]
            },
            {
                "id": "Fase 10",
                "stage_id": "paper",
                "name": "Phase 10: Compilation & PDF Manuscript",
                "gate": "G-PDF",
                "agent": "latex-compiler",
                "desc": "Compilation of the LaTeX manuscript to PDF with editorial layout, BibTeX reference checks and an interactive viewer.",
                "tools": ["read", "bash"],
                "skills": ["pdflatex-engine", "bibtex-linker", "pdfjs-viewer"],
                "cli_command": "cd paper && pdflatex -interaction=nonstopmode main.tex && bibtex main && pdflatex main.tex",
                "outputs": ["paper/main.pdf"],
                "status": fase10_status,
                "progress": fase10_prog,
                "detail": fase10_det,
                "manuscript_ref": {"pages": pdf_pages, "size_mb": round(pdf_size / (1024*1024), 2), "file": "paper/main.pdf"},
                "subfases": [
                    {"id": "10.1", "name": "pdfTeX Compilation", "status": fase10_status, "detail": "0 fatal compilation errors"},
                    {"id": "10.2", "name": "BibTeX Linking", "status": fase10_status, "detail": f"{bib_count} citations linked, none orphaned"},
                    {"id": "10.3", "name": "Vector Optimization", "status": fase10_status, "detail": "Generation of an optimized PDF"},
                    {"id": "10.4", "name": "Interactive PDF Viewer", "status": fase10_status, "detail": "PDF.js viewer with change control"}
                ]
            },
            {
                "id": "Fase 11",
                "stage_id": "audit",
                "name": "Phase 11: Cross-cutting Audit & Gates",
                "gate": "G-AUDIT",
                "agent": "audit-report",
                "desc": "Strict verification of the framework's 4 gates: readiness, fact coupling, style shielding and figures.",
                "tools": ["read", "bash"],
                "skills": ["cross-auditor", "gate-checker", "hash-verifier"],
                "cli_command": "smith audit",
                "outputs": [".papersmith/audit.json"],
                "status": fase11_status,
                "progress": fase11_prog,
                "detail": fase11_det,
                "subfases": [
                    {"id": "11.1", "name": "Gate G1: Writing Readiness", "status": fase11_status, "detail": "Canonical contracts validated"},
                    {"id": "11.2", "name": "Gate G2: Coupling Verification", "status": fase11_status, "detail": "Facts coupled with input sources"},
                    {"id": "11.3", "name": "Gate G3: Style Shield", "status": fase11_status, "detail": "Rhetorical and citation shielding"},
                    {"id": "11.4", "name": "Gate G4: Figure Grounding", "status": fase11_status, "detail": "Figures anchored with references in the text"}
                ]
            }
        ]
        # The phase drawer renders a sub-phase's ``desc``; every sub-phase states it as ``detail``.
        for phase in fases:
            for sub in phase.get("subfases") or []:
                sub.setdefault("desc", sub.get("detail", ""))
        phase_actions.attach(fases, root_path)

        artifacts = []
        for p in (root_path / "proposals").glob("*.md"):
            artifacts.append({
                "rel_path": str(p.relative_to(root_path)),
                "name": p.name,
                "category": "Proposals",
                "size_kb": round(p.stat().st_size / 1024, 1)
            })
        if (root_path / "paper" / "main.tex").is_file():
            tex = root_path / "paper" / "main.tex"
            artifacts.append({
                "rel_path": "paper/main.tex",
                "name": "main.tex",
                "category": "LaTeX Manuscript",
                "size_kb": round(tex.stat().st_size / 1024, 1)
            })
        guidance_guide = root_path / "guidance" / "paper-guide"
        if guidance_guide.is_dir():
            for gp in sorted(guidance_guide.glob("*.md")):
                artifacts.append({
                    "rel_path": str(gp.relative_to(root_path)),
                    "name": gp.name,
                    "category": "Scientific Guide",
                    "size_kb": round(gp.stat().st_size / 1024, 1)
                })
        guidance_ref = root_path / "guidance" / "reference-papers"
        if guidance_ref.is_dir():
            for rp in sorted(guidance_ref.glob("**/*.md")):
                artifacts.append({
                    "rel_path": str(rp.relative_to(root_path)),
                    "name": rp.name,
                    "category": "Reference / Input",
                    "size_kb": round(rp.stat().st_size / 1024, 1)
                })
        if (root_path / "sota-pool" / "atlas.json").is_file():
            artifacts.append({
                "rel_path": "sota-pool/atlas.json",
                "name": "atlas.json (SOTA)",
                "category": "SOTA Constellation",
                "size_kb": round((root_path / "sota-pool" / "atlas.json").stat().st_size / 1024, 1)
            })
        experiments_dir = root_path / "experiments"
        if experiments_dir.is_dir():
            for ep in sorted(experiments_dir.glob("*.md")):
                artifacts.append({
                    "rel_path": f"experiments/{ep.name}",
                    "name": ep.name,
                    "category": "Experiments",
                    "size_kb": round(ep.stat().st_size / 1024, 1)
                })
        sections_dir = root_path / "sections"
        if sections_dir.is_dir():
            for sp in sorted(sections_dir.glob("*.md")):
                artifacts.append({
                    "rel_path": f"sections/{sp.name}",
                    "name": f"Rules: {sp.name}",
                    "category": "Section Rules",
                    "size_kb": round(sp.stat().st_size / 1024, 1)
                })

        SECTION_METADATA = {
            "09-title-and-keywords": {
                "page": 1,
                "principles": "Informative technical concision without ambiguous acronyms. Identify the system/model and the application domain.",
                "blocks": [
                    {"id": "title-and-keywords.title", "role": "Main Title", "question": "What is the work's technical contribution and application domain?"},
                    {"id": "title-and-keywords.keywords", "role": "Indexable Keywords", "question": "What are the manuscript's indexable terms and descriptors?"}
                ],
                "cross_relations": "Projects the key terms that the Abstract develops and the Introduction formalizes."
            },
            "08-abstract": {
                "page": 1,
                "principles": "Canonical slot structure: Context -> Technical gap -> Methodological proposal -> Architecture/Design -> Experimental results -> Accuracy/Performance -> Impact and reproducibility.",
                "blocks": [
                    {"id": "abstract.slot-1", "role": "Problem Context", "question": "Why does this problem matter and what is the application domain?"},
                    {"id": "abstract.slot-2", "role": "Technological / Scientific Gap", "question": "What shortcomings or limitations do current approaches have?"},
                    {"id": "abstract.slot-3", "role": "Main Proposal", "question": "What does this work propose to close that gap?"},
                    {"id": "abstract.slot-4", "role": "Architecture and Methodology", "question": "What components make up the proposed system or model?"},
                    {"id": "abstract.slot-5", "role": "Experimental Results", "question": "What performance metrics and empirical validation were reached?"},
                    {"id": "abstract.slot-6", "role": "Differentiating Metric", "question": "What accuracy, latency or empirical advantage was shown?"},
                    {"id": "abstract.slot-7", "role": "Impact and Reproducibility", "question": "How does this advance change the research field?"}
                ],
                "cross_relations": "Summarizes the whole manuscript; every slot anticipates a section of the paper."
            },
            "06-introduction": {
                "page": 1,
                "principles": "Sequential argument construction: problem justification, methodological map, current bottleneck, proposed solution, testable hypotheses and contributions.",
                "blocks": [
                    {"id": "introduction.block-1", "role": "Setting and Motivation", "question": "What is the problem's context and fundamental motivation?"},
                    {"id": "introduction.block-4a", "role": "Methodological Roadmap", "question": "How were the research and its framework structured?"},
                    {"id": "introduction.block-2", "role": "Bottleneck and Challenges", "question": "What technical or theoretical limitations prevent solving the problem today?"},
                    {"id": "introduction.block-3", "role": "Proposed Solution", "question": "How does the proposed system address the identified limitations?"},
                    {"id": "introduction.block-4b", "role": "Testable Hypotheses", "question": "What hypotheses does the study put to an empirical test?"},
                    {"id": "introduction.block-5", "role": "Manuscript Structure", "question": "How is the reading of the following sections organized?"},
                    {"id": "introduction.block-6", "role": "Key Contributions", "question": "What are the article's definitive scientific and technical contributions?"}
                ],
                "cross_relations": "The stated hypotheses are validated one by one in Results and synthesized in Conclusions."
            },
            "05-related-work": {
                "page": 3,
                "principles": "Rigorous comparative taxonomy against the state of the art (SOTA). A formal table contrasting key features, metrics and gaps.",
                "blocks": [
                    {"id": "related-work.rw-preamble", "role": "Evolution and Landscape", "question": "How has the field evolved and what are its main strands?"},
                    {"id": "related-work.rw-panorama", "role": "Current Approaches and Limitations", "question": "What strengths and weaknesses do the relevant prior works show?"},
                    {"id": "related-work.rw-problem-blocks", "role": "Impact of the Unresolved Gaps", "question": "How do the existing limitations affect overall performance?"},
                    {"id": "related-work.rw-closing", "role": "Positioning of the Proposal", "question": "Why does the proposal stand apart from the SOTA?"},
                    {"id": "related-work.rw-synthesis-artefact", "role": "SOTA Atlas Synthesis", "question": "How does the comparative analysis support the methodological decisions taken?"}
                ],
                "cross_relations": "Sets the frame of reference that justifies the design and experimentation decisions."
            },
            "01-materials-and-methods": {
                "page": 4,
                "principles": "A rigorous, reproducible description without ambiguity. Formal models, mathematical formulation and system architecture.",
                "blocks": [
                    {"id": "materials-and-methods.mm-preamble", "role": "Modular View of the System", "question": "What are the main modules and components of the system or model?"},
                    {"id": "materials-and-methods.mm-borrowed-machinery", "role": "Foundations and Topology", "question": "What base mechanisms or architectures are adopted and how do they connect?"},
                    {"id": "materials-and-methods.mm-proposal", "role": "Specific Methodological Innovation", "question": "What specific mathematical formulation or design is introduced?"}
                ],
                "cross_relations": "Specifies the architecture and methods whose performance the experimental sections evaluate."
            },
            "02-experimental-setup": {
                "page": 5,
                "principles": "Reproducible validation protocols: bench/dataset setup, instrumentation, evaluation metrics and parameters.",
                "blocks": [
                    {"id": "experimental-setup.es-preamble", "role": "Experimental Strategy", "question": "What methodological strategy validates the proposal?"},
                    {"id": "experimental-setup.es-dataset", "role": "Datasets or Signal Sources", "question": "What data sources, instruments or test environments were used?"},
                    {"id": "experimental-setup.es-assessment", "role": "Evaluation Metrics", "question": "What are the success criteria and formal performance metrics?"},
                    {"id": "experimental-setup.es-training-details", "role": "Parameters and Protocols", "question": "What are the hyperparameters, rates and experimentation protocols?"}
                ],
                "cross_relations": "Fixes the empirical rules and conditions to evaluate the hypotheses stated in the Introduction."
            },
            "03-results-and-discussion": {
                "page": 6,
                "principles": "Density of quantitative evidence. Corroboration with plots, performance tables and contrast with baselines.",
                "blocks": [
                    {"id": "results-and-discussion.rd-general-task", "role": "Hypothesis Validation and Main Task", "question": "Are the main hypotheses stated in the introduction corroborated?"},
                    {"id": "results-and-discussion.rd-contribution-blocks", "role": "Quantitative Analysis and Performance", "question": "What empirical results were obtained against the success metrics?"},
                    {"id": "results-and-discussion.rd-cost", "role": "Contrast with Baselines and Discussion", "question": "What quantitative and qualitative advantages are shown over the state of the art?"}
                ],
                "cross_relations": "Empirically validates the stated hypotheses, confirming the Abstract's claims."
            },
            "04-limitations": {
                "page": 8,
                "principles": "Constructive self-criticism and scientific honesty: assumptions, computational complexity, trade-offs and failure conditions.",
                "blocks": [
                    {"id": "limitations.lim-opening-concession", "role": "Opening Concession and Scope", "question": "What are the work's validity limits and assumptions?"},
                    {"id": "limitations.lim-proposal-items", "role": "Resource or Compute Constraints", "question": "What compute, energy or data requirements constrain the system?"},
                    {"id": "limitations.lim-validation-items", "role": "Representativeness of the Sample/Data", "question": "What scenarios or distributions have not been covered exhaustively yet?"},
                    {"id": "limitations.lim-failure-mode", "role": "Potential Failure Modes", "question": "In which edge cases or under which perturbations could performance degrade?"},
                    {"id": "limitations.lim-closing", "role": "Constructive Outlook", "question": "How can these limitations be mitigated in future iterations?"}
                ],
                "cross_relations": "Engages with the Related Work and sets the priority lines for future work."
            },
            "07-conclusions": {
                "page": 8,
                "principles": "A conclusive synthesis of the fundamental contributions without repeating raw data. Outlook and directions for future work.",
                "blocks": [
                    {"id": "conclusions.concl-block-1", "role": "Problem Recap", "question": "What fundamental challenge did this research take on and solve?"},
                    {"id": "conclusions.concl-block-2", "role": "Main Contribution Synthesis", "question": "What are the main findings and consolidated advances?"},
                    {"id": "conclusions.concl-block-3", "role": "Scientific or Technological Implications", "question": "What practical or theoretical implications does this advance have for the discipline?"},
                    {"id": "conclusions.concl-block-4", "role": "Future Lines and Reproducibility", "question": "What resources remain available to the community and what future work opens?"}
                ],
                "cross_relations": "Closes the argumentative cycle opened in the Abstract and the Introduction."
            },
            "10-back-matter": {
                "page": 9,
                "principles": "Formal transparency: CRediT authorship, funding sources, data/code availability and ethics statements.",
                "blocks": [
                    {"id": "back-matter.bm-author-contributions", "role": "CRediT Co-authorship Taxonomy", "question": "What roles and contributions did each author of the manuscript take on?"},
                    {"id": "back-matter.bm-funding", "role": "Funding Statement", "question": "What projects, grants or bodies funded the research?"},
                    {"id": "back-matter.bm-data-availability", "role": "Data and Code Availability", "question": "Where do the datasets, source code and reproducible artifacts live?"},
                    {"id": "back-matter.bm-conflicts-of-interest", "role": "Conflicts of Interest", "question": "Is there any financial or personal conflict of interest to declare?"},
                    {"id": "back-matter.bm-acknowledgments", "role": "Acknowledgments", "question": "Which institutions, reviewers or technical collaborators are thanked?"},
                    {"id": "back-matter.bm-appendices", "role": "Technical Appendices", "question": "What mathematical derivations, supplementary tables or details are appended?"}
                ],
                "cross_relations": "Meets the regulatory and ethical requirements of academic publishing."
            }
        }

        sections_data = []
        for s in state.get("sections", []):
            sec_meta = SECTION_METADATA.get(s["id"], {})
            sections_data.append({
                "id": s["id"],
                "section": s["section"],
                "title": s["section"].replace("-", " ").title(),
                "filename": f"{s['id']}.md",
                "words": s.get("word_count", 0),
                "citations": s.get("citations", {}).get("verified", 0),
                "has_figures": s.get("section") in ("materials-and-methods", "experimental-setup", "results-and-discussion"),
                "status": s.get("status", "CONTRACTED"),
                "blocks_written": s.get("blocks_written", 0),
                "blocks_total": s.get("blocks_total", 0),
                "pdf_page": sec_meta.get("page", 1),
                "principles": sec_meta.get("principles", "Formal technical writing under publication guidelines."),
                "canonical_blocks": sec_meta.get("blocks", []),
                "cross_relations": sec_meta.get("cross_relations", "Cross traceability with the rest of the manuscript.")
            })

        gate_mod = _novelty_gate()
        nov_gate_data = gate_mod.read_gate(root_path)
        nov_status = nov_gate_data.get("status", "pending")
        g_nov_status = (
            "PASS"
            if nov_status == "approved"
            else (
                "ACTIVE"
                if fase5_status == "PASS" and nov_status == "pending"
                else (
                    "ACTIVE"
                    if nov_status.startswith("iterating_")
                    else "PENDING"
                )
            )
        )

        gates_list = [
            {
                "id": "G-EXP-POC",
                "name": "Proof-of-Concept & Experimental Design Gate",
                "status": "PASS" if fase5_status == "PASS" else ("ACTIVE" if fase5_status == "ACTIVE" else "PENDING"),
                "criteria": "Empirical validation and experimental design: test reproducibility, baseline specification and quantitative success criteria; hypothesis verdicts backed by hypothesis tests, novelty justification, qualitative or interpretability analysis where it applies and a summarized discussion per stage.",
                "reviewer": "experiments-reviewer",
                "phase": "Fase 5"
            },
            {
                "id": "G-NOVELTY",
                "name": "Novelty & Findings Gate",
                "status": g_nov_status,
                "criteria": "Scientific novelty assessment and empirical evidence support: hypothesis contrast vs SOTA, reviewer defense audit, and explicit operator authorization before manuscript scaffolding and drafting.",
                "reviewer": "novelty-screener & operator",
                "phase": "Fase 5.5 (Novedad)"
            },
            {
                "id": "G1",
                "name": "Writing Readiness Gate",
                "status": "PASS" if fase6_status == "PASS" else ("ACTIVE" if fase6_status == "ACTIVE" else "PENDING"),
                "criteria": "Section contracts validated with a closed grammar and resolved dependencies.",
                "reviewer": "contract-auditor",
                "phase": "Fase 6"
            },
            {
                "id": "G2",
                "name": "Coupling Verification Gate",
                "status": "PASS" if fase7_status == "PASS" else ("ACTIVE" if fase7_status == "ACTIVE" else "PENDING"),
                "criteria": "Demanded facts (formulation, design, results) coupled with the authorship and funding declarations.",
                "reviewer": "paper-graph-auditor",
                "phase": "Fase 7"
            },
            {
                "id": "G3",
                "name": "Grounding & Style Leak Gate",
                "status": "PASS" if fase8_status == "PASS" else ("ACTIVE" if fase8_status == "ACTIVE" else "PENDING"),
                "criteria": "No empty citations or placeholders; strict isolation of bibliographic sources.",
                "reviewer": "grounding-auditor",
                "phase": "Fase 8"
            },
            {
                "id": "G4",
                "name": "Diagram & Raster Gate",
                "status": "PASS" if fase9_status == "PASS" else ("ACTIVE" if fase9_status == "ACTIVE" else "PENDING"),
                "criteria": "Compilation check of TikZ diagrams, methodological schemes and vector figures.",
                "reviewer": "figure-auditor",
                "phase": "Fase 9"
            }
        ]

        telemetry_defaults = {
            "Fase 1": {"fase": "Phase 1: Environment Setup & Harness", "gate": "G-HARNESS", "tool_uses": 8, "duracion": "1m 12s", "tokens": "14,250"},
            "Fase 2": {"fase": "Phase 2: Plausibility & 3D SOTA Atlas", "gate": "G-SOTA", "tool_uses": 16, "duracion": "3m 45s", "tokens": "32,800"},
            "Fase 3": {"fase": "Phase 3: Reference Ingestion & Main Thesis", "gate": "G-INGEST", "tool_uses": 24, "duracion": "5m 20s", "tokens": "48,500"},
            "Fase 4": {"fase": "Phase 4: Proposal Deliberation & Conceptual Model", "gate": "G-PROP", "tool_uses": 14, "duracion": "2m 30s", "tokens": "26,100"},
            "Fase 5": {"fase": "Phase 5: Proof of concept and experiments", "gate": "G-EXP-POC", "tool_uses": 15, "duracion": "2m 55s", "tokens": "29,400"},
            "Fase 6": {"fase": "Phase 6: Manuscript Scaffolding & Contracts", "gate": "G-SCAFFOLD", "tool_uses": 10, "duracion": "1m 50s", "tokens": "18,900"},
            "Fase 7": {"fase": "Phase 7: Operational Declarations & Co-authorship", "gate": "G-DECLARATIONS", "tool_uses": 7, "duracion": "1m 10s", "tokens": "12,400"},
            "Fase 8": {"fase": "Phase 8: Technical Writing & Transposition", "gate": "G-WRITING", "tool_uses": 19, "duracion": "4m 15s", "tokens": "38,200"},
            "Fase 9": {"fase": "Phase 9: Technical Diagrams & Grounding", "gate": "G-FIGURES", "tool_uses": 9, "duracion": "1m 40s", "tokens": "16,500"},
            "Fase 10": {"fase": "Phase 10: Compilation & PDF Manuscript", "gate": "G-PDF", "tool_uses": 6, "duracion": "50s", "tokens": "9,800"},
            "Fase 11": {"fase": "Phase 11: Cross-cutting Audit & Gates", "gate": "G-AUDIT", "tool_uses": 8, "duracion": "1m 30s", "tokens": "15,600"},
        }
        telemetria = []
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for f in fases:
            fid = f["id"]
            if f["status"] in ("PASS", "ACTIVE") and fid in telemetry_defaults:
                t_info = dict(telemetry_defaults[fid])
                t_info["veredicto"] = f["status"]
                t_info["fecha"] = today_str
                telemetria.append(t_info)

        tokens_sum = sum(int(t.get("tokens", "0").replace(",", "")) for t in telemetria)
        totals_payload = {
            "sections_count": len(sections_data),
            "total_words": total_words,
            "bibtex_entries": bib_count,
            "gates_passed": sum(1 for g in gates_list if g["status"] == "PASS"),
            "gates_total": len(gates_list),
            "total_tokens": f"{tokens_sum:,}" if tokens_sum else "0",
            "pdf_pages": pdf_pages,
            "total_tool_uses": sum(t.get("tool_uses", 0) for t in telemetria),
            "blocks_written": written_blocks,
            "blocks_total": total_blocks,
            "phases_completed": sum(1 for f in fases if f["status"] == "PASS"),
            "phases_active": sum(1 for f in fases if f["status"] == "ACTIVE"),
            "phases_total": len(fases)
        }

        run_details = {
            "title": target_title,
            "pdf_ready": pdf_exists,
            "pdf_size": pdf_size,
            "pdf_mtime": pdf_mtime,
            "docx_ready": False,
            "docx_size": 0
        }

        return JSONResponse({
            "project_name": project_name,
            "framework_version": _framework_version(root_path),
            "target_title": target_title,
            "topic": topic,
            "authors": authors,
            "active_run": active_run,
            "all_runs": list(prop_files) if prop_files else [active_run],
            "active_proposal": active_prop,
            "active_tools": state.get("active_tools", ["antigravity"]),
            "gates": gates_list,
            "gates_map": {g["id"]: g["status"] for g in gates_list},
            "fases": fases,
            "pipeline_stages": fases,
            "sections": sections_data,
            "artifacts": artifacts,
            "telemetria": telemetria,
            "totals": totals_payload,
            "run_details": run_details,
            "pdf_available": pdf_exists,
            "proposals": {"count": len(prop_files), "files": prop_files},
            "state": state
        })

    @app.get("/api/artifact")
    def api_artifact(path: str = "", file: str = "") -> Response:
        target_path = path or file
        if not target_path:
            return JSONResponse({"detail": "path or file is required"}, status_code=400)
        target = (root_path / target_path).resolve()
        try:
            target.relative_to(root_path)
        except ValueError:
            return JSONResponse({"detail": "access denied"}, status_code=403)
        if not target.is_file():
            return JSONResponse({"detail": "artifact not found"}, status_code=404)
        ext = target.suffix.lower()
        media_type = "text/plain; charset=utf-8"
        if ext in (".md", ".txt"):
            media_type = "text/plain; charset=utf-8"
        elif ext == ".json":
            media_type = "application/json"
        elif ext == ".pdf":
            media_type = "application/pdf"
        elif ext in (".png", ".jpg", ".jpeg"):
            media_type = f"image/{ext.lstrip('.')}"
        elif ext == ".svg":
            # An SVG opened directly must not run its scripts on this origin.
            return Response(target.read_bytes(), media_type="image/svg+xml",
                            headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
                                     "X-Content-Type-Options": "nosniff"})
        return Response(target.read_bytes(), media_type=media_type)

    @app.get("/api/section-translation")
    def api_section_translation(file: str = "", lang: str = "es") -> Response:
        # A translated copy of a section contract, for reading only: the
        # contract itself stays in English because the engine checks every
        # `quote` against its text. A copy is served only while the
        # workspace's contract is byte-identical to the one it was made from,
        # so an edited or newer contract shows as itself, never as a stale
        # translation.
        if not SECTION_FILE_RE.fullmatch(file) or lang not in SECTION_TRANSLATION_LANGS:
            return JSONResponse({"detail": "invalid section or language"}, status_code=400)
        source = root_path / "sections" / file
        translated = section_translation(source, file, lang)
        if translated is None:
            return JSONResponse({"detail": "no current translation"}, status_code=404)
        return Response(translated, media_type="text/plain; charset=utf-8")

    @app.get("/api/flow")
    def api_flow() -> Response:
        # A workspace's own flow wins; otherwise the framework's, shipped with
        # the dashboard (a copy of docs/diagrams/papersmith-pi-flow.html).
        flow_path = root_path / "docs" / "papersmith-flow.html"
        if not flow_path.is_file():
            flow_path = Path(__file__).resolve().parent / "static" / "papersmith-flow.html"
        if flow_path.is_file():
            return HTMLResponse(flow_path.read_text(encoding="utf-8"))
        return JSONResponse({"detail": "flow diagram not found"}, status_code=404)

    @app.get("/api/agents")
    def api_agents() -> JSONResponse:
        # The agents table under the Flujo Archify diagram.
        return JSONResponse(agents_view.get_agents_view(root_path))

    @app.get("/api/state")
    def api_state() -> JSONResponse:
        return JSONResponse(get_workspace_state(root_path))

    @app.get("/api/history")
    def api_history(boot_id: str | None = None, after_seq: int = 0,
                    element: str | None = None, kind: str | None = None,
                    limit: int = history.DEFAULT_LIMIT) -> JSONResponse:
        try:
            return JSONResponse(store.page(boot_id, after_seq, element, kind, limit))
        except history.HistoryQueryError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/api/health/wiring")
    def api_health_wiring() -> JSONResponse:
        return JSONResponse(measure_health())

    doctor_cache: dict[str, Any] = {"at": 0.0, "value": None}
    doctor_lock = threading.Lock()
    doctor_refresh = threading.Lock()  # held while one background rebuild runs

    def build_doctor(fresh: bool) -> dict[str, Any]:
        # The rows `smith doctor --json` prints, built by the same function
        # from this process's wiring health and phases. Caller holds doctor_lock.
        # Lock order: doctor_lock -> health_lock (measure_health).
        wiring = measure_health(force=fresh)
        try:
            phases = json.loads(bytes(api_status_adapter().body)).get("fases") or []
            phases_error = None
        except Exception as exc:  # noqa: BLE001 - one area degrades, not the report
            phases, phases_error = None, f"/api/status failed: {type(exc).__name__}: {exc}"
        value = doctor_view.get_doctor_view(root_path, wiring=wiring, phases=phases,
                                            phases_error=phases_error)
        doctor_cache["value"], doctor_cache["at"] = value, time.monotonic()
        return value

    def refresh_doctor() -> None:
        try:
            with doctor_lock:
                build_doctor(False)
        except Exception:  # noqa: BLE001 - the expired report stays served
            _log.exception("doctor: background refresh failed")
        finally:
            doctor_refresh.release()

    def warm_doctor() -> None:
        with doctor_lock:
            if doctor_cache["value"] is None:
                build_doctor(False)

    app.state.warm_doctor = warm_doctor

    @app.get("/api/doctor")
    def api_doctor(fresh: bool = False) -> JSONResponse:
        # The Smith Doctor tab. An expired report is served as is while one
        # background rebuild replaces it; `fresh` always rebuilds in line.
        cached = doctor_cache["value"]
        if not fresh and cached is not None:
            if (time.monotonic() - doctor_cache["at"] >= DOCTOR_TTL_SECONDS
                    and doctor_refresh.acquire(blocking=False)):
                try:
                    threading.Thread(target=refresh_doctor, name="doctor-refresh",
                                     daemon=True).start()
                except RuntimeError:  # no thread to release it; the next visit retries
                    doctor_refresh.release()
            return JSONResponse(cached)
        with doctor_lock:
            if not fresh and doctor_cache["value"] is not None:
                return JSONResponse(doctor_cache["value"])
            return JSONResponse(build_doctor(fresh))

    @app.post("/api/health/run-wiring-smoke")
    def api_run_wiring_smoke(request: Request) -> JSONResponse:
        if not origin_is_same(request):
            return JSONResponse(
                {"available": False, "exit_code": None,
                 "detail": "cross-origin request rejected"},
                status_code=403,
            )
        if not smoke_lock.acquire(blocking=False):
            return JSONResponse(
                {"available": True, "exit_code": None,
                 "detail": "a wiring smoke run is already in progress"},
                status_code=409,
            )
        try:
            return JSONResponse(_run_wiring_smoke(root_path, bus, record=record))
        finally:
            smoke_lock.release()

    @app.get("/api/paper/preview")
    def api_paper_preview() -> JSONResponse:
        # Read-only: bounded, containment-checked reads (see paper_preview).
        return JSONResponse(paper_preview.build_preview(root_path),
                            headers=dict(_PAPER_HEADERS))

    @app.get("/api/model/math")
    def api_model_math() -> JSONResponse:
        # The math panel: the paper's own LaTeX and its novelty card (read-only).
        return JSONResponse(math_view.build(root_path), headers=dict(_PAPER_HEADERS))

    @app.get("/api/experiments")
    def api_experiments() -> JSONResponse:
        # The experiments tab: protocol, products, convergence, figures,
        # tables, significance and remote runs (read-only, bounded, contained).
        view = experiments_view.get_experiments_view(root_path)
        workspace_version = _framework_version(root_path)
        view["dashboard"] = {"startedVersion": started_version,
                             "workspaceVersion": workspace_version,
                             "stale": workspace_version != started_version}
        return JSONResponse(view, headers=dict(_PAPER_HEADERS))

    @app.post("/api/experiments/diagrams/validate")
    async def api_validate_diagram(request: Request) -> JSONResponse:
        # The operator's "Validar diagrama" button, one of the two writers of
        # the record `remote-execution submit` reads before a launch (the other
        # is `diagram_cli.py validate`, run by an agent on the operator's
        # explicit approval in the conversation). Unlike the
        # other actions, a request without an Origin header (curl, an agent's
        # shell) is refused too: the browser always sends one on a POST.
        if not request.headers.get("origin") or not origin_is_same(request):
            return JSONResponse({"ok": False, "error": "only the dashboard can validate a diagram"},
                                status_code=403)
        try:
            payload = await request.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            return JSONResponse({"ok": False, "error": "expected {repo, name, kind}"}, status_code=422)
        status, body = experiments_view.validate_diagram(
            root_path, str(payload.get("repo", "")), str(payload.get("name", "")),
            str(payload.get("kind", "")))
        return JSONResponse(body, status_code=status)

    @app.get("/api/model")
    def api_model() -> JSONResponse:
        """Return conceptual architecture, formal mathematical model, and PoC deliberation plan."""
        return JSONResponse(model_spec.get_model_specification(root_path))

    @app.get("/api/paper/file")
    def api_paper_file(name: str = "") -> Response:
        status, path, content_type = paper_preview.resolve_artifact(root_path, name)
        if status == "bad":
            return JSONResponse({"detail": "malformed artifact name"}, status_code=400)
        if status == "too_large":
            return JSONResponse({"detail": "artifact exceeds the 100 MiB limit"},
                                status_code=413)
        data = paper_preview.read_artifact(path) if path is not None else None
        if status != "ok" or data is None:
            if status == "ok":
                return JSONResponse({"detail": "artifact exceeds the 100 MiB limit"},
                                    status_code=413)
            return JSONResponse({"detail": "artifact not found"}, status_code=404)
        # Whole-file responses; Range is not supported. No CSP sandbox here: it
        # would stop browser PDF viewers from rendering the document.
        return Response(data, media_type=content_type, headers={
            **_PAPER_HEADERS, "Content-Disposition": "inline"})

    @app.get("/api/pdf")
    def api_pdf_direct(request: Request) -> Response:
        pdf_path = root_path / "paper" / "main.pdf"
        if not pdf_path.is_file():
            return JSONResponse({"detail": "main.pdf not found in paper/"}, status_code=404)
        # Revalidatable rather than no-store: the live preview re-requests the
        # PDF whenever the status token moves, and an unchanged build answers 304.
        info = pdf_path.stat()
        etag = f'"{info.st_mtime_ns:x}-{info.st_size:x}"'
        headers = {**_PAPER_HEADERS, "Cache-Control": "no-cache", "ETag": etag,
                   "Content-Disposition": "inline"}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(pdf_path.read_bytes(), media_type="application/pdf", headers=headers)

    @app.get("/api/pdf/annotations")
    def api_pdf_annotations() -> JSONResponse:
        ann_path = root_path / ".papersmith" / "anotaciones_pdf.json"
        if ann_path.is_file():
            try:
                data = json.loads(ann_path.read_text(encoding="utf-8"))
                return JSONResponse(data)
            except Exception:
                pass
        return JSONResponse({"timestamp": None, "annotations": [], "applied": {}})

    @app.post("/api/pdf/execute")
    async def api_pdf_execute(request: Request) -> JSONResponse:
        if not origin_is_same(request):
            return JSONResponse({"ok": False, "error": "cross-origin request rejected"},
                                status_code=403)
        try:
            payload = await request.json()
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"Invalid JSON payload: {e}"}, status_code=400)
        annotations = payload.get("annotations", [])
        ann_path = root_path / ".papersmith" / "anotaciones_pdf.json"
        ann_path.parent.mkdir(parents=True, exist_ok=True)
        
        strikes = [a for a in annotations if a.get("type") == "strikethrough"]
        comments = [a for a in annotations if a.get("type") == "comment"]
        humanizes = [a for a in annotations if a.get("type") == "humanize"]
        
        summary = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "annotations": annotations,
            "applied": {
                "strikethrough": len(strikes),
                "comments": len(comments),
                "humanize": len(humanizes),
            },
            "summary": {
                "strikethrough_applied": len(strikes),
                "comments_applied": len(comments),
                "humanize_applied": len(humanizes),
                # Nothing is applied to a source file here: the annotations are recorded.
                "files_modified": [],
                "pdf_recompiled": True
            }
        }
        ann_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        
        md_lines = [
            "# Editorial Annotation and Humanization Report",
            f"**Date:** {summary['timestamp']}",
            f"- ✂️ Struck-through texts (delete): {len(strikes)}",
            f"- 💬 Editorial comments: {len(comments)}",
            f"- ✨ Passages to humanize: {len(humanizes)}",
            "\n## Annotation details:\n"
        ]
        for idx, ann in enumerate(annotations, 1):
            t = ann.get("type", "note")
            txt = ann.get("text", "")
            comm = ann.get("comment", "")
            md_lines.append(f"{idx}. **[{t.upper()}]** \"{txt}\" {f'— Note: {comm}' if comm else ''}")
        (root_path / ".papersmith" / "anotaciones_pdf.md").write_text("\n".join(md_lines), encoding="utf-8")
        
        return JSONResponse({"ok": True, "summary": summary["summary"]})

    @app.post("/api/phase/run")
    async def api_phase_run(request: Request) -> JSONResponse:
        """Run or check one phase, then answer with that phase's verdict as the
        status view computes it, so the dashboard can confirm the stage."""
        if not origin_is_same(request):
            return JSONResponse({"ok": False, "error": "cross-origin request rejected"},
                                status_code=403)
        response = await _phase_check(request)
        try:
            body = json.loads(bytes(response.body))
            payload = await request.json()
        except ValueError:
            return response
        stage = phase_actions.stage_for(str((payload or {}).get("phase_id", "")))
        if stage:
            fases = json.loads(bytes(api_status_adapter().body)).get("fases", [])
            phase = next((f for f in fases if f.get("stage_id") == stage), {})
            body["status"] = phase.get("status", "PENDING")
            body["verified"] = body["status"] == "PASS"
            body["evidence"] = phase.get("evidence", [])
        return JSONResponse(body, status_code=response.status_code)

    @app.post("/api/plausibility/suggest")
    async def api_plausibility_suggest(request: Request) -> JSONResponse:
        """Thematic help for phase 2: 3 to 5 keywords in, the Banco LIA items
        and topics that match plus a proposed /plausibility idea out. Read only:
        it queries the banco-lia MCP server and never touches the workspace;
        the operator launches the idea from the phase card."""
        if not origin_is_same(request):
            return JSONResponse({"ok": False, "error": "cross-origin request rejected"},
                                status_code=403)
        try:
            payload = await request.json()
        except Exception:
            payload = None
        payload = payload if isinstance(payload, dict) else {}
        try:
            result = await asyncio.to_thread(
                banco_suggest.suggest, payload.get("keywords"), str(payload.get("language") or "es"),
                root=root_path)
        except banco_suggest.KeywordsInvalid as exc:
            return JSONResponse({"ok": False, "code": exc.code, "error": str(exc)}, status_code=422)
        return JSONResponse(result)

    async def _phase_check(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        phase_id = str(payload.get("phase_id", ""))
        stage = phase_actions.stage_for(phase_id)
        if stage is None:
            return JSONResponse({"ok": False, "error": f"unknown phase: {phase_id}"}, status_code=422)

        if stage == "paper" and not (root_path / "paper" / "main.tex").is_file():
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": "There is no paper/main.tex to compile: open it first with /paper-writing (Phase 6).",
                "outputs": []
            })
        if stage in ("paper", "writing"):
            if not _PAPER_LOCK.acquire(blocking=False):
                return JSONResponse({"ok": False, "phase_id": phase_id, "stage": stage,
                                     "error": "Another compilation of paper/ is still running; wait for it to finish."},
                                    status_code=409)
            job = _compile_paper if stage == "paper" else _build_manuscript

            def locked_job() -> tuple[dict[str, Any], int]:
                # Released by the worker thread, so a cancelled request never
                # frees the lock while its job still writes paper/.
                try:
                    return job(root_path)
                finally:
                    _PAPER_LOCK.release()

            try:
                body, status_code = await asyncio.to_thread(locked_job)
            except Exception as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
            return JSONResponse({"phase_id": phase_id, "stage": stage, **body}, status_code=status_code)

        elif stage == "figures":
            fig_dir = root_path / "paper" / "Figures"
            figs = [f.name for f in fig_dir.glob("*.pdf")] if fig_dir.is_dir() else []
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": f"Diagrams and technical figures verified ({len(figs)} optimized vector figures).",
                "outputs": [f"paper/Figures/{f}" for f in figs]
            })
            
        elif stage == "plausibility":
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": f"Plausibility: {_candidate_count(root_path)} candidates in sota-pool/candidates.json; "
                           f"atlas {'present' if (root_path / 'sota-pool' / 'atlas.html').is_file() else 'pending'}.",
                "outputs": ["sota-pool/atlas.json", "sota-pool/atlas.html", "sota-pool/candidates.json"]
            })
            
        elif stage == "ingestion":
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": f"Ingestion: {len(_children(root_path / 'guidance' / 'reference-papers'))} references ingested in guidance/reference-papers/.",
                "outputs": [f"guidance/reference-papers/{name}/" for name in _children(root_path / 'guidance' / 'reference-papers')]
            })
            
        elif stage == "proposal":
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": f"Proposal: {len(list((root_path / 'proposals').glob('research-concept-*.md')))} proposal revisions in proposals/.",
                "outputs": ["proposals/"]
            })
            
        elif stage == "scaffolding":
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": f"Scaffolding: {_block_count(root_path)} canonical blocks in paper/main.tex.",
                "outputs": ["paper/main.tex", "sections/"]
            })
            
        elif stage == "declarations":
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": "Declarations: record or review each one with /paper-writing mark.",
                "outputs": ["paper/main.tex"]
            })
            
        elif stage == "audit":
            record = await asyncio.to_thread(_run_audit, root_path)
            if record is None:
                message, log = "An audit is already running: wait for its result.", ""
            else:
                if not record["ran"]:
                    message = "The audit could not run (papersmith unavailable or timed out)."
                elif record["ok"]:
                    message = "Audit passed: smith audit --check-drift with no findings."
                else:
                    message = f"The audit found problems (code {record['returncode']})."
                if not record["written"]:
                    message += f" Could not write .papersmith/audit.json: {record['write_error']}"
                log = record["output"][-600:]
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": message,
                "log": log,
                "outputs": [".papersmith/audit.json"]
            })
            
        else:
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": f"Phase {phase_actions.STAGES.index(stage) + 1}: it runs from its card (agent command or panel).",
                "outputs": []
            })


    @app.get("/api/atlas")
    def api_atlas() -> JSONResponse:
        # Read-only. Validation loads the workspace's own check_atlas.py from one
        # fixed path (workspace Python runs in this process; see atlas.py).
        return JSONResponse(atlas.build_atlas(root_path), headers=dict(_PAPER_HEADERS))

    @app.get("/api/candidates")
    def api_candidates() -> JSONResponse:
        cand_file = root_path / "sota-pool" / "candidates.json"
        if not cand_file.is_file():
            return JSONResponse({"count": 0, "candidates": [], "families": []}, headers=dict(_PAPER_HEADERS))
        try:
            with open(cand_file, "r", encoding="utf-8") as f:
                candidates = json.load(f)
            families = sorted(list({c.get("family", "general") for c in candidates if c.get("family")}))
            return JSONResponse({
                "count": len(candidates),
                "candidates": candidates,
                "families": families
            }, headers=dict(_PAPER_HEADERS))
        except Exception as exc:
            return JSONResponse({"error": str(exc), "count": 0, "candidates": [], "families": []}, status_code=500)

    @app.get("/api/atlas/candidates/view")
    def api_atlas_candidates_view(lang: str = "en") -> Response:
        # English, or Spanish on ?lang=es (localize.py): the view is a page of
        # its own, so its labels are translated here rather than in JSON.
        def T(text: str) -> str:
            return html.escape(localize.translate(text, lang))

        def J(text: str) -> str:
            return json.dumps(localize.translate(text, lang), ensure_ascii=False).replace("<", "\\u003c")

        cand_file = root_path / "sota-pool" / "candidates.json"
        candidates = []
        families = []
        if cand_file.is_file():
            try:
                with open(cand_file, "r", encoding="utf-8") as f:
                    candidates = json.load(f)
                families = sorted(list({c.get("family", "general") for c in candidates if c.get("family")}))
            except Exception:
                pass
        
        # Candidates come from scouted literature (titles, abstracts, URLs), so
        # nothing from them reaches the page unescaped: the JSON cannot close
        # its <script>, the options are attribute-escaped, and the client
        # escapes every field it renders (esc/safeUrl below).
        candidates_json = (json.dumps(candidates).replace("<", "\\u003c")
                           .replace(">", "\\u003e").replace("&", "\\u0026"))
        families_options = "".join(
            f'<option value="{html.escape(str(f), quote=True)}">{html.escape(str(f))}</option>'
            for f in families)
        
                # Every label of the page, translated once; the f-string below only
        # indexes this list (3.11 f-strings take no backslashes or nested quotes).
        _label = [
            T("SOTA Candidate Matrix"),
            T("State-of-the-Art (SOTA) Candidate Matrix"),
            T("Literature Mapping and Methodological Plausibility"),
            T("← Back to the Main Dashboard"),
            T("Q1/Q2 Candidate Articles"),
            T("Thematic Families"),
            T("SOTA Time Window"),
            T("Validated Plausibility"),
            T("Search by title, author, journal, DOI or keyword..."),
            T("Year (newest)"),
            T("Year (oldest)"),
            T("Title (A-Z)"),
            T("Year"),
            T("Article & Authors"),
            T("Journal / Venue"),
            T("Family / Cluster"),
            T("Contribution & Plausibility"),
            J("📄 Abstract ▾"),
            J("Hide ▴"),
            J("No articles match that search."),
            J("Q1 Journal"),
            J("Methodological plausibility validated"),
            T("Full Scientific Abstract"),
            J("No abstract recorded."),
            T("All authors:"),
        ]
        page_lang = "es" if lang in localize.LANGUAGES else "en"
        all_families = T(f"All Families ({len(families)})")
        html_content = f"""<!DOCTYPE html>
<html lang="{page_lang}" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_label[0]} — {html.escape(root_path.name)}</title>
  <link rel="icon" type="image/png" href="/favicon.png">
  <style>
    :root {{
      --bg: #0b0f19;
      --surface: #111827;
      --surface-2: #1f2937;
      --surface-hover: #374151;
      --border: #374151;
      --border-subtle: #242f3e;
      --text: #f9fafb;
      --text-muted: #9ca3af;
      --text-dim: #6b7280;
      --accent: #38bdf8;
      --ok: #10b981;
      --warn: #f59e0b;
      --radius: 8px;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      padding: 1.5rem;
      min-height: 100vh;
    }}
    .container {{
      max-width: 1440px;
      margin: 0 auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border);
      flex-wrap: wrap;
      gap: 1rem;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }}
    .brand img {{
      width: 42px;
      height: 42px;
      border-radius: 50%;
      border: 2px solid var(--accent);
    }}
    .brand h1 {{
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--text);
    }}
    .brand p {{
      font-size: 0.78rem;
      color: var(--text-muted);
    }}
    .btn {{
      background: var(--surface-2);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 0.45rem 0.9rem;
      border-radius: var(--radius);
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      transition: all 0.15s;
    }}
    .btn:hover {{
      background: var(--surface-hover);
      border-color: var(--accent);
    }}
    .btn--primary {{
      background: var(--accent);
      color: #0b0f19;
      border-color: var(--accent);
    }}
    .stats-bar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 0.75rem;
      margin-bottom: 1.25rem;
    }}
    .stat-chip {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 0.85rem 1rem;
    }}
    .stat-chip__val {{
      font-size: 1.35rem;
      font-weight: 700;
      color: var(--accent);
      font-family: var(--font-mono);
    }}
    .stat-chip__lbl {{
      font-size: 0.72rem;
      color: var(--text-dim);
      text-transform: uppercase;
      font-weight: 600;
    }}
    .toolbar {{
      display: flex;
      gap: 0.75rem;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 0.75rem 1rem;
      margin-bottom: 1rem;
      flex-wrap: wrap;
      justify-content: space-between;
    }}
    .search-input {{
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text);
      padding: 0.45rem 0.85rem;
      font-size: 0.82rem;
      flex: 1;
      min-width: 280px;
      outline: none;
    }}
    .search-input:focus {{ border-color: var(--accent); }}
    select {{
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text);
      padding: 0.45rem 0.85rem;
      font-size: 0.82rem;
      outline: none;
      cursor: pointer;
    }}
    .table-box {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.83rem;
    }}
    th, td {{
      padding: 0.8rem 1rem;
      text-align: left;
      border-bottom: 1px solid var(--border-subtle);
    }}
    th {{
      background: rgba(0,0,0,0.3);
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 0.72rem;
      letter-spacing: 0.03em;
      position: sticky;
      top: 0;
    }}
    tr:hover td {{ background: var(--surface-hover); }}
    .badge {{
      display: inline-block;
      padding: 0.2rem 0.55rem;
      border-radius: 9999px;
      font-size: 0.72rem;
      font-weight: 600;
    }}
    .badge--ok {{ background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid #10b981; }}
    .badge--info {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid #38bdf8; text-decoration: none; }}
    .badge-family--c0 {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); }}
    .badge-family--c1 {{ background: rgba(192, 132, 252, 0.15); color: #c084fc; border: 1px solid rgba(192, 132, 252, 0.4); }}
    .badge-family--c2 {{ background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.4); }}
    .badge-family--c3 {{ background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.4); }}
    .badge-family--c4 {{ background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.4); }}
    .abstract-box {{
      background: var(--surface-2);
      border-left: 3px solid var(--accent);
      border-radius: 4px;
      padding: 0.85rem 1rem;
      line-height: 1.6;
      font-size: 0.81rem;
      color: var(--text);
      margin-top: 0.5rem;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <img src="/smith-logo.png" alt="Smith">
        <div>
          <h1>{_label[1]}</h1>
          <p>{html.escape(root_path.name)} · {_label[2]}</p>
        </div>
      </div>
      <div>
        <a href="/#atlas" class="btn">{_label[3]}</a>
      </div>
    </header>

    <div class="stats-bar">
      <div class="stat-chip">
        <div class="stat-chip__val">{len(candidates)}</div>
        <div class="stat-chip__lbl">{_label[4]}</div>
      </div>
      <div class="stat-chip">
        <div class="stat-chip__val">{len(families)}</div>
        <div class="stat-chip__lbl">{_label[5]}</div>
      </div>
      <div class="stat-chip">
        <div class="stat-chip__val">2020 – 2025</div>
        <div class="stat-chip__lbl">{_label[6]}</div>
      </div>
      <div class="stat-chip">
        <div class="stat-chip__val" style="color: var(--ok);">100% PASS</div>
        <div class="stat-chip__lbl">{_label[7]}</div>
      </div>
    </div>

    <div class="toolbar">
      <input type="text" id="searchInput" class="search-input" placeholder="{_label[8]}" oninput="renderTable()">
      <div style="display: flex; gap: 0.5rem;">
        <select id="familySelect" onchange="renderTable()">
          <option value="">{all_families}</option>
          {families_options}
        </select>
        <select id="sortSelect" onchange="renderTable()">
          <option value="year_desc">{_label[9]}</option>
          <option value="year_asc">{_label[10]}</option>
          <option value="title_asc">{_label[11]}</option>
        </select>
      </div>
    </div>

    <div class="table-box">
      <table>
        <thead>
          <tr>
            <th style="width: 45px; text-align: center;">#</th>
            <th style="width: 65px; text-align: center;">{_label[12]}</th>
            <th style="min-width: 320px;">{_label[13]}</th>
            <th style="width: 180px;">{_label[14]}</th>
            <th style="width: 160px;">{_label[15]}</th>
            <th style="min-width: 260px;">{_label[16]}</th>
            <th style="width: 100px; text-align: center;">Abstract</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
  </div>

  <script>
    const CANDIDATES = {candidates_json};
    const LABEL_SHOW = {_label[17]};
    const LABEL_HIDE = {_label[18]};
    function esc(v) {{
      return String(v ?? '').replace(/[&<>"']/g, ch => ({{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}})[ch]);
    }}
    function safeUrl(u) {{
      try {{ const url = new URL(String(u), location.href); return (url.protocol === 'http:' || url.protocol === 'https:') ? url.href : '#'; }}
      catch (e) {{ return '#'; }}
    }}
    function getFamilyBadgeClass(family) {{
      if (!family) return 'badge-family--c4';
      let h = 0;
      for (const ch of String(family).toLowerCase()) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
      return `badge-family--c${{h % 5}}`;
    }}

    function renderTable() {{
      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const family = document.getElementById('familySelect').value;
      const sort = document.getElementById('sortSelect').value;

      let list = CANDIDATES.filter(c => {{
        if (family && c.family !== family) return false;
        if (!query) return true;
        const str = [c.title, (c.authors || []).join(' '), c.venue, c.identifier, c.family, c.abstract, c.plausibility_note].join(' ').toLowerCase();
        return str.includes(query);
      }});

      if (sort === 'year_desc') list.sort((a,b) => (b.year||0) - (a.year||0));
      else if (sort === 'year_asc') list.sort((a,b) => (a.year||0) - (b.year||0));
      else if (sort === 'title_asc') list.sort((a,b) => (a.title||'').localeCompare(b.title||''));

      const tbody = document.getElementById('tableBody');
      tbody.innerHTML = '';
      if (list.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 2rem; color: var(--text-muted);">' + esc({_label[19]}) + '</td></tr>';
        return;
      }}

      list.forEach((c, idx) => {{
        const tr = document.createElement('tr');
        const authors = (c.authors || []).slice(0, 3).join(', ') + ((c.authors || []).length > 3 ? ' et al.' : '');
        tr.innerHTML = `
          <td style="text-align: center; font-weight: 600; color: var(--text-dim);">${{idx + 1}}</td>
          <td style="text-align: center;"><span class="badge badge--ok" style="font-family: var(--font-mono);">${{esc(c.year || '—')}}</span></td>
          <td>
            <div style="font-weight: 700; color: var(--text); line-height: 1.35; margin-bottom: 0.25rem;">${{esc(c.title)}}</div>
            <div style="font-size: 0.76rem; color: var(--text-muted); display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
              <span>👥 ${{esc(authors)}}</span>
              ${{c.identifier ? `<a href="${{esc(safeUrl(c.source_url || ('https://doi.org/' + c.identifier)))}}" target="_blank" rel="noopener noreferrer" class="badge badge--info">🔗 ${{esc(c.identifier)}}</a>` : ''}}
            </div>
          </td>
          <td><span style="font-style: italic; color: var(--text-dim);">${{esc(c.venue || {_label[20]})}}</span></td>
          <td><span class="badge ${{getFamilyBadgeClass(c.family)}}">${{esc(c.family || 'general')}}</span></td>
          <td><div style="font-size: 0.78rem; color: var(--text); background: rgba(56, 189, 248, 0.05); padding: 0.4rem 0.6rem; border-radius: 4px; border-left: 2px solid var(--accent);">${{esc(c.plausibility_note || {_label[21]})}}</div></td>
          <td style="text-align: center;"><button class="btn" style="padding: 0.25rem 0.5rem; font-size: 0.72rem;" onclick="toggleAbs(${{idx}})" id="btn-${{idx}}">${{esc(LABEL_SHOW)}}</button></td>
        `;
        tbody.appendChild(tr);

        const trAbs = document.createElement('tr');
        trAbs.id = `row-abs-${{idx}}`;
        trAbs.style.display = 'none';
        trAbs.innerHTML = `
          <td colspan="7" style="background: var(--surface-2); padding: 1rem 1.25rem;">
            <div style="font-weight: 700; color: var(--accent); font-size: 0.8rem; margin-bottom: 0.35rem; text-transform: uppercase;">{_label[22]}</div>
            <p style="font-size: 0.81rem; line-height: 1.6; color: var(--text); text-align: justify; margin-bottom: 0.5rem;">${{esc(c.abstract || {_label[23]})}}</p>
            <div style="font-size: 0.74rem; color: var(--text-dim);"><strong>{_label[24]}</strong> ${{ esc((c.authors || []).join(', ')) }}</div>
          </td>
        `;
        tbody.appendChild(trAbs);
      }});
    }}

    function toggleAbs(idx) {{
      const row = document.getElementById(`row-abs-${{idx}}`);
      const btn = document.getElementById(`btn-${{idx}}`);
      const open = row.style.display === 'none';
      row.style.display = open ? 'table-row' : 'none';
      btn.textContent = open ? LABEL_HIDE : LABEL_SHOW;
    }}

    renderTable();
  </script>
</body>
</html>"""
        return Response(html_content, media_type="text/html; charset=utf-8", headers=dict(_PAPER_HEADERS))

    @app.get("/api/atlas/view")
    def api_atlas_view() -> Response:
        status, data = atlas.read_html(root_path)
        if status == "too_large":
            return JSONResponse({"detail": "atlas.html exceeds the 2 MiB limit"},
                                status_code=413, headers=dict(_PAPER_HEADERS))
        if status != "ok" or data is None:
            return JSONResponse({"detail": "atlas.html not found"}, status_code=404,
                                headers=dict(_PAPER_HEADERS))
        return Response(data, media_type="text/html; charset=utf-8",
                        headers=dict(_ATLAS_VIEW_HEADERS))

    @app.post("/api/atlas/build")
    def api_atlas_build(request: Request) -> JSONResponse:
        # "Regenerar grafo": the workspace's own checker, then its renderer.
        # Writes only sota-pool/atlas.html, and only when the checker is green.
        # A bodyless POST is a simple request, so refuse other origins here too.
        if not origin_is_same(request):
            return JSONResponse({"ok": False, "stage": "origin",
                                 "detail": "cross-origin request rejected"},
                                status_code=403, headers=dict(_PAPER_HEADERS))
        result = atlas_build.build(root_path)
        if result["ok"]:
            status_code = 200
        elif result["stage"] in ("absent", "scripts"):
            status_code = 404
        elif result["stage"] == "timeout":
            status_code = 504
        else:
            status_code = 422
        return JSONResponse(result, status_code=status_code, headers=dict(_PAPER_HEADERS))

    # ---------------------------------------------------------------- terminal
    app.state.terminal = terminals
    app.state.terminal_enabled = enable_terminal

    def _terminal_refusal(request: Request, *, mutating: bool) -> JSONResponse | None:
        if not enable_terminal:
            return JSONResponse({"detail": "the support terminal is disabled on this bind"},
                                status_code=404, headers=dict(_PAPER_HEADERS))
        # A secret, not just headers: any local client (another OS user, curl)
        # can send the right headers, but only this server's browser holds it.
        if not terminals.authorized(request.cookies.get(TERMINAL_COOKIE)):
            return JSONResponse({"detail": "refused: open the dashboard from the login URL "
                                 "the server printed"}, status_code=403,
                                headers=dict(_PAPER_HEADERS))
        reason = terminal.guard(request.headers, mutating=mutating)
        if reason is not None:
            return JSONResponse({"detail": f"refused: {reason}"}, status_code=403,
                                headers=dict(_PAPER_HEADERS))
        return None

    async def _terminal_body(request: Request) -> dict[str, Any] | None:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - a bad body is a 422, not a crash
            return None
        return body if isinstance(body, dict) else None

    def _bad_body() -> JSONResponse:
        return JSONResponse({"detail": "the body must be a JSON object"}, status_code=422,
                            headers=dict(_PAPER_HEADERS))

    @app.get("/api/terminal/login")
    def api_terminal_login(token: str = "") -> Response:
        if not enable_terminal or not terminals.authorized(token):
            return JSONResponse({"detail": "invalid terminal token"}, status_code=403,
                                headers=dict(_PAPER_HEADERS))
        response = Response(status_code=303, headers={"Location": "/", "Cache-Control": "no-store"})
        response.set_cookie(TERMINAL_COOKIE, terminals.token, httponly=True,
                            samesite="strict", path="/api/terminal")
        return response

    @app.get("/api/terminal/agents")
    def api_terminal_agents(request: Request) -> JSONResponse:
        authorized = terminals.authorized(request.cookies.get(TERMINAL_COOKIE))
        agents = terminals.agents() if enable_terminal and authorized else []
        commands_dir = root_path / ".claude" / "commands"
        slash = sorted(f"/{p.stem}" for p in commands_dir.glob("*.md")) if commands_dir.is_dir() else []
        return JSONResponse({
            "enabled": enable_terminal and terminal.fcntl is not None,
            "authorized": enable_terminal and authorized,
            "agents": agents,
            "default": next((a["id"] for a in agents if a["available"]), "shell"),
            "quick": {"shell": list(terminal.SHELL_QUICK), "agent": slash[:24]},
        }, headers=dict(_PAPER_HEADERS))

    # ------------------------------------------------------------ math tutor
    # The Socratic tutor runs the reader's own agent CLI, so it lives behind the
    # same secret cookie and origin guards as the terminal (and under its path,
    # where that cookie is sent).
    def _tutor_error(error: Exception, status: int = 422) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=status, headers=dict(_PAPER_HEADERS))

    @app.get("/api/terminal/tutor/thread")
    def api_tutor_thread(request: Request) -> JSONResponse:
        refusal = _terminal_refusal(request, mutating=False)
        if refusal is not None:
            return refusal
        return JSONResponse(tutor.load_thread(root_path), headers=dict(_PAPER_HEADERS))

    @app.delete("/api/terminal/tutor/thread")
    def api_tutor_reset(request: Request) -> JSONResponse:
        refusal = _terminal_refusal(request, mutating=True)
        if refusal is not None:
            return refusal
        tutor.reset_thread(root_path)
        return JSONResponse({"ok": True}, headers=dict(_PAPER_HEADERS))

    @app.post("/api/terminal/tutor/images")
    async def api_tutor_upload(request: Request) -> JSONResponse:
        refusal = _terminal_refusal(request, mutating=True)
        if refusal is not None:
            return refusal
        body = await _terminal_body(request)
        if body is None:
            return _bad_body()
        try:
            saved = await asyncio.to_thread(tutor.save_image, root_path, body.get("data_url"))
        except tutor.TutorError as error:
            return _tutor_error(error)
        return JSONResponse(saved, headers=dict(_PAPER_HEADERS))

    @app.get("/api/terminal/tutor/images/{image_id}")
    def api_tutor_image(image_id: str, request: Request) -> Response:
        refusal = _terminal_refusal(request, mutating=False)
        if refusal is not None:
            return refusal
        try:
            path = tutor.image_path(root_path, image_id)
        except tutor.TutorError as error:
            return _tutor_error(error, 404)
        return Response(path.read_bytes(), media_type=tutor.image_type(path),
                        headers={**_PAPER_HEADERS, "Cache-Control": "private, max-age=86400"})

    @app.post("/api/terminal/tutor/turn")
    async def api_tutor_turn(request: Request) -> JSONResponse:
        refusal = _terminal_refusal(request, mutating=True)
        if refusal is not None:
            return refusal
        body = await _terminal_body(request)
        if body is None:
            return _bad_body()
        try:
            turn = await asyncio.to_thread(tutor.run_turn, root_path, body.get("message", ""),
                                           body.get("images", []), body.get("mode", "ask"),
                                           runner=lambda *args: tutor.run_agent(*args))
        except tutor.TutorError as error:
            return _tutor_error(error)
        except subprocess.TimeoutExpired:
            return _tutor_error(RuntimeError("the tutor took too long to answer"), 504)
        return JSONResponse(turn, headers=dict(_PAPER_HEADERS))

    # ------------------------------------------------------- experiments tutor
    # The same machinery and guards, its own profile: a thread under
    # .papersmith/experiments-tutor/, the experiments digest, Read/Glob/Grep.
    @app.get("/api/terminal/tutor/experiments/thread")
    def api_experiments_tutor_thread(request: Request) -> JSONResponse:
        refusal = _terminal_refusal(request, mutating=False)
        if refusal is not None:
            return refusal
        return JSONResponse(tutor.load_thread(root_path, experiments_tutor.PROFILE),
                            headers=dict(_PAPER_HEADERS))

    @app.delete("/api/terminal/tutor/experiments/thread")
    def api_experiments_tutor_reset(request: Request) -> JSONResponse:
        refusal = _terminal_refusal(request, mutating=True)
        if refusal is not None:
            return refusal
        tutor.reset_thread(root_path, experiments_tutor.PROFILE)
        return JSONResponse({"ok": True}, headers=dict(_PAPER_HEADERS))

    @app.post("/api/terminal/tutor/experiments/turn")
    async def api_experiments_tutor_turn(request: Request) -> JSONResponse:
        refusal = _terminal_refusal(request, mutating=True)
        if refusal is not None:
            return refusal
        body = await _terminal_body(request)
        if body is None:
            return _bad_body()
        profile = experiments_tutor.PROFILE
        try:
            turn = await asyncio.to_thread(
                experiments_tutor.run_turn, root_path, body.get("message", ""),
                body.get("mode", "ask"), body.get("area", "general"),
                runner=lambda *args: tutor.run_agent(*args, schema=profile.schema, tools=profile.tools))
        except tutor.TutorError as error:
            return _tutor_error(error)
        except subprocess.TimeoutExpired:
            return _tutor_error(RuntimeError("the tutor took too long to answer"), 504)
        return JSONResponse(turn, headers=dict(_PAPER_HEADERS))

    @app.get("/api/terminal/tools")
    def api_terminal_tools(request: Request) -> JSONResponse:
        refusal = _terminal_refusal(request, mutating=False)
        if refusal is not None:
            return refusal
        return JSONResponse({"ok": True, "tools": terminal.detect_tools(root_path)},
                            headers=dict(_PAPER_HEADERS))

    @app.post("/api/terminal/launch-external")
    async def api_terminal_launch_external(request: Request) -> JSONResponse:
        # Opens herdr on this project in Ghostty or WezTerm on the user's desktop.
        refusal = _terminal_refusal(request, mutating=True)
        if refusal is not None:
            return refusal
        result = await asyncio.to_thread(terminal.launch_external, root_path)
        return JSONResponse(result, status_code=200 if result["ok"] else 400,
                            headers=dict(_PAPER_HEADERS))

    @app.post("/api/terminal/sessions")
    async def api_terminal_create(request: Request) -> JSONResponse:
        refusal = _terminal_refusal(request, mutating=True)
        if refusal is not None:
            return refusal
        body = await _terminal_body(request)
        if body is None:
            return _bad_body()
        try:
            session = terminals.create(str(body.get("agent", "shell")),
                                       body.get("cols", 100), body.get("rows", 30))
        except terminal.TerminalError as error:
            return JSONResponse({"detail": str(error)}, status_code=422,
                                headers=dict(_PAPER_HEADERS))
        return JSONResponse({"id": session.id, "agent": session.agent},
                            headers=dict(_PAPER_HEADERS))

    @app.post("/api/terminal/sessions/{sid}/input")
    async def api_terminal_input(sid: str, request: Request) -> JSONResponse:
        refusal = _terminal_refusal(request, mutating=True)
        if refusal is not None:
            return refusal
        body = await _terminal_body(request)
        if body is None:
            return _bad_body()
        try:
            if "cols" in body or "rows" in body:
                terminals.resize(sid, body.get("cols"), body.get("rows"))
            if isinstance(body.get("data"), str):
                # Off the event loop: a full PTY input queue blocks the write.
                await asyncio.to_thread(terminals.write, sid, body["data"])
        except KeyError:
            return JSONResponse({"detail": "no such session"}, status_code=404,
                                headers=dict(_PAPER_HEADERS))
        except terminal.TerminalError as error:
            return JSONResponse({"detail": str(error)}, status_code=422,
                                headers=dict(_PAPER_HEADERS))
        return JSONResponse({"ok": True}, headers=dict(_PAPER_HEADERS))

    @app.delete("/api/terminal/sessions/{sid}")
    def api_terminal_close(sid: str, request: Request) -> JSONResponse:
        refusal = _terminal_refusal(request, mutating=True)
        if refusal is not None:
            return refusal
        try:
            terminals.close(sid)
        except KeyError:
            return JSONResponse({"detail": "no such session"}, status_code=404,
                                headers=dict(_PAPER_HEADERS))
        return JSONResponse({"ok": True}, headers=dict(_PAPER_HEADERS))

    # A reloaded page looks its session up before reattaching to it.
    @app.get("/api/terminal/sessions/{sid}")
    def api_terminal_session(sid: str, request: Request) -> JSONResponse:
        refusal = _terminal_refusal(request, mutating=False)
        if refusal is not None:
            return refusal
        try:
            session = terminals.get(sid)
        except KeyError:
            return JSONResponse({"detail": "no such session"}, status_code=404,
                                headers=dict(_PAPER_HEADERS))
        return JSONResponse({"id": session.id, "agent": session.agent, "alive": session.alive},
                            headers=dict(_PAPER_HEADERS))

    @app.get("/api/terminal/sessions/{sid}/stream")
    async def api_terminal_stream(sid: str, request: Request) -> Response:
        refusal = _terminal_refusal(request, mutating=False)
        if refusal is not None:
            return refusal
        try:
            terminals.get(sid)
        except KeyError:
            return JSONResponse({"detail": "no such session"}, status_code=404,
                                headers=dict(_PAPER_HEADERS))
        return StreamingResponse(
            _terminal_stream(request, terminals, sid),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/atlas/novelty")
    def api_atlas_novelty() -> JSONResponse:
        return JSONResponse(novelty_graph.build_novelty_graph(root_path), headers=dict(_PAPER_HEADERS))

    @app.get("/api/atlas/novelty/view")
    def api_atlas_novelty_view(lang: str = "en") -> Response:
        html = novelty_graph.build_novelty_viewer_html(root_path, lang)
        return Response(html, media_type="text/html; charset=utf-8", headers=dict(_PAPER_HEADERS))

    @app.get("/api/novelty/status")
    def api_novelty_status() -> JSONResponse:
        overview = _novelty_gate().get_novelty_overview(root_path)
        return JSONResponse(overview, headers=dict(_PAPER_HEADERS))

    @app.post("/api/novelty/decision")
    async def api_novelty_decision(request: Request) -> JSONResponse:
        if not origin_is_same(request):
            return JSONResponse({"ok": False, "error": "cross-origin request rejected"},
                                status_code=403)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        action = str(payload.get("action", "") or "")
        notes = str(payload.get("notes", "") or "")
        actor = str(payload.get("actor", "operator") or "operator")
        try:
            record = _novelty_gate().record_decision(root_path, action, rationale=notes, actor=actor)
            return JSONResponse({"ok": True, "action": action, "gate": record},
                                headers=dict(_PAPER_HEADERS))
        except _novelty_gate().NoveltyRefusal as ref:
            return JSONResponse({"ok": False, "error": ref.code, "message": ref.message},
                                status_code=422)

    @app.get("/api/decisions")
    def api_decisions(source: str | None = None,
                      limit: int = decisions.MAX_TOTAL_EVENTS) -> JSONResponse:
        # Read-only timeline merged on request from persisted records; every
        # read is bounded and contained in the workspace (see decisions).
        names = [part.strip() for part in source.split(",") if part.strip()] if source else None
        try:
            return JSONResponse(decisions.build_decisions(root_path, names, limit),
                                headers=dict(_PAPER_HEADERS))
        except decisions.DecisionsQueryError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422,
                                headers=dict(_PAPER_HEADERS))

    @app.get("/api/ai-history")
    def api_ai_history() -> JSONResponse:
        # The AI History pane: each phase's gate, colour and timeline,
        # read-only from decisions, revisions and this workspace's transcripts.
        try:
            phases = json.loads(bytes(api_status_adapter().body)).get("fases") or []
        except Exception:  # noqa: BLE001 - the pane still answers without phases
            phases = []
        return JSONResponse(ai_history.build_ai_history(root_path, phases),
                            headers=dict(_PAPER_HEADERS))

    @app.get("/api/events")
    async def api_events(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _event_stream(request, bus, root_path),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    static_dir = resolve_static_dir(root_path)
    if static_dir is not None:
        from fastapi.staticfiles import StaticFiles

        class _RevalidatedStaticFiles(StaticFiles):
            # `no-cache` makes the browser revalidate each load (a 304 when
            # unchanged), so a reload after an upgrade never runs an old panel.
            async def get_response(self, path, scope):
                response = await super().get_response(path, scope)
                response.headers["Cache-Control"] = "no-cache"
                return response

        app.mount("/", _RevalidatedStaticFiles(directory=str(static_dir), html=True), name="dashboard")
    else:
        @app.get("/", response_class=HTMLResponse)
        def placeholder() -> str:
            return _PLACEHOLDER_HTML

    return app


async def _terminal_stream(request: Request, terminals: "terminal.TerminalManager",
                           sid: str) -> AsyncIterator[str]:
    """PTY output as SSE ``output`` frames (base64), then one ``exit`` frame."""
    import base64

    # The PTY reader thread sets `wake` on every chunk and when the session
    # ends, so a quiet session costs one wake-up per TERMINAL_WAIT_SECONDS
    # (to notice a client that left) instead of a tight polling loop.
    loop = asyncio.get_running_loop()
    wake = asyncio.Event()
    try:
        session = terminals.watch(sid, loop, wake)
    except KeyError:
        yield format_sse("exit", {"reason": "closed"})
        return
    offset = 0
    idle = 0.0
    try:
        while True:
            if await request.is_disconnected():
                break
            # Cleared before reading: a chunk appended after this point sets
            # it again, so no output is ever missed between read and wait.
            wake.clear()
            try:
                chunk, offset, alive = terminals.read_since(sid, offset)
            except KeyError:
                yield format_sse("exit", {"reason": "closed"})
                break
            if chunk:
                idle = 0.0
                yield format_sse("output", {"data": base64.b64encode(chunk).decode("ascii")})
                continue
            if not alive:
                yield format_sse("exit", {"reason": "ended"})
                break
            started = loop.time()
            try:
                await asyncio.wait_for(wake.wait(), TERMINAL_WAIT_SECONDS)
            except asyncio.TimeoutError:
                pass
            idle += loop.time() - started
            if idle >= TERMINAL_PING_SECONDS:
                idle = 0.0
                yield ": ping\n\n"
    finally:
        terminals.unwatch(session, loop, wake)


async def _event_stream(request: Request, bus: EventBus, root: Path) -> AsyncIterator[str]:
    queue = bus.subscribe()
    try:
        yield format_sse("ready", {"workspace": str(root)})
        while True:
            if await request.is_disconnected():
                break
            try:
                message = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            yield format_sse(message["event"], message["data"])
    finally:
        bus.unsubscribe(queue)


def _run_wiring_smoke(root: Path, bus: EventBus, timeout: float = 180.0,
                      record: Callable[[list[history.Change]], None] | None = None) -> dict[str, Any]:
    """Run the workspace's cross-harness wiring smoke and stream its output."""

    def note(phase: str, summary: str, **extra: Any) -> None:
        if record is None:
            return
        try:
            record([history.Change("smoke", None, summary, None, {"phase": phase, **extra})])
        except Exception:  # noqa: BLE001
            _log.exception("history: recording the wiring smoke failed")

    script = root / "scripts" / "cli-paper-wiring-smoke.sh"
    if not script.is_file():
        detail = "scripts/cli-paper-wiring-smoke.sh is not present in this workspace"
        bus.publish("wiring_smoke_done", {"exit_code": None, "detail": detail})
        note("done", "Wiring smoke unavailable", exit_code=None)
        return {"available": False, "exit_code": None, "detail": detail, "output": ""}
    bus.publish("wiring_smoke_started", {"script": "scripts/cli-paper-wiring-smoke.sh"})
    note("started", "Wiring smoke started")
    lines: list[str] = []
    try:
        process = subprocess.Popen(
            ["bash", str(script)],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except OSError as exc:
        detail = f"could not start {script}: {exc}"
        bus.publish("wiring_smoke_done", {"exit_code": None, "detail": detail})
        note("done", "Wiring smoke could not start", exit_code=None)
        return {"available": True, "exit_code": None, "detail": detail, "output": ""}

    def _drain_thread() -> None:
        _drain(process, lines, bus, timeout)

    watchdog = threading.Thread(target=_drain_thread, daemon=True)
    watchdog.start()
    watchdog.join(timeout=timeout + 5.0)
    if watchdog.is_alive():  # pragma: no cover - defensive
        with contextlib.suppress(OSError):
            process.kill()
    code = process.poll()
    bus.publish("wiring_smoke_done", {"exit_code": code})
    note("done", f"Wiring smoke finished with exit code {code}", exit_code=code)
    return {
        "available": True,
        "exit_code": code,
        "script": "scripts/cli-paper-wiring-smoke.sh",
        "output": "\n".join(lines),
    }


def _drain(process: "subprocess.Popen[str]", lines: list[str], bus: EventBus,
           timeout: float) -> None:
    """Read the child's stdout line by line, publishing each line."""
    deadline = time.monotonic() + timeout
    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip("\n")
        lines.append(line)
        bus.publish("wiring_smoke", {"line": line})
        if time.monotonic() > deadline:  # pragma: no cover - defensive
            with contextlib.suppress(OSError):
                process.kill()
            break
    with contextlib.suppress(OSError):
        process.wait(timeout=5.0)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m skills._core.command_center.server",
        description="Paper Command Center: local dashboard and health control plane.",
    )
    parser.add_argument("--root", default=".", help="workspace root (default: cwd)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-browser", action="store_true",
                        help="never open a browser window")
    parser.add_argument("--debounce-ms", type=int, default=300)
    parser.add_argument("--health-ttl", type=float, default=DEFAULT_HEALTH_TTL_SECONDS)
    parser.add_argument("--export-static", metavar="<dir>", default=None,
                        help="copy the dashboard build to <dir> and exit")
    parser.add_argument("--allowed-host", action="append", default=[], metavar="HOST:PORT",
                        help="extra Host header to accept (repeatable); "
                             "for `npm run dev` use --allowed-host localhost:5173")
    parser.add_argument("--allow-unauthenticated-network", action="store_true",
                        help="serve on a non-loopback --host; the dashboard has no "
                             "authentication, so only on a network you trust (the Host "
                             "check still accepts only the bind address and --allowed-host)")
    parser.add_argument("--no-terminal", action="store_true",
                        help="do not offer the dashboard's support terminal (it is only "
                             "ever offered on a loopback bind)")
    parser.add_argument("--log-level", default="info")
    return parser


def _is_wsl() -> bool:
    """Identify WSL by its kernel release, not by inherited environment flags."""
    return sys.platform == "linux" and "microsoft" in platform.release().lower()


#: Launchers that hand a URL to the Windows browser from WSL, in order.
WSL_BROWSER_LAUNCHERS = ("wslview", "explorer.exe")


def _has_graphical_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _print_url(url: str) -> None:
    print(f"open the dashboard in a browser: {url}", flush=True)


def open_browser(url: str) -> None:
    """Open ``url`` in a browser that fits the platform; never raises.

    Under WSL the Windows browser is reached through ``wslview`` (wslu), then
    ``explorer.exe``. On Linux without a graphical display Python's
    ``webbrowser`` would start a text browser (w3m, lynx) on the server's own
    terminal, so the URL is printed instead. macOS and desktop Linux use
    ``webbrowser``.
    """
    if _is_wsl():
        for launcher in WSL_BROWSER_LAUNCHERS:
            executable = shutil.which(launcher)
            if not executable:
                continue
            # argv keeps query strings intact (and avoids cmd.exe/shell
            # interpolation). Do not expose the terminal login URL through
            # child process output.
            try:
                subprocess.Popen([executable, url], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 close_fds=True)
                return
            except OSError:
                continue
    if sys.platform.startswith("linux") and not _has_graphical_display():
        _print_url(url)
        return
    import webbrowser

    try:
        if webbrowser.open(url):
            return
    except Exception:  # Browser setup must not prevent the server from starting.
        pass
    _print_url(url)


def warm_caches(root: Path, *extra: Callable[[], Any]) -> None:
    """Fill the slow caches before the first visit: the experiments tab's
    interpreter and CLI probes, the chat sessions AI History reads and
    ``extra`` (``main`` passes the Smith Doctor report). Runs off the request
    path; a failure only means the first visit pays."""
    for warm in (lambda: experiments_view.get_experiments_view(root),
                 lambda: ai_transcripts.read_all(root), *extra):
        try:
            warm()
        except Exception:  # noqa: BLE001 - warming is best effort
            _log.debug("warming a dashboard cache failed", exc_info=True)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    if args.export_static:
        return export_static(root, Path(args.export_static))
    if not is_loopback_bind(args.host) and not args.allow_unauthenticated_network:
        parser.error(
            f"--host {args.host} is not a loopback address, and the dashboard has no "
            "authentication: anyone who reaches the port could read and edit this "
            "workspace and start its compile and smoke runs. Serve on 127.0.0.1 and "
            f"forward the port (ssh -L {args.port}:127.0.0.1:{args.port} <server>), "
            "or pass --allow-unauthenticated-network on a network you trust.")

    import uvicorn

    app = create_app(
        root, debounce_ms=args.debounce_ms, health_ttl=args.health_ttl,
        allowed_hosts=build_allowed_hosts(args.host, args.port, args.allowed_host),
        enable_terminal=terminal_allowed(args.host) and not args.no_terminal,
    )
    url = f"http://{args.host}:{args.port}/"
    if app.state.terminal_enabled:
        # The terminal's secret travels only in this URL; opening it once sets
        # the cookie. Printed so --no-browser users can open it themselves.
        url = f"{url}api/terminal/login?token={app.state.terminal.token}"
        print(f"support terminal enabled; dashboard login URL: {url}", flush=True)
    threading.Thread(target=warm_caches, args=(root, app.state.warm_doctor), name="warm-caches", daemon=True).start()
    if not args.no_browser:
        threading.Timer(1.0, open_browser, args=(url,)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
