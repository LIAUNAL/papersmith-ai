"""experiment-diagrams at print size (specs S1 and S3 of
`odd/tasks/figure-and-table-quality.md`), through `diagram_cli.py`'s verbs:
explicit `\\fontsize` sizes computed from the manuscript body size, no
background, the TeX log kept, overfull boxes refused, the mechanical audit
written by `render`/`audit` and required by `validate`.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_experiment_diagrams import (  # noqa: E402
    REPO, _Workspace, _load_cli, _raster_available, _tex_available, run_cli,
)

sys.path.insert(0, str(REPO / "skills" / "_core" / "figure"))
import diagram_audit  # noqa: E402

STATEMENT = "aprobado"


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory(prefix="experiment-diagrams-print-")
        self.addCleanup(holder.cleanup)
        self.ws = _Workspace(Path(holder.name))

    def spec(self, kind: str = "experiments", **changes) -> Path:
        self.ws.approve(kind)
        run_cli("derive", "--target", str(self.ws.target), "--name", "Sample", "--kind", kind)
        path = self.ws.product / "diagrams" / f"{kind}.json"
        if changes:
            spec = json.loads(path.read_text(encoding="utf-8"))
            spec.update(changes)
            path.write_text(json.dumps(spec), encoding="utf-8")
        return path

    def tex_without_toolchain(self, spec_path: Path) -> str:
        """`render` writes the .tex before it looks for TeX."""
        cli = _load_cli()
        with mock.patch.dict(os.environ, {"PATH": ""}), \
                mock.patch.object(cli, "TEX_FALLBACK_DIRS", ()), \
                contextlib.redirect_stdout(io.StringIO()):
            cli.main(["render", "--spec", str(spec_path)])
        return spec_path.with_suffix(".tex").read_text(encoding="utf-8")


class SourceTests(_Base):

    def test_every_size_is_an_explicit_fontsize_inside_the_print_range(self) -> None:
        tex = self.tex_without_toolchain(self.spec())
        self.assertEqual(diagram_audit.find_size_switches(tex), [])
        sizes = [float(size) for size in re.findall(r"\\fontsize\{([\d.]+)\}", tex)]
        self.assertEqual(len(sizes), 4)
        self.assertGreaterEqual(min(sizes), 7.0)  # 0.70 x the 10 pt default body
        self.assertLessEqual(max(sizes), 9.0)  # 0.90 x the 10 pt default body

    def test_the_body_size_is_read_from_the_manuscript(self) -> None:
        (self.ws.root / "paper").mkdir()
        (self.ws.root / "paper" / "main.tex").write_text(
            "\\documentclass[11pt]{article}\n\\begin{document}\n\\end{document}\n", encoding="utf-8")
        tex = self.tex_without_toolchain(self.spec())
        self.assertIn(r"\newcommand{\psSpineFont}{\fontsize{9.02}{10.82}\selectfont}", tex)
        self.assertIn(r"\newcommand{\psNoteFont}{\fontsize{8.36}{10.03}\selectfont}", tex)

    def test_the_paper_export_draws_no_background(self) -> None:
        tex = self.tex_without_toolchain(self.spec())
        self.assertNotIn("show background rectangle", tex)
        self.assertNotIn("fill=psCanvas", tex)
        self.assertIn("\\documentclass[border=2pt]{standalone}", tex)

    def test_a_bad_print_block_is_refused_naming_the_field(self) -> None:
        code, payload = run_cli("render", "--spec", str(self.spec(print={"width_fraction": 3})))
        self.assertEqual((code, payload["error"]), (2, "SPEC_INVALID"))
        self.assertIn("print.width_fraction", payload["message"])


class ValidateGateTests(_Base):
    """`validate` shows the audit and requires it to pass for the PNG drawn
    now, unless the operator's own words override it."""

    def drawn(self, audit: str | None, *, for_png: bytes | None = None) -> str:
        self.ws.approve("poc")
        folder = self.ws.product / "diagrams"
        folder.mkdir(parents=True, exist_ok=True)
        png = folder / "poc.png"
        png.write_bytes(b"\x89PNG drawing")
        (folder / "poc.json").write_text("{}\n", encoding="utf-8")
        sha = hashlib.sha256(png.read_bytes()).hexdigest()
        if audit is not None:
            audited = hashlib.sha256(for_png).hexdigest() if for_png else sha
            (folder / "poc.audit.json").write_text(json.dumps({
                "kind": "poc", "verdict": audit, "png_sha256": audited,
                "failures": [] if audit == "pass" else ["text_overlap"],
                "messages": [] if audit == "pass" else ["text_overlap: Alpha / Gamma"],
            }), encoding="utf-8")
        return sha

    def validate(self, sha: str, *extra: str) -> tuple[int, dict]:
        return run_cli("validate", "--target", str(self.ws.target), "--name", "Sample", "--kind", "poc",
                       "--png-sha256", sha, "--operator-statement", STATEMENT, *extra)

    def record(self) -> Path:
        return self.ws.product / "diagrams" / "poc.validated.json"

    def test_a_failing_audit_is_refused_and_shown(self) -> None:
        code, payload = self.validate(self.drawn("fail"))
        self.assertEqual((code, payload["error"]), (2, "AUDIT_NOT_PASSED"))
        self.assertIn("text_overlap: Alpha / Gamma", payload["message"])
        self.assertEqual(payload["audit"]["verdict"], "fail")
        self.assertFalse(self.record().exists())

    def test_an_absent_or_stale_audit_is_refused(self) -> None:
        for audit, for_png in ((None, None), ("pass", b"\x89PNG an older drawing")):
            with self.subTest(audit=audit, stale=bool(for_png)):
                code, payload = self.validate(self.drawn(audit, for_png=for_png))
                self.assertEqual((code, payload["error"]), (2, "AUDIT_NOT_PASSED"))
                self.assertEqual(payload["audit"]["verdict"], "absent" if audit is None else "stale")
                self.assertFalse(self.record().exists())

    def test_a_passing_audit_validates_and_is_shown(self) -> None:
        code, payload = self.validate(self.drawn("pass"))
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["audit"]["verdict"], "pass")
        self.assertNotIn("audit_override", json.loads(self.record().read_text(encoding="utf-8")))

    def test_the_operators_override_is_recorded_verbatim(self) -> None:
        words = "acepto el diagrama así"
        code, payload = self.validate(self.drawn("fail"), "--audit-override", words)
        self.assertEqual(code, 0, payload)
        self.assertEqual(json.loads(self.record().read_text(encoding="utf-8"))["audit_override"], words)
        code, payload = self.validate(self.drawn("fail"), "--audit-override", "   ")
        self.assertEqual((code, payload["error"]), (2, "STATEMENT_EMPTY"))

    def test_status_reports_the_audit(self) -> None:
        self.drawn("fail")
        code, payload = run_cli("status", "--target", str(self.ws.target), "--name", "Sample")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["kinds"]["poc"]["audit"], "fail")
        self.assertEqual(payload["kinds"]["experiments"]["audit"], "absent")


@unittest.skipUnless(_tex_available() and _raster_available(), "needs a TeX engine and a rasterizer")
class RenderAuditTests(_Base):

    def test_render_keeps_the_log_and_writes_a_passing_audit(self) -> None:
        for kind in ("poc", "experiments"):
            with self.subTest(kind=kind):
                spec_path = self.spec(kind)
                code, payload = run_cli("render", "--spec", str(spec_path))
                self.assertEqual(code, 0, payload)
                self.assertTrue(spec_path.with_suffix(".log").is_file())
                self.assertEqual(payload["audit"]["verdict"], "pass", payload["audit"])
                record = json.loads(spec_path.with_name(f"{kind}.audit.json").read_text(encoding="utf-8"))
                self.assertEqual(record["png_sha256"],
                                 hashlib.sha256(spec_path.with_suffix(".png").read_bytes()).hexdigest())
                for check in ("overfull", "size_switches", "text_overlap", "font_range", "margins"):
                    self.assertEqual(record["report"]["checks"][check]["verdict"], "pass", check)

    def test_a_label_too_long_for_its_box_is_refused_overfull(self) -> None:
        spec_path = self.spec()
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["nodes"][1]["label"] = "Electroencephalographicallymultichannelized"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        code, payload = run_cli("render", "--spec", str(spec_path))
        self.assertEqual((code, payload["error"]), (2, "TEX_OVERFULL"), payload)
        self.assertIn("Overfull \\hbox", payload["message"])
        self.assertEqual([item["gap_cm"] for item in payload["fit"]], [0.6, 0.45])
        self.assertFalse(spec_path.with_suffix(".png").exists())

    def test_the_audit_verb_finds_what_render_did_not_write(self) -> None:
        spec_path = self.spec("poc")
        self.assertEqual(run_cli("render", "--spec", str(spec_path))[0], 0)
        tex = spec_path.with_suffix(".tex")
        tex.write_text(tex.read_text(encoding="utf-8") + "\\small\n", encoding="utf-8")
        code, payload = run_cli("audit", "--spec", str(spec_path))
        self.assertEqual(code, 0, payload)
        self.assertEqual((payload["verdict"], payload["failures"]), ("fail", ["size_switches"]))
        sha = hashlib.sha256(spec_path.with_suffix(".png").read_bytes()).hexdigest()
        code, payload = run_cli("validate", "--target", str(self.ws.target), "--name", "Sample",
                                "--kind", "poc", "--png-sha256", sha, "--operator-statement", STATEMENT)
        self.assertEqual((code, payload["error"]), (2, "AUDIT_NOT_PASSED"))


if __name__ == "__main__":
    unittest.main()
