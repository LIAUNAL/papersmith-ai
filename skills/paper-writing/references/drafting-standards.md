## Manuscript Presentation and Drafting Standards

### Format and Review Presentation Mode
The canonical manuscript is presented in **review mode, single column** (`onecolumn`, e.g., `\documentclass[11pt,onecolumn,a4paper]{article}` with standard review margins and line spacing). Multi-column or journal-specific publication styles are deferred to the `venue` adaptation workflow once a journal is selected.

### Blinded Author Metadata on Initial Drafts
During the initial drafting and refinement of the manuscript, **no author names, affiliations, or emails are included**. All author metadata remains blinded and marked as English placeholders:
```latex
\author{Author names withheld \\ \textit{Affiliations and contact e-mails to be provided}}
```
Only when the complete manuscript passes all verification gates with the user is the operator prompted to provide the author identities, affiliations, and correspondence details.

### Revealed Author Metadata
When the operator lifts the blinding, the `title-and-keywords.title` block replaces the placeholder with this template, and only this one:
```latex
\author{%
\begin{minipage}[t]{\dimexpr\textwidth-2\tabcolsep\relax}
\centering
First Author$^{1}$, Second Author$^{1,2}$, and Third Author$^{3,*}$\\[1ex]
\small
$^{1}$Departamento de Sistemas e Inform\'{a}tica, Universidad de Caldas, Manizales 170004, Colombia\\
$^{2}$Departamento de Electr\'{o}nica y Automatizaci\'{o}n, Universidad Aut\'{o}noma de Manizales, Manizales 170001, Colombia\\
$^{3}$AI-Lab, Signal Processing and Recognition Group, Universidad Nacional de Colombia, Sede Manizales, Manizales 170003, Colombia\\[1ex]
E-mails: \texttt{first.author@ucaldas.edu.co}, \texttt{second.author@ucaldas.edu.co}, \texttt{third.author@unal.edu.co}\\
$^{*}$Corresponding author: \texttt{third.author@unal.edu.co}
\end{minipage}}
```
`article` sets `\author` in a centred `c` column that never wraps, so an affiliation or e-mail list written as a bare `\\` line wider than the text block runs into the margin (an `Overfull \hbox` in `main.log`). The `minipage` of width `\textwidth-2\tabcolsep` turns the header back into wrapping text. Keep one author line with superscript affiliation indices, one affiliation per line in `\small`, then the e-mails and the corresponding author. Separate lines with `\\`, never `\par` or a blank line: `\author` is not a long command, and a paragraph break inside it aborts the preamble. Verify that `main.log` has no `Overfull \hbox` at the `\maketitle` line before reporting the header done.

### Seven-Paragraph Introduction Structure
The Introduction has exactly seven paragraphs; the full contract, with the extent of each one, is `sections/06-introduction.md`:
1. **Paragraph 1 (Application Context):** General context of the application domain and motivating phenomenon.
2. **Paragraph 2 (AI Context & Problem Statement):** Context of AI techniques in said application, concluding with 2 to 3 sentences explicitly declaring the problem and its causes (drawn from the conceptual map, model panel, and pillars; strictly running text, no bullet items, no bold text, no numbered questions).
3. **Paragraph 3 (State of the Art, first families):** The first methodological families, with their principal methods, strengths, and issues/limitations.
4. **Paragraph 4 (State of the Art, remaining families and joint gap):** The remaining families in the same form, closing on the joint gap. Paragraphs 3 and 4 together present 3 to 7 families.
5. **Paragraph 5 (Proposal & Contributions):** Proposal presentation, introduced once in the paper's one voice (*this work introduces* by default, *we propose* when the paper chose first person), ending in a colon and followed by its main contributions in 3 to 4 short items; the list continues the paragraph. The count is inherited from the methods section: a proposal outside 3 to 4 contributions is fixed there, never by padding or trimming the list.
6. **Paragraph 6 (Evaluation, Results & Impact):** Summary of experiments conducted, comparison methods and criteria, most important empirical results obtained, and potential impact.
7. **Paragraph 7 (Roadmap/Agenda):** Agenda of the paper (`The remainder of this paper is organized as follows: ...`).

### Related Work Structure and Citation Density
1. **Opening Context Paragraph:** First paragraph establishes the overarching context of problems and methods studied, framing the families introduced in the Introduction.
2. **Subsections per Family:** Each of the 3 to 7 families has its own dedicated subsection (`\subsection{...}`).
3. **Three-part internal structure (2 to 3 paragraphs per subsection):** Foundations (fundamentos), Main methods (métodos principales), and Main challenges/issues (principales desafíos).
4. **Citation volume per family:** Each family subsection must cite between 5 to 10 distinct alternative works.
5. **Reference Horizon:** Between the Introduction and Related Work, the bibliography must collectively cite between 30 and 40 references.
6. **Synthesis table (Block 5):** 7 to 12 works selected by relevance to the pillars and contributions, every family with at least one row, the proposal as the last row. Columns are the family plus one axis per pillar, contribution or property the proposal declares; an axis every row shares is dropped. The redactor picks the clearest layout (checkmark matrix, compact attribute table, or rows grouped by family) and states why; cells are a symbol or at most three words, the caption decodes every symbol, and the table follows the table rules of contracts 02 and 03. The contract-audit stage counts the works deterministically (`paper_audit.count_table_works`): a `clear` verdict on the row-count disqualifier over a table outside 7–12 is reported `undecidable` with the measured count under `deterministic`, never blocking by itself.
