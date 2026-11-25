import { describe, expect, it } from "vitest";
import { parseManifest, serializeManifest } from "../../src/snapshot-manifest.ts";

const HASH = `sha256:${"a".repeat(64)}`;
const file = { hash: HASH, size: 3, mtimeMs: 10, mode: 0o644, undoable: true };
const change = {
  path: "a.tex",
  change: "modified",
  beforeHash: HASH,
  afterHash: HASH,
  beforeMode: 0o644,
  afterMode: 0o644,
  afterSignature: "3:10:420",
  undoable: true,
  mixed: false,
};
const valid = (overrides: Record<string, unknown> = {}) =>
  JSON.stringify({
    version: 1,
    kind: "turn",
    turnId: "t1",
    seq: 1,
    createdAt: 5,
    state: "applied",
    partial: false,
    files: { "a.tex": file },
    dirs: ["sections"],
    changes: null,
    ...overrides,
  });

describe("snapshot manifest parsing", () => {
  it.each([".env", ".env.local", ".mcp.json", ".papersmith/config.json", ".pi/x"])("stays readable when an older snapshot holds %s", (path) => {
    expect(parseManifest(valid({ files: { [path]: file } }), "t1")?.files.has(path as never)).toBe(true);
  });

  it("round-trips a valid manifest", () => {
    const parsed = parseManifest(valid({ changes: [change] }), "t1");
    expect(parsed).not.toBeNull();
    expect(parsed?.files.get("a.tex" as never)).toEqual({ ...file, ctimeMs: null, id: null });
    expect(parseManifest(serializeManifest(parsed!), "t1")).toEqual(parsed);
  });

  it.each([
    ["a parent traversal", { "../outside.tex": file }],
    ["a nested traversal", { "sections/../../outside.tex": file }],
    ["an absolute path", { "/etc/passwd": file }],
    ["the git folder", { ".git/config": file }],
    ["the state folder", { ".caztor/state.json": file }],
    ["an agent folder", { ".claude/agents/caztor.md": file }],
    ["a backslash path", { "a\\b.tex": file }],
    ["a path starting with a dash", { "-flag.tex": file }],
  ])("rejects the whole manifest for %s in the file list", (_label, files) => {
    expect(parseManifest(valid({ files: { "ok.tex": file, ...files } }), "t1")).toBeNull();
  });

  it.each(["../x", "/abs", ".git", "node_modules/x"])("rejects the folder entry %j", (dir) => {
    expect(parseManifest(valid({ dirs: [dir] }), "t1")).toBeNull();
  });

  it.each(["../escape.tex", "/etc/passwd", ".git/HEAD", ".caztor/state.json"])("rejects the recorded change to %j", (path) => {
    expect(parseManifest(valid({ changes: [{ ...change, path }] }), "t1")).toBeNull();
  });

  it.each([
    ["a malformed hash", { files: { "a.tex": { ...file, hash: "sha256:xyz" } } }],
    ["a copy that claims to exist without a hash", { files: { "a.tex": { ...file, hash: null, undoable: true } } }],
    ["a mode with file type bits", { files: { "a.tex": { ...file, mode: 0o100644 } } }],
    ["a negative size", { files: { "a.tex": { ...file, size: -1 } } }],
    ["an unknown state", { state: "pending" }],
    ["an unknown version", { version: 2 }],
    ["another turn id inside the file", { turnId: "t2" }],
    ["an invalid change kind", { changes: [{ ...change, change: "renamed" }] }],
  ])("rejects %s", (_label, overrides) => {
    expect(parseManifest(valid(overrides), "t1")).toBeNull();
  });

  it("rejects text that is not JSON and values that are not objects", () => {
    expect(parseManifest("{broken", "t1")).toBeNull();
    expect(parseManifest("[]", "t1")).toBeNull();
    expect(parseManifest("null", "t1")).toBeNull();
  });

  it("keeps a file called __proto__ as an ordinary entry without touching the prototype", () => {
    const parsed = parseManifest(`{"version":1,"kind":"turn","turnId":"t1","seq":1,"createdAt":5,"state":"applied","partial":false,"files":{"__proto__":${JSON.stringify(file)}},"dirs":[],"changes":null}`, "t1");
    expect([...(parsed?.files.keys() ?? [])]).toEqual(["__proto__"]);
    expect(({} as Record<string, unknown>)["hash"]).toBeUndefined();
  });
});
