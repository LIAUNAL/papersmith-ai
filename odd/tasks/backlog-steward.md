# Feature: a backlog steward that reviews, groups and resolves papersmith's issues and PRs

Objective: bring gentle-ai's issue/PR practice (root-class triage, evidence-gated closure, issue-first PRs, bounded dual review) into papersmith as repo-only maintainer tooling, then use it on the live backlog (55 issues, PRs #94–#99).
Branch: `feat/backlog-steward` · Delivery: ask-on-risk · Runner: `.micromamba/envs/papersmith/bin/pytest` (focused), `python3 scripts/clean_context_gate.py` (CI gate).

## Specs

- **S1** "revisa el repo https://github.com/Gentleman-Programming/gentle-ai, verifica agentes o skills para resolver issues y pr. revisa como los agrupa testea y acepta." Findings recorded in L2.
- **S2** "explora como podemos llevar y mejorar esas mismas ideas, agentes o skills para que en papersmith revisemos, agrupemos y resolvamos issues y pr": a repo-only maintainer kit under `maintainer/` (never `skills/` or `.claude/agents`, which ship to users through `KIT_ENTRIES`):
  - a protocol skill `maintainer/skills/backlog-steward/SKILL.md` (buckets, root clusters, repro-first, closure rules, PR acceptance, bounded dual review);
  - `maintainer/backlog.py`, stdlib-only: `check` validates `maintainer/backlog/roots.json` against live GitHub (every open issue in exactly one root, every open PR linked to issues of a single root), `stale` flags issues whose cited paths/symbols no longer exist on the checkout, `render` prints the tracker issue body, `pr-link` validates a PR body's issue reference;
  - a CI job requiring a `Closes|Fixes|Resolves|Refs #N` reference in every PR body.
- **S3** "implementa la mejor opcion y usalo para resolver los issues y pr en papersmith": triage every open issue into `roots.json`, restore green CI (#108), evaluate PRs #94–#99 against their roots, fix the contained bug roots with repro tests, close stale/already-fixed issues with evidence. Assumption: pushing, merging, closing and commenting on GitHub wait for one explicit operator confirmation of the prepared batch.

## Tasks

| ID | Specs | Route | Status | Commit |
|----|-------|-------|--------|--------|
| T1 | S2 (kit: skill, backlog.py, tests, CI pr-link job, routing docs) | inline | done | `3241a4e0`, `e121e47b` (on main via 0.22.1) |
| T2 | S3 (triage: roots.json, stale scan, evidence per issue) | 3 read-only explorers + inline roots.json | done | `e121e47b`; states updated on `chore/backlog-tracker` |
| T3 | S3 (#108 green CI) | inline | done locally, CI proof pending push | `fix/env-provisioning` `ad78fb3e` |
| T4 | S3 (PRs #94–#99: rebase, RED/GREEN, dual review) | 1 verifier + 2 blind judges | done: #94 #95 #96 #97 #99 accept, #98 changes needed | scratchpad logs |
| T5 | S3 (contained bug roots, repro-first) | 8 parallel writers in worktrees + parent fixes | done: 18 Closes, 5 Refs, 1 not reproduced (#76) | 15 `fix/*` branches |
| T6 | S3 (GitHub batch: push, merge, close, tracker) | inline, after confirmation | pending operator confirmation | |

## Log

- **L1** (2026-10-25, user verbatim): "revisa el repo https://github.com/Gentleman-Programming/gentle-ai, verifica agentes o skills para resolver issues y pr. revisa como los agrupa testea y acepta. luego, explora como podemos llevar y mejorar esas mismas ideas, agentes o skills para que en papersmith revisemos, agrupemos y resolvamos issues y pr, luego de explorar y planear, implementa la mejor opcion y usalo para resolver los issues y pr en papersmith"
- **L2** gentle-ai findings: `systemic-issue-triage` (buckets A covered / B duplicate / C root cluster / D feature / E unclear; "N issues never justify N patches"), `issue-root-resolution` (meta-issue #2471: 438 issues → 20 roots in tiers; close only on A fixed-with-commit+test, B superseded decision, C code gone, D duplicate of fixed; mechanism is a hypothesis, a repro that passes on main disproves the diagnosis), `branch-pr` + `.github/workflows/pr-check.yml` (issue reference + `status:approved` + one `type:*` label), `chained-pr` (400-line budget, dormant in practice), `judgment-day` (two blind judges, fix only confirmed findings, ≤2 rounds, APPROVED|ESCALATED, no merge authority). Weaknesses to improve: the meta-issue is hand-maintained prose that drifts; the size gate is dormant; nothing machine-checks that every issue sits in one root.
- **L3** papersmith state at `06d27b33`: CI red on main since 2026-10-21 (#108); fork PRs #94–#99 never ran CI (runs `action_required`, awaiting maintainer approval); 35 issues (#52–#86) come from a v0.13.0 audit, so staleness must be checked against current main.
- **L4** (2026-10-25) A concurrent session merged T1/T2 into main and released 0.22.1 (`2d31f873`); all later work moved to worktrees under `papersmith-ai-worktrees/`.
- **L5** Review: two blind judges, no BLOCKER. Fixed after confirmation by both or deterministic proof: IPv6/`git+ssh` refused by the #56 boundary (`dec7c64a`), unbounded orphan registry (`29c9780d`). Refuted with evidence: MCP `extra` after `--` (the bridge forwards `extra` verbatim, `bridges/implementation.py:73`); agent doc lost overwrite/PDF rules (the skill owns them, `SKILL.md:362`, and moves the PDF).
- **L6** Integration (all 15 branches + PRs #94–#97, #99 merged in order): node 832/832; python 7029 passed. Seams found and fixed: PR #99's origin guard needs `headers` on the phase-run fake request (`f5d1c56e`); conftest import broke test_process_state_isolation (`981bf66d`); a self-guarded-facts probe pins an audit_cli.py line (repinned in `6eb978bd`). Remaining: 5 test_forge_gate interpreter tests (fail on main in a worktree too: no `.micromamba`), and ReleaseHygieneTests, which requires a version bump with the merge.
