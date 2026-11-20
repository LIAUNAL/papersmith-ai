import { describe, expect, it } from "vitest";
import {
  PIPELINE_TERMS,
  SHARED_CONVENTIONS,
  STRIPPED_HEADINGS,
  distillGuide,
} from "../../src/guides/distill.ts";

const COMMIT = "1f09516";
const PATH = "sections/08-abstract.md";

const FRONT = `---
{
  "section": "abstract",
  "blocks": [{ "id": "slot-1", "requires_facts": [] }]
}
---
`;

function source(body: string): string {
  return `${FRONT}${body}`;
}

const SIMPLE = source(`# Abstract

**Extent** 216–280 words · **one paragraph**

The abstract is the whole argument at one-fiftieth scale.

## Slot 1 — Context

State the field and the phenomenon.

## Disqualifiers

- More than one paragraph.
`);

describe("distillGuide: structure", () => {
  it("removes the JSON front matter and keeps the title and body", () => {
    const { markdown } = distillGuide(SIMPLE, PATH, COMMIT);
    expect(markdown.startsWith("# Abstract\n")).toBe(true);
    expect(markdown).not.toContain("requires_facts");
    expect(markdown).not.toContain('"section"');
    expect(markdown).toContain("The abstract is the whole argument at one-fiftieth scale.");
    expect(markdown).toContain("## Slot 1 — Context");
  });

  it("removes the three pipeline input subsections and reports them as stripped", () => {
    const text = source(`# Methods

Lead.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| The dataset | \`mm-dataset\` |

### Internal chain

| Block | Depends on |
|---|---|
| \`methods.mm-proposal\` | \`methods.mm-dataset\` |

### Structural decisions

- A decision about the structure.

## Disqualifiers

- A symbol used without a declaration.
`);
    const result = distillGuide(text, "sections/01-materials-and-methods.md", COMMIT);
    expect(result.markdown).not.toContain("mm-proposal");
    expect(result.markdown).not.toContain("Unblocks");
    expect(result.markdown).not.toContain("A decision about the structure");
    expect(result.stripped).toEqual(["### External inputs", "### Internal chain", "### Structural decisions"]);
    expect(result.markdown).toContain("- A symbol used without a declaration.");
  });

  it("only strips headings listed in STRIPPED_HEADINGS", () => {
    expect([...STRIPPED_HEADINGS]).toEqual(["### External inputs", "### Internal chain", "### Structural decisions"]);
    const text = source(`# Intro

## Inputs per block

Drafting remark.

### What is writable before measuring

Blocks one to three can be drafted early.

### The loop that must be closed by hand

**The results rule.** The text is corrected to match the results, never the reverse.
`);
    const result = distillGuide(text, "sections/06-introduction.md", COMMIT);
    expect(result.stripped).toEqual([]);
    expect(result.markdown).toContain("### What is writable before measuring");
    expect(result.markdown).toContain("**The results rule.** The text is corrected to match the results, never the reverse.");
  });

  it("drops an Inputs heading that has nothing left, and renames one that keeps prose", () => {
    const empty = distillGuide(
      source("# T\n\n## Inputs\n\n### External inputs\n\nx\n\n## Disqualifiers\n\n- y\n"),
      "sections/09-title-and-keywords.md",
      COMMIT,
    );
    expect(empty.markdown).not.toContain("## Inputs");
    expect(empty.markdown).not.toContain("## Drafting order");

    const lead = distillGuide(
      source("# T\n\n## Inputs per block\n\nNothing here depends on a measurement.\n\n### Internal chain\n\nx\n\n## Disqualifiers\n\n- y\n"),
      "sections/05-related-work.md",
      COMMIT,
    );
    expect(lead.markdown).toContain("## Drafting order\n\nNothing here depends on a measurement.");
    expect(lead.markdown).not.toContain("## Inputs");
  });

  it("removes block id suffixes from headings", () => {
    const text = source("# I\n\n## Block 4 — Proposal and contributions (`block-4a`, `block-4b`)\n\nText.\n\n### Paragraph 4a — the prose (`block-4a`)\n\nMore.\n");
    const { markdown, kept } = distillGuide(text, "sections/06-introduction.md", COMMIT);
    expect(markdown).toContain("## Block 4 — Proposal and contributions\n");
    expect(markdown).toContain("### Paragraph 4a — the prose\n");
    expect(markdown).not.toContain("block-4a");
    expect(kept).toContain("## Block 4 — Proposal and contributions");
  });

  it("removes HTML comments, including multi-line ones", () => {
    const text = source("# R\n\n## Whether\n\n<!-- Open Question 1 (design.md):\nresolved block-level. -->\n\nThis is one decision.\n");
    const { markdown } = distillGuide(text, "sections/05-related-work.md", COMMIT);
    expect(markdown).not.toContain("Open Question");
    expect(markdown).not.toContain("<!--");
    expect(markdown).toContain("This is one decision.");
  });

  it("rewrites known sentences that mention the origin tooling, even when the source wraps them", () => {
    const text = source(
      "# M\n\n## Rules\n\nEither way, what the section's own Components Check reads back against the\ndiagram is that ordered list of names.\n\nNothing in this contract licenses that.\n",
    );
    const { markdown } = distillGuide(text, "sections/01-materials-and-methods.md", COMMIT);
    expect(markdown).toContain("Either way, what is read back against the diagram is that ordered list of names.");
    expect(markdown).toContain("Nothing in this guide licenses that.");
    expect(markdown).not.toMatch(/Components Check/i);
  });

  it("rewrites the drafting-order sentences that talk about a graph or about waiting for the code", () => {
    const text = source(
      "# M\n\n## Inputs\n\nNothing here waits for an experiment. But it does wait for the code to exist.\n\n## Other\n\nIn practice most of the chain survives, which is why the graph is worth following\nrather than waiting.\n",
    );
    const { markdown } = distillGuide(text, "sections/01-materials-and-methods.md", COMMIT);
    expect(markdown).toContain("Nothing here waits for an experiment, but it does wait for the implementation to exist,");
    expect(markdown).toContain("which is why the chain is worth following\nrather than waiting.");
    expect(markdown).not.toMatch(/\bgraph\b/);
  });

  it("throws for an unknown sentence that mentions a contract, reporting the paragraph's first line", () => {
    const text = source("# M\n\nA clean line.\nThe section follows its own contract here.\n");
    const first = FRONT.split("\n").length - 1 + 3;
    expect(() => distillGuide(text, PATH, COMMIT)).toThrowError(`${PATH}:${first + 1}`);
  });

  it("is deterministic", () => {
    const first = distillGuide(SIMPLE, PATH, COMMIT);
    const second = distillGuide(SIMPLE, PATH, COMMIT);
    expect(second).toEqual(first);
  });

  it("reports the kept headings in order, without the added sections", () => {
    const { kept } = distillGuide(SIMPLE, PATH, COMMIT);
    expect(kept).toEqual(["# Abstract", "## Slot 1 — Context", "## Disqualifiers"]);
  });
});

describe("distillGuide: added text", () => {
  it("adds a modification notice with the source path, the commit and the license", () => {
    const { markdown } = distillGuide(SIMPLE, PATH, COMMIT);
    expect(markdown).toContain(`sections/08-abstract.md`);
    expect(markdown).toContain(COMMIT);
    expect(markdown).toContain("Apache License, Version 2.0");
    expect(markdown).toContain("LICENSE-papersmith-ai.txt");
    expect(markdown).toMatch(/modified/i);
  });

  it("states that the guide is advisory, that ranges are typical, and names the other genres", () => {
    const { markdown } = distillGuide(SIMPLE, PATH, COMMIT);
    expect(markdown).toMatch(/advisory/i);
    expect(markdown).toMatch(/typical range/i);
    expect(markdown).toMatch(/venue template/i);
    expect(markdown).toMatch(/theses, reports and reviews/i);
    expect(markdown).toMatch(/document'?s? own structure/i);
  });

  it("appends the shared conventions as the last section, labelled as Caztor's own text", () => {
    const { markdown } = distillGuide(SIMPLE, PATH, COMMIT);
    const index = markdown.indexOf("## Shared conventions");
    expect(index).toBeGreaterThan(markdown.indexOf("## Disqualifiers"));
    const tail = markdown.slice(index);
    expect(tail).toMatch(/Caztor/);
    expect(tail.match(/^## /gm)).toHaveLength(1);
    for (const convention of SHARED_CONVENTIONS) expect(tail).toContain(convention.rule);
  });

  it("names the source guides each shared convention summarizes, or marks it as Caztor's own", () => {
    const { markdown } = distillGuide(SIMPLE, PATH, COMMIT);
    const withSources = SHARED_CONVENTIONS.filter((c) => c.evidence.length > 0);
    const own = SHARED_CONVENTIONS.filter((c) => c.evidence.length === 0);
    expect(withSources.length).toBeGreaterThan(5);
    expect(own.length).toBeGreaterThan(0);
    const citation = SHARED_CONVENTIONS.find((c) => c.rule.includes("end of the sentence"));
    expect(citation).toBeDefined();
    expect(citation?.evidence.map((e) => e.file)).toEqual(["05-related-work.md", "06-introduction.md"]);
    expect(markdown).toContain("(Summarizes the guides 05-related-work and 06-introduction.)");
    expect(markdown).toMatch(/\(Caztor's own rule\.\)/);
  });

  it("keeps notice and advisory text clear of pipeline terms", () => {
    const { markdown } = distillGuide(SIMPLE, PATH, COMMIT);
    const withoutPath = markdown.replaceAll("papersmith-ai", "").replaceAll("sections/08-abstract.md", "");
    for (const term of PIPELINE_TERMS) expect(withoutPath).not.toMatch(term);
  });
});

describe("distillGuide: failures", () => {
  it("throws naming the file and the source line of a leftover pipeline term", () => {
    const text = source("# Abstract\n\nFirst line.\n\nThe forge decides this.\n");
    const frontLines = FRONT.split("\n").length - 1;
    const expectedLine = frontLines + 5;
    expect(() => distillGuide(text, PATH, COMMIT)).toThrowError(`${PATH}:${expectedLine}`);
    expect(() => distillGuide(text, PATH, COMMIT)).toThrowError(/forge/i);
  });

  it("does not throw for a term inside a stripped section", () => {
    const text = source("# A\n\n## Inputs\n\n### Internal chain\n\nThe forge decides this, see `requires_facts`.\n\n## Disqualifiers\n\n- x\n");
    expect(() => distillGuide(text, PATH, COMMIT)).not.toThrow();
  });

  it("catches each family of pipeline vocabulary", () => {
    const samples = [
      "the forge",
      "Kaggle notebooks",
      "a deliberation round",
      "OpenSpec contracts",
      "requires_facts",
      "produces_facts",
      "the binding map",
      "an evidence set",
      "transposition mode",
      "run `paper build`",
      "see mm-proposal",
      "block-4a",
      "slot-3",
    ];
    for (const sample of samples) {
      const text = source(`# T\n\n${sample}\n`);
      expect(() => distillGuide(text, PATH, COMMIT), sample).toThrowError(/pipeline term/);
    }
  });

  it("does not flag ordinary words that merely contain a pipeline term", () => {
    const clean = source("# T\n\nThe sentence is deliberately stretched here.\n");
    expect(distillGuide(clean, PATH, COMMIT).markdown).toContain("deliberately stretched");
  });

  it("throws naming the file when the front matter is missing", () => {
    expect(() => distillGuide("# Abstract\n\nText.\n", PATH, COMMIT)).toThrowError(`${PATH}:1: missing JSON front matter`);
  });
});
