import type { CompileResult, CompileStatusReport, ServerEvent } from "../api/types.ts";

export type CompilePhase = "downloading" | "typesetting" | "bibliography" | "finalizing";

/** What the UI knows about compiling: pure data, changed only by `compileReducer`. */
export interface CompileState {
  running: boolean;
  runningId: string | null;
  /** The phase the running compile reported last; null before the first report. */
  phase: CompilePhase | null;
  /** A follow-up request waits for the running compile. */
  queued: boolean;
  last: { compileId: string; result: CompileResult } | null;
  /** A preview PDF exists on the server. */
  pdfAvailable: boolean;
  /** A readable message when a request failed (engine missing, no main file, unreachable server). */
  problem: string | null;
}

export type CompileAction =
  | { type: "status"; report: CompileStatusReport }
  | { type: "event"; event: ServerEvent }
  | { type: "accepted"; compileId: string; queued: boolean }
  | { type: "failed"; message: string };

export const INITIAL_COMPILE_STATE: CompileState = {
  running: false,
  runningId: null,
  phase: null,
  queued: false,
  last: null,
  pdfAvailable: false,
  problem: null,
};

const PHASES: readonly string[] = ["downloading", "typesetting", "bibliography", "finalizing"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function onEvent(state: CompileState, event: ServerEvent): CompileState {
  const data = event.data;
  if (!isRecord(data)) return state;
  if (event.event === "compile.started" && typeof data["compileId"] === "string") {
    return { ...state, running: true, runningId: data["compileId"], phase: null, queued: false, problem: null };
  }
  // Another client queued a follow-up, or a cancel dropped it: every open client shows the same state.
  if (event.event === "compile.queued" && typeof data["compileId"] === "string") return { ...state, queued: true };
  if (event.event === "compile.dequeued" && typeof data["compileId"] === "string") return { ...state, queued: false };
  if (event.event === "compile.phase" && typeof data["phase"] === "string" && PHASES.includes(data["phase"])) {
    return { ...state, phase: data["phase"] as CompilePhase };
  }
  if (event.event === "compile.finished" && typeof data["compileId"] === "string" && isRecord(data["result"])) {
    const result = data["result"] as unknown as CompileResult;
    return {
      ...state,
      running: false,
      runningId: null,
      phase: null,
      // A cancel also discards the queued follow-up; any other end leaves it to start next.
      queued: result.status === "cancelled" ? false : state.queued,
      last: { compileId: data["compileId"], result },
      pdfAvailable: state.pdfAvailable || result.pdfRev !== null,
    };
  }
  return state;
}

export function compileReducer(state: CompileState, action: CompileAction): CompileState {
  switch (action.type) {
    case "status":
      return {
        ...state,
        running: action.report.running !== null,
        runningId: action.report.running?.compileId ?? null,
        queued: action.report.queued !== null,
        last: action.report.last,
        pdfAvailable: action.report.pdfAvailable || action.report.last?.result.pdfRev != null,
      };
    case "event":
      return onEvent(state, action.event);
    case "accepted": {
      // The events of a fast compile can arrive before the answer to the request; they win.
      if (state.last?.compileId === action.compileId || state.runningId === action.compileId) return { ...state, problem: null };
      if (action.queued) return { ...state, queued: state.running, problem: null };
      return { ...state, running: true, runningId: action.compileId, problem: null };
    }
    case "failed":
      return { ...state, problem: action.message };
  }
}

const PHASE_LABELS: Record<CompilePhase, string> = {
  downloading: "Preparing: downloading support files",
  typesetting: "Compiling",
  bibliography: "Running BibTeX",
  finalizing: "Writing the PDF",
};

const RESULT_LABELS: Record<CompileResult["status"], string> = {
  success: "Compiled",
  "failed-with-errors": "Compiled with errors",
  failed: "Compile failed",
  "timed-out": "Compile timed out",
  cancelled: "Compile cancelled",
  "engine-missing": "LaTeX engine not found",
};

/** The one-line status shown in the toolbar. */
export function describeCompile(state: CompileState): string {
  if (state.running) {
    const label = state.phase === null ? "Compiling" : PHASE_LABELS[state.phase];
    return state.queued ? `${label}, another compile is queued` : label;
  }
  return state.last === null ? "Not compiled yet" : RESULT_LABELS[state.last.result.status];
}
