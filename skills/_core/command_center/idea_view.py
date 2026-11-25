"""The idea-shaping phase in the dashboard (idea-shaping S6): the Idea tab's adapters.

Thin adapters over the engine in ``skills/_core/idea/`` (the same functions
``smith idea`` calls), loaded from the tree this dashboard runs from, like
``paper_type_view`` loads ``paper_types``. Every adapter answers the tab's
whole state, :func:`view`, plus the step's own ``result``:

* ``view(root)``: the brief, the bank choices (banco-lia and the workspace's
  other MCP servers), the experience levels, and whether the draft is approved
  (``ready``) with its ``/plausibility <draft>`` hand-off line.
* ``bank``, ``profile``, ``experience``, ``interests``, ``propose``,
  ``choose``, ``draft`` and ``approve``: one step each, recorded in
  ``.papersmith/idea_brief.json``.

Every field the operator sends is type-checked first: text where text is
expected, text or a list of texts for the list fields; anything else refuses
``FIELD_TYPE`` and nothing is written (a number or an object is never
coerced into text). A refusal of the engine raises :class:`IdeaError` (``code``, ``message``);
:func:`status_of` maps it to the HTTP status the server answers. An
unreachable bank or OpenAlex is not a refusal: the engine answers it in the
step's data (``available: False`` / ``source: "none"`` with the reason), and
that passes through unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..idea import bank, brief, draft, profile, topics

IdeaError = brief.IdeaError

#: Refusals about a damaged file on disk (the operator must fix it) answer 409;
#: every other refusal is a 422 about the request.
CONFLICT_CODES = frozenset({"BRIEF_UNREADABLE", "MCP_CONFIG_UNREADABLE"})
BANK_ACTIONS = ("list", "probe", "choose", "add", "search")
DRAFT_ACTIONS = ("compose", "text", "check")


def status_of(exc: IdeaError) -> int:
    return 409 if exc.code in CONFLICT_CODES else 422


def refusal(exc: IdeaError) -> dict[str, Any]:
    return {"ok": False, "code": exc.code, "message": exc.message, "error": exc.message}


def _payload(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _typed(data: dict[str, Any], texts: tuple[str, ...] = (), lists: tuple[str, ...] = ()) -> dict[str, Any]:
    """``data`` after checking that each of ``texts`` is text (or null) and each
    of ``lists`` is text or a list of texts (or null); refuses ``FIELD_TYPE``."""
    for key in texts:
        value = data.get(key)
        if value is not None and not isinstance(value, str):
            raise IdeaError("FIELD_TYPE", f"{key} must be text")
    for key in lists:
        value = data.get(key)
        if value is None or isinstance(value, str):
            continue
        if not isinstance(value, list) or not all(isinstance(entry, str) for entry in value):
            raise IdeaError("FIELD_TYPE", f"{key} must be text or a list of texts")
    return data


def _text(value: Any) -> str | None:
    clean = " ".join(str(value).split()) if value is not None else ""
    return clean or None


def view(root: Path, result: Any = None) -> dict[str, Any]:
    """The Idea tab's state. Raises :class:`IdeaError` for an unreadable brief."""
    root = Path(root)
    b = brief.load(root)
    ready = bool(b["draft"].get("approved"))
    out: dict[str, Any] = {
        "ok": True, "brief": b, "choices": bank.choices(root), "levels": list(brief.LEVELS),
        "ready": ready, "handoff": draft.handoff(root) if ready else None,
    }
    if result is not None:
        out["result"] = result
    return out


# --------------------------------------------------------------------------
# Step 1: sources
# --------------------------------------------------------------------------
def bank_step(root: Path, payload: Any) -> dict[str, Any]:
    """``{"action": "list"|"probe"|"choose"|"add"|"search", ...}``.

    ``probe`` checks a server without recording it; ``choose`` records the
    choice (probing a bank); ``add`` writes a new server to ``.mcp.json`` and
    chooses it; ``search`` queries the chosen compatible bank."""
    data = _typed(_payload(payload), ("action", "server", "choice", "name", "command", "url", "query"))
    action = data.get("action") or "list"
    if action not in BANK_ACTIONS:
        raise IdeaError("ACTION_UNKNOWN", f"unknown bank action {action!r}; expected one of "
                                          f"{', '.join(BANK_ACTIONS)}")
    root = Path(root)
    if action == "list":
        result: Any = bank.choices(root)
    elif action == "probe":
        server = _text(data.get("server"))
        if not server:
            raise IdeaError("SERVER_MISSING", "name the server to probe")
        result = {"server": server, **bank.probe(root, server)}
    elif action == "choose":
        result = bank.choose(root, data.get("choice") or "", _text(data.get("server")))
    elif action == "add":
        added = bank.add_server(root, data.get("name") or "", command=_text(data.get("command")),
                                url=_text(data.get("url")))
        result = {"added": added, "bank": bank.choose(root, "other", added["server"])}
    else:
        query = _text(data.get("query"))
        if not query:
            raise IdeaError("QUERY_MISSING", "give the words to search the bank for")
        result = bank.search(root, query)
    return view(root, result)


# --------------------------------------------------------------------------
# Step 2: profile
# --------------------------------------------------------------------------
def profile_step(root: Path, payload: Any) -> dict[str, Any]:
    """``{"text": <ORCID, OpenAlex id, Scholar link or name>}`` (classified by
    ``profile.identify``), or the explicit ``orcid`` / ``openalex_author`` /
    ``scholar_url`` / ``name`` fields. A Scholar link without a name in it
    takes the ``name`` given beside it. Offline answers the reason."""
    data = _typed(_payload(payload), ("text", "orcid", "openalex_author", "scholar_url", "name"))
    ids: dict[str, Any] = dict(profile.identify(data.get("text"))) if _text(data.get("text")) else {}
    for key in ("orcid", "openalex_author", "scholar_url", "name"):
        if _text(data.get(key)) and key not in ids:
            ids[key] = _text(data.get(key))
    if not ids:
        raise IdeaError("PROFILE_MISSING", "give an ORCID iD, an OpenAlex author id, a Google Scholar link or "
                                           "your name")
    found = profile.lookup(**ids)
    return view(root, brief.record(root, "profile", found)["profile"])


# --------------------------------------------------------------------------
# Steps 3 and 4: experience, interests
# --------------------------------------------------------------------------
def _fields(data: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    return {key: data[key] for key in names if key in data}


def experience_step(root: Path, payload: Any) -> dict[str, Any]:
    fields = _fields(_typed(_payload(payload), ("level", "time"), ("methods", "resources")),
                     ("level", "methods", "resources", "time"))
    if "level" in fields and not _text(fields["level"]):
        fields["level"] = None
    b = brief.record(root, "experience", fields) if fields else brief.load(root)
    return view(root, b["experience"])


def interests_step(root: Path, payload: Any) -> dict[str, Any]:
    fields = _fields(_typed(_payload(payload), ("domain", "admired_paper"), ("keywords",)),
                     ("keywords", "domain", "admired_paper"))
    b = brief.record(root, "interests", fields) if fields else brief.load(root)
    return view(root, b["interests"])


# --------------------------------------------------------------------------
# Step 5: topics
# --------------------------------------------------------------------------
def propose(root: Path, payload: Any) -> dict[str, Any]:
    data = _payload(payload)
    try:
        n = int(data.get("n") or topics.DEFAULT_N)
    except (TypeError, ValueError):
        raise IdeaError("TOPICS_N_INVALID", "n must be a whole number of topics") from None
    return view(root, topics.propose(root, n))


def choose(root: Path, payload: Any) -> dict[str, Any]:
    data = _typed(_payload(payload), ("note",), ("topic_ids",))
    return view(root, topics.choose(root, data.get("topic_ids"), _text(data.get("note"))))


# --------------------------------------------------------------------------
# Step 6: draft
# --------------------------------------------------------------------------
def draft_step(root: Path, payload: Any) -> dict[str, Any]:
    """``{"action": "compose"}`` composes and records a draft; ``{"action":
    "text", "text"}`` records the operator's text; ``{"action": "check",
    "text"}`` only scores the text (or the recorded draft) with the prompt gate."""
    data = _typed(_payload(payload), ("action", "text"))
    action = data.get("action") or "compose"
    if action not in DRAFT_ACTIONS:
        raise IdeaError("ACTION_UNKNOWN", f"unknown draft action {action!r}; expected one of "
                                          f"{', '.join(DRAFT_ACTIONS)}")
    if action == "compose":
        result: Any = draft.compose(root)
    elif action == "text":
        result = draft.store(root, data.get("text") or "")
    else:
        text = data["text"] if "text" in data else brief.load(root)["draft"].get("text", "")
        result = {"text": " ".join(str(text or "").split()), "gate": draft.check(str(text or ""))}
    return view(root, result)


def approve(root: Path, payload: Any = None) -> dict[str, Any]:
    """Approve the recorded draft (refused while the gate fails)."""
    return view(root, draft.approve(root))


__all__ = ["BANK_ACTIONS", "CONFLICT_CODES", "DRAFT_ACTIONS", "IdeaError", "approve", "bank_step", "choose",
           "draft_step", "experience_step", "interests_step", "profile_step", "propose", "refusal", "status_of",
           "view"]
