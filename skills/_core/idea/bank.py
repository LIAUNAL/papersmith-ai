"""Step 1, sources: which knowledge bank (if any) the idea-shaping phase queries.

The user decides among three choices (recorded in the brief's ``bank``):

* ``banco-lia``: the lab's bank, managed by smith; probed when chosen, the
  reason shown when it cannot be reached;
* ``other``: another MCP server of the workspace's ``.mcp.json`` that smith
  does not manage (:data:`MANAGED_MCP_SERVERS`), or one added with
  :func:`add_server`. Probed with ``tools/list``: it is *compatible* when it
  exposes ``search_bank`` (optionally ``taxonomy``) and is then queried like
  banco-lia; otherwise only the agent can use it, through its own
  ``mcp__<server>__*`` tools;
* ``none``: no bank is ever queried.

The stdio client is ``command_center/banco_suggest.py``'s (one implementation
for the thematic help and this phase); an HTTP server is spoken to with a
minimal streamable-HTTP JSON-RPC client here. Every network or process call
goes through :data:`CONNECT` (tests replace it), and nothing here raises for an
unreachable server: the result carries ``available: False`` and the reason.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from . import brief as _brief
from ..command_center import banco_suggest

try:  # the one list of servers smith registers (papersmith.generators)
    from papersmith.generators import MANAGED_MCP_SERVERS  # type: ignore
except Exception:  # noqa: BLE001 - the workspace's bare Python has no papersmith package
    MANAGED_MCP_SERVERS = ("banco-lia", "kaggle", "colab", "asta")

MANAGED = banco_suggest.SERVER
MCP_FILE = ".mcp.json"
SEARCH_TOOL = "search_bank"
TAXONOMY_TOOL = "taxonomy"
SEARCH_LIMIT = 8
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_ENV_RE = re.compile(r"\$\{(\w+)(?::-([^}]*))?\}")
Unavailable = banco_suggest.Unavailable


def _reason(text: Any) -> str:
    return " ".join(str(text).split())[:240] or "unknown error"


# --------------------------------------------------------------------------
# .mcp.json
# --------------------------------------------------------------------------
def _read_config(root: Path | str) -> dict[str, Any]:
    target = Path(root) / MCP_FILE
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        raise _brief.IdeaError("MCP_CONFIG_UNREADABLE", f"{MCP_FILE} is not readable JSON; fix it first") from None
    if not isinstance(data, dict):
        raise _brief.IdeaError("MCP_CONFIG_UNREADABLE", f"{MCP_FILE} is not a JSON object; fix it first")
    return data


def _servers(root: Path | str) -> dict[str, Any]:
    try:
        servers = _read_config(root).get("mcpServers")
    except _brief.IdeaError:
        return {}
    return servers if isinstance(servers, dict) else {}


def _describe(name: str, entry: Any) -> dict[str, Any]:
    entry = entry if isinstance(entry, dict) else {}
    if entry.get("url"):
        return {"server": name, "transport": "http", "url": str(entry["url"])}
    args = entry.get("args")
    return {"server": name, "transport": "stdio", "command": str(entry.get("command") or ""),
            "args": [str(a) for a in args] if isinstance(args, list) else []}


def choices(root: Path | str) -> dict[str, Any]:
    """The managed bank and the workspace's other MCP servers (those smith
    does not manage), in ``.mcp.json`` order."""
    others = [_describe(name, entry) for name, entry in _servers(root).items()
              if name not in MANAGED_MCP_SERVERS]
    return {"managed": MANAGED, "others": others}


def add_server(root: Path | str, name: str, command: str | None = None, url: str | None = None,
               args: list[str] | None = None) -> dict[str, Any]:
    """Add a bank server to ``.mcp.json`` (stdio ``command`` or HTTP ``url``),
    keeping every other server and key in their order. Refuses a managed
    name, an existing one, or neither/both of command and url."""
    name = str(name or "").strip()
    if not _NAME_RE.match(name):
        raise _brief.IdeaError("SERVER_NAME_INVALID",
                               "a server name is 1 to 64 letters, digits, '.', '_' or '-'")
    if name in MANAGED_MCP_SERVERS:
        raise _brief.IdeaError("SERVER_MANAGED", f"{name} is managed by smith; choose it directly")
    if bool(command) == bool(url):
        raise _brief.IdeaError("SERVER_SPEC", "give either a command or a URL for the server")
    if url:
        url = str(url).strip()
        if not re.match(r"^https?://\S+$", url):
            raise _brief.IdeaError("SERVER_SPEC", "the URL must start with http:// or https://")
        entry: dict[str, Any] = {"type": "http", "url": url}
    else:
        try:
            argv = shlex.split(str(command)) + [str(a) for a in (args or [])]
        except ValueError as exc:
            raise _brief.IdeaError("SERVER_SPEC", f"cannot read the command: {exc}") from None
        if not argv:
            raise _brief.IdeaError("SERVER_SPEC", "the command is empty")
        entry = {"type": "stdio", "command": argv[0], "args": argv[1:]}
    config = _read_config(root)
    servers = config.get("mcpServers")
    if servers is None:
        servers = config["mcpServers"] = {}
    if not isinstance(servers, dict):
        raise _brief.IdeaError("MCP_CONFIG_UNREADABLE", f"{MCP_FILE} mcpServers is not an object; fix it first")
    if name in servers:
        raise _brief.IdeaError("SERVER_EXISTS", f"{MCP_FILE} already has a server named {name}")
    servers[name] = entry
    target = Path(root) / MCP_FILE
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=target.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return _describe(name, entry)


# --------------------------------------------------------------------------
# Streamable-HTTP JSON-RPC client (stdlib)
# --------------------------------------------------------------------------
def _expand(value: str) -> str:
    """``${VAR}`` and ``${VAR:-default}`` from the environment, as the harnesses do."""
    return _ENV_RE.sub(lambda m: os.environ.get(m.group(1)) or (m.group(2) or ""), value)


class _HttpSession:
    def __init__(self, url: str, headers: dict[str, str], timeout: float, label: str) -> None:
        self.url = url
        self.headers = headers
        self.timeout = timeout
        self.deadline = time.monotonic() + timeout
        self.label = label
        self.next_id = 0
        self.session_id: str | None = None

    def _post(self, message: dict[str, Any]) -> tuple[str, bytes]:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Unavailable(f"timed out after {self.timeout:g} s waiting for {self.label}")
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "User-Agent": "papersmith-ai", **self.headers}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(self.url, data=json.dumps(message).encode("utf-8"),
                                         headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=remaining) as response:
                self.session_id = response.headers.get("Mcp-Session-Id") or self.session_id
                return str(response.headers.get("Content-Type") or ""), response.read()
        except urllib.error.HTTPError as exc:
            raise Unavailable(f"{self.label} answered HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            reason = getattr(exc, "reason", None) or exc
            raise Unavailable(f"cannot reach {self.label}: {reason}") from None

    def notify(self, method: str) -> None:
        self._post({"jsonrpc": "2.0", "method": method})

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.next_id += 1
        ident = self.next_id
        kind, body = self._post({"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}})
        for message in self._messages(kind, body):
            if isinstance(message, dict) and message.get("id") == ident:
                if "error" in message:
                    error = message["error"]
                    raise Unavailable(f"{self.label} refused {method}: "
                                      f"{_reason(error.get('message') if isinstance(error, dict) else error)}")
                if "result" in message:
                    return message["result"]
        raise Unavailable(f"{self.label} sent no answer to {method}")

    def _messages(self, kind: str, body: bytes) -> list[Any]:
        text = body.decode("utf-8", "replace")
        try:
            if "text/event-stream" in kind:
                found = []
                for line in text.splitlines():
                    if line.startswith("data:"):
                        found.append(json.loads(line[5:].strip()))
                return found
            data = json.loads(text) if text.strip() else []
        except ValueError:
            raise Unavailable(f"{self.label} sent a malformed JSON-RPC message") from None
        return data if isinstance(data, list) else [data]

    def start(self) -> None:
        self.request("initialize", {"protocolVersion": banco_suggest.PROTOCOL_VERSION, "capabilities": {},
                                    "clientInfo": {"name": "papersmith-idea", "version": "1"}})
        self.notify("notifications/initialized")

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        return banco_suggest._tool_payload(  # noqa: SLF001 - the one tool-result reader
            self.request("tools/call", {"name": name, "arguments": arguments}), self.label)

    def tools(self) -> list[str]:
        result = self.request("tools/list")
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list):
            raise Unavailable(f"{self.label} sent a malformed tools/list result")
        return [str(t["name"]) for t in tools if isinstance(t, dict) and isinstance(t.get("name"), str)]

    def close(self) -> None:
        if not self.session_id:
            return
        request = urllib.request.Request(self.url, headers={"Mcp-Session-Id": self.session_id}, method="DELETE")
        try:
            urllib.request.urlopen(request, timeout=2).close()
        except (urllib.error.URLError, OSError, ValueError):
            pass


def connect(root: Path | str, server: str, timeout: float | None = None) -> Any:
    """A started session with ``server``: banco-lia exactly as the thematic help
    starts it, another stdio server from its ``.mcp.json`` entry, an HTTP one
    with the client above. Raises :data:`Unavailable` with the reason."""
    seconds = timeout if timeout is not None else banco_suggest.timeout_seconds()
    entry = banco_suggest.server_entry(root, server)
    if server != MANAGED and entry is not None and entry.get("url"):
        raw = entry.get("headers")
        headers = {str(k): _expand(str(v)) for k, v in raw.items()} if isinstance(raw, dict) else {}
        session = _HttpSession(_expand(str(entry["url"])), headers, seconds, server)
        session.start()
        return session
    return banco_suggest.open_session(root, server, seconds)


#: The seam every probe and search goes through: ``CONNECT(root, server, timeout)``.
CONNECT: Callable[..., Any] = connect


def _close(session: Any) -> None:
    try:
        session.close()
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# Probe, choose, search
# --------------------------------------------------------------------------
def probe(root: Path | str, server: str) -> dict[str, Any]:
    """``tools/list`` on ``server``: ``{"available", "compatible", "tools", "reason"}``.
    Never raises; an unreachable server answers ``available: False`` and why."""
    session = None
    try:
        session = CONNECT(root, server, None)
        tools = session.tools()
    except Unavailable as exc:
        return {"available": False, "compatible": False, "tools": [], "reason": _reason(exc)}
    except Exception as exc:  # noqa: BLE001 - the user must never see a traceback from a bank
        return {"available": False, "compatible": False, "tools": [],
                "reason": _reason(f"unexpected failure talking to {server}: {exc}")}
    finally:
        if session is not None:
            _close(session)
    compatible = SEARCH_TOOL in tools
    reason = None if compatible else (
        f"{server} does not expose {SEARCH_TOOL}: smith cannot query it, but the agent can use its "
        f"mcp__{server}__* tools")
    return {"available": True, "compatible": compatible, "tools": tools, "reason": reason}


def _kind(root: Path | str, choice: str, server: str | None) -> tuple[str, str | None]:
    choice = str(choice or "").strip()
    server = str(server).strip() if server else None
    if choice == "none":
        return "none", None
    if choice == MANAGED or (choice == "other" and server == MANAGED):
        return "banco-lia", MANAGED
    if choice == "other":
        if not server:
            raise _brief.IdeaError("SERVER_MISSING", "choose which server of .mcp.json is the bank")
    elif choice:
        server = choice
    else:
        raise _brief.IdeaError("BANK_CHOICE_INVALID", "choose banco-lia, none, or a server of .mcp.json")
    if server in MANAGED_MCP_SERVERS:
        raise _brief.IdeaError("SERVER_MANAGED",
                               f"{server} is managed by smith and is not a bank; choose banco-lia, none or "
                               "another server")
    if server not in _servers(root):
        raise _brief.IdeaError("SERVER_UNKNOWN",
                               f"no server named {server} in .mcp.json; add it with "
                               "`smith idea bank --add NAME --command ...|--url ...`")
    return "other", server


def choose(root: Path | str, choice: str, server: str | None = None) -> dict[str, Any]:
    """Record the user's source choice (probing a bank) and return the brief's ``bank``."""
    kind, name = _kind(root, choice, server)
    if kind == "none":
        data = {"choice": "none", "server": None, "compatible": None, "tools": [], "available": None,
                "reason": None}
    else:
        data = {"choice": kind, "server": name, **probe(root, name)}
    data["checked_at"] = _brief.now()
    return _brief.record(root, "bank", data)["bank"]


def search(root: Path | str, query: str, limit: int = SEARCH_LIMIT) -> dict[str, Any]:
    """Items of the chosen bank for ``query``, only when that bank is compatible
    and was reachable when probed; never raises."""
    bank = _brief.load(root)["bank"]
    if bank.get("choice") not in ("banco-lia", "other") or not bank.get("compatible"):
        return {"available": False, "hits": [], "topics": [], "reason": "no compatible bank was chosen"}
    server = str(bank.get("server") or MANAGED)
    arguments: dict[str, Any] = {"query": str(query), "limit": int(limit)}
    if server == MANAGED:
        arguments["match"] = "any"
    session = None
    try:
        session = CONNECT(root, server, None)
        items = banco_suggest.parse_items(session.call(SEARCH_TOOL, arguments))[:limit]
        names = banco_suggest.taxonomy_names(session) if items and TAXONOMY_TOOL in (bank.get("tools") or []) \
            else {}
    except Unavailable as exc:
        return {"available": False, "hits": [], "topics": [], "reason": _reason(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "hits": [], "topics": [],
                "reason": _reason(f"unexpected failure talking to {server}: {exc}")}
    finally:
        if session is not None:
            _close(session)
    return {"available": True, "server": server, "hits": items,
            "topics": banco_suggest.cluster_topics(items, names), "reason": None}


__all__ = ["CONNECT", "MANAGED", "MANAGED_MCP_SERVERS", "add_server", "choices", "choose", "connect", "probe",
           "search"]
