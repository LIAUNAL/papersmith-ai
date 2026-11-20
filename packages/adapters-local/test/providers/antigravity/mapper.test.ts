import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir, userInfo } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AgentEvent } from "@caztor/core";
import { describe, expect, it } from "vitest";
import {
  ANTIGRAVITY_ALLOWED_TOOLS,
  createAntigravityMapper,
  type AntigravityMapOutcome,
  type AntigravityToolStep,
} from "../../../src/providers/antigravity/mapper.ts";
import { MAX_LINE_BYTES, MAX_MALFORMED_LINES } from "../../../src/providers/claude/mapper.ts";

const fixtures = fileURLToPath(new URL("./fixtures/", import.meta.url));
const RAW = join(homedir(), ".cache", "caztor-tools", "agy-evidence");
const fixture = (name: string): string[] => readFileSync(join(fixtures, name), "utf8").split("\n").filter((line) => line !== "");
const ROOT = "/work/project";
const SESSION_1 = "00000000-0000-4000-8000-000000000001";

/** Feeds every line to a fresh mapper and returns everything it said. */
function run(lines: string[], finish?: { cancelled: boolean; exitCode?: number | null; stderrTail?: string }) {
  const mapper = createAntigravityMapper({ root: ROOT });
  const events: AgentEvent[] = [];
  const tools: AntigravityToolStep[] = [];
  let fatal = false;
  for (const line of lines) {
    const out = mapper.feed(line);
    events.push(...out.events);
    if (out.tool !== undefined) tools.push(out.tool);
    fatal ||= out.fatal;
    if (out.fatal) break;
  }
  if (finish !== undefined) events.push(...mapper.finish(finish));
  return { events, tools, fatal, mapper };
}

const types = (events: AgentEvent[]) => events.map((event) => event.type);

describe("the sanitized fixtures", () => {
  const names = readdirSync(fixtures).filter((name) => name.endsWith(".jsonl"));

  it("exist for the real turn, search turn, and synthetic variants", () => {
    expect(names.sort()).toEqual([
      "edit-turn.jsonl",
      "search-turn.jsonl",
      "synthetic-auth-failure.jsonl",
      "synthetic-disallowed-tool.jsonl",
      "synthetic-error-result.jsonl",
      "synthetic-malformed-line.jsonl",
      "synthetic-missing-result.jsonl",
    ].sort());
  });

  const rawIds = (): string[] => {
    if (!existsSync(RAW)) return [];
    try {
      return readdirSync(RAW)
        .filter((name) => name.endsWith(".jsonl"))
        .flatMap((name) => readFileSync(join(RAW, name), "utf8").match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi) ?? []);
    } catch {
      return [];
    }
  };

  it.each(names)("%s is valid JSON lines (or declared malformed) holding nothing of the machine it came from", (name) => {
    const text = readFileSync(join(fixtures, name), "utf8");
    const lines = text.split("\n").filter((l) => l !== "");
    expect(lines.length).toBeGreaterThan(0);
    if (name !== "synthetic-malformed-line.jsonl") {
      for (const entry of lines) expect(() => JSON.parse(entry)).not.toThrow();
    }
    const forbidden = [
      homedir(),
      userInfo().username,
      "/home/",
      "claude-1000",
      "engram",
      "codegraph",
      "context7",
      "gentle",
      "@gmail",
      "hsP6XbMZRU",
      "xlHnuhZHSW",
      ...rawIds(),
    ];
    for (const word of forbidden) {
      expect(text.includes(word), `${name} contains ${word}`).toBe(false);
    }
  });
});

describe("a whole turn that edits a file", () => {
  const result = run(fixture("edit-turn.jsonl"), { cancelled: false, exitCode: 0 });

  it("maps the session, the finished tools with kind and path, deltas and full text, and done completed", () => {
    expect(types(result.events)).toContain("session");
    expect(types(result.events)).toContain("tool_start");
    expect(types(result.events)).toContain("tool_end");
    expect(types(result.events)).toContain("done");

    const session = result.events.find((e) => e.type === "session");
    expect(session).toEqual({ type: "session", sessionId: SESSION_1 });

    const toolStarts = result.events.filter((e) => e.type === "tool_start");
    expect(toolStarts).toHaveLength(2);
    expect(toolStarts[0]).toMatchObject({ type: "tool_start", name: "view_file", kind: "read", path: "main.tex" });
    expect(toolStarts[1]).toMatchObject({ type: "tool_start", name: "replace_file_content", kind: "edit", path: "main.tex" });

    const toolEnds = result.events.filter((e) => e.type === "tool_end");
    expect(toolEnds).toHaveLength(2);
    expect(toolEnds[0]).toEqual({ type: "tool_end", toolId: toolStarts[0]?.toolId, status: "done" });
    expect(toolEnds[1]).toEqual({ type: "tool_end", toolId: toolStarts[1]?.toolId, status: "done" });

    const texts = result.events.filter((e) => e.type === "text");
    expect(texts.length).toBeGreaterThan(0);

    const done = result.events.find((e) => e.type === "done");
    expect(done).toEqual({
      type: "done",
      reason: "completed",
      usage: { inputTokens: 23214, outputTokens: 624 },
    });
  });

  it("streams the text chunk by chunk and arrives at the same final text however it was chunked", () => {
    const deltas = result.events.filter((e) => e.type === "text_delta");
    const deltaCombined = deltas.map((e) => (e.type === "text_delta" ? e.text : "")).join("");
    const texts = result.events.filter((e) => e.type === "text");
    const textCombined = texts.map((e) => (e.type === "text" ? e.text : "")).join("");
    expect(deltaCombined).toContain("replace \"cat\" with \"dog\"");
    expect(deltaCombined).toContain("changed \"cat\" to \"dog\"");
    expect(textCombined).toBe(deltaCombined);
  });

  it("never shows thinking or internal content", () => {
    expect(JSON.stringify(result.events)).not.toMatch(/thinking_tokens/);
    expect(JSON.stringify(result.events)).not.toMatch(/\"thinking\"/);
  });
});

describe("a search turn", () => {
  const result = run(fixture("search-turn.jsonl"), { cancelled: false, exitCode: 0 });

  it("maps list_dir to search tool and reports completion", () => {
    const toolStart = result.events.find((e) => e.type === "tool_start");
    expect(toolStart).toMatchObject({ type: "tool_start", name: "list_dir", kind: "search" });
    const done = result.events.find((e) => e.type === "done");
    expect(done).toMatchObject({ type: "done", reason: "completed" });
  });
});

describe("checkpoints, user_input and unknown events", () => {
  it("ignores user_input, checkpoint, and unknown event types without failing", () => {
    const lines = [
      JSON.stringify({ event: "init", conversation_id: SESSION_1, init: { model: "m", cwd: ROOT, agent: "caztor", tools: ["view_file"], permission_mode: "request-review" } }),
      JSON.stringify({ event: "step_update", step_update: { conversation_id: SESSION_1, step_index: 0, state: "DONE", step_type: "user_input" } }),
      JSON.stringify({ event: "step_update", step_update: { conversation_id: SESSION_1, step_index: 1, state: "DONE", step_type: "checkpoint" } }),
      JSON.stringify({ event: "unknown_event_type", data: {} }),
      JSON.stringify({ event: "result", result: { conversation_id: SESSION_1, status: "SUCCESS", response: "ok", duration_seconds: 1, num_turns: 1, usage: { input_tokens: 10, output_tokens: 5, thinking_tokens: 0, cache_read_tokens: 0, total_tokens: 15 } } }),
    ];
    const { events } = run(lines, { cancelled: false, exitCode: 0 });
    expect(types(events)).toEqual(["session", "text", "done"]);
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });
});

describe("result with error", () => {
  it("maps a failed result event to a readable error and failed done", () => {
    const { events } = run(fixture("synthetic-error-result.jsonl"), { cancelled: false, exitCode: 1 });
    expect(events).toEqual([
      { type: "session", sessionId: "00000000-0000-4000-8000-000000000006" },
      { type: "error", code: "provider_error", message: "The model returned an internal error." },
      { type: "done", reason: "failed" },
    ]);
  });
});

describe("auth failure and AGY_ERROR", () => {
  it("maps auth failure fixture to auth error with login hint", () => {
    const { events } = run(fixture("synthetic-auth-failure.jsonl"), { cancelled: false, exitCode: 3 });
    const err = events.find((e) => e.type === "error");
    expect(err).toMatchObject({
      type: "error",
      code: "auth",
      message: expect.stringContaining("run `agy` and follow the sign-in prompts"),
    });
  });

  it("maps exitCode 3 on finish to auth error with login hint", () => {
    const mapper = createAntigravityMapper({ root: ROOT });
    const events = mapper.finish({ cancelled: false, exitCode: 3 });
    expect(events).toEqual([
      { type: "error", code: "auth", message: expect.stringContaining("run `agy` and follow the sign-in prompts") },
      { type: "done", reason: "failed" },
    ]);
  });

  it("maps AGY_ERROR in stderr to auth error with login hint when authentication is mentioned", () => {
    const mapper = createAntigravityMapper({ root: ROOT });
    const events = mapper.finish({ cancelled: false, exitCode: 1, stderrTail: "AGY_ERROR: sign in required" });
    expect(events).toEqual([
      { type: "error", code: "auth", message: expect.stringContaining("run `agy` and follow the sign-in prompts") },
      { type: "done", reason: "failed" },
    ]);
  });
});

describe("malformed output", () => {
  it("fails with malformed_output after 20 unparseable lines", () => {
    const { events, fatal } = run(fixture("synthetic-malformed-line.jsonl"));
    expect(fatal).toBe(true);
    expect(events).toEqual([
      { type: "error", code: "malformed_output", message: "Antigravity sent output Caztor could not read." },
      { type: "done", reason: "failed" },
    ]);
  });
});

describe("oversized line", () => {
  it("drops lines exceeding MAX_LINE_BYTES and emits a single notice per turn", () => {
    const mapper = createAntigravityMapper({ root: ROOT });
    const big = "a".repeat(MAX_LINE_BYTES + 10);
    const out1 = mapper.feed(big);
    expect(out1.events).toEqual([
      { type: "notice", level: "warning", message: expect.stringContaining("too long to read") },
    ]);
    const out2 = mapper.feed(big);
    expect(out2.events).toEqual([]);
  });
});

describe("stream ending with no result or dangling tool", () => {
  it("closes cleanly with failed done when stream terminates mid-turn", () => {
    const { events } = run(fixture("synthetic-missing-result.jsonl"), { cancelled: false, exitCode: 0 });
    expect(types(events)).toContain("error");
    expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
    // Exactly one done event
    expect(events.filter((e) => e.type === "done")).toHaveLength(1);
  });
});

describe("hostile conversation id", () => {
  it("rejects conversation ids with traversal or command injection characters", () => {
    const lines = [
      JSON.stringify({ event: "init", conversation_id: "../../../etc/passwd", init: { model: "m", cwd: ROOT, agent: "caztor", tools: ["view_file"], permission_mode: "request-review" } }),
    ];
    const { events } = run(lines);
    expect(events.filter((e) => e.type === "session")).toHaveLength(0);
  });
});

describe("what real runs reported", () => {
  const result = (fields: Record<string, unknown>) => JSON.stringify({ event: "result", result: { conversation_id: SESSION_1, ...fields } });

  it("reads the error field of a failed result and reports a spent quota as rate_limited", () => {
    const message = "Individual quota reached. Please upgrade your subscription to increase your limits. Resets in 121h5m40s.";
    const { events } = run([result({ status: "ERROR", error: message, finished_reason: "error" })], { cancelled: false, exitCode: 1 });
    expect(events.filter((event) => event.type !== "session")).toEqual([
      { type: "error", code: "rate_limited", message },
      { type: "done", reason: "failed" },
    ]);
  });

  it("reports a spent quota in the error output as rate_limited, not as a sign-in problem", () => {
    const stderrTail = 'AGY_ERROR: {"short_error":"RESOURCE_EXHAUSTED (code 429): Individual quota reached.","error_code":429}';
    const { events } = run([], { cancelled: false, exitCode: 1, stderrTail });
    expect(events[0]).toMatchObject({ type: "error", code: "rate_limited" });
    expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
  });

  it("warns about denied actions when a turn ends in success", () => {
    const { events } = run([result({ status: "SUCCESS", response: "", denied_actions: [{ action: "read_file", display_name: "ReadFile" }] })], { cancelled: false, exitCode: 0 });
    expect(events).toContainEqual({
      type: "notice",
      level: "warning",
      message: "Antigravity was not allowed to do this, so its answer may be incomplete: ReadFile.",
    });
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });

  it("counts only this turn's usage when the result of a continued conversation is cumulative", () => {
    const step = JSON.stringify({ event: "step_update", step_update: { conversation_id: SESSION_1, step_index: 8, state: "DONE", step_type: "agent_response", text_delta: "Done.", usage: { input_tokens: 8522, output_tokens: 98 } } });
    const { events } = run([step, result({ status: "SUCCESS", response: "Done.", usage: { input_tokens: 31736, output_tokens: 722 } })], { cancelled: false, exitCode: 0 });
    expect(events.at(-1)).toEqual({ type: "done", reason: "completed", usage: { inputTokens: 8522, outputTokens: 98 } });
  });
});
