import { readdirSync, readFileSync } from "node:fs";
import { homedir, userInfo } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AgentEvent } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { createPiMapper, PI_LOGIN_HINT, type PiToolReport } from "../../../src/providers/pi/mapper.ts";
import { MAX_LINE_BYTES, MAX_MALFORMED_LINES } from "../../../src/providers/claude/mapper.ts";

const fixtures = fileURLToPath(new URL("./fixtures/", import.meta.url));
const fixture = (name: string): string[] => readFileSync(join(fixtures, name), "utf8").split("\n").filter((line) => line !== "");
const ROOT = "/work/project";
const SESSION_1 = "00000000-0000-4000-8000-000000000001";

function run(lines: string[], finish?: { cancelled: boolean; exitCode?: number | null; stderrTail?: string }) {
  const mapper = createPiMapper({ root: ROOT });
  const events: AgentEvent[] = [];
  const tools: PiToolReport[] = [];
  let fatal = false;
  let final = false;
  for (const line of lines) {
    const out = mapper.feed(line);
    events.push(...out.events);
    if (out.tool !== undefined) tools.push(out.tool);
    fatal ||= out.fatal;
    final ||= out.final === true;
    if (out.fatal) break;
  }
  if (finish !== undefined) events.push(...mapper.finish(finish));
  return { events, tools, fatal, final };
}

const types = (events: AgentEvent[]) => events.map((event) => event.type);
const line = (record: unknown) => JSON.stringify(record);

describe("the synthetic fixtures", () => {
  it("are all labelled synthetic and listed in the README", () => {
    const readme = readFileSync(join(fixtures, "README.md"), "utf8");
    for (const name of readdirSync(fixtures).filter((file) => file.endsWith(".jsonl"))) {
      expect(name.startsWith("synthetic-"), name).toBe(true);
      expect(readme, name).toContain(`\`${name}\``);
    }
  });

  it("hold no home path, user name or real session id", () => {
    for (const name of readdirSync(fixtures)) {
      const text = readFileSync(join(fixtures, name), "utf8");
      expect(text, name).not.toContain(homedir());
      expect(text, name).not.toContain(userInfo().username);
      for (const id of text.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g) ?? []) expect(id, name).toBe(SESSION_1);
    }
  });
});

describe("the Pi mapper", () => {
  it("maps a whole turn that reads, edits and answers", () => {
    const { events, tools, final } = run(fixture("synthetic-edit-turn.jsonl"));
    expect(events[0]).toEqual({ type: "session", sessionId: SESSION_1 });
    expect(events.filter((event) => event.type === "tool_start")).toEqual([
      { type: "tool_start", toolId: "tool_1", name: "read", kind: "read", path: "main.tex" },
      { type: "tool_start", toolId: "tool_2", name: "edit", kind: "edit", path: "main.tex" },
    ]);
    expect(events.filter((event) => event.type === "tool_end")).toEqual([
      { type: "tool_end", toolId: "tool_1", status: "done" },
      { type: "tool_end", toolId: "tool_2", status: "done" },
    ]);
    const texts = events.filter((event) => event.type === "text");
    expect(texts).toEqual([
      { type: "text", messageId: "msg_1", text: "I will read main.tex first." },
      { type: "text", messageId: "msg_3", text: "I changed cat to dog in main.tex." },
    ]);
    const deltas = events.flatMap((event) => (event.type === "text_delta" && event.messageId === "msg_3" ? [event.text] : []));
    expect(deltas.join("")).toBe("I changed cat to dog in main.tex.");
    expect(new Set(tools.map((tool) => tool.name))).toEqual(new Set(["read", "edit"]));
    expect(events.at(-1)).toEqual({ type: "done", reason: "completed", usage: { inputTokens: 3900, outputTokens: 105 } });
    expect(types(events).filter((type) => type === "done")).toHaveLength(1);
    expect(final).toBe(true);
  });

  it("reports bash to the guard as soon as the call starts", () => {
    const { tools } = run(fixture("synthetic-disallowed-tool.jsonl"));
    expect(tools[0]).toEqual({ name: "bash" });
  });

  it("reports a call whose name changes, or has none, as unnamed", () => {
    const start = line({ type: "message_update", assistantMessageEvent: { type: "toolcall_start", id: "c1", toolName: "read" } });
    const end = line({ type: "message_update", assistantMessageEvent: { type: "toolcall_end", toolCall: { id: "c1", name: "bash" } } });
    expect(run([start, end]).tools).toEqual([{ name: "read" }, { name: "" }]);
    expect(run([line({ type: "tool_execution_start", toolCallId: "c2", args: {} })]).tools).toEqual([{ name: "" }]);
    expect(run([line({ type: "message_update", assistantMessageEvent: { type: "servertool_call" } })]).tools).toEqual([{ name: "" }]);
    expect(run([line({ type: "remote_tool_started" })]).tools).toEqual([{ name: "" }]);
  });

  it("ignores thinking, turn and queue events", () => {
    const { events, tools } = run([
      line({ type: "message_update", assistantMessageEvent: { type: "thinking_delta", delta: "secret plan" } }),
      line({ type: "turn_start" }),
      line({ type: "queue_update", steering: [], followUp: [] }),
    ]);
    expect(events).toEqual([]);
    expect(tools).toEqual([]);
  });

  it("ends with a rate limit when every retry failed, though the CLI exits 0", () => {
    const { events } = run(fixture("synthetic-rate-limit.jsonl"), { cancelled: false, exitCode: 0, stderrTail: "" });
    expect(events.slice(-2)).toEqual([
      { type: "error", code: "rate_limited", message: "429 Too Many Requests: rate limit exceeded after 2 retries" },
      { type: "done", reason: "failed" },
    ]);
    expect(types(events).filter((type) => type === "done")).toHaveLength(1);
  });

  it("ends failed when the response failed, though the CLI exits 0", () => {
    const { events } = run(fixture("synthetic-failed-response.jsonl"), { cancelled: false, exitCode: 0, stderrTail: "" });
    expect(events.slice(-2)).toEqual([
      { type: "error", code: "provider_error", message: "400 invalid_request_error: prompt is too long" },
      { type: "done", reason: "failed" },
    ]);
  });

  it("completes when a retry succeeds after an overloaded attempt", () => {
    const { events } = run(fixture("synthetic-retry-success.jsonl"));
    expect(events.some((event) => event.type === "error")).toBe(false);
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });

  it("gives the login hint for a response that failed for its key", () => {
    const { events } = run([line({ type: "message_end", message: { role: "assistant", content: [], stopReason: "error", errorMessage: "401 authentication_error: invalid x-api-key" } }), line({ type: "agent_settled", aborted: false })]);
    expect(events).toEqual([
      { type: "error", code: "auth", message: PI_LOGIN_HINT, detail: "401 authentication_error: invalid x-api-key" },
      { type: "done", reason: "failed" },
    ]);
  });

  it("warns when the answer was cut at the output limit, and still completes", () => {
    const { events } = run([line({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "Half" }], stopReason: "length" } }), line({ type: "agent_settled", aborted: false })]);
    expect(types(events)).toEqual(["text", "notice", "done"]);
    expect(events.at(-1)).toEqual({ type: "done", reason: "completed" });
  });

  it("treats 'not signed in' on exit 1 as an auth error with the login hint", () => {
    const { events } = run([], { cancelled: false, exitCode: 1, stderrTail: "No models available. Use /login to log into a provider via OAuth or API key. See:\n  docs/providers.md\n" });
    expect(events).toEqual([{ type: "error", code: "auth", message: PI_LOGIN_HINT }, { type: "done", reason: "failed" }]);
  });

  it("treats an unknown model on exit 1 as model_unavailable with Pi's message", () => {
    const { events } = run([], { cancelled: false, exitCode: 1, stderrTail: 'Model "nowhere/x" not found. Use --list-models to see available models.\n' });
    expect(events).toEqual([
      { type: "error", code: "model_unavailable", message: 'Model "nowhere/x" not found. Use --list-models to see available models.' },
      { type: "done", reason: "failed" },
    ]);
  });

  it("fails a stream that stops before it settles, closing open tools", () => {
    const started = [
      line({ type: "tool_execution_start", toolCallId: "c1", toolName: "read", args: { path: "a.tex" } }),
    ];
    const { events } = run([...fixture("synthetic-missing-settled.jsonl"), ...started], { cancelled: false, exitCode: 1, stderrTail: "crash" });
    expect(events.slice(-3)).toEqual([
      { type: "tool_end", toolId: "tool_1", status: "failed" },
      { type: "error", code: "provider_error", message: "Pi stopped before it finished its answer.", detail: "crash" },
      { type: "done", reason: "failed" },
    ]);
  });

  it("ends a stopped turn cancelled", () => {
    const { events } = run(fixture("synthetic-missing-settled.jsonl"), { cancelled: true, exitCode: null, stderrTail: "" });
    expect(events.at(-1)).toEqual({ type: "done", reason: "cancelled" });
  });

  it(`gives up after ${MAX_MALFORMED_LINES} unreadable lines`, () => {
    const { events, fatal } = run(fixture("synthetic-malformed-line.jsonl"));
    expect(fatal).toBe(true);
    expect(events).toEqual([{ type: "error", code: "malformed_output", message: "Pi sent output Caztor could not read." }, { type: "done", reason: "failed" }]);
  });

  it("drops an oversized line with one notice per turn", () => {
    const big = `{"type":"message_update","x":"${"a".repeat(MAX_LINE_BYTES)}"}`;
    const { events } = run([big, big]);
    expect(events).toEqual([{ type: "notice", level: "warning", message: expect.stringContaining("too long") }]);
  });

  it("accepts only a UUID session id, and keeps a path outside the project off the card", () => {
    expect(run([line({ type: "session", version: 3, id: "../../etc" })]).events).toEqual([]);
    const outside = run([line({ type: "tool_execution_start", toolCallId: "c1", toolName: "read", args: { path: "/etc/passwd" } })]).events;
    expect(outside).toEqual([{ type: "tool_start", toolId: "tool_1", name: "read", kind: "read" }]);
  });

  it("does not split a line on a Unicode line separator inside a string", () => {
    const text = "one two";
    const { events } = run([line({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: text } })]);
    expect(events).toEqual([{ type: "text_delta", messageId: "msg_1", text }]);
  });
});
