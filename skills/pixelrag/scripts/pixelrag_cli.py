#!/usr/bin/env python3
"""pixelrag: turn a figure `paper-ingestion` extracted into a description usable as evidence.

Keyless and local, like `paper-ingestion`: no model is called and nothing leaves
the machine. The description is written by the session's own agent, which can
look at the image; this CLI makes that description evidence by binding it to
deterministic facts about the image, refusing what contradicts them, and storing
it with provenance.

    python pixelrag_cli.py facts  --figure <image under an ingested paper>
    python pixelrag_cli.py record --figure <image> --sha256 <hex from facts>
                                  --description <text | @file> [--markdown]
    python pixelrag_cli.py status --paper <ingested paper folder>

Stdlib only. One JSON object on stdout per call. Refusals answer
`{"ok": false, "error": CODE, "message": ...}` with exit code 2.
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
import datetime as dt
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

TOOL = "pixelrag"
SIDECAR_SUFFIX = ".pixelrag.json"
IMAGE_SUFFIXES = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".gif": "gif", ".webp": "webp"}
MIN_DESCRIPTION = 40
MAX_DESCRIPTION = 4000
NEARBY_CHARS = 600

_PAGE_MARKER = re.compile(r"^<!-- page (\d+) -->$", re.MULTILINE)
_IMAGE_REF = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
_CAPTION = re.compile(r"^\s*(?:\*\*|__|\*|_)?\s*(fig(?:ure)?\.?)\s*(\d+)([a-z]?)\b", re.IGNORECASE)
_MENTION = re.compile(r"\bfig(?:ure)?\.?\s*(\d+)", re.IGNORECASE)
_SPECULATION = re.compile(
    r"\b(probably|presumably|perhaps|maybe|possibly|apparently|likely|seems?|seemingly|might|"
    r"suggests?|suggesting|implies|i think|we believe)\b", re.IGNORECASE)
_MARKUP = ("<!--", "-->", "![")
_BLOCK_BEGIN = "<!-- pixelrag:begin {name} sha256={sha} -->"
_BLOCK_END = "<!-- pixelrag:end {name} -->"
OCR_NOTE = ("pixelrag runs no OCR: text drawn inside the image (axis labels, legends, panel letters) is "
            "read by the agent looking at the image, never by this tool")


class Refused(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # one JSON object on stdout, even for a usage error
        raise Refused("USAGE", f"{message}; usage: {self.format_usage().strip()}")


# -- reading the image --------------------------------------------------------

def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _pixel_size(data: bytes, fmt: str) -> tuple[int, int] | None:
    """Width and height from the file header, or None when the header is not one this reads."""
    if fmt == "png" and data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    if fmt == "gif" and data[:4] == b"GIF8" and len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    if fmt == "jpeg" and data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                height, width = struct.unpack(">HH", data[i + 5:i + 9])
                return width, height
            i += 2 + length
    return None


def _image(figure: str) -> Path:
    path = Path(figure).expanduser()
    if not path.is_file():
        raise Refused("FIGURE_NOT_FOUND", f"{figure} is not a file")
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        raise Refused("NOT_AN_IMAGE", f"{figure} is not an image ({', '.join(sorted(IMAGE_SUFFIXES))})")
    return path.resolve()


# -- reading the ingested paper -----------------------------------------------

def _strip_blocks(markdown: str) -> str:
    """The Markdown without pixelrag's own blocks, so facts never read a description as the paper's text."""
    return re.sub(r"\n<!-- pixelrag:begin .*? -->\n.*?\n<!-- pixelrag:end .*? -->\n", "", markdown, flags=re.DOTALL)


def _markdown_for(image: Path) -> Path:
    folder = image.parent
    candidates = [md for md in sorted(folder.glob("*.md"))
                  if image.name in _IMAGE_REF.findall(md.read_text(encoding="utf-8"))]
    if not candidates:
        raise Refused("NOT_INGESTED", f"no ingested Markdown in {_display(folder)} references {image.name}; "
                                      "run /paper-ingestion on the paper first")
    named = folder / f"{folder.name}.md"
    return named if named in candidates else candidates[0]


def _page_map(markdown_path: Path) -> dict | None:
    path = markdown_path.with_suffix(".json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("schema") == "papersmith.ingestion/v1" else None


def _paragraphs(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def _is_body(paragraph: str) -> bool:
    return not (paragraph.startswith("#") or _PAGE_MARKER.match(paragraph) or _IMAGE_REF.search(paragraph)
                or _CAPTION.match(paragraph))


def _clip(text: str | None) -> str | None:
    if text is None:
        return None
    text = " ".join(text.split())
    return text if len(text) <= NEARBY_CHARS else text[:NEARBY_CHARS].rstrip() + " [...]"


def facts_for(image: Path) -> dict:
    markdown_path = _markdown_for(image)
    markdown = _strip_blocks(markdown_path.read_text(encoding="utf-8"))
    ref = next(m for m in _IMAGE_REF.finditer(markdown) if m.group(1) == image.name)

    markers = list(_PAGE_MARKER.finditer(markdown))
    before_markers = [m for m in markers if m.start() <= ref.start()]
    page = int(before_markers[-1].group(1)) if before_markers else None
    page_start = before_markers[-1].end() if before_markers else 0
    later = [m for m in markers if m.start() > ref.start()]
    page_end = later[0].start() if later else len(markdown)

    # The page's paragraphs, the one holding the image, and the caption beside it.
    head = _paragraphs(markdown[page_start:ref.start()])
    holder_rest = markdown[ref.end():page_end]
    tail = _paragraphs(holder_rest)
    caption = None
    candidates = tail[:2] + list(reversed(head[-2:]))
    for paragraph in candidates:
        if _CAPTION.match(paragraph):
            caption = " ".join(paragraph.split())
            break
    if caption is None:
        alt = re.match(r"!\[([^\]]*)\]", ref.group(0)).group(1)
        if _CAPTION.match(alt):
            caption = " ".join(alt.split())
    match = _CAPTION.match(caption) if caption else None
    number = (match.group(2) + match.group(3)) if match else None

    before = next((p for p in reversed(head) if _is_body(p)), None)
    after = next((p for p in tail if _is_body(p)), None)
    page_text = _IMAGE_REF.sub("", markdown[page_start:page_end])
    available = bool(re.search(r"\w", page_text))
    row = {}
    page_map = _page_map(markdown_path)
    if page_map:
        row = next((r for r in page_map.get("pages", []) if r.get("page") == page), {})
    data = image.read_bytes()
    fmt = IMAGE_SUFFIXES[image.suffix.lower()]
    size = _pixel_size(data, fmt)
    return {
        "path": _display(image),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "format": fmt,
        "width": size[0] if size else None,
        "height": size[1] if size else None,
        "markdown": _display(markdown_path),
        "page": page,
        "label": f"Figure {number}" if number else None,
        "number": number,
        "caption": caption,
        "nearby_text": {"before": _clip(before), "after": _clip(after)},
        "text_layer": {
            "available": available,
            "page": page,
            "route": row.get("route"),
            "engine": row.get("engine"),
            "note": ("text ingestion extracted from the PDF page around the figure; it is the authors' text, "
                     "not text read from the image") if available else
                    (f"ingestion extracted no text for page {page}; the description rests on the image alone"),
        },
        "in_image_text": None,
        "in_image_text_note": OCR_NOTE,
    }


# -- the description ----------------------------------------------------------

def _read_description(value: str) -> str:
    if value.startswith("@"):
        try:
            value = Path(value[1:]).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise Refused("DESCRIPTION_UNREADABLE", f"cannot read {value[1:]}: {exc}") from None
    return value.strip()


def validate_description(text: str, facts: dict) -> None:
    if not text:
        raise Refused("DESCRIPTION_EMPTY", "the description is empty; look at the image and write what it shows")
    if len(text) < MIN_DESCRIPTION:
        raise Refused("DESCRIPTION_TOO_SHORT", f"the description has {len(text)} characters; at least "
                                               f"{MIN_DESCRIPTION} are needed to say what the figure shows")
    if len(text) > MAX_DESCRIPTION:
        raise Refused("DESCRIPTION_TOO_LONG", f"the description has {len(text)} characters; at most "
                                              f"{MAX_DESCRIPTION} are kept")
    for token in _MARKUP:
        if token in text:
            raise Refused("DESCRIPTION_MARKUP", f"the description contains {token!r}, which would corrupt the "
                                                "ingested Markdown's page and figure markers")
    hedges = sorted({m.group(0).lower() for m in _SPECULATION.finditer(text)})
    if hedges:
        raise Refused("DESCRIPTION_SPECULATIVE", f"the description speculates ({', '.join(hedges)}); state only "
                                                 "what the image shows: axes, units, trends, panels")
    if facts["number"]:
        caption_number = re.match(r"\d+", facts["number"]).group(0)
        wrong = sorted({m.group(1) for m in _MENTION.finditer(text) if m.group(1) != caption_number})
        if wrong:
            raise Refused("FIGURE_NUMBER_MISMATCH", f"the description names figure {', '.join(wrong)} but the "
                                                    f"caption labels this image {facts['label']}")


# -- storage ------------------------------------------------------------------

def _sidecar(image: Path) -> Path:
    return image.with_name(image.name + SIDECAR_SUFFIX)


def _block_pattern(name: str) -> re.Pattern:
    return re.compile(r"\n<!-- pixelrag:begin " + re.escape(name) + r" sha256=([0-9a-f]+) -->\n.*?\n"
                      r"<!-- pixelrag:end " + re.escape(name) + r" -->\n", re.DOTALL)


def _shift_map(page_map_path: Path, at: int, delta: int, chars: int) -> None:
    """Keep the ingestion map's character offsets true after the Markdown grew or shrank at `at`."""
    try:
        data = json.loads(page_map_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict) or data.get("schema") != "papersmith.ingestion/v1":
        return
    for key in ("pages", "headings", "equations", "figures"):
        for row in data.get(key) or []:
            for field in ("md_start", "md_end", "md_offset"):
                if isinstance(row.get(field), int) and row[field] >= at:
                    row[field] += delta
    if isinstance(data.get("markdown"), dict):
        data["markdown"]["chars"] = chars
    page_map_path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def write_block(markdown_path: Path, image: Path, sha: str, description: str) -> str:
    """Insert or replace the marker-delimited block right under the image reference; idempotent."""
    markdown = markdown_path.read_text(encoding="utf-8")
    quoted = "\n".join("> " + line if line.strip() else ">" for line in description.splitlines())
    block = ("\n" + _BLOCK_BEGIN.format(name=image.name, sha=sha[:16]) + "\n"
             + f"> **Figure description** (pixelrag: written by the session agent from the image, "
               f"not the authors' text)\n>\n{quoted}\n"
             + _BLOCK_END.format(name=image.name) + "\n")
    existing = _block_pattern(image.name).search(markdown)
    if existing:
        if existing.group(0) == block:
            return "unchanged"
        start, end = existing.span()
    else:
        ref = next(m for m in _IMAGE_REF.finditer(markdown) if m.group(1) == image.name)
        line_end = markdown.find("\n", ref.end())
        if line_end == -1:
            markdown += "\n"
            line_end = len(markdown) - 1
        start = end = line_end + 1
    updated = markdown[:start] + block + markdown[end:]
    markdown_path.write_text(updated, encoding="utf-8")
    _shift_map(markdown_path.with_suffix(".json"), end, len(block) - (end - start), len(updated))
    return "written"


# -- verbs ---------------------------------------------------------------------

def cmd_facts(args: argparse.Namespace) -> dict:
    return {"ok": True, "facts": facts_for(_image(args.figure))}


def cmd_record(args: argparse.Namespace) -> dict:
    image = _image(args.figure)
    facts = facts_for(image)
    if facts["sha256"] != args.sha256.strip().lower():
        raise Refused("IMAGE_CHANGED", f"{facts['path']} changed since `facts` (sha256 {args.sha256[:16]}... "
                                       f"expected, {facts['sha256'][:16]}... on disk); run `facts` again and "
                                       "look at the image again")
    description = _read_description(args.description)
    validate_description(description, facts)
    sidecar = _sidecar(image)
    state = "written"
    try:
        previous = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None
    if isinstance(previous, dict) and previous.get("sha256") == facts["sha256"] \
            and previous.get("description") == description:
        state = "unchanged"
    else:
        record = {
            "image": image.name,
            "sha256": facts["sha256"],
            "facts": facts,
            "description": description,
            "recorded_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tool": TOOL,
        }
        sidecar.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown = "skipped"
    if args.markdown:
        markdown = write_block(_markdown_for(image), image, facts["sha256"], description)
    return {"ok": True, "image": facts["path"], "sidecar": state, "sidecar_path": _display(sidecar),
            "markdown": markdown}


def cmd_status(args: argparse.Namespace) -> dict:
    folder = Path(args.paper).expanduser()
    if not folder.is_dir():
        raise Refused("PAPER_NOT_FOUND", f"{args.paper} is not a folder")
    named = folder / f"{folder.name}.md"
    found = sorted(folder.glob("*.md"))
    markdown_path = named if named.is_file() else (found[0] if len(found) == 1 else None)
    if markdown_path is None:
        raise Refused("NOT_INGESTED", f"{args.paper} holds no ingested Markdown ({folder.name}.md)")
    markdown = markdown_path.read_text(encoding="utf-8")
    names = list(dict.fromkeys(_IMAGE_REF.findall(markdown)))
    rows, current, missing, stale, absent = [], [], [], [], []
    for name in names:
        image = folder / name
        if not image.is_file():
            absent.append(name)
            continue
        sha = hashlib.sha256(image.read_bytes()).hexdigest()
        try:
            stored = json.loads(_sidecar(image).read_text(encoding="utf-8"))
        except FileNotFoundError:
            stored = None
        except (OSError, ValueError):
            stored = {}
        if stored is None:
            state = "missing"
            missing.append(name)
        elif isinstance(stored, dict) and stored.get("sha256") == sha and stored.get("description"):
            state = "current"
            current.append(name)
        else:
            state = "stale"
            stale.append(name)
        block = _block_pattern(name).search(markdown)
        block_state = "absent" if block is None else ("current" if sha.startswith(block.group(1)) else "stale")
        rows.append({"image": name, "state": state, "sha256": sha, "markdown_block": block_state})
    return {"ok": True, "paper": _display(folder), "markdown": _display(markdown_path), "figures": rows,
            "current": current, "missing": missing, "stale": stale, "referenced_but_absent": absent}


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="pixelrag_cli.py", description=__doc__.splitlines()[0])
    verbs = parser.add_subparsers(dest="verb", required=True, parser_class=_Parser)
    facts = verbs.add_parser("facts", help="deterministic facts about an ingested figure")
    facts.add_argument("--figure", required=True)
    facts.set_defaults(func=cmd_facts)
    record = verbs.add_parser("record", help="validate and store the agent's description")
    record.add_argument("--figure", required=True)
    record.add_argument("--sha256", required=True, help="the sha256 `facts` reported for the image looked at")
    record.add_argument("--description", required=True, help="the text, or @file to read it from")
    record.add_argument("--markdown", action="store_true",
                        help="also write the marker-delimited block under the image reference in the Markdown")
    record.set_defaults(func=cmd_record)
    status = verbs.add_parser("status", help="which figures have a current, missing or stale description")
    status.add_argument("--paper", required=True)
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = args.func(args)
    except Refused as refusal:
        print(json.dumps({"ok": False, "error": refusal.code, "message": refusal.message}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
