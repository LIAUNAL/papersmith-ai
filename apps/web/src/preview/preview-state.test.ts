import { describe, expect, it } from "vitest";
import type { CompileResult } from "../api/types.ts";
import { INITIAL_PREVIEW_STATE, needsLoad, previewReducer, type PreviewAction, type PreviewState } from "./preview-state.ts";

const result = (extra: Partial<CompileResult> = {}): CompileResult => ({ status: "success", pdfRev: "5", diagnostics: [], durationMs: 1, logAvailable: true, ...extra });
const run = (state: PreviewState, ...actions: PreviewAction[]) => actions.reduce(previewReducer, state);

describe("previewReducer", () => {
  it("starts empty", () => {
    expect(INITIAL_PREVIEW_STATE).toEqual({ shownRev: null, wantedRev: null, outOfDate: false, error: null });
    expect(needsLoad(INITIAL_PREVIEW_STATE)).toBe(false);
  });

  it("asks to load a preview that exists when the page opens, before any compile of this session", () => {
    const state = run(INITIAL_PREVIEW_STATE, { type: "known", available: true });
    expect(needsLoad(state)).toBe(true);
    expect(state.wantedRev).toBe("current");
    expect(run(INITIAL_PREVIEW_STATE, { type: "known", available: false })).toEqual(INITIAL_PREVIEW_STATE);
  });

  it("loads the new revision after a compile that produced a PDF", () => {
    const state = run(INITIAL_PREVIEW_STATE, { type: "finished", result: result({ pdfRev: "7" }) });
    expect(state).toMatchObject({ wantedRev: "7", outOfDate: false });
    expect(needsLoad(state)).toBe(true);
    const shown = run(state, { type: "loaded", rev: "7" });
    expect(shown).toMatchObject({ shownRev: "7", wantedRev: "7", error: null });
    expect(needsLoad(shown)).toBe(false);
  });

  it("keeps a failed compile's missing PDF from blanking the pane, and marks the old one out of date", () => {
    const shown = run(INITIAL_PREVIEW_STATE, { type: "finished", result: result({ pdfRev: "7" }) }, { type: "loaded", rev: "7" });
    const failed = run(shown, { type: "finished", result: result({ status: "failed", pdfRev: null }) });
    expect(failed).toMatchObject({ shownRev: "7", wantedRev: "7", outOfDate: true });
    expect(needsLoad(failed)).toBe(false);
  });

  it.each(["failed", "timed-out", "cancelled"] as const)("marks the preview out of date after a %s run", (status) => {
    const shown = run(INITIAL_PREVIEW_STATE, { type: "known", available: true }, { type: "loaded", rev: "current" });
    expect(run(shown, { type: "finished", result: result({ status, pdfRev: null }) }).outOfDate).toBe(true);
  });

  it("clears the mark when a later compile produces a PDF", () => {
    const state = run(
      INITIAL_PREVIEW_STATE,
      { type: "finished", result: result({ pdfRev: "7" }) },
      { type: "loaded", rev: "7" },
      { type: "finished", result: result({ status: "failed", pdfRev: null }) },
      { type: "finished", result: result({ pdfRev: "8" }) },
    );
    expect(state).toMatchObject({ outOfDate: false, wantedRev: "8", shownRev: "7" });
    expect(needsLoad(state)).toBe(true);
  });

  it("shows a PDF made with errors as current, not out of date", () => {
    const state = run(INITIAL_PREVIEW_STATE, { type: "finished", result: result({ status: "failed-with-errors", pdfRev: "9" }) });
    expect(state.outOfDate).toBe(false);
  });

  it("has nothing to mark when no PDF ever existed", () => {
    expect(run(INITIAL_PREVIEW_STATE, { type: "finished", result: result({ status: "failed", pdfRev: null }) })).toEqual(INITIAL_PREVIEW_STATE);
  });

  it("ignores a load that finished for a revision that is no longer wanted", () => {
    const state = run(
      INITIAL_PREVIEW_STATE,
      { type: "finished", result: result({ pdfRev: "7" }) },
      { type: "finished", result: result({ pdfRev: "8" }) },
      { type: "loaded", rev: "7" },
    );
    expect(state.shownRev).toBeNull();
    expect(needsLoad(state)).toBe(true);
  });

  it("keeps the shown PDF and reports the problem when loading the new one fails", () => {
    const state = run(
      INITIAL_PREVIEW_STATE,
      { type: "finished", result: result({ pdfRev: "7" }) },
      { type: "loaded", rev: "7" },
      { type: "finished", result: result({ pdfRev: "8" }) },
      { type: "load-failed", rev: "8", message: "The PDF could not be read." },
    );
    expect(state).toMatchObject({ shownRev: "7", error: "The PDF could not be read." });
    expect(needsLoad(state)).toBe(false);
  });

  it("forgets an old error when a new revision is wanted", () => {
    const state = run(
      INITIAL_PREVIEW_STATE,
      { type: "finished", result: result({ pdfRev: "8" }) },
      { type: "load-failed", rev: "8", message: "boom" },
      { type: "finished", result: result({ pdfRev: "9" }) },
    );
    expect(state.error).toBeNull();
    expect(needsLoad(state)).toBe(true);
  });
});
