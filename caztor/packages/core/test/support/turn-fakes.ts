import type {
  AgentDefinition,
  AgentEvent,
  AgentRunnerPort,
  ChangedFile,
  ChatHistoryPort,
  ChatTurnRecord,
  ContentHash,
  ProjectState,
  ProviderId,
  ProviderStatus,
  ProvisionerPort,
  ProvisionOutcome,
  RelPath,
  RestoreResult,
  Result,
  SnapshotPort,
  StatePort,
  TurnRequest,
  UserWrite,
} from "../../src/index.ts";

export const hashOf = (text: string) => `sha256:${text.padEnd(64, "0").slice(0, 64)}` as ContentHash;
export const rel = (path: string) => path as RelPath;

export const agentDefinition = (hash = "agent1"): AgentDefinition => ({
  hash: hashOf(hash),
  name: "caztor",
  description: "LaTeX assistant",
  prompt: "You edit LaTeX.",
  tools: ["Read", "Edit"],
});

export function emptyState(): ProjectState {
  return {
    selectedProvider: null,
    authModes: {},
    models: {},
    sessions: {},
    mainFile: null,
    stopOnFirstError: false,
    autoCompile: true,
    sandboxedCompile: false,
    disclosureAcknowledged: false,
    projectCliConfigTrusted: {},
    provisioned: {},
  };
}

export function memoryState(initial: Partial<ProjectState> = {}): StatePort & { current: ProjectState } {
  const port = {
    current: { ...emptyState(), ...initial },
    async load() {
      return structuredClone(port.current);
    },
    async update(patch: Partial<ProjectState>) {
      port.current = { ...port.current, ...patch };
      return structuredClone(port.current);
    },
  };
  return port;
}

/** Everything the turn service does to its collaborators, in order. */
export type CallLog = string[];

export interface FakeRunContext {
  req: TurnRequest;
  signal: AbortSignal;
}

export interface FakeRunner extends AgentRunnerPort {
  requests: TurnRequest[];
  status: ProviderStatus;
  script: (context: FakeRunContext) => AsyncIterable<AgentEvent>;
  isolationTier: string;
}

export async function* events(...list: AgentEvent[]): AsyncGenerator<AgentEvent> {
  for (const event of list) yield event;
}

/** Resolves when the signal aborts. */
export function aborted(signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) resolve();
    else signal.addEventListener("abort", () => resolve(), { once: true });
  });
}

export function fakeRunner(log: CallLog, provider: ProviderId = "claude"): FakeRunner {
  const runner: FakeRunner = {
    provider,
    get isolation() {
      return runner.isolationTier;
    },
    isolationTier: "tier-1",
    requests: [],
    status: { provider, installed: true, requiresModel: false },
    script: () => events({ type: "done", reason: "completed" }),
    async detect() {
      return runner.status;
    },
    runTurn(req, signal) {
      log.push("run");
      runner.requests.push(req);
      return runner.script({ req, signal });
    },
  };
  return runner;
}

export interface FakeProvisioner extends ProvisionerPort {
  calls: Array<{ provider: ProviderId; replace: boolean }>;
  agent: AgentDefinition;
  outcomes: ProvisionOutcome[];
  failure: string | null;
}

export function fakeProvisioner(log: CallLog): FakeProvisioner {
  const port: FakeProvisioner = {
    calls: [],
    agent: agentDefinition(),
    outcomes: [{ target: ".claude/agents/caztor.md", status: "unchanged" }],
    failure: null,
    async ensure(provider, opts) {
      log.push("ensure");
      port.calls.push({ provider, replace: opts?.replace === true });
      if (port.failure !== null) return { ok: false, error: { message: port.failure } } satisfies Result<never, { message: string }>;
      return { ok: true, value: { outcomes: port.outcomes, agent: port.agent } };
    },
  };
  return port;
}

export interface FakeSnapshots extends SnapshotPort {
  captured: string[];
  diffs: Array<{ turnId: string; userWrites: ReadonlyMap<RelPath, UserWrite> }>;
  pruned: number[];
  restores: Array<{ turnId: string; mode: string }>;
  captureFailure: string | null;
  captureResult: { partial: boolean; unprotected: RelPath[] };
  /** What the agent changed, before the user-only files are left out. */
  agentChanges: ChangedFile[];
  /** Runs inside `capture`, to simulate something happening while the snapshot is taken. */
  duringCapture: (() => void) | null;
  /** Runs while the diff is being worked out. */
  duringDiff: (() => void) | null;
  restoreResult: RestoreResult;
  top: string | null;
  /** The names `notCovered` reports. */
  unreadable: RelPath[];
  unreadableFailure: string | null;
}

export function fakeSnapshots(log: CallLog): FakeSnapshots {
  const port: FakeSnapshots = {
    captured: [],
    diffs: [],
    pruned: [],
    restores: [],
    captureFailure: null,
    captureResult: { partial: false, unprotected: [] },
    agentChanges: [],
    duringCapture: null,
    duringDiff: null,
    restoreResult: { status: "restored", files: [], skipped: [] },
    top: null,
    unreadable: [],
    unreadableFailure: null,
    async notCovered() {
      if (port.unreadableFailure !== null) return { ok: false, error: { message: port.unreadableFailure } };
      return { ok: true, value: port.unreadable };
    },
    async capture(turnId) {
      log.push("capture");
      port.captured.push(turnId);
      port.duringCapture?.();
      if (port.captureFailure !== null) return { ok: false, error: { message: port.captureFailure } };
      return { ok: true, value: port.captureResult };
    },
    async diff(turnId, userWrites) {
      log.push("diff");
      port.diffs.push({ turnId, userWrites });
      port.duringDiff?.();
      // A file the user changed that the agent did not change is not in `agentChanges`; one both changed is flagged.
      return { ok: true, value: port.agentChanges.map((file) => (userWrites.has(file.path) ? { ...file, mixed: true } : file)) };
    },
    async undoable() {
      return { ok: true, value: port.top };
    },
    async restore(turnId, mode) {
      log.push("restore");
      port.restores.push({ turnId, mode });
      return port.restoreResult;
    },
    async prune(keep) {
      log.push("prune");
      port.pruned.push(keep);
      return { ok: true, value: [] };
    },
  };
  return port;
}

export interface FakeUserWrites {
  begin(): void;
  peek(): ReadonlyMap<RelPath, UserWrite>;
  end(): Promise<ReadonlyMap<RelPath, UserWrite>>;
  /** A save by the user through the file API; counted only while recording. */
  save(path: string, before: string | null, after: string | null): void;
  recording: boolean;
}

export function fakeUserWrites(log: CallLog): FakeUserWrites {
  let writes: Map<RelPath, UserWrite> | null = null;
  const port: FakeUserWrites = {
    get recording() {
      return writes !== null;
    },
    begin() {
      log.push("begin");
      writes = new Map();
    },
    peek() {
      return new Map(writes ?? []);
    },
    async end() {
      log.push("end");
      const done = writes ?? new Map<RelPath, UserWrite>();
      writes = null;
      return done;
    },
    save(path, before, after) {
      if (writes === null) return;
      const known = writes.get(rel(path));
      writes.set(rel(path), {
        first: known === undefined ? (before === null ? null : hashOf(before)) : known.first,
        last: after === null ? null : hashOf(after),
      });
    },
  };
  return port;
}

export function memoryHistory(): ChatHistoryPort & { records: ChatTurnRecord[]; cleared: ProviderId[]; failure: string | null } {
  const port = {
    failure: null as string | null,
    records: [] as ChatTurnRecord[],
    cleared: [] as ProviderId[],
    async load(provider: ProviderId) {
      return port.records.filter((record) => record.provider === provider);
    },
    async append(record: ChatTurnRecord) {
      if (port.failure !== null) throw new Error(port.failure);
      port.records.push(record);
    },
    async clear(provider: ProviderId) {
      port.cleared.push(provider);
      port.records = port.records.filter((record) => record.provider !== provider);
    },
  };
  return port;
}

export const changed = (path: string, change: ChangedFile["change"] = "modified"): ChangedFile => ({
  path: rel(path),
  change,
  beforeHash: change === "created" ? null : hashOf(`${path}-before`),
  afterHash: change === "deleted" ? null : hashOf(`${path}-after`),
  undoable: true,
  mixed: false,
});
