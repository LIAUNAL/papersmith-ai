import { describe, expect, it } from "vitest";
import { compactEvents, createReplayBuffer, MAX_EVENT_TEXT_CHARS, MAX_FIELD_CHARS, validateAgentEvent } from "../src/index.ts";
import type { TurnEvent } from "../src/index.ts";

describe("validating what a runner emits", () => {
  it.each([
    ["session", { type: "session", sessionId: "s1" }],
    ["text_delta", { type: "text_delta", messageId: "m", text: "a" }],
    ["text", { type: "text", messageId: "m", text: "whole" }],
    ["tool_start", { type: "tool_start", toolId: "t", name: "Edit", kind: "edit", path: "a.tex" }],
    ["tool_update", { type: "tool_update", toolId: "t", title: "x" }],
    ["tool_end", { type: "tool_end", toolId: "t", status: "done", summary: "ok" }],
    ["notice", { type: "notice", level: "info", message: "hi", action: "replace_definition" }],
    ["error", { type: "error", code: "auth", message: "log in", detail: "d" }],
    ["done", { type: "done", reason: "completed", usage: { costUsd: 0.1 } }],
  ])("accepts a well-formed %s event unchanged", (_name, event) => {
    expect(validateAgentEvent(event)).toEqual(event);
  });

  it.each([
    ["null", null],
    ["a string", "text_delta"],
    ["an array", []],
    ["an unknown type", { type: "rm_rf" }],
    ["a missing type", { text: "x" }],
    ["a delta without text", { type: "text_delta", messageId: "m" }],
    ["a number as message id", { type: "text_delta", messageId: 1, text: "a" }],
    ["an unknown tool kind", { type: "tool_start", toolId: "t", name: "x", kind: "magic" }],
    ["an unknown error code", { type: "error", code: "boom", message: "x" }],
    ["an unknown done reason", { type: "done", reason: "maybe" }],
    ["a notice level that does not exist", { type: "notice", level: "fatal", message: "x" }],
  ])("refuses %s", (_name, event) => {
    expect(validateAgentEvent(event)).toBeNull();
  });

  it("truncates a huge text with a marker and keeps the rest of the event", () => {
    const big = "x".repeat(MAX_EVENT_TEXT_CHARS * 5);
    const event = validateAgentEvent({ type: "text", messageId: "m", text: big });
    expect(event?.type).toBe("text");
    const text = event?.type === "text" ? event.text : "";
    expect(text.length).toBeLessThan(MAX_EVENT_TEXT_CHARS + 200);
    expect(text.startsWith("xxxx")).toBe(true);
    expect(text).toContain("[truncated by Caztor]");
  });

  it("truncates a long detail, title or path and drops optional fields of the wrong type", () => {
    const event = validateAgentEvent({ type: "error", code: "provider_error", message: "m", detail: "d".repeat(MAX_FIELD_CHARS * 3) });
    expect(event?.type === "error" && event.detail?.length).toBeLessThan(MAX_FIELD_CHARS + 200);
    const update = validateAgentEvent({ type: "tool_update", toolId: "t", path: 42, title: "ok" });
    expect(update).toEqual({ type: "tool_update", toolId: "t", title: "ok" });
  });
});

describe("the replay buffer of a turn", () => {
  const delta = (text: string, messageId = "m"): TurnEvent => ({ type: "text_delta", messageId, text });

  it("numbers every event from 1 and replays what came after a number", () => {
    const buffer = createReplayBuffer();
    expect(buffer.push({ type: "session", sessionId: "s" })).toBe(1);
    expect(buffer.push(delta("a"))).toBe(2);
    expect(buffer.push({ type: "done", reason: "completed" })).toBe(3);
    expect(buffer.after(1).map((entry) => [entry.seq, entry.event.type])).toEqual([[2, "text_delta"], [3, "done"]]);
    expect(buffer.hasDone()).toBe(true);
  });

  it("stays small under a million one-character deltas and loses no text", () => {
    const buffer = createReplayBuffer();
    const total = 1_000_000;
    for (let index = 0; index < total; index += 1) buffer.push(delta("a"));
    buffer.push({ type: "done", reason: "completed" });
    expect(buffer.count()).toBeLessThan(5000);
    expect(buffer.bytes()).toBeLessThan(4 * 1024 * 1024);
    const text = compactEvents(buffer.events()).find((event) => event.type === "text");
    expect(text?.type === "text" && text.text.length).toBe(total);
    expect(buffer.after(0).at(-1)?.seq).toBe(total + 1);
  });

  it("keeps every delta while the turn is small, so a client that resumes sees each one", () => {
    const buffer = createReplayBuffer();
    for (let index = 0; index < 100; index += 1) buffer.push(delta(String(index % 10)));
    expect(buffer.count()).toBe(100);
  });

  it("bounds a flood of tool updates but still keeps the end of the turn", () => {
    const buffer = createReplayBuffer();
    buffer.push({ type: "tool_start", toolId: "t", name: "Edit", kind: "edit" });
    for (let index = 0; index < 300_000; index += 1) buffer.push({ type: "tool_update", toolId: "t", title: `step ${index}` });
    buffer.push({ type: "tool_end", toolId: "t", status: "done" });
    buffer.push({ type: "done", reason: "completed" });
    expect(buffer.count()).toBeLessThan(12_000);
    expect(buffer.events().slice(-1)[0]?.type).toBe("done");
    expect(buffer.events()[0]?.type).toBe("tool_start");
  });

  it("stops growing a coalesced text at a limit and marks it", () => {
    const buffer = createReplayBuffer();
    const chunk = "y".repeat(10_000);
    for (let index = 0; index < 1000; index += 1) buffer.push(delta(chunk));
    const joined = compactEvents(buffer.events()).find((event) => event.type === "text");
    const text = joined?.type === "text" ? joined.text : "";
    expect(text.length).toBeLessThan(4 * 1024 * 1024);
    expect(text).toContain("[truncated by Caztor]");
  });
});
