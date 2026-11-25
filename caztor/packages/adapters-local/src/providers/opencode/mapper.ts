import type { AgentEvent, ToolKind, TurnErrorCode } from "@caztor/core";
import { MAX_LINE_BYTES, MAX_MALFORMED_LINES, stripAnsi } from "../claude/mapper.ts";

const MAX_SUMMARY_CHARS = 200;
const MAX_DETAIL_CHARS = 1000;
const MAX_MESSAGE_CHARS = 500;

/** A tool call as the CLI reported it, for the runner's check against the tools Caztor allows. */
export interface OpencodeToolUse {
  name: string;
  status: string;
}

export interface OpencodeMapOutcome {
  events: AgentEvent[];
  /** Set for every `tool_use` line that reported a finished call. */
  tool?: OpencodeToolUse;
  /** True after an error or the final step: nothing more is expected, so a process that lingers can be ended. */
  final: boolean;
  /** True once the mapper decided the stream cannot be trusted; its events already end the turn. */
  fatal: boolean;
}

export interface OpencodeMapper {
  /** Reads one line of the CLI's JSON output. */
  feed(line: string): OpencodeMapOutcome;
  /** One warning notice the first time a line is dropped for its size in the turn; nothing after. */
  oversize(): AgentEvent[];
  /** The process ended: closes the turn. `exitCode` is null when a signal ended it. */
  finish(how: { cancelled: boolean; exitCode?: number | null; stderrTail?: string }): AgentEvent[];
}

export interface OpencodeMapperOptions {
  /** Absolute path of the project folder, to turn the absolute path of a tool call into a path inside the project. */
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
    case "multiedit":
    case "patch":
    case "apply_patch":
      return "edit";
    case "write":
      return "write";
    case "glob":
    case "grep":
    case "list":
      return "search";
    case "bash":
      return "command";
    default:
      return "other";
  }
}

const AUTH_MESSAGE = "opencode could not sign in to the provider. Run `opencode providers login` in a terminal, then try again.";

/** What an `error` event means for the user. The CLI gives a name and an HTTP status; the text is the rest. */
export function classifyError(name: string, status: number | null, message: string): { code: TurnErrorCode; message: string; keepDetail: boolean } {
  const modelWord = /model/i.test(message);
  if (status === 403 && /free tier/i.test(message)) {
    return { code: "model_unavailable", message: "opencode's free models cannot be used from Caztor. Choose another model in the model setting, one from a provider you are signed in to.", keepDetail: true };
  }
  if (name === "ProviderModelNotFoundError" || (status === 404 && modelWord)) {
    return { code: "model_unavailable", message: "opencode could not find this model. Choose another model in the model setting.", keepDetail: true };
  }
  if ((status === 400 || status === 422) && modelWord && /not supported|unsupported|not found|does not exist|not available|invalid/i.test(message)) {
    return { code: "model_unavailable", message: "The provider does not accept this model with your account. Choose another model in the model setting.", keepDetail: true };
  }
  if (name === "ProviderAuthError" || status === 401 || status === 403) return { code: "auth", message: AUTH_MESSAGE, keepDetail: true };
  if (status === 429) return { code: "rate_limited", message: "The provider's rate limit was reached. Wait a moment and try again.", keepDetail: true };
  if (status === 408 || /time(d)?[ -]?out/i.test(message)) return { code: "timeout", message: oneLine(message, MAX_MESSAGE_CHARS) || "The provider took too long to answer.", keepDetail: false };
  return { code: "provider_error", message: oneLine(message, MAX_MESSAGE_CHARS) || "opencode reported an error.", keepDetail: false };
}

/**
 * Turns the lines of `opencode run --format json` into normalized events. The CLI sends whole blocks: a text event holds
 * the complete text, and a tool event comes once, when the call has finished. The only thing kept between lines is the
 * usage sum and the error to report when the process ends.
 */
export function createOpencodeMapper(options: OpencodeMapperOptions): OpencodeMapper {
  const prefix = `${options.root.replace(/\/+$/, "")}/`;
  let sessionSent = false;
  let finished = false;
  let malformed = 0;
  let oversizeReported = false;
  let steps = 0;
  let stopped = false;
  let input = 0;
  let output = 0;
  let cost = 0;
  let costSeen = false;
  let pendingError: AgentEvent | null = null;
  let earlyEnd: string | null = null;

  /** The path inside the project that a path names, or null. */
  function inside(raw: string | null): string | null {
    if (raw === null) return null;
    const relative = raw.startsWith(prefix) ? raw.slice(prefix.length) : raw.startsWith("/") ? null : raw;
    if (relative === null || relative === "" || relative.split("/").some((part) => part === ".." || part === "")) return null;
    return relative;
  }

  function pathOf(kind: ToolKind, state: Record<string, unknown>): string | null {
    if (kind !== "read" && kind !== "edit" && kind !== "write") return null;
    const input = isRecord(state["input"]) ? state["input"] : {};
    const direct = inside(asString(input["filePath"]) ?? asString(input["file_path"]) ?? asString(input["path"]));
    if (direct !== null) return direct;
    const metadata = isRecord(state["metadata"]) ? state["metadata"] : {};
    const files = Array.isArray(metadata["files"]) ? metadata["files"] : [];
    const first = files.find(isRecord);
    return first === undefined ? null : inside(asString(first["filePath"]));
  }

  function tool(part: Record<string, unknown>, events: AgentEvent[]): OpencodeToolUse | undefined {
    const name = asString(part["tool"]);
    const toolId = asString(part["callID"]);
    const state = part["state"];
    if (name === null || toolId === null || !isRecord(state)) return undefined;
    const status = asString(state["status"]);
    if (status !== "completed" && status !== "error") return undefined;
    const kind = kindOf(name);
    const path = pathOf(kind, state);
    events.push({ type: "tool_start", toolId, name, kind, ...(path === null ? {} : { path }) });
    if (status === "completed") {
      events.push({ type: "tool_end", toolId, status: "done" });
    } else {
      const summary = oneLine(asString(state["error"]) ?? "", MAX_SUMMARY_CHARS);
      events.push({ type: "tool_end", toolId, status: "failed", ...(summary === "" ? {} : { summary }) });
    }
    return { name, status };
  }

  function stepFinish(part: Record<string, unknown>): void {
    steps += 1;
    const tokens = isRecord(part["tokens"]) ? part["tokens"] : {};
    const cache = isRecord(tokens["cache"]) ? tokens["cache"] : {};
    input += asNumber(tokens["input"]) + asNumber(cache["read"]) + asNumber(cache["write"]);
    output += asNumber(tokens["output"]) + asNumber(tokens["reasoning"]);
    if (typeof part["cost"] === "number") {
      cost += part["cost"];
      costSeen = true;
    }
    const reason = asString(part["reason"]);
    if (reason !== null && reason !== "tool-calls") {
      stopped = true;
      if (reason !== "stop") earlyEnd = reason;
    }
  }

  function oversize(): AgentEvent[] {
    if (oversizeReported) return [];
    oversizeReported = true;
    return [{ type: "notice", level: "warning", message: "opencode sent a line that was too long to read, so Caztor skipped it. Some of its output may be missing." }];
  }

  return {
    oversize,
    feed(rawLine) {
      const none: OpencodeMapOutcome = { events: [], final: false, fatal: false };
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
            { type: "error", code: "malformed_output", message: "opencode sent output Caztor could not read." },
            { type: "done", reason: "failed" },
          ],
          final: true,
          fatal: true,
        };
      }
      malformed = 0;
      if (!isRecord(parsed)) return none;

      const events: AgentEvent[] = [];
      const sessionId = asString(parsed["sessionID"]);
      if (!sessionSent && sessionId !== null && sessionId !== "") {
        sessionSent = true;
        events.push({ type: "session", sessionId });
      }
      const part = isRecord(parsed["part"]) ? parsed["part"] : null;
      let used: OpencodeToolUse | undefined;
      let final = false;
      switch (parsed["type"]) {
        case "text": {
          const body = part === null ? null : asString(part["text"]);
          if (part !== null && body !== null && body !== "") events.push({ type: "text", messageId: asString(part["messageID"]) ?? "message", text: body });
          break;
        }
        case "tool_use":
          if (part !== null) used = tool(part, events);
          break;
        case "step_finish":
          if (part !== null) stepFinish(part);
          final = stopped;
          break;
        case "error": {
          if (pendingError !== null) break;
          const error = isRecord(parsed["error"]) ? parsed["error"] : {};
          const data = isRecord(error["data"]) ? error["data"] : {};
          const message = asString(data["message"]) ?? "";
          const status = typeof data["statusCode"] === "number" ? data["statusCode"] : null;
          const known = classifyError(asString(error["name"]) ?? "", status, stripAnsi(message));
          const detail = known.keepDetail ? oneLine(message, MAX_DETAIL_CHARS) : "";
          pendingError = { type: "error", code: known.code, message: known.message, ...(detail === "" ? {} : { detail }) };
          final = true;
          break;
        }
        default:
      }
      return used === undefined ? { events, final, fatal: false } : { events, tool: used, final, fatal: false };
    },

    finish({ cancelled, exitCode, stderrTail }) {
      if (finished) return [];
      finished = true;
      if (cancelled) return [{ type: "done", reason: "cancelled" }];
      const events: AgentEvent[] = [];
      if (pendingError !== null) {
        events.push(pendingError, { type: "done", reason: "failed" });
        return events;
      }
      if (stopped || (exitCode === 0 && steps > 0)) {
        if (earlyEnd !== null) events.push({ type: "notice", level: "warning", message: `opencode ended its answer early (reason: ${earlyEnd}).` });
        const usage = {
          ...(steps > 0 ? { inputTokens: input, outputTokens: output } : {}),
          ...(costSeen ? { costUsd: cost } : {}),
        };
        events.push({ type: "done", reason: "completed", ...(Object.keys(usage).length > 0 ? { usage } : {}) });
        return events;
      }
      const detail = stderrTail === undefined ? "" : oneLine(stderrTail, MAX_DETAIL_CHARS);
      events.push(
        { type: "error", code: "provider_error", message: "opencode stopped before it finished its answer.", ...(detail === "" ? {} : { detail }) },
        { type: "done", reason: "failed" },
      );
      return events;
    },
  };
}
