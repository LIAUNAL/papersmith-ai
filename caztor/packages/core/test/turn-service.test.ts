import { describe, expect, it, vi } from "vitest";
import { createTurnService, REVERT_NOTE_HEADER, type ProviderId, type RestoreResult, type TurnEvent, type TurnService } from "../src/index.ts";
import {
  aborted,
  agentDefinition,
  changed,
  events,
  fakeProvisioner,
  fakeRunner,
  fakeSnapshots,
  fakeUserWrites,
  hashOf,
  memoryHistory,
  memoryState,
  rel,
  type CallLog,
  type FakeRunner,
} from "./support/turn-fakes.ts";

function setup(options: { providers?: ProviderId[]; state?: Parameters<typeof memoryState>[0]; now?: () => number } = {}) {
  const log: CallLog = [];
  const runners = Object.fromEntries((options.providers ?? ["claude"]).map((id) => [id, fakeRunner(log, id)])) as Record<ProviderId, FakeRunner>;
  const provisioner = fakeProvisioner(log);
  const snapshots = fakeSnapshots(log);
  const state = memoryState(options.state);
  const userWrites = fakeUserWrites(log);
  const history = memoryHistory();
  let ids = 0;
  const timers: Array<{ fn: () => void; ms: number; live: boolean }> = [];
  const t: { onRescan: (() => void) | null } = { onRescan: null };
  const service = createTurnService({
    runners,
    provisioner,
    snapshots,
    state,
    userWrites,
    rescan: async () => {
      log.push("rescan");
      t.onRescan?.();
    },
    history,
    newId: () => `t${(ids += 1)}`,
    ...(options.now === undefined ? {} : { now: options.now }),
    setTimeout: (fn, ms) => {
      const timer = { fn, ms, live: true };
      timers.push(timer);
      return () => void (timer.live = false);
    },
  });
  /** Starts a turn and collects its events until it ends. */
  async function turn(prompt = "Fix the typo", provider: ProviderId = "claude"): Promise<{ turnId: string; events: TurnEvent[] }> {
    const started = await service.start({ provider, prompt });
    if (!started.ok) throw new Error(`refused: ${started.error.code}`);
    const seen: TurnEvent[] = [];
    await new Promise<void>((resolve) => {
      service.subscribe(started.value.turnId, { onEvent: (event) => seen.push(event), onEnd: resolve });
    });
    return { turnId: started.value.turnId, events: seen };
  }
  return { service, runners, runner: runners.claude, provisioner, snapshots, state, userWrites, history, log, turn, hooks: t, timers };
}

const types = (list: TurnEvent[]) => list.map((event) => event.type);

describe("a conversation that cannot be saved", () => {
  it("still finishes the turn and tells the user that the conversation will not be restored", async () => {
    const t = setup();
    t.history.failure = ".caztor/chat is a link, not a plain folder";

    const { events: seen } = await t.turn();

    expect(types(seen).slice(-2)).toEqual(["files_changed", "notice"]);
    expect(seen.at(-1)).toEqual({
      type: "notice",
      level: "warning",
      message: "This conversation could not be saved, so it will not be restored after a reload: .caztor/chat is a link, not a plain folder",
    });
    expect(t.history.records).toEqual([]);
  });
});

describe("events from a runner", () => {
  it("passes on the valid ones, drops the rest and says so once", async () => {
    const t = setup();
    t.runner.script = async function* () {
      yield { type: "session", sessionId: "s1" };
      yield null as never;
      yield "text_delta" as never;
      yield { type: "rm_rf" } as never;
      yield { type: "text_delta", messageId: 7, text: "x" } as never;
      yield { type: "text", messageId: "m", text: "Hello" };
      yield { type: "done", reason: "completed" };
    };

    const { events: seen } = await t.turn();

    expect(types(seen)).toEqual(["turn_started", "session", "notice", "text", "done", "files_changed"]);
    expect(seen[2]).toEqual({ type: "notice", level: "warning", message: "The agent sent data Caztor does not understand. It was ignored." });
    expect(t.history.records[0]!.events.some((event) => (event as { type: string }).type === "rm_rf")).toBe(false);
  });

  it("cuts a huge text before it reaches the clients or the history", async () => {
    const t = setup();
    t.runner.script = async function* () {
      yield { type: "text", messageId: "m", text: "z".repeat(50_000_000) };
      yield { type: "done", reason: "completed" };
    };

    const { events: seen } = await t.turn();

    const text = seen.find((event) => event.type === "text");
    expect(text?.type === "text" && text.text.length).toBeLessThan(250_000);
    expect(JSON.stringify(t.history.records[0]).length).toBeLessThan(260_000);
  });

  it("keeps the memory of a turn with a million deltas small and still ends it", async () => {
    const t = setup();
    t.runner.script = async function* () {
      for (let index = 0; index < 300_000; index += 1) yield { type: "text_delta", messageId: "m", text: "a" };
      yield { type: "done", reason: "completed" };
    };
    const started = await t.service.start({ provider: "claude", prompt: "go" });
    if (!started.ok) throw new Error("refused");
    await t.service.idle();
    const replay: TurnEvent[] = [];
    t.service.subscribe(started.value.turnId, { onEvent: (event) => replay.push(event), onEnd: () => {} });

    expect(replay.length).toBeLessThan(5000);
    const text = replay.filter((event) => event.type === "text_delta").map((event) => (event.type === "text_delta" ? event.text : "")).join("");
    expect(text.length).toBe(300_000);
    expect(replay.at(-1)?.type).toBe("files_changed");
  });
});

describe("a runner that does not stop when asked", () => {
  const never = () => new Promise<never>(() => {});

  it("is cut off after the grace time: the turn ends cancelled, the adapter is told to kill its processes, and the next turn can start", async () => {
    const t = setup();
    const forced = vi.fn();
    t.runner.forceStop = forced;
    t.runner.script = async function* () {
      yield { type: "text", messageId: "m", text: "working" };
      await never();
    };
    const started = await t.service.start({ provider: "claude", prompt: "go" });
    if (!started.ok) throw new Error("refused");
    await vi.waitFor(() => expect(t.runner.requests.length).toBe(1));
    expect(t.service.stop(started.value.turnId)).toBe(true);
    await vi.waitFor(() => expect(t.timers.some((timer) => timer.live)).toBe(true));
    expect(forced).not.toHaveBeenCalled();
    const timer = t.timers.find((entry) => entry.live)!;
    expect(timer.ms).toBe(5000);

    timer.fn();
    await t.service.idle();

    expect(forced).toHaveBeenCalledTimes(1);
    const seen: TurnEvent[] = [];
    t.service.subscribe(started.value.turnId, { onEvent: (event) => seen.push(event), onEnd: () => {} });
    expect(types(seen)).toContain("done");
    expect(seen.find((event) => event.type === "done")).toEqual({ type: "done", reason: "cancelled" });
    expect(seen.find((event) => event.type === "notice")).toMatchObject({ level: "warning", message: expect.stringContaining("did not stop") });
    expect(t.service.current()?.running).toBe(false);
    t.runner.script = () => events({ type: "done", reason: "completed" });
    expect((await t.service.start({ provider: "claude", prompt: "again" })).ok).toBe(true);
  });

  it("does not force anything when the runner stops in time", async () => {
    const t = setup();
    const forced = vi.fn();
    t.runner.forceStop = forced;
    t.runner.script = async function* ({ signal }) {
      await aborted(signal);
    };
    const started = await t.service.start({ provider: "claude", prompt: "go" });
    if (!started.ok) throw new Error("refused");
    await vi.waitFor(() => expect(t.runner.requests.length).toBe(1));
    t.service.stop(started.value.turnId);
    await t.service.idle();

    expect(forced).not.toHaveBeenCalled();
    expect(t.timers.filter((timer) => timer.live)).toEqual([]);
  });

  it("lets shutdown finish once the grace time passes", async () => {
    const t = setup();
    t.runner.script = async function* () {
      await never();
    };
    await t.service.start({ provider: "claude", prompt: "go" });
    await vi.waitFor(() => expect(t.runner.requests.length).toBe(1));

    const closing = t.service.shutdown();
    await vi.waitFor(() => expect(t.timers.some((timer) => timer.live)).toBe(true));
    t.timers.find((timer) => timer.live)!.fn();

    await closing;
    expect(t.service.current()?.running).toBe(false);
  });
});

describe("names undo cannot cover", () => {
  it("puts the names Caztor cannot read in the turn result, next to the changed files", async () => {
    const t = setup();
    t.snapshots.agentChanges = [changed("main.tex")];
    t.snapshots.unreadable = ["made\uFFFD.tex" as never];
    const { events: seen } = await t.turn();
    const files = seen.find((event) => event.type === "files_changed");
    expect(files?.type === "files_changed" && files.notCovered).toEqual(["made\uFFFD.tex"]);
  });

  it("leaves the field out when every name is readable, and when the check itself fails", async () => {
    const t = setup();
    const { events: plain } = await t.turn();
    expect(plain.find((event) => event.type === "files_changed")).not.toHaveProperty("notCovered");
    t.snapshots.unreadableFailure = "cannot walk";
    const { events: failed } = await t.turn();
    expect(failed.find((event) => event.type === "files_changed")).not.toHaveProperty("notCovered");
  });
});

describe("a save by the user right after the agent finished", () => {
  it("is still attributed to the user when it lands while the project is rescanned", async () => {
    const t = setup();
    t.snapshots.agentChanges = [changed("main.tex")];
    t.hooks.onRescan = () => t.userWrites.save("main.tex", "agent text", "user text");

    const { events: seen } = await t.turn();

    expect(t.snapshots.diffs.at(-1)?.userWrites.get(rel("main.tex"))).toEqual({ first: hashOf("agent text"), last: hashOf("user text") });
    const files = seen.find((event) => event.type === "files_changed");
    expect(files?.type === "files_changed" && files.files.map((file) => [file.path, file.mixed])).toEqual([["main.tex", true]]);
  });

  it("is still attributed to the user when it lands while the changes are worked out, by comparing again", async () => {
    const t = setup();
    t.snapshots.agentChanges = [changed("main.tex")];
    let fired = false;
    t.snapshots.duringDiff = () => {
      if (fired) return;
      fired = true;
      t.userWrites.save("main.tex", "agent text", "user text");
    };

    const { events: seen } = await t.turn();

    expect(t.snapshots.diffs).toHaveLength(2);
    const files = seen.find((event) => event.type === "files_changed");
    expect(files?.type === "files_changed" && files.files.map((file) => [file.path, file.mixed])).toEqual([["main.tex", true]]);
    expect(t.userWrites.recording).toBe(false);
  });

  it("compares only once when nothing was saved meanwhile", async () => {
    const t = setup();
    await t.turn();
    expect(t.snapshots.diffs).toHaveLength(1);
  });
});

describe("the order of a turn", () => {
  it("provisions, starts the user-write recorder, takes the snapshot, prunes, runs, stops the recorder, rescans and compares", async () => {
    const t = setup();
    t.snapshots.agentChanges = [changed("main.tex")];
    const { events: seen } = await t.turn();
    expect(t.log).toEqual(["ensure", "begin", "capture", "prune", "run", "rescan", "diff", "end"]);
    expect(t.snapshots.pruned).toEqual([20]);
    expect(types(seen)).toEqual(["turn_started", "done", "files_changed"]);
  });

  it("starts the recorder before the snapshot, so a save that lands during the capture counts as the user's", async () => {
    const t = setup();
    t.snapshots.agentChanges = [changed("a.tex")];
    t.snapshots.duringCapture = () => {
      expect(t.userWrites.recording).toBe(true);
      t.userWrites.save("a.tex", "agent-before", "user-version");
      t.userWrites.save("c.tex", "c-before", "c-user");
    };
    const { events: seen } = await t.turn();
    const writes = t.snapshots.diffs[0]!.userWrites;
    expect([...writes.keys()].sort()).toEqual(["a.tex", "c.tex"]);
    expect(writes.get(rel("c.tex"))).toEqual({ first: hashOf("c-before"), last: hashOf("c-user") });
    const summary = seen.find((event) => event.type === "files_changed");
    // a.tex was changed by both; c.tex only by the user and is not in the list.
    expect(summary).toMatchObject({ files: [{ path: "a.tex", mixed: true }] });
  });

  it("does not count a save that comes after the agent finished", async () => {
    const t = setup();
    await t.turn();
    t.userWrites.save("late.tex", null, "x");
    expect(t.userWrites.recording).toBe(false);
    expect(t.snapshots.diffs[0]!.userWrites.size).toBe(0);
  });

  it("lists the files the agent changed", async () => {
    const t = setup();
    t.snapshots.agentChanges = [changed("a.tex"), changed("new.tex", "created")];
    const { turnId, events: seen } = await t.turn();
    expect(seen.at(-1)).toEqual({ type: "files_changed", turnId, files: [changed("a.tex"), changed("new.tex", "created")] });
  });

  it("reports an empty list when nothing changed", async () => {
    const t = setup();
    const { turnId, events: seen } = await t.turn();
    expect(seen.at(-1)).toEqual({ type: "files_changed", turnId, files: [] });
  });

  it("passes the prompt, the stored model and the provisioned definition to the runner", async () => {
    const t = setup({ state: { models: { claude: "sonnet" } } });
    t.provisioner.agent = agentDefinition("agent7");
    await t.turn("Shorten the abstract");
    expect(t.runner.requests).toEqual([{ prompt: "Shorten the abstract", sessionId: null, model: "sonnet", agent: agentDefinition("agent7"), authMode: "account" }]);
  });

  it("tells the chat which files the snapshot could not protect", async () => {
    const t = setup();
    t.snapshots.captureResult = { partial: true, unprotected: [rel("big.pdf")] };
    const { events: seen } = await t.turn();
    expect(seen[0]).toEqual({ type: "turn_started", turnId: "t1", provider: "claude", snapshotPartial: true, unprotected: ["big.pdf"] });
  });

  it("names at most 20 unprotected files and counts the rest, so a large project keeps the event small", async () => {
    const t = setup();
    const many = Array.from({ length: 50_000 }, (_, index) => rel(`env/lib/file-${index}.py`));
    t.snapshots.captureResult = { partial: true, unprotected: many };
    const { events: seen } = await t.turn();
    expect(seen[0]).toEqual({ type: "turn_started", turnId: "t1", provider: "claude", snapshotPartial: true, unprotected: many.slice(0, 20), unprotectedCount: 50_000 });
  });
});

describe("a snapshot that cannot be taken", () => {
  it("does not start the agent, says why, ends the turn failed and stops the recorder", async () => {
    const t = setup();
    t.snapshots.captureFailure = "No space left on device";
    const { events: seen } = await t.turn();
    expect(t.log).toEqual(["ensure", "begin", "capture", "end"]);
    expect(t.runner.requests).toEqual([]);
    expect(seen).toEqual([
      { type: "error", code: "snapshot_failed", message: expect.stringContaining("No space left on device") },
      { type: "done", reason: "failed" },
    ]);
    expect(t.userWrites.recording).toBe(false);
  });

  it("is ready for the next turn afterwards", async () => {
    const t = setup();
    t.snapshots.captureFailure = "disk full";
    await t.turn();
    t.snapshots.captureFailure = null;
    const { events: seen } = await t.turn();
    expect(types(seen)).toContain("files_changed");
    expect(t.runner.requests).toHaveLength(1);
  });
});

describe("provisioning", () => {
  it("ends the turn failed, before any snapshot, when the definition cannot be provisioned", async () => {
    const t = setup();
    t.provisioner.failure = "The .claude folder is a link";
    const { events: seen } = await t.turn();
    expect(t.log).toEqual(["ensure"]);
    expect(seen).toEqual([
      { type: "error", code: "provider_error", message: expect.stringContaining("The .claude folder is a link") },
      { type: "done", reason: "failed" },
    ]);
  });

  it("does not blame the agent definition for a problem with the project folder it needs", async () => {
    const t = setup();
    t.provisioner.failure = ".caztor is a link, so Caztor cannot keep its settings there.";
    const { events: seen } = await t.turn();
    const message = (seen[0] as { message: string }).message;
    expect(message).toBe("Caztor could not prepare the project for the assistant: .caztor is a link, so Caztor cannot keep its settings there.");
    expect(message).not.toMatch(/agent definition could not be prepared/);
  });

  it("keeps a definition the user changed, says so with the replace action, and still runs the turn", async () => {
    const t = setup();
    t.provisioner.outcomes = [{ target: ".claude/agents/caztor.md", status: "skipped_user_modified" }];
    const { events: seen } = await t.turn();
    expect(seen[0]).toEqual({
      type: "notice",
      level: "warning",
      message: expect.stringContaining(".claude/agents/caztor.md"),
      action: "replace_definition",
    });
    expect(types(seen)).toContain("files_changed");
    expect(t.runner.requests).toHaveLength(1);
  });
});

describe("writing guide outcomes", () => {
  it("says which guide the user changed, in words that fit a guide, and keeps the replace action", async () => {
    const t = setup();
    t.provisioner.outcomes = [
      { target: ".claude/agents/caztor.md", status: "unchanged" },
      { target: ".caztor/guides/04-limitations.md", status: "skipped_user_modified" },
    ];
    const { events: seen } = await t.turn();
    expect(seen[0]).toEqual({
      type: "notice",
      level: "warning",
      message: "The writing guide `04-limitations.md` was changed, so Caztor kept the changed version. Replace it to restore Caztor's guide.",
      action: "replace_definition",
    });
    expect(t.runner.requests).toHaveLength(1);
  });

  it("gives one notice per changed guide, and the definition keeps its own wording", async () => {
    const t = setup();
    t.provisioner.outcomes = [
      { target: ".claude/agents/caztor.md", status: "skipped_user_modified" },
      { target: ".caztor/guides/INDEX.md", status: "skipped_user_modified" },
      { target: ".caztor/guides/LICENSE-papersmith-ai.txt", status: "skipped_user_modified" },
    ];
    const { events: seen } = await t.turn();
    const messages = seen.filter((event) => event.type === "notice").map((event) => (event as { message: string }).message);
    expect(messages).toEqual([
      ".claude/agents/caztor.md was changed by you, so Caztor kept your version. Replace it to use Caztor's definition.",
      "The writing guide `INDEX.md` was changed, so Caztor kept the changed version. Replace it to restore Caztor's guide.",
      "The writing guide `LICENSE-papersmith-ai.txt` was changed, so Caztor kept the changed version. Replace it to restore Caztor's guide.",
    ]);
  });

  it("warns that the guides are unavailable, says why, and still runs the turn", async () => {
    const t = setup();
    t.provisioner.outcomes = [
      { target: ".claude/agents/caztor.md", status: "unchanged" },
      { target: ".caztor/guides", status: "unavailable", detail: "The built-in writing guides could not be read: ENOENT" },
    ];
    const { events: seen } = await t.turn();
    expect(seen[0]).toEqual({
      type: "notice",
      level: "warning",
      message: "The writing guides could not be prepared, so this turn runs without them: The built-in writing guides could not be read: ENOENT",
    });
    expect(types(seen)).toContain("files_changed");
    expect(types(seen)).toContain("done");
    expect(t.runner.requests).toHaveLength(1);
  });

  it("stays silent when guides were created, updated or unchanged", async () => {
    const t = setup();
    t.provisioner.outcomes = [
      { target: ".caztor/guides/INDEX.md", status: "created" },
      { target: ".caztor/guides/08-abstract.md", status: "updated" },
      { target: ".caztor/guides/01-materials-and-methods.md", status: "unchanged" },
    ];
    const { events: seen } = await t.turn();
    expect(seen.filter((event) => event.type === "notice")).toEqual([]);
  });
});

describe("session continuity", () => {
  const sessionTurn = (id: string) => (): ReturnType<typeof events> =>
    events({ type: "session", sessionId: id }, { type: "done", reason: "completed" });

  it("resumes the stored session while the definition and the isolation stay the same", async () => {
    const t = setup();
    t.runner.script = sessionTurn("s1");
    await t.turn("first");
    expect(t.state.current.sessions.claude).toEqual({ sessionId: "s1", agentHash: hashOf("agent1"), isolation: "tier-1", authMode: "account" });
    await t.turn("second");
    expect(t.runner.requests.map((request) => request.sessionId)).toEqual([null, "s1"]);
  });

  it("starts a new conversation and says so when the definition changed", async () => {
    const t = setup();
    t.runner.script = sessionTurn("s1");
    await t.turn("first");
    t.provisioner.agent = agentDefinition("agent2");
    t.runner.script = sessionTurn("s2");
    const { events: seen } = await t.turn("second");
    expect(t.runner.requests[1]!.sessionId).toBeNull();
    expect(seen[0]).toEqual({ type: "notice", level: "info", message: "New conversation started because the agent definition changed." });
    expect(t.state.current.sessions.claude).toEqual({ sessionId: "s2", agentHash: hashOf("agent2"), isolation: "tier-1", authMode: "account" });
  });

  it("resets exactly once when the definition changes, and the next turn goes on with the new conversation", async () => {
    const t = setup();
    t.runner.script = sessionTurn("s1");
    await t.turn("first");
    t.provisioner.agent = agentDefinition("agent-with-guide-core");
    t.runner.script = sessionTurn("s2");
    const second = await t.turn("second");
    const third = await t.turn("third");
    expect(t.runner.requests.map((request) => request.sessionId)).toEqual([null, null, "s2"]);
    const resets = (seen: typeof second.events) => seen.filter((event) => event.type === "notice" && event.message.includes("agent definition changed"));
    expect(resets(second.events)).toHaveLength(1);
    expect(resets(third.events)).toHaveLength(0);
  });

  it("does not reset the conversation when only the writing guides were updated", async () => {
    const t = setup();
    t.runner.script = sessionTurn("s1");
    await t.turn("first");
    t.provisioner.outcomes = [
      { target: ".claude/agents/caztor.md", status: "unchanged" },
      { target: ".caztor/guides/INDEX.md", status: "updated" },
      { target: ".caztor/guides/08-abstract.md", status: "created" },
    ];
    const { events: seen } = await t.turn("second");
    expect(t.runner.requests.map((request) => request.sessionId)).toEqual([null, "s1"]);
    expect(seen.some((event) => event.type === "notice")).toBe(false);
  });

  it("starts a new conversation and says so when the isolation changed", async () => {
    const t = setup();
    t.runner.script = sessionTurn("s1");
    await t.turn("first");
    t.runner.isolationTier = "tier-2";
    const { events: seen } = await t.turn("second");
    expect(t.runner.requests[1]!.sessionId).toBeNull();
    expect(seen[0]).toMatchObject({ type: "notice", message: "New conversation started because the isolation level changed." });
  });

  it("says nothing about a new conversation when there was none before", async () => {
    const t = setup();
    const { events: seen } = await t.turn();
    expect(seen.some((event) => event.type === "notice")).toBe(false);
  });

  it("keeps the session of each provider apart", async () => {
    const t = setup({ providers: ["claude", "opencode"], state: { models: { opencode: "free/model" } } });
    t.runners.claude.script = sessionTurn("claude-1");
    t.runners.opencode.script = sessionTurn("opencode-1");
    await t.turn("a", "claude");
    await t.turn("b", "opencode");
    await t.turn("c", "claude");
    expect(t.runners.claude.requests.map((request) => request.sessionId)).toEqual([null, "claude-1"]);
    expect(t.runners.opencode.requests.map((request) => request.sessionId)).toEqual([null]);
  });

  it("forgets the conversation of a provider when a new chat is started", async () => {
    const t = setup();
    t.runner.script = sessionTurn("s1");
    await t.turn("first");
    await t.service.resetSession("claude");
    expect(t.state.current.sessions.claude).toBeUndefined();
    expect(t.history.cleared).toEqual(["claude"]);
    await t.turn("second");
    expect(t.runner.requests[1]!.sessionId).toBeNull();
  });
});

describe("the changed-files list of an interrupted turn", () => {
  it.each([
    ["completed", [{ type: "done", reason: "completed" }]],
    ["failed", [{ type: "error", code: "provider_error", message: "boom" }, { type: "done", reason: "failed" }]],
  ] as const)("is computed when the turn %s", async (_name, script) => {
    const t = setup();
    t.snapshots.agentChanges = [changed("a.tex")];
    t.runner.script = () => events(...script);
    const { events: seen } = await t.turn();
    expect(seen.at(-1)).toMatchObject({ type: "files_changed", files: [{ path: "a.tex" }] });
  });

  it("is computed when the user stops the turn, which ends cancelled", async () => {
    const t = setup();
    t.snapshots.agentChanges = [changed("a.tex")];
    t.runner.script = async function* ({ signal }) {
      yield { type: "text_delta", messageId: "m", text: "Working" };
      await aborted(signal);
      yield { type: "done", reason: "cancelled" };
    };
    const started = await t.service.start({ provider: "claude", prompt: "Long task" });
    expect(started.ok).toBe(true);
    const turnId = started.ok ? started.value.turnId : "";
    const seen: TurnEvent[] = [];
    const ended = new Promise<void>((resolve) => t.service.subscribe(turnId, { onEvent: (event) => seen.push(event), onEnd: resolve }));
    await vi.waitFor(() => expect(seen.some((event) => event.type === "text_delta")).toBe(true));
    expect(t.service.stop(turnId)).toBe(true);
    await ended;
    expect(t.runner.requests[0]).toBeDefined();
    expect(seen.filter((event) => event.type === "done")).toEqual([{ type: "done", reason: "cancelled" }]);
    expect(seen.at(-1)).toMatchObject({ type: "files_changed", files: [{ path: "a.tex" }] });
  });

  it("stops asking nothing of the runner when the stop comes before it started", async () => {
    const t = setup();
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => (release = resolve));
    t.provisioner.ensure = async () => {
      await gate;
      return { ok: true, value: { outcomes: [], agent: agentDefinition() } };
    };
    const started = await t.service.start({ provider: "claude", prompt: "x" });
    const turnId = started.ok ? started.value.turnId : "";
    expect(t.service.stop(turnId)).toBe(true);
    release();
    await t.service.idle();
    expect(t.runner.requests).toEqual([]);
    const seen: TurnEvent[] = [];
    t.service.subscribe(turnId, { onEvent: (event) => seen.push(event), onEnd: () => {} });
    expect(seen.filter((event) => event.type === "done")).toEqual([{ type: "done", reason: "cancelled" }]);
  });

  it("knows no turn that never existed or that already ended", async () => {
    const t = setup();
    expect(t.service.stop("nope")).toBe(false);
    const { turnId } = await t.turn();
    expect(t.service.stop(turnId)).toBe(false);
  });
});

describe("a runner that breaks its contract", () => {
  it("fails the turn when the stream ends without a done event", async () => {
    const t = setup();
    t.runner.script = () => events({ type: "text", messageId: "m", text: "Half" });
    const { events: seen } = await t.turn();
    expect(seen.slice(1, 4)).toEqual([
      { type: "text", messageId: "m", text: "Half" },
      { type: "error", code: "provider_error", message: expect.stringContaining("ended without finishing") },
      { type: "done", reason: "failed" },
    ]);
    expect(seen.at(-1)?.type).toBe("files_changed");
  });

  it("fails the turn when the runner throws", async () => {
    const t = setup();
    t.runner.script = async function* () {
      yield { type: "text", messageId: "m", text: "Half" } as const;
      throw new Error("spawn exploded");
    };
    const { events: seen } = await t.turn();
    expect(seen.filter((event) => event.type === "error")).toEqual([
      { type: "error", code: "provider_error", message: expect.any(String), detail: "spawn exploded" },
    ]);
    expect(seen.filter((event) => event.type === "done")).toEqual([{ type: "done", reason: "failed" }]);
  });

  it("ignores anything after the done event, so there is exactly one done and it is last of the agent's", async () => {
    const t = setup();
    t.runner.script = () =>
      events({ type: "done", reason: "completed" }, { type: "text", messageId: "m", text: "late" }, { type: "done", reason: "failed" });
    const { events: seen } = await t.turn();
    expect(types(seen)).toEqual(["turn_started", "done", "files_changed"]);
    expect(seen[1]).toEqual({ type: "done", reason: "completed" });
  });

  it("ends cancelled, not failed, when the stream ends without done after a stop", async () => {
    const t = setup();
    t.runner.script = async function* ({ signal }) {
      await aborted(signal);
    };
    const started = await t.service.start({ provider: "claude", prompt: "x" });
    const turnId = started.ok ? started.value.turnId : "";
    await vi.waitFor(() => expect(t.runner.requests).toHaveLength(1));
    t.service.stop(turnId);
    await t.service.idle();
    const seen: TurnEvent[] = [];
    t.service.subscribe(turnId, { onEvent: (event) => seen.push(event), onEnd: () => {} });
    expect(seen.filter((event) => event.type === "done")).toEqual([{ type: "done", reason: "cancelled" }]);
    expect(seen.some((event) => event.type === "error")).toBe(false);
  });
});

describe("one turn at a time", () => {
  it("refuses a second turn while one runs and accepts one afterwards", async () => {
    const t = setup();
    let finish: () => void = () => {};
    const gate = new Promise<void>((resolve) => (finish = resolve));
    t.runner.script = async function* () {
      await gate;
      yield { type: "done", reason: "completed" } as const;
    };
    const first = await t.service.start({ provider: "claude", prompt: "one" });
    expect(first.ok).toBe(true);
    const second = await t.service.start({ provider: "claude", prompt: "two" });
    expect(second).toEqual({ ok: false, error: { code: "busy", message: expect.stringContaining("already running") } });
    expect(t.service.current()).toMatchObject({ turnId: "t1", provider: "claude", running: true });
    finish();
    await t.service.idle();
    expect(t.service.current()).toMatchObject({ turnId: "t1", running: false });
    expect((await t.service.start({ provider: "claude", prompt: "three" })).ok).toBe(true);
    await t.service.idle();
  });

  it("refuses two turns started at the same moment", async () => {
    const t = setup();
    const [a, b] = await Promise.all([t.service.start({ provider: "claude", prompt: "a" }), t.service.start({ provider: "claude", prompt: "b" })]);
    expect([a.ok, b.ok].sort()).toEqual([false, true]);
    await t.service.idle();
    expect(t.runner.requests).toHaveLength(1);
  });
});

describe("requests that are refused before anything happens", () => {
  const nothingHappened = (t: ReturnType<typeof setup>) => {
    expect(t.log).toEqual([]);
    expect(t.service.current()).toBeNull();
  };

  it("refuses an empty prompt and one that is too long", async () => {
    const t = setup();
    expect(await t.service.start({ provider: "claude", prompt: "  \n " })).toMatchObject({ ok: false, error: { code: "invalid_prompt" } });
    expect(await t.service.start({ provider: "claude", prompt: "x".repeat(100_001) })).toMatchObject({ ok: false, error: { code: "invalid_prompt" } });
    nothingHappened(t);
  });

  it("refuses a provider that has no adapter", async () => {
    const t = setup();
    expect(await t.service.start({ provider: "codex", prompt: "hi" })).toMatchObject({ ok: false, error: { code: "unknown_provider" } });
    nothingHappened(t);
  });

  it("checks a provider once a minute, not before every turn", async () => {
    let clock = 1_000_000;
    const t = setup({ now: () => clock });
    let checks = 0;
    const detect = t.runner.detect.bind(t.runner);
    t.runner.detect = async () => ((checks += 1), detect());
    await t.turn();
    await t.turn();
    expect(checks).toBe(1);
    clock += 61_000;
    await t.turn();
    expect(checks).toBe(2);
  });

  it("checks again after finding a provider not installed, so installing it shows at once", async () => {
    const t = setup({ now: () => 1_000_000 });
    t.runner.status = { provider: "claude", installed: false, unavailableReason: "claude is not installed", requiresModel: false };
    expect(await t.service.start({ provider: "claude", prompt: "hi" })).toMatchObject({ ok: false, error: { code: "not_installed" } });
    t.runner.status = { provider: "claude", installed: true, requiresModel: false };
    expect((await t.turn()).events.map((event) => event.type)).toContain("done");
  });

  it("refuses a provider that is not installed, with the reason", async () => {
    const t = setup();
    t.runner.status = { provider: "claude", installed: false, unavailableReason: "claude is not installed", requiresModel: false };
    expect(await t.service.start({ provider: "claude", prompt: "hi" })).toEqual({
      ok: false,
      error: { code: "not_installed", message: "claude is not installed" },
    });
    nothingHappened(t);
  });

  it("refuses a provider that needs a model when none is set, and runs once one is", async () => {
    const t = setup({ providers: ["opencode"] });
    t.runners.opencode.status = { provider: "opencode", installed: true, requiresModel: true };
    expect(await t.service.start({ provider: "opencode", prompt: "hi" })).toMatchObject({ ok: false, error: { code: "model_required" } });
    nothingHappened(t);
    await t.state.update({ models: { opencode: "anthropic/claude-sonnet" } });
    const { events: seen } = await t.turn("hi", "opencode");
    expect(types(seen)).toContain("files_changed");
    expect(t.runners.opencode.requests[0]!.model).toBe("anthropic/claude-sonnet");
  });
});

describe("undo and the note to the agent", () => {
  it("names the reverted files in the next prompt only, and rescans after the undo", async () => {
    const t = setup();
    t.snapshots.restoreResult = { status: "restored", files: [rel("a.tex"), rel("b.tex")], skipped: [rel("c.tex")] };
    const { turnId } = await t.turn("first");
    t.log.length = 0;
    expect(await t.service.undo(turnId, "strict")).toEqual(t.snapshots.restoreResult);
    expect(t.snapshots.restores).toEqual([{ turnId, mode: "strict" }]);
    expect(t.log).toEqual(["restore", "rescan"]);

    await t.turn("Try again");
    await t.turn("Another thing");
    const [, second, third] = t.runner.requests;
    expect(second!.prompt.startsWith(REVERT_NOTE_HEADER)).toBe(true);
    expect(second!.prompt).toContain("- a.tex");
    expect(second!.prompt).toContain("- b.tex");
    expect(second!.prompt).not.toContain("c.tex");
    expect(second!.prompt.endsWith("Try again")).toBe(true);
    expect(third!.prompt).toBe("Another thing");
  });

  it("collects the files of several undos made before the next message into one note", async () => {
    const t = setup();
    const first = await t.turn("one");
    const second = await t.turn("two");
    t.snapshots.restoreResult = { status: "restored", files: [rel("b.tex")], skipped: [] };
    await t.service.undo(second.turnId, "strict");
    t.snapshots.restoreResult = { status: "restored", files: [rel("a.tex"), rel("b.tex")], skipped: [] };
    await t.service.undo(first.turnId, "strict");
    await t.turn("three");
    const prompt = t.runner.requests.at(-1)!.prompt;
    expect(prompt.match(/- b\.tex/g)).toHaveLength(1);
    expect(prompt).toContain("- a.tex");
  });

  it.each([
    ["a conflict", { status: "conflict", conflicts: [{ path: rel("a.tex"), expected: null, actual: null }] }],
    ["an unavailable undo", { status: "unavailable", reason: "not_latest" }],
    ["a failure", { status: "failed", message: "disk full" }],
  ] satisfies Array<[string, RestoreResult]>)("adds no note after %s", async (_name, result: RestoreResult) => {
    const t = setup();
    const { turnId } = await t.turn("first");
    t.snapshots.restoreResult = result;
    expect(await t.service.undo(turnId, "strict")).toEqual(result);
    await t.turn("next");
    expect(t.runner.requests[1]!.prompt).toBe("next");
  });

  it("does not undo while a turn runs", async () => {
    const t = setup();
    t.runner.script = async function* ({ signal }) {
      await aborted(signal);
      yield { type: "done", reason: "cancelled" } as const;
    };
    const started = await t.service.start({ provider: "claude", prompt: "x" });
    const turnId = started.ok ? started.value.turnId : "";
    expect(await t.service.undo("older", "strict")).toEqual({ status: "busy" });
    expect(t.snapshots.restores).toEqual([]);
    t.service.stop(turnId);
    await t.service.idle();
  });
});

describe("watching a turn", () => {
  it("replays what a late subscriber missed and then follows the turn, and a dropped subscriber does not stop it", async () => {
    const t = setup();
    let finish: () => void = () => {};
    const gate = new Promise<void>((resolve) => (finish = resolve));
    t.runner.script = async function* () {
      yield { type: "text_delta", messageId: "m", text: "one " } as const;
      await gate;
      yield { type: "text_delta", messageId: "m", text: "two" } as const;
      yield { type: "done", reason: "completed" } as const;
    };
    const started = await t.service.start({ provider: "claude", prompt: "x" });
    const turnId = started.ok ? started.value.turnId : "";

    const firstSeen: Array<[number, string]> = [];
    const drop = t.service.subscribe(turnId, { onEvent: (event, seq) => firstSeen.push([seq, event.type]), onEnd: () => {} });
    await vi.waitFor(() => expect(firstSeen.map(([, type]) => type)).toContain("text_delta"));
    drop?.();

    // The connection returns: everything so far is replayed, then the rest follows.
    const lateSeen: Array<[number, string]> = [];
    const ended = new Promise<void>((resolve) => t.service.subscribe(turnId, { onEvent: (event, seq) => lateSeen.push([seq, event.type]), onEnd: resolve }));
    expect(lateSeen.map(([, type]) => type)).toEqual(["turn_started", "text_delta"]);
    finish();
    await ended;
    expect(lateSeen).toEqual([
      [1, "turn_started"],
      [2, "text_delta"],
      [3, "text_delta"],
      [4, "done"],
      [5, "files_changed"],
    ]);
    expect(firstSeen.map(([seq]) => seq)).toEqual([1, 2]);
  });

  it("skips what the subscriber already has", async () => {
    const t = setup();
    const { turnId } = await t.turn();
    const seen: number[] = [];
    t.service.subscribe(turnId, { onEvent: (_event, seq) => seen.push(seq), onEnd: () => {} }, 2);
    expect(seen).toEqual([3]);
  });

  it("ends a subscription at once for a turn that already ended, and knows no other turn", async () => {
    const t = setup();
    const { turnId } = await t.turn();
    const onEnd = vi.fn();
    t.service.subscribe(turnId, { onEvent: () => {}, onEnd });
    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(t.service.subscribe("unknown", { onEvent: () => {}, onEnd: () => {} })).toBeNull();
  });
});

describe("the visible conversation", () => {
  it("is stored per provider, with the text deltas joined", async () => {
    const t = setup();
    t.snapshots.agentChanges = [changed("a.tex")];
    t.runner.script = () =>
      events(
        { type: "text_delta", messageId: "m", text: "Done " },
        { type: "text_delta", messageId: "m", text: "it." },
        { type: "done", reason: "completed" },
      );
    const { turnId } = await t.turn("Fix it");
    expect(t.history.records).toHaveLength(1);
    expect(t.history.records[0]).toMatchObject({ turnId, provider: "claude", prompt: "Fix it" });
    expect(t.history.records[0]!.events.map((event) => event.type)).toEqual(["turn_started", "text", "done", "files_changed"]);
    expect(t.history.records[0]!.events[1]).toEqual({ type: "text", messageId: "m", text: "Done it." });
  });

  it("keeps the readable error of a turn that did not start", async () => {
    const t = setup();
    t.snapshots.captureFailure = "disk full";
    await t.turn("Fix it");
    expect(t.history.records[0]!.events.map((event) => event.type)).toEqual(["error", "done"]);
  });

  it("does not store the revert note as something the user wrote", async () => {
    const t = setup();
    const first = await t.turn("one");
    t.snapshots.restoreResult = { status: "restored", files: [rel("a.tex")], skipped: [] };
    await t.service.undo(first.turnId, "strict");
    await t.turn("two");
    expect(t.history.records.map((record) => record.prompt)).toEqual(["one", "two"]);
  });
});

describe("replacing the definition", () => {
  it("asks the provisioner to replace the user's file, and not while a turn runs", async () => {
    const t = setup();
    t.provisioner.outcomes = [{ target: ".claude/agents/caztor.md", status: "updated" }];
    expect(await t.service.replaceDefinition("claude")).toEqual({ ok: true, value: { outcomes: t.provisioner.outcomes } });
    expect(t.provisioner.calls).toEqual([{ provider: "claude", replace: true }]);

    let finish: () => void = () => {};
    const gate = new Promise<void>((resolve) => (finish = resolve));
    t.runner.script = async function* () {
      await gate;
      yield { type: "done", reason: "completed" } as const;
    };
    await t.service.start({ provider: "claude", prompt: "x" });
    expect(await t.service.replaceDefinition("claude")).toEqual({ ok: false, error: { code: "busy", message: expect.any(String) } });
    finish();
    await t.service.idle();
  });

  it("passes on a provisioning failure", async () => {
    const t = setup();
    t.provisioner.failure = "not allowed";
    expect(await t.service.replaceDefinition("claude")).toEqual({ ok: false, error: { code: "provision_failed", message: "not allowed" } });
  });
});

describe("shutdown", () => {
  it("stops a running turn and waits for it to end", async () => {
    const t = setup();
    t.runner.script = async function* ({ signal }) {
      await aborted(signal);
      yield { type: "done", reason: "cancelled" } as const;
    };
    await t.service.start({ provider: "claude", prompt: "x" });
    await vi.waitFor(() => expect(t.runner.requests).toHaveLength(1));
    await (t.service as TurnService).shutdown();
    expect(t.service.current()?.running).toBe(false);
  });
});
