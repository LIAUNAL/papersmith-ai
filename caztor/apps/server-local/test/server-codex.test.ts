import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
const turnFixture = readFileSync(fileURLToPath(new URL("../../../packages/adapters-local/test/providers/codex/fixtures/documented-edit-turn.jsonl", import.meta.url)), "utf8");
const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});
const ok = { code: 0, signal: null };

async function start(options: { installed?: boolean } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "caztor-server-codex-"));
  dirs.push(dir);
  writeFileSync(join(dir, "main.tex"), "Hello world.");
  const bin = mkdtempSync(join(tmpdir(), "caztor-bin-"));
  dirs.push(bin);
  if (options.installed !== false) {
    writeFileSync(join(bin, "codex"), "#!/bin/sh\n");
    chmodSync(join(bin, "codex"), 0o755);
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
    env: { PATH: bin, HOME: "/home/someone", GITHUB_TOKEN: "must-not-leak", CODEX_THREAD_ID: "parent" },
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
  return { server, call, spawner, dir: await nodeFileSystem.realpath(dir) };
}

describe("the Codex adapter in the running server", () => {
  it("lists Codex as not installed, with the reason, and without a model setting, when it is not on the PATH", async () => {
    const { server, call } = await start({ installed: false });
    const body = (await (await call("GET", "/api/providers")).json()) as { providers: Array<Record<string, unknown>> };
    const codex = body.providers.find((provider) => provider["id"] === "codex");
    expect(codex).toMatchObject({ installed: false, supportsModel: false, requiresModel: false });
    expect(String(codex?.["unavailableReason"])).toMatch(/not installed/i);
    await server.close();
  });

  it("lists Codex as available with its version when it answers", async () => {
    const { server, call, spawner } = await start();
    spawner.enqueue({ stdout: ["codex-cli 0.46.0\n"], exit: ok });
    const body = (await (await call("GET", "/api/providers")).json()) as { providers: Array<Record<string, unknown>> };
    expect(body.providers.find((provider) => provider["id"] === "codex")).toMatchObject({ installed: true, version: "0.46.0", supportsModel: false });
    await server.close();
  });

  it("refuses a turn with the not-installed reason when it is missing", async () => {
    const { server, call } = await start({ installed: false });
    const response = await call("POST", "/api/chat/turns", { provider: "codex", prompt: "Say hi" });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "not_installed", message: expect.stringMatching(/not installed/i) });
    await server.close();
  });

  it("runs a chat turn end to end: provisions AGENTS.md, starts exec with the prompt on stdin, streams the events", async () => {
    const { server, call, spawner, dir } = await start();
    spawner.enqueue({ stdout: ["codex-cli 0.46.0\n"], exit: ok });
    spawner.enqueue({ stdout: turnFixture.split("\n").filter((line) => line !== "").map((line) => `${line}\n`), exit: ok });

    const response = await call("POST", "/api/chat/turns", { provider: "codex", prompt: "Say hi instead of hello" });
    const text = await response.text();
    const frames = parseFrames(text);
    expect(response.status, text).toBe(200);
    expect(frames[0]?.event).toBe("turn_started");
    expect(frames.map((frame) => frame.event)).toContain("tool_start");
    expect(frames.at(-2)).toMatchObject({ event: "done", data: { reason: "completed" } });
    const run = spawner.calls.find((spawn) => spawn.args[0] === "exec")!;
    expect(run.cwd).toBe(dir);
    expect(run.stdin).toBe("Say hi instead of hello");
    expect(run.args).toEqual(["exec", "--json", "--sandbox", "workspace-write", "--skip-git-repo-check", "--ignore-user-config", "-"]);
    expect(Object.keys(run.env)).not.toContain("GITHUB_TOKEN");
    expect(Object.keys(run.env)).not.toContain("CODEX_THREAD_ID");
    expect(readFileSync(join(dir, "AGENTS.md"), "utf8")).toContain("caztor:agent:begin");
    await server.close();
  });
});
