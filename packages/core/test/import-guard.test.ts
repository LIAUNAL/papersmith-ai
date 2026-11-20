import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { findForbiddenImports } from "./support/scan-imports.ts";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const temps: string[] = [];

function fixture(files: Record<string, string>): string {
  const dir = mkdtempSync(join(tmpdir(), "caztor-guard-"));
  temps.push(dir);
  for (const [name, content] of Object.entries(files)) {
    const full = join(dir, name);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, content);
  }
  return dir;
}

afterEach(() => {
  for (const dir of temps.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("findForbiddenImports", () => {
  it("flags a node: import planted in a fixture", () => {
    const dir = fixture({ "bad.ts": 'import { readFileSync } from "node:fs";\nexport const x = 1;\n' });
    expect(findForbiddenImports(dir)).toEqual([{ file: "bad.ts", specifier: "node:fs" }]);
  });

  it("flags bare builtin specifiers, dynamic imports and require calls", () => {
    const dir = fixture({
      "a.ts": 'import path from "path";\n',
      "nested/b.ts": 'const m = await import("child_process");\n',
      "nested/c.ts": 'const fs = require("fs/promises");\n',
      "d.ts": 'export * from "crypto";\n',
    });
    const found = findForbiddenImports(dir).map((v) => `${v.file}:${v.specifier}`).sort();
    expect(found).toEqual(["a.ts:path", "d.ts:crypto", "nested/b.ts:child_process", "nested/c.ts:fs/promises"]);
  });

  it("accepts relative and package imports", () => {
    const dir = fixture({
      "ok.ts": 'import { a } from "./a.ts";\nimport { Hono } from "hono";\nimport type { T } from "@caztor/core";\n',
    });
    expect(findForbiddenImports(dir)).toEqual([]);
  });
});

describe("pure packages stay free of Node built-ins", () => {
  it.each(["packages/core/src", "packages/api/src"])("%s has no node: or builtin imports", (rel) => {
    expect(findForbiddenImports(join(repoRoot, rel))).toEqual([]);
  });
});
