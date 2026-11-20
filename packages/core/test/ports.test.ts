import { describe, expect, expectTypeOf, it } from "vitest";
import {
  PROVIDER_IDS,
  TURN_ERROR_CODES,
  type AgentEvent,
  type AgentRunnerPort,
  type CompilerPort,
  type ContentHash,
  type ProjectState,
  type ProjectStorePort,
  type ProvisionerPort,
  type RelPath,
  type Result,
  type SnapshotPort,
  type StatePort,
  type StoreError,
  type TurnEvent,
} from "../src/ports.ts";

// Exhaustive over AgentEvent: tsc fails when a variant is added or removed without updating this table.
function describeEvent(event: AgentEvent): string {
  switch (event.type) {
    case "session":
      return `session ${event.sessionId}`;
    case "text_delta":
      return `delta ${event.messageId} ${event.text}`;
    case "text":
      return `text ${event.messageId} ${event.text}`;
    case "tool_start":
      return `tool_start ${event.toolId} ${event.kind}`;
    case "tool_update":
      return `tool_update ${event.toolId}`;
    case "tool_end":
      return `tool_end ${event.toolId} ${event.status}`;
    case "notice":
      return `notice ${event.level}`;
    case "error":
      return `error ${event.code}`;
    case "done":
      return `done ${event.reason}`;
    default: {
      const unreachable: never = event;
      return unreachable;
    }
  }
}

describe("runtime constants", () => {
  it("lists the five providers in a stable order", () => {
    expect(PROVIDER_IDS).toEqual(["claude", "opencode", "codex", "antigravity", "pi"]);
  });

  it("lists every turn error code", () => {
    expect(TURN_ERROR_CODES).toEqual([
      "not_installed",
      "auth",
      "model_unavailable",
      "model_required",
      "rate_limited",
      "permission_denied",
      "isolation_failed",
      "snapshot_failed",
      "malformed_output",
      "timeout",
      "provider_error",
      "mode_unsupported",
    ]);
  });
});

describe("event unions", () => {
  it("narrows every AgentEvent variant", () => {
    const events: AgentEvent[] = [
      { type: "session", sessionId: "s1" },
      { type: "text_delta", messageId: "m1", text: "hel" },
      { type: "text", messageId: "m1", text: "hello" },
      { type: "tool_start", toolId: "t1", name: "Edit", kind: "edit", path: "main.tex" },
      { type: "tool_update", toolId: "t1", title: "Editing" },
      { type: "tool_end", toolId: "t1", status: "done" },
      { type: "notice", level: "warning", message: "careful" },
      { type: "error", code: "auth", message: "Not signed in" },
      { type: "done", reason: "completed", usage: { inputTokens: 1 } },
    ];
    expect(events.map(describeEvent)).toEqual([
      "session s1",
      "delta m1 hel",
      "text m1 hello",
      "tool_start t1 edit",
      "tool_update t1",
      "tool_end t1 done",
      "notice warning",
      "error auth",
      "done completed",
    ]);
  });

  it("extends AgentEvent with the turn-level events", () => {
    const events: TurnEvent[] = [
      { type: "turn_started", turnId: "u1", provider: "claude", snapshotPartial: false, unprotected: [] },
      { type: "files_changed", turnId: "u1", files: [] },
      { type: "done", reason: "cancelled" },
    ];
    expect(events.map((event) => event.type)).toEqual(["turn_started", "files_changed", "done"]);
    expectTypeOf<AgentEvent>().toExtend<TurnEvent>();
  });
});

describe("port shapes", () => {
  it("keeps the documented signatures", () => {
    expectTypeOf<Result<number, string>>().toEqualTypeOf<{ ok: true; value: number } | { ok: false; error: string }>();
    expectTypeOf<ProjectStorePort["write"]>().parameters.toEqualTypeOf<
      [path: RelPath, bytes: Uint8Array, expect: ContentHash | null | "any"]
    >();
    expectTypeOf<ProjectStorePort["watch"]>().returns.toEqualTypeOf<() => void>();
    expectTypeOf<CompilerPort["compile"]>().parameters.toEqualTypeOf<
      [req: { main: RelPath; stopOnFirstError: boolean; sandboxed?: boolean }, signal: AbortSignal]
    >();
    expectTypeOf<AgentRunnerPort["provider"]>().toEqualTypeOf<"claude" | "opencode" | "codex" | "antigravity" | "pi">();
    expectTypeOf<SnapshotPort["restore"]>().parameters.toEqualTypeOf<
      [turnId: string, mode: "strict" | "skip_conflicts" | "force"]
    >();
    expectTypeOf<StatePort["update"]>().parameters.toEqualTypeOf<[patch: Partial<ProjectState>]>();
    expectTypeOf<ProvisionerPort["ensure"]>().parameter(0).toEqualTypeOf<"claude" | "opencode" | "codex" | "antigravity" | "pi">();
    expectTypeOf<ProvisionerPort["ensure"]>().parameter(1).toEqualTypeOf<{ replace: boolean } | undefined>();
  });

  it("keeps the conflict variant of StoreError carrying the current hash", () => {
    const conflict: StoreError = { code: "conflict", path: "a.tex" as RelPath, currentHash: null };
    const hidden: StoreError = { code: "hidden", path: ".git" };
    expect([conflict.code, hidden.code]).toEqual(["conflict", "hidden"]);
    expectTypeOf<Extract<StoreError, { code: "conflict" }>["currentHash"]>().toEqualTypeOf<ContentHash | null>();
  });
});
