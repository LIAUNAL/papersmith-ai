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
            "quote": "One subsection per theme of the taxonomy, each naming the research question it answers, in the order of the introduction."
          }
        },
        {
          "target": "background.bg-open-problems",
          "source": {
            "file": "sections/06-results.md",
            "quote": "One subsection per theme of the taxonomy, each naming the research question it answers, in the order of the introduction."
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

**Extent** 3000–6500 words · one comparison table per theme

## Block `r-study-selection` (item 16)

The flow of records: identified per source, duplicates removed, screened,
excluded at title and abstract, reports sought and not retrieved, assessed in
full text, excluded with each reason and its count, and included. The PRISMA
2020 flow diagram (`paper/Figures/prisma-flow.svg`, drawn by `review_cli.py
flow`) is cited here. Name studies that looked eligible but were excluded,
with the reason.

## Block `r-study-characteristics` (item 17)

The distribution of the included studies by theme and by problem class (the
background's open problems), as tables, and a table of the included studies
(reference, year, venue, setting, method, data, evaluation, outcomes) from
the extraction, in a supplementary file when it is long. When a study falls
in several themes, the table says so and the text gives the number of
distinct studies, so that no table total reads as the included count.

## Block `r-risk-of-bias` (item 18)

The appraisal of each included study (a table or a figure) and the overall
pattern.

## Block `r-bibliometrics` (optional)

Publications per year, per venue and per country, and the keyword
co-occurrence map from `review_cli.py biblio`, each described in one or two
sentences that state what the figure shows, not what it means.

## Block `r-thematic-synthesis` (items 19-22)

One subsection per theme of the taxonomy, each naming the research question it answers, in the order of the introduction. Each subsection is built the same way:

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
4. **A comparison table per theme** (studies by dimensions), from
   `review/extraction.jsonl`, referenced before it appears. Every value in a
   table or the text is the extracted value, whose quote is on file.

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
- **Every number comes from a record.** Counts from `review/prisma.json`, study values from `review/extraction.jsonl`, never recounted by hand.

## Disqualifiers

- A citation as the subject of a sentence: *The paper by [n]*, *The study by [n]*, *The article by [n]*, *In [n], the authors*, *Author et al. [n] proposed*.
- Three or more consecutive sentences about one study.
- A sub-theme paragraph that cites a single study, unless it says that this study is the only evidence.
- A sub-theme without its closing synthesis sentence, or one that restates the topic (*These studies highlight the importance of …*).
- A theme without its comparison table, or a table never referenced in the text.
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
| `results.r-thematic-synthesis` — One subsection per theme of the taxonomy, each naming the research question it answers, in the order of the introduction. | `introduction.intro-objectives` |
| `results.r-thematic-synthesis` — One subsection per theme of the taxonomy, each naming the research question it answers, in the order of the introduction. | `background.bg-open-problems` |
