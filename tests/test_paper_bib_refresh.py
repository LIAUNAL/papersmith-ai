"""`bib refresh`: relink an existing citation's evidence to fresher cached
metadata of the SAME work, without re-judging its source.

Every fixture runs through the real `paper_cli.py` subprocess under the
already-gitignored `.scratch/` tree (the CLI resolves `--paper`/`--guidance`
against the real repository root, so a system temp directory would refuse
`PAPER_OUTSIDE_REPOSITORY`) and is removed afterward. The cited source sits
in a folder classed `style-reference`: `validate` refuses to quote it as new
evidence, and the refresh must leave that refusal exactly where it is.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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

OLD_DIGEST = "a" * 64
NEW_DIGEST = "b" * 64
QUOTE = "weights each instance by its attention score"


def _cache(paper_dir: Path, digest: str, *, year, identifier="10.1234/ABC.5",
           doi="10.1234/abc.5", resolver="crossref", own_digest=None) -> None:
    paper_resolve.cache_metadata(paper_dir, {
        "identifier": identifier, "resolver": resolver,
        "metadata_digest": own_digest or digest, "title": "Attention MIL",
        "doi": doi, "year": year, "authors": ["Ada Smith"], "venue": "Neural Journal",
    })
    if own_digest is not None:
        # `cache_metadata` keys the file by the blob's own digest; a tampered
        # blob is one filed under a digest it does not itself carry.
        (paper_resolve.metadata_dir(paper_dir) / f"{own_digest}.json").rename(
            paper_resolve.metadata_dir(paper_dir) / f"{digest}.json"
        )


class BibRefreshCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = FORGE_ROOT / ".scratch" / f".paper-bib-refresh-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.guidance = self.root / "guidance"
        folder = self.guidance / "related-work"
        (folder / "smith2024").mkdir(parents=True)
        (folder / ".paper-writing.json").write_text('{"class": "style-reference"}', encoding="utf-8")
        self.source_md = folder / "smith2024" / "smith2024.md"
        self.source_md.write_text(f"The model {QUOTE} before pooling.\n", encoding="utf-8")
        self.assertEqual(self._run("scaffold", "--paper", str(self.paper_dir)).returncode, 0)
        (self.paper_dir / "main.tex").write_text("See \\cite{smith2024}.\n", encoding="utf-8")
        _cache(self.paper_dir, OLD_DIGEST, year=None)
        _cache(self.paper_dir, NEW_DIGEST, year=2024)
        # An older, superseded record in a store sorted first, then the
        # winning record `bib build` reads (last-write-wins per cite key).
        self._append("aa-early", "an early claim", round_number=1)
        self.winner = self._append("rw-blocks", "attention weights each instance", round_number=4)

    def _append(self, block_id: str, claim: str, *, round_number: int, cite_key="smith2024") -> dict:
        span = paper_evidence.EvidenceSpan.locate(self.source_md, QUOTE)
        record = paper_evidence.EvidenceRecord.from_verdict(
            block_id=block_id, regime="none", claim=claim, cite_key=cite_key,
            identifier="10.1234/ABC.5", resolver="crossref", metadata_digest=OLD_DIGEST,
            verdict=paper_evidence.Verdict.holds(span), round=round_number,
        )
        paper_evidence.append_record(self.paper_dir, record)
        return record.to_json()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, timeout=30)

    def _refresh(self, *extra: str, cite_key="smith2024", digest=NEW_DIGEST) -> subprocess.CompletedProcess:
        return self._run(
            "bib", "refresh", "--paper", str(self.paper_dir), "--guidance", str(self.guidance),
            "--cite-key", cite_key, "--metadata-digest", digest, *extra,
        )

    def _snapshot(self) -> dict:
        state = self.paper_dir / ".paper-writing"
        return {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in sorted([*state.rglob("*"), *self.guidance.rglob("*"), self.paper_dir / "refs.bib"])
            if p.is_file()
        }

    def test_refresh_relinks_a_style_reference_citation_changing_only_resolver_and_digest(self) -> None:
        # validate's protection for NEW evidence still refuses this source.
        before = self._snapshot()
        proc = self._run(
            "validate", "--paper", str(self.paper_dir), "--guidance", str(self.guidance),
            "--block", "rw-blocks", "--claim", "c", "--quote", QUOTE,
            "--source-md", str(self.source_md), "--verdict", "holds", "--cite-key", "smith2024",
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "SOURCE_STYLE_REFERENCE")
        self.assertEqual(self._snapshot(), before)

        store = self.paper_dir / ".paper-writing" / "evidence" / "rw-blocks.jsonl"
        early = (self.paper_dir / ".paper-writing" / "evidence" / "aa-early.jsonl").read_bytes()
        old_bytes = store.read_bytes()
        proc = self._refresh()

        self.assertEqual((proc.returncode, proc.stderr), (0, ""), proc.stdout)
        self.assertEqual(json.loads(proc.stdout), {
            "status": "ok", "command": "bib", "cite_key": "smith2024", "refreshed": True,
            "block": "rw-blocks", "path": str(store), "resolver": "crossref",
            "metadata_digest": NEW_DIGEST, "previous_metadata_digest": OLD_DIGEST, "year": 2024,
        })
        new_bytes = store.read_bytes()
        self.assertTrue(new_bytes.startswith(old_bytes))
        appended = json.loads(new_bytes[len(old_bytes):])
        self.assertEqual(appended, {**self.winner, "metadata_digest": NEW_DIGEST})
        self.assertEqual((self.paper_dir / ".paper-writing" / "evidence" / "aa-early.jsonl").read_bytes(), early)
        self.assertFalse((self.guidance / "related-work" / ".papersmith-evidence.json").exists())

        proc = self._run("bib", "build", "--paper", str(self.paper_dir), "--guidance", str(self.guidance))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("  year = {2024},\n", (self.paper_dir / "refs.bib").read_text(encoding="utf-8"))

        # A second identical refresh is a no-op, never a duplicate line.
        settled = self._snapshot()
        proc = self._refresh()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertFalse(json.loads(proc.stdout)["refreshed"])
        self.assertEqual(self._snapshot(), settled)

    def test_bib_build_before_refresh_reads_the_old_metadata_unchanged(self) -> None:
        proc = self._run("bib", "build", "--paper", str(self.paper_dir), "--guidance", str(self.guidance))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        text = (self.paper_dir / "refs.bib").read_text(encoding="utf-8")
        self.assertIn(f"metadata_digest={OLD_DIGEST}", text)
        self.assertNotIn("year =", text)

    def test_bib_build_still_rejects_refresh_only_flags(self) -> None:
        proc = self._run("bib", "build", "--paper", str(self.paper_dir), "--cite-key", "smith2024")
        self.assertEqual((proc.returncode, proc.stdout), (2, ""))
        self.assertIn("unrecognized arguments: --cite-key smith2024", proc.stderr)

    def test_every_refusal_writes_nothing(self) -> None:
        other = "c" * 64
        cases = {
            "unknown cite key": (
                lambda: None, (), {"cite_key": "nobody2020"},
                "ENTRY_UNSOURCED", "'nobody2020': no evidence record carries this cite key -- "
                "refresh relinks existing evidence and never creates any",
            ),
            "new digest not cached": (
                lambda: None, (), {"digest": other}, "ENTRY_UNSOURCED",
                f"'smith2024': no cached metadata found for digest '{other}'",
            ),
            "tampered new cache": (
                lambda: _cache(self.paper_dir, other, year=2024, own_digest="d" * 64), (),
                {"digest": other}, "ENTRY_UNSOURCED",
                "'smith2024': the cached blob's own digest does not match the digest it was looked up by",
            ),
            "different work": (
                lambda: _cache(self.paper_dir, other, year=2024, identifier="10.1234/abc.6",
                               doi="10.1234/abc.6"), (), {"digest": other}, "ENTRY_UNSOURCED",
                f"'smith2024': cached metadata '{other}' does not identify the same work as its "
                "evidence record (record doi:10.1234/abc.5, current doi:10.1234/abc.5, "
                "new doi:10.1234/abc.6)",
            ),
            "an arXiv work for a DOI citation": (
                lambda: _cache(self.paper_dir, other, year=2024, identifier="2401.00001v3",
                               doi=None, resolver="arxiv"), (), {"digest": other}, "ENTRY_UNSOURCED",
                f"'smith2024': cached metadata '{other}' does not identify the same work as its "
                "evidence record (record doi:10.1234/abc.5, current doi:10.1234/abc.5, "
                "new arxiv:2401.00001v3)",
            ),
            "resolver mismatch": (
                lambda: None, ("--resolver", "openalex"), {}, "ENTRY_UNSOURCED",
                "'smith2024': --resolver 'openalex' does not match the cached metadata's resolver 'crossref'",
            ),
            "no located evidence": (
                lambda: paper_evidence.append_record(self.paper_dir, paper_evidence.EvidenceRecord.from_verdict(
                    block_id="rw-blocks", regime="none", claim="x", cite_key="smith2024",
                    identifier="10.1234/ABC.5", resolver="crossref", metadata_digest=OLD_DIGEST,
                    verdict=paper_evidence.Verdict.insufficient("not found"), round=5,
                )), (), {}, "ENTRY_NOT_INGESTED",
                "'smith2024': its current evidence record carries no located, verdict-bearing span -- "
                "refresh relinks existing located evidence only and never creates any",
            ),
            "source no longer ingested": (
                lambda: self.source_md.unlink(), (), {}, "ENTRY_NOT_INGESTED",
                lambda: f"'smith2024': {str(self.source_md)!r} is not an ingested paper under {self.guidance} "
                "(guidance/<root>/<paper>/<paper>.md) -- place the cited PDF under guidance/<section>/ "
                "and run the paper-ingestion skill over it first",
            ),
            "winner outside its own store": (
                lambda: (self.paper_dir / ".paper-writing" / "evidence" / "zz-moved.jsonl").write_text(
                    json.dumps(self.winner) + "\n", encoding="utf-8"), (), {}, "ENTRY_UNSOURCED",
                "'smith2024': its current evidence record is not the last line of its own block's store "
                "'rw-blocks' -- an appended copy would not supersede it",
            ),
        }
        for name, (prepare, extra, kwargs, code, detail) in cases.items():
            with self.subTest(name):
                shutil.rmtree(self.root, ignore_errors=True)
                self.setUp()
                prepare()
                before = self._snapshot()
                proc = self._refresh(*extra, **kwargs)
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stderr, "")
                self.assertEqual(proc.stdout, json.dumps(
                    {"status": "refused", "code": code,
                     "detail": detail() if callable(detail) else detail}) + "\n")
                self.assertEqual(self._snapshot(), before)


class SourceIdentityTests(unittest.TestCase):
    def test_doi_and_arxiv_spellings_of_one_work_agree_and_versions_do_not(self) -> None:
        identity = paper_bib.source_identity
        self.assertEqual(identity("https://doi.org/10.1109/TNSRE.2021.1", "crossref"),
                         identity("10.1109/tnsre.2021.1", "openalex"))
        self.assertEqual(identity("doi:10.1/X", "crossref"), ("doi", "10.1/x"))
        self.assertEqual(identity("https://arxiv.org/abs/2401.00001v2", "arxiv"),
                         identity("arXiv:2401.00001v2", "arxiv"))
        self.assertEqual(identity("https://arxiv.org/pdf/2401.00001v2.pdf", "arxiv"),
                         ("arxiv", "2401.00001v2"))
        self.assertNotEqual(identity("2401.00001v2", "arxiv"), identity("2401.00001", "arxiv"))
        self.assertNotEqual(identity("10.48550/arXiv.2401.00001", "crossref"),
                            identity("2401.00001", "arxiv"))
        self.assertIsNone(identity("10.1/x", "scholar"))
        self.assertIsNone(identity("  ", "crossref"))


if __name__ == "__main__":
    unittest.main()
