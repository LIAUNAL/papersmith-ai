# Workspace Layout Specification

## Purpose

The application shell: four resizable vertical panes whose sizes persist.

## Requirements

### Requirement: Four-pane arrangement

The system MUST present four vertical panes, left to right: file tree, LaTeX editor, PDF preview, chatbot.

#### Scenario: Initial render

- GIVEN the app is opened with no saved layout
- WHEN the workspace renders
- THEN four panes appear in the order tree, editor, preview, chat
- AND each pane has a usable default width

### Requirement: Resizable panes

The system MUST let the user resize adjacent panes by dragging the divider between them, and MUST enforce a minimum width per pane.

#### Scenario: Drag divider

- GIVEN the workspace is rendered
- WHEN the user drags the divider between editor and preview
- THEN the two panes resize and the others keep their width

#### Scenario: Minimum width

- GIVEN a pane is at its minimum width
- WHEN the user drags its divider further inward
- THEN the pane does not shrink below the minimum

### Requirement: Persisted sizes

The system MUST persist pane sizes and restore them on the next load.

#### Scenario: Reload restores sizes

- GIVEN the user resized the panes
- WHEN the page is reloaded
- THEN the panes render with the saved sizes

#### Scenario: Corrupt saved layout

- GIVEN the stored layout is invalid or unreadable
- WHEN the workspace renders
- THEN default sizes are used and no error blocks the app

### Requirement: Independent panes

The editor MUST remain fully editable regardless of chat state, because chat is a separate panel.

#### Scenario: Edit during a running turn

- GIVEN a chat turn is running
- WHEN the user types in the editor
- THEN the input is accepted without delay or lock
