"""The shipped plotting helper for experiment repositories,
`skills/experimental-implementation/assets/kit/ps_figures.py` (specs S2,
S3, S4 of `odd/tasks/figure-and-table-quality.md`).

matplotlib is not installed in the papersmith environment: the helper's
pure surface (`rc_params`, `save_figure`'s refusals and the exact
`savefig` options) is tested against a duck-typed figure, and the
end-to-end export (a real plot measured by `print_scale` and judged by
`figure_dimensions`) skips with a stated reason when matplotlib is not
importable.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
KIT = FORGE_ROOT / "skills" / "experimental-implementation" / "assets" / "kit"
sys.path.insert(0, str(KIT))
import ps_figures  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "figure"))
import figure_dimensions  # noqa: E402

HAS_MATPLOTLIB = importlib.util.find_spec("matplotlib") is not None
NO_MATPLOTLIB = "matplotlib is not importable here; it lives in each experiment repository"

TEXT_ROLES = (
    "font.size", "axes.labelsize", "xtick.labelsize", "ytick.labelsize",
    "legend.fontsize", "legend.title_fontsize",
)


class _Text:
    def __init__(self, text: str) -> None:
        self._text = text

    def get_text(self) -> str:
        return self._text


class _Axes:
    def __init__(self, **titles) -> None:
        self._titles = titles

    def get_title(self, loc: str = "center") -> str:
        return self._titles.get(loc, "")


class _Figure:
    def __init__(self, axes=(), suptitle=None) -> None:
        self._axes = list(axes)
        self._suptitle = _Text(suptitle) if suptitle is not None else None
        self.saved: list = []

    def get_axes(self) -> list:
        return self._axes

    def savefig(self, path, **options) -> None:
        self.saved.append((Path(path), options))
        Path(path).write_bytes(b"stub")


class RcParamsTests(unittest.TestCase):
    """S3: the figure is its printed size and every text role prints at
    least 0.70 x the body."""

    def test_every_text_role_is_at_least_seventy_percent_of_the_body(self) -> None:
        for body in (9, 10, 11, 12):
            params = ps_figures.rc_params(body, 0.5)
            floor = 0.70 * body * 72 / 72.27
            for role in TEXT_ROLES:
                self.assertGreaterEqual(params[role], floor, (body, role))

    def test_every_text_role_prints_inside_the_range_with_crop_headroom(self) -> None:
        """S2 of `manuscript-polish-0-54`: every role within [0.70, 0.90] x
        body. `bbox_inches="tight"` crops the figure a little, so `place`
        enlarges it by up to ~10 % to fill the declared width: each role
        still prints below the cap at that enlargement."""
        self.assertEqual((ps_figures.MIN_RATIO, ps_figures.MAX_RATIO), (0.70, 0.90))
        for body in (9, 10, 11, 12):
            params = ps_figures.rc_params(body, 0.5)
            floor = 0.70 * body * 72 / 72.27
            cap = 0.90 * body * 72 / 72.27
            for role in TEXT_ROLES:
                with self.subTest(body=body, role=role):
                    self.assertGreaterEqual(params[role], floor)
                    self.assertLessEqual(params[role] * 1.10, cap)
        params = ps_figures.rc_params(10, 1.0)
        self.assertEqual((params["axes.labelsize"], params["xtick.labelsize"]), (7.97, 7.47))

    def test_the_figure_width_is_the_declared_printed_width(self) -> None:
        width, height = ps_figures.rc_params(10, 0.8)["figure.figsize"]
        self.assertAlmostEqual(width, 0.8 * 345 / 72.27, places=3)
        self.assertLess(height, width)
        self.assertAlmostEqual(
            ps_figures.rc_params(10, 1.0, text_width_pt=516.0)["figure.figsize"][0], 516 / 72.27, places=3,
        )

    def test_fonts_are_embedded_and_nothing_paints_a_background(self) -> None:
        params = ps_figures.rc_params(10)
        self.assertEqual(params["pdf.fonttype"], 42)
        self.assertTrue(params["savefig.transparent"])
        self.assertEqual(params["figure.facecolor"], "none")

    def test_an_out_of_range_fraction_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            ps_figures.rc_params(10, 1.2)


class SaveFigureTests(unittest.TestCase):
    """S2: tight, transparent, PDF. S4: no title in the figure."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name)

    def test_the_pdf_is_saved_tight_and_transparent_with_an_optional_png_preview(self) -> None:
        fig = _Figure([_Axes()])
        path = ps_figures.save_figure(fig, self.tmp / "figures" / "accuracy.pdf", png_preview=True)
        self.assertEqual(path, self.tmp / "figures" / "accuracy.pdf")
        (pdf_path, pdf_options), (png_path, png_options) = fig.saved
        self.assertEqual(pdf_path.suffix, ".pdf")
        self.assertEqual(png_path.suffix, ".png")
        self.assertEqual(
            {key: pdf_options[key] for key in ("bbox_inches", "pad_inches", "transparent", "format")},
            {"bbox_inches": "tight", "pad_inches": 0.02, "transparent": True, "format": "pdf"},
        )
        self.assertTrue(png_options["transparent"])

    def test_a_non_pdf_manuscript_copy_is_refused(self) -> None:
        fig = _Figure([_Axes()])
        with self.assertRaises(ps_figures.FigureExportError):
            ps_figures.save_figure(fig, self.tmp / "accuracy.png")
        self.assertEqual(fig.saved, [])

    def test_an_axes_title_is_refused(self) -> None:
        for loc in ("center", "left", "right"):
            fig = _Figure([_Axes(**{loc: "Accuracy per epoch"})])
            with self.assertRaises(ps_figures.FigureExportError) as ctx:
                ps_figures.save_figure(fig, self.tmp / "a.pdf")
            self.assertIn("caption", str(ctx.exception))
            self.assertEqual(fig.saved, [])

    def test_a_suptitle_is_refused(self) -> None:
        fig = _Figure([_Axes()], suptitle="Results")
        with self.assertRaises(ps_figures.FigureExportError):
            ps_figures.save_figure(fig, self.tmp / "a.pdf")


@unittest.skipUnless(HAS_MATPLOTLIB, NO_MATPLOTLIB)
class MatplotlibExportTests(unittest.TestCase):
    """A real plot styled and saved by the helper meets every vector
    verdict `place` checks."""

    def test_a_styled_plot_meets_s2_s3_s4(self) -> None:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:  # optional: matplotlib lives in experiment repos
            self.skipTest(NO_MATPLOTLIB)
        import print_scale

        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        ps_figures.apply_style(10, printed_width_fraction=0.8)
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2, 3], [0.2, 0.5, 0.7, 0.8], label="Proposed")
        ax.plot([0, 1, 2, 3], [0.2, 0.4, 0.5, 0.55], label="Baseline")
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Accuracy")
        ax.legend()
        pdf = ps_figures.save_figure(fig, Path(holder.name) / "accuracy.pdf")
        plt.close(fig)

        bounds = print_scale.content_bbox(pdf)
        self.assertFalse(bounds["full_page_background"])
        self.assertEqual(figure_dimensions.whitespace_verdict(bounds["margins"])["verdict"], "pass")
        self.assertFalse(figure_dimensions.no_text_layer(bounds["counts"]))
        printed = print_scale.declared_width_pt(345.0, 0.8)
        report = print_scale.printed_font_report(pdf, printed, 10)
        self.assertEqual(report["verdict"], "pass", report["offending"])
        self.assertAlmostEqual(report["scale"], 1.0, delta=0.15)


if __name__ == "__main__":
    unittest.main()
