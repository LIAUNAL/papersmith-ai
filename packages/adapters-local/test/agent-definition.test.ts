import type { ContentHash } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { parseAgentFile } from "../src/agent-definition.ts";

const hash = `sha256:${"a".repeat(64)}` as ContentHash;
const file = (tools: string) => `---\nname: caztor\ndescription: A writing agent\ntools: ${tools}\ncommandExecutionPolicy: off\nmodel: inherit\n---\n\nBody text.\n`;

describe("parseAgentFile for antigravity", () => {
  it("splits the bracketed tool list", () => {
    expect(parseAgentFile("antigravity", file("[view_file, list_dir, write_to_file]"), hash)).toEqual({
      hash,
      name: "caztor",
      description: "A writing agent",
      prompt: "Body text.",
      tools: ["view_file", "list_dir", "write_to_file"],
    });
  });

  it("reads a list without spaces and an empty list", () => {
    expect(parseAgentFile("antigravity", file("[view_file,grep_search]"), hash)?.tools).toEqual(["view_file", "grep_search"]);
    expect(parseAgentFile("antigravity", file("[]"), hash)?.tools).toEqual([]);
  });

  it("refuses a file without the name, a description, or a bracketed list", () => {
    expect(parseAgentFile("antigravity", file("view_file, list_dir"), hash)).toBeNull();
    expect(parseAgentFile("antigravity", file("[view_file]").replace("name: caztor", "name: other"), hash)).toBeNull();
    expect(parseAgentFile("antigravity", "no frontmatter", hash)).toBeNull();
  });
});

describe("parseAgentFile for pi", () => {
  it("takes the whole Markdown file as the system prompt, as for Codex, with no tools of its own", () => {
    expect(parseAgentFile("pi", "# Caztor\n\nWrite well.\n", hash)).toEqual({ hash, name: "caztor", description: "Caztor academic writing instructions", prompt: "# Caztor\n\nWrite well.", tools: [] });
  });
});
