"""Own data in the `datasets` skill (T7-U3, S7): the `own` role with the
operator's data-use statement, the data dictionary, and QC against it.

Driven through `datasets_cli.run(argv)`, the entry point `main()` uses, and
asserted on the exit code, the refusal code and the persisted JSON.
"""

from __future__ import annotations

import csv
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
CLI_PATH = ROOT / "skills" / "datasets" / "scripts" / "datasets_cli.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("datasets_cli_own_data", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLI = load_cli()


class Run:
    def __init__(self, root: Path, argv: list[str]) -> None:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.code = CLI.run(["--root", str(root), *argv])
        self.out, self.err = out.getvalue(), err.getvalue()
        self.json = json.loads(self.out) if self.out.strip().startswith("{") else None
        self.error = json.loads(self.err) if self.err.strip().startswith("{") else None


class Base(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()

    def cli(self, *argv: str) -> Run:
        return Run(self.root, list(argv))

    def registry(self) -> list[dict]:
        return json.loads((self.root / "datasets" / "registry.json").read_text(encoding="utf-8"))

    def entry(self, slug: str) -> dict:
        return next(item for item in self.registry() if item["slug"] == slug)

    def write_csv(self, name: str, header: list[str], rows: list[list[str]]) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
        return path

    def write_dictionary(self, slug: str, columns: list[dict]) -> Path:
        path = self.root / "datasets" / slug / "dictionary.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"slug": slug, "columns": columns}), encoding="utf-8")
        return path

    def own(self, slug: str = "cohort") -> Run:
        result = self.cli("own", "--slug", slug, "--by", "Dr. Operator",
                          "--statement", "Collected under protocol 12/2026; analysis in this workspace only.")
        self.assertEqual(result.code, 0, result.err)
        return result

    def assertRefused(self, result: Run, code: str) -> None:
        self.assertEqual(result.code, 2, result.out)
        self.assertEqual(result.error["error"], code, result.err)
        self.assertIn("objective", result.error)


def column(name: str, type_: str, **extra) -> dict:
    return {"name": name, "type": type_, **extra}


# ----------------------------------------------------------------------- own
class OwnRoleTests(Base):
    def test_own_records_the_operator_statement_instead_of_a_license_classification(self) -> None:
        result = self.own()
        entry = self.entry("cohort")
        self.assertEqual(entry["role"], "own")
        self.assertEqual(entry["source"]["kind"], "own")
        self.assertEqual(entry["data_use"]["by"], "Dr. Operator")
        self.assertEqual(entry["data_use"]["statement"],
                         "Collected under protocol 12/2026; analysis in this workspace only.")
        self.assertTrue(entry["data_use"]["recorded"])
        self.assertEqual(entry["license"]["source_name"], "own data")
        self.assertEqual(entry["license"]["decision"], "allowed")
        self.assertIn("data-use statement", entry["license"]["reason"])
        self.assertEqual(result.json["role"], "own")
        self.assertEqual(result.json["data_use"], entry["data_use"])

    def test_the_operator_and_the_statement_are_required(self) -> None:
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            CLI.run(["--root", str(self.root), "own", "--slug", "cohort", "--statement", "text"])
        self.assertEqual(raised.exception.code, 2)
        self.assertRefused(self.cli("own", "--slug", "cohort", "--by", "  ", "--statement", "text"),
                           "operator-missing")
        self.assertRefused(self.cli("own", "--slug", "cohort", "--by", "Dr. Operator", "--statement", " "),
                           "statement-missing")
        self.assertFalse((self.root / "datasets" / "registry.json").exists())

    def test_own_and_license_never_change_each_others_role(self) -> None:
        self.assertEqual(self.cli("license", "--slug", "public-set", "--source-license", "CC0").code, 0)
        self.assertRefused(self.cli("own", "--slug", "public-set", "--by", "Op", "--statement", "mine"),
                           "role-conflict")
        self.assertEqual(self.entry("public-set")["role"], "full")
        self.own("cohort")
        before = self.entry("cohort")
        self.assertRefused(self.cli("license", "--slug", "cohort", "--source-license", "CC-BY-NC"),
                           "role-conflict")
        self.assertEqual(self.entry("cohort"), before)

    def test_a_new_statement_keeps_the_previous_one_in_its_history(self) -> None:
        self.own("cohort")
        first = self.entry("cohort")["data_use"]
        result = self.cli("own", "--slug", "cohort", "--by", "Dr. Operator", "--statement", "Now shareable on request.")
        self.assertEqual(result.code, 0, result.err)
        data_use = self.entry("cohort")["data_use"]
        self.assertEqual(data_use["statement"], "Now shareable on request.")
        self.assertEqual(data_use["history"], [{k: first[k] for k in ("statement", "by", "recorded")}])


# ---------------------------------------------------------------- dictionary
class DictionaryTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.own()
        self.data = self.write_csv(
            "data/cohort.csv", ["patient_email", "age", "sex", "smoker", "visit", "note"],
            [[f"p{i}@example.org", str(30 + i), "F" if i % 2 else "M", "yes" if i % 3 else "no",
              f"2026-01-{i + 1:02d}", f"free text {i}"] for i in range(12)])

    def dictionary(self) -> dict:
        return json.loads((self.root / "datasets/cohort/dictionary.json").read_text(encoding="utf-8"))

    def test_init_scaffolds_one_entry_per_header_column(self) -> None:
        result = self.cli("dictionary", "init", "--slug", "cohort", "--file", str(self.data))
        self.assertEqual(result.code, 0, result.err)
        written = self.dictionary()
        self.assertEqual(written["file"], "data/cohort.csv")
        self.assertEqual(written["sha256"], hashlib.sha256(self.data.read_bytes()).hexdigest())
        by_name = {c["name"]: c for c in written["columns"]}
        self.assertEqual([c["name"] for c in written["columns"]],
                         ["patient_email", "age", "sex", "smoker", "visit", "note"])
        self.assertEqual({n: c["type"] for n, c in by_name.items()},
                         {"patient_email": "text", "age": "integer", "sex": "category", "smoker": "boolean",
                          "visit": "date", "note": "text"})
        self.assertEqual(by_name["sex"]["levels"], ["F", "M"])
        self.assertTrue(by_name["patient_email"]["pii"])
        self.assertFalse(by_name["age"]["pii"])
        for entry in written["columns"]:
            self.assertEqual(set(entry), {"name", "type", "unit", "range", "levels", "missing_codes",
                                          "description", "pii"})
        self.assertNotIn("example.org", json.dumps(written))
        self.assertEqual(result.json["columns"], 6)
        self.assertRefused(self.cli("dictionary", "init", "--slug", "cohort", "--file", str(self.data)),
                           "dictionary-exists")
        self.assertEqual(self.cli("dictionary", "init", "--slug", "cohort", "--file", str(self.data),
                                  "--force").code, 0)

    def test_check_accepts_a_valid_dictionary(self) -> None:
        self.write_dictionary("cohort", [column("age", "integer", unit="years", range={"min": 18, "max": 90}),
                                         column("sex", "category", levels=["F", "M"]),
                                         column("patient_email", "text", pii=True)])
        result = self.cli("dictionary", "check", "--slug", "cohort")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(result.json["columns"], 3)
        self.assertEqual(result.json["pii"], ["patient_email"])

    def test_check_refuses_each_invalid_shape_with_its_code(self) -> None:
        cases = {
            "dictionary-unknown-type": [column("age", "float")],
            "dictionary-range-not-numeric": [column("note", "text", range={"min": 0, "max": 1})],
            "dictionary-empty-levels": [column("sex", "category", levels=[])],
            "dictionary-duplicate-column": [column("age", "integer"), column("age", "number")],
            "dictionary-bad-entry": [column("age", "integer", range={"min": 9, "max": 1})],
        }
        for code, columns in cases.items():
            with self.subTest(code=code):
                self.write_dictionary("cohort", columns)
                self.assertRefused(self.cli("dictionary", "check", "--slug", "cohort"), code)
        (self.root / "datasets/cohort/dictionary.json").write_text("{not json", encoding="utf-8")
        self.assertRefused(self.cli("dictionary", "check", "--slug", "cohort"), "dictionary-unreadable")
        (self.root / "datasets/cohort/dictionary.json").unlink()
        self.assertRefused(self.cli("dictionary", "check", "--slug", "cohort"), "dictionary-missing")
        self.assertRefused(self.cli("dictionary", "check", "--slug", "ghost"), "unknown-slug")


# ------------------------------------------------------------- domain checks
class DomainCheckTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.own()

    def qc(self, path: Path, *extra: str) -> tuple[Run, dict]:
        result = self.cli("qc", "--slug", "cohort", "--file", str(path), *extra)
        self.assertEqual(result.code, 0, result.err)
        report = json.loads((self.root / "datasets/cohort/qc.json").read_text(encoding="utf-8"))
        return result, report

    def checks(self, report: dict) -> dict:
        return {(c["check"], c.get("column")): c for c in report["domain_checks"]}

    def test_the_data_is_validated_against_the_dictionary(self) -> None:
        rows = [["Ana Pérez", "34", "F", "120", "2026-01-02"],
                ["Luis Gómez", "-99", "M", "250", "2026-01-03"],
                ["Eva Ruiz", "41", "X", "130", "2026-01-04"],
                ["Juan Díaz", "abc", "F", "999", "2026-02-30"],
                ["Rosa Vega", "58", "Q", "140", "2026-01-06"]]
        path = self.write_csv("data/cohort.csv", ["full_name", "age", "sex", "sbp", "extra"], rows)
        dictionary = self.write_dictionary("cohort", [
            column("full_name", "text", pii=True),
            column("age", "integer", unit="years", range={"min": 18, "max": 90}, missing_codes=["-99"]),
            column("sex", "category", levels=["F", "M"]),
            column("sbp", "number", unit="mmHg", range={"min": 60, "max": 240}, missing_codes=["999"]),
            column("weight", "number", unit="kg"),
        ])
        result, report = self.qc(path)
        checks = self.checks(report)
        self.assertEqual(checks[("out-of-range", "sbp")]["count"], 1)
        self.assertEqual(checks[("out-of-range", "sbp")]["rows"], [2])
        self.assertEqual(checks[("unknown-level", "sex")]["count"], 2)
        self.assertEqual(checks[("unknown-level", "sex")]["rows"], [3, 5])
        self.assertEqual(checks[("type-mismatch", "age")]["count"], 1)
        self.assertEqual(checks[("type-mismatch", "age")]["rows"], [4])
        self.assertEqual(checks[("missing-codes", "age")]["count"], 1)
        self.assertEqual(checks[("missing-codes", "sbp")]["count"], 1)
        self.assertEqual(checks[("undeclared-column", "extra")]["severity"], "warn")
        self.assertEqual(checks[("absent-column", "weight")]["severity"], "fail")
        self.assertEqual(checks[("pii-column", "full_name")]["count"], 5)
        self.assertEqual(checks[("pii-column", "full_name")]["severity"], "warn")
        self.assertEqual(checks[("type-mismatch", "age")]["severity"], "fail")
        self.assertEqual(checks[("out-of-range", "sbp")]["severity"], "warn")
        # Missing codes count as missing and leave the measured range.
        self.assertEqual(report["missing"]["age"], 1)
        self.assertEqual(report["missing"]["sbp"], 1)
        self.assertEqual(report["ranges"]["sbp"], {"min": 120.0, "max": 250.0})
        self.assertEqual(report["status"], "fail")
        self.assertEqual(result.json["status"], "fail")
        self.assertTrue(any("weight" in reason for reason in report["reasons"]))
        self.assertEqual(report["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(report["dictionary"], {
            "file": "datasets/cohort/dictionary.json",
            "sha256": hashlib.sha256(dictionary.read_bytes()).hexdigest()})
        text = json.dumps(report)
        for name, *_ in rows:
            self.assertNotIn(name, text)
        self.assertEqual(self.entry("cohort")["qc"]["status"], "fail")

    def test_pii_values_never_reach_the_report(self) -> None:
        path = self.write_csv("data/ids.csv", ["national_id", "score"],
                              [["900111222", "1"], ["900333444", "2"], ["oops", "3"]])
        self.write_dictionary("cohort", [column("national_id", "integer", pii=True, range={"min": 0, "max": 5}),
                                         column("score", "integer")])
        _result, report = self.qc(path)
        text = json.dumps(report)
        for value in ("900111222", "900333444", "oops", "9001"):
            self.assertNotIn(value, text)
        checks = self.checks(report)
        self.assertNotIn("values", checks[("type-mismatch", "national_id")])
        self.assertNotIn("national_id", report["ranges"])

    def test_warn_only_findings_warn_and_clean_data_passes(self) -> None:
        path = self.write_csv("data/clean.csv", ["age", "sex"], [["30", "F"], ["95", "M"], ["40", "F"]])
        self.write_dictionary("cohort", [column("age", "integer", range={"min": 18, "max": 90}),
                                         column("sex", "category", levels=["F", "M"])])
        _result, report = self.qc(path)
        self.assertEqual(report["status"], "warn")
        self.assertEqual(self.checks(report)[("out-of-range", "age")]["values"], ["95"])
        self.write_dictionary("cohort", [column("age", "integer", range={"min": 18, "max": 99}),
                                         column("sex", "category", levels=["F", "M"])])
        _result, report = self.qc(path)
        self.assertEqual(report["status"], "pass", report["reasons"])
        self.assertEqual(report["domain_checks"], [])

    def test_an_invalid_dictionary_stops_qc(self) -> None:
        path = self.write_csv("data/clean.csv", ["age"], [["30"]])
        self.write_dictionary("cohort", [column("age", "float")])
        self.assertRefused(self.cli("qc", "--slug", "cohort", "--file", str(path)), "dictionary-unknown-type")
        self.assertFalse((self.root / "datasets/cohort/qc.json").exists())

    def test_own_data_without_a_dictionary_warns(self) -> None:
        path = self.write_csv("data/clean.csv", ["age", "sex"], [["30", "F"], ["40", "M"]])
        _result, report = self.qc(path)
        self.assertEqual(report["status"], "warn")
        self.assertTrue(any("dictionary" in reason for reason in report["reasons"]))
        self.assertEqual(report["domain_checks"], [])


# ------------------------------------------------------------- unchanged
class ExistingRolesUnchangedTests(Base):
    def test_full_license_and_qc_outputs_keep_their_shape(self) -> None:
        result = self.cli("license", "--slug", "full-set", "--source-license", "CC-BY 4.0")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(set(result.json), {"slug", "source_name", "decision", "host_license", "reason", "decided"})
        self.assertEqual((result.json["decision"], result.json["host_license"]), ("allowed", "CC-BY-4.0"))
        entry = self.entry("full-set")
        self.assertEqual(set(entry), {"slug", "role", "title", "source", "license", "files", "qc",
                                      "preparation", "remote"})
        self.assertEqual(entry["source"]["kind"], "external")
        path = self.write_csv("clean.csv", ["subject", "label", "x"],
                              [[f"s{i // 4}", str(i % 2), str(i * 1.5)] for i in range(16)])
        result = self.cli("qc", "--slug", "full-set", "--file", str(path), "--label", "label", "--group", "subject")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(result.json, {"slug": "full-set", "status": "pass", "reasons": [],
                                       "report": "datasets/full-set/qc.json"})
        report = json.loads((self.root / "datasets/full-set/qc.json").read_text(encoding="utf-8"))
        self.assertEqual(set(report), {"rows", "columns", "missing", "constant_columns", "duplicates", "ranges",
                                       "class_balance", "groups", "status", "reasons", "file", "sha256",
                                       "checked", "domain_checks"})
        self.assertEqual(report["domain_checks"], [])

    def test_toy_entries_keep_their_shape(self) -> None:
        result = self.cli("synth", "--slug", "toy", "--kind", "classification", "--n-subjects", "2",
                          "--n-per-subject", "4", "--channels", "2")
        self.assertEqual(result.code, 0, result.err)
        entry = self.entry("toy")
        self.assertEqual(set(entry), {"slug", "role", "title", "source", "license", "files", "qc",
                                      "preparation", "remote"})
        result = self.cli("qc", "--slug", "toy", "--file", entry["files"][0], "--label", "label")
        self.assertEqual(result.code, 0, result.err)
        report = json.loads((self.root / "datasets/toy/qc.json").read_text(encoding="utf-8"))
        self.assertNotIn("dictionary", report)
        self.assertFalse(any("dictionary" in reason for reason in report["reasons"]))


if __name__ == "__main__":
    unittest.main()
