# empirical

The operator records of an empirical study: the approval of its protocol
(gate G-STUDY-PROTOCOL), its ethics approval and its registration; and the
labelled log of every analysis run. Every one
of them is the operator's act, named with `--by`; an agent never approves,
amends or records any of them on the operator's behalf (decisions D5 and D6
of `odd/tasks/paper-type-lines.md`).

The protocol is the managed revision `protocol/study-protocol-<slug>-vNN.md`
that [`study-protocol-deliberation`](../../study-protocol-deliberation/SKILL.md)
publishes. This module reads none of its fields: the lock pins the bytes of a
revision by sha256 and names it. A reader that needs the outcomes calls that
skill's single parser, `protocol-fields.ts`.

## Files

| File | Holds |
| --- | --- |
| `study/protocol.lock.json` | the approved revision, its sha256, who approved it and when, and every amendment |
| `study/ethics.json` | the history of ethics records, each bound to the lock's sha256 |
| `study/registration.json` | the history of registration records, each bound to the lock's sha256 |

```json
{"schema": 1, "gate": "G-STUDY-PROTOCOL",
 "revision": "protocol/study-protocol-walking-v02.md", "sha256": "<hex>",
 "approved_by": "Ana Ruiz", "approved_at": "2026-03-01T10:00:00Z",
 "amendments": [{"by": "Ana Ruiz", "at": "...", "reason": "widened the age range",
                 "from_revision": "protocol/study-protocol-walking-v01.md", "from_sha256": "<hex>",
                 "revision": "protocol/study-protocol-walking-v02.md", "sha256": "<hex>"}]}
```

`approved_by` and `approved_at` keep the first approval; `revision` and
`sha256` follow the latest amendment.

An ethics entry is `{"by", "at", "status": "approved", "committee", "code",
"date", "consent", "protocol_revision", "protocol_sha256"}` or `{"by", "at",
"status": "not-applicable", "reason", "protocol_revision", "protocol_sha256"}`.

A registration entry is `{"by", "at", "status": "registered", "registry",
"id", "date", "first_enrolment", "retrospective", "protocol_revision",
"protocol_sha256"}` or the `not-applicable` form with `reason` and
`"retrospective": null`. `retrospective` is `true` when the registration date
is after the first-enrolment date (ICMJE asks for registration at or before
the first enrolment), `false` when it is not, and `null` when no
first-enrolment date was given.

## CLI

```bash
python skills/_core/empirical/study_cli.py protocol approve --by "<operator>" [--revision protocol/study-protocol-<slug>-v01.md] --root .
python skills/_core/empirical/study_cli.py protocol amend --by "<operator>" --reason "<why>" [--revision ...] --root .
python skills/_core/empirical/study_cli.py protocol status --root .
python skills/_core/empirical/study_cli.py ethics record --by "<operator>" --committee "<name>" --code "<approval code>" --date YYYY-MM-DD --consent "<route>" --root .
python skills/_core/empirical/study_cli.py ethics record --by "<operator>" --not-applicable --reason "<why>" --root .
python skills/_core/empirical/study_cli.py registration record --by "<operator>" --registry "<name>" --id "<id>" --date YYYY-MM-DD [--first-enrolment YYYY-MM-DD] --root .
python skills/_core/empirical/study_cli.py registration record --by "<operator>" --not-applicable --reason "<why>" --root .
python skills/_core/empirical/study_cli.py status --root .
```

- `protocol approve` locks the latest managed revision (the highest `vNN`
  carrying the engine's managed-artifact marker) or the one `--revision`
  names. It refuses a second approval: a later revision is an amendment.
- `protocol amend` moves the lock to the latest (or named) revision and
  appends the amendment with its reason. It refuses an unchanged protocol and
  a revision older than the locked one; the edited bytes of the locked
  revision itself can be amended.
- `protocol status` answers `state`: `absent`, `current`, `changed` (with
  `reasons`: `revision-edited`, `revision-missing`, `newer-revision`) or
  `corrupt`.
- `ethics record` and `registration record` refuse until the protocol is
  approved and current. Each appends an entry bound to the lock's sha256; an
  identical entry over the same lock is refused. After an amendment the
  entry is stale: a warning (`ETHICS_STALE`, `REGISTRATION_STALE`), never a
  refusal, until the operator records it again.
- `status` reports the three records and every warning: `PROTOCOL_NOT_APPROVED`,
  `PROTOCOL_CHANGED`, `PROTOCOL_LOCK_CORRUPT`, `ETHICS_ABSENT`,
  `REGISTRATION_ABSENT`, `ETHICS_STALE`, `REGISTRATION_STALE`,
  `REGISTRATION_RETROSPECTIVE`, `FIRST_ENROLMENT_UNKNOWN`, `ETHICS_CORRUPT`,
  `REGISTRATION_CORRUPT`.

Every verb prints one JSON object. A refusal prints `{"ok": false, "error":
<CODE>, "message": ...}` and exits 1 (usage errors exit 2): `USAGE`,
`APPROVER_MISSING`, `PROTOCOL_ABSENT`, `REVISION_INVALID`, `REVISION_ABSENT`,
`REVISION_NOT_MANAGED`, `REVISION_AMBIGUOUS`, `REVISION_OLDER`,
`PROTOCOL_ALREADY_APPROVED`, `PROTOCOL_NOT_APPROVED`, `PROTOCOL_LOCK_CORRUPT`,
`PROTOCOL_CHANGED`, `PROTOCOL_UNCHANGED`, `AMENDMENT_REASON_MISSING`,
`FIELD_MISSING`, `FIELDS_CONFLICT`, `REASON_MISSING`, `DATE_INVALID`,
`TEXT_INVALID`, `RECORD_UNCHANGED`, `ETHICS_CORRUPT`, `REGISTRATION_CORRUPT`,
`INTERNAL_ERROR`. Writes are atomic.

## The analysis log

Every analysis of the study is an entry of `analysis/log.jsonl` (decisions
D7 and D8): one JSON object per line, append-only, each line chained to the
one before it by `prev`, the sha256 of that line's bytes. `analysis_cli.py`
is its only writer; it sits beside `study_cli.py` rather than inside it
because it wraps a command (`run ... -- <cmd>`) and writes a different file,
so the operator records' parser and refusal roster stay as they were.

```bash
python skills/_core/empirical/analysis_cli.py run --outcome O1 [--plan primary-model] [--script analysis.R] \
    --input data/cohort.csv --output results/model.csv [--note "<text>"] --root . -- Rscript analysis.R
python skills/_core/empirical/analysis_cli.py record --by "<operator>" --tool "SPSS 29" --outcome O2 \
    --input data/cohort.csv --output spss/glm.spv [--note "<text>"] --root .
python skills/_core/empirical/analysis_cli.py status --root .
```

- `run` hashes, before running, the script (`--script`, or the first
  argument after the program that names a file in the workspace, or the
  program itself when it is one), every `--input` (a registered `datasets`
  file also carries its `qc.json` hash, status and dictionary hash, and
  whether the input still matches the hash QC saw) and the lock's sha256; it
  runs the command in the workspace root, then records the exit code, the
  duration, the sha256 of stdout and stderr (kept under
  `analysis/streams/<sha256>`) and of every `--output` (`null` when the run
  did not write it). It exits 0 once the entry is written, whatever the
  command's exit code; `status` lists the failed runs.
- `record` is the operator's attested entry for an analysis run outside
  smith (SPSS, the R GUI): `--by`, `--tool` and at least one `--output` are
  required, and the entry carries `"attested": true`.
- `status` reports the log (`absent`, `ok`, `corrupt`), the lock, the
  protocol's outcomes and plan entries, the count per label, the failed runs
  and the warnings `PROTOCOL_OUTCOME_NOT_ANALYSED`, `OUTCOME_NOT_IN_PROTOCOL`,
  `OUTCOME_ADDED_AFTER_ANALYSIS` (analysed as exploratory before an amendment
  named it: a HARKing risk to report), `ANALYSIS_LOG_CORRUPT` and
  `PROTOCOL_PARSER_UNAVAILABLE`.

**The label is computed, never passed.** No flag sets it (an unknown or
abbreviated flag is a usage error). `analysis_log.compute_label` gives
`confirmatory` when the lock is current, the outcome is the locked revision's
primary or a secondary outcome and, when `--plan` names an entry, the
protocol plans it (`primary-model`, `covariates`, `missing-data`,
`multiplicity`, each declared with a value other than `none` or `not
applicable`; `primary-model` only for the primary outcome). Anything else is
`exploratory` with its reason: `no-protocol-lock`, `protocol-lock-corrupt`,
`protocol-changed`, `outcome-not-in-protocol`, `plan-entry-not-in-protocol`,
`primary-model-not-for-outcome`. An entry keeps its label: an amendment that
adds an outcome makes only the later runs of it confirmatory. The outcome
ids and the plan are read by the study protocol's single parser
(`skills/study-protocol-deliberation/fields.mjs` over `protocol-fields.ts`,
under `node` 22.18+ from `PATH`); without node a locked study refuses with
`PROTOCOL_PARSER_UNAVAILABLE`, and a study with no lock still logs.

An entry is `{"schema", "seq", "id": "A0001", "kind": "run" | "record", "at",
"attested", "by", "tool", "outcome", "plan", "label", "label_reason": {"code",
"message"}, "protocol": {"state", "revision", "sha256", "amendments"},
"script": {"path", "sha256"}, "inputs": [{"path", "sha256", "dataset"}],
"outputs": [{"path", "sha256"}], "command", "exit_code", "duration_s",
"stdout_sha256", "stderr_sha256", "note", "prev"}`.

Refusals (exit 1; usage exit 2): `USAGE`, `APPROVER_MISSING`,
`FIELD_MISSING`, `OUTCOME_INVALID`, `PLAN_ENTRY_INVALID`, `TEXT_INVALID`,
`PATH_OUTSIDE_WORKSPACE`, `SCRIPT_ABSENT`, `SCRIPT_NOT_FOUND`,
`INPUT_ABSENT`, `OUTPUT_ABSENT`, `OUTPUT_MISSING`, `COMMAND_NOT_FOUND`,
`ANALYSIS_LOG_CORRUPT` (a line that is not an entry, or a broken chain: every
append refuses, before the command runs, until the log is restored),
`PROTOCOL_PARSER_UNAVAILABLE`, `INTERNAL_ERROR`.

`paper_cli.py verify` reads the log and the lock through
`analysis_log.manuscript_inputs(root)` and reports the study checks
(`primary-outcome-switch`, a hard check, and three warnings); see the
paper-writing skill.

## Readers for other modules

`records.py` holds side-effect-free readers (no write, no directory created):

| Function | Returns |
| --- | --- |
| `protocol_state(root)` | the `protocol status` object |
| `gate_state(root, "ethics" \| "registration")` | `None` when never recorded, else the latest entry with `state`, `current`, `records` and `warnings` (or `{"state": "corrupt"}`) |
| `study_status(root)` | the `status` object without `ok` |
| `require_current_lock(root)` | the lock, or raises `StudyError` (`PROTOCOL_NOT_APPROVED`, `PROTOCOL_LOCK_CORRUPT`, `PROTOCOL_CHANGED`) |
| `latest_revision(root)`, `managed_revisions(root)`, `read_lock(root)` | the building blocks above |
| `analysis_log.read_log(root)`, `analysis_log.status(root)` | the log's entries (or `ANALYSIS_LOG_CORRUPT`), the `analysis status` object |
| `analysis_log.manuscript_inputs(root)` | `None` without a study protocol; otherwise the lock, the locked revision parsed, the primary outcome at the approval and after each amendment, and the log per outcome |
