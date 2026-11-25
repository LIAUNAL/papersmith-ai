import type { AgentEvent, ToolKind } from "@caztor/core";
import { MAX_LINE_BYTES, MAX_MALFORMED_LINES, stripAnsi } from "../claude/mapper.ts";

export { MAX_LINE_BYTES, MAX_MALFORMED_LINES };

/** Pi's own names for the tools that read, search and edit files. `bash` and every other tool are refused. */
export const PI_ALLOWED_TOOLS = ["read", "edit", "write", "grep", "find", "ls"] as const;
export type PiAllowedTool = (typeof PI_ALLOWED_TOOLS)[number];

export const PI_ISOLATION_TIER = "P1";
/** The CLI version the flags and the stream were checked against; an older one gets a warning. */
export const PI_TESTED_VERSION = "1.4.0";

export const PI_LOGIN_HINT = "Sign in with Pi: run `pi`, then `/login`.";

const SESSION_ID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_MESSAGE_CHARS = 500;
/** The events that run nothing. Any other event whose name mentions a tool counts as an unnamed tool, which the guard refuses. */
const KNOWN_TOOL_EVENTS: ReadonlySet<string> = new Set(["tool_execution_start", "tool_execution_update", "tool_execution_end"]);
const KNOWN_INNER_TOOL_EVENTS: ReadonlySet<string> = new Set(["toolcall_start", "toolcall_delta", "toolcall_end"]);

/** A tool the stream named: what the runner's guard judges. An empty name means the stream was unclear about it. */
export interface PiToolReport {
  name: string;
}

export interface PiMapOutcome {
  events: AgentEvent[];
  tool?: PiToolReport;
  fatal: boolean;
  final?: boolean;
}

export interface PiMapper {
  feed(line: string): PiMapOutcome;
  oversize(): AgentEvent[];
  finish(how: { cancelled: boolean; exitCode?: number | null; stderrTail?: string }): AgentEvent[];
}

export interface PiMapperOptions {
  root: string;
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const asString = (value: unknown): string | null => (typeof value === "string" ? value : null);
const asNumber = (value: unknown): number => (typeof value === "number" && Number.isFinite(value) ? value : 0);
const cut = (text: string, limit: number) => (text.length > limit ? `${text.slice(0, limit)}...` : text);
const oneLine = (text: string, limit: number) => cut(stripAnsi(text).replace(/\s+/g, " ").trim(), limit);

export function kindOf(tool: string): ToolKind {
  switch (tool) {
    case "read":
      return "read";
    case "edit":
      return "edit";
    case "write":
      return "write";
    case "grep":
    case "find":
    case "ls":
      return "search";
    case "bash":
    case "powershell":
      return "command";
    default:
      return "other";
  }
}

const isRateLimit = (text: string) => /\b429\b|\b529\b|rate.?limit|too many requests|quota|RESOURCE_EXHAUSTED|overloaded/i.test(text);
const isAuthProblem = (text: string) => /\b401\b|\b403\b|unauthori[sz]ed|invalid[^.\n]{0,20}api.?key|authenticat|No API key found|No models available/i.test(text);
const UNKNOWN_MODEL = /Model "[^"\n]*" not found[^\n]*/;

/** The error and done events for a failure Pi reported, by what its text says it was. */
function failure(reported: string): AgentEvent[] {
  const text = oneLine(reported, MAX_MESSAGE_CHARS);
  const unknownModel = UNKNOWN_MODEL.exec(reported);
  if (unknownModel !== null) return [{ type: "error", code: "model_unavailable", message: oneLine(unknownModel[0], MAX_MESSAGE_CHARS) }, { type: "done", reason: "failed" }];
  if (isRateLimit(reported)) return [{ type: "error", code: "rate_limited", message: text || "Pi's model provider is limiting requests. Try again later." }, { type: "done", reason: "failed" }];
  if (isAuthProblem(reported)) return [{ type: "error", code: "auth", message: PI_LOGIN_HINT, ...(text === "" ? {} : { detail: text }) }, { type: "done", reason: "failed" }];
  return [{ type: "error", code: "provider_error", message: text || "Pi reported an error." }, { type: "done", reason: "failed" }];
}

/**
 * Turns the JSONL of `pi --mode json` into normalized events. `message_end` is the authoritative message; a failed
 * response is read from its `stopReason` and `errorMessage` and from `auto_retry_end`, because the CLI exits 0 even then.
 * The turn ends at `agent_settled`, when Pi has no retry or other automatic work left.
 */
export function createPiMapper(options: PiMapperOptions): PiMapper {
  const prefix = `${options.root.replace(/\/+$/, "")}/`;
  let sessionSent = false;
  let finished = false;
  let malformed = 0;
  let oversizeReported = false;
  let messages = 0;
  let toolCount = 0;
  let agentEnded = false;
  /** The failure of the latest assistant response, or of the last retry; cleared by a response that succeeded. */
  let lastError: string | null = null;
  let truncated = false;
  let inputTokens = 0;
  let outputTokens = 0;
  /** Pi's tool call id to the id the chat uses, and the name Pi first gave the call. */
  const calls = new Map<string, { toolId: string; name: string; started: boolean }>();

  function inside(raw: string | null): string | null {
    if (raw === null) return null;
    const relative = raw.startsWith(prefix) ? raw.slice(prefix.length) : raw.startsWith("/") ? null : raw.replace(/^\.\//, "");
    if (relative === null || relative === "" || relative.split("/").some((part) => part === ".." || part === "")) return null;
    return relative;
  }

  /** The name to report for a call: the one given, unless the stream named the same call differently before. */
  function nameOf(callId: string | null, name: string | null): string {
    if (name === null || name === "") return "";
    if (callId === null) return name;
    const known = calls.get(callId);
    if (known === undefined) {
      calls.set(callId, { toolId: `tool_${++toolCount}`, name, started: false });
      return name;
    }
    return known.name === name ? name : "";
  }

  function oversize(): AgentEvent[] {
    if (oversizeReported) return [];
    oversizeReported = true;
    return [{ type: "notice", level: "warning", message: "Pi sent a line that was too long to read, so Caztor skipped it. Some of its output may be missing." }];
  }

  /** The end of the turn once Pi has no automatic work left. */
  function settle(aborted: boolean): AgentEvent[] {
    finished = true;
    const events: AgentEvent[] = [];
    for (const call of calls.values()) {
      if (call.started) events.push({ type: "tool_end", toolId: call.toolId, status: "failed" });
    }
    calls.clear();
    if (lastError !== null) return [...events, ...failure(lastError)];
    if (aborted) return [...events, { type: "error", code: "provider_error", message: "Pi stopped the answer before it finished." }, { type: "done", reason: "failed" }];
    if (truncated) events.push({ type: "notice", level: "warning", message: "Pi's answer was cut off at the model's output limit, so it may be incomplete." });
    const usage = { ...(inputTokens > 0 ? { inputTokens } : {}), ...(outputTokens > 0 ? { outputTokens } : {}) };
    events.push({ type: "done", reason: "completed", ...(Object.keys(usage).length > 0 ? { usage } : {}) });
    return events;
  }

  function assistantEnd(message: Record<string, unknown>, events: AgentEvent[]): void {
    const content = Array.isArray(message["content"]) ? message["content"] : [];
    const text = content.flatMap((block) => (isRecord(block) && block["type"] === "text" && typeof block["text"] === "string" ? [block["text"]] : [])).join("");
    if (text !== "") events.push({ type: "text", messageId: `msg_${Math.max(messages, 1)}`, text });
    if (isRecord(message["usage"])) {
      inputTokens += asNumber(message["usage"]["input"]);
      outputTokens += asNumber(message["usage"]["output"]);
    }
    const stopReason = asString(message["stopReason"]);
    if (stopReason === "error" || stopReason === "aborted") {
      lastError = asString(message["errorMessage"]) ?? (stopReason === "aborted" ? "Pi stopped the answer before it finished." : "Pi reported an error.");
    } else {
      lastError = null;
      truncated = stopReason === "length";
    }
  }

  return {
    oversize,

    feed(rawLine) {
      const none: PiMapOutcome = { events: [], fatal: false, final: false };
      if (finished) return none;
      if (rawLine.length > MAX_LINE_BYTES) return { events: oversize(), fatal: false, final: false };
      const text = rawLine.replace(/\r$/, "").trim();
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
            { type: "error", code: "malformed_output", message: "Pi sent output Caztor could not read." },
            { type: "done", reason: "failed" },
          ],
          fatal: true,
          final: true,
        };
      }
      malformed = 0;
      if (!isRecord(parsed)) return none;

      const events: AgentEvent[] = [];
      let tool: PiToolReport | undefined;
      const type = asString(parsed["type"]) ?? "";

      switch (type) {
        case "session": {
          const id = asString(parsed["id"]);
          if (!sessionSent && id !== null && SESSION_ID_REGEX.test(id)) {
            sessionSent = true;
            events.push({ type: "session", sessionId: id });
          }
          break;
        }

        case "message_start": {
          if (isRecord(parsed["message"]) && parsed["message"]["role"] === "assistant") messages += 1;
          break;
        }

        case "message_update": {
          const inner = isRecord(parsed["assistantMessageEvent"]) ? parsed["assistantMessageEvent"] : null;
          const innerType = inner === null ? "" : (asString(inner["type"]) ?? "");
          if (inner === null) break;
          if (innerType === "text_delta") {
            const delta = asString(inner["delta"]);
            if (delta !== null && delta !== "") events.push({ type: "text_delta", messageId: `msg_${Math.max(messages, 1)}`, text: delta });
          } else if (innerType === "toolcall_start") {
            tool = { name: nameOf(asString(inner["id"]), asString(inner["toolName"])) };
          } else if (innerType === "toolcall_end") {
            const call = isRecord(inner["toolCall"]) ? inner["toolCall"] : {};
            tool = { name: nameOf(asString(call["id"]), asString(call["name"])) };
          } else if (/tool/i.test(innerType) && !KNOWN_INNER_TOOL_EVENTS.has(innerType)) {
            tool = { name: "" };
          }
          // Thinking and the other block events carry nothing the chat shows.
          break;
        }

        case "message_end": {
          const message = isRecord(parsed["message"]) ? parsed["message"] : null;
          if (message !== null && message["role"] === "assistant") assistantEnd(message, events);
          break;
        }

        case "tool_execution_start":
        case "tool_execution_update":
        case "tool_execution_end": {
          const callId = asString(parsed["toolCallId"]);
          const name = nameOf(callId, asString(parsed["toolName"]));
          tool = { name };
          const call = callId === null ? undefined : calls.get(callId);
          if (call === undefined || name === "") break;
          if (type === "tool_execution_start" && !call.started) {
            call.started = true;
            const kind = kindOf(name);
            const args = isRecord(parsed["args"]) ? parsed["args"] : {};
            const path = kind === "read" || kind === "edit" || kind === "write" ? inside(asString(args["path"])) : null;
            events.push({ type: "tool_start", toolId: call.toolId, name, kind, ...(path === null ? {} : { path }) });
          } else if (type === "tool_execution_end" && call.started) {
            call.started = false;
            events.push({ type: "tool_end", toolId: call.toolId, status: parsed["isError"] === true ? "failed" : "done" });
          }
          break;
        }

        case "auto_retry_end": {
          if (parsed["success"] === false) lastError = asString(parsed["finalError"]) ?? lastError ?? "Pi gave up after retrying.";
          break;
        }

        case "agent_end": {
          agentEnded = true;
          break;
        }

        case "agent_settled": {
          return { events: [...events, ...settle(parsed["aborted"] === true)], fatal: false, final: true };
        }

        default:
          if (/tool/i.test(type) && !KNOWN_TOOL_EVENTS.has(type)) tool = { name: "" };
          // Turn, queue, compaction and retry-start events change nothing the chat shows.
          break;
      }

      return tool !== undefined ? { events, tool, fatal: false, final: false } : { events, fatal: false, final: false };
    },

    finish({ cancelled, exitCode, stderrTail }) {
      if (finished) return [];
      if (cancelled) {
        finished = true;
        const events: AgentEvent[] = [];
        for (const call of calls.values()) if (call.started) events.push({ type: "tool_end", toolId: call.toolId, status: "failed" });
        calls.clear();
        return [...events, { type: "done", reason: "cancelled" }];
      }
      // A run that ended normally but did not say it settled (an older CLI) ends as it would have.
      if (exitCode === 0 && agentEnded) return settle(false);
      const stderr = stderrTail ?? "";
      const dangling: AgentEvent[] = [];
      for (const call of calls.values()) if (call.started) dangling.push({ type: "tool_end", toolId: call.toolId, status: "failed" });
      calls.clear();
      finished = true;
      if (/No models available|No API key found/i.test(stderr)) {
        return [...dangling, { type: "error", code: "auth", message: PI_LOGIN_HINT }, { type: "done", reason: "failed" }];
      }
      if (UNKNOWN_MODEL.test(stderr) || isRateLimit(stderr)) return [...dangling, ...failure(stderr)];
      if (lastError !== null) return [...dangling, ...failure(lastError)];
      const detail = oneLine(stderr, MAX_MESSAGE_CHARS);
      return [
        ...dangling,
        { type: "error", code: "provider_error", message: "Pi stopped before it finished its answer.", ...(detail === "" ? {} : { detail }) },
        { type: "done", reason: "failed" },
      ];
    },
  };
}
