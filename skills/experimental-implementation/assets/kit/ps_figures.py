"""ps_figures: matplotlib style and export for figures that enter the
manuscript (papersmith, specs S2-S4 of
`odd/tasks/figure-and-table-quality.md`).

Copy this file into the experiment repository (beside the plotting code,
for example `src/<Package>/ps_figures.py`); matplotlib lives there, never
in the papersmith environment. Two calls:

    from ps_figures import apply_style, save_figure

    width, height = apply_style(body_pt=10, printed_width_fraction=0.8)
    fig, ax = plt.subplots()            # already width x height inches
    ax.plot(...); ax.set_xlabel(...); ax.set_ylabel(...)   # no set_title
    save_figure(fig, "Results/figures/accuracy.pdf", png_preview=True)

`apply_style` sets the figure to its printed size (the fraction of
`\\textwidth` the manuscript's `\\includegraphics[width=...]` will use), so
the inclusion scale is ~1 and every text role (axis labels, ticks, legend,
annotations) prints between 0.70 and 0.90 x the body size (spec S2 of
`odd/tasks/manuscript-polish-0-54.md`); TrueType fonts are
embedded so the PDF keeps a text layer (`place` measures it).
`save_figure` writes `savefig(pdf, bbox_inches="tight", pad_inches=0.02,
transparent=True)`: no background, no wasted margin. It refuses a
non-PDF manuscript copy and a figure carrying a title: the caption carries
the title.

Pass the same width to `paper_cli.py place` as `"printedWidthFraction"`
in the figure's provenance record.

Chart helpers for the usual result figures (spec S4 of
`odd/tasks/figures-over-tables.md`; Methods and Results prefer data
figures over tables). Each draws on the given Axes in the house style
(colours from the active `axes.prop_cycle`, fonts from `apply_style`),
returns that Axes, and raises ValueError on mismatched inputs before
drawing anything:

    interval_plot(ax, labels, estimates, low, high, *, reference=None)
    grouped_bars(ax, groups, series, *, errors=None)
    distribution_plot(ax, samples, *, kind="violin")   # or kind="box"
    line_plot(ax, x, series, *, bands=None)

Illustrative-result helpers (spec S4 of `odd/tasks/illustrative-results.md`;
the Results show what the novelty does at its basic stages before any
aggregate metric), drawn only from arrays the run recorded:

    forecast_plot(ax, t_input, y_input, t_output, target, predictions, *, bands=None)
    loss_terms_plot(ax, steps, terms, *, log=True)      # a "total" term is the total
    heatmap_plot(ax, matrix, *, x_labels=None, y_labels=None, colorbar=True)
    embedding_plot(ax, coords, labels)                   # coords already 2-D
    confusion_matrix_plot(ax, matrix, labels, *, normalize=False)
    roc_plot(ax, curves)                                 # name -> (fpr, tpr[, auc])
"""
from __future__ import annotations

from pathlib import Path

#: `\\textwidth` in TeX points for the common article setups (a4, one
#: column), keyed by body size. Pass `text_width_pt` for any other class.
TEXT_WIDTH_PT = {10: 345.0, 11: 360.0, 12: 390.0}

#: The printed text range, as a fraction of the body size; the same values
#: as papersmith's `_core/figure/print_scale.py` (this file is copied into
#: experiment repositories, so it cannot import it).
MIN_RATIO = 0.70
MAX_RATIO = 0.90
TEX_PT_TO_PDF_PT = 72.0 / 72.27

#: Text role sizes as a fraction of the body size, inside
#: [MIN_RATIO, MAX_RATIO]. `bbox_inches="tight"` crops the saved figure a
#: little, so `place` enlarges it (up to ~10 %) to fill the declared width:
#: axis labels at 0.80 still print below 0.90 x body after that, ticks and
#: legend at 0.75 stay above the 0.70 floor.
LABEL_RATIO = 0.80
SMALL_RATIO = 0.75

PAD_INCHES = 0.02
GOLDEN = 0.618


class FigureExportError(ValueError):
    """The figure cannot be exported for the manuscript as it stands."""


def rc_params(body_pt: float, printed_width_fraction: float = 1.0,
              text_width_pt: float | None = None, aspect: float = GOLDEN) -> dict:
    """The rcParams `apply_style` sets: pure data, no matplotlib needed.
    Sizes are in PDF points (matplotlib's unit) and the figure size in
    inches equals the printed size."""
    if not 0 < printed_width_fraction <= 1:
        raise ValueError("printed_width_fraction must be in (0, 1]")
    if text_width_pt is None:
        text_width_pt = TEXT_WIDTH_PT.get(int(round(body_pt)), TEXT_WIDTH_PT[10])
    width_in = text_width_pt * printed_width_fraction / 72.27
    label = round(body_pt * LABEL_RATIO * TEX_PT_TO_PDF_PT, 2)
    small = round(body_pt * SMALL_RATIO * TEX_PT_TO_PDF_PT, 2)
    return {
        "figure.figsize": (round(width_in, 4), round(width_in * aspect, 4)),
        "font.size": label,
        "axes.labelsize": label,
        "axes.titlesize": label,
        "xtick.labelsize": small,
        "ytick.labelsize": small,
        "legend.fontsize": small,
        "legend.title_fontsize": small,
        "figure.titlesize": label,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "savefig.transparent": True,
        "savefig.bbox": "tight",
        "savefig.pad_inches": PAD_INCHES,
        "figure.facecolor": "none",
        "axes.facecolor": "none",
        "savefig.facecolor": "none",
    }


def apply_style(body_pt: float, printed_width_fraction: float = 1.0,
                text_width_pt: float | None = None, aspect: float = GOLDEN) -> tuple:
    """Set matplotlib's rcParams for a figure printed at
    `printed_width_fraction x text_width_pt`; return its (width, height)
    in inches. Annotations (`ax.annotate`, `ax.text`) inherit `font.size`."""
    import matplotlib

    params = rc_params(body_pt, printed_width_fraction, text_width_pt, aspect)
    matplotlib.rcParams.update(params)
    return params["figure.figsize"]


def figure_titles(fig) -> list:
    """Every title the figure carries: each axes' center/left/right title
    and the figure's suptitle."""
    titles = []
    for ax in fig.get_axes():
        for loc in ("center", "left", "right"):
            text = ax.get_title(loc=loc)
            if text:
                titles.append(text)
    suptitle = getattr(fig, "_suptitle", None)
    if suptitle is not None and suptitle.get_text():
        titles.append(suptitle.get_text())
    return titles


def save_figure(fig, path_pdf, *, png_preview: bool = False, preview_dpi: int = 200) -> Path:
    """Write the manuscript copy as a tight, transparent vector PDF.

    Refuses (FigureExportError) a path that is not `.pdf` and a figure with
    a title. With `png_preview`, also writes `<name>.png` beside it for the
    dashboard; the PDF is the copy `place` takes."""
    path = Path(path_pdf)
    if path.suffix.lower() != ".pdf":
        raise FigureExportError(
            f"{path}: the manuscript copy must be a vector PDF (.pdf); "
            "pass png_preview=True for a raster preview")
    titles = figure_titles(fig)
    if titles:
        raise FigureExportError(
            f"{path}: the figure carries a title {titles!r}; remove set_title/suptitle "
            "and put it in the caption")
    path.parent.mkdir(parents=True, exist_ok=True)
    options = {"bbox_inches": "tight", "pad_inches": PAD_INCHES, "transparent": True}
    fig.savefig(path, format="pdf", **options)
    if png_preview:
        fig.savefig(path.with_suffix(".png"), format="png", dpi=preview_dpi, **options)
    return path


# ---------------------------------------------------------------- chart helpers

DISTRIBUTION_KINDS = ("violin", "box")
BAR_GROUP_WIDTH = 0.8
BAND_ALPHA = 0.2
REFERENCE_STYLE = {"linestyle": "--", "linewidth": 0.8}


def _require_rows(name: str, values) -> list:
    rows = list(values)
    if not rows:
        raise ValueError(f"{name} needs at least one entry")
    return rows


def _require_length(name: str, values, expected: int, against: str) -> list:
    rows = list(values)
    if len(rows) != expected:
        raise ValueError(f"{name} has {len(rows)} values; {against} has {expected}")
    return rows


def _require_known(name: str, mapping, known) -> None:
    unknown = [key for key in mapping if key not in known]
    if unknown:
        raise ValueError(f"{name} names {unknown[0]!r}, which is not a series")


def _palette() -> list:
    """The house colours: the active `axes.prop_cycle` (what `ax.plot`
    and `ax.bar` cycle through)."""
    import matplotlib

    return matplotlib.rcParams["axes.prop_cycle"].by_key()["color"]


def _reference_colour() -> str:
    import matplotlib

    return matplotlib.rcParams["axes.edgecolor"]


def _line_width() -> float:
    import matplotlib

    return float(matplotlib.rcParams["lines.linewidth"])


def _bar_errors(name: str, values, groups: int):
    """`values` as matplotlib's `yerr`: one symmetric error per group, or
    one (below, above) pair per group (both distances from the bar top)."""
    rows = _require_length(f"errors[{name!r}]", values, groups, "groups")
    pairs = [hasattr(row, "__len__") for row in rows]
    if not any(pairs):
        return rows
    if not all(pairs) or any(len(row) != 2 for row in rows):
        raise ValueError(f"errors[{name!r}] must hold one number or one (low, high) pair per group")
    return [[row[0] for row in rows], [row[1] for row in rows]]


def interval_plot(ax, labels, estimates, low, high, *, reference=None):
    """Dot-and-whisker (forest) plot: one row per label, top to bottom, the
    estimate as a dot and [low, high] as a horizontal whisker. `reference`
    (for example 0 or a margin) adds a dashed vertical line."""
    labels = _require_rows("labels", labels)
    count = len(labels)
    estimates = _require_length("estimates", estimates, count, "labels")
    low = _require_length("low", low, count, "labels")
    high = _require_length("high", high, count, "labels")
    for label, est, lo, hi in zip(labels, estimates, low, high):
        if not lo <= est <= hi:
            raise ValueError(f"{label!r}: the interval must satisfy low <= estimate <= high "
                             f"(got {lo}, {est}, {hi})")
    rows = list(range(count))
    below = [est - lo for est, lo in zip(estimates, low)]
    above = [hi - est for est, hi in zip(estimates, high)]
    ax.errorbar(estimates, rows, xerr=[below, above], fmt="o", color=_palette()[0], capsize=0)
    if reference is not None:
        ax.axvline(reference, color=_reference_colour(), **REFERENCE_STYLE)
    ax.set_yticks(rows, [str(label) for label in labels])
    ax.set_ylim(count - 0.5, -0.5)
    return ax


def grouped_bars(ax, groups, series, *, errors=None):
    """Grouped bar chart: `groups` label the x axis, `series` maps a name to
    one value per group, `errors` (same shape, optional) maps a name to one
    symmetric error or one (low, high) pair of distances per group. Adds a
    legend."""
    groups = _require_rows("groups", groups)
    names = _require_rows("series", series)
    values = {name: _require_length(f"series[{name!r}]", series[name], len(groups), "groups")
              for name in names}
    errors = dict(errors or {})
    _require_known("errors", errors, values)
    yerrs = {name: _bar_errors(name, errors[name], len(groups)) for name in errors}
    colours = _palette()
    width = BAR_GROUP_WIDTH / len(names)
    centres = list(range(len(groups)))
    for index, name in enumerate(names):
        offset = (index - (len(names) - 1) / 2) * width
        ax.bar([c + offset for c in centres], values[name], width, label=str(name),
               color=colours[index % len(colours)], yerr=yerrs.get(name),
               error_kw={"ecolor": _reference_colour(), "elinewidth": 0.8})
    ax.set_xticks(centres, [str(group) for group in groups])
    ax.legend()
    return ax


def distribution_plot(ax, samples, *, kind="violin"):
    """One violin (`kind="violin"`, with its median) or one box
    (`kind="box"`) per named 1-D sample, labelled on the x axis."""
    if kind not in DISTRIBUTION_KINDS:
        raise ValueError(f"kind must be one of {DISTRIBUTION_KINDS}, got {kind!r}")
    names = _require_rows("samples", samples)
    data = []
    for name in names:
        values = list(samples[name])
        if not values:
            raise ValueError(f"samples[{name!r}] is empty")
        data.append(values)
    colours = _palette()
    positions = list(range(1, len(names) + 1))
    if kind == "violin":
        parts = ax.violinplot(data, positions=positions, showmedians=True)
        for index, body in enumerate(parts["bodies"]):
            body.set_facecolor(colours[index % len(colours)])
            body.set_edgecolor(colours[index % len(colours)])
    else:
        parts = ax.boxplot(data, positions=positions, patch_artist=True)
        for index, box in enumerate(parts["boxes"]):
            box.set_facecolor(colours[index % len(colours)])
    ax.set_xticks(positions, [str(name) for name in names])
    return ax


def line_plot(ax, x, series, *, bands=None):
    """One line per named series over `x`; `bands` (optional) maps a series
    name to a (low, high) pair of sequences, shaded in that line's colour.
    Adds a legend when there is more than one series."""
    x = _require_rows("x", x)
    names = _require_rows("series", series)
    values = {name: _require_length(f"series[{name!r}]", series[name], len(x), "x") for name in names}
    bands = dict(bands or {})
    _require_known("bands", bands, values)
    shaded = {}
    for name, band in bands.items():
        band = list(band)
        if len(band) != 2:
            raise ValueError(f"band {name!r} must be a (low, high) pair of sequences")
        shaded[name] = (_require_length(f"band {name!r} low", band[0], len(x), "x"),
                        _require_length(f"band {name!r} high", band[1], len(x), "x"))
    colours = _palette()
    for index, name in enumerate(names):
        colour = colours[index % len(colours)]
        ax.plot(x, values[name], color=colour, label=str(name))
        if name in shaded:
            ax.fill_between(x, *shaded[name], color=colour, alpha=BAND_ALPHA, linewidth=0)
    if len(names) > 1:
        ax.legend()
    return ax


# ------------------------------------------------- illustrative-result helpers
#
# Spec S4 of `odd/tasks/illustrative-results.md`: the Results show what the
# novelty does at its basic stages before any aggregate metric. These helpers
# draw only from arrays the experiment already recorded (embeddings arrive
# already projected to 2-D: no UMAP or t-SNE dependency here).

TOTAL_TERM = "total"
TOTAL_LINEWIDTH_FACTOR = 1.6
CONFUSION_AXIS_LABELS = ("Predicted", "True")


def _require_matrix(name: str, matrix) -> list:
    """`matrix` as a non-empty rectangular list of rows of floats."""
    rows = _require_rows(name, matrix)
    table = []
    for index, row in enumerate(rows):
        if isinstance(row, (str, bytes)) or not hasattr(row, "__iter__"):
            raise ValueError(f"{name} must be 2-D: a sequence of rows")
        table.append([float(value) for value in row])
    if not table[0]:
        raise ValueError(f"{name} needs at least one column")
    for index, row in enumerate(table):
        if len(row) != len(table[0]):
            raise ValueError(f"{name} row {index} has {len(row)} values; row 0 has {len(table[0])}")
    return table


def _require_band(name: str, band, count: int, against: str) -> tuple:
    band = list(band)
    if len(band) != 2:
        raise ValueError(f"band {name!r} must be a (low, high) pair of sequences")
    low = _require_length(f"band {name!r} low", band[0], count, against)
    high = _require_length(f"band {name!r} high", band[1], count, against)
    if any(lo > hi for lo, hi in zip(low, high)):
        raise ValueError(f"band {name!r} must satisfy low <= high at every point")
    return low, high


def forecast_plot(ax, t_input, y_input, t_output, target, predictions, *, bands=None):
    """Prediction example: the input window (solid) and the target over the
    forecast horizon (dashed) in the reference colour, a dotted line at the
    forecast origin, then one line per named prediction (the proposal first,
    then the comparators, in house colours) with an optional (low, high)
    band per prediction (a confidence interval, or a Monte Carlo or Monte
    Carlo dropout spread). Adds a legend."""
    t_input = _require_rows("t_input", t_input)
    y_input = _require_length("y_input", y_input, len(t_input), "t_input")
    t_output = _require_rows("t_output", t_output)
    target = _require_length("target", target, len(t_output), "t_output")
    names = _require_rows("predictions", predictions)
    values = {name: _require_length(f"predictions[{name!r}]", predictions[name], len(t_output), "t_output")
              for name in names}
    bands = dict(bands or {})
    _require_known("bands", bands, values)
    shaded = {name: _require_band(name, band, len(t_output), "t_output") for name, band in bands.items()}
    reference = _reference_colour()
    ax.plot(t_input, y_input, color=reference, label="Input window")
    ax.plot(t_output, target, color=reference, linestyle="--", label="Target")
    ax.axvline(t_input[-1], color=reference, linestyle=":", linewidth=REFERENCE_STYLE["linewidth"])
    colours = _palette()
    for index, name in enumerate(names):
        colour = colours[index % len(colours)]
        ax.plot(t_output, values[name], color=colour, label=str(name))
        if name in shaded:
            ax.fill_between(t_output, *shaded[name], color=colour, alpha=BAND_ALPHA, linewidth=0)
    ax.legend()
    return ax


def loss_terms_plot(ax, steps, terms, *, log=True):
    """Per-term training curves of a loss or regularizer over `steps` (epoch
    or step), in house colours, on a log y axis by default. A term named
    `"total"` is drawn as the total: thicker, in the reference colour. Adds a
    legend when there is more than one curve."""
    steps = _require_rows("steps", steps)
    names = _require_rows("terms", terms)
    values = {name: _require_length(f"terms[{name!r}]", terms[name], len(steps), "steps") for name in names}
    if log:
        for name, curve in values.items():
            if any(value <= 0 for value in curve):
                raise ValueError(f"terms[{name!r}] has a value <= 0, which a log axis cannot show; "
                                 "pass log=False")
    colours = _palette()
    linewidth = _line_width()
    term_index = 0
    for name in names:
        if name == TOTAL_TERM:
            ax.plot(steps, values[name], color=_reference_colour(), label=str(name),
                    linewidth=linewidth * TOTAL_LINEWIDTH_FACTOR)
            continue
        ax.plot(steps, values[name], color=colours[term_index % len(colours)], label=str(name))
        term_index += 1
    if log:
        ax.set_yscale("log")
    if len(names) > 1:
        ax.legend()
    return ax


def heatmap_plot(ax, matrix, *, x_labels=None, y_labels=None, colorbar=True):
    """imshow of a representation (an attention map, a field the network
    reconstructs, a feature map), row 0 at the top, with optional tick
    labels per column and row and a colour bar beside the Axes."""
    table = _require_matrix("matrix", matrix)
    columns, rows = len(table[0]), len(table)
    if x_labels is not None:
        x_labels = _require_length("x_labels", x_labels, columns, "the matrix's columns")
    if y_labels is not None:
        y_labels = _require_length("y_labels", y_labels, rows, "the matrix's rows")
    image = ax.imshow(table, aspect="auto", interpolation="nearest")
    if x_labels is not None:
        ax.set_xticks(list(range(columns)), [str(label) for label in x_labels])
    if y_labels is not None:
        ax.set_yticks(list(range(rows)), [str(label) for label in y_labels])
    if colorbar:
        ax.figure.colorbar(image, ax=ax)
    return ax


def embedding_plot(ax, coords, labels):
    """A 2-D embedding (already projected: UMAP, t-SNE, PCA or similar) as
    one scatter per label, in first-seen order and house colours. Adds a
    legend."""
    points = _require_rows("coords", coords)
    labels = _require_length("labels", labels, len(points), "coords")
    pairs = []
    for point in points:
        if isinstance(point, (str, bytes)) or not hasattr(point, "__len__") or len(point) != 2:
            raise ValueError("coords must be 2-D: one (x, y) pair per point")
        pairs.append((float(point[0]), float(point[1])))
    groups: dict = {}
    for pair, label in zip(pairs, labels):
        groups.setdefault(label, []).append(pair)
    colours = _palette()
    for index, (label, members) in enumerate(groups.items()):
        ax.scatter([x for x, _ in members], [y for _, y in members], s=8,
                   color=colours[index % len(colours)], label=str(label))
    ax.legend()
    return ax


def confusion_matrix_plot(ax, matrix, labels, *, normalize=False):
    """A confusion matrix: rows are true classes, columns predicted ones,
    each cell annotated with its count (or, with `normalize`, its share of
    the true row, two decimals)."""
    labels = _require_rows("labels", labels)
    table = _require_matrix("matrix", matrix)
    _require_length("matrix rows", table, len(labels), "labels")
    if len(table[0]) != len(labels):
        raise ValueError(f"matrix rows have {len(table[0])} columns; labels has {len(labels)}")
    if any(value < 0 for row in table for value in row):
        raise ValueError("matrix holds a negative count")
    if normalize:
        for label, row in zip(labels, table):
            if sum(row) == 0:
                raise ValueError(f"true class {label!r} has no samples, so its row cannot be normalized")
        table = [[value / sum(row) for value in row] for row in table]
    ax.imshow(table, interpolation="nearest")
    peak = max(max(row) for row in table)
    for i, row in enumerate(table):
        for j, value in enumerate(row):
            text = f"{value:.2f}" if normalize else f"{value:g}"
            colour = "white" if peak and value > peak / 2 else _reference_colour()
            ax.text(j, i, text, ha="center", va="center", color=colour)
    ticks = list(range(len(labels)))
    ax.set_xticks(ticks, [str(label) for label in labels])
    ax.set_yticks(ticks, [str(label) for label in labels])
    ax.set_xlabel(CONFUSION_AXIS_LABELS[0])
    ax.set_ylabel(CONFUSION_AXIS_LABELS[1])
    return ax


def roc_plot(ax, curves):
    """ROC curves: `curves` maps a name to (fpr, tpr) or (fpr, tpr, auc);
    the AUC, when given, enters the legend label. Draws the chance diagonal
    and fixes both axes to [0, 1]."""
    names = _require_rows("curves", curves)
    parsed = {}
    for name in names:
        curve = list(curves[name])
        if len(curve) not in (2, 3):
            raise ValueError(f"curves[{name!r}] must be (fpr, tpr) or (fpr, tpr, auc)")
        fpr = list(curve[0])
        tpr = _require_length(f"curves[{name!r}] tpr", curve[1], len(fpr), "fpr")
        if len(fpr) < 2:
            raise ValueError(f"curves[{name!r}] needs at least two points")
        if any(not 0 <= value <= 1 for value in fpr + tpr):
            raise ValueError(f"curves[{name!r}] rates must lie in [0, 1]")
        auc = curve[2] if len(curve) == 3 else None
        if auc is not None and not 0 <= auc <= 1:
            raise ValueError(f"curves[{name!r}] auc must lie in [0, 1], got {auc}")
        parsed[name] = (fpr, tpr, auc)
    colours = _palette()
    for index, (name, (fpr, tpr, auc)) in enumerate(parsed.items()):
        label = str(name) if auc is None else f"{name} (AUC = {auc:.2f})"
        ax.plot(fpr, tpr, color=colours[index % len(colours)], label=label)
    ax.plot([0, 1], [0, 1], color=_reference_colour(), **REFERENCE_STYLE)
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.legend()
    return ax
