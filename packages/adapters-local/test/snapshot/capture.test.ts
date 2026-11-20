import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { decode, hashOf, implementations, setupSnapshots } from "./support.ts";

cleanupSandboxes();

describe.each(implementations)("snapshot capture: %s", (_name, create) => {
  it("stores the content of every file as a blob named by its hash and lists them in a manifest", async () => {
    const t = await setupSnapshots(create);
    await t.put("main.tex", "hello");
    await t.put("sections/intro.tex", "intro");
    await t.put("run.sh", "#!/bin/sh", 0o755);

    const result = await t.snapshots.capture("t1");

    expect(result).toEqual({ ok: true, value: { partial: false, unprotected: [] } });
    const hex = (await hashOf("hello")).slice("sha256:".length);
    expect(decode(await t.fs.readFile(`${t.project}/.caztor/snapshots/blobs/${hex}`))).toBe("hello");
    const files = (await t.manifest("t1"))["files"] as Record<string, Record<string, unknown>>;
    expect(Object.keys(files).sort()).toEqual(["main.tex", "run.sh", "sections/intro.tex"]);
    expect(files["main.tex"]).toMatchObject({ hash: await hashOf("hello"), size: 5, undoable: true });
    expect(files["run.sh"]?.["mode"]).toBe(0o755);
  });

  it("keeps one blob for files with the same content", async () => {
    const t = await setupSnapshots(create);
    await t.put("a.tex", "same");
    await t.put("b.tex", "same");
    await t.snapshots.capture("t1");
    expect(await t.fs.readdir(`${t.project}/.caztor/snapshots/blobs`)).toHaveLength(1);
  });

  it("reuses the hash of a file whose size and modification time did not change", async () => {
    const reads: string[] = [];
    const t = await setupSnapshots(create, { hooks: { readFile: (path) => void reads.push(path) } });
    await t.put("a.tex", "one");
    await t.put("b.tex", "two");
    await t.snapshots.capture("t1");
    const afterFirst = reads.filter((path) => path.endsWith(".tex")).length;
    expect(afterFirst).toBe(2);

    await t.snapshots.capture("t2");
    expect(reads.filter((path) => path.endsWith(".tex")).length).toBe(afterFirst);

    await t.put("b.tex", "TWO!");
    await t.snapshots.capture("t3");
    const read = reads.filter((path) => path.endsWith(".tex")).slice(afterFirst);
    expect(read).toEqual([`${t.project}/b.tex`]);
    const files = (await t.manifest("t3"))["files"] as Record<string, Record<string, unknown>>;
    expect(files["b.tex"]?.["hash"]).toBe(await hashOf("TWO!"));
    expect(files["a.tex"]?.["hash"]).toBe(await hashOf("one"));
  });

  it("hashes again a file written within two seconds of the previous snapshot, because its timestamp cannot be trusted", async () => {
    const reads: string[] = [];
    const probe = await setupSnapshots(create);
    await probe.put("a.tex", "one");
    const mtime = (await probe.fs.stat(`${probe.project}/a.tex`)).mtimeMs;

    const t = await setupSnapshots(create, { hooks: { readFile: (path) => void reads.push(path) }, clockStart: mtime + 10 });
    await t.put("a.tex", "one");
    const written = (await t.fs.stat(`${t.project}/a.tex`)).mtimeMs;
    t.clock.advance(Math.max(0, written - mtime));
    await t.snapshots.capture("t1");
    await t.snapshots.capture("t2");
    expect(reads.filter((path) => path.endsWith("a.tex"))).toHaveLength(2);
  });

  it("leaves out internal state, repositories, dependencies, agent folders, links and temporary files", async () => {
    const t = await setupSnapshots(create);
    await t.put("main.tex", "m");
    await t.put(".caztor/state.json", "{}");
    await t.put(".git/HEAD", "ref");
    await t.put("node_modules/pkg/index.js", "x");
    await t.put("sub/node_modules/pkg/index.js", "x");
    await t.put("sub/.git/config", "x");
    await t.put(".claude/agents/caztor.md", "x");
    await t.put(".opencode/agents/caztor.md", "x");
    await t.put(".agents/agents/caztor.md", "x");
    await t.put(".caztor-tmp-1234", "x");
    t.symlink(`${t.project}/main.tex`, `${t.project}/alias.tex`);

    await t.snapshots.capture("t1");

    const files = (await t.manifest("t1"))["files"] as Record<string, unknown>;
    expect(Object.keys(files)).toEqual(["main.tex"]);
  });

  it("returns a typed failure and writes no manifest when a file cannot be read", async () => {
    const t = await setupSnapshots(create, {
      hooks: {
        readFile: (path) => {
          if (path.endsWith("locked.tex")) throw Object.assign(new Error("EACCES: permission denied"), { code: "EACCES" });
        },
      },
    });
    await t.put("ok.tex", "fine");
    await t.put("locked.tex", "secret");

    const result = await t.snapshots.capture("t1");

    expect(result.ok).toBe(false);
    expect(!result.ok && result.error.message).toContain("locked.tex");
    expect(await t.exists(".caztor/snapshots/turns/t1.json")).toBe(false);
  });

  it("returns a typed failure when a blob cannot be written", async () => {
    const t = await setupSnapshots(create, {
      hooks: {
        writeFile: (path) => {
          if (path.includes("/snapshots/blobs/")) throw Object.assign(new Error("ENOSPC: no space left on device"), { code: "ENOSPC" });
        },
      },
    });
    await t.put("a.tex", "one");

    const result = await t.snapshots.capture("t1");

    expect(result.ok).toBe(false);
    expect(!result.ok && result.error.message).toContain("ENOSPC");
    expect(await t.exists(".caztor/snapshots/turns/t1.json")).toBe(false);
  });

  it.each(["", "../escape", "a/b", ".hidden", "x".repeat(65), "a b"])("refuses the turn id %j", async (turnId) => {
    const t = await setupSnapshots(create);
    await t.put("a.tex", "one");
    const result = await t.snapshots.capture(turnId);
    expect(result.ok).toBe(false);
    expect(await t.fs.readdir(t.project).then((entries) => entries.map((entry) => entry.name))).toEqual(["a.tex"]);
  });

  it("refuses to reuse a turn id", async () => {
    const t = await setupSnapshots(create);
    await t.put("a.tex", "one");
    expect((await t.snapshots.capture("t1")).ok).toBe(true);
    const again = await t.snapshots.capture("t1");
    expect(again.ok).toBe(false);
  });

  it("does not store anything outside the project when the snapshot folder is a link leading out", async () => {
    const t = await setupSnapshots(create);
    await t.put("a.tex", "one");
    await t.fs.mkdir(`${t.root}/elsewhere`, { recursive: true });
    await t.fs.mkdir(`${t.project}/.caztor`, { recursive: true });
    t.symlink(`${t.root}/elsewhere`, `${t.project}/.caztor/snapshots`);

    const result = await t.snapshots.capture("t1");

    expect(result.ok).toBe(false);
    expect(await t.fs.readdir(`${t.root}/elsewhere`)).toEqual([]);
  });

  it("does not let two captures of the same project overlap", async () => {
    const t = await setupSnapshots(create);
    await t.put("a.tex", "one");
    const [first, second] = await Promise.all([t.snapshots.capture("t1"), t.snapshots.capture("t2")]);
    expect(first.ok && second.ok).toBe(true);
    expect((await t.manifest("t1"))["seq"]).not.toBe((await t.manifest("t2"))["seq"]);
  });

  it("skips a file whose name cannot be a project path", async () => {
    const t = await setupSnapshots(create);
    await t.put("-dash.tex", "x");
    await t.put("ok.tex", "y");
    await t.snapshots.capture("t1");
    expect(Object.keys((await t.manifest("t1"))["files"] as object)).toEqual(["ok.tex"]);
  });
});

describe.each(implementations)("snapshot of the AGENTS.md that Caztor created: %s", (_name, create) => {
  it("leaves it out of the snapshot and the changed-files list when told it is Caztor's, and keeps a user's", async () => {
    const mine = await setupSnapshots(create, { skipAgentsMd: false });
    await mine.put("AGENTS.md", "user rules");
    await mine.snapshots.capture("t1");
    expect(Object.keys((await mine.manifest("t1"))["files"] as object)).toEqual(["AGENTS.md"]);

    const ours = await setupSnapshots(create, { skipAgentsMd: true });
    await ours.put("AGENTS.md", "managed");
    await ours.put("main.tex", "m");
    await ours.snapshots.capture("t1");
    expect(Object.keys((await ours.manifest("t1"))["files"] as object)).toEqual(["main.tex"]);
    await ours.put("AGENTS.md", "changed by the agent");
    expect(await ours.snapshots.diff("t1", new Map())).toEqual([]);
  });
});
