import { chmodSync, existsSync, mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem } from "@caztor/adapters-local";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FetchHandler, Listener, ListenFn } from "../src/listen.ts";
import { startServer } from "../src/server.ts";
import { parseFrames } from "./routes/chat-support.ts";
import { createFakeRunner } from "./support/fake-runner.ts";
import { ScriptedSpawner } from "./support/scripted-spawner.ts";

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));
const PUBLIC = "box.tail1234.ts.net";
const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});
const hasBwrap = existsSync("/usr/bin/bwrap");
const flush = async () => {
  for (let index = 0; index < 20; index += 1) await new Promise((resolve) => setImmediate(resolve));
};
const CLAUDE_FIRST = "Opening browser to sign in…\nIf the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&state=A3v5\nPaste code here if prompted > ";

interface Call {
  method?: string;
  body?: unknown;
}

/** A server open to collaborators, with fake CLIs on the PATH and every process scripted: nothing real is started. */
async function boot() {
  const home = realpathSync(mkdtempSync(join(tmpdir(), "caztor-logins-")));
  dirs.push(home);
  const project = join(home, "papers", "paper");
  mkdirSync(project, { recursive: true });
  writeFileSync(join(project, "main.tex"), "x");
  const bin = realpathSync(mkdtempSync(join(tmpdir(), "caztor-logins-bin-")));
  dirs.push(bin);
  for (const name of ["claude", "codex"]) {
    writeFileSync(join(bin, name), "#!/bin/sh\n");
    chmodSync(join(bin, name), 0o755);
  }
  const claude = createFakeRunner(project, "claude");
  let fetch!: FetchHandler;
  const listen: ListenFn = async (options) => {
    fetch = options.fetch;
    return { port: options.port, close: async () => {} } satisfies Listener;
  };
  const spawner = new ScriptedSpawner();
  const env = { PATH: `${bin}:/usr/bin:/bin`, HOME: home, TMPDIR: tmpdir(), CLAUDE_CODE_OAUTH_TOKEN: "host-oauth" };
  const server = await startServer({ projectDir: project, webRoot, env, fs: nodeFileSystem, listen, watcher: { watch: () => () => {} }, runners: { claude }, spawner, publicNames: [PUBLIC] });
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
  return { server, claude, spawner, project, home, bin, host, invite };
}

const loginOf = async (call: (path: string) => Promise<Response> | Response) =>
  ((await (await call("/api/providers")).json()) as { providers: Array<{ id: string; auth: { login: string } }> }).providers.find((provider) => provider.id === "claude")?.auth.login;

describe("collaborators in the running server", () => {
  it("may use the chat, the providers and their own keys now, and their turns ask for the sandbox; the user routes stay the host's", async () => {
    const t = await boot();
    const ana = await t.invite("Ana");
    expect((await ana.call("/api/providers")).status).toBe(200);
    expect((await ana.call("/api/credentials/claude", { method: "PUT", body: { key: "sk-ana-key-000000001" } })).status).toBe(200);
    const turn = await ana.call("/api/chat/turns", { method: "POST", body: { provider: "claude", prompt: "hi" } });
    expect(turn.status).toBe(200);
    const frames = parseFrames(await turn.text());
    expect(frames.map((frame) => frame.event), JSON.stringify(frames)).toContain("done");
    expect(t.claude.requests.at(-1)?.sandbox?.home).toBe(join(t.home, ".config", "caztor", "users", ana.id, "home"));
    expect((await ana.call("/api/users")).status).toBe(403);
    await t.server.close();
  });

  it("may not trust the project's CLI configuration, which the host's unsandboxed turns would load", async () => {
    const t = await boot();
    const ana = await t.invite("Ana");
    const refused = await ana.call("/api/providers/opencode/project-config/trust", { method: "POST", body: { fingerprint: "sha256:x" } });
    expect(refused.status).toBe(403);
    expect(((await refused.json()) as { error: string }).error).toBe("host_only");
    await t.server.close();
  });

  it.skipIf(!hasBwrap)("signs a collaborator in to claude inside bubblewrap with their private home, and only they see it", async () => {
    const t = await boot();
    const ana = await t.invite("Ana");
    const privateHome = join(t.home, ".config", "caztor", "users", ana.id, "home");
    // The host signs in with its own token; Ana's sign-in must leave the host's state as it was.
    const hostBefore = await loginOf(t.host);
    // ldd of the CLI's interpreter, the --version probe in the sandbox, then the sign-in.
    t.spawner.enqueue({ stdout: [""], exit: { code: 0, signal: null } });
    t.spawner.enqueue({ stdout: ["2.1.317 (Claude Code)\n"], exit: { code: 0, signal: null } });
    t.spawner.enqueue({ stdout: [CLAUDE_FIRST, "Login successful.\n"], exit: { code: 0, signal: null } });
    const started = await ana.call("/api/logins/claude", { method: "POST", body: {} });
    expect(started.status).toBe(201);
    const spawned = t.spawner.calls.at(-1)!;
    expect(spawned.file).toBe("/usr/bin/bwrap");
    expect(spawned.args.slice(-5)).toEqual(["--", join(t.bin, "claude"), "auth", "login", "--claudeai"]);
    expect(spawned.args).toEqual(expect.arrayContaining(["--tmpfs", t.home, "--tmpfs", `${t.project}/.caztor`]));
    expect(spawned.env).toMatchObject({ HOME: privateHome, CLAUDE_CONFIG_DIR: `${privateHome}/.claude` });
    expect(spawned.env).not.toHaveProperty("CLAUDE_CODE_OAUTH_TOKEN");
    expect(spawned.interactive).toBe(true);
    await flush();
    const followed = (await (await ana.call("/api/logins/claude")).json()) as { login: { state: string; text: string } };
    expect(followed.login, JSON.stringify(t.spawner.calls.map((call) => call.args.slice(-4)))).toMatchObject({ state: "signed_in" });
    expect(followed.login.text).toContain("https://claude.com/cai/oauth/authorize");
    // The login state is Ana's alone.
    expect(await loginOf(ana.call)).toBe("signed_in");
    expect(await loginOf(t.host)).toBe(hostBefore);
    // Nobody else sees, feeds or cancels it.
    expect(((await (await t.host("/api/logins/claude")).json()) as { login: unknown }).login).toBeNull();
    const bo = await t.invite("Bo");
    expect(((await (await bo.call("/api/logins/claude")).json()) as { login: unknown }).login).toBeNull();
    expect((await bo.call("/api/logins/claude/input", { method: "POST", body: { line: "code" } })).status).toBe(404);
    expect((await bo.call("/api/logins/claude", { method: "DELETE" })).status).toBe(404);
    await t.server.close();
  });

  it("signs the host in without a sandbox, with the server's environment, from an empty folder of its own", async () => {
    const t = await boot();
    t.spawner.enqueue({ stdout: ["Enter this one-time code\n   XZIF-17WOH\n"], exit: { code: 0, signal: null } });
    expect((await t.host("/api/logins/codex", { method: "POST", body: {} })).status).toBe(201);
    const spawned = t.spawner.calls.at(-1)!;
    expect(spawned).toMatchObject({ file: join(t.bin, "codex"), args: ["login", "--device-auth"] });
    // Never the project, which a collaborator's turn can write: a fresh folder closed to others, removed afterwards.
    expect(spawned.cwd).not.toBe(t.project);
    expect(spawned.cwd).toMatch(/\/caztor-login-[^/]+$/);
    expect(spawned.env).toMatchObject({ HOME: t.home, CLAUDE_CODE_OAUTH_TOKEN: "host-oauth" });
    // The folder is removed when the session ends; that is not awaited by the request, so wait for it.
    await vi.waitFor(() => expect(existsSync(spawned.cwd)).toBe(false));
    expect(((await (await t.host("/api/logins/codex")).json()) as { login: unknown }).login).toMatchObject({ state: "signed_in", code: "XZIF-17WOH" });
    await t.server.close();
  });
});
