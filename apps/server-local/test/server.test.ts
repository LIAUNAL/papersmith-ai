import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem } from "@caztor/adapters-local";
import { afterEach, describe, expect, it } from "vitest";
import { bindWithFallback, DEFAULT_PORT, LOOPBACK, type Listener, type ListenFn } from "../src/listen.ts";
import { startServer } from "../src/server.ts";

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));

function addressInUse(): Error {
  return Object.assign(new Error("listen EADDRINUSE"), { code: "EADDRINUSE" });
}

/** A listen function that records its calls and refuses the ports in `busy`. */
function fakeListen(busy: readonly number[] = []) {
  const calls: { port: number; hostname: string }[] = [];
  const handlers: ((request: Request) => Response | Promise<Response>)[] = [];
  let closed = 0;
  const listen: ListenFn = async ({ port, hostname, fetch }) => {
    calls.push({ port, hostname });
    if (busy.includes(port)) throw addressInUse();
    handlers.push(fetch);
    const listener: Listener = { port, close: async () => void (closed += 1) };
    return listener;
  };
  return { listen, calls, handlers, closedCount: () => closed };
}

describe("bindWithFallback", () => {
  it("binds the loopback address on the default port", async () => {
    const { listen, calls } = fakeListen();
    const listener = await bindWithFallback(listen, () => new Response("ok"));
    expect(calls).toEqual([{ port: 4317, hostname: "127.0.0.1" }]);
    expect(LOOPBACK).toBe("127.0.0.1");
    expect(DEFAULT_PORT).toBe(4317);
    expect(listener.port).toBe(4317);
  });

  it("moves to the next free port when the default is busy", async () => {
    const { listen, calls } = fakeListen([4317, 4318]);
    const listener = await bindWithFallback(listen, () => new Response("ok"));
    expect(calls.map((call) => call.port)).toEqual([4317, 4318, 4319]);
    expect(listener.port).toBe(4319);
  });

  it("never binds anything but the loopback address, on any attempt", async () => {
    const { listen, calls } = fakeListen([4317, 4318]);
    await bindWithFallback(listen, () => new Response("ok"));
    expect(calls.every((call) => call.hostname === "127.0.0.1")).toBe(true);
  });

  it("fails on an error that is not a busy port", async () => {
    const listen: ListenFn = async () => {
      throw Object.assign(new Error("denied"), { code: "EACCES" });
    };
    await expect(bindWithFallback(listen, () => new Response("ok"))).rejects.toThrow("denied");
  });

  it("gives up after the attempt limit with a readable message", async () => {
    const busy = Array.from({ length: 20 }, (_, i) => 4317 + i);
    const { listen, calls } = fakeListen(busy);
    await expect(bindWithFallback(listen, () => new Response("ok"))).rejects.toThrow(/no free port/i);
    expect(calls.length).toBeLessThanOrEqual(20);
  });
});

describe("startServer", () => {
  const dirs: string[] = [];
  afterEach(() => {
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });
  const project = () => {
    const dir = mkdtempSync(join(tmpdir(), "caztor-main-"));
    dirs.push(dir);
    return dir;
  };

  async function start(env: Record<string, string> = {}, busy: readonly number[] = []) {
    const fake = fakeListen(busy);
    const server = await startServer({ projectDir: project(), webRoot, env, fs: nodeFileSystem, listen: fake.listen });
    const request = (path: string, headers: Record<string, string>) =>
      fake.handlers[0]!(new Request(`http://${headers["host"]}${path}`, { headers }));
    return { ...fake, server, request };
  }

  it("serves the page on the bound port with a generated token that is not from the environment", async () => {
    const { server, request } = await start({ CAZTOR_TOKEN: "x".repeat(32) });
    const html = await (await request("/", { host: `127.0.0.1:${server.port}` })).text();
    expect(html).toContain(`content="${server.token}"`);
    expect(server.token).toMatch(/^[0-9a-f]{64}$/);
    expect(html).not.toContain("x".repeat(32));
  });

  it("honors the environment token only with CAZTOR_DEV=1", async () => {
    const supplied = "dev-token-0123456789abcdef";
    expect((await start({ CAZTOR_DEV: "1", CAZTOR_TOKEN: supplied })).server.token).toBe(supplied);
    expect((await start({ CAZTOR_TOKEN: supplied })).server.token).not.toBe(supplied);
  });

  it("allows the Host of the port it actually bound, after a fallback", async () => {
    const { server, request } = await start({}, [4317]);
    expect(server.port).toBe(4318);
    expect((await request("/", { host: "127.0.0.1:4318" })).status).toBe(200);
    expect((await request("/", { host: "localhost:4318" })).status).toBe(200);
    expect((await request("/", { host: "127.0.0.1:4317" })).status).toBe(403);
    expect((await request("/", { host: "evil.example" })).status).toBe(403);
  });

  it("mounts the API behind the token: 401 without it, the session with it", async () => {
    const { server, request } = await start();
    const host = `127.0.0.1:${server.port}`;
    expect((await request("/api/session", { host })).status).toBe(401);
    const response = await request("/api/session", { host, "x-caztor-token": server.token });
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ project: { name: expect.stringMatching(/^caztor-main-/) } });
  });

  it("reports the loopback URL and closes the listener", async () => {
    const { server, closedCount } = await start();
    expect(server.url).toBe(`http://127.0.0.1:${server.port}`);
    await server.close();
    expect(closedCount()).toBe(1);
  });

  it("refuses a project folder that does not exist or is a file", async () => {
    const dir = project();
    writeFileSync(join(dir, "file.txt"), "x");
    const base = { webRoot, env: {}, fs: nodeFileSystem, listen: fakeListen().listen };
    await expect(startServer({ ...base, projectDir: join(dir, "missing") })).rejects.toThrow(/project folder/i);
    await expect(startServer({ ...base, projectDir: join(dir, "file.txt") })).rejects.toThrow(/not a folder/i);
  });
});
