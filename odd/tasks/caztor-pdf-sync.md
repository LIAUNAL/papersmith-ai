Caztor in the smith PDF tab: compile failures that leave the PDF stale, and jumping from the LaTeX source to the PDF.
Branch: papersmith-ai `pr/caztor-embed` (worktree ~/papersmith-ai-worktrees/pr-caztor-embed). Delivery: single-pr (same PR as caztor-vendor). Runners: vitest + tsc (caztor/).

## Specs

- S1. "compilé el paper y no se ve, ademas, sigue habiendo un problema con el out of date": the compile fails with "`.caztor/build.json would run `python3 paper/build_preview.py` before compiling paper/main.tex, and it is not confirmed on this computer. Read it, then confirm it from the Caztor folder with: npm start -- trust-build "/home/andres/papers/paper-mcmc-optimized"`", so the PDF stays the 2026-11-16 build ("Out of date") and holds none of the explained passages. The confirmation stays the host's decision (Caztor's trust-build gate is not bypassed); the message names a command that works where Caztor actually runs (smith's checkout or the wheel's bundle, where there is no `npm start`).
- S2. "quiero agregarle que cuando le de doble click al codigo latex me lleve a esa parte del pdf": a double click in the LaTeX editor scrolls the PDF preview to the place that prints the clicked text and marks it briefly. Assumption: found by the printed text (the same matching as the explained passages), not SyncTeX, because this project compiles paper/preview.tex generated from main.tex by its build step, so SyncTeX would point at preview-body.tex instead of the line clicked.

## Tasks

- [ ] T1 [S1] The unconfirmed-recipe message names the running server's own command (`<node> <entry> trust-build "<root>"`). Route: inline. Risk: item 2 (touches the message of a security gate, not the gate).
- [ ] T2 [S2] Double click in the editor -> candidates around the clicked word -> the PDF finds the page, scrolls and marks the printed text for a moment. Route: inline.

## Log

- L1 (2026-11-20) "compilé el paper y no se ve, ademas, sigue habiendo un problema con el out of date. tambien quiero agregarle que cuando le de doble click al codigo latex me lleve a esa parte del pdf"
- L2 (2026-11-20) Evidence: .caztor/build/preview.pdf and last-compile.log date from 2026-11-16 21:52; .caztor/build.seal does not exist; trust-build gating entered Caztor on 2026-11-15 (089f6dd). The PDF shown is therefore older than the passages.
