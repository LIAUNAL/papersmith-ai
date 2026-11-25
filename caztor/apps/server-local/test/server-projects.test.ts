import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem } from "@caztor/adapters-local";
import type { AgentEvent, AgentRunnerPort } from "@caztor/core";
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
  const dir = realpathSync(mkdtempSync(join(tmpdir(), prefix)));
  dirs.push(dir);
  return dir;
};
interface Listing {
  projects: Array<{ path: string; name: string; kind: string; active: boolean; title?: string; missingMain?: boolean }>;
}

async function open(options: { runners?: Partial<Record<"claude", AgentRunnerPort>> } = {}) {
  const home = scratch("caztor-home-");
  const first = join(home, "first");
  mkdirSync(first);
  writeFileSync(join(first, "first.tex"), "one");
  const paper = join(home, "papers", "spin");
  mkdirSync(join(paper, "paper"), { recursive: true });
  writeFileSync(join(paper, "papersmith.yaml"), "title: Spin\n");
  writeFileSync(join(paper, "paper", "main.tex"), "two");
  const handlers: Array<(request: Request) => Response | Promise<Response>> = [];
  const listen: ListenFn = async ({ port, fetch }) => {
    handlers.push(fetch);
    return { port, close: async () => {} } satisfies Listener;
  };
  const server = await startServer({
    projectDir: first,
    webRoot,
    env: { PATH: "/none", HOME: home, TMPDIR: tmpdir() },
    fs: nodeFileSystem,
    listen,
    watcher: { watch: () => () => {} },
    spawner: new ScriptedSpawner(),
    ...(options.runners === undefined ? {} : { runners: options.runners }),
  });
  const host = `127.0.0.1:${server.port}`;
  const call = async (method: string, path: string, body?: unknown, token: string = server.token, project?: string) =>
    handlers[0]!(
      new Request(`http://${host}${path}`, {
        method,
        headers: { host, "x-caztor-token": token, ...(project === undefined ? {} : { "x-caztor-project": project }), ...(method === "GET" ? {} : { origin: `http://${host}`, "content-type": "application/json" }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      }),
    );
  const names = async () => ((await (await call("GET", "/api/files")).json()) as { entries: Array<{ path: string }> }).entries.map((entry) => entry.path);
  return { server, call, home, first, paper, names };
}

describe("switching projects", () => {
  it("lists the running project and the workspaces, marking the active one", async () => {
    const { server, call, first, paper } = await open();
    const listing = (await (await call("GET", "/api/projects")).json()) as Listing;
    expect(listing.projects).toEqual([
      { path: first, name: "first", kind: "folder", active: true },
      { path: paper, name: "spin", kind: "papersmith", title: "Spin", active: false },
    ]);
    await server.close();
  });

  it("serves the other project's files and session after a switch, tells open pages, and remembers it", async () => {
    const { server, call, first, paper, names } = await open();
    expect(await names()).toContain("first.tex");
    const stream = await call("GET", "/api/events");
    const reader = stream.body!.getReader();

    const switched = await call("POST", "/api/projects/open", { path: paper });
    expect(switched.status).toBe(200);
    expect(((await switched.json()) as Listing).projects.find((entry) => entry.active)?.path).toBe(paper);
    expect(await names()).toContain("paper/main.tex");
    expect(await names()).not.toContain("first.tex");
    expect(((await (await call("GET", "/api/session")).json()) as { project: { name: string } }).project.name).toBe("spin");
    expect(server.root).toBe(paper);

    let seen = "";
    while (!seen.includes("project_changed")) seen += new TextDecoder().decode((await reader.read()).value);
    await reader.cancel();

    await call("POST", "/api/projects/open", { path: first });
    expect(((await (await call("GET", "/api/projects")).json()) as Listing).projects.find((entry) => entry.active)?.path).toBe(first);
    await server.close();
  });

  it("compiles paper/main.tex when that is PaperSmith's main file", async () => {
    const { server, call, paper } = await open();
    await call("POST", "/api/projects/open", { path: paper });
    const answer = await call("POST", "/api/compile", {});
    expect(await answer.text()).not.toContain("no_main_file");
    await server.close();
  });

  it.each([
    ["a relative path", "papers/spin", 400, "invalid_path"],
    ["no path", undefined, 400, "invalid_path"],
    ["a missing folder", "/does/not/exist", 404, "not_found"],
    ["the root folder", "/", 403, "folder_refused"],
  ])("refuses %s, and keeps the project open", async (_label, path, status, error) => {
    const { server, call, names } = await open();
    const answer = await call("POST", "/api/projects/open", { path });
    expect(answer.status).toBe(status);
    expect(await answer.json()).toMatchObject({ error, message: expect.any(String) });
    expect(await names()).toContain("first.tex");
    await server.close();
  });

  it("refuses the home folder and a file, and accepts ~/ paths", async () => {
    const { server, call, home, first, paper } = await open();
    expect((await call("POST", "/api/projects/open", { path: home })).status).toBe(403);
    expect((await call("POST", "/api/projects/open", { path: "~" })).status).toBe(403);
    expect((await call("POST", "/api/projects/open", { path: join(first, "first.tex") })).status).toBe(404);
    expect((await call("POST", "/api/projects/open", { path: "~/papers/spin" })).status).toBe(200);
    expect(server.root).toBe(paper);
    await server.close();
  });

  it("refuses a parent of the home folder and a hidden folder inside it", async () => {
    const { server, call, home, names } = await open();
    mkdirSync(join(home, ".ssh"));
    expect((await call("POST", "/api/projects/open", { path: join(home, "..") })).status).toBe(403);
    expect((await call("POST", "/api/projects/open", { path: "~/.ssh" })).status).toBe(403);
    expect(await names()).toContain("first.tex");
    await server.close();
  });

  it("refuses a request meant for the project that was open before, and tells it apart from a current one", async () => {
    const { server, call, paper, first } = await open();
    const session = (await (await call("GET", "/api/session")).json()) as { project: { id: string } };
    await call("POST", "/api/projects/open", { path: paper });
    const before = await nodeFileSystem.readFile(join(paper, "paper", "main.tex"));
    const stale = await call("PUT", "/api/files/content?path=paper/main.tex", { content: "meant for the other", baseHash: null }, undefined, session.project.id);
    expect(stale.status).toBe(409);
    expect(await stale.json()).toMatchObject({ error: "project_changed", message: expect.any(String) });
    expect(await nodeFileSystem.readFile(join(paper, "paper", "main.tex"))).toEqual(before);

    const current = (await (await call("GET", "/api/session")).json()) as { project: { id: string } };
    expect(current.project.id).not.toBe(session.project.id);
    expect((await call("GET", "/api/files", undefined, undefined, current.project.id)).status).toBe(200);
    expect(first).toBeTruthy();
    await server.close();
  });

  it("creates a project in the papers folder with a main.tex, opens it, and lists it", async () => {
    const { server, call, home, names } = await open();
    const answer = await call("POST", "/api/projects/create", { name: "my-thesis_2" });
    expect(answer.status).toBe(200);
    const created = join(home, "papers", "my-thesis_2");
    expect(((await answer.json()) as Listing).projects.find((entry) => entry.active)).toMatchObject({ path: created, name: "my-thesis_2", kind: "folder" });
    expect(server.root).toBe(created);
    expect(await names()).toEqual(["main.tex"]);
    expect(readFileSync(join(created, "main.tex"), "utf8")).toContain("\\documentclass");
    await server.close();
  });

  it("creates the papers folder when it does not exist yet", async () => {
    const { server, call, home, paper } = await open();
    rmSync(join(home, "papers"), { recursive: true, force: true });
    expect(existsSync(paper)).toBe(false);
    expect((await call("POST", "/api/projects/create", { name: "first-one" })).status).toBe(200);
    expect(existsSync(join(home, "papers", "first-one", "main.tex"))).toBe(true);
    await call("POST", "/api/projects/open", { path: join(home, "first") });
    await server.close();
  });

  it.each([["../escape"], ["a/b"], [".hidden"], ["-flag"], [""], [" "], ["a\\b"], ["a\u0000b"], [".."], ["x".repeat(101)], [7], [undefined]])("refuses the name %j, and creates nothing", async (name) => {
    const { server, call, home, names } = await open();
    const before = readdirSync(home).sort();
    const papers = readdirSync(join(home, "papers")).sort();
    const answer = await call("POST", "/api/projects/create", { name });
    expect(answer.status).toBe(400);
    expect(await answer.json()).toMatchObject({ error: "invalid_name", message: expect.any(String) });
    expect(readdirSync(home).sort()).toEqual(before);
    expect(readdirSync(join(home, "papers")).sort()).toEqual(papers);
    expect(await names()).toContain("first.tex");
    await server.close();
  });

  it("says it cannot create when the papers folder is really a file, not that the name is taken", async () => {
    const { server, call, home } = await open();
    rmSync(join(home, "papers"), { recursive: true, force: true });
    writeFileSync(join(home, "papers"), "x");
    const answer = await call("POST", "/api/projects/create", { name: "thesis" });
    expect(answer.status).toBe(503);
    expect(await answer.json()).toMatchObject({ error: "not_available" });
    await server.close();
  });

  it("refuses a name in use, and leaves that folder as it was", async () => {
    const { server, call, paper, names } = await open();
    const answer = await call("POST", "/api/projects/create", { name: "spin" });
    expect(answer.status).toBe(409);
    expect(await answer.json()).toMatchObject({ error: "exists", message: expect.stringContaining("spin") });
    expect(existsSync(join(paper, "main.tex"))).toBe(false);
    expect(await names()).toContain("first.tex");
    await server.close();
  });

  it("needs the launch token", async () => {
    const { server, call, paper, names } = await open();
    expect((await call("POST", "/api/projects/open", { path: paper }, "wrong")).status).toBe(401);
    expect((await call("GET", "/api/projects", undefined, "wrong")).status).toBe(401);
    expect(await names()).toContain("first.tex");
    await server.close();
  });

  it("creates nothing while a turn runs", async () => {
    let finish = () => {};
    const ended = new Promise<void>((resolve) => (finish = resolve));
    const runner = {
      provider: "claude",
      isolation: "P2",
      detect: async () => ({ provider: "claude", installed: true, requiresModel: false }),
      async *runTurn(): AsyncGenerator<AgentEvent> {
        await ended;
        yield { type: "done", reason: "completed" };
      },
    } as AgentRunnerPort;
    const { server, call, home } = await open({ runners: { claude: runner } });
    const turn = call("POST", "/api/chat/turns", { provider: "claude", prompt: "Hi" }).then((response) => response.text());
    await expect.poll(async () => (await call("GET", "/api/chat/turns/current")).status).toBe(200);
    expect((await call("POST", "/api/projects/create", { name: "during" })).status).toBe(409);
    expect(existsSync(join(home, "papers", "during"))).toBe(false);
    finish();
    await turn;
    await server.close();
  });

  it("refuses while a turn runs, and allows it once the turn has ended", async () => {
    let finish = () => {};
    const ended = new Promise<void>((resolve) => (finish = resolve));
    const runner: AgentRunnerPort = {
      provider: "claude",
      isolation: "P2",
      detect: async () => ({ provider: "claude", installed: true, requiresModel: false }),
      async *runTurn(): AsyncGenerator<AgentEvent> {
        await ended;
        yield { type: "done", reason: "completed" };
      },
    } as AgentRunnerPort;
    const { server, call, first, paper, names } = await open({ runners: { claude: runner } });
    const turn = call("POST", "/api/chat/turns", { provider: "claude", prompt: "Hi" }).then((response) => response.text());
    await expect.poll(async () => (await call("GET", "/api/chat/turns/current")).status).toBe(200);

    const refused = await call("POST", "/api/projects/open", { path: paper });
    expect(refused.status).toBe(409);
    expect(await refused.json()).toMatchObject({ error: "turn_running", message: expect.stringContaining("Stop") });
    expect(await names()).toContain("first.tex");

    finish();
    await turn;
    expect((await call("POST", "/api/projects/open", { path: paper })).status).toBe(200);
    expect(existsSync(first)).toBe(true);
    await server.close();
  });
});

describe("a PaperSmith workspace", () => {
  const BEGIN = `%% paper-writing block intro.lead begin sha256=${"a".repeat(64)}`;
  const END = "%% paper-writing block intro.lead end";
  const session = async (call: Awaited<ReturnType<typeof open>>["call"]) =>
    ((await (await call("GET", "/api/session")).json()) as { papersmith?: { main: string; exists: boolean } }).papersmith;

  it("names its main file, and a plain project names none", async () => {
    const { server, call, paper } = await open();
    expect(await session(call)).toBeUndefined();
    await call("POST", "/api/projects/open", { path: paper });
    expect(await session(call)).toEqual({ main: "paper/main.tex", exists: true });
    await server.close();
  });

  it("compiles paper/main.tex even when another .tex file sits at the top", async () => {
    const { server, call, paper } = await open();
    writeFileSync(join(paper, "notes.tex"), "x");
    await call("POST", "/api/projects/open", { path: paper });
    expect(await (await call("POST", "/api/compile", {})).text()).not.toContain("notes.tex");
    await server.close();
  });

  it("creates the paper folder as PaperSmith's scaffold does, without touching what exists", async () => {
    const { server, call, paper } = await open();
    rmSync(join(paper, "paper"), { recursive: true });
    mkdirSync(join(paper, "paper"));
    writeFileSync(join(paper, "paper", "refs.bib"), "@kept{}");
    await call("POST", "/api/projects/open", { path: paper });
    expect(await session(call)).toEqual({ main: "paper/main.tex", exists: false });

    const answer = await call("POST", "/api/papersmith/scaffold", {});
    expect(answer.status).toBe(200);
    expect(await answer.json()).toEqual({ created: ["main.tex", "Figures", ".gitkeep"] });
    expect(readFileSync(join(paper, "paper", "main.tex"), "utf8")).toContain("\\title{Spin}");
    expect(readFileSync(join(paper, "paper", "main.tex"), "utf8")).toMatch(/\\begin\{document\}[\s\S]*\\end\{document\}\n$/);
    expect(readFileSync(join(paper, "paper", ".gitkeep"), "utf8")).toBe("");
    expect(readFileSync(join(paper, "paper", "refs.bib"), "utf8")).toBe("@kept{}");
    expect(existsSync(join(paper, "paper", "Figures"))).toBe(true);
    expect(await session(call)).toEqual({ main: "paper/main.tex", exists: true });
    expect(await (await call("POST", "/api/papersmith/scaffold", {})).json()).toEqual({ created: [] });
    await server.close();
  });

  it("refuses to scaffold over an entry of the wrong kind, or through a link, writing nothing", async () => {
    const { server, call, paper, home } = await open();
    rmSync(join(paper, "paper"), { recursive: true });
    mkdirSync(join(paper, "paper"));
    writeFileSync(join(paper, "paper", "Figures"), "a file");
    await call("POST", "/api/projects/open", { path: paper });
    const wrong = await call("POST", "/api/papersmith/scaffold", {});
    expect(wrong.status).toBe(409);
    expect(await wrong.json()).toMatchObject({ error: "scaffold_refused", message: expect.stringContaining("Figures") });
    expect(existsSync(join(paper, "paper", "main.tex"))).toBe(false);

    rmSync(join(paper, "paper"), { recursive: true });
    mkdirSync(join(home, "elsewhere"));
    symlinkSync(join(home, "elsewhere"), join(paper, "paper"));
    expect((await call("POST", "/api/papersmith/scaffold", {})).status).toBe(409);
    expect(readdirSync(join(home, "elsewhere"))).toEqual([]);
    await server.close();
  });

  it("refuses to scaffold outside a workspace", async () => {
    const { server, call } = await open();
    expect((await call("POST", "/api/papersmith/scaffold", {})).status).toBe(404);
    await server.close();
  });

  it("refuses a save that changes or removes a block marker, and accepts one that keeps them", async () => {
    const { server, call, paper } = await open();
    const file = join(paper, "paper", "main.tex");
    const doc = `\\documentclass{article}\n${BEGIN}\nSome text.\n${END}\n`;
    writeFileSync(file, doc);
    await call("POST", "/api/projects/open", { path: paper });
    const read = (await (await call("GET", "/api/files/content?path=paper/main.tex")).json()) as { hash: string };
    const broken = await call("PUT", "/api/files/content?path=paper/main.tex", { content: doc.replace(`${END}\n`, ""), baseHash: read.hash });
    expect(broken.status).toBe(409);
    expect(await broken.json()).toMatchObject({ error: "markers_changed", message: expect.stringContaining("paper-writing") });
    expect(readFileSync(file, "utf8")).toBe(doc);
    const kept = await call("PUT", "/api/files/content?path=paper/main.tex", { content: doc.replace("Some text.", "New text."), baseHash: read.hash });
    expect(kept.status).toBe(200);
    writeFileSync(join(paper, "paper", "Upper.TEX"), doc);
    const upper = (await (await call("GET", "/api/files/content?path=paper/Upper.TEX")).json()) as { hash: string };
    expect((await call("PUT", "/api/files/content?path=paper/Upper.TEX", { content: "gone", baseHash: upper.hash })).status).toBe(409);
    await server.close();
  });
});
