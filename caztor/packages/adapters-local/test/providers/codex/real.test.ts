import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { afterAll, describe, expect, it } from "vitest";
import { nodeFileSystem, createNodeSpawner, systemClock } from "../../../src/index.ts";
import { createCodexRunner } from "../../../src/providers/codex/runner.ts";

/**
 * Checks the documentation-derived command line against the real `codex`, without spending tokens: detection, and that
 * `codex exec --help` knows every flag the adapter passes. Runs only with `CAZTOR_REAL_BIN=1` and `CAZTOR_REAL_CODEX=1`.
 * The adapter was written when no `codex` was installed, so this is the check to run first on a machine that has it.
 */
const enabled = process.env["CAZTOR_REAL_BIN"] === "1" && process.env["CAZTOR_REAL_CODEX"] === "1";
const dirs: string[] = [];
afterAll(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe.skipIf(!enabled)("the real codex (opt-in, spends nothing)", () => {
  it("is detected with a version", { timeout: 30_000 }, async () => {
    const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-real-codex-")));
    dirs.push(root);
    const status = await createCodexRunner({ fs: nodeFileSystem, spawner: createNodeSpawner(), clock: systemClock, root, env: process.env }).detect();
    console.log(JSON.stringify(status));
    expect(status.installed, status.unavailableReason).toBe(true);
    expect(status.version).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it("knows every flag of the command line, and the resume subcommand", { timeout: 30_000 }, () => {
    const help = spawnSync("codex", ["exec", "--help"], { encoding: "utf8" }).stdout;
    for (const flag of ["--json", "--sandbox", "--skip-git-repo-check", "--ignore-user-config"]) expect(help, flag).toContain(flag);
    expect(help).toContain("resume");
    console.log(`model flag documented: ${/--model|\s-m[,\s]/.test(help)}`);
  });
});
