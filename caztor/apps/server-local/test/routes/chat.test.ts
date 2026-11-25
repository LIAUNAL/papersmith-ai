import { hashBytes } from "@caztor/core";
import { existsSync, mkdirSync, readFileSync, renameSync, symlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { chatHarness, cleanupChatProjects, parseFrames, type ChatHarness, type Frame } from "./chat-support.ts";

cleanupChatProjects();

const types = (frames: Frame[]) => frames.map((frame) => frame.event);
const read = (h: ChatHarness, path: string) => readFileSync(join(h.root, path), "utf8");

/** Starts a long turn and returns when the agent is running. */
async function startHeld(h: ChatHarness, prompt = "Long task") {
  const before = h.runners.claude.requests.length;
  const response = await h.call("POST", "/api/chat/turns", { body: { provider: "claude", prompt } });
  expect(response.status).toBe(200);
  const turnId = response.headers.get("x-caztor-turn-id")!;
  await vi.waitFor(() => expect(h.runners.claude.requests.length).toBeGreaterThan(before));
  return { response, turnId };
}

const REQUESTS: Array<[string, string, unknown]> = [
  ["POST", "/api/chat/turns", { provider: "claude", prompt: "hi" }],
  ["GET", "/api/chat/turns/current", undefined],
  ["GET", "/api/chat/turns/t1/events", undefined],
  ["POST", "/api/chat/turns/t1/stop", {}],
  ["POST", "/api/chat/turns/t1/undo", { mode: "strict" }],
  ["POST", "/api/chat/definition/replace", { provider: "claude" }],
  ["GET", "/api/chat/history?provider=claude", undefined],
  ["POST", "/api/chat/sessions/reset", { provider: "claude" }],
];

describe("chat routes are behind the security gate", () => {
  it.each(REQUESTS)("%s %s is rejected without the launch token and starts nothing", async (method, path, body) => {
    const h = chatHarness();
    const response = await h.call(method, path, { ...(body === undefined ? {} : { body }), headers: { "x-caztor-token": "" } });
    expect(response.status).toBe(401);
    expect(h.runners.claude.requests).toEqual([]);
    expect(existsSync(join(h.root, ".claude"))).toBe(false);
    expect(existsSync(join(h.root, ".caztor", "snapshots"))).toBe(false);
  });

  it("is rejected for a foreign Host and for a send without JSON content type", async () => {
    const h = chatHarness();
    expect((await h.call("POST", "/api/chat/turns", { body: { provider: "claude", prompt: "x" }, headers: { host: "evil.example" } })).status).toBe(403);
    expect((await h.call("POST", "/api/chat/turns", { body: "x", headers: { "content-type": "text/plain" } })).status).toBe(415);
    expect(h.runners.claude.requests).toEqual([]);
  });
});

describe("POST /api/chat/turns", () => {
  it("streams the normalized events of the turn as Server-Sent Events, with the changed files last", async () => {
    const h = chatHarness();
    writeFileSync(join(h.root, "main.tex"), "old text");
    h.runners.claude.script = async function* ({ write }) {
      yield { type: "session", sessionId: "s1" };
      yield { type: "text_delta", messageId: "m1", text: "Chang" };
      yield { type: "text_delta", messageId: "m1", text: "ing it." };
      yield { type: "tool_start", toolId: "t1", name: "Edit", kind: "edit", path: "main.tex" };
      write("main.tex", "new text");
      yield { type: "tool_end", toolId: "t1", status: "done" };
      yield { type: "text", messageId: "m2", text: "Done." };
      yield { type: "done", reason: "completed", usage: { outputTokens: 5 } };
    };
    const { response, frames } = await h.sendMessage("Rewrite main");

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(types(frames)).toEqual([
      "turn_started", "session", "text_delta", "text_delta", "tool_start", "tool_end", "text", "done", "files_changed",
    ]);
    expect(frames.map((frame) => frame.id)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
    expect(frames[2]?.data).toMatchObject({ type: "text_delta", messageId: "m1", text: "Chang" });
    expect(frames[7]?.data).toEqual({ type: "done", reason: "completed", usage: { outputTokens: 5 } });
    const summary = frames[8]!.data as { files: Array<{ path: string; change: string; undoable: boolean; mixed: boolean }> };
    expect(summary.files).toMatchObject([{ path: "main.tex", change: "modified", undoable: true, mixed: false }]);
    expect(read(h, "main.tex")).toBe("new text");
  });

  it("provisions the definition and takes the snapshot before the agent starts, and passes the prompt as plain data", async () => {
    const h = chatHarness();
    writeFileSync(join(h.root, "main.tex"), "text");
    let seen: { definition: boolean; snapshots: string[] } | null = null;
    h.runners.claude.script = async function* ({ root }) {
      seen = {
        definition: existsSync(join(root, ".claude", "agents", "caztor.md")),
        snapshots: existsSync(join(root, ".caztor", "snapshots", "turns")) ? (await import("node:fs")).readdirSync(join(root, ".caztor", "snapshots", "turns")) : [],
      };
      yield { type: "done", reason: "completed" };
    };
    const { response } = await h.sendMessage("; rm -rf ~ --model x");
    const turnId = response.headers.get("x-caztor-turn-id")!;
    expect(seen).toEqual({ definition: true, snapshots: [`${turnId}.json`] });
    expect(h.runners.claude.requests[0]).toMatchObject({ prompt: "; rm -rf ~ --model x", sessionId: null, model: null });
    expect(h.runners.claude.requests[0]!.agent.name).toBe("caztor");
  });

  it("uses the selected provider and its saved model when the request names none", async () => {
    const h = chatHarness();
    await h.call("PUT", "/api/providers/selected", { body: { provider: "opencode" } });
    await h.call("PUT", "/api/providers/opencode/model", { body: { model: "free/model" } });
    const response = await h.call("POST", "/api/chat/turns", { body: { prompt: "hi" } });
    expect(response.status).toBe(200);
    await response.text();
    expect(h.runners.opencode.requests[0]).toMatchObject({ prompt: "hi", model: "free/model" });
    expect(h.runners.claude.requests).toEqual([]);
  });

  it.each([
    ["no prompt", { provider: "claude" }, 400, "invalid_prompt"],
    ["a blank prompt", { provider: "claude", prompt: "  " }, 400, "invalid_prompt"],
    ["a prompt that is not text", { provider: "claude", prompt: 5 }, 400, "invalid_prompt"],
    ["an unknown provider", { provider: "gemini", prompt: "hi" }, 400, "invalid_provider"],
    ["no provider and none selected", { prompt: "hi" }, 400, "no_provider"],
    ["a provider without an adapter", { provider: "codex", prompt: "hi" }, 409, "unknown_provider"],
  ])("refuses %s before anything happens", async (_name, body, status, code) => {
    const h = chatHarness();
    const response = await h.call("POST", "/api/chat/turns", { body });
    expect(response.status).toBe(status);
    const json = (await response.json()) as { error: string; message: string };
    expect(json.error).toBe(code);
    expect(json.message.length).toBeGreaterThan(10);
    expect(existsSync(join(h.root, ".claude"))).toBe(false);
    expect(existsSync(join(h.root, ".caztor", "snapshots"))).toBe(false);
  });

  it("refuses a provider that is not installed, with the reason", async () => {
    const h = chatHarness();
    h.runners.claude.status = { provider: "claude", installed: false, unavailableReason: "claude is not installed", requiresModel: false };
    const response = await h.call("POST", "/api/chat/turns", { body: { provider: "claude", prompt: "hi" } });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "not_installed", message: "claude is not installed" });
    expect(h.runners.claude.requests).toEqual([]);
  });

  it("refuses opencode without a model and asks the user to set one", async () => {
    const h = chatHarness();
    const response = await h.call("POST", "/api/chat/turns", { body: { provider: "opencode", prompt: "hi" } });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "model_required", message: expect.stringContaining("Choose a model") });
    expect(h.runners.opencode.requests).toEqual([]);
    expect(existsSync(join(h.root, ".opencode"))).toBe(false);
  });

  it("refuses a second message while a turn runs (409) and accepts one after it ended", async () => {
    const h = chatHarness();
    h.runners.claude.script = async function* ({ gate }) {
      await gate;
      yield { type: "done", reason: "completed" };
    };
    const { response } = await startHeld(h);
    const second = await h.call("POST", "/api/chat/turns", { body: { provider: "claude", prompt: "again" } });
    expect(second.status).toBe(409);
    expect(await second.json()).toMatchObject({ error: "busy", message: expect.stringContaining("already running") });
    expect(h.runners.claude.requests).toHaveLength(1);
    h.runners.claude.release();
    await response.text();
    h.runners.claude.script = async function* () {
      yield { type: "done", reason: "completed" };
    };
    const third = await h.sendMessage("now");
    expect(third.response.status).toBe(200);
  });

  it("ends the turn failed with a readable snapshot_failed error, and never starts the agent, when the snapshot cannot be taken", async () => {
    const h = chatHarness();
    mkdirSync(join(h.root, ".caztor"), { recursive: true });
    writeFileSync(join(h.root, ".caztor", "snapshots"), "a file where the snapshot folder should be");
    const { frames } = await h.sendMessage("Rewrite");
    expect(types(frames)).toEqual(["error", "done"]);
    expect(frames[0]?.data).toMatchObject({ type: "error", code: "snapshot_failed", message: expect.stringContaining("snapshot") });
    expect(frames[1]?.data).toEqual({ type: "done", reason: "failed" });
    expect(h.runners.claude.requests).toEqual([]);
  });

  it("shows provider errors and an agent that ends without finishing as failed turns", async () => {
    const h = chatHarness();
    h.runners.claude.script = async function* () {
      yield { type: "error", code: "auth", message: "Sign in to Claude first." };
      yield { type: "done", reason: "failed" };
    };
    const failed = await h.sendMessage("a");
    expect(failed.frames.map((frame) => frame.data["type"])).toEqual(["turn_started", "error", "done", "files_changed"]);
    expect(failed.frames[1]?.data).toMatchObject({ code: "auth", message: "Sign in to Claude first." });

    h.runners.claude.script = async function* () {
      yield { type: "text_delta", messageId: "m", text: "Half an answ" };
    };
    const abrupt = await h.sendMessage("b");
    const tail = abrupt.frames.slice(-3).map((frame) => frame.data);
    expect(tail[0]).toMatchObject({ type: "error", code: "provider_error", message: expect.stringContaining("without finishing") });
    expect(tail[1]).toEqual({ type: "done", reason: "failed" });
    expect(tail[2]).toMatchObject({ type: "files_changed" });
  });

  it("does not list a file only the user changed, and flags a file both changed", async () => {
    const h = chatHarness();
    writeFileSync(join(h.root, "a.tex"), "a0");
    writeFileSync(join(h.root, "c.tex"), "c0");
    h.runners.claude.script = async function* ({ write, gate }) {
      write("a.tex", "a-agent");
      await gate;
      yield { type: "done", reason: "completed" };
    };
    const { response } = await startHeld(h);
    await vi.waitFor(() => expect(read(h, "a.tex")).toBe("a-agent"));
    const saveC = await h.call("PUT", "/api/files/content?path=c.tex", { body: { content: "c-user", baseHash: await hashOf("c0") } });
    expect(saveC.status).toBe(200);
    const saveA = await h.call("PUT", "/api/files/content?path=a.tex", { body: { content: "a-user", baseHash: await hashOf("a-agent") } });
    expect(saveA.status).toBe(200);
    h.runners.claude.release();
    const frames = parseFrames(await response.text());
    const files = (frames.at(-1)!.data as { files: Array<{ path: string; mixed: boolean }> }).files;
    expect(files).toMatchObject([{ path: "a.tex", mixed: true }]);
  });
});

async function hashOf(text: string): Promise<string> {
  const { hashBytes } = await import("@caztor/core");
  return hashBytes(new TextEncoder().encode(text));
}

describe("stopping a turn", () => {
  it("terminates the agent through the abort signal, ends the turn cancelled and still lists and allows undo of what was edited", async () => {
    const h = chatHarness();
    writeFileSync(join(h.root, "a.tex"), "original");
    let aborted = false;
    h.runners.claude.script = async function* ({ write, aborted: wait, signal }) {
      write("a.tex", "half edited");
      yield { type: "text_delta", messageId: "m", text: "Working" };
      await wait();
      aborted = signal.aborted;
      yield { type: "done", reason: "cancelled" };
    };
    const { response, turnId } = await startHeld(h);
    const stop = await h.call("POST", `/api/chat/turns/${turnId}/stop`, { body: {} });
    expect(stop.status).toBe(200);
    expect(await stop.json()).toEqual({ stopped: true });
    const frames = parseFrames(await response.text());
    expect(aborted).toBe(true);
    expect(frames.filter((frame) => frame.event === "done").map((frame) => frame.data)).toEqual([{ type: "done", reason: "cancelled" }]);
    expect(frames.at(-1)?.data).toMatchObject({ type: "files_changed", files: [{ path: "a.tex", undoable: true }] });

    const undo = await h.call("POST", `/api/chat/turns/${turnId}/undo`, { body: { mode: "strict" } });
    expect(undo.status).toBe(200);
    expect(read(h, "a.tex")).toBe("original");
  });

  it("answers 404 for a turn that is not running", async () => {
    const h = chatHarness();
    const unknown = await h.call("POST", "/api/chat/turns/nope/stop", { body: {} });
    expect(unknown.status).toBe(404);
    expect(await unknown.json()).toMatchObject({ error: "no_running_turn" });
    const { response } = await h.sendMessage("x");
    const finished = await h.call("POST", `/api/chat/turns/${response.headers.get("x-caztor-turn-id")}/stop`, { body: {} });
    expect(finished.status).toBe(404);
  });
});

describe("a dropped connection", () => {
  it("does not stop the turn, and a client that comes back gets the events it missed and the rest", async () => {
    const h = chatHarness();
    h.runners.claude.script = async function* ({ write, gate }) {
      yield { type: "text_delta", messageId: "m", text: "One " };
      await gate;
      write("a.tex", "written after the drop");
      yield { type: "text_delta", messageId: "m", text: "two" };
      yield { type: "done", reason: "completed" };
    };
    const first = await h.call("POST", "/api/chat/turns", { body: { provider: "claude", prompt: "go" } });
    const turnId = first.headers.get("x-caztor-turn-id")!;
    const reader = first.body!.getReader();
    const seen: string[] = [];
    const decoder = new TextDecoder();
    while (!seen.join("").includes("event: text_delta")) {
      const chunk = await reader.read();
      seen.push(decoder.decode(chunk.value));
    }
    await reader.cancel();

    const current = await h.call("GET", "/api/chat/turns/current", { headers: { "last-event-id": "1" } });
    expect(current.status).toBe(200);
    expect(current.headers.get("x-caztor-turn-id")).toBe(turnId);
    h.runners.claude.release();
    const frames = parseFrames(await current.text());
    expect(frames.map((frame) => frame.id)).toEqual([2, 3, 4, 5]);
    expect(types(frames)).toEqual(["text_delta", "text_delta", "done", "files_changed"]);
    expect(read(h, "a.tex")).toBe("written after the drop");
  });

  it("serves a finished turn from the start, or after the given event, and knows only the latest turn", async () => {
    const h = chatHarness();
    const { response } = await h.sendMessage("x");
    const turnId = response.headers.get("x-caztor-turn-id")!;
    const all = parseFrames(await (await h.call("GET", `/api/chat/turns/${turnId}/events`)).text());
    expect(types(all)).toEqual(["turn_started", "text", "done", "files_changed"]);
    const rest = parseFrames(await (await h.call("GET", `/api/chat/turns/${turnId}/events?after=3`)).text());
    expect(rest.map((frame) => frame.id)).toEqual([4]);
    expect((await h.call("GET", "/api/chat/turns/other/events")).status).toBe(404);
  });

  it("answers 404 when there is no turn at all", async () => {
    const h = chatHarness();
    const response = await h.call("GET", "/api/chat/turns/current");
    expect(response.status).toBe(404);
    expect(await response.json()).toMatchObject({ error: "no_turn" });
  });
});

describe("POST /api/chat/turns/:id/undo", () => {
  async function editedTurn(h: ChatHarness) {
    writeFileSync(join(h.root, "a.tex"), "a-original");
    writeFileSync(join(h.root, "b.tex"), "b-original");
    h.runners.claude.script = async function* ({ write }) {
      write("a.tex", "a-agent");
      write("b.tex", "b-agent");
      write("new.tex", "created by agent");
      yield { type: "done", reason: "completed" };
    };
    const { response } = await h.sendMessage("Edit");
    return response.headers.get("x-caztor-turn-id")!;
  }

  it("restores every file of the turn, removing created files, and answers with the files", async () => {
    const h = chatHarness();
    const turnId = await editedTurn(h);
    const response = await h.call("POST", `/api/chat/turns/${turnId}/undo`, { body: { mode: "strict" } });
    expect(response.status).toBe(200);
    const json = (await response.json()) as { status: string; files: string[]; skipped: string[] };
    expect(json.status).toBe("restored");
    expect([...json.files].sort()).toEqual(["a.tex", "b.tex", "new.tex"]);
    expect(read(h, "a.tex")).toBe("a-original");
    expect(read(h, "b.tex")).toBe("b-original");
    expect(existsSync(join(h.root, "new.tex"))).toBe(false);
  });

  it("answers 409 with the conflicting files and writes nothing when the user edited a file after the turn", async () => {
    const h = chatHarness();
    const turnId = await editedTurn(h);
    writeFileSync(join(h.root, "a.tex"), "a-user-edit");
    const response = await h.call("POST", `/api/chat/turns/${turnId}/undo`, { body: { mode: "strict" } });
    expect(response.status).toBe(409);
    const json = (await response.json()) as { error: string; message: string; conflicts: Array<{ path: string }> };
    expect(json.error).toBe("undo_conflict");
    expect(json.message).toContain("a.tex");
    expect(json.conflicts.map((conflict) => conflict.path)).toEqual(["a.tex"]);
    expect(read(h, "a.tex")).toBe("a-user-edit");
    expect(read(h, "b.tex")).toBe("b-agent");
  });

  it("with skip_conflicts restores the rest and keeps the user's edit; with force overwrites it", async () => {
    const h = chatHarness();
    const turnId = await editedTurn(h);
    writeFileSync(join(h.root, "a.tex"), "a-user-edit");
    const skip = await h.call("POST", `/api/chat/turns/${turnId}/undo`, { body: { mode: "skip_conflicts" } });
    expect(skip.status).toBe(200);
    expect(await skip.json()).toMatchObject({ status: "restored", skipped: ["a.tex"] });
    expect(read(h, "a.tex")).toBe("a-user-edit");
    expect(read(h, "b.tex")).toBe("b-original");

    const h2 = chatHarness();
    const turn2 = await editedTurn(h2);
    writeFileSync(join(h2.root, "a.tex"), "a-user-edit");
    const force = await h2.call("POST", `/api/chat/turns/${turn2}/undo`, { body: { mode: "force" } });
    expect(force.status).toBe(200);
    expect(read(h2, "a.tex")).toBe("a-original");
  });

  it("refuses an older turn (not the latest) and a second undo, with the reason", async () => {
    const h = chatHarness();
    const first = await editedTurn(h);
    h.runners.claude.script = async function* ({ write }) {
      write("c.tex", "c");
      yield { type: "done", reason: "completed" };
    };
    const second = (await h.sendMessage("more")).response.headers.get("x-caztor-turn-id")!;
    const older = await h.call("POST", `/api/chat/turns/${first}/undo`, { body: { mode: "strict" } });
    expect(older.status).toBe(409);
    expect(await older.json()).toMatchObject({ error: "undo_unavailable", reason: "not_latest" });
    expect((await h.call("POST", `/api/chat/turns/${second}/undo`, { body: { mode: "strict" } })).status).toBe(200);
    const again = await h.call("POST", `/api/chat/turns/${second}/undo`, { body: { mode: "strict" } });
    expect(await again.json()).toMatchObject({ error: "undo_unavailable", reason: "already_undone" });
    expect((await h.call("POST", `/api/chat/turns/${first}/undo`, { body: { mode: "strict" } })).status).toBe(200);
  });

  it.each([[{ mode: "everything" }], [{}], [{ mode: 3 }]])("refuses the mode %j", async (body) => {
    const h = chatHarness();
    const turnId = await editedTurn(h);
    const response = await h.call("POST", `/api/chat/turns/${turnId}/undo`, { body });
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ error: "invalid_mode" });
    expect(read(h, "a.tex")).toBe("a-agent");
  });

  it("refuses an undo while a turn runs", async () => {
    const h = chatHarness();
    const turnId = await editedTurn(h);
    h.runners.claude.script = async function* ({ gate }) {
      await gate;
      yield { type: "done", reason: "completed" };
    };
    const { response } = await startHeld(h);
    const undo = await h.call("POST", `/api/chat/turns/${turnId}/undo`, { body: { mode: "strict" } });
    expect(undo.status).toBe(409);
    expect(await undo.json()).toMatchObject({ error: "busy" });
    h.runners.claude.release();
    await response.text();
  });

  it("puts a note that names the reverted files into the next message to the agent", async () => {
    const h = chatHarness();
    const turnId = await editedTurn(h);
    await h.call("POST", `/api/chat/turns/${turnId}/undo`, { body: { mode: "strict" } });
    h.runners.claude.script = async function* () {
      yield { type: "done", reason: "completed" };
    };
    await h.sendMessage("Try a shorter version");
    await h.sendMessage("And one more thing");
    const [, next, after] = h.runners.claude.requests;
    expect(next!.prompt).toContain("- a.tex");
    expect(next!.prompt).toContain("- new.tex");
    expect(next!.prompt.endsWith("Try a shorter version")).toBe(true);
    expect(after!.prompt).toBe("And one more thing");
  });
});

describe("conversation and definition", () => {
  it("resumes the provider session on the next message and starts over after a new chat", async () => {
    const h = chatHarness();
    h.runners.claude.script = async function* () {
      yield { type: "session", sessionId: "sess-1" };
      yield { type: "done", reason: "completed" };
    };
    await h.sendMessage("one");
    await h.sendMessage("two");
    expect(h.runners.claude.requests.map((request) => request.sessionId)).toEqual([null, "sess-1"]);

    const reset = await h.call("POST", "/api/chat/sessions/reset", { body: { provider: "claude" } });
    expect(reset.status).toBe(200);
    expect(((await (await h.call("GET", "/api/chat/history?provider=claude")).json()) as { turns: unknown[] }).turns).toEqual([]);
    await h.sendMessage("three");
    expect(h.runners.claude.requests.map((request) => request.sessionId)).toEqual([null, "sess-1", null]);
  });

  it("starts a new conversation and says so when the isolation level changes", async () => {
    const h = chatHarness();
    h.runners.claude.script = async function* () {
      yield { type: "session", sessionId: "sess-1" };
      yield { type: "done", reason: "completed" };
    };
    await h.sendMessage("one");
    h.runners.claude.isolationTier = "another-tier";
    const { frames } = await h.sendMessage("two");
    expect(frames[0]?.data).toMatchObject({ type: "notice", message: "New conversation started because the isolation level changed." });
    expect(h.runners.claude.requests[1]!.sessionId).toBeNull();
  });

  it("refuses a new chat while a turn runs, and an unknown provider", async () => {
    const h = chatHarness();
    h.runners.claude.script = async function* ({ gate }) {
      await gate;
      yield { type: "done", reason: "completed" };
    };
    const { response } = await startHeld(h);
    expect((await h.call("POST", "/api/chat/sessions/reset", { body: { provider: "claude" } })).status).toBe(409);
    expect((await h.call("POST", "/api/chat/sessions/reset", { body: { provider: "gemini" } })).status).toBe(400);
    h.runners.claude.release();
    await response.text();
  });

  it("keeps a definition the user changed, tells the chat, and replaces it on request", async () => {
    const h = chatHarness();
    await h.sendMessage("first");
    const target = join(h.root, ".claude", "agents", "caztor.md");
    const shipped = readFileSync(target, "utf8");
    writeFileSync(target, `${shipped}\nMy own rule.\n`);
    const { frames } = await h.sendMessage("second");
    expect(frames[0]?.data).toMatchObject({ type: "notice", level: "warning", action: "replace_definition" });
    expect(readFileSync(target, "utf8")).toContain("My own rule.");

    const replaced = await h.call("POST", "/api/chat/definition/replace", { body: { provider: "claude" } });
    expect(replaced.status).toBe(200);
    // The outcomes also list the twelve writing guides, which were not touched.
    const { outcomes } = (await replaced.json()) as { outcomes: { target: string; status: string }[] };
    expect(outcomes[0]).toEqual({ target: ".claude/agents/caztor.md", status: "updated" });
    expect(outcomes.slice(1)).toHaveLength(12);
    expect(outcomes.slice(1).every((outcome) => outcome.target.startsWith(".caztor/guides/") && outcome.status === "unchanged")).toBe(true);
    expect(readFileSync(target, "utf8")).toBe(shipped);
  });

  it("refuses to replace a definition while a turn runs", async () => {
    const h = chatHarness();
    h.runners.claude.script = async function* ({ gate }) {
      await gate;
      yield { type: "done", reason: "completed" };
    };
    const { response } = await startHeld(h);
    expect((await h.call("POST", "/api/chat/definition/replace", { body: { provider: "claude" } })).status).toBe(409);
    h.runners.claude.release();
    await response.text();
  });
});

describe("a save by the user right after the agent finished", () => {
  it("survives a strict undo, which refuses and names the file instead of reverting it", async () => {
    const h = chatHarness();
    writeFileSync(join(h.root, "main.tex"), "old text");
    h.runners.claude.script = async function* ({ write }) {
      write("main.tex", "agent text");
      try {
        yield { type: "done", reason: "completed" };
      } finally {
        // The turn leaves the loop on `done`; this save lands while it rescans and compares.
        void h.store.write("main.tex" as never, new TextEncoder().encode("user text"), "any");
      }
    };
    const { response, frames } = await h.sendMessage("Edit it");
    const turnId = response.headers.get("x-caztor-turn-id")!;

    expect(frames.at(-1)?.data).toMatchObject({ type: "files_changed", files: [{ path: "main.tex", mixed: true }] });
    const undo = await h.call("POST", `/api/chat/turns/${turnId}/undo`, { body: { mode: "strict" } });
    expect(undo.status).toBe(409);
    expect(read(h, "main.tex")).toBe("user text");
  });
});

describe("GET /api/chat/history", () => {
  it("restores the visible conversation of the provider after a reload, with the turn that can be undone", async () => {
    const h = chatHarness();
    h.runners.claude.script = async function* ({ write }) {
      yield { type: "text_delta", messageId: "m", text: "Hel" };
      yield { type: "text_delta", messageId: "m", text: "lo" };
      write("a.tex", "x");
      yield { type: "done", reason: "completed" };
    };
    const first = (await h.sendMessage("first question")).response.headers.get("x-caztor-turn-id")!;
    h.runners.claude.script = async function* () {
      yield { type: "text", messageId: "n", text: "Nothing changes." };
      yield { type: "done", reason: "completed" };
    };
    await h.sendMessage("second question");
    await h.sendMessage("opencode text", "opencode").catch(() => {});

    const history = (await (await h.call("GET", "/api/chat/history?provider=claude")).json()) as {
      provider: string;
      turns: Array<{ turnId: string; prompt: string; events: Array<{ type: string; text?: string }> }>;
      undoableTurnId: string | null;
      running: boolean;
    };
    expect(history.provider).toBe("claude");
    expect(history.turns.map((turn) => turn.prompt)).toEqual(["first question", "second question"]);
    expect(history.turns[0]?.turnId).toBe(first);
    expect(history.turns[0]?.events.find((event) => event.type === "text")?.text).toBe("Hello");
    expect(history.turns[0]?.events.at(-1)?.type).toBe("files_changed");
    // The second turn changed nothing, so it is not on the undo stack; the first is still undoable.
    expect(history.undoableTurnId).toBe(first);
    expect(history.running).toBe(false);
  });

  it("answers with a readable problem instead of a server error when the snapshot folder was replaced by a link", async () => {
    const h = chatHarness();
    h.runners.claude.script = async function* ({ write }) {
      write("a.tex", "x");
      yield { type: "done", reason: "completed" };
    };
    const turnId = (await h.sendMessage("first question")).response.headers.get("x-caztor-turn-id")!;
    mkdirSync(join(h.root, "..", `${turnId}-elsewhere`), { recursive: true });
    renameSync(join(h.root, ".caztor", "snapshots"), join(h.root, "..", `${turnId}-moved`));
    symlinkSync(join(h.root, "..", `${turnId}-elsewhere`), join(h.root, ".caztor", "snapshots"));

    const history = await h.call("GET", "/api/chat/history?provider=claude");
    const undo = await h.call("POST", `/api/chat/turns/${turnId}/undo`, { body: { mode: "strict" } });

    expect(history.status).toBe(200);
    const body = (await history.json()) as { undoableTurnId: string | null; undoProblem: string | null };
    expect(body.undoableTurnId).toBeNull();
    expect(body.undoProblem).toContain("not a plain folder");
    expect(undo.status).toBe(409);
    const problem = (await undo.json()) as { error: string; message: string };
    expect(problem.error).toBe("undo_failed");
    expect(problem.message).toContain("not a plain folder");
  });

  it("uses the selected provider when none is named, and refuses an unknown one", async () => {
    const h = chatHarness();
    await h.sendMessage("a question");
    expect((await h.call("GET", "/api/chat/history")).status).toBe(400);
    await h.call("PUT", "/api/providers/selected", { body: { provider: "claude" } });
    const history = (await (await h.call("GET", "/api/chat/history")).json()) as { provider: string; turns: unknown[] };
    expect(history.provider).toBe("claude");
    expect(history.turns).toHaveLength(1);
    expect((await h.call("GET", "/api/chat/history?provider=gemini")).status).toBe(400);
  });

  it("reports a running turn so a reloaded page can follow it", async () => {
    const h = chatHarness();
    h.runners.claude.script = async function* ({ gate }) {
      await gate;
      yield { type: "done", reason: "completed" };
    };
    const { response, turnId } = await startHeld(h);
    const history = (await (await h.call("GET", "/api/chat/history?provider=claude")).json()) as { running: boolean; currentTurnId: string | null };
    expect(history).toMatchObject({ running: true, currentTurnId: turnId });
    h.runners.claude.release();
    await response.text();
  });
});

describe("chat without agents wired", () => {
  it("refuses every chat request readably", async () => {
    const { harness } = await import("./support.ts");
    const h = harness();
    const send = await h.call("POST", "/api/chat/turns", { body: { provider: "claude", prompt: "hi" } });
    expect(send.status).toBe(503);
    expect(await send.json()).toMatchObject({ error: "chat_unavailable" });
    expect((await h.call("GET", "/api/chat/history?provider=claude")).status).toBe(503);
  });
});

describe("a user save that is on disk but not recorded yet when the turn ends", () => {
  const encode = (text: string) => new TextEncoder().encode(text);

  /** Runs a turn in which the agent edits main.tex, and the user's save is held between its rename and its record while the agent finishes. */
  async function raced() {
    let armed = false;
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => (release = resolve));
    let renamed: () => void = () => {};
    const onDisk = new Promise<void>((resolve) => (renamed = resolve));
    const h = chatHarness({
      wrapStoreFs: (fs) => ({
        ...fs,
        async rename(from, to) {
          await fs.rename(from, to);
          if (armed && to.endsWith("main.tex")) {
            renamed();
            await gate;
          }
        },
      }),
    });
    writeFileSync(join(h.root, "main.tex"), "base");
    h.runners.claude.script = async function* ({ write, gate: agentGate }) {
      write("main.tex", "agent");
      yield { type: "text", messageId: "m", text: "Edited." };
      await agentGate;
      yield { type: "done", reason: "completed" };
    };
    const response = await h.call("POST", "/api/chat/turns", { body: { provider: "claude", prompt: "Edit" } });
    const turnId = response.headers.get("x-caztor-turn-id")!;
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let text = "";
    let sawDone: () => void = () => {};
    const doneSeen = new Promise<void>((resolve) => (sawDone = resolve));
    const reading = (async () => {
      for (;;) {
        const chunk = await reader.read();
        if (chunk.done) return parseFrames(text);
        text += decoder.decode(chunk.value, { stream: true });
        if (text.includes("event: done")) sawDone();
      }
    })();
    await vi.waitFor(() => expect(read(h, "main.tex")).toBe("agent"));
    armed = true;
    const saving = h.store.write("main.tex" as never, encode("user"), (await hashBytes(encode("agent"))) as never);
    await onDisk;
    expect(read(h, "main.tex")).toBe("user");
    h.runners.claude.release();
    await doneSeen;
    // The turn now works out its changed files and ends the recording; the save stays held until that has happened
    // (a correct recorder waits for it, so this pause only makes the failure of a naive one certain).
    await new Promise((resolve) => setTimeout(resolve, 250));
    release();
    expect((await saving).ok).toBe(true);
    const frames = await reading;
    return { h, turnId, frames };
  }

  it("lists the file as changed by both, so it is a conflict and not a plain agent change", async () => {
    const { frames } = await raced();
    const summary = frames.at(-1)!.data as { files: Array<{ path: string; mixed: boolean }> };
    expect(summary.files).toMatchObject([{ path: "main.tex", mixed: true }]);
  });

  it("keeps the user's save through a strict undo", async () => {
    const { h, turnId } = await raced();
    const response = await h.call("POST", `/api/chat/turns/${turnId}/undo`, { body: { mode: "strict" } });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "undo_conflict" });
    expect(read(h, "main.tex")).toBe("user");
  });

  it("keeps the user's save through a skip_conflicts undo", async () => {
    const { h, turnId } = await raced();
    const response = await h.call("POST", `/api/chat/turns/${turnId}/undo`, { body: { mode: "skip_conflicts" } });
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ status: "restored", skipped: ["main.tex"] });
    expect(read(h, "main.tex")).toBe("user");
  });
});
