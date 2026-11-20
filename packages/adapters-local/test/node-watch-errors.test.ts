import { EventEmitter } from "node:events";
import { afterEach, describe, expect, it, vi } from "vitest";

/** The `fs.watch` handles the code under test opens, by folder path. */
const handles = new Map<string, EventEmitter & { close: () => void }>();
let failOpening: string | null = null;

vi.mock("node:fs", async (importOriginal) => {
  const real = await importOriginal<typeof import("node:fs")>();
  return {
    ...real,
    watch: (path: string) => {
      if (failOpening !== null && path.endsWith(failOpening)) throw Object.assign(new Error("EMFILE: too many open files"), { code: "EMFILE" });
      const handle = Object.assign(new EventEmitter(), { close: () => handles.delete(path) });
      handles.set(path, handle);
      return handle;
    },
  };
});

const { mkdtempSync, mkdirSync, rmSync } = await import("node:fs");
const { tmpdir } = await import("node:os");
const { join } = await import("node:path");
const { nodeDirectoryWatcher } = await import("../src/node-infra.ts");

const roots: string[] = [];
function project(...folders: string[]): string {
  const root = mkdtempSync(join(tmpdir(), "caztor-watch-errors-"));
  roots.push(root);
  for (const folder of folders) mkdirSync(join(root, folder), { recursive: true });
  return root;
}

afterEach(() => {
  failOpening = null;
  handles.clear();
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

describe("nodeDirectoryWatcher failures below the project folder", () => {
  it("reports an error when the watch of a sub-folder fails while running, so the caller falls back to rescans and opens a new watcher", () => {
    const root = project("chapters");
    const errors: Error[] = [];
    const close = nodeDirectoryWatcher.watch(root, () => {}, (error) => errors.push(error));
    handles.get(join(root, "chapters"))!.emit("error", new Error("inotify limit reached"));
    expect(errors.map((error) => error.message)).toEqual(["inotify limit reached"]);
    close();
  });

  it("reports an error when a sub-folder cannot be watched at all", () => {
    const root = project("chapters", "figures");
    failOpening = "figures";
    const errors: Error[] = [];
    const close = nodeDirectoryWatcher.watch(root, () => {}, (error) => errors.push(error));
    expect(errors.map((error) => error.message)).toEqual(["EMFILE: too many open files"]);
    close();
  });

  it("does not report a sub-folder that vanished while it was being watched", () => {
    const root = project("chapters");
    const errors: Error[] = [];
    const close = nodeDirectoryWatcher.watch(root, () => {}, (error) => errors.push(error));
    handles.get(join(root, "chapters"))!.emit("error", Object.assign(new Error("ENOENT: gone"), { code: "ENOENT" }));
    expect(errors).toEqual([]);
    close();
  });
});
