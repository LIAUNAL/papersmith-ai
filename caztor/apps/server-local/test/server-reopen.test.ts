import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem } from "@caztor/adapters-local";
import { afterEach, describe, expect, it } from "vitest";
import { ScriptedSpawner } from "./support/scripted-spawner.ts";
import type { Listener, ListenFn } from "../src/listen.ts";
import { startServer } from "../src/server.ts";

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));
const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});
const scratch = (prefix: string) => {
  const dir = mkdtempSync(join(tmpdir(), prefix));
  dirs.push(dir);
  return dir;
};

async function open(projectDir: string, bin: string, configHome: string) {
  const handlers: Array<(request: Request) => Response | Promise<Response>> = [];
  const listen: ListenFn = async ({ port, fetch }) => {
    handlers.push(fetch);
    return { port, close: async () => {} } satisfies Listener;
  };
  const server = await startServer({
    projectDir,
    webRoot,
    env: { PATH: bin, HOME: "/home/someone", XDG_CONFIG_HOME: configHome, TMPDIR: tmpdir() },
    fs: nodeFileSystem,
    listen,
    watcher: { watch: () => () => {} },
    spawner: new ScriptedSpawner(),
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
  return { server, call };
}

describe("reopening a project", () => {
  it("keeps opencode in api mode", async () => {
    const project = scratch("caztor-reopen-");
    writeFileSync(join(project, "main.tex"), "x");
    const bin = scratch("caztor-bin-");
    writeFileSync(join(bin, "opencode"), "#!/bin/sh\n");
    chmodSync(join(bin, "opencode"), 0o755);
    const configHome = scratch("caztor-config-");

    const first = await open(project, bin, configHome);
    expect((await first.call("PUT", "/api/providers/opencode/model", { model: "openai/gpt-5.5" })).status).toBe(200);
    expect((await first.call("PUT", "/api/credentials/opencode:openai", { key: "sk-openai-9999aaaa" })).status).toBe(200);
    expect((await first.call("PUT", "/api/providers/opencode/auth-mode", { mode: "api" })).status).toBe(200);
    await first.server.close();

    const second = await open(project, bin, configHome);
    const listing = (await (await second.call("GET", "/api/providers")).json()) as { providers: Array<{ id: string; auth: { mode: string } }> };
    expect(listing.providers.find((provider) => provider.id === "opencode")?.auth.mode).toBe("api");
    await second.server.close();
  });
});
