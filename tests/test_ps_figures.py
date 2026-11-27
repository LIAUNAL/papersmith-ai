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


class IllustrativeHelperValidationTests(unittest.TestCase):
    """S4 of `odd/tasks/illustrative-results.md`: the illustrative-result
    helpers refuse malformed arrays with a ValueError before they touch the
    Axes (no matplotlib needed)."""

    assert_refused = ChartHelperValidationTests.assert_refused

    def test_forecast_plot_refuses_mismatched_windows_predictions_and_bands(self) -> None:
        ax = _NoDrawAxes()
        call = ps_figures.forecast_plot
        window = ([0, 1], [1.0, 1.0], [2, 3], [1.0, 1.0])
        self.assert_refused(lambda: call(ax, [0, 1], [1.0], [2, 3], [1.0, 1.0], {"P": [1.0, 1.0]}), "y_input")
        self.assert_refused(lambda: call(ax, [], [], [2, 3], [1.0, 1.0], {"P": [1.0, 1.0]}), "at least one")
        self.assert_refused(lambda: call(ax, [0, 1], [1.0, 1.0], [2, 3], [1.0], {"P": [1.0, 1.0]}), "target")
        self.assert_refused(lambda: call(ax, *window, {}), "at least one")
        self.assert_refused(lambda: call(ax, *window, {"P": [1.0]}), "'P'")
        self.assert_refused(lambda: call(ax, *window, {"P": [1.0, 1.0]}, bands={"Q": ([0, 0], [2, 2])}), "'Q'")
        self.assert_refused(lambda: call(ax, *window, {"P": [1.0, 1.0]}, bands={"P": ([0, 0], [2])}), "band")
        self.assert_refused(lambda: call(ax, *window, {"P": [1.0, 1.0]}, bands={"P": ([0, 0],)}), "band")
        self.assert_refused(lambda: call(ax, *window, {"P": [1.0, 1.0]}, bands={"P": ([0, 3], [2, 2])}),
                            "low <= high")

    def test_loss_terms_plot_refuses_mismatched_terms_and_non_positive_values_on_a_log_axis(self) -> None:
        ax = _NoDrawAxes()
        call = ps_figures.loss_terms_plot
        self.assert_refused(lambda: call(ax, [], {"data": []}), "at least one")
        self.assert_refused(lambda: call(ax, [0, 1], {}), "at least one")
        self.assert_refused(lambda: call(ax, [0, 1, 2], {"data": [1.0, 0.5]}), "'data'")
        self.assert_refused(lambda: call(ax, [0, 1], {"data": [1.0, 0.0]}), "log")

    def test_heatmap_plot_refuses_ragged_or_empty_matrices_and_mismatched_labels(self) -> None:
        ax = _NoDrawAxes()
        call = ps_figures.heatmap_plot
        self.assert_refused(lambda: call(ax, []), "at least one")
        self.assert_refused(lambda: call(ax, [[]]), "at least one")
        self.assert_refused(lambda: call(ax, [1.0, 2.0]), "2-D")
        self.assert_refused(lambda: call(ax, [[1.0, 2.0], [3.0]]), "row 1")
        self.assert_refused(lambda: call(ax, [[1.0, 2.0]], x_labels=["a"]), "x_labels")
        self.assert_refused(lambda: call(ax, [[1.0, 2.0]], y_labels=["a", "b"]), "y_labels")

    def test_embedding_plot_refuses_non_planar_coordinates_and_mismatched_labels(self) -> None:
        ax = _NoDrawAxes()
        call = ps_figures.embedding_plot
        self.assert_refused(lambda: call(ax, [], []), "at least one")
        self.assert_refused(lambda: call(ax, [(0.0, 1.0), (1.0, 0.0)], ["a"]), "labels")
        self.assert_refused(lambda: call(ax, [(0.0, 1.0, 2.0)], ["a"]), "2-D")
        self.assert_refused(lambda: call(ax, [0.0, 1.0], ["a", "b"]), "2-D")

    def test_confusion_matrix_plot_refuses_non_square_negative_or_unnormalizable_counts(self) -> None:
        ax = _NoDrawAxes()
        call = ps_figures.confusion_matrix_plot
        self.assert_refused(lambda: call(ax, [], []), "at least one")
        self.assert_refused(lambda: call(ax, [[1, 2]], ["a", "b"]), "rows")
        self.assert_refused(lambda: call(ax, [[1, 2], [3]], ["a", "b"]), "row 1")
        self.assert_refused(lambda: call(ax, [[1, -2], [3, 4]], ["a", "b"]), "negative")
        self.assert_refused(lambda: call(ax, [[1, 2], [0, 0]], ["a", "b"], normalize=True), "'b'")

    def test_roc_plot_refuses_malformed_curves(self) -> None:
        ax = _NoDrawAxes()
        call = ps_figures.roc_plot
        self.assert_refused(lambda: call(ax, {}), "at least one")
        self.assert_refused(lambda: call(ax, {"A": ([0.0, 1.0],)}), "'A'")
        self.assert_refused(lambda: call(ax, {"A": ([0.0, 1.0], [0.0])}), "tpr")
        self.assert_refused(lambda: call(ax, {"A": ([0.0], [0.0])}), "two points")
        self.assert_refused(lambda: call(ax, {"A": ([0.0, 1.5], [0.0, 1.0])}), "[0, 1]")
        self.assert_refused(lambda: call(ax, {"A": ([0.0, 1.0], [0.0, 1.0], 1.2)}), "auc")


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
            from matplotlib.collections import PathCollection
        except ImportError:  # optional: matplotlib lives in experiment repos
            self.skipTest(NO_MATPLOTLIB)
        self.PathCollection = PathCollection
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

    # S4 of `odd/tasks/illustrative-results.md`: the illustrative-result helpers.

    def test_forecast_plot_draws_the_window_the_target_each_prediction_and_its_band(self) -> None:
        predictions = {"Proposed": [1.1, 1.3, 1.2], "LSTM": [0.9, 1.0, 1.4]}
        bands = {"Proposed": ([1.0, 1.1, 1.0], [1.2, 1.5, 1.4])}
        result = ps_figures.forecast_plot(self.ax, [0, 1, 2], [0.5, 0.8, 1.0], [3, 4, 5], [1.2, 1.25, 1.3],
                                          predictions, bands=bands)
        self.assertIs(result, self.ax)
        labelled = {line.get_label(): line for line in self.ax.lines if not line.get_label().startswith("_")}
        self.assertEqual(list(labelled), ["Input window", "Target", "Proposed", "LSTM"])
        self.assertEqual(list(labelled["Input window"].get_xdata()), [0, 1, 2])
        self.assertEqual(list(labelled["Target"].get_xdata()), [3, 4, 5])
        colours = self.colours()
        self.assertEqual(self.mcolors.to_hex(labelled["Proposed"].get_color()), self.mcolors.to_hex(colours[0]))
        self.assertEqual(self.mcolors.to_hex(labelled["LSTM"].get_color()), self.mcolors.to_hex(colours[1]))
        fills = [c for c in self.ax.collections if isinstance(c, self.PolyCollection)]
        self.assertEqual(len(fills), 1)
        self.assertEqual(self.mcolors.to_hex(fills[0].get_facecolor()[0], keep_alpha=False),
                         self.mcolors.to_hex(colours[0]))
        self.assertEqual([t.get_text() for t in self.ax.get_legend().get_texts()],
                         ["Input window", "Target", "Proposed", "LSTM"])
        self.assert_exports()

    def test_loss_terms_plot_draws_one_curve_per_term_on_a_log_axis_and_the_total_in_the_reference_colour(self) -> None:
        terms = {"data": [1.0, 0.5, 0.2], "physics": [2.0, 0.4, 0.1], "total": [3.0, 0.9, 0.3]}
        result = ps_figures.loss_terms_plot(self.ax, [0, 10, 20], terms)
        self.assertIs(result, self.ax)
        self.assertEqual([line.get_label() for line in self.ax.lines], list(terms))
        self.assertEqual(self.ax.get_yscale(), "log")
        total = self.ax.lines[2]
        self.assertEqual(self.mcolors.to_hex(total.get_color()),
                         self.mcolors.to_hex(self.mpl.rcParams["axes.edgecolor"]))
        self.assertGreater(total.get_linewidth(), self.ax.lines[0].get_linewidth())
        self.assert_exports()

    def test_loss_terms_plot_on_a_linear_axis_accepts_non_positive_values(self) -> None:
        ps_figures.loss_terms_plot(self.ax, [0, 1], {"penalty": [0.0, -0.1]}, log=False)
        self.assertEqual(self.ax.get_yscale(), "linear")
        self.assertEqual(len(self.ax.lines), 1)

    def test_heatmap_plot_draws_one_image_with_its_labels_and_a_colourbar(self) -> None:
        matrix = [[0.1, 0.4, 0.2], [0.9, 0.3, 0.5]]
        result = ps_figures.heatmap_plot(self.ax, matrix, x_labels=["t0", "t1", "t2"], y_labels=["h1", "h2"])
        self.assertIs(result, self.ax)
        self.assertEqual(len(self.ax.images), 1)
        self.assertEqual(self.ax.images[0].get_array().shape, (2, 3))
        self.assertEqual([t.get_text() for t in self.ax.get_xticklabels()], ["t0", "t1", "t2"])
        self.assertEqual([t.get_text() for t in self.ax.get_yticklabels()], ["h1", "h2"])
        self.assertEqual(len(self.fig.axes), 2)
        self.assert_exports()

    def test_heatmap_plot_without_a_colourbar_adds_no_axes(self) -> None:
        ps_figures.heatmap_plot(self.ax, [[1.0, 2.0], [3.0, 4.0]], colorbar=False)
        self.assertEqual(len(self.fig.axes), 1)

    def test_embedding_plot_draws_one_scatter_per_label_in_first_seen_order(self) -> None:
        coords = [(0.0, 0.1), (1.0, 1.1), (0.2, 0.0), (1.2, 0.9), (2.0, 2.0)]
        labels = ["walk", "run", "walk", "run", "sit"]
        result = ps_figures.embedding_plot(self.ax, coords, labels)
        self.assertIs(result, self.ax)
        scatters = [c for c in self.ax.collections if isinstance(c, self.PathCollection)]
        self.assertEqual([len(s.get_offsets()) for s in scatters], [2, 2, 1])
        colours = self.colours()
        self.assertEqual(self.mcolors.to_hex(scatters[1].get_facecolor()[0], keep_alpha=False),
                         self.mcolors.to_hex(colours[1]))
        self.assertEqual([t.get_text() for t in self.ax.get_legend().get_texts()], ["walk", "run", "sit"])
        self.assert_exports()

    def test_confusion_matrix_plot_annotates_counts_or_row_rates(self) -> None:
        result = ps_figures.confusion_matrix_plot(self.ax, [[8, 2], [1, 9]], ["neg", "pos"])
        self.assertIs(result, self.ax)
        self.assertEqual(len(self.ax.images), 1)
        self.assertEqual([t.get_text() for t in self.ax.texts], ["8", "2", "1", "9"])
        self.assertEqual([t.get_text() for t in self.ax.get_xticklabels()], ["neg", "pos"])
        self.assertEqual([t.get_text() for t in self.ax.get_yticklabels()], ["neg", "pos"])
        self.assertEqual((self.ax.get_xlabel(), self.ax.get_ylabel()), ("Predicted", "True"))
        self.assert_exports()

    def test_confusion_matrix_plot_normalizes_each_true_row(self) -> None:
        ps_figures.confusion_matrix_plot(self.ax, [[8, 2], [1, 9]], ["neg", "pos"], normalize=True)
        self.assertEqual([t.get_text() for t in self.ax.texts], ["0.80", "0.20", "0.10", "0.90"])

    def test_roc_plot_draws_each_curve_with_its_auc_and_the_chance_diagonal(self) -> None:
        curves = {"Proposed": ([0.0, 0.1, 1.0], [0.0, 0.8, 1.0], 0.91), "SVM": ([0.0, 0.3, 1.0], [0.0, 0.6, 1.0])}
        result = ps_figures.roc_plot(self.ax, curves)
        self.assertIs(result, self.ax)
        self.assertEqual([t.get_text() for t in self.ax.get_legend().get_texts()], ["Proposed (AUC = 0.91)", "SVM"])
        diagonal = [line for line in self.ax.lines if list(line.get_xdata()) == [0, 1]
                    and list(line.get_ydata()) == [0, 1]]
        self.assertEqual(len(diagonal), 1)
        self.assertEqual(len(self.ax.lines), 3)
        self.assertEqual((self.ax.get_xlim(), self.ax.get_ylim()), ((0.0, 1.0), (0.0, 1.0)))
        self.assert_exports()


if __name__ == "__main__":
    unittest.main()
