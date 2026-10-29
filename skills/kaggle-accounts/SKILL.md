---
name: kaggle-accounts
description: "Trigger: check that this project's Kaggle accounts actually authenticate, take in new credentials left in kaggle-inbox/, or remove accounts. Two interactive options — validate or remove. A third command, `materialize`, exists for code rather than a human: it writes one worker's stored credential to a plain-text token file and prints back where, never what. Stdlib-only, no venv."
---

# Kaggle Accounts

Prove the project's Kaggle accounts work, and keep only the ones that do.

The user supplies credentials by hand — a `kaggle.json`, or a `.txt`/`.md` list
with one `username key` per line, left in `kaggle-inbox/`. That being manual is what this
is *for*. The work worth automating is not moving a file; it is answering **does
this account actually authenticate**, which is a question only Kaggle can answer
and one that stops being true over time.

## The objective flow

**Why this skill was invoked, and where it has to arrive.** Declared here and in
`OBJECTIVE_FLOW`, held equal by a test. `list` answers *which accounts are
there*; this answers *what is this for*, which a listing never implies — an
account is in the store because somebody put it there, not because it works.

**Purpose:** have every credential this project holds proven against the service
that decides — not stored, not once-working, currently proven.

| Stage | Establishes | Behind you when |
| --- | --- | --- |
| `taken-in` | What the user handed over is in the store, one row at a time, so a bad row never costs the rows around it | the inbox gave up everything it held and was consumed, or kept because rows are still in it |
| `proven` | Each stored account was asked of the service, under whichever of the two token schemes it actually uses | every account carries a verdict from this run |
| `decided` | What happens to the ones that stopped working, which is the user's call and never a side effect of asking | this is the arrival; it is behind nobody |

**Arrival:** every account carrying a current verdict, and the failures answered for rather than merely reported.

**Arrival is every account carrying a CURRENT verdict, not a command that ran.**
A stored credential is a claim and only the service settles it — and a verdict
decays, since tokens are rotated and expired, so "it authenticated once" is not
arrival either. A session that runs `validate`, sees a failure reported and
stops has not arrived: a dead credential is reported and never removed here,
deliberately, because removing it is the user's other option and not a side
effect of asking whether it still works.

**Two stops are a person's:** consenting to validate at all, because it writes —
it stores credentials and consumes the inbox — and deciding what happens to an
account that stopped working.


## Accepted operations

The closed set this CLI accepts. Derived from `accounts_cli.py`'s own argparse
roster on 2026-09-14 by running it, never transcribed from memory: anything not
in this table is refused, and the refusal names these five.

| Operation | What it does |
|---|---|
| `list` | show stored accounts, never their keys |
| `discover` | find `kaggle.json` files to offer as choices |
| `validate` | re-check every stored account and take in whatever is in the inbox |
| `remove` | delete stored accounts by username |
| `materialize` | write one worker's credential to a config directory, non-interactively |

Two things stay true about auditing this surface: the instrument that first
found the roster missing **cannot be declared** in the auditor's own doctrine,
for a reason recorded there; and this skill holds live credentials, so any audit
of it stays **read-only**.

## Activation Contract

Invoking this skill asks **one** interactive question before doing anything:

1. Run `list` first, so the question is asked against what is actually there.
2. Ask with `AskUserQuestion` — never a question typed into the reply:
   - **Validate accounts** — re-check everything stored, and take in whatever is
     in the inbox.
   - **Remove accounts** — delete accounts. Drop this option when the store is
     empty; there is nothing to remove.

**Ask even when only one option is left.** Dropping the remove option does not
turn the question into a formality with an obvious answer, and "there is no
branch to choose, so I will just run it" is the wrong reading. The question is
not routing — it is consent. `validate` **writes**: it puts credentials in the
store and it *deletes* the user's file from the inbox once that file has given
up everything it held. Nothing here is read-only, so nothing here runs
unprompted. If the user picks nothing, do nothing.

Never infer the intent from context either: a session that mentions Kaggle is
not a request to touch credentials, and finding a file in the inbox is not
permission to consume it.

**Every question is a selection, not prose.** The opening choice, and the pick
of which accounts to remove, are both interactive prompts built from what the
CLI reports. A question written into the reply asks the user to retype something
they could have clicked, and a retyped username is a typo waiting to delete the
wrong account.

A prompt can only offer what something enumerated first, so each question has a
command behind it: `list` for the accounts, `discover` for the credential files.
If a question has no command behind it, it is the wrong question.

## Environment

**None.** The script is stdlib-only — no `.venv`, no `setup.sh`, no
`requirements.txt`, no `pip install kaggle`. Validation is an authenticated
HTTPS request, which `urllib` already does. Creating a virtualenv to hold zero
packages is ceremony, so there is none. Requires Python 3.10+ and a network
connection.

Two Kaggle token formats are live at once and they do not authenticate the same
way: the classic 32-hex key is the password half of Basic `username:key`, while
the newer prefixed token is a **bearer** token that Basic refuses outright. So a
401 from the first scheme is a reason to try the other, not a verdict — trying
only one reports a working account as expired, which is the single wrong answer
this command exists to prevent.

A consequence worth stating: a bearer token carries its own identity, so what it
proves is that the *token* works. The username beside it is a label the store
files it under, and Kaggle is never asked whether the two belong together. Under
the classic format the pairing is what gets proven; under the new one it cannot
be, so a mislabelled row authenticates and is stored under the wrong name.

## How to execute

```
python3 skills/kaggle-accounts/scripts/accounts_cli.py <command>
```

- `validate` — re-check every stored account, take in the inbox, keep what passes.
- `validate --account <username> [--json]` — re-check only that stored account
  (repeatable) and print a verdict per account, never a key. It takes in nothing
  and writes nothing, so it is the read-only probe `remote_cli preflight` runs
  per worker; it still asks the service, so it needs the network. `--json`
  without `--account` is refused (`JSON_NEEDS_ACCOUNT`, exit 2) before anything
  is read.
- `remove <username>…` — delete stored accounts, and the token file each one materialized.
- `list [--json]` — stored accounts, never their keys.
- `discover [--json]` — credential files lying around and the accounts in each.
- `materialize --worker <username> [--into <dir>] --json` — write that
  worker's credential to a token file and print back where. For code, not
  for a human: it asks nothing, and it prints a destination, never a value.

## Validating

One command does the whole thing: `validate`.

- **Every stored account is re-checked.** This is the half that has to keep
  happening. Tokens get expired and rotated, and an account that quietly stopped
  working does not fail when it was added — it fails hours later in the middle
  of a run.
- **Everything in `kaggle-inbox/` is taken in**, and only what authenticates is
  stored. A list is judged line by line: the rows that pass are stored, the
  rows that fail are reported by line number, and one bad row never costs the
  rows around it.
- A username already stored has its key replaced, which makes rotating an
  expired token the same command as adding one.

Only the inbox is taken in automatically. That folder means "these are for you";
a `kaggle.json` sitting in `~/Downloads` shows up in `discover` and is taken only
when named, because finding a file in somebody's home directory is not the same
as being handed it.

**A dead credential is reported, never quietly dropped.** Removing an account is
the user's other option, not a side effect of asking whether it still works.

Report which accounts passed, which stopped working, and which new ones were
stored or rejected. Then let the user decide what to do about the failures.

## Removing

Removal is a **selection**, never an inference:

1. Run `list --json` to get the usernames.
2. Present them as an **interactive multi-select** (`AskUserQuestion`), one
   option per stored account, and let the user mark what goes. Never ask them to
   type the usernames back.
3. Run `remove` with exactly the chosen usernames.

If a username does not exist the whole batch is refused. A typo that silently
removes only the names it happened to match is worse than removing nothing,
because the report would read as success.

The multi-select *is* the confirmation. Deleting a credential destroys no
account and loses no work; the token can be regenerated on Kaggle.

## Where credentials come from

Never ask for a token, and never ask for a path in prose. There are two ways in,
and neither goes through the conversation:

- **The inbox.** `kaggle-inbox/` at the repository root exists for exactly this
  and ships already ignored by git. Drop in a `kaggle.json` (kaggle.com →
  Settings → API → *Create New Token*) or a `.txt`/`.md` with one
  `username key` per line — comma, colon, tab or space between them, `#`
  headings and blank lines skipped, markdown bullets and table pipes stripped,
  and a table's header row skipped by the `|---|` under it. Then validate.

  **Both fields on the same line.** Username on one line and token on the next
  is not read as a pair: for a list of several accounts that shape is ambiguous,
  and guessing at it would pair the wrong token to the wrong account in silence.

  A delimiter the user typed wins over whitespace, so a field may contain a
  space. Splitting on every separator at once would mean no field ever could.

  **A name with a space is the display name, not the username**, and the report
  says exactly that rather than counting fields. The two sit next to each other
  in Kaggle's own UI, so copying the wrong one is the ordinary mistake, not a
  typo — and it cannot be repaired later, since a bearer token authenticates
  without Kaggle ever saying whose it is. The username is the one in the profile
  URL, `kaggle.com/<username>`.

  A `.txt` or `.md` list is looked for **in the inbox only.** Reading every text
  file in somebody's Downloads to see whether it happens to hold credentials is
  not a thing to do quietly; putting one in the inbox is what opts it in.

- **A terminal prompt**, for a token that lives in a password manager or a
  download that is long gone:

  ```
  python3 skills/kaggle-accounts/scripts/accounts_cli.py validate --interactive
  ```

  It asks for the username, then the key with the echo off. The key is in no
  message, no argv, and no shell history.

**Tell the user to run that one themselves, in their own shell. Never run it for
them.** It refuses when stdin is not a terminal precisely so that an agent
running it hits an error instead of finding a way — but the refusal is the
backstop, not the rule. There is deliberately no `--key` flag either: a secret on
a command line is in the process list and in the shell history, which is the same
leak wearing a different hat.

If a user pastes a token anyway: do not store it, and say plainly that it is in
the transcript for good and should be expired at kaggle.com → Settings → API →
*Expire API Token*. Say it once. Then point at the two ways in — the point is to
get them a working credential, not to make them feel caught.

## The inbox is transit, not storage

A file that came from `kaggle-inbox/` and gave up **everything it held** is
deleted, and the report says so: the same token sitting in two places in
plaintext is exposure with nothing bought.

Everything it held, not most of it. Deleting a list because four of its five
rows worked would take the fifth — the one that still needs a retry — with it.
A list with any row left is kept, and the report says how many did not go in.

Only the inbox, too. A file the user keeps in `~/Downloads` or anywhere else is
theirs: report that it still holds tokens and leave the deleting to them.

## Keys never cross into the agent

`list` prints usernames, never keys, and `--json` omits them too. So an agent can
offer a choice of accounts, and remove one, without a secret ever entering its
context. Whatever launches runs reads the store file directly.

Never `cat`, `bat`, `rg`, or otherwise read `store/accounts.json` to answer a
question about which accounts exist. `list` answers that without the keys.

## Where credentials live

`store/accounts.json`, inside the skill, `0600`, ignored by `store/.gitignore`.
An account is its Kaggle username; there is no alias, because a second name for
the same thing gives you two ways to refer to one account and one of them is
always the wrong one.

The store is inside the repository, so that ignore rule is the whole protection
— and it is enforced as a **precondition**: before writing, the script asks
`git check-ignore` whether the path is genuinely ignored and refuses to write if
it is not. It asks git for the effective answer rather than checking that a file
exists, because an ignore rule can be present and still not match. Outside a git
checkout it falls back to requiring the `.gitignore`.

Both ignore files are committed so the protection exists *before* the first
credential is written rather than after.

Writes are atomic: a truncated write would cost every credential in the file,
not just the one being added.

## What `materialize` writes

`materialize` is the one way a credential this store holds reaches another
process, and the file it writes has a **shape another skill depends on**. That
shape belongs here, in the doctrine of the skill that owns it, not only in a
docstring: the consuming skill and this one disagreed about it for as long as
they did precisely because there was no place the two statements could be put
side by side. Every row below is re-derived from a real `materialize` run by
this skill's own test suite — a row that stops being true fails a test.

| # | id | Property | Held to code by |
|---|---|---|---|
| 1 | `destination` | `store/workers/<username>/token`, unless `--into <dir>` names another directory — then `<dir>/token` | `worker_token_path()`, the one place that spelling exists |
| 2 | `content` | The token itself and nothing else: no JSON wrapper, no `username` field, no surrounding quotes | `cmd_materialize()` |
| 3 | `trailing-newline` | Exactly one `\n` after the token. The consumer strips it — a newline inside an `Authorization` header is a malformed header, not a credential | `cmd_materialize()` |
| 4 | `encoding` | UTF-8 | `cmd_materialize()` |
| 5 | `file-mode` | `0600`, set on the descriptor before the first byte is written | `cmd_materialize()` |
| 6 | `directory-mode` | `0700` | `cmd_materialize()` |
| 7 | `atomicity` | `mkstemp` inside the destination then `os.replace`, so a reader finds the old file or the new one and never a partial one; no `.kaggle-` temporary file survives | `cmd_materialize()` |
| 8 | `removal` | `remove <username>` deletes it, before the store entry is saved | `cmd_remove()` |

**The consumer reads the value, not the path.** Kaggle's own client
authenticates `KAGGLE_API_TOKEN` by value and checks no path, so whatever points
a client at this file ends up reading it and sending its stripped content. That
is a fact about the client, not a choice this command makes — but it is why row 3
matters and why this file holds a bare token rather than the legacy
`kaggle.json` container, which routes a bearer token through a Basic-auth path
and answers 401 for every account regardless of validity.

## Decision Gates

| Situation | Action |
| --- | --- |
| Invoked | `list`, then the interactive validate-or-remove selection |
| Nothing stored | Offer validate only — and still ask; `validate` writes |
| Only one option is available | Still ask. The question is consent, not routing |
| User picks nothing | Do nothing. Nothing was written and nothing was consumed |
| User picks validate | Run `validate`; report passed, failed, stored, rejected |
| A stored account stops authenticating | Report it; do not remove it — that is the user's other option |
| A row names a display name (has a space) | Say it is the display name and point at the profile URL; never "wrong field count" |
| Some lines of a list fail | Store the rest; report each by line number, never the line |
| Kaggle unreachable while validating | Report it as unreachable, not as invalid; store nothing |
| Nothing to validate | Say to drop a file in `kaggle-inbox/` and run again |
| User picks remove | `list --json`, multi-select, then `remove` |
| A username to remove does not exist | Refuse the whole batch; change nothing |
| User pastes a raw token | Do not store it; say to expire it, once; then point at the two ways in |
| Asked to run `validate --interactive` for them | Refuse: it is theirs to run in a terminal, and the command refuses anyway |
| An inbox file gave up everything it held | It is deleted; report that it was consumed |
| An inbox file has rows left | It is kept; report how many did not go in |
| `discover` warns the inbox is not ignored | Relay it; say to restore `kaggle-inbox/.gitignore` before dropping a token |
| A `.gitignore` missing or not matching | Refuse to write; say to restore it |
| Store file unreadable or malformed | Report it; write nothing |
| Asked which accounts exist | Run `list`; never read the store file directly |
| Code needs one account's credential as a file | `materialize --worker <username> --json`; report the destination, never the value |
| An account is removed | Its materialized token file goes with it; say the credential file was deleted too |

## Output Reporting

Report only what changed or what was learned: which accounts authenticate, which
stopped working, which were stored, rejected or removed. Never a key, never a
store dump, never a path listing.

**Speak the user's language.** The questions, the account listing, and the
report go in the language the user is writing in, not the language of this
document. The script's stdout stays English: it is data to read, not a message
to relay verbatim. Usernames, paths, and flags are never translated.
