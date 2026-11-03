---
{
  "section": "experimental-setup",
  "position": 6,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/02-experimental-setup.md",
      "quote": "Nothing here is discovered: every condition this section states was already fixed when the experiments ran."
    }
  },
  "blocks": [
    {
      "id": "es-preamble",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "es-dataset",
      "requires_facts": [
        {
          "value": "dataset",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "The dataset — when this section owns it"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    },
    {
      "id": "es-assessment",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "Which property each contribution claims — if it was promised, this is where its instrument is named"
          }
        },
        {
          "value": "experimental-design",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "The experimental design — the competing methods, the axes, and the purpose-built corpus criteria settled as one comparison protocol"
          }
        },
        {
          "value": "gap",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "The gap — that no standard reference measures what is claimed, which is why the purpose-built corpus exists"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "experimental-setup.es-dataset",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "Its one dependency that is NOT internal is the data it must show entering, which live in `es-dataset` when the dataset belongs to this section"
          }
        },
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "Which property each contribution claims — if it was promised, this is where its instrument is named"
          }
        },
        {
          "target": "introduction.block-3",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "The gap — that no standard reference measures what is claimed, which is why the purpose-built corpus exists"
          }
        },
        {
          "target": "related-work.rw-closing",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "The gap — that no standard reference measures what is claimed, which is why the purpose-built corpus exists"
          }
        }
      ],
      "figure": {
        "ordered": false,
        "excludes": ["internal component of the proposal"],
        "caption_enumerates": true,
        "caption_decodes": false,
        "mandatory": true
      }
    },
    {
      "id": "es-training-details",
      "requires_facts": [
        {
          "value": "implementation",
          "source": {
            "file": "sections/02-experimental-setup.md",
            "quote": "The implementation of the experiments and its configuration — what actually ran"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    }
  ]
}
---
# Experimental Set-Up

**Extent** 800–3500 words · an optional preamble and two subsections
**Carries** the whole evaluation protocol — data as used, metrics, compared methods, statistical test, ablation and sensitivity design, interpretability measures — and one closing diagram
**Does not carry** any result

This section answers *would I get your numbers if I ran this myself*. It turns the
method into a protocol: what is measured, what it is measured against, and under
exactly what conditions. Every number in the results section must trace to something
declared here.

The methods section says what the model **is**. This one says what was **done** to it. Nothing here is discovered: every condition this section states was already fixed when the experiments ran.

## The evaluation lives here, all of it

**Every element of the evaluation is declared in this section and nowhere else**: the
scenarios and data as used, the partition, the metrics, the compared methods, the
statistical test, the ablation variants, the sensitivity sweeps, and the measures that
evaluate an interpretability contribution. The methods section defines the proposal
and never evaluates it; the results section reads what was declared here and never
introduces a protocol element of its own. Across the group's measured papers, the
test, the ablation and even the baselines often surfaced for the first time in the
results — the defect this rule removes.

**Each block applies when the paper has what it covers, and only then.** A method
with no learned parameters has no hyperparameter search; a single-component proposal
has nothing to ablate; a paper that claims no interpretability declares no
interpretability measure. The contract fixes where each element goes and how it is
written, never that every paper must carry all of them.

## The two subsections split design from execution

**Assessment and Method Comparison is the design of the comparison. Training Details
is its execution.** Everything answering *what is measured and against what* is
design. Everything answering *with which values and on which machine it ran* is
execution. They are the same thing before and after running.

The section has two subsections. When the datasets do not belong to the methods
section, they are the first block of Assessment rather than a third subsection.

## Preamble

Optional: four of the group's ten measured setups have none. When written, one
paragraph of 30–80 words, no citations: the purpose of the protocol, then the blocks
the section specifies, in order. It may point to the closing diagram.

## Subsection 1 — Assessment and Method Comparison

Nine blocks. Each one is conditional on the paper having what it covers, except the
metrics.

**1. The datasets** — only when the methods section does not own them. First. When
there are several scenarios, the controlled ones come first — synthetic, then
semi-synthetic, then real — and **each scenario is named after the property of the
problem it stresses** (a noise level, a sparsity level, a domain shift), so the reader
knows which part of the problem each one tests. A corruption or simulation applied to
the data — simulated annotators, injected noise, masked inputs — is defined here, with
its equation. When the datasets live here and one of them is real, its explanation
closes on its acquisition-protocol diagram, as the methods section's dataset slot
prescribes: drawn by the `diagram-author` agent following
`skills/paper-writing/references/data-acquisition-diagram.md`, its stages illustrated
with domain pictograms from `skills/paper-writing/references/pictograms.tex`, never
boxes alone, and the last artefact of the dataset explanation.

**2. The announcement of the split** — when the framework has two dissimilar halves.
Each half then makes its own pass through the blocks that follow.

**3. The comparison axes.** The architectures, backbones, or variants over which the
comparison is swept, each with its structure table — layers, shapes, parameter counts
— and its citation. The axis is as much part of the protocol as the metric.

**4. The competing methods.** One list item each, one citation each, and where
possible **its own defining equation**. Do not merely name a baseline: formalize it.
A competitor written as an objective leaves no doubt about which version was run.

**5. The quantitative metrics.** Each defined by a numbered equation, with its symbol
glossary immediately **after** the equation, not before. This is the
equation-densest place in the paper outside the methods section, and every equation
here is a metric definition.

**Each instrument is named under the property it measures**, using the same words
the problem statement and the contribution used for that property. A synonym breaks
the chain that runs from the problem to the evidence.

**6. The qualitative or complementary instruments.** The visualization or attribution
techniques that support the claims no metric measures, each with its citation. These
are what answer the properties a contribution promised and a metric cannot reach.

**When interpretability is a contribution, it is evaluated twice**: by the
qualitative reading named here, and by a measure of faithfulness — a deletion,
perturbation, or recovery-of-known-structure score — against the attribution or
explanation methods it competes with, each cited. The methods section defined the
mechanism; this block names how its explanations are judged.

**7. The purpose-built evaluation corpus** — only when no standard reference measures
what is claimed. Describe it here: its size, its composition, and a table of
examples. Without it the metric for that half means nothing.

**8. The statistical test** — whenever the proposal is compared with anything. The
test, the post hoc procedure and the multiple-comparison correction, the significance
level, and **the unit the test runs over** (folds, seeds, subjects, datasets). The
results apply it; they do not choose it.

**9. The ablation and sensitivity design** — when the proposal has components that
can be removed or knobs that can be swept. **One ablation variant per contribution**,
in the methods section's order, each removing that contribution or replacing it with
the borrowed piece it modifies, under the same protocol. Then the sensitivity sweeps:
each knob the methods section exposes that is varied, with its range. Each variant and
each sweep is named here so the results can only read it.

### What is cited here

**One citation per compared object.** One per competing method, one per axis or
architecture swept, one per qualitative instrument, and one per **non-standard**
metric.

**Standard metrics carry an equation, not a citation.** The same asymmetry as the
methods section: what is borrowed is cited, what is conventional is defined.

**Every protocol decision carries the citation that justifies it.** The comparison
criteria (why these metrics and these baselines measure the claimed property), the
statistical test with its post hoc procedure and correction, and the faithfulness
measure each cite a paper that uses or justifies that choice, or the reference book or
foundational paper in machine learning, statistics, health or the application's
field that establishes it. A protocol stated without the reason it is the right one
reads as an arbitrary choice.

## Subsection 2 — Training Details

The reproducibility block. Past tense, passive for procedure. Six slots.

**1. Preprocessing and exclusions.** What was filtered, discarded, or resampled, and
why. State what was thrown away before stating what was kept.

**2. The partition protocol.** The splits, the cross-validation strategy, the
stratification.

**3. The optimizer and the schedule.** When the method is not trained — an analytic
estimator, a simulation, a solver — this slot and the next carry its numerical
settings instead: tolerances, iterations, discretization, sampling budget.

**4. The hyperparameter search.** The tool, the sampler, **the seed**, the objective
being minimized, and the search range per model. Naming the seed and the pruner's
settings is the level at which a run becomes reproducible.

**5. Leakage control.** One explicit sentence stating that everything requiring a
reference used information from the training partition only.

**6. Software and hardware.** Language version, framework version, library versions,
the environment, and the accelerator by model — mandatory whenever timing is reported
anywhere.

**A value comes with the reason it is that value.** Bounds established empirically
are stated with what the bound guarantees. The form of an objective is justified in
the methods section; a value inside a fixed form is justified here.

**Every knob traces back.** A hyperparameter named here must be a symbol declared in
the methods section.

### What is cited in the training details

**Each protocol decision cites what justifies it.** The preprocessing (a filter band,
a re-referencing, an artefact-removal method), the partition protocol (subject-wise
or leave-one-out cross-validation, the stratification), the leakage control and the
hyperparameter search method each carry a citation to a paper that uses or justifies
that protocol in the same kind of data, or to the reference book or foundational
paper in machine learning, statistics, health or the application's field that
establishes it. The citation attaches to the protocol it credits. Software and
library versions carry their own citation when the venue asks for one; a value
chosen by the authors carries its reason, not a citation.

**The full parameter table may go to an appendix**, keeping in the body only the
values that were reasoned about. That is the correct use of an appendix: the body
carries what has a reason, the appendix carries what must be consultable.

## Paragraphs open on a sentence, never on a label

The numbered blocks above are this contract's names, never the paper's. Each block
becomes one or more paragraphs that open on a sentence, **never as a bold label**
(`\textbf{Partition.}`), a run-in heading (`\paragraph{Metrics}`) or a bold list item.
A paragraph's first sentence introduces its topic and carries the transition from
the paragraph before it, through the relation between the two: the scenarios lead to
how their data are split, the split to what is compared on it, the comparison to how
it is scored and tested.

- *The real data were split by subject, so that no subject contributed samples to
  both the training and the test folds.* — opens the partition by what it guarantees.
- *Three published methods were trained on those same folds, each formalized by the
  objective it minimizes.* — opens the competing methods on the protocol they share.
- *Every comparison was scored per subject, the unit the application decides on.* —
  opens the metrics on the unit the previous paragraph fixed.

Let the sentence's own content carry the relation, as the house style asks: a stock
connector at the head of every paragraph (*Moreover*, *Furthermore*, *In addition*)
is the same outline in other words. The competing methods may still form a list; its
items open on each method's name in plain text. `write` refuses a draft of this
section that opens a paragraph or an item on emphasis (`DRAFT_BOLD_LEAD_IN`).

## Every artefact is referenced before it appears

Any numbered object — figure, table, or panel — is referenced in the body **before**
it appears, and the pointer resolves to the exact sub-element when the artefact has
parts. An artefact appearing with no prior reference is either misplaced or dead.

## Figures and tables here are protocol, never results

Nothing in this section reports a performance. Its figures illustrate the protocol —
the schedule that was used, the spectrum of the input, the structure of the design —
and its tables carry the architectures of each axis and the parameter values.

## The closing diagram

The section closes on one diagram, and **it is the handoff to the results section**.
What the reader must carry forward is the crossing, not the values: the values are
looked up when needed, the crossing has to be held in mind to read a results table.

It shows:

- which data enter;
- against which methods the comparison runs;
- over which axes it is swept;
- which metric comes out of each crossing;
- where the qualitative instruments attach;
- **the repetition unit** — what a single reported number is an average over, and
  what its dispersion is computed across.

The proposal is one row of the crossing, not the centre of the figure.

That repetition unit is the only element of execution admitted into the diagram.
Without it a cell of the diagram cannot be read as a cell of a table. Everything else
about execution stays in Training Details, which is where it gets consulted.

**Its obligation to the results section:** every table and every figure there must be
locatable in this diagram. A reported cell the diagram does not contain is a cell the
design never declared.

**Separation from the methods diagram.** The methods diagram shows the method; this
one shows the experiment. The test: **no dataset and no baseline appears in the
methods diagram, and no internal component of the proposal appears in this one.** A
box appearing in both means one of them is wrong.

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

**Measured size.** 7–10–24 paragraphs; about 810–1190–3480 words, the maximum an
outlier with its own simulation protocol; 0–3–4 subsections; 0–2–8 displayed
equations; 4–9–17 citations; 0–1–3 figures and 0–1–2 tables.

**Measured placement.** Eight of ten have a set-up of their own after the methods; six
open with a purpose-and-roadmap paragraph. Only three define their metrics by
equation, only two declare the statistical test here, and only one declares its
ablation here — the rest surface them in the results, which this contract forbids.

**What the group's setups state, in this order:**

1. preprocessing of the data, with every parameter that shapes it;
2. the validation scheme — folds, stratification, and whether subjects or recordings
   are kept apart across folds;
3. the hyperparameter search — the method (Bayesian optimization, tree-structured
   Parzen estimators), the ranges searched, and the value selected, in a table;
4. the baselines, with the statement that they ran under the same splits and the same
   tuning budget;
5. the metrics, with an equation only when the metric is not standard;
6. the statistical test that decides significance — Friedman with a post hoc
   pairwise test and a Holm or Bonferroni correction is the group's default;
7. the hardware and platform, and the URL of the code repository.

**Writing.**

- **Sentences average 21–27 words.** Long enough to carry one claim and its qualifier, never a chain of three clauses.
- **One voice for the whole paper.** First person plural (*we propose*) or impersonal (*this work introduces*), chosen once; procedures that were run go in the passive past (*was evaluated using*).
- **Transitions come from the relation between claims, not from a list.** Name the relation first (contrast, cause, consequence, elaboration, example) and carry it with the sentence's own content: a clause (*yet*, *so*, *although*), a subject that points back (*that gap*, *this cost*), or no connector at all when the order of the sentences already says it. A stock connector (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) is the exception: never the same one twice within five sentences, never most of a paragraph's openings, and a synthesis opener (*Overall*, *Taken together*) at most once per section.
- ***because* and *where* keep their jobs.** *because* states a cause the method or the data establish, at most once every few sentences and never stacked (*because …, and because …*); *where* opens the clause after an equation that defines its symbols, and nowhere else in prose (use *in which*, *when*, or two sentences). An evaluation is its own sentence, not a trailing *, which indicates …*.
- **The method has one name.** Expanded with its acronym at first use in each of the abstract and the body, then *the proposed* followed by the acronym.
- **What ran is in the past tense; what a table holds is in the present.** *Each model
  was trained for*; *Table 3 lists the search ranges*.
- **No symbol is redefined here.** The setup reuses the methods section's notation;
  a parameter it sets must already exist there.
- **The section is titled *Experimental Set-Up*.**

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| The **dataset** — when this section owns it | `es-dataset` |
| The **competing methods** — the baseline list settled in the state of the art | `es-assessment` |
| The **axes** — what the comparison is swept over | `es-assessment` |
| The **purpose-built corpus** — that no standard reference measures what is claimed | `es-assessment` |
| The **experimental design** — the competing methods, the axes, and the purpose-built corpus criteria settled as one comparison protocol | `es-assessment` |
| The **implementation** of the experiments and its configuration — what actually ran | `es-training-details` |

### Internal chain

| Block | Depends on |
|---|---|
| `experimental-setup.es-assessment` — the closing diagram's "which data enter" panel | `experimental-setup.es-dataset` — the dataset block, when this section owns it |
| `experimental-setup.es-assessment` — Which property each contribution claims — if it was promised, this is where its instrument is named | `materials-and-methods.mm-proposal` — the enumerated contributions the instrument is named for |
| `experimental-setup.es-assessment` — The gap — that no standard reference measures what is claimed, which is why the purpose-built corpus exists | `introduction.block-3` — the joint gap, condensed there |
| `experimental-setup.es-assessment` — The gap — that no standard reference measures what is claimed, which is why the purpose-built corpus exists | `related-work.rw-closing` — the joint gap, developed there |

### Structural decisions

- **How many blocks Assessment has** is decided by the dataset placement
  already decided in the methods section — a structural decision, not a
  dependency on a specific block.
- **The closing diagram** is the crossing declared by everything Assessment
  already carries, plus the repetition unit — an internal composition rule
  within `es-assessment` itself. Its one dependency that is NOT internal is
  the data it must show entering, which live in `es-dataset` when the
  dataset belongs to this section; that one is a chain row above, not a
  structural decision.

## Disqualifiers

- A real dataset described here whose explanation does not close on its
  acquisition-protocol diagram, or whose diagram is boxes alone.
- A preprocessing step, partition protocol, statistical test or comparison criterion
  stated without a citation that uses or justifies it.
- A metric named but not defined.
- A metric glossary placed before its equation instead of after.
- A citation on a standard metric, or a missing citation on a non-standard one.
- A competing method named without a citation, or named without being formalized
  where a formalization exists.
- An axis swept without its structure declared.
- A property claimed by a contribution with no instrument named here.
- An instrument named under a different name than the property it measures carries in
  the problem statement and the contribution.
- An artefact that appears before any reference to it, or that nothing references at
  all.
- A pointer to a whole artefact when the value is in one of its parts.
- A purpose-built corpus used without being described.
- A hyperparameter with no value, or a value disagreeing with the configuration that
  ran.
- A knob that does not exist in the methods section.
- A seed, split, or repetition count omitted.
- Hardware omitted while timing is reported.
- No leakage-control statement.
- A result, a measured comparison, or a performance figure.
- A comparison with competing methods and no statistical test declared, or a test
  declared without the unit it runs over.
- A contribution that can be removed with no ablation variant declared, or a knob
  swept in the results with no sweep declared here.
- An interpretability contribution with no qualitative instrument or no faithfulness
  measure declared here.
- A scenario that does not say which property of the problem it stresses.
- A paragraph or list item that opens on a bold label or a run-in heading.
- The closing diagram missing.
- A results table or figure that cannot be located in the closing diagram.
- A box shared between the closing diagram and the methods diagram.
- Any element of execution in the closing diagram other than the repetition unit.
- The full parameter table in the body when only some values were reasoned about, or
  an appendix table contradicting the body.
- A table that runs past `\textwidth`, or whose text prints below 0.70 or above 0.90
  times the body font size (a table left at the body size included).
- A table scaled with `\resizebox`, `\scalebox` or `adjustbox` below 0.85, or scaled
  to `\textwidth`.
- A table with vertical rules, or a table whose caption sits below it.
