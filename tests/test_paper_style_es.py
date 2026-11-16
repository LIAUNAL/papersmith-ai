"""`paper_style_es.py`: the Spanish readability index and the EN->ES fidelity check.

Spec: odd/tasks/manuscript-translation-es.md, T1 (S3, S4, S6). Every catalog
category is detected on a sentence that carries the pattern and not on its
clean rewrite; flow and redundancy findings fire on the shapes they name;
`compare_facts` catches every changed fact and ignores what a translation
legitimately changes (month names, the decimal separator).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import paper_style_es  # noqa: E402

#: (category, flagged sentence, clean rewrite)
CATALOG_CASES = (
    ("cliche", "El método juega un papel fundamental en la clasificación de señales.",
     "El método determina la clasificación de señales."),
    ("comodin", "Proponemos un marco robusto para la clasificación de señales.",
     "Proponemos un marco para la clasificación de señales con error acotado."),
    ("promocional", "Presentamos un enfoque revolucionario para el análisis de la señal.",
     "Presentamos un enfoque para el análisis de la señal."),
    ("atribucion_vaga", "Estudios recientes señalan que el ruido afecta la señal.",
     "El ruido afecta la señal medida en cada canal."),
    ("perifrasis", "El modelo tiene la capacidad de separar las clases.",
     "El modelo puede separar las clases."),
    ("copula_evitada", "El conjunto de datos cuenta con diez sujetos.",
     "El conjunto de datos tiene diez sujetos."),
    ("calco", "Eventualmente, el modelo converge a una solución estable.",
     "Al final, el modelo converge a una solución estable."),
    ("plantilla", "Cabe destacar que el error disminuye con más datos.",
     "El error disminuye con más datos."),
    ("paralelismo_negativo", "El método no solo reduce el error, sino que acelera el entrenamiento.",
     "El método reduce el error y acelera el entrenamiento."),
    ("falso_rango", "El sistema cubre desde la adquisición hasta la interpretación clínica.",
     "El sistema cubre la adquisición y la interpretación clínica."),
    ("closing_gerund", "El modelo reduce el error de clasificación, mejorando la precisión global.",
     "El modelo reduce el error de clasificación y mejora la precisión global."),
    ("spaced_dash", "El clasificador — una red convolucional — separa las clases.",
     "El clasificador, una red convolucional, separa las clases."),
    ("register", "Puedes ver el resultado en la tabla de comparación.",
     "El resultado aparece en la tabla de comparación."),
)


def categories(text: str, **kwargs) -> set[str]:
    return {finding["category"] for finding in paper_style_es.audit_text(text, **kwargs)["findings"]}


class CatalogTests(unittest.TestCase):

    def test_each_category_fires_on_its_pattern_and_not_on_the_rewrite(self) -> None:
        for category, flagged, clean in CATALOG_CASES:
            with self.subTest(category=category):
                self.assertIn(category, categories(flagged))
                self.assertNotIn(category, categories(clean))

    def test_a_cited_attribution_is_not_vague(self) -> None:
        self.assertNotIn("atribucion_vaga",
                         categories("Estudios recientes señalan que el ruido afecta la señal \\cite{smith2020}."))

    def test_a_long_sentence_is_flagged_and_a_short_one_is_not(self) -> None:
        long = "El modelo " + " ".join(["procesa la señal del canal"] * 10) + "."
        self.assertIn("long_sentence", categories(long))
        self.assertNotIn("long_sentence", categories("El modelo procesa la señal del canal."))

    def test_a_finding_carries_exactly_the_contract_keys(self) -> None:
        finding = paper_style_es.audit_text(CATALOG_CASES[0][1])["findings"][0]
        self.assertEqual(set(finding), {"category", "fragment", "hint", "paragraph", "sentence"})
        self.assertEqual((finding["paragraph"], finding["sentence"]), (1, 1))
        self.assertTrue(finding["hint"])


class FlowTests(unittest.TestCase):

    def test_two_consecutive_sentences_with_the_same_opening(self) -> None:
        text = "El modelo separa las clases. El modelo reduce el error."
        self.assertIn("opening_repeat", categories(text))
        self.assertNotIn("opening_repeat", categories("El modelo separa las clases. Su error es bajo."))

    def test_a_connector_repeated_within_the_window(self) -> None:
        text = ("Además, el modelo separa las clases. La red es pequeña. "
                "Además, el error baja con más datos.")
        self.assertIn("connector_repeat", categories(text))
        self.assertNotIn("connector_repeat", categories(
            "Además, el modelo separa las clases. La red es pequeña. El error baja con más datos."))


class RedundancyTests(unittest.TestCase):
    PHRASE = "análisis espectral de grafos dinámicos ponderados"

    def repeated(self) -> str:
        return (f"Aplicamos el {self.PHRASE} a cada sujeto. Luego medimos el error.\n\n"
                f"El {self.PHRASE} separa las clases. Su costo es bajo.\n\n"
                f"Con el {self.PHRASE} obtenemos mapas estables.")

    def test_a_phrase_repeated_across_paragraphs(self) -> None:
        self.assertIn("repeated_phrase", categories(self.repeated()))

    def test_a_glossary_term_is_collapsed_and_never_counted(self) -> None:
        self.assertNotIn("repeated_phrase", categories(self.repeated(), glossary=[self.PHRASE]))

    def test_two_near_duplicate_sentences(self) -> None:
        text = ("La red convolucional profunda clasifica señales cerebrales registradas durante tareas motoras.\n\n"
                "La red convolucional profunda clasifica señales cerebrales registradas durante tareas cognitivas.")
        self.assertIn("near_duplicate", categories(text))
        self.assertNotIn("near_duplicate", categories(
            "La red convolucional profunda clasifica señales cerebrales registradas durante tareas motoras.\n\n"
            "El protocolo de adquisición usa sesenta y cuatro electrodos y una frecuencia alta."))

    def test_redundancy_raises_the_redundancy_score(self) -> None:
        clean = paper_style_es.audit_text("El modelo separa las clases. Su error es bajo.")
        self.assertGreater(paper_style_es.audit_text(self.repeated())["redundancy_score"],
                           clean["redundancy_score"])


class ScoreTests(unittest.TestCase):

    def test_the_score_shape_and_ranges(self) -> None:
        report = paper_style_es.audit_text(" ".join(flagged for _, flagged, _ in CATALOG_CASES))
        self.assertEqual(set(report), {"index", "style_score", "flow_score", "redundancy_score",
                                       "verdict", "findings"})
        self.assertTrue(0 <= report["index"] <= 100)
        for key in ("style_score", "flow_score", "redundancy_score"):
            self.assertTrue(0.0 <= report[key] <= 1.0, key)
        self.assertIn(report["verdict"], {"clear", "uneven", "needs_revision"})

    def test_flagged_prose_scores_lower_than_its_rewrite(self) -> None:
        flagged = paper_style_es.audit_text(" ".join(f for _, f, _ in CATALOG_CASES))
        clean = paper_style_es.audit_text(" ".join(c for _, _, c in CATALOG_CASES))
        self.assertLess(flagged["index"], clean["index"])
        self.assertEqual(clean["verdict"], "clear")
        self.assertIn(flagged["verdict"], {"uneven", "needs_revision"})

    def test_the_notice_is_not_an_authorship_claim(self) -> None:
        notice = paper_style_es.NOTICE.lower()
        self.assertIn("not", notice)
        self.assertIn("author", notice)
        for word in ("perplexity", "burstiness"):
            self.assertNotIn(word, notice)

    def test_latex_markup_is_not_prose(self) -> None:
        text = ("El modelo \\textbf{separa} las clases \\citep{a2020}, como muestra la "
                "Figura~\\ref{fig:x}.\n\\begin{equation}\nx = y\n\\end{equation}\n")
        report = paper_style_es.audit_text(text)
        self.assertEqual(report["findings"], [])


class DocumentTests(unittest.TestCase):

    def test_blocks_are_scored_and_cross_block_repetition_reported(self) -> None:
        phrase = "análisis espectral de grafos dinámicos ponderados"
        blocks = {
            "intro": f"Aplicamos el {phrase} a cada sujeto. Luego medimos el error.",
            "methods": f"El {phrase} separa las clases. Su costo es bajo.",
            "results": f"Con el {phrase} obtenemos mapas estables.",
        }
        report = paper_style_es.audit_document(blocks)
        self.assertEqual(set(report), {"document", "blocks", "cross_block_redundancy"})
        self.assertEqual([block["id"] for block in report["blocks"]], ["intro", "methods", "results"])
        self.assertEqual(set(report["blocks"][0]),
                         {"id", "index", "style_score", "flow_score", "redundancy_score", "verdict", "findings"})
        self.assertEqual(set(report["document"]),
                         {"index", "style_score", "flow_score", "redundancy_score", "verdict"})
        self.assertTrue(report["cross_block_redundancy"])
        entry = report["cross_block_redundancy"][0]
        self.assertTrue({"phrase", "sentence"} & set(entry))
        self.assertEqual(sorted(entry["blocks"]), ["intro", "methods", "results"])

    def test_the_glossary_reaches_the_document_audit(self) -> None:
        phrase = "análisis espectral de grafos dinámicos ponderados"
        blocks = {"a": f"Aplicamos el {phrase} aquí.", "b": f"El {phrase} separa.", "c": f"Con el {phrase} medimos."}
        self.assertEqual(paper_style_es.audit_document(blocks, glossary=[phrase])["cross_block_redundancy"], [])


ENGLISH = ("We train the network on 120 subjects \\citep{smith2020,lee2021} and reach 0.85 accuracy "
           "in March 2024 (Figure~\\ref{fig:roc}). The loss is $\\mathcal{L} = x^2$.\n\n"
           "Table~\\ref{tab:main} lists 3.5 ms per epoch.\n\\label{sec:results}\n")
SPANISH = ("Entrenamos la red con 120 sujetos \\citep{smith2020,lee2021} y alcanzamos una exactitud de 0,85 "
           "en marzo de 2024 (Figura~\\ref{fig:roc}). La pérdida es $\\mathcal{L} = x^2$.\n\n"
           "La Tabla~\\ref{tab:main} reporta 3,5 ms por época.\n\\label{sec:results}\n")


class CompareFactsTests(unittest.TestCase):

    def test_a_faithful_translation_has_no_difference(self) -> None:
        self.assertEqual(paper_style_es.compare_facts(ENGLISH, SPANISH), [])

    def test_a_changed_number(self) -> None:
        differences = paper_style_es.compare_facts(ENGLISH, SPANISH.replace("120 sujetos", "121 sujetos"))
        self.assertTrue(any("number" in d and "120" in d and "121" in d for d in differences), differences)

    def test_a_dropped_citation(self) -> None:
        differences = paper_style_es.compare_facts(ENGLISH, SPANISH.replace("smith2020,", ""))
        self.assertTrue(any("citation" in d and "smith2020" in d for d in differences), differences)

    def test_a_changed_label_or_reference(self) -> None:
        label = paper_style_es.compare_facts(ENGLISH, SPANISH.replace("\\label{sec:results}", "\\label{sec:res}"))
        self.assertTrue(any("label" in d and "sec:results" in d for d in label), label)
        ref = paper_style_es.compare_facts(ENGLISH, SPANISH.replace("\\ref{fig:roc}", "\\ref{fig:pr}"))
        self.assertTrue(any("reference" in d and "fig:roc" in d for d in ref), ref)

    def test_a_changed_math(self) -> None:
        differences = paper_style_es.compare_facts(ENGLISH, SPANISH.replace("x^2", "x^3"))
        self.assertTrue(any("math" in d for d in differences), differences)

    def test_changed_display_math(self) -> None:
        english = "We minimize\n\\begin{equation}\na + b\n\\end{equation}\n"
        spanish = "Minimizamos\n\\begin{equation}\na - b\n\\end{equation}\n"
        self.assertTrue(any("math" in d for d in paper_style_es.compare_facts(english, spanish)))

    def test_a_paragraph_mismatch(self) -> None:
        differences = paper_style_es.compare_facts(ENGLISH, SPANISH.replace("\n\n", " "))
        self.assertTrue(any("paragraph" in d for d in differences), differences)

    def test_month_names_and_decimal_commas_are_not_differences(self) -> None:
        self.assertEqual(paper_style_es.compare_facts(
            "Collected in March 2024 with 1,500 trials and 0.25 s windows.",
            "Recolectado en marzo de 2024 con 1.500 ensayos y ventanas de 0,25 s."), [])


if __name__ == "__main__":
    unittest.main()
