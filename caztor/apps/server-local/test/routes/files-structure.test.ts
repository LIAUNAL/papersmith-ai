import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { cleanupProjects, harness } from "./support.ts";

cleanupProjects();

const MB = 1024 * 1024;
const del = (h: ReturnType<typeof harness>, path: string, extra = "") =>
  h.call("DELETE", `/api/files?path=${encodeURIComponent(path)}${extra}`);
const rename = (h: ReturnType<typeof harness>, from: unknown, to: unknown) =>
  h.call("POST", "/api/files/rename", { body: { from, to } });
const upload = (h: ReturnType<typeof harness>, path: string, bytes: Uint8Array) =>
  h.upload(`/api/files/upload?path=${encodeURIComponent(path)}`, bytes);

describe("POST /api/files/rename", () => {
  it("is rejected without the launch token and renames nothing", async () => {
    const h = harness();
    writeFileSync(join(h.root, "a.tex"), "x");
    const response = await h.call("POST", "/api/files/rename", { body: { from: "a.tex", to: "b.tex" }, headers: { "x-caztor-token": "" } });
    expect(response.status).toBe(401);
    expect(existsSync(join(h.root, "a.tex"))).toBe(true);
  });

  it("renames a file and a folder", async () => {
    const h = harness();
    writeFileSync(join(h.root, "refs.bib"), "bib");
    mkdirSync(join(h.root, "old"));
    writeFileSync(join(h.root, "old", "x.tex"), "x");
    const file = await rename(h, "refs.bib", "bib.bib");
    expect(file.status).toBe(200);
    expect(await file.json()).toEqual({ from: "refs.bib", to: "bib.bib" });
    expect((await rename(h, "old", "new")).status).toBe(200);
    expect(existsSync(join(h.root, "refs.bib"))).toBe(false);
    expect(readFileSync(join(h.root, "bib.bib"), "utf8")).toBe("bib");
    expect(readFileSync(join(h.root, "new", "x.tex"), "utf8")).toBe("x");
  });

  it("rejects a name collision with 409 and leaves both files unchanged", async () => {
    const h = harness();
    writeFileSync(join(h.root, "a.tex"), "A");
    writeFileSync(join(h.root, "b.tex"), "B");
    const response = await rename(h, "a.tex", "b.tex");
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "exists", message: '"b.tex" already exists. Choose another name.' });
    expect(readFileSync(join(h.root, "a.tex"), "utf8")).toBe("A");
    expect(readFileSync(join(h.root, "b.tex"), "utf8")).toBe("B");
  });

  it.each([
    ["a missing source", "missing.tex", "x.tex", 404],
    ["a reserved source", ".git/config", "x", 403],
    ["a reserved target", "a.tex", ".caztor/state.json", 403],
    ["a traversal target", "a.tex", "../a.tex", 403],
    ["a target starting with a dash", "a.tex", "-b.tex", 400],
  ])("rejects %s", async (_label, from, to, status) => {
    const h = harness();
    writeFileSync(join(h.root, "a.tex"), "A");
    expect((await rename(h, from, to)).status).toBe(status);
    expect(readFileSync(join(h.root, "a.tex"), "utf8")).toBe("A");
  });

  it.each([
    ["from missing", { to: "b.tex" }],
    ["to not a string", { from: "a.tex", to: 3 }],
    ["a non-object body", "[]"],
  ])("rejects a body with %s with 400", async (_label, body) => {
    const h = harness();
    expect((await h.call("POST", "/api/files/rename", { body })).status).toBe(400);
  });
});

describe("DELETE /api/files", () => {
  it("is rejected without the launch token and deletes nothing", async () => {
    const h = harness();
    writeFileSync(join(h.root, "a.tex"), "x");
    const response = await h.call("DELETE", "/api/files?path=a.tex", { headers: { "x-caztor-token": "" } });
    expect(response.status).toBe(401);
    expect(existsSync(join(h.root, "a.tex"))).toBe(true);
  });

  it("requires the JSON content type like every write", async () => {
    const h = harness();
    writeFileSync(join(h.root, "a.tex"), "x");
    const response = await h.call("DELETE", "/api/files?path=a.tex", { headers: { "content-type": "text/plain" } });
    expect(response.status).toBe(415);
    expect(existsSync(join(h.root, "a.tex"))).toBe(true);
  });

  it("deletes a file and an empty folder", async () => {
    const h = harness();
    writeFileSync(join(h.root, "a.tex"), "x");
    mkdirSync(join(h.root, "empty"));
    const file = await del(h, "a.tex");
    expect(file.status).toBe(200);
    expect(await file.json()).toEqual({ path: "a.tex" });
    expect((await del(h, "empty")).status).toBe(200);
    expect(existsSync(join(h.root, "a.tex"))).toBe(false);
    expect(existsSync(join(h.root, "empty"))).toBe(false);
  });

  it("does not delete a folder with content unless recursive is requested", async () => {
    const h = harness();
    mkdirSync(join(h.root, "chapters"));
    writeFileSync(join(h.root, "chapters", "one.tex"), "1");
    const refused = await del(h, "chapters");
    expect(refused.status).toBe(409);
    expect(await refused.json()).toMatchObject({
      error: "not_empty",
      message: expect.stringContaining("chapters"),
      path: "chapters",
    });
    expect(existsSync(join(h.root, "chapters", "one.tex"))).toBe(true);

    expect((await del(h, "chapters", "&recursive=false")).status).toBe(409);
    expect(existsSync(join(h.root, "chapters", "one.tex"))).toBe(true);

    expect((await del(h, "chapters", "&recursive=true")).status).toBe(200);
    expect(existsSync(join(h.root, "chapters"))).toBe(false);
  });

  it.each([
    ["a missing file", "missing.tex", 404],
    ["a reserved folder", ".git", 403],
    ["a traversal path", "../x", 403],
    ["a path starting with a dash", "-x", 400],
  ])("rejects %s", async (_label, path, status) => {
    const h = harness();
    expect((await del(h, path, "&recursive=true")).status).toBe(status);
  });

  it("requires the path parameter", async () => {
    const h = harness();
    expect((await h.call("DELETE", "/api/files")).status).toBe(400);
  });
});

describe("POST /api/files/upload", () => {
  it("is rejected without the launch token and writes nothing", async () => {
    const h = harness();
    const response = await h.call("POST", "/api/files/upload?path=a.bin", { body: "x", headers: { "x-caztor-token": "", "content-type": "application/octet-stream" } });
    expect(response.status).toBe(401);
    expect(existsSync(join(h.root, "a.bin"))).toBe(false);
  });

  it("stores the raw bytes and returns the path and hash", async () => {
    const h = harness();
    mkdirSync(join(h.root, "figures"));
    const bytes = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x00, 0xff, 0xfe]);
    const response = await upload(h, "figures/logo.png", bytes);
    expect(response.status).toBe(201);
    expect(await response.json()).toMatchObject({ path: "figures/logo.png", hash: expect.stringMatching(/^sha256:[0-9a-f]{64}$/) });
    expect(new Uint8Array(readFileSync(join(h.root, "figures", "logo.png")))).toEqual(bytes);
  });

  it("accepts exactly 20 MB and rejects 20 MB plus one byte with 413, writing nothing", async () => {
    const h = harness();
    expect((await upload(h, "ok.bin", new Uint8Array(20 * MB))).status).toBe(201);
    expect(readFileSync(join(h.root, "ok.bin")).byteLength).toBe(20 * MB);
    const response = await upload(h, "big.bin", new Uint8Array(20 * MB + 1));
    expect(response.status).toBe(413);
    expect(existsSync(join(h.root, "big.bin"))).toBe(false);
  });

  it("rejects a name collision with 409 and leaves the existing file unchanged", async () => {
    const h = harness();
    writeFileSync(join(h.root, "a.bin"), "original");
    const response = await upload(h, "a.bin", new Uint8Array([1, 2, 3]));
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "exists", message: '"a.bin" already exists. Choose another name.' });
    expect(readFileSync(join(h.root, "a.bin"), "utf8")).toBe("original");
  });

  it.each([
    ["a reserved path", ".claude/agents/x.md", 403],
    ["the state folder", ".caztor/state.json", 403],
    ["a traversal path", "../x.bin", 403],
    ["a missing folder", "missing/x.bin", 404],
  ])("rejects an upload to %s", async (_label, path, status) => {
    const h = harness();
    expect((await upload(h, path, new Uint8Array([1]))).status).toBe(status);
  });

  it("requires the path parameter and the octet-stream content type", async () => {
    const h = harness();
    expect((await h.upload("/api/files/upload", new Uint8Array([1]))).status).toBe(400);
    const json = await h.call("POST", "/api/files/upload?path=a.bin", { body: "{}" });
    expect(json.status).toBe(415);
  });
});
