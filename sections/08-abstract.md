---
{
  "section": "abstract",
  "position": 2,
  "after": [
    {
      "target": "conclusions",
      "source": {
        "file": "sections/07-conclusions.md",
        "quote": "The abstract is written after this section, because it compresses it."
      }
    }
  ],
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/08-abstract.md",
      "quote": "Every sentence here compresses something the paper already establishes, and nothing in it reaches outside this work."
    }
  },
  "blocks": [
    {
      "id": "slot-1",
      "requires_facts": [
        {
          "value": "dataset",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "The dataset — the condition, population, or process it contains"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "slot-2",
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
      "citations": "none",
      "after": [
        {
          "target": "abstract.slot-4",
          "source": {
            "file": "sections/06-introduction.md",
            "quote": "this block is derived from the contributions, read backwards"
          }
        },
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
      "id": "slot-3",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "The mathematical formulation reaches the abstract already transposed, as the methods section's own enumerated contributions, never from the proposals document"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "abstract.slot-2",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "The purpose clause mirrors the deficiencies of slot 2, in the same order."
          }
        },
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "The mathematical formulation reaches the abstract already transposed, as the methods section's own enumerated contributions, never from the proposals document"
          }
        }
      ]
    },
    {
      "id": "slot-4",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "The mathematical formulation reaches the abstract already transposed, as the methods section's own enumerated contributions, never from the proposals document"
          }
        },
        {
          "value": "results",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "The results"
          }
        }
      ],
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "The mathematical formulation reaches the abstract already transposed, as the methods section's own enumerated contributions, never from the proposals document"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "slot-5",
      "requires_facts": [
        {
          "value": "experimental-design",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "The experimental design"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "slot-6",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "The results"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "slot-7",
      "requires_facts": [
        {
          "value": "results",
          "source": {
            "file": "sections/08-abstract.md",
            "quote": "The results"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---
# Abstract

**Extent** 216–280 words · 7–14 sentences · **one paragraph**
**Does not carry** citations, equations, figures, tables, or section references
**Unit of composition** the sentence, not the paragraph

The abstract is the whole argument at one-fiftieth scale, and for most readers it is
the whole paper. It must be self-contained: no forward reference, no undefined
acronym, nothing that only makes sense after reading further. Every sentence here
compresses something the paper already establishes, and nothing in it reaches
outside this work.

## Global structural rule

Seven **functional slots**, in fixed order. Slot and sentence are not the same unit:
five of the seven expand. The shortest form is one sentence per slot; the longest
expands slots 1, 2, 4, 5, and 6 to reach fourteen.

| Slot | Function | Sentences | Words per sentence |
|---|---|---|---|
| 1 | Context | 1–2 | 9–31 |
| 2 | Problem | 1–2 | 15–29 |
| 3 | **The proposal, named** | **1, always** | 15–34 |
| 4 | Announcement and components | 1 inline, or 1 + N | 49–85 inline |
| 5 | Validation | 1–4 | 14–35 |
| 6 | Result or secondary contribution | 1–2 | 16–31 |
| 7 | **Verdict** | **1, always, and last** | 11–28 |

Two slots never expand and never move: the proposal occupies exactly one sentence,
and the verdict occupies exactly one sentence and is the last one in the abstract.

The components slot is the longest sentence — or the longest block — of the abstract.
It is the only place where the sentence is deliberately stretched; everywhere else,
compress.

## What the abstract drops

The abstract carries the same argument as the introduction, minus two of its blocks:

- **The state of the art does not get a slot.** It survives as half a clause inside
  slot 2, in the form *existing methods struggle to …*. Nothing more: no family is
  named, no lineage is walked.
- **The organization of the article never appears.** No section is named or
  referenced.

## Inputs per slot

There is no order among the slots — there is a graph, the same one that governs the
introduction. Four of the seven are draftable before anything is measured.

### External inputs

| Input | Unblocks |
|---|---|
| The **dataset** — the condition, population, or process it contains | `slot-1` |
| The **experimental design** | `slot-5` |
| The **results** | `slot-4` (the achieved-effect clause), `slot-6`, `slot-7` |

### Internal chain

| Block | Depends on |
|---|---|
| `abstract.slot-2` — Problem | `abstract.slot-4` — each component read backwards as the deficiency it resolves |
| `abstract.slot-2` — Problem | `materials-and-methods.mm-proposal` — this block is derived from the contributions, read backwards |
| `abstract.slot-3` — Proposal | `abstract.slot-2` — for the purpose clause |
| `abstract.slot-3` — Proposal | `materials-and-methods.mm-proposal` — The mathematical formulation reaches the abstract already transposed, as the methods section's own enumerated contributions, never from the proposals document |
| `abstract.slot-4` — Announcement and components | `materials-and-methods.mm-proposal` — The mathematical formulation reaches the abstract already transposed, as the methods section's own enumerated contributions, never from the proposals document |

The mathematical formulation reaches the abstract already transposed, as the methods section's own enumerated contributions, never from the proposals document.

The abstract is more blocked by measurement than the introduction: slots 6 and 7 need
the results in full, slot 4 needs them for half of each item, and there is no
equivalent of the introduction's state-of-the-art or organization blocks to write
early. When the results change, this section is corrected to match them.

## Slot 1 — Context

One or two sentences. State the field and the phenomenon that motivates the work, and
why failure there is costly.

Anchor it in the condition, population, or process the dataset contains, not in the
family of techniques employed — the same rule that governs the introduction's opening
block. A single sentence suffices when the domain is common knowledge; a technical
domain needs two, one to place the field and one to narrow to the specific scenario.

## Slot 2 — Problem

One or two sentences. Open with an adversative — the gap is stated against the
context, not alongside it.

Name the specific shortcoming, never "challenges remain". Two sentences are used when
there are two distinct deficiencies, one per sentence. The state of the art is
absorbed here as a single clause attributing the shortcoming to existing methods.

When the problems must be satisfied together, say so in this slot: the word carrying
that simultaneity is what turns two limitations into one gap.

## Slot 3 — The proposal, named

**Exactly one sentence.** Never split, never moved.

It carries four things: the full name, the acronym in parentheses, the category of
the artefact, and the one mechanism that makes it new. The purpose clause mirrors the
deficiencies of slot 2, in the same order.

The first-person verb introducing the proposal appears exactly once in the whole
abstract. Everything before this sentence belongs to other people's work.

## Slot 4 — Announcement and components

**The number of items is the number of contributions the proposal has.** It is
inherited, never a drafting target. Announce the count before enumerating it.

Two forms are available. Choose one and hold it — never mix them.

**Inline.** Announcement and list in a single sentence, ending the announcement in a
colon, roman enumerators, semicolons between items. One sentence of 49 to 85 words.
Maximum compression.

**Expanded.** The announcement becomes its own short sentence, ending in a period, and
each component gets a sentence of its own opening with an ordinal. More legible, and
it makes each component quotable on its own.

Each item states what the component is and what function it performs. The clause
claiming an achieved effect is the part that waits for the results.

Do not open an item with a first-person verb instead of the component's name.

## Slot 5 — Validation

One to four sentences, in this order: scenario, data or tasks, methods compared
against, criteria or metrics, complementary analyses.

Name everything by its proper name. When the slot expands, each of those elements
takes its own sentence, in that order — the scenario is never stated after the
result.

Every property the proposal claims must have its instrument named here.

## Slot 6 — Result or secondary contribution

One or two sentences. This is where the secondary contribution lands — the property
that no component delivers and that an analysis answers instead, typically the one
that is not about performance.

### Figures are permitted here, under three conditions

A figure is admitted only when the figure **is** the fact being framed. This is the
one place in the paper where a number appears outside the results section, and it
exists because the abstract is read on its own: a result that must be framed has
nowhere else to land. The introduction never carries one.

1. **It is a permission, not a convention.** If the abstract works in comparatives, it
   stays in comparatives. A figure is not decoration for the verdict.
2. **The figure states what it belongs to, in the same sentence.** If the number
   characterizes a base component rather than the contribution, say so explicitly.
   Without that clause the abstract claims credit that is not its own.
3. **The unit is one framed fact, not one number.** A single fact may need two values
   to state it; that is one, not two.

A figure quoted here is bound to the results section and must match it exactly.

## Slot 7 — Verdict

**Exactly one sentence, the last one, and among the shortest.** 11 to 28 words.

It states the direction of the outcome and names the axes on which the work improves
— the same axes stated as requirements in slot 2. It opens with a summative adverbial
or a confirmation formula.

It introduces nothing: no new property, no new number, no new claim.

## LIA house style

Measured on the group's ten Q1 method papers of 2025–2026 (SJR 2025): items A003, A006, A007, A009, A012, A013, A021, A022, A023 and A026 of the lab's bank of articles. Ranges are minimum–median–maximum across the papers that have the section; a typeset line is about 12 words in a single-column layout. The ranges describe how the group writes; the extent at the top of this contract stays the target.

**Measured size.** One paragraph of 139–236–311 words, without headings.

**The moves, in order:** context; the challenge, opened by *However* or *Yet*; the
limitation of existing methods; the proposal, introduced by *To address …, we propose*
or *This work introduces* with the full name and the acronym; the mechanism in two to
four sentences, its components often numbered (i)–(iv); the data and the protocol; the
comparative result; and a closing implication (*These results support …*).

**Writing.**

- **Sentences average 21–27 words.** Long enough to carry one claim and its qualifier, never a chain of three clauses.
- **One voice for the whole paper.** First person plural (*we propose*) or impersonal (*this work introduces*), chosen once; procedures that were run go in the passive past (*was evaluated using*).
- **Transitions come from the relation between claims, not from a list.** Name the relation first (contrast, cause, consequence, elaboration, example) and carry it with the sentence's own content: a clause (*yet*, *so*, *although*), a subject that points back (*that gap*, *this cost*), or no connector at all when the order of the sentences already says it. A stock connector (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) is the exception: never the same one twice within five sentences, never most of a paragraph's openings, and a synthesis opener (*Overall*, *Taken together*) at most once per section.
- ***because* and *where* keep their jobs.** *because* states a cause the method or the data establish, at most once every few sentences and never stacked (*because …, and because …*); *where* opens the clause after an equation that defines its symbols, and nowhere else in prose (use *in which*, *when*, or two sentences). An evaluation is its own sentence, not a trailing *, which indicates …*.
- **The method has one name.** Expanded with its acronym at first use in each of the abstract and the body, then *the proposed* followed by the acronym.

## Cross-cutting conventions

- **One paragraph.** No line breaks, no bullets, no headings.
- **No citations of any kind**, including to the authors' own prior work.
- **Expand every acronym on first appearance**, including the proposal's own. A
  domain dense in acronyms expands all of them, however many that is.
- **State the count before enumerating it.**
- The enumeration form here is distinct from the introduction's: roman numerals
  inline, or ordinals one per sentence. The count, order, and naming must match the
  introduction's list and the components of the methods section.

## Disqualifiers

- More than one paragraph.
- A citation, an equation, a figure, a table, or a section reference.
- An unexpanded acronym.
- Over 300 or under 200 words.
- A missing slot. All seven are present even in the shortest form.
- The proposal split across two sentences, or not carrying its full name, acronym,
  category, and mechanism.
- The verdict not last, or expanded beyond one sentence, or introducing something new.
- The components slot not being the longest of the abstract.
- Inline and expanded component forms mixed.
- A component count, order, or naming that disagrees with the introduction or the
  methods section.
- The count announced without being enumerated, or enumerated without being announced.
- The evaluation scenario stated after the result it produced.
- A named family of prior methods, or a walked lineage: that belongs to the state of
  the art, which has no slot here.
- A section named or referenced.
- A quoted figure with no statement of what it belongs to.
- A quoted figure that does not match the results section exactly.
- A property claimed with no instrument named in slot 5.
- A forward reference of any kind.
