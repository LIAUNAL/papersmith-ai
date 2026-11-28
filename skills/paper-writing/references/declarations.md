## The paper's own decisions: declarations and provenance

Two more regions live in `main.tex` alongside its blocks, holding JSON
bodies rather than prose — `declarations` and `provenance`. Neither is
readable by Phase 1's block scanner: both markers share the `%% paper-writing
<kind>` lead-in but never the literal token `block` in slot 3, so
`MARKER_PREFIX`'s own `startswith` check skips them (proven in
`tests/test_paper_decisions.py::DisjointGrammarTests`).

`declare` records two kinds of value: a `declaration` (one of the nine
operator-input ids — `author-roles`, `grant-title`, `grant-code`,
`repository-url`, `keyword-bounds`, `classification-line`, `ethics-approval`,
`review-registration`, used by review workspaces only, and
`study-registration`, a primary study's registry, registration id,
registration date and first-enrolment date, copied from the operator's
registration record) or a `fact` resolution (one of the fifteen fact ids). Recording either fixes it immediately
— a further `declare` on the same id refuses `DECLARATION_FIXED` until
`--reopen <id>` clears exactly that entry.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py declare \
    --declaration repository-url --value https://example.org/repo
.venv/bin/python skills/paper-writing/scripts/paper_cli.py declare \
    --reopen repository-url
```

`declare --fact` records the digest of the fact's source (`proposals/`, `experiments/`, the ingested evidence; `dataset` also covers `experiments/`; `protocol`, `sample`, `outcomes` and `analysis-plan` the study protocol revisions under `protocol/`; `participant-flow` the counts in `study/flow.json`, a structured record hashed as the participant flow module hashes it, timestamp keys aside, so a re-stamped but unchanged record is no change). `readiness` and `phases` list `stale_facts` when that source changed since the declaration; that is a warning, not a refusal: check the value, then `declare --reopen <fact>` and declare it again.

**A fact can also be DECLINED, not just resolved.** `declare --decline
<fact-id> --reason <text> --condition <json>` records a fact the operator
has decided does not enter the paper for now — e.g. no experimental
protocol exists yet — as distinct from a fact simply not yet measured. All
three flags are mandatory together: `--reason` empty or missing refuses
`DECLINE_REASON_REQUIRED`, since an undocumented decline is
indistinguishable from an omission six months later; `--condition` missing
refuses `CONDITION_REQUIRED`; a malformed condition (not a JSON object, a
missing/wrong-typed required field, or a `path` resolving outside the
repository root) refuses `CONDITION_MALFORMED`; a `condition.type` outside
the closed vocabulary (today, only `"directory-empty-except"`) refuses
`UNKNOWN_CONDITION_TYPE`. A decline fixes the fact exactly like a
resolution does — declining an already-resolved fact, or resolving an
already-declined one, both refuse `DECLARATION_FIXED` until `--reopen
<fact-id>` clears it, the same single gate every other fixed record goes
through.

**The condition is what keeps a decline from going stale on a human's
memory.** It is re-evaluated fresh from disk on EVERY `readiness`/`phases`
call, never cached and never evaluated only once at decline time: a block
whose only missing facts are declines whose condition still holds reports
`declined`, naming the fact and its reason. Once the named condition no
longer holds — `"directory-empty-except"` means the path now contains
something beyond its own `ignore` allowlist, e.g. a real file landed in
`experiments/` — that same block reports `blocked` again, and the response
carries `stale_declines` naming the fact, its reason, its condition, and
what changed (`detail`). The skill never auto-unblocks a block just
because a lapsed condition suggests progress, and it never keeps quietly
reporting `declined` once the condition is gone either — it only surfaces
the lapse; the operator decides what happens next (declare the fact for
real, or re-decline on new grounds). A block missing even one live
(non-declined) fact, one whose decline has lapsed, or any declaration at
all, still reports `blocked` regardless of any other decline's own state —
a decline never masks a real gap.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py declare \
    --decline experimental-design --reason "no protocol exists yet in experiments/" \
    --condition '{"type": "directory-empty-except", "path": "experiments", "ignore": [".gitkeep"]}'
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `declare (--declaration <id> \| --fact <id> \| --reopen <id> \| --decline <fact-id> --reason <text> --condition <json>) [--value <v>]` | Records a declaration or fact resolution, clears one id's fixed state, or declines a fact with a disk condition re-checked on every later read. A PRODUCED fact (`contributions`, `problem-statement`, `gap`, `limitations`) can never be declared or declined directly — its satisfaction comes only from writing its producer block | `DECLARE_MODE_REQUIRED`, `DECLARE_MODE_CONFLICT`, `DECLARE_VALUE_REQUIRED`, `DECLINE_REASON_REQUIRED`, `CONDITION_REQUIRED`, `CONDITION_MALFORMED`, `UNKNOWN_CONDITION_TYPE`, `UNKNOWN_DECLARATION`, `UNKNOWN_FACT`, `DECLARATION_FIXED`, `DECLARATIONS_HAND_EDITED`, `PRODUCED_FACT_UNDECLARABLE` |

`substitute` also accepts an optional `--contract <path>`: it changes no
byte of what gets written to the block, only records — in the `provenance`
region — the contract file's sha256 digest as read at that exact moment and
the declarations region's current generation. A block substituted without
`--contract` is reported `unprovenanced`, never assumed current. `write`
records the same provenance on every successful write, for the contract
file it judged the block against, so a block rewritten after its contract
changed reads `current` again; a refused write records nothing.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py substitute \
    --block intro --body body.tex --contract sections/introduction.md
```

`plan` reads all three concerns — guidance classification, declaration/fact
fill state, and provenance state (`current`, `drifted`, `unprovenanced`) —
in one call, and writes nothing anywhere:

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py plan
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `plan [--guidance <dir>] [--sections <dir>]` | Read-only aggregation: guidance classes plus their declaration state, source root states plus their declaration state, declaration/fact fill state, per-block provenance state | `PAPER_ABSENT`, `TEX_UNDECODABLE`, marker/region grammar codes, `GUIDANCE_OUTSIDE_REPOSITORY`, `UNKNOWN_GUIDANCE_CLASS`, `MALFORMED_GUIDANCE_MARKER`, `SOURCE_DECLARATION_HAND_EDITED`, `GUIDANCE_DECLARATION_HAND_EDITED`, `SECTIONS_OUTSIDE_REPOSITORY`, `MALFORMED_HEADER`, `ID_COLLISION` (no new codes of its own — the two `*_HAND_EDITED` codes belong to `read_revisions_marker`/`_classify`, reached here because `plan` reads through the same readers) |

**`plan` names every declarable root's and every `guidance/` folder's
declaration state, in ONE shared vocabulary — never two.** A `sourceRoots`
key carries one entry per root `FACT_SOURCE_ROOT` knows, each naming that
root's existing measurement `state`/`documents`/`reason` plus a
`declaration` value; `guidance`'s own entries widen from a bare class
string to `{"class": ..., "declaration": ...}`. Both `declaration` values
are drawn from the SAME four-value vocabulary: `"undeclared"` (no marker),
`"declared-unsealed"` (a valid marker with no seal — every marker written
before this skill could seal one, and every marker written with `mark
... --unsealed`), `"declared-sealed"` (a valid marker whose recorded seal
matches), or `"n/a"` (a `REPOSITORY`-, `INGESTED`- or `STRUCTURED`-kind
source root, which carries no revisions rule at all — never applies to a `guidance/` folder,
since every listed one is classifiable). A worked `plan` reply, invented
names throughout:

```json
{"guidance": {"style-corpus": {"class": "style-reference", "declaration": "declared-sealed"},
              "scratch":      {"class": "unclassified",    "declaration": "undeclared"}},
 "sourceRoots": {"experiments": {"state": "document-rooted", "documents": 3,
                                 "reason": null, "declaration": "declared-sealed"},
                 "proposals":   {"state": "unmeasured", "documents": 0,
                                 "reason": "... holds no '*.md' documents",
                                 "declaration": "undeclared"}},
 "declarations": {"...": "..."}, "provenance": ["..."]}
```

**Reopening a fact or declaration invalidates the blocks that named it.**
`plan` reads the `sections/` corpus (`--sections` overrides it, same shape
as the other three corpus-reading verbs) to derive, per block, whether any
fact or declaration its own contract names was declared or reopened after
that block's own provenance was written — `declare`/`--reopen` both bump
a record's own generation counter; a block whose recorded generation is
now behind is reported `drifted`, the same state name a contract-byte edit
already used. No new state, no new field on-disk carries a literal "stale"
flag — this is a derived read-time property, recomputed on every `plan`
call from `paper_declarations.affected_blocks` (the reopen-scan function)
and the generation each record was last touched at, never from write
order.

**`guidance/` classifies as `style-reference` or `evidence`, from a
per-folder marker only — never a folder's name.** A folder with no
`.paper-writing.json` reports `unclassified`, including every folder on a
fresh clone; that is designed behavior, not a fault. Both classes have a
real, wired consequence: `style-reference` feeds the style channel
(`packet`/`resolve_style_set`, below) and, since `the-skill-stops-trusting-
memory`, GATES `validate --source-md` shut (`SOURCE_STYLE_REFERENCE`);
`evidence` is the one class `validate --source-md` accepts
(`SOURCE_NOT_EVIDENCE` otherwise) — classifying a folder is no longer a
label with nothing reading it back. Multiple evidence folders coexist;
ingested source-root status and bindings aggregate their documents, while
style-reference folders remain excluded. Paper identities must be unique
across evidence folders (`EVIDENCE_ROOT_AMBIGUOUS` otherwise).

**`read_registry` and the actual ingested papers live at two different
depths.** `read_registry` (above, driving `plan` and now `validate`)
enumerates exactly one level — `guidance/<category>/` — and reports each
category's own class or `unclassified`. The eight ingested papers this
skill ships sit one level further down, at
`guidance/<category>/<paper>/<paper>.md`; `ingested_papers` walks that
second level for `packet` below. `guidance/*/*` is a `.gitignore` pattern,
so `fd`/`rg` report that whole tree empty — both readers walk it with
`Path.iterdir()`, gitignore-blind by construction, never a shell call. A
category folder still unclassified on a given checkout keeps reporting
`unmeasured` through the style channel, and now refuses `SOURCE_NOT_
EVIDENCE` from `validate` — correct, and the operator's own pending
decision, not a defect.

**Two kinds of guidance folder coexist, ADDITIVELY.** A function-named
folder (`reference-papers`, `paper-guide`, `data-paper`,
…) is whatever the operator has always used it for — style references, a
general paper guide, a benchmark's own data paper — and every one of those
keeps flowing through `read_registry`/`classify_source_md` exactly as
before; nothing here deletes, moves or reclassifies any of them. A
**section citation folder** is a SECOND, independent kind: a folder whose
name equals a section id the parsed `sections/` corpus declares (from
`SECTION_ID` in a contract's own front matter — `introduction`,
`related-work`, `materials-and-methods`, … — never a hand-listed tuple,
since one went stale silently in this repository the day the skill grew
past its first three verbs). It holds exactly that section's own cited
PDFs, downloaded there for `paper-ingestion` to turn into evidence
(`no-citation-before-its-paper-is-ingested`, item 1). Nothing distinguishes
the two kinds structurally — a folder is read either way through the same
`.paper-writing.json` marker and the same `Path.iterdir()` walk
(`paper_guidance.section_citation_status`) — the ONLY thing that makes a
folder a section citation folder is its name matching a real section id;
an operator's function-named folder that happens to collide with a future
section id would simply become both at once, which is intended, not a
conflict to resolve. `plan` reports every corpus section's own citation
status under `sectionGuidance` — `{exists, classification, ingested,
pending_pdfs}` per section id — alongside `guidance`'s pre-existing
function-named-folder registry, in the same call.

**No `--adopt` exists for either region.** A hand-edited `declarations` or
`provenance` region refuses (`DECLARATIONS_HAND_EDITED` /
`PROVENANCE_HAND_EDITED`) and writes nothing — unlike a block body, a
region is a decision the machine reads back as authority, and adopting a
hand edit would launder an unreviewed change into "what was decided."
