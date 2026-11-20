import type { AgentEvent, ToolKind } from "@caztor/core";
import { MAX_LINE_BYTES, MAX_MALFORMED_LINES, stripAnsi } from "../claude/mapper.ts";

export { MAX_LINE_BYTES, MAX_MALFORMED_LINES };

export const ANTIGRAVITY_ALLOWED_TOOLS = [
  "view_file",
  "list_dir",
  "find_by_name",
  "grep_search",
  "replace_file_content",
  "write_to_file",
] as const;

export type AntigravityAllowedTool = (typeof ANTIGRAVITY_ALLOWED_TOOLS)[number];

export const ANTIGRAVITY_ISOLATION_TIER = "P1";
export const ANTIGRAVITY_TESTED_VERSION = "1.4.12";

export const ANTIGRAVITY_LOGIN_HINT = "Sign in with Antigravity: run `agy` and follow the sign-in prompts.";

const SESSION_ID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_MESSAGE_CHARS = 500;
/** The step types that run nothing. Any other type could be a tool, so the runner's guard refuses it. */
const NON_TOOL_STEPS: ReadonlySet<string> = new Set(["agent_response", "user_input", "system_message", "error_message", "checkpoint"]);

export interface AntigravityToolStep {
  name: string;
  state: "ACTIVE" | "DONE" | string;
}

export interface AntigravityMapOutcome {
  events: AgentEvent[];
  tool?: AntigravityToolStep;
  fatal: boolean;
  final?: boolean;
}

export interface AntigravityMapper {
  feed(line: string): AntigravityMapOutcome;
  oversize(): AgentEvent[];
  finish(how: { cancelled: boolean; exitCode?: number | null; stderrTail?: string }): AgentEvent[];
}

export interface AntigravityMapperOptions {
  root: string;
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const asString = (value: unknown): string | null => (typeof value === "string" ? value : null);
const asNumber = (value: unknown): number => (typeof value === "number" && Number.isFinite(value) ? value : 0);
const cut = (text: string, limit: number) => (text.length > limit ? `${text.slice(0, limit)}...` : text);
const oneLine = (text: string, limit: number) => cut(stripAnsi(text).replace(/\s+/g, " ").trim(), limit);

export function kindOf(tool: string): ToolKind {
  switch (tool) {
    case "view_file":
      return "read";
    case "replace_file_content":
      return "edit";
    case "write_to_file":
      return "write";
    case "list_dir":
    case "find_by_name":
    case "grep_search":
      return "search";
    case "run_command":
    case "bash":
    case "command":
      return "command";
    default:
      return "other";
  }
}

function isQuotaProblem(text: string): boolean {
  return /RESOURCE_EXHAUSTED|quota|code 429|"error_code":\s*429/i.test(text);
}

function isAuthProblem(text: string): boolean {
  return /sign[ -]?in|authenticat|unauthori[sz]ed|log[ -]?in|credentials?/i.test(text);
}

function deniedActions(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const names = value.map((item) => (isRecord(item) ? asString(item["display_name"]) ?? asString(item["action"]) : null));
  return [...new Set(names.filter((name): name is string => name !== null && name !== ""))];
}

export function createAntigravityMapper(options: AntigravityMapperOptions): AntigravityMapper {
  const prefix = `${options.root.replace(/\/+$/, "")}/`;
  let sessionSent = false;
  let finished = false;
  let malformed = 0;
  let oversizeReported = false;
  let currentMessageText = "";
  let textEmitted = false;
  let resultReceived = false;
  // The result of a continued conversation counts every earlier turn too, so this turn's usage comes from its steps.
  let turnInputTokens = 0;
  let turnOutputTokens = 0;
  const activeTools = new Map<number, { toolId: string; name: string }>();

  function inside(raw: string | null): string | null {
    if (raw === null) return null;
    const relative = raw.startsWith(prefix) ? raw.slice(prefix.length) : raw.startsWith("/") ? null : raw;
    if (relative === null || relative === "" || relative.split("/").some((part) => part === ".." || part === "")) return null;
    return relative;
  }

  function pathOf(kind: ToolKind, params: Record<string, unknown>): string | null {
    if (kind !== "read" && kind !== "edit" && kind !== "write") return null;
    const raw = asString(params["AbsolutePath"]) ?? asString(params["TargetFile"]) ?? asString(params["FilePath"]) ?? asString(params["Path"]);
    return inside(raw);
  }

  function oversize(): AgentEvent[] {
    if (oversizeReported) return [];
    oversizeReported = true;
    return [{ type: "notice", level: "warning", message: "Antigravity sent a line that was too long to read, so Caztor skipped it. Some of its output may be missing." }];
  }

  return {
    oversize,

    feed(rawLine) {
      const none: AntigravityMapOutcome = { events: [], fatal: false, final: false };
      if (finished) return none;
      if (rawLine.length > MAX_LINE_BYTES) return { events: oversize(), fatal: false, final: false };
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
            { type: "error", code: "malformed_output", message: "Antigravity sent output Caztor could not read." },
            { type: "done", reason: "failed" },
          ],
          fatal: true,
          final: true,
        };
      }
      malformed = 0;
      if (!isRecord(parsed)) return none;

      const events: AgentEvent[] = [];
      let reportedTool: AntigravityToolStep | undefined;
      let isFinal = false;

      const convId = asString(parsed["conversation_id"]);
      if (!sessionSent && convId !== null && SESSION_ID_REGEX.test(convId)) {
        sessionSent = true;
        events.push({ type: "session", sessionId: convId });
      }

      const eventName = asString(parsed["event"]);
      switch (eventName) {
        case "init": {
          // init event handled: session already emitted if valid convId
          break;
        }

        case "step_update": {
          const update = isRecord(parsed["step_update"]) ? parsed["step_update"] : null;
          if (update === null) break;

          const stepIndex = asNumber(update["step_index"]);
          const stepType = asString(update["step_type"]);
          const state = asString(update["state"]) ?? "";
          if (isRecord(update["usage"])) {
            turnInputTokens += asNumber(update["usage"]["input_tokens"]);
            turnOutputTokens += asNumber(update["usage"]["output_tokens"]);
          }

          const claimsTool = update["tool_name"] !== undefined || update["tool_info"] !== undefined;
          if (stepType === null || !NON_TOOL_STEPS.has(stepType) || claimsTool) {
            const toolName = asString(update["tool_name"]) ?? "";
            const infoName = isRecord(update["tool_info"]) ? update["tool_info"]["name"] : undefined;
            // A step that is unclear about its tool counts as unnamed, which the runner's guard refuses.
            const clear = stepType === "tool" && (infoName === undefined || infoName === toolName);
            reportedTool = { name: clear ? toolName : "", state };
            const toolId = `tool_${stepIndex}`;

            if (state === "ACTIVE") {
              const toolInfo = isRecord(update["tool_info"]) ? update["tool_info"] : {};
              const params = isRecord(toolInfo["parameters"]) ? toolInfo["parameters"] : {};
              const kind = kindOf(toolName);
              const path = pathOf(kind, params);
              activeTools.set(stepIndex, { toolId, name: toolName });
              events.push({ type: "tool_start", toolId, name: toolName, kind, ...(path === null ? {} : { path }) });
            } else if (state === "DONE") {
              activeTools.delete(stepIndex);
              events.push({ type: "tool_end", toolId, status: "done" });
            }
          } else if (stepType === "agent_response") {
            const delta = asString(update["text_delta"]);
            const msgId = `msg_${stepIndex}`;

            if (delta !== null && delta !== "") {
              currentMessageText += delta;
              events.push({ type: "text_delta", messageId: msgId, text: delta });
            }

            if (state === "DONE") {
              if (currentMessageText !== "") {
                events.push({ type: "text", messageId: msgId, text: currentMessageText });
                currentMessageText = "";
                textEmitted = true;
              }
            }
          }
          break;
        }

        case "result": {
          const res = isRecord(parsed["result"]) ? parsed["result"] : null;
          if (res === null) break;
          resultReceived = true;
          isFinal = true;
          finished = true;

          const status = asString(res["status"]);
          const responseText = asString(res["response"]) ?? "";
          const denied = deniedActions(res["denied_actions"]);
          if (denied.length > 0) {
            events.push({ type: "notice", level: "warning", message: `Antigravity was not allowed to do this, so its answer may be incomplete: ${oneLine(denied.join(", "), MAX_MESSAGE_CHARS)}.` });
          }

          if (status === "SUCCESS") {
            if (currentMessageText !== "") {
              events.push({ type: "text", messageId: "msg_final", text: currentMessageText });
              currentMessageText = "";
              textEmitted = true;
            } else if (!textEmitted && responseText !== "") {
              events.push({ type: "text", messageId: "msg_final", text: responseText });
              textEmitted = true;
            }
            const usageObj = isRecord(res["usage"]) ? res["usage"] : {};
            const fromSteps = turnInputTokens > 0 || turnOutputTokens > 0;
            const inputTokens = fromSteps ? turnInputTokens : asNumber(usageObj["input_tokens"]);
            const outputTokens = fromSteps ? turnOutputTokens : asNumber(usageObj["output_tokens"]);
            const usage = {
              ...(inputTokens > 0 ? { inputTokens } : {}),
              ...(outputTokens > 0 ? { outputTokens } : {}),
            };
            events.push({ type: "done", reason: "completed", ...(Object.keys(usage).length > 0 ? { usage } : {}) });
          } else {
            const reported = asString(res["error"]) ?? responseText;
            if (isQuotaProblem(reported)) {
              events.push(
                { type: "error", code: "rate_limited", message: oneLine(reported, MAX_MESSAGE_CHARS) },
                { type: "done", reason: "failed" },
              );
            } else if (isAuthProblem(reported)) {
              events.push(
                { type: "error", code: "auth", message: ANTIGRAVITY_LOGIN_HINT },
                { type: "done", reason: "failed" },
              );
            } else {
              events.push(
                { type: "error", code: "provider_error", message: oneLine(reported, MAX_MESSAGE_CHARS) || "Antigravity reported an error." },
                { type: "done", reason: "failed" },
              );
            }
          }
          break;
        }

        default:
          // Ignore checkpoints, user_inputs, system_messages, unknown events
          break;
      }

      return reportedTool !== undefined
        ? { events, tool: reportedTool, fatal: false, final: isFinal }
        : { events, fatal: false, final: isFinal };
    },

    finish({ cancelled, exitCode, stderrTail }) {
      if (finished) return [];
      finished = true;

      const events: AgentEvent[] = [];

      for (const [, dangling] of activeTools) {
        events.push({ type: "tool_end", toolId: dangling.toolId, status: "failed" });
      }
      activeTools.clear();

      if (cancelled) {
        events.push({ type: "done", reason: "cancelled" });
        return events;
      }

      if (stderrTail !== undefined && isQuotaProblem(stderrTail)) {
        events.push(
          { type: "error", code: "rate_limited", message: "Antigravity's usage limit has been reached. Try again after it resets." },
          { type: "done", reason: "failed" },
        );
        return events;
      }

      if (exitCode === 3 || (stderrTail !== undefined && isAuthProblem(stderrTail))) {
        events.push(
          { type: "error", code: "auth", message: ANTIGRAVITY_LOGIN_HINT },
          { type: "done", reason: "failed" },
        );
        return events;
      }

      if (!resultReceived) {
        const detail = stderrTail === undefined ? "" : oneLine(stderrTail, MAX_MESSAGE_CHARS);
        events.push(
          { type: "error", code: "provider_error", message: "Antigravity stopped before it finished its answer.", ...(detail === "" ? {} : { detail }) },
          { type: "done", reason: "failed" },
        );
      }

      return events;
    },
  };
}
