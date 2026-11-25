import { TURN_ERROR_CODES } from "./ports.ts";
import type { AgentEvent, ToolKind, TurnErrorCode } from "./ports.ts";
import type { TurnEvent } from "./ports.ts";

/** One text event is cut to this many characters; a runner cannot push a huge string through the server. */
export const MAX_EVENT_TEXT_CHARS = 200_000;
/** Any other text field of an event (a title, a path, a detail) is cut to this many characters. */
export const MAX_FIELD_CHARS = 4_000;
const TRUNCATED = "\n[truncated by Caztor]";

/** Past these, consecutive text deltas are joined and tool updates are dropped. */
const SOFT_EVENTS = 2_000;
const SOFT_BYTES = 2 * 1024 * 1024;
/** Past these, only the events that matter for the end of the turn are kept. */
const HARD_EVENTS = 10_000;
const HARD_BYTES = 8 * 1024 * 1024;
/** Joined deltas of one message stop growing here. */
const MAX_JOINED_CHARS = 1_048_576;

const TOOL_KINDS: readonly ToolKind[] = ["read", "edit", "write", "search", "command", "other"];
const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const cut = (text: string, limit: number): string => (text.length > limit ? text.slice(0, limit) + TRUNCATED : text);

/**
 * Checks one value from a runner against the event union and returns a clean copy, or null when it is not an event.
 * Unknown fields are dropped, optional fields of the wrong type are dropped, and long strings are truncated.
 */
export function validateAgentEvent(value: unknown): AgentEvent | null {
  if (!isRecord(value)) return null;
  const str = (key: string): string | null => (typeof value[key] === "string" ? (value[key] as string) : null);
  const short = (key: string): string | null => {
    const text = str(key);
    return text === null ? null : cut(text, MAX_FIELD_CHARS);
  };
  const optional = <K extends string>(key: K): { [P in K]?: string } => {
    const text = short(key);
    return text === null ? {} : ({ [key]: text } as { [P in K]?: string });
  };
  switch (value["type"]) {
    case "session": {
      const sessionId = short("sessionId");
      return sessionId === null ? null : { type: "session", sessionId };
    }
    case "text_delta":
    case "text": {
      const messageId = short("messageId");
      const text = str("text");
      if (messageId === null || text === null) return null;
      return { type: value["type"], messageId, text: cut(text, MAX_EVENT_TEXT_CHARS) };
    }
    case "tool_start": {
      const toolId = short("toolId");
      const name = short("name");
      const kind = value["kind"];
      if (toolId === null || name === null || !TOOL_KINDS.includes(kind as ToolKind)) return null;
      return { type: "tool_start", toolId, name, kind: kind as ToolKind, ...optional("path") };
    }
    case "tool_update": {
      const toolId = short("toolId");
      return toolId === null ? null : { type: "tool_update", toolId, ...optional("path"), ...optional("title") };
    }
    case "tool_end": {
      const toolId = short("toolId");
      const status = value["status"];
      if (toolId === null || (status !== "done" && status !== "failed")) return null;
      return { type: "tool_end", toolId, status, ...optional("summary") };
    }
    case "notice": {
      const message = short("message");
      const level = value["level"];
      if (message === null || (level !== "info" && level !== "warning")) return null;
      return { type: "notice", level, message, ...(value["action"] === "replace_definition" ? { action: "replace_definition" as const } : {}) };
    }
    case "error": {
      const message = short("message");
      const code = value["code"];
      if (message === null || !TURN_ERROR_CODES.includes(code as TurnErrorCode)) return null;
      return { type: "error", code: code as TurnErrorCode, message, ...optional("detail") };
    }
    case "done": {
      const reason = value["reason"];
      if (reason !== "completed" && reason !== "cancelled" && reason !== "failed") return null;
      const usage = isRecord(value["usage"]) ? value["usage"] : null;
      const number = (key: string) => (usage !== null && typeof usage[key] === "number" && Number.isFinite(usage[key]) ? { [key]: usage[key] as number } : {});
      const clean = usage === null ? {} : { ...number("inputTokens"), ...number("outputTokens"), ...number("costUsd") };
      return { type: "done", reason, ...(Object.keys(clean).length > 0 ? { usage: clean } : {}) };
    }
    default:
      return null;
  }
}

export interface ReplayEntry {
  /** Counts every event of the turn from 1, also the ones that were joined or dropped from the buffer. */
  seq: number;
  event: TurnEvent;
}

export interface ReplayBuffer {
  /** Stores (or joins, or drops) the event and returns its number. */
  push(event: TurnEvent): number;
  /** The stored entries whose number is greater than `seq`. */
  after(seq: number): ReplayEntry[];
  events(): TurnEvent[];
  hasDone(): boolean;
  count(): number;
  bytes(): number;
}

const ESSENTIAL: ReadonlySet<string> = new Set(["session", "error", "done", "turn_started", "files_changed"]);

const sizeOf = (event: TurnEvent): number => JSON.stringify(event).length;

/**
 * What a client that joins late or reconnects is shown again. Bounded by count and bytes: past the soft limits
 * consecutive deltas of a message are joined into one and tool updates are dropped, past the hard limits only the
 * essential events are kept. The turn itself and the live stream are not affected.
 */
export function createReplayBuffer(): ReplayBuffer {
  const entries: ReplayEntry[] = [];
  const sizes: number[] = [];
  let seq = 0;
  let total = 0;
  let done = false;

  return {
    push(event) {
      seq += 1;
      if (event.type === "done") done = true;
      const size = sizeOf(event);
      const soft = entries.length >= SOFT_EVENTS || total >= SOFT_BYTES;
      const hard = entries.length >= HARD_EVENTS || total >= HARD_BYTES;
      if (hard && !ESSENTIAL.has(event.type)) return seq;
      if (soft) {
        if (event.type === "tool_update") return seq;
        const last = entries.at(-1);
        if (event.type === "text_delta" && last?.event.type === "text_delta" && last.event.messageId === event.messageId) {
          const room = MAX_JOINED_CHARS - last.event.text.length;
          if (room > 0) {
            const added = event.text.length <= room ? event.text : event.text.slice(0, room) + TRUNCATED;
            last.event = { ...last.event, text: last.event.text + added };
            last.seq = seq;
            total += added.length;
            sizes[sizes.length - 1] = (sizes.at(-1) ?? 0) + added.length;
          }
          return seq;
        }
      }
      entries.push({ seq, event });
      sizes.push(size);
      total += size;
      return seq;
    },
    after: (from) => entries.filter((entry) => entry.seq > from),
    events: () => entries.map((entry) => entry.event),
    hasDone: () => done,
    count: () => entries.length,
    bytes: () => total,
  };
}
