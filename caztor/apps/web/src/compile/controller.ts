import type { ApiClient, ServerEvent } from "../api/types.ts";
import { compileReducer, INITIAL_COMPILE_STATE, type CompileAction, type CompileState } from "./compile-state.ts";

export interface CompileControllerOptions {
  api: Pick<ApiClient, "startCompile" | "cancelCompile" | "getCompileStatus">;
}

/** Holds the compile state and carries out the user's compile and cancel requests. Read it with `useSyncExternalStore`. */
export class CompileController {
  private state: CompileState = INITIAL_COMPILE_STATE;
  private readonly listeners = new Set<() => void>();
  private readonly api: CompileControllerOptions["api"];

  constructor(options: CompileControllerOptions) {
    this.api = options.api;
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => void this.listeners.delete(listener);
  };

  getSnapshot = (): CompileState => this.state;

  private dispatch(action: CompileAction): void {
    const next = compileReducer(this.state, action);
    if (next === this.state) return;
    this.state = next;
    for (const listener of [...this.listeners]) listener();
  }

  /** Feeds a server event; a reconnect reloads the status because events may have been missed. */
  handleEvent = (event: ServerEvent): void => {
    if (event.event === "stream_resumed") {
      void this.refresh();
      return;
    }
    this.dispatch({ type: "event", event });
  };

  /** Reads the status route: what runs, what is queued, the last result and whether a preview exists. */
  async refresh(): Promise<void> {
    try {
      this.dispatch({ type: "status", report: await this.api.getCompileStatus() });
    } catch {
      // The status is a convenience; the events and the next action keep the state right.
    }
  }

  /** Starts a compile of the main file, or of `main`, or queues the single follow-up when one is running. */
  async start(main?: string): Promise<void> {
    try {
      const accepted = await this.api.startCompile(main);
      this.dispatch({ type: "accepted", ...accepted });
    } catch (error) {
      this.dispatch({ type: "failed", message: error instanceof Error ? error.message : "The compile could not be started." });
    }
  }

  /** Stops the running compile and discards the queued one. */
  async cancel(): Promise<void> {
    try {
      await this.api.cancelCompile();
    } catch (error) {
      this.dispatch({ type: "failed", message: error instanceof Error ? error.message : "The compile could not be cancelled." });
    }
  }
}
