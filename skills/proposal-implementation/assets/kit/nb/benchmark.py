"""Bounded benchmark: train both implementations in one common setting.

This runs in the target repository, with the target's interpreter and its torch —
never the forge's. It is small, but sized rather than merely shrunk: enough to resolve
the difference worth detecting, and no larger.

Read every number together with the bounds printed beside it. Being sized for one
question does not make it an answer to every question — a setting that resolves a
three-point gap says nothing about a method whose advantage appears only at a scale
this never reached.

What speed buys is repetition. One run cannot separate a difference from its own
noise, so the default is several seeds and the report carries dispersion, never a
bare mean.

    python benchmark.py --config config.json
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
import sys
from pathlib import Path
from typing import Callable

# `verdict.py` sits beside this file inside `src/<Package>_Benchmark/`, and this
# file is reached two ways: as the script the docstring above names
# (`python benchmark.py`, run from inside that directory, where there is no parent
# package at all) and as the dotted module the benchmark declaration's own `entry`
# example names (`<Package>_Benchmark.benchmark`, where there is). A flat import
# resolves only the first, a relative one only the second, and this kit ships both
# claims about the same file.
#
# Measured: a repository built exactly from this kit, with `entry` answered by the
# example the kit itself publishes, answered `ModuleNotFoundError: No module named
# 'verdict'` on that declared entry module -- reached before `import torch`, so the
# forge read it as a broken environment and offered a rung that installs packages
# and could never have fixed an import.
#
# `__package__` is that question asked directly, so nothing is guessed and no
# ImportError is swallowed on the way past: a `verdict.py` that is present but
# broken still raises, exactly as before.
if __package__:
    from .verdict import DESCRIPTIVE, HIGHER, LOWER, judge, render, tally
else:
    from verdict import DESCRIPTIVE, HIGHER, LOWER, judge, render, tally

def hosted_runtime() -> str | None:
    """Is this a notebook service, where there is no interpreter of our own to use?

    Asked positively, and that matters. The tempting shortcut is to infer it from a
    missing virtualenv — but a repository where nobody has created one yet also has
    no virtualenv, and there the guard is exactly right to refuse. Inferring from the
    absence would drop the protection on the user's own machine to buy portability
    somewhere else.
    """
    if "google.colab" in sys.modules or Path("/content").is_dir():
        return "colab"
    if os.environ.get("KAGGLE_KERNEL_RUN_TYPE") or Path("/kaggle").is_dir():
        return "kaggle"
    if os.environ.get("BINDER_SERVICE_HOST") or os.environ.get("CODESPACES"):
        return "hosted"
    return None


def refuse_foreign_interpreter() -> None:
    """Stop before anything heavy is imported, when this is the wrong interpreter.

    **Above the `import torch` below, and called at import time, and that
    placement is the whole of it.** The check used to live inside
    `environment()`, several hundred lines down and reached only when a caller
    asked for the stamp — so importing this module under a foreign interpreter
    died on `import torch` first, and what a reader met was
    `ModuleNotFoundError: No module named 'torch'`. A broken-environment
    message, for a correctly-installed environment that simply was not this
    repository's own. The doctrine says the guard refuses BEFORE anything is
    measured; a guard that cannot be reached refuses nothing.

    Standard library only, for the same reason: a guard that needed an
    installed package to decide whether the packages are the right ones could
    not run in the one case it exists for.

    The file sits at <repo>/src/<Package>_Benchmark/benchmark.py, so the
    repository is two levels up.
    """
    repository = Path(__file__).resolve().parents[2]
    prefix = Path(sys.prefix).resolve()
    if prefix.is_relative_to(repository) or hosted_runtime():
        return
    raise SystemExit(
        f"refusing to run under {prefix}\n"
        f"  this benchmark must use {repository}'s own virtualenv, because wall "
        f"time and peak memory are the measurement: another interpreter would "
        f"measure a different environment correctly and report it as this one.\n"
        f"  invoke this file with {repository}/.venv/bin/python directly, or\n"
        f"  run the notebook with\n"
        f'    PATH="{repository}/.venv/bin:$PATH" {repository}/.venv/bin/python -m jupyter \\\n'
        f"      nbconvert --to notebook --execute --inplace <notebook>\n"
        f"  The PATH prefix is not optional and is the reason you are seeing "
        f"this: a kernelspec launches a bare `python` resolved off PATH, so "
        f"naming the interpreter without also putting it first still hands the "
        f"cells to whichever one was already there.")


# Not called unconditionally, and the correction is worth stating. Refusing at
# import time reaches something this guard has no business refusing: `verify`
# and `probe` IMPORT this module to answer whether the declared entry point is
# importable at all, and an import is not a measurement -- a kit-built target
# was routed to `env-first` by its own guard, which is a check reporting a
# defect it created.
#
# So the two cases are separated by what actually happens. If the heavy import
# succeeds, nothing is refused: importing is free and whoever measures calls
# `environment()`, which refuses there. If it FAILS, the interpreter decides
# which failure it is -- a foreign one is the cause and says so, a correct one
# is a genuinely absent package and the original error stands untouched. That
# is the whole defect this closes: under a foreign interpreter a reader used to
# meet `No module named 'torch'`, a broken-environment message for an
# environment that was correctly installed and simply was not this one.
try:
    import torch
    import torch.nn as nn
except ImportError:
    refuse_foreign_interpreter()
    raise
from torch.utils.data import DataLoader, Subset

# No dataset catalogue lives here. The comparison only happens when a baseline is
# present, and a baseline arrives with the data it was actually measured on — its
# loaders, its splits, its task names. Hardcoding a list of well-known sets would let
# this file dictate the experiment: the wiring would be forced to pick whichever of
# them the baseline happens to touch, and the reported "common environment" would be
# the intersection of somebody's catalogue with the real work, rather than the real
# work. `build_data` comes from the wiring, like the builders.


# The dimensions the trained setting measures, and which direction wins each. The
# synthetic sweep reports its own dimensions through the same shape and the same
# rules, so both settings produce one comparable table.
DIMENSIONS = {
    "accuracy": HIGHER,
    "seconds": LOWER,
    "peakMiB": LOWER,
    "parameters": DESCRIPTIVE,
}


@dataclass
class Reduction:
    """The bounds this run was carried out under, recorded beside its numbers.

    The scale is chosen to resolve the difference worth detecting, so what this
    answers, it answers. These are the limits of that answer — how much material, how
    long, how many repetitions — and a number read without them will be taken for more
    than it is.
    """

    setting: str = "trained"
    dataset: str = ""      # named by the wiring, not chosen here
    backbone: str = ""     # named by the wiring, not chosen here
    fraction: float = 0.1
    epochs: int = 1
    batch_size: int = 64
    seeds: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    revision: str = ""
    device: str = "cpu"


def stratified_indices(targets: list[int], fraction: float, classes: int,
                       generator: torch.Generator) -> list[int]:
    """A slice that keeps every class, drawn per class rather than at random.

    The proposal requires every class to be present in the source collection the
    local correspondence uses. A random slice can drop one, which leaves that
    correspondence undefined — and the failure would look like a defect of the
    method while being a defect of the sampling. So the slice is drawn class by
    class, and a class that cannot contribute at least one example is an error
    rather than a silently smaller slice.
    """
    by_class: dict[int, list[int]] = {c: [] for c in range(classes)}
    for index, label in enumerate(targets):
        by_class[int(label)].append(index)

    chosen: list[int] = []
    for label, pool in by_class.items():
        if not pool:
            raise ValueError(f"class {label} is absent from the dataset split")
        take = max(1, int(len(pool) * fraction))
        order = torch.randperm(len(pool), generator=generator).tolist()
        chosen.extend(pool[i] for i in order[:take])
    return chosen


def reduce_split(dataset, fraction: float, classes: int, seed: int):
    """Cut the wiring's own material down to the agreed size, keeping every class.

    The data comes from the baseline's world; this only makes it small enough to run
    several seeds. The slice is drawn per class because the proposal requires every
    class present in the source collection the local correspondence uses — a random
    slice can drop one and leave that correspondence undefined, and the failure would
    look like a defect of the method while being a defect of the sampling.
    """
    if fraction >= 1.0:
        return dataset
    targets = getattr(dataset, "targets", None)
    if targets is None:
        targets = [int(label) for _, label in dataset]
    elif torch.is_tensor(targets):
        targets = targets.tolist()
    generator = torch.Generator().manual_seed(seed)
    return Subset(dataset, stratified_indices(list(targets), fraction, classes, generator))


def synchronize(device: torch.device) -> None:
    """Wait for the device before reading the clock.

    CUDA and MPS queue their kernels and return immediately, so a timer stopped
    without this measures when the work was *submitted*. The number that comes out
    looks precise and describes nothing — and wall time is half of what this file
    exists to report.
    """
    if device.type == "cuda":
        torch.cuda.synchronize()
    elif device.type == "mps":
        torch.mps.synchronize()


@dataclass
class RunMetrics:
    accuracy: float
    seconds: float
    peak_mib: float
    parameters: int


def train_and_score(build: Callable[[int], nn.Module], build_data: Callable,
                    reduction: Reduction, root: Path, seed: int) -> RunMetrics:
    """One seed, end to end, with cost measured around the whole thing."""
    torch.manual_seed(seed)
    raw_train, raw_test, classes = build_data(reduction.dataset, root, seed)
    train_set = reduce_split(raw_train, reduction.fraction, classes, seed)
    test_set = reduce_split(raw_test, reduction.fraction, classes, seed)
    device = torch.device(reduction.device)

    model = build(classes).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()
    loader = DataLoader(train_set, batch_size=reduction.batch_size, shuffle=True)

    tracemalloc.start()
    synchronize(device)
    started = time.perf_counter()
    model.train()
    for _ in range(reduction.epochs):
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            loss_fn(model(images), labels).backward()
            optimizer.step()
    synchronize(device)
    seconds = time.perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1] / (1024 * 1024)
    tracemalloc.stop()

    model.eval()
    correct = total = 0
    with torch.no_grad():
        for images, labels in DataLoader(test_set, batch_size=reduction.batch_size):
            images, labels = images.to(device), labels.to(device)
            correct += int((model(images).argmax(dim=1) == labels).sum())
            total += int(labels.numel())

    return RunMetrics(
        accuracy=correct / total if total else float("nan"),
        seconds=seconds,
        peak_mib=peak,
        parameters=sum(p.numel() for p in model.parameters()),
    )


def summarize(runs: list[RunMetrics]) -> dict:
    """Mean and dispersion. A bare mean over several seeds hides the only thing
    several seeds were run to reveal."""
    def spread(values: list[float]) -> dict:
        return {"mean": statistics.fmean(values),
                "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
                "n": len(values)}

    return {
        "accuracy": spread([r.accuracy for r in runs]),
        "seconds": spread([r.seconds for r in runs]),
        "peakMiB": spread([r.peak_mib for r in runs]),
        "parameters": runs[0].parameters if runs else None,
    }


def compare(builders: dict[str, Callable[[int], nn.Module] | None],
            build_data: Callable, reduction: Reduction, root: Path) -> dict:
    """Run every implementation that can be driven into this exact setting.

    A builder of None means the implementation could not be brought into the common
    reduction as it stands. That is reported as `not applicable` with its reason and
    never filled with a number: inventing one would describe a setting nobody ran.
    """
    results: dict[str, dict] = {}
    for label, build in builders.items():
        if build is None:
            results[label] = {"applicable": False,
                              "reason": "cannot be driven into the common reduction "
                                        "as it stands, and a baseline is never edited "
                                        "to make a comparison possible"}
            continue
        runs = [train_and_score(build, build_data, reduction, root, seed)
                for seed in reduction.seeds]
        results[label] = {"applicable": True, **summarize(runs)}
    return results


def hosted_runtime() -> str | None:
    """Is this a notebook service, where there is no interpreter of our own to use?

    Asked positively, and that matters. The tempting shortcut is to infer it from a
    missing virtualenv — but a repository where nobody has created one yet also has
    no virtualenv, and there the guard is exactly right to refuse. Inferring from the
    absence would drop the protection on the user's own machine to buy portability
    somewhere else.
    """
    if "google.colab" in sys.modules or Path("/content").is_dir():
        return "colab"
    if os.environ.get("KAGGLE_KERNEL_RUN_TYPE") or Path("/kaggle").is_dir():
        return "kaggle"
    if os.environ.get("BINDER_SERVICE_HOST") or os.environ.get("CODESPACES"):
        return "hosted"
    return None


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


def host_label() -> str | None:
    """`MVIA_TIMING_HOST` when the job set it, else `platform.node()`."""
    label = os.environ.get(HOST_LABEL_ENV, "").strip()
    return label or platform.node() or None


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
    return {"host": host_label(), "hostSource": HOST_LABEL_ENV if labelled else "platform.node",
            "hardware": {"machine": platform.machine() or None, "cpu": cpu_model(),
                         "cpuCount": os.cpu_count(), "gpu": gpu_model(torch)},
            "libraries": library_versions(torch), "threads": thread_settings(torch)}


def environment() -> dict:
    """Where this ran — refused when it is the wrong place, stamped when it is elsewhere.

    Wall time and peak memory *are* the measurement, so an interpreter from somewhere
    else does not give a slightly inaccurate result: it gives a correct measurement of
    a different environment, and the summary would attribute it to this repository.

    So when the repository has a virtualenv of its own and something else is running,
    that is a mistake and it stops here. But on a hosted runtime — a notebook service
    where the checkout has no virtualenv — there is nothing to compare against, and
    refusing would only mean the benchmark cannot run there at all. There the
    environment is recorded instead: a table produced elsewhere is labelled as produced
    elsewhere rather than attributed to a machine that never saw it.

    The file sits at <repo>/src/<Package>_Benchmark/benchmark.py, so the repository is
    two levels up.
    """
    refuse_foreign_interpreter()
    repository = Path(__file__).resolve().parents[2]
    prefix = Path(sys.prefix).resolve()
    inside = prefix.is_relative_to(repository)
    return {
        "repository": str(repository),
        "interpreter": str(prefix),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "selfHosted": inside,
        "hostedRuntime": hosted_runtime(),
        "runtime": runtime_record(torch),
    }


def main(argv: list[str] | None = None) -> int:
    where = environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="JSON holding the reduction")
    parser.add_argument("--data", default="./.benchmark-data", help="dataset cache")
    parser.add_argument("--out", required=True, help="where to write the summary")
    args = parser.parse_args(argv)

    reduction = Reduction(**json.loads(Path(args.config).read_text(encoding="utf-8")))
    # Filled in from the wiring `probe` proposed and the user completed. A bare
    # backbone is not either implementation: training one and reporting it would
    # measure the backbone and call it the method.
    #
    # Both stay unset here on purpose. `build_wiring` is written into the target
    # repository as part of the flow, and its absence is refused below rather than
    # silently producing a table about nothing.
    try:
        # `build_data` is part of the wiring for the same reason the builders are:
        # the data belongs to the baseline's world, not to this file.
        #
        # Spelled both ways for the same reason `verdict` is above: `wiring.py` is
        # written beside this file, so it is a sibling module under a script run and
        # a sibling submodule under a package import.
        if __package__:
            from .wiring import build_baseline, build_data, build_new
        else:
            from wiring import build_baseline, build_data, build_new
    except ImportError as missing:
        raise SystemExit(
            "wiring.py is missing: this benchmark has nothing to compare.\n"
            f"  ({missing})\n"
            "Run `probe` and complete the wiring it proposes — which modules carry "
            "the trainable terms, where the backbone enters, what the head predicts "
            "over, and how the baseline's own data is loaded — then write it as "
            "wiring.py beside this file. Running without it would train a bare "
            "backbone on a dataset this file chose, and report it as the method."
        )

    builders: dict[str, Callable[[int], nn.Module] | None] = {
        "new": lambda classes: build_new(classes, reduction.backbone),
        "baseline": (lambda classes: build_baseline(classes, reduction.backbone))
                    if build_baseline is not None else None,
    }

    measured = compare(builders, build_data, reduction, Path(args.data))
    # One row per dimension, both sides side by side, so the verdict rules that serve
    # the synthetic sweep serve this one unchanged.
    rows = []
    for dimension, better in DIMENSIONS.items():
        def side(label):
            entry = measured.get(label, {})
            if not entry.get("applicable"):
                return None
            value = entry.get(dimension)
            return value if isinstance(value, dict) else {"mean": value, "stdev": 0.0, "n": 1}
        rows.append({"dimension": dimension, "better": better,
                     "baseline": side("baseline"), "new": side("new")})

    judged = judge(rows)
    summary = {
        "kind": "bounded",
        "setting": reduction.setting,
        "revision": reduction.revision,
        "reduction": asdict(reduction),
        "environment": where,
        "comparison": judged,
        "tally": tally(judged),
    }
    print(render(judged, {**asdict(reduction), "seeds": len(reduction.seeds)}))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
