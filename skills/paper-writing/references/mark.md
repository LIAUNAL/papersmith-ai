## Recording a declaration: `mark`

One verb, `mark`, with two sub-modes — `revisions` and `class` — from
`the-skill-writes-the-declaration-it-demands`. Both write the SAME per-
directory `.paper-writing.json` file name, validated against the real files
on disk at the moment of writing, sealed the same way, with the same
rollback mode. They keep disjoint key sets (`revisions` for a source root,
`class` for a `guidance/` folder) and their own kind-specific refusals —
this is one subject (a directory's own declaration), not two.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py mark revisions \
    --root experiments --revision-prefix r --ordinal-digits 2
.venv/bin/python skills/paper-writing/scripts/paper_cli.py mark class \
    --folder style-corpus --class style-reference
```

The study protocol revisions take the same marker as `experiments/`:
`mark revisions --root protocol --revision-prefix v --ordinal-digits 2`
(names `protocol/study-protocol-<slug>-vNN.md`, the lineage being
`study-protocol-<slug>`). `study/flow.json` is a `STRUCTURED` root, one JSON
record its own module writes and hashes: never prose, so it takes no marker
(`SOURCE_ROOT_UNDECLARABLE` names its kind) and is reported `unmeasured` for
section binding.

| Verb | What it does | Refuses |
| --- | --- | --- |
| `mark revisions --root <name> --revision-prefix <prefix> --ordinal-digits <n> [--unsealed]` | Records `<root>/.paper-writing.json`'s `revisions` grammar, matched against `sorted(path.glob("*.md"))` at the moment of writing, sealed by default | `SOURCE_ROOT_UNDECLARABLE`, `MALFORMED_SOURCE_MARKER`, `SOURCE_DECLARATION_UNMATCHED` |
| `mark class --folder <name> --class <value> [--guidance <dir>] [--unsealed]` | Records `guidance/<folder>/.paper-writing.json`'s `class` grammar, checked against the folders actually enumerated under `guidance/` at the moment of writing, sealed by default; multiple evidence folders are accepted | `GUIDANCE_FOLDER_ABSENT`, `UNKNOWN_GUIDANCE_CLASS`, `MALFORMED_GUIDANCE_MARKER` |

**Neither verb creates the directory or folder it names, and no operator
string is ever joined onto a path.** `--root` is matched against the
derived declarable-root map and `--folder` against `sorted(guidance_dir.
iterdir())`; the write target always comes from the matched entry, never
from string concatenation. `--root` MUST name a `PROSE`-kind key of
`FACT_SOURCE_ROOT` — otherwise `SOURCE_ROOT_UNDECLARABLE`, naming every
declarable root and the rejected root's own kind. `--folder` MUST name a
directory directly under the resolved `guidance/` — otherwise
`GUIDANCE_FOLDER_ABSENT`, naming every folder that is there.

**The loop this verb closes — a refusal now names a command, not just a
wall.** Two independent gating verbs raise the refusal `mark` answers:

```
write / bind refuses SOURCE_REVISIONS_UNDECLARED
  │  names the root, the marker filename it is missing, every *.md file
  │  currently under it, and the exact `mark revisions` invocation to run
  ▼
mark revisions --root <name> --revision-prefix <prefix> --ordinal-digits <n>
  │  matches the declared prefix/width against disk RIGHT NOW; zero
  │  matches refuses SOURCE_DECLARATION_UNMATCHED instead of writing
  ▼
write / bind proceeds
```

```
validate --source-md refuses SOURCE_NOT_EVIDENCE (folder unclassified)
  ▼
mark class --folder <name> --class evidence
  ▼
validate --source-md proceeds
```

**Re-recording always succeeds — there is no `--reopen`, no `--adopt`, and
no stuck state.** Both `mark` sub-modes always write when their own
write-time validation passes, whether or not a marker already exists at
that path and whatever its existing seal says. A hand-edited marker is
cleared by running `mark` again with values matching the files actually on
disk, never by hand-editing the file — running the verb IS the only exit,
because there is no `--adopt`.

**The seal, and exactly how strong it is.** Both sub-modes write a
`seal_sha256` key by default — a digest over the declaration's own
canonical bytes (sorted-keys JSON, so the identical declaration serializes
identically across runs), excluding that key itself. The seal is verified
inside the same reader every gating verb already reaches
(`read_revisions_marker`, `_classify`) — never inside `plan` alone — so a
hand edit to a sealed marker's bytes refuses `SOURCE_DECLARATION_HAND_EDITED`
or `GUIDANCE_DECLARATION_HAND_EDITED` the next time ANY gating verb reads
it, not only when `plan` happens to be the one asking.

> This seal detects an unaware edit. It is self-consistency, not tamper-proofing: the convention has no secret, so anyone who reproduces it can edit the file and recompute a matching seal.

That is the seal's entire claim — no more. It stops a declaration from
silently drifting out of sync with a hand-typed edit nobody meant to make;
it does not stop a determined edit, because the convention that computes it
is public, reproducible, and lives in this very file.

**`--unsealed` is the rollback path, and only that.** Both sub-modes accept
`--unsealed`, which writes the declaration in the pre-seal grammar with the
`seal_sha256` key entirely absent — the exact shape an unmodified older
reader (one that predates this capability) still accepts. It is not a
weaker everyday mode: run it once per already-declared root or folder,
while the code that still understands `--unsealed` is present, immediately
before reverting past this capability — otherwise a revert would leave
every marker this skill sealed refused as malformed (`MALFORMED_SOURCE_
MARKER`/`MALFORMED_GUIDANCE_MARKER`) by the older reader, unreadable rather
than merely unsealed. `--unsealed` removes nothing a determined editor
could not already remove by hand-editing the file — it exists only to make
the rollback a command instead of a hand edit.

### Decision Gates (mark)

| Situation | Action |
| --- | --- |
| `write`/`bind` refuses `SOURCE_REVISIONS_UNDECLARED` | Run the exact `mark revisions` invocation the refusal names — it already reads the root's current `*.md` files for you |
| `mark revisions` refuses `SOURCE_ROOT_UNDECLARABLE` | `--root` names a root whose kind is not `PROSE` — pick one of the roots the refusal lists as declarable |
| `mark revisions` refuses `SOURCE_DECLARATION_UNMATCHED` | The prefix/digit-width pair matches zero `*.md` files under the root right now — the refusal lists every file it saw; fix the prefix/width or check the root |
| `validate --source-md` refuses `SOURCE_NOT_EVIDENCE` on a `guidance/` folder | Run `mark class --folder <name> --class evidence` (only if the folder truly holds evidence, never to silence the refusal) |
| `mark class` refuses `GUIDANCE_FOLDER_ABSENT` | `--folder` names a folder that does not exist directly under `guidance/` — the refusal lists every folder that is there; `mark` never creates one |
| A corpus-reading verb refuses `EVIDENCE_ROOT_AMBIGUOUS` | The same ingested paper id occurs under multiple evidence folders; make document identities unique before binding. Several evidence folders with distinct papers are accepted |
| Either `mark` refuses `MALFORMED_SOURCE_MARKER` / `MALFORMED_GUIDANCE_MARKER` | The marker file on disk was hand-edited into an invalid shape — re-run `mark` with correct values; it always overwrites |
| `read_revisions_marker`/`_classify` refuses `SOURCE_DECLARATION_HAND_EDITED` / `GUIDANCE_DECLARATION_HAND_EDITED` | A sealed marker's bytes were hand-edited after sealing — re-run `mark` for that root/folder; there is no `--adopt` |
| About to revert past this capability | Run `mark ... --unsealed` once per already-sealed root/folder BEFORE reverting, or the older reader will refuse every sealed marker as malformed |
