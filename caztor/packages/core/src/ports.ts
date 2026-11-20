// Pure domain contracts. This file must not import Node built-ins (see import-guard.test.ts).

export type RelPath = string & { readonly __brand: "RelPath" };
export type ContentHash = `sha256:${string}`;
export type Result<T, E> = { ok: true; value: T } | { ok: false; error: E };

export const PROVIDER_IDS = ["claude", "opencode", "codex", "antigravity", "pi"] as const;
export type ProviderId = (typeof PROVIDER_IDS)[number];

/** A folder Caztor can open: a PaperSmith workspace or any other project. */
export interface ProjectEntry {
  path: string;
  /** The folder name. */
  name: string;
  kind: "papersmith" | "folder";
  /** The paper's title, when the workspace states one. */
  title?: string;
  /** A workspace with no `paper/main.tex` yet: there is nothing to compile. */
  missingMain?: boolean;
}

/** How a provider's CLI is signed in: with the user's own account login, or with an API key stored by Caztor. */
export const AUTH_MODES = ["account", "api"] as const;
export type AuthMode = (typeof AUTH_MODES)[number];

/** Names where a key is stored: `claude`, `codex`, `opencode:<vendor>` or `pi:<vendor>`. */
export type CredentialSlot = string;
/** What the browser may know about a key: whether it is set and, for a long enough key, its last four characters. */
export interface CredentialStatus {
  slot: CredentialSlot;
  set: boolean;
  last4?: string;
}
/** Why the credential store refused. The messages never contain a key. */
export type CredentialError = {
  code: "unsafe_permissions" | "unsafe_owner" | "linked" | "corrupt" | "invalid" | "io";
  message: string;
};
/** What a runner needs: the key of one slot, read on demand and held only for the turn. Null when nothing is stored. */
export interface CredentialReaderPort {
  read(slot: CredentialSlot): Promise<Result<string | null, CredentialError>>;
}
/** The write-only store. No method returns more than a `CredentialStatus`, except `read`, which only runners receive. */
export interface CredentialStorePort extends CredentialReaderPort {
  status(slot: CredentialSlot): Promise<Result<CredentialStatus, CredentialError>>;
  /** Every slot that has a key. */
  list(): Promise<Result<CredentialStatus[], CredentialError>>;
  set(slot: CredentialSlot, key: string): Promise<Result<CredentialStatus, CredentialError>>;
  clear(slot: CredentialSlot): Promise<Result<CredentialStatus, CredentialError>>;
}

export interface FileEntry {
  path: RelPath;
  kind: "file" | "dir";
  size: number;
}
export type StoreError =
  | {
      code: "not_found" | "invalid_path" | "outside_root" | "hidden" | "exists" | "too_large" | "not_text" | "io";
      path: string;
    }
  | { code: "conflict"; path: RelPath; currentHash: ContentHash | null };
export interface FileChange {
  path: RelPath;
  hash: ContentHash | null;
}

export interface ProjectStorePort {
  list(): Promise<FileEntry[]>;
  read(path: RelPath): Promise<Result<{ bytes: Uint8Array; hash: ContentHash }, StoreError>>;
  /** expect: a hash = must match; null = must not exist (create, upload); "any" = unconditional (undo only). */
  write(
    path: RelPath,
    bytes: Uint8Array,
    expect: ContentHash | null | "any",
  ): Promise<Result<{ hash: ContentHash }, StoreError>>;
  mkdir(path: RelPath): Promise<Result<void, StoreError>>;
  /** Files and folders. */
  rename(from: RelPath, to: RelPath): Promise<Result<void, StoreError>>;
  remove(path: RelPath, opts?: { recursive: boolean }): Promise<Result<void, StoreError>>;
  watch(onChange: (change: FileChange) => void): () => void;
}

export interface Diagnostic {
  severity: "error" | "warning";
  file: RelPath | null;
  line: number | null;
  message: string;
  detail?: string;
  source: "stderr" | "log" | "caztor";
}
export interface CompileRequest {
  main: RelPath;
  stopOnFirstError: boolean;
  /** Run the engine inside the OS sandbox. Off unless the project turned it on. */
  sandboxed?: boolean;
}
export interface CompileResult {
  status: "success" | "failed-with-errors" | "failed" | "timed-out" | "cancelled" | "engine-missing";
  pdfRev: string | null;
  diagnostics: Diagnostic[];
  durationMs: number;
  logAvailable: boolean;
}
/** An agent the project defines itself, such as PaperSmith's `.claude/agents/<name>.md`. */
export interface ProjectAgent {
  name: string;
  description: string;
  /** The agent's instructions: its file without the frontmatter. */
  prompt: string;
  /** Where it is defined, relative to the project folder. */
  file: string;
}

export interface ProjectAgentsPort {
  list(): Promise<ProjectAgent[]>;
  /**
   * The workspace files a PaperSmith dashboard panel would hand its agent (latest proposal revision, model spec, latest
   * experiments protocol, manuscript), those that exist, relative to the project folder. Named to the agent because
   * its own file search may skip them: PaperSmith workspaces ignore those folders in git.
   */
  sources?(): Promise<string[]>;
}

/** How many files a turn names as not protected by undo; the rest are only counted, so the event stays small. */
export const MAX_NAMED_UNPROTECTED = 20;

export type CompileEvent =
  | { type: "started"; compileId: string }
  | { type: "phase"; phase: "downloading" | "typesetting" | "bibliography" | "finalizing" }
  | { type: "finished"; compileId: string; result: CompileResult };
export interface CompilerPort {
  /** `reason` says why the engine cannot be used when `ok` is false. */
  available(): Promise<{ ok: boolean; version?: string; reason?: string }>;
  /** Aborting the signal cancels the run. */
  compile(req: CompileRequest, signal: AbortSignal): AsyncIterable<CompileEvent>;
  readArtifact(kind: "pdf" | "log"): Promise<Uint8Array | null>;
}

export const TURN_ERROR_CODES = [
  "not_installed",
  "auth",
  "model_unavailable",
  "model_required",
  "rate_limited",
  "permission_denied",
  "isolation_failed",
  "snapshot_failed",
  "malformed_output",
  "timeout",
  "provider_error",
  "mode_unsupported",
] as const;
export type TurnErrorCode = (typeof TURN_ERROR_CODES)[number];
export type ToolKind = "read" | "edit" | "write" | "search" | "command" | "other";
export type AgentEvent =
  | { type: "session"; sessionId: string }
  | { type: "text_delta"; messageId: string; text: string }
  /** Authoritative; replaces the deltas received so far for this message. */
  | { type: "text"; messageId: string; text: string }
  | { type: "tool_start"; toolId: string; name: string; kind: ToolKind; path?: string }
  | { type: "tool_update"; toolId: string; path?: string; title?: string }
  | { type: "tool_end"; toolId: string; status: "done" | "failed"; summary?: string }
  /** `action` names something the chat can offer next to the notice. */
  | { type: "notice"; level: "info" | "warning"; message: string; action?: "replace_definition" }
  | { type: "error"; code: TurnErrorCode; message: string; detail?: string }
  | {
      type: "done";
      reason: "completed" | "cancelled" | "failed";
      usage?: { inputTokens?: number; outputTokens?: number; costUsd?: number };
    };

export interface ProviderStatus {
  provider: ProviderId;
  installed: boolean;
  unavailableReason?: string;
  version?: string;
  versionWarning?: string;
  models?: string[];
  /** The model a turn uses when none is chosen. When set, the browser offers no separate "Default" entry. */
  defaultModel?: string;
  requiresModel: boolean;
  /** False when the CLI offers no way to choose a model; the chat then hides the model setting. Default true. */
  supportsModel?: boolean;
  /** Something the user should know about this provider that is not an error, such as what isolation hides. */
  note?: string;
}
export interface AgentDefinition {
  hash: ContentHash;
  name: string;
  description: string;
  prompt: string;
  tools: string[];
}
export interface TurnRequest {
  prompt: string;
  sessionId: string | null;
  model: string | null;
  agent: AgentDefinition;
  /** How the CLI signs in for this turn. Missing means `account`. */
  authMode?: AuthMode;
  /** Set only for a collaborator's turn: the environment the runner builds the CLI's from, instead of the server's. */
  env?: Readonly<Record<string, string | undefined>>;
  /** Set only for a collaborator's turn: where their own API keys are read, instead of the host's. */
  credentials?: CredentialReaderPort;
  /**
   * Set only for a collaborator's turn: the CLI runs inside bubblewrap, which shows it the project, this private folder
   * (its HOME) and the read-only system and CLI install folders, and nothing else of the host's home. A runner that
   * cannot sandbox the turn refuses it.
   */
  sandbox?: { home: string };
}
/** Project files that make a provider CLI run programs; shown to the user, who may trust them. */
export interface ProjectConfigFinding {
  /** Paths relative to the project folder; a folder ends with a slash. */
  files: string[];
  /** A hash of the files' names and contents: a confirmation counts only while it is unchanged. */
  fingerprint: string;
}
export interface AgentRunnerPort {
  readonly provider: ProviderId;
  /** Isolation tier id; part of the session record. */
  readonly isolation: string;
  detect(): Promise<ProviderStatus>;
  /** The project's own CLI configuration that would run programs when a turn starts, or null. Absent for a provider that has none. */
  projectConfig?(): Promise<ProjectConfigFinding | null>;
  /** Emits exactly one "done" event, and it is the last one. */
  runTurn(req: TurnRequest, signal: AbortSignal): AsyncIterable<AgentEvent>;
  /**
   * Called when the turn was cut off because the runner kept going after the abort signal: kills what the current
   * turn started (the whole process group) at once. Never throws.
   */
  forceStop?(): void;
}

export interface ProvisionOutcome {
  target: string;
  /** `unavailable`: the writing guides could not be prepared. The turn goes on without them; `detail` says why. */
  status: "created" | "updated" | "unchanged" | "skipped_user_modified" | "unavailable";
  detail?: string;
}
/** One file of the writing guides: `INDEX.md`, the license copy, or a numbered guide such as `01-materials-and-methods.md`. */
export interface GuideDocument {
  name: string;
  bytes: Uint8Array;
}
/** Where the writing guides come from. Replaceable without changing how they are provisioned. */
export interface GuideSourcePort {
  load(): Promise<Result<readonly GuideDocument[], { message: string }>>;
}
export interface ProvisionerPort {
  /** Idempotent. Returns the definition actually present in the project. */
  ensure(
    provider: ProviderId,
    opts?: { replace: boolean },
  ): Promise<Result<{ outcomes: ProvisionOutcome[]; agent: AgentDefinition }, { message: string }>>;
}

export interface ChangedFile {
  path: RelPath;
  change: "created" | "modified" | "deleted";
  beforeHash: ContentHash | null;
  afterHash: ContentHash | null;
  undoable: boolean;
  mixed: boolean;
}
/**
 * What the user did to one file through the file API while a turn ran: the content hash before the first change
 * and after the last one (null = the file did not exist, or no longer does).
 */
export interface UserWrite {
  first: ContentHash | null;
  last: ContentHash | null;
}
export type RestoreResult =
  | { status: "restored"; files: RelPath[]; skipped: RelPath[] }
  | { status: "conflict"; conflicts: { path: RelPath; expected: ContentHash | null; actual: ContentHash | null }[] }
  | { status: "unavailable"; reason: "not_latest" | "discarded" | "already_undone" }
  /** Nothing was undone because the safety snapshot could not be taken, or a write failed part-way. */
  | { status: "failed"; message: string };
export interface SnapshotPort {
  capture(turnId: string): Promise<Result<{ partial: boolean; unprotected: RelPath[] }, { message: string }>>;
  /** `userWrites`: what the user saved through the file API while the turn ran (see `UserWrite`). */
  diff(turnId: string, userWrites: ReadonlyMap<RelPath, UserWrite>): Promise<Result<ChangedFile[], { message: string }>>;
  /** Names in the project that Caztor cannot read (not valid UTF-8), so undo does not cover them. */
  notCovered(): Promise<Result<RelPath[], { message: string }>>;
  /** Top of the LIFO stack. Fails with a readable message when the snapshot folder cannot be used. */
  undoable(): Promise<Result<string | null, { message: string }>>;
  restore(turnId: string, mode: "strict" | "skip_conflicts" | "force"): Promise<RestoreResult>;
  /** Returns the discarded turn ids. */
  prune(keepTurns: number): Promise<Result<string[], { message: string }>>;
}

export interface SessionRecord {
  sessionId: string;
  agentHash: ContentHash;
  isolation: string;
  /** The sign-in method the conversation started under. Missing means `account`. */
  authMode?: AuthMode;
}
export interface ProjectState {
  selectedProvider: ProviderId | null;
  /** Per provider, how the CLI signs in. Missing means `account`. */
  authModes: Partial<Record<ProviderId, AuthMode>>;
  models: Partial<Record<ProviderId, string>>;
  sessions: Partial<Record<ProviderId, SessionRecord>>;
  mainFile: RelPath | null;
  stopOnFirstError: boolean;
  autoCompile: boolean;
  sandboxedCompile: boolean;
  disclosureAcknowledged: boolean;
  /** Per provider, the fingerprint of the project CLI configuration the user trusted. */
  projectCliConfigTrusted: Partial<Record<ProviderId, string>>;
  provisioned: Record<string, { hash: ContentHash; createdByCaztor: boolean }>;
  /** Each collaborator's own choices, by user id. Absent until a collaborator saves one; the host's stay in the fields above. */
  users?: Record<string, PersonalState>;
}
/** What each person chooses for themselves; the host's live in the top-level fields of the same names. */
export type PersonalState = Pick<ProjectState, "selectedProvider" | "authModes" | "models" | "sessions">;
export interface StatePort {
  /** Returns defaults when the file is missing or corrupt. */
  load(): Promise<ProjectState>;
  /** Atomic write of .caztor/state.json. */
  update(patch: Partial<ProjectState>): Promise<ProjectState>;
  /** Like `update`, with the patch worked out from the current state inside the same serialized step. */
  change?(edit: (current: ProjectState) => Partial<ProjectState>): Promise<ProjectState>;
}

export type TurnEvent =
  | AgentEvent
  /** `unprotected` names at most `MAX_NAMED_UNPROTECTED` files; `unprotectedCount` is set when there are more. */
  | { type: "turn_started"; turnId: string; provider: ProviderId; snapshotPartial: boolean; unprotected: RelPath[]; unprotectedCount?: number }
  /** An empty list means "No files changed". */
  | {
      type: "files_changed";
      turnId: string;
      files: ChangedFile[];
      /** Names Caztor cannot read, so they are not in `files` and undo does not cover them. Absent when there are none. */
      notCovered?: RelPath[];
    };
