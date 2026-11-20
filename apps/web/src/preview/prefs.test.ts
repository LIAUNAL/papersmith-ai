import { describe, expect, it } from "vitest";
import { createPrefsStore, DEFAULT_PREFS, parsePrefs } from "./prefs.ts";

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (key: string) => data[key] ?? null,
    setItem: (key: string, value: string) => void (data[key] = value),
  };
}

describe("parsePrefs", () => {
  it("accepts a percentage zoom or fit, with an anchor", () => {
    expect(parsePrefs({ zoom: { mode: "percent", percent: 150 }, anchor: { page: 2, offset: 0.4 } })).toEqual({
      zoom: { mode: "percent", percent: 150 },
      anchor: { page: 2, offset: 0.4 },
    });
    expect(parsePrefs({ zoom: { mode: "fit" }, anchor: { page: 0, offset: 0 } })).toEqual({ zoom: { mode: "fit" }, anchor: { page: 0, offset: 0 } });
  });

  it.each([
    ["null", null],
    ["a string", "x"],
    ["no zoom", { anchor: { page: 0, offset: 0 } }],
    ["unknown mode", { zoom: { mode: "huge" }, anchor: { page: 0, offset: 0 } }],
    ["percent not a number", { zoom: { mode: "percent", percent: "150" }, anchor: { page: 0, offset: 0 } }],
    ["negative page", { zoom: { mode: "fit" }, anchor: { page: -1, offset: 0 } }],
    ["fractional page", { zoom: { mode: "fit" }, anchor: { page: 1.5, offset: 0 } }],
    ["offset above 1", { zoom: { mode: "fit" }, anchor: { page: 0, offset: 2 } }],
    ["non-finite offset", { zoom: { mode: "fit" }, anchor: { page: 0, offset: Number.NaN } }],
  ])("rejects %s", (_name, value) => {
    expect(parsePrefs(value)).toBeNull();
  });

  it("clamps an out-of-range percentage instead of rejecting it", () => {
    expect(parsePrefs({ zoom: { mode: "percent", percent: 9000 }, anchor: { page: 0, offset: 0 } })?.zoom).toEqual({ mode: "percent", percent: 400 });
  });
});

describe("createPrefsStore", () => {
  it("returns the defaults when nothing is saved", () => {
    expect(createPrefsStore(memoryStorage(), "thesis").load()).toEqual(DEFAULT_PREFS);
  });

  it("saves and restores per project", () => {
    const storage = memoryStorage();
    createPrefsStore(storage, "thesis").save({ zoom: { mode: "percent", percent: 150 }, anchor: { page: 2, offset: 0.5 } });
    expect(createPrefsStore(storage, "thesis").load()).toEqual({ zoom: { mode: "percent", percent: 150 }, anchor: { page: 2, offset: 0.5 } });
    expect(createPrefsStore(storage, "other").load()).toEqual(DEFAULT_PREFS);
  });

  it("keeps projects whose names look alike apart", () => {
    const storage = memoryStorage();
    createPrefsStore(storage, "a b").save({ zoom: { mode: "fit" }, anchor: { page: 4, offset: 0 } });
    expect(createPrefsStore(storage, "a%20b").load()).toEqual(DEFAULT_PREFS);
  });

  it("falls back to the defaults for unreadable data and survives a storage that throws", () => {
    const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("full"); } };
    expect(createPrefsStore(broken, "thesis").load()).toEqual(DEFAULT_PREFS);
    expect(() => createPrefsStore(broken, "thesis").save(DEFAULT_PREFS)).not.toThrow();
    const garbage = memoryStorage();
    garbage.setItem("caztor.preview.v1.thesis", "{not json");
    expect(createPrefsStore(garbage, "thesis").load()).toEqual(DEFAULT_PREFS);
    expect(createPrefsStore(null, "thesis").load()).toEqual(DEFAULT_PREFS);
  });

  it("does not save invalid preferences", () => {
    const storage = memoryStorage();
    createPrefsStore(storage, "thesis").save({ zoom: { mode: "fit" }, anchor: { page: -3, offset: 0 } });
    expect(storage.data).toEqual({});
  });
});
