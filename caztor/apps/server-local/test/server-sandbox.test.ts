import { chmodSync, mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem, type ChildHandle, type ProcessSpawner, type SpawnSpec } from "@caztor/adapters-local";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Listener, ListenFn } from "../src/listen.ts";
import { startServer } from "../src/server.ts";

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));

/** Answers every spawn from `answer`; the output is delivered and the child exits at once. */
function spawnerFor(answer: (spec: SpawnSpec) => { stdout?: string; stderr?: string; code?: number }) {
  const calls: SpawnSpec[] = [];
  const spawner: ProcessSpawner = {
    spawn(spec): ChildHandle {
      calls.push(spec);
      const plan = answer(spec);
      const chunk = (text?: string) =>
        (async function* () {
          if (text !== undefined) yield new TextEncoder().encode(text);
        })();
      return {
        stdout: chunk(plan.stdout),
        stderr: chunk(plan.stderr),
        exit: Promise.resolve({ code: plan.code ?? 0, signal: null }),
        killGroup() {},
      };
    },
  };
  return { spawner, calls };
}

describe("startServer sandbox wiring", () => {
  const dirs: string[] = [];
  afterEach(() => {
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });

  async function start(spawner: ProcessSpawner, withBwrap: boolean) {
    const dir = realpathSync(mkdtempSync(join(tmpdir(), "caztor-sandbox-server-")));
    dirs.push(dir);
    const bin = join(dir, "bin");
    mkdirSync(bin);
    for (const name of withBwrap ? ["bwrap", "tectonic"] : ["tectonic"]) {
      writeFileSync(join(bin, name), "#!/bin/sh\n");
      chmodSync(join(bin, name), 0o755);
    }
    const project = join(dir, "project");
    mkdirSync(project);
    writeFileSync(join(project, "main.tex"), "\\documentclass{article}");
    const handlers: Array<(request: Request) => Response | Promise<Response>> = [];
    const listen: ListenFn = async ({ port, fetch }) => {
      handlers.push(fetch);
      const listener: Listener = { port, close: async () => {} };
      return listener;
    };
    const server = await startServer({
      projectDir: project,
      webRoot,
      env: { PATH: bin, HOME: join(dir, "home") },
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
    return { bin, call };
  }

  const tectonic = (spec: SpawnSpec) => (spec.args.at(-1) === "--version" ? { stdout: "Tectonic 0.17.0\n" } : { code: 1 });

  it("lists the sandbox as available once the trial run inside bwrap answers", async () => {
    const { spawner } = spawnerFor((spec) => (spec.file === "ldd" ? { stdout: "" } : tectonic(spec)));
    const { call } = await start(spawner, true);
    const body = (await (await call("GET", "/api/session")).json()) as { sandbox: unknown; settings: { sandboxedCompile: boolean } };
    expect(body.sandbox).toEqual({ available: true, version: "bubblewrap, Tectonic 0.17.0" });
    expect(body.settings.sandboxedCompile).toBe(false);
  });

  it("lists the sandbox as unavailable, with the reason, when bwrap is not installed", async () => {
    const { spawner } = spawnerFor(tectonic);
    const { call } = await start(spawner, false);
    const body = (await (await call("GET", "/api/session")).json()) as { sandbox: { available: boolean; reason: string } };
    expect(body.sandbox.available).toBe(false);
    expect(body.sandbox.reason).toMatch(/bwrap/);
  });

  it("compiles unsandboxed by default and through bwrap once the project setting is on", async () => {
    const { spawner, calls } = spawnerFor((spec) => (spec.file === "ldd" ? { stdout: "" } : tectonic(spec)));
    const { bin, call } = await start(spawner, true);
    await call("POST", "/api/compile", {});
    await vi.waitFor(() => expect(calls.some((spec) => spec.args.includes("compile"))).toBe(true));
    expect(calls.find((spec) => spec.args.includes("compile"))?.file).toBe("tectonic");

    expect((await call("PATCH", "/api/settings", { sandboxedCompile: true })).status).toBe(200);
    calls.length = 0;
    await call("POST", "/api/compile", {});
    await vi.waitFor(() => expect(calls.some((spec) => spec.file === join(bin, "bwrap") && spec.args.includes("compile"))).toBe(true));
  });
});
