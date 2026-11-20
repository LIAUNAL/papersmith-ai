import { hashBytes, type RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import type { FileSystem } from "../src/infra.ts";
import { createProjectStore, MAX_FILE_BYTES } from "../src/project-store.ts";
import { cleanupSandboxes, implementations } from "./support/fs-sandbox.ts";

const encode = (text: string) => new TextEncoder().encode(text);
const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);
const rel = (path: string) => path as RelPath;

cleanupSandboxes();

/** A file system whose operations can be intercepted by name. */
type Hooks = Partial<{ [K in keyof FileSystem]: (...args: Parameters<FileSystem[K]>) => Promise<void> | void }>;

function intercept(fs: FileSystem, before: Hooks, afterWrite: () => Promise<void> | void = () => {}): FileSystem {
  const hook = async <K extends keyof FileSystem>(name: K, args: Parameters<FileSystem[K]>) => {
    await (before[name] as ((...a: Parameters<FileSystem[K]>) => Promise<void> | void) | undefined)?.(...args);
  };
  return {
    readFile: async (p) => (await hook("readFile", [p]), fs.readFile(p)),
    readRange: (p, s, l) => fs.readRange(p, s, l),
    writeFile: async (p, d, o) => {
      await hook("writeFile", [p, d, o]);
      await fs.writeFile(p, d, o);
      await afterWrite();
    },
    mkdir: async (p, o) => (await hook("mkdir", [p, o]), fs.mkdir(p, o)),
    readdir: (p) => fs.readdir(p),
    stat: (p) => fs.stat(p),
    lstat: (p) => fs.lstat(p),
    realpath: (p) => fs.realpath(p),
    rename: async (a, b) => (await hook("rename", [a, b]), fs.rename(a, b)),
    rm: (p, o) => fs.rm(p, o),
    copyFile: (a, b) => fs.copyFile(a, b),
    chmod: (p, m) => fs.chmod(p, m),
    mkdtemp: (p) => fs.mkdtemp(p),
  };
}

describe.each(implementations)("project store hardening: %s", (_name, create) => {
  async function setup(wrap: (fs: FileSystem) => FileSystem = (fs) => fs) {
    const box = create();
    const project = `${box.root}/project`;
    const outside = `${box.root}/outside`;
    await box.fs.mkdir(project, { recursive: true });
    await box.fs.mkdir(outside, { recursive: true });
    await box.fs.writeFile(`${outside}/secret.txt`, encode("secret"));
    const store = createProjectStore({ fs: wrap(box.fs), root: project });
    return { ...box, project, outside, store };
  }

  describe("concurrent writes", () => {
    it("lets exactly one of two saves based on the same hash succeed", async () => {
      const { store, project, fs } = await setup();
      const base = await store.write(rel("a.tex"), encode("base"), null);
      const hash = base.ok ? base.value.hash : null;

      const results = await Promise.all([store.write(rel("a.tex"), encode("first"), hash), store.write(rel("a.tex"), encode("second"), hash)]);
      expect(results.filter((result) => result.ok)).toHaveLength(1);
      const loser = results.find((result) => !result.ok);
      expect(loser).toMatchObject({ ok: false, error: { code: "conflict", path: "a.tex" } });
      const winner = results.findIndex((result) => result.ok);
      expect(decode(await fs.readFile(`${project}/a.tex`))).toBe(winner === 0 ? "first" : "second");
    });

    it("lets exactly one of several create-only writes succeed", async () => {
      const { store, project, fs } = await setup();
      const results = await Promise.all(["one", "two", "three"].map((text) => store.write(rel("new.tex"), encode(text), null)));
      expect(results.filter((result) => result.ok)).toHaveLength(1);
      for (const result of results.filter((entry) => !entry.ok)) {
        expect(result).toMatchObject({ ok: false, error: { code: "exists" } });
      }
      const winner = ["one", "two", "three"][results.findIndex((result) => result.ok)];
      expect(decode(await fs.readFile(`${project}/new.tex`))).toBe(winner);
      expect((await fs.readdir(project)).map((entry) => entry.name)).toEqual(["new.tex"]);
    });

    it("does not serialize writes to different files", async () => {
      const { store } = await setup();
      const results = await Promise.all([store.write(rel("a.tex"), encode("a"), null), store.write(rel("b.tex"), encode("b"), null)]);
      expect(results.map((result) => result.ok)).toEqual([true, true]);
    });

    it("keeps serializing after a write has failed", async () => {
      const { store } = await setup();
      expect(await store.write(rel("missing/a.tex"), encode("x"), null)).toMatchObject({ ok: false });
      const results = await Promise.all([store.write(rel("a.tex"), encode("1"), null), store.write(rel("a.tex"), encode("2"), null)]);
      expect(results.filter((result) => result.ok)).toHaveLength(1);
    });

    it("lets exactly one of two renames onto the same destination succeed", async () => {
      const { store, project, fs } = await setup();
      await fs.writeFile(`${project}/a.tex`, encode("a"));
      await fs.writeFile(`${project}/b.tex`, encode("b"));

      const results = await Promise.all([store.rename(rel("a.tex"), rel("c.tex")), store.rename(rel("b.tex"), rel("c.tex"))]);
      expect(results.filter((result) => result.ok)).toHaveLength(1);
      expect(results.find((result) => !result.ok)).toMatchObject({ ok: false, error: { code: "exists", path: "c.tex" } });
      const names = (await fs.readdir(project)).map((entry) => entry.name).sort();
      expect(names).toHaveLength(2);
      expect(names).toContain("c.tex");
    });

    it("lets a create-only write and a rename onto the same name settle without losing either file", async () => {
      const { store, project, fs } = await setup();
      await fs.writeFile(`${project}/a.tex`, encode("moved"));
      const [created, renamed] = await Promise.all([store.write(rel("c.tex"), encode("created"), null), store.rename(rel("a.tex"), rel("c.tex"))]);
      expect([created.ok, renamed.ok].filter(Boolean)).toHaveLength(1);
      const remaining = (await fs.readdir(project)).map((entry) => entry.name).sort();
      expect(remaining).toHaveLength(created.ok ? 2 : 1);
    });
  });

  describe("parent directory swap", () => {
    /** Replaces `<project>/sub` with a link to the outside folder the first time `trigger` runs. */
    async function swappable(trigger: "before-write" | "after-write") {
      let swap: () => Promise<void> = async () => {};
      const once = async () => {
        const run = swap;
        swap = async () => {};
        await run();
      };
      const box = await setup((base) =>
        trigger === "before-write" ? intercept(base, { writeFile: once }) : intercept(base, {}, once),
      );
      await box.fs.mkdir(`${box.project}/sub`);
      await box.fs.writeFile(`${box.project}/sub/a.tex`, encode("old"));
      swap = async () => {
        await box.fs.rm(`${box.project}/sub`, { recursive: true });
        box.symlink(box.outside, `${box.project}/sub`);
      };
      return box;
    }

    it("aborts when the parent becomes a link out of the project before the temporary file is written, leaving nothing outside", async () => {
      const { store, outside, fs } = await swappable("before-write");
      expect(await store.write(rel("sub/a.tex"), encode("pwned"), "any")).toMatchObject({ ok: false, error: { code: "outside_root" } });
      expect((await fs.readdir(outside)).map((entry) => entry.name)).toEqual(["secret.txt"]);
      expect(decode(await fs.readFile(`${outside}/secret.txt`))).toBe("secret");
    });

    it("aborts when the parent is swapped after the temporary file is written, and removes nothing outside the project", async () => {
      const { store, outside, project, fs } = await swappable("after-write");
      expect(await store.write(rel("sub/a.tex"), encode("pwned"), "any")).toMatchObject({ ok: false, error: { code: "outside_root" } });
      expect((await fs.readdir(outside)).map((entry) => entry.name)).toEqual(["secret.txt"]);
      expect((await fs.lstat(`${project}/sub`)).isSymbolicLink()).toBe(true);
    });

    it("still writes when the parent is not swapped", async () => {
      const { store, project, fs } = await setup((base) => intercept(base, {}));
      await fs.mkdir(`${project}/sub`);
      expect((await store.write(rel("sub/a.tex"), encode("fine"), null)).ok).toBe(true);
      expect(decode(await fs.readFile(`${project}/sub/a.tex`))).toBe("fine");
    });
  });

  describe("reserved temporary prefix", () => {
    it.each([".caztor-tmp-1", "docs/.caztor-tmp-abc", ".caztor-tmp-dir/file.tex", ".caztor-tmp-"])("rejects the path %s everywhere", async (path) => {
      const { store, project, fs } = await setup();
      await fs.mkdir(`${project}/docs`);
      expect(await store.write(rel(path), encode("x"), null)).toMatchObject({ ok: false, error: { code: "hidden", path } });
      expect(await store.mkdir(rel(path))).toMatchObject({ ok: false, error: { code: "hidden" } });
      expect(await store.read(rel(path))).toMatchObject({ ok: false, error: { code: "hidden" } });
      await fs.writeFile(`${project}/a.tex`, encode("a"));
      expect(await store.rename(rel("a.tex"), rel(path))).toMatchObject({ ok: false, error: { code: "hidden" } });
      expect(await store.remove(rel(path))).toMatchObject({ ok: false, error: { code: "hidden" } });
      expect((await fs.readdir(project)).map((entry) => entry.name).sort()).toEqual(["a.tex", "docs"]);
    });

    it("still accepts names that only contain the prefix", async () => {
      const { store } = await setup();
      expect((await store.write(rel("my.caztor-tmp-1"), encode("x"), null)).ok).toBe(true);
      expect((await store.write(rel("x.caztor-tmp-"), encode("x"), null)).ok).toBe(true);
    });
  });

  describe("bounded reads", () => {
    it("refuses to read a file above 20 MB without loading it", async () => {
      let loaded = 0;
      const { store, project, fs } = await setup((base) => intercept(base, { readFile: () => void loaded++ }));
      await fs.writeFile(`${project}/big.bin`, new Uint8Array(MAX_FILE_BYTES + 1));
      await fs.writeFile(`${project}/ok.bin`, new Uint8Array(MAX_FILE_BYTES));

      expect(await store.read(rel("big.bin"))).toMatchObject({ ok: false, error: { code: "too_large" } });
      expect(loaded).toBe(0);
      const ok = await store.read(rel("ok.bin"));
      expect(ok.ok && ok.value.bytes.length).toBe(MAX_FILE_BYTES);
      expect(loaded).toBe(1);
    });

    it("refuses a hash-checked save over a file above 20 MB without loading it", async () => {
      let loaded = 0;
      const { store, project, fs } = await setup((base) => intercept(base, { readFile: () => void loaded++ }));
      await fs.writeFile(`${project}/big.bin`, new Uint8Array(MAX_FILE_BYTES + 1));

      const stale = await hashBytes(encode("old"));
      expect(await store.write(rel("big.bin"), encode("x"), stale)).toMatchObject({ ok: false, error: { code: "too_large" } });
      expect(loaded).toBe(0);
      expect((await fs.stat(`${project}/big.bin`)).size).toBe(MAX_FILE_BYTES + 1);
    });

    it("answers a create-only write over a large file with exists, and an unconditional save replaces it, neither loading it", async () => {
      let loaded = 0;
      const { store, project, fs } = await setup((base) => intercept(base, { readFile: () => void loaded++ }));
      await fs.writeFile(`${project}/big.bin`, new Uint8Array(MAX_FILE_BYTES + 1));

      expect(await store.write(rel("big.bin"), encode("x"), null)).toMatchObject({ ok: false, error: { code: "exists" } });
      expect((await store.write(rel("big.bin"), encode("small"), "any")).ok).toBe(true);
      expect(loaded).toBe(0);
      expect(decode(await fs.readFile(`${project}/big.bin`))).toBe("small");
    });
  });
});
