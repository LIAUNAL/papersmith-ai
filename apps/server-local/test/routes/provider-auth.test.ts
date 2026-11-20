import { chmodSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createCredentialStore, credentialPaths, nodeFileSystem } from "@caztor/adapters-local";
import { afterEach, describe, expect, it } from "vitest";
import { chatHarness, cleanupChatProjects } from "./chat-support.ts";
import { cleanupProjects } from "./support.ts";

cleanupProjects();
cleanupChatProjects();

const KEY = "sk-abcdef1234";
const OPENAI_KEY = "sk-openai-9999aaaa";
const configHomes: string[] = [];
afterEach(() => {
  for (const dir of configHomes.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function setup(options: { store?: boolean } = {}) {
  const configHome = mkdtempSync(join(tmpdir(), "caztor-config-"));
  configHomes.push(configHome);
  const credentials = createCredentialStore({ fs: nodeFileSystem, configHome, uid: process.getuid?.() ?? null });
  const h = chatHarness(options.store === false ? {} : { credentials });
  return { ...h, credentials, configHome, paths: credentialPaths(configHome) };
}

interface Auth {
  mode: string;
  modes: string[];
  keys: Array<{ slot: string; set: boolean; last4?: string }>;
  /** The slot the active key goes in: the provider's own, or for opencode the one of the model's vendor. */
  slot: string | null;
  slotProblem?: string;
  apiReady: boolean;
  login: string;
  loginHint: string;
  storeProblem?: string;
}
interface Listing {
  providers: Array<{ id: string; auth: Auth }>;
}
const listing = async (response: Response): Promise<Listing> => (await response.json()) as Listing;
const authOf = (list: Listing, id: string): Auth => list.providers.find((provider) => provider.id === id)!.auth;

describe("GET /api/providers carries the sign-in state of each provider", () => {
  it("starts in account mode, offering both modes, with a login hint naming the CLI step and no key set", async () => {
    const h = setup();
    const list = await listing(await h.call("GET", "/api/providers"));
    expect(authOf(list, "claude")).toEqual({
      mode: "account",
      modes: ["account", "api"],
      keys: [{ slot: "claude", set: false }],
      slot: "claude",
      apiReady: false,
      login: "unknown",
      loginHint: "Sign in with your Claude account: run `claude`, then `/login`.",
    });
    expect(authOf(list, "codex")).toMatchObject({ keys: [{ slot: "codex", set: false }], loginHint: "Sign in with Codex: run `codex login`." });
    expect(authOf(list, "opencode").loginHint).toBe("Sign in with opencode: run `opencode providers login`.");
    expect(authOf(list, "opencode").keys.map((key) => key.slot)).toContain("opencode:openai");
    expect(authOf(list, "opencode").keys.every((key) => !key.set)).toBe(true);
  });

  it("names the opencode slot from the model's vendor, and says why there is none otherwise", async () => {
    const h = setup();
    const before = authOf(await listing(await h.call("GET", "/api/providers")), "opencode");
    expect(before.slot).toBeNull();
    expect(before.slotProblem).toContain("provider/model");
    await h.call("PUT", "/api/providers/opencode/model", { body: { model: "openai/gpt-5.5" } });
    const openai = authOf(await listing(await h.call("GET", "/api/providers")), "opencode");
    expect(openai.slot).toBe("opencode:openai");
    expect(openai.slotProblem).toBeUndefined();
    await h.call("PUT", "/api/providers/opencode/model", { body: { model: "nowhere/m" } });
    const nowhere = authOf(await listing(await h.call("GET", "/api/providers")), "opencode");
    expect(nowhere.slot).toBeNull();
    expect(nowhere.slotProblem).toContain("nowhere");
  });

  it("shows which keys are set with the last four characters, never a key", async () => {
    const h = setup();
    await h.credentials.set("claude", KEY);
    await h.credentials.set("opencode:openai", OPENAI_KEY);
    const response = await h.call("GET", "/api/providers");
    const text = await response.text();
    expect(text).not.toContain(KEY);
    expect(text).not.toContain(OPENAI_KEY);
    const list = JSON.parse(text) as Listing;
    expect(authOf(list, "claude").keys).toEqual([{ slot: "claude", set: true, last4: "1234" }]);
    expect(authOf(list, "opencode").keys.find((key) => key.slot === "opencode:openai")).toEqual({ slot: "opencode:openai", set: true, last4: "aaaa" });
  });

  it("reports the problem, and no keys, when the store cannot be used", async () => {
    const h = setup();
    await h.credentials.set("claude", KEY);
    chmodSync(h.paths.file, 0o644);
    const list = await listing(await h.call("GET", "/api/providers"));
    expect(authOf(list, "claude")).toMatchObject({ keys: [], apiReady: false, storeProblem: expect.stringContaining("chmod") });
  });

  it("reports no keys and no store problem when the server has no store, and api is never ready", async () => {
    const h = setup({ store: false });
    const claude = authOf(await listing(await h.call("GET", "/api/providers")), "claude");
    expect(claude.keys).toEqual([]);
    expect(claude.apiReady).toBe(false);
    expect(claude.storeProblem).toEqual(expect.any(String));
  });
});

describe("Antigravity signs in with its account only", () => {
  it("offers only account mode, no key slots and the agy login hint", async () => {
    const h = setup();
    const antigravity = authOf(await listing(await h.call("GET", "/api/providers")), "antigravity");
    expect(antigravity).toMatchObject({ mode: "account", modes: ["account"], keys: [], slot: null, apiReady: false, loginHint: "Sign in with Antigravity: run `agy` and follow the sign-in prompts." });
  });

  it("rejects api mode with mode_unsupported and keeps account, even with every other key stored", async () => {
    const h = setup();
    await h.credentials.set("claude", KEY);
    const response = await h.call("PUT", "/api/providers/antigravity/auth-mode", { body: { mode: "api" } });
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ error: "mode_unsupported", message: expect.stringContaining("account") });
    expect((await h.deps.state.load()).authModes).toEqual({});
  });

  it("accepts account mode for it", async () => {
    const h = setup();
    expect((await h.call("PUT", "/api/providers/antigravity/auth-mode", { body: { mode: "account" } })).status).toBe(200);
  });

  it("refuses to store a key for it", async () => {
    const h = setup();
    expect((await h.call("PUT", "/api/credentials/antigravity", { body: { key: KEY } })).status).toBe(404);
  });
});

describe("PUT /api/providers/:id/auth-mode", () => {
  it("rejects api mode without a stored key, with api_key_missing, and the mode stays account", async () => {
    const h = setup();
    const response = await h.call("PUT", "/api/providers/claude/auth-mode", { body: { mode: "api" } });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "api_key_missing", message: expect.stringContaining("API key") });
    expect((await h.deps.state.load()).authModes).toEqual({});
  });

  it("switches to api mode once a key is stored, keeps it across requests, and switches back", async () => {
    const h = setup();
    await h.call("PUT", "/api/credentials/claude", { body: { key: KEY } });
    const switched = await h.call("PUT", "/api/providers/claude/auth-mode", { body: { mode: "api" } });
    expect(switched.status).toBe(200);
    expect(authOf(await listing(switched), "claude")).toMatchObject({ mode: "api", apiReady: true });
    expect((await h.deps.state.load()).authModes).toEqual({ claude: "api" });
    expect(authOf(await listing(await h.call("GET", "/api/providers")), "claude").mode).toBe("api");

    const back = await h.call("PUT", "/api/providers/claude/auth-mode", { body: { mode: "account" } });
    expect(authOf(await listing(back), "claude").mode).toBe("account");
    expect((await h.deps.state.load()).authModes).toEqual({ claude: "account" });
  });

  it("changes only the provider it names", async () => {
    const h = setup();
    await h.credentials.set("claude", KEY);
    await h.credentials.set("codex", "codex-key-12345678");
    await h.call("PUT", "/api/providers/claude/auth-mode", { body: { mode: "api" } });
    const list = await listing(await h.call("GET", "/api/providers"));
    expect(authOf(list, "codex").mode).toBe("account");
    expect(authOf(list, "opencode").mode).toBe("account");
  });

  it("keeps api mode but reports it not ready after the key is deleted", async () => {
    const h = setup();
    await h.credentials.set("claude", KEY);
    await h.call("PUT", "/api/providers/claude/auth-mode", { body: { mode: "api" } });
    await h.call("DELETE", "/api/credentials/claude");
    expect(authOf(await listing(await h.call("GET", "/api/providers")), "claude")).toMatchObject({ mode: "api", apiReady: false });
  });

  it("uses the key of the opencode model's vendor: not ready for another vendor's key, rejected without a vendor", async () => {
    const h = setup();
    await h.credentials.set("opencode:openai", OPENAI_KEY);
    await h.call("PUT", "/api/providers/opencode/model", { body: { model: "anthropic/claude-sonnet-4-5" } });
    const noKey = await h.call("PUT", "/api/providers/opencode/auth-mode", { body: { mode: "api" } });
    expect(noKey.status).toBe(409);
    expect(await noKey.json()).toMatchObject({ error: "api_key_missing", message: expect.stringContaining("anthropic") });

    await h.call("PUT", "/api/providers/opencode/model", { body: { model: "openai/gpt-5.5" } });
    const ok = await h.call("PUT", "/api/providers/opencode/auth-mode", { body: { mode: "api" } });
    expect(authOf(await listing(ok), "opencode")).toMatchObject({ mode: "api", apiReady: true });

    await h.call("PUT", "/api/providers/opencode/model", { body: { model: "anthropic/claude-sonnet-4-5" } });
    expect(authOf(await listing(await h.call("GET", "/api/providers")), "opencode")).toMatchObject({ mode: "api", apiReady: false });
  });

  it("rejects opencode api mode without a model, and a vendor Caztor has no key route for", async () => {
    const h = setup();
    const none = await h.call("PUT", "/api/providers/opencode/auth-mode", { body: { mode: "api" } });
    expect(none.status).toBe(409);
    expect(await none.json()).toMatchObject({ error: "api_key_missing", message: expect.stringContaining("provider/model") });
    await h.call("PUT", "/api/providers/opencode/model", { body: { model: "nowhere/model" } });
    const unsupported = await h.call("PUT", "/api/providers/opencode/auth-mode", { body: { mode: "api" } });
    expect(unsupported.status).toBe(400);
    expect(await unsupported.json()).toMatchObject({ error: "mode_unsupported" });
  });

  it("rejects a mode it does not know, an unknown provider and a body that is not JSON", async () => {
    const h = setup();
    expect((await h.call("PUT", "/api/providers/claude/auth-mode", { body: { mode: "oauth" } })).status).toBe(400);
    expect((await h.call("PUT", "/api/providers/claude/auth-mode", { body: {} })).status).toBe(400);
    expect((await h.call("PUT", "/api/providers/nobody/auth-mode", { body: { mode: "api" } })).status).toBe(404);
    expect((await h.call("PUT", "/api/providers/claude/auth-mode", { body: "{no" })).status).toBe(400);
    expect((await h.deps.state.load()).authModes).toEqual({});
  });

  it("is behind the launch token and the content-type gate, and changes nothing without them", async () => {
    const h = setup();
    await h.credentials.set("claude", KEY);
    const noToken = await h.call("PUT", "/api/providers/claude/auth-mode", { body: { mode: "api" }, headers: { "x-caztor-token": "" } });
    expect(noToken.status).toBe(401);
    const form = await h.call("PUT", "/api/providers/claude/auth-mode", { body: "mode=api", headers: { "content-type": "application/x-www-form-urlencoded" } });
    expect(form.status).toBe(415);
    expect((await h.deps.state.load()).authModes).toEqual({});
  });
});

describe("the chat in api mode", () => {
  it("refuses a message without a stored key with api_key_missing and starts nothing", async () => {
    const h = setup();
    await h.deps.state.update({ authModes: { claude: "api" } });
    const response = await h.call("POST", "/api/chat/turns", { body: { provider: "claude", prompt: "Hello" } });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "api_key_missing", message: expect.stringContaining("API key") });
    expect(h.runners.claude.requests).toEqual([]);
  });

  it("starts the turn when the key is stored, handing the runner api mode and never the key", async () => {
    const h = setup();
    await h.call("PUT", "/api/credentials/claude", { body: { key: KEY } });
    await h.call("PUT", "/api/providers/claude/auth-mode", { body: { mode: "api" } });
    const { response } = await h.sendMessage("Hello");
    expect(response.status).toBe(200);
    expect(h.runners.claude.requests.map((request) => request.authMode)).toEqual(["api"]);
    expect(JSON.stringify(h.runners.claude.requests)).not.toContain(KEY);
  });

  it("runs in account mode by default", async () => {
    const h = setup();
    await h.sendMessage("Hello");
    expect(h.runners.claude.requests.map((request) => request.authMode)).toEqual(["account"]);
  });
});

describe("Pi signs in with its account or a per-vendor key", () => {
  const ANTHROPIC_KEY = "sk-ant-pi-key-7777bbbb";

  it("offers both modes, one key slot per vendor, and the pi login hint", async () => {
    const h = setup();
    const pi = authOf(await listing(await h.call("GET", "/api/providers")), "pi");
    expect(pi).toMatchObject({ mode: "account", modes: ["account", "api"], slot: null, apiReady: false, loginHint: "Sign in with Pi: run `pi`, then `/login`." });
    expect(pi.slotProblem).toBe("Choose a Pi model written as provider/model, so Caztor knows which key to use.");
    expect(pi.keys.map((key) => key.slot)).toContain("pi:anthropic");
  });

  it("stores a key under pi:<vendor>, names the slot from the model, and switches to api mode", async () => {
    const h = setup();
    expect((await h.call("PUT", "/api/credentials/pi:anthropic", { body: { key: ANTHROPIC_KEY } })).status).toBe(200);
    await h.call("PUT", "/api/providers/pi/model", { body: { model: "anthropic/claude-sonnet-4-5" } });
    const text = await (await h.call("GET", "/api/providers")).text();
    expect(text).not.toContain(ANTHROPIC_KEY);
    const pi = authOf(JSON.parse(text) as Listing, "pi");
    expect(pi).toMatchObject({ slot: "pi:anthropic", apiReady: true });
    expect((await h.call("PUT", "/api/providers/pi/auth-mode", { body: { mode: "api" } })).status).toBe(200);
    expect((await h.deps.state.load()).authModes).toEqual({ pi: "api" });
  });

  it("refuses api mode without a key for the model's vendor, naming it", async () => {
    const h = setup();
    await h.call("PUT", "/api/providers/pi/model", { body: { model: "openai/gpt-5.5" } });
    const response = await h.call("PUT", "/api/providers/pi/auth-mode", { body: { mode: "api" } });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ error: "api_key_missing", message: "No API key is stored for Pi (openai). Add one first, then switch." });
  });

  it("refuses an unknown vendor slot", async () => {
    const h = setup();
    expect((await h.call("PUT", "/api/credentials/pi:nowhere", { body: { key: KEY } })).status).toBe(404);
  });
});
