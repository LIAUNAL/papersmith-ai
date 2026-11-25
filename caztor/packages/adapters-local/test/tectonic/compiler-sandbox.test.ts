import { describe, expect, it } from "vitest";
import type { SpawnSpec } from "../../src/infra.ts";
import type { Sandbox } from "../../src/sandbox.ts";
import { drain, finishedOf, harness, request } from "../support/compile-harness.ts";

const PDF = "%PDF-1.5 fake";
const wrapped = (spec: SpawnSpec): SpawnSpec => ({ ...spec, file: "/usr/bin/bwrap", args: ["--sandbox-marker", "--", spec.file, ...spec.args] });
const working: Sandbox = { probe: async () => ({ ok: true }), wrapper: async () => wrapped };
const broken: Sandbox = {
  probe: async () => ({ ok: false, reason: "no bwrap" }),
  wrapper: async () => {
    throw new Error("Bubblewrap (bwrap) was not found. Install it to use the sandbox.");
  },
};

describe("sandboxed compile", () => {
  it("runs the engine through the wrapper only when the request asks for the sandbox", async () => {
    const h = harness(undefined, { sandbox: working });
    h.child({ exit: { code: 0, signal: null } }, { ".caztor/build/out/main.pdf": PDF });
    const result = finishedOf(await drain(h.compiler.compile(request({ sandboxed: true }), new AbortController().signal)));
    expect(result.status).toBe("success");
    expect(h.calls[0]).toMatchObject({ file: "/usr/bin/bwrap", args: expect.arrayContaining(["--sandbox-marker", "tectonic"]) });
  });

  it("does not use the sandbox by default, even when one is configured", async () => {
    const h = harness(undefined, { sandbox: working });
    h.child({ exit: { code: 0, signal: null } }, { ".caztor/build/out/main.pdf": PDF });
    await drain(h.compiler.compile(request(), new AbortController().signal));
    expect(h.calls[0]?.file).toBe("tectonic");
  });

  it("reports a sandbox that cannot start, with how to turn it off, and runs nothing", async () => {
    const h = harness(undefined, { sandbox: broken });
    const result = finishedOf(await drain(h.compiler.compile(request({ sandboxed: true }), new AbortController().signal)));
    expect(h.calls).toEqual([]);
    expect(result.status).toBe("failed");
    expect(result.diagnostics[0]).toMatchObject({ severity: "error", source: "caztor" });
    expect(result.diagnostics[0]?.message).toMatch(/sandbox could not start/i);
    expect(result.diagnostics[0]?.message).toMatch(/turn off .*sandboxed compile/i);
    expect(result.diagnostics[0]?.detail).toMatch(/bwrap.*not found/i);
  });

  it("reports a bwrap failure after launch the same way instead of as a LaTeX error", async () => {
    const h = harness(undefined, { sandbox: working });
    h.child({ stderr: ["bwrap: Can't mount proc on /newroot/proc: Operation not permitted\n"], exit: { code: 1, signal: null } });
    const result = finishedOf(await drain(h.compiler.compile(request({ sandboxed: true }), new AbortController().signal)));
    expect(result.status).toBe("failed");
    expect(result.diagnostics).toHaveLength(1);
    expect(result.diagnostics[0]?.message).toMatch(/sandbox could not start/i);
    expect(result.diagnostics[0]?.detail).toContain("Can't mount proc");
  });

  it("refuses when the request asks for a sandbox and none is configured", async () => {
    const h = harness();
    const result = finishedOf(await drain(h.compiler.compile(request({ sandboxed: true }), new AbortController().signal)));
    expect(h.calls).toEqual([]);
    expect(result.diagnostics[0]?.message).toMatch(/sandbox could not start/i);
  });
});
