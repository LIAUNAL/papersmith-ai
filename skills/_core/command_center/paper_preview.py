"""Read-only paper preview for the command center.

Two jobs, both strictly read-only:

* :func:`build_preview` turns ``sections/*.md`` contracts plus the
  ``%% paper-writing block`` regions of ``paper/main.tex`` into a plain-text
  preview payload.
* :func:`resolve_artifact` maps a public artifact name to a real file under
  ``paper/`` (``main.pdf`` and ``figures/<id>.pdf|png``) or says why not.
  :func:`resolve_venue_pdf` does the same for ``paper/venues/<slug>/main.pdf``.

Every read goes through :func:`bounded_read`: the path is resolved and must stay
inside the workspace, must be a regular file, and its size is checked BEFORE any
byte is read. The extractor's unbounded ``_read_text`` is deliberately not used.

Figure id rule (stricter than ``paper_figure.py`` which only rejects empty ids,
``/``, ``\\``, NUL, ``.`` and ``..``): one path segment made of ``[A-Za-z0-9._-]``,
no leading dot, at most 100 characters. The public ``figures/`` prefix maps to
the real directory ``paper/Figures/`` (capital F).
"""

from __future__ import annotations

import re
import stat
import os
from pathlib import Path
from typing import Any

from . import state_extractor as _ex

MAIN_TEX_MAX_BYTES = 2 * 1024 * 1024
SECTION_MAX_BYTES = 256 * 1024
BIB_MAX_BYTES = 1024 * 1024
VERDICT_MAX_BYTES = 256 * 1024
FILE_MAX_BYTES = 100 * 1024 * 1024
TOTAL_TEXT_MAX_BYTES = 200 * 1024
BLOCK_TEXT_MAX_BYTES = 32 * 1024
MAX_SECTION_FILES = 100
MAX_FIGURES = 200
FIGURE_ID_MAX = 100
NAME_MAX = 200

CAPS = {
    "main_tex_bytes": MAIN_TEX_MAX_BYTES,
    "section_bytes": SECTION_MAX_BYTES,
    "total_text_bytes": TOTAL_TEXT_MAX_BYTES,
    "block_text_bytes": BLOCK_TEXT_MAX_BYTES,
    "file_bytes": FILE_MAX_BYTES,
}

_NAME_RE = re.compile(r"^[A-Za-z0-9._/-]{1,%d}$" % NAME_MAX)
_FIGURE_ID_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,%d}$" % (FIGURE_ID_MAX - 1))
_REGION_BEGIN_RE = re.compile(r"^%% paper-writing (declarations|provenance) begin\b")
_REGION_END_RE = re.compile(r"^%% paper-writing (declarations|provenance) end\s*$")
_CONTENT_TYPES = {"pdf": "application/pdf", "png": "image/png"}
#: A venue slug, as ``paper_venue.SLUG_RE`` defines it.
VENUE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


# --------------------------------------------------------------------------
# bounded, containment-checked reads
# --------------------------------------------------------------------------
def _contained(root: Path, path: Path) -> Path | None:
    """The resolved ``path`` when it is a regular file inside ``root``."""
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        if not stat.S_ISREG(resolved.stat().st_mode):
            return None
    except (OSError, ValueError, RuntimeError):
        return None
    return resolved


def bounded_read(root: Path, path: Path, cap: int) -> tuple[str, str | None]:
    """Read ``path`` as text under a size cap.

    Returns ``(status, text)``; ``status`` is one of ``ok``, ``absent``,
    ``too_large``, ``unsafe`` (resolves outside ``root``) or ``unreadable``
    (not a regular file, or an OS error). ``text`` is ``None`` unless ``ok``.
    """
    root = root.resolve()
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return "absent", None
    except (OSError, RuntimeError):
        return "unreadable", None
    try:
        resolved.relative_to(root)
    except ValueError:
        return "unsafe", None
    try:
        info = resolved.stat()
        if not stat.S_ISREG(info.st_mode):
            return "unreadable", None
        if info.st_size > cap:
            return "too_large", None
        with open(resolved, "rb") as handle:
            data = handle.read(cap + 1)
    except OSError:
        return "unreadable", None
    if len(data) > cap:
        return "too_large", None
    return "ok", data.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# main.tex blocks
# --------------------------------------------------------------------------
def parse_blocks(text: str) -> dict[str, dict[str, Any]]:
    """Map block ids to ``{body, duplicate}`` (first definition wins).

    Same grammar as the extractor (an unterminated block contributes nothing; a
    nested ``begin`` is block content) but declarations and provenance regions
    are skipped and a repeated id is flagged instead of overwritten.
    """
    blocks: dict[str, dict[str, Any]] = {}
    open_id: str | None = None
    buffer: list[str] = []
    in_region = False
    for line in text.splitlines():
        if open_id is None:
            if in_region:
                in_region = _REGION_END_RE.match(line) is None
                continue
            if _REGION_BEGIN_RE.match(line):
                in_region = True
                continue
        begin = _ex._BEGIN_RE.match(line)
        if begin is not None and open_id is None:
            open_id = begin.group("id")
            buffer = []
            continue
        end = _ex._END_RE.match(line)
        if end is not None and open_id is not None and end.group("id") == open_id:
            if open_id in blocks:
                blocks[open_id]["duplicate"] = True
            else:
                blocks[open_id] = {"body": "\n".join(buffer), "duplicate": False}
            open_id = None
            buffer = []
            continue
        if open_id is not None:
            buffer.append(line)
    return blocks


def _cite_keys(body: str) -> list[str]:
    keys: list[str] = []
    for match in _ex._CITE_RE.finditer(body):
        for key in (part.strip() for part in match.group("keys").split(",")):
            if key and key not in keys:
                keys.append(key)
    return keys


def _clip(text: str, limit: int) -> tuple[str, bool]:
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text, False
    return data[:limit].decode("utf-8", errors="ignore"), True


# --------------------------------------------------------------------------
# preview payload
# --------------------------------------------------------------------------
def _section_paths(root: Path) -> tuple[list[Path], dict[str, Any]]:
    """The section files to preview plus ``{"status", "truncated"}`` for the directory.

    ``sections/`` itself must resolve inside the workspace; a symlink pointing
    outside is ``unsafe`` and is never listed (so no outside file name becomes a
    section id). Canonical sections are always resolved by name; only the extra
    (non-canonical) ones are capped at ``MAX_SECTION_FILES``, and the cap is
    reported as ``truncated`` instead of making later sections look absent.
    """
    sections_dir = root / "sections"
    canonical = set(_ex.SECTION_ORDER)
    by_name: dict[str, Path] = {}
    extras: list[Path] = []
    status, truncated = "absent", False
    try:
        resolved_dir = sections_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        resolved_dir = None
    if resolved_dir is not None:
        try:
            resolved_dir.relative_to(root.resolve())
        except ValueError:
            status = "unsafe"
        else:
            if not resolved_dir.is_dir():
                status = "unreadable"
            else:
                status = "ok"
                for path in sorted(sections_dir.glob("*.md")):
                    if path.stem in canonical:
                        by_name[path.stem] = path
                    elif len(extras) < MAX_SECTION_FILES:
                        extras.append(path)
                    else:
                        truncated = True
    paths = [by_name.get(name, sections_dir / f"{name}.md") for name in _ex.SECTION_ORDER]
    paths.extend(extras)
    return paths, {"status": status, "truncated": truncated}


def _pdf_info(root: Path, tex_mtime: float | None) -> dict[str, Any]:
    paper = (root / "paper")
    main = None
    resolved = _contained(root.resolve(), paper / "main.pdf")
    if resolved is not None:
        info = resolved.stat()
        stale = tex_mtime is not None and tex_mtime > info.st_mtime
        main = {"present": True, "size": info.st_size, "stale": stale,
                "mtime": info.st_mtime_ns // 1_000_000}
    figures: list[dict[str, Any]] = []
    figures_dir = paper / "Figures"
    try:
        entries = sorted(figures_dir.iterdir()) if figures_dir.is_dir() else []
    except OSError:
        entries = []
    for entry in entries:
        kind = entry.suffix[1:].lower() if entry.suffix else ""
        if kind not in _CONTENT_TYPES or entry.suffix != f".{kind}":
            continue
        if _FIGURE_ID_RE.match(entry.stem) is None:
            continue
        real = _contained(root.resolve(), entry)
        if real is None:
            continue
        info = real.stat()
        figures.append({"id": entry.stem, "kind": kind, "size": info.st_size,
                        "mtime": info.st_mtime_ns // 1_000_000})
        if len(figures) >= MAX_FIGURES:
            break
    return {"main": main, "figures": figures}


def build_preview(root: Path | str) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    paper = root / "paper"
    tex_status, tex_text = bounded_read(root, paper / "main.tex", MAIN_TEX_MAX_BYTES)
    drafted = parse_blocks(tex_text) if tex_text is not None else {}
    draft = {
        block_id: {"body": value["body"], "words": _ex._word_count(value["body"]),
                   "has_body": bool(value["body"].strip())}
        for block_id, value in drafted.items()
    }
    bib_status, bib_text = bounded_read(root, paper / "refs.bib", BIB_MAX_BYTES)
    bib = {m.group("key") for m in _ex._BIB_KEY_RE.finditer(bib_text)} if bib_text else set()
    verdict_status, _ = bounded_read(root, paper / "verdict.json", VERDICT_MAX_BYTES)
    sealed = verdict_status == "ok"

    truncated = False
    budget = TOTAL_TEXT_MAX_BYTES
    sections: list[dict[str, Any]] = []
    section_paths, sections_dir = _section_paths(root)
    for path in section_paths:
        _, text = bounded_read(root, path, SECTION_MAX_BYTES)
        meta, _body = _ex._split_frontmatter(text or "")
        contract_blocks = _ex._blocks_of(meta)
        section_name = meta.get("section") if isinstance(meta, dict) else None
        section_name = section_name if isinstance(section_name, str) else path.stem
        own = {
            block_id: value for block_id, value in draft.items()
            if block_id.startswith(f"{section_name}.") or block_id == section_name
        }
        placeholders = sum(_ex._citation_signals(v["body"], bib)[1] for v in own.values())
        status = _ex._section_status(meta, contract_blocks, draft, placeholders, sealed)
        title = meta.get("title") if isinstance(meta, dict) else None
        position = meta.get("position") if isinstance(meta, dict) else None
        out_blocks: list[dict[str, Any]] = []
        for block in contract_blocks:
            block_id = str(block.get("id"))
            value = draft.get(block_id)
            written = bool(value and value["has_body"])
            entry: dict[str, Any] = {
                "id": block_id, "written": written, "text": None, "words": 0,
                "citations": [], "truncated": False,
                "duplicate": bool(drafted.get(block_id, {}).get("duplicate")),
            }
            if written:
                body = value["body"]
                entry["words"] = value["words"]
                entry["citations"] = _cite_keys(body)
                if budget <= 0:
                    entry["truncated"] = True
                else:
                    clipped, cut = _clip(body, min(BLOCK_TEXT_MAX_BYTES, budget))
                    entry["text"] = clipped
                    entry["truncated"] = cut
                    budget -= len(clipped.encode("utf-8"))
                truncated = truncated or entry["truncated"]
            out_blocks.append(entry)
        sections.append({
            "id": path.stem,
            "title": title if isinstance(title, str) else None,
            "position": position,
            "status": status,
            "blocks": out_blocks,
        })

    tex_mtime = None
    tex_real = _contained(root, paper / "main.tex")
    if tex_real is not None:
        tex_mtime = tex_real.stat().st_mtime
    return {
        "sections": sections,
        "truncated": truncated,
        "caps": dict(CAPS),
        "sections_dir": sections_dir,
        "main_tex": {"status": tex_status},
        "pdf": _pdf_info(root, tex_mtime),
    }


# --------------------------------------------------------------------------
# whitelisted artifacts
# --------------------------------------------------------------------------
def _exact_case(base: Path, target: Path) -> bool:
    """Whether every component of ``target`` below ``base`` is spelled exactly
    as its directory lists it. A case-insensitive file system (macOS, Windows)
    would otherwise serve ``figures/ARCH.pdf`` for ``arch.pdf``, so the public
    name space would depend on the machine instead of on the bytes."""
    try:
        relative = target.relative_to(base.parent) if target.is_absolute() else target
    except ValueError:
        return False
    current = base.parent
    for part in relative.parts:
        try:
            if part not in os.listdir(current):
                return False
        except OSError:
            return False
        current = current / part
    return True


def resolve_artifact(root: Path | str, name: str) -> tuple[str, Path | None, str | None]:
    """Resolve a public artifact ``name`` to ``(status, path, content_type)``.

    ``status`` is ``ok``, ``bad`` (malformed name, HTTP 400), ``absent``
    (well-formed but not served or not present, HTTP 404) or ``too_large``
    (HTTP 413). Only ``main.pdf`` and ``figures/<id>.pdf|png`` are served.
    """
    if not isinstance(name, str) or _NAME_RE.match(name) is None:
        return "bad", None, None
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts) or len(parts) > 2:
        return "bad", None, None
    root = Path(root).expanduser().resolve()
    paper = root / "paper"
    if len(parts) == 1:
        if name != "main.pdf":
            return "absent", None, None
        target, kind = paper / "main.pdf", "pdf"
    else:
        if parts[0] != "figures":
            return "absent", None, None
        stem, dot, ext = parts[1].rpartition(".")
        if not dot or ext not in _CONTENT_TYPES or _FIGURE_ID_RE.match(stem) is None:
            return "absent", None, None
        target, kind = paper / "Figures" / f"{stem}.{ext}", ext
    try:
        base = paper.resolve(strict=True)
        base.relative_to(root)
    except (OSError, ValueError, RuntimeError):
        return "absent", None, None
    resolved = _contained(base, target)
    if resolved is None or not _exact_case(base, target):
        return "absent", None, None
    try:
        if resolved.stat().st_size > FILE_MAX_BYTES:
            return "too_large", None, None
    except OSError:
        return "absent", None, None
    return "ok", resolved, _CONTENT_TYPES[kind]


def read_artifact(path: Path) -> bytes | None:
    """Read a resolved artifact, re-checking the cap; ``None`` when it grew."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(FILE_MAX_BYTES + 1)
    except OSError:
        return None
    return None if len(data) > FILE_MAX_BYTES else data


def venue_directory(root: Path | str, slug: str) -> Path | None:
    """The real directory of venue ``slug``, or ``None``.

    ``None`` for a malformed slug, a missing venue, or a venue directory that
    resolves anywhere but directly under ``paper/venues/`` inside the
    workspace (a symlink out is not followed).
    """
    if not isinstance(slug, str) or VENUE_SLUG_RE.match(slug) is None:
        return None
    root = Path(root).expanduser().resolve()
    try:
        base = (root / "paper" / "venues").resolve(strict=True)
        base.relative_to(root)
        real = (base / slug).resolve(strict=True)
    except (OSError, ValueError, RuntimeError):
        return None
    if real.parent != base or not real.is_dir():
        return None
    return real


def resolve_venue_pdf(root: Path | str, slug: str) -> tuple[str, Path | None]:
    """Resolve ``paper/venues/<slug>/main.pdf`` to ``(status, path)``.

    ``status`` is ``ok``, ``bad`` (malformed slug, HTTP 400), ``absent``
    (HTTP 404) or ``too_large`` (HTTP 413). The file must resolve inside the
    venue's own directory.
    """
    if not isinstance(slug, str) or VENUE_SLUG_RE.match(slug) is None:
        return "bad", None
    directory = venue_directory(root, slug)
    if directory is None:
        return "absent", None
    resolved = _contained(directory, directory / "main.pdf")
    if resolved is None:
        return "absent", None
    try:
        if resolved.stat().st_size > FILE_MAX_BYTES:
            return "too_large", None
    except OSError:
        return "absent", None
    return "ok", resolved


def read_capped_bytes(root: Path | str, path: Path, cap: int) -> tuple[str, bytes | None]:
    """Like :func:`bounded_read` but returns the raw bytes, so a hash taken
    from them is the hash of the file on disk."""
    root = Path(root).expanduser().resolve()
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return "absent", None
    except (OSError, RuntimeError):
        return "unreadable", None
    try:
        resolved.relative_to(root)
    except ValueError:
        return "unsafe", None
    try:
        info = resolved.stat()
        if not stat.S_ISREG(info.st_mode):
            return "unreadable", None
        if info.st_size > cap:
            return "too_large", None
        with open(resolved, "rb") as handle:
            data = handle.read(cap + 1)
    except OSError:
        return "unreadable", None
    if len(data) > cap:
        return "too_large", None
    return "ok", data
