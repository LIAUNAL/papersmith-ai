import type { ChatTurnRecord } from "./chat-history.ts";
import type { ChangedFile, RelPath, ToolKind, TurnErrorCode, TurnEvent } from "./ports.ts";

/** `interrupted`: the turn ended before the tool reported a result. */
export type ToolStatus = "running" | "done" | "failed" | "interrupted";

export type ChatItem =
  | { kind: "text"; id: string; text: string }
  | { kind: "tool"; toolId: string; name: string; toolKind: ToolKind; path?: string; title?: string; status: ToolStatus; summary?: string }
  | { kind: "notice"; level: "info" | "warning"; message: string; action?: "replace_definition" }
  | { kind: "error"; code: TurnErrorCode | "connection_lost"; message: string; detail?: string };

export interface ChatTurn {
  /** Stable across the life of the turn, also before the server has named it. */
  key: string;
  /** Null until the server names the turn. */
  turnId: string | null;
  /** What the user wrote; null for a turn this page did not send and could not read back. */
  prompt: string | null;
  status: "running" | "completed" | "cancelled" | "failed";
  items: ChatItem[];
  /** Null until the list of changed files arrives; an empty list means "No files changed". */
  files: ChangedFile[] | null;
  snapshotPartial: boolean;
  unprotected: RelPath[];
  /** Set when more files are unprotected than `unprotected` names. */
  unprotectedCount?: number;
  /** Names Caztor cannot read: not in `files`, and undo does not cover them. */
  notCovered: RelPath[];
  usage?: { inputTokens?: number; outputTokens?: number; costUsd?: number };
}

export interface ChatNote {
  key: string;
  level: "info" | "warning";
  message: string;
}

export type TimelineEntry = { kind: "turn"; turn: ChatTurn } | ({ kind: "note" } & ChatNote);

export interface ChatState {
  timeline: TimelineEntry[];
  /** The turns of `timeline`, in order. */
  turns: ChatTurn[];
  running: boolean;
  /** Number of the last event of the running turn that was applied; replayed events at or below it are ignored. */
  lastSeq: number;
  undoableTurnId: string | null;
  undoProblem: string | null;
  nextKey: number;
}

export type ChatAction =
  | { type: "history"; turns: ChatTurnRecord[]; undoableTurnId: string | null; undoProblem: string | null; runningTurnId: string | null }
  | { type: "prompt_sent"; prompt: string }
  /** The server answered the send with a refusal instead of a stream. */
  | { type: "prompt_refused" }
  | { type: "event"; event: TurnEvent; seq?: number }
  | { type: "connection_lost"; message: string }
  | { type: "undoable"; turnId: string | null; problem: string | null }
  | { type: "note"; level: "info" | "warning"; message: string }
  /** A new conversation: the visible one is cleared and `message` is the only entry left. */
  | { type: "reset"; message: string };

export const INITIAL_CHAT_STATE: ChatState = {
  timeline: [],
  turns: [],
  running: false,
  lastSeq: 0,
  undoableTurnId: null,
  undoProblem: null,
  nextKey: 1,
};

const newTurn = (key: string, turnId: string | null, prompt: string | null): ChatTurn => ({
  key,
  turnId,
  prompt,
  status: "running",
  items: [],
  files: null,
  snapshotPartial: false,
  unprotected: [],
  notCovered: [],
});

const withTimeline = (state: ChatState, timeline: TimelineEntry[], extra: Partial<ChatState> = {}): ChatState => ({
  ...state,
  ...extra,
  timeline,
  turns: timeline.flatMap((entry) => (entry.kind === "turn" ? [entry.turn] : [])),
});

/** Closes the tools that never reported an end, so a stopped or failed turn leaves no card running. */
const closeTools = (items: ChatItem[]): ChatItem[] =>
  items.map((item) => (item.kind === "tool" && item.status === "running" ? { ...item, status: "interrupted" as const } : item));

/** Applies one event to a turn. Events that do not belong to a known item are ignored. */
function applyToTurn(turn: ChatTurn, event: TurnEvent): ChatTurn {
  switch (event.type) {
    case "turn_started":
      return { ...turn, turnId: event.turnId, snapshotPartial: event.snapshotPartial, unprotected: event.unprotected, ...(event.unprotectedCount === undefined ? {} : { unprotectedCount: event.unprotectedCount }) };
    case "text_delta":
    case "text": {
      const at = turn.items.findIndex((item) => item.kind === "text" && item.id === event.messageId);
      if (at === -1) return { ...turn, items: [...turn.items, { kind: "text", id: event.messageId, text: event.text }] };
      const known = turn.items[at] as Extract<ChatItem, { kind: "text" }>;
      const text = event.type === "text" ? event.text : known.text + event.text;
      return { ...turn, items: turn.items.map((item, index) => (index === at ? { ...known, text } : item)) };
    }
    case "tool_start": {
      const tool: ChatItem = { kind: "tool", toolId: event.toolId, name: event.name, toolKind: event.kind, status: "running", ...(event.path === undefined ? {} : { path: event.path }) };
      return { ...turn, items: [...turn.items, tool] };
    }
    case "tool_update":
      return updateTool(turn, event.toolId, { ...(event.path === undefined ? {} : { path: event.path }), ...(event.title === undefined ? {} : { title: event.title }) });
    case "tool_end":
      return updateTool(turn, event.toolId, { status: event.status, ...(event.summary === undefined ? {} : { summary: event.summary }) });
    case "notice":
      return { ...turn, items: [...turn.items, { kind: "notice", level: event.level, message: event.message, ...(event.action === undefined ? {} : { action: event.action }) }] };
    case "error":
      return { ...turn, items: [...turn.items, { kind: "error", code: event.code, message: event.message, ...(event.detail === undefined ? {} : { detail: event.detail }) }] };
    case "done":
      return { ...turn, status: event.reason, items: closeTools(turn.items), ...(event.usage === undefined ? {} : { usage: event.usage }) };
    case "files_changed":
      return { ...turn, files: event.files, notCovered: event.notCovered ?? [] };
    case "session":
      return turn;
  }
}

function updateTool(turn: ChatTurn, toolId: string, patch: Partial<Extract<ChatItem, { kind: "tool" }>>): ChatTurn {
  if (!turn.items.some((item) => item.kind === "tool" && item.toolId === toolId)) return turn;
  return { ...turn, items: turn.items.map((item) => (item.kind === "tool" && item.toolId === toolId ? { ...item, ...patch } : item)) };
}

/** A stored turn as a finished one. A record with no `done` event was cut off, so it counts as failed. */
export function turnFromRecord(record: ChatTurnRecord): ChatTurn {
  const turn = record.events.reduce(applyToTurn, newTurn(`turn-${record.turnId}`, record.turnId, record.prompt));
  return turn.status === "running" ? { ...turn, status: "failed", items: closeTools(turn.items) } : turn;
}

const lastIndexOfTurn = (timeline: TimelineEntry[], match: (turn: ChatTurn) => boolean): number => {
  for (let i = timeline.length - 1; i >= 0; i -= 1) {
    const entry = timeline[i]!;
    if (entry.kind === "turn" && match(entry.turn)) return i;
  }
  return -1;
};

function replaceTurn(state: ChatState, at: number, turn: ChatTurn, extra: Partial<ChatState> = {}): ChatState {
  return withTimeline(state, state.timeline.map((entry, index) => (index === at ? { kind: "turn", turn } : entry)), extra);
}

function applyEvent(state: ChatState, event: TurnEvent, seq: number | undefined): ChatState {
  if (seq !== undefined && seq <= state.lastSeq) return state;
  const lastSeq = seq ?? state.lastSeq;
  if (event.type === "files_changed") {
    const at = lastIndexOfTurn(state.timeline, (turn) => turn.turnId === event.turnId);
    return at === -1 ? state : replaceTurn(state, at, applyToTurn((state.timeline[at] as { turn: ChatTurn }).turn, event), { lastSeq });
  }
  let at = lastIndexOfTurn(state.timeline, (turn) => turn.status === "running");
  if (event.type === "turn_started" && at !== -1) {
    const open = (state.timeline[at] as { turn: ChatTurn }).turn;
    if (open.turnId !== null && open.turnId !== event.turnId) at = -1;
  }
  if (at === -1) {
    if (event.type !== "turn_started") return state;
    const key = `local-${state.nextKey}`;
    return withTimeline(state, [...state.timeline, { kind: "turn", turn: applyToTurn(newTurn(key, null, null), event) }], { running: true, lastSeq, nextKey: state.nextKey + 1 });
  }
  const turn = applyToTurn((state.timeline[at] as { turn: ChatTurn }).turn, event);
  return replaceTurn(state, at, turn, { lastSeq, running: event.type === "done" ? false : state.running });
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "history": {
      const stored = action.turns.map(turnFromRecord);
      const storedIds = new Set(stored.map((turn) => turn.turnId));
      const live = state.turns.filter((turn) => turn.status === "running" && (turn.turnId === null || !storedIds.has(turn.turnId)));
      const timeline: TimelineEntry[] = [...stored, ...live].map((turn) => ({ kind: "turn", turn }));
      return withTimeline(state, timeline, {
        running: live.length > 0 || action.runningTurnId !== null,
        undoableTurnId: action.undoableTurnId,
        undoProblem: action.undoProblem,
      });
    }
    case "prompt_sent": {
      const turn = newTurn(`local-${state.nextKey}`, null, action.prompt);
      return withTimeline(state, [...state.timeline, { kind: "turn", turn }], { running: true, lastSeq: 0, nextKey: state.nextKey + 1 });
    }
    case "prompt_refused": {
      const at = lastIndexOfTurn(state.timeline, () => true);
      const turn = at === -1 ? undefined : (state.timeline[at] as { turn: ChatTurn }).turn;
      if (turn === undefined || turn.status !== "running" || turn.turnId !== null || turn.items.length > 0) return state;
      return withTimeline(state, state.timeline.filter((_, index) => index !== at), { running: false });
    }
    case "event":
      return applyEvent(state, action.event, action.seq);
    case "connection_lost": {
      const at = lastIndexOfTurn(state.timeline, (turn) => turn.status === "running");
      if (at === -1) return { ...state, running: false };
      const turn = (state.timeline[at] as { turn: ChatTurn }).turn;
      const failed: ChatTurn = { ...turn, status: "failed", items: [...closeTools(turn.items), { kind: "error", code: "connection_lost", message: action.message }] };
      return replaceTurn(state, at, failed, { running: false });
    }
    case "undoable":
      return { ...state, undoableTurnId: action.turnId, undoProblem: action.problem };
    case "note": {
      const note: TimelineEntry = { kind: "note", key: `note-${state.nextKey}`, level: action.level, message: action.message };
      return withTimeline(state, [...state.timeline, note], { nextKey: state.nextKey + 1 });
    }
    case "reset": {
      const note: TimelineEntry = { kind: "note", key: `note-${state.nextKey}`, level: "info", message: action.message };
      return withTimeline({ ...state, running: false, lastSeq: 0, undoableTurnId: null, undoProblem: null }, [note], { nextKey: state.nextKey + 1 });
    }
  }
}
