import { describe, expect, it } from "vitest";
import { locatePassage, type LocateSources } from "./locate.ts";

const passage = "each colour class is updated in parallel without conflicts";
const holding = "Intro.\nMore.\nEach colour class is updated\nin parallel without conflicts.\n";

function sources(files: Record<string, string>, open: LocateSources["open"] = null, sizes: Record<string, number> = {}) {
  const read: string[] = [];
  const source: LocateSources = {
    open,
    listFiles: async () => [{ path: "paper", kind: "dir", size: 0 }, ...Object.keys(files).map((path) => ({ path, kind: "file" as const, size: sizes[path] ?? files[path]!.length }))],
    readFile: async (path) => {
      read.push(path);
      if (!(path in files)) throw new Error("not found");
      return { content: files[path]! };
    },
  };
  return { source, read };
}

describe("locatePassage", () => {
  it("answers from the open file, with the line the passage starts on, without reading anything", async () => {
    const { source, read } = sources({ "paper/other.tex": holding }, { path: "paper/main.tex", text: holding });
    expect(await locatePassage(passage, source, new Map())).toEqual({ path: "paper/main.tex", line: 3 });
    expect(read).toEqual([]);
  });

  it("otherwise searches LaTeX sources before Markdown, and returns the first file that holds it", async () => {
    const { source, read } = sources({ "notes.md": holding, "paper/b.tex": "nothing", "paper/a.tex": holding }, { path: "paper/main.tex", text: "nothing" });
    expect(await locatePassage(passage, source, new Map())).toEqual({ path: "paper/a.tex", line: 3 });
    expect(read).toEqual(["paper/b.tex", "paper/a.tex"]);
  });

  it("prefers the latest revision of a numbered file", async () => {
    const { source } = sources({ "experiments/protocol-v2.md": holding, "experiments/protocol-v19.md": holding, "experiments/protocol-v8.md": holding });
    expect(await locatePassage(passage, source, new Map())).toEqual({ path: "experiments/protocol-v19.md", line: 3 });
  });

  it("finds a passage only Markdown holds, such as an experiments protocol", async () => {
    const { source } = sources({ "paper/main.tex": "nothing", "experiments/protocol-v19.md": holding });
    expect(await locatePassage(passage, source, new Map())).toEqual({ path: "experiments/protocol-v19.md", line: 3 });
  });

  it("reads each file once across steps, and skips large files, other kinds and unreadable ones", async () => {
    const { source, read } = sources({ "big.tex": holding, "image.png": holding, "broken.tex": "", "paper/x.md": holding }, null, { "big.tex": 5 * 1024 * 1024 });
    source.readFile = async (path) => {
      read.push(path);
      if (path === "broken.tex") throw new Error("io");
      return { content: path === "paper/x.md" ? holding : "" };
    };
    const texts = new Map<string, string>();
    expect(await locatePassage(passage, source, texts)).toEqual({ path: "paper/x.md", line: 3 });
    expect(await locatePassage("a passage that is nowhere in these files", source, texts)).toBeNull();
    expect(read).toEqual(["broken.tex", "paper/x.md"]);
  });
});
