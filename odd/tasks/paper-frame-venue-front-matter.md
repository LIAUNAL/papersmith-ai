# Paper frame, venue front matter and config reader fixes
Objective: stop three defects found while building the Energy and Buildings paper of the Paper_EEIA workspace from recurring in other projects. Branch `fix/paper-frame-venue-front-matter`; delivery `ask-on-risk`; runner `.venv/bin/python -m pytest -q tests/test_paper_writing.py` (plus the suites each unit touches).

## Specs
- S1: «entocnes debemos ajustar algo en papersmith? si si ajustalo en papersmith, push y release para que no ocurra en futuroa proyectos» (operator, 2026-11-26).
- S2 (frame): `scaffold` writes an empty `paper/main.tex` and `skeleton` only opens block markers, so no verb writes the canonical document frame (preamble, `\begin{document}`, one body `\section{...}\label{...}` line per content section outside the blocks, the back-matter heading, `\bibliographystyle`/`\bibliography`, `\end{document}`). In Paper_EEIA the redactor then put the body `\section` lines inside blocks, and `venue build` duplicated every heading and loaded no packages. Acceptance: on a fresh paper the frame exists outside the blocks with every block inside `\begin{document}`; a body block draft that carries a `\section{`/`\section*{` line (declarations excepted, as their contracts place `\section*` inside) is refused by `write` with a named code; existing papers can obtain the frame without touching block bytes.
- S3 (venue front matter): the revealed-author template of `sections/09-title-and-keywords.md` wraps `\author` in a minipage; `venue build` for elsarticle splits it across `\author{\begin{minipage}...}` and `\address{...\end{minipage}}` (invalid LaTeX); and the highlights block is emitted as `\paragraph{Highlights}` among the declarations although the venue table marks elsarticle `highlights: True`. Acceptance: an elsarticle build of a paper with the revealed template yields valid `\author`/`\address`/`\cortext` (or the class's equivalent) and places the highlights in `\begin{highlights}...\end{highlights}` inside the front matter; the build compiles.
- S4 (config reader): `skills/paper-writing/scripts/paper_resolve.py` `parse_yaml_subset` stops silently at a block list of mappings (`authors:` with `- name: ...` and nested keys), dropping every later key (`paper_writing.roles`), so `resolve` refuses `RESOLVER_ROLE_EMPTY`; its docstring promises to fail closed. Acceptance: a list of mappings parses (or the reader refuses `PAPERSMITH_CONFIG_UNREADABLE` naming the line); keys after it are kept; a papersmith.yaml with `authors:` before `paper_writing:` resolves its roles.

## Tasks
| ID | Specs | Route | Status | Evidence |
| --- | --- | --- | --- | --- |
| T1 | S2 | delegated (Writer trigger a: parallel with T2, disjoint surfaces; context backstop) | pending | |
| T2 | S3, S4 | delegated (Writer trigger a: parallel with T1) | pending | |
| T3 | S1 | inline | pending | merge, full suite, release 0.84.4 (version files, CHANGELOG, README pin, ?v= tokens, tag, gh release) |

## Log
- L1 (2026-11-26): «entocnes debemos ajustar algo en papersmith? si si ajustalo en papersmith, push y release para que no ocurra en futuroa proyectos»
- L2 (2026-11-26): evidence from Paper_EEIA: reviewJorge/paper/main.tex keeps the frame and body \section lines outside the blocks (hand-written); Paper_EEIA's frame was never written; first elsarticle build invalid (duplicate headings, no packages, author minipage split, highlights as \paragraph); paper_resolve dropped paper_writing.roles after authors:. The ingestion setup was checked and is not a defect (scripts/setup_env.py ships in the workspace).
