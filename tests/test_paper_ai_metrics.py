"""Unit tests for paper_ai_metrics: stylometry, burstiness, Claude fingerprints,
and F5 invariant verification.
"""
from __future__ import annotations

import io
import json
import hashlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))
sys.path.insert(0, str(REPO))
import paper_ai_metrics as metrics
import paper_cli
from skills._core.command_center import server


class BurstinessTests(unittest.TestCase):
    def test_flat_sentence_lengths_receive_high_penalty(self) -> None:
        # 5 sentences, each exactly 10 words -> CV = 0.0 -> penalty = 1.0
        sentences = [
            "The model processes the input data in a sequential manner.",
            "The system evaluates the output scores with a fixed threshold.",
            "The method optimizes the loss value across the training epochs.",
            "The network extracts the feature vectors from the raw signals.",
            "The framework computes the final prediction for each test sample.",
        ]
        res = metrics.compute_burstiness(sentences)
        self.assertEqual(res["sentence_count"], 5)
        self.assertAlmostEqual(res["cv"], 0.0, places=2)
        self.assertEqual(res["burstiness_penalty"], 1.0)

    def test_varied_cadence_receives_zero_penalty(self) -> None:
        # Varied sentence lengths (short punchy mixed with long complex): 4, 32, 7, 28 words
        sentences = [
            "We reject this hypothesis.",
            "Specifically, when the projection matrix is rank-deficient, the resulting optimization problem fails to converge within the allotted gradient iterations, thereby degrading the classification accuracy across all evaluation folds.",
            "Figure 2 illustrates the resulting manifold.",
            "Although prior approaches relied heavily on hand-crafted spatial filters, our formulation introduces an adaptive regularization term that directly penalizes spurious electrode correlations.",
        ]
        res = metrics.compute_burstiness(sentences)
        self.assertGreaterEqual(res["cv"], 0.45)
        self.assertEqual(res["burstiness_penalty"], 0.0)


class ClicheDetectionTests(unittest.TestCase):
    def test_detects_claude_cliches_and_phrases(self) -> None:
        text = (
            "In this work, we delve into the multifaceted landscape of quantum machine learning. "
            "Our bespoke architecture serves as a testament to the seamless interplay between classical and quantum circuits, "
            "which is paramount for robust performance. Not only does this framework foster scalability, but it also bolsters efficiency."
        )
        findings = metrics.detect_cliches(text)
        words_found = {f["target"].lower() for f in findings if f["type"] == "word"}
        self.assertTrue({"delve", "multifaceted", "landscape", "bespoke", "testament", "seamless", "interplay", "paramount", "foster", "bolsters"}.issubset(words_found))
        
        phrases_found = [f["category"] for f in findings if f["type"] == "phrase"]
        self.assertIn("not_only_but_also", phrases_found)

    def test_detects_triadic_parallelism(self) -> None:
        text = "The proposed algorithm ensures scalability, efficiency, and reliability across all benchmark datasets."
        findings = metrics.detect_cliches(text)
        syntactic = [f for f in findings if f["type"] == "syntax"]
        self.assertEqual(len(syntactic), 1)
        self.assertEqual(syntactic[0]["category"], "triadic_parallelism")

    def test_clean_human_academic_text_has_zero_cliches(self) -> None:
        # A typical LIA house style paragraph
        text = (
            "Materials and methods are structured as follows. "
            "First, the raw electroencephalographic signals are filtered using a fifth-order Butterworth bandpass filter. "
            "Next, spatial covariance matrices are estimated for each epoch and projected onto the Riemannian manifold. "
            "Table 1 summarizes the demographic characteristics of the recruited cohort."
        )
        findings = metrics.detect_cliches(text)
        self.assertEqual(len(findings), 0)


class CompositeScoreTests(unittest.TestCase):
    def test_ai_heavy_draft_is_flagged(self) -> None:
        ai_draft = (
            "We delve into the intricate landscape of brain-computer interfaces. "
            "Our bespoke methodology serves as a testament to the seamless interplay of quantum algorithms. "
            "It is worth noting that this architecture is paramount for unlocking vibrant solutions. "
            "Furthermore, not only does our model foster adaptability, but it also underscores the multifaceted nature of neural decoding. "
            "In conclusion, the proposed framework revolutionizes the realm of biomedical engineering."
        )
        result = metrics.analyze_ai_signatures(ai_draft)
        self.assertGreaterEqual(result["composite_score"], 0.50)
        self.assertEqual(result["verdict"], "ai_flagged")

    def test_clean_academic_text_is_classified_as_human(self) -> None:
        human_text = (
            "We evaluated the proposed classifier on 54 subjects from the public PhysioNet dataset. "
            "All recordings were acquired at 160 Hz using a standard 64-channel montage. "
            "Specifically, artifacts caused by ocular movements were removed using independent component analysis. "
            "The filtered signals were subsequently segmented into 3-second non-overlapping epochs. "
            "Overall, the median classification accuracy reached 84.5% across five cross-validation folds."
        )
        result = metrics.analyze_ai_signatures(human_text)
        self.assertLessEqual(result["composite_score"], 0.20)
        self.assertEqual(result["verdict"], "human")


class F5InvariantTests(unittest.TestCase):
    def test_valid_rephrase_preserves_invariants(self) -> None:
        orig = (
            "As demonstrated in \\cite{smith2024}, the model achieved an accuracy of 94.2% on the 128-channel montage. "
            "The loss function is defined as:\n"
            "\\begin{equation}\n"
            "\\mathcal{L} = \\lVert \\mathbf{y} - \\hat{\\mathbf{y}} \\rVert_2^2\n"
            "\\end{equation}\n"
        )
        # Rephrase changing sentence order and rhythm, but keeping citation, numbers and equation byte-identical
        hum = (
            "The network reached an accuracy of 94.2% using the 128-channel montage, in agreement with \\cite{smith2024}. "
            "The corresponding objective formulation is expressed as:\n"
            "\\begin{equation}\n"
            "\\mathcal{L} = \\lVert \\mathbf{y} - \\hat{\\mathbf{y}} \\rVert_2^2\n"
            "\\end{equation}\n"
        )
        passed, violations = metrics.verify_f5_invariants(orig, hum)
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)

    def test_altering_number_fails_f5_invariant(self) -> None:
        orig = "The learning rate was initialized to 0.001 with a batch size of 64."
        # Altered 0.001 to 0.01
        hum = "We initialized the learning rate to 0.01 and trained with a batch size of 64."
        passed, violations = metrics.verify_f5_invariants(orig, hum)
        self.assertFalse(passed)
        self.assertTrue(any("numbers or statistics altered" in v for v in violations))

    def test_dropping_citation_fails_f5_invariant(self) -> None:
        orig = "Prior work \\cite{vaswani2017} introduced multi-head attention mechanisms."
        hum = "Prior work introduced multi-head attention mechanisms."
        passed, violations = metrics.verify_f5_invariants(orig, hum)
        self.assertFalse(passed)
        self.assertTrue(any("Citations missing" in v for v in violations))

    def test_dropping_displayed_equation_fails_f5_invariant(self) -> None:
        orig = (
            "The reconstruction error is minimized:\n"
            "\\begin{equation}\n"
            "\\min_{\\theta} \\mathcal{L}(\\theta)\n"
            "\\end{equation}\n"
        )
        hum = "The reconstruction error is minimized across parameter space."
        passed, violations = metrics.verify_f5_invariants(orig, hum)
        self.assertFalse(passed)
        self.assertTrue(any("Displayed equation count mismatch" in v for v in violations))


class CliIntegrationTests(unittest.TestCase):
    def test_ai_audit_file_succeeds(self) -> None:
        fixture_path = REPO / "tests" / "fixtures" / "temp_ai_test.tex"
        fixture_path.write_text(
            "We delve into the multifaceted landscape of quantum machine learning. "
            "Not only does this architecture foster scalability, but it also bolsters efficiency.",
            encoding="utf-8",
        )
        try:
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                exit_code = paper_cli.main(["ai_audit", "--file", str(fixture_path.relative_to(REPO))])
            self.assertEqual(exit_code, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["command"], "ai_audit")
            self.assertIn("composite_score", payload)
            self.assertGreaterEqual(payload["composite_score"], 0.40)
        finally:
            fixture_path.unlink(missing_ok=True)

    def test_ai_audit_requires_target_argument(self) -> None:
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            exit_code = paper_cli.main(["ai_audit"])
        self.assertEqual(exit_code, 2)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], "TARGET_REQUIRED")

    def test_humanize_f5_violation_refuses(self) -> None:
        import shutil
        paper_dir = REPO / "tests" / "fixtures" / "temp_paper"
        paper_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / "main.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "%% paper-writing block intro begin sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n"
            "The model reached an accuracy of 95.4% using 64 channels \\cite{ref2024}.\n"
            "%% paper-writing block intro end\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        draft_file = REPO / "tests" / "fixtures" / "temp_draft.tex"
        # Alter number 95.4% to 92.0%
        draft_file.write_text(
            "The model reached an accuracy of 92.0% using 64 channels \\cite{ref2024}.\n",
            encoding="utf-8",
        )
        try:
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                exit_code = paper_cli.main([
                    "humanize",
                    "--block", "intro",
                    "--draft", str(draft_file.relative_to(REPO)),
                    "--paper", str(paper_dir.relative_to(REPO)),
                ])
            self.assertEqual(exit_code, 2)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "refused")
            self.assertEqual(payload["code"], "F5_INVARIANT_VIOLATION")
        finally:
            shutil.rmtree(paper_dir, ignore_errors=True)
            draft_file.unlink(missing_ok=True)

    def test_humanize_success_and_apply(self) -> None:
        import hashlib
        import shutil
        paper_dir = REPO / "tests" / "fixtures" / "temp_paper_ok"
        paper_dir.mkdir(parents=True, exist_ok=True)
        orig_body = "The model reached an accuracy of 95.4% using 64 channels \\cite{ref2024}.\n"
        digest = hashlib.sha256(orig_body.encode("utf-8")).hexdigest()
        (paper_dir / "main.tex").write_text(
            f"\\documentclass{{article}}\n\\begin{{document}}\n"
            f"%% paper-writing block intro begin sha256={digest}\n"
            f"{orig_body}"
            f"%% paper-writing block intro end\n"
            f"\\end{{document}}\n",
            encoding="utf-8",
        )
        draft_file = REPO / "tests" / "fixtures" / "temp_draft_ok.tex"
        # Natural rephrase preserving numbers and citation
        draft_file.write_text(
            "Using 64 channels, the model reached an accuracy of 95.4% \\cite{ref2024}.\n",
            encoding="utf-8",
        )
        try:
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                exit_code = paper_cli.main([
                    "humanize",
                    "--block", "intro",
                    "--draft", str(draft_file.relative_to(REPO)),
                    "--paper", str(paper_dir.relative_to(REPO)),
                    "--apply",
                ])
            self.assertEqual(exit_code, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["f5_invariants_preserved"])
            self.assertTrue(payload["applied"])
            updated_tex = (paper_dir / "main.tex").read_text(encoding="utf-8")
            self.assertIn("Using 64 channels, the model reached an accuracy of 95.4%", updated_tex)
        finally:
            shutil.rmtree(paper_dir, ignore_errors=True)
            draft_file.unlink(missing_ok=True)

    def test_ai_audit_whole_manuscript_cli(self) -> None:
        paper_dir = REPO / "tests" / "fixtures" / "temp_paper_whole"
        paper_dir.mkdir(parents=True, exist_ok=True)
        main_tex = paper_dir / "main.tex"
        main_tex.write_text(
            "\\begin{document}\n"
            "%% paper-writing block intro begin sha256=1111111111111111111111111111111111111111111111111111111111111111\n"
            "We delve into this framework. It serves as a testament to progress.\n"
            "%% paper-writing block intro end\n"
            "%% paper-writing block methods begin sha256=2222222222222222222222222222222222222222222222222222222222222222\n"
            "We evaluate 32 subjects using cross-validation over 10 folds.\n"
            "%% paper-writing block methods end\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        try:
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                exit_code = paper_cli.main([
                    "ai_audit",
                    "--all",
                    "--paper", str(paper_dir.relative_to(REPO)),
                ])
            self.assertEqual(exit_code, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["target"], "manuscript:main.tex")
            self.assertEqual(payload["blocks_analyzed"], 2)
            self.assertIn("intro", payload["blocks"])
            self.assertIn("methods", payload["blocks"])
            self.assertIn("composite_score", payload)
        finally:
            shutil.rmtree(paper_dir, ignore_errors=True)

    def test_humanize_with_replacement_and_inplace(self) -> None:
        paper_dir = REPO / "tests" / "fixtures" / "temp_paper_inplace"
        paper_dir.mkdir(parents=True, exist_ok=True)
        main_tex = paper_dir / "main.tex"
        orig_body = "In this work, we delve into 12 metrics \\cite{smith2025}.\n"
        digest = hashlib.sha256(orig_body.encode("utf-8")).hexdigest()
        main_tex.write_text(
            f"%% paper-writing block b1 begin sha256={digest}\n"
            f"{orig_body}"
            f"%% paper-writing block b1 end\n",
            encoding="utf-8",
        )
        try:
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                exit_code = paper_cli.main([
                    "humanize",
                    "--block", "b1",
                    "--replacement", "Here we investigate 12 metrics \\cite{smith2025}.\n",
                    "--inplace",
                    "--paper", str(paper_dir.relative_to(REPO)),
                ])
            self.assertEqual(exit_code, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["f5_invariants_preserved"])
            self.assertTrue(payload["applied"])
            updated = main_tex.read_text(encoding="utf-8")
            self.assertIn("Here we investigate 12 metrics", updated)
        finally:
            shutil.rmtree(paper_dir, ignore_errors=True)


class ServerEndpointTests(unittest.TestCase):
    def test_ai_audit_endpoint_with_text(self) -> None:
        client = TestClient(server.create_app(REPO))
        res = client.post("/api/pdf/ai-audit", json={
            "text": "We delve into the multifaceted landscape of quantum machine learning. "
                    "Not only does this architecture foster scalability, but it also bolsters efficiency."
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertIn("composite_score", data)
        self.assertIn("burstiness", data)
        self.assertIn("cliches", data)
        self.assertGreaterEqual(data["composite_score"], 0.40)

    def test_ai_audit_endpoint_manuscript(self) -> None:
        client = TestClient(server.create_app(REPO))
        res = client.post("/api/pdf/ai-audit", json={})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["scope"], "manuscript")
        self.assertIn("composite_score", data)
        self.assertIn("blocks", data)

    def test_write_block_includes_ai_stylometry(self) -> None:
        import paper_write
        paper_dir = REPO / "tests" / "fixtures" / "temp_paper_wb"
        paper_dir.mkdir(parents=True, exist_ok=True)
        main_tex = paper_dir / "main.tex"
        main_tex.write_text(
            "%% paper-writing block intro begin sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n"
            "%% paper-writing block intro end\n",
            encoding="utf-8",
        )
        contract = paper_write.BlockContract(
            block_id="intro",
            contract_prose="## Disqualifiers\n- None.\n",
            contract_source="contract.md",
            citations_regime="none",
            mode="argument",
            requires_facts=(),
            evidence_set=(),
        )
        sentence = "In this section, we provide an overview of the proposed framework."
        draft = {
            "latex": sentence,
            "bindings": [{"sentence": sentence, "binding": "structural"}],
        }
        audit = {"verdicts": [{"bullet": "None.", "verdict": "clear"}]}
        try:
            res = paper_write.write_block(paper_dir, contract, draft, audit)
            self.assertEqual(res["status"], "written")
            self.assertIn("aiStylometry", res)
            self.assertIn("composite_score", res["aiStylometry"])
            self.assertIn("burstiness", res["aiStylometry"])
            self.assertIn("cliches", res["aiStylometry"])
        finally:
            shutil.rmtree(paper_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
