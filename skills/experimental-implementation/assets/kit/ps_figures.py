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
