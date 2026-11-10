"""The SVG figure audit: stdlib-only checks with diagram_audit's verdict contract."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "_core" / "figure"))
import svg_audit  # noqa: E402  (sibling of diagram_audit, resolved above)


def _svg(*body: str, viewbox: str = "0 0 400 200",
         background: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">'
            f'{background}{"".join(body)}</svg>')


def _text(value: str, x: float, y: float, size: float = 14,
          fill: str = "black", extra: str = "") -> str:
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"{extra}>'
            f'{value}</text>')


class VerdictContractTests(unittest.TestCase):
    """The overall verdict follows diagram_audit's fail > pass > unmeasured order."""

    def test_a_clean_figure_passes_every_check(self) -> None:
        report = svg_audit.audit_svg_text(_svg(
            _text("Attention over features", 20, 30, size=18, fill="black"),
            _text("the encoder maps tokens", 20, 80, size=12, fill="#222222"),
            _text("note: see Table 2", 20, 160, size=8, fill="#333333"),
            background='<rect x="0" y="0" width="400" height="200" fill="white"/>',
        ))
        self.assertEqual(report["verdict"], "pass", json.dumps(report, indent=2))
        self.assertEqual(report["failures"], [])
        for name in ("font_range", "text_overlap", "contrast", "viewbox_fit"):
            self.assertEqual(report["checks"][name]["verdict"], "pass", name)

    def test_a_malformed_svg_is_unmeasured_never_a_crash(self) -> None:
        report = svg_audit.audit_svg_text("<svg><text>unclosed")
        self.assertEqual(report["verdict"], "unmeasured")
        self.assertIn("XML_PARSE_ERROR", report["reason"])

    def test_failures_beat_unmeasured_in_the_overall_verdict(self) -> None:
        # contrast fails; text_overlap is unmeasured (no positioned text)
        report = svg_audit.audit_svg_text(_svg(
            _text("Ghost text", 20, 30, size=14, fill="#eeeeee"),
        ))
        self.assertEqual(report["verdict"], "fail")
        self.assertIn("contrast", report["failures"])

    def test_failure_messages_name_each_failed_check(self) -> None:
        report = svg_audit.audit_svg_text(_svg(
            _text("Title", 20, 30, size=16, fill="black"),
            _text("Ghost line", 20, 120, size=12, fill="white"),
            background='<rect x="0" y="0" width="400" height="200" fill="white"/>',
        ))
        lines = svg_audit.failure_messages(report)
        self.assertTrue(any(line.startswith("contrast:") for line in lines), lines)


class CollisionTests(unittest.TestCase):

    def test_two_overlapping_spans_fail(self) -> None:
        report = svg_audit.audit_svg_text(_svg(
            _text("encoder attention map", 20, 60, size=14),
            _text("decoder attention head", 30, 62, size=14),
        ))
        self.assertEqual(report["checks"]["text_overlap"]["verdict"], "fail")
        self.assertEqual(len(report["checks"]["text_overlap"]["collisions"]), 1)

    def test_far_apart_spans_pass(self) -> None:
        report = svg_audit.audit_svg_text(_svg(
            _text("left column", 20, 60, size=14),
            _text("right column", 250, 60, size=14),
        ))
        self.assertEqual(report["checks"]["text_overlap"]["verdict"], "pass")


class HierarchyTests(unittest.TestCase):

    def test_too_many_size_levels_fail(self) -> None:
        report = svg_audit.audit_svg_text(_svg(
            _text("a", 10, 20, size=20), _text("b", 10, 40, size=17),
            _text("c", 10, 60, size=14), _text("d", 10, 80, size=12),
            _text("e", 10, 100, size=10),
        ))
        self.assertEqual(report["checks"]["font_range"]["verdict"], "fail")
        self.assertIn("HIERARCHY_TOO_DEEP", report["checks"]["font_range"]["reason"])

    def test_a_caption_below_half_the_title_fails(self) -> None:
        report = svg_audit.audit_svg_text(_svg(
            _text("Title", 10, 30, size=20),
            _text("unreadable footnote", 10, 180, size=6),
        ))
        self.assertEqual(report["checks"]["font_range"]["verdict"], "fail")
        self.assertIn("HIERARCHY_JUMP", report["checks"]["font_range"]["reason"])

    def test_text_without_sizes_is_unmeasured(self) -> None:
        report = svg_audit.audit_svg_text(_svg('<text x="10" y="20">plain</text>'))
        self.assertEqual(report["checks"]["font_range"]["verdict"], "unmeasured")


class ContrastTests(unittest.TestCase):

    def test_light_text_on_white_fails(self) -> None:
        report = svg_audit.audit_svg_text(_svg(
            _text("washed out", 20, 60, size=14, fill="#f0f0f0"),
        ))
        self.assertEqual(report["checks"]["contrast"]["verdict"], "fail")
        ratio = report["checks"]["contrast"]["failures"][0]["ratio"]
        self.assertLess(ratio, svg_audit.MIN_CONTRAST)

    def test_a_gradient_fill_is_unmeasured_never_a_pass(self) -> None:
        report = svg_audit.audit_svg_text(_svg(
            _text("gradient text", 20, 60, size=14, fill="url(#grad)"),
        ))
        self.assertEqual(report["checks"]["contrast"]["verdict"], "unmeasured")


class ViewboxFitTests(unittest.TestCase):

    def test_content_past_the_viewbox_fails(self) -> None:
        report = svg_audit.audit_svg_text(_svg(
            _text("runs off the edge to the right", 300, 60, size=14),
            viewbox="0 0 200 200",
        ))
        self.assertEqual(report["checks"]["viewbox_fit"]["verdict"], "fail")

    def test_no_viewbox_is_unmeasured(self) -> None:
        report = svg_audit.audit_svg_text(
            '<svg xmlns="http://www.w3.org/2000/svg">' + _text("fine", 10, 20) + "</svg>")
        self.assertEqual(report["checks"]["viewbox_fit"]["verdict"], "unmeasured")


class FileAndTransformTests(unittest.TestCase):

    def test_audit_svg_reads_a_file_without_touching_it(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fig.svg"
            path.write_text(_svg(_text("hello", 10, 20, size=14)), encoding="utf-8")
            before = path.read_bytes()
            report = svg_audit.audit_svg(path)
            self.assertIn(report["verdict"], ("pass", "unmeasured"))
            self.assertEqual(path.read_bytes(), before)

    def test_spans_inside_transforms_are_excluded_not_guessed(self) -> None:
        report = svg_audit.audit_svg_text(_svg(
            _text("rotated label", 10, 20, size=14, extra=' transform="rotate(45 10 20)"'),
        ))
        check = report["checks"]["text_overlap"]
        self.assertEqual(check["verdict"], "unmeasured")
        self.assertEqual(check["reason"], "TEXT_INSIDE_TRANSFORMS")
        self.assertEqual(check["excluded"], 1)


class CliWiringTests(unittest.TestCase):
    """diagram_cli audit-svg: one JSON object, Refusal on a missing file."""

    @staticmethod
    def _cli():
        import importlib.util
        path = Path(__file__).resolve().parent.parent / "skills" / "experiment-diagrams" / "scripts" / "diagram_cli.py"
        spec = importlib.util.spec_from_file_location("diagram_cli_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_audit_svg_prints_one_json_report(self) -> None:
        import tempfile
        cli = self._cli()
        with tempfile.TemporaryDirectory() as tmp:
            svg = Path(tmp) / "fig.svg"
            svg.write_text(_svg(_text("title", 10, 20, size=16, fill="black")),
                           encoding="utf-8")
            import io
            from contextlib import redirect_stdout
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["audit-svg", "--svg", str(svg)])
            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertTrue(payload["ok"])
            self.assertIn(payload["verdict"], ("pass", "unmeasured"))
            self.assertIn("checks", payload["report"])

    def test_a_missing_svg_is_refused_not_a_crash(self) -> None:
        import io
        import tempfile
        from contextlib import redirect_stdout
        cli = self._cli()
        with tempfile.TemporaryDirectory() as tmp:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["audit-svg", "--svg", str(Path(tmp) / "nope.svg")])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(buffer.getvalue())["error"], "SVG_ABSENT")


if __name__ == "__main__":
    unittest.main()
