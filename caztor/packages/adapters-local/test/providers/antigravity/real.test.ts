import { mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { AgentEvent } from "@caztor/core";
import { afterAll, describe, expect, it } from "vitest";
import { createNodeSpawner, nodeFileSystem, systemClock } from "../../../src/index.ts";
import { createAntigravityRunner } from "../../../src/providers/antigravity/runner.ts";

/**
 * Talks to the real `agy`. `CAZTOR_REAL_BIN=1` and `CAZTOR_REAL_AGY=1` check detection, which is free.
 * `CAZTOR_REAL_AGY_TURNS=1` adds one real turn, which spends the account's quota.
 */
const enabled = process.env["CAZTOR_REAL_BIN"] === "1" && process.env["CAZTOR_REAL_AGY"] === "1";
const turns = enabled && process.env["CAZTOR_REAL_AGY_TURNS"] === "1";
const dirs: string[] = [];
afterAll(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function runner() {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-real-agy-")));
  dirs.push(root);
  writeFileSync(join(root, "main.tex"), "The cat sat on the mat.\n");
  return { root, runner: createAntigravityRunner({ fs: nodeFileSystem, spawner: createNodeSpawner(), clock: systemClock, root, env: process.env }) };
}

describe.skipIf(!enabled)("the real agy", () => {
  it("is detected with a version and a model list", async () => {
    const status = await runner().runner.detect();
    expect(status).toMatchObject({ provider: "antigravity", installed: true });
    expect(status.models?.length).toBeGreaterThan(0);
  }, 60_000);

  it.skipIf(!turns)("completes one turn with only allowed tools", async () => {
    const events: AgentEvent[] = [];
    const { runner: real } = runner();
    for await (const event of real.runTurn({ prompt: "Reply with the word OK.", sessionId: null, model: null } as never, new AbortController().signal)) events.push(event);
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  }, 180_000);
});
