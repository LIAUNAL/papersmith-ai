import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem, type ChildHandle, type ProcessSpawner, type SpawnSpec } from "@caztor/adapters-local";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Listener, ListenFn } from "../src/listen.ts";
import { startServer } from "../src/server.ts";

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));

/** Spawns children that print `stdout` and then either exit at once or stay alive until signalled. */
function scriptedSpawner(script: (spec: SpawnSpec) => { stdout?: string; exit?: { code: number } | "hang" | "missing" }) {
  const calls: SpawnSpec[] = [];
  const signals: string[] = [];
  const spawner: ProcessSpawner = {
    spawn(spec): ChildHandle {
      calls.push(spec);
      const plan = script(spec);
      let finish: (value: { code: number | null; signal: string | null }) => void = () => {};
      let fail: (error: Error) => void = () => {};
      const exit = new Promise<{ code: number | null; signal: string | null }>((resolve, reject) => {
        finish = resolve;
        fail = reject;
      });
      exit.catch(() => {});
      let release: () => void = () => {};
      const ended = new Promise<void>((resolve) => (release = resolve));
      const stdout = (async function* () {
        if (plan.stdout !== undefined) yield new TextEncoder().encode(plan.stdout);
        await ended;
      })();
      const stderr = (async function* () {
        await ended;
      })();
      if (plan.exit === "missing") {
        fail(Object.assign(new Error("spawn tectonic ENOENT"), { code: "ENOENT" }));
        release();
      } else if (plan.exit !== undefined && plan.exit !== "hang") {
        finish({ code: plan.exit.code, signal: null });
        release();
      }
      return {
        stdout,
        stderr,
        exit,
        killGroup(signal) {
          signals.push(signal);
          finish({ code: null, signal });
          release();
        },
      };
    },
  };
  return { spawner, calls, signals };
}

describe("startServer compile wiring", () => {
  const dirs: string[] = [];
  afterEach(() => {
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });

  async function start(spawner: ProcessSpawner, env: Record<string, string> = {}) {
    const dir = mkdtempSync(join(tmpdir(), "caztor-compile-server-"));
    dirs.push(dir);
    writeFileSync(join(dir, "main.tex"), "\\documentclass{article}");
    const handlers: Array<(request: Request) => Response | Promise<Response>> = [];
    const listen: ListenFn = async ({ port, fetch }) => {
      handlers.push(fetch);
      const listener: Listener = { port, close: async () => {} };
      return listener;
    };
    const server = await startServer({
      projectDir: dir,
      webRoot,
      env,
      fs: nodeFileSystem,
      listen,
      spawner,
      watcher: { watch: () => () => {} },
    });
    const host = `127.0.0.1:${server.port}`;
    const origin = `http://${host}`;
    const call = (method: string, path: string, body?: unknown) =>
      Promise.resolve(
        handlers[0]!(
          new Request(`${origin}${path}`, {
            method,
            headers: { host, "x-caztor-token": server.token, ...(method === "GET" ? {} : { origin, "content-type": "application/json" }) },
            ...(body === undefined ? {} : { body: JSON.stringify(body) }),
          }),
        ),
      );
    return { server, call };
  }

  it("reports the engine as available with its version when the probe runs", async () => {
    const { spawner, calls } = scriptedSpawner(() => ({ stdout: "Tectonic 0.17.0\n", exit: { code: 0 } }));
    const { call } = await start(spawner);
    const body = (await (await call("GET", "/api/session")).json()) as { engine: unknown };
    expect(body.engine).toEqual({ available: true, version: "0.17.0" });
    expect(calls[0]?.args).toEqual(["--version"]);
  });

  it("reports the engine as unavailable, and refuses a compile readably, when tectonic is not installed", async () => {
    const { spawner } = scriptedSpawner(() => ({ exit: "missing" }));
    const { call } = await start(spawner);
    expect(((await (await call("GET", "/api/session")).json()) as { engine: unknown }).engine).toEqual({
      available: false,
      reason: "Tectonic was not found on the PATH.",
    });
    const response = await call("POST", "/api/compile", {});
    expect(response.status).toBe(503);
    expect(((await response.json()) as { message: string }).message).toMatch(/tectonic/i);
  });

  it("runs the compile in the project folder with the argv and an environment without the server's secrets", async () => {
    const { spawner, calls } = scriptedSpawner((spec) =>
      spec.args[0] === "--version" ? { stdout: "Tectonic 0.17.0\n", exit: { code: 0 } } : { exit: { code: 1 } },
    );
    const { server, call } = await start(spawner, { PATH: "/usr/bin", ANTHROPIC_API_KEY: "sk-secret", CAZTOR_TOKEN: "t" });
    expect((await call("POST", "/api/compile", {})).status).toBe(202);
    await vi.waitFor(() => expect(calls.some((spec) => spec.args.includes("compile"))).toBe(true));

    const run = calls.find((spec) => spec.args.includes("compile"))!;
    expect(run.file).toBe("tectonic");
    expect(run.cwd).toBe(server.root);
    expect(run.args.slice(0, 3)).toEqual(["-X", "compile", "./main.tex"]);
    expect(run.env).toEqual({ PATH: "/usr/bin", TECTONIC_UNTRUSTED_MODE: "1" });
  });

  it("cancels a running compile when the server closes, and waits for it to end", async () => {
    const { spawner, calls, signals } = scriptedSpawner((spec) =>
      spec.args[0] === "--version" ? { stdout: "Tectonic 0.17.0\n", exit: { code: 0 } } : { exit: "hang" },
    );
    const { server, call } = await start(spawner);
    await call("POST", "/api/compile", {});
    await vi.waitFor(() => expect(calls.some((spec) => spec.args.includes("compile"))).toBe(true));

    await server.close();
    expect(signals).toContain("SIGTERM");
  });
});
