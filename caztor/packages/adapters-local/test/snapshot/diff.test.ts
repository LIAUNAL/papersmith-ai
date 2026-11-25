import type { ContentHash, RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { decode, encode, hashOf, implementations, rel, setupSnapshots } from "./support.ts";

cleanupSandboxes();

const none = new Map<RelPath, { first: ContentHash | null; last: ContentHash | null }>();

describe.each(implementations)("snapshot diff: %s", (_name, create) => {
  async function project() {
    const t = await setupSnapshots(create);
    await t.put("a.tex", "alpha");
    await t.put("b.tex", "beta");
    await t.put("c.tex", "gamma");
    return t;
  }

  it("lists created, modified and deleted files with their hashes, sorted by path", async () => {
    const t = await project();
    await t.snapshots.capture("t1");
    await t.put("a.tex", "alpha edited");
    await t.fs.rm(`${t.project}/b.tex`);
    await t.put("sections/new.tex", "fresh");

    const files = await t.snapshots.diff("t1", none);

    expect(files).toEqual([
      { path: "a.tex", change: "modified", beforeHash: await hashOf("alpha"), afterHash: await hashOf("alpha edited"), undoable: true, mixed: false },
      { path: "b.tex", change: "deleted", beforeHash: await hashOf("beta"), afterHash: null, undoable: true, mixed: false },
      { path: "sections/new.tex", change: "created", beforeHash: null, afterHash: await hashOf("fresh"), undoable: true, mixed: false },
    ]);
  });

  it("returns an empty list when nothing changed, even though the project has files", async () => {
    const t = await project();
    await t.snapshots.capture("t1");
    expect(await t.snapshots.diff("t1", none)).toEqual([]);
  });

  it("reports a file whose permission bits changed as modified with the same content hash", async () => {
    const t = await project();
    await t.snapshots.capture("t1");
    await t.fs.chmod(`${t.project}/a.tex`, 0o755);

    expect(await t.snapshots.diff("t1", none)).toEqual([
      { path: "a.tex", change: "modified", beforeHash: await hashOf("alpha"), afterHash: await hashOf("alpha"), undoable: true, mixed: false },
    ]);
  });

  it("ignores the snapshot folder and the other reserved folders when listing changes", async () => {
    const t = await project();
    await t.snapshots.capture("t1");
    await t.put(".claude/agents/caztor.md", "agent");
    await t.put("node_modules/x/index.js", "dep");
    await t.put(".caztor/state.json", "{}");

    expect(await t.snapshots.diff("t1", none)).toEqual([]);
  });

  it("keeps the provisioned writing guides out of the snapshot, the changed files and undo", async () => {
    const t = await project();
    await t.put(".caztor/guides/INDEX.md", "index v1");
    await t.put(".caztor/guides/08-abstract.md", "abstract v1");
    await t.snapshots.capture("t1");
    await t.put(".caztor/guides/INDEX.md", "index v2");
    await t.put(".caztor/guides/10-back-matter.md", "new guide");
    await t.fs.rm(`${t.project}/.caztor/guides/08-abstract.md`);
    await t.put("a.tex", "alpha by agent");

    const files = await t.snapshots.diff("t1", none);

    expect(files.map((file) => file.path)).toEqual(["a.tex"]);
    const restored = await t.snapshots.restore("t1", "strict");
    expect(restored).toMatchObject({ status: "restored", files: ["a.tex"] });
    expect(decode(await t.fs.readFile(`${t.project}/.caztor/guides/INDEX.md`))).toBe("index v2");
    expect(await t.exists(".caztor/guides/10-back-matter.md")).toBe(true);
    expect(await t.exists(".caztor/guides/08-abstract.md")).toBe(false);
  });

  it("returns nothing for a turn that has no snapshot", async () => {
    const t = await project();
    expect(await t.snapshots.diff("never", none)).toEqual([]);
  });

  describe("attribution of user edits", () => {
    it("leaves out a file only the user changed, and keeps the file the agent changed", async () => {
      const t = await project();
      await t.snapshots.capture("t1");
      t.userWrites.begin();
      await t.put("a.tex", "alpha by agent");
      await t.store.write(rel("c.tex"), encode("gamma by user"), await hashOf("gamma"));
      const writes = await t.userWrites.end();

      const files = await t.snapshots.diff("t1", writes);

      expect(files.map((file) => [file.path, file.change, file.mixed])).toEqual([["a.tex", "modified", false]]);
    });

    it("leaves out a file the user created or deleted during the turn", async () => {
      const t = await project();
      await t.snapshots.capture("t1");
      t.userWrites.begin();
      await t.store.write(rel("mine.tex"), encode("new"), null);
      await t.store.remove(rel("b.tex"));
      const writes = await t.userWrites.end();

      expect(await t.snapshots.diff("t1", writes)).toEqual([]);
    });

    it("flags a file both changed as mixed when the agent wrote first and the user saved over it", async () => {
      const t = await project();
      await t.snapshots.capture("t1");
      t.userWrites.begin();
      await t.put("a.tex", "alpha by agent");
      await t.store.write(rel("a.tex"), encode("alpha by user"), await hashOf("alpha by agent"));
      const writes = await t.userWrites.end();

      const files = await t.snapshots.diff("t1", writes);

      expect(files).toEqual([
        { path: "a.tex", change: "modified", beforeHash: await hashOf("alpha"), afterHash: await hashOf("alpha by user"), undoable: true, mixed: true },
      ]);
    });

    it("flags a file both changed as mixed when the user saved first and the agent wrote over it", async () => {
      const t = await project();
      await t.snapshots.capture("t1");
      t.userWrites.begin();
      await t.store.write(rel("a.tex"), encode("alpha by user"), await hashOf("alpha"));
      await t.put("a.tex", "alpha by agent");
      const writes = await t.userWrites.end();

      const files = await t.snapshots.diff("t1", writes);

      expect(files.map((file) => [file.path, file.mixed])).toEqual([["a.tex", true]]);
    });

    it("lists nothing for a file the user edited and then restored to its original content", async () => {
      const t = await project();
      await t.snapshots.capture("t1");
      t.userWrites.begin();
      await t.store.write(rel("a.tex"), encode("temporary"), await hashOf("alpha"));
      await t.store.write(rel("a.tex"), encode("alpha"), await hashOf("temporary"));
      const writes = await t.userWrites.end();

      expect(await t.snapshots.diff("t1", writes)).toEqual([]);
    });
  });

  describe("files that are not copied", () => {
    it("does not report an unchanged large file, and reports an edited one as modified but not undoable", async () => {
      const t = await setupSnapshots(create);
      await t.put("big.bin", new Uint8Array(6 * 1024 * 1024).fill(1));
      await t.put("main.tex", "m");
      await t.snapshots.capture("t1");
      expect(await t.snapshots.diff("t1", none)).toEqual([]);

      await t.put("big.bin", new Uint8Array(6 * 1024 * 1024).fill(2));
      const files = await t.snapshots.diff("t1", none);
      expect(files).toHaveLength(1);
      expect(files[0]).toMatchObject({ path: "big.bin", change: "modified", beforeHash: null, undoable: false, mixed: false });
    });

    it("reports a large file the turn deleted as deleted and not undoable", async () => {
      const t = await setupSnapshots(create);
      await t.put("big.bin", new Uint8Array(6 * 1024 * 1024).fill(1));
      await t.snapshots.capture("t1");
      await t.fs.rm(`${t.project}/big.bin`);
      expect(await t.snapshots.diff("t1", none)).toEqual([
        { path: "big.bin", change: "deleted", beforeHash: null, afterHash: null, undoable: false, mixed: false },
      ]);
    });
  });
});
