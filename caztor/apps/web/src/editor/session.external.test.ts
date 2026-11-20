import type { RelPath } from "@caztor/core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ServerEvent } from "../api/types.ts";
import { createFakeApi } from "../testing/fake-api.ts";
import { AUTOSAVE_MS, EditorSession } from "./session.ts";

const file = (path: string, size = 5) => ({ path: path as RelPath, kind: "file" as const, size });
const changed = (path: string, hash: string | null): ServerEvent => ({ id: 1, event: "file_changed", data: { path, hash } });
const reads = (calls: string[]) => calls.filter((call) => call.startsWith("readFile"));

function setup() {
  const fake = createFakeApi({ files: [file("main.tex"), file("refs.bib")], contents: { "main.tex": "hello", "refs.bib": "@book{k}" } });
  const session = new EditorSession({ api: fake.api });
  const open = async (path: string) => {
    session.open(await fake.api.readFile(path));
    session.setActive(path);
    fake.calls.length = 0;
  };
  return { fake, session, open };
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("external change to a clean buffer", () => {
  it("ignores an event whose hash is the one the buffer is based on, without reading the file", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    await session.handleEvent(changed("main.tex", "sha256:main.tex#0"));
    expect(reads(fake.calls)).toEqual([]);
    expect(session.get("main.tex")).toMatchObject({ text: "hello", status: "saved" });
  });

  it("reloads the new content, hash and a saved state when the disk changed", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    const hash = fake.changeOnDisk("main.tex", "written by the agent");
    await session.handleEvent(changed("main.tex", hash));
    expect(session.get("main.tex")).toMatchObject({ text: "written by the agent", status: "saved", baseHash: hash, conflict: null });
    // The next save is based on the reloaded hash.
    session.edit("main.tex", "written by the agent!");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(fake.disk("main.tex")?.content).toBe("written by the agent!");
  });

  it("ignores events for files that are not open and events without a usable payload", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    await session.handleEvent(changed("refs.bib", "sha256:other"));
    await session.handleEvent({ id: 2, event: "file_changed", data: null });
    await session.handleEvent({ id: 3, event: "file_changed", data: { path: 7 } });
    await session.handleEvent({ id: 4, event: "compile.finished", data: { path: "main.tex" } });
    expect(reads(fake.calls)).toEqual([]);
  });

  it("does nothing when the file read back is the version the buffer already has", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    await session.handleEvent(changed("main.tex", "sha256:something-stale"));
    expect(reads(fake.calls)).toEqual(["readFile main.tex"]);
    expect(session.get("main.tex")).toMatchObject({ text: "hello", status: "saved", baseHash: "sha256:main.tex#0" });
  });

  it("closes a clean buffer whose file was deleted on disk", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    fake.removeFromDisk("main.tex");
    await session.handleEvent(changed("main.tex", null));
    expect(session.get("main.tex")).toBeUndefined();
    expect(session.getSnapshot().active).toBeNull();
  });

  it("applies bursts of events for one file one after another and ends with the latest content", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    fake.changeOnDisk("main.tex", "v1");
    const first = session.handleEvent(changed("main.tex", "x1"));
    fake.changeOnDisk("main.tex", "v2");
    const second = session.handleEvent(changed("main.tex", "x2"));
    fake.changeOnDisk("main.tex", "v3");
    const third = session.handleEvent(changed("main.tex", "x3"));
    await Promise.all([first, second, third]);
    expect(session.get("main.tex")?.text).toBe("v3");
    expect(reads(fake.calls).length).toBeLessThanOrEqual(3);
  });

  it("checks every open buffer after the event stream reconnected, since events may have been missed", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    await open("refs.bib");
    session.open(await fake.api.readFile("main.tex"));
    fake.calls.length = 0;
    fake.changeOnDisk("main.tex", "changed while disconnected");
    await session.handleEvent({ id: null, event: "stream_resumed", data: null });
    expect(session.get("main.tex")?.text).toBe("changed while disconnected");
    expect(reads(fake.calls).sort()).toEqual(["readFile main.tex", "readFile refs.bib"]);
  });

  it("adopts the disk text when a clean file is opened again after it changed", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    fake.changeOnDisk("main.tex", "newer");
    session.open(await fake.api.readFile("main.tex"));
    expect(session.get("main.tex")).toMatchObject({ text: "newer", status: "saved" });
  });
});

describe("external change to a buffer with unsaved edits", () => {
  it("keeps the user's text, enters the conflict state with the disk version, and pauses autosave", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    session.edit("main.tex", "my edit");
    const hash = fake.changeOnDisk("main.tex", "their edit");
    await session.handleEvent(changed("main.tex", hash));
    expect(session.get("main.tex")).toMatchObject({
      text: "my edit",
      status: "conflict",
      conflict: { disk: { text: "their edit", hash }, deleted: false, copiedTo: null, problem: null },
    });
    fake.calls.length = 0;
    session.edit("main.tex", "my edit, continued");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS * 5);
    expect(fake.calls.filter((call) => call.startsWith("writeFile"))).toEqual([]);
    expect(fake.disk("main.tex")?.content).toBe("their edit");
    expect(session.get("main.tex")?.text).toBe("my edit, continued");
  });

  it("also treats a buffer whose last save failed as having unsaved edits", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    fake.failNext(new (await import("../api/client.ts")).ApiError({ status: 500, code: "io", message: "disk full" }));
    session.edit("main.tex", "unsaved");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(session.get("main.tex")?.status).toBe("error");
    const hash = fake.changeOnDisk("main.tex", "other");
    await session.handleEvent(changed("main.tex", hash));
    expect(session.get("main.tex")).toMatchObject({ status: "conflict", text: "unsaved" });
  });

  it("refreshes the disk version while a conflict is already open", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    session.edit("main.tex", "mine");
    await session.handleEvent(changed("main.tex", fake.changeOnDisk("main.tex", "first")));
    await session.handleEvent(changed("main.tex", fake.changeOnDisk("main.tex", "second")));
    expect(session.get("main.tex")?.conflict?.disk?.text).toBe("second");
  });

  it("resolves silently when the disk text turns out to equal the user's text", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    session.edit("main.tex", "same text");
    const hash = fake.changeOnDisk("main.tex", "same text");
    await session.handleEvent(changed("main.tex", hash));
    expect(session.get("main.tex")).toMatchObject({ status: "saved", conflict: null, baseHash: hash });
  });

  it("enters the conflict state with the deleted flag when the file disappeared", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    session.edit("main.tex", "still mine");
    fake.removeFromDisk("main.tex");
    await session.handleEvent(changed("main.tex", null));
    expect(session.get("main.tex")).toMatchObject({ text: "still mine", status: "conflict", conflict: { disk: null, deleted: true } });
  });

  it("does not treat its own save as a change when the echo event arrives before the save returns", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => (release = resolve));
    const write = fake.api.writeFile.bind(fake.api);
    fake.api.writeFile = async (...args) => {
      const saved = await write(...args);
      await gate;
      return saved;
    };
    session.edit("main.tex", "typed");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(session.get("main.tex")?.status).toBe("saving");
    const echo = session.handleEvent(changed("main.tex", "sha256:main.tex#1"));
    release();
    await echo;
    expect(session.get("main.tex")).toMatchObject({ status: "saved", text: "typed", conflict: null });
  });

  it("loads the disk version when a save is rejected, so both versions can be compared", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    const hash = fake.changeOnDisk("main.tex", "changed elsewhere");
    session.edit("main.tex", "my edit");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(session.get("main.tex")).toMatchObject({ status: "conflict", text: "my edit", conflict: { disk: { text: "changed elsewhere", hash } } });
  });

  it("starts in conflict when a dirty file is opened again and its disk version changed", async () => {
    const { fake, session, open } = setup();
    await open("main.tex");
    session.edit("main.tex", "draft");
    fake.changeOnDisk("main.tex", "changed");
    session.open(await fake.api.readFile("main.tex"));
    expect(session.get("main.tex")).toMatchObject({ text: "draft", status: "conflict", conflict: { disk: { text: "changed" } } });
  });
});
