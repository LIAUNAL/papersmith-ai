import { describe, expect, it } from "vitest";
import {
  API_KEY_MAX_LENGTH,
  authModeOf,
  credentialSlot,
  DEFAULT_AUTH_MODE,
  lastFour,
  loginHintOf,
  providerSlots,
  OPENCODE_API_VENDORS,
  PI_API_VENDORS,
  parseApiKey,
  parseAuthMode,
  parseCredentialSlot,
} from "../src/index.ts";

describe("auth mode", () => {
  it("is account unless the project chose otherwise", () => {
    expect(DEFAULT_AUTH_MODE).toBe("account");
    expect(authModeOf({}, "claude")).toBe("account");
    expect(authModeOf({ opencode: "api" }, "claude")).toBe("account");
    expect(authModeOf({ opencode: "api" }, "opencode")).toBe("api");
  });

  it("parses only the two known modes", () => {
    expect(parseAuthMode("account")).toBe("account");
    expect(parseAuthMode("api")).toBe("api");
    expect(parseAuthMode("API")).toBeNull();
    expect(parseAuthMode(undefined)).toBeNull();
    expect(parseAuthMode(3)).toBeNull();
  });
});

describe("credentialSlot", () => {
  it("names one slot for claude and one for codex", () => {
    expect(credentialSlot("claude", null)).toEqual({ ok: true, value: "claude" });
    expect(credentialSlot("claude", "sonnet")).toEqual({ ok: true, value: "claude" });
    expect(credentialSlot("codex", null)).toEqual({ ok: true, value: "codex" });
  });

  it("gives opencode one slot per model vendor, taken from the model prefix", () => {
    expect(credentialSlot("opencode", "openai/gpt-5.5")).toEqual({ ok: true, value: "opencode:openai" });
    expect(credentialSlot("opencode", "anthropic/claude-sonnet-4-5")).toEqual({ ok: true, value: "opencode:anthropic" });
  });

  it("refuses an opencode model without a known vendor", () => {
    expect(credentialSlot("opencode", null)).toEqual({ ok: false, error: { code: "vendor_required", message: expect.stringContaining("provider/model") } });
    expect(credentialSlot("opencode", "gpt-5.5")).toMatchObject({ ok: false, error: { code: "vendor_required" } });
    expect(credentialSlot("opencode", "nowhere/model")).toEqual({ ok: false, error: { code: "vendor_unsupported", message: expect.stringContaining("nowhere") } });
  });

  it("gives Pi one slot per model vendor, taken from the model prefix", () => {
    expect(credentialSlot("pi", "anthropic/claude-sonnet-4-5")).toEqual({ ok: true, value: "pi:anthropic" });
    expect(credentialSlot("pi", "google/gemini-2.5-pro")).toEqual({ ok: true, value: "pi:google" });
    expect(credentialSlot("pi", "openrouter/qwen/qwen3-coder")).toEqual({ ok: true, value: "pi:openrouter" });
  });

  it("refuses a Pi model without a known vendor", () => {
    expect(credentialSlot("pi", null)).toEqual({ ok: false, error: { code: "vendor_required", message: "Choose a Pi model written as provider/model, so Caztor knows which key to use." } });
    expect(credentialSlot("pi", "sonnet")).toMatchObject({ ok: false, error: { code: "vendor_required" } });
    expect(credentialSlot("pi", "nowhere/model")).toEqual({ ok: false, error: { code: "vendor_unsupported", message: "Caztor cannot pass an API key for the provider nowhere. Sign in through Pi instead." } });
  });

  it("offers no slot to a provider that has no API mode", () => {
    expect(credentialSlot("antigravity", null)).toMatchObject({ ok: false, error: { code: "mode_unsupported" } });
  });
});

describe("parseCredentialSlot", () => {
  it("accepts the three kinds of slot and every listed vendor", () => {
    expect(parseCredentialSlot("claude")).toBe("claude");
    expect(parseCredentialSlot("codex")).toBe("codex");
    for (const vendor of OPENCODE_API_VENDORS) expect(parseCredentialSlot(`opencode:${vendor}`)).toBe(`opencode:${vendor}`);
    for (const vendor of PI_API_VENDORS) expect(parseCredentialSlot(`pi:${vendor}`)).toBe(`pi:${vendor}`);
  });

  it.each(["", "opencode", "opencode:", "opencode:unknown", "Claude", "claude ", "../claude", "opencode:openai/x", "__proto__", "antigravity", "pi", "pi:", "pi:unknown", "pi:openai/x"])("rejects %j", (slot) => {
    expect(parseCredentialSlot(slot)).toBeNull();
  });
});

describe("parseApiKey", () => {
  it("accepts printable ASCII without whitespace", () => {
    expect(parseApiKey("sk-ant-api03_AbC.dEf~123")).toEqual({ ok: true, value: "sk-ant-api03_AbC.dEf~123" });
    expect(parseApiKey("k")).toEqual({ ok: true, value: "k" });
    expect(parseApiKey("x".repeat(API_KEY_MAX_LENGTH))).toMatchObject({ ok: true });
  });

  it.each(["", "has space", "tab\tkey", "new\nline", "ünïcode", "\u007f", "x".repeat(API_KEY_MAX_LENGTH + 1)])("rejects %j", (key) => {
    expect(parseApiKey(key)).toEqual({ ok: false, error: { message: expect.any(String) } });
  });

  it("never repeats the rejected key in its message", () => {
    const rejected = parseApiKey("secret key with spaces");
    expect(rejected.ok).toBe(false);
    expect(JSON.stringify(rejected)).not.toContain("secret");
  });

  it("rejects what is not text", () => {
    expect(parseApiKey(12345)).toMatchObject({ ok: false });
    expect(parseApiKey(null)).toMatchObject({ ok: false });
  });
});

describe("lastFour", () => {
  it("shows the last four characters of a key of twelve or more", () => {
    expect(lastFour("sk-abcdef1234")).toBe("1234");
    expect(lastFour("x".repeat(11) + "a")).toBe("xxxa");
  });

  it("shows nothing for a shorter key", () => {
    expect(lastFour("sk-abcdef12")).toBeUndefined();
    expect(lastFour("short")).toBeUndefined();
  });
});

describe("loginHintOf", () => {
  it("names the exact CLI step for each provider", () => {
    expect(loginHintOf("claude")).toBe("Sign in with your Claude account: run `claude`, then `/login`.");
    expect(loginHintOf("opencode")).toBe("Sign in with opencode: run `opencode providers login`.");
    expect(loginHintOf("codex")).toBe("Sign in with Codex: run `codex login`.");
    expect(loginHintOf("antigravity")).toBe("Sign in with Antigravity: run `agy` and follow the sign-in prompts.");
    expect(loginHintOf("pi")).toBe("Sign in with Pi: run `pi`, then `/login`.");
  });
});

describe("providerSlots", () => {
  it("lists the slots that belong to a provider", () => {
    expect(providerSlots("claude")).toEqual(["claude"]);
    expect(providerSlots("codex")).toEqual(["codex"]);
    expect(providerSlots("antigravity")).toEqual([]);
    expect(providerSlots("opencode")).toEqual(OPENCODE_API_VENDORS.map((vendor) => `opencode:${vendor}`));
    expect(providerSlots("pi")).toEqual(PI_API_VENDORS.map((vendor) => `pi:${vendor}`));
  });
});
