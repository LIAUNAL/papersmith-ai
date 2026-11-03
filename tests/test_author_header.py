"""The revealed author header never overflows the text block.

When blinding is lifted, the title contract prescribes one author-header
template. ``article``'s ``\\author`` sets its argument in a ``c`` column, so a
bare ``\\\\``-separated affiliation line wider than the text block never
wraps and runs into the margin. The template wraps everything in a
``minipage`` of the column width, so long affiliations and e-mail lists break
like ordinary text. These tests read the template from the contract itself and
compile it against the longest real-world affiliations we have seen.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "sections" / "09-title-and-keywords.md"
TEMPLATE_SURFACES = (
    "sections/09-title-and-keywords.md",
    "skills/paper-writing/SKILL.md",
    "skills/_core/command_center/static/i18n/es/sections/09-title-and-keywords.md",
)
HEADINGS = ("### Revealed Author Metadata", "### Metadatos de autoría revelados")

PREAMBLE = (
    "\\documentclass[11pt,onecolumn,a4paper]{article}\n"
    "\\usepackage[utf8]{inputenc}\n"
    "\\usepackage{geometry}\n"
    "\\geometry{top=2.5cm,bottom=2.5cm,left=2.5cm,right=2.5cm}\n"
    "\\title{A Title}\n"
)
BODY = "\\begin{document}\n\\maketitle\n\\end{document}\n"

LONG_NAIVE_AUTHOR = (
    "\\author{First Author$^{1}$, Second Author$^{2}$ \\\\\n"
    "$^{1}$Departamento de Electr\\'{o}nica y Automatizaci\\'{o}n, Universidad Aut\\'{o}noma de "
    "Manizales, Manizales 170001, Colombia \\\\\n"
    "$^{2}$AI-Lab, Signal Processing and Recognition Group, Universidad Nacional de Colombia, "
    "Sede Manizales, Manizales 170003, Colombia}\n"
)


def contract_template(path: Path = CONTRACT) -> str:
    """The first ```latex block after the revealed-metadata heading."""
    text = path.read_text(encoding="utf-8")
    starts = [text.index(h) for h in HEADINGS if h in text]
    if not starts:
        raise AssertionError(f"no revealed-metadata heading in {path}")
    start = starts[0]
    match = re.search(r"```latex\n(.*?)```", text[start:], re.S)
    if match is None:
        raise AssertionError(f"no latex block under the revealed-metadata heading in {path}")
    return match.group(1)


def overfull_lines(author_block: str) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        tex = Path(tmp) / "main.tex"
        tex.write_text(PREAMBLE + author_block + BODY, encoding="utf-8")
        run = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
            cwd=tmp, capture_output=True, text=True, timeout=120,
        )
        log = (Path(tmp) / "main.log").read_text(encoding="latin-1")
        if run.returncode != 0:
            raise AssertionError(f"pdflatex failed:\n{log[-2000:]}")
        return [line for line in log.splitlines() if line.startswith("Overfull \\hbox")]


class TemplateIsPrescribedTests(unittest.TestCase):
    def test_every_surface_prescribes_the_same_wrapping_template(self) -> None:
        reference = contract_template()
        self.assertIn("\\begin{minipage}[t]{\\dimexpr\\textwidth-2\\tabcolsep\\relax}", reference)
        self.assertNotIn("\\par", reference)  # \author is not \long: \par aborts the preamble
        for rel in TEMPLATE_SURFACES:
            with self.subTest(rel=rel):
                self.assertEqual(contract_template(REPO / rel), reference)


@unittest.skipUnless(shutil.which("pdflatex"), "pdflatex not installed")
class TemplateCompilesWithoutOverflowTests(unittest.TestCase):
    def test_the_naive_backslash_form_overflows(self) -> None:
        self.assertTrue(overfull_lines(LONG_NAIVE_AUTHOR))

    def test_the_contract_template_with_long_affiliations_does_not_overflow(self) -> None:
        self.assertEqual(overfull_lines(contract_template()), [])


if __name__ == "__main__":
    unittest.main()
