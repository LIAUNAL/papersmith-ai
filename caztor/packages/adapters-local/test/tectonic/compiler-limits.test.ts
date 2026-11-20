import { describe, expect, it, vi } from "vitest";
import type { CompileEvent } from "@caztor/core";
import { drain, finishedOf, harness, request } from "../support/compile-harness.ts";

const HUNG = { stderr: ["note: Running TeX ...\n"] };

/** Starts a compile and waits until the engine has been spawned and the time limit is armed. */
async function startRun(h: ReturnType<typeof harness>, signal = new AbortController().signal) {
  const run = drain(h.compiler.compile(request(), signal));
  await vi.waitFor(() => {
    expect(h.calls).toHaveLength(1);
    expect(h.clock.pendingTimers).toBeGreaterThan(0);
  });
  return { run };
}

describe("time limit", () => {
  it("terminates a run that passes 180 seconds without downloading, and reports timed-out", async () => {
    const h = harness();
    h.child(HUNG);
    const { run } = await startRun(h);

    h.clock.advance(179_999);
    expect(h.fake.signals).toEqual([]);
    h.clock.advance(1);
    expect(h.fake.signals).toEqual(["SIGTERM"]);

    const result = finishedOf(await run);
    expect(result.status).toBe("timed-out");
    expect(result.pdfRev).toBeNull();
    expect(h.clock.pendingTimers).toBe(0);
  });

  it("extends the limit to 600 seconds once support files are downloading", async () => {
    const h = harness();
    h.child({ stderr: ["note: downloading latex.ltx\n"] });
    const { run } = await startRun(h);

    h.clock.advance(180_000);
    expect(h.fake.signals).toEqual([]);
    h.clock.advance(419_999);
    expect(h.fake.signals).toEqual([]);
    h.clock.advance(1);
    expect(h.fake.signals).toEqual(["SIGTERM"]);
    expect(finishedOf(await run).status).toBe("timed-out");
  });

  it("counts the extended limit from the start of the run, not from the first download note", async () => {
    const h = harness();
    // Output arrives after 170 s of silence: the download note comes late.
    h.child({});
    const events: CompileEvent[] = [];
    const run = (async () => {
      for await (const event of h.compiler.compile(request(), new AbortController().signal)) events.push(event);
      return events;
    })();
    await vi.waitFor(() => expect(h.clock.pendingTimers).toBeGreaterThan(0));
    h.clock.advance(170_000);
    h.fake.pushStderr("note: downloading late.sty\n");
    await vi.waitFor(() => expect(events.some((event) => event.type === "phase")).toBe(true));
    h.clock.advance(429_999);
    expect(h.fake.signals).toEqual([]);
    h.clock.advance(1);
    expect(h.fake.signals).toEqual(["SIGTERM"]);
    expect(finishedOf(await run).status).toBe("timed-out");
  });

  it("escalates to SIGKILL 2 seconds after a SIGTERM the engine ignores", async () => {
    const h = harness();
    h.child({ ...HUNG, ignores: ["SIGTERM"] });
    const { run } = await startRun(h);

    h.clock.advance(180_000);
    expect(h.fake.signals).toEqual(["SIGTERM"]);
    h.clock.advance(1_999);
    expect(h.fake.signals).toEqual(["SIGTERM"]);
    h.clock.advance(1);
    expect(h.fake.signals).toEqual(["SIGTERM", "SIGKILL"]);
    expect(finishedOf(await run).status).toBe("timed-out");
    expect(h.clock.pendingTimers).toBe(0);
  });

  it("leaves no timer behind after a run that ends on its own", async () => {
    const h = harness();
    h.child({ exit: { code: 1, signal: null } });
    await drain(h.compiler.compile(request(), new AbortController().signal));
    expect(h.clock.pendingTimers).toBe(0);
    expect(h.fake.signals).toEqual([]);
  });
});

describe("cancel", () => {
  it("aborting the signal terminates the process group and reports cancelled", async () => {
    const h = harness();
    h.child(HUNG);
    const controller = new AbortController();
    const { run } = await startRun(h, controller.signal);

    controller.abort();
    expect(h.fake.signals).toEqual(["SIGTERM"]);
    expect(finishedOf(await run).status).toBe("cancelled");
    expect(h.clock.pendingTimers).toBe(0);
  });

  it("kills a process that ignores the cancel after 2 seconds", async () => {
    const h = harness();
    h.child({ ...HUNG, ignores: ["SIGTERM"] });
    const controller = new AbortController();
    const { run } = await startRun(h, controller.signal);

    controller.abort();
    h.clock.advance(2_000);
    expect(h.fake.signals).toEqual(["SIGTERM", "SIGKILL"]);
    expect(finishedOf(await run).status).toBe("cancelled");
  });

  it("reports cancelled without spawning when the signal is already aborted", async () => {
    const h = harness();
    const controller = new AbortController();
    controller.abort();
    const result = finishedOf(await drain(h.compiler.compile(request(), controller.signal)));
    expect(result.status).toBe("cancelled");
    expect(h.calls).toEqual([]);
  });

  it("a run that is both cancelled and past its limit keeps the first cause", async () => {
    const h = harness();
    h.child({ ...HUNG, ignores: ["SIGTERM"] });
    const controller = new AbortController();
    const { run } = await startRun(h, controller.signal);
    controller.abort();
    h.clock.advance(180_000);
    expect(finishedOf(await run).status).toBe("cancelled");
  });
});

describe("output caps", () => {
  it("cuts a line over 4 KB before it reaches a diagnostic", async () => {
    const h = harness();
    h.child({ stderr: [`error: main.tex:1: ${"x".repeat(10_000)}\n`], exit: { code: 1, signal: null } });
    const result = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));
    const error = result.diagnostics.find((d) => d.severity === "error");
    expect(error?.line).toBe(1);
    expect(error?.message.length).toBeLessThanOrEqual(4096);
    expect(error?.message.length).toBeGreaterThan(4000);
  });

  it("keeps at most 2 MB of stderr and says so, ignoring errors printed after that", async () => {
    const h = harness();
    const noise = `note: ${"n".repeat(1018)}\n`;
    const lines = Array.from({ length: 3000 }, () => noise).join("");
    h.child({ stderr: ["error: main.tex:1: early\n", lines, "error: main.tex:9: too late\n"], exit: { code: 1, signal: null } });
    const result = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));

    expect(result.diagnostics.filter((d) => d.severity === "error").map((d) => d.line)).toEqual([1]);
    expect(result.diagnostics).toContainEqual(
      expect.objectContaining({ severity: "warning", source: "caztor", message: expect.stringMatching(/2 MB/) as unknown }),
    );
  });

  it("does not warn about the cap for ordinary output", async () => {
    const h = harness();
    h.child({ stderr: ["note: Running TeX ...\n"], exit: { code: 1, signal: null } });
    const result = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));
    expect(result.diagnostics.some((d) => /2 MB/.test(d.message))).toBe(false);
  });
});

describe("available", () => {
  it("runs tectonic --version with the allowlisted environment and reads the version", async () => {
    const h = harness();
    h.child({ stdout: ["Tectonic 0.17.0\n"], exit: { code: 0, signal: null } });
    expect(await h.compiler.available()).toEqual({ ok: true, version: "0.17.0" });
    expect(h.calls[0]).toMatchObject({ file: "tectonic", args: ["--version"], cwd: "/proj" });
    expect(h.calls[0]?.env).not.toHaveProperty("SECRET_TOKEN");
  });

  it("is unavailable when the binary is missing or fails", async () => {
    const missing = harness();
    missing.child({ spawnError: "ENOENT" });
    expect(await missing.compiler.available()).toEqual({ ok: false, reason: "Tectonic was not found on the PATH." });

    const broken = harness();
    broken.child({ stderr: ["error: cannot open the cache\n"], exit: { code: 2, signal: null } });
    expect(await broken.compiler.available()).toEqual({
      ok: false,
      reason: "Tectonic was found but failed to run (exit code 2): error: cannot open the cache",
    });
  });

  it("is unavailable, with the reason, when the version output is not recognised", async () => {
    const h = harness();
    h.child({ stdout: ["something else entirely\n"], exit: { code: 0, signal: null } });
    expect(await h.compiler.available()).toEqual({
      ok: false,
      reason: 'Tectonic answered --version with output that was not recognised: "something else entirely"',
    });
  });

  it("gives up on a probe that hangs for 5 seconds", async () => {
    const h = harness();
    h.child({});
    const probe = h.compiler.available();
    await vi.waitFor(() => expect(h.clock.pendingTimers).toBeGreaterThan(0));
    h.clock.advance(5_000);
    expect(await probe).toEqual({ ok: false, reason: "Tectonic did not answer --version within 5 seconds." });
    expect(h.fake.signals).toEqual(["SIGTERM"]);
  });
});
