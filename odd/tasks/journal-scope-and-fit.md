# Suggested journals: scope toggle and topical fit

Objective: the national/international toggle never strands the search button, and suggested journals match the paper's topic.
Branch: `feat/review-prose-and-protocol-diagram` (same release) · delivery: single-pr · runner: `.venv/bin/python -m pytest`.

## Specs

- S1 (toggle) "revisa en el panel de pdf viewer, en la seccoon suggested journals, revisa que al cambiar de nacional e internacional, al dar buscar en nacional y luego internacional y viceversa ya no funciona la busqueda de journals, el boton queda desactivado o sin funcionar."
- S2 (fit) "revisa bien el fit con lso journlas, que si tengan que ver con el tema del paper, estas sugiriendo journals que no tienen nada que ver con el paper que se trabaja, valida y verifica"
- S3 delivery: "comit, merge push y release"

## Tasks

- [x] T1 [S1] per-scope search state: one lock and one result file per scope on the server, the canonical `paper/journal-candidates.json` kept as the latest search, `venue select` resolving ids from the scope files too; the panel tracks busy per scope, loads the selected scope's results and shows the elapsed time — inline
- [x] T2 [S2] national fit from the paper's OpenAlex subfield profile (one group_by per facet phrase, cached in the workspace), journals with no topical evidence excluded (`off_topic`), offline fallback with a stricter lexical gate — inline
- [ ] T3 [S3] commit, combined native review, merge, push, release

## Log

- L1 (2026-11-19) user request verbatim in S1-S3.
- L2 Reproduced S1 in a real browser (scratch workspace, Playwright): an uncached international search keeps the single `busy.search` flag and the single server lock for ~40 s (up to 330 s with OpenAlex 429 retries); switching to national meanwhile shows "Searching…" disabled, and when it ends the form says national while the table shows international results. With a warm cache the toggle works both ways.
- L3 Reproduced S2: for an ADHD-EEG quantum-kernel paper the national list ranked a theology journal, a private-law journal, surgery, orthopaedics and rheumatology, each on one shared word ("attention", "disorder") in the Spanish scope text. Prototype: OpenAlex `group_by=primary_topic.subfield.id` per facet phrase gives Artificial Intelligence, Cognitive Neuroscience, Psychiatry, Atomic Physics, Clinical Psychology; Publindex journals' OpenAlex topic subfields then give those five journals zero affinity and put engineering/AI, neuroscience, psychology and physics journals first. Control profiles (power grids, crops) rank TecnoLógicas/Tecnura and agronomy journals first. OpenAlex answered 429 to two calls per phrase, so one call per phrase, cached.
- L4 T1/T2 evidence (RED observed for each): tests/test_journal_finder_national.py 24, tests/test_command_center_journals.py + i18n 208, tests/test_paper_venue.py; full suite 10547 passed, the only failures xdist-flaky (proposal toy targets, skill_audit) and test_version_sources (clears on release). Browser re-check (scratch workspace, real CLI): during an uncached international search ("Searching… 9 s") the national button stays usable, the national search returns, the international result arriving while on national leaves the national table and is shown on return. Real paper (ADHD-EEG quantum kernels): 8 national journals (cognitive neuroscience, five psychology, two engineering), 166 off topic; theology, private law, surgery and education gone. Subfield rarity (log((1+N)/(1+df))) added after the first browser run still let education journals in through the Artificial Intelligence and Education subfields. Old tests that used the off-topic bulletin as a vehicle were moved to on-topic fixtures; their behaviors are unchanged. International ranking left unchanged (its list for this paper is on topic).
