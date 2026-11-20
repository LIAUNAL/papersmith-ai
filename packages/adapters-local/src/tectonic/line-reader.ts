import type { CompileEvent } from "@caztor/core";

export const MAX_LINE_CHARS = 4096;

export type CompilePhase = Extract<CompileEvent, { type: "phase" }>["phase"];

/** Turns output chunks into lines. Characters split across chunks are decoded whole; a line over 4 KB is cut. */
export class LineReader {
  private readonly decoder = new TextDecoder();
  private partial = "";
  private discarding = false;

  push(chunk: Uint8Array): string[] {
    return this.feed(this.decoder.decode(chunk, { stream: true }));
  }

  /** The final line when the stream ended without a trailing newline. */
  flush(): string[] {
    const lines = this.feed(this.decoder.decode());
    if (this.partial !== "") lines.push(this.partial);
    this.partial = "";
    this.discarding = false;
    return lines;
  }

  private feed(text: string): string[] {
    const lines: string[] = [];
    let start = 0;
    for (;;) {
      const newline = text.indexOf("\n", start);
      const end = newline === -1 ? text.length : newline;
      this.append(text.slice(start, end));
      if (newline === -1) break;
      lines.push(this.partial.endsWith("\r") ? this.partial.slice(0, -1) : this.partial);
      this.partial = "";
      this.discarding = false;
      start = newline + 1;
    }
    return lines;
  }

  private append(piece: string): void {
    if (this.discarding) return;
    this.partial += piece;
    if (this.partial.length > MAX_LINE_CHARS) {
      this.partial = this.partial.slice(0, MAX_LINE_CHARS);
      this.discarding = true;
    }
  }
}

/** The compile phase a stderr line announces, or null. Unknown notes are ignored. */
export function phaseOfLine(line: string): CompilePhase | null {
  if (!line.startsWith("note: ")) return null;
  const note = line.slice("note: ".length);
  if (note.startsWith("downloading ")) return "downloading";
  if (note.startsWith("Running TeX") || note.startsWith("Rerunning TeX because")) return "typesetting";
  if (note.startsWith("Running BibTeX on")) return "bibliography";
  if (note.startsWith("Running xdvipdfmx") || note.startsWith("Writing ")) return "finalizing";
  return null;
}

/**
 * The lines of several output streams as one sequence. The order inside a stream is kept; across streams it is the
 * order of arrival. A stream that fails ends there without failing the others.
 */
export async function* mergedLines(streams: readonly AsyncIterable<Uint8Array>[]): AsyncGenerator<string> {
  const queue: string[] = [];
  let active = streams.length;
  let wake: (() => void) | null = null;
  const notify = (): void => {
    wake?.();
    wake = null;
  };

  for (const stream of streams) {
    void (async () => {
      const reader = new LineReader();
      try {
        for await (const chunk of stream) {
          queue.push(...reader.push(chunk));
          notify();
        }
      } catch {
        // A broken stream ends the reading of that stream; the exit result still decides the run.
      }
      queue.push(...reader.flush());
      active -= 1;
      notify();
    })();
  }

  for (;;) {
    const next = queue.shift();
    if (next !== undefined) {
      yield next;
    } else if (active === 0) {
      return;
    } else {
      await new Promise<void>((resolve) => (wake = resolve));
    }
  }
}
