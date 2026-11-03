---
{
  "section": "back-matter",
  "position": 10,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/10-back-matter.md",
      "quote": "Every block here is an external fact, not a decision."
    }
  },
  "blocks": [
    {
      "id": "bm-author-contributions",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "author-roles",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "The author-roles — the author list, and each author's confirmed roles"
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "bm-funding",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "grant-title",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "The grant-title and grant-code — the funding project's registered title, funder, and code"
          }
        },
        {
          "value": "grant-code",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "The grant-title and grant-code — the funding project's registered title, funder, and code"
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "bm-data-availability",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "repository-url",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "The repository-url — the project repository URL, and the date it was checked"
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "bm-code-availability",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "repository-url",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "The repository-url — the code repository that produced the reported numbers, and its release or commit"
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "bm-ethics-statement",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "ethics-approval",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "The ethics-approval — the approving committee, approval code and date, and how consent was obtained, or Not applicable. for public data"
          }
        }
      ],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-informed-consent",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "ethics-approval",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "The ethics-approval — the approving committee, approval code and date, and how consent was obtained, or Not applicable. for public data"
          }
        }
      ],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-conflicts-of-interest",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "bm-acknowledgments",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true,
      "after": [
        {
          "target": "back-matter.bm-funding",
          "source": {
            "file": "sections/10-back-matter.md",
            "quote": "Present only when there is a project or institution to thank that is not already named under funding."
          }
        }
      ]
    },
    {
      "id": "bm-supplementary-materials",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-abbreviations",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-appendices",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-highlights",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-graphical-abstract",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "bm-ai-use-declaration",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---
# Back Matter

The administrative block that sits after the conclusions and before the references.
It is not scientific prose — it is the paper's accountability surface: who did what,
who paid, where the data and code are, how AI was used, and what could bias the work.

Each block is a bold inline label followed by prose, unless the venue gives it a
section of its own. No subsections. This is the most mechanical part of the paper and
the most likely to be wrong at submission, because nobody treats it as writing.

## The blocks, in this order

| Block | Required | Words |
|---|---|---|
| Author Contributions | yes | 37–44 |
| Funding | yes; its placement follows the venue | 55 per project |
| Data Availability Statement | yes | 7–22 |
| Code Availability | yes | 7–25 |
| Institutional Review Board Statement | when the venue asks for it, or humans or animals were studied | one or two sentences |
| Informed Consent Statement | when the venue asks for it, or humans were studied | one sentence |
| Conflicts of Interest | yes | one sentence |
| Acknowledgments | only if there is a project to thank, or the venue puts funding or the AI declaration there | ~25 |
| Supplementary Materials | only if the paper ships them | one sentence per item |
| Abbreviations | optional | one line per term |
| Appendices | only if the paper needs them | — |
| Highlights | Elsevier venues | 3–5 bullets |
| Graphical Abstract | Elsevier venues, optional | one image |
| AI-use declaration | yes, always | 40–90 |

## Placement follows the venue

The block list is the same for every paper; where each block lands and what it is
titled follow the publisher of the selected venue (`venue select` records it).

**Back matter renders after the conclusions and before the references, for every venue.**
In `main.tex` every declaration block sits above the `\bibliography` line (or the
`thebibliography` environment); the AI-use declaration, when it is a section of its
own, is the last of them, immediately before the references.
**Appendices follow the references**, unless the venue's guidelines say otherwise; no
publisher family below does. `verify` reports the order (`back-matter-order`), and `venue build` always emits
it, whatever order the canonical file holds.

- **Elsevier.** Highlights and a graphical abstract are submitted with the manuscript.
  CRediT author contributions, a declaration of competing interest, and **funding
  inside the Acknowledgements**. The AI-use declaration is **its own section,
  immediately before the references**.
- **MDPI.** Author Contributions, a **Funding block of its own**, Institutional
  Review Board Statement, Informed Consent Statement (*Not applicable.* when the data
  are public), Data Availability Statement, and Conflicts of Interest carrying the
  funder-role sentence. The AI-use disclosure goes **inside the Acknowledgments**.
- **IEEE.** The AI-use disclosure goes in the Acknowledgments and names the sections
  that contain AI-generated content.
- **Any other venue.** The publisher-neutral template below, as its own unnumbered
  section before the references, unless the author guidelines say otherwise.

## Each declaration is a paragraph of its own

Author contributions, funding, the data and code availability statements, the ethics
and consent statements, the conflicts of interest and the acknowledgments each open a
paragraph of their own, after a paragraph break: never two declarations run together
as consecutive sentences of one paragraph. Their blocks sit back to back in
`main.tex` and their markers are comments, so `write` and `humanize --apply` open
each of these bodies on a blank line, and `verify` reports a declaration that runs
into the one before it (`own-paragraph`).

## Author Contributions

A formula, which is why its length barely varies. The CRediT roles, semicolon
separated, each followed by the initials of the authors who held it, comma separated
with *and* before the last. Then the standing closing sentence stating that all
authors have read and agreed to the published version.

**Every author appears in at least one role.** The roles are the ones each author
confirmed, not the ones inferred from the work. **An AI tool is never an author** and
never holds a role.

## Funding

One entry per grant. Each carries the project's **exact registered title**, in its
original language, the funder, and the grant code. When a grant supports a specific
author rather than the work as a whole, name that author with it.

Grant codes are copied from the funding records, never retyped from memory.

Where the venue puts funding inside the acknowledgements, the same entries go there,
unchanged.

## Data Availability Statement

The repository URL plus the date it was checked. The URL must resolve, and it must
hold the code that produced the reported numbers.

When the data cannot be published, say so in one line and give the route to request
it. Do not point at a repository holding only code while implying it holds the data.

State what is public and what is not — they are different claims.

## Code Availability

Separate from the data statement, because code and data are different claims. The
repository URL, the date it was checked, and the release or commit that produced the
reported numbers. When the code cannot be released, say so and give the route to
request it.

## Institutional Review Board Statement

The approving committee, the approval code, and the approval date, copied from the
approval record. When the study used only public, de-identified data and no committee
reviewed it, the statement is *Not applicable.* — and the data availability statement
names the public source that makes it so.

## Informed Consent Statement

One sentence: consent was obtained from all subjects involved in the study, or *Not
applicable.* when no human subject was recruited. Never claim consent the approval
record does not show.

## Conflicts of Interest

One sentence declaring none.

The one case that needs more: when an author is affiliated with an organization with
an interest in the results — typically the one that supplied the data — name the
affiliation explicitly and repeat the declaration for that author. Silence about a
known affiliation is the failure this block exists to prevent.

When the venue asks for it, add the funder-role sentence: the funders had no role in
the design of the study, the analyses, the writing of the manuscript, or the decision
to publish.

## Acknowledgments

Present only when there is a project or institution to thank that is not already
named under funding. One or two sentences. It also hosts funding and the AI-use
disclosure when the venue places them here.

## Supplementary Materials

One sentence per item: what it is, and where it is downloaded from. Every item listed
here is referenced from the body section that needs it.

## Abbreviations

Optional; none of the group's measured papers carries one. When the venue asks for it,
one line per abbreviation, in the order of first use, with exactly the expansion the
body uses.

## Appendices

Used when material is necessary to reproduce the work but would break the flow of
the section that needs it — verbatim artefacts, or a full parameter table when the
experimental setup carries only the values that were reasoned about.

Lettered, with subsections numbered under their letter. **Each appendix is referenced
from the body section that needs it**; one that nothing references is dead weight.

Whether the paper has appendices at all is decided per paper. When it has them, they
come after the references, never among the declarations.

**An appendix that prints in one page or less is not an appendix.** Its content goes
into the body section that needs it, where it is read in context instead of a page
turn away: Materials and Methods for a derivation, a proof or a formal detail of the
method, and the experimental set-up for a table of settings, a protocol detail or a
configuration. Only material longer than one page stays after the references.
`verify` estimates each appendix's printed extent from the source and reports one
that fits in a page (`appendix-length`), naming the section it belongs in.

## Highlights

Three to five bullets, each at most 85 characters with spaces, each one claim: the
proposal, then one finding per contribution, in the conclusions' order. Highlights
compress the paper's contributions and findings, after the conclusions state them;
they add nothing the conclusions do not hold, and a number in a highlight is identical
to the results.

## Graphical Abstract

Optional, for venues that accept one: a single image of the proposal and its main
finding, readable without the paper. It reuses the methods diagram or a results figure
rather than inventing a new claim.

## AI-use declaration

**Always present.** Every paper this pipeline writes was produced with AI agents, so
there is always something to declare. The declaration is built from the pipeline's
AI-usage record — the agent of each phase, the harness sessions with their tool, the
operator's approval rounds, the revisions, and the paper blocks the agents drafted.
`packet` attaches that record to this block; the declaration states what it shows,
never less and never more.

Name the tools and, when the record carries it, their version; state what they were
used for (the phases and the sections they drafted); state that the authors reviewed
and edited the output at the recorded approval gates and take full responsibility.
Where a version is not in the record, the operator supplies it.

Name the framework that ran the pipeline and cite its repository, from the record's
`framework` field: papersmith, with its release when recorded, at
https://github.com/LIAUNAL/papersmith-ai (in LaTeX, `\url{https://github.com/LIAUNAL/papersmith-ai}`).
The citation goes in the declaration's first sentence, beside the harnesses that ran
the agents, for example "the authors used AI agents orchestrated by the papersmith
framework (version 0.58.2, \url{https://github.com/LIAUNAL/papersmith-ai}) and run in
[harnesses] to [uses]".

Wording by venue, with the brackets filled from the record:

- **Elsevier**, titled "Declaration of generative AI and AI-assisted technologies in
  the manuscript preparation process": "During the preparation of this work the
  author(s) used [NAME OF TOOL / SERVICE] in order to [REASON]. After using this
  tool/service, the author(s) reviewed and edited the content as needed and take(s)
  full responsibility for the content of the published article."
- **MDPI**, inside the Acknowledgments: "During the preparation of this
  manuscript/study, the author(s) used [tool name, version information] for the
  purposes of [description of use]. The authors have reviewed and edited the output and
  take full responsibility for the content of this publication."
- **IEEE**, inside the Acknowledgments: the tools, what they were used for, and the
  sections that contain AI-generated content, by name.
- **Any other venue**: "During the preparation of this work, the authors used [tools]
  to [uses], in [sections]. The authors reviewed and edited all generated content and
  take full responsibility for the content of this publication."

**When agents generated or ran code or experiments**, the experimental setup also
carries one Methods sentence saying which parts of the implementation and the runs were
produced or executed by AI agents, and how they were checked. The AI-usage record says
whether that happened.

AI use for grammar or spelling alone still names the tool: the group's papers that
declare it name Grammarly, Quillbot with ChatGPT, or Gemini with Claude.

## LIA house style

Measured on the group's ten Q1 method papers of 2025–2026 (SJR 2025): items A008, A017 and A018 (Elsevier), then A003, A006, A007, A009, A021, A022 and A026 (MDPI) of the lab's bank of articles.

**Measured blocks.** The three Elsevier papers carry Highlights, an AI declaration
section before the references, CRediT author contributions, a declaration of competing
interest, and funding inside the Acknowledgements. The MDPI papers carry Author
Contributions, Funding, an Institutional Review Board Statement and an Informed Consent
Statement (*Not applicable.* in 4 of 7), a Data Availability Statement, Conflicts of
Interest with the funder-role sentence, and the AI disclosure inside the
Acknowledgments. 6 of 10 declare AI use (Grammarly; Quillbot with ChatGPT; Gemini with
Claude); none carries an Abbreviations list.

## Inputs

Every block here is an external fact, not a decision. None of it is derived from the
paper, except the highlights, which compress what the conclusions already state —
they are written last, once the conclusions exist, and carry no cross-section edge
because back matter renders after every body section and constrains no other section.

### External inputs

| Input | Unblocks |
|---|---|
| The **author-roles** — the author list, and each author's confirmed roles | `bm-author-contributions` |
| The **grant-title** and **grant-code** — the funding project's registered title, funder, and code | `bm-funding` |
| The **repository-url** — the project repository URL, and the date it was checked | `bm-data-availability` |
| The **repository-url** — the code repository that produced the reported numbers, and its release or commit | `bm-code-availability` |
| The **ethics-approval** — the approving committee, approval code and date, and how consent was obtained, or *Not applicable.* for public data | `bm-ethics-statement`, `bm-informed-consent` |
| Any author affiliation with an interested organization | `bm-conflicts-of-interest` |
| The project or institution to thank | `bm-acknowledgments` |
| The supplementary files the paper ships | `bm-supplementary-materials` |
| The abbreviations the body uses, when the venue asks for the list | `bm-abbreviations` |
| Whichever body sections need one | `bm-appendices` |
| The selected venue's publisher, which decides highlights and the graphical abstract; the written conclusions, which the highlights compress | `bm-highlights`, `bm-graphical-abstract` |
| The pipeline's AI-usage record, attached by `packet` | `bm-ai-use-declaration` |

### Internal chain

| Block | Depends on |
|---|---|
| `back-matter.bm-acknowledgments` — present only when there is a project or institution to thank that is not already named under funding | `back-matter.bm-funding` — the funding entries already naming any project or institution credited there |

## Disqualifiers

- An author with no role.
- A role attributed without the author confirming it.
- An AI tool listed as an author, or holding a CRediT role.
- A grant title or code reproduced from memory rather than copied.
- Funding placed against the venue's rule — a separate block where the venue puts it in
  the acknowledgements, or the reverse.
- A repository URL that does not resolve, or that holds code unable to produce the
  reported numbers.
- A missing access date on the URL.
- A data availability statement claiming public data that is not public.
- Code availability folded into the data statement.
- An approval code or consent claim not copied from the approval record.
- A known interested affiliation left undeclared.
- A declaration placed after the references, or an appendix placed before them.
- An appendix or supplementary item that no body section references.
- An appendix that fits in one page instead of sitting in the body section that needs it.
- Two declarations run together in one paragraph.
- Appendix content that contradicts the experimental setup.
- A highlight that states something the conclusions do not, or a number differing from
  the results.
- No AI-use declaration.
- An AI-use declaration whose tools, uses, or sections contradict the pipeline's
  AI-usage record, or that omits the Methods sentence when agents generated or ran
  code or experiments.
- An AI-use declaration placed against the venue's rule.
