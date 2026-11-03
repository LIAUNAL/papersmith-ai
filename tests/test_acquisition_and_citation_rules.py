"""Writing rules from `odd/tasks/acquisition-diagram-citations-template.md`.

S1/S2: a real dataset's explanation closes on an acquisition-protocol diagram,
drawn by the `diagram-author` agent with domain pictograms, never boxes only.
The guide's own example, built from the shipped pictogram library, passes the
same mechanical audit every diagram meets.

S3: the experimental set-up backs its protocol decisions (comparison criteria,
preprocessing, partitions, hypothesis tests) with citations, so the training
details block runs under the resolution regime.

S4: results and discussion back interpretive explanations, baseline analyses
and qualitative-interpretability arguments with citations, never the paper's
own numbers.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REFS = REPO / "skills" / "paper-writing" / "references"
GUIDE = REFS / "data-acquisition-diagram.md"
LIBRARY = REFS / "pictograms.tex"
GUIDE_REL = "references/data-acquisition-diagram.md"
ES = REPO / "skills" / "_core" / "command_center" / "static" / "i18n" / "es" / "sections"
AGENT_COPIES = (".claude/agents/diagram-author.md", ".agents/agents/diagram-author.md",
                ".opencode/agents/diagram-author.md", ".pi/agents/diagram-author.md")
PICS = ("pg eeg patient", "pg seated subject", "pg amplifier", "pg stimulus screen",
        "pg signal traces", "pg computer", "pg database", "pg wind turbine",
        "pg generator", "pg electric machine", "pg sensor probe")

sys.path.insert(0, str(REPO / "skills" / "_core" / "figure"))
sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))
import diagram_audit  # noqa: E402
import paper_contract  # noqa: E402


def contract(name: str, es: bool = False) -> str:
    return ((ES if es else REPO / "sections") / name).read_text(encoding="utf-8")


def blocks(name: str) -> dict:
    header, _ = paper_contract.parse((REPO / "sections" / name).read_bytes())
    return {block["id"].split(".")[-1]: block for block in header.blocks}


def guide_example() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    match = re.search(r"## Example.*?```latex\n(.*?)```", text, re.S)
    assert match, "no latex example in the guide"
    return match.group(1).replace("% <pictograms>", LIBRARY.read_text(encoding="utf-8"))


def compile_tex(tex: str, tmp: Path) -> subprocess.CompletedProcess:
    (tmp / "fig.tex").write_text(tex, encoding="utf-8")
    return subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "fig.tex"],
                          cwd=tmp, capture_output=True, text=True, timeout=120)


class AcquisitionDiagramRuleTests(unittest.TestCase):
    def test_both_dataset_homes_close_on_the_acquisition_diagram(self) -> None:
        for name in ("01-materials-and-methods.md", "02-experimental-setup.md"):
            for es in (False, True):
                with self.subTest(name=name, es=es):
                    self.assertIn(GUIDE_REL, contract(name, es))
                    self.assertIn("pictograms.tex", contract(name, es))

    def test_a_missing_acquisition_diagram_is_a_disqualifier(self) -> None:
        for name in ("01-materials-and-methods.md", "02-experimental-setup.md"):
            with self.subTest(name=name):
                disqualifiers = contract(name).split("## Disqualifiers", 1)[1]
                self.assertIn("acquisition-protocol diagram", disqualifiers)

    def test_every_diagram_author_copy_loads_the_guide(self) -> None:
        for rel in AGENT_COPIES:
            with self.subTest(rel=rel):
                text = (REPO / rel).read_text(encoding="utf-8")
                self.assertIn("skills/paper-writing/" + GUIDE_REL, text)
                self.assertIn("pictograms.tex", text)

    def test_the_guide_requires_pictograms_and_names_the_library(self) -> None:
        text = GUIDE.read_text(encoding="utf-8")
        self.assertIn("at least two stages carry a pictogram", text)
        self.assertIn("never `\\input` the library", text)
        for pic in PICS:
            with self.subTest(pic=pic):
                self.assertIn(f"pics/{pic}/.style", LIBRARY.read_text(encoding="utf-8"))

    def test_the_example_manifest_markers_match(self) -> None:
        text = GUIDE.read_text(encoding="utf-8")
        manifest = json.loads(re.search(r"```json\n(.*?)```", text, re.S).group(1))
        markers = re.findall(r"% node: (.+)", guide_example())
        self.assertEqual(markers, manifest["components"])
        self.assertIsInstance(manifest["encodings"], list)


@unittest.skipUnless(shutil.which("pdflatex"), "pdflatex not installed")
class PictogramCompileTests(unittest.TestCase):
    def test_the_guide_example_passes_the_diagram_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tex = guide_example()
            run = compile_tex(tex, tmp)
            self.assertEqual(run.returncode, 0, run.stdout[-1500:])
            report = diagram_audit.audit_diagram(
                tmp / "fig.pdf", body_pt=11, printed_width_pt=453.5, tex_text=tex,
                log_text=(tmp / "fig.log").read_text(encoding="latin-1"))
            self.assertEqual(report["verdict"], "pass", diagram_audit.failure_messages(report))

    def test_every_pictogram_compiles_without_text(self) -> None:
        body = "".join(f"\\pic at ({2.2 * i},0) {{{pic}}};\n" for i, pic in enumerate(PICS))
        tex = ("\\documentclass[tikz,border=2pt]{standalone}\n\\begin{document}\n"
               + LIBRARY.read_text(encoding="utf-8")
               + "\\begin{tikzpicture}\n" + body + "\\end{tikzpicture}\n\\end{document}\n")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            run = compile_tex(tex, tmp)
            self.assertEqual(run.returncode, 0, run.stdout[-1500:])
            if shutil.which("pdftotext"):
                text = subprocess.run(["pdftotext", "fig.pdf", "-"], cwd=tmp,
                                      capture_output=True, text=True).stdout
                self.assertEqual(text.strip(), "")


class SetUpCitationTests(unittest.TestCase):
    def test_training_details_cite_under_the_resolution_regime(self) -> None:
        self.assertEqual(blocks("02-experimental-setup.md")["es-training-details"]["citations"],
                         "resolution")

    def test_the_set_up_requires_a_citation_per_protocol_decision(self) -> None:
        text = " ".join(contract("02-experimental-setup.md").split())
        assessment = text.split("### What is cited here", 1)[1].split("## Subsection 2", 1)[0]
        training = text.split("### What is cited in the training details", 1)[1].split("## ", 1)[0]
        for phrase in ("comparison criteria", "statistical test"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, assessment)
        for phrase in ("preprocessing", "partition protocol", "leakage control"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, training)


class DiscussionCitationTests(unittest.TestCase):
    def test_interpretive_claims_are_cited_never_the_papers_numbers(self) -> None:
        citations = " ".join(contract("03-results-and-discussion.md").split("## Citations", 1)[1]
                             .split("\n## ", 1)[0].split()).lower()
        for phrase in ("interpretive", "baseline", "qualitative", "never for a result"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, citations)
        self.assertNotIn("Almost none", citations)

    def test_an_uncited_interpretive_mechanism_is_a_disqualifier(self) -> None:
        disqualifiers = contract("03-results-and-discussion.md").split("## Disqualifiers", 1)[1]
        self.assertIn("without a citation", disqualifiers)


if __name__ == "__main__":
    unittest.main()
