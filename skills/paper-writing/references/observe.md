## No claim without a source that holds it: `resolve` (observing before declaring)

**Observing before declaring: the `insumos-observer` agent.** For the ten
facts an outside observer can check against evidence (`formulation`,
`dataset`, `experimental-design`, `implementation`, `results`, and the study
facts `protocol`, `sample`, `outcomes`, `analysis-plan` from `protocol/` and
`participant-flow` from `study/flow.json`), this skill
delegates to the `insumos-observer` agent — it reports satisfaction and
evidence, never a value, and never calls `declare` itself. Its JSON report
is shuttled to a file and read back through `observe`, which validates it
against the observable-fact schema before a human runs `declare` against
it — the same shuttle shape `write --draft <path>` already establishes for
the redactor's account, never trusting an agent's account unjudged.

**On a harness with no Task-tool delegation** (OpenCode projects these
agents as `mode: subagent` per `OPENCODE.md`, Antigravity reads them from
`.agents/agents/` per `.agents/AGENTS.md`, and Pi reads its projection only
when the third-party `pi-subagents` package is installed per
`.pi/APPEND_SYSTEM.md`; a Pi session without that package, or any session
whose agent is not registered, has none):
run this stretch in-process, as one step, in the same order, holding to the
same measure-before-delegating gate before starting. The tool boundary the
agent would have enforced (`insumos-observer` cannot write to disk) becomes
the orchestrator's own discipline to hold, not a structural guarantee —
treat any action that would have needed a scoped-out tool as a stop, not a
workaround.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py observe \
    --report insumos-observer-report.json \
    --proposals proposals --experiments experiments \
    --implementation implementations/<target-repo>
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `observe --report <path> [--proposals <dir>] [--experiments <dir>] [--implementation <dir>] [--protocol <dir>] [--flow <file>]` | Read-only: validates an `insumos-observer` report against the ten observable facts and the `implementation`/`results` evidence-conflation guard, THEN reconciles it against a real disk measurement this process takes itself for every root given; writes nothing and never calls `declare` | `OBSERVATION_REPORT_UNREADABLE`, `NOT_AN_OBSERVABLE_FACT`, `EVIDENCE_CONFLATED`, `OBSERVATION_DISK_CONFLICT` |

**The skill measures source availability itself — it does not trust an
agent's word for it, and it does not trust a human's memory either.**
`--proposals`/`--experiments`/`--implementation`/`--protocol`/`--flow` each
name a root this process measures directly (`Path.iterdir()`, gitignore-blind by
construction — the same mechanism `ingested_papers` already uses for
`guidance/`, never a shell call, never `fd`/`rg`, both of which honor
`.gitignore` by default and can report a genuinely populated directory
empty). Pass all three you can: when a fact's own source root
(`formulation`/`dataset` from `proposals/`, `experimental-design` from
`experiments/`, `implementation`/`results` from the target repository, the
study facts from `protocol/`, `participant-flow` from `study/flow.json`, a
file that is available when it is non-empty) is
measurably non-empty right now while the report claims that fact
UNSATISFIED with no evidence at all, `observe` refuses
`OBSERVATION_DISK_CONFLICT` naming the exact disagreement — never averaged
into a report that simply repeats the agent's claim. A root you omit is
never measured and never reconciled against; omitting `--implementation`
(no fixed default — its path varies per target) only skips reconciling
`implementation`/`results`, it never widens what the other two check.
`--proposals`/`--experiments` also have no default, deliberately: both are
long-lived, ongoing directories in this repository's own real layout,
routinely non-empty for reasons unrelated to any one paper's current
facts, so silently defaulting to them would reconcile against content that
says nothing about THIS observation.
