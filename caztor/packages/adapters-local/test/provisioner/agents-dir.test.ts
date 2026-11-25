import { isAbsolute } from "node:path";
import { describe, expect, it } from "vitest";
import { defaultAgentsDir } from "../../src/agents-dir.ts";
import { nodeFileSystem } from "../../src/node-infra.ts";
import { decode } from "./support.ts";

describe("shipped agents folder", () => {
  it("is an absolute path to the folder holding the three definitions", async () => {
    const dir = defaultAgentsDir();
    expect(isAbsolute(dir)).toBe(true);
    for (const name of ["claude", "opencode", "codex"]) {
      const text = decode(await nodeFileSystem.readFile(`${dir}/${name}.md`));
      expect(text).toContain("## Provider characteristics");
    }
  });

  it("does not depend on the working directory of the process", async () => {
    const before = defaultAgentsDir();
    const original = process.cwd();
    // Vitest workers share the process, so move back immediately; the path was built from the module location.
    process.chdir("/");
    try {
      expect(defaultAgentsDir()).toBe(before);
      expect(decode(await nodeFileSystem.readFile(`${defaultAgentsDir()}/claude.md`))).toContain("name: caztor");
    } finally {
      process.chdir(original);
    }
  });
});
