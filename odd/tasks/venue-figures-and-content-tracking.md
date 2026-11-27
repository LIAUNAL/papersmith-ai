# Venue figure print size and opt-in content tracking (0.85.1)
Objective: (a) measure placed figures against each venue layout, not only the canonical one; (b) let a workspace opt in to versioning its research content, keeping the private default. Branch `fix/venue-figures-and-content-tracking` (worktree papersmith-ai-worktrees/fix-0.85.1); release 0.85.1. Runner: `.venv/bin/python -m pytest` (run e2e files serially; -n auto interferes).

## Specs
- S1: operator, 2026-11-27, verbatim: «ajusta papersmith y vuelve release». This answers the parent's proposal to fix the two papersmith gaps found in Paper_EEIA:
  - (a) the figures are sized for the canonical 11 pt layout and print below the 0.70 x body floor at the venue's 12 pt body, because the place gate measures only the canonical layout;
  - (b) new paper files (figures, supplement sources) were ignored by the workspace .gitignore (`paper/*`), so a clone could not build the paper.
- S2 (a): the print-quality measurement `place` already applies (paper_place.py) also runs against every built venue layout:
  - the venue's body font size and text width come from the venue's own build data (template.json, build.json or the venue main.tex);
  - `venue build` reports each figure whose smallest text falls below 0.70 x the venue body (or whose width does not fit) as a finding in its output and build record, with the remedy (redraw at the venue's width or body size);
  - `place` reports the same per built venue as warnings beside its canonical verdict. The canonical gate is unchanged; nothing new refuses.
- S3 (b): an opt-in workspace setting in papersmith.yaml, `track_research_content: true`:
  - the managed .gitignore block omits the "Research content" ignores for paper/, proposals/, experiments/, guidance/ and protocol/, keeping build products ignored (LaTeX aux, log, out, fdb_latexmk, fls, synctex, blg, spl; __pycache__; *.before-* backups; .scratch);
  - default false: the private "structure versioned, content local" contract is unchanged;
  - `smith upgrade` rewrites the block accordingly;
  - documented in docs and the CHANGELOG.

## Tasks
| ID | Specs | Route | Status | Evidence |
| --- | --- | --- | --- | --- |
| T1 | S2 | delegated (Writer trigger a: parallel with T2, disjoint surfaces) | done | venue figure measurement |
| T2 | S3 | delegated (Writer trigger a) | done | content-tracking opt-in |
| T3 | S1 | inline | done | suite, CHANGELOG, merge, release 0.85.1, cleanup, upgrade Paper_EEIA |

## Log
- L1 (2026-11-27): operator «ajusta papersmith y vuelve release». Found: templates/gitignore.tpl deliberately keeps research content local ("structure versioned, content local"); so (b) becomes an opt-in, never a default change.
- L2 (2026-11-27): T2 done.
  - The gitignore template has private and tracked research-content variants (`#@` template notes).
  - generators.render_gitignore_block; papersmith.yaml.tpl declares `track_research_content: false`; README and docs/cli.md.
  - The default block is byte-identical to 0.85.0 (sha pinned).
  - Tracked mode keeps ignored: LaTeX build products, *.before-* backups, sota-pool/atlas.html, implementations/*, analysis/streams/, engine state.
  - Parent added the schema check (a non-boolean is refused) with tests.
  - Tests: 6 passed; gitignore and e2e serial 83 passed.
- L3 (2026-11-27): T1 done: paper_place.layout, venue_layouts, venue_figure_report; venue build figure_print; place venueWarnings; 8 new tests.
  - Seam: full suite with -n 6 and TMPDIR on disk (/tmp tmpfs filled up): 11 failed, all in test_proposal_implementation. They fail only because ~/.cache is a hidden path that discovery skips; with the default /tmp they pass 11/11. 12107 passed.
