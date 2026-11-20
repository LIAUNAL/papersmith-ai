import { describe, expect, it } from "vitest";
import { LineReader, MAX_LINE_CHARS, mergedLines, phaseOfLine } from "../../src/tectonic/line-reader.ts";
import { splitBytes } from "../fakes/fake-spawner.ts";

const bytes = (text: string) => new TextEncoder().encode(text);

describe("LineReader", () => {
  it("returns complete lines and holds the partial one until its newline arrives", () => {
    const reader = new LineReader();
    expect(reader.push(bytes("one\ntw"))).toEqual(["one"]);
    expect(reader.push(bytes("o\nthree"))).toEqual(["two"]);
    expect(reader.flush()).toEqual(["three"]);
  });

  it("decodes a multi-byte character split across chunks", () => {
    const reader = new LineReader();
    const parts = splitBytes("café ✓\n", [4, 8]);
    const lines = parts.flatMap((part) => reader.push(part));
    expect(lines).toEqual(["café ✓"]);
  });

  it("strips a carriage return before the newline", () => {
    expect(new LineReader().push(bytes("a\r\nb\r\n"))).toEqual(["a", "b"]);
  });

  it("cuts a line longer than 4 KB and drops the rest of it, keeping the next line intact", () => {
    const reader = new LineReader();
    const lines = reader.push(bytes(`${"x".repeat(10_000)}\nnext\n`));
    expect(MAX_LINE_CHARS).toBe(4096);
    expect(lines).toHaveLength(2);
    expect(lines[0]!.length).toBe(4096);
    expect(lines[1]).toBe("next");
  });

  it("cuts a long line whose pieces arrive in several chunks", () => {
    const reader = new LineReader();
    const first = reader.push(bytes("y".repeat(3000)));
    const second = reader.push(bytes("y".repeat(3000)));
    const third = reader.push(bytes("\nafter\n"));
    expect([...first, ...second]).toEqual([]);
    expect(third.map((line) => line.length)).toEqual([4096, 5]);
  });
});

describe("phaseOfLine", () => {
  it.each([
    ["note: downloading latex.ltx", "downloading"],
    ["note: Running TeX ...", "typesetting"],
    ['note: Rerunning TeX because "main.aux" changed ...', "typesetting"],
    ["note: Rerunning TeX because bibtex was run ...", "typesetting"],
    ["note: Running BibTeX on main.aux ...", "bibliography"],
    ["note: Running xdvipdfmx ...", "finalizing"],
    ["note: Writing `.caztor/build/out/main.pdf` (4.4 KiB)", "finalizing"],
  ])("maps %s to %s", (line, phase) => {
    expect(phaseOfLine(line)).toBe(phase);
  });

  it("ignores notes it does not know and lines that are not notes", () => {
    expect(phaseOfLine('note: "version 2" Tectonic command-line interface activated')).toBeNull();
    expect(phaseOfLine('note: generating format "latex"')).toBeNull();
    expect(phaseOfLine("warning: downloading is slow")).toBeNull();
    expect(phaseOfLine("error: note: Running TeX")).toBeNull();
  });
});

async function* stream(...chunks: string[]): AsyncGenerator<Uint8Array> {
  for (const chunk of chunks) {
    await Promise.resolve();
    yield bytes(chunk);
  }
}

describe("mergedLines", () => {
  it("yields the lines of every stream and the unterminated last line of each", async () => {
    const seen: string[] = [];
    for await (const line of mergedLines([stream("note: a\nnote: ", "b\n"), stream("error: x\nwarning: y")])) seen.push(line);
    expect(seen.sort()).toEqual(["error: x", "note: a", "note: b", "warning: y"]);
  });

  it("keeps the order of lines within one stream", async () => {
    const seen: string[] = [];
    for await (const line of mergedLines([stream("1\n2\n", "3\n"), stream("a\n", "b\n")])) seen.push(line);
    expect(seen.filter((line) => /\d/.test(line))).toEqual(["1", "2", "3"]);
    expect(seen.filter((line) => /[a-z]/.test(line))).toEqual(["a", "b"]);
  });

  it("finishes when every stream has ended, and survives a stream that throws", async () => {
    async function* broken(): AsyncGenerator<Uint8Array> {
      yield bytes("before\n");
      throw new Error("pipe closed");
    }
    const seen: string[] = [];
    for await (const line of mergedLines([broken(), stream("other\n")])) seen.push(line);
    expect(seen.sort()).toEqual(["before", "other"]);
  });
});
