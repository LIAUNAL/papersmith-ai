---
name: study-protocol-deliberation
description: "Trigger: deliberate the protocol of an empirical study before any datum is collected: create, amend or manage revisions of protocol/study-protocol-<slug>-vNN.md through the keyless engine. Never invents data or the primary outcome."
---

# Study Protocol Deliberation

**Scope.** Session-local deliberation about the protocol of an empirical study (observational or measurement, experiment or intervention, qualitative or participatory, hardware, lab or simulation, data resource) before any datum is collected or analysed — first-version creation, amendments of an existing managed protocol, or managed-revision lifecycle operations. Keeps the protocol as labelled fields (research question, one primary outcome, secondary outcomes, design, eligibility, sample size and its justification, analysis plan) in protocol/study-protocol-<slug>-vNN.md through the keyless bounded engine. Never invents data, a sample size from data it has not seen, or the choice of the primary outcome.

Invoking this skill conditions **you, the running agent**, to become the
methodologist for this deliberation. The engine is a deterministic, byte-exact
executor; you propose, discuss and refute the protocol with the operator, and
the engine writes only what the operator accepted.

This is the shared deliberation engine's third domain profile, beside
[`proposal-deliberation`](../proposal-deliberation/SKILL.md) (mathematics) and
[`experimental-deliberation`](../experimental-deliberation/SKILL.md)
(experiment plans). The writing scaffold is the same — resolve a locus, patch
it, preview, acknowledge, publish — and that skill's
[Applying an approved change](../experimental-deliberation/SKILL.md#applying-an-approved-change)
and [Resolving the base version](../experimental-deliberation/SKILL.md#resolving-the-base-version)
hold here word for word, with `protocol/` and `.study-protocol-deliberation/`
in place of `experiments/` and `.experimental-deliberation/`. What a protocol
must say is this skill's own.

## When to use it

For the empirical lines of smith (S8): observational and measurement studies,
experiments and interventions, qualitative and participatory studies, hardware,
lab and simulation studies, and data resources — any study whose question,
primary outcome and analysis must be fixed before its data exist. It is not
for the applied-AI line (its plan is `/experimental-deliberation`) nor for the
review line (its protocol is `/systematic-review`'s G-PROTOCOL).

The skill ships to every workspace, and each of the six empirical lines
(observational-measurement, hardware, lab-simulation, data-resource,
experiment-intervention, qualitative-participatory) calls it from its own flow.

## The objective flow

**Why this skill was invoked, and where it has to arrive.** Declared here and
in this skill's own `profile.ts` `objective` field, held equal by a test, and
independent of any document on disk. `STATUS` answers *where am I* by listing
what has been published; this answers *what is this for*. `STATUS` reports it
above the inventory, and both of the engine's CLI-level error paths carry it
too — that is its complete reach. A typed refusal returned as a value from
`tool.execute` does not carry it; run `STATUS` to recover it.

The profile's wording avoids words the shared core already spells (a lock
holds every domain's north apart from the engine), so the table says *main
endpoint* for the `**Primary outcome:**` line and *main analysis* for the
`**Primary model:**` line.

**Purpose:** carry the study protocol that was discussed as far as a published
managed revision — its aim, its main endpoint, its eligibility, its sample size
and its analysis plan, in a document that exists and is the current one.

| Stage | Establishes | Behind you when |
| --- | --- | --- |
| `bound` | Which revision is current and which entry of it the change touches | `STATUS` named the latest and the target resolved to an entry |
| `validated` | The aim, the main endpoint, the eligibility, the sample size with its justification and the analysis plan are each stated once, none of them stating findings | No main endpoint or two of them, an endpoint with no id, measure or timing, a sample size with no target or no justification, an analysis plan with no main analysis named, or a line stating findings, stops this stage |
| `deliberated` | The change was argued through rather than typed | **the user said so** — nothing here measures it, and nothing may |
| `composed` | The replacement exists written as the protocol, not a description of it | A block exists carrying the change |
| `published` | The successor exists carrying the artifact marker and is the current revision | This is the arrival; it is behind nobody |

**Arrival:** the successor revision published and current, which is the only form the study protocol travels in.

**There is no entrance from outside.** No other skill hands this one a finding.

**Three stops are a person's:** picking the primary outcome, accepting the
change, which closes `deliberated`, and authorizing publication, because it
advances the real lineage.

## What stays human

- **The choice of the primary outcome is the operator's.** You may list
  candidates and their trade-offs; you never pick one, and a draft with no
  `**Primary outcome:**` line is refused rather than completed by you.
- **You never invent data**, a pilot result, an effect size, a variance or a
  dropout rate. A sample size comes from a calculation whose inputs the
  operator supplied or a cited source states, or from a rationale the operator
  gives (feasibility, saturation, a fixed population). Never compute a sample
  size from data you have not seen.
- **Ethics, consent, registration and data collection stay human.** This skill
  writes none of them.
- Accepting a change and authorizing publication are the operator's, as above.

## The document

Managed revisions live in `protocol/` as `study-protocol-<slug>-vNN.md`
(`study-protocol-walking-hypertension-v01.md`, then `-v02.md`). The slug is
derived from the first sentence of the idea at v1 and stays for the lineage;
the engine's first-revision matcher requires one, so there is no slugless form.
State and receipts live under `.study-protocol-deliberation/` (`state/`,
`receipts/`, `locks/`), which a workspace should keep out of version control
like the siblings' sidecars.

Every decision is a **labelled line**: a bold label, optionally carried by a
list bullet, the colon inside or outside the bold, and the value as the rest
of the line. Section headings are free; the labels are what is read.

| Label | Required | Value |
| --- | --- | --- |
| `**Research question:**` | exactly once | the question the study answers |
| `**Primary outcome:**` | exactly once | `O<n> -- <measure>; time point: <when>` |
| `**Secondary outcome:**` | zero or more | `O<n> -- <measure>; time point: <when>`, one line each |
| `**Secondary outcomes:**` | when there are none | `none` |
| `**Design:**` | exactly once | the design (arms, allocation, blinding, setting) |
| `**Eligibility:**` | exactly once | inclusion and exclusion criteria |
| `**Sample size:**` | exactly once | the target number, with a digit |
| `**Sample size justification:**` | exactly once | the calculation (effect, variability, alpha, power, attrition) or the rationale |
| `**Primary model:**` | exactly once | the analysis of the primary outcome |
| `**Covariates:**` | exactly once | the adjustment set, or an explicit `none` |
| `**Missing data:**` | exactly once | how missing data are handled, or `not applicable` |
| `**Multiplicity:**` | exactly once | how multiple comparisons are handled, or `not applicable` |

Outcome ids are `O1`, `O2`, ... and never re-numbered: an amendment adds or
demotes an outcome, it does not shift the others. The analysis plan and the
prose cite an outcome as `[outcome:O1]` or `(Outcome O1)`. The SPIRIT 2025
items beyond these fields (schedule, interventions, data management,
monitoring, dissemination) are optional prose under headings of your choice.

```markdown
**Research question:** In adults with stage 1 hypertension, does a 12-week supervised walking programme lower systolic blood pressure compared with usual care?

**Primary outcome:** O1 -- change in seated systolic blood pressure (mmHg) from baseline; time point: 12 weeks

**Secondary outcome:** O2 -- change in diastolic blood pressure (mmHg); time point: 12 weeks

**Design:** two-arm, parallel-group randomised controlled trial, 1:1 allocation, assessor-blinded

**Eligibility:** adults aged 40 to 70 with untreated stage 1 hypertension

**Sample size:** 148 participants (74 per arm)

**Sample size justification:** a two-sided t-test at alpha 0.05 with 80% power detects a 5 mmHg difference (assumed SD 10 mmHg, from the operator's cited source) at 64 per arm, inflated by 15% for attrition

**Primary model:** ANCOVA of the 12-week systolic change on arm, adjusted for baseline, for [outcome:O1]

**Covariates:** baseline systolic blood pressure, age, sex

**Missing data:** multiple imputation by chained equations under missing at random

**Multiplicity:** not applicable to the single primary outcome
```

**One parser.** `protocol-fields.ts` is the only reader of this grammar:
`parseProtocol(source)` returns every field, the outcomes with their ids,
measures and time points, and `primaryOutcomeId`; `outcomeIds(source)` returns
`{ primary, secondary }`. The preservation gate, the reference module and the
later units (the analysis log maps a run to the analysis plan; verify compares
the manuscript's primary outcome with the protocol's) all read it; a reader in
another language mirrors this table, never a variant of it.

## The canonical form

Checked on v1 and on every successor, before anything is written
(`preservation-study-protocol.ts`, `violations`). A refusal names its rule:

| Rule | Raised when |
| --- | --- |
| `primary-outcome-missing` | no `**Primary outcome:**` line |
| `primary-outcome-repeated` | more than one `**Primary outcome:**` line |
| `outcome-without-id` / `outcome-without-measure` / `outcome-without-time-point` | an outcome line lacks its `O<n>`, its measure or its `; time point:` |
| `outcome-id-repeated` | two outcomes share an id |
| `secondary-outcomes-undeclared` / `secondary-outcomes-contradictory` | neither secondary lines nor `**Secondary outcomes:** none`, or both |
| `research-question-declaration-missing`, `design-declaration-missing`, `eligibility-declaration-missing`, `sample-size-declaration-missing`, `covariates-declaration-missing`, `missing-data-declaration-missing`, `multiplicity-declaration-missing` | the field is absent or holds a placeholder (`TBD`, `pending`, `?`) |
| `<field>-declaration-repeated` | a single-valued field is declared twice |
| `sample-size-without-number` | the sample size names no number |
| `sample-size-without-justification` | the sample size has no justification, or a placeholder one |
| `analysis-plan-without-primary-model` | no `**Primary model:**`, or a placeholder one |
| `field-states-result` | the research question or an outcome field reports a result: a p-value, "was reduced", "we found", "outperformed" |
| `url-without-verification-marker` | a URL not followed by `[pending-verification]` or `[verified: YYYY-MM-DD]` (the experimental convention) |

An explicit `none` or `not applicable` is a decision for covariates, missing
data and multiplicity; it is never one for the question, the design, the
eligibility, an outcome's measure, the sample size or the primary model.

Because v1 has no skeleton, **the whole field block arrives in the idea text**
of `CREATE_INITIAL_REVISION`, after the two sentences that name the document
(title and section heading). Draft it with the operator first; a draft missing
a field is refused, not padded.

## Preservation: what must not vanish in silence

Every field is an atom keyed by its content (whitespace, case and trailing
punctuation folded): `research-question:<hash>`, `primary-outcome:O1:<hash>`,
`secondary-outcome:O2:<hash>`, `design:<hash>`, `eligibility:<hash>`,
`sample-size:<value>`, `primary-model:<hash>` and `url:<url>`. An amendment
that changes one reports it in `preservationDelta.lost`, and the accept turn
is refused (`MATH_REMOVALS_NOT_ACKNOWLEDGED`, the engine's legacy name) until
every lost id is echoed back in `acknowledgedRemovals`. So **switching what
the primary outcome measures, or when, is never silent**: `primary-outcome:O1`
keeps its id and loses its hash, and only an acknowledged amendment publishes
it. Record the operator's reason in `changeSummary.why`; the document's own
`## Changes` block carries it.

## The bound on claims

A protocol is written before its data are collected or analysed. The
profile's `sourceAuthority` (advisory, bound `guidance/data-paper`) reports
every line anywhere in the document that states a result, so a background
paragraph restating somebody else's published finding is acknowledged by id
(`acknowledgedSourceConflicts`) rather than refused. The research question
and the outcome fields never get that latitude: `field-states-result` refuses
them outright. The planning fields (design, eligibility, sample size and its
justification, the analysis plan) may cite a significance threshold, a
past-tense screening criterion or a pilot estimate; result language there is
reported by the advisory bound like any other line.

## Sources

Both optional: `guidance/paper-guide/` (methodological references) and
`guidance/data-paper/` (the description of an existing dataset the study
analyses). Present ones are loaded once at v1 under `## Reference Sources`,
and their text faces the same canonical form (an untagged URL in a source
refuses v1, as in the siblings).

## Commands

Launch only through this skill's own `cli.mjs`; the shared core refuses to
start without a domain profile.

```bash
node skills/study-protocol-deliberation/cli.mjs '{"operation":"STATUS"}'
node skills/study-protocol-deliberation/cli.mjs '{"operation":"CREATE_INITIAL_REVISION","instruction":"<two sentences, then the field block>","dryRun":true}'
node skills/study-protocol-deliberation/cli.mjs --serve
```

An amendment is `RESOLVE_TARGET`, then `CREATE_SUCCESSOR` on one `--serve`
stdin: the preview, then the same request with `acceptSuccessor: true`, its
token and `acknowledgedRemovals`. `changeSummary: { what, why }` is required on
every preview.

## Other engine operations

| Operation | Use it for |
| --- | --- |
| `STATUS` | Read-only, keyless inventory of `protocol/`. Never mutates. Run it at the start of every deliberation. |
| `RESOLVE_TARGET` | Read-only locus resolution, using the exact resolver `CREATE_SUCCESSOR` uses internally. |
| `ADOPT_INITIAL_REVISION` | Makes an existing document in `protocol/` v1, through the same gate, state and receipt as `CREATE_INITIAL_REVISION`. |
| `CREATE_INITIAL_REVISION` | Creates v1 from the idea (its two naming sentences, then the field block) plus the optional sources, only when no managed revision exists. Preview it with `"dryRun": true` first. |
| `WITHDRAW_REVISION` | Withdraws one eligible managed revision, preserving an audited recovery copy. Not content deletion. |
| `RESTORE_WITHDRAWN_REVISION` | Restores a previously withdrawn revision from its audited copy. |

`CHAT_DELIBERATION`, `CLOSE_DELIBERATION` and `MAINTENANCE` are accepted by the host but outside this skill's flow. Anything else is refused by name with `UNKNOWN_OPERATION`.

No `ANTHROPIC_API_KEY` and no model call is ever needed on this path.

## The lock

Publishing a revision does not approve it. The operator passes gate
G-STUDY-PROTOCOL with `python skills/_core/empirical/study_cli.py protocol
approve --by <operator> --root .`, which pins the latest managed revision (or
the one `--revision` names) by the sha256 of its bytes in
`study/protocol.lock.json`. Once it is approved, a newer published revision
leaves the lock `changed` until the operator runs `protocol amend --by
<operator> --reason <why>`; the amendment moves the lock to that revision and
keeps the history. The ethics approval (`ethics record`) and the registration
(`registration record`, a retrospective one flagged) are recorded beside the
lock and bound to its sha256, so an amendment marks them stale until the
operator records them again. In an intervention study the allocation record
follows the locked protocol: the operator generates the allocation sequence
with their own tool or service and runs `study_cli.py allocation record --by
<operator> --file <list> --method <method> --concealment <how>`, which binds
the list's sha256 and row count and the lock's sha256 (gate G-ALLOCATION) and
goes stale when the list changes or the protocol is amended. You never
generate, read out, alter or reveal an allocation sequence, and never open the
allocation list. You never run `approve`, `amend` or `record`
yourself: you tell the operator the command. Until `protocol status` answers
`current`, never describe a revision as locked or approved, and never
describe the study as approved by an ethics committee or registered unless
`study_cli.py status` shows that record current. See
[`skills/_core/empirical/README.md`](../_core/empirical/README.md).

## The analysis log and its labels

Once data exist, every analysis is logged in `analysis/log.jsonl` by
`python skills/_core/empirical/analysis_cli.py run --outcome O1 [--plan
primary-model] --input <data> --output <result> --root . -- <command>`, which
hashes the script, the inputs and the lock before running and the streams and
outputs after; an analysis the operator ran in a GUI tool is entered by the
operator with `analysis_cli.py record --by <operator> --tool <name> ...`.
Each entry is labelled `confirmatory` or `exploratory` by the log, never by
you or the operator: confirmatory only when the lock is current and the
outcome (and the plan entry named) is in the locked revision, which the log
reads through `fields.mjs`, this skill's parser entry point. A run before the
lock, of an outcome the protocol does not name, or of an unplanned analysis
is exploratory, and stays so; only an amendment that adds the outcome makes a
later run confirmatory, and `analysis_cli.py status` flags an outcome first
analysed before the amendment named it. Never present an exploratory result
as a confirmatory one, and never suggest an amendment to turn one into the
other: an amendment records a decision the operator took for a reason, and
the paper reports it. `paper_cli.py verify` fails a manuscript whose primary
outcome is not the locked one unless an amendment declared the switch. See
[`skills/_core/empirical/README.md`](../_core/empirical/README.md#the-analysis-log).
