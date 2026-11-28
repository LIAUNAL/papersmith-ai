## The whole cut is argued before any section is claimed: `separate` and `bind`

Two more verbs, from `source-section-binding` and `source-separation-review`.
Five `requires_facts` ids are BINDABLE — read from a real document on disk,
never declared by hand: `formulation` (a `proposals/` document),
`experimental-design` (an `experiments/` document), `dataset` (an
already-ingested paper under `guidance/`), and `implementation`/`results`
(a target code repository — always reported unmeasured for binding purposes,
because a repository is measured by RUNNING it, never read as prose for
section binding, regardless of what files it happens to contain). The first
three resolve to a real document (a `PROSE` root's current revision, or an
`INGESTED` root's own paper); a binding for either kind names which
section(s) of that document feed the block's claim.

**The refusal that starts the loop fires only at `write`.** Every read-only
verb — `contract`, `order`, `readiness`, `phases`, `plan` — tolerates a
document-rooted bindable fact with no recorded binding and reports nothing
about it. Only `write`'s own gate, immediately after its phase check, turns
the same gap into a refusal: `SECTION_BINDING_ABSENT`, naming the block, the
fact, every lineage that root currently carries on disk right now, and a
`bind` invocation to run.

**Recording that binding is a two-step loop, not the one command the first
refusal names.** Answering `SECTION_BINDING_ABSENT` with `bind` alone now
refuses a second time: for a document-rooted fact, `bind` demands a SETTLED
`separate` round that already argued this exact claim.

```
write refuses SECTION_BINDING_ABSENT
  │  names the block, the fact, and a bare `bind` invocation
  ▼
separate --proposal <path>
  │  scores the WHOLE cut against the document's own structure;
  │  refuses on any defect, naming every instance of every class present
  ▼  score 0 → the cut is SETTLED; the payload names the exact
  │  `bind` invocation for every assignment
bind --block <id> --fact <id> --lineage <lineage> --section <title> ...
  │  refuses BINDING_UNARGUED unless a settled round just named
  │  this exact (block, fact) with this exact title set
  ▼
write proceeds
```

`separate --proposal <path>` reads an agent-authored JSON file — never a
hand-edited `sections/*.md` header, which ships with the corpus and must
stay byte-identical, and never conversation prose an agent merely
paraphrases:

```json
{
  "lineage": "field-survey",
  "concedes_to_round": 1,
  "assignments": [
    {"block": "overview.block-a", "fact": "formulation",
     "sections": ["1. Background on widget metrics"]},
    {"block": "methods.block-b", "fact": "formulation",
     "sections": ["2. Alignment estimators", "3. Proposed alignment objective"]}
  ]
}
```

`lineage` and `assignments` are required; `concedes_to_round` is optional and
names the round number this cut abandons in favour of itself. Each
assignment's `sections` is a list of unique, non-empty title strings — a
bare string, an unknown top-level key, a duplicate `(block, fact)` pair
across assignments, or assignments resolving through more than one source
root all refuse `SEPARATION_REPORT_UNREADABLE` before anything is scored.

**A block that compresses what another block expands shares its sections
with `"shares": true`.** An abstract states what the experimental set-up
transposes, so it must be grounded against the same sections — which a cut
lets exactly one block claim. An assignment with the optional boolean
`"shares": true` names sections WITHOUT claiming them:

```json
{"block": "abstract.slot-5", "fact": "experimental-design",
 "sections": ["4. Instruments", "7. Statistical tests"], "shares": true}
```

A share is left out of scoring entirely (it clears no orphan and causes no
overlap or gap), so it need not be contiguous. Every section it names
resolves as a claim's does (`<title>#<n>` included) and must be claimed by a
non-sharing assignment of the same cut; otherwise `separate` refuses
`SEPARATION_SHARE_UNCLAIMED`, naming each such title, before any round is
recorded — another share does not count. A settled round names its `bind`
invocation like any other, `bind` licenses it by the same four checks, and
`packet`/`write` resolve its bound sections exactly as a claim's, so a
transposition block's grounding reads them. `"shares": false` is the plain
claim; a cut without the key scores and records exactly as before.

**A title two or more headings share is named `<title>#<n>`.** A section
title names every heading that carries exactly that title; one heading is a
resolved section, two or more refuse `SECTION_TITLE_AMBIGUOUS`. For such a
repeated title, write `<title>#<n>` (no space before the `#`): the n-th
heading, in document order, whose title is exactly `<title>` —
`"Field Survey of Widget Alignment#2"`. The refusal names this syntax and
every occurrence with its line and level, e.g. `'Field Survey of Widget
Alignment#2' (line 13, level 1)`. The same spelling is used everywhere a
title goes: a cut's `sections`, `bind --section`, the recorded binding, and
the `write` gate and `packet` that resolve it. It is the only new spelling:
a title one heading carries keeps its one name (`<title>#1` for it refuses
`SECTION_NOT_IN_SOURCE`), so every title that resolved before resolves to
the same heading, and an ordinal past the last occurrence refuses
`SECTION_NOT_IN_SOURCE` naming how many there are. Scoring names each
claimable heading the same way, so two claimable headings sharing a title
are claimed, orphaned or overlapped each on its own. A managed revision
rendered before the deliberation engine escaped its pasted sources'
headings repeats the document title in every pasted copy; this is how such
a document is cut and bound without a new revision. The deliberation
engine's `RESOLVE_TARGET` reads the same form, counted the same way.

**Scoring, in one paragraph.** `separate` derives the document's own
claimable sections (every heading at the shallowest remaining level, once
any heading that wraps every other heading is eliminated — no heading-level
number is ever hardcoded), then scores the proposed cut against it:
**orphan** (a claimable title no assignment claims), **overlap** (a
claimable title two or more distinct blocks claim), **gap** (a title sitting
between two titles the same block claims, that the block itself does not
claim). A defect-free cut (total 0) is **settled**. A nonzero total raises
exactly ONE code by fixed precedence — overlap, then orphan, then gap — with
a detail naming every instance of every class present, never only the first
one found.

**Every structurally-valid round is recorded, whatever its score — settled
or not.** The record is the negotiation's own log, not a verdict: a losing
round stays readable so a later `concedes_to_round` can point back at it.
When `concedes_to_round` is given, `separate` recomputes BOTH totals from
disk — this cut's own score and the conceded round's score, from its stored
assignments, never trusting either round's stored `score` field — and
refuses `SEPARATION_CONCESSION_REGRESSED` if this cut scores strictly worse;
an equal total is accepted, never treated as a regression.

**`bind` demands that a settled round argued exactly this claim.** For a
document-rooted fact, `bind` refuses `BINDING_UNARGUED` unless a recorded
round: names the same root, lineage and document revision as resolved right
now; was scored against that document's exact bytes, digested at scoring
time (a newly published revision, or an in-place rewrite of the same
filename, both void the licence); settled at total 0; and named this exact
`(block, fact)` with this exact SET of titles — a subset or a superset of
the argued titles refuses just as a wrong block would. The refusal names
which of the four checks failed, both title sets when they disagree, and
the exact `separate --proposal <path>` invocation to run next.
`bind --reopen` is never guarded this way: withdrawing a binding never
needs an argument for the claim it is retracting.

**`separate` never records a binding, under any outcome.** A settled
(score-0) round only ever names the `bind` invocations it licenses; `bind`
remains the one place a binding becomes real, and it is still the only
verb `write`'s phase-gated corpus assembly ever reads back.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py separate \
    --proposal proposal.json
.venv/bin/python skills/paper-writing/scripts/paper_cli.py bind \
    --block overview.block-a --fact formulation --lineage field-survey \
    --section "1. Background on widget metrics"
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `separate --proposal <path> [--sections <dir>] [--paper <dir>]` | Reads an already-authored whole-cut proposal, resolves every named title against the document's own structure and the assembled corpus, scores it, and records the round it just argued regardless of outcome. Never records a binding | `SEPARATION_REPORT_UNREADABLE`, `SEPARATION_SECTION_UNCLAIMABLE`, `SECTION_NOT_IN_SOURCE`, `SECTION_TITLE_AMBIGUOUS`, `SEPARATION_SECTION_OVERLAP`, `SEPARATION_SECTION_ORPHANED`, `SEPARATION_NOTATION_GAP`, `SEPARATION_SHARE_UNCLAIMED`, `SEPARATION_ROUND_ABSENT`, `SEPARATION_CONCESSION_REGRESSED` |
| `bind --block <id> --fact <id> --lineage <lineage> --section <title> [--section <title> ...] [--sections <dir>] [--paper <dir>]` | Records which section(s) of a source document feed one block's own bindable requirement | `UNKNOWN_FACT`, `BINDING_FACT_NOT_BINDABLE`, `BINDING_LINEAGE_REQUIRED`, `BINDING_SECTIONS_REQUIRED`, `DECLARATION_FIXED`, `BINDING_UNARGUED` |
| `bind --block <id> --fact <id> --reopen` | Clears an already-recorded `(block, fact)` binding's fixed state instead of recording one — never gated by `BINDING_UNARGUED` | (none beyond `bind`'s own) |

**`--sections <dir>` here is the same corpus-directory override every other
verb carries** (default `sections/`) — it is never the list of section
titles a binding claims. That list is the repeatable `--section <title>`
(singular), a different flag entirely; do not confuse the two when reading
either command's own `--help`.

A document with a single section (an ingested dataset page) claims that section; a title wrapping two or more sections is never claimable.

### Decision Gates (separate, bind)

| Situation | Action |
| --- | --- |
| `write` refuses `DRAFT_NOT_ENGLISH` | The draft carries Spanish prose (the refusal names each line) — redraft it in English; only a paper that declares another main language in `main.tex` (babel/polyglossia) is written in it. No attempt is spent |
| `write` refuses `DRAFT_SECTION_HEADING` | A body block's draft carries a `\section{…}` or `\section*{…}` line; the refusal names each line. The section heading lives outside the blocks (`skeleton --frame` writes it), so drop it from the draft; a `\subsection` stays free. Back-matter blocks are exempt: the venue may give a declaration a section of its own. No attempt is spent and `main.tex` is untouched |
| `write` refuses `DRAFT_BOLD_LEAD_IN` | A draft of the introduction or the experimental set-up opens a paragraph or a list item on bold, a `{\bf …}` group, a run-in `\paragraph{…}` or a description label (`\item[…]`); the refusal names each line. Open the paragraph with a sentence that carries the transition from the previous one, and name a contribution item in plain text. Table cells and in-sentence emphasis are free. No attempt is spent, and `humanize --apply` refuses the same draft |
| `write` refuses `DRAFT_PLACEHOLDER_TEXT` | The draft still carries `por definir`, `TODO`, `TBD`, `FIXME` or `\todo` — write the content, or leave the block unwritten. No attempt is spent |
| `write` refuses `SECTION_BINDING_ABSENT` | Run `separate --proposal <path>` naming a whole cut for the missing claim's lineage, then the exact `bind` invocation the settled cut licenses |
| `separate` refuses `SEPARATION_SECTION_OVERLAP` / `SEPARATION_SECTION_ORPHANED` / `SEPARATION_NOTATION_GAP` | One code by fixed precedence overlap → orphan → gap; the detail names every instance of every class present — fix the cut and resubmit the same proposal file |
| `separate` refuses `SEPARATION_SHARE_UNCLAIMED` | A `"shares": true` assignment names a section no non-sharing assignment of the same cut claims — claim that section in the block that expands it, or drop it from the share. A share never covers a section on its own |
| `separate`, `bind` or `write` refuses `SECTION_TITLE_AMBIGUOUS` | The title is carried by two or more headings — name one as `<title>#<n>`, picking it from the occurrences and lines the detail lists |
| `separate` refuses `SEPARATION_SECTION_UNCLAIMABLE` | A named title resolves to a real heading outside the claimable set (the document's own title, or a subsection), or the document's claimable set could not be measured at all — `--file`/`contract` the section, or re-check the title against the document's own headings |
| `separate` refuses `SEPARATION_ROUND_ABSENT` | `concedes_to_round` names a round with no record for this exact `(root, lineage, revision)` — check the round number and that the document revision has not moved |
| `separate` refuses `SEPARATION_CONCESSION_REGRESSED` | This cut recomputes worse than the round it concedes to; both totals are recomputed from disk, never trusted from either round's stored record — argue a cut that is at least as good |
| `bind` refuses `BINDING_UNARGUED` | No settled round licenses this exact `(block, fact)` claim, or its licence expired (a new revision or an in-place rewrite voids it) — the detail names which of the four checks failed and the exact `separate` invocation to run next |
| A binding's own fact resolves to an unmeasured root | `bind` records as it always did, no `separate` round required — the payload reports `separation: unmeasured(<reason>)`, never a silent pass over a document that was never there to argue about |
