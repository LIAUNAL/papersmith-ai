import type { Diagnostic, RelPath } from "./ports.ts";

export interface TexSource {
  path: RelPath;
  text: string;
}

export const BIBLATEX_NOTICE =
  "This project uses biblatex, which needs biber. Biber is not supported; use BibTeX (\\bibliography) instead.";

const PACKAGE_LOAD = /\\(?:usepackage|RequirePackage)\s*(?:\[([^\]]*)\])?\s*\{([^}]*)\}/g;
const ADD_RESOURCE = /\\addbibresource\b/;
const BIBTEX_BACKEND = /\bbackend\s*=\s*bibtex8?\b/;

/** Drops the comment part of a line; a percent sign preceded by a backslash is text. */
function withoutComment(line: string): string {
  for (let i = 0; i < line.length; i += 1) {
    if (line[i] === "\\") i += 1;
    else if (line[i] === "%") return line.slice(0, i);
  }
  return line;
}

interface Use {
  line: number;
  bibtexBackend: boolean;
}

/** The first line that loads biblatex or declares a biblatex resource, and whether it picks the BibTeX backend. */
function findUse(text: string): Use | null {
  const lines = text.split(/\r?\n/).map(withoutComment);
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]!;
    for (const match of line.matchAll(PACKAGE_LOAD)) {
      const names = match[2]!.split(",").map((name) => name.trim());
      if (names.includes("biblatex")) return { line: index + 1, bibtexBackend: BIBTEX_BACKEND.test(match[1] ?? "") };
    }
    if (ADD_RESOURCE.test(line)) return { line: index + 1, bibtexBackend: false };
  }
  return null;
}

/**
 * A notice when the project needs biblatex with biber, which the engine cannot run. biblatex with the `bibtex`
 * backend is fine, so it raises nothing. Points at the first file that uses biblatex.
 */
export function biblatexNotice(sources: Iterable<TexSource>): Diagnostic | null {
  let first: { path: RelPath; use: Use } | null = null;
  for (const source of sources) {
    const use = findUse(source.text);
    if (use === null) continue;
    if (use.bibtexBackend) return null;
    first ??= { path: source.path, use };
  }
  if (first === null) return null;
  return { severity: "warning", file: first.path, line: first.use.line, message: BIBLATEX_NOTICE, source: "caztor" };
}
