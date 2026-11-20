import type { AgentDefinition, ContentHash, ProviderId } from "@caztor/core";

/** The agent name every definition uses; the file name carries it for opencode. */
export const AGENT_NAME = "caztor";

type Frontmatter = Record<string, string | Record<string, string>>;

/**
 * Reads the flat `key: value` frontmatter these definitions use, with one level of nested keys. Returns null when
 * the text has no frontmatter block or a line this small reader does not understand.
 */
export function parseFrontmatter(text: string): { data: Frontmatter; body: string } | null {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text);
  if (match === null) return null;
  const data: Frontmatter = {};
  let nested: Record<string, string> | null = null;
  for (const line of (match[1] ?? "").split(/\r?\n/)) {
    if (line.trim() === "") continue;
    const child = /^ {2}([A-Za-z_]+): *(.*)$/.exec(line);
    if (child !== null && nested !== null) {
      nested[child[1] as string] = child[2] as string;
      continue;
    }
    const top = /^([A-Za-z_]+):(?: *(.*))?$/.exec(line);
    if (top === null) return null;
    if (top[2] === undefined || top[2] === "") {
      nested = {};
      data[top[1] as string] = nested;
    } else {
      nested = null;
      data[top[1] as string] = top[2];
    }
  }
  return { data, body: text.slice(match[0].length) };
}

/**
 * The definition a provider's file describes. `hash` identifies the content that is present (the session record
 * compares it), and the other fields come from the file. Null when the file cannot be understood.
 */
export function parseAgentFile(provider: ProviderId, text: string, hash: ContentHash): AgentDefinition | null {
  // Both are plain Markdown: AGENTS.md for Codex, and the system prompt file Pi is given on its command line.
  if (provider === "codex" || provider === "pi") {
    return { hash, name: AGENT_NAME, description: "Caztor academic writing instructions", prompt: text.trim(), tools: [] };
  }
  const parsed = parseFrontmatter(text);
  if (parsed === null) return null;
  const { data, body } = parsed;
  const description = data["description"];
  if (typeof description !== "string" || description === "") return null;
  if (provider === "claude") {
    const tools = data["tools"];
    if (data["name"] !== AGENT_NAME || typeof tools !== "string") return null;
    return {
      hash,
      name: AGENT_NAME,
      description,
      prompt: body.trim(),
      tools: tools
        .split(",")
        .map((tool) => tool.trim())
        .filter((tool) => tool !== ""),
    };
  }
  if (provider === "antigravity") {
    const tools = data["tools"];
    if (data["name"] !== AGENT_NAME || typeof tools !== "string") return null;
    // The tool list is written on one line between brackets.
    const bracketed = /^\[(.*)\]$/.exec(tools.trim());
    if (bracketed === null) return null;
    return { hash, name: AGENT_NAME, description, prompt: body.trim(), tools: (bracketed[1] ?? "").split(",").map((tool) => tool.trim()).filter((tool) => tool !== "") };
  }
  const permission = data["permission"];
  const allowed = typeof permission === "object" ? Object.entries(permission).filter(([, value]) => value === "allow").map(([key]) => key) : [];
  return { hash, name: AGENT_NAME, description, prompt: body.trim(), tools: allowed };
}

/**
 * The `permission` map of an opencode definition file, or null when the text is not a definition. A key the file does
 * not mention is absent from the map (opencode allows it).
 */
export function parseOpencodePermissions(text: string): Record<string, string> | null {
  const parsed = parseFrontmatter(text);
  if (parsed === null) return null;
  const permission = parsed.data["permission"];
  return typeof permission === "object" ? { ...permission } : {};
}

/** The only tools the Antigravity agent may have: reading, searching and editing files. */
export const ANTIGRAVITY_ALLOWED_TOOLS: readonly string[] = ["view_file", "list_dir", "find_by_name", "grep_search", "replace_file_content", "write_to_file"];

/**
 * Why a definition file at `.agents/agents/caztor.md` lets the agent do more than Caztor intends: a tool outside the
 * allowed set, command execution that is not off, or a setting Caztor does not write. Null when it is safe; a readable reason otherwise.
 */
export function antigravityDefinitionProblem(text: string): string | null {
  const parsed = parseFrontmatter(text);
  const tools = parsed === null ? undefined : parsed.data["tools"];
  const bracketed = typeof tools === "string" ? /^\[(.*)\]$/.exec(tools.trim()) : null;
  if (parsed === null || bracketed === null) return "The agent definition cannot be read, so Caztor cannot tell what Antigravity may do.";
  const extra = (bracketed[1] ?? "")
    .split(",")
    .map((tool) => tool.trim())
    .filter((tool) => tool !== "" && !ANTIGRAVITY_ALLOWED_TOOLS.includes(tool));
  if (extra.length > 0) return `The agent definition lists tools other than file reading and editing (${extra.join(", ")}).`;
  const unknown = Object.keys(parsed.data).filter((key) => !["name", "description", "tools", "commandExecutionPolicy", "model"].includes(key));
  if (unknown.length > 0) return `The agent definition has settings Caztor does not write (${unknown.join(", ")}).`;
  if (parsed.data["commandExecutionPolicy"] !== "off") return "The agent definition no longer sets commandExecutionPolicy to off, so Antigravity could run commands.";
  return null;
}
