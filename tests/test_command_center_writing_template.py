"""The Sections tab offers a general writing template.

A "General template" button in the command center's Sections tab opens the
detail drawer on a concise, section-by-section summary of the manuscript's
structure and basic rules, in paper order, closing on the cross-cutting rules.
The summary is data, one file per dashboard language, served as static files
under ``static/writing-template/``; it is derived from the contracts in
``sections/`` and switches with the dashboard's language selector.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import server

REPO = Path(__file__).resolve().parents[1]
STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
TEMPLATE_DIR = STATIC / "writing-template"
SPANISH_ACCENTS = re.compile(r"[áéíóúñÁÉÍÓÚÑ¿¡]")

PAPER_ORDER = [
    ("title-and-keywords", "sections/09-title-and-keywords.md"),
    ("abstract", "sections/08-abstract.md"),
    ("introduction", "sections/06-introduction.md"),
    ("related-work", "sections/05-related-work.md"),
    ("materials-and-methods", "sections/01-materials-and-methods.md"),
    ("experimental-setup", "sections/02-experimental-setup.md"),
    ("results-and-discussion", "sections/03-results-and-discussion.md"),
    ("limitations", "sections/04-limitations.md"),
    ("conclusions", "sections/07-conclusions.md"),
    ("back-matter", "sections/10-back-matter.md"),
]


def catalogue(lang: str) -> dict[str, str]:
    text = (STATIC / "i18n" / f"{lang}.js").read_text(encoding="utf-8")
    match = re.search(rf"window\.PAPERSMITH_I18N\.{lang}\s*=\s*(\{{.*\}})\s*;\s*\Z", text, re.S)
    assert match
    return json.loads(match.group(1))


def template(lang: str) -> dict:
    return json.loads((TEMPLATE_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def entry(lang: str, section_id: str) -> dict:
    return next(item for item in template(lang)["sections"] if item["id"] == section_id)


def flat(item: dict) -> str:
    """Every visible string of one section entry, joined."""
    parts = [item["name"], item["extent"]]
    parts += [f"{step['label']} {step['text']}" for step in item["structure"]]
    parts += item["rules"]
    return " ".join(parts)


def sections_pane() -> str:
    start = PAGE.index('<div id="pane-sections"')
    return PAGE[start:PAGE.index("<!-- TAB 5", start)]


class ButtonTests(unittest.TestCase):
    def test_the_sections_pane_holds_the_general_template_button(self) -> None:
        match = re.search(r"<button\b[^>]*\bid=\"writingTemplateButton\"[^>]*>", sections_pane())
        self.assertIsNotNone(match, "the Sections pane holds #writingTemplateButton")
        tag = match.group(0)
        self.assertIn('data-i18n="sections.templateButton"', tag)
        self.assertIn('onclick="openWritingTemplate()"', tag)

    def test_the_button_label_reads_in_both_languages(self) -> None:
        self.assertEqual(catalogue("en")["sections.templateButton"], "General template")
        self.assertEqual(catalogue("es")["sections.templateButton"], "Plantilla general")

    def test_the_panel_opens_in_the_detail_drawer_and_follows_the_language(self) -> None:
        script = PAGE[PAGE.index("<script>", PAGE.index("<body>")):]
        body = script[script.index("function openWritingTemplate"):]
        body = body[:body.index("\n    }\n")]
        self.assertIn("writing-template/", body)
        self.assertIn("getLanguage()", body)
        self.assertIn("drawerOverlay", body)
        handler = script[script.index("document.addEventListener('languagechange'"):]
        self.assertIn("writingTemplateOpen", handler[:handler.index("\n    });")])


class ContentTests(unittest.TestCase):
    def test_one_entry_per_section_in_paper_order_in_both_languages(self) -> None:
        for lang in ("en", "es"):
            with self.subTest(lang=lang):
                data = template(lang)
                self.assertEqual([(s["id"], s["contract"]) for s in data["sections"]], PAPER_ORDER)
                for item in data["sections"]:
                    self.assertTrue((REPO / item["contract"]).is_file(), item["contract"])
                    self.assertTrue(item["name"].strip() and item["extent"].strip())
                    self.assertTrue(item["structure"] and item["rules"], item["id"])
                self.assertTrue(data["title"].strip() and data["intro"].strip())
                self.assertGreaterEqual(len(data["general"]["rules"]), 5)

    def test_the_two_languages_mirror_each_other(self) -> None:
        en, es = template("en"), template("es")
        self.assertEqual(len(en["general"]["rules"]), len(es["general"]["rules"]))
        for left, right in zip(en["sections"], es["sections"]):
            with self.subTest(section=left["id"]):
                self.assertEqual(len(left["structure"]), len(right["structure"]))
                self.assertEqual(len(left["rules"]), len(right["rules"]))
                self.assertNotEqual(flat(left), flat(right))

    def test_english_is_english_and_spanish_is_spanish(self) -> None:
        en_text = (TEMPLATE_DIR / "en.json").read_text(encoding="utf-8")
        self.assertIsNone(SPANISH_ACCENTS.search(en_text))
        self.assertIsNotNone(SPANISH_ACCENTS.search((TEMPLATE_DIR / "es.json").read_text(encoding="utf-8")))

    def test_the_introduction_walks_its_seven_paragraphs(self) -> None:
        for lang in ("en", "es"):
            with self.subTest(lang=lang):
                self.assertEqual(len(entry(lang, "introduction")["structure"]), 7)
                self.assertIn("750", entry(lang, "introduction")["extent"])
                self.assertIn("1380", entry(lang, "introduction")["extent"])

    def test_the_title_carries_its_word_count_and_the_author_minipage(self) -> None:
        title = flat(entry("en", "title-and-keywords"))
        self.assertIn("10–13 words", title)
        self.assertIn("minipage", title)
        self.assertIn("minipage", flat(entry("es", "title-and-keywords")))

    def test_the_new_dataset_citation_and_discussion_rules_are_stated(self) -> None:
        methods = flat(entry("en", "materials-and-methods"))
        setup = flat(entry("en", "experimental-setup"))
        results = flat(entry("en", "results-and-discussion"))
        for text in (methods, setup):
            self.assertIn("acquisition-protocol diagram", text)
            self.assertIn("pictogram", text)
        self.assertRegex(setup, r"hypothesis tests[^.]*citation")
        self.assertIn("never stands for the paper's own numbers", results)
        for section_id in ("materials-and-methods", "experimental-setup"):
            self.assertIn("pictograma", flat(entry("es", section_id)))


class ServedTests(unittest.TestCase):
    def test_the_dashboard_serves_the_template_per_language(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "papersmith.yaml").write_text("title: Fresh Paper\n", encoding="utf-8")
        client = TestClient(server.create_app(root))
        for lang in ("en", "es"):
            with self.subTest(lang=lang):
                response = client.get(f"/writing-template/{lang}.json")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), template(lang))


class SectionsTableUnchangedTests(unittest.TestCase):
    def test_the_sections_table_and_its_rules_drawer_still_work_as_before(self) -> None:
        pane = sections_pane()
        self.assertIn('id="sectionsTableBody"', pane)
        self.assertIn('id="sectionsMetaCount"', pane)
        self.assertEqual(len(re.findall(r'<th data-i18n="sections\.col\.', pane)), 8)
        self.assertIn("function openSectionDrawer(secId)", PAGE)
        self.assertIn("loadSectionArtifactIntoDrawer(s.filename, s.id)", PAGE)
        close = PAGE[PAGE.index("function closeDrawer"):]
        self.assertIn("document.getElementById('drawerOverlay').classList.remove('active')",
                      close[:close.index("\n    }\n")])


if __name__ == "__main__":
    unittest.main()
