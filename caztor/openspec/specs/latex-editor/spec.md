# LaTeX Editor Specification

## Purpose

Editing LaTeX and BibTeX text with autosave and safe handling of external changes (user and agent can write the same file).

## Requirements

### Requirement: Syntax highlighting

The editor MUST highlight LaTeX and BibTeX syntax for `.tex`, `.sty`, `.cls` and `.bib` files.

#### Scenario: Highlight

- GIVEN `main.tex` is open
- WHEN it contains `\section{A}`
- THEN the command is rendered with distinct styling from plain text

### Requirement: Autosave

The editor MUST autosave edits after a short idle period using a hash-checked save, and MUST show saved, saving, dirty and conflict states.

#### Scenario: Idle autosave

- GIVEN the user edited a buffer
- WHEN the idle period elapses
- THEN the buffer is saved and the state returns to saved

#### Scenario: Save failure

- GIVEN a save fails for a non-conflict reason
- WHEN the failure occurs
- THEN the buffer stays dirty, an error state is shown and no text is lost

### Requirement: External change to a clean buffer

When a file changes on disk and its open buffer has no unsaved edits, the editor MUST reload the new content.

#### Scenario: Agent edits clean file

- GIVEN `main.tex` is open and clean
- WHEN an agent turn rewrites it on disk
- THEN the editor shows the new content without user action

### Requirement: External change to a dirty buffer

When a file changes on disk and its buffer has unsaved edits, the editor MUST NOT overwrite the user's text silently and MUST present a conflict the user resolves. Autosave MUST pause while a conflict is unresolved, and the user SHOULD be able to compare both versions.

#### Scenario: Conflict on dirty buffer

- GIVEN the buffer is dirty and disk content changed
- WHEN the change is detected or a save returns a conflict
- THEN the user's text is preserved
- AND the user can keep their version, take the disk version, or copy before deciding
- AND the user can compare both versions

#### Scenario: Autosave paused

- GIVEN a conflict is unresolved
- WHEN the idle period elapses
- THEN no save is attempted until the conflict is resolved

### Requirement: Undo restores open buffers

When a turn undo changes files on disk, open clean buffers MUST reflect the restored content.

#### Scenario: Reload after undo

- GIVEN a clean open buffer changed by a turn
- WHEN the user undoes that turn
- THEN the buffer shows the pre-turn content
