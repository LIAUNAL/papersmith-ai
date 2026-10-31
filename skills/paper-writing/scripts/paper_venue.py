"""paper_venue: adapting the manuscript to a chosen journal, one venue at a
time, under `paper/venues/<slug>/`.

Nine verbs (`VERBS`), each returning one dict that `paper_cli.py` prints:

    select        venue.json         the journal, copied from
                                     `paper/journal-candidates.json` or given by hand
    requirements  requirements.json  what the author guidelines ask for, every
                                     requirement carrying its quote and url
    acquire       template.json      the document class: TeX Live by name, or a
                  (+ template/)      publisher template copied with its origin
    diff          audit.json         smith's section contracts and the written
                                     manuscript against the requirements
    plan          plan.md            the agent's adjustment plan; resets approval
    approve       approval.json      the operator's words, bound to the plan hash
    build         main.tex           the venue's own file; canonical blocks
                  (+ build.json)     transposed byte for byte, markers included
    status/list                      the state machine, read-only

The canonical `paper/main.tex` and `sections/` are inputs here, never outputs:
`build` copies each block's region verbatim (begin marker, digest, body, end
marker), so `paper_block.parse` reads the venue file with every digest still
valid. Text changes the plan calls for are not made here at all -- they go
through `write` (redactor -> contract-auditor -> `write --draft --audit`),
one block at a time, after `approve`.

Standard library only; the one subprocess seam (`kpsewhich`) lives in
`paper_latex.py`, the sole module this skill lets spawn a process.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_block  # noqa: E402
import paper_contract  # noqa: E402
import paper_latex  # noqa: E402
import paper_region  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

VERBS = ("select", "requirements", "acquire", "diff", "plan", "approve", "build", "status", "list")

#: A venue slug: lowercase, digits and hyphens, never leading with a hyphen.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

#: A downloaded publisher template is data, not code: bounded in bytes and in
#: member count before a single byte is extracted.
MAX_TEMPLATE_BYTES = 50 * 1024 * 1024
MAX_TEMPLATE_FILES = 500
TEMPLATE_SUFFIXES = (".cls", ".sty", ".bst", ".tex", ".zip")

#: The sections whose blocks feed the front matter and the back matter; every
#: other section a manuscript carries is "content" (body text).
FRONT_SECTIONS = ("title-and-keywords", "abstract")
BACK_SECTION = "back-matter"
TITLE_BLOCK = "title-and-keywords.title"
KEYWORDS_BLOCK = "title-and-keywords.keywords"

LIMIT_KEYS = (
    "abstract_words", "keywords", "title_words", "main_text_words",
    "pages", "figures", "tables", "references",
)
#: A limit the submission system itself enforces blocks; the rest is major.
BLOCKING_LIMITS = ("abstract_words", "keywords", "title_words")

_CLASS_SOURCES = ("texlive", "publisher-template", "generic")
_CLASS_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SECTION_ID_RE = re.compile(r"^(?:new:)?[a-z0-9][a-z0-9-]*$")
_DECLARATION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_ISSN_RE = re.compile(r"^\d{4}-?\d{3}[\dXx]$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_BST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


# =====================================================================
# paths, small I/O
# =====================================================================
def _clock() -> str:
    return paper_region.default_clock()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _atomic_write(path: Path, data: bytes) -> None:
    """Same-directory temp file, then `os.replace`: a crash leaves either the
    old file or the new one, never half of either."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _json_bytes(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _write_json(path: Path, obj) -> None:
    _atomic_write(path, _json_bytes(obj))


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _require_paper_dir(paper_dir: Path) -> None:
    if not paper_dir.exists():
        raise Refused("PAPER_ABSENT", f"{paper_dir} does not exist; run scaffold first")
    if not paper_dir.is_dir():
        raise Refused("PAPER_NOT_A_DIRECTORY", f"{paper_dir} exists and is not a directory")


def validate_slug(slug: str) -> None:
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise Refused(
            "VENUE_SLUG_INVALID",
            f"{slug!r} is not a venue slug: lowercase letters, digits and hyphens, "
            "starting with a letter or digit, at most 63 characters",
        )


def venue_dir(paper_dir: Path, slug: str) -> Path:
    return paper_dir / "venues" / slug


def _require_venue(paper_dir: Path, slug: str) -> Path:
    """Slug shape first, then the paper, then the venue itself."""
    validate_slug(slug)
    _require_paper_dir(paper_dir)
    directory = venue_dir(paper_dir, slug)
    if not (directory / "venue.json").is_file():
        raise Refused("VENUE_ABSENT", f"no venue {slug!r}; run `venue select` first")
    return directory


def _relative_to_repo(paper_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(paper_dir.parent))
    except ValueError:
        return str(path)


# =====================================================================
# select
# =====================================================================
def _openalex_key(value) -> str:
    return str(value or "").strip().rstrip("/").rsplit("/", 1)[-1].upper()


def _normalize_issn(raw: str) -> str:
    if not isinstance(raw, str) or not _ISSN_RE.match(raw.strip()):
        raise Refused("ISSN_INVALID", f"{raw!r} is not an ISSN (NNNN-NNNC)")
    compact = raw.strip().replace("-", "").upper()
    return compact[:4] + "-" + compact[4:]


def _issn_list(value) -> list:
    if isinstance(value, str):
        value = [value]
    out = []
    for item in value or []:
        if isinstance(item, str) and _ISSN_RE.match(item.strip()):
            out.append(_normalize_issn(item))
    return out


def select(
    paper_dir: Path, slug: str, *, candidate: str | None = None, journal: str | None = None,
    issn: str | None = None, clock=_clock,
) -> dict:
    validate_slug(slug)
    _require_paper_dir(paper_dir)
    target = venue_dir(paper_dir, slug)
    if (target / "venue.json").exists():
        raise Refused("VENUE_EXISTS", f"venue {slug!r} is already selected")

    manual = journal is not None or issn is not None
    if candidate is not None and manual:
        raise Refused(
            "SELECT_MODE_CONFLICT",
            "--candidate and --journal/--issn were given together; choose one",
        )
    if candidate is None and not (journal is not None and issn is not None):
        raise Refused(
            "SELECT_MODE_REQUIRED",
            "--candidate <openalex source id>, or --journal <name> together with --issn <issn>, is required",
        )

    if candidate is not None:
        candidates_path = paper_dir / "journal-candidates.json"
        if not candidates_path.is_file():
            raise Refused(
                "CANDIDATES_ABSENT",
                f"{candidates_path} does not exist; run /journal-finder first",
            )
        try:
            candidates = _read_json(candidates_path).get("candidates", [])
            if not isinstance(candidates, list):
                raise ValueError("candidates is not a list")
        except (OSError, ValueError, AttributeError) as exc:
            raise Refused("CANDIDATES_ABSENT", f"{candidates_path} is unreadable: {exc}")
        wanted = _openalex_key(candidate)
        match = None
        for entry in candidates:
            if isinstance(entry, dict) and wanted and wanted in (
                _openalex_key(entry.get("openalex_id")), _openalex_key(entry.get("id")),
            ):
                match = entry
                break
        if match is None:
            raise Refused("CANDIDATE_UNKNOWN", f"no candidate {candidate!r} in {candidates_path.name}")
        record_journal = {
            "name": match.get("display_name"),
            "issn": _issn_list(match.get("issn")),
            "issn_l": match.get("issn_l"),
            "publisher": match.get("publisher"),
            "homepage_url": match.get("homepage_url"),
        }
        extra = {
            "quartile": match.get("quartile"),
            "quartile_source": match.get("quartile_source"),
            "review_time": match.get("review_time"),
            "via": "candidate",
            "candidate_id": _openalex_key(match.get("openalex_id") or match.get("id")),
        }
    else:
        name = (journal or "").strip()
        if not name:
            raise Refused("SELECT_MODE_REQUIRED", "--journal must not be empty")
        record_journal = {
            "name": name, "issn": [_normalize_issn(issn)], "issn_l": None,
            "publisher": None, "homepage_url": None,
        }
        extra = {
            "quartile": None, "quartile_source": None, "review_time": None,
            "via": "manual", "candidate_id": None,
        }

    record = {"schema": 1, "slug": slug, "journal": record_journal, "selected_at": clock()}
    record.update(extra)
    _write_json(target / "venue.json", record)
    return {"verb": "select", "slug": slug, "journal": record_journal["name"], "via": extra["via"],
            "venue": _relative_to_repo(paper_dir, target)}


# =====================================================================
# requirements
# =====================================================================
def _is_url(value) -> bool:
    return isinstance(value, str) and re.match(r"^https?://[^\s]+$", value) is not None


def _invalid(message: str):
    return Refused("REQUIREMENTS_INVALID", message)


def _sourced(entry: dict, owner: str, unsourced: list) -> None:
    quote = entry.get("quote")
    url = entry.get("url")
    if not isinstance(quote, str) or not quote.strip():
        unsourced.append(f"{owner}: no quote")
    if not _is_url(url):
        unsourced.append(f"{owner}: no http(s) url")


def _int_value(value, owner: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _invalid(f"{owner} must be a non-negative integer")
    return value


def _normalize_options(value, owner: str) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _invalid(f"{owner} must be a list of strings")
    return [item.strip() for item in value if item.strip()]


def validate_requirements(data) -> dict:
    """Shape first (`REQUIREMENTS_INVALID`), sourcing second
    (`REQUIREMENT_UNSOURCED`): every requirement -- the class, a section, a
    limit, a declaration, the reference style, an extra -- carries a `quote`
    from the guidelines and the `url` it came from. Returns the normalized
    record, defaults filled in."""
    if not isinstance(data, dict):
        raise _invalid("requirements must be a JSON object")
    allowed = {"schema", "guidelines_urls", "document_class", "sections", "limits",
               "declarations_required", "reference_style", "extras"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise _invalid(f"unknown key(s): {', '.join(unknown)}")
    if data.get("schema", 1) != 1:
        raise _invalid("schema must be 1")

    unsourced: list = []

    urls = data.get("guidelines_urls")
    if not isinstance(urls, list) or not urls or not all(_is_url(url) for url in urls):
        raise _invalid("guidelines_urls must be a non-empty list of http(s) urls")

    klass = data.get("document_class")
    if not isinstance(klass, dict):
        raise _invalid("document_class is required: {name, options, source, quote, url}")
    name = klass.get("name")
    if not isinstance(name, str) or not _CLASS_NAME_RE.match(name):
        raise _invalid("document_class.name must be a class name such as elsarticle")
    if klass.get("source") not in _CLASS_SOURCES:
        raise _invalid(f"document_class.source must be one of {', '.join(_CLASS_SOURCES)}")
    document_class = {
        "name": name, "options": _normalize_options(klass.get("options"), "document_class.options"),
        "source": klass["source"], "quote": klass.get("quote"), "url": klass.get("url"),
    }
    _sourced(document_class, "document_class", unsourced)

    raw_sections = data.get("sections", [])
    if not isinstance(raw_sections, list):
        raise _invalid("sections must be a list")
    sections, seen = [], set()
    for index, item in enumerate(raw_sections):
        owner = f"sections[{index}]"
        if not isinstance(item, dict):
            raise _invalid(f"{owner} must be an object")
        section_id = item.get("id")
        if not isinstance(section_id, str) or not _SECTION_ID_RE.match(section_id):
            raise _invalid(f"{owner}.id must be a smith section id or new:<name> (lowercase, hyphens)")
        if section_id in seen:
            raise _invalid(f"{owner}.id {section_id!r} is listed twice")
        seen.add(section_id)
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            raise _invalid(f"{owner}.title must be a non-empty string")
        if not isinstance(item.get("required"), bool):
            raise _invalid(f"{owner}.required must be true or false")
        order = _int_value(item.get("order"), f"{owner}.order")
        entry = {"id": section_id, "title": title.strip(), "required": item["required"], "order": order,
                 "quote": item.get("quote"), "url": item.get("url")}
        _sourced(entry, owner, unsourced)
        sections.append(entry)

    raw_limits = data.get("limits", {})
    if not isinstance(raw_limits, dict):
        raise _invalid("limits must be an object")
    stray = sorted(set(raw_limits) - set(LIMIT_KEYS))
    if stray:
        raise _invalid(f"unknown limit(s): {', '.join(stray)}; allowed: {', '.join(LIMIT_KEYS)}")
    limits = {}
    for key in LIMIT_KEYS:
        if key not in raw_limits:
            continue
        item = raw_limits[key]
        owner = f"limits.{key}"
        if not isinstance(item, dict):
            raise _invalid(f"{owner} must be an object")
        if "min" not in item and "max" not in item:
            raise _invalid(f"{owner} needs a min, a max, or both")
        entry = {"quote": item.get("quote"), "url": item.get("url")}
        for bound in ("min", "max"):
            if bound in item:
                entry[bound] = _int_value(item[bound], f"{owner}.{bound}")
        if "min" in entry and "max" in entry and entry["min"] > entry["max"]:
            raise _invalid(f"{owner}.min exceeds {owner}.max")
        _sourced(entry, owner, unsourced)
        limits[key] = entry

    raw_declarations = data.get("declarations_required", [])
    if not isinstance(raw_declarations, list):
        raise _invalid("declarations_required must be a list")
    declarations, seen_declarations = [], set()
    for index, item in enumerate(raw_declarations):
        owner = f"declarations_required[{index}]"
        if isinstance(item, str):
            unsourced.append(f"{owner} ({item!r}): a bare id carries no quote or url")
            continue
        if not isinstance(item, dict):
            raise _invalid(f"{owner} must be an object {{id, quote, url}}")
        declaration_id = item.get("id")
        if not isinstance(declaration_id, str) or not _DECLARATION_ID_RE.match(declaration_id):
            raise _invalid(f"{owner}.id must be lowercase words joined by hyphens")
        if declaration_id in seen_declarations:
            raise _invalid(f"{owner}.id {declaration_id!r} is listed twice")
        seen_declarations.add(declaration_id)
        entry = {"id": declaration_id, "quote": item.get("quote"), "url": item.get("url")}
        _sourced(entry, owner, unsourced)
        declarations.append(entry)

    reference_style = None
    raw_style = data.get("reference_style")
    if raw_style is not None:
        if not isinstance(raw_style, dict):
            raise _invalid("reference_style must be an object {bst or description, quote, url}")
        bst, description = raw_style.get("bst"), raw_style.get("description")
        if bst is None and description is None:
            raise _invalid("reference_style needs a bst or a description")
        if bst is not None and (not isinstance(bst, str) or not _BST_RE.match(bst)):
            raise _invalid("reference_style.bst must be a .bst name such as elsarticle-num")
        if description is not None and (not isinstance(description, str) or not description.strip()):
            raise _invalid("reference_style.description must be a non-empty string")
        reference_style = {"bst": bst, "description": description,
                           "quote": raw_style.get("quote"), "url": raw_style.get("url")}
        _sourced(reference_style, "reference_style", unsourced)

    raw_extras = data.get("extras", [])
    if not isinstance(raw_extras, list):
        raise _invalid("extras must be a list")
    extras, seen_extras = [], set()
    for index, item in enumerate(raw_extras):
        owner = f"extras[{index}]"
        if not isinstance(item, dict):
            raise _invalid(f"{owner} must be an object {{id, quote, url}}")
        extra_id = item.get("id")
        if not isinstance(extra_id, str) or not _DECLARATION_ID_RE.match(extra_id):
            raise _invalid(f"{owner}.id must be lowercase words joined by hyphens")
        if extra_id in seen_extras:
            raise _invalid(f"{owner}.id {extra_id!r} is listed twice")
        seen_extras.add(extra_id)
        entry = {"id": extra_id, "quote": item.get("quote"), "url": item.get("url")}
        _sourced(entry, owner, unsourced)
        extras.append(entry)

    if unsourced:
        raise Refused(
            "REQUIREMENT_UNSOURCED",
            "every requirement needs the quote from the guidelines and the url it came from: "
            + "; ".join(unsourced),
        )
    return {
        "schema": 1, "guidelines_urls": urls, "document_class": document_class, "sections": sections,
        "limits": limits, "declarations_required": declarations, "reference_style": reference_style,
        "extras": extras,
    }


def store_requirements(paper_dir: Path, slug: str, file_path: Path) -> dict:
    directory = _require_venue(paper_dir, slug)
    try:
        raw = json.loads(Path(file_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused("REQUIREMENTS_INVALID", f"{file_path}: not readable JSON: {exc}")
    normalized = validate_requirements(raw)
    payload = _json_bytes(normalized)
    _atomic_write(directory / "requirements.json", payload)
    return {
        "verb": "requirements", "slug": slug, "sha256": _sha256_bytes(payload),
        "counts": {
            "sections": len(normalized["sections"]), "limits": len(normalized["limits"]),
            "declarations": len(normalized["declarations_required"]), "extras": len(normalized["extras"]),
        },
        "document_class": normalized["document_class"]["name"],
    }


# =====================================================================
# acquire
# =====================================================================
def _member_name(raw: str) -> str:
    """The safe relative POSIX name of one archive member, or a refusal."""
    name = raw.replace("\\", "/")
    pure = PurePosixPath(name)
    if (
        not name or name.startswith("/") or re.match(r"^[A-Za-z]:", name)
        or ".." in pure.parts or "\x00" in name
    ):
        raise Refused("TEMPLATE_UNSAFE", f"archive member {raw!r} escapes the template directory")
    return str(pure)


def _extract_zip(archive: Path, stage: Path) -> list:
    try:
        zf = zipfile.ZipFile(str(archive))
    except (zipfile.BadZipFile, OSError) as exc:
        raise Refused("TEMPLATE_UNSAFE", f"{archive.name} is not a readable zip archive: {exc}")
    with zf:
        members = [info for info in zf.infolist() if not info.filename.startswith("__MACOSX/")]
        if len(members) > MAX_TEMPLATE_FILES:
            raise Refused(
                "TEMPLATE_UNSAFE",
                f"archive has {len(members)} entries; the cap is {MAX_TEMPLATE_FILES}",
            )
        planned = []
        total = 0
        for info in members:
            name = _member_name(info.filename)
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and stat.S_ISLNK(mode):
                raise Refused("TEMPLATE_UNSAFE", f"archive member {info.filename!r} is a symbolic link")
            total += info.file_size
            if total > MAX_TEMPLATE_BYTES:
                raise Refused(
                    "TEMPLATE_UNSAFE",
                    f"archive expands past the size cap of {MAX_TEMPLATE_BYTES} bytes",
                )
            planned.append((info, name))
        stage_root = stage.resolve()
        written, extracted = [], 0
        for info, name in planned:
            target = (stage / name).resolve()
            try:
                target.relative_to(stage_root)
            except ValueError:
                raise Refused("TEMPLATE_UNSAFE", f"archive member {info.filename!r} escapes the template directory")
            if info.is_dir() or name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            if PurePosixPath(name).name == ".DS_Store":
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, open(str(target), "wb") as sink:
                remaining = info.file_size
                while remaining > 0:
                    chunk = source.read(min(65536, remaining))
                    if not chunk:
                        break
                    extracted += len(chunk)
                    if extracted > MAX_TEMPLATE_BYTES:
                        raise Refused(
                            "TEMPLATE_UNSAFE",
                            f"archive expands past the size cap of {MAX_TEMPLATE_BYTES} bytes",
                        )
                    sink.write(chunk)
                    remaining -= len(chunk)
            written.append(name)
    return sorted(written)


def _detect_class(files: list, hint: str | None) -> str | None:
    classes = sorted({PurePosixPath(name).stem for name in files if name.lower().endswith(".cls")})
    if not classes:
        return None
    if hint and hint in classes:
        return hint
    return classes[0]


def acquire(
    paper_dir: Path, slug: str, *, texlive: str | None = None, file: Path | None = None,
    url: str | None = None, clock=_clock, tool_path: str | None = None,
    tool_fallback_dirs: tuple = paper_latex.TOOL_FALLBACK_DIRS,
) -> dict:
    directory = _require_venue(paper_dir, slug)
    if texlive is not None and file is not None:
        raise Refused("ACQUIRE_MODE_CONFLICT", "--texlive and --file were given together; choose one")
    if texlive is None and file is None:
        raise Refused("ACQUIRE_MODE_REQUIRED", "--texlive <class> or --file <zip|cls|sty|bst|tex> --url <origin> is required")

    if texlive is not None:
        if not _CLASS_NAME_RE.match(texlive):
            raise Refused("TEMPLATE_CLASS_INVALID", f"{texlive!r} is not a document class name")
        binary = paper_latex.discover_kpsewhich(tool_path, tool_fallback_dirs)
        if binary is None:
            raise Refused(
                "TEXLIVE_UNAVAILABLE",
                "kpsewhich was not found on PATH or in the usual TeX Live directories; "
                "install TeX Live or acquire the class with --file/--url",
            )
        resolved = paper_latex.kpsewhich_lookup(binary, texlive + ".cls")
        if resolved is None:
            raise Refused(
                "TEMPLATE_ABSENT",
                f"TeX Live has no {texlive}.cls; acquire the publisher's template with --file/--url",
            )
        record = {"schema": 1, "kind": "texlive", "class": texlive, "path": resolved,
                  "tool": binary, "resolved_at": clock()}
        _write_json(directory / "template.json", record)
        stale = directory / "template"
        if stale.is_dir():
            shutil.rmtree(str(stale))
        return {"verb": "acquire", "slug": slug, "kind": "texlive", "class": texlive, "path": resolved}

    if not isinstance(url, str) or not re.match(r"^https?://\S+$", url):
        raise Refused("TEMPLATE_ORIGIN_REQUIRED", "--url <http(s) origin of the template> is required with --file")
    source = Path(file).expanduser()
    if not source.is_file():
        raise Refused("TEMPLATE_ABSENT", f"{source} does not exist or is not a file")
    suffix = source.suffix.lower()
    if suffix not in TEMPLATE_SUFFIXES:
        raise Refused(
            "TEMPLATE_FILE_UNSUPPORTED",
            f"{source.name}: expected one of {', '.join(TEMPLATE_SUFFIXES)}",
        )
    size = source.stat().st_size
    if size > MAX_TEMPLATE_BYTES:
        raise Refused("TEMPLATE_UNSAFE", f"{source.name} is {size} bytes; the size cap is {MAX_TEMPLATE_BYTES}")

    directory.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=str(directory), prefix=".template-"))
    try:
        if suffix == ".zip":
            files = _extract_zip(source, stage)
        else:
            shutil.copyfile(str(source), str(stage / source.name))
            files = [source.name]
        hint = None
        requirements_path = directory / "requirements.json"
        if requirements_path.is_file():
            try:
                hint = _read_json(requirements_path)["document_class"]["name"]
            except (OSError, ValueError, KeyError, TypeError):
                hint = None
        record = {
            "schema": 1, "kind": "publisher-template", "class": _detect_class(files, hint),
            "origin_url": url, "sha256": _sha256_file(source), "source_name": source.name,
            "bytes": size, "files": files, "acquired_at": clock(),
        }
        final = directory / "template"
        if final.is_dir():
            shutil.rmtree(str(final))
        os.replace(str(stage), str(final))
    except BaseException:
        shutil.rmtree(str(stage), ignore_errors=True)
        raise
    _write_json(directory / "template.json", record)
    return {"verb": "acquire", "slug": slug, "kind": "publisher-template", "class": record["class"],
            "files": files, "sha256": record["sha256"]}


# =====================================================================
# readers over the manuscript and the contracts
# =====================================================================
_EXTENT_LINE_RE = re.compile(r"^\*\*Extent\*\*[ \t]+(?P<rest>.+?)[ \t]*$", re.MULTILINE)
_RANGE_RE = re.compile(
    r"^(?:(?P<label>[A-Za-z][A-Za-z ]*?)\s+)?(?P<lo>\d+)\s*(?:[–—-]|to)\s*(?P<hi>\d+)\b\s*(?P<unit>[A-Za-z]+)?"
)


def extent_line(body: str) -> str | None:
    """The section-level `**Extent**` line of a contract body (the first line
    that opens with it; `**Extent.**` lines further down describe one block)."""
    found = _EXTENT_LINE_RE.search(body)
    return found.group(0) if found else None


def parse_extent(line: str) -> dict | None:
    """Best-effort reading of the `**Extent**` prose: `560–3950 words · 2 to 5
    subsections` -> `{"words": (560, 3950)}`; `title 10–13 words · keywords
    4–8` -> `{"title": (10, 13), "keywords": (4, 8)}`. Ranges counted in
    anything but words (subsections, sentences, paragraphs) are ignored.
    `None` when nothing parses -- the caller reports `undecidable`."""
    found = _EXTENT_LINE_RE.match(line.strip())
    if not found:
        return None
    result = {}
    for segment in found.group("rest").split("·"):
        segment = segment.replace("**", "").strip()
        match = _RANGE_RE.match(segment)
        if not match:
            continue
        label, unit = match.group("label"), (match.group("unit") or "").lower()
        bounds = (int(match.group("lo")), int(match.group("hi")))
        if label:
            if unit in ("", "words"):
                result[label.strip().lower()] = bounds
        elif unit == "words":
            result["words"] = bounds
    return result or None


def read_extent(body: str) -> dict | None:
    line = extent_line(body)
    return parse_extent(line) if line else None


_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")
_SKIPPED_ENVS = (
    "equation", "align", "eqnarray", "gather", "multline", "displaymath", "math", "figure", "table",
    "tabular", "tikzpicture", "lstlisting", "verbatim", "algorithm", "algorithmic",
)
_ENV_RE = re.compile(
    r"\\begin\{(?P<env>(?:" + "|".join(_SKIPPED_ENVS) + r")\*?)\}.*?\\end\{(?P=env)\}", re.DOTALL
)
_DISPLAY_MATH_RE = re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]|\\\(.*?\\\)|\$[^$]*\$", re.DOTALL)
_ARGUMENT_COMMAND_RE = re.compile(
    r"\\(?:cite[a-zA-Z]*|ref|eqref|autoref|cref|Cref|pageref|label|url|href|includegraphics)\*?"
    r"(?:\[[^\]]*\])*\{[^}]*\}"
)
_COMMAND_RE = re.compile(r"\\[A-Za-z]+\*?|\\.")
_WORD_RE = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")


def strip_comments(tex: str) -> str:
    return _COMMENT_RE.sub("", tex)


def count_words(tex: str) -> int:
    """Words in the prose of a LaTeX fragment: comments, display and inline
    math, figure/table/equation environments and citation-like commands are
    dropped; every other command keeps its argument. An approximation with a
    stated rule, the same one every measurement here uses."""
    text = strip_comments(tex)
    previous = None
    while previous != text:
        previous = text
        text = _ENV_RE.sub(" ", text)
    text = _DISPLAY_MATH_RE.sub(" ", text)
    text = _ARGUMENT_COMMAND_RE.sub(" ", text)
    text = _COMMAND_RE.sub(" ", text)
    return len(_WORD_RE.findall(text))


def _balanced_group(text: str, start: int) -> tuple:
    """`(content, end)` of the `{...}` group opening at `text[start]`;
    `\\{` and `\\}` do not count. `("", start)` when it never closes."""
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
        index += 1
    return "", start


def _command_argument(tex: str, command: str) -> str | None:
    match = re.search(r"\\" + command + r"(?![A-Za-z])\s*(?:\[[^\]]*\])?\s*\{", tex)
    if not match:
        return None
    content, end = _balanced_group(tex, match.end() - 1)
    return content if end > match.end() - 1 else None


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


_SIZE_COMMAND_RE = re.compile(r"^\\(?:Large|large|LARGE|huge|Huge|normalsize|bfseries|bf)\b\s*")


def read_title(tex: str) -> str | None:
    """The `\\title{...}` argument with size commands and one outer
    `\\textbf{...}` unwrapped."""
    argument = _command_argument(strip_comments(tex), "title")
    if argument is None:
        return None
    text = argument.strip()
    previous = None
    while previous != text:
        previous = text
        text = _SIZE_COMMAND_RE.sub("", text).strip()
        if text.startswith("\\textbf{"):
            inner, end = _balanced_group(text, len("\\textbf"))
            if end == len(text):
                text = inner.strip()
    return _collapse(text) or None


_SUPERSCRIPT_RE = re.compile(r"\$\^\{[^{}]*\}\$|\$\^[^${}]*\$")
_TEXT_STYLE_RE = re.compile(r"\\text(?:bf|it|tt|sc|sl|rm|sf)\{")


def _unwrap_text_styles(text: str) -> str:
    """`\\textbf{Andr{\\'e}s}` -> `Andr{\\'e}s`: the style command goes, its
    argument (nested braces and all) stays."""
    while True:
        match = _TEXT_STYLE_RE.search(text)
        if match is None:
            return text
        inner, end = _balanced_group(text, match.end() - 1)
        if end <= match.end() - 1:
            return text[:match.start()] + text[match.end():]
        text = text[:match.start()] + inner + text[end:]


def _clean_inline(text: str) -> str:
    return _collapse(_unwrap_text_styles(_SUPERSCRIPT_RE.sub("", text)))


def read_authors(tex: str) -> tuple:
    """`(names, affiliations)` from `\\author{...}`: the first `\\\\`-separated
    line is the names, the rest the affiliations; superscript markers and
    text-style wrappers are removed. Best effort -- the build reports it."""
    argument = _command_argument(strip_comments(tex), "author")
    if argument is None:
        return None, []
    pieces = [_clean_inline(piece) for piece in re.split(r"\\\\(?:\[[^\]]*\])?", argument)]
    pieces = [piece for piece in pieces if piece]
    if not pieces:
        return None, []
    return pieces[0], pieces[1:]


def _split_top_level(text: str) -> list:
    parts, depth, current = [], 0, []
    index = 0
    while index < len(text):
        char = text[index]
        if text.startswith("\\sep", index) or text.startswith("\\and", index):
            parts.append("".join(current))
            current = []
            index += 4
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        if char in ",;" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def read_keywords(body: str) -> list:
    """The keywords of a keywords block: `\\textbf{Keywords:} a, b, c.`,
    `\\keywords{a \\and b}` or an `IEEEkeywords`/`keyword` environment."""
    text = strip_comments(body).strip()
    label = re.search(r"\\textbf\{\s*Keywords?\s*:?\s*\}\s*:?", text, re.IGNORECASE)
    if label:
        text = text[label.end():]
    else:
        command = _command_argument(text, "keywords")
        if command is not None:
            text = command
        else:
            env = re.search(r"\\begin\{(?:IEEEkeywords|keyword)\}(.*?)\\end\{", text, re.DOTALL)
            if env:
                text = env.group(1)
    text = _collapse(text).rstrip(".").strip()
    return [item for item in (_collapse(part) for part in _split_top_level(text)) if item]


_CITE_KEYS_RE = re.compile(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]*)\}")
_DOCUMENTCLASS_RE = re.compile(
    r"^[ \t]*\\documentclass(?:\[(?P<options>[^\]]*)\])?\{(?P<name>[^}]+)\}", re.MULTILINE
)
_BIBSTYLE_RE = re.compile(r"^[ \t]*\\bibliographystyle\{(?P<name>[^}]+)\}", re.MULTILINE)
_SECTION_COMMAND_RE = re.compile(r"^[ \t]*\\section\*?\{")


def _split_id(qualified: str) -> tuple:
    section, _, name = qualified.partition(".")
    return section, name


class Manuscript:
    """The canonical `main.tex`, read once: ordered blocks with their
    section, body and byte regions; the heading each section sits under; the
    preamble facts. Reads through `paper_block.parse`, so every marker
    refusal (`MARKER_MALFORMED`, `BLOCK_*`) is the one `status` already has."""

    def __init__(self, paper_dir: Path) -> None:
        tex_path = paper_block.resolve_main_tex(paper_dir)
        self.path = tex_path
        self.data = tex_path.read_bytes()
        self.sha256 = _sha256_bytes(self.data)
        parsed = paper_block.parse(self.data)
        self.blocks = []
        self.by_id = {}
        for block_id in parsed.order:
            begin, end = parsed.pairs[block_id]
            section, name = _split_id(block_id)
            body = self.data[begin["end"]:end["start"]]
            block = {
                "id": block_id, "section": section, "name": name, "begin": begin, "end": end,
                "body": body, "text": body.decode("utf-8"),
                "digest": begin["digest"], "written": bool(body.strip()),
            }
            self.blocks.append(block)
            self.by_id[block_id] = block
        self.sections = []
        for block in self.blocks:
            if block["section"] not in self.sections:
                self.sections.append(block["section"])
        outside = paper_block.project(self.data).decode("utf-8")
        self.outside = outside
        preamble = outside.split("\\begin{document}", 1)[0]
        found = _DOCUMENTCLASS_RE.search(strip_comments(preamble))
        self.document_class = found.group("name").strip() if found else None
        self.options = (
            [item.strip() for item in (found.group("options") or "").split(",") if item.strip()]
            if found else []
        )
        style = _BIBSTYLE_RE.search(strip_comments(outside))
        self.bibliography_style = style.group("name").strip() if style else None
        self.preamble = preamble
        self.headings = self._headings()

    def _headings(self) -> dict:
        """The `\\section` line sitting between a section's first block and
        whatever block precedes it, outside every block region."""
        headings = {}
        previous_end = 0
        for block in sorted(self.blocks, key=lambda b: b["begin"]["start"]):
            gap = self.data[previous_end:block["begin"]["start"]].decode("utf-8")
            if block["section"] not in headings:
                lines = [line for line in gap.splitlines() if _SECTION_COMMAND_RE.match(line)]
                if lines:
                    headings[block["section"]] = lines[-1].strip()
            previous_end = block["end"]["end"]
        return headings

    def section_blocks(self, section: str) -> list:
        return [block for block in self.blocks if block["section"] == section]

    def written_sections(self) -> list:
        return [s for s in self.sections if any(b["written"] for b in self.section_blocks(s))]

    def content_sections(self) -> list:
        return [s for s in self.written_sections() if s not in FRONT_SECTIONS and s != BACK_SECTION]

    def region(self, section: str) -> bytes:
        """The section's bytes, first begin marker to last end marker, glue
        between its blocks included -- when the section is contiguous.
        Otherwise its blocks one by one, a blank line apart."""
        blocks = self.section_blocks(section)
        first, last = blocks[0], blocks[-1]
        start, stop = first["begin"]["start"], last["end"]["end"]
        for other in self.blocks:
            if other["section"] != section and start <= other["begin"]["start"] < stop:
                return b"\n".join(self.block_region(b) for b in blocks)
        return self.data[start:stop]

    def block_region(self, block: dict) -> bytes:
        return self.data[block["begin"]["start"]:block["end"]["end"]]

    def region_for(self, kind: str) -> bytes | None:
        found = paper_region.find_region(self.data, kind)
        if found is None:
            return None
        return self.data[found["begin_start"]:found["end_end"]]

    def verify_digests(self) -> None:
        for block in self.blocks:
            actual = _sha256_bytes(block["body"])
            if actual != block["digest"]:
                raise Refused(
                    "BLOCK_HAND_EDITED",
                    f"{block['id']!r}: expected sha256={block['digest']}, found sha256={actual}; "
                    "run `substitute --adopt` for a deliberate hand edit before building",
                )


def read_contracts(sections_dir: Path) -> tuple:
    """Every `NN-*.md` section contract, through `paper_contract.parse`:
    `{section, position, file, blocks, extent_line, extent}`, in document
    order (`position`), and the sha256 of the contracts' bytes."""
    records, digest = [], hashlib.sha256()
    for path in sorted(sections_dir.glob("[0-9][0-9]-*.md")):
        raw = path.read_bytes()
        header, body = paper_contract.parse(raw)
        text = body.decode("utf-8", errors="replace")
        records.append({
            "section": header.section, "position": header.position, "file": path.name,
            "blocks": [block["id"] for block in header.blocks],
            "extent_line": extent_line(text), "extent": read_extent(text),
        })
        digest.update(path.name.encode("utf-8") + b"\0" + raw + b"\0")
    if not records:
        raise Refused("SECTION_CONTRACTS_UNREADABLE", f"{sections_dir} holds no NN-*.md section contracts")
    records.sort(key=lambda record: (record["position"], record["file"]))
    return records, digest.hexdigest()


# =====================================================================
# diff
# =====================================================================
_SEVERITY_RANK = {"blocker": 0, "major": 1, "minor": 2}

#: How a declaration the venue requires is recognised among smith's blocks.
_DECLARATION_TOKENS = {
    "author-contributions": ("author-contributions", "contributions", "credit"),
    "funding": ("funding", "grant"),
    "data-availability": ("data-availability",),
    "code-availability": ("code-availability",),
    "conflicts": ("conflicts", "competing", "interest"),
    "ethics": ("ethics",),
    "acknowledgments": ("acknowledg",),
}


def _venue_side(entry: dict, **values) -> dict:
    side = {"quote": entry.get("quote"), "url": entry.get("url")}
    side.update(values)
    return side


def _declaration_present(manuscript: Manuscript, declaration_id: str) -> bool:
    tokens = _DECLARATION_TOKENS.get(declaration_id, (declaration_id,))
    for block in manuscript.blocks:
        if not block["written"]:
            continue
        lowered = block["id"].lower()
        if any(token in lowered for token in tokens):
            return True
        if declaration_id == "code-availability" and "data-availability" in lowered \
                and re.search(r"\bcode\b", block["text"], re.IGNORECASE):
            return True
    return False


def _longest_increasing(ranks: list) -> list:
    """Indices of one longest strictly increasing subsequence of `ranks`."""
    if not ranks:
        return []
    best = [1] * len(ranks)
    parent = [-1] * len(ranks)
    for i in range(len(ranks)):
        for j in range(i):
            if ranks[j] < ranks[i] and best[j] + 1 > best[i]:
                best[i], parent[i] = best[j] + 1, j
    end = max(range(len(ranks)), key=lambda i: best[i])
    chain = []
    while end != -1:
        chain.append(end)
        end = parent[end]
    return sorted(chain)


def measure(manuscript: Manuscript) -> dict:
    """What the written manuscript measures, by the rules `count_words` states."""
    def written_text(blocks):
        return "\n".join(block["text"] for block in blocks if block["written"])

    abstract = [b for b in manuscript.section_blocks("abstract") if b["written"]]
    title_block = manuscript.by_id.get(TITLE_BLOCK)
    keywords_block = manuscript.by_id.get(KEYWORDS_BLOCK)
    content = [b for s in manuscript.content_sections() for b in manuscript.section_blocks(s)]
    everything = "\n".join(block["text"] for block in manuscript.blocks if block["written"])
    title = read_title(title_block["text"]) if title_block and title_block["written"] else None
    keywords = read_keywords(keywords_block["text"]) if keywords_block and keywords_block["written"] else None
    cited = set()
    for found in _CITE_KEYS_RE.finditer(strip_comments(everything)):
        cited.update(key.strip() for key in found.group(1).split(",") if key.strip())
    return {
        "abstract_words": count_words(written_text(abstract)) if abstract else None,
        "keywords": len(keywords) if keywords is not None else None,
        "title_words": count_words(title) if title else None,
        "main_text_words": count_words(written_text(content)) if content else None,
        "figures": len(re.findall(r"\\begin\{figure\*?\}", strip_comments(everything))),
        "tables": len(re.findall(r"\\begin\{table\*?\}", strip_comments(everything))),
        "references": len(cited),
        "pages": None,
    }


def _limit_blocks(manuscript: Manuscript, key: str) -> list:
    if key == "abstract_words":
        return [b["id"] for b in manuscript.section_blocks("abstract") if b["written"]]
    if key == "title_words":
        return [TITLE_BLOCK] if TITLE_BLOCK in manuscript.by_id else []
    if key == "keywords":
        return [KEYWORDS_BLOCK] if KEYWORDS_BLOCK in manuscript.by_id else []
    if key == "main_text_words":
        return [b["id"] for s in manuscript.content_sections() for b in manuscript.section_blocks(s) if b["written"]]
    pattern = {"figures": r"\\begin\{figure", "tables": r"\\begin\{table", "references": r"\\cite"}.get(key)
    if pattern is None:
        return []
    return [b["id"] for b in manuscript.blocks if b["written"] and re.search(pattern, strip_comments(b["text"]))]


def _contract_bounds(key: str, contracts: list, manuscript: Manuscript, findings: list, entry: dict) -> tuple | None:
    """The `(min, max)` smith's own contracts allow for `key`, or `None` when
    they say nothing; an `**Extent**` line that does not parse is reported
    once, `undecidable`."""
    by_section = {record["section"]: record for record in contracts}

    def unparseable(record: dict) -> None:
        findings.append({
            "id": f"undecidable:extent:{record['section']}", "kind": "undecidable", "severity": "minor",
            "basis": "contract", "subject": f"extent:{record['section']}",
            "smith": {"contract": record["file"], "extent_line": record["extent_line"]},
            "venue": _venue_side(entry, limit=key),
            "blocks": [b["id"] for b in manuscript.section_blocks(record["section"])],
            "resolved_by": "operator-decision",
            "message": f"{record['file']}: the **Extent** prose could not be read as a range, so "
                       f"the contract cannot be compared with the venue's {key} limit",
        })

    wanted = {"abstract_words": ("abstract", "words"), "title_words": ("title-and-keywords", "title"),
              "keywords": ("title-and-keywords", "keywords")}.get(key)
    if wanted:
        record = by_section.get(wanted[0])
        if record is None or record["extent_line"] is None:
            return None
        if record["extent"] is None or wanted[1] not in record["extent"]:
            unparseable(record)
            return None
        return record["extent"][wanted[1]]
    if key != "main_text_words":
        return None
    low = high = 0
    complete = True
    for section in manuscript.content_sections():
        record = by_section.get(section)
        if record is None or record["extent_line"] is None:
            continue
        if record["extent"] is None or "words" not in record["extent"]:
            unparseable(record)
            complete = False
            continue
        low += record["extent"]["words"][0]
        high += record["extent"]["words"][1]
    return (low, high) if complete and (low or high) else None


def compute_audit(
    manuscript: Manuscript, contracts: list, requirements: dict,
) -> dict:
    findings: list = []
    guidelines_url = requirements["guidelines_urls"][0]
    measurements = measure(manuscript)
    content_written = manuscript.content_sections()
    contract_by_section = {record["section"]: record for record in contracts}
    contract_content = [
        record["section"] for record in contracts
        if record["section"] not in FRONT_SECTIONS and record["section"] != BACK_SECTION
    ]

    # -- sections ----------------------------------------------------------------
    required_sections = [s for s in requirements["sections"] if s["id"] != "references"]
    listed = {s["id"] for s in requirements["sections"]}
    for section in required_sections:
        sid = section["id"]
        if sid.startswith("new:"):
            has_contract = False
            written = False
        elif sid == BACK_SECTION:
            has_contract = sid in contract_by_section
            written = any(b["written"] for b in manuscript.section_blocks(sid))
        else:
            has_contract = sid in contract_by_section
            written = sid in content_written
        if written or not section["required"]:
            continue
        findings.append({
            "id": f"missing-section:{sid}", "kind": "missing-section", "severity": "blocker",
            "basis": "structure", "subject": sid,
            "smith": {"contract": has_contract, "written": written},
            "venue": _venue_side(section, id=sid, title=section["title"], required=True),
            "blocks": [b["id"] for b in manuscript.section_blocks(sid)] if has_contract else [],
            "resolved_by": "operator-decision",
            "message": (
                f"the venue requires a {section['title']!r} section"
                + (" and smith has no such section; a plan item for the operator to decide, never invented"
                   if not has_contract else " and the manuscript has no written block for it")
            ),
        })
    if requirements["sections"]:
        for sid in content_written:
            if sid in listed:
                continue
            findings.append({
                "id": f"extra-section:{sid}", "kind": "extra-section", "severity": "minor",
                "basis": "structure", "subject": sid,
                "smith": {"contract": sid in contract_by_section, "written": True},
                "venue": {"quote": None, "url": guidelines_url, "sections": sorted(listed)},
                "blocks": [b["id"] for b in manuscript.section_blocks(sid)],
                "resolved_by": "operator-decision",
                "message": f"smith writes a {sid!r} section the venue's structure does not list; "
                           "the build keeps it after the venue's sections",
            })
    shared = [
        s for s in sorted(requirements["sections"], key=lambda s: s["order"])
        if not s["id"].startswith("new:") and s["id"] not in ("references", BACK_SECTION)
        and (s["id"] in contract_by_section or s["id"] in content_written)
    ]

    def smith_rank(sid: str) -> int:
        if sid in contract_by_section:
            return contract_by_section[sid]["position"]
        return 1000 + manuscript.sections.index(sid)

    ranks = [smith_rank(s["id"]) for s in shared]
    keep = set(_longest_increasing(ranks))
    displaced = [shared[i] for i in range(len(shared)) if i not in keep]
    if displaced:
        findings.append({
            "id": "out-of-order:section-order", "kind": "out-of-order", "severity": "minor",
            "basis": "structure", "subject": "section-order",
            "smith": {"order": [s["id"] for s in sorted(shared, key=lambda s: smith_rank(s["id"]))],
                      "displaced": [s["id"] for s in displaced]},
            "venue": _venue_side(displaced[0], order=[s["id"] for s in shared]),
            "blocks": [b["id"] for s in displaced for b in manuscript.section_blocks(s["id"])],
            "resolved_by": "build",
            "message": "the venue orders its sections differently from smith's base template; "
                       "the venue build transposes them, the canonical order is untouched",
        })

    # -- limits --------------------------------------------------------------------
    for key in LIMIT_KEYS:
        entry = requirements["limits"].get(key)
        if entry is None:
            continue
        vmin, vmax = entry.get("min"), entry.get("max")
        measured = measurements.get(key)
        blocks = _limit_blocks(manuscript, key)
        severity = "blocker" if key in BLOCKING_LIMITS else "major"
        if measured is None:
            reason = ("the page count needs a compiled venue PDF" if key == "pages"
                      else f"{key} could not be measured: the manuscript has no written block for it")
            findings.append({
                "id": f"undecidable:{key}", "kind": "undecidable", "severity": "minor",
                "basis": "measured", "subject": key, "smith": {"value": None, "blocks": blocks},
                "venue": _venue_side(entry, min=vmin, max=vmax), "blocks": blocks,
                "resolved_by": "operator-decision", "message": reason,
            })
        else:
            for kind, bad, bound in (("over-limit", vmax is not None and measured > vmax, vmax),
                                     ("under-limit", vmin is not None and measured < vmin, vmin)):
                if not bad:
                    continue
                findings.append({
                    "id": f"{kind}:{key}", "kind": kind, "severity": severity, "basis": "measured",
                    "subject": key, "smith": {"value": measured, "unit": "count"},
                    "venue": _venue_side(entry, min=vmin, max=vmax), "blocks": blocks,
                    "resolved_by": "text-change",
                    "message": f"the manuscript measures {measured} for {key}; the venue's "
                               f"{'maximum' if kind == 'over-limit' else 'minimum'} is {bound}",
                })
        bounds = _contract_bounds(key, contracts, manuscript, findings, entry)
        if bounds is not None:
            clo, chi = bounds
            if vmax is not None and chi > vmax:
                conflict = clo > vmax
                findings.append({
                    "id": f"over-limit:{key}:contract", "kind": "over-limit",
                    "severity": "major" if conflict else "minor", "basis": "contract", "subject": key,
                    "smith": {"min": clo, "max": chi, "conflict": conflict},
                    "venue": _venue_side(entry, min=vmin, max=vmax), "blocks": blocks,
                    "resolved_by": "operator-decision",
                    "message": f"smith's contract lets {key} reach {chi}; the venue's maximum is {vmax}"
                               + (" and the contract's own minimum already exceeds it" if conflict else ""),
                })
            if vmin is not None and clo < vmin:
                conflict = chi < vmin
                findings.append({
                    "id": f"under-limit:{key}:contract", "kind": "under-limit",
                    "severity": "major" if conflict else "minor", "basis": "contract", "subject": key,
                    "smith": {"min": clo, "max": chi, "conflict": conflict},
                    "venue": _venue_side(entry, min=vmin, max=vmax), "blocks": blocks,
                    "resolved_by": "operator-decision",
                    "message": f"smith's contract lets {key} fall to {clo}; the venue's minimum is {vmin}"
                               + (" and the contract's own maximum is below it" if conflict else ""),
                })

    # -- declarations and extras -----------------------------------------------------
    for entry in requirements["declarations_required"]:
        if _declaration_present(manuscript, entry["id"]):
            continue
        findings.append({
            "id": f"missing-declaration:{entry['id']}", "kind": "missing-declaration", "severity": "blocker",
            "basis": "structure", "subject": entry["id"],
            "smith": {"written": False}, "venue": _venue_side(entry, id=entry["id"]),
            "blocks": [b["id"] for b in manuscript.section_blocks(BACK_SECTION)],
            "resolved_by": "text-change",
            "message": f"the venue requires a {entry['id']} declaration and no written block carries it",
        })
    for entry in requirements["extras"]:
        token = entry["id"].lower()
        present = any(b["written"] and token in b["id"].lower() for b in manuscript.blocks)
        if present:
            continue
        findings.append({
            "id": f"missing-extra:{entry['id']}", "kind": "missing-extra", "severity": "major",
            "basis": "structure", "subject": entry["id"],
            "smith": {"written": False}, "venue": _venue_side(entry, id=entry["id"]),
            "blocks": [], "resolved_by": "operator-decision",
            "message": f"the venue asks for {entry['id']}; smith's template has no such part",
        })

    # -- class and bibliography style ----------------------------------------------------
    klass = requirements["document_class"]
    smith_options = sorted(manuscript.options)
    venue_options = sorted(klass["options"])
    if manuscript.document_class != klass["name"] or smith_options != venue_options:
        findings.append({
            "id": "class-mismatch:document-class", "kind": "class-mismatch", "severity": "minor",
            "basis": "structure", "subject": "document-class",
            "smith": {"class": manuscript.document_class, "options": manuscript.options},
            "venue": _venue_side(klass, **{"class": klass["name"], "options": klass["options"],
                                           "source": klass["source"]}),
            "blocks": [], "resolved_by": "build",
            "message": f"smith's main.tex uses {manuscript.document_class or 'no document class'}; "
                       f"the venue asks for {klass['name']}; the venue build writes the venue's class line",
        })
    style = requirements["reference_style"]
    if style is not None:
        if style["bst"] is None:
            findings.append({
                "id": "undecidable:reference-style", "kind": "undecidable", "severity": "minor",
                "basis": "structure", "subject": "reference-style",
                "smith": {"bst": manuscript.bibliography_style}, "venue": _venue_side(style, description=style["description"]),
                "blocks": [], "resolved_by": "operator-decision",
                "message": "the venue describes its reference style in prose; name a .bst to compare and build with",
            })
        elif manuscript.bibliography_style != style["bst"]:
            findings.append({
                "id": "reference-style-mismatch:reference-style", "kind": "reference-style-mismatch",
                "severity": "minor", "basis": "structure", "subject": "reference-style",
                "smith": {"bst": manuscript.bibliography_style}, "venue": _venue_side(style, bst=style["bst"]),
                "blocks": [], "resolved_by": "build",
                "message": f"smith cites with {manuscript.bibliography_style or 'no bibliography style'}; "
                           f"the venue asks for {style['bst']}; the venue build writes the venue's style",
            })

    unique = {}
    for finding in findings:
        unique.setdefault(finding["id"], finding)
    findings = sorted(unique.values(), key=lambda f: (_SEVERITY_RANK[f["severity"]], f["kind"], f["id"]))
    counts = {name: sum(1 for f in findings if f["severity"] == name) for name in _SEVERITY_RANK}
    return {
        "measurements": measurements,
        "smith": {
            "document_class": manuscript.document_class, "options": manuscript.options,
            "bibliography_style": manuscript.bibliography_style,
            "sections": manuscript.sections, "content_sections": content_written,
            "contract_sections": [record["section"] for record in contracts],
        },
        "findings": findings,
        "summary": dict(counts, total=len(findings)),
        "needs_plan": any(
            f["resolved_by"] in ("text-change", "operator-decision") and f["severity"] in ("blocker", "major")
            for f in findings
        ),
    }


def diff(paper_dir: Path, slug: str, sections_dir: Path, clock=_clock) -> dict:
    directory = _require_venue(paper_dir, slug)
    requirements_path = directory / "requirements.json"
    if not requirements_path.is_file():
        raise Refused("REQUIREMENTS_ABSENT", "requirements.json is absent; run `venue requirements` first")
    if not (directory / "template.json").is_file():
        raise Refused("TEMPLATE_ABSENT", "template.json is absent; run `venue acquire` first")
    try:
        requirements = _read_json(requirements_path)
    except (OSError, ValueError) as exc:
        raise Refused("REQUIREMENTS_ABSENT", f"requirements.json is unreadable: {exc}; run `venue requirements` again")
    manuscript = Manuscript(paper_dir)
    contracts, sections_digest = read_contracts(sections_dir)
    audit = compute_audit(manuscript, contracts, requirements)
    audit.update({
        "schema": 1, "slug": slug, "generated_at": clock(),
        "canonical_sha256": manuscript.sha256,
        "requirements_sha256": _sha256_file(requirements_path),
        "sections_sha256": sections_digest,
    })
    _write_json(directory / "audit.json", audit)
    result = dict(audit)
    result["verb"] = "diff"
    return result


# =====================================================================
# plan and approve
# =====================================================================
def store_plan(paper_dir: Path, slug: str, plan_path: Path) -> dict:
    directory = _require_venue(paper_dir, slug)
    audit_path = directory / "audit.json"
    if not audit_path.is_file():
        raise Refused("AUDIT_ABSENT", "audit.json is absent; run `venue diff` before planning")
    try:
        raw = Path(plan_path).read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Refused("PLAN_UNREADABLE", f"{plan_path}: {exc}")
    if not text.strip():
        raise Refused("PLAN_UNREADABLE", f"{plan_path} is empty")
    audit = _read_json(audit_path)
    referenced = [
        finding["id"] for finding in audit.get("findings", [])
        if re.search(r"(?<![\w:.-])" + re.escape(finding["id"]) + r"(?![\w:.-])", text)
    ]
    if not referenced:
        raise Refused(
            "PLAN_REFERENCES_NO_FINDING",
            "the plan names no finding id from audit.json; cite each item as e.g. "
            "[over-limit:abstract_words]",
        )
    _atomic_write(directory / "plan.md", raw)
    approval = directory / "approval.json"
    reset = approval.is_file()
    if reset:
        approval.unlink()
    return {
        "verb": "plan", "slug": slug, "plan_sha256": _sha256_bytes(raw),
        "referenced_findings": referenced, "approval_reset": reset,
        "audit_stale": _audit_stale(paper_dir, directory, audit),
    }


def approve(
    paper_dir: Path, slug: str, *, statement: str, plan_sha256: str, via: str = "cli", clock=_clock,
) -> dict:
    directory = _require_venue(paper_dir, slug)
    if not isinstance(statement, str) or not statement.strip():
        raise Refused("STATEMENT_EMPTY", "--statement must carry the operator's own words")
    plan_path = directory / "plan.md"
    if not plan_path.is_file():
        raise Refused("PLAN_ABSENT", "plan.md is absent; the agent proposes one with `venue plan`")
    current = _sha256_file(plan_path)
    if (plan_sha256 or "").strip().lower() != current:
        raise Refused(
            "PLAN_HASH_MISMATCH",
            f"--plan-sha256 does not match the current plan (sha256={current}); "
            "approval binds to the exact plan the operator read",
        )
    record = {
        "schema": 1, "slug": slug, "statement": statement, "plan_sha256": current,
        "approved_at": clock(), "via": via,
    }
    _write_json(directory / "approval.json", record)
    return {"verb": "approve", "slug": slug, "plan_sha256": current, "via": via}


def _valid_approval(directory: Path) -> bool:
    approval, plan = directory / "approval.json", directory / "plan.md"
    if not (approval.is_file() and plan.is_file()):
        return False
    try:
        return _read_json(approval).get("plan_sha256") == _sha256_file(plan)
    except (OSError, ValueError, AttributeError):
        return False


def _audit_stale(paper_dir: Path, directory: Path, audit: dict) -> bool:
    main_tex = paper_dir / "main.tex"
    requirements = directory / "requirements.json"
    if not main_tex.is_file() or not requirements.is_file():
        return True
    return (
        audit.get("canonical_sha256") != _sha256_file(main_tex)
        or audit.get("requirements_sha256") != _sha256_file(requirements)
    )


# =====================================================================
# build
# =====================================================================
_FAMILIES = {"elsarticle": "elsarticle", "ieeetran": "ieeetran", "llncs": "llncs"}
_SKIPPED_PACKAGES = {
    "elsarticle": ("geometry", "cite", "natbib"),
    "ieeetran": ("geometry",),
    "llncs": ("geometry",),
    "generic": (),
}
_KEPT_COMMANDS = (
    "usepackage", "RequirePackage", "newcommand", "renewcommand", "providecommand",
    "DeclareMathOperator", "newtheorem", "theoremstyle", "def", "newenvironment", "hypersetup",
    "geometry", "graphicspath",
)
_STATEMENT_RE = re.compile(r"^\\(?P<command>[A-Za-z]+)\*?")


def class_family(name: str) -> str:
    return _FAMILIES.get(name.lower(), "generic")


def _brace_balance(text: str) -> int:
    depth, index = 0, 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        depth += (char == "{") - (char == "}")
        index += 1
    return depth


def _preamble_statements(preamble: str) -> list:
    """The preamble's statements -- one command plus the lines its braces
    span -- as `(command, text)`, comments and blank lines dropped."""
    statements, pending = [], None
    for line in strip_comments(preamble).splitlines():
        if pending is None:
            stripped = line.strip()
            if not stripped:
                continue
            match = _STATEMENT_RE.match(stripped)
            pending = (match.group("command") if match else "", [])
        pending[1].append(line.rstrip())
        if _brace_balance("\n".join(pending[1])) <= 0:
            statements.append((pending[0], "\n".join(pending[1])))
            pending = None
    if pending is not None:
        statements.append((pending[0], "\n".join(pending[1])))
    return statements


def build_preamble(manuscript: Manuscript, family: str) -> tuple:
    """`(kept lines, skipped package names, dropped statements)`: the canonical
    preamble minus the class line, the packages the venue class owns or
    conflicts with, and anything this build does not recognise."""
    skip = _SKIPPED_PACKAGES[family]
    kept, skipped, dropped = [], [], []
    graphics = []
    for command, text in _preamble_statements(manuscript.preamble):
        if command == "documentclass":
            continue
        if command not in _KEPT_COMMANDS:
            dropped.append(text.strip())
            continue
        if command == "geometry":
            if "geometry" in skip:
                continue
            kept.append(text)
            continue
        if command == "graphicspath":
            graphics.extend(re.findall(r"\{([^{}]+)\}", text.split("{", 1)[1] if "{" in text else ""))
            continue
        if command in ("usepackage", "RequirePackage"):
            match = re.match(r"^(\\[A-Za-z]+)(\[[^\]]*\])?\{([^}]*)\}\s*$", text.strip(), re.DOTALL)
            if match:
                names = [name.strip() for name in match.group(3).split(",") if name.strip()]
                remaining = [name for name in names if name not in skip]
                skipped.extend(name for name in names if name in skip)
                if not remaining:
                    continue
                if len(remaining) != len(names):
                    text = f"{match.group(1)}{match.group(2) or ''}{{{','.join(remaining)}}}"
        kept.append(text)
    paths = ["../../"] + ["../../" + path.lstrip("./") for path in graphics]
    kept.append("\\graphicspath{" + "".join("{" + path + "}" for path in paths) + "}")
    return kept, sorted(set(skipped)), dropped


def _document_class_line(name: str, options: list) -> str:
    return f"\\documentclass[{','.join(options)}]{{{name}}}" if options else f"\\documentclass{{{name}}}"


def _retitle_heading(heading: str | None, title: str | None, section_id: str) -> str:
    """The `\\section` line for one emitted section: the canonical line with
    its label kept, the title replaced by the venue's when it names one."""
    if heading is None:
        return f"\\section{{{title or section_id.replace('-', ' ').title()}}}"
    if not title:
        return heading
    match = re.match(r"^(\s*\\section\*?)\{", heading)
    if not match:
        return heading
    _content, end = _balanced_group(heading, match.end() - 1)
    if end <= match.end() - 1:
        return heading
    return f"{match.group(1)}{{{title}}}{heading[end:]}"


def _front_matter(family: str, manuscript: Manuscript, report: dict) -> tuple:
    """`(preamble_text, front_text)` for one class family, plus what was mapped
    in `report`. Generic keeps the canonical title block where `\\maketitle`
    expects it; the others take the title, authors and keywords mapped out of
    the canonical blocks, which stay in the file inside `\\iffalse ... \\fi`."""
    title_block = manuscript.by_id.get(TITLE_BLOCK)
    keywords_block = manuscript.by_id.get(KEYWORDS_BLOCK)
    abstract_blocks = [b for b in manuscript.section_blocks("abstract")]
    abstract_region = manuscript.region("abstract").decode("utf-8") if abstract_blocks else ""
    report["abstract"] = [b["id"] for b in abstract_blocks]
    title = read_title(title_block["text"]) if title_block else None
    names, affiliations = read_authors(title_block["text"]) if title_block else (None, [])
    keywords = read_keywords(keywords_block["text"]) if keywords_block else []
    report["title"] = TITLE_BLOCK if title_block else None
    report["keywords"] = KEYWORDS_BLOCK if keywords_block else None
    report["unmapped"] = [
        name for name, value in (("title", title), ("authors", names), ("keywords", keywords or None),
                                 ("abstract", abstract_region or None)) if not value
    ]
    canonical = ""
    if family != "generic":
        sources = [manuscript.block_region(b).decode("utf-8") for b in (title_block, keywords_block) if b]
        if sources:
            canonical = "\\iffalse\n% canonical blocks, kept verbatim; the mapped front matter below is derived from them\n" \
                        + "".join(sources) + "\\fi\n"

    if family == "generic":
        pre = manuscript.block_region(title_block).decode("utf-8") if title_block else ""
        lines = ["\\maketitle", ""]
        if abstract_region or keywords_block:
            lines.append("\\begin{abstract}")
            if abstract_region:
                lines.append(abstract_region.rstrip("\n"))
            if keywords_block:
                lines.append(manuscript.block_region(keywords_block).decode("utf-8").rstrip("\n"))
            lines.append("\\end{abstract}")
        return pre, "\n".join(lines) + "\n"

    parts = [canonical]
    abstract_env = f"\\begin{{abstract}}\n{abstract_region.rstrip(chr(10))}\n\\end{{abstract}}\n" if abstract_region else ""
    if family == "elsarticle":
        parts.append("\\begin{frontmatter}\n")
        if title:
            parts.append(f"\\title{{{title}}}\n")
        if names:
            parts.append(f"\\author{{{names}}}\n")
        if affiliations:
            parts.append("\\address{" + " \\\\ ".join(affiliations) + "}\n")
        parts.append(abstract_env)
        if keywords:
            parts.append("\\begin{keyword}\n" + " \\sep ".join(keywords) + "\n\\end{keyword}\n")
        parts.append("\\end{frontmatter}\n")
    elif family == "ieeetran":
        if title:
            parts.append(f"\\title{{{title}}}\n")
        if names:
            block = f"\\IEEEauthorblockN{{{names}}}"
            if affiliations:
                block += "\n\\IEEEauthorblockA{" + " \\\\ ".join(affiliations) + "}"
            parts.append(f"\\author{{{block}}}\n")
        parts.append("\\maketitle\n")
        parts.append(abstract_env)
        if keywords:
            parts.append("\\begin{IEEEkeywords}\n" + ", ".join(keywords) + "\n\\end{IEEEkeywords}\n")
    else:  # llncs
        if title:
            parts.append(f"\\title{{{title}}}\n")
        if names:
            parts.append(f"\\author{{{names}}}\n")
        if affiliations:
            parts.append("\\institute{" + " \\and ".join(affiliations) + "}\n")
        parts.append("\\maketitle\n")
        if abstract_region:
            keywords_line = ("\\keywords{" + " \\and ".join(keywords) + "}\n") if keywords else ""
            parts.append(f"\\begin{{abstract}}\n{abstract_region.rstrip(chr(10))}\n{keywords_line}\\end{{abstract}}\n")
    return "", "".join(parts)


def build(paper_dir: Path, slug: str, clock=_clock) -> dict:
    directory = _require_venue(paper_dir, slug)
    requirements_path = directory / "requirements.json"
    if not requirements_path.is_file():
        raise Refused("REQUIREMENTS_ABSENT", "requirements.json is absent; run `venue requirements` first")
    template_path = directory / "template.json"
    if not template_path.is_file():
        raise Refused("TEMPLATE_ABSENT", "template.json is absent; run `venue acquire` first")
    audit_path = directory / "audit.json"
    if not audit_path.is_file():
        raise Refused("AUDIT_ABSENT", "audit.json is absent; run `venue diff` first")
    requirements = _read_json(requirements_path)
    template = _read_json(template_path)
    audit = _read_json(audit_path)

    manuscript = Manuscript(paper_dir)
    if _audit_stale(paper_dir, directory, audit):
        raise Refused(
            "AUDIT_STALE",
            "main.tex or requirements.json changed since `venue diff`; re-run it so the build "
            "answers to the findings that exist now",
        )
    manuscript.verify_digests()
    blockers = audit["summary"]["blocker"]
    if blockers and not _valid_approval(directory):
        raise Refused(
            "PLAN_NOT_APPROVED",
            f"{blockers} blocker finding(s) stand and no approved plan covers them; the operator "
            "approves the exact plan with `venue approve --plan-sha256`",
        )

    klass = requirements["document_class"]
    class_name = template.get("class") or klass["name"]
    family = class_family(class_name)
    notes = []
    if template.get("class") and template["class"] != klass["name"]:
        notes.append(f"the template provides {template['class']}; requirements asked for {klass['name']}")
    if family == "generic" and class_name.lower() not in ("article", "report", "book"):
        notes.append(f"no front-matter mapping for the {class_name} class; the generic \\maketitle layout was used")
    if family != "generic":
        notes.append("authors and affiliations were mapped best-effort from the canonical \\author block; "
                     "check them against the journal's author format before submitting")

    preamble_lines, skipped, dropped = build_preamble(manuscript, family)
    front_report: dict = {"family": family}
    pre_front, front = _front_matter(family, manuscript, front_report)

    # -- body sections in the venue's order ------------------------------------------------
    content = manuscript.content_sections()
    ordered, missing, emitted = [], [], set()
    for section in sorted(requirements["sections"], key=lambda s: s["order"]):
        sid = section["id"]
        if sid == "references":
            ordered.append(("references", section))
        elif sid == BACK_SECTION:
            if any(b["written"] for b in manuscript.section_blocks(BACK_SECTION)):
                ordered.append((BACK_SECTION, section))
                emitted.add(BACK_SECTION)
        elif sid in content and sid not in emitted:
            ordered.append((sid, section))
            emitted.add(sid)
        else:
            missing.append(sid)
    extra_kept = [s for s in content if s not in emitted]
    # sections the venue does not list sit after its own content sections,
    # ahead of the bibliography and the declarations
    cut = next((i for i, item in enumerate(ordered) if item[0] in ("references", BACK_SECTION)), len(ordered))
    ordered[cut:cut] = [(s, None) for s in extra_kept]
    if not any(item[0] == "references" for item in ordered):
        ordered.append(("references", None))
    if BACK_SECTION not in emitted and any(b["written"] for b in manuscript.section_blocks(BACK_SECTION)):
        ordered.append((BACK_SECTION, None))

    style = requirements["reference_style"]
    bst = (style or {}).get("bst") or manuscript.bibliography_style or "plain"
    chunks = []
    for sid, section in ordered:
        if sid == "references":
            chunks.append(f"\\bibliographystyle{{{bst}}}\n\\bibliography{{../../refs}}\n")
            continue
        title = section["title"] if section else None
        heading = _retitle_heading(manuscript.headings.get(sid), title, sid)
        chunks.append(heading + "\n" + manuscript.region(sid).decode("utf-8") + "\n")

    regions = [manuscript.region_for(kind) for kind in ("declarations", "provenance")]
    region_text = "".join(r.decode("utf-8") for r in regions if r)

    document = [
        _document_class_line(class_name, klass["options"]) + "\n",
        f"% Built by `paper_cli.py venue build --slug {slug}`; the text lives in paper/main.tex.\n",
        "\n".join(preamble_lines) + "\n" if preamble_lines else "",
        pre_front,
        "\\begin{document}\n",
        front,
        "\n".join(chunks),
        region_text,
        "\\end{document}\n",
    ]
    output = "".join(document)
    encoded = output.encode("utf-8")

    # the venue file must parse and carry every canonical block byte for byte,
    # proven in memory before a single byte reaches disk
    rebuilt = paper_block.parse(encoded)
    for block in manuscript.blocks:
        pair = rebuilt.pairs.get(block["id"])
        carried = encoded[pair[0]["end"]:pair[1]["start"]] if pair else None
        if carried != block["body"]:
            raise Refused(
                "BLOCK_HAND_EDITED",
                f"{block['id']!r} did not survive the venue assembly byte for byte; nothing was written",
            )
    output_path = directory / "main.tex"
    _atomic_write(output_path, encoded)

    manifest = {
        "schema": 1, "slug": slug, "built_at": clock(),
        "canonical_sha256": manuscript.sha256,
        "requirements_sha256": audit["requirements_sha256"],
        "output_sha256": _sha256_bytes(encoded),
        "document_class": class_name, "family": family,
        "blocks": [{"id": b["id"], "digest": b["digest"]} for b in manuscript.blocks],
        "sections": {"order": [s for s, _ in ordered if s != "references"], "extra_kept": extra_kept,
                     "missing": missing},
        "preamble": {"skipped": skipped, "dropped": dropped},
        "front_matter": front_report, "bibliography_style": bst, "notes": notes,
    }
    _write_json(directory / "build.json", manifest)
    compile_env = (
        {"TEXINPUTS": "./template//:", "BSTINPUTS": "./template//:"}
        if template.get("kind") == "publisher-template" else {}
    )
    return {
        "verb": "build", "slug": slug, "output": _relative_to_repo(paper_dir, output_path),
        "output_sha256": manifest["output_sha256"], "document_class": class_name, "family": family,
        "sections": manifest["sections"], "preamble": manifest["preamble"],
        "front_matter": front_report, "plan_required": blockers > 0, "compile_env": compile_env,
        "notes": notes,
    }


# =====================================================================
# status and list
# =====================================================================
STEPS = ("selected", "requirements", "template", "audited", "planned", "approved", "built", "compiled")


def _summarise(paper_dir: Path, slug: str) -> dict:
    directory = venue_dir(paper_dir, slug)
    venue = _read_json(directory / "venue.json")
    audit = None
    if (directory / "audit.json").is_file():
        try:
            audit = _read_json(directory / "audit.json")
        except (OSError, ValueError):
            audit = None
    done = {
        "selected": True,
        "requirements": (directory / "requirements.json").is_file(),
        "template": (directory / "template.json").is_file(),
        "audited": audit is not None,
        "planned": (directory / "plan.md").is_file(),
        "approved": _valid_approval(directory),
        "built": (directory / "main.tex").is_file() and (directory / "build.json").is_file(),
        "compiled": (directory / "main.pdf").is_file(),
    }
    state = [name for name in STEPS if done[name]][-1]
    stale = bool(audit) and _audit_stale(paper_dir, directory, audit)
    counts = (audit or {}).get("summary", {"blocker": 0, "major": 0, "minor": 0})
    blockers = counts.get("blocker", 0)
    build_stale = False
    if done["built"]:
        try:
            build_stale = _read_json(directory / "build.json").get("canonical_sha256") != (
                _sha256_file(paper_dir / "main.tex") if (paper_dir / "main.tex").is_file() else None)
        except (OSError, ValueError):
            build_stale = True

    if not done["requirements"]:
        action = "agent: read the author guidelines, write requirements.json and run `venue requirements`"
    elif not done["template"]:
        action = "run `venue acquire` (--texlive <class>, or --file <zip|cls> --url <origin>)"
    elif not done["audited"]:
        action = "run `venue diff`"
    elif stale and not done["built"]:
        action = "re-run `venue diff`: the manuscript or the requirements changed since the audit"
    elif blockers and not done["planned"]:
        action = "agent: write the adjustment plan and run `venue plan`"
    elif blockers and not done["approved"]:
        action = "operator: read the plan, then `venue approve --statement ... --plan-sha256 ...`"
    elif not done["built"]:
        action = "run `venue build`"
    elif stale or build_stale:
        action = "re-run `venue diff` and `venue build`: the manuscript changed since the last build"
    elif not done["compiled"]:
        action = f"compile paper/venues/{slug}/main.tex"
    else:
        action = "nothing pending"
    template_kind = None
    if done["template"]:
        try:
            template_kind = _read_json(directory / "template.json").get("kind")
        except (OSError, ValueError):
            template_kind = None
    return {
        "slug": slug, "journal": venue.get("journal", {}).get("name"), "quartile": venue.get("quartile"),
        "state": state, "steps": [{"step": name, "done": done[name]} for name in STEPS],
        "blockers": blockers, "major": counts.get("major", 0), "minor": counts.get("minor", 0),
        "plan_required": bool(blockers), "audit_stale": stale, "build_stale": build_stale,
        "next_action": action,
        "compile_env": {"TEXINPUTS": "./template//:", "BSTINPUTS": "./template//:"}
        if template_kind == "publisher-template" else {},
    }


def status(paper_dir: Path, slug: str) -> dict:
    _require_venue(paper_dir, slug)
    result = _summarise(paper_dir, slug)
    result["verb"] = "status"
    return result


def list_venues(paper_dir: Path) -> dict:
    _require_paper_dir(paper_dir)
    root = paper_dir / "venues"
    venues = []
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and SLUG_RE.match(entry.name) and (entry / "venue.json").is_file():
                summary = _summarise(paper_dir, entry.name)
                venues.append({key: summary[key] for key in
                               ("slug", "journal", "quartile", "state", "blockers", "next_action")})
    return {"verb": "list", "venues": venues}
