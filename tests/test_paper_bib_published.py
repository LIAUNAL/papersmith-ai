"""`bib build` prefers the published record over the arXiv one, and normalizes
HTML entities and entry types (#182).

Every rule is observed through `paper_bib.build_refs_bib`, the function
`cmd_bib` calls, asserting the bytes written to `refs.bib` and the warnings it
returns; one test runs the real `paper_cli.py bib build` to show the warning
reaches the verb's JSON. Fixtures are offline: cached metadata and the
`resolve --references` sidecar are written to disk, never fetched.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
CLI = SKILL_SCRIPTS / "paper_cli.py"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_bib  # noqa: E402
import paper_evidence  # noqa: E402
import paper_resolve  # noqa: E402

QUOTE = "weights each instance by its attention score"
ARXIV_DIGEST = "a" * 64
TITLE = "Attention-Based Deep Multiple Instance Learning"


def _digest(n: int) -> str:
    return f"{n:064x}"


class _Paper:
    """A paper dir plus an ingested guidance paper, under `root`."""

    def __init__(self, root: Path) -> None:
        self.paper_dir = root / "paper"
        self.paper_dir.mkdir(parents=True)
        self.guidance = root / "guidance"
        folder = self.guidance / "methods" / "ilse2018"
        folder.mkdir(parents=True)
        self.source_md = folder / "ilse2018.md"
        self.source_md.write_text(f"The model {QUOTE} before pooling.\n", encoding="utf-8")
        self.records: list[dict] = []

    def cite(self, key: str, metadata: dict) -> None:
        paper_resolve.cache_metadata(self.paper_dir, metadata)
        span = paper_evidence.EvidenceSpan.locate(self.source_md, QUOTE)
        record = paper_evidence.EvidenceRecord.from_verdict(
            block_id="methods", regime="resolution", claim=f"claim for {key}", cite_key=key,
            identifier=metadata["identifier"], resolver=metadata["resolver"],
            metadata_digest=metadata["metadata_digest"], verdict=paper_evidence.Verdict.holds(span), round=1,
        )
        paper_evidence.append_record(self.paper_dir, record)

    def sidecar(self, references: dict) -> None:
        path = paper_bib.references_path(self.paper_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": paper_bib.REFERENCES_SCHEMA, "references": references}),
                        encoding="utf-8")

    def build(self) -> dict:
        records = paper_evidence.read_all_records(self.paper_dir)
        return paper_bib.build_refs_bib(self.paper_dir, records, guidance_dir=self.guidance)

    def refs(self) -> str:
        return (self.paper_dir / "refs.bib").read_text(encoding="utf-8")


def _arxiv(**over) -> dict:
    metadata = {
        "identifier": "1802.04712", "resolver": "arxiv", "metadata_digest": ARXIV_DIGEST,
        "title": TITLE, "doi": None, "year": 2018,
        "authors": ["Maximilian Ilse", "Jakub Tomczak", "Max Welling"], "venue": "arXiv",
    }
    metadata.update(over)
    return metadata


class _TempPaperCase(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="paper-bib-published-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.paper = _Paper(root)


class PublishedRecordTests(_TempPaperCase):
    def test_the_sidecar_published_record_replaces_the_arxiv_venue(self) -> None:
        self.paper.cite("ilse2018", _arxiv())
        self.paper.sidecar({"ilse2018": {
            "status": "resolved", "resolver": "openalex", "identifier": "1802.04712",
            "title": TITLE, "abstract": None, "year": 2018,
            "venue": "Proceedings of Machine Learning Research",
            "link": "https://doi.org/10.5555/3327345.3327399", "digest": "f" * 64,
            "retrieved": "2026-01-01T00:00:00Z",
        }})

        result = self.paper.build()

        self.assertEqual(self.paper.refs(), (
            f"% resolver=arxiv; metadata_digest={ARXIV_DIGEST}\n"
            "% published record: references.json (openalex)\n"
            "@inproceedings{ilse2018,\n"
            "  author = {Maximilian Ilse and Jakub Tomczak and Max Welling},\n"
            "  title = {Attention-Based Deep Multiple Instance Learning},\n"
            "  booktitle = {Proceedings of Machine Learning Research},\n"
            "  doi = {10.5555/3327345.3327399},\n"
            "  year = {2018},\n"
            "}\n"
        ))
        self.assertEqual(result["published"], {"ilse2018": "Proceedings of Machine Learning Research"})
        self.assertNotIn("warnings", result)

    def test_a_cached_journal_resolution_of_the_same_title_replaces_the_arxiv_venue(self) -> None:
        self.paper.cite("ilse2018", _arxiv())
        paper_resolve.cache_metadata(self.paper.paper_dir, {
            "identifier": "10.1000/jmlr.1", "resolver": "crossref", "metadata_digest": _digest(7),
            "title": "Attention-based deep multiple instance learning.", "doi": "10.1000/jmlr.1",
            "year": 2019, "authors": ["M. Ilse"], "venue": "Journal of Machine Learning Research",
        })

        result = self.paper.build()

        text = self.paper.refs()
        self.assertIn("@article{ilse2018,\n", text)
        self.assertIn("  journal = {Journal of Machine Learning Research},\n", text)
        self.assertIn("  doi = {10.1000/jmlr.1},\n  year = {2019},\n", text)
        # Authors and title stay the evidence record's own.
        self.assertIn("  author = {Maximilian Ilse and Jakub Tomczak and Max Welling},\n", text)
        self.assertIn(f"% published record: metadata_digest={_digest(7)}\n", text)
        self.assertNotIn("arXiv", text)
        self.assertNotIn("warnings", result)

    def test_without_a_published_record_arxiv_stays_and_the_key_is_warned(self) -> None:
        self.paper.cite("ilse2018", _arxiv())
        # A resolved sidecar record of ANOTHER title is not the same work.
        self.paper.sidecar({"ilse2018": {
            "status": "resolved", "resolver": "openalex", "identifier": "10.1/other",
            "title": "A Different Paper", "venue": "Neural Journal", "year": 2018,
        }})

        result = self.paper.build()

        self.assertIn("@article{ilse2018,\n", self.paper.refs())
        self.assertIn("  journal = {arXiv},\n", self.paper.refs())
        self.assertNotIn("published record", self.paper.refs())
        self.assertEqual(len(result["warnings"]), 1)
        self.assertTrue(result["warnings"][0].startswith("ilse2018: rendered as the arXiv preprint"))
        self.assertNotIn("published", result)

    def test_an_unreadable_sidecar_offline_warns_and_never_fails(self) -> None:
        self.paper.cite("ilse2018", _arxiv(venue="arXiv (Cornell University)"))
        path = paper_bib.references_path(self.paper.paper_dir)
        path.write_text("{ not json", encoding="utf-8")

        result = self.paper.build()

        self.assertIn("  journal = {arXiv (Cornell University)},\n", self.paper.refs())
        self.assertEqual([w.split(":")[0] for w in result["warnings"]], ["ilse2018"])

    def test_an_arxiv_datacite_doi_counts_as_the_preprint(self) -> None:
        self.paper.cite("ilse2018", _arxiv(resolver="openalex", venue="", doi="10.48550/arXiv.1802.04712"))

        result = self.paper.build()

        self.assertEqual([w.split(":")[0] for w in result["warnings"]], ["ilse2018"])


class EntityAndTypeTests(_TempPaperCase):
    def test_html_entities_are_decoded_then_escaped_once(self) -> None:
        self.paper.cite("amp2021", {
            "identifier": "10.1/amp", "resolver": "crossref", "metadata_digest": _digest(1),
            "title": "Graphs &amp;amp; Nets &lt;fast&gt; R&D", "doi": "10.1/amp", "year": 2021,
            "authors": ["Smith &amp; Jones"], "venue": "Journal of A &amp; B",
        })

        self.paper.build()
        first = self.paper.refs()
        self.paper.build()

        self.assertIn(r"  title = {Graphs \& Nets <fast> R\&D},", first)
        self.assertIn(r"  author = {Smith \& Jones},", first)
        self.assertIn(r"  journal = {Journal of A \& B},", first)
        self.assertNotIn("amp;", first)
        self.assertEqual(self.paper.refs(), first)
        self.assertEqual(paper_bib._decode_entities("A &amp;amp; B"), "A & B")
        self.assertEqual(paper_bib._decode_entities("A & B"), "A & B")

    def _kind_of(self, key: str, venue: str, doi: str) -> str:
        """`"@<type>{<key>, <venue field>"` of the written entry."""
        self.paper.cite(key, {
            "identifier": doi, "resolver": "crossref", "metadata_digest": _digest(len(key) + 100),
            "title": f"Title {key}", "doi": doi, "year": 2022, "authors": ["A. Author"], "venue": venue,
        })
        self.paper.build()
        lines = self.paper.refs().splitlines()
        header = next(line for line in lines if line.startswith("@"))
        field = next(line.split(" = ")[0].strip() for line in lines
                     if line.strip().startswith(("journal =", "booktitle =", "howpublished =")))
        return f"{header} {field}"

    def test_a_proceedings_venue_is_inproceedings_with_booktitle(self) -> None:
        self.assertEqual(self._kind_of("conf", "Proceedings of the 40th International Conference on Machine "
                                       "Learning", "10.1/conf"), "@inproceedings{conf, booktitle")

    def test_a_journal_named_proceedings_stays_an_article(self) -> None:
        self.assertEqual(self._kind_of("pieee", "Proceedings of the IEEE", "10.1109/x"), "@article{pieee, journal")

    def test_a_data_repository_record_stays_a_dataset(self) -> None:
        self.assertEqual(self._kind_of("zen", "Zenodo", "10.5281/zenodo.123"), "@misc{zen, howpublished")

    def test_a_paper_with_a_dataset_doi_and_a_journal_venue_is_an_article(self) -> None:
        self.assertEqual(self._kind_of("paper", "Scientific Data Journal", "10.5281/zenodo.9"),
                         "@article{paper, journal")

    def test_an_untouched_entry_is_byte_identical(self) -> None:
        self.paper.cite("smith2024", {
            "identifier": "10.1234/abc.5", "resolver": "crossref", "metadata_digest": _digest(2),
            "title": "Attention MIL & Friends_v2", "doi": "10.1234/abc.5", "year": 2024,
            "authors": ["Ada Smith", "Óscar Gómez"], "venue": "Neural Journal",
        })

        result = self.paper.build()

        self.assertEqual(self.paper.refs(), (
            f"% resolver=crossref; metadata_digest={_digest(2)}\n"
            "@article{smith2024,\n"
            "  author = {Ada Smith and {\\relax Ó}scar Gómez},\n"
            "  title = {Attention MIL \\& Friends\\_v2},\n"
            "  journal = {Neural Journal},\n"
            "  doi = {10.1234/abc.5},\n"
            "  year = {2024},\n"
            "}\n"
        ))
        self.assertEqual(set(result), {"path", "entries"})


class CliWarningTests(unittest.TestCase):
    """`--paper` must resolve inside the repository, so this one fixture lives
    under the gitignored `.scratch/` tree and is removed afterward."""

    def test_bib_build_reports_the_arxiv_warning_in_its_json(self) -> None:
        root = FORGE_ROOT / ".scratch" / f".paper-bib-published-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        root.mkdir(parents=True)
        paper = _Paper(root)
        paper.cite("ilse2018", _arxiv())
        (paper.paper_dir / "main.tex").write_text(
            "\\documentclass{article}\\begin{document}\\cite{ilse2018}\\end{document}\n", encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(CLI), "bib", "build", "--paper", str(paper.paper_dir),
             "--guidance", str(paper.guidance)],
            capture_output=True, text=True, timeout=60,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        out = json.loads(proc.stdout)
        self.assertEqual([w.split(":")[0] for w in out["warnings"]], ["ilse2018"])
        self.assertIn("@article{ilse2018,", paper.refs())


if __name__ == "__main__":
    unittest.main()
