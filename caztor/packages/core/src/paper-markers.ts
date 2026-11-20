/**
 * Where PaperSmith keeps a workspace's paper, and the prefix of the comment lines it delimits its parts with: named
 * blocks of prose, and its `declarations` and `provenance` regions.
 */
export const PAPERSMITH_MAIN = "paper/main.tex";
export const PAPER_MARKER_PREFIX = "%% paper-writing ";

/** The marker lines of a document, in order. Like PaperSmith, a line counts only when it starts with the prefix. */
export function paperMarkerLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.replace(/\r$/, ""))
    .filter((line) => line.startsWith(PAPER_MARKER_PREFIX));
}

/** Whether `after` holds exactly the markers of `before`, in the same order. PaperSmith finds each block by them. */
export function markersKept(before: string, after: string): boolean {
  const kept = paperMarkerLines(before);
  if (kept.length === 0) return true;
  const now = paperMarkerLines(after);
  return now.length === kept.length && now.every((line, index) => line === kept[index]);
}

const END_OF_DOCUMENT = "\\end{document}";
const isEndOfDocument = (line: string) => /^\s*\\end\{document\}\s*(%.*)?$/.test(line.replace(/\r$/, ""));

/** The index of the last `\end{document}` line outside PaperSmith's blocks and regions, whose text is theirs; -1 if none. */
function lastEndOfDocument(lines: readonly string[]): number {
  let inside = false;
  let found = -1;
  lines.forEach((line, index) => {
    if (line.startsWith(PAPER_MARKER_PREFIX)) inside = / begin( |$)/.test(line.replace(/\r$/, ""));
    else if (!inside && isEndOfDocument(line)) found = index;
  });
  return found;
}

/**
 * Whether PaperSmith put a part after `\end{document}`. It adds every new block at the end of the file, where LaTeX
 * no longer reads, so a paper with a preamble needs its end moved after them.
 */
export function endOfDocumentMisplaced(text: string): boolean {
  const lines = text.split("\n");
  const end = lastEndOfDocument(lines);
  return end !== -1 && lines.slice(end + 1).some((line) => line.startsWith(PAPER_MARKER_PREFIX));
}

/** Moves the last `\end{document}` to the end of the file. Nothing else changes, so every block keeps its bytes. */
export function moveEndOfDocument(text: string): string {
  const lines = text.split("\n");
  const end = lastEndOfDocument(lines);
  if (end === -1) return text;
  const rest = [...lines.slice(0, end), ...lines.slice(end + 1)].join("\n");
  return `${rest.endsWith("\n") || rest === "" ? rest : `${rest}\n`}${END_OF_DOCUMENT}\n`;
}

const LATEX_SPECIAL: Readonly<Record<string, string>> = {
  "\\": "\\textbackslash{}", "&": "\\&", "%": "\\%", $: "\\$", "#": "\\#", _: "\\_", "{": "\\{", "}": "\\}", "~": "\\textasciitilde{}", "^": "\\textasciicircum{}",
};

/**
 * The starter paper Caztor writes in place of PaperSmith's empty `main.tex`: a whole document that compiles. PaperSmith
 * reads it like any other, since only its marker lines matter to it, and adds its blocks at the end.
 */
export function paperTemplate(title: string | undefined): string {
  const escaped = (title ?? "Title").replace(/[\\&%$#_{}~^]/g, (character) => LATEX_SPECIAL[character] ?? character);
  return [
    "\\documentclass[11pt]{article}",
    "\\usepackage{amsmath}",
    "\\usepackage{graphicx}",
    "\\graphicspath{{Figures/}}",
    "",
    `\\title{${escaped}}`,
    "\\author{}",
    "\\date{}",
    "",
    "\\begin{document}",
    "\\maketitle",
    "",
    "% PaperSmith adds the blocks of the paper below. If one ends up after \\end{document},",
    "% Caztor offers to move \\end{document} back to the end.",
    "",
    END_OF_DOCUMENT,
    "",
  ].join("\n");
}
