import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { encode, hashOf, implementations, rel, setupSnapshots, treeOf } from "./support.ts";

cleanupSandboxes();

const none = new Map();

describe.each(implementations)("undo of a turn: %s", (_name, create) => {
  type Setup = Awaited<ReturnType<typeof setupSnapshots>>;

  /** A project, a snapshot, then the agent modifies, deletes and creates files and changes a mode. */
  async function afterTurn(options: Parameters<typeof setupSnapshots>[1] = {}) {
    const t = await setupSnapshots(create, options);
    await t.put("a.tex", "alpha", 0o644);
    await t.put("b.tex", "beta", 0o644);
    await t.put("sections/deep/gone.tex", "will be deleted", 0o600);
    await t.put("run.sh", "#!/bin/sh", 0o755);
    await t.put("c.tex", "gamma", 0o644);
    const before = await treeOf(t);
    await t.snapshots.capture("t1");

    await t.put("a.tex", "alpha by the agent");
    await t.fs.rm(`${t.project}/sections`, { recursive: true });
    await t.put("new/dir/created.tex", "created by the agent");
    await t.put("d.tex", "created too");
    await t.fs.chmod(`${t.project}/run.sh`, 0o644);
    await t.fs.chmod(`${t.project}/c.tex`, 0o600);
    await t.snapshots.diff("t1", none);
    return { t, before };
  }

  const names = async (t: Setup) => (await t.fs.readdir(t.project)).map((entry) => entry.name).sort();

  it("restores the project to the snapshot: content, permission bits, deleted files and folders, and removes created ones", async () => {
    const { t, before } = await afterTurn();

    const result = await t.snapshots.restore("t1", "strict");

    expect(result).toEqual({
      status: "restored",
      files: ["a.tex", "c.tex", "d.tex", "new/dir/created.tex", "run.sh", "sections/deep/gone.tex"],
      skipped: [],
    });
    expect(await treeOf(t)).toEqual(before);
    expect((await t.fs.stat(`${t.project}/run.sh`)).mode).toBe(0o755);
    expect((await t.fs.stat(`${t.project}/sections/deep/gone.tex`)).mode).toBe(0o600);
    expect(await names(t)).toEqual([".caztor", "a.tex", "b.tex", "c.tex", "run.sh", "sections"]);
  });

  describe("later edits by the user", () => {
    it("writes nothing and names the file when the user edited it after the turn, and keeps the turn undoable", async () => {
      const { t } = await afterTurn();
      await t.put("a.tex", "alpha edited by the user");
      const snapshot = await treeOf(t);

      const result = await t.snapshots.restore("t1", "strict");

      expect(result).toEqual({
        status: "conflict",
        conflicts: [{ path: "a.tex", expected: await hashOf("alpha by the agent"), actual: await hashOf("alpha edited by the user") }],
      });
      expect(await treeOf(t)).toEqual(snapshot);
      expect(await t.exists(".caztor/snapshots/safety/t1.json")).toBe(false);
      expect(await t.snapshots.undoable()).toBe("t1");
    });

    it("names every conflicting file, including a created one the user changed and a deleted one the user recreated", async () => {
      const { t } = await afterTurn();
      await t.put("d.tex", "user rewrote the created file");
      await t.put("sections/deep/gone.tex", "user wrote it again");

      const result = await t.snapshots.restore("t1", "strict");

      expect(result.status).toBe("conflict");
      const conflicts = result.status === "conflict" ? result.conflicts : [];
      expect(conflicts.map((conflict) => conflict.path)).toEqual(["d.tex", "sections/deep/gone.tex"]);
      expect(conflicts[1]).toEqual({ path: "sections/deep/gone.tex", expected: null, actual: await hashOf("user wrote it again") });
    });

    it("treats a permission change after the turn as an edit", async () => {
      const { t } = await afterTurn();
      await t.fs.chmod(`${t.project}/run.sh`, 0o700);
      const result = await t.snapshots.restore("t1", "strict");
      expect(result.status).toBe("conflict");
    });

    it("restores the other files and keeps the edited one when asked to skip conflicts", async () => {
      const { t, before } = await afterTurn();
      await t.put("a.tex", "alpha edited by the user");

      const result = await t.snapshots.restore("t1", "skip_conflicts");

      expect(result).toEqual({
        status: "restored",
        files: ["c.tex", "d.tex", "new/dir/created.tex", "run.sh", "sections/deep/gone.tex"],
        skipped: ["a.tex"],
      });
      expect(await t.text("a.tex")).toBe("alpha edited by the user");
      expect(await treeOf(t)).toEqual({ ...before, "a.tex": `${await hashOf("alpha edited by the user")}:644` });
      expect(await t.snapshots.undoable()).toBeNull();
    });

    it("overwrites the edits when forced", async () => {
      const { t, before } = await afterTurn();
      await t.put("a.tex", "alpha edited by the user");
      await t.put("d.tex", "user rewrote the created file");

      const result = await t.snapshots.restore("t1", "force");

      expect(result.status).toBe("restored");
      expect(await treeOf(t)).toEqual(before);
    });

    it("handles a file both the user and the agent changed as a conflict even when the disk matches the turn's result", async () => {
      const t = await setupSnapshots(create);
      await t.put("a.tex", "alpha");
      await t.snapshots.capture("t1");
      t.userWrites.begin();
      await t.put("a.tex", "alpha by the agent");
      await t.store.write(rel("a.tex"), encode("alpha by both"), await hashOf("alpha by the agent"));
      const writes = await t.userWrites.end();
      const listed = await t.snapshots.diff("t1", writes);
      expect(listed.map((file) => [file.path, file.mixed])).toEqual([["a.tex", true]]);

      const strict = await t.snapshots.restore("t1", "strict");
      expect(strict).toEqual({ status: "conflict", conflicts: [{ path: "a.tex", expected: await hashOf("alpha by both"), actual: await hashOf("alpha by both") }] });
      expect(await t.text("a.tex")).toBe("alpha by both");

      expect(await t.snapshots.restore("t1", "force")).toEqual({ status: "restored", files: ["a.tex"], skipped: [] });
      expect(await t.text("a.tex")).toBe("alpha");
    });

    it("does not overwrite an edit that lands after the check and before the write", async () => {
      let edit: (() => Promise<void>) | null = null;
      const { t } = await afterTurn({
        hooks: {
          writeFile: async (path) => {
            if (path.includes("/safety/") && edit !== null) {
              const run = edit;
              edit = null;
              await run();
            }
          },
        },
      });
      edit = async () => {
        await t.fs.writeFile(`${t.project}/a.tex`, encode("typed during the undo"));
      };

      const result = await t.snapshots.restore("t1", "strict");

      expect(result.status).toBe("restored");
      expect(result.status === "restored" ? result.skipped : []).toContain("a.tex");
      expect(await t.text("a.tex")).toBe("typed during the undo");
    });
  });

  describe("the safety snapshot", () => {
    it("is stored, with the content about to be overwritten, before the first project file is written", async () => {
      const order: string[] = [];
      const { t } = await afterTurn({ hooks: { writeFile: (path) => void order.push(path) } });
      order.length = 0;

      await t.snapshots.restore("t1", "strict");

      const manifestAt = order.findIndex((path) => path.includes("/snapshots/safety/"));
      const firstProjectWrite = order.findIndex((path) => !path.includes("/.caztor/"));
      expect(manifestAt).toBeGreaterThanOrEqual(0);
      expect(firstProjectWrite).toBeGreaterThan(manifestAt);
      const files = (await t.manifest("t1", "safety"))["files"] as Record<string, { hash: string }>;
      expect(files["a.tex"]?.hash).toBe(await hashOf("alpha by the agent"));
      const blob = (await hashOf("alpha by the agent")).slice("sha256:".length);
      expect(await t.fs.stat(`${t.project}/.caztor/snapshots/blobs/${blob}`)).toBeTruthy();
    });

    it("is not on the undo stack and survives pruning", async () => {
      const { t } = await afterTurn();
      await t.snapshots.restore("t1", "strict");
      expect(await t.snapshots.undoable()).toBeNull();

      await t.snapshots.prune(0);

      expect(await t.exists(".caztor/snapshots/safety/t1.json")).toBe(true);
      const blob = (await hashOf("alpha by the agent")).slice("sha256:".length);
      expect(await t.exists(`.caztor/snapshots/blobs/${blob}`)).toBe(true);
    });

    it("stops the undo without touching the project when the safety snapshot cannot be taken", async () => {
      const { t } = await afterTurn({
        hooks: {
          writeFile: (path) => {
            if (path.includes("/snapshots/safety/")) throw Object.assign(new Error("ENOSPC: no space left on device"), { code: "ENOSPC" });
          },
        },
      });
      const snapshot = await treeOf(t);

      const result = await t.snapshots.restore("t1", "strict");

      expect(result.status).toBe("failed");
      expect(result.status === "failed" ? result.message : "").toContain("ENOSPC");
      expect(await treeOf(t)).toEqual(snapshot);
      expect(await t.snapshots.undoable()).toBe("t1");
    });
  });

  describe("files that cannot be restored", () => {
    it("skips a file that was not copied and restores the rest", async () => {
      const t = await setupSnapshots(create);
      await t.put("big.bin", new Uint8Array(6 * 1024 * 1024).fill(1));
      await t.put("a.tex", "alpha");
      await t.snapshots.capture("t1");
      await t.put("big.bin", new Uint8Array(6 * 1024 * 1024).fill(2));
      await t.put("a.tex", "changed");
      await t.snapshots.diff("t1", none);

      const result = await t.snapshots.restore("t1", "force");

      expect(result).toEqual({ status: "restored", files: ["a.tex"], skipped: ["big.bin"] });
      expect(await t.text("a.tex")).toBe("alpha");
    });

    it("refuses to write a copy whose content no longer matches its hash, and writes nothing", async () => {
      const { t } = await afterTurn();
      const blob = (await hashOf("alpha")).slice("sha256:".length);
      await t.fs.writeFile(`${t.project}/.caztor/snapshots/blobs/${blob}`, encode("tampered"));
      const snapshot = await treeOf(t);

      const result = await t.snapshots.restore("t1", "strict");

      expect(result.status).toBe("failed");
      expect(result.status === "failed" ? result.message : "").toContain("a.tex");
      expect(await treeOf(t)).toEqual(snapshot);
    });

    it("fails clearly, writing nothing, when a copy has been deleted from the snapshot folder", async () => {
      const { t } = await afterTurn();
      const blob = (await hashOf("will be deleted")).slice("sha256:".length);
      await t.fs.rm(`${t.project}/.caztor/snapshots/blobs/${blob}`, { force: true });
      const snapshot = await treeOf(t);

      const result = await t.snapshots.restore("t1", "strict");

      expect(result.status).toBe("failed");
      expect(result.status === "failed" ? result.message : "").toContain("sections/deep/gone.tex");
      expect(await treeOf(t)).toEqual(snapshot);
    });
  });

  describe("tampered metadata", () => {
    async function tamper(t: Setup, edit: (manifest: Record<string, any>) => void) {
      const path = `${t.project}/.caztor/snapshots/turns/t1.json`;
      const manifest = JSON.parse(new TextDecoder().decode(await t.fs.readFile(path))) as Record<string, any>;
      edit(manifest);
      await t.fs.writeFile(path, encode(JSON.stringify(manifest)));
    }

    it.each([
      ["a path that climbs out of the project", "../outside.tex"],
      ["an absolute path", "/tmp/caztor-outside.tex"],
      ["the git folder", ".git/hooks/pre-commit"],
      ["the state folder", ".caztor/state.json"],
      ["an agent folder", ".claude/agents/caztor.md"],
    ])("never restores %s named in the file list", async (_label, path) => {
      const { t } = await afterTurn();
      await t.fs.writeFile(`${t.root}/outside.tex`, encode("outside"));
      const hash = await hashOf("alpha");
      await tamper(t, (manifest) => {
        manifest["files"][path] = { hash, size: 5, mtimeMs: 1, mode: 0o644, undoable: true };
      });

      const result = await t.snapshots.restore("t1", "force");

      expect(result).toEqual({ status: "unavailable", reason: "discarded" });
      expect(new TextDecoder().decode(await t.fs.readFile(`${t.root}/outside.tex`))).toBe("outside");
      expect(await t.text("a.tex")).toBe("alpha by the agent");
    });

    it.each(["../outside.tex", "/etc/cron.d/evil", ".git/config", ".caztor/state.json"])("never acts on the recorded change to %j", async (path) => {
      const { t } = await afterTurn();
      await t.fs.writeFile(`${t.root}/outside.tex`, encode("outside"));
      await tamper(t, (manifest) => {
        manifest["changes"].push({ ...manifest["changes"][0], path, change: "created", beforeHash: null, beforeMode: null });
      });

      expect(await t.snapshots.restore("t1", "force")).toEqual({ status: "unavailable", reason: "discarded" });
      expect(new TextDecoder().decode(await t.fs.readFile(`${t.root}/outside.tex`))).toBe("outside");
    });

    it("never reads or writes outside the snapshot folder for a turn id taken from the request", async () => {
      const { t } = await afterTurn();
      expect(await t.snapshots.restore("../../project/.caztor/snapshots/turns/t1", "force")).toEqual({ status: "unavailable", reason: "discarded" });
      expect(await t.text("a.tex")).toBe("alpha by the agent");
    });
  });

  describe("containment", () => {
    it("does not write through a file that became a link leading out of the project", async () => {
      const { t } = await afterTurn();
      await t.fs.writeFile(`${t.root}/secret.txt`, encode("secret"));
      await t.fs.rm(`${t.project}/a.tex`);
      t.symlink(`${t.root}/secret.txt`, `${t.project}/a.tex`);

      const result = await t.snapshots.restore("t1", "force");

      expect(new TextDecoder().decode(await t.fs.readFile(`${t.root}/secret.txt`))).toBe("secret");
      expect(result.status).toBe("restored");
      expect(result.status === "restored" ? result.skipped : []).toContain("a.tex");
    });

    it("does not recreate a deleted file inside a folder that became a link leading out of the project", async () => {
      const { t } = await afterTurn();
      await t.fs.mkdir(`${t.root}/elsewhere`, { recursive: true });
      t.symlink(`${t.root}/elsewhere`, `${t.project}/sections`);

      const result = await t.snapshots.restore("t1", "force");

      expect(await t.fs.readdir(`${t.root}/elsewhere`)).toEqual([]);
      expect(result.status).toBe("restored");
      expect(result.status === "restored" ? result.skipped : []).toContain("sections/deep/gone.tex");
    });

    it("keeps files that the turn did not touch exactly as they are", async () => {
      const { t } = await afterTurn();
      await t.put("untouched.tex", "mine", 0o640);
      await t.snapshots.restore("t1", "force");
      expect(await t.text("untouched.tex")).toBe("mine");
      expect((await t.fs.stat(`${t.project}/untouched.tex`)).mode).toBe(0o640);
    });
  });

  it("removes the folders a turn created once their files are gone, and only those", async () => {
    const t = await setupSnapshots(create);
    await t.put("keep/old.tex", "old");
    await t.fs.mkdir(`${t.project}/empty-before`, { recursive: true });
    await t.snapshots.capture("t1");
    await t.put("keep/new.tex", "new");
    await t.put("fresh/inner/file.tex", "new");
    await t.snapshots.diff("t1", none);

    await t.snapshots.restore("t1", "strict");

    expect(await names(t)).toEqual([".caztor", "empty-before", "keep"]);
    expect((await t.fs.readdir(`${t.project}/keep`)).map((entry) => entry.name)).toEqual(["old.tex"]);
  });
});
