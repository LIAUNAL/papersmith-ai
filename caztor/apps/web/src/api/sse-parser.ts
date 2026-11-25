import type { ServerEvent } from "./types.ts";

export interface SseParser {
  /** Feeds the next piece of the stream, split anywhere. Complete frames are delivered as they are found. */
  feed(chunk: string): void;
}

function readData(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

/**
 * An incremental Server-Sent Events parser. The server sends `id`, `event` and single-line JSON `data`, plus comment
 * lines as heartbeats; the standard rules are followed so other line endings and multi-line data also work.
 */
export function createSseParser(onEvent: (event: ServerEvent) => void): SseParser {
  let buffer = "";
  let id: number | null = null;
  let name = "";
  let data: string[] = [];

  function dispatch(): void {
    if (data.length > 0) onEvent({ id, event: name === "" ? "message" : name, data: readData(data.join("\n")) });
    id = null;
    name = "";
    data = [];
  }

  function line(text: string): void {
    if (text === "") return dispatch();
    if (text.startsWith(":")) return;
    const colon = text.indexOf(":");
    const field = colon === -1 ? text : text.slice(0, colon);
    let value = colon === -1 ? "" : text.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "id") id = /^\d+$/.test(value) ? Number(value) : null;
    else if (field === "event") name = value;
    else if (field === "data") data.push(value);
  }

  // After a CR the next LF belongs to the same CRLF terminator, even when it arrives in the next chunk.
  let skipLf = false;

  return {
    feed(chunk) {
      let rest = chunk;
      if (skipLf && rest.startsWith("\n")) rest = rest.slice(1);
      if (rest.length > 0) skipLf = false;
      buffer += rest;
      for (;;) {
        const end = buffer.search(/\r|\n/);
        if (end === -1) return;
        const crlf = buffer.startsWith("\r\n", end);
        skipLf = buffer[end] === "\r" && !crlf && end + 1 === buffer.length;
        const text = buffer.slice(0, end);
        buffer = buffer.slice(end + (crlf ? 2 : 1));
        line(text);
      }
    },
  };
}
