import type { AgentEvent, ToolKind } from "@caztor/core";
import { classifyError, MAX_LINE_BYTES, MAX_MALFORMED_LINES, stripAnsi } from "../claude/mapper.ts";

const MAX_TITLE_CHARS = 200;
const MAX_DETAIL_CHARS = 1000;
const MAX_MESSAGE_CHARS = 500;
const MAX_TRACKED_ITEMS = 1000;

export interface CodexMapOutcome {
  events: AgentEvent[];
  /** Nothing more is expected from the CLI, though it has not exited: a process that lingers is ended. */
  final: boolean;
  /** True once the mapper decided the stream cannot be trusted; its events already end the turn. */
  fatal: boolean;
}

export interface CodexMapper {
  /** Reads one line of the CLI's JSON output. */
  feed(line: string): CodexMapOutcome;
  /** One warning notice the first time a line is dropped for its size in the turn; nothing after. */
  oversize(): AgentEvent[];
  /** The process ended: closes the turn if the CLI did not. */
  finish(how: { cancelled: boolean; exitCode?: number | null; stderrTail?: string }): AgentEvent[];
}

export interface CodexMapperOptions {
  /** Absolute path of the project folder, to turn the path of a file change into a path inside the project. */
  root: string;
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const asString = (value: unknown): string | null => (typeof value === "string" ? value : null);
const cut = (text: string, limit: number) => (text.length > limit ? `${text.slice(0, limit)}...` : text);
const oneLine = (text: string, limit: number) => cut(stripAnsi(text).replace(/\s+/g, " ").trim(), limit);

const SIGN_IN_MESSAGE = "Codex is not signed in. Run `codex login` in a terminal, then try again.";

function failure(message: string): AgentEvent {
  const text = oneLine(message, MAX_MESSAGE_CHARS) || "Codex reported an error.";
  const code = classifyError(text);
  if (code === "auth") return { type: "error", code, message: SIGN_IN_MESSAGE, detail: oneLine(message, MAX_DETAIL_CHARS) };
  return { type: "error", code, message: text };
}

/**
 * Turns the lines of `codex exec --json` into normalized events. The shapes are the ones the documentation lists, read
 * leniently: the item kind is the `type` key or the older `item_type`, and unknown events and items are ignored. A
 * finished message arrives whole. The reasoning of the model is never passed on.
 */
export function createCodexMapper(options: CodexMapperOptions): CodexMapper {
  const prefix = `${options.root.replace(/\/+$/, "")}/`;
  let sessionSent = false;
  let finished = false;
  let malformed = 0;
  let oversizeReported = false;
  let failed: string | null = null;
  let streamError: string | null = null;
  const started = new Set<string>();

  /** The path inside the project that a path names, or null. */
  function inside(raw: string | null): string | null {
    if (raw === null) return null;
    const relative = raw.startsWith(prefix) ? raw.slice(prefix.length) : raw.startsWith("/") ? null : raw;
    if (relative === null || relative === "" || relative.split("/").some((part) => part === ".." || part === "")) return null;
    return relative;
  }

  function begin(events: AgentEvent[], toolId: string, name: string, kind: ToolKind, title: string | null, path: string | null): void {
    if (started.has(toolId)) return;
    if (started.size >= MAX_TRACKED_ITEMS) started.clear();
    started.add(toolId);
    events.push({ type: "tool_start", toolId, name, kind, ...(path === null ? {} : { path }) });
    if (title !== null && title !== "") events.push({ type: "tool_update", toolId, title: oneLine(title, MAX_TITLE_CHARS) });
  }

  function tool(kind: string, id: string, body: Record<string, unknown>, done: boolean, events: AgentEvent[]): void {
    const status = asString(body["status"]);
    let summary: string | null = null;
    switch (kind) {
      case "command_execution":
        begin(events, id, "command", "command", asString(body["command"]), null);
        if (typeof body["exit_code"] === "number" && status === "failed") summary = `Exit code ${body["exit_code"]}`;
        break;
      case "file_change": {
        const changes = Array.isArray(body["changes"]) ? body["changes"].filter(isRecord) : [];
        const path = inside(changes.length === 0 ? null : asString(changes[0]!["path"]));
        const adds = changes.length > 0 && changes.every((change) => change["kind"] === "add");
        begin(events, id, "file_change", adds ? "write" : "edit", null, path);
        break;
      }
      case "web_search":
        begin(events, id, "web_search", "other", asString(body["query"]), null);
        break;
      default:
        begin(events, id, `${asString(body["server"]) ?? "mcp"}/${asString(body["tool"]) ?? "tool"}`, "other", null, null);
    }
    if (!done) return;
    const bad = status === "failed" || status === "declined";
    events.push({ type: "tool_end", toolId: id, status: bad ? "failed" : "done", ...(bad && summary !== null ? { summary } : {}) });
  }

  function item(phase: "started" | "completed", raw: unknown, events: AgentEvent[]): void {
    if (!isRecord(raw)) return;
    const id = asString(raw["id"]);
    const rawKind = asString(raw["type"]) ?? asString(raw["item_type"]);
    if (id === null || rawKind === null) return;
    const kind = rawKind === "assistant_message" ? "agent_message" : rawKind;
    switch (kind) {
      case "agent_message": {
        const text = asString(raw["text"]);
        if (phase === "completed" && text !== null && text !== "") events.push({ type: "text", messageId: id, text });
        return;
      }
      case "command_execution":
      case "file_change":
      case "web_search":
      case "mcp_tool_call":
        tool(kind, id, raw, phase === "completed", events);
        return;
      case "error": {
        const message = asString(raw["message"]);
        if (phase === "completed" && message !== null) events.push({ type: "notice", level: "warning", message: `Codex reported: ${oneLine(message, MAX_MESSAGE_CHARS)}` });
        return;
      }
      default:
        // Reasoning, plan updates and kinds added later are not shown.
    }
  }

  function oversize(): AgentEvent[] {
    if (oversizeReported) return [];
    oversizeReported = true;
    return [{ type: "notice", level: "warning", message: "Codex sent a line that was too long to read, so Caztor skipped it. Some of its output may be missing." }];
  }

  function completed(parsed: Record<string, unknown>, events: AgentEvent[]): void {
    finished = true;
    if (streamError !== null) events.push({ type: "notice", level: "warning", message: `Codex reported: ${oneLine(streamError, MAX_MESSAGE_CHARS)}` });
    const usage = isRecord(parsed["usage"]) ? parsed["usage"] : {};
    const input = typeof usage["input_tokens"] === "number" ? usage["input_tokens"] : null;
    const output = typeof usage["output_tokens"] === "number" ? usage["output_tokens"] : null;
    const summary = { ...(input === null ? {} : { inputTokens: input }), ...(output === null ? {} : { outputTokens: output }) };
    events.push({ type: "done", reason: "completed", ...(Object.keys(summary).length > 0 ? { usage: summary } : {}) });
  }

  return {
    oversize,
    feed(rawLine) {
      const none: CodexMapOutcome = { events: [], final: false, fatal: false };
      if (finished) return none;
      if (rawLine.length > MAX_LINE_BYTES) return { events: oversize(), final: false, fatal: false };
      const text = stripAnsi(rawLine).trim();
      if (text === "") return none;
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch {
        malformed += 1;
        if (malformed < MAX_MALFORMED_LINES) return none;
        finished = true;
        return {
          events: [
            { type: "error", code: "malformed_output", message: "Codex sent output Caztor could not read." },
            { type: "done", reason: "failed" },
          ],
          final: true,
          fatal: true,
        };
      }
      malformed = 0;
      if (!isRecord(parsed)) return none;

      const events: AgentEvent[] = [];
      let final = false;
      switch (parsed["type"]) {
        case "thread.started": {
          const threadId = asString(parsed["thread_id"]);
          if (!sessionSent && threadId !== null && threadId !== "") {
            sessionSent = true;
            events.push({ type: "session", sessionId: threadId });
          }
          break;
        }
        case "item.started":
          item("started", parsed["item"], events);
          break;
        case "item.completed":
          item("completed", parsed["item"], events);
          break;
        case "turn.completed":
          completed(parsed, events);
          final = true;
          break;
        case "turn.failed": {
          const error = isRecord(parsed["error"]) ? parsed["error"] : {};
          failed ??= asString(error["message"]) ?? "";
          final = true;
          break;
        }
        case "error":
          streamError ??= asString(parsed["message"]) ?? "";
          break;
        default:
      }
      return { events, final, fatal: false };
    },

    finish({ cancelled, stderrTail }) {
      if (finished) return [];
      finished = true;
      if (cancelled) return [{ type: "done", reason: "cancelled" }];
      const reason = failed ?? streamError;
      if (reason !== null) return [failure(reason), { type: "done", reason: "failed" }];
      const detail = stderrTail === undefined ? "" : oneLine(stderrTail, MAX_DETAIL_CHARS);
      return [
        { type: "error", code: "provider_error", message: "Codex stopped before it finished its answer.", ...(detail === "" ? {} : { detail }) },
        { type: "done", reason: "failed" },
      ];
    },
  };
}
