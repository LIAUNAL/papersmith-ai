"""A fake banco-lia MCP server on stdio for tests/test_banco_suggest.py.

Speaks the three requests the dashboard's client sends (initialize,
tools/list, tools/call search_bank|taxonomy) over newline-delimited JSON-RPC,
answering from bank.json beside this file. ``FAKE_MCP_MODE`` picks a
misbehaviour: ``hang`` (never answers), ``stubborn`` (ignores SIGTERM and never
answers), ``malformed`` (answers initialize with a non-JSON line), ``crash``
(exits at once), ``toolerror`` (search_bank answers isError), ``textonly``
(results as JSON text blocks, no structuredContent). ``FAKE_MCP_LOG`` appends
one JSON line per tools/call; ``FAKE_MCP_PIDFILE`` receives this process id.
"""
import json
import os
import signal
import sys
import time
from pathlib import Path

MODE = os.environ.get("FAKE_MCP_MODE", "ok")
DATA = json.loads((Path(__file__).with_name("bank.json")).read_text(encoding="utf-8"))
SHOWN = ("id", "kind", "title", "year", "cluster", "doi")


def say(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def search(arguments):
    words = [w for w in str(arguments.get("query", "")).lower().split() if w]
    mode = arguments.get("match", "any")
    hits = []
    for item in DATA["items"]:
        found = [item["text"].lower().split().count(w) for w in words]
        if (all(found) if mode == "all" else any(found)) and words:
            hits.append((sum(found), item))
    hits.sort(key=lambda hit: (-hit[0], hit[1]["id"]))
    limit = int(arguments.get("limit", 10))
    return [{**{k: item[k] for k in SHOWN if k in item}, "snippet": "…[" + words[0] + "]…", "score": float(score)}
            for score, item in hits[:limit]]


def taxonomy():
    return {"topics": DATA["topics"], "clusters": DATA["clusters"]}


def result(payload):
    if MODE == "textonly":
        blocks = payload if isinstance(payload, list) else [payload]
        return {"content": [{"type": "text", "text": json.dumps(b)} for b in blocks]}
    structured = {"result": payload} if isinstance(payload, list) else payload
    return {"content": [{"type": "text", "text": json.dumps(payload)}], "structuredContent": structured}


def main():
    pidfile = os.environ.get("FAKE_MCP_PIDFILE")
    if pidfile:
        Path(pidfile).write_text(str(os.getpid()), encoding="utf-8")
    if MODE == "crash":
        sys.exit(3)
    if MODE == "stubborn":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        method, ident = request.get("method"), request.get("id")
        if MODE in ("hang", "stubborn"):
            time.sleep(600)
        if method == "initialize":
            if MODE == "malformed":
                sys.stdout.write("this is not json-rpc\n")
                sys.stdout.flush()
                continue
            say({"jsonrpc": "2.0", "id": ident, "result": {
                "protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-banco-lia", "version": "0"}}})
        elif method == "tools/list":
            say({"jsonrpc": "2.0", "id": ident, "result": {"tools": [{"name": "search_bank"}, {"name": "taxonomy"}]}})
        elif method == "tools/call":
            params = request.get("params", {})
            name, arguments = params.get("name"), params.get("arguments", {})
            log = os.environ.get("FAKE_MCP_LOG")
            if log:
                with open(log, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"name": name, "arguments": arguments}) + "\n")
            if name == "search_bank" and MODE == "toolerror":
                say({"jsonrpc": "2.0", "id": ident, "result": {
                    "isError": True, "content": [{"type": "text", "text": "index is being rebuilt"}]}})
            elif name == "search_bank":
                say({"jsonrpc": "2.0", "id": ident, "result": result(search(arguments))})
            elif name == "taxonomy":
                say({"jsonrpc": "2.0", "id": ident, "result": result(taxonomy())})
            else:
                say({"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": f"unknown tool {name}"}})
        elif ident is not None:
            say({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "method not found"}})


if __name__ == "__main__":
    main()
