import type { EventHub, HeartbeatClock } from "./sse.ts";
import type { RateLimiter } from "./users.ts";
import type {
  ProjectAgentsPort,
  AgentRunnerPort,
  ChatHistoryPort,
  CompileCoordinator,
  CompilerPort,
  ContentHash,
  CredentialStorePort,
  FileEntry,
  LoginRelayPort,
  PeoplePort,
  ProjectEntry,
  ProviderId,
  RelPath,
  Result,
  StatePort,
  StoreError,
  TurnService,
} from "@caztor/core";

/** A capability probe: whether an optional local tool is usable, its version when known and, when it is not, why. */
export type Probe = () => Promise<{ ok: boolean; version?: string; reason?: string }>;

/** The project files the routes use. The local project store satisfies it; a cloud store could too. */
export interface FileStore {
  list(): Promise<FileEntry[]>;
  /** UTF-8 text up to 2 MB: `too_large` and `not_text` otherwise. */
  readText(path: RelPath): Promise<Result<{ bytes: Uint8Array; hash: ContentHash }, StoreError>>;
  write(
    path: RelPath,
    bytes: Uint8Array,
    expect: ContentHash | null | "any",
  ): Promise<Result<{ hash: ContentHash }, StoreError>>;
  mkdir(path: RelPath): Promise<Result<void, StoreError>>;
  /** Files and folders. Never replaces an existing entry. */
  rename(from: RelPath, to: RelPath): Promise<Result<void, StoreError>>;
  /** A folder with content needs `recursive: true`. */
  remove(path: RelPath, opts?: { recursive: boolean }): Promise<Result<void, StoreError>>;
}

/** Why a project could not be opened. */
export interface ProjectOpenError {
  code: "invalid_path" | "invalid_name" | "exists" | "not_available" | "folder_refused" | "not_found" | "turn_running";
  message: string;
}

/** One access key of a person, as the host sees it: never the key itself. */
export interface InviteSummary {
  /** The id in the invite link. */
  id: string;
  createdAt: number;
  expiresAt: number;
  /** `old` is a one-time link of the first version, which no longer works. */
  status: "active" | "expired" | "locked" | "old";
  /** Wrong keys tried so far; the invite locks at 10. */
  failures: number;
  /** Browsers signed in with this key now. */
  sessions: number;
}

/** A person who may use this server, as the host sees them. No secret is ever part of it. */
export interface UserSummary {
  id: string;
  name: string;
  role: "host" | "collaborator";
  createdAt: number;
  sessions: number;
  invites: InviteSummary[];
}

export interface UsersError {
  code: "invalid_name" | "invalid_lifetime" | "not_found" | "host_refused" | "not_exposed" | "busy" | "io" | "unsafe" | "corrupt";
  message: string;
}

/** Ports and services the routes need. Routes are added slice by slice. */
export interface ApiDeps {
  /** Shown as the project name; the folder name, never a full path. */
  projectName: string;
  /**
   * Collaborators can reach this server (at least one public name is set). The session answer then names its user, and
   * every compile runs in the sandbox. Off, the server answers exactly as a single-user one.
   */
  collaboratorMode?: boolean;
  /** Changes every time a project is opened, so the browser can name the project it means. */
  projectId?: string;
  store: FileStore;
  state: StatePort;
  /** Where file and compile events are published for the SSE stream. */
  events: EventHub;
  clock: HeartbeatClock;
  /** The LaTeX engine probe. Until a compiler is wired the engine is reported as unavailable. */
  engine?: Probe;
  /** The compile pipeline. Until it is wired, compile requests are refused with a readable error. */
  compile?: {
    coordinator: CompileCoordinator;
    compiler: Pick<CompilerPort, "available" | "readArtifact">;
  };
  /** Where API keys are stored. Until it is wired, the credential routes answer 503 and api mode cannot be switched on. */
  credentials?: CredentialStorePort;
  /** The projects this server can move to. Until it is wired, the project routes answer 503. */
  projects?: {
    list(): Promise<Array<ProjectEntry & { active: boolean }>>;
    open(path: string): Promise<Result<void, ProjectOpenError>>;
    /** Makes a new project in the papers folder and opens it. */
    create(name: string): Promise<Result<void, ProjectOpenError>>;
  };
  /** Set when the pages are shown in a frame of this origin (a PaperSmith dashboard); the web app then hides the navigator. */
  embed?: { origin: string };
  /** Set in a PaperSmith workspace: where its paper is, and making it the way PaperSmith does. */
  papersmith?: {
    status(): Promise<{ main: RelPath; exists: boolean } | null>;
    scaffold(): Promise<Result<string[], { message: string }>>;
  };
  /** The sandbox probe. Until a sandbox is wired it is reported as unavailable. */
  sandbox?: Probe;
  /**
   * Seals the host's confirmation of a project's CLI configuration, so a record written into the project by anyone
   * else does not count. Without it the fingerprint itself is stored, as a single-user server once did.
   */
  trust?: {
    seal(provider: ProviderId, fingerprint: string): Promise<string>;
    holds(provider: ProviderId, fingerprint: string, stored: string | undefined): Promise<boolean>;
  };
  /** The people who may use this server. Until it is wired, the user routes answer 503 and every sign-in is refused. */
  users?: {
    list(): Promise<Result<UserSummary[], UsersError>>;
    /**
     * An invite for a collaborator with this name, lasting `minutes` (the server's default when absent): a link that
     * only opens the sign-in page, and an access key returned this once.
     */
    invite(name: string, minutes?: number): Promise<Result<{ user: UserSummary; link: string; key: string; inviteId: string; expiresAt: number }, UsersError>>;
    /** Ends one access key and the sessions made with it. */
    revokeInvite(id: string): Promise<Result<void, UsersError>>;
    revoke(id: string): Promise<Result<void, UsersError>>;
    /** The new session's raw secret when the key opens that invite, or null, without saying why. */
    signIn(inviteId: string, key: string): Promise<string | null>;
    /** Spends this launch's host link and returns the new session's raw secret, or null when the code cannot be used. */
    redeemHost(code: string): Promise<string | null>;
    /** Session cookies get `Secure` (a TLS proxy fronts the server). */
    secureCookies: boolean;
    /** Counts failed sign-ins (wrong keys, used host links) per remote address. */
    redemptions: RateLimiter;
  };
  /**
   * Each collaborator's own state view, chat history and key store. The host's are `state`, `agents.history` and
   * `credentials`. Without it a collaborator's chat, provider and key requests are refused.
   */
  people?: PeoplePort;
  /** Signing in to a provider's CLI from the browser. Until it is wired, the login routes answer 503. */
  logins?: LoginRelayPort;
  /** The provider agents and the chat. Until they are wired, providers are listed as unavailable and chat requests are refused. */
  agents?: {
    turns: TurnService;
    history: ChatHistoryPort;
    /** One adapter per provider that has one; a provider without an adapter is listed as unavailable. */
    runners: Partial<Record<ProviderId, AgentRunnerPort>>;
    /** The turn whose undo is available now (the top of the undo stack), or null. */
    undoable(): Promise<Result<string | null, { message: string }>>;
    /** The project's own agents (PaperSmith's), offered in the chat as `/<name>`. */
    projectAgents?: ProjectAgentsPort;
  };
}
