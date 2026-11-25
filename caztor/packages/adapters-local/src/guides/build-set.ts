import { SHARED_CONVENTIONS, distillGuide } from "./distill.ts";

/** The papersmith-ai section guides that become Caztor guides, in reading order. */
export const GUIDE_SOURCE_FILES = [
  "01-materials-and-methods.md",
  "02-experimental-setup.md",
  "03-results-and-discussion.md",
  "04-limitations.md",
  "05-related-work.md",
  "06-introduction.md",
  "07-conclusions.md",
  "08-abstract.md",
  "09-title-and-keywords.md",
  "10-back-matter.md",
] as const;

/** One line per guide for the index. Caztor's own wording. */
const FUNCTIONS: Readonly<Record<(typeof GUIDE_SOURCE_FILES)[number], readonly [section: string, function_: string]>> = {
  "01-materials-and-methods.md": ["Materials and Methods", "Defines the contributions formally: the dataset, the borrowed theory, the proposal and its notation."],
  "02-experimental-setup.md": ["Experimental Set-Up", "Turns the method into a protocol: the comparison design, the metrics, the compared methods and the training details."],
  "03-results-and-discussion.md": ["Results and Discussion", "Presents the evidence for each claim and explains each result next to its number."],
  "04-limitations.md": ["Limitations", "States what the reported results do not establish, tied to decisions in the method and the design."],
  "05-related-work.md": ["Related Work", "Argues what prior work, taken together, leaves unsolved, one block per stated problem."],
  "06-introduction.md": ["Introduction", "Motivates the problem, states the gap, presents the proposal and its evaluation, and announces the structure."],
  "07-conclusions.md": ["Conclusions", "Restates the proposal, the results, their consequence and the future work, for readers who skip the paper."],
  "08-abstract.md": ["Abstract", "Compresses the whole argument into one self-contained paragraph."],
  "09-title-and-keywords.md": ["Title and Keywords", "Shapes the title as one claim and the keywords as the retrieval surface."],
  "10-back-matter.md": ["Back Matter", "Covers author contributions, funding, data availability, conflicts of interest, acknowledgments and appendices."],
};

export interface GuideSetInput {
  /** Source file name (for example `08-abstract.md`) to its text. */
  readonly sources: Readonly<Record<string, string>>;
  readonly commit: string;
  readonly repository: string;
  /** Hex SHA-256 of a source text; injected so this module has no runtime dependencies. */
  readonly sha256: (text: string, file: string) => string;
}

export interface GuideSet {
  /** Output file name to content: ten guides, `INDEX.md` and `SOURCE.json`. */
  readonly files: Record<string, string>;
}

function index(): string {
  const rows = GUIDE_SOURCE_FILES.map((file) => {
    const [section, summary] = FUNCTIONS[file];
    return `| \`${file}\` | ${section} | ${summary} |`;
  });
  return [
    "# Writing guides",
    "",
    "These guides are advisory advice for writing the sections of an academic document. The user's request, the document's own structure and the venue template take precedence over them. They describe a research article; for theses, reports and reviews, map the functions they describe onto that document's own sections and do not copy headings or extents. Word counts and other extents are typical ranges, not limits. The guides never license stating anything the user has not provided.",
    "",
    "They are derived from the section guides of papersmith-ai, licensed under the Apache License, Version 2.0 (the license text is in `LICENSE-papersmith-ai.txt`). Each guide carries its own notice.",
    "",
    "## How to use them",
    "",
    "1. Read this index.",
    "2. Open only the guide for the section being written or revised.",
    "3. Apply the advice that fits the document and ignore the rest.",
    "",
    "## Guides",
    "",
    "| Guide | Section | Function |",
    "|---|---|---|",
    ...rows,
    "",
    "## Coherence across sections",
    "",
    "- The introduction, the abstract and the conclusions restate the contributions of the methods section with the same count, order and names; the title selects among them.",
    "- A problem keeps one name through the introduction, the contribution, the experimental set-up and the results.",
    "- The gap stated in the introduction and the gap closing the related work say the same thing at different depths.",
    "- Every future-work direction in the conclusions answers a limitation that the limitations section declares.",
    "- The abstract compresses the conclusions, so it is written after them; it adds nothing the paper does not establish.",
    "",
  ].join("\n");
}

/** Builds the full guide set from the source guides. Throws naming a missing source file. */
export function buildGuideSet(input: GuideSetInput): GuideSet {
  const files: Record<string, string> = {};
  const record: Record<string, { source: string; sha256: string; stripped: readonly string[]; kept: readonly string[] }> = {};
  for (const file of GUIDE_SOURCE_FILES) {
    const text = input.sources[file];
    if (text === undefined) throw new Error(`Source guide not available: ${file}`);
    const sourcePath = `sections/${file}`;
    const distilled = distillGuide(text, sourcePath, input.commit);
    files[file] = distilled.markdown;
    record[file] = { source: sourcePath, sha256: input.sha256(text, file), stripped: distilled.stripped, kept: distilled.kept };
  }
  files["INDEX.md"] = index();
  files["SOURCE.json"] = `${JSON.stringify(
    { repository: input.repository, commit: input.commit, files: record, conventions: SHARED_CONVENTIONS },
    null,
    2,
  )}\n`;
  return { files };
}

const normalize = (text: string) => text.replaceAll("*", "").replace(/\s+/g, " ");

/** Quotes that the shared conventions cite but the given source files do not contain. */
export function findMissingEvidence(sources: Readonly<Record<string, string>>): string[] {
  const missing: string[] = [];
  const seen = new Set<string>();
  for (const convention of SHARED_CONVENTIONS) {
    for (const { file, quote } of convention.evidence) {
      const key = `${file}: "${quote}"`;
      if (seen.has(key)) continue;
      seen.add(key);
      const text = sources[file];
      if (text === undefined) {
        const entry = `${file}: file not available`;
        if (!missing.includes(entry)) missing.push(entry);
      } else if (!normalize(text).includes(normalize(quote))) missing.push(key);
    }
  }
  return missing;
}
