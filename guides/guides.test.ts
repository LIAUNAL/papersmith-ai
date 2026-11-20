import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { GUIDE_SOURCE_FILES } from "../packages/adapters-local/src/guides/build-set.ts";
import { PIPELINE_TERMS, SHARED_CONVENTIONS, STRIPPED_HEADINGS } from "../packages/adapters-local/src/guides/distill.ts";
import { buildFromRepository } from "../scripts/distill-guides.ts";

const guidesDir = dirname(fileURLToPath(import.meta.url));
const root = join(guidesDir, "..");
const read = (name: string) => readFileSync(join(guidesDir, name), "utf8");

interface SourceRecord {
  repository: string;
  commit: string;
  files: Record<string, { source: string; sha256: string; stripped: string[]; kept: string[] }>;
}
const record = JSON.parse(read("SOURCE.json")) as SourceRecord;

/** Headings of the distilled body, without the sections Caztor appends. */
function bodyHeadings(markdown: string): string[] {
  const body = markdown.slice(0, markdown.indexOf("\n## Shared conventions"));
  return body.split("\n").filter((line) => /^#{1,6} /.test(line));
}

/** Text without the added notice and advisory block quote, which names the source path by design. */
const withoutNotice = (markdown: string) =>
  markdown
    .split("\n")
    .filter((line) => !line.startsWith(">"))
    .join("\n");

describe("the shipped guides", () => {
  it("are ten guides, an index and a source record", () => {
    const shipped = readdirSync(guidesDir)
      .filter((name) => name.endsWith(".md") || name === "SOURCE.json")
      .sort();
    expect(shipped).toEqual([...GUIDE_SOURCE_FILES, "INDEX.md", "SOURCE.json"].sort());
  });

  it("record the repository and the commit", () => {
    expect(record.commit).toBe("1f09516");
    expect(record.repository).toBe("https://github.com/Daprosero/papersmith-ai");
    expect(Object.keys(record.files)).toEqual([...GUIDE_SOURCE_FILES]);
  });

  describe.each(GUIDE_SOURCE_FILES)("%s", (file) => {
    const text = read(file);

    it("keeps exactly the headings the source record lists", () => {
      expect(bodyHeadings(text)).toEqual(record.files[file]?.kept);
    });

    it("strips only the pipeline input subsections", () => {
      const stripped = record.files[file]?.stripped ?? [];
      for (const heading of stripped) expect(STRIPPED_HEADINGS as readonly string[]).toContain(heading);
      for (const heading of STRIPPED_HEADINGS) expect(text).not.toContain(`\n${heading}\n`);
    });

    it("carries a modification notice with the source path, the commit and the license", () => {
      expect(text).toContain(`\`sections/${file}\``);
      expect(text).toContain("commit `1f09516`");
      expect(text).toContain("Apache License, Version 2.0");
      expect(text).toContain("`LICENSE-papersmith-ai.txt`");
    });

    it("states that it is advisory, that extents are typical ranges, and names the other genres", () => {
      expect(text).toMatch(/\*\*Advisory\.\*\* This guide is advice, not a set of rules/);
      expect(text).toContain("the venue template take precedence");
      expect(text).toMatch(/typical ranges for a research article/);
      expect(text).toContain("theses, reports and reviews");
    });

    it("lists its disqualifiers and the shared conventions last", () => {
      expect(text).toContain("\n## Disqualifiers\n");
      const conventions = text.indexOf("\n## Shared conventions\n");
      expect(conventions).toBeGreaterThan(text.indexOf("\n## Disqualifiers\n"));
      expect(text.slice(conventions).match(/^## /gm)).toHaveLength(1);
      for (const convention of SHARED_CONVENTIONS) expect(text).toContain(convention.rule);
    });

    it("states its extent", () => {
      if (file === "10-back-matter.md") expect(text).toContain("| Block | Required | Words |");
      else expect(text).toContain("**Extent**");
    });

    it("has no vocabulary of the source project's tooling", () => {
      const body = withoutNotice(text);
      for (const term of PIPELINE_TERMS) expect(body, String(term)).not.toMatch(term);
    });
  });

  it("keeps the introduction's generic drafting advice", () => {
    const intro = read("06-introduction.md");
    expect(intro).toContain("### What is writable before measuring");
    expect(intro).toContain("### The loop that must be closed by hand");
    expect(intro).toContain("**The results rule.**");
    expect(intro).toContain("the text is corrected to match them — never the reverse.");
    expect(intro).not.toContain("### Internal chain");
  });

  it("describes a drafting order instead of the source project's inputs", () => {
    for (const file of GUIDE_SOURCE_FILES) expect(read(file)).not.toMatch(/^## Inputs/m);
  });

  it("has an index that lists every guide and states the advisory stance", () => {
    const index = read("INDEX.md");
    for (const file of GUIDE_SOURCE_FILES) expect(index).toContain(`\`${file}\``);
    expect(index).toContain("advisory");
    expect(index).toContain("theses, reports and reviews");
    expect(index).toContain("`LICENSE-papersmith-ai.txt`");
    for (const term of PIPELINE_TERMS) expect(index, String(term)).not.toMatch(term);
  });
});

describe("attribution", () => {
  const license = readFileSync(join(root, "LICENSES", "Apache-2.0.txt"), "utf8");
  const notice = readFileSync(join(root, "NOTICE.md"), "utf8");

  it("ships the Apache-2.0 license text", () => {
    expect(license).toContain("Apache License");
    expect(license).toContain("Version 2.0, January 2004");
    expect(license).toContain("END OF TERMS AND CONDITIONS");
  });

  it("names the origin project, license, commit and the changes in NOTICE.md", () => {
    const start = notice.indexOf("## Writing guides");
    expect(start).toBeGreaterThan(-1);
    const section = notice.slice(start);
    expect(section).toContain("https://github.com/Daprosero/papersmith-ai");
    expect(section).toContain("Apache License, Version 2.0");
    expect(section).toContain("1f09516");
    expect(section).toContain("LICENSES/Apache-2.0.txt");
    expect(section).toMatch(/modified|changes/i);
  });
});

const papersmithDir = process.env["CAZTOR_PAPERSMITH_DIR"];

describe.skipIf(papersmithDir === undefined)("rebuild from the source repository (CAZTOR_PAPERSMITH_DIR)", () => {
  it("reproduces the committed guides and license byte for byte", () => {
    const built = buildFromRepository(papersmithDir as string, record.commit);
    for (const [name, content] of Object.entries(built.files)) expect(read(name), name).toBe(content);
    expect(readFileSync(join(root, "LICENSES", "Apache-2.0.txt"), "utf8")).toBe(built.license);
  });

  it("matches the recorded source hashes and the cited evidence", () => {
    for (const [file, entry] of Object.entries(record.files)) {
      const source = execFileSync("git", ["-C", papersmithDir as string, "show", `${record.commit}:${entry.source}`], { encoding: "utf8" });
      expect(createHash("sha256").update(source).digest("hex"), file).toBe(entry.sha256);
    }
  });
});
