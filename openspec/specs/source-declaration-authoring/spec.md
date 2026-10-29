# Source Declaration Authoring Specification

## Purpose

A source root's revision-naming rule and a `guidance/` folder's class both
live in a per-directory `.paper-writing.json` marker, and until now neither
had a verb of the skill that writes it — only a reader that refuses when the
file is absent or wrong. This capability adds the writer for both marker
kinds: a validated write against the files actually on disk at the moment of
writing, a seal against an unaware edit stated at exactly its real strength,
a rollback path that never becomes a hand edit, and the position report line
that lets a session with no memory learn where every declarable root and
every `guidance/` folder stands before it hits a refusal.

## Requirements

### Requirement: A Source Root's Revision Rule Is Recorded And Validated Against Disk By Using The Skill

A verb (`mark revisions`) MUST record `<root>/.paper-writing.json`'s
`revisions` grammar. `--root` MUST name a `PROSE`-kind key of
`FACT_SOURCE_ROOT`; otherwise it MUST refuse `SOURCE_ROOT_UNDECLARABLE`,
naming every declarable root and the rejected root's own kind. The declared
prefix and ordinal-digit count MUST be matched, at the moment of writing,
against `sorted(path.glob("*.md"))` under that root; zero matches MUST
refuse `SOURCE_DECLARATION_UNMATCHED`, naming the prefix, the digit count,
and every `*.md` file seen. The written object MUST pass the same shape
validation the reader applies before being written, so the verb can never
produce a marker its own reader would refuse as `MALFORMED_SOURCE_MARKER`.
The verb MUST NOT create the root directory.

#### Scenario: A matching declaration is recorded

- GIVEN `experiments/` holds `field-survey-r07.md` and `field-survey-r08.md`
- WHEN `mark revisions --root experiments --revision-prefix r
  --ordinal-digits 2` is invoked
- THEN it records the marker, reporting both files matched and none
  unmatched

#### Scenario: A declared width matching nothing on disk refuses at write time

- GIVEN the same directory
- WHEN `mark revisions --root experiments --revision-prefix v
  --ordinal-digits 3` is invoked
- THEN it refuses `SOURCE_DECLARATION_UNMATCHED`, naming `v`, `3`, and both
  `*.md` files it saw — refused here, not three steps later under an
  unrelated message

#### Scenario: A non-declarable root refuses by name

- GIVEN `--root` names a root whose kind is `REPOSITORY`, not `PROSE`
- WHEN `mark revisions` is invoked
- THEN it refuses `SOURCE_ROOT_UNDECLARABLE`, naming every declarable root
  and that the rejected root's kind is not `PROSE`

### Requirement: A Guidance Folder's Class Is Recorded And Validated Against Disk By Using The Skill

A verb (`mark class`) MUST record `guidance/<folder>/.paper-writing.json`'s
`class` grammar. `--folder` MUST name a directory enumerated directly under
the resolved `guidance/`; otherwise it MUST refuse `GUIDANCE_FOLDER_ABSENT`,
naming every folder that is there. `--class` MUST be a member of `CLASSES`;
otherwise it MUST refuse `UNKNOWN_GUIDANCE_CLASS` (reused verbatim).
Multiple folders MAY be classed `evidence`; the ingested source root MUST
aggregate their documents. Duplicate ingested document identities across
those folders MUST refuse `EVIDENCE_ROOT_AMBIGUOUS` during source-root
assembly, before binding resolution or drafting. The written object MUST
pass the same shape validation `_classify` applies. The verb MUST NOT create the folder,
and MUST NOT refuse an `evidence` folder that holds zero ingested papers —
that condition is an earlier stage, not a fault, and stays unchanged.

#### Scenario: A folder is classed

- GIVEN `guidance/style-corpus/` exists with no marker
- WHEN `mark class --folder style-corpus --class style-reference` is invoked
- THEN it records the marker and reports class `style-reference`

#### Scenario: Naming an absent folder refuses without creating it

- GIVEN `guidance/` has no folder named `missing-notes`
- WHEN `mark class --folder missing-notes --class evidence` is invoked
- THEN it refuses `GUIDANCE_FOLDER_ABSENT`, naming every folder that exists,
  and no `missing-notes` directory is created

#### Scenario: A second evidence folder is classed without replacing the first

- GIVEN `guidance/prior-papers/` already classed `evidence` and
  `guidance/new-corpus/` exists
- WHEN `mark class --folder new-corpus --class evidence` is invoked
- THEN it records the new evidence marker and preserves the first marker
- AND distinct ingested identities from both folders form one source root

### Requirement: Which Roots And Folders Are Declarable Is Derived, Never Listed

The set of roots `mark revisions` accepts MUST be exactly the `PROSE`-kind
keys of `FACT_SOURCE_ROOT`, computed from that mapping — no engine-side list
of root names. The set of folders `mark class` accepts MUST be exactly the
directories enumerated under the resolved `guidance/` at the moment of the
call — no engine-side list of folder names.

#### Scenario: Mutation — a sixth PROSE root widens declarability with no code change

- GIVEN `FACT_SOURCE_ROOT` extended with a sixth `PROSE`-kind root in a
  fixture
- WHEN `mark revisions --root` is invoked naming that sixth root
- THEN it is accepted as declarable, proving the test is membership in the
  mapping and not a hand-maintained list

### Requirement: A Declaration Is Sealed Against An Unaware Edit, At Exactly Its Real Strength

Both `mark revisions` and `mark class` MUST write a `seal_sha256` key holding
a digest computed over the declaration's own canonical bytes, excluding that
key itself, sorted-keys JSON so the same declaration serializes identically
across runs. The one sentence stating the seal's real strength — that it
detects an unaware edit, is self-consistency and not tamper-proofing, and
that anyone reproducing the convention can hand-edit the file and recompute
a matching seal — MUST appear byte-identically in: the shared module's own
docstring, both `*_HAND_EDITED` refusal details (`source-section-binding`,
`guidance-registry`), `SKILL.md`, and `references/usage.md`. A test MUST
derive the expected text from one constant and assert its presence in all
four surfaces, so weakening the claim anywhere is a red test, never a review
miss.

#### Scenario: The same declaration seals identically across runs

- GIVEN a declaration written twice with identical inputs, on two separate
  invocations
- WHEN each run's seal is computed
- THEN both seals are identical, proving canonicalization is stable

#### Scenario: Mutation — weakening the strength statement is caught

- GIVEN the shared strength constant mutated to drop "not tamper-proofing"
- WHEN the four-surface strength test runs
- THEN it fails red

### Requirement: Re-Recording Always Succeeds; There Is No Stuck State

`mark revisions` and `mark class` MUST always write when their own
validation passes, regardless of whether a marker already exists at that
path, whether it is currently sealed, or whether its existing seal matches.
Neither verb MAY require a `--reopen` or a `--adopt` flag, and neither verb
MAY read the previous marker's seal as a precondition to writing a new one.

#### Scenario: A sealed marker is freely re-recorded

- GIVEN a root already carrying a sealed, valid marker
- WHEN `mark revisions` is invoked again for that root with new values that
  match files on disk
- THEN it overwrites the marker with the new, freshly sealed declaration and
  no flag is required

#### Scenario: A hand-edited marker is freely re-recorded, clearing the defect

- GIVEN a sealed marker whose bytes were edited outside the skill
- WHEN `mark revisions` is invoked for that same root with values matching
  files on disk
- THEN it overwrites the marker with a new, correctly sealed declaration —
  running the verb is the only exit, since there is no `--adopt`

### Requirement: Absence Is A Reported State; A Broken Seal Refuses Where The Marker Is Read

A directory's declaration state is one of four values: `undeclared` (no
marker file), `declared-unsealed` (a valid marker with no `seal_sha256`
key), `declared-sealed` (a valid marker whose recorded seal matches the
computed one), or `n/a` (the directory's kind carries no revisions rule at
all). The seal itself MUST be verified inside the same reader every gating
verb already reaches (`read_revisions_marker`, `_classify`), never inside a
read-only reporting verb alone. A marker whose seal is present but does not
match MUST refuse through that reader — `SOURCE_DECLARATION_HAND_EDITED` or
`GUIDANCE_DECLARATION_HAND_EDITED` — reachable through a gating verb, not
only through the position report.

#### Scenario: An unsealed marker on an existing checkout reports, not refuses

- GIVEN a marker written before this change landed, carrying no
  `seal_sha256` key
- WHEN its declaration state is computed
- THEN it reports `declared-unsealed`, with no refusal

#### Scenario: Mutation — the seal check is reachable through a gating verb, not only the report

- GIVEN the seal-comparison line inside `read_revisions_marker` replaced
  with a constant `True`
- WHEN a test drives a hand-edited sealed marker through `write` (a gating
  verb), not through the position report alone
- THEN that test fails red, proving the guard is wired to something that
  actually gates drafting

### Requirement: The Position Report Names Every Declarable Root's And Every Guidance Folder's Declaration State

The read-only position verb's report MUST carry a `sourceRoots` key, one
entry per root known to `FACT_SOURCE_ROOT`, each naming that root's existing
measurement state plus its declaration state from the four-value vocabulary
above; a root whose kind is not `PROSE` MUST report `n/a` for declaration,
by kind, never by name. The report's existing `guidance` entries MUST widen
from a bare class string to an object naming both the class and the
declaration state. This corrects the archived predecessor's `tasks.md` item
2.14, which claimed `Corpus.source_roots` was already "echoed by every
corpus-reading verb" while, measured by running `plan`, `phases`, and
`contract`, none of the three rendered it: this requirement is met only by
running the position verb and reading its output, never by asserting a field
exists.

#### Scenario: An undeclared root is named, not hidden

- GIVEN a `PROSE`-kind root with no marker
- WHEN the position verb runs
- THEN its `sourceRoots` entry names that root `declaration: "undeclared"`

#### Scenario: A non-PROSE root reports n/a by kind

- GIVEN a root whose kind is `REPOSITORY` or `INGESTED`
- WHEN the position verb runs
- THEN its entry reports `declaration: "n/a"`, and no root name is matched
  by literal to produce that value

#### Scenario: guidance's report widens without dropping its class

- GIVEN a `guidance/` folder classed `style-reference` with a sealed marker
- WHEN the position verb runs
- THEN that folder's entry names both `class: "style-reference"` and
  `declaration: "declared-sealed"`

#### Scenario: A malformed marker still refuses through the position verb

- GIVEN a marker under a declarable root that is not valid JSON
- WHEN the position verb runs
- THEN it refuses `MALFORMED_SOURCE_MARKER`, exactly as any other reader of
  that marker would

### Requirement: Rollback Writes The Pre-Change Grammar, Never An Editor

`mark revisions --unsealed` and `mark class --unsealed` MUST write the
declaration in the pre-change grammar, with the `seal_sha256` key absent,
otherwise passing the same write-time validation as a sealed write. This is
the documented rollback path: run the verb once per declared root or folder,
while the code that reads `--unsealed` still exists, before reverting the
branch. Neither verb's docstring MAY claim this removes anything a
determined editor could not already remove by hand-editing the file.

#### Scenario: `--unsealed` produces a marker an older reader accepts

- GIVEN a root declared with `mark revisions --root experiments
  --revision-prefix r --ordinal-digits 2 --unsealed`
- WHEN the written marker is inspected
- THEN it carries no `seal_sha256` key, and its shape matches the grammar an
  unmodified pre-change reader accepts

## Acceptance Criteria

- Both marker kinds gain a writer reachable only by using the skill; no
  file-writing tool is needed to answer either refusal this capability
  answers.
- Write-time validation runs against the files or folders actually on disk
  at the moment of writing, proven by an executed mutation per refusal code.
- The seal is verified inside the reader every gating verb already reaches,
  proven by a mutation driven through a gating verb, never through the
  position report alone.
- The seal's real strength — self-consistency, not tamper-proofing — is one
  constant, asserted present in the module docstring, both `*_HAND_EDITED`
  refusal details, `SKILL.md`, and `references/usage.md` by one test.
- The position report names every declarable root's and every guidance
  folder's declaration state, proven by running the verb and reading its
  output.
- Declarability is derived from `FACT_SOURCE_ROOT` and the `guidance/`
  directory listing; a sixth root or an added folder is reported with no
  engine edit.
