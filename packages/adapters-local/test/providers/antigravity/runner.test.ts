import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { AgentDefinition, AgentEvent, TurnRequest } from "@caztor/core";
import { describe, expect, it, vi } from "vitest";
import {
  ANTIGRAVITY_ALLOWED_TOOLS,
  ANTIGRAVITY_ISOLATION_TIER,
  ANTIGRAVITY_PARTIAL_ISOLATION_NOTICE,
  ANTIGRAVITY_TESTED_VERSION,
  createAntigravityRunner,
  type AntigravityRunnerOptions,
} from "../../../src/providers/antigravity/runner.ts";
import { FakeClock } from "../../fakes/fake-clock.ts";
import { FakeSpawner } from "../../fakes/fake-spawner.ts";
import { MemoryFileSystem } from "../../fakes/memory-fs.ts";
import { describeSandboxedTurns } from "../../support/sandboxed-turns.ts";
import { fakeAgentSandbox } from "../../fakes/fake-agent-sandbox.ts";

const fixture = (name: string): string[] => readFileSync(fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url)), "utf8").split("\n").filter((line) => line !== "").map((line) => `${line}\n`);
const ROOT = "/work/project";
const BINARY = "/usr/local/bin/agy";
const hash = `sha256:${"a".repeat(64)}` as AgentDefinition["hash"];
const agent: AgentDefinition = {
  hash,
  name: "caztor",
  description: "LaTeX assistant",
  prompt: "You edit LaTeX.",
  tools: ["view_file", "replace_file_content", "write_to_file", "list_dir", "find_by_name", "grep_search"],
};
const request = (extra: Partial<TurnRequest> = {}): TurnRequest => ({
  prompt: "Fix the typo",
  sessionId: null,
  model: null,
  agent,
  ...extra,
});
const ok = { code: 0, signal: null };

const ENV = {
  PATH: "/usr/local/bin:/usr/bin",
  HOME: "/home/user",
  LANG: "en_US.UTF-8",
  TMPDIR: "/tmp",
  XDG_RUNTIME_DIR: "/run/user/1000",
  DBUS_SESSION_BUS_ADDRESS: "unix:path=/run/user/1000/bus",
  GEMINI_API_KEY: "secret-gemini-key",
  GOOGLE_API_KEY: "secret-google-key",
  CLAUDE_CODE_SESSION_ID: "parent-session",
  GITHUB_TOKEN: "ghp_secret",
  AWS_SECRET_ACCESS_KEY: "aws-secret",
};

async function setup(options: Partial<AntigravityRunnerOptions> = {}, files: Record<string, string> = {}) {
  const fs = new MemoryFileSystem({ [BINARY]: "#!/bin/sh", ...files });
  await fs.chmod(BINARY, 0o755);
  const spawner = new FakeSpawner();
  const clock = new FakeClock(1000);
  const runner = createAntigravityRunner({ fs, spawner, clock, root: ROOT, env: ENV, ...options });
  return { fs, spawner, clock, runner };
}

async function collect(iterable: AsyncIterable<AgentEvent>): Promise<AgentEvent[]> {
  const out: AgentEvent[] = [];
  for await (const event of iterable) out.push(event);
  return out;
}

const types = (events: AgentEvent[]) => events.map((event) => event.type);

describe("the Antigravity runner", () => {
  it("exposes the provider id and partial isolation tier P1", async () => {
    const { runner } = await setup();
    expect(runner.provider).toBe("antigravity");
    expect(runner.isolation).toBe(ANTIGRAVITY_ISOLATION_TIER);
    expect(runner.isolation).toBe("P1");
  });

  describe("API mode refusal", () => {
    it("refuses API mode with mode_unsupported and spawns nothing", async () => {
      const { runner, spawner } = await setup();
      const events = await collect(runner.runTurn(request({ authMode: "api" }), new AbortController().signal));
      expect(types(events)).toEqual(["error", "done"]);
      expect(events[0]).toMatchObject({ type: "error", code: "mode_unsupported" });
      expect(events[1]).toEqual({ type: "done", reason: "failed" });
      expect(spawner.calls).toHaveLength(0);
    });
  });

  describe("argv and environment", () => {
    it("passes exact argv with prompt attached to -p, mode accept-edits and agent caztor, with no time limit of its own", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      await collect(runner.runTurn(request({ prompt: "Change cat to dog" }), new AbortController().signal));

      expect(spawner.calls).toHaveLength(1);
      const call = spawner.calls[0]!;
      expect(call.file).toBe(BINARY);
      expect(call.cwd).toBe(ROOT);
      expect(call.args).toEqual([
        "--output-format", "stream-json",
        "--mode", "accept-edits",
        "--agent", "caztor",
        "-p=Change cat to dog",
      ]);
      expect(call.args).not.toContain("--dangerously-skip-permissions");
    });

    it("attaches prompts beginning with a dash to -p so they never become CLI options", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      await collect(runner.runTurn(request({ prompt: "-l --help" }), new AbortController().signal));
      expect(spawner.calls[0]?.args).toContain("-p=-l --help");
    });

    it("passes validated model if provided, and rejects hostile model names", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      await collect(runner.runTurn(request({ model: "gemini-3.8-flash-medium" }), new AbortController().signal));
      expect(spawner.calls[0]?.args).toContain("--model");
      expect(spawner.calls[0]?.args).toContain("gemini-3.8-flash-medium");

      const hostileEvents = await collect(runner.runTurn(request({ model: "--dangerously-skip-permissions" }), new AbortController().signal));
      expect(hostileEvents.some((e) => e.type === "error" && e.code === "model_unavailable")).toBe(true);
    });

    it("passes only allowed environment variables, excluding secrets and GEMINI/GOOGLE/CLAUDE vars", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      await collect(runner.runTurn(request(), new AbortController().signal));

      const env = spawner.calls[0]!.env;
      expect(env["PATH"]).toBe(ENV.PATH);
      expect(env["HOME"]).toBe(ENV.HOME);
      expect(env["XDG_RUNTIME_DIR"]).toBe(ENV.XDG_RUNTIME_DIR);
      expect(env["DBUS_SESSION_BUS_ADDRESS"]).toBe(ENV.DBUS_SESSION_BUS_ADDRESS);
      expect(env["NO_COLOR"]).toBe("1");

      expect(env["GEMINI_API_KEY"]).toBeUndefined();
      expect(env["GOOGLE_API_KEY"]).toBeUndefined();
      expect(env["CLAUDE_CODE_SESSION_ID"]).toBeUndefined();
      expect(env["GITHUB_TOKEN"]).toBeUndefined();
      expect(env["AWS_SECRET_ACCESS_KEY"]).toBeUndefined();
    });
  });

  describe("continuation and session ID", () => {
    it("passes --conversation for valid stored UUID session id", async () => {
      const { runner, spawner } = await setup();
      const validSession = "00000000-0000-4000-8000-000000000001";
      spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      await collect(runner.runTurn(request({ sessionId: validSession }), new AbortController().signal));

      expect(spawner.calls[0]?.args).toContain("--conversation");
      expect(spawner.calls[0]?.args).toContain(validSession);
    });

    it("does not pass hostile session id in --conversation", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      await collect(runner.runTurn(request({ sessionId: "../../../etc/passwd" }), new AbortController().signal));

      expect(spawner.calls[0]?.args).not.toContain("--conversation");
    });
  });

  describe("partial isolation notice", () => {
    it("emits the partial-isolation notice on every turn", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));

      expect(events).toContainEqual({ type: "notice", level: "info", message: ANTIGRAVITY_PARTIAL_ISOLATION_NOTICE });
    });
  });

  describe("tool guard", () => {
    it("does not abort on init.tools even if it contains run_command", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      expect(events.some((e) => e.type === "error" && e.code === "isolation_failed")).toBe(false);
      expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
    });

    it("aborts turn mid-turn when a disallowed tool step is reported", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: fixture("synthetic-disallowed-tool.jsonl"), exit: ok });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));

      expect(types(events)).toContain("error");
      const err = events.find((e) => e.type === "error");
      expect(err).toMatchObject({
        type: "error",
        code: "isolation_failed",
        message: expect.stringContaining("run_command"),
      });
      expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
    });
  });

  describe("guard fails closed", () => {
    const step = (update: Record<string, unknown>) => `${JSON.stringify({ event: "step_update", step_update: { conversation_id: "00000000-0000-4000-8000-000000000001", step_index: 1, state: "ACTIVE", ...update } })}\n`;
    const refused = async (line: string) => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: [line], exit: ok });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      return events.some((event) => event.type === "error" && event.code === "isolation_failed");
    };

    it("stops a step whose two tool names disagree", async () => {
      expect(await refused(step({ step_type: "tool", tool_name: "view_file", tool_info: { name: "run_command" } }))).toBe(true);
    });

    it("stops a tool step with no name at all, and terminates the process", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: [step({ step_type: "tool" })], exit: ok });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      expect(events.find((event) => event.type === "error")).toMatchObject({ code: "isolation_failed", message: expect.stringContaining("unnamed") });
      expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
      expect(spawner.signals).toEqual(["SIGTERM"]);
    });

    it("stops a step of type TOOL with no name, and terminates the process", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: [step({ step_type: "TOOL" })], exit: ok });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      expect(events.find((event) => event.type === "error")).toMatchObject({ code: "isolation_failed" });
      expect(spawner.signals).toEqual(["SIGTERM"]);
    });

    it.each([["tool_call"], ["function_call"], ["mcp_tool"], ["something_new"]])("stops a nameless step of the unknown type %s", async (step_type) => {
      expect(await refused(step({ step_type }))).toBe(true);
    });

    it.each([["agent_response"], ["user_input"], ["system_message"], ["error_message"]])("does not stop a step of the known type %s", async (step_type) => {
      expect(await refused(step({ step_type }))).toBe(false);
    });

    it("stops a disallowed tool on a last line with no newline, and shows no tool card", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: [step({ step_type: "tool", tool_name: "run_command" }).trimEnd()], exit: ok });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      expect(events.find((event) => event.type === "error")).toMatchObject({ code: "isolation_failed", message: expect.stringContaining("run_command") });
      expect(events.some((event) => event.type === "tool_start")).toBe(false);
      expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
    });

    it.each([["TOOL"], ["command"], [undefined]])("stops a tool reported under the step type %s", async (step_type) => {
      expect(await refused(step({ step_type, tool_name: "run_command" }))).toBe(true);
    });
  });

  describe("what agy prints", () => {
    const ENV_KEY = "env-secret-value-1234";
    const STORED_KEY = "stored-secret-value-5678";
    const credentials = { read: async (slot: string) => ({ ok: true as const, value: slot === "claude" ? STORED_KEY : null }) };
    const secretSetup = () => setup({ env: { ...ENV, GEMINI_API_KEY: ENV_KEY }, credentials });

    it("hides keys in the error output of a process that stops early, and keeps the rest", async () => {
      const { runner, spawner } = await secretSetup();
      spawner.enqueue({ stdout: [], stderr: [`boom ${ENV_KEY} and ${STORED_KEY}\n`], exit: { code: 1, signal: null } });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      const seen = JSON.stringify(events);
      expect(seen).not.toContain(ENV_KEY);
      expect(seen).not.toContain(STORED_KEY);
      expect(events.find((event) => event.type === "error")).toMatchObject({ code: "provider_error", detail: expect.stringContaining("boom [redacted]") });
    });

    it("hides keys in an error the result reports", async () => {
      const { runner, spawner } = await secretSetup();
      spawner.enqueue({ stdout: [`${JSON.stringify({ event: "result", result: { status: "ERROR", error: `failed with ${ENV_KEY}` } })}\n`], exit: ok });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      expect(JSON.stringify(events)).not.toContain(ENV_KEY);
    });

    it("leaves ordinary text alone when a variable only looks like a secret", async () => {
      const env = { ...ENV, TOKEN_CACHE: "disabled", PROJECT_KEY_DIR: ROOT, MONKEY_TOOL: "view_file", KEY_STATUS: "completed", FEATURE_TOKEN: "completed" };
      const plain = await setup();
      plain.spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      const expected = await collect(plain.runner.runTurn(request(), new AbortController().signal));
      const { runner, spawner } = await setup({ env });
      spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      expect(await collect(runner.runTurn(request(), new AbortController().signal))).toEqual(expected);
    });

    it("still runs the turn when the key store cannot be read", async () => {
      const { runner, spawner } = await setup({ credentials: { read: async () => ({ ok: false as const, error: { code: "io" as const, message: "no" } }) } });
      spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
    });
  });

  describe("the definition file", () => {
    const definition = (front: string) => ({ [`${ROOT}/.agents/agents/caztor.md`]: `---\nname: caztor\ntools: [view_file]\ncommandExecutionPolicy: off\n${front}---\nBody\n` });

    it("refuses a turn when the definition has a key Caztor does not write, offering to replace it", async () => {
      const { runner, spawner } = await setup({}, definition("mcpServers: x\n"));
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      expect(events.find((event) => event.type === "notice")).toMatchObject({ action: "replace_definition" });
      expect(events.at(-2)).toMatchObject({ type: "error", code: "isolation_failed" });
      expect(spawner.calls).toHaveLength(0);
    });

    it("refuses a turn when the definition is a symbolic link", async () => {
      const { runner, spawner, fs } = await setup({}, { [`${ROOT}/other.md`]: "x" });
      await fs.mkdir(`${ROOT}/.agents/agents`, { recursive: true });
      await fs.symlink(`${ROOT}/other.md`, `${ROOT}/.agents/agents/caztor.md`);
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      expect(events.at(-2)).toMatchObject({ type: "error", code: "isolation_failed" });
      expect(spawner.calls).toHaveLength(0);
    });

    it("runs with the definition Caztor writes", async () => {
      const { runner, spawner } = await setup({}, definition("description: x\nmodel: inherit\n"));
      spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
    });
  });

  describe("trust gate", () => {
    it("refuses turn when unconfirmed .agents/ configuration is present", async () => {
      const { runner, spawner } = await setup({}, {
        [`${ROOT}/.agents/hooks.json`]: '{"hook": "run"}',
      });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      expect(types(events)).toEqual(["error", "done"]);
      expect(events[0]).toMatchObject({ type: "error", code: "isolation_failed" });
      expect(spawner.calls).toHaveLength(0);
    });

    it("proceeds when .agents/ configuration is confirmed", async () => {
      const { runner, spawner } = await setup({
        projectConfigConfirmed: async () => true,
      }, {
        [`${ROOT}/.agents/hooks.json`]: '{"hook": "run"}',
      });
      spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
      const events = await collect(runner.runTurn(request(), new AbortController().signal));
      expect(events.some((e) => e.type === "error" && e.code === "isolation_failed")).toBe(false);
      expect(spawner.calls).toHaveLength(1);
    });
  });

  describe("stop escalation", () => {
    async function running(script: import("../../fakes/fake-spawner.ts").ChildScript = {}) {
      const t = await setup();
      t.spawner.enqueue(script);
      const controller = new AbortController();
      const events: AgentEvent[] = [];
      const finished = collect(t.runner.runTurn(request(), controller.signal)).then((all) => void events.push(...all));
      await vi.waitFor(() => expect(t.spawner.calls).toHaveLength(1));
      const pause = () => new Promise<void>((resolve) => setImmediate(resolve));
      return { t, controller, events, finished, pause };
    }

    it("sends SIGINT to the process group at once and ends the turn cancelled when the CLI exits", async () => {
      const { t, controller, events, finished } = await running({});
      controller.abort();
      await finished;
      expect(t.spawner.signals).toEqual(["SIGINT"]);
      expect(events.at(-1)).toEqual({ type: "done", reason: "cancelled" });
      expect(t.clock.pendingTimers).toBe(0);
    });

    it("goes on to SIGTERM after 3 s and SIGKILL 2 s later when the CLI ignores the signals", async () => {
      const { t, controller, finished, pause } = await running({ ignores: ["SIGINT", "SIGTERM"] });
      controller.abort();
      await pause();
      expect(t.spawner.signals).toEqual(["SIGINT"]);
      t.clock.advance(3000 - 1);
      expect(t.spawner.signals).toEqual(["SIGINT"]);
      t.clock.advance(1);
      expect(t.spawner.signals).toEqual(["SIGINT", "SIGTERM"]);
      t.clock.advance(2000 - 1);
      expect(t.spawner.signals).toEqual(["SIGINT", "SIGTERM"]);
      t.clock.advance(1);
      await finished;
      expect(t.spawner.signals).toEqual(["SIGINT", "SIGTERM", "SIGKILL"]);
    });

    it("kills the process group at once when asked to force a stop", async () => {
      const { t, controller, finished } = await running({ ignores: ["SIGINT"] });
      controller.abort();
      t.runner.forceStop?.();
      await finished;
      expect(t.spawner.signals).toEqual(["SIGINT", "SIGKILL"]);
    });
  });

  describe("detection", () => {
    it("reports not installed when agy is not on PATH", async () => {
      const fs = new MemoryFileSystem({});
      const spawner = new FakeSpawner();
      const clock = new FakeClock();
      const runner = createAntigravityRunner({ fs, spawner, clock, root: ROOT, env: { PATH: "/bin" } });

      const status = await runner.detect();
      expect(status.installed).toBe(false);
      expect(status.unavailableReason).toContain("not found on the PATH");
    });

    it("detects installed version and parses models skipping the first Fetching line", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: ["1.4.11\n"], exit: ok });
      spawner.enqueue({
        stdout: [
          "Fetching available models...\n",
          "gemini-3.8-flash-high\tGemini 3.8 Flash (High)\n",
          "gemini-3.8-flash-medium\tGemini 3.8 Flash (Medium)\n",
          "claude-sonnet-4-6\tClaude Sonnet 4.6\n",
        ],
        exit: ok,
      });

      const status = await runner.detect();
      expect(status.installed).toBe(true);
      expect(status.version).toBe("1.4.11");
      expect(status.requiresModel).toBe(false);
      expect(status.models).toEqual([
        "claude-sonnet-4-6",
        "gemini-3.8-flash-high",
        "gemini-3.8-flash-medium",
      ]);

      // Detection ran in a temporary directory outside the project
      expect(spawner.calls[0]?.cwd).not.toBe(ROOT);
    });
  });
});

describe("a collaborator's turn", () => {
  it("builds the child's environment from the turn's environment, so no D-Bus of the host's reaches it", async () => {
    const { runner, spawner } = await setup({ sandbox: fakeAgentSandbox().sandbox });
    spawner.enqueue({ stdout: fixture("edit-turn.jsonl"), exit: ok });
    await collect(runner.runTurn(request({ env: { PATH: "/usr/bin", HOME: "/cfg/u/home" }, sandbox: { home: "/cfg/u/home" } }), new AbortController().signal));
    expect(spawner.calls[0]!.env).toEqual({ PATH: "/usr/bin", HOME: "/cfg/u/home", NO_COLOR: "1" });
  });
});

describeSandboxedTurns({
  setup: async (options) => setup(options),
  request,
  script: { stdout: fixture("edit-turn.jsonl"), exit: ok },
  binary: BINARY,
});
