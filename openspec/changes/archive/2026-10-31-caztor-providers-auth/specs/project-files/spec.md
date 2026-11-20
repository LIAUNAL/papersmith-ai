# Delta for Project Files

## MODIFIED Requirements

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
