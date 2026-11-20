import { mkdirSync, readFileSync, symlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { hashBytes } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { cleanupProjects, harness } from "./support.ts";

cleanupProjects();

const encode = (text: string) => new TextEncoder().encode(text);
const hashOf = (text: string) => hashBytes(encode(text));
const query = (path: string) => `/api/files/content?path=${encodeURIComponent(path)}`;

describe("GET /api/files", () => {
  it("is rejected without the launch token", async () => {
    const h = harness();
    expect((await h.call("GET", "/api/files", { headers: { "x-caztor-token": "wrong" } })).status).toBe(401);
  });

  it("lists files and folders with sizes, binary files included, and hides reserved folders", async () => {
    const h = harness();
    writeFileSync(join(h.root, "main.tex"), "hello");
    writeFileSync(join(h.root, "logo.png"), Buffer.from([0x89, 0x50, 0x00, 0xff]));
    mkdirSync(join(h.root, "chapters"));
    writeFileSync(join(h.root, "chapters", "one.tex"), "1");
    mkdirSync(join(h.root, ".git"));
    mkdirSync(join(h.root, ".caztor"));
    writeFileSync(join(h.root, ".caztor", "state.json"), "{}");

    const response = await h.call("GET", "/api/files");
    expect(response.status).toBe(200);
    const body = (await response.json()) as { entries: { path: string; kind: string; size: number }[] };
    const byPath = Object.fromEntries(body.entries.map((entry) => [entry.path, entry]));
    expect(byPath["main.tex"]).toEqual({ path: "main.tex", kind: "file", size: 5 });
    expect(byPath["logo.png"]).toEqual({ path: "logo.png", kind: "file", size: 4 });
    expect(byPath["chapters"]).toMatchObject({ kind: "dir" });
    expect(byPath["chapters/one.tex"]).toEqual({ path: "chapters/one.tex", kind: "file", size: 1 });
    expect(Object.keys(byPath).some((path) => path.startsWith(".git") || path.startsWith(".caztor"))).toBe(false);
  });
});

describe("GET /api/files/content", () => {
  it("is rejected without the launch token", async () => {
    const h = harness();
    writeFileSync(join(h.root, "main.tex"), "hello");
    expect((await h.call("GET", query("main.tex"), { headers: { "x-caztor-token": "" } })).status).toBe(401);
  });

  it("returns the text and its hash", async () => {
    const h = harness();
    writeFileSync(join(h.root, "main.tex"), "héllo \\LaTeX");
    const response = await h.call("GET", query("main.tex"));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ path: "main.tex", content: "héllo \\LaTeX", hash: await hashOf("héllo \\LaTeX") });
  });

  it.each([
    ["a missing file", "nope.tex", 404, "not_found"],
    ["a traversal path", "../secret.txt", 403, "outside_root"],
    ["an absolute path", "/etc/passwd", 403, "outside_root"],
    ["a reserved folder", ".git/config", 403, "hidden"],
    ["the state folder", ".caztor/state.json", 403, "hidden"],
    ["a path starting with a dash", "-Z shell-escape.tex", 400, "invalid_path"],
  ])("answers %s with %i %s and a readable message", async (_label, path, status, code) => {
    const h = harness();
    const response = await h.call("GET", query(path));
    expect(response.status).toBe(status);
    expect(await response.json()).toMatchObject({ error: code, message: expect.stringContaining(path), path });
  });

  it("hides .agents and refuses to read, write or delete inside it", async () => {
    const h = harness();
    const path = ".agents/agents/caztor.md";
    mkdirSync(join(h.root, ".agents", "agents"), { recursive: true });
    writeFileSync(join(h.root, path), "managed");

    const listed = await (await h.call("GET", "/api/files")).text();
    expect(listed).not.toContain(".agents");
    expect((await h.call("GET", query(path))).status).toBe(403);
    expect((await h.call("PUT", query(path), { body: { content: "x", baseHash: null } })).status).toBe(403);
    expect((await h.call("DELETE", query(path).replace("/content", ""))).status).toBe(403);
    expect(readFileSync(join(h.root, path), "utf8")).toBe("managed");
  });

  it("refuses a symbolic link that points outside the project", async () => {
    const h = harness();
    writeFileSync(join(h.root, "..", `${h.deps.projectName}-secret.txt`), "secret");
    symlinkSync(join(h.root, "..", `${h.deps.projectName}-secret.txt`), join(h.root, "leak.txt"));
    const response = await h.call("GET", query("leak.txt"));
    expect(response.status).toBe(403);
    expect(await response.text()).not.toContain("secret\"");
  });

  it("refuses a binary file as not text, and a text file over 2 MB as too large", async () => {
    const h = harness();
    writeFileSync(join(h.root, "logo.png"), Buffer.from([0xff, 0xfe, 0x00, 0x01]));
    writeFileSync(join(h.root, "big.tex"), "a".repeat(2 * 1024 * 1024 + 1));
    expect((await h.call("GET", query("logo.png"))).status).toBe(415);
    expect((await h.call("GET", query("big.tex"))).status).toBe(413);
  });

  it("requires the path parameter", async () => {
    const h = harness();
    const response = await h.call("GET", "/api/files/content");
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ error: "invalid_path" });
  });
});

describe("PUT /api/files/content", () => {
  const put = (h: ReturnType<typeof harness>, path: string, body: unknown) => h.call("PUT", query(path), { body });

  it("is rejected without the launch token and writes nothing", async () => {
    const h = harness();
    const response = await h.call("PUT", query("a.tex"), { body: { content: "x", baseHash: null }, headers: { "x-caztor-token": "" } });
    expect(response.status).toBe(401);
    expect(await h.call("GET", query("a.tex"))).toHaveProperty("status", 404);
  });

  it("saves when the base hash matches and returns the new hash", async () => {
    const h = harness();
    writeFileSync(join(h.root, "a.tex"), "old");
    const response = await put(h, "a.tex", { content: "new ✓", baseHash: await hashOf("old") });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ path: "a.tex", hash: await hashOf("new ✓") });
    expect(readFileSync(join(h.root, "a.tex"), "utf8")).toBe("new ✓");
  });

  it("answers 409 with the current hash when disk changed, and leaves the disk untouched", async () => {
    const h = harness();
    writeFileSync(join(h.root, "a.tex"), "changed elsewhere");
    const response = await put(h, "a.tex", { content: "mine", baseHash: await hashOf("old") });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({
      error: "conflict",
      path: "a.tex",
      currentHash: await hashOf("changed elsewhere"),
    });
    expect(readFileSync(join(h.root, "a.tex"), "utf8")).toBe("changed elsewhere");
  });

  it("creates a file when the base hash is null and refuses to overwrite one that exists", async () => {
    const h = harness();
    expect((await put(h, "new.tex", { content: "first", baseHash: null })).status).toBe(200);
    expect(readFileSync(join(h.root, "new.tex"), "utf8")).toBe("first");
    const again = await put(h, "new.tex", { content: "second", baseHash: null });
    expect(again.status).toBe(409);
    expect(await again.json()).toMatchObject({ error: "exists", message: '"new.tex" already exists. Choose another name.' });
    expect(readFileSync(join(h.root, "new.tex"), "utf8")).toBe("first");
  });

  it("answers 409 with a null hash when the file was deleted under the editor", async () => {
    const h = harness();
    const response = await put(h, "gone.tex", { content: "x", baseHash: await hashOf("old") });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "conflict", currentHash: null });
  });

  it.each([
    ["a reserved path", ".claude/agents/x.md", 403],
    ["a traversal path", "../outside.tex", 403],
  ])("rejects %s and writes nothing", async (_label, path, status) => {
    const h = harness();
    const response = await put(h, path, { content: "x", baseHash: null });
    expect(response.status).toBe(status);
  });

  it.each([
    ["no baseHash", { content: "x" }],
    ["a baseHash that is not a hash", { content: "x", baseHash: "abc" }],
    ["the unconditional marker", { content: "x", baseHash: "any" }],
    ["content that is not a string", { content: 5, baseHash: null }],
    ["a non-object body", ["x"]],
  ])("rejects %s with 400", async (_label, body) => {
    const h = harness();
    const response = await put(h, "a.tex", body);
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ error: "invalid_body" });
  });

  it("rejects text/plain with 415 and a body over 2 MB with 413", async () => {
    const h = harness();
    expect((await h.call("PUT", query("a.tex"), { body: "{}", headers: { "content-type": "text/plain" } })).status).toBe(415);
    const big = { content: "a".repeat(2 * 1024 * 1024 + 10), baseHash: null };
    expect((await put(h, "a.tex", big)).status).toBe(413);
  });
});

describe("POST /api/files", () => {
  const create = (h: ReturnType<typeof harness>, body: unknown) => h.call("POST", "/api/files", { body });

  it("is rejected without the launch token and creates nothing", async () => {
    const h = harness();
    const response = await h.call("POST", "/api/files", { body: { path: "a.tex", kind: "file" }, headers: { "x-caztor-token": "" } });
    expect(response.status).toBe(401);
    expect(await h.call("GET", query("a.tex"))).toHaveProperty("status", 404);
  });

  it("creates an empty file and a folder", async () => {
    const h = harness();
    const file = await create(h, { path: "refs.bib", kind: "file" });
    expect(file.status).toBe(201);
    expect(await file.json()).toEqual({ path: "refs.bib", kind: "file" });
    expect(readFileSync(join(h.root, "refs.bib"), "utf8")).toBe("");
    const dir = await create(h, { path: "chapters", kind: "dir" });
    expect(dir.status).toBe(201);
    const inside = await create(h, { path: "chapters/one.tex", kind: "file" });
    expect(inside.status).toBe(201);
  });

  it("rejects a name collision with 409 and a readable message, leaving the existing file unchanged", async () => {
    const h = harness();
    writeFileSync(join(h.root, "a.tex"), "keep me");
    const response = await create(h, { path: "a.tex", kind: "file" });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "exists", message: '"a.tex" already exists. Choose another name.' });
    expect(readFileSync(join(h.root, "a.tex"), "utf8")).toBe("keep me");
    mkdirSync(join(h.root, "dir"));
    expect((await create(h, { path: "dir", kind: "dir" })).status).toBe(409);
  });

  it("answers 404 when the parent folder does not exist", async () => {
    const h = harness();
    expect((await create(h, { path: "missing/x.tex", kind: "file" })).status).toBe(404);
    expect((await create(h, { path: "missing/sub", kind: "dir" })).status).toBe(404);
  });

  it.each([
    ["a reserved path", { path: ".git/hooks", kind: "dir" }, 403],
    ["a traversal path", { path: "../x.tex", kind: "file" }, 403],
    ["a leading dash", { path: "-x.tex", kind: "file" }, 400],
    ["an unknown kind", { path: "a.tex", kind: "link" }, 400],
    ["a missing kind", { path: "a.tex" }, 400],
    ["a path that is not a string", { path: 4, kind: "file" }, 400],
  ])("rejects %s", async (_label, body, status) => {
    const h = harness();
    expect((await create(h, body)).status).toBe(status);
  });
});
