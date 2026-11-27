---
{
  "section": "methods",
  "position": 5,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/05-methods.md",
      "quote": "The methods transcribe the protocol and the logs under review/; they never describe a step that was not run."
    }
  },
  "blocks": [
    {
      "id": "m-protocol-registration",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "review-registration",
          "source": {
            "file": "sections/05-methods.md",
            "quote": "The review-registration is stated with the protocol's location and any amendment to it."
          }
        }
      ],
      "citations": "resolution",
      "figure": {
        "ordered": true,
        "excludes": ["record count", "included study's finding"],
        "caption_enumerates": true,
        "caption_decodes": true,
        "mandatory": true
      }
    },
    {
      "id": "m-eligibility",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-information-sources",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-search-strategy",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-selection-process",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-data-collection",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-risk-of-bias",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-synthesis",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-certainty",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    }
  ]
}
---

# Methods (review line)

The methods transcribe the protocol and the logs under review/; they never describe a step that was not run.
Titled *Research Methodology* when the venue or the group prefers it. Open
with one sentence stating that the review follows the PRISMA 2020 statement
(Page et al., 2021, doi:10.1136/bmj.n71), and, for software engineering
topics, the Kitchenham and Charters guidelines. Every block below maps to
PRISMA 2020 items; `python skills/systematic-review/scripts/review_cli.py
checklist --root .` reports which items still lack a section.

**Extent** 800–1500 words · one protocol flow diagram, the PRISMA flow figure · at least as many figures as tables

## Block `m-protocol-registration` (item 24)

The review-registration is stated with the protocol's location and any amendment to it. When the protocol was registered after the search started, say so.
A flow diagram, not a table, summarizes the protocol: the PRISMA 2020 phases
(planning, identification, screening, eligibility, extraction and synthesis)
as ordered nodes joined by arrows, each node adapted to this review's topic
rather than generic. The planning node names the objective and the PICOC
elements; identification names the sources searched and the concept blocks of
the query; screening names the two stages, the reviewers and the language
model used as a second screener when there was one; eligibility names the
inclusion and exclusion criteria by their short labels; extraction names the
data items and the appraisal tool; synthesis names the themes and the problem
classes the results use. The diagram carries no record count: the counts
belong to the PRISMA 2020 flow figure (`review_cli.py flow`), and an included
study's finding belongs to the results.

The diagram follows the review's `figure:` obligation. The orchestrating agent
delegates it to the `diagram-author` agent, which writes
`paper/Figures/protocol-flow.tex` and its `protocol-flow.diagram.json` from
`review/protocol.json` and `review/searches.jsonl` and compiles it with
`paper_cli.py render --figure-id protocol-flow --section methods --block
m-protocol-registration`, which also checks this obligation; `/figure-review protocol-flow` (agents
`figure-auditor` and `figure-visual-reviewer`) checks the compiled figure
before the block is drafted. The caption enumerates the phases in order and
decodes every shape and arrow style in two to four words each, within four lines. The text cites the figure before it
appears and walks the reader through it in one paragraph, phase by phase,
saying what the review did at each one for this topic and which record under
`review/` holds it.

## Block `m-eligibility` (item 5)

Inclusion and exclusion criteria from `review/protocol.json`, each with its
reason, and how studies were grouped for the synthesis: study design, years,
language, publication type (peer-reviewed journal and conference papers,
grey literature or not). The review cites 100 to 200 references in total;
when the eligible studies would exceed that budget, state the budget criterion
of the protocol and how the excess was ranked (`review_cli.py prioritize`:
topical relation to the protocol's questions and query, weighted by the best
SJR quartile of the journal), so a reader can repeat the cut.

## Block `m-information-sources` (item 6)

Every database, registry and other source with the date it was last searched
(`review/searches.jsonl`), plus citation chasing (backward and forward
snowballing) and contact with authors when done.

## Block `m-search-strategy` (item 7)

The full query string for each source, exactly as run, with its filters and
limits. When it is long, the full strings go to a supplementary table and the
text shows one of them.

## Block `m-selection-process` (item 8)

Who screened (number of reviewers and whether they worked independently), the
two stages (titles and abstracts, then full texts), how disagreements were
resolved, the agreement measured (Cohen's kappa from `review_cli.py kappa`),
and any automation tool used, including the language model that acted as a
second screener and how its decisions were checked.

## Block `m-data-collection` (items 9-10)

How data were extracted (the protocol's extraction fields, who extracted, how
it was verified) and the list of data items: outcomes and the other variables
sought (study characteristics, methods, datasets, metrics).

## Block `m-risk-of-bias` (item 11)

The appraisal tool (the Kitchenham quality checklist, CASP, JBI, MMAT or
RoB 2 for randomized trials), its questions and scoring, how many reviewers
applied it, and whether a threshold excluded studies.

## Block `m-synthesis` (items 12-13)

The synthesis method: how the taxonomy of themes and the problem classes
were built (from the background's open problems and the extracted data, with
the operator), the comparison dimensions each theme is read along, the
evidence figures (evidence map, forest plot) and comparison tables, and any meta-analysis (model, heterogeneity), bibliometric
analysis or sensitivity analysis. When a study can fall in several themes,
say so here.

## Block `m-certainty` (items 14-15, optional)

Reporting-bias assessment and the certainty of evidence (GRADE) when the
review makes evaluative claims.

## LIA house style

Measured on the group's MDPI review A029 (Cardona-Álvarez, Álvarez-Meza and Castellanos-Dominguez, *Computers* 2025, 14(5):194, doi:10.3390/computers14050194): about 9500 words of body, 168 references of which 102 are included studies, one figure (the PRISMA 2020 flow) and six tables. The ranges describe how the group writes a review; the extent at the top of this contract stays the target, and the disqualifiers below also correct what a PRISMA referee flags in A029.

**Measured size.** 985 words; the PRISMA 2020 flow (Figure 1), a four-phase protocol table (Table 1), the distribution of the included studies by topic and by addressed problem (Tables 2 and 3) and a qualitative comparison of the technologies (Table 4).

**What A029 does and the review line keeps:** the protocol summary, the flow figure cited in the text, and the sources with the period searched (2020 to 2024). **What it changes:** A029 lists its keywords as examples (*Keywords such as …*) instead of the query strings as run, gives no last search date per source, names no number of screeners and no agreement, and assesses no risk of bias; each of those is a PRISMA item a referee checks. The classification tables move to the results, where PRISMA reports study characteristics, and A029's four-phase protocol table becomes a flow diagram adapted to the review's topic, which a reader follows at a glance.

**Writing (every review section).**

- **Sentences average 18–27 words** (A029: median 22). One claim and its qualifier per sentence.
- **One voice.** First person plural for what the review did (*we searched*, *we grouped*), past tense for every step that was run, present tense for what the evidence shows (*the included studies agree*).
- **Citations are numeric, in square brackets, and close the claim they support.** A review cites groups of included studies: list them with commas (`[12,15,19]`), or as a range when they are consecutive in the reference list (`[36–39]`). A citation is never the grammatical subject of a sentence.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences. A029 opens 14 sentences with *In addition* and 16 with *Furthermore* or *Additionally*; that is the pattern to avoid.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the evidence shows instead.
- **A table has at least three columns and three rows.** A two-column or two-row table is a grid with nothing to cross: counts or measures across categories become a bar chart, the shares of one whole (at most six parts) a pie chart, and one or two values go in the sentence. The chart is drawn by a script from the review's records, its provenance recorded with `paper_cli.py figure provenance`, and placed with `paper_cli.py place`.
- Figures over tables. In Methods and Results, present comparisons, distributions, trends, effects with their intervals and time series as data figures (line, bar, dot-and-whisker or forest, violin or box plots, heat maps) or diagrams. Keep a table only for values a reader must look up exactly (settings, hyperparameters, dataset, participant or hardware characteristics, metadata) or when the venue requires one. Among the floats of Methods and Results, aim at about 60 % figures and 40 % tables.
- A figure or table caption is at most four lines: a title that says what the float shows, plus the one definition a reader needs to read it. Notation and further definitions go in a table note below the table or in the text.
- **Every number comes from a record.** Counts from `review/prisma.json`, study values from `review/extraction.jsonl`, never recounted by hand.

## Disqualifiers

- A table of two columns or two rows whose values a bar or pie chart, or the sentence, could carry.
- A search strategy given as example keywords (*terms such as*) instead of the full query string of each source as run.
- A source named without the date it was last searched.
- A count that differs from `review/prisma.json`.
- A selection process without the number of reviewers, how conflicts were settled, and the agreement measured.
- No risk-of-bias tool, or *not assessed* without the limitations saying so.
- A step described that has no record under `review/`.
- The protocol summarized as a table instead of the protocol flow diagram.
- Studies dropped to fit the 100–200 reference budget without the criterion and the ranking that dropped them.
- A protocol diagram generic to any review: phases without this review's sources, query concepts, criteria, data items or themes.
- A protocol diagram that carries record counts, or one the text never walks through.
- A language model used as a screener or an extractor and not reported.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `review-registration` — The review-registration is stated with the protocol's location and any amendment to it. | `m-protocol-registration` |

### Internal chain

None: no block of this section waits on another block.
