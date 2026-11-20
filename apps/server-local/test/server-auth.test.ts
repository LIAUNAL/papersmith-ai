import { chmodSync, existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem } from "@caztor/adapters-local";
import { afterEach, describe, expect, it } from "vitest";
import { ScriptedSpawner } from "./support/scripted-spawner.ts";
import type { Listener, ListenFn } from "../src/listen.ts";
import { startServer } from "../src/server.ts";

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));
const authFixture = readFileSync(fileURLToPath(new URL("../../../packages/adapters-local/test/providers/claude/fixtures/error-auth.jsonl", import.meta.url)), "utf8");
const editFixture = readFileSync(fileURLToPath(new URL("../../../packages/adapters-local/test/providers/claude/fixtures/edit-turn.jsonl", import.meta.url)), "utf8");
const KEY = "sk-planted-fake-key-ABCDEF123456";
const EXPORTED = "sk-exported-in-server-env-0001";
const ok = { code: 0, signal: null };
const lines = (text: string) => text.split("\n").filter((line) => line !== "").map((line) => `${line}\n`);

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});
const temp = (prefix: string) => {
  const dir = mkdtempSync(join(tmpdir(), prefix));
  dirs.push(dir);
  return dir;
};

/** The real server over a real project, a scripted `claude` and a temporary configuration home; the user's own ~/.config is never read. */
async function start(extraEnv: Record<string, string> = {}) {
  const dir = temp("caztor-auth-project-");
  writeFileSync(join(dir, "main.tex"), "Hello world.");
  const bin = temp("caztor-auth-bin-");
  writeFileSync(join(bin, "claude"), "#!/bin/sh\n");
  chmodSync(join(bin, "claude"), 0o755);
  const configHome = temp("caztor-auth-config-");
  const handlers: Array<(request: Request) => Response | Promise<Response>> = [];
  const listen: ListenFn = async ({ port, fetch }) => {
    handlers.push(fetch);
    return { port, close: async () => {} } satisfies Listener;
  };
  const spawner = new ScriptedSpawner();
  const server = await startServer({
    projectDir: dir,
    webRoot,
    env: { PATH: bin, HOME: "/home/someone", XDG_CONFIG_HOME: configHome, ANTHROPIC_API_KEY: EXPORTED, ...extraEnv },
    fs: nodeFileSystem,
    listen,
    watcher: { watch: () => () => {} },
    spawner,
  });
  const host = `127.0.0.1:${server.port}`;
  const call = async (method: string, path: string, body?: unknown) =>
    handlers[0]!(
      new Request(`http://${host}${path}`, {
        method,
        headers: { host, "x-caztor-token": server.token, ...(method === "GET" ? {} : { origin: `http://${host}`, "content-type": "application/json" }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      }),
    );
  return { server, call, spawner, configHome, dir: await nodeFileSystem.realpath(dir) };
}

/** Every file below `dir`, as text, with its path. */
function filesUnder(dir: string): Array<{ path: string; text: string }> {
  const out: Array<{ path: string; text: string }> = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...filesUnder(full));
    else if (entry.isFile()) out.push({ path: full, text: readFileSync(full, "utf8") });
  }
  return out;
}

describe("the Claude Code adapter in each sign-in mode", () => {
  it("in account mode (the default) never passes the Anthropic key that is exported in the server environment", async () => {
    const { server, call, spawner } = await start();
    spawner.enqueue({ stdout: ["2.1.304 (Claude Code)\n"], exit: ok });
    spawner.enqueue({ stdout: lines(editFixture), exit: ok });
    const response = await call("POST", "/api/chat/turns", { provider: "claude", prompt: "Hi" });
    expect(response.status).toBe(200);
    await response.text();
    const env = spawner.calls.at(-1)!.env;
    expect(Object.keys(env)).not.toContain("ANTHROPIC_API_KEY");
    expect(JSON.stringify(spawner.calls)).not.toContain(EXPORTED);
    await server.close();
  });

  it("refuses a message in api mode once the key is deleted, and starts no run", async () => {
    const { server, call, spawner } = await start();
    await call("PUT", "/api/credentials/claude", { key: KEY });
    await call("PUT", "/api/providers/claude/auth-mode", { mode: "api" });
    await call("DELETE", "/api/credentials/claude");
    spawner.enqueue({ stdout: ["2.1.304 (Claude Code)\n"], exit: ok });
    const response = await call("POST", "/api/chat/turns", { provider: "claude", prompt: "Hi" });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "api_key_missing" });
    expect(spawner.calls.every((call) => call.args[0] === "--version")).toBe(true);
    await server.close();
  });

  it("does not switch to api mode without a stored key", async () => {
    const { server, call } = await start();
    expect((await call("PUT", "/api/providers/claude/auth-mode", { mode: "api" })).status).toBe(409);
    await server.close();
  });

  it("in api mode passes the stored key to the child, and a key the CLI echoes reaches no output channel", async () => {
    const { server, call, spawner, configHome, dir } = await start();
    expect((await call("PUT", "/api/credentials/claude", { key: KEY })).status).toBe(200);
    expect((await call("PUT", "/api/providers/claude/auth-mode", { mode: "api" })).status).toBe(200);

    const echoed = authFixture.replaceAll("Invalid API key \\u00b7 Please run /login", `Invalid API key ${KEY} rejected`);
    expect(echoed).toContain(KEY);
    spawner.enqueue({ stdout: ["2.1.304 (Claude Code)\n"], exit: ok });
    spawner.enqueue({ stdout: lines(echoed), stderr: [`warning: using key ${KEY}\n`], exit: { code: 1, signal: null } });

    const channels: Array<[string, string]> = [];
    const response = await call("POST", "/api/chat/turns", { provider: "claude", prompt: "Say hi" });
    expect(response.status).toBe(200);
    channels.push(["turn stream", await response.text()]);

    const run = spawner.calls.at(-1)!;
    expect(run.env["ANTHROPIC_API_KEY"]).toBe(KEY);
    expect(JSON.stringify(run.env)).not.toContain(EXPORTED);
    expect(run.args.join(" ")).not.toContain(KEY);
    expect(run.stdin).toBe("Say hi");

    for (const [method, path, body] of [
      ["GET", "/api/chat/history", undefined],
      ["GET", "/api/chat/turns/current", undefined],
      ["GET", "/api/providers", undefined],
      ["POST", "/api/providers/recheck", {}],
      ["GET", "/api/credentials/claude", undefined],
      ["PUT", "/api/credentials/claude", { key: "has space" }],
      ["DELETE", "/api/credentials/nobody", undefined],
    ] as const) {
      const r = await call(method, path, body);
      channels.push([`${method} ${path}`, [...r.headers].map(([k, v]) => `${k}: ${v}`).join("\n") + (await r.text())]);
    }
    for (const [name, text] of channels) expect(text, name).not.toContain(KEY);
    expect(channels[0]![1]).toContain("[redacted]");

    // Files in the project (state, chat history, snapshots, definitions) never hold the key; the store file is the one place that does.
    for (const file of filesUnder(dir)) expect(file.text, file.path).not.toContain(KEY);
    const stored = filesUnder(configHome);
    expect(stored.filter((file) => file.text.includes(KEY)).map((file) => file.path)).toEqual([join(configHome, "caztor", "credentials.json")]);
    await server.close();
  });

  it("starts a new conversation with a notice when the sign-in method changes", async () => {
    const { server, call, spawner } = await start();
    await call("PUT", "/api/credentials/claude", { key: KEY });
    spawner.enqueue({ stdout: ["2.1.304 (Claude Code)\n"], exit: ok });
    spawner.enqueue({ stdout: lines(editFixture), exit: ok });
    await (await call("POST", "/api/chat/turns", { provider: "claude", prompt: "One" })).text();
    await call("PUT", "/api/providers/claude/auth-mode", { mode: "api" });
    spawner.enqueue({ stdout: ["2.1.304 (Claude Code)\n"], exit: ok });
    spawner.enqueue({ stdout: lines(editFixture), exit: ok });
    const text = await (await call("POST", "/api/chat/turns", { provider: "claude", prompt: "Two" })).text();
    expect(text).toContain("New conversation started because the sign-in method changed.");
    expect(spawner.calls.at(-1)!.args).not.toContain("--resume");
    await server.close();
  });

  it("does not create the user's credential folder just by starting or listing", async () => {
    const { server, call, configHome } = await start();
    await call("GET", "/api/providers");
    expect(existsSync(join(configHome, "caztor"))).toBe(false);
    await server.close();
  });
});
