# PDF Preview Specification

## Purpose

Showing the compiled PDF and the compile log with navigation back to source.

## Requirements

### Requirement: PDF display

The preview pane MUST display the latest compiled PDF.

#### Scenario: Show after compile

- GIVEN a compile succeeded
- WHEN it finishes
- THEN the pane displays the new PDF

### Requirement: Reload keeps position

Reloading after a compile MUST preserve the scroll position and zoom.

#### Scenario: Recompile

- GIVEN the user is on page 3 at 150% zoom
- WHEN a compile finishes
- THEN the new PDF opens on the same position and zoom

### Requirement: Empty and failed states

The pane MUST show an empty state when no PDF exists and MUST keep the last good PDF when a compile fails.

#### Scenario: No PDF yet

- GIVEN a project never compiled
- WHEN the pane renders
- THEN an empty state invites the user to compile

#### Scenario: Failed compile keeps last PDF

- GIVEN a previous PDF exists and the new compile fails with no PDF
- WHEN the run ends
- THEN the previous PDF stays visible and is marked out of date

### Requirement: Log panel with click-to-line

A log panel MUST list errors and warnings. Selecting an entry with a file and line MUST open that file in the editor at that line.

#### Scenario: Jump to error

- GIVEN an error `chapter.tex:7`
- WHEN the user clicks it
- THEN `chapter.tex` opens with the cursor on line 7

#### Scenario: Entry without location

- GIVEN a diagnostic with no file or line
- WHEN it is listed
- THEN it is shown without a jump action
