import type { CompileEvent, CompileRequest, CompileResult, CompilerPort, Diagnostic } from "./ports.ts";

/** What listeners receive: the compile events, each named by the id the request was given. */
export type CoordinatorEvent =
  | { type: "started"; compileId: string }
  | { type: "phase"; compileId: string; phase: Extract<CompileEvent, { type: "phase" }>["phase"] }
  /** A request waits for the running compile; a newer one replaces it. */
  | { type: "queued"; compileId: string }
  /** The queued request was discarded by a cancel. */
  | { type: "dequeued"; compileId: string }
  | { type: "finished"; compileId: string; result: CompileResult };

export interface CompileStatus {
  running: { compileId: string } | null;
  queued: { compileId: string } | null;
  last: { compileId: string; result: CompileResult } | null;
}

export interface CompileCoordinator {
  /**
   * Starts the compile, or when one is running stores it as the single follow-up (a newer request replaces the
   * queued one). The id is known at once, so the caller can answer before the run starts.
   */
  request(req: CompileRequest): { compileId: string; queued: boolean };
  /** Stops the running compile and discards the queued follow-up. */
  cancel(): { cancelled: boolean };
  status(): CompileStatus;
  subscribe(listener: (event: CoordinatorEvent) => void): () => void;
  /** Resolves when nothing runs and nothing is queued. */
  idle(): Promise<void>;
  /** Cancels everything and resolves once the running compile has ended. */
  shutdown(): Promise<void>;
}

export interface CompileCoordinatorOptions {
  compiler: CompilerPort;
  newId?: () => string;
}

interface Entry {
  compileId: string;
  req: CompileRequest;
}

function endedWith(status: CompileResult["status"], diagnostics: Diagnostic[]): CompileResult {
  return { status, pdfRev: null, diagnostics, durationMs: 0, logAvailable: false };
}

function failure(message: string, detail?: string): CompileResult {
  const diagnostic: Diagnostic = {
    severity: "error",
    file: null,
    line: null,
    message,
    ...(detail === undefined ? {} : { detail }),
    source: "caztor",
  };
  return endedWith("failed", [diagnostic]);
}

/** One compile at a time per project, with a single queued follow-up and cancel. Pure: time and the engine are behind the port. */
export function createCompileCoordinator(options: CompileCoordinatorOptions): CompileCoordinator {
  const { compiler } = options;
  let counter = 0;
  const newId = options.newId ?? (() => `compile-${(counter += 1)}`);

  let running: Entry | null = null;
  let queued: Entry | null = null;
  let last: CompileStatus["last"] = null;
  let controller: AbortController | null = null;
  let current: Promise<void> = Promise.resolve();
  const listeners = new Set<(event: CoordinatorEvent) => void>();

  const publish = (event: CoordinatorEvent): void => {
    for (const listener of [...listeners]) {
      try {
        listener(event);
      } catch {
        // A failing listener must not stop the run or the other listeners.
      }
    }
  };

  const finish = (entry: Entry, result: CompileResult): void => {
    last = { compileId: entry.compileId, result };
    publish({ type: "finished", compileId: entry.compileId, result });
  };

  async function run(entry: Entry, abort: AbortController): Promise<void> {
    publish({ type: "started", compileId: entry.compileId });
    let finished = false;
    try {
      for await (const event of compiler.compile(entry.req, abort.signal)) {
        if (event.type === "phase") publish({ type: "phase", compileId: entry.compileId, phase: event.phase });
        else if (event.type === "finished" && !finished) {
          finished = true;
          finish(entry, event.result);
        }
      }
    } catch (error) {
      if (!finished) {
        finished = true;
        finish(entry, failure("The compile stopped unexpectedly.", error instanceof Error ? error.message : String(error)));
      }
    }
    if (!finished) {
      finish(entry, abort.signal.aborted ? endedWith("cancelled", []) : failure("The compile ended without a result."));
    }
  }

  function start(entry: Entry): void {
    running = entry;
    controller = new AbortController();
    current = run(entry, controller).then(() => {
      running = null;
      controller = null;
      const next = queued;
      queued = null;
      if (next !== null) start(next);
    });
  }

  return {
    request(req) {
      const entry: Entry = { compileId: newId(), req };
      if (running === null) {
        start(entry);
        return { compileId: entry.compileId, queued: false };
      }
      queued = entry;
      publish({ type: "queued", compileId: entry.compileId });
      return { compileId: entry.compileId, queued: true };
    },
    cancel() {
      const discarded = queued;
      queued = null;
      if (discarded !== null && running !== null) publish({ type: "dequeued", compileId: discarded.compileId });
      if (running === null || controller === null) return { cancelled: false };
      controller.abort();
      return { cancelled: true };
    },
    status: () => ({
      running: running === null ? null : { compileId: running.compileId },
      queued: queued === null ? null : { compileId: queued.compileId },
      last,
    }),
    subscribe(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    async idle() {
      while (running !== null || queued !== null) await current;
    },
    async shutdown() {
      this.cancel();
      await this.idle();
    },
  };
}
