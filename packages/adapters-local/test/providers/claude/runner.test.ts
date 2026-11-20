import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { AgentDefinition, AgentEvent, TurnRequest } from "@caztor/core";
import { describe, expect, it, vi } from "vitest";
import {
  ALLOWED_TOOLS,
  CLAUDE_ISOLATION_TIER,
  CLAUDE_TESTED_VERSION,
  createClaudeRunner,
  STOP_ESCALATION_MS,
  type ClaudeRunnerOptions,
  CLAUDE_DEFAULT_MODEL,
  CLAUDE_MODELS,
} from "../../../src/providers/claude/runner.ts";
import { resolveBinary } from "../../../src/providers/resolve-binary.ts";
import { FakeClock } from "../../fakes/fake-clock.ts";
import { FakeSpawner, type ChildScript } from "../../fakes/fake-spawner.ts";
import { MemoryFileSystem } from "../../fakes/memory-fs.ts";
import { describeSandboxedTurns } from "../../support/sandboxed-turns.ts";
import { fakeAgentSandbox } from "../../fakes/fake-agent-sandbox.ts";
import { fakeReader } from "../../support/credentials.ts";

const fixture = (name: string): string[] => readFileSync(fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url)), "utf8").split("\n").filter((line) => line !== "");
const ROOT = "/work/project";
const BINARY = "/usr/local/bin/claude";
const hash = `sha256:${"a".repeat(64)}` as AgentDefinition["hash"];
const agent: AgentDefinition = { hash, name: "caztor", description: "LaTeX assistant", prompt: "You edit LaTeX.", tools: ["Read", "Edit", "Write", "Glob", "Grep"] };
const request = (extra: Partial<TurnRequest> = {}): TurnRequest => ({ prompt: "Fix the typo", sessionId: null, model: null, agent, ...extra });
const ok = { code: 0, signal: null };

const ENV = {
  PATH: "/usr/local/bin:/usr/bin",
  HOME: "/home/user",
  LANG: "en_US.UTF-8",
  TMPDIR: "/tmp",
  ANTHROPIC_API_KEY: "sk-test-key",
  ANTHROPIC_AUTH_TOKEN: "auth-token",
  ANTHROPIC_BASE_URL: "https://proxy.example",
  CLAUDE_CODE_OAUTH_TOKEN: "oauth-token",
  CLAUDE_CONFIG_DIR: "/home/user/.claude-work",
  CLAUDE_CODE_SESSION_ID: "parent-session",
  CLAUDE_PID: "1234",
  CLAUDE_EFFORT: "high",
  CLAUDE_CODE_ENTRYPOINT: "cli",
  GITHUB_TOKEN: "ghp_secret",
  AWS_SECRET_ACCESS_KEY: "aws-secret",
  SECRET_TOKEN: "x",
};

async function setup(options: Partial<ClaudeRunnerOptions> = {}, files: Record<string, string> = {}) {
  const fs = new MemoryFileSystem({ [BINARY]: "#!/bin/sh", ...files });
  await fs.chmod(BINARY, 0o755);
  const spawner = new FakeSpawner();
  const clock = new FakeClock(1000);
  const runner = createClaudeRunner({ fs, spawner, clock, root: ROOT, env: ENV, ...options });
  return { fs, spawner, clock, runner };
}

async function collect(iterable: AsyncIterable<AgentEvent>): Promise<AgentEvent[]> {
  const out: AgentEvent[] = [];
  for await (const event of iterable) out.push(event);
  return out;
}
const types = (events: AgentEvent[]) => events.map((event) => event.type);
const turn = (script: ChildScript, req = request()) => async (t: Awaited<ReturnType<typeof setup>>) => {
  t.spawner.enqueue(script);
  return collect(t.runner.runTurn(req, new AbortController().signal));
};
const EDIT = { stdout: fixture("edit-turn.jsonl").map((line) => `${line}\n`), exit: ok };

describe("the command line", () => {
  it("is the observed set plus the isolation flags of tier I1, as an array, with the prompt on stdin", async () => {
    const t = await setup();
    await turn(EDIT)(t);

    const call = t.spawner.calls[0]!;
    expect(CLAUDE_ISOLATION_TIER).toBe("I1");
    expect(call.file).toBe(BINARY);
    expect(call.cwd).toBe(ROOT);
    expect(call.stdin).toBe("Fix the typo");
    const agents = call.args[call.args.indexOf("--agents") + 1]!;
    expect(call.args).toEqual([
      "-p",
      "--output-format", "stream-json",
      "--verbose",
      "--include-partial-messages",
      "--permission-mode", "acceptEdits",
      "--setting-sources", "",
      "--strict-mcp-config",
      "--disable-slash-commands",
      "--tools", "Read,Edit,Write,Glob,Grep",
      "--agents", agents,
      "--agent", "caztor",
      "--model", CLAUDE_DEFAULT_MODEL,
    ]);
    expect(JSON.parse(agents)).toEqual({ caztor: { description: "LaTeX assistant", prompt: "You edit LaTeX.", tools: ["Read", "Edit", "Write", "Glob", "Grep"] } });
    expect(call.args).not.toContain("--bare");
  });

  it.each(["; rm -rf ~", "--dangerously-skip-permissions", "$(touch /tmp/x) `id`", "-p", "line one\nline two"])("keeps the prompt %j out of the arguments", async (prompt) => {
    const baseline = await setup();
    await turn(EDIT, request({ prompt: "plain" }))(baseline);
    const t = await setup();
    await turn(EDIT, request({ prompt }))(t);
    expect(t.spawner.calls[0]!.stdin).toBe(prompt);
    expect(t.spawner.calls[0]!.args).toEqual(baseline.spawner.calls[0]!.args);
  });

  it("adds a valid model after --model and resumes by session id", async () => {
    const t = await setup();
    await turn(EDIT, request({ model: "claude-sonnet-4-5", sessionId: "c01f757e-ae3b-455c-9f5a-5aafe8e7af20" }))(t);
    const args = t.spawner.calls[0]!.args;
    expect(args.slice(args.indexOf("--model"), args.indexOf("--model") + 2)).toEqual(["--model", "claude-sonnet-4-5"]);
    expect(args.slice(args.indexOf("--resume"), args.indexOf("--resume") + 2)).toEqual(["--resume", "c01f757e-ae3b-455c-9f5a-5aafe8e7af20"]);
  });

  it("does not start a turn with a model that could be read as an option", async () => {
    const t = await setup();
    t.spawner.enqueue(EDIT);
    const events = await collect(t.runner.runTurn(request({ model: "--dangerous" }), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(events).toEqual([
      { type: "error", code: "model_unavailable", message: expect.stringContaining("dash") },
      { type: "done", reason: "failed" },
    ]);
  });

  it("starts a new conversation instead of passing a session id that is not an id", async () => {
    const t = await setup();
    await turn(EDIT, request({ sessionId: "--dangerously-skip-permissions" }))(t);
    expect(t.spawner.calls[0]!.args).not.toContain("--resume");
    expect(t.spawner.calls[0]!.args).not.toContain("--dangerously-skip-permissions");
  });

  it("leaves out tools other than file reading and editing, and says so", async () => {
    const t = await setup();
    const events = await turn(EDIT, request({ agent: { ...agent, tools: ["Read", "Bash", "WebFetch", "Edit"] } }))(t);
    const args = t.spawner.calls[0]!.args;
    expect(args[args.indexOf("--tools") + 1]).toBe("Read,Edit");
    expect(JSON.parse(args[args.indexOf("--agents") + 1]!).caztor.tools).toEqual(["Read", "Edit"]);
    expect(events[0]).toEqual({ type: "notice", level: "warning", message: "The agent definition lists tools other than file reading and editing (Bash, WebFetch). Caztor left them out." });
    expect(ALLOWED_TOOLS).toEqual(["Read", "Edit", "Write", "Glob", "Grep"]);
  });

  it("refuses an agent definition with no usable tool", async () => {
    const t = await setup();
    const events = await turn(EDIT, request({ agent: { ...agent, tools: ["Bash"] } }))(t);
    expect(t.spawner.calls).toEqual([]);
    expect(events[0]).toMatchObject({ type: "error", code: "isolation_failed" });
    expect(types(events).at(-1)).toBe("done");
  });
});

describe("the environment", () => {
  it("holds only what the CLI needs to find its login and the network; an exported Anthropic key, token or base URL is dropped", async () => {
    const t = await setup();
    await turn(EDIT)(t);
    expect(t.spawner.calls[0]!.env).toEqual({
      PATH: "/usr/local/bin:/usr/bin",
      HOME: "/home/user",
      LANG: "en_US.UTF-8",
      TMPDIR: "/tmp",
      CLAUDE_CODE_OAUTH_TOKEN: "oauth-token",
      CLAUDE_CONFIG_DIR: "/home/user/.claude-work",
      CLAUDE_CODE_DISABLE_AUTO_MEMORY: "1",
      NO_COLOR: "1",
    });
  });

  it("does not pass any other secret of the server, nor the variables of a Claude Code session that started the server", async () => {
    const t = await setup();
    await turn(EDIT)(t);
    const names = Object.keys(t.spawner.calls[0]!.env);
    for (const secret of ["GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "SECRET_TOKEN", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_CODE_ENTRYPOINT"]) expect(names).not.toContain(secret);
  });
});

describe("what the isolation allows", () => {
  const init = (tools: string[], servers: Array<{ name: string; status: string }> = []) =>
    `${JSON.stringify({ type: "system", subtype: "init", session_id: "s1", tools, mcp_servers: servers })}\n`;
  const after = `${JSON.stringify({ type: "stream_event", session_id: "s1", api_message_id: "m", event: { type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "ZZTEXT" } } })}\n`;

  it("aborts the turn before the agent acts when a tool outside the allowed set is listed", async () => {
    const t = await setup();
    const events = await turn({ stdout: [init(["Read", "Edit", "Bash"]), after] })(t);
    expect(events).toEqual([
      { type: "session", sessionId: "s1" },
      { type: "error", code: "isolation_failed", message: expect.stringContaining("Bash") },
      { type: "done", reason: "failed" },
    ]);
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
  });

  it("aborts the turn when any MCP server is connected", async () => {
    const t = await setup();
    const events = await turn({ stdout: [init(["Read"], [{ name: "server-a", status: "connected" }]), after] })(t);
    expect(events.find((event) => event.type === "error")).toMatchObject({ code: "isolation_failed", message: expect.stringContaining("server-a") });
    expect(JSON.stringify(events)).not.toContain("ZZTEXT");
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
  });

  it("lets a turn with exactly the allowed tools and no server go on", async () => {
    const t = await setup();
    const events = await turn({ stdout: [init(["Read", "Edit", "Write", "Glob", "Grep"]), after, `${JSON.stringify({ type: "result", subtype: "success", is_error: false, session_id: "s1" })}\n`], exit: ok })(t);
    expect(JSON.stringify(events)).toContain("ZZTEXT");
    expect(t.spawner.signals).toEqual([]);
  });

  it("aborts on the isolation violation fixture", async () => {
    const t = await setup();
    const events = await turn({ stdout: fixture("isolation-violation.jsonl").map((line) => `${line}\n`) })(t);
    expect(events.find((event) => event.type === "error")).toMatchObject({ code: "isolation_failed" });
    expect(types(events).filter((type) => type === "text_delta")).toEqual([]);
  });
});

describe("the fallback tiers", () => {
  it("tier I2 loads the project settings only and uses the agent file", async () => {
    const t = await setup({ tier: "I2" });
    await turn(EDIT)(t);
    const args = t.spawner.calls[0]!.args;
    expect(args).toEqual([
      "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages", "--permission-mode", "acceptEdits",
      "--setting-sources", "project", "--strict-mcp-config", "--disable-slash-commands", "--agent", "caztor",
      "--model", CLAUDE_DEFAULT_MODEL,
    ]);
    expect(t.runner.isolation).toBe("I2");
  });

  it.each([".mcp.json", ".claude/settings.json", ".claude/settings.local.json"])("blocks the turn while %s exists and nobody confirmed it, whatever the tier", async (name) => {
    for (const tier of ["I1", "I2", "I3"] as const) {
      const t = await setup({ tier, projectConfigConfirmed: async () => false }, { [`${ROOT}/${name}`]: "{}" });
      const events = await turn(EDIT)(t);
      expect(t.spawner.calls).toEqual([]);
      expect(events[0]).toMatchObject({ type: "error", code: "isolation_failed", message: expect.stringContaining(name) });
      expect(events[0]).toMatchObject({ message: expect.stringContaining("Trust this project's CLI configuration") });
      expect(types(events).at(-1)).toBe("done");
    }
  });

  it("blocks the turn when nothing was ever confirmed, because no confirmation function is wired", async () => {
    const t = await setup({}, { [`${ROOT}/.mcp.json`]: "{}" });
    const events = await turn(EDIT)(t);
    expect(t.spawner.calls).toEqual([]);
    expect(events[0]).toMatchObject({ code: "isolation_failed" });
  });

  it("goes on once the project configuration was confirmed, or when there is none", async () => {
    const confirmed = await setup({ projectConfigConfirmed: async () => true }, { [`${ROOT}/.mcp.json`]: "{}" });
    await turn(EDIT)(confirmed);
    expect(confirmed.spawner.calls).toHaveLength(1);
    const none = await setup({ projectConfigConfirmed: async () => false });
    await turn(EDIT)(none);
    expect(none.spawner.calls).toHaveLength(1);
  });

  it("asks about the fingerprint of the files it found, so a confirmation stops counting when they change", async () => {
    const asked: string[] = [];
    const t = await setup({ projectConfigConfirmed: async (fingerprint) => (asked.push(fingerprint), false) }, { [`${ROOT}/.mcp.json`]: '{"a":1}' });
    const found = await t.runner.projectConfig?.();
    await turn(EDIT)(t);
    expect(found).toMatchObject({ files: [".mcp.json"], fingerprint: expect.stringMatching(/^sha256:/) });
    expect(asked).toEqual([found?.fingerprint]);
  });

  it("tier I3 passes no isolation flag, says isolation is unavailable and accepts the servers it cannot remove", async () => {
    const t = await setup({ tier: "I3" });
    const events = await turn({
      stdout: [`${JSON.stringify({ type: "system", subtype: "init", session_id: "s1", tools: ["Read", "Edit"], mcp_servers: [{ name: "server-a", status: "connected" }] })}\n`, `${JSON.stringify({ type: "result", subtype: "success", is_error: false, session_id: "s1" })}\n`],
      exit: ok,
    })(t);
    const args = t.spawner.calls[0]!.args;
    for (const flag of ["--setting-sources", "--strict-mcp-config", "--tools", "--agents", "--disable-slash-commands"]) expect(args).not.toContain(flag);
    expect(args).toContain("--agent");
    expect(events[0]).toEqual({ type: "notice", level: "warning", message: expect.stringContaining("Isolation") });
    expect(events.some((event) => event.type === "error")).toBe(false);
  });
});

describe("when the CLI misbehaves", () => {
  it("fails with the end of its error output when it exits without a result", async () => {
    const t = await setup();
    const events = await turn({ stdout: [fixture("edit-turn.jsonl")[6]! + "\n"], stderr: ["noise\n", "fatal: boom\n"], exit: { code: 1, signal: null } })(t);
    expect(events.slice(-2)).toEqual([
      { type: "error", code: "provider_error", message: "Claude Code stopped before it finished its answer.", detail: expect.stringContaining("fatal: boom") },
      { type: "done", reason: "failed" },
    ]);
  });

  it("ends the turn and stops the process after twenty unreadable lines", async () => {
    const t = await setup();
    const events = await turn({ stdout: Array.from({ length: 25 }, () => "not json\n") })(t);
    expect(events.map((event) => event.type)).toEqual(["error", "done"]);
    expect(events[0]).toMatchObject({ code: "malformed_output" });
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
  });

  it("reads lines that arrive in pieces, also inside a multi-byte character", async () => {
    const t = await setup();
    const text = `${JSON.stringify({ type: "result", subtype: "success", is_error: false, result: "caf\u00e9", session_id: "s9" })}\n`;
    const bytes = new TextEncoder().encode(text);
    const cut = text.indexOf("\u00e9") + 4;
    const events = await turn({ stdout: [bytes.slice(0, cut), bytes.slice(cut, cut + 1), bytes.slice(cut + 1)], exit: ok })(t);
    expect(events).toEqual([{ type: "session", sessionId: "s9" }, { type: "done", reason: "completed" }]);
  });

  it("drops a line that has no end within the size limit and goes on with the next", async () => {
    const t = await setup();
    const huge = "x".repeat(1_100_000);
    const events = await turn({ stdout: [huge.slice(0, 600_000), huge.slice(600_000), "\n", `${JSON.stringify({ type: "result", subtype: "success", is_error: false, session_id: "s2" })}\n`], exit: ok })(t);
    expect(events.at(-1)).toEqual({ type: "done", reason: "completed" });
    expect(events.filter((event) => event.type === "notice")).toHaveLength(1);
  });

  it("gives one warning for several dropped lines of a turn, from the line reader and from the mapper together", async () => {
    const t = await setup();
    const huge = "x".repeat(1_100_000);
    const events = await turn({ stdout: [huge, "\n", huge, "\n", `${JSON.stringify({ type: "result", subtype: "success", is_error: false, session_id: "s2" })}\n`], exit: ok })(t);
    expect(events.filter((event) => event.type === "notice")).toHaveLength(1);
    expect(events.at(-1)).toEqual({ type: "done", reason: "completed" });
  });

  it("says one done, last, however the process ends", async () => {
    const t = await setup();
    const events = await turn({ stdout: fixture("edit-turn.jsonl").map((line) => `${line}\n`), exit: { code: 3, signal: null } })(t);
    expect(events.filter((event) => event.type === "done")).toHaveLength(1);
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });

  it("reports a binary that disappeared after detection as a failed turn", async () => {
    const t = await setup();
    t.spawner.enqueue({ spawnError: "ENOENT" });
    const events = await collect(t.runner.runTurn(request(), new AbortController().signal));
    expect(events).toEqual([
      { type: "error", code: "not_installed", message: "Claude Code could not be started. Is it installed?" },
      { type: "done", reason: "failed" },
    ]);
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
    expect(t.clock.pendingTimers).toBe(0);
  });

  it("goes on to SIGTERM after 3 s and SIGKILL 2 s later when the CLI ignores the signals", async () => {
    const { t, controller, finished, pause } = await running({ ignores: ["SIGINT", "SIGTERM"] });
    controller.abort();
    await pause();
    expect(t.spawner.signals).toEqual(["SIGINT"]);
    t.clock.advance(STOP_ESCALATION_MS.term - 1);
    expect(t.spawner.signals).toEqual(["SIGINT"]);
    t.clock.advance(1);
    expect(t.spawner.signals).toEqual(["SIGINT", "SIGTERM"]);
    t.clock.advance(STOP_ESCALATION_MS.kill - 1);
    expect(t.spawner.signals).toEqual(["SIGINT", "SIGTERM"]);
    t.clock.advance(1);
    await finished;
    expect(t.spawner.signals).toEqual(["SIGINT", "SIGTERM", "SIGKILL"]);
    expect(STOP_ESCALATION_MS).toEqual({ term: 3000, kill: 2000 });
  });

  it("stops at once when the signal was already aborted, without starting the CLI", async () => {
    const t = await setup();
    const controller = new AbortController();
    controller.abort();
    const events = await collect(t.runner.runTurn(request(), controller.signal));
    expect(t.spawner.calls).toEqual([]);
    expect(events).toEqual([{ type: "done", reason: "cancelled" }]);
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
  const probe = async (script: ChildScript, options: Partial<ClaudeRunnerOptions> = {}, files: Record<string, string> = {}) => {
    const t = await setup(options, files);
    t.spawner.enqueue(script);
    return { t, status: await t.runner.detect() };
  };

  it("reports the version from claude --version", async () => {
    const { t, status } = await probe({ stdout: ["2.1.304 (Claude Code)\n"], exit: ok });
    expect(status).toEqual({ provider: "claude", installed: true, version: "2.1.304", requiresModel: false, models: [...CLAUDE_MODELS], defaultModel: "claude-sonnet-5-5" });
    expect(CLAUDE_MODELS).toEqual(["claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"]);
    expect(t.spawner.calls[0]).toMatchObject({ file: BINARY, args: ["--version"], cwd: ROOT });
    expect(CLAUDE_TESTED_VERSION).toBe("2.1.296");
  });

  it("warns about a version older than the tested one, and not about a newer or equal one", async () => {
    const old = await probe({ stdout: ["2.0.9 (Claude Code)\n"], exit: ok });
    expect(old.status.installed && old.status.versionWarning).toContain("2.1.296");
    const same = await probe({ stdout: ["2.1.296 (Claude Code)\n"], exit: ok });
    expect(same.status.versionWarning).toBeUndefined();
    const newer = await probe({ stdout: ["10.0.1 (Claude Code)\n"], exit: ok });
    expect(newer.status.versionWarning).toBeUndefined();
  });

  it("says it is not installed when no PATH folder holds an executable file of that name", async () => {
    const fs = new MemoryFileSystem({ "/usr/bin/claude": "not executable" });
    const spawner = new FakeSpawner();
    const runner = createClaudeRunner({ fs, spawner, clock: new FakeClock(), root: ROOT, env: ENV });
    expect(await runner.detect()).toEqual({ provider: "claude", installed: false, unavailableReason: "Claude Code was not found on the PATH.", requiresModel: false });
    expect(spawner.calls).toEqual([]);
  });

  it("says why it cannot run: a failing exit, output it does not know, silence", async () => {
    const failing = await probe({ stderr: ["segfault\n"], exit: { code: 139, signal: null } });
    expect(failing.status).toMatchObject({ installed: false, unavailableReason: expect.stringContaining("segfault") });
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
    expect(await pending).toMatchObject({ installed: false, unavailableReason: "Claude Code did not answer --version within 5 seconds." });
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
  });
});

describe("finding the binary", () => {
  const fsWith = async (files: Record<string, number>) => {
    const fs = new MemoryFileSystem(Object.fromEntries(Object.keys(files).map((path) => [path, "x"])));
    for (const [path, mode] of Object.entries(files)) await fs.chmod(path, mode);
    return fs;
  };

  it("takes the first executable file in PATH order", async () => {
    const fs = await fsWith({ "/a/claude": 0o755, "/b/claude": 0o755 });
    expect(await resolveBinary(fs, "claude", "/b:/a")).toBe("/b/claude");
  });

  it("skips a file that cannot be executed, a folder, and a relative PATH entry", async () => {
    const fs = await fsWith({ "/a/claude": 0o644, "/c/claude": 0o755 });
    await fs.mkdir("/d/claude", { recursive: true });
    const looked: string[] = [];
    const watching = Object.create(fs, { stat: { value: (path: string) => (looked.push(path), fs.stat(path)) } }) as MemoryFileSystem;
    expect(await resolveBinary(watching, "claude", "rel:/d:/a:/c")).toBe("/c/claude");
    expect(looked).toEqual(["/d/claude", "/a/claude", "/c/claude"]);
  });

  it("returns null when there is none, and for an empty PATH", async () => {
    const fs = await fsWith({ "/a/claude": 0o644 });
    expect(await resolveBinary(fs, "claude", "/a")).toBeNull();
    expect(await resolveBinary(fs, "claude", "")).toBeNull();
    expect(await resolveBinary(fs, "claude", undefined)).toBeNull();
  });
});

describe("auth modes", () => {
  const STORED = "sk-stored-claude-key-0001";
  const THREE = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"];

  it("in account mode (also when the request names no mode) removes the three Anthropic variables and never reads a stored key", async () => {
    for (const authMode of [undefined, "account"] as const) {
      const reader = fakeReader({ claude: STORED });
      const t = await setup({ credentials: reader });
      await turn(EDIT, request(authMode === undefined ? {} : { authMode }))(t);
      const env = t.spawner.calls[0]!.env;
      for (const name of THREE) expect(Object.keys(env)).not.toContain(name);
      expect(env["CLAUDE_CODE_OAUTH_TOKEN"]).toBe("oauth-token");
      expect(env["CLAUDE_CONFIG_DIR"]).toBe("/home/user/.claude-work");
      expect(JSON.stringify(env)).not.toContain(STORED);
      expect(reader.reads).toEqual([]);
    }
  });

  it("in api mode gives the child the stored key only, without the server's Anthropic variables or the OAuth token", async () => {
    const reader = fakeReader({ claude: STORED, codex: "sk-stored-codex-key-0002" });
    const t = await setup({ credentials: reader });
    const events = await turn(EDIT, request({ authMode: "api" }))(t);
    const call = t.spawner.calls[0]!;
    expect(call.env["ANTHROPIC_API_KEY"]).toBe(STORED);
    expect(Object.keys(call.env)).not.toContain("ANTHROPIC_AUTH_TOKEN");
    expect(Object.keys(call.env)).not.toContain("ANTHROPIC_BASE_URL");
    expect(Object.keys(call.env)).not.toContain("CLAUDE_CODE_OAUTH_TOKEN");
    expect(call.env["CLAUDE_CONFIG_DIR"]).toBe("/home/user/.claude-work");
    expect(JSON.stringify(call.env)).not.toContain("sk-stored-codex-key-0002");
    expect(reader.reads).toEqual(["claude"]);
    expect(types(events).at(-1)).toBe("done");
  });

  it("keeps the stored key out of the arguments and the prompt", async () => {
    const t = await setup({ credentials: fakeReader({ claude: STORED }) });
    await turn(EDIT, request({ authMode: "api" }))(t);
    const call = t.spawner.calls[0]!;
    expect(call.args.join(" ")).not.toContain(STORED);
    expect(call.stdin).toBe("Fix the typo");
  });

  it("does not start a turn in api mode when no key is stored, and says so", async () => {
    const t = await setup({ credentials: fakeReader({}) });
    t.spawner.enqueue(EDIT);
    const events = await collect(t.runner.runTurn(request({ authMode: "api" }), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(events).toEqual([
      { type: "error", code: "auth", message: expect.stringContaining("API key") },
      { type: "done", reason: "failed" },
    ]);
  });

  it("does not start a turn in api mode when the store refuses, and shows the store's message", async () => {
    const reader = fakeReader({ claude: STORED }, { code: "unsafe_permissions", message: "The Caztor key file can be reached by other users." });
    const t = await setup({ credentials: reader });
    const events = await collect(t.runner.runTurn(request({ authMode: "api" }), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(events[0]).toEqual({ type: "error", code: "auth", message: "The Caztor key file can be reached by other users." });
  });

  it("does not start a turn in api mode when the runner has no key reader", async () => {
    const t = await setup();
    const events = await collect(t.runner.runTurn(request({ authMode: "api" }), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(events[0]).toMatchObject({ type: "error", code: "auth" });
  });

  it("probes the version with the account environment", async () => {
    const t = await setup({ credentials: fakeReader({ claude: STORED }) });
    t.spawner.enqueue({ stdout: ["2.1.296 (Claude Code)\n"], exit: ok });
    await t.runner.detect();
    const env = t.spawner.calls[0]!.env;
    for (const name of THREE) expect(Object.keys(env)).not.toContain(name);
  });
});

describe("a stored key echoed by the CLI", () => {
  it("is masked in the tapped lines and in every event, also from the end of the error output", async () => {
    const KEY = "sk-echoed-claude-key-77";
    const tapped: string[] = [];
    const t = await setup({ credentials: fakeReader({ claude: KEY }), tap: (line) => tapped.push(line) });
    t.spawner.enqueue({ stdout: [`{"type":"noise","note":"rejected ${KEY}"}\n`], stderr: [`Invalid API key ${KEY}\n`], exit: { code: 1, signal: null } });
    const events = await collect(t.runner.runTurn(request({ authMode: "api" }), new AbortController().signal));
    expect(tapped.join("\n")).toContain("[redacted]");
    expect(tapped.join("\n")).not.toContain(KEY);
    expect(JSON.stringify(events)).not.toContain(KEY);
    expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
  });
});

describe("isolation does not depend on the sign-in mode", () => {
  const STORED = "sk-stored-claude-key-0001";
  const apiRequest = () => request({ authMode: "api" });

  it("passes the same isolation flags in account and api mode", async () => {
    const account = await setup({ credentials: fakeReader({ claude: STORED }) });
    await turn(EDIT, request({ authMode: "account" }))(account);
    const api = await setup({ credentials: fakeReader({ claude: STORED }) });
    await turn(EDIT, apiRequest())(api);
    expect(api.spawner.calls[0]!.args).toEqual(account.spawner.calls[0]!.args);
  });

  it("still asks for the project's configuration to be trusted in api mode, and reads no key before that is settled", async () => {
    const reader = fakeReader({ claude: STORED });
    const t = await setup({ credentials: reader, projectConfigConfirmed: async () => false }, { [`${ROOT}/.mcp.json`]: "{}" });
    t.spawner.enqueue(EDIT);
    const events = await collect(t.runner.runTurn(apiRequest(), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(reader.reads).toEqual([]);
    expect(events[0]).toMatchObject({ type: "error", code: "isolation_failed" });
  });

  it("still aborts on a tool outside the allowed set in api mode, and the message holds no key", async () => {
    const t = await setup({ credentials: fakeReader({ claude: STORED }) });
    const init = `${JSON.stringify({ type: "system", subtype: "init", session_id: "s1", tools: ["Read", "Bash"], mcp_servers: [] })}\n`;
    const events = await turn({ stdout: [init] }, apiRequest())(t);
    expect(events).toContainEqual({ type: "error", code: "isolation_failed", message: expect.stringContaining("Bash") });
    expect(JSON.stringify(events)).not.toContain(STORED);
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
  });
});

describe("the default model", () => {
  it("is claude-sonnet-5-5 when none is chosen, and a chosen one replaces it", async () => {
    const plain = await setup();
    plain.spawner.enqueue({ stdout: [], exit: ok });
    await collect(plain.runner.runTurn(request(), new AbortController().signal));
    const args = plain.spawner.calls.at(-1)?.args ?? [];
    expect(args.slice(args.indexOf("--model"), args.indexOf("--model") + 2)).toEqual(["--model", CLAUDE_DEFAULT_MODEL]);
    expect(CLAUDE_DEFAULT_MODEL).toBe("claude-sonnet-5-5");

    const chosen = await setup();
    chosen.spawner.enqueue({ stdout: [], exit: ok });
    await collect(chosen.runner.runTurn(request({ model: "claude-opus-5-5" }), new AbortController().signal));
    const chosenArgs = chosen.spawner.calls.at(-1)?.args ?? [];
    expect(chosenArgs.filter((arg) => arg === "--model")).toHaveLength(1);
    expect(chosenArgs[chosenArgs.indexOf("--model") + 1]).toBe("claude-opus-5-5");
  });
});

describe("a collaborator's turn", () => {
  const COLLAB = { PATH: "/usr/bin", HOME: "/cfg/caztor/users/u1/home", CLAUDE_CONFIG_DIR: "/cfg/caztor/users/u1/home/.claude" };

  it("builds the child's environment from the turn's environment instead of the server's", async () => {
    const t = await setup({ sandbox: fakeAgentSandbox().sandbox });
    await turn(EDIT, request({ env: COLLAB, sandbox: { home: COLLAB.HOME } }))(t);
    expect(t.spawner.calls[0]!.env).toEqual({ ...COLLAB, CLAUDE_CODE_DISABLE_AUTO_MEMORY: "1", NO_COLOR: "1" });
  });

  it("reads the api key from the turn's own key reader, never the server's", async () => {
    const host = fakeReader({ claude: "sk-host-claude-key-0001" });
    const own = fakeReader({ claude: "sk-collaborator-key-0003" });
    const t = await setup({ credentials: host, sandbox: fakeAgentSandbox().sandbox });
    await turn(EDIT, request({ authMode: "api", env: COLLAB, sandbox: { home: COLLAB.HOME }, credentials: own }))(t);
    expect(t.spawner.calls[0]!.env["ANTHROPIC_API_KEY"]).toBe("sk-collaborator-key-0003");
    expect(host.reads).toEqual([]);
  });
});

describeSandboxedTurns({
  setup: async (options) => setup(options),
  request,
  script: EDIT,
  binary: BINARY,
});
