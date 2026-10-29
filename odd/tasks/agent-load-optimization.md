# Agent load optimization: smaller per-agent context and lighter models for mechanical agents

Objective: cut the tokens and wait each smith phase spends by loading only the doctrine a stage needs, and by letting mechanical read-only agents run on a lighter model, without changing what any agent is required to do.
Branch: `feat/agent-load-optimization` (from `origin/main` b40171fc, v0.37.0). Delivery: release after verification. Tests: `~/Documents/papers_smith/papersmith-ai/.micromamba/envs/papersmith/bin/python -m pytest -q -n 6`; `npm test`.

## Specs

- S0. The operator's requests, verbatim: (2026-10-28) "revisa en donde podemos optmizar el uso de recuros, tokens, y tiempo de espera en las fases de smith para hacer mas agil la construccion de todas las fases"; (2026-10-29) "4. resuleve los pendientes" (the pending list named "Las optimizaciones de tokens: partir las skills gigantes y declarar `model:` en los agentes").
- S1. `skills/proposal-implementation/SKILL.md` (307 KB, the largest skill, loaded whole by every agent that binds it) is split: the per-probe-state `### nextStep: "…"` sections and other bulky per-stage explanation move into `skills/proposal-implementation/references/*.md`, one file per stage, each pointed to by a one-line reference left in SKILL.md; Hard Rules, Activation Contract, Output Contract, Command Roster and every other pinned doctrine stay in SKILL.md. No rule text is lost or reworded: the union of SKILL.md and its references holds every sentence the old SKILL.md held. Tests that pin SKILL.md text read SKILL.md plus its references through one shared helper. Agents that bind the skill read SKILL.md, then only the reference for the current `nextStep`. Measured result reported: SKILL.md bytes before/after and the largest per-stage load.
- S2. Agent sources gain an optional frontmatter field `tier: light|heavy` (omitted = inherit, today's behavior). The Claude projection maps `light` to `model: sonnet` and writes nothing for `heavy`/omitted; projections for harnesses without a cited per-agent model mechanism write nothing (no unverified claim). `tier: light` is set only on read-only mechanical agents (no write tools, no gate): the candidates named by the triage (`math-tutor`, `insumos-observer`, `style-sampler`, `figure-auditor`, `sota-grapher`, `dataset-curator`) after checking each one's tools; writers, judges and gate holders stay inherit. A test proves an omitted tier writes no `model:` line and `light` writes exactly `model: sonnet` in the Claude projection only.
- S3. Docs (README agent/harness section, CHANGELOG `## Unreleased`), harness projections in sync (`scripts/sync-repo-harness.py --check` clean).

## Tasks

- T1 (S1) split proposal-implementation SKILL.md + shared pin helper + agent read instruction -- pending
- T2 (S2) `tier` field, Claude mapping, agents tagged, tests -- pending
- T3 (S3) docs, CHANGELOG, projections -- pending
- T4 independent verifier (item 3: mirrored prompts and doctrine contracts) -- pending

## Log

- L1 (2026-10-29): triage evidence. `skills/proposal-implementation/SKILL.md` ~3,500 lines: `## Hard Rules` 250-594, `## Flow A` 789-1322, `## Flow B` 1322-1441, ~14 `### nextStep:` sections 1624-2427, `## References` 3498; `references/usage.md` exists. `.claude/agents/implementation-build.md`: "Load it and follow it. Every rule is there and none is repeated here." Pins: `tests/test_proposal_implementation.py:96,506,687,5162,9004-9018,9189,9216` (every `nextStep` needs a defined section). No agent declares `model:`; `generators.py` `_split_agent_source`, `_translate_agent_for_pi` passes frontmatter through except `tools:`; OpenCode translator near `OPENCODE_PERMISSION_KEYS` (~489). Other mega skills (remote-execution 144 KB, paper-writing 120 KB) are left for a follow-up once S1's pattern is proven.
