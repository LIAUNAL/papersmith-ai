"""Ai2 Asta's scientific-corpus tools, spoken over MCP streamable HTTP by hand.

Asta (https://allenai.org/asta/resources/mcp) serves the Semantic Scholar
corpus as MCP tools at :data:`ENDPOINT`. This module is the one place that knows
the wire format, and it holds no transport and no key: pure functions over
bytes, standard library only, so every caller keeps its own HTTP path (the
paper-writing resolver goes through its swappable ``OPENER``, journal-finder
through its cached ``Http``, ``api_keys.verify`` through a no-redirect opener)
and passes the key in. Load it by path; it imports nothing of the framework.

What the live server answered on 2026-11-09, which these functions encode:

* it is stateless: ``tools/call`` works with no ``initialize`` handshake and
  no ``Mcp-Session-Id``;
* a reply is always ``text/event-stream``: ``event: message`` and one
  ``data:`` line carrying the JSON-RPC reply, preceded by ``: ping`` comments
  every 15 s while the call is pending. A per-read socket timeout therefore
  never fires on a stalled search, so :func:`read_message` bounds the TOTAL
  wall time itself;
* the answer is ``result.content[*].text``: the JSON of a Semantic Scholar
  paper object, or of a page of them. ``result.isError`` marks a failed tool
  call, and its text is the only place the reason travels — a missing paper
  ("... not found") and a refused key ("HTTP status 403 Forbidden.") both
  arrive as HTTP 200, so :func:`classify` reads the text;
* an empty ``x-api-key`` header is keyless; searches without a key stall.

On 2026-11-11 about half of the keyed lookups answered only after 30 or 60 s
while the others took under a second, so a lookup is asked again after
:data:`LOOKUP_ATTEMPT_SECONDS` of silence (:attr:`AstaError.timed_out` says
the silence ran out).

Model-generated fields (``tldr``) and excerpted passages (``snippet_search``)
point at a paper; they are never an abstract or a quote, and nothing here
returns them as one.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Iterable

ENDPOINT = "https://asta-tools.allen.ai/mcp/v1"
PROTOCOL_VERSION = "2025-06-18"
KEY_HEADER = "x-api-key"
#: Every call is one request with this JSON-RPC id; the reply carries it back.
REQUEST_ID = 1
#: Largest reply read before giving up, pings included.
MAX_RESPONSE_BYTES = 8 << 20
#: How long a single-paper lookup (``get_paper``) is waited for before it is
#: asked again. Measured live on 2026-11-11 with a key, a lookup answered in
#: 0.4-0.7 s or only after 30.5-30.8 s or 60.6 s (keyless, always under a
#: second), and a fresh request usually answered at once: waiting out a slow
#: one costs half a minute, asking again about a second.
LOOKUP_ATTEMPT_SECONDS = 5.0

#: Why a call failed, as :class:`AstaError.kind`.
NOT_FOUND = "not_found"
REFUSED = "refused"
UNAVAILABLE = "unavailable"
KINDS = (NOT_FOUND, REFUSED, UNAVAILABLE)

#: A bare number is never enough: "DOI:10.403/x not found" names a paper.
_REFUSED_RE = re.compile(r"\b(?:http|status)\s*(?:status\s*)?(?:401|403)\b|\bforbidden\b"
                         r"|\bunauthori[sz]ed\b|invalid (?:or missing )?api key", re.IGNORECASE)
_NOT_FOUND_RE = re.compile(r"\bnot found\b|\b(?:http|status)\s*(?:status\s*)?404\b", re.IGNORECASE)
_ARXIV_VERSION_RE = re.compile(r"v\d+$")


class AstaError(Exception):
    """A call that did not produce an answer: :attr:`kind` says which way."""

    def __init__(self, kind: str, detail: str, *, timed_out: bool = False) -> None:
        super().__init__(detail)
        self.kind = kind if kind in KINDS else UNAVAILABLE
        self.detail = detail
        #: The deadline passed with no answer: the call may be asked again.
        self.timed_out = timed_out


def paper_id(kind: str, value: str) -> str:
    """Asta's id for a DOI (``DOI:<doi>``) or an arXiv id (``ARXIV:<bare id>``).

    The arXiv version suffix is dropped: Asta names the work, not one upload.
    """
    value = value.strip()
    if kind == "doi":
        return f"DOI:{value}"
    if kind == "arxiv":
        return f"ARXIV:{_ARXIV_VERSION_RE.sub('', value)}"
    raise ValueError(f"no Asta id for identifier kind {kind!r}")


def request(tool: str, arguments: dict[str, Any], *, key: str | None = None,
            endpoint: str = ENDPOINT) -> tuple[str, bytes, dict[str, str]]:
    """``(url, body, headers)`` of one ``tools/call``.

    The key travels only in :data:`KEY_HEADER`, and only when it is non-empty;
    the body never carries it.
    """
    body = json.dumps({"jsonrpc": "2.0", "id": REQUEST_ID, "method": "tools/call",
                       "params": {"name": tool, "arguments": arguments}},
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": PROTOCOL_VERSION}
    if key and key.strip():
        headers[KEY_HEADER] = key.strip()
    return endpoint, body, headers


def _dispatch(data_lines: list[str], request_id: int) -> dict[str, Any] | None:
    if not data_lines:
        return None
    try:
        message = json.loads("\n".join(data_lines))
    except ValueError as exc:
        raise AstaError(UNAVAILABLE, "the server sent an event that is not JSON") from exc
    if isinstance(message, dict) and message.get("id") == request_id:
        return message
    return None  # a notification, or another id: keep reading


def read_message(readline: Callable[[], bytes], *, deadline: float,
                 clock: Callable[[], float] = time.monotonic,
                 request_id: int = REQUEST_ID) -> dict[str, Any]:
    """The JSON-RPC reply with ``request_id``, read line by line.

    Accepts an event stream (``event:``/``data:`` fields, multi-line data,
    ``:`` comments such as the server's pings, blank-line dispatch) or a plain
    JSON body. ``deadline`` is an absolute ``clock()`` time checked after every
    line, so a stream of pings cannot hold a caller past it; the caller bounds
    each single read with its socket timeout. Raises :class:`AstaError`
    (:data:`UNAVAILABLE`) on the deadline, on end of stream without the reply,
    and past :data:`MAX_RESPONSE_BYTES`.
    """
    received = 0
    data: list[str] = []
    plain: list[str] | None = None
    while True:
        raw = readline()
        if clock() > deadline:
            raise AstaError(UNAVAILABLE, "no answer within the deadline", timed_out=True)
        if not raw:
            break
        received += len(raw)
        if received > MAX_RESPONSE_BYTES:
            raise AstaError(UNAVAILABLE, "the answer exceeded the size limit")
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if plain is not None:
            plain.append(line)
            continue
        if not data and line.lstrip().startswith(("{", "[")):
            plain = [line]  # application/json: the rest of the body is the message
            continue
        if line == "":
            message = _dispatch(data, request_id)
            data = []
            if message is not None:
                return message
            continue
        if line.startswith(":"):
            continue  # a comment: the server's keep-alive ping
        field, _, value = line.partition(":")
        if field == "data":
            data.append(value[1:] if value.startswith(" ") else value)
        # `event`, `id`, `retry` carry nothing this client needs.
    if plain is not None:
        try:
            message = json.loads("\n".join(plain))
        except ValueError as exc:
            raise AstaError(UNAVAILABLE, "the server answered with a body that is not JSON") from exc
        if isinstance(message, dict) and message.get("id") == request_id:
            return message
        raise AstaError(UNAVAILABLE, "the server answered without the reply to this call")
    message = _dispatch(data, request_id)
    if message is not None:
        return message
    raise AstaError(UNAVAILABLE, "the stream ended without an answer")


def classify(text: str) -> str:
    """The :class:`AstaError` kind a failed tool call's text describes.

    A refused or missing key is :data:`REFUSED`, a paper the corpus does not
    hold is :data:`NOT_FOUND`, and anything else — 429, 5xx, a timeout, a
    message nobody anticipated — is :data:`UNAVAILABLE`, which a caller may
    retry or route around but never reads as an answer.
    """
    if _REFUSED_RE.search(text or ""):
        return REFUSED
    if _NOT_FOUND_RE.search(text or ""):
        return NOT_FOUND
    return UNAVAILABLE


def tool_texts(message: dict[str, Any]) -> list[str]:
    """The text parts of a successful tool result; raises :class:`AstaError`."""
    if not isinstance(message, dict):
        raise AstaError(UNAVAILABLE, "the reply is not a JSON-RPC object")
    error = message.get("error")
    if error is not None:
        detail = str(error.get("message") if isinstance(error, dict) else error)[:300]
        raise AstaError(UNAVAILABLE, f"JSON-RPC error: {detail}")
    result = message.get("result")
    if not isinstance(result, dict):
        raise AstaError(UNAVAILABLE, "the reply carries no result")
    parts = result.get("content") or []
    texts = [part.get("text", "") for part in parts
             if isinstance(part, dict) and part.get("type") == "text"
             and isinstance(part.get("text"), str)]
    if result.get("isError"):
        detail = " ".join(texts).strip()[:300] or "the tool reported an error"
        raise AstaError(classify(detail), detail)
    return texts


def papers(texts: Iterable[str]) -> list[dict[str, Any]]:
    """Paper objects from a tool's text parts.

    Accepts one paper per part, a list of papers, or a page (``{"data": [...]}``)
    — the Semantic Scholar shapes. A part that is not JSON is skipped; if no
    part parsed at all the answer is :data:`UNAVAILABLE`, never an empty
    result that would read as "nothing found".
    """
    found: list[dict[str, Any]] = []
    parsed_any = False
    seen = 0
    for text in texts:
        seen += 1
        try:
            value = json.loads(text)
        except ValueError:
            continue
        parsed_any = True
        if isinstance(value, dict) and isinstance(value.get("data"), list):
            found.extend(item for item in value["data"] if isinstance(item, dict))
        elif isinstance(value, list):
            found.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            found.append(value)
    if seen and not parsed_any:
        raise AstaError(UNAVAILABLE, "the tool answered with text that is not JSON")
    return found


def redact(text: str, *secrets: str | None) -> str:
    """``text`` with every non-empty secret replaced by ``<redacted>``."""
    for secret in secrets:
        if secret and secret.strip():
            text = text.replace(secret.strip(), "<redacted>")
    return text


__all__ = ["ENDPOINT", "PROTOCOL_VERSION", "KEY_HEADER", "REQUEST_ID", "MAX_RESPONSE_BYTES",
           "NOT_FOUND", "REFUSED", "UNAVAILABLE", "KINDS", "AstaError", "paper_id", "request",
           "read_message", "classify", "tool_texts", "papers", "redact"]
