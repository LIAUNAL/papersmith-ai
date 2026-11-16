# Journal scope: international or Colombian national (Publindex)
Objective: let the journal match choose international journals or Colombian national journals (Publindex IBN 2026), with review times and languages. Branch: feat/journal-scope-publindex. Delivery: single PR-sized branch merged with --no-ff, then release 0.74.0. Test runner: `.micromamba/envs/papersmith/bin/pytest`.

## Specs
- S1. "vamos a dejar una bandera en la revsion de revistas, para que se pueda escoger revistas internacionales y revistas nacionales de colombia, entra a la pagina de publinkdex y descarga el listado y homologacion de revistas nacionales" — the national list is the IBN 2026 ("ahi encuentras la IBN nacional 2026, esa es la que necesitamos").
- S2. "incluye selector en el pannel de pdf previsualizador, en match con journal, para que el usuario pueda escoger internacional o Nacional (Colombiana)".
- S3. "para las colombianas ajsuta para que el match se haga solo cno las B, A1, A2".
- S4. "agrega en la visualicion del mathc para revistas colombianas, ademas del tiempo promedio de revision, si reciben en español e ingles".
- S5. "revisa que para el match que realizas en revistas internacionales, tambien se presente el tiempo promedio de revision a publicacion".
- S6. "para las revistas nacionales, ingresa a sus paginas web y explora los tiempos aproximaods de revision, desde envio del paper hasta la publicacion del mismo".
- S7. "no busques el mathc del paper qmleeg, solo deja la informacino base, y lista para cruzar con el paper y con banco lia mcp".
- S8. "ajusta, verifica, testea que funcione, comit, mergea, push y release."

## Tasks
- T1 [x] S1,S6,S7 — data file publindex-ibn.json (515 journals, OpenAlex, website review survey) + scripts fetch-publindex.py, fetch-publindex-review-times.py; CLI --scope national; server scope; panel selector. Route: inline.
- T2 [x] S3 — national match limited to A1, A2, B (CLI, server, panel). Route: inline. RED 18 failing -> GREEN.
- T3 [x] S4 — languages (declared or published) per A1/A2/B journal; shown in the national match. Route: inline. scripts/fetch-publindex-languages.py: 173/174 known, 125 accept es+en.
- T4 [x] S5 — international review_time also reports submission-to-publication; shown in the panel. Route: inline. Live: Quantum Machine Intelligence 201 d to acceptance, 217 d to publication (n=40).
- T5 [ ] S8 — full suite, live check, commit, merge, push, release 0.74.0. Route: inline.

## Log
- L1 (2026-11-15) "vamos a dejar una bandera en la revsion de revistas, para que se pueda escoger revistas internacionales y revistas nacionales de colombia, entra a la pagina de publinkdex y descarga el listado y homologacion de revistas nacionales"
- L2 (2026-11-15) Latest homologation published by Minciencias is "Jul 2024 - Dic 2024"; no 2025/2026 homologation exists. User: use the IBN national 2026.
- L3 (2026-11-15) User: do not tune matching to the qmleeg paper; survey national journals' websites for submission-to-publication times.
- L4 (2026-11-15) Survey: 348 sites read, 281 journals measured (n>=5), 144 with declared times; medians under 30 days marked implausible-dates.
- L5 (2026-11-15) "incluye selector en el pannel de pdf previsualizador ... comit, mergea, push y release."
- L6 (2026-11-15) Live check: POST /api/journals/search {scope: national} through the real server ranks A1/A2/B only (341 excluded), with review times and languages; categories C -> 422; panel renders the real outputs.
