import { describe, expect, it } from "vitest";
import { SHARED_CONVENTIONS, distillGuide } from "../../src/guides/distill.ts";
import { GUIDE_SOURCE_FILES, buildGuideSet, findMissingEvidence } from "../../src/guides/build-set.ts";

const COMMIT = "1f09516";
const REPOSITORY = "https://github.com/Daprosero/papersmith-ai";

function fakeSource(index: number): string {
  return `---\n{ "section": "s${index}" }\n---\n# Section ${index}\n\n**Extent** ${index} words\n\n## Disqualifiers\n\n- A weak draft ${index}.\n`;
}

function fakeSources(): Record<string, string> {
  return Object.fromEntries(GUIDE_SOURCE_FILES.map((file, i) => [file, fakeSource(i + 1)]));
}

const sha = (file: string) => `hash-of-${file}`;

function build(sources = fakeSources()) {
  return buildGuideSet({ sources, commit: COMMIT, repository: REPOSITORY, sha256: (_text, file) => sha(file) });
}

describe("buildGuideSet", () => {
  it("lists the ten source guides in order", () => {
    expect(GUIDE_SOURCE_FILES).toHaveLength(10);
    expect(GUIDE_SOURCE_FILES[0]).toBe("01-materials-and-methods.md");
    expect(GUIDE_SOURCE_FILES[9]).toBe("10-back-matter.md");
    for (const [i, file] of GUIDE_SOURCE_FILES.entries()) expect(file.startsWith(String(i + 1).padStart(2, "0") + "-")).toBe(true);
  });

  it("produces the ten guides, the index and the source record", () => {
    const files = Object.keys(build().files).sort();
    expect(files).toEqual([...GUIDE_SOURCE_FILES, "INDEX.md", "SOURCE.json"].sort());
  });

  it("distills each guide with the source path and commit", () => {
    const set = build();
    const expected = distillGuide(fakeSource(3), "sections/03-results-and-discussion.md", COMMIT).markdown;
    expect(set.files["03-results-and-discussion.md"]).toBe(expected);
  });

  it("generates an index that lists every guide, states the advisory stance and the coherence invariants", () => {
    const index = build().files["INDEX.md"] as string;
    for (const file of GUIDE_SOURCE_FILES) expect(index).toContain(`\`${file}\``);
    expect(index.startsWith("# Writing guides\n")).toBe(true);
    expect(index).toMatch(/advisory/i);
    expect(index).toMatch(/venue template/i);
    expect(index).toMatch(/theses, reports and reviews/i);
    expect(index).toContain("LICENSE-papersmith-ai.txt");
    expect(index).toMatch(/same count, order and names/i);
    expect(index).toContain("the title selects among them");
  });

  it("records source path, hash, stripped and kept headings and the shared conventions", () => {
    const record = JSON.parse(build().files["SOURCE.json"] as string) as {
      repository: string;
      commit: string;
      files: Record<string, { source: string; sha256: string; stripped: string[]; kept: string[] }>;
      conventions: { rule: string; evidence: { file: string; quote: string }[] }[];
    };
    expect(record.repository).toBe(REPOSITORY);
    expect(record.commit).toBe(COMMIT);
    expect(Object.keys(record.files)).toEqual([...GUIDE_SOURCE_FILES]);
    expect(record.files["08-abstract.md"]).toEqual({
      source: "sections/08-abstract.md",
      sha256: "hash-of-08-abstract.md",
      stripped: [],
      kept: ["# Section 8", "## Disqualifiers"],
    });
    expect(record.conventions).toHaveLength(SHARED_CONVENTIONS.length);
  });

  it("is deterministic", () => {
    expect(build()).toEqual(build());
  });

  it("names the missing source file", () => {
    const sources = fakeSources();
    delete sources["05-related-work.md"];
    expect(() => build(sources)).toThrowError("05-related-work.md");
  });
});

describe("findMissingEvidence", () => {
  const sourcesWithQuotes = () => {
    const sources: Record<string, string> = {};
    for (const convention of SHARED_CONVENTIONS) {
      for (const evidence of convention.evidence) {
        sources[evidence.file] = `${sources[evidence.file] ?? ""}\n**${evidence.quote.split(" ").join("**\n  ")}**\n`;
      }
    }
    return sources;
  };

  it("finds every quote, ignoring emphasis marks and line wrapping", () => {
    expect(findMissingEvidence(sourcesWithQuotes())).toEqual([]);
  });

  it("reports the quotes that are absent from their source file", () => {
    const sources = sourcesWithQuotes();
    sources["07-conclusions.md"] = "nothing relevant";
    const missing = findMissingEvidence(sources);
    expect(missing).toContain('07-conclusions.md: "They add nothing"');
    expect(missing).toContain('07-conclusions.md: "Same count, same order, same names"');
    expect(missing.some((entry) => entry.startsWith("06-introduction.md"))).toBe(false);
  });

  it("reports a source file that is not available", () => {
    const sources = sourcesWithQuotes();
    delete sources["08-abstract.md"];
    expect(findMissingEvidence(sources)).toContain('08-abstract.md: file not available');
  });
});
