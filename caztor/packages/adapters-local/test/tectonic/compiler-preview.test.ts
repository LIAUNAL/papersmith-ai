import { describe, expect, it, vi } from "vitest";
import { fixture } from "../support/fixtures.ts";
import { drain, finishedOf, harness, request, text } from "../support/compile-harness.ts";

const OK = { stderr: [fixture("bibtex-success.stderr")], exit: { code: 0, signal: null } };

describe("preview promotion", () => {
  it("copies the PDF to a temporary file and renames it, never writing the preview in place", async () => {
    const log: string[] = [];
    const h = harness(
      { "/proj/main.tex": "x" },
      {
        wrapFs: (fs) =>
          new Proxy(fs, {
            get(target, property, receiver) {
              const value = Reflect.get(target, property, receiver) as unknown;
              if (typeof value !== "function") return value;
              return (...args: unknown[]) => {
                if (property === "copyFile" || property === "rename" || property === "writeFile") {
                  log.push(`${String(property)} ${String(args[0])} ${String(args[1] ?? "")}`.trim());
                }
                return (value as (...a: unknown[]) => unknown).apply(target, args);
              };
            },
          }),
      },
    );
    h.child(OK, { ".caztor/build/out/main.pdf": "%PDF new" });
    await drain(h.compiler.compile(request(), new AbortController().signal));

    const promotion = log.filter((entry) => entry.includes("preview.pdf"));
    expect(promotion).toHaveLength(2);
    expect(promotion[0]).toMatch(/^copyFile \/proj\/\.caztor\/build\/out\/main\.pdf \/proj\/\.caztor\/build\/preview\.pdf\.[\w-]+\.tmp$/);
    expect(promotion[1]).toMatch(/^rename \/proj\/\.caztor\/build\/preview\.pdf\.[\w-]+\.tmp \/proj\/\.caztor\/build\/preview\.pdf$/);
    expect(text(await h.compiler.readArtifact("pdf"))).toBe("%PDF new");
  });

  it("bumps the revision on every promoted PDF", async () => {
    const h = harness();
    h.child(OK, { ".caztor/build/out/main.pdf": "%PDF one" });
    h.child(OK, { ".caztor/build/out/main.pdf": "%PDF two" });
    const first = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));
    const second = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));

    expect(first.pdfRev).not.toBeNull();
    expect(second.pdfRev).not.toBeNull();
    expect(Number(second.pdfRev)).toBeGreaterThan(Number(first.pdfRev));
    expect(text(await h.compiler.readArtifact("pdf"))).toBe("%PDF two");
  });

  it("keeps the last good preview when the next run produces no PDF", async () => {
    const h = harness();
    h.child(OK, { ".caztor/build/out/main.pdf": "%PDF good" });
    h.child({ stderr: ["error: main.tex:1: broken\n"], exit: { code: 1, signal: null } });
    await drain(h.compiler.compile(request(), new AbortController().signal));
    const failed = finishedOf(await drain(h.compiler.compile(request({ stopOnFirstError: true }), new AbortController().signal)));

    expect(failed.status).toBe("failed");
    expect(failed.pdfRev).toBeNull();
    expect(text(await h.compiler.readArtifact("pdf"))).toBe("%PDF good");
  });

  it("returns null for an artifact that was never produced", async () => {
    const h = harness();
    expect(await h.compiler.readArtifact("pdf")).toBeNull();
    expect(await h.compiler.readArtifact("log")).toBeNull();
  });

  it("does not promote the output of a cancelled run", async () => {
    const h = harness();
    h.child(OK, { ".caztor/build/out/main.pdf": "%PDF good" });
    await drain(h.compiler.compile(request(), new AbortController().signal));
    const controller = new AbortController();
    h.child({ stderr: ["note: Running TeX ...\n"] }, { ".caztor/build/out/main.pdf": "%PDF partial" });
    const run = drain(h.compiler.compile(request(), controller.signal));
    await vi.waitFor(() => expect(h.calls).toHaveLength(2));
    controller.abort();
    const result = finishedOf(await run);

    expect(result.status).toBe("cancelled");
    expect(result.pdfRev).toBeNull();
    expect(text(await h.compiler.readArtifact("pdf"))).toBe("%PDF good");
  });
});
