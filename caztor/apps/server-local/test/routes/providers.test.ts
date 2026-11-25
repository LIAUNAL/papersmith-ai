import { describe, expect, it } from "vitest";
import { chatHarness, cleanupChatProjects } from "./chat-support.ts";
import { cleanupProjects, harness } from "./support.ts";

cleanupProjects();
cleanupChatProjects();

interface ProviderList {
  selected: string | null;
  providers: Array<{
    id: string;
    installed: boolean;
    unavailableReason?: string;
    version?: string;
    versionWarning?: string;
    models?: string[];
    requiresModel: boolean;
    supportsModel?: boolean;
    note?: string;
    projectConfig?: { files: string[]; confirmed: boolean; fingerprint: string };
    model: string | null;
    auth: { mode: string };
  }>;
}

const REQUESTS: Array<[string, string, unknown]> = [
  ["GET", "/api/providers", undefined],
  ["POST", "/api/providers/recheck", {}],
  ["PUT", "/api/providers/selected", { provider: "claude" }],
  ["PUT", "/api/providers/claude/model", { model: "sonnet" }],
  ["POST", "/api/providers/claude/project-config/trust", { fingerprint: "sha256:x" }],
];

describe("provider routes are behind the security gate", () => {
  it.each(REQUESTS)("%s %s is rejected without the launch token and changes nothing", async (method, path, body) => {
    const h = chatHarness();
    const response = await h.call(method, path, { ...(body === undefined ? {} : { body }), headers: { "x-caztor-token": "" } });
    expect(response.status).toBe(401);
    expect((await h.deps.state.load()).selectedProvider).toBeNull();
    expect((await h.deps.state.load()).models).toEqual({});
    expect(h.runners.claude.detections).toBe(0);
  });
});

describe("GET /api/providers", () => {
  it("lists all five providers with availability, the reason when unavailable and the saved model", async () => {
    const h = chatHarness();
    h.runners.claude.status = { provider: "claude", installed: true, version: "2.1.296", requiresModel: false, models: ["sonnet", "opus"] };
    await h.deps.state.update({ models: { opencode: "free/model" } });
    const list = (await (await h.call("GET", "/api/providers")).json()) as ProviderList;
    expect(list.selected).toBeNull();
    expect(list.providers.map((provider) => provider.id)).toEqual(["claude", "opencode", "codex", "antigravity", "pi"]);
    expect(list.providers[0]).toEqual({ id: "claude", installed: true, version: "2.1.296", requiresModel: false, models: ["sonnet", "opus"], model: null, auth: expect.objectContaining({ mode: "account" }) });
    expect(list.providers[1]).toMatchObject({ id: "opencode", installed: true, requiresModel: true, model: "free/model" });
    expect(list.providers[2]).toMatchObject({ id: "codex", installed: false, requiresModel: false, model: null });
    expect(list.providers[2]?.unavailableReason).toMatch(/not available yet/i);
  });

  it("passes on a note, and that a provider takes no model", async () => {
    const h = chatHarness();
    h.runners.claude.status = { provider: "claude", installed: true, requiresModel: false, supportsModel: false, note: "Something to know." };
    const list = (await (await h.call("GET", "/api/providers")).json()) as ProviderList;
    expect(list.providers[0]).toEqual({ id: "claude", installed: true, requiresModel: false, supportsModel: false, note: "Something to know.", model: null, auth: expect.objectContaining({ mode: "account" }) });
    expect(list.providers[1]).not.toHaveProperty("supportsModel");
    expect(list.providers[1]).not.toHaveProperty("note");
  });

  it("shows the reason an installed-looking provider is unavailable", async () => {
    const h = chatHarness();
    h.runners.claude.status = { provider: "claude", installed: false, unavailableReason: "claude is not installed", requiresModel: false };
    const list = (await (await h.call("GET", "/api/providers")).json()) as ProviderList;
    expect(list.providers[0]).toMatchObject({ id: "claude", installed: false, unavailableReason: "claude is not installed" });
  });

  it("detects once and answers later requests from the cache until a re-check", async () => {
    const h = chatHarness();
    await h.call("GET", "/api/providers");
    await h.call("GET", "/api/providers");
    expect(h.runners.claude.detections).toBe(1);

    h.runners.claude.status = { provider: "claude", installed: false, unavailableReason: "claude was removed", requiresModel: false };
    const stale = (await (await h.call("GET", "/api/providers")).json()) as ProviderList;
    expect(stale.providers[0]?.installed).toBe(true);

    const fresh = (await (await h.call("POST", "/api/providers/recheck", { body: {} })).json()) as ProviderList;
    expect(fresh.providers[0]).toMatchObject({ installed: false, unavailableReason: "claude was removed" });
    expect(h.runners.claude.detections).toBe(2);
    const after = (await (await h.call("GET", "/api/providers")).json()) as ProviderList;
    expect(after.providers[0]?.installed).toBe(false);
  });

  it("lists every provider as unavailable when no agents are wired", async () => {
    const h = harness();
    const list = (await (await h.call("GET", "/api/providers")).json()) as ProviderList;
    expect(list.providers.map((provider) => [provider.id, provider.installed])).toEqual([["claude", false], ["opencode", false], ["codex", false], ["antigravity", false], ["pi", false]]);
    expect(list.providers.every((provider) => typeof provider.unavailableReason === "string")).toBe(true);
  });

  it("copes with an adapter whose detection throws", async () => {
    const h = chatHarness();
    h.runners.claude.detect = async () => {
      throw new Error("spawn failed");
    };
    const list = (await (await h.call("GET", "/api/providers")).json()) as ProviderList;
    expect(list.providers[0]).toMatchObject({ id: "claude", installed: false, unavailableReason: expect.stringContaining("spawn failed") });
  });
});

describe("PUT /api/providers/selected", () => {
  it("saves the choice for the project and reports it", async () => {
    const h = chatHarness();
    const response = await h.call("PUT", "/api/providers/selected", { body: { provider: "opencode" } });
    expect(response.status).toBe(200);
    expect(((await response.json()) as ProviderList).selected).toBe("opencode");
    expect((await h.deps.state.load()).selectedProvider).toBe("opencode");
    expect(((await (await h.call("GET", "/api/providers")).json()) as ProviderList).selected).toBe("opencode");

    await h.call("PUT", "/api/providers/selected", { body: { provider: "claude" } });
    expect((await h.deps.state.load()).selectedProvider).toBe("claude");
  });

  it.each([[{ provider: "gemini" }], [{ provider: 3 }], [{}], [{ provider: "__proto__" }]])("refuses %j", async (body) => {
    const h = chatHarness();
    const response = await h.call("PUT", "/api/providers/selected", { body });
    expect(response.status).toBe(400);
    expect(((await response.json()) as { message: string }).message).toMatch(/claude, opencode, codex, antigravity or pi/);
    expect((await h.deps.state.load()).selectedProvider).toBeNull();
  });

  it("refuses a body that is not JSON", async () => {
    const h = chatHarness();
    expect((await h.call("PUT", "/api/providers/selected", { body: "{nope" })).status).toBe(400);
  });
});

describe("PUT /api/providers/:id/model", () => {
  it("saves a valid model for that provider only and shows it in the list", async () => {
    const h = chatHarness();
    const response = await h.call("PUT", "/api/providers/opencode/model", { body: { model: "anthropic/claude-sonnet-4.5" } });
    expect(response.status).toBe(200);
    expect((await h.deps.state.load()).models).toEqual({ opencode: "anthropic/claude-sonnet-4.5" });
    const list = (await response.json()) as ProviderList;
    expect(list.providers.find((provider) => provider.id === "opencode")?.model).toBe("anthropic/claude-sonnet-4.5");
    expect(list.providers.find((provider) => provider.id === "claude")?.model).toBeNull();
  });

  it("rejects a value that could be read as a command-line option, with a readable message, and keeps the old model", async () => {
    const h = chatHarness();
    await h.call("PUT", "/api/providers/claude/model", { body: { model: "sonnet" } });
    for (const model of ["--dangerous", "-m", "--model=x"]) {
      const response = await h.call("PUT", "/api/providers/claude/model", { body: { model } });
      expect(response.status).toBe(400);
      expect(((await response.json()) as { message: string }).message).toMatch(/cannot start with a dash/);
    }
    expect((await h.deps.state.load()).models).toEqual({ claude: "sonnet" });
  });

  it.each([["has space"], ["a;b"], ["x".repeat(201)], [42], [["a"]]])("rejects %j", async (model) => {
    const h = chatHarness();
    expect((await h.call("PUT", "/api/providers/claude/model", { body: { model } })).status).toBe(400);
    expect((await h.deps.state.load()).models).toEqual({});
  });

  it("clears the model with null or an empty value", async () => {
    const h = chatHarness();
    await h.call("PUT", "/api/providers/claude/model", { body: { model: "sonnet" } });
    await h.call("PUT", "/api/providers/claude/model", { body: { model: null } });
    expect((await h.deps.state.load()).models).toEqual({});
    await h.call("PUT", "/api/providers/claude/model", { body: { model: "opus" } });
    await h.call("PUT", "/api/providers/claude/model", { body: { model: "  " } });
    expect((await h.deps.state.load()).models).toEqual({});
  });

  it("refuses an unknown provider and a body without a model field", async () => {
    const h = chatHarness();
    expect((await h.call("PUT", "/api/providers/gemini/model", { body: { model: "x" } })).status).toBe(404);
    expect((await h.call("PUT", "/api/providers/claude/model", { body: {} })).status).toBe(400);
    expect((await h.deps.state.load()).models).toEqual({});
  });
});

describe("the project's CLI configuration", () => {
  const FINGERPRINT = `sha256:${"a".repeat(64)}`;

  it("is listed with its files, unconfirmed, only for a provider whose project carries some", async () => {
    const h = chatHarness();
    h.runners.opencode.config = { files: ["opencode.json", ".opencode/plugins/"], fingerprint: FINGERPRINT };
    const list = (await (await h.call("GET", "/api/providers")).json()) as ProviderList;
    expect(list.providers[1]?.projectConfig).toEqual({ files: ["opencode.json", ".opencode/plugins/"], confirmed: false, fingerprint: FINGERPRINT });
    expect(list.providers[0]).not.toHaveProperty("projectConfig");
  });

  it("is trusted by sending back the fingerprint of the files that were shown, and is remembered per provider", async () => {
    const h = chatHarness();
    h.runners.opencode.config = { files: ["opencode.json"], fingerprint: FINGERPRINT };
    const response = await h.call("POST", "/api/providers/opencode/project-config/trust", { body: { fingerprint: FINGERPRINT } });
    expect(response.status).toBe(200);
    expect(((await response.json()) as ProviderList).providers[1]?.projectConfig).toEqual({ files: ["opencode.json"], confirmed: true, fingerprint: FINGERPRINT });
    expect((await h.deps.state.load()).projectCliConfigTrusted).toEqual({ opencode: FINGERPRINT });
  });

  it("is not trusted when the files changed since they were shown, and says to review them again", async () => {
    const h = chatHarness();
    h.runners.opencode.config = { files: ["opencode.json"], fingerprint: `sha256:${"b".repeat(64)}` };
    const response = await h.call("POST", "/api/providers/opencode/project-config/trust", { body: { fingerprint: FINGERPRINT } });
    expect(response.status).toBe(409);
    expect(((await response.json()) as { error: string }).error).toBe("project_config_changed");
    expect((await h.deps.state.load()).projectCliConfigTrusted).toEqual({});
  });

  it("stops counting as trusted when a file changes after the confirmation", async () => {
    const h = chatHarness();
    h.runners.opencode.config = { files: ["opencode.json"], fingerprint: FINGERPRINT };
    await h.call("POST", "/api/providers/opencode/project-config/trust", { body: { fingerprint: FINGERPRINT } });
    h.runners.opencode.config = { files: ["opencode.json"], fingerprint: `sha256:${"c".repeat(64)}` };
    const list = (await (await h.call("GET", "/api/providers")).json()) as ProviderList;
    expect(list.providers[1]?.projectConfig?.confirmed).toBe(false);
  });

  it.each([
    ["an unknown provider", "/api/providers/nobody/project-config/trust", { fingerprint: FINGERPRINT }, 404],
    ["a body without a fingerprint", "/api/providers/opencode/project-config/trust", {}, 400],
    ["a provider with nothing to trust", "/api/providers/claude/project-config/trust", { fingerprint: FINGERPRINT }, 409],
  ])("refuses %s", async (_name, path, body, status) => {
    const h = chatHarness();
    h.runners.opencode.config = { files: ["opencode.json"], fingerprint: FINGERPRINT };
    expect((await h.call("POST", path, { body })).status).toBe(status);
    expect((await h.deps.state.load()).projectCliConfigTrusted).toEqual({});
  });
});
