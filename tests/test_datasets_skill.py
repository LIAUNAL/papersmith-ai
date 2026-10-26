"""The `datasets` skill: toy sets, discovery, license gate, QC, official
preparation and private publishing behind the operator's consent.

Every verb is driven through `datasets_cli.run(argv, http=..., runner=...)`,
the same entry point `main()` uses, with the network and the remote host's
command line injected: no test here opens a socket or spawns the real client.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "datasets"
CLI_PATH = SKILL / "scripts" / "datasets_cli.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("datasets_cli_under_test", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLI = load_cli()
TOKEN_SENTINEL = "KGAT_sentinel_never_printed_0123456789"


class Run:
    """One CLI invocation: exit code, stdout, stderr, parsed stdout JSON."""

    def __init__(self, root: Path, argv: list[str], **inject) -> None:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.code = CLI.run(["--root", str(root), *argv], **inject)
        self.out, self.err = out.getvalue(), err.getvalue()
        try:
            self.json = json.loads(self.out) if self.out.strip().startswith("{") else None
        except ValueError:
            self.json = None
        try:
            self.error = json.loads(self.err) if self.err.strip().startswith("{") else None
        except ValueError:
            self.error = None


class Base(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()

    def run_cli(self, *argv: str, **inject) -> Run:
        return Run(self.root, list(argv), **inject)

    def registry(self) -> list[dict]:
        return json.loads((self.root / "datasets" / "registry.json").read_text(encoding="utf-8"))

    def entry(self, slug: str) -> dict:
        return next(item for item in self.registry() if item["slug"] == slug)

    def write_csv(self, name: str, rows: list[dict]) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return path


# --------------------------------------------------------------------- synth
class SynthTests(Base):
    def test_eeg_toy_set_is_deterministic_for_a_seed_and_has_its_shape(self) -> None:
        args = ["synth", "--slug", "toy-eeg", "--kind", "eeg", "--seed", "7", "--n-subjects", "4",
                "--n-per-subject", "6", "--channels", "3", "--length", "32", "--sfreq", "64"]
        first = self.run_cli(*args)
        self.assertEqual(first.code, 0, first.err)
        data = self.root / "datasets" / "toy-eeg" / "toy-eeg.csv"
        before = data.read_bytes()
        again = self.run_cli(*args, "--force")
        self.assertEqual(again.code, 0, again.err)
        self.assertEqual(data.read_bytes(), before, "same seed must give the same bytes")
        rows = list(csv.reader(io.StringIO(before.decode("utf-8"))))
        self.assertEqual(rows[0][:3], ["subject", "trial", "label"])
        self.assertEqual(len(rows) - 1, 4 * 6)
        self.assertEqual(len(rows[0]), 3 + 3 * 32)
        self.assertEqual({r[2] for r in rows[1:]}, {"0", "1"})

    def test_a_different_seed_changes_the_data(self) -> None:
        base = ["--kind", "classification", "--n-subjects", "3", "--n-per-subject", "4", "--channels", "2"]
        self.assertEqual(self.run_cli("synth", "--slug", "a-toy", "--seed", "1", *base).code, 0)
        self.assertEqual(self.run_cli("synth", "--slug", "b-toy", "--seed", "2", *base).code, 0)
        a = (self.root / "datasets/a-toy/a-toy.csv").read_text(encoding="utf-8")
        b = (self.root / "datasets/b-toy/b-toy.csv").read_text(encoding="utf-8")
        self.assertNotEqual(a, b)
        header = a.splitlines()[0].split(",")
        self.assertEqual(header, ["subject", "sample", "label", "x0", "x1"])

    def test_eeg_band_power_depends_on_the_class(self) -> None:
        self.run_cli("synth", "--slug", "toy-eeg", "--kind", "eeg", "--seed", "3", "--n-subjects", "4",
                     "--n-per-subject", "20", "--channels", "1", "--length", "64", "--sfreq", "64")
        rows = list(csv.DictReader((self.root / "datasets/toy-eeg/toy-eeg.csv").open(encoding="utf-8")))
        power = {"0": [], "1": []}
        for row in rows:
            values = [float(row[f"ch0_t{t}"]) for t in range(64)]
            power[row["label"]].append(sum(v * v for v in values) / len(values))
        mean = {k: sum(v) / len(v) for k, v in power.items()}
        self.assertGreater(mean["1"], mean["0"] * 1.5)

    def test_toy_registry_entry_and_toy_md_record_the_parameters(self) -> None:
        self.run_cli("synth", "--slug", "toy-eeg", "--kind", "eeg", "--seed", "5")
        entry = self.entry("toy-eeg")
        self.assertEqual(entry["role"], "toy")
        self.assertEqual(entry["source"]["kind"], "synthetic")
        self.assertEqual(entry["license"]["decision"], "allowed")
        self.assertEqual(entry["files"], ["datasets/toy-eeg/toy-eeg.csv"])
        toy_md = (self.root / "datasets/toy-eeg/TOY.md").read_text(encoding="utf-8")
        for needle in ("seed", "5", "eeg", "sfreq"):
            self.assertIn(needle, toy_md)

    # ---------------------------------------------------------- capacity
    CAPACITY = ["synth", "--slug", "cap", "--kind", "eeg", "--profile", "capacity", "--seed", "3",
                "--n-train", "4", "--n-val", "2", "--n-test", "2", "--n-per-subject", "2", "--length", "64"]

    def npy(self, path: Path) -> tuple[tuple[int, ...], list[float]]:
        blob = path.read_bytes()
        self.assertEqual(blob[:8], b"\x93NUMPY\x01\x00")
        size = struct.unpack("<H", blob[8:10])[0]
        header = blob[10:10 + size].decode("latin1")
        self.assertEqual((10 + size) % 64, 0)
        self.assertIn("'descr': '<f4'", header)
        shape = tuple(int(n) for n in re.search(r"\(([^)]*)\)", header).group(1).split(",") if n.strip())
        values = list(struct.unpack(f"<{len(blob[10 + size:]) // 4}f", blob[10 + size:]))
        return shape, values

    def test_a_capacity_member_is_seeded_balanced_and_described(self) -> None:
        first = self.run_cli(*self.CAPACITY, "--rule", "monotone", "--d-prime", "1.5")
        self.assertEqual(first.code, 0, first.err)
        folder = self.root / "datasets" / "cap"
        npy, side = folder / "monotone-d1.5-s3.npy", folder / "monotone-d1.5-s3.json"
        before = npy.read_bytes()
        again = self.run_cli(*self.CAPACITY, "--rule", "monotone", "--d-prime", "1.5", "--force")
        self.assertEqual(again.code, 0, again.err)
        self.assertEqual(npy.read_bytes(), before, "same rule, d', seed and sizes must give the same bytes")
        shape, values = self.npy(npy)
        self.assertEqual(shape, ((4 + 2 + 2) * 2, 19, 64))
        self.assertEqual(len(values), shape[0] * 19 * 64)
        meta = json.loads(side.read_text(encoding="utf-8"))
        self.assertEqual((meta["rule"], meta["dPrime"], meta["seed"]), ("monotone", 1.5, 3))
        self.assertEqual(meta["sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(meta["channels"][:2], ["Fp1", "Fp2"])
        for split, n in (("train", 4), ("validation", 2), ("test", 2)):
            labels = [s["label"] for s in meta["subjects"] if s["split"] == split]
            self.assertEqual(sorted(labels), [0] * (n // 2) + [1] * (n // 2))
        self.assertEqual(len(meta["epochs"]["label"]), shape[0])
        self.assertEqual(first.json["file"], "datasets/cap/monotone-d1.5-s3.npy")

    def test_capacity_members_share_one_registry_entry_and_toy_md(self) -> None:
        self.assertEqual(self.run_cli(*self.CAPACITY, "--rule", "monotone", "--d-prime", "1.5").code, 0)
        other = self.run_cli(*self.CAPACITY, "--rule", "frequency-two")
        self.assertEqual(other.code, 0, other.err)
        entry = self.entry("cap")
        self.assertEqual(entry["role"], "toy")
        self.assertEqual(entry["files"], ["datasets/cap/frequency-two-s3.npy", "datasets/cap/monotone-d1.5-s3.npy"])
        toy_md = (self.root / "datasets/cap/TOY.md").read_text(encoding="utf-8")
        for needle in ("capacity", "frequency-two-s3.npy", "monotone-d1.5-s3.npy", "effectGain", "Phi(d'/2)"):
            self.assertIn(needle, toy_md)
        self.assertNotEqual((self.root / "datasets/cap/frequency-two-s3.npy").read_bytes(),
                            (self.root / "datasets/cap/monotone-d1.5-s3.npy").read_bytes())

    def test_the_monotone_rule_raises_the_theta_beta_ratio_of_class_one(self) -> None:
        sys.path.insert(0, str(CLI_PATH.parent))
        import capacity_toy
        values, meta = capacity_toy.generate("monotone", 6.0, 1, {"train": 8, "validation": 0, "test": 0}, 2, 128)
        n, c, t = meta["shape"]
        fz = capacity_toy.CHANNELS.index("Fz")

        def power(row, lo, hi):
            out = 0.0
            for k in range(int(lo * t / 128), int(hi * t / 128) + 1):
                re_ = sum(row[i] * math.cos(2 * math.pi * k * i / t) for i in range(t))
                im_ = sum(row[i] * math.sin(2 * math.pi * k * i / t) for i in range(t))
                out += re_ * re_ + im_ * im_
            return out

        ratio = {0: [], 1: []}
        for e in range(n):
            row = values[(e * c + fz) * t:(e * c + fz + 1) * t]
            ratio[meta["epochs"]["label"][e]].append(math.log(power(row, 4, 8) / power(row, 13, 30)))
        self.assertGreater(sum(ratio[1]) / len(ratio[1]), sum(ratio[0]) / len(ratio[0]) + 1.0)

    def test_capacity_refuses_what_it_would_otherwise_ignore(self) -> None:
        cases = [((), "bad-argument"),                                   # no --rule
                 (("--rule", "monotone"), "bad-argument"),                # monotone without d'
                 (("--rule", "interaction", "--d-prime", "1"), "bad-argument"),
                 (("--rule", "interaction", "--channels", "4"), "bad-argument"),
                 (("--rule", "interaction", "--n-subjects", "6"), "bad-argument"),
                 (("--rule", "interaction", "--label-per", "trial"), "bad-argument"),
                 (("--rule", "interaction", "--sfreq", "50"), "bad-argument")]
        for extra, code in cases:
            with self.subTest(extra=extra):
                run = self.run_cli(*self.CAPACITY, *extra)
                self.assertEqual(run.code, 2, run.out)
                self.assertEqual(run.error["error"], code)
        odd = [a if a != "4" else "3" for a in self.CAPACITY]
        self.assertEqual(self.run_cli(*odd, "--rule", "interaction").error["error"], "bad-argument")
        self.assertEqual(self.run_cli(*self.CAPACITY, "--rule", "interaction").code, 0)
        again = self.run_cli(*self.CAPACITY, "--rule", "interaction")
        self.assertEqual(again.error["error"], "member-exists")
        self.assertFalse((self.root / "datasets/cap/cap.csv").exists())

    def test_an_existing_slug_is_refused_without_force(self) -> None:
        self.run_cli("synth", "--slug", "toy-eeg", "--kind", "eeg", "--seed", "5")
        again = self.run_cli("synth", "--slug", "toy-eeg", "--kind", "eeg", "--seed", "5")
        self.assertEqual(again.code, 2)
        self.assertEqual(again.error["error"], "slug-exists")
        self.assertIn("objective", again.error)

    def test_a_malformed_slug_is_refused(self) -> None:
        bad = self.run_cli("synth", "--slug", "Bad Slug!", "--kind", "eeg")
        self.assertEqual(bad.code, 2)
        self.assertEqual(bad.error["error"], "bad-slug")


# -------------------------------------------------------------------- search
class FakeHttp:
    """Answers per host substring; a host mapped to an exception raises it."""

    def __init__(self, answers: dict) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, url, body=None, headers=None, timeout=20):
        self.calls.append((method, url))
        for needle, answer in self.answers.items():
            if needle in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise OSError("no route")


class SearchTests(Base):
    def answers(self) -> dict:
        return {
            "huggingface.co": (200, json.dumps([
                {"id": "org/eeg-motor", "tags": ["license:cc-by-4.0"]}])),
            "zenodo.org": (200, json.dumps({"hits": {"hits": [
                {"id": 11, "metadata": {"title": "EEG MI", "license": {"id": "cc-by-4.0"}},
                 "links": {"self_html": "https://zenodo.org/records/11"}}]}})),
            "openneuro.org": OSError("connection refused"),
            "/mcp": (200, "event: message\ndata: " + json.dumps({"jsonrpc": "2.0", "id": 1, "result": {
                "content": [{"type": "text", "text": json.dumps({"datasets": [
                    {"ref": "someone/eeg-set", "title": "EEG set", "licenseName": "CC0-1.0"}]})}]}}) + "\n"),
        }

    def test_hits_are_written_and_a_failing_host_is_recorded_not_fatal(self) -> None:
        http = FakeHttp(self.answers())
        result = self.run_cli("search", "--query", "motor imagery eeg", http=http)
        self.assertEqual(result.code, 0, result.err)
        today = datetime.date.today().isoformat()
        written = json.loads((self.root / "datasets" / f"search-{today}.json").read_text(encoding="utf-8"))
        self.assertEqual(written["query"], "motor imagery eeg")
        self.assertEqual(written["hosts"]["openneuro"]["status"], "failed")
        self.assertIn("connection refused", written["hosts"]["openneuro"]["error"])
        self.assertEqual(written["hosts"]["huggingface"]["status"], "ok")
        refs = {(hit["host"], hit["ref"]) for hit in written["hits"]}
        self.assertIn(("huggingface", "org/eeg-motor"), refs)
        self.assertIn(("zenodo", "11"), refs)
        self.assertEqual(len(refs), 3)
        for hit in written["hits"]:
            self.assertEqual(hit["retrieved"], today)
            self.assertTrue(hit["url"].startswith("https://"))
            self.assertIn("title", hit)
        hf = next(hit for hit in written["hits"] if hit["host"] == "huggingface")
        self.assertEqual(hf["license"], "cc-by-4.0")
        self.assertEqual(hf["url"], "https://huggingface.co/datasets/org/eeg-motor")
        self.assertIn("datasetsearch.research.google.com", result.out)
        self.assertIn("datasetsearch.research.google.com", json.dumps(written["manual"]))
        self.assertFalse(any("datasetsearch" in url for _m, url in http.calls),
                         "the manual link is printed, never queried")

    def test_every_host_failing_still_writes_the_file(self) -> None:
        http = FakeHttp({})
        result = self.run_cli("search", "--query", "eeg", http=http)
        self.assertEqual(result.code, 0, result.err)
        today = datetime.date.today().isoformat()
        written = json.loads((self.root / "datasets" / f"search-{today}.json").read_text(encoding="utf-8"))
        self.assertEqual(written["hits"], [])
        self.assertTrue(all(h["status"] == "failed" for h in written["hosts"].values()))
        self.assertGreaterEqual(len(written["hosts"]), 4)

    def test_hosts_can_be_restricted(self) -> None:
        http = FakeHttp(self.answers())
        result = self.run_cli("search", "--query", "eeg", "--hosts", "zenodo", http=http)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual([url for _m, url in http.calls if "zenodo" not in url], [])

    def test_an_unknown_host_is_refused(self) -> None:
        result = self.run_cli("search", "--query", "eeg", "--hosts", "nowhere", http=FakeHttp({}))
        self.assertEqual(result.code, 2)
        self.assertEqual(result.error["error"], "unknown-host")


# ------------------------------------------------------------------- license
class LicenseTests(Base):
    def test_cc_by_is_allowed_and_mapped(self) -> None:
        result = self.run_cli("license", "--slug", "bci-iv", "--source-license", "CC BY 4.0",
                              "--title", "BCI IV 2a", "--source-url", "https://example.org/bci")
        self.assertEqual(result.code, 0, result.err)
        entry = self.entry("bci-iv")
        self.assertEqual(entry["role"], "full")
        self.assertEqual(entry["license"]["decision"], "allowed")
        self.assertEqual(entry["license"]["host_license"], "CC-BY-4.0")
        self.assertEqual(entry["license"]["source_name"], "CC BY 4.0")
        self.assertEqual(entry["source"]["url"], "https://example.org/bci")

    def test_mapping_of_the_permissive_family(self) -> None:
        cases = {"CC0 1.0": "CC0-1.0", "cc-zero": "CC0-1.0", "Public Domain": "CC0-1.0", "CC-BY-SA-4.0": "CC-BY-SA-4.0",
                 "ODbL": "ODbL-1.0", "MIT": "other"}
        for index, (text, expected) in enumerate(cases.items()):
            with self.subTest(text=text):
                slug = f"set-{index}"
                self.assertEqual(self.run_cli("license", "--slug", slug, "--source-license", text).code, 0)
                self.assertEqual(self.entry(slug)["license"]["decision"], "allowed")
                self.assertEqual(self.entry(slug)["license"]["host_license"], expected)

    def test_restrictive_terms_are_refused(self) -> None:
        for index, text in enumerate(("CC BY-NC 4.0", "CC-BY-ND-4.0", "PhysioNet Credentialed Health Data License",
                                      "Data Use Agreement required", "", "some custom terms")):
            with self.subTest(text=text):
                slug = f"refused-{index}"
                result = self.run_cli("license", "--slug", slug, "--source-license", text)
                self.assertEqual(result.code, 0, result.err)
                self.assertEqual(result.json["decision"], "refused")
                self.assertEqual(self.entry(slug)["license"]["decision"], "refused")
                self.assertTrue(self.entry(slug)["license"]["reason"])

    def test_an_override_is_recorded_with_its_reason(self) -> None:
        result = self.run_cli("license", "--slug", "nc-set", "--source-license", "CC BY-NC-SA 4.0",
                              "--override", "operator holds written permission from the authors")
        self.assertEqual(result.code, 0, result.err)
        lic = self.entry("nc-set")["license"]
        self.assertEqual(lic["decision"], "overridden")
        self.assertEqual(lic["override"], "operator holds written permission from the authors")
        self.assertEqual(lic["host_license"], "CC-BY-NC-SA-4.0")


# ------------------------------------------------------------------------ qc
class QcTests(Base):
    def test_report_fields_and_status(self) -> None:
        rows = [{"subject": f"s{i // 4}", "label": str(i % 2), "x": str(i), "k": "1"} for i in range(16)]
        rows.append(dict(rows[0]))  # one duplicate
        rows[3]["x"] = ""  # one missing value
        path = self.write_csv("data/full.csv", rows)
        self.run_cli("license", "--slug", "full-set", "--source-license", "CC0")
        result = self.run_cli("qc", "--slug", "full-set", "--file", str(path), "--label", "label", "--group", "subject")
        self.assertEqual(result.code, 0, result.err)
        report = json.loads((self.root / "datasets/full-set/qc.json").read_text(encoding="utf-8"))
        self.assertEqual(report["rows"], 17)
        self.assertEqual(report["columns"], 4)
        self.assertEqual(report["missing"]["x"], 1)
        self.assertIn("k", report["constant_columns"])
        self.assertEqual(report["duplicates"], 1)
        self.assertEqual(report["class_balance"], {"0": 9, "1": 8})
        self.assertEqual(report["groups"]["count"], 4)
        self.assertEqual(report["groups"]["single_class_groups"], 0)
        self.assertEqual(report["ranges"]["x"]["min"], 0.0)
        self.assertEqual(report["status"], "warn")
        self.assertTrue(report["reasons"])
        entry = self.entry("full-set")
        self.assertEqual(entry["qc"], {"status": "warn", "report": "datasets/full-set/qc.json"})
        self.assertIn("data/full.csv", entry["files"])

    def test_clean_data_passes(self) -> None:
        rows = [{"subject": f"s{i // 4}", "label": str(i % 2), "x": str(i * 1.5)} for i in range(16)]
        path = self.write_csv("clean.csv", rows)
        self.run_cli("license", "--slug", "clean", "--source-license", "CC0")
        result = self.run_cli("qc", "--slug", "clean", "--file", str(path), "--label", "label", "--group", "subject")
        self.assertEqual(result.json["status"], "pass", result.out)

    def test_a_missing_label_column_fails(self) -> None:
        path = self.write_csv("x.csv", [{"a": "1"}, {"a": "2"}])
        self.run_cli("license", "--slug", "xset", "--source-license", "CC0")
        result = self.run_cli("qc", "--slug", "xset", "--file", str(path), "--label", "label")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(result.json["status"], "fail")

    def test_qc_needs_a_registered_slug(self) -> None:
        path = self.write_csv("x.csv", [{"a": "1"}])
        result = self.run_cli("qc", "--slug", "ghost", "--file", str(path))
        self.assertEqual(result.code, 2)
        self.assertEqual(result.error["error"], "unknown-slug")

    def test_a_file_outside_the_workspace_is_refused(self) -> None:
        self.run_cli("license", "--slug", "xset", "--source-license", "CC0")
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write("a\n1\n")
        self.addCleanup(os.unlink, handle.name)
        result = self.run_cli("qc", "--slug", "xset", "--file", handle.name)
        self.assertEqual(result.code, 2)
        self.assertEqual(result.error["error"], "file-outside-workspace")


# ------------------------------------------------------------------- prepare
class LicenseWordingTests(Base):
    def test_the_spelled_out_attribution_license_is_recognised(self) -> None:
        result = self.run_cli("license", "--slug", "spelled", "--source-license",
                              "Creative Commons Attribution 4.0 International")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(self.entry("spelled")["license"]["host_license"], "CC-BY-4.0")


class UnevenSubjectsTests(Base):
    def test_folds_stay_balanced_when_subjects_differ_in_size(self) -> None:
        rows = []
        for subject in range(12):
            size = 5 + 4 * subject          # 5 .. 49 rows per subject
            label = subject % 2
            rows += [{"subject": f"s{subject}", "label": str(label), "x": str(i)} for i in range(size)]
        self.write_csv("uneven.csv", rows)
        self.run_cli("synth", "--slug", "uneven", "--kind", "classification", "--seed", "1")
        result = self.run_cli("prepare", "--slug", "uneven", "--file", "uneven.csv", "--label", "label",
                              "--group", "subject", "--folds", "4", "--seed", "3")
        self.assertEqual(result.code, 0, result.err)
        splits = json.loads((self.root / "datasets" / "uneven" / "splits.json").read_text())
        sizes = [fold["n_rows"] for fold in splits["folds_summary"]]
        self.assertTrue(all(size > 0 for size in sizes), sizes)
        self.assertLess(max(sizes) / min(sizes), 1.6, sizes)


class PrepareTests(Base):
    def make(self) -> Path:
        rows = []
        for subject in range(12):
            positives = 2 + subject % 5  # subjects differ in their class mix
            for trial in range(8):
                rows.append({"subject": f"sub{subject:02d}", "trial": str(trial),
                             "label": "1" if trial < positives else "0", "x": str(trial)})
        self.run_cli("license", "--slug", "prep", "--source-license", "CC0")
        return self.write_csv("prep.csv", rows)

    def test_no_group_lands_in_two_folds_and_every_fold_holds_every_class(self) -> None:
        path = self.make()
        result = self.run_cli("prepare", "--slug", "prep", "--file", str(path), "--label", "label",
                              "--group", "subject", "--folds", "4", "--seed", "0")
        self.assertEqual(result.code, 0, result.err)
        splits = json.loads((self.root / "datasets/prep/splits.json").read_text(encoding="utf-8"))
        assignment = splits["assignment"]
        self.assertEqual(len(assignment), 12)
        self.assertEqual(set(assignment.values()), {0, 1, 2, 3})
        self.assertTrue(all(isinstance(v, int) for v in assignment.values()))
        total = {"0": 0, "1": 0}
        for fold in splits["folds_summary"]:
            self.assertEqual(set(fold["class_counts"]), {"0", "1"})
            self.assertEqual(fold["n_groups"], 3)
            for key, value in fold["class_counts"].items():
                total[key] += value
        overall = total["1"] / (total["0"] + total["1"])
        for fold in splits["folds_summary"]:
            share = fold["class_counts"]["1"] / fold["n_rows"]
            self.assertLess(abs(share - overall), 0.2, "stratification drifted")

    def test_it_is_deterministic_and_the_manifest_carries_the_source_sha256(self) -> None:
        path = self.make()
        argv = ["prepare", "--slug", "prep", "--file", str(path), "--label", "label", "--group", "subject",
                "--folds", "3", "--seed", "11"]
        self.run_cli(*argv)
        first = json.loads((self.root / "datasets/prep/splits.json").read_text(encoding="utf-8"))
        self.run_cli(*argv)
        second = json.loads((self.root / "datasets/prep/splits.json").read_text(encoding="utf-8"))
        self.assertEqual(first["assignment"], second["assignment"])
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(first["sha256"], digest)
        manifest = (self.root / "datasets/prep/PREPARATION.md").read_text(encoding="utf-8")
        self.assertIn(digest, manifest)
        for needle in ("folds", "seed", "subject", "label", "splits.json"):
            self.assertIn(needle, manifest)
        prep = self.entry("prep")["preparation"]
        self.assertEqual(prep["manifest"], "datasets/prep/PREPARATION.md")
        self.assertEqual(prep["version"], 2, "each preparation run is a new version")

    def test_too_few_groups_is_refused(self) -> None:
        rows = [{"subject": "a", "label": "0"}, {"subject": "b", "label": "1"}]
        path = self.write_csv("tiny.csv", rows)
        self.run_cli("license", "--slug", "tiny", "--source-license", "CC0")
        result = self.run_cli("prepare", "--slug", "tiny", "--file", str(path), "--label", "label",
                              "--group", "subject", "--folds", "5")
        self.assertEqual(result.code, 2)
        self.assertEqual(result.error["error"], "too-few-groups")


# ------------------------------------------------------------------- publish
class FakeRunner:
    def __init__(self, codes: dict | None = None) -> None:
        self.codes = codes or {}
        self.calls: list[list[str]] = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        code = self.codes.get(argv[2], 0) if len(argv) > 2 else 0
        return code, "ok", ""


class PublishTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.run_cli("synth", "--slug", "toy-eeg", "--kind", "eeg", "--seed", "1")
        os.environ["KAGGLE_API_TOKEN"] = TOKEN_SENTINEL
        self.addCleanup(os.environ.pop, "KAGGLE_API_TOKEN", None)

    def publish(self, *extra, runner=None):
        runner = runner or FakeRunner({"status": 1})
        return self.run_cli("publish", "--slug", "toy-eeg", "--owner", "someone", *extra, runner=runner), runner

    def test_without_consent_it_only_prints_the_plan(self) -> None:
        result, runner = self.publish()
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(runner.calls, [], "a dry run never invokes the host's client")
        self.assertTrue(result.json["dry_run"])
        self.assertIn("-p", result.json["plan"])
        self.assertIsNone(self.entry("toy-eeg")["remote"])

    def test_consent_must_match_the_slug_exactly(self) -> None:
        result, runner = self.publish("--consent", "toy")
        self.assertTrue(result.json["dry_run"])
        self.assertEqual(runner.calls, [])

    def test_refused_without_an_allowed_license(self) -> None:
        self.run_cli("license", "--slug", "nc", "--source-license", "CC BY-NC 4.0")
        result = self.run_cli("publish", "--slug", "nc", "--owner", "someone", "--consent", "nc", runner=FakeRunner())
        self.assertEqual(result.code, 2)
        self.assertEqual(result.error["error"], "license-not-allowed")

    def test_a_symlinked_sidecar_never_reaches_the_upload_folder(self) -> None:
        secret = self.root.parent / f"{self.root.name}-outside-secret"
        secret.write_text(TOKEN_SENTINEL, encoding="utf-8")
        self.addCleanup(secret.unlink)
        sidecar = self.root / "datasets" / "toy-eeg" / "qc.json"
        if sidecar.exists():
            sidecar.unlink()
        sidecar.symlink_to(secret)
        result, runner = self.publish("--consent", "toy-eeg")
        self.assertEqual(result.code, 2)
        self.assertEqual(result.error["error"], "file-outside-workspace")
        self.assertEqual(runner.calls, [])
        remote = self.root / "datasets" / "toy-eeg" / "remote"
        if remote.exists():
            for path in remote.rglob("*"):
                if path.is_file():
                    self.assertNotIn(TOKEN_SENTINEL, path.read_text(encoding="utf-8", errors="replace"))

    def test_a_registry_path_leaving_the_workspace_is_refused(self) -> None:
        registry = self.registry()
        registry[0]["files"] = ["../outside.csv"]
        (self.root / "datasets" / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
        result, runner = self.publish("--consent", "toy-eeg")
        self.assertEqual(result.code, 2)
        self.assertEqual(result.error["error"], "file-outside-workspace")
        self.assertEqual(runner.calls, [])

    def test_a_registered_data_file_that_is_a_symlink_is_refused(self) -> None:
        data = self.root / "datasets" / "toy-eeg" / "toy-eeg.csv"
        outside = self.root.parent / f"{self.root.name}-hosts"
        outside.write_text("x", encoding="utf-8")
        self.addCleanup(outside.unlink)
        data.unlink()
        data.symlink_to(outside)
        result, _ = self.publish("--consent", "toy-eeg")
        self.assertEqual(result.error["error"], "file-outside-workspace")

    def test_private_create_command_line_is_exact(self) -> None:
        result, runner = self.publish("--consent", "toy-eeg")
        self.assertEqual(result.code, 0, result.err)
        remote_dir = str(self.root / "datasets" / "toy-eeg" / "remote")
        creates = [call for call in runner.calls if call[2] == "create"]
        self.assertEqual(creates, [["kaggle", "datasets", "create", "-p", remote_dir]])
        self.assertNotIn("-u", sum(runner.calls, []))
        remote = self.entry("toy-eeg")["remote"]
        self.assertEqual(remote, {"ref": "someone/toy-eeg", "visibility": "private", "version": 1})
        self.assertIn("/kaggle/input/", result.out)
        self.assertIn("os.walk", result.out)

    def test_metadata_is_valid_and_the_files_are_copied(self) -> None:
        self.publish("--consent", "toy-eeg")
        remote = self.root / "datasets" / "toy-eeg" / "remote"
        meta = json.loads((remote / "dataset-metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["id"], "someone/toy-eeg")
        self.assertTrue(6 <= len(meta["title"]) <= 50, meta["title"])
        self.assertTrue(20 <= len(meta["subtitle"]) <= 80, meta["subtitle"])
        self.assertEqual(meta["licenses"], [{"name": "CC0-1.0"}])
        self.assertTrue(meta["keywords"])
        paths = [item["path"] for item in meta["resources"]]
        self.assertIn("toy-eeg.csv", paths)
        for name in paths:
            self.assertTrue((remote / name).is_file(), name)

    def test_existing_dataset_gets_a_new_version_with_notes(self) -> None:
        self.publish("--consent", "toy-eeg")
        result, runner = self.publish("--consent", "toy-eeg", "--version-notes", "second preparation",
                                      runner=FakeRunner())
        self.assertEqual(result.code, 0, result.err)
        remote_dir = str(self.root / "datasets" / "toy-eeg" / "remote")
        self.assertEqual(runner.calls, [["kaggle", "datasets", "version", "-p", remote_dir,
                                         "-m", "second preparation"]])
        self.assertEqual(self.entry("toy-eeg")["remote"]["version"], 2)

    def test_a_dataset_already_on_the_host_is_versioned_not_created(self) -> None:
        result, runner = self.publish("--consent", "toy-eeg", runner=FakeRunner({"status": 0}))
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual([call[2] for call in runner.calls], ["status", "version"])

    def test_public_needs_both_flags(self) -> None:
        refused, runner = self.publish("--consent", "toy-eeg", "--public")
        self.assertEqual(refused.code, 2)
        self.assertEqual(refused.error["error"], "public-consent-missing")
        self.assertEqual(runner.calls, [])
        wrong, runner = self.publish("--consent", "toy-eeg", "--public", "--consent-public", "toy")
        self.assertEqual(wrong.code, 2)
        self.assertEqual(runner.calls, [])
        only_token, runner = self.publish("--consent", "toy-eeg", "--consent-public", "toy-eeg")
        self.assertEqual(only_token.code, 0, only_token.err)
        self.assertNotIn("-u", sum(runner.calls, []))
        existing, runner = self.publish("--consent", "toy-eeg", "--public", "--consent-public", "toy-eeg")
        self.assertEqual(existing.code, 2)
        self.assertEqual(existing.error["error"], "public-on-existing")
        self.assertEqual(runner.calls, [])

    def test_public_create_appends_u(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        self.run_cli("synth", "--slug", "toy-eeg", "--kind", "eeg", "--seed", "1")
        result, runner = self.publish("--consent", "toy-eeg", "--public", "--consent-public", "toy-eeg")
        self.assertEqual(result.code, 0, result.err)
        create = [call for call in runner.calls if call[2] == "create"][0]
        self.assertEqual(create[-1], "-u")
        self.assertEqual(self.entry("toy-eeg")["remote"]["visibility"], "public")

    def test_the_token_is_never_printed_nor_passed(self) -> None:
        dry, _ = self.publish()
        real, runner = self.publish("--consent", "toy-eeg")
        for result in (dry, real):
            self.assertNotIn(TOKEN_SENTINEL, result.out + result.err)
        self.assertNotIn(TOKEN_SENTINEL, json.dumps(runner.calls))
        registry = (self.root / "datasets" / "registry.json").read_text(encoding="utf-8")
        self.assertNotIn(TOKEN_SENTINEL, registry)

    def test_a_failing_client_records_nothing(self) -> None:
        result, _ = self.publish("--consent", "toy-eeg", runner=FakeRunner({"status": 1, "create": 1}))
        self.assertEqual(result.code, 2)
        self.assertEqual(result.error["error"], "host-cli-failed")
        self.assertIsNone(self.entry("toy-eeg").get("remote"))

    def test_a_bad_owner_is_refused(self) -> None:
        result = self.run_cli("publish", "--slug", "toy-eeg", "--owner", "a b", runner=FakeRunner())
        self.assertEqual(result.code, 2)
        self.assertEqual(result.error["error"], "bad-owner")


# ------------------------------------------------------- registry and status
class RegistryTests(Base):
    def test_round_trip_and_status_summary(self) -> None:
        self.run_cli("synth", "--slug", "toy-eeg", "--kind", "eeg", "--seed", "1")
        self.run_cli("license", "--slug", "full-eeg", "--source-license", "CC-BY-4.0", "--title", "Full EEG")
        loaded = CLI.load_registry(self.root)
        CLI.save_registry(self.root, loaded)
        self.assertEqual(CLI.load_registry(self.root), loaded)
        keys = {"slug", "role", "title", "source", "license", "files", "qc", "preparation", "remote"}
        for item in loaded:
            self.assertEqual(set(item), keys)
        status = self.run_cli("status")
        self.assertEqual(status.code, 0, status.err)
        slugs = [item["slug"] for item in status.json["datasets"]]
        self.assertEqual(slugs, ["full-eeg", "toy-eeg"])

    def test_status_on_an_empty_workspace(self) -> None:
        status = self.run_cli("status")
        self.assertEqual(status.code, 0)
        self.assertEqual(status.json["datasets"], [])

    def test_an_unknown_verb_names_the_roster(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                CLI.run(["--root", str(self.root), "nope"])
        for verb in ("synth", "search", "license", "qc", "prepare", "publish", "status"):
            self.assertIn(verb, err.getvalue())


# --------------------------------------------------------------- doctrine
class DoctrineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.flat = " ".join(self.doc.split())

    def test_frontmatter_names_the_skill(self) -> None:
        self.assertTrue(self.doc.startswith("---\nname: datasets\n"))
        self.assertRegex(self.doc.split("---", 2)[1], r"description: \".+\"")

    def test_the_objective_flow_is_declared_in_both_places_in_order(self) -> None:
        stages = [stage["stage"] for stage in CLI.OBJECTIVE_FLOW["stages"]]
        self.assertEqual(stages, ["toy", "sourced", "licensed", "checked", "prepared", "published"])
        positions = [self.doc.find(f"`{stage}`") for stage in stages]
        self.assertTrue(all(p >= 0 for p in positions), positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn(CLI.OBJECTIVE_FLOW["arrival"], self.flat)

    def test_every_verb_and_error_code_is_documented(self) -> None:
        for verb in CLI.VERBS:
            self.assertIn(f"| `{verb}` |", self.doc)
        for code in CLI.ERROR_CODES:
            self.assertIn(f"`{code}`", self.doc, code)

    def test_the_error_codes_are_the_ones_the_code_raises(self) -> None:
        source = "".join(path.read_text(encoding="utf-8") for path in (SKILL / "scripts").rglob("*.py"))
        raised = set(re.findall(r'Refusal\(\s*"([a-z-]+)"', source))
        self.assertEqual(raised, set(CLI.ERROR_CODES))

    def test_delegation_gates_and_harness_note(self) -> None:
        self.assertIn("delegates to the `dataset-scout` agent", self.flat)
        self.assertIn("delegates to the `dataset-curator` agent", self.flat)
        self.assertIn("Measure this before delegating", self.flat)
        for harness in ("Claude Code", "OpenCode", "Pi"):
            self.assertIn(harness, self.flat)
        self.assertIn("personal data", self.flat)
        for gate in ("--override", "--consent", "--consent-public"):
            self.assertIn(gate, self.flat)

    def test_the_cli_is_stdlib_only(self) -> None:
        allowed = set(sys.stdlib_module_names) | {"hosts", "capacity_toy", "__future__"}
        for path in (SKILL / "scripts").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for name in re.findall(r"^\s*(?:from|import)\s+([A-Za-z_][\w]*)", text, re.MULTILINE):
                self.assertIn(name, allowed, f"{path.name} imports {name}")


class AgentTests(unittest.TestCase):
    AGENTS = ROOT / ".claude" / "agents"

    def test_both_agents_bind_the_skill_and_their_tools(self) -> None:
        expected = {
            "dataset-scout": "Read, Glob, Grep, WebSearch, WebFetch, Bash",
            "dataset-curator": "Read, Write, Edit, Bash, Glob, Grep",
        }
        for name, tools in expected.items():
            with self.subTest(agent=name):
                text = (self.AGENTS / f"{name}.md").read_text(encoding="utf-8")
                header = text.split("---", 2)[1]
                self.assertIn(f"name: {name}\n", header)
                self.assertIn(f"tools: {tools}\n", header)
                self.assertNotIn("model:", header, "agents inherit the session's model")
                self.assertIn("skills/datasets/SKILL.md", text)

    def test_the_curator_never_publishes_without_consent(self) -> None:
        text = " ".join((self.AGENTS / "dataset-curator.md").read_text(encoding="utf-8").split())
        self.assertIn("--consent", text)
        self.assertIn("--consent-public", text)
        scout = " ".join((self.AGENTS / "dataset-scout.md").read_text(encoding="utf-8").split())
        self.assertIn("never upload", scout.lower())


if __name__ == "__main__":
    unittest.main()


class ThetaBetaProfileTests(Base):
    """`--profile theta-beta`: class-dependent Theta (6 Hz) and Beta (20 Hz) power."""

    @staticmethod
    def band_power(samples: list[float], freq: float, sfreq: float) -> float:
        re_part = sum(x * math.cos(2 * math.pi * freq * i / sfreq) for i, x in enumerate(samples))
        im_part = sum(x * math.sin(2 * math.pi * freq * i / sfreq) for i, x in enumerate(samples))
        return (re_part ** 2 + im_part ** 2) / len(samples)

    def test_class_one_carries_a_higher_theta_beta_ratio(self) -> None:
        result = self.run_cli("synth", "--slug", "tb", "--kind", "eeg", "--profile", "theta-beta", "--seed", "3",
                              "--n-subjects", "4", "--n-per-subject", "6", "--channels", "2", "--length", "256",
                              "--sfreq", "128")
        self.assertEqual(result.code, 0, result.err)
        rows = list(csv.reader((self.root / "datasets" / "tb" / "tb.csv").open(encoding="utf-8")))[1:]
        ratios = {"0": [], "1": []}
        for row in rows:
            channel0 = [float(v) for v in row[3:3 + 256]]
            ratios[row[2]].append(self.band_power(channel0, 6, 128) / self.band_power(channel0, 20, 128))
        mean = {k: sum(v) / len(v) for k, v in ratios.items()}
        self.assertGreater(mean["1"], 2 * mean["0"], mean)
        toy = (self.root / "datasets" / "tb" / "TOY.md").read_text(encoding="utf-8")
        self.assertIn("| profile | theta-beta |", toy)

    def test_the_default_profile_is_unchanged(self) -> None:
        args = ["synth", "--slug", "a", "--kind", "eeg", "--seed", "9", "--n-subjects", "2", "--n-per-subject", "2",
                "--channels", "1", "--length", "16"]
        self.run_cli(*args)
        default = (self.root / "datasets" / "a" / "a.csv").read_bytes()
        self.run_cli(*args, "--profile", "alpha", "--force")
        self.assertEqual((self.root / "datasets" / "a" / "a.csv").read_bytes(), default)

    def test_beta_above_nyquist_is_refused(self) -> None:
        result = self.run_cli("synth", "--slug", "low", "--kind", "eeg", "--profile", "theta-beta", "--sfreq", "32")
        self.assertEqual(result.code, 2)
        self.assertEqual(result.error["error"], "bad-argument")


class LabelPerSubjectTests(Base):
    """`--label-per subject`: one diagnosis per subject, for subject-level protocols."""

    def test_every_subject_carries_one_label_and_classes_are_balanced(self) -> None:
        result = self.run_cli("synth", "--slug", "subj", "--kind", "eeg", "--profile", "theta-beta",
                              "--label-per", "subject", "--seed", "3", "--n-subjects", "6",
                              "--n-per-subject", "4", "--channels", "2", "--length", "64", "--sfreq", "128")
        self.assertEqual(result.code, 0, result.err)
        rows = list(csv.reader((self.root / "datasets" / "subj" / "subj.csv").open(encoding="utf-8")))[1:]
        labels: dict[str, set] = {}
        for row in rows:
            labels.setdefault(row[0], set()).add(row[2])
        self.assertTrue(all(len(v) == 1 for v in labels.values()), labels)
        per_class = [sum(1 for v in labels.values() if v == {c}) for c in ("0", "1")]
        self.assertEqual(per_class, [3, 3])
        toy = (self.root / "datasets" / "subj" / "TOY.md").read_text(encoding="utf-8")
        self.assertIn("| label_per | subject |", toy)

    def test_the_default_still_alternates_within_a_subject(self) -> None:
        args = ["synth", "--slug", "d", "--kind", "eeg", "--seed", "9", "--n-subjects", "2",
                "--n-per-subject", "2", "--channels", "1", "--length", "16"]
        self.run_cli(*args)
        default = (self.root / "datasets" / "d" / "d.csv").read_bytes()
        self.run_cli(*args, "--label-per", "trial", "--force")
        self.assertEqual((self.root / "datasets" / "d" / "d.csv").read_bytes(), default)
