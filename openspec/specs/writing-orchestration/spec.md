# Writing Orchestration Specification

## Purpose

The `write` verb sequences readiness, evidence-bound drafting, and contract
auditing into one pipeline, with exactly one bounded re-draft, and it commits
a block to `main.tex` only when both audits clear. This capability owns the
pipeline's order and its exhaustion path — not the two audits' own rules,
specified elsewhere.

## Requirements

### Requirement: Pipeline Stage Order

`write` MUST run its stages in this order for one block: readiness, gate,
draft, evidence-audit, contract-audit, `substitute --contract`. A stage MUST
NOT start until every earlier stage has cleared.

#### Scenario: A failing evidence-audit stops the pipeline before contract-audit

- GIVEN a draft whose binding map fails evidence-audit (for example
  `UNBOUND_SENTENCE`)
- WHEN `write` runs
- THEN contract-audit never runs and `substitute` is never called

### Requirement: One Bounded Re-Draft

When contract-audit reports at least one `fires` verdict, `write` MUST
attempt exactly one re-draft, carrying the fired bullets and their quoted
spans as explicit feedback to the redactor, and MUST audit the result with
the same auditor and the same inputs. `write` MUST NOT attempt a third draft.

#### Scenario: A second attempt is audited with the same inputs

- GIVEN a first draft whose contract-audit reports `fires` on bullet B
- WHEN `write` re-drafts
- THEN the re-draft's input includes bullet B's quoted span and the same
  contract, evidence set, and mode as the first attempt

### Requirement: Exhaustion Leaves The Block Unwritten

When the re-draft's contract-audit also reports at least one `fires` verdict,
`write` MUST refuse `AUDIT_EXHAUSTED`, naming every bullet that fired on the
second attempt, and MUST NOT call `substitute`. The block MUST remain absent
from `main.tex`.

#### Scenario: Two failing audits leave main.tex unchanged

- GIVEN a block whose first and second drafts both fire the same disqualifier
- WHEN `write` completes its bounded retry
- THEN it refuses `AUDIT_EXHAUSTED` naming the fired bullet, and `main.tex` is
  byte-identical to its state before `write` ran

### Requirement: No Live Agent Invocation In Tests

Every test exercising `write`, the redactor, the contract-auditor, or the
style-sampler MUST run against recorded agent transcripts and fixture
evidence sets. No test MUST spawn a live agent process. A guard test MUST
assert that no subprocess naming an agent binary is launched during the
suite's run.

#### Scenario: The suite runs with zero live agent subprocesses

- GIVEN the full test suite
- WHEN it runs to completion
- THEN the live-agent guard reports zero subprocess launches naming an agent
  binary
### Requirement: Packet Assembly Precedes Draft

Before the `draft` stage runs for a block, `write` MUST assemble that
block's redactor packet (`redactor-packet`) and pass it to the draft stage
alongside the existing evidence set and mode. A draft stage invoked without
an assembled packet MUST NOT proceed.

#### Scenario: The draft stage receives an assembled packet

- GIVEN a block entering the `write` pipeline with at least one
  `style-reference`-classed `guidance/` entry
- WHEN the pipeline reaches the `draft` stage
- THEN the redactor packet was assembled before that stage ran, and the
  draft stage's input includes it

### Requirement: Packet Assembly Shuttles Through Files, Never A Live Process

Packet assembly and every agent shuttle it depends on (`style-sampler`)
MUST exchange data through files read and written by the pipeline itself —
never by invoking `subprocess` or any other live process spawn. This is the
same no-subprocess discipline `NoSubprocessScanTests` already enforces
repository-wide, restated here because packet assembly is new code in this
pipeline.

#### Scenario: The suite's subprocess guard covers packet assembly

- GIVEN the full test suite, including tests exercising packet assembly
- WHEN it runs to completion
- THEN the repository-wide no-subprocess guard reports no `subprocess`
  import anywhere in the packet-assembly code path
### Requirement: Section Binding Resolution Gates `write`, Not Only A Read-Only Verb

When `write` assembles the corpus for the block it is about to draft, ANY
refusal this change introduces — `SECTION_NOT_IN_SOURCE`,
`SECTION_TITLE_AMBIGUOUS`, `SECTION_BINDING_ABSENT`,
`SOURCE_LINEAGE_UNRESOLVED`, `SOURCE_REVISIONS_UNDECLARED` or
`MALFORMED_SOURCE_MARKER` — raised by that assembly
(`source-section-binding`) MUST stop `write` before the readiness stage
begins: no draft, evidence-audit, or contract-audit byte MUST be read for
that block, and the block MUST remain absent from `main.tex`. A read-only
verb (for example `phases`) having already reported the same broken binding
MUST NOT be treated as sufficient: `write` MUST perform its own corpus
assembly and raise the refusal itself, never rely on a cached report a
read-only verb produced earlier.

`EVIDENCE_ROOT_AMBIGUOUS` (`source-section-binding` spec, added by U2c) is
computed unconditionally for every root `Corpus.source_roots` names, inside
the SAME corpus assembly the six codes above reach `write` through — it
MUST therefore also stop `write` before the readiness stage begins, under
the identical rule: never reachable only from a read-only verb.

`SECTION_BINDING_ABSENT` (U3b correctness repair) is the one code among the
seven this `write` MUST reach through its own corpus assembly and NOWHERE
ELSE: an undecided binding is reported (`source-section-binding`,
`Corpus.undecided_bindings`) rather than refused everywhere else in the
skill, so `write`'s own assembly is not merely the FIRST place this code is
proven reachable — after U3b it is the ONLY place. This narrower rule does
not weaken the requirement above; it sharpens it for exactly the one code
whose unconditional form (U3's own shipped behaviour) forced an agent to
invent a binding rather than leave any assembly refusing.

#### Scenario: `write` refuses before drafting on an unresolved binding

- GIVEN a block whose bindable requirement's bound section title is absent
  from the resolved revision
- WHEN `write` is invoked for that block
- THEN it refuses `SECTION_NOT_IN_SOURCE` naming the binding, before the
  draft stage runs, and `main.tex` is byte-identical to its state before
  `write` ran

#### Scenario: `write` refuses on a source root whose revision rule is undeclared

- GIVEN a block whose bindable requirement names a lineage under a
  document-rooted source root that carries no `.paper-writing.json` marker
- WHEN `write` is invoked for that block
- THEN it refuses `SOURCE_REVISIONS_UNDECLARED` naming the root, before the
  draft stage runs — the marker codes reach `write` through the same corpus
  assembly as the binding codes, and MUST NOT be reachable only from a
  read-only verb

#### Scenario: A read-only verb's prior report does not excuse `write`'s own check

- GIVEN a corpus whose section binding a read-only verb already reported
  broken, unchanged since that report
- WHEN `write` is invoked afterward without that read-only verb having run
  again
- THEN `write` performs its own assembly and refuses the same way, rather
  than proceeding on the assumption that only the read-only verb needs to
  check

#### Scenario: An undecided binding reads fine and refuses only at `write`

- GIVEN a block whose bindable requirement's source root is measured but
  carries no `document` half at all — `source-section-binding` reports it
  `undecided`, not broken
- WHEN a read-only verb assembles the corpus, and separately `write` is
  invoked for that exact block
- THEN the read-only verb's assembly raises nothing, and `write` refuses
  `SECTION_BINDING_ABSENT` naming the block and the fact id, before the
  draft stage runs

#### Scenario: `write` refuses duplicate ingested identities across evidence folders

- GIVEN more than one folder under `guidance/` classed `'evidence'`
  contains an ingested paper with the same document identity
- WHEN `write` is invoked for any block, whether or not it names a
  `dataset` binding
- THEN it refuses `EVIDENCE_ROOT_AMBIGUOUS` naming the duplicate identity
  and the folders containing it, before the draft stage runs, since
  `Corpus.source_roots` is computed for every root unconditionally as part
  of the same corpus assembly
- AND distinct identities across evidence folders are aggregated, not refused

#### Scenario: Mutation — wiring the guard only into the read-only verb is caught

- GIVEN the guard implemented so that only the read-only verb calls the
  section-existence check and `write` skips it
- WHEN a test drafts a block whose binding is broken by directly invoking
  `write`, never the read-only verb
- THEN the test fails, since `write` would proceed and draft the block
  instead of refusing

### Requirement: `SECTION_BINDING_ABSENT` Names Its Own Next Action

`SECTION_BINDING_ABSENT`'s own refusal detail MUST name the block, the
fact, and the source root, AND — read from disk at the moment of refusal,
never cached or hand-listed — every lineage that root currently carries,
each one's own current revision (or, for an identity-resolved root, its
own paper), and the section titles that revision actually holds right
now. It MUST also name the exact recording-verb invocation (naming this
refusal's own block and fact) that answers it. A person reading the
refusal MUST be able to answer it without opening anything else.

#### Scenario: The refusal names the block, fact, root and disk-derived candidates

- GIVEN a bindable, measured entry with no binding, under a root carrying
  more than one revision of the same lineage
- WHEN `write` refuses `SECTION_BINDING_ABSENT` for it
- THEN the detail names the block, the fact, the root, the CURRENT
  (highest-ordinal) revision only — never an older one — and every
  section title that revision carries

#### Scenario: Mutation — reverting the detail to a bare message is caught

- GIVEN the refusal detail reverted to name only the block, the fact and
  the root, with no disk-derived candidates
- WHEN a test asserts the detail names a candidate section title read
  from disk
- THEN the test fails, since the bare message carries nothing to answer
  the refusal with
