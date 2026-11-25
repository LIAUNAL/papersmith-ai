"""Step 2, profile: who the author is and what their published work covers.

The author is found in OpenAlex by ORCID iD (``/authors/orcid:<id>``), by
OpenAlex author id (``/authors/A...``) or by name (``/authors?search=``). A
Google Scholar link is used only to read a name out of it (the ``mauthors``
or ``author:`` query of a Scholar search link): smith never scrapes Scholar,
and a profile link (``citations?user=...``) carries no name, so the user is
asked for one. The author's topics are OpenAlex's own counts of their works
per topic (``topics``, or the older ``x_concepts``).

Every request goes through :data:`FETCH` (``FETCH(url) -> dict``; tests
replace it, or pass ``fetch=``). The operator's OpenAlex key, when configured
(``skills/_core/api_keys.py``, the same reader ``citations_cli.py`` uses), is
added by the default fetcher only, so no stored URL or message carries it.
Offline or unreachable answers ``{"source": "none", "reason": ...}``; nothing
here raises.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

OPENALEX = "https://api.openalex.org"
HTTP_TIMEOUT = 15
MAX_TOPICS = 8
_ORCID_RE = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dXx])")
_OPENALEX_RE = re.compile(r"(?:^|[/\s:])(A\d{4,})\b", re.IGNORECASE)


def openalex_key() -> str | None:
    """The operator's OpenAlex key or ``None``; loads ``api_keys.py`` by path
    under the shared module name every consumer uses. Never raises."""
    name = "papersmith_api_keys"
    try:
        module = sys.modules.get(name)
        if module is None:
            source = Path(__file__).resolve().parents[1] / "api_keys.py"
            spec = importlib.util.spec_from_file_location(name, source)
            module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)  # type: ignore[union-attr]
            except BaseException:
                sys.modules.pop(name, None)
                raise
        return module.read("openalex")
    except Exception:  # noqa: BLE001
        return None


def _fetch_json(url: str) -> Any:
    """GET ``url`` from OpenAlex (with the operator's key when configured)."""
    key = openalex_key()
    if key:
        url += ("&" if "?" in url else "?") + "api_key=" + urllib.parse.quote(key, safe="")
    request = urllib.request.Request(url, headers={"User-Agent": "papersmith-ai"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.load(response)


#: The seam every OpenAlex request goes through: ``FETCH(url) -> dict``.
FETCH: Callable[[str], Any] = _fetch_json


def openalex_url(path: str, params: dict[str, Any] | None = None) -> str:
    """The public OpenAlex URL (never with a key) of ``path`` and ``params``."""
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    return f"{OPENALEX}{path}" + (f"?{query}" if query else "")


def openalex_get(path: str, params: dict[str, Any] | None = None, *,
                 fetch: Callable[[str], Any] | None = None) -> Any:
    """One OpenAlex request through ``fetch`` (default :data:`FETCH`); raises on failure."""
    return (fetch or FETCH)(openalex_url(path, params))


def _reason(prefix: str, exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    detail = f"HTTP {code}" if isinstance(code, int) else (getattr(exc, "reason", None) or exc)
    return " ".join(f"{prefix}: {detail}".split())[:240]


# --------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------
def normalize_orcid(value: Any) -> str | None:
    match = _ORCID_RE.search(str(value or ""))
    return match.group(1).upper() if match else None


def normalize_openalex(value: Any) -> str | None:
    match = _OPENALEX_RE.search(str(value or "").strip())
    return match.group(1).upper() if match else None


def scholar_name(url: Any) -> str | None:
    """The author name a Google Scholar link carries (``mauthors=`` of an
    author search, ``q=author:"..."`` of a search), or ``None``."""
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return None
    if "scholar.google" not in parsed.netloc:
        return None
    query = parse_qs(parsed.query)
    for key in ("mauthors", "q", "as_sauthors"):
        for value in query.get(key, []):
            text = re.sub(r"\bauthor:", " ", value)
            text = " ".join(text.replace('"', " ").replace("'", " ").replace("+", " ").split())
            if text and not text.lower().startswith(("http", "label:")):
                return text
    return None


def identify(text: Any) -> dict[str, str]:
    """What one free answer names: ``{"orcid"|"openalex_author"|"scholar_url"|"name": text}``."""
    raw = " ".join(str(text or "").split())
    if not raw:
        return {}
    if "scholar.google" in raw:
        return {"scholar_url": raw}
    if (orcid := normalize_orcid(raw)) is not None:
        return {"orcid": orcid}
    if re.fullmatch(r"(https?://)?(api\.)?openalex\.org/(authors/)?A\d{4,}/?|A\d{4,}", raw, re.IGNORECASE):
        return {"openalex_author": normalize_openalex(raw) or raw}
    return {"name": raw}


# --------------------------------------------------------------------------
# Lookup
# --------------------------------------------------------------------------
def _short_id(value: Any, prefix: str) -> str | None:
    text = str(value or "")
    return text.rsplit("/", 1)[-1] if text.startswith(prefix) else (text or None)


def _topics(author: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for topic in author.get("topics") or []:
        if isinstance(topic, dict) and topic.get("display_name"):
            count = topic.get("count")
            found.append({"name": str(topic["display_name"]), "count": count if isinstance(count, int) else 0})
    if not found:  # older records: concepts with a score instead of a count
        for concept in author.get("x_concepts") or []:
            if isinstance(concept, dict) and concept.get("display_name") and concept.get("level", 1) >= 1:
                score = concept.get("score")
                found.append({"name": str(concept["display_name"]),
                              "count": int(round(score)) if isinstance(score, (int, float)) else 0})
    found.sort(key=lambda t: -t["count"])
    return found[:MAX_TOPICS]


def _empty(orcid: str | None, openalex_author: str | None, scholar_url: str | None) -> dict[str, Any]:
    return {"orcid": orcid, "openalex_author": openalex_author, "scholar_url": scholar_url, "display_name": None,
            "works_count": None, "topics": [], "source": "none", "reason": None}


def lookup(orcid: str | None = None, openalex_author: str | None = None, scholar_url: str | None = None,
           name: str | None = None, *, fetch: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """The author's profile from OpenAlex, in the brief's ``profile`` shape.
    Precedence: OpenAlex id, ORCID, then a name (given, or read from the
    Scholar link). Never raises."""
    scholar_url = " ".join(str(scholar_url).split()) if scholar_url else None
    result = _empty(None, None, scholar_url)
    if orcid:
        result["orcid"] = normalize_orcid(orcid)
        if result["orcid"] is None:
            result["reason"] = f"{orcid!r} is not an ORCID iD (0000-0000-0000-0000)"
            return result
    if openalex_author:
        result["openalex_author"] = normalize_openalex(openalex_author)
        if result["openalex_author"] is None:
            result["reason"] = f"{openalex_author!r} is not an OpenAlex author id (A followed by digits)"
            return result
    name = " ".join(str(name).split()) if name else None
    if not name and scholar_url:
        name = scholar_name(scholar_url)
    try:
        if result["openalex_author"]:
            author = openalex_get(f"/authors/{result['openalex_author']}", fetch=fetch)
        elif result["orcid"]:
            author = openalex_get(f"/authors/orcid:{result['orcid']}", fetch=fetch)
        elif name:
            found = openalex_get("/authors", {"search": name, "per-page": 5}, fetch=fetch)
            authors = found.get("results") if isinstance(found, dict) else None
            if not authors:
                result["reason"] = f"OpenAlex has no author named {name!r}"
                return result
            author = authors[0]
        elif scholar_url:
            result["reason"] = ("the Google Scholar link carries no author name (smith never scrapes Scholar): "
                                "give your name, ORCID iD or OpenAlex author id")
            return result
        else:
            result["reason"] = "no ORCID iD, OpenAlex author, Google Scholar link or name was given"
            return result
    except Exception as exc:  # noqa: BLE001 - offline must never reach the user as a traceback
        result["reason"] = _reason("OpenAlex could not be reached", exc)
        return result
    if not isinstance(author, dict) or not author.get("id"):
        result["reason"] = "OpenAlex answered without an author record"
        return result
    works = author.get("works_count")
    result.update({
        "openalex_author": _short_id(author.get("id"), "https://openalex.org/"),
        "orcid": result["orcid"] or normalize_orcid(author.get("orcid")),
        "display_name": str(author.get("display_name") or "") or None,
        "works_count": works if isinstance(works, int) else None,
        "topics": _topics(author), "source": "openalex", "reason": None,
    })
    return result


__all__ = ["FETCH", "OPENALEX", "identify", "lookup", "normalize_openalex", "normalize_orcid", "openalex_get",
           "openalex_key", "openalex_url", "scholar_name"]
