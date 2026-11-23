---
name: paper-type
description: "Trigger: when the operator accepts the plausibility report (plausibility hands over here), or asks which kind of paper to build (`/paper-type`). Scores the accepted idea against smith's catalogue of paper types (`python -m skills._core.paper_types.registry list`), has the paper-type-advisor agent relate each type to the idea, discusses the suggestion with the operator, and records the type and variant the operator agrees in `.papersmith/paper_type.json`. Never agrees on the operator's behalf and never changes the workspace layout."
---

# Paper Type

Plausibility answers whether the idea holds against the state of the art. This
skill answers the next question: what kind of paper the idea becomes. Smith
knows eight types (`skills/_core/paper_types/paper_types.json`): applied AI
method, review, observational and measurement study, experiment or
intervention, qualitative, participatory and consensus study, hardware,
laboratory and simulation science, and data resource. Some group variants that
share one flow and change only the reporting checklist. Applied AI, review and
observational and measurement studies already have a flow (a workspace line);
the others are planned.

The applied-AI flow does not depend on this skill: a workspace with no agreed
type stays on its line, as before.

## Step 1 — the accepted idea, on disk

If `.papersmith/plausibility.json` does not hold the idea the operator just
accepted, record it, with a delimiter that does not occur in the idea:

```bash
python skills/_core/paper_types/paper_type_cli.py accept --root . --by "<operator>" --idea-file - <<'IDEA_EOF_4c1e'
<the idea, verbatim>
IDEA_EOF_4c1e
```

`accept` also scores the idea. Otherwise score it again (the pool may have
changed): `python skills/_core/paper_types/paper_type_cli.py score --root .`.
Read the catalogue with `python -m skills._core.paper_types.registry list`.

## Step 2 — the advisor's reading

The score is lexical: it counts the words that signal each type. For the
judgement, this skill delegates to the `paper-type-advisor` agent: it relates
every type to the idea and proposes one, with its variant.

**Measure this before delegating.** `paper_type.json` must hold scores for the
current idea (its `idea_sha256` equals the accepted idea's). Hand the agent the
idea, the scores, the catalogue, and what plausibility found (the claim grades,
the SOTA families) as stated in this conversation.

## Step 3 — discuss and agree

Show the operator, in their language:

1. one line per type: its name, its score, the advisor's fit (`strong`,
   `partial`, `weak`, `none`) and one sentence relating it to the idea;
2. the suggested type and variant, and why;
3. for a planned type, that smith has no flow for it yet and the workspace
   keeps its current line.

Then ask the operator to agree a type, with the agent's native question tool
when it has one (Claude Code `AskUserQuestion`; OpenCode's `question` tool),
otherwise as numbered options, and stop until they answer: the suggested type
(and variant), the runner-up, another type, or "not now". The operator may also
answer the advisor's questions first; ask them, then propose again once.

## Step 4 — record the agreement

```bash
python skills/_core/paper_types/paper_type_cli.py agree --root . --type <id> [--variant <id>] --by "<operator>" --rationale "<one sentence>"
```

Read its `layout`:

- `current`: the workspace's line already fits; continue with ingestion.
- `switch:<line>`: the agreed type needs the `<line>` line. The workspace
  keeps its present line until the operator moves it with
  `smith kind set <id> --by "<operator>"` (it applies the line's section
  contracts and flow text, removes the other line's unedited files and keeps
  the edited ones, and refuses once a proposal revision or `paper/main.tex`
  exists unless `--force`), or starts a new workspace with
  `smith init --kind <line>`. Say so and let the operator decide; never run
  `smith kind set` on the operator's behalf.
- `planned`: no flow yet; the workspace keeps its line, and the agreement is
  on record for when the flow exists.

## Rules

- **The operator agrees.** Never run `agree` without their explicit choice in
  this conversation. "Not now" records nothing.
- **Never invent.** Relations cite the idea or the plausibility findings; a
  type is not suggested for words the idea does not contain.
- **Non-interactive runs** (`claude -p`, `pi -p`, scheduled jobs): record and
  score, report the suggestion, never agree.
- When the idea changes after an agreement, `score` marks it `agreed_stale`:
  bring the type back to the operator.

## When a delegated agent cannot be spawned

The reading this skill delegates is defined in full by its own agent file:
`.claude/agents/paper-type-advisor.md`. When that agent cannot be spawned — the
harness has no sub-agent mechanism, the agent is not registered in this
session, or the spawn itself fails — perform the reading inline: read that
agent's definition file and follow it as written, returning the same JSON
object. Its `tools:` line still bounds the reading: it reads, and never writes
or agrees. Say in the reply that the reading ran inline and why the agent
could not be spawned.

## Headless advisor contract

When the command center runs the advisor headless (the Paper type panel), the
answer is exactly one JSON object:

```json
{
  "reply": "<one-sentence summary for the operator, in their language>",
  "types": [{"type": "<id>", "fit": "strong | partial | weak | none", "variant": "<id or empty>",
             "relation": "<one sentence relating the type to the idea, in the operator's language>"}],
  "suggested": "<type id or empty>",
  "variant": "<variant id or empty>",
  "rationale": "<why, citing the idea>",
  "questions": ["<at most two questions when the idea is ambiguous>"]
}
```

`types` lists every catalogue type once, in catalogue order.
