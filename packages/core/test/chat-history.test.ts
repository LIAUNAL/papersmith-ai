import { describe, expect, it } from "vitest";
import { compactEvents, type TurnEvent } from "../src/index.ts";

describe("compactEvents", () => {
  it("joins the deltas of a message into one text, in place, and keeps the other events in order", () => {
    const events: TurnEvent[] = [
      { type: "session", sessionId: "s1" },
      { type: "text_delta", messageId: "m1", text: "Hel" },
      { type: "tool_start", toolId: "t1", name: "Edit", kind: "edit", path: "a.tex" },
      { type: "text_delta", messageId: "m1", text: "lo " },
      { type: "text_delta", messageId: "m1", text: "world" },
      { type: "tool_end", toolId: "t1", status: "done" },
      { type: "done", reason: "completed" },
    ];
    expect(compactEvents(events)).toEqual([
      { type: "session", sessionId: "s1" },
      { type: "text", messageId: "m1", text: "Hello world" },
      { type: "tool_start", toolId: "t1", name: "Edit", kind: "edit", path: "a.tex" },
      { type: "tool_end", toolId: "t1", status: "done" },
      { type: "done", reason: "completed" },
    ]);
  });

  it("lets a whole text replace the deltas that came before it, and keeps messages apart", () => {
    const events: TurnEvent[] = [
      { type: "text_delta", messageId: "m1", text: "draft" },
      { type: "text", messageId: "m1", text: "final" },
      { type: "text", messageId: "m2", text: "second" },
    ];
    expect(compactEvents(events)).toEqual([
      { type: "text", messageId: "m1", text: "final" },
      { type: "text", messageId: "m2", text: "second" },
    ]);
  });

  it("keeps a turn without any text as it is", () => {
    expect(compactEvents([{ type: "done", reason: "failed" }])).toEqual([{ type: "done", reason: "failed" }]);
  });
});
