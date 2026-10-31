"""`paper_cli.py venue ...` -- adapting the manuscript to a chosen journal.

Every verb is exercised through the real front door (`paper_cli.main`, plus a
couple of real subprocesses for the exit code), on a scratch repository tree
under the already-gitignored `.scratch/`. Each refusal test also proves the
refusal wrote nothing: the whole scratch tree is hashed before and after.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from unittest import mock

FORGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
CLI = SCRIPTS / "paper_cli.py"
FIXTURES = FORGE_ROOT / "tests" / "fixtures" / "paper_venue"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
import paper_block  # noqa: E402
import paper_cli  # noqa: E402
import paper_venue  # noqa: E402

_COUNTER = [0]

SECTION_TITLES = {
    "introduction": "Introduction",
    "related-work": "Related Work",
    "materials-and-methods": "Materials and Methods",
    "results-and-discussion": "Results and Discussion",
    "conclusions": "Conclusions",
}

#: `(section id, position, file number, block ids, **Extent** line or None)`
CONTRACTS = (
    ("title-and-keywords", 1, "09", ["title", "keywords"], "**Extent** title 10–13 words · keywords 4–8"),
    ("abstract", 2, "08", ["slot-1", "slot-2"], "**Extent** 216–280 words · 7–14 sentences · **one paragraph**"),
    ("introduction", 3, "06", ["block-1"], "**Extent** 900–1650 words · 7–13 paragraphs"),
    ("related-work", 4, "05", ["rw-preamble"], "**Extent** 820–1700 words"),
    ("materials-and-methods", 5, "01", ["mm-preamble"], "**Extent** 560–3950 words · 2 to 5 subsections"),
    ("results-and-discussion", 6, "03", ["rd-general-task"], "**Extent** 1170–4150 words"),
    ("conclusions", 7, "07", ["concl-block-1"], "**Extent** 375–500 words · 3 or 4 paragraphs"),
    ("back-matter", 8, "10", ["bm-author-contributions", "bm-funding", "bm-data-availability",
                              "bm-conflicts-of-interest"], None),
)


def words(count: int) -> str:
    return " ".join(["word"] * count)


def block_bytes(block_id: str, body: str) -> str:
    if body and not body.endswith("\n"):
        body += "\n"
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return (
        f"%% paper-writing block {block_id} begin sha256={digest}\n{body}"
        f"%% paper-writing block {block_id} end\n"
    )


def canonical_tex(
    *,
    title: str = "\\Large\\textbf{A Hybrid Quantum Classical Network for EEG}",
    abstract_words: int = 200,
    keywords: tuple = ("alpha", "beta", "gamma", "delta", "epsilon"),
    intro_words: int = 80,
    related: bool = False,
    methods_words: int = 60,
    results_words: int = 60,
    conclusion_words: int = 40,
    declarations: tuple = ("author-contributions", "funding"),
    documentclass: str = "\\documentclass[10pt,twocolumn,a4paper]{article}",
    bibstyle: str = "ieeetr",
    results_extra: str = "",
) -> str:
    half = abstract_words // 2
    parts = [
        documentclass + "\n",
        "\\usepackage[utf8]{inputenc}\n\\usepackage{amsmath,amssymb}\n\\usepackage{graphicx}\n"
        "\\usepackage{cite}\n\\usepackage{geometry}\n\\geometry{top=2cm,bottom=2cm}\n"
        "\\usepackage{hyperref}\n\\hypersetup{\n    colorlinks=true,\n    linkcolor=blue\n}\n\n",
        block_bytes(
            "title-and-keywords.title",
            f"\\title{{{title}}}\n\\author{{\n    \\textbf{{Ada Lovelace}}$^{{1,*}}$ \\\\\n"
            "    $^{1}$Analytical Engine Lab \\\\\n    $^{*}$Corresponding author\n}\n\\date{\\today}\n",
        ),
        "\\begin{document}\n\\maketitle\n\n\\begin{abstract}\n",
        block_bytes("abstract.slot-1", words(half) + ".\n"),
        block_bytes("abstract.slot-2", words(abstract_words - half) + ".\n"),
        "\n",
        block_bytes("title-and-keywords.keywords",
                    "\\textbf{Keywords:} " + ", ".join(keywords) + ".\n"),
        "\\end{abstract}\n\n",
        "\\section{Introduction}\\label{sec:intro}\n",
        block_bytes("introduction.block-1", words(intro_words) + ".\n"),
        "\n",
    ]
    if related:
        parts += ["\\section{Related Work}\\label{sec:rw}\n",
                  block_bytes("related-work.rw-preamble", words(50) + ".\n"), "\n"]
    parts += [
        "\\section{Materials and Methods}\\label{sec:methods}\n",
        block_bytes("materials-and-methods.mm-preamble", words(methods_words) + ". \\cite{ref1,ref2}\n"),
        "\n\\section{Results and Discussion}\\label{sec:results}\n",
        block_bytes("results-and-discussion.rd-general-task",
                    words(results_words) + ".\n" + results_extra),
        "\n\\section{Conclusions}\\label{sec:conclusions}\n",
        block_bytes("conclusions.concl-block-1", words(conclusion_words) + ".\n"),
        f"\n\\bibliographystyle{{{bibstyle}}}\n\\bibliography{{refs}}\n\n",
        "\\section*{Declarations}\n",
    ]
    texts = {
        "author-contributions": ("bm-author-contributions", "\\textbf{Author Contributions:} A.L.: everything.\n"),
        "funding": ("bm-funding", "\\textbf{Funding:} No funding.\n"),
        "data-availability": ("bm-data-availability", "\\textbf{Data Availability:} On request.\n"),
        "conflicts": ("bm-conflicts-of-interest", "\\textbf{Conflicts of Interest:} None.\n"),
        "acknowledgments": ("bm-acknowledgments", "\\textbf{Acknowledgments:} Thanks.\n"),
    }
    for name in declarations:
        block_id, text = texts[name]
        parts.append(block_bytes(f"back-matter.{block_id}", text))
    parts.append("\\end{document}\n")
    return "".join(parts)


def tree_state(root: Path) -> dict:
    state = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            state[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return state


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VenueCase(unittest.TestCase):
    """One scratch repository per test: `paper/`, `sections/`, no venues."""

    def setUp(self) -> None:
        _COUNTER[0] += 1
        self.root = FORGE_ROOT / ".scratch" / f".paper-venue-test-{os.getpid()}-{_COUNTER[0]}"
        shutil.rmtree(self.root, ignore_errors=True)
        self.paper = self.root / "paper"
        self.sections = self.root / "sections"
        self.paper.mkdir(parents=True)
        self.sections.mkdir()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.paper / "refs.bib").write_text("@article{ref1,title={A}}\n@article{ref2,title={B}}\n")
        self.write_contracts()
        self.write_canonical(canonical_tex())

    # -- scenario builders ----------------------------------------------------------
    def write_contracts(self, *, abstract_extent: str | None = None, broken_extent: str | None = None) -> None:
        for section, position, number, block_ids, extent in CONTRACTS:
            if section == "abstract" and abstract_extent is not None:
                extent = abstract_extent
            if section == broken_extent:
                extent = "**Extent** as long as it needs to be"
            header = {
                "section": section,
                "position": position,
                "blocks": [
                    {"id": block_id, "requires_facts": [], "requires_declarations": [], "citations": "none"}
                    for block_id in block_ids
                ],
            }
            body = f"# {section}\n\n" + (extent + "\n\n" if extent else "") + "Prose.\n"
            (self.sections / f"{number}-{section}.md").write_text(
                "---\n" + json.dumps(header, indent=2) + "\n---\n" + body, encoding="utf-8")

    def write_canonical(self, text: str) -> None:
        (self.paper / "main.tex").write_bytes(text.encode("utf-8"))

    def requirements(self, **changes) -> Path:
        """Write the Elsevier fixture, with top-level keys replaced by `changes`
        (a value of `None` removes the key), into the scratch root."""
        data = json.loads((FIXTURES / "requirements-elsevier.json").read_text())
        for key, value in changes.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        target = self.root / "requirements.json"
        target.write_text(json.dumps(data), encoding="utf-8")
        return target

    def fake_class(self, name: str = "elsarticle") -> Path:
        path = self.root / f"{name}.cls"
        path.write_text(f"\\NeedsTeXFormat{{LaTeX2e}}\n\\ProvidesClass{{{name}}}\n", encoding="utf-8")
        return path

    def candidates(self) -> None:
        shutil.copy(FIXTURES / "journal-candidates.json", self.paper / "journal-candidates.json")

    # -- running the CLI ------------------------------------------------------------
    def run_cli(self, *argv: str) -> tuple:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = paper_cli.main(list(argv))
        return code, json.loads(buffer.getvalue())

    def venue(self, verb: str, *args: str, sections: bool = False) -> tuple:
        extra = ["--sections", str(self.sections)] if sections else []
        return self.run_cli("venue", verb, "--paper", str(self.paper), *extra, *args)

    def ok(self, verb: str, *args: str, sections: bool = False) -> dict:
        code, payload = self.venue(verb, *args, sections=sections)
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["status"], "ok")
        return payload

    def refused(self, verb: str, code_name: str, *args: str, sections: bool = False) -> dict:
        before = tree_state(self.root)
        code, payload = self.venue(verb, *args, sections=sections)
        self.assertEqual(code, 2, payload)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], code_name, payload)
        self.assertEqual(tree_state(self.root), before, "a refusal must write nothing")
        return payload

    def venue_dir(self, slug: str = "eswa") -> Path:
        return self.paper / "venues" / slug

    def selected(self, slug: str = "eswa") -> None:
        self.candidates()
        self.ok("select", "--slug", slug, "--candidate", "S1001")

    def with_requirements(self, slug: str = "eswa", **changes) -> None:
        self.selected(slug)
        self.ok("requirements", "--slug", slug, "--file", str(self.requirements(**changes)))

    def with_template(self, slug: str = "eswa", name: str = "elsarticle") -> None:
        self.ok("acquire", "--slug", slug, "--file", str(self.fake_class(name)),
                "--url", "https://example.org/elsarticle.zip")

    def audited(self, slug: str = "eswa", **changes) -> dict:
        self.with_requirements(slug, **changes)
        self.with_template(slug)
        return self.ok("diff", "--slug", slug, sections=True)

    def finding(self, audit: dict, finding_id: str) -> dict:
        found = [f for f in audit["findings"] if f["id"] == finding_id]
        self.assertEqual(len(found), 1, f"{finding_id} not in {[f['id'] for f in audit['findings']]}")
        return found[0]

    def write_plan(self, text: str) -> Path:
        path = self.root / "plan.md"
        path.write_text(text, encoding="utf-8")
        return path


# =====================================================================
# select
# =====================================================================
class SelectTests(VenueCase):
    def test_select_by_candidate_copies_the_journal_and_its_estimates(self) -> None:
        self.candidates()
        payload = self.ok("select", "--slug", "eswa", "--candidate", "S1001")
        self.assertEqual(payload["verb"], "select")
        self.assertEqual(payload["slug"], "eswa")
        record = json.loads((self.venue_dir() / "venue.json").read_text())
        self.assertEqual(record["journal"]["name"], "Expert Systems with Applications")
        self.assertEqual(record["journal"]["issn"], ["0957-4174", "1873-6793"])
        self.assertEqual(record["journal"]["issn_l"], "0957-4174")
        self.assertEqual(record["journal"]["publisher"], "Elsevier BV")
        self.assertTrue(record["journal"]["homepage_url"].startswith("https://"))
        self.assertEqual(record["quartile"], "Q1")
        self.assertEqual(record["quartile_source"], "sjr")
        self.assertEqual(record["review_time"]["median_days"], 120)
        self.assertEqual(record["via"], "candidate")
        self.assertEqual(record["candidate_id"], "S1001")
        self.assertTrue(record["selected_at"])

    def test_the_candidate_id_may_be_the_full_openalex_url_in_any_case(self) -> None:
        self.candidates()
        self.ok("select", "--slug", "eswa", "--candidate", "https://openalex.org/s1001")
        self.assertTrue((self.venue_dir() / "venue.json").is_file())

    def test_a_candidate_missing_every_optional_field_is_tolerated(self) -> None:
        self.candidates()
        self.ok("select", "--slug", "bare", "--candidate", "S1002")
        record = json.loads((self.venue_dir("bare") / "venue.json").read_text())
        self.assertEqual(record["journal"]["name"], "Journal Without Optional Fields")
        self.assertEqual(record["journal"]["issn"], [])
        self.assertIsNone(record["quartile"])
        self.assertIsNone(record["review_time"])

    def test_select_manual_records_the_journal_and_issn(self) -> None:
        self.ok("select", "--slug", "manual", "--journal", "Some Journal", "--issn", "1234-5678")
        record = json.loads((self.venue_dir("manual") / "venue.json").read_text())
        self.assertEqual(record["journal"]["name"], "Some Journal")
        self.assertEqual(record["journal"]["issn"], ["1234-5678"])
        self.assertEqual(record["via"], "manual")

    def test_unknown_candidate_refuses(self) -> None:
        self.candidates()
        self.refused("select", "CANDIDATE_UNKNOWN", "--slug", "eswa", "--candidate", "S9999")

    def test_absent_candidates_file_refuses(self) -> None:
        self.refused("select", "CANDIDATES_ABSENT", "--slug", "eswa", "--candidate", "S1001")

    def test_invalid_slugs_refuse(self) -> None:
        self.candidates()
        for slug in ("Bad Slug", "../escape", "", "-lead", "a" * 80, "UPPER", "a/b", "."):
            with self.subTest(slug=slug):
                self.refused("select", "VENUE_SLUG_INVALID", f"--slug={slug}", "--candidate", "S1001")

    def test_mode_flags_are_exclusive_and_one_is_required(self) -> None:
        self.candidates()
        self.refused("select", "SELECT_MODE_REQUIRED", "--slug", "eswa")
        self.refused("select", "SELECT_MODE_REQUIRED", "--slug", "eswa", "--journal", "No ISSN")
        self.refused("select", "SELECT_MODE_CONFLICT", "--slug", "eswa", "--candidate", "S1001",
                     "--journal", "X", "--issn", "1234-5678")

    def test_a_malformed_issn_refuses(self) -> None:
        self.refused("select", "ISSN_INVALID", "--slug", "eswa", "--journal", "X", "--issn", "12-34")

    def test_selecting_the_same_slug_twice_refuses(self) -> None:
        self.selected()
        self.refused("select", "VENUE_EXISTS", "--slug", "eswa", "--candidate", "S1001")

    def test_select_without_a_paper_directory_refuses(self) -> None:
        shutil.rmtree(self.paper)
        code, payload = self.venue("select", "--slug", "eswa", "--journal", "X", "--issn", "1234-5678")
        self.assertEqual((code, payload["code"]), (2, "PAPER_ABSENT"))


# =====================================================================
# requirements
# =====================================================================
class RequirementsTests(VenueCase):
    def test_a_sourced_requirements_file_is_validated_and_stored(self) -> None:
        self.selected()
        payload = self.ok("requirements", "--slug", "eswa", "--file", str(self.requirements()))
        stored = self.venue_dir() / "requirements.json"
        self.assertEqual(payload["sha256"], sha(stored))
        data = json.loads(stored.read_text())
        self.assertEqual(data["document_class"]["name"], "elsarticle")
        self.assertEqual(data["limits"]["abstract_words"]["max"], 250)
        self.assertEqual(payload["counts"]["sections"], 7)

    def test_every_requirement_without_a_quote_and_url_is_refused_unsourced(self) -> None:
        self.selected()
        base = json.loads((FIXTURES / "requirements-elsevier.json").read_text())
        cases = {
            "section quote": ("sections", lambda d: d["sections"][0].pop("quote")),
            "section url": ("sections", lambda d: d["sections"][0].pop("url")),
            "limit quote": ("limits", lambda d: d["limits"]["abstract_words"].pop("quote")),
            "limit url": ("limits", lambda d: d["limits"]["keywords"].pop("url")),
            "class quote": ("document_class", lambda d: d["document_class"].pop("quote")),
            "bare declaration": ("declarations_required",
                                 lambda d: d["declarations_required"].__setitem__(0, "funding")),
            "extra url": ("extras", lambda d: d["extras"][0].pop("url")),
            "bst quote": ("reference_style", lambda d: d["reference_style"].pop("quote")),
            "blank quote": ("sections", lambda d: d["sections"][0].__setitem__("quote", "   ")),
            "non-http url": ("sections", lambda d: d["sections"][0].__setitem__("url", "file:///etc/passwd")),
        }
        for label, (_key, mutate) in cases.items():
            with self.subTest(label):
                data = json.loads(json.dumps(base))
                mutate(data)
                path = self.root / "bad.json"
                path.write_text(json.dumps(data))
                self.refused("requirements", "REQUIREMENT_UNSOURCED", "--slug", "eswa", "--file", str(path))
        self.assertFalse((self.venue_dir() / "requirements.json").exists())

    def test_structurally_invalid_requirements_are_refused(self) -> None:
        self.selected()
        base = json.loads((FIXTURES / "requirements-elsevier.json").read_text())
        cases = {
            "no guidelines": lambda d: d.update(guidelines_urls=[]),
            "bad url": lambda d: d.update(guidelines_urls=["not a url"]),
            "no class": lambda d: d.pop("document_class"),
            "bad class source": lambda d: d["document_class"].update(source="napster"),
            "unknown key": lambda d: d.update(sectoins=[]),
            "unknown limit": lambda d: d["limits"].update(abstract_word={"max": 3, "quote": "q", "url": "https://x.org"}),
            "sections not a list": lambda d: d.update(sections={}),
            "bad section id": lambda d: d["sections"][0].update(id="Not A Slug"),
            "bad order": lambda d: d["sections"][0].update(order="first"),
            "limit without bound": lambda d: [d["limits"]["keywords"].pop(key) for key in ("min", "max")],
            "max below min": lambda d: d["limits"]["keywords"].update(min=9, max=2),
            "wrong schema": lambda d: d.update(schema=2),
            "duplicate section": lambda d: d["sections"].append(dict(d["sections"][0])),
        }
        for label, mutate in cases.items():
            with self.subTest(label):
                data = json.loads(json.dumps(base))
                mutate(data)
                path = self.root / "bad.json"
                path.write_text(json.dumps(data))
                self.refused("requirements", "REQUIREMENTS_INVALID", "--slug", "eswa", "--file", str(path))

    def test_unparseable_and_missing_files_are_invalid_requirements(self) -> None:
        self.selected()
        broken = self.root / "broken.json"
        broken.write_text("{nope")
        self.refused("requirements", "REQUIREMENTS_INVALID", "--slug", "eswa", "--file", str(broken))
        self.refused("requirements", "REQUIREMENTS_INVALID", "--slug", "eswa",
                     "--file", str(self.root / "absent.json"))

    def test_requirements_for_an_unselected_venue_refuse(self) -> None:
        self.refused("requirements", "VENUE_ABSENT", "--slug", "ghost", "--file", str(self.requirements()))

    def test_a_file_outside_the_repository_refuses(self) -> None:
        self.selected()
        outside = Path(os.environ.get("TMPDIR", "/tmp")) / f"venue-outside-{os.getpid()}.json"
        outside.write_text((FIXTURES / "requirements-elsevier.json").read_text())
        self.addCleanup(outside.unlink)
        self.refused("requirements", "PAPER_OUTSIDE_REPOSITORY", "--slug", "eswa", "--file", str(outside))

    def test_storing_requirements_again_replaces_them(self) -> None:
        self.with_requirements()
        limits = json.loads((FIXTURES / "requirements-elsevier.json").read_text())["limits"]
        limits["abstract_words"]["max"] = 150
        self.ok("requirements", "--slug", "eswa", "--file", str(self.requirements(limits=limits)))
        stored = json.loads((self.venue_dir() / "requirements.json").read_text())
        self.assertEqual(stored["limits"]["abstract_words"]["max"], 150)


# =====================================================================
# acquire
# =====================================================================
def _fake_kpsewhich(directory: Path, *, found: bool = True) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "kpsewhich"
    body = '#!/bin/sh\necho "/fake/texmf/tex/latex/$1"\n' if found else "#!/bin/sh\nexit 1\n"
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


class AcquireTests(VenueCase):
    def test_texlive_class_is_recorded_by_name_and_resolved_path(self) -> None:
        self.selected()
        _fake_kpsewhich(self.root / "bin")
        result = paper_venue.acquire(
            self.paper, "eswa", texlive="elsarticle", tool_path=str(self.root / "bin"),
            tool_fallback_dirs=())
        record = json.loads((self.venue_dir() / "template.json").read_text())
        self.assertEqual(record["kind"], "texlive")
        self.assertEqual(record["class"], "elsarticle")
        self.assertEqual(record["path"], "/fake/texmf/tex/latex/elsarticle.cls")
        self.assertEqual(result["class"], "elsarticle")
        self.assertFalse((self.venue_dir() / "template").exists(), "TeX Live classes are not copied")

    @unittest.skipUnless(paper_venue.paper_latex.resolve_texlive_file("article.cls"),
                         "needs a TeX Live with kpsewhich")
    def test_texlive_class_resolves_through_the_cli_with_the_real_toolchain(self) -> None:
        self.selected()
        payload = self.ok("acquire", "--slug", "eswa", "--texlive", "article")
        self.assertTrue(payload["path"].endswith("article.cls"))

    def test_a_class_texlive_does_not_have_is_template_absent(self) -> None:
        self.selected()
        _fake_kpsewhich(self.root / "bin", found=False)
        before = tree_state(self.root)
        with self.assertRaises(paper_venue.Refused) as caught:
            paper_venue.acquire(self.paper, "eswa", texlive="nosuchclass",
                                tool_path=str(self.root / "bin"), tool_fallback_dirs=())
        self.assertEqual(caught.exception.code, "TEMPLATE_ABSENT")
        self.assertEqual(tree_state(self.root), before)

    def test_missing_kpsewhich_is_texlive_unavailable(self) -> None:
        self.selected()
        before = tree_state(self.root)
        with self.assertRaises(paper_venue.Refused) as caught:
            paper_venue.acquire(self.paper, "eswa", texlive="elsarticle",
                                tool_path=str(self.root / "nowhere"), tool_fallback_dirs=())
        self.assertEqual(caught.exception.code, "TEXLIVE_UNAVAILABLE")
        self.assertEqual(tree_state(self.root), before)

    def test_a_hostile_class_name_refuses(self) -> None:
        self.selected()
        for name in ("../x", "a b", "-flag", ""):
            with self.subTest(name=name):
                self.refused("acquire", "TEMPLATE_CLASS_INVALID", "--slug", "eswa", f"--texlive={name}")

    def test_a_class_file_is_copied_with_origin_hash_and_date(self) -> None:
        self.selected()
        source = self.fake_class("elsarticle")
        payload = self.ok("acquire", "--slug", "eswa", "--file", str(source),
                          "--url", "https://example.org/elsarticle.cls")
        copied = self.venue_dir() / "template" / "elsarticle.cls"
        self.assertEqual(copied.read_bytes(), source.read_bytes())
        record = json.loads((self.venue_dir() / "template.json").read_text())
        self.assertEqual(record["kind"], "publisher-template")
        self.assertEqual(record["class"], "elsarticle")
        self.assertEqual(record["origin_url"], "https://example.org/elsarticle.cls")
        self.assertEqual(record["sha256"], sha(source))
        self.assertTrue(record["acquired_at"])
        self.assertEqual(record["files"], ["elsarticle.cls"])
        self.assertEqual(payload["class"], "elsarticle")

    def test_a_zip_is_extracted_safely_and_its_class_detected(self) -> None:
        self.selected()
        archive = self.root / "template.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("pkg/mystyle.cls", "\\ProvidesClass{mystyle}\n")
            zf.writestr("pkg/mystyle.bst", "ENTRY\n")
            zf.writestr("pkg/sample.tex", "\\documentclass{mystyle}\n")
        self.ok("acquire", "--slug", "eswa", "--file", str(archive), "--url", "https://example.org/t.zip")
        record = json.loads((self.venue_dir() / "template.json").read_text())
        self.assertEqual(record["class"], "mystyle")
        self.assertEqual(sorted(record["files"]), ["pkg/mystyle.bst", "pkg/mystyle.cls", "pkg/sample.tex"])
        self.assertTrue((self.venue_dir() / "template" / "pkg" / "mystyle.cls").is_file())

    def test_zip_path_traversal_is_unsafe_and_leaves_nothing_behind(self) -> None:
        self.selected()
        for name in ("../evil.cls", "/abs/evil.cls", "a/../../evil.cls"):
            with self.subTest(name=name):
                archive = self.root / "evil.zip"
                with zipfile.ZipFile(archive, "w") as zf:
                    zf.writestr("fine.cls", "ok")
                    zf.writestr(name, "evil")
                self.refused("acquire", "TEMPLATE_UNSAFE", "--slug", "eswa", "--file", str(archive),
                             "--url", "https://example.org/t.zip")
                self.assertFalse((self.venue_dir() / "template").exists())
                self.assertFalse((self.root / "evil.cls").exists())
                archive.unlink()
        self.assertFalse(list(self.venue_dir().glob("template*")), "no half-extracted temp directory")

    def test_zip_symlinks_are_unsafe(self) -> None:
        self.selected()
        archive = self.root / "link.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            info = zipfile.ZipInfo("link.cls")
            info.external_attr = (0o120777 << 16)
            zf.writestr(info, "/etc/passwd")
        self.refused("acquire", "TEMPLATE_UNSAFE", "--slug", "eswa", "--file", str(archive),
                     "--url", "https://example.org/t.zip")

    def test_zip_over_the_size_cap_is_unsafe(self) -> None:
        self.selected()
        archive = self.root / "big.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("big.cls", "x" * 5000)
        before = tree_state(self.root)
        with mock.patch.object(paper_venue, "MAX_TEMPLATE_BYTES", 1000):
            with self.assertRaises(paper_venue.Refused) as caught:
                paper_venue.acquire(self.paper, "eswa", file=archive, url="https://example.org/big.zip")
        self.assertEqual(caught.exception.code, "TEMPLATE_UNSAFE")
        self.assertIn("size", caught.exception.detail)
        self.assertEqual(tree_state(self.root), before)

    def test_zip_with_too_many_entries_is_unsafe(self) -> None:
        self.selected()
        archive = self.root / "many.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for index in range(6):
                zf.writestr(f"f{index}.tex", "x")
        with mock.patch.object(paper_venue, "MAX_TEMPLATE_FILES", 3):
            with self.assertRaises(paper_venue.Refused) as caught:
                paper_venue.acquire(self.paper, "eswa", file=archive, url="https://example.org/many.zip")
        self.assertEqual(caught.exception.code, "TEMPLATE_UNSAFE")

    def test_a_corrupt_zip_is_unsafe(self) -> None:
        self.selected()
        archive = self.root / "corrupt.zip"
        archive.write_bytes(b"PK\x03\x04 definitely not a zip")
        self.refused("acquire", "TEMPLATE_UNSAFE", "--slug", "eswa", "--file", str(archive),
                     "--url", "https://example.org/t.zip")

    def test_absent_and_unsupported_files_refuse(self) -> None:
        self.selected()
        self.refused("acquire", "TEMPLATE_ABSENT", "--slug", "eswa", "--file", str(self.root / "no.cls"),
                     "--url", "https://example.org/x")
        binary = self.root / "tool.exe"
        binary.write_bytes(b"MZ")
        self.refused("acquire", "TEMPLATE_FILE_UNSUPPORTED", "--slug", "eswa", "--file", str(binary),
                     "--url", "https://example.org/x")

    def test_mode_and_origin_rules(self) -> None:
        self.selected()
        source = str(self.fake_class())
        self.refused("acquire", "ACQUIRE_MODE_REQUIRED", "--slug", "eswa")
        self.refused("acquire", "ACQUIRE_MODE_CONFLICT", "--slug", "eswa", "--texlive", "elsarticle",
                     "--file", source, "--url", "https://example.org/x")
        self.refused("acquire", "TEMPLATE_ORIGIN_REQUIRED", "--slug", "eswa", "--file", source)
        self.refused("acquire", "TEMPLATE_ORIGIN_REQUIRED", "--slug", "eswa", "--file", source,
                     "--url", "ftp://example.org/x")

    def test_acquire_for_an_unselected_venue_refuses(self) -> None:
        self.refused("acquire", "VENUE_ABSENT", "--slug", "ghost", "--texlive", "elsarticle")

    def test_acquiring_again_replaces_the_previous_template(self) -> None:
        self.selected()
        self.ok("acquire", "--slug", "eswa", "--file", str(self.fake_class("first")),
                "--url", "https://example.org/a")
        self.ok("acquire", "--slug", "eswa", "--file", str(self.fake_class("second")),
                "--url", "https://example.org/b")
        self.assertEqual(sorted(p.name for p in (self.venue_dir() / "template").iterdir()), ["second.cls"])
        self.assertEqual(json.loads((self.venue_dir() / "template.json").read_text())["class"], "second")


# =====================================================================
# the readers diff relies on
# =====================================================================
class ReaderTests(unittest.TestCase):
    def test_extent_prose_forms_in_the_shipped_contracts(self) -> None:
        cases = {
            "**Extent** 560–3950 words · 2 to 5 subsections": {"words": (560, 3950)},
            "**Extent** title 10–13 words · keywords 4–8": {"title": (10, 13), "keywords": (4, 8)},
            "**Extent** 216–280 words · 7–14 sentences · **one paragraph**": {"words": (216, 280)},
            "**Extent** 180-410 words · 1 paragraph": {"words": (180, 410)},
            "**Extent** 820–1700 words": {"words": (820, 1700)},
        }
        for line, expected in cases.items():
            with self.subTest(line):
                self.assertEqual(paper_venue.parse_extent(line), expected)

    def test_unparseable_extent_is_none_and_absent_is_none(self) -> None:
        self.assertIsNone(paper_venue.parse_extent("**Extent** as long as it needs to be"))
        self.assertIsNone(paper_venue.parse_extent("no such line"))

    def test_extent_reader_takes_the_section_level_line_only(self) -> None:
        body = "# S\n\n**Extent** 900–1650 words · 7–13 paragraphs\n\nlater\n\n**Extent.** One paragraph, 145–200 words.\n"
        self.assertEqual(paper_venue.read_extent(body), {"words": (900, 1650)})

    def test_the_real_shipped_contracts_all_read_an_extent(self) -> None:
        readable = {}
        for path in sorted((FORGE_ROOT / "sections").glob("[0-9][0-9]-*.md")):
            text = path.read_text(encoding="utf-8")
            readable[path.name] = paper_venue.read_extent(text.split("\n---\n", 1)[1]) if "**Extent**" in text else "none"
        self.assertEqual(readable["08-abstract.md"], {"words": (216, 280)})
        self.assertEqual(readable["10-back-matter.md"], "none")
        self.assertTrue(all(value for value in readable.values()))

    def test_plain_words_drops_commands_math_and_comments(self) -> None:
        text = "We use \\textbf{bold} words $x^2 + y$ here. % a comment with many words\n\\cite{a}"
        self.assertEqual(paper_venue.count_words(text), 5)
        self.assertEqual(paper_venue.count_words("\\begin{equation}\n a = b \n\\end{equation}\nOne two."), 2)

    def test_keywords_are_split_outside_parentheses(self) -> None:
        text = "\\textbf{Keywords:} Quantum ML, Electroencephalography (EEG, raw), ADHD."
        self.assertEqual(paper_venue.read_keywords(text),
                         ["Quantum ML", "Electroencephalography (EEG, raw)", "ADHD"])

    def test_title_and_authors_are_unwrapped(self) -> None:
        tex = "\\title{\\Large\\textbf{A Title Here}}\n\\author{\\textbf{Ada}$^{1}$ \\\\\n $^{1}$Lab \\\\\n $^{*}$Mail}\n\\date{\\today}\n"
        self.assertEqual(paper_venue.read_title(tex), "A Title Here")
        names, affiliations = paper_venue.read_authors(tex)
        self.assertEqual(names, "Ada")
        self.assertEqual(affiliations, ["Lab", "Mail"])
        nested = "\\author{\\textbf{Andr{\\'e}s {\\'A}lvarez}$^{1,*}$ \\\\ $^{1}$Group}"
        self.assertEqual(paper_venue.read_authors(nested), ("Andr{\\'e}s {\\'A}lvarez", ["Group"]))


# =====================================================================
# diff
# =====================================================================
class DiffTests(VenueCase):
    def messy(self) -> dict:
        """Every finding kind at once: 260-word abstract, 9 keywords, a swapped
        and a missing and an extra section, no data-availability/conflicts,
        no highlights, a different class and bibliography style."""
        self.write_canonical(canonical_tex(
            abstract_words=260,
            keywords=tuple(f"kw{i}" for i in range(9)),
            title="\\textbf{Short Title Of Eight Plain Words Only Now}",
        ))
        self.write_contracts(broken_extent="conclusions")
        sections = json.loads((FIXTURES / "requirements-elsevier.json").read_text())["sections"]
        by_id = {section["id"]: dict(section) for section in sections}
        reordered = [
            dict(by_id["materials-and-methods"], order=1),
            dict(by_id["introduction"], order=2),
            dict(by_id["related-work"], required=True, order=3),
            dict(by_id["conclusions"], order=4),
            dict(by_id["references"], order=5),
            dict(by_id["back-matter"], order=6),
            {"id": "new:ethics-statement", "title": "Ethics statement", "required": True, "order": 7,
             "quote": "An ethics statement section is required.", "url": "https://example.org/guide"},
        ]
        limits = json.loads((FIXTURES / "requirements-elsevier.json").read_text())["limits"]
        limits["title_words"] = {"min": 12, "quote": "Titles carry at least twelve words.",
                                 "url": "https://example.org/guide"}
        limits["pages"] = {"max": 30, "quote": "Maximum 30 pages.", "url": "https://example.org/guide"}
        limits["main_text_words"] = {"max": 150, "quote": "Main text up to 150 words.",
                                     "url": "https://example.org/guide"}
        return self.audited(sections=reordered, limits=limits)

    def test_diff_reports_every_finding_kind_with_both_sides(self) -> None:
        audit = self.messy()
        kinds = {finding["kind"] for finding in audit["findings"]}
        self.assertEqual(kinds, {
            "missing-section", "extra-section", "out-of-order", "over-limit", "under-limit",
            "missing-declaration", "class-mismatch", "reference-style-mismatch", "missing-extra",
            "undecidable",
        })

        missing = self.finding(audit, "missing-section:related-work")
        self.assertEqual(missing["severity"], "blocker")
        self.assertEqual(missing["venue"]["url"], "https://www.sciencedirect.com/journal/expert-systems-with-applications/publish/guide-for-authors")
        self.assertIn("quote", missing["venue"])
        self.assertTrue(missing["smith"]["contract"])
        self.assertFalse(missing["smith"]["written"])

        new = self.finding(audit, "missing-section:new:ethics-statement")
        self.assertEqual(new["severity"], "blocker")
        self.assertFalse(new["smith"]["contract"])

        extra = self.finding(audit, "extra-section:results-and-discussion")
        self.assertEqual(extra["severity"], "minor")
        self.assertIn("results-and-discussion.rd-general-task", extra["blocks"])

        order = self.finding(audit, "out-of-order:section-order")
        self.assertEqual(order["severity"], "minor")
        self.assertEqual(order["resolved_by"], "build")

        abstract = self.finding(audit, "over-limit:abstract_words")
        self.assertEqual(abstract["severity"], "blocker")
        self.assertEqual(abstract["smith"]["value"], 260)
        self.assertEqual(abstract["venue"]["max"], 250)
        self.assertEqual(abstract["resolved_by"], "text-change")
        self.assertEqual(abstract["blocks"], ["abstract.slot-1", "abstract.slot-2"])

        contract = self.finding(audit, "over-limit:abstract_words:contract")
        self.assertEqual(contract["severity"], "minor")
        self.assertEqual(contract["smith"]["max"], 280)
        self.assertEqual(contract["basis"], "contract")

        keywords = self.finding(audit, "over-limit:keywords")
        self.assertEqual((keywords["smith"]["value"], keywords["venue"]["max"]), (9, 7))
        self.assertEqual(keywords["blocks"], ["title-and-keywords.keywords"])

        title = self.finding(audit, "under-limit:title_words")
        self.assertEqual(title["severity"], "blocker")
        self.assertEqual(title["smith"]["value"], 8)

        main_text = self.finding(audit, "over-limit:main_text_words")
        self.assertEqual(main_text["severity"], "major")

        for declaration in ("data-availability", "conflicts"):
            found = self.finding(audit, f"missing-declaration:{declaration}")
            self.assertEqual(found["severity"], "blocker")
        ids = [finding["id"] for finding in audit["findings"]]
        self.assertNotIn("missing-declaration:funding", ids)
        self.assertNotIn("missing-declaration:author-contributions", ids)

        klass = self.finding(audit, "class-mismatch:document-class")
        self.assertEqual(klass["smith"]["class"], "article")
        self.assertEqual(klass["venue"]["class"], "elsarticle")
        self.assertEqual(klass["resolved_by"], "build")
        style = self.finding(audit, "reference-style-mismatch:reference-style")
        self.assertEqual((style["smith"]["bst"], style["venue"]["bst"]), ("ieeetr", "elsarticle-num"))

        extra_item = self.finding(audit, "missing-extra:highlights")
        self.assertEqual(extra_item["severity"], "major")
        self.assertEqual(extra_item["resolved_by"], "operator-decision")

        pages = self.finding(audit, "undecidable:pages")
        self.assertEqual(pages["severity"], "minor")
        contract_gap = self.finding(audit, "undecidable:extent:conclusions")
        self.assertIn("Extent", contract_gap["message"])

    def test_diff_writes_audit_json_and_nothing_else(self) -> None:
        self.with_requirements()
        self.with_template()
        before = tree_state(self.root)
        payload = self.ok("diff", "--slug", "eswa", sections=True)
        after = tree_state(self.root)
        changed = {name for name in after if before.get(name) != after[name]}
        self.assertEqual(changed, {"paper/venues/eswa/audit.json"})
        stored = json.loads((self.venue_dir() / "audit.json").read_text())
        self.assertEqual(stored["findings"], payload["findings"])
        self.assertEqual(stored["canonical_sha256"], sha(self.paper / "main.tex"))
        self.assertEqual(stored["requirements_sha256"], sha(self.venue_dir() / "requirements.json"))
        self.assertEqual(stored["measurements"]["abstract_words"], 200)
        self.assertEqual(stored["measurements"]["keywords"], 5)
        self.assertEqual(stored["measurements"]["title_words"], 7)
        self.assertEqual(stored["measurements"]["figures"], 0)
        self.assertEqual(stored["measurements"]["references"], 2)

    def test_the_diff_is_deterministic(self) -> None:
        first = self.audited()
        second = self.ok("diff", "--slug", "eswa", sections=True)
        strip = lambda audit: {k: v for k, v in audit.items() if k != "generated_at"}  # noqa: E731
        self.assertEqual(strip(first), strip(second))

    def test_a_manuscript_that_conforms_has_no_blocker_and_needs_no_plan(self) -> None:
        self.write_contracts(abstract_extent="**Extent** 200–240 words · one paragraph")
        self.write_canonical(canonical_tex(
            related=True, declarations=("author-contributions", "funding", "data-availability", "conflicts"),
            results_extra="\\begin{figure}\\end{figure}\n"))
        audit = self.audited(extras=[])
        self.assertEqual(audit["summary"]["blocker"], 0)
        self.assertFalse(audit["needs_plan"])
        self.assertEqual({f["kind"] for f in audit["findings"]},
                         {"class-mismatch", "reference-style-mismatch", "over-limit"})
        contract_only = [f for f in audit["findings"] if f["kind"] == "over-limit"]
        self.assertEqual([(f["id"], f["severity"]) for f in contract_only],
                         [("over-limit:keywords:contract", "minor")])
        self.assertEqual(audit["measurements"]["figures"], 1)

    def test_under_limits_are_reported(self) -> None:
        limits = {"abstract_words": {"min": 300, "quote": "At least 300 words.", "url": "https://example.org/g"},
                  "keywords": {"min": 6, "quote": "At least six keywords.", "url": "https://example.org/g"},
                  "main_text_words": {"min": 5000, "quote": "At least 5000 words.", "url": "https://example.org/g"}}
        audit = self.audited(limits=limits)
        self.assertEqual(self.finding(audit, "under-limit:abstract_words")["severity"], "blocker")
        self.assertEqual(self.finding(audit, "under-limit:keywords")["severity"], "blocker")
        self.assertEqual(self.finding(audit, "under-limit:main_text_words")["severity"], "major")

    def test_a_contract_that_cannot_satisfy_the_venue_is_a_major_conflict(self) -> None:
        self.write_contracts(abstract_extent="**Extent** 300–400 words")
        audit = self.audited()
        conflict = self.finding(audit, "over-limit:abstract_words:contract")
        self.assertEqual(conflict["severity"], "major")
        self.assertTrue(conflict["smith"]["conflict"])

    def test_same_class_with_different_options_is_still_a_class_mismatch(self) -> None:
        self.write_canonical(canonical_tex(documentclass="\\documentclass[12pt]{elsarticle}",
                                           bibstyle="elsarticle-num"))
        audit = self.audited()
        klass = self.finding(audit, "class-mismatch:document-class")
        self.assertEqual(klass["smith"]["class"], "elsarticle")
        self.assertEqual(klass["smith"]["options"], ["12pt"])
        self.assertNotIn("reference-style-mismatch:reference-style", [f["id"] for f in audit["findings"]])

    def test_a_bibliography_style_given_only_as_prose_is_undecidable(self) -> None:
        style = {"description": "Numbered, in order of appearance.", "quote": "Numbered references.",
                 "url": "https://example.org/guide"}
        audit = self.audited(reference_style=style)
        self.finding(audit, "undecidable:reference-style")

    def test_diff_refuses_without_requirements_template_or_paper(self) -> None:
        self.selected()
        self.refused("diff", "REQUIREMENTS_ABSENT", "--slug", "eswa", sections=True)
        self.ok("requirements", "--slug", "eswa", "--file", str(self.requirements()))
        self.refused("diff", "TEMPLATE_ABSENT", "--slug", "eswa", sections=True)
        self.refused("diff", "VENUE_ABSENT", "--slug", "ghost", sections=True)
        self.with_template()
        (self.paper / "main.tex").unlink()
        self.refused("diff", "PAPER_ABSENT", "--slug", "eswa", sections=True)

    def test_diff_refuses_when_the_contracts_cannot_be_read(self) -> None:
        self.with_requirements()
        self.with_template()
        self.refused("diff", "SECTION_CONTRACTS_UNREADABLE", "--slug", "eswa",
                     "--sections", str(self.root / "nowhere"))

    def test_diff_refuses_a_malformed_contract_header(self) -> None:
        self.with_requirements()
        self.with_template()
        (self.sections / "99-broken.md").write_text("no front matter here\n")
        self.refused("diff", "MALFORMED_HEADER", "--slug", "eswa", sections=True)

    def test_diff_refuses_a_canonical_file_with_a_broken_marker(self) -> None:
        self.with_requirements()
        self.with_template()
        text = (self.paper / "main.tex").read_text().replace(
            "%% paper-writing block introduction.block-1 end", "%% paper-writing block introduction.block-1")
        (self.paper / "main.tex").write_text(text)
        code, payload = self.venue("diff", "--slug", "eswa", sections=True)
        self.assertEqual((code, payload["code"]), (2, "MARKER_MALFORMED"))


# =====================================================================
# plan and approve
# =====================================================================
PLAN_TEXT = (
    "# Plan for eswa\n\n- [over-limit:abstract_words] shorten the abstract to 250 words.\n"
    "- [missing-declaration:data-availability] add a data-availability statement.\n"
)


class PlanApproveTests(VenueCase):
    def messy_audit(self) -> dict:
        self.write_canonical(canonical_tex(abstract_words=260))
        return self.audited()

    def test_plan_is_stored_with_its_hash(self) -> None:
        self.messy_audit()
        plan = self.write_plan(PLAN_TEXT)
        payload = self.ok("plan", "--slug", "eswa", "--file", str(plan))
        self.assertEqual((self.venue_dir() / "plan.md").read_bytes(), plan.read_bytes())
        self.assertEqual(payload["plan_sha256"], hashlib.sha256(plan.read_bytes()).hexdigest())
        self.assertIn("over-limit:abstract_words", payload["referenced_findings"])
        self.assertFalse(payload["approval_reset"])

    def test_plan_without_an_audit_refuses(self) -> None:
        self.with_requirements()
        self.refused("plan", "AUDIT_ABSENT", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT)))

    def test_plan_that_references_no_finding_refuses(self) -> None:
        self.messy_audit()
        self.refused("plan", "PLAN_REFERENCES_NO_FINDING", "--slug", "eswa",
                     "--file", str(self.write_plan("Just make it better.\n")))
        self.refused("plan", "PLAN_REFERENCES_NO_FINDING", "--slug", "eswa",
                     "--file", str(self.write_plan("[over-limit:invented] not a finding.\n")))

    def test_empty_and_missing_plans_are_unreadable(self) -> None:
        self.messy_audit()
        self.refused("plan", "PLAN_UNREADABLE", "--slug", "eswa", "--file", str(self.write_plan("  \n")))
        self.refused("plan", "PLAN_UNREADABLE", "--slug", "eswa", "--file", str(self.root / "absent.md"))

    def test_approval_is_bound_to_the_plan_hash(self) -> None:
        self.messy_audit()
        plan = self.write_plan(PLAN_TEXT)
        digest = self.ok("plan", "--slug", "eswa", "--file", str(plan))["plan_sha256"]
        payload = self.ok("approve", "--slug", "eswa", "--statement", "Yes, apply it as written.",
                          "--plan-sha256", digest)
        record = json.loads((self.venue_dir() / "approval.json").read_text())
        self.assertEqual(record["plan_sha256"], digest)
        self.assertEqual(record["statement"], "Yes, apply it as written.")
        self.assertEqual(record["via"], "cli")
        self.assertTrue(record["approved_at"])
        self.assertEqual(payload["plan_sha256"], digest)

    def test_approve_refuses_a_wrong_hash_an_empty_statement_and_a_missing_plan(self) -> None:
        self.messy_audit()
        self.refused("approve", "PLAN_ABSENT", "--slug", "eswa", "--statement", "ok", "--plan-sha256", "0" * 64)
        digest = self.ok("plan", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT)))["plan_sha256"]
        self.refused("approve", "PLAN_HASH_MISMATCH", "--slug", "eswa", "--statement", "ok",
                     "--plan-sha256", "f" * 64)
        self.refused("approve", "PLAN_HASH_MISMATCH", "--slug", "eswa", "--statement", "ok",
                     "--plan-sha256", "short")
        self.refused("approve", "STATEMENT_EMPTY", "--slug", "eswa", "--statement", "   ",
                     "--plan-sha256", digest)
        self.assertFalse((self.venue_dir() / "approval.json").exists())

    def test_a_new_plan_resets_the_previous_approval(self) -> None:
        self.messy_audit()
        first = self.ok("plan", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT)))["plan_sha256"]
        self.ok("approve", "--slug", "eswa", "--statement", "yes", "--plan-sha256", first)
        self.assertTrue((self.venue_dir() / "approval.json").is_file())
        revised = self.ok("plan", "--slug", "eswa",
                          "--file", str(self.write_plan(PLAN_TEXT + "- [missing-extra:highlights] draft them.\n")))
        self.assertTrue(revised["approval_reset"])
        self.assertFalse((self.venue_dir() / "approval.json").exists())
        self.assertNotEqual(revised["plan_sha256"], first)
        self.refused("approve", "PLAN_HASH_MISMATCH", "--slug", "eswa", "--statement", "yes",
                     "--plan-sha256", first)

    def test_a_refused_plan_keeps_the_existing_approval(self) -> None:
        self.messy_audit()
        digest = self.ok("plan", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT)))["plan_sha256"]
        self.ok("approve", "--slug", "eswa", "--statement", "yes", "--plan-sha256", digest)
        self.refused("plan", "PLAN_REFERENCES_NO_FINDING", "--slug", "eswa",
                     "--file", str(self.write_plan("nothing useful")))
        self.assertTrue((self.venue_dir() / "approval.json").is_file())


# =====================================================================
# build
# =====================================================================
class BuildTests(VenueCase):
    def canonical_blocks(self) -> dict:
        data = (self.paper / "main.tex").read_bytes()
        parsed = paper_block.parse(data)
        return {block_id: (data[begin["end"]:end["start"]], begin["digest"])
                for block_id, (begin, end) in parsed.pairs.items()}

    def approved_build_ready(self, **canonical) -> None:
        self.write_canonical(canonical_tex(**canonical))
        self.audited()
        digest = self.ok("plan", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT)))["plan_sha256"]
        self.ok("approve", "--slug", "eswa", "--statement", "approved", "--plan-sha256", digest)

    def test_build_assembles_the_venue_file_and_never_touches_the_canonical_text(self) -> None:
        self.approved_build_ready(abstract_words=260, related=True)
        protected = {name: digest for name, digest in tree_state(self.root).items()
                     if not name.startswith("paper/venues/")}
        payload = self.ok("build", "--slug", "eswa")
        self.assertEqual({name: digest for name, digest in tree_state(self.root).items()
                          if not name.startswith("paper/venues/")}, protected,
                         "build must not write paper/main.tex, sections/ or anything outside the venue")
        venue_tex = self.venue_dir() / "main.tex"
        self.assertEqual(payload["output"], "paper/venues/eswa/main.tex")
        text = venue_tex.read_text(encoding="utf-8")

        self.assertTrue(text.startswith("\\documentclass[preprint,12pt]{elsarticle}\n"))
        self.assertIn("\\begin{frontmatter}", text)
        self.assertIn("\\title{A Hybrid Quantum Classical Network for EEG}", text)
        self.assertIn("\\author{Ada Lovelace}", text)
        self.assertIn("\\address{Analytical Engine Lab", text)
        self.assertIn("\\begin{keyword}\nalpha \\sep beta \\sep gamma \\sep delta \\sep epsilon\n\\end{keyword}", text)
        self.assertIn("\\end{frontmatter}", text)
        self.assertIn("\\bibliographystyle{elsarticle-num}", text)
        self.assertIn("\\bibliography{../../refs}", text)
        self.assertIn("\\graphicspath{{../../}}", text)
        self.assertNotIn("\\usepackage{geometry}", text)
        self.assertNotIn("\\usepackage{cite}", text)
        self.assertIn("\\usepackage{amsmath,amssymb}", text)
        self.assertEqual(payload["preamble"]["skipped"], ["cite", "geometry"])

        # the canonical blocks, byte for byte, markers and digests intact, once each
        venue_data = venue_tex.read_bytes()
        parsed = paper_block.parse(venue_data)
        canonical = self.canonical_blocks()
        self.assertEqual(sorted(parsed.pairs), sorted(canonical))
        for block_id, (begin, end) in parsed.pairs.items():
            body = venue_data[begin["end"]:end["start"]]
            self.assertEqual(body, canonical[block_id][0], block_id)
            self.assertEqual(begin["digest"], canonical[block_id][1], block_id)
            self.assertEqual(hashlib.sha256(body).hexdigest(), begin["digest"], block_id)

        # the venue's own section order and headings
        headings = [line for line in text.splitlines() if line.startswith("\\section")]
        self.assertEqual(headings, [
            "\\section{Introduction}\\label{sec:intro}",
            "\\section{Related work}\\label{sec:rw}",
            "\\section{Material and methods}\\label{sec:methods}",
            "\\section{Results and discussion}\\label{sec:results}",
            "\\section{Conclusions}\\label{sec:conclusions}",
            "\\section*{Declarations}",
        ])
        self.assertLess(text.index("\\bibliography{../../refs}"), text.index("\\section*{Declarations}"))
        order = [bid for bid in parsed.order]
        self.assertEqual(order.index("introduction.block-1") < order.index("related-work.rw-preamble")
                         < order.index("materials-and-methods.mm-preamble"), True)

        manifest = json.loads((self.venue_dir() / "build.json").read_text())
        self.assertEqual(manifest["canonical_sha256"], sha(self.paper / "main.tex"))
        self.assertEqual(manifest["output_sha256"], sha(venue_tex))
        self.assertEqual(manifest["document_class"], "elsarticle")

    def test_the_venue_section_order_is_followed_not_the_canonical_one(self) -> None:
        sections = json.loads((FIXTURES / "requirements-elsevier.json").read_text())["sections"]
        by_id = {s["id"]: s for s in sections}
        swapped = [dict(by_id["materials-and-methods"], order=1), dict(by_id["introduction"], order=2),
                   dict(by_id["results-and-discussion"], order=3), dict(by_id["conclusions"], order=4),
                   dict(by_id["references"], order=5), dict(by_id["back-matter"], order=6)]
        self.write_canonical(canonical_tex(declarations=("author-contributions", "funding", "data-availability", "conflicts")))
        self.audited(sections=swapped, extras=[])
        self.ok("build", "--slug", "eswa")
        text = (self.venue_dir() / "main.tex").read_text()
        self.assertLess(text.index("\\section{Material and methods}"), text.index("\\section{Introduction}"))

    def test_sections_the_venue_does_not_list_are_kept_and_the_ones_smith_lacks_are_not_invented(self) -> None:
        sections = json.loads((FIXTURES / "requirements-elsevier.json").read_text())["sections"]
        sections.append({"id": "new:ethics", "title": "Ethics", "required": True, "order": 8,
                         "quote": "Ethics section.", "url": "https://example.org/g"})
        self.write_canonical(canonical_tex())
        self.audited(sections=[s for s in sections if s["id"] != "results-and-discussion"])
        digest = self.ok("plan", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT)))["plan_sha256"]
        self.ok("approve", "--slug", "eswa", "--statement", "ok", "--plan-sha256", digest)
        payload = self.ok("build", "--slug", "eswa")
        text = (self.venue_dir() / "main.tex").read_text()
        self.assertIn("results-and-discussion.rd-general-task begin", text)
        self.assertEqual(payload["sections"]["extra_kept"], ["results-and-discussion"])
        self.assertEqual(payload["sections"]["missing"], ["related-work", "new:ethics"])
        self.assertNotIn("Ethics", text)
        self.assertLess(text.index("results-and-discussion.rd-general-task begin"),
                        text.index("\\bibliography{../../refs}"),
                        "sections the venue does not list stay ahead of the bibliography")
        self.assertLess(text.index("\\bibliography{../../refs}"), text.index("\\section*{Declarations}"))

    def test_build_without_blockers_needs_no_plan(self) -> None:
        self.write_contracts(abstract_extent="**Extent** 200–240 words")
        self.write_canonical(canonical_tex(related=True, declarations=(
            "author-contributions", "funding", "data-availability", "conflicts")))
        self.audited(extras=[])
        payload = self.ok("build", "--slug", "eswa")
        self.assertTrue((self.venue_dir() / "main.tex").is_file())
        self.assertFalse(payload["plan_required"])

    def test_build_refuses_while_blockers_exist_without_an_approved_plan(self) -> None:
        self.write_canonical(canonical_tex(abstract_words=260))
        self.audited()
        self.refused("build", "PLAN_NOT_APPROVED", "--slug", "eswa")
        self.ok("plan", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT)))
        self.refused("build", "PLAN_NOT_APPROVED", "--slug", "eswa")
        self.assertFalse((self.venue_dir() / "main.tex").exists())

    def test_an_approval_for_a_superseded_plan_does_not_license_the_build(self) -> None:
        self.approved_build_ready(abstract_words=260)
        approval = self.venue_dir() / "approval.json"
        record = json.loads(approval.read_text())
        record["plan_sha256"] = "a" * 64
        approval.write_text(json.dumps(record))
        self.refused("build", "PLAN_NOT_APPROVED", "--slug", "eswa")

    def test_build_refuses_a_stale_audit(self) -> None:
        self.approved_build_ready(abstract_words=260)
        self.write_canonical(canonical_tex(abstract_words=240))
        self.refused("build", "AUDIT_STALE", "--slug", "eswa")
        self.ok("diff", "--slug", "eswa", sections=True)
        self.ok("build", "--slug", "eswa")

    def test_build_refuses_a_stale_audit_after_new_requirements(self) -> None:
        self.approved_build_ready()
        self.ok("requirements", "--slug", "eswa", "--file", str(self.requirements(extras=[])))
        self.refused("build", "AUDIT_STALE", "--slug", "eswa")

    def test_build_refuses_missing_prerequisites(self) -> None:
        self.selected()
        self.refused("build", "REQUIREMENTS_ABSENT", "--slug", "eswa")
        self.ok("requirements", "--slug", "eswa", "--file", str(self.requirements()))
        self.refused("build", "TEMPLATE_ABSENT", "--slug", "eswa")
        self.with_template()
        self.refused("build", "AUDIT_ABSENT", "--slug", "eswa")
        self.refused("build", "VENUE_ABSENT", "--slug", "ghost")

    def test_build_refuses_a_hand_edited_canonical_block(self) -> None:
        self.write_canonical(canonical_tex(declarations=("author-contributions", "funding",
                                                        "data-availability", "conflicts"), related=True))
        self.write_contracts(abstract_extent="**Extent** 200–240 words")
        self.audited(extras=[])
        text = (self.paper / "main.tex").read_text()
        (self.paper / "main.tex").write_text(text.replace("Funding:} No funding.", "Funding:} Sneaky."))
        self.ok("diff", "--slug", "eswa", sections=True)
        self.refused("build", "BLOCK_HAND_EDITED", "--slug", "eswa")

    def test_ieeetran_and_llncs_front_matter(self) -> None:
        for name, needles in (
            ("IEEEtran", ["\\begin{IEEEkeywords}", "\\IEEEauthorblockN{Ada Lovelace}", "\\maketitle"]),
            ("llncs", ["\\institute{", "\\keywords{alpha \\and beta", "\\maketitle"]),
        ):
            with self.subTest(name):
                slug = name.lower()
                self.write_canonical(canonical_tex())
                document_class = {"name": name, "options": [], "source": "texlive",
                                  "quote": f"Use {name}.", "url": "https://example.org/g"}
                self.with_requirements(slug, document_class=document_class, extras=[])
                self.with_template(slug, name)
                self.ok("diff", "--slug", slug, sections=True)
                digest = self.ok("plan", "--slug", slug, "--file", str(self.write_plan(PLAN_TEXT)))["plan_sha256"]
                self.ok("approve", "--slug", slug, "--statement", "ok", "--plan-sha256", digest)
                self.ok("build", "--slug", slug)
                text = (self.venue_dir(slug) / "main.tex").read_text()
                self.assertTrue(text.startswith(f"\\documentclass{{{name}}}\n"), text[:80])
                for needle in needles:
                    self.assertIn(needle, text)

    def test_a_generic_class_keeps_the_canonical_title_block_in_place(self) -> None:
        document_class = {"name": "article", "options": ["11pt"], "source": "generic",
                          "quote": "Any LaTeX article.", "url": "https://example.org/g"}
        self.write_canonical(canonical_tex())
        self.with_requirements(document_class=document_class, extras=[])
        self.with_template(name="article")
        self.ok("diff", "--slug", "eswa", sections=True)
        digest = self.ok("plan", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT)))["plan_sha256"]
        self.ok("approve", "--slug", "eswa", "--statement", "ok", "--plan-sha256", digest)
        self.ok("build", "--slug", "eswa")
        text = (self.venue_dir() / "main.tex").read_text()
        self.assertTrue(text.startswith("\\documentclass[11pt]{article}\n"))
        self.assertIn("\\maketitle", text)
        self.assertNotIn("\\iffalse", text)
        self.assertNotIn("\\begin{frontmatter}", text)

    def test_the_declarations_region_travels_with_the_venue_file(self) -> None:
        text = canonical_tex()
        region = ("%% paper-writing declarations begin sha256=" + "0" * 64 + "\n%% {}\n"
                  "%% paper-writing declarations end\n")
        self.write_canonical(text.replace("\\end{document}", region + "\\end{document}"))
        self.audited()
        digest = self.ok("plan", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT)))["plan_sha256"]
        self.ok("approve", "--slug", "eswa", "--statement", "ok", "--plan-sha256", digest)
        self.ok("build", "--slug", "eswa")
        venue_text = (self.venue_dir() / "main.tex").read_text()
        self.assertIn(region, venue_text)


def _tex_bin(name: str) -> str | None:
    kpsewhich = paper_venue.paper_latex.discover_kpsewhich()
    if kpsewhich is None:
        return None
    sibling = Path(kpsewhich).parent / name
    return str(sibling) if sibling.is_file() else shutil.which(name)


@unittest.skipUnless(
    paper_venue.paper_latex.resolve_texlive_file("elsarticle.cls")
    and _tex_bin("pdflatex") and _tex_bin("bibtex"),
    "needs a TeX Live with elsarticle, pdflatex and bibtex",
)
class CompileTests(VenueCase):
    def test_the_elsarticle_venue_file_compiles_with_the_real_toolchain(self) -> None:
        self.write_canonical(canonical_tex(declarations=("author-contributions", "funding",
                                                        "data-availability", "conflicts"), related=True))
        self.write_contracts(abstract_extent="**Extent** 200–240 words")
        self.with_requirements(extras=[])
        self.ok("acquire", "--slug", "eswa", "--texlive", "elsarticle")
        self.ok("diff", "--slug", "eswa", sections=True)
        self.ok("build", "--slug", "eswa")
        directory = self.venue_dir()
        env = dict(os.environ, openout_any="p", shell_escape="f")
        for tool in ("pdflatex", "bibtex", "pdflatex", "pdflatex"):
            argv = [_tex_bin(tool)] + (["-interaction=nonstopmode", "-file-line-error"] if tool == "pdflatex" else [])
            proc = subprocess.run(argv + ["main"] if tool == "bibtex" else argv + ["main.tex"],
                                  cwd=str(directory), env=env, capture_output=True, text=True, timeout=240)
            self.assertEqual(proc.returncode, 0, f"{tool}: {proc.stdout[-1500:]}")
        self.assertTrue((directory / "main.pdf").is_file())
        self.assertIn("../../refs.bib", (directory / "main.blg").read_text())
        self.assertEqual(self.ok("status", "--slug", "eswa")["state"], "compiled")


# =====================================================================
# status and list
# =====================================================================
class StatusListTests(VenueCase):
    def test_status_walks_the_state_machine(self) -> None:
        self.write_canonical(canonical_tex(abstract_words=260))
        self.candidates()
        self.assertEqual(self.ok("list")["venues"], [])
        self.ok("select", "--slug", "eswa", "--candidate", "S1001")
        self.assertEqual(self.ok("status", "--slug", "eswa")["state"], "selected")
        self.ok("requirements", "--slug", "eswa", "--file", str(self.requirements()))
        self.assertEqual(self.ok("status", "--slug", "eswa")["state"], "requirements")
        self.with_template()
        self.assertEqual(self.ok("status", "--slug", "eswa")["state"], "template")
        self.ok("diff", "--slug", "eswa", sections=True)
        status = self.ok("status", "--slug", "eswa")
        self.assertEqual(status["state"], "audited")
        self.assertTrue(status["blockers"] > 0)
        self.assertTrue(status["plan_required"])
        self.assertIn("plan", status["next_action"])
        digest = self.ok("plan", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT)))["plan_sha256"]
        self.assertEqual(self.ok("status", "--slug", "eswa")["state"], "planned")
        self.ok("approve", "--slug", "eswa", "--statement", "ok", "--plan-sha256", digest)
        self.assertEqual(self.ok("status", "--slug", "eswa")["state"], "approved")
        self.ok("build", "--slug", "eswa")
        built = self.ok("status", "--slug", "eswa")
        self.assertEqual(built["state"], "built")
        self.assertFalse(built["audit_stale"])
        (self.venue_dir() / "main.pdf").write_bytes(b"%PDF-1.5")
        self.assertEqual(self.ok("status", "--slug", "eswa")["state"], "compiled")
        self.assertEqual([step["done"] for step in built["steps"]], [True] * 7 + [False])

    def test_status_reports_a_stale_audit(self) -> None:
        self.audited()
        self.write_canonical(canonical_tex(abstract_words=100))
        status = self.ok("status", "--slug", "eswa")
        self.assertTrue(status["audit_stale"])
        self.assertIn("diff", status["next_action"])

    def test_status_ignores_an_approval_for_another_plan(self) -> None:
        self.write_canonical(canonical_tex(abstract_words=260))
        self.audited()
        self.ok("plan", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT)))
        (self.venue_dir() / "approval.json").write_text(json.dumps(
            {"plan_sha256": "b" * 64, "statement": "x", "approved_at": "t", "via": "cli"}))
        self.assertEqual(self.ok("status", "--slug", "eswa")["state"], "planned")

    def test_list_summarises_every_venue(self) -> None:
        self.candidates()
        self.ok("select", "--slug", "b-journal", "--journal", "B", "--issn", "1111-2222")
        self.ok("select", "--slug", "a-journal", "--candidate", "S1001")
        listing = self.ok("list")["venues"]
        self.assertEqual([entry["slug"] for entry in listing], ["a-journal", "b-journal"])
        self.assertEqual(listing[0]["journal"], "Expert Systems with Applications")
        self.assertEqual(listing[0]["state"], "selected")

    def test_status_of_an_unknown_venue_refuses(self) -> None:
        self.refused("status", "VENUE_ABSENT", "--slug", "ghost")
        self.refused("status", "VENUE_SLUG_INVALID", "--slug", "../x")

    def test_list_without_a_paper_directory_refuses(self) -> None:
        shutil.rmtree(self.paper)
        code, payload = self.venue("list")
        self.assertEqual((code, payload["code"]), (2, "PAPER_ABSENT"))


# =====================================================================
# wiring
# =====================================================================
class WiringTests(VenueCase):
    def test_every_venue_verb_is_in_the_parser_and_every_refusal_is_classified(self) -> None:
        parser = paper_cli.build_parser()
        venue = next(a for a in parser._actions if hasattr(a, "choices") and a.choices and "venue" in a.choices)
        group = next(a for a in venue.choices["venue"]._actions if hasattr(a, "choices") and a.choices)
        self.assertEqual(set(group.choices), set(paper_venue.VERBS))
        self.assertEqual(set(paper_venue.VERBS), {
            "select", "requirements", "acquire", "diff", "plan", "approve", "build", "status", "list"})
        self.assertIn("venue", paper_cli.COMMANDS)
        source = (SCRIPTS / "paper_venue.py").read_text(encoding="utf-8")
        raised = set(re.findall(r'Refused\(\s*"([A-Z_]+)"', source))
        self.assertGreater(len(raised), 30)
        for code in raised:
            self.assertIn(code, paper_cli.REFUSAL_CLASSIFICATION)

    def test_a_refusal_through_a_real_subprocess_exits_2_with_json(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(CLI), "venue", "status", "--slug", "ghost", "--paper", str(self.paper)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual((payload["status"], payload["code"]), ("refused", "VENUE_ABSENT"))

    def test_a_success_through_a_real_subprocess_exits_0_with_json(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(CLI), "venue", "list", "--paper", str(self.paper)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["venues"], [])

    def test_the_paper_must_resolve_inside_the_repository(self) -> None:
        outside = Path(os.environ.get("TMPDIR", "/tmp")) / "venue-outside-paper"
        code, payload = self.run_cli("venue", "list", "--paper", str(outside))
        self.assertEqual((code, payload["code"]), (2, "PAPER_OUTSIDE_REPOSITORY"))


if __name__ == "__main__":
    unittest.main()
