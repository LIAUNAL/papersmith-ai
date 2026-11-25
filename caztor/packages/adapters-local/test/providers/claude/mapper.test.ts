import { classifyError } from "../../../src/providers/claude/mapper.ts";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AgentEvent } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { createClaudeMapper, MAX_LINE_BYTES, MAX_MALFORMED_LINES } from "../../../src/providers/claude/mapper.ts";

const fixtures = fileURLToPath(new URL("./fixtures/", import.meta.url));
const fixture = (name: string): string[] => readFileSync(join(fixtures, name), "utf8").split("\n").filter((line) => line !== "");
const ROOT = "/work/project";
const SESSION = "11111111-2222-4333-8444-555555555555";

/** Feeds every line to a fresh mapper and returns everything it said. */
function run(lines: string[], finish?: { cancelled: boolean; stderrTail?: string }) {
  const mapper = createClaudeMapper({ root: ROOT });
  const events: AgentEvent[] = [];
  let init: ReturnType<typeof mapper.feed>["init"];
  let fatal = false;
  for (const line of lines) {
    const out = mapper.feed(line);
    events.push(...out.events);
    init ??= out.init;
    fatal ||= out.fatal;
    if (out.fatal) break;
  }
  if (finish !== undefined) events.push(...mapper.finish(finish));
  return { events, init, fatal, mapper };
}

const line = (value: unknown) => JSON.stringify(value);
const stream = (event: unknown, extra: Record<string, unknown> = {}) => line({ type: "stream_event", event, session_id: SESSION, api_message_id: "msg_a", ...extra });
const types = (events: AgentEvent[]) => events.map((event) => event.type);

describe("the sanitized fixtures", () => {
  const names = readdirSync(fixtures).filter((name) => name.endsWith(".jsonl"));

  it("exist for the real turn and its variants", () => {
    expect(names).toEqual(["cancelled.jsonl", "edit-turn.jsonl", "error-auth.jsonl", "isolation-violation.jsonl", "permission-denied.jsonl", "rate-limited.jsonl", "resume.jsonl"]);
  });

  it.each(names)("%s is valid JSON lines holding nothing of the machine it came from", (name) => {
    const text = readFileSync(join(fixtures, name), "utf8");
    for (const entry of text.split("\n").filter((l) => l !== "")) expect(() => JSON.parse(entry)).not.toThrow();
    for (const forbidden of ["/home/", "claude-1000", "andres", "codegraph", "context7", "engram", "@gmail", "ANTHROPIC_API_KEY", "sk-ant"]) {
      expect(text.includes(forbidden), `${name} contains ${forbidden}`).toBe(false);
    }
  });
});

describe("a whole turn that edits a file", () => {
  const result = run(fixture("edit-turn.jsonl"));

  it("maps the session, the tools, the streamed text and the end with its cost", () => {
    expect(types(result.events)).toEqual([
      "session",
      "tool_start", "tool_update", "tool_end",
      "tool_start", "tool_update", "tool_end",
      "text_delta", "text_delta", "text_delta", "text",
      "done",
    ]);
    expect(result.events[0]).toEqual({ type: "session", sessionId: SESSION });
    expect(result.events[1]).toEqual({ type: "tool_start", toolId: "toolu_01", name: "Read", kind: "read" });
    expect(result.events[2]).toEqual({ type: "tool_update", toolId: "toolu_01", path: "main.tex" });
    expect(result.events[3]).toEqual({ type: "tool_end", toolId: "toolu_01", status: "done" });
    expect(result.events[4]).toEqual({ type: "tool_start", toolId: "toolu_02", name: "Edit", kind: "edit" });
    expect(result.events[5]).toEqual({ type: "tool_update", toolId: "toolu_02", path: "main.tex" });
    expect(result.events.at(-1)).toEqual({ type: "done", reason: "completed", usage: { inputTokens: 4606, outputTokens: 489, costUsd: 0.0123 } });
  });

  it("streams the text token by token and ends it with the whole text", () => {
    const deltas = result.events.filter((event) => event.type === "text_delta");
    expect(deltas.map((event) => (event.type === "text_delta" ? event.text : ""))).toEqual(["I changed line 3 of ", "`main.tex` from \"Hello world.\" ", "to \"Hi world.\"."]);
    const whole = result.events.find((event) => event.type === "text");
    expect(whole).toEqual({ type: "text", messageId: deltas[0] !== undefined && deltas[0].type === "text_delta" ? deltas[0].messageId : "", text: 'I changed line 3 of `main.tex` from "Hello world." to "Hi world.".' });
  });

  it("never shows the thinking or its signature", () => {
    expect(JSON.stringify(result.events)).not.toMatch(/thinking|signature|U0lHTkFUVVJF/i);
  });

  it("reports what system/init said about the tools and the servers", () => {
    expect(result.init).toEqual({ sessionId: SESSION, tools: ["Read", "Edit", "Write", "Glob", "Grep"], mcpServers: [] });
  });

  it("is complete: nothing more to say when the stream ends", () => {
    expect(result.mapper.finish({ cancelled: false })).toEqual([]);
  });
});

describe("the variants", () => {
  it("reports the tools and servers of an isolation violation", () => {
    const { init } = run(fixture("isolation-violation.jsonl"));
    expect(init?.tools).toContain("Bash");
    expect(init?.mcpServers).toEqual([{ name: "server-a", status: "connected" }]);
  });

  it("maps an authentication failure to one error and a failed done", () => {
    const { events } = run(fixture("error-auth.jsonl"));
    expect(events).toEqual([
      { type: "session", sessionId: SESSION },
      { type: "error", code: "auth", message: "Invalid API key · Please run /login" },
      { type: "done", reason: "failed", usage: { inputTokens: 4606, outputTokens: 489, costUsd: 0 } },
    ]);
  });

  it("maps a refused rate limit to one rate_limited error, not two", () => {
    const { events } = run(fixture("rate-limited.jsonl"));
    expect(events.filter((event) => event.type === "error")).toEqual([
      { type: "error", code: "rate_limited", message: "Claude Code reached its usage limit. It can be used again at 2023-11-14 23:13 UTC." },
    ]);
    expect(types(events).at(-1)).toBe("done");
    expect(events.filter((event) => event.type === "done")).toHaveLength(1);
  });

  it("turns permission denials into a warning that names the tools, before the done", () => {
    const { events } = run(fixture("permission-denied.jsonl"));
    const notice = events.find((event) => event.type === "notice");
    expect(notice).toEqual({ type: "notice", level: "warning", message: "Claude Code refused 1 tool request: Bash." });
    expect(events.indexOf(notice!)).toBe(events.length - 2);
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });

  it("cut short: a cancelled turn ends with one cancelled done, and an unexplained end is a failure with the error output", () => {
    const cancelled = run(fixture("cancelled.jsonl"), { cancelled: true });
    expect(cancelled.events.at(-1)).toEqual({ type: "done", reason: "cancelled" });
    expect(cancelled.events.filter((event) => event.type === "done")).toHaveLength(1);

    const cut = run(fixture("cancelled.jsonl"), { cancelled: false, stderrTail: "boom: out of memory" });
    expect(cut.events.slice(-2)).toEqual([
      { type: "error", code: "provider_error", message: "Claude Code stopped before it finished its answer.", detail: "boom: out of memory" },
      { type: "done", reason: "failed" },
    ]);
  });

  it("maps a resumed turn the same way", () => {
    const { events } = run(fixture("resume.jsonl"));
    expect(events[0]).toEqual({ type: "session", sessionId: SESSION });
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });
});

describe("single native events", () => {
  it("maps a text block start and a delta to a delta event with the message id", () => {
    const { events } = run([stream({ type: "content_block_start", index: 0, content_block: { type: "text", text: "" } }), stream({ type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "Hi" } })]);
    expect(events).toEqual([{ type: "session", sessionId: SESSION }, { type: "text_delta", messageId: "msg_a", text: "Hi" }]);
  });

  it("maps a whole assistant text block to an authoritative text event", () => {
    const { events } = run([line({ type: "assistant", session_id: SESSION, message: { id: "msg_b", content: [{ type: "text", text: "Whole." }] } })]);
    expect(events).toContainEqual({ type: "text", messageId: "msg_b", text: "Whole." });
  });

  it("starts a Write tool with the write kind and a path inside the project", () => {
    const { events } = run([
      stream({ type: "content_block_start", index: 1, content_block: { type: "tool_use", id: "t9", name: "Write", input: {} } }),
      stream({ type: "content_block_delta", index: 1, delta: { type: "input_json_delta", partial_json: `{"file_path":"${ROOT}/sections/` } }),
      stream({ type: "content_block_delta", index: 1, delta: { type: "input_json_delta", partial_json: `intro.tex","content":"x"}` } }),
      stream({ type: "content_block_stop", index: 1 }),
    ]);
    expect(events.slice(1)).toEqual([
      { type: "tool_start", toolId: "t9", name: "Write", kind: "write" },
      { type: "tool_update", toolId: "t9", path: "sections/intro.tex" },
    ]);
  });

  it.each([
    ["Glob", "search"],
    ["Grep", "search"],
    ["Bash", "command"],
    ["WebFetch", "other"],
  ])("gives the %s tool the %s kind", (name, kind) => {
    const { events } = run([stream({ type: "content_block_start", index: 0, content_block: { type: "tool_use", id: "t1", name, input: {} } })]);
    expect(events[1]).toEqual({ type: "tool_start", toolId: "t1", name, kind });
  });

  it("leaves out the path of a file outside the project, and of an input that is not JSON", () => {
    const outside = run([
      stream({ type: "content_block_start", index: 0, content_block: { type: "tool_use", id: "t1", name: "Edit", input: {} } }),
      stream({ type: "content_block_delta", index: 0, delta: { type: "input_json_delta", partial_json: '{"file_path":"/etc/passwd"}' } }),
      stream({ type: "content_block_stop", index: 0 }),
    ]);
    expect(types(outside.events)).toEqual(["session", "tool_start"]);
    const broken = run([
      stream({ type: "content_block_start", index: 0, content_block: { type: "tool_use", id: "t1", name: "Edit", input: {} } }),
      stream({ type: "content_block_delta", index: 0, delta: { type: "input_json_delta", partial_json: '{"file_path":' } }),
      stream({ type: "content_block_stop", index: 0 }),
    ]);
    expect(types(broken.events)).toEqual(["session", "tool_start"]);
  });

  it("does not collect an input that grows past the limit", () => {
    const big = "x".repeat(300_000);
    const lines = [stream({ type: "content_block_start", index: 0, content_block: { type: "tool_use", id: "t1", name: "Write", input: {} } })];
    for (let part = 0; part < 6; part += 1) lines.push(stream({ type: "content_block_delta", index: 0, delta: { type: "input_json_delta", partial_json: part === 0 ? `{"file_path":"${ROOT}/a.tex","content":"${big}` : big } }));
    lines.push(stream({ type: "content_block_stop", index: 0 }));
    expect(types(run(lines).events)).toEqual(["session", "tool_start"]);
  });

  it("ends a tool as failed, with a short summary, when its result is an error", () => {
    const { events } = run([line({ type: "user", session_id: SESSION, message: { content: [{ type: "tool_result", tool_use_id: "t1", is_error: true, content: "File not found" }] } })]);
    expect(events).toContainEqual({ type: "tool_end", toolId: "t1", status: "failed", summary: "File not found" });
  });

  it("reads the text of a tool error that comes as blocks", () => {
    const { events } = run([line({ type: "user", session_id: SESSION, message: { content: [{ type: "tool_result", tool_use_id: "t1", is_error: true, content: [{ type: "text", text: "No such file" }] }] } })]);
    expect(events).toContainEqual({ type: "tool_end", toolId: "t1", status: "failed", summary: "No such file" });
  });

  it.each([
    ["Invalid API key · Please run /login", "auth"],
    ["OAuth token has expired. Please run /login", "auth"],
    ["API Error: 429 rate limit exceeded", "rate_limited"],
    ["Claude usage limit reached", "rate_limited"],
    ["The model claude-x does not exist", "model_unavailable"],
    ["Request timed out", "timeout"],
    ["Something unexpected", "provider_error"],
  ])("maps the error result %j to %s", (message, code) => {
    const { events } = run([line({ type: "result", subtype: "success", is_error: true, result: message, session_id: SESSION, total_cost_usd: 0 })]);
    expect(events.filter((event) => event.type === "error")).toEqual([{ type: "error", code, message }]);
    expect(events.at(-1)).toEqual({ type: "done", reason: "failed", usage: { costUsd: 0 } });
  });

  it("warns, without an error, when the usage limit is close", () => {
    const { events } = run([line({ type: "rate_limit_event", session_id: SESSION, rate_limit_info: { status: "allowed_warning", rateLimitType: "five_hour" } })]);
    expect(events).toEqual([{ type: "session", sessionId: SESSION }, { type: "notice", level: "info", message: "Claude Code is close to its usage limit." }]);
  });
});

describe("lines that are not events", () => {
  it.each([
    ["an unknown type", line({ type: "future_thing", session_id: SESSION })],
    ["a status line", line({ type: "system", subtype: "status", status: "requesting", session_id: SESSION })],
    ["a hook line", line({ type: "system", subtype: "hook_started", session_id: SESSION })],
    ["thinking tokens", line({ type: "system", subtype: "thinking_tokens", session_id: SESSION })],
    ["a thinking delta", stream({ type: "content_block_delta", index: 0, delta: { type: "thinking_delta", thinking: "secret" } })],
    ["a signature delta", stream({ type: "content_block_delta", index: 0, delta: { type: "signature_delta", signature: "abc" } })],
    ["a message_stop", stream({ type: "message_stop" })],
    ["a JSON value that is not an object", "42"],
    ["an empty line", ""],
  ])("ignores %s", (_name, text) => {
    const { events, fatal } = run([text]);
    expect(events.filter((event) => event.type !== "session")).toEqual([]);
    expect(fatal).toBe(false);
  });

  it("strips terminal colors before reading a line", () => {
    const colored = `\u001b[32m${line({ type: "result", subtype: "success", is_error: false, result: "ok", session_id: SESSION })}\u001b[0m`;
    expect(run([colored]).events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });

  it("drops a line over the size limit without failing the turn", () => {
    const huge = line({ type: "stream_event", pad: "x".repeat(MAX_LINE_BYTES + 10) });
    const { events, fatal } = run([huge, line({ type: "result", subtype: "success", is_error: false, session_id: SESSION })]);
    expect(fatal).toBe(false);
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });

  it("says so once with a warning notice when lines are dropped for their size, however many are dropped", () => {
    const huge = line({ type: "stream_event", pad: "x".repeat(MAX_LINE_BYTES + 10) });
    const { events } = run([huge, huge, huge, line({ type: "result", subtype: "success", is_error: false, session_id: SESSION })]);
    const notices = events.filter((event) => event.type === "notice");
    expect(notices).toHaveLength(1);
    expect(notices[0]).toMatchObject({ level: "warning", message: expect.stringMatching(/too long|size limit/i) });
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });

  it("ends the turn with malformed_output after twenty unparseable lines in a row", () => {
    const bad = Array.from({ length: MAX_MALFORMED_LINES }, () => "this is not json {");
    const { events, fatal } = run(bad);
    expect(fatal).toBe(true);
    expect(events).toEqual([
      { type: "error", code: "malformed_output", message: "Claude Code sent output Caztor could not read." },
      { type: "done", reason: "failed" },
    ]);
  });

  it("does not count unparseable lines that a valid line interrupts", () => {
    const lines: string[] = [];
    for (let index = 0; index < 3 * (MAX_MALFORMED_LINES - 1); index += 1) lines.push(index % (MAX_MALFORMED_LINES - 1) === MAX_MALFORMED_LINES - 2 ? line({ type: "system", subtype: "status", session_id: SESSION }) : "garbage");
    const { fatal } = run(lines);
    expect(fatal).toBe(false);
  });

  it("says nothing after the done", () => {
    const done = line({ type: "result", subtype: "success", is_error: false, session_id: SESSION });
    const { events } = run([done, done, stream({ type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "late" } })]);
    expect(events.filter((event) => event.type === "done")).toHaveLength(1);
    expect(events.at(-1)?.type).toBe("done");
  });
});

describe("an error about the chosen model", () => {
  it("is read as an unavailable model, not as a provider failure", () => {
    expect(classifyError("There's an issue with the selected model (Model). It may not exist or you may not have access to it. Run --model to pick a different model.")).toBe("model_unavailable");
  });
});
