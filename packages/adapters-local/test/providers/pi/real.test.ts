import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { createNodeSpawner, nodeFileSystem, systemClock } from "../../../src/index.ts";
import { createPiRunner } from "../../../src/providers/pi/runner.ts";

/**
 * Talks to the real `pi`. `CAZTOR_REAL_BIN=1` and `CAZTOR_REAL_PI=1` check detection only (`--version` and
 * `--list-models`), which costs nothing. There is no real turn here: a turn spends the account's quota.
 */
const enabled = process.env["CAZTOR_REAL_BIN"] === "1" && process.env["CAZTOR_REAL_PI"] === "1";
const dirs: string[] = [];
afterAll(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe.skipIf(!enabled)("the real pi", () => {
  it("is detected with a version, and lists models only when someone is signed in", async () => {
    const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-real-pi-")));
    dirs.push(root);
    const status = await createPiRunner({ fs: nodeFileSystem, spawner: createNodeSpawner(), clock: systemClock, root, env: process.env }).detect();
    expect(status).toMatchObject({ provider: "pi", installed: true, requiresModel: false });
    expect(status.version).toMatch(/^\d+\.\d+\.\d+$/);
    for (const model of status.models ?? []) expect(model).toMatch(/^[a-z0-9][a-z0-9._-]*\/\S+$/);
  }, 60_000);
});
