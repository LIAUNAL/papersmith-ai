Objective: every idea of the proposal and of the experimental protocol is justified by 2 to 5 SOTA pool citations, shown beside the idea in its panel, and the flow blocks without them.
Branch: feat/sota-citations. Delivery: ask-on-risk. Test runner: `.micromamba/envs/papersmith/bin/pytest -q -n 4 -p no:cacheprovider` and `npm run -s test:node`.

## Specs

- **S1** — "en los paneles de mapa conceptual y matematica, hipotesis, pilares, y deliberacion de experimentos y donde consideres, se justifiquen las ideas ocn citas del sota, entre 2 y 5 citas". Ideas: pillars, hypotheses, concept-map layers, numbered equations (`\tag{N}`) of the latest revision, and experiments (`[exp:<id>]`) of the latest protocol.
- **S2** — Contract (assumption, design proposed to and accepted by the user): one workspace file `.papersmith/citations.json`: `{"schema": 1, "ideas": {"pillar:P1": [{"id": "<pool identifier>", "why": "<how this reference supports the idea>"}], "hypothesis:H1": [...], "layer:<layer name>": [...], "equation:1": [...], "experiment:E1": [...]}}`. A valid idea has 2 to 5 entries, distinct ids, each id present in `sota-pool/candidates.json` (`candidates[].identifier`, compared normalized so `arXiv:2008.08605` equals `2008.08605` and DOI case/prefix differences do not matter; reuse the normalization of `skills/paper-writing/scripts/paper_bib.py:source_identity` semantics without importing across skills if a loader by path is not clean), and a non-blank `why` of at most 300 characters.
- **S3** — User decision, verbatim answer: "Bloquear las fases (Recomendado)": "Igual que el juez NeurIPS: un paso obligatorio bloquea la Fase 5 y la implementación del experimento hasta tener 2-5 citas válidas por idea. QMLEEG y otros proyectos existentes pierden su PASS hasta completar las citas con el agente." Phase 4 gets a new required step `sota_citations` after `mathematics` and before `neurips_review` (so the judge reads justified ideas); it covers pillar, hypothesis, layer and equation ideas. Experiment ideas: the implementation actions (`/proposal-implementation`, `/experimental-implementation`) stay locked and Phase 5 cannot pass until every experiment of the latest protocol is cited; G-EXP-POC approval refuses `SOTA_CITATIONS_OWED` while one is not, in the dashboard and in `smith novelty approve`.
- **S4** — A button in the panels, as with the judge: the stepper step and the Experiments tab type the skill command into the agent terminal (`window.sendToCli(text, false, {kind:'slash'})`), disabled with a reason while locked. Agent input stays English.
- **S5** — Each panel shows an idea's citations beside it (title, year, the why), and marks an idea that owes them, in en and es.
- **S6** — A checker the agent runs: `python skills/_core/results/citations_cli.py check --root .` prints what is owed and exits non-zero. `proposal-deliberation` and `experimental-deliberation` SKILL.md state the rule; flow text, README and docs/cli.md are updated.

## Tasks

- T1 [S1-S6] delegated (context backstop: the parent session is past the advisory context limit) — contract, checker, gates, buttons, panels, docs. Status: pending.

## Log

- L1 (2026-11-05, user, verbatim): "antes de push, revisa el flujo para que en los paneles de mapa conceptual y matematica, hipotesis, pilares, y deliberacion de experimentos y donde consideres, se justifiquen las ideas ocn citas del sota, entre 2 y 5 citas"
- L2: map: no idea has a citation field today; `candidates[].identifier` (DOI or bare arXiv id) is the pool key; `model_spec.json` has no validator; equations come from the revision markdown by `\tag{N}`; QMLEEG r04 overlay cites `arXiv:1904.04767` and `arXiv:2307.11300`, absent from its pool. Validity here means pool membership and a stated reason; it does not prove that the reference supports the idea.
