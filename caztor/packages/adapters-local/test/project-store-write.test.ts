import { hashBytes, type RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import type { FileSystem } from "../src/infra.ts";
import { createProjectStore, MAX_FILE_BYTES } from "../src/project-store.ts";
import { cleanupSandboxes, implementations } from "./support/fs-sandbox.ts";

const encode = (text: string) => new TextEncoder().encode(text);
const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);
const rel = (path: string) => path as RelPath;

cleanupSandboxes();

describe.each(implementations)("project store writes and containment: %s", (_name, create) => {
  async function setup(wrap: (fs: FileSystem) => FileSystem = (fs) => fs) {
    const box = create();
    const project = `${box.root}/project`;
    const outside = `${box.root}/outside`;
    await box.fs.mkdir(project, { recursive: true });
    await box.fs.mkdir(outside, { recursive: true });
    await box.fs.writeFile(`${outside}/secret.txt`, encode("secret"));
    const store = createProjectStore({ fs: wrap(box.fs), root: project });
    const text = async (path: string) => decode(await box.fs.readFile(path));
    return { ...box, project, outside, store, text };
  }

  describe("write", () => {
    it("creates a file only when none exists and returns the hash of what was written", async () => {
      const { store, project, text } = await setup();
      const created = await store.write(rel("a.tex"), encode("one"), null);
      expect(created).toEqual({ ok: true, value: { hash: await hashBytes(encode("one")) } });
      expect(await text(`${project}/a.tex`)).toBe("one");

      expect(await store.write(rel("a.tex"), encode("two"), null)).toEqual({ ok: false, error: { code: "exists", path: "a.tex" } });
      expect(await text(`${project}/a.tex`)).toBe("one");
    });

    it("saves over the hash it was based on and returns the new hash", async () => {
      const { store, project, text } = await setup();
      const first = await store.write(rel("a.tex"), encode("one"), null);
      const base = first.ok ? first.value.hash : null;
      const second = await store.write(rel("a.tex"), encode("two"), base);
      expect(second).toEqual({ ok: true, value: { hash: await hashBytes(encode("two")) } });
      expect(await text(`${project}/a.tex`)).toBe("two");
    });

    it("rejects a stale hash with a conflict carrying the current hash and leaves the file untouched", async () => {
      const { store, project, fs, text } = await setup();
      const first = await store.write(rel("a.tex"), encode("one"), null);
      const stale = first.ok ? first.value.hash : null;
      await fs.writeFile(`${project}/a.tex`, encode("changed elsewhere"));

      const result = await store.write(rel("a.tex"), encode("mine"), stale);
      expect(result).toEqual({
        ok: false,
        error: { code: "conflict", path: "a.tex", currentHash: await hashBytes(encode("changed elsewhere")) },
      });
      expect(await text(`${project}/a.tex`)).toBe("changed elsewhere");
    });

    it("reports a conflict with no current hash when the file based on a hash has vanished", async () => {
      const { store, project, fs } = await setup();
      const result = await store.write(rel("gone.tex"), encode("x"), await hashBytes(encode("old")));
      expect(result).toEqual({ ok: false, error: { code: "conflict", path: "gone.tex", currentHash: null } });
      expect((await fs.readdir(project)).length).toBe(0);
    });

    it("overwrites unconditionally for expect any, whether the file exists or not", async () => {
      const { store, project, text } = await setup();
      expect((await store.write(rel("a.tex"), encode("one"), "any")).ok).toBe(true);
      expect((await store.write(rel("a.tex"), encode("two"), "any")).ok).toBe(true);
      expect(await text(`${project}/a.tex`)).toBe("two");
    });

    it("writes binary data byte for byte", async () => {
      const { store, project, fs } = await setup();
      const bytes = new Uint8Array([0, 255, 128, 1]);
      await store.write(rel("figure.png"), bytes, null);
      expect(await fs.readFile(`${project}/figure.png`)).toEqual(bytes);
    });

    it("rejects uploads and saves into reserved folders without creating anything", async () => {
      const { store, project, fs } = await setup();
      for (const path of [".git/x", ".caztor/state.json", ".claude/a", ".opencode/a", ".agents/a", "node_modules/pkg.js"]) {
        expect(await store.write(rel(path), encode("x"), null)).toEqual({ ok: false, error: { code: "hidden", path } });
      }
      expect(await fs.readdir(project)).toEqual([]);
    });

    it("refuses to write through a link that escapes the project, for the file and for a parent", async () => {
      const { store, project, outside, symlink, text } = await setup();
      symlink(`${outside}/secret.txt`, `${project}/leak.txt`);
      symlink(outside, `${project}/escape`);

      expect(await store.write(rel("leak.txt"), encode("pwned"), "any")).toMatchObject({ ok: false, error: { code: "outside_root" } });
      expect(await store.write(rel("escape/new.txt"), encode("pwned"), null)).toMatchObject({ ok: false, error: { code: "outside_root" } });
      expect(await store.write(rel("../outside/secret.txt"), encode("pwned"), "any")).toMatchObject({ ok: false, error: { code: "outside_root" } });
      expect(await text(`${outside}/secret.txt`)).toBe("secret");
    });

    it("refuses a dangling link, which could create a file outside the project", async () => {
      const { store, project, outside, symlink, fs } = await setup();
      symlink(`${outside}/new.txt`, `${project}/dangling.txt`);
      expect(await store.write(rel("dangling.txt"), encode("x"), "any")).toMatchObject({ ok: false, error: { code: "outside_root" } });
      await expect(fs.stat(`${outside}/new.txt`)).rejects.toMatchObject({ code: "ENOENT" });
    });

    it("writes through a link that stays inside the project and keeps the link", async () => {
      const { store, project, fs, symlink, text } = await setup();
      await fs.writeFile(`${project}/real.tex`, encode("real"));
      symlink(`${project}/real.tex`, `${project}/alias.tex`);
      expect((await store.write(rel("alias.tex"), encode("via link"), "any")).ok).toBe(true);
      expect(await text(`${project}/real.tex`)).toBe("via link");
      expect((await fs.lstat(`${project}/alias.tex`)).isSymbolicLink()).toBe(true);
    });

    it("refuses directories, special files, a file used as a folder and a missing parent", async () => {
      const { store, project, fs, special } = await setup();
      await fs.mkdir(`${project}/folder`);
      await special(`${project}/pipe`);
      await fs.writeFile(`${project}/file.tex`, encode("f"));

      expect(await store.write(rel("folder"), encode("x"), "any")).toMatchObject({ ok: false, error: { code: "invalid_path" } });
      expect(await store.write(rel("pipe"), encode("x"), "any")).toMatchObject({ ok: false, error: { code: "invalid_path" } });
      expect(await store.write(rel("file.tex/inner.tex"), encode("x"), null)).toMatchObject({ ok: false, error: { code: "invalid_path" } });
      expect(await store.write(rel("missing/inner.tex"), encode("x"), null)).toMatchObject({ ok: false, error: { code: "not_found" } });
    });

    it("rejects a payload over 20 MB before touching the disk", async () => {
      const { store, project, fs } = await setup();
      const result = await store.write(rel("big.bin"), new Uint8Array(MAX_FILE_BYTES + 1), null);
      expect(result).toMatchObject({ ok: false, error: { code: "too_large" } });
      expect(await fs.readdir(project)).toEqual([]);
    });

    it("writes atomically: a failed replace keeps the old content and leaves no temporary file", async () => {
      const failing = (fs: FileSystem): FileSystem => ({
        readFile: (p) => fs.readFile(p),
        readRange: (p, s, l) => fs.readRange(p, s, l),
        writeFile: (p, d, o) => fs.writeFile(p, d, o),
        mkdir: (p, o) => fs.mkdir(p, o),
        readdir: (p) => fs.readdir(p),
        stat: (p) => fs.stat(p),
        lstat: (p) => fs.lstat(p),
        realpath: (p) => fs.realpath(p),
        rename: () => Promise.reject(Object.assign(new Error("disk full"), { code: "ENOSPC" })),
        rm: (p, o) => fs.rm(p, o),
        copyFile: (a, b) => fs.copyFile(a, b),
        chmod: (p, m) => fs.chmod(p, m),
        mkdtemp: (p) => fs.mkdtemp(p),
      });
      const { store, project, fs, text } = await setup(failing);
      await fs.writeFile(`${project}/a.tex`, encode("old"));

      expect(await store.write(rel("a.tex"), encode("new"), "any")).toMatchObject({ ok: false, error: { code: "io" } });
      expect(await text(`${project}/a.tex`)).toBe("old");
      expect((await fs.readdir(project)).map((entry) => entry.name)).toEqual(["a.tex"]);
    });

    it("keeps the permission bits of the file it replaces", async () => {
      const { store, project, fs } = await setup();
      await fs.writeFile(`${project}/run.sh`, encode("#!/bin/sh\n"));
      await fs.chmod(`${project}/run.sh`, 0o755);
      await fs.writeFile(`${project}/private.tex`, encode("secret"));
      await fs.chmod(`${project}/private.tex`, 0o600);

      expect((await store.write(rel("run.sh"), encode("#!/bin/sh\necho"), "any")).ok).toBe(true);
      expect((await store.write(rel("private.tex"), encode("changed"), "any")).ok).toBe(true);
      expect((await fs.stat(`${project}/run.sh`)).mode).toBe(0o755);
      expect((await fs.stat(`${project}/private.tex`)).mode).toBe(0o600);
    });

    it("creates the temporary file readable by the owner only, so the content is never exposed more than the original", async () => {
      const created: Array<{ path: string; mode: number | undefined; statMode: number }> = [];
      const { store, project, fs } = await setup((base) => {
        const writeFile: FileSystem["writeFile"] = async (path, data, opts) => {
          await base.writeFile(path, data, opts);
          created.push({ path, mode: opts?.mode, statMode: (await base.stat(path)).mode });
        };
        return new Proxy(base, {
          get: (target, key) => (key === "writeFile" ? writeFile : (target[key as keyof FileSystem] as (...a: never[]) => unknown).bind(target)),
        });
      });
      await fs.writeFile(`${project}/private.tex`, encode("secret"));
      await fs.chmod(`${project}/private.tex`, 0o600);
      await fs.writeFile(`${project}/shared.tex`, encode("shared"));
      await fs.chmod(`${project}/shared.tex`, 0o644);
      created.length = 0;

      expect((await store.write(rel("private.tex"), encode("changed"), "any")).ok).toBe(true);
      expect((await store.write(rel("shared.tex"), encode("changed"), "any")).ok).toBe(true);

      expect(created).toHaveLength(2);
      for (const entry of created) {
        expect(entry.mode).toBe(0o600);
        expect(entry.statMode).toBe(0o600);
      }
      expect((await fs.stat(`${project}/private.tex`)).mode).toBe(0o600);
      expect((await fs.stat(`${project}/shared.tex`)).mode).toBe(0o644);
    });

    it("leaves no temporary file behind after a successful write and never lists one", async () => {
      const { store, project, fs } = await setup();
      await store.write(rel("a.tex"), encode("x"), null);
      expect((await fs.readdir(project)).map((entry) => entry.name)).toEqual(["a.tex"]);
      await fs.writeFile(`${project}/.caztor-tmp-123`, encode("partial"));
      expect((await store.list()).map((entry) => entry.path)).toEqual(["a.tex"]);
    });
  });

  describe("mkdir", () => {
    it("creates a folder and refuses an existing one, a missing parent and reserved or escaping locations", async () => {
      const { store, project, outside, fs, symlink } = await setup();
      expect(await store.mkdir(rel("chapters"))).toEqual({ ok: true, value: undefined });
      expect((await fs.stat(`${project}/chapters`)).isDirectory()).toBe(true);
      expect(await store.mkdir(rel("chapters"))).toMatchObject({ ok: false, error: { code: "exists" } });
      expect(await store.mkdir(rel("a/b"))).toMatchObject({ ok: false, error: { code: "not_found" } });
      expect(await store.mkdir(rel(".git"))).toMatchObject({ ok: false, error: { code: "hidden" } });

      symlink(outside, `${project}/escape`);
      expect(await store.mkdir(rel("escape/made"))).toMatchObject({ ok: false, error: { code: "outside_root" } });
      expect(await store.mkdir(rel("../made"))).toMatchObject({ ok: false, error: { code: "outside_root" } });
      expect((await fs.readdir(outside)).map((entry) => entry.name)).toEqual(["secret.txt"]);
    });
  });

  describe("rename", () => {
    it("renames a file and a folder together with its children", async () => {
      const { store, project, fs, text } = await setup();
      await fs.writeFile(`${project}/refs.bib`, encode("bib"));
      await fs.mkdir(`${project}/old`);
      await fs.writeFile(`${project}/old/a.tex`, encode("a"));

      expect(await store.rename(rel("refs.bib"), rel("bib.bib"))).toEqual({ ok: true, value: undefined });
      expect(await store.rename(rel("old"), rel("new"))).toEqual({ ok: true, value: undefined });
      expect(await text(`${project}/bib.bib`)).toBe("bib");
      expect(await text(`${project}/new/a.tex`)).toBe("a");
      expect((await store.list()).map((entry) => entry.path)).toEqual(["bib.bib", "new", "new/a.tex"]);
    });

    it("rejects a name collision for a file or a folder and leaves both untouched", async () => {
      const { store, project, fs, text } = await setup();
      await fs.writeFile(`${project}/a.tex`, encode("a"));
      await fs.writeFile(`${project}/b.tex`, encode("b"));
      await fs.mkdir(`${project}/dir`);

      expect(await store.rename(rel("b.tex"), rel("a.tex"))).toMatchObject({ ok: false, error: { code: "exists" } });
      expect(await store.rename(rel("b.tex"), rel("dir"))).toMatchObject({ ok: false, error: { code: "exists" } });
      expect(await text(`${project}/a.tex`)).toBe("a");
      expect(await text(`${project}/b.tex`)).toBe("b");
    });

    it("reports a missing source or destination folder", async () => {
      const { store, project, fs } = await setup();
      await fs.writeFile(`${project}/a.tex`, encode("a"));
      expect(await store.rename(rel("nope.tex"), rel("x.tex"))).toMatchObject({ ok: false, error: { code: "not_found" } });
      expect(await store.rename(rel("a.tex"), rel("missing/x.tex"))).toMatchObject({ ok: false, error: { code: "not_found" } });
    });

    it("refuses reserved sources and destinations, escaping destinations and moving a folder into itself", async () => {
      const { store, project, outside, fs, symlink } = await setup();
      await fs.writeFile(`${project}/a.tex`, encode("a"));
      await fs.mkdir(`${project}/dir`);
      await fs.mkdir(`${project}/.git`);
      symlink(outside, `${project}/escape`);

      expect(await store.rename(rel("a.tex"), rel(".git/a.tex"))).toMatchObject({ ok: false, error: { code: "hidden" } });
      expect(await store.rename(rel(".git"), rel("git"))).toMatchObject({ ok: false, error: { code: "hidden" } });
      expect(await store.rename(rel("a.tex"), rel("escape/a.tex"))).toMatchObject({ ok: false, error: { code: "outside_root" } });
      expect(await store.rename(rel("a.tex"), rel("../a.tex"))).toMatchObject({ ok: false, error: { code: "outside_root" } });
      expect(await store.rename(rel("dir"), rel("dir/inner"))).toMatchObject({ ok: false, error: { code: "invalid_path" } });
      expect((await fs.readdir(outside)).map((entry) => entry.name)).toEqual(["secret.txt"]);
    });

    it("moves a link that points outside as a link, without touching its target", async () => {
      const { store, project, outside, symlink, fs } = await setup();
      symlink(`${outside}/secret.txt`, `${project}/leak.txt`);
      expect((await store.rename(rel("leak.txt"), rel("moved.txt"))).ok).toBe(true);
      expect((await fs.lstat(`${project}/moved.txt`)).isSymbolicLink()).toBe(true);
      expect(decode(await fs.readFile(`${outside}/secret.txt`))).toBe("secret");
    });
  });

  describe("remove", () => {
    it("removes a file, an empty folder and, when asked, a folder with everything in it", async () => {
      const { store, project, fs } = await setup();
      await fs.writeFile(`${project}/a.tex`, encode("a"));
      await fs.mkdir(`${project}/empty`);
      await fs.mkdir(`${project}/full/deep`, { recursive: true });
      await fs.writeFile(`${project}/full/deep/b.tex`, encode("b"));

      expect(await store.remove(rel("a.tex"))).toEqual({ ok: true, value: undefined });
      expect(await store.remove(rel("empty"))).toEqual({ ok: true, value: undefined });
      expect(await store.remove(rel("full"), { recursive: true })).toEqual({ ok: true, value: undefined });
      expect(await fs.readdir(project)).toEqual([]);
    });

    it("keeps a folder with content when recursive is not requested", async () => {
      const { store, project, fs } = await setup();
      await fs.mkdir(`${project}/full`);
      await fs.writeFile(`${project}/full/b.tex`, encode("b"));
      expect(await store.remove(rel("full"))).toMatchObject({ ok: false, error: { code: "invalid_path" } });
      expect(await store.remove(rel("full"), { recursive: false })).toMatchObject({ ok: false, error: { code: "invalid_path" } });
      expect((await fs.readdir(`${project}/full`)).length).toBe(1);
    });

    it("reports a missing path and refuses reserved or escaping locations", async () => {
      const { store, project, outside, fs, symlink } = await setup();
      await fs.mkdir(`${project}/.git`);
      symlink(outside, `${project}/escape`);

      expect(await store.remove(rel("missing.tex"))).toMatchObject({ ok: false, error: { code: "not_found" } });
      expect(await store.remove(rel(".git"), { recursive: true })).toMatchObject({ ok: false, error: { code: "hidden" } });
      expect(await store.remove(rel("escape/secret.txt"))).toMatchObject({ ok: false, error: { code: "outside_root" } });
      expect(await store.remove(rel("../outside/secret.txt"))).toMatchObject({ ok: false, error: { code: "outside_root" } });
      expect(decode(await fs.readFile(`${outside}/secret.txt`))).toBe("secret");
    });

    it("removes only the link when a link to the outside is deleted, even recursively", async () => {
      const { store, project, outside, symlink, fs } = await setup();
      symlink(outside, `${project}/escape`);
      expect(await store.remove(rel("escape"), { recursive: true })).toEqual({ ok: true, value: undefined });
      expect(await fs.readdir(project)).toEqual([]);
      expect(decode(await fs.readFile(`${outside}/secret.txt`))).toBe("secret");
    });
  });
});
