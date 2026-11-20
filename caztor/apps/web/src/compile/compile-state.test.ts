import { describe, expect, it } from "vitest";
import type { CompileResult, CompileStatusReport, ServerEvent } from "../api/types.ts";
import { compileReducer, INITIAL_COMPILE_STATE, describeCompile, type CompileState } from "./compile-state.ts";

const result = (extra: Partial<CompileResult> = {}): CompileResult => ({
  status: "success",
  pdfRev: "1",
  diagnostics: [],
  durationMs: 10,
  logAvailable: true,
  ...extra,
});
const event = (name: string, data: unknown): ServerEvent => ({ id: 1, event: name, data });
const apply = (state: CompileState, ...actions: Parameters<typeof compileReducer>[1][]) => actions.reduce(compileReducer, state);
const report = (extra: Partial<CompileStatusReport> = {}): CompileStatusReport => ({ running: null, queued: null, last: null, pdfAvailable: false, ...extra });

describe("compileReducer", () => {
  it("starts idle with nothing known", () => {
    expect(INITIAL_COMPILE_STATE).toMatchObject({ running: false, queued: false, phase: null, last: null, pdfAvailable: false, problem: null });
  });

  it("follows started, phase and finished events", () => {
    let state = apply(INITIAL_COMPILE_STATE, { type: "event", event: event("compile.started", { compileId: "c1" }) });
    expect(state).toMatchObject({ running: true, runningId: "c1", phase: null });
    state = apply(state, { type: "event", event: event("compile.phase", { phase: "downloading" }) });
    expect(state.phase).toBe("downloading");
    state = apply(state, { type: "event", event: event("compile.phase", { phase: "typesetting" }) });
    expect(state.phase).toBe("typesetting");
    state = apply(state, { type: "event", event: event("compile.finished", { compileId: "c1", result: result({ pdfRev: "9" }) }) });
    expect(state).toMatchObject({ running: false, runningId: null, phase: null, pdfAvailable: true, last: { compileId: "c1", result: { pdfRev: "9" } } });
  });

  it("keeps pdfAvailable when a later run produces no PDF", () => {
    const withPdf = apply(INITIAL_COMPILE_STATE, { type: "status", report: report({ pdfAvailable: true }) });
    const failed = apply(
      withPdf,
      { type: "event", event: event("compile.started", { compileId: "c2" }) },
      { type: "event", event: event("compile.finished", { compileId: "c2", result: result({ status: "failed", pdfRev: null }) }) },
    );
    expect(failed.pdfAvailable).toBe(true);
    expect(failed.last?.result.status).toBe("failed");
  });

  it("shows a queued follow-up while one runs, and clears it when the follow-up starts", () => {
    let state = apply(INITIAL_COMPILE_STATE, { type: "event", event: event("compile.started", { compileId: "c1" }) });
    state = apply(state, { type: "accepted", compileId: "c2", queued: true });
    expect(state.queued).toBe(true);
    state = apply(state, { type: "event", event: event("compile.finished", { compileId: "c1", result: result() }) }, { type: "event", event: event("compile.started", { compileId: "c2" }) });
    expect(state).toMatchObject({ running: true, queued: false, runningId: "c2" });
  });

  it("shows a follow-up that another client queued, and clears it when the server drops it", () => {
    let state = apply(INITIAL_COMPILE_STATE, { type: "event", event: event("compile.started", { compileId: "c1" }) });
    state = apply(state, { type: "event", event: event("compile.queued", { compileId: "c2" }) });
    expect(state.queued).toBe(true);
    expect(describeCompile(state)).toBe("Compiling, another compile is queued");
    state = apply(state, { type: "event", event: event("compile.dequeued", { compileId: "c2" }) });
    expect(state.queued).toBe(false);
  });

  it("clears the queue when the run is cancelled", () => {
    const state = apply(
      INITIAL_COMPILE_STATE,
      { type: "event", event: event("compile.started", { compileId: "c1" }) },
      { type: "accepted", compileId: "c2", queued: true },
      { type: "event", event: event("compile.finished", { compileId: "c1", result: result({ status: "cancelled", pdfRev: null }) }) },
    );
    expect(state).toMatchObject({ running: false, queued: false });
  });

  it("treats an accepted, not queued request as running until its events say otherwise", () => {
    const state = apply(INITIAL_COMPILE_STATE, { type: "accepted", compileId: "c1", queued: false });
    expect(state).toMatchObject({ running: true, runningId: "c1" });
  });

  it("ignores a late answer for a compile whose events already arrived", () => {
    const state = apply(
      INITIAL_COMPILE_STATE,
      { type: "event", event: event("compile.started", { compileId: "c1" }) },
      { type: "event", event: event("compile.finished", { compileId: "c1", result: result() }) },
      { type: "accepted", compileId: "c1", queued: false },
    );
    expect(state.running).toBe(false);
  });

  it("does not show a queue for a request whose run already started", () => {
    const state = apply(
      INITIAL_COMPILE_STATE,
      { type: "event", event: event("compile.started", { compileId: "c1" }) },
      { type: "accepted", compileId: "c1", queued: true },
    );
    expect(state.queued).toBe(false);
  });

  it("takes running, queued and last from a status report", () => {
    const state = apply(INITIAL_COMPILE_STATE, {
      type: "status",
      report: report({ running: { compileId: "c4" }, queued: { compileId: "c5" }, last: { compileId: "c3", result: result({ status: "failed-with-errors" }) }, pdfAvailable: true }),
    });
    expect(state).toMatchObject({ running: true, runningId: "c4", queued: true, pdfAvailable: true, last: { compileId: "c3" } });
  });

  it("keeps a problem message from a failed request and clears it on the next request", () => {
    let state = apply(INITIAL_COMPILE_STATE, { type: "failed", message: "The LaTeX engine (Tectonic) was not found." });
    expect(state.problem).toBe("The LaTeX engine (Tectonic) was not found.");
    state = apply(state, { type: "accepted", compileId: "c1", queued: false });
    expect(state.problem).toBeNull();
  });

  it("ignores events it does not know and malformed ones", () => {
    const state = apply(
      INITIAL_COMPILE_STATE,
      { type: "event", event: event("file_changed", { path: "a.tex" }) },
      { type: "event", event: event("compile.phase", { phase: 7 }) },
      { type: "event", event: event("compile.finished", null) },
    );
    expect(state).toEqual(INITIAL_COMPILE_STATE);
  });
});

describe("describeCompile", () => {
  const base = INITIAL_COMPILE_STATE;
  it("says what is happening, with the first-run state distinct from compiling", () => {
    expect(describeCompile({ ...base, running: true, phase: null })).toBe("Compiling");
    expect(describeCompile({ ...base, running: true, phase: "typesetting" })).toBe("Compiling");
    expect(describeCompile({ ...base, running: true, phase: "bibliography" })).toBe("Running BibTeX");
    expect(describeCompile({ ...base, running: true, phase: "finalizing" })).toBe("Writing the PDF");
    expect(describeCompile({ ...base, running: true, phase: "downloading" })).toBe("Preparing: downloading support files");
  });

  it("mentions a queued follow-up", () => {
    expect(describeCompile({ ...base, running: true, queued: true, phase: "typesetting" })).toBe("Compiling, another compile is queued");
  });

  it("describes the last result when idle", () => {
    const last = (status: CompileResult["status"], diagnostics: CompileResult["diagnostics"] = []) => ({ compileId: "c", result: result({ status, diagnostics }) });
    expect(describeCompile({ ...base, last: last("success") })).toBe("Compiled");
    expect(describeCompile({ ...base, last: last("failed-with-errors") })).toBe("Compiled with errors");
    expect(describeCompile({ ...base, last: last("failed") })).toBe("Compile failed");
    expect(describeCompile({ ...base, last: last("timed-out") })).toBe("Compile timed out");
    expect(describeCompile({ ...base, last: last("cancelled") })).toBe("Compile cancelled");
    expect(describeCompile(base)).toBe("Not compiled yet");
  });
});
