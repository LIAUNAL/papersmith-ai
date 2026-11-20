import { PAPERSMITH_MAIN, paperTemplate, type Result } from "@caztor/core";
import type { FileSystem } from "./infra.ts";

/** What PaperSmith's own `paper_scaffold.py` creates, in its order: empty files and one folder. */
const ENTRIES: ReadonlyArray<{ name: string; kind: "file" | "dir" }> = [
  { name: "main.tex", kind: "file" },
  { name: "refs.bib", kind: "file" },
  { name: "Figures", kind: "dir" },
  { name: ".gitkeep", kind: "file" },
];

const kindOf = (fs: FileSystem, path: string) =>
  fs.lstat(path).then(
    (stats) => (stats.isSymbolicLink() ? "link" : stats.isDirectory() ? "dir" : "file"),
    () => null,
  );

/**
 * Creates `paper/` as PaperSmith's scaffold does, so PaperSmith recognises it: whatever exists is left byte for byte,
 * and `main.tex` starts as a small whole document instead of an empty file,
 * and an entry of the wrong kind refuses before anything is written. Unlike PaperSmith it also refuses links, so
 * nothing is written outside the project.
 */
export async function scaffoldPaper(fs: FileSystem, root: string, title?: string): Promise<Result<string[], { message: string }>> {
  const paper = `${root}/${PAPERSMITH_MAIN.slice(0, PAPERSMITH_MAIN.indexOf("/"))}`;
  const paperKind = await kindOf(fs, paper);
  if (paperKind === "link" || paperKind === "file") return { ok: false, error: { message: "paper exists and is not a folder." } };
  for (const entry of ENTRIES) {
    const found = await kindOf(fs, `${paper}/${entry.name}`);
    if (found === "link") return { ok: false, error: { message: `paper/${entry.name} is a link, so it was left alone.` } };
    if (found !== null && found !== entry.kind) return { ok: false, error: { message: `paper/${entry.name} exists as a ${found === "dir" ? "folder" : "file"}, not a ${entry.kind === "dir" ? "folder" : "file"}.` } };
  }
  const created: string[] = [];
  try {
    if (paperKind === null) await fs.mkdir(paper);
    for (const entry of ENTRIES) {
      const path = `${paper}/${entry.name}`;
      if ((await kindOf(fs, path)) !== null) continue;
      if (entry.kind === "dir") await fs.mkdir(path);
      else await fs.writeFile(path, entry.name === "main.tex" ? new TextEncoder().encode(paperTemplate(title)) : new Uint8Array(), { exclusive: true });
      created.push(entry.name);
    }
  } catch {
    return { ok: false, error: { message: "The paper folder could not be created." } };
  }
  return { ok: true, value: created };
}
