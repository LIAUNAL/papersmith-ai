import { existsSync, mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import type { AgentDefinition, AgentEvent } from "@caztor/core";
import { afterAll, describe, expect, it } from "vitest";
import { createNodeSpawner, nodeFileSystem, systemClock } from "../../../src/index.ts";
import { createOpencodeRunner } from "../../../src/providers/opencode/runner.ts";

/**
 * Plants a project whose opencode configuration would run programs (a local MCP server and a plugin, each leaving a
 * marker file) and checks, with the real `opencode` and only free commands, that detection and a refused turn run none
 * of it. No model is called. Runs only with `CAZTOR_REAL_BIN=1` and `CAZTOR_REAL_OPENCODE=1`.
 */
const enabled = process.env["CAZTOR_REAL_BIN"] === "1" && process.env["CAZTOR_REAL_OPENCODE"] === "1";
const dirs: string[] = [];
afterAll(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function planted() {
  const base = realpathSync(mkdtempSync(join(tmpdir(), "caztor-real-config-")));
  dirs.push(base);
  const root = join(base, "project");
  const marks = join(base, "marks");
  mkdirSync(join(root, ".opencode", "plugins"), { recursive: true });
  mkdirSync(marks);
  writeFileSync(join(root, "main.tex"), "Hello.\n");
  writeFileSync(join(root, "opencode.json"), JSON.stringify({ mcp: { x: { type: "local", command: ["touch", join(marks, "mcp")] } } }));
  writeFileSync(
    join(root, ".opencode", "plugins", "p.js"),
    `import { writeFileSync } from "node:fs";\nwriteFileSync(${JSON.stringify(join(marks, "plugin"))}, "ran");\nexport const P = async () => ({});\n`,
  );
  const marked = () => ["mcp", "plugin"].filter((name) => existsSync(join(marks, name)));
  const reset = () => {
    for (const name of ["mcp", "plugin"]) rmSync(join(marks, name), { force: true });
  };
  return { root, marked, reset };
}

const agent: AgentDefinition = { hash: `sha256:${"a".repeat(64)}`, name: "caztor", description: "x", prompt: "x", tools: ["edit"] };

describe.skipIf(!enabled)("the real opencode with a malicious project (opt-in, spends nothing)", () => {
  it("control: a plain, non-pure opencode started in the project does run its plugin, so the markers can fire", () => {
    const { root, marked, reset } = planted();
    reset();
    const env = { ...process.env, XDG_CONFIG_HOME: join(root, "..", "xdg") };
    spawnSync("opencode", ["models"], { cwd: root, env, encoding: "utf8", timeout: 60_000, stdio: ["ignore", "pipe", "pipe"] });
    expect(marked()).toContain("plugin");
  }, 90_000);

  it("detection runs nothing from the project and still lists models", async () => {
    const { root, marked, reset } = planted();
    reset();
    const runner = createOpencodeRunner({ fs: nodeFileSystem, spawner: createNodeSpawner(), clock: systemClock, root, env: process.env });
    const status = await runner.detect();
    expect(status.installed).toBe(true);
    expect(marked()).toEqual([]);
  }, 90_000);

  it("reports the planted files and refuses a turn that is not trusted, without starting opencode", async () => {
    const { root, marked, reset } = planted();
    reset();
    const runner = createOpencodeRunner({ fs: nodeFileSystem, spawner: createNodeSpawner(), clock: systemClock, root, env: process.env });
    const found = await runner.projectConfig?.();
    expect(found?.files).toEqual(["opencode.json", ".opencode/plugins/"]);
    const events: AgentEvent[] = [];
    for await (const event of runner.runTurn({ prompt: "hi", sessionId: null, model: "openai/gpt-5.5", agent }, new AbortController().signal)) events.push(event);
    expect(events[0]).toMatchObject({ type: "error", code: "isolation_failed" });
    expect(marked()).toEqual([]);
  }, 90_000);

  it("a free pure command in the project runs no plugin and no MCP server either", () => {
    const { root, marked, reset } = planted();
    reset();
    const env = { ...process.env, XDG_CONFIG_HOME: join(root, "..", "xdg") };
    const out = spawnSync("opencode", ["--pure", "debug", "agent", "caztor"], { cwd: root, env, encoding: "utf8", timeout: 60_000, stdio: ["ignore", "pipe", "pipe"] });
    expect(out.status).not.toBeNull();
    expect(marked()).toEqual([]);
  }, 90_000);
});
