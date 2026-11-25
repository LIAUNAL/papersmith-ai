import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { createProjectStore, createStateStore, nodeFileSystem, systemClock, createUserWriteLog, type FileSystem } from "@caztor/adapters-local";
import { createApp, createEventHub, type ApiDeps } from "@caztor/api";
import type { CredentialStorePort, GuideSourcePort, ProviderId } from "@caztor/core";
import { afterEach } from "vitest";
import { createAgentServices } from "../../src/agents.ts";
import { createFakeRunner, type FakeAgentRunner } from "../support/fake-runner.ts";
import { HOST, ORIGIN, TOKEN } from "./support.ts";

const dirs: string[] = [];

/** Call once at the top of a chat route test file. */
export function cleanupChatProjects(): void {
  afterEach(() => {
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });
}

/** One parsed Server-Sent Events frame. */
export interface Frame {
  id: number;
  event: string;
  data: Record<string, unknown>;
}

export function parseFrames(text: string): Frame[] {
  return text
    .split("\n\n")
    .filter((block) => block.includes("event: "))
    .map((block) => {
      const field = (name: string) => block.split("\n").find((line) => line.startsWith(`${name}: `))?.slice(name.length + 2) ?? "";
      return { id: Number(field("id")), event: field("event"), data: JSON.parse(field("data")) as Record<string, unknown> };
    });
}

export interface ChatHarness {
  root: string;
  deps: ApiDeps;
  /** The project store the file API uses, for a save made as the user. */
  store: ReturnType<typeof createProjectStore>;
  runners: Record<"claude" | "opencode", FakeAgentRunner>;
  call(method: string, path: string, init?: { body?: unknown; headers?: Record<string, string> }): Promise<Response>;
  /** Sends a message and reads the whole stream of the turn. */
  sendMessage(prompt: string, provider?: ProviderId): Promise<{ response: Response; frames: Frame[] }>;
}

/** The real app over a real project folder with the real snapshot store, provisioner, history and turn service; only the agent CLIs are fake. */
export function chatHarness(options: { claude?: boolean; opencode?: boolean; /** A different guide source, tried before the built-in one. */ guides?: GuideSourcePort; /** Replaces the built-in guide source. */ builtInGuides?: GuideSourcePort; /** Wraps the file system of the file API's store only, to hold a save at a chosen step. */ wrapStoreFs?: (fs: FileSystem) => FileSystem; /** The credential store of the server; without it the credential routes are off and api mode cannot start a turn. */ credentials?: CredentialStorePort } = {}): ChatHarness {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-chat-")));
  dirs.push(root);
  const claude = createFakeRunner(root, "claude");
  const opencode = createFakeRunner(root, "opencode");
  opencode.status = { provider: "opencode", installed: true, requiresModel: true, version: "1.19.0" };
  const userWrites = createUserWriteLog();
  const state = createStateStore({ fs: nodeFileSystem, root });
  const store = createProjectStore({
    fs: options.wrapStoreFs === undefined ? nodeFileSystem : options.wrapStoreFs(nodeFileSystem),
    root,
    userWrites,
    agentsMdCreatedByCaztor: async () => (await state.load()).provisioned["AGENTS.md"]?.createdByCaztor === true,
  });
  const agents = createAgentServices({
    fs: nodeFileSystem,
    root,
    store,
    state,
    clock: systemClock,
    userWrites,
    ...(options.credentials === undefined ? {} : { credentials: options.credentials }),
    ...(options.guides === undefined ? {} : { guides: options.guides }),
    ...(options.builtInGuides === undefined ? {} : { builtInGuides: options.builtInGuides }),
    runners: { ...(options.claude === false ? {} : { claude }), ...(options.opencode === false ? {} : { opencode }) },
  });
  const deps: ApiDeps = { projectName: basename(root), store, state, events: createEventHub(), clock: systemClock, agents, ...(options.credentials === undefined ? {} : { credentials: options.credentials }) };
  const app = createApp(deps, { token: TOKEN, allowedHosts: [HOST], allowedOrigins: [ORIGIN] });
  const base: Record<string, string> = { host: HOST, "x-caztor-token": TOKEN };
  const call: ChatHarness["call"] = (method, path, init = {}) => {
    const headers: Record<string, string> = { ...base, ...init.headers };
    if (method !== "GET") Object.assign(headers, { origin: ORIGIN, "content-type": "application/json" }, init.headers);
    const body = init.body === undefined ? undefined : typeof init.body === "string" ? init.body : JSON.stringify(init.body);
    return Promise.resolve(app.request(path, { method, headers, ...(body === undefined ? {} : { body }) }));
  };
  return {
    root,
    deps,
    store,
    runners: { claude, opencode },
    call,
    async sendMessage(prompt, provider = "claude") {
      const response = await call("POST", "/api/chat/turns", { body: { provider, prompt } });
      return { response, frames: parseFrames(await response.text()) };
    },
  };
}
