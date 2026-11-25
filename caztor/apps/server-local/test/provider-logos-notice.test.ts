import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const root = fileURLToPath(new URL("../../..", import.meta.url));
const assets = join(root, "apps", "web", "src", "assets", "providers");
const notice = readFileSync(join(root, "NOTICE.md"), "utf8");

describe("NOTICE.md", () => {
  const files = readdirSync(assets).filter((name) => name.endsWith(".svg"));

  it("records every shipped provider logo with its source, its checksum and the non-affiliation statement", () => {
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const row = notice.split("\n").find((line) => line.startsWith("|") && line.includes(`\`${file}\``));
      expect(row, `${file} has a row`).toBeDefined();
      expect(row).toMatch(/https:\/\//);
      const sum = createHash("sha256").update(readFileSync(join(assets, file))).digest("hex");
      expect(row, `${file} checksum`).toContain(sum);
    }
    expect(notice).toMatch(/not affiliated with/i);
    expect(notice).toMatch(/retrieved on \d{4}-\d{2}-\d{2}/i);
  });

  it("ships the Codex logo, and says it is the OpenAI company mark used to identify Codex", () => {
    expect(files).toContain("codex.svg");
    const row = notice.split("\n").find((line) => line.startsWith("|") && line.includes("`codex.svg`"))!;
    expect(row).toContain("https://developers.openai.com/");
    expect(row).toMatch(/OpenAI company mark/);
    expect(row).toMatch(/identify Codex/);
    expect(notice).not.toMatch(/None found/);
  });

  it("ships the logos unmodified: plain vector files that cannot run code or load anything", () => {
    for (const file of files) {
      const text = readFileSync(join(assets, file), "utf8");
      expect(text, file).not.toMatch(/<script|onload|onerror|<image|xlink:href|href=["']http/i);
    }
  });
});
