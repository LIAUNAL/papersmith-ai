import { utimesSync, writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { FsDirent } from "../../src/infra.ts";
import { cleanupSandboxes, implementations } from "../support/fs-sandbox.ts";
import { hashOf, setupSnapshots } from "./support.ts";

cleanupSandboxes();

const none = new Map();
const linkAt = (t: Awaited<ReturnType<typeof setupSnapshots>>, path: string) => t.fs.lstat(`${t.project}/${path}`).then((stats) => stats.isSymbolicLink());
const names = async (t: Awaited<ReturnType<typeof setupSnapshots>>, dir: string) => (await t.fs.readdir(`${t.project}/${dir}`)).map((entry) => entry.name).sort();

describe.each(implementations)("snapshot hardening: %s", (_name, create) => {
  describe("undo never writes through a link", () => {
    it.each(["strict", "skip_conflicts", "force"] as const)("leaves the target of a link that replaced a file alone in %s mode", async (mode) => {
      const t = await setupSnapshots(create);
      await t.put("f.tex", "original f");
      await t.put("other.tex", "other");
      await t.snapshots.capture("t1");
      await t.fs.rm(`${t.project}/f.tex`);
      t.symlink(`${t.project}/other.tex`, `${t.project}/f.tex`);
      await t.snapshots.diff("t1", none);

      const result = await t.snapshots.restore("t1", mode);

      expect(await t.text("other.tex")).toBe("other");
      expect(await linkAt(t, "f.tex")).toBe(true);
      if (result.status === "restored") expect(result.skipped).toEqual(["f.tex"]);
    });

    it("does not restore a file into a folder that the turn replaced with a link", async () => {
      const t = await setupSnapshots(create);
      await t.put("d/x.tex", "x in d");
      await t.put("elsewhere/keep.tex", "keep");
      await t.snapshots.capture("t1");
      await t.fs.rm(`${t.project}/d`, { recursive: true });
      t.symlink(`${t.project}/elsewhere`, `${t.project}/d`);
      await t.snapshots.diff("t1", none);

      const result = await t.snapshots.restore("t1", "force");

      expect(await names(t, "elsewhere")).toEqual(["keep.tex"]);
      expect(result.status === "restored" ? result.skipped : []).toEqual(["d/x.tex"]);
    });

    it("still restores a plain file the same way when no link is involved", async () => {
      const t = await setupSnapshots(create);
      await t.put("f.tex", "original f");
      await t.snapshots.capture("t1");
      await t.put("f.tex", "changed");
      await t.snapshots.diff("t1", none);

      expect(await t.snapshots.restore("t1", "force")).toEqual({ status: "restored", files: ["f.tex"], skipped: [] });
      expect(await t.text("f.tex")).toBe("original f");
    });
  });

  describe("safety snapshots", () => {
    it("keeps the newest five and collects the copies only the older ones used", async () => {
      const t = await setupSnapshots(create);
      for (let index = 1; index <= 8; index += 1) {
        await t.put("a.tex", `v${index}`);
        await t.snapshots.capture(`t${index}`);
        await t.put("a.tex", `agent ${index}`);
        await t.snapshots.diff(`t${index}`, none);
        expect((await t.snapshots.restore(`t${index}`, "strict")).status).toBe("restored");
      }

      expect(await names(t, ".caztor/snapshots/safety")).toHaveLength(5);
      const blobs = await names(t, ".caztor/snapshots/blobs");
      const blobOf = async (text: string) => (await hashOf(text)).slice("sha256:".length);
      expect(blobs).toContain(await blobOf("agent 8"));
      expect(blobs).toContain(await blobOf("agent 4"));
      expect(blobs).not.toContain(await blobOf("agent 3"));
      expect(blobs).not.toContain(await blobOf("agent 1"));
    });
  });

  describe("names the disk cannot open", () => {
    const lossy = (entries: FsDirent[]): FsDirent[] => [...entries, { name: "bad�.tex", isFile: () => true, isDirectory: () => false, isSymbolicLink: () => false }];
    const withBadName = (path: string, entries: FsDirent[]) => (path.endsWith("/project") ? lossy(entries) : entries);

    it("takes the snapshot anyway and reports the name as not protected", async () => {
      const t = await setupSnapshots(create, { hooks: { readdir: withBadName } });
      await t.put("a.tex", "alpha");

      const result = await t.raw.capture("t1");

      expect(result).toEqual({ ok: true, value: { partial: true, unprotected: ["bad�.tex"] } });
      expect((await t.manifest("t1"))["files"]).toHaveProperty(["a.tex", "hash"], await hashOf("alpha"));
    });

    it("leaves the name out of the file list instead of failing the listing", async () => {
      const t = await setupSnapshots(create, { hooks: { readdir: withBadName } });
      await t.put("a.tex", "alpha");

      expect((await t.store.list()).map((entry) => entry.path)).toEqual(["a.tex"]);
    });
  });

  describe("a content change that keeps the size and the modification time", () => {
    const stamp = Math.floor((Date.now() - 3_600_000) / 1000) * 1000;

    async function setup() {
      const t = await setupSnapshots(create);
      await t.put("a.tex", "aaaa");
      t.setMtime(`${t.project}/a.tex`, stamp);
      return t;
    }

    it("is hashed again by the next capture", async () => {
      const t = await setup();
      await t.snapshots.capture("t1");
      await t.put("a.tex", "bbbb");
      t.setMtime(`${t.project}/a.tex`, stamp);

      await t.snapshots.capture("t2");

      expect((await t.manifest("t2"))["files"]).toHaveProperty(["a.tex", "hash"], await hashOf("bbbb"));
    });

    it("is reported by the diff and put back by the undo", async () => {
      const t = await setup();
      await t.snapshots.capture("t1");
      await t.put("a.tex", "bbbb");
      t.setMtime(`${t.project}/a.tex`, stamp);

      const changes = await t.snapshots.diff("t1", none);

      expect(changes.map((change) => [change.path, change.change])).toEqual([["a.tex", "modified"]]);
      expect((await t.snapshots.restore("t1", "strict")).status).toBe("restored");
      expect(await t.text("a.tex")).toBe("aaaa");
    });

    it("still reuses the hash of a file nobody touched", async () => {
      let reads = 0;
      const counting = await setupSnapshots(create, { hooks: { readFile: () => void (reads += 1) } });
      await counting.put("a.tex", "aaaa");
      counting.setMtime(`${counting.project}/a.tex`, stamp);
      await counting.snapshots.capture("c1");
      const afterFirst = reads;

      await counting.snapshots.capture("c2");

      expect(afterFirst).toBeGreaterThan(0);
      // Neither the file nor the first turn's manifest, which this store wrote and still knows, is read again.
      expect(reads).toBe(afterFirst);
    });
  });

  describe("empty folders", () => {
    it("recreates an empty folder the turn deleted and removes an empty folder the turn created", async () => {
      const t = await setupSnapshots(create);
      await t.put("a.tex", "alpha");
      await t.fs.mkdir(`${t.project}/empty`);
      await t.fs.mkdir(`${t.project}/nest/inner`, { recursive: true });
      await t.snapshots.capture("t1");
      await t.put("a.tex", "alpha by the agent");
      await t.fs.rm(`${t.project}/empty`, { recursive: true });
      await t.fs.rm(`${t.project}/nest`, { recursive: true });
      await t.fs.mkdir(`${t.project}/made/deeper`, { recursive: true });
      await t.snapshots.diff("t1", none);

      expect((await t.snapshots.restore("t1", "strict")).status).toBe("restored");

      expect(await names(t, "")).toEqual([".caztor", "a.tex", "empty", "nest"]);
      expect(await names(t, "nest")).toEqual(["inner"]);
    });

    it("counts a turn that only changed folders as something to undo", async () => {
      const t = await setupSnapshots(create);
      await t.put("a.tex", "alpha");
      await t.fs.mkdir(`${t.project}/empty`);
      await t.snapshots.capture("t1");
      await t.fs.rm(`${t.project}/empty`, { recursive: true });
      await t.snapshots.diff("t1", none);

      expect(await t.snapshots.undoable()).toBe("t1");
      expect((await t.snapshots.restore("t1", "strict")).status).toBe("restored");
      expect(await names(t, "")).toEqual([".caztor", "a.tex", "empty"]);
    });

    it("leaves a created folder alone when it holds a file the turn did not create", async () => {
      const t = await setupSnapshots(create);
      await t.put("a.tex", "alpha");
      await t.snapshots.capture("t1");
      await t.put("a.tex", "alpha by the agent");
      await t.fs.mkdir(`${t.project}/made`);
      await t.snapshots.diff("t1", none);
      await t.put("made/mine.tex", "written by the user afterwards");

      await t.snapshots.restore("t1", "force");

      expect(await names(t, "made")).toEqual(["mine.tex"]);
    });
  });

  describe("the manifest is untrusted", () => {
    it("restores permission bits without setuid, setgid or sticky", async () => {
      const t = await setupSnapshots(create);
      await t.put("run.sh", "#!/bin/sh", 0o755);
      await t.snapshots.capture("t1");
      await t.put("run.sh", "changed");
      await t.snapshots.diff("t1", none);
      const tampered = await t.manifest("t1");
      const changes = tampered["changes"] as Array<Record<string, unknown>>;
      changes[0]!["beforeMode"] = 0o6755;
      await t.fs.writeFile(`${t.project}/.caztor/snapshots/turns/t1.json`, new TextEncoder().encode(JSON.stringify(tampered)));

      expect((await t.snapshots.restore("t1", "force")).status).toBe("restored");

      expect((await t.fs.stat(`${t.project}/run.sh`)).mode).toBe(0o755);
    });

    it("refuses a manifest that lists one path twice", async () => {
      const t = await setupSnapshots(create);
      await t.put("a.tex", "alpha");
      await t.snapshots.capture("t1");
      await t.put("a.tex", "changed");
      await t.snapshots.diff("t1", none);
      const tampered = await t.manifest("t1");
      const changes = tampered["changes"] as unknown[];
      changes.push(changes[0]);
      await t.fs.writeFile(`${t.project}/.caztor/snapshots/turns/t1.json`, new TextEncoder().encode(JSON.stringify(tampered)));

      expect(await t.snapshots.restore("t1", "force")).toEqual({ status: "unavailable", reason: "discarded" });
      expect(await t.text("a.tex")).toBe("changed");
    });

    it("removes temporary files left in the copy folder when it prunes", async () => {
      const t = await setupSnapshots(create);
      await t.put("a.tex", "alpha");
      await t.snapshots.capture("t1");
      await t.fs.writeFile(`${t.project}/.caztor/snapshots/blobs/${"a".repeat(64)}.1234.tmp`, new TextEncoder().encode("half"));

      await t.snapshots.prune(20);

      expect(await names(t, ".caztor/snapshots/blobs")).toEqual([(await hashOf("alpha")).slice("sha256:".length)]);
    });
  });

  describe("when .caztor/snapshots is a link", () => {
    it("answers with a failure instead of throwing, and writes nothing outside", async () => {
      const t = await setupSnapshots(create);
      await t.put("a.tex", "alpha");
      await t.snapshots.capture("t1");
      await t.fs.mkdir(`${t.root}/elsewhere`);
      await t.fs.rename(`${t.project}/.caztor/snapshots`, `${t.root}/moved`);
      t.symlink(`${t.root}/elsewhere`, `${t.project}/.caztor/snapshots`);

      const failed = { ok: false, error: { message: expect.stringContaining("not a plain folder") } };
      expect(await t.raw.undoable()).toEqual(failed);
      expect(await t.raw.diff("t1", none)).toEqual(failed);
      expect(await t.raw.prune(20)).toEqual(failed);
      expect(await t.raw.restore("t1", "strict")).toEqual({ status: "failed", message: expect.stringContaining("not a plain folder") });
      expect(await t.raw.capture("t2")).toEqual({ ok: false, error: { message: expect.stringContaining("not a plain folder") } });
      expect((await t.fs.readdir(`${t.root}/elsewhere`)).length).toBe(0);
    });
  });
});

describe("a file name that is not UTF-8 on the real disk", () => {
  it("is skipped by the snapshot and the file list, and reported as not protected", async () => {
    const [, create] = implementations[1]!;
    const t = await setupSnapshots(create);
    await t.put("a.tex", "alpha");
    writeFileSync(Buffer.concat([Buffer.from(`${t.project}/bad`), Buffer.from([0xff]), Buffer.from(".tex")]), "x");

    const result = await t.raw.capture("t1");

    expect(result).toEqual({ ok: true, value: { partial: true, unprotected: ["bad�.tex"] } });
    expect((await t.store.list()).map((entry) => entry.path)).toEqual(["a.tex"]);
  });
});

describe("a file the agent creates with a name that is not UTF-8", () => {
  it("is reported as not covered by undo, and undo leaves it where it is", async () => {
    const [, create] = implementations[1]!;
    const t = await setupSnapshots(create);
    await t.put("a.tex", "alpha");
    await t.raw.capture("t1");
    await t.put("a.tex", "alpha by agent");
    writeFileSync(Buffer.concat([Buffer.from(`${t.project}/made`), Buffer.from([0xfe]), Buffer.from(".tex")]), "by agent");

    const changes = await t.raw.diff("t1", none);
    expect(changes).toMatchObject({ ok: true, value: [{ path: "a.tex" }] });
    expect(await t.raw.notCovered()).toEqual({ ok: true, value: ["made�.tex"] });
    expect((await t.raw.restore("t1", "strict")).status).toBe("restored");
    expect(await t.text("a.tex")).toBe("alpha");
    expect(await t.raw.notCovered()).toEqual({ ok: true, value: ["made�.tex"] });
  });

  it("reports nothing when every name is readable", async () => {
    const [, create] = implementations[1]!;
    const t = await setupSnapshots(create);
    await t.put("a.tex", "alpha");
    expect(await t.raw.notCovered()).toEqual({ ok: true, value: [] });
  });
});

describe("a real disk keeps the change time when the modification time is set back", () => {
  it("shows that the signature of size and modification time alone cannot see the change", async () => {
    const [, create] = implementations[1]!;
    const t = await setupSnapshots(create);
    const path = `${t.project}/f.txt`;
    writeFileSync(path, "aaaa");
    utimesSync(path, 1000, 1000);
    const before = await t.fs.lstat(path);
    writeFileSync(path, "bbbb");
    utimesSync(path, 1000, 1000);
    const after = await t.fs.lstat(path);

    expect([after.size, after.mtimeMs]).toEqual([before.size, before.mtimeMs]);
    expect(after.ctimeMs).toBeGreaterThan(before.ctimeMs);
  });
});
