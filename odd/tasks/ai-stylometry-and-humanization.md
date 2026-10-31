# AI Stylometry, Claude Fingerprint Quantification, and Authentic Humanization

Objective: Provide an automated, deterministic stylometric and AI-detection quantification engine (`paper_ai_metrics.py`), a CLI audit/humanization pass, and an `ai-auditor` agent that guides draft iterations to eliminate Claude/LLM fingerprints and raise natural burstiness while strictly preserving the forge's F5 invariants (untouchable citations, numbers/statistics, methodology, and evidence bindings).

Branch: `feat/ai-stylometry-auditor` (from `main` 018a1473, v0.48.0).

## Specs

- S0. The operator's request, verbatim: L1.
- S1. **Deterministic Stylometric & AI Signature Engine** (`skills/paper-writing/scripts/paper_ai_metrics.py`):
  - **Sentence Burstiness**: Computes mean sentence length $\mu$, standard deviation $\sigma$, and coefficient of variation $CV = \sigma / \mu$. Natural academic writing exhibits varied cadence ($CV \ge 0.38$); uniform LLM output exhibits flat cadence ($CV < 0.25$).
  - **Closed Catalog of AI Clichés & Claudeisms**:
    - High-frequency vocabulary: *delve, testament, tapestry, beacon, paramount, multifaceted, bespoke, meticulously, underscore, seamless, nuanced, holistic, foster, pivotal, interplay, overarching, realm, landscape, bolster, vibrant*.
    - Formulaic rhetorical constructs: forced triadic parallelism ("X, Y, and Z" structures), repetitive "Not only ... but also ...", empty nominalizations ("the utilization/implementation of..."), and redundant hedges ("It is worth noting that...", "While X has merit, Y remains...").
  - **Lexical Diversity**: Type-Token Ratio (TTR), Hapax Legomena ratio, and functional word variance against the LIA house style baseline.
  - **Composite AI Signature Score ($0.0$ to $1.0$)**: Weighted combination of cliché density, burstiness penalty, and structural symmetry. Scores $\le 0.15$ indicate natural human cadence; scores $\ge 0.50$ flag high AI likelihood.
- S2. **F5 Invariant Protection Gate**:
  - Every proposed rewrite must satisfy the F5 contract before entering the draft pipeline:
    - Citations (`\cite{...}`, bracketed numbers) must remain byte-identical.
    - Numbers, statistics, p-values, percentages, and units must remain byte-identical.
    - Mathematical symbols and declared notation must remain byte-identical.
    - Evidence bindings (`evidence:<id>`, `fact:<id>`) must remain intact.
  - Any pass attempting to alter an F5 invariant is refused with `F5_INVARIANT_VIOLATION`.
- S3. **CLI Interface** (`skills/paper-writing/scripts/paper_cli.py`):
  - `paper_cli.py ai-audit --section <id> [--block <id>] [--draft <path>] [--target-score <float>]`:
    - Reports burstiness ($CV$), cliché density, sentence-by-sentence risk breakdown, and composite AI score.
  - `paper_cli.py humanize --section <id> --block <id> --draft <path> [--target-score <float>]`:
    - Validates a humanized draft against F5 invariants and verifies that the composite AI score drops below `--target-score` (default: 0.20).
- S4. **AI Auditor Agent** (`.claude/agents/ai-auditor.md`, mirrored across harnesses):
  - Evaluates drafted blocks, points out low-burstiness sentence clusters and Claudeisms, and proposes concrete sentence structure variations adhering strictly to `LIA house style` and the F5 contract.
- S5. **Pluggable External Detector / Perplexity Support (Zero-Dependency Default)**:
  - Default runs 100% locally and deterministically with standard Python libraries.
  - Optional support for external detection APIs (e.g., GPTZero, ZeroGPT) or local Binoculars/transformers servers if configured via environment variables (`PAPERSMITH_AI_DETECTOR_URL`, `PAPERSMITH_AI_DETECTOR_KEY`).
- S6. **Command Center & PDF Preview Integration**:
  - `/api/pdf/ai-audit` endpoint providing section-level AI scores and flagged sentence spans.
  - Connects the existing "✨ Humanize" emerald button in the PDF preview toolbar to trigger the stylometric inspection and highlight flagged passages.
- S7. **Tests & Documentation**:
  - Unit tests in `tests/test_paper_ai_metrics.py` testing against human Q1 reference blocks vs LLM raw drafts.
  - F5 invariant protection tests.
  - Documentation in `skills/paper-writing/SKILL.md` and `docs/skills.md`.

## Tasks

- T1 (S1, S2) Stylometric engine (`paper_ai_metrics.py`) + unit tests (`test_paper_ai_metrics.py`)
- T2 (S3) CLI verbs `ai-audit` and `humanize` in `paper_cli.py` + tests
- T3 (S4, S5) Agent `ai-auditor.md` across harness mirrors + optional detector adapter
- T4 (S6) Command Center `/api/pdf/ai-audit` endpoint and PDF preview highlight hook
- T5 (S7) Verification on benchmark drafts, docs, and delivery

## Log

- L1 (2026-10-31, user): "revisa en que quedamos para terminar ultimas depuracion y sacar release, luego explora en la parte de redaccion del manuscrito que tecnicas de humanizacion estamos haciendo, y explora la inclusion de skill agente o mcp que estime la cuantifiacino de uso de ia, marca de agua de claude y todo lo que pueda respaldar identificacion de ia, para iterar con la skills y agentes que redactan buscando preservar estilo de redaccion sin marcar uso de ia" -> release 0.48.0 tagged and delivered; authorized to proceed with AI stylometry, quantification and humanization engine.
- L2 (T1-T4, parent): implemented `paper_ai_metrics.py` (burstiness CV, 40+ Claude words/clichés, formulaic patterns, triadic parallelism, lexical diversity TTR, F5 invariant verifier); wired into `paper_cli.py` (verbs `ai_audit` and `humanize` with `--block`, `--draft`, `--file`, `--apply`); registered agent `ai-auditor.md` across `.claude`, `.opencode`, `.pi`, `.agents`; added `/api/pdf/ai-audit` in Command Center `server.py`; updated `SKILL.md` and `docs/skills.md`; 16 targeted unit tests passing in `tests/test_paper_ai_metrics.py`, plus `test_agents.py` and `test_mcp_registry.py` green.
- L3 (T1-T5, parent): added manuscript-level audit `--all` in `cmd_ai_audit`, `--replacement` and `--inplace` in `cmd_humanize`, `write_block` automatic AI stylometry calculation and return (`aiStylometry`), whole-manuscript audit in `/api/pdf/ai-audit`, PDF toolbar `btnAuditAi` and active selection panel AI risk indicator with cliché hints and bilingual i18n support (`en` and `es`), `AGENT_STAGES` mapping for `ai-auditor` in `state_extractor.py`, updated 31 verbs in `papersmith-pi-flow.build.mjs`, Archify showcase re-finalization green, all 20 tests in `test_paper_ai_metrics.py` and 132 tests across full suite passing; bumped version to 0.49.0.
