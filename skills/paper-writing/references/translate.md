## Translation to Spanish: `translate`

Some journals receive manuscripts only in Spanish: a national Publindex
journal whose catalog entry has `languages.english` false is the common case.
The paper is still **written in English first** (the section above holds
unchanged: `paper/main.tex` and its blocks stay English and canonical), and
only the finished, verified English paper is translated. The translation is a
derived artifact under `paper/translations/es/`, built block by block, and **no
`translate` verb ever writes `paper/main.tex`, `sections/` or `refs.bib`**.
The slash form is `/paper-writing translate es`.

```
paper/translations/es/translation.json   state: schema 1, language, source_main_sha256, one record per block, glossary
paper/translations/es/blocks/<id>.tex    the Spanish body of each canonical block
paper/translations/es/main.tex           built: canonical main.tex with every body in Spanish
paper/translations/es/audit.json         the last audit
paper/translations/es/main.pdf           compiled from the built file
```

A block is `missing` (no Spanish body), `current` (stored against the English
digest the block has now) or `stale` (its English changed after the store; it
must be translated again). A block with no prose (an equation alone) has
nothing to translate: `plan` carries it over as `current`.

**Fragments.** The prose `main.tex` holds outside every block is translated
too, since a Spanish paper keeps no English heading: `\title{}`, `\section{}`,
`\subsection{}`, `\subsubsection{}`, `\paragraph{}` (starred or not; an
optional short title `[...]` is a fragment of its own) and `\caption{}`.
Commented lines and arguments with no prose are skipped. Each fragment has a
stable id `<kind>-<n>-<sha8>`: its kind (`title`, `section`, `subsection`,
`subsubsection`, `paragraph`, `caption`), its ordinal among fragments of that
kind in document order, and the first 8 hex characters of the sha256 of its
English text. `translation.json` keeps them under `fragments` (`{id: {kind,
english, source_sha, state, spanish?, spanish_source_sha?, stored_at?}}`). A
fragment whose English changes gets a new id, and the Spanish stored for its
place makes it `stale` until it is stored again.

**The flow.**

1. Finish and verify the English paper (`verify` clean, no placeholder).
2. `translate plan --lang es [--term "<method name>"]...` writes
   `translation.json` and lists each block's work (id, the `paper/main.tex`
   lines, an excerpt, its state). Its glossary holds the paper's protected
   terms: acronyms in parentheses, `\texttt`/`\textsc` terms, and every
   `--term` the operator adds (kept across plans). It also lists every
   fragment (id, kind, English text, line, state).
3. Per `missing` or `stale` block or fragment, the translator writes the
   Spanish text and the orchestrator stores it with `translate store --lang
   es --block <id> --file <path>` or `translate store --lang es --fragment
   <id> --file <path>` (exactly one of `--block` and `--fragment`).
4. `translate audit --lang es` scores the stored blocks and checks each one's
   fidelity against the current English; the style reviewer reads it.
5. Fixes go back through the translator and `translate store`, never by hand.
6. `translate build --lang es`, then compile from `paper/translations/es/`
   (`pdflatex main`, `bibtex main`, `pdflatex main` twice). The built file
   finds `refs.bib`, figures and inputs two directories up.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py translate plan --lang es
.venv/bin/python skills/paper-writing/scripts/paper_cli.py translate store --lang es --block <id> --file paper/translations/es/drafts/<id>.tex
.venv/bin/python skills/paper-writing/scripts/paper_cli.py translate store --lang es --fragment <fragment-id> --file paper/translations/es/drafts/<fragment-id>.txt
.venv/bin/python skills/paper-writing/scripts/paper_cli.py translate audit --lang es
.venv/bin/python skills/paper-writing/scripts/paper_cli.py translate build --lang es
.venv/bin/python skills/paper-writing/scripts/paper_cli.py translate status --lang es
```

Every verb takes `--lang` (only `es` today) and `--paper <dir>`, prints one
JSON object, and on a refusal exits 2 having written nothing. Besides the
usual `status`/`code`/`detail`, a `translate` refusal also carries `ok:
false`, `error` (the code) and `message` (the detail), the shape the dashboard
reads; a success carries `ok: true`.

| Verb | What it does | Refuses |
| --- | --- | --- |
| `plan --lang es [--term <t>]...` | Writes `translation.json`; lists the per-block work, every fragment outside the blocks with its counts, and the glossary | `TRANSLATION_LANGUAGE_UNSUPPORTED`, `PAPER_ABSENT`, `TRANSLATION_NO_BLOCKS`, `TRANSLATION_SOURCE_PLACEHOLDER`, `TRANSLATION_SOURCE_INCOMPLETE`, `BLOCK_HAND_EDITED` and the marker codes |
| `store --lang es (--block <id> \| --fragment <id>) --file <path>` | A block: stores its Spanish body in `blocks/<id>.tex`, recording the English digest it was translated from and its style summary, and prints the block's full audit. A fragment: stores its Spanish text in `translation.json` against the English sha256 it has now | `TRANSLATION_NOT_PLANNED`, `BLOCK_ABSENT`, `TRANSLATION_FRAGMENT_UNKNOWN`, `BLOCK_ID_MALFORMED`, `TARGET_UNREADABLE`, `TRANSLATION_EMPTY`, `CONTENT_CARRIES_MARKER`, `TRANSLATION_PLACEHOLDER_TEXT`, `TRANSLATION_NOT_SPANISH`, `TRANSLATION_FIDELITY`, `BLOCK_HAND_EDITED`, `PAPER_OUTSIDE_REPOSITORY` |
| `build --lang es` | Writes `main.tex`: the canonical file with each block body in Spanish, its markers rewritten to `%% paper-writing translation <id> source <english-digest> begin\|end` so no canonical parser reads it as a block, each fragment's argument replaced by its Spanish text, and Spanish declared as the main language (babel `main=spanish` beside the languages already loaded, with `es-noshorthands` and `es-tabla`; polyglossia `\setmainlanguage{spanish}`; or a babel line when neither is there) | `TRANSLATION_NOT_PLANNED`, `TRANSLATION_INCOMPLETE` (names every missing or stale block and fragment), `BLOCK_HAND_EDITED` |
| `audit --lang es` | Writes and prints `audit.json`: `notice`, `document` and per-block `index`, `style_score`, `flow_score`, `redundancy_score`, `verdict` and `findings` (`category`, `fragment`, `hint`, `paragraph`, `sentence`), `cross_block_redundancy` and per-block `fidelity` against the current English | `TRANSLATION_NOT_PLANNED`, `TRANSLATION_NOTHING_STORED` |
| `status --lang es` | Read-only: each block's `state`, `source_digest` and `stored_at`, the counts, whether `main.tex` is built for the current English, the `main_tex` and `pdf` paths (or null), the last audit's `generated_at`, `index` and `verdict`, and each fragment's `id`, `kind` and `state` with `fragment_counts` | `TRANSLATION_LANGUAGE_UNSUPPORTED`, `PAPER_ABSENT` |

**The fidelity gate.** `store` refuses `TRANSLATION_FIDELITY`, listing every
difference, when the Spanish body does not keep the English block's citation
keys, `\label`/`\ref`/`\eqref`/`\autoref`/`\cref` targets, inline and display
math, numbers with their units, or paragraph count
(`paper_style_es.compare_facts`). A decimal comma for a decimal point, a
thousands separator, and a Spanish month name for an English one are not
differences. It also refuses `TRANSLATION_NOT_SPANISH` when the body still
reads as English (`paper_language`'s heuristic, inverted) and
`TRANSLATION_PLACEHOLDER_TEXT` for a TODO-like marker (the Spanish word for a
slope is not one). A fragment passes the same checks except the paragraph
count; it must also keep its braces balanced, hold no blank line, and differ
from the English (the same text with a lowercase letter is
`TRANSLATION_NOT_SPANISH`).

**The estimators.** `paper_style_es.py` (adapted from
LIAUNAL/propuestasmorfeo-ia `scripts/estilo_es.py`, Apache-2.0) is a
readability and redundancy index for Spanish prose: a pattern catalog (stock
phrases, filler adjectives, promotional words, vague attributions, periphrasis,
avoided copulas, English calques, chatbot templates, negative parallelism,
false ranges, second-person and regional register), closing gerunds, spaced
dashes and `--`, triads, long sentences, lexical diversity (MATTR), flow
(repeated connectors and openings, demonstrative openings, causal and relative
tails) and redundancy (repeated 5-grams across paragraphs, near-duplicate
sentences by Jaccard similarity, overused words). Glossary terms collapse to
one token first, so the paper's own vocabulary is never counted as
repetition. `index` runs 0 to 100, higher is better; the three scores run 0
to 1, lower is better. **It is a writing-quality estimate, not an authorship
test**: it says nothing about who or what wrote the text, its thresholds are
provisional, and it never refuses anything.

**The translation delegates to the `translator` agent.** It receives one
block's English body (or one fragment's English text), the glossary and, on
a revision, the reviewer's findings for it, and returns the Spanish text whole: neutral academic
Spanish, every fact kept, no new claim, no dropped sentence, no stock phrase,
calque, chatbot template, closing gerund, reflex triad, spaced em dash or
`--`, same paragraphs. It holds no write tool: the orchestrator saves the text
under `paper/translations/es/drafts/` and runs `translate store`.

**The review delegates to the `translation-style-reviewer` agent.** It reads
`audit.json`, the stored Spanish blocks and their English, judges what the
audit cannot see (meaning drift, an idea restated in other words, a calque the
catalog misses), quotes every location and proposes a rewrite per finding. It
never edits and never assigns a score; the translator applies each fix and the
orchestrator stores it again.

**Measure this before delegating (translator/translation-style-reviewer):**
confirm `translate status --lang es` runs, the block or fragment is `missing`
or `stale` for the translator, and, for the reviewer, that `audit.json` exists and its
`generated_at` is later than every reviewed block's `stored_at`.

**On a harness with no Task-tool delegation:** run both stretches in-process,
in the same order; their `tools:` line (read and search only) is then the
orchestrator's own discipline, not a structural guarantee.

| Situation | Action |
| --- | --- |
| `plan` refuses `TRANSLATION_SOURCE_PLACEHOLDER` or `TRANSLATION_SOURCE_INCOMPLETE` | The English paper is not finished: complete it through `write` and `verify` first |
| `store` refuses `TRANSLATION_FIDELITY` | Restore exactly the facts the message lists, missing and added, and store again |
| `status` shows a block `stale` | Its English changed after the store: translate it again from the current English |
| `build` refuses `TRANSLATION_INCOMPLETE` | Store every block and fragment the message names |
| `store` refuses `TRANSLATION_FRAGMENT_UNKNOWN` | The English changed since the id was listed; run `plan` again and use the current id |
