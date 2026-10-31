# Documentation index

Where each kind of document lives, and which ones describe the forge as it is
today. Start with the [README](../README.md) for installation and the order of
the work.

## Active guidance

These describe current behavior. When code and one of these disagree, the
document is the defect.

| Topic | Where |
|---|---|
| What each skill accepts and promises | `skills/<name>/SKILL.md` (source of truth) |
| Guided tour of every skill, with flow diagrams | [skills.md](skills.md) |
| Every `smith` command | [cli.md](cli.md); `smith <command> --help` is the source of truth |
| Project context for agents | [`openspec/project-context.md`](../openspec/project-context.md) |
| Current capability specs | [`openspec/specs/`](../openspec/specs/) (one `spec.md` per capability) |
| Harness support, per harness | [harness-support-matrix.md](harness-support-matrix.md) |
| Guard hooks | [guard-hooks.md](guard-hooks.md) |
| MCP server and tool catalogue | [mcp.md](mcp.md) |
| The dashboard's thematic help for `/plausibility` (`banco-lia`, `uv`, offline behaviour) | [mcp.md](mcp.md#the-dashboards-thematic-help) |
| The dashboard's tabs, including *Experimentos* (results discussion) and *Novedad & Hallazgos* | [cli.md](cli.md#smith-ui-dir) |
| Novelty assessment, the `G-NOVELTY` gate and `smith novelty`; the results-discussion tool | [cli.md](cli.md#smith-novelty-statusapproveiteratereset) |
| Choosing a journal by quartile range, the quartile source, the review-time estimate and the OpenAlex budget | [README](../README.md#choosing-and-adapting-to-a-journal); [skills.md](skills.md#19-journal-finder--a-journal-chosen-on-evidence-a-template-adapted-on-approval) |
| Adapting the manuscript to a chosen journal: the `venue` verbs, the `venue-adapter` agent and the approval gate | [skills.md](skills.md#9-paper-writing--from-the-section-contracts-to-the-pdf-with-nothing-assumed); `skills/paper-writing/SKILL.md` ("Venue adaptation") |
| The PDF Preview tab's journal block and its `/api/journals*` routes | [cli.md](cli.md#smith-ui-dir) |
| Releasing | [releasing.md](releasing.md) |
| Dashboard under WSL | [wsl-dashboard.md](wsl-dashboard.md) |
| Flow diagrams | [diagrams/README.md](diagrams/README.md) |
| Repository maintenance (issues and PRs) | [`maintainer/skills/backlog-steward/SKILL.md`](../maintainer/skills/backlog-steward/SKILL.md) |

## History

These record how the forge got here. They are kept for audit and are never
edited to match today's behavior; a dated measurement in them is true of its
date.

| Record | Where |
|---|---|
| Release notes, newest first | [`CHANGELOG.md`](../CHANGELOG.md) |
| Completed OpenSpec changes, dated | [`openspec/changes/archive/`](../openspec/changes/archive/) |
| Feature task logs | [`odd/tasks/`](../odd/tasks/) |
| Maintenance essays | [`MAINTENANCE-the-forge-carries-no-paper-inside.md`](../MAINTENANCE-the-forge-carries-no-paper-inside.md), [`MAINTENANCE-seven-ways-to-fail-green.md`](../MAINTENANCE-seven-ways-to-fail-green.md) |

## Policy

- A new reference page goes under `docs/` and gets a row here; the README links
  to it instead of growing.
- When an OpenSpec change is done it moves to `openspec/changes/archive/<date>-<name>/`;
  its lasting requirements go to `openspec/specs/`.
- History is archived, never deleted: moving a page keeps its links working, and
  a dated record is not rewritten to match today.
