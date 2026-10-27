# Remote rehearsal lessons

Objective: carry what the QMLEEG E5 Colab rehearsal exposed into papersmith so future projects and launches do not repeat it.
Branch: `fix/remote-rehearsal-lessons` (from `origin/main` 3dd4649e). Delivery: single PR-sized branch, merged by the operator. Tests: `pytest` from the main checkout's micromamba env, `npm test`.

## Specs

- S1. An incomplete `fetch --smoke` (run still going) must not leave an empty `.partial/` that blocks every later fetch. A partial holding bytes keeps today's refusal.
- S2. A notebook downloaded from Colab arrives as a Python dict repr (google-colab-cli 0.6.0 `str(content)` on the contents API's JSON notebook). The Colab adapter must hand back valid notebook JSON.
- S3. A smoke block declared without `--smoke-required-evidence` passes on any JSON, and nothing says the smoke callable must write `shard.json` into its working directory. `generate-job` reports a warning for the first; `smoke record --from-artifact <dir>` reads `<dir>/shard.json`, and a missing stamp names what the callable must write. Docs say it.
- S4. The experiments reviewer checks that tensors created inside the forward/simulation are allocated on the input's device (a CPU-only run never exposes it); the GPU dimension covers Colab as well as Kaggle.
- S5. The walk agents carry the operational lessons: commit job folders and diagrams before `step` (DIRTY_WORKTREE); `generate-job --regenerate` after re-pinning; wait with `poll`, not `fetch`; a `submit` that times out ("refusing to guess") is followed by a read-only `reconcile` before any retry; the consent token is per pin.

## Tasks

- T1 (S1) inline — done, 64834281 (RED: empty partial kept; GREEN after rmdir)
- T2 (S2) inline — done, 771808ae (RED: repr download / missing helper)
- T3 (S3) inline — done, 021d7d2a (RED: Errno 21 on a folder, no smoke_warnings)
- T4 (S4, S5) inline, docs + harness sync — done (this commit); sync-repo-harness --check clean

## Log

- L1 (2026-10-26, user): "sí, impleméntalo así y relanza el smoke, y ajsuta papersmith proyecto para incluir todos estos ajustes en futuros proyectos y lanzadas."
- L2: Mapping done by a read-only explorer: fetch partial at `remote_cli.py:1718-1766` and `adapters/colab.py:1596`; repr notebooks from google-colab-cli `contents.py:87`; smoke validation `jobfolder.py:1649-1712`, output `remote_cli.py:3235-3256`, smoke record `remote_cli.py:2147-2222`; agents SSOT `.claude/agents/`, projections via `scripts/sync-repo-harness.py`.
- L3: Verified: remote-execution suites 816 passed; full pytest 31 failures = the 30 baseline + release-hygiene version check (cleared by the release); npm 834/0.
- L4: Field evidence: E5 smoke colab:amalvarezme/psmith-e5-run-end-to-end-37879052 passed (`smoke record` on its shard.json) and readiness is true, using the qmleeg-dru side of S3.
