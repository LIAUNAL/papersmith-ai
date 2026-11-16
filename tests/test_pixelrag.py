"""pixelrag: an ingested figure becomes a description usable as evidence (#13).

Keyless and local (decision L8 of odd/tasks/daprosero-backlog.md): the CLI computes
deterministic facts about an image `paper-ingestion` extracted, validates the
description the session's own agent writes from looking at it, and stores it with
provenance. Every case runs through the CLI on a copy of a tiny ingested paper.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "pixelrag" / "scripts" / "pixelrag_cli.py"
FIXTURE = ROOT / "tests" / "fixtures" / "pixelrag" / "demo"
CAPTIONED = "_page_0_Figure_1.png"
UNCAPTIONED = "_page_1_Figure_0.png"
GOOD = ("Line plot of training loss against epoch, three curves, one per learning rate; "
        "the y-axis is loss from 0 to 2.5, every curve decreases and flattens after epoch 20.")


class PixelragTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        self.paper = self.root / "guidance" / "topic" / "demo"
        shutil.copytree(FIXTURE, self.paper)

    def run_cli(self, *args: str) -> tuple[int, dict]:
        done = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                              cwd=self.root, timeout=60)
        self.assertNotIn("Traceback", done.stderr)
        lines = [line for line in done.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, done.stdout)
        return done.returncode, json.loads(lines[0])

    def figure(self, name: str = CAPTIONED) -> Path:
        return self.paper / name

    def sha(self, name: str = CAPTIONED) -> str:
        return hashlib.sha256(self.figure(name).read_bytes()).hexdigest()

    def record(self, *extra: str, name: str = CAPTIONED, description: str = GOOD) -> tuple[int, dict]:
        return self.run_cli("record", "--figure", str(self.figure(name)), "--sha256", self.sha(name),
                            "--description", description, *extra)

    # facts ---------------------------------------------------------------

    def test_facts_reports_the_image_and_what_ingestion_wrote_around_it(self) -> None:
        code, out = self.run_cli("facts", "--figure", str(self.figure()))
        self.assertEqual(code, 0, out)
        self.assertTrue(out["ok"])
        facts = out["facts"]
        self.assertEqual(facts["path"], f"guidance/topic/demo/{CAPTIONED}")
        self.assertEqual(facts["sha256"], self.sha())
        self.assertEqual(facts["width"], 4)
        self.assertEqual(facts["height"], 3)
        self.assertEqual(facts["format"], "png")
        self.assertEqual(facts["markdown"], "guidance/topic/demo/demo.md")
        self.assertEqual(facts["label"], "Figure 3")
        self.assertEqual(facts["number"], "3")
        self.assertEqual(facts["caption"], "Figure 3: Training loss versus epoch for the three learning rates.")
        self.assertEqual(facts["page"], 1)
        self.assertIn("converges after twenty epochs", facts["nearby_text"]["before"])
        self.assertIn("validation curve", facts["nearby_text"]["after"])
        self.assertTrue(facts["text_layer"]["available"])
        self.assertIsNone(facts["in_image_text"])
        self.assertIn("no OCR", facts["in_image_text_note"])

    def test_facts_on_a_figure_without_a_caption_says_so(self) -> None:
        code, out = self.run_cli("facts", "--figure", str(self.figure(UNCAPTIONED)))
        self.assertEqual(code, 0, out)
        facts = out["facts"]
        self.assertIsNone(facts["caption"])
        self.assertIsNone(facts["number"])
        self.assertEqual((facts["width"], facts["height"]), (2, 5))
        self.assertEqual(facts["page"], 2)

    def test_prose_that_names_a_figure_is_not_its_caption(self) -> None:
        # Review finding R3-caption-heuristic: "Fig. 5 compares ..." is body text, not a caption.
        md = self.paper / "demo.md"
        md.write_text(md.read_text(encoding="utf-8").replace(
            "Removing the attention block", "Fig. 5 compares it with Fig. 3, and removing the attention block"),
            encoding="utf-8")
        code, out = self.run_cli("facts", "--figure", str(self.figure(UNCAPTIONED)))
        self.assertEqual(code, 0, out)
        self.assertIsNone(out["facts"]["caption"])
        self.assertIsNone(out["facts"]["number"])

    def test_facts_reports_an_unavailable_text_layer(self) -> None:
        sidecar = self.paper / "demo.json"
        data = json.loads(sidecar.read_text())
        data["pages"][0]["md_end"] = data["pages"][0]["md_start"]
        sidecar.write_text(json.dumps(data))
        (self.paper / "demo.md").write_text("<!-- page 1 -->\n![](_page_0_Figure_1.png)\n")
        code, out = self.run_cli("facts", "--figure", str(self.figure()))
        self.assertEqual(code, 0, out)
        self.assertFalse(out["facts"]["text_layer"]["available"])
        self.assertIn("no text", out["facts"]["text_layer"]["note"])

    # record --------------------------------------------------------------

    def test_record_writes_the_sidecar_with_provenance(self) -> None:
        code, out = self.record()
        self.assertEqual(code, 0, out)
        self.assertEqual(out["sidecar"], "written")
        stored = json.loads((self.paper / f"{CAPTIONED}.pixelrag.json").read_text())
        self.assertEqual(stored["tool"], "pixelrag")
        self.assertEqual(stored["image"], CAPTIONED)
        self.assertEqual(stored["sha256"], self.sha())
        self.assertEqual(stored["description"], GOOD)
        self.assertEqual(stored["facts"]["label"], "Figure 3")
        self.assertTrue(stored["recorded_at"].endswith("Z"))
        # The Markdown is untouched unless asked.
        self.assertNotIn("pixelrag", (self.paper / "demo.md").read_text())
        self.assertEqual(self.record()[1]["sidecar"], "unchanged")

    def test_record_reads_the_description_from_a_file(self) -> None:
        source = self.root / "desc.txt"
        source.write_text(GOOD + "\n")
        code, out = self.record(description=f"@{source}")
        self.assertEqual(code, 0, out)
        stored = json.loads((self.paper / f"{CAPTIONED}.pixelrag.json").read_text())
        self.assertEqual(stored["description"], GOOD)

    def test_record_markdown_block_is_idempotent_and_keeps_the_page_map_true(self) -> None:
        original = (self.paper / "demo.md").read_text()
        code, out = self.record("--markdown")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["markdown"], "written")
        once = (self.paper / "demo.md").read_text()
        block_at = once.index("<!-- pixelrag:begin _page_0_Figure_1.png")
        self.assertEqual(block_at, once.index("![](_page_0_Figure_1.png)") + len("![](_page_0_Figure_1.png)\n\n"))
        self.assertIn("> " + GOOD[:40], once)
        self.assertEqual(self.record("--markdown")[1]["markdown"], "unchanged")
        self.assertEqual((self.paper / "demo.md").read_text(), once)
        self.assertEqual(once.count("pixelrag:begin"), 1)
        # A new description replaces the block in place, never appends a second one.
        other = GOOD.replace("three curves", "3 curves")
        self.assertEqual(self.record("--markdown", description=other)[1]["markdown"], "written")
        twice = (self.paper / "demo.md").read_text()
        self.assertEqual(twice.count("pixelrag:begin"), 1)
        self.assertIn("3 curves", twice)
        # facts still reads the caption past the block.
        self.assertEqual(self.run_cli("facts", "--figure", str(self.figure()))[1]["facts"]["number"], "3")
        # The ingestion map's offsets still point at what they named.
        sidecar = json.loads((self.paper / "demo.json").read_text())
        self.assertEqual(sidecar["markdown"]["chars"], len(twice))
        for entry in sidecar["figures"]:
            self.assertTrue(twice[entry["md_offset"]:].startswith(f"![]({entry['file']})"))
        for entry in sidecar["headings"]:
            self.assertTrue(twice[entry["md_offset"]:].startswith("#"))
        self.assertEqual(sidecar["pages"][0]["md_end"], twice.index("<!-- page 2 -->"))
        self.assertEqual(sidecar["pages"][1]["md_start"], twice.index("<!-- page 2 -->") + len("<!-- page 2 -->"))
        self.assertEqual(sidecar["pages"][1]["md_end"], len(twice))
        self.assertNotEqual(original, twice)

    # refusals ------------------------------------------------------------

    def assert_refused(self, result: tuple[int, dict], code: str) -> None:
        exit_code, out = result
        self.assertEqual(exit_code, 2, out)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], code)
        self.assertTrue(out["message"])
        self.assertFalse((self.paper / f"{CAPTIONED}.pixelrag.json").exists())

    def test_refuses_an_empty_or_short_or_long_description(self) -> None:
        self.assert_refused(self.record(description="   "), "DESCRIPTION_EMPTY")
        self.assert_refused(self.record(description="A plot."), "DESCRIPTION_TOO_SHORT")
        self.assert_refused(self.record(description="x " * 3000), "DESCRIPTION_TOO_LONG")

    def test_refuses_a_figure_number_the_caption_contradicts(self) -> None:
        self.assert_refused(self.record(description="Figure 4 shows " + GOOD), "FIGURE_NUMBER_MISMATCH")
        code, out = self.record(description="Figure 3 shows " + GOOD)
        self.assertEqual(code, 0, out)

    def test_refuses_speculation_and_markup(self) -> None:
        self.assert_refused(self.record(description=GOOD + " This probably means the model overfits."),
                            "DESCRIPTION_SPECULATIVE")
        self.assert_refused(self.record(description=GOOD + " <!-- page 9 -->"), "DESCRIPTION_MARKUP")

    def test_a_non_utf8_description_file_is_a_json_refusal(self) -> None:
        # Review finding R3-non-utf8-traceback.
        bad = self.root / "bad.txt"
        bad.write_bytes(b"\xff\xfe not utf-8 \x80\x81 at all, and long enough to pass the length bound")
        self.assert_refused(self.record(description=f"@{bad}"), "DESCRIPTION_UNREADABLE")

    def test_record_markdown_leaves_no_temporary_file(self) -> None:
        # Review finding R1-001: writes go through a temporary file replaced in one step.
        code, out = self.record("--markdown")
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(p.name for p in self.paper.glob(".*pixelrag-tmp")), [])

    def test_refuses_an_image_changed_since_facts(self) -> None:
        stale = self.sha()
        self.figure().write_bytes(self.figure().read_bytes() + b"\x00")
        self.assert_refused(self.run_cli("record", "--figure", str(self.figure()), "--sha256", stale,
                                         "--description", GOOD), "IMAGE_CHANGED")

    def test_refuses_what_is_not_an_ingested_figure(self) -> None:
        self.assert_refused(self.run_cli("facts", "--figure", str(self.paper / "missing.png")), "FIGURE_NOT_FOUND")
        self.assert_refused(self.run_cli("facts", "--figure", str(self.paper / "demo.md")), "NOT_AN_IMAGE")
        loose = self.root / "loose.png"
        shutil.copy(self.figure(), loose)
        self.assert_refused(self.run_cli("facts", "--figure", str(loose)), "NOT_INGESTED")
        self.assert_refused(self.run_cli("status", "--paper", str(self.root / "nowhere")), "PAPER_NOT_FOUND")

    # status --------------------------------------------------------------

    def test_status_names_current_missing_and_stale_figures(self) -> None:
        code, out = self.run_cli("status", "--paper", str(self.paper))
        self.assertEqual(code, 0, out)
        self.assertEqual(out["missing"], [CAPTIONED, UNCAPTIONED])
        self.assertEqual(out["current"], [])
        self.assertEqual(self.record("--markdown")[0], 0)
        self.assertEqual(self.record(name=UNCAPTIONED)[0], 0)
        code, out = self.run_cli("status", "--paper", str(self.paper))
        self.assertEqual((out["current"], out["missing"], out["stale"]), ([CAPTIONED, UNCAPTIONED], [], []))
        rows = {row["image"]: row for row in out["figures"]}
        self.assertEqual(rows[CAPTIONED]["markdown_block"], "current")
        self.assertEqual(rows[UNCAPTIONED]["markdown_block"], "absent")
        self.figure(UNCAPTIONED).write_bytes(self.figure(UNCAPTIONED).read_bytes() + b"\x00")
        code, out = self.run_cli("status", "--paper", str(self.paper))
        self.assertEqual(out["stale"], [UNCAPTIONED])
        self.assertEqual(out["current"], [CAPTIONED])


if __name__ == "__main__":
    unittest.main()
