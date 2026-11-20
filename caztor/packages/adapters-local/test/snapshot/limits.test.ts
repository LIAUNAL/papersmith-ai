import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { hashOf, implementations, setupSnapshots } from "./support.ts";

cleanupSandboxes();

type FilesRecord = Record<string, { hash: string | null; size: number; undoable: boolean }>;

describe.each(implementations)("snapshot limits: %s", (_name, create) => {
  it("tracks a file over 5 MB by size and time without a copy, and reports it as not protected", async () => {
    const t = await setupSnapshots(create);
    await t.put("big.bin", new Uint8Array(6 * 1024 * 1024).fill(7));
    await t.put("main.tex", "small");

    const result = await t.snapshots.capture("t1");

    expect(result).toEqual({ ok: true, value: { partial: true, unprotected: ["big.bin"] } });
    const files = (await t.manifest("t1"))["files"] as FilesRecord;
    expect(files["big.bin"]).toMatchObject({ hash: null, size: 6 * 1024 * 1024, undoable: false });
    expect(files["main.tex"]).toMatchObject({ hash: await hashOf("small"), undoable: true });
    expect(await t.fs.readdir(`${t.project}/.caztor/snapshots/blobs`)).toHaveLength(1);
  });

  it("leaves environment, dependency and cache folders out of the snapshot at any depth", async () => {
    const t = await setupSnapshots(create);
    await t.put("main.tex", "paper");
    for (const path of [".micromamba/envs/a.py", "code/.venv/lib/b.py", "code/src/__pycache__/c.pyc", "code/.mypy_cache/d.json"]) await t.put(path, "tool file");
    const result = await t.snapshots.capture("t1");
    expect(result).toEqual({ ok: true, value: { partial: false, unprotected: [] } });
    expect(Object.keys((await t.manifest("t1"))["files"] as FilesRecord)).toEqual(["main.tex"]);
  });

  it("copies a file of exactly 5 MB", async () => {
    const t = await setupSnapshots(create);
    await t.put("edge.bin", new Uint8Array(5 * 1024 * 1024).fill(1));
    const result = await t.snapshots.capture("t1");
    expect(result).toEqual({ ok: true, value: { partial: false, unprotected: [] } });
  });

  it("protects only the first files in path order once the file count limit is reached", async () => {
    const t = await setupSnapshots(create, { limits: { maxFiles: 3 } });
    for (const name of ["a", "b", "c", "d", "e"]) await t.put(`${name}.tex`, `content ${name}`);

    const result = await t.snapshots.capture("t1");

    expect(result).toEqual({ ok: true, value: { partial: true, unprotected: ["d.tex", "e.tex"] } });
    const files = (await t.manifest("t1"))["files"] as FilesRecord;
    expect(Object.keys(files)).toHaveLength(5);
    expect(files["c.tex"]?.undoable).toBe(true);
    expect(files["d.tex"]).toMatchObject({ hash: null, undoable: false });
  });

  it("stops copying new content past the byte limit but keeps tracking the rest", async () => {
    const t = await setupSnapshots(create, { limits: { maxNewBytes: 250 } });
    for (const name of ["a", "b", "c"]) await t.put(`${name}.txt`, name.repeat(100));

    const result = await t.snapshots.capture("t1");

    expect(result).toEqual({ ok: true, value: { partial: true, unprotected: ["c.txt"] } });
    expect(((await t.manifest("t1"))["files"] as FilesRecord)["c.txt"]).toMatchObject({ hash: null, size: 100, undoable: false });
  });

  it("counts only new content against the byte limit, not copies that already exist", async () => {
    const t = await setupSnapshots(create, { limits: { maxNewBytes: 250 } });
    await t.put("a.txt", "a".repeat(100));
    await t.put("b.txt", "b".repeat(100));
    expect((await t.snapshots.capture("t1")).ok).toBe(true);
    await t.put("c.txt", "c".repeat(100));

    const second = await t.snapshots.capture("t2");

    expect(second).toEqual({ ok: true, value: { partial: false, unprotected: [] } });
  });

  it("reports nothing as unprotected for a small project", async () => {
    const t = await setupSnapshots(create);
    await t.put("a.tex", "one");
    expect(await t.snapshots.capture("t1")).toEqual({ ok: true, value: { partial: false, unprotected: [] } });
  });
});
