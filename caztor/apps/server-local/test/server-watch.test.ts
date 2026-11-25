import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { hashBytes } from "@caztor/core";
import { nodeFileSystem, type DirectoryWatcher } from "@caztor/adapters-local";
import { afterEach, describe, expect, it } from "vitest";
import type { Listener, ListenFn } from "../src/listen.ts";
import { startServer } from "../src/server.ts";

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));

/** A directory watcher that tests drive by hand and that counts what is open. */
function manualWatcher() {
  const open = new Set<(path: string | null) => void>();
  let starts = 0;
  const watcher: DirectoryWatcher = {
    watch(_dir, listener) {
      starts += 1;
      open.add(listener);
      return () => void open.delete(listener);
    },
  };
  return { watcher, emit: (path: string | null) => open.forEach((listener) => listener(path)), active: () => open.size, starts: () => starts };
}

function fakeListen() {
  const handlers: Array<(request: Request) => Response | Promise<Response>> = [];
  const listen: ListenFn = async ({ port, fetch }) => {
    handlers.push(fetch);
    const listener: Listener = { port, close: async () => {} };
    return listener;
  };
  return { listen, handlers };
}

describe("startServer file watching", () => {
  const dirs: string[] = [];
  afterEach(() => {
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });

  async function start() {
    const dir = mkdtempSync(join(tmpdir(), "caztor-watch-server-"));
    dirs.push(dir);
    writeFileSync(join(dir, "main.tex"), "one");
    const manual = manualWatcher();
    const { listen, handlers } = fakeListen();
    const server = await startServer({ projectDir: dir, webRoot, env: {}, fs: nodeFileSystem, listen, watcher: manual.watcher });
    const host = `127.0.0.1:${server.port}`;
    const events = async () => {
      const response = await handlers[0]!(new Request(`http://${host}/api/events`, { headers: { host, "x-caztor-token": server.token } }));
      return response.body!.getReader();
    };
    return { dir, manual, server, events };
  }

  /** Reads event stream frames until one has the wanted event name, or fails after two seconds. */
  async function frameNamed(reader: ReadableStreamDefaultReader<Uint8Array>, name: string): Promise<string> {
    const decoder = new TextDecoder();
    const limit = Date.now() + 2000;
    let text = "";
    while (Date.now() < limit) {
      const chunk = await Promise.race([reader.read(), new Promise<null>((resolve) => setTimeout(() => resolve(null), 200))]);
      if (chunk === null) continue;
      if (chunk.done) break;
      text += decoder.decode(chunk.value);
      const frame = text.split("\n\n").find((candidate) => candidate.includes(`event: ${name}`));
      if (frame !== undefined) return frame;
    }
    throw new Error(`No ${name} event arrived. Received: ${JSON.stringify(text)}`);
  }

  it("publishes a file_changed event with the new hash when a project file changes", async () => {
    const { dir, manual, server, events } = await start();
    const reader = await events();
    await new Promise((resolve) => setTimeout(resolve, 50));
    writeFileSync(join(dir, "main.tex"), "two");
    manual.emit("main.tex");
    const frame = await frameNamed(reader, "file_changed");
    const data = JSON.parse(frame.split("\n").find((line) => line.startsWith("data: "))!.slice(6)) as unknown;
    expect(data).toEqual({ path: "main.tex", hash: await hashBytes(new TextEncoder().encode("two")) });
    await reader.cancel();
    await server.close();
  });

  it("stops watching when the server stops", async () => {
    const { manual, server } = await start();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(manual.active()).toBe(1);
    await server.close();
    expect(manual.active()).toBe(0);
  });

  it("watches only the project folder, once", async () => {
    const { manual, server } = await start();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(manual.starts()).toBe(1);
    await server.close();
  });
});
