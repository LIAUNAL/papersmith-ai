"""Remote readiness. Will a remote smoke record, and will the forward run there?

Two failures surface only on a remote worker, after a clone, an install and a
queue: a smoke that leaves no `shard.json` (or one missing the evidence the job
requires), and a forward that builds a tensor on the CPU while its inputs sit
on the GPU. Both are cheap to catch here.

- The stamp tests check `src/{{PKG}}/remote_stamp.py`: nothing is written
  without `FORGE_RUN_MODE`, and the declared fields are written with it.
- The device guard runs a callable with `torch.einsum`, `torch.matmul` and the
  `@` operator patched to refuse operands on different devices. Run on
  `torch.device("meta")` it costs nothing and needs no GPU; `meta` alone does
  not refuse a CPU tensor mixed into it, which is why the guard exists.

Fill in `FORWARD` below with a callable that builds this target's inputs on
the device it is given and runs its forward pass. Until then that one test
skips and says so. Every torch test skips when torch is not installed.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from contextlib import contextmanager

import pytest

PACKAGE = "{{PKG}}"

#: Fill in: `def FORWARD(device): ...` building this target's inputs on
#: `device` and running its forward. `None` until the target wires it.
FORWARD = None

try:
    import torch
except ImportError:
    torch = None

_ORIGINAL_EINSUM = torch.einsum if torch is not None else None


def _stamp():
    return importlib.import_module(f"{PACKAGE}.remote_stamp")


def _devices(values) -> set:
    found = set()
    for value in values:
        if isinstance(value, (list, tuple)):
            found |= _devices(value)
        elif torch is not None and torch.is_tensor(value):
            found.add(value.device)
    return found


def _guarded(name, original):
    def call(*args, **kwargs):
        devices = _devices([*args, *kwargs.values()])
        if len(devices) > 1:
            raise AssertionError(
                f"{name} mixes devices {sorted(str(d) for d in devices)}: a "
                "tensor was built without `device=` taken from the inputs")
        return original(*args, **kwargs)
    return call


@contextmanager
def single_device():
    """Patch einsum, matmul and `@` to refuse operands on two devices."""
    if torch is None:
        pytest.skip("torch is not installed; the device guard needs it")
    patched = [(torch, "einsum", torch.einsum),
               (torch, "matmul", torch.matmul),
               (torch.Tensor, "__matmul__", torch.Tensor.__matmul__)]
    for owner, attribute, original in patched:
        label = "matmul" if "matmul" in attribute else attribute
        setattr(owner, attribute, _guarded(f"torch.{label}", original))
    try:
        yield
    finally:
        for owner, attribute, original in patched:
            setattr(owner, attribute, original)


def test_stamp_writes_nothing_without_the_run_mode(tmp_path, monkeypatch):
    stamp = _stamp()
    monkeypatch.delenv(stamp.RUN_MODE_ENV, raising=False)
    assert stamp.write_shard({"units": 1}, tmp_path) is None
    assert not (tmp_path / stamp.SHARD).exists()


def test_stamp_writes_the_declared_fields_under_the_run_mode(tmp_path, monkeypatch):
    stamp = _stamp()
    monkeypatch.setenv(stamp.RUN_MODE_ENV, "smoke")
    path = stamp.write_shard({"units": 1}, tmp_path, device="cpu")
    shard = json.loads(path.read_text(encoding="utf-8"))
    head = subprocess.run(
        ["git", "-C", str(stamp.repository_root()), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False)
    expected = head.stdout.strip() if head.returncode == 0 else None
    assert shard["mode"] == "smoke"
    assert shard["runs"] == {"units": 1}
    assert shard["evidence"]["commit"] == (expected or None)
    assert len(shard["evidence"]["sourcesDigest"]) == 64
    assert shard["environment"]["device"]["kind"] == "cpu"


def test_device_guard_refuses_a_mixed_einsum():
    if torch is None:
        pytest.skip("torch is not installed; the device guard needs it")
    inputs = torch.ones(2, 3, device="meta")
    with pytest.raises(AssertionError, match="mixes devices"):
        with single_device():
            torch.einsum("bi,i->b", inputs, torch.ones(3))


def test_forward_keeps_one_device():
    if torch is None:
        pytest.skip("torch is not installed; the device guard needs it")
    if FORWARD is None:
        pytest.skip(
            "tests/test_remote_readiness.py: set FORWARD to a callable(device) "
            "that builds this target's inputs on `device` and runs its forward; "
            "it is then run on torch.device('meta') under the device guard")
    with single_device():
        FORWARD(torch.device("meta"))
