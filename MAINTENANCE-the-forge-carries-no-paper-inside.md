# The forge carries no paper inside

Maintenance document. Written 2026-09-20, with everything measured that day
against `main`. Numbers age: **re-measure them before using them**, with the
commands further down.

---

## The rule

`.claude/skills/` is a paper forge. It serves to write **any** paper. Nothing
specific to the paper being written today may live in there: not a block id,
not a section title, not a document name, not the id of an ingested paper, not
a word of the topic, not the pattern revisions are numbered with.

What belongs to a paper lives in the **designated spaces** — `proposals/`,
`experiments/`, `guidance/`, `paper/` — all of which are outside git except for
their `.gitkeep`. The forge reads them; it does not name them.

---

## The needle analogy, which is what this is about

You take the car in because the fuel gauge does not work. The mechanic fixes
it, but to prove it works **glues the needle at "half tank"** — because with
the needle loose the dashboard threw an error and the job could not be closed.

The gauge now works. And the tank lies to you forever.

That is exactly what happens when a skill demands something and provides no
way to answer it. Someone plugs the hole with an invented value so the machine
keeps running, and that value ends up looking like a decision.

**Two different defects, and it pays not to mix them:**

| | **the needle** | **the drawer** |
|---|---|---|
| what happened | someone **decided** something about the paper to unblock a machine | that got stored in a file **that is distributed** |
| the question | who decided? | where does it live? |
| how it is fixed | remove it, so the skill asks when used | move it to the paper's copy |

Moving the file **does not un-invent the decision**. If an agent derived a
binding by reading prose, taking it to a private place removes it from what is
distributed and leaves it, all the same, a decision a machine made.

---

## The four pieces any declaration must have

They came from comparing two things that already exist and work differently:
a binding —recorded with a verb— and a root marker —which someone wrote from
outside—.

```
1. SHOWS     the state appears in the position report, before hitting it
2. ASKS      the refusal names the exact command and reads the disk
             to say what it sees
3. VALIDATES at write time, with the person watching — not three steps later,
             in another command, with an unrelated message
4. SEALS     an edit made from outside is not read as a decision
```

If 3 is missing, a wrong value gets in and is discovered far away. If 2 is
missing, the refusal is true and useless. If 1 is missing, a new session does
not know where it stands. If 4 is missing, an unreviewed edit is
indistinguishable from a decision taken.

**About 4, state it at its real strength.** The seal that exists is
self-consistency, not cryptography: there is no secret, and whoever reproduces
the convention can edit and recompute the digest. It defends against a
**careless** edit, never against a **deliberate** one. Promising more than the
mechanism gives is worse than the hole. Keeping that true is a **test**
(`paper_marker.SEAL_STRENGTH` is a single constant, and a test requires every
surface that quotes it to match byte for byte), not a promise that someone
will review it.

---

## State measured on 2026-09-20

### In the skills

```
proposal-deliberation        33
proposal-implementation      18
experimental-deliberation     9
paper-writing                 1   ← an example list in prose
the other five                0
```

`paper-writing` was cleaned during this session. The three sibling skills
never went through this.

**And it is not only file names in examples.** The worst:

```
proposal-deliberation/profile.ts:44        stem: "research-concept"
```

---

## The distinction this audit needs before anything else

**Not every proper name inside the forge is a leak.** The forge has its own
architecture —folders it defines, versions and requires— and pointing at those
folders by name is correct. It is the architecture, not the product.

```
forge structure                 a paper's content
────────────────────────        ──────────────────────
guidance/data-paper             CREDA
guidance/paper-guide            research-concept
guidance/reference-papers       s41597-026-06758-7
proposals/  experiments/        "fixed CREDA base"
implementations/
```

The left column travels with `.gitkeep` to any clone and is empty of content.
The right column is someone's paper. A skill that names the left describes its
own scaffolding; one that names the right carries a paper inside.

**The test:** *"if someone else clones the forge to write a completely
different paper, does this name help them or get in their way?"*

- `guidance/data-paper` → it helps. It is where **their** data paper goes.
- `research-concept` → it gets in the way. It is the lineage of someone else's
  paper.

**This already produced a false positive, and an expensive one.** Without this
distinction, `guidance/data-paper` was read as a leak and replaced in
`paper-writing/SKILL.md` with `evidence-source` — a folder **that exists
nowhere in the repository**. And prose that said precisely *"`guidance/
data-paper/` existed on this disk and had no `.gitkeep`"* became *"the
evidence-classified folder of this repository"*. The documentation was made
**less accurate** to dodge a name that was not a leak.

> An audit that does not separate the architecture from the product does not
> give false negatives: it gives **false positives**, and each one changes
> something that was right into something invented.

### In the tests

```
513 occurrences in 54 files
```

Almost all in the `proposal-deliberation` suites. They are real names used as
test data: `research-concept-r01.md` and relatives.

---

## The three cases, which are fixed differently

**Case 1 — `profile.ts`.** It has a written defense next to it: *"this profile
is now the only place that names them, and the core reads them from there."*
The engine is generic and the profile configures. The problem is not the
pattern: it is that **there is a single `profile.ts` per skill and it is
distributed**. The day you start a second paper, you have to edit the forge —
when the right model is to fill a designated space.

**Case 2 — `usage.md`.** Usage recipes with your names. It breaks nothing: it
teaches badly. Someone clones to write about something else and every example
shows them your document. It is fixed with invented names.

**Case 3 — `SKILL.md`.** The doctrine requires, by name, a folder of yours. A
paper that organizes its evidence differently cannot comply with that rule: it
is not missing the material, it is missing your folder name. **It cannot be
separated from case 1**, because the prose describes the code.

---

## The prompt, to run skill by skill

Run **one per skill**, never a single one for all of them: one skill's finding
must not make another read as dirty, and a wide scope invites "fixing in
passing" things nobody reviewed.

> Audit **a single skill**, `<NAME>`, under `.claude/skills/<NAME>/`, plus the
> suites that belong to it under `tests/`. Only that one. If you find something
> in another skill, note it and move on: do not touch it.
>
> **Derive the product vocabulary from the disk, never from a list.** The
> top-level names under `proposals/`, `experiments/`, `implementations/` and
> `guidance/`. Those folders are in `.gitignore`, so `fd` and `rg` need
> `-I -H` or you will conclude they are empty — that mistake was made six
> times in this repo.
>
> Discard collisions with common English (`data`, `paper`, `method`,
> `computation`): a target repository having a word does not make it a product
> name. A method name, a document stem or a paper id are.
>
> **For each occurrence, classify which of the three cases it is** —
> configuration constant, manual example, or doctrine— and **measure whether it
> is enforced in code or only written**. A doctrine that describes what the
> engine really does is true: changing its prose without changing the engine
> turns it into a lie, and that is a worse defect than the original.
>
> Then ask what really matters, which is not the leak but the needle:
>
> - Is there any place where the skill **requires** a declaration and **has no
>   verb that writes it**? If there is, someone is writing it from outside and
>   the skill does not validate, does not seal and does not show that it is
>   missing.
> - Is any decision about the paper taken by an agent reading prose, instead of
>   by the person using the skill?
> - Is the state of each designated space **visible** when asking where we
>   stand, or does it only appear when something collides?
>
> **Report, do not repair.** For each finding: the file and line, which of the
> three cases, whether it is enforced in code, and which of the four pieces is
> missing. If a premise you were given turns out false when measured, say so —
> it is worth more than a plan built on top of it.
>
> Close with the exact commands you ran and their results, so someone else can
> repeat them without taking your word for it.

---

## How to re-measure

```bash
# product vocabulary, derived from the disk
fd -I -H -t d . proposals experiments implementations guidance --max-depth 1
fd -I -H -t f . proposals --max-depth 1

# leak per skill
for d in .claude/skills/*/; do
  s=$(basename "$d"); [ "${s:0:1}" = "_" ] && continue
  n=$(rg -c -w '<words derived above>' "$d" 2>/dev/null \
      | awk -F: '{x+=$2} END{print x+0}')
  [ "$n" != "0" ] && printf '  %-30s %s\n' "$s" "$n"
done

# the guard that already exists, and its blind spot
cd tests && ../.venv/bin/python -m unittest \
  test_proposal_implementation.ForgeVocabularyDerivedGuardTests
```

**The guard's blind spot, which matters:** it derives its list of forbidden
words by reading **only** `implementations/`. The names that live in
`proposals/` and `guidance/` were invisible to it until it was widened. That is
why fourteen lines made it into distributed contracts with the suite green. If
you find leaks again that the guard does not see, **check where it derives its
list from before the leak itself**.

And another blind spot of its own: **it inspects the tests' comments and
docstrings, never the code literals.** It sees a forbidden word in a comment;
the same word as the data of an assertion, it does not.

---

## How this audit can come out clean without being so

Three ways of lying unintentionally, all three seen in a single day of work.

**An artifact can assert something the code does not do.** Four documents
—two designs, a file table and a ticked task— asserted behaviours that did not
exist. **All four were found by a later change going to rely on them. None was
found by its own verification.**

The cause is always the same: a document does not execute. The intent is
written, it is not implemented, and nobody notices because nothing runs it.

> **Rule:** do not inherit any claim from a previous artifact without
> measuring it again. If you are going to rely on something working, run it.

**A task can be ticked and half done.** A task said *"…echoed by every
corpus-reading verb"*, was marked `[x]`, and passed verify and archive. The
field existed on the object, the tests that consumed it passed, and **no verb
printed it**. Nobody ran the three verbs to look at the output.

> **Rule:** the proof that something is visible is **running the verb and
> reading what it prints**. Asserting that a field exists on an object is
> exactly the test that let that false tick through.

**The audit report can repeat what it was told.** A verifier that summarizes
the implementer's report verifies nothing.

> **Rule:** demand the exact commands and their outputs. And for mutations,
> that they were **run**, not read: a described mutation and an executed one
> read the same in a report.

---

## Operational traps, for whoever runs the sweep

None is about the code; each one cost a lost run or a false diagnosis.

- **`fd` and `rg` respect `.gitignore`.** This repo ignores `implementations/*`,
  `proposals/`, `experiments/`, `paper/*` and `guidance/*/*`. Without `-I -H`
  you will conclude they are empty. It happened six times.
- **The full suite does not fit in a single run.** It takes longer than the
  foreground limit, and in the background memory kills it. It goes in batches,
  **sequential, never in parallel** — two batches at once step on each other in
  `implementations/` and produce a failure that does not exist.
- **A `test_proposal_implementation` run cut off halfway leaves an orphan
  directory** `implementations/_smokebox_*` that turns the next one red. Delete
  it and run again before recording a number.
- **A mutation of the same size can reuse the old `.pyc`**, so the mutated code
  never runs and the lock reads alive while dead. Purge the bytecode.
- **`git diff --stat` does not prove a mutation ran** on an unversioned file:
  it shows nothing. Assert the anchor's count.
- **Agents finish and do not always commit.** Three units in one day reported
  done with the work loose in the tree, and it had to be recovered by hand.
  Check `git status` before believing a unit closed.
- **Counting engine lines means counting `scripts/`**, not the skill folder.
  Including `SKILL.md` in the count inflates the number — it happened to me,
  and I reported 323 where there were 289.

---

## The mould, which is already built and shipped

The change `the-skill-writes-the-declaration-it-demands` is archived under
`openspec/changes/archive/2026-09-20-…` and **already runs**. It implements the
four pieces for the two markers of `paper-writing`. What follows is measured
against the shipped code, not against its design.

### The verb

```
paper_cli.py mark revisions --root <root> --revision-prefix <p> --ordinal-digits <n> [--unsealed]
paper_cli.py mark class     --folder <folder> --class <class>               [--unsealed]
```

One verb, two modes, one per marker type. Its own root, not a mode hanging off
another verb that writes to another file.

### The four pieces, as they turned out

**SHOWS.** The position report carries the state of each designated space,
with **a single vocabulary** in both halves:

```
proposals        declared-unsealed
experiments      undeclared          ← visible before hitting it
implementation   n/a                 ← it is a repository, it takes no declaration
data-paper       declared-unsealed
```

`n/a` and `undeclared` are not the same: one does not apply, the other is
missing. If they are mixed, someone will try to declare something that takes
no declaration.

**ASKS.** The refusal names the exact command and reads the disk to say what it
sees. The two places that raise it share **a single constructor**, so the
identity of the message is structural and not the coincidence of a copied
text.

**VALIDATES at write time.** Declaring three digits while holding two-digit
files is rejected on the spot, with the person watching. Before, it got in and
surfaced much later, in another command, with an unrelated message.

**SEALS.** A single module owns the seal — not two ideas of what sealing
means. And it is verified **inside the readers**, never in the report: if it
were verified when reporting it would be the tenth guard in this repo reachable
only from a read-only verb. Its mutations run through `write` and `validate`.

### The migration property, which must be preserved

**The old keeps being read.** The five markers that existed before the seal
—`proposals/` and the four folders of `guidance/`— report `declared-unsealed`
and break nothing. A change that forces everything to be re-declared stalls
the paper.

### The revert mode, which is less obvious than it looks

`--unsealed` writes the grammar from before the seal. It is needed because
**both readers reject an unknown key**: if someone reverts the change without
more, the sealed markers become **unreadable**, not merely unsealed. The
revert is done by running the verb while the code still exists, never with an
editor.

---

## When the three siblings are tackled

That is the mould, and the order matters: **the `profile.ts` stops naming,
there is a place to declare it, and there is a verb that writes it — all three
together.**

If the values are moved without building the verb, it repeats the lock without
a key that was already built twice in this repository and had to be corrected
afterwards in both cases.

---

## What this document does not cover

- What to do with `profile.ts` as a concept: whether a single sanctioned place
  where a skill names a paper is acceptable or not is the owner's decision, not
  a defect to repair on one's own initiative.
- The `proposal-deliberation` suites (513 occurrences) are the largest volume
  and the most mechanical work; they are best measured separately from the
  skills.
- There is a test in `remote-execution` that fails only when it runs in the
  same process as fourteen other modules, and passes in isolation. It is an
  isolation artifact, not a leak, but it shows up in sweeps and is worth
  knowing about.
