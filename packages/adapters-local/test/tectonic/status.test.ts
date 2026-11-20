import type { Diagnostic } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { finalizeRun, stderrTail, type RunOutcome } from "../../src/tectonic/diagnostics.ts";
import { fixture } from "../support/fixtures.ts";

const typo: Diagnostic = { severity: "error", file: null, line: null, message: "boom", source: "stderr" };
const undefinedRef: Diagnostic = { severity: "warning", file: null, line: null, message: "Reference `x' undefined", source: "log" };

function outcome(overrides: Partial<RunOutcome>): RunOutcome {
  return { killed: null, exitCode: 0, hasPdf: true, diagnostics: [], stderr: "", downloading: false, ...overrides };
}

describe("finalizeRun status", () => {
  it("is success for a PDF with only warnings", () => {
    const run = finalizeRun(outcome({ diagnostics: [undefinedRef] }));
    expect(run.status).toBe("success");
    expect(run.diagnostics).toEqual([undefinedRef]);
  });

  it("is failed-with-errors when the engine exits 0 and writes a PDF but reported an error", () => {
    expect(finalizeRun(outcome({ exitCode: 0, hasPdf: true, diagnostics: [typo] })).status).toBe("failed-with-errors");
  });

  it("is failed when stop-on-error halted the engine without a PDF, and keeps the located error", () => {
    const run = finalizeRun(outcome({ exitCode: 1, hasPdf: false, diagnostics: [typo] }));
    expect(run.status).toBe("failed");
    expect(run.diagnostics).toEqual([typo]);
  });

  it("is cancelled or timed-out whatever the exit code, PDF or errors say", () => {
    expect(finalizeRun(outcome({ killed: "cancelled", exitCode: 0, hasPdf: true })).status).toBe("cancelled");
    expect(finalizeRun(outcome({ killed: "timed-out", exitCode: null, hasPdf: false, diagnostics: [typo] })).status).toBe("timed-out");
  });

  it("adds no synthetic error to a killed run", () => {
    expect(finalizeRun(outcome({ killed: "cancelled", exitCode: null, hasPdf: false })).diagnostics).toEqual([]);
  });
});

describe("finalizeRun synthetic error", () => {
  const stderr = ["note: Running TeX ...", "", "something unexpected", "at the end"].join("\n");

  it("explains a non-zero exit with no parsed error using the stderr tail", () => {
    const run = finalizeRun(outcome({ exitCode: 101, hasPdf: false, stderr }));
    expect(run.status).toBe("failed");
    expect(run.diagnostics).toEqual([
      {
        severity: "error",
        file: null,
        line: null,
        message: "The LaTeX engine failed (exit code 101) without reporting an error.",
        detail: "note: Running TeX ...\nsomething unexpected\nat the end",
        source: "caztor",
      },
    ]);
  });

  it("makes a non-zero exit that still left a PDF failed-with-errors", () => {
    const run = finalizeRun(outcome({ exitCode: 1, hasPdf: true, stderr }));
    expect(run.status).toBe("failed-with-errors");
    expect(run.diagnostics).toHaveLength(1);
  });

  it("explains a clean exit that produced no PDF", () => {
    const run = finalizeRun(outcome({ exitCode: 0, hasPdf: false, diagnostics: [undefinedRef], stderr }));
    expect(run.status).toBe("failed");
    expect(run.diagnostics.map((d) => d.message)).toEqual([
      "Reference `x' undefined",
      "The LaTeX engine finished without producing a PDF.",
    ]);
  });

  it("adds nothing when a located error already explains the failure", () => {
    expect(finalizeRun(outcome({ exitCode: 1, hasPdf: false, diagnostics: [typo], stderr })).diagnostics).toEqual([typo]);
  });
});

describe("stderrTail", () => {
  it("keeps the last non-empty lines and bounds the length", () => {
    const text = Array.from({ length: 40 }, (_, i) => `line ${i + 1}`).join("\n\n");
    expect(stderrTail(text, 3)).toBe("line 38\nline 39\nline 40");
    expect(stderrTail("x".repeat(5000), 3).length).toBe(2000);
  });
});

describe("finalizeRun offline first run", () => {
  const readable = "Could not download LaTeX support files. The first compile needs a network connection.";

  it("explains the recorded offline failure and keeps the raw text as detail", () => {
    const stderr = fixture("offline-first-run.stderr");
    const run = finalizeRun(outcome({ exitCode: 101, hasPdf: false, stderr }));
    expect(run.status).toBe("failed");
    expect(run.diagnostics).toHaveLength(1);
    expect(run.diagnostics[0]).toMatchObject({ severity: "error", file: null, line: null, message: readable, source: "caztor" });
    expect(run.diagnostics[0]?.detail).toContain("error sending request for url");
  });

  it("recognises other download failure texts", () => {
    for (const text of ["dns error: failed to lookup address information", "Connection refused (os error 111)", "operation timed out"]) {
      const run = finalizeRun(outcome({ exitCode: 1, hasPdf: false, stderr: `error: failed to fetch: ${text}` }));
      expect(run.diagnostics[0]?.message, text).toBe(readable);
    }
  });

  it("attaches the hint to a failure with no located error that happened while downloading", () => {
    const run = finalizeRun(outcome({ exitCode: 1, hasPdf: false, downloading: true, stderr: "error: something unrecognised" }));
    expect(run.diagnostics.map((d) => d.message)).toEqual([readable]);
  });

  it("keeps the ordinary synthetic error when nothing points at the network", () => {
    const run = finalizeRun(outcome({ exitCode: 1, hasPdf: false, downloading: false, stderr: "error: something unrecognised" }));
    expect(run.diagnostics[0]?.message).toBe("The LaTeX engine failed (exit code 1) without reporting an error.");
  });

  it("does not blame the network for a located TeX error, even after downloads", () => {
    const run = finalizeRun(
      outcome({ exitCode: 1, hasPdf: false, downloading: true, diagnostics: [typo], stderr: "error sending request" }),
    );
    expect(run.diagnostics).toEqual([typo]);
  });
});
