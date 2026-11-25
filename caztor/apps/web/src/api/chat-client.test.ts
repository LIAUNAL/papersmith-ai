import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "./client.ts";
import type { TurnEvent } from "./types.ts";

const TOKEN = "launch-token-0123456789";
const frame = (id: number, event: TurnEvent) => `id: ${id}\nevent: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`;

function streamOf(chunks: string[], fail = false): Response {
  const encoder = new TextEncoder();
  const rest = [...chunks];
  // One chunk per pull, so a failure arrives after the earlier chunks were read.
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      const next = rest.shift();
      if (next !== undefined) controller.enqueue(encoder.encode(next));
      else if (fail) controller.error(new TypeError("network error"));
      else controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
}

interface Seen {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string | undefined;
}

function clientWith(respond: (seen: Seen) => Response | Promise<Response>) {
  const calls: Seen[] = [];
  const fetchFn = async (input: RequestInfo | URL, init?: RequestInit) => {
    const seen = { url: String(input), method: init?.method ?? "GET", headers: Object.fromEntries(new Headers(init?.headers).entries()), body: init?.body as string | undefined };
    calls.push(seen);
    return respond(seen);
  };
  return { calls, api: createApiClient({ token: TOKEN, fetch: fetchFn as typeof fetch, wait: async () => {} }) };
}

describe("streamTurn", () => {
  it("posts the message and the provider with the token, and delivers events with their numbers in order", async () => {
    const { api, calls } = clientWith(() =>
      streamOf([
        frame(1, { type: "turn_started", turnId: "t1", provider: "claude", snapshotPartial: false, unprotected: [] }),
        // A frame split across two chunks still arrives once.
        frame(2, { type: "text_delta", messageId: "m", text: "Hi" }).slice(0, 12),
        frame(2, { type: "text_delta", messageId: "m", text: "Hi" }).slice(12),
        `: heartbeat\n\n`,
        frame(3, { type: "done", reason: "completed" }),
      ]),
    );
    const seen: Array<[string, number | null]> = [];
    await api.streamTurn({ kind: "start", provider: "claude", prompt: "Hello" }, (event, seq) => seen.push([event.type, seq]), new AbortController().signal);
    expect(seen).toEqual([["turn_started", 1], ["text_delta", 2], ["done", 3]]);
    expect(calls[0]).toMatchObject({ url: "/api/chat/turns", method: "POST" });
    expect(calls[0]!.headers["x-caztor-token"]).toBe(TOKEN);
    expect(calls[0]!.headers["content-type"]).toBe("application/json");
    expect(JSON.parse(calls[0]!.body!)).toEqual({ provider: "claude", prompt: "Hello" });
  });

  it("follows the current turn with Last-Event-ID, and without it from the start", async () => {
    const { api, calls } = clientWith(() => streamOf([]));
    await api.streamTurn({ kind: "follow", after: 7 }, () => {}, new AbortController().signal);
    await api.streamTurn({ kind: "follow", after: 0 }, () => {}, new AbortController().signal);
    expect(calls[0]).toMatchObject({ url: "/api/chat/turns/current", method: "GET" });
    expect(calls[0]!.headers["last-event-id"]).toBe("7");
    expect(calls[1]!.headers["last-event-id"]).toBeUndefined();
  });

  it("tells when the stream is open, before any event, and not when the request is refused", async () => {
    const opened: string[] = [];
    const ok = clientWith(() => streamOf([frame(1, { type: "done", reason: "completed" })]));
    await ok.api.streamTurn({ kind: "follow", after: 0 }, () => opened.push("event"), new AbortController().signal, () => opened.push("open"));
    expect(opened).toEqual(["open", "event"]);
    const refused = clientWith(() => new Response("{}", { status: 404 }));
    await refused.api.streamTurn({ kind: "follow", after: 0 }, () => {}, new AbortController().signal, () => opened.push("again")).catch(() => {});
    expect(opened).not.toContain("again");
  });

  it("ignores events it does not know", async () => {
    const { api } = clientWith(() => streamOf([`id: 1\nevent: mystery\ndata: {"type":"mystery"}\n\n`, `id: 2\nevent: x\ndata: not json\n\n`, frame(3, { type: "done", reason: "completed" })]));
    const types: string[] = [];
    await api.streamTurn({ kind: "follow", after: 0 }, (event) => types.push(event.type), new AbortController().signal);
    expect(types).toEqual(["done"]);
  });

  it("turns a refusal into an ApiError with the server's code and message", async () => {
    const { api } = clientWith(() => new Response(JSON.stringify({ error: "busy", message: "A turn is already running." }), { status: 409, headers: { "content-type": "application/json" } }));
    const failure = await api.streamTurn({ kind: "start", provider: "claude", prompt: "x" }, () => {}, new AbortController().signal).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ status: 409, code: "busy", message: "A turn is already running." });
  });

  it("reports a dropped connection as a status 0 error, before or during the stream", async () => {
    const before = clientWith(() => {
      throw new TypeError("fetch failed");
    });
    await expect(before.api.streamTurn({ kind: "follow", after: 0 }, () => {}, new AbortController().signal)).rejects.toMatchObject({ status: 0, code: "network" });
    const during = clientWith(() => streamOf([frame(1, { type: "done", reason: "completed" })], true));
    const seen: string[] = [];
    await expect(during.api.streamTurn({ kind: "follow", after: 0 }, (event) => seen.push(event.type), new AbortController().signal)).rejects.toMatchObject({ status: 0 });
    expect(seen).toEqual(["done"]);
  });
});

describe("chat reads and stop", () => {
  it("lists providers, reads the history of one provider and stops a turn by id", async () => {
    const { api, calls } = clientWith((seen) =>
      new Response(JSON.stringify(seen.url.startsWith("/api/providers") ? { selected: null, providers: [] } : { stopped: true }), { status: 200, headers: { "content-type": "application/json" } }),
    );
    expect(await api.listProviders()).toEqual({ selected: null, providers: [] });
    await api.chatHistory("opencode");
    await api.stopTurn("t 1");
    expect(calls.map((call) => `${call.method} ${call.url}`)).toEqual(["GET /api/providers", "GET /api/chat/history?provider=opencode", "POST /api/chat/turns/t%201/stop"]);
    expect(calls[2]!.headers["content-type"]).toBe("application/json");
  });
});

describe("provider and conversation changes", () => {
  it("re-checks, selects, sets and clears a model, and starts a new chat, each with a JSON body", async () => {
    const { api, calls } = clientWith(
      (seen) => new Response(JSON.stringify(seen.url.includes("/sessions/reset") ? { reset: true } : { selected: "claude", providers: [] }), { status: 200, headers: { "content-type": "application/json" } }),
    );
    await api.recheckProviders();
    await api.selectProvider("opencode");
    await api.setProviderModel("opencode", "anthropic/claude-sonnet");
    await api.setProviderModel("opencode", null);
    await api.resetChat("claude");
    expect(calls.map((call) => `${call.method} ${call.url} ${call.body ?? ""}`)).toEqual([
      "POST /api/providers/recheck {}",
      'PUT /api/providers/selected {"provider":"opencode"}',
      'PUT /api/providers/opencode/model {"model":"anthropic/claude-sonnet"}',
      'PUT /api/providers/opencode/model {"model":null}',
      'POST /api/chat/sessions/reset {"provider":"claude"}',
    ]);
    expect(calls.every((call) => call.headers["content-type"] === "application/json")).toBe(true);
  });
});

describe("undo and definition", () => {
  it("posts the undo mode and returns the restored and skipped files", async () => {
    const { api, calls } = clientWith(() => new Response(JSON.stringify({ status: "restored", files: ["a.tex"], skipped: ["b.tex"] }), { status: 200, headers: { "content-type": "application/json" } }));
    expect(await api.undoTurn("t 1", "skip_conflicts")).toEqual({ files: ["a.tex"], skipped: ["b.tex"] });
    expect(calls[0]).toMatchObject({ method: "POST", url: "/api/chat/turns/t%201/undo", body: '{"mode":"skip_conflicts"}' });
  });

  it("keeps the conflicts of a 409 undo_conflict answer on the error", async () => {
    const conflicts = [{ path: "a.tex", expected: "sha256:1", actual: "sha256:2" }];
    const { api } = clientWith(() => new Response(JSON.stringify({ error: "undo_conflict", message: "These files changed.", conflicts }), { status: 409, headers: { "content-type": "application/json" } }));
    const failure = (await api.undoTurn("t1", "strict").catch((error: unknown) => error)) as ApiError;
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure.code).toBe("undo_conflict");
    expect(failure.conflicts).toEqual(conflicts);
  });

  it("asks the server to replace the agent definition of a provider", async () => {
    const { api, calls } = clientWith(() => new Response(JSON.stringify({ outcomes: [] }), { status: 200, headers: { "content-type": "application/json" } }));
    await api.replaceDefinition("claude");
    expect(calls[0]).toMatchObject({ method: "POST", url: "/api/chat/definition/replace", body: '{"provider":"claude"}' });
  });
});

describe("sign-in mode and keys", () => {
  it("sets the mode with a JSON body and sends a key only in the body of a PUT, never in the URL", async () => {
    const { api, calls } = clientWith(
      (seen) => new Response(JSON.stringify(seen.url.startsWith("/api/credentials") ? { slot: "opencode:openai", set: true, last4: "1234" } : { selected: "claude", providers: [] }), { status: 200, headers: { "content-type": "application/json" } }),
    );
    await api.setAuthMode("claude", "api");
    expect(await api.saveCredential("opencode:openai", "sk-secret-abcdef1234")).toEqual({ slot: "opencode:openai", set: true, last4: "1234" });
    await api.deleteCredential("opencode:openai");
    expect(calls.map((call) => `${call.method} ${call.url} ${call.body ?? ""}`)).toEqual([
      'PUT /api/providers/claude/auth-mode {"mode":"api"}',
      'PUT /api/credentials/opencode%3Aopenai {"key":"sk-secret-abcdef1234"}',
      "DELETE /api/credentials/opencode%3Aopenai ",
    ]);
    expect(calls.every((call) => call.headers["content-type"] === "application/json")).toBe(true);
    expect(calls.every((call) => !call.url.includes("sk-secret"))).toBe(true);
  });

  it("fails with the server's readable message, which holds no key", async () => {
    const { api } = clientWith(() => new Response(JSON.stringify({ error: "invalid_key", message: "A key can use only printable ASCII characters, without spaces." }), { status: 400 }));
    await expect(api.saveCredential("claude", "bad key")).rejects.toMatchObject({ code: "invalid_key", message: "A key can use only printable ASCII characters, without spaces." });
  });
});

describe("the project a page opened", () => {
  it("is named on later requests, and a refusal says the server moved on", async () => {
    const seen: Array<string | null> = [];
    const onProjectChanged = vi.fn();
    const answers = [
      new Response(JSON.stringify({ project: { name: "a", id: "p1" }, engine: {}, sandbox: {}, settings: {} })),
      new Response(JSON.stringify({ error: "project_changed", message: "Moved." }), { status: 409 }),
    ];
    const api = createApiClient({
      token: "t",
      onProjectChanged,
      fetch: (async (_url: unknown, init?: RequestInit) => {
        seen.push(new Headers(init?.headers).get("x-caztor-project"));
        return answers.shift()!;
      }) as typeof fetch,
    });
    await api.getSession();
    await expect(api.listFiles()).rejects.toMatchObject({ code: "project_changed" });
    expect(seen).toEqual([null, "p1"]);
    expect(onProjectChanged).toHaveBeenCalledTimes(1);
  });
});
