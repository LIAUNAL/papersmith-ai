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
for the vector verdicts (`printed-font-range`, `background`, `whitespace`,
`in-figure-title`; see `typeset.py`), the compiled manuscript around it
(`main.log` for the body size and `\\textwidth`, `main.tex` for the printed
width, `main.pdf` for table widths and per-page whitespace; see
`page_space.py`), and reports the advisories `numeric-text`, `width-share`
and `page-whitespace` beside the roster: it reads the PNG and
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

import sys as _floor_sys
if _floor_sys.version_info < (3, 11):  # the package floor (pyproject requires-python >=3.11)
    _floor_sys.stdout.write('{"ok": false, "error": "PYTHON_VERSION_UNSUPPORTED", "message": "this skill needs '
                            'Python 3.11+; the running interpreter is %d.%d. Run it with the workspace '
                            'environment (.micromamba/envs/papersmith/bin/python) or the smith interpreter."}\n'
                            % _floor_sys.version_info[:2])
    raise SystemExit(2)

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import findings  # noqa: E402
import page_space  # noqa: E402
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
    main_tex = Path(args.main_tex) if args.main_tex else pdf.resolve().parent.parent / "main.tex"
    main_log = Path(args.main_log) if args.main_log else main_tex.with_suffix(".log")
    main_pdf = Path(args.main_pdf) if args.main_pdf else main_tex.with_suffix(".pdf")
    log_text = page_space.read_log(main_log if main_log.is_file() else None)
    manuscript = page_space.read_manuscript(main_tex if main_tex.is_file() else None)

    body_evidence = None
    from_log = page_space.body_pt_from_log(log_text)
    if args.body_pt is not None:
        body_pt, body_source = float(args.body_pt), "flag"
    elif from_log is not None:
        (body_pt, body_evidence), body_source = from_log, "log"
    else:
        body_pt, body_source = typeset.body_pt_from_main_tex(main_tex if main_tex.is_file() else None)

    widths = page_space.text_widths(manuscript, log_text, body_pt)
    float_list = page_space.floats(manuscript, widths)
    printed_width_pt, width_source, width_detail = args.printed_width_pt, "flag", None
    if printed_width_pt is None:
        printed_width_pt, width_source, width_detail = typeset.printed_width_from_manuscript(
            pdf, page_space.placement_for(pdf.stem, float_list))

    vector = typeset.measure_pdf(
        pdf, body_pt=body_pt, body_source=body_source, printed_width_pt=printed_width_pt,
        printed_width_source=width_source,
    )
    advisories, pdf_tables = _manuscript_advisories(main_pdf, widths)
    if manuscript is None:
        advisories["width-share"] = {"verdict": "unmeasured", "reason": "MANUSCRIPT_SOURCE_ABSENT",
                                     "floor": page_space.WIDTH_SHARE_FLOOR, "floats": []}
    else:
        advisories["width-share"] = page_space.width_share(float_list, widths, pdf_tables, pdf.stem)
    sources = {
        "bodyPt": {"value": body_pt, "source": body_source, "evidence": body_evidence,
                   "log": str(main_log) if log_text is not None else None},
        "printedWidthPt": {"value": printed_width_pt, "source": width_source,
                           "detail": width_detail},
        "textWidthPt": {"value": widths["textWidthPt"], "source": widths["textWidthSource"],
                        "columnWidthPt": widths["columnWidthPt"], "twocolumn": widths["twocolumn"]},
    }
    visual = findings.measure_figure(
        png_path, raster_provenance,
        tex_path=tex_path if tex_path.is_file() else None,
        vector=vector, advisories=advisories, sources=sources,
    )
    report_path = out_dir / "visual-report.json"
    raster._atomic_write_json(report_path, visual)
    return {"visualReport": str(report_path), **visual}


def _manuscript_advisories(main_pdf: Path, widths: dict) -> tuple:
    """`page-whitespace` read from the compiled manuscript, and its table
    rule widths for `width-share`; unmeasured with a reason when the PDF is
    absent, unreadable, or this interpreter cannot read PDFs."""
    def unmeasured(reason: str) -> tuple:
        return {"page-whitespace": {"verdict": "unmeasured", "reason": reason, "pages": []}}, None

    if not main_pdf.is_file():
        return unmeasured("MANUSCRIPT_PDF_ABSENT")
    try:
        import print_scale
    except ImportError:
        return unmeasured("PDF_READER_ABSENT")
    if not print_scale.pdf_reader_available():
        return unmeasured("PDF_READER_ABSENT")
    try:
        pages = page_space.read_pages(main_pdf)
    except (print_scale.pdfium.PdfiumError, OSError):
        return unmeasured("PDF_UNREADABLE")
    text_width = widths["textWidthPt"]
    text_width_pdf = None if text_width is None else text_width * page_space.TEX_PT_TO_PDF_PT
    report = page_space.page_whitespace(pages, text_width_pdf)
    report["pdf"] = str(main_pdf)
    return {"page-whitespace": report}, page_space.table_widths(pages)


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
        help="manuscript body size in TeX points (default: --main-log, else --main-tex)")
    p_measure.add_argument(
        "--main-tex", default=None, metavar="path",
        help="the manuscript whose \\documentclass[<N>pt] sets the body size "
             "(default: <paper>/main.tex two levels above --pdf; 10 pt when absent)")
    p_measure.add_argument(
        "--main-log", default=None, metavar="path",
        help="the compiled manuscript's log, read for the effective body size and "
             "\\textwidth (default: <main-tex>.log)")
    p_measure.add_argument(
        "--main-pdf", default=None, metavar="path",
        help="the compiled manuscript, read for table widths and per-page whitespace "
             "(default: <main-tex>.pdf)")
    p_measure.add_argument(
        "--printed-width-pt", type=float, default=None, metavar="pt",
        help="the width the figure prints at, in PDF points (e.g. 0.8\\textwidth of 345 pt = "
             "0.8 * 345 * 72/72.27); default: the figure's \\includegraphics width in "
             "--main-tex, else natural size")
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
