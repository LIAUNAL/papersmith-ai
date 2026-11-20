import type { RelPath } from "@caztor/core";
import { ApiError } from "../api/client.ts";
import type { ApiClient, Collaborator, SessionUser, ProjectEntry, ChatHistory, CompileResult, CompileStatusReport, FileEntry, KeyStatus, LoginMethod, LoginView, ProviderId, ProviderInfo, ProvidersListing, ServerEvent, Session, Settings, TurnEvent, UndoOutcome } from "../api/types.ts";

export interface FakeApiInit {
  projectName?: string;
  settings?: Partial<Settings>;
  files?: FileEntry[];
  /** Text of the files that can be opened. */
  contents?: Record<string, string>;
  /** Whether the LaTeX engine is installed. Default: yes. */
  engineAvailable?: boolean;
  /** Why the engine is missing, as the server reports it. */
  engineReason?: string;
  /** A preview PDF that already exists, as after a server restart. */
  pdf?: Uint8Array;
  /** The providers the server lists. Default: claude installed and selected, opencode and codex not installed. */
  providers?: ProvidersListing;
  /** The project's own agents (PaperSmith's), as the slash menu lists them. */
  agents?: Array<{ name: string; description: string }>;
  /** What the project navigator lists. Default: nothing. */
  projects?: ProjectEntry[];
  /** Set to act as a PaperSmith workspace. */
  papersmith?: { main: string; exists: boolean };
  /** Set when the page is shown in a frame of a PaperSmith dashboard. */
  embed?: { origin: string };
  /** Why the server refuses to open a project. */
  openProjectError?: string;
  /** Who the page is signed in as; absent like an older server. */
  user?: SessionUser;
  collaborators?: Collaborator[];
  /** The readable message an invite is refused with. */
  inviteError?: string;
  /** The clock new invites count their expiry from. */
  now?: number;
}

/** The chat side of the fake, driven by hand: a test decides which events a turn sends and when its stream ends or drops. */
export interface FakeChat {
  listing: ProvidersListing;
  /** What the history route answers, per provider. */
  history: Partial<Record<ProviderId, ChatHistory>>;
  /** The messages sent, in order. */
  starts: Array<{ provider: ProviderId; prompt: string }>;
  /** Ids of the turns the UI asked to stop. */
  stopped: string[];
  /** Every undo asked for, in order. */
  undos: Array<{ turnId: string; mode: string }>;
  /** What the next undo does: an outcome, or an error such as an `undo_conflict`. Default: restores nothing, skips nothing. */
  nextUndo: UndoOutcome | ApiError | null;
  /** Providers whose definition was replaced. */
  replaced: ProviderId[];
  /** The keys the UI sent, in order. Kept apart from `calls`, which never holds a key. */
  savedKeys: Array<{ slot: string; key: string }>;
  /** How many times the providers were detected again on request. */
  rechecks: number;
  /** How many streams are connected right now. */
  connections(): number;
  /** The requests to follow a turn, as `after` values. */
  follows: number[];
  /** Makes the next start fail with this error instead of streaming. */
  refuseNext(error: ApiError): void;
  /** Sends an event on the current turn; it is numbered from 1 and kept for resubscribers. */
  emit(event: TurnEvent): void;
  /** Sends `turn_started` for a new id. */
  begin(turnId?: string): void;
  /** Ends the connected stream the way the server does after the last event. */
  end(): void;
  /** Breaks the connected stream like a lost connection. */
  drop(): void;
}

/** The compile side of the fake, driven by hand: a test decides when a run advances and how it ends. */
export interface FakeCompile {
  status: CompileStatusReport;
  /** The PDF `readPdf` returns; null makes it answer 404. */
  pdf: Uint8Array | null;
  log: string | null;
  /** How many `startCompile` calls were made. */
  starts: number;
  /** Reports a phase of the running compile. */
  phase(phase: "downloading" | "typesetting" | "bibliography" | "finalizing"): void;
  /** Ends the running compile with this result (defaults to a success with revision `rev`) and starts the queued one, if any. */
  finish(result?: Partial<CompileResult>): void;
}

export interface FakeApi {
  api: ApiClient;
  /** One line per request, such as `createEntry a.tex file`. */
  calls: string[];
  state: { files: FileEntry[]; settings: Settings };
  /** Makes the next request fail with this error. */
  failNext(error: ApiError): void;
  /** Makes every request fail until `recover` is called. */
  failAll(error: ApiError): void;
  recover(): void;
  /** Changes a file the way another program would: new text and a new hash, without any event. */
  changeOnDisk(path: string, content: string): string;
  /** Removes a file the way another program would: no event, no tree change in the fake's own listing until `listFiles`. */
  removeFromDisk(path: string): void;
  /** The text and hash currently on the fake disk, or undefined. */
  disk(path: string): { content: string; hash: string } | undefined;
  /** Delivers a server event to every subscriber. */
  emit(event: ServerEvent): void;
  /** How many listeners are subscribed right now. */
  subscribers(): number;
  compile: FakeCompile;
  chat: FakeChat;
  /** The browser sign-in: what `followLogin` answers next. Tests change `view` to move it on. */
  login: { view: LoginView | null; methods: LoginMethod[] };
}

export const DEFAULT_SETTINGS: Settings = {
  stopOnFirstError: false,
  autoCompile: true,
  sandboxedCompile: false,
  mainFile: null,
  disclosureAcknowledged: true,
};

export function apiError(code: string, message: string, status = 400, path?: string): ApiError {
  return new ApiError({ status, code, message, path });
}

/** An in-memory API for component tests: it keeps the project files and settings and records every call. */
export function createFakeApi(init: FakeApiInit = {}): FakeApi {
  const state = { files: [...(init.files ?? [])], settings: { ...DEFAULT_SETTINGS, ...init.settings } };
  const contents = { ...init.contents };
  const revisions: Record<string, number> = {};
  // A hash belongs to the content, so it survives a rename.
  const hashes: Record<string, string> = {};
  const hashOf = (path: string) => (hashes[path] ??= `sha256:${path}#0`);
  const touch = (path: string) => {
    revisions[path] = (revisions[path] ?? 0) + 1;
    hashes[path] = `sha256:${path}#${revisions[path]}`;
  };
  const calls: string[] = [];
  let next: ApiError | null = null;
  let always: ApiError | null = null;
  const listeners = new Set<(event: ServerEvent) => void>();
  let eventId = 0;
  const publish = (event: string, data: unknown) => {
    eventId += 1;
    listeners.forEach((listener) => listener({ id: eventId, event, data }));
  };
  let compileCount = 0;
  const compile: FakeCompile = {
    status: { running: null, queued: null, last: null, pdfAvailable: init.pdf !== undefined },
    pdf: init.pdf ?? null,
    log: null,
    starts: 0,
    phase: (phase) => publish("compile.phase", { phase }),
    finish(result = {}) {
      const running = compile.status.running;
      if (running === null) return;
      const full: CompileResult = { status: "success", pdfRev: String(compileCount), diagnostics: [], durationMs: 10, logAvailable: true, ...result };
      compile.status = { ...compile.status, running: null, last: { compileId: running.compileId, result: full } };
      if (full.pdfRev !== null) compile.status.pdfAvailable = true;
      publish("compile.finished", { compileId: running.compileId, result: full });
      const queued = compile.status.queued;
      if (queued !== null) {
        compile.status = { ...compile.status, queued: null, running: queued };
        publish("compile.started", { compileId: queued.compileId });
      }
    },
  };

  const info = (id: ProviderId, patch: Partial<ProviderInfo> = {}): ProviderInfo => ({
    id,
    installed: id === "claude",
    ...(id === "claude" ? {} : { unavailableReason: `Support for ${id} is not available yet.` }),
    requiresModel: id === "opencode",
    model: null,
    ...patch,
  });
  const listing: ProvidersListing = init.providers ?? { selected: "claude", providers: [info("claude"), info("opencode"), info("codex")] };
  /** Records a key's status in every provider that lists the slot, and whether the active slot has a key. */
  const setKey = (slot: string, status: KeyStatus) => {
    listing.providers = listing.providers.map((candidate) =>
      candidate.auth === undefined || !candidate.auth.keys.some((key) => key.slot === slot)
        ? candidate
        : {
            ...candidate,
            auth: {
              ...candidate.auth,
              keys: candidate.auth.keys.map((key) => (key.slot === slot ? status : key)),
              apiReady: candidate.auth.slot === slot ? status.set : candidate.auth.apiReady,
            },
          },
    );
  };
  type Connection = { send(event: TurnEvent, seq: number): void; close(): void; fail(error: ApiError): void };
  let connection: Connection | null = null;
  let turnLog: Array<{ event: TurnEvent; seq: number }> = [];
  let turnCount = 0;
  let refusal: ApiError | null = null;
  const chat: FakeChat = {
    listing,
    history: {},
    starts: [],
    stopped: [],
    rechecks: 0,
    undos: [],
    nextUndo: null,
    replaced: [],
    savedKeys: [],
    follows: [],
    connections: () => (connection === null ? 0 : 1),
    refuseNext: (error) => void (refusal = error),
    emit(event) {
      const entry = { event, seq: turnLog.length + 1 };
      turnLog.push(entry);
      connection?.send(event, entry.seq);
    },
    begin(turnId = `t${turnCount}`) {
      chat.emit({ type: "turn_started", turnId, provider: listing.selected ?? "claude", snapshotPartial: false, unprotected: [] });
    },
    end() {
      connection?.close();
      connection = null;
    },
    drop() {
      connection?.fail(new ApiError({ status: 0, code: "network", message: "The connection to Caztor was interrupted." }));
      connection = null;
    },
  };

  function connect(replay: Array<{ event: TurnEvent; seq: number }>, onEvent: (event: TurnEvent, seq: number | null) => void, signal: AbortSignal, onOpen?: () => void): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      onOpen?.();
      for (const entry of replay) onEvent(entry.event, entry.seq);
      if (replay.some((entry) => entry.event.type === "done")) return resolve();
      connection = {
        send: (event, seq) => onEvent(event, seq),
        close: resolve,
        fail: reject,
      };
      signal.addEventListener("abort", () => {
        connection = null;
        reject(new DOMException("aborted", "AbortError"));
      });
    });
  }

  async function begin(call: string): Promise<void> {
    calls.push(call);
    const failure = next ?? always;
    next = null;
    if (failure !== null) throw failure;
  }

  const find = (path: string) => state.files.find((entry) => entry.path === path);
  const missing = (path: string) => apiError("not_found", `"${path}" was not found.`, 404, path);
  const exists = (path: string) => apiError("exists", `"${path}" already exists. Choose another name.`, 409, path);

  let collaborators = [...(init.collaborators ?? [])];
  let invites = 0;

  const login: FakeApi["login"] = { view: null, methods: [{ id: "default", label: "Account" }] };

  const api: ApiClient = {
    async listCollaborators() {
      await begin("listCollaborators");
      return collaborators.map((entry) => structuredClone(entry));
    },
    async inviteCollaborator(name, minutes) {
      await begin(`inviteCollaborator ${name} ${minutes}`);
      if (init.inviteError !== undefined) throw apiError("not_exposed", init.inviteError, 409);
      invites += 1;
      let user = collaborators.find((entry) => entry.name === name);
      if (user === undefined) {
        user = { id: `u${invites}`, name, role: "collaborator", createdAt: 0, sessions: 0, invites: [] };
        collaborators.push(user);
      }
      const now = init.now ?? 0;
      const inviteId = `invite${invites}`;
      const expiresAt = now + minutes * 60_000;
      user.invites.push({ id: inviteId, createdAt: now, expiresAt, status: "active", failures: 0, sessions: 0 });
      return { user: structuredClone(user), link: `https://box.ts.net/invite/${inviteId}`, key: `ABCDE-FGH23-JKMNP-QRST${invites}`, inviteId, expiresAt };
    },
    async revokeCollaboratorKey(id) {
      await begin(`revokeCollaboratorKey ${id}`);
      for (const person of collaborators) person.invites = person.invites.filter((entry) => entry.id !== id);
    },
    async revokeCollaborator(id) {
      await begin(`revokeCollaborator ${id}`);
      collaborators = collaborators.filter((entry) => entry.id !== id);
    },
    listProjects: async () => (calls.push("listProjects"), init.projects ?? []),
    async scaffoldPaper() {
      calls.push("scaffoldPaper");
      if (init.papersmith !== undefined) init.papersmith = { ...init.papersmith, exists: true };
      contents["paper/main.tex"] = "";
      state.files = [...state.files.filter((entry) => entry.path !== "paper/main.tex"), { path: "paper/main.tex" as RelPath, kind: "file", size: 0 }];
      return { created: ["main.tex"] };
    },
    async createProject(name) {
      calls.push(`createProject ${name}`);
      return init.projects ?? [];
    },
    async openProject(path) {
      calls.push(`openProject ${path}`);
      if (init.openProjectError !== undefined) throw apiError("turn_running", init.openProjectError, 409);
      return init.projects ?? [];
    },
    async getSession(): Promise<Session> {
      await begin("getSession");
      return {
        ...(init.user === undefined ? {} : { user: { ...init.user } }),
        project: { name: init.projectName ?? "thesis" },
        ...(init.papersmith === undefined ? {} : { papersmith: { ...init.papersmith } }),
        ...(init.embed === undefined ? {} : { embed: { ...init.embed } }),
        engine: init.engineAvailable === false ? { available: false, ...(init.engineReason === undefined ? {} : { reason: init.engineReason }) } : { available: true, version: "0.17.0" },
        sandbox: { available: false },
        settings: { ...state.settings },
      };
    },
    async patchSettings(patch) {
      await begin(`patchSettings ${JSON.stringify(patch)}`);
      state.settings = { ...state.settings, ...patch };
      return { ...state.settings };
    },
    async listFiles() {
      await begin("listFiles");
      return state.files.map((entry) => ({ ...entry }));
    },
    async readFile(path) {
      await begin(`readFile ${path}`);
      if (find(path) === undefined) throw missing(path);
      return { path, content: contents[path] ?? "", hash: hashOf(path) };
    },
    async writeFile(path, content, baseHash) {
      await begin(`writeFile ${path} ${baseHash ?? "null"}`);
      const entry = find(path);
      if (entry === undefined && baseHash !== null) throw missing(path);
      if (entry !== undefined && baseHash === null) throw exists(path);
      if (entry !== undefined && baseHash !== hashOf(path)) {
        throw new ApiError({ status: 409, code: "conflict", message: `"${path}" changed on disk since it was opened.`, path, currentHash: hashOf(path) });
      }
      if (entry === undefined) state.files.push({ path: path as RelPath, kind: "file", size: content.length });
      contents[path] = content;
      touch(path);
      return { hash: hashOf(path) };
    },
    async createEntry(path, kind) {
      await begin(`createEntry ${path} ${kind}`);
      if (find(path) !== undefined) throw exists(path);
      state.files.push({ path: path as RelPath, kind, size: 0 });
    },
    async renameEntry(from, to) {
      await begin(`renameEntry ${from} ${to}`);
      const entry = find(from);
      if (entry === undefined) throw missing(from);
      if (find(to) !== undefined) throw exists(to);
      for (const path of Object.keys(contents)) {
        if (path === from || path.startsWith(`${from}/`)) {
          const moved = `${to}${path.slice(from.length)}`;
          contents[moved] = contents[path] ?? "";
          revisions[moved] = revisions[path] ?? 0;
          hashes[moved] = hashOf(path);
          delete contents[path];
          delete revisions[path];
          delete hashes[path];
        }
      }
      state.files = state.files.map((file) =>
        file.path === from
          ? { ...file, path: to as RelPath }
          : file.path.startsWith(`${from}/`)
            ? { ...file, path: `${to}${file.path.slice(from.length)}` as RelPath }
            : file,
      );
    },
    async deleteEntry(path, { recursive }) {
      await begin(`deleteEntry ${path} ${recursive ? "recursive" : "plain"}`);
      const entry = find(path);
      if (entry === undefined) throw missing(path);
      const hasContent = state.files.some((file) => file.path.startsWith(`${path}/`));
      if (entry.kind === "dir" && hasContent && !recursive) {
        throw apiError("not_empty", `"${path}" is a folder with content. Confirm to delete it with everything inside.`, 409, path);
      }
      state.files = state.files.filter((file) => file.path !== path && !file.path.startsWith(`${path}/`));
    },
    async uploadFile(path, bytes) {
      await begin(`uploadFile ${path} ${bytes.length}`);
      if (find(path) !== undefined) throw exists(path);
      state.files.push({ path: path as RelPath, kind: "file", size: bytes.length });
    },
    async startCompile(main) {
      await begin(main === undefined ? "startCompile" : `startCompile ${main}`);
      if (init.engineAvailable === false) throw apiError("engine_unavailable", "The LaTeX engine (Tectonic) was not found.", 503);
      compile.starts += 1;
      compileCount += 1;
      const compileId = `c${compileCount}`;
      if (compile.status.running !== null) {
        compile.status = { ...compile.status, queued: { compileId } };
        return { compileId, queued: true };
      }
      compile.status = { ...compile.status, running: { compileId } };
      publish("compile.started", { compileId });
      return { compileId, queued: false };
    },
    async cancelCompile() {
      await begin("cancelCompile");
      if (compile.status.running === null) return { cancelled: false };
      compile.status = { ...compile.status, queued: null };
      compile.finish({ status: "cancelled", pdfRev: null, logAvailable: false });
      return { cancelled: true };
    },
    async getCompileStatus() {
      await begin("getCompileStatus");
      return structuredClone(compile.status);
    },
    async readPdf(rev) {
      await begin(`readPdf ${rev}`);
      if (compile.pdf === null) throw apiError("no_pdf", "No PDF has been produced yet. Compile the project first.", 404);
      return compile.pdf;
    },
    async readLog() {
      await begin("readLog");
      if (compile.log === null) throw apiError("no_log", "There is no compile log yet.", 404);
      return compile.log;
    },
    async listAgents() {
      await begin("listAgents");
      return structuredClone(init.agents ?? []);
    },
    async listProviders() {
      await begin("listProviders");
      return structuredClone(listing);
    },
    async chatHistory(provider) {
      await begin(`chatHistory ${provider}`);
      return structuredClone(chat.history[provider] ?? { provider, turns: [], undoableTurnId: null, undoProblem: null, running: false, currentTurnId: null });
    },
    async recheckProviders() {
      await begin("recheckProviders");
      chat.rechecks += 1;
      return structuredClone(listing);
    },
    async selectProvider(provider) {
      await begin(`selectProvider ${provider}`);
      listing.selected = provider;
      return structuredClone(listing);
    },
    async trustProjectConfig(provider, fingerprint) {
      await begin(`trustProjectConfig ${provider} ${fingerprint}`);
      listing.providers = listing.providers.map((candidate) =>
        candidate.id === provider && candidate.projectConfig !== undefined && candidate.projectConfig.fingerprint === fingerprint
          ? { ...candidate, projectConfig: { ...candidate.projectConfig, confirmed: true } }
          : candidate,
      );
      return structuredClone(listing);
    },
    async setProviderModel(provider, model) {
      await begin(`setProviderModel ${provider} ${model ?? "null"}`);
      listing.providers = listing.providers.map((candidate) => (candidate.id === provider ? { ...candidate, model } : candidate));
      return structuredClone(listing);
    },
    async setAuthMode(provider, mode) {
      await begin(`setAuthMode ${provider} ${mode}`);
      const target = listing.providers.find((candidate) => candidate.id === provider);
      if (mode === "api" && target?.auth?.apiReady !== true) throw apiError("api_key_missing", `No API key is stored for ${provider}. Add one first, then switch.`, 409);
      listing.providers = listing.providers.map((candidate) => (candidate.id === provider && candidate.auth !== undefined ? { ...candidate, auth: { ...candidate.auth, mode } } : candidate));
      return structuredClone(listing);
    },
    async saveCredential(slot, key) {
      await begin(`saveCredential ${slot}`);
      chat.savedKeys.push({ slot, key });
      const status: KeyStatus = { slot, set: true, ...(key.length >= 12 ? { last4: key.slice(-4) } : {}) };
      setKey(slot, status);
      return status;
    },
    async startLogin(provider, method) {
      await begin(`startLogin ${provider}${method === undefined ? "" : ` ${method}`}`);
      login.view = { provider, method: method ?? login.methods[0]?.id ?? "default", state: "running", text: "", terminal: false };
      return { login: { ...login.view }, methods: [...login.methods] };
    },
    async followLogin(provider) {
      calls.push(`followLogin ${provider}`);
      return { login: login.view === null ? null : { ...login.view }, methods: [...login.methods] };
    },
    async sendLogin(provider, input) {
      await begin(`sendLogin ${provider} ${"line" in input ? `line:${input.line}` : `key:${input.key}`}`);
      if (login.view === null) throw apiError("not_found", "There is no sign-in of yours to this provider.", 404);
      return { ...login.view };
    },
    async cancelLogin(provider) {
      await begin(`cancelLogin ${provider}`);
      if (login.view !== null) login.view = { ...login.view, state: "cancelled" };
    },
    async deleteCredential(slot) {
      await begin(`deleteCredential ${slot}`);
      const status: KeyStatus = { slot, set: false };
      setKey(slot, status);
      return status;
    },
    async resetChat(provider) {
      await begin(`resetChat ${provider}`);
      chat.history[provider] = { provider, turns: [], undoableTurnId: null, undoProblem: null, running: false, currentTurnId: null };
    },
    async undoTurn(turnId, mode) {
      await begin(`undoTurn ${turnId} ${mode}`);
      chat.undos.push({ turnId, mode });
      const outcome = chat.nextUndo ?? { files: [], skipped: [] };
      if (outcome instanceof ApiError) {
        chat.nextUndo = null;
        throw outcome;
      }
      chat.nextUndo = null;
      return outcome;
    },
    async replaceDefinition(provider) {
      await begin(`replaceDefinition ${provider}`);
      chat.replaced.push(provider);
    },
    async streamTurn(request, onEvent, signal, onOpen) {
      if (request.kind === "follow") {
        calls.push(`streamTurn follow ${request.after}`);
        chat.follows.push(request.after);
        if (always !== null) throw always;
        if (turnLog.length === 0) throw apiError("no_turn", "There is no turn to follow yet.", 404);
        return connect(turnLog.filter((entry) => entry.seq > request.after), onEvent, signal, onOpen);
      }
      calls.push(`streamTurn start ${request.provider}`);
      if (always !== null) throw always;
      if (refusal !== null) {
        const failure = refusal;
        refusal = null;
        throw failure;
      }
      chat.starts.push({ provider: request.provider, prompt: request.prompt });
      turnCount += 1;
      turnLog = [];
      return connect([], onEvent, signal, onOpen);
    },
    async stopTurn(turnId) {
      await begin(`stopTurn ${turnId}`);
      chat.stopped.push(turnId);
    },
    subscribeEvents(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
  };

  return {
    api,
    calls,
    state,
    failNext: (error) => void (next = error),
    failAll: (error) => void (always = error),
    recover: () => void (always = null),
    changeOnDisk(path, content) {
      contents[path] = content;
      touch(path);
      return hashOf(path);
    },
    removeFromDisk(path) {
      delete contents[path];
      state.files = state.files.filter((entry) => entry.path !== path);
    },
    disk: (path) => (path in contents ? { content: contents[path] ?? "", hash: hashOf(path) } : undefined),
    emit: (event) => listeners.forEach((listener) => listener(event)),
    subscribers: () => listeners.size,
    compile,
    chat,
    login,
  };
}
