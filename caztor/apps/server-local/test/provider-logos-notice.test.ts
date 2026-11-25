import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const root = fileURLToPath(new URL("../../..", import.meta.url));
const notice = readFileSync(join(root, "NOTICE.md"), "utf8");

describe("NOTICE.md and the provider names", () => {
  it("ships no vendor logo: every provider is a text label", () => {
    expect(existsSync(join(root, "apps", "web", "src", "assets", "providers"))).toBe(false);
    expect(notice).toMatch(/ships no logo or other brand asset/i);
  });

  it("keeps the non-affiliation statement for the provider names", () => {
    expect(notice).toMatch(/not affiliated with/i);
  });
});
