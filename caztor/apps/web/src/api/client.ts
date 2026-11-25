import { createSseParser } from "./sse-parser.ts";
import type { ApiClient, Collaborator, CollaboratorInvite, ProjectEntry, ChatHistory, FileContent, FileEntry, KeyStatus, LoginListing, LoginView, ProvidersListing, ServerEvent, Session, Settings, TurnEvent, TurnStreamRequest, UndoConflict, UndoMode, UndoOutcome } from "./types.ts";

export const TOKEN_HEADER = "X-Caztor-Token";

/** A failed request: the stable code and readable message of the API's error body, or a generic one. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly path: string | undefined;
  readonly currentHash: string | null | undefined;
  /** The files an undo was refused for, when the error is `undo_conflict`. */
  readonly conflicts: UndoConflict[] | undefined;

  constructor(init: { status: number; code: string; message: string; path?: string | undefined; currentHash?: string | null | undefined; conflicts?: UndoConflict[] | undefined }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.path = init.path;
    this.currentHash = init.currentHash;
    this.conflicts = init.conflicts;
  }
}

const PROJECT_HEADER = "X-Caztor-Project";

export interface ApiClientOptions {
  token: string;
  fetch?: typeof fetch;
  /** Pause between reconnection attempts. Tests replace it. */
  wait?: (ms: number) => Promise<void>;
  /** The server moved to another project, so this page must start again. */
  onProjectChanged?: () => void;
  /** The server refused the launch token: it restarted with a new one, so this page must load again to get it. */
  onTokenRejected?: () => void;
}

const FIRST_RETRY_MS = 1000;
const LONGEST_RETRY_MS = 10_000;

const TURN_EVENT_TYPES: ReadonlySet<string> = new Set([
  "session", "text_delta", "text", "tool_start", "tool_update", "tool_end", "notice", "error", "done", "turn_started", "files_changed",
]);

/** A turn event from the stream, or null when the data is not one (an unknown event is ignored, never fatal). */
function toTurnEvent(data: unknown): TurnEvent | null {
  return isRecord(data) && typeof data["type"] === "string" && TURN_EVENT_TYPES.has(data["type"]) ? (data as unknown as TurnEvent) : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function toApiError(response: Response): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null);
  if (isRecord(body) && typeof body["error"] === "string" && typeof body["message"] === "string") {
    return new ApiError({
      status: response.status,
      code: body["error"],
      message: body["message"],
      path: typeof body["path"] === "string" ? body["path"] : undefined,
      currentHash: typeof body["currentHash"] === "string" || body["currentHash"] === null ? body["currentHash"] : undefined,
      conflicts: Array.isArray(body["conflicts"]) ? (body["conflicts"] as UndoConflict[]) : undefined,
    });
  }
  return new ApiError({
    status: response.status,
    code: "http_error",
    message: `The server answered with an unexpected error (${response.status}).`,
  });
}

/** The typed client for the local API. Every request carries the launch token; state-changing ones declare their content type. */
export function createApiClient(options: ApiClientOptions): ApiClient {
  const doFetch = options.fetch ?? ((...args: Parameters<typeof fetch>) => fetch(...args));

  /** The project this page opened: a request for it is refused once the server has moved, so it cannot land in another project. */
  let projectId: string | undefined;

  async function send(method: string, url: string, body?: { type: string; data: BodyInit }): Promise<Response> {
    const headers: Record<string, string> = { [TOKEN_HEADER]: options.token, ...(projectId === undefined ? {} : { [PROJECT_HEADER]: projectId }) };
    // The server requires a content type on every non-GET request, DELETE included.
    if (method !== "GET") headers["Content-Type"] = body?.type ?? "application/json";
    let response: Response;
    try {
      const init: RequestInit = { method, headers };
      if (body !== undefined) init.body = body.data;
      response = await doFetch(url, init);
    } catch {
      throw new ApiError({ status: 0, code: "network", message: "Cannot reach the Caztor server. Check that it is still running." });
    }
    if (!response.ok) {
      if (response.status === 401) options.onTokenRejected?.();
      const error = await toApiError(response);
      if (error.code === "project_changed") options.onProjectChanged?.();
      throw error;
    }
    return response;
  }

  async function request<T>(method: string, url: string, body?: { type: string; data: BodyInit }): Promise<T> {
    return (await (await send(method, url, body)).json()) as T;
  }

  const wait = options.wait ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));

  /** Reads the event stream until `signal` aborts, reconnecting with a growing pause after any failure. */
  async function follow(listener: (event: ServerEvent) => void, signal: AbortSignal): Promise<void> {
    let pause = FIRST_RETRY_MS;
    let attempts = 0;
    while (!signal.aborted) {
      try {
        const response = await doFetch("/api/events", { headers: { [TOKEN_HEADER]: options.token, Accept: "text/event-stream" }, signal });
        if (response.status === 401) options.onTokenRejected?.();
        if (!response.ok || response.body === null) throw new Error(`event stream refused (${response.status})`);
        if (attempts > 0) listener({ id: null, event: "stream_resumed", data: null });
        pause = FIRST_RETRY_MS;
        const parser = createSseParser(listener);
        const decoder = new TextDecoder();
        const reader = response.body.getReader();
        for (;;) {
          const chunk = await reader.read();
          if (chunk.done) break;
          parser.feed(decoder.decode(chunk.value, { stream: true }));
        }
      } catch {
        // Aborted, unreachable or refused: fall through to the pause below.
      }
      attempts += 1;
      if (signal.aborted) return;
      await wait(pause);
      pause = Math.min(pause * 2, LONGEST_RETRY_MS);
    }
  }

  async function streamTurn(request: TurnStreamRequest, onEvent: (event: TurnEvent, seq: number | null) => void, signal: AbortSignal, onOpen?: () => void): Promise<void> {
    const headers: Record<string, string> = { [TOKEN_HEADER]: options.token, ...(projectId === undefined ? {} : { [PROJECT_HEADER]: projectId }), Accept: "text/event-stream" };
    const init: RequestInit = { headers, signal };
    let url = "/api/chat/turns/current";
    if (request.kind === "start") {
      url = "/api/chat/turns";
      init.method = "POST";
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify({ provider: request.provider, prompt: request.prompt });
    } else if (request.after > 0) {
      headers["Last-Event-ID"] = String(request.after);
    }
    const lost = () => new ApiError({ status: 0, code: "network", message: "The connection to Caztor was interrupted." });
    let response: Response;
    try {
      response = await doFetch(url, init);
    } catch (error) {
      if (signal.aborted) throw error;
      throw lost();
    }
    if (response.status === 401) options.onTokenRejected?.();
    if (!response.ok) throw await toApiError(response);
    if (response.body === null) throw lost();
    onOpen?.();
    const parser = createSseParser((event) => {
      const turnEvent = toTurnEvent(event.data);
      if (turnEvent !== null) onEvent(turnEvent, event.id);
    });
    const decoder = new TextDecoder();
    const reader = response.body.getReader();
    try {
      for (;;) {
        const chunk = await reader.read();
        if (chunk.done) return;
        parser.feed(decoder.decode(chunk.value, { stream: true }));
      }
    } catch (error) {
      if (signal.aborted) throw error;
      throw lost();
    }
  }

  const subscribers = new Set<(event: ServerEvent) => void>();
  let stream: AbortController | null = null;

  const json = (value: unknown) => ({ type: "application/json", data: JSON.stringify(value) });
  const query = (params: Record<string, string>) => new URLSearchParams(params).toString().replaceAll("+", "%20");

  return {
    getSession: async () => {
      const session = await request<Session>("GET", "/api/session");
      projectId = session.project.id;
      return session;
    },
    listCollaborators: async () => (await request<{ users: Collaborator[] }>("GET", "/api/users")).users,
    inviteCollaborator: (name, minutes) => request<CollaboratorInvite>("POST", "/api/users/invites", json({ name, minutes })),
    async revokeCollaboratorKey(id) {
      await request("DELETE", `/api/users/invites/${encodeURIComponent(id)}`);
    },
    async revokeCollaborator(id) {
      await request("DELETE", `/api/users/${encodeURIComponent(id)}`);
    },
    listProjects: async () => (await request<{ projects: ProjectEntry[] }>("GET", "/api/projects")).projects,
    scaffoldPaper: () => request<{ created: string[] }>("POST", "/api/papersmith/scaffold", json({})),
    createProject: async (name) => (await request<{ projects: ProjectEntry[] }>("POST", "/api/projects/create", json({ name }))).projects,
    openProject: async (path) => (await request<{ projects: ProjectEntry[] }>("POST", "/api/projects/open", json({ path }))).projects,
    patchSettings: async (patch) => (await request<{ settings: Settings }>("PATCH", "/api/settings", json(patch))).settings,
    listFiles: async () => (await request<{ entries: FileEntry[] }>("GET", "/api/files")).entries,
    readFile: (path) => request<FileContent>("GET", `/api/files/content?${query({ path })}`),
    async writeFile(path, content, baseHash) {
      const saved = await request<{ hash: string }>("PUT", `/api/files/content?${query({ path })}`, json({ content, baseHash }));
      return { hash: saved.hash };
    },
    async createEntry(path, kind) {
      await request("POST", "/api/files", json({ path, kind }));
    },
    async renameEntry(from, to) {
      await request("POST", "/api/files/rename", json({ from, to }));
    },
    async deleteEntry(path, { recursive }) {
      await request("DELETE", `/api/files?${query(recursive ? { path, recursive: "true" } : { path })}`);
    },
    async uploadFile(path, bytes) {
      await request("POST", `/api/files/upload?${query({ path })}`, { type: "application/octet-stream", data: bytes as Uint8Array<ArrayBuffer> });
    },
    startCompile: (main) => request("POST", "/api/compile", main === undefined ? undefined : json({ main })),
    cancelCompile: () => request("POST", "/api/compile/cancel"),
    getCompileStatus: () => request("GET", "/api/compile/status"),
    async readPdf(rev) {
      return new Uint8Array(await (await send("GET", `/api/compile/pdf?${query({ rev })}`)).arrayBuffer());
    },
    async readLog() {
      return (await send("GET", "/api/compile/log")).text();
    },
    listProviders: () => request<ProvidersListing>("GET", "/api/providers"),
    chatHistory: (provider) => request<ChatHistory>("GET", `/api/chat/history?${query({ provider })}`),
    listAgents: async () => (await request<{ agents: Array<{ name: string; description: string }> }>("GET", "/api/chat/agents")).agents,
    recheckProviders: () => request<ProvidersListing>("POST", "/api/providers/recheck", json({})),
    selectProvider: (provider) => request<ProvidersListing>("PUT", "/api/providers/selected", json({ provider })),
    trustProjectConfig: (provider, fingerprint) =>
      request<ProvidersListing>("POST", `/api/providers/${encodeURIComponent(provider)}/project-config/trust`, json({ fingerprint })),
    setProviderModel: (provider, model) => request<ProvidersListing>("PUT", `/api/providers/${encodeURIComponent(provider)}/model`, json({ model })),
    setAuthMode: (provider, mode) => request<ProvidersListing>("PUT", `/api/providers/${encodeURIComponent(provider)}/auth-mode`, json({ mode })),
    saveCredential: (slot, key) => request<KeyStatus>("PUT", `/api/credentials/${encodeURIComponent(slot)}`, json({ key })),
    deleteCredential: (slot) => request<KeyStatus>("DELETE", `/api/credentials/${encodeURIComponent(slot)}`),
    startLogin: (provider, method) => request<LoginListing>("POST", `/api/logins/${encodeURIComponent(provider)}`, json(method === undefined ? {} : { method })),
    followLogin: (provider) => request<LoginListing>("GET", `/api/logins/${encodeURIComponent(provider)}`),
    async sendLogin(provider, input) {
      return (await request<{ login: LoginView }>("POST", `/api/logins/${encodeURIComponent(provider)}/input`, json(input))).login;
    },
    async cancelLogin(provider) {
      await request("DELETE", `/api/logins/${encodeURIComponent(provider)}`);
    },
    async resetChat(provider) {
      await request("POST", "/api/chat/sessions/reset", json({ provider }));
    },
    async undoTurn(turnId, mode) {
      const done = await request<{ files: string[]; skipped: string[] }>("POST", `/api/chat/turns/${encodeURIComponent(turnId)}/undo`, json({ mode }));
      return { files: done.files, skipped: done.skipped };
    },
    async replaceDefinition(provider) {
      await request("POST", "/api/chat/definition/replace", json({ provider }));
    },
    streamTurn,
    async stopTurn(turnId) {
      await request("POST", `/api/chat/turns/${encodeURIComponent(turnId)}/stop`, json({}));
    },
    subscribeEvents(listener) {
      // One connection serves every subscriber: it opens with the first and closes with the last.
      subscribers.add(listener);
      if (stream === null) {
        stream = new AbortController();
        void follow((event) => {
          for (const subscriber of [...subscribers]) {
            try {
              subscriber(event);
            } catch {
              // One failing subscriber must not stop the others or the stream.
            }
          }
        }, stream.signal);
      }
      return () => {
        if (!subscribers.delete(listener) || subscribers.size > 0) return;
        stream?.abort();
        stream = null;
      };
    },
  };
}
