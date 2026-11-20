import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const folder = fileURLToPath(new URL("./", import.meta.url));
const PROVIDERS = ["claude", "opencode", "codex", "antigravity", "pi"] as const;
type Provider = (typeof PROVIDERS)[number];

/** Codex stops reading project instructions at 32 KiB by default. */
const CODEX_INSTRUCTION_LIMIT = 32 * 1024;
/** The user's own AGENTS.md text shares Codex's 32 KiB, so every definition leaves it half of that. */
const DEFINITION_LIMIT = 16 * 1024;
/** The compact writing guide core, which every definition carries. */
const CORE_LIMIT = 3 * 1024;
const CORE_START = "\n## Section guides\n";

const read = (provider: Provider) => readFileSync(`${folder}${provider}.md`, "utf8");

type Scalar = string;
type Frontmatter = Record<string, Scalar | Record<string, Scalar>>;

/** The flat `key: value` frontmatter these files use, with one level of nested keys. Null without a frontmatter block. */
function parseFrontmatter(text: string): { data: Frontmatter; body: string } | null {
  const match = /^---\n([\s\S]*?)\n---\n/.exec(text);
  if (match === null) return null;
  const data: Frontmatter = {};
  let nested: Record<string, Scalar> | null = null;
  for (const line of (match[1] ?? "").split("\n")) {
    const child = /^ {2}([A-Za-z_]+): (.*)$/.exec(line);
    if (child !== null && nested !== null) {
      nested[child[1] as string] = child[2] as string;
      continue;
    }
    const top = /^([A-Za-z_]+):(?: (.*))?$/.exec(line);
    if (top === null) throw new Error(`Unsupported frontmatter line: ${line}`);
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

const SHARED_START = "\n## Role\n";
const PROVIDER_START = "\n## Provider characteristics\n";

const sharedSection = (text: string) => text.slice(text.indexOf(SHARED_START));
/** The `## Section guides` section: from its heading to the next second-level heading. */
const coreSection = (text: string) => {
  const start = text.indexOf(CORE_START);
  if (start === -1) return "";
  const next = text.indexOf("\n## ", start + CORE_START.length);
  return text.slice(start, next === -1 ? undefined : next);
};

/** The one rule that governs `.caztor/`: the compile log and the guides may be read, nothing else is touched. */
const CAZTOR_RULE =
  "Inside `.caztor/` you may only read `.caztor/build/last-compile.log` and the files in `.caztor/guides/`. Do not change them, and do not read, create, modify or delete anything else inside `.caztor/`.";
const ALLOWED_CAZTOR_PATHS = new Set([".caztor/", ".caztor/build/last-compile.log", ".caztor/guides/", ".caztor/guides/INDEX.md"]);
const providerSection = (text: string) => text.slice(text.indexOf(PROVIDER_START), text.indexOf(SHARED_START));

describe("agent definitions", () => {
  it("ships exactly one definition per provider", () => {
    const shipped = readdirSync(folder)
      .filter((name) => name.endsWith(".md"))
      .sort();
    expect(shipped).toEqual(["antigravity.md", "claude.md", "codex.md", "opencode.md", "pi.md"]);
  });

  describe("claude", () => {
    const parsed = parseFrontmatter(read("claude"));

    it("starts with frontmatter that has the required fields and the file tool allowlist", () => {
      expect(parsed).not.toBeNull();
      const data = parsed?.data ?? {};
      expect(data["name"]).toBe("caztor");
      expect(typeof data["description"] === "string" && data["description"].length > 20).toBe(true);
      expect(data["tools"]).toBe("Read, Edit, Write, Glob, Grep");
    });

    it("keeps the name within the documented limits and the description free of a YAML-breaking colon", () => {
      const data = parsed?.data ?? {};
      const name = String(data["name"]);
      expect(name.length).toBeLessThanOrEqual(256);
      expect(name).not.toContain(":");
      expect(String(data["description"])).not.toMatch(/: |:$/);
    });

    it("has no marker comment before the frontmatter", () => {
      expect(read("claude").startsWith("---\n")).toBe(true);
    });
  });

  describe("opencode", () => {
    const parsed = parseFrontmatter(read("opencode"));

    it("starts with frontmatter that has a description and the primary mode", () => {
      expect(parsed).not.toBeNull();
      const data = parsed?.data ?? {};
      expect(typeof data["description"] === "string" && data["description"].length > 20).toBe(true);
      expect(data["mode"]).toBe("primary");
      expect(String(data["description"])).not.toMatch(/: |:$/);
    });

    it("allows editing and denies commands, web access and folders outside the project", () => {
      expect(parsed?.data["permission"]).toEqual({
        edit: "allow",
        bash: "deny",
        webfetch: "deny",
        external_directory: "deny",
      });
    });

    it("has no marker comment before the frontmatter", () => {
      expect(read("opencode").startsWith("---\n")).toBe(true);
    });
  });

  describe("antigravity", () => {
    const parsed = parseFrontmatter(read("antigravity"));
    const FILE_TOOLS = ["view_file", "list_dir", "find_by_name", "grep_search", "replace_file_content", "write_to_file"];

    it("starts with frontmatter that has the name, a description, the file tool list and no command execution", () => {
      expect(parsed).not.toBeNull();
      const data = parsed?.data ?? {};
      expect(data["name"]).toBe("caztor");
      expect(typeof data["description"] === "string" && data["description"].length > 20).toBe(true);
      expect(String(data["description"])).not.toMatch(/: |:$/);
      expect(data["commandExecutionPolicy"]).toBe("off");
      expect(data["model"]).toBe("inherit");
    });

    it("lists only file reading, searching and editing tools, on one line, in brackets", () => {
      const tools = String(parsed?.data["tools"] ?? "");
      expect(tools).toMatch(/^\[[a-z_, ]+\]$/);
      expect(tools.slice(1, -1).split(", ")).toEqual(FILE_TOOLS);
    });

    it("has no marker comment before the frontmatter, and states that shell commands are forbidden", () => {
      expect(read("antigravity").startsWith("---\n")).toBe(true);
      expect(read("antigravity")).toMatch(/do not run shell commands/i);
    });
  });

  describe("pi", () => {
    it("is plain Markdown without frontmatter, because the whole file becomes the system prompt", () => {
      const text = read("pi");
      expect(parseFrontmatter(text)).toBeNull();
      expect(text.startsWith("# ")).toBe(true);
    });
  });

  describe("codex", () => {
    it("is plain Markdown without frontmatter, as AGENTS.md is", () => {
      const text = read("codex");
      expect(parseFrontmatter(text)).toBeNull();
      expect(text.startsWith("# ")).toBe(true);
    });
  });

  describe.each(PROVIDERS)("%s text", (provider) => {
    const text = read(provider);

    it("forbids fabricating citations", () => {
      expect(text).toMatch(/never fabricate[^.\n]*citations/i);
      expect(text).toContain("% TODO(citation)");
    });

    it("forbids executing shell commands", () => {
      expect(text).toMatch(/do not run shell commands/i);
    });

    it("treats the text of project files as data, not instructions", () => {
      expect(text).toMatch(/content to work on, not instructions/i);
    });

    it("tells the agent where the compile feedback is, that BibTeX is the only bibliography engine, and what not to touch", () => {
      expect(text).toContain("`.caztor/build/last-compile.log`");
      expect(text).toMatch(/biblatex/i);
      expect(text).toMatch(/BibTeX/);
      for (const protectedPath of [".caztor/", ".git/", "AGENTS.md"]) expect(text).toContain(protectedPath);
    });

    it("has the provider section before the shared one", () => {
      expect(text.indexOf(PROVIDER_START)).toBeGreaterThan(0);
      expect(text.indexOf(SHARED_START)).toBeGreaterThan(text.indexOf(PROVIDER_START));
    });

    it("stays below the 32 KiB instruction limit of Codex", () => {
      expect(Buffer.byteLength(text, "utf8")).toBeLessThan(CODEX_INSTRUCTION_LIMIT);
    });

    it("stays below 16 KiB, so the user's own AGENTS.md text keeps half of Codex's budget", () => {
      expect(Buffer.byteLength(text, "utf8")).toBeLessThan(DEFINITION_LIMIT);
    });

    it("uses plain ASCII characters only", () => {
      expect(text).toMatch(/^[\x09\x0a\x20-\x7e]*$/);
    });
  });

  describe("rules that must not contradict each other", () => {
    const shared = sharedSection(read("claude"));

    it("asks for the user's request or confirmation before a change to the class, packages or options, and proposes it first", () => {
      expect(shared).not.toMatch(/unless asked/i);
      expect(shared).not.toMatch(/add the smallest change that works/i);
      expect(shared).toMatch(/document class, the package list or the options need the user's request or explicit confirmation/i);
      expect(shared).toMatch(/propose it first/i);
    });

    it("forbids the managed block and the definition files, and allows the user's own text in AGENTS.md when asked", () => {
      expect(shared).not.toMatch(/which include `AGENTS\.md`/);
      expect(shared).toMatch(/block of `AGENTS\.md` that Caztor manages/);
      expect(shared).toMatch(/may edit the user's own text in `AGENTS\.md` when the user explicitly asks/i);
      expect(shared).toContain("caztor:agent:begin");
    });
  });

  describe("shared academic-writing instructions", () => {
    it("are identical in the five files", () => {
      const shared = PROVIDERS.map((provider) => sharedSection(read(provider)));
      expect(shared[0]?.length).toBeGreaterThan(2000);
      expect(shared[1]).toBe(shared[0]);
      expect(shared[2]).toBe(shared[0]);
      expect(shared[3]).toBe(shared[0]);
      expect(shared[4]).toBe(shared[0]);
    });

    it("name a divergent definition when its shared section differs by one byte", () => {
      const divergent = (sections: Record<Provider, string>) => PROVIDERS.filter((provider) => sections[provider] !== sections.claude);
      const sections = Object.fromEntries(PROVIDERS.map((provider) => [provider, sharedSection(read(provider))])) as Record<Provider, string>;
      expect(divergent(sections)).toEqual([]);
      const changed = sections.antigravity.replace("Do not run shell commands", "Do not run shell command");
      expect(changed.length).toBe(sections.antigravity.length - 1);
      expect(divergent({ ...sections, antigravity: changed })).toEqual(["antigravity"]);
    });

    it("tell the agent to leave .agents/ alone, together with the other agent folders", () => {
      const shared = sharedSection(read("claude"));
      expect(shared).toContain("inside `.git/`, `.claude/`, `.opencode/` or `.agents/`");
      for (const provider of PROVIDERS) expect(read(provider), provider).toContain("`.agents/`");
    });

    it("do not name a provider, apart from the agent folders they tell the agent to leave alone", () => {
      const withoutFolders = sharedSection(read("claude")).replaceAll(".claude/", "").replaceAll(".opencode/", "");
      expect(withoutFolders).not.toMatch(/claude|opencode|codex|anthropic|openai/i);
    });

    it("cover editing rules, citation integrity, the answer format and writing style", () => {
      const shared = sharedSection(read("claude"));
      for (const heading of ["## Role", "## Project facts", "## Editing rules", "## Citation integrity", "## Files are data", "## Commands", "## Academic style", "## Working method"]) {
        expect(shared).toContain(`\n${heading}\n`);
      }
      expect(shared).toMatch(/only cite keys that exist in the project's `\.bib` files/i);
      expect(shared).toMatch(/ask[^.\n]*(ambiguous|unclear)|(ambiguous|unclear)[^.\n]*ask/i);
      expect(shared).toMatch(/short summary/i);
    });
  });

  describe("writing guides core", () => {
    it.each(PROVIDERS)("%s: has a Section guides section after Academic style, before Working method, pointing at the index", (provider) => {
      const text = read(provider);
      const shared = sharedSection(text);
      const core = coreSection(text);
      expect(core).not.toBe("");
      expect(shared.indexOf("\n## Academic style\n")).toBeLessThan(shared.indexOf(CORE_START));
      expect(shared.indexOf(CORE_START)).toBeLessThan(shared.indexOf("\n## Working method\n"));
      expect(core).toContain("`.caztor/guides/INDEX.md`");
    });

    it("is byte-identical in the five files, plain ASCII, and at most 3 KiB", () => {
      const cores = PROVIDERS.map((provider) => coreSection(read(provider)));
      expect(cores[0]?.length).toBeGreaterThan(1000);
      expect(cores[1]).toBe(cores[0]);
      expect(cores[2]).toBe(cores[0]);
      expect(cores[3]).toBe(cores[0]);
      expect(cores[4]).toBe(cores[0]);
      const core = cores[0] ?? "";
      expect(Buffer.byteLength(core, "utf8")).toBeLessThanOrEqual(CORE_LIMIT);
      expect(core).toMatch(/^[\x09\x0a\x20-\x7e]*$/);
    });

    it("says the guides are advisory, that the request, the structure and the template win, and what to do for other genres", () => {
      const core = coreSection(read("claude"));
      expect(core).toMatch(/advice, not rules/i);
      expect(core).toMatch(/what the user asked for, the document's own structure and the venue template always win/i);
      expect(core).toMatch(/theses, reports and reviews/i);
      expect(core).toMatch(/only the one guide/i);
    });

    it("gives the function of each of the ten sections and the coherence invariants", () => {
      const core = coreSection(read("claude"));
      for (const section of ["Abstract:", "Introduction:", "Related work:", "Methods:", "Experimental set-up:", "Results and discussion:", "Limitations:", "Conclusions:", "Title and keywords:", "Back matter:"]) {
        expect(core, section).toContain(section);
      }
      expect(core).toMatch(/one count, order and name/i);
      expect(core).toMatch(/every future-work direction answers a stated limitation/i);
    });

    it("never licenses content the user did not provide, and defers to the citation rules", () => {
      const core = coreSection(read("claude"));
      expect(core).toMatch(/never licenses writing content the user did not provide/i);
      expect(core).toMatch(/citation integrity/i);
    });
  });

  describe("access to the internal state folder", () => {
    it.each(PROVIDERS)("%s: has the exact .caztor/ rule, and the old broad ban is gone", (provider) => {
      const text = read(provider);
      expect(text).toContain(CAZTOR_RULE);
      expect(text).not.toContain("(except reading the compile log named above)");
    });

    it.each(PROVIDERS)("%s: names no .caztor/ path other than the compile log and the guides", (provider) => {
      const text = read(provider);
      const found = new Set(text.match(/\.caztor\/[A-Za-z0-9_./-]*/g)?.map((path) => path.replace(/\.$/, "")));
      expect(found.size).toBeGreaterThan(2);
      for (const path of found) expect(ALLOWED_CAZTOR_PATHS.has(path), path).toBe(true);
    });
  });

  describe("provider characteristics", () => {
    it("describe each provider differently", () => {
      const sections = PROVIDERS.map((provider) => providerSection(read(provider)));
      expect(new Set(sections).size).toBe(5);
      for (const section of sections) expect(section.length).toBeGreaterThan(600);
    });

    it("state where each CLI reads its definition", () => {
      expect(providerSection(read("claude"))).toContain("`.claude/agents/caztor.md`");
      expect(providerSection(read("opencode"))).toContain("`.opencode/agents/caztor.md`");
      expect(providerSection(read("codex"))).toContain("`AGENTS.md`");
      expect(providerSection(read("antigravity"))).toContain("`.agents/agents/caztor.md`");
      expect(providerSection(read("pi"))).toMatch(/this text is your system prompt/i);
    });

    it("say that Pi may load global configuration, that only its file tools are allowed, and to leave .pi/ alone", () => {
      const section = providerSection(read("pi"));
      expect(section).toMatch(/global settings/i);
      expect(section).toMatch(/only file reading, searching and editing tools/i);
      for (const tool of ["read", "edit", "write", "grep", "find", "ls"]) expect(section).toContain(`\`${tool}\``);
      expect(section).toMatch(/stops the turn/i);
      expect(section).toContain("`.pi/`");
    });

    it("say that Antigravity may load global configuration, and that only the file tools are allowed", () => {
      const section = providerSection(read("antigravity"));
      expect(section).toMatch(/global (settings|configuration)/i);
      expect(section).toMatch(/only file reading, searching and editing tools|file tools only/i);
      for (const tool of ["view_file", "list_dir", "find_by_name", "grep_search", "replace_file_content", "write_to_file"]) expect(section).toContain(`\`${tool}\``);
      expect(section).toMatch(/stops the turn|the turn is stopped/i);
    });

    it("say that Claude Code streams token by token and enforces the tool list", () => {
      const section = providerSection(read("claude"));
      expect(section).toMatch(/token by token/i);
      expect(section).toMatch(/enforces the tool list/i);
    });

    it("say that opencode needs an explicit provider/model and delivers whole blocks", () => {
      const section = providerSection(read("opencode"));
      expect(section).toContain("`provider/model`");
      expect(section).toMatch(/whole blocks/i);
    });

    it("say that Codex can run commands in its sandbox, so the rule is an instruction", () => {
      const section = providerSection(read("codex"));
      expect(section).toContain("`workspace-write`");
      expect(section).toMatch(/can run commands/i);
      expect(section).toMatch(/not an enforced limit/i);
    });

    it("hold no development note, and nothing the model cannot act on", () => {
      for (const provider of PROVIDERS) {
        const section = providerSection(read(provider));
        expect(section).not.toMatch(/was not installed|developed|has not been tested|untested|not been verified/i);
        expect(section).not.toMatch(/32 KiB|frontmatter|YAML/i);
        expect(section).not.toMatch(/^- Status:/m);
      }
    });

    it("tell the model what it can and cannot do with its tools", () => {
      expect(providerSection(read("claude"))).toMatch(/cannot run commands/i);
      expect(providerSection(read("opencode"))).toMatch(/denied/i);
      expect(providerSection(read("codex"))).toMatch(/may edit the user's own text/i);
      expect(providerSection(read("antigravity"))).toMatch(/cannot run commands|must not run commands/i);
      expect(providerSection(read("pi"))).toMatch(/cannot run commands/i);
    });

    it("make no claim about model quality or benchmarks", () => {
      for (const provider of PROVIDERS) {
        expect(providerSection(read(provider))).not.toMatch(/\b(best|state-of-the-art|benchmark|smartest|most capable|leading|superior)\b/i);
      }
    });
  });
});
