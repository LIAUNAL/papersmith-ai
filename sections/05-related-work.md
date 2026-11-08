---
{
  "section": "related-work",
  "position": 4,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/05-related-work.md",
      "quote": "Every claim here belongs to someone else's work, and the section argues what those works together leave unsolved."
    }
  },
  "blocks": [
    {
      "id": "rw-preamble",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "The list of specific problems — to announce the blocks and their order"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "optional": true,
      "after": [
        {
          "target": "introduction.block-2",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "The list of specific problems — to announce the blocks and their order"
          }
        }
      ]
    },
    {
      "id": "rw-panorama",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "The general problem of the problem statement"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "optional": true,
      "after": [
        {
          "target": "introduction.block-2",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "The general problem of the problem statement"
          }
        }
      ]
    },
    {
      "id": "rw-problem-blocks",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "The specific problems, one block each"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "optional": true,
      "after": [
        {
          "target": "introduction.block-2",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "The specific problems, one block each"
          }
        }
      ]
    },
    {
      "id": "rw-closing",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true,
      "produces_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "The gap is stated in two places — the closing of this section and the closing of the introduction's state-of-the-art block — and they must say the same thing at different depths."
          }
        }
      ],
      "after": [
        {
          "target": "related-work.rw-problem-blocks",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "Name the fronts left open — as many as there are blocks."
          }
        }
      ]
    },
    {
      "id": "rw-synthesis-artefact",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "The properties (contributions) the proposal declares"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "optional": true,
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/05-related-work.md",
            "quote": "The properties (contributions) the proposal declares"
          }
        }
      ],
      "figure": {
        "components_from": "contributions",
        "ordered": false,
        "excludes": [],
        "caption_enumerates": true,
        "caption_decodes": false,
        "mandatory": false
      }
    }
  ]
}
---
# Related Work

**Extent** 820–1700 words
**Does not carry** equations
**Carries** one block per stated problem, and one synthesis table (or figure) of 7–12 works

Every claim here belongs to someone else's work, and the section argues what those works together leave unsolved.

## Whether the section exists

<!-- Open Question 1 (design.md, `the-phases-are-derived-not-remembered`):
resolved block-level — every `rw-*` block carries `optional: true` in the
front matter. No schema change, no `_TOP_LEVEL_ALLOWED` widening. This is
what "the whole section is conditional" means at the block granularity the
contract already speaks. -->

This is one decision with two criteria, and either one is enough to create the
section:

- **Does the lineage need more than one paragraph per problem?** If every problem is
  discharged in a single paragraph, the material stays compressed in the
  introduction.
- **Is the comparison table wanted?** The synthesis artefact lives here and nowhere
  else.

**If the section does not exist:** there is no panorama paragraph, there is no
synthesis artefact anywhere in the paper, and the introduction's state-of-the-art
block expands to one paragraph per stated problem. The table does not move to another
section — it is lost together with the section.

The decision governs two places at once, so it is taken before drafting either.

## Global structural rule

Five blocks. The third repeats — once per stated problem.

1. preamble
2. general panorama of the problem
3. one block per specific problem
4. closing: open fronts and the gap
5. synthesis artefact

### Directives: Correspondence with Introduction's Families & Subsection Triad
Organized in direct correspondence with the 3 to 7 methodological families or alternatives established in Paragraphs 3 and 4 of the Introduction:
- **Opening Context Paragraph:** A first paragraph giving context to the problems and methods studied, directly framing the families that follow.
- **Subsections per Family:** Each family introduced in the Introduction's state of the art receives its own dedicated subsection (`\subsection{...}`).
- **Internal Subsection Triad (2 to 3 paragraphs each):**
  1. *Foundations (Fundamentos)*: theoretical roots, mathematical formulation, and operational assumptions.
  2. *Main Methods (Métodos principales)*: primary architectures, key representative algorithms, and benchmark works.
  3. *Main Challenges (Principales desafíos)*: critical bottlenecks, open failure modes, and unresolved issues.
- **Citation Volume:** Each family subsection must cite between 5 and 10 distinct alternative works.
- **Reference Horizon:** Between the Introduction and Related Work, the manuscript must collectively cite between 30 and 40 references.

**The organizing principle is one unit per stated problem**, the same principle that
governs the introduction's state-of-the-art block. What differs is what the unit is
made of: a paragraph in the introduction, a block of paragraphs here.

**The cut between the two places:** the introduction retains, per problem, the family
whose limitation motivates the contribution. Everything else that attacked that same
problem is a variant, and it lives here.

## Block 1 — Preamble

One paragraph of about 40 words, two sentences, **no citations**. It names the blocks
that follow and their order. Nothing else.

It is the only paragraph in the section that does not close on a limitation, because
it characterizes no family.

## Block 2 — General panorama of the problem

One paragraph, about 150 words. Take the **general problem** — the one that names the
paradigm, not the difficulties — and state the whole trajectory the literature
travelled: where the field came from and where it moved.

It is panorama, not review: develop no family and attribute no particular limitation.
Its job is to let the blocks that follow start directly on their problem.

## Block 3 — One block per specific problem

As many blocks as the problem statement declares specific problems. Two or three.
Each block is made of:

- **one paragraph carrying the main lineage** — the same family the introduction
  retained, here with its full progression;
- **one or two further paragraphs** carrying the variants, the alternative
  strategies, and the partial attempts that attacked the same problem and that the
  introduction left out.

Every paragraph closes on the limitation of its family. Every block closes on what
none of its families resolved.

**Each block opens by naming its problem and stating its own trajectory** before
walking it, and **starts from the close of the previous block**: the deficiency the
previous problem ended on is what motivates the next. The blocks are a chain, not
parallel islands.

Paragraph size: 130–300 words. Nothing in this section runs longer than 300 words.

**The blocks weigh about the same.** A block of 700 words against one of 220 says the
second problem was mentioned rather than reviewed.

### Two ways to walk a block, chosen by the nature of the problem

**Chronological** — when the problem is *how has this task been solved*. A task has a
history.

1. the founding family, with what it provides and its structural limitation;
2. intermediate families, one paragraph each, each starting from the previous
   limitation;
3. the most recent family, which is either the one the proposal **adopts** — and the
   paragraph closes by saying why it is suitable — or the one it **displaces**, and
   the paragraph closes on a limitation.

**Taxonomic** — when the problem is *how has this property been achieved*. A property
has no history; it has types.

1. state the whole taxonomy in a short paragraph that develops none of it;
2. declare which branch is the relevant one and why;
3. walk that branch, family by family, each paragraph on its limitation.

Because the unit here is a block and not a paragraph, a discarded branch can take a
paragraph of its own instead of a single sentence. That is what the extra room in
this section is for.

## Block 4 — Closing: open fronts and the gap

One paragraph, 100–125 words, 3 to 5 sentences.

1. **A recapitulation formula.**
2. **Name the fronts left open — as many as there are blocks.** Two blocks, two
   fronts.
3. **State which of them the proposal attacks**, closing on the proposal by name.

**The gap is not always methodological.** A work may be limited by its mechanism, but
also by the **task** it solves or by the **data** it uses: close in method and remote
in scope. When the gap is one of scope rather than mechanism, say so explicitly — a
reader who knows that work will otherwise wonder why it did not already suffice.

## Block 5 — Synthesis artefact

A comparison table by default; an evolution figure only when the lineage, not the
comparison, is the point. Either form places **7 to 12 works**, the proposal's row
not counted.

**Its dimensions are the properties on which the proposal wins** — they are derived
from the contributions, not from whatever is easy to tabulate. The proposal's row is
the only one holding every column.

It goes after the closing, preceded by **a one-sentence pointer paragraph that names
the dimensions in the body** before the table appears. The variant is one artefact
per block of block 3, placed at that block's close; in that case the pointer is the
block's last sentence, and the 7 to 12 works are counted across those artefacts.

Name the dimensions in the body, never only in the table header.

### The synthesis table

**Rows: 7 to 12 works, then the proposal as the last row.** A work earns a row by its
relevance to the paper's pillars and contributions — the strongest representative of
its family on the properties the proposal claims, not the most cited or the most
recent. Every family this section develops has at least one row; a family with
several rows keeps them adjacent.

**Columns: the family, then the comparison axes.** Each axis is one pillar,
contribution or property the proposal declares, named in the body's pointer sentence.
An axis every row satisfies separates nothing and is dropped; so is an axis no
contribution claims.

**The redactor chooses the layout that reads fastest and states why in one line of
its account:**

- a **checkmark matrix** when every axis is a yes/no property;
- a **compact attribute table** when an axis takes a short value (a data regime, a
  model class, a validation scheme);
- **rows grouped by family** — a `\multicolumn` label row per family, or a family
  column — when several works share a family and the grouping is itself the argument.

**Cells are concise and exact:** a symbol (`\checkmark`, `--`, a partial mark) or at
most three words. No sentence, no clause, no citation-only cell. The caption is the
legend: it decodes every symbol and abbreviation the cells use, so the table reads
without the body. The citation goes in the work's own cell, once.

**It fits the text block.** `booktabs` rules and a `tabularx` at `\linewidth`, under
the table rules of contracts 02 and 03 (*Tables stay inside the text block*): the same
text range (0.70 to 0.90 times the body size), no scaling to fit, and a table too wide is split or transposed, never
shrunk.

## Every artefact is referenced before it appears

The synthesis artefact — and any other figure or table this section carries — is
referenced in the body **before** it appears, with the pointer resolving to the exact
sub-element when it has parts. An artefact appearing with no prior reference is either
misplaced or dead.

## Thematic, not catalogue

The paragraph is about **families**, not about individual works. The subject of the
sentences is the family or the capability.

**Reliable marker of cataloguing: the citation used as a noun phrase** — *the work in
[N] uses*, *the method of [N] combines*. If it appears, the section is cataloguing.

**Soft signal: fewer than twenty words per sentence.** A thematic paragraph runs 24 to
27; a catalogue drops to 13–18 because it packs one short sentence per work. This is
an indication, not proof — the ranges touch at the edge.

The underlying reason: **a catalogue cannot close on a gap, because it never produced
one.** If the paragraph enumerates works instead of characterizing families, nothing
is left to synthesize.

## Citations

- **At the end of the sentence it supports.** One sentence, one attributed claim. A
  sentence that would need two citations is two sentences. Collapse ranges.
- **Never as a noun phrase.**
- **Two to six per paragraph.** That is the actionable number; the total of distinct
  references is the consequence, not the target.
- **Every limitation attributed to prior work carries a citation**, preferably one
  from that literature rather than from the authors themselves.
- This section is not necessarily more cited than the introduction. What changes is
  the depth per family.

## LIA house style

Measured on the group's ten Q1 method papers of 2025–2026 (SJR 2025): items A003, A006, A007, A009, A012, A013, A021, A022, A023 and A026 of the lab's bank of articles. Ranges are minimum–median–maximum across the papers that have the section; a typeset line is about 12 words in a single-column layout. The ranges describe how the group writes; the extent at the top of this contract stays the target.

**Measured size, in the three papers that keep this section.** 6–13–22 paragraphs;
604–1723–2264 words, about 53–149–201 lines; 101–103–133 words per paragraph; 2–3–5
subsections; 19–31–35 citations, 2.7–3.2 per paragraph. The other seven carry the
state of the art inside the introduction.

**Citations.** Numeric, in square brackets. Most markers cite one work; a group cites
at most four, listed with commas (`[31,32,33,34]`), never as a range. A citation closes
the sentence it supports, or follows the name of the method it credits; it is never
the subject of a sentence (*ref. [29] presents*).

**The section can close on a comparison table** that sets the proposal's properties
against the works reviewed: 7 to 12 representative works, every family with at least
one row (Block 5).

**Writing.**

- **Sentences average 21–27 words.** Long enough to carry one claim and its qualifier, never a chain of three clauses.
- **One voice for the whole paper.** First person plural (*we propose*) or impersonal (*this work introduces*), chosen once; procedures that were run go in the passive past (*was evaluated using*).
- **Transitions come from the relation between claims, not from a list.** Name the relation first (contrast, cause, consequence, elaboration, example) and carry it with the sentence's own content: a clause (*yet*, *so*, *although*), a subject that points back (*that gap*, *this cost*), or no connector at all when the order of the sentences already says it. A stock connector (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) is the exception: never the same one twice within five sentences, never most of a paragraph's openings, and a synthesis opener (*Overall*, *Taken together*) at most once per section.
- ***because* and *where* keep their jobs.** *because* states a cause the method or the data establish, at most once every few sentences and never stacked (*because …, and because …*); *where* opens the clause after an equation that defines its symbols, and nowhere else in prose (use *in which*, *when*, or two sentences). An evaluation is its own sentence, not a trailing *, which indicates …*.
- **The method has one name.** Expanded with its acronym at first use in each of the abstract and the body, then *the proposed* followed by the acronym.

## Inputs per block

**Nothing here depends on a measurement.** The section is written in full before a
single experiment runs. Every block traces back to the problem statement, which comes
from the contributions, which come from the mathematical formulation — the root of
this section is the formulation.

### External inputs

| Input | Unblocks |
|---|---|

### Internal chain

| Block | Depends on |
|---|---|
| `related-work.rw-preamble` — The list of specific problems — to announce the blocks and their order | `introduction.block-2` — the problem statement, general and specific, decomposed there |
| `related-work.rw-panorama` — The general problem of the problem statement | `introduction.block-2` — the problem statement, general and specific, decomposed there |
| `related-work.rw-problem-blocks` — The specific problems, one block each | `introduction.block-2` — the problem statement, general and specific, decomposed there |
| `related-work.rw-closing` — names the fronts left open, as many as there are blocks | `related-work.rw-problem-blocks` — the specific-problem blocks whose unresolved limitation each becomes a named front |
| `related-work.rw-synthesis-artefact` — The properties (contributions) the proposal declares | `materials-and-methods.mm-proposal` — the enumerated contributions the synthesis artefact tabulates |

**The referent moved.** This block's `components_from` resolves against the methods
section now, not the introduction — a real cross-section check still, only its
source changed.

**Cross-obligation.** The gap is stated in two places — the closing of this section
and the closing of the introduction's state-of-the-art block — and they must say the
same thing at different depths.

## Disqualifiers

- A block that corresponds to no stated problem.
- A stated problem with no block.
- A preamble that reviews a family, or that carries a citation.
- A panorama that attributes a limitation to a particular family.
- A paragraph that does not close on a limitation.
- A block that does not close on what none of its families resolved.
- A block that does not start from the close of the previous one.
- A limitation attributed without a citation.
- A paragraph over 300 words.
- Blocks of grossly unequal weight.
- The closing paragraph missing.
- Fronts named in the closing that do not match the number of blocks.
- The synthesis artefact missing.
- An artefact whose dimensions are not the properties the proposal declares.
- Dimensions named only in the table header and not in the body.
- Fewer than 7 or more than 12 works in the synthesis table, the proposal's row not counted.
- A family of this section with no row in the synthesis table.
- A synthesis-table column not tied to a pillar, contribution or property the proposal declares, or one every row shares.
- A sentence or clause as prose in a synthesis-table cell, or a symbol the caption does not decode.
- An artefact that appears before any reference to it, or that nothing references at
  all.
- A citation used as a noun phrase.
- A citation anywhere but at the end of the sentence it supports.
- An equation.
- A family developed both here and across the introduction's state-of-the-art block:
  when this section exists, that block is a summary.
- A variant named in the introduction: variants belong here.
- The gap of this section and the gap of the introduction disagreeing.
- Related Work lacking the opening context paragraph framing the problems and methods studied.
- Any methodological family introduced in the Introduction's state of the art lacking its dedicated subsection.
- A family subsection with fewer than 2 or more than 3 paragraphs, or omitting foundations, main methods, or main challenges.
- Fewer than 5 or more than 10 alternatives cited per family.
- Total combined references between Introduction and Related Work outside the range of 30 to 40.
