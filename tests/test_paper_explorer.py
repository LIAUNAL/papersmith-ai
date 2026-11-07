"""The cited-paper explorer reads any Papersmith workspace, whatever it holds.

``paper_explorer.cited_papers`` joins ``paper/main.tex``, ``paper/refs.bib``,
the SOTA pool, the evidence ledger, ``.papersmith/citations.json`` and the
manuscript graph ids. Each input is optional: a workspace at any phase, with a
bibliography from any exporter, gets every paper it can name and a warning for
what it cannot read. ``GET /api/atlas/cited-papers`` never writes.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from skills._core.command_center import manuscript_graph, paper_explorer, server

REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "skills" / "_core" / "command_center" / "static"

MAIN_TEX = r"""\documentclass{article}
\begin{document}
\section{Introduction}
Prior work \cite{alpha2020,beta2021}. See \citep[p.~3]{alpha2020}.
% \cite{commented2000}
\section{Methods}
We follow \citet{alpha2020} and \cite{ghost2019}.
\bibliography{refs}
\end{document}
"""

REFS = r"""@article{alpha2020,
  title={{Alpha} Networks for P{\'e}rez Signals},
  author={P{\'e}rez, Ana and Smith, John and others},
  journal={Journal of Alpha},
  year={2020},
  doi={10.1000/ALPHA},
  abstract={We study alpha.},
  keywords={eeg, alpha}
}

@inproceedings{beta2021,
  title={Beta Models},
  author={Doe, Jane},
  booktitle={Proceedings of Beta},
  year={2021}
}
"""


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class Workspace(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()

    def papers(self) -> dict[str, dict]:
        return {p["key"]: p for p in paper_explorer.cited_papers(self.root)["papers"]}


class BibParsingTests(unittest.TestCase):
    def parse(self, text: str) -> dict[str, dict]:
        return paper_explorer.parse_bib(text)

    def test_a_whole_entry_on_one_line_keeps_every_field(self) -> None:
        entry = self.parse('@article{k, title={One Line}, DOI={10.1/x}, author={Roe, Ann}, year={2018}, pages={68–77} }')["k"]
        self.assertEqual((entry["title"], entry["doi"], entry["year"]), ("One Line", "10.1/x", "2018"))

    def test_multi_line_values_quotes_parentheses_and_upper_case_are_read(self) -> None:
        entries = self.parse('@ARTICLE(k1,\n  TITLE = "A {Quoted}\n   Title",\n  YEAR = 2019,\n)\n'
                             '@misc{k2, title = {Nested {braces} here}}')
        self.assertEqual(entries["k1"]["title"], "A {Quoted}\n   Title")
        self.assertEqual(entries["k1"]["year"], "2019")
        self.assertEqual(entries["k1"]["_type"], "article")
        self.assertEqual(entries["k2"]["title"], "Nested {braces} here")

    def test_strings_are_expanded_and_comments_are_not_entries(self) -> None:
        entries = self.parse('@string{jml = "Journal of ML"}\n@comment{ignored, title={no}}\n'
                             '@preamble{"x"}\n@article{k, journal = jml # " Letters", title={T}}')
        self.assertEqual(list(entries), ["k"])
        self.assertEqual(entries["k"]["journal"], "Journal of ML Letters")

    def test_an_unterminated_entry_does_not_swallow_the_next_one(self) -> None:
        entries = self.parse('@article{broken, title={Open\n\n@article{fine, title={Closed}}\n')
        self.assertEqual(entries["fine"]["title"], "Closed")

    def test_latex_becomes_readable_text(self) -> None:
        cases = {
            r"{ADHDeepNet} From Raw {EEG}": "ADHDeepNet From Raw EEG",
            r'F{\"o}rderung des Ga{\"e}l': "Förderung des Gaël",
            r"P\'erez-Salinas, Adri{\'a}n": "Pérez-Salinas, Adrián",
            r"Garc{\'\i}a and \v{S}koda": "García and Škoda",
            r"Stra{\ss}e \& M\o ller": "Straße & Møller",
            r"\emph{Deep} learning---a survey": "Deep learning—a survey",
            r"pages 1--22~and more": "pages 1–22 and more",
            r"$k$-means and $\beta$-VAE": r"k-means and \beta-VAE",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(paper_explorer.plain_text(raw), expected)

    def test_an_accent_keeps_the_space_after_its_letter(self) -> None:
        for raw, expected in (
            (r"Jos\'e Garc\'ia", "José García"),
            (r"Universit\'e de Montr\'eal", "Université de Montréal"),
            (r"Jos\'{e} Garc\'{ i }a", "José García"),
            (r"M\"uller and Sons", "Müller and Sons"),
            (r"\c c and \v s then", "ç and š then"),
            (r"\c{c} and \v{s} then", "ç and š then"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(paper_explorer.plain_text(raw), expected)

    def test_raw_nul_digits_never_read_as_a_math_placeholder(self) -> None:
        self.assertEqual(paper_explorer.plain_text("a\x007\x00b $x$"), "a7b x")


class JoinTests(Workspace):
    def full_workspace(self) -> None:
        write(self.root, "paper/main.tex", MAIN_TEX)
        write(self.root, "paper/refs.bib", REFS)

    def test_every_cited_key_is_a_paper_in_manuscript_order(self) -> None:
        self.full_workspace()
        body = paper_explorer.cited_papers(self.root)
        self.assertEqual(body["schema"], paper_explorer.SCHEMA)
        self.assertEqual(body["cite_source"], "main.tex")
        self.assertEqual([p["key"] for p in body["papers"]][:3], ["alpha2020", "beta2021", "ghost2019"])
        self.assertEqual(body["summary"]["total"], len(body["papers"]))

    def test_bib_metadata_reaches_the_paper(self) -> None:
        self.full_workspace()
        alpha = self.papers()["alpha2020"]
        self.assertEqual(alpha["title"], "Alpha Networks for Pérez Signals")
        self.assertEqual(alpha["authors"], ["Ana Pérez", "John Smith"])
        self.assertEqual((alpha["year"], alpha["venue"]), ("2020", "Journal of Alpha"))
        self.assertEqual(alpha["abstract"], "We study alpha.")
        self.assertEqual(alpha["keywords"], ["eeg", "alpha"])
        self.assertEqual(alpha["link"], "https://doi.org/10.1000/ALPHA")
        self.assertEqual(self.papers()["beta2021"]["venue"], "Proceedings of Beta")

    def test_the_sections_that_cite_a_paper_are_counted(self) -> None:
        self.full_workspace()
        alpha = self.papers()["alpha2020"]
        self.assertEqual(alpha["sections"], [{"title": "Introduction", "count": 2}, {"title": "Methods", "count": 1}])
        self.assertEqual(alpha["cites"], 3)

    def test_a_cited_key_without_a_bib_entry_stays_visible(self) -> None:
        self.full_workspace()
        ghost = self.papers()["ghost2019"]
        self.assertFalse(ghost["has_entry"])
        self.assertIsNone(ghost["title"])
        self.assertEqual(paper_explorer.cited_papers(self.root)["summary"]["missing_entries"],
                         ["ghost2019"])

    def test_the_pool_fills_gaps_by_identifier_and_by_title(self) -> None:
        self.full_workspace()
        write(self.root, "sota-pool/candidates.json", json.dumps({"candidates": [
            {"identifier": "https://doi.org/10.1000/alpha", "resolver": "crossref", "title": "Other title",
             "abstract": "Pool abstract", "family": "Family A", "venue": "Pool venue"},
            {"identifier": "pool-beta", "title": "BETA models", "abstract": "Beta abstract", "family": "Family B",
             "source_url": "https://example.org/beta", "authors": ["Jane Doe"]},
        ]}))
        papers = self.papers()
        alpha, beta = papers["alpha2020"], papers["beta2021"]
        self.assertEqual((alpha["in_pool"], alpha["family"]), (True, "Family A"))
        self.assertEqual(alpha["abstract"], "We study alpha.")  # the bib wins when it has one
        self.assertEqual((beta["in_pool"], beta["abstract"]), (True, "Beta abstract"))
        self.assertEqual(beta["link"], "https://example.org/beta")
        self.assertFalse(papers["ghost2019"]["in_pool"])

    def test_claims_and_ideas_are_attached_to_their_paper(self) -> None:
        self.full_workspace()
        write(self.root, "paper/.paper-writing/evidence/intro.jsonl", json.dumps(
            {"block_id": "intro", "cite_key": "alpha2020", "claim": "Alpha works", "verdict": "supported"}) + "\n")
        write(self.root, ".papersmith/citations.json", json.dumps({"schema": 1, "ideas": {
            "pillar:P1": [{"id": "10.1000/alpha", "why": "It frames the pillar"}]}}))
        alpha = self.papers()["alpha2020"]
        self.assertEqual([(c["claim"], c["verdict"]) for c in alpha["claims"]], [("Alpha works", "supported")])
        self.assertEqual(alpha["ideas"], [{"idea": "pillar:P1", "why": "It frames the pillar"}])

    def test_node_ids_are_the_ids_of_the_manuscript_graph(self) -> None:
        self.full_workspace()
        graph_ids = {n["id"] for n in manuscript_graph.build_graph(self.root)["nodes"]}
        for key, paper in self.papers().items():
            with self.subTest(key=key):
                self.assertIn(paper["node_id"], graph_ids)

    def test_only_web_links_are_offered(self) -> None:
        write(self.root, "paper/main.tex", r"\cite{a,b,c}")
        write(self.root, "paper/refs.bib", "@misc{a, title={A}, url={javascript:alert(1)}}\n"
                                           "@misc{b, title={B}, url={file:///etc/passwd}}\n"
                                           "@misc{c, title={C}, url={https://example.org/a\\_b}}\n")
        papers = self.papers()
        self.assertIsNone(papers["a"]["link"])
        self.assertIsNone(papers["b"]["link"])
        self.assertEqual(papers["c"]["link"], "https://example.org/a_b")

    def test_an_arxiv_reference_links_to_arxiv(self) -> None:
        write(self.root, "paper/main.tex", r"\cite{a,b}")
        write(self.root, "paper/refs.bib", "@misc{a, title={A}, eprint={1905.13311}, archivePrefix={arXiv}}\n"
                                           "@misc{b, title={B}, journal={arXiv preprint arXiv:2001.00001}}\n")
        papers = self.papers()
        self.assertEqual(papers["a"]["link"], "https://arxiv.org/abs/1905.13311")
        self.assertEqual(papers["b"]["link"], "https://arxiv.org/abs/2001.00001")


class ClusterTests(Workspace):
    def test_the_answer_groups_papers_and_co_citation_counts(self) -> None:
        write(self.root, "paper/main.tex", r"\cite{a,b} \cite{c} \cite{d}")
        write(self.root, "paper/refs.bib", "".join(
            f"@misc{{{key}, title={{{title}}}}}\n" for key, title in (
                ("a", "Quantum circuit learning"), ("b", "Variational quantum circuit models"),
                ("c", "Convolutional networks for image recognition"),
                ("d", "Deep convolutional networks for vision"))))
        clusters = paper_explorer.cited_papers(self.root)["clusters"]
        self.assertEqual(sorted(sorted(c["keys"]) for c in clusters["clusters"]), [["a", "b"], ["c", "d"]])
        self.assertTrue(clusters["method"])

    def test_an_empty_workspace_has_no_clusters(self) -> None:
        self.assertEqual(paper_explorer.cited_papers(self.root)["clusters"]["clusters"], [])


class AnyWorkspaceTests(Workspace):
    def test_an_empty_workspace_is_an_empty_answer(self) -> None:
        body = paper_explorer.cited_papers(self.root)
        self.assertEqual((body["papers"], body["cite_source"], body["warnings"]), ([], "none", []))

    def test_a_bibliography_without_a_manuscript_lists_its_entries(self) -> None:
        write(self.root, "paper/refs.bib", REFS)
        body = paper_explorer.cited_papers(self.root)
        self.assertEqual(body["cite_source"], "refs.bib")
        self.assertEqual({p["key"] for p in body["papers"]}, {"alpha2020", "beta2021"})

    def test_a_manuscript_using_other_cite_commands_falls_back_to_the_bibliography(self) -> None:
        write(self.root, "paper/main.tex", r"\parencite{alpha2020}")
        write(self.root, "paper/refs.bib", REFS)
        body = paper_explorer.cited_papers(self.root)
        self.assertEqual(body["cite_source"], "refs.bib")
        self.assertEqual(len(body["papers"]), 2)

    def test_a_manuscript_without_a_bibliography_still_names_its_keys(self) -> None:
        write(self.root, "paper/main.tex", MAIN_TEX)
        papers = self.papers()
        self.assertFalse(papers["alpha2020"]["has_entry"])

    def test_no_atlas_and_no_pool_is_not_a_failure(self) -> None:
        write(self.root, "paper/main.tex", MAIN_TEX)
        write(self.root, "paper/refs.bib", REFS)
        body = paper_explorer.cited_papers(self.root)
        self.assertEqual(body["warnings"], [])
        self.assertEqual(body["summary"]["in_pool"], 0)

    def test_broken_inputs_become_warnings_and_the_rest_survives(self) -> None:
        write(self.root, "paper/main.tex", MAIN_TEX)
        write(self.root, "paper/refs.bib", REFS)
        write(self.root, "sota-pool/candidates.json", "{not json")
        write(self.root, "sota-pool/atlas.json", "{not json")
        write(self.root, ".papersmith/citations.json", "[1, 2")
        body = paper_explorer.cited_papers(self.root)
        self.assertEqual({w["code"] for w in body["warnings"]}, {"pool", "graph", "ideas"})
        alpha = next(p for p in body["papers"] if p["key"] == "alpha2020")
        self.assertEqual(alpha["title"], "Alpha Networks for Pérez Signals")
        self.assertIsNone(alpha["node_id"])

    def test_non_utf8_bytes_in_the_bibliography_do_not_stop_the_reading(self) -> None:
        (self.root / "paper").mkdir()
        (self.root / "paper" / "refs.bib").write_bytes("@misc{a, title={Caf\xe9 Study}}".encode("latin-1"))
        self.assertEqual(len(paper_explorer.cited_papers(self.root)["papers"]), 1)

    def test_an_evidence_record_with_an_unhashable_cite_key_is_skipped(self) -> None:
        write(self.root, "paper/main.tex", MAIN_TEX)
        write(self.root, "paper/refs.bib", REFS)
        write(self.root, "paper/.paper-writing/evidence/intro.jsonl",
              json.dumps({"cite_key": ["alpha2020"], "claim": "bad"}) + "\n"
              + json.dumps({"cite_key": "alpha2020", "block_id": "intro", "claim": "good", "verdict": "holds"}) + "\n")
        papers = self.papers()
        self.assertEqual([c["claim"] for c in papers["alpha2020"]["claims"]], ["good"])

    def test_a_bib_value_with_nul_digits_does_not_stop_the_answer(self) -> None:
        write(self.root, "paper/main.tex", MAIN_TEX)
        write(self.root, "paper/refs.bib", REFS.replace("Beta Models", "Beta\x009\x00 Models"))
        papers = self.papers()
        self.assertEqual(papers["beta2021"]["title"], "Beta9 Models")

    def test_a_paper_that_cannot_be_assembled_stays_listed_with_a_warning(self) -> None:
        write(self.root, "paper/main.tex", MAIN_TEX)
        write(self.root, "paper/refs.bib", REFS)
        real = paper_explorer._paper

        def explode(paper_bib, key, *rest):
            if key == "beta2021":
                raise TypeError("broken record")
            return real(paper_bib, key, *rest)

        with mock.patch.object(paper_explorer, "_paper", explode):
            body = paper_explorer.cited_papers(self.root)
        self.assertEqual([p["key"] for p in body["papers"]], ["alpha2020", "beta2021", "ghost2019"])
        self.assertEqual({w["code"] for w in body["warnings"]}, {"paper"})
        self.assertIsNone(body["papers"][1]["title"])
        self.assertEqual(body["summary"]["total"], 3)

    def test_a_key_cited_only_in_a_comment_is_not_listed(self) -> None:
        write(self.root, "paper/main.tex", MAIN_TEX)
        write(self.root, "paper/refs.bib", REFS)
        body = paper_explorer.cited_papers(self.root)
        self.assertNotIn("commented2000", [p["key"] for p in body["papers"]])
        self.assertEqual(body["summary"]["missing_entries"], ["ghost2019"])
        self.assertTrue(all(p["cites"] > 0 for p in body["papers"]))

    def test_the_answer_is_deterministic(self) -> None:
        write(self.root, "paper/main.tex", MAIN_TEX)
        write(self.root, "paper/refs.bib", REFS)
        self.assertEqual(paper_explorer.cited_papers(self.root), paper_explorer.cited_papers(self.root))


class RouteTests(Workspace):
    def test_the_route_answers_and_writes_nothing(self) -> None:
        write(self.root, "paper/main.tex", MAIN_TEX)
        write(self.root, "paper/refs.bib", REFS)
        before = snapshot(self.root)
        client = TestClient(server.create_app(self.root))
        response = client.get("/api/atlas/cited-papers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["total"], 3)
        self.assertEqual(snapshot(self.root), before)


class ReferenceSidecarTests(Workspace):
    SIDECAR = "paper/.paper-writing/references.json"

    def sidecar(self, **records: dict) -> None:
        write(self.root, self.SIDECAR, json.dumps({"schema": "papersmith.references/v1", "references": records}))

    def setUp(self) -> None:
        super().setUp()
        write(self.root, "paper/main.tex", "\\cite{bare2020}\n\\cite{alpha2020}\n")
        write(self.root, "paper/refs.bib", "@misc{bare2020, note={x}}\n" + REFS)

    def test_the_sidecar_fills_what_nothing_else_holds(self) -> None:
        self.sidecar(bare2020={"status": "resolved", "title": "Side title", "abstract": "Side abstract",
                               "year": 2020, "venue": "Side venue", "link": "https://doi.org/10.1/side"})
        body = paper_explorer.cited_papers(self.root)
        bare = next(p for p in body["papers"] if p["key"] == "bare2020")
        self.assertEqual((bare["title"], bare["abstract"], bare["year"], bare["venue"], bare["link"]),
                         ("Side title", "Side abstract", "2020", "Side venue", "https://doi.org/10.1/side"))
        self.assertEqual(body["summary"]["with_abstract"], 2)
        self.assertEqual(body["warnings"], [])

    def test_the_bib_and_the_pool_win_over_the_sidecar(self) -> None:
        self.sidecar(alpha2020={"status": "resolved", "abstract": "Side abstract", "venue": "Side venue"},
                     bare2020={"status": "resolved", "abstract": "Side abstract"})
        write(self.root, "sota-pool/candidates.json", json.dumps({"candidates": [
            {"identifier": "pool-bare", "title": "Bare", "abstract": "Pool abstract"}]}))
        write(self.root, "paper/refs.bib", "@misc{bare2020, title={Bare}}\n" + REFS)
        papers = self.papers()
        self.assertEqual(papers["alpha2020"]["abstract"], "We study alpha.")
        self.assertEqual(papers["alpha2020"]["venue"], "Journal of Alpha")
        self.assertEqual(papers["bare2020"]["abstract"], "Pool abstract")

    def test_a_link_that_is_not_http_is_not_offered(self) -> None:
        self.sidecar(bare2020={"status": "resolved", "link": "javascript:alert(1)"})
        self.assertIsNone(self.papers()["bare2020"]["link"])

    def test_only_a_resolved_record_is_read(self) -> None:
        self.sidecar(bare2020={"status": "not_found", "abstract": "Stale"})
        self.assertIsNone(self.papers()["bare2020"]["abstract"])

    def test_a_bad_sidecar_is_a_warning_and_the_rest_survives(self) -> None:
        write(self.root, self.SIDECAR, "{not json")
        body = paper_explorer.cited_papers(self.root)
        self.assertEqual([w["code"] for w in body["warnings"]], ["references"])
        self.assertEqual(len(body["papers"]), 2)


class DashboardWiringTests(unittest.TestCase):
    def test_the_view_is_reachable_from_the_graph_atlas(self) -> None:
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("switchGraph('cited')", page)
        self.assertIn('id="citedPapersContainer"', page)
        self.assertIn('src="./paper-explorer-panel.js?v=', page)

    def test_the_panel_reads_the_route_and_escapes_workspace_text(self) -> None:
        panel = (STATIC / "paper-explorer-panel.js").read_text(encoding="utf-8")
        self.assertIn("/api/atlas/cited-papers", panel)
        self.assertIn("esc(", panel)

    def test_the_summary_view_accepts_a_locate_request_from_its_parent_only(self) -> None:
        source = (REPO / "skills" / "_core" / "command_center" / "manuscript_graph.py").read_text(encoding="utf-8")
        self.assertIn("manuscript-graph-locate", source)
        self.assertIn("e.source !== window.parent", source)


if __name__ == "__main__":
    unittest.main()
