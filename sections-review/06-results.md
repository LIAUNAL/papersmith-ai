---
{
  "section": "results",
  "position": 6,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/06-results.md",
      "quote": "Every count comes from review/prisma.json and every study characteristic from review/extraction.jsonl."
    }
  },
  "blocks": [
    {
      "id": "r-study-selection",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-study-characteristics",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "r-risk-of-bias",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "r-bibliometrics",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "r-thematic-synthesis",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "introduction.intro-objectives",
          "source": {
            "file": "sections/06-results.md",
            "quote": "One subsection per theme of the taxonomy, titled by its theme, in the order of the introduction's key points."
          }
        },
        {
          "target": "background.bg-open-problems",
          "source": {
            "file": "sections/06-results.md",
            "quote": "One subsection per theme of the taxonomy, titled by its theme, in the order of the introduction's key points."
          }
        }
      ]
    }
  ]
}
---

# Results (review line)

PRISMA 2020 items 16 to 22. Every count comes from review/prisma.json and every study characteristic from review/extraction.jsonl.
The results are a comparative synthesis: they compare the included studies
along named dimensions, never summarize them one by one.

**Extent** 3000–6500 words · the PRISMA flow diagram, one evidence figure per theme (an evidence map, a forest plot, or the studies charted by dimension) and at most one comparison table per theme · at least as many figures as tables

The whole review fits 45 single-column Elsevier pages (25 two-column), references
included, about 11,000 words of body at 200 references; the results take the
lower part of this range when the references approach 200 (`smith paper qa`
reports the estimate as `page_budget`).

## Block `r-study-selection` (item 16)

The flow of records: identified per source, duplicates removed, screened,
excluded at title and abstract, reports sought and not retrieved, assessed in
full text, excluded with each reason and its count, and included. The PRISMA
2020 flow diagram (`paper/Figures/prisma-flow.svg`, drawn by `review_cli.py
flow`) is cited here. Name studies that looked eligible but were excluded,
with the reason. Studies dropped by the reference budget are a full-text
exclusion with their own criterion and count, read from
`review/prioritization.json` and `review/prisma.json`, never folded into
another reason.

## Block `r-study-characteristics` (item 17)

The distribution of the included studies by theme and by problem class (the
background's open problems), as bar charts or an evidence map, and a table of the included studies
(reference, year, venue, setting, method, data, evaluation, outcomes) from
the extraction, in a supplementary file when it is long. When a study falls
in several themes, the table says so and the text gives the number of
distinct studies, so that no table total reads as the included count.

## Block `r-risk-of-bias` (item 18)

The appraisal of each included study (a traffic-light or summary plot, or a
table when the venue requires one) and the overall pattern.

## Block `r-bibliometrics` (optional)

Publications per year, per venue and per country, and the keyword
co-occurrence map from `review_cli.py biblio`, each described in one or two
sentences that state what the figure shows, not what it means.

## Block `r-thematic-synthesis` (items 19-22)

One subsection per theme of the taxonomy, titled by its theme, in the order of the introduction's key points. The results never use RQ notation: no RQ1, RQ2 … label in a title, a
sentence, a parenthesis or a table, and no *Regarding RQ2* opener. A theme
answers its question through its content, and the reader already met the
questions in the introduction's proposal paragraph.

The paragraphs read as one connected synthesis, following the ideas and the
discussions the extraction supports: each subsection opens from what the
previous one left open (*that latency bound*, *the data those studies lack*),
and each sub-theme paragraph picks up the claim the one before closed, with
the relation carried in the sentence's own content rather than by a stock
connector (the redactor's *Prose flow* rules). Each subsection is built the
same way:

1. **A framing paragraph**: what the theme covers, how many included studies
   it holds (cited as a group), and the dimensions they are compared along
   (approach, data, evaluation, reported result, deployment).
2. **Sub-themes**, each a paragraph that opens with a bold label (*FPGA-based
   processing:*) and compares at least two studies along one dimension: what
   they share, where they differ, and which setting favors which result. The
   subject of each sentence is an approach, a finding or a dimension, and the
   citations close it: *Three studies offload filtering to the edge
   [12,15,19], whereas two keep it in the cloud and report lower latency only
   above 10 Gb/s [22,31].* A single study gets its own sentence only when its
   result departs from the group or is the only evidence, and never more than
   two sentences in a row.
3. **A closing synthesis sentence per sub-theme** that states what the
   evidence supports: agreement, disagreement, or a gap (*These studies agree
   that …, but none evaluates …*). It carries a claim, never a restatement of
   the topic.
4. **An evidence figure per theme**, from `review/extraction.jsonl`: an
   evidence map of the studies by approach and outcome, a forest plot when the
   theme's effects share a measure, or the studies charted by dimension. A
   comparison table (studies by dimensions) follows it only for the words a
   reader looks up, at most one per theme. Each is referenced before it
   appears. A theme too small for a table (two columns or two rows) carries its
   comparison as a bar or pie chart, or in the text, under the table-shape rule
   below. Every value in a figure, a table or the text is the extracted value,
   whose quote is on file.

Interpretation, recommendations and directions wait for the discussion.

## LIA house style

Measured on the group's MDPI review A029 (Cardona-Álvarez, Álvarez-Meza and Castellanos-Dominguez, *Computers* 2025, 14(5):194, doi:10.3390/computers14050194): about 9500 words of body, 168 references of which 102 are included studies, one figure (the PRISMA 2020 flow) and six tables. The ranges describe how the group writes a review; the extent at the top of this contract stays the target, and the disqualifiers below also correct what a PRISMA referee flags in A029.

**Measured size.** 5186 words in four thematic subsections of 800–1800 words; 17 sub-themes opened by a bold label; 13 sub-themes closed by a *These studies …* sentence; two tool-comparison tables (Tables 5 and 6); 135 citation markers.

**What A029 does and the review line keeps:** subsections by theme, each opened by a paragraph that says what it addresses; bold-labelled sub-themes; a closing *These studies …* sentence; comparison tables. **What it changes:** A029 writes the sub-themes as a catalogue, one study per sentence with the citation as the subject (*The paper by [n] …*, *The article by [n] …*, *The study conducted by [n] …*, 46 times). Its closing sentences restate the topic (*These studies highlight the importance of …*) instead of stating a pattern. Its counts are reconciled in prose (92 of the 102 studies classified by topic, 74 by problem, the rest contextual); the review line keeps that reconciliation as a rule.

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
- A citation as the subject of a sentence: *The paper by [n]*, *The study by [n]*, *The article by [n]*, *In [n], the authors*, *Author et al. [n] proposed*.
- Three or more consecutive sentences about one study.
- A sub-theme paragraph that cites a single study, unless it says that this study is the only evidence.
- A sub-theme without its closing synthesis sentence, or one that restates the topic (*These studies highlight the importance of …*).
- A theme without its evidence figure (or, for a theme of one or two studies, its comparison in the text), a theme with more comparison tables than figures, or a figure or table never referenced in the text.
- RQ notation anywhere in the results: an RQ label in a title, a sentence, a parenthesis or a table.
- A subsection or sub-theme paragraph that starts from zero, with no link to the claim the previous one closed.
- A value that is not in `review/extraction.jsonl`.
- Category totals presented as the number of included studies, or category counts that cannot be reconciled with `review/prisma.json`.
- An included study cited nowhere in the results.
- A recommendation or a research direction: those belong to the discussion.

## Inputs

### External inputs

None: every block reads the records under `review/` and the operator's declarations.

### Internal chain

| Block | Depends on |
|---|---|
| `results.r-thematic-synthesis` — One subsection per theme of the taxonomy, titled by its theme, in the order of the introduction's key points. | `introduction.intro-objectives` |
| `results.r-thematic-synthesis` — One subsection per theme of the taxonomy, titled by its theme, in the order of the introduction's key points. | `background.bg-open-problems` |
