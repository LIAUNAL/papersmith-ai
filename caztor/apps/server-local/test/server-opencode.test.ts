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
const turnFixture = readFileSync(fileURLToPath(new URL("../../../packages/adapters-local/test/providers/opencode/fixtures/edit-turn.jsonl", import.meta.url)), "utf8");
const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});
const ok = { code: 0, signal: null };

async function start(options: { installed?: boolean; files?: Record<string, string> } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "caztor-server-opencode-"));
  dirs.push(dir);
  writeFileSync(join(dir, "main.tex"), "Hello world.");
  for (const [name, text] of Object.entries(options.files ?? {})) writeFileSync(join(dir, name), text);
  const bin = mkdtempSync(join(tmpdir(), "caztor-bin-"));
  dirs.push(bin);
  if (options.installed !== false) {
    writeFileSync(join(bin, "opencode"), "#!/bin/sh\n");
    chmodSync(join(bin, "opencode"), 0o755);
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
    env: { PATH: bin, HOME: "/home/someone", GITHUB_TOKEN: "must-not-leak", OPENCODE_CONFIG_CONTENT: "{}" },
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

describe("the opencode adapter in the running server", () => {
  it("lists opencode as available with its version and a model list, looking at nothing of the user's own setup", async () => {
    const { server, call, spawner } = await start();
    spawner.enqueue({ stdout: ["1.19.0\n"], exit: ok });
    spawner.enqueue({ stdout: ["openai/gpt-5.5\n"], exit: ok });

    const body = (await (await call("GET", "/api/providers")).json()) as { providers: Array<Record<string, unknown>> };
    const opencode = body.providers.find((provider) => provider["id"] === "opencode");

    expect(opencode).toMatchObject({ installed: true, version: "1.19.0", requiresModel: true, models: ["openai/gpt-5.5"], model: null });
    expect(opencode).not.toHaveProperty("note");
    expect(body.providers.find((provider) => provider["id"] === "claude")).toMatchObject({ installed: false });
    expect(spawner.calls.map((call) => call.args)).toEqual([["--version"], ["--pure", "models"]]);
    await server.close();
  });

  it("lists opencode as not installed, with the reason, when it is not on the PATH", async () => {
    const { server, call } = await start({ installed: false });
    const body = (await (await call("GET", "/api/providers")).json()) as { providers: Array<Record<string, unknown>> };
    expect(body.providers.find((provider) => provider["id"] === "opencode")).toMatchObject({ installed: false, unavailableReason: "opencode was not found on the PATH." });
    await server.close();
  });

  it("does not start a turn without a model, and says so", async () => {
    const { server, call, spawner } = await start();
    spawner.enqueue({ stdout: ["1.19.0\n"], exit: ok });
    const response = await call("POST", "/api/chat/turns", { provider: "opencode", prompt: "Say hi" });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "model_required", message: expect.stringContaining("Choose a model for opencode") });
    expect(spawner.calls.every((spawn) => spawn.args[0] !== "run")).toBe(true);
    await server.close();
  });

  it("runs a chat turn end to end: provisions the agent file, passes the model and the prompt on stdin, streams whole blocks, hides the user's configuration", async () => {
    const { server, call, spawner, dir } = await start();
    expect((await call("PUT", "/api/providers/opencode/model", { model: "openai/gpt-5.5" })).status).toBe(200);
    spawner.enqueue({ stdout: ["1.19.0\n"], exit: ok });
    spawner.enqueue({ stdout: ["openai/gpt-5.5\n"], exit: ok });
    spawner.enqueue({ stdout: turnFixture.split("\n").filter((line) => line !== "").map((line) => `${line}\n`), exit: ok });

    const response = await call("POST", "/api/chat/turns", { provider: "opencode", prompt: "Say hi instead of hello" });
    const text = await response.text();
    const frames = parseFrames(text);
    expect(response.status, text).toBe(200);

    expect(frames[0]?.event).toBe("turn_started");
    expect(frames.map((frame) => frame.event)).toContain("text");
    expect(frames.map((frame) => frame.event)).not.toContain("text_delta");
    expect(frames.at(-2)).toMatchObject({ event: "done", data: { reason: "completed" } });
    expect(frames.at(-1)?.event).toBe("files_changed");
    const run = spawner.calls.find((spawn) => spawn.args[0] === "run")!;
    expect(run.cwd).toBe(dir);
    expect(run.stdin).toBe("Say hi instead of hello");
    expect(run.args).toEqual(["run", "--format", "json", "--agent", "caztor", "--pure", "-m", "openai/gpt-5.5", "--dir", dir]);
    expect(Object.keys(run.env)).not.toContain("GITHUB_TOKEN");
    expect(Object.keys(run.env)).not.toContain("OPENCODE_CONFIG_CONTENT");
    expect(run.env["XDG_CONFIG_HOME"]).toBe(`${dir}/.caztor/opencode-xdg`);
    const agentFile = join(dir, ".opencode", "agents", "caztor.md");
    expect(existsSync(agentFile)).toBe(true);
    expect(readFileSync(agentFile, "utf8")).toContain("bash: deny");
    await server.close();
  });

  it("refuses a turn while the project's opencode.json can run programs, until the user trusts exactly those files", async () => {
    const mcp = '{"mcp":{"x":{"type":"local","command":["touch","/tmp/X"]}}}';
    const { server, call, spawner } = await start({ files: { "opencode.json": mcp } });
    expect((await call("PUT", "/api/providers/opencode/model", { model: "openai/gpt-5.5" })).status).toBe(200);
    spawner.enqueue({ stdout: ["1.19.0\n"], exit: ok });
    spawner.enqueue({ stdout: ["openai/gpt-5.5\n"], exit: ok });

    const listed = (await (await call("GET", "/api/providers")).json()) as { providers: Array<Record<string, any>> };
    const config = listed.providers.find((provider) => provider["id"] === "opencode")?.["projectConfig"];
    expect(config).toEqual({ files: ["opencode.json"], confirmed: false, fingerprint: expect.stringMatching(/^sha256:/) });

    const refused = await call("POST", "/api/chat/turns", { provider: "opencode", prompt: "Say hi" });
    expect(await refused.text()).toContain("isolation_failed");
    expect(spawner.calls.some((spawn) => spawn.args[0] === "run")).toBe(false);

    const fingerprint = (config as { fingerprint: string }).fingerprint;
    expect(fingerprint).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect((await call("POST", "/api/providers/opencode/project-config/trust", { fingerprint })).status).toBe(200);
    spawner.enqueue({ stdout: ["1.19.0\n"], exit: ok });
    spawner.enqueue({ stdout: ["openai/gpt-5.5\n"], exit: ok });
    spawner.enqueue({ stdout: turnFixture.split("\n").filter((line) => line !== "").map((line) => `${line}\n`), exit: ok });
    const allowed = await (await call("POST", "/api/chat/turns", { provider: "opencode", prompt: "Say hi" })).text();
    expect(allowed).not.toContain("isolation_failed");
    expect(spawner.calls.some((spawn) => spawn.args[0] === "run")).toBe(true);
    await server.close();
  });

  it("does not count a trust record written into the project's state by someone who can write the project", async () => {
    const mcp = '{"mcp":{"x":{"type":"local","command":["touch","/tmp/X"]}}}';
    const { server, call, spawner, dir } = await start({ files: { "opencode.json": mcp } });
    expect((await call("PUT", "/api/providers/opencode/model", { model: "openai/gpt-5.5" })).status).toBe(200);
    spawner.enqueue({ stdout: ["1.19.0\n"], exit: ok });
    spawner.enqueue({ stdout: ["openai/gpt-5.5\n"], exit: ok });
    const listed = (await (await call("GET", "/api/providers")).json()) as { providers: Array<Record<string, any>> };
    const fingerprint = listed.providers.find((provider) => provider["id"] === "opencode")?.["projectConfig"]?.["fingerprint"] as string;
    // The fingerprint is a plain hash of the files, so anyone who can write the project can compute it and forge the record.
    const statePath = join(dir, ".caztor", "state.json");
    const state = JSON.parse(readFileSync(statePath, "utf8")) as Record<string, unknown>;
    writeFileSync(statePath, JSON.stringify({ ...state, projectCliConfigTrusted: { opencode: fingerprint } }));
    const again = (await (await call("GET", "/api/providers")).json()) as { providers: Array<Record<string, any>> };
    expect(again.providers.find((provider) => provider["id"] === "opencode")?.["projectConfig"]?.["confirmed"]).toBe(false);
    spawner.enqueue({ stdout: ["1.19.0\n"], exit: ok });
    spawner.enqueue({ stdout: ["openai/gpt-5.5\n"], exit: ok });
    expect(await (await call("POST", "/api/chat/turns", { provider: "opencode", prompt: "Say hi" })).text()).toContain("isolation_failed");
    expect(spawner.calls.some((spawn) => spawn.args[0] === "run")).toBe(false);
    await server.close();
  });
});
