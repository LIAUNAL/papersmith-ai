import { readdirSync, readFileSync } from "node:fs";
import { homedir, userInfo } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AgentEvent } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { MAX_LINE_BYTES, MAX_MALFORMED_LINES } from "../../../src/providers/claude/mapper.ts";
import { createCodexMapper } from "../../../src/providers/codex/mapper.ts";

const fixtures = fileURLToPath(new URL("./fixtures/", import.meta.url));
const fixture = (name: string): string[] => readFileSync(join(fixtures, name), "utf8").split("\n").filter((line) => line !== "");
const ROOT = "/work/project";
const THREAD = "00000000-0000-4000-8000-000000000001";

function run(lines: string[], finish?: { cancelled: boolean; exitCode?: number | null; stderrTail?: string }) {
  const mapper = createCodexMapper({ root: ROOT });
  const events: AgentEvent[] = [];
  let fatal = false;
  let final = false;
  for (const line of lines) {
    const out = mapper.feed(line);
    events.push(...out.events);
    fatal ||= out.fatal;
    final ||= out.final === true;
    if (out.fatal) break;
  }
  if (finish !== undefined) events.push(...mapper.finish(finish));
  return { events, fatal, final, mapper };
}
const line = (value: unknown) => JSON.stringify(value);
const types = (events: AgentEvent[]) => events.map((event) => event.type);
const item = (kind: "item.started" | "item.completed", body: Record<string, unknown>) => line({ type: kind, item: body });

describe("the documentation-derived fixtures", () => {
  const names = readdirSync(fixtures).filter((name) => name.endsWith(".jsonl"));

  it("are named for what they are, and say in a README that none is a real capture", () => {
    expect(names).toEqual(["documented-edit-turn.jsonl", "documented-error-event.jsonl", "documented-legacy-item-type.jsonl", "documented-turn-failed.jsonl"]);
    const readme = readFileSync(join(fixtures, "README.md"), "utf8");
    expect(readme).toContain("documentation-derived");
    expect(readme).toContain("not installed");
  });

  it.each(names)("%s is valid JSON lines with nothing of the machine it was written on", (name) => {
    const text = readFileSync(join(fixtures, name), "utf8");
    const lines = text.split("\n").filter((l) => l !== "");
    expect(lines.length).toBeGreaterThan(2);
    for (const entry of lines) expect(() => JSON.parse(entry)).not.toThrow();
    for (const word of [homedir(), userInfo().username, "/home/", "claude-1000", "engram", "@gmail", "sk-"]) expect(text.includes(word), `${name} contains ${word}`).toBe(false);
  });
});

describe("a whole turn that edits a file", () => {
  const result = run(fixture("documented-edit-turn.jsonl"), { cancelled: false, exitCode: 0 });

  it("maps the thread, the command and the file change as tools, the message as text, and the end with usage", () => {
    expect(result.events).toEqual([
      { type: "session", sessionId: THREAD },
      { type: "tool_start", toolId: "item_0", name: "command", kind: "command" },
      { type: "tool_update", toolId: "item_0", title: "ls" },
      { type: "tool_end", toolId: "item_0", status: "done" },
      { type: "tool_start", toolId: "item_2", name: "file_change", kind: "edit", path: "main.tex" },
      { type: "tool_end", toolId: "item_2", status: "done" },
      { type: "text", messageId: "item_3", text: "Changed the title in main.tex." },
      { type: "done", reason: "completed", usage: { inputTokens: 24763, outputTokens: 122 } },
    ]);
  });

  it("never passes the reasoning on, and sends exactly one done, last", () => {
    expect(JSON.stringify(result.events)).not.toContain("Looking for the title");
    expect(result.events.filter((event) => event.type === "done")).toHaveLength(1);
  });

  it("says the turn is over once it completed, so a process that lingers is ended", () => {
    expect(result.final).toBe(true);
  });
});

describe("the older item_type key", () => {
  it("is read like type, and an assistant_message is a message", () => {
    const { events } = run(fixture("documented-legacy-item-type.jsonl"), { cancelled: false, exitCode: 0 });
    expect(events).toEqual([
      { type: "session", sessionId: THREAD },
      { type: "tool_start", toolId: "item_0", name: "command", kind: "command" },
      { type: "tool_update", toolId: "item_0", title: "ls" },
      { type: "tool_end", toolId: "item_0", status: "done" },
      { type: "text", messageId: "item_1", text: "Done." },
      { type: "done", reason: "completed", usage: { inputTokens: 100, outputTokens: 10 } },
    ]);
  });
});

describe("items", () => {
  it("reports a command that failed as a failed tool, with the exit code", () => {
    const { events } = run([item("item.started", { id: "c", type: "command_execution", command: "make", status: "in_progress" }), item("item.completed", { id: "c", type: "command_execution", command: "make", exit_code: 2, status: "failed" })]);
    expect(events.at(-1)).toEqual({ type: "tool_end", toolId: "c", status: "failed", summary: "Exit code 2" });
  });

  it("treats a command that ended with a non-zero exit but a completed status as done: running it was not a failure of the tool", () => {
    const { events } = run([item("item.completed", { id: "c", type: "command_execution", command: "grep x main.tex", exit_code: 1, status: "completed" })]);
    expect(events.at(-1)).toEqual({ type: "tool_end", toolId: "c", status: "done" });
  });

  it("starts a tool that only arrives completed, with the start first", () => {
    const { events } = run([item("item.completed", { id: "c", type: "command_execution", command: "ls", status: "completed" })]);
    expect(types(events)).toEqual(["tool_start", "tool_update", "tool_end"]);
  });

  it("shortens a long command to one line and strips escapes", () => {
    const { events } = run([item("item.started", { id: "c", type: "command_execution", command: `\u001b[1mecho\u001b[0m ${"x ".repeat(300)}\nnext`, status: "in_progress" })]);
    const update = events.find((event) => event.type === "tool_update");
    expect(update).toMatchObject({ type: "tool_update", toolId: "c" });
    const title = update?.type === "tool_update" ? (update.title ?? "") : "";
    expect(title.startsWith("echo x x")).toBe(true);
    expect(title.endsWith("...")).toBe(true);
    expect(title).not.toContain("\u001b");
    expect(title.length).toBe(203);
  });

  it.each([
    [[{ path: "/work/project/a.tex", kind: "add" }], "write", "a.tex"],
    [[{ path: "sections/b.tex", kind: "update" }, { path: "/work/project/a.tex", kind: "add" }], "edit", "sections/b.tex"],
    [[{ path: "/etc/passwd", kind: "update" }], "edit", undefined],
    [[{ path: "/work/project/../x.tex", kind: "update" }], "edit", undefined],
  ])("shows file changes %j as a %s tool with the path %s", (changes, kind, path) => {
    const { events } = run([item("item.completed", { id: "f", type: "file_change", changes, status: "completed" })]);
    expect(events[0]).toEqual({ type: "tool_start", toolId: "f", name: "file_change", kind, ...(path === undefined ? {} : { path }) });
    expect(events[1]).toEqual({ type: "tool_end", toolId: "f", status: "done" });
  });

  it("ends a file change that failed as failed", () => {
    const { events } = run([item("item.completed", { id: "f", type: "file_change", changes: [], status: "failed" })]);
    expect(events.at(-1)).toMatchObject({ type: "tool_end", toolId: "f", status: "failed" });
  });

  it("shows a web search and a tool of an MCP server as other tools, named for what they are", () => {
    const search = run([item("item.completed", { id: "w", type: "web_search", query: "latex siunitx", status: "completed" })]).events;
    expect(search).toEqual([
      { type: "tool_start", toolId: "w", name: "web_search", kind: "other" },
      { type: "tool_update", toolId: "w", title: "latex siunitx" },
      { type: "tool_end", toolId: "w", status: "done" },
    ]);
    const mcp = run([item("item.completed", { id: "m", type: "mcp_tool_call", server: "docs", tool: "lookup", status: "completed" })]).events;
    expect(mcp[0]).toEqual({ type: "tool_start", toolId: "m", name: "docs/lookup", kind: "other" });
  });

  it("ignores reasoning, plan updates and item types it does not know", () => {
    const { events } = run([
      item("item.completed", { id: "r", type: "reasoning", text: "secret thoughts" }),
      item("item.completed", { id: "p", type: "plan_update", items: [] }),
      item("item.completed", { id: "t", type: "todo_list", items: [] }),
      item("item.completed", { id: "z", type: "something_new" }),
      line({ type: "item.updated", item: { id: "u", type: "agent_message", text: "partial" } }),
    ]);
    expect(events).toEqual([]);
  });

  it("shows an error item as a warning notice", () => {
    const { events } = run([item("item.completed", { id: "e", type: "error", message: "The tool could not start." })]);
    expect(events).toEqual([{ type: "notice", level: "warning", message: "Codex reported: The tool could not start." }]);
  });

  it("skips an empty message and an item with no id, and keeps the thread id only once", () => {
    const { events } = run([
      item("item.completed", { id: "a", type: "agent_message", text: "" }),
      item("item.completed", { type: "agent_message", text: "no id" }),
      line({ type: "thread.started", thread_id: THREAD }),
      line({ type: "thread.started", thread_id: THREAD }),
    ]);
    expect(events).toEqual([{ type: "session", sessionId: THREAD }]);
  });
});

describe("the end of the turn", () => {
  it("fails with the message of turn.failed, as a sign-in problem when it is one", () => {
    const { events } = run(fixture("documented-turn-failed.jsonl"), { cancelled: false, exitCode: 1 });
    expect(events).toEqual([
      { type: "session", sessionId: THREAD },
      { type: "error", code: "auth", message: "Codex is not signed in. Run `codex login` in a terminal, then try again.", detail: "unexpected status 401 Unauthorized: Missing bearer or basic authentication in header" },
      { type: "done", reason: "failed" },
    ]);
  });

  it.each([
    ["Rate limit reached for requests", "rate_limited"],
    ["The model gpt-x does not exist", "model_unavailable"],
    ["something broke", "provider_error"],
  ])("maps the turn.failed text %j to %s", (message, code) => {
    const { events } = run([line({ type: "turn.failed", error: { message } })], { cancelled: false, exitCode: 1 });
    expect(events[0]).toMatchObject({ type: "error", code });
    expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
  });

  it("gives a readable message when the failure carries none", () => {
    const { events } = run([line({ type: "turn.failed" })], { cancelled: false, exitCode: 1 });
    expect(events[0]).toEqual({ type: "error", code: "provider_error", message: "Codex reported an error." });
  });

  it("keeps an error event that was followed by a completed turn as a warning, because the CLI went on", () => {
    const { events } = run(fixture("documented-error-event.jsonl"), { cancelled: false, exitCode: 0 });
    expect(events).toEqual([
      { type: "session", sessionId: THREAD },
      { type: "text", messageId: "item_0", text: "Done after a retry." },
      { type: "notice", level: "warning", message: "Codex reported: stream error: rate limit reached; retrying 1/5" },
      { type: "done", reason: "completed", usage: { inputTokens: 5, outputTokens: 2 } },
    ]);
  });

  it("fails with an error event when the turn never completed", () => {
    const { events } = run([line({ type: "error", message: "stream closed before response.completed" })], { cancelled: false, exitCode: 1 });
    expect(events).toEqual([
      { type: "error", code: "provider_error", message: "stream closed before response.completed" },
      { type: "done", reason: "failed" },
    ]);
  });

  it("fails with the end of the error output when the process ends with nothing", () => {
    const { events } = run([], { cancelled: false, exitCode: 1, stderrTail: "no such option: --foo\n" });
    expect(events).toEqual([
      { type: "error", code: "provider_error", message: "Codex stopped before it finished its answer.", detail: "no such option: --foo" },
      { type: "done", reason: "failed" },
    ]);
  });

  it("completes without usage when the CLI sends none", () => {
    const { events } = run([line({ type: "turn.completed" })]);
    expect(events).toEqual([{ type: "done", reason: "completed" }]);
  });

  it("ends cancelled, with no error, after a stop", () => {
    const { events } = run([line({ type: "turn.failed", error: { message: "aborted" } })], { cancelled: true, exitCode: null });
    expect(events).toEqual([{ type: "done", reason: "cancelled" }]);
  });

  it("does not finish twice", () => {
    const result = run([line({ type: "turn.completed" })], { cancelled: false, exitCode: 0 });
    expect(result.mapper.finish({ cancelled: false, exitCode: 0 })).toEqual([]);
    expect(result.mapper.feed(item("item.completed", { id: "x", type: "agent_message", text: "late" })).events).toEqual([]);
  });
});

describe("a stream that cannot be trusted", () => {
  it("ignores unknown event types and lines that are not objects", () => {
    expect(run([line({ type: "mystery" }), "[1]", "7", line({ type: "turn.started" })]).events).toEqual([]);
  });

  it("ends the turn failed after a run of unreadable lines, and ignores a single one", () => {
    expect(run([...Array.from({ length: MAX_MALFORMED_LINES - 1 }, () => "nope"), line({ type: "turn.started" }), ...Array.from({ length: MAX_MALFORMED_LINES - 1 }, () => "nope")]).fatal).toBe(false);
    const result = run(Array.from({ length: MAX_MALFORMED_LINES }, () => "garbage"));
    expect(result.fatal).toBe(true);
    expect(result.events).toEqual([
      { type: "error", code: "malformed_output", message: "Codex sent output Caztor could not read." },
      { type: "done", reason: "failed" },
    ]);
  });

  it("strips terminal escapes before it reads a line", () => {
    expect(run([`\u001b[32m${line({ type: "thread.started", thread_id: THREAD })}\u001b[0m`]).events).toEqual([{ type: "session", sessionId: THREAD }]);
  });

  it("skips a line over the size limit with one warning for the turn", () => {
    const mapper = createCodexMapper({ root: ROOT });
    expect(mapper.feed("x".repeat(MAX_LINE_BYTES + 1)).events).toEqual([{ type: "notice", level: "warning", message: "Codex sent a line that was too long to read, so Caztor skipped it. Some of its output may be missing." }]);
    expect(mapper.feed("y".repeat(MAX_LINE_BYTES + 1)).events).toEqual([]);
  });
});
