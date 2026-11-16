"""`verify --shards` warns, never refuses, when shards ran on different hosts
or under different thread settings (issue #186, S8).

Each shard's `shard.json` carries a top-level `runtime` block written by the
stamp kit's `write_shard`: `{host, hostSource, hardware, libraries, threads}`.
A merge that pools shards from two hosts, or from two thread settings, is
flagged in `distribution.runtimeWarnings`; the verdict, the exit code and
`shardsDisagree` stay exactly what they were. Shards written before the
`runtime` block existed are skipped.

Driven through the public CLI and read off its stdout.
Shards are written to a `tempfile.mkdtemp()` outside the worktree.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
CLI = FORGE / "skills/proposal-implementation/scripts/implementation_cli.py"

DECLARATION = (
    "__benchmark__ = {\n"
    "    'revision': 'r01.md',\n"
    "    'arms': {'floor': {'sections': ['3']}, "
    "'full': {'sections': ['3']}},\n"
    "    'distribution': {'axis': 'repetition',\n"
    "                     'poolable': ['score'],\n"
    "                     'perEnvironment': ['wallSeconds'],\n"
    "                     'perRun': ['seed'],\n"
    "                     'identicalAcrossShards': ['epochs']},\n"
    "}\n")

THREADS = {"OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4"}


def runtime(host, threads=None):
    return {"host": host, "hostSource": "env", "hardware": {"machine": "x86_64"},
            "libraries": {"numpy": "2.1.0"},
            "threads": dict(THREADS if threads is None else threads)}


class VerifyShardsRuntimeWarnings(unittest.TestCase):

    def scratch(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def build_target(self):
        # `verify` refuses a target outside `implementations/` (git-excluded),
        # so the target lives there and is removed; shards stay outside.
        box = Path(tempfile.mkdtemp(prefix="_runtimewarn_",
                                    dir=FORGE / "implementations"))
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        for directory in ("src/Method", "src/Method_Benchmark", "Method"):
            (box / directory).mkdir(parents=True)
        (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
        (box / "src/Method_Benchmark/__init__.py").write_text(
            DECLARATION, encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)
        return box

    def build_shards(self, stamps):
        root = self.scratch() / "shards"
        root.mkdir()
        for shard, stamp in stamps.items():
            (root / shard).mkdir()
            (root / shard / "shard.json").write_text(json.dumps(stamp),
                                                     encoding="utf-8")
        return root

    def verify(self, box, shards=None):
        argv = [sys.executable, str(CLI), "verify", "--target", str(box),
                "--name", "Method"]
        if shards is not None:
            argv += ["--shards", str(shards)]
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=FORGE)
        return proc

    def distribution(self, box, shards):
        proc = self.verify(box, shards)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)["distribution"]

    def test_cross_host_shards_are_flagged_without_changing_the_verdict(self):
        box = self.build_target()
        same = self.distribution(box, self.build_shards({
            "a": {"epochs": 5, "runtime": runtime("host-aaaaaaaaaaaa")},
            "b": {"epochs": 5, "runtime": runtime("host-aaaaaaaaaaaa")}}))
        mixed = self.distribution(box, self.build_shards({
            "a": {"epochs": 5, "runtime": runtime("host-aaaaaaaaaaaa")},
            "b": {"epochs": 5, "runtime": runtime("host-bbbbbbbbbbbb")}}))

        self.assertEqual(mixed["runtimeWarnings"], [
            {"kind": "cross-host", "shards": ["a", "b"],
             "values": ["host-aaaaaaaaaaaa", "host-bbbbbbbbbbbb"]}])
        # Non-blocking: no refusal, same status and disagreements as the
        # same-host merge of the same target.
        self.assertEqual(mixed["shardsDisagree"], [])
        self.assertEqual(mixed["status"], same["status"])

    def test_differing_thread_settings_are_flagged(self):
        box = self.build_target()
        distribution = self.distribution(box, self.build_shards({
            "a": {"epochs": 5, "runtime": runtime("host-aaaaaaaaaaaa")},
            "b": {"epochs": 5, "runtime": runtime(
                "host-aaaaaaaaaaaa", {"OMP_NUM_THREADS": "1"})}}))

        self.assertEqual(distribution["runtimeWarnings"], [
            {"kind": "thread-settings", "shards": ["a", "b"],
             "values": [THREADS, {"OMP_NUM_THREADS": "1"}]}])

    def test_same_host_same_threads_produce_no_warning(self):
        box = self.build_target()
        distribution = self.distribution(box, self.build_shards({
            "a": {"epochs": 5, "runtime": runtime("host-aaaaaaaaaaaa")},
            "b": {"epochs": 5, "runtime": runtime("host-aaaaaaaaaaaa")}}))

        self.assertEqual(distribution["runtimeWarnings"], [])

    def test_older_shards_without_runtime_are_skipped(self):
        box = self.build_target()
        distribution = self.distribution(box, self.build_shards({
            "a": {"epochs": 5},
            "b": {"epochs": 5, "runtime": runtime("host-bbbbbbbbbbbb")}}))

        self.assertEqual(distribution["runtimeWarnings"], [])
        self.assertEqual(distribution["shardsArrived"], ["a", "b"])

    def test_disagreement_refusal_is_unchanged_alongside_a_warning(self):
        box = self.build_target()
        distribution = self.distribution(box, self.build_shards({
            "a": {"epochs": 5, "runtime": runtime("host-aaaaaaaaaaaa")},
            "b": {"epochs": 9, "runtime": runtime("host-bbbbbbbbbbbb")}}))

        self.assertEqual(distribution["shardsDisagree"], ["epochs"])
        self.assertEqual(distribution["status"], "incomplete")
        self.assertEqual([w["kind"] for w in distribution["runtimeWarnings"]],
                         ["cross-host"])

    def test_without_the_flag_no_warning_is_reported(self):
        box = self.build_target()
        proc = self.verify(box)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["distribution"]["runtimeWarnings"], [])


if __name__ == "__main__":
    unittest.main()
