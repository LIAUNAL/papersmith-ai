# qualitative

The qualitative core of the qualitative-participatory line (decisions K2-K5
of `odd/tasks/paper-type-lines.md`): the de-identified transcripts and field
notes the operator registers, the codebook versions, the operator's sign-off
of the themes, and the check that every participant quote in the paper is
found verbatim in a registered transcript.

**The assistant never writes or edits a transcript.** The operator collects,
transcribes and de-identifies the material and registers each file with
`--by`; the core binds it by its sha256 and character count and only reads
it. The assistant may propose codes and themes in files; only the operator
records a codebook version or signs the themes off. No verb and no reader
outputs a transcript's text.

## Files

| File | Holds | Written by |
| --- | --- | --- |
| `study/transcripts.json` | every transcript registration, history kept (gate G-TRANSCRIPTS) | `transcripts add --by` |
| `study/codebook.json` | every codebook version, history kept | `codebook record --by` |
| `study/themes.json` | every sign-off of the themes, history kept (gate G-ANALYSIS) | `themes signoff --by` |

A transcript registration:

```json
{"by": "Ana Ruiz", "at": "2026-11-24T10:00:00Z", "action": "add", "participant": "P01",
 "file": "data/interviews/p01.txt", "kind": "interview", "sha256": "…", "characters": 18342,
 "consent": "written consent, form C-12", "deidentified": "names and places replaced by codes",
 "note": null}
```

`kind` is `interview` (default), `focus-group`, `field-note` or `document`.
The participant is a code (letters, digits, `.`, `_`, `-`; at most 40),
never a name. One file may hold several participants (a focus group): each
code is registered once per file. A changed file is registered again with
`--replace` (`action: "replace"`); the latest entry of each (participant,
file) is the registration.

A codebook version is `{by, at, file, sha256, note}`; its version number is
its position in the history. A sign-off is `{by, at, file, sha256, codebook:
{version, file, sha256}, transcripts: [{participant, file, sha256}], note}`:
the themes file, the codebook version it rests on and every registered
transcript at the time.

## Commands

```
python skills/_core/qualitative/qual_cli.py transcripts add --file <path> --participant <code> \
    --consent "<how consent was given>" --deidentified "<how it was de-identified>" --by <operator> \
    [--kind interview|focus-group|field-note|document] [--note <text>] [--replace] --root .
python skills/_core/qualitative/qual_cli.py transcripts status --root .
python skills/_core/qualitative/qual_cli.py codebook record --file <codebook> --by <operator> [--note] --root .
python skills/_core/qualitative/qual_cli.py codebook status --root .
python skills/_core/qualitative/qual_cli.py themes signoff --file <themes> --by <operator> [--note] --root .
python skills/_core/qualitative/qual_cli.py themes status --root .
python skills/_core/qualitative/qual_cli.py quotes check [--paper paper] --root .
python skills/_core/qualitative/qual_cli.py status --root .
```

`--root` goes before or after the action. Each call prints one JSON object;
a refusal is `{"ok": false, "error": <CODE>, "message": …}` with exit 1, a
usage error exit 2. Codes: `USAGE`, `APPROVER_MISSING`, `TEXT_INVALID`,
`FIELD_MISSING`, `PARTICIPANT_INVALID`, `CONSENT_MISSING`,
`DEIDENTIFICATION_MISSING`, `FILE_OUTSIDE`, `FILE_MISSING`,
`FILE_UNREADABLE`, `FILE_EMPTY`, `TRANSCRIPT_NOT_TEXT` (not UTF-8),
`TRANSCRIPT_DUPLICATE`, `TRANSCRIPT_NOT_REGISTERED` (`--replace` of nothing),
`RECORD_UNCHANGED`, `TRANSCRIPTS_CORRUPT`, `TRANSCRIPTS_ABSENT`,
`TRANSCRIPTS_STALE`, `CODEBOOK_CORRUPT`, `CODEBOOK_NOT_RECORDED`,
`CODEBOOK_STALE`, `THEMES_CORRUPT`, `PAPER_OUTSIDE`, `PAPER_MISSING`,
`QUOTE_NOT_FOUND`, `INTERNAL_ERROR`.

Every path stays in the workspace: an absolute path outside it, a path that
traverses out or a link pointing out is refused (`FILE_OUTSIDE`) and, when
hand-edited into a record, reads as `file-outside` and is never followed or
hashed.

## Gates and staleness

- **G-TRANSCRIPTS** passes when at least one transcript is registered and
  every registered file still holds the bytes it was registered with. A
  registration is `stale` with `file-changed`, `file-missing`,
  `file-unreadable` or `file-outside`.
- A codebook version is `stale` when its file changed (same reasons).
- **G-ANALYSIS** passes while the latest sign-off is current. It refuses
  until a codebook version is recorded and current and every registered
  transcript is current; it goes stale with `themes-file-changed` (or
  `-missing`, `-unreadable`, `-outside`), `codebook-changed` (another version
  recorded), `codebook-stale` (the codebook file changed),
  `transcript-changed` (a signed transcript changed or was replaced) or
  `transcript-added` (a transcript registered since). The operator signs
  the themes off again.

## Verbatim quotes

A participant quote in the paper's `.tex` sources is written

```latex
\pquote{P01}{the co-op helped us more than the ministry did}
```

defined in the preamble, for example, as

```latex
\newcommand{\pquote}[2]{``#2''~(#1)}
```

The text may span lines; a `%` comment hides a quote. `quotes check` scans every `.tex` file under the
paper directory except `translations/` and checks that each quote occurs in a
registered, current transcript of its participant after normalising only
whitespace (runs of blanks and line breaks, `~`, `\ `), quote ligatures
(double and single TeX quotes and the typographic quotes, read as `"` and
`'`) and the LaTeX escapes of
special characters (`\% \& \# \$ \_ \{ \}`). Case, punctuation, spelling and
word order are compared as they are, so a polished or invented quote fails;
an omission (`[…]`) is written as two quotes. A failure names the file, the
line where the quote starts, the participant, the reason (`not-found`,
`participant-not-registered`, `transcript-stale`, `quote-empty`,
`quote-malformed`) and the paper's own words, never the transcript around
them; any failure exits 1 with `QUOTE_NOT_FOUND`.

`paper_cli.py verify` runs the same check when the workspace has
`study/transcripts.json` (and only then, so every other line verifies as
before): the report gains a `qualitative` key with one `quote-not-verbatim`
entry (`severity: error`); a `fail` makes `clean` false, and an unreadable
register is `unmeasured` (`TRANSCRIPTS_CORRUPT`).

## Readers

`records.py` is importable and side-effect free (no write, no directory
created, no model call, never raises on a corrupt record) for the board and
the Study tab: `transcripts_state(root)` (state `absent`, `current`, `stale`
or `corrupt`; `passed` is G-TRANSCRIPTS; each transcript with its code, file,
kind, character count, consent and de-identification statements, never its
text; counts by kind and participant), `codebook_state(root)`,
`themes_state(root)` (`passed` is G-ANALYSIS, with `reasons`),
`qualitative_status(root)` (all three with their warnings) and
`check_quotes(root, paper_dir)`.

## Consensus rounds

`consensus_cli.py` records a consensus study (Delphi, nominal group, RAND/UCLA)
and computes its results from the operator's files. The operator registers each
panel member by an anonymised code with their expertise (`panel add --by`);
records the consensus rule against the approved study protocol (`plan record
--rounds --threshold --scale --agree-from --by`, stale after a protocol
amendment; a change needs `--reason`); and registers each round's response file
(`member,item,rating[,comment]`) in order (`round record --round k --file --by`).
`round status` gives per item n, percent agreement (ratings >= agree-from),
median and IQR (Hyndman-Fan type 7), consensus (percent >= threshold) and the
change from the previous round. Gate G-ROUNDS passes when the plan is current
and every planned round is recorded and current. `micmac compute --file --by`
reads the operator's square influence matrix (0-3 or P; P counts as
`--p-value`, 4 by default; zero diagonal) and records direct and indirect
influence and dependence (row and column sums of M and M^k, k raised until the
rankings are stable, at most 10) and each variable's quadrant by the means.
MACTOR and scenarios stay narrative. The assistant never enters or edits a
rating, and no output carries a comment.
