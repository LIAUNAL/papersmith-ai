import { describe, expect, it } from "vitest";
import { GUIDES_DIR, isGuideName, isGuideTarget } from "../src/agent-targets.ts";
import { guideSetProblem, withFallback } from "../src/guide-source.ts";
import type { GuideDocument, GuideSourcePort, Result } from "../src/ports.ts";

const doc = (name: string, text = name): GuideDocument => ({ name, bytes: new TextEncoder().encode(text) });
const SET = [doc("INDEX.md"), doc("01-materials-and-methods.md"), doc("LICENSE-papersmith-ai.txt")];

function source(result: Result<readonly GuideDocument[], { message: string }>, calls: string[] = [], label = "source"): GuideSourcePort {
  return {
    async load() {
      calls.push(label);
      return result;
    },
  };
}
const ok = (docs: readonly GuideDocument[]): Result<readonly GuideDocument[], { message: string }> => ({ ok: true, value: docs });
const fail = (message: string): Result<readonly GuideDocument[], { message: string }> => ({ ok: false, error: { message } });

describe("guide names", () => {
  it("lives under the internal state folder", () => {
    expect(GUIDES_DIR).toBe(".caztor/guides");
  });

  it("accepts the index, the license copy and numbered guides", () => {
    for (const name of ["INDEX.md", "LICENSE-papersmith-ai.txt", "01-materials-and-methods.md", "10-back-matter.md", "08-abstract.md"]) {
      expect(isGuideName(name), name).toBe(true);
    }
  });

  it("refuses anything that could leave the folder or is not a guide", () => {
    for (const name of ["../INDEX.md", "a/INDEX.md", "index.md", "1-intro.md", "01-Intro.md", "01-intro.txt", "01--x.md", "01-x-.md", ".md", "", "INDEX.md ", "LICENSE.txt", "state.json", "01-intro.md/", "..", "01-intro.md\u0000"]) {
      expect(isGuideName(name), JSON.stringify(name)).toBe(false);
    }
  });
});

describe("guide targets", () => {
  it("are the guide names inside the guides folder, and nothing else", () => {
    expect(isGuideTarget(".caztor/guides/INDEX.md")).toBe(true);
    expect(isGuideTarget(".caztor/guides/05-related-work.md")).toBe(true);
    for (const path of [".caztor/guides/notes.md", ".caztor/guides/a/INDEX.md", ".caztor/guides/../INDEX.md", ".caztor/INDEX.md", "guides/INDEX.md", ".caztor/guides", ".caztor/guides/"]) {
      expect(isGuideTarget(path), path).toBe(false);
    }
  });
});

describe("guideSetProblem", () => {
  it("accepts a set with an index and valid names", () => {
    expect(guideSetProblem(SET)).toBeNull();
  });

  it("names an invalid file name", () => {
    expect(guideSetProblem([...SET, doc("../escape.md")])).toBe('"../escape.md" is not a valid guide name');
  });

  it("requires INDEX.md", () => {
    expect(guideSetProblem([doc("01-materials-and-methods.md")])).toBe("INDEX.md is missing");
  });

  it("refuses a repeated name", () => {
    expect(guideSetProblem([...SET, doc("INDEX.md")])).toBe('"INDEX.md" appears twice');
  });
});

describe("withFallback", () => {
  it("uses the primary source when it works, and does not read the fallback", async () => {
    const calls: string[] = [];
    const primary = [doc("INDEX.md", "primary"), doc("01-a.md")];
    const result = await withFallback(source(ok(primary), calls, "primary"), source(ok(SET), calls, "fallback")).load();
    expect(result).toEqual({ ok: true, value: primary });
    expect(calls).toEqual(["primary"]);
  });

  it("falls back when the primary source reports an error", async () => {
    const calls: string[] = [];
    const result = await withFallback(source(fail("offline"), calls, "primary"), source(ok(SET), calls, "fallback")).load();
    expect(result).toEqual({ ok: true, value: SET });
    expect(calls).toEqual(["primary", "fallback"]);
  });

  it("falls back when the primary source throws", async () => {
    const throwing: GuideSourcePort = {
      async load() {
        throw new Error("boom");
      },
    };
    expect(await withFallback(throwing, source(ok(SET))).load()).toEqual({ ok: true, value: SET });
  });

  it("falls back when the primary source returns a set without an index", async () => {
    const result = await withFallback(source(ok([doc("01-a.md")])), source(ok(SET))).load();
    expect(result).toEqual({ ok: true, value: SET });
  });

  it("reports both reasons when neither source works", async () => {
    const result = await withFallback(source(fail("offline")), source(fail("folder missing"))).load();
    expect(result).toEqual({ ok: false, error: { message: "folder missing (the configured source also failed: offline)" } });
  });

  it("reports the fallback's own error when the primary source is not a failure", async () => {
    const result = await withFallback(source(ok([])), source(fail("folder missing"))).load();
    expect(result.ok).toBe(false);
    expect(!result.ok && result.error.message).toContain("folder missing");
    expect(!result.ok && result.error.message).toContain("INDEX.md is missing");
  });
});
