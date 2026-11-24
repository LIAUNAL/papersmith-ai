"""The `deposit` record of the `datasets` skill (T8-D1, G-DEPOSIT): the
operator deposits a dataset in a repository and the CLI records where, under
which persistent identifier and licence, bound to the sha256 of every
registered file. The CLI never uploads anything.

Driven through `datasets_cli.run(argv)`, the entry point `main()` uses, and
asserted on the exit code, the refusal code and the persisted JSON.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "datasets"
CLI_PATH = SKILL / "scripts" / "datasets_cli.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("datasets_cli_deposit", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLI = load_cli()
DOI = "10.5281/zenodo.1234567"


class Run:
    def __init__(self, root: Path, argv: list[str], runner=None, http=None) -> None:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.code = CLI.run(["--root", str(root), *argv], runner=runner, http=http)
        self.out, self.err = out.getvalue(), err.getvalue()
        self.json = json.loads(self.out) if self.out.strip().startswith("{") else None
        self.error = json.loads(self.err) if self.err.strip().startswith("{") else None


class Forbidden:
    """A runner or http client that fails the test when called: deposit never uploads."""

    def __init__(self) -> None:
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        raise AssertionError("deposit must never call a host")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()

    def cli(self, *argv: str, runner=None, http=None) -> Run:
        return Run(self.root, list(argv), runner=runner, http=http)

    def registry_text(self) -> str:
        return (self.root / "datasets" / "registry.json").read_text(encoding="utf-8")

    def entry(self, slug: str) -> dict:
        return next(item for item in json.loads(self.registry_text()) if item["slug"] == slug)

    def write_csv(self, name: str, header: list[str], rows: list[list[str]]) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
        return path

    def own_with_file(self, slug: str = "cohort", header=("age", "score")) -> Path:
        result = self.cli("own", "--slug", slug, "--by", "Dr. Operator",
                          "--statement", "Collected under protocol 12/2026; open after deposit.")
        self.assertEqual(result.code, 0, result.err)
        data = self.write_csv(f"data/{slug}.csv", list(header), [[str(30 + i), str(i)] for i in range(8)])
        self.assertEqual(self.cli("qc", "--slug", slug, "--file", f"data/{slug}.csv").code, 0)
        return data

    def deposit(self, *extra: str, slug: str = "cohort", identifier: str = DOI, by: str = "Dr. Operator",
                license_: str = "CC-BY-4.0", repository: str = "Zenodo", runner=None, http=None) -> Run:
        return self.cli("deposit", "--slug", slug, "--repository", repository, "--identifier", identifier,
                        "--license", license_, "--by", by, *extra, runner=runner, http=http)

    def status_item(self, slug: str = "cohort") -> dict:
        status = self.cli("status")
        self.assertEqual(status.code, 0, status.err)
        return next(item for item in status.json["datasets"] if item["slug"] == slug)

    def assertRefused(self, result: Run, code: str) -> None:
        self.assertEqual(result.code, 2, result.out)
        self.assertEqual(result.error["error"], code, result.err)
        self.assertIn("objective", result.error)

    def sha(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


# -------------------------------------------------------------------- record
class RecordTests(Base):
    def test_deposit_records_the_operator_record_bound_to_the_registered_files(self) -> None:
        data = self.own_with_file()
        runner, http = Forbidden(), Forbidden()
        result = self.deposit("--url", "https://zenodo.org/records/1234567", "--version", "v1.0",
                              "--date", "2026-11-20", runner=runner, http=http)
        self.assertEqual(result.code, 0, result.err)
        record = self.entry("cohort")["deposit"]
        self.assertEqual({k: record[k] for k in ("repository", "identifier", "scheme", "license", "url",
                                                 "version", "date", "by")},
                         {"repository": "Zenodo", "identifier": DOI, "scheme": "doi", "license": "CC-BY-4.0",
                          "url": "https://zenodo.org/records/1234567", "version": "v1.0",
                          "date": "2026-11-20", "by": "Dr. Operator"})
        self.assertEqual(record["recorded"], datetime.date.today().isoformat())
        self.assertEqual(record["files"], {"data/cohort.csv": self.sha(data)})
        self.assertNotIn("history", record)
        self.assertEqual(result.json["deposit"], record)
        self.assertTrue(result.json["current"])
        self.assertEqual(runner.calls, [])
        self.assertEqual(http.calls, [])
        self.assertFalse((self.root / "datasets" / "cohort" / "remote").exists())
        self.assertIsNone(self.entry("cohort")["remote"])

    def test_optional_fields_default_and_a_doi_link_is_normalized(self) -> None:
        self.own_with_file()
        result = self.deposit(identifier="https://doi.org/10.5281/ZENODO.42")
        self.assertEqual(result.code, 0, result.err)
        record = self.entry("cohort")["deposit"]
        self.assertEqual(record["identifier"], "10.5281/ZENODO.42")
        self.assertEqual(record["url"], "")
        self.assertEqual(record["version"], "")
        self.assertEqual(record["date"], datetime.date.today().isoformat())
        self.assertEqual(self.deposit(identifier="doi:10.1000/xyz.9").code, 0)
        self.assertEqual(self.entry("cohort")["deposit"]["identifier"], "10.1000/xyz.9")

    def test_a_new_deposit_keeps_the_previous_one_in_its_history(self) -> None:
        self.own_with_file()
        self.assertEqual(self.deposit("--version", "v1").code, 0)
        first = self.entry("cohort")["deposit"]
        self.assertEqual(self.deposit("--version", "v2", identifier="10.5281/zenodo.7654321").code, 0)
        record = self.entry("cohort")["deposit"]
        self.assertEqual(record["identifier"], "10.5281/zenodo.7654321")
        self.assertEqual(record["history"], [{k: v for k, v in first.items() if k != "history"}])

    def test_other_persistent_identifier_schemes_are_declared(self) -> None:
        self.own_with_file()
        for scheme, identifier in (("handle", "20.500.12345/abc-1"), ("ark", "ark:/12148/btv1b8449691v"),
                                   ("accession", "GSE123456")):
            result = self.deposit("--scheme", scheme, identifier=identifier)
            self.assertEqual(result.code, 0, result.err)
            record = self.entry("cohort")["deposit"]
            self.assertEqual((record["scheme"], record["identifier"]), (scheme, identifier))

    def test_the_operator_is_required(self) -> None:
        self.own_with_file()
        before = self.registry_text()
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            CLI.run(["--root", str(self.root), "deposit", "--slug", "cohort", "--repository", "Zenodo",
                     "--identifier", DOI, "--license", "CC-BY-4.0"])
        self.assertEqual(raised.exception.code, 2)
        self.assertRefused(self.deposit(by="  "), "operator-missing")
        self.assertEqual(self.registry_text(), before)


# ---------------------------------------------------------------- refusals
class ValidationTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.own_with_file()
        self.before = self.registry_text()

    def test_a_malformed_identifier_is_refused(self) -> None:
        for scheme, identifier in (("doi", "zenodo.1234567"), ("doi", "10.5281"), ("doi", "11.5281/x"),
                                   ("doi", "10.12/short-registrant"), ("handle", "no-slash"),
                                   ("ark", "12148/btv1b8449691v"), ("accession", "has space"),
                                   ("doi", "  ")):
            result = self.deposit("--scheme", scheme, identifier=identifier)
            self.assertRefused(result, "bad-identifier")
        self.assertEqual(self.registry_text(), self.before)

    def test_malformed_repository_url_and_date_are_refused(self) -> None:
        for result in (self.deposit(repository=" "), self.deposit("--url", "zenodo.org/records/1"),
                       self.deposit("--date", "20-11-2026"), self.deposit("--date", "2026-02-30")):
            self.assertRefused(result, "bad-argument")
        self.assertEqual(self.registry_text(), self.before)

    def test_a_deposit_without_a_stated_license_is_refused(self) -> None:
        for text in (" ", "unknown", "None"):
            self.assertRefused(self.deposit(license_=text), "deposit-license-missing")
        self.assertEqual(self.registry_text(), self.before)

    def test_an_unknown_slug_or_one_without_files_is_refused(self) -> None:
        self.assertRefused(self.deposit(slug="nowhere"), "unknown-slug")
        self.assertEqual(self.cli("own", "--slug", "empty", "--by", "Op", "--statement", "mine").code, 0)
        before = self.registry_text()
        self.assertRefused(self.deposit(slug="empty"), "file-missing")
        self.assertEqual(self.registry_text(), before)

    def test_a_registered_file_missing_on_disk_is_refused(self) -> None:
        (self.root / "data" / "cohort.csv").unlink()
        self.assertRefused(self.deposit(), "file-missing")
        self.assertEqual(self.registry_text(), self.before)


class LicenseAndPiiTests(Base):
    def external(self, slug: str, *license_args: str) -> None:
        self.assertEqual(self.cli("license", "--slug", slug, *license_args).code, 0)
        self.write_csv(f"data/{slug}.csv", ["age"], [[str(i)] for i in range(5)])
        self.assertEqual(self.cli("qc", "--slug", slug, "--file", f"data/{slug}.csv").code, 0)

    def test_a_source_license_that_is_not_allowed_is_refused(self) -> None:
        self.external("refused-set", "--source-license", "CC-BY-NC-ND-4.0")
        self.external("overridden-set", "--source-license", "CC-BY-NC-4.0", "--override", "use in the lab only")
        for slug in ("refused-set", "overridden-set"):
            before = self.registry_text()
            result = self.deposit(slug=slug)
            self.assertRefused(result, "license-not-allowed")
            self.assertIn(slug, result.error["message"])
            self.assertEqual(self.registry_text(), before)

    def test_an_allowed_external_source_can_be_recorded(self) -> None:
        self.external("open-set", "--source-license", "CC-BY-4.0")
        self.assertEqual(self.deposit(slug="open-set").code, 0)

    def test_pii_without_a_current_deidentification_is_refused(self) -> None:
        data = self.own_with_file(header=("patient_email", "age"))
        self.assertEqual(self.cli("dictionary", "init", "--slug", "cohort", "--file", "data/cohort.csv").code, 0)
        result = self.deposit()
        self.assertRefused(result, "pii-not-deidentified")
        self.assertIn("patient_email", result.error["message"])
        self.assertIn("deidentify --slug cohort", result.error["message"])
        self.assertNotIn("deposit", self.entry("cohort"))
        self.assertEqual(self.entry("cohort")["pii_columns_seen"], ["patient_email"])
        self.assertEqual(self.cli("deidentify", "--slug", "cohort", "--by", "Dr. Operator",
                                  "--statement", "Emails replaced by study ids.").code, 0)
        self.assertEqual(self.deposit().code, 0)
        with data.open("a", encoding="utf-8") as handle:
            handle.write("p99@example.org,99\n")
        self.assertRefused(self.deposit(), "pii-not-deidentified")

    def test_an_unreadable_dictionary_without_pii_history_fails_closed(self) -> None:
        self.own_with_file()
        (self.root / "datasets" / "cohort" / "dictionary.json").write_text("{not json", encoding="utf-8")
        self.assertRefused(self.deposit(), "dictionary-unreadable")
        self.assertNotIn("deposit", self.entry("cohort"))


# ---------------------------------------------------------------- staleness
class StalenessTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.data = self.own_with_file()
        self.assertEqual(self.deposit("--url", "https://zenodo.org/records/1234567").code, 0)

    def test_status_reports_a_current_deposit(self) -> None:
        item = self.status_item()
        self.assertEqual(item["deposit"], {"repository": "Zenodo", "identifier": DOI, "scheme": "doi",
                                           "license": "CC-BY-4.0", "url": "https://zenodo.org/records/1234567",
                                           "version": "", "date": datetime.date.today().isoformat(), "by": "Dr. Operator",
                                           "current": True, "stale": []})

    def test_a_changed_file_makes_the_deposit_stale(self) -> None:
        with self.data.open("a", encoding="utf-8") as handle:
            handle.write("99,99\n")
        item = self.status_item()
        self.assertFalse(item["deposit"]["current"])
        self.assertEqual(item["deposit"]["stale"], [{"reason": "file-changed", "file": "data/cohort.csv"}])
        self.assertEqual(self.deposit("--version", "v2").code, 0)
        self.assertTrue(self.status_item()["deposit"]["current"])

    def test_an_added_file_makes_the_deposit_stale(self) -> None:
        self.write_csv("data/cohort-wave2.csv", ["age", "score"], [["40", "1"], ["41", "2"]])
        self.assertEqual(self.cli("qc", "--slug", "cohort", "--file", "data/cohort-wave2.csv").code, 0)
        item = self.status_item()
        self.assertFalse(item["deposit"]["current"])
        self.assertEqual(item["deposit"]["stale"], [{"reason": "file-added", "file": "data/cohort-wave2.csv"}])

    def test_a_missing_or_unregistered_file_makes_the_deposit_stale(self) -> None:
        self.data.unlink()
        item = self.status_item()
        self.assertEqual(item["deposit"]["stale"], [{"reason": "file-missing", "file": "data/cohort.csv"}])
        registry = json.loads(self.registry_text())
        for entry in registry:
            if entry["slug"] == "cohort":
                entry["files"] = []
        (self.root / "datasets" / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
        self.write_csv("data/cohort.csv", ["age", "score"], [["1", "2"]])
        item = self.status_item()
        self.assertFalse(item["deposit"]["current"])
        self.assertEqual(item["deposit"]["stale"], [{"reason": "file-missing", "file": "data/cohort.csv"}])


# ------------------------------------------------------------------- reader
class ReaderTests(Base):
    def test_deposit_state_reads_without_writing(self) -> None:
        self.assertEqual(CLI.deposit_state(self.root, "anything"),
                         {"recorded": False, "current": False, "stale": [], "deposit": None})
        data = self.own_with_file()
        self.assertEqual(CLI.deposit_state(self.root, "cohort"),
                         {"recorded": False, "current": False, "stale": [], "deposit": None})
        self.assertEqual(self.deposit().code, 0)
        before = self.registry_text()
        state = CLI.deposit_state(self.root, "cohort")
        self.assertEqual(state["recorded"], True)
        self.assertEqual(state["current"], True)
        self.assertEqual(state["deposit"], self.entry("cohort")["deposit"])
        entry = self.entry("cohort")
        self.assertEqual(CLI.deposit_state(self.root, entry), state)
        data.write_text("age,score\n1,1\n", encoding="utf-8")
        stale = CLI.deposit_state(self.root, entry)
        self.assertEqual((stale["current"], stale["stale"]),
                         (False, [{"reason": "file-changed", "file": "data/cohort.csv"}]))
        self.assertEqual(self.registry_text(), before)

    def test_a_malformed_record_is_never_current(self) -> None:
        self.own_with_file()
        for broken in ("text", {"files": "nope"}, {"files": {}}):
            entry = {**self.entry("cohort"), "deposit": broken}
            state = CLI.deposit_state(self.root, entry)
            self.assertTrue(state["recorded"])
            self.assertFalse(state["current"])


# ------------------------------------------------------------- unchanged
class UnchangedTests(Base):
    def test_status_without_a_deposit_keeps_its_shape(self) -> None:
        self.own_with_file()
        self.assertEqual(set(self.status_item()),
                         {"slug", "role", "title", "license", "host_license", "qc", "prepared", "remote"})


class DoctrineTests(unittest.TestCase):
    def test_the_skill_documents_the_record_and_never_deposits(self) -> None:
        flat = " ".join((SKILL / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("| `deposit` |", flat)
        self.assertIn("It never deposits a dataset", flat)
        self.assertIn("never records a deposit on the operator's behalf", flat)
        self.assertIn("deposit?{repository, identifier, scheme, license", flat)


if __name__ == "__main__":
    unittest.main()
