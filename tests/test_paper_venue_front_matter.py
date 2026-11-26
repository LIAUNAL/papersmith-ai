"""paper-writing `venue build`: the front matter a class with its own author
machinery receives, the highlights environment, and the heading lines the
canonical file writes between blocks.

Stdlib-only `unittest`, synthetic manuscripts only. The shared scenario
builders live in `test_paper_venue.py`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_paper_venue import (  # noqa: E402
    PLAN_TEXT,
    VenueCase,
    block_bytes,
    canonical_tex,
    paper_venue,
)

#: The revealed-author template of `sections/09-title-and-keywords.md`.
MINIPAGE_AUTHOR = (
    "\\author{%\n"
    "\\begin{minipage}[t]{\\dimexpr\\textwidth-2\\tabcolsep\\relax}\n"
    "\\centering\n"
    "First Author$^{1}$, Second Author$^{1,2}$, and Third Author$^{3,*}$\\\\[1ex]\n"
    "\\small\n"
    "$^{1}$Departamento de Sistemas e Inform\\'{a}tica, Universidad de Caldas, Manizales 170004, Colombia\\\\\n"
    "$^{2}$Departamento de Electr\\'{o}nica, Universidad Aut\\'{o}noma de Manizales, Colombia\\\\\n"
    "$^{3}$AI-Lab, Universidad Nacional de Colombia, Sede Manizales, Colombia\\\\[1ex]\n"
    "E-mails: \\texttt{first.author@ucaldas.edu.co}, \\texttt{second.author@ucaldas.edu.co}, "
    "\\texttt{third.author@unal.edu.co}\\\\\n"
    "$^{*}$Corresponding author: \\texttt{third.author@unal.edu.co}\n"
    "\\end{minipage}}\n"
)

#: The same facts without the minipage: affiliations wrapped over two lines,
#: an ORCID line and a corresponding line that names the author.
PLAIN_AUTHOR = (
    "\\author{Ana Mar\\'{i}a P\\'{e}rez$^{1,*}$, Luis G\\'{o}mez-Ruiz$^{2}$, Eva Soto$^{1}$\\\\\n"
    "$^{1}$Laboratorio de Inteligencia Artificial and Signal Processing Group,\\\\\n"
    "Universidad Nacional de Colombia, Manizales, Colombia\\\\\n"
    "$^{2}$Departamento de Inform\\'{a}tica,\\\\\n"
    "Universidad Nacional de Colombia, Manizales, Colombia\\\\\n"
    "ORCID: G\\'{o}mez-Ruiz 0000-0003-0569-0605; Soto 0000-0003-0308-9576\\\\\n"
    "$^{*}$Corresponding author: Ana Mar\\'{i}a P\\'{e}rez, aperez@unal.edu.co}\n"
)

HIGHLIGHTS = (
    "\\paragraph{Highlights}\n\\begin{itemize}\n"
    "\\item A frozen network is read from the load alone.\n"
    "\\item A rule withholds the time constant when it is not carried.\n"
    "\\end{itemize}\n"
)

_BLOCK_RE = r"%% paper-writing block {id} begin sha256=[0-9a-f]{{64}}\n.*?%% paper-writing block {id} end\n"


def replace_block(text: str, block_id: str, body: str) -> str:
    pattern = re.compile(_BLOCK_RE.format(id=re.escape(block_id)), re.DOTALL)
    assert pattern.search(text), block_id
    return pattern.sub(lambda _m: block_bytes(block_id, body), text, count=1)


def with_author(author: str, **canonical) -> str:
    title = "\\title{A Hybrid Quantum Classical Network for EEG}\n" + author + "\\date{}\n"
    return replace_block(canonical_tex(**canonical), "title-and-keywords.title", title)


def with_highlights(text: str) -> str:
    """The highlights block between two declarations, as the back-matter
    skeleton places it."""
    anchor = "%% paper-writing block back-matter.bm-funding begin"
    return text.replace(anchor, block_bytes("back-matter.bm-highlights", HIGHLIGHTS) + anchor, 1)


def mapped_part(text: str) -> str:
    """The venue file after the `\\iffalse ... \\fi` copy of the canonical
    front-matter blocks."""
    return text.split("\\fi\n", 1)[1] if "\\iffalse" in text else text


class FrontMatterCase(VenueCase):
    def build_with(self, text: str, *, name: str = "elsarticle", slug: str = "eswa", ok: bool = True):
        self.write_canonical(text)
        changes = {"extras": []}
        if name != "elsarticle":
            changes["document_class"] = {"name": name, "options": [], "source": "generic",
                                         "quote": f"Use {name}.", "url": "https://example.org/g"}
        self.with_requirements(slug, **changes)
        self.with_template(slug, name)
        self.ok("diff", "--slug", slug, sections=True)
        digest = self.ok("plan", "--slug", slug, "--file", str(self.write_plan(PLAN_TEXT)))["plan_sha256"]
        self.ok("approve", "--slug", slug, "--statement", "ok", "--plan-sha256", digest)
        if not ok:
            return None
        self.ok("build", "--slug", slug)
        return (self.venue_dir(slug) / "main.tex").read_text(encoding="utf-8")


# =====================================================================
# the author-block reader
# =====================================================================
class AuthorBlockReaderTests(unittest.TestCase):
    def test_the_revealed_minipage_template_parses(self) -> None:
        parsed = paper_venue.parse_author_block(MINIPAGE_AUTHOR)
        self.assertEqual([a["name"] for a in parsed["authors"]], ["First Author", "Second Author", "Third Author"])
        self.assertEqual([a["affiliations"] for a in parsed["authors"]], [["1"], ["1", "2"], ["3"]])
        self.assertEqual([a["corresponding"] for a in parsed["authors"]], [False, False, True])
        self.assertEqual([a["email"] for a in parsed["authors"]],
                         ["first.author@ucaldas.edu.co", "second.author@ucaldas.edu.co", "third.author@unal.edu.co"])
        self.assertEqual([a["orcid"] for a in parsed["authors"]], [None, None, None])
        self.assertEqual([f["index"] for f in parsed["affiliations"]], ["1", "2", "3"])
        self.assertTrue(parsed["affiliations"][0]["text"].startswith("Departamento de Sistemas e Inform\\'{a}tica"))
        self.assertNotIn("minipage", json.dumps(parsed))

    def test_the_plain_form_joins_wrapped_affiliations_and_reads_orcid_and_corresponding(self) -> None:
        parsed = paper_venue.parse_author_block(PLAIN_AUTHOR)
        authors = parsed["authors"]
        self.assertEqual([a["name"] for a in authors],
                         ["Ana Mar\\'{i}a P\\'{e}rez", "Luis G\\'{o}mez-Ruiz", "Eva Soto"])
        self.assertEqual([a["corresponding"] for a in authors], [True, False, False])
        self.assertEqual([a["email"] for a in authors], ["aperez@unal.edu.co", None, None])
        self.assertEqual([a["orcid"] for a in authors], [None, "0000-0003-0569-0605", "0000-0003-0308-9576"])
        self.assertEqual(parsed["affiliations"][0]["text"],
                         "Laboratorio de Inteligencia Artificial and Signal Processing Group, "
                         "Universidad Nacional de Colombia, Manizales, Colombia")
        self.assertEqual(len(parsed["affiliations"]), 2)

    def test_the_simple_and_blinded_forms_still_parse(self) -> None:
        simple = paper_venue.parse_author_block(
            "\\author{\n    \\textbf{Ada Lovelace}$^{1,*}$ \\\\\n    $^{1}$Analytical Engine Lab \\\\\n"
            "    $^{*}$Corresponding author\n}\n")
        self.assertEqual(simple["authors"][0]["name"], "Ada Lovelace")
        self.assertTrue(simple["authors"][0]["corresponding"])
        self.assertEqual(simple["affiliations"], [{"index": "1", "text": "Analytical Engine Lab"}])
        blinded = paper_venue.parse_author_block(
            "\\author{Author names withheld \\\\ \\textit{Affiliations and contact e-mails to be provided}}")
        self.assertEqual([a["name"] for a in blinded["authors"]], ["Author names withheld"])
        self.assertEqual(blinded["affiliations"],
                         [{"index": None, "text": "Affiliations and contact e-mails to be provided"}])
        self.assertIsNone(paper_venue.parse_author_block("\\title{No author here}"))

    def test_an_unreadable_author_block_refuses_by_name(self) -> None:
        cases = {
            "unknown marker": "\\author{A$^{1,\\dagger}$ \\\\ $^{1}$Lab}",
            "undefined index": "\\author{A$^{1}$, B$^{2}$ \\\\ $^{1}$Lab}",
            "unclosed minipage": "\\author{\\begin{minipage}{\\textwidth} A \\\\ Lab}",
            "inner environment": "\\author{\\begin{tabular}{c} A \\\\ Lab \\end{tabular}}",
            "e-mails that do not match the authors": "\\author{A$^{1}$, B$^{1}$ \\\\ $^{1}$Lab \\\\ "
                                                     "E-mails: a@x.org, b@x.org, c@x.org}",
            "an ORCID no author carries": "\\author{A Bee$^{1}$ \\\\ $^{1}$Lab \\\\ ORCID: Zed 0000-0003-0569-0605}",
        }
        for label, tex in cases.items():
            with self.subTest(label):
                with self.assertRaises(paper_venue.Refused) as ctx:
                    paper_venue.parse_author_block(tex)
                self.assertEqual(ctx.exception.code, "TITLE_BLOCK_UNPARSEABLE")


# =====================================================================
# build
# =====================================================================
class ElsarticleFrontMatterTests(FrontMatterCase):
    def test_the_minipage_template_maps_to_elsarticle_author_commands(self) -> None:
        text = self.build_with(with_author(MINIPAGE_AUTHOR))
        mapped = mapped_part(text)
        self.assertNotIn("minipage", mapped, "the minipage must never be split across commands")
        front = mapped.split("\\begin{frontmatter}", 1)[1].split("\\end{frontmatter}", 1)[0]
        for needle in (
            "\\author[aff1]{First Author}\n\\ead{first.author@ucaldas.edu.co}\n",
            "\\author[aff1,aff2]{Second Author}\n\\ead{second.author@ucaldas.edu.co}\n",
            "\\author[aff3]{Third Author\\corref{cor1}}\n\\ead{third.author@unal.edu.co}\n",
            "\\cortext[cor1]{Corresponding author.}\n",
            "\\address[aff1]{Departamento de Sistemas e Inform\\'{a}tica, Universidad de Caldas, "
            "Manizales 170004, Colombia}\n",
            "\\address[aff3]{AI-Lab, Universidad Nacional de Colombia, Sede Manizales, Colombia}\n",
        ):
            self.assertIn(needle, front)
        self.assertNotIn("E-mails", front)
        self.assertNotIn("Corresponding author:", front)
        # the canonical block still travels verbatim inside \iffalse
        self.assertIn("\\begin{minipage}", text.split("\\fi\n", 1)[0])

    def test_the_plain_form_maps_orcid_and_corresponding_into_class_commands(self) -> None:
        text = self.build_with(with_author(PLAIN_AUTHOR))
        front = mapped_part(text).split("\\begin{frontmatter}", 1)[1].split("\\end{frontmatter}", 1)[0]
        self.assertIn("\\author[aff1]{Ana Mar\\'{i}a P\\'{e}rez\\corref{cor1}}\n\\ead{aperez@unal.edu.co}\n", front)
        self.assertIn("\\author[aff2]{Luis G\\'{o}mez-Ruiz\\fnref{orcid2}}\n", front)
        self.assertIn("\\fntext[orcid2]{ORCID: 0000-0003-0569-0605}\n", front)
        self.assertIn("\\fntext[orcid3]{ORCID: 0000-0003-0308-9576}\n", front)
        self.assertIn("\\address[aff1]{Laboratorio de Inteligencia Artificial and Signal Processing Group, "
                      "Universidad Nacional de Colombia, Manizales, Colombia}\n", front)
        addresses = re.findall(r"\\address\[[^\]]*\]\{[^\n]*\}", front)
        self.assertEqual(len(addresses), 2)
        self.assertFalse(any("ORCID" in a or "Corresponding" in a or "@" in a for a in addresses), addresses)

    def test_highlights_land_in_the_highlights_environment_inside_the_front_matter(self) -> None:
        text = self.build_with(with_highlights(with_author(MINIPAGE_AUTHOR)))
        mapped = mapped_part(text)
        front = mapped.split("\\begin{frontmatter}", 1)[1].split("\\end{frontmatter}", 1)[0]
        self.assertIn("\\begin{highlights}\n"
                      "\\item A frozen network is read from the load alone.\n"
                      "\\item A rule withholds the time constant when it is not carried.\n"
                      "\\end{highlights}\n", front)
        self.assertLess(front.index("\\end{abstract}"), front.index("\\begin{highlights}"))
        self.assertLess(front.index("\\end{highlights}"), front.index("\\begin{keyword}"))
        declarations = mapped.split("\\section*{Declarations}", 1)[1]
        self.assertNotIn("Highlights", declarations)
        self.assertNotIn("bm-highlights", declarations)
        # the canonical block travels once, verbatim, inside \iffalse
        self.assertEqual(text.count("back-matter.bm-highlights begin"), 1)
        self.assertLess(text.index("back-matter.bm-highlights begin"), text.index("\\fi\n"))
        self.assertIn("back-matter.bm-funding begin", declarations)

    def test_an_unparseable_title_block_refuses_and_writes_nothing(self) -> None:
        self.build_with(with_author("\\author{A$^{1,\\dagger}$ \\\\ $^{1}$Lab}\n"), ok=False)
        payload = self.refused("build", "TITLE_BLOCK_UNPARSEABLE", "--slug", "eswa")
        self.assertIn("\\dagger", payload["detail"])
        self.assertFalse((self.venue_dir() / "main.tex").exists())


    def test_highlights_without_an_itemize_refuse_and_write_nothing(self) -> None:
        text = with_highlights(with_author(MINIPAGE_AUTHOR)).replace(
            HIGHLIGHTS, "Highlights written as one plain paragraph.\n")
        text = replace_block(text, "back-matter.bm-highlights", "Highlights written as one plain paragraph.\n")
        self.build_with(text, ok=False)
        self.refused("build", "HIGHLIGHTS_UNPARSEABLE", "--slug", "eswa")
        self.assertFalse((self.venue_dir() / "main.tex").exists())

class GenericFrontMatterTests(FrontMatterCase):
    def test_article_keeps_the_minipage_and_the_highlights_among_the_declarations(self) -> None:
        text = self.build_with(with_highlights(with_author(MINIPAGE_AUTHOR)), name="article")
        self.assertIn("\\begin{minipage}[t]{\\dimexpr\\textwidth-2\\tabcolsep\\relax}", text)
        self.assertIn("\\end{minipage}}", text)
        self.assertNotIn("\\begin{highlights}", text)
        self.assertNotIn("\\iffalse", text)
        declarations = text.split("\\section*{Declarations}", 1)[1]
        self.assertIn("\\paragraph{Highlights}", declarations)

    def test_an_unreadable_author_block_is_kept_verbatim_by_article(self) -> None:
        author = "\\author{A$^{1,\\dagger}$ \\\\ $^{1}$Lab}\n"
        text = self.build_with(with_author(author), name="article")
        self.assertIn(author, text)


class OtherClassFrontMatterTests(FrontMatterCase):
    def test_ieeetran_and_llncs_never_split_the_minipage(self) -> None:
        for name, needles in (
            ("IEEEtran", ["\\IEEEauthorblockN{First Author\\textsuperscript{1}, Second Author\\textsuperscript{1,2}, "
                          "and Third Author\\textsuperscript{3,*}}"]),
            ("llncs", ["\\author{First Author\\inst{1} \\and Second Author\\inst{1,2} \\and "
                       "Third Author\\inst{3}\\thanks{Corresponding author.}}", "\\institute{"]),
        ):
            with self.subTest(name):
                text = self.build_with(with_author(MINIPAGE_AUTHOR), name=name, slug=name.lower())
                self.assertNotIn("minipage", mapped_part(text))
                for needle in needles:
                    self.assertIn(needle, text)


# =====================================================================
# heading lines written between blocks
# =====================================================================
class HeadingLineTests(FrontMatterCase):
    def setUp(self) -> None:
        super().setUp()
        header = {"section": "limitations", "position": 7,
                  "blocks": [{"id": "lim-opening", "requires_facts": [], "requires_declarations": [],
                              "citations": "none"}]}
        (self.sections / "04-limitations.md").write_text(
            "---\n" + json.dumps(header, indent=2) + "\n---\n# limitations\n\nProse.\n", encoding="utf-8")

    def canonical_with_limitations(self) -> str:
        text = canonical_tex()
        anchor = "\n\\section{Conclusions}"
        limitations = ("\\subsection{Limitations}\\label{sec:limitations}\n"
                       + block_bytes("limitations.lim-opening", "The method needs a long record.\n"))
        return text.replace(anchor, "\n" + limitations + anchor, 1)

    def test_a_subsection_heading_between_blocks_is_kept_in_place(self) -> None:
        text = self.build_with(self.canonical_with_limitations())
        self.assertEqual(text.count("\\subsection{Limitations}\\label{sec:limitations}\n"), 1)
        self.assertNotIn("\\section{Limitations}", text)
        self.assertLess(text.index("\\section{Results and discussion}"), text.index("\\subsection{Limitations}"))
        self.assertLess(text.index("\\subsection{Limitations}"), text.index("limitations.lim-opening begin"))
        self.assertLess(text.index("limitations.lim-opening end"), text.index("\\section{Conclusions}"))

    def test_section_headings_are_still_retitled_by_the_venue(self) -> None:
        text = self.build_with(canonical_tex())
        headings = [line for line in text.splitlines() if line.startswith("\\section")]
        self.assertEqual(headings[:2], ["\\section{Introduction}\\label{sec:intro}",
                                        "\\section{Material and methods}\\label{sec:methods}"])


# =====================================================================
# the real toolchain
# =====================================================================
def _tex_bin(name: str) -> str | None:
    kpsewhich = paper_venue.paper_latex.discover_kpsewhich()
    if kpsewhich is None:
        return None
    sibling = Path(kpsewhich).parent / name
    return str(sibling) if sibling.is_file() else shutil.which(name)


def _elsarticle_cls() -> str | None:
    kpsewhich = paper_venue.paper_latex.discover_kpsewhich()
    if kpsewhich is None:
        return None
    proc = subprocess.run([kpsewhich, "elsarticle.cls"], capture_output=True, text=True)
    found = proc.stdout.strip()
    return found if proc.returncode == 0 and found else None


@unittest.skipUnless(_tex_bin("pdflatex") and _elsarticle_cls(),
                     "needs pdflatex and an elsarticle.cls kpsewhich can find (TEXINPUTS counts)")
class FrontMatterCompileTests(FrontMatterCase):
    def test_the_built_elsarticle_front_matter_compiles(self) -> None:
        text = self.build_with(with_highlights(with_author(PLAIN_AUTHOR)))
        self.assertIn("\\begin{highlights}", text)
        directory = self.venue_dir()
        env = dict(os.environ, openout_any="p", shell_escape="f")
        for _ in range(2):
            proc = subprocess.run([_tex_bin("pdflatex"), "-interaction=nonstopmode", "-file-line-error",
                                   "main.tex"], cwd=str(directory), env=env, capture_output=True,
                                  text=True, timeout=240)
            self.assertEqual(proc.returncode, 0, proc.stdout[-2000:])
        self.assertTrue((directory / "main.pdf").is_file())
        log = (directory / "main.log").read_text(errors="replace")
        self.assertNotIn("! ", log)


if __name__ == "__main__":
    unittest.main()
