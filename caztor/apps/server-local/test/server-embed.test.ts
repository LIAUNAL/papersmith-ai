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
const TWIN = "http://localhost:8765";
const KEY = "frame-key-0123456789-abcdefghijklmnopqrstu";

async function open(embedOrigin?: string | readonly string[], embedKey?: string) {
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
    ...(embedKey === undefined ? {} : { embedKey }),
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
  // A page request as a browser sends it: no token header, only the address (and its query).
  const page = (path: string) => handlers[0]!(new Request(`http://${host}${path}`, { headers: { host } }));
  return { server, call, other, page };
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

  it("lets every name of the dashboard frame it, the session naming the first", async () => {
    const { call, page, server } = await open([SMITH, TWIN]);
    expect(((await (await call("GET", "/api/session")).json()) as { embed?: unknown }).embed).toEqual({ origin: SMITH });
    expect((await page("/")).headers.get("content-security-policy")).toContain(`frame-ancestors ${SMITH} ${TWIN}`);
    await server.close();
    await expect(open([SMITH, "http://127.0.0.1:8765/x"])).rejects.toThrow(/origin/);
    await expect(open([])).rejects.toThrow(/empty/);
  });

  it("with a frame key, serves the page and its launch token only to a request carrying that key", async () => {
    const { page, server } = await open([SMITH, TWIN], KEY);
    const keyed = await page(`/?k=${encodeURIComponent(KEY)}`);
    expect(keyed.status).toBe(200);
    expect(await keyed.text()).toContain(`<meta name="caztor-token" content="${server.token}" />`);
    for (const path of ["/", "/?k=", `/?k=${KEY}x`, `/?k=${KEY.slice(0, -1)}`, `/?key=${KEY}`]) {
      const refused = await page(path);
      expect(refused.status, path).toBe(401);
      const text = await refused.text();
      expect(text).not.toContain(server.token);
      expect(text).toContain("PaperSmith dashboard");
    }
    await server.close();
  });

  it("refuses a frame key that is too short or given without an embedding origin, never echoing it", async () => {
    await expect(open(SMITH, "short-secret")).rejects.toThrow(/at least 16 characters/);
    await expect(open(SMITH, "short-secret")).rejects.not.toThrow(/short-secret/);
    await expect(open(undefined, KEY)).rejects.toThrow(/--embed-origin/);
  });

  it("embedded without a frame key, the page is served as before", async () => {
    const { page, server } = await open(SMITH);
    const served = await page("/");
    expect(served.status).toBe(200);
    expect(await served.text()).toContain(server.token);
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

  it("without it, the page needs no key", async () => {
    const { page, server } = await open();
    const served = await page("/?k=anything");
    expect(served.status).toBe(200);
    expect(await served.text()).toContain(server.token);
    await server.close();
  });
});
