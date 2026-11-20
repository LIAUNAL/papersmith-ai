import type { ProjectAgent, ProjectAgentsPort } from "@caztor/core";
import { parseFrontmatter } from "./agent-definition.ts";
import type { FileSystem } from "./infra.ts";

/** Where a project keeps its own agents: the Claude Code layout PaperSmith writes for its workspaces. */
export const PROJECT_AGENTS_DIR = ".claude/agents";
const AGENT_NAME = /^[a-z0-9][a-z0-9-]{0,63}$/;
const MAX_AGENT_BYTES = 256 * 1024;

const unquote = (value: string) => (value.length >= 2 && value.startsWith('"') && value.endsWith('"') ? value.slice(1, -1) : value);

/**
 * Reads the project's own agent definitions, fresh on every call, so the chat offers what the workspace holds now.
 * Caztor's own agent and anything that is not a plain Markdown file named after its agent are left out.
 */
export function createProjectAgents(options: { fs: FileSystem; root: string }): ProjectAgentsPort {
  const { fs, root } = options;
  return {
    async list(): Promise<ProjectAgent[]> {
      const dir = `${root}/${PROJECT_AGENTS_DIR}`;
      // PaperSmith links .claude/skills to the workspace's skills/. Caztor's agent does not read .claude/, so the
      // instructions name the same files through skills/ instead, when the link really leads there.
      const linked = await fs.realpath(`${root}/.claude/skills`).catch(() => null);
      const realSkills = await fs.realpath(`${root}/skills`).catch(() => null);
      const skillsLinked = linked !== null && realSkills !== null && linked === realSkills;
      const entries = await fs.readdir(dir).catch(() => []);
      const agents: ProjectAgent[] = [];
      for (const entry of entries) {
        if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith(".md")) continue;
        const name = entry.name.slice(0, -3);
        if (name === "caztor" || !AGENT_NAME.test(name)) continue;
        const file = `${dir}/${entry.name}`;
        const stats = await fs.lstat(file).catch(() => null);
        if (stats === null || !stats.isFile() || stats.size > MAX_AGENT_BYTES) continue;
        const parsed = parseFrontmatter(new TextDecoder().decode(await fs.readFile(file)));
        const description = parsed?.data["description"];
        if (parsed === null || parsed.data["name"] !== name || typeof description !== "string" || description === "") continue;
        const body = parsed.body.trim();
        agents.push({ name, description: unquote(description), prompt: skillsLinked ? body.replaceAll(".claude/skills/", "skills/") : body, file: `${PROJECT_AGENTS_DIR}/${entry.name}` });
      }
      return agents.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    },
    async sources(): Promise<string[]> {
      const isFile = async (path: string) => (await fs.lstat(`${root}/${path}`).catch(() => null))?.isFile() === true;
      /** The file of `dir` matching `pattern` with the highest revision number, captured by its first group. */
      const latest = async (dir: string, pattern: RegExp): Promise<string | null> => {
        const entries = await fs.readdir(`${root}/${dir}`).catch(() => []);
        let best: { name: string; revision: number } | null = null;
        for (const entry of entries) {
          const match = pattern.exec(entry.name);
          if (!entry.isFile() || entry.isSymbolicLink() || match === null) continue;
          const revision = Number(match[1]);
          if (best === null || revision > best.revision) best = { name: entry.name, revision };
        }
        return best === null ? null : `${dir}/${best.name}`;
      };
      const found = [
        await latest("proposals", /^research-concept-(?:.+-)?r(\d+)\.md$/),
        (await isFile(".papersmith/model_spec.json")) ? ".papersmith/model_spec.json" : null,
        await latest("experiments", /^experiments-.+-v(\d+)\.md$/),
        (await isFile("paper/main.tex")) ? "paper/main.tex" : null,
      ];
      return found.filter((path): path is string => path !== null);
    },
  };
}
