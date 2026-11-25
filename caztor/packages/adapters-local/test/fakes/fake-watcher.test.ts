import { describe, expect, it } from "vitest";
import { FakeDirectoryWatcher } from "./fake-watcher.ts";

describe("FakeDirectoryWatcher", () => {
  it("delivers emitted paths to every open watch until it is closed", () => {
    const watcher = new FakeDirectoryWatcher();
    const seen: Array<string | null> = [];
    const close = watcher.watch("/p", (path) => seen.push(path), () => {});
    watcher.emit("a.tex");
    watcher.emit(null);
    close();
    watcher.emit("b.tex");
    expect(seen).toEqual(["a.tex", null]);
    expect(watcher.active).toBe(0);
  });

  it("counts open watches and starts, and reports errors to the error callback", () => {
    const watcher = new FakeDirectoryWatcher();
    const errors: string[] = [];
    watcher.watch("/p", () => {}, (error) => errors.push(error.message));
    watcher.watch("/q", () => {}, () => {});
    expect(watcher.active).toBe(2);
    expect(watcher.directories).toEqual(["/p", "/q"]);
    watcher.fail(new Error("boom"));
    expect(errors).toEqual(["boom"]);
    expect(watcher.starts).toBe(2);
  });

  it("can fail to start once, like a file system without recursive watching", () => {
    const watcher = new FakeDirectoryWatcher();
    watcher.failToStart = new Error("ERR_FEATURE_UNAVAILABLE_ON_PLATFORM");
    expect(() => watcher.watch("/p", () => {}, () => {})).toThrow("ERR_FEATURE");
    expect(watcher.active).toBe(0);
    expect(() => watcher.watch("/p", () => {}, () => {})).not.toThrow();
  });
});
