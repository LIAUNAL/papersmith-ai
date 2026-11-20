import type { ProviderId } from "@caztor/core";
import antigravityLogo from "../assets/providers/antigravity.svg?no-inline";
import claudeLogo from "../assets/providers/claude.svg?no-inline";
import codexLogo from "../assets/providers/codex.svg?no-inline";
import opencodeLogoDark from "../assets/providers/opencode-logo-dark.svg?no-inline";
import opencodeLogoLight from "../assets/providers/opencode-logo-light.svg?no-inline";

export interface ProviderMeta {
  id: ProviderId;
  /** The name shown as text only when the logo is missing or fails to load. */
  name: string;
  /** The command the user installs. */
  command: string;
  /**
   * The vendor's official logo, shipped unmodified (see NOTICE.md). `dark` is the variant for dark color schemes.
   * Null when no official asset could be obtained: the name is shown as text instead. Codex has no logo of its own: it
   * shows the OpenAI mark.
   */
  logo: { light: string; dark?: string } | null;
}

export const PROVIDER_META: Record<ProviderId, ProviderMeta> = {
  opencode: { id: "opencode", name: "opencode", command: "opencode", logo: { light: opencodeLogoLight, dark: opencodeLogoDark } },
  claude: { id: "claude", name: "Claude Code", command: "claude", logo: { light: claudeLogo } },
  codex: { id: "codex", name: "Codex", command: "codex", logo: { light: codexLogo } },
  antigravity: { id: "antigravity", name: "Antigravity", command: "agy", logo: { light: antigravityLogo } },
  pi: { id: "pi", name: "Pi", command: "pi", logo: null },
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

/** Shown for as long as Pi is the active provider. */
export const PI_ISOLATION_NOTICE =
  "Partial isolation: your global Pi settings and sign-in in ~/.pi/agent still load. Caztor stops a disallowed tool, but it may already have started.";
