import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ChatController } from "../chat/controller.ts";
import { useExplained } from "./useExplained.ts";

/** A chat whose latest reply can be replaced, as the hook reads it. */
function chatWith(reply: string) {
  let listeners: Array<() => void> = [];
  let snapshot = { chat: { turns: [{ items: [{ kind: "text", text: reply }] }] } };
  const chat = {
    subscribe(listener: () => void) {
      listeners.push(listener);
      return () => void (listeners = listeners.filter((one) => one !== listener));
    },
    getSnapshot: () => snapshot,
  } as unknown as ChatController;
  const reply_ = (text: string) => {
    snapshot = { chat: { turns: [{ items: [{ kind: "text", text }] }] } };
    listeners.forEach((listener) => listener());
  };
  return { chat, reply: reply_ };
}

const quoted = (...passages: string[]) => passages.map((passage) => `> ${passage}`).join("\n\n");
const A = "the first passage of the paper is long enough";
const B = "the second passage of the paper is long enough";
const C = "the third passage of the paper is long enough";
/** The paper's main file, holding the three passages. */
const PAPER = `\\section{Intro}\n${A}.\n${B}.\n${C}.\n`;

describe("useExplained stepping", () => {
  it("starts before the first passage, steps forward and back, and goes round at both ends", () => {
    const { chat } = chatWith(quoted(A, B, C));
    const { result } = renderHook(() => useExplained(chat, null, PAPER));
    expect(result.current.current).toBeNull();
    expect(result.current.focus).toBeNull();
    act(() => result.current.step(1));
    expect(result.current.current).toBe(0);
    expect(result.current.focus?.passage).toBe(A);
    act(() => result.current.step(-1));
    expect(result.current.current).toBe(2);
    act(() => result.current.step(1));
    expect(result.current.current).toBe(0);
  });

  it("gives every step a new nonce, so the same passage is brought into view again", () => {
    const { chat } = chatWith(quoted(A));
    const { result } = renderHook(() => useExplained(chat, null, PAPER));
    act(() => result.current.step(1));
    const first = result.current.focus?.nonce;
    act(() => result.current.step(1));
    expect(result.current.focus?.passage).toBe(A);
    expect(result.current.focus?.nonce).not.toBe(first);
  });

  it("a step back from the start goes to the last passage", () => {
    const { chat } = chatWith(quoted(A, B, C));
    const { result } = renderHook(() => useExplained(chat, null, PAPER));
    act(() => result.current.step(-1));
    expect(result.current.current).toBe(2);
  });

  it("a new reply starts again before its first passage", () => {
    const { chat, reply } = chatWith(quoted(A, B));
    const { result } = renderHook(() => useExplained(chat, null, PAPER));
    act(() => result.current.step(1));
    act(() => result.current.step(1));
    expect(result.current.current).toBe(1);
    act(() => reply(quoted(C)));
    expect(result.current.current).toBeNull();
    act(() => result.current.step(1));
    expect(result.current.focus?.passage).toBe(C);
  });

  it("does nothing without passages", () => {
    const { chat } = chatWith("no quotes here");
    const { result } = renderHook(() => useExplained(chat, null, PAPER));
    act(() => result.current.step(1));
    expect(result.current.current).toBeNull();
  });
});

describe("useExplained keeps the paper's passages only", () => {
  it("drops a passage quoted from another file, such as the experiments protocol", () => {
    const { chat } = chatWith(quoted(A, "the protocol repeats every run on the default device twice", C));
    const { result } = renderHook(() => useExplained(chat, null, PAPER));
    expect(result.current.passages).toEqual([A, C]);
  });

  it("has none until the paper's text is known", () => {
    const { chat } = chatWith(quoted(A, B));
    const { result } = renderHook(() => useExplained(chat, null, null));
    expect(result.current.passages).toEqual([]);
    act(() => result.current.step(1));
    expect(result.current.focus).toBeNull();
  });
});
