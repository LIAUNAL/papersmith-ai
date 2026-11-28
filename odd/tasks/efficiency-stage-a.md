Objective: stage A of the 2026-11-28 efficiency audit — low-risk savings that keep quality and keep Claude Code, OpenCode, Pi and Antigravity (agy) working.
Branch: feat/efficiency-stage-a · Delivery: ask-on-risk · Runner: `.micromamba/envs/papersmith/bin/pytest` (+ `python scripts/sync-repo-harness.py --check`)

## Specs

- S1 — The dashboard tutors pass the model their agent file declares. `skills/_core/command_center/tutor.py` runs `claude -p` with no `--model`, so `model: sonnet` in `.claude/agents/math-tutor.md` is ignored. On the Claude branch only, a declared `model:` becomes `--model <value>`; agy and Pi keep inheriting (Claude aliases are not their model slugs). No declared model keeps today's argv byte for byte.
- S2 — Skill descriptions are trigger-first and at most 250 characters, keeping each skill's trigger phrases and verb names, dropping internals and guarantees. Pi refuses descriptions over 1024 chars and Claude truncates at 1536; all four harnesses read the same `skills/*/SKILL.md`.
- S3 — The generated command body runs the deterministic prompt gate first and reads `skills/prompt-gate/SKILL.md` only when the verdict is not a pass, instead of reading it on every call. Applies to the three command harnesses (Claude, OpenCode, Pi) and to agy's rules in `.agents/AGENTS.md` (see L5).
- S4 — `experiments-walk` and `implementation-walk` no longer contradict themselves about the rehearsal: the description says the rehearsal is left to a person while the body says "The rehearsal is yours … run it rather than offering it". One consistent statement, matching what the skills and tests require.
- S5 — (dropped, L11) `skill-audit` (and its `audit-report` agent) stop shipping to paper workspaces and live as a maintainer tool of the forge, the way `maintainer/skills/backlog-steward` does; `smith audit .` stays. (Assumption: the phase-11 card keeps `smith audit .` and drops `/skill-audit`.)
- S6 — Harness parity holds: `python scripts/sync-repo-harness.py --check` is clean, the generated `.claude/commands`, `.opencode/commands`, `.pi/prompts`, `.opencode/agents`, `.agents/agents`, `.pi/agents` are regenerated, and the full Python and node suites pass.

## Tasks

- [x] T1 — S1 tutor `--model` · route: inline · commit: 90224104 (RED 2 failed → GREEN 79 tutor tests)
- [x] T2 — S4 walk agents rehearsal wording · route: inline · commit: 6487e71b (test_agents 19 passed; sync --check clean)
- [x] T3 — S3 prompt gate first in command body · route: inline · commit: 03e6a36c (RED 4 failed → GREEN 224 passed)
- [x] T4 — S2 skill descriptions ≤250 chars · route: inline · commit: 4c630c38 (RED budget test → GREEN; full suite 12195 passed)
- [~] T5 — S5 skill-audit out of the workspace kit · dropped by the user (L11) · commit: —
- [x] T6 — S6 parity and full suites · route: inline · evidence: L9; sync --check clean (179 files) after 4c630c38

## Log

- L1 (2026-11-28, user, verbatim): "realiza una revision exahustiva del los proceos en smith, tienpos de ejecucion en cada fase, errores o reprocesos que hemos cometidos en proyectos usando smith (mira proyectos y engram para ver proyectos) revisa cada agentr dentro de smith y cada skill, mira si debemos depurar o quitar agentes o skills, o mejorarlas con tu skill creator, buscamos eficiencia sin perder calidad"
- L2 (2026-11-28, user, verbatim): "antes de arracar con ts recomendaciones, verifica que sean compatibles luego para que papersmith funcione con claude code, opencode, pi y antigravity cli (agy)"
- L3 (2026-11-28, user, verbatim): "arranca" — authorizes stage A on a branch.
- L4: Compatibility evidence: Read caps Pi 2000 lines/50KB, OpenCode 2000 lines/50KiB, Claude ~25k tokens; Pi description max 1024; `generators.py` drops `model:` for non-Claude agents and rewrites `.claude/skills/` to `skills/`; COMMAND_TOOLS = opencode, claude, pi. Engram: audit/smith-efficiency-2026-11, audit/smith-efficiency-harness-compat.
- L5: T3 correction: agy does apply the gate, through `.agents/AGENTS.md` (antigravity-rules.md.tpl); the change covers it too. `ai_transcripts._EXPANDED_RE` requires the body to start "Read `skills/X/SKILL.md` and follow it" and end at the first "`$ARGUMENTS`:", so the new body keeps both.
- L6: T4: three new line skills (idea-shaping, paper-type, study-protocol-deliberation) were already missing from the kit.json golden as declared additions; left for T5's golden refresh. remote-execution's roster test moved from the frontmatter to `## The commands` (the closed roster skill-audit derives against); each old description is kept in its body as a **Scope.** paragraph, loaded only on trigger.
- L7: T5 scope is larger than forecast: `/skill-audit` is phase 11 of all eight lines (7 boards, prompt_gate contract, health_inspector, state_extractor, 8 generated flow diagrams, index.html, flow templates, goldens). Removing it from workspaces is Risk item 3. Paused for a user decision.
- L8: /tmp (tmpfs) hit EDQUOT during the full suite; suites now run with TMPDIR under ~/.cache/psm-stage-a.*.
- L9: Full suite after T1-T4 (TMPDIR outside /tmp): python 12195 passed, 13 failed; node exit 0. Of the 13: 10 proposal-implementation discovery tests fail only because TMPDIR sat under a dot-directory (`~/.cache`) and pass with a plain TMPDIR; `test_description_names_the_driver_and_the_pinned_sdk` was real and now reads the Scope paragraph; `test_missing_transcripts_never_fail` fails on main too (agy installed on this machine reads a real history DB); `test_shipped_changes_since_the_last_release_moved_the_version` fails by design until the release bump.
- L10: After T4 the per-session cost of `skill-audit` is a 237-char description; T5's remaining gain is about 60 tokens per session against ~40 files and a phase-11 card in all eight lines. Recommendation: drop T5.
- L11 (2026-11-28, user choice): "Descartar T5 (Recommended)" — skill-audit keeps shipping; stage A closes with T1-T4 and work moves to stage B.
