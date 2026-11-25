import type { FileEntry, RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { buildTree, classifyFile, MAX_TEXT_BYTES, isWithin, movedPath, type TreeNode } from "./tree.ts";

const file = (path: string, size = 10): FileEntry => ({ path: path as RelPath, kind: "file", size });
const dir = (path: string): FileEntry => ({ path: path as RelPath, kind: "dir", size: 0 });

/** The tree as nested names, easy to compare. */
function names(nodes: TreeNode[]): unknown[] {
  return nodes.map((node) => (node.kind === "dir" ? { [node.name]: names(node.children) } : node.name));
}

describe("buildTree", () => {
  it("nests entries under their folders", () => {
    const tree = buildTree([dir("chapters"), file("chapters/intro.tex"), file("main.tex"), dir("chapters/figs"), file("chapters/figs/a.png")]);
    expect(names(tree)).toEqual([{ chapters: [{ figs: ["a.png"] }, "intro.tex"] }, "main.tex"]);
    expect(tree[0]?.path).toBe("chapters");
    expect(tree[0]?.children[0]?.path).toBe("chapters/figs");
  });

  it("lists folders before files and sorts each group by name, numbers in order, ignoring case", () => {
    const tree = buildTree([file("b.tex"), file("A.tex"), file("ch10.tex"), file("ch2.tex"), dir("zeta"), dir("alpha")]);
    expect(names(tree)).toEqual([{ alpha: [] }, { zeta: [] }, "A.tex", "b.tex", "ch2.tex", "ch10.tex"]);
  });

  it("creates the missing folder of an entry whose folder was not listed", () => {
    expect(names(buildTree([file("deep/inner/x.tex")]))).toEqual([{ deep: [{ inner: ["x.tex"] }] }]);
  });

  it("returns an empty list for an empty project", () => {
    expect(buildTree([file("only.tex")])).toHaveLength(1);
    expect(buildTree([])).toEqual([]);
  });

  it("leaves out the reserved folders the server never lists, as a second line of defence", () => {
    const tree = buildTree([file(".git/config"), dir(".caztor"), file(".claude/a.md"), file("node_modules/x.js"), file("main.tex")]);
    expect(names(tree)).toEqual(["main.tex"]);
  });
});

describe("classifyFile", () => {
  it.each([
    ["main.tex", 100, "text"],
    ["refs.bib", 100, "text"],
    ["notes", 100, "text"],
    ["figure.PNG", 100, "binary"],
    ["paper.pdf", 100, "binary"],
    ["data.zip", 100, "binary"],
    ["big.tex", MAX_TEXT_BYTES + 1, "large"],
    ["limit.tex", MAX_TEXT_BYTES, "text"],
    ["huge.png", MAX_TEXT_BYTES + 1, "binary"],
  ])("classifies %s (%d bytes) as %s", (path, size, expected) => {
    expect(classifyFile(file(path, size))).toBe(expected);
  });
});

describe("movedPath", () => {
  it.each([
    ["main.tex", "main.tex", "thesis.tex", "thesis.tex"],
    ["chapters/intro.tex", "chapters", "parts", "parts/intro.tex"],
    ["chapters/a/b.tex", "chapters/a", "chapters/z", "chapters/z/b.tex"],
    ["chapters2/intro.tex", "chapters", "parts", "chapters2/intro.tex"],
    ["other.tex", "main.tex", "thesis.tex", "other.tex"],
  ])("moves %s when %s becomes %s", (path, from, to, expected) => {
    expect(movedPath(path, from, to)).toBe(expected);
  });
});

describe("isWithin", () => {
  it.each([
    ["main.tex", "main.tex", true],
    ["chapters/intro.tex", "chapters", true],
    ["chapters2/intro.tex", "chapters", false],
    ["chapters", "chapters/intro.tex", false],
  ])("%s within %s is %s", (path, removed, expected) => {
    expect(isWithin(path, removed)).toBe(expected);
  });
});
