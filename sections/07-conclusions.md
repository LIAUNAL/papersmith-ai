---
{
  "section": "conclusions",
  "position": 9,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/07-conclusions.md",
      "quote": "They add nothing — every claim here already exists earlier, in more detail."
    }
  },
  "blocks": [
    {
      "id": "concl-block-1",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/07-conclusions.md",
            "quote": "The contributions, as defined — same count, order, and names as the introduction and the methods section"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/07-conclusions.md",
            "quote": "The contributions, as defined — same count, order, and names as the introduction and the methods section"
          }
        }
      ]
    },
    {
      "id": "concl-block-2",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/07-conclusions.md",
            "quote": "The results, one finding per contribution or hypothesis, in the order the methods and results present them"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "concl-block-3",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "concl-block-4",
      "requires_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/07-conclusions.md",
            "quote": "The limitations, which it is the relevant subset of, and one reference per direction"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "limitations.lim-proposal-items",
          "source": {
            "file": "sections/07-conclusions.md",
            "quote": "The limitations, which it is the relevant subset of, and one reference per direction"
          }
        }
      ]
    }
  ]
}
---
# Conclusions

**Extent** 350–950 words · 3 to 6 paragraphs
**Does not carry** equations, figures, or tables
**Carries** citations in one place only: the future-work block

The conclusions are read by people who will not read the paper. They must stand
alone. They add nothing — every claim here already exists earlier, in more detail.

## Four functional blocks

| Block | Paragraphs | Words |
|---|---|---|
| 1 — The proposal and its components | 1, always the first | 60–226 |
| 2 — The findings, one per contribution | 1 per contribution or hypothesis | 80–180 each |
| 3 — The consequence beyond the method (optional) | own paragraph, or the close of block 2 | ~50–120 |
| 4 — Future work | 1, always last | 55–180 |

Blocks 2 and 3 may share a paragraph; blocks 1 and 4 never merge with anything.
The paragraph count follows the contribution count: three contributions with an
implication paragraph make six.

## Block 1 — The proposal and its components

Past tense. Full name, acronym, and the category of the artefact. Then the N
components restated, in one of three forms:

- **`First / Second / Third`** as separate sentences, after announcing the count;
- **an inline list** inside a single sentence — the most compact form;
- **prose with connectives** — *integrating A … the incorporation of B allows … 
  furthermore C*.

**Same count, same order, same names** as the introduction's contribution list and
the methods section's subsections.

**Close on what distinguishes the method from its alternatives** — the property, not
the number. What it does not require, what it does not need modified, what it does
not depend on.

## Block 2 — The findings, one per contribution

**One paragraph per contribution, in the order the methods and the results present
them.** Each paragraph answers its contribution — or the hypothesis that contribution
tested — with the finding the results reported for it: named competitors, named axes,
and the conditions under which the finding held. A contribution with no finding
paragraph is a contribution the conclusions forgot; a finding paragraph that answers
no contribution is a result the paper did not promise.

**At most one headline number per contribution, identical to the results.** Quote a
value only when the value is the point; otherwise stay in comparatives. A quoted
figure carries its dispersion when the results gave one, and it must match the
results section character for character — same value, same unit, same precision.

**Nothing new.** No experiment, figure, comparison, or interpretation that the results
section does not already hold. The conclusions compress the evidence; they never add
to it.

## Block 3 — The consequence beyond the method (optional)

What the reader takes away, past the fact that the method worked. Not a result and
not a contribution — a consequence. It answers *so what*. About half of the group's
papers carry it; write it when the consequence is real, omit it otherwise.

Two flavours; the paper picks by whose problem it is:

- **For whoever implements it** — the cost of adoption is low: nothing needs
  modifying, the method drops into existing pipelines, the run time falls.
- **For whoever lives the problem** — something becomes possible that was not: the
  factor behind a decision can be traced back, the process is auditable where
  regulation demands it.

It may be its own paragraph or the closing sentences of block 2. It is the only part
of the section that speaks to someone outside the sub-field.

## Block 4 — Future work

Always last. **The only block in the section that cites** — one reference per
direction, showing the direction is live in the literature. Everything before it
cites nothing.

**It is the section's last paragraph, and a paragraph of its own.** It opens after a
paragraph break, never as a sentence continuing the paragraph before it. `write` and
`humanize --apply` open this block's body on a blank line, and `verify` reports a
future-work block that runs into the paragraph above it (`own-paragraph`).

**Future work is the relevant subset of the limitations, with a reference per
direction.** Each direction answers a stated limitation: one direction per relevant
limitation, each with its citation.

**The limitations themselves are not developed here.** They live in the limitations
section; this block names only the directions they motivate.

**The reduction goes one way only.** A limitation may be left without a direction —
not everything is meant to be repaired. But no direction is left without a limitation
motivating it: **a direction with no corresponding limitation means the limitation
was never declared**, not that the direction is unnecessary. Fix it by declaring the
limitation, not by dropping the direction.

That is what makes the coupling between the two sections checkable.

Each direction is specific enough to be a paper — an extension named, not a hope.
The block closes on the applicability those directions would widen.

## Optional

**A scope caveat.** When the results could be read as a finding about the domain
rather than about the model, say which one they are. This carries the same
attribution discipline as a quoted figure: state what the claim belongs to.

## LIA house style

Measured on the group's ten Q1 method papers of 2025–2026 (SJR 2025): items A008, A017, A018 (Elsevier), then A003, A006, A007, A009, A021, A022 and A026 (MDPI) of the lab's bank of articles. Ranges are minimum–median–maximum across the papers that have the section; a typeset line is about 12 words in a single-column layout. The ranges describe how the group writes; the extent at the top of this contract stays the target.

**Measured size.** 2–4.5–10 paragraphs; about 255–610–952 words; no equations,
figures or tables; 0–4–9 citations, mostly in the future-work sentences.

**Measured shape.** 10/10 open by restating the proposal and 10/10 close on future
work; 5/10 repeat headline numbers from the results; 7/10 put limitations inside the
conclusions, which this contract does not follow — the limitations stay in their own
section and the conclusions only draw future work from them; about half carry an
implication paragraph; only one introduced evidence the results did not hold.

**Shape.** Titled *Conclusions*, or *Concluding Remarks and Future Work*. It opens by
restating the method in the past tense (*This work introduced …, a …*), walks the
findings in the order of the contributions, and closes on future work enumerated as
*First*, *Second*, *Third*.

**Writing.**

- **Sentences average 21–27 words.** Long enough to carry one claim and its qualifier, never a chain of three clauses.
- **One voice for the whole paper.** First person plural (*we propose*) or impersonal (*this work introduces*), chosen once; procedures that were run go in the passive past (*was evaluated using*).
- **Transitions come from the relation between claims, not from a list.** Name the relation first (contrast, cause, consequence, elaboration, example) and carry it with the sentence's own content: a clause (*yet*, *so*, *although*), a subject that points back (*that gap*, *this cost*), or no connector at all when the order of the sentences already says it. A stock connector (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) is the exception: never the same one twice within five sentences, never most of a paragraph's openings, and a synthesis opener (*Overall*, *Taken together*) at most once per section.
- ***because* and *where* keep their jobs.** *because* states a cause the method or the data establish, at most once every few sentences and never stacked (*because …, and because …*); *where* opens the clause after an equation that defines its symbols, and nowhere else in prose (use *in which*, *when*, or two sentences). An evaluation is its own sentence, not a trailing *, which indicates …*.
- **The method has one name.** Expanded with its acronym at first use in each of the abstract and the body, then *the proposed* followed by the acronym.

## Inputs

Everything except the abstract must exist. The abstract is written after this
section, because it compresses it.

### External inputs

| Input | Unblocks |
|---|---|
| The **results**, one finding per contribution or hypothesis, in the order the methods and results present them | `concl-block-2` |

### Internal chain

| Block | Depends on |
|---|---|
| `conclusions.concl-block-1` — The contributions, as defined — same count, order, and names as the introduction and the methods section | `materials-and-methods.mm-proposal` — the enumerated contributions restated here |
| `conclusions.concl-block-4` — The limitations, which it is the relevant subset of, and one reference per direction | `limitations.lim-proposal-items` — the swept limitations this block draws its relevant subset from |

Block 3's own placement — its own paragraph or the close of block 2 — is a
placement option (see Structural decisions), not a content derivation from
block 2's own prose, so `concl-block-3` carries neither an external input nor
an internal-chain row.

### Structural decisions

- **Block 3 — the consequence beyond the method** is chosen by whose problem
  it is: the implementer's or the domain's — an authorial decision, not a
  fact fetched from data or a dependency on a sibling block.

## Disqualifiers

- A claim, number, or property that appears nowhere earlier in the paper.
- New evidence: an experiment, figure, comparison, or interpretation the results
  section does not already hold.
- A component list disagreeing with the introduction or the methods section in count,
  order, or naming.
- A contribution with no finding paragraph in block 2.
- Block 1 not first, or block 4 not last.
- Block 1 closing on a number instead of on the distinguishing property.
- A number that differs from the results section — in value, unit, or precision.
- More than one headline number for a single contribution.
- A future-work direction that answers no stated limitation.
- A future-work block that continues the paragraph before it instead of opening its own.
- A citation anywhere outside the future-work block.
- A future-work direction with no reference.
- A future-work direction too vague to be a paper.
- An equation, a figure, or a table.
- Limitations developed here instead of in the limitations section.
- Over 950 or under 350 words.
- A section that cannot be read without having read the paper.
