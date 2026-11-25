import type { ChatTurnRecord, CompileResult, Diagnostic, FileEntry, LoginKey, LoginMethod, LoginView, ProviderId, TurnEvent } from "@caztor/core";

export type { ChatTurnRecord, CompileResult, Diagnostic, FileEntry, LoginKey, LoginMethod, LoginView, ProviderId, TurnEvent };

/** The person's own sign-in to a provider's CLI, and the ways to sign in to it. */
export interface LoginListing {
  login: LoginView | null;
  methods: LoginMethod[];
}

export interface Settings {
  stopOnFirstError: boolean;
  autoCompile: boolean;
  sandboxedCompile: boolean;
  mainFile: string | null;
  disclosureAcknowledged: boolean;
}

export interface Capability {
  available: boolean;
  version?: string;
  /** Why it is not available, when the server knows. */
  reason?: string;
}

/** Who this page is signed in as: the host, or a collaborator the host invited. */
export interface SessionUser {
  id: string;
  name: string;
  role: "host" | "collaborator";
}

/** One access key of a collaborator, never the key itself. */
export interface CollaboratorKey {
  /** The id in the invite link. */
  id: string;
  createdAt: number;
  expiresAt: number;
  /** `locked` took 10 wrong keys; `old` is a one-time link of the first version, which no longer works. */
  status: "active" | "expired" | "locked" | "old";
  failures: number;
  /** Browsers signed in with this key now. */
  sessions: number;
}

/** A person the host invited. No secret is ever part of it. */
export interface Collaborator extends SessionUser {
  createdAt: number;
  /** How many browsers are signed in as this person. */
  sessions: number;
  /** Their access keys, oldest first. */
  invites: CollaboratorKey[];
}

/** A new invite: the link opens a sign-in page, the key is shown this once. */
export interface CollaboratorInvite {
  user: Collaborator;
  link: string;
  key: string;
  inviteId: string;
  expiresAt: number;
}

export interface Session {
  /** Who this page is signed in as. */
  user?: SessionUser;
  /** Set in a PaperSmith workspace: where its paper is, and whether it exists yet. */
  papersmith?: { main: string; exists: boolean };
  /** Set when the page is shown in a frame of this origin (a PaperSmith dashboard): one project, no navigator. */
  embed?: { origin: string };
  /** `id` changes every time a project is opened. */
  project: { name: string; id?: string };
  engine: Capability;
  sandbox: Capability;
  settings: Settings;
}

/** A folder the navigator can open. */
export interface ProjectEntry {
  path: string;
  name: string;
  kind: "papersmith" | "folder";
  title?: string;
  /** A workspace with no `paper/main.tex` yet. */
  missingMain?: boolean;
  active: boolean;
}

export interface FileContent {
  path: string;
  content: string;
  hash: string;
}

/** A server event as read from the stream. The client also emits `stream_resumed` after it had to reconnect. */
export interface ServerEvent {
  id: number | null;
  event: string;
  data: unknown;
}

/** What `GET /api/compile/status` reports. */
export interface CompileStatusReport {
  running: { compileId: string } | null;
  queued: { compileId: string } | null;
  last: { compileId: string; result: CompileResult } | null;
  /** A preview PDF exists on the server, even when this server run has not compiled yet. */
  pdfAvailable: boolean;
}

/** How a provider's CLI signs in: with the user's own login, or with an API key Caztor keeps. */
export type AuthMode = "account" | "api";

/** Whether a key is stored in one slot, and at most its last four characters. The key itself never reaches the browser. */
export interface KeyStatus {
  slot: string;
  set: boolean;
  last4?: string;
}

/** The sign-in state of one provider. */
export interface ProviderAuth {
  mode: AuthMode;
  /** The modes the provider offers. A provider with API access only through its login offers just `account`. */
  modes: AuthMode[];
  keys: KeyStatus[];
  /** The slot the active key is stored in; null when it cannot be told yet (`slotProblem` says why). */
  slot: string | null;
  slotProblem?: string;
  /** A key is stored for the active slot, so API mode can be used. */
  apiReady: boolean;
  /** Why keys cannot be shown or saved (the store is unusable), when that is so. */
  storeProblem?: string;
  login: "signed_in" | "signed_out" | "unknown";
  /** The terminal step that signs in to the provider's CLI. Commands are written between backticks. */
  loginHint: string;
}

/** One provider as `GET /api/providers` lists it. */
export interface ProviderInfo {
  id: ProviderId;
  installed: boolean;
  /** Why the provider cannot be used, when it is not installed or not set up. */
  unavailableReason?: string;
  version?: string;
  versionWarning?: string;
  /** Models the CLI offers, when it can list them. */
  models?: string[];
  /** The model a turn uses when none is chosen; the list then has no "Default" entry. */
  defaultModel?: string;
  requiresModel: boolean;
  /** False when the CLI offers no way to choose a model, so the model setting is not shown. */
  supportsModel?: boolean;
  /** Something to know about this provider that is not an error. */
  note?: string;
  /** The model chosen for this project, if any. */
  model: string | null;
  /** The project's own CLI configuration that would run programs, when it has some. `fingerprint` identifies what was listed. */
  projectConfig?: { files: string[]; confirmed: boolean; fingerprint: string };
  /** How the provider signs in. Absent when the server does not report it. */
  auth?: ProviderAuth;
}

export interface ProvidersListing {
  selected: ProviderId | null;
  providers: ProviderInfo[];
}

export type UndoMode = "strict" | "skip_conflicts" | "force";

/** A file that changed after the turn, as the server reports it when an undo is refused. */
export interface UndoConflict {
  path: string;
  expected: string | null;
  actual: string | null;
}

/** What an undo did. `skipped` lists files that were left as they are; a non-empty list means the undo was only partial. */
export interface UndoOutcome {
  files: string[];
  skipped: string[];
}

/** What `GET /api/chat/history` returns for one provider. */
export interface ChatHistory {
  provider: ProviderId;
  turns: ChatTurnRecord[];
  undoableTurnId: string | null;
  undoProblem: string | null;
  running: boolean;
  currentTurnId: string | null;
}

/** Starts a turn with a message, or follows the current turn after the events already seen. */
export type TurnStreamRequest = { kind: "start"; provider: ProviderId; prompt: string } | { kind: "follow"; after: number };

/**
 * Everything the UI asks of the server. Components receive this interface, so tests replace it with a fake
 * and no running server is needed.
 */
export interface ApiClient {
  getSession(): Promise<Session>;
  /** Host only: the collaborators. */
  listCollaborators(): Promise<Collaborator[]>;
  /** Host only: an invite link and access key for a person, lasting `minutes` (10 minutes to 365 days). */
  inviteCollaborator(name: string, minutes: number): Promise<CollaboratorInvite>;
  /** Host only: ends one access key and the browsers signed in with it. */
  revokeCollaboratorKey(id: string): Promise<void>;
  /** Host only: removes a collaborator and signs out every browser of theirs. */
  revokeCollaborator(id: string): Promise<void>;
  listProjects(): Promise<ProjectEntry[]>;
  /** Moves the server to a folder. Refused while a turn runs. */
  openProject(path: string): Promise<ProjectEntry[]>;
  /** Makes a new project in the papers folder and moves the server to it. */
  createProject(name: string): Promise<ProjectEntry[]>;
  /** Creates `paper/` the way PaperSmith's scaffold does. */
  scaffoldPaper(): Promise<{ created: string[] }>;
  patchSettings(patch: Partial<Settings>): Promise<Settings>;
  listFiles(): Promise<FileEntry[]>;
  readFile(path: string): Promise<FileContent>;
  /**
   * Replaces the text of a file if its hash is still `baseHash` (null: the file must not exist yet). A file that
   * changed on disk meanwhile fails with an `ApiError` whose code is `conflict` and whose `currentHash` is the new hash.
   */
  writeFile(path: string, content: string, baseHash: string | null): Promise<{ hash: string }>;
  createEntry(path: string, kind: "file" | "dir"): Promise<void>;
  renameEntry(from: string, to: string): Promise<void>;
  deleteEntry(path: string, options: { recursive: boolean }): Promise<void>;
  uploadFile(path: string, bytes: Uint8Array): Promise<void>;
  /** Starts a compile of the project's main file, or queues it as the single follow-up when one is running. */
  /** Compiles the project's main file, or `main` when given. */
  startCompile(main?: string): Promise<{ compileId: string; queued: boolean }>;
  /** Stops the running compile and drops the queued one. */
  cancelCompile(): Promise<{ cancelled: boolean }>;
  getCompileStatus(): Promise<CompileStatusReport>;
  /** The preview PDF as bytes. `rev` is only a cache key. The token header cannot be sent by a plain link, so the bytes are fetched. */
  readPdf(rev: string): Promise<Uint8Array>;
  /** The raw log of the last compile. */
  readLog(): Promise<string>;
  /**
   * Streams server events to `listener` until the returned function is called. The connection is read with `fetch`
   * (the token header cannot be sent by `EventSource`) and reopened after a failure; `stream_resumed` tells the
   * listener that events may have been missed in between.
   */
  subscribeEvents(listener: (event: ServerEvent) => void): () => void;
  listProviders(): Promise<ProvidersListing>;
  chatHistory(provider: ProviderId): Promise<ChatHistory>;
  /** The project's own agents (PaperSmith's), which a message can name with `/<name>`. */
  listAgents(): Promise<Array<{ name: string; description: string }>>;
  /**
   * Reads a turn's event stream: `onEvent` gets each event with its sequence number. Resolves when the server ends the
   * stream. A refused start fails with an `ApiError` carrying the server's message (status 400 or 409); a dropped
   * connection fails with an `ApiError` of status 0. The turn keeps running on the server either way.
   */
  streamTurn(request: TurnStreamRequest, onEvent: (event: TurnEvent, seq: number | null) => void, signal: AbortSignal, onOpen?: () => void): Promise<void>;
  /** Detects the provider CLIs again (a CLI may have been installed meanwhile). */
  recheckProviders(): Promise<ProvidersListing>;
  selectProvider(provider: ProviderId): Promise<ProvidersListing>;
  /** Trusts the project's CLI configuration that was listed (identified by its fingerprint). Refused when the files changed since. */
  trustProjectConfig(provider: ProviderId, fingerprint: string): Promise<ProvidersListing>;
  /** Sets the model of a provider; null clears it. A value the server rejects fails with its readable message. */
  setProviderModel(provider: ProviderId, model: string | null): Promise<ProvidersListing>;
  /** Chooses how the provider signs in. `api` is refused with `api_key_missing` when no key is stored. */
  setAuthMode(provider: ProviderId, mode: AuthMode): Promise<ProvidersListing>;
  /** Stores a key. The answer holds only whether it is set and its last four characters. */
  saveCredential(slot: string, key: string): Promise<KeyStatus>;
  deleteCredential(slot: string): Promise<KeyStatus>;
  /** Starts signing in to the provider's CLI from the browser, ending any other sign-in of this person. */
  startLogin(provider: ProviderId, method?: string): Promise<LoginListing>;
  /** The person's sign-in to the provider, with the CLI's text so far. */
  followLogin(provider: ProviderId): Promise<LoginListing>;
  /** Sends a line (a pasted code) or a key to the sign-in. */
  sendLogin(provider: ProviderId, input: { line: string } | { key: LoginKey }): Promise<LoginView>;
  cancelLogin(provider: ProviderId): Promise<void>;
  /** Starts a new conversation with the provider. Refused with `busy` while a turn runs. */
  resetChat(provider: ProviderId): Promise<void>;
  /**
   * Restores the files of a turn. When files changed after the turn and `mode` is `strict` it fails with an `ApiError`
   * of code `undo_conflict` that lists them in `conflicts`; other refusals carry a readable message.
   */
  undoTurn(turnId: string, mode: UndoMode): Promise<UndoOutcome>;
  /** Writes Caztor's agent definition over the one the user changed. */
  replaceDefinition(provider: ProviderId): Promise<void>;
  /** Asks the running turn to stop; the stream then ends with a cancelled `done`. */
  stopTurn(turnId: string): Promise<void>;
}
