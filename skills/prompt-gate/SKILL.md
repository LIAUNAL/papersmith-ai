---
name: prompt-gate
description: "Trigger: before any phase skill runs its `$ARGUMENTS` (every slash command applies it first), or when the operator asks to review, debug or improve a prompt (`/prompt-gate /<skill> <prompt>`). Measures the prompt's quality with a deterministic per-skill score (`python -m skills._core.command_center.prompt_gate check`) and a rubric from published prompt-engineering guidance; under the threshold or on a critical failure it alerts that the prompt is not clear, proposes an improved prompt and waits for approval, or asks clarifying questions when the operator's input is too thin, builds the prompt from the answers and launches it. Never invents requirements; a prompt carrying `[prompt-gate: approved]` passes untouched."
---

# Prompt Gate

The phase skills are only as good as the text they receive. This gate measures
that text before a skill acts on it, and when it is not clear enough it either
proposes a better-structured prompt for the operator to approve, or asks the
questions that make one possible. It runs the same way in every agent
(Claude Code, OpenCode, Pi, Antigravity) and from every surface: an agent
terminal, the dashboard's embedded terminal, and the dashboard's phase cards
(which also run it before launching; see "Dashboard" below).

## When it runs

1. **Automatically, on every phase slash command.** The body of each projected
   command (`.claude/commands`, `.opencode/commands`, `.pi/prompts`) and the
   Antigravity rules (`.agents/AGENTS.md`) tell the agent to apply this gate to
   `$ARGUMENTS` before following the skill.
2. **On request.** `/prompt-gate /<skill> <prompt>` reviews `<prompt>` as the
   input of `/<skill>`; on approval it follows `skills/<skill>/SKILL.md` with the
   improved prompt. `/prompt-gate <prompt>` without a skill reviews it with the
   generic rubric and names the skill it seems meant for.

Skip the gate entirely, and say nothing about it, when:

- the arguments carry `[prompt-gate: approved]` (strip the marker and use the
  rest as `$ARGUMENTS`): the operator already approved this prompt, in the
  dashboard or in this conversation;
- the operator explicitly asked to run the prompt as written ("launch as is",
  "tal cual", "sin revisar");
- the skill being run is `prompt-gate` itself.

When nobody can answer — a non-interactive run (`claude -p`, `pi -p`, a
scheduled or remote job) — never stop on a failed gate: follow the skill with
the prompt as written and state the score and the issues at the start of your
output, so the operator sees them afterwards.

## Step 1 — measure (deterministic, no model)

Run the score with the prompt on stdin, so no quoting can break it:

```bash
python -m skills._core.command_center.prompt_gate check --skill <skill> <<'PROMPT_EOF_7f3a91'
<the $ARGUMENTS, verbatim>
PROMPT_EOF_7f3a91
```

Use a delimiter that does not occur in the prompt (change its suffix if it
does): a line equal to the delimiter would end the input early and hand the
rest of the prompt to the shell.

It prints one JSON object: `score` (0-100), `threshold` (60), `verdict`
(`pass`/`fail`), `critical`, `issues` (`id`, `severity`, `message`) and `needs`
(what this skill's input contract asks for). An issue is `critical` (the skill
cannot start, e.g. `/plausibility` under two sentences, `/paper-ingestion`
without a path or URL, `/figure-review` without a figure id), `major` (-25) or
`minor` (-10). If the command cannot run (no Python 3.11), apply the rubric
below by reading and say that the score was not computed.

- **`pass`** → follow the skill with the prompt unchanged. Do not comment on the
  gate beyond, at most, one line with the score.
- **`fail`** → Step 2.

## Step 2 — judge with the rubric

Read the prompt against the skill's own input rules (`skills/<skill>/SKILL.md`,
its "input" or "arguments" section) and these dimensions. Each comes from
published guidance; none is a style preference:

| Dimension | Check | Source |
|---|---|---|
| Task | Would a newcomer with no context know exactly what to do? | Anthropic, prompting best practices ("be clear and direct") |
| Object and scope | Does it name what to act on (file, block, claim, figure, repository) and what is out of scope? | Google AI Studio, prompting strategies (constraints) |
| Context and motive | Does it say why, or what the result is for, when that changes the work? | Anthropic best practices ("add context"); The Prompt Report, arXiv 2406.06608 |
| Expected outcome | Is the deliverable or the end state stated, positively ("write X"), not only as prohibitions? | Anthropic best practices; OpenAI prompt engineering guide |
| Consistency | No contradictory requirements, no undefined terms, no leftover example text | The Prompt Report §5 (sensitivity to small changes) |
| Contract fit | Does it give what this skill needs to start (the score's `needs`)? | the skill's own SKILL.md |
| Restraint | No aggressive emphasis ("CRITICAL", "MUST") and no hand-written step lists the skill already owns | Anthropic best practices (over-application of emphatic rules) |

Then decide between two outcomes:

- **improve** — the prompt carries the operator's intent and the facts it needs;
  only its structure is weak (the task is buried, the object implicit, the
  outcome unstated). You can rewrite it without inventing anything.
- **clarify** — a fact only the operator knows is missing: the problem and the
  proposal of an idea, the target repository, the figure id, which block, which
  revision. Rewriting would mean guessing.

## Step 3a — improve: alert, propose, wait

Show the alert, in the operator's language:

1. One line: the prompt is not clear enough for `/<skill>` (score N/100,
   threshold 60), and the critical issue if there is one.
2. The issues, one line each, worded for the operator.
3. **The improved prompt**, in a fenced block, in the language the operator
   wrote it in, restructured: the task first, then the object and scope, then
   the constraints and the expected outcome. Keep it as short as the task
   allows; never add requirements the operator did not ask for.
4. **Preserved requirements**: every requirement, name, number, path and quoted
   phrase of the original, listed, each one present in the improved prompt.

Then ask for a decision and stop until it arrives. Use the agent's native
question tool when it has one (Claude Code `AskUserQuestion`; OpenCode's
`question` tool); otherwise print the options numbered and wait:

- **Approve and launch** → follow the skill with the improved prompt as
  `$ARGUMENTS` (this is the relaunch; do not score it again).
- **Edit** → take the operator's edited text, score it once more (Step 1), and
  launch it on `pass` or on the operator's explicit "launch".
- **Launch as is** → follow the skill with the original prompt.
- **Cancel** → stop; run nothing.

## Step 3b — clarify: ask, build, launch

Ask at most four questions, all at once, each with two to four concrete options
drawn from the workspace when possible (the repositories under
`implementations/`, the figures under `paper/Figures/`, the revisions under
`proposals/`, the blocks of `paper/main.tex`) plus a free answer. Use the native
question tool when the agent has one; otherwise print them numbered and stop
until the operator answers.

With the answers, build the prompt (same structure as Step 3a), show it in a
fenced block with the preserved requirements, and follow the skill with it. The
answers are the operator's approval; if an answer is still too thin to build a
prompt the skill can start from, ask once more about that gap only, never a
second full round.

## Rules

- **Never invent.** Every fact in the improved prompt comes from the original,
  from the operator's answers, or from a workspace file you read in this reply
  (and named). A proposal that drops or softens one of the operator's
  requirements is wrong.
- **One round.** One proposal or one set of questions; a second only for an
  edit or an answer that still leaves a gap. Never loop.
- **The operator launches.** Nothing runs on a failed prompt until the operator
  approves, edits, answers or says "launch as is".
- **Do not over-engineer.** A prompt that passes is never rewritten; an improved
  prompt is not longer than it needs to be.

## Dashboard

The phase cards score the prompt (`POST /api/prompt/check`) on every launch. On
`fail` the card shows the alert, and for the review this skill
delegates to the `prompt-reviewer` agent, which the command center runs headless
(`POST /api/prompt/review`) for an improved prompt or for questions; the
operator approves, edits, answers or launches as is in the card.

**Measure this before delegating.** The deterministic check must have run and
returned `fail`: the reviewer is never asked about a prompt that passed, and it
receives that check (`score`, `issues`, `needs`) with the prompt.

A prompt the card launches after the operator's decision (approved, launched as
is, or built from the answers) carries `[prompt-gate: approved]`, so the agent
does not gate it a second time; a prompt that passed the card's check goes
unmarked, and the agent scores it again, which is cheap and passes.

## When a delegated agent cannot be spawned

The review this skill delegates is defined in full by its own agent file:
`.claude/agents/prompt-reviewer.md`. When that agent cannot be spawned — the
command center finds no agent CLI (`claude`, `agy`, `pi`), or the run fails —
the phase card says so and offers to edit the prompt, launch it as is, or
cancel; the agent's own gate (Steps 1-3 above) still applies when the prompt
reaches the agent. In a session without sub-agents, perform the review inline:
read that agent's definition file and follow it as written, returning the same
JSON object. Its `tools:` line still bounds the review: it reads, and never
writes or launches. Say in the reply that the review ran inline and why the
agent could not be spawned.

## Headless reviewer contract

When the command center runs this gate headless (`.claude/agents/prompt-reviewer.md`),
the answer is exactly one JSON object:

```json
{
  "reply": "<one-sentence summary for the operator, in their language>",
  "verdict": "improve | clarify",
  "issues": ["<issue worded for the operator>"],
  "improved_prompt": "<the improved prompt, or empty for clarify>",
  "preserved_requirements": ["<each requirement of the original>"],
  "questions": [{"id": "q1", "question": "<question>", "options": ["<option>"]}]
}
```

`improved_prompt` is required for `improve` (and for `clarify` once answers are
given); `questions` is required for `clarify` before answers (1 to 4, each with
2 to 4 options) and empty otherwise.
