# Turn Snapshots Specification

## Purpose

Agent edits apply directly to disk; each turn is protected by a snapshot, a changed-files list and whole-turn undo.

## Requirements

### Requirement: Pre-turn snapshot

The system MUST snapshot the project before each agent turn starts.

#### Scenario: Snapshot taken

- GIVEN the user sends a message
- WHEN the turn starts
- THEN a snapshot exists before the agent can write

#### Scenario: Snapshot failure

- GIVEN the snapshot cannot be created
- WHEN the turn is about to start
- THEN the turn does not start and a readable error is shown

### Requirement: Changed-files list

At turn end, the chat MUST list files the turn created, modified or deleted, derived from comparing disk with the snapshot.

#### Scenario: Changes listed

- GIVEN the agent modified `a.tex` and created `b.tex`
- WHEN the turn ends
- THEN the chat lists `a.tex` modified and `b.tex` created

#### Scenario: No changes

- GIVEN the turn changed nothing
- WHEN it ends
- THEN the chat states no files changed and offers no undo

### Requirement: Whole-turn undo

The user MUST be able to undo a whole turn, restoring all changed files to their snapshot state, removing created files and restoring deleted ones.

#### Scenario: Undo turn

- GIVEN a turn modified, created and deleted files
- WHEN the user undoes it
- THEN the project matches the snapshot for those files

### Requirement: Undo protects later user edits

If files changed after the turn ended, the user MUST be offered three choices: cancel, undo the remaining files and keep the edited ones, or overwrite the edits. The system MUST take a snapshot of the current state before any undo writes.

#### Scenario: Later edit

- GIVEN the user edited `a.tex` after the turn
- WHEN the user requests undo
- THEN `a.tex` is named and the three choices are offered
- AND no file changes until the user chooses

#### Scenario: Keep edited files

- GIVEN `a.tex` was edited after the turn and `b.tex` was not
- WHEN the user chooses to undo the remaining files
- THEN `b.tex` is restored and `a.tex` keeps the user's edits

#### Scenario: Safety snapshot

- GIVEN the user confirms an undo
- WHEN undo begins
- THEN a snapshot of the current state exists before the first write

### Requirement: Snapshot scope and retention

Snapshots MUST exclude internal state, `.git/`, `node_modules/`, provisioned agent directories, provisioned writing guides under `.caztor/guides/`, and large binary build artifacts, MUST be stored under `.caztor/`, and SHOULD retain the last 20 turns.
(Previously: provisioned writing guides were not named in the exclusions)

#### Scenario: Retention

- GIVEN 20 retained turns
- WHEN a new snapshot is taken
- THEN the oldest is discarded and its undo is shown as unavailable

#### Scenario: Excluded paths

- GIVEN `node_modules/` and `.git/` exist
- WHEN a snapshot is taken
- THEN neither is included

#### Scenario: Guides excluded

- GIVEN provisioned guides exist under `.caztor/guides/`
- WHEN a snapshot is taken
- THEN no guide file is included
- AND a guide rewritten by provisioning never appears in a changed-files list or an undo
### Requirement: Undo order

Undo MUST apply to the most recent turn that has not been undone; after it is undone, the previous retained turn MUST become undoable. Older turns MUST show undo as unavailable until then.

#### Scenario: Sequential undo

- GIVEN turns 1, 2 and 3
- WHEN the user undoes turn 3
- THEN turn 2 becomes undoable and turn 1 shows undo as unavailable

### Requirement: User edits during a turn

A file changed only by the user during a turn MUST NOT appear in that turn's changed-files list. A file changed by both MUST be listed and MUST be treated as a conflict on undo.

#### Scenario: User-only edit

- GIVEN the user edits `c.tex` while the agent edits `a.tex`
- WHEN the turn ends
- THEN only `a.tex` is listed

#### Scenario: Both edit

- GIVEN the user and the agent both change `a.tex`
- WHEN the turn ends and undo is requested
- THEN `a.tex` is listed and handled as a conflict

### Requirement: Snapshot limits

A file larger than 5 MB MAY be excluded from undo and MUST then be reported as not protected. When a snapshot exceeds 200 MB of new content or 5,000 files, the turn MUST still run and the chat MUST warn which files are not protected.

#### Scenario: Oversized file

- GIVEN a 6 MB file in the project
- WHEN a snapshot is taken
- THEN the file is reported as not protected

#### Scenario: Snapshot over limit

- GIVEN a project over 5,000 files
- WHEN a turn starts
- THEN the turn runs and the chat warns which files are not protected

### Requirement: Revert note

After an undo, the next message to the agent MUST state which files were reverted.

#### Scenario: Note after undo

- GIVEN a turn was undone restoring `a.tex`
- WHEN the user sends the next message
- THEN the message given to the agent states that `a.tex` was reverted

### Requirement: Interrupted turns

A stopped or failed turn MUST still list changes and allow undo.

#### Scenario: Stopped turn

- GIVEN the user stopped a turn after one file was edited
- WHEN the turn ends
- THEN the edit is listed and undoable
