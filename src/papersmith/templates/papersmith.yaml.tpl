version: "1"
name: {{name_yaml}}
title: {{title_yaml}}
topic: {{topic_yaml}}
venue_target: "unspecified"

skills:
  - paper-ingestion
  - proposal-deliberation
  - proposal-implementation
  - remote-execution
  - kaggle-accounts
  - skill-audit

environment:
  python: ">=3.11"
  node: ">=20.0.0"
  cuda: "12.2"

compute_targets:
  default: {{default_target_yaml}}
  targets:
    local-workstation:
      provider: "local"
      device: "cuda:0"
      max_parallel_jobs: 2
      scratch_dir: ".scratch/runs"

    # The remote-execution adapter does not read `accelerator`: it always
    # requests one GPU through machine_shape "NvidiaTeslaT4" (a bare GPU
    # request can land on a P100, which fails). `max_timeout_hours` is a
    # local cap you declare for planning, not Kaggle's own limit: the session
    # and weekly GPU limits are the ones the account's settings or the MCP's
    # get_accelerator_quota show.
    kaggle-gpu-pool:
      provider: "kaggle"
      account_pool: "default"
      accelerator: "GPU_T4_X2"
      internet_access: true
      max_timeout_hours: 9
      auto_pull_artifacts: true

    slurm-cluster:
      provider: "remote-ssh"
      host: "hpc.university.edu"
      partition: "gpu-a100"
      nodes: 1
      gpus_per_node: 2
      walltime: "12:00:00"

execution_profiles:
  smoke_and_invariants:
    target: "local-workstation"
    entrypoint: "{target_python} -m pytest {target}/tests/test_invariants.py"
    env_vars:
      PYTHONPATH: "{target}/src"
      CUDA_VISIBLE_DEVICES: "0"
    timeout_seconds: 300

  sweep_training:
    target: "kaggle-gpu-pool"
    bootstrap: "skills/remote-execution/assets/runner_bootstrap.py"
    entrypoint: "python {target}/src/train.py"
    sharding:
      enabled: true
      strategy: "grid"
      parameter: "--seed"
      values: [42, 1337, 2026, 9999]
      distribute_across_accounts: true
    resources:
      min_ram_gb: 16
      gpu_vram_gb: 16
    artifacts:
      collect:
        - "checkpoints/*.pt"
        - "metrics/*.json"
        - "figures/*.png"
      destination: "kaggle-inbox/{job_id}/"

  benchmark_evaluation:
    target: "kaggle-gpu-pool"
    entrypoint: "papermill {target}/nb/benchmark.ipynb kaggle-inbox/{job_id}/benchmark_out.ipynb"
    # Not read by the adapter either (see kaggle-gpu-pool above).
    resources:
      accelerator: "GPU_P100"
    artifacts:
      collect:
        - "kaggle-inbox/{job_id}/benchmark_out.ipynb"
        - "kaggle-inbox/{job_id}/verdict.json"

# The paper-ingestion skill owns this block. The orchestrator intentionally
# leaves its keys opaque while keeping the block in the same workspace file.
paper_ingestion:
  # auto: route each page -- digital prose through pypdfium2 in milliseconds,
  # only equation, table and scanned pages through Docling. All
  # license-unrestricted. Also: pdfium (fast path only), docling (every page),
  # marker (opt-in; weights free only below USD 5M in funding or revenue).
  engine: auto
  mode: fast
  strip_references: true
  source_base: guidance
  source_roots: []

# The paper-writing skill owns this block: connector roles (never code).
# Without the `resolution` role, `paper_cli.py resolve` refuses with
# RESOLVER_ROLE_EMPTY and literature scouting cannot start. Mirrors the
# framework default shipped in this repository's own papersmith.yaml.
# `asta` (Ai2's Asta, the Semantic Scholar corpus) is asked first once its
# key is set in smith ui (Doctor -> API keys) or with `smith keys set asta`,
# and skipped without it, so without the key OpenAlex answers as before.
paper_writing:
  contact: ""
  roles:
    discovery:
      - asta
    resolution:
      - asta
      - openalex
      - crossref
      - arxiv
    full-text:
      - openalex
      - arxiv
