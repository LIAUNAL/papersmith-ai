import { MAX_LINE_BYTES } from "./claude/mapper.ts";

/**
 * Cuts a byte stream into lines. A multi-byte character split between two chunks is kept whole, and a line that grows
 * past the size limit without an end is dropped up to its next line break, so memory never grows with a bad stream.
 */
export function createLineSplitter(limit = MAX_LINE_BYTES): { push(chunk: Uint8Array): string[]; rest(): string; /** How many lines were dropped for their size so far. */ dropped(): number } {
  const decoder = new TextDecoder();
  let pending = "";
  let dropping = false;
  let droppedLines = 0;
  return {
    dropped: () => droppedLines,
    push(chunk) {
      const lines: string[] = [];
      const parts = decoder.decode(chunk, { stream: true }).split("\n");
      for (const [index, part] of parts.entries()) {
        const last = index === parts.length - 1;
        if (!dropping) pending += part;
        if (pending.length > limit) {
          pending = "";
          dropping = true;
          droppedLines += 1;
        }
        if (last) break;
        if (dropping) dropping = false;
        else lines.push(pending);
        pending = "";
      }
      return lines;
    },
    rest() {
      const line = dropping ? "" : pending + decoder.decode();
      pending = "";
      dropping = false;
      return line;
    },
  };
}
