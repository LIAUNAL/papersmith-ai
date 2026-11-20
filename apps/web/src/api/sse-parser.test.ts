import { describe, expect, it } from "vitest";
import { createSseParser } from "./sse-parser.ts";
import type { ServerEvent } from "./types.ts";

function parse(...chunks: string[]): ServerEvent[] {
  const events: ServerEvent[] = [];
  const parser = createSseParser((event) => events.push(event));
  for (const chunk of chunks) parser.feed(chunk);
  return events;
}

describe("createSseParser", () => {
  it("reads the id, event name and JSON data of a frame", () => {
    expect(parse('id: 7\nevent: file_changed\ndata: {"path":"main.tex","hash":null}\n\n')).toEqual([
      { id: 7, event: "file_changed", data: { path: "main.tex", hash: null } },
    ]);
  });

  it("reads several frames from one chunk, in order", () => {
    const events = parse('id: 1\nevent: a\ndata: 1\n\nid: 2\nevent: b\ndata: 2\n\n');
    expect(events.map((event) => [event.id, event.event, event.data])).toEqual([
      [1, "a", 1],
      [2, "b", 2],
    ]);
  });

  it("joins a frame split anywhere across chunks, even in the middle of a field", () => {
    const text = 'id: 3\nevent: file_changed\ndata: {"path":"a.tex"}\n\n';
    for (let cut = 1; cut < text.length; cut++) {
      expect(parse(text.slice(0, cut), text.slice(cut))).toEqual([{ id: 3, event: "file_changed", data: { path: "a.tex" } }]);
    }
  });

  it("ignores heartbeat comments and emits nothing for them", () => {
    expect(parse(": heartbeat\n\n")).toEqual([]);
    expect(parse(': heartbeat\n\nid: 1\nevent: a\ndata: "x"\n\n')).toEqual([{ id: 1, event: "a", data: "x" }]);
  });

  it("accepts CRLF and CR line endings", () => {
    expect(parse('id: 1\r\nevent: a\r\ndata: true\r\n\r\n')).toEqual([{ id: 1, event: "a", data: true }]);
    expect(parse('id: 1\revent: a\rdata: true\r\r')).toEqual([{ id: 1, event: "a", data: true }]);
  });

  it("does not read the LF of a CRLF split across chunks as an extra blank line", () => {
    expect(parse("id: 1\r", "\nevent: a\r\ndata: 1\r", "\n\r", "\n")).toEqual([{ id: 1, event: "a", data: 1 }]);
  });

  it("uses the default event name and a null id when the frame has none", () => {
    expect(parse("data: 5\n\n")).toEqual([{ id: null, event: "message", data: 5 }]);
  });

  it("joins multiple data lines with a newline before reading the JSON", () => {
    expect(parse('event: a\ndata: [1,\ndata: 2]\n\n')).toEqual([{ id: null, event: "a", data: [1, 2] }]);
  });

  it("keeps the raw text when the data is not JSON, and skips frames without data", () => {
    expect(parse("event: a\ndata: plain words\n\n")).toEqual([{ id: null, event: "a", data: "plain words" }]);
    expect(parse("event: a\nid: 4\n\n")).toEqual([]);
  });

  it("does not emit a frame that has not ended yet", () => {
    expect(parse('event: a\ndata: 1\n')).toEqual([]);
  });

  it("treats a non-numeric id as no id", () => {
    expect(parse("id: nope\nevent: a\ndata: 1\n\n")).toEqual([{ id: null, event: "a", data: 1 }]);
  });
});
