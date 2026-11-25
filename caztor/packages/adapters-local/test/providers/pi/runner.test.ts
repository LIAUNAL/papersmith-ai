import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { AgentDefinition, AgentEvent, TurnRequest } from "@caztor/core";
import { describe, expect, it, vi } from "vitest";
import {
  createPiRunner,
  PI_ISOLATION_TIER,
  PI_LOGIN_HINT,
  PI_PARTIAL_ISOLATION_NOTICE,
  PI_TESTED_VERSION,
  type PiRunnerOptions,
} from "../../../src/providers/pi/runner.ts";
import { FakeClock } from "../../fakes/fake-clock.ts";
import { FakeSpawner, type ChildScript } from "../../fakes/fake-spawner.ts";
import { MemoryFileSystem } from "../../fakes/memory-fs.ts";
import { describeSandboxedTurns } from "../../support/sandboxed-turns.ts";
import { fakeAgentSandbox } from "../../fakes/fake-agent-sandbox.ts";

const fixture = (name: string): string[] => readFileSync(fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url)), "utf8").split("\n").filter((line) => line !== "").map((line) => `${line}\n`);
const ROOT = "/work/project";
const BINARY = "/usr/local/bin/pi";
const PROMPT_FILE = `${ROOT}/.caztor/agents/pi.md`;
const SESSION_DIR = `${ROOT}/.caztor/pi-sessions`;
const SESSION_1 = "00000000-0000-4000-8000-000000000001";
const NEW_SESSION = "00000000-0000-4000-8000-0000000000aa";
const hash = `sha256:${"a".repeat(64)}` as AgentDefinition["hash"];
const agent: AgentDefinition = { hash, name: "caztor", description: "LaTeX assistant", prompt: "You edit LaTeX.", tools: [] };
const request = (extra: Partial<TurnRequest> = {}): TurnRequest => ({ prompt: "Fix the typo", sessionId: null, model: null, agent, ...extra });
const ok = { code: 0, signal: null };

const ENV = {
  PATH: "/usr/local/bin:/usr/bin",
  HOME: "/home/user",
  LANG: "en_US.UTF-8",
  TMPDIR: "/tmp",
  HTTPS_PROXY: "http://proxy:3128",
  ANTHROPIC_API_KEY: "sk-ant-parent-key-0000",
  OPENAI_API_KEY: "sk-parent-openai-0000",
  GEMINI_API_KEY: "parent-gemini-key-0000",
  PI_CODING_AGENT_SESSION_DIR: "/somewhere/else",
  CLAUDE_CODE_SESSION_ID: "parent-session",
  GITHUB_TOKEN: "ghp_secret_parent_token",
};

const STORED_KEY = "sk-ant-stored-secret-5678";

async function setup(options: Partial<PiRunnerOptions> = {}, files: Record<string, string> = { [PROMPT_FILE]: "# Caztor\n" }) {
  const fs = new MemoryFileSystem({ [BINARY]: "#!/bin/sh", ...files });
  await fs.chmod(BINARY, 0o755);
  const spawner = new FakeSpawner();
  const clock = new FakeClock(1000);
  const runner = createPiRunner({ fs, spawner, clock, root: ROOT, env: ENV, newSessionId: () => NEW_SESSION, ...options });
  return { fs, spawner, clock, runner };
}

async function collect(iterable: AsyncIterable<AgentEvent>): Promise<AgentEvent[]> {
  const out: AgentEvent[] = [];
  for await (const event of iterable) out.push(event);
  return out;
}

async function turn(script: ChildScript, req: Partial<TurnRequest> = {}, options: Partial<PiRunnerOptions> = {}) {
  const t = await setup(options);
  t.spawner.enqueue(script);
  const events = await collect(t.runner.runTurn(request(req), new AbortController().signal));
  return { ...t, events, call: t.spawner.calls[0] };
}

const types = (events: AgentEvent[]) => events.map((event) => event.type);
const credentials = { read: async (slot: string) => ({ ok: true as const, value: slot === "pi:anthropic" ? STORED_KEY : null }) };

const ARGS_BEFORE_SESSION = [
  "-p", "--mode", "json",
  "-na", "-ne", "--no-mcp", "-ns", "-np", "--no-themes", "-nc", "--offline",
  "--tools", "read,edit,write,grep,find,ls",
  "-xt", "mcp__*",
  "--system-prompt", PROMPT_FILE,
  "--append-system-prompt", "",
];

describe("the Pi runner", () => {
  it("exposes the provider id and the partial isolation tier", async () => {
    const { runner } = await setup();
    expect(runner.provider).toBe("pi");
    expect(runner.isolation).toBe(PI_ISOLATION_TIER);
  });

  describe("a whole turn", () => {
    it("reads, edits and answers with the exact argv, without repeating the isolation notice the chat panel already shows", async () => {
      const { events, call } = await turn({ stdout: fixture("synthetic-edit-turn.jsonl"), exit: ok }, { prompt: "Change cat to dog" });
      expect(call?.file).toBe(BINARY);
      expect(call?.cwd).toBe(ROOT);
      expect(call?.args).toEqual([...ARGS_BEFORE_SESSION, "--session-id", NEW_SESSION, "--session-dir", SESSION_DIR]);
      expect(call?.stdin).toBe("Change cat to dog");
      expect(events).not.toContainEqual({ type: "notice", level: "info", message: PI_PARTIAL_ISOLATION_NOTICE });
      expect(events).toContainEqual({ type: "session", sessionId: SESSION_1 });
      expect(events.filter((event) => event.type === "tool_start").map((event) => event.type === "tool_start" && event.name)).toEqual(["read", "edit"]);
      expect(events.at(-1)).toEqual({ type: "done", reason: "completed", usage: { inputTokens: 3900, outputTokens: 105 } });
    });

    it.each([["--tools bash"], ["@main.tex fix the intro"], ["@/etc/hosts"]])("sends the prompt %j on stdin, so Pi never reads it as an option or a file", async (prompt) => {
      const { call } = await turn({ stdout: fixture("synthetic-edit-turn.jsonl"), exit: ok }, { prompt });
      expect(call?.stdin).toBe(prompt);
      expect(call?.args).not.toContain(prompt);
      expect(call?.args).not.toContain("--");
      expect(call?.args.filter((arg) => arg === "--tools")).toHaveLength(1);
    });

    it("passes a chosen model, and refuses a hostile one without spawning", async () => {
      const chosen = await turn({ stdout: fixture("synthetic-edit-turn.jsonl"), exit: ok }, { model: "anthropic/claude-sonnet-4-5" });
      expect(chosen.call?.args.slice(-2)).toEqual(["--model", "anthropic/claude-sonnet-4-5"]);
      expect(chosen.call?.stdin).toBe("Fix the typo");
      const hostile = await turn({}, { model: "--api-key=x" });
      expect(hostile.events).toEqual([{ type: "error", code: "model_unavailable", message: "The model name cannot start with a dash." }, { type: "done", reason: "failed" }]);
      expect(hostile.spawner.calls).toHaveLength(0);
    });
  });

  describe("the tool guard", () => {
    it("stops the turn with SIGTERM when bash appears, shows no tool card and drops later events", async () => {
      // The child stays alive until a signal ends it, as a CLI in the middle of a turn does.
      const { events, spawner } = await turn({ stdout: fixture("synthetic-disallowed-tool.jsonl") });
      expect(events.find((event) => event.type === "error")).toEqual({ type: "error", code: "isolation_failed", message: "Pi used a tool that Caztor does not allow (bash), so the turn was stopped." });
      expect(events.some((event) => event.type === "tool_start" || event.type === "text")).toBe(false);
      expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
      expect(types(events).filter((type) => type === "done")).toHaveLength(1);
      expect(spawner.signals).toEqual(["SIGTERM"]);
    });

    it.each([["mcp__github__create_issue"], ["codemode"], ["tool_search"], ["powershell"], [""]])("stops a call to %j", async (toolName) => {
      const start = `${JSON.stringify({ type: "message_update", assistantMessageEvent: { type: "toolcall_start", id: "c1", toolName } })}\n`;
      const { events, spawner } = await turn({ stdout: [start] });
      expect(events.find((event) => event.type === "error")).toMatchObject({ code: "isolation_failed", message: expect.stringContaining(toolName || "unnamed") });
      expect(spawner.signals).toEqual(["SIGTERM"]);
    });

    it("lets every allowed tool through", async () => {
      for (const toolName of ["read", "edit", "write", "grep", "find", "ls"]) {
        const start = `${JSON.stringify({ type: "message_update", assistantMessageEvent: { type: "toolcall_start", id: "c1", toolName } })}\n`;
        const { events } = await turn({ stdout: [start, ...fixture("synthetic-edit-turn.jsonl").slice(-1)], exit: ok });
        expect(events.some((event) => event.type === "error"), toolName).toBe(false);
      }
    });
  });

  describe("failures", () => {
    it("reports not signed in from exit 1 with the login hint", async () => {
      const { events } = await turn({ stdout: [], stderr: ["No models available. Use /login to log into a provider via OAuth or API key. See:\n"], exit: { code: 1, signal: null } });
      expect(events.slice(-2)).toEqual([{ type: "error", code: "auth", message: PI_LOGIN_HINT }, { type: "done", reason: "failed" }]);
    });

    it("reports an unknown model", async () => {
      const { events } = await turn({ stdout: [], stderr: ['Model "anthropic/nope" not found. Use --list-models to see available models.\n'], exit: { code: 1, signal: null } }, { model: "anthropic/nope" });
      expect(events.slice(-2)).toEqual([
        { type: "error", code: "model_unavailable", message: 'Model "anthropic/nope" not found. Use --list-models to see available models.' },
        { type: "done", reason: "failed" },
      ]);
    });

    it("reports a rate limit after retries, though the CLI exits 0", async () => {
      const { events } = await turn({ stdout: fixture("synthetic-rate-limit.jsonl"), exit: ok });
      expect(events.slice(-2)).toEqual([{ type: "error", code: "rate_limited", message: "429 Too Many Requests: rate limit exceeded after 2 retries" }, { type: "done", reason: "failed" }]);
    });

    it("reports a failed response, though the CLI exits 0", async () => {
      const { events } = await turn({ stdout: fixture("synthetic-failed-response.jsonl"), exit: ok });
      expect(events.slice(-2)).toEqual([{ type: "error", code: "provider_error", message: "400 invalid_request_error: prompt is too long" }, { type: "done", reason: "failed" }]);
    });

    it("gives up on malformed output and stops the process", async () => {
      const { events, spawner } = await turn({ stdout: fixture("synthetic-malformed-line.jsonl") });
      expect(events.slice(-2)).toEqual([{ type: "error", code: "malformed_output", message: "Pi sent output Caztor could not read." }, { type: "done", reason: "failed" }]);
      expect(spawner.signals).toEqual(["SIGTERM"]);
    });

    it("reports a missing binary without spawning", async () => {
      const fs = new MemoryFileSystem({ [PROMPT_FILE]: "# Caztor\n" });
      const spawner = new FakeSpawner();
      const runner = createPiRunner({ fs, spawner, clock: new FakeClock(), root: ROOT, env: { PATH: "/bin" } });
      expect(await collect(runner.runTurn(request(), new AbortController().signal))).toEqual([{ type: "error", code: "not_installed", message: "pi was not found on the PATH." }, { type: "done", reason: "failed" }]);
      expect(spawner.calls).toHaveLength(0);
      expect(await runner.detect()).toEqual({ provider: "pi", installed: false, unavailableReason: "pi was not found on the PATH.", requiresModel: false });
    });

    it("refuses to start without its system prompt file, or when it is a link, since Pi would read the path as text", async () => {
      const missing = await setup({}, {});
      expect((await collect(missing.runner.runTurn(request(), new AbortController().signal))).at(-2)).toMatchObject({ type: "error", code: "isolation_failed" });
      expect(missing.spawner.calls).toHaveLength(0);
      const linked = await setup({}, { [`${ROOT}/other.md`]: "x" });
      await linked.fs.mkdir(`${ROOT}/.caztor/agents`, { recursive: true });
      await linked.fs.symlink(`${ROOT}/other.md`, PROMPT_FILE);
      expect((await collect(linked.runner.runTurn(request(), new AbortController().signal))).at(-2)).toMatchObject({ type: "error", code: "isolation_failed" });
      expect(linked.spawner.calls).toHaveLength(0);
    });

    it("refuses a session folder that is a link", async () => {
      const t = await setup({}, { [PROMPT_FILE]: "# Caztor\n", [`${ROOT}/elsewhere/x`]: "x" });
      await t.fs.symlink(`${ROOT}/elsewhere`, SESSION_DIR);
      const events = await collect(t.runner.runTurn(request(), new AbortController().signal));
      expect(events.at(-2)).toMatchObject({ type: "error", code: "isolation_failed", message: expect.stringContaining("symbolic link") });
      expect(t.spawner.calls).toHaveLength(0);
    });
  });

  describe("session continuation", () => {
    it("continues a stored UUID session and creates the session folder", async () => {
      const { call, fs } = await turn({ stdout: fixture("synthetic-edit-turn.jsonl"), exit: ok }, { sessionId: SESSION_1 });
      expect(call?.args).toContain("--session-id");
      expect(call?.args[call.args.indexOf("--session-id") + 1]).toBe(SESSION_1);
      expect((await fs.lstat(SESSION_DIR)).isDirectory()).toBe(true);
    });

    it("starts a new session instead of passing a hostile id", async () => {
      const { call } = await turn({ stdout: fixture("synthetic-edit-turn.jsonl"), exit: ok }, { sessionId: "../../etc/passwd" });
      expect(call?.args[call.args.indexOf("--session-id") + 1]).toBe(NEW_SESSION);
      expect(call?.args.join(" ")).not.toContain("passwd");
    });
  });

  describe("environment", () => {
    it("in account mode passes only the allowlist, Pi's quiet switches, and no key", async () => {
      const { call } = await turn({ stdout: fixture("synthetic-edit-turn.jsonl"), exit: ok }, {}, { credentials });
      expect(call?.env).toEqual({
        PATH: ENV.PATH,
        HOME: ENV.HOME,
        LANG: ENV.LANG,
        TMPDIR: ENV.TMPDIR,
        HTTPS_PROXY: ENV.HTTPS_PROXY,
        NO_COLOR: "1",
        PI_OFFLINE: "1",
        PI_SKIP_VERSION_CHECK: "1",
        PI_TELEMETRY: "0",
        // A tutor question often comes more than five minutes after the last answer: the prompt cache lasts an hour.
        PI_CACHE_RETENTION: "long",
      });
      expect(call?.args.join(" ")).not.toContain("--api-key");
    });

    it("in api mode gives the stored key only as the vendor's variable, with a private agent folder, never in argv", async () => {
      const { call, events } = await turn({ stdout: fixture("synthetic-edit-turn.jsonl"), exit: ok }, { authMode: "api", model: "anthropic/claude-sonnet-4-5" }, { credentials });
      expect(call?.env["ANTHROPIC_API_KEY"]).toBe(STORED_KEY);
      expect(call?.env["OPENAI_API_KEY"]).toBeUndefined();
      expect(call?.env["GEMINI_API_KEY"]).toBeUndefined();
      expect(call?.env["PI_CODING_AGENT_DIR"]).toBe(`${ROOT}/.caztor/pi-agent-api`);
      expect(call?.args.join(" ")).not.toContain(STORED_KEY);
      expect(call?.args).not.toContain("--api-key");
      expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
    });

    it("in api mode needs a provider/model, a vendor Caztor can pass a key to, and a stored key", async () => {
      const noModel = await turn({}, { authMode: "api" }, { credentials });
      expect(noModel.events).toEqual([{ type: "error", code: "model_required", message: "Choose a Pi model written as provider/model, so Caztor knows which key to use." }, { type: "done", reason: "failed" }]);
      const vendor = await turn({}, { authMode: "api", model: "nowhere/x" }, { credentials });
      expect(vendor.events.at(-2)).toMatchObject({ code: "model_unavailable", message: expect.stringContaining("nowhere") });
      const noKey = await turn({}, { authMode: "api", model: "openai/gpt-5.5" }, { credentials });
      expect(noKey.events.at(-2)).toMatchObject({ code: "auth", message: expect.stringContaining("Pi (openai)") });
      expect([noModel, vendor, noKey].every((t) => t.spawner.calls.length === 0)).toBe(true);
    });
  });

  describe("redaction", () => {
    it("masks the stored key and keys from the environment in every event", async () => {
      const leak = `${JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: `key ${STORED_KEY} and ${ENV.ANTHROPIC_API_KEY}` }], stopReason: "error", errorMessage: `bad ${STORED_KEY}` } })}\n`;
      const tapped: string[] = [];
      const { events } = await turn({ stdout: [leak], stderr: [`boom ${STORED_KEY}\n`], exit: ok }, { authMode: "api", model: "anthropic/claude-sonnet-4-5" }, { credentials, tap: (text) => tapped.push(text) });
      const seen = JSON.stringify(events) + tapped.join("\n");
      expect(seen).not.toContain(STORED_KEY);
      expect(seen).not.toContain(ENV.ANTHROPIC_API_KEY);
      expect(seen).toContain("[redacted]");
    });
  });

  describe("stop escalation", () => {
    it("sends SIGINT, then SIGTERM after 3 s and SIGKILL 2 s later, and ends cancelled", async () => {
      const t = await setup();
      t.spawner.enqueue({ ignores: ["SIGINT", "SIGTERM"] });
      const controller = new AbortController();
      const done = collect(t.runner.runTurn(request(), controller.signal));
      await vi.waitFor(() => expect(t.spawner.calls).toHaveLength(1));
      controller.abort();
      await new Promise<void>((resolve) => setImmediate(resolve));
      expect(t.spawner.signals).toEqual(["SIGINT"]);
      t.clock.advance(3000);
      expect(t.spawner.signals).toEqual(["SIGINT", "SIGTERM"]);
      t.clock.advance(2000);
      const events = await done;
      expect(t.spawner.signals).toEqual(["SIGINT", "SIGTERM", "SIGKILL"]);
      expect(events.at(-1)).toEqual({ type: "done", reason: "cancelled" });
    });
  });

  describe("detection", () => {
    it("reads the version and the signed-in models, outside the project, and removes its folder", async () => {
      const { runner, spawner, fs } = await setup();
      spawner.enqueue({ stdout: ["1.4.0\n"], exit: ok });
      spawner.enqueue({
        stdout: [
          "provider   model                context  max-out  thinking  images\n",
          "anthropic  claude-sonnet-4-5    200K     64K      yes       yes\n",
          "openai     gpt-5.5              400K     128K     yes       yes\n",
          "bad;name   x                    1K       1K       no        no\n",
        ],
        exit: ok,
      });
      expect(await runner.detect()).toEqual({ provider: "pi", installed: true, version: "1.4.0", requiresModel: false, models: ["anthropic/claude-sonnet-4-5", "openai/gpt-5.5"] });
      expect(spawner.calls.map((call) => call.args)).toEqual([["--version"], ["--offline", "-na", "-ne", "--no-mcp", "--list-models"]]);
      for (const call of spawner.calls) expect(call.cwd.startsWith(ROOT)).toBe(false);
      expect(await fs.lstat(spawner.calls[0]!.cwd).then(() => true, () => false)).toBe(false);
    });

    it("gives no model list when nobody is signed in, and warns about an older version", async () => {
      const { runner, spawner } = await setup();
      spawner.enqueue({ stdout: ["1.3.9\n"], exit: ok });
      spawner.enqueue({ stdout: ["No models available. Use /login to log into a provider via OAuth or API key. See:\n"], exit: ok });
      expect(await runner.detect()).toEqual({
        provider: "pi",
        installed: true,
        version: "1.3.9",
        requiresModel: false,
        versionWarning: `Caztor was tested with pi ${PI_TESTED_VERSION} or newer; this version may behave differently.`,
      });
    });
  });
});

describe("a collaborator's turn", () => {
  it("builds the child's environment from the turn's environment", async () => {
    const env = { PATH: "/usr/bin", HOME: "/cfg/u/home", PI_CODING_AGENT_DIR: "/cfg/u/home/.pi/agent" };
    const { call } = await turn({ stdout: fixture("synthetic-edit-turn.jsonl"), exit: ok }, { env, sandbox: { home: env.HOME } }, { sandbox: fakeAgentSandbox().sandbox });
    expect(call?.env).toMatchObject(env);
    expect(Object.values(call!.env)).not.toContain(ENV.HOME);
  });
});

describeSandboxedTurns({
  setup: async (options) => setup(options),
  request,
  script: { stdout: fixture("synthetic-edit-turn.jsonl"), exit: ok },
  binary: BINARY,
});
