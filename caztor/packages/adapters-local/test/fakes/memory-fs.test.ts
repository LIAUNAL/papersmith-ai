import { describe, expect, it } from "vitest";
import { MemoryFileSystem } from "./memory-fs.ts";

const encode = (text: string) => new TextEncoder().encode(text);
const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);

async function codeOf(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error) {
    return (error as { code?: unknown }).code;
  }
  return "no error";
}

describe("MemoryFileSystem", () => {
  it("writes and reads bytes, reporting size and a changing mtime", async () => {
    const fs = new MemoryFileSystem();
    await fs.mkdir("/p", { recursive: true });
    await fs.writeFile("/p/a.tex", encode("hello"));
    const first = await fs.stat("/p/a.tex");
    await fs.writeFile("/p/a.tex", encode("hello world"));
    const second = await fs.stat("/p/a.tex");

    expect(decode(await fs.readFile("/p/a.tex"))).toBe("hello world");
    expect([first.size, second.size]).toEqual([5, 11]);
    expect(second.mtimeMs).toBeGreaterThan(first.mtimeMs);
    expect(second.isFile()).toBe(true);
  });

  it("uses Node error codes for missing, existing and mistyped entries", async () => {
    const fs = new MemoryFileSystem({ "/p/a.tex": "x", "/p/dir/b.tex": "y" });

    expect(await codeOf(fs.readFile("/p/missing"))).toBe("ENOENT");
    expect(await codeOf(fs.writeFile("/p/a.tex", encode("z"), { exclusive: true }))).toBe("EEXIST");
    expect(await codeOf(fs.mkdir("/p/dir"))).toBe("EEXIST");
    expect(await codeOf(fs.readFile("/p/dir"))).toBe("EISDIR");
    expect(await codeOf(fs.readdir("/p/a.tex"))).toBe("ENOTDIR");
    expect(await codeOf(fs.writeFile("/nowhere/a.tex", encode("z")))).toBe("ENOENT");
  });

  it("lists directory entries with their kind", async () => {
    const fs = new MemoryFileSystem({ "/p/a.tex": "x", "/p/sub/b.tex": "y" });
    const entries = await fs.readdir("/p");
    const summary = entries.map((entry) => `${entry.name}:${entry.isDirectory() ? "dir" : "file"}`).sort();
    expect(summary).toEqual(["a.tex:file", "sub:dir"]);
  });

  it("renames a directory together with its children and removes the old name", async () => {
    const fs = new MemoryFileSystem({ "/p/old/a.tex": "x", "/p/old/deep/b.tex": "y" });
    await fs.rename("/p/old", "/p/new");

    expect(decode(await fs.readFile("/p/new/deep/b.tex"))).toBe("y");
    expect(await codeOf(fs.readFile("/p/old/a.tex"))).toBe("ENOENT");
  });

  it("removes recursively, refuses a directory without recursive, and tolerates force on missing paths", async () => {
    const fs = new MemoryFileSystem({ "/p/d/a.tex": "x" });
    expect(await codeOf(fs.rm("/p/d"))).toBe("ERR_FS_EISDIR");
    await fs.rm("/p/d", { recursive: true });
    expect(await codeOf(fs.stat("/p/d"))).toBe("ENOENT");
    expect(await codeOf(fs.rm("/p/d"))).toBe("ENOENT");
    expect(await codeOf(fs.rm("/p/d", { force: true }))).toBe("no error");
  });

  it("copies a file without sharing storage", async () => {
    const fs = new MemoryFileSystem({ "/p/a.tex": "one" });
    await fs.copyFile("/p/a.tex", "/p/b.tex");
    await fs.writeFile("/p/a.tex", encode("two"));
    expect(decode(await fs.readFile("/p/b.tex"))).toBe("one");
  });

  it("resolves symbolic links in realpath and distinguishes lstat from stat", async () => {
    const fs = new MemoryFileSystem({ "/outside/secret.txt": "s", "/p/real.tex": "r" });
    fs.symlink("/outside", "/p/escape");
    fs.symlink("/p/real.tex", "/p/alias.tex");

    expect(await fs.realpath("/p/escape/secret.txt")).toBe("/outside/secret.txt");
    expect(await fs.realpath("/p/alias.tex")).toBe("/p/real.tex");
    expect((await fs.lstat("/p/alias.tex")).isSymbolicLink()).toBe(true);
    expect((await fs.stat("/p/alias.tex")).isFile()).toBe(true);
    expect(decode(await fs.readFile("/p/escape/secret.txt"))).toBe("s");
  });
});

describe("MemoryFileSystem.mkdtemp", () => {
  it("creates distinct empty folders that begin with the prefix", async () => {
    const fs = new MemoryFileSystem({ "/tmp/keep": "x" });
    const a = await fs.mkdtemp("/tmp/box-");
    const b = await fs.mkdtemp("/tmp/box-");
    expect(a).not.toBe(b);
    expect(a.startsWith("/tmp/box-")).toBe(true);
    expect((await fs.stat(a)).isDirectory()).toBe(true);
    expect(await fs.readdir(a)).toEqual([]);
  });
});
