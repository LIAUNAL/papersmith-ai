import { describe, expect, it } from "vitest";
import { chatReducer, INITIAL_CHAT_STATE, turnFromRecord, type ChatAction, type ChatState, type ChatTurn, type ChatTurnRecord, type TurnEvent } from "../src/index.ts";

const run = (events: Array<TurnEvent | [TurnEvent, number]>, from: ChatState = INITIAL_CHAT_STATE): ChatState =>
  events.reduce<ChatState>((state, entry) => {
    const [event, seq] = Array.isArray(entry) ? entry : [entry, undefined];
    return chatReducer(state, seq === undefined ? { type: "event", event } : { type: "event", event, seq });
  }, from);

const started = (turnId = "t1"): TurnEvent => ({ type: "turn_started", turnId, provider: "claude", snapshotPartial: false, unprotected: [] });
const lastTurn = (state: ChatState): ChatTurn => state.turns.at(-1)!;
const texts = (turn: ChatTurn) => turn.items.flatMap((item) => (item.kind === "text" ? [item.text] : []));

describe("chatReducer: text", () => {
  it("builds a message from deltas and equals their concatenation, however they are cut", () => {
    const whole = "Hello, **world**! Here is \\textbf{LaTeX}.";
    const cutAt = (size: number) => {
      const events: TurnEvent[] = [started()];
      for (let i = 0; i < whole.length; i += size) events.push({ type: "text_delta", messageId: "m1", text: whole.slice(i, i + size) });
      return run(events);
    };
    for (const size of [1, 3, 7, whole.length]) expect(texts(lastTurn(cutAt(size)))).toEqual([whole]);
  });

  it("shows whole parts as separate messages in arrival order", () => {
    const state = run([started(), { type: "text", messageId: "a", text: "First part." }, { type: "text", messageId: "b", text: "Second part." }]);
    expect(texts(lastTurn(state))).toEqual(["First part.", "Second part."]);
  });

  it("lets a whole text replace the deltas of the same message, and keeps other messages untouched", () => {
    const state = run([
      started(),
      { type: "text_delta", messageId: "a", text: "Hel" },
      { type: "text_delta", messageId: "b", text: "other" },
      { type: "text_delta", messageId: "a", text: "lo" },
      { type: "text", messageId: "a", text: "Hello!" },
    ]);
    expect(texts(lastTurn(state))).toEqual(["Hello!", "other"]);
  });

  it("keeps the position of a message when tools come in between its deltas", () => {
    const state = run([
      started(),
      { type: "text_delta", messageId: "a", text: "Before " },
      { type: "tool_start", toolId: "x", name: "Edit", kind: "edit", path: "a.tex" },
      { type: "text_delta", messageId: "a", text: "after" },
    ]);
    expect(lastTurn(state).items.map((item) => item.kind)).toEqual(["text", "tool"]);
    expect(texts(lastTurn(state))).toEqual(["Before after"]);
  });
});

describe("chatReducer: tools", () => {
  it("follows a tool from running to done, with the path and a title from an update", () => {
    const base = run([started(), { type: "tool_start", toolId: "x", name: "Read", kind: "read" }]);
    const tool = (state: ChatState) => lastTurn(state).items.find((item) => item.kind === "tool")!;
    expect(tool(base)).toMatchObject({ status: "running", name: "Read", toolKind: "read" });
    const updated = run([{ type: "tool_update", toolId: "x", path: "main.tex", title: "Reading main.tex" }], base);
    expect(tool(updated)).toMatchObject({ status: "running", path: "main.tex", title: "Reading main.tex" });
    const ended = run([{ type: "tool_end", toolId: "x", status: "done", summary: "12 lines" }], updated);
    expect(tool(ended)).toMatchObject({ status: "done", path: "main.tex", summary: "12 lines" });
  });

  it("marks a failed tool, and ignores updates for a tool it never saw", () => {
    const state = run([started(), { type: "tool_start", toolId: "x", name: "Edit", kind: "edit", path: "a.tex" }, { type: "tool_end", toolId: "x", status: "failed" }, { type: "tool_update", toolId: "ghost", path: "z" }, { type: "tool_end", toolId: "ghost", status: "done" }]);
    expect(lastTurn(state).items).toHaveLength(1);
    expect(lastTurn(state).items[0]).toMatchObject({ kind: "tool", status: "failed" });
  });
});

describe("chatReducer: tools left open", () => {
  const open: TurnEvent[] = [started(), { type: "tool_start", toolId: "a", name: "Edit", kind: "edit", path: "a.tex" }, { type: "tool_start", toolId: "b", name: "Read", kind: "read" }, { type: "tool_end", toolId: "b", status: "done" }];
  const tools = (state: ChatState) => lastTurn(state).items.flatMap((item) => (item.kind === "tool" ? [[item.toolId, item.status]] : []));

  it.each(["completed", "cancelled", "failed"] as const)("closes a tool that never ended as interrupted when the turn ends %s, and leaves finished tools alone", (reason) => {
    expect(tools(run([...open, { type: "done", reason }]))).toEqual([["a", "interrupted"], ["b", "done"]]);
  });

  it("keeps a tool running while the turn runs", () => {
    expect(tools(run(open))).toEqual([["a", "running"], ["b", "done"]]);
  });

  it("closes dangling tools of a stored turn that has no done event, and of a turn whose connection was lost", () => {
    const record: ChatTurnRecord = { turnId: "t1", provider: "claude", prompt: "p", startedAt: 1, events: open };
    expect(turnFromRecord(record).items.map((item) => (item.kind === "tool" ? item.status : ""))).toEqual(["interrupted", "done"]);
    expect(tools(chatReducer(run(open), { type: "connection_lost", message: "x" }))).toEqual([["a", "interrupted"], ["b", "done"]]);
  });
});

describe("chatReducer: turn life", () => {
  it("starts a turn from the sent prompt and takes the id from turn_started", () => {
    const sent = chatReducer(INITIAL_CHAT_STATE, { type: "prompt_sent", prompt: "Fix the title" });
    expect(lastTurn(sent)).toMatchObject({ turnId: null, prompt: "Fix the title", status: "running" });
    expect(sent.running).toBe(true);
    const began = run([started("t9")], sent);
    expect(began.turns).toHaveLength(1);
    expect(lastTurn(began)).toMatchObject({ turnId: "t9", prompt: "Fix the title" });
  });

  it("opens a turn without a prompt when events arrive for a turn this page did not send", () => {
    const state = run([started("t2"), { type: "text", messageId: "m", text: "hi" }]);
    expect(lastTurn(state)).toMatchObject({ turnId: "t2", prompt: null, status: "running" });
  });

  it.each([
    ["completed", "completed"],
    ["cancelled", "cancelled"],
    ["failed", "failed"],
  ] as const)("ends the turn as %s and stops running", (reason, status) => {
    const state = run([started(), { type: "done", reason, usage: { costUsd: 0.01 } }]);
    expect(lastTurn(state)).toMatchObject({ status, usage: { costUsd: 0.01 } });
    expect(state.running).toBe(false);
  });

  it("stores the changed files after the end and the empty list as no files", () => {
    const file = { path: "a.tex", change: "modified", beforeHash: null, afterHash: null, undoable: true, mixed: false } as const;
    const withFiles = run([started(), { type: "done", reason: "completed" }, { type: "files_changed", turnId: "t1", files: [file as never] }]);
    expect(lastTurn(withFiles).files).toHaveLength(1);
    const none = run([started(), { type: "done", reason: "completed" }, { type: "files_changed", turnId: "t1", files: [] }]);
    expect(lastTurn(none).files).toEqual([]);
    expect(lastTurn(run([started()])).files).toBeNull();
  });

  it("records errors, notices and the partial snapshot warning in the turn", () => {
    const state = run([
      { type: "turn_started", turnId: "t1", provider: "claude", snapshotPartial: true, unprotected: ["big.pdf" as never] },
      { type: "notice", level: "info", message: "New conversation started." },
      { type: "error", code: "auth", message: "Sign in again.", detail: "401" },
    ]);
    expect(lastTurn(state).unprotected).toEqual(["big.pdf"]);
    expect(lastTurn(state).items.map((item) => item.kind)).toEqual(["notice", "error"]);
  });

  it("fails a pending prompt that the server refused, and removes nothing else", () => {
    const sent = chatReducer(INITIAL_CHAT_STATE, { type: "prompt_sent", prompt: "x" });
    expect(chatReducer(sent, { type: "prompt_refused" }).turns).toEqual([]);
    expect(chatReducer(sent, { type: "prompt_refused" }).running).toBe(false);
    const finished = run([started(), { type: "done", reason: "completed" }]);
    expect(chatReducer(finished, { type: "prompt_refused" })).toBe(finished);
  });

  it("ends a running turn as failed when the connection could not be restored", () => {
    const state = chatReducer(run([started(), { type: "text_delta", messageId: "m", text: "par" }]), { type: "connection_lost", message: "Lost it." });
    expect(lastTurn(state).status).toBe("failed");
    expect(lastTurn(state).items.at(-1)).toMatchObject({ kind: "error", message: "Lost it." });
    expect(state.running).toBe(false);
  });
});

describe("chatReducer: resubscription", () => {
  it("ignores events at or before the last sequence number it saw, so replays never duplicate text", () => {
    const first = run([[started(), 1], [{ type: "text_delta", messageId: "m", text: "Hel" }, 2], [{ type: "text_delta", messageId: "m", text: "lo" }, 3]]);
    expect(first.lastSeq).toBe(3);
    const replayed = run([[{ type: "text_delta", messageId: "m", text: "lo" }, 3], [{ type: "text_delta", messageId: "m", text: " you" }, 4]], first);
    expect(texts(lastTurn(replayed))).toEqual(["Hello you"]);
    expect(replayed.lastSeq).toBe(4);
  });

  it("restarts the count when a new turn begins", () => {
    const old = run([[started("t1"), 1], [{ type: "done", reason: "completed" }, 2]]);
    const sent = chatReducer(old, { type: "prompt_sent", prompt: "again" });
    expect(sent.lastSeq).toBe(0);
    expect(lastTurn(run([[started("t2"), 1]], sent)).turnId).toBe("t2");
  });
});

describe("chatReducer: history", () => {
  const record = (turnId: string, prompt: string, events: TurnEvent[]): ChatTurnRecord => ({ turnId, provider: "claude", prompt, startedAt: 1, events });

  it("rebuilds finished turns from stored events and marks only the undoable one", () => {
    const turns = [
      record("t1", "one", [started("t1"), { type: "text", messageId: "m", text: "A" }, { type: "done", reason: "completed" }, { type: "files_changed", turnId: "t1", files: [] }]),
      record("t2", "two", [started("t2"), { type: "text", messageId: "m", text: "B" }, { type: "done", reason: "failed" }]),
    ];
    const state = chatReducer(INITIAL_CHAT_STATE, { type: "history", turns, undoableTurnId: "t2", undoProblem: null, runningTurnId: null });
    expect(state.turns.map((turn) => [turn.turnId, turn.prompt, turn.status])).toEqual([["t1", "one", "completed"], ["t2", "two", "failed"]]);
    expect(state.undoableTurnId).toBe("t2");
    expect(state.running).toBe(false);
  });

  it("closes a stored turn that has no done event as failed", () => {
    expect(turnFromRecord(record("t1", "p", [started("t1")])).status).toBe("failed");
  });

  it("keeps a turn that is running now instead of replacing it, and keeps history in front of it", () => {
    const live = run([[started("t5"), 1], [{ type: "text", messageId: "m", text: "live" }, 2]], chatReducer(INITIAL_CHAT_STATE, { type: "prompt_sent", prompt: "now" }));
    const turns = [record("t4", "before", [started("t4"), { type: "done", reason: "completed" }])];
    const merged = chatReducer(live, { type: "history", turns, undoableTurnId: null, undoProblem: "Snapshots are unreadable.", runningTurnId: "t5" });
    expect(merged.turns.map((turn) => turn.turnId)).toEqual(["t4", "t5"]);
    expect(texts(lastTurn(merged))).toEqual(["live"]);
    expect(merged.running).toBe(true);
    expect(merged.undoProblem).toBe("Snapshots are unreadable.");
  });

  it("shows a turn the server says is running, before its events arrive", () => {
    const merged = chatReducer(INITIAL_CHAT_STATE, { type: "history", turns: [], undoableTurnId: null, undoProblem: null, runningTurnId: "t7" });
    expect(merged.running).toBe(true);
    expect(merged.turns).toEqual([]);
    expect(lastTurn(run([[started("t7"), 1]], merged))).toMatchObject({ turnId: "t7", status: "running" });
  });

  it("updates only the undoable turn id on request", () => {
    const state = chatReducer(run([started(), { type: "done", reason: "completed" }]), { type: "undoable", turnId: "t1", problem: null });
    expect(state.undoableTurnId).toBe("t1");
  });
});

describe("chatReducer: notes and reset", () => {
  it("adds a note between turns and clears everything on a new conversation", () => {
    const finished = run([started(), { type: "done", reason: "completed" }]);
    const noted = chatReducer(finished, { type: "note", level: "info", message: "Undid the last turn." } satisfies ChatAction);
    expect(noted.timeline.map((entry) => entry.kind)).toEqual(["turn", "note"]);
    const reset = chatReducer(noted, { type: "reset", message: "New conversation started." });
    expect(reset.turns).toEqual([]);
    expect(reset.timeline).toHaveLength(1);
    expect(reset.timeline[0]).toMatchObject({ kind: "note", message: "New conversation started." });
    expect(reset.undoableTurnId).toBeNull();
  });
});
