import { existsSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem, userChatFolder } from "@caztor/adapters-local";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FetchHandler, Listener, ListenFn } from "../src/listen.ts";
import { startServer } from "../src/server.ts";
import { parseFrames } from "./routes/chat-support.ts";
import { createFakeRunner } from "./support/fake-runner.ts";

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));
const PUBLIC = "box.tail1234.ts.net";
const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

interface Call {
  method?: string;
  body?: unknown;
}

async function boot(again?: { home: string }) {
  const home = again?.home ?? realpathSync(mkdtempSync(join(tmpdir(), "caztor-people-")));
  if (again === undefined) dirs.push(home);
  const project = join(home, "papers", "paper");
  await nodeFileSystem.mkdir(project, { recursive: true });
  if (again === undefined) writeFileSync(join(project, "main.tex"), "x");
  const claude = createFakeRunner(project, "claude");
  claude.status = { ...claude.status, models: ["m-host", "m-ana", "m-bo"] };
  claude.script = async function* ({ req }) {
    yield { type: "session", sessionId: `session-${req.model ?? "none"}` };
    yield { type: "text", messageId: "m", text: `answer to ${req.prompt}` };
    yield { type: "done", reason: "completed" };
  };
  let fetch!: FetchHandler;
  const listen: ListenFn = async (options) => {
    fetch = options.fetch;
    return { port: options.port, close: async () => {} } satisfies Listener;
  };
  const env = { PATH: "/usr/bin", HOME: home, TMPDIR: tmpdir(), DBUS_SESSION_BUS_ADDRESS: "unix:path=/run/bus", CLAUDE_CODE_OAUTH_TOKEN: "host-oauth" };
  const server = await startServer({ projectDir: project, webRoot, env, fs: nodeFileSystem, listen, watcher: { watch: () => () => {} }, runners: { claude }, publicNames: [PUBLIC] });
  const send = (path: string, headers: Record<string, string>, call: Call = {}) => {
    const method = call.method ?? "GET";
    const all: Record<string, string> = { host: PUBLIC, ...headers };
    if (method !== "GET") Object.assign(all, { origin: `http://${PUBLIC}`, "content-type": "application/json" });
    return fetch(new Request(`http://${PUBLIC}${path}`, { method, headers: all, ...(call.body === undefined ? {} : { body: JSON.stringify(call.body) }) }));
  };
  const host = (path: string, call?: Call) => send(path, { "x-caztor-token": server.token }, call);
  async function invite(name: string) {
    const made = (await (await host("/api/users/invites", { method: "POST", body: { name } })).json()) as { link: string; key: string; user: { id: string } };
    const redeemed = await send(new URL(made.link).pathname, {}, { method: "POST", body: { key: made.key } });
    const cookie = redeemed.headers.get("set-cookie")!.split(";")[0]!;
    const page = await (await send("/", { cookie })).text();
    const token = /<meta name="caztor-token" content="([^"]*)"/.exec(page)![1]!;
    return { id: made.user.id, call: (path: string, call?: Call) => send(path, { cookie, "x-caztor-token": token }, call) };
  }
  const config = join(home, ".config", "caztor");
  return { server, claude, project, home, config, host, invite };
}

type Caller = (path: string, call?: Call) => Promise<Response> | Response;

async function turnOf(call: Caller, prompt: string) {
  const response = await call("/api/chat/turns", { method: "POST", body: { provider: "claude", prompt } });
  expect(response.status).toBe(200);
  return parseFrames(await response.text());
}

describe("each person's chat state through the running server", () => {
  it("keeps history, sessions, models, auth modes and keys apart for the host and two collaborators", async () => {
    const t = await boot();
    const ana = await t.invite("Ana");
    const bo = await t.invite("Bo");

    for (const [call, model] of [[t.host, "m-host"], [ana.call, "m-ana"], [bo.call, "m-bo"]] as const) {
      expect((await call("/api/providers/claude/model", { method: "PUT", body: { model } })).status).toBe(200);
    }
    expect((await ana.call("/api/credentials/claude", { method: "PUT", body: { key: "sk-ana-key-000000001" } })).status).toBe(200);
    expect((await ana.call("/api/providers/claude/auth-mode", { method: "PUT", body: { mode: "api" } })).status).toBe(200);
    expect((await bo.call("/api/providers/claude/auth-mode", { method: "PUT", body: { mode: "api" } })).status).toBe(409);

    await turnOf(t.host, "host prompt");
    await turnOf(ana.call, "ana prompt");
    await turnOf(bo.call, "bo prompt");

    const listed = async (call: Caller) => {
      const body = (await (await call("/api/providers")).json()) as { providers: Array<{ id: string; model: string | null; auth: { mode: string; keys: Array<{ slot: string; set: boolean; last4?: string }>; login: string } }> };
      const claude = body.providers.find((provider) => provider.id === "claude")!;
      return { model: claude.model, mode: claude.auth.mode, key: claude.auth.keys.find((key) => key.slot === "claude"), login: claude.auth.login, text: JSON.stringify(body) };
    };
    expect(await listed(t.host)).toMatchObject({ model: "m-host", mode: "account", key: { slot: "claude", set: false }, login: "signed_in" });
    const anaListing = await listed(ana.call);
    expect(anaListing).toMatchObject({ model: "m-ana", mode: "api", key: { slot: "claude", set: true, last4: "0001" }, login: "unknown" });
    expect(anaListing.text).not.toContain("sk-ana-key-000000001");
    expect(await listed(bo.call)).toMatchObject({ model: "m-bo", mode: "account", key: { slot: "claude", set: false }, login: "signed_in" });

    const prompts = async (call: Caller) => ((await (await call("/api/chat/history?provider=claude")).json()) as { turns: Array<{ prompt: string }> }).turns.map((turn) => turn.prompt);
    expect(await prompts(t.host)).toEqual(["host prompt"]);
    expect(await prompts(ana.call)).toEqual(["ana prompt"]);
    expect(await prompts(bo.call)).toEqual(["bo prompt"]);

    // On disk: the host's files where a single-user project keeps them, each collaborator's apart.
    const chat = join(t.project, ".caztor", "chat");
    expect(readFileSync(join(chat, "claude.jsonl"), "utf8")).toContain("host prompt");
    // A collaborator's conversation is kept in their private folder, outside the shared project that agents see.
    expect(readdirSync(chat)).toEqual(["claude.jsonl"]);
    expect(readFileSync(join(userChatFolder(join(t.home, ".config"), ana.id, t.project), "claude.jsonl"), "utf8")).toContain("ana prompt");
    expect(readFileSync(join(userChatFolder(join(t.home, ".config"), bo.id, t.project), "claude.jsonl"), "utf8")).toContain("bo prompt");
    expect(userChatFolder(join(t.home, ".config"), ana.id, t.project).startsWith(join(t.config, "users", ana.id, "chat"))).toBe(true);
    const state = JSON.parse(readFileSync(join(t.project, ".caztor", "state.json"), "utf8")) as Record<string, any>;
    expect(state["models"]).toEqual({ claude: "m-host" });
    expect(state["sessions"].claude.sessionId).toBe("session-m-host");
    expect(state["users"][ana.id]).toMatchObject({ models: { claude: "m-ana" }, authModes: { claude: "api" }, sessions: { claude: { sessionId: "session-m-ana", authMode: "api" } } });
    expect(state["users"][bo.id]).toMatchObject({ models: { claude: "m-bo" }, sessions: { claude: { sessionId: "session-m-bo" } } });
    expect(existsSync(join(t.config, "credentials.json"))).toBe(false);
    expect(JSON.parse(readFileSync(join(t.config, "users", ana.id, "credentials.json"), "utf8"))).toEqual({ version: 1, keys: { claude: "sk-ana-key-000000001" } });
    expect(statSync(join(t.config, "users", ana.id, "credentials.json")).mode & 0o777).toBe(0o600);

    // The runner got each collaborator's own environment and key; the host's turn the server's, as before.
    const [hostReq, anaReq, boReq] = t.claude.requests;
    expect(hostReq).not.toHaveProperty("env");
    expect(anaReq?.env?.["HOME"]).toBe(join(t.config, "users", ana.id, "home"));
    expect(anaReq?.env).not.toHaveProperty("CLAUDE_CODE_OAUTH_TOKEN");
    expect(anaReq?.env).not.toHaveProperty("DBUS_SESSION_BUS_ADDRESS");
    expect(await anaReq?.credentials?.read("claude")).toEqual({ ok: true, value: "sk-ana-key-000000001" });
    expect(boReq?.env?.["CLAUDE_CONFIG_DIR"]).toBe(join(t.config, "users", bo.id, "home", ".claude"));
    for (const id of [ana.id, bo.id]) expect(statSync(join(t.config, "users", id, "home")).mode & 0o777).toBe(0o700);
    expect(join(t.config, "users").startsWith(`${t.project}/`)).toBe(false);
    expect(readdirSync(join(t.project, ".caztor")).sort()).not.toContain("users");
    await t.server.close();
  });

  it("runs one turn at a time per project and keeps stop and undo with whoever ran the turn", async () => {
    const t = await boot();
    const ana = await t.invite("Ana");
    const bo = await t.invite("Bo");
    t.claude.script = async function* ({ gate, write }) {
      write("main.tex", "changed by Ana's agent");
      await gate;
      yield { type: "done", reason: "completed" };
    };
    const running = await ana.call("/api/chat/turns", { method: "POST", body: { provider: "claude", prompt: "go" } });
    const turnId = running.headers.get("x-caztor-turn-id")!;
    await vi.waitFor(() => expect(t.claude.requests).toHaveLength(1));

    for (const call of [bo.call, t.host]) {
      const refused = await call("/api/chat/turns", { method: "POST", body: { provider: "claude", prompt: "me too" } });
      expect(refused.status).toBe(409);
      expect(await refused.json()).toMatchObject({ error: "busy", message: "Ana has a turn running. Wait for it to finish." });
      const stop = await call(`/api/chat/turns/${turnId}/stop`, { method: "POST", body: {} });
      expect(stop.status).toBe(409);
      expect(await stop.json()).toMatchObject({ error: "not_your_turn", message: "Ana has a turn running. Wait for it to finish." });
      expect((await call("/api/chat/turns/current")).status).toBe(409);
    }
    expect(await (await bo.call("/api/chat/history?provider=claude")).json()).toMatchObject({ running: true, currentTurnId: null, runningBy: "Ana" });
    t.claude.release();
    await parseFrames(await running.text());

    const undoBo = await bo.call(`/api/chat/turns/${turnId}/undo`, { method: "POST", body: { mode: "strict" } });
    expect(undoBo.status).toBe(409);
    expect(await undoBo.json()).toMatchObject({ error: "not_your_turn", message: "Ana ran this turn, so only Ana can undo it." });
    expect(((await (await bo.call("/api/chat/history?provider=claude")).json()) as { undoableTurnId: unknown }).undoableTurnId).toBeNull();
    expect(((await (await ana.call("/api/chat/history?provider=claude")).json()) as { undoableTurnId: unknown }).undoableTurnId).toBe(turnId);
    expect(readFileSync(join(t.project, "main.tex"), "utf8")).toBe("changed by Ana's agent");
    const undone = await ana.call(`/api/chat/turns/${turnId}/undo`, { method: "POST", body: { mode: "strict" } });
    expect(undone.status).toBe(200);
    expect(readFileSync(join(t.project, "main.tex"), "utf8")).toBe("x");
    await t.server.close();
  });

  it("lets only the person who ran a turn follow it, also once it has finished (B4)", async () => {
    const t = await boot();
    const ana = await t.invite("Ana");
    const bo = await t.invite("Bo");
    await turnOf(ana.call, "ana secret prompt");
    const id = ((await (await ana.call("/api/chat/history?provider=claude")).json()) as { turns: Array<{ turnId: string }> }).turns[0]!.turnId;
    for (const call of [bo.call, t.host]) {
      for (const path of ["/api/chat/turns/current", `/api/chat/turns/${id}/events`]) {
        const refused = await call(path);
        expect(refused.status).toBe(404);
        const text = await refused.text();
        for (const secret of ["ana secret prompt", "answer to", "session-", id]) expect(text).not.toContain(secret);
      }
    }
    for (const path of ["/api/chat/turns/current", `/api/chat/turns/${id}/events`]) {
      const own = await ana.call(path);
      expect(own.status).toBe(200);
      expect(await own.text()).toContain("answer to ana secret prompt");
    }
    await t.server.close();
  });

  it("keeps who ran a turn across a restart: nobody else, the host included, can undo it (B5)", async () => {
    const t = await boot();
    const ana = await t.invite("Ana");
    t.claude.script = async function* ({ write }) {
      write("main.tex", "changed by Ana's agent");
      yield { type: "done", reason: "completed" };
    };
    await turnOf(ana.call, "go");
    const turnId = ((await (await ana.call("/api/chat/history?provider=claude")).json()) as { undoableTurnId: string }).undoableTurnId;
    expect(turnId).toEqual(expect.any(String));
    await t.server.close();

    const again = await boot({ home: t.home });
    expect(((await (await again.host("/api/chat/history?provider=claude")).json()) as { undoableTurnId: unknown }).undoableTurnId).toBeNull();
    const refused = await again.host(`/api/chat/turns/${turnId}/undo`, { method: "POST", body: { mode: "strict" } });
    expect(refused.status).toBe(409);
    expect(await refused.json()).toMatchObject({ error: "not_your_turn" });
    expect(readFileSync(join(again.project, "main.tex"), "utf8")).toBe("changed by Ana's agent");
    await again.server.close();
  });
});
