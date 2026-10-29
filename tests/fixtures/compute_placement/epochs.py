"""Synthetic epochs for the timing probe's tests, importable by spawned workers."""

from __future__ import annotations

import time


def sleepy_epoch(settings: dict, wrap) -> None:
    """Four batches: 10 ms waiting on data, 10 ms computing each."""
    def batches():
        for index in range(4):
            time.sleep(0.01)
            yield index

    for _ in wrap(batches()):
        time.sleep(0.01)
