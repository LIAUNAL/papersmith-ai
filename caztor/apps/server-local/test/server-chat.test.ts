import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem } from "@caztor/adapters-local";
import { afterEach, describe, expect, it } from "vitest";
import type { Listener, ListenFn } from "../src/listen.ts";
import { startServer } from "../src/server.ts";
import { parseFrames } from "./routes/chat-support.ts";
import { createFakeRunner } from "./support/fake-runner.ts";

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));
const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

async function start() {
  const dir = mkdtempSync(join(tmpdir(), "caztor-server-chat-"));
  dirs.push(dir);
  writeFileSync(join(dir, "main.tex"), "before");
  const handlers: Array<(request: Request) => Response | Promise<Response>> = [];
  const listen: ListenFn = async ({ port, fetch }) => {
    handlers.push(fetch);
    return { port, close: async () => {} } satisfies Listener;
  };
  const probe = await nodeFileSystem.realpath(dir);
  const claude = createFakeRunner(probe, "claude");
  const server = await startServer({ projectDir: dir, webRoot, env: {}, fs: nodeFileSystem, listen, watcher: { watch: () => () => {} }, runners: { claude } });
  const host = `127.0.0.1:${server.port}`;
  const call = async (method: string, path: string, body?: unknown) =>
    handlers[0]!(
      new Request(`http://${host}${path}`, {
        method,
        headers: { host, "x-caztor-token": server.token, ...(method === "GET" ? {} : { origin: `http://${host}`, "content-type": "application/json" }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      }),
    );
  return { server, call, claude, dir: probe };
}

describe("the chat through the running server", () => {
  it("lists the wired provider, runs a turn that edits a file, and announces the change on the event stream", async () => {
    const { server, call, claude, dir } = await start();
    const providers = (await (await call("GET", "/api/providers")).json()) as { providers: Array<{ id: string; installed: boolean }> };
    expect(providers.providers.map((provider) => [provider.id, provider.installed])).toEqual([["claude", true], ["opencode", false], ["codex", false], ["antigravity", false], ["pi", false]]);

    const events = await call("GET", "/api/events");
    const reader = events.body!.getReader();
    claude.script = async function* ({ write }) {
      write("main.tex", "after");
      yield { type: "done", reason: "completed" };
    };
    const response = await call("POST", "/api/chat/turns", { provider: "claude", prompt: "Change it" });
    const frames = parseFrames(await response.text());
    expect(frames.map((frame) => frame.event)).toEqual(["turn_started", "done", "files_changed"]);
    expect(readFileSync(join(dir, "main.tex"), "utf8")).toBe("after");
    expect(existsSync(join(dir, ".claude", "agents", "caztor.md"))).toBe(true);

    const decoder = new TextDecoder();
    let seen = "";
    while (!seen.includes("event: file_changed")) seen += decoder.decode((await reader.read()).value);
    await reader.cancel();
    expect(seen).toContain('"path":"main.tex"');
    await server.close();
  });

  it("stops a running turn when the server closes", async () => {
    const { server, call, claude } = await start();
    let signalSeen: AbortSignal | null = null;
    claude.script = async function* ({ signal, aborted }) {
      signalSeen = signal;
      await aborted();
      yield { type: "done", reason: "cancelled" };
    };
    const response = await call("POST", "/api/chat/turns", { provider: "claude", prompt: "Long" });
    const reading = response.text();
    while (signalSeen === null) await new Promise((resolve) => setTimeout(resolve, 5));
    await server.close();
    expect((signalSeen as AbortSignal).aborted).toBe(true);
    expect(parseFrames(await reading).some((frame) => frame.event === "done" && frame.data["reason"] === "cancelled")).toBe(true);
  });
});
