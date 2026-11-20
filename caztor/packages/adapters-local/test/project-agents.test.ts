import { mkdirSync, mkdtempSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { nodeFileSystem } from "../src/node-infra.ts";
import { createProjectAgents } from "../src/project-agents.ts";

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function project(): string {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-agents-")));
  dirs.push(root);
  mkdirSync(join(root, ".claude", "agents"), { recursive: true });
  return root;
}

const agent = (name: string, description: string, body = "Do the thing.") => `---\nname: ${name}\ndescription: ${description}\ntools: Read, Glob, Grep\nmodel: sonnet\n---\n\n${body}\n`;

describe("the project's own agents (PaperSmith's .claude/agents)", () => {
  it("lists each agent by name, with its description unquoted and its body as the prompt, in name order, without Caztor's own", async () => {
    const root = project();
    writeFileSync(join(root, ".claude/agents/math-tutor.md"), agent("math-tutor", '"Socratic math tutor."', "# Math Tutor\nAsk one question."));
    writeFileSync(join(root, ".claude/agents/experiments-tutor.md"), agent("experiments-tutor", "Experiments tutor."));
    writeFileSync(join(root, ".claude/agents/caztor.md"), agent("caztor", "Caztor itself."));
    expect(await createProjectAgents({ fs: nodeFileSystem, root }).list()).toEqual([
      { name: "experiments-tutor", description: "Experiments tutor.", prompt: "Do the thing.", file: ".claude/agents/experiments-tutor.md" },
      { name: "math-tutor", description: "Socratic math tutor.", prompt: "# Math Tutor\nAsk one question.", file: ".claude/agents/math-tutor.md" },
    ]);
  });

  it("skips files it cannot use: no frontmatter, a name that differs from the file or is not a plain name, links, and other extensions", async () => {
    const root = project();
    writeFileSync(join(root, ".claude/agents/plain.md"), "no frontmatter");
    writeFileSync(join(root, ".claude/agents/other.md"), agent("someone-else", "Mismatch."));
    writeFileSync(join(root, ".claude/agents/notes.txt"), agent("notes", "Not markdown."));
    writeFileSync(join(root, "elsewhere.md"), agent("linked", "Linked."));
    symlinkSync(join(root, "elsewhere.md"), join(root, ".claude/agents/linked.md"));
    expect(await createProjectAgents({ fs: nodeFileSystem, root }).list()).toEqual([]);
  });

  it("lists nothing in a project without the folder", async () => {
    const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-agents-")));
    dirs.push(root);
    expect(await createProjectAgents({ fs: nodeFileSystem, root }).list()).toEqual([]);
  });

  it("points skill paths through .claude/skills at the project's skills folder when that is where the link leads", async () => {
    const root = project();
    mkdirSync(join(root, "skills/math-tutor"), { recursive: true });
    symlinkSync("../skills", join(root, ".claude/skills"));
    writeFileSync(join(root, ".claude/agents/math-tutor.md"), agent("math-tutor", "Tutor.", "Skill: `.claude/skills/math-tutor/SKILL.md`. Load it."));
    const [listed] = await createProjectAgents({ fs: nodeFileSystem, root }).list();
    expect(listed?.prompt).toBe("Skill: `skills/math-tutor/SKILL.md`. Load it.");
  });

  it("leaves skill paths alone when .claude/skills is not the project's skills folder", async () => {
    const root = project();
    mkdirSync(join(root, ".claude/skills/math-tutor"), { recursive: true });
    writeFileSync(join(root, ".claude/agents/math-tutor.md"), agent("math-tutor", "Tutor.", "Skill: `.claude/skills/math-tutor/SKILL.md`."));
    const [listed] = await createProjectAgents({ fs: nodeFileSystem, root }).list();
    expect(listed?.prompt).toBe("Skill: `.claude/skills/math-tutor/SKILL.md`.");
  });

  it("names the files a panel would hand its agent, the latest revision of each, and only those that exist", async () => {
    const root = project();
    for (const dir of ["proposals", "experiments", "paper", ".papersmith"]) mkdirSync(join(root, dir));
    for (const file of ["research-concept-spin-r9.md", "research-concept-spin-r15.md", "research-concept-spin-r15.graph.html", "notes.md"]) writeFileSync(join(root, "proposals", file), "");
    for (const file of ["experiments-validation-v03.md", "experiments-validation-v19.md"]) writeFileSync(join(root, "experiments", file), "");
    writeFileSync(join(root, ".papersmith", "model_spec.json"), "{}");
    writeFileSync(join(root, "paper", "main.tex"), "");
    expect(await createProjectAgents({ fs: nodeFileSystem, root }).sources!()).toEqual([
      "proposals/research-concept-spin-r15.md",
      ".papersmith/model_spec.json",
      "experiments/experiments-validation-v19.md",
      "paper/main.tex",
    ]);
    rmSync(join(root, "paper", "main.tex"));
    rmSync(join(root, "experiments"), { recursive: true });
    expect(await createProjectAgents({ fs: nodeFileSystem, root }).sources!()).toEqual(["proposals/research-concept-spin-r15.md", ".papersmith/model_spec.json"]);
  });
});
