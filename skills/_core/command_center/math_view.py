"""The math panel's data: the paper's own LaTeX, condensed into cards.

Read-only. Sources, first match wins:

1. the latest proposal revision, ``proposals/research-concept-<slug>-rNN.md``:
   every display block (``$$`` alone on its line, the proposal's canonical
   form) with its ``\\tag{N}``, the heading it sits under and the first sentence
   of the paragraph after it as its "connection"; the matching
   ``proposals/research-concept-<slug>-rNN.sky.json`` overlay fills the novelty
   card (``sun``, ``novelty``, ``problem``, ``contribution`` planets);
2. ``.papersmith/model_spec.json``, normalised from its ``core_equations`` /
   ``optimization_problems`` / ``equations``;
3. nothing: an empty panel that says so, named after ``papersmith.yaml``.

The panel never invents mathematics: an empty source yields no equation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import model_spec

MAX_BYTES = 2 * 1024 * 1024
MAX_EQUATIONS = 40
TEXT_MAX = 600

#: A managed revision, with or without a slug: research-concept-r44.md and
#: research-concept-eeg-r07.md both are, as Phase 4 reads them.
_REVISION = re.compile(r"^research-concept-(?:.+-)?r(\d+)\.md$")
_TAG = re.compile(r"\\tag\{([^{}]*)\}")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^(```|~~~)")


def _first_sentence(text: str) -> str:
    """Up to the first sentence end that is not inside parentheses, so a
    citation like "(Ec. 1)" never cuts a sentence in two."""
    text = " ".join(str(text or "").split())
    depth = 0
    for index, char in enumerate(text):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char in ".!?" and depth <= 0 and (index + 1 == len(text) or text[index + 1] == " "):
            return text[:index + 1][:TEXT_MAX]
    return text[:TEXT_MAX]


def _read(path: Path, root: Path | None = None) -> str | None:
    """Bounded read; with ``root``, only a file that resolves inside it, so a
    symlinked proposal never serves bytes from outside the workspace."""
    try:
        if root is not None and not path.resolve().is_relative_to(root):
            return None
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _yaml_field(root: Path, key: str) -> str:
    text = _read(root / "papersmith.yaml") or ""
    match = re.search(rf"^{key}:\s*(.+)$", text, re.M)
    return match.group(1).strip().strip("'\"") if match else ""


# --------------------------------------------------------------------------
# proposals
# --------------------------------------------------------------------------
def _latest_proposal(root: Path) -> Path | None:
    folder = root / "proposals"
    if not folder.is_dir() or not folder.resolve().is_relative_to(root):
        return None
    ranked = []
    for path in folder.iterdir():
        match = _REVISION.match(path.name)
        # A revision resolving outside the workspace is not this paper's.
        if match and path.is_file() and path.resolve().is_relative_to(root):
            ranked.append((int(match.group(1)), path.name, path))
    return max(ranked)[2] if ranked else None


def _paragraph_after(lines: list[str], start: int) -> str:
    index = start
    while index < len(lines) and not lines[index].strip():
        index += 1
    paragraph = []
    while index < len(lines):
        line = lines[index].strip()
        if not line or line == "$$" or _HEADING.match(line):
            break
        paragraph.append(line)
        index += 1
    return " ".join(paragraph)


def equations_from_markdown(text: str) -> list[dict[str, Any]]:
    """The first ``MAX_EQUATIONS`` closed ``$$`` display blocks, in order, with
    their context."""
    return [equation for equation, _ in _display_equations(text)][:MAX_EQUATIONS]


def tagged_equation_count(text: str) -> int:
    """How many closed ``$$`` display blocks carry an explicit ``\\tag{N}``:
    the proposal's canonical numbered equations (Phase 4's mathematics step),
    up to ``MAX_EQUATIONS`` of them; untagged blocks never use up that cap."""
    return sum(1 for _, tagged in _display_equations(text) if tagged)


def _display_equations(text: str) -> list[tuple[dict[str, Any], bool]]:
    lines = text.splitlines()
    heading = ""
    found: list[tuple[dict[str, Any], bool]] = []
    index = 0
    fence: str | None = None
    tagged = 0
    while index < len(lines) and tagged < MAX_EQUATIONS:
        line = lines[index].strip()
        fence_match = _FENCE.match(line)
        if fence_match and (fence is None or fence_match.group(1) == fence):
            # A code block shows LaTeX, it does not state the paper's maths.
            fence = None if fence else fence_match.group(1)
            index += 1
            continue
        if fence:
            index += 1
            continue
        heading_match = _HEADING.match(line)
        if heading_match:
            heading = heading_match.group(2)
        if line != "$$":
            index += 1
            continue
        end = next((j for j in range(index + 1, len(lines)) if lines[j].strip() == "$$"), None)
        if end is None:
            break
        body = "\n".join(lines[index + 1:end]).strip()
        tag_match = _TAG.search(body)
        latex = _TAG.sub("", body).strip()
        if latex:
            found.append(({
                "id": f"eq-{len(found) + 1}",
                "tag": tag_match.group(1).strip() if tag_match else str(len(found) + 1),
                "heading": heading,
                "latex": latex,
                "connection": _first_sentence(_paragraph_after(lines, end + 1)),
                "variables": [],
            }, tag_match is not None))
            tagged += tag_match is not None
        index = end + 1
    return found


def _novelty_from_sky(sky: Any, fallback_title: str) -> dict[str, Any]:
    planets = ((sky or {}).get("system") or {}).get("planets") if isinstance(sky, dict) else None
    planets = [p for p in planets or [] if isinstance(p, dict)]

    def first(slot: str, field: str = "label") -> str:
        for planet in planets:
            if planet.get("slot") == slot and isinstance(planet.get(field), str):
                return planet[field][:TEXT_MAX]
        return ""

    title = ((sky or {}).get("system") or {}).get("title") if isinstance(sky, dict) else ""
    return {
        "central_idea": first("sun") or (title if isinstance(title, str) else "") or fallback_title,
        "novelty": first("novelty"),
        "novelty_detail": first("novelty", "detail"),
        "problem": first("problem"),
        "problem_detail": first("problem", "detail"),
        "contributions": [p["label"][:TEXT_MAX] for p in planets
                          if p.get("slot") == "contribution" and isinstance(p.get("label"), str)],
    }


# --------------------------------------------------------------------------
# model specifications
# --------------------------------------------------------------------------
def _variables(raw: Any) -> list[dict[str, str]]:
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            out.append({"symbol": str(item.get("sym") or item.get("symbol") or "")[:120],
                        "meaning": str(item.get("desc") or item.get("meaning") or "")[:TEXT_MAX]})
    return out


def equations_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    model = spec.get("mathematical_model") if isinstance(spec.get("mathematical_model"), dict) else {}
    raw = []
    for key in ("core_equations", "equations", "optimization_problems"):
        value = model.get(key)
        raw.extend(item for item in (value if isinstance(value, list) else []) if isinstance(item, dict))
    found = []
    for item in raw[:MAX_EQUATIONS]:
        latex = item.get("latex")
        if not isinstance(latex, str) or not latex.strip():
            continue
        number = str(item.get("number") or "").strip("() ")
        found.append({
            "id": str(item.get("id") or f"eq-{len(found) + 1}"),
            "tag": number or str(len(found) + 1),
            "heading": str(item.get("name") or "")[:TEXT_MAX],
            "latex": latex.strip(),
            "connection": _first_sentence(item.get("description") or ""),
            "variables": _variables(item.get("variables")),
        })
    return found


def _central_problem(novelty: dict[str, Any]) -> str:
    """The problem tree's central problem, the proposal's one problem text."""
    tree = novelty.get("problem_tree") if isinstance(novelty.get("problem_tree"), dict) else {}
    central = tree.get("central") if isinstance(tree.get("central"), dict) else {}
    text = central.get("text")
    return text.strip()[:TEXT_MAX] if isinstance(text, str) else ""


def _novelty_from_spec(spec: dict[str, Any], fallback_title: str) -> dict[str, Any]:
    novelty = spec.get("novelty") if isinstance(spec.get("novelty"), dict) else {}
    pillars = [p for p in novelty.get("pillars") or [] if isinstance(p, dict)]
    return {
        "central_idea": str(spec.get("title") or fallback_title)[:TEXT_MAX],
        "novelty": str(pillars[0].get("name") or "")[:TEXT_MAX] if pillars else "",
        "novelty_detail": str(pillars[0].get("summary") or "")[:TEXT_MAX] if pillars else "",
        "problem": _central_problem(novelty) or _first_sentence(novelty.get("problem_statement") or ""),
        "problem_detail": "",
        "contributions": [str(p.get("name") or "")[:TEXT_MAX] for p in pillars[1:] if p.get("name")],
    }


def _valid_spec_file(path: Path) -> bool:
    try:
        return isinstance(json.loads(_read(path) or ""), dict)
    except ValueError:
        return False


# --------------------------------------------------------------------------
# the view
# --------------------------------------------------------------------------
def build(root: Path | str) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    title = _yaml_field(root, "title") or root.name
    topic = _yaml_field(root, "topic")

    proposal = _latest_proposal(root)
    if proposal is not None:
        text = _read(proposal, root) or ""
        sky_path = proposal.with_suffix(".sky.json")
        try:
            sky = json.loads(_read(sky_path, root) or "null")
        except ValueError:
            sky = None
        equations = equations_from_markdown(text)
        novelty = _novelty_from_sky(sky, title)
        current = model_spec.get_model_specification(root)
        spec_novelty = current.get("novelty") if isinstance(current, dict) else None
        central = _central_problem(spec_novelty) if isinstance(spec_novelty, dict) else ""
        if central:
            novelty = {**novelty, "problem": central, "problem_detail": ""}
        source = f"proposal:{proposal.relative_to(root).as_posix()}"
        lema = novelty["novelty_detail"] or novelty["novelty"] or topic
    else:
        spec_file = root / ".papersmith" / "model_spec.json"
        spec = model_spec.get_model_specification(root)
        spec = spec if isinstance(spec, dict) else {}
        equations = equations_from_spec(spec)
        novelty = _novelty_from_spec(spec, title)
        if _valid_spec_file(spec_file):
            source = "model_spec:.papersmith/model_spec.json"
        else:
            source = "none"
            novelty = {"central_idea": title, "novelty": "", "novelty_detail": "", "problem": "",
                       "problem_detail": "", "contributions": []}
        lema = _first_sentence(spec.get("executive_summary") or "") if source != "none" else topic

    if not equations and source.startswith("proposal:"):
        lema = lema or topic
    novelty["key_equation"] = equations[0] if equations else None
    return {
        "title": title,
        "topic": topic,
        "source": source,
        "lema": lema or topic or title,
        "novelty": novelty,
        "equations": equations,
    }


__all__ = ["build", "equations_from_markdown", "equations_from_spec", "tagged_equation_count"]
