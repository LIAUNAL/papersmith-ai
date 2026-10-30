#!/usr/bin/env python3
"""Paper ingestion — one self-contained folder per paper.

For each **loose** ``<root>/<stem>.pdf`` (a PDF sitting directly in a source
root), this creates ``<root>/<stem>/``, converts the PDF, strips the
references/bibliography section, writes each figure as its own image file,
writes ``<stem>.md`` that references those files and ``<stem>.json`` that maps
it (pages, headings, equations, references, figures), and finally moves the PDF
in. So a paper's whole footprint lives in one folder: ``pdf + md + json +
figure images``.

The default engine, ``auto``, routes page by page (``pdf_pipeline.py``): a
digital prose page is read from its text layer by pypdfium2 in milliseconds,
and only pages with display mathematics, tables or no text layer go to Docling,
through its page range, with formulas as LaTeX and OCR only for scanned pages.
Every page is cached by the PDF's SHA-256, so re-ingesting a paper, or the same
PDF fetched again, converts nothing twice. Every default engine is
license-unrestricted (Apache-2.0, BSD, MIT, CDLA-Permissive-2.0: no copyleft,
no revenue or user threshold). ``marker`` remains as an explicit opt-in whose
model weights are free only below a funding/revenue threshold.

A loose PDF = not yet ingested. Once ingested, the PDF lives inside its folder,
so it is no longer loose and is skipped on the next run.

Ingestion is transactional: conversion happens in a staging directory and the
PDF is moved only once the Markdown and figures are safely in place. A paper
that fails to convert is left **loose**, so the next run retries it instead of
silently reporting "nothing to ingest".

The ``.md`` stays lean (text + LaTeX equations + Markdown tables); figures are
referenced, not embedded — an agent loads a specific figure only when it needs
it. Local and keyless: no API keys and no LLM service.

Source roots are discovered on every run: each folder directly under
``source_base`` that already holds a loose PDF is one, so a new paper folder
needs no configuration edit.

Ingestion *moves* files, so it is never the first thing that runs. ``--list``
answers "what is pending?" without loading a single model, which is what lets
the skill show the findings and get an answer before anything is displaced.

A PDF dropped directly in ``source_base``, beside the topic folders rather than
inside one, is reported and never ingested. Converting it where it lies would make
it a topic of its own, and which topic a paper belongs to is not a decision this
script can make — so it names the options and waits for one.

Usage:
    python extract_pdf.py --list          # report the loose PDFs, ingest nothing
    python extract_pdf.py                 # ingest every loose PDF under every source root
    python extract_pdf.py <pdf> [<pdf>…]  # ingest exactly these loose PDFs
    python extract_pdf.py --force-ocr <pdf>  # OCR every page, ignore the text layer
    python extract_pdf.py --engine pdfium <pdf>  # fast path only, no model
    python extract_pdf.py --verify-cache  # re-check every cached page, ingest nothing
    python extract_pdf.py --file <pdf> --into <topic>  # file an unfiled PDF, ingest nothing

Exit codes: 0 success (or nothing to do), 1 at least one paper failed,
2 configuration/usage/environment error (nothing was touched).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Apple Silicon (MPS) needs CPU fallback for the handful of ops surya/torch
# do not yet implement on the Metal backend.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

# On Intel Macs with discrete AMD GPUs, MPS is exposed by Metal but unsupported
# by PyTorch (which requires unified memory on Apple Silicon). Default to CPU
# unless the operator explicitly chose another device.
import platform
if sys.platform == "darwin" and platform.machine() == "x86_64":
    os.environ.setdefault("TORCH_DEVICE", "cpu")


# skills/paper-ingestion/scripts/extract_pdf.py -> repo root is parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # pdf_pipeline beside this script
CONFIG_PATH = REPO_ROOT / "papersmith.yaml"
SETUP_SCRIPT = "./skills/paper-ingestion/setup.sh"

VALID_MODES = ("fast", "balanced")
#: auto: route each page; pdfium: fast path only; docling: every page through
#: Docling; marker: the former whole-document engine, opt-in (weights licensed
#: under a modified OpenRAIL-M, free only below USD 5M funding or revenue).
VALID_ENGINES = ("auto", "pdfium", "docling", "marker")
DEFAULT_ENGINE = "auto"
CACHE_DIR = Path(".papersmith") / "cache" / "ingestion"
MARKER_LICENSE_NOTE = (
    "engine 'marker': its model weights are licensed under a modified OpenRAIL-M that is "
    "free only for research, personal use and organizations under USD 5M in funding or "
    "revenue; set engine: auto in papersmith.yaml for the license-unrestricted engines")

# A references/bibliography heading (EN or ES). Marker decorates headings with
# bold (**References**), anchor <span> wrappers, and leading numbers, so match
# the heading line, then test its cleaned title text.
_HEADING_LINE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
_REFERENCES_TITLE = re.compile(
    r"^(?:\d+\.?\s*)?(?:references|bibliography|referencias|bibliograf[ií]a)\b",
    re.IGNORECASE,
)
_MARKDOWN_DECOR = re.compile(r"[*_`~]|<[^>]+>")


class ConfigError(Exception):
    """The `paper_ingestion` configuration is missing or malformed."""


class EngineError(Exception):
    """The configured engine is not usable in this environment."""


class IngestionError(Exception):
    """A single paper could not be ingested; the run continues with the rest."""


def load_config(path: Path | None = None) -> dict:
    """Read and validate the `paper_ingestion` block. Raises `ConfigError`.

    Fail closed: a missing file, unparseable YAML, a missing block, or a value
    of the wrong shape is reported instead of being silently treated as "no
    papers to ingest", which is indistinguishable from a healthy no-op.
    """
    # Imported here, not at module scope: the CLI's own refusal surface
    # (usage, argparse errors) must be reachable on an interpreter without
    # the conversion stack -- the skill-audit probe drives exactly that
    # path, and a top-level import turned its `exit 2` into a traceback's
    # `exit 1` on any machine without PyYAML.
    import yaml

    path = CONFIG_PATH if path is None else path
    if not path.exists():
        raise ConfigError(f"{path} not found")
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        detail = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        raise ConfigError(f"{path} is not valid YAML: {detail}") from None
    if data is None:
        raise ConfigError(f"{path} is empty")
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must be a YAML mapping")

    cfg = data.get("paper_ingestion")
    if cfg is None:
        raise ConfigError(f"{path} has no 'paper_ingestion' block")
    if not isinstance(cfg, dict):
        raise ConfigError("'paper_ingestion' must be a mapping of settings")

    engine = cfg.get("engine")
    if engine is not None and engine not in VALID_ENGINES:
        raise ConfigError(f"unknown engine {engine!r}; expected one of {', '.join(VALID_ENGINES)}")

    mode = cfg.get("mode")
    if mode is not None and mode not in VALID_MODES:
        raise ConfigError(f"unknown mode {mode!r}; expected one of {', '.join(VALID_MODES)}")

    strip_refs = cfg.get("strip_references")
    if strip_refs is not None and not isinstance(strip_refs, bool):
        raise ConfigError(f"strip_references must be true or false, got {strip_refs!r}")

    force_ocr = cfg.get("force_ocr")
    if force_ocr is not None and not isinstance(force_ocr, bool):
        raise ConfigError(f"force_ocr must be true or false, got {force_ocr!r}")

    for flag in ("cache", "formulas_on_cpu"):
        value = cfg.get(flag)
        if value is not None and not isinstance(value, bool):
            raise ConfigError(f"{flag} must be true or false, got {value!r}")

    roots = cfg.get("source_roots")
    if roots is not None:
        if not isinstance(roots, list) or not all(isinstance(r, str) for r in roots):
            raise ConfigError("source_roots must be a list of folder paths")

    base = cfg.get("source_base")
    if base is not None and not isinstance(base, str):
        raise ConfigError(f"source_base must be a folder path, got {base!r}")
    return cfg


def is_pdf(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


def is_loose(pdf: Path) -> bool:
    """A PDF is loose until it lives inside its own `<stem>/` folder."""
    return pdf.parent.name != pdf.stem


def loose_pdfs_in(folder: Path) -> list[Path]:
    """Loose PDFs sitting directly in `folder` (never a nested folder's)."""
    return sorted(
        entry for entry in folder.iterdir()
        if entry.is_file() and is_pdf(entry) and is_loose(entry)
    )


def base_path_of(cfg: dict) -> Path | None:
    """The configured `source_base` as a folder, or None when there is none."""
    base = cfg.get("source_base")
    if not base:
        return None
    resolved = (REPO_ROOT / base).resolve()
    return resolved if resolved.is_dir() else None


def unfiled_pdfs(cfg: dict) -> list[Path]:
    """Loose PDFs sitting directly in `source_base`, outside every topic folder.

    They are pending and they are invisible, which is the worst pair: discovery only
    promotes the base's *children*, so a PDF dropped beside those children is never
    found and nothing says so — the run reports that every paper is already ingested,
    which is exactly the silence `source_base` fails closed to avoid.

    Ingesting them where they lie is not the fix. The base's children are topics, so
    a paper ingested at that level becomes a topic of its own, and the next run reads
    it as a folder already ingested and leaves it there for good. Which topic a paper
    belongs to is a judgement nothing here can make, so these are reported and never
    moved: the flow asks, and `--into` files them once there is an answer.
    """
    base_path = base_path_of(cfg)
    return loose_pdfs_in(base_path) if base_path else []


def filing_options(cfg: dict) -> list[str]:
    """The topic folders an unfiled PDF could be filed into, as they exist now.

    Read from the tree rather than configured, for the same reason the roots are:
    a topic added last week is an option this week with nothing edited anywhere.
    """
    base_path = base_path_of(cfg)
    if not base_path:
        return []
    return sorted(child.name for child in base_path.iterdir()
                  if child.is_dir() and not child.name.startswith("."))


def file_into(pdf: Path, folder: str, cfg: dict) -> Path:
    """Move an unfiled PDF into a topic folder under the base, creating it if new.

    This is filing, not ingestion: the PDF lands loose inside the topic so the next
    ordinary run discovers it and converts it. Doing it here rather than leaving the
    caller a `mv` is what keeps it under the same guards as everything else that
    displaces a file. Raises `ConfigError`.
    """
    base_path = base_path_of(cfg)
    if base_path is None:
        raise ConfigError("no source_base configured; there is nowhere to file into")
    if not folder or folder.startswith(".") or Path(folder).name != folder:
        raise ConfigError(f"{folder!r} is not a folder name directly under the base")
    if pdf.parent.resolve() != base_path:
        raise ConfigError(f"{pdf.name} is not an unfiled PDF sitting in the base")

    destination = base_path / folder
    if destination.exists() and not destination.is_dir():
        raise ConfigError(f"{folder} exists and is not a folder")
    landing = destination / pdf.name
    # Never displace a file that is already there: the two may be different papers
    # under one name, and the move would destroy the one that arrived first.
    if landing.exists():
        raise ConfigError(f"{folder}/{pdf.name} already exists; nothing was moved")
    destination.mkdir(parents=True, exist_ok=True)
    pdf.rename(landing)
    return landing


def discover_source_roots(cfg: dict) -> list[Path]:
    """Resolve the folders to scan: auto-discovered under `source_base`, plus
    any explicit `source_roots`. Raises `ConfigError`.

    A direct child of `source_base` is promoted to a source root only when it
    already holds a loose PDF. Ingestion *moves* files, so that loose PDF is the
    signal that the folder was stocked on purpose — an unrelated folder that
    happens to live under the base is never touched.

    Only one level down: a folder nested inside a root stays invisible, which
    keeps the skill's core rule intact — a subfolder means "paper already
    ingested", not "more papers to find".
    """
    roots: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        if path not in seen:
            seen.add(path)
            roots.append(path)

    base = cfg.get("source_base")
    if base:
        base_path = (REPO_ROOT / base).resolve()
        # Fail closed: a base that is not a folder is a typo, and silently
        # discovering nothing would read exactly like "all papers ingested".
        if not base_path.is_dir():
            raise ConfigError(f"source_base {base} is not a folder")
        for child in sorted(base_path.iterdir()):
            if child.is_dir() and not child.name.startswith(".") and loose_pdfs_in(child):
                add(child)

    for root in cfg.get("source_roots") or []:
        root_path = (REPO_ROOT / root).resolve()
        if root_path.is_dir():
            add(root_path)

    if not base and not cfg.get("source_roots"):
        raise ConfigError("no source_base or source_roots configured; nothing can be discovered")
    return roots


def find_loose_pdfs(source_roots: list[Path]) -> list[Path]:
    """PDFs sitting directly in a source root (not yet moved into their folder)."""
    pdfs: list[Path] = []
    for root_path in source_roots:
        pdfs.extend(loose_pdfs_in(root_path))
    return pdfs


def resolve_single_target(raw: str) -> Path:
    """Validate an explicit `<loose-pdf>` argument. Raises `ConfigError`.

    Checked before the engine loads so a mistyped argument never costs a model
    load, and — more importantly — never displaces a file that is not a paper.
    """
    pdf = Path(raw).expanduser().resolve()
    if not pdf.exists():
        raise ConfigError(f"{pdf} does not exist")
    if pdf.is_dir():
        raise ConfigError(f"{pdf} is a directory, not a PDF")
    if not pdf.is_file():
        raise ConfigError(f"{pdf} is not a regular file")
    if not is_pdf(pdf):
        raise ConfigError(f"{pdf.name} is not a PDF")
    if not is_loose(pdf):
        raise ConfigError(
            f"{pdf.name} is already ingested (it lives in {pdf.parent.name}/); "
            "delete that folder to re-ingest"
        )
    return pdf


def page_count(pdf: Path) -> int | None:
    """Page count for the listing, or `None` when it cannot be read.

    Best-effort on purpose. `--list` exists to answer "what is pending?" before
    any model loads, so a PDF whose page tree will not parse is still worth
    showing — without a page count, rather than not at all.
    """
    try:
        import pypdfium2

        doc = pypdfium2.PdfDocument(pdf)
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:
        return None


def _relative(path: Path) -> Path:
    return path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path


def print_listing(targets: list[Path]) -> None:
    """Report the pending papers: what would be ingested, and how big each is."""
    print(f"Found {len(targets)} loose PDF(s) pending ingestion:")
    for pdf in targets:
        pages = page_count(pdf)
        print(f"  {_relative(pdf)}" + (f"  ({pages} pages)" if pages is not None else ""))


def print_unfiled(unfiled: list[Path], options: list[str]) -> None:
    """Report the PDFs no topic folder covers, and what could be done with them.

    Printed on every run and not only under `--list`, because the moment they are
    easiest to miss is the one where everything else succeeded. Nothing here moves
    them: the options are named so a person can choose, which is the whole reason
    this is a report and not a default.
    """
    print(f"\n{len(unfiled)} PDF(s) sitting in the base, in no topic folder — "
          f"NOT ingested:")
    for pdf in unfiled:
        pages = page_count(pdf)
        print(f"  {_relative(pdf)}" + (f"  ({pages} pages)" if pages is not None else ""))
    print("  Ingesting these where they lie would make each one a topic of its own.")
    print("  File each into a topic, existing or new:")
    print(f"    existing: {', '.join(options)}" if options
          else "    (no topic folder exists yet)")
    print("    python extract_pdf.py --file <pdf> --into <topic>")


def _is_references_heading(match: "re.Match[str]") -> bool:
    """Whether a heading match opens a references/bibliography section."""
    title = _MARKDOWN_DECOR.sub("", match.group(1)).strip()
    return bool(_REFERENCES_TITLE.match(title))


def reference_spans(text: str) -> list[tuple[int, int]]:
    """The ``(begin, end)`` offsets of every references section (see below)."""
    headings = list(_HEADING_LINE.finditer(text))
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(headings):
        if not _is_references_heading(headings[index]):
            index += 1
            continue
        run_end = index
        while (run_end + 1 < len(headings)
               and _is_references_heading(headings[run_end + 1])):
            run_end += 1
        after = headings[run_end + 1] if run_end + 1 < len(headings) else None
        spans.append((headings[index].start(),
                      after.start() if after else len(text)))
        index = run_end + 1
    return spans


#: The page markers ``pdf_pipeline`` writes; a cut keeps them so the pages after
#: a references section still know where they start.
_PAGE_MARKER = re.compile(r"^<!-- page \d+ -->$", re.MULTILINE)


def strip_references(text: str) -> str:
    """Drop EVERY references/bibliography section, and only those sections.

    Two things this must not do, both learned by measuring a real corpus of
    116 ingested documents rather than by reasoning about the shape of a
    paper:

    It must not cut to the end of the document. References are not always
    last: in ML venues the appendix usually follows them. Seventeen of those
    documents carried a references heading and five placed supplementary
    material after it -- cutting to the end removed 52% to 74% of each file,
    taking a generalization bound, a derivation, dataset details and an
    algorithm's specification with it. So each cut ends at the next heading
    that is not itself a references heading.

    That end is the next heading of ANY level, deliberately not the next
    heading at the same or shallower level. The depth rule reads as the
    principled one and fails on real input: one paper puts `# References`
    above a `## A. Further Information ...` appendix, making the appendix
    nominally a CHILD of the references. Marker infers heading levels from
    font size, so depth carries no reliable claim about structure.

    And it must not cut only one section. Eight of those documents carry a
    `References` section in the body AND another later, usually beside
    supplementary material. An earlier version anchored on the LAST one,
    removed the trailing block and left the body's real bibliography in
    place -- which looked like success, because the file did get smaller.
    Every matching section is cut, which also makes this idempotent: a
    second pass has nothing left to find, and a test asserts that rather
    than leaving it for someone to notice.

    A consecutive run of references headings is cut as one span, since a
    two-column render can emit the same heading twice.

    Page markers (``<!-- page N -->``) inside a cut survive it, so a page that
    begins inside the references still has its start in the Markdown.

    Stopping at the first following heading can leave part of a references
    section behind when a bibliography carries sub-headings of its own. That
    is the safe direction and it is chosen on purpose: surviving reference
    lines are a nuisance a reader skips, while a deleted appendix costs a
    PDF re-ingestion to recover.
    """
    spans = reference_spans(text)
    if not spans:
        return text

    kept: list[str] = []
    cursor = 0
    for begin, finish in spans:
        kept.append(text[cursor:begin].rstrip())
        markers = _PAGE_MARKER.findall(text, begin, finish)
        if markers:
            kept.append("\n\n".join(markers))
        cursor = finish
    if cursor < len(text):
        kept.append(text[cursor:])
    return "\n\n".join(part for part in kept if part) + ("\n" if not kept[-1].endswith("\n") else "")

def marker_options(mode: str | None, force_ocr: bool) -> dict:
    """The options handed to Marker's `ConfigParser` for one run.

    `force_ocr` is the one lever that keeps Marker away from the PDF's own text
    layer. Without it, Marker rebuilds every digital table from that layer
    (`tables_pdftext`) in both modes, and falls back to OCR only when its own
    reconstruction score is low -- so a text layer that is present but poor
    (ligatures split, columns interleaved, a broken font map) produces a table
    that is confidently wrong. With it, the provider extracts no text layer and
    every page, tables included, is rebuilt by OCR: slower, and immune to a bad
    layer. It is off by default because a good text layer is exact and OCR is not.
    """
    options: dict = {"output_format": "markdown"}
    if mode:
        options["mode"] = mode
    if force_ocr:
        options["force_ocr"] = True
    return options


def _marker_unavailable(exc: ImportError) -> EngineError:
    return EngineError(
        f"the Marker engine is not available in this interpreter ({exc}). "
        f"Provision it with {SETUP_SCRIPT} and run the script through "
        "skills/paper-ingestion/.venv/bin/python"
    )


def build_converter(mode: str | None, force_ocr: bool = False):
    """Construct a keyless Marker PDF->markdown converter (models loaded once)."""
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.config.parser import ConfigParser
    except ImportError as exc:
        raise _marker_unavailable(exc) from None

    config_parser = ConfigParser(marker_options(mode, force_ocr))
    return PdfConverter(
        config=config_parser.generate_config_dict(),
        artifact_dict=create_model_dict(),
        processor_list=config_parser.get_processors(),
        renderer=config_parser.get_renderer(),
        # No llm_service: ingestion stays local/keyless.
    )


def write_figures(images: dict, folder: Path) -> None:
    """Write each Marker figure to its own file in ``folder`` (names match the
    ``![](name)`` references already present in the Markdown)."""
    for name, image in images.items():
        is_png = name.lower().endswith(".png")
        fmt = "PNG" if is_png else "JPEG"
        if fmt == "JPEG" and image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        image.save(folder / name, format=fmt)


def render_paper(converter, pdf_path: Path, strip_refs: bool, staging: Path) -> None:
    """Convert ``pdf_path`` and write the `.md` + figures (+ `.json`) into ``staging``."""
    if isinstance(converter, RoutedEngine):
        converter.render(pdf_path, strip_refs, staging)
        return
    # Marker is opt-in: guarded here as in build_converter, so the forge gate
    # does not count it as a package every interpreter must carry.
    try:
        from marker.output import text_from_rendered
    except ImportError as exc:
        raise _marker_unavailable(exc) from None

    started = time.monotonic()
    rendered = converter(str(pdf_path))
    text, _ext, images = text_from_rendered(rendered)
    references = [(None, text[a:b]) for a, b in reference_spans(text)]
    if strip_refs:
        text = strip_references(text)
    if images:
        write_figures(images, staging)
    (staging / f"{pdf_path.stem}.md").write_text(text, encoding="utf-8")
    write_sidecar(staging / f"{pdf_path.stem}.json", pdf_path, text, references,
                  engine={"name": "marker"}, pages=[], seconds=time.monotonic() - started)


class RoutedEngine:
    """The page-routed engines: ``auto``, ``pdfium`` and ``docling``.

    ``auto`` sends each page where the probe says (``pdf_pipeline``); ``pdfium``
    keeps every page on the fast path; ``docling`` sends every page with text
    or images to Docling. ``force_ocr`` OCRs every page through Docling, and
    ``mode: balanced`` means fidelity first: every page through Docling.
    When Docling is not installed, ``auto`` reads every page on the fast path
    and says so, so ingestion still works on a core install.
    """

    def __init__(self, engine: str, mode: str | None, force_ocr: bool, cache_root: Path | None,
                 formulas_on_cpu: bool = False, table_mode: str = "fast"):
        import pdf_pipeline

        self.pipeline = pdf_pipeline
        self.engine = engine
        self.all_heavy = engine == "docling" or mode == "balanced" or force_ocr
        self.force_ocr = force_ocr
        self.cache = pdf_pipeline.PageCache(cache_root) if cache_root else None
        self.heavy = pdf_pipeline.HeavyEngine(formulas_on_cpu=formulas_on_cpu, table_mode=table_mode)
        self.heavy_missing: str | None = None

    def _plan(self, probes: list) -> None:
        for probe in probes:
            if self.engine == "pdfium":
                if probe.route in self.pipeline.HEAVY_ROUTES:
                    probe.reason += "; fast path forced by engine pdfium"
                    probe.route = "text"
            elif self.force_ocr:
                probe.route, probe.reason = "scan", "force_ocr"
            elif self.all_heavy and probe.route in ("text", "table", "math"):
                probe.reason += "; every page to Docling"
                probe.route = probe.route if probe.route != "text" else "math"
            elif probe.route == "math" and self.heavy.formula_preset is None:
                # Without a formula model Docling would only box the equations;
                # the text layer reads them better, and in milliseconds.
                probe.reason += f"; {self.heavy.formula_why}"
                probe.route = "text"

    def render(self, pdf_path: Path, strip_refs: bool, staging: Path) -> None:
        import pypdfium2

        pp = self.pipeline
        started = time.monotonic()
        pdf_sha = pp.sha256_file(pdf_path)
        document = pypdfium2.PdfDocument(pdf_path)
        try:
            probes = pp.probe_document(document)
            self._plan(probes)
            line_groups = {p.page: pp.page_lines(document, p.page) for p in probes if p.route not in pp.HEAVY_ROUTES}
            body = pp.body_size(list(line_groups.values()))
            pages: dict[int, object] = {}
            engines: dict[int, str] = {}
            cached: set[int] = set()
            fast_version = f"pypdfium2-{_version('pypdfium2')}"
            for probe in probes:
                if probe.route in pp.HEAVY_ROUTES:
                    continue  # heavy pages are cached and converted by run, below
                key = self._key(pdf_sha, probe, None, body, fast_version)
                hit = self.cache.get(pdf_sha, key) if self.cache else None
                if hit is not None:
                    pages[probe.page] = hit
                    engines[probe.page] = "pdfium"
                    cached.add(probe.page)
                else:
                    page = document[probe.page - 1]
                    try:
                        pages[probe.page] = pp.fast_page_markdown(page, probe.page, body, line_groups[probe.page])
                    finally:
                        page.close()
                    engines[probe.page] = "pdfium"
                    self._store(pdf_sha, key, probe, pages[probe.page], "pdfium")
            heavy_seconds = 0.0
            for run in pp.heavy_runs(probes):
                first, last, ocr, tables = run
                # Docling lays a page out with its neighbours in the same run, so
                # a page is only reused when its whole run is: one missing entry
                # reconverts the run, never one page alone with other neighbours.
                keys = {n: self._key(pdf_sha, probes[n - 1], run, body, fast_version) for n in range(first, last + 1)}
                hits = {n: self.cache.get(pdf_sha, key) for n, key in keys.items()} if self.cache else {}
                if hits and all(hit is not None for hit in hits.values()):
                    for number, hit in hits.items():
                        pages[number] = hit
                        engines[number] = "docling"
                        cached.add(number)
                    continue
                run_started = time.monotonic()
                try:
                    produced = self.heavy.convert(pdf_path, first, last, ocr, tables)
                except ImportError as exc:
                    if self.engine == "docling":
                        raise EngineError(f"the Docling engine is not installed ({exc}); "
                                          f"provision it with {SETUP_SCRIPT}") from None
                    self.heavy_missing = str(exc)
                    produced = {}
                heavy_seconds += time.monotonic() - run_started
                dropped = [n for n in range(first, last + 1) if n not in produced]
                if dropped and self.engine == "docling":
                    # `docling` reads no page any other way: fail the paper so
                    # it stays loose and the next run retries it, rather than
                    # file it with these pages empty (#105).
                    raise EngineError(f"Docling did not convert page(s) {', '.join(map(str, dropped))} of "
                                      f"{pdf_path.name}; the paper was not ingested and the next run retries it")
                for number in range(first, last + 1):
                    probe = probes[number - 1]
                    if number in produced:
                        pages[number] = produced[number]
                        engines[number] = "docling"
                        self._store(pdf_sha, keys[number], probe, produced[number], "docling")
                    else:
                        if number not in line_groups:
                            line_groups[number] = pp.page_lines(document, number)
                        page = document[number - 1]
                        try:
                            pages[number] = pp.fast_page_markdown(page, number, body, line_groups[number])
                        finally:
                            page.close()
                        engines[number] = "pdfium"
                        probe.reason += ("; Docling unavailable, read on the fast path" if self.heavy_missing
                                         else "; Docling did not convert this page, read on the fast path")
        finally:
            document.close()

        blocks = []
        for probe in probes:
            page = pages[probe.page]
            for name, image in page.figures.items():
                pp.write_figure(image, staging / name)
            blocks.append(pp.page_marker(probe.page) + ("\n\n" + page.markdown if page.markdown else ""))
        text = "\n\n".join(blocks) + "\n"
        references = [(_page_before(text, a), text[a:b]) for a, b in reference_spans(text)]
        if strip_refs:
            text = strip_references(text)
        (staging / f"{pdf_path.stem}.md").write_text(text, encoding="utf-8")
        page_rows = [dict(p.as_dict(), engine=engines[p.page], cached=p.page in cached) for p in probes]
        engine = {"name": self.engine, "fast": fast_version, "heavy": None if self.heavy_missing else self._heavy_version(),
                  "heavy_unavailable": self.heavy_missing,
                  "formulas": None if self.engine == "pdfium" else self.heavy.formula_why,
                  "pipeline": pp.PIPELINE_VERSION}
        write_sidecar(staging / f"{pdf_path.stem}.json", pdf_path, text, references, engine=engine,
                      pages=page_rows, seconds=time.monotonic() - started, heavy_seconds=heavy_seconds,
                      pdf_sha=pdf_sha)
        if self.heavy_missing:
            print(f"NOTE {pdf_path.name}: Docling is not installed, so its math/table/scanned pages "
                  f"were read on the fast path (formulas as Unicode, tables as text). "
                  f"Provision it with {SETUP_SCRIPT}.", file=sys.stderr)

    def _heavy_version(self) -> str | None:
        try:
            return f"docling-{self.heavy.version()}"
        except Exception:
            return None

    def _key(self, pdf_sha: str, probe, run: tuple | None, body: float, fast_version: str) -> str:
        """A heavy page's key carries its run: the same page laid out in another
        run is another entry."""
        if run is not None:
            version = self._heavy_version() or "docling-missing"
            options = dict(self.heavy.options(run[2], run[3]), run=[run[0], run[1]])
            return self.pipeline.PageCache.key(pdf_sha, probe.page, probe.route, "docling", version, options)
        return self.pipeline.PageCache.key(pdf_sha, probe.page, probe.route, "pdfium", fast_version, {"body": body})

    def _store(self, pdf_sha: str, key: str, probe, page, engine: str) -> None:
        if self.cache:
            self.cache.put(pdf_sha, key, page, {"pdf_sha256": pdf_sha, "page": probe.page,
                                                "route": probe.route, "engine": engine})


def _version(package: str) -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


def _page_before(text: str, offset: int) -> int | None:
    """The page whose marker last precedes ``offset`` in ``text``."""
    import pdf_pipeline as pp

    pages = [int(m.group(1)) for m in pp.PAGE_MARKER.finditer(text, 0, offset)]
    return pages[-1] if pages else None


#: Where a numbered reference entry begins inside a joined line: "[12] ".
_REFERENCE_START = re.compile(r"\s(?=\[\d{1,3}\]\s)")
_DISPLAY_MATH = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)


def write_sidecar(path: Path, pdf_path: Path, text: str, references: list[tuple[int | None, str]], *, engine: dict,
                  pages: list[dict], seconds: float, heavy_seconds: float = 0.0, pdf_sha: str | None = None) -> None:
    """The map of ``<stem>.md`` that lets a reader fetch one piece of it.

    Offsets are character offsets into the final Markdown. Page ranges come
    from the page markers; headings, equations and figures carry the page
    they sit on. References are kept here, by page, even when the Markdown
    drops them.
    """
    import pdf_pipeline as pp

    markers = [(int(m.group(1)), m.start(), m.end()) for m in pp.PAGE_MARKER.finditer(text)]

    def page_at(offset: int) -> int | None:
        current = None
        for number, start, _end in markers:
            if start > offset:
                break
            current = number
        return current

    by_page = {row["page"]: row for row in pages}
    page_rows = []
    for index, (number, _start, end) in enumerate(markers):
        stop = markers[index + 1][1] if index + 1 < len(markers) else len(text)
        page_rows.append(dict(by_page.get(number, {"page": number}), md_start=end, md_end=stop))
    headings = [{"level": len(m.group(0)) - len(m.group(0).lstrip("#")), "text": m.group(1).strip(),
                 "md_offset": m.start(), "page": page_at(m.start())}
                for m in _HEADING_LINE.finditer(text)]
    equations = [{"index": i, "latex": m.group(1).strip(), "md_offset": m.start(), "page": page_at(m.start())}
                 for i, m in enumerate(_DISPLAY_MATH.finditer(text))]
    figures = [{"file": m.group(1), "md_offset": m.start(), "page": page_at(m.start())}
               for m in re.finditer(r"!\[[^\]]*\]\(([^)\s]+)\)", text)]
    reference_rows = []
    for page, block in references:
        for line in block.splitlines():
            marker = pp.PAGE_MARKER.match(line.strip())
            if marker:
                page = int(marker.group(1))
                continue
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            # The fast path joins a bibliography into one paragraph and Docling
            # bullets it; one row per entry either way.
            for part in _REFERENCE_START.split(entry):
                part = part.strip().lstrip("-").strip()  # a Docling bullet, alone or before its entry
                if part:
                    reference_rows.append({"text": part, "page": page})
    sidecar = {
        "schema": "papersmith.ingestion/v1",
        "source": {"file": pdf_path.name, "sha256": pdf_sha or _sha256_of(pdf_path), "pages": len(pages) or None},
        "markdown": {"file": f"{pdf_path.stem}.md", "chars": len(text)},
        "engine": engine,
        "pages": page_rows,
        "headings": headings,
        "equations": equations,
        "figures": figures,
        "references": reference_rows,
        "timing": {"seconds": round(seconds, 2), "heavy_seconds": round(heavy_seconds, 2)},
    }
    path.write_text(json.dumps(sidecar, indent=1, ensure_ascii=False), encoding="utf-8")


def _sha256_of(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_engine(engine: str, mode: str | None, force_ocr: bool, cache_root: Path | None,
                 formulas_on_cpu: bool = False):
    """The converter for one run: Marker's, or the page-routed engine."""
    if engine == "marker":
        print(f"NOTE {MARKER_LICENSE_NOTE}", file=sys.stderr)
        return build_converter(mode, force_ocr)
    try:
        import pypdfium2  # noqa: F401 -- the fast path is the core and always required
    except ImportError as exc:
        raise EngineError(f"pypdfium2 is not available in this interpreter ({exc}); "
                          f"provision the environment with {SETUP_SCRIPT}") from None
    return RoutedEngine(engine, mode, force_ocr, cache_root, formulas_on_cpu)


def ingest_loose(converter, loose_pdf: Path, strip_refs: bool) -> Path:
    """Ingest one loose PDF into its own folder, transactionally.

    Conversion happens in a staging directory beside the paper; only when the
    Markdown and figures exist is the destination folder populated and the PDF
    moved in. Any failure leaves the PDF loose and the source root clean, so the
    next run retries the paper instead of skipping it as "already ingested".
    """
    folder = loose_pdf.parent / loose_pdf.stem
    if folder.exists():
        if not folder.is_dir():
            raise IngestionError(f"{folder.name} already exists and is not a folder")
        if any(folder.iterdir()):
            raise IngestionError(
                f"{folder.name}/ already exists and is not empty; "
                "delete that folder to re-ingest this paper"
            )

    # Only a folder this run created may be rolled back; one the operator had
    # already put there is never deleted on our behalf.
    pre_existing = folder.exists()
    staging = Path(tempfile.mkdtemp(prefix=f".{loose_pdf.stem}-ingest-", dir=loose_pdf.parent))
    try:
        render_paper(converter, loose_pdf, strip_refs, staging)
        folder.mkdir(exist_ok=True)
        for produced in sorted(staging.iterdir()):
            shutil.move(str(produced), str(folder / produced.name))
        # The PDF moves last: until it does, the paper is still loose and a
        # retry is a plain re-run.
        shutil.move(str(loose_pdf), str(folder / loose_pdf.name))
    except Exception:
        if not pre_existing:
            shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return folder / f"{loose_pdf.stem}.md"


#: WHY THIS SKILL WAS INVOKED, AND WHERE IT HAS TO ARRIVE.
#:
#: Declared, invariant, and independent of what is on disk. A listing of what
#: has been ingested answers *where am I*; this answers *what is this for*,
#: which no listing implies. A session that hits an error, an interruption or a
#: gap consults it, locates itself, resolves what blocks, and rejoins.
#:
#: **Arrival is an artefact somebody can read and cite, never a PDF that was
#: processed.** The distinction is this skill's whole reason to exist: a PDF is
#: already on disk and already unusable as evidence -- its equations are
#: pictures, its tables are ink, and nothing downstream can quote it. What is
#: being produced is the form in which the paper can be read, argued with and
#: cited.
OBJECTIVE_FLOW = {
    "purpose": (
        "turn a paper into the form it can actually be used in -- equations as "
        "LaTeX, tables as tables, figures as files -- not a PDF that was "
        "processed"),
    "stages": [
        {"stage": "filed",
         "establishes": "the PDF sits inside a topic folder of its own, which "
                        "is what makes it a paper rather than a download",
         "behindWhen": "it is no longer reported among the unfiled"},
        {"stage": "extracted",
         "establishes": "the Markdown exists beside it, with its figures "
                        "written as files rather than left inside the page",
         "behindWhen": "the paper folder holds the document and its images"},
        {"stage": "readable",
         "establishes": "the equations are LaTeX and the tables are Markdown, "
                        "so a later reader can quote a formula rather than "
                        "describe a picture of one",
         "behindWhen": "this is the arrival; it is behind nobody"},
    ],
    "arrival": (
        "a document a person can read and a later session can cite, which a "
        "PDF is not"),
    # Nothing here is a person's decision: ingestion asks nobody. Said
    # explicitly and left empty rather than omitted, so a reader learns the
    # answer is none rather than meeting a missing key and guessing.
    "humanStops": [],
}


def main() -> int:
    # Keep the usage line on one screen row: the skill-audit probe derives
    # its closed flag roster from this single line, and a wrapped usage would
    # bury a flag behind a newline the roster's own split cannot see.
    os.environ.setdefault("COLUMNS", "240")
    parser = argparse.ArgumentParser(description="Per-paper-folder PDF -> Markdown ingestion (page-routed).")
    parser.add_argument(
        "pdf", nargs="*", help="the loose PDFs to ingest (default: every loose PDF found)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="report the pending loose PDFs and exit, without loading any model or moving any file",
    )
    parser.add_argument(
        "--file", metavar="PDF",
        help="file one unfiled PDF sitting in the base into a topic folder; ingests nothing",
    )
    parser.add_argument(
        "--into", metavar="TOPIC",
        help="the topic folder --file moves into, created when it does not exist yet",
    )
    parser.add_argument(
        "--mode", choices=VALID_MODES, default=None,
        help="override papersmith.yaml's conversion mode for this run",
    )
    parser.add_argument(
        "--force-ocr", action="store_true",
        help="OCR every page instead of reading the PDF's text layer (for a poor text layer that garbles tables)",
    )
    parser.add_argument(
        "--engine", choices=VALID_ENGINES, default=None,
        help="override papersmith.yaml's engine for this run (auto routes each page)",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="convert every page again and do not store the result in the page cache",
    )
    parser.add_argument(
        "--verify-cache", action="store_true",
        help="re-check every cached page against its recorded hashes and exit; ingests nothing",
    )
    args = parser.parse_args()

    if bool(args.file) != bool(args.into):
        print("Usage error: --file and --into are given together.", file=sys.stderr)
        return 2

    try:
        cfg = load_config()
        mode = args.mode if args.mode is not None else cfg.get("mode")  # None -> Marker auto-selects by device
        engine = args.engine or cfg.get("engine") or DEFAULT_ENGINE
        use_cache = not args.no_cache and cfg.get("cache", True)
        if args.verify_cache:
            import pdf_pipeline

            checked, bad = pdf_pipeline.PageCache(REPO_ROOT / CACHE_DIR).verify()
            print(f"Page cache: {checked} entr{'y' if checked == 1 else 'ies'} checked, {len(bad)} failing.")
            for folder in bad:
                print(f"  FAILING {_relative(folder)}")
            return 1 if bad else 0
        strip_refs = bool(cfg.get("strip_references", True))
        force_ocr = bool(args.force_ocr or cfg.get("force_ocr", False))
        # Filing is not ingestion: it moves one PDF into a topic and loads no model,
        # so it answers and exits before anything here can displace anything else.
        if args.file:
            landed = file_into(Path(args.file).resolve(), args.into, cfg)
            print(f"Filed into {_relative(landed.parent)}: {landed.name}")
            print("Run the ingestion to convert it.")
            return 0
        if args.pdf:
            # Dedupe while keeping the caller's order: the same PDF named twice
            # would move on the first pass and then "fail" on the second.
            targets = list(dict.fromkeys(resolve_single_target(raw) for raw in args.pdf))
            unfiled: list[Path] = []
        else:
            targets = find_loose_pdfs(discover_source_roots(cfg))
            unfiled = unfiled_pdfs(cfg)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        # The north, on the one path a refusal reaches a reader. A blocked
        # session is exactly the one that has lost the purpose, and this is
        # the cheapest place to hand it back.
        print(json.dumps({"objective": OBJECTIVE_FLOW}, indent=2), file=sys.stderr)
        return 2

    if not targets:
        # Never "every paper is already in its folder" while PDFs sit unfiled in the
        # base. That sentence is what makes them invisible, and it is the reason this
        # branch reports them instead of reporting success.
        if unfiled:
            print("Nothing to ingest: no loose PDF sits inside a topic folder.")
            print_unfiled(unfiled, filing_options(cfg))
            return 0
        print("Nothing to ingest: no loose PDFs found (every paper is already in its folder).")
        return 0

    # Discovery is free; ingestion moves files. Reporting happens before the
    # engine loads so the skill can ask which papers to ingest at no cost.
    if args.list:
        print_listing(targets)
        if unfiled:
            print_unfiled(unfiled, filing_options(cfg))
        return 0

    try:
        converter = build_engine(engine, mode, force_ocr, REPO_ROOT / CACHE_DIR if use_cache else None,
                                 bool(cfg.get("formulas_on_cpu", False)))
    except EngineError as exc:
        print(f"Environment error: {exc}", file=sys.stderr)
        return 2

    done: list[str] = []
    failed = 0
    for loose_pdf in targets:
        try:
            md_path = ingest_loose(converter, loose_pdf, strip_refs)
            done.append(md_path.parent.name)
        except Exception as exc:  # keep going; report the failure for this file only
            failed += 1
            print(f"FAILED {loose_pdf.name}: {exc}", file=sys.stderr)

    if done:
        print(f"Ingested {len(done)}: " + ", ".join(done))
    # Last, and on purpose: a successful run is exactly when a pending PDF nobody
    # filed is easiest to read as nothing left to do.
    if unfiled:
        print_unfiled(unfiled, filing_options(cfg))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
