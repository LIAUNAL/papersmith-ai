# empirical

The operator records of an empirical study: the approval of its protocol
(gate G-STUDY-PROTOCOL), its ethics approval and its registration. Every one
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

## Readers for other modules

`records.py` holds side-effect-free readers (no write, no directory created):

| Function | Returns |
| --- | --- |
| `protocol_state(root)` | the `protocol status` object |
| `gate_state(root, "ethics" \| "registration")` | `None` when never recorded, else the latest entry with `state`, `current`, `records` and `warnings` (or `{"state": "corrupt"}`) |
| `study_status(root)` | the `status` object without `ok` |
| `require_current_lock(root)` | the lock, or raises `StudyError` (`PROTOCOL_NOT_APPROVED`, `PROTOCOL_LOCK_CORRUPT`, `PROTOCOL_CHANGED`) |
| `latest_revision(root)`, `managed_revisions(root)`, `read_lock(root)` | the building blocks above |
