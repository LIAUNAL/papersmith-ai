import type { AgentEvent } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { drive, type DrivenMapper, type DrivenOutcome } from "../../src/providers/drive.ts";
import { FakeClock } from "../fakes/fake-clock.ts";
import { FakeSpawner, splitBytes, type ChildScript } from "../fakes/fake-spawner.ts";

const KEY = "sk-planted-secret-key-123456";
const ok = { code: 0, signal: null };

/** A mapper that shows every line as text, and reports the stderr tail the way a provider mapper does on a failed exit. */
function echoMapper(): DrivenMapper<DrivenOutcome> {
  return {
    feed: (line) => ({
      events: line === "BOOM" ? [{ type: "tool_start", toolId: `t-${KEY}`, name: "read", kind: "read", path: `/p/${KEY}.tex` }] : [{ type: "text", messageId: "m1", text: line }],
      fatal: false,
    }),
    oversize: () => [],
    finish: ({ exitCode, stderrTail }) =>
      exitCode === 0
        ? [{ type: "done", reason: "completed" }]
        : [{ type: "error", code: "provider_error", message: `The CLI failed: ${stderrTail}`, detail: stderrTail }, { type: "done", reason: "failed" }],
  };
}

describe("a last line with no newline", () => {
  it("goes through the same check as the others", async () => {
    const { events } = await run({ stdout: ["forbidden"], exit: ok }, { check: () => "not allowed" });
    expect(events).toContainEqual({ type: "error", code: "isolation_failed", message: "not allowed" });
    expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
  });
});

async function run(script: ChildScript, extra: { secrets?: readonly string[]; check?: (outcome: DrivenOutcome) => string | null } = {}) {
  const spawner = new FakeSpawner();
  spawner.enqueue(script);
  const tapped: string[] = [];
  const events: AgentEvent[] = [];
  for await (const event of drive({
    spawner,
    clock: new FakeClock(0),
    spec: { file: "/bin/cli", args: [], cwd: "/work", env: {} },
    signal: new AbortController().signal,
    mapper: echoMapper(),
    notStarted: "The CLI could not be started.",
    tap: (line) => tapped.push(line),
    ...extra,
  })) {
    events.push(event);
  }
  return { events, tapped };
}

describe("drive redacts the secrets it was given", () => {
  it("scrubs the tapped lines and the text of the events", async () => {
    const { events, tapped } = await run({ stdout: [`echo of ${KEY}\n`], exit: ok }, { secrets: [KEY] });
    expect(tapped).toEqual(["echo of [redacted]"]);
    expect(events[0]).toEqual({ type: "text", messageId: "m1", text: "echo of [redacted]" });
    expect(JSON.stringify(events)).not.toContain(KEY);
  });

  it("scrubs every string field of an event, not only the text", async () => {
    const { events } = await run({ stdout: ["BOOM\n"], exit: ok }, { secrets: [KEY] });
    expect(events[0]).toEqual({ type: "tool_start", toolId: "t-[redacted]", name: "read", kind: "read", path: "/p/[redacted].tex" });
  });

  it("scrubs the end of the error output that an error event repeats, also when the key arrives in two pieces", async () => {
    const half = Math.floor(KEY.length / 2);
    const { events } = await run({ stderr: [`auth failed for ${KEY.slice(0, half)}`, `${KEY.slice(half)} retry later`], exit: { code: 1, signal: null } }, { secrets: [KEY] });
    const error = events.find((event) => event.type === "error");
    expect(error).toMatchObject({ type: "error", code: "provider_error", message: "The CLI failed: auth failed for [redacted] retry later", detail: "auth failed for [redacted] retry later" });
    expect(JSON.stringify(events)).not.toContain(KEY);
    expect(JSON.stringify(events)).not.toContain(KEY.slice(0, half));
  });

  it("scrubs a line that ends without a newline", async () => {
    const { events, tapped } = await run({ stdout: [`last ${KEY}`], exit: ok }, { secrets: [KEY] });
    expect(JSON.stringify(events)).not.toContain(KEY);
    expect(events[0]).toMatchObject({ type: "text", text: "last [redacted]" });
    expect(tapped.join("")).not.toContain(KEY);
  });

  it("scrubs the text of an isolation violation", async () => {
    const { events } = await run({ stdout: ["a line\n"], exit: ok }, { secrets: [KEY], check: () => `tool leaked ${KEY}` });
    expect(events).toContainEqual({ type: "error", code: "isolation_failed", message: "tool leaked [redacted]" });
    expect(JSON.stringify(events)).not.toContain(KEY);
  });

  it("leaves everything alone for a secret shorter than eight characters, and when no secret is given", async () => {
    const short = await run({ stdout: ["a short secret line\n"], exit: ok }, { secrets: ["secret"] });
    expect(short.events[0]).toMatchObject({ text: "a short secret line" });
    const none = await run({ stdout: [`plain ${KEY}\n`], exit: ok });
    expect(none.tapped).toEqual([`plain ${KEY}`]);
    expect(none.events[0]).toMatchObject({ text: `plain ${KEY}` });
  });

  it("keeps a key that was cut by a chunk boundary in the output out of the events", async () => {
    const chunks = splitBytes(`before ${KEY} after\n`, [12, 20]);
    const { events, tapped } = await run({ stdout: chunks, exit: ok }, { secrets: [KEY] });
    expect(tapped).toEqual(["before [redacted] after"]);
    expect(JSON.stringify(events)).not.toContain(KEY);
  });
});
