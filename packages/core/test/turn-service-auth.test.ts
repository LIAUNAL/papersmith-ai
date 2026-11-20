import { describe, expect, it } from "vitest";
import { createTurnService, type CredentialError, type CredentialStatus, type ProviderId, type Result, type TurnEvent } from "../src/index.ts";
import { fakeProvisioner, fakeRunner, fakeSnapshots, fakeUserWrites, hashOf, memoryHistory, memoryState, type CallLog, type FakeRunner } from "./support/turn-fakes.ts";

/** A status port over fake slots; `error` makes every lookup fail as a refusing store does. */
function credentials(set: string[], error?: CredentialError) {
  const asked: string[] = [];
  return {
    asked,
    async status(slot: string): Promise<Result<CredentialStatus, CredentialError>> {
      asked.push(slot);
      return error === undefined ? { ok: true, value: { slot, set: set.includes(slot) } } : { ok: false, error };
    },
  };
}

function setup(options: { state?: Parameters<typeof memoryState>[0]; stored?: string[]; error?: CredentialError; withStore?: boolean; providers?: ProviderId[] } = {}) {
  const log: CallLog = [];
  const runners = Object.fromEntries((options.providers ?? ["claude"]).map((id) => [id, fakeRunner(log, id)])) as Record<ProviderId, FakeRunner>;
  runners.opencode && (runners.opencode.status = { provider: "opencode", installed: true, requiresModel: true });
  const provisioner = fakeProvisioner(log);
  const state = memoryState(options.state);
  const store = credentials(options.stored ?? [], options.error);
  let ids = 0;
  const service = createTurnService({
    runners,
    provisioner,
    snapshots: fakeSnapshots(log),
    state,
    userWrites: fakeUserWrites(log),
    rescan: async () => {},
    history: memoryHistory(),
    newId: () => `t${(ids += 1)}`,
    ...(options.withStore === false ? {} : { credentials: store }),
  });
  async function turn(provider: ProviderId = "claude"): Promise<{ events: TurnEvent[] }> {
    const started = await service.start({ provider, prompt: "Fix the typo" });
    if (!started.ok) throw new Error(`refused: ${started.error.code}`);
    const seen: TurnEvent[] = [];
    await new Promise<void>((resolve) => void service.subscribe(started.value.turnId, { onEvent: (event) => seen.push(event), onEnd: resolve }));
    return { events: seen };
  }
  return { service, runners, runner: runners.claude, provisioner, state, store, log, turn };
}

const sessionTurn = (id: string) =>
  async function* (): AsyncGenerator<never | { type: "session"; sessionId: string } | { type: "done"; reason: "completed" }> {
    yield { type: "session", sessionId: id };
    yield { type: "done", reason: "completed" };
  };

describe("what the turns show about the CLI login", () => {
  const ending = (...events: unknown[]) =>
    async function* () {
      yield* events as never[];
    };
  const failedAuth = ending({ type: "error", code: "auth", message: "Sign in" }, { type: "done", reason: "failed" });
  const completed = ending({ type: "done", reason: "completed" });

  it("knows nothing before a turn", () => {
    expect(setup().service.loginOf("claude")).toBe("unknown");
  });

  it("is signed in after a completed account turn, and signed out after an auth error", async () => {
    const t = setup();
    t.runner.script = completed;
    await t.turn();
    expect(t.service.loginOf("claude")).toBe("signed_in");
    t.runner.script = failedAuth;
    await t.turn();
    expect(t.service.loginOf("claude")).toBe("signed_out");
  });

  it("learns nothing from a cancelled turn, another failure or a turn in api mode", async () => {
    const t = setup();
    t.runner.script = ending({ type: "done", reason: "cancelled" });
    await t.turn();
    t.runner.script = ending({ type: "error", code: "provider_error", message: "x" }, { type: "done", reason: "failed" });
    await t.turn();
    expect(t.service.loginOf("claude")).toBe("unknown");

    const api = setup({ state: { authModes: { claude: "api" } }, stored: ["claude"] });
    api.runner.script = completed;
    await api.turn();
    expect(api.service.loginOf("claude")).toBe("unknown");
  });

  it("keeps each provider apart", async () => {
    const t = setup({ providers: ["claude", "codex"] });
    t.runner.script = completed;
    await t.turn();
    expect(t.service.loginOf("codex")).toBe("unknown");
  });
});

describe("a turn in api mode needs a stored key", () => {
  it("refuses with api_key_missing, a readable message and nothing provisioned, captured or spawned", async () => {
    const t = setup({ state: { authModes: { claude: "api" } }, stored: [] });
    const started = await t.service.start({ provider: "claude", prompt: "Fix" });
    expect(started).toEqual({ ok: false, error: { code: "api_key_missing", message: expect.stringContaining("API key") } });
    expect(t.log).toEqual([]);
    expect(t.runner.requests).toEqual([]);
    expect(t.service.current()).toBeNull();
    expect(t.store.asked).toEqual(["claude"]);
  });

  it("starts the turn when the key is stored, and hands the runner the mode", async () => {
    const t = setup({ state: { authModes: { claude: "api" } }, stored: ["claude"] });
    const { events } = await t.turn();
    expect(events.at(-2)?.type).toBe("done");
    expect(t.runner.requests.map((request) => request.authMode)).toEqual(["api"]);
  });

  it("hands the runner account mode when the project chose none, without asking the store", async () => {
    const t = setup({ stored: ["claude"] });
    await t.turn();
    expect(t.runner.requests.map((request) => request.authMode)).toEqual(["account"]);
    expect(t.store.asked).toEqual([]);
  });

  it("ignores a stored key in account mode", async () => {
    const t = setup({ state: { authModes: { claude: "account" } }, stored: [] });
    const started = await t.service.start({ provider: "claude", prompt: "Fix" });
    expect(started.ok).toBe(true);
    await t.service.idle();
  });

  it("refuses with the store's own message when the store cannot be used", async () => {
    const t = setup({ state: { authModes: { claude: "api" } }, error: { code: "corrupt", message: "The Caztor key file cannot be read." } });
    const started = await t.service.start({ provider: "claude", prompt: "Fix" });
    expect(started).toEqual({ ok: false, error: { code: "api_key_missing", message: "The Caztor key file cannot be read." } });
    expect(t.runner.requests).toEqual([]);
  });

  it("refuses when this server has no credential store at all", async () => {
    const t = setup({ state: { authModes: { claude: "api" } }, withStore: false });
    const started = await t.service.start({ provider: "claude", prompt: "Fix" });
    expect(started).toMatchObject({ ok: false, error: { code: "api_key_missing" } });
  });

  it("looks for the opencode key of the model's vendor only", async () => {
    const t = setup({ providers: ["opencode"], state: { authModes: { opencode: "api" }, models: { opencode: "openai/gpt-5.5" } }, stored: ["opencode:anthropic", "claude"] });
    const started = await t.service.start({ provider: "opencode", prompt: "Fix" });
    expect(started).toEqual({ ok: false, error: { code: "api_key_missing", message: expect.stringContaining("openai") } });
    expect(t.store.asked).toEqual(["opencode:openai"]);
  });

  it("starts an opencode turn when the vendor's key is stored", async () => {
    const t = setup({ providers: ["opencode"], state: { authModes: { opencode: "api" }, models: { opencode: "openai/gpt-5.5" } }, stored: ["opencode:openai"] });
    await t.turn("opencode");
    expect(t.runners.opencode.requests.map((request) => request.authMode)).toEqual(["api"]);
  });

  it("asks for a provider/model name when opencode is in api mode without one, and refuses a vendor with no key route", async () => {
    const none = setup({ providers: ["opencode"], state: { authModes: { opencode: "api" }, models: { opencode: "plain-model" } }, stored: [] });
    expect(await none.service.start({ provider: "opencode", prompt: "Fix" })).toEqual({ ok: false, error: { code: "model_required", message: expect.stringContaining("provider/model") } });
    const unsupported = setup({ providers: ["opencode"], state: { authModes: { opencode: "api" }, models: { opencode: "nowhere/m" } }, stored: [] });
    expect(await unsupported.service.start({ provider: "opencode", prompt: "Fix" })).toEqual({ ok: false, error: { code: "mode_unsupported", message: expect.stringContaining("nowhere") } });
    expect(none.store.asked).toEqual([]);
  });
});

describe("a conversation follows the sign-in method", () => {
  it("records the mode a conversation started under", async () => {
    const t = setup({ state: { authModes: { claude: "api" } }, stored: ["claude"] });
    t.runner.script = sessionTurn("s1");
    await t.turn();
    expect(t.state.current.sessions.claude).toEqual({ sessionId: "s1", agentHash: hashOf("agent1"), isolation: "tier-1", authMode: "api" });
  });

  it("starts a new conversation with a notice when the mode changed", async () => {
    const t = setup({ stored: ["claude"] });
    t.runner.script = sessionTurn("s1");
    await t.turn();
    await t.state.update({ authModes: { claude: "api" } });
    const { events } = await t.turn();
    expect(t.runner.requests.map((request) => request.sessionId)).toEqual([null, null]);
    expect(events[0]).toEqual({ type: "notice", level: "info", message: "New conversation started because the sign-in method changed." });
  });

  it("keeps resuming while the mode is the same, with no notice", async () => {
    const t = setup({ state: { authModes: { claude: "api" } }, stored: ["claude"] });
    t.runner.script = sessionTurn("s1");
    await t.turn();
    const { events } = await t.turn();
    expect(t.runner.requests.map((request) => request.sessionId)).toEqual([null, "s1"]);
    expect(events.some((event) => event.type === "notice")).toBe(false);
  });

  it("resumes a conversation saved before modes existed as an account conversation", async () => {
    const t = setup({ state: { sessions: { claude: { sessionId: "old", agentHash: hashOf("agent1"), isolation: "tier-1" } } } });
    const { events } = await t.turn();
    expect(t.runner.requests[0]!.sessionId).toBe("old");
    expect(events.some((event) => event.type === "notice")).toBe(false);
  });

  it("starts over when an old conversation meets api mode", async () => {
    const t = setup({ state: { authModes: { claude: "api" }, sessions: { claude: { sessionId: "old", agentHash: hashOf("agent1"), isolation: "tier-1" } } }, stored: ["claude"] });
    const { events } = await t.turn();
    expect(t.runner.requests[0]!.sessionId).toBeNull();
    expect(events[0]).toMatchObject({ type: "notice", message: "New conversation started because the sign-in method changed." });
  });
});
