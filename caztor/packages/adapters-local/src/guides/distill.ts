/**
 * Turns the section guides of the papersmith-ai project into Caztor writing guides.
 *
 * The transform is pure (strings in, strings out) so the same function can serve a build script today
 * and a runtime guide source later. The source files are Apache-2.0; every guide carries a notice.
 */

/** Source subsections that hold the origin project's input tables and block references, never writing advice. */
export const STRIPPED_HEADINGS = ["### External inputs", "### Internal chain", "### Structural decisions"] as const;

/**
 * Vocabulary of the origin project's tooling. A match in text that survives the transform is a bug in the
 * transform or a new source construct, so distilling throws instead of shipping it.
 */
export const PIPELINE_TERMS: readonly RegExp[] = [
  /forge/i,
  /kaggle/i,
  /\bdeliberation\b/i,
  /openspec/i,
  /requires_(?:facts|declarations)/,
  /produces_facts/,
  /components_from/,
  /binding map/i,
  /evidence sets?/i,
  /transposition/i,
  /transposed/i,
  /`paper [a-z]/,
  /\bblock-\d/,
  /\bslot-\d/,
  /\b(?:mm|es|rd|rw|lim|concl|bm)-[a-z]/,
  /\bcontracts?\b/i,
  /components check/i,
  /\bsettled decision/i,
  /proposals document/i,
  /\bsections\/\d\d-/,
  /\bgraph\b/i,
];

/** The heading text a kept `## Inputs...` section gets: its remaining prose is advice on drafting order. */
const DRAFTING_ORDER_HEADING = "## Drafting order";

/**
 * Exact phrase replacements for source sentences that mention the origin project's own machinery but carry
 * advice worth keeping. Whitespace in `from` matches any run of whitespace, so line wrapping is irrelevant.
 */
const REWRITES: readonly (readonly [from: string, to: string])[] = [
  ["The decision changes the contract of both sections", "The decision changes the requirements of both sections"],
  [
    "what the section's own Components Check reads back against the diagram",
    "what is read back against the diagram",
  ],
  [
    "The Components Check this diagram undergoes compares it against this same block's own roster.** That is intra-block drift, never cross-section corroboration — nothing outside this block is consulted.",
    "The diagram is read back against this same section's own roster.** Nothing outside this section is consulted.",
  ],
  ["Every word count in this contract", "Every word count in this guide"],
  ["Nothing in this contract licenses that.", "Nothing in this guide licenses that."],
  ["Last, always, under its own contract.", "Last, always, and treated in its own guide."],
  ["Those names are the methods section's own contract", "Those names are the ones the methods section defines"],
  [
    "Nothing here waits for an experiment. But it does wait for the code to exist.",
    "Nothing here waits for an experiment, but it does wait for the implementation to exist, because this section describes what the code computes.",
  ],
  ["which is why the graph is worth following", "which is why the chain is worth following"],
  [
    "There is no order among these blocks — there is a graph.",
    "These blocks are not written in reading order.",
  ],
  [
    "There is no order among the slots — there is a graph, the same one that governs the introduction.",
    "The slots are not written in reading order; the same drafting dependencies apply as for the introduction.",
  ],
];

export interface ConventionEvidence {
  /** Source file name, for example `06-introduction.md`. */
  readonly file: string;
  /** A phrase that must appear in that source file (ignoring emphasis marks and line wrapping). */
  readonly quote: string;
}

export interface SharedConvention {
  readonly rule: string;
  /** The source guides this rule summarizes. Empty for a rule Caztor wrote itself. */
  readonly evidence: readonly ConventionEvidence[];
}

/** New text written for Caztor. Each rule names the source guides it summarizes, or says it is Caztor's own. */
export const SHARED_CONVENTIONS: readonly SharedConvention[] = [
  {
    rule: "Place a citation at the end of the sentence it supports: one sentence, one attributed claim, and a sentence that would need two citations is two sentences.",
    evidence: [
      { file: "05-related-work.md", quote: "At the end of the sentence it supports" },
      { file: "06-introduction.md", quote: "Place the citation at the end of the sentence it supports" },
    ],
  },
  {
    rule: "Never use a citation as a noun phrase (\"the work in [N] does X\"): write about families of work and ideas, and let the citation close the sentence.",
    evidence: [
      { file: "05-related-work.md", quote: "Never as a noun phrase" },
      { file: "06-introduction.md", quote: "Do not use the citation as a noun phrase" },
    ],
  },
  {
    rule: "Cite what is borrowed and do not cite what is the document's own. A citation that credits an object (a definition, an estimator, a dataset, an instrument) attaches to that object.",
    evidence: [
      { file: "01-materials-and-methods.md", quote: "Borrowed is cited, own is not" },
      { file: "01-materials-and-methods.md", quote: "The citation attaches to the object it credits" },
      { file: "02-experimental-setup.md", quote: "what is borrowed is cited" },
    ],
  },
  {
    rule: "Expand every acronym at its first appearance, including the name of the document's own method, and use the acronym alone afterwards.",
    evidence: [
      { file: "06-introduction.md", quote: "Expand acronyms on first appearance" },
      { file: "08-abstract.md", quote: "Expand every acronym on first appearance" },
    ],
  },
  {
    rule: "State the count before enumerating components or contributions, and keep the same count, order and names wherever the list is repeated.",
    evidence: [
      { file: "06-introduction.md", quote: "State the count before enumerating" },
      { file: "07-conclusions.md", quote: "Same count, same order, same names" },
      { file: "08-abstract.md", quote: "State the count before enumerating it" },
    ],
  },
  {
    rule: "Give each property, problem and component the same name everywhere it appears, not a synonym.",
    evidence: [
      { file: "03-results-and-discussion.md", quote: "The property carries the same name through all five links" },
      { file: "06-introduction.md", quote: "The property carries the same name through every link" },
    ],
  },
  {
    rule: "Refer to every figure and table in the text before it appears, and point at the exact part of it that holds the value.",
    evidence: [
      { file: "01-materials-and-methods.md", quote: "Every artefact is referenced before it appears" },
      { file: "02-experimental-setup.md", quote: "Every artefact is referenced before it appears" },
      { file: "03-results-and-discussion.md", quote: "Every artefact is referenced before it appears" },
      { file: "05-related-work.md", quote: "Every artefact is referenced before it appears" },
    ],
  },
  {
    rule: "In summarizing parts (the abstract and the conclusions) add no claim, number or property that the body does not establish, and quote a figure only when it matches the results exactly.",
    evidence: [
      { file: "07-conclusions.md", quote: "They add nothing" },
      { file: "07-conclusions.md", quote: "A quoted figure must match the results section exactly" },
      { file: "08-abstract.md", quote: "must match it exactly" },
    ],
  },
  {
    rule: "Never state a fact, number, result or reference the user has not provided. Ask for it, or leave a visible placeholder.",
    evidence: [],
  },
];

export interface DistilledGuide {
  readonly markdown: string;
  /** Source headings that were removed, in source order. */
  readonly stripped: readonly string[];
  /** Headings of the distilled body (title included), without the sections Caztor adds. */
  readonly kept: readonly string[];
}

interface Entry {
  text: string;
  line: number;
}

const HEADING = /^(#{1,6}) (.*)$/;
const ID_SUFFIX = /\s*\((?:`[^`]+`)(?:,\s*`[^`]+`)*\)\s*$/;

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const phrasePattern = (phrase: string) => new RegExp(phrase.split(/\s+/).map(escapeRegExp).join("\\s+"), "g");
const REWRITE_RULES = REWRITES.map(([from, to]) => [phrasePattern(from), to] as const);

function fail(sourcePath: string, line: number, message: string): never {
  throw new Error(`${sourcePath}:${line}: ${message}`);
}

/** Removes the leading JSON front matter. Throws naming the file when it is absent. */
function splitFrontMatter(lines: readonly string[], sourcePath: string): Entry[] {
  if (lines[0] !== "---") fail(sourcePath, 1, "missing JSON front matter");
  const end = lines.indexOf("---", 1);
  if (end === -1) fail(sourcePath, 1, "unterminated JSON front matter");
  return lines.slice(end + 1).map((text, offset) => ({ text, line: end + 2 + offset }));
}

/** Removes `<!-- ... -->` comments, including multi-line ones. */
function dropComments(entries: readonly Entry[]): Entry[] {
  const kept: Entry[] = [];
  let open = false;
  for (const entry of entries) {
    let text = entry.text;
    let result = "";
    while (text.length > 0) {
      if (open) {
        const close = text.indexOf("-->");
        if (close === -1) {
          text = "";
        } else {
          open = false;
          text = text.slice(close + 3);
        }
      } else {
        const start = text.indexOf("<!--");
        if (start === -1) {
          result += text;
          text = "";
        } else {
          result += text.slice(0, start);
          open = true;
          text = text.slice(start + 4);
        }
      }
    }
    if (result.trim() === "" && entry.text.trim() !== "") continue;
    kept.push({ text: result, line: entry.line });
  }
  return kept;
}

interface Section {
  heading: Entry | null;
  body: Entry[];
}

function splitSections(entries: readonly Entry[]): Section[] {
  const sections: Section[] = [{ heading: null, body: [] }];
  for (const entry of entries) {
    if (HEADING.test(entry.text)) sections.push({ heading: entry, body: [] });
    else (sections[sections.length - 1] as Section).body.push(entry);
  }
  return sections;
}

const hasProse = (body: readonly Entry[]) => body.some((entry) => entry.text.trim() !== "");

/** Applies the phrase rewrites paragraph by paragraph. A rewritten paragraph reports its first source line. */
function rewriteBody(body: readonly Entry[]): Entry[] {
  const result: Entry[] = [];
  let paragraph: Entry[] = [];
  const flush = () => {
    if (paragraph.length === 0) return;
    const original = paragraph.map((entry) => entry.text).join("\n");
    let text = original;
    for (const [pattern, to] of REWRITE_RULES) text = text.replace(pattern, to);
    if (text === original) result.push(...paragraph);
    else {
      const first = (paragraph[0] as Entry).line;
      for (const part of text.split("\n")) result.push({ text: part, line: first });
    }
    paragraph = [];
  };
  for (const entry of body) {
    if (entry.text.trim() === "") {
      flush();
      result.push(entry);
    } else paragraph.push(entry);
  }
  flush();
  return result;
}

function assertNoPipelineTerms(entries: readonly Entry[], sourcePath: string): void {
  for (const entry of entries) {
    for (const term of PIPELINE_TERMS) {
      if (term.test(entry.text)) fail(sourcePath, entry.line, `pipeline term ${String(term)} survived the transform: ${entry.text.trim()}`);
    }
  }
}

function orderedList(names: readonly string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

function notice(sourcePath: string, commit: string): string {
  return [
    `> **Notice.** This guide is a modified derivative of \`${sourcePath}\` from papersmith-ai (https://github.com/Daprosero/papersmith-ai, commit \`${commit}\`), licensed under the Apache License, Version 2.0. A copy of the license is provided as \`LICENSE-papersmith-ai.txt\` in this folder. Caztor removed the parts that belong to the source project's own tooling, reworded a few sentences, added the notes below, and appended the section "Shared conventions".`,
    ">",
    "> **Advisory.** This guide is advice, not a set of rules. The user's request, the document's own structure and the venue template take precedence over it; use the guide for the advice that remains. It describes a research article. The word counts, paragraph counts and other extents are typical ranges for a research article, not limits. For theses, reports and reviews, map the functions the guide describes onto that document's own sections and do not copy its headings or ranges. The list of disqualifiers names common weaknesses to check a draft against. The guide never licenses stating anything the user has not provided: facts, numbers, results and references come from the user's own files.",
  ].join("\n");
}

function sharedConventions(): string {
  const lines = SHARED_CONVENTIONS.map((convention) => {
    const files = [...new Set(convention.evidence.map((e) => e.file.replace(/\.md$/, "")))];
    const origin = files.length === 0 ? "(Caztor's own rule.)" : `(Summarizes the ${files.length === 1 ? "guide" : "guides"} ${orderedList(files)}.)`;
    return `- ${convention.rule} ${origin}`;
  });
  return [
    "## Shared conventions",
    "",
    "This section is Caztor's own summary of rules that recur across the guides. It is not part of the source text; each rule names the guides it summarizes.",
    "",
    ...lines,
  ].join("\n");
}

/** Distills one papersmith section guide. Throws, naming file and line, when pipeline vocabulary survives. */
export function distillGuide(source: string, sourcePath: string, commit: string): DistilledGuide {
  const body = dropComments(splitFrontMatter(source.split("\n"), sourcePath));
  const stripped: string[] = [];
  const kept: string[] = [];
  const output: Entry[] = [];

  for (const section of splitSections(body)) {
    const heading = section.heading;
    let headingText = heading === null ? null : heading.text.trim();
    const content = rewriteBody(section.body);
    if (heading !== null && headingText !== null) {
      if ((STRIPPED_HEADINGS as readonly string[]).includes(headingText)) {
        stripped.push(headingText);
        continue;
      }
      if (/^## Inputs\b/.test(headingText)) {
        if (!hasProse(content)) continue;
        headingText = DRAFTING_ORDER_HEADING;
      }
      headingText = headingText.replace(ID_SUFFIX, "");
      kept.push(headingText);
      output.push({ text: headingText, line: heading.line });
    }
    output.push(...content);
  }

  assertNoPipelineTerms(output, sourcePath);

  const text = output.map((entry) => entry.text).join("\n").replace(/\n{3,}/g, "\n\n").trim();
  const newline = text.indexOf("\n");
  const title = newline === -1 ? text : text.slice(0, newline);
  const rest = newline === -1 ? "" : text.slice(newline + 1).replace(/^\n+/, "");
  const markdown = [title, "", notice(sourcePath, commit), "", rest, "", sharedConventions(), ""].join("\n").replace(/\n{3,}/g, "\n\n");
  return { markdown, stripped, kept };
}
