---
name: experiment-diagrams
description: "Trigger: a product's proof of concept (`AGREED.md`) or full experiments (`Experimental_AGREED.md`) approval is settled and the operator must verify it in the Experimentos panel. Draws one TikZ diagram per approval -- `poc` or `experiments` -- that states the experiment's single scientific claim along one reading spine, compiles it to PDF and PNG, and reviews the picture against a fixed design discipline, grayscale included. Verbs: `derive` drafts the spec from the product's evidence, `render` writes .tex/.pdf/.png, `status` reports what exists and its validation (`absent`, `pending`, `validated`, `stale`) and how it was validated, `validate` records the operator's approval given in the agent chat. Never runs an experiment, never edits the approval, never validates a diagram on its own initiative: the operator does, in the dashboard or by approving it explicitly in the conversation."
---

# Experiment diagrams

Two figures per product folder, each drawn when its approval lands:

| Kind | Drawn when | Summarises |
| --- | --- | --- |
| `poc` | `<Name>/AGREED.md` exists (proof of concept approved) | the pilot ladder: toy data, the steps, the evidence it leaves |
| `experiments` | `<Name>/Experimental_AGREED.md` exists (full experiments approved) | the full protocol: data, the run, the tests, one evidence frame per experiment |

The command center's Experimentos panel shows each PNG beside its product so
the operator can check that the figure says what was agreed, and validate it
there with **Validar diagrama**. The operator can also validate it in the
conversation with an agent (Claude Code, OpenCode, Pi or the dashboard's CLI
assistant): the agent shows the PNG, the operator approves that diagram
explicitly, and the agent runs `validate` with the operator's words verbatim
and the PNG's SHA-256. Both routes write the same
`<Name>/diagrams/<kind>.validated.json`, which holds the PNG's SHA-256
(`validate` adds `"via": "chat"` and the `statement`; a record without `via`
came from the dashboard): `remote-execution submit` (rehearsal included)
refuses `DIAGRAM_NOT_VALIDATED` while an approved kind's diagram reads anything
but `validated`, and `render` drops the record, so a diagram drawn again is
validated again, whichever way it was validated before. The panel says how
each validated diagram was validated ("validado por chat", "validado en el
tablero"). The panel's
**Generar diagrama** / **Regenerar diagrama** buttons run `derive` and `render`
in the dashboard's CLI assistant; this skill is the same step from an agent.
Every diagram not yet validated is also listed at the top of the tab, under
**Antes de lanzar**, linked to its product; the same notice asks for a server
restart when the dashboard started under an older release than the workspace's.

## Usage

```
python skills/experiment-diagrams/scripts/diagram_cli.py derive --target implementations/<repo> --name <Name> --kind poc|experiments [--force]
python skills/experiment-diagrams/scripts/diagram_cli.py render --spec implementations/<repo>/<Name>/diagrams/<kind>.json
python skills/experiment-diagrams/scripts/diagram_cli.py status --target implementations/<repo> --name <Name>
python skills/experiment-diagrams/scripts/diagram_cli.py validate --target implementations/<repo> --name <Name> --kind poc|experiments --png-sha256 <hex> --operator-statement "<the operator's words, verbatim>"
```

`status` reports, per kind, `validation` and `provenance`: `null` unless the
diagram reads `validated`, otherwise `{"via": "chat"|"dashboard",
"validatedAt": ..., "statement": ...}` (`statement` is `null` for the
dashboard).

## Validating from the conversation

Run `validate` only after the operator explicitly approves **that** diagram
(`poc` or `experiments`, of that product) in the current conversation:

1. Show the operator the current `diagrams/<kind>.png` (read the image) and
   compute its SHA-256 (`shasum -a 256` / `sha256sum`) at that moment.
2. Wait for the operator's explicit approval of that diagram. Silence, an
   approval of something else (the protocol, a launch, another diagram) or
   your own judgement that it looks right is not an approval.
3. Run `validate` with `--png-sha256` set to the hash of the PNG you showed
   (the full hex, or a prefix of at least 12 characters) and
   `--operator-statement` set to the operator's words, verbatim.

It refuses, writing nothing, when the hash does not match the current PNG
(the diagram was drawn again after you showed it: show the new one and ask
again), when the statement is empty, when the PNG or spec is missing, or when
the kind's approval marker is absent. Never validate on your own initiative.

`$ARGUMENTS` names the kind (`poc` or `experiments`) and, when more than one
product exists, the product (`<repo>/<Name>`). `--target` accepts the clone's
path or its bare `<repo>` name under `implementations/`; the product folder is
`<target>/<Name>/`, the same convention the implementation skills use.

Files, all inside the product folder: `diagrams/<kind>.json` (the spec),
`diagrams/<kind>.tex`, `diagrams/<kind>.pdf`, `diagrams/<kind>.png`.

Every command prints one JSON object. Refusals carry `"ok": false`, an
`error` code and a `message`, and exit non-zero:

| Code | Meaning | What to do |
| --- | --- | --- |
| `APPROVAL_ABSENT` | the kind's approval marker is missing | wait for the approval; never write the marker yourself |
| `PRODUCT_ABSENT` | no `<target>/<Name>/` folder | check the repo and product names |
| `DIAGRAMS_OUTSIDE_PRODUCT` | `<Name>/diagrams` is a link or resolves outside the product | replace the link with a real folder inside the product |
| `SPEC_INVALID` | the spec breaks a rule; the message names the field | fix that field (Corrector) |
| `TEX_TOOLCHAIN_ABSENT` | no `latexmk`, `pdflatex` or `lualatex` on PATH or in the usual TeX folders | install TeX Live / MacTeX; the `.tex` is already written |
| `TEX_COMPILE_FAILED` | TeX ran and failed; the message carries the log tail | usually an unusual character in a label |
| `RASTER_TOOLCHAIN_ABSENT` | none of `pdftoppm`, `pdftocairo`, `gs`, `sips` produced a PNG | install poppler-utils or Ghostscript; the `.pdf` is kept |
| `SPEC_ABSENT` | `validate`: `diagrams/<kind>.json` does not exist | draw the diagram first (`derive`, `render`) |
| `DIAGRAM_ABSENT` | `validate`: `diagrams/<kind>.png` has not been drawn | run `render` |
| `PNG_HASH_INVALID` | `validate`: `--png-sha256` is not hex or shorter than 12 characters | pass the SHA-256 of the PNG you showed |
| `PNG_HASH_MISMATCH` | `validate`: the current PNG is not the one the operator saw | show the current PNG and ask the operator again |
| `STATEMENT_EMPTY` | `validate`: `--operator-statement` is blank | pass the operator's approval, verbatim |
| `USAGE` | a required option is missing or a value is not accepted | fix the command line |

The toolchain is found through `PATH` first and then the folders TeX
distributions use on macOS (`/Library/TeX/texbin`), Linux and WSL
(`/usr/bin`, `/usr/local/texlive/<year>/bin/<arch>`, `~/texlive/...`). TeX
runs with shell escape disabled and file access limited to the diagram folder.

## Four roles, one correction round

Play each role in turn. Do not skip the review because the render succeeded.

1. **Designer** -- run `derive`, then read the drafted spec against the
   approval marker and the protocol it names (`proposals/` for the PoC,
   `experiments/` for the full run). Rewrite it until it holds:
   - `claim`: the one scientific sentence the figure must make a reader
     believe. Everything in the figure serves it; anything that does not
     goes.
   - `nodes`: each with an `id`, a short sentence-case `label` and a `role`
     (below), placed on the `spine` (the reading path, left to right, 2 to 7
     nodes), the `evidence` row (below) or the `context` row (above).
     `under`/`near` pin a row node beneath or above a spine node.
   - `focal`: the id of the one node where the claim is decided -- the
     mechanism the experiment exists to test.
   - `edges`: `from`, `to`, `semantics` and `prominence` (below), optional
     `label` of at most 24 characters.
2. **Drawer** -- run `render`. The script computes the layout and applies the
   style library; never hand-edit the `.tex`, change the spec instead.
3. **Reviewer** -- open the PNG (read the image) and check it against the
   rules below, one by one. Check grayscale explicitly: imagine or produce a
   gray copy (`pdftoppm -gray`) and confirm the focal node and the primary
   path still stand out without hue. Write down each rule that fails.
4. **Corrector** -- make the smallest spec change that fixes each failure
   (shorter label, a node moved to a row, one edge demoted to secondary),
   render again and review once more. **At most one correction round**: if
   something still fails, report it to the operator with the PNG path rather
   than looping.

## The design discipline

These rules restate, in this skill's own words, the figure-design philosophy
of **Sivia** (github.com/exsinger-hub/Sivia, by exsinger-hub, released under
a non-commercial license). Credit for the ideas is Sivia's; no text,
template or asset of Sivia is copied here, and the TikZ library in
`scripts/diagram_cli.py` is papersmith's own.

- **One claim, one path, one focus.** A single sentence states what the
  figure proves. The eye enters at the left of one spine and travels it to
  the end; one focal zone is visibly heavier than everything else.
- **Three reading levels.** The claim (large, bold), the spine labels
  (normal), and notes and evidence detail (small). A reader who stops at any
  level still leaves with something true.
- **Shape follows role.**

  | Role | Meaning | Drawn as |
  | --- | --- | --- |
  | `operator` | something that acts; label it with a verb | a rounded box with a cool outline |
  | `state` | data or a feature at rest | a pale pill (a port or token) |
  | `focal` | the mechanism the claim is about | a warm ellipse, thick outline, bold label |
  | `evidence` | what a reader can check afterwards | a plain restrained frame |
  | `context` | where it came from, caveats | a small note, no frame |
  | `group` | related nodes (`members`) | a light wash behind them, never a heavy box |

- **Connectors carry two independent facts.** Prominence: `primary` (dark,
  thick) for the spine, `secondary` (gray, thinner) for everything else --
  the difference must survive grayscale. Semantics: `data` flow is solid,
  `supervision` is dashed, `feedback` curves back, `inhibition` ends blunt.
  Never use prominence to mean semantics or the reverse.
- **Arrows enter from the side that faces their source** and never run
  through a label. Branches to a row leave vertically and share one lane.
- **Sentence case everywhere**, no Title Case labels (the validator refuses
  them). Two font weights and three sizes, nothing more.
- **Not a dashboard.** A wall of equal-size cards says nothing about what
  matters. If the evidence row grows past five frames, group them or keep
  only the ones the claim needs.
- **Measured strokes and a fixed palette.** Connectors 1.4-1.9 pt, outlines
  1.3-1.8 pt. Canvas `#F7F3E8`, ink `#20252B`, cool `#4F7CAC`, warm
  `#E09F3E` and `#D96855`, with pale tints for fills. Hue is decoration;
  value (light against dark) and stroke weight carry the meaning, so the
  figure reads in grayscale.

## What this skill never does

- It never writes or edits `AGREED.md` or `Experimental_AGREED.md`; it only
  reads whether they exist.
- It never runs, schedules or alters an experiment, and never writes outside
  `<Name>/diagrams/`.
- `derive` keeps an existing spec (the Designer's edits) unless `--force` is
  passed.
- It never validates a diagram on its own initiative. Validation is the
  operator's act: the dashboard's **Validar diagrama**, or `validate`, which an
  agent runs only after the operator explicitly approves that diagram in the
  current conversation, passing the operator's words verbatim and the hash of
  the PNG it showed -- never inferred from silence or from an approval of
  something else. An agent never writes `<kind>.validated.json` by hand.
