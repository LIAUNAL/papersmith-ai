---
{
  "section": "introduction",
  "position": 3,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/06-introduction.md",
      "quote": "Six argumentative functions, in fixed order, distributed across seven canonical paragraphs."
    }
  },
  "blocks": [
    {
      "id": "block-1",
      "requires_facts": [
        {
          "value": "dataset",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "The dataset — the condition, population, or process it contains"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery"
    },
    {
      "id": "block-2",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "this block is derived from the contributions, read backwards"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "produces_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "Turn the general need into a concrete technical problem, and decompose it into the specific problems the proposal resolves."
          }
        }
      ],
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "this block is derived from the contributions, read backwards"
          }
        }
      ]
    },
    {
      "id": "block-3",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "Block 3 — state of the art and gap depends on the problem statement when there is no Related Work section"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "produces_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "The closing is the joint gap, and the conjunction is what makes it a gap."
          }
        }
      ],
      "after": [
        {
          "target": "introduction.block-2",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "Block 3 — state of the art and gap depends on the problem statement when there is no Related Work section"
          }
        },
        {
          "target": "related-work",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "When a Related Work section exists, this block is written after it."
          }
        }
      ]
    },
    {
      "id": "block-4a",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "the core idea comes from the methods section, where the proposal is defined and named"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "introduction.block-2",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "the presentation and the purpose clause come from block 2 — the clause mirrors its specific problems, in the same order"
          }
        },
        {
          "target": "introduction.block-4b",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "the announcement of the count comes from `introduction.block-4b`, in its partial form."
          }
        },
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "the core idea comes from the methods section, where the proposal is defined and named"
          }
        }
      ]
    },
    {
      "id": "block-4b",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "The results"
          }
        },
        {
          "value": "contributions",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "It is inherited, never a drafting target."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "It is inherited, never a drafting target."
          }
        }
      ]
    },
    {
      "id": "block-5",
      "requires_facts": [
        {
          "value": "experimental-design",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "The experimental design — scenarios, comparisons, criteria, complementary analyses"
          }
        },
        {
          "value": "results",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "The results"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "block-6",
      "requires_facts": [
        {
          "value": "skeleton",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "The section skeleton of the manuscript"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---
# Introduction

**Extent** 750–1380 words · 7 paragraphs
**Does not carry** equations, figures, or tables
**Carries** 18–41 distinct references, concentrated in blocks 1 to 3

## Global structural rule

Six **argumentative functions**, in fixed order, distributed across seven canonical paragraphs.
Function and paragraph are not the same unit: the state-of-the-art function takes two
paragraphs (3 and 4), every other function takes one.

1. why the topic matters
2. which concrete problems must be solved
3. existing solutions solve them only in part
4. a proposal whose contributions answer those problems
5. how each promised property is validated
6. how the rest of the article is organized

### Canonical Seven-Paragraph Structure
The introduction has exactly seven paragraphs. The paragraph count is fixed; the
block extents below are written to fit it, and no block adds a paragraph of its own.

1. **Paragraph 1 (General Application Context)** — `block-1`, 145–200 words: general context of the application domain and motivating phenomenon.
2. **Paragraph 2 (AI Context & Problem Statement)** — `block-2`, 130–220 words: context of AI techniques in said application, ending with two or three sentences declaring the technical problem and its root causes (taken from the conceptual map & model panel and foundational pillars; strictly continuous running text, with no bullet items, no bold text highlights, and no numbered questions).
3. **Paragraph 3 (State of the Art, first families)** — `block-3`, 130–300 words: the first methodological families of the state of the art, with their primary methods, main strengths and issues/limitations.
4. **Paragraph 4 (State of the Art, remaining families and joint gap)** — `block-3`, 130–300 words: the remaining families, in the same form, closing on the joint gap. Paragraphs 3 and 4 together present 3 to 7 families.
5. **Paragraph 5 (Proposal & Contributions)** — `block-4a` + `block-4b`, 120–180 words: the proposal presentation ending in a colon, followed by its contributions described in 3 to 4 short items. The list continues the paragraph; it is not counted as a paragraph of its own.
6. **Paragraph 6 (Evaluation, Results & Impact)** — `block-5`, 65–135 words: summary of experiments conducted, comparison methods and evaluation criteria, most significant empirical results obtained, and potential impact of the work.
7. **Paragraph 7 (Roadmap/Agenda)** — `block-6`, 32–42 words: agenda of the paper specifying section organization in a fixed roadmap formula.

The word extent at the top of this contract is the sum of these seven ranges, rounded.

**Intended correspondence:** `problem i → state-of-the-art limitation i →
contribution i → property i → instrument i → evidence i`. The chain starts at the
problem, not at the contribution: a contribution delivering a property that no
declared problem needed has nothing motivating it.

**The property carries the same name through every link** — not a synonym, the same
words. If the problem is named one way in block 2, the contribution delivers that,
block 5 names the instrument for that, and the results block is about that. Without
the shared name the chain is interpretable rather than checkable.

The requirement is the strong half: no stated problem is left without an answer, and
no declared property is left without an identifiable form of evaluation. A problem
may be answered by **a component of the proposal or by an analysis in the
evaluation** — not necessarily by a component. The one-to-one correspondence is a
preference, not a requirement.

## Inputs per block

There is no order among these blocks — there is a graph. Each block is drafted as
soon as its input exists. **Two blocks admit a partial form**: they are written from
the design and completed from the measurement.

### External inputs

| Input | Unblocks |
|---|---|
| The **dataset** — the condition, population, or process it contains | 1 |
| The **section skeleton** of the manuscript | 6 |
| The **experimental design** — scenarios, comparisons, criteria, complementary analyses | 5 partial |
| The **results** | 4b complete, 5 complete |

### Internal chain

| Block | Depends on |
|---|---|
| `introduction.block-2` — the general problem and the specific ones | `materials-and-methods.mm-proposal` — each contribution is read backwards as the deficiency it resolves, named in the accepted vocabulary of the field |
| `introduction.block-3` — state of the art and gap, depending on the problem statement | `introduction.block-2` — the problem statement, general and specific, decomposed there |
| `introduction.block-4a` — the presenting prose | `introduction.block-2` — the presentation and the purpose clause, mirroring its specific problems in the same order |
| `introduction.block-4a` — the presenting prose | `introduction.block-4b` — the announcement of the count, stated before the list enumerates it |
| `introduction.block-4a` — the presenting prose | `materials-and-methods.mm-proposal` — the section that defines and names the proposal, from which the core idea is drawn |
| `introduction.block-4b` — the list of contributions, inherited rather than drafted | `materials-and-methods.mm-proposal` — the section that defines and names each contribution |

### Structural decisions

- **Block 3 — state of the art and gap** depends on the problem statement
  when there is no Related Work section — its own `after` edge to
  `introduction.block-2` carries this now that `problem-statement` is a
  produced-class fact — **and** the problem statement **and the written
  Related Work section** when a Related Work section exists — the
  conditional cross-section case this block's own second `after` edge to
  `related-work` carries.
- **`introduction.block-4a` / `block-4b` are two blocks, not one.** They
  share canonical paragraph 5 — the prose (`Paragraph 4a - the prose`)
  ending in a colon, then its list (`Paragraph 4b - the list`), 120–180
  words in total. They are separate ids because they are drafted
  from different inputs: 4a's purpose clause depends on block 2, while 4b's
  contribution list is inherited directly from
  `materials-and-methods.mm-proposal`, never from block 2. 4a itself also
  depends on 4b, for the announced count. Collapsing them into one node
  would conflate a block that needs the problem statement with one that
  does not.
- **Composite parts within `introduction.block-4b`** (settled decision 5):
  4b's complete form — the effect each contribution achieves — is drafted
  after its partial form, once the results arrive. A drafting-sequence note
  inside one node, never a dependency on a sibling block.
- **Composite parts within `introduction.block-5`**: 5's complete form — the
  evidence sentence — is drafted after 5's partial form, once the results
  arrive. The same intra-node sequencing as block 4, never a dependency on a
  sibling block.

**Block 4a draws on three sources, one per sentence:**

- the **presentation and the purpose clause** come from block 2 — the clause mirrors
  its specific problems, in the same order;
- the **core idea** comes from the methods section, where the proposal is defined and named;
- the **announcement of the count** comes from `introduction.block-4b`, in its partial form.

### What is writable before measuring

With the proposal formulated and the dataset chosen, before a single experiment has
run, blocks **1, 2, 3, 4a, 4b in partial form, and 6** are all draftable. With the
experimental design settled, **5 in partial form** is added.

The results contribute only the closing of two blocks that are already written: the
achieved effect of each contribution, and the evidence sentence. The introduction is
built in full before measuring; measuring completes it, it does not originate it.

### The loop that must be closed by hand

**The results rule.** They can contradict the effect a contribution promised, and
when they do, the text is corrected to match them — never the reverse.

The correction does not stop at 4b. Block 2 was derived from that contribution, and
block 3 from block 2. On completing 4b, walk the chain backwards and verify that
every stated problem still has an answer and that no contribution is left without a
problem motivating it. This is the only point in the section where measurement can
invalidate what is already written.

In practice most of the chain survives, which is why the graph is worth following
rather than waiting: a contradicted effect usually revises one item and one clause,
not the argument.

## Block 1 — Contextualization

**Function.** Introduce the application domain and the phenomenon motivating the
work, its relevance, and the general need that justifies studying it.

**Sequence.** domain → phenomenon of interest → relevance → general need.

**Extent.** One paragraph (canonical paragraph 1), 145–200 words. Never two.

**The phenomenon is fixed by the data, not by the method.** Anchor the context in the
condition, population, or process that the dataset actually contains. Changing the
dataset rewrites this paragraph entirely even when the method is identical: state
domain, phenomenon, and relevance over what was measured, not over the family of
techniques employed. A context written about the method leaves the reader without
knowing what the work is about.

**Do not name the dataset here.** What anchors the context is the condition,
population, or process, not the dataset's name — the name belongs to block 5.

**Scale change inside one paragraph.** The paragraph must traverse all four
dimensions and close by leading into the technical problem. When the move from broad
domain to specific scenario requires an explicit change of scale — from the general
field to the concrete population, institution, or territory of the study — make it
with one transition sentence inside the paragraph, never by splitting it.

**Does not belong here.** The proposal, its name, its components, its contributions,
or any experimental detail.

## Block 2 — Problem statement

**Function.** Turn the general need into a concrete technical problem, and decompose
it into the specific problems the proposal resolves.

**Paragraph 2 Directives (AI Context & Problem Statement):** Context of the AI techniques used in the application domain, terminating in two or three sentences that declare the concrete problem and its causes (drawn from the conceptual map, model panel, and pillars). Must be redacted without items/bullet points, in coherent running prose, without bold highlights, and without numbered questions (strictly continuous text).

**Sequence.** general problem → specific 1 → specific 2 → [specific 3] →
requirements an adequate solution should satisfy.

**Extent.** One paragraph (canonical paragraph 2), 130–220 words.

**Nest the problems: a general one naming the paradigm, and the specific ones inside
it.** The general problem is the name of the field or the task, not a difficulty; the
specific ones are the difficulties. State the general one first, acknowledging that
it is only partially resolved, and open the enumeration only after that.

**Name the problems with the accepted terminology of the state of the art.** This is
not cosmetic: the name of each problem is the search key with which block 3 will find
its literature. A problem described in private vocabulary instead of the field's has
no methodological family addressing it, and block 3 is left with nothing to chain.

**Each specific problem corresponds to a capability the proposal incorporates** —
which is why this block is derived from the contributions, read backwards. Introduce
no difficulty that the work will not address.

**Close by consolidating the requirements** an adequate solution should satisfy. That
closing is what enables the gap in block 3, and its terms are the axes the evaluation
will measure: state them in the same words block 5 will later use.

**Count.** Two or three specific problems.

## Block 3 — State of the art and gap

**Function.** Present the families of methods that have addressed the problems of
block 2, organized **around those problems and not as an enumeration of works or
authors**.

**Paragraphs 3 & 4 Directives (State of the Art across 3–7 Families):** Indicate between 3 to 7 methodological families or alternatives of the state of the art. For each family, present the primary representative methods alongside their key strengths and critical issues/limitations.

**Per family:** which problem it addresses → what advantage it provides → what
limitation it retains.
**Overall:** existing solutions → advances → limitations → joint gap.

**Extent. Always two paragraphs — canonical paragraphs 3 and 4 — 130–300 words each,
260–600 words in total.** Whether the article has its own Related Work section changes
what the two paragraphs contain, never how many there are. That is a decision about the
structure of the manuscript, and it is taken before drafting the block.

**The unit is the family, tied to the problems.** The 3 to 7 families are distributed
across the two paragraphs in the order of the problems of block 2, and each family
states which of those problems it addresses: that is what keeps the correspondence with
block 2 explicit. Paragraph 3 carries the first families; paragraph 4 carries the
remaining ones and closes on the joint gap. Expand each method's nomenclature on first
appearance.

**With a Related Work section, the two paragraphs summarize it.** Per family: its
primary methods, its main strength, and the limitation that motivates the contribution.
The families are the same ones, in the same order, as that section's subsections.
Variants and alternative strategies are not named here — they live in the section.

**When a Related Work section exists, this block is written after it.** It summarizes
the section, and a summary cannot precede what it summarizes. Without that section,
the block depends only on the problem statement.

**The cut between the two places:** this block retains, per family, its primary methods
and the limitation that motivates the contribution. Everything else that attacked the
same problem is a variant, and it belongs to the dedicated section.

**Without a Related Work section, the two paragraphs carry the whole state of the
art.** Per family: its representative methods walked in progression, its strengths, and
what it left unresolved.

**No panorama paragraph is added to the introduction:** blocks 1 and 2 already do that
work, and duplicating it is noise.

**The progression chains.** Each paragraph, and each family within a paragraph,
starts from the limitation of the previous one, and that chaining is explicit in the
opening sentence: the new family appears *because* the previous one failed at
something named. A chronological enumeration that does not chain limitations is not a
state of the art — it is a list.

**The closing is the joint gap, and the conjunction is what makes it a gap.** It is
not enough to say that each family has limitations: establish that existing solutions
resolve the problems **separately and not simultaneously**, and therefore do not
jointly satisfy the requirements stated at the end of block 2. The word expressing
that simultaneity must be present.

**When a Related Work section exists, this gap and that section's closing gap say the
same thing at different depths.** They are one claim stated twice, and they must
agree.

**No ordering exception.** When the problem cannot be stated without first presenting
the enabling technology, paragraph 2 presents it as part of its AI context; block 3 is
never split around block 2.

## Block 4 — Proposal and contributions (`block-4a`, `block-4b`)

**Function.** Present the method by name and purpose, the core idea articulating its
components, and enumerate the contributions.

**Sequence.** presentation → overall objective → core idea → contribution 1 → 2 → …

**Extent. One canonical paragraph (paragraph 5), 120–180 words in total:** the prose
of 4a ending in a colon, followed by the list of 4b, which continues the paragraph.

### Paragraph 4a — the prose. Three movements, two or three sentences.

1. **Presentation and objective.** Full name, acronym in parentheses, the category of
   the artefact, and a purpose clause **mirroring the specific problems of block 2 in
   the same order**. Introduce it with the hinge in the paper's one voice — impersonal
   *To address these limitations, this work introduces* (the LIA default) or
   first-person plural *we propose* when the paper chose that voice — and use that hinge
   **exactly once in the whole introduction**: everything before it is other people's
   work.
2. **The core idea.** One sentence, one mechanism, without mathematics and without
   symbols. It is what makes the proposal new, not what it does.
3. **The announcement.** Close the paragraph by stating the number of components and
   ending in a colon, which is what opens the list. Announce the count before
   enumerating it, always.

### Paragraph 4b — the list.

**The contributions are described in 3 to 4 short items.**
The number of items is the number of contributions the proposal has. It is
inherited, never a drafting target. The 3-to-4 range is a requirement on the
proposal, checked where the contributions are defined: when the methods section
defines fewer than three or more than four, the fix is made there — merging or
splitting components — never by padding or trimming this list. What drafting requires
here is only that the count be announced in 4a before being enumerated, and that the
list agree in count, order, and naming with the components of the methods section.

Open each item with **the name of the component followed by a colon**, and continue
with a single sentence stating what it does and which previously stated problem it
resolves. Those names are the methods section's own contract — this list uses the
same ones, in the same order.

**The name is written in plain text, never in bold** and never as a description
label: `\item Circular data re-uploading: …`, not `\item \textbf{Circular data
re-uploading:} …` or `\item[Circular data re-uploading:] …`. The list already sets
each item apart; a bold name on top of it reads as a generated outline. `write`
refuses a draft of this section whose paragraph or item opens on emphasis
(`DRAFT_BOLD_LEAD_IN`).

Do not open items with a first-person verb instead of a component name: without a
name, the component cannot be referred to again later.

**The achieved-effect clause is the part that waits for the results.** What each
contribution introduces and what function it performs come from the formulation; the
effect it is claimed to achieve comes from the measurement.

**One citation only, in 4a.** Paragraph 4a may cite the prior work the proposal extends, attached to it; from 4b to the end of the introduction, cite nothing.

## Block 5 — Evaluation of the proposal

**Function.** Summarize how the proposal is validated, in direct correspondence with
the stated contributions.

**Paragraph 6 Directives (Evaluation, Results & Impact):** Summarize the experiments conducted, comparison methods and evaluation criteria, the most significant results obtained, and the potential impact of the work.

**Sequence.** evaluation scenario → data or tasks → comparison methods → criteria or
metrics → complementary analyses → general evidence → potential impact.

**Extent.** One paragraph, 65–135 words.

**Name everything by its proper name:** the datasets, the methods compared against,
and the axes over which the comparison is swept. Name the complementary analyses too,
because they are what answer the properties no contribution covers — typically the
ones that are not about performance.

**Naming a dataset here does not credit it.** No citation appears in this block. An
external dataset carries a credit obligation, and it is discharged where the dataset
is described — in the datasets subsection — with its reference there. Naming it here
without a reference is correct; leaving it unreferenced where it is described is not.

**Every property declared in block 4 must have its identifiable form of evaluation
here.** Performance, robustness, interpretability, stability, efficiency, coherence,
generalization: if it was promised, it is evaluated, and this is where the instrument
is named — **under the same name the problem and the contribution gave it**.

**The first five movements come from the experimental design; only the closing comes
from the results.** Scenario, data, comparisons, criteria, and complementary analyses
are all decidable before anything runs.

**Close in evidence, not in values.** State the direction of the result and the axes
on which it improves, without quoting any figure, percentage, or table. Numbers
belong to the results section.

## Block 6 — Organization of the article

**Function.** Orient the reader about the structure. Nothing more.

**Extent.** One paragraph, 32–42 words.

It is a fixed formula:

`The remainder of this paper is organized as follows: Section [N] [verb] the [content]. … Finally, Section [N] [verb] the concluding remarks.`

- One clause per section, in order.
- Each section appears in exactly one clause. Adjacent sections with a related
  function may share one.
- The verb varies by section (`introduces`, `presents`, `describes`, `reviews`,
  `details`, `discusses`).
- The final clause opens with `Finally,` or `Lastly,`.

**Introduce no new argument, problem, contribution, method, or result.**

## LIA house style

Measured on the group's ten Q1 method papers of 2025–2026 (SJR 2025): items A003, A006, A007, A009, A012, A013, A021, A022, A023 and A026 of the lab's bank of articles. Ranges are minimum–median–maximum across the papers that have the section; a typeset line is about 12 words in a single-column layout. The ranges describe how the group writes; the extent at the top of this contract stays the target.

**Measured size.** 7–9–15 paragraphs; 850–1166–1604 words, about 73–102–139 lines;
105–123–178 words per paragraph; no subsections, equations, figures or tables;
23–27–45 citations, 1.7–4.2 per paragraph.

**The moves the group's introductions make**, ten of ten: the stakes of the
application, often anchored in a public health or societal goal; the difficulties of
the data; the families of prior methods, each closed by a sentence opening on
*However* that names its limitation; the joint gap; the proposal, introduced by the
hinge *To address these limitations, this work introduces* followed by the full name and
the acronym in parentheses; the contributions, as a list announced by *The main
contributions of this work are as follows:*; and the closing roadmap, *The remainder
of this paper is organized as follows:*.

**Citations.** Numeric, in square brackets. Most markers cite one work; a group cites
at most four, listed with commas (`[31,32,33,34]`), never as a range. A citation closes
the sentence it supports, or follows the name of the method it credits; it is never
the subject of a sentence.

**Writing.**

- **Sentences average 21–27 words.** Long enough to carry one claim and its qualifier, never a chain of three clauses.
- **One voice for the whole paper.** First person plural (*we propose*) or impersonal (*this work introduces*), chosen once; procedures that were run go in the passive past (*was evaluated using*).
- **Transitions come from the relation between claims, not from a list.** Name the relation first (contrast, cause, consequence, elaboration, example) and carry it with the sentence's own content: a clause (*yet*, *so*, *although*), a subject that points back (*that gap*, *this cost*), or no connector at all when the order of the sentences already says it. A stock connector (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) is the exception: never the same one twice within five sentences, never most of a paragraph's openings, and a synthesis opener (*Overall*, *Taken together*) at most once per section.
- ***because* and *where* keep their jobs.** *because* states a cause the method or the data establish, at most once every few sentences and never stacked (*because …, and because …*); *where* opens the clause after an equation that defines its symbols, and nowhere else in prose (use *in which*, *when*, or two sentences). An evaluation is its own sentence, not a trailing *, which indicates …*.
- **The method has one name.** Expanded with its acronym at first use in each of the abstract and the body, then *the proposed* followed by the acronym.
- **Present and present perfect.** The field *has addressed*; the problem *remains*.
- **Novelty is stated by contrast, not by priority.** *Unlike previous approaches,
  the proposed …*; a claim of being first appears only when the state of the art was
  searched for it.

## Cross-cutting conventions

- **Place the citation at the end of the sentence it supports.** One sentence, one
  attributed claim. A sentence that would need two citations is two sentences.
  Collapse ranges.
- **Do not use the citation as a noun phrase** — *the work in [N] does X*, *the
  method of [N] combines*. It turns the argument into a catalogue of individual works
  instead of an account of families.
- **Density:** one citation every one or two sentences in blocks 1 to 3; **no
  citations from block 4 onward, except the prior work 4a extends**.
- **Every assertion about the field carries a citation.** Assertions about the
  proposal itself carry none.
- **Expand acronyms on first appearance**, the acronym alone thereafter — including
  the proposal's own.
- **State the count before enumerating**, in any block that enumerates.
- **No equations, figures, or tables anywhere in the section.**

## Disqualifiers

- An equation, a figure, or a table.
- A context written about the family of methods instead of the phenomenon the dataset
  contains.
- The dataset named in block 1.
- A dataset named in block 5 and left unreferenced where it is described.
- More than one paragraph of contextualization.
- A specific problem answered by neither a component of the proposal nor an analysis
  in the evaluation.
- A problem named in private vocabulary instead of the accepted terminology of the
  field.
- Block 2 without its closing statement of requirements.
- A paragraph of block 3 that does not end in a limitation.
- Block 3 without a joint-gap closing, or with a gap stated as a sum of separate
  limitations.
- This block's gap and the Related Work section's closing gap disagreeing.
- Block 3 in other than two paragraphs, or outside 260–600 words.
- A variant or alternative strategy named in block 3 when a Related Work section
  exists: those belong to that section.
- Block 3 written as a summary of a Related Work section that does not yet exist.
- A panorama paragraph added to the introduction.
- The count announced in 4a not matching the number of items in 4b.
- The list in 4b differing in count, order, or naming from the components of the
  methods section.
- A contribution motivated by no problem in block 2.
- A property declared in block 4 with no evaluation named in block 5.
- A property named differently in blocks 2, 4 and 5 — a synonym instead of the same
  words.
- A figure, percentage, or value in block 5.
- A citation anywhere from block 4 onward, other than 4a's citation of the prior work the proposal extends.
- A citation placed anywhere but at the end of the sentence it supports.
- A citation used as a noun phrase.
- Block 6 missing, or naming sections that do not exist, or repeating one.
- A completed 4b whose achieved effects were not checked back against block 2 and,
  through it, block 3.
- Bullet items, lists (`itemize`, `enumerate`), bold text highlighting, or numbered questions in Block 2 (Paragraph 2).
- Block 3 presenting fewer than 3 or more than 7 methodological families or alternatives, or omitting their strengths and issues.
- Block 4 presenting fewer than 3 or more than 4 contribution items.
- A contribution item that opens in bold or as a description label.
- Block 5 omitting the comparison methods, evaluation criteria, or potential impact.
- An introduction deviating from the canonical seven-paragraph sequence.
