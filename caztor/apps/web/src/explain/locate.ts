import { findPassages } from "./passages.ts";

/** Where an explained passage is: a project file and the line it starts on. */
export interface PassagePlace {
  path: string;
  line: number;
}

export interface LocateSources {
  /** The file open in the editor and its text as shown, unsaved edits included. */
  open: { path: string; text: string } | null;
  listFiles(): Promise<ReadonlyArray<{ path: string; kind: "file" | "dir"; size: number }>>;
  readFile(path: string): Promise<{ content: string }>;
}

/** Text files a passage of the paper can be quoted from, in the order they are searched. */
const SEARCHED = [".tex", ".md", ".bib", ".txt"];
const MAX_BYTES = 2 * 1024 * 1024;
const MAX_FILES = 400;

const lineAt = (text: string, offset: number): number => text.slice(0, offset).split("\n").length;

/**
 * The file that holds `passage`: the open one when it does, else the first project file that does, LaTeX sources
 * first, then Markdown, BibTeX and plain text, the latest revision of a numbered file first, at most `MAX_FILES`. `texts` keeps what was read, so the next
 * step does not read it again. Null when no searched file holds it.
 */
export async function locatePassage(passage: string, sources: LocateSources, texts: Map<string, string>): Promise<PassagePlace | null> {
  const inText = (path: string, text: string): PassagePlace | null => {
    const found = findPassages(text, [passage])[0];
    return found === undefined ? null : { path, line: lineAt(text, found.from) };
  };
  if (sources.open !== null) {
    const here = inText(sources.open.path, sources.open.text);
    if (here !== null) return here;
  }
  const rank = (path: string) => SEARCHED.findIndex((extension) => path.toLowerCase().endsWith(extension));
  const candidates = (await sources.listFiles())
    .filter((entry) => entry.kind === "file" && entry.size <= MAX_BYTES && rank(entry.path) !== -1 && entry.path !== sources.open?.path)
    // Within a kind, later names first: PaperSmith numbers revisions (-r15, -v19), so the current one wins.
    .sort((a, b) => rank(a.path) - rank(b.path) || b.path.localeCompare(a.path, "en", { numeric: true }))
    .slice(0, MAX_FILES);
  for (const { path } of candidates) {
    let text = texts.get(path);
    if (text === undefined) {
      text = await sources.readFile(path).then((file) => file.content, () => "");
      texts.set(path, text);
    }
    const place = inText(path, text);
    if (place !== null) return place;
  }
  return null;
}
