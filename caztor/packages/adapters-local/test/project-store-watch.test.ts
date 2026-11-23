import { hashBytes, type FileChange, type RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { createProjectStore, type ProjectStoreOptions } from "../src/project-store.ts";
import { FakeClock } from "./fakes/fake-clock.ts";
import { FakeDirectoryWatcher } from "./fakes/fake-watcher.ts";
import { cleanupSandboxes, implementations } from "./support/fs-sandbox.ts";

const encode = (text: string) => new TextEncoder().encode(text);
const rel = (path: string) => path as RelPath;
const hash = (text: string) => hashBytes(encode(text));

cleanupSandboxes();

const pause = (ms = 15) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Waits until `check` holds, for at most ten seconds of real time: a CI runner's file events can be slow. Each test gets 30 seconds, so this limit, not the test timeout, is what fails. */
async function until(check: () => boolean): Promise<void> {
  const limit = Date.now() + 10_000;
  while (!check()) {
    if (Date.now() > limit) throw new Error("The condition did not hold in time");
    await pause(5);
  }
}

/** The debounce of watcher events, and the safety rescan period, as the store defaults them. */
const DEBOUNCE_MS = 100;
const RESCAN_MS = 30_000;
/** The faster rescan used while the event watcher is not working. */
const FALLBACK_RESCAN_MS = 5000;

describe.each(implementations)("project store watching: %s", (_name, create) => {
  async function setup(extra: Partial<ProjectStoreOptions> = {}, files: Record<string, string> = {}) {
    const box = create();
    const project = `${box.root}/project`;
    await box.fs.mkdir(project, { recursive: true });
    for (const [path, text] of Object.entries(files)) {
      const parent = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
      if (parent !== "") await box.fs.mkdir(`${project}/${parent}`, { recursive: true });
      await box.fs.writeFile(`${project}/${path}`, encode(text));
    }
    const watcher = new FakeDirectoryWatcher();
    const clock = new FakeClock();
    const store = createProjectStore({ fs: box.fs, root: project, watcher, clock, ...extra });
    const changes: FileChange[] = [];
    const start = async () => {
      const stop = store.watch((change) => changes.push(change));
      // A rescan waits in the same queue behind the baseline scan, so when it returns the baseline is taken and the
      // watcher is open; no fixed pause decides whether the files written next count as changes.
      await store.rescan();
      return stop;
    };
    /** An event for `path`, then the debounce period, then the time the work takes. */
    const touch = async (path: string | null) => {
      watcher.emit(path);
      clock.advance(DEBOUNCE_MS);
      await pause();
    };
    return { ...box, project, watcher, clock, store, changes, start, touch };
  }

  describe("lifecycle", () => {
    it("watches the project folder recursively, shares one watch between listeners and closes it with the last one", async () => {
      const { watcher, store, clock, project, fs } = await setup();
      const first = store.watch(() => {});
      const second = store.watch(() => {});
      await pause();
      expect(watcher.starts).toBe(1);
      expect(watcher.directories).toEqual([await fs.realpath(project)]);
      first();
      expect(watcher.active).toBe(1);
      second();
      expect(watcher.active).toBe(0);
      expect(clock.pendingTimers).toBe(0);
      second();
      expect(watcher.active).toBe(0);
    });

    it("can be started again after it was stopped", async () => {
      const { watcher, store, start } = await setup();
      const stop = await start();
      stop();
      await start();
      expect(watcher.active).toBe(1);
      expect(store.watch).toBeTypeOf("function");
    });

    it("leaves no watch and no timer behind when stopped in the middle of a pending flush", async () => {
      const { watcher, clock, changes, start, fs, project } = await setup({}, { "a.tex": "one" });
      const stop = await start();
      await fs.writeFile(`${project}/a.tex`, encode("two"));
      watcher.emit("a.tex");
      stop();
      clock.advance(DEBOUNCE_MS);
      await pause();
      expect(changes).toEqual([]);
      expect(watcher.active).toBe(0);
      expect(clock.pendingTimers).toBe(0);
    });

    it("needs a watcher and a clock, and says so", async () => {
      const box = create();
      await box.fs.mkdir(`${box.root}/project`, { recursive: true });
      const store = createProjectStore({ fs: box.fs, root: `${box.root}/project` });
      expect(() => store.watch(() => {})).toThrow("watcher and a clock");
    });
  });

  describe("reporting changes", () => {
    it("reports nothing for files that exist when watching starts", async () => {
      const { changes, start, clock } = await setup({}, { "a.tex": "one", "refs.bib": "@book{k}" });
      await start();
      clock.advance(DEBOUNCE_MS);
      await pause();
      expect(changes).toEqual([]);
    });

    it("reports a modified file once, with the hash of its new content, after the debounce period", async () => {
      const { changes, start, touch, fs, project, watcher, clock } = await setup({}, { "a.tex": "one" });
      await start();
      await fs.writeFile(`${project}/a.tex`, encode("two"));
      watcher.emit("a.tex");
      clock.advance(DEBOUNCE_MS - 1);
      await pause();
      expect(changes).toEqual([]);
      await touch("a.tex");
      await until(() => changes.length > 0);
      expect(changes).toEqual([{ path: "a.tex", hash: await hash("two") }]);
    });

    it("merges a burst of events for one file into one report", async () => {
      const { changes, start, fs, project, watcher, clock } = await setup({}, { "a.tex": "one" });
      await start();
      await fs.writeFile(`${project}/a.tex`, encode("two"));
      for (let i = 0; i < 5; i += 1) watcher.emit("a.tex");
      clock.advance(DEBOUNCE_MS);
      await until(() => changes.length > 0);
      await pause();
      expect(changes).toHaveLength(1);
    });

    it("reports nothing when an event arrives for a file whose content did not change", async () => {
      const { changes, start, touch } = await setup({}, { "a.tex": "one" });
      await start();
      await touch("a.tex");
      expect(changes).toEqual([]);
    });

    it("reports a new file with its hash and a deleted file with a null hash", async () => {
      const { changes, start, touch, fs, project } = await setup({}, { "a.tex": "one" });
      await start();
      await fs.writeFile(`${project}/new.tex`, encode("fresh"));
      await touch("new.tex");
      await until(() => changes.length === 1);
      expect(changes[0]).toEqual({ path: "new.tex", hash: await hash("fresh") });
      await fs.rm(`${project}/a.tex`);
      await touch("a.tex");
      await until(() => changes.length === 2);
      expect(changes[1]).toEqual({ path: "a.tex", hash: null });
    });

    it("reports the files of a folder that was moved in, and of one that was removed", async () => {
      const { changes, start, touch, fs, project } = await setup({}, { "old/x.tex": "x", "old/y.tex": "y" });
      await start();
      await fs.mkdir(`${project}/moved`);
      await fs.writeFile(`${project}/moved/z.tex`, encode("z"));
      await touch("moved");
      await until(() => changes.some((change) => change.path === "moved/z.tex"));
      expect(changes).toContainEqual({ path: "moved/z.tex", hash: await hash("z") });

      changes.length = 0;
      await fs.rm(`${project}/old`, { recursive: true });
      await touch("old");
      await until(() => changes.length >= 2);
      expect(changes).toEqual(expect.arrayContaining([{ path: "old/x.tex", hash: null }, { path: "old/y.tex", hash: null }]));
    });

    it("reports a file written through the store, with the hash the store returned", async () => {
      const { changes, start, touch, store } = await setup({}, { "a.tex": "one" });
      await start();
      const written = await store.write(rel("a.tex"), encode("through the store"), "any");
      if (!written.ok) throw new Error("write failed");
      await touch("a.tex");
      await until(() => changes.length > 0);
      expect(changes).toEqual([{ path: "a.tex", hash: written.value.hash }]);
    });
  });

  describe("what is never reported", () => {
    it("ignores the temporary files of atomic writes, reserved folders, folders that look like paths out of the project and bad paths", async () => {
      const { changes, start, touch, fs, project } = await setup({}, { "a.tex": "one" });
      await start();
      for (const reserved of [".caztor", ".git", ".claude", ".opencode", ".agents", "node_modules"]) {
        await fs.mkdir(`${project}/${reserved}`);
        await fs.writeFile(`${project}/${reserved}/x.txt`, encode("hidden"));
      }
      await fs.writeFile(`${project}/.caztor-tmp-123`, encode("partial"));
      for (const path of [".caztor/state.json", ".git/index", ".claude/x.txt", ".opencode/x.txt", ".agents/x.txt", "node_modules/x.txt", ".caztor-tmp-123", "sub/.caztor-tmp-9", "../outside.txt", "/etc/passwd", "a\0b", ""]) {
        await touch(path);
      }
      await pause(40);
      expect(changes).toEqual([]);
    });

    it("does not report the AGENTS.md that Caztor created, but reports one the user wrote", async () => {
      const hidden = await setup({ agentsMdCreatedByCaztor: true }, { "AGENTS.md": "one" });
      await hidden.start();
      await hidden.fs.writeFile(`${hidden.project}/AGENTS.md`, encode("two"));
      await hidden.touch("AGENTS.md");
      await pause(30);
      expect(hidden.changes).toEqual([]);

      const shown = await setup({ agentsMdCreatedByCaztor: false }, { "AGENTS.md": "one" });
      await shown.start();
      await shown.fs.writeFile(`${shown.project}/AGENTS.md`, encode("two"));
      await shown.touch("AGENTS.md");
      await until(() => shown.changes.length > 0);
      expect(shown.changes[0]?.path).toBe("AGENTS.md");
    });

    it("ignores a link, as the file listing does", async () => {
      const { changes, start, touch, symlink, project, fs } = await setup({}, { "a.tex": "one" });
      await start();
      symlink(`${project}/a.tex`, `${project}/alias.tex`);
      await touch("alias.tex");
      await pause(30);
      expect(changes).toEqual([]);
      expect((await fs.lstat(`${project}/alias.tex`)).isSymbolicLink()).toBe(true);
    });
  });

  describe("the forced rescan", () => {
    it("finds changes that no event announced when asked to rescan", async () => {
      const { changes, start, store, fs, project } = await setup({}, { "a.tex": "one", "b.tex": "two", "gone.tex": "bye" });
      await start();
      await fs.writeFile(`${project}/a.tex`, encode("one, edited"));
      await fs.writeFile(`${project}/c.tex`, encode("new"));
      await fs.rm(`${project}/gone.tex`);
      await store.rescan();
      expect(changes).toHaveLength(3);
      expect(changes).toEqual(
        expect.arrayContaining([
          { path: "a.tex", hash: await hash("one, edited") },
          { path: "c.tex", hash: await hash("new") },
          { path: "gone.tex", hash: null },
        ]),
      );
    });

    it("reports new and removed folders and reports nothing a second time", async () => {
      const { changes, start, store, fs, project } = await setup({}, { "a.tex": "one" });
      await start();
      await fs.mkdir(`${project}/figures`);
      await store.rescan();
      expect(changes).toEqual([{ path: "figures", hash: null }]);
      await store.rescan();
      expect(changes).toHaveLength(1);
      await fs.rm(`${project}/figures`, { recursive: true });
      await store.rescan();
      expect(changes).toHaveLength(2);
    });

    it("does nothing when nobody is watching", async () => {
      const { store, fs, project, changes } = await setup({}, { "a.tex": "one" });
      await fs.writeFile(`${project}/a.tex`, encode("two"));
      await expect(store.rescan()).resolves.toBeUndefined();
      expect(changes).toEqual([]);
    });

    it("runs on its own every few seconds, so a watcher that sees nothing still finds changes", async () => {
      const { changes, start, clock, fs, project } = await setup({}, { "a.tex": "one" });
      await start();
      await fs.writeFile(`${project}/a.tex`, encode("changed with no event"));
      clock.advance(RESCAN_MS - 1);
      await pause();
      expect(changes).toEqual([]);
      clock.advance(1);
      await until(() => changes.length > 0);
      expect(changes).toEqual([{ path: "a.tex", hash: await hash("changed with no event") }]);

      await fs.writeFile(`${project}/a.tex`, encode("and again"));
      clock.advance(RESCAN_MS);
      await until(() => changes.length > 1);
      expect(changes[1]?.hash).toBe(await hash("and again"));
    });

    it("rescans only every 30 seconds while the event watcher works, and every 5 seconds once it does not", async () => {
      const { watcher, changes, start, clock, fs, project } = await setup({}, { "a.tex": "one" });
      await start();
      await fs.writeFile(`${project}/a.tex`, encode("silent change"));
      clock.advance(FALLBACK_RESCAN_MS);
      await pause();
      expect(changes).toEqual([]);
      watcher.fail(new Error("inotify limit reached"));
      clock.advance(FALLBACK_RESCAN_MS);
      await until(() => changes.length > 0);
      expect(changes[0]?.path).toBe("a.tex");
      // The failed watcher was opened again by that rescan, so the long period applies once more.
      expect(watcher.active).toBe(1);
      await fs.writeFile(`${project}/a.tex`, encode("second silent change"));
      clock.advance(FALLBACK_RESCAN_MS);
      await pause();
      expect(changes).toHaveLength(1);
      clock.advance(RESCAN_MS - FALLBACK_RESCAN_MS);
      await until(() => changes.length > 1);
      expect(changes[1]?.hash).toBe(await hash("second silent change"));
    });

    it("stops rescanning when watching stops", async () => {
      const { start, clock } = await setup({}, { "a.tex": "one" });
      const stop = await start();
      stop();
      expect(clock.pendingTimers).toBe(0);
    });

    it("also runs for an event that names no file", async () => {
      const { changes, start, touch, fs, project } = await setup({}, { "a.tex": "one" });
      await start();
      await fs.writeFile(`${project}/b.tex`, encode("appeared"));
      await touch(null);
      await until(() => changes.length > 0);
      expect(changes).toEqual([{ path: "b.tex", hash: await hash("appeared") }]);
    });
  });

  describe("when the watched folder is deleted and created again", () => {
    it("arms the event watcher on the new folder and reports its files", async () => {
      const { watcher, changes, start, clock, touch, fs, project } = await setup({}, { "a.tex": "one" });
      await start();
      expect(watcher.starts).toBe(1);
      await fs.rm(project, { recursive: true });
      clock.advance(RESCAN_MS);
      await pause(30);
      await fs.mkdir(project, { recursive: true });
      await fs.writeFile(`${project}/b.tex`, encode("new project"));
      clock.advance(FALLBACK_RESCAN_MS);
      await until(() => changes.some((change) => change.path === "b.tex"));
      expect(changes).toContainEqual({ path: "a.tex", hash: null });
      expect(changes).toContainEqual({ path: "b.tex", hash: await hash("new project") });
      expect(watcher.starts).toBe(2);
      expect(watcher.active).toBe(1);

      await fs.writeFile(`${project}/b.tex`, encode("edited"));
      await touch("b.tex");
      await until(() => changes.some((change) => change.path === "b.tex" && change.hash !== null && changes.length > 2));
      expect(changes.at(-1)).toEqual({ path: "b.tex", hash: await hash("edited") });
    });
  });

  describe("when the watched folder is replaced between two scans", () => {
    it("notices the new folder at the next backstop pass, arms a new watcher and then reports edits without waiting for a scan", async () => {
      const { watcher, changes, start, clock, touch, fs, project } = await setup({}, { "a.tex": "one" });
      await start();
      expect(watcher.starts).toBe(1);
      // Replaced with no scan in between: no scan ever sees the folder missing. The new folder is made before the old
      // one is removed, so the file system cannot give it the old folder's inode back.
      await fs.mkdir(`${project}.new`, { recursive: true });
      await fs.writeFile(`${project}.new/b.tex`, encode("new project"));
      await fs.rm(project, { recursive: true });
      await fs.rename(`${project}.new`, project);
      clock.advance(RESCAN_MS);
      await until(() => watcher.starts === 2);
      await until(() => changes.some((change) => change.path === "b.tex"));
      expect(watcher.active).toBe(1);

      await fs.writeFile(`${project}/b.tex`, encode("edited by event"));
      await touch("b.tex");
      await until(() => changes.at(-1)?.hash !== undefined && changes.at(-1)?.path === "b.tex" && changes.length > 2);
      expect(changes.at(-1)).toEqual({ path: "b.tex", hash: await hash("edited by event") });
    });

    it("keeps one watcher when the folder was not replaced", async () => {
      const { watcher, start, clock, fs, project } = await setup({}, { "a.tex": "one" });
      await start();
      await fs.writeFile(`${project}/a.tex`, encode("silent change"));
      clock.advance(RESCAN_MS);
      await pause(40);
      clock.advance(RESCAN_MS);
      await pause(40);
      expect(watcher.starts).toBe(1);
      expect(watcher.active).toBe(1);
    });
  });

  describe("when the watcher is unreliable", () => {
    it("keeps working through rescans when the recursive watch cannot start", async () => {
      const { watcher, changes, start, clock, fs, project } = await setup({}, { "a.tex": "one" });
      watcher.failToStart = new Error("recursive watching is not supported here");
      await start();
      expect(watcher.active).toBe(0);
      await fs.writeFile(`${project}/a.tex`, encode("two"));
      clock.advance(FALLBACK_RESCAN_MS);
      await until(() => changes.length > 0);
      expect(changes[0]?.path).toBe("a.tex");
    });

    it("keeps working through rescans after the watcher reports an error", async () => {
      const { watcher, changes, start, clock, fs, project } = await setup({}, { "a.tex": "one" });
      await start();
      watcher.fail(new Error("inotify limit reached"));
      await fs.writeFile(`${project}/a.tex`, encode("two"));
      clock.advance(FALLBACK_RESCAN_MS);
      await until(() => changes.length > 0);
      expect(changes[0]?.path).toBe("a.tex");
    });

    it("opens the watcher again at once after an error, so the next edit is seen without waiting for a rescan", async () => {
      const { watcher, changes, start, touch, fs, project } = await setup({}, { "a.tex": "one" });
      await start();
      expect(watcher.starts).toBe(1);

      watcher.fail(new Error("the watched folder was replaced"));
      await until(() => watcher.starts === 2);
      await fs.writeFile(`${project}/a.tex`, encode("edited outside"));
      await touch("a.tex");

      await until(() => changes.length > 0);
      expect(changes).toEqual([{ path: "a.tex", hash: await hash("edited outside") }]);
    });

    it("does not let a failing listener stop the others or the watch", async () => {
      const { watcher, store, clock, fs, project } = await setup({}, { "a.tex": "one" });
      const seen: string[] = [];
      store.watch(() => {
        throw new Error("listener failure");
      });
      store.watch((change) => seen.push(change.path));
      await pause();
      await fs.writeFile(`${project}/a.tex`, encode("two"));
      watcher.emit("a.tex");
      clock.advance(DEBOUNCE_MS);
      await until(() => seen.length > 0);
      expect(seen).toEqual(["a.tex"]);
    });
  });
}, 30_000);
