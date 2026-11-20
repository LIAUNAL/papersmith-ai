import { describe, expect, it } from "vitest";
import { DEFAULT_LAYOUT } from "./panes.ts";
import { createLayoutStore, LAYOUT_KEY, type StorageLike } from "./storage.ts";

function memoryStorage(initial: Record<string, string> = {}): StorageLike & { data: Record<string, string> } {
  const data = { ...initial };
  return {
    data,
    getItem: (key) => data[key] ?? null,
    setItem: (key, value) => void (data[key] = value),
  };
}

const saved = { files: 18, editor: 30, preview: 30, chat: 22 };

describe("layout store", () => {
  it("returns the defaults when nothing was saved", () => {
    expect(createLayoutStore(memoryStorage()).load()).toEqual(DEFAULT_LAYOUT);
  });

  it("restores what was saved", () => {
    const storage = memoryStorage();
    const store = createLayoutStore(storage);
    store.save(saved);
    expect(JSON.parse(storage.data[LAYOUT_KEY] ?? "null")).toEqual(saved);
    expect(createLayoutStore(storage).load()).toEqual(saved);
  });

  it.each([
    ["unparseable text", "{not json"],
    ["an empty string", ""],
    ["a wrong shape", JSON.stringify([1, 2, 3, 4])],
    ["a zero-sized pane", JSON.stringify({ files: 0, editor: 40, preview: 38, chat: 22 })],
  ])("falls back to the defaults for %s without throwing", (_label, text) => {
    expect(createLayoutStore(memoryStorage({ [LAYOUT_KEY]: text })).load()).toEqual(DEFAULT_LAYOUT);
  });

  it("falls back to the defaults when the browser refuses storage access", () => {
    const blocked: StorageLike = {
      getItem: () => {
        throw new DOMException("denied", "SecurityError");
      },
      setItem: () => {
        throw new DOMException("quota", "QuotaExceededError");
      },
    };
    const store = createLayoutStore(blocked);
    expect(store.load()).toEqual(DEFAULT_LAYOUT);
    expect(() => store.save(saved)).not.toThrow();
  });

  it("works without any storage", () => {
    const store = createLayoutStore(null);
    expect(store.load()).toEqual(DEFAULT_LAYOUT);
    expect(() => store.save(saved)).not.toThrow();
  });

  it("keeps a layout with a narrow pane, so a layout saved on a wide window survives a narrower one", () => {
    const storage = memoryStorage();
    const narrow = { files: 4, editor: 40, preview: 34, chat: 22 };
    createLayoutStore(storage).save(narrow);
    expect(createLayoutStore(storage).load()).toEqual(narrow);
  });

  it("does not save a layout that would be discarded on the next load", () => {
    const storage = memoryStorage();
    createLayoutStore(storage).save({ files: 1, editor: 1, preview: 1, chat: 1 });
    expect(storage.data[LAYOUT_KEY]).toBeUndefined();
  });
});
