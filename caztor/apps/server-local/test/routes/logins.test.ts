import type { LoginRelayPort, LoginView } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { cleanupProjects, harness } from "./support.ts";

cleanupProjects();

const view = (extra: Partial<LoginView> = {}): LoginView => ({ provider: "codex", method: "device", state: "running", text: "Enter this one-time code\n   XZIF-17WOH", code: "XZIF-17WOH", terminal: false, ...extra });

function fakeRelay() {
  const calls: Array<[string, ...unknown[]]> = [];
  let current: LoginView | null = null;
  const relay: LoginRelayPort = {
    methods: () => [{ id: "device", label: "ChatGPT account (device code)" }],
    async start(user, provider, method) {
      calls.push(["start", user.id, provider, method]);
      current = view();
      return { ok: true, value: current };
    },
    view(user, provider) {
      calls.push(["view", user.id, provider]);
      return current;
    },
    send(user, provider, input) {
      calls.push(["send", user.id, provider, input]);
      return current === null ? { ok: false, error: { code: "not_found", message: "none" } } : { ok: true, value: current };
    },
    cancel(user, provider) {
      calls.push(["cancel", user.id, provider]);
      const had = current !== null;
      current = had ? view({ state: "cancelled" }) : null;
      return had;
    },
    close: async () => {},
  };
  return { relay, calls };
}

describe("the login routes", () => {
  it("start, follow, send a line and cancel the caller's own sign-in", async () => {
    const { relay, calls } = fakeRelay();
    const h = harness({ logins: relay });
    const started = await h.call("POST", "/api/logins/codex", { body: {} });
    expect(started.status).toBe(201);
    expect(await started.json()).toEqual({ login: view(), methods: [{ id: "device", label: "ChatGPT account (device code)" }] });
    expect(((await (await h.call("GET", "/api/logins/codex")).json()) as { login: unknown }).login).toEqual(view());
    expect((await h.call("POST", "/api/logins/codex/input", { body: { line: "abc" } })).status).toBe(200);
    expect((await h.call("POST", "/api/logins/codex/input", { body: { key: "enter" } })).status).toBe(200);
    expect((await h.call("DELETE", "/api/logins/codex")).status).toBe(200);
    expect(calls).toEqual([
      ["start", "host", "codex", undefined],
      ["view", "host", "codex"],
      ["send", "host", "codex", { line: "abc" }],
      ["send", "host", "codex", { key: "enter" }],
      ["cancel", "host", "codex"],
      ["view", "host", "codex"],
    ]);
  });

  it("passes the chosen method", async () => {
    const { relay, calls } = fakeRelay();
    const h = harness({ logins: relay });
    await h.call("POST", "/api/logins/opencode", { body: { method: "menu" } });
    expect(calls[0]).toEqual(["start", "host", "opencode", "menu"]);
  });

  it.each([
    ["a line over the limit", { line: "x".repeat(2049) }],
    ["a line and a key at once", { line: "a", key: "enter" }],
    ["an unknown key", { key: "f1" }],
    ["no input", {}],
  ])("refuses %s without sending anything", async (_name, body) => {
    const { relay, calls } = fakeRelay();
    const h = harness({ logins: relay });
    await h.call("POST", "/api/logins/codex", { body: {} });
    const response = await h.call("POST", "/api/logins/codex/input", { body });
    expect(response.status).toBe(400);
    expect(calls.filter((call) => call[0] === "send")).toEqual([]);
  });

  it("answers 404 for an unknown provider or when there is nothing to send to or cancel", async () => {
    const { relay } = fakeRelay();
    const h = harness({ logins: relay });
    expect((await h.call("POST", "/api/logins/nobody", { body: {} })).status).toBe(404);
    expect((await h.call("POST", "/api/logins/codex/input", { body: { line: "abc" } })).status).toBe(404);
    expect((await h.call("DELETE", "/api/logins/codex")).status).toBe(404);
    expect(((await (await h.call("GET", "/api/logins/codex")).json()) as { login: unknown }).login).toBeNull();
  });

  it("answers 503 when signing in from the browser is not set up", async () => {
    const h = harness();
    expect((await h.call("POST", "/api/logins/codex", { body: {} })).status).toBe(503);
  });
});
