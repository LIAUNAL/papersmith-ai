import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type { AgentEvent, AgentRunnerPort, ProjectConfigFinding, ProviderId, ProviderStatus, TurnRequest } from "@caztor/core";

export interface RunContext {
  req: TurnRequest;
  signal: AbortSignal;
  /** The project folder: what the agent edits, straight on disk. */
  root: string;
  /** Writes a file in the project the way an agent's edit tool does. */
  write(path: string, text: string): void;
  /** Resolves when the signal aborts. */
  aborted(): Promise<void>;
  /** Resolves when `release()` is called by the test. */
  gate: Promise<void>;
}

export interface FakeAgentRunner extends AgentRunnerPort {
  /** Every request the runner got, in order. */
  requests: TurnRequest[];
  status: ProviderStatus;
  /** The project CLI configuration the runner reports, or null for none. */
  config: ProjectConfigFinding | null;
  detections: number;
  isolationTier: string;
  /** What the next turns do; a script is an async generator of normalized events. */
  script: (context: RunContext) => AsyncIterable<AgentEvent>;
  /** Lets scripts that wait on `gate` go on. */
  release(): void;
}

/** A provider adapter that spawns nothing: it plays a script of normalized events and really edits files in the project. */
export function createFakeRunner(root: string, provider: ProviderId = "claude"): FakeAgentRunner {
  let release: () => void = () => {};
  let gate = new Promise<void>((resolve) => (release = resolve));
  const runner: FakeAgentRunner = {
    provider,
    get isolation() {
      return runner.isolationTier;
    },
    isolationTier: "fake-tier",
    requests: [],
    config: null,
    detections: 0,
    status: { provider, installed: true, version: "1.0.0", requiresModel: false },
    script: async function* () {
      yield { type: "text", messageId: "m1", text: "Nothing to do." };
      yield { type: "done", reason: "completed" };
    },
    release() {
      release();
      gate = new Promise<void>((resolve) => (release = resolve));
    },
    async projectConfig() {
      return runner.config;
    },
    async detect() {
      runner.detections += 1;
      return runner.status;
    },
    runTurn(req, signal) {
      runner.requests.push(req);
      return runner.script({
        req,
        signal,
        root,
        write(path, text) {
          const file = join(root, path);
          mkdirSync(dirname(file), { recursive: true });
          writeFileSync(file, text);
        },
        aborted: () =>
          new Promise<void>((resolve) => {
            if (signal.aborted) resolve();
            else signal.addEventListener("abort", () => resolve(), { once: true });
          }),
        gate,
      });
    },
  };
  return runner;
}
