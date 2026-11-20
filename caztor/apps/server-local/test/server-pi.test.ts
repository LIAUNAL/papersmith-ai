import { chmodSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
const turnLines = readFileSync(fileURLToPath(new URL("../../../packages/adapters-local/test/providers/pi/fixtures/synthetic-edit-turn.jsonl", import.meta.url)), "utf8")
  .split("\n")
  .filter((line) => line !== "")
  .map((line) => `${line}\n`);
const SESSION_1 = "00000000-0000-4000-8000-000000000001";
const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});
const ok = { code: 0, signal: null };

async function start(options: { installed?: boolean } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "caztor-server-pi-"));
  dirs.push(dir);
  writeFileSync(join(dir, "main.tex"), "The cat sat on the mat.");
  const bin = mkdtempSync(join(tmpdir(), "caztor-bin-"));
  dirs.push(bin);
  if (options.installed !== false) {
    writeFileSync(join(bin, "pi"), "#!/bin/sh\n");
    chmodSync(join(bin, "pi"), 0o755);
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
    env: { PATH: bin, HOME: "/home/someone", TMPDIR: tmpdir(), ANTHROPIC_API_KEY: "must-not-leak-0000000" },
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

const piOf = async (call: Awaited<ReturnType<typeof start>>["call"]) =>
  ((await (await call("GET", "/api/providers")).json()) as { providers: Array<Record<string, unknown>> }).providers.find((provider) => provider["id"] === "pi");

describe("the Pi adapter in the running server", () => {
  it("lists Pi as available with its version and signed-in models, in both sign-in modes", async () => {
    const { server, call, spawner } = await start();
    spawner.enqueue({ stdout: ["1.4.0\n"], exit: ok });
    spawner.enqueue({ stdout: ["provider   model              context  max-out  thinking  images\n", "anthropic  claude-sonnet-4-5  200K     64K      yes       yes\n"], exit: ok });
    expect(await piOf(call)).toMatchObject({ installed: true, version: "1.4.0", requiresModel: false, models: ["anthropic/claude-sonnet-4-5"], auth: { modes: ["account", "api"] } });
    await server.close();
  });

  it("lists Pi as not installed when pi is not on the PATH", async () => {
    const { server, call } = await start({ installed: false });
    expect(await piOf(call)).toMatchObject({ installed: false, unavailableReason: "pi was not found on the PATH." });
    await server.close();
  });

  it("runs a turn over HTTP: provisions the prompt in .caztor, never .pi/, keeps keys out, and continues the session", async () => {
    const { server, call, spawner, dir } = await start();
    spawner.enqueue({ stdout: ["1.4.0\n"], exit: ok });
    spawner.enqueue({ stdout: ["No models available.\n"], exit: ok });
    spawner.enqueue({ stdout: turnLines, exit: ok });
    const response = await call("POST", "/api/chat/turns", { provider: "pi", prompt: "Change cat to dog" });
    const text = await response.text();
    const frames = parseFrames(text);
    expect(response.status, text).toBe(200);
    expect(frames.some((frame) => frame.event === "notice" && JSON.stringify(frame.data).includes("partial isolation"))).toBe(true);
    expect(frames.find((frame) => frame.event === "done")).toMatchObject({ data: { reason: "completed" } });
    const run = spawner.calls.find((spawn) => spawn.args.includes("--mode"))!;
    const promptFile = join(dir, ".caztor", "agents", "pi.md");
    expect(run.args.slice(0, 20)).toEqual(["-p", "--mode", "json", "-na", "-ne", "--no-mcp", "-ns", "-np", "--no-themes", "-nc", "--offline", "--tools", "read,edit,write,grep,find,ls", "-xt", "mcp__*", "--system-prompt", promptFile, "--append-system-prompt", "", "--session-id"]);
    expect(run.args.slice(-2)).toEqual(["--session-dir", join(dir, ".caztor", "pi-sessions")]);
    expect(run.stdin).toBe("Change cat to dog");
    expect(Object.keys(run.env)).not.toContain("ANTHROPIC_API_KEY");
    expect(readFileSync(promptFile, "utf8")).toContain("This definition is used when the selected provider is Pi.");
    expect(existsSync(join(dir, ".pi"))).toBe(false);

    spawner.enqueue({ stdout: ["1.4.0\n"], exit: ok });
    spawner.enqueue({ stdout: turnLines, exit: ok });
    await (await call("POST", "/api/chat/turns", { provider: "pi", prompt: "What did you change?" })).text();
    const second = spawner.calls.filter((spawn) => spawn.args.includes("--mode")).at(-1)!;
    expect(second.args[second.args.indexOf("--session-id") + 1]).toBe(SESSION_1);
    await server.close();
  });
});
