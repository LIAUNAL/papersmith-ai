---
{
  "section": "title-and-keywords",
  "position": 1,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/09-title-and-keywords.md",
      "quote": "The title states what the thing is, not how well it did."
    }
  },
  "blocks": [
    {
      "id": "title",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/09-title-and-keywords.md",
            "quote": "The contributions, already defined — the title selects among them"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "keywords",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "keyword-bounds",
          "source": {
            "file": "sections/09-title-and-keywords.md",
            "quote": "The keyword-bounds and classification-line — the target journal's requirements"
          }
        },
        {
          "value": "classification-line",
          "source": {
            "file": "sections/09-title-and-keywords.md",
            "quote": "The keyword-bounds and classification-line — the target journal's requirements"
          }
        }
      ],
      "citations": "none",
      "after": [
        {
          "target": "title-and-keywords.title",
          "source": {
            "file": "sections/09-title-and-keywords.md",
            "quote": "The title carries the adjective; the keyword carries the noun."
          }
        }
      ]
    }
  ]
}
---
# Title and Keywords

**Extent** title 10–13 words · keywords 4–8
**Carries** no number, no percentage, no claim of superiority

The title is the paper's only irrevocable claim: it is what gets cited, indexed and
searched. The keywords are the retrieval surface — the terms a reader who needs this
paper will type without knowing it exists.

## The title is a slot machine

| Slot | Required | What it is |
|---|---|---|
| Acronym, followed by a colon | no | The name the method is meant to carry in the literature |
| Article | no | *A* or *An* |
| **Property adjective** | **yes** | The property the contribution adds — and it comes first |
| **Mechanism** | **yes** | What the method is made of, named explicitly |
| Artefact noun | no | *Framework*, *approach*, *network* — the category of the thing |
| **Task** | **yes** | What the method is for |
| Domain or place | no | Only when the work is bound to it |

**The three required slots come from the proposal**: the property is the one the
contributions add, the mechanism is what realizes them, the task is the one the
problem statement named.

**The property adjective comes first**, right after the article or the acronym. The
title opens on the property, not on the mechanism — it is the first thing the reader
reads.

**Three slots are optional, and each has a condition.** The artefact noun is dropped
when the mechanisms themselves are the title. The domain or place appears only when
the work does not transfer beyond it. The acronym appears only when it is meant to
become the method's public name, and then it takes a colon and the abstract expands
it.

## Dashes do two different jobs

**A hyphen joins a modifier pair** — two words that together modify a third.

**An en dash joins co-equal terms in a series** — dimensions of the same rank, none
modifying another.

Confusing them changes what the title says: with a hyphen, the first term of a
co-equal series reads as a modifier of the last.

## What never appears in the title

No number, no percentage, no comparative, no claim of superiority. The title states
what the thing is, not how well it did.

Title case, with prepositions and articles in lower case.

## Keywords

**Four to eight, separated by semicolons.** Lower case by default; acronyms in capitals;
proper nouns keep their case.

**They are not a restatement of the title.** Roughly a third repeat a term the title
already carries; the rest add something the title had no room for. A keyword list
that only echoes the title has wasted its whole retrieval surface.

**What the added ones carry**, in three kinds:

1. **The mechanisms the title omitted** — the estimator, the architecture, the
   reduction method, whatever did not fit.
2. **The data modality or the population** — the kind of data, the task family, the
   concrete condition or setting studied.
3. **The property in its searchable form.** The title carries the adjective; the
   keyword carries the noun.

**Ordered broadest to most specific:** the task or domain first, then the property,
then the machinery.

**Every keyword appears in the body.** A keyword absent from the paper is a keyword
invented for the search engine.

## Manuscript Review Format & Author Blinding

### Single-Column Review Mode
The canonical manuscript is presented and typeset in **review format, at one column** (`onecolumn`, e.g., `\documentclass[11pt,onecolumn,a4paper]{article}` with standard review margins and 1.5 line spacing). Two-column or final publisher layouts are reserved for post-acceptance venue adaptation via the `venue` skill.

### Blinded Author Metadata on Initial Drafts
In the initial drafting of the manuscript, **no author names, institutional affiliations, or contact emails are included**. All author metadata remains blinded and explicitly set as placeholders (*por definir* / suppressed for peer review):
```latex
\author{Por definir \\ \textit{Afiliaciones y correos por definir}}
```
Only when the entire manuscript has been drafted, compiled, and passes all verifications with the user is the operator prompted to supply author identities, affiliations, and correspondence details.

## The classification line

Some journals require a subject-classification code after the keywords. That is an
external requirement, not a style decision: take it from the target journal's
instructions, along with the permitted keyword count.

## LIA house style

Measured on the group's ten Q1 method papers of 2025–2026 (SJR 2025): items A003, A006, A007, A009, A012, A013, A021, A022, A023 and A026 of the lab's bank of articles. Ranges are minimum–median–maximum across the papers that have the section; a typeset line is about 12 words in a single-column layout. The ranges describe how the group writes; the extent at the top of this contract stays the target.

**Measured size.** Titles of 7–12–13 words, in title case; 4–5–8 keywords.

**The group's titles** follow *<Mechanism>-Based <Model> for <Task>* or *<Property>
<Mechanism> for <Qualified Task>*, and nine of ten leave the method's acronym out. The
acronym appears in the abstract and the body.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| The **keyword-bounds** and **classification-line** — the target journal's requirements | `keywords` |

### Internal chain

| Block | Depends on |
|---|---|
| `title-and-keywords.title` — The contributions, already defined — the title selects among them | `materials-and-methods.mm-proposal` — the enumerated contributions the title selects among |
| `title-and-keywords.keywords` — the property in its searchable form, the noun form of what the title carries as an adjective | `title-and-keywords.title` — the property adjective the title opens on |

### Structural decisions

- **Whether the acronym appears** is decided by whether it is meant to
  become the method's public name — a structural decision, not a dependency
  on a block.

## Disqualifiers

- Under 10 or over 16 words in the title.
- No property adjective, or one that is not first.
- No mechanism named.
- No task named.
- A number, a percentage, or a claim of superiority.
- An acronym in the title without a colon, or one the abstract does not expand.
- A domain or place named when the work is not bound to it.
- A hyphen where co-equal terms in a series need an en dash.
- Fewer than 4 or more than 8 keywords, or a count the target journal does not permit.
- A keyword list that only repeats title terms.
- A keyword absent from the body.
- A missing classification line when the target journal requires one.
- Real author names, affiliations, or contact emails populated in the initial drafting before complete manuscript verification with the user.
- Manuscript typeset in two-column format instead of single-column review mode (`onecolumn`).
