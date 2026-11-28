## The lifecycle: `reuse` and `exhaustion`

Operator-ruled, 2026-09-19 (`a-leftover-paper-is-offered-before-it-is-lost`):

```
downloaded -> ingested -> candidate for every claim with no record yet
                              |
                   validate -> holds          -> cited, counts toward coverage
                            -> does-not-hold  -> still a candidate for the others
                              |
        when EVERY open claim has its does-not-hold -> exhausted -> operator deletes
```

**The skill NEVER deletes on its own.** `reuse` and `exhaustion` are both
read-only reports over `paper_lifecycle.py`; the operator deletes with
their own explicit shell command. Neither verb needed `main.tex` open at
all — every read here goes through `paper_evidence.read_records`/`read_all_
records` (the JSONL store under `paper/.paper-writing/evidence/`) and
`paper_guidance`'s own registry, so neither raises a code of its own —
`PAPER_ABSENT`/`GUIDANCE_OUTSIDE_REPOSITORY`/etc. are already classified.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py reuse --block intro.claim
.venv/bin/python skills/paper-writing/scripts/paper_cli.py exhaustion
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `reuse --block <id> [--paper <dir>] [--guidance <dir>] [--min-sources <n>]` | Read-only: for `--block`'s own OPEN claims (recorded, not yet `min_sources`-satisfied), names which already-ingested, `evidence`-classed papers carry no verdict yet for each one — what stops the operator re-downloading a paper already on disk | none of its own |
| `exhaustion [--paper <dir>] [--guidance <dir>] [--min-sources <n>]` | Read-only, CORPUS-WIDE: every `evidence`-classed ingested paper's exhaustion state against every open claim in the WHOLE corpus (never one section's blocks alone) — `exhausted` when a `does-not-hold` covers every one; otherwise `active`, naming every claim still without a verdict from that paper | none of its own |

**A `does-not-hold` never masks a `holds`.** A paper carrying a `holds`
verdict anywhere is reported `active`, reason `"holds"`, regardless of what
every other claim decided about it — deleting a cited paper would break
that citation. **An empty open-claim set never means "exhausted."** Nothing
tried yet is not evidence of uselessness, so a freshly-ingested, never-
tested paper reports `active`, reason `"no-open-claims"`, not vacuously
`exhausted`.

**Corpus-wide, never per section.** `exhaustion`'s open-claim set unions
every block's own evidence store (`paper_evidence.read_all_records`),
because `validate --source-md` was never section-scoped to begin with — a
paper ingested under any `evidence`-classed `guidance/` root is already
citable from any block. Evaluating "uncited" within one section's blocks
alone would propose deleting a paper another section still needs; this is
exactly the mistake the operator caught before either verb was built.

### Decision Gates (reuse, exhaustion)

| Situation | Action |
| --- | --- |
| `reuse --block <id>` reports `openClaims: []` | Either nothing has been asked about this block yet, or every claim already asked already has `min_sources` distinct `holds` sources — check `validate`'s own coverage report to tell which |
| `exhaustion` reports a paper `active`, reason `"holds"` | Never a candidate for deletion — it is cited; `remaining` is reported empty on purpose |
| `exhaustion` reports a paper `active`, reason `"no-open-claims"` | Nothing has been tried against it corpus-wide yet — not a defect, and never "exhausted" by an empty set |
| `exhaustion` reports a paper `active`, reason `"remaining-claims"` | `remaining` names every claim, corpus-wide, this paper still carries no verdict for — the operator's own next search |
| `exhaustion` lists a paper under `exhausted` | Every corpus-wide open claim already carries this paper's own `does-not-hold` — the operator deletes it by hand; this skill never does |
