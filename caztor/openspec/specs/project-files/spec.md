# Project Files Specification

## Purpose

Listing and managing project files with strict path containment and hash-checked saves.

## Requirements

### Requirement: File tree

The system MUST show the project's files and folders as a tree and let the user open a file from it.

#### Scenario: Open file

- GIVEN a project with `main.tex`
- WHEN the user selects `main.tex` in the tree
- THEN its contents load in the editor

### Requirement: File operations

The system MUST support creating, renaming, deleting files and folders, and uploading files, within the project.

#### Scenario: Create and rename

- GIVEN an open project
- WHEN the user creates `refs.bib` and renames it to `bib.bib`
- THEN the tree shows only `bib.bib`

#### Scenario: Name collision

- GIVEN `a.tex` exists
- WHEN the user creates or renames another file to `a.tex`
- THEN the operation is rejected, with a readable message, and the existing file is unchanged

Uploads MUST be limited to 20 MB and MUST be rejected on a name collision. Deleting a folder MUST require confirmation. Files that are not UTF-8 text or exceed 2 MB MUST be listed but MUST NOT open in the editor.

#### Scenario: Upload limits

- GIVEN a 25 MB upload, or an upload named like an existing file
- WHEN the upload is sent
- THEN it is rejected and the existing file is unchanged

#### Scenario: Folder delete confirmation

- GIVEN a folder with files
- WHEN the user deletes it
- THEN nothing is deleted until the user confirms

#### Scenario: Unopenable file

- GIVEN a binary file or a text file over 2 MB
- WHEN the tree is listed and the user selects it
- THEN it is listed but does not open in the editor

### Requirement: Path containment

Every file operation MUST resolve inside the project root. Traversal sequences, absolute paths and symbolic links that escape the root MUST be rejected.

#### Scenario: Traversal rejected

- GIVEN a project root
- WHEN a request targets `../secret.txt`
- THEN it is rejected and no file outside the root is read or written

#### Scenario: Escaping symlink

- GIVEN a symlink inside the project pointing outside it
- WHEN a read or write goes through the symlink
- THEN it is rejected

### Requirement: Hash-checked saves

Each file read MUST return a content hash. A save MUST include the hash it was based on and MUST fail with a conflict result when the on-disk hash differs.

#### Scenario: Clean save

- GIVEN the editor holds hash H and disk still has H
- WHEN the user saves
- THEN the file is written and a new hash is returned

#### Scenario: Stale save

- GIVEN disk content changed since hash H was read
- WHEN a save based on H is sent
- THEN the system returns a conflict and leaves disk content untouched

### Requirement: Reserved paths

The tree MUST hide, and file operations MUST reject, `.caztor/`, `.claude/`, `.opencode/`, `.agents/`, `.git/` and `node_modules/`. `AGENTS.md` MUST be hidden only when Caztor created it.
(Previously: `.agents/` was not reserved)

#### Scenario: Internal state hidden

- GIVEN a project with `.caztor/` and `.git/` directories
- WHEN the tree is listed
- THEN neither is shown, and a file operation targeting either is rejected

#### Scenario: AGENTS.md visibility

- GIVEN an `AGENTS.md` authored by the user
- WHEN the tree is listed
- THEN it is shown
- AND an `AGENTS.md` created by Caztor is hidden

#### Scenario: Agents directory reserved

- GIVEN a project with `.agents/agents/caztor.md`
- WHEN the tree is listed and a read, write or delete targets that path
- THEN the directory is not shown and every operation is rejected

### Requirement: PaperSmith workspace privacy

The file API MUST hide `.papersmith/`, `.pi/`, `.mcp.json`, `.env`, `.env.local` and `skills/kaggle-accounts/store/` from the tree and refuse every operation on them.

#### Scenario: Kaggle accounts stay hidden

- GIVEN a workspace with `skills/kaggle-accounts/store/a.json`
- WHEN the tree is listed or that path is read
- THEN the folder is not shown and the read is rejected

### Requirement: Project navigator

The server MUST list the PaperSmith workspaces of the papers folder and the folders opened before, and MUST move to one of them on request. It MUST refuse the root and home folders, a path that is not a folder, and any switch while a turn runs. Open pages MUST reload after a switch.

#### Scenario: New project

- GIVEN no folder named `thesis` in the papers folder
- WHEN the user creates the project `thesis`
- THEN the folder holds a starter `main.tex` and it opens

#### Scenario: Name refused

- GIVEN a name that is in use, or one that could leave the papers folder
- WHEN the user creates a project with it
- THEN nothing is created and the user is told why

#### Scenario: Workspace found

- GIVEN `~/papers/spin/papersmith.yaml`
- WHEN the projects are listed
- THEN `spin` appears as a PaperSmith workspace

#### Scenario: Switch while a turn runs

- GIVEN a running turn
- WHEN another project is opened
- THEN the request is refused with a readable message and the project stays open

#### Scenario: Edits that cannot be saved

- GIVEN an open edit that cannot be saved
- WHEN the user picks another project
- THEN nothing moves and the rail says why

### Requirement: PaperSmith paper

In a PaperSmith workspace the system MUST treat `paper/main.tex` as the main file, open it, and compile it. When it is missing, the system MUST ask before creating `paper/` the way PaperSmith's scaffold does, leaving every existing entry unchanged. The system MUST NOT let the editor or a save change, remove or add a line starting with `%% paper-writing block` in a `.tex` file that has such lines.

#### Scenario: Missing paper

- GIVEN a workspace without `paper/main.tex`
- WHEN it opens and the user accepts
- THEN `paper/main.tex`, `paper/refs.bib`, `paper/Figures/` and `paper/.gitkeep` exist, empty, and the main file is open

#### Scenario: Marker kept

- GIVEN `paper/main.tex` with block markers
- WHEN a save would remove one
- THEN the save is refused with a readable message and the file is unchanged
