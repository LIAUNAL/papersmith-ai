/**
 * The PaperSmith agents the chat offers as switches. They are the ones that hold a conversation about the paper
 * that is open; the workspace's other agents are stages of PaperSmith's flow and run from its dashboard.
 * A message to an active agent travels as `/<name> message`, which the server runs as that agent.
 */

export interface ChatAgent {
  name: string;
  label: string;
  /** Shown as its own button; the others are in the "More" menu. */
  primary: boolean;
}

export const CHAT_AGENTS: readonly ChatAgent[] = [
  { name: "math-tutor", label: "Math tutor", primary: true },
  { name: "experiments-tutor", label: "Experiments tutor", primary: true },
  { name: "paper-reviewer", label: "Paper reviewer", primary: false },
  { name: "ai-auditor", label: "Writing auditor", primary: false },
];

/** The message sent for `text` while `agent` is active. */
export function addressed(agent: string, text: string): string {
  const message = text.trim();
  return message === "" ? `/${agent}` : `/${agent} ${message}`;
}

/** A sent prompt read back: which chat agent it went to, if any, and the user's own words. */
export function splitAddressed(prompt: string): { agent: ChatAgent | null; text: string } {
  const match = /^\/([a-z0-9][a-z0-9-]*)(?:[ \t]+([\s\S]*))?$/.exec(prompt);
  const agent = match === null ? undefined : CHAT_AGENTS.find((candidate) => candidate.name === match[1]);
  return agent === undefined ? { agent: null, text: prompt } : { agent, text: (match![2] ?? "").trim() };
}
