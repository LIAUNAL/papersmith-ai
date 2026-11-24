"""Verbatim participant quotes (paper-type-lines S8, T8-Q1, decision K3).

K3: "every participant quote in the paper must be found verbatim in a
registered transcript (`qual_cli.py quotes check`, run by `verify`), so a
quote cannot be invented or polished". A quote is written
`\\pquote{<participant code>}{<text>}`; only whitespace and quote ligatures
(and the LaTeX escapes of special characters) are normalised. `verify` reports
the check under its own `qualitative` key, only in a workspace with
`study/transcripts.json`, so every other line's report is unchanged.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
QUAL_CLI = FORGE_ROOT / "skills" / "_core" / "qualitative" / "qual_cli.py"
SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(FORGE_ROOT))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from skills._core.qualitative import records  # noqa: E402
import paper_verify  # noqa: E402
from test_paper_writing import CLI as PAPER_CLI, _build_coupling_paper  # noqa: E402

SECRET = "OCELOTBRAMBLE9902"  # a transcript word no quote uses: never in any output
P01 = ("Interviewer: And the co-op?\n"
       "P01: Honestly, the co-op   helped us\nmore than the ministry did. It's the \u201cneighbours' bank\u201d.\n"
       f"P01: We kept the seed in jars, {SECRET}, and 50% of it rotted.\n")
P02 = "P02: The road washed out twice that year.\n"


def _register(root: Path, file: str, participant: str) -> dict:
    proc = subprocess.run([sys.executable, str(QUAL_CLI), "transcripts", "add", "--file", file, "--participant",
                           participant, "--consent", "written", "--deidentified", "codes", "--by", "Ana",
                           "--root", str(root)], capture_output=True, text=True, timeout=60)
    out = json.loads(proc.stdout)
    assert proc.returncode == 0, out
    return out


class _Quotes(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="qual-quotes-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.outputs: list[str] = []
        self.write("data/p01.txt", P01)
        self.write("data/p02.txt", P02)
        _register(self.root, "data/p01.txt", "P01")
        _register(self.root, "data/p02.txt", "P02")

    def tearDown(self) -> None:
        for out in self.outputs:
            self.assertNotIn(SECRET, out, "a transcript's text reached an output")

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def check(self, *extra: str) -> tuple[int, dict]:
        proc = subprocess.run([sys.executable, str(QUAL_CLI), "quotes", "check", *extra, "--root", str(self.root)],
                              capture_output=True, text=True, timeout=60)
        self.outputs.extend((proc.stdout, proc.stderr))
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout + proc.stderr[-400:])
        return proc.returncode, json.loads(lines[0])

    def paper(self, body: str, name: str = "main.tex") -> None:
        self.write(f"paper/{name}", "\\section{Findings}\n" + body + "\n")

    def failures(self) -> list[dict]:
        code, out = self.check()
        if out.get("ok"):
            self.assertEqual(code, 0)
            return []
        self.assertEqual((code, out["error"]), (1, "QUOTE_NOT_FOUND"), out)
        return out["failures"]


class QuotesCheckTests(_Quotes):
    def test_a_verbatim_quote_passes(self) -> None:
        self.paper("One farmer put it plainly: \\pquote{P01}{the co-op helped us more than the ministry did}.")
        code, out = self.check()
        self.assertEqual((code, out["ok"], out["quotes"], out["verified"]), (0, True, 1, 1), out)
        self.assertEqual(out["files"], ["paper/main.tex"])

    def test_a_paper_without_quotes_passes(self) -> None:
        self.paper("No participant speaks here.")
        code, out = self.check()
        self.assertEqual((code, out["quotes"], out["failures"]), (0, 0, []))

    def test_a_polished_or_invented_quote_fails_with_file_and_line(self) -> None:
        self.paper("Intro line.\n\nThey said \\pquote{P01}{the cooperative helped us more than the ministry did}.")
        failures = self.failures()
        self.assertEqual(failures, [{"file": "paper/main.tex", "line": 4, "participant": "P01",
                                     "reason": "not-found",
                                     "quote": "the cooperative helped us more than the ministry did"}])

    def test_whitespace_and_line_breaks_are_normalised(self) -> None:
        self.paper("\\pquote{P01}{Honestly, the co-op helped\n   us more than the ministry did.}")
        self.assertEqual(self.failures(), [])

    def test_quote_ligatures_are_normalised(self) -> None:
        self.paper("\\pquote{P01}{It's the ``neighbours' bank''.}")
        self.assertEqual(self.failures(), [])
        self.paper("\\pquote{P01}{It\u2019s the \"neighbours\u2019 bank\".}")
        self.assertEqual(self.failures(), [])

    def test_latex_escapes_and_ties_are_read_as_printed(self) -> None:
        self.paper("\\pquote{P01}{and 50\\% of it~rotted}")
        self.assertEqual(self.failures(), [])

    def test_case_and_punctuation_are_not_normalised(self) -> None:
        self.paper("\\pquote{P01}{The co-op helped us}")
        self.assertEqual([f["reason"] for f in self.failures()], ["not-found"])
        self.paper("\\pquote{P01}{the co-op helped us more than the ministry did!}")
        self.assertEqual([f["reason"] for f in self.failures()], ["not-found"])

    def test_a_quote_attributed_to_the_wrong_participant_fails(self) -> None:
        self.paper("\\pquote{P02}{the co-op helped us}")
        self.assertEqual([(f["participant"], f["reason"]) for f in self.failures()], [("P02", "not-found")])

    def test_an_unregistered_participant_fails(self) -> None:
        self.paper("\\pquote{P09}{the co-op helped us}")
        self.assertEqual([f["reason"] for f in self.failures()], ["participant-not-registered"])

    def test_a_quote_from_a_stale_transcript_fails(self) -> None:
        self.paper("\\pquote{P01}{the co-op helped us}")
        self.write("data/p01.txt", P01 + "P01: added later.\n")
        self.assertEqual([f["reason"] for f in self.failures()], ["transcript-stale"])

    def test_commented_quotes_are_ignored_and_escaped_percent_is_not_a_comment(self) -> None:
        self.paper("% \\pquote{P01}{an invented line}\nSee 10\\% \\pquote{P02}{The road washed out twice}")
        code, out = self.check()
        self.assertEqual((code, out["quotes"]), (0, 1), out)

    def test_every_tex_file_is_scanned_but_translations(self) -> None:
        self.paper("\\pquote{P02}{The road washed out twice that year.}")
        self.write("paper/sections/results.tex", "a\nb\n\\pquote{P02}{The bridge washed out}\n")
        self.write("paper/translations/es/main.tex", "\\pquote{P02}{El camino se inund\u00f3 dos veces}\n")
        code, out = self.check()
        self.assertEqual(out["quotes"], 2)
        self.assertEqual([(f["file"], f["line"]) for f in out["failures"]], [("paper/sections/results.tex", 3)])

    def test_malformed_and_empty_quotes_fail(self) -> None:
        self.paper("\\pquote{P01}{ }\n\\pquote{P01}{never closed")
        self.assertEqual([(f["line"], f["reason"]) for f in self.failures()],
                         [(2, "quote-empty"), (3, "quote-malformed")])

    def test_another_macro_starting_with_pquote_is_not_a_quote(self) -> None:
        self.paper("\\pquotestyle{P01}{anything}")
        self.assertEqual(self.check()[1]["quotes"], 0)

    def test_paper_dir_refusals(self) -> None:
        code, out = self.check("--paper", "nowhere")
        self.assertEqual((code, out["error"]), (1, "PAPER_MISSING"))
        code, out = self.check("--paper", "../")
        self.assertEqual((code, out["error"]), (1, "PAPER_OUTSIDE"))

    def test_a_corrupt_register_is_refused(self) -> None:
        self.paper("\\pquote{P01}{the co-op helped us}")
        self.write("study/transcripts.json", "{")
        code, out = self.check()
        self.assertEqual((code, out["error"]), (1, "TRANSCRIPTS_CORRUPT"))

    def test_the_reader_never_returns_transcript_text(self) -> None:
        self.paper("\\pquote{P01}{the co-op helped us}\n\\pquote{P01}{made up}")
        result = records.check_quotes(self.root, self.root / "paper")
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn(SECRET, json.dumps(records.qualitative_status(self.root)))


class VerifyEntryTests(unittest.TestCase):
    """`paper_verify` stays pure: it shapes the entry `cmd_verify` reads from `check_quotes`."""

    REPORT = {"checks": [], "clean": True, "holds": 10, "fails": 0, "unmeasured": 0, "structure": []}

    def test_no_register_adds_nothing(self) -> None:
        self.assertEqual(paper_verify.qualitative_entries(None), [])
        self.assertIs(paper_verify.attach_qualitative(self.REPORT, []), self.REPORT)

    def test_a_failing_quote_fails_verify_naming_file_and_line(self) -> None:
        result = {"quotes": 2, "verified": 1, "transcripts": 2, "files": ["paper/main.tex"],
                  "failures": [{"file": "paper/main.tex", "line": 7, "participant": "P01", "reason": "not-found",
                                "quote": "made up"}]}
        report = paper_verify.attach_qualitative(self.REPORT, paper_verify.qualitative_entries(result))
        self.assertFalse(report["clean"])
        (entry,) = report["qualitative"]
        self.assertEqual((entry["check"], entry["verdict"], entry["severity"]), ("quote-not-verbatim", "fail", "error"))
        self.assertEqual(entry["findings"], result["failures"])
        self.assertEqual((report["holds"], report["fails"], report["unmeasured"]), (10, 0, 0))

    def test_all_quotes_found_keeps_clean(self) -> None:
        result = {"quotes": 1, "verified": 1, "transcripts": 1, "files": ["paper/main.tex"], "failures": []}
        report = paper_verify.attach_qualitative(self.REPORT, paper_verify.qualitative_entries(result))
        self.assertTrue(report["clean"])
        self.assertEqual(report["qualitative"][0]["verdict"], "pass")
        unclean = paper_verify.attach_qualitative({**self.REPORT, "clean": False},
                                                  paper_verify.qualitative_entries(result))
        self.assertFalse(unclean["clean"])

    def test_unreadable_register_or_module_is_unmeasured(self) -> None:
        for result, reason in (({"corrupt": "bad json"}, "TRANSCRIPTS_CORRUPT"),
                               ({"unavailable": "not shipped"}, "CHECK_FAILED")):
            report = paper_verify.attach_qualitative(self.REPORT, paper_verify.qualitative_entries(result))
            self.assertEqual((report["qualitative"][0]["verdict"], report["qualitative"][0]["unmeasured_reason"]),
                             ("unmeasured", reason))
            self.assertTrue(report["clean"])

    def test_a_malformed_entry_list_is_a_programming_error(self) -> None:
        entry = paper_verify.qualitative_entries({"failures": [], "quotes": 0})[0]
        for bad in ([{**entry, "check": "other"}], [entry, entry], [{**entry, "severity": "warning"}],
                    [{**entry, "verdict": "fail"}]):
            with self.assertRaises(AssertionError):
                paper_verify.attach_qualitative(self.REPORT, bad)


class VerifyIntegrationTests(unittest.TestCase):
    """Through the real `paper_cli.py verify`; the paper CLI refuses papers outside the
    repository, so each fixture lives under `.scratch/`."""

    def setUp(self) -> None:
        (FORGE_ROOT / ".scratch").mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix=".qual-verify-", dir=FORGE_ROOT / ".scratch"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.sections_dir = self.root / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)

    def verify(self) -> tuple[int, str, dict]:
        proc = subprocess.run([sys.executable, str(PAPER_CLI), "verify", "--paper", str(self.paper_dir),
                               "--sections", str(self.sections_dir)], capture_output=True, text=True, timeout=120)
        self.assertNotIn(SECRET, proc.stdout + proc.stderr)
        return proc.returncode, proc.stdout, json.loads(proc.stdout)

    def quotes_file(self, body: str) -> None:
        (self.paper_dir / "quotes.tex").write_text(body + "\n", encoding="utf-8")

    def test_a_workspace_without_transcripts_verifies_unchanged(self) -> None:
        code, before, report = self.verify()
        self.assertNotIn("qualitative", report)
        # Without a register a quote is never checked: the report is byte-identical.
        self.quotes_file("\\pquote{P01}{made up}")
        code_after, after, _ = self.verify()
        self.assertEqual((code_after, after), (code, before))

    def test_a_quote_not_in_its_transcript_fails_verify(self) -> None:
        _, _, baseline = self.verify()
        (self.root / "data").mkdir()
        (self.root / "data/p01.txt").write_text(P01, encoding="utf-8")
        _register(self.root, "data/p01.txt", "P01")
        self.quotes_file("\\pquote{P01}{the co-op helped us}\n\\pquote{P01}{the cooperative saved us}")
        _, _, report = self.verify()
        (entry,) = report["qualitative"]
        self.assertEqual((entry["check"], entry["verdict"]), ("quote-not-verbatim", "fail"))
        self.assertEqual([(f["file"], f["line"], f["reason"]) for f in entry["findings"]],
                         [(f"{self.paper_dir.name}/quotes.tex", 2, "not-found")])
        self.assertFalse(report["clean"])
        self.assertEqual({k: report[k] for k in ("holds", "fails", "unmeasured")},
                         {k: baseline[k] for k in ("holds", "fails", "unmeasured")})

    def test_verbatim_quotes_pass_and_leave_clean_as_it_was(self) -> None:
        _, _, baseline = self.verify()
        (self.root / "data").mkdir()
        (self.root / "data/p01.txt").write_text(P01, encoding="utf-8")
        _register(self.root, "data/p01.txt", "P01")
        self.quotes_file("\\pquote{P01}{the co-op helped us}")
        _, _, report = self.verify()
        self.assertEqual(report["qualitative"][0]["verdict"], "pass")
        self.assertEqual(report["clean"], baseline["clean"])


if __name__ == "__main__":
    unittest.main()
