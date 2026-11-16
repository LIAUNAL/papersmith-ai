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

A smoke callable decorated with `stamped` calls it for you with whatever the
smoke returns, which is the scaffold's smoke template: a smoke that only
times or only runs and never stamps is refused at `smoke record`, after a
whole remote rehearsal.

It lives beside the method's own package, like `report_digest.py`, and for
the same reason: it proves nothing, declares no `__provenance__`, and finds
the repository from its own path. Standard library only at import time;
`torch` is imported lazily, only to name the device when the caller did not.
"""

from __future__ import annotations

import functools
import importlib.metadata
import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

#: The variable the remote runner exports around the call it makes.
RUN_MODE_ENV = "FORGE_RUN_MODE"

#: The file `remote-execution` reads a shard's stamp from.
SHARD = "shard.json"

#: The pinned commit the remote runner exports beside the clone it hands over.
CLONE_COMMIT_ENV = "FORGE_CLONE_COMMIT"


def repository_root() -> Path:
    """`<repo>`, read off this file's own path: `<repo>/src/<Package>/`."""
    return Path(__file__).resolve().parents[2]


def commit(repository: Path | None = None) -> str | None:
    """The checked-out commit: `git rev-parse HEAD`, or, where git cannot
    answer, the commit the runner exported (`FORGE_CLONE_COMMIT`). A worker
    that received the code as a bundle holds only `.git/HEAD`, so git fails
    there while the runner still knows the pin. `None` when neither answers."""
    repository = repository or repository_root()
    try:
        run = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=False)
    except OSError:
        run = None
    if run is not None and run.returncode == 0 and run.stdout.strip():
        return run.stdout.strip()
    return os.environ.get(CLONE_COMMIT_ENV) or None


def sources_digest(repository: Path | None = None) -> str:
    """The seal `report_digest.py` computes, so a shard and a report agree."""
    repository = repository or repository_root()
    seal = Path(__file__).resolve().parent / "report_digest.py"
    spec = importlib.util.spec_from_file_location("_remote_stamp_seal", seal)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.source_digest(repository, Path(__file__).resolve().parent.name)


# --- The run's runtime: host, hardware, libraries, threads (#186) -----------
# The same block is written by every run record (the runner's `bootstrap.json`,
# the kit's `shard.json` and bounded-benchmark summary, the timing probe's
# `timing.json`), each file keeping its own copy because each runs alone in a
# different interpreter. Re-running one configuration on another machine moves
# per-seed results, so a record names where it ran; an analysis that pools
# records from several hosts can then say so. Standard library only; `torch`
# is read only when the caller holds it or it is already imported.

#: The label a job exports for the host it runs on (`generate-job --env
#: MVIA_TIMING_HOST=<host>:<owner>`); without it, the machine's node name.
HOST_LABEL_ENV = "MVIA_TIMING_HOST"
#: The thread-count variables that change a run's speed and, through the order
#: of floating-point reductions, its results.
THREAD_ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
#: The libraries whose installed version the record names, when installed.
LIBRARIES = ("numpy", "torch", "scikit-learn")


def host_label() -> str:
    """`MVIA_TIMING_HOST` when the job set it, else `host-<12 hex>`: a digest of the machine's node name,
    stable per machine but never the name itself, which on a personal machine often carries its owner's
    name. `unknown-host` when the machine reports no node name, so a record never holds a null label."""
    label = os.environ.get(HOST_LABEL_ENV, "").strip()
    if label:
        return label
    node = platform.node()
    if not node:
        return "unknown-host"
    import hashlib
    return "host-" + hashlib.sha256(node.encode("utf-8")).hexdigest()[:12]


def cpu_model() -> str | None:
    """The CPU's model name, read where the operating system states it."""
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True,
                                 text=True, timeout=5, check=False)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        elif sys.platform.startswith("linux"):
            text = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                key, _, value = line.partition(":")
                if key.strip().lower() == "model name" and value.strip():
                    return value.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return platform.processor() or None


def gpu_model(torch=None) -> str | None:
    """The CUDA device's name when `torch` sees one, else `None`."""
    torch = torch if torch is not None else sys.modules.get("torch")
    try:
        cuda = getattr(torch, "cuda", None)
        if cuda is not None and cuda.is_available():
            return str(cuda.get_device_name(0))
    except Exception:  # noqa: BLE001  (a broken driver names no GPU; the run goes on)
        return None
    return None


def library_versions(torch=None) -> dict:
    """Python and each of `LIBRARIES` that is installed, by installed version."""
    versions = {"python": platform.python_version()}
    for name in LIBRARIES:
        try:
            versions[name] = importlib.metadata.version(name)
        except Exception:  # noqa: BLE001  (not installed, or installed without metadata)
            continue
    if torch is not None and getattr(torch, "__version__", None):
        versions["torch"] = str(torch.__version__)
    return versions


def thread_settings(torch=None) -> dict:
    """`torch.get_num_threads()` (or `None`) and each of `THREAD_ENV` as set (or `None`)."""
    torch = torch if torch is not None else sys.modules.get("torch")
    threads = None
    getter = getattr(torch, "get_num_threads", None)
    if callable(getter):
        try:
            threads = int(getter())
        except Exception:  # noqa: BLE001
            threads = None
    settings = {"torch": threads}
    settings.update({name: os.environ.get(name) for name in THREAD_ENV})
    return settings


def runtime_record(torch=None) -> dict:
    """`{host, hostSource, hardware, libraries, threads}` for this process."""
    torch = torch if torch is not None else sys.modules.get("torch")
    labelled = bool(os.environ.get(HOST_LABEL_ENV, "").strip())
    return {"host": host_label(), "hostSource": HOST_LABEL_ENV if labelled else "platform.node digest",
            "hardware": {"machine": platform.machine() or None, "cpu": cpu_model(),
                         "cpuCount": os.cpu_count(), "gpu": gpu_model(torch)},
            "libraries": library_versions(torch), "threads": thread_settings(torch)}


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
    `evidence.sourcesDigest`, `environment.device` and `runtime` (host,
    hardware, library versions, thread settings). Written into the
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
        # A top-level key of its own, so a distribution that declares
        # `environment` identical across shards is not refused by it.
        "runtime": runtime_record(),
        "runs": summary,
    }
    folder = Path(directory) if directory is not None else Path.cwd()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / SHARD
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_jsonable)
                    + "\n", encoding="utf-8")
    return path


def stamped(function):
    """The smoke template: wrap the target's smoke callable so it leaves
    `shard.json` by itself. Whatever the smoke returns becomes the stamp's
    `runs` (a non-mapping is stored under `result`); outside the runner
    nothing is written, exactly as `write_shard` behaves.

        @stamped
        def smoke(**kwargs):
            ...
            return {"units": 1, "seconds": elapsed}
    """
    @functools.wraps(function)
    def run(*args, **kwargs):
        summary = function(*args, **kwargs)
        write_shard(summary if isinstance(summary, dict) else {"result": summary})
        return summary
    return run
