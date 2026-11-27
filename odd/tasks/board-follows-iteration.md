# The board follows the current iteration (release 0.87.0)
Objective: the board (`smith ui`) shows the idea, problem, pillars, hypotheses, findings and contribution type of the CURRENT proposal revision and protocol version, never stale or accumulated entries from earlier iterations, and "Update board" brings them up to date. Branch `feat/board-follows-iteration` (worktree papersmith-ai-worktrees/board-iteration); release 0.87.0. Runner: `.venv/bin/python -m pytest`. Run e2e files serially; for the full suite clean /tmp/pytest-of-* first (/tmp is a 16 GB tmpfs) and never point TMPDIR at a hidden path.

## Specs
- S1: operator request (2026-11-27), verbatim: «luego, revisa los flujos de actualizacon del tablero y sis artefactos. por ejemplo, al itwrar sobre la idea, problema, novedad, e hipotesis, los pilares e hipotesia que se muestran en smith ui no se actualizan, deberian actualizarae y dejarae solo las que se han depurado segun la version o iteracion actualizada del trabajo. revisa flujo y actualziadion de smith ui para proyectos que se van iterando, revisa y actualiza sus flujos e implementa los cambios y verifica que fincione. liego push relase, actualiza smith en esta maquina beelink y en este priyecto y verifica que los paneles y artefactos y visualizacion esten actualizados a la version e iteracion actual del paper»
- S2: ideas follow the latest proposal revision.
  - A deterministic sync takes the identity of the problem tree, pillars and hypotheses from the latest published revision's sky overlay (`proposals/*-rNN.sky.json`):
    - ids, statements and names;
    - pillar links;
    - experiments.
  - It writes them into `.papersmith/model_spec.json`:
    - entries absent from the latest revision leave the active lists and are kept under `novelty.retired`, with the last revision that held them;
    - agent-written enrichment of surviving ids is kept;
    - `novelty.source_revision` records the revision.
  - It runs from "Update board" (`/api/board/refresh`) and from a CLI the proposal-deliberation publish step calls.
  - Precedence is the same everywhere: the latest revision gives identity, the spec gives enrichment. That covers `/api/model`, the phase steps, citations and the manuscript graph.
  - A spec older than the latest revision is never shown as current.
- S3: findings follow the latest protocol.
  - The board panels count only the discussion products whose `protocol` is the latest published protocol version: the novelty overview, the manuscript-graph findings and the hypothesis statuses. Older products are shown as superseded, or left out, and are never merged with the current ones.
  - Discussion hypotheses carry `proposal_hypotheses`: the proposal ids, mapped through the sky overlay's `hypotheses[].experiments` to the protocol experiment. The scaffold writes it, and the sync backfills existing discussions without changing their verdicts.
  - The board shows findings under proposal ids, so discussion H14 (E14) appears as proposal H11.
  - The Concept Map's hypothesis status comes from the current findings, not from stale prose.
- S4: freshness. `contribution_type` (model_spec and discussion) is flagged stale on the board when it predates the latest revision or discussion. The paper-reviewer and the proposal-deliberation SKILL say to refresh it.
- S5: "Update board" reports what the sync changed (pruned, added and renamed ids; superseded products; stale flags). Tests cover sync, pruning, precedence, the protocol filter and id mapping.

## Tasks
| ID | Specs | Route | Status | Evidence |
| --- | --- | --- | --- | --- |
| T1 | S2, S4 (spec side), S5 | delegated (Writer trigger a: parallel with T2, disjoint surfaces) | done | idea sync, precedence, board refresh, deliberation SKILL, tests |
| T2 | S3, S4 (board side) | delegated (Writer trigger a) | pending | discussion proposal ids, protocol filter, manuscript graph, novelty overview, Concept Map status, stale badges, server endpoint, i18n, tests |
| T3 | S1 | inline | pending | seam, CHANGELOG, release, upgrade Paper_EEIA, verify the panels there |

## Log
- L1 (2026-11-27): operator request, verbatim in S1.
- L2 (2026-11-27): explorer map, paths relative to the papersmith repo:
  - The Concept Map shows `model_spec.json` as written (`model_spec.py:118-138`). No code updates it on a new revision, and nothing prunes it.
  - `board_refresh.ARTIFACT_IDS` covers only derived graphs (`board_refresh.py:25, 75-98`).
  - Precedence is inconsistent: spec first in `phase_steps.py:105-117` and `citations.py:384-392`; sky first in `manuscript_graph.py:312-338`.
  - Discussion ids are positional (`discussion.py:685-689`).
  - `manuscript_graph._findings` (`:474-511`) and `novelty_gate.get_novelty_overview` (`:404-447`) merge every product with no protocol filter.
  - `merge_proposal_sky.pillars_and_hypotheses` (`skills/proposal-deliberation/scripts/merge_proposal_sky.py:83`) parses hypotheses and their experiments.
  - Paper_EEIA evidence: ids match r21, but the statuses cite v18/v19, the contribution_type is the r18 one, the pillar-3 name differs, and H8's pillars differ. The board mixes a v12 PoC product (`implementations/pi5rc`) with the v23 one, and discussion H1-H14 are positional.
  - Existing tests: test_command_center_board_refresh, test_flow_gating_phase4, test_sota_citations, test_manuscript_graph, test_command_center_math_view, test_proposal_sky_pillars.
- L3 (2026-11-27): T1 done.
  - idea_sync.py: sync, CLI --dry-run/--json, retired with last_revision, a format-preserving atomic write, idempotent.
  - current_novelty precedence at /api/model, phase_steps and citations; /api/model adds stale, source_revision, latest_revision and contribution_type_stale.
  - contribution_type_revision is a separate field (contribution.py rejects inner keys); board_refresh has an ideas artifact and summary.ideas.
  - Tests: 29 new; existing refresh, phase4, citations and sky tests pass.
  - Paper_EEIA dry-run: r21, 0 added, 0 pruned, 17 changed (pillar-3 renamed, 7 hypotheses restated, experiments added), contribution type stale.
  - Forwarded to T2: badges from /api/model, the paper-reviewer records contribution_type_revision, manuscript_graph reuses current_novelty.
