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


class _NoDrawAxes:
    """An Axes stand-in that fails on any use: a helper must validate its
    inputs before it draws anything."""

    def __getattr__(self, name):
        raise AssertionError(f"the helper drew ({name}) before validating its inputs")


class ChartHelperValidationTests(unittest.TestCase):
    """S4 of `odd/tasks/figures-over-tables.md`: every chart helper refuses
    mismatched inputs with a ValueError before it touches the Axes (no
    matplotlib needed)."""

    def assert_refused(self, call, fragment: str) -> None:
        with self.assertRaises(ValueError) as ctx:
            call()
        self.assertIn(fragment, str(ctx.exception))

    def test_interval_plot_refuses_mismatched_lengths_and_inverted_intervals(self) -> None:
        ax = _NoDrawAxes()
        self.assert_refused(lambda: ps_figures.interval_plot(ax, ["a", "b"], [1.0], [0.0, 0.0], [2.0, 2.0]),
                            "estimates")
        self.assert_refused(lambda: ps_figures.interval_plot(ax, ["a"], [1.0], [0.0, 0.0], [2.0]), "low")
        self.assert_refused(lambda: ps_figures.interval_plot(ax, ["a"], [1.0], [0.0], []), "high")
        self.assert_refused(lambda: ps_figures.interval_plot(ax, [], [], [], []), "at least one")
        self.assert_refused(lambda: ps_figures.interval_plot(ax, ["a"], [1.0], [1.5], [2.0]), "low <= estimate <= high")

    def test_grouped_bars_refuses_mismatched_series_and_errors(self) -> None:
        ax = _NoDrawAxes()
        self.assert_refused(lambda: ps_figures.grouped_bars(ax, ["g1", "g2"], {"A": [1.0]}), "'A'")
        self.assert_refused(lambda: ps_figures.grouped_bars(ax, ["g1"], {}), "at least one")
        self.assert_refused(lambda: ps_figures.grouped_bars(ax, ["g1"], {"A": [1.0]}, errors={"B": [0.1]}), "'B'")
        self.assert_refused(lambda: ps_figures.grouped_bars(ax, ["g1", "g2"], {"A": [1.0, 2.0]},
                                                            errors={"A": [0.1]}), "errors")
        self.assert_refused(lambda: ps_figures.grouped_bars(ax, ["g1"], {"A": [1.0]},
                                                            errors={"A": [(0.1, 0.2, 0.3)]}), "errors")

    def test_distribution_plot_refuses_an_unknown_kind_and_empty_samples(self) -> None:
        ax = _NoDrawAxes()
        self.assert_refused(lambda: ps_figures.distribution_plot(ax, {"A": [1.0, 2.0]}, kind="histogram"), "kind")
        self.assert_refused(lambda: ps_figures.distribution_plot(ax, {"A": []}), "'A'")
        self.assert_refused(lambda: ps_figures.distribution_plot(ax, {}), "at least one")

    def test_line_plot_refuses_mismatched_series_and_bands(self) -> None:
        ax = _NoDrawAxes()
        self.assert_refused(lambda: ps_figures.line_plot(ax, [0, 1, 2], {"A": [1.0, 2.0]}), "'A'")
        self.assert_refused(lambda: ps_figures.line_plot(ax, [0, 1], {}), "at least one")
        self.assert_refused(lambda: ps_figures.line_plot(ax, [0, 1], {"A": [1.0, 2.0]},
                                                         bands={"B": ([0, 0], [2, 2])}), "'B'")
        self.assert_refused(lambda: ps_figures.line_plot(ax, [0, 1], {"A": [1.0, 2.0]},
                                                         bands={"A": ([0, 0], [2])}), "band")
        self.assert_refused(lambda: ps_figures.line_plot(ax, [0, 1], {"A": [1.0, 2.0]},
                                                         bands={"A": ([0, 0],)}), "band")


@unittest.skipUnless(HAS_MATPLOTLIB, NO_MATPLOTLIB)
class ChartHelperDrawingTests(unittest.TestCase):
    """S4: each helper draws its artists on the given Axes in the house
    style, returns that Axes, and the figure still exports through
    `save_figure`."""

    def setUp(self) -> None:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.colors as mcolors
            from matplotlib.collections import PolyCollection
            from matplotlib.container import BarContainer, ErrorbarContainer
            from matplotlib.patches import PathPatch
        except ImportError:  # optional: matplotlib lives in experiment repos
            self.skipTest(NO_MATPLOTLIB)
        self.plt = plt
        self.mpl = matplotlib
        self.mcolors = mcolors
        self.PolyCollection, self.PathPatch = PolyCollection, PathPatch
        self.BarContainer, self.ErrorbarContainer = BarContainer, ErrorbarContainer
        ps_figures.apply_style(10, printed_width_fraction=0.8)
        self.fig, self.ax = plt.subplots()
        self.addCleanup(plt.close, self.fig)
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name)

    def colours(self) -> list:
        return self.mpl.rcParams["axes.prop_cycle"].by_key()["color"]

    def assert_exports(self) -> None:
        pdf = ps_figures.save_figure(self.fig, self.tmp / "chart.pdf", png_preview=True)
        self.assertGreater(pdf.stat().st_size, 0)
        self.assertTrue(pdf.with_suffix(".png").is_file())

    def test_interval_plot_draws_one_whisker_per_row_and_a_reference_line(self) -> None:
        labels = ["Model A", "Model B", "Model C"]
        result = ps_figures.interval_plot(self.ax, labels, [0.2, -0.1, 0.5], [0.0, -0.3, 0.3], [0.4, 0.1, 0.7],
                                          reference=0.0)
        self.assertIs(result, self.ax)
        containers = [c for c in self.ax.containers if isinstance(c, self.ErrorbarContainer)]
        self.assertEqual(len(containers), 1)
        self.assertEqual(len(containers[0].lines[0].get_xdata()), 3)
        self.assertEqual(len(containers[0].lines[2][0].get_segments()), 3)
        self.assertEqual([t.get_text() for t in self.ax.get_yticklabels()], labels)
        references = [line for line in self.ax.lines if list(line.get_xdata()) == [0.0, 0.0]]
        self.assertEqual(len(references), 1)
        self.assert_exports()

    def test_interval_plot_without_a_reference_draws_no_extra_line(self) -> None:
        ps_figures.interval_plot(self.ax, ["a", "b"], [1.0, 2.0], [0.5, 1.5], [1.5, 2.5])
        self.assertEqual(len(self.ax.lines), 1)

    def test_grouped_bars_draws_one_bar_per_group_and_series_with_errors_and_a_legend(self) -> None:
        groups = ["Task 1", "Task 2", "Task 3"]
        series = {"Proposed": [0.8, 0.7, 0.9], "Baseline": [0.6, 0.5, 0.7]}
        errors = {"Proposed": [0.05, 0.04, 0.03], "Baseline": [(0.02, 0.06), (0.01, 0.02), (0.03, 0.03)]}
        result = ps_figures.grouped_bars(self.ax, groups, series, errors=errors)
        self.assertIs(result, self.ax)
        bars = [c for c in self.ax.containers if isinstance(c, self.BarContainer)]
        self.assertEqual([len(c.patches) for c in bars], [3, 3])
        self.assertEqual(len(self.ax.patches), 6)
        self.assertEqual(len([c for c in self.ax.containers if isinstance(c, self.ErrorbarContainer)]), 2)
        self.assertEqual([t.get_text() for t in self.ax.get_legend().get_texts()], list(series))
        self.assertEqual([t.get_text() for t in self.ax.get_xticklabels()], groups)
        colours = self.colours()
        self.assertEqual(self.mcolors.to_hex(bars[0].patches[0].get_facecolor()), self.mcolors.to_hex(colours[0]))
        self.assertEqual(self.mcolors.to_hex(bars[1].patches[0].get_facecolor()), self.mcolors.to_hex(colours[1]))
        self.assert_exports()

    def test_grouped_bars_without_errors_draws_no_error_bars(self) -> None:
        ps_figures.grouped_bars(self.ax, ["g1", "g2"], {"A": [1.0, 2.0]})
        self.assertEqual(len(self.ax.patches), 2)
        self.assertFalse([c for c in self.ax.containers if isinstance(c, self.ErrorbarContainer)])

    def test_distribution_plot_draws_one_violin_body_per_sample(self) -> None:
        samples = {"A": [1.0, 1.2, 0.9, 1.4, 1.1], "B": [2.0, 2.5, 1.8, 2.2, 2.1], "C": [0.5, 0.7, 0.6, 0.4, 0.8]}
        result = ps_figures.distribution_plot(self.ax, samples)
        self.assertIs(result, self.ax)
        bodies = [c for c in self.ax.collections if isinstance(c, self.PolyCollection)]
        self.assertEqual(len(bodies), 3)
        self.assertEqual([t.get_text() for t in self.ax.get_xticklabels()], list(samples))
        self.assert_exports()

    def test_distribution_plot_draws_one_box_patch_per_sample(self) -> None:
        samples = {"A": [1.0, 1.2, 0.9, 1.4, 1.1], "B": [2.0, 2.5, 1.8, 2.2, 2.1]}
        result = ps_figures.distribution_plot(self.ax, samples, kind="box")
        self.assertIs(result, self.ax)
        self.assertEqual(len([p for p in self.ax.patches if isinstance(p, self.PathPatch)]), 2)
        self.assertEqual([t.get_text() for t in self.ax.get_xticklabels()], list(samples))
        self.assert_exports()

    def test_line_plot_draws_one_line_per_series_and_one_band_per_entry(self) -> None:

        x = [0, 1, 2, 3]
        series = {"Proposed": [0.2, 0.5, 0.7, 0.8], "Baseline": [0.2, 0.4, 0.5, 0.55]}
        bands = {"Proposed": ([0.1, 0.4, 0.6, 0.75], [0.3, 0.6, 0.8, 0.85])}
        result = ps_figures.line_plot(self.ax, x, series, bands=bands)
        self.assertIs(result, self.ax)
        self.assertEqual(len(self.ax.lines), 2)
        fills = [c for c in self.ax.collections if isinstance(c, self.PolyCollection)]
        self.assertEqual(len(fills), 1)
        self.assertEqual(self.mcolors.to_hex(fills[0].get_facecolor()[0], keep_alpha=False),
                         self.mcolors.to_hex(self.ax.lines[0].get_color()))
        self.assertEqual([t.get_text() for t in self.ax.get_legend().get_texts()], list(series))
        self.assert_exports()


if __name__ == "__main__":
    unittest.main()
