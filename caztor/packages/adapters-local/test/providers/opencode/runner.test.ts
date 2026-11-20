import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { AgentDefinition, AgentEvent, TurnRequest } from "@caztor/core";
import { describe, expect, it, vi } from "vitest";
import {
  createOpencodeRunner,
  OPENCODE_ALLOWED_TOOLS,
  OPENCODE_ISOLATION_TIER,
  OPENCODE_TESTED_VERSION,
  STOP_ESCALATION_MS,
  type OpencodeRunnerOptions,
} from "../../../src/providers/opencode/runner.ts";
import { FakeClock } from "../../fakes/fake-clock.ts";
import { FakeSpawner, type ChildScript } from "../../fakes/fake-spawner.ts";
import { MemoryFileSystem } from "../../fakes/memory-fs.ts";
import { describeSandboxedTurns } from "../../support/sandboxed-turns.ts";
import { fakeAgentSandbox } from "../../fakes/fake-agent-sandbox.ts";
import { fakeReader } from "../../support/credentials.ts";

const fixture = (name: string): string[] => readFileSync(fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url)), "utf8").split("\n").filter((line) => line !== "");
const ROOT = "/work/project";
const BINARY = "/usr/local/bin/opencode";
const AGENT_FILE = `${ROOT}/.opencode/agents/caztor.md`;
const hash = `sha256:${"a".repeat(64)}` as AgentDefinition["hash"];
const agent: AgentDefinition = { hash, name: "caztor", description: "LaTeX assistant", prompt: "You edit LaTeX.", tools: ["edit"] };
const MODEL = "openai/gpt-5.5";
const request = (extra: Partial<TurnRequest> = {}): TurnRequest => ({ prompt: "Fix the typo", sessionId: null, model: MODEL, agent, ...extra });
const ok = { code: 0, signal: null };

const DENIES = "---\ndescription: x\nmode: primary\npermission:\n  edit: allow\n  bash: deny\n  webfetch: deny\n  external_directory: deny\n---\nBody\n";

const ENV = {
  PATH: "/usr/local/bin:/usr/bin",
  HOME: "/home/user",
  LANG: "en_US.UTF-8",
  TMPDIR: "/tmp",
  XDG_DATA_HOME: "/home/user/.data",
  XDG_CONFIG_HOME: "/home/user/.config",
  OPENAI_API_KEY: "sk-test-key",
  OPENCODE_CONFIG: "/home/user/other.json",
  OPENCODE_CONFIG_DIR: "/home/user/oc",
  OPENCODE_CONFIG_CONTENT: "{}",
  GITHUB_TOKEN: "ghp_secret",
  AWS_SECRET_ACCESS_KEY: "aws-secret",
  SECRET_TOKEN: "x",
};

async function setup(options: Partial<OpencodeRunnerOptions> = {}, files: Record<string, string> = { [AGENT_FILE]: DENIES }) {
  const fs = new MemoryFileSystem({ [BINARY]: "#!/bin/sh", ...files });
  await fs.chmod(BINARY, 0o755);
  const spawner = new FakeSpawner();
  const clock = new FakeClock(1000);
  const runner = createOpencodeRunner({ fs, spawner, clock, root: ROOT, env: ENV, ...options });
  return { fs, spawner, clock, runner };
}
type T = Awaited<ReturnType<typeof setup>>;

async function collect(iterable: AsyncIterable<AgentEvent>): Promise<AgentEvent[]> {
  const out: AgentEvent[] = [];
  for await (const event of iterable) out.push(event);
  return out;
}
const types = (events: AgentEvent[]) => events.map((event) => event.type);
const turn = (script: ChildScript, req = request()) => async (t: T) => {
  t.spawner.enqueue(script);
  return collect(t.runner.runTurn(req, new AbortController().signal));
};
const lines = (name: string) => fixture(name).map((line) => `${line}\n`);
const EDIT = { stdout: lines("edit-turn.jsonl"), exit: ok };

describe("the command line", () => {
  it("is the observed set with the agent, the model and the project folder, as an array, with the prompt on stdin", async () => {
    const t = await setup();
    await turn(EDIT)(t);
    const call = t.spawner.calls[0]!;
    expect(OPENCODE_ISOLATION_TIER).toBe("I1");
    expect(call.file).toBe(BINARY);
    expect(call.cwd).toBe(ROOT);
    expect(call.stdin).toBe("Fix the typo");
    expect(call.args).toEqual(["run", "--format", "json", "--agent", "caztor", "--pure", "-m", MODEL, "--dir", ROOT]);
    expect(call.args).not.toContain("--auto");
  });

  it.each(["; rm -rf ~", "--auto", "$(touch /tmp/x) `id`", "-s", "line one\nline two", "-- --model x"])("keeps the prompt %j out of the arguments", async (prompt) => {
    const baseline = await setup();
    await turn(EDIT, request({ prompt: "plain" }))(baseline);
    const t = await setup();
    await turn(EDIT, request({ prompt }))(t);
    expect(t.spawner.calls[0]!.stdin).toBe(prompt);
    expect(t.spawner.calls[0]!.args).toEqual(baseline.spawner.calls[0]!.args);
  });

  it("continues a session with -s", async () => {
    const t = await setup();
    await turn(EDIT, request({ sessionId: "ses_ed293d464fferhCUqDYLIhE0xu" }))(t);
    const args = t.spawner.calls[0]!.args;
    expect(args.slice(args.indexOf("-s"), args.indexOf("-s") + 2)).toEqual(["-s", "ses_ed293d464fferhCUqDYLIhE0xu"]);
  });

  it.each(["--auto", "ses_", "abc", "ses_a b", "ses_$(id)", ""])("starts a new conversation instead of passing the session id %j", async (sessionId) => {
    const t = await setup();
    await turn(EDIT, request({ sessionId }))(t);
    expect(t.spawner.calls[0]!.args).not.toContain("-s");
    expect(t.spawner.calls[0]!.args).not.toContain("--auto");
  });
});

describe("the model", () => {
  const refused = async (model: string | null) => {
    const t = await setup();
    t.spawner.enqueue(EDIT);
    const events = await collect(t.runner.runTurn(request({ model }), new AbortController().signal));
    return { t, events };
  };

  it("is required: without one the turn is not started and the user is asked to set it", async () => {
    for (const model of [null, "", "   "]) {
      const { t, events } = await refused(model);
      expect(t.spawner.calls, String(model)).toEqual([]);
      expect(events).toEqual([
        { type: "error", code: "model_required", message: "Choose a model for opencode before sending a message. Write it as provider/model." },
        { type: "done", reason: "failed" },
      ]);
    }
  });

  it("must be provider/model, so a name without a provider is refused with an example of the form", async () => {
    for (const model of ["gpt-5.5", "openai/", "/gpt", "openai//x", "openai/gpt 5"]) {
      const { t, events } = await refused(model);
      expect(t.spawner.calls, model).toEqual([]);
      expect(events[0], model).toMatchObject({ type: "error", code: "model_unavailable", message: expect.stringContaining("provider/model") });
    }
  });

  it("is refused when it could be read as an option", async () => {
    for (const model of ["--dangerous", "-m", "--x/y"]) {
      const { t, events } = await refused(model);
      expect(t.spawner.calls, model).toEqual([]);
      expect(events[0], model).toMatchObject({ type: "error", code: "model_unavailable", message: expect.stringContaining("dash") });
    }
  });

  it("accepts the forms providers use: a nested path and a variant", async () => {
    for (const model of ["openai/gpt-5.5", "openrouter/anthropic/claude-3.5-sonnet:free", "ollama/llama3.2:3b"]) {
      const t = await setup();
      await turn(EDIT, request({ model }))(t);
      const args = t.spawner.calls[0]!.args;
      expect(args[args.indexOf("-m") + 1]).toBe(model);
    }
  });
});

describe("the environment", () => {
  it("holds what the CLI needs to find its login and the network, points its configuration at an empty folder and turns the other global sources off", async () => {
    const t = await setup();
    await turn(EDIT)(t);
    expect(t.spawner.calls[0]!.env).toEqual({
      PATH: "/usr/local/bin:/usr/bin",
      HOME: "/home/user",
      LANG: "en_US.UTF-8",
      TMPDIR: "/tmp",
      XDG_DATA_HOME: "/home/user/.data",
      XDG_CONFIG_HOME: `${ROOT}/.caztor/opencode-xdg`,
      OPENCODE_DISABLE_CLAUDE_CODE: "1",
      OPENCODE_DISABLE_EXTERNAL_SKILLS: "1",
      OPENCODE_DISABLE_AUTOUPDATE: "1",
      NO_COLOR: "1",
    });
  });

  it("passes no other secret, and none of the variables that point the CLI at a configuration", async () => {
    const t = await setup();
    await turn(EDIT)(t);
    const names = Object.keys(t.spawner.calls[0]!.env);
    for (const other of ["GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "SECRET_TOKEN", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG_CONTENT"]) expect(names).not.toContain(other);
  });

  it("drops every exported provider key and base URL in account mode, so a login in the CLI is never overridden", async () => {
    const exported = {
      ANTHROPIC_API_KEY: "a", ANTHROPIC_BASE_URL: "u", OPENROUTER_API_KEY: "b", OPENCODE_API_KEY: "c", OPENAI_BASE_URL: "d",
      GEMINI_API_KEY: "e", GROQ_API_KEY: "f", XAI_API_KEY: "g", MISTRAL_API_KEY: "h", DEEPSEEK_API_KEY: "i",
      GOOGLE_GENERATIVE_AI_API_KEY: "j", OPENCODE_AUTH_CONTENT: "{}", OPENAI_UNRELATED: "k",
    };
    const t = await setup({ env: { ...ENV, ...exported } });
    await turn(EDIT)(t);
    const names = Object.keys(t.spawner.calls[0]!.env);
    for (const name of [...Object.keys(exported), "OPENAI_API_KEY"]) expect(names).not.toContain(name);
  });
});

describe("auth modes", () => {
  const OPENAI = "sk-openai-stored-0001";
  const ANTHROPIC = "sk-anthropic-stored-0002";
  const DATA_API = `${ROOT}/.caztor/opencode-data-api`;
  const apiRequest = (model = MODEL) => request({ authMode: "api", model });
  const exportedOthers = { ...ENV, ANTHROPIC_API_KEY: "exported-anthropic", OPENAI_API_KEY: "exported-openai" };

  it("in api mode passes only the model vendor's key, from the store, and none of the server's exported keys", async () => {
    const reader = fakeReader({ "opencode:openai": OPENAI, "opencode:anthropic": ANTHROPIC, claude: "sk-claude-stored-0003" });
    const t = await setup({ credentials: reader, env: exportedOthers });
    await turn(EDIT, apiRequest())(t);
    const env = t.spawner.calls[0]!.env;
    expect(env["OPENAI_API_KEY"]).toBe(OPENAI);
    expect(Object.keys(env)).not.toContain("ANTHROPIC_API_KEY");
    expect(JSON.stringify(env)).not.toContain(ANTHROPIC);
    expect(JSON.stringify(env)).not.toContain("sk-claude-stored-0003");
    expect(JSON.stringify(env)).not.toContain("exported-");
    expect(reader.reads).toEqual(["opencode:openai"]);
  });

  it.each([
    ["openai/gpt-5.5", "OPENAI_API_KEY"],
    ["anthropic/claude-sonnet-4-5", "ANTHROPIC_API_KEY"],
    ["google/gemini-3", "GOOGLE_GENERATIVE_AI_API_KEY"],
    ["openrouter/meta/llama", "OPENROUTER_API_KEY"],
    ["groq/llama", "GROQ_API_KEY"],
    ["xai/grok", "XAI_API_KEY"],
    ["mistral/large", "MISTRAL_API_KEY"],
    ["deepseek/chat", "DEEPSEEK_API_KEY"],
    ["opencode/big-pickle", "OPENCODE_API_KEY"],
  ])("maps the vendor of %s to %s", async (model, variable) => {
    const vendor = model.slice(0, model.indexOf("/"));
    const t = await setup({ credentials: fakeReader({ [`opencode:${vendor}`]: "vendor-key-0123456789" }) });
    await turn(EDIT, apiRequest(model))(t);
    const env = t.spawner.calls[0]!.env;
    expect(env[variable]).toBe("vendor-key-0123456789");
    const keyVariables = Object.keys(env).filter((name) => /API_KEY$/.test(name));
    expect(keyVariables).toEqual([variable]);
  });

  it("gives api mode its own data folder (0700), so a login saved by the CLI cannot win, and keeps the config folder", async () => {
    const t = await setup({ credentials: fakeReader({ "opencode:openai": OPENAI }) });
    await turn(EDIT, apiRequest())(t);
    const env = t.spawner.calls[0]!.env;
    expect(env["XDG_DATA_HOME"]).toBe(DATA_API);
    expect(env["XDG_CONFIG_HOME"]).toBe(`${ROOT}/.caztor/opencode-xdg`);
    expect((await t.fs.lstat(DATA_API)).mode).toBe(0o700);
  });

  it("keeps the user's data folder in account mode", async () => {
    const t = await setup({ credentials: fakeReader({ "opencode:openai": OPENAI }) });
    await turn(EDIT, request({ authMode: "account" }))(t);
    expect(t.spawner.calls[0]!.env["XDG_DATA_HOME"]).toBe("/home/user/.data");
  });

  it("refuses api mode when the data folder is a symbolic link, without starting", async () => {
    const t = await setup({ credentials: fakeReader({ "opencode:openai": OPENAI }) });
    t.fs.symlink("/work/elsewhere", DATA_API);
    const events = await collect(t.runner.runTurn(apiRequest(), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(events[0]).toMatchObject({ type: "error", code: "isolation_failed", message: expect.stringContaining("opencode-data-api") });
  });

  it("refuses a vendor without a variable of its own before reading anything or starting", async () => {
    const reader = fakeReader({ "opencode:openai": OPENAI });
    const t = await setup({ credentials: reader });
    const events = await collect(t.runner.runTurn(apiRequest("nowhere/model"), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(reader.reads).toEqual([]);
    expect(events).toEqual([
      { type: "error", code: "model_unavailable", message: expect.stringContaining("nowhere") },
      { type: "done", reason: "failed" },
    ]);
  });

  it.each(["--model/x", "-m/openai", "openai/-x", "openai/gpt 5", "openai"])("does not read a key or start for the hostile model %j", async (model) => {
    const reader = fakeReader({ "opencode:openai": OPENAI });
    const t = await setup({ credentials: reader });
    const events = await collect(t.runner.runTurn(apiRequest(model), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(reader.reads).toEqual([]);
    expect(events[0]).toMatchObject({ type: "error" });
    expect(types(events).at(-1)).toBe("done");
  });

  it("keeps the key out of the arguments and the prompt", async () => {
    const t = await setup({ credentials: fakeReader({ "opencode:openai": OPENAI }) });
    await turn(EDIT, apiRequest())(t);
    const call = t.spawner.calls[0]!;
    expect(call.args.join(" ")).not.toContain(OPENAI);
    expect(call.stdin).toBe("Fix the typo");
  });

  it("does not start a turn in api mode without a stored key for the vendor, naming the vendor", async () => {
    const t = await setup({ credentials: fakeReader({ "opencode:anthropic": ANTHROPIC }) });
    const events = await collect(t.runner.runTurn(apiRequest(), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(events).toEqual([
      { type: "error", code: "auth", message: expect.stringContaining("openai") },
      { type: "done", reason: "failed" },
    ]);
  });

  it("does not start a turn in api mode when the store refuses", async () => {
    const t = await setup({ credentials: fakeReader({}, { code: "linked", message: "The Caztor key folder is a symbolic link." }) });
    const events = await collect(t.runner.runTurn(apiRequest(), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(events[0]).toEqual({ type: "error", code: "auth", message: "The Caztor key folder is a symbolic link." });
  });
});

describe("the agent definition", () => {
  const warning = (events: AgentEvent[]) => events.filter((event) => event.type === "notice");

  it("raises no warning while the file denies commands, web pages and folders outside the project", async () => {
    const t = await setup();
    const events = await turn(EDIT)(t);
    expect(warning(events)).toEqual([]);
  });

  it.each([
    ["bash", "allow"],
    ["bash", "ask"],
    ["webfetch", "allow"],
    ["external_directory", "allow"],
  ])("warns, with the offer to restore the definition, when %s is %s", async (key, value) => {
    const text = DENIES.replace(`${key}: deny`, `${key}: ${value}`);
    const t = await setup({}, { [AGENT_FILE]: text });
    const events = await turn(EDIT)(t);
    expect(events[0]).toEqual({
      type: "notice",
      level: "warning",
      message: `The agent definition no longer denies ${key}, so opencode could use it. Restore Caztor's definition to turn this off.`,
      action: "replace_definition",
    });
    expect(warning(events)).toHaveLength(1);
  });

  it("warns when a key is missing altogether, because opencode allows what a file does not mention", async () => {
    const text = DENIES.replace("  bash: deny\n", "");
    const t = await setup({}, { [AGENT_FILE]: text });
    const events = await turn(EDIT)(t);
    expect(events[0]).toMatchObject({ type: "notice", message: expect.stringContaining("bash") });
  });

  it("names every key that is not denied in one warning", async () => {
    const t = await setup({}, { [AGENT_FILE]: DENIES.replace("bash: deny", "bash: allow").replace("webfetch: deny", "webfetch: ask") });
    const events = await turn(EDIT)(t);
    expect(warning(events)).toEqual([expect.objectContaining({ message: expect.stringContaining("bash, webfetch") })]);
  });

  it("warns when the file cannot be read as a definition", async () => {
    const t = await setup({}, { [AGENT_FILE]: "no frontmatter at all" });
    const events = await turn(EDIT)(t);
    expect(events[0]).toMatchObject({ type: "notice", action: "replace_definition" });
  });

  it("goes on without a warning when the file is not there; opencode then reports it itself", async () => {
    const t = await setup({}, {});
    const events = await turn(EDIT)(t);
    expect(warning(events)).toEqual([]);
  });
});

describe("what the isolation allows", () => {
  it("lists the file tools and nothing that runs a command or reaches the network", () => {
    expect(OPENCODE_ALLOWED_TOOLS).toEqual(expect.arrayContaining(["read", "edit", "write", "apply_patch", "glob", "grep", "list"]));
    for (const tool of ["bash", "webfetch", "websearch", "task", "skill"]) expect(OPENCODE_ALLOWED_TOOLS).not.toContain(tool);
  });

  it("lets a turn that only reads and patches files go on", async () => {
    const t = await setup();
    const events = await turn(EDIT)(t);
    expect(types(events)).toEqual(["session", "tool_start", "tool_end", "tool_start", "tool_end", "text", "done"]);
    expect(t.spawner.signals).toEqual([]);
  });

  it("aborts the turn, and shows nothing of the call, when a finished tool is outside the allowed set", async () => {
    const t = await setup();
    const events = await turn({ stdout: lines("synthetic-isolation-violation.jsonl") })(t);
    expect(events).toEqual([
      { type: "session", sessionId: "ses_FIXTURE0000SESSION" },
      { type: "error", code: "isolation_failed", message: expect.stringContaining("examplemcp_lookup") },
      { type: "done", reason: "failed" },
    ]);
    expect(events.map((event) => event.type)).not.toContain("tool_start");
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
  });

  it("aborts when a tool the CLI does not know as its own fails, because its name shows that a plugin or server is loaded", async () => {
    const t = await setup();
    const call = JSON.stringify({ type: "tool_use", sessionID: "ses_x", part: { type: "tool", tool: "someserver_search", callID: "c", state: { status: "error", input: {}, error: "boom" } } });
    const events = await turn({ stdout: [`${call}\n`] })(t);
    expect(events.find((event) => event.type === "error")).toMatchObject({ code: "isolation_failed" });
  });

  it("aborts when a command ran", async () => {
    const t = await setup();
    const call = JSON.stringify({ type: "tool_use", sessionID: "ses_x", part: { type: "tool", tool: "bash", callID: "c", state: { status: "completed", input: { command: "ls" }, output: "" } } });
    const events = await turn({ stdout: [`${call}\n`] })(t);
    expect(events.find((event) => event.type === "error")).toMatchObject({ code: "isolation_failed", message: expect.stringContaining("bash") });
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
  });

  it("shows a refused command as a failed tool and lets the turn finish", async () => {
    const t = await setup();
    const events = await turn({ stdout: lines("synthetic-denied-bash.jsonl"), exit: ok })(t);
    expect(events).toContainEqual({ type: "tool_end", toolId: "call_FIXTURE0001", status: "failed", summary: expect.stringContaining("rule") });
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
    expect(t.spawner.signals).toEqual([]);
  });

  it("does not mind the CLI naming a tool that does not exist, which does nothing", async () => {
    const t = await setup();
    const call = JSON.stringify({ type: "tool_use", sessionID: "ses_x", part: { type: "tool", tool: "invalid", callID: "c", state: { status: "completed", input: {}, output: "" } } });
    const finish = JSON.stringify({ type: "step_finish", sessionID: "ses_x", part: { reason: "stop", tokens: { input: 1, output: 1 } } });
    const events = await turn({ stdout: [`${call}\n`, `${finish}\n`], exit: ok })(t);
    expect(events.map((event) => event.type)).not.toContain("error");
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });
});

describe("errors from the provider", () => {
  const failing = (name: string) => ({ stdout: lines(name), stderr: ["[plugin] noise that has nothing to do with it\n"], exit: { code: 1, signal: null } });

  it("ends the free-tier refusal as a model problem with the real text kept as detail", async () => {
    const t = await setup();
    const events = await turn(failing("error-free-tier.jsonl"))(t);
    expect(events).toEqual([
      { type: "session", sessionId: "ses_FIXTURE0000SESSION" },
      expect.objectContaining({ type: "error", code: "model_unavailable", detail: "OpenCode's free tier can only be used from within OpenCode" }),
      { type: "done", reason: "failed" },
    ]);
  });

  it("ends a rejected model, an authentication failure and a rate limit with a readable code", async () => {
    const t = await setup();
    const codes: string[] = [];
    for (const name of ["error-model-rejected.jsonl", "synthetic-auth-401.jsonl", "synthetic-rate-limit-429.jsonl"]) {
      const events = await turn(failing(name))(t);
      codes.push((events.find((event) => event.type === "error") as { code: string }).code);
      expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
    }
    expect(codes).toEqual(["model_unavailable", "auth", "rate_limited"]);
  });

  it("does not put the plugin noise on stderr into an error that the CLI explained", async () => {
    const t = await setup();
    const events = await turn(failing("synthetic-auth-401.jsonl"))(t);
    expect(JSON.stringify(events)).not.toContain("noise");
  });
});

describe("when the CLI misbehaves", () => {
  it("fails with the end of its error output when it exits without a step", async () => {
    const t = await setup();
    const events = await turn({ stderr: ["line one\n", "the real reason\n"], exit: { code: 2, signal: null } })(t);
    expect(events).toEqual([
      { type: "error", code: "provider_error", message: "opencode stopped before it finished its answer.", detail: "line one the real reason" },
      { type: "done", reason: "failed" },
    ]);
  });

  it("ends the turn and stops the process after twenty unreadable lines", async () => {
    const t = await setup();
    const events = await turn({ stdout: Array.from({ length: 25 }, () => "nope\n") })(t);
    expect(events).toEqual([
      { type: "error", code: "malformed_output", message: "opencode sent output Caztor could not read." },
      { type: "done", reason: "failed" },
    ]);
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
  });

  it("reads lines that arrive in pieces", async () => {
    const t = await setup();
    const text = lines("edit-turn.jsonl").join("");
    const pieces = [text.slice(0, 77), text.slice(77, 900), text.slice(900)];
    const events = await turn({ stdout: pieces, exit: ok })(t);
    expect(types(events)).toEqual(["session", "tool_start", "tool_end", "tool_start", "tool_end", "text", "done"]);
  });

  it("says one done, last, however the process ends", async () => {
    const t = await setup();
    for (const script of [EDIT, { stdout: lines("edit-turn.jsonl").slice(0, 2), exit: ok }, { exit: ok }, { exit: { code: 1, signal: null } }]) {
      const events = await turn(script)(t);
      expect(events.filter((event) => event.type === "done")).toHaveLength(1);
      expect(events.at(-1)?.type).toBe("done");
    }
  });

  it("ends a process that stays alive after its final step, and still completes", async () => {
    const t = await setup();
    t.spawner.enqueue({ stdout: lines("edit-turn.jsonl") });
    const finished = collect(t.runner.runTurn(request(), new AbortController().signal));
    await vi.waitFor(() => expect(t.spawner.calls).toHaveLength(1));
    await new Promise<void>((resolve) => setImmediate(resolve));
    expect(t.spawner.signals).toEqual([]);
    t.clock.advance(2000);
    const events = await finished;
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
    expect(events.at(-1)).toMatchObject({ type: "done", reason: "completed" });
  });

  it("reports a binary that disappeared after detection as a failed turn", async () => {
    const t = await setup();
    t.spawner.enqueue({ spawnError: "ENOENT" });
    const events = await collect(t.runner.runTurn(request(), new AbortController().signal));
    expect(events).toEqual([
      { type: "error", code: "not_installed", message: "opencode could not be started. Is it installed?" },
      { type: "done", reason: "failed" },
    ]);
  });

  it("reports a missing binary as not installed without starting anything", async () => {
    const t = await setup({ env: { ...ENV, PATH: "/nowhere" } });
    const events = await turn(EDIT)(t);
    expect(t.spawner.calls).toEqual([]);
    expect(events).toEqual([
      { type: "error", code: "not_installed", message: "opencode was not found on the PATH." },
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
    t.clock.advance(STOP_ESCALATION_MS.term);
    expect(t.spawner.signals).toEqual(["SIGINT", "SIGTERM"]);
    t.clock.advance(STOP_ESCALATION_MS.kill);
    await finished;
    expect(t.spawner.signals).toEqual(["SIGINT", "SIGTERM", "SIGKILL"]);
  });

  it("drops the error the CLI sends while it is being stopped", async () => {
    const { controller, events, finished, t } = await running({ stdout: lines("synthetic-auth-401.jsonl") });
    controller.abort();
    await finished;
    expect(t.spawner.signals.length).toBeGreaterThan(0);
    expect(events.map((event) => event.type)).not.toContain("error");
    expect(events.at(-1)).toEqual({ type: "done", reason: "cancelled" });
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
  const MODELS_ISOLATED = "openai/gpt-5.5\nopenai/gpt-5.4\nopencode/big-pickle\n";
  const detect = async (scripts: ChildScript[], options: Partial<OpencodeRunnerOptions> = {}) => {
    const t = await setup(options);
    for (const script of scripts) t.spawner.enqueue(script);
    return { t, status: await t.runner.detect() };
  };
  const version = { stdout: ["1.19.0\n"], exit: ok };

  it("reports the version, requires a model and lists the models the isolated agent can use, sorted", async () => {
    const { t, status } = await detect([version, { stdout: [MODELS_ISOLATED], exit: ok }]);
    expect(status).toEqual({ provider: "opencode", installed: true, version: "1.19.0", requiresModel: true, models: ["openai/gpt-5.4", "openai/gpt-5.5", "opencode/big-pickle"] });
    expect(t.spawner.calls[0]).toMatchObject({ file: BINARY, args: ["--version"] });
    expect(OPENCODE_TESTED_VERSION).toBe("1.19.0");
  });

  it("never runs with the project as its working directory: a private temporary folder is the cwd and the empty config home", async () => {
    const { t } = await detect([version, { stdout: [MODELS_ISOLATED], exit: ok }]);
    expect(t.spawner.calls).toHaveLength(2);
    const [probe, listing] = t.spawner.calls;
    expect(listing!.args).toEqual(["--pure", "models"]);
    for (const call of [probe!, listing!]) {
      expect(call.cwd).not.toBe(ROOT);
      expect(call.cwd.startsWith(ROOT)).toBe(false);
      expect(call.cwd).toMatch(/^\/tmp\/caztor-opencode-/);
      expect(call.env["XDG_CONFIG_HOME"]).toBe(call.cwd);
    }
    expect(listing!.env["OPENCODE_CONFIG"]).toBeUndefined();
  });

  it("makes the temporary folder private, removes it afterwards, and uses a new one for the next check", async () => {
    const { t } = await detect([version, { stdout: [MODELS_ISOLATED], exit: ok }]);
    const folder = t.spawner.calls[0]!.cwd;
    expect(t.spawner.calls[1]!.cwd).toBe(folder);
    await expect(t.fs.stat(folder)).rejects.toMatchObject({ code: "ENOENT" });
    t.clock.advance(30_000);
    t.spawner.enqueue(version);
    t.spawner.enqueue({ stdout: [MODELS_ISOLATED], exit: ok });
    await t.runner.detect();
    expect(t.spawner.calls[2]!.cwd).not.toBe(folder);
  });

  it("removes the temporary folder when the CLI cannot be started", async () => {
    const { t } = await detect([{ spawnError: "EACCES" }]);
    await expect(t.fs.stat(t.spawner.calls[0]!.cwd)).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("does not look at the user's own opencode setup: one listing, and no note about hidden providers", async () => {
    const { t, status } = await detect([version, { stdout: [MODELS_ISOLATED], exit: ok }]);
    expect(t.spawner.calls.map((call) => call.args)).toEqual([["--version"], ["--pure", "models"]]);
    expect(status).not.toHaveProperty("note");
  });

  it("falls back to a text box for the model when the list cannot be read", async () => {
    const failed = { stderr: ["boom\n"], exit: { code: 1, signal: null } };
    const { status } = await detect([version, failed]);
    expect(status).toMatchObject({ installed: true, version: "1.19.0", requiresModel: true });
    expect(status).not.toHaveProperty("models");
  });

  it("lists the models again only after half a minute, because a turn checks the CLI first and listing takes seconds", async () => {
    const t = await setup();
    t.spawner.enqueue(version);
    t.spawner.enqueue({ stdout: [MODELS_ISOLATED], exit: ok });
    const first = await t.runner.detect();
    t.spawner.enqueue(version);
    const second = await t.runner.detect();
    expect(t.spawner.calls.map((call) => call.args)).toEqual([["--version"], ["--pure", "models"], ["--version"]]);
    expect(second).toEqual(first);
    t.clock.advance(30_000);
    t.spawner.enqueue(version);
    t.spawner.enqueue({ stdout: ["openai/gpt-5.9\n"], exit: ok });
    expect(await t.runner.detect()).toMatchObject({ models: ["openai/gpt-5.9"] });
    expect(t.spawner.calls).toHaveLength(5);
  });

  it("gives the model listing 15 seconds, because it takes longer on a busy machine, and goes on without a list after that", async () => {
    const t = await setup();
    t.spawner.enqueue(version);
    t.spawner.enqueue({});
    const pending = t.runner.detect();
    await vi.waitFor(() => expect(t.spawner.calls).toHaveLength(2));
    t.clock.advance(5000);
    await new Promise<void>((resolve) => setImmediate(resolve));
    expect(t.spawner.signals).toEqual([]);
    t.clock.advance(10_000);
    const status = await pending;
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
    expect(status).toMatchObject({ installed: true, version: "1.19.0", requiresModel: true });
    expect(status).not.toHaveProperty("models");
  });

  it("ignores lines of the list that are not a model, such as log lines", async () => {
    const { status } = await detect([version, { stdout: ["INFO starting\nopenai/gpt-5.5\n\n  \nnot a model line\n"], exit: ok }]);
    expect(status).toMatchObject({ models: ["openai/gpt-5.5"] });
  });

  it("warns about a version older than the tested one, and not about a newer or equal one", async () => {
    const rest = [{ exit: ok }];
    const old = await detect([{ stdout: ["1.18.9\n"], exit: ok }, ...rest]);
    expect(old.status.versionWarning).toContain("1.19.0");
    const same = await detect([version, ...rest]);
    expect(same.status.versionWarning).toBeUndefined();
    const newer = await detect([{ stdout: ["2.0.1\n"], exit: ok }, ...rest]);
    expect(newer.status.versionWarning).toBeUndefined();
  });

  it("says it is not installed when no PATH folder holds an executable file of that name", async () => {
    const t = await setup({ env: { ...ENV, PATH: "/nowhere" } });
    expect(await t.runner.detect()).toEqual({ provider: "opencode", installed: false, unavailableReason: "opencode was not found on the PATH.", requiresModel: false });
    expect(t.spawner.calls).toEqual([]);
  });

  it("says why it cannot run: a failing exit, output it does not know, a start failure", async () => {
    const failing = await detect([{ stderr: ["segfault\n"], exit: { code: 139, signal: null } }]);
    expect(failing.status).toMatchObject({ installed: false, unavailableReason: expect.stringContaining("segfault") });
    const strange = await detect([{ stdout: ["hello\n"], exit: ok }]);
    expect(strange.status).toMatchObject({ installed: false, unavailableReason: expect.stringContaining("not recognised") });
    const missing = await detect([{ spawnError: "ENOENT" }]);
    expect(missing.status).toMatchObject({ installed: false, unavailableReason: expect.stringContaining("could not be started") });
  });

  it("gives up after 5 seconds on --version and stops the probe", async () => {
    const t = await setup();
    t.spawner.enqueue({});
    const pending = t.runner.detect();
    await vi.waitFor(() => expect(t.spawner.calls).toHaveLength(1));
    t.clock.advance(5000);
    expect(await pending).toMatchObject({ installed: false, unavailableReason: "opencode did not answer --version within 5 seconds." });
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
  });
});

describe("the project's own opencode configuration", () => {
  const MCP = '{"mcp":{"x":{"type":"local","command":["touch","/tmp/X"]}}}';

  it("refuses the turn before anything starts while a project config can run programs and nobody trusted it", async () => {
    const t = await setup({ projectConfigConfirmed: async () => false }, { [AGENT_FILE]: DENIES, [`${ROOT}/opencode.json`]: MCP });
    const events = await turn(EDIT)(t);
    expect(t.spawner.calls).toEqual([]);
    expect(events[0]).toMatchObject({ type: "error", code: "isolation_failed", message: expect.stringContaining("opencode.json") });
    expect(events[0]).toMatchObject({ message: expect.stringContaining("Trust this project's CLI configuration") });
    expect(types(events).at(-1)).toBe("done");
  });

  it("names a plugin folder too, and refuses when no confirmation function is wired", async () => {
    const t = await setup({}, { [AGENT_FILE]: DENIES, [`${ROOT}/.opencode/plugins/p.js`]: "export const P = async () => ({})" });
    const events = await turn(EDIT)(t);
    expect(t.spawner.calls).toEqual([]);
    expect(events[0]).toMatchObject({ code: "isolation_failed", message: expect.stringContaining(".opencode/plugins/") });
  });

  it("goes on once the user trusted exactly the files found, and asks about their fingerprint", async () => {
    const asked: string[] = [];
    const files = { [AGENT_FILE]: DENIES, [`${ROOT}/opencode.json`]: MCP };
    const t = await setup({ projectConfigConfirmed: async (fingerprint) => (asked.push(fingerprint), true) }, files);
    await turn(EDIT)(t);
    expect(t.spawner.calls).toHaveLength(1);
    expect(asked).toEqual([(await t.runner.projectConfig?.())?.fingerprint]);
  });

  it("does not ask when the project has no such configuration", async () => {
    const asked: string[] = [];
    const t = await setup({ projectConfigConfirmed: async (fingerprint) => (asked.push(fingerprint), false) });
    await turn(EDIT)(t);
    expect(t.spawner.calls).toHaveLength(1);
    expect(asked).toEqual([]);
  });
});

describe("the configuration folder inside the project", () => {
  const XDG = `${ROOT}/.caztor/opencode-xdg`;

  it("is created by Caztor, readable only by this user, before the CLI starts", async () => {
    const t = await setup();
    await turn(EDIT)(t);
    expect((await t.fs.stat(XDG)).isDirectory()).toBe(true);
    expect((await t.fs.stat(XDG)).mode & 0o777).toBe(0o700);
    expect(t.spawner.calls[0]!.env["XDG_CONFIG_HOME"]).toBe(XDG);
  });

  it("starts every turn empty: a configuration Caztor did not write there (a planted MCP server) is removed first", async () => {
    const t = await setup({}, { [AGENT_FILE]: DENIES, [`${XDG}/opencode/opencode.json`]: '{"mcp":{"x":{"type":"local","command":["sh"]}}}' });
    let seen: string[] | null = null;
    t.spawner.enqueue(EDIT);
    const spawn = t.spawner.spawn.bind(t.spawner);
    t.spawner.spawn = (spec) => {
      void t.fs.readdir(XDG).then((entries) => (seen = entries.map((entry) => entry.name)));
      return spawn(spec);
    };
    await collect(t.runner.runTurn(request(), new AbortController().signal));
    expect(seen).toEqual([]);
    await expect(t.fs.stat(`${XDG}/opencode/opencode.json`)).rejects.toMatchObject({ code: "ENOENT" });
    expect((await t.fs.stat(XDG)).mode & 0o777).toBe(0o700);
  });

  it("keeps what opencode writes there itself: a schema-only config, its .gitignore and its plugin package", async () => {
    const own = { [`${XDG}/opencode/opencode.jsonc`]: '{\n  "$schema": "https://opencode.ai/config.json"\n}', [`${XDG}/opencode/.gitignore`]: "node_modules\n", [`${XDG}/opencode/node_modules/@opencode-ai/plugin/index.js`]: "x" };
    const t = await setup({}, { [AGENT_FILE]: DENIES, ...own });
    await turn(EDIT)(t);
    for (const path of Object.keys(own)) expect((await t.fs.stat(path)).isFile()).toBe(true);
  });

  it("empties the folder when anything else is in it, such as a plugin folder", async () => {
    const t = await setup({}, { [AGENT_FILE]: DENIES, [`${XDG}/opencode/opencode.jsonc`]: '{"$schema":"x"}', [`${XDG}/opencode/plugins/evil.js`]: "run()" });
    await turn(EDIT)(t);
    await expect(t.fs.stat(`${XDG}/opencode/plugins/evil.js`)).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("tightens a folder that already exists with looser permissions", async () => {
    const t = await setup();
    await t.fs.mkdir(XDG, { recursive: true });
    await t.fs.chmod(XDG, 0o755);
    await turn(EDIT)(t);
    expect((await t.fs.stat(XDG)).mode & 0o777).toBe(0o700);
  });

  it.each([
    ["the folder itself", `${ROOT}/.caztor/opencode-xdg`],
    [".caztor", `${ROOT}/.caztor`],
  ])("refuses the turn when %s is a symbolic link", async (_name, link) => {
    const t = await setup({}, { [AGENT_FILE]: DENIES, "/elsewhere/keep": "x" });
    await t.fs.mkdir(link.slice(0, link.lastIndexOf("/")), { recursive: true });
    t.fs.symlink("/elsewhere", link);
    const events = await turn(EDIT)(t);
    expect(t.spawner.calls).toEqual([]);
    expect(events[0]).toMatchObject({ type: "error", code: "isolation_failed", message: expect.stringContaining("symbolic link") });
  });
});

describe("a stored key echoed by the CLI", () => {
  it("is masked in the tapped lines and in every event, also from the end of the error output", async () => {
    const KEY = "sk-echoed-openai-key-99";
    const tapped: string[] = [];
    const t = await setup({ credentials: fakeReader({ "opencode:openai": KEY }), tap: (line) => tapped.push(line) });
    t.spawner.enqueue({ stdout: [`{"type":"noise","note":"rejected ${KEY}"}\n`], stderr: [`Invalid API key ${KEY}\n`], exit: { code: 1, signal: null } });
    const events = await collect(t.runner.runTurn(request({ authMode: "api", model: MODEL }), new AbortController().signal));
    expect(tapped.join("\n")).toContain("[redacted]");
    expect(tapped.join("\n")).not.toContain(KEY);
    expect(JSON.stringify(events)).not.toContain(KEY);
    expect(events.at(-1)).toEqual({ type: "done", reason: "failed" });
  });
});

describe("isolation does not depend on the sign-in mode", () => {
  const OPENAI = "sk-openai-stored-0001";
  const MCP = '{"mcp":{"x":{"type":"local","command":["touch","/tmp/X"]}}}';

  it("passes the same command line in account and api mode", async () => {
    const account = await setup({ credentials: fakeReader({ "opencode:openai": OPENAI }) });
    await turn(EDIT, request({ authMode: "account" }))(account);
    const api = await setup({ credentials: fakeReader({ "opencode:openai": OPENAI }) });
    await turn(EDIT, request({ authMode: "api" }))(api);
    expect(api.spawner.calls[0]!.args).toEqual(account.spawner.calls[0]!.args);
    expect(api.spawner.calls[0]!.env["XDG_CONFIG_HOME"]).toBe(account.spawner.calls[0]!.env["XDG_CONFIG_HOME"]);
  });

  it("still asks for the project's configuration to be trusted in api mode, and reads no key before that is settled", async () => {
    const reader = fakeReader({ "opencode:openai": OPENAI });
    const t = await setup({ credentials: reader, projectConfigConfirmed: async () => false }, { [AGENT_FILE]: DENIES, [`${ROOT}/opencode.json`]: MCP });
    const events = await collect(t.runner.runTurn(request({ authMode: "api" }), new AbortController().signal));
    expect(t.spawner.calls).toEqual([]);
    expect(reader.reads).toEqual([]);
    expect(events[0]).toMatchObject({ type: "error", code: "isolation_failed", message: expect.stringContaining("opencode.json") });
  });

  it("still names the definition problem in api mode", async () => {
    const t = await setup({ credentials: fakeReader({ "opencode:openai": OPENAI }) }, { [AGENT_FILE]: "---\ndescription: x\npermission:\n  bash: allow\n---\n" });
    const events = await turn(EDIT, request({ authMode: "api" }))(t);
    expect(events.find((event) => event.type === "notice")).toMatchObject({ level: "warning", action: "replace_definition", message: expect.stringContaining("bash") });
  });
});

describe("a collaborator's turn", () => {
  it("builds the child's environment from the turn's environment", async () => {
    const t = await setup({ sandbox: fakeAgentSandbox().sandbox });
    const env = { PATH: "/usr/bin", HOME: "/cfg/u/home", XDG_DATA_HOME: "/cfg/u/home/.local/share", XDG_STATE_HOME: "/cfg/u/home/.local/state", XDG_CACHE_HOME: "/cfg/u/home/.cache" };
    await turn(EDIT, request({ env, sandbox: { home: env.HOME } }))(t);
    const child = t.spawner.calls[0]!.env;
    expect(child).toMatchObject(env);
    expect(child["XDG_CONFIG_HOME"]).toBe(`${ROOT}/.caztor/opencode-xdg`);
    expect(Object.values(child)).not.toContain(ENV.HOME);
  });
});

describeSandboxedTurns({
  setup: async (options) => setup(options),
  request,
  script: EDIT,
  binary: BINARY,
});
