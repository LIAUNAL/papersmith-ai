"""The qualitative core's operator records (paper-type-lines S8, T8-Q1, decisions K2, K5, K8).

K2: "the operator registers each de-identified transcript or field note by
sha256 with its participant code and consent (`transcripts add --by`; the
assistant never writes or edits a transcript), records codebook versions and
signs off the themes (`themes signoff --by`, G-ANALYSIS); the assistant may
propose codes and themes, only the operator records them". K8: the Study tab
shows transcripts, the codebook and the theme sign-off, "never a transcript's
text". Driven through the real `qual_cli.py` and the importable readers.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
CLI = FORGE_ROOT / "skills" / "_core" / "qualitative" / "qual_cli.py"
sys.path.insert(0, str(FORGE_ROOT))
from skills._core.qualitative import records  # noqa: E402

#: Recognizable transcript words: no output may ever carry them.
TOKENS = ("ZEBRAQUILL7731", "MARMOTLANTERN4410")
TRANSCRIPT = (f"Interviewer: How was the harvest?\nP01: Honestly the rains came late and {TOKENS[0]} "
              f"was all we had.\nP01: The co-op helped us more than the ministry did. {TOKENS[1]}\n")


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="qual-core-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.outputs: list[str] = []
        self.write("data/p01.txt", TRANSCRIPT)

    def tearDown(self) -> None:
        for out in self.outputs:
            for token in TOKENS:
                self.assertNotIn(token, out, "a transcript's text reached an output")

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_cli(self, *argv: str, root: Path | None = None) -> tuple[int, dict]:
        proc = subprocess.run([sys.executable, str(CLI), *argv, "--root", str(root or self.root)],
                              capture_output=True, text=True, timeout=60)
        self.outputs.extend((proc.stdout, proc.stderr))
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, f"one JSON object per call: {proc.stdout!r} {proc.stderr[-400:]!r}")
        return proc.returncode, json.loads(lines[0])

    def add(self, file: str = "data/p01.txt", participant: str = "P01", *extra: str) -> tuple[int, dict]:
        return self.run_cli("transcripts", "add", "--file", file, "--participant", participant,
                            "--consent", "written consent, form C-12", "--deidentified",
                            "names and places replaced by codes", "--by", "Ana Ruiz", *extra)

    def refused(self, result: tuple[int, dict], code: str) -> dict:
        exit_code, out = result
        self.assertEqual((exit_code, out.get("ok"), out.get("error")), (1, False, code), out)
        return out

    def record(self, rel: str) -> dict:
        return json.loads((self.root / rel).read_text(encoding="utf-8"))


class TranscriptsAddTests(_Workspace):
    def test_registers_by_sha256_and_character_count_never_the_text(self) -> None:
        code, out = self.add()
        self.assertEqual(code, 0, out)
        self.assertTrue(out["ok"])
        self.assertEqual(out["path"], "study/transcripts.json")
        shown = out["registered"]
        self.assertEqual((shown["participant"], shown["file"], shown["kind"], shown["state"]),
                         ("P01", "data/p01.txt", "interview", "current"))
        self.assertEqual(shown["characters"], len(TRANSCRIPT))
        self.assertEqual(out["gate"], {"id": "G-TRANSCRIPTS", "passed": True, "state": "current"})
        entry = self.record("study/transcripts.json")["history"][0]
        import hashlib
        self.assertEqual(entry["sha256"], hashlib.sha256(TRANSCRIPT.encode()).hexdigest())
        self.assertEqual((entry["by"], entry["action"], entry["consent"], entry["deidentified"]),
                         ("Ana Ruiz", "add", "written consent, form C-12", "names and places replaced by codes"))
        self.assertEqual((self.root / "data/p01.txt").read_text(encoding="utf-8"), TRANSCRIPT, "never edited")

    def test_kind_and_note_are_kept(self) -> None:
        self.write("data/field.md", "Observed the market at dawn.\n")
        code, out = self.add("data/field.md", "SITE-A", "--kind", "field-note", "--note", "first visit")
        self.assertEqual(code, 0, out)
        self.assertEqual((out["registered"]["kind"], out["registered"]["note"]), ("field-note", "first visit"))

    def test_a_focus_group_file_holds_several_participants(self) -> None:
        self.assertEqual(self.add("data/p01.txt", "P01")[0], 0)
        code, out = self.add("data/p01.txt", "P02", "--kind", "focus-group")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["counts"]["participants"], 2)

    def test_refusals_write_nothing(self) -> None:
        cases = {
            "APPROVER_MISSING": ("transcripts", "add", "--file", "data/p01.txt", "--participant", "P01",
                                 "--consent", "oral", "--deidentified", "coded"),
            "CONSENT_MISSING": ("transcripts", "add", "--file", "data/p01.txt", "--participant", "P01",
                                "--deidentified", "coded", "--by", "Ana"),
            "DEIDENTIFICATION_MISSING": ("transcripts", "add", "--file", "data/p01.txt", "--participant", "P01",
                                         "--consent", "oral", "--deidentified", "  ", "--by", "Ana"),
            "FIELD_MISSING": ("transcripts", "add", "--file", "data/p01.txt", "--consent", "oral",
                              "--deidentified", "coded", "--by", "Ana"),
            "PARTICIPANT_INVALID": ("transcripts", "add", "--file", "data/p01.txt", "--participant", "Maria Lopez",
                                    "--consent", "oral", "--deidentified", "coded", "--by", "Ana"),
            "TEXT_INVALID": ("transcripts", "add", "--file", "data/p01.txt", "--participant", "P01",
                             "--consent", "oral\x07", "--deidentified", "coded", "--by", "Ana"),
        }
        for code, argv in cases.items():
            with self.subTest(code=code):
                self.refused(self.run_cli(*argv), code)
        self.assertFalse((self.root / "study").exists())

    def test_an_empty_missing_or_binary_file_is_refused(self) -> None:
        self.write("data/empty.txt", "  \n\n")
        (self.root / "data/latin.txt").write_bytes("se\xf1or".encode("latin-1"))
        self.refused(self.add("data/empty.txt"), "FILE_EMPTY")
        self.refused(self.add("data/none.txt"), "FILE_MISSING")
        self.refused(self.add("data/latin.txt"), "TRANSCRIPT_NOT_TEXT")
        self.assertFalse((self.root / "study").exists())

    def test_paths_are_confined_to_the_workspace(self) -> None:
        outside = Path(tempfile.mkdtemp(prefix="qual-outside-"))
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (outside / "t.txt").write_text(TRANSCRIPT, encoding="utf-8")
        os.symlink(outside / "t.txt", self.root / "data/link.txt")
        for given in (str(outside / "t.txt"), f"../{outside.name}/t.txt", "data/link.txt", "."):
            with self.subTest(given=given):
                self.refused(self.add(given), "FILE_OUTSIDE")
        self.assertFalse((self.root / "study").exists())

    def test_an_absolute_path_inside_the_workspace_is_stored_relative(self) -> None:
        code, out = self.add(str(self.root / "data/p01.txt"))
        self.assertEqual(code, 0, out)
        self.assertEqual(out["registered"]["file"], "data/p01.txt")

    def test_a_duplicate_participant_for_the_same_file_is_refused(self) -> None:
        self.assertEqual(self.add()[0], 0)
        self.refused(self.add(), "TRANSCRIPT_DUPLICATE")
        self.assertEqual(len(self.record("study/transcripts.json")["history"]), 1)

    def test_replace_registers_a_changed_file_and_keeps_history(self) -> None:
        self.refused(self.add("data/p01.txt", "P01", "--replace"), "TRANSCRIPT_NOT_REGISTERED")
        self.assertEqual(self.add()[0], 0)
        self.refused(self.add("data/p01.txt", "P01", "--replace"), "RECORD_UNCHANGED")
        self.write("data/p01.txt", TRANSCRIPT + "P01: One more line.\n")
        code, out = self.add("data/p01.txt", "P01", "--replace")
        self.assertEqual(code, 0, out)
        self.assertTrue(out["replaced"])
        history = self.record("study/transcripts.json")["history"]
        self.assertEqual([e["action"] for e in history], ["add", "replace"])
        self.assertEqual(records.transcripts_state(self.root)["counts"]["transcripts"], 1)

    def test_an_unknown_kind_is_a_usage_error(self) -> None:
        code, out = self.add("data/p01.txt", "P01", "--kind", "survey")
        self.assertEqual((code, out["error"]), (2, "USAGE"))

    def test_status_refuses_a_record_option(self) -> None:
        code, out = self.run_cli("transcripts", "status", "--by", "Ana")
        self.assertEqual((code, out["error"]), (2, "USAGE"))

    def test_root_is_accepted_before_the_action(self) -> None:
        self.assertEqual(self.add()[0], 0)
        proc = subprocess.run([sys.executable, str(CLI), "transcripts", "--root", str(self.root), "status"],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(json.loads(proc.stdout)["transcripts"]["state"], "current")

    def test_a_corrupt_register_refuses_and_reads_as_corrupt(self) -> None:
        self.write("study/transcripts.json", "{not json")
        self.refused(self.add(), "TRANSCRIPTS_CORRUPT")
        self.assertEqual(self.run_cli("transcripts", "status")[1]["transcripts"]["state"], "corrupt")


class TranscriptsStatusTests(_Workspace):
    def test_absent_then_current(self) -> None:
        state = records.transcripts_state(self.root)
        self.assertEqual((state["state"], state["passed"]), ("absent", False))
        self.add()
        code, out = self.run_cli("transcripts", "status")
        self.assertEqual(code, 0)
        self.assertEqual((out["transcripts"]["state"], out["transcripts"]["passed"]), ("current", True))

    def test_changed_or_missing_files_are_stale_and_fail_the_gate(self) -> None:
        self.add()
        self.write("data/p02.txt", "P02: something else.\n")
        self.add("data/p02.txt", "P02")
        self.write("data/p01.txt", TRANSCRIPT.replace("late", "early"))
        (self.root / "data/p02.txt").unlink()
        state = self.run_cli("transcripts", "status")[1]["transcripts"]
        self.assertEqual((state["state"], state["passed"]), ("stale", False))
        self.assertEqual({t["participant"]: t["reasons"] for t in state["transcripts"]},
                         {"P01": ["file-changed"], "P02": ["file-missing"]})
        self.assertEqual(state["counts"]["stale"], 2)
        self.assertEqual([w["code"] for w in state["warnings"]], ["TRANSCRIPT_STALE"] * 2)

    def test_a_hand_edited_path_leaving_the_workspace_is_outside_and_never_followed(self) -> None:
        outside = Path(tempfile.mkdtemp(prefix="qual-outside-"))
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (outside / "t.txt").write_text(TRANSCRIPT, encoding="utf-8")
        self.add()
        os.symlink(outside / "t.txt", self.root / "data/link.txt")
        data = self.record("study/transcripts.json")
        for stored in (str(outside / "t.txt"), f"../{outside.name}/t.txt", "data/link.txt", "bad\x00path"):
            with self.subTest(stored=stored):
                data["history"][0]["file"] = stored
                self.write("study/transcripts.json", json.dumps(data))
                state = records.transcripts_state(self.root)
                self.assertEqual(state["transcripts"][0]["reasons"], ["file-outside"])
                self.assertEqual(state["state"], "stale")

    def test_readers_never_raise_on_a_corrupt_record_and_write_nothing(self) -> None:
        for text in ("{", "[]", '{"history": [1]}', '{"history": [{"participant": "P01"}]}'):
            with self.subTest(text=text):
                self.write("study/transcripts.json", text)
                self.write("study/codebook.json", text)
                self.write("study/themes.json", text)
                self.assertEqual(records.transcripts_state(self.root)["state"], "corrupt")
                self.assertEqual(records.codebook_state(self.root)["state"], "corrupt")
                self.assertEqual(records.themes_state(self.root)["state"], "corrupt")
                status = records.qualitative_status(self.root)
                self.assertEqual([w["code"] for w in status["warnings"]],
                                 ["TRANSCRIPTS_CORRUPT", "CODEBOOK_CORRUPT", "THEMES_CORRUPT"])

    def test_readers_on_an_empty_workspace_create_nothing(self) -> None:
        empty = Path(tempfile.mkdtemp(prefix="qual-empty-"))
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        self.assertEqual(records.transcripts_state(empty)["state"], "absent")
        self.assertEqual(records.codebook_state(empty)["state"], "absent")
        self.assertEqual(records.themes_state(empty)["state"], "absent")
        self.assertEqual(records.check_quotes(empty, empty / "paper")["quotes"], 0)
        self.assertEqual(list(empty.iterdir()), [])


class CodebookAndThemesTests(_Workspace):
    def setUp(self) -> None:
        super().setUp()
        self.write("analysis/codebook.md", "# Codebook\n- late-rains: delays in the season\n")
        self.write("analysis/themes.md", "# Themes\n1. Institutions at a distance\n")

    def codebook(self) -> tuple[int, dict]:
        return self.run_cli("codebook", "record", "--file", "analysis/codebook.md", "--by", "Ana Ruiz")

    def signoff(self) -> tuple[int, dict]:
        return self.run_cli("themes", "signoff", "--file", "analysis/themes.md", "--by", "Ana Ruiz",
                            "--note", "after the second coding pass")

    def test_codebook_versions_are_kept_with_history(self) -> None:
        self.refused(self.run_cli("codebook", "record", "--file", "analysis/codebook.md"), "APPROVER_MISSING")
        code, out = self.codebook()
        self.assertEqual(code, 0, out)
        self.assertEqual((out["codebook"]["version"], out["codebook"]["state"]), (1, "current"))
        self.refused(self.codebook(), "RECORD_UNCHANGED")
        self.write("analysis/codebook.md", "# Codebook\n- late-rains\n- distant-institutions\n")
        self.assertEqual(records.codebook_state(self.root)["reasons"], ["file-changed"])
        code, out = self.codebook()
        self.assertEqual((code, out["codebook"]["version"], out["codebook"]["state"]), (0, 2, "current"))
        self.assertEqual(len(self.record("study/codebook.json")["history"]), 2)

    def test_codebook_file_refusals(self) -> None:
        self.write("analysis/blank.md", "\n")
        self.refused(self.run_cli("codebook", "record", "--file", "analysis/blank.md", "--by", "A"), "FILE_EMPTY")
        self.refused(self.run_cli("codebook", "record", "--file", "/etc/hostname", "--by", "A"), "FILE_OUTSIDE")
        self.refused(self.run_cli("codebook", "record", "--by", "A"), "FIELD_MISSING")

    def test_signoff_refuses_until_codebook_and_transcripts_are_current(self) -> None:
        self.refused(self.signoff(), "CODEBOOK_NOT_RECORDED")
        self.codebook()
        self.refused(self.signoff(), "TRANSCRIPTS_ABSENT")
        self.add()
        self.write("analysis/codebook.md", "# Codebook v2\n")
        self.refused(self.signoff(), "CODEBOOK_STALE")
        self.codebook()
        self.write("data/p01.txt", TRANSCRIPT + "edit\n")
        out = self.refused(self.signoff(), "TRANSCRIPTS_STALE")
        self.assertIn("data/p01.txt", out["message"])
        self.add("data/p01.txt", "P01", "--replace")
        self.refused(self.run_cli("themes", "signoff", "--file", "analysis/themes.md"), "APPROVER_MISSING")
        self.assertFalse((self.root / "study/themes.json").exists())
        code, out = self.signoff()
        self.assertEqual(code, 0, out)
        themes = out["themes"]
        self.assertEqual((themes["state"], themes["passed"], themes["gate"]), ("current", True, "G-ANALYSIS"))
        self.assertEqual(themes["codebook"]["version"], 2)
        self.assertEqual([t["participant"] for t in themes["transcripts"]], ["P01"])
        self.refused(self.signoff(), "RECORD_UNCHANGED")

    def signed(self) -> None:
        self.codebook()
        self.add()
        self.assertEqual(self.signoff()[0], 0)

    def themes_reasons(self) -> list[str]:
        state = self.run_cli("themes", "status")[1]["themes"]
        self.assertEqual(state["passed"], state["state"] == "current")
        return state["reasons"]

    def test_signoff_goes_stale_when_the_themes_file_changes(self) -> None:
        self.signed()
        self.write("analysis/themes.md", "# Themes\n1. Something else\n")
        self.assertEqual(self.themes_reasons(), ["themes-file-changed"])
        (self.root / "analysis/themes.md").unlink()
        self.assertEqual(self.themes_reasons(), ["themes-file-missing"])

    def test_signoff_goes_stale_when_the_codebook_changes(self) -> None:
        self.signed()
        self.write("analysis/codebook.md", "# Codebook v2\n")
        self.assertEqual(self.themes_reasons(), ["codebook-stale"])
        self.codebook()
        self.assertEqual(self.themes_reasons(), ["codebook-changed"])

    def test_signoff_goes_stale_when_a_transcript_changes_or_is_added(self) -> None:
        self.signed()
        self.write("data/p01.txt", TRANSCRIPT + "edit\n")
        self.assertEqual(self.themes_reasons(), ["transcript-changed"])
        self.add("data/p01.txt", "P01", "--replace")
        self.assertEqual(self.themes_reasons(), ["transcript-changed"])
        self.assertEqual(self.signoff()[0], 0)
        self.assertEqual(self.themes_reasons(), [])
        self.write("data/p02.txt", "P02: another voice.\n")
        self.add("data/p02.txt", "P02")
        self.assertEqual(self.themes_reasons(), ["transcript-added"])
        code, out = self.signoff()
        self.assertEqual((code, out["themes"]["state"]), (0, "current"))
        self.assertEqual(len(self.record("study/themes.json")["history"]), 3)

    def test_status_reports_all_three_with_warnings(self) -> None:
        self.signed()
        self.write("analysis/themes.md", "changed\n")
        code, out = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertEqual((out["transcripts"]["state"], out["codebook"]["state"], out["themes"]["state"]),
                         ("current", "current", "stale"))
        self.assertEqual([w["code"] for w in out["warnings"]], ["THEMES_STALE"])


class HelpTests(unittest.TestCase):
    def test_help_exits_zero(self) -> None:
        proc = subprocess.run([sys.executable, str(CLI), "--help"], capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0)
        for verb in ("transcripts", "codebook", "themes", "quotes", "status"):
            self.assertIn(verb, proc.stdout)

    def test_no_verb_is_a_usage_error(self) -> None:
        proc = subprocess.run([sys.executable, str(CLI)], capture_output=True, text=True, timeout=60)
        self.assertEqual((proc.returncode, json.loads(proc.stdout)["error"]), (2, "USAGE"))


if __name__ == "__main__":
    unittest.main()
