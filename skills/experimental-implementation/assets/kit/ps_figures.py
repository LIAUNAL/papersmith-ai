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
