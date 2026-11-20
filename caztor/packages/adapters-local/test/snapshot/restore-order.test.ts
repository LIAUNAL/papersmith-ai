import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { implementations, setupSnapshots } from "./support.ts";

cleanupSandboxes();

const none = new Map();

describe.each(implementations)("undo order: %s", (_name, create) => {
  /** Turns t1..tN, each one edits a.tex after its snapshot and has its changes computed. */
  async function turns(count: number) {
    const t = await setupSnapshots(create);
    await t.put("a.tex", "version 0");
    for (let index = 1; index <= count; index += 1) {
      await t.snapshots.capture(`t${index}`);
      await t.put("a.tex", `version ${index}`);
      await t.snapshots.diff(`t${index}`, none);
    }
    return t;
  }

  it("undoes the most recent turn, then makes the one before it undoable", async () => {
    const t = await turns(3);
    expect(await t.snapshots.undoable()).toBe("t3");
    expect(await t.snapshots.restore("t1", "strict")).toEqual({ status: "unavailable", reason: "not_latest" });
    expect(await t.snapshots.restore("t2", "strict")).toEqual({ status: "unavailable", reason: "not_latest" });
    expect(await t.text("a.tex")).toBe("version 3");

    expect(await t.snapshots.restore("t3", "strict")).toEqual({ status: "restored", files: ["a.tex"], skipped: [] });
    expect(await t.text("a.tex")).toBe("version 2");

    expect(await t.snapshots.undoable()).toBe("t2");
    expect(await t.snapshots.restore("t1", "strict")).toEqual({ status: "unavailable", reason: "not_latest" });
    expect(await t.snapshots.restore("t2", "strict")).toEqual({ status: "restored", files: ["a.tex"], skipped: [] });
    expect(await t.text("a.tex")).toBe("version 1");
    expect(await t.snapshots.undoable()).toBe("t1");
  });

  it("refuses to undo a turn twice", async () => {
    const t = await turns(2);
    await t.snapshots.restore("t2", "strict");
    expect(await t.snapshots.restore("t2", "strict")).toEqual({ status: "unavailable", reason: "already_undone" });
    expect(await t.text("a.tex")).toBe("version 1");
  });

  it("reports a turn that was never taken or was discarded as discarded", async () => {
    const t = await turns(3);
    await t.snapshots.prune(1);
    expect(await t.snapshots.restore("t1", "strict")).toEqual({ status: "unavailable", reason: "discarded" });
    expect(await t.snapshots.restore("never", "strict")).toEqual({ status: "unavailable", reason: "discarded" });
    expect(await t.snapshots.restore("../escape", "strict")).toEqual({ status: "unavailable", reason: "discarded" });
    expect(await t.snapshots.restore("t3", "strict")).toMatchObject({ status: "restored" });
  });

  it("lets a turn undone earlier stay behind a newer one taken afterwards", async () => {
    const t = await turns(2);
    await t.snapshots.restore("t2", "strict");
    await t.snapshots.capture("t3");
    await t.put("a.tex", "version 3");
    await t.snapshots.diff("t3", none);

    expect(await t.snapshots.undoable()).toBe("t3");
    expect(await t.snapshots.restore("t1", "strict")).toEqual({ status: "unavailable", reason: "not_latest" });
    await t.snapshots.restore("t3", "strict");
    expect(await t.snapshots.undoable()).toBe("t1");
  });

  it("does nothing for a turn that changed no files", async () => {
    const t = await setupSnapshots(create);
    await t.put("a.tex", "one");
    await t.snapshots.capture("t1");
    await t.snapshots.diff("t1", none);
    expect(await t.snapshots.restore("t1", "strict")).toEqual({ status: "restored", files: [], skipped: [] });
    expect(await t.exists(".caztor/snapshots/safety/t1.json")).toBe(false);
  });

  it("serializes two undo requests for the same turn", async () => {
    const t = await turns(1);
    const results = await Promise.all([t.snapshots.restore("t1", "strict"), t.snapshots.restore("t1", "strict")]);
    expect(results.map((result) => result.status).sort()).toEqual(["restored", "unavailable"]);
  });
});
