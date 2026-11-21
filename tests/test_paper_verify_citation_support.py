"""`verify` warns, never fails, about citations that look unsupported (#182).

Three advisory warnings, all deterministic and offline:

* `CITED_MORE_THAN_ONCE` -- only when `couplings.json` declares
  `"citation_policy": {"cite_once": true}`: a key cited more than once.
* `QUOTE_SHARES_NO_TERM_WITH_CLAIM` -- an evidence record that `holds` whose
  verbatim quote shares no content term with the claim it supports.
* `SOURCE_SHARES_NO_TERM_WITH_PAPER` -- a cited source whose title and abstract
  share no content term with the paper's title, abstract and declared
  contributions (a possible off-field source).

None touches `clean`, `holds`, `fails` or `unmeasured`. The pure function is
tested directly; the wiring through the real `paper_cli.py verify` reuses the
coupling fixture of `tests/test_paper_writing.py`.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_paper_writing import CLI, _build_coupling_paper, _coupling_record  # noqa: E402
sys.path.insert(0, str(FORGE_ROOT / "skills" / "paper-writing" / "scripts"))
import paper_couplings  # noqa: E402
import paper_verify  # noqa: E402
from impl_refusals import Refused  # noqa: E402

TEX = (b"\\title{Quantum kernels for cross-subject EEG motor imagery decoding}\n"
       b"\\begin{abstract}We align subject covariances with a quantum kernel to decode motor imagery "
       b"from electroencephalography.\\end{abstract}\n"
       b"Kernels help \\cite{havlicek2019}. Again \\cite{havlicek2019,adam2015}.\n"
       b"% \\cite{commented2020} never counts\n")
REFERENCES = {
    "havlicek2019": {"status": "resolved", "title": "Supervised learning with quantum enhanced feature spaces",
                     "abstract": "Quantum kernels map data to a feature space."},
    "adam2015": {"status": "resolved", "title": "Adam: a stochastic optimizer for deep networks",
                 "abstract": "First-order gradient-based optimization of stochastic objective functions."},
}
RECORD = {"facts": {"contributions": ["quantum kernel alignment"]}}


def codes(report: dict) -> dict:
    return {w["code"]: w for w in report.get("warnings") or []}


def attach(record=RECORD, evidence=(), references=REFERENCES, tex=TEX) -> dict:
    report = {"clean": True, "holds": 3, "fails": 0, "unmeasured": 0, "checks": []}
    out = paper_verify.attach_citation_warnings(report, tex, record, list(evidence), references)
    for field in ("clean", "holds", "fails", "unmeasured"):
        assert out[field] == report[field], field
    return out


class CiteOncePolicyTests(unittest.TestCase):
    def test_off_by_default(self) -> None:
        self.assertNotIn("CITED_MORE_THAN_ONCE", codes(attach()))

    def test_on_names_each_repeated_key_with_its_count(self) -> None:
        warning = codes(attach(record={**RECORD, "citation_policy": {"cite_once": True}}))["CITED_MORE_THAN_ONCE"]
        self.assertEqual(warning["keys"], ["havlicek2019"])
        self.assertEqual(warning["counts"], {"havlicek2019": 2})

    def test_a_commented_cite_is_not_a_citation(self) -> None:
        tex = TEX + b"% \\cite{adam2015} again\n"
        warning = codes(attach(record={"citation_policy": {"cite_once": True}}, tex=tex))["CITED_MORE_THAN_ONCE"]
        self.assertEqual(warning["keys"], ["havlicek2019"])

    def test_the_policy_shape_is_validated(self) -> None:
        green = _coupling_record()
        for bad in ({"citation_policy": True}, {"citation_policy": {"cite_once": "yes"}}):
            with self.subTest(bad=bad), self.assertRaises(Refused) as caught:
                paper_couplings.validate_couplings_shape({**green, **bad})
            self.assertEqual(caught.exception.code, "COUPLINGS_RECORD_MALFORMED")
            self.assertIn("citation_policy", str(caught.exception))
        paper_couplings.validate_couplings_shape({**green, "citation_policy": {"cite_once": False}})


class QuoteSupportTests(unittest.TestCase):
    def test_a_quote_unrelated_to_its_claim_is_flagged(self) -> None:
        evidence = [
            {"block_id": "intro.motivation", "cite_key": "havlicek2019", "verdict": "holds",
             "claim": "Quantum kernels separate motor imagery classes.",
             "quote": "The weather station recorded rainfall in April."},
            {"block_id": "intro.motivation", "cite_key": "havlicek2019", "verdict": "holds",
             "claim": "Quantum kernels map data to feature spaces.",
             "quote": "Quantum kernels map data to a feature space."},
            {"block_id": "intro.gap", "cite_key": "adam2015", "verdict": "does-not-hold",
             "claim": "Something else entirely.", "quote": "Unrelated words here."},
        ]
        warning = codes(attach(evidence=evidence))["QUOTE_SHARES_NO_TERM_WITH_CLAIM"]
        self.assertEqual(warning["keys"], ["havlicek2019"])
        self.assertEqual(len(warning["records"]), 1)
        self.assertEqual(warning["records"][0]["block_id"], "intro.motivation")

    def test_accents_and_inflection_still_match(self) -> None:
        evidence = [{"block_id": "b", "cite_key": "k", "verdict": "holds",
                     "claim": "La clasificación de señales mejora.", "quote": "clasificaciones de senales"}]
        self.assertNotIn("QUOTE_SHARES_NO_TERM_WITH_CLAIM", codes(attach(evidence=evidence)))


class OffFieldSourceTests(unittest.TestCase):
    def test_a_source_sharing_no_term_with_the_paper_is_flagged(self) -> None:
        warning = codes(attach())["SOURCE_SHARES_NO_TERM_WITH_PAPER"]
        self.assertEqual(warning["keys"], ["adam2015"])

    def test_no_paper_vocabulary_measures_nothing(self) -> None:
        self.assertNotIn("SOURCE_SHARES_NO_TERM_WITH_PAPER",
                         codes(attach(record={}, tex=b"\\cite{adam2015}\n")))

    def test_a_source_without_title_or_abstract_is_left_to_its_own_warning(self) -> None:
        refs = {**REFERENCES, "adam2015": {"status": "not_found"}}
        self.assertNotIn("SOURCE_SHARES_NO_TERM_WITH_PAPER", codes(attach(references=refs)))


class VerifyWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = FORGE_ROOT / ".scratch" / f".paper-verify-support-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.sections_dir = self.root / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)

    def verify(self) -> dict:
        proc = subprocess.run(
            [sys.executable, str(CLI), "verify", "--paper", str(self.paper_dir),
             "--sections", str(self.sections_dir)], capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def test_verify_reads_the_policy_and_the_evidence_store_and_stays_clean(self) -> None:
        before = self.verify()
        couplings = self.paper_dir / "couplings.json"
        record = json.loads(couplings.read_text(encoding="utf-8"))
        record["citation_policy"] = {"cite_once": True}
        couplings.write_text(json.dumps(record), encoding="utf-8")
        tex = self.paper_dir / "main.tex"
        tex.write_bytes(tex.read_bytes() + b"\nOnce \\cite{zeta2020}. Twice \\cite{zeta2020}.\n")
        store = self.paper_dir / ".paper-writing" / "evidence"
        store.mkdir(parents=True, exist_ok=True)
        (store / "intro.motivation.jsonl").write_text(json.dumps({
            "block_id": "intro.motivation", "cite_key": "zeta2020", "verdict": "holds",
            "claim": "Kernels improve decoding accuracy.", "quote": "Rainfall was recorded in April."}) + "\n",
            encoding="utf-8")
        after = self.verify()
        found = codes(after)
        self.assertEqual(found["CITED_MORE_THAN_ONCE"]["keys"], ["zeta2020"])
        self.assertEqual(found["QUOTE_SHARES_NO_TERM_WITH_CLAIM"]["keys"], ["zeta2020"])
        # Advisory only: no check carries these codes, so no verdict counts them.
        self.assertFalse({c.get("check") for c in after["checks"]} - {c.get("check") for c in before["checks"]})


if __name__ == "__main__":
    unittest.main()
