---
name: idea-shaping
description: "Trigger: the operator has only a vague paper idea and wants help shaping it before plausibility (`/idea-shaping`, `smith idea`, the Idea tab). Asks sources and profile, proposes three topics and a two-sentence draft for `/plausibility`."
---

# Idea Shaping

**Scope.** When the operator has only a vague idea for a paper and asks for help shaping it before plausibility (`/idea-shaping`, `smith idea`, or the dashboard's Idea tab). An optional guided phase (lane 2a): the operator decides the sources (banco-lia, another bank MCP, or none), states a profile, experience and interests one question at a time, the engine proposes three candidate topics with evidence (the idea-guide agent adds its own suggestions and a draft), the operator picks or combines the engine's topics, and a two-sentence draft that passes the plausibility prompt gate is handed off as `/plausibility <draft>` only when the operator launches it. Records every step in `.papersmith/idea_brief.json` through the `smith idea` CLI.

`/plausibility` needs the idea in at least two sentences that name a problem
and a proposal. An operator with a vague idea may not have those sentences
yet. This skill is the optional phase before plausibility (lane **2a** of the
flow; it adds no new phase and locks nothing) that helps the operator get
there: it asks key questions, gathers evidence from the sources the operator
chose, and composes a draft idea the operator edits and approves.

The engine is `skills/_core/idea/`. Every step is recorded in
`.papersmith/idea_brief.json` by the CLI, never by hand: run `smith idea
<verb> [options]` from the workspace (or `python
skills/_core/idea/idea_cli.py <verb> [options]`, the same engine; `--json`
prints the brief as JSON). The dashboard's **Idea** tab (`smith ui`) shows the
same brief as a six-step stepper and records through the same engine, so the
operator may move between the conversation, the terminal and the tab at any
step. Read the current brief first with `smith idea show --json` and resume
from the first step it does not hold.

**Language.** Talk to the operator in their language. Everything recorded in
the brief (answers, topics, the draft) and every artifact stays English;
translate the operator's answers faithfully when recording them.

**One question at a time.** Ask each question with the agent's native question
tool when it has one (Claude Code `AskUserQuestion`; OpenCode's `question`
tool), otherwise as plain text, and stop until the operator answers. A skipped
question is recorded as empty, never guessed.

## Step 1 — sources (the operator decides)

Ask the operator which knowledge bank, if any, this phase may use, and record
the answer before anything else. List the choices with `smith idea bank
--list` (the managed `banco-lia` and every other server of the workspace's
`.mcp.json` that smith does not manage). Offer exactly three kinds of answer:

1. **`banco-lia`** — the lab's bank, managed by smith. Record it with `smith
   idea bank --choose banco-lia`; the choice probes the server. When it is
   unreachable, show the operator the recorded `reason` and let them retry or
   change the choice.
2. **Another bank MCP** — one of the listed servers, or a new one the operator
   adds with `smith idea bank --add NAME --command ...` (stdio) or `smith idea
   bank --add NAME --url ...`. Probe it with `smith idea bank --probe SERVER`
   and record it with `smith idea bank --choose SERVER`. The probe lists its
   tools: a server that exposes `search_bank` (and optionally `taxonomy`) is
   **compatible** and is searched like banco-lia by the panel and the CLI; any
   other server is **conversation-only**: this skill may query it through its
   own `mcp__<server>__*` tools in this session, and the panel says it cannot
   search it. Say which of the two it is.
3. **None** — `smith idea bank --choose none`. The phase then uses only the
   operator's profile, experience and interests, OpenAlex and (with a key)
   Asta. No bank is queried, by the engine or by this skill.

The operator may change the choice later; record the change the same way.

## Step 2 — profile

Ask for one way to find the operator as an author: an ORCID iD, an OpenAlex
author id, a Google Scholar profile link, or their name. Record it with
`smith idea profile --orcid ID`, `--openalex ID`, `--scholar URL` or `--name
NAME`. The engine looks the author up in OpenAlex and summarises their works
into topics. A Google Scholar link is used **only to find the author's name**
in OpenAlex or ORCID: never fetch, scrape or read Scholar pages. When the
lookup fails (offline, no match) the brief records the reason; say so and
continue without a profile. The operator may also skip this step.

## Step 3 — experience

Ask, one at a time: the research level (`student`, `early-career`,
`experienced`, `senior`), the methods they master, the data, equipment or
compute they can access, and the time they have. Record each answer as it
comes with `smith idea experience --level LEVEL`, `--methods LIST`,
`--resources LIST` or `--time TEXT` (lists are comma-separated; one answer
never erases the others).

## Step 4 — interests

Ask for 3 to 5 keywords, the application domain, and one paper they admire
(title or DOI), one question at a time. Record them with `smith idea
interests --keywords LIST`, `--domain TEXT` and `--admired TEXT`.

## Step 5 — candidate topics

`smith idea topics --propose` computes three deterministic candidates, `t1`
to `t3` (`--n N` for another number), from the interests, the profile topics
and, when the chosen bank is compatible, the bank's hits, with OpenAlex volume
counts of the last four years when reachable, and records them in the brief.
These engine topics are the only topics the brief holds. This skill then
delegates to the `idea-guide` agent, which reads the brief and returns its own
three topic suggestions, each with a rationale and its evidence, and a draft.

**Measure this before delegating.** `smith idea show --json` must hold a bank
choice (`bank.choice` is not empty) and at least one interest keyword; a
profile and experience are optional. Without a choice there is no rule for
which sources the topics may cite, and without keywords there is nothing to
shape. When the chosen bank is conversation-only, query it yourself through
its `mcp__<server>__*` tools first and hand the agent the hits you used, each
with the tool and query that returned it.

Show the operator, in their language, one card per engine topic: its id,
title, rationale and every evidence item with its source. Show the guide's
suggestions beside them in the conversation, labelled as the guide's; no verb
records them. Then ask the operator to pick one engine topic, combine two or
three, or ask for new candidates (`smith idea topics --propose` again, for
example after changing the interests; it clears the previous pick). Record the
choice with `smith idea topics --choose t1,t3`. When the operator prefers an
angle from a guide suggestion, record it with the closest engine topics and
the angle in their words: `smith idea topics --choose t1 --note TEXT`.

## Step 6 — draft, gate and handoff

Compose the draft with `smith idea draft --compose`, or record the guide's
draft (or the operator's edit of it) with `smith idea draft --text -` (the
text on stdin). Both record the draft, unapproved, with its prompt-gate
result: the plausibility rules (at least 15 words and two sentences, naming a
problem and a proposal), its score and what is missing. The draft states, in
at least two sentences, the problem and the proposal, built from the chosen
topics. `smith idea draft --check` only scores, the `--text` given or else
the recorded draft, and records nothing: use it to try an edit before
recording it. Show the operator the draft and the gate result; they edit it
until it passes and they agree with it, and the text they keep is recorded
with `--text -`.

When the operator approves it, record the approval with `smith idea approve`
(it refuses while the gate fails, and prints the handoff line); `smith idea
handoff` prints the same `/plausibility <draft>` again later. Show that line
to the operator: typing it, or pressing **Launch plausibility** in the Idea
tab, is the operator's decision. Never run `/plausibility` on the operator's behalf.
The approved draft is English, like the whole brief: once plausibility is
accepted, `/paper-type` records this same text in `.papersmith/plausibility.json`
(`paper_type_cli.py accept` without `--idea-file` takes it), so the dashboard
shows an English idea on an English board.

## Rules

- **Evidence names its source.** Every topic and the draft name where they
  came from: `bank:<server>`, `openalex`, `profile`, `operator` or `guide`.
  A topic with no evidence is labelled as the guide's suggestion, never
  presented as found in the literature.
- **Nothing from a bank the operator did not choose.** With the choice `none`,
  no bank is queried and no bank item appears in a topic or the draft.
- **Bank items are continuity context, never SOTA evidence.** Plausibility
  treats a draft built from bank items like any other idea, and its own scout
  decides what enters the SOTA pool.
- **Never invent.** A count, a paper or an author's topic is reported only as
  the engine or a tool returned it.
- **Record through the CLI.** Never hand-edit `.papersmith/idea_brief.json`.
- **Non-interactive runs** (`claude -p`, `pi -p`, scheduled jobs): run `smith
  idea start --answers FILE.json --bank banco-lia|none|SERVER` (without
  `--yes`, which approves the draft when the gate passes) when the operator
  gave an answers file, report the topics and the draft, and never approve or
  hand off.

## Refusals

A refused verb prints `<CODE>: <message>` (with `--json`, `{"ok": false,
"error": <CODE>, "message": ...}`) and exits 1; the refused step is not
recorded. Tell the
operator the message and what to do; never work around it by editing a file.

- Brief and steps: `BRIEF_UNREADABLE`, `NOT_A_WORKSPACE`, `ANSWERS_UNREADABLE`,
  `LEVEL_UNKNOWN`, `STEP_UNKNOWN`, `STEP_INVALID`.
- Sources: `BANK_CHOICE_INVALID`, `SERVER_MISSING`, `SERVER_UNKNOWN`,
  `SERVER_MANAGED`, `SERVER_EXISTS`, `SERVER_NAME_INVALID`, `SERVER_SPEC`,
  `FIELD_TYPE`, `MCP_CONFIG_UNREADABLE`, `MCP_CONFIG_SYMLINK`.
- Topics: `TOPICS_ABSENT`, `TOPIC_MISSING`, `TOPIC_UNKNOWN`.
- Draft and handoff: `DRAFT_EMPTY`, `DRAFT_TOO_LONG`, `DRAFT_ABSENT`,
  `DRAFT_GATE_FAILED`, `DRAFT_NOT_APPROVED`.

## When a delegated agent cannot be spawned

The reading this skill delegates is defined in full by its own agent file:
`.claude/agents/idea-guide.md`. When that agent cannot be spawned — the
harness has no sub-agent mechanism, the agent is not registered in this
session, or the spawn itself fails — perform the reading inline: read that
agent's definition file and follow it as written, returning the same JSON
object. Its `tools:` line still bounds the reading: it reads, and never writes
the brief or chooses for the operator. Say in the reply that the reading ran
inline and why the agent could not be spawned.

## Guide contract

The `idea-guide` agent returns exactly one JSON object. No verb stores its
`topics`: they are suggestions shown to the operator in the conversation, and
the brief's topics stay the engine's (`topics --propose`). What this skill
records is the operator's choice among the engine's topics (`topics --choose
t1,…`, with the angle of a guide suggestion in `--note` when the operator
wants it) and the draft the operator keeps (`draft --text -`):

```json
{
  "reply": "<one-sentence summary for the operator, in their language>",
  "topics": [{"id": "t1", "title": "<English>", "rationale": "<English, citing the brief>",
              "keywords": ["<English>"],
              "evidence": [{"source": "bank:<server> | openalex | profile | operator | guide",
                            "detail": "<what it is>", "count": null, "url": null}]}],
  "draft": {"text": "<two or more English sentences: the problem, then the proposal>",
            "source_topics": ["t1"]},
  "questions": ["<at most two questions when the brief is too thin>"]
}
```

`topics` holds three suggestions, `t1` to `t3` in the guide's own numbering,
which is not the brief's: never pass a guide id to `topics --choose`.
