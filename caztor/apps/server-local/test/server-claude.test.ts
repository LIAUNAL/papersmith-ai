import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
const turnFixture = readFileSync(fileURLToPath(new URL("../../../packages/adapters-local/test/providers/claude/fixtures/edit-turn.jsonl", import.meta.url)), "utf8");
const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

async function start(options: { installed?: boolean } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "caztor-server-claude-"));
  dirs.push(dir);
  writeFileSync(join(dir, "main.tex"), "Hello world.");
  const bin = mkdtempSync(join(tmpdir(), "caztor-bin-"));
  dirs.push(bin);
  if (options.installed !== false) {
    writeFileSync(join(bin, "claude"), "#!/bin/sh\n");
    chmodSync(join(bin, "claude"), 0o755);
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
    env: { PATH: bin, HOME: "/home/someone", GITHUB_TOKEN: "must-not-leak" },
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

describe("the Claude Code adapter in the running server", () => {
  it("lists Claude Code as available with its version, and the others as not installed", async () => {
    const { server, call, spawner } = await start();
    spawner.enqueue({ stdout: ["2.1.304 (Claude Code)\n"], exit: { code: 0, signal: null } });

    const body = (await (await call("GET", "/api/providers")).json()) as { providers: Array<{ id: string; installed: boolean; version?: string; unavailableReason?: string }> };

    expect(body.providers.map((provider) => [provider.id, provider.installed, provider.version])).toEqual([["claude", true, "2.1.304"], ["opencode", false, undefined], ["codex", false, undefined], ["antigravity", false, undefined], ["pi", false, undefined]]);
    expect(spawner.calls[0]).toMatchObject({ args: ["--version"] });
    await server.close();
  });

  it("lists Claude Code as not installed, with the reason, when it is not on the PATH", async () => {
    const { server, call } = await start({ installed: false });
    const body = (await (await call("GET", "/api/providers")).json()) as { providers: Array<{ id: string; installed: boolean; unavailableReason?: string }> };
    expect(body.providers[0]).toMatchObject({ id: "claude", installed: false, unavailableReason: "Claude Code was not found on the PATH." });
    await server.close();
  });

  it("runs a chat turn end to end: provisions the agent, starts the CLI with the prompt on stdin, streams the events, lists no change", async () => {
    const { server, call, spawner, dir } = await start();
    // Starting a turn checks the installed version once more, then the CLI runs.
    spawner.enqueue({ stdout: ["2.1.304 (Claude Code)\n"], exit: { code: 0, signal: null } });
    spawner.enqueue({ stdout: turnFixture.split("\n").filter((line) => line !== "").map((line) => `${line}\n`), exit: { code: 0, signal: null } });

    const response = await call("POST", "/api/chat/turns", { provider: "claude", prompt: "Say hi instead of hello" });
    const text = await response.text();
    const frames = parseFrames(text);
    expect(response.status, text).toBe(200);

    expect(frames[0]?.event).toBe("turn_started");
    expect(frames.map((frame) => frame.event)).toContain("text_delta");
    expect(frames.at(-2)).toMatchObject({ event: "done", data: { reason: "completed" } });
    expect(frames.at(-1)?.event).toBe("files_changed");
    expect(spawner.calls[0]?.args).toEqual(["--version"]);
    const run = spawner.calls[1]!;
    expect(run.cwd).toBe(dir);
    expect(run.stdin).toBe("Say hi instead of hello");
    expect(run.args).toContain("--agents");
    expect(Object.keys(run.env)).not.toContain("GITHUB_TOKEN");
    expect(existsSync(join(dir, ".claude", "agents", "caztor.md"))).toBe(true);
    await server.close();
  });
});
