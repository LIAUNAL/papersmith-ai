import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { AgentDefinition, AgentEvent, TurnRequest } from "@caztor/core";
import { describe, expect, it, vi } from "vitest";
import { CODEX_ISOLATION_TIER, createCodexRunner, STOP_ESCALATION_MS, type CodexRunnerOptions } from "../../../src/providers/codex/runner.ts";
import { FakeClock } from "../../fakes/fake-clock.ts";
import { FakeSpawner, type ChildScript } from "../../fakes/fake-spawner.ts";
import { MemoryFileSystem } from "../../fakes/memory-fs.ts";
import { describeSandboxedTurns } from "../../support/sandboxed-turns.ts";
import { fakeAgentSandbox } from "../../fakes/fake-agent-sandbox.ts";
import { fakeReader } from "../../support/credentials.ts";

const fixture = (name: string): string[] => readFileSync(fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url)), "utf8").split("\n").filter((line) => line !== "");
const ROOT = "/work/project";
const BINARY = "/usr/local/bin/codex";
const hash = `sha256:${"a".repeat(64)}` as AgentDefinition["hash"];
const agent: AgentDefinition = { hash, name: "caztor", description: "LaTeX assistant", prompt: "You edit LaTeX.", tools: [] };
const request = (extra: Partial<TurnRequest> = {}): TurnRequest => ({ prompt: "Fix the typo", sessionId: null, model: null, agent, ...extra });
const ok = { code: 0, signal: null };
const THREAD = "00000000-0000-4000-8000-000000000001";

const ENV = {
  PATH: "/usr/local/bin:/usr/bin",
  HOME: "/home/user",
  LANG: "en_US.UTF-8",
  TMPDIR: "/tmp",
  CODEX_HOME: "/home/user/.codex-work",
  CODEX_API_KEY: "codex-key",
  OPENAI_API_KEY: "sk-test-key",
  OPENAI_BASE_URL: "https://proxy.example",
  CODEX_THREAD_ID: "parent-thread",
  CODEX_SANDBOX: "seatbelt",
  GITHUB_TOKEN: "ghp_secret",
  AWS_SECRET_ACCESS_KEY: "aws-secret",
};

async function setup(options: Partial<CodexRunnerOptions> = {}) {
  const fs = new MemoryFileSystem({ [BINARY]: "#!/bin/sh" });
  await fs.chmod(BINARY, 0o755);
  const spawner = new FakeSpawner();
  const clock = new FakeClock(1000);
  const runner = createCodexRunner({ fs, spawner, clock, root: ROOT, env: ENV, ...options });
  return { fs, spawner, clock, runner };
}
type T = Awaited<ReturnType<typeof setup>>;

async function collect(iterable: AsyncIterable<AgentEvent>): Promise<AgentEvent[]> {
  const out: AgentEvent[] = [];
  for await (const event of iterable) out.push(event);
  return out;
}
const turn = (script: ChildScript, req = request()) => async (t: T) => {
  t.spawner.enqueue(script);
  return collect(t.runner.runTurn(req, new AbortController().signal));
};
const lines = (name: string) => fixture(name).map((line) => `${line}\n`);
const EDIT = { stdout: lines("documented-edit-turn.jsonl"), exit: ok };
const FLAGS = ["exec", "--json", "--sandbox", "workspace-write", "--skip-git-repo-check", "--ignore-user-config"];

describe("the command line", () => {
  it("is the documented set, as an array, with the prompt read from stdin by a trailing dash", async () => {
    const t = await setup();
    await turn(EDIT)(t);
    const call = t.spawner.calls[0]!;
    expect(CODEX_ISOLATION_TIER).toBe("I1");
    expect(call.file).toBe(BINARY);
    expect(call.cwd).toBe(ROOT);
    expect(call.stdin).toBe("Fix the typo");
    expect(call.args).toEqual([...FLAGS, "-"]);
    for (const refused of ["--full-auto", "--dangerously-bypass-approvals-and-sandbox", "danger-full-access", "-C", "--cd"]) expect(call.args).not.toContain(refused);
  });

  it("resumes a thread with the subcommand after the flags", async () => {
    const t = await setup();
    await turn(EDIT, request({ sessionId: THREAD }))(t);
    expect(t.spawner.calls[0]!.args).toEqual([...FLAGS, "resume", THREAD, "-"]);
  });

  it.each(["--last", "-m", "../x", "a b", "$(id)", "--dangerously-bypass-approvals-and-sandbox", ""])("starts a new thread instead of passing the session id %j", async (sessionId) => {
    const t = await setup();
    await turn(EDIT, request({ sessionId }))(t);
    expect(t.spawner.calls[0]!.args).toEqual([...FLAGS, "-"]);
  });

  it.each(["; rm -rf ~", "--full-auto", "$(touch /tmp/x) `id`", "-", "line one\nline two"])("keeps the prompt %j out of the arguments", async (prompt) => {
    const baseline = await setup();
    await turn(EDIT, request({ prompt: "plain" }))(baseline);
    const t = await setup();
    await turn(EDIT, request({ prompt }))(t);
    expect(t.spawner.calls[0]!.stdin).toBe(prompt);
    expect(t.spawner.calls[0]!.args).toEqual(baseline.spawner.calls[0]!.args);
  });

  it("passes no model: the flag is not in the documentation the adapter was written from, so the model setting is off", async () => {
    const t = await setup();
    await turn(EDIT, request({ model: "gpt-5" }))(t);
    expect(t.spawner.calls[0]!.args).not.toContain("gpt-5");
    expect(t.spawner.calls[0]!.args).not.toContain("-m");
    expect(t.spawner.calls[0]!.args).not.toContain("--model");
  });
});

describe("the environment", () => {
  it("holds what the CLI needs to find its login and the network; exported keys and base URL are dropped", async () => {
    const t = await setup();
    await turn(EDIT)(t);
    expect(t.spawner.calls[0]!.env).toEqual({
      PATH: "/usr/local/bin:/usr/bin",
      HOME: "/home/user",
      LANG: "en_US.UTF-8",
      TMPDIR: "/tmp",
      CODEX_HOME: "/home/user/.codex-work",
      NO_COLOR: "1",
    });
  });

  it("does not pass any other secret, nor the variables of a Codex session that started the server", async () => {
    const t = await setup();
    await turn(EDIT)(t);
    const names = Object.keys(t.spawner.calls[0]!.env);
    for (const other of ["GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "CODEX_THREAD_ID", "CODEX_SANDBOX"]) expect(names).not.toContain(other);
  });
});

describe("a turn", () => {
  it("passes the commands Codex ran on as tool events: the sandbox is Codex's, and the chat discloses it", async () => {
    const t = await setup();
    const events = await turn(EDIT)(t);
    expect(events.map((event) => event.type)).toEqual(["session", "tool_start", "tool_update", "tool_end", "tool_start", "tool_end", "text", "done"]);
    expect(events[1]).toEqual({ type: "tool_start", toolId: "item_0", name: "command", kind: "command" });
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
    expect(t.spawner.signals).toEqual([]);
  });

  it("ends a failed turn with the readable error", async () => {
    const t = await setup();
    const events = await turn({ stdout: lines("documented-turn-failed.jsonl"), exit: { code: 1, signal: null } })(t);
    expect(events.find((event) => event.type === "error")).toMatchObject({ code: "auth", message: expect.stringContaining("codex login") });
    expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
  });

  it("reports a missing binary as not installed without starting anything", async () => {
    const t = await setup({ env: { ...ENV, PATH: "/nowhere" } });
    const events = await turn(EDIT)(t);
    expect(t.spawner.calls).toEqual([]);
    expect(events).toEqual([
      { type: "error", code: "not_installed", message: "Codex is not installed: the codex command was not found on the PATH." },
      { type: "done", reason: "failed" },
    ]);
  });

  it("reports a binary that disappeared after detection as a failed turn", async () => {
    const t = await setup();
    t.spawner.enqueue({ spawnError: "ENOENT" });
    const events = await collect(t.runner.runTurn(request(), new AbortController().signal));
    expect(events).toEqual([
      { type: "error", code: "not_installed", message: "Codex could not be started. Is it installed?" },
      { type: "done", reason: "failed" },
    ]);
  });

  it("fails with the end of its error output when it exits without a result", async () => {
    const t = await setup();
    const events = await turn({ stderr: ["Error: not inside a trusted directory\n"], exit: { code: 1, signal: null } })(t);
    expect(events).toEqual([
      { type: "error", code: "provider_error", message: "Codex stopped before it finished its answer.", detail: "Error: not inside a trusted directory" },
      { type: "done", reason: "failed" },
    ]);
  });

  it("ends the turn and stops the process after twenty unreadable lines", async () => {
    const t = await setup();
    const events = await turn({ stdout: Array.from({ length: 25 }, () => "nope\n") })(t);
    expect(events.at(-2)).toMatchObject({ type: "error", code: "malformed_output" });
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
  });

  it("ends a process that stays alive after the turn completed", async () => {
    const t = await setup();
    t.spawner.enqueue({ stdout: lines("documented-edit-turn.jsonl") });
    const finished = collect(t.runner.runTurn(request(), new AbortController().signal));
    await vi.waitFor(() => expect(t.spawner.calls).toHaveLength(1));
    await new Promise<void>((resolve) => setImmediate(resolve));
    t.clock.advance(2000);
    const events = await finished;
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });
});

describe("stopping", () => {
  async function running(script: ChildScript) {
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
  });

  it("goes on to SIGTERM after 3 s and SIGKILL 2 s later when the CLI ignores the signals", async () => {
    const { t, controller, finished, pause } = await running({ ignores: ["SIGINT", "SIGTERM"] });
    controller.abort();
    await pause();
    t.clock.advance(STOP_ESCALATION_MS.term);
    t.clock.advance(STOP_ESCALATION_MS.kill);
    await finished;
    expect(t.spawner.signals).toEqual(["SIGINT", "SIGTERM", "SIGKILL"]);
  });

  it("stops at once when the signal was already aborted, without starting the CLI", async () => {
    const t = await setup();
    const controller = new AbortController();
    controller.abort();
    expect(await collect(t.runner.runTurn(request(), controller.signal))).toEqual([{ type: "done", reason: "cancelled" }]);
    expect(t.spawner.calls).toEqual([]);
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
  const probe = async (script: ChildScript) => {
    const t = await setup();
    t.spawner.enqueue(script);
    return { t, status: await t.runner.detect() };
  };

  it("reports the version from codex --version, and that there is no model setting", async () => {
    const { t, status } = await probe({ stdout: ["codex-cli 0.46.0\n"], exit: ok });
    expect(status).toEqual({ provider: "codex", installed: true, version: "0.46.0", requiresModel: false, supportsModel: false });
    expect(t.spawner.calls[0]).toMatchObject({ file: BINARY, args: ["--version"], cwd: ROOT });
  });

  it("says it is not installed, with the reason, when no PATH folder holds an executable file of that name", async () => {
    const t = await setup({ env: { ...ENV, PATH: "/nowhere" } });
    const status = await t.runner.detect();
    expect(status).toEqual({ provider: "codex", installed: false, unavailableReason: "Codex is not installed: the codex command was not found on the PATH.", requiresModel: false, supportsModel: false });
    expect(t.spawner.calls).toEqual([]);
  });

  it("says why it cannot run: a failing exit, output it does not know, a start failure", async () => {
    const failing = await probe({ stderr: ["illegal instruction\n"], exit: { code: 132, signal: null } });
    expect(failing.status).toMatchObject({ installed: false, unavailableReason: expect.stringContaining("illegal instruction") });
    const strange = await probe({ stdout: ["hello\n"], exit: ok });
    expect(strange.status).toMatchObject({ installed: false, unavailableReason: expect.stringContaining("not recognised") });
    const missing = await probe({ spawnError: "ENOENT" });
    expect(missing.status).toMatchObject({ installed: false, unavailableReason: expect.stringContaining("could not be started") });
  });

  it("gives up after 5 seconds and stops the probe", async () => {
    const t = await setup();
    t.spawner.enqueue({});
    const pending = t.runner.detect();
    await vi.waitFor(() => expect(t.spawner.calls).toHaveLength(1));
    t.clock.advance(5000);
    expect(await pending).toMatchObject({ installed: false, unavailableReason: "Codex did not answer --version within 5 seconds." });
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
  });
});

describe("auth modes", () => {
  const STORED = "codex-stored-key-000111";
  const dropped = ["CODEX_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"];

  it("in account mode strips the exported keys and base URL, keeps CODEX_HOME, and never reads a stored key", async () => {
    for (const authMode of [undefined, "account"] as const) {
      const reader = fakeReader({ codex: STORED });
      const t = await setup({ credentials: reader });
      await turn(EDIT, request(authMode === undefined ? {} : { authMode }))(t);
      const env = t.spawner.calls[0]!.env;
      for (const name of dropped) expect(Object.keys(env)).not.toContain(name);
      expect(env["CODEX_HOME"]).toBe("/home/user/.codex-work");
      expect(JSON.stringify(env)).not.toContain(STORED);
      expect(reader.reads).toEqual([]);
    }
  });

  it("in api mode passes the stored key as CODEX_API_KEY and none of the server's variables", async () => {
    const reader = fakeReader({ codex: STORED, claude: "sk-claude-stored-0009" });
    const t = await setup({ credentials: reader });
    await turn(EDIT, request({ authMode: "api" }))(t);
    const call = t.spawner.calls[0]!;
    expect(call.env["CODEX_API_KEY"]).toBe(STORED);
    expect(call.env["CODEX_HOME"]).toBe("/home/user/.codex-work");
    expect(Object.keys(call.env)).not.toContain("OPENAI_API_KEY");
    expect(Object.keys(call.env)).not.toContain("OPENAI_BASE_URL");
    expect(JSON.stringify(call.env)).not.toContain("sk-claude-stored-0009");
    expect(call.args.join(" ")).not.toContain(STORED);
    expect(reader.reads).toEqual(["codex"]);
  });

  it("does not start a turn in api mode without a stored key", async () => {
    const t = await setup({ credentials: fakeReader({}) });
    const events = await collect(t.runner.runTurn(request({ authMode: "api" }), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(events).toEqual([
      { type: "error", code: "auth", message: expect.stringContaining("API key") },
      { type: "done", reason: "failed" },
    ]);
  });

  it("does not start a turn in api mode when the store refuses", async () => {
    const t = await setup({ credentials: fakeReader({}, { code: "corrupt", message: "The Caztor key file cannot be read." }) });
    const events = await collect(t.runner.runTurn(request({ authMode: "api" }), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(events[0]).toEqual({ type: "error", code: "auth", message: "The Caztor key file cannot be read." });
  });
});

describe("a stored key echoed by the CLI", () => {
  it("is masked in the tapped lines and in every event, also from the end of the error output", async () => {
    const KEY = "echoed-codex-key-7788";
    const tapped: string[] = [];
    const t = await setup({ credentials: fakeReader({ codex: KEY }), tap: (line) => tapped.push(line) });
    t.spawner.enqueue({ stdout: [`{"type":"noise","note":"rejected ${KEY}"}\n`], stderr: [`Invalid API key ${KEY}\n`], exit: { code: 1, signal: null } });
    const events = await collect(t.runner.runTurn(request({ authMode: "api" }), new AbortController().signal));
    expect(tapped.join("\n")).toContain("[redacted]");
    expect(tapped.join("\n")).not.toContain(KEY);
    expect(JSON.stringify(events)).not.toContain(KEY);
    expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
  });
});

describe("a collaborator's turn", () => {
  it("builds the child's environment from the turn's environment and reads the turn's own key", async () => {
    const host = fakeReader({ codex: "sk-host-codex-key-0001" });
    const own = fakeReader({ codex: "sk-own-codex-key-00002" });
    const t = await setup({ credentials: host, sandbox: fakeAgentSandbox().sandbox });
    const env = { PATH: "/usr/bin", HOME: "/cfg/caztor/users/u1/home", CODEX_HOME: "/cfg/caztor/users/u1/home/.codex" };
    await turn(EDIT, request({ authMode: "api", env, sandbox: { home: env.HOME }, credentials: own }))(t);
    expect(t.spawner.calls[0]!.env).toEqual({ ...env, CODEX_API_KEY: "sk-own-codex-key-00002", NO_COLOR: "1" });
    expect(host.reads).toEqual([]);
  });
});

describeSandboxedTurns({
  setup: async (options) => setup(options),
  request,
  script: EDIT,
  binary: BINARY,
});
