## The safety net has no git behind it — three layers, read for what each alone catches

`paper/*` is gitignored except `.gitkeep` (`paper-scaffold` writes it), the
same policy this repository already applies to `proposals/` and
`experiments/`. `main.tex` is never tracked, so nothing below assumes a
commit history could recover a bad write — none exists.

1. **The byte-identity invariant**, checked on candidate bytes in memory
   before any write. Primary and load-bearing, not a supplement to a deeper
   history that does not exist — the only layer with no depth limit,
   because refusing to write has no "how many steps back" question. Proven
   by an executed mutation harness (`tests/test_paper_writing.py`,
   `MutationProofTests`), not asserted: a real subprocess patches the
   engine's own source, purges any cached bytecode, and confirms the
   corresponding guard test goes red.
2. **Same-directory temp file + `os.replace`**. Catches an interrupted
   process only: `main.tex` is always fully the pre-write or fully the
   post-write content, never torn. Says nothing about whether the
   post-write content is correct.
3. **A one-deep pre-image** at `paper/.paper-writing/main.tex.prev`. The
   only recovery path once bytes have reached disk — the one case layer 1
   cannot reach, because layer 1 only rejects a region-boundary violation,
   never a correctly-scoped write whose content nobody actually wanted.
   Recovers exactly the state immediately before the most recent write. A
   second successful write overwrites it; anything earlier than one step
   back has no recovery path anywhere in this system.

`BLOCK_HAND_EDITED` sits beside these three, not inside them: it protects a
human's on-disk text from being silently overwritten, which is a different
property from "the write stayed inside its own region."

**Declared gap, narrowed.** The marker digest covers block bodies and, as of
`the-paper-carries-its-own-decisions`, the `declarations`/`provenance`
region bodies too — a hand edit to either region's own bytes refuses
(`DECLARATIONS_HAND_EDITED` / `PROVENANCE_HAND_EDITED`) rather than passing
silently. What remains outside every digest is ordinary prose: text that is
neither inside a block nor inside a region. A hand edit there is still
invisible to every layer above — `status` cannot see it and neither can the
byte-identity invariant, since both compare against the pre-image read in
the same call and carry that edit forward silently. That prose belongs to
the human; this engine never claims it.

## Binary I/O only

Every read and write of `main.tex` is binary, end to end. A universal-
newlines text-mode open would silently flatten every CRLF pair in the file
to LF outside the block being touched — exactly the corruption the
byte-identity invariant exists to catch, and a fixture with real CRLF bytes
(`tests/test_paper_writing.py`, `CRLFTests`) proves it round-trips
untouched.

## What "shape only" means for block ids

`[A-Za-z0-9._-]+`, nothing else. The block-substitution engine (`open`,
`status`, `substitute`) never validates an id against a list of what should
exist, never derives ordering, and never opens anything under `sections/`
itself — that reasoning is entirely the contract reader's, described below,
and the two sides only agree on the shape class, never on meaning. A later
change may join ids with `.` or `-` and the substitution engine needs zero
changes; a `/`-joined id would need a one-character widening of the shape
class there, and nothing more.
