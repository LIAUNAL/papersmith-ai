import { hashBytes, type ContentHash, type RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { createProjectStore } from "../src/project-store.ts";
import { createUserWriteLog } from "../src/user-writes.ts";
import { cleanupSandboxes, implementations } from "./support/fs-sandbox.ts";

const encode = (text: string) => new TextEncoder().encode(text);
const rel = (path: string) => path as RelPath;
const hashOf = (text: string) => hashBytes(encode(text));

cleanupSandboxes();

describe.each(implementations)("project store user-write attribution and modes: %s", (_name, create) => {
  async function setup() {
    const box = create();
    const project = `${box.root}/project`;
    await box.fs.mkdir(project, { recursive: true });
    const log = createUserWriteLog();
    const store = createProjectStore({ fs: box.fs, root: project, userWrites: log });
    return { ...box, project, store, log };
  }

  describe("a save that is on disk but not recorded yet", () => {
    /** A file system whose rename on `held` completes on disk, then waits: the window between the rename and the record. */
    async function gated(held: string) {
      const box = await setup();
      let release: () => void = () => {};
      const gate = new Promise<void>((resolve) => (release = resolve));
      let renamed: () => void = () => {};
      const onDisk = new Promise<void>((resolve) => (renamed = resolve));
      // A derived object, because a spread would drop the methods of a class instance.
      const slow = Object.create(box.fs) as typeof box.fs;
      slow.rename = async (from: string, to: string) => {
        await box.fs.rename(from, to);
        if (to.endsWith(held)) {
          renamed();
          await gate;
        }
      };
      const store = createProjectStore({ fs: slow, root: box.project, userWrites: box.log });
      return { ...box, store, release, onDisk };
    }

    it("makes ending the recording wait for the save, so the save is attributed to the user", async () => {
      const { store, log, fs, project, release, onDisk } = await gated("a.tex");
      await fs.writeFile(`${project}/a.tex`, encode("agent"));
      log.begin();
      const saving = store.write(rel("a.tex"), encode("user"), await hashOf("agent"));
      await onDisk;
      expect(await fs.readFile(`${project}/a.tex`)).toEqual(encode("user"));
      let ended = false;
      const ending = log.end().then((writes) => {
        ended = true;
        return writes;
      });
      await new Promise((resolve) => setTimeout(resolve, 20));
      expect(ended).toBe(false);
      release();
      expect((await saving).ok).toBe(true);
      const writes = await ending;
      expect(writes.get(rel("a.tex"))).toEqual({ first: await hashOf("agent"), last: await hashOf("user") });
    });

    it("waits for a rename and a removal in flight in the same way", async () => {
      const { store, log, fs, project, release, onDisk } = await gated("moved.tex");
      await fs.writeFile(`${project}/a.tex`, encode("one"));
      log.begin();
      const moving = store.rename(rel("a.tex"), rel("moved.tex"));
      await onDisk;
      const ending = log.end();
      release();
      await moving;
      const writes = await ending;
      expect(writes.get(rel("a.tex"))).toEqual({ first: await hashOf("one"), last: null });
      expect(writes.get(rel("moved.tex"))).toEqual({ first: null, last: await hashOf("one") });
    });

    it("does not wait when nothing is in flight, and a failed save does not block the end", async () => {
      const { store, log, fs, project } = await setup();
      await fs.writeFile(`${project}/a.tex`, encode("one"));
      log.begin();
      expect((await store.write(rel("a.tex"), encode("x"), await hashOf("stale"))).ok).toBe(false);
      expect((await log.end()).size).toBe(0);
    });
  });

  describe("recording", () => {
    it("reports the hashes before and after a save, a create and a delete made during a turn", async () => {
      const { store, log, fs, project } = await setup();
      await fs.writeFile(`${project}/a.tex`, encode("one"));
      await fs.writeFile(`${project}/gone.tex`, encode("bye"));

      log.begin();
      await store.write(rel("a.tex"), encode("two"), await hashOf("one"));
      await store.write(rel("new.tex"), encode("fresh"), null);
      await store.remove(rel("gone.tex"));
      const writes = await log.end();

       expect(writes.get(rel("a.tex"))).toEqual({ first: await hashOf("one"), last: await hashOf("two") });
      expect(writes.get(rel("new.tex"))).toEqual({ first: null, last: await hashOf("fresh") });
      expect(writes.get(rel("gone.tex"))).toEqual({ first: await hashOf("bye"), last: null });
    });

    it("sees the unconditional write that the hash-checked one does not cover", async () => {
      const { store, log, fs, project } = await setup();
      await fs.writeFile(`${project}/a.tex`, encode("one"));
      log.begin();
      await store.write(rel("a.tex"), encode("two"), "any");
      expect((await log.end()).get(rel("a.tex"))).toEqual({ first: await hashOf("one"), last: await hashOf("two") });
    });

    it("records nothing outside a turn, and nothing for a rejected save", async () => {
      const { store, log, fs, project } = await setup();
      await fs.writeFile(`${project}/a.tex`, encode("one"));
      await store.write(rel("a.tex"), encode("two"), await hashOf("one"));

      log.begin();
      const stale = await store.write(rel("a.tex"), encode("three"), await hashOf("one"));
      expect(stale.ok).toBe(false);
      expect((await log.end()).size).toBe(0);
    });

    it("records every file under a folder that is renamed or removed", async () => {
      const { store, log, fs, project } = await setup();
      await fs.mkdir(`${project}/chapters/deep`, { recursive: true });
      await fs.writeFile(`${project}/chapters/one.tex`, encode("1"));
      await fs.writeFile(`${project}/chapters/deep/two.tex`, encode("2"));
      await fs.mkdir(`${project}/old`);
      await fs.writeFile(`${project}/old/three.tex`, encode("3"));

      log.begin();
      expect((await store.rename(rel("chapters"), rel("parts"))).ok).toBe(true);
      expect((await store.remove(rel("old"), { recursive: true })).ok).toBe(true);
      const writes = await log.end();

      expect([...writes.keys()].sort()).toEqual([
        "chapters/deep/two.tex",
        "chapters/one.tex",
        "old/three.tex",
        "parts/deep/two.tex",
        "parts/one.tex",
      ]);
      expect(writes.get(rel("chapters/one.tex"))).toEqual({ first: await hashOf("1"), last: null });
      expect(writes.get(rel("parts/one.tex"))).toEqual({ first: null, last: await hashOf("1") });
    });
  });

  describe("modes and conditional removal", () => {
    it("writes a new file with the permission bits asked for, and changes the bits of an existing one", async () => {
      const { store, fs, project } = await setup();
      await store.write(rel("run.sh"), encode("#!/bin/sh"), null, { mode: 0o755 });
      expect((await fs.stat(`${project}/run.sh`)).mode).toBe(0o755);

      await store.write(rel("run.sh"), encode("#!/bin/sh\n"), "any", { mode: 0o640 });
      expect((await fs.stat(`${project}/run.sh`)).mode).toBe(0o640);
    });

    it("removes a file only when its hash is the expected one", async () => {
      const { store, fs, project } = await setup();
      await fs.writeFile(`${project}/a.tex`, encode("one"));
      const wrong = await store.remove(rel("a.tex"), { expect: await hashOf("other") });
      expect(wrong).toEqual({ ok: false, error: { code: "conflict", path: "a.tex", currentHash: await hashOf("one") } });
      expect((await fs.stat(`${project}/a.tex`)).isFile()).toBe(true);

      expect((await store.remove(rel("a.tex"), { expect: await hashOf("one") })).ok).toBe(true);
      await expect(fs.stat(`${project}/a.tex`)).rejects.toMatchObject({ code: "ENOENT" });
    });

    it("reports a file that is already gone as a conflict with no current hash", async () => {
      const { store } = await setup();
      const expected: ContentHash = await hashOf("one");
      expect(await store.remove(rel("a.tex"), { expect: expected })).toEqual({
        ok: false,
        error: { code: "conflict", path: "a.tex", currentHash: null },
      });
    });
  });
});
