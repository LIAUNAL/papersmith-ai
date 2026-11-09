# Pi and Gentle Shell release

Compatibility, runtime documentation, and the next Papersmith release. Target: LIAUNAL/papersmith-ai.

## Specs

S1. "verifica que el presente proyecto sea compatible con pi y gentle-shell, si falta ajustar algo, ajustalo."
S2. "luego, actualiza el readme del proyecto, requeriments y lo que consideres, para actulizar las verisones de npm, puython, y lo que ajustaste por seguridad."
S3. "luego, da comit, meregea, y mergea tambien estos comits  • Existen 3 commits en main posteriores a la etiqueta v0.68.0: 1. 7a5254e1: docs(odd): close ui-pages T3 2. 9a83002c: Merge branch 'docs/ui-pages-t3' 3. cfb7cea0: fix(ui): install httpx2 so the static snapshot export runs, dale push, y saca release de papers_smith"
S4. "el repositorio es el que esta enlazado con https://github.com/LIAUNAL/papersmith-ai"

## Tasks

T1 [S1-S2] Audit compatibility and document verified runtime requirements; route inline; commit pending (harness projection clean, diff whitespace clean).
T2 [S1-S2] Verify compatibility and project checks; route inline; commit pending.
T3 [S3-S4] Commit, merge release branch, tag, push and publish release after gates; route inline; commit pending.

## Log

L1. verifica que el presente proyecto sea compatible con pi y gentle-shell, si falta ajustar algo, ajustalo. luego, actualiza el readme del proyecto, requeriments y lo que consideres, para actulizar las verisones de npm, puython, y lo que ajustaste por seguridad. luego, da comit, meregea, y mergea tambien estos comits  • Existen 3 commits en main posteriores a la etiqueta v0.68.0:
      1. 7a5254e1: docs(odd): close ui-pages T3
      2. 9a83002c: Merge branch 'docs/ui-pages-t3'
      3. cfb7cea0: fix(ui): install httpx2 so the static snapshot export runs, dale push, y saca release de papers_smith
L2. el repositorio es el que esta enlazado con https://github.com/LIAUNAL/papersmith-ai
L3. 7a5254e1, 9a83002c and cfb7cea0 are already ancestors of main and origin/main; do not merge them twice.
L4. docs: distinguish verified Node 26/npm 12 workstation from Node>=21/Python>=3.11 project contract; Python 3.11/3.12 and Node 24 are CI-tested. `python3 -m pytest` used the unrelated Python 3.15 lacking pytest; use `.micromamba/envs/papersmith/bin/pytest` for T2.
