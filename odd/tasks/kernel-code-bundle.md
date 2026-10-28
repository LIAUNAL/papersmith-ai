# Ship a private repository's pinned code inside the kernel

Objective: a kernel-service job (the Kaggle adapter) can run code from a private repository without cloning it and without any token, by carrying the pinned clone paths as an archive inside the pushed notebook.
Branch: `feat/kernel-code-bundle` (from `origin/main` 07320802, v0.32.0). Delivery: release 0.33.0 (authorized by the operator); push of the feature branch is not needed. Tests: `~/Documents/papers_smith/papersmith-ai/.micromamba/envs/papersmith/bin/python -m pytest -q -n 6`; `npm test` (node_modules linked).

## Specs

- S0. The operator's choice, verbatim (2026-10-28): "sí, sigue con la opción 2 y saca la release 0.33.0", where option 2 was: "Que papersmith empaquete el código dentro del kernel. Al generar el job, papersmith arma un archivo con solo las carpetas a clonar en el commit fijado (hoy pesan 237 KB) y lo incrusta en el notebook privado. El kernel lo desempaca en lugar de clonar, así el repo sigue privado y no viaja ningún token. Es un cambio acotado en el adaptador de Kaggle, con tests y una release 0.33.0."
- S1. Bundle at the pinned commit. For a service that declares it carries code bundles (the Kaggle adapter; an optional adapter capability, the Adapter ABC stays at six abstract methods), the job carries the declared clone paths (plus the run/smoke notebook) taken from the pinned commit with `git archive` (never the working tree), compressed, with its sha256 recorded in `run-config.json`. How it is requested is the writer's choice within the existing CLI shape (e.g. `generate-job --code-bundle`, or automatic when the remote is not anonymously reachable and the service carries bundles); state it in help and docs. A job that does not use a bundle behaves exactly as today.
- S2. Reachability. With a bundle, `generate-job` does not require the remote to be anonymously reachable (the private repo is the reason), but still refuses unless the pinned commit exists locally and is the target's HEAD/declared pin, as today; it never reads or needs a repository credential.
- S3. In the kernel. The runner unpacks the bundle instead of `git clone`, verifies its sha256 before unpacking (refuse on mismatch), refuses entries that escape the working directory (absolute paths, `..`, links), and records the same `evidence.commit` the clone path records today (the pinned commit), so readiness/smoke verdicts read identically.
- S4. Staleness and size. A bundled job goes stale exactly when a cloned job would (a clone path changed after the pin). The pushed notebook must stay within the service's source size limit: refuse at generation with a typed error naming the bundle size and the limit when it would not fit (find the documented limit or choose a conservative bound and say so).
- S5. No secrets. Nothing from a credential file enters the bundle, the notebook, `run-config.json` or the ledger; the bundle contains only tracked files under the declared clone paths at the pin.
- S6. Docs: remote-execution SKILL.md ("Private repositories" section gains the bundle route), help text, CHANGELOG `## Unreleased` (doctrine files must not name the service; see the vocabulary tests).

## Tasks

- T1 (S1-S6) delegated writer (reason: long-session backstop of the parent) — done (S1-S6 covered; commit: see L3)
- T2 independent verifier (high risk: delivery/security, items 2 and 5) — pending
- T3 release 0.33.0 (parent) — pending

## Log

- L1 (2026-10-28, user): "sí, sigue con la opción 2 y saca la release 0.33.0"
- L2: Context: QMLEEG target `implementations/qmleeg-dru` is a PRIVATE GitHub repo; only the Colab adapter declares `REPO_CREDENTIAL_CARRIER`; Kaggle has no API to attach secrets to a kernel. Clone paths of the QMLEEG jobs (`src/QMLEEG_DRU`, `vendor`, `QMLEEG-DRU/Notebooks`, `QMLEEG-DRU/Data`) archive to 236,855 bytes gzipped at b8a170e.
- L3 (2026-10-28, T1 writer): `generate-job --code-bundle` (explicit flag) archives clone paths + notebooks at the pin with `git archive`, gzip mtime=0 (deterministic), writes `code-bundle.tar.gz` beside `run-config.json`, records `codeBundle {file, format, sha256, bytes}`. Capability: optional class attribute `Adapter.CODE_BUNDLE_MAX_BYTES = None` (ABC still six abstract methods); Kaggle declares 786,432 compressed bytes (no documented notebook-source limit found on 2026-10-28; conservative, ~1 MiB base64). With a bundle the published-tip default and `pin-published` are skipped, every local condition runs; `submit`'s gate and the Kaggle push verify the sha256; the push prepends a base64 cell writing the bundle; `runner_bootstrap.materialize_code()` unpacks via `unpack_code_bundle()` instead of cloning (sha verified first; absolute, `..`, link/special, out-of-clone-path entries refused). Codes: CODE_BUNDLE_NOT_CARRIED, CODE_BUNDLE_TOO_LARGE, CODE_BUNDLE_UNSAFE_ENTRY, CODE_BUNDLE_MISMATCH. Tests: `tests/test_remote_execution_code_bundle.py` (36, RED observed 32 failing first). `KernelCarryTests.test_the_docs_describe_the_automatic_carry` now reads the `## 0.32.0` section instead of the newest one. Full suite: only the known environmental failures; npm test 834/834.
