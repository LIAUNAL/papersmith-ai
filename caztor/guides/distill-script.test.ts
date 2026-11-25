import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { GUIDE_SOURCE_FILES } from "../packages/adapters-local/src/guides/build-set.ts";
import { SHARED_CONVENTIONS } from "../packages/adapters-local/src/guides/distill.ts";
import { buildFromRepository } from "../scripts/distill-guides.ts";

const temps: string[] = [];
afterEach(() => {
  for (const dir of temps.splice(0)) rmSync(dir, { recursive: true, force: true });
});

const LICENSE = "Apache License\nVersion 2.0, January 2004\n";

function section(file: string): string {
  const quotes = SHARED_CONVENTIONS.flatMap((c) => c.evidence)
    .filter((e) => e.file === file)
    .map((e) => e.quote)
    .join("\n\n");
  return `---\n{ "section": "${file}" }\n---\n# ${file}\n\n${quotes}\n\n## Disqualifiers\n\n- Weak.\n`;
}

function git(dir: string, ...args: string[]): string {
  return execFileSync("git", ["-C", dir, "-c", "user.name=Test", "-c", "user.email=test@example.com", ...args], { encoding: "utf8" }).trim();
}

function repository(overrides: Record<string, string> = {}): { dir: string; commit: string } {
  const dir = mkdtempSync(join(tmpdir(), "caztor-distill-"));
  temps.push(dir);
  git(dir, "init", "--quiet");
  mkdirSync(join(dir, "sections"));
  for (const file of GUIDE_SOURCE_FILES) writeFileSync(join(dir, "sections", file), overrides[file] ?? section(file));
  writeFileSync(join(dir, "LICENSE"), LICENSE);
  git(dir, "add", "-A");
  git(dir, "commit", "--quiet", "-m", "sources");
  return { dir, commit: git(dir, "rev-parse", "--short", "HEAD") };
}

describe("buildFromRepository", () => {
  it("builds the guide files and the license from a commit", () => {
    const { dir, commit } = repository();
    const built = buildFromRepository(dir, commit);
    expect(Object.keys(built.files).sort()).toEqual([...GUIDE_SOURCE_FILES, "INDEX.md", "SOURCE.json"].sort());
    expect(built.license).toBe(LICENSE);
    expect(built.files["08-abstract.md"]).toContain(`commit \`${commit}\``);
    const record = JSON.parse(built.files["SOURCE.json"] as string) as { commit: string; files: Record<string, { sha256: string }> };
    expect(record.commit).toBe(commit);
    expect(record.files["08-abstract.md"]?.sha256).toMatch(/^[0-9a-f]{64}$/);
  });

  it("reads the committed text, not the working tree", () => {
    const { dir, commit } = repository();
    writeFileSync(join(dir, "sections", "08-abstract.md"), "no front matter at all\n");
    const built = buildFromRepository(dir, commit);
    expect(built.files["08-abstract.md"]).toContain("# 08-abstract.md");
  });

  it("rejects a commit that does not exist", () => {
    const { dir } = repository();
    expect(() => buildFromRepository(dir, "deadbee")).toThrowError(/deadbee/);
  });

  it("fails when a cited source quote is missing from its file", () => {
    const { dir, commit } = repository({ "07-conclusions.md": "---\n{ }\n---\n# C\n\n## Disqualifiers\n\n- x\n" });
    expect(() => buildFromRepository(dir, commit)).toThrowError(/07-conclusions\.md: "They add nothing"/);
  });
});
