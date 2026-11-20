import { appendFileSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { hashBytes } from "@caztor/core";
import type { AgentEvent } from "@caztor/core";
import { afterAll, describe, expect, it } from "vitest";
import { parseAgentFile } from "../../../src/agent-definition.ts";
import { nodeFileSystem, createNodeSpawner, systemClock } from "../../../src/index.ts";
import { createOpencodeRunner } from "../../../src/providers/opencode/runner.ts";

/**
 * Talks to the real opencode. `CAZTOR_REAL_BIN=1` (real binaries) and `CAZTOR_REAL_OPENCODE=1` (this file) run the
 * detection, which spends nothing. The turns SPEND TOKENS and run only with `CAZTOR_REAL_OPENCODE_TURNS=1` as well, and
 * need a model the signed-in account can use, in `CAZTOR_REAL_OPENCODE_MODEL` (for example `openai/gpt-5.5`).
 * `CAZTOR_REAL_REPORT=<file>` appends what each step showed (argv, events, cost) to a file.
 */
const enabled = process.env["CAZTOR_REAL_BIN"] === "1" && process.env["CAZTOR_REAL_OPENCODE"] === "1";
const turns = enabled && process.env["CAZTOR_REAL_OPENCODE_TURNS"] === "1";
const dirs: string[] = [];
afterAll(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function report(entry: unknown): void {
  const text = JSON.stringify(entry);
  console.log(text);
  const file = process.env["CAZTOR_REAL_REPORT"];
  if (file !== undefined) appendFileSync(file, `${text}\n`);
}

async function collect(iterable: AsyncIterable<AgentEvent>): Promise<AgentEvent[]> {
  const out: AgentEvent[] = [];
  for await (const event of iterable) out.push(event);
  return out;
}

function project(): string {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-real-opencode-")));
  dirs.push(root);
  mkdirSync(join(root, ".opencode", "agents"), { recursive: true });
  writeFileSync(join(root, "main.tex"), "\\documentclass{article}\n\\begin{document}\nThe cat sat on the mat.\n\\end{document}\n");
  writeFileSync(join(root, ".opencode", "agents", "caztor.md"), readFileSync(fileURLToPath(new URL("../../../../../agents/opencode.md", import.meta.url)), "utf8"));
  return root;
}

describe.skipIf(!enabled)("the real opencode detection (opt-in, spends nothing)", () => {
  it("finds the binary, reads its version and lists models in the form provider/model", { timeout: 60_000 }, async () => {
    const root = project();
    const runner = createOpencodeRunner({ fs: nodeFileSystem, spawner: createNodeSpawner(), clock: systemClock, root, env: process.env });
    const status = await runner.detect();
    report({ detect: status });
    expect(status.installed, status.unavailableReason).toBe(true);
    expect(status.version).toMatch(/^\d+\.\d+\.\d+$/);
    expect(status.requiresModel).toBe(true);
    expect(status.models?.length ?? 0).toBeGreaterThan(0);
    for (const model of status.models ?? []) expect(model).toMatch(/^[^/\s]+\/\S+$/);
  });
});

describe.skipIf(!turns)("the real opencode turns (opt-in, spends tokens)", () => {
  it("runs an isolated turn that edits a file, then continues the session", { timeout: 300_000 }, async () => {
    const model = process.env["CAZTOR_REAL_OPENCODE_MODEL"];
    expect(model, "set CAZTOR_REAL_OPENCODE_MODEL").toBeTruthy();
    const root = project();
    const text = readFileSync(join(root, ".opencode", "agents", "caztor.md"), "utf8");
    const agent = parseAgentFile("opencode", text, await hashBytes(new TextEncoder().encode(text)))!;
    const lines: string[] = [];
    const spawner = createNodeSpawner();
    const calls: Array<{ args: readonly string[]; env: string[] }> = [];
    const runner = createOpencodeRunner({
      fs: nodeFileSystem,
      spawner: { spawn: (spec) => (calls.push({ args: spec.args, env: Object.keys(spec.env) }), spawner.spawn(spec)) },
      clock: systemClock,
      root,
      env: process.env,
      tap: (line) => lines.push(line),
    });
    const first = await collect(runner.runTurn({ prompt: "In main.tex change the word cat to dog. Then say yes or no: do you have any tool whose name starts with engram?", sessionId: null, model: model!, agent }, new AbortController().signal));
    report({ argv: calls.at(-1)?.args, envNames: calls.at(-1)?.env, events: first.map((event) => event.type), done: first.at(-1) });
    expect(first.at(-1), JSON.stringify(first.slice(-3))).toMatchObject({ type: "done", reason: "completed" });
    expect(readFileSync(join(root, "main.tex"), "utf8")).toContain("The dog sat on the mat.");
    const session = first.find((event) => event.type === "session");
    expect(session).toBeDefined();
    const toolNames = lines.map((line) => JSON.parse(line) as { type?: string; part?: { tool?: string } }).flatMap((event) => (event.type === "tool_use" ? [event.part?.tool ?? ""] : []));
    expect(toolNames.every((name) => !name.startsWith("engram"))).toBe(true);

    if (process.env["CAZTOR_REAL_OPENCODE_TURNS_ONE"] === "1") return;
    const sessionId = session?.type === "session" ? session.sessionId : null;
    const second = await collect(runner.runTurn({ prompt: "Change dog back to cat in main.tex and answer: done", sessionId, model: model!, agent }, new AbortController().signal));
    report({ resumeArgv: calls.at(-1)?.args.slice(-2), events: second.map((event) => event.type), done: second.at(-1) });
    expect(second.at(-1)).toMatchObject({ type: "done", reason: "completed" });
    expect(calls.at(-1)?.args).toContain("-s");
    expect(readFileSync(join(root, "main.tex"), "utf8")).toContain("The cat sat on the mat.");
  });
});
