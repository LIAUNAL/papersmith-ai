# participant_flow

The participant flow diagram of an empirical study, drawn from counts the
operator enters. Three templates follow the flow diagram each reporting
guideline recommends:

| Template | Guideline | Stages |
| --- | --- | --- |
| `consort-2025` | CONSORT 2025, parallel-group randomised trial | assessed for eligibility → randomised (excluded, with reasons) → allocated per arm (received / did not receive the intervention, with reasons) → followed up per arm (lost to follow-up, discontinued, with reasons) → analysed per arm (excluded from analysis, with reasons) |
| `strobe` | STROBE, cohort or cross-sectional study | potentially eligible → examined for eligibility → confirmed eligible → included → completed follow-up (optional: omit it for a cross-sectional study) → analysed; each step lists the reasons people left |
| `stard-2015` | STARD 2015, diagnostic accuracy study | potentially eligible → eligible → received the index test → index test positive / negative / inconclusive → per result: received the reference standard (no reference standard, with reasons) and its results (target condition present, absent, inconclusive) |

The counts are the operator's (decision D14 of `odd/tasks/paper-type-lines.md`):
an agent never enters, derives or fills a count, and never signs.

## Files

- `study/flow.json`: the counts, entered by the operator.
- `paper/Figures/participant-flow.svg`: the diagram, drawn only from valid counts.
- `study/flow-signoffs.json`: the operator's sign-offs, each bound to a hash.

## `study/flow.json`

```json
{
  "schema": 1,
  "template": "consort-2025",
  "branches": ["Intervention", "Control"],
  "stages": {
    "assessed": {"n": 120},
    "randomised": {"n": 100, "excluded": [{"reason": "Declined to participate", "n": 20}]},
    "allocated": {"branches": {"Intervention": {"n": 50, "not_received": []},
                               "Control": {"n": 50, "not_received": []}}},
    "follow_up": {"branches": {"Intervention": {"n": 48, "lost": [{"reason": "Moved away", "n": 2}],
                                                "discontinued": []},
                               "Control": {"n": 50, "lost": [], "discontinued": []}}},
    "analysed": {"basis": "follow_up",
                 "branches": {"Intervention": {"n": 48, "excluded": []},
                              "Control": {"n": 50, "excluded": []}}}
  }
}
```

- `branches` (CONSORT only): the arms, 2 to 6 distinct names chosen by the
  operator; `template --arm` refuses other names (`BRANCHES_INVALID`,
  `TEXT_INVALID`) before printing or writing anything. STARD's branches are fixed (`positive`, `negative`, `inconclusive`).
- A stage holds `n` and its reason groups; a split stage holds
  `{"branches": {<branch>: {...}}}`.
- A reason group is a list of `{"reason": <text>, "n": <count>}`. STARD's
  `outcome` is `{"target_present": n, "target_absent": n, "inconclusive": n}`.
- `basis` (CONSORT `analysed` only): `follow_up` (default) or `allocated` for
  an intention-to-treat analysis that counts everyone allocated.
- Top-level `generated_at`, `updated_at` and `entered_at` are allowed and never
  change the signed state.

## Arithmetic rules (`check`)

| Rule | Problem code |
| --- | --- |
| a stage equals the stage before it (or its `basis`) minus the people who left on the way (`excluded`, `lost`, `no_reference`) | `COUNT_MISMATCH` |
| a stage never holds more people than the stage before it (analysed ≤ followed up) | `EXCEEDS_PREVIOUS_STAGE` |
| the branches of a split stage share the single stage before it: arms sum to the randomised total, index test results to those tested | `BRANCH_SUM_MISMATCH` |
| people reported but kept (did not receive, discontinued) are at most the stage's count | `NOTE_EXCEEDS_COUNT` |
| reference standard results sum to the branch's count | `PARTITION_MISMATCH` |
| every count is a non-negative whole number, entered | `COUNT_INVALID`, `COUNT_MISSING` |
| every reason and arm name is named once, without control characters or other characters XML 1.0 forbids (surrogates, U+FFFE, U+FFFF) | `REASON_MISSING`, `REASON_DUPLICATE`, `TEXT_INVALID` |
| the stages, keys, arms and basis are the template's | `SCHEMA_INVALID`, `TEMPLATE_UNKNOWN`, `BRANCHES_INVALID`, `BRANCH_MISMATCH`, `BASIS_INVALID` |

Each problem is `{"code", "where", "message"}`, `where` being a path such as
`stages.analysed.branches.Control.n`.

## CLI

```bash
python skills/_core/participant_flow/flow_cli.py template consort-2025 --arm Exercise --arm "Usual care" --write --root .
python skills/_core/participant_flow/flow_cli.py check --root .
python skills/_core/participant_flow/flow_cli.py render --root .
python skills/_core/participant_flow/flow_cli.py signoff --by "<operator>" --note "counts from the enrolment log" --root .
python skills/_core/participant_flow/flow_cli.py status --root .
```

- `template <id>` prints an empty flow (every count `null`); `--write` saves it
  to `study/flow.json`, never over an existing file.
- `check` answers `valid` and the list of `problems`.
- `render` writes the SVG; it refuses invalid counts.
- `signoff` records the operator, the time, the note and the sha256 of the
  counts together with the figure. It refuses invalid counts, a missing figure,
  a figure that does not show the current counts and an unchanged state.
- `status` reports `flow` (`absent`, `invalid`, `valid`), `figure` (`absent`,
  `current`, `stale`) and the latest sign-off with `current`. Editing a count
  makes the figure and the sign-off stale until the operator renders and signs
  again; so does editing the figure by hand.

Every verb prints one JSON object. A refusal prints `{"ok": false, "error":
<CODE>, "message": ...}` and exits 1 (usage errors exit 2): `USAGE`,
`TEMPLATE_UNKNOWN`, `ARMS_NOT_APPLICABLE`, `FLOW_EXISTS`, `FLOW_ABSENT`,
`FLOW_UNREADABLE`, `FLOW_INVALID` (with `problems`), `FIGURE_ABSENT`,
`FIGURE_STALE`, `OPERATOR_ABSENT`, `SIGNOFF_UNCHANGED`, `SIGNOFFS_CORRUPT`.

## The diagram

Deterministic SVG with no dependencies: the same counts give the same bytes.
Black on white, 11 px text at the smallest, stage bands down the left edge,
single stages in a centre column with their exclusions in a side box, split
stages in one column per branch. Operator text is escaped and wrapped; a
count `(n = 12)` is never split across lines.
