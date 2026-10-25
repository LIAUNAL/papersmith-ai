# Worked invocations

Every invocation below is one that runs, from the repository root, exactly as
written. A reference documenting a command nobody can type is the same defect
this skill is pointed at other people's documents to find, so a lock drives
each of these and requires JSON on stdout.

## `roster` against the first subject

Derives the accepted-operation set of the deliberation host by driving it as a
real process and reading the roster out of its own refusal, then holds that
against every documented site the recipe declares.

```
$ python3 skills/skill-audit/scripts/audit_cli.py roster --subject skills/proposal-deliberation --probe-spec skills/skill-audit/references/probes/proposal-deliberation.accepted-operations.json --repo-root .
```

Exit `0`. Read `comparison` before reading the sets: `not-run` means no site
carried a closed roster, so `unregistered` is deliberately empty rather than
clean. `notes` names each site and the range that was searched.

## `roster` against the auditor itself

The same move, pointed back at this tool. `argparse`'s own refusal is the
roster, and the documented side is the subcommand table in `SKILL.md`.

```
$ python3 skills/skill-audit/scripts/audit_cli.py roster --subject skills/skill-audit --probe-spec skills/skill-audit/references/probes/skill-audit.subcommands.json --repo-root .
```

Exit `0`, with `unregistered` and `phantom` both empty. Add a subparser without
adding its row and `unregistered` names it; delete the row and leave the
subparser and `phantom` names it.

## `check-report` against a report

```
$ python3 skills/skill-audit/scripts/audit_cli.py check-report skills/skill-audit/references/example-report.md
```

Exit `0` and an empty `violations` list. Exit `1` lists what is missing, each
violation naming the item, why it matters, and where. Exit `2` means the report
could not be read at all, which is not the same claim as reading an invalid one.

## `structure` against the auditor's own layout

Derives the declared side from `SKILL.md`'s own `## The shipped files` table,
the on-disk side by walking `--subject` itself, and the from-zero side by
driving the recipe's own operator-declared driver -- `claude -p`, invoked
non-interactively, inside a fresh, empty box under `implementations/` -- then
removes the box and adjudicates arithmetically.

```
$ python3 skills/skill-audit/scripts/audit_cli.py structure --subject skills/skill-audit --spec skills/skill-audit/references/probes/skill-audit.structure.json --repo-root .
```

Exit `0` for any verdict, `outcome` included. Against an uncommitted change
this reads `builder-broken` — the from-zero side is built from `HEAD`, so a
file added on disk but not yet committed is genuinely absent from a fresh
install, and that is documented as accurate rather than papered over.

## `walkthrough` against the auditor's own first-run flow

Drives an ordered sequence of real invocations against one shared box under
`implementations/`: `check-report` refusing to read a report that does not
exist yet, `check-report` accepting the shipped example, and `roster` against
the auditor's own subcommand surface. Each step is held to its own declared
`expect`; the first step whose observation contradicts it is the stall.

```
$ python3 skills/skill-audit/scripts/audit_cli.py walkthrough --subject skills/skill-audit --spec skills/skill-audit/references/probes/skill-audit.first-run.json --repo-root .
```

Exit `0` for any verdict, `stall` included. A `null` `stall` means every step
matched its own expectation; a non-`null` `stall` names the step's index and
kind, and `unreached` lists every gate at or after it. A step may declare
`"role": "setup"` to stand up a fixture without asserting anything about the
subject; a setup step is never counted among `gates.passed`, and its failure
is reported directly as `"setup-failed"` at exit `2` -- never `"stalled"` --
because a void run has no unchecked gates, it has no run.

## `reading-diff` against the shipped reading pair

Two supplied readings of the same prose surface -- this skill's own
subcommand table -- compared by mechanical diff. Neither reading calls
`doctrine_side` or `probe_code_side`; a subcommand, not a flag, is what
keeps `comparison` at `not-run` for this surface permanently, whatever the
two readers agree on.

```
$ python3 skills/skill-audit/scripts/audit_cli.py reading-diff --surface subcommands --reading skills/skill-audit/references/probes/skill-audit.reading-a.json --reading skills/skill-audit/references/probes/skill-audit.reading-b.json
```

Exit `0`, `agreement: "single-reading"` -- both readers name the same five
subcommands, so `onlyIn` is empty on both sides. `comparison` stays
`"not-run"` regardless: two readers agreeing proves the prose has one
reading, never that it is closed. `candidates` carries the shared set, for
a caller to drive as `walkthrough` gates next; `reading-diff` itself never
runs a process.

## `sensitivity` against the auditor's own layout

This skill declares no computed-value table of its own -- it is a
validator, not a subject reporting metrics that depend on inputs -- so
this invocation exercises the honest degenerate path rather than a real
sweep: `SKILL.md` carries no `| Metric | Value |` table, and `sensitivity`
reports that first-class result rather than inventing a roster.

```
$ python3 skills/skill-audit/scripts/audit_cli.py sensitivity --subject skills/skill-audit --spec skills/skill-audit/references/probes/skill-audit.sensitivity.json --repo-root .
```

Exit `2`, `notes` naming "this subject declares no computed values" and the
range searched -- not an error, and not a clean verdict. A subject that does
declare a results table instead reports `control`, `matrix`,
`notAdjudicable`, `inputsVaried`, and `inputsUnchecked`, exactly like
`## Computed-value provenance` transcribes.

## `inversion` against the auditor's own guarded fact

Mutates `scripts/audit_cli.py` itself, in the real tracked tree, one guarded
fact at a time: `REPORT_SCHEMA_VERSION`'s own declared value, whose
observing run is `SchemaVersionDerivationTests` -- a real test class this
repository already ships, driven from the repository root because its
declaring test lives outside `--subject`. Every mutation is restored from
recorded bytes before this invocation returns, whatever its verdict.

```
$ python3 skills/skill-audit/scripts/audit_cli.py inversion --subject skills/skill-audit --spec skills/skill-audit/references/probes/skill-audit.self-guarded-facts.json --repo-root .
```

Exit `0`, `matrix` naming the one guarded fact `"fires"`: the mutated value
disagrees with `SKILL.md`'s own stated schema version, so
`SchemaVersionDerivationTests` goes red exactly as declared, and the byte
mutation is restored before this invocation exits.

## `exits` against the auditor's own doctrine

Two states declared against `SKILL.md`'s own Decision Gates table: whether
an occupied from-zero box's own documented remedy ("remove it by hand") is
ever published as a runnable act, and the build-or-delete judgement every
not-adjudicable finding carries.

```
$ python3 skills/skill-audit/scripts/audit_cli.py exits --subject skills/skill-audit --spec skills/skill-audit/references/probes/skill-audit.exits.json --repo-root .
```

Exit `0`. `exits` names the occupied-box remedy `"unstated"` -- the doctrine
states a mechanical remedy in prose and never publishes it as a runnable
act, which is a real, if minor, gap in this skill's own documentation -- and
the build-or-delete decision `"judgement"`, correctly reported and not a
finding.

## `enumeration-reach` against two of this suite's own checks

Two of `tests/test_skill_audit.py`'s own checks, classified: one iterates a
hand-written tuple directly (`literal-collection`), the other calls
`subcommand_surface(...)`, a real derivation (`derived`).

```
$ python3 skills/skill-audit/scripts/audit_cli.py enumeration-reach --subject skills/skill-audit --spec skills/skill-audit/references/probes/skill-audit.enumeration-reach.json --repo-root .
```

Exit `0`. `bounded` names the one check whose enumeration is a literal
collection; the other's `kind` reads `"derived"` and it is absent from
`bounded` -- reported plainly, never escalated.

## Exit codes, in one place

| Exit | `roster` | `check-report` | `structure` | `walkthrough` | `reading-diff` | `sensitivity` | `inversion` | `exits` | `enumeration-reach` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `0` | it looked, and this is the verdict | the report is valid | it looked, and this is the outcome | it looked, `stall` included | it compared, agreement or divergence | it looked, `not adjudicable` findings included | it looked, `not adjudicable` findings included | it looked, every state's outcome included | it looked, every check's classification included |
| `1` | not used | the report is invalid | not used | not used | not used | not used | not used | not used | not used |
| `2` | it could not look | the report could not be read | a side could not be derived, the box was not empty, or the build escaped it | a step declared no expectation, the box was not empty, the flow was never entered, a `kind: "setup"` step failed (`"setup-failed"`), or the recipe declared no `"gate"` step at all | not exactly two `--reading` flags, or a reading file could not be read or named an empty `members` list | no declared computed values, an occupied box, a stalled control, a refused baseline (`kind=sensitivity-baseline-refused`: the producer refuses with every input present), a restore mismatch, or an escape | no `mutations` block, an absent/ambiguous fact, an operator-flip, a no-op write, a non-green baseline, a restore mismatch, or an escape | no `states` block, an occupied box, or an act escaping to the real subject | no `checks` block, a check naming no site, or a named check not found in its own site |
