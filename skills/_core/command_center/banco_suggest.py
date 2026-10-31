"""Thematic help for the plausibility phase: 3 to 5 keywords in, the best
matching Banco LIA items and topics plus a proposed ``/plausibility`` idea out.

The bank is reached through the SAME MCP server papersmith registers for
agents (``.mcp.json`` ``mcpServers["banco-lia"]``, else the default
``uvx --from git+https://github.com/LIAUNAL/bancoProyectosPapersLIA
banco-lia-mcp``), so the help sees exactly what an agent sees. This module is
a minimal stdio JSON-RPC client (stdlib only): ``initialize``, the
``notifications/initialized`` notification, then ``tools/call`` of
``search_bank`` and ``taxonomy``, under one deadline, with the child process
always terminated.

* ``PAPERSMITH_BANCO_LIA_COMMAND`` — JSON argv list that replaces the command
  (tests, offline clones).
* ``PAPERSMITH_BANCO_LIA_TIMEOUT`` — seconds for the whole exchange (the first
  ``uvx`` run downloads the server); default 90.

``suggest`` refuses bad keywords with ``KeywordsInvalid`` (code
``KEYWORDS_INVALID``) and never raises for anything else: a missing command,
a timeout or a protocol error answers ``{"available": False, "reason": ...}``.
The draft is composed from the keywords and the matched items alone (no model
call, no invented data); the items are the lab's own background, never state
of the art. Its sentences are English templates; the Spanish ones live in
``static/i18n/server-es.json`` like every other server string.
"""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import localize

DEFAULT_COMMAND: list[str] = [
    "uvx", "--from", "git+https://github.com/LIAUNAL/bancoProyectosPapersLIA", "banco-lia-mcp"]
DEFAULT_TIMEOUT = 90.0
#: Seconds a child gets between SIGTERM and SIGKILL.
TERMINATE_GRACE = 2.0
COMMAND_ENV = "PAPERSMITH_BANCO_LIA_COMMAND"
TIMEOUT_ENV = "PAPERSMITH_BANCO_LIA_TIMEOUT"
PROTOCOL_VERSION = "2025-03-26"

MIN_KEYWORDS = 3
MAX_KEYWORDS = 5
MAX_KEYWORD_CHARS = 40
MAX_ITEMS = 8
MAX_TOPICS = 5
MAX_DRAFT_ITEMS = 3
MAX_DRAFT_TOPICS = 2
MIN_ITEMS_FOR_ALL = 3
SNIPPET_CHARS = 240


class KeywordsInvalid(ValueError):
    """The keywords break the 3-to-5 rule; ``str()`` names the rule."""

    code = "KEYWORDS_INVALID"


class _Unavailable(Exception):
    """The bank cannot be reached; the message is the one-line reason."""


class _ToolError(_Unavailable):
    """The server answered a tool call with an error."""


# --------------------------------------------------------------------------
# Keywords
# --------------------------------------------------------------------------
def normalize_keywords(raw: Any) -> list[str]:
    """Trim, reject empty/long entries, drop case-insensitive duplicates and
    require 3 to 5 keywords; otherwise raise ``KeywordsInvalid``."""
    if not isinstance(raw, (list, tuple)):
        raise KeywordsInvalid(f"keywords must be a list of {MIN_KEYWORDS} to {MAX_KEYWORDS} words or phrases")
    keywords: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, str):
            raise KeywordsInvalid("every keyword must be text")
        word = " ".join(entry.split())
        if not word:
            raise KeywordsInvalid("a keyword is empty")
        if len(word) > MAX_KEYWORD_CHARS:
            raise KeywordsInvalid(f"a keyword is longer than {MAX_KEYWORD_CHARS} characters")
        if word.casefold() not in seen:
            seen.add(word.casefold())
            keywords.append(word)
    if not MIN_KEYWORDS <= len(keywords) <= MAX_KEYWORDS:
        raise KeywordsInvalid(
            f"give {MIN_KEYWORDS} to {MAX_KEYWORDS} different keywords (got {len(keywords)})")
    return keywords


# --------------------------------------------------------------------------
# Command and timeout
# --------------------------------------------------------------------------
def _launch(root: Path | str | None) -> tuple[list[str], dict[str, str]]:
    """The argv (and extra environment) that starts the bank's MCP server."""
    override = os.environ.get(COMMAND_ENV)
    if override:
        try:
            argv = json.loads(override)
        except ValueError:
            argv = None
        if not (isinstance(argv, list) and argv and all(isinstance(a, str) and a for a in argv)):
            raise _Unavailable(f"{COMMAND_ENV} must be a JSON list of strings, e.g. [\"uvx\", \"banco-lia-mcp\"]")
        return argv, {}
    if root is not None:
        try:
            entry = json.loads((Path(root) / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["banco-lia"]
            command, args = entry["command"], entry.get("args", [])
            if isinstance(command, str) and command and isinstance(args, list) \
                    and all(isinstance(a, str) for a in args):
                env = entry.get("env")
                extra = {k: v for k, v in env.items() if isinstance(v, str)} if isinstance(env, dict) else {}
                return [command, *args], extra
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
    return list(DEFAULT_COMMAND), {}


def resolve_command(root: Path | str | None = None) -> list[str]:
    """The argv the client starts: the env override, else the workspace's
    ``.mcp.json`` entry for ``banco-lia``, else the default."""
    return _launch(root)[0]


def timeout_seconds() -> float:
    try:
        value = float(os.environ.get(TIMEOUT_ENV, ""))
    except ValueError:
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


# --------------------------------------------------------------------------
# Minimal MCP stdio client
# --------------------------------------------------------------------------
def _reason(text: str) -> str:
    return " ".join(str(text).split())[:240] or "unknown error"


class _Session:
    def __init__(self, argv: list[str], extra_env: dict[str, str], timeout: float) -> None:
        self.deadline = time.monotonic() + timeout
        self.timeout = timeout
        self.next_id = 0
        self.lines: queue.Queue[str | None] = queue.Queue()
        try:
            self.proc = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env={**os.environ, **extra_env}, text=True, encoding="utf-8", bufsize=1,
                start_new_session=(os.name == "posix"))
        except (OSError, ValueError) as exc:
            raise _Unavailable(f"cannot start {argv[0]}: {exc.strerror or exc}") from exc
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        try:
            for line in self.proc.stdout:  # type: ignore[union-attr]
                self.lines.put(line)
        except (OSError, ValueError):
            pass
        self.lines.put(None)

    def _send(self, message: dict[str, Any]) -> None:
        try:
            self.proc.stdin.write(json.dumps(message) + "\n")  # type: ignore[union-attr]
            self.proc.stdin.flush()  # type: ignore[union-attr]
        except (OSError, ValueError) as exc:
            raise _Unavailable("banco-lia server closed the connection") from exc

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})})

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.next_id += 1
        ident = self.next_id
        self._send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}})
        while True:
            try:
                line = self.lines.get(timeout=max(0.0, self.deadline - time.monotonic()))
            except queue.Empty:
                raise _Unavailable(f"timed out after {self.timeout:g} s waiting for banco-lia") from None
            if line is None:
                raise _Unavailable("banco-lia server closed the connection")
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except ValueError:
                raise _Unavailable("banco-lia sent a malformed JSON-RPC message") from None
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                raise _Unavailable("banco-lia sent a malformed JSON-RPC message")
            if message.get("id") != ident:
                continue  # a notification or a server request: not ours to answer
            if "error" in message:
                error = message["error"]
                raise _Unavailable(f"banco-lia refused {method}: "
                                   f"{_reason(error.get('message') if isinstance(error, dict) else error)}")
            if "result" not in message:
                raise _Unavailable("banco-lia sent a malformed JSON-RPC message")
            return message["result"]

    def start(self) -> None:
        self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "papersmith-dashboard", "version": "1"}})
        self.notify("notifications/initialized")

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        return _tool_payload(self.request("tools/call", {"name": name, "arguments": arguments}))

    def close(self) -> None:
        """Always leave no child behind: EOF on stdin, then SIGTERM, then SIGKILL."""
        proc = self.proc
        try:
            proc.stdin.close()  # type: ignore[union-attr]
        except (OSError, ValueError):
            pass
        try:
            proc.wait(min(0.3, TERMINATE_GRACE))
            return
        except subprocess.TimeoutExpired:
            pass
        self._signal(signal.SIGTERM)
        try:
            proc.wait(TERMINATE_GRACE)
        except subprocess.TimeoutExpired:
            self._signal(getattr(signal, "SIGKILL", signal.SIGTERM))
            proc.wait()

    def _signal(self, sig: int) -> None:
        try:
            if os.name == "posix":
                os.killpg(self.proc.pid, sig)
            elif sig == signal.SIGTERM:
                self.proc.terminate()
            else:
                self.proc.kill()
        except (ProcessLookupError, PermissionError):
            pass


def _tool_payload(result: Any) -> Any:
    """The value a ``tools/call`` result carries: ``structuredContent`` (a
    ``{"result": [...]}`` wrapper unwrapped) or the JSON of its text blocks."""
    if not isinstance(result, dict):
        raise _Unavailable("banco-lia sent a malformed tool result")
    blocks = [b for b in (result.get("content") or []) if isinstance(b, dict)]
    if result.get("isError"):
        text = " ".join(str(b.get("text", "")) for b in blocks)
        raise _ToolError(f"banco-lia tool error: {_reason(text)}")
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured["result"] if set(structured) == {"result"} else structured
    values = []
    for block in blocks:
        if block.get("type") == "text":
            try:
                values.append(json.loads(block.get("text", "")))
            except ValueError:
                raise _Unavailable("banco-lia sent a malformed tool result") from None
    return values[0] if len(values) == 1 else values


# --------------------------------------------------------------------------
# Suggestion
# --------------------------------------------------------------------------
def _hits(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = [payload]
    return [h for h in payload if isinstance(h, dict) and h.get("id")] if isinstance(payload, list) else []


def _item(hit: dict[str, Any]) -> dict[str, Any]:
    year = hit.get("year")
    try:
        score = round(float(hit.get("score", 0)), 3)
    except (TypeError, ValueError):
        score = 0.0
    return {
        "id": str(hit["id"]), "kind": str(hit.get("kind") or ""),
        "title": " ".join(str(hit.get("title") or "").split()),
        "year": year if isinstance(year, int) else None,
        "cluster": str(hit.get("cluster") or ""), "doi": str(hit.get("doi") or ""),
        "score": score, "snippet": " ".join(str(hit.get("snippet") or "").split())[:SNIPPET_CHARS],
    }


def _taxonomy_names(session: _Session) -> dict[str, str]:
    """Cluster id -> name. A failing taxonomy only costs the names."""
    try:
        clusters = session.call("taxonomy", {}).get("clusters", [])
    except (_ToolError, AttributeError):
        return {}
    return {str(c["id"]): str(c.get("name") or c["id"]) for c in clusters if isinstance(c, dict) and c.get("id")}


def _topics(items: list[dict[str, Any]], names: dict[str, str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in items:  # insertion order = best item first, so ties keep the better topic ahead
        if item["cluster"]:
            counts[item["cluster"]] = counts.get(item["cluster"], 0) + 1
    ranked = sorted(counts, key=lambda c: -counts[c])
    return [{"id": c, "name": names.get(c, c), "count": counts[c]} for c in ranked[:MAX_TOPICS]]


def suggest(keywords: Any, language: str = "es", *, root: Path | str | None = None,
            timeout: float | None = None) -> dict[str, Any]:
    """Ranked items, topics and a proposed idea for the keywords.

    Raises ``KeywordsInvalid`` for bad keywords; answers
    ``{"available": False, "reason": ...}`` when the bank cannot be reached."""
    words = normalize_keywords(keywords)
    lang = "en" if language == "en" else "es"
    session: _Session | None = None
    try:
        argv, extra_env = _launch(root)
        session = _Session(argv, extra_env, timeout if timeout is not None else timeout_seconds())
        session.start()
        query = " ".join(words)
        match = "all"
        hits = _hits(session.call("search_bank", {"query": query, "limit": MAX_ITEMS, "match": "all"}))
        if len(hits) < MIN_ITEMS_FOR_ALL:
            match = "any"
            hits = _hits(session.call("search_bank", {"query": query, "limit": MAX_ITEMS, "match": "any"}))
        items = sorted((_item(h) for h in hits), key=lambda i: -i["score"])[:MAX_ITEMS]
        topics = _topics(items, _taxonomy_names(session) if items else {})
    except _Unavailable as exc:
        return {"available": False, "reason": _reason(exc)}
    except Exception as exc:  # the dashboard must never see a traceback from the bank
        return {"available": False, "reason": _reason(f"unexpected failure talking to banco-lia: {exc}")}
    finally:
        if session is not None:
            session.close()
    return {"available": True, "keywords": words, "match": match, "items": items,
            "topics": topics, "draft": compose_draft(words, items, topics, lang)}


# --------------------------------------------------------------------------
# Draft
# --------------------------------------------------------------------------
_AND = "and"
_TOPIC = "within the topic"
_TOPICS = "within the topics"
_PROJECT = "the project"
_FOUND_1 = "I propose to explore an idea that crosses {keywords}{where} and that has no clear framing yet."
_FOUND_2 = "As the lab's (LIA) background, not as state of the art, I start from {cited}."
_FOUND_3 = ("The idea would test whether {keywords} supports a new contribution beyond that prior experience "
            "and the current literature.")
_EMPTY_1 = "I propose to explore the plausibility of an idea about {keywords}."
_EMPTY_2 = ("The LIA bank holds no related work for these keywords, so there is no lab background to build on.")
_EMPTY_3 = "The idea would test whether {keywords} supports a new contribution beyond the current literature."

#: Every template the draft can use; server-es.json holds the Spanish of each.
DRAFT_TEMPLATES = (_AND, _TOPIC, _TOPICS, _PROJECT, _FOUND_1, _FOUND_2, _FOUND_3, _EMPTY_1, _EMPTY_2, _EMPTY_3)


@lru_cache(maxsize=1)
def _spanish() -> dict[str, str]:
    try:
        return json.loads(localize.CATALOGUE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _say(template: str, lang: str, **values: str) -> str:
    """The template in ``lang`` (English when the catalogue has no entry), filled in."""
    text = _spanish().get(template, template) if lang == "es" else template
    return text.format(**values)


def _enumerate(parts: list[str], lang: str) -> str:
    if len(parts) < 2:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} {_say(_AND, lang)} {parts[-1]}"


def _cited(item: dict[str, Any], lang: str) -> str:
    """A project is background by id and title; an article by title and DOI."""
    if item["kind"] == "proyecto":
        return f"{_say(_PROJECT, lang)} {item['id']} \"{item['title']}\""
    return f"\"{item['title']}\" (DOI {item['doi']})" if item["doi"] else f"\"{item['title']}\""


def compose_draft(keywords: list[str], items: list[dict[str, Any]], topics: list[dict[str, Any]],
                  lang: str = "es") -> str:
    """A deterministic idea of at least two sentences from the keywords and the
    matched items; it never states anything the bank did not return."""
    kws = _enumerate(keywords, lang)
    if not items:
        return " ".join((_say(_EMPTY_1, lang, keywords=kws), _say(_EMPTY_2, lang),
                         _say(_EMPTY_3, lang, keywords=kws)))
    names = [f"\"{t['name']}\"" for t in topics[:MAX_DRAFT_TOPICS]]
    where = f", {_say(_TOPIC if len(names) == 1 else _TOPICS, lang)} {_enumerate(names, lang)}," if names else ""
    cited = _enumerate([_cited(i, lang) for i in items[:MAX_DRAFT_ITEMS]], lang)
    return " ".join((_say(_FOUND_1, lang, keywords=kws, where=where), _say(_FOUND_2, lang, cited=cited),
                     _say(_FOUND_3, lang, keywords=kws)))
