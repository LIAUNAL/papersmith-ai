## A diagram that compiles, or says why: `render` and `place` (before delegating `diagram-author`)

**Measure this before delegating (diagram-author):** confirm the block's
`figure:` declaration is already readable (`contract --file <path>`) and,
when it declares a `components_from` fact, that fact is already declared
as a JSON array of strings (`plan` reports it fixed; `declare --fact <id>
--value '["a", "b"]'` if not) — an agent asked to draft a diagram against
an obligation it cannot read cannot distinguish "no components yet" from
"cannot be checked."

**On a harness with no Task-tool delegation** (OpenCode projects these
agents as `mode: subagent` per `OPENCODE.md`, Antigravity reads them from
`.agents/agents/` per `.agents/AGENTS.md`, and Pi reads its projection only
when the third-party `pi-subagents` package is installed per
`.pi/APPEND_SYSTEM.md`; a Pi session without that package, or any session
whose agent is not registered, has none):
run this stretch in-process, as one step, in the same order, holding to the
same measure-before-delegating gate before starting. `diagram-author`'s own
doctrine says it only touches its `<id>.tex`/`<id>.diagram.json` pair, but
its `tools:` grant (`Read, Write, Edit, Bash`) doesn't structurally enforce
that — on a no-Task-tool harness this is now the orchestrator's discipline
to hold, same as it always doctrinally was, just without an isolated
process backing it. Treat any action that would touch a different file as
a stop, not a workaround.
