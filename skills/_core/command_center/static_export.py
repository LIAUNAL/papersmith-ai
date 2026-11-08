"""A static, read-only snapshot of the dashboard (``smith ui --export-snapshot``).

The snapshot is a folder a static host (GitHub Pages) can serve: the shipped
``static/`` assets, and every read-only GET the dashboard makes, answered once
in-process by the real backend and written as files indexed in
``snapshot/manifest.json``. ``static/snapshot.js`` (inert in the live
dashboard) maps the page's ``/api/...`` requests to those files, refuses every
write and hides the controls that run something.

A Pages site is public even for a private repository, so the snapshot carries
an allow-list only: no terminal or doctor routes, no team members, accounts or
credential status, no operator PDF annotations, nothing under ``guidance/``,
and no absolute workspace or home path (they become ``.`` and ``~``). The AI
History tab and its conversations are included unless ``ai_history=False``
(``--no-ai-history``). Every text answer passes through
``ai_archive.redact_public``: credentials become ``[secret]``, addresses
``[email]``, and the people the workspace declares (authors, team members, the
operator) ``[author-N]``, ``[member-N]`` and ``[user]``; a name typed free-form
that the workspace does not declare cannot be recognized. Binary answers (the
PDF, figures) are copied as they are. Exporting writes nothing into the
workspace: the AI-archive sync that ``/api/status`` starts and the novelty
viewer's copy are switched off for the duration.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import quote

#: Cache-buster parameters the dashboard appends; they never change an answer.
DROPPED_PARAMS = frozenset({"v", "t", "fresh"})

#: Read-only routes the shipped dashboard requests with fixed parameters.
STATIC_ROUTES = (
    "/api/status", "/api/model", "/api/model/steps", "/api/model/math", "/api/citations",
    "/api/experiments", "/api/agents", "/api/novelty/status", "/api/atlas/manuscript-graph",
    "/api/atlas/manuscript", "/api/atlas/coverage", "/api/candidates", "/api/atlas/cited-papers",
    "/api/paper/qa", "/api/journals", "/api/venues", "/api/flow", "/api/atlas/view",
    "/api/atlas/manuscript-graph/view", "/api/atlas/candidates/view", "/api/atlas/novelty/view",
    "/api/pdf",
)

#: Routes never exported; the shim answers them "not in this snapshot".
EXCLUDED_ROUTES = ("/api/doctor", "/api/terminal/*")
#: The AI History tab, exported unless ``ai_history=False`` (``--no-ai-history``).
AI_HISTORY_ROUTES = ("/api/ai-history", "/api/ai-history/session")

#: The operator's PDF notes are private: the snapshot answers "none".
EMPTY_ANNOTATIONS = {"timestamp": None, "annotations": [], "applied": {}}

#: Top-level `/api/experiments` sections that describe accounts, credentials
#: and the local machine rather than the research.
EXPERIMENT_SECTIONS_DROPPED = ("remote_accounts", "remote_mcp", "remote_colab", "remote_services",
                               "local_environment", "run_options")
#: Keys dropped wherever they occur inside `/api/experiments`.
EXPERIMENT_KEYS_DROPPED = frozenset({
    "remote_workers", "placement_plan", "accounts", "worker", "submission_id", "kaggle_username",
    "email", "emails", "members", "team", "token_path", "user",
})

#: Extensions an allow-listed artifact may have.
ARTIFACT_SUFFIXES = frozenset({".md", ".txt", ".json", ".jsonl", ".csv", ".tsv", ".png", ".jpg",
                               ".jpeg", ".gif", ".svg", ".pdf", ".tex", ".bib", ".yaml", ".yml"})
#: Path parts that keep a file out of the snapshot even when a panel links it.
#: Top-level folders never copied: `guidance/` holds the operator's drop-zone
#: and the full text of third-party reference papers.
ARTIFACT_DENIED_ROOTS = frozenset({"guidance"})
ARTIFACT_DENIED_PARTS = frozenset({"ai-history", "cache", "caches", "node_modules", "kaggle-inbox",
                                   "team.json", "accounts.json", "secrets"})
#: Larger answers are left out (a Pages site has a 1 GB budget).
MAX_ANSWER_BYTES = 50 * 1024 * 1024

EXTENSIONS = {
    "application/json": ".json", "text/html": ".html", "application/pdf": ".pdf",
    "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/gif": ".gif",
    "image/svg+xml": ".svg", "text/plain": ".txt", "text/markdown": ".md",
}
TEXT_TYPES = ("application/json", "text/", "image/svg+xml")
#: Answers whose scripts must survive the scrub (see ``redact_public(code=True)``).
CODE_TYPES = ("text/html", "image/svg+xml")


class SnapshotError(ValueError):
    """A refusal the CLI reports as a one-line message (exit code 2)."""


# --------------------------------------------------------------------------
# request keys (mirrored by static/snapshot.js)
# --------------------------------------------------------------------------
def _encode(text: str) -> str:
    # Exactly what encodeURIComponent leaves unescaped.
    return quote(text, safe="!*'()")


def request_key(path: str, params: dict[str, str] | None = None) -> str:
    """The manifest key of a GET: its path and sorted query, without
    cache-busters and without ``lang=en`` (English is the default answer).
    ``/api/artifact`` takes ``file=`` and ``path=`` alike; both become ``path``."""
    query: dict[str, str] = {}
    for name, value in (params or {}).items():
        if name in DROPPED_PARAMS or (name == "lang" and value == "en"):
            continue
        if path == "/api/artifact" and name == "file":
            name = "path"
        query[name] = str(value)
    if not query:
        return path
    return path + "?" + "&".join(f"{_encode(k)}={_encode(v)}" for k, v in sorted(query.items()))


def _media_type(content_type: str) -> str:
    return (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()


def _file_for(key: str, media_type: str) -> str:
    path, _, query = key.partition("?")
    params = dict(part.split("=", 1) for part in query.split("&") if "=" in part) if query else {}
    lang = "es" if params.get("lang") == "es" else "en"
    segments = [_safe_segment(part) for part in path.strip("/").split("/") if part]
    name = "/".join(segments)
    if query:
        name += "__" + hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
    return f"snapshot/{lang}/{name}{EXTENSIONS.get(media_type, '.bin')}"


def _safe_segment(part: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in part)
    return cleaned.strip(".") or "_"


# --------------------------------------------------------------------------
# scrubbing
# --------------------------------------------------------------------------
def scrub_experiments(view: Any) -> Any:
    """`/api/experiments` without accounts, credentials or local paths."""
    if isinstance(view, dict):
        view = {key: value for key, value in view.items() if key not in EXPERIMENT_SECTIONS_DROPPED}

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: walk(value) for key, value in node.items() if key not in EXPERIMENT_KEYS_DROPPED}
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(view)


def _path_replacements(root: Path) -> list[tuple[str, str]]:
    pairs = [(str(root), "."), (str(Path.home()), "~")]
    out: list[tuple[str, str]] = []
    for needle, replacement in pairs:
        if len(needle) > 1:
            out.append((needle, replacement))
            escaped = json.dumps(needle)[1:-1]
            if escaped != needle:
                out.append((escaped, replacement))
    return out


#: Any other machine's home directory (a teammate's run records it): the
#: user name and everything above it become ``~``.
OTHER_HOME = re.compile(r"(?<![\w.~])(?:/Users|/home|[A-Za-z]:(?:\\\\|\\)Users)(?:/|\\\\|\\)[^/\\\s\"'<>]+")


def _clean(text: str, replacements: list[tuple[str, str]],
           identities: tuple[tuple[str, str], ...] = (), *, code: bool = False) -> str:
    """One string fit for the public snapshot: the workspace and home paths
    relative, then ``ai_archive.redact_public`` (credentials, addresses, the
    workspace's people), then any other machine's home directory."""
    from . import ai_archive

    for needle, replacement in replacements:
        text = text.replace(needle, replacement)
    return OTHER_HOME.sub("~", ai_archive.redact_public(text, identities, code=code))


def _scrub_text(data: bytes, replacements: list[tuple[str, str]],
                identities: tuple[tuple[str, str], ...] = (), *, code: bool = False) -> bytes:
    return _clean(data.decode("utf-8", errors="replace"), replacements, identities,
                  code=code).encode("utf-8")


def _scrub_json(node: Any, replacements: list[tuple[str, str]],
                identities: tuple[tuple[str, str], ...]) -> Any:
    """Every string of a JSON document, keys included, through :func:`_clean`."""
    if isinstance(node, dict):
        return {_clean(key, replacements, identities) if isinstance(key, str) else key:
                _scrub_json(value, replacements, identities) for key, value in node.items()}
    if isinstance(node, list):
        return [_scrub_json(item, replacements, identities) for item in node]
    if isinstance(node, str):
        return _clean(node, replacements, identities)
    return node


def _chat_refs(history: Any) -> list[str]:
    """The ``ref`` of every chat event the AI History lists, for its sessions."""
    refs: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("source") == "chats" and isinstance(node.get("ref"), str) and ":" in node["ref"]:
                refs.append(node["ref"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(history)
    return _unique(refs)


def _event_paths(history: Any) -> list[str]:
    paths: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("path"), str):
                paths.append(node["path"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(history)
    return paths


# --------------------------------------------------------------------------
# allow-list of workspace files
# --------------------------------------------------------------------------
def _allowed_artifact(root: Path, rel: str) -> bool:
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel:
        return False
    parts = PurePosixPath(rel).parts
    if not parts or any(part in ("..", "") or part.startswith(".") for part in parts):
        return False
    if parts[0] in ARTIFACT_DENIED_ROOTS or any(part.lower() in ARTIFACT_DENIED_PARTS for part in parts):
        return False
    if PurePosixPath(rel).suffix.lower() not in ARTIFACT_SUFFIXES:
        return False
    target = root / rel
    try:
        resolved = target.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return False
    return target.is_file() and not target.is_symlink() and target.stat().st_size <= MAX_ANSWER_BYTES


def _experiment_paths(view: Any) -> list[str]:
    """Every file the experiments panel links: figures, tables, evidence,
    run sources and dataset searches."""
    found: list[str] = []

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                walk(value, name)
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif isinstance(node, str) and key in ("path", "file", "sources", "searches", "png", "image"):
            found.append(node)

    walk(view)
    return found


def _citation_ids(*documents: Any) -> list[str]:
    ids: list[str] = []

    def walk(node: Any, under_citations: bool = False) -> None:
        if isinstance(node, dict):
            if under_citations and isinstance(node.get("id"), str):
                ids.append(node["id"])
            for name, value in node.items():
                walk(value, name == "citations")
        elif isinstance(node, list):
            for item in node:
                walk(item, under_citations)

    for document in documents:
        walk(document)
    return ids


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------
def _project_name(root: Path, status: Any) -> str:
    if isinstance(status, dict):
        name = status.get("project_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return root.name


def _prepare_destination(out_dir: Path) -> None:
    if out_dir.exists():
        if not out_dir.is_dir():
            raise SnapshotError(f"destination is not a directory: {out_dir}")
        if any(out_dir.iterdir()):
            previous = (out_dir / "snapshot" / "manifest.json").is_file() and (out_dir / "index.html").is_file()
            if not previous:
                raise SnapshotError(f"destination is not empty: {out_dir}")
            # A previous snapshot is replaced as a whole.
            for child in out_dir.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)


def export_snapshot(root: Path | str, out_dir: Path | str, *,
                    languages: tuple[str, ...] = ("en", "es"),
                    ai_history: bool = True,
                    report: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Write the snapshot of the workspace at ``root`` into ``out_dir``.

    The snapshot is built in a staging folder beside ``out_dir`` and replaces a
    previous one only once it is complete, so a failed export leaves the old
    snapshot in place."""
    final = Path(out_dir).expanduser().resolve()
    if final.exists() and any(final.iterdir()):
        previous = (final / "snapshot" / "manifest.json").is_file() and (final / "index.html").is_file()
        if not previous:
            raise SnapshotError(f"destination is not empty: {final}")
    final.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=final.parent))
    try:
        result = _export_into(root, staging, languages=languages, ai_history=ai_history, report=report)
        _prepare_destination(final)
        for child in staging.iterdir():
            shutil.move(str(child), str(final / child.name))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    result["out"] = str(final)
    return result


def _export_into(root: Path | str, out_dir: Path | str, *,
                 languages: tuple[str, ...] = ("en", "es"),
                 ai_history: bool = True,
                 report: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Write the snapshot of the workspace at ``root`` into ``out_dir`` and
    return its counts: routes, files, bytes, excluded and missing.

    ``ai_history`` exports the AI History tab and every conversation it lists;
    like every other text, they pass through ``ai_archive.redact_public``."""
    root = Path(root).expanduser().resolve()
    out_dir = Path(out_dir).expanduser().resolve()
    if not (root / "papersmith.yaml").is_file():
        raise SnapshotError(f"{root} is not a papersmith workspace (no papersmith.yaml)")
    languages = tuple(dict.fromkeys(lang for lang in languages if lang in ("en", "es")))
    if not languages:
        raise SnapshotError("no supported language: use en, es or en,es")
    try:
        out_dir.relative_to(root / ".papersmith")
        raise SnapshotError("the snapshot cannot go under .papersmith/")
    except ValueError:
        pass
    _prepare_destination(out_dir)

    from fastapi.testclient import TestClient

    from . import server

    from . import ai_archive

    replacements = _path_replacements(root)
    identities = ai_archive.public_identities(root)
    entries: dict[str, dict[str, Any]] = {}
    by_digest: dict[str, str] = {}
    missing: list[str] = []
    skipped: list[str] = []
    written = {"files": 0, "bytes": 0}

    def store(key: str, body: bytes, media_type: str, status: int) -> None:
        if media_type == "application/json":
            try:
                body = json.dumps(_scrub_json(json.loads(body), replacements, identities),
                                  ensure_ascii=False).encode("utf-8")
            except ValueError:
                body = _scrub_text(body, replacements, identities)
        elif media_type.startswith(TEXT_TYPES):
            body = _scrub_text(body, replacements, identities, code=media_type in CODE_TYPES)
        digest = hashlib.sha256(body + media_type.encode()).hexdigest()
        rel = by_digest.get(digest)
        if rel is None:
            rel = _file_for(key, media_type)
            target = out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            by_digest[digest] = rel
            written["files"] += 1
            written["bytes"] += len(body)
        entries[key] = {"file": rel, "type": media_type, "status": status}

    saved_sync = server.ai_archive.sync_in_background
    saved_env = os.environ.get("PYTHONDONTWRITEBYTECODE")
    saved_bytecode = sys.dont_write_bytecode
    saved_viewer_copy = server.novelty_graph.WRITE_VIEWER_COPY
    server.ai_archive.sync_in_background = lambda *_args, **_kwargs: None
    server.novelty_graph.WRITE_VIEWER_COPY = False
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    try:
        app = server.create_app(root, history_store=None, enable_terminal=False)
        client = TestClient(app, raise_server_exceptions=False)

        def get(path: str, params: dict[str, str]) -> tuple[int, bytes, str] | None:
            try:
                response = client.get(path, params=params)
            except Exception:  # noqa: BLE001 - one failing route never stops the export
                return None
            return response.status_code, response.content, _media_type(response.headers.get("content-type", ""))

        def first_json(path: str) -> Any:
            answer = get(path, {})
            if answer is None or answer[0] != 200 or answer[2] != "application/json":
                return None
            try:
                return json.loads(answer[1])
            except ValueError:
                return None

        status = first_json("/api/status")
        experiments = first_json("/api/experiments")
        citations = first_json("/api/citations")
        qa = first_json("/api/paper/qa")
        venues = first_json("/api/venues")
        history = first_json("/api/ai-history") if ai_history else None

        artifacts: list[str] = []
        if isinstance(status, dict):
            artifacts += [item.get("rel_path") for item in status.get("artifacts") or []
                          if isinstance(item, dict)]
            artifacts += [f"sections/{item.get('filename')}" for item in status.get("sections") or []
                          if isinstance(item, dict) and item.get("filename")]
        artifacts += _experiment_paths(experiments)
        artifacts += _event_paths(history)
        artifacts.append("paper/journal-candidates.md")
        artifacts = [rel for rel in _unique([a for a in artifacts if isinstance(a, str)])
                     if _allowed_artifact(root, rel)]
        allowed_artifacts = set(artifacts)

        requests: list[tuple[str, dict[str, str]]] = [(route, {}) for route in STATIC_ROUTES]
        if ai_history:
            requests.append(("/api/ai-history", {}))
            requests += [("/api/ai-history/session", {"ref": ref}) for ref in _chat_refs(history)]
        requests += [("/api/artifact", {"path": rel}) for rel in artifacts]
        requests += [("/api/atlas/reference", {"id": ref}) for ref in _unique(_citation_ids(citations))]
        if isinstance(status, dict):
            for item in status.get("sections") or []:
                if isinstance(item, dict) and item.get("filename"):
                    requests.append(("/api/section-translation",
                                     {"lang": "es", "file": str(item["filename"])}))
        report_doc = qa.get("report") if isinstance(qa, dict) else None
        qa_pages = report_doc.get("pages") if isinstance(report_doc, dict) else None
        for page in qa_pages if isinstance(qa_pages, list) else []:
            if isinstance(page, dict) and page.get("png") and isinstance(page.get("page"), int):
                requests.append(("/api/paper/qa/page", {"n": str(page["page"])}))
        venue_list = venues.get("venues") if isinstance(venues, dict) else None
        for venue in venue_list if isinstance(venue_list, list) else []:
            slug = venue.get("slug") if isinstance(venue, dict) else None
            if isinstance(slug, str) and slug:
                requests.append((f"/api/venues/{slug}", {}))
                requests.append(("/api/pdf", {"venue": slug}))

        for lang in languages:
            for path, params in requests:
                query = dict(params)
                if lang != "en" and "lang" not in query:
                    query["lang"] = lang
                key = request_key(path, query)
                if key in entries:
                    continue
                if report is not None:
                    report(f"snapshot: {key}")
                answer = get(path, query)
                if answer is None or answer[0] >= 500:
                    missing.append(key)
                    continue
                code, body, media_type = answer
                if len(body) > MAX_ANSWER_BYTES:
                    skipped.append(key)
                    continue
                if code >= 400:
                    missing.append(key)
                if path == "/api/experiments" and media_type == "application/json":
                    body = json.dumps(scrub_experiments(json.loads(body)), ensure_ascii=False).encode("utf-8")
                elif path == "/api/status" and media_type == "application/json":
                    doc = json.loads(body)
                    if isinstance(doc, dict) and isinstance(doc.get("artifacts"), list):
                        doc["artifacts"] = [item for item in doc["artifacts"] if isinstance(item, dict)
                                            and item.get("rel_path") in allowed_artifacts]
                    body = json.dumps(doc, ensure_ascii=False).encode("utf-8")
                store(key, body, media_type, code)
            store(request_key("/api/pdf/annotations", {"lang": lang}),
                  json.dumps(EMPTY_ANNOTATIONS).encode("utf-8"), "application/json", 200)
    finally:
        server.ai_archive.sync_in_background = saved_sync
        server.novelty_graph.WRITE_VIEWER_COPY = saved_viewer_copy
        sys.dont_write_bytecode = saved_bytecode
        if saved_env is None:
            os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
        else:
            os.environ["PYTHONDONTWRITEBYTECODE"] = saved_env

    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    workspace_name = _clean(_project_name(root, status), replacements, identities)
    manifest = {"version": 1, "generated": generated, "workspace": workspace_name,
                "languages": list(languages), "ai_history": bool(ai_history),
                "entries": dict(sorted(entries.items()))}
    (out_dir / "snapshot").mkdir(parents=True, exist_ok=True)
    (out_dir / "snapshot" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "snapshot" / "missing.html").write_text(MISSING_PAGE, encoding="utf-8")

    static_dir = Path(__file__).resolve().parent / "static"
    shutil.copytree(static_dir, out_dir, dirs_exist_ok=True)
    page = (static_dir / "index.html").read_text(encoding="utf-8")
    (out_dir / "index.html").write_text(
        build_index(page, manifest, {"generated": generated, "workspace": workspace_name}),
        encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    return {"out": str(out_dir), "routes": len(entries), "files": written["files"],
            "bytes": written["bytes"], "excluded": list(EXCLUDED_ROUTES) + ([] if ai_history else list(AI_HISTORY_ROUTES)),
            "ai_history": bool(ai_history),
            "missing": sorted(set(missing)), "skipped": skipped, "generated": generated,
            "workspace": workspace_name}


MISSING_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Not in this snapshot</title>
<style>body{font-family:system-ui,sans-serif;margin:3rem;color:#556}</style></head>
<body><p>This view is not part of the read-only snapshot.</p></body></html>
"""

#: Scripts the static page does without: the support terminal and its xterm.
DROPPED_SCRIPTS = ("./vendor/xterm.js", "./vendor/xterm-addon-fit.js", "./cli-console.js")


def _script_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _rewrite_markup(markup: str, entries: dict[str, dict[str, Any]]) -> str:
    """Point root-absolute ``src``/``href`` attributes of the markup (never of
    inline scripts) at their snapshot files, keeping the original URL in
    ``data-ps-src`` for the shim's ``iframe.src`` getter."""
    from html import unescape
    from urllib.parse import parse_qsl, urlsplit

    attribute = re.compile(r'(\s(?:src|href)=)"(/[^"/][^"]*)"')

    def replace(match: re.Match) -> str:
        original = match.group(2)
        parts = urlsplit(unescape(original))
        if parts.path.startswith("/api/"):
            entry = entries.get(request_key(parts.path, dict(parse_qsl(parts.query))))
            target = entry["file"] if entry else "snapshot/missing.html"
        else:
            target = original.lstrip("/")
        return f'{match.group(1)}"{target}" data-ps-src="{original}"'

    pieces = re.split(r"(<script\b.*?</script>)", markup, flags=re.S | re.I)
    return "".join(piece if piece.lower().startswith("<script") else attribute.sub(replace, piece)
                   for piece in pieces)


def build_index(page: str, manifest: dict[str, Any], info: dict[str, Any]) -> str:
    """The shipped page, set up for the snapshot: the manifest and its
    metadata inline before ``snapshot.js``, no terminal scripts, and the
    markup's ``/api`` URLs pointing at their files."""
    for script in DROPPED_SCRIPTS:
        page = re.sub(r'<script src="' + re.escape(script) + r'(\?[^"]*)?"></script>\n?', "", page)
    page = re.sub(r'<link rel="stylesheet" href="\./vendor/xterm\.css">\n?', "", page)
    marker = '<script src="./snapshot.js'
    if marker not in page:
        raise SnapshotError("the shipped index.html does not load snapshot.js")
    config = ("<script>window.PAPERSMITH_STATIC = " + _script_json(info) + ";\n"
              "window.PAPERSMITH_SNAPSHOT_MANIFEST = " + _script_json(manifest) + ";</script>\n")
    head, tail = page.split(marker, 1)
    # The config script sits on the line before snapshot.js, so the script
    # order stays i18n.js -> snapshot.js.
    page = head + config + marker + tail
    return _rewrite_markup(page, manifest["entries"])


__all__ = ["export_snapshot", "request_key", "scrub_experiments", "build_index", "SnapshotError"]
