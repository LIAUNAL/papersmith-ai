import { describe, expect, it } from "vitest";
import type { FileSystem } from "../../src/infra.ts";
import { KEEP_HEAD_BYTES, KEEP_TAIL_BYTES, PARSE_LIMIT_BYTES, PARSE_TAIL_BYTES, readBoundedLog, readLogForParsing } from "../../src/tectonic/log-bounds.ts";
import { MemoryFileSystem } from "../fakes/memory-fs.ts";

const encode = (text: string) => new TextEncoder().encode(text);
const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);

/** A file system that records how many bytes `readFile` and `readRange` handed out. */
function counting(fs: MemoryFileSystem): { fs: FileSystem; read: () => number } {
  let bytes = 0;
  const wrapped = new Proxy(fs, {
    get(target, name) {
      const member = Reflect.get(target, name) as unknown;
      if (name !== "readFile" && name !== "readRange") return typeof member === "function" ? member.bind(target) : member;
      return async (...args: unknown[]) => {
        const result = await (member as (...a: unknown[]) => Promise<Uint8Array>).apply(target, args);
        bytes += result.length;
        return result;
      };
    },
  }) as FileSystem;
  return { fs: wrapped, read: () => bytes };
}

describe("readBoundedLog", () => {
  it("returns a log that fits as it is, with nothing omitted", async () => {
    const fs = new MemoryFileSystem({ "/a.log": "short log\n" });
    const log = await readBoundedLog(fs, "/a.log");
    expect(log).not.toBeNull();
    expect(decode(log!.bytes)).toBe("short log\n");
    expect(log!.omittedBytes).toBe(0);
  });

  it("keeps the head and the tail of a long log and says how much was left out", async () => {
    const head = "HEAD".repeat(KEEP_HEAD_BYTES / 4);
    const middle = "m".repeat(5 * 1024 * 1024);
    const tail = "TAIL".repeat(KEEP_TAIL_BYTES / 4);
    const fs = new MemoryFileSystem({ "/big.log": head + middle + tail });
    const counted = counting(fs);

    const log = await readBoundedLog(counted.fs, "/big.log");
    const text = decode(log!.bytes);

    expect(log!.omittedBytes).toBe(middle.length);
    expect(text.startsWith(head)).toBe(true);
    expect(text.endsWith(tail)).toBe(true);
    expect(text).toContain(`[Caztor left out ${middle.length} bytes from the middle of this log`);
    expect(text).not.toContain("mmmm");
    // Only the two kept pieces were read, never the whole file.
    expect(counted.read()).toBe(KEEP_HEAD_BYTES + KEEP_TAIL_BYTES);
  });

  it("returns null for a log that does not exist", async () => {
    expect(await readBoundedLog(new MemoryFileSystem(), "/missing.log")).toBeNull();
  });
});

describe("readLogForParsing", () => {
  it("reads a log up to the parse limit completely", async () => {
    const fs = new MemoryFileSystem({ "/a.log": "complete" });
    expect(await readLogForParsing(fs, "/a.log")).toEqual({ text: "complete", skippedBytes: 0 });
  });

  it("reads only the end of a log above the limit and reports how much was skipped", async () => {
    const size = PARSE_LIMIT_BYTES + 1024;
    const body = "a".repeat(size - 6) + "THE END";
    const fs = new MemoryFileSystem({ "/big.log": body });
    const counted = counting(fs);

    const parsed = await readLogForParsing(counted.fs, "/big.log");

    expect(parsed!.skippedBytes).toBe(body.length - PARSE_TAIL_BYTES);
    expect(parsed!.text.length).toBe(PARSE_TAIL_BYTES);
    expect(parsed!.text.endsWith("THE END")).toBe(true);
    expect(counted.read()).toBe(PARSE_TAIL_BYTES);
  });

  it("returns null when there is no log", async () => {
    expect(await readLogForParsing(new MemoryFileSystem(), "/none.log")).toBeNull();
  });
});
