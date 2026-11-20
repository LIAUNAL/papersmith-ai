import type { ChatTurnRecord, ProviderId, TurnEvent } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { userChatFolder } from "../src/user-home.ts";
import { createChatHistory, MAX_HISTORY_BYTES, MAX_HISTORY_TURNS, MAX_STORED_LINE_BYTES, MAX_TURN_EVENTS } from "../src/chat-history.ts";
import { cleanupSandboxes, implementations } from "./support/fs-sandbox.ts";

const encode = (text: string) => new TextEncoder().encode(text);
const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);

cleanupSandboxes();

const record = (id: string, extra: Partial<ChatTurnRecord> = {}): ChatTurnRecord => ({
  turnId: id,
  provider: "claude",
  prompt: `prompt ${id}`,
  startedAt: 1000,
  events: [
    { type: "text", messageId: "m", text: `answer ${id}` },
    { type: "done", reason: "completed" },
  ],
  ...extra,
});

describe.each(implementations)("chat history: %s", (_name, create) => {
  async function setup() {
    const box = create();
    const project = `${box.root}/project`;
    await box.fs.mkdir(project, { recursive: true });
    const history = createChatHistory({ fs: box.fs, root: project });
    const file = (provider: ProviderId) => `${project}/.caztor/chat/${provider}.jsonl`;
    return { ...box, project, history, file };
  }

  describe("size bounds", () => {
    const update = (index: number): TurnEvent => ({ type: "tool_update", toolId: "t", title: `step ${index}` });

    it("keeps the assistant's reply when the turn names a huge list of unprotected files", async () => {
      const { history, file, fs } = await setup();
      const unprotected = Array.from({ length: 100_000 }, (_, index) => `.micromamba/envs/papersmith/lib/python3.12/site-packages/pkg/module_${index}.py`);
      const events = [
        { type: "turn_started", turnId: "env", provider: "claude", snapshotPartial: true, unprotected },
        { type: "text", messageId: "m1", text: "The paper introduces exact colourings." },
        { type: "done", reason: "completed" },
      ] as TurnEvent[];

      await history.append(record("env", { events }));

      expect(decode(await fs.readFile(file("claude"))).length).toBeLessThanOrEqual(MAX_STORED_LINE_BYTES + 1);
      const [turn] = await history.load("claude");
      expect(turn?.events.find((event) => event.type === "text")).toEqual({ type: "text", messageId: "m1", text: "The paper introduces exact colourings." });
      const started = turn?.events[0] as Extract<TurnEvent, { type: "turn_started" }>;
      expect(started.unprotected).toHaveLength(20);
      expect(started.unprotectedCount).toBe(100_000);
    });

    it("keeps one turn with 300,000 tool updates within the line limit and keeps the end of the turn", async () => {
      const { history, file, fs } = await setup();
      const events: TurnEvent[] = [{ type: "turn_started", turnId: "big", provider: "claude", snapshotPartial: false, unprotected: [] }];
      for (let index = 0; index < 300_000; index += 1) events.push(update(index));
      events.push({ type: "done", reason: "completed" });

      await history.append(record("big", { events }));

      const stored = decode(await fs.readFile(file("claude")));
      expect(stored.length).toBeLessThanOrEqual(MAX_STORED_LINE_BYTES + 1);
      const [turn] = await history.load("claude");
      expect(turn?.events.length).toBeLessThanOrEqual(MAX_TURN_EVENTS);
      expect(turn?.events[0]?.type).toBe("turn_started");
      expect(turn?.events.at(-1)?.type).toBe("done");
    });

    it("shortens many long answers so one stored line stays small, and still keeps every event type that matters", async () => {
      const { history, file, fs } = await setup();
      const events: TurnEvent[] = [];
      for (let index = 0; index < 100; index += 1) events.push({ type: "text", messageId: `m${index}`, text: "w".repeat(50_000) });
      events.push({ type: "error", code: "provider_error", message: "stopped" });
      events.push({ type: "done", reason: "failed" });

      await history.append(record("wide", { events }));

      expect(decode(await fs.readFile(file("claude"))).length).toBeLessThanOrEqual(MAX_STORED_LINE_BYTES + 1);
      const [turn] = await history.load("claude");
      expect(turn?.events.map((event) => event.type).slice(-2)).toEqual(["error", "done"]);
    });

    it("leaves a small turn exactly as it was", async () => {
      const { history } = await setup();
      await history.append(record("small"));
      expect(await history.load("claude")).toEqual([record("small")]);
    });

    it("skips an oversized line already on disk and returns no more than the size limit", async () => {
      const { history, file, fs } = await setup();
      await fs.mkdir(`${file("claude").slice(0, file("claude").lastIndexOf("/"))}`, { recursive: true });
      const huge = JSON.stringify(record("huge", { prompt: "p".repeat(3 * 1024 * 1024) }));
      const lines = [huge, ...Array.from({ length: 30 }, (_unused, index) => JSON.stringify(record(`n${index}`, { prompt: "q".repeat(60_000) })))];
      await fs.writeFile(file("claude"), encode(`${lines.join("\n")}\n`));

      const turns = await history.load("claude");

      expect(turns.map((turn) => turn.turnId)).not.toContain("huge");
      expect(JSON.stringify(turns).length).toBeLessThanOrEqual(MAX_HISTORY_BYTES);
      expect(turns.at(-1)?.turnId).toBe("n29");
      expect(turns.length).toBeGreaterThan(5);
    });
  });

  describe("links", () => {
    const SECRET = '{"turnId":"x","provider":"claude","prompt":"SECRET OUTSIDE","startedAt":1,"events":[]}\n';

    it.each([
      ["outside the project", (t: Awaited<ReturnType<typeof setup>>) => `${t.root}/outside`],
      ["inside the project", (t: Awaited<ReturnType<typeof setup>>) => `${t.project}/notes`],
    ])("never writes through a chat folder that is a link %s", async (_where, target) => {
      const t = await setup();
      const folder = target(t);
      await t.fs.mkdir(folder, { recursive: true });
      await t.fs.mkdir(`${t.project}/.caztor`, { recursive: true });
      t.symlink(folder, `${t.project}/.caztor/chat`);

      await expect(t.history.append(record("t1"))).rejects.toThrow(/not a plain folder/);

      expect(await t.fs.readdir(folder)).toEqual([]);
      expect(await t.history.load("claude")).toEqual([]);
    });

    it("never writes through a .caztor folder that is a link", async () => {
      const t = await setup();
      await t.fs.mkdir(`${t.root}/outside`, { recursive: true });
      t.symlink(`${t.root}/outside`, `${t.project}/.caztor`);

      const failure = await t.history.append(record("t1")).then(() => new Error("it did not fail"), (error: Error) => error);
      expect(failure.message).toBe(".caztor is a link, not a plain folder");

      expect(await t.fs.readdir(`${t.root}/outside`)).toEqual([]);
    });

    it("names the refused place relative to the project, never by a path on this computer", async () => {
      const t = await setup();
      await t.fs.mkdir(`${t.root}/outside`, { recursive: true });
      await t.fs.mkdir(`${t.project}/.caztor`, { recursive: true });
      t.symlink(`${t.root}/outside`, `${t.project}/.caztor/chat`);
      const folder = await t.history.append(record("t1")).then(() => new Error("it did not fail"), (error: Error) => error);
      expect(folder.message).toBe(".caztor/chat is a link, not a plain folder");
      await t.fs.rm(`${t.project}/.caztor/chat`);
      await t.fs.mkdir(`${t.project}/.caztor/chat`, { recursive: true });
      await t.fs.writeFile(`${t.root}/secret.jsonl`, encode(SECRET));
      t.symlink(`${t.root}/secret.jsonl`, t.file("claude"));
      const file = await t.history.append(record("t1")).then(() => new Error("it did not fail"), (error: Error) => error);
      expect(file.message).toBe(".caztor/chat/claude.jsonl is a link");
      for (const failure of [folder, file]) expect(failure.message).not.toContain(t.root);
    });

    it.each([
      ["outside the project", (t: Awaited<ReturnType<typeof setup>>) => `${t.root}/secret.jsonl`],
      ["inside the project", (t: Awaited<ReturnType<typeof setup>>) => `${t.project}/notes.jsonl`],
    ])("neither reads nor replaces a history file that is a link %s", async (_where, target) => {
      const t = await setup();
      const file = target(t);
      await t.fs.writeFile(file, encode(SECRET));
      await t.fs.mkdir(`${t.project}/.caztor/chat`, { recursive: true });
      t.symlink(file, t.file("claude"));

      expect(await t.history.load("claude")).toEqual([]);
      await expect(t.history.append(record("t1"))).rejects.toThrow(/is a link/);

      expect(decode(await t.fs.readFile(file))).toBe(SECRET);
      expect((await t.fs.lstat(t.file("claude"))).isSymbolicLink()).toBe(true);
    });
  });

  it("has no turns before anything was stored", async () => {
    const { history } = await setup();
    expect(await history.load("claude")).toEqual([]);
  });

  it("stores turns per provider as JSON lines, oldest first, and loads them back", async () => {
    const { history, file, fs } = await setup();
    await history.append(record("t1"));
    await history.append(record("t2"));
    await history.append(record("o1", { provider: "opencode" }));
    expect((await history.load("claude")).map((turn) => turn.turnId)).toEqual(["t1", "t2"]);
    expect(await history.load("claude")).toEqual([record("t1"), record("t2")]);
    expect((await history.load("opencode")).map((turn) => turn.turnId)).toEqual(["o1"]);
    const lines = decode(await fs.readFile(file("claude"))).trimEnd().split("\n");
    expect(lines).toHaveLength(2);
    expect(JSON.parse(lines[0]!)).toMatchObject({ turnId: "t1", prompt: "prompt t1" });
  });

  it("forgets one provider's conversation and leaves the others", async () => {
    const { history } = await setup();
    await history.append(record("t1"));
    await history.append(record("o1", { provider: "opencode" }));
    await history.clear("claude");
    expect(await history.load("claude")).toEqual([]);
    expect(await history.load("opencode")).toHaveLength(1);
    await history.clear("claude");
  });

  it("keeps the newest turns when there are more than the limit", async () => {
    const { history } = await setup();
    for (let i = 0; i < MAX_HISTORY_TURNS + 3; i += 1) await history.append(record(`t${i}`));
    const turns = await history.load("claude");
    expect(turns).toHaveLength(MAX_HISTORY_TURNS);
    expect(turns[0]?.turnId).toBe("t3");
    expect(turns.at(-1)?.turnId).toBe(`t${MAX_HISTORY_TURNS + 2}`);
  });

  it("keeps the file within its size limit by dropping the oldest turns", async () => {
    const { history, file, fs } = await setup();
    const big = "x".repeat(100_000);
    for (let i = 0; i < 40; i += 1) await history.append(record(`t${i}`, { prompt: big }));
    const bytes = (await fs.readFile(file("claude"))).length;
    expect(bytes).toBeLessThanOrEqual(MAX_HISTORY_BYTES);
    const turns = await history.load("claude");
    expect(turns.length).toBeGreaterThan(5);
    expect(turns.length).toBeLessThan(40);
    expect(turns.at(-1)?.turnId).toBe("t39");
  });

  it("shortens one enormous answer instead of refusing to store the turn", async () => {
    const { history } = await setup();
    const events: TurnEvent[] = [{ type: "text", messageId: "m", text: "y".repeat(MAX_HISTORY_BYTES) }, { type: "done", reason: "completed" }];
    await history.append(record("huge", { events }));
    const [stored] = await history.load("claude");
    expect(stored?.turnId).toBe("huge");
    const text = stored?.events.find((event) => event.type === "text");
    expect(text?.type === "text" && text.text.length).toBeLessThan(60_000);
    expect(text?.type === "text" && text.text).toContain("shortened");
  });

  it("skips damaged lines and lines that are not turns, and keeps the rest", async () => {
    const { history, file, fs, project } = await setup();
    await fs.mkdir(`${project}/.caztor/chat`, { recursive: true });
    const good = JSON.stringify(record("good"));
    const wrongProvider = JSON.stringify(record("other", { provider: "opencode" }));
    const noEvents = JSON.stringify({ turnId: "x", provider: "claude", prompt: "p", startedAt: 1 });
    const unknownEvent = JSON.stringify(record("odd", { events: [{ type: "bogus" } as unknown as TurnEvent, { type: "done", reason: "failed" }] }));
    await fs.writeFile(file("claude"), encode(["{not json", good, wrongProvider, noEvents, "", unknownEvent].join("\n") + "\n"));
    const turns = await history.load("claude");
    expect(turns.map((turn) => turn.turnId)).toEqual(["good", "odd"]);
    expect(turns[1]?.events).toEqual([{ type: "done", reason: "failed" }]);
  });

  it("serializes appends that run at the same time", async () => {
    const { history } = await setup();
    await Promise.all(Array.from({ length: 12 }, (_, i) => history.append(record(`t${i}`))));
    expect(await history.load("claude")).toHaveLength(12);
  });

  describe("each person's conversation", () => {
    it("keeps a collaborator's turns in their private folder, outside the project, and leaves the host's file where it was", async () => {
      const t = await setup();
      const configHome = `${t.root}/config`;
      const alice = createChatHistory({ fs: t.fs, root: t.project, userId: "alice-1", configHome });
      await t.history.append(record("h1"));
      await alice.append(record("a1"));
      expect((await t.history.load("claude")).map((turn) => turn.turnId)).toEqual(["h1"]);
      expect((await alice.load("claude")).map((turn) => turn.turnId)).toEqual(["a1"]);
      expect(decode(await t.fs.readFile(t.file("claude")))).toContain('"turnId":"h1"');
      const folder = userChatFolder(configHome, "alice-1", t.project);
      expect(folder).toMatch(new RegExp(`^${configHome}/caztor/users/alice-1/chat/[0-9a-f]{32}$`));
      expect(decode(await t.fs.readFile(`${folder}/claude.jsonl`))).toContain('"turnId":"a1"');
      expect(await t.fs.readdir(`${t.project}/.caztor/chat`).then((entries) => entries.map((entry) => entry.name))).toEqual(["claude.jsonl"]);
      // Another project of the same person gets its own conversation.
      expect(userChatFolder(configHome, "alice-1", `${t.project}-2`)).not.toBe(folder);
      await alice.clear("claude");
      expect(await alice.load("claude")).toEqual([]);
      expect(await t.history.load("claude")).toHaveLength(1);
    });

    it("refuses a hostile user id, and a collaborator without a configuration folder", async () => {
      const t = await setup();
      for (const userId of ["..", "a/b", "host", ""]) expect(() => createChatHistory({ fs: t.fs, root: t.project, userId, configHome: `${t.root}/config` })).toThrow(/user id/i);
      expect(() => createChatHistory({ fs: t.fs, root: t.project, userId: "alice-1" })).toThrow(/configuration folder/i);
    });

    it("refuses a person's chat folder that is a link", async () => {
      const t = await setup();
      const configHome = `${t.root}/config`;
      await t.fs.mkdir(`${configHome}/caztor/users/alice-1`, { recursive: true });
      await t.fs.mkdir(`${t.root}/elsewhere`);
      t.symlink(`${t.root}/elsewhere`, `${configHome}/caztor/users/alice-1/chat`);
      const alice = createChatHistory({ fs: t.fs, root: t.project, userId: "alice-1", configHome });
      await expect(alice.append(record("a1"))).rejects.toThrow("Your chat folder is a link");
      expect(await t.fs.readdir(`${t.root}/elsewhere`)).toEqual([]);
    });

    it("writes a collaborator's folders closed to everyone else", async () => {
      const t = await setup();
      const configHome = `${t.root}/config`;
      const alice = createChatHistory({ fs: t.fs, root: t.project, userId: "alice-1", configHome });
      await alice.append(record("a1"));
      const folder = userChatFolder(configHome, "alice-1", t.project);
      for (const path of [`${configHome}/caztor/users/alice-1/chat`, folder]) expect((await t.fs.stat(path)).mode & 0o077).toBe(0);
    });
  });
});
