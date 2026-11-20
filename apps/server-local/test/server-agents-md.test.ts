import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem } from "@caztor/adapters-local";
import { AGENT_BLOCK_BEGIN as BEGIN, AGENT_BLOCK_END as END } from "@caztor/core";
import { afterEach, describe, expect, it } from "vitest";
import type { Listener, ListenFn } from "../src/listen.ts";
import { startServer } from "../src/server.ts";

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));
const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

async function start(createdByCaztor: boolean | null, content: "block" | "rewritten" = "block") {
  const dir = mkdtempSync(join(tmpdir(), "caztor-agents-md-"));
  dirs.push(dir);
  writeFileSync(join(dir, "main.tex"), "m");
  writeFileSync(join(dir, "AGENTS.md"), content === "block" ? `${BEGIN}\nrules\n${END}\n` : "rewritten by the user\n");
  if (createdByCaztor !== null) {
    mkdirSync(join(dir, ".caztor"));
    const hash = `sha256:${createHash("sha256").update("rules\n").digest("hex")}`;
    writeFileSync(join(dir, ".caztor", "state.json"), JSON.stringify({ provisioned: { "AGENTS.md": { hash, createdByCaztor } } }));
  }
  const handlers: Array<(request: Request) => Response | Promise<Response>> = [];
  const listen: ListenFn = async ({ port, fetch }) => {
    handlers.push(fetch);
    return { port, close: async () => {} } satisfies Listener;
  };
  const server = await startServer({ projectDir: dir, webRoot, env: {}, fs: nodeFileSystem, listen, watcher: { watch: () => () => {} } });
  const host = `127.0.0.1:${server.port}`;
  const get = async (path: string) => handlers[0]!(new Request(`http://${host}${path}`, { headers: { host, "x-caztor-token": server.token } }));
  return { server, get };
}

describe("AGENTS.md created by Caztor, through the running server", () => {
  it("is hidden from the tree and refused by the file API when state says Caztor created it", async () => {
    const { server, get } = await start(true);
    const tree = (await (await get("/api/files")).json()) as { entries: { path: string }[] };
    expect(tree.entries.map((entry) => entry.path)).toEqual(["main.tex"]);
    expect((await get("/api/files/content?path=AGENTS.md")).status).toBe(403);
    await server.close();
  });

  it("is shown at once when the user rewrote it outside the app, although the state still says Caztor created it", async () => {
    const { server, get } = await start(true, "rewritten");
    const tree = (await (await get("/api/files")).json()) as { entries: { path: string }[] };
    expect(tree.entries.map((entry) => entry.path)).toEqual(["AGENTS.md", "main.tex"]);
    expect((await get("/api/files/content?path=AGENTS.md")).status).toBe(200);
    await server.close();
  });

  it("is shown and readable when the user wrote it, or when there is no record", async () => {
    for (const flag of [false, null]) {
      const { server, get } = await start(flag);
      const tree = (await (await get("/api/files")).json()) as { entries: { path: string }[] };
      expect(tree.entries.map((entry) => entry.path)).toEqual(["AGENTS.md", "main.tex"]);
      expect((await get("/api/files/content?path=AGENTS.md")).status).toBe(200);
      await server.close();
    }
  });
});
