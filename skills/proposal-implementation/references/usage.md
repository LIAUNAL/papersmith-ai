# Proposal Implementation — worked invocations

See [SKILL.md](../SKILL.md) for the contract. Everything below is a real
invocation of `scripts/implementation_cli.py`: standard library only, no keys, no
network. Each command prints one JSON object; exit code `2` means a guard
refused and nothing was touched.

Run the CLI with a **system** interpreter (`python3`), and it must be **3.10 or
newer**. It refuses to run from a forge virtualenv, so it can never hand the forge's
interpreter to a target venv — but the floor is a separate requirement from that
refusal, and it is not enforced: under an older `python3`, `verify` reaches
`remote-execution`'s adapter, which evaluates `tuple[int, int] | None` at import time,
and the command dies with `TypeError: unsupported operand type(s) for |` instead of
refusing. Worse than a crash: `main()` records that exception as an open defect, and an
open defect then refuses `step`, `gate`, `offer`, `close`, `settle`, `apply`, `admit`
and `materialize` until somebody closes it. Check with `python3 --version` before the
first command; this is not the same thing as `env`'s `--python` floor for the TARGET's
venv, which is enforced and refuses `PYTHON_BELOW_FLOOR`.

The launcher sets `IMPLEMENTATION_DOMAIN_PROFILE` to this skill's own
`impl_profile.py` only when the environment does not already carry the
variable, so an explicit fixture profile wins. When the inherited value is
another skill's own `impl_profile.py` (for example `experimental-implementation`'s,
left exported by a shell or an earlier process), the launcher refuses
`IMPLEMENTATION_DOMAIN_PROFILE_SIBLING` with exit `2` before the engine loads,
naming both profiles, instead of reading the other skill's documents and
holder. Unset the variable and run the command again. "Another skill's" is the
skill the profile declares (the skill directory of its `PROFILE["cli"]["path"]`),
so a sibling's profile from a different checkout or workspace is refused as
well, while this skill's own profile is accepted wherever it lives.

If you set `IMPLEMENTATION_DOMAIN_PROFILE` yourself — a fixture profile, or
running the engine without this launcher — it must be an **absolute** path. A
relative one refuses `IMPLEMENTATION_DOMAIN_PROFILE_NOT_ABSOLUTE` before any
command runs, because it would resolve against whatever working directory a
child process happens to have.

`smith implement --action <command>` (the workspace CLI's bridge) runs only
`env`, `name`, `plan`, `apply`, `admit`, `handoff`, `compose`, `probe` and
`verify`; every other command on this page runs through this launcher directly.
Its `--action materialize` is a kept alias of `apply`, not of the `materialize`
documented below.

### Session ids

`position`, `propose`, `gate`, `offer`, `close`, `step`, `settle`, `defect` and
`walk` require `--session <id>` (`adopt --apply` accepts one). The id is yours:
the engine never mints or looks it up, and validates it only where `position`
writes it into the header (below). It is stamped verbatim into
every event the call appends to `<Name>/.implementation/position.jsonl` and, for
`position`, into the position block's header, so a later reader can tell which
working session made each write. Use one id for one working session (a
conversation, a sitting at the terminal) and pass the same id to every write in
it; a new session gets a new id. Write it as one shell-safe token with no
whitespace — for example `2026-10-12-a`, or your agent harness's own session
id — because the commands `offer` publishes (its `launch` and `run-step` actions)
carry it unquoted. `position` refuses an empty, non-ASCII or whitespace-holding
id as `POSITION_SESSION_INVALID` before writing, because the header reads it
back as one ASCII token. It is an attribution, not a credential: `close` uses it
only to recognize a repeat close by the same session over an unmoved position, which
reports `not_open` instead of recording a second close.

## 0. Bind the revision

```bash
node skills/proposal-deliberation/cli.mjs '{ "operation": "STATUS" }'
```

Take `latest` (e.g. `research-concept-r05.md`). That string is what modules
declare in `__provenance__["revision"]` and what `verify --revision` compares
against. Everything downstream is bound to it.

## 1. Land the repository under `implementations/`

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone <url> implementations/<repo>   # existing repository
git init implementations/<repo>                                # new one
```

`implementations/` is gitignored in the forge, so the clone's own `.git` never becomes a
stray gitlink in the forge's index.

On a repository that tracks weights, pin the skip in the clone as well — the
environment variable covers the clone and nothing else, so a later `git reset
--hard` or branch switch starts downloading again:

```bash
git -C implementations/<repo> config --local filter.lfs.smudge "git-lfs smudge --skip -- %f"
git -C implementations/<repo> config --local filter.lfs.process "git-lfs filter-process --skip"
```

Measured: without this, `git reset --hard` on the migration commit hung
downloading blobs; with it, the same reset took 0.2 s.

`GIT_LFS_SKIP_SMUDGE=1` is not optional on a repository that tracks weights.
Measured on a real target: a smudging clone pulled **3.2 GB** of `.pth` blobs
(4.5 GB on disk); skipping it produced the same 47-file inventory in **43 MB**,
with each weight present as a 133-byte pointer. Every command here works on
paths and on `.py` sources, so the pointers are sufficient — and the LFS quota
stays untouched. Fetch real blobs only when the user actually runs a model.

### The name, normalized before the directory exists

The product directory and the Python package are two spellings of one name, and
a hyphen is legal in exactly one of them. `name` answers that before anything is
created, which is the only moment the answer is free:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py name \
  --name "Example-Method"
```

```json
{ "status": "ok", "input": "deep set", "directory": "Deep-Set",
  "package": "Deep_Set" }
```

It is the one command that takes no `--target`: normalizing a name runs before a
repository exists. Show the pair to the user before scaffolding either, because
renaming afterwards is a migration and this is a question.

## 2. The isolated environment

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py env \
  --target implementations/<repo> [--python python3.12]
```

Without `--python` the venv is built from the interpreter running the CLI.
Check `pythonVersion` in the response: the templates declare `requires-python
>= 3.10`, so pass `--python` when the system default is older.

```json
{
  "command": "env",
  "target": "…/implementations/<repo>",
  "status": "created",
  "pythonVersion": "Python 3.12.4",
  "interpreter": "…/implementations/<repo>/.venv/bin/python",
  "pip": "…/implementations/<repo>/.venv/bin/pip",
  "nextCommand": "…/pip install -r …/assets/requirements-dev.txt -r …/requirements.txt",
  "manifests": {
    "rows": [{"name": "requirements.txt", "status": "honoured"}],
    "args": ["-r", "…/requirements.txt"],
    "absentNote": "…"
  },
  "lfs": {"status": "none", "patterns": []},
  "excluded": [".venv/", "*.egg-info/"],
  "note": "Run every target command through this interpreter. Never the forge's."
}
```

Before it builds anything, `env` appends `.venv/` and `*.egg-info/` to the
clone's own `.git/info/exclude` (`excluded` lists what it added; `[]` on a
rerun). Those are the two things `env` brings into the target — the virtualenv
and the metadata the printed `pip install -e .` creates under `src/` — so a
fresh `git init` target is still clean for the `plan` that follows, and no file
of the target's tracked tree changes. Anything else untracked still refuses
`DIRTY_WORKTREE`. The tracked `.gitignore` gets the same entries later, from
`apply` or `materialize --stage scaffold`, so a clone carries them too.

`--torch cpu|gpu` (with optional `--torch-version X`) adds a torch build to
the same invocation and reports it as `torch`: `cpu` appends
`--extra-index-url https://download.pytorch.org/whl/cpu torch==X+cpu` (X from
the flag or the one exact `torch==X` pin a manifest carries, else
`TORCH_VERSION_REQUIRED`), `gpu` appends `torch` or `torch==X` from the
default index, whose Linux build is the CUDA one. Without the flag, `torch` is
`{"variant": null, "args": []}`.

`nextCommand` is one invocation: the forge's own dev requirements first, then
every manifest the target declares and this flow can honour — `-r
requirements.txt`, `-r requirements-dev.txt`, `-e .` when a build descriptor
exists — last. A conda `environment.yml` is named in `manifests.rows` with
`"status": "unhonoured"` and a reason, never silently skipped; a target that
declares nothing gets `"rows": []` and an `absentNote` saying so. Run
`nextCommand` as printed. From here on, every command that touches target
code goes through the returned `interpreter`.

## 3. Plan the migration (read-only)

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py plan \
  --target implementations/<repo> --name Example-Method > /tmp/plan.json
```

```json
{
  "command": "plan",
  "target": "…/implementations/<repo>",
  "name": "Example-Method",
  "status": "drift",
  "renames": [],
  "referenceUpdates": [],
  "reorganization": {
    "decisionCount": 2,
    "breakdown": {"moves": 2, "renames": 0, "referenceUpdates": 0},
    "carriedFiles": 2, "limit": 15, "scale": "reviewable"
  },
  "createDirs": ["Example-Method/Notebooks", "Example-Method/Results", "Example-Method/Models", "src/Example_Method", "tests"],
  "moves": [
    { "from": "analysis.ipynb", "to": "Example-Method/Notebooks/analysis.ipynb", "reason": "notebook" },
    { "from": "utils.py", "to": "src/legacy/utils.py",
      "reason": "pre-existing implementation moves into its own package under src/" }
  ],
  "conflicts": [],
  "unclassified": ["notes.docx"],
  "scaffoldFiles": [".gitignore (.venv/, __pycache__/, .ipynb_checkpoints/, .implementation/)",
                    "pyproject.toml [tool.pytest.ini_options] pythonpath",
                    "src/Example_Method/__init__.py",
                    "src/Example_Method/report_digest.py",
                    "tests/test_smoke.py", "tests/findings.py",
                    "tests/conftest.py", "tests/sweep.py",
                    "tests/admissibility.py",
                    "tests/test_audit.py", "tests/test_remedies.py",
                    "Example-Method/Notebooks/verification.ipynb"]
}
```

Present `moves` to the user file by file. `unclassified` means no rule covers
those files — ask, never invent a destination. `apply` refuses while the list is
non-empty.

`status` is `compliant` only when there is nothing left to decide: no move, no
rename, no missing directory, no scaffold gap **and** no `conflicts` or
`unclassified`. A tree `apply` is about to refuse is never reported as settled.

`reorganization` sizes the whole plan before anybody reads it file by file:
`decisionCount` is the moves, renames and reference updates added together, its
`breakdown` says which of the three they were, `carriedFiles` counts the files that
travel, and `scale` compares the count against `limit`. Use it to decide whether the
plan is one a person can review in a sitting or one worth splitting; it decides
nothing on its own.

### `renames` beats a pile of moves

When one top-level folder already groups `Notebooks/`, `Results/` or `Models/`
and only its *name* breaks the `<Name>/` ↔ `src/<Name>/` correspondence, the
plan proposes a single directory rename instead of reclassifying its contents:

```json
{
  "renames": [{ "from": "Images", "to": "Example-Method",
                "reason": "product folder has the right shape but the wrong name; renaming preserves every subtree" }],
  "createDirs": ["src/Example_Method", "tests"], "moves": [], "conflicts": [],
  "referenceUpdates": [
    { "file": "src/Example_Method/artifacts.py", "occurrences": 2,
      "kind": "path prefix", "replace": "Images/", "with": "Example-Method/" },
    { "file": "src/Example_Method/artifacts.py", "occurrences": 1,
      "kind": "quoted path segment", "replace": "\"Images\"", "with": "\"Example-Method\"" }
  ]
}
```

Note `createDirs`: with a hyphenated name the product folder is `Example-Method/`
but the package is `src/Example_Method/`, because `import Example-Method` is a syntax
error. The two forms are derived, never asked twice.

### `referenceUpdates` — a rename is half a migration

Renaming or moving a directory leaves every notebook, module and doc that
addresses the old path pointing at nothing. `apply` rewrites them inside the
same commit, mapping the planned pre-rename paths through the rename first.

Mappings come from renames **and** from moves. A move's prefix is derived by
stripping the longest common suffix, so `Alpha/Results/x.csv -> <Name>/Results/x.csv`
yields `Alpha -> <Name>`, while `Results/x.csv -> <Name>/Results/x.csv` yields
`Results -> <Name>/Results`. An ambiguous prefix (two destinations) is reported
rather than rewritten.

Two forms are detected, and the second matters most:

- **path prefix** — `Images/Results/...` in a string, a URL or prose.
- **quoted path segment** — `root / "Images"`. It contains no slash, so the
  prefix pattern cannot see it, yet it is the form that actually breaks at
  runtime. On the real target, this was the single functional break of the
  whole rename.

`anchored` says how the match is made, and the distinction is not cosmetic:

- A **pure rename** (`Images -> <Name>`) matches anywhere, because the new value
  cannot contain the old one. This is what rewrites a Colab URL such as
  `.../blob/main/Images/Notebooks/`.
- A **nesting** mapping (`Results -> <Name>/Results`) is anchored to a path
  boundary. Without that, `Images/Results/` would become
  `Images/<Name>/Results/` — measured, not hypothetical.

`apply` also removes directories left empty by the moves. `git` does not track
directories, so the old parents survive as empty shells and make a vanished
path look like it still exists.

This is not cosmetic. Reclassifying those files individually flattens
`Results/Resnet18/`, `Results/Resnet50/` and `Results/Transformer/` into one
directory — on a real target that meant three different `results.csv` files landing
on the same path. `conflicts` catches both clash kinds (onto an existing file,
and two sources onto one destination) and `apply` refuses, because a cascade of
`git mv` onto one path destroys files silently.

Outside a rename, a file already sitting under a category folder keeps that
category and its subtree whatever its extension says: a `.csv` under `Results/`
is a result, not a dataset.

## 4. Apply, as one separate commit

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py apply \
  --target implementations/<repo> --name Example-Method --plan /tmp/plan.json
```

The plan is recomputed and compared before anything moves: if the repository
changed since approval, it refuses with `PLAN_STALE`. The comparison covers the
`referenceUpdates` too, not only the renames, moves and directories — a commit
that edits nothing but a file's *contents* leaves all three identical, and
without that check `apply` would rewrite a file that was never on the list the
user approved. On success everything lands in one commit — `git revert <commit>`
undoes the whole migration.

### The plan, apply and materialize lifecycle

A plan describes the tree it was taken from. `apply` carries out its renames,
moves and `createDirs` (on a fresh `git init` target, `createDirs` is the whole
plan), so once `apply` has run that plan is `PLAN_STALE` for `materialize` by
design: the gate cannot tell "applied" from "moved by somebody else", and it
must refuse the second. Re-plan once `apply` has run, and pass the new plan to
`materialize`:

```text
env -> plan (A) -> [GATE] apply --plan A -> plan (B) -> materialize --stage scaffold --plan B
```

Plan B normally lists nothing to move (`decisionCount: 0`), so it needs no
second reorganization approval; it is what binds `materialize` to the tree
that `apply` left. When `plan` A was already `compliant` and nothing was
applied, A itself is current and `materialize` takes it.

## Adopt an external folder (survey, then apply)

When the work starts as a folder outside the workspace — prior code, a paper
draft, or both — rather than a repository URL, `adopt` brings it under
`implementations/` in two phases mirroring `plan` → `apply`, with the human
gate between them. No deliberation-engine change and no new engine operation:
the paper leg performs the deliberation skill's own ADOPT file operation
(marker bytes plus rename to `research-concept-r01.md`), and every other step
reuses the existing plan, scaffold and verify machinery.

### Phase 1: survey (read the source, write the copy and the plan)

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py adopt \
  --source /path/to/external-folder --target implementations/<repo> --name Example-Method
```

```json
{
  "command": "adopt", "mode": "survey", "status": "surveyed",
  "source": "/path/to/external-folder",
  "target": "…/implementations/<repo>",
  "name": "Example-Method",
  "sourceTreeHash": "4f43…00",
  "paper": { "candidate": "draft.md", "mode": "adopt-as-v1" },
  "reorganization": { "decisionCount": 1, "scale": "reviewable", "…": "…" },
  "scaffoldGaps": ["…the scaffold destinations on a fresh tree…"],
  "adoptFiles": [],
  "plan": "…/implementations/<repo>/adoption-plan.json",
  "scaleNote": "…",
  "nextCommand": "… adopt --apply --target … --name … --plan …"
}
```

The survey validates before copying: a missing `--source` or a source that
is not a directory refuses `SOURCE_NOT_FOUND`; a target outside
`implementations/` refuses `OUTSIDE_WORKSPACE`; a target that already exists
— or one nested inside the source it would copy — refuses
`DESTINATION_CONFLICT`. The `--name` is normalized through the existing
`name` command first, before any `<Name>`/`<Package>` path is written.

The copy is one way: the source is never moved, never edited, never
git-touched. `.git/` is not carried over — adoption starts its own history
with one survey commit holding the copy and the plan. The survey mutates
nothing else: no reorganization, no scaffold, no paper placement.

Paper drafts are detected, not guessed at: every `*.md` file outside version
control, environments, caches and vendored trees, except `README.md` — a
readme describes the folder, it is never the paper. Zero drafts means
code-only (`"candidate": null`); one is proposed as the v1 base; several
refuse `ADOPT_AMBIGUOUS` before anything is copied, because choosing among
drafts is the decision the gate exists to take.

The plan machinery runs over the copy as it stands: `reorganization` carries
the decision count and scale (`reviewable` or `large`), alongside the moves,
renames, reference updates, conflicts and unclassified files. Prior work
keeps its own package under `src/` and never lands in `src/<Package>/` —
that is `classify`'s own rule, reused unchanged. `scaffoldGaps` names the
scaffold destinations still open. `adoptFiles` names the kit
destinations the copy already holds, each with `kind: "adopted"` and the
degraded guarantee spelled out: **the record names who wrote the bytes, not
that the bytes came from the kit** — adoption records responsibility for
bytes the engine never saw, and must never be read as engine confidence in
them. `sourceTreeHash` binds the approval to the surveyed bytes: anything
the copy gains, loses or changes before the apply refuses `PLAN_STALE`.

The gate between the phases is human-side, and there is no code to override
it: a `scale: "large"` list is presented, never applied blind, and no `--yes`
flag exists to skip the reading.

### Phase 2: apply (revalidate, place the paper, migrate the code)

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py adopt \
  --apply --target implementations/<repo> --name Example-Method \
  --plan implementations/<repo>/adoption-plan.json [--session <id>] [--seed 7]
```

The plan hash is revalidated first: a copy that moved since the survey
refuses `PLAN_STALE`, and a plan written for another target or name refuses
`PLAN_MISMATCH`. Then the paper leg, when the survey proposed a candidate:
the draft is copied into `proposals/` under its own basename — still
unmanaged — `STATUS` confirms that standing, the marker bytes
(`<!-- proposal-workspace:artifact:v1 -->\n`) are prepended and the file is
renamed to `research-concept-r01.md`, and the post-adoption consistency
(managed marker present, the unambiguous latest, no tie) must hold before
anything else runs. A paper leg that fails removes what it placed and
refuses `ADOPT_AMBIGUOUS`, leaving `proposals/` as found; a `proposals/`
that already holds managed revisions refuses the same way, because adopting
an external draft as v1 beside them is a standing no flag can settle.

Then the code leg: the `git mv` migration lands with its reference updates
in one commit, exactly as `apply` performs it; the scaffold stage writes
(`--seed` substitutes `{{SEED}}`, default `7`); each surveyed file is
recorded through the unchanged per-file adopt, which keeps its own refusals
intact — `ALREADY_RECORDED` on a path the receipt already carries,
`NOT_A_KIT_DESTINATION` outside the sealed set (listed under "The sealed set" below), `MATERIALIZE_PATH_ABSENT`
with no bytes on disk. The run closes with the `verify` report, read-only.
The migration commit reverts as one; the scaffold writes and the adoptions
stay uncommitted for review, then commit.

```json
{
  "command": "adopt", "mode": "apply", "status": "applied",
  "paper": { "candidate": "draft.md", "status": "adopted",
             "revision": "research-concept-r01.md",
             "consistency": { "status": "PASS", "latest": "research-concept-r01.md",
                              "multipleActive": false,
                              "sourceClassification": "LATEST",
                              "markerPresent": true } },
  "migration": { "commit": "1cd11…", "moved": 1, "…": "…" },
  "scaffold": { "written": ["…the scaffold destinations…"], "anchors": ["…"] },
  "adopted": [],
  "verify": { "…": "the read-only report" }
}
```

## Materialize the scaffold

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py materialize \
  --target implementations/<repo> --name Example-Method \
  --stage scaffold --plan /tmp/plan.json --seed 7
```

This is the command that fills every scaffold gap — never the agent copying
files by hand. It writes every one of `scaffoldFiles`' file destinations
(`scaffold_destinations(name)`, the one list this call and `plan`/`verify`'s
gap report both read) from `assets/kit/` — `kit/tests/` and `kit/nb/`, with
`src/<Package>/__init__.py` authored directly — merges the two anchors
(`.gitignore`, `pyproject.toml [tool.pytest.ini_options]`) into whatever the
target already has, and records every write in
`<Name>/.implementation/materialization.json`, git-ignored, written last and
atomically after every file has landed. `src/<Package>_Benchmark/__init__.py`
is **not** among these destinations — it is a harness destination, written
only once a comparison is accepted (see "Materialize the harness" below).

The plan gate is the same one `apply` uses: `PLAN_MISMATCH` for a plan
produced elsewhere, `PLAN_STALE` if the repository's structure moved since
approval. `--stage` requires a clean worktree — commit whatever `apply` just
produced first. A destination already present on disk is never a
destination: it is simply excluded from what this call writes, so a target
scaffolded by hand keeps its hand-written files untouched (and unrecorded —
see `UNRECORDED_SCAFFOLD` below). `DESTINATION_CONFLICT` fires only on the
genuine race of a file appearing between that computation and the write.

## Materialize the object scaffolding

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py materialize \
  --target implementations/<repo> --name Example-Method \
  --stage objects --plan /tmp/plan.json --seed 7
```

The three destinations SKILL.md step 9 names: `src/<Package>/module.py`,
`tests/test_invariants.py`, `tests/test_synthetic.py`. The first follows the
approved map rather than the kit's file name. `--module <name>` writes it as
`src/<Package>/<name>.py` (from the same template; sealed in the receipt and
released by `--authored` like the default), refusing `MODULE_NAME_INVALID` for
anything but an importable identifier that is not a keyword, `__init__` or a
kit-owned file such as `report_digest`, and `MODULE_STAGE_MISMATCH` with any
other mode. Without the flag, `module.py` is written only while the package
holds no `.py` file of its own (its `__init__.py` and the kit's seal do not
count); once the map's modules exist under their own names it is not written,
and `verify`'s `structure.objectGaps` stops naming it. A target that already
carries `module.py` keeps verifying unchanged. Same plan/clean-worktree
preflight as `--stage scaffold`, plus one more: it refuses
`OBJECT_MAP_NOT_APPROVED` until `src/<Package>/__init__.py`'s `__implementation__`
carries step 8's `revision`/`premises` — or, on a target scaffolded before this
literal existed and whose old `src/<Package>_Benchmark/__init__.py` still binds
them, `OBJECT_MAP_AT_OLD_HOME`, naming both locations (SKILL.md step 8's
migration procedure). Unlike scaffold, this write is **not** gated on
the result parsing — `writable_at_scaffold_time`'s `ast.parse` check is scoped
to the scaffold stage on purpose. It fills in what it knows: `{{REVISION}}`
(the declaration the gate just read), `{{NAME}}`, and `{{MODULE}}` whenever it
writes the module (the `--module` name, or `module`). The rest
(`{{FUNCTION_NAME}}`, `{{INVARIANT_ID}}`, `{{EXPECTATION}}`, ...) sit inside
Python identifiers that only step 9's own authoring can answer, so this stage
writes them as scaffolding for the agent to author over. Until then the kit's
`conftest.py` collects a test file that does not parse because of them as one
failing item naming the placeholders and the step that answers them, instead
of a collection `SyntaxError`. Author the real module and tests, then run
`materialize --authored <path>` on each of the three so `verify` stops reading
them as drift.

The same call fills `{{REVISION}}`, `{{NAME}}` and `{{MODULE}}` into every
scaffold destination that still carries them **and** is still byte-identical
to what its receipt sealed (typically `tests/test_smoke.py`,
`tests/admissibility.py` and the verification notebook, scaffolded before the
revision was declared), re-sealing each entry with the new bytes; the result
lists them under `filled` (present only when it filled something). A scaffold
file somebody edited, adopted or declared authored is never touched.

## Materialize the harness

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py materialize \
  --target implementations/<repo> --name Example-Method \
  --stage harness --plan /tmp/plan.json
```

The destinations the harness-wiring section names: `src/<Package>_Benchmark/__init__.py`
(the benchmark declaration itself — copied verbatim from `assets/kit/src_benchmark/`
and never populated by this command), `benchmark.py`, `verdict.py`, `probe.ipynb`.
No `--seed`: none of the four carries a `{{SEED}}` token (`probe.ipynb` carries
`{{SEEDS}}` instead, answered later, at probe time, not by this command). No
object-map precondition either — `__init__.py`/`benchmark.py`/`verdict.py` carry
no unresolved token at all and parse the moment they land. `wiring.py` stays out
of this stage entirely: SKILL.md states it is bespoke-authored, never a kit
destination. This is the only stage that ever writes `src/<Package>_Benchmark/`
into a target — the scaffold stage does not, and never runs it merely because a
comparison was declined or an acid test was run instead.

### Declaring authorship, and adopting what was never recorded

Two more modes, both ledger-only — no file write, no plan gate, and
deliberately no clean-worktree requirement, because the file they name is by
definition an uncommitted edit:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py materialize \
  --target implementations/<repo> --name Example-Method \
  --authored src/Example_Method/module.py
```

`--authored <path>` releases the drift seal on one receipt-recorded
destination after the agent has genuinely authored over it — the record's
`writtenSha256` is updated to the new bytes and `kind` becomes `"authored"`.
For a notebook it also records `writtenSourceSha256`, the digest of its cell
types and sources, so running the notebook in place afterwards is not drift;
editing a cell's source is. Executing the kit's own `verification.ipynb` or
`probe.ipynb` needs no `--authored` at all: the stage that wrote them recorded
the same digest.
It refuses `NO_RECEIPT_ENTRY` on a path the engine never wrote in the first
place; that path is adopted, not re-sealed. The release is per-declaration:
a second silent edit after this drifts again.

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py materialize \
  --target implementations/<repo> --name Example-Method \
  --adopt tests/test_smoke.py
```

`--adopt <path>` is the remedy for `UNRECORDED_SCAFFOLD` (see the refusal
table below): a kit destination exists on disk with no receipt entry
explaining it — most commonly because a target was scaffolded before this
command existed. Adoption records the destination's current sha256 with
`kind: "adopted"`, distinguishable forever from `"materialized"`. **This
degrades the guarantee, and says so where an operator reads it**: adoption
records who is responsible for the bytes; it does not verify the bytes came
from the kit. For an adopted destination the guarantee is "the record names
who wrote them," not "the engine owns the bytes." Adopt one path at a time,
deliberately — there is no batch or automatic adopt, because auto-adopting
would record engine confidence in bytes the engine never saw.

#### The sealed set

`--authored` and `--adopt` accept exactly these paths — the scaffold, objects
and harness destination lists, in that order (`all_kit_destinations`). Any
other path refuses `NOT_A_KIT_DESTINATION`, and the refusal lists the paths it
would have accepted. `<Name>` is the product folder (`--name`), `<Package>` its
importable form (hyphens become underscores).

- `src/<Package>/__init__.py` (scaffold)
- `src/<Package>/report_digest.py` (scaffold)
- `tests/test_smoke.py` (scaffold)
- `tests/findings.py` (scaffold)
- `tests/conftest.py` (scaffold)
- `tests/sweep.py` (scaffold)
- `tests/admissibility.py` (scaffold)
- `tests/test_audit.py` (scaffold)
- `tests/test_remedies.py` (scaffold)
- `<Name>/Notebooks/verification.ipynb` (scaffold)
- `src/<Package>/module.py` (objects)
- `tests/test_invariants.py` (objects)
- `tests/test_synthetic.py` (objects)
- `src/<Package>_Benchmark/__init__.py` (harness)
- `src/<Package>_Benchmark/benchmark.py` (harness)
- `src/<Package>_Benchmark/verdict.py` (harness)
- `<Name>/Notebooks/probe.ipynb` (harness)

`--authored` also accepts a file `materialize --stage objects --module <stem>`
wrote under its own name (`src/<Package>/<stem>.py`), because its receipt entry
already names it; `--adopt` does not, since such a file was never unrecorded.
`.gitignore` and `pyproject.toml` are merge anchors, not destinations, and
`src/<Package>_Benchmark/wiring.py` is authored by hand and never sealed: none
of the three is accepted by either mode.

Substitute these placeholders. Every one of them occurs in some template, and
no template carries any other. `materialize --stage scaffold` substitutes
`{{PKG}}`, `{{SEED}}` and `{{NAME}}` itself, and `{{REVISION}}` when it is
already known: the target's `__implementation__` declares one, or the approved
plan was taken with `plan --revision` (its `boundTo`). It never guesses one; an
unknown revision stays a token, and the kit's `admissibility.py` and
`test_smoke.py` then fail saying so, until `--stage objects` fills it in after
step 8. Every other token is left standing on purpose, and the stage refuses
`STAGE_CANNOT_ANSWER` if a scaffold-stage `.py` destination still fails to
parse after substitution. The receipt records each entry's substitutions.

`Answered at` says when the value exists, which is not the same as when the file
carrying the token is written. `tests/test_smoke.py` is placed by the scaffold and
carries `{{MODULE}}`, which only step 9 can answer: a leftover `{{MODULE}}` there
is the scaffold posing its question, not a substitution somebody missed. Guessing
a value to make it disappear produces a suite that passes while asserting nothing.

| Token | Substituted with | Answered at |
| --- | --- | --- |
| `{{NAME}}` | the `<Name>/` product folder form | scaffold |
| `{{NAME_LOWER}}` | the distribution name, lowercased and hyphenated | scaffold |
| `{{PKG}}` | the `src/<Package>/` importable form | scaffold |
| `{{MODULE}}` | the module being written, without its suffix | step 9 |
| `{{FUNCTION_NAME}}` | the function that module's invariant is asserted over | step 9 |
| `{{INVARIANT_ID}}` | the invariant's identifier, as `__provenance__` declares it | step 9 |
| `{{REVISION}}` | the bound revision's filename | scaffold |
| `{{SECTION}}` | the section of the proposal the module implements | step 9 |
| `{{EQUATION}}` | the equation it implements, by tag | step 9 |
| `{{ONE_LINE_STATEMENT_OF_THE_MATHEMATICAL_OBJECT}}` | one line saying what the module computes | step 9 |
| `{{SEED}}` | the seed the suite fixes | scaffold |
| `{{SEEDS}}` | the seeds a probe run repeats over | probe |
| `{{EPOCHS}}` | the epoch count a probe run reduces to | probe |
| `{{FRACTION}}` | the fraction of the data a probe run uses | probe |
| `{{DATASET}}` | the dataset a probe run reads | probe |
| `{{BASELINE}}` | the baseline a probe compares against | probe |
| `{{PROBE_RESULTS}}` | the filename a probe writes its record to | probe |
| `{{EXPECTATION}}` | what a synthetic case is expected to produce | step 9 |

## 5. Verify

```bash
implementations/<repo>/.venv/bin/python -m pytest -q
python3 skills/proposal-implementation/scripts/implementation_cli.py verify \
  --target implementations/<repo> --name Example-Method --revision research-concept-r05.md
```

```json
{
  "command": "verify",
  "target": "…/implementations/<repo>",
  "name": "Example-Method",
  "structure": { "status": "ok", "missingDirs": [], "strayModules": [],
                 "staleReferences": [], "scaffoldGaps": [],
                 "unparsableTests": [] },
  "fidelity": {
    "status": "drift",
    "latestRevision": "research-concept-r05.md",
    "staleModules": ["src/Example_Method/kernel.py"],
    "missingProvenance": [],
    "invariantsWithoutTest": ["entropy_non_negative"],
    "modules": [
      { "module": "src/Example_Method/kernel.py", "revision": "research-concept-r03.md",
        "sections": ["3"], "invariants": ["kernel_is_psd"], "stale": true }
    ]
  },
  "validation": {
    "status": "ok",
    "smokeTest": true, "invariantTests": ["test_kernel_is_psd"],
    "notebook": { "status": "executed", "codeCells": 3, "unexecuted": [], "errors": [] }
  }
}
```

`fidelity.drift` lists, per stale module, the `changedSections` between the
revision it declares and the current one and the `touchedSections` it declares
among them. Section labels follow `skills/_core/conventions/sections.json`: the
first token of a heading, a number (`3`), a dotted number (`3.1`) or an
identifier (`O1`), with an optional `.`, `)` or `:` after it. A nested
labelled heading also counts for its parent (`3.1` moving reports `3` and
`3.1`). Before 0.14.0 only a leading bare number followed by a space counted,
so identifier, dotted and label-only headings produced no sections.

`missingProvenance` never lists the kit's own seal,
`src/<Package>/report_digest.py`, while it is still the kit's file: its path
is a scaffold destination with a kit source and its bytes equal either today's
kit source or the `writtenSha256` of the scaffold receipt's `materialized`
entry for it (so a seal written by an earlier release still counts). An
`adopted` or `authored` entry does not count, and any other bytes are reported
like any other module. A freshly scaffolded target therefore reports no
provenance gap until it has modules of its own.

### `--shards` — the refusal a split campaign needs

A campaign divided across machines comes back as a directory of shards, one
subdirectory each, every one holding its own `shard.json` stamp. Hand `verify`
that directory and it checks what the declaration said had to be identical:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py verify \
  --target implementations/<repo> --name <Name> --shards <Name>/Results/shards
```

```json
{ "distribution": { "status": "incomplete",
                    "shardsDisagree": ["epochs"],
                    "shardsArrived": ["shard-00", "shard-01"] } }
```

`shardsDisagree` names the fields, not the shards, because the field is what
the declaration promised and the shards are where the promise broke.
`shardsArrived` is read off the disk every time, so three shards planned and two
returned reports two — a smaller campaign, not a failed one.

Omit the flag and both are empty. That means nothing was checked, not that
nothing was wrong, and the difference is the whole reason the flag exists. A
shard directory that is not there yet reports nothing arrived; a `shard.json`
that is not JSON raises, because an unreadable shard is not a shard that never
came back and must not be quietly counted as one.

`verify` never averages or pools what it read. Merging what may legitimately be
merged is the target's own work, in its own harness — see `SKILL.md` for why
that division is deliberate.

### The notebook is read, not counted

`notebook.status` answers whether the report was produced, not whether the file
is on disk — a template copied into place is indistinguishable from an executed
report by existence alone, and that is exactly the mistake `pyproject.toml`
already taught. The `.ipynb` records its own state, so the question is
answerable without running anything:

| status | meaning |
| --- | --- |
| `executed` | every non-empty code cell has an `execution_count` and none raised |
| `stale` | the file is there but some cells never ran — `unexecuted` lists them |
| `errored` | a cell raised; `errors` names the cell and the exception |
| `missing` / `unreadable` / `empty` | no file, not a notebook document (not UTF-8, not JSON, or JSON whose top level is not an object), or no code cells |

An `unreadable` file is a finding, never a traceback: `verify` and `probe` report
it with `sealed: false` and `sourcesMatch: null`, list it under `unsealed`, and
the notebooks verdict reads `drift`, so it never passes for a sealed or current
report.

`errored` is caught even when the notebook was executed with `--allow-errors`,
which otherwise writes a red cell and exits zero.

### A green result needs a reachable red

Two independent ways a check proves nothing while looking like coverage.

`validation.trivialAssertions` catches the syntactic one. `audit.remediesWithoutControl`
catches the structural one: a remedy test that measures its own proposed
replacement and never exercises the declared formulation it corrects. With one
pole only, nothing in the measurement distinguishes a real improvement from a
number that would have passed whatever it was handed.

Every remedy test must show both poles on the same sweep:

```python
declared_survives += global_loss(losses) > 0.1        # Eq. (37) still penalizes
vanishes          += remedy_global_loss(losses, means) < 1e-5   # the remedy does not
```

Measured on this repository, one of the four remedy tests had no control: it
only ever called its own proposal. `audit.status` is `incomplete` while any
remains.

What counts as exercising the declared formulation is read statically from
`tests/test_remedies*.py`: a `test_remedy_<id>` must call something bound to
the target's own package, spelled any of three ways —

- a name imported from it, called bare: `from <Package>.kernel import f` then
  `f(...)`;
- an attribute call rooted at a name bound to it: `from <Package> import
  kernel` then `kernel.f(...)`, `import <Package>.kernel as k` then `k.f(...)`,
  or `import <Package>` then `<Package>.kernel.f(...)`;
- a call to a function defined in the same file that does either, followed
  through any number of such helpers.

Importing the package without calling into it, handing a function along
without calling it, or calling a method of an unrelated import is still no
control.

### Assertions that cannot fail

`validation.trivialAssertions` lists two shapes: asserting a truthy constant,
and comparing an expression with itself. The scan covers the whole test module,
not only `assert` statements — the one that got through this repository fed a
counter,

```python
frozen_unchanged += adaptation(w) == adaptation(w)   # always true
assert frozen_unchanged == SWEEP_SIZE                # perfectly legitimate
```

and stayed green through three full rounds of the scenario battery. Looking only
inside assertions finds the comfortable case, not the dangerous one. `!=` is
exempt: `x != x` is the standard NaN test.

`validation.status` is `ok` only when the smoke test exists, the notebook is
`executed`, and no trivial assertion is present. Never report the ladder as run
on anything else.

## The audit bridge

`verify` also reads `tests/findings.py` statically and reports an `audit`
section. The contract mirrors the invariant bridge: every declared finding needs
a `test_finding_<id>` proving the defect is real and a `test_remedy_<id>`
proving the proposed correction resolves it without breaking anything already
established.
A finding whose remedy the bound revision has adopted is the one exception to
the second half: its remedy test is retired by design (see
[After adoption](#after-adoption-the-remedy-becomes-an-invariant)), so it is
listed under `audit.adopted` (present only when some finding is adopted)
instead of `remediesWithoutValidation`.

```json
{
  "audit": {
    "status": "ok",
    "findings": [
      { "id": "local_penalty_guarantee_is_vacuous", "kind": "overstated-claim",
        "status": "theorem", "rate": "200/200",
        "equations": ["38"], "remedyEquations": ["38"] }
    ],
    "findingsWithoutEvidence": [], "findingsWithoutRemedy": [],
    "remediesWithoutValidation": []
  }
}
```

`kind` is one of `ill-formed`, `underspecified`, `missing-complement`,
`overstated-claim`, `ill-posed-objective`, `loose-constant`. `status` is
`theorem` (holds across the whole sweep) or `tendency` (holds at the declared
rate and must not be asserted as a law).

Both halves matter. Validating the remedy is what caught the second finding in
this repository: the first proposed fix mirrored the shape of Eq. (38), and the
sweep showed that shape cannot damp anything — which turned out to be a defect
in Eq. (38) itself, not in the fix.

### `admit` — admissibility is ruled on first

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py admit \
  --target implementations/<repo> --name <Name> --revision research-concept-r05.md
```

```json
{ "status": "admitted",
  "admitted": ["local_penalty_guarantee_is_vacuous", "..."],
  "inadmissible": {},
  "introducesNotation": { "confidence_is_an_unconstrained_decision_variable":
                          ["\\operatorname{sg}", "\\lambda_{\\mathrm{conf}}"] },
  "record": "tests/admissibility.json" }
```

The ruling is written into the target and the remedy suite reads it before
measuring anything: without it every `test_remedy_<id>` fails immediately, and a
finding ruled inadmissible is never measured while the others still run. Only
the verdict travels — the revision's text stays in the forge.

Ruled against a successor that already took a remedy in, the finding is not
inadmissible for its adoption marker being gone — that absence is the adoption.
Its verdict is admissible, introduces nothing, and carries
`"adopted": {"revision": "<successor>", "matched": [<expected forms found>]}`;
the command's output lists it under `adopted` (a key present only when some
finding is adopted). The key is optional: a ruling
without it reads exactly as before. A marker gone with no expected form in its
place (`changed-unrecognized`) is still ruled inadmissible.

An audit that found nothing is ruled on explicitly, never by default:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py admit \
  --target implementations/<repo> --name <Name> --revision research-concept-r05.md \
  --no-findings
```

With `tests/findings.py` declaring `FINDINGS = []`, plain `admit` still
refuses `NO_FINDINGS` (its detail names `--no-findings`): a list nobody has
filled in yet reads exactly like an audit that found nothing, so only the flag
records the second. It writes an empty ruling (`"findings": {}`,
`"noFindings": true`) bound to the revision's bytes, and answers
`"status": "no-findings"`. `verify` then reads `audit.status` as `ok` and adds
`"noFindings": true` to `audit`. The ruling voids itself like any other: a new
revision makes it `stale` (`audit` back to `incomplete` until it is ruled
again), and a finding declared afterwards is unruled. With findings declared,
`--no-findings` refuses `FINDINGS_DECLARED` and writes nothing.

Refuses `REVISION_UNREADABLE` when the pinned document 0 revision cannot be
read, and, under a profile declaring more than one document,
`DOCUMENT_REVISION_UNREADABLE` when a declared document beyond it has no
readable revision of its own (no family found, ambiguous families, or a
discovered name that does not read) — the same code and cause every other
binding-write command shares.

Order is the whole point. A remedy that cites a missing equation or leans on
undefined notation would otherwise be swept over 200 configurations, and those
numbers would read as evidence for something that should not have reached the
bench. `verify` requires the ruling to exist, to cover every declared finding,
and to have been issued against the same revision bytes; anything else leaves
`audit` at `incomplete`.

### Sound is not the same as complete

`audit.compatibility` answers a different question from the sweep: can the
remedy be written inside the proposal as it stands? Each finding declares `uses`
— notation the remedy leans on, which must appear verbatim in the bound
revision — and `introduces`, notation it would add.

| status | meaning |
| --- | --- |
| `ok` | every cited equation exists, all notation is already defined, nothing new |
| `needs-deliberation` | sound and validated, but it would add notation |
| `incompatible` | cites an equation the revision does not have, or leans on undefined notation |
| `unknown` | the revision could not be read; nothing is concluded |

`needs-deliberation` propagates to `audit.status`, so a remedy that would extend
the notation can never be reported as settled. On this repository three remedies
are expressible as they stand, and the fourth — freezing the confidence with
`sg[·]` and adding `L_conf` with its own coefficient — introduces three symbols
the revision does not define. That is a decision for the deliberation, not a
verdict this skill may issue.

### `compose` — the remedy takes the entry's place

A deliberation replaces a whole entry, and an entry is almost always more than
the equation at issue. `compose` substitutes the remedy inside the resolved
entry's own text rather than handing back the bare block, so every neighbouring
line the entry carries survives:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py compose \
  --target implementations/<repo> --finding <finding-id> --entry-text -
```

`--entry-text -` reads the entry from stdin, which is what you want for anything
longer than a line. The finding's own `remedy_block` supplies the replacement,
and the equation's `\tag{n}` is the identity used to find what it replaces — so
the substitution lands on the equation the finding names and not on whatever
happens to look similar.

Refusals are named rather than silent: `NO_SUCH_FINDING`, `NO_REMEDY_BLOCK` for a
finding whose correction was never written, and `EMPTY_ENTRY`.

## Reading `verify`

Two independent findings, reported separately:

- **structure drift** — the layout no longer matches, or `staleReferences` lists
  a file addressing `<folder>/<Category>` that does not resolve. Both the
  textual form and the chained quoted form (`root / "Alpha" / "Results"`) are
  detected, and an **empty** directory counts as unresolved: the content it
  named is gone. A lone quoted segment (`root / "data"`) is never flagged,
  because fallback probes for optional dataset roots are legitimately absent
  and burying the real finding is worse. Fix with `plan` → `apply`.
- **fidelity drift** — `staleModules` implement an older revision than the one
  in `--revision` (a module bound to another document label's lineage under a
  keyed `revision` is listed in `otherLineageModules` instead); `invariantsWithoutTest` are claims declared in code with no
  test enforcing them. Both need the user's decision before you touch anything.

Twelve more are reported and none of them is a finding, which is exactly why
they were easy to leave undocumented:

- **`coupling`** — which notebook cells reach into the target's internals instead
  of going through its declared surface. It **never gates**: it is a static
  reading, and a cell that reaches inside is sometimes the right thing to have
  written. Read it before deciding a notebook is portable, and do not treat a
  non-empty result as a defect to fix on sight.
- **`lfs`** — which large files under the target are real content and which are
  still unfetched pointers. A pointer is not a missing file and not a broken
  one; it is a file nobody has paid to download yet. Read it when a run reports
  data it cannot open, because that is what it usually is.
- **`position`** — the execution sequence's derived state, read from
  `<Name>/AGREED.md`'s own position section. Every mark is measured, never
  asserted: `sequence` lists each step's disk mark beside what the evidence
  actually says, `disagreements` names a mark contradicted by measurement,
  `unbacked` names a mark that is ticked with nothing measured behind it (an
  assertion, not a reading), and
  `unmeasured` names a witness this invocation could not check at all (most
  commonly `@shard` without `--shards`). It **never gates** — read it before
  telling a human a step is done. A `disagreements` entry is cleared by a
  `position` refresh, which rewrites a contradicted mark on the spot; an
  `unbacked` one is not, because that same refresh deliberately never rewrites
  a mark it could not measure. Run `position` there and read the `resolve` it
  prints — see "`unbacked`, and the `resolve` that clears it" below.
- **`agreements.witness`** — a nested reading of every checklist item's
  optional trailing `` `test_<id>` `` token (`settle --witness` is the only
  command that ever writes one). Three states, never collapsed into one
  another: `unwitnessed` (the line carries no token — a state, not a
  failure), `unmeasured` (a token is declared but this run could not, or
  would not, call it a contradiction — this CLI never executes a suite, so
  even a token whose function name *is* found among `test_<id>` functions
  stays `unmeasured`, never "proven"), and `disagrees` (declared, `tests/`
  is readable and fully parsed, the item is ticked, and the declared
  function is absent). Two more keys appear only when non-empty: `decided`
  (ticked witness-less lines closed by `settle --done --unwitnessed`, each
  `{text, reason, session, at}`) and `handTicked` (ticked witness-less lines
  with no such recorded act); neither counts as witnessed, and both lines
  stay listed under `unwitnessed`. `summary` prints `"N of M witnessed"` on every run,
  including a target with zero declared tokens (`"0 of 0 witnessed"`) —
  silence never stands in for "nothing is declared". It **never gates
  here** — `close` is the one place `disagrees` refuses
  (`AGREEMENT_DISAGREES`); `verify` and `probe` only ever report it.
- **`toDiscuss`** — one directly runnable, `shlex.quote`-escaped `discuss`
  command per `audit.localRemediesNotWritten` finding id, asking whether
  that finding's local remedy is written now or deliberately deferred (and
  why). Question text derives from the finding id alone, never a count or
  anything else that could vary between calls while the same finding stays
  unwritten — run it verbatim, or run `discuss` by hand. Never published
  for `prose.staleRevisions`/`unresolvedSymbols` (unbounded per call, and
  the engine already declines to judge them) or `agreements.witness.
  unwitnessed` (a legitimate resting state, not an open question). It
  **never gates** — publishing the command lowers the friction to ask; it
  does not prove whoever answers it is the operator.
- **`undeclaredOptional`** — every optional key a DECLARED `search` or
  `distribution` block left unanswered: `search.record`,
  `search.currentWhen`, `distribution.currentWhen`,
  `distribution.shardsRoot`. Each entry names
  its `section`, `field` and the exact `consequence` its absence carries —
  e.g. without `search.record` nothing was ever told which artefact the
  search writes, so `recordFound` answers `null` on every run and `probe`
  keeps answering `search-first`; without `search.currentWhen`, a found
  record is trusted on the
  strength of being present, never checked against the code that produced
  it. **Reported, never demanded**: a target with no search, or no split
  run, is asked nothing here either — the same restraint every other
  optional field in this file already keeps. It **never gates** — an
  unanswered optional field is a legitimate resting state, not a defect;
  this only makes the option visible. It carries every unanswered optional
  field MINUS the ones `undeclaredBlocking` reports below: a field the
  target's own sequence is waiting on is not optional in any sense this
  word carries, and leaving it in a list called `undeclaredOptional` is
  what let one be read as "unanswered, fine" four ordinals before the flow
  died on it.
- **`undeclaredBlocking`** — the other half of that absence, and the half
  `undeclaredOptional` cannot honestly hold: an undeclared optional field a
  witness in the target's OWN declared sequence cannot be measured without,
  so what its absence costs is a declared step rather than a reading. Each
  entry carries `section`, `field`, `evidence` (the key that field produces),
  `blockedBy` (every sequence item measured through it, with its witness),
  `blockedSteps` (every declared step whose `advances` ordinal sits above the
  earliest of them), the `consequence` — the field's own composed into a
  sentence naming the ordinals and the steps — and an `exit`. **The set is
  derived, never listed.** Each roster entry states only what it feeds, and
  blocking is the join against the sequence: an item whose `measuredBy` head
  is that key. The head and never the whole string is what keeps the two
  halves of a section apart — `search.currentWhen` and
  `distribution.currentWhen` are corroborators, never a head, so they narrow
  a reading and stay above — and it sorts the record kinds for free, since a
  named `@record:level <name>` is measured through its own `__records__`
  entry while the two-state `@record` beside it is measured through
  `search.recordFound`. `[]` when the target declares no ordered flow, when
  no unanswered field's key is named by any item, and when every such item
  sits at or above the furthest ordinal any step advances — the same rule
  `unfinishableFlow` keeps, read off `cmd_step`, which refuses only on items
  strictly below the ordinal a step advances. It **never gates**: the
  refusal it reports ahead of is unchanged. Its `exit` is a **question and
  never a command**, because the one act that clears it is an edit to the
  target's own benchmark declaration and the forge authors no target
  declaration — so what you get is the question and the directly runnable
  `discuss` command that opens it, exactly as the `POSITION_SHARDS_
  UNDECLARED` refusal already publishes one.
- **`undeclaredLadder`** — the ordered rung ladder `__levels__` names, in
  the case where it names none: `declaration`, the `path` of the file that
  would carry it, and the exact `consequence` of leaving it empty. That
  consequence is the point, so it is spelled out rather than named:
  `POSITION_RUNG_SKIPPED` — the refusal that stops a pass sealing at a rung
  whose predecessor the evidence has not reached — can never fire against an
  empty ladder; `position.attainedLevel` stays `null` on every run, because
  there is no rung name to answer with; every sequence item stays two-state,
  since a `:level`-marked witness is refused outright
  (`POSITION_LEVELS_UNDECLARED`), so a step that got part of the way has no
  rung to be recorded at; and `--target-level` accepts any word, because
  `POSITION_TARGET_LEVEL_UNKNOWN` compares against a declared vocabulary and
  there is none. `null` when a ladder is declared, and `null` for a target
  with no benchmark package to declare one in — `structure.scaffoldGaps`
  already names that missing file. **Reported, never demanded**: a
  repository whose steps are all two-state legitimately has no ladder, and
  the forge never invents a rung name on its behalf. It **never gates**.
- **`unreachableLadder`** — the other half of the same declaration, and the
  one `undeclaredLadder` cannot reach: a ladder that WAS named, long enough
  that the sequence beside it can never climb to the launch floor. It carries
  `levels` (the ladder as declared), `requiredLevel` (the rung
  `launch_available` floors a launch at, `levels[-2]`), `highestAttainable`
  (the highest rung every leveled item in the sequence could EVER grade
  satisfied at), `cappedBy` (the ordinals and witnesses holding it there) and
  the `consequence`. It fires only when the second sits strictly below the
  first — from four declared rungs up, with one leveled `@rehearsal` item
  anywhere in the sequence: `smokeReady` is two-valued, so that item can never
  prove more than the floor plus one rung, and `position.attainedLevel` is the
  highest rung at which *every* leveled item grades satisfied. `gate` then
  answers `RUNG_NOT_ATTAINED` on every call, naming a rung nothing that can
  run will reach. Two exits, both the target's own: declare at most three
  rungs, or drop the `:level` marker from that item and record it two-state
  (the grammar's default). A sequence with no leveled item attains the rung
  its position aims at, so after the second exit the position must aim at
  the launch rung (`position --target-level <requiredLevel>`) before `gate`
  passes. The forge takes neither on its own — a launch floor
  that moved with whatever the sequence happens to hold would let *adding* a
  leveled item quietly *lower* the threshold for every item beside it. `null`
  when the ladder and the sequence can meet, and `null` below two rungs, where
  the rung threshold does not apply at all. It **never gates**.
- **`unfinishableFlow`** — an ordered flow the target cannot walk to the end
  of below its own declared scale, said before the first step runs. It carries
  `requiredScale` (the scale the search declares for itself, which is what
  decides), `blockedBy` (every sequence item a run below that scale can never
  tick), `blockedSteps` (every declared step that must wait behind the earliest
  of them) and the `consequence`. The pair that makes an item unsatisfiable is
  two-state **and** graded against a declared scale, never two-state alone: a
  two-state `@notebook` item is satisfied by a notebook executed against these
  sources and ticks fine at pilot, while a two-state `@record` item is graded on
  `search.scaleSatisfied` and derives `false` until the full scale is reached —
  with no rung for a smaller run to earn partial credit at. `step` then refuses
  `STEP_SEQUENCE_NOT_REACHED` for every step above it, on every call, while
  `pilotCompleteness` asks for that same flow to finish at pilot. The exit is
  the target's own and is already built: mark that item leveled and give it a
  named witness, `@record:level <name>`, backed by one `__records__` entry per
  record the flow actually produces, each with its own `path` and its own
  `requiredScale` — a named entry is graded against ITS own scale, so the
  record a smaller run leaves behind reaches a rung a smaller pass can be
  sealed at while the entry declaring the full scale still reaches the top.
  `null` when the search declares no scale, when no item is graded against one,
  and when no step waits behind such an item. It **never gates** — the refusal
  it reports ahead of is unchanged, and nobody is let through any earlier.
- **`undeclaredProduces`** — one entry per declared `__steps__` step that names
  no `produces`, the list of path roots (relative to the product folder) that
  step and only that step writes into. Not a defect and never a gate: it names
  what the absence costs. `step` snapshots the product folder before and after
  every run and reports `wrote`; with no declared root it can tell neither a
  run that returned having written nothing from one that produced its whole
  output, nor a run that stayed in its own tree from one that wrote into a
  neighbour's — the second of which was measured twice in one day on one
  repository, each time reported as `returned` and caught only by a digest
  compared by hand. Declare the roots, or leave the reading switched off
  knowingly. The kit ships the key in its own `__steps__` example, so a
  repository built from zero is asked rather than defaulted past.
- **`undeclaredStepNotebooks`** — the same declaration one reading deeper, and
  the half `undeclaredProduces` cannot answer: one entry per declared
  `__steps__` step that names no notebook among its `produces` roots. A pilot
  is the declared flow walked with the declared notebooks, and a step's
  notebooks are read off those roots and off nothing else, so a step naming
  none is walked by calling the target's own library while the notebook that
  would carry the same work to a worker elsewhere goes untouched by the very
  run meant to validate it. It reads that one declaration and **never the
  position sequence**: a notebook is also reachable through the item at a
  step's `advances` ordinal, and a step reached only that way is named here
  anyway, because a sequence witness is a mark in `AGREED.md` that a repository
  built from zero has not written — consulting it would go quiet on exactly the
  repository this exists for. The exit for that false positive is the cheap
  one: name the notebook in `produces` too. The shape it asks for is two steps rather than one,
  each naming its own root under `Notebooks/`: one that **computes** —
  orchestrating the library, writing data, drawing nothing — and one that
  **draws**, reading what the first left behind and rendering tables, figures
  and conclusions. Collapsing them is a legitimate design and this never
  refuses it; what it costs is that a figure cannot be redrawn without paying
  for the computation again, and that whichever half sits outside a notebook is
  the half the pilot never exercised in the shape it will be sent in. It names
  every step that owns no notebook, **including one that declares no
  `produces` at all** — deliberately not subtracted from `undeclaredProduces`,
  because `[]` here has to mean *every declared step owns a notebook* and
  subtracting would let a repository whose steps all declare nothing read
  empty. A new key and not a widening of `pilotCompleteness.withoutNotebook`:
  that one is computed from a pilot's own evidence and says *this repository
  opened no notebook here*, after a run; this one is read off the declaration
  alone and says *nobody ever asked it to have one*, which is the question a
  repository built from zero has to meet before any run exists. `[]` when every
  declared step names one, when no step is declared, and when there is no
  benchmark package to declare one in — `structure.scaffoldGaps` already names
  that missing file. It **never gates**. The kit ships both kinds of step in
  its own `__steps__` example, so a repository built from zero meets the
  pattern rather than discovering it after a pilot has run.

Omit `--revision` and `fidelity.status` is `unknown`: the modules' declared
revisions are still listed, but nothing is compared. Never report an
implementation as up to date from an `unknown` run.

`fidelity.status` carries four values, and the headline never reads better than
the block underneath it:

| value | meaning |
| --- | --- |
| `unknown` | no revision could be established at all — none was given and none discovered — so nothing was compared |
| `drift` | something that exists is defective: a stale module, missing provenance, an untested invariant, or an arm that never calls what it declares |
| `undeclared` | the Benchmark package exists and every block of `__benchmark__` is still at its scaffolded empty value; `fidelity.benchmark.status` reports the same word |
| `ok` | a declared benchmark, and none of the above |

`drift` outranks `undeclared` on purpose, the way `unfaithful` already outranks
`stale` inside `fidelity.benchmark`: a stale module is a defect in something that
exists, and an undeclared benchmark is the absence of a declaration. An
**absent** Benchmark package is deliberately not folded in — there is nothing to
be unfaithful to, and `structure.scaffoldGaps` already names the missing file.

### Which revision counts as the newest

Without `--revision`, `verify` derives a family from the name the bench itself
declares and discovers the newest member. Only **published** revisions are
eligible: a revision is published when the deliberation skill writes the artifact
marker as the file's first bytes, and a draft, an export or a copy dropped into
the same directory carries no marker. Before that rule existed, such a file
became "the newest" and every module was reported stale against a document nobody
had published.

The discriminator is the marker, never a filename shape — the resolver knows no
naming convention, by design, so a forge whose revisions are `draft-4.md` is
served by the identical code. Three additive fields say what discovery saw:

| field | meaning |
| --- | --- |
| `fidelity.markerOwned` | `true` when at least one candidate of the family carries the marker, so only marked candidates were eligible; `false` when none does and resolution is exactly what it always was |
| `fidelity.nonManagedCandidates` | the unmarked candidates that were passed over, named rather than silently filtered |
| `fidelity.revisionTie` | candidates tying on the digit tuple (`draft-1.md` and `draft-01.md` are one family and one key); the deterministic pick is preserved and the ambiguity is reported |

All three are reported and none of them refuses: `verify` reads, and a stray file
in a directory must not stop the whole check. The filter applies to discovery
only — an explicit `--revision` is read verbatim, whether or not it is marked.

## `position` — refresh and install the execution sequence

`verify`/`probe` only ever *read* the position section (above). `position` is
the one command that writes it — `settle` (below) is the other writer into
`<Name>/AGREED.md`, and the two never touch the same lines: `position` only
ever rewrites the marks of its own delimited block, `settle` only ever inserts
one plain checklist line outside it. No flag: re-derive the marks of whatever
block is already there, touching nothing else about it — not the item text,
not the order, not which witness each one names.

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py position \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id>
```

```json
{ "command": "position", "target": "…/implementations/<repo>",
  "name": "Example-Method",
  "status": "written", "holder": "Method/AGREED.md",
  "wrote": [2], "left": [1], "unmeasured": [3], "unbacked": [],
  "revision": "research-concept-r05.md",
  "revisionSha256": "9251935…",
  "sequence": [ "..." ] }
```

`revisionSha256` is the hash of the revision the header is bound to, and it is
what makes a clean `verify` mean something: a revision can be rewritten in place
under the same filename, and only the hash catches that. `revision` names the
file; `revisionSha256` says which bytes.

`status` is `"written"` only when something actually moved — a mark flipped, or
the header rebound to a different revision. Nothing to flip and nothing to
rebind reports `"unchanged"` and touches neither the file nor the ledger:
writing a fresh timestamp over marks nobody re-measured would claim work that
did not happen. `"absent"` means there is no block yet — install one first.

`--shards <dir>` measures every `@shard` witness against that directory,
whichever write mode this call uses — a bare refresh included. Without it,
`@shard` reads `unmeasured` (never `False`): the shard may well have
arrived, this invocation simply was not told where to look.

### `unbacked`, and the `resolve` that clears it

`unbacked` lists every ordinal whose box is ticked and whose witness this run
could not measure — an assertion, not a reading, and the one thing a refresh
leaves exactly where it found it. That restraint is deliberate: a mark rewritten
from evidence nobody could read would be a guess, and a derived mark that
sometimes guesses is not worth reading. So the refresh reports the tick and
changes nothing.

Which leaves the question of how to get out, and the answer is a **reinstall**:
`--sequence - --replace` installs every item blank and re-derives the whole
sequence inside that same call, so every mark anything can measure comes
straight back and only the assertions go. The array that command reads from
stdin is the sequence the report just printed — so `position` builds it and
publishes the whole thing:

```json
{ "status": "written", "unbacked": [3],
  "resolve": { "kind": "command",
               "command": "printf '%s' '[{\"text\": \"...\", \"witness\": {...}}]' | ... position ... --sequence - --replace" } }
```

`resolve` is on every branch and is `null` when nothing is unbacked. The
command runs unedited: the payload is inside it, and the `--shards` this
invocation was given is carried into it, so the reinstall measures exactly what
the report measured rather than blanking a tick this run had just earned.

`verify` and `probe` report `position.unbacked` and publish no command for it.
A `position` write is stamped with the caller's own `--session`, neither of
those two commands carries one, and an identity the engine made up is worse in
the ledger than an extra step here: run `position` and read its `resolve`.

### `--target-level` — the rung this pass is aiming at

Every write mode also takes `--target-level <level>`, the header field a
mark is now measured against: a witness's mark means "reached the level
this pass asks for", not a bare pass/fail, unless the witness is two-state
(see below). `<level>` must be one of the target's own `__levels__`, a
second top-level literal declared next to `__benchmark__` in the benchmark
package's `__init__.py` (or `config.py`) — an ordered list, entirely in the
target's own words, e.g. `__levels__ = ["local", "cluster"]`. Required only
for a fresh header with nothing to inherit one from; a bare refresh reuses
whatever the existing block already recorded when `--target-level` is
omitted, the same way it never asks a caller to retype item text nobody
changed. Refuses `POSITION_TARGET_LEVEL_REQUIRED` (fresh header, nothing
given or to inherit), `POSITION_TARGET_LEVEL_UNKNOWN` (the value named is
not one of `__levels__`'s own entries), and `POSITION_LEVELS_UNDECLARED` (a
leveled witness exists in the sequence but `__levels__` declares no
ladder).

#### A rung is never skipped going forward

Naming a declared rung is not the same as being allowed to reach it. **To
seal at rung N, every leveled item in the sequence must already grade as
satisfied at rung N-1** — otherwise `POSITION_RUNG_SKIPPED`, a work state
whose published `resolve` names the rung this target *can* seal next and
asks what has to run before the one above it can be claimed. The rung whose
whole purpose is proving the flow runs before anything is spent further up
is exactly the rung a jump would skip.

The check reads the **evidence**, never the ledger. "Was there a prior pass
at the rung below" would be the obvious rule and is deliberately not the
one: a target that has never run this command has no `position.jsonl` at
all, so a history check would pass vacuously on precisely the repositories
it exists to stop. Instead the sequence is re-graded by
`impl_position.derive` itself at the previous rung, so "satisfied at rung
N-1" means here exactly what it means when a mark is written.

**The header states an aim, not an attainment.** `target=` is the rung a
pass is *aiming at*, and an aim legitimately sits one rung above what has
been reached — otherwise no pass could ever climb. So the rule is put to
the evidence and never to that field: `attained_level` answers *which rung
the evidence currently reaches* (the highest rung at which every leveled
item grades satisfied), and an aim may reach at most one rung above it.
Where a pass came from is not consulted at all — a retreat and a re-seal
land on rung N and assert that N-1 is reached exactly as a climb to N
does.

That separation is also published: `position`'s state carries
`attainedLevel` beside `targetLevel`, so the gap between what a pass aims
at and what backs it can be read without tripping a refusal to find it.
`attainedLevel` never claims more than ran: with no leveled (`:level`)
witness in the sequence, nothing measured a scale, and it reports the aim
(`targetLevel`), never a rung above it. Before 0.14.0 such a sequence
reported the ladder's top.

Three boundaries, each of them decided rather than fallen into:

- **The first rung has no predecessor.** Sealing at `__levels__[0]` is
  always possible, including on a repository with no evidence whatsoever —
  a ladder needs a bottom step or nothing can ever start. This is also what
  keeps an operator from ever being cornered: `position` is the instrument
  that measures, and an instrument that refuses to take a reading because
  the reading is bad hides the regression it exists to report. When
  evidence collapses, the floor is still sealable, demoting the header to
  it is the honest reading, and the refusal that sends an operator there
  names every item that came up short.
- **Two-state items do not participate.** Their verdict is computed without
  the ladder and is identical at every rung, so they say nothing about
  which rung was reached. Folding them in would refuse a legitimate advance
  because some unrelated boolean step is still open. Their own ordering is
  already held, within a rung, by `SEQUENCE_NOT_REACHED`.
- **Unmeasured is not attained.** A leveled item nobody could measure does
  not satisfy the rung below, because "we did not look" is not "it has been
  reached". This is also what separates the rule from a cheaper one that
  merely counts ladder positions: even a single-step advance is refused
  when the step below it is not *shown* attained.

A target that declares no `__levels__` at all is entirely unaffected: no
ladder, no rungs, no progression to enforce. Unaffected is not the same as
unremarked — nothing here ever asks a target for a ladder, so `verify`
reports the absence and what it costs under `undeclaredLadder` above, and
leaves the decision where it belongs.

Each witness in the block's markdown may carry `:level` right after its
kind — `` `@rehearsal:level governing-search` `` — to opt into being
measured against the declared ladder instead of a plain pass/fail. Omitted
(the default, unchanged from before this mechanism existed), a witness is
**two-state**: satisfied or not, with no rung ever assigned to it — a step
that only ever holds or does not (a local check with nothing in between)
declares itself this way and is never assigned a level string, no matter
how the evidence underneath it reads.

`--sequence -` installs a fresh section instead of refreshing one, reading an
ordered JSON array of `{text, witness: {kind, operand, twostate}}` from
stdin — `witness.twostate` defaults to `true` when omitted, the same
default the markdown grammar itself keeps:

```bash
echo '[{"text": "Search for the governing value.",
        "witness": {"kind": "record"}},
       {"text": "Rehearse the campaign job.",
        "witness": {"kind": "rehearsal", "operand": "governing-search",
                    "twostate": false}}]' \
  | python3 skills/proposal-implementation/scripts/implementation_cli.py position \
      --target implementations/<repo> --name <Name> \
      --revision research-concept-r05.md --session <your-session-id> \
      --target-level local --sequence -
```

Every declared item is validated by the same grammar that reads a hand-authored
block — a malformed witness is refused here, not left to surface at the next
`verify`. Installing over a block that already exists refuses
`POSITION_BLOCK_EXISTS` unless `--replace` is also given.

The holder is found by shape, never by a fixed filename — the same rule
`agreements_state` already applies — except that a sibling skill's own
declared holder (`Experimental_AGREED.md`) is never a candidate, for reading
or for writing. Refuses `POSITION_HOLDER_ABSENT` when no
markdown file in the product folder holds anything to append into, and
`POSITION_HOLDER_AMBIGUOUS` when more than one candidate exists and none is
decidable without a human choosing. A malformed existing block —  no witness,
an unknown witness kind, or more than one `<!-- position -->` opener — refuses
with `POSITION_ITEM_WITHOUT_WITNESS`, `POSITION_WITNESS_UNKNOWN_KIND`,
`POSITION_ITEM_MALFORMED`, `POSITION_BLOCK_MALFORMED` or
`POSITION_BLOCK_NOT_UNIQUE`: the same class `MALFORMED_FINDINGS` already is
for `read_findings`, a broken artifact rather than a not-yet-ready target.

### `--reconcile` — reconstruction from what the target already has

For a target that already has notebooks, job folders and a declared search
but no position section yet:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py position \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id> \
  --target-level local --reconcile
```

Builds one `@record` from the benchmark's declared search, one `@rehearsal`
per discovered job folder, one `@notebook` per `Notebooks/*.ipynb` in name
order, and — with `--shards` also given — one `@shard` per arrived shard,
each measured `True` against that same directory in the same call, not left
`unmeasured` until some later invocation happens to pass `--shards` too.
Every discovered witness is two-state — reconciliation discovers that a
step exists, never what a human means by it, and only a human editing
`AGREED.md` to add `:level` afterward can say a step has rungs at all.
Existing items are matched by witness identity (kind and operand) and keep
their text and their order exactly; only a witness with no match is
appended, its text a placeholder for a human to write over. Safe to run
again: an unchanged target appends nothing and reports `"unchanged"`.
`--sequence` and `--reconcile` together refuse `POSITION_SEQUENCE_AND_RECONCILE`
— only one of the two may name this call's sequence. `--target-level` is
required here too only for a fresh header; a `--reconcile` that merges into
an existing block reuses its recorded target when omitted.

## `discuss` — a question with a return value

Replaces telling the agent, in prose, to name a collision with an existing
agreement and wait: `discuss` makes "I asked" a fact with a ledger line
instead. It never gates — an unanswered question is a reported `status`,
not a refusal.

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py discuss \
  --target implementations/<repo> --name <Name> \
  --about "rehearsal governing-search" \
  --question "Should this job rehearse before the campaign?"
```

```json
{ "status": "open", "about": {"ordinal": null, "kind": "rehearsal",
                              "operand": "governing-search"},
  "measured": null, "collides": [], "collisionSearch": "performed",
  "asked": "Should this job rehearse...", "answered": null }
```

`--about` names the step either by its ordinal in the current position
sequence, or by a bare witness spec (`"kind"` or `"kind operand"`) when
there is no sequence item yet to number — for `notebook`/`rehearsal`/`shard`
the operand is required (`DISCUSS_ABOUT_OPERAND_REQUIRED` refuses a bare
`--about notebook` with none); `record` is the one witness kind that keeps
accepting none. `--answer` (optionally `-` to read stdin, like `--question`)
moves `status` from `"open"` to `"answered"`; at most one of
`--question`/`--answer` may read stdin in the same call. `collides` is
computed fresh against every checklist item in the product folder's
markdown that names the same operand — never remembered from an earlier
call, and never against the position section's own item lines, which are
excluded from the search along with the rest of the block. `collisionSearch`
distinguishes the two ways `collides` can read `[]`: `"performed"` when the
witness carried an operand to search with, `"unperformed"` for the one kind
(`record`) that never does — an empty list alone cannot tell "searched, found
nothing" apart from "could not search at all".

## `settle` — place what `discuss` answered

Once a `discuss` question is answered, `settle` performs the actual write —
the agent drafts the question and the proposed sentence, `settle` validates,
refuses, and writes. It never authors the text and never ticks the box: the
mark placed is always `[ ]`, and the text placed is `--text`, verbatim.

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --about "notebook Notebooks/verification.ipynb" \
  --text "the free scalar stays at its neutral and identical across arms" \
  --under "## Ladder"
```

```json
{ "status": "written", "holder": "Method/AGREED.md",
  "about": {"ordinal": null, "kind": "notebook",
           "operand": "Notebooks/verification.ipynb", "twostate": true},
  "text": "the free scalar stays at its neutral and identical across arms",
  "under": "## Ladder", "supersedes": null, "collides": [] }
```

`--about` takes the identical shape `discuss`'s own `--about` does (an ordinal
or a bare witness spec), matched against the ledger by witness identity
`(kind, operand)` — ANY answered `discuss` event for that identity satisfies
this, never newest-wins, so a later open clarifying question never erases an
earlier answer. Refuses `SETTLE_NOT_DISCUSSED` when no `discuss` event names
it at all, `SETTLE_DISCUSSION_UNANSWERED` when one does but none is answered.

`--under` is matched by exact equality against a heading line, hash marks
included — `## Figures` never matches `## Figures — phase 2`. The item is
appended after the section's last checklist item, so a section reads in the
order its items were settled (oldest first). The section runs to the next
heading of any level. The position block's own lines are never the section's
items: on the holder `position` creates (block directly under `## Ladder`),
the first item lands directly after `<!-- /position -->`. A section with no
item and no block receives the item at its first non-blank line. Nothing
already in the holder moves: a holder written by 0.13.0 or earlier, whose
section reads newest first, keeps those lines in place and gains the new item
after them. Refuses
`SETTLE_HEADING_ABSENT` or `SETTLE_HEADING_AMBIGUOUS` when it occurs zero, or
more than one, times across every markdown file `agreements_state` already
knows holds checklist items; `SETTLE_HOLDER_ABSENT` when none does at all.

On a collision — the same collision search `discuss` already reports — name
the existing item this placement supersedes with `--supersedes "<exact
text>"`, or `settle` refuses `SETTLE_COLLIDES_UNNAMED`. The refusal names
every colliding text verbatim, never a bare count ("2 existing
agreement(s)"), and also prints one directly runnable, `shlex.quote`-escaped
`discuss` command asking which one, if any, this placement supersedes — the
same identity-derived, `discuss --answer` retirement discipline
`DISCUSSION_UNANSWERED` uses. `--supersedes` must exact-match a member of the
computed collision list (`SETTLE_SUPERSEDES_UNKNOWN` otherwise) and is
recorded in the ledger event only: the document itself still needs a
human-written `Reversed` paragraph to show a supersession actually happened.
`--text -` and `--supersedes -` cannot both read stdin in one call
(`SETTLE_STDIN_CONFLICT`).

### `--witness` — binding this agreement to a test, at write time

Optional `--witness test_<id>` names this agreement's own function in the
declared-invariants suite — a separate identity from `--about`, which names
the *position* witness this placement discussed. Given, it is persisted
verbatim into the written line as a trailing `` `test_<id>` `` token;
omitted, the line is byte-identical to the pre-witness grammar, exactly as
it always was. Refused `SETTLE_WITNESS_MALFORMED` if given and it does not
match `test_[A-Za-z0-9_]+` — a malformed value would otherwise round-trip
as inert trailing text, never as a witness `agreements_state` could read
back.

**`settle` is the only command that ever writes this token.** There is no
`patch` or `edit` subcommand, by design (spec Group 5): a witness token is
bound either at the moment an agreement is placed (`--witness`, above),
with `--attach` (below) afterward, or re-pointed onto a different test
with `--attach --replace` (further below) — all three routes stay inside
this one command; there is still no fourth way in. Hand-typing one into `AGREED.md`
is unsupported doctrine, not a technical prevention — the parser cannot,
and does not try to, distinguish a skill-written token from a hand-typed
one, so `verify` and `close` evaluate either exactly the same way.

### `--attach` — binding a witness to a line already settled

`--text` only ever CREATES with the shape above; there was no way to bind
`--witness` onto an agreement a prior `settle` call already placed, ticked
or not, without either hand-editing `AGREED.md` (unsupported) or
re-`settle`ing it (which would write a second, fresh `[ ]` line beside one
that may already be ticked). `--attach` closes that gap:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --attach \
  --text "the free scalar stays at its neutral and identical across arms" \
  --witness test_the_free_scalar_stays_neutral
```

```json
{ "status": "written", "holder": "Method/AGREED.md", "attach": true,
  "about": null, "text": "the free scalar stays at its neutral and identical across arms",
  "under": null, "witness": "test_the_free_scalar_stays_neutral",
  "supersedes": null, "collides": [] }
```

`--text` is matched by EXACT equality against an existing line's own
`AGREEMENT_LINE` text group — the identical "found by shape, matched
exactly" discipline `--under` already uses for a heading. Refuses
`SETTLE_TEXT_ABSENT` when it matches no existing line, `SETTLE_TEXT_AMBIGUOUS`
when it matches more than one — which one receives the witness is not
decidable without a human choosing, the same reasoning
`SETTLE_HEADING_AMBIGUOUS` already states one level up. `--witness` is
required in this mode (`SETTLE_WITNESS_REQUIRED` if omitted — binding one
is the entire point) and refused `SETTLE_ALREADY_WITNESSED` if the located
line already carries a token and `--replace` is not also given: `--attach`
adds a witness, it never replaces one on its own — the refusal's detail
names `--replace` as the exit. See below for what `--replace` does.

**The mark is never touched.** A ticked item stays ticked, an open one
stays open — only the witness token is appended, and everything else in
the holder file is byte-identical afterward. `--under` and `--supersedes`
name nothing in this mode and are refused `SETTLE_ATTACH_CONFLICT` if
given together with `--attach`.

**The discussion precondition is skipped, on purpose.** `SETTLE_NOT_DISCUSSED`
/ `SETTLE_DISCUSSION_UNANSWERED` exist so nothing is PLACED without having
been discussed first. A line `--attach` matches was, by construction,
already placed by an earlier `settle` call — it already passed that gate
once. Binding a witness onto it afterward is not placing a new agreement;
requiring a fresh `discuss` per already-settled line would be ceremony
with nothing behind it. `--about` is not even resolved in this mode, since
there is no discussion gate left to check it against.

**This is the mechanism, not the retrofit.** Running `--attach` over every
already-settled line in a target is a separate, bounded, operator-directed
pass — never something a flow does incrementally as it happens to
encounter an unwired agreement.

**`--replace` — re-pointing a witness onto a different test.** Re-pointing
a proof is not retracting a claim: the agreement's truth did
not change, only the artefact that demonstrates it. The only path that
reached this end state before `--replace` existed — `--reverse` followed
by a fresh placement — de-ticks and un-witnesses a line that was already
measured and closed, forcing re-discussion and re-measurement to reach the
state it already had. `--replace` closes that gap by modifying `--attach`
itself, rather than adding a sixth mode: the mark is never touched, and
the behaviour is mark-blind between a ticked and an open line, exactly as
plain `--attach` already is.

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --attach --replace \
  --text "the free scalar stays at its neutral and identical across arms" \
  --witness test_the_free_scalar_stays_neutral_across_arms
```

```json
{ "status": "written", "holder": "Method/AGREED.md", "attach": true,
  "replace": true, "replacedWitness": "test_the_free_scalar_stays_neutral",
  "about": null, "text": "the free scalar stays at its neutral and identical across arms",
  "under": null, "witness": "test_the_free_scalar_stays_neutral_across_arms",
  "supersedes": null, "collides": [] }
```

**The operator-facing surprise, shown explicitly.** `--text` is matched
against `AGREEMENT_LINE`'s own `text` group, and that group stops before
the trailing `` `test_<id>` `` token — the witness is never part of
`--text`, in this mode or in plain `--attach`. Re-pointing a line that
reads `` - [x] the free scalar stays at its neutral and identical across
arms `test_the_free_scalar_stays_neutral` `` is `--text "the free scalar
stays at its neutral and identical across arms"`, never `--text "the free
scalar stays at its neutral and identical across arms
\`test_the_free_scalar_stays_neutral\`"` — the latter matches zero lines
and refuses `SETTLE_TEXT_ABSENT`, because no line's own text group ever
contains its trailing token.

Three refusals guard this path, each an `INVOCATION_DEFECT` — a fact about
this call's argv, not about the state of the work:

- **`SETTLE_REPLACE_CONFLICT`** — `--replace` given without `--attach`.
  `--replace` modifies `--attach`'s own write; it names nothing on its own.
- **`SETTLE_NOTHING_TO_REPLACE`** — the located line carries no witness at
  all. The caller asked to replace a binding, and none existed; plain
  `--attach` (without `--replace`) is the create path for a first witness.
- **`SETTLE_WITNESS_UNCHANGED`** — the incoming `--witness` equals the one
  already on the located line. Refusing rather than writing keeps every
  `replacedWitness` ledger event honest evidence of an actual change,
  instead of a no-op splice that claims one.

**No test-suite measurement leaks in.** `--replace` never reads `tests/`
and never checks whether either witness — the displaced one or the
incoming one — names a real, existing test. Gating on that fact is
`verify`'s and `close`'s job, reached only through `agreements_state()`;
`settle` writing a second, independent check of the same fact would be a
second gate on the witness axis, which is the doctrine this modifier is
written not to disturb.

**The mark is never touched, inherited rather than restated.** This is
exactly `--attach`'s own rule, one caller further in — a ticked item stays
ticked and an open one stays open, and every other byte of the holder file
is identical before and after the call. The previous token is recorded as
`replacedWitness` in both the appended `settle` ledger event and this
call's own response, alongside an always-present `replace` boolean that
mirrors the other four mode flags on every `settle` call, whether or not
that call ever exercises `--replace`.

### `--remove` — the eraser, guarded by the record itself

`--text` only ever CREATES, and `--attach` only ever binds a witness onto
a line that stays exactly where it was. Neither ever deletes one. Moving
an agreement between sections, or dropping one the target has genuinely
outgrown, had no supported path at all — either a hand edit
(unsupported) or leaving a retired line sitting under a heading it no
longer belongs to. `--remove` closes that gap by deleting the located
line's own bytes outright, including its trailing newline, and touching
no other byte in the document:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --remove \
  --text "the free scalar stays at its neutral and identical across arms"
```

```json
{ "status": "written", "holder": "Method/AGREED.md", "remove": true,
  "about": null, "text": "the free scalar stays at its neutral and identical across arms",
  "under": null, "witness": null,
  "supersedes": null, "collides": [] }
```

`--text` is matched by the identical exact-equality discipline `--attach`
already uses. Refuses `SETTLE_TEXT_ABSENT` / `SETTLE_TEXT_AMBIGUOUS` the
same way.

**The guard: nothing is deleted before it is explained.** This is the
single most destructive write this command can make — unlike `--attach`
(adds a token) or the create path (adds a line), nothing `--remove`
deletes is recoverable from anything `settle` itself ever wrote. The
guard is inherited from the document's own stated convention: the `##
Reversed` section's own preamble already says, in prose, "Written rather
than deleted: an agreement that was turned over is part of the record,
and removing it would lose exactly what this file exists to keep."
`--remove` therefore refuses `SETTLE_NOT_REVERSED` unless the EXACT text
it would delete is already quoted, bold, under a `## Reversed` heading
somewhere in the same holder file the line itself lives in — a full quote
or one truncated with a trailing ellipsis (`...`/`…`) whose visible
prefix exactly matches `--text`'s own opening words. This forces the
write that explains WHY an agreement was turned over to exist BEFORE the
write that erases it can happen. `--remove` never authors that
explanation itself — write it by hand, or with `--reverse` (below), which
writes both in one call.

**Conflicts.** `--under`, `--supersedes` and `--witness` name nothing in
this mode (there is no new item to place, and no witness to bind onto a
line being deleted) and are refused `SETTLE_REMOVE_CONFLICT` if given
together with `--remove`, so a flag the caller bothered to type is never
silently ignored.

### `--reverse` — writing the explanation and the deletion in one call

`--remove` shipped guarded by `SETTLE_NOT_REVERSED`, correctly — but
measured after shipping it, nothing could ever satisfy that guard except
a hand edit: `settle` places `- [ ] {text}` checklist bullets, and a `##
Reversed` entry is bold-quoted prose in a different shape, so no existing
command could write one. `--reverse` closes that gap by writing the `##
Reversed` entry and performing the deletion in the SAME call:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --reverse \
  --text "the free scalar stays at its neutral and identical across arms" \
  --paragraph "Reversed because the underlying measurement changed."
```

```json
{ "status": "written", "holder": "Method/AGREED.md", "reverse": true,
  "about": null, "text": "the free scalar stays at its neutral and identical across arms",
  "under": null, "witness": null,
  "paragraph": "Reversed because the underlying measurement changed.",
  "supersedes": null, "collides": [] }
```

**The guard that makes it safe: it refuses without an explanation.** The
engine never authors the reasoning behind a reversal — that is a human's
call, not a computed fact. `--paragraph` is therefore required
(`SETTLE_PARAGRAPH_REQUIRED` if blank or omitted): an `--reverse` call
carrying no paragraph has nothing to explain with, and this mode's entire
point is writing that explanation down.

**One transaction, never two separate writes.** Both the new `##
Reversed` entry and the deleted checklist line are folded into ONE
spliced buffer, computed from the same pre-image bytes, before the single
shared compare-and-swap write at the bottom of this command ever runs.
There is no intermediate state where one edit has landed and the other
has not — both land in the one written file, or the write itself refuses
(`POSITION_HOLDER_MOVED`, the holder changed underneath it) and NEITHER
does. The entry is appended last, immediately before the section's own
position block when one exists, or at the section's own end otherwise —
never first, since a reversal explains something that just happened.

Refuses `SETTLE_ALREADY_REVERSED` if the exact text is already quoted
under `## Reversed` — this mode writes a NEW explanation together with
the deletion, and would duplicate one the document already has. In that
state the explanation already exists and only the deletion is still
pending; plain `--remove` (above) is the reachable command for exactly
that case. When the holder has no `## Reversed` heading yet, the first
reversal opens one at the end of the file (a blank line, `## Reversed`, a
blank line, then the entry); nothing above it moves. Refuses
`SETTLE_HEADING_AMBIGUOUS` when more than one `## Reversed` heading occurs in
the same holder.

**Conflicts.** `--under`, `--supersedes` and `--witness` name nothing in
this mode (the identical reasoning `--remove`'s own conflict already
gives) and are refused `SETTLE_REVERSE_CONFLICT` if given together with
`--reverse`; giving `--paragraph` in any OTHER mode is refused the same
way, since that flag feeds an entry only `--reverse` ever writes.

### `--done` — the tick this class closes

`--remove` and `--reverse` are *compositions* of verbs this file already
had: editing an agreement's text is `--reverse` (which explains why)
followed by a fresh placement; moving one between sections is `--remove`
(once explained) followed by placement under the new heading.
Ticking one had no composition at all — nothing either of those two could
do, alone or chained, ever changed a mark from `[ ]` to `[x]`. Every ticked
agreement a real target carries was typed by hand. `--done` closes that
gap:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --done \
  --text "the free scalar stays at its neutral and identical across arms"
```

```json
{ "status": "written", "holder": "Method/AGREED.md", "done": true,
  "about": null, "text": "the free scalar stays at its neutral and identical across arms",
  "under": null, "witness": "test_the_free_scalar_stays_neutral",
  "supersedes": null, "collides": [] }
```

`--text` is matched by the identical exact-equality discipline `--attach`
already uses. Refuses `SETTLE_TEXT_ABSENT` / `SETTLE_TEXT_AMBIGUOUS` the
same way.

**The guard: a tick must rest on a witness.** Refused `SETTLE_NOT_WITNESSED`
unless the located line already carries a `` `test_<id>` `` token — bind
one first with `--attach`. A tick asserts the work is done; a line nobody
can point a test at cannot assert that through this command. Refused
`SETTLE_ALREADY_DONE` if the located mark is already `x`/`X` — `--done`
never re-ticks an already-ticked line.

**An agreement no test could ever witness closes by a recorded decision.**
A scoping decision, a premise, a deferral, a design tradeoff: nothing about
them is executable, so no witness can be bound and plain `--done` refuses
them. Ask the operator whether the item is closed and why, then pass their
answer:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --done --unwitnessed --reason "<the operator's reason>" \
  --text "<the exact line text>"
```

The same one byte flips. The `settle` ledger event and the response carry
`unwitnessed: true` and `reason` beside the session; both keys are absent
from every other `settle` call. The act is never counted as witnessed:
`agreements.witness` keeps the line under `unwitnessed`, out of the
`summary` count, and names it under `witness.decided` as `{text, reason,
session, at}`. A ticked witness-less line with no such recorded act (a hand
tick) reads exactly as it always has and is named under
`witness.handTicked`; both keys appear only when non-empty, so a holder
carrying neither reads as before. Refused `SETTLE_REASON_REQUIRED` when
`--reason` is missing or blank (the reason is the operator's, never the
agent's), `SETTLE_WITNESS_PRESENT` when the located line names a witness
(that line closes through plain `--done`, which its test answers for), and
`SETTLE_UNWITNESSED_CONFLICT` when `--unwitnessed` is given with neither
`--done` nor `--under`, or `--reason` without `--unwitnessed`.
`SETTLE_ALREADY_DONE` is checked first.

**When the line does not exist yet, place it the same way.** A witness-less
agreement often has no position sequence and no discussion to bind it to, and
placing a line otherwise needs `--about`. Pass `--unwitnessed --reason` with
`--under` instead:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --under "## Ladder" --unwitnessed --reason "<the operator's reason>" \
  --text "<the agreement>"
```

It places one unticked `- [ ] <text>` line, creating the declared holder if it
is missing, with no discussion gate (the line names no witness to discuss).
The ledger event carries `about: null`, `unwitnessed: true`, `done: false`
and the reason. It closes nothing: the line stays open until the `--done
--unwitnessed` act above, and only that act is named under
`witness.decided`. Refused `SETTLE_UNWITNESSED_CONFLICT` with `--about`,
`--witness` or `--supersedes`, `SETTLE_REASON_REQUIRED` without a reason,
and `SETTLE_UNDER_REQUIRED` / `SETTLE_HEADING_ABSENT` as any placement is.
Before 0.14.0 this line had to be written by hand.

**Only the mark moves.** `--text`, any witness token the line already
carries, and every other byte in the holder file are byte-identical
afterward — the single byte inside the checklist mark's own brackets is
the only thing this writes. `--under`, `--supersedes`, `--witness` and
`--paragraph` do not apply with `--done` and are refused
`SETTLE_DONE_CONFLICT` if given, and so are `--attach`, `--remove` and
`--reverse` themselves. The discussion precondition is skipped for the
identical reason `--attach` skips it: a line `--done` matches was already
discussed and placed by a prior `settle` call.

**A tick cannot be undone, only corrected on the record.** No mode turns
`[x]` back into `[ ]`: a tick asserts that something came true, and taking it
back is a different assertion (the earlier claim was wrong), which the holder
keeps in writing, never by editing a mark. To correct a mistaken tick, run
`settle --reverse --text "<the ticked text>" --paragraph "<why it was
wrong>"` (it works on a ticked line exactly as on an open one: the line is
removed, the explanation lands under `## Reversed`, and the ledger records the
`reverse` event), then place the corrected agreement again with `discuss` and
`settle --under`, which writes it as a fresh `[ ]` line.

## `defect` — declare a forge file broken

Records that some file this forge itself ships is currently wrong — a bug in
`implementation_cli.py`, a stale claim in `SKILL.md`, anything under
`skills/`. While it stays open, `step`, `gate`, `offer`, `close`,
`settle`, `apply`, `admit` and `materialize` all refuse `FORGE_DEFECT_OPEN` for
this exact `<target>/<name>`; `probe`, `verify`, `position`, `plan`, `compose`,
`handoff`, `discuss` and `propose` stay reachable throughout. Both rosters name
every verb: a verb missing from both reads as undecided, and the two that were
missing turned out to sit on opposite sides — `materialize` refuses, `propose`
does not. `main()` also appends this
same kind of event on its own, with no `defect` call at all, the moment any
OTHER exception reaches it while dispatching a command — see SKILL.md's
"When the forge itself crashes mid-flow".

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py defect \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --file skills/proposal-implementation/scripts/implementation_cli.py \
  --detail "cmd_step ignores STEP_MALFORMED for an entry missing 'function'"
```

```json
{ "command": "defect", "target": "<repo>", "name": "<Name>",
  "file": "skills/proposal-implementation/scripts/implementation_cli.py",
  "fileSha256": "<64-char hex>", "session": "<your-session-id>",
  "at": "2026-08-27T00:00:00Z",
  "detail": "cmd_step ignores STEP_MALFORMED for an entry missing 'function'" }
```

`--file` must resolve under `FORGE_ROOT/skills/`; a path outside that
tree refuses `DEFECT_FILE_NOT_FORGE_OWNED`, checked BEFORE existence, so this
command never reports on the existence of anything outside it. A path that
does not resolve to a regular file refuses `DEFECT_FILE_ABSENT` — declaring
against an already-absent path is refused rather than recorded, because the
honest reading of a `--file` nobody can find is a typo, not a forge bug; the
genuine case ("this module is missing") is declarable against the file that
fails to find it, which exists. `--detail` is optional free text and is
omitted from the ledger event entirely, never written as `null`, when not
given. Clearing happens the moment the named file's bytes change — editing
it, even to fix the exact thing declared, clears the defect; asserting the
fix in a fresh `--detail` on unchanged bytes does not. Deleting the file
after the declaration clears it too, on the same rule: an absent file can
never again match the recorded digest, so absence is treated as the
strongest possible change, not a bypass that needs closing.

## Probe — what stands between this repository and a benchmark

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py probe \
  --target implementations/<repo> --name <Name> --revision research-concept-r05.md
```

`--revision` is optional here for the same reason it is optional on `verify`:
omit it and the newest published revision of the family the bench declares is
discovered. Everything else is required.

```json
{ "status": "ok", "nextStep": "benchmark", "comparable": true,
  "backend": { "trainable": true },
  "results": { "status": "absent" },
  "remoteExecution": { "status": "absent", "jobs": [], "services": 0,
                       "smokeReady": {} },
  "kind": "read-only" }
```

`probe` runs nothing and changes nothing — `kind` says so in the output itself,
and the exit status is `0` whatever it finds. `nextStep` is the answer and there
is exactly one of them: the ladder is ordered, so the first thing standing in
the way is the only thing reported. The full set of values `probe` can return,
and which of them have their own `SKILL.md` section, is derived rather than
transcribed here — see
`NextStepSectionCoverageTests.test_every_value_the_cli_can_return_is_accounted_for`,
which scrapes both directly from the source rather than carrying a count that
can drift out of sync with it. Most values prescribe work and each has its own
section in `SKILL.md` — `convert`, `declare-first`, `env-first`, `wiring-first`,
`poll-first`, `pilot-first`, `pilot-decisions`, `search-first`, `report-first`,
`benchmark`, `validate` and `build-first`. A few have no section:
`nothing-to-compare` and `already-benchmarked` prescribe no work at all,
`piloted`'s own rule keeps its question open rather than handing over a list
of steps, and `declined` is this flow's own answer to "the person said no" —
twice.

**Prescribing no section is not the same as publishing nothing.** Most values
publish a `resolve` question or draft (below); only the terminal states that
name no work at all — `nothing-to-compare`, `already-benchmarked` and
`declined` — publish `null`, and they say so in `PROBE_NEXT_STEPS` rather than
by omission.

Never read past the answer for a reason to skip it. A rung fires because
everything above it is already settled, so the next one down says nothing about
whether the campaign is a good idea yet.

## The remote-execution seam

The commands that send work to a worker belong to the forge's
`remote-execution` skill, not to this one: `probe` and `verify` read the ledger
and the job folders, and never submit, poll or repair anything. But a reader
told to wait, or told a ledger has drifted, needs a name to type. Three
invocations, in the shape this flow reaches them:

```bash
# a submission is out and its answer has not come back — `nextStep: "poll-first"`
python3 skills/remote-execution/scripts/remote_cli.py poll \
  --submission-id <id> --backend <backend>

# the ledger and the service disagree — `remoteExecution` reporting drift or unreliable
python3 skills/remote-execution/scripts/remote_cli.py reconcile \
  --target implementations/<repo> --entrypoint <Name>/Notebooks/<notebook>.ipynb \
  --worker <worker> --backend <backend>

# there is no job folder for the campaign about to be offered
python3 skills/remote-execution/scripts/remote_cli.py generate-job \
  --target implementations/<repo> --service <service> --job-name <job> \
  --product <Name> --commit <sha> --repo-url <url> --repo-ref <ref> \
  --clone-path src --run-module <module> --run-function <function>
```

`generate-job` is what places `tools/<service>/<job-name>/`; nothing in this
skill scaffolds that directory, and there is no template for it here.

**The flags above are the shape, not the list.** Every one of these subcommands
takes more than is shown — overrides, rehearsal flags, resolution switches — and
they are documented once, in the `remote-execution` skill that owns them. A
second copy here would be a second thing to keep in step, which is the same
defect the tables in `SKILL.md` exist to prevent. `SKILL.md`'s own subcommand
table says which reported state routes to which command; this says how the three
a reader of this flow actually reaches are typed.

## Reading `probe`

`probe` looks and reports: it runs nothing, submits nothing, and never changes
the exit status. `nextStep` is the answer; everything else is what a human needs
in order to decide what to do about the answer.

Two facts about remote execution are reported beside that answer and gate
nothing, which is exactly what makes them easy to walk past:

- **`smokeReady`** — per job folder, whether a rehearsal has already passed on
  the commit that job is pinned to. `false` does not mean the job is broken; it
  means either that nothing has been rehearsed yet, or that the rehearsal on
  record was against a different commit. Read it before offering a long run: a
  rehearsal finds cheaply what the long run would find expensively. Recording one
  belongs to the `remote-execution` skill's own CLI — `probe` never submits.
- **`staleness`** — per job folder, inside `remoteExecution.jobs`. `fresh` means
  the pinned commit still matches the declared clone paths; `drift` means the
  repository has moved and the job would clone older code than the one on disk;
  `unknown` means the question could not be answered at all, because there is no
  git history or the pinned commit is not in it. `unreadable` is a fourth verdict
  and a different problem: that job's own `run-config.json` could not be parsed,
  so staleness was never attempted and a blank cell would have read as "nothing
  wrong".

A third fact rides inside `search.costForecast` (and the benchmark's
`projectedCost`): **`contention`**. A forecast scales one recorded duration,
and concurrent runs on one machine compete for it. With `parallelism` (a
positive integer) in the record's `reduction`, the forecast echoes it and reads
`contention: "included"`: it is that run's own duration and holds at that
parallelism only. Without it, `parallelism` is `null`, `contention` is
`"unmeasured"` and `basis` says the projection is single-process; no
contention factor is supplied. A `parallelism` of another shape comes back as
`parallelismMalformed`. Before planning eight concurrent runs from a
single-process forecast, pilot at eight and record `parallelism: 8`.

The first two are not rungs on the ladder, and that is a position rather than an
oversight: the fact as computed cannot tell a repository that is not ready apart
from one that never sends work anywhere. `SKILL.md`'s Output Contract carries the
argument and states what would change it.

**A reported state that names work publishes the way out of it.** Two of them
do, beside the fact itself, in the same `{kind, question, command}` shape a
refusal's own `resolve` carries:

- **`remoteExecution.resolve`** — non-`null` exactly when the ledger reports
  `drift` or `unreliable`, on `verify` and on `probe` alike, because both read
  one function. It publishes the QUESTION rather than the command, and the
  question says why: `remote_cli reconcile` is the act, and two of its four
  required flags are values this section may not print — a worker id is a
  service account's username, which is why `workers` beside it is a count, and
  a backend name is a service name. The `discuss` command it carries does run
  unedited; paste it, answer it, and the answer lands in the record.
- **`structure.unparsableTests`** — the test files under `tests/` whose source
  could not be parsed, so nothing could be read out of them. A gap key names a
  file that is MISSING; this one names a file that is there and unreadable, and
  the difference matters because a suite that cannot be parsed is not a suite
  that passes. `[]` when every test file parses.
- **`structure.resolve`** — a list, one entry per gap key (`scaffoldGaps`,
  `objectGaps`, `harnessGaps`) that names anything, `[]` when the repository is
  fully materialized. Each entry names the exact `materialize --stage` that
  writes those files and the exact files it would write. A question again, and
  again the reason is in it: `--plan` is an approval a human gives, and a
  published command that generated its own approval would answer the gate
  rather than pass it; `--seed` is the number the scaffolded experiment draws
  from, which no skill may pick for a repository.

**`notebookPilot` is the third, and it is a join rather than a fact.**
`remoteExecution.notebookPilot` asks, per generated job, whether the notebook
that job would run is one the pilot actually walked. It reads no disk of its
own: the job's `run.notebook` comes out of the same `run-config.json` its
`staleness` came from, and the walked set is `pilotCompleteness`'s own. Three
answers and one shape — `piloted`, `unpiloted`, `not-applicable` — with every
row carrying `job`, `notebook`, `pilotRelative` and `status` whichever answer it
got. `unpiloted` means the pilot never opened that file, or that the job's path
is not one the pilot's vocabulary can express; `not-applicable` means the job
declares the callable shape and names no notebook, which is a different fact
from a comparison that came out wrong and is reported as one. `status` is `"ok"`
or `"unpiloted"` for the whole set, `unpiloted` names the jobs, and `walked`
names every notebook the pilot opened, so a mismatch can be read without
re-deriving either side. It gates nothing: read it before offering a campaign,
and say plainly which notebook is about to be run untested.

**`pilotCompleteness` is a rung, and two of them.** It answers whether the flow
the target declared has actually finished at pilot: `status: "undeclared"` when
no `__steps__` entry carries an `advances` ordinal at all (the rule does not
apply, and the ladder answers what it always did), `"incomplete"` while any step
is short, `"complete"` once none is. `incomplete` names the steps still short —
read that, not a count. Each row says why: `ran` is the step's own ledger verdict
(`null` is unmeasured, which includes a run recorded against a suite that has
since moved), `notebooks` are the files it owes, and `notebooksCurrent` is
whether all of them are executed against these sources. Existence is not
evidence — a template copied into place and an executed report look identical
until the execution counts are read.

**Every declared step counts, not the ordered subset.** A row exists for every
`__steps__` entry: the ones carrying an ordinal first and in that order, then the
rest in name order with `advances: null`. The ordinal says where a step goes, and
it never said whether the step has to run. Measured, and the reason this changed:
a repository declaring ten steps carried no ordinal on four of them, none of the
four had ever run, two of their notebooks held zero executed cells — and `probe`
answered `pilot-decisions`, which offers the remote worker. The gate was reading
six tenths of the flow and reporting on all of it.

**The notebooks a step owes come from two links the target already writes.** Its
own `produces` roots, where a root under `Notebooks/` names a notebook it renders
— the half that needs no ordinal, and therefore the half that works for the
entries above; and, when the step carries an ordinal, the operand of the sequence
item at it whenever that item's witness is a notebook. The union, never one or
the other: dropping the second would lose a check today's targets already have.

**Whether the pilot opened a notebook at all is said per step, zero included.**
A pilot is the declared flow walked with the declared notebooks, at whatever
reduced scale the target declares, so that the artefacts that will later be sent
have been executed and read first — and a step the flow ran without opening one has
not had that done for it. Every row carries `notebookCount`, and
`withoutNotebook` names the steps whose set came back empty, beside its own
`withoutNotebookNote`. It gates nothing and refuses nothing: a target may
legitimately keep its computation in a library and render nothing of its own, so
the step's verdict and the ladder's answer are exactly what they were. It is
reported because it was invisible — measured, at four declared steps in ten whose
notebooks the flow never executed, one of them the file a remote worker would have
been sent — and the count is on every row rather than only on the zeroes, so a
reader learns what the check watches before the run where it decides something.

**`unmeasurable` sits beside `incomplete`, and it is not a softer version of
it.** It names the steps that declare no `produces` roots, so nobody could look
at what they rendered. Such a step has not failed the pilot — its own run still
decides its row — and the top-level `note` says exactly what the missing
declaration costs. `incomplete` asks a reader for a run; `unmeasurable` asks for
a declaration.

While it is `"incomplete"` the answer is `pilot-first` and the offer of the
declared scale is withheld: the outputs are what anybody reads to know the agreed
thing is there, and there are none yet. Once it is `"complete"` the answer is
`pilot-decisions` until every step has been decided — one `discuss` bucket per
step, asking how the full run carries it. Both rungs fire with nothing to
compare as well: a target with no prior-work package under `src/` answers
`pilot-first` and then `pilot-decisions` while either condition holds, and
`nothing-to-compare` only after both are settled. Read `remoteExecution.necessity`
alongside those questions; it classifies job folders rather than steps, so it
informs the decisions and never makes them.

Two more fields are reported beside `nextStep`, and they are the answer to
"what do I do about it" — published by the engine rather than composed by
whoever reads the output:

- **`resolve`** — what this answer's work actually is. `{kind: "command",
  command}` where the flow can name the whole exit (`env-first` resolves to
  `implementation_cli.py env --target <t>`; run it unedited). `{kind:
  "question", question, command}` where the next act is a decision, in which
  case `command` is the runnable `discuss` invocation that opens it. `null`
  only at `nothing-to-compare`, `already-benchmarked` and `declined`, the
  three answers `PROBE_NEXT_STEPS` declares terminal. `declined` is a
  comparison the person said no to; the offer stays remembered and does not
  re-fire unless the situation it was declined against genuinely changes.

  **Wherever the flow reaches the point of running experiments, the question
  is the same one**: continue the flow toward the declared scale, or complement
  the experiments first. Four answers reach that point — `benchmark` (the
  offer to run), `validate` **reached from an absent benchmark package** (the
  acid test: the method alone, against its own declared prediction, once the
  comparison has been declined), `piloted` (a run already made below the
  scale it declared) and `search-first` (a declared search that has chosen
  nothing yet, and a search is an experiment with a scale of its own).
  `search-first` used to publish nothing at all.

  **`validate` reached from `already-benchmarked` (Unit 6b, design D23a-c) is
  the one exception**: a REPORTING state, not an offer to run, so it asks the
  repair choice instead — do the transition now, or record why it is
  deliberately deferred — never the experiment choice above. A comparison
  that has already completed already measures the method alone on the same
  data an acid test would use, so accepting never spends machine time; it
  hand-edits the benchmark declaration's own `arms` block to undeclare the
  rival, re-sealed with `materialize --authored`, and touches nothing else —
  not `Results/…`, not an executed notebook or its stamp, not a ledger event.
  See `SKILL.md`'s own `### nextStep: "validate"` section, "Two transitions,
  and they are not symmetric", for the full account of both directions
  (test → comparison reuses `build-first`'s own token with no new machinery
  at all; comparison → test is the one described here).

- **`toDiscuss`** — the question-shaped half of `resolve`, as a list, so a
  reader can treat every open question the same way whichever command reported
  it. Each entry is one directly runnable, `shlex.quote`-escaped `discuss`
  command. For `piloted` and `search-first` the question names the target/name
  pair and the DECLARED scale the protocol asks for — never the currently-
  achieved count, which climbs on every poll while the decision has not changed.
  Run it verbatim, or run `discuss` by hand. It **never gates** — the same
  non-goal as `verify`'s own `toDiscuss` above.

`wiring` and `validation` are the two draft payloads `PROBE_DRAFTS` can
publish (design D12, replacing a single `wiring: bool` flag). `wiring` is
reported at three answers: `benchmark`, where the draft is the raw material
the run offer is built from; `wiring-first`, where an arm declares
mathematics it never calls and the draft is the very thing that state is
missing; and `build-first` (design D21), when it is the comparison's own
decision that was reopened or freshly accepted. It was guarded on
`benchmark` alone, and because the `wiring-first` override runs before that
guard, the one answer naming missing wiring came back with `wiring: null`.
`validation` is reported at two answers: `validate` **reached from an absent
benchmark package** — the acid test's own draft: the method's modules with
no rival, the target's own `__levels__`, a `placement` section naming
`local`/`remote` and deciding neither, and a proposed record entry — and
`build-first`, when it is the acid test's own decision that was reopened or
freshly accepted. `build-first` never publishes both at once: exactly one of
`wiring`/`validation` is non-`null` there, by which decision routed to it
(`decisions.comparison.decision` or `decisions.validation.decision`), the
same discipline every other rung's `null`-elsewhere shape already keeps.
`validate` **reached from `already-benchmarked`** (Unit 6b, D23b) reports
`validation: null` — a REPORTING state never proposes a run, so no draft of
how to wire and run one rides beside it.

- **`walk`** — where this repository stands in its own declared flow. Read it
  when you are opening a clean repository to run the flow from the top: it
  answers *where am I*, not *what is broken*, and nothing in it is a finding.
  Each declared step reads `notWalked`, `unfinished` (a `started` ledger event
  with no terminal partner — a run that was killed, whose product is partial)
  or `walked`, beside the `rung` its position item grades at, so a step walked
  at the floor and one walked at the top are not the same answer. Each
  result-rendering artefact in the product tree inherits the state of the step
  that renders it, through that step's own `produces` roots; one claimed by
  several steps is only as walked as the least walked of them. An artefact no
  declared step renders reads `outsideTheWalk` — that is a description of the
  artefact, not an accusation: a repository legitimately carries a whole side
  axis of work its agreement does not adjudicate. `witnessed` says whether some
  position item names that artefact, as a fact and never as a verdict. No
  reason is offered for an artefact being outside the walk, because nothing a
  target declares today can state one and this skill never invents a
  declaration to fill a field.

## `propose` — the campaign proposal

Appends one `proposal` event to `.implementation/position.jsonl`, scoped to
a whole CAMPAIGN — matching `gate --unit`'s own campaign scope — never to a
single job. Names every job it covers, its intended workers, its dependency
edges (if any) and a human-authored rationale: the four facts the spec's
"One Proposal Per Campaign" requirement names.

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py propose \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --job governing-search --job ablation-a \
  --worker worker-1 --worker worker-2 \
  --depends-on ablation-a:governing-search \
  --rationale "Full-scale campaign for the accepted research concept."
```

`--job` (repeatable, at least one) is the human-declared subset of currently
discovered job folders THIS proposal authorizes — checked later, at `gate`
time, for job membership. `--worker` (repeatable, at least one) is a
declared list of intended accounts, recorded as write-only history — read by
no code path in this file. `--depends-on <job>:<dependency>` (repeatable,
optional) names one ordering edge per flag. `--rationale` is required and
non-blank, refused `EMPTY_RATIONALE` otherwise — the same discipline `gate`'s
own `--justification` already keeps.

`campaign: {commit, jobSet}` is never argv: it is a live-disk snapshot —
every job folder `_discovered_job_folders()` currently finds, and the single
commit they all currently agree on (`null` when they disagree) — re-derived
identically at `gate` time to detect drift. This is deliberately a
DIFFERENT fact from `--job`'s declared subset: `jobSet` moves the moment ANY
job folder is added or removed, regardless of which jobs this particular
proposal named.

Multi-use by design — there is no consumed marker and no
`GATE_PROPOSAL_CONSUMED`. Calling `propose` again appends a fresh event
rather than editing or replacing the last one; a bound proposal survives a
same-campaign retry (a failed job's retry re-verifies against the same
proposal, no re-propose needed) because its own staleness keys (`commit`,
`jobSet`) are structurally distinct from the authorization's own seven
(never `entrypoint`, never `positionStatus`).

## `offer` — the state-derived action menu

The fifth ledger-appending command, named after its own event kind the same
way `position`/`discuss`/`gate`/`close`/`step` already are. Records the
flow-continuation answer as a closed token (never free text) and publishes a
closed action set: one `launch` per job the identical shared rule `gate`
itself reads (`impl_availability.launch_available`) already says is
available, plus `run-step` when the recorded answer is `yes` or
`expand-contract` when it is `no`. An unavailable action is omitted
entirely — never disabled with a reason attached — and the standing
explanation is still the position sequence and the Decision Gates table, not
a per-action string.

`expand-contract`'s published `command` is a `discuss --about record
--question <text>` invocation, not a write: it carries no `--session`
(`discuss` is the one write-adjacent command that registers none), and
running it verbatim only appends a `discuss` event to
`.implementation/position.jsonl` — `AGREED.md` is never touched. This
repoints what used to publish `position --reconcile` on the same branch, a
write an agent could run believing itself still inside the "what should the
contract still add" conversation this branch is meant to open.

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py offer \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id> \
  --answer yes
```

`--answer` is required on EVERY call — never read back from a prior `offer`
event, no matter how many exist or what they contain. `OFFER_UNANSWERED`
refuses whenever `--answer` is omitted, checked first, before the revision
is even read; the refusal is identical whether the target's ledger holds no
`offer` event, one, or many. A supplied answer is always honored and always
appends a new event — it is never compared against, or deduplicated against,
any prior `offer` event's answer. Refuses `OFFER_ANSWER_NOT_A_TOKEN` when
`--answer` is given something other than `yes`/`no`, and
`REVISION_UNREADABLE` when the pinned revision cannot be read, and
`DOCUMENT_REVISION_UNREADABLE` when a declared document beyond document 0
has no readable revision of its own — no family found in its own
directory, more than one family found there (ambiguous), or a discovered
name that does not read; the detail names the index, label, directory and
cause. It does not touch a token an earlier `offer` already minted; see
`gate`'s own closing paragraph for that gap, stated in full there.

Every published `launch` action's `binding` carries a minted `authorization`
token — a digest over the engine's own re-derived binding (job, commit,
entrypoint, units, rung, revision, position status, and now the digest of
whichever campaign `proposal` event currently names this job, or `null`
when none does), never over this call's argv alone — and its own
`binding.authorization` key names the same value already appended to the
action's `command` string as `--authorization <token>`, so the next step is
to run that command exactly as printed. A token minted while no proposal
covers this job (`proposalDigest: null`) still mints and still passes
`gate`'s own authorization check; `gate` then refuses `GATE_PROPOSAL_UNKNOWN`
on the SEPARATE proposal precondition — publish one with `propose` first.

## `gate` — the launch authorization record

The second, independent precondition a non-rehearsal `submit` reads before it
may run (design's launch-authorization domain). Binds an un-forgeable
readiness measurement — a rehearsal that actually ran and was recorded, read
back through `smokeReady` — to a human-legible justification, and appends
the pair, plus one `authorization-consumed` event naming the token spent.
Prints no token of its own: nothing here can be minted by computing a digest
over the caller's own argv. `--authorization <token>` is required and must
instead name a token an earlier `offer` publish already minted — copy it
from that `launch` action's own `command` string or `binding.authorization`.

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py gate \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id> \
  --job governing-search --worker <account> \
  --justification "Rehearsal passed at the pinned commit; launching the full grid." \
  --authorization '3f9c...e21a'
```

Repeatable `--unit`, in place of `--worker`, authorizes a CAMPAIGN launch
instead — one that will spread across every healthy account via `submit
--unit ...` rather than one named account. It binds the exact ordered unit
list that later `submit --unit ...` will carry, the same derivation
`campaign_consent_token()` already uses when minting the launch's consent
token, and records `worker: null`: a campaign names no single account.
`--worker` and `--unit` are mutually exclusive.

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py gate \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id> \
  --job governing-search --unit shard-0 --unit shard-1 --unit shard-2 \
  --justification "Rehearsal passed at the pinned commit; launching the campaign." \
  --authorization '9a10...5b3c'
```

Once the authorization token itself verifies, `gate` requires a bound
campaign proposal naming this job (published by `propose`) and, when this
job classifies `optional` (`classify_remote_necessity`'s own verdict — the
recorded facts do not decide), a matching human election:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py gate \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id> \
  --job ablation-a --worker w1 \
  --justification "No declared accelerator or local budget; electing anyway." \
  --authorization '3f9c...e21a' --elect ablation-a
```

`--elect <job>` (repeatable) is argv, per invocation, never stored and
reused — the same "asked every time" discipline `--justification` already
keeps. A job with no declared `accelerator` and no `--local-budget-seconds`
classifies `optional` and needs `--elect` at every gate call; that is
intended, not a bug — it is the recorded facts saying "not decided", never
"skip it".

Refuses `EMPTY_JUSTIFICATION` on blank input, `POSITION_ABSENT`/`POSITION_STALE`
when there is nothing current to gate against, `POSITION_UNBACKED` when a step
is ticked and its witness was never measured — a blank box claims nothing and
is honest for it, a ticked one asserts a step was reached, and a launch is not
authorized against an assertion nobody checked — `POSITION_SHARDS_UNDECLARED`
when the ticked item's witness is `@shard` and nothing named where a returned
shard lands (no `distribution.shardsRoot` declared, `gate` itself carries no
`--shards` flag to override with) — a different fact from `POSITION_UNBACKED`:
this tick was never told where to look, rather than looked-at and found
silent — `NOT_READY` when no passing
rehearsal is on file for this job at its current pin, `SEQUENCE_NOT_REACHED`
when an earlier item in the sequence is still open — a launch that would skip
a rung is refused rather than authorized around it —
`GATE_WORKER_UNIT_CONFLICT`/`GATE_WORKER_REQUIRED` when `--worker` and
`--unit` are both given or neither is, six authorization codes:
`GATE_AUTHORIZATION_REQUIRED` (`--authorization` omitted — there is no
default), `GATE_AUTHORIZATION_UNKNOWN` (no ledger record vouches for the
token, or it no longer re-digests to its own recorded fields),
`GATE_AUTHORIZATION_SUPERSEDED` (a legitimate token minted before
`proposalDigest` joined the binding, re-digesting correctly under the
7-key shape that predates it — diagnostic only, refused exactly as hard as
`UNKNOWN`), `GATE_AUTHORIZATION_MISMATCH` (the record names a different job
or unit list), `GATE_AUTHORIZATION_STALE` (a bound fact — pin, entrypoint,
rung, revision, position status — has moved since minting, never merely
elapsed time), and `GATE_AUTHORIZATION_CONSUMED` (the token already
authorized one successful `gate` call; single-use, never reusable); three
proposal codes: `GATE_PROPOSAL_UNKNOWN` (the token names no campaign
proposal this ledger still vouches for), `GATE_PROPOSAL_MISMATCH` (a
genuine, current proposal exists but does not name this job),
`GATE_PROPOSAL_STALE` (the proposal's own `commit`/`jobSet` no longer
matches live disk); and two election codes: `GATE_ELECTION_REQUIRED` (this
job classifies `optional` and no `--elect` names it),
`GATE_ELECTION_MISMATCH` (`--elect` names a different job, or names this
job while it does not classify `optional`). There is deliberately no
`GATE_PROPOSAL_REQUIRED` and no `--proposal` flag — the proposal
precondition is entirely engine-derived from the authorization token's own
`proposalDigest`, never argv. A `gate` record written before this mechanism
existed carries no token and is neither migrated nor invalidated — the
requirement binds the *command*, not the record.

A later `offer` call over a changed experiment contract does not revoke an
outstanding, unconsumed token, either — `offer` no longer recomputes or
compares any contract digest at all (see `offer`'s own docstring). This is
reasoned, not executed or measured: `_AUTHORIZATION_BINDING_KEYS` carries no
contract fact, and adding one would make every token minted before this
mechanism existed re-digest to a different value — refused as
`GATE_AUTHORIZATION_UNKNOWN`, whose own message says the event was edited
after minting. That would be a true refusal under a false explanation, and
this codebase does not ship one. Only the seven facts
`GATE_AUTHORIZATION_STALE` already names can invalidate a token; a change to
the underlying contract is not one of them, and no new `gate` refusal exists
to close that gap. It is left open on purpose. `GATE_PROPOSAL_STALE` is a
separate, later check over a separate fact (the proposal's own `commit`/
`jobSet`, never `_AUTHORIZATION_BINDING_KEYS`' seven) — it does not widen
what invalidates the token itself.

## `close` — the finishing precondition

Writing the position becomes a precondition of finishing, not a courtesy:
`close` refuses while a transition has been made and not recorded, and names
which one, rather than always succeeding.

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py close \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id>
```

Checked against the position exactly as recorded, before the refresh that
follows — the identical ladder `gate` calls first
(`impl_availability.position_honest`, shared rather than reimplemented):
`POSITION_ABSENT` when no section was ever generated and the target
declares a flow, `POSITION_STALE` when
it is bound to a revision that has moved on, `POSITION_UNBACKED` when a
sequence item is ticked and its witness was never measured, `POSITION_
SHARDS_UNDECLARED` when the ticked item carries a `@shard` witness and
nothing named where a returned shard lands — neither an explicit `--shards
<dir>` at `position` nor this target's own declared `distribution.
shardsRoot` — so the tick cannot be checked at all, a different fact from
`POSITION_UNBACKED`'s "checked, and found silent", and `POSITION_DISAGREES`
when a recorded mark still contradicts its own measured evidence. Right
after that ladder, a second and independent axis: `AGREEMENT_DISAGREES`
when a ticked `AGREED.md` checklist item's own declared
`test_<id>` witness (`settle --witness`) is absent from a fully-parsed
`tests/` — the only place in the whole CLI this ever gates; `verify` and
`probe` only ever report it. Only once both checks are clean does `close`
refresh — picking up any position witness that has become measurable since
— and record the transition. A second `close` over the identical, unmoved
position reports `"not_open"` rather than appending a second event.

**A position is owed only where a flow is declared.** Every position
witness is an execution one (`@step`, `@notebook`, `@record`, `@rehearsal`,
`@shard`), so a target declaring none of `__levels__`, `__steps__`,
`__records__`, a shard root (`distribution.shardsRoot`) or a job folder
under `tools/` has nothing a sequence could honestly name — a proposal-only
target, before any experimental stage defines a ladder. There `close` does
not refuse `POSITION_ABSENT`: it checks `AGREEMENT_DISAGREES` and
`DISCUSSION_UNANSWERED` as always, skips the refresh, records the close
over an empty sequence, and its response carries `"positionOwed": false`
(the key is absent whenever a position was owed). Declare any part of a
flow and the position is owed again; an existing position block is always
held to the full ladder. `POSITION_ABSENT`'s detail names what the target
declares.

## `step` — run one declared local step, isolated

The executor for the isolation rule stated at the very top of `SKILL.md`
("Executing a notebook needs `PATH`, not just the right `python`"): a target
names one callable in its own `__steps__`, and this runs exactly that one,
as a subprocess under the target's own `.venv/bin/python`, `PATH` prefixed
by that interpreter's own directory so a notebook's kernelspec resolves it
rather than whatever `python` happens to be first on the inherited `PATH`.

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py step \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --step verification
```

## `walk` — the flow walks itself, act by act

`step` runs exactly one. `walk` runs the ones the flow still owes, in the
order the flow declares, and stops at the first act a person has to take.

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py walk \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --revision research-concept-r17.md
```

It asks `probe` what is owed, routes each step by its own declared
`placement`, and then **executes the published subcommands as subprocesses**
rather than calling their functions -- so every guard those carry applies
exactly as it does to somebody running them by hand. After each local step it
refreshes the position and records that step's product, because `step`
refuses on a dirty tree and every step dirties it with its own output; the
message names the step and narrates nothing, which is the half that stays
yours.

The subject defaults to `walk: <step>`. A target whose history is held to a
convention (a Conventional Commits hook, a CI lint) passes its own shape with
`--commit-template`, where `{step}` is the one placeholder:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py walk \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --revision research-concept-r17.md --commit-template 'chore(walk): {step}'
```

A template with no `{step}`, any other brace, or more than one line is refused
`WALK_COMMIT_TEMPLATE_MALFORMED` before anything runs: a commit nobody can
trace back to its step is worse than the mechanical default. No receipt or
ledger records the message, so changing it between walks changes nothing on
disk but the history.

It stops, rather than refusing, and says where: at a `launch`, at a `blocked`
step nobody routed, or at the first act that refused -- returning `performed`
and `stoppedAt` so the answer is what it did and what is left. It stops
rather than skipping ahead because the flow is ordered: a step that cannot
run is one whose output every later step reads.

**It has no path to `submit`.** A launch is hours of somebody's quota and is
the one act whose plan a person asked to see first, so the walk hands it over
instead of taking it.

Omit `--revision` and no position refresh runs between steps, which means an
ordered next step will refuse -- the flag is what lets a walk be more than one
step long.

Runs exactly one step per call — no flag sequences or dispatches more than
one, and this never consults `probe`'s `nextStep`. A step that declares
`advances` is refused `STEP_SEQUENCE_NOT_REACHED` while an earlier sequence
item is still unticked — and the mark it reads is the literal one in the
target's own `AGREED.md`, which a step that just ran does not update.
`position` is the only writer into that section, so `step` never re-derives
it; the refusal publishes the exact `position` refresh instead, bound to the
revision the block already names, as a command run unedited. That pair —
**run the step, commit its product, re-derive `position`, run the next
step** — is the whole loop between two ordered steps.

Every successful call publishes that loop for itself, in `next`, so it is
read where it is needed rather than remembered from here. `next[0]` is the
`git status --porcelain` listing of what this step just left in the tree:
**a step's product must be committed before the next step runs**, because
every step dirties the target and the next one refuses `DIRTY_WORKTREE`
until it is clean. The commit message is the operator's; this skill never
writes one. `next[1]`, when the product carries a readable position block,
is the exact `position` refresh, bound to the block's own revision. A
six-step flow is therefore six `step` calls, five commits and five
refreshes — not one command repeated six times. Refuses `DIRTY_WORKTREE`
before any subprocess spawns (a step mutates the target, same guard
`plan`/`apply` already call). When the ledger's latest `step` event is a
bare `started`, that refusal's published question says so: it names the
step that was killed, when it started, that what it left behind is partial
product a re-run does not resume, and it publishes `git clean -nd` — a dry
run listing exactly which untracked paths a cleanup would remove, removing
none of them. Which of them are the dead run's leftovers stays the
operator's reading; the engine never authors the removal. Also refuses `STEPS_UNDECLARED` when the target's
`__steps__` names nothing at all, `STEP_UNKNOWN` when it names something and
`--step` is not one of them, `STEP_MALFORMED` when the named entry is
missing `module` or `function`; `INTERPRETER_ABSENT` when the target has no
`.venv` yet (`env` first); and, once the subprocess itself has run,
`STEP_MODULE_MISSING` / `STEP_FUNCTION_MISSING` / `STEP_NOT_CALLABLE` when
the declared callable does not resolve inside the venv, or
`STEP_RUNNER_SILENT` when the process exited without ever writing a verdict
— died before resolution even began, so nothing here can say whether the
step ran. Those four target-side refusals each leave a `refused` terminal
event in the ledger naming the code; the forge-side refusals above them
(`FORGE_DEFECT_OPEN` through `INTERPRETER_ABSENT`) leave nothing at all,
which is what keeps "no event" meaning exactly one thing.

Every run past `INTERPRETER_ABSENT` appends a **pair** of `kind: "step"`
events to `.implementation/position.jsonl`. The first, `outcome:
"started"`, is written the instant before the subprocess spawns and carries
the step's name, its dotted callable, the interpreter path and the session —
nothing else. So the ledger's *shape* answers the question an exit code
cannot: **no event at all means this command never started** (a mis-resolved
invocation, a wrong working directory — nothing here ever ran); **a
`started` with no partner after it means it started and was killed** (a
harness timeout, a `SIGKILL`) and its product is partial; **a terminal event
means it ran and reported**. Do not read a step's success off an exit status
or off stdout: read it off this pair.

Every successful call also publishes `wrote`: what this run changed inside the
product folder, split by whether this step owns it. A `__steps__` entry names
`produces`, the list of path roots -- relative to the product folder -- that
step and only that step writes into; `step` snapshots the folder before the
spawn and again after the child reports, and answers `own` (everything changed
lies under those roots), `nothing` (the run returned and changed nothing under
them), `foreign` (it changed paths outside them) or `undeclared` (the step named
no roots, so neither reading is available). `foreign` is the one nothing else
here can see: a step that writes into a neighbouring step's product still
reports `outcome: "returned"`, still passes every check, and may change only a
field inside a file nobody opens. Files are compared by `(size, mtime)` -- every
write a filesystem records moves it, and a file touched without its bytes
changing reads as written, which is the safe direction for a guard about who
wrote where. `.implementation/` is excluded, for the reason the dirty-tree guard
excuses it.

`wrote` also carries `ignored`: which of this run's own written products,
under its declared roots, the repository's own ignore rules exclude. Answers
the question `status`/`inside`/`outside` cannot -- a path can be entirely
`own`, exactly where the step was told to write, and still never enter the
repository's history, because a rule written for what existed some earlier
day also excludes what was written today. `ignored` is always present, `[]`
when nothing is excluded; it is computed over `inside` only, since a foreign
write already gets the strongest reading this skill can give it. When
`ignored` is non-empty, `ignoredNote` carries the same, singly-defined
consequence sentence every sibling note in this file carries -- it reports
what is excluded and never repairs it, exactly as this whole reading never
gates on what it finds. The same block, minus its constant note and its
ignoredNote, is written into the terminal ledger event, so both readings
survive the process that took them.

That same pair is also the only cost figure this skill has, and `step`
publishes it: `lastRun` on every successful call carries the elapsed seconds
of the LAST completed run of the step being run, folded from its own
`started` -> terminal stamps. It is a measurement of that run and never a
budget for this one — the same step over a larger scale costs what it now
costs — and it is deliberately not an `expectedMinutes` a target declares:
a field this skill reads is a field a repository built from zero would have
to be made to ship, and nobody chose that obligation. The limit is stated in
the payload rather than implied. `status: "unmeasured"` is what a step
nobody has run yet reports, which is exactly the run whose cost surprises
somebody; a run that started and never reported measured nothing and is
skipped, so the field says the same thing the ledger's own shape does.

The terminal event carries the step's name, its dotted callable,
the interpreter path, `outcome` (`returned`/`raised`/`unknown`), exit
status, `error` (the raised exception, formatted once inside the
subprocess itself, since the step's own stdout/stderr are inherited live
rather than captured), and `suiteDigest` — `suite_digest(target)`, every
`.py` under `src/` and `tests/` plus five fixed environment manifests
(`requirements.txt`, `pyproject.toml`, `setup.cfg`, `tox.ini`,
`pytest.ini`), computed fresh at write time, unconditionally regardless of
outcome. This reverses "no digest field" only for a bare runner step with
no self-stamping artifact of its own; a notebook still recomputes
`source_digest` fresh against its own `DIGEST_MARKER` output, so a
ledger-carried copy there would still be redundant. An `@step <name>`
witness in `position`'s own sequence folds the ledger's latest event per
name (latest wins) against a live digest: `True` for a current `returned`,
`False` for a current `raised`, `unmeasured` for a stale digest, a
pre-change event with no digest at all, or no event at all — never a false
`True`/`False` over code nobody ran against.

The digest is not narrowed to the code a step executes, and that is
deliberate: a step's callable may run the suite, read a file under `tests/`
or spawn a subprocess, and the engine cannot see which. A narrower scope
would let a mark stay satisfied over an edit the step actually runs. The cost
is that any edit under `src/` or `tests/` (a test-only edit included) or to
one of the manifests makes every earlier step mark unmeasured until that
step runs again, so commit the code and the tests before the first pilot
step and run the steps last. Each unmeasured `@step` item in a position
state's `unmeasured` list carries `reason`,
which says whether the step never produced a verdict or its last run no
longer counts and gives the exact `step` command that clears it, and
`digestScope`, which states this scope. **Stated non-goal**: this does
not distinguish a fully-executed suite from one that skipped tests —
`pytest` exits 0 on skips, so `returned` grades green over a skipped suite
exactly as a notebook report already does. An unknown `--step` name is
`STEP_UNKNOWN` on this command; the identical operand named inside a
position sequence's `@step` witness is `POSITION_STEP_UNKNOWN` instead,
raised by `position` (an argument to `step` is an invocation the caller
typed; a position item's operand lives in AGREED.md, so clearing it means
editing the document or declaring the step) — `STEPS_UNDECLARED` covers
the case where `__steps__` names nothing at all, in either command,
verbatim. This never touches `gate`: it calls none of the remote-execution
loaders, and a `kind: "step"` line is invisible to
`_verify_launch_authorization`, which selects on the exact string
`"gate"`.

## `handoff` — back to the deliberation, sized by reach

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py handoff \
  --target implementations/<repo> --name <Name> --revision research-concept-r05.md
```

Every open finding is measured against the document itself: how many equations
the remedy rewrites, how much notation it adds, and how often the rest of the
text cites those equations. Nothing is judged — all three are read.

| class | condition | what happens |
| --- | --- | --- |
| `local` | one equation, no new notation, cited at most once elsewhere | `settleInline`: an agenda item for the current deliberation |
| `structural` | anything wider | `deferToOwnSession`: the reason code and the numbers behind it, for the agent to put into the reader's own language |

A deferred item says why in `deferredBecause`:

| value | meaning |
| --- | --- |
| `structural-reach` | the remedy rewrites more than one equation, adds notation, or touches an equation the text leans on |
| `remedy-text-missing` | local reach, but nobody wrote the corrected block (`remedy_block`) |
| `remedy-locus-missing` | it measures as local only because `remedy_equations` is empty, so there is no equation to resolve against |
| `prose-remedy` | the finding declares `"remedy_in_prose": True`: its remedy rewrites prose, which carries no `\tag{n}` to substitute at, so only a session of its own can decide the new wording |

Measured on this repository: three remedies are local, and the confidence one is
not — it rewrites two equations, adds three symbols, and touches Eq. (24), which
the text cites three times.

`adoption` is read from the revision rather than assumed:

| state | meaning |
| --- | --- |
| `open` | the text the remedy replaces is still there |
| `adopted` | it is gone and an expected form is present |
| `changed-unrecognized` | it is gone but nothing expected appeared — confirm by hand |
| `unknown` | the finding declares no marker |

Inference is textual, so it is built to fail toward `open`. An adopted finding
stops counting as introducing notation — in `admit`'s `introducesNotation` and
in `verify`'s `audit.compatibility` alike: the deliberation settled that when it
published. Every reader (`admit`, `verify`'s audit, `migration`, `handoff`)
reads adoption from the same text: the document(s) the finding names, or
document 0 when it names none.

### After adoption: the remedy becomes an invariant

`audit.migration` closes the loop. Once the deliberation publishes a remedy it
is no longer a correction under consideration — it is what the proposal says,
and it belongs where every other claim of the proposal lives.

Each finding declares `becomes_invariant`. When its adoption reads `adopted`,
three things must have happened:

```
test_remedy_<id>            retired
test_<becomes_invariant>    present in the invariant suite
__provenance__["invariants"] declares <becomes_invariant> in the module
```

`audit.status` stays `incomplete` until all three hold. The skill checks the
move; writing it is the agent's work, as with any other code. Leaving the
remedy in place would keep reporting a defect the revision no longer has.

Once all three hold the finding is in its terminal state: `audit.adopted` names
it with the revision and the expected form that confirmed it, it stays in
`tests/findings.py` with its `test_finding_<id>` as evidence, and it no longer
holds `audit.status` below `ok`.

## Guard codes

A guard's failure is silent by definition: when one stops working, every happy
path stays green. They are exercised as a suite, each driven to its failure
state, alongside the scenarios — not verified by hand once.



| Code | Meaning |
| --- | --- |
| `OUTSIDE_WORKSPACE` | Target is not under `implementations/`. Clone it there. |
| `NOT_A_GIT_REPO` | No `.git`. Migration needs a revertible commit. |
| `DIRTY_WORKTREE` | Uncommitted or untracked changes. Commit or stash first. |
| `FORGE_INTERPRETER` | The CLI is running from a forge venv. Use system `python3`. |
| `PLAN_STALE` | The repository changed after approval — a rename, a move, a directory **or a reference update**. Re-plan, re-approve. |
| `MALFORMED_FINDINGS` | `tests/findings.py` exists but cannot be read as a list of mappings each carrying an `id`. Reading it as empty would answer `audit: none`, which is what a repository that declares no finding answers. |
| `NO_FINDINGS` | `admit` was run while `tests/findings.py` declares no finding. Write the findings, or, when the audit found nothing, record that with `admit --no-findings`. |
| `FINDINGS_DECLARED` | `admit --no-findings` was run while `tests/findings.py` declares findings. The flag records an empty audit only; drop it to rule on the findings. |
| `DESTINATION_CONFLICT` | A destination is taken, or two sources target one path. For `materialize --stage`, a destination appeared between the destination set's computation and the write; the whole stage refuses before any byte lands. |
| `UNCLASSIFIED_FILES` | No rule covers some files. Ask where they belong. |
| `APPLY_ABORTED` | Something failed mid-migration, or mid-`materialize`. Nothing was committed/written and the tree was restored; re-run `plan`. |
| `MATERIALIZE_MODE_REQUIRED` | `materialize` needs exactly one of `--stage`/`--authored`/`--adopt`; none was given. |
| `MATERIALIZE_MODE_CONFLICT` | Two or more of `--stage`/`--authored`/`--adopt` were given together; the three modes are mutually exclusive. |
| `PLAN_REQUIRED` | `materialize --stage` needs `--plan <approved plan JSON>`. |
| `MODULE_STAGE_MISMATCH` | `materialize --module` was given with a mode other than `--stage objects`, the only one that writes a module. |
| `MODULE_NAME_INVALID` | `materialize --module` names something that cannot be the module's file: not an importable identifier, a keyword, `__init__`, or a file the kit owns (`report_digest`). |
| `SEED_REQUIRED` | `materialize --stage scaffold` needs `--seed`, substituted into `{{SEED}}`. |
| `STAGE_CANNOT_ANSWER` | A scaffold-stage `.py` destination still fails `ast.parse` after `{{PKG}}`/`{{SEED}}` substitution — its remaining token answers a later step. Names the file. Never raised by `objects`/`harness`: their three destinations are either written with tokens deliberately left standing (`objects`) or already parse cleanly (`harness`'s two `.py` files). |
| `OBJECT_MAP_NOT_APPROVED` | `materialize --stage objects` ran before step 8's `revision`/`premises` were recorded in `src/<Package>/__init__.py`'s `__implementation__`. The detail names whichever of the two is still blank, so a half-written map does not send you back to re-read the half that is already right. Get that declaration approved and written first. |
| `OBJECT_MAP_AT_OLD_HOME` | `materialize --stage objects` ran on a target scaffolded before this change: `src/<Package>_Benchmark/__init__.py` still binds `revision`/`premises` there, and `src/<Package>/__init__.py`'s `__implementation__` is blank. Distinct from `OBJECT_MAP_NOT_APPROVED` — this target once declared, at the old home — and names both locations. Follow SKILL.md step 8's migration procedure: scaffold, hand-move the literals (including any this skill has no reader for), `materialize --authored`, delete the orphaned seal copy, re-execute notebooks. |
| `SCAFFOLD_DRIFT` | (`verify`, reported in `structure.scaffoldDrift`, never raised) A receipt-recorded scaffold destination's on-disk bytes no longer match its `writtenSha256`. For a notebook (`.ipynb`), its source content (each cell's type and source, in order) is compared as well, against the entry's `writtenSourceSha256`: executing it in place, which rewrites outputs, execution counts and kernel metadata, is not drift, and a changed cell source or cell type is. An entry written by an earlier release has no `writtenSourceSha256`; for an engine-written entry the source content is rebuilt from the kit and trusted only when it hashes to `writtenSha256`, and any other entry is compared on full bytes alone until its next `--authored`. Release the seal with `materialize --authored <path>` after declaring the edit. `objects`/`harness` destinations get the identical check under `structure.objectDrift`/`structure.harnessDrift`. |
| `UNRECORDED_SCAFFOLD` | (`verify`, reported in `structure.unrecordedScaffold`, never raised) A scaffold destination exists on disk with no receipt entry — most often because the target was scaffolded before this command existed. Remedy: `materialize --adopt <path>`, one path at a time, deliberately. **This degrades the guarantee**: adoption records who is responsible for the bytes, never that they came from the kit — the record names who wrote them, not that the engine owns them. `objects`/`harness` destinations get the identical check under `structure.unrecordedObjects`/`structure.unrecordedHarness`. |
| `NOT_A_KIT_DESTINATION` | `materialize --authored`/`--adopt` named a path outside `all_kit_destinations` — the scaffold, objects and harness destination lists, concatenated (the paths listed under "The sealed set"); `--authored` also accepts a file the objects stage recorded under a `--module` name. The detail lists every accepted path. The receipt is not a general-purpose ledger. |
| `MATERIALIZE_PATH_ABSENT` | `materialize --authored`/`--adopt` named a path with no bytes on disk. |
| `NO_RECEIPT_ENTRY` | `materialize --authored <path>` named a path the engine never wrote. There is no seal to release; use `--adopt`. |
| `ALREADY_RECORDED` | `materialize --adopt <path>` named a path the receipt already carries. Adoption is not a re-seal; use `--authored`. |

### Every refusal says how it is cleared

Every refusal leaves the CLI through one handler and prints the same JSON:
`status`, `code`, `detail`, exit `2`, nothing appended anywhere. Refusals a call
to one of the ten **gating** commands can reach — `apply`, `admit`, `gate`,
`offer`, `close`, `step`, `settle`, `materialize`, `position`, `agree` — carry
one more thing. `agree` is on that roster but not on this skill's command line:
it is registered only for a profile declaring more than one document, and this
one declares a single document. Its codes are reachable here in the sense the
roster means — derivable from a module-level function — and unreachable in the
sense a reader cares about, which is that no invocation of this skill raises
them. Which refusals carry the extra key is itself the answer to a question:

> Can the caller clear this by changing the invocation alone, without touching
> the repository?

**Yes — an invocation defect.** The detail already names the flag, the token or
the mutual exclusion. Fifty-nine codes, and nothing is published beside them:
`SETTLE_STDIN_CONFLICT`, `OFFER_ANSWER_NOT_A_TOKEN`, `MATERIALIZE_MODE_REQUIRED`,
`NOT_A_GIT_REPO`, `GATE_ELECTION_REQUIRED` and the rest. Retype the call.

**No — a work state.** Somebody has to act on the repository, so the payload
carries a `resolve` key saying what. Seventy-two codes, including
`POSITION_DISAGREES`, `AGREEMENT_DISAGREES`, `POSITION_STALE`, `DIRTY_WORKTREE`,
`GATE_AUTHORIZATION_CONSUMED`, `STEP_MODULE_MISSING`,
`POSITION_RUNG_SKIPPED`, `POSITION_STEP_UNKNOWN`, `STEPS_UNDECLARED`,
`POSITION_RECORD_MALFORMED` and `NOT_READY`:

```json
{ "status": "refused", "code": "POSITION_STALE",
  "detail": "the position section is bound to a revision whose bytes no longer match; ...",
  "resolve": { "kind": "command",
               "command": "/usr/bin/python3 /abs/path/to/implementation_cli.py position --target /abs/path/to/implementations/repo --name Name --session s1 --revision r7.md" } }
```

Every published command is runnable **verbatim, from any directory**: it begins with the absolute path of the interpreter running this CLI and the absolute path of the CLI itself, both `shlex.quote`d, and every embedded path is absolute too. That is not decoration — the script ships mode 644 with no execute bit, so a bare relative `implementation_cli.py …` was runnable only from one directory, and a shell that answers `command not found` can hand a harness that text on stdout with exit status 0. Do not shorten a published command before pasting it.

`resolve.kind` is `command` when the engine can name the whole exit — run it
unedited — and `question` when the next act is a decision nobody but a human
can take, in which case `resolve.command` is the runnable `discuss` invocation
that opens it and `resolve.question` is the text it will ask.

`POSITION_DISAGREES` — a ticked item whose own witness contradicts the mark —
resolves to re-executing the verification notebook under the target's own venv
with that venv's `bin` on `PATH`, then re-running `position` to rebind. The
`PATH` prefix is not decoration; see
[Executing a notebook needs `PATH`](../SKILL.md#executing-a-notebook-needs-path-not-just-the-right-python).

The roster lives in `implementation_cli.py` as `GATING_REFUSALS`, and the suite
derives the gating commands' refusal codes from their own source: **a refusal
added to a gating command fails the tests until it has been classified.** No
code reaches a reader as a bare word again.

`DESTINATION_CONFLICT` also covers a rename whose destination already exists.
That case is not cosmetic: `git mv A B` with `B` present does not rename, it
moves `A` *inside* `B`, which silently produces `<Name>/Images/Results/...`.

`apply` is all-or-nothing. The tree is verified clean before any mutation, so a
failure discards the partial work and restores exactly the reviewed starting
point instead of leaving a half-migrated repository.
