import type { ProviderId } from "./ports.ts";

/**
 * Where each provider's agent definition lives in the project. The native files sit in reserved folders, so they are
 * reachable only through the provisioner; `AGENTS.md` is shared with the user and carries a marked block. Pi reads no
 * agent file of its own: its system prompt is a file in the internal state folder, passed on the command line, so the
 * project's `.pi/` (PaperSmith's) is never written.
 */
export const AGENT_TARGETS: Readonly<Record<ProviderId, string>> = {
  claude: ".claude/agents/caztor.md",
  opencode: ".opencode/agents/caztor.md",
  codex: "AGENTS.md",
  antigravity: ".agents/agents/caztor.md",
  pi: ".caztor/agents/pi.md",
};

/** Body markers of the block Caztor manages inside `AGENTS.md`. */
export const AGENT_BLOCK_BEGIN = "<!-- caztor:agent:begin -->";
export const AGENT_BLOCK_END = "<!-- caztor:agent:end -->";

export const isAgentTarget = (path: string): boolean => (Object.values(AGENT_TARGETS) as string[]).includes(path);

/** Where the writing guides are provisioned, inside the internal state folder. */
export const GUIDES_DIR = ".caztor/guides";

const NUMBERED_GUIDE = /^\d\d-[a-z]+(?:-[a-z]+)*\.md$/;

/** The only file names the guides may have: the index, the license copy and numbered guides. */
export const isGuideName = (name: string): boolean => name === "INDEX.md" || name === "LICENSE-papersmith-ai.txt" || NUMBERED_GUIDE.test(name);

/** True for the path of a provisioned guide: a valid guide name directly inside the guides folder. */
export const isGuideTarget = (path: string): boolean => path.startsWith(`${GUIDES_DIR}/`) && isGuideName(path.slice(GUIDES_DIR.length + 1));
