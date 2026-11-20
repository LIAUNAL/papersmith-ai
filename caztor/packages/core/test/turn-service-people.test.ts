import { describe, expect, it, vi } from "vitest";
import {
  createTurnService,
  isSafeUserId,
  personalStateView,
  type CredentialError,
  type CredentialStatus,
  type PersonalPorts,
  type ProviderId,
  type Result,
  type TurnEvent,
  type TurnUser,
} from "../src/index.ts";
import { aborted, fakeProvisioner, fakeRunner, fakeSnapshots, fakeUserWrites, memoryHistory, memoryState, type CallLog } from "./support/turn-fakes.ts";

const HOST: TurnUser = { id: "host", name: "Host", role: "host" };
const ALICE: TurnUser = { id: "alice-1", name: "Alice", role: "collaborator" };
const BOB: TurnUser = { id: "bob-2", name: "Bob", role: "collaborator" };

/** A key store over fake slots that also hands out the key, as the runners' reader does. */
function keys(set: Record<string, string>) {
  return {
    async status(slot: string): Promise<Result<CredentialStatus, CredentialError>> {
      return { ok: true, value: { slot, set: set[slot] !== undefined } };
    },
    async read(slot: string): Promise<Result<string | null, CredentialError>> {
      return { ok: true, value: set[slot] ?? null };
    },
    list: async (): Promise<Result<CredentialStatus[], CredentialError>> => ({ ok: true, value: [] }),
    set: async (slot: string): Promise<Result<CredentialStatus, CredentialError>> => ({ ok: true, value: { slot, set: true } }),
    clear: async (slot: string): Promise<Result<CredentialStatus, CredentialError>> => ({ ok: true, value: { slot, set: false } }),
  };
}

function setup() {
  const log: CallLog = [];
  const runner = fakeRunner(log, "claude");
  const state = memoryState();
  const snapshots = fakeSnapshots(log);
  const hostHistory = memoryHistory();
  const histories = new Map<string, ReturnType<typeof memoryHistory>>();
  const stores = new Map<string, ReturnType<typeof keys>>([[ALICE.id, keys({ claude: "sk-alice-key-0001" })], [BOB.id, keys({})]]);
  const envs = new Map<string, Record<string, string>>();
  let ids = 0;
  const people = (user: TurnUser): PersonalPorts => {
    if (!histories.has(user.id)) histories.set(user.id, memoryHistory());
    return {
      state: personalStateView(state, user.id),
      history: histories.get(user.id)!,
      credentials: stores.get(user.id)!,
      runEnv: async (provider: ProviderId) => ({ ok: true, value: { HOME: `/config/caztor/users/${user.id}/home`, PROVIDER: provider } }),
    };
  };
  const service = createTurnService({
    runners: { claude: runner },
    provisioner: fakeProvisioner(log),
    snapshots,
    state,
    userWrites: fakeUserWrites(log),
    rescan: async () => {},
    history: hostHistory,
    credentials: keys({ claude: "sk-host-key-00001" }),
    people,
    newId: () => `t${(ids += 1)}`,
  });
  async function turn(user: TurnUser, prompt = "Fix the typo"): Promise<{ turnId: string; events: TurnEvent[] }> {
    const started = await service.start({ provider: "claude", prompt, user });
    if (!started.ok) throw new Error(`refused: ${started.error.code}`);
    const seen: TurnEvent[] = [];
    await new Promise<void>((resolve) => void service.subscribe(started.value.turnId, { onEvent: (event) => seen.push(event), onEnd: resolve }));
    return { turnId: started.value.turnId, events: seen };
  }
  return { service, runner, state, snapshots, hostHistory, histories, envs, turn };
}

describe("a user id that builds a path", () => {
  it("is a plain segment of letters, digits, dashes and underscores, and never the host's", () => {
    expect(isSafeUserId("0b5f2c1e-8a7d-4c1b-9f00-123456789abc")).toBe(true);
    for (const hostile of ["", "..", ".", "a/b", "a\\b", "host", "x".repeat(65), "a b", "-x", "a\u0000b", 7, null]) {
      expect(isSafeUserId(hostile)).toBe(false);
    }
  });

  it("is refused by the personal state view", () => {
    expect(() => personalStateView(memoryState(), "../escape")).toThrow(/user id/i);
  });
});

describe("the personal state view", () => {
  it("keeps the host's fields where they are and writes nothing new for the host", async () => {
    const state = memoryState();
    const host = personalStateView(state, "host");
    await host.update({ models: { claude: "claude-opus" }, selectedProvider: "claude" });
    expect(state.current.models).toEqual({ claude: "claude-opus" });
    expect(state.current.selectedProvider).toBe("claude");
    expect("users" in state.current).toBe(false);
  });

  it("keeps a collaborator's choices under their id and shares the project settings", async () => {
    const state = memoryState({ models: { claude: "host-model" }, autoCompile: false });
    const alice = personalStateView(state, ALICE.id);
    await alice.update({ models: { claude: "alice-model" }, authModes: { claude: "api" }, selectedProvider: "claude", autoCompile: true });

    expect(state.current.models).toEqual({ claude: "host-model" });
    expect(state.current.authModes).toEqual({});
    expect(state.current.selectedProvider).toBeNull();
    expect(state.current.autoCompile).toBe(true);
    expect(state.current.users).toEqual({ [ALICE.id]: { models: { claude: "alice-model" }, authModes: { claude: "api" }, selectedProvider: "claude", sessions: {} } });
    expect(await alice.load()).toMatchObject({ models: { claude: "alice-model" }, authModes: { claude: "api" }, selectedProvider: "claude", autoCompile: true });
    expect(await personalStateView(state, BOB.id).load()).toMatchObject({ models: {}, authModes: {}, selectedProvider: null, sessions: {}, autoCompile: true });
  });
});

describe("turns per person", () => {
  it("keeps each person's history, session, model and auth mode apart", async () => {
    const t = setup();
    await personalStateView(t.state, ALICE.id).update({ models: { claude: "alice-model" }, authModes: { claude: "api" } });
    await t.state.update({ models: { claude: "host-model" } });
    t.runner.script = async function* ({ req }) {
      yield { type: "session", sessionId: `session-of-${req.model}` };
      yield { type: "done", reason: "completed" };
    };

    await t.turn(HOST, "host prompt");
    await t.turn(ALICE, "alice prompt");
    await t.turn(BOB, "bob prompt");

    expect(t.hostHistory.records.map((record) => record.prompt)).toEqual(["host prompt"]);
    expect(t.histories.get(ALICE.id)!.records.map((record) => record.prompt)).toEqual(["alice prompt"]);
    expect(t.histories.get(BOB.id)!.records.map((record) => record.prompt)).toEqual(["bob prompt"]);
    expect(t.state.current.sessions.claude?.sessionId).toBe("session-of-host-model");
    expect(t.state.current.users?.[ALICE.id]?.sessions.claude).toMatchObject({ sessionId: "session-of-alice-model", authMode: "api" });
    expect(t.state.current.users?.[BOB.id]?.sessions.claude).toMatchObject({ sessionId: "session-of-null", authMode: "account" });
    expect(t.runner.requests.map((req) => [req.model, req.authMode])).toEqual([["host-model", "account"], ["alice-model", "api"], [null, "account"]]);
  });

  it("resumes each person's own session", async () => {
    const t = setup();
    t.runner.script = async function* ({ req }) {
      yield { type: "session", sessionId: `s-${t.runner.requests.length}` };
      yield { type: "done", reason: "completed" };
      void req;
    };
    await t.turn(ALICE);
    await t.turn(HOST);
    await t.turn(ALICE);
    await t.turn(HOST);
    expect(t.runner.requests.map((req) => req.sessionId)).toEqual([null, null, "s-1", "s-2"]);
  });

  it("gives a collaborator's turn their environment and key reader, and the host's turn neither", async () => {
    const t = setup();
    await t.turn(HOST);
    await t.turn(ALICE);
    const [host, alice] = t.runner.requests;
    expect(host).not.toHaveProperty("env");
    expect(host).not.toHaveProperty("credentials");
    expect(alice?.env).toEqual({ HOME: `/config/caztor/users/${ALICE.id}/home`, PROVIDER: "claude" });
    expect(await alice?.credentials?.read("claude")).toEqual({ ok: true, value: "sk-alice-key-0001" });
  });

  it("marks only a collaborator's turn to run sandboxed, with their private folder as its home", async () => {
    const t = setup();
    await t.turn(HOST);
    await t.turn(ALICE);
    const [host, alice] = t.runner.requests;
    expect(host).not.toHaveProperty("sandbox");
    expect(alice?.sandbox).toEqual({ home: `/config/caztor/users/${ALICE.id}/home` });
  });

  it("refuses a collaborator's turn whose environment names no private home, before anything runs", async () => {
    const t = setup();
    const service = createTurnService({
      runners: { claude: t.runner },
      provisioner: fakeProvisioner([]),
      snapshots: fakeSnapshots([]),
      state: t.state,
      userWrites: fakeUserWrites([]),
      rescan: async () => {},
      people: (user) => ({ state: personalStateView(t.state, user.id), runEnv: async () => ({ ok: true, value: { PATH: "/usr/bin" } }) }),
    });
    expect(await service.start({ provider: "claude", prompt: "go", user: ALICE })).toMatchObject({ ok: false, error: { code: "person_unavailable" } });
    expect(t.runner.requests).toEqual([]);
  });

  it("checks the collaborator's own key for api mode", async () => {
    const t = setup();
    await personalStateView(t.state, BOB.id).update({ authModes: { claude: "api" } });
    const refused = await t.service.start({ provider: "claude", prompt: "go", user: BOB });
    expect(refused).toMatchObject({ ok: false, error: { code: "api_key_missing" } });
  });

  it("refuses a collaborator's turn whose private folder cannot be prepared, before anything runs", async () => {
    const t = setup();
    const service = createTurnService({
      runners: { claude: t.runner },
      provisioner: fakeProvisioner([]),
      snapshots: fakeSnapshots([]),
      state: t.state,
      userWrites: fakeUserWrites([]),
      rescan: async () => {},
      people: (user) => ({ state: personalStateView(t.state, user.id), runEnv: async () => ({ ok: false, error: { message: "The private folder is a link." } }) }),
    });
    expect(await service.start({ provider: "claude", prompt: "go", user: ALICE })).toEqual({ ok: false, error: { code: "person_unavailable", message: "The private folder is a link." } });
    expect(t.runner.requests).toEqual([]);
  });

  it("refuses a collaborator where per-person state is not set up", async () => {
    const log: CallLog = [];
    const service = createTurnService({
      runners: { claude: fakeRunner(log) },
      provisioner: fakeProvisioner(log),
      snapshots: fakeSnapshots(log),
      state: memoryState(),
      userWrites: fakeUserWrites(log),
      rescan: async () => {},
    });
    expect(await service.start({ provider: "claude", prompt: "go", user: ALICE })).toMatchObject({ ok: false, error: { code: "person_unavailable" } });
    expect(log).toEqual([]);
  });

  it("tracks the CLI login per person", async () => {
    const t = setup();
    t.runner.script = async function* () {
      yield { type: "error", code: "auth", message: "Sign in" };
      yield { type: "done", reason: "failed" };
    };
    await t.turn(BOB);
    t.runner.script = async function* () {
      yield { type: "done", reason: "completed" };
    };
    await t.turn(HOST);
    expect(t.service.loginOf("claude", BOB)).toBe("signed_out");
    expect(t.service.loginOf("claude")).toBe("signed_in");
    expect(t.service.loginOf("claude", HOST)).toBe("signed_in");
    expect(t.service.loginOf("claude", ALICE)).toBe("unknown");
  });

  it("takes a login the person finished outside a turn, for that person only", () => {
    const t = setup();
    t.service.noteLogin("codex", "signed_in", ALICE);
    expect(t.service.loginOf("codex", ALICE)).toBe("signed_in");
    expect(t.service.loginOf("codex", BOB)).toBe("unknown");
    expect(t.service.loginOf("codex")).toBe("unknown");
    t.service.noteLogin("codex", "signed_in");
    expect(t.service.loginOf("codex", HOST)).toBe("signed_in");
  });

  it("starts a new chat for one person only", async () => {
    const t = setup();
    t.runner.script = async function* () {
      yield { type: "session", sessionId: "s" };
      yield { type: "done", reason: "completed" };
    };
    await t.turn(HOST);
    await t.turn(ALICE);
    expect(await t.service.resetSession("claude", ALICE)).toBe(true);
    expect(t.state.current.users?.[ALICE.id]?.sessions).toEqual({});
    expect(t.histories.get(ALICE.id)!.records).toEqual([]);
    expect(t.state.current.sessions.claude?.sessionId).toBe("s");
    expect(t.hostHistory.records).toHaveLength(1);
  });
});

describe("one turn at a time per project", () => {
  function blocking(t: ReturnType<typeof setup>) {
    t.runner.script = async function* ({ signal }) {
      await aborted(signal);
    };
  }

  it("refuses another person's start with a readable message that names who runs", async () => {
    const t = setup();
    blocking(t);
    const started = await t.service.start({ provider: "claude", prompt: "go", user: ALICE });
    expect(started.ok).toBe(true);
    await vi.waitFor(() => expect(t.runner.requests).toHaveLength(1));

    expect(await t.service.start({ provider: "claude", prompt: "me too", user: BOB })).toEqual({ ok: false, error: { code: "busy", message: "Alice has a turn running. Wait for it to finish." } });
    expect(await t.service.start({ provider: "claude", prompt: "me too", user: HOST })).toEqual({ ok: false, error: { code: "busy", message: "Alice has a turn running. Wait for it to finish." } });
    expect(await t.service.start({ provider: "claude", prompt: "again", user: ALICE })).toEqual({ ok: false, error: { code: "busy", message: "A turn is already running. Wait for it to finish or stop it." } });
    expect(t.service.current()).toMatchObject({ running: true, owner: { id: ALICE.id, name: "Alice" } });
    await t.service.shutdown();
  });

  it("lets only the owner stop the turn", async () => {
    const t = setup();
    blocking(t);
    const started = await t.service.start({ provider: "claude", prompt: "go", user: ALICE });
    if (!started.ok) throw new Error("refused");
    await vi.waitFor(() => expect(t.runner.requests).toHaveLength(1));

    expect(t.service.stop(started.value.turnId, BOB)).toBe(false);
    expect(t.service.stop(started.value.turnId, HOST)).toBe(false);
    expect(t.service.stop(started.value.turnId)).toBe(false);
    expect(t.service.current()?.running).toBe(true);
    expect(t.service.stop(started.value.turnId, ALICE)).toBe(true);
    await t.service.idle();
  });

  it("lets only the owner undo a turn, and keeps undo shared on the same snapshots", async () => {
    const t = setup();
    const { turnId } = await t.turn(ALICE);

    expect(await t.service.undo(turnId, "strict", BOB)).toEqual({ status: "not_yours", message: "Alice ran this turn, so only Alice can undo it." });
    expect(await t.service.undo(turnId, "strict", HOST)).toMatchObject({ status: "not_yours" });
    expect(t.snapshots.restores).toEqual([]);
    expect(await t.service.undo(turnId, "strict", ALICE)).toMatchObject({ status: "restored" });
    expect(t.snapshots.restores).toEqual([{ turnId, mode: "strict" }]);
  });

  it("finds the owner of a turn from before a restart in their history", async () => {
    const t = setup();
    const history = memoryHistory();
    await history.append({ turnId: "old-1", provider: "claude", prompt: "p", startedAt: 1, events: [] });
    const fresh = createTurnService({
      runners: { claude: t.runner },
      provisioner: fakeProvisioner([]),
      snapshots: t.snapshots,
      state: t.state,
      userWrites: fakeUserWrites([]),
      rescan: async () => {},
      history: memoryHistory(),
      people: (user) => ({ state: personalStateView(t.state, user.id), history: user.id === ALICE.id ? history : memoryHistory() }),
    });
    expect(await fresh.undo("old-1", "strict", BOB)).toMatchObject({ status: "not_yours" });
    expect(await fresh.undo("old-1", "strict", ALICE)).toMatchObject({ status: "restored" });
    expect(t.snapshots.restores).toEqual([{ turnId: "old-1", mode: "strict" }]);
  });

  it("keeps a collaborator's turn theirs after a restart: the host cannot undo it, nor is offered to (B5)", async () => {
    const t = setup();
    const fresh = createTurnService({
      runners: { claude: t.runner },
      provisioner: fakeProvisioner([]),
      snapshots: t.snapshots,
      state: t.state,
      userWrites: fakeUserWrites([]),
      rescan: async () => {},
      history: memoryHistory(),
      people: (user) => ({ state: personalStateView(t.state, user.id), history: memoryHistory() }),
      turnOwner: async (turnId) => (turnId === "old-1" ? { id: ALICE.id, name: "Alice" } : null),
    });
    expect(await fresh.mayUndo("old-1", HOST)).toBe(false);
    expect(await fresh.undo("old-1", "strict", HOST)).toEqual({ status: "not_yours", message: "Alice ran this turn, so only Alice can undo it." });
    expect(await fresh.mayUndo("old-1", ALICE)).toBe(true);
    // A turn no collaborator ran stays the host's, as before people existed.
    expect(await fresh.mayUndo("host-1", HOST)).toBe(true);
    expect(await fresh.mayUndo("host-1", BOB)).toBe(false);
    expect(t.snapshots.restores).toEqual([]);
  });

  it("keeps the host's undo of an older turn as before", async () => {
    const t = setup();
    expect(await t.service.undo("before-any-collaborator", "force")).toMatchObject({ status: "restored" });
    expect(t.snapshots.restores).toEqual([{ turnId: "before-any-collaborator", mode: "force" }]);
  });
});

