"""The MCP server: dispatch, tool execution, and the stdio loop.

The server never executes domain logic itself. Every tool call becomes one
child process through :mod:`papersmith.mcp.bridge`, whose captured stdout is
projected into the tool result. A child's exit code is classified by the
*child's own contract*: the orchestrator CLI's 1..4 keep their meaning, while a
skill script's 2 is a domain refusal whose name is read out of its
``{"status":"refused","code":...}`` envelope and preserved verbatim.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from .. import __version__
from . import protocol
from .bridge import ChildResult, redact, run_plan
from .registry import TOOLS, TOOLS_BY_NAME, ToolRefusal, ToolSpec
from .resources import RESOURCES, read_resource

SERVER_NAME = "papersmith"
INSTRUCTIONS = (
    "PaperSmith workspace orchestration and paper-writing tools. Every tool "
    "projects an existing `smith` CLI contract; nothing is reimplemented. "
    "Read-only tools and resources are safe to call freely. Mutating tools keep "
    "the CLI's own consent and force semantics: `workspace_upgrade` writes only "
    "framework files, `run` and `remote push` require an explicit consent token, "
    "and `ingest_add` is long-running and open-world."
)

CLI_EXIT_NAMES: dict[int, str] = {
    1: "USER_ERROR",
    2: "SOURCE_ERROR",
    3: "DRIFT_ERROR",
    4: "EXECUTION_ERROR",
}


class Server:
    def __init__(
        self,
        workspace: str | Path,
        *,
        out: TextIO | None = None,
        err: TextIO | None = None,
        name: str = SERVER_NAME,
        version: str = __version__,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.name = name
        self.version = version
        self.out: TextIO = sys.stdout if out is None else out
        self.err: TextIO = sys.stderr if err is None else err

    # -- protocol ---------------------------------------------------------- #

    def capabilities(self) -> dict[str, Any]:
        return {"tools": {}, "resources": {}}

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        if not isinstance(method, str):
            return None
        has_id = "id" in message
        if method.startswith("notifications/"):
            return None
        request_id = message.get("id")
        params = message.get("params")
        try:
            revision = protocol.negotiate(params)
            result = self._dispatch(method, params, revision)
        except protocol.ProtocolError as exc:
            return None if not has_id else exc.envelope(request_id)
        except ToolRefusal as refusal:
            if not has_id:
                return None
            error = protocol.ProtocolError(
                protocol.INVALID_PARAMS,
                refusal.code,
                {"code": refusal.code, "detail": refusal.detail},
            )
            return error.envelope(request_id)
        except Exception as exc:  # a bad call must never kill the transport loop
            self.err.write(f"smith mcp: {method} failed: {exc}\n")
            self.err.flush()
            if not has_id:
                return None
            return protocol.ProtocolError(
                protocol.INTERNAL_ERROR, f"{method} failed"
            ).envelope(request_id)
        if not has_id:
            return None
        return protocol.success(request_id, result)

    def _dispatch(self, method: str, params: Any, revision: str) -> Any:
        if method == "server/discover":
            return protocol.discover_result(
                name=self.name,
                version=self.version,
                capabilities=self.capabilities(),
                instructions=INSTRUCTIONS,
            )
        if method == "initialize":
            return protocol.initialize_result(
                revision=revision,
                name=self.name,
                version=self.version,
                capabilities=self.capabilities(),
            )
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [spec.as_tool() for spec in TOOLS]}
        if method == "tools/call":
            return self._call_tool(params)
        if method == "resources/list":
            return {
                "resources": [
                    {
                        "uri": spec.uri,
                        "name": spec.name,
                        "description": spec.description,
                        "mimeType": spec.mime_type,
                    }
                    for spec in RESOURCES
                ]
            }
        if method == "resources/read":
            return self._read_resource(params)
        if method == "prompts/list":
            return {"prompts": []}
        raise protocol.ProtocolError(protocol.METHOD_NOT_FOUND, f"unknown method: {method}")

    def _call_tool(self, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            raise protocol.ProtocolError(protocol.INVALID_PARAMS, "params must be an object")
        name = params.get("name")
        if not isinstance(name, str):
            raise protocol.ProtocolError(protocol.INVALID_PARAMS, "name is required")
        spec = TOOLS_BY_NAME.get(name)
        if spec is None:
            raise protocol.ProtocolError(
                protocol.INVALID_PARAMS, f"unknown tool: {name}", {"code": "UNKNOWN_TOOL"}
            )
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise protocol.ProtocolError(protocol.INVALID_PARAMS, "arguments must be an object")
        return execute_tool(spec, arguments, self.workspace)

    def _read_resource(self, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            raise protocol.ProtocolError(protocol.INVALID_PARAMS, "params must be an object")
        uri = params.get("uri")
        if not isinstance(uri, str):
            raise protocol.ProtocolError(protocol.INVALID_PARAMS, "uri is required")
        spec = read_resource(uri, self.workspace)
        text = redact(spec.reader(self.workspace))
        return {"contents": [{"uri": spec.uri, "mimeType": spec.mime_type, "text": text}]}

    # -- transport --------------------------------------------------------- #

    def serve(self, stdin: TextIO | None = None, out: TextIO | None = None) -> int:
        source: TextIO = sys.stdin if stdin is None else stdin
        sink: TextIO = self.out if out is None else out
        for raw in source:
            line = raw.strip()
            if not line:
                continue
            try:
                message = protocol.decode(line)
            except protocol.ProtocolError as exc:
                self._write(sink, exc.envelope(None))
                continue
            response = self.handle(message)
            if response is not None:
                self._write(sink, response)
        return 0

    def _write(self, sink: TextIO, message: dict[str, Any]) -> None:
        sink.write(protocol.encode(message) + "\n")
        sink.flush()


def _matches(declared: dict[str, Any], value: Any) -> bool:
    """Whether ``value`` has the JSON type the advertised schema declares.

    Strict: ``"false"`` is not a boolean and ``True`` is not an integer, so a
    value is never coerced into argv it was not declared to produce.
    """
    kind = declared.get("type")
    if kind == "boolean":
        ok = isinstance(value, bool)
    elif kind == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif kind == "array":
        ok = isinstance(value, list) and all(isinstance(item, str) for item in value)
    else:
        ok = isinstance(value, str)
    return ok and ("enum" not in declared or value in declared["enum"])


def _validate_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> None:
    """Refuse a call whose names or values the schema does not declare.

    Runs before ``spec.build``, so a refused call never reaches argv or a child.
    """
    properties = spec.input_schema.get("properties", {})
    for key in arguments:
        if key not in properties:
            raise ToolRefusal("UNKNOWN_ARGUMENT", f"{spec.name} has no argument {key!r}")
    for key, value in arguments.items():
        declared = properties[key]
        if value is not None and not _matches(declared, value):
            expected = declared.get("type", "string")
            if "enum" in declared:
                expected += " in " + ", ".join(map(str, declared["enum"]))
            raise ToolRefusal(
                "INVALID_ARGUMENT", f"{spec.name} argument {key!r} must be {expected}"
            )
    for key in spec.input_schema.get("required", []):
        if arguments.get(key) is None:
            raise ToolRefusal("MISSING_ARGUMENT", f"{spec.name} requires {key!r}")


def execute_tool(
    spec: ToolSpec, arguments: dict[str, Any], workspace: Path
) -> dict[str, Any]:
    """Run one tool call and project the child result into an MCP result."""
    try:
        _validate_arguments(spec, arguments)
        if spec.precondition is not None:
            spec.precondition(arguments, workspace)
        plan = spec.build(arguments, workspace)
    except ToolRefusal as refusal:
        return _error_result(refusal.code, refusal.detail, exit_code=None)

    result = run_plan(plan, workspace)
    if result.timed_out:
        return _error_result(
            "TIMEOUT", f"{spec.verb} exceeded its time budget", exit_code=result.returncode
        )

    structured = _maybe_json(result.stdout) if spec.result_json else None
    if result.returncode != 0:
        code = _refusal_code(spec, result)
        detail = _failure_detail(spec, result, structured)
        payload: dict[str, Any] = {"code": code, "exit": result.returncode}
        if spec.surface == "paper" and result.returncode == 2:
            payload["mapped"] = "USER_ERROR"
        return _error_result(code, detail, exit_code=result.returncode, structured=payload)

    text = result.stdout.strip()
    if not text and structured is not None:
        text = json.dumps(structured, indent=2, sort_keys=True)
    return protocol.tool_result(
        [protocol.text_content(redact(text))],
        structured=structured,
        is_error=False,
    )


def _refusal_code(spec: ToolSpec, result: ChildResult) -> str:
    if spec.surface == "paper":
        envelope = _maybe_json(result.stdout)
        if isinstance(envelope, dict) and isinstance(envelope.get("code"), str):
            return str(envelope["code"])
        return "USER_ERROR"
    return CLI_EXIT_NAMES.get(result.returncode, "EXECUTION_ERROR")


def _failure_detail(spec: ToolSpec, result: ChildResult, structured: Any) -> str:
    if isinstance(structured, dict) and isinstance(structured.get("detail"), str):
        return redact(str(structured["detail"]))
    stderr = result.stderr.strip()
    if stderr:
        return redact(stderr.splitlines()[-1])
    return f"{spec.verb} exited {result.returncode}"


def _error_result(
    code: str,
    detail: str,
    *,
    exit_code: int | None,
    structured: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "detail": detail}
    if exit_code is not None:
        payload["exit"] = exit_code
    if structured:
        payload.update({key: value for key, value in structured.items() if key != "code"})
        payload["code"] = code
    line = f"{code}: {detail}" if detail else code
    return protocol.tool_result(
        [protocol.text_content(redact(line))],
        structured=payload,
        is_error=True,
    )


def _maybe_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def catalog() -> dict[str, Any]:
    """The capability catalog `mcp inspect` prints, and docs are checked against."""
    return {
        "server": {"name": SERVER_NAME, "version": __version__},
        "protocol": {
            "revision": protocol.PROTOCOL_REVISION,
            "supported": list(protocol.SUPPORTED_REVISIONS),
        },
        "tools": [spec.as_tool() for spec in TOOLS],
        "resources": [
            {
                "uri": spec.uri,
                "name": spec.name,
                "description": spec.description,
                "mimeType": spec.mime_type,
            }
            for spec in RESOURCES
        ],
    }
