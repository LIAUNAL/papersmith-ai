import type { AgentEvent, AgentRunnerPort, TurnRequest } from "@caztor/core";
import { describe, expect, it } from "vitest";
import type { AgentSandbox } from "../../src/agent-sandbox.ts";
import { STOP_ESCALATION_MS } from "../../src/providers/drive.ts";
import { fakeAgentSandbox } from "../fakes/fake-agent-sandbox.ts";
import type { FakeClock } from "../fakes/fake-clock.ts";
import type { ChildScript, FakeSpawner } from "../fakes/fake-spawner.ts";

export interface SandboxedTurnSubject {
  setup(options: { sandbox?: AgentSandbox }): Promise<{ spawner: FakeSpawner; clock: FakeClock; runner: AgentRunnerPort }>;
  request(extra?: Partial<TurnRequest>): TurnRequest;
  /** A successful edit turn of this CLI. */
  script: ChildScript;
  binary: string;
}

const HOME = "/cfg/caztor/users/u1/home";
const COLLABORATOR: Partial<TurnRequest> = { env: { PATH: "/usr/bin", HOME }, sandbox: { home: HOME } };

/** The turn's events, without the notices some CLIs give before every turn. */
async function collect(iterable: AsyncIterable<AgentEvent>): Promise<AgentEvent[]> {
  const out: AgentEvent[] = [];
  for await (const event of iterable) if (event.type !== "notice") out.push(event);
  return out;
}

/** The cases every runner shares for a collaborator's turn inside bubblewrap, and the host's turn outside it. */
export function describeSandboxedTurns(subject: SandboxedTurnSubject): void {
  describe("a collaborator's turn in the sandbox", () => {
    it("spawns the wrapped spec, asking the sandbox for this CLI and the private home", async () => {
      const fake = fakeAgentSandbox();
      const t = await subject.setup({ sandbox: fake.sandbox });
      t.spawner.enqueue(subject.script);
      const events = await collect(t.runner.runTurn(subject.request(COLLABORATOR), new AbortController().signal));
      expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
      expect(fake.asked).toEqual([{ binary: subject.binary, home: HOME }]);
      expect(t.spawner.calls).toHaveLength(1);
      const call = t.spawner.calls[0]!;
      expect(call.file).toBe("/usr/bin/bwrap");
      expect(call.args).toEqual(["--", subject.binary, ...fake.wrapped[0]!.args]);
      expect(call.env).toEqual(fake.wrapped[0]!.env);
      expect(call.env["HOME"]).toBe(HOME);
    });

    it("is refused, and nothing runs, when the server has no sandbox", async () => {
      const t = await subject.setup({});
      const events = await collect(t.runner.runTurn(subject.request(COLLABORATOR), new AbortController().signal));
      expect(events).toEqual([
        { type: "error", code: "isolation_failed", message: expect.stringMatching(/could not run in the sandbox/) },
        { type: "done", reason: "failed" },
      ]);
      expect(t.spawner.calls).toEqual([]);
    });

    it("is refused with the sandbox's reason, and nothing runs, when bwrap cannot be used", async () => {
      const fake = fakeAgentSandbox({ refuse: "Bubblewrap (bwrap) was not found." });
      const t = await subject.setup({ sandbox: fake.sandbox });
      const events = await collect(t.runner.runTurn(subject.request(COLLABORATOR), new AbortController().signal));
      expect(events).toEqual([
        { type: "error", code: "isolation_failed", message: "Your turn was not started because it could not run in the sandbox: Bubblewrap (bwrap) was not found." },
        { type: "done", reason: "failed" },
      ]);
      expect(t.spawner.calls).toEqual([]);
    });

    it("is refused when it has a collaborator's environment but names no private folder", async () => {
      const fake = fakeAgentSandbox();
      const t = await subject.setup({ sandbox: fake.sandbox });
      const events = await collect(t.runner.runTurn(subject.request({ env: { PATH: "/usr/bin", HOME } }), new AbortController().signal));
      expect(events.map((event) => event.type)).toEqual(["error", "done"]);
      expect(events[0]).toMatchObject({ code: "isolation_failed" });
      expect(t.spawner.calls).toEqual([]);
      expect(fake.asked).toEqual([]);
    });

    it("stops the sandboxed child with the same escalation: SIGINT, then SIGTERM, then SIGKILL to its group", async () => {
      const fake = fakeAgentSandbox();
      const t = await subject.setup({ sandbox: fake.sandbox });
      t.spawner.enqueue({ ignores: ["SIGINT", "SIGTERM"] });
      const controller = new AbortController();
      const events = collect(t.runner.runTurn(subject.request(COLLABORATOR), controller.signal));
      while (t.spawner.calls.length === 0) await new Promise((resolve) => setTimeout(resolve, 0));
      expect(t.spawner.calls[0]!.file).toBe("/usr/bin/bwrap");
      controller.abort();
      t.clock.advance(STOP_ESCALATION_MS.term);
      t.clock.advance(STOP_ESCALATION_MS.kill);
      expect((await events).at(-1)).toEqual({ type: "done", reason: "cancelled" });
      expect(t.spawner.signals).toEqual(["SIGINT", "SIGTERM", "SIGKILL"]);
    });
  });

  describe("the host's turn", () => {
    it("is never wrapped, even when the server has a sandbox", async () => {
      const fake = fakeAgentSandbox();
      const t = await subject.setup({ sandbox: fake.sandbox });
      t.spawner.enqueue(subject.script);
      await collect(t.runner.runTurn(subject.request(), new AbortController().signal));
      expect(fake.asked).toEqual([]);
      expect(t.spawner.calls[0]!.file).toBe(subject.binary);
    });
  });
}
