---
{
  "section": "limitations",
  "position": 8,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/04-limitations.md",
      "quote": "Each item is argued rather than reported, and reaches outside this work for the standard it falls short of."
    }
  },
  "blocks": [
    {
      "id": "lim-opening-concession",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/04-limitations.md",
            "quote": "The results — the concrete achievement they do support"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "lim-proposal-items",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/04-limitations.md",
            "quote": "The mathematical section reaches this block already transposed, as the methods section's own enumerated contributions -- its design decisions are read there, one by one, not from the proposals document"
          }
        }
      ],
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/04-limitations.md",
            "quote": "The mathematical section reaches this block already transposed, as the methods section's own enumerated contributions -- its design decisions are read there, one by one, not from the proposals document"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "produces_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/04-limitations.md",
            "quote": "Sweep the mathematical section for gaps in the proposal:"
          }
        }
      ]
    },
    {
      "id": "lim-validation-items",
      "requires_facts": [
        {
          "value": "experimental-design",
          "source": {
            "file": "sections/04-limitations.md",
            "quote": "The experimental design — what was fixed instead of searched, what was tested at a single point"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "lim-failure-mode",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/04-limitations.md",
            "quote": "The results — the worst reported cell, and the baseline's performance there"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "lim-closing",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "discovery",
      "optional": true
    }
  ]
}
---
# Limitations

**Extent** 180–410 words · 1 paragraph, or 2 when the second carries a failure mode
**Items** 3 to 5
**Carries** at least one citation per item · no figure, no table, no equation, and no
new measurement

This subsection states what the reported results do **not** establish. Its source of
truth is the inverse of every other part of the results section: those are written
from what the artefacts show, this one from what they fail to show. Each item is
argued rather than reported, and reaches outside this work for the standard it falls
short of.

## The opening is a concession

*Although / While / Despite* **[a concrete achievement the results do support]**,
several limitations must be acknowledged.

The concession is mandatory and it names something specific, not a formula. It may
carry the bridge to future work in the same sentence — *which in turn open avenues
for future research*.

## The anatomy of an item

Five movements. The first four are required; reach the fifth wherever possible.

**1. Name the decision or the boundary.** A fixed value, a shared strategy, an
unexplored scale, a predefined grid, a chosen baseline, an approximation. **Never a
feeling.** *Performance may vary* is not a limitation; *the weighting coefficient is
static* is one.

**2. Concede its benefit.** *Although this design enables X* / *While this choice
promotes reproducibility and permits direct comparison*. This is what separates a
limitation from an oversight: the decision was made for a reason, and the reason is
stated.

**3. State the cost.** What it restricts, what it may overlook, what it precludes.

**4. State the consequence for the claim.** *Therefore the resolution of the result
is partly constrained by …* / *the estimated contributions may still depend on …* —
what the paper consequently cannot assert.

**5. State what the alternative would give, and what it would cost.** *… could
improve performance, albeit at an increased computational cost.* This answers the
question the reader asks unprompted: **if you knew it was a limitation, why did you
not fix it.**

### Every item carries at least one citation

The citation is what makes the limitation verifiable rather than confessional. It
lands in one of two places:

- **On the alternative that would fix it** — whoever already proposed it. This is the
  natural home when the item reaches movement 5.
- **On the fact that the problem is known** in the literature, when the item stops at
  movement 4.

## Two sweeps, two kinds of gap

Items come from two places, and both sweeps are made. Some papers have items from
only one, which usually means the other sweep was not done.

**Sweep the mathematical section for gaps in the proposal:**

- a fixed coefficient where an adaptive one is possible;
- a heuristic where a principled choice is possible;
- a predefined grid or partition that constrains the resolution of the result;
- a chosen baseline or reference the result depends on;
- an approximation that ignores a known dependency structure;
- a theoretical grounding the formulation does not incorporate;
- an operating regime where the method degrades;
- the generality of the formulation outside the problem type tested.

**Sweep the experimental design for gaps in the validation:**

- a single shared hyperparameter configuration, with no per-scenario search;
- evaluation on a single source, site, or cohort, with transferability untested;
- a scale left uncharacterized — tested at one only;
- a sample size that constrains generalization;
- data heterogeneity or harmonization left unresolved;
- dependence on the quality and completeness of the input data.

**The checkable rule:** every item names a decision in the formulation or a decision
in the experimental design. An item naming neither is a feeling, and it does not go
in.

## The second paragraph: the quantitative failure mode

Written when there is a regime worth isolating. Four movements:

1. **Name the concrete regime where the method is weakest.**
2. **Point at the worst cell of a table already reported**, by number. Never a new
   measurement.
3. **Bring the evidence that the regime is hard, not that the method is bad** —
   typically the baseline's own performance in that same regime.
4. **Give the mechanism**: which stage of the pipeline breaks, and what input breaks
   it.

The third movement is what separates *the method fails here* from *here nobody
succeeds*, and it does it with a number already in the paper.

## The closing

Optional. Either what addressing the limitations would give, or where the field is
moving, with a citation.

## Coupling with future work

Future work is the relevant subset of these items. The twin obligation lives here:
**an item is declared knowing it may be asked for a direction**, and an orphan
direction in the conclusions — one answering no item here — means an item is missing
from this list, not that the direction is unnecessary.

When an item reaches movement 5, the reference on its alternative is the same one the
corresponding future-work direction carries.

## LIA house style

Measured on the group's ten Q1 method papers of 2025–2026 (SJR 2025): items A003, A006, A007, A009, A012, A013, A021, A022, A023 and A026 of the lab's bank of articles. Ranges are minimum–median–maximum across the papers that have the section; a typeset line is about 12 words in a single-column layout. The ranges describe how the group writes; the extent at the top of this contract stays the target.

Nine of the ten papers state their limitations, and none in a top-level section: five
as the last subsection of the results, titled *Limitations*, and four inside the
conclusions, ahead of the future work. They open by conceding the scope (*Despite the
performance of the proposed …, several limitations should be acknowledged.*) and
enumerate the items as *First*, *Second*, *Third*, each paired with the direction that
would address it.

**Writing.**

- **Sentences average 21–27 words.** Long enough to carry one claim and its qualifier, never a chain of three clauses.
- **One voice for the whole paper.** First person plural (*we propose*) or impersonal (*this work introduces*), chosen once; procedures that were run go in the passive past (*was evaluated using*).
- **Transitions come from the relation between claims, not from a list.** Name the relation first (contrast, cause, consequence, elaboration, example) and carry it with the sentence's own content: a clause (*yet*, *so*, *although*), a subject that points back (*that gap*, *this cost*), or no connector at all when the order of the sentences already says it. A stock connector (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) is the exception: never the same one twice within five sentences, never most of a paragraph's openings, and a synthesis opener (*Overall*, *Taken together*) at most once per section.
- ***because* and *where* keep their jobs.** *because* states a cause the method or the data establish, at most once every few sentences and never stacked (*because …, and because …*); *where* opens the clause after an equation that defines its symbols, and nowhere else in prose (use *in which*, *when*, or two sentences). An evaluation is its own sentence, not a trailing *, which indicates …*.
- **The method has one name.** Expanded with its acronym at first use in each of the abstract and the body, then *the proposed* followed by the acronym.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| The **experimental design** — what was fixed instead of searched, what was tested at a single point | `lim-validation-items` |
| The **results** — the worst reported cell, and the baseline's performance there | `lim-failure-mode` |
| The **results** — the concrete achievement they do support | `lim-opening-concession` |

### Internal chain

| Block | Depends on |
|---|---|
| `limitations.lim-proposal-items` — the design decisions of the proposal, read one by one as what each one costs | `materials-and-methods.mm-proposal` — The mathematical section reaches this block already transposed, as the methods section's own enumerated contributions -- its design decisions are read there, one by one, not from the proposals document |

Checked every other block's `requires_facts` (`results`, `experimental-design`)
and this file's own prose body for a reference to a sibling block's own text:
the remaining four ids (`lim-opening-concession`, `lim-validation-items`,
`lim-failure-mode`, `lim-closing`) draw only on the external facts named above;
no sibling-block prose reference was found for them.

The mathematical section reaches this block already transposed, as the methods section's own enumerated contributions -- its design decisions are read there, one by one, not from the proposals document.

### Structural decisions

- **Each item's citation** lands on the alternative that would fix it, or on
  the literature that already knows the problem — a rule governing every
  item's citation placement, not a dependency naming one block.

## Disqualifiers

- An item naming no decision in the formulation and none in the experimental design.
- An item with no citation.
- An item that stops before movement 4 — the consequence for the claim left unstated.
- An item that concedes no benefit, which makes it read as an oversight rather than a
  decision.
- A new measurement, or a value not already in a reported table.
- A failure mode not visible in any reported table.
- A failure regime named without the baseline's performance in it.
- Only proposal items, or only validation items — one of the two sweeps was skipped.
- An item that no future-work direction may be built on, when the conclusions
  nonetheless carry a direction for it.
- Placement in the conclusions, or anywhere but the last subsection of the results.
- A worst-performing cell softened here while stated plainly in the results, or the
  reverse.
- A figure, a table, or an equation.
