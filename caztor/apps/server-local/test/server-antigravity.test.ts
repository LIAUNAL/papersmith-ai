import { chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem } from "@caztor/adapters-local";
import { afterEach, describe, expect, it } from "vitest";
import { ScriptedSpawner } from "./support/scripted-spawner.ts";
import type { Listener, ListenFn } from "../src/listen.ts";
import { startServer } from "../src/server.ts";
import { parseFrames } from "./routes/chat-support.ts";

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));
const turnLines = readFileSync(fileURLToPath(new URL("../../../packages/adapters-local/test/providers/antigravity/fixtures/edit-turn.jsonl", import.meta.url)), "utf8")
  .split("\n")
  .filter((line) => line !== "")
  .map((line) => `${line}\n`);
const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});
const ok = { code: 0, signal: null };

async function start(options: { installed?: boolean; files?: Record<string, string> } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "caztor-server-antigravity-"));
  dirs.push(dir);
  writeFileSync(join(dir, "main.tex"), "The cat sat on the mat.");
  for (const [name, text] of Object.entries(options.files ?? {})) {
    mkdirSync(join(dir, name, ".."), { recursive: true });
    writeFileSync(join(dir, name), text);
  }
  const bin = mkdtempSync(join(tmpdir(), "caztor-bin-"));
  dirs.push(bin);
  if (options.installed !== false) {
    writeFileSync(join(bin, "agy"), "#!/bin/sh\n");
    chmodSync(join(bin, "agy"), 0o755);
  }
  const handlers: Array<(request: Request) => Response | Promise<Response>> = [];
  const listen: ListenFn = async ({ port, fetch }) => {
    handlers.push(fetch);
    return { port, close: async () => {} } satisfies Listener;
  };
  const spawner = new ScriptedSpawner();
  const server = await startServer({
    projectDir: dir,
    webRoot,
    env: { PATH: bin, HOME: "/home/someone", TMPDIR: tmpdir(), GEMINI_API_KEY: "must-not-leak" },
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
  return { server, call, spawner, dir };
}

const listProviders = async (call: Awaited<ReturnType<typeof start>>["call"]) =>
  ((await (await call("GET", "/api/providers")).json()) as { providers: Array<Record<string, unknown>> }).providers.find((provider) => provider["id"] === "antigravity");

describe("the Antigravity adapter in the running server", () => {
  it("lists Antigravity as available, account only, with its version and models", async () => {
    const { server, call, spawner } = await start();
    spawner.enqueue({ stdout: ["1.4.12\n"], exit: ok });
    spawner.enqueue({ stdout: ["Fetching available models...\ngemini-3.8-flash-medium\tGemini 3.8 Flash (Medium)\n"], exit: ok });
    expect(await listProviders(call)).toMatchObject({ installed: true, version: "1.4.12", requiresModel: false, models: ["gemini-3.8-flash-medium"], auth: { modes: ["account"] } });
    await server.close();
  });

  it("lists Antigravity as not installed when agy is not on the PATH", async () => {
    const { server, call } = await start({ installed: false });
    expect(await listProviders(call)).toMatchObject({ installed: false, unavailableReason: expect.stringContaining("agy") });
    await server.close();
  });

  it("runs a turn over HTTP: provisions the definition, attaches the prompt, keeps keys out, shows the notice", async () => {
    const { server, call, spawner, dir } = await start();
    spawner.enqueue({ stdout: ["1.4.12\n"], exit: ok });
    spawner.enqueue({ stdout: [], exit: ok });
    spawner.enqueue({ stdout: turnLines, exit: ok });
    const response = await call("POST", "/api/chat/turns", { provider: "antigravity", prompt: "Change cat to dog" });
    const text = await response.text();
    const frames = parseFrames(text);
    expect(response.status, text).toBe(200);
    expect(frames.some((frame) => frame.event === "notice" && JSON.stringify(frame.data).includes("partial isolation"))).toBe(true);
    expect(frames.map((frame) => frame.event)).toContain("text");
    expect(frames.find((frame) => frame.event === "done")).toMatchObject({ data: { reason: "completed" } });
    const run = spawner.calls.find((spawn) => spawn.args.includes("--agent"))!;
    expect(run.args).toEqual(["--output-format", "stream-json", "--mode", "accept-edits", "--agent", "caztor", "-p=Change cat to dog"]);
    expect(Object.keys(run.env)).not.toContain("GEMINI_API_KEY");
    expect(readFileSync(join(dir, ".agents", "agents", "caztor.md"), "utf8")).toContain("commandExecutionPolicy: off");
    await server.close();
  });

  it("reports the login as unknown until a turn completes, then as signed in", async () => {
    const { server, call, spawner } = await start();
    spawner.enqueue({ stdout: ["1.4.12\n"], exit: ok });
    spawner.enqueue({ stdout: [], exit: ok });
    const loginOf = async () => ((await (await call("GET", "/api/providers")).json()) as { providers: Array<{ id: string; auth: { login: string } }> }).providers.find((provider) => provider.id === "antigravity")?.auth.login;
    expect(await loginOf()).toBe("unknown");
    spawner.enqueue({ stdout: ["1.4.12\n"], exit: ok });
    spawner.enqueue({ stdout: turnLines, exit: ok });
    await (await call("POST", "/api/chat/turns", { provider: "antigravity", prompt: "Hi" })).text();
    expect(await loginOf()).toBe("signed_in");
    await server.close();
  });

  it("refuses a turn while the project's .agents folder holds other files, until the user trusts them", async () => {
    const { server, call, spawner } = await start({ files: { ".agents/hooks.json": "{}" } });
    spawner.enqueue({ stdout: ["1.4.12\n"], exit: ok });
    spawner.enqueue({ stdout: [], exit: ok });
    const refused = await (await call("POST", "/api/chat/turns", { provider: "antigravity", prompt: "Hi" })).text();
    expect(refused).toContain("isolation_failed");
    expect(spawner.calls.some((spawn) => spawn.args.includes("--agent"))).toBe(false);
    await server.close();
  });

  it("asks the user to confirm those files, and runs the turn once they are trusted", async () => {
    const { server, call, spawner } = await start({ files: { ".agents/hooks.json": "{}" } });
    spawner.enqueue({ stdout: ["1.4.12\n"], exit: ok });
    spawner.enqueue({ stdout: [], exit: ok });
    const listing = (await (await call("GET", "/api/providers")).json()) as { providers: Array<{ id: string; projectConfig?: { files: string[]; confirmed: boolean; fingerprint: string } }> };
    const config = listing.providers.find((provider) => provider.id === "antigravity")?.projectConfig;
    expect(config).toMatchObject({ confirmed: false, files: expect.arrayContaining([expect.stringContaining(".agents/hooks.json")]) });

    expect((await call("POST", "/api/providers/antigravity/project-config/trust", { fingerprint: config?.fingerprint })).status).toBe(200);
    spawner.enqueue({ stdout: ["1.4.12\n"], exit: ok });
    spawner.enqueue({ stdout: turnLines, exit: ok });
    const turn = await call("POST", "/api/chat/turns", { provider: "antigravity", prompt: "Hi" });
    const text = await turn.text();
    expect(text).not.toContain("isolation_failed");
    expect(text).toContain('"completed"');
    expect(spawner.calls.some((spawn) => spawn.args.includes("--agent"))).toBe(true);
    await server.close();
  });
});
