import { describe, expect, it } from "vitest";
import { parseRelPath, RESERVED_ROOTS } from "../src/paths.ts";

describe("parseRelPath accepts project-relative paths", () => {
  it.each(["main.tex", "chapters/intro.tex", "figures/a b.png", "dir/-leading-dash-inside.tex", ".gitignore", "a/b/c/d.bib", "AGENTS.md"])(
    "accepts %s unchanged",
    (input) => {
      const result = parseRelPath(input);
      expect(result).toEqual({ ok: true, value: input });
    },
  );

  it("accepts a path of exactly 1024 characters", () => {
    const input = "a".repeat(1024);
    expect(parseRelPath(input)).toEqual({ ok: true, value: input });
  });
});

describe("parseRelPath rejects malformed paths as invalid_path", () => {
  const cases: [label: string, input: string][] = [
    ["empty", ""],
    ["backslash", "dir\\file.tex"],
    ["NUL byte", "main\0.tex"],
    ["newline", "main\n.tex"],
    ["DEL control character", "main\x7f.tex"],
    ["leading dash flag-like name", "-Z shell-escape.tex"],
    ["a lone dash", "-"],
    ["longer than 1024", "a".repeat(1025)],
    ["current-directory segment", "a/./b.tex"],
    ["empty segment", "a//b.tex"],
    ["trailing slash", "chapters/"],
  ];
  it.each(cases)("%s", (_label, input) => {
    expect(parseRelPath(input)).toEqual({ ok: false, error: { code: "invalid_path", path: input } });
  });
});

describe("parseRelPath rejects paths escaping the project root as outside_root", () => {
  const cases: [label: string, input: string][] = [
    ["parent traversal", "../secret.txt"],
    ["nested traversal", "a/../../secret.txt"],
    ["traversal that returns inside", "a/../b.tex"],
    ["bare parent", ".."],
    ["absolute path", "/etc/passwd"],
  ];
  it.each(cases)("%s", (_label, input) => {
    expect(parseRelPath(input)).toEqual({ ok: false, error: { code: "outside_root", path: input } });
  });
});

describe("parseRelPath hides reserved roots", () => {
  it.each(["skills/kaggle-accounts/store", "skills/kaggle-accounts/store/a.json", ".papersmith/config.json", ".pi/x", ".mcp.json", ".env", ".env.local"])("hides %s, which belongs to PaperSmith or holds secrets", (path) => {
    expect(parseRelPath(path)).toMatchObject({ ok: false, error: { code: "hidden" } });
  });

  it("allows the files around them", () => {
    for (const path of ["paper/main.tex", "skills/kaggle-accounts/SKILL.md", "docs/.env", ".envelope"]) expect(parseRelPath(path).ok, path).toBe(true);
  });

  it("lists the reserved roots", () => {
    expect([...RESERVED_ROOTS]).toEqual([".caztor", ".claude", ".opencode", ".agents", ".git", "node_modules", ".papersmith", ".pi", ".mcp.json", ".env", ".env.local"]);
  });

  it.each([
    ".caztor",
    ".caztor/state.json",
    ".claude/agents/caztor.md",
    ".opencode/agent/caztor.md",
    ".agents/agents/caztor.md",
    ".AGENTS/hooks.json",
    ".git/config",
    "node_modules/x/index.js",
    ".GIT/config",
  ])("returns hidden for %s", (input) => {
    expect(parseRelPath(input)).toEqual({ ok: false, error: { code: "hidden", path: input } });
  });

  it.each([".gitignore", ".github/workflows/ci.yml", "src/.git/config", "node_modules_backup/a.tex"])(
    "does not hide %s",
    (input) => {
      expect(parseRelPath(input)).toEqual({ ok: true, value: input });
    },
  );
});
