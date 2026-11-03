---
{
  "section": "results-and-discussion",
  "position": 7,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/03-results-and-discussion.md",
      "quote": "The discussion is inferential by default and assertive by exception."
    }
  },
  "blocks": [
    {
      "id": "rd-general-task",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "The results — the main runs, against the baselines"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "rd-contribution-blocks",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "The property a contribution promised, and the instrument the setup named for it"
          }
        },
        {
          "value": "results",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "Input the results of the experiments"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "results-and-discussion.rd-general-task",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "A mechanism block opens by naming the previous block's result as the question it comes to answer."
          }
        },
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "The property a contribution promised, and the instrument the setup named for it"
          }
        }
      ]
    },
    {
      "id": "rd-cost",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "Input the results of the experiments"
          }
        },
        {
          "value": "implementation",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "The implementation — the most demanding configuration, and the hardware declared in the setup"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "optional": true,
      "after": [
        {
          "target": "results-and-discussion.rd-contribution-blocks",
          "source": {
            "file": "sections/03-results-and-discussion.md",
            "quote": "A mechanism block opens by naming the previous block's result as the question it comes to answer."
          }
        }
      ]
    }
  ]
}
---
# Results and Discussion

**Extent** 1170–4150 words · two to five content blocks, plus limitations last
**Input** the results of the experiments
**Carries** 3–12 figures and 0–8 tables — the artefact-densest section of the paper
**Does not carry** a preamble, a closing artefact, or a single numbered equation

## One section, never two

The discussion is not a block. There is no separate stretch of discussion prose: the
discussion is **the third beat of every artefact reading, in the same paragraph as
the number it explains**. That is why the two are one section and why they cannot be
split.

## Nothing is introduced here

**Every scenario, split, metric, baseline, statistical test, ablation variant,
sensitivity sweep and interpretability measure read in this section was declared in
the experimental setup.** This section applies the protocol and reads what it
produced; it never chooses a test, adds a baseline, or improvises an ablation after
seeing the numbers.

## The blocks

Each block is present when the setup declared what it reads, and only then — the
order below holds for any kind of paper, whatever its domain.

**0. The controlled scenario**, when the setup declared one. First: the proposal on
data whose ground truth is known — synthetic or simulated — showing the property the
problem names under conditions where it can be checked. It is short, and it is what
makes the real-data blocks credible.

**1. The general task.** The evidence that the proposal works on the task it was
built for: the main metric, on the main data, against the baselines. This block
carries the bulk of the section — 40% to 66% of it — and closes on the statistical
test the setup declared.

**2. One block per contribution.** Each validates the property that contribution
promised, using the instrument the experimental setup named for it, in the order the
contributions were defined. **An interpretability contribution is read twice**: what
its explanations show — maps, filters, weights, recovered structure — and how faithful
they are, by the measure the setup declared against the competing explanation
methods. A qualitative reading alone is an illustration, not evidence.

**3. Ablation and sensitivity**, when the setup declared them. One reading per
ablation variant, in the setup's order, each stating what removing that contribution
costs; then each sweep, stating where the proposal is stable and where it is not. This
is the block that shows each contribution earns its place.

**4. Cost, when cost is claimed.** One or two paragraphs, one figure. Measured on the
most demanding configuration, and stated as such so the estimate reads as
conservative.

**5. Limitations.** Last, always, under its own contract.

**A block may close on one synthesis paragraph** — *Taken together*, *Overall* — that
states what the block established and points to its artefacts. The section itself
never closes on one; that is the conclusions' job.

### Organizing by scenario instead

When the work has dissimilar experimental scenarios — different domains, different
data regimes — the blocks may be organized one per scenario, each walking
performance-then-mechanism internally. **The correspondence to the contributions is
still stated**, so the reader knows which block validates which contribution.
Organizing by scenario without saying that is what loses the correspondence.

## The chain that ends here

> **problem *i* → contribution *i* → property *i* → instrument *i* → evidence *i***

The problem was declared in the problem statement, the gap said nobody had resolved
it, the contribution answers it, the setup named the instrument that measures it, and
this section is where the evidence appears. **The property carries the same name
through all five links** — not a synonym, the same words.

The obligation runs both ways:

- **every contribution has a block here**, and
- **every block here belongs to a contribution or to the general task.**

A block belonging to neither is a measurement nobody asked for.

## How a result is presented

The form is the same for a figure and for a table. Two syntactic positions:

**The artefact as grammatical subject**, followed by a reading verb and what it
shows.

**The artefact as a pointer inside the claim** — the form used whenever there is a
value:

> **[the claim in words] + [the value in parentheses] + [the pointer to the artefact]**

**The pointer resolves to the exact sub-element, not to the artefact as a whole.**
When an artefact has parts — panels, columns, row bands, sides, shaded regions — the
pointer names the part. Sending the reader to a whole artefact to find one number is
sending them to look for it.

**The reading verbs are a closed set with a gradient.** Neutral ones say the artefact
displays something: *presents, shows, illustrates, depicts, provides*. Assertive ones
say it establishes something: *reveals, demonstrates, confirms, identifies*. Use the
assertive form only when the artefact settles the point.

## Every artefact is referenced before it appears

Any numbered object — figure, table, or panel — is referenced in the body **before**
it appears. Without exception.

The diagnostic value is the point: **an artefact that appears with no prior reference
is either misplaced or dead.** Applying this rule is how a figure that nothing in the
paper points at gets found.

## The three-beat move

Per artefact: **point at it → read it in numbers → give the mechanism.** All three, in
that order, in the same paragraph. The third beat is what separates reporting from
explaining.

**A number in prose comes with its pointer.** Prose never introduces a value that no
artefact shows.

## The discussion: three registers

The third beat comes in three registers, and they are not interchangeable.

| Register | Share | Form | When |
|---|---|---|---|
| **Inferential** | ~57% | *indicates, suggests, is consistent with, reflects* | the mechanism is inferred from the pattern |
| **Assertive** | ~30% | *because, due to, stems from, is attributed to* | the mechanism is a known property of the formulation or of the data, not an inference from the result |
| **Corroborative** | ~13% | *confirms, reinforces* | the result agrees with an earlier block or with established behaviour |

**The discussion is inferential by default and assertive by exception.** Two out of
three explanations say what the number is *consistent with*, not what *caused* it. A
discussion written entirely in the assertive register is claiming causal knowledge
the experiment did not produce.

**The forms are a range, not a refrain.** Each register lists several forms so the
discussion can vary them: no form opens or links two explanations in a row, and
*because* — the bluntest assertive form — is used at most once per paragraph, never
stacked (*because …, and because …*). An assertive explanation can also be carried by
a verb (*stems from*, *follows from*) or by a colon that introduces the mechanism; an
inferential one can make the evaluation its own sentence rather than a trailing
*, which indicates …*.

**It is anchored.** The explanation sits in the same paragraph as the number it
explains. It never floats.

**It chains between blocks.** A mechanism block opens by naming the previous block's
result as the question it comes to answer.

**The concession belongs to the discussion.** Where a competitor wins a sub-criterion,
say so, and say what the loss buys.

**Three things the discussion does not do:** introduce a claim no artefact supports;
restate the number in words without adding a mechanism; or jump to implications for
practice — that belongs to the conclusions.

## When a contribution has no competitor

Some contributions have nothing to be compared against, because nothing else does
that thing. Three moves, in order:

1. **Project down to a shared space where comparison is possible**, and show
   **parity** there — parity, not superiority. If the contribution operates over more
   dimensions than any competitor, reduce it to the dimension they share and show it
   holds up.
2. **Show what only this contribution produces** — the part no competitor can be
   measured on. There is no comparison there because there is nothing to compare
   with, and that absence is the argument.
3. **If the parity is in fact a loss, concede it and state what is bought with it.**

**The guard:** a conceded loss is paired with a **measured** gain, not an asserted
one. Both point at an artefact. *We lose here but we are better there* holds only if
*there* has its own reported cell. Without this guard, any unfavourable result can be
recycled as a virtue.

**And the deficiency still goes to limitations as an item.** Justified here it reads
defensive; declared there it reads honest, and only there can it earn a future-work
direction.

## The artefact type follows the claim

A grid of numbers is a table. A spatial, temporal, or spectral pattern is a figure.
This is not a stylistic preference: a block whose claim is a comparison across cells
takes tables and may carry no figure at all, while a block whose claim is a pattern
takes figures and may carry no table.

## Citations

Never for a result: the paper's own numbers carry no citation. A citation here
credits **an instrument** used to read the data, or **supports an idea the discussion
relies on**, and those ideas are cited every time:

- an **interpretive** explanation — the mechanism a result is *consistent with* or
  *due to* — cites the work that established that mechanism or that behaviour;
- an analysis of a **baseline** method — why a competitor wins, loses or fails under
  a condition — cites the source of the property it invokes (the baseline's own paper
  or the work that characterized it);
- a **qualitative** interpretability argument — that an attribution map, a saliency
  pattern or a learned structure is plausible — cites the domain knowledge it is
  checked against (physiology, physics, the application's literature).

The corroborative register always carries its citation: what the result *confirms*
is named with its source. The citation attaches to the idea it supports, inside the
sentence that states it.

## Tables stay inside the text block

A table prints inside `\textwidth` at a legible size, by the same rule as a figure
(labels, ticks, legends and annotations included): **every text in a table or a
figure prints between 0.70 and 0.90 times the body font size** (7 to 9 pt in a 10 pt
document): never smaller, and never at the body size.

- **Rules are `booktabs`** — `\toprule`, `\midrule`, `\bottomrule` — with no vertical
  rules; a column of prose is a `tabularx` `X` column, so the table takes the text width
  instead of running past it.
- **The table runs below the body size, inside the range.** `\footnotesize` fits it
  at 10, 11 and 12 pt; `\small` only with a 10 pt body (above 0.90 at 11 and 12 pt);
  never `\normalsize`, the default when the table declares no size; `\scriptsize`
  and `\tiny` never when they fall below the floor (`\scriptsize` meets it only at
  10 pt).
- **A table is never scaled to fit.** No `\resizebox`, `\scalebox` or `adjustbox`
  below a factor of 0.85, and no `width=\textwidth` scaling of a `tabular`: scaling
  shrinks the text with the box.
- **A table wider than `\textwidth` is split, transposed, or moved** to a `table*` or
  a landscape page when the venue allows either — never shrunk below the floor.
- **The caption goes above the table.**

## LIA house style

Measured on the group's ten Q1 method papers of 2025–2026 (SJR 2025), Elsevier first and MDPI after: items A008, A017, A018, A003, A006, A007, A009, A021, A022 and A026 of the lab's bank of articles. Ranges are minimum–median–maximum across the papers that have the section; a typeset line is about 12 words in a single-column layout. The ranges describe how the group writes; the extent at the top of this contract stays the target.

**Measured size.** 5–17–45 paragraphs; about 1080–2890–5750 words; 0–4–7
subsections; no displayed equations; 1–5–31 citations, used only to anchor an
interpretation; 2–6–12 figures and 0–2–8 tables.

**Subsections, one per analysis, in this order when present:** the controlled or
synthetic scenario; comparison with the state of the art (mean ± standard deviation
over the repetitions) closed by its significance test; one block per contribution,
interpretability included; ablation and sensitivity; limitations, last. Eight of ten
merge results and discussion; six open on a controlled scenario; seven report a
significance test and seven an interpretability analysis, but only two an explicit
ablation. Subsections close on a *Taken together* synthesis; no section closes on one.

**Writing.**

- **Sentences average 21–27 words.** Long enough to carry one claim and its qualifier, never a chain of three clauses.
- **One voice for the whole paper.** First person plural (*we propose*) or impersonal (*this work introduces*), chosen once; procedures that were run go in the passive past (*was evaluated using*).
- **Transitions come from the relation between claims, not from a list.** Name the relation first (contrast, cause, consequence, elaboration, example) and carry it with the sentence's own content: a clause (*yet*, *so*, *although*), a subject that points back (*that gap*, *this cost*), or no connector at all when the order of the sentences already says it. A stock connector (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) is the exception: never the same one twice within five sentences, never most of a paragraph's openings, and a synthesis opener (*Overall*, *Taken together*) at most once per section (here, once per subsection: the synthesis that closes it).
- ***because* and *where* keep their jobs.** *because* states a cause the method or the data establish, at most once every few sentences and never stacked (*because …, and because …*); *where* opens the clause after an equation that defines its symbols, and nowhere else in prose (use *in which*, *when*, or two sentences). An evaluation is its own sentence, not a trailing *, which indicates …*.
- **The method has one name.** Expanded with its acronym at first use in each of the abstract and the body, then *the proposed* followed by the acronym.
- **Results are in the past tense, their reading in the present.** *The proposed
  model reached*; *this suggests that*.
- **Interpretation is hedged, never superlative.** *Suggests*, *indicates*, *is
  consistent with*; not *remarkable*, *perfect*, *cementing*.
- **Numbers are inline**: `80.9 \pm 1.7\%`, with the same decimals across a table and
  its text.
- **The best value of each column is in bold, and the caption says so**: *Bold marks
  the best result for each metric.*
- **A figure or table is the subject of its sentence** (*Table 4 compares*, *As shown
  in Figure 5,*), and its caption is a noun phrase followed by one to three sentences
  that explain the panels, colours and abbreviations — about 30 to 60 words.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| The **results** — the main runs, against the baselines | `rd-general-task` |
| The **implementation** — the most demanding configuration, and the hardware declared in the setup | `rd-cost` |

### Internal chain

| Block | Depends on |
|---|---|
| `results-and-discussion.rd-contribution-blocks` — a mechanism block opens by naming the previous block's result as the question it comes to answer | `results-and-discussion.rd-general-task` — the general task's evidence, the block immediately before it |
| `results-and-discussion.rd-contribution-blocks` — The property a contribution promised, and the instrument the setup named for it | `materials-and-methods.mm-proposal` — the enumerated contributions each property traces to |
| `results-and-discussion.rd-cost` — a mechanism block opens by naming the previous block's result as the question it comes to answer | `results-and-discussion.rd-contribution-blocks` — the per-contribution validation, the block immediately before cost |

### Structural decisions

- **Each artefact** depends on the runs, and the experimental setup's closing
  diagram must be able to locate it — a rule cutting across every block here,
  not a dependency on one specific block.
- **The third beat** (the mechanistic explanation) draws on the formulation,
  or on a property of the data — again cutting across every block, not
  naming one.
- **Limitations** lives in its own section, under its own contract — it is
  not a block of this section and carries no dependency on it.

## Disqualifiers

- An interpretive mechanism, a baseline analysis or a qualitative-interpretability
  argument stated without a citation that supports it.
- A numbered equation.
- A preamble, or a closing summary artefact.
- A block that opens on prose with no artefact reference.
- An artefact that appears before any reference to it, or that nothing references at
  all.
- A pointer to a whole artefact when the value is in one of its parts.
- A number in prose that appears in no artefact.
- An artefact that cannot be located in the experimental setup's closing diagram —
  a reported cell the design never declared.
- A claim of improvement without the baseline it improves on, in the same artefact.
- A contribution with no block here.
- A block belonging to neither a contribution nor the general task.
- A property named here under a different name than the problem statement, the
  contribution, or the instrument gave it.
- A block organized by scenario without stating which contribution it validates.
- An artefact reading with no third beat — the number stated and never explained.
- A discussion written entirely in the assertive register.
- An explanation placed in a different paragraph from the number it explains.
- A conceded loss paired with an asserted gain instead of a measured one.
- A deficiency justified here and absent from limitations.
- A citation credited to a result.
- A table used for a pattern, or a figure used for a comparison grid.
- Limitations placed anywhere but last.
- Interpretation of a result no artefact contains.
- A comparison against the baselines with no statistical significance test.
- A scenario, split, metric, baseline, test, ablation variant, sweep, or
  interpretability measure that the experimental setup did not declare.
- An ablation variant or sweep declared in the setup with no reading here.
- An interpretability contribution read only qualitatively when the setup declared a
  faithfulness measure for it.
- The section closing on a synthesis paragraph.
- A table with values in bold whose caption does not say what the bold marks.
- A table that runs past `\textwidth`, or whose text prints below 0.70 or above 0.90
  times the body font size (a table left at the body size included).
- A table scaled with `\resizebox`, `\scalebox` or `adjustbox` below 0.85, or scaled
  to `\textwidth`.
- A table with vertical rules, or a table whose caption sits below it.
