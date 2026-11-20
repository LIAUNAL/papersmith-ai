# Proposal: Caztor Writing Guides

## Intent

Caztor's agents carry only six academic-style bullets. The papersmith-ai section guides (Apache-2.0, commit `1f09516`) hold mature, generic advice per section. Distill them into Caztor as advisory guidance, behind a seam that a later papersmith-backed source can fill, since Caztor is meant to become a papersmith extension.

## Scope

### In Scope
- Distilled guides from `sections/01..10-*.md`: function, sequence, extent, exclusions, cross-section coherence, citation and acronym conventions, disqualifiers. Pipeline-specific content removed.
- Compact advisory core in the shared section of every definition (byte-identical, under Codex's 32 KiB).
- Condensed per-section guides plus `INDEX.md` provisioned to `.caztor/guides/`, hash-tracked, read on demand.
- Narrow read exception for `.caztor/guides/` in the definitions.
- `GuideSourcePort` with a built-in distilled source as default and fallback.
- Apache-2.0 compliance: license copy, per-file modification notice (source path, commit), `NOTICE.md` entry.

### Out of Scope
- The papersmith-backed source (later change).
- papersmith pipeline agents (`redactor`, `style-sampler`, `contract-auditor`, ...).
- Automatic section detection or guide injection.
- Choosing a license for Caztor.

## Capabilities

### New Capabilities
- `writing-guides`: guide content and genre-neutral advisory stance, source port with built-in default, provisioning to `.caztor/guides/` with `INDEX.md`, hash tracking, removal, Apache-2.0 attribution.

### Modified Capabilities
- `agent-definitions`: shared section gains the guide core and the `.caztor/guides/` read exception; size bound; cleanup covers guides.
- `turn-snapshots`: provisioned guides explicitly excluded.

`project-files` is unchanged: `.caztor/` is already hidden and rejected.

## Approach

Exploration option B. Core: a `GuideSourcePort` returning guide documents. Adapters: a built-in source over distilled files in the repo; the provisioner writes them with the existing hash tracking and user-modification rules, provider-agnostic so the fourth provider in `caztor-providers-auth` inherits them. Each condensed guide notes that the document's structure and venue template take precedence and covers theses, reports and reviews. "Assert nothing the user did not provide" maps to the existing citation-integrity rules.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `agents/{claude,opencode,codex}.md`, `agents/agents.test.ts` | Modified | Core, read exception, size test |
| `guides/` (new, repo) | New | Distilled guides, `INDEX.md` |
| `packages/core/src/` | New | `GuideSourcePort` |
| `packages/adapters-local/src/provisioner.ts` | Modified | Guide provisioning, removal |
| Snapshot exclusion | Modified | Skip `.caztor/guides/` |
| `LICENSES/Apache-2.0.txt`, `NOTICE.md` | New | Attribution |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Caztor has no LICENSE; mixing Apache-2.0 content is unclear | High | Recommend the user add an Apache-2.0-compatible license; not chosen here |
| Guides bias toward applied-research articles | Med | Advisory wording, genre notes |
| Definition exceeds 32 KiB | Low | Test enforces the bound |
| Read exception widens agent access | Low | Path-exact rule, read only |
| Definition change resets conversations | Med | Expected; one reset on upgrade |

## Rollback Plan

Revert the slice branches. Removal deletes provisioned guides by hash; restored definitions drop the exception. No data migration.

## Dependencies

- Local papersmith checkout at `1f09516` for distillation.
- No dependence on tectonic or codex.

## Success Criteria

- [ ] All definitions byte-identical in the shared section and under 32 KiB.
- [ ] Ten guides and `INDEX.md` provisioned idempotently, hidden, excluded from snapshots.
- [ ] No pipeline-specific term remains (test-checked).
- [ ] Each guide carries the modification notice; `NOTICE.md` and the license copy exist.
- [ ] A fake source can replace the built-in one through the port in tests.
