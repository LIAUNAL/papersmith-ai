import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir, userInfo } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AgentEvent } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { MAX_LINE_BYTES, MAX_MALFORMED_LINES } from "../../../src/providers/claude/mapper.ts";
import { createOpencodeMapper, type OpencodeToolUse } from "../../../src/providers/opencode/mapper.ts";

const fixtures = fileURLToPath(new URL("./fixtures/", import.meta.url));
const RAW = fileURLToPath(new URL("../../../../../openspec/changes/caztor-mvp/spike-raw/", import.meta.url));
const fixture = (name: string): string[] => readFileSync(join(fixtures, name), "utf8").split("\n").filter((line) => line !== "");
const ROOT = "/work/project";
const SESSION = "ses_FIXTURE0000SESSION";

/** Feeds every line to a fresh mapper and returns everything it said. */
function run(lines: string[], finish?: { cancelled: boolean; exitCode?: number | null; stderrTail?: string }) {
  const mapper = createOpencodeMapper({ root: ROOT });
  const events: AgentEvent[] = [];
  const tools: OpencodeToolUse[] = [];
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

const line = (value: unknown) => JSON.stringify(value);
const types = (events: AgentEvent[]) => events.map((event) => event.type);
const step = (reason: string, tokens = { input: 10, output: 5, reasoning: 0, cache: { read: 0, write: 0 } }, cost = 0) =>
  line({ type: "step_finish", sessionID: SESSION, part: { type: "step-finish", reason, tokens, cost } });

describe("the sanitized fixtures", () => {
  const names = readdirSync(fixtures).filter((name) => name.endsWith(".jsonl"));

  it("exist for the real turn, the two real errors and the synthetic variants", () => {
    expect(names).toEqual([
      "edit-turn.jsonl",
      "error-free-tier.jsonl",
      "error-model-rejected.jsonl",
      "synthetic-auth-401.jsonl",
      "synthetic-denied-bash.jsonl",
      "synthetic-isolation-violation.jsonl",
      "synthetic-rate-limit-429.jsonl",
    ]);
  });

  /** What the raw captures hold that must never reach a committed file: their ids. The captures are git-ignored. */
  const rawIds = (): string[] => {
    if (!existsSync(RAW)) return [];
    return readdirSync(RAW)
      .filter((name) => name.startsWith("opencode-") && name.endsWith(".jsonl"))
      .flatMap((name) => readFileSync(join(RAW, name), "utf8").match(/\b(?:ses|prt|msg)_[A-Za-z0-9]{8,}|\bcall_[A-Za-z0-9]{8,}|\bfc_[A-Za-z0-9]{8,}/g) ?? []);
  };

  it.each(names)("%s is valid JSON lines holding nothing of the machine it came from", (name) => {
    const text = readFileSync(join(fixtures, name), "utf8");
    const lines = text.split("\n").filter((l) => l !== "");
    expect(lines.length).toBeGreaterThan(0);
    for (const entry of lines) expect(() => JSON.parse(entry)).not.toThrow();
    const forbidden = [
      homedir(),
      userInfo().username,
      "/home/",
      "claude-1000",
      "engram",
      "codegraph",
      "context7",
      "gentle",
      "ollama",
      "@gmail",
      "x-opencode-log-id",
      "cf-ray",
      "set-cookie",
      "x-oai-request-id",
      ...rawIds(),
    ];
    for (const word of forbidden) expect(text.includes(word), `${name} contains ${word}`).toBe(false);
  });

  it("the check can see the raw ids when the captures are there", () => {
    if (!existsSync(RAW)) return;
    expect(rawIds().length).toBeGreaterThan(5);
  });
});

describe("a whole turn that edits a file", () => {
  const result = run(fixture("edit-turn.jsonl"), { cancelled: false, exitCode: 0 });

  it("maps the session, the finished tools, the whole text block and the end with the summed usage", () => {
    expect(types(result.events)).toEqual(["session", "tool_start", "tool_end", "tool_start", "tool_end", "text", "done"]);
    expect(result.events[0]).toEqual({ type: "session", sessionId: SESSION });
    expect(result.events[1]).toEqual({ type: "tool_start", toolId: "call_FIXTURE0003", name: "read", kind: "read", path: "main.tex" });
    expect(result.events[2]).toEqual({ type: "tool_end", toolId: "call_FIXTURE0003", status: "done" });
    expect(result.events[3]).toEqual({ type: "tool_start", toolId: "call_FIXTURE0009", name: "apply_patch", kind: "edit", path: "main.tex" });
    expect(result.events[5]).toEqual({ type: "text", messageId: "msg_FIXTURE0014", text: "Changed `Hello world.` to `Hi world.` in `main.tex` CAZTOR-AGENT-ACTIVE" });
    // Per step: input + cache read and write; output includes the reasoning tokens. Three steps.
    expect(result.events.at(-1)).toEqual({ type: "done", reason: "completed", usage: { inputTokens: 18058 + 526 + 17920 + 683 + 17920, outputTokens: 102 + 44 + 91 + 30 + 156, costUsd: 0 } });
  });

  it("reports each tool once it finished, with the names the isolation check reads", () => {
    expect(result.tools).toEqual([
      { name: "read", status: "completed" },
      { name: "apply_patch", status: "completed" },
    ]);
  });

  it("sends exactly one done, last, and no text delta", () => {
    expect(result.events.filter((event) => event.type === "done")).toHaveLength(1);
    expect(types(result.events)).not.toContain("text_delta");
  });
});

describe("tools", () => {
  const tool = (name: string, state: Record<string, unknown>, extra: Record<string, unknown> = {}) =>
    line({ type: "tool_use", sessionID: SESSION, part: { type: "tool", tool: name, callID: "c1", state, ...extra } });

  it.each([
    ["read", "read"],
    ["edit", "edit"],
    ["multiedit", "edit"],
    ["apply_patch", "edit"],
    ["write", "write"],
    ["glob", "search"],
    ["grep", "search"],
    ["list", "search"],
    ["bash", "command"],
    ["something_else", "other"],
  ])("gives %s the kind %s", (name, kind) => {
    const { events } = run([tool(name, { status: "completed", input: {} })]);
    expect(events).toContainEqual({ type: "tool_start", toolId: "c1", name, kind });
  });

  it("takes the path hint from the input, relative to the project, and drops one that points outside it", () => {
    const inside = run([tool("edit", { status: "completed", input: { filePath: "/work/project/sections/intro.tex" } })]).events[1];
    expect(inside).toMatchObject({ type: "tool_start", path: "sections/intro.tex" });
    const relative = run([tool("write", { status: "completed", input: { filePath: "notes.tex" } })]).events[1];
    expect(relative).toMatchObject({ type: "tool_start", path: "notes.tex" });
    for (const filePath of ["/etc/passwd", "../x.tex", "/work/project/../x.tex", "/work/projectile/a.tex"]) {
      const out = run([tool("edit", { status: "completed", input: { filePath } })]).events[1];
      expect(out, filePath).toEqual({ type: "tool_start", toolId: "c1", name: "edit", kind: "edit" });
    }
  });

  it("takes the path of a patch from the files it changed, the first one", () => {
    const out = run([tool("apply_patch", { status: "completed", input: {}, metadata: { files: [{ filePath: "/work/project/a.tex" }, { filePath: "/work/project/b.tex" }] } })]).events[1];
    expect(out).toMatchObject({ type: "tool_start", path: "a.tex" });
  });

  it("ends a tool the CLI refused as failed, with the reason, and goes on", () => {
    const result = run(fixture("synthetic-denied-bash.jsonl"), { cancelled: false, exitCode: 0 });
    expect(result.events).toContainEqual({ type: "tool_start", toolId: "call_FIXTURE0001", name: "bash", kind: "command" });
    expect(result.events).toContainEqual({
      type: "tool_end",
      toolId: "call_FIXTURE0001",
      status: "failed",
      summary: "The user has specified a rule which prevents you from using this specific tool call.",
    });
    expect(result.tools).toEqual([{ name: "bash", status: "error" }]);
    expect(result.events).toContainEqual({ type: "text", messageId: "msg_FIXTURE0003", text: "I cannot run commands here." });
    expect(result.events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });

  it("says nothing about a tool that has not finished", () => {
    const out = run([tool("edit", { status: "running", input: {} }), tool("edit", { status: "pending", input: {} })]);
    expect(out.events).toEqual([{ type: "session", sessionId: SESSION }]);
    expect(out.tools).toEqual([]);
  });

  it("strips terminal escapes from a failure reason and shortens it", () => {
    const events = run([tool("edit", { status: "error", input: {}, error: `\u001b[31m${"bad ".repeat(100)}\u001b[0m` })]).events;
    const end = events.find((event) => event.type === "tool_end");
    expect(end).toMatchObject({ status: "failed" });
    const summary = end?.type === "tool_end" ? (end.summary ?? "") : "";
    expect(summary.startsWith("bad bad bad")).toBe(true);
    expect(summary.endsWith("...")).toBe(true);
    expect(summary).not.toContain("\u001b");
    expect(summary.length).toBe(203);
  });
});

describe("the end of the turn", () => {
  const text = (value: string) => line({ type: "text", sessionID: SESSION, part: { type: "text", messageID: "m1", text: value } });

  it("sums the usage of every step and rounds nothing", () => {
    const { events } = run(
      [step("tool-calls", { input: 100, output: 10, reasoning: 5, cache: { read: 50, write: 20 } }, 0.25), step("stop", { input: 3, output: 2, reasoning: 0, cache: { read: 7, write: 0 } }, 0.125)],
      { cancelled: false, exitCode: 0 },
    );
    expect(events.at(-1)).toEqual({ type: "done", reason: "completed", usage: { inputTokens: 100 + 50 + 20 + 3 + 7, outputTokens: 10 + 5 + 2, costUsd: 0.375 } });
  });

  it("completes when the final step finished, even if the process had to be ended afterwards", () => {
    const { events } = run([text("Done"), step("stop")], { cancelled: false, exitCode: null });
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });

  it("completes on a clean exit after a step that asked for tools", () => {
    const { events } = run([step("tool-calls")], { cancelled: false, exitCode: 0 });
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });

  it("warns when the answer was cut short, naming the reason", () => {
    const { events } = run([step("length")], { cancelled: false, exitCode: 0 });
    expect(events).toContainEqual({ type: "notice", level: "warning", message: "opencode ended its answer early (reason: length)." });
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });

  it("fails with the end of the error output when the process ends with no step at all", () => {
    const { events } = run([], { cancelled: false, exitCode: 1, stderrTail: "boom: it broke\n" });
    expect(events).toEqual([
      { type: "error", code: "provider_error", message: "opencode stopped before it finished its answer.", detail: "boom: it broke" },
      { type: "done", reason: "failed" },
    ]);
  });

  it("fails on a clean exit that produced nothing, and on a signal after unfinished work", () => {
    expect(run([text("half")], { cancelled: false, exitCode: 0 }).events.at(-1)).toEqual({ type: "done", reason: "failed" });
    expect(run([step("tool-calls")], { cancelled: false, exitCode: null }).events.at(-1)).toEqual({ type: "done", reason: "failed" });
  });

  it("ends cancelled, with no error, after a stop", () => {
    const { events } = run([text("half")], { cancelled: true, exitCode: null });
    expect(events.slice(-1)).toEqual([{ type: "done", reason: "cancelled" }]);
    expect(types(events)).not.toContain("error");
  });

  it("does not finish twice", () => {
    const result = run([step("stop")], { cancelled: false, exitCode: 0 });
    expect(result.mapper.finish({ cancelled: false, exitCode: 0 })).toEqual([]);
    expect(result.mapper.feed(text("late")).events).toEqual([]);
  });
});

describe("errors", () => {
  const errorEvent = (data: Record<string, unknown>, name = "APIError") => line({ type: "error", sessionID: SESSION, error: { name, data } });
  const finish = { cancelled: false, exitCode: 1 } as const;

  it("tells the user to pick another model when the free tier refuses a headless call (real capture)", () => {
    const { events } = run(fixture("error-free-tier.jsonl"), finish);
    expect(events).toEqual([
      { type: "session", sessionId: SESSION },
      {
        type: "error",
        code: "model_unavailable",
        message: "opencode's free models cannot be used from Caztor. Choose another model in the model setting, one from a provider you are signed in to.",
        detail: "OpenCode's free tier can only be used from within OpenCode",
      },
      { type: "done", reason: "failed" },
    ]);
  });

  it("tells the user to pick another model when the provider rejects it (real capture)", () => {
    const { events } = run(fixture("error-model-rejected.jsonl"), finish);
    expect(events[1]).toMatchObject({
      type: "error",
      code: "model_unavailable",
      message: "The provider does not accept this model with your account. Choose another model in the model setting.",
    });
    expect(events[1]).toMatchObject({ detail: expect.stringContaining("'gpt-5.4-mini' model is not supported") });
    expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
  });

  it("maps 401 to auth", () => {
    const { events } = run(fixture("synthetic-auth-401.jsonl"), finish);
    expect(events[1]).toMatchObject({ type: "error", code: "auth", message: expect.stringContaining("opencode providers login") });
  });

  it("maps 429 to rate_limited", () => {
    const { events } = run(fixture("synthetic-rate-limit-429.jsonl"), finish);
    expect(events[1]).toMatchObject({ type: "error", code: "rate_limited" });
  });

  it.each([
    [{ message: "Forbidden", statusCode: 403 }, "APIError", "auth"],
    [{ message: "model gpt-x not found", statusCode: 404 }, "APIError", "model_unavailable"],
    [{ message: "Model not found: openai/nope" }, "ProviderModelNotFoundError", "model_unavailable"],
    [{ message: "bad credentials" }, "ProviderAuthError", "auth"],
    [{ message: "The request timed out", statusCode: 408 }, "APIError", "timeout"],
    [{ message: "Internal error", statusCode: 500 }, "APIError", "provider_error"],
    [{ message: "something odd" }, "UnknownError", "provider_error"],
  ])("maps %j with name %s to %s", (data, name, code) => {
    const { events } = run([errorEvent(data, name)], finish);
    expect(events[1]).toMatchObject({ type: "error", code });
  });

  it("gives a readable message when the error carries none", () => {
    const { events } = run([line({ type: "error", sessionID: SESSION, error: { name: "Weird" } })], finish);
    expect(events[1]).toMatchObject({ type: "error", code: "provider_error", message: "opencode reported an error." });
  });

  it("reports one error even if the CLI sends two, and a done that is failed", () => {
    const { events } = run([errorEvent({ message: "one", statusCode: 500 }), errorEvent({ message: "two", statusCode: 500 })], finish);
    expect(events.filter((event) => event.type === "error")).toHaveLength(1);
    expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
  });

  it("does not report the error of a turn that was stopped", () => {
    const { events } = run([errorEvent({ message: "aborted", statusCode: 500 })], { cancelled: true, exitCode: null });
    expect(types(events)).toEqual(["session", "done"]);
    expect(events.at(-1)).toEqual({ type: "done", reason: "cancelled" });
  });
});

describe("a stream that cannot be trusted", () => {
  it("ignores unknown event types and lines that are not objects, and keeps the session once", () => {
    const { events } = run([line({ type: "mystery", sessionID: SESSION }), "[1,2]", "42", line({ type: "step_start", sessionID: SESSION })]);
    expect(events).toEqual([{ type: "session", sessionId: SESSION }]);
  });

  it("ignores a single unreadable line and counts only the lines in a row", () => {
    const lines = [...Array.from({ length: MAX_MALFORMED_LINES - 1 }, () => "not json"), line({ type: "step_start", sessionID: SESSION }), ...Array.from({ length: MAX_MALFORMED_LINES - 1 }, () => "{oops")];
    const result = run(lines);
    expect(result.fatal).toBe(false);
    expect(types(result.events)).toEqual(["session"]);
  });

  it("ends the turn failed after a run of unreadable lines", () => {
    const result = run(Array.from({ length: MAX_MALFORMED_LINES }, () => "garbage"));
    expect(result.fatal).toBe(true);
    expect(result.events).toEqual([
      { type: "error", code: "malformed_output", message: "opencode sent output Caztor could not read." },
      { type: "done", reason: "failed" },
    ]);
  });

  it("strips terminal escapes before it reads a line", () => {
    const { events } = run([`\u001b[32m${line({ type: "step_start", sessionID: SESSION })}\u001b[0m`]);
    expect(events).toEqual([{ type: "session", sessionId: SESSION }]);
  });

  it("skips a line over the size limit with one warning for the turn", () => {
    const mapper = createOpencodeMapper({ root: ROOT });
    const first = mapper.feed("x".repeat(MAX_LINE_BYTES + 1));
    expect(first.events).toEqual([{ type: "notice", level: "warning", message: "opencode sent a line that was too long to read, so Caztor skipped it. Some of its output may be missing." }]);
    expect(mapper.feed("y".repeat(MAX_LINE_BYTES + 1)).events).toEqual([]);
    expect(mapper.oversize()).toEqual([]);
  });
});
