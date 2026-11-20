import { AUTH_MODES } from "./ports.ts";
import type { AuthMode, CredentialSlot, ProviderId, Result } from "./ports.ts";

export const DEFAULT_AUTH_MODE: AuthMode = "account";

export const parseAuthMode = (value: unknown): AuthMode | null => (AUTH_MODES as readonly unknown[]).includes(value) ? (value as AuthMode) : null;

/** The mode in effect for a provider: what the project stored, or `account`. */
export const authModeOf = (modes: Partial<Record<ProviderId, AuthMode>>, provider: ProviderId): AuthMode => modes[provider] ?? DEFAULT_AUTH_MODE;

/** The model vendors whose key opencode can be given. Each has its own slot, so a key never reaches another vendor. */
export const OPENCODE_API_VENDORS = ["openai", "anthropic", "google", "openrouter", "groq", "xai", "mistral", "deepseek", "opencode"] as const;

/**
 * The model vendors whose key Pi can be given, named as Pi names its providers (the `provider/` prefix of a model). Each
 * has its own slot, as for opencode.
 */
export const PI_API_VENDORS = ["anthropic", "openai", "google", "openrouter", "groq", "xai", "mistral", "deepseek", "cerebras", "opencode"] as const;

export type SlotError = { code: "vendor_required" | "vendor_unsupported" | "mode_unsupported"; message: string };

/** The providers whose key depends on the model's vendor, with their vendors and the name the messages use. */
const VENDOR_SLOTTED: Readonly<Record<string, { vendors: readonly string[]; name: string; article: string }>> = {
  opencode: { vendors: OPENCODE_API_VENDORS, name: "opencode", article: "an" },
  pi: { vendors: PI_API_VENDORS, name: "Pi", article: "a" },
};

/** The slot a provider's key lives in; for opencode and Pi it depends on the vendor in the model name (`vendor/model`). */
export function credentialSlot(provider: string, model: string | null): Result<CredentialSlot, SlotError> {
  if (provider === "claude" || provider === "codex") return { ok: true, value: provider };
  const slotted = Object.hasOwn(VENDOR_SLOTTED, provider) ? VENDOR_SLOTTED[provider] : undefined;
  if (slotted === undefined) return { ok: false, error: { code: "mode_unsupported", message: `${provider} signs in with its account only.` } };
  const vendor = model?.includes("/") === true ? model.slice(0, model.indexOf("/")) : "";
  if (vendor === "") return { ok: false, error: { code: "vendor_required", message: `Choose ${slotted.article} ${slotted.name} model written as provider/model, so Caztor knows which key to use.` } };
  if (!slotted.vendors.includes(vendor)) {
    return { ok: false, error: { code: "vendor_unsupported", message: `Caztor cannot pass an API key for the provider ${vendor}. Sign in through ${slotted.name} instead.` } };
  }
  return { ok: true, value: `${provider}:${vendor}` };
}

/** A slot name that is one of the known ones, or null. Anything else is never used as a key in the store. */
export function parseCredentialSlot(value: string): CredentialSlot | null {
  if (value === "claude" || value === "codex") return value;
  const colon = value.indexOf(":");
  if (colon === -1) return null;
  const provider = value.slice(0, colon);
  const slotted = Object.hasOwn(VENDOR_SLOTTED, provider) ? VENDOR_SLOTTED[provider] : undefined;
  return slotted !== undefined && slotted.vendors.includes(value.slice(colon + 1)) ? value : null;
}

/** How the messages name the key of a slot: `claude`, or `opencode (openai)` for a vendor slot. */
export function slotLabel(slot: CredentialSlot): string {
  const colon = slot.indexOf(":");
  if (colon === -1) return slot;
  const provider = slot.slice(0, colon);
  return `${VENDOR_SLOTTED[provider]?.name ?? provider} (${slot.slice(colon + 1)})`;
}

export const API_KEY_MAX_LENGTH = 512;
const API_KEY_SHAPE = /^[!-~]+$/;

/** A key to store: 1 to 512 printable ASCII characters without whitespace. The message never repeats the key. */
export function parseApiKey(value: unknown): Result<string, { message: string }> {
  if (typeof value !== "string" || value === "") return { ok: false, error: { message: "Enter an API key." } };
  if (value.length > API_KEY_MAX_LENGTH) return { ok: false, error: { message: `The key is too long (the limit is ${API_KEY_MAX_LENGTH} characters).` } };
  if (!API_KEY_SHAPE.test(value)) return { ok: false, error: { message: "A key can use only printable ASCII characters, without spaces." } };
  return { ok: true, value };
}

/** Shorter keys show nothing: four characters of a short key would be too large a part of it. */
const LAST4_MIN_KEY_LENGTH = 12;
export const lastFour = (key: string): string | undefined => (key.length >= LAST4_MIN_KEY_LENGTH ? key.slice(-4) : undefined);

const LOGIN_HINTS: Readonly<Record<ProviderId, string>> = {
  claude: "Sign in with your Claude account: run `claude`, then `/login`.",
  opencode: "Sign in with opencode: run `opencode providers login`.",
  codex: "Sign in with Codex: run `codex login`.",
  antigravity: "Sign in with Antigravity: run `agy` and follow the sign-in prompts.",
  pi: "Sign in with Pi: run `pi`, then `/login`.",
};

/** What the user does in a terminal to sign in to the provider's CLI. */
export const loginHintOf = (provider: ProviderId): string => LOGIN_HINTS[provider];

/** Every credential slot a provider can use. */
export const providerSlots = (provider: ProviderId): CredentialSlot[] => {
  const slotted = VENDOR_SLOTTED[provider];
  if (slotted !== undefined) return slotted.vendors.map((vendor) => `${provider}:${vendor}`);
  return provider === "antigravity" ? [] : [provider];
};
