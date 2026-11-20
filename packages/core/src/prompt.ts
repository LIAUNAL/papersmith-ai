import type { ProjectAgent, RelPath } from "./ports.ts";

/** The first line of the note that tells the agent about an undo; also how a test or a reader recognises it. */
export const REVERT_NOTE_HEADER = "[Note from Caztor: the user undid your previous changes. These files were restored to their earlier content:";
/** Files named in the note; the rest are counted. */
export const MAX_NOTE_FILES = 30;

/** A file name goes on one line of the note, so it cannot add lines of its own. */
const oneLine = (path: string) => path.replace(/\s+/g, " ").trim();

/**
 * The message given to the agent: the user's text, preceded by a note naming the files an undo reverted since the
 * agent last worked. Without an undo it is the user's text, unchanged.
 */
export function buildPrompt(userText: string, revertedFiles: readonly RelPath[]): string {
  if (revertedFiles.length === 0) return userText;
  const named = revertedFiles.slice(0, MAX_NOTE_FILES).map((path) => `- ${oneLine(path)}`);
  const more = revertedFiles.length - named.length;
  const lines = [
    REVERT_NOTE_HEADER,
    ...named,
    ...(more > 0 ? [`- and ${more} more file${more === 1 ? "" : "s"}`] : []),
    "Do not assume your earlier edits to them still exist; read them again before you change them.]",
  ];
  return `${lines.join("\n")}\n\n${userText}`;
}

/** How the note that replaces a PaperSmith dashboard panel's view begins. */
export const AGENT_CONTEXT_HEADER = "[You run in Caztor's chat, not in a PaperSmith dashboard panel: no panel view, message mode or decision area reaches you.";

/**
 * PaperSmith's dashboard panels hand an agent their own view (the paper's mathematics, the novelty card, the
 * experiments protocol). Caztor's chat has no such panel, so the agent is told which workspace files hold it.
 */
export function agentContextNote(sources: readonly string[]): string {
  const where =
    sources.length === 0
      ? "This workspace holds none of the files a panel reads (proposals/, .papersmith/model_spec.json, experiments/, paper/main.tex); say so when you need them."
      : `Where your instructions expect what a panel supplies, read it from these workspace files, by these exact paths (a file search may not list them): ${sources.map((path) => `\`${path}\``).join(", ")}. Never invent what they do not hold.`;
  return `${AGENT_CONTEXT_HEADER} ${where} Choose the mode and the decision area that fit the user's message.]`;
}

/**
 * A message that starts with `/<name>` for one of the project's own agents is run as that agent: its instructions come
 * first, then the user's message. The turn keeps Caztor's own rules and tools; the instructions only steer it. Any
 * other message is returned unchanged.
 */
export function expandAgentCommand(userText: string, agents: readonly ProjectAgent[], sources: readonly string[] = []): string {
  const match = /^\/([a-z0-9][a-z0-9-]*)(?:[ \t]+([\s\S]*))?$/.exec(userText);
  const agent = match === null ? undefined : agents.find((candidate) => candidate.name === match[1]);
  if (match === null || agent === undefined) return userText;
  const message = (match[2] ?? "").trim();
  return [
    `[For this message, act as the PaperSmith agent "${agent.name}" of this workspace, defined in ${agent.file}. Its instructions follow; files and skills they name are read from the workspace. Caztor's own rules and tools still apply. When you explain a passage of the paper, quote it word for word from the paper's LaTeX source in a \`>\` block, so the editor can highlight it.]`,
    agentContextNote(sources),
    agent.prompt,
    "[The user's message]",
    message === "" ? "(No message yet. Do not read files or start tutoring: reply with one short sentence saying you are ready for the user's question.)" : message,
  ].join("\n\n");
}
