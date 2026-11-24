# One reproducible dependency specification (issue #58)

Objective: provision every environment (workspace, CI, dashboard venv) from one locked dependency specification. Branch `fix/env-provisioning` (root `env-provisioning`, tier 1). Delivery `ask-on-risk`. Runner: `.micromamba/envs/papersmith/bin/python -m pytest` with absolute `PYTHONPATH=$PWD/src:$PWD`; node via `PATH=/usr/bin:$PATH npm test`.

## Specs

- S1. Issue #58 acceptance, verbatim:
  - "Choose one dependency source of truth and generate platform-aware runtime locks."
  - "Provision local and CI environments from those locks; remove hand-maintained duplicate lists."
  - "Demonstrate repeatable installation and document lock refreshes."
- S2. Source of truth (L2): `environment.yml` on conda-forge, locked with conda-lock for linux-64, osx-64, osx-arm64 and win-64, in a cpu and a cuda variant. ROCm torch stays on AMD's pinned index. `conda-lock` is needed only by whoever refreshes the locks. Ingestion's docling and mlx-vlm stay a pinned, unlocked pip layer declared once in `env/ingestion.txt` (L4: they cannot be locked with conda-lock on every platform).
- S3. `scripts/setup_env.py install`, CI and the dashboard's venv install from the lock, never a live solve of a hand-written list; `requirements.txt` is generated from `environment.yml` (or dropped where nothing reads it); the duplicate lists (`CONDA_BASE_PACKAGES`, `PIP_PACKAGES`, `UI_ENV_PACKAGES`, `skills/paper-ingestion/requirements.txt`) are removed or derived.
- S4. The tests that pin these lists read the single source; a lock out of date with `environment.yml` fails a test. Lock refresh documented in `docs/releasing.md`.

## Tasks

- T1 (S2) `environment.yml` and the lock script with its locks -- inline -- done (L4; uncommitted until T2-T4)
- T2 (S3) `setup_env.py` installs from the lock; duplicate lists derived or removed -- delegated (context backstop) -- in progress
- T3 (S3) dashboard venv and CI from the lock -- delegated with T2 -- in progress
- T4 (S4) tests read the single source; lock freshness check; docs -- delegated with T2 -- in progress

## Log

- L1 (2026-11-24, user): "puedes revisar pr e issues del proyecto y revisar que modemos mergear y atacar"; after the triage, "dale" to merging the paper-types chain and starting #58.
- L2 (2026-11-24, user): chose "environment.yml + conda-lock (Recommended)" for #58's single source.
- L3 (exploration, read-only): no single source today. The real installer is `scripts/setup_env.py:65-141` (`PIP_PACKAGES`, `CONDA_BASE_PACKAGES`), a live unpinned conda-forge solve except python=3.12 and kagglesdk==0.1.37; torch is `pytorch-gpu|pytorch-cpu` + torchvision (:417-421), ROCm wheels from `gpu_probe.py:362-370`. `requirements.txt` installs nothing (its :45 comment is wrong) but is a kit entry (`manifest.py:203`) and is read by `test_env_pins.py`, `test_remote_execution.py` (DoctrinePinTests), `test_ui_runtime_bootstrap.py`, `test_mcp_dependencies.py`, `test_pypi_publishing.py`. `ui.py:61-99` is a third install path (pip venv in `~/.cache/papersmith/ui-env-pyXY`). `skills/paper-ingestion/requirements.txt` is read by nothing. `uv.lock` holds only the package itself. CI (`test.yml:36-66`) runs `setup_env.py install --no-ingestion` on ubuntu, matrix 3.11/3.12 for the host only (the env is always 3.12), no cache. No macOS/Windows runners. `pyproject.toml` `dependencies = []` must stay empty for pipx.
- L4 (T1, parent): sources `env/environment.yml` (category main: every conda dependency with requirements.txt's lower bounds, kagglesdk==0.1.37, python=3.12, llama.cpp), `env/torch-cpu.yml` (pytorch-cpu, torchvision), `env/torch-cuda.yml` (pytorch-gpu, torchvision). Ingestion stays a pip layer in `env/ingestion.txt` (docling==2.141.0; mlx-vlm==0.7.10 on Apple Silicon): docling has no win-64 build on conda-forge, conda-forge's docling-parse stops below what docling 2.142 needs on some platforms, and conda-lock's pip solver does not map conda's torch onto docling's `torch` requirement (it pulled PyPI torch with nvidia-cublas). `scripts/lock-env.py lock|check` (maintainer; conda-lock 4.1.0 in `~/.cache/papersmith/lock-tools`) writes `env/cpu.conda-lock.yml` (linux-64, osx-64, osx-arm64, win-64), `env/cuda.conda-lock.yml` (linux-64, win-64, solved `--with-cuda 12.8`), `env/rocm.conda-lock.yml` (linux-64, no torch; AMD wheels on top) and `env/locks.json` (sha256 of each lock's sources; `check` exits 1 when a source changed). micromamba reads a file as a lockfile only when its name ends in `-lock.yml` (a `probe-cpu3.yml` name created an empty env). Unlocked platforms today: linux-aarch64, win-arm64.
- L5 (S1 'Demonstrate repeatable installation', parent): two installs from `env/cpu.conda-lock.yml --category main` into fresh prefixes on linux-64 (`micromamba create -y -p <prefix> -f env/cpu.conda-lock.yml --category main`, 2026-11-24): both give 221 packages whose `micromamba list --explicit --md5` lines are identical (only the header naming the prefix differs); torch 2.14.1, numpy 2.5.5, llama-server and pip present; imports of torch, fastapi, kagglesdk, numpy, nbclient, ipykernel, pypdfium2, PIL succeed. macOS and Windows locks are solved but not installed (no runner or machine here).
