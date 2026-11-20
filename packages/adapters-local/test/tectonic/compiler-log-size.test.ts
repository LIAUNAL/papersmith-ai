import { describe, expect, it } from "vitest";
import type { FileSystem } from "../../src/infra.ts";
import { KEEP_HEAD_BYTES, KEEP_TAIL_BYTES } from "../../src/tectonic/log-bounds.ts";
import { drain, finishedOf, harness, request, ROOT, text } from "../support/compile-harness.ts";

const PDF = "%PDF-1.5 fake";
const WARNING = "LaTeX Warning: Reference `late' on page 1 undefined on input line 7.\n\n";

/** A log far larger than the cap, with one warning at the very end. */
const hugeLog = () => `(./main.tex\n${"filler line of a very noisy package\n".repeat(600_000)}${WARNING})\n`;

describe("a compile log of many megabytes", () => {
  const sizeOfHuge = hugeLog().length;

  it("is not read whole: the diagnostics come from its end and the result says that the rest was skipped", async () => {
    let wholeReads = 0;
    const h = harness(undefined, {
      wrapFs: (fs): FileSystem =>
        new Proxy(fs, {
          get(target, name) {
            const member = Reflect.get(target, name) as unknown;
            if (name === "readFile") {
              return async (path: string) => {
                const bytes = await target.readFile(path);
                if (path.endsWith(".log")) wholeReads += bytes.length;
                return bytes;
              };
            }
            return typeof member === "function" ? member.bind(target) : member;
          },
        }),
    });
    h.child({ exit: { code: 0, signal: null } }, { ".caztor/build/out/main.pdf": PDF, ".caztor/build/out/main.log": hugeLog() });

    const result = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));

    expect(wholeReads).toBe(0);
    expect(result.status).toBe("success");
    expect(result.diagnostics.some((d) => d.source === "log" && d.message.includes("Reference `late'") && d.message.endsWith("on input line 7"))).toBe(true);
    const notice = result.diagnostics.find((d) => d.source === "caztor");
    expect(notice?.severity).toBe("warning");
    expect(notice?.message).toMatch(/log is \d+(\.\d+)? MB.*only the last/i);
  });

  it("keeps a copy and serves a log of bounded size that says it was cut", async () => {
    const h = harness();
    h.child({ exit: { code: 0, signal: null } }, { ".caztor/build/out/main.pdf": PDF, ".caztor/build/out/main.log": hugeLog() });

    const result = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));
    const copied = new TextDecoder().decode(await h.fs.readFile(`${ROOT}/.caztor/build/last-compile.log`));
    const served = text(await h.compiler.readArtifact("log"))!;

    expect(result.logAvailable).toBe(true);
    for (const log of [copied, served!]) {
      expect(log.length).toBeLessThan(KEEP_HEAD_BYTES + KEEP_TAIL_BYTES + 400);
      expect(log.length).toBeGreaterThan(KEEP_HEAD_BYTES + KEEP_TAIL_BYTES);
      expect(log).toContain("[Caztor left out");
      expect(log.endsWith(")\n")).toBe(true);
      expect(log).toContain(WARNING);
    }
    expect(sizeOfHuge).toBeGreaterThan(20 * 1024 * 1024);
  });

  it("serves a log that was left in the build folder by an older version in full size no more", async () => {
    const h = harness();
    await h.fs.mkdir(`${ROOT}/.caztor/build`, { recursive: true });
    await h.fs.writeFile(`${ROOT}/.caztor/build/last-compile.log`, new TextEncoder().encode(hugeLog()));
    const served = text(await h.compiler.readArtifact("log"))!;
    expect(served.length).toBeLessThan(KEEP_HEAD_BYTES + KEEP_TAIL_BYTES + 400);
    expect(served).toContain("[Caztor left out");
  });
});
