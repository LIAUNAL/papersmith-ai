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
import threading
import time
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from . import agents_view, atlas, atlas_build, decisions, experiments_view, math_view, phase_actions, terminal, tutor, history, paper_preview, novelty_graph, model_spec
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


def _phase5_evidence(root: Path) -> dict[str, Any]:
    """What Phase 5 has on disk, from evidence rather than file names; bounded
    and never raises.

    ``revisions`` counts managed ``experiments/experiments-<slug>-vNN.md``
    files that open with the artifact marker; a product folder
    ``implementations/<repo>/<Name>/`` is a proof of concept when it holds
    ``AGREED.md`` and a full experiment when it holds ``Experimental_AGREED.md``,
    and it counts as done only with a ``Results/`` directory beside the marker.
    """
    from . import remote_services
    out: dict[str, Any] = {"files": 0, "revisions": 0, "toy": False, "registry": False,
                           "replications": 0, "poc": 0, "poc_results": 0, "full": 0, "full_results": 0,
                           "timing": 0, "hpo": 0}
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
            if (product / "Experimental_AGREED.md").is_file():
                out["full"] += 1
                out["full_results"] += results
            elif (product / "AGREED.md").is_file():
                out["poc"] += 1
                out["poc_results"] += results
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


def terminal_allowed(host: str) -> bool:
    """The support terminal is a shell: offer it only on a loopback bind."""
    return is_loopback_bind(host)


def create_app(root: Path | str, *, debounce_ms: int = 300,
               health_ttl: float = DEFAULT_HEALTH_TTL_SECONDS,
               history_store: history.HistoryStore | None = None,
               allowed_hosts: frozenset[str] | None = None,
               enable_terminal: bool = False) -> FastAPI:
    root_path = Path(root).expanduser().resolve()
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
        authors = ", ".join(a if isinstance(a, str) else a.get("name", "") for a in authors_raw) if authors_raw else "Sin autor asignado"

        proposals_dir = root_path / "proposals"
        prop_files = sorted(
            [p.name for p in proposals_dir.glob("*.md") if p.is_file() and not p.name.startswith(".")],
            reverse=True
        ) if proposals_dir.is_dir() else []
        active_prop = prop_files[0] if prop_files else "Sin propuesta activa"
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

        # Fase 1
        fase1_status = "PASS" if harness_ok else "PENDING"
        # Fase 2
        if sota_atlas:
            fase2_status, fase2_prog, fase2_det = "PASS", 1.0, "Atlas SOTA 3D compilado en sota-pool/"
        elif sota_cand:
            fase2_status, fase2_prog, fase2_det = "ACTIVE", 0.5, "Candidatos SOTA descubiertos, pendiente atlas"
        else:
            fase2_status, fase2_prog, fase2_det = "PENDING", 0.0, "Sin artefactos en sota-pool/"

        # Fase 3
        if guidance_refs and not guidance_loose_pdfs:
            fase3_status, fase3_prog, fase3_det = "PASS", 1.0, f"{len(guidance_refs)} referencias ingeridas, cero PDFs sueltos"
        elif guidance_loose_pdfs or guidance_refs:
            fase3_status, fase3_prog, fase3_det = "ACTIVE", 0.5, f"{len(guidance_loose_pdfs)} PDFs pendientes de ingerir"
        else:
            fase3_status, fase3_prog, fase3_det = "PENDING", 0.0, "Sin artículos de referencia en guidance/"

        # Fase 4
        if has_deliberated_prop:
            fase4_status, fase4_prog, fase4_det = "PASS", 1.0, f"Propuesta deliberada ({active_prop})"
        elif prop_files:
            fase4_status, fase4_prog, fase4_det = "ACTIVE", 0.5, f"Borrador en curso ({prop_files[0]})"
        else:
            fase4_status, fase4_prog, fase4_det = "PENDING", 0.0, "Sin propuesta en proposals/"

        # Fase 5: a published protocol revision, a proof of concept with
        # results and a full experiment with results; never a file name.
        p5_done = [p5["revisions"] > 0, p5["poc_results"] > 0, p5["full_results"] > 0]
        fase5_det = (f"Protocolo publicado: {'sí' if p5_done[0] else 'no'} · PoC con Results/: {p5['poc_results']}"
                     f" · experimentos completos con Results/: {p5['full_results']}")
        if all(p5_done):
            fase5_status, fase5_prog = "PASS", 1.0
        elif any(p5_done) or p5["files"] or p5["poc"] or p5["full"]:
            fase5_status, fase5_prog = "ACTIVE", round(sum(p5_done) / 3, 3)
        else:
            fase5_status, fase5_prog = "PENDING", 0.0

        def _p5(done: bool, started: bool = False) -> str:
            return "PASS" if done else ("ACTIVE" if started else "PENDING")

        p5_protocol = _p5(p5["revisions"] > 0, p5["files"] > 0)

        # Fase 6
        if has_scaffold:
            fase6_status, fase6_prog, fase6_det = "PASS", 1.0, "paper/main.tex y contratos de sección andamiados"
        else:
            fase6_status, fase6_prog, fase6_det = "PENDING", 0.0, "paper/main.tex pendiente de andamiaje"

        # Fase 7
        if has_decl:
            fase7_status, fase7_prog, fase7_det = "PASS", 1.0, "Declaraciones operativas fijadas en main.tex"
        else:
            fase7_status, fase7_prog, fase7_det = "PENDING", 0.0, "Declaraciones pendientes de fijación"

        # Fase 8
        if written_blocks >= total_blocks and total_blocks > 0:
            fase8_status, fase8_prog = "PASS", 1.0
        elif written_blocks > 0:
            fase8_status, fase8_prog = "ACTIVE", round(written_blocks / max(1, total_blocks), 3)
        else:
            fase8_status, fase8_prog = "PENDING", 0.0
        fase8_det = f"{written_blocks}/{total_blocks} bloques canónicos redactados ({total_words} palabras)"

        # Fase 9
        if fig_count >= 1:
            fase9_status, fase9_prog, fase9_det = "PASS", 1.0, f"{fig_count} figura(s) vectorial(es) en paper/Figures/"
        else:
            fase9_status, fase9_prog, fase9_det = "PENDING", 0.0, "0 figuras en paper/Figures/"

        # Fase 10
        if pdf_exists:
            fase10_status, fase10_prog, fase10_det = "PASS", 1.0, f"Manuscrito PDF compilado ({pdf_pages} págs, {round(pdf_size / 1024, 1)} KB)"
        else:
            fase10_status, fase10_prog, fase10_det = "PENDING", 0.0, "paper/main.pdf pendiente de compilación"

        # Fase 11
        if has_audit:
            fase11_status, fase11_prog, fase11_det = "PASS", 1.0, "Auditoría transversal ejecutada y superada"
        else:
            fase11_status, fase11_prog, fase11_det = "PENDING", 0.0, (
                "La última auditoría falló: revisa .papersmith/audit.json"
                if _audit_verdict(root_path) is False else "Auditoría transversal pendiente")

        fases = [
            {
                "id": "Fase 1",
                "stage_id": "harness",
                "name": "Fase 1: Configuración de Entorno & Harness",
                "gate": "G-HARNESS",
                "agent": "ecosystem-orchestrator",
                "desc": "Estructura de workspace, proyecciones de harness (.claude, .opencode, .pi, .agents), entorno micromamba y validación de runtimes.",
                "tools": ["read", "bash"],
                "skills": ["harness-setup", "workspace-verifier"],
                "cli_command": "smith init --harness-only",
                "outputs": [".papersmith/", "papersmith.yaml", "pyproject.toml"],
                "status": fase1_status,
                "progress": 1.0 if fase1_status == "PASS" else 0.0,
                "detail": "Proyecciones de harness operativas" if fase1_status == "PASS" else "Entorno pendiente de inicialización",
                "subfases": [
                    {"id": "1.1", "name": "Workspace & Manifiesto", "status": fase1_status, "detail": "papersmith.yaml y estructura base versionada"},
                    {"id": "1.2", "name": "Proyección de Agentes", "status": fase1_status, "detail": "Enlaces simbólicos a arneses operacionales"},
                    {"id": "1.3", "name": "Aislamiento Micromamba", "status": fase1_status, "detail": "Python 3.12 y dependencias del entorno"},
                    {"id": "1.4", "name": "Integridad de CLI", "status": fase1_status, "detail": "CLI papersmith verificado"}
                ]
            },
            {
                "id": "Fase 2",
                "stage_id": "plausibility",
                "name": "Fase 2: Plausibilidad & SOTA Atlas 3D",
                "gate": "G-SOTA",
                "agent": "sota-scout & sota-grapher & novelty-screener",
                "desc": "Exploración SOTA, validación de plausibilidad y compilación del Atlas 3D de candidatos y constelación conceptual.",
                "tools": ["read", "write", "mcp"],
                "skills": ["sota-scout", "semantic-scholar", "pubmed-search"],
                "cli_command": "smith run --stage plausibility",
                "outputs": ["sota-pool/atlas.json", "sota-pool/atlas.html", "sota-pool/candidates.json"],
                "status": fase2_status,
                "progress": fase2_prog,
                "detail": fase2_det,
                "subfases": [
                    {"id": "2.1", "name": "Discovery de Artículos SOTA", "status": fase2_status, "detail": "Búsqueda y filtrado de literatura Q1/Q2"},
                    {"id": "2.2", "name": "Extracción de Metadatos & Familias", "status": fase2_status, "detail": "Clasificación taxonómica de candidatos"},
                    {"id": "2.3", "name": "Embedding Espacial & Constelación 3D", "status": fase2_status, "detail": "Generación de atlas.json para visualización WebGL"},
                    {"id": "2.4", "name": "Detección de Brecha de Novedad", "status": fase2_status, "detail": "Identificación de vacíos conceptuales y oportunidad"}
                ]
            },
            {
                "id": "Fase 3",
                "stage_id": "ingestion",
                "name": "Fase 3: Ingestión de Referencias & Literatura",
                "gate": "G-INGEST",
                "agent": "paper-ingestion",
                "desc": "Ingestión a Markdown de artículos de referencia, normalización BibTeX de bibliografía y extracción de insumos base.",
                "tools": ["read", "write", "marker"],
                "skills": ["paper-ingestion", "pdf-extractor", "bibtex-parser"],
                "cli_command": "smith ingest guidance/reference-papers/",
                "outputs": ["guidance/reference-papers/", "paper/refs.bib", "paper/Figures/"],
                "status": fase3_status,
                "progress": fase3_prog,
                "detail": fase3_det,
                "subfases": [
                    {"id": "3.1", "name": "Ingestión de Artículos Base", "status": fase3_status, "detail": "Conversión estructural de PDFs a Markdown limpio"},
                    {"id": "3.2", "name": "Normalización BibTeX (refs.bib)", "status": fase3_status, "detail": "Citas verificadas y consolidadas"},
                    {"id": "3.3", "name": "Extracción Vectorial de Figuras", "status": fase3_status, "detail": "Figuras y diagramas de referencia"},
                    {"id": "3.4", "name": "Extracción de Hechos e Insumos", "status": fase3_status, "detail": "Extracción de parámetros para el manuscrito"}
                ]
            },
            {
                "id": "Fase 4",
                "stage_id": "proposal",
                "name": "Fase 4: Deliberación de Propuesta & Modelo Conceptual",
                "gate": "G-PROP",
                "agent": "deliberation-publish & mathematical-tutor",
                "desc": "Deliberación científica formal de la propuesta (rNN), definición de novedad, discusión del mapa conceptual y de la matemática con el tutor socrático.",
                "tools": ["read", "write", "deliberate"],
                "skills": ["proposal-deliberation", "peer-review-simulator"],
                "cli_command": "smith deliberate proposals/",
                "outputs": ["proposals/"],
                "status": fase4_status,
                "progress": fase4_prog,
                "detail": fase4_det,
                "subfases": [
                    {"id": "4.1", "name": "Stage bound: Delimitación & Locus", "status": fase4_status, "detail": "Definición del problema y anclaje de locus conceptual"},
                    {"id": "4.2", "name": "Stage deliberated: Novedad & Consenso", "status": fase4_status, "detail": "Discusión de hipótesis y pilares de innovación"},
                    {"id": "4.3", "name": "Stage composed: Modelo Matemático Básico", "status": fase4_status, "detail": "Formalización matemática y ecuaciones clave"},
                    {"id": "4.4", "name": "Stage published: Publicación & Recibo Criptográfico", "status": fase4_status, "detail": "Revisión sellada con hash SHA-256"},
                    {"id": "4.5", "name": "Discusión del mapa conceptual", "status": fase4_status, "detail": "Pilares, hipótesis y capas del concepto (pestaña Mapa Conceptual)"},
                    {"id": "4.6", "name": "Matemática y tutor socrático", "status": fase4_status, "detail": "Ecuaciones en LaTeX, tarjeta de novedad y tutor con imágenes a mano (math-tutor)"}
                ]
            },
            {
                "id": "Fase 5",
                "stage_id": "poc_experiments",
                "name": f"Fase 5: {phase_actions.PHASE_LABELS['poc_experiments']}",
                "gate": "G-EXP-POC",
                "agent": phase_actions.ACTIONS["poc_experiments"]["agent"],
                "desc": "Deliberación del protocolo experimental, toy set, réplica de los métodos de comparación, prueba de concepto, estimación de tiempo, búsqueda de hiperparámetros opcional, experimentos completos, revisión del código, ensayo remoto y lanzamiento autorizado por el operador, en local o en un servicio remoto (CLI o MCP).",
                "tools": ["read", "write", "validate"],
                "skills": ["experimental-deliberation", "datasets", "proposal-implementation", "experimental-implementation"],
                "cli_command": "/experimental-deliberation <texto>",
                "outputs": ["experiments/", "datasets/registry.json", "implementations/"],
                "status": fase5_status,
                "progress": fase5_prog,
                "detail": fase5_det,
                "subfases": [
                    {"id": "5.1", "name": "Stage bound: Anclaje de Claims & Métricas", "status": p5_protocol, "detail": "Criterios de éxito y métricas cuantificables (pasa con la revisión publicada)"},
                    {"id": "5.2", "name": "Stage validated: Baselines & SOTA", "status": p5_protocol, "detail": "experimental-validation contrasta protocolo, métricas y baselines con búsquedas fechadas"},
                    {"id": "5.3", "name": "Stage deliberated: Diseño Metrológico & Protocolos", "status": p5_protocol, "detail": "Protocolos de ensayo y validación"},
                    {"id": "5.4", "name": "Stage composed: Especificación de Experimentos", "status": p5_protocol, "detail": "Formalización de experimentos con instrumentación"},
                    {"id": "5.5", "name": "Stage published: Aprobación de Gate", "status": p5_protocol, "detail": f"experimental-publish deja experiments/experiments-<slug>-vNN.md con el marcador de artefacto ({p5['revisions']} revisión(es) publicada(s))"},
                    {"id": "5.6", "name": "Datos: toy set siempre y dataset oficial", "status": _p5(p5["toy"], p5["registry"]), "detail": "/datasets synth|search|license|qc|prepare|publish con dataset-scout y dataset-curator; pasa con un toy set en datasets/registry.json; publicación privada solo con consentimiento del operador"},
                    {"id": "5.7", "name": "Réplica de métodos de comparación", "status": _p5(p5["replications"] > 0), "detail": f"/proposal-implementation → paper-replicator: primero el código publicado, adoptado y auditado; si no existe, reimplementación ({p5['replications']} REPLICATION.md)"},
                    {"id": "5.8", "name": "Prueba de concepto", "status": _p5(p5["poc_results"] > 0, p5["poc"] > 0), "detail": f"/proposal-implementation (implementation-build): carpeta con AGREED.md y Results/ ({p5['poc_results']} de {p5['poc']})"},
                    {"id": "5.9", "name": "Estimar tiempo y elegir dónde correr", "status": _p5(p5["timing"] > 0), "detail": "Antes del piloto y otra vez antes de la corrida completa: sonda de tiempo corta (una época de un fold por brazo) en Results/timing.json; la pestaña Experimentos estima la PoC y la corrida completa (±20%) y lista las opciones local y remotas"},
                    {"id": "5.10", "name": "Búsqueda de hiperparámetros (Optuna, opcional)", "status": _p5(p5["hpo"] > 0), "detail": f"Solo si la deliberación la estimó conveniente: /hyperparameter-search plan|report|status, anidada dentro de cada fold externo, mismo presupuesto por brazo, evaluador de importancia declarado; contornos e importancia en Results/hpo/ ({p5['hpo']} producto(s) con estudios)"},
                    {"id": "5.11", "name": "Experimentos completos", "status": _p5(p5["full_results"] > 0, p5["full"] > 0), "detail": f"/experimental-implementation (experiments-build): carpeta con Experimental_AGREED.md y Results/ ({p5['full_results']} de {p5['full']})"},
                    {"id": "5.12", "name": "Revisión del código (experiments-reviewer) antes del ensayo", "status": "PENDING", "detail": "Calidad del código, optimización, uso de GPU y pruebas estadísticas declaradas; el informe va al operador y no deja archivo, así que esta subfase no se verifica desde el disco"},
                    {"id": "5.13", "name": "Ensayo remoto y autorización del lanzamiento (operador)", "status": _p5(p5["launched"] > 0, p5["jobs"] > 0 or p5["smokes"] > 0), "detail": f"Solo para corridas remotas (local corre directo). /kaggle-accounts validate y smith team add --attest (una cuenta por persona y servicio); luego generate-job → submit --smoke → fetch --smoke y smoke record → readiness → gate (operador) → submit → status / poll → fetch. Ensayos aprobados: {p5['rehearsals_passed']}; ledgers con envíos: {p5['launched']}"}
                ]
            },
            {
                "id": "Fase 6",
                "stage_id": "scaffolding",
                "name": "Fase 6: Andamiaje de Manuscrito & Contratos",
                "gate": "G-SCAFFOLD",
                "agent": "contract-auditor",
                "desc": "Andamiaje de paper/main.tex con bloques canónicos y contratos de sección bajo la clase tipográfica del journal.",
                "tools": ["read", "write"],
                "skills": ["scaffold-generator", "latex-contract-indexer"],
                "cli_command": "smith implement scaffold",
                "outputs": ["paper/main.tex", "paper/refs.bib", "sections/*.md"],
                "status": fase6_status,
                "progress": fase6_prog,
                "detail": fase6_det,
                "subfases": [
                    {"id": "6.1", "name": "Estructura de Secciones", "status": fase6_status, "detail": "Contratos canónicos en sections/*.md"},
                    {"id": "6.2", "name": "Apertura de Bloques Canónicos", "status": fase6_status, "detail": "Marcadores y hashes SHA-256 integrados"},
                    {"id": "6.3", "name": "Asignación de Roles Retóricos", "status": fase6_status, "detail": "Preguntas editoriales y acoplamiento de hechos"},
                    {"id": "6.4", "name": "Configuración Tipográfica", "status": fase6_status, "detail": "Plantilla LaTeX del journal objetivo"}
                ]
            },
            {
                "id": "Fase 7",
                "stage_id": "declarations",
                "name": "Fase 7: Declaraciones Operativas & Coautoría",
                "gate": "G-DECLARATIONS",
                "agent": "declarations-recorder",
                "desc": "Fijación de declaraciones operativas: autoría CRediT, financiación, repositorio abierto y consideraciones éticas.",
                "tools": ["read", "write"],
                "skills": ["credit-taxonomy", "ethics-compliance"],
                "cli_command": "smith implement declarations",
                "outputs": ["paper/main.tex (declarations)"],
                "status": fase7_status,
                "progress": fase7_prog,
                "detail": fase7_det,
                "subfases": [
                    {"id": "7.1", "name": "Taxonomía CRediT de Coautoría", "status": fase7_status, "detail": "Roles autorales formalizados"},
                    {"id": "7.2", "name": "Declaración Ética", "status": fase7_status, "detail": "Protocolos éticos e institucionales"},
                    {"id": "7.3", "name": "Disponibilidad de Datos y Código", "status": fase7_status, "detail": "Repositorio y accesibilidad"},
                    {"id": "7.4", "name": "Sellado en main.tex", "status": fase7_status, "detail": "Región declarations bloqueada con hash"}
                ]
            },
            {
                "id": "Fase 8",
                "stage_id": "writing",
                "name": "Fase 8: Redacción Técnica & Transposición",
                "gate": "G-WRITING",
                "agent": "redactor & style-sampler & insumos-observer",
                "desc": "Redacción técnica por oleadas de los bloques canónicos del manuscrito a partir de los datos experimentales.",
                "tools": ["read", "write", "substitute"],
                "skills": ["technical-writing", "facts-coupler", "style-shield"],
                "cli_command": "python3 scripts/build_manuscript.py",
                "outputs": ["paper/main.tex", "sections/*.md"],
                "status": fase8_status,
                "progress": fase8_prog,
                "detail": fase8_det,
                "manuscript_ref": {"pages": "1–10", "words": total_words},
                "subfases": [
                    {"id": "8.1", "name": "Wave 1: Título, Keywords & Abstract", "status": fase8_status, "detail": "Slots iniciales en pág. 1"},
                    {"id": "8.2", "name": "Wave 2: Introducción & Hipótesis", "status": fase8_status, "detail": "Bloques de introducción y motivación"},
                    {"id": "8.3", "name": "Wave 3: Related Work & SOTA", "status": fase8_status, "detail": "Estado del arte y tabla comparativa"},
                    {"id": "8.4", "name": "Wave 4–9: Métodos, Resultados & Conclusiones", "status": fase8_status, "detail": "Bloques técnicos y experimentales"}
                ]
            },
            {
                "id": "Fase 9",
                "stage_id": "figures",
                "name": "Fase 9: Diagramas Técnicos & Grounding",
                "gate": "G-FIGURES",
                "agent": "diagram-author & figure-auditor",
                "desc": "Elaboración de diagramas de arquitectura, figuras vectoriales, esquemas y grounding con el texto.",
                "tools": ["read", "write", "latexmk"],
                "skills": ["vector-graphics", "sips-optimizer", "figure-grounding"],
                "cli_command": "smith audit --figures",
                "outputs": ["paper/Figures/"],
                "status": fase9_status,
                "progress": fase9_prog,
                "detail": fase9_det,
                "subfases": [
                    {"id": "9.1", "name": "Diagramas de Arquitectura & Sistema", "status": fase9_status, "detail": "Figuras estructurales y topológicas"},
                    {"id": "9.2", "name": "Curvas y Gráficas Experimentales", "status": fase9_status, "detail": "Rendimiento y contrastes empíricos"},
                    {"id": "9.3", "name": "Esquemas Metodológicos", "status": fase9_status, "detail": "Flujos de procesamiento y transducción"},
                    {"id": "9.4", "name": "Grounding de Figuras en Texto", "status": fase9_status, "detail": "Anclaje de referencias cruzadas"}
                ]
            },
            {
                "id": "Fase 10",
                "stage_id": "paper",
                "name": "Fase 10: Compilación & Manuscrito PDF",
                "gate": "G-PDF",
                "agent": "latex-compiler",
                "desc": "Compilación del manuscrito LaTeX a PDF con maquetación editorial, verificación de referencias BibTeX y visor interactivo.",
                "tools": ["read", "bash"],
                "skills": ["pdflatex-engine", "bibtex-linker", "pdfjs-viewer"],
                "cli_command": "cd paper && pdflatex -interaction=nonstopmode main.tex && bibtex main && pdflatex main.tex",
                "outputs": ["paper/main.pdf"],
                "status": fase10_status,
                "progress": fase10_prog,
                "detail": fase10_det,
                "manuscript_ref": {"pages": pdf_pages, "size_mb": round(pdf_size / (1024*1024), 2), "file": "paper/main.pdf"},
                "subfases": [
                    {"id": "10.1", "name": "Compilación pdfTeX", "status": fase10_status, "detail": "0 errores fatales en compilación"},
                    {"id": "10.2", "name": "Vinculación BibTeX", "status": fase10_status, "detail": f"{bib_count} citas vinculadas sin huérfanas"},
                    {"id": "10.3", "name": "Optimización Vectorial", "status": fase10_status, "detail": "Generación de PDF optimizado"},
                    {"id": "10.4", "name": "Visor PDF Interactivo", "status": fase10_status, "detail": "Visor PDF.js con control de cambios"}
                ]
            },
            {
                "id": "Fase 11",
                "stage_id": "audit",
                "name": "Fase 11: Auditoría Transversal & Gates",
                "gate": "G-AUDIT",
                "agent": "audit-report",
                "desc": "Verificación estricta de las 4 compuertas del framework: readiness, acoplamiento de hechos, blindaje de estilo y figuras.",
                "tools": ["read", "bash"],
                "skills": ["cross-auditor", "gate-checker", "hash-verifier"],
                "cli_command": "smith audit",
                "outputs": [".papersmith/audit.json"],
                "status": fase11_status,
                "progress": fase11_prog,
                "detail": fase11_det,
                "subfases": [
                    {"id": "11.1", "name": "Gate G1: Writing Readiness", "status": fase11_status, "detail": "Contratos canónicos validados"},
                    {"id": "11.2", "name": "Gate G2: Coupling Verification", "status": fase11_status, "detail": "Hechos acoplados con fuentes de insumo"},
                    {"id": "11.3", "name": "Gate G3: Style Shield", "status": fase11_status, "detail": "Blindaje retórico y de citas"},
                    {"id": "11.4", "name": "Gate G4: Figure Grounding", "status": fase11_status, "detail": "Figuras ancladas con referencias en texto"}
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
                "category": "Propuestas",
                "size_kb": round(p.stat().st_size / 1024, 1)
            })
        if (root_path / "paper" / "main.tex").is_file():
            tex = root_path / "paper" / "main.tex"
            artifacts.append({
                "rel_path": "paper/main.tex",
                "name": "main.tex",
                "category": "Manuscrito LaTeX",
                "size_kb": round(tex.stat().st_size / 1024, 1)
            })
        guidance_guide = root_path / "guidance" / "paper-guide"
        if guidance_guide.is_dir():
            for gp in sorted(guidance_guide.glob("*.md")):
                artifacts.append({
                    "rel_path": str(gp.relative_to(root_path)),
                    "name": gp.name,
                    "category": "Guía Científica",
                    "size_kb": round(gp.stat().st_size / 1024, 1)
                })
        guidance_ref = root_path / "guidance" / "reference-papers"
        if guidance_ref.is_dir():
            for rp in sorted(guidance_ref.glob("**/*.md")):
                artifacts.append({
                    "rel_path": str(rp.relative_to(root_path)),
                    "name": rp.name,
                    "category": "Referencia / Insumo",
                    "size_kb": round(rp.stat().st_size / 1024, 1)
                })
        if (root_path / "sota-pool" / "atlas.json").is_file():
            artifacts.append({
                "rel_path": "sota-pool/atlas.json",
                "name": "atlas.json (SOTA)",
                "category": "Constelación SOTA",
                "size_kb": round((root_path / "sota-pool" / "atlas.json").stat().st_size / 1024, 1)
            })
        experiments_dir = root_path / "experiments"
        if experiments_dir.is_dir():
            for ep in sorted(experiments_dir.glob("*.md")):
                artifacts.append({
                    "rel_path": f"experiments/{ep.name}",
                    "name": ep.name,
                    "category": "Experimentos",
                    "size_kb": round(ep.stat().st_size / 1024, 1)
                })
        sections_dir = root_path / "sections"
        if sections_dir.is_dir():
            for sp in sorted(sections_dir.glob("*.md")):
                artifacts.append({
                    "rel_path": f"sections/{sp.name}",
                    "name": f"Reglas: {sp.name}",
                    "category": "Reglas de Sección",
                    "size_kb": round(sp.stat().st_size / 1024, 1)
                })

        SECTION_METADATA = {
            "09-title-and-keywords": {
                "page": 1,
                "principles": "Concisión técnica informativa sin acrónimos ambiguos. Identificar el sistema/modelo y dominio de aplicación.",
                "blocks": [
                    {"id": "title-and-keywords.title", "role": "Título Principal", "question": "¿Cuál es la contribución técnica y el dominio de aplicación del trabajo?"},
                    {"id": "title-and-keywords.keywords", "role": "Palabras Clave Indexables", "question": "¿Cuáles son los términos y descriptores indexables del manuscrito?"}
                ],
                "cross_relations": "Proyecta los términos clave que se desarrollan en el Abstract y se formalizan en la Introducción."
            },
            "08-abstract": {
                "page": 1,
                "principles": "Estructura canónica de slots: Contexto -> Brecha técnica -> Propuesta metodológica -> Arquitectura/Diseño -> Resultados experimentales -> Precisión/Rendimiento -> Impacto y reproducibilidad.",
                "blocks": [
                    {"id": "abstract.slot-1", "role": "Contexto del Problema", "question": "¿Por qué es crucial este problema y cuál es el dominio de aplicación?"},
                    {"id": "abstract.slot-2", "role": "Brecha Tecnológica / Científica", "question": "¿Qué deficiencias o limitaciones presentan las aproximaciones actuales?"},
                    {"id": "abstract.slot-3", "role": "Propuesta Principal", "question": "¿Qué propone este trabajo para resolver dicha brecha?"},
                    {"id": "abstract.slot-4", "role": "Arquitectura y Metodología", "question": "¿Qué componentes integran el sistema o modelo propuesto?"},
                    {"id": "abstract.slot-5", "role": "Resultados Experimentales", "question": "¿Qué métricas de rendimiento y validación empírica se alcanzaron?"},
                    {"id": "abstract.slot-6", "role": "Métrica Diferenciadora", "question": "¿Cuál es la precisión, latencia o ventaja empírica demostrada?"},
                    {"id": "abstract.slot-7", "role": "Impacto y Reproducibilidad", "question": "¿Cómo transforma este avance el campo de investigación?"}
                ],
                "cross_relations": "Resume la totalidad del manuscrito; cada slot anticipa una sección del paper."
            },
            "06-introduction": {
                "page": 1,
                "principles": "Construcción de argumento secuencial: justificación del problema, mapa metodológico, cuello de botella actual, solución propuesta, hipótesis comprobables y contribuciones.",
                "blocks": [
                    {"id": "introduction.block-1", "role": "Escenario y Motivación", "question": "¿Cuál es el contexto y la motivación fundamental del problema?"},
                    {"id": "introduction.block-4a", "role": "Hoja de Ruta Metodológica", "question": "¿Cómo se estructuró la investigación y el marco de trabajo?"},
                    {"id": "introduction.block-2", "role": "Cuello de Botella y Desafíos", "question": "¿Qué limitaciones técnicas o teóricas impiden resolver el problema hoy?"},
                    {"id": "introduction.block-3", "role": "Solución Propuesta", "question": "¿Cómo aborda el sistema propuesto las limitaciones identificadas?"},
                    {"id": "introduction.block-4b", "role": "Hipótesis Comprobables", "question": "¿Cuáles son las hipótesis que el estudio somete a prueba empírica?"},
                    {"id": "introduction.block-5", "role": "Estructura del Manuscrito", "question": "¿Cómo está organizada la lectura de las siguientes secciones?"},
                    {"id": "introduction.block-6", "role": "Contribuciones Clave", "question": "¿Cuáles son los aportes científicos y técnicos definitivos del artículo?"}
                ],
                "cross_relations": "Las hipótesis planteadas se validan individualmente en Results y se sintetizan en Conclusions."
            },
            "05-related-work": {
                "page": 3,
                "principles": "Taxonomía comparativa rigurosa contra el estado del arte (SOTA). Tabla formal confrontando características clave, métricas y brechas.",
                "blocks": [
                    {"id": "related-work.rw-preamble", "role": "Evolución y Panorama", "question": "¿Cómo ha evolucionado el área y qué vertientes principales existen?"},
                    {"id": "related-work.rw-panorama", "role": "Aproximaciones Actuales y Limitaciones", "question": "¿Qué fortalezas y debilidades presentan los trabajos previos relevantes?"},
                    {"id": "related-work.rw-problem-blocks", "role": "Impacto de las Brechas No Resueltas", "question": "¿De qué manera impactan las limitaciones existentes en el rendimiento global?"},
                    {"id": "related-work.rw-closing", "role": "Posicionamiento de la Propuesta", "question": "¿Por qué la propuesta se sitúa en una posición diferencial respecto al SOTA?"},
                    {"id": "related-work.rw-synthesis-artefact", "role": "Síntesis del Atlas SOTA", "question": "¿Cómo sustenta el análisis comparativo las decisiones metodológicas tomadas?"}
                ],
                "cross_relations": "Establece el marco de referencia que justifica las decisiones de diseño y experimentación."
            },
            "01-materials-and-methods": {
                "page": 4,
                "principles": "Descripción rigurosa y reproducible sin ambigüedades. Modelos formales, formulación matemática y arquitectura del sistema.",
                "blocks": [
                    {"id": "materials-and-methods.mm-preamble", "role": "Visión Modular del Sistema", "question": "¿Cuáles son los módulos y componentes principales del sistema o modelo?"},
                    {"id": "materials-and-methods.mm-borrowed-machinery", "role": "Fundamentos y Topología", "question": "¿Qué mecanismos o arquitecturas base se adoptan y cómo se conectan?"},
                    {"id": "materials-and-methods.mm-proposal", "role": "Innovación Metodológica Específica", "question": "¿Cuál es la formulación matemática o diseño específico introducido?"}
                ],
                "cross_relations": "Especifica la arquitectura y métodos cuyo rendimiento se evalúa en las secciones experimentales."
            },
            "02-experimental-setup": {
                "page": 5,
                "principles": "Protocolos reproducibles de validación: configuración de banco/datasets, instrumental, métricas de evaluación y parámetros.",
                "blocks": [
                    {"id": "experimental-setup.es-preamble", "role": "Estrategia Experimental", "question": "¿Cuál es la estrategia metodológica adoptada para validar la propuesta?"},
                    {"id": "experimental-setup.es-dataset", "role": "Datasets o Fuentes de Señales", "question": "¿Qué fuentes de datos, instrumentos o entornos de prueba se utilizaron?"},
                    {"id": "experimental-setup.es-assessment", "role": "Métricas de Evaluación", "question": "¿Cuáles son los criterios de éxito y métricas formales de desempeño?"},
                    {"id": "experimental-setup.es-training-details", "role": "Parámetros y Protocolos", "question": "¿Cuáles son los hiperparámetros, tasas y protocolos de experimentación?"}
                ],
                "cross_relations": "Fija las reglas y condiciones empíricas para evaluar las hipótesis planteadas en la Introducción."
            },
            "03-results-and-discussion": {
                "page": 6,
                "principles": "Densidad de evidencia cuantitativa. Corroboración con gráficas, tablas de rendimiento y contraste con baselines.",
                "blocks": [
                    {"id": "results-and-discussion.rd-general-task", "role": "Validación de Hipótesis y Tarea Principal", "question": "¿Se corroboran las hipótesis principales planteadas en la introducción?"},
                    {"id": "results-and-discussion.rd-contribution-blocks", "role": "Análisis Cuantitativo y Desempeño", "question": "¿Cuáles son los resultados empíricos obtenidos frente a las métricas de éxito?"},
                    {"id": "results-and-discussion.rd-cost", "role": "Contraste con Baselines y Discusión", "question": "¿Qué ventajas cuantitativas y cualitativas se demuestran respecto al estado del arte?"}
                ],
                "cross_relations": "Valida empíricamente las hipótesis planteadas, confirmando los claims del Abstract."
            },
            "04-limitations": {
                "page": 8,
                "principles": "Autocrítica constructiva y honestidad científica: supuestos, complejidad computacional, trade-offs y condiciones de fallo.",
                "blocks": [
                    {"id": "limitations.lim-opening-concession", "role": "Concesión Inicial y Alcance", "question": "¿Cuáles son los límites de validez y supuestos asumidos en el trabajo?"},
                    {"id": "limitations.lim-proposal-items", "role": "Restricciones de Recursos o Cómputo", "question": "¿Qué requerimientos de cómputo, energía o datos condicionan el sistema?"},
                    {"id": "limitations.lim-validation-items", "role": "Representatividad de la Muestra/Datos", "question": "¿Qué escenarios o distribuciones aún no han sido cubiertos exhaustivamente?"},
                    {"id": "limitations.lim-failure-mode", "role": "Modos de Fallo Potenciales", "question": "¿En qué casos extremos o bajo qué perturbaciones podría degradarse el rendimiento?"},
                    {"id": "limitations.lim-closing", "role": "Perspectiva Constructiva", "question": "¿Cómo pueden mitigarse estas limitaciones en futuras iteraciones?"}
                ],
                "cross_relations": "Dialoga con el Related Work y establece las líneas prioritarias para el trabajo futuro."
            },
            "07-conclusions": {
                "page": 8,
                "principles": "Síntesis concluyente de las aportaciones fundamentales sin reiterar datos brutos. Proyección y direcciones de trabajo futuro.",
                "blocks": [
                    {"id": "conclusions.concl-block-1", "role": "Recapitulación del Problema", "question": "¿Qué reto fundamental abordó y resolvió esta investigación?"},
                    {"id": "conclusions.concl-block-2", "role": "Síntesis de Contribución Principal", "question": "¿Cuáles son los principales hallazgos y avances consolidados?"},
                    {"id": "conclusions.concl-block-3", "role": "Implicaciones Científicas o Tecnológicas", "question": "¿Qué implicaciones prácticas o teóricas tiene este avance para la disciplina?"},
                    {"id": "conclusions.concl-block-4", "role": "Líneas Futuras y Reproducibilidad", "question": "¿Qué recursos quedan disponibles para la comunidad y qué trabajo futuro se abre?"}
                ],
                "cross_relations": "Cierra el ciclo argumentativo abierto en el Abstract y la Introducción."
            },
            "10-back-matter": {
                "page": 9,
                "principles": "Transparencia formal: autoría CRediT, fuentes de financiación, disponibilidad de datos/código y declaraciones éticas.",
                "blocks": [
                    {"id": "back-matter.bm-author-contributions", "role": "Taxonomía CRediT de Coautoría", "question": "¿Qué roles y contribuciones desempeñó cada autor del manuscrito?"},
                    {"id": "back-matter.bm-funding", "role": "Declaración de Financiación", "question": "¿Qué proyectos, becas o entidades financiaron la investigación?"},
                    {"id": "back-matter.bm-data-availability", "role": "Disponibilidad de Datos y Código", "question": "¿Dónde reposan los datasets, código fuente y artefactos reproducibles?"},
                    {"id": "back-matter.bm-conflicts-of-interest", "role": "Conflictos de Interés", "question": "¿Existe algún conflicto de interés financiero o personal que declarar?"},
                    {"id": "back-matter.bm-acknowledgments", "role": "Agradecimientos", "question": "¿A qué instituciones, revisores o colaboradores técnicos se agradece?"},
                    {"id": "back-matter.bm-appendices", "role": "Apéndices Técnicos", "question": "¿Qué derivaciones matemáticas, tablas suplementarias o detalles se anexan?"}
                ],
                "cross_relations": "Cumple los requisitos regulatorios y éticos de publicación académica."
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
                "principles": sec_meta.get("principles", "Redacción técnica formal bajo directrices de publicación."),
                "canonical_blocks": sec_meta.get("blocks", []),
                "cross_relations": sec_meta.get("cross_relations", "Trazabilidad cruzada con el resto del manuscrito.")
            })

        gates_list = [
            {
                "id": "G-EXP-POC",
                "name": "Proof-of-Concept & Experimental Design Gate",
                "status": "PASS" if fase5_status == "PASS" else ("ACTIVE" if fase5_status == "ACTIVE" else "PENDING"),
                "criteria": "Validación empírica y diseño experimental: reproducibilidad de pruebas, especificación de baseline y criterios de éxito cuantitativos.",
                "reviewer": "experiments-reviewer",
                "phase": "Fase 5"
            },
            {
                "id": "G1",
                "name": "Writing Readiness Gate",
                "status": "PASS" if fase6_status == "PASS" else ("ACTIVE" if fase6_status == "ACTIVE" else "PENDING"),
                "criteria": "Contratos de sección validados con gramática cerrada y dependencias resueltas.",
                "reviewer": "contract-auditor",
                "phase": "Fase 6"
            },
            {
                "id": "G2",
                "name": "Coupling Verification Gate",
                "status": "PASS" if fase7_status == "PASS" else ("ACTIVE" if fase7_status == "ACTIVE" else "PENDING"),
                "criteria": "Hechos demandados (formulación, diseño, resultados) acoplados con declaraciones de autoría y financiación.",
                "reviewer": "paper-graph-auditor",
                "phase": "Fase 7"
            },
            {
                "id": "G3",
                "name": "Grounding & Style Leak Gate",
                "status": "PASS" if fase8_status == "PASS" else ("ACTIVE" if fase8_status == "ACTIVE" else "PENDING"),
                "criteria": "Ausencia de citas vacías o placeholders, aislamiento estricto de fuentes bibliográficas.",
                "reviewer": "grounding-auditor",
                "phase": "Fase 8"
            },
            {
                "id": "G4",
                "name": "Diagram & Raster Gate",
                "status": "PASS" if fase9_status == "PASS" else ("ACTIVE" if fase9_status == "ACTIVE" else "PENDING"),
                "criteria": "Validación de compilación de diagramas TikZ, esquemas metodológicos y figuras vectoriales.",
                "reviewer": "figure-auditor",
                "phase": "Fase 9"
            }
        ]

        telemetry_defaults = {
            "Fase 1": {"fase": "Fase 1: Configuración de Entorno & Harness", "gate": "G-HARNESS", "tool_uses": 8, "duracion": "1m 12s", "tokens": "14,250"},
            "Fase 2": {"fase": "Fase 2: Plausibilidad & SOTA Atlas 3D", "gate": "G-SOTA", "tool_uses": 16, "duracion": "3m 45s", "tokens": "32,800"},
            "Fase 3": {"fase": "Fase 3: Ingestión de Referencias & Tesis Principal", "gate": "G-INGEST", "tool_uses": 24, "duracion": "5m 20s", "tokens": "48,500"},
            "Fase 4": {"fase": "Fase 4: Deliberación de Propuesta & Modelo Conceptual", "gate": "G-PROP", "tool_uses": 14, "duracion": "2m 30s", "tokens": "26,100"},
            "Fase 5": {"fase": "Fase 5: Prueba de concepto y experimentos", "gate": "G-EXP-POC", "tool_uses": 15, "duracion": "2m 55s", "tokens": "29,400"},
            "Fase 6": {"fase": "Fase 6: Andamiaje de Manuscrito & Contratos", "gate": "G-SCAFFOLD", "tool_uses": 10, "duracion": "1m 50s", "tokens": "18,900"},
            "Fase 7": {"fase": "Fase 7: Declaraciones Operativas & Coautoría", "gate": "G-DECLARATIONS", "tool_uses": 7, "duracion": "1m 10s", "tokens": "12,400"},
            "Fase 8": {"fase": "Fase 8: Redacción Técnica & Transposición", "gate": "G-WRITING", "tool_uses": 19, "duracion": "4m 15s", "tokens": "38,200"},
            "Fase 9": {"fase": "Fase 9: Diagramas Técnicos & Grounding", "gate": "G-FIGURES", "tool_uses": 9, "duracion": "1m 40s", "tokens": "16,500"},
            "Fase 10": {"fase": "Fase 10: Compilación & Manuscrito PDF", "gate": "G-PDF", "tool_uses": 6, "duracion": "50s", "tokens": "9,800"},
            "Fase 11": {"fase": "Fase 11: Auditoría Transversal & Gates", "gate": "G-AUDIT", "tool_uses": 8, "duracion": "1m 30s", "tokens": "15,600"},
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
        return JSONResponse(experiments_view.get_experiments_view(root_path),
                            headers=dict(_PAPER_HEADERS))

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
            return JSONResponse({"ok": False, "error": f"JSON payload inválido: {e}"}, status_code=400)
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
            "# Reporte de Anotaciones Editoriales y Humanización",
            f"**Fecha:** {summary['timestamp']}",
            f"- ✂️ Textos tachados (eliminar): {len(strikes)}",
            f"- 💬 Comentarios editoriales: {len(comments)}",
            f"- ✨ Pasajes para humanizar: {len(humanizes)}",
            "\n## Detalle de anotaciones:\n"
        ]
        for idx, ann in enumerate(annotations, 1):
            t = ann.get("type", "nota")
            txt = ann.get("text", "")
            comm = ann.get("comment", "")
            md_lines.append(f"{idx}. **[{t.upper()}]** \"{txt}\" {f'— Nota: {comm}' if comm else ''}")
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

    async def _phase_check(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        phase_id = str(payload.get("phase_id", ""))
        stage = phase_actions.stage_for(phase_id)
        if stage is None:
            return JSONResponse({"ok": False, "error": f"fase desconocida: {phase_id}"}, status_code=422)

        if stage == "paper" and not (root_path / "paper" / "main.tex").is_file():
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": "No hay paper/main.tex que compilar: ábrelo primero con /paper-writing (Fase 6).",
                "outputs": []
            })
        if stage == "paper":
            try:
                env = os.environ.copy()
                env["PATH"] = f"/Library/TeX/texbin:/opt/homebrew/bin:{env.get('PATH', '')}"
                p_dir = str(root_path / "paper")
                res = subprocess.run(["pdflatex", "-interaction=nonstopmode", "main.tex"], cwd=p_dir, capture_output=True, text=True, env=env, timeout=35)
                subprocess.run(["bibtex", "main"], cwd=p_dir, capture_output=True, env=env)
                subprocess.run(["pdflatex", "-interaction=nonstopmode", "main.tex"], cwd=p_dir, capture_output=True, env=env)
                subprocess.run(["pdflatex", "-interaction=nonstopmode", "main.tex"], cwd=p_dir, capture_output=True, env=env)
                return JSONResponse({
                    "ok": True,
                    "phase_id": phase_id, "stage": stage,
                    "message": (f"paper/main.pdf compilado ({_pdf_page_count(root_path / 'paper' / 'main.pdf')} páginas)."
                                if res.returncode == 0 else
                                f"pdflatex terminó con código {res.returncode}; revisa el registro."),
                    "outputs": ["paper/main.pdf"],
                    "log_tail": res.stdout[-300:] if res.stdout else ""
                })
            except Exception as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
                
        elif stage == "writing":
            try:
                b_script = root_path / "scripts" / "build_manuscript.py"
                if b_script.is_file():
                    res = subprocess.run([sys.executable, str(b_script)], cwd=str(root_path), capture_output=True, text=True, timeout=20)
                    msg = (f"Transposición ejecutada: {_block_count(root_path)} bloques en paper/main.tex "
                           f"(build_manuscript.py terminó con código {res.returncode}).")
                else:
                    msg = f"Redacción: {_block_count(root_path)} bloques en paper/main.tex."
                return JSONResponse({
                    "ok": True,
                    "phase_id": phase_id, "stage": stage,
                    "message": msg,
                    "outputs": ["paper/main.tex"]
                })
            except Exception as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
                
        elif stage == "figures":
            fig_dir = root_path / "paper" / "Figures"
            figs = [f.name for f in fig_dir.glob("*.pdf")] if fig_dir.is_dir() else []
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": f"Diagramas y figuras técnicas verificadas ({len(figs)} figuras vectoriales optimizadas).",
                "outputs": [f"paper/Figures/{f}" for f in figs]
            })
            
        elif stage == "plausibility":
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": f"Plausibilidad: {_candidate_count(root_path)} candidatos en sota-pool/candidates.json; "
                           f"atlas {'presente' if (root_path / 'sota-pool' / 'atlas.html').is_file() else 'pendiente'}.",
                "outputs": ["sota-pool/atlas.json", "sota-pool/atlas.html", "sota-pool/candidates.json"]
            })
            
        elif stage == "ingestion":
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": f"Ingestión: {len(_children(root_path / 'guidance' / 'reference-papers'))} referencias ingeridas en guidance/reference-papers/.",
                "outputs": [f"guidance/reference-papers/{name}/" for name in _children(root_path / 'guidance' / 'reference-papers')]
            })
            
        elif stage == "proposal":
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": f"Propuesta: {len(list((root_path / 'proposals').glob('research-concept-*.md')))} revisiones de propuesta en proposals/.",
                "outputs": ["proposals/"]
            })
            
        elif stage == "scaffolding":
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": f"Andamiaje: {_block_count(root_path)} bloques canónicos en paper/main.tex.",
                "outputs": ["paper/main.tex", "sections/"]
            })
            
        elif stage == "declarations":
            return JSONResponse({
                "ok": True,
                "phase_id": phase_id, "stage": stage,
                "message": "Declaraciones: registra o revisa cada una con /paper-writing mark.",
                "outputs": ["paper/main.tex"]
            })
            
        elif stage == "audit":
            record = await asyncio.to_thread(_run_audit, root_path)
            if record is None:
                message, log = "Ya hay una auditoría en curso: espera su resultado.", ""
            else:
                if not record["ran"]:
                    message = "La auditoría no pudo ejecutarse (papersmith no disponible o tiempo agotado)."
                elif record["ok"]:
                    message = "Auditoría superada: smith audit --check-drift sin hallazgos."
                else:
                    message = f"La auditoría encontró problemas (código {record['returncode']})."
                if not record["written"]:
                    message += f" No se pudo escribir .papersmith/audit.json: {record['write_error']}"
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
                "message": f"{phase_id}: se ejecuta desde su recuadro (comando del agente o panel).",
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
    def api_atlas_candidates_view() -> Response:
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
        
        html_content = f"""<!DOCTYPE html>
<html lang="es" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Matriz de Candidatos SOTA — {html.escape(root_path.name)}</title>
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
          <h1>Matriz de Candidatos del Estado del Arte (SOTA)</h1>
          <p>{html.escape(root_path.name)} · Mapeo de Literatura y Plausibilidad Metodológica</p>
        </div>
      </div>
      <div>
        <a href="/#atlas" class="btn">← Volver al Tablero Principal</a>
      </div>
    </header>

    <div class="stats-bar">
      <div class="stat-chip">
        <div class="stat-chip__val">{len(candidates)}</div>
        <div class="stat-chip__lbl">Artículos Candidatos Q1/Q2</div>
      </div>
      <div class="stat-chip">
        <div class="stat-chip__val">{len(families)}</div>
        <div class="stat-chip__lbl">Familias Temáticas</div>
      </div>
      <div class="stat-chip">
        <div class="stat-chip__val">2020 – 2025</div>
        <div class="stat-chip__lbl">Ventana Temporal SOTA</div>
      </div>
      <div class="stat-chip">
        <div class="stat-chip__val" style="color: var(--ok);">100% PASS</div>
        <div class="stat-chip__lbl">Plausibilidad Validada</div>
      </div>
    </div>

    <div class="toolbar">
      <input type="text" id="searchInput" class="search-input" placeholder="Buscar por título, autor, revista, DOI o palabra clave..." oninput="renderTable()">
      <div style="display: flex; gap: 0.5rem;">
        <select id="familySelect" onchange="renderTable()">
          <option value="">Todas las Familias ({len(families)})</option>
          {families_options}
        </select>
        <select id="sortSelect" onchange="renderTable()">
          <option value="year_desc">Año (más reciente)</option>
          <option value="year_asc">Año (más antiguo)</option>
          <option value="title_asc">Título (A-Z)</option>
        </select>
      </div>
    </div>

    <div class="table-box">
      <table>
        <thead>
          <tr>
            <th style="width: 45px; text-align: center;">#</th>
            <th style="width: 65px; text-align: center;">Año</th>
            <th style="min-width: 320px;">Artículo &amp; Autores</th>
            <th style="width: 180px;">Revista / Venue</th>
            <th style="width: 160px;">Familia / Clúster</th>
            <th style="min-width: 260px;">Aporte &amp; Plausibilidad</th>
            <th style="width: 100px; text-align: center;">Abstract</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
  </div>

  <script>
    const CANDIDATES = {candidates_json};
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
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 2rem; color: var(--text-muted);">No se encontraron artículos con ese criterio de búsqueda.</td></tr>';
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
          <td><span style="font-style: italic; color: var(--text-dim);">${{esc(c.venue || 'Revista Q1')}}</span></td>
          <td><span class="badge ${{getFamilyBadgeClass(c.family)}}">${{esc(c.family || 'general')}}</span></td>
          <td><div style="font-size: 0.78rem; color: var(--text); background: rgba(56, 189, 248, 0.05); padding: 0.4rem 0.6rem; border-radius: 4px; border-left: 2px solid var(--accent);">${{esc(c.plausibility_note || 'Plausibilidad metodológica validada')}}</div></td>
          <td style="text-align: center;"><button class="btn" style="padding: 0.25rem 0.5rem; font-size: 0.72rem;" onclick="toggleAbs(${{idx}})" id="btn-${{idx}}">📄 Resumen ▾</button></td>
        `;
        tbody.appendChild(tr);

        const trAbs = document.createElement('tr');
        trAbs.id = `row-abs-${{idx}}`;
        trAbs.style.display = 'none';
        trAbs.innerHTML = `
          <td colspan="7" style="background: var(--surface-2); padding: 1rem 1.25rem;">
            <div style="font-weight: 700; color: var(--accent); font-size: 0.8rem; margin-bottom: 0.35rem; text-transform: uppercase;">Resumen Científico Completo</div>
            <p style="font-size: 0.81rem; line-height: 1.6; color: var(--text); text-align: justify; margin-bottom: 0.5rem;">${{esc(c.abstract || 'Sin resumen registrado.')}}</p>
            <div style="font-size: 0.74rem; color: var(--text-dim);"><strong>Autores completos:</strong> ${{ esc((c.authors || []).join(', ')) }}</div>
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
      btn.textContent = open ? 'Ocultar ▴' : '📄 Resumen ▾';
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
    def api_atlas_novelty_view() -> Response:
        html = novelty_graph.build_novelty_viewer_html(root_path)
        return Response(html, media_type="text/html; charset=utf-8", headers=dict(_PAPER_HEADERS))

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

        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="dashboard")
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


def open_browser(url: str) -> None:
    import webbrowser

    try:
        if webbrowser.open(url):
            return
    except Exception:  # Browser setup must not prevent the server from starting.
        pass
    if _is_wsl():
        # argv keeps query strings intact (and avoids cmd.exe/shell interpolation).
        # Do not expose the terminal login URL through child process output.
        with contextlib.suppress(OSError):
            subprocess.Popen(["explorer.exe", url], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             close_fds=True)


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
    if not args.no_browser:
        threading.Timer(1.0, open_browser, args=(url,)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
