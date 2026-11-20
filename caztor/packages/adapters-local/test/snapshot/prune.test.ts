import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { hashOf, implementations, setupSnapshots } from "./support.ts";

cleanupSandboxes();

describe.each(implementations)("snapshot retention and the undo stack top: %s", (_name, create) => {
  async function turns(count: number) {
    const t = await setupSnapshots(create);
    for (let index = 1; index <= count; index += 1) {
      await t.put("a.tex", `version ${index}`);
      await t.snapshots.capture(`t${index}`);
    }
    return t;
  }

  const blobCount = async (t: Awaited<ReturnType<typeof turns>>) => (await t.fs.readdir(`${t.project}/.caztor/snapshots/blobs`)).length;

  it("keeps the newest turns, discards the oldest first and returns their ids", async () => {
    const t = await turns(4);

    const discarded = await t.snapshots.prune(2);

    expect(discarded).toEqual(["t1", "t2"]);
    expect((await t.fs.readdir(`${t.project}/.caztor/snapshots/turns`)).map((entry) => entry.name).sort()).toEqual(["t3.json", "t4.json"]);
  });

  it("collects the copies that no retained turn needs and keeps the shared ones", async () => {
    const t = await setupSnapshots(create);
    await t.put("a.tex", "only in turn one");
    await t.put("shared.tex", "in every turn");
    await t.snapshots.capture("t1");
    await t.put("a.tex", "in turns two and three");
    await t.snapshots.capture("t2");
    await t.snapshots.capture("t3");
    expect(await blobCount(t)).toBe(3);

    await t.snapshots.prune(2);

    const blobs = (await t.fs.readdir(`${t.project}/.caztor/snapshots/blobs`)).map((entry) => entry.name).sort();
    const keep = [await hashOf("in turns two and three"), await hashOf("in every turn")].map((hash) => hash.slice("sha256:".length)).sort();
    expect(blobs).toEqual(keep);
  });

  it("discards nothing while the retained count is not exceeded", async () => {
    const t = await turns(3);
    expect(await t.snapshots.prune(3)).toEqual([]);
    expect(await t.snapshots.prune(20)).toEqual([]);
    expect(await blobCount(t)).toBe(3);
  });

  it("retains the last 20 turns when asked to, discarding the oldest when a 21st arrives", async () => {
    const t = await turns(21);
    expect(await t.snapshots.prune(20)).toEqual(["t1"]);
  });

  it("names the newest turn as the one to undo, and nobody when there is none", async () => {
    const empty = await setupSnapshots(create);
    expect(await empty.snapshots.undoable()).toBeNull();

    const t = await turns(3);
    expect(await t.snapshots.undoable()).toBe("t3");
  });

  it("skips a turn that changed nothing, so it does not block the turn before it", async () => {
    const t = await setupSnapshots(create);
    await t.put("a.tex", "one");
    await t.snapshots.capture("t1");
    await t.put("a.tex", "two");
    expect(await t.snapshots.diff("t1", new Map())).toHaveLength(1);
    await t.snapshots.capture("t2");
    expect(await t.snapshots.diff("t2", new Map())).toEqual([]);

    expect(await t.snapshots.undoable()).toBe("t1");
  });

  it("counts a turn whose changes were not computed yet", async () => {
    const t = await setupSnapshots(create);
    await t.put("a.tex", "one");
    await t.snapshots.capture("t1");
    await t.snapshots.capture("t2");
    expect(await t.snapshots.undoable()).toBe("t2");
  });
});
