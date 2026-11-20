import { appendFileSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { hashBytes } from "@caztor/core";
import type { AgentEvent } from "@caztor/core";
import { afterAll, describe, expect, it } from "vitest";
import { parseAgentFile } from "../../../src/agent-definition.ts";
import { nodeFileSystem, createNodeSpawner, systemClock } from "../../../src/index.ts";
import { ALLOWED_TOOLS, createClaudeRunner } from "../../../src/providers/claude/runner.ts";

/**
 * Talks to the real Claude Code and SPENDS TOKENS (two small turns, a few cents). It runs only when both
 * `CAZTOR_REAL_BIN=1` (real binaries) and `CAZTOR_REAL_CLAUDE=1` (this test) are set, and needs a logged-in `claude`.
 * `CAZTOR_REAL_CLAUDE_TURNS=1` runs only the first turn (one call). `CAZTOR_REAL_REPORT=<file>` appends what each turn
 * showed (argv, `system/init`, cost, usage) to a file, because the reporter may not print console output.
 */
const enabled = process.env["CAZTOR_REAL_BIN"] === "1" && process.env["CAZTOR_REAL_CLAUDE"] === "1";
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

describe.skipIf(!enabled)("the real Claude Code (opt-in, spends tokens)", () => {
  it("runs an isolated turn that edits a file, then resumes the conversation", { timeout: 240_000 }, async () => {
    const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-real-claude-")));
    dirs.push(root);
    mkdirSync(join(root, "sections"));
    writeFileSync(join(root, "main.tex"), "\\documentclass{article}\n\\begin{document}\nThe cat sat on the mat.\n\\end{document}\n");
    const text = readFileSync(fileURLToPath(new URL("../../../../../agents/claude.md", import.meta.url)), "utf8");
    const agent = parseAgentFile("claude", text, await hashBytes(new TextEncoder().encode(text)));
    expect(agent).not.toBeNull();

    const lines: string[] = [];
    const spawner = createNodeSpawner();
    const calls: Array<{ args: readonly string[]; env: string[] }> = [];
    const runner = createClaudeRunner({
      fs: nodeFileSystem,
      spawner: { spawn: (spec) => (calls.push({ args: spec.args, env: Object.keys(spec.env) }), spawner.spawn(spec)) },
      clock: systemClock,
      root,
      env: process.env,
      tap: (line) => lines.push(line),
    });

    const status = await runner.detect();
    expect(status.installed, status.unavailableReason).toBe(true);

    const first = await collect(runner.runTurn({ prompt: "In main.tex change the word cat to dog. Then answer with one word, yes or no: does your context mention Engram?", sessionId: null, model: null, agent: agent! }, new AbortController().signal));
    const init = lines.map((l) => JSON.parse(l) as Record<string, unknown>).find((l) => l["subtype"] === "init");
    const result = lines.map((l) => JSON.parse(l) as Record<string, unknown>).find((l) => l["type"] === "result");
    const hooks = lines.filter((l) => l.includes('"hook_started"')).length;
    report(
      {
        version: status.version,
        argv: calls.at(-1)?.args.map((arg) => (arg.length > 120 ? `${arg.slice(0, 60)}...(${arg.length} chars)` : arg)),
        envNames: calls.at(-1)?.env,
        hookStartedLines: hooks,
        init: init === undefined ? null : { tools: init["tools"], mcp_servers: init["mcp_servers"], slash_commands: init["slash_commands"], agents: init["agents"], skills: init["skills"], plugins: init["plugins"], memory_paths: init["memory_paths"], apiKeySource: init["apiKeySource"], permissionMode: init["permissionMode"] },
        cost: result?.["total_cost_usd"],
        usage: result?.["usage"],
        events: first.map((event) => event.type),
        answer: first.filter((event) => event.type === "text").map((event) => (event.type === "text" ? event.text : "")),
      },
    );
    expect(first.at(-1), JSON.stringify(first.slice(-3))).toMatchObject({ type: "done", reason: "completed" });
    expect(readFileSync(join(root, "main.tex"), "utf8")).toContain("The dog sat on the mat.");
    const session = first.find((event) => event.type === "session");
    expect(session).toBeDefined();
    expect(init?.["tools"]).toEqual([...ALLOWED_TOOLS]);
    expect(init?.["mcp_servers"]).toEqual([]);
    expect(hooks).toBe(0);

    if (process.env["CAZTOR_REAL_CLAUDE_TURNS"] === "1") return;
    const sessionId = session?.type === "session" ? session.sessionId : null;
    lines.length = 0;
    const second = await collect(runner.runTurn({ prompt: "Change dog back to cat in main.tex and answer: done", sessionId, model: null, agent: agent! }, new AbortController().signal));
    const result2 = lines.map((l) => JSON.parse(l) as Record<string, unknown>).find((l) => l["type"] === "result");
    report({ resumeArgv: calls.at(-1)?.args.slice(-2), resumedSession: second.find((event) => event.type === "session"), cost: result2?.["total_cost_usd"], usage: result2?.["usage"], events: second.map((event) => event.type) });
    expect(second.at(-1)).toMatchObject({ type: "done", reason: "completed" });
    expect(calls.at(-1)?.args).toContain("--resume");
    expect(readFileSync(join(root, "main.tex"), "utf8")).toContain("The cat sat on the mat.");
  });
});
