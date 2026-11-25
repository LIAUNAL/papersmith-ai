import { describe, expect, it } from "vitest";
import { minimalChange } from "./diff.ts";

describe("minimalChange", () => {
  it("returns null for equal texts", () => {
    expect(minimalChange("same", "same")).toBeNull();
    expect(minimalChange("", "")).toBeNull();
  });

  it("replaces only the differing middle", () => {
    expect(minimalChange("hello brave world", "hello new world")).toEqual({ from: 6, to: 11, insert: "new" });
  });

  it("handles an insertion, a deletion, an append and a prepend", () => {
    expect(minimalChange("ab", "aXb")).toEqual({ from: 1, to: 1, insert: "X" });
    expect(minimalChange("aXb", "ab")).toEqual({ from: 1, to: 2, insert: "" });
    expect(minimalChange("ab", "abc")).toEqual({ from: 2, to: 2, insert: "c" });
    expect(minimalChange("bc", "abc")).toEqual({ from: 0, to: 0, insert: "a" });
  });

  it("replaces everything when nothing is shared", () => {
    expect(minimalChange("abc", "xyz")).toEqual({ from: 0, to: 3, insert: "xyz" });
    expect(minimalChange("", "new")).toEqual({ from: 0, to: 0, insert: "new" });
    expect(minimalChange("old", "")).toEqual({ from: 0, to: 3, insert: "" });
  });

  it("does not count the same character twice when the prefix and the suffix meet", () => {
    expect(minimalChange("aaa", "aa")).toEqual({ from: 2, to: 3, insert: "" });
    expect(minimalChange("aa", "aaa")).toEqual({ from: 2, to: 2, insert: "a" });
  });

  it("never splits a surrogate pair", () => {
    const change = minimalChange("x\u{1F600}y", "x\u{1F601}y");
    expect(change).toEqual({ from: 1, to: 3, insert: "\u{1F601}" });
    const tail = minimalChange("a\u{1F600}", "b\u{1F600}");
    expect(tail).toEqual({ from: 0, to: 1, insert: "b" });
  });

  it("extends the end of the change over a low surrogate shared by two different characters", () => {
    // U+1F600 and U+1FE00 differ only in their high surrogate; the common low surrogate must not be cut off.
    const change = minimalChange("a\u{1F600}b", "a\u{1FE00}b");
    expect(change).toEqual({ from: 1, to: 3, insert: "\u{1FE00}" });
    expect(minimalChange("\u{1F600}", "\u{1FE00}")).toEqual({ from: 0, to: 2, insert: "\u{1FE00}" });
  });

  it("applies to the old text to give the new one", () => {
    const pairs: Array<[string, string]> = [
      ["\\section{A}\ntext", "\\section{B}\ntext"],
      ["line1\nline2\nline3", "line1\nline3"],
      ["one", "one\ntwo"],
    ];
    for (const [before, after] of pairs) {
      const change = minimalChange(before, after);
      expect(change === null ? before : before.slice(0, change.from) + change.insert + before.slice(change.to)).toBe(after);
    }
  });
});

describe("minimalChange round trip", () => {
  /** A small deterministic generator, so a failure can be reproduced from the seed. */
  function random(seed: number) {
    let state = seed;
    return () => {
      state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
      return state / 2 ** 32;
    };
  }
  const alphabet = ["a", "b", "\n", "\\", "\u{1F600}", "\u{1FE00}", "\u00e9"];
  const isHigh = (code: number) => code >= 0xd800 && code <= 0xdbff;
  const isLow = (code: number) => code >= 0xdc00 && code <= 0xdfff;

  it("always gives the new text when applied to the old one, and never cuts inside a surrogate pair", () => {
    const next = random(20260412);
    const text = () => Array.from({ length: Math.floor(next() * 9) }, () => alphabet[Math.floor(next() * alphabet.length)]).join("");
    let changes = 0;
    for (let round = 0; round < 2000; round += 1) {
      const before = text();
      const after = next() < 0.5 ? text() : before.slice(0, Math.floor(next() * before.length)) + text() + before.slice(Math.floor(next() * before.length));
      const change = minimalChange(before, after);
      if (change === null) {
        expect(after).toBe(before);
        continue;
      }
      changes += 1;
      expect(before.slice(0, change.from) + change.insert + before.slice(change.to)).toBe(after);
      for (const cut of [change.from, change.to]) {
        expect(isHigh(before.charCodeAt(cut - 1)) && isLow(before.charCodeAt(cut)), `cut ${cut} of ${JSON.stringify(before)}`).toBe(false);
      }
    }
    expect(changes).toBeGreaterThan(1000);
  });
});
