#!/usr/bin/env python3
"""timing_probe: measure the candidate ways to run one epoch, and pick none.

Run by the TARGET's own interpreter (its isolated venv) against the target's
own epoch function, so what is timed is what will run:

    <target>/.venv/bin/python skills/remote-parallelism/scripts/timing_probe.py \\
        --path <target>/src --entry <package>.<module>:<function> --arm <arm id> \\
        --out <target>/<Name>/Results/timing.json [--candidates local-cpu-1,local-cpu-4,local-mps] \\
        [--batch-sizes 32,128] [--num-workers 0,4] [--pin-memory false,true] [--prefetch 2] \\
        [--threads 4] [--dtype float32] [--data-source raw,cached] [--cap-seconds 300]

The entry is `epoch(settings, wrap)`: it runs ONE epoch with `settings`
(`device`, `candidate`, `processes`, and each swept key: `batchSize`,
`numWorkers`, `pinMemory`, `prefetch`, `threads`, `dtype`, `dataSource`) and
iterates its data loader through `wrap(loader)`, which times every wait for
the next batch. The epoch's wall time minus that wait is compute.

For each candidate -- `local-cpu-<N>` (N concurrent processes, each timed
under the others' contention), `local-mps`, `local-cuda`, or
`<host>:<owner>/<machine>` when the probe runs on a remote machine -- one
epoch runs per setting until the candidate's time cap: the first setting
always runs, and every setting past the cap is listed under `skipped` with its
reason. An accelerator this machine does not have is skipped, never run on
the CPU under its name. Rows are schema 2 timing measurements, appended to
`Results/timing.json` (a schema 1 record is upgraded and keeps its rows), the
one file this probe writes. `scales` is copied from the protocol, never
guessed.

It never picks a device. `device_from_plan` reads the device out of
`parallelism_cli.py plan`'s measured recommendation and refuses when there is
none: no evidence, no choice, and the CPU is a candidate like any other.

Stdlib only; `torch` is imported lazily and only to read what it already sees.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import importlib
import itertools
import json
import multiprocessing
import os
import sys
import time
from pathlib import Path

SCHEMA = 2
DEFAULT_CAP_SECONDS = 300
#: The swept settings, in the order a sweep varies them (the first value of
#: each runs first). Absent or None values are not recorded.
SETTING_KEYS = ("batchSize", "numWorkers", "pinMemory", "prefetch", "threads", "dtype", "dataSource")


class ProbeRefusal(Exception):
    pass


def _torch():
    return sys.modules.get("torch")


def host_info() -> dict:
    """What this machine is: logical cores, RAM, and the accelerators torch sees."""
    try:
        ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
    except (AttributeError, OSError, ValueError):
        ram = None
    torch = _torch()
    if torch is None:
        try:
            import torch  # noqa: F811  (lazy: a target without torch still probes)
        except ImportError:
            torch = None
    mps = bool(torch is not None and getattr(torch.backends, "mps", None) is not None
               and torch.backends.mps.is_available())
    cuda = bool(torch is not None and torch.cuda.is_available())
    return {"cpuCount": os.cpu_count() or 1, "ramGB": None if ram is None else round(ram, 1),
            "mps": mps, "cuda": cuda}


def local_candidates(info: dict) -> list[str]:
    """CPU always (one process, and half the cores in parallel), accelerators when present."""
    names = ["local-cpu-1"]
    if info["cpuCount"] // 2 > 1:
        names.append(f"local-cpu-{info['cpuCount'] // 2}")
    names += [name for name, key in (("local-mps", "mps"), ("local-cuda", "cuda")) if info[key]]
    return names


def processes_of(candidate: str) -> int:
    return int(candidate.rsplit("-", 1)[1]) if candidate.startswith("local-cpu-") else 1


def device_for(candidate: str, info: dict) -> str:
    """The device a candidate computes on, or a refusal when this machine lacks it."""
    if candidate.startswith("local-cpu-") or candidate.endswith("/cpu"):
        return "cpu"
    if candidate == "local-mps":
        if not info["mps"]:
            raise ProbeRefusal("this machine has no mps device")
        return "mps"
    if not info["cuda"]:
        raise ProbeRefusal(f"{candidate} needs a CUDA device and this machine has none")
    torch = _torch()
    name = torch.cuda.get_device_name(0) if torch is not None else "unknown"
    return f"cuda:{name}"


class LoadTimer:
    """Wraps a loader and adds up the time spent waiting for each next batch."""

    def __init__(self, clock) -> None:
        self.clock, self.seconds = clock, 0.0

    def wrap(self, iterable):
        iterator = iter(iterable)
        while True:
            start = self.clock()
            try:
                item = next(iterator)
            except StopIteration:
                self.seconds += self.clock() - start
                return
            self.seconds += self.clock() - start
            yield item


def _set_threads(threads) -> None:
    torch = _torch()
    if threads and torch is not None:
        torch.set_num_threads(threads)


def time_epoch(epoch, settings: dict, clock=time.perf_counter) -> tuple[float, float]:
    """One epoch's wall time and the part of it spent waiting on data."""
    _set_threads(settings.get("threads"))
    timer = LoadTimer(clock)
    start = clock()
    epoch(settings, timer.wrap)
    return clock() - start, timer.seconds


def _concurrent(epoch, settings: dict, processes: int) -> tuple[float, float]:
    """`processes` epochs at once, in spawned workers; the mean per process."""
    context = multiprocessing.get_context("spawn")
    with concurrent.futures.ProcessPoolExecutor(max_workers=processes, mp_context=context) as pool:
        results = list(pool.map(time_epoch, [epoch] * processes, [settings] * processes))
    return (sum(wall for wall, _ in results) / processes, sum(load for _, load in results) / processes)


def settings_grid(grid: dict, candidate: str, info: dict) -> list[dict]:
    values = dict(grid)
    if candidate.startswith("local-cpu-") and not values.get("threads"):
        values["threads"] = [max(1, info["cpuCount"] // processes_of(candidate))]
    keys = [key for key in SETTING_KEYS if values.get(key)]
    return [dict(zip(keys, combo)) for combo in itertools.product(*(values[key] for key in keys))]


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sweep(epoch, *, arm: str, candidates: list[str], grid: dict | None = None, host: str = "local",
          cap_seconds: float = DEFAULT_CAP_SECONDS, setup=None, info: dict | None = None,
          clock=time.perf_counter, now=_now) -> dict:
    """Time `epoch` for every candidate and setting, each candidate within its cap."""
    if not candidates:
        raise ProbeRefusal("name the candidates to measure: the probe never picks one")
    info = host_info() if info is None else info
    rows, skipped = [], []
    for candidate in candidates:
        try:
            device = device_for(candidate, info)
        except ProbeRefusal as refusal:
            skipped.append({"candidate": candidate, "settings": {}, "reason": str(refusal)})
            continue
        processes = processes_of(candidate)
        started = clock()
        setup_seconds = None
        if setup is not None:
            mark = clock()
            setup({"device": device, "candidate": candidate, "processes": processes})
            setup_seconds = clock() - mark
        for index, setting in enumerate(settings_grid(grid or {}, candidate, info)):
            if index and clock() - started >= cap_seconds:
                skipped.append({"candidate": candidate, "settings": setting,
                                "reason": f"time cap of {cap_seconds:g} s reached for {candidate}"})
                continue
            settings = dict(setting, device=device, candidate=candidate, processes=processes)
            try:
                wall, load = (_concurrent(epoch, settings, processes) if processes > 1
                              else time_epoch(epoch, settings, clock))
            except Exception as exc:  # noqa: BLE001  (a failed setting is reported, not fatal)
                skipped.append({"candidate": candidate, "settings": setting,
                                "reason": f"{type(exc).__name__}: {exc}"[:300]})
                continue
            row = {"measuredAt": now(), "host": host, "candidate": candidate, "device": device, "arm": arm,
                   "unit": "epoch", "secondsPerUnit": round(max(wall, 1e-6), 4), "unitsMeasured": 1}
            if candidate.startswith("local-cpu-") or processes > 1:
                row["processes"] = processes
            row.update({key: value for key, value in setting.items() if value is not None})
            row.update({"loadSeconds": round(min(load, wall), 4),
                        "computeSeconds": round(max(wall - load, 0.0), 4)})
            if setup_seconds is not None:
                row["setupSeconds"] = round(setup_seconds, 4)
            rows.append(row)
    return {"rows": rows, "skipped": skipped, "hosts": {host: info}}


def write_record(path, result: dict, *, scales: dict | None = None) -> Path:
    """Append the sweep's rows to `<Name>/Results/timing.json`, the only file written."""
    path = Path(path)
    if path.name != "timing.json" or path.parent.name != "Results":
        raise ProbeRefusal(f"{path}: the probe writes only <Name>/Results/timing.json")
    record = None
    if path.is_file():
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("schema") not in (1, 2):
            raise ProbeRefusal(f"{path} is not a schema 1 or 2 timing record; it is left untouched")
    if scales is None and record is None:
        raise ProbeRefusal("scales are copied from the approved protocol and the declared pilot, never "
                           "guessed: pass them for a new record")
    record = record or {"measurements": []}
    upgraded = {"schema": SCHEMA, "hosts": dict(record.get("hosts") or {}, **result["hosts"]),
                "measurements": list(record.get("measurements") or []) + list(result["rows"]),
                "scales": scales if scales is not None else record["scales"]}
    path.write_text(json.dumps(upgraded, indent=2) + "\n", encoding="utf-8")
    return path


def device_from_plan(plan, stage: str) -> str:
    """The device `plan` recommends for `stage`, measured; a refusal otherwise."""
    if isinstance(plan, (str, Path)):
        plan = json.loads(Path(plan).read_text(encoding="utf-8"))
    recommended = (((plan or {}).get("plans") or {}).get(stage) or {}).get("recommended")
    if not isinstance(recommended, dict) or not recommended.get("device"):
        raise ProbeRefusal(f"no measured recommendation for {stage}: run the probe and "
                           "parallelism_cli.py plan first; there is no default device")
    return recommended["device"]


def _values(raw: str | None, kind):
    if raw is None:
        return None
    parse = {"bool": lambda text: {"true": True, "false": False}[text.strip().lower()]}.get(kind, kind)
    return [parse(part) for part in raw.split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="timing_probe.py", description=__doc__.split("\n", 1)[0])
    parser.add_argument("--entry", required=True, help="<module>:<function>, the target's epoch(settings, wrap)")
    parser.add_argument("--path", action="append", default=[], help="a directory put on sys.path first")
    parser.add_argument("--setup", default=None, help="<module>:<function>, timed once per candidate")
    parser.add_argument("--arm", required=True)
    parser.add_argument("--out", required=True, help="<Name>/Results/timing.json")
    parser.add_argument("--host", default="local", help="local, or <host>:<owner> on a remote machine")
    parser.add_argument("--candidates", default=None, help="comma list; default: local CPU candidates and "
                                                           "the accelerators this machine has")
    parser.add_argument("--scales", default=None, help="JSON {poc: {...}, full: {...}} for a new record")
    parser.add_argument("--cap-seconds", type=float, default=DEFAULT_CAP_SECONDS)
    for flag, kind in (("--batch-sizes", int), ("--num-workers", int), ("--pin-memory", "bool"),
                       ("--prefetch", int), ("--threads", int), ("--dtype", str), ("--data-source", str)):
        parser.add_argument(flag, default=None, help=f"comma list ({kind if isinstance(kind, str) else kind.__name__})")
    args = parser.parse_args(argv)
    for entry in reversed(args.path):
        sys.path.insert(0, entry)

    def resolve(spec: str):
        module, _, name = spec.partition(":")
        return getattr(importlib.import_module(module), name)

    info = host_info()
    grid = {"batchSize": _values(args.batch_sizes, int), "numWorkers": _values(args.num_workers, int),
            "pinMemory": _values(args.pin_memory, "bool"), "prefetch": _values(args.prefetch, int),
            "threads": _values(args.threads, int), "dtype": _values(args.dtype, str),
            "dataSource": _values(args.data_source, str)}
    candidates = _values(args.candidates, str) or local_candidates(info)
    try:
        result = sweep(resolve(args.entry), arm=args.arm, candidates=candidates, host=args.host,
                       grid={key: value for key, value in grid.items() if value},
                       cap_seconds=args.cap_seconds, info=info,
                       setup=resolve(args.setup) if args.setup else None)
        written = write_record(args.out, result, scales=json.loads(args.scales) if args.scales else None)
    except ProbeRefusal as refusal:
        print(json.dumps({"error": "probe-refused", "message": str(refusal)}), file=sys.stderr)
        return 2
    print(json.dumps({"written": str(written), "rows": len(result["rows"]), "skipped": result["skipped"],
                      "hosts": result["hosts"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
