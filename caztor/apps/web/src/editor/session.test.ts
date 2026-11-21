import type { RelPath } from "@caztor/core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiError, createFakeApi } from "../testing/fake-api.ts";
import { AUTOSAVE_MS, EditorSession } from "./session.ts";

const file = (path: string, size = 5) => ({ path: path as RelPath, kind: "file" as const, size });

function setup() {
  const fake = createFakeApi({
    files: [file("main.tex"), file("refs.bib")],
    contents: { "main.tex": "hello", "refs.bib": "@book{k}" },
  });
  const session = new EditorSession({ api: fake.api });
  const open = async (path: string) => {
    session.open(await fake.api.readFile(path));
  };
  const writes = () => fake.calls.filter((call) => call.startsWith("writeFile"));
  return { fake, session, open, writes };
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("EditorSession opening and editing", () => {
  it("opens a file as a saved buffer holding the text and the hash it was read with", async () => {
    const { session, open } = setup();
    await open("main.tex");
    expect(session.get("main.tex")).toMatchObject({ path: "main.tex", text: "hello", status: "saved", baseHash: "sha256:main.tex#0", error: null });
    expect(session.get("other.tex")).toBeUndefined();
  });

  it("marks a buffer dirty on the first edit and sends nothing before the idle period ends", async () => {
    const { session, open, writes } = setup();
    await open("main.tex");
    session.edit("main.tex", "hello world");
    expect(session.get("main.tex")).toMatchObject({ text: "hello world", status: "dirty" });
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS - 1);
    expect(writes()).toEqual([]);
  });

  it("saves after 800 ms of idle with the base hash, then returns to saved with the new hash", async () => {
    const { fake, session, open, writes } = setup();
    expect(AUTOSAVE_MS).toBe(800);
    await open("main.tex");
    session.edit("main.tex", "hello world");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(writes()).toEqual(["writeFile main.tex sha256:main.tex#0"]);
    expect(session.get("main.tex")).toMatchObject({ status: "saved", baseHash: "sha256:main.tex#1" });
    expect(fake.disk("main.tex")?.content).toBe("hello world");

    session.edit("main.tex", "hello world!");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(writes()[1]).toBe("writeFile main.tex sha256:main.tex#1");
    expect(session.get("main.tex")?.status).toBe("saved");
  });

  it("restarts the idle period on every edit", async () => {
    const { session, open, writes } = setup();
    await open("main.tex");
    session.edit("main.tex", "a");
    await vi.advanceTimersByTimeAsync(500);
    session.edit("main.tex", "ab");
    await vi.advanceTimersByTimeAsync(799);
    expect(writes()).toEqual([]);
    await vi.advanceTimersByTimeAsync(1);
    expect(writes()).toHaveLength(1);
  });

  it("shows the saving state while the request is in flight", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => (release = resolve));
    const write = fake.api.writeFile.bind(fake.api);
    fake.api.writeFile = async (...args) => (await gate, write(...args));
    session.edit("main.tex", "slow");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(session.get("main.tex")?.status).toBe("saving");
    release();
    await vi.advanceTimersByTimeAsync(0);
    expect(session.get("main.tex")?.status).toBe("saved");
  });

  it("returns to saved without a request when the text is edited back to what is on disk", async () => {
    const { session, open, writes } = setup();
    await open("main.tex");
    session.edit("main.tex", "hello!");
    session.edit("main.tex", "hello");
    expect(session.get("main.tex")?.status).toBe("saved");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS * 2);
    expect(writes()).toEqual([]);
  });

  it("keeps edits made while a save is in flight and saves them next", async () => {
    const { fake, session, open, writes } = setup();
    await open("main.tex");
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => (release = resolve));
    const write = fake.api.writeFile.bind(fake.api);
    fake.api.writeFile = async (...args) => (await gate, write(...args));
    session.edit("main.tex", "first");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    session.edit("main.tex", "first, then more");
    release();
    await vi.advanceTimersByTimeAsync(0);
    expect(session.get("main.tex")).toMatchObject({ text: "first, then more", status: "dirty", baseHash: "sha256:main.tex#1" });
    fake.api.writeFile = write;
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(fake.disk("main.tex")?.content).toBe("first, then more");
    expect(session.get("main.tex")?.status).toBe("saved");
    expect(writes()).toHaveLength(2);
  });

  it("ignores edits and saves for a file that is not open", async () => {
    const { session, writes } = setup();
    session.edit("nowhere.tex", "x");
    await session.saveNow("nowhere.tex");
    expect(writes()).toEqual([]);
  });
});

describe("EditorSession failures", () => {
  it("enters the conflict state on a 409, keeps the text and stops autosaving", async () => {
    const { fake, session, open, writes } = setup();
    await open("main.tex");
    fake.changeOnDisk("main.tex", "changed elsewhere");
    session.edit("main.tex", "my edit");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(session.get("main.tex")).toMatchObject({ status: "conflict", text: "my edit" });
    expect(fake.disk("main.tex")?.content).toBe("changed elsewhere");

    session.edit("main.tex", "my edit, more");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS * 5);
    expect(writes()).toHaveLength(1);
    expect(session.get("main.tex")).toMatchObject({ status: "conflict", text: "my edit, more" });
  });

  it("keeps the buffer dirty with an error for any other failure, without losing text", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    fake.failNext(apiError("io", "The file could not be written.", 500, "main.tex"));
    session.edit("main.tex", "precious");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(session.get("main.tex")).toMatchObject({ status: "error", text: "precious", error: "The file could not be written." });
  });

  it("retries on the next edit after an error and clears it once saved", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    fake.failNext(apiError("network", "Cannot reach the Caztor server.", 0));
    session.edit("main.tex", "one");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(session.get("main.tex")?.status).toBe("error");
    session.edit("main.tex", "one two");
    expect(session.get("main.tex")).toMatchObject({ status: "dirty", error: null });
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(session.get("main.tex")).toMatchObject({ status: "saved", error: null });
    expect(fake.disk("main.tex")?.content).toBe("one two");
  });

  it("retries at once when asked to save now after an error", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    fake.failNext(apiError("io", "No space left.", 500));
    session.edit("main.tex", "keep me");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    await session.saveNow("main.tex");
    expect(session.get("main.tex")?.status).toBe("saved");
    expect(fake.disk("main.tex")?.content).toBe("keep me");
  });
});

describe("EditorSession several files", () => {
  it("keeps the unsaved edits of a file when another one is opened, and still saves them", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    session.edit("main.tex", "draft");
    await open("refs.bib");
    session.setActive("refs.bib");
    expect(session.get("main.tex")).toMatchObject({ text: "draft", status: "dirty" });
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(fake.disk("main.tex")?.content).toBe("draft");
  });

  it("returns the kept text, not the disk text, when a dirty file is opened again", async () => {
    const { session, open } = setup();
    await open("main.tex");
    session.setActive("main.tex");
    session.edit("main.tex", "draft");
    await open("refs.bib");
    session.setActive("refs.bib");
    await open("main.tex");
    expect(session.get("main.tex")?.text).toBe("draft");
  });

  it("lets go of a clean buffer when another file becomes active", async () => {
    const { session, open } = setup();
    await open("main.tex");
    session.setActive("main.tex");
    await open("refs.bib");
    session.setActive("refs.bib");
    expect(session.get("main.tex")).toBeUndefined();
    expect(session.get("refs.bib")).toBeDefined();
  });

  it("saves every dirty buffer at once on flushAll", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    await open("refs.bib");
    session.edit("main.tex", "A");
    session.edit("refs.bib", "B");
    await session.flushAll();
    expect([fake.disk("main.tex")?.content, fake.disk("refs.bib")?.content]).toEqual(["A", "B"]);
    expect(session.get("main.tex")?.status).toBe("saved");
  });

  it("moves a buffer to a new path when its file is renamed and drops one that was deleted", async () => {
    const { session, open } = setup();
    await open("main.tex");
    await open("refs.bib");
    session.edit("main.tex", "draft");
    session.rename("main.tex", "thesis.tex");
    expect(session.get("main.tex")).toBeUndefined();
    expect(session.get("thesis.tex")).toMatchObject({ text: "draft", status: "dirty" });
    session.forget("refs.bib");
    expect(session.get("refs.bib")).toBeUndefined();
  });

  it("renames the buffers inside a renamed folder", async () => {
    const fake = createFakeApi({ files: [file("chapters/a.tex")], contents: { "chapters/a.tex": "x" } });
    const session = new EditorSession({ api: fake.api });
    session.open(await fake.api.readFile("chapters/a.tex"));
    session.rename("chapters", "parts");
    expect(session.get("parts/a.tex")).toBeDefined();
    expect(session.get("chapters/a.tex")).toBeUndefined();
  });
});

describe("EditorSession subscription", () => {
  it("notifies listeners and hands out a new snapshot on every change, and stops after unsubscribe", async () => {
    const { session, open } = setup();
    const listener = vi.fn();
    const stop = session.subscribe(listener);
    const first = session.getSnapshot();
    await open("main.tex");
    session.edit("main.tex", "x");
    expect(listener).toHaveBeenCalledTimes(2);
    expect(session.getSnapshot()).not.toBe(first);
    expect(session.getSnapshot()).toBe(session.getSnapshot());
    stop();
    session.edit("main.tex", "xy");
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("stops its timers when disposed", async () => {
    const { session, open, writes } = setup();
    await open("main.tex");
    session.edit("main.tex", "x");
    session.dispose();
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS * 2);
    expect(writes()).toEqual([]);
  });
});

describe("EditorSession saved notifications", () => {
  it("tells listeners the path of each file that was saved, once per save", async () => {
    const { session, open } = setup();
    const saved: string[] = [];
    session.onSaved((path) => saved.push(path));
    await open("main.tex");
    await open("refs.bib");
    session.edit("main.tex", "hello world");
    session.edit("refs.bib", "@book{other}");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(saved.sort()).toEqual(["main.tex", "refs.bib"]);
  });

  it("says nothing when the save failed or hit a conflict, and stops after unsubscribing", async () => {
    const { fake, session, open } = setup();
    const saved: string[] = [];
    const stop = session.onSaved((path) => saved.push(path));
    await open("main.tex");
    session.edit("main.tex", "a");
    fake.failNext(apiError("io", "The disk is full.", 500));
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(session.get("main.tex")?.status).toBe("error");
    fake.changeOnDisk("main.tex", "theirs");
    await session.saveNow("main.tex");
    expect(session.get("main.tex")?.status).toBe("conflict");
    expect(saved).toEqual([]);

    await session.takeDisk("main.tex");
    stop();
    session.edit("main.tex", "after");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(fake.disk("main.tex")?.content).toBe("after");
    expect(saved).toEqual([]);
  });
});

describe("EditorSession reveal", () => {
  it("publishes a jump with the path, the line and a new id for every request", async () => {
    const { session, open } = setup();
    await open("main.tex");
    expect(session.getSnapshot().jump).toBeNull();
    session.reveal("main.tex", 7);
    const first = session.getSnapshot().jump;
    expect(first).toMatchObject({ path: "main.tex", line: 7 });
    session.reveal("main.tex", 7);
    const second = session.getSnapshot().jump;
    expect(second).toMatchObject({ path: "main.tex", line: 7 });
    expect(second!.id).toBeGreaterThan(first!.id);
  });

  it("carries the word to select when one is given, and none otherwise", async () => {
    const { session, open } = setup();
    await open("main.tex");
    session.reveal("main.tex", 3, { column: 12, length: 8 });
    expect(session.getSnapshot().jump).toMatchObject({ path: "main.tex", line: 3, select: { column: 12, length: 8 } });
    session.reveal("main.tex", 4);
    expect(session.getSnapshot().jump).not.toHaveProperty("select");
  });

  it("tells subscribers about the jump", async () => {
    const { session } = setup();
    let notified = 0;
    session.subscribe(() => (notified += 1));
    session.reveal("refs.bib", 2);
    expect(notified).toBe(1);
  });
});
