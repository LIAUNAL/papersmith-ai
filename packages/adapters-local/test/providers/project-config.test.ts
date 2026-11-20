import { describe, expect, it } from "vitest";
import { antigravityDefinitionProblem, parseJsonc, scanAntigravityProjectConfig, scanClaudeProjectConfig, scanOpencodeProjectConfig } from "../../src/providers/project-config.ts";
import { MemoryFileSystem } from "../fakes/memory-fs.ts";

const ROOT = "/work/project";
const fsWith = (files: Record<string, string>) => new MemoryFileSystem(Object.fromEntries(Object.entries(files).map(([name, text]) => [`${ROOT}/${name}`, text])));

describe("parseJsonc", () => {
  it("reads comments and trailing commas but keeps text inside strings", () => {
    expect(parseJsonc('{\n // c\n "a": "x // y", /* b */ "b": [1,],\n}')).toEqual({ a: "x // y", b: [1] });
  });

  it("returns null for text that is not JSON", () => {
    expect(parseJsonc("{ nope")).toBeNull();
  });
});

describe("scanOpencodeProjectConfig", () => {
  it("finds nothing in a project without opencode configuration", async () => {
    expect(await scanOpencodeProjectConfig(fsWith({ "main.tex": "x", ".opencode/agents/caztor.md": "---\n---\n" }), ROOT)).toBeNull();
  });

  it("flags a project opencode.json that defines a local MCP server", async () => {
    const found = await scanOpencodeProjectConfig(fsWith({ "opencode.json": '{"mcp":{"x":{"type":"local","command":["touch","/tmp/X"]}}}' }), ROOT);
    expect(found?.files).toEqual(["opencode.json"]);
    expect(found?.fingerprint).toMatch(/^sha256:[0-9a-f]{64}$/);
  });

  it("flags opencode.jsonc, the .opencode config file and a plugin folder", async () => {
    const found = await scanOpencodeProjectConfig(
      fsWith({
        "opencode.jsonc": '{ // x\n "plugin": ["evil"] }',
        ".opencode/opencode.json": '{"formatter":{"x":{"command":["sh"]}}}',
        ".opencode/plugins/p.js": "export const P = async () => ({})",
        ".opencode/tools/t.ts": "export default {}",
      }),
      ROOT,
    );
    expect(found?.files).toEqual(["opencode.jsonc", ".opencode/opencode.json", ".opencode/plugins/", ".opencode/tools/"]);
  });

  it("does not flag a config file that only holds harmless display settings", async () => {
    expect(await scanOpencodeProjectConfig(fsWith({ "opencode.json": '{"$schema":"https://opencode.ai/config.json","theme":"dark"}' }), ROOT)).toBeNull();
  });

  it("flags a config file it cannot read, since it cannot show that it is harmless", async () => {
    expect((await scanOpencodeProjectConfig(fsWith({ "opencode.json": "{ broken" }), ROOT))?.files).toEqual(["opencode.json"]);
  });

  it("ignores the package files opencode installs by itself in .opencode", async () => {
    const files = { ".opencode/package.json": "{}", ".opencode/node_modules/x/index.js": "x", ".opencode/bun.lock": "x" };
    expect(await scanOpencodeProjectConfig(fsWith(files), ROOT)).toBeNull();
  });

  it("changes the fingerprint when a flagged file changes, and keeps it when nothing changed", async () => {
    const before = await scanOpencodeProjectConfig(fsWith({ "opencode.json": '{"mcp":{"a":{}}}' }), ROOT);
    const same = await scanOpencodeProjectConfig(fsWith({ "opencode.json": '{"mcp":{"a":{}}}' }), ROOT);
    const after = await scanOpencodeProjectConfig(fsWith({ "opencode.json": '{"mcp":{"b":{}}}' }), ROOT);
    expect(same?.fingerprint).toBe(before?.fingerprint);
    expect(after?.fingerprint).not.toBe(before?.fingerprint);
  });

  it("also finds the configuration of a parent folder up to the repository root", async () => {
    const fs = new MemoryFileSystem({
      "/work/.git/HEAD": "ref",
      "/work/opencode.json": '{"mcp":{"x":{}}}',
      "/other/opencode.json": '{"mcp":{"x":{}}}',
      [`${ROOT}/main.tex`]: "x",
    });
    expect((await scanOpencodeProjectConfig(fs, ROOT))?.files).toEqual(["../opencode.json"]);
  });
});

describe("scanClaudeProjectConfig", () => {
  it("flags .mcp.json and the project settings files, and nothing else", async () => {
    const found = await scanClaudeProjectConfig(fsWith({ ".mcp.json": "{}", ".claude/settings.json": "{}", ".claude/agents/caztor.md": "x", "main.tex": "x" }), ROOT);
    expect(found?.files).toEqual([".mcp.json", ".claude/settings.json"]);
  });

  it("finds nothing when none of them exists", async () => {
    expect(await scanClaudeProjectConfig(fsWith({ ".claude/agents/caztor.md": "x" }), ROOT)).toBeNull();
  });

  it("changes the fingerprint when a settings file changes", async () => {
    const a = await scanClaudeProjectConfig(fsWith({ ".claude/settings.json": '{"hooks":1}' }), ROOT);
    const b = await scanClaudeProjectConfig(fsWith({ ".claude/settings.json": '{"hooks":2}' }), ROOT);
    expect(a?.fingerprint).not.toBe(b?.fingerprint);
  });
});

describe("scanAntigravityProjectConfig", () => {
  const DEFINITION = "---\nname: caztor\n---\n";

  it("finds nothing when .agents/ holds only Caztor's definition, or does not exist", async () => {
    expect(await scanAntigravityProjectConfig(fsWith({ "main.tex": "x", ".agents/agents/caztor.md": DEFINITION }), ROOT)).toBeNull();
    expect(await scanAntigravityProjectConfig(fsWith({ "main.tex": "x" }), ROOT)).toBeNull();
  });

  it("flags every other file under .agents/, whatever its kind", async () => {
    const found = await scanAntigravityProjectConfig(
      fsWith({ ".agents/agents/caztor.md": DEFINITION, ".agents/hooks.json": "{}", ".agents/mcp_config.json": "{}", ".agents/skills/x/SKILL.md": "s", ".agents/agents/other.md": "o" }),
      ROOT,
    );
    expect(found?.files).toEqual([".agents/hooks.json", ".agents/mcp_config.json", ".agents/agents/other.md", ".agents/skills/x/SKILL.md"]);
    expect(found?.fingerprint).toMatch(/^sha256:[0-9a-f]{64}$/);
  });

  it("changes the fingerprint when a flagged file changes, and not when only caztor.md changes", async () => {
    const base = { ".agents/agents/caztor.md": DEFINITION, ".agents/hooks.json": "{}" };
    const a = await scanAntigravityProjectConfig(fsWith(base), ROOT);
    const b = await scanAntigravityProjectConfig(fsWith({ ...base, ".agents/hooks.json": '{"x":1}' }), ROOT);
    const c = await scanAntigravityProjectConfig(fsWith({ ...base, ".agents/agents/caztor.md": "edited" }), ROOT);
    expect(b?.fingerprint).not.toBe(a?.fingerprint);
    expect(c?.fingerprint).toBe(a?.fingerprint);
  });

  it("flags .agents itself when it is a link, and a link inside it", async () => {
    const linked = fsWith({ "main.tex": "x" });
    linked.symlink("/elsewhere", `${ROOT}/.agents`);
    expect((await scanAntigravityProjectConfig(linked, ROOT))?.files).toEqual([".agents"]);
    const inner = fsWith({ ".agents/agents/caztor.md": DEFINITION });
    inner.symlink("/elsewhere/hooks.json", `${ROOT}/.agents/hooks.json`);
    expect((await scanAntigravityProjectConfig(inner, ROOT))?.files).toEqual([".agents/hooks.json"]);
  });
});

describe("antigravityDefinitionProblem", () => {
  const file = (tools: string, policy = "off") => `---\nname: caztor\ndescription: x\ntools: ${tools}\ncommandExecutionPolicy: ${policy}\nmodel: inherit\n---\nbody\n`;

  it("accepts a definition with file tools only and commands off", () => {
    expect(antigravityDefinitionProblem(file("[view_file, list_dir, find_by_name, grep_search, replace_file_content, write_to_file]"))).toBeNull();
    expect(antigravityDefinitionProblem(file("[view_file]"))).toBeNull();
  });

  it("names a tool outside the allowed set", () => {
    expect(antigravityDefinitionProblem(file("[view_file, run_command]"))).toContain("run_command");
  });

  it("names a command execution policy that is not off", () => {
    expect(antigravityDefinitionProblem(file("[view_file]", "auto"))).toContain("commandExecutionPolicy");
  });

  it("reports a definition that cannot be read", () => {
    expect(antigravityDefinitionProblem("not a definition")).toContain("cannot be read");
    expect(antigravityDefinitionProblem(file("view_file"))).toContain("cannot be read");
  });
});

describe("a configuration file that is a link", () => {
  it("is fingerprinted by what it points to, so a change behind the link needs confirming again", async () => {
    const fs = fsWith({ "elsewhere/settings.json": "{}" });
    await fs.mkdir(`${ROOT}/.claude`, { recursive: true });
    fs.symlink(`${ROOT}/elsewhere/settings.json`, `${ROOT}/.claude/settings.json`);
    const before = await scanClaudeProjectConfig(fs, ROOT);
    await fs.writeFile(`${ROOT}/elsewhere/settings.json`, new TextEncoder().encode('{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"x"}]}]}}'));
    const after = await scanClaudeProjectConfig(fs, ROOT);
    expect(before?.files).toEqual([".claude/settings.json"]);
    expect(after?.fingerprint).not.toBe(before?.fingerprint);
  });
});

describe("a configuration folder reached through a link", () => {
  const change = async (fs: MemoryFileSystem, path: string, text: string) => fs.writeFile(`${ROOT}/${path}`, new TextEncoder().encode(text));

  it("is fingerprinted by what is inside it, for .agents", async () => {
    const fs = fsWith({ "ad/x.md": "a" });
    fs.symlink(`${ROOT}/ad`, `${ROOT}/.agents`);
    const before = await scanAntigravityProjectConfig(fs, ROOT);
    await change(fs, "ad/x.md", "evil");
    expect((await scanAntigravityProjectConfig(fs, ROOT))?.fingerprint).not.toBe(before?.fingerprint);
  });

  it("is fingerprinted by what is inside it, for an opencode plugin folder and a nested tool folder", async () => {
    const fs = fsWith({ "pd/p.js": "a", "pd2/t.js": "a", ".opencode/tool/keep.js": "k" });
    fs.symlink(`${ROOT}/pd`, `${ROOT}/.opencode/plugin`);
    fs.symlink(`${ROOT}/pd2`, `${ROOT}/.opencode/tool/sub`);
    const before = await scanOpencodeProjectConfig(fs, ROOT);
    expect(before?.files).toEqual(expect.arrayContaining([".opencode/plugin/", ".opencode/tool/"]));
    await change(fs, "pd/p.js", "evil");
    const afterPlugin = await scanOpencodeProjectConfig(fs, ROOT);
    expect(afterPlugin?.fingerprint).not.toBe(before?.fingerprint);
    await change(fs, "pd2/t.js", "evil");
    expect((await scanOpencodeProjectConfig(fs, ROOT))?.fingerprint).not.toBe(afterPlugin?.fingerprint);
  });

  it("does not loop on a link that points back up", async () => {
    const fs = fsWith({ ".opencode/plugin/p.js": "a" });
    fs.symlink(`${ROOT}/.opencode`, `${ROOT}/.opencode/plugin/up`);
    expect((await scanOpencodeProjectConfig(fs, ROOT))?.files).toEqual([".opencode/plugin/"]);
  });
});
