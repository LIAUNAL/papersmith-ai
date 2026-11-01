#!/usr/bin/env python3
"""figure-review: turn an already-compiled figure PDF into pixels, and
compute the geometric facts a raster can actually support.

This front door answers a command, never a session claim
(`figure-raster` spec, `Requirement: Presence Is a Command the Front Door
Answers`). Two verbs today:

    python review_cli.py probe [--json] [--path PATH]
    python review_cli.py raster --pdf <path/to/id.pdf> [--dpi 150]
                                 [--out DIR] [--path PATH] [--timeout SECONDS]

`probe` reports which of the fixed rasterizer chain
(`pdftoppm`, `pdftocairo`, `gs`, `sips`) this machine's `PATH` resolves, or
refuses `RASTER_TOOLCHAIN_ABSENT` naming all four and the exact `PATH`
searched. `raster` produces `<id>.png` and `raster-provenance.json` from an
already-compiled PDF — it compiles nothing, and it never opens a
repair-budget ledger.

`measure` turns an already-produced raster into computed findings
(out-of-bounds, overlap, canvas occupancy), and reads the figure PDF itself
for the vector verdicts (`min-printed-font`, `background`, `whitespace`,
`in-figure-title`; see `typeset.py`): it reads the PNG and
`raster-provenance.json` a prior `raster` call already wrote, decodes
and measures via `png_read`/`geometry`/`findings`, and writes a
plain-data `visual-report.json` beside them. It refuses
`DIAGRAM_SOURCE_ABSENT` when no prior raster is found — `measure` never
rasterizes on its own.

`--path` and `--timeout` are test-only injection points, exactly like
`paper_latex.compile`'s own `path=` operand: a caller can point this front
door at a scratch `PATH` holding stub executables, or shorten the per-link
timeout, without touching the real toolchain or the real 60-second bound.

Exit codes: 0 the command answered; 2 a refusal — nothing was written.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import findings  # noqa: E402
import raster  # noqa: E402
import typeset  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402


def _scratch_dir_for(pdf: Path) -> Path:
    """The same scratch-directory shape `paper_figure.figure_paths` already
    resolves for this figure id — computed independently here, never by
    importing `paper_figure` (design.md: "Never an edge: paper-writing --X-->
    figure-review"). `pdf` is expected at `<paper>/Figures/<id>.pdf`, so the
    paper directory is two levels up."""
    figure_id = pdf.stem
    paper_dir = pdf.resolve().parent.parent
    return paper_dir / ".paper-writing" / "figures" / figure_id


def cmd_probe(args: argparse.Namespace) -> dict:
    return raster.probe(path=args.path)


def cmd_raster(args: argparse.Namespace) -> dict:
    pdf = Path(args.pdf)
    if not pdf.is_file():
        raise Refused("DIAGRAM_SOURCE_ABSENT", f"{pdf} does not exist")
    out_dir = Path(args.out) if args.out else _scratch_dir_for(pdf)
    kwargs: dict = {"dpi": args.dpi, "path": args.path}
    if args.timeout is not None:
        kwargs["timeout"] = args.timeout
    return raster.rasterize(pdf, out_dir, **kwargs)


def cmd_measure(args: argparse.Namespace) -> dict:
    pdf = Path(args.pdf)
    out_dir = Path(args.out) if args.out else _scratch_dir_for(pdf)
    png_path = out_dir / f"{pdf.stem}.png"
    provenance_path = out_dir / "raster-provenance.json"
    if not png_path.is_file() or not provenance_path.is_file():
        raise Refused(
            "DIAGRAM_SOURCE_ABSENT",
            f"no raster found for {pdf} in {out_dir}; run `raster` first",
        )
    raster_provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    tex_path = Path(args.tex) if args.tex else pdf.with_suffix(".tex")
    if args.body_pt is not None:
        body_pt, body_source = float(args.body_pt), "flag"
    else:
        main_tex = Path(args.main_tex) if args.main_tex else pdf.resolve().parent.parent / "main.tex"
        body_pt, body_source = typeset.body_pt_from_main_tex(main_tex if main_tex.is_file() else None)
    vector = typeset.measure_pdf(
        pdf, body_pt=body_pt, body_source=body_source, printed_width_pt=args.printed_width_pt,
    )
    visual = findings.measure_figure(
        png_path, raster_provenance,
        tex_path=tex_path if tex_path.is_file() else None,
        vector=vector,
    )
    report_path = out_dir / "visual-report.json"
    raster._atomic_write_json(report_path, visual)
    return {"visualReport": str(report_path), **visual}


_COMMANDS = {
    "probe": cmd_probe,
    "raster": cmd_raster,
    "measure": cmd_measure,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rasterize an already-compiled figure PDF and report the geometric "
                    "facts a raster can actually support.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser(
        "probe", help="report which rasterizer link this machine's PATH resolves")
    p_probe.add_argument("--path", default=None, help="override PATH, test-only")
    p_probe.add_argument("--json", action="store_true", help="machine-readable output")
    p_probe.set_defaults(func=cmd_probe)

    p_raster = sub.add_parser(
        "raster", help="rasterize an already-compiled figure PDF to PNG plus provenance")
    p_raster.add_argument("--pdf", required=True, metavar="path", help="the compiled figure PDF")
    p_raster.add_argument("--dpi", type=int, default=raster.DEFAULT_DPI)
    p_raster.add_argument(
        "--out", default=None, metavar="dir",
        help="override the derived scratch directory")
    p_raster.add_argument("--path", default=None, help="override PATH, test-only")
    p_raster.add_argument(
        "--timeout", type=float, default=None,
        help="override the per-link timeout in seconds, test-only")
    p_raster.add_argument("--json", action="store_true", help="machine-readable output")
    p_raster.set_defaults(func=cmd_raster)

    p_measure = sub.add_parser(
        "measure", help="compute visual findings from a raster `raster` already produced")
    p_measure.add_argument("--pdf", required=True, metavar="path", help="the compiled figure PDF")
    p_measure.add_argument(
        "--out", default=None, metavar="dir",
        help="override the derived scratch directory (must match the `raster` call's)")
    p_measure.add_argument(
        "--tex", default=None, metavar="path",
        help="override the sibling .tex path used for the border precondition")
    p_measure.add_argument(
        "--body-pt", type=float, default=None, metavar="pt",
        help="manuscript body size in TeX points (default: read from --main-tex)")
    p_measure.add_argument(
        "--main-tex", default=None, metavar="path",
        help="the manuscript whose \\documentclass[<N>pt] sets the body size "
             "(default: <paper>/main.tex two levels above --pdf; 10 pt when absent)")
    p_measure.add_argument(
        "--printed-width-pt", type=float, default=None, metavar="pt",
        help="the width the figure prints at, in PDF points (e.g. 0.8\\textwidth of 345 pt = "
             "0.8 * 345 * 72/72.27); default: natural size")
    p_measure.add_argument("--json", action="store_true", help="machine-readable output")
    p_measure.set_defaults(func=cmd_measure)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = _COMMANDS[args.command](args)
    except Refused as exc:
        print(json.dumps({"status": "refused", "code": exc.code, "detail": exc.detail}))
        return 2
    print(json.dumps({"status": "ok", "command": args.command, **result}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
