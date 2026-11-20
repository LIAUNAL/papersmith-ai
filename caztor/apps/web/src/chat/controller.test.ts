import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client.ts";
import { apiError, createFakeApi } from "../testing/fake-api.ts";
import { ChatController } from "./controller.ts";
import type { ChatHistory, ChatTurnRecord } from "../api/types.ts";

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));
const lastTurn = (controller: ChatController) => controller.getSnapshot().chat.turns.at(-1)!;
const texts = (controller: ChatController) => lastTurn(controller).items.flatMap((item) => (item.kind === "text" ? [item.text] : []));

function setup(init: Parameters<typeof createFakeApi>[0] = {}) {
  const fake = createFakeApi(init);
  const waits: number[] = [];
  const controller = new ChatController({ api: fake.api, wait: async (ms) => void waits.push(ms) });
  return { fake, controller, waits };
}

const record = (turnId: string, prompt: string, text: string): ChatTurnRecord => ({
  turnId,
  provider: "claude",
  prompt,
  startedAt: 1,
  events: [
    { type: "turn_started", turnId, provider: "claude", snapshotPartial: false, unprotected: [] },
    { type: "text", messageId: "m", text },
    { type: "done", reason: "completed" },
    { type: "files_changed", turnId, files: [] },
  ],
});
const history = (patch: Partial<ChatHistory>): ChatHistory => ({ provider: "claude", turns: [], undoableTurnId: null, undoProblem: null, running: false, currentTurnId: null, ...patch });

describe("ChatController load", () => {
  it("loads the providers and restores the history of the selected one", async () => {
    const { fake, controller } = setup();
    fake.chat.history.claude = history({ turns: [record("t1", "Hello", "Hi there")], undoableTurnId: "t1" });
    await controller.load();
    const view = controller.getSnapshot();
    expect(view.loading).toBe(false);
    expect(view.providers?.selected).toBe("claude");
    expect(view.chat.turns.map((turn) => turn.prompt)).toEqual(["Hello"]);
    expect(view.chat.undoableTurnId).toBe("t1");
  });

  it("shows a readable failure when the providers cannot be read, and loads again on request", async () => {
    const { fake, controller } = setup();
    fake.failNext(apiError("boom", "The server is not answering.", 500));
    await controller.load();
    expect(controller.getSnapshot().loadError).toBe("The server is not answering.");
    await controller.load();
    expect(controller.getSnapshot().loadError).toBeNull();
    expect(controller.getSnapshot().providers).not.toBeNull();
  });

  const unchosen = (): Parameters<typeof createFakeApi>[0] => ({
    providers: {
      selected: null,
      providers: [
        { id: "opencode", installed: true, requiresModel: true, model: null },
        { id: "claude", installed: true, requiresModel: false, model: null },
        { id: "codex", installed: false, unavailableReason: "no", requiresModel: false, model: null },
      ],
    },
  });

  it("shows the first installed provider as selected when the project has no choice yet, claude first, without saving it", async () => {
    const { fake, controller } = setup(unchosen());
    await controller.load();
    expect(controller.getSnapshot().providers?.selected).toBe("claude");
    expect(fake.calls.some((call) => call.startsWith("selectProvider"))).toBe(false);
    expect(fake.calls).toContain("chatHistory claude");
  });

  it("keeps the shown choice after the model or a re-check changes the listing, still unsaved", async () => {
    const { fake, controller } = setup(unchosen());
    await controller.load();
    await controller.setModel("claude", "some-model");
    expect(controller.getSnapshot().providers?.selected).toBe("claude");
    await controller.recheck();
    expect(controller.getSnapshot().providers?.selected).toBe("claude");
    expect(fake.calls.some((call) => call.startsWith("selectProvider"))).toBe(false);
  });

  it("saves the shown choice when the user sends a message", async () => {
    const { fake, controller } = setup(unchosen());
    await controller.load();
    const sending = controller.send("Hello");
    await flush();
    const saved = fake.calls.indexOf("selectProvider claude");
    expect(saved).toBeGreaterThanOrEqual(0);
    expect(saved).toBeLessThan(fake.calls.indexOf("streamTurn start claude"));
    fake.chat.begin("t1");
    fake.chat.emit({ type: "done", reason: "completed" });
    fake.chat.end();
    await sending;
    expect(fake.calls.filter((call) => call === "selectProvider claude")).toHaveLength(1);
  });

  it("saves the shown choice when the user picks it explicitly", async () => {
    const { fake, controller } = setup(unchosen());
    await controller.load();
    await controller.selectProvider("claude");
    expect(fake.calls.filter((call) => call === "selectProvider claude")).toHaveLength(1);
  });

  it("saves a different provider the user picks instead of the shown one", async () => {
    const { fake, controller } = setup(unchosen());
    await controller.load();
    await controller.selectProvider("opencode");
    expect(fake.calls).toContain("selectProvider opencode");
    expect(fake.calls).not.toContain("selectProvider claude");
    expect(controller.getSnapshot().providers?.selected).toBe("opencode");
  });

  it("leaves the choice empty when no provider is installed", async () => {
    const { fake, controller } = setup({ providers: { selected: null, providers: [{ id: "claude", installed: false, unavailableReason: "no", requiresModel: false, model: null }] } });
    await controller.load();
    expect(controller.getSnapshot().providers?.selected).toBeNull();
    expect(fake.calls.some((call) => call.startsWith("selectProvider"))).toBe(false);
  });

  it("follows a turn that is already running after a page reload, without duplicating what it shows", async () => {
    const { fake, controller } = setup();
    fake.chat.history.claude = history({ running: true, currentTurnId: "t1" });
    // The turn had sent three events before the page loaded.
    fake.chat.emit({ type: "turn_started", turnId: "t1", provider: "claude", snapshotPartial: false, unprotected: [] });
    fake.chat.emit({ type: "text_delta", messageId: "m", text: "Part " });
    await controller.load();
    expect(controller.getSnapshot().chat.running).toBe(true);
    expect(fake.chat.follows).toEqual([0]);
    expect(texts(controller)).toEqual(["Part "]);
    fake.chat.emit({ type: "text_delta", messageId: "m", text: "two" });
    fake.chat.emit({ type: "done", reason: "completed" });
    fake.chat.end();
    await flush();
    expect(texts(controller)).toEqual(["Part two"]);
    expect(controller.getSnapshot().chat.running).toBe(false);
  });
});

describe("ChatController send", () => {
  it("sends the message to the selected provider and shows the answer as it streams", async () => {
    const { fake, controller } = setup();
    await controller.load();
    const sending = controller.send("Fix the title");
    await flush();
    expect(fake.chat.starts).toEqual([{ provider: "claude", prompt: "Fix the title" }]);
    expect(controller.getSnapshot().chat.running).toBe(true);
    expect(lastTurn(controller).prompt).toBe("Fix the title");
    fake.chat.begin("t1");
    fake.chat.emit({ type: "text_delta", messageId: "m", text: "Done" });
    expect(texts(controller)).toEqual(["Done"]);
    fake.chat.emit({ type: "done", reason: "completed" });
    fake.chat.end();
    await sending;
    expect(controller.getSnapshot().chat.running).toBe(false);
    expect(lastTurn(controller)).toMatchObject({ turnId: "t1", status: "completed" });
  });

  it("refreshes which turn can be undone when a turn ends", async () => {
    const { fake, controller } = setup();
    await controller.load();
    const sending = controller.send("Edit");
    await flush();
    fake.chat.begin("t1");
    fake.chat.emit({ type: "done", reason: "completed" });
    fake.chat.history.claude = history({ undoableTurnId: "t1" });
    fake.chat.end();
    await sending;
    expect(controller.getSnapshot().chat.undoableTurnId).toBe("t1");
  });

  it("reads the providers again when a turn ends, so the sign-in panel learns the login", async () => {
    const { fake, controller } = setup();
    await controller.load();
    const before = fake.calls.filter((call) => call === "listProviders").length;
    const sending = controller.send("Edit");
    await flush();
    fake.chat.begin("t1");
    fake.chat.emit({ type: "done", reason: "completed" });
    fake.chat.end();
    await sending;
    expect(fake.calls.filter((call) => call === "listProviders").length).toBe(before + 1);
  });

  it("keeps a provider picked while the providers are being read again after a turn", async () => {
    const providers = [
      { id: "claude" as const, installed: true, requiresModel: false, model: null },
      { id: "codex" as const, installed: true, requiresModel: false, model: null },
    ];
    const { fake, controller } = setup({ providers: { selected: "claude", providers } });
    await controller.load();
    const read = fake.api.listProviders;
    const old = await read();
    let answer: (listing: typeof old) => void = () => {};
    fake.api.listProviders = () => new Promise((resolve) => (answer = resolve));
    const sending = controller.send("Edit");
    await flush();
    fake.chat.begin("t1");
    fake.chat.emit({ type: "done", reason: "completed" });
    fake.chat.end();
    await flush();
    await controller.selectProvider("codex");
    answer(old);
    await sending;
    expect(controller.getSnapshot().providers?.selected).toBe("codex");
  });

  it("does not send an empty message, a second message while busy, or a message without a usable provider", async () => {
    const { fake, controller } = setup();
    await controller.load();
    await controller.send("   ");
    expect(fake.chat.starts).toEqual([]);
    void controller.send("first");
    await flush();
    await controller.send("second");
    expect(fake.chat.starts).toHaveLength(1);
    fake.chat.begin();
    fake.chat.emit({ type: "done", reason: "completed" });
    fake.chat.end();
    await flush();

    const none = setup({ providers: { selected: null, providers: [] } });
    await none.controller.load();
    await none.controller.send("hello");
    expect(none.controller.getSnapshot().problem).toMatch(/choose a provider/i);
    expect(none.fake.chat.starts).toEqual([]);

    const missing = setup({ providers: { selected: "codex", providers: [{ id: "codex", installed: false, unavailableReason: "codex is not installed.", requiresModel: false, model: null }] } });
    await missing.controller.load();
    await missing.controller.send("hello");
    expect(missing.controller.getSnapshot().problem).toBe("codex is not installed.");
    expect(missing.fake.chat.starts).toEqual([]);
  });

  it("removes the message and puts it back in the draft when the server refuses it", async () => {
    const { fake, controller } = setup();
    await controller.load();
    fake.chat.refuseNext(apiError("model_required", "Choose a model for opencode first.", 409));
    await controller.send("Please help");
    const view = controller.getSnapshot();
    expect(view.chat.turns).toEqual([]);
    expect(view.chat.running).toBe(false);
    expect(view.problem).toBe("Choose a model for opencode first.");
    expect(view.drafts.claude).toBe("Please help");
  });

  it("keeps a draft for each provider", async () => {
    const { controller } = setup();
    await controller.load();
    controller.setDraft("claude", "for claude");
    controller.setDraft("opencode", "for opencode");
    expect(controller.getSnapshot().drafts).toEqual({ claude: "for claude", opencode: "for opencode" });
  });
});

describe("ChatController connection", () => {
  it("resubscribes after a dropped connection from the last event it saw, and shows the text once", async () => {
    const { fake, controller, waits } = setup();
    await controller.load();
    const sending = controller.send("Write");
    await flush();
    fake.chat.begin("t1");
    fake.chat.emit({ type: "text_delta", messageId: "m", text: "One " });
    fake.chat.drop();
    // Sent while the page has no connection: the server keeps it for whoever follows next.
    fake.chat.emit({ type: "text_delta", messageId: "m", text: "two " });
    await flush();
    expect(fake.chat.follows).toEqual([2]);
    expect(waits.length).toBeGreaterThan(0);
    expect(texts(controller)).toEqual(["One two "]);
    expect(controller.getSnapshot().reconnecting).toBe(false);
    fake.chat.drop();
    await flush();
    expect(fake.chat.follows).toEqual([2, 3]);
    expect(texts(controller)).toEqual(["One two "]);
    fake.chat.emit({ type: "text_delta", messageId: "m", text: "three" });
    fake.chat.emit({ type: "done", reason: "completed" });
    fake.chat.end();
    await sending;
    expect(texts(controller)).toEqual(["One two three"]);
    expect(lastTurn(controller).status).toBe("completed");
  });

  it("gives up after repeated failures and ends the turn with a readable error", async () => {
    const { fake, controller } = setup();
    await controller.load();
    const sending = controller.send("Write");
    await flush();
    fake.chat.begin("t1");
    fake.failAll(apiError("network", "down", 0));
    fake.chat.drop();
    await sending;
    expect(lastTurn(controller).status).toBe("failed");
    expect(lastTurn(controller).items.at(-1)).toMatchObject({ kind: "error", code: "connection_lost" });
    expect(controller.getSnapshot().chat.running).toBe(false);
  });
});

describe("ChatController stop", () => {
  it("asks the server to stop the running turn and lets the stream end it as cancelled", async () => {
    const { fake, controller } = setup();
    await controller.load();
    const sending = controller.send("Long task");
    await flush();
    fake.chat.begin("t1");
    await controller.stop();
    expect(fake.chat.stopped).toEqual(["t1"]);
    fake.chat.emit({ type: "done", reason: "cancelled" });
    fake.chat.end();
    await sending;
    expect(lastTurn(controller).status).toBe("cancelled");
  });

  it("stops as soon as the turn is named when Stop was pressed before that", async () => {
    const { fake, controller } = setup();
    await controller.load();
    void controller.send("Long task");
    await flush();
    await controller.stop();
    expect(fake.chat.stopped).toEqual([]);
    fake.chat.begin("t3");
    await flush();
    expect(fake.chat.stopped).toEqual(["t3"]);
  });
});

describe("ChatController provider changes", () => {
  it("switches provider, loads that provider's history and keeps each provider's draft", async () => {
    const { fake, controller } = setup({
      providers: {
        selected: "claude",
        providers: [
          { id: "claude", installed: true, requiresModel: false, model: null },
          { id: "opencode", installed: true, requiresModel: true, model: "a/b" },
        ],
      },
    });
    fake.chat.history.opencode = history({ provider: "opencode", turns: [{ ...record("o1", "In opencode", "From opencode"), provider: "opencode" }] });
    await controller.load();
    controller.setDraft("claude", "typed for claude");
    await controller.selectProvider("opencode");
    expect(controller.getSnapshot().providers?.selected).toBe("opencode");
    expect(controller.getSnapshot().chat.turns.map((turn) => turn.prompt)).toEqual(["In opencode"]);
    expect(controller.getSnapshot().drafts.claude).toBe("typed for claude");
    await controller.selectProvider("claude");
    expect(controller.getSnapshot().chat.turns).toEqual([]);
  });

  it("does not switch provider while a turn runs", async () => {
    const { fake, controller } = setup();
    await controller.load();
    void controller.send("busy");
    await flush();
    await controller.selectProvider("opencode");
    expect(fake.calls).not.toContain("selectProvider opencode");
    fake.chat.begin();
    fake.chat.emit({ type: "done", reason: "completed" });
    fake.chat.end();
    await flush();
  });

  it("saves a model and answers null, or the server's reason when it refuses", async () => {
    const { fake, controller } = setup();
    await controller.load();
    expect(await controller.setModel("claude", "sonnet")).toBeNull();
    expect(controller.getSnapshot().providers?.providers.find((provider) => provider.id === "claude")?.model).toBe("sonnet");
    fake.failNext(apiError("invalid_model", "A model cannot start with a dash.", 400));
    expect(await controller.setModel("claude", "--x")).toBe("A model cannot start with a dash.");
  });

  it("re-checks the providers and shows that it is checking meanwhile", async () => {
    const { fake, controller } = setup();
    await controller.load();
    const checking = controller.recheck();
    expect(controller.getSnapshot().checking).toBe(true);
    await checking;
    expect(controller.getSnapshot().checking).toBe(false);
    expect(fake.chat.rechecks).toBe(1);
  });

  it("starts a new conversation: the server forgets it, the visible one is replaced by a note", async () => {
    const { fake, controller } = setup();
    fake.chat.history.claude = history({ turns: [record("t1", "Hello", "Hi")], undoableTurnId: "t1" });
    await controller.load();
    await controller.newChat();
    const view = controller.getSnapshot();
    expect(fake.calls).toContain("resetChat claude");
    expect(view.chat.turns).toEqual([]);
    expect(view.chat.timeline.map((entry) => entry.kind)).toEqual(["note"]);
    expect(view.chat.undoableTurnId).toBeNull();
  });

  it("keeps the conversation and says why when the server refuses a new chat", async () => {
    const { fake, controller } = setup();
    fake.chat.history.claude = history({ turns: [record("t1", "Hello", "Hi")] });
    await controller.load();
    fake.failNext(apiError("busy", "A turn is running. Start a new chat when it has finished.", 409));
    await controller.newChat();
    expect(controller.getSnapshot().chat.turns).toHaveLength(1);
    expect(controller.getSnapshot().problem).toMatch(/turn is running/);
  });
});

describe("ChatController undo", () => {
  const conflict = new ApiError({ status: 409, code: "undo_conflict", message: "These files changed.", conflicts: [{ path: "a.tex", expected: "sha256:1", actual: "sha256:2" }] });

  async function afterTurn(fake: ReturnType<typeof createFakeApi>, controller: ChatController) {
    await controller.load();
    const sending = controller.send("Edit it");
    await flush();
    fake.chat.begin("t1");
    fake.chat.emit({ type: "done", reason: "completed" });
    fake.chat.emit({ type: "files_changed", turnId: "t1", files: [{ path: "a.tex" as never, change: "modified", beforeHash: null, afterHash: null, undoable: true, mixed: false }] });
    fake.chat.history.claude = history({ undoableTurnId: "t1" });
    fake.chat.end();
    await sending;
  }

  it("undoes the turn, says which files came back, and moves the undoable turn", async () => {
    const { fake, controller } = setup();
    await afterTurn(fake, controller);
    expect(controller.getSnapshot().chat.undoableTurnId).toBe("t1");
    fake.chat.nextUndo = { files: ["a.tex"], skipped: [] };
    fake.chat.history.claude = history({ undoableTurnId: null });
    await controller.undo("t1");
    expect(fake.chat.undos).toEqual([{ turnId: "t1", mode: "strict" }]);
    const view = controller.getSnapshot();
    expect(view.chat.undoableTurnId).toBeNull();
    expect(view.undone).toEqual(["t1"]);
    const note = view.chat.timeline.at(-1)!;
    expect(note).toMatchObject({ kind: "note", level: "info" });
    expect((note as { message: string }).message).toContain("a.tex");
  });

  it("opens the three-way choice when files changed after the turn, and does not undo anything yet", async () => {
    const { fake, controller } = setup();
    await afterTurn(fake, controller);
    fake.chat.nextUndo = conflict;
    await controller.undo("t1");
    expect(controller.getSnapshot().undoChoice).toEqual({ turnId: "t1", conflicts: conflict.conflicts });
    expect(controller.getSnapshot().undone).toEqual([]);
    controller.cancelUndo();
    expect(controller.getSnapshot().undoChoice).toBeNull();
    expect(fake.chat.undos).toHaveLength(1);
  });

  it.each([["skip_conflicts" as const], ["force" as const]])("carries out the %s choice", async (mode) => {
    const { fake, controller } = setup();
    await afterTurn(fake, controller);
    fake.chat.nextUndo = conflict;
    await controller.undo("t1");
    fake.chat.nextUndo = { files: ["b.tex"], skipped: mode === "skip_conflicts" ? ["a.tex"] : [] };
    await controller.undo("t1", mode);
    expect(fake.chat.undos.at(-1)).toEqual({ turnId: "t1", mode });
    expect(controller.getSnapshot().undoChoice).toBeNull();
    // Files left alone make the undo partial, even when the user asked to keep their own edits.
    expect(controller.getSnapshot().undone).toEqual(mode === "force" ? ["t1"] : []);
    const note = controller.getSnapshot().chat.timeline.at(-1) as { level: string };
    expect(note.level).toBe(mode === "force" ? "info" : "warning");
  });

  it("reports a partial undo as a warning that names the files left alone, never as a full success", async () => {
    const { fake, controller } = setup();
    await afterTurn(fake, controller);
    fake.chat.nextUndo = { files: [], skipped: ["notes.tex"] };
    await controller.undo("t1");
    const note = controller.getSnapshot().chat.timeline.at(-1) as { kind: string; level: string; message: string };
    expect(note.level).toBe("warning");
    expect(note.message).toContain("notes.tex");
    expect(note.message).toMatch(/not restored/i);
    expect(note.message).toMatch(/link/i);
    expect(controller.getSnapshot().undone).toEqual([]);
  });

  it("keeps the turn undoable-looking and shows the server's message when the undo is refused", async () => {
    const { fake, controller } = setup();
    await afterTurn(fake, controller);
    fake.chat.nextUndo = new ApiError({ status: 409, code: "undo_failed", message: "The snapshot folder cannot be used." });
    await controller.undo("t1");
    expect(controller.getSnapshot().problem).toBe("The snapshot folder cannot be used.");
    expect(controller.getSnapshot().undone).toEqual([]);
  });

  it("replaces the agent definition on request and says so, or shows the refusal", async () => {
    const { fake, controller } = setup();
    await controller.load();
    await controller.replaceDefinition();
    expect(fake.chat.replaced).toEqual(["claude"]);
    expect((controller.getSnapshot().chat.timeline.at(-1) as { message: string }).message).toMatch(/replaced/i);
    fake.failNext(apiError("busy", "A turn is running.", 409));
    await controller.replaceDefinition();
    expect(controller.getSnapshot().problem).toBe("A turn is running.");
  });

  describe("sign-in mode and keys", () => {
    const keyed = (): Parameters<typeof createFakeApi>[0] => ({
      providers: {
        selected: "claude",
        providers: [{ id: "claude", installed: true, requiresModel: false, model: null, auth: { mode: "account", modes: ["account", "api"], keys: [{ slot: "claude", set: false }], slot: "claude", apiReady: false, login: "unknown", loginHint: "Run `claude`." } }],
      },
    });

    it("answers null and shows the new mode when the server accepts the switch, else the readable reason and the old mode", async () => {
      const { fake, controller } = setup(keyed());
      await controller.load();
      expect(await controller.setAuthMode("claude", "api")).toBe("No API key is stored for claude. Add one first, then switch.");
      expect(controller.getSnapshot().providers?.providers[0]?.auth?.mode).toBe("account");
      await controller.saveKey("claude", "sk-abcdef1234567890");
      expect(await controller.setAuthMode("claude", "api")).toBeNull();
      expect(controller.getSnapshot().providers?.providers[0]?.auth).toMatchObject({ mode: "api", apiReady: true });
      expect(fake.calls).toContain("setAuthMode claude api");
    });

    it("reads the provider list again after a key is saved or deleted, so the form shows the new status", async () => {
      const { fake, controller } = setup(keyed());
      await controller.load();
      expect(await controller.saveKey("claude", "sk-abcdef1234567890")).toBeNull();
      expect(controller.getSnapshot().providers?.providers[0]?.auth?.keys).toEqual([{ slot: "claude", set: true, last4: "7890" }]);
      expect(await controller.deleteKey("claude")).toBeNull();
      expect(controller.getSnapshot().providers?.providers[0]?.auth?.keys).toEqual([{ slot: "claude", set: false }]);
      expect(fake.calls.filter((call) => call === "listProviders").length).toBeGreaterThanOrEqual(3);
    });

    it("answers the server's reason when a key cannot be saved or deleted, and keeps the old status", async () => {
      const { fake, controller } = setup(keyed());
      await controller.load();
      fake.failNext(apiError("invalid_key", "A key can use only printable ASCII characters, without spaces.", 400));
      expect(await controller.saveKey("claude", "bad key")).toBe("A key can use only printable ASCII characters, without spaces.");
      fake.failNext(apiError("credential_store_unusable", "The Caztor key file can be reached by other users.", 409));
      expect(await controller.deleteKey("claude")).toBe("The Caztor key file can be reached by other users.");
      expect(controller.getSnapshot().providers?.providers[0]?.auth?.keys).toEqual([{ slot: "claude", set: false }]);
    });
  });
});
