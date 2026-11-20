import type { RelPath } from "@caztor/core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiError, createFakeApi } from "../testing/fake-api.ts";
import { AUTOSAVE_MS, copyName, EditorSession } from "./session.ts";

const file = (path: string, size = 5) => ({ path: path as RelPath, kind: "file" as const, size });

/** A project with an open, dirty `main.tex` whose disk version changed: a conflict is open. */
async function conflicted(extra: { files?: string[] } = {}) {
  const fake = createFakeApi({
    files: [file("main.tex"), ...(extra.files ?? []).map((path) => file(path))],
    contents: { "main.tex": "hello", ...Object.fromEntries((extra.files ?? []).map((path) => [path, "x"])) },
  });
  const session = new EditorSession({ api: fake.api });
  session.open(await fake.api.readFile("main.tex"));
  session.setActive("main.tex");
  session.edit("main.tex", "my edit");
  const hash = fake.changeOnDisk("main.tex", "their edit");
  await session.handleEvent({ id: 1, event: "file_changed", data: { path: "main.tex", hash } });
  expect(session.get("main.tex")?.status).toBe("conflict");
  fake.calls.length = 0;
  return { fake, session, hash };
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("copyName", () => {
  it("adds -copy before the extension, then a number", () => {
    expect(copyName("main.tex", 1)).toBe("main-copy.tex");
    expect(copyName("main.tex", 2)).toBe("main-copy-2.tex");
    expect(copyName("chapters/intro.tex", 3)).toBe("chapters/intro-copy-3.tex");
  });

  it("handles names without an extension, dotfiles and dots in folder names", () => {
    expect(copyName("Makefile", 1)).toBe("Makefile-copy");
    expect(copyName(".hidden", 1)).toBe(".hidden-copy");
    expect(copyName("v1.2/notes", 1)).toBe("v1.2/notes-copy");
    expect(copyName("archive.tar.gz", 1)).toBe("archive.tar-copy.gz");
  });
});

describe("resolving a conflict: keep mine", () => {
  it("saves the user's text over the disk version and returns to saved", async () => {
    const { fake, session, hash } = await conflicted();
    await session.keepMine("main.tex");
    expect(fake.calls).toContain(`writeFile main.tex ${hash}`);
    expect(fake.disk("main.tex")?.content).toBe("my edit");
    expect(session.get("main.tex")).toMatchObject({ status: "saved", text: "my edit", conflict: null });
  });

  it("goes back to the conflict state, with the new disk version, when the file changed again meanwhile", async () => {
    const { fake, session } = await conflicted();
    const write = fake.api.writeFile.bind(fake.api);
    fake.api.writeFile = async (...args) => {
      fake.changeOnDisk("main.tex", "changed yet again");
      fake.api.writeFile = write;
      return write(...args);
    };
    await session.keepMine("main.tex");
    await vi.advanceTimersByTimeAsync(0);
    expect(session.get("main.tex")).toMatchObject({ status: "conflict", text: "my edit", conflict: { disk: { text: "changed yet again" } } });
  });

  it("creates the file again when it was deleted on disk", async () => {
    const { fake, session } = await conflicted();
    fake.removeFromDisk("main.tex");
    await session.handleEvent({ id: 2, event: "file_changed", data: { path: "main.tex", hash: null } });
    expect(session.get("main.tex")?.conflict).toMatchObject({ deleted: true });
    fake.calls.length = 0;
    await session.keepMine("main.tex");
    expect(fake.calls).toContain("writeFile main.tex null");
    expect(fake.disk("main.tex")?.content).toBe("my edit");
    expect(session.get("main.tex")?.status).toBe("saved");
  });

  it("sends the latest text when the user typed more during the conflict", async () => {
    const { fake, session } = await conflicted();
    session.edit("main.tex", "my edit and then more");
    expect(session.get("main.tex")?.status).toBe("conflict");
    await session.keepMine("main.tex");
    expect(fake.disk("main.tex")?.content).toBe("my edit and then more");
    expect(session.get("main.tex")).toMatchObject({ status: "saved", text: "my edit and then more" });
  });

  it("resumes autosave afterwards", async () => {
    const { fake, session } = await conflicted();
    await session.keepMine("main.tex");
    session.edit("main.tex", "my edit and more");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(fake.disk("main.tex")?.content).toBe("my edit and more");
  });

  it("does nothing for a buffer that is not in conflict", async () => {
    const { fake, session } = await conflicted();
    await session.keepMine("main.tex");
    fake.calls.length = 0;
    await session.keepMine("main.tex");
    await session.takeDisk("main.tex");
    expect(fake.calls).toEqual([]);
  });
});

/** A save that fails with 409 and whose follow-up read of the disk fails too: the conflict has no disk version yet. */
async function conflictWithoutDiskVersion() {
  const fake = createFakeApi({ files: [file("main.tex")], contents: { "main.tex": "hello" } });
  const session = new EditorSession({ api: fake.api });
  session.open(await fake.api.readFile("main.tex"));
  session.setActive("main.tex");
  session.edit("main.tex", "my edit");
  fake.changeOnDisk("main.tex", "their edit");
  const read = fake.api.readFile.bind(fake.api);
  fake.api.readFile = async () => {
    throw apiError("io", "The disk could not be read.", 500);
  };
  await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
  expect(session.get("main.tex")).toMatchObject({ status: "conflict", conflict: { disk: null, deleted: false } });
  fake.calls.length = 0;
  return { fake, session, restore: () => void (fake.api.readFile = read) };
}

describe("resolving a conflict when the disk version cannot be read", () => {
  it("keep mine reports the problem, writes nothing and stays in conflict", async () => {
    const { fake, session } = await conflictWithoutDiskVersion();
    await session.keepMine("main.tex");
    expect(fake.calls.filter((call) => call.startsWith("writeFile"))).toEqual([]);
    expect(session.get("main.tex")).toMatchObject({ status: "conflict", text: "my edit", conflict: { problem: "The disk could not be read." } });
  });

  it("load the disk version reports the problem, keeps the user's text and stays in conflict", async () => {
    const { session } = await conflictWithoutDiskVersion();
    await session.takeDisk("main.tex");
    expect(session.get("main.tex")).toMatchObject({ status: "conflict", text: "my edit", conflict: { problem: "The disk could not be read." } });
  });

  it("works once the disk can be read again", async () => {
    const { fake, session, restore } = await conflictWithoutDiskVersion();
    await session.keepMine("main.tex");
    restore();
    await session.keepMine("main.tex");
    expect(fake.disk("main.tex")?.content).toBe("my edit");
    expect(session.get("main.tex")).toMatchObject({ status: "saved", conflict: null });
  });
});

describe("resolving a conflict: load the disk version", () => {
  it("replaces the user's text with the disk text and returns to saved", async () => {
    const { fake, session, hash } = await conflicted();
    await session.takeDisk("main.tex");
    expect(session.get("main.tex")).toMatchObject({ status: "saved", text: "their edit", baseHash: hash, conflict: null });
    expect(fake.calls.filter((call) => call.startsWith("writeFile"))).toEqual([]);
  });

  it("resumes autosave on top of the loaded version", async () => {
    const { fake, session } = await conflicted();
    await session.takeDisk("main.tex");
    session.edit("main.tex", "their edit plus mine");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    expect(fake.disk("main.tex")?.content).toBe("their edit plus mine");
  });

  it("closes the buffer when the file was deleted on disk", async () => {
    const { fake, session } = await conflicted();
    fake.removeFromDisk("main.tex");
    await session.handleEvent({ id: 2, event: "file_changed", data: { path: "main.tex", hash: null } });
    await session.takeDisk("main.tex");
    expect(session.get("main.tex")).toBeUndefined();
  });
});

describe("resolving a conflict: save a copy", () => {
  it("writes the user's text to a new file next to the original and stays in conflict", async () => {
    const { fake, session } = await conflicted();
    expect(await session.saveCopy("main.tex")).toBe("main-copy.tex");
    expect(fake.disk("main-copy.tex")?.content).toBe("my edit");
    expect(fake.disk("main.tex")?.content).toBe("their edit");
    expect(session.get("main.tex")).toMatchObject({ status: "conflict", text: "my edit", conflict: { copiedTo: "main-copy.tex", problem: null } });
  });

  it("picks the next free name when the copy name is taken", async () => {
    const { fake, session } = await conflicted({ files: ["main-copy.tex", "main-copy-2.tex"] });
    expect(await session.saveCopy("main.tex")).toBe("main-copy-3.tex");
    expect(fake.disk("main-copy.tex")?.content).toBe("x");
  });

  it("gives up with a message when every candidate name is taken", async () => {
    const taken = ["main-copy.tex", ...Array.from({ length: 49 }, (_, index) => `main-copy-${index + 2}.tex`)];
    const { fake, session } = await conflicted({ files: taken });
    expect(await session.saveCopy("main.tex")).toBeNull();
    expect(fake.calls.filter((call) => call.startsWith("writeFile"))).toHaveLength(50);
    expect(session.get("main.tex")).toMatchObject({ status: "conflict", text: "my edit", conflict: { copiedTo: null, problem: "No free name was found for a copy." } });
  });

  it("does nothing outside a conflict", async () => {
    const fake = createFakeApi({ files: [file("main.tex")], contents: { "main.tex": "hello" } });
    const session = new EditorSession({ api: fake.api });
    session.open(await fake.api.readFile("main.tex"));
    session.edit("main.tex", "dirty");
    fake.calls.length = 0;
    expect(await session.saveCopy("main.tex")).toBeNull();
    expect(await session.saveCopy("missing.tex")).toBeNull();
    expect(fake.calls).toEqual([]);
  });

  it("reports a failure without losing the text or the conflict", async () => {
    const { fake, session } = await conflicted();
    fake.failNext(apiError("io", "The disk is full.", 500));
    expect(await session.saveCopy("main.tex")).toBeNull();
    expect(session.get("main.tex")).toMatchObject({ status: "conflict", text: "my edit", conflict: { copiedTo: null, problem: "The disk is full." } });
  });

  it("lets the user still pick a resolution afterwards", async () => {
    const { session } = await conflicted();
    await session.saveCopy("main.tex");
    await session.takeDisk("main.tex");
    expect(session.get("main.tex")).toMatchObject({ status: "saved", text: "their edit" });
  });
});
