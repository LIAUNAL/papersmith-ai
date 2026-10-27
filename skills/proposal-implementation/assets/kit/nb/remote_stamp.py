"""The stamp a remote run leaves beside its results: `shard.json`.

`remote-execution`'s `smoke record` passes a smoke only when the fetched
`shard.json` carries every path the job declared under
`run.smoke.requiredEvidence` (for example `evidence.commit` and
`environment.device.kind`). Nothing else writes that file: the target's own
smoke callable does, by calling `write_shard` once its work is done.

It writes only under the runner. The remote runner exports `FORGE_RUN_MODE`
around the call it makes; a local session, a notebook or the test suite has
no such variable, and a stamp written there would be a claim about a run that
never happened remotely. So without it `write_shard` writes nothing and
returns `None`.

It lives beside the method's own package, like `report_digest.py`, and for
the same reason: it proves nothing, declares no `__provenance__`, and finds
the repository from its own path. Standard library only at import time;
`torch` is imported lazily, only to name the device when the caller did not.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import subprocess
from pathlib import Path

#: The variable the remote runner exports around the call it makes.
RUN_MODE_ENV = "FORGE_RUN_MODE"

#: The file `remote-execution` reads a shard's stamp from.
SHARD = "shard.json"


def repository_root() -> Path:
    """`<repo>`, read off this file's own path: `<repo>/src/<Package>/`."""
    return Path(__file__).resolve().parents[2]


def commit(repository: Path | None = None) -> str | None:
    """The checked-out commit, or `None` when there is no git or no commit."""
    repository = repository or repository_root()
    try:
        run = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=False)
    except OSError:
        return None
    return run.stdout.strip() if run.returncode == 0 and run.stdout.strip() else None


def sources_digest(repository: Path | None = None) -> str:
    """The seal `report_digest.py` computes, so a shard and a report agree."""
    repository = repository or repository_root()
    seal = Path(__file__).resolve().parent / "report_digest.py"
    spec = importlib.util.spec_from_file_location("_remote_stamp_seal", seal)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.source_digest(repository, Path(__file__).resolve().parent.name)


def device_record(device=None) -> dict:
    """`{kind, name}` for `device`, or for what this machine computes on.

    `device` may be a `torch.device`, a string such as `"cuda:0"`, or `None`.
    With `None`, a CUDA device is reported when `torch` is importable and sees
    one; otherwise the CPU.
    """
    torch = None
    try:
        import torch  # noqa: F811 - optional, imported only here
    except ImportError:
        torch = None
    if device is None:
        if torch is not None and torch.cuda.is_available():
            device = "cuda:0"
        else:
            device = "cpu"
    kind = getattr(device, "type", None) or str(device).split(":", 1)[0]
    if kind == "cuda" and torch is not None and torch.cuda.is_available():
        index = getattr(device, "index", None)
        if index is None and ":" in str(device):
            index = int(str(device).split(":", 1)[1])
        name = torch.cuda.get_device_name(index or 0)
    elif kind == "cpu":
        name = platform.processor() or platform.machine() or "cpu"
    else:
        name = str(device)
    return {"kind": kind, "name": name}


def _jsonable(value):
    for attribute in ("tolist", "item"):
        if hasattr(value, attribute):
            return getattr(value, attribute)()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def write_shard(summary: dict, directory=None, *, device=None,
                repository: Path | None = None) -> Path | None:
    """Write `shard.json` under the runner; do nothing anywhere else.

    `summary` lands under `runs`; the stamp adds `mode`, `evidence.commit`,
    `evidence.sourcesDigest` and `environment.device`. Written into the
    working directory -- the runner's own, where it collects outputs -- unless
    `directory` names another. Returns the path written, or `None` when
    `FORGE_RUN_MODE` is not set.
    """
    mode = os.environ.get(RUN_MODE_ENV)
    if not mode:
        return None
    repository = repository or repository_root()
    payload = {
        "mode": mode,
        "evidence": {"commit": commit(repository),
                     "sourcesDigest": sources_digest(repository)},
        "environment": {"device": device_record(device)},
        "runs": summary,
    }
    folder = Path(directory) if directory is not None else Path.cwd()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / SHARD
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_jsonable)
                    + "\n", encoding="utf-8")
    return path
