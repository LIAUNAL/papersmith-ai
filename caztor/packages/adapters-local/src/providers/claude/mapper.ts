import type { AgentEvent, ToolKind, TurnErrorCode } from "@caztor/core";

/** A line longer than this is dropped without being parsed. */
export const MAX_LINE_BYTES = 1_000_000;
/** This many lines in a row that are not JSON end the turn. */
export const MAX_MALFORMED_LINES = 20;
/** The input of one tool call is collected up to this size; a larger one gets no path hint. */
const MAX_TOOL_INPUT_CHARS = 256 * 1024;
const MAX_SUMMARY_CHARS = 200;
const MAX_DETAIL_CHARS = 1000;
const MAX_MESSAGE_CHARS = 500;
const MAX_TRACKED_TOOLS = 1000;

/** What `system/init` says about the session: the runner checks it against the isolation it asked for. */
export interface ClaudeInit {
  sessionId: string;
  tools: string[];
  mcpServers: Array<{ name: string; status: string }>;
}

export interface MapOutcome {
  events: AgentEvent[];
  init?: ClaudeInit;
  /** True once the mapper decided the stream cannot be trusted; its events already end the turn. */
  fatal: boolean;
}

export interface ClaudeMapper {
  /** Reads one line of the CLI's stream. */
  feed(line: string): MapOutcome;
  /** The stream ended: closes the turn if the CLI did not. */
  /** One warning notice the first time a line is dropped for its size in the turn; nothing after. */
  oversize(): AgentEvent[];
  finish(how: { cancelled: boolean; stderrTail?: string }): AgentEvent[];
}

export interface ClaudeMapperOptions {
  /** Absolute path of the project folder, to turn the absolute path of a tool call into a path inside the project. */
  root: string;
}

const ANSI = /\u001b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\u0007\u001b]*(?:\u0007|\u001b\\)|[@-Z\\-_])/g;
export const stripAnsi = (text: string): string => text.replace(ANSI, "");

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const asString = (value: unknown): string | null => (typeof value === "string" ? value : null);
const cut = (text: string, limit: number) => (text.length > limit ? `${text.slice(0, limit)}...` : text);
const oneLine = (text: string, limit: number) => cut(stripAnsi(text).replace(/\s+/g, " ").trim(), limit);

function kindOf(name: string): ToolKind {
  switch (name) {
    case "Read":
      return "read";
    case "Edit":
    case "MultiEdit":
    case "NotebookEdit":
      return "edit";
    case "Write":
      return "write";
    case "Glob":
    case "Grep":
      return "search";
    case "Bash":
    case "PowerShell":
      return "command";
    default:
      return "other";
  }
}

/** Which error the CLI's text means. The CLI has no code field for these, so the text is all there is. */
export function classifyError(message: string): TurnErrorCode {
  if (/api key|log ?in|oauth|credential|unauthori[sz]ed|authenticat|\b40[13]\b/i.test(message)) return "auth";
  if (/rate.?limit|usage limit|hit your limit|too many requests|\b429\b/i.test(message)) return "rate_limited";
  if (/model/i.test(message) && /not found|not exist|unavailable|not available|issue with the selected|\b404\b/i.test(message)) return "model_unavailable";
  if (/time(d)?[ -]?out/i.test(message)) return "timeout";
  if (/permission/i.test(message)) return "permission_denied";
  return "provider_error";
}

function textOfResult(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.map((block) => (isRecord(block) && typeof block["text"] === "string" ? block["text"] : "")).join(" ");
}

interface ToolBlock {
  toolId: string;
  kind: ToolKind;
  json: string;
  overflow: boolean;
}

/**
 * Turns the lines of `claude -p --output-format stream-json --include-partial-messages` into normalized events. It keeps
 * no text: deltas pass straight through, and the only buffer is the input of one tool call at a time, up to a limit.
 * Thinking blocks and their signatures are never passed on.
 */
export function createClaudeMapper(options: ClaudeMapperOptions): ClaudeMapper {
  const prefix = `${options.root.replace(/\/+$/, "")}/`;
  let sessionSent = false;
  let finished = false;
  let malformed = 0;
  let errorSent = false;
  let warnedLimit = false;
  let messageId = "message";
  const blocks = new Map<number, ToolBlock>();
  const hinted = new Set<string>();

  /** The path inside the project that a tool input names, or null. */
  function pathOf(kind: ToolKind, input: unknown): string | null {
    if (!isRecord(input) || (kind !== "read" && kind !== "edit" && kind !== "write")) return null;
    const raw = asString(input["file_path"]) ?? asString(input["notebook_path"]);
    if (raw === null) return null;
    const relative = raw.startsWith(prefix) ? raw.slice(prefix.length) : raw.startsWith("/") ? null : raw;
    if (relative === null || relative === "" || relative.split("/").some((part) => part === ".." || part === "")) return null;
    return relative;
  }

  function hint(events: AgentEvent[], toolId: string, kind: ToolKind, input: unknown): void {
    if (hinted.has(toolId)) return;
    const path = pathOf(kind, input);
    if (path === null) return;
    if (hinted.size >= MAX_TRACKED_TOOLS) hinted.clear();
    hinted.add(toolId);
    events.push({ type: "tool_update", toolId, path });
  }

  function done(events: AgentEvent[], event: Extract<AgentEvent, { type: "done" }>): void {
    finished = true;
    events.push(event);
  }

  function streamEvent(obj: Record<string, unknown>, events: AgentEvent[]): void {
    const event = obj["event"];
    if (!isRecord(event)) return;
    const id = asString(obj["api_message_id"]) ?? messageId;
    switch (event["type"]) {
      case "message_start": {
        const message = event["message"];
        const started = isRecord(message) ? asString(message["id"]) : null;
        if (started !== null) messageId = started;
        blocks.clear();
        return;
      }
      case "content_block_start": {
        const block = event["content_block"];
        const index = event["index"];
        if (!isRecord(block) || typeof index !== "number" || block["type"] !== "tool_use") return;
        const toolId = asString(block["id"]);
        const name = asString(block["name"]);
        if (toolId === null || name === null) return;
        const kind = kindOf(name);
        blocks.set(index, { toolId, kind, json: "", overflow: false });
        events.push({ type: "tool_start", toolId, name, kind });
        return;
      }
      case "content_block_delta": {
        const delta = event["delta"];
        if (!isRecord(delta)) return;
        if (delta["type"] === "text_delta" && typeof delta["text"] === "string") {
          events.push({ type: "text_delta", messageId: id, text: delta["text"] });
        } else if (delta["type"] === "input_json_delta" && typeof delta["partial_json"] === "string" && typeof event["index"] === "number") {
          const block = blocks.get(event["index"]);
          if (block === undefined || block.overflow) return;
          block.json += delta["partial_json"];
          if (block.json.length > MAX_TOOL_INPUT_CHARS) {
            block.overflow = true;
            block.json = "";
          }
        }
        return;
      }
      case "content_block_stop": {
        const index = event["index"];
        const block = typeof index === "number" ? blocks.get(index) : undefined;
        if (block === undefined || typeof index !== "number") return;
        blocks.delete(index);
        if (block.overflow || block.json === "") return;
        try {
          hint(events, block.toolId, block.kind, JSON.parse(block.json));
        } catch {
          // An input that is not JSON gives no hint.
        }
        return;
      }
      default:
    }
  }

  function assistant(obj: Record<string, unknown>, events: AgentEvent[]): void {
    const message = obj["message"];
    if (!isRecord(message) || !Array.isArray(message["content"])) return;
    const id = asString(message["id"]) ?? messageId;
    for (const block of message["content"]) {
      if (!isRecord(block)) continue;
      if (block["type"] === "text" && typeof block["text"] === "string") {
        events.push({ type: "text", messageId: id, text: block["text"] });
      } else if (block["type"] === "tool_use") {
        const toolId = asString(block["id"]);
        const name = asString(block["name"]);
        if (toolId !== null && name !== null) hint(events, toolId, kindOf(name), block["input"]);
      }
    }
  }

  function toolResults(obj: Record<string, unknown>, events: AgentEvent[]): void {
    const message = obj["message"];
    if (!isRecord(message) || !Array.isArray(message["content"])) return;
    for (const block of message["content"]) {
      if (!isRecord(block) || block["type"] !== "tool_result") continue;
      const toolId = asString(block["tool_use_id"]);
      if (toolId === null) continue;
      if (block["is_error"] === true) {
        const summary = oneLine(textOfResult(block["content"]), MAX_SUMMARY_CHARS);
        events.push({ type: "tool_end", toolId, status: "failed", ...(summary === "" ? {} : { summary }) });
      } else {
        events.push({ type: "tool_end", toolId, status: "done" });
      }
    }
  }

  function rateLimit(obj: Record<string, unknown>, events: AgentEvent[]): void {
    const info = obj["rate_limit_info"];
    if (!isRecord(info)) return;
    if (info["status"] === "rejected" && !errorSent) {
      errorSent = true;
      const resets = typeof info["resetsAt"] === "number" ? new Date(info["resetsAt"] * 1000) : null;
      const when = resets === null || Number.isNaN(resets.getTime()) ? "" : ` It can be used again at ${resets.toISOString().slice(0, 16).replace("T", " ")} UTC.`;
      events.push({ type: "error", code: "rate_limited", message: `Claude Code reached its usage limit.${when}` });
    } else if (info["status"] === "allowed_warning" && !warnedLimit) {
      warnedLimit = true;
      events.push({ type: "notice", level: "info", message: "Claude Code is close to its usage limit." });
    }
  }

  function result(obj: Record<string, unknown>, events: AgentEvent[]): void {
    const isError = obj["is_error"] === true;
    if (isError && !errorSent) {
      errorSent = true;
      const message = oneLine(asString(obj["result"]) ?? "", MAX_MESSAGE_CHARS) || "Claude Code reported an error.";
      events.push({ type: "error", code: classifyError(message), message });
    }
    const denials = Array.isArray(obj["permission_denials"]) ? obj["permission_denials"] : [];
    if (denials.length > 0) {
      const names = [...new Set(denials.map((denial) => (isRecord(denial) ? asString(denial["tool_name"]) : null)).filter((name): name is string => name !== null))];
      const plural = denials.length === 1 ? "request" : "requests";
      events.push({
        type: "notice",
        level: "warning",
        message: `Claude Code refused ${denials.length} tool ${plural}${names.length > 0 ? `: ${names.join(", ")}` : ""}.`,
      });
    }
    const usage = isRecord(obj["usage"]) ? obj["usage"] : {};
    const count = (key: string) => (typeof usage[key] === "number" ? (usage[key] as number) : null);
    const input = [count("input_tokens"), count("cache_creation_input_tokens"), count("cache_read_input_tokens")].filter((value): value is number => value !== null);
    const output = count("output_tokens");
    const cost = typeof obj["total_cost_usd"] === "number" ? obj["total_cost_usd"] : null;
    const summary = {
      ...(input.length > 0 ? { inputTokens: input.reduce((sum, value) => sum + value, 0) } : {}),
      ...(output === null ? {} : { outputTokens: output }),
      ...(cost === null ? {} : { costUsd: cost }),
    };
    done(events, { type: "done", reason: isError ? "failed" : "completed", ...(Object.keys(summary).length > 0 ? { usage: summary } : {}) });
  }

  function initOf(obj: Record<string, unknown>): ClaudeInit {
    const tools = Array.isArray(obj["tools"]) ? obj["tools"].filter((tool): tool is string => typeof tool === "string") : [];
    const servers = Array.isArray(obj["mcp_servers"]) ? obj["mcp_servers"] : [];
    const mcpServers = servers
      .filter(isRecord)
      .map((server) => ({ name: asString(server["name"]) ?? "", status: asString(server["status"]) ?? "" }));
    return { sessionId: asString(obj["session_id"]) ?? "", tools, mcpServers };
  }

  /** One warning per turn, however many lines were dropped for their size. */
  let oversizeReported = false;
  function oversize(): AgentEvent[] {
    if (oversizeReported) return [];
    oversizeReported = true;
    return [{ type: "notice", level: "warning", message: "Claude Code sent a line that was too long to read, so Caztor skipped it. Some of its output may be missing." }];
  }

  return {
    /** Called when the line reader dropped a line for its size before it reached `feed`. */
    oversize,
    feed(rawLine) {
      const none: MapOutcome = { events: [], fatal: false };
      if (finished) return none;
      if (rawLine.length > MAX_LINE_BYTES) return { events: oversize(), fatal: false };
      const text = stripAnsi(rawLine).trim();
      if (text === "") return none;
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch {
        malformed += 1;
        if (malformed < MAX_MALFORMED_LINES) return none;
        const events: AgentEvent[] = [{ type: "error", code: "malformed_output", message: "Claude Code sent output Caztor could not read." }];
        done(events, { type: "done", reason: "failed" });
        return { events, fatal: true };
      }
      malformed = 0;
      if (!isRecord(parsed)) return none;

      const events: AgentEvent[] = [];
      const sessionId = asString(parsed["session_id"]);
      if (!sessionSent && sessionId !== null && sessionId !== "") {
        sessionSent = true;
        events.push({ type: "session", sessionId });
      }
      let init: ClaudeInit | undefined;
      switch (parsed["type"]) {
        case "system":
          if (parsed["subtype"] === "init") init = initOf(parsed);
          break;
        case "stream_event":
          streamEvent(parsed, events);
          break;
        case "assistant":
          assistant(parsed, events);
          break;
        case "user":
          toolResults(parsed, events);
          break;
        case "rate_limit_event":
          rateLimit(parsed, events);
          break;
        case "result":
          result(parsed, events);
          break;
        default:
      }
      return init === undefined ? { events, fatal: false } : { events, init, fatal: false };
    },

    finish({ cancelled, stderrTail }) {
      if (finished) return [];
      const events: AgentEvent[] = [];
      if (!cancelled) {
        const detail = stderrTail === undefined ? "" : oneLine(stderrTail, MAX_DETAIL_CHARS);
        events.push({
          type: "error",
          code: "provider_error",
          message: "Claude Code stopped before it finished its answer.",
          ...(detail === "" ? {} : { detail }),
        });
      }
      done(events, { type: "done", reason: cancelled ? "cancelled" : "failed" });
      return events;
    },
  };
}
