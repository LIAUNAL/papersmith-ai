import type { CompileResult } from "../api/types.ts";

/** Which version of the PDF the pane shows, which one it should show, and whether what it shows is stale. */
export interface PreviewState {
  /** The revision on screen; null before the first PDF is shown. */
  shownRev: string | null;
  /** The revision that should be on screen; differs from `shownRev` while a load is due or running. */
  wantedRev: string | null;
  /** The last compile did not produce a PDF, so the one on screen predates the source. */
  outOfDate: boolean;
  /** Why the wanted revision could not be shown. */
  error: string | null;
}

export type PreviewAction =
  | { type: "known"; available: boolean }
  | { type: "finished"; result: CompileResult }
  | { type: "loaded"; rev: string }
  | { type: "load-failed"; rev: string; message: string };

export const INITIAL_PREVIEW_STATE: PreviewState = { shownRev: null, wantedRev: null, outOfDate: false, error: null };

/** The revision asked for when a preview exists but this session has not seen its number (after a server restart). */
export const CURRENT_REV = "current";

export function previewReducer(state: PreviewState, action: PreviewAction): PreviewState {
  switch (action.type) {
    case "known":
      return action.available && state.wantedRev === null ? { ...state, wantedRev: CURRENT_REV } : state;
    case "finished": {
      if (action.result.pdfRev !== null) return { ...state, wantedRev: action.result.pdfRev, outOfDate: false, error: null };
      // No new PDF: whatever is on screen (or about to be) no longer matches the source.
      return state.wantedRev === null ? state : { ...state, outOfDate: true };
    }
    case "loaded":
      return action.rev === state.wantedRev ? { ...state, shownRev: action.rev, error: null } : state;
    case "load-failed":
      return action.rev === state.wantedRev ? { ...state, wantedRev: state.shownRev, error: action.message } : state;
  }
}

/** A revision is wanted that is not on screen yet. */
export function needsLoad(state: PreviewState): boolean {
  return state.wantedRev !== null && state.wantedRev !== state.shownRev;
}
