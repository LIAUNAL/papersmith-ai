import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
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

const SMITH = "http://127.0.0.1:8765";

async function open(embedOrigin?: string) {
  const home = realpathSync(mkdtempSync(join(tmpdir(), "caztor-embed-")));
  dirs.push(home);
  const paper = join(home, "papers", "spin");
  mkdirSync(join(paper, "paper"), { recursive: true });
  writeFileSync(join(paper, "papersmith.yaml"), "title: Spin\n");
  writeFileSync(join(paper, "paper", "main.tex"), "two");
  const other = join(home, "papers", "other");
  mkdirSync(other);
  const handlers: Array<(request: Request) => Response | Promise<Response>> = [];
  const listen: ListenFn = async ({ port, fetch }) => {
    handlers.push(fetch);
    return { port, close: async () => {} } satisfies Listener;
  };
  const server = await startServer({
    projectDir: paper,
    webRoot,
    env: { PATH: "/none", HOME: home, TMPDIR: tmpdir() },
    fs: nodeFileSystem,
    listen,
    watcher: { watch: () => () => {} },
    spawner: new ScriptedSpawner(),
    ...(embedOrigin === undefined ? {} : { embedOrigin }),
  });
  const host = `127.0.0.1:${server.port}`;
  const call = (method: string, path: string, body?: unknown) =>
    handlers[0]!(
      new Request(`http://${host}${path}`, {
        method,
        headers: { host, "x-caztor-token": server.token, ...(method === "GET" ? {} : { origin: `http://${host}`, "content-type": "application/json" }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      }),
    );
  return { server, call, other };
}

describe("embedded in a PaperSmith dashboard", () => {
  it("names the embedding origin in the session and lets only that origin frame the pages", async () => {
    const { call, server } = await open(SMITH);
    const session = (await (await call("GET", "/api/session")).json()) as { embed?: { origin: string } };
    expect(session.embed).toEqual({ origin: SMITH });
    const page = await call("GET", "/");
    expect(page.headers.get("content-security-policy")).toContain(`frame-ancestors ${SMITH}`);
    expect(page.headers.get("content-security-policy")).not.toContain("frame-ancestors 'none'");
    await server.close();
  });

  it("stays on its one project: listing, opening and creating projects are refused", async () => {
    const { call, other, server } = await open(SMITH);
    expect((await call("GET", "/api/projects")).status).toBe(503);
    const opened = await call("POST", "/api/projects/open", { path: other });
    expect(opened.status).toBe(503);
    expect((await call("POST", "/api/projects/create", { name: "fresh" })).status).toBe(503);
    expect(((await (await call("GET", "/api/session")).json()) as { project: { name: string } }).project.name).toBe("spin");
    await server.close();
  });

  it("refuses an embedding origin that is not a plain http(s) origin", async () => {
    await expect(open("http://127.0.0.1:8765/path")).rejects.toThrow(/origin/);
    await expect(open("javascript:alert(1)")).rejects.toThrow(/origin/);
  });

  it("without it, nothing changes: no embed field, no framing, projects can be switched", async () => {
    const { call, server } = await open();
    const session = (await (await call("GET", "/api/session")).json()) as { embed?: unknown };
    expect(session.embed).toBeUndefined();
    expect((await call("GET", "/")).headers.get("content-security-policy")).toContain("frame-ancestors 'none'");
    expect((await call("GET", "/api/projects")).status).toBe(200);
    await server.close();
  });
});
