import type { ProviderId } from "@caztor/core";

export interface ProviderMeta {
  id: ProviderId;
  /**
   * The name the chat shows for the provider, as text. No vendor logo ships with Caztor (see NOTICE.md): every provider,
   * in the selector and the header, is a text label.
   */
  name: string;
  /** The command the user installs. */
  command: string;
}

export const PROVIDER_META: Record<ProviderId, ProviderMeta> = {
  opencode: { id: "opencode", name: "opencode", command: "opencode" },
  claude: { id: "claude", name: "Claude Code", command: "claude" },
  codex: { id: "codex", name: "Codex", command: "codex" },
  antigravity: { id: "antigravity", name: "Antigravity", command: "agy" },
  pi: { id: "pi", name: "Pi", command: "pi" },
};

/**
 * The providers, in the order the selector shows them as radio buttons. Codex is not offered: no PaperSmith harness
 * drives it, so a workspace has nothing to hand it. The server still knows it.
 */
export const PROVIDER_ORDER: readonly ProviderId[] = ["opencode", "claude", "pi", "antigravity"];

/** Providers offered in the selector's "More providers" dropdown, in this order. None at the moment. */
export const EXTRA_PROVIDER_ORDER: readonly ProviderId[] = [];

/** Shown for as long as Antigravity is the active provider. */
export const ANTIGRAVITY_ISOLATION_NOTICE =
  "Partial isolation: settings and MCP servers in ~/.gemini may load, and your prompts are stored there. Caztor stops a disallowed tool, but it may already have started.";

/**
 * The start of the isolation notices Pi and Antigravity turns carried before the panel took them over: such a notice,
 * stored in earlier turns, is left out of the conversation, since the panel already says it.
 */
export const TURN_ISOLATION_NOTICE_STARTS: readonly string[] = ["Pi runs with partial isolation:", "Antigravity runs with partial isolation:"];

/** Shown for as long as Pi is the active provider. */
export const PI_ISOLATION_NOTICE =
  "Partial isolation: your global Pi settings and sign-in in ~/.pi/agent still load. Caztor stops a disallowed tool, but it may already have started.";
