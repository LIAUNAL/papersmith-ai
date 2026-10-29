"""Display language of the JSON API: English always, Spanish on request.

Every module of the command center builds its labels in English, and every
response is English unless the request asks otherwise. A request to an
``/api/`` route that carries ``?lang=es`` gets the same JSON with its DISPLAY
fields translated, the same way ``/api/section-translation`` serves a Spanish
copy of an English contract: the English stays the source, the Spanish is a
reading copy.

What is translated is chosen explicitly, never guessed:

* ``DISPLAY_FIELDS`` maps a route to the dotted JSON paths whose values are
  labels the server wrote (``fases.name``, ``fases.actions.label``…; list
  levels are left out of a path). A string at any other path — an id, a
  state, a kind, a path, a command, a file name, a transcript, the paper's own
  text — is never touched, even when it happens to equal a catalogue entry,
  because the panels compare those values (``state === 'running'``). A list at
  a display path is translated item by item; a dict at one is walked with the
  same rule.
* ``static/i18n/server-es.json`` maps an English text to its Spanish. A key with
  ``{name}`` placeholders is a template: ``"{n} blocks in paper/main.tex."``
  matches any text of that shape and keeps the matched values; a matched value
  that has an entry of its own (a phase label inside "Phase 4 — {label}") is
  translated too. Exact entries win over templates, and longer templates are
  tried before shorter ones.
* A display string with no entry stays English; it is never emptied.

The two server-rendered HTML views (``/api/atlas/candidates/view`` and
``/api/atlas/novelty/view``) take the same ``?lang=`` parameter and translate
their own labels with ``translate``; the dashboard adds it to their iframe and
links, which do not go through ``fetch``.

A request without ``lang``, or with ``lang=en``, passes through untouched: the
response bytes are the handler's own. Non-JSON responses (HTML views, PDFs,
event streams) pass through untouched in every language.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import parse_qs

CATALOGUE = Path(__file__).resolve().parent / "static" / "i18n" / "server-es.json"
LANGUAGES = frozenset({"es"})

def _paths(*groups: str | Iterable[str]) -> frozenset[str]:
    out: set[str] = set()
    for group in groups:
        out.update([group] if isinstance(group, str) else group)
    return frozenset(out)


def _under(prefix: str, *keys: str) -> list[str]:
    return [f"{prefix}.{key}" for key in keys]


_PHASE_FIELDS = (["name", "desc", "detail"] + _under("subfases", "name", "detail", "desc")
                 + _under("actions", "label", "desc", "guide", "placeholder") + _under("evidence", "label"))
_STAGES = ("poc", "full")
_HARNESSES = ("claude-code", "pi", "opencode", "antigravity")

#: Route -> the dotted JSON paths whose string values are labels the server
#: wrote. Everything else in a response is a machine value or the workspace's
#: own content and is never translated.
DISPLAY_FIELDS: dict[str, frozenset[str]] = {
    "/api/status": _paths(
        "authors", _under("fases", *_PHASE_FIELDS), _under("pipeline_stages", *_PHASE_FIELDS),
        "gates.criteria", "artifacts.category", "artifacts.name", "telemetria.fase",
        _under("sections", "principles", "cross_relations", "canonical_blocks.role",
               "canonical_blocks.question"),
    ),
    "/api/experiments": _paths(
        _under("remote_services", "note", "rows.service", "rows.purpose", "rows.detail", "rows.badge",
               "rows.action.label"),
        _under("local_environment", "note", "workspace.label", "workspace.detail", "targets.detail",
               "targets.device"),
        _under("run_options", "plan_hint", "empty_hint", "rows.stage_label", "rows.reason",
               "rows.estimate_label", "candidates.estimate_label", "candidates.reason"),
        [f"run_options.recommendations.{stage}.text" for stage in _STAGES],
    ),
    "/api/ai-history": _paths(
        "note", _under("phases", "label", "name", "reasons", "rounds.reason", "events.actor",
                       "artifacts.label"),
        [f"sources.chats.{harness}.detail" for harness in _HARNESSES],
    ),
    "/api/agents": _paths("agents.phases"),
    "/api/terminal/agents": _paths("agents.desc"),
    "/api/model": _paths(
        "authors", "trl", "executive_summary", "novelty.problem_statement",
        _under("novelty.pillars", "name", "badge", "summary", "details"),
        _under("conceptual_map.layers", "layer", "desc"),
        _under("mathematical_model.domains", "name", "definition"),
    ),
    "/api/atlas/novelty": _paths(
        "title", "target_journal", "authors", "summary", "links.label",
        _under("nodes", "label", "category", "badge", "desc", "rhetorical_question", "paragraph_text",
               "metrics", "novelty_claim", "thesis_ref", "section_ref"),
    ),
    "/api/phase/run": _paths("message", "error"),
    "/api/pdf/execute": _paths("message", "error"),
}

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@lru_cache(maxsize=1)
def _catalogue() -> tuple[dict[str, str], tuple[tuple[re.Pattern[str], str], ...]]:
    try:
        entries = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        entries = {}
    exact = {english: spanish for english, spanish in entries.items()
             if not _PLACEHOLDER.search(english)}
    templates = []
    for english, spanish in entries.items():
        if not _PLACEHOLDER.search(english):
            continue
        pattern, last = [], 0
        for match in _PLACEHOLDER.finditer(english):
            pattern.append(re.escape(english[last:match.start()]))
            pattern.append(f"(?P<{match.group(1)}>.*?)")
            last = match.end()
        pattern.append(re.escape(english[last:]))
        templates.append((re.compile("".join(pattern), re.S), spanish))
    # Longer templates are more specific: try them first.
    templates.sort(key=lambda item: -len(item[0].pattern))
    return exact, tuple(templates)


@lru_cache(maxsize=8192)
def lookup(text: str) -> str | None:
    """The Spanish of ``text``, or ``None`` when the catalogue has no entry.

    A template's matched values are looked up too (a phase label inside
    "Phase {n} — {label}", a sentence inside a composed recommendation); a
    value with no entry of its own is kept as it is.
    """
    exact, templates = _catalogue()
    if text in exact:
        return exact[text]
    for pattern, spanish in templates:
        match = pattern.fullmatch(text)
        if match:
            values = {name: _captured(value) if value and value != text else value
                      for name, value in match.groupdict().items()}
            return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), spanish)
    return None


def _captured(value: str) -> str:
    """A template's matched value in Spanish: whole, else each ``; `` part."""
    whole = lookup(value)
    if whole is not None:
        return whole
    if "; " in value:
        return "; ".join(lookup(part) or part for part in value.split("; "))
    return value


def translate(text: str, lang: str) -> str:
    """``text`` in ``lang``; English (the text itself) when there is no entry."""
    if lang not in LANGUAGES or not text:
        return text
    return lookup(text) or text


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _display(value: Any, lang: str, fields: frozenset[str], path: str) -> Any:
    if isinstance(value, str):
        return translate(value, lang)
    if isinstance(value, list):
        return [_display(item, lang, fields, path) for item in value]
    if isinstance(value, dict):
        return localize(value, lang, fields, path)
    return value


def localize(payload: Any, lang: str, fields: frozenset[str], path: str = "") -> Any:
    """``payload`` with the string values at the display ``fields`` translated.

    A field is a dotted path of JSON keys from the root, list levels left out:
    ``fases.actions.label`` is the ``label`` of every action of every phase.
    """
    if isinstance(payload, dict):
        out = {}
        for key, value in payload.items():
            where = _join(path, key)
            out[key] = (_display(value, lang, fields, where) if where in fields
                        else localize(value, lang, fields, where))
        return out
    if isinstance(payload, list):
        return [localize(item, lang, fields, path) for item in payload]
    return payload


def display_strings(payload: Any, fields: frozenset[str], path: str = "",
                    inside: bool = False) -> Iterator[str]:
    """Every string ``localize`` would offer to the catalogue."""
    if isinstance(payload, str):
        if inside:
            yield payload
    elif isinstance(payload, list):
        for item in payload:
            yield from display_strings(item, fields, path, inside)
    elif isinstance(payload, dict):
        for key, value in payload.items():
            where = _join(path, key)
            yield from display_strings(value, fields, where, inside or where in fields)


def requested_language(query_string: bytes) -> str:
    values = parse_qs(query_string.decode("latin-1")).get("lang") or [""]
    return values[0] if values[0] in LANGUAGES else "en"


class LocalizeMiddleware:
    """Translate the display fields of a JSON ``/api/`` response on ``?lang=es``.

    ``fields`` overrides ``DISPLAY_FIELDS`` (route -> keys); a route it does not
    name passes through untouched.
    """

    def __init__(self, app: Any, fields: dict[str, Iterable[str]] | None = None) -> None:
        self.app = app
        source = DISPLAY_FIELDS if fields is None else fields
        self.fields = {route: frozenset(keys) for route, keys in source.items()}

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        fields = self.fields.get(scope.get("path", ""))
        lang = requested_language(scope.get("query_string", b""))
        if fields is None or lang == "en":
            await self.app(scope, receive, send)
            return

        start: dict[str, Any] | None = None
        chunks: list[bytes] = []

        async def capture(message: dict[str, Any]) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers") or [])
                if headers.get(b"content-type", b"").split(b";")[0].strip() == b"application/json":
                    start = message  # held until the whole body is in
                else:
                    await send(message)
                return
            if start is None:
                await send(message)
                return
            chunks.append(message.get("body", b""))
            if message.get("more_body"):
                return
            body = b"".join(chunks)
            try:
                payload = json.loads(body)
            except ValueError:
                localized = body
            else:
                localized = json.dumps(localize(payload, lang, fields), ensure_ascii=False,
                                       allow_nan=False, separators=(",", ":")).encode("utf-8")
            headers = [(name, value) for name, value in start.get("headers") or []
                       if name != b"content-length"]
            headers.append((b"content-length", str(len(localized)).encode()))
            await send({**start, "headers": headers})
            await send({"type": "http.response.body", "body": localized})

        await self.app(scope, receive, capture)


__all__ = ["CATALOGUE", "DISPLAY_FIELDS", "LANGUAGES", "LocalizeMiddleware", "display_strings",
           "localize", "lookup", "requested_language", "translate"]
