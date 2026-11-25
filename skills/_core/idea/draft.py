"""Step 6, draft: the base idea handed to ``/plausibility``.

:func:`compose` writes a deterministic draft of at least two sentences (the
problem, then the proposal, then the background the evidence supports) from
the chosen topics, the experience and the interests; it states nothing the
brief does not hold. :func:`check` scores a text with the same prompt gate the
Phase 2 card runs (``command_center/prompt_gate.py``, the ``plausibility``
contract: at least 15 words and two sentences naming a problem and a
proposal). :func:`approve` refuses while the gate fails, and :func:`handoff`
refuses until the draft is approved, then answers ``/plausibility <draft>``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import brief as _brief
from ..command_center import prompt_gate

SKILL = "plausibility"
COMMAND = "/plausibility"


def _join(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def check(text: str) -> dict[str, Any]:
    """The prompt gate's verdict on ``text`` as ``/plausibility``'s input:
    ``{"ok", "score", "missing"}`` (``missing`` lists what the gate asks for)."""
    result = prompt_gate.check(SKILL, str(text or ""))
    return {"ok": result["verdict"] == "pass", "score": result["score"],
            "missing": [issue["message"] for issue in result["issues"]]}


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def store(root: Path | str, text: str) -> dict[str, Any]:
    """Record ``text`` as the draft with its gate result; a new text is never approved."""
    clean = _clean(text)
    if not clean:
        raise _brief.IdeaError("DRAFT_EMPTY", "the draft is empty")
    if len(clean) > _brief.MAX_TEXT:
        raise _brief.IdeaError("DRAFT_TOO_LONG", f"the draft is longer than {_brief.MAX_TEXT} characters")
    b = _brief.load(root)
    data = {"text": clean, "source_topics": list(b["chosen"].get("topic_ids") or []), "gate": check(clean),
            "approved": False, "approved_at": None}
    return _brief.record(root, "draft", data)["draft"]


def _evidence(topics: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    return [e for t in topics for e in (t.get("evidence") or [])
            if isinstance(e, dict) and str(e.get("source", "")).startswith(prefix)]


def compose_text(b: dict[str, Any]) -> str:
    """The deterministic draft for brief ``b`` (see the module doc)."""
    ids = list(b["chosen"].get("topic_ids") or [])
    chosen = [t for t in b["topics"] if isinstance(t, dict) and t.get("id") in ids]
    if not chosen:
        if b["topics"]:
            raise _brief.IdeaError("TOPIC_MISSING", "pick a topic first (e.g. `smith idea topics --choose t1`)")
        raise _brief.IdeaError("TOPICS_ABSENT", "propose topics first (`smith idea topics --propose`)")
    interests, experience = b["interests"], b["experience"]
    subject = _join([t["title"] for t in chosen])
    keywords = _brief.words([k for t in chosen for k in t.get("keywords") or []])[:4]
    where = f" in {interests['domain']}" if interests.get("domain") and interests["domain"] not in subject else ""
    counts = [(e, t) for t in chosen for e in _evidence([t], "openalex") if isinstance(e.get("count"), int)]
    if counts:
        fewest, topic = min(counts, key=lambda pair: pair[0]["count"])
        detail = str(fewest.get("detail") or "")
        since = detail.split("since ", 1)[1].split(" ", 1)[0] if "since " in detail else "recent years"
        about = "" if len(chosen) == 1 else f" on {topic['title']}"
        if "possible gap" in detail:
            problem = (f"Research on {subject}{where} shows a clear gap: OpenAlex lists only {fewest['count']} "
                       f"works{about} since {since}, so the problem is still poorly covered.")
        else:
            problem = (f"Research on {subject}{where} is active ({fewest['count']} works{about} since {since} in "
                       f"OpenAlex), yet the problem of how {_join(keywords)} fit together still lacks a clear "
                       "answer.")
    else:
        problem = (f"Research on {subject}{where} still lacks a clear framing that connects {_join(keywords)}, "
                   "and that limitation is the problem this idea addresses.")
    methods = experience.get("methods") or []
    proposal = (f"I propose an approach that uses {_join(methods[:2])} to address {subject}" if methods
                else f"I propose an approach to {subject} that combines {_join(keywords)}")
    if experience.get("resources"):
        proposal += f", working with {_join(experience['resources'][:2])}"
    if experience.get("time"):
        proposal += f", within {experience['time']}"
    sentences = [problem, proposal + "."]
    bank = _evidence(chosen, "bank:")
    if bank and bank[0].get("count"):
        server = str(bank[0]["source"]).split(":", 1)[1]
        sentences.append(f"As background, not state of the art, the {server} bank holds "
                         f"{bank[0]['count']} related items.")
    own = {str(p.get("name")) for p in b["profile"].get("topics") or [] if isinstance(p, dict)}
    names = _brief.words([k for t in chosen if _evidence([t], "profile") for k in t.get("keywords") or []
                          if k in own])
    if names:
        sentences.append(f"It builds on my own published work on {_join(names[:2])}.")
    if interests.get("admired_paper"):
        sentences.append(f"It takes inspiration from \"{interests['admired_paper']}\".")
    note = b["chosen"].get("note")
    if note:
        sentences.append(f"Focus: {note.rstrip('.')}.")
    return " ".join(sentences)


def compose(root: Path | str) -> dict[str, Any]:
    """Compose the draft from the brief, record it (unapproved, with its gate
    result) and return the brief's ``draft``."""
    return store(root, compose_text(_brief.load(root)))


def approve(root: Path | str) -> dict[str, Any]:
    """Approve the recorded draft; refuses when there is none or the gate fails."""
    b = _brief.load(root)
    draft = b["draft"]
    text = _clean(draft.get("text"))
    if not text:
        raise _brief.IdeaError("DRAFT_ABSENT", "there is no draft to approve; compose or write one first")
    gate = check(text)
    if not gate["ok"]:
        raise _brief.IdeaError("DRAFT_GATE_FAILED",
                               f"the prompt gate refuses the draft (score {gate['score']}): "
                               + " ".join(gate["missing"]))
    data = {**draft, "text": text, "gate": gate, "approved": True, "approved_at": _brief.now()}
    return _brief.record(root, "draft", data)["draft"]


def handoff(root: Path | str) -> str:
    """``/plausibility <draft>`` for the approved draft; refuses until approved."""
    draft = _brief.load(root)["draft"]
    if not draft.get("approved"):
        raise _brief.IdeaError("DRAFT_NOT_APPROVED", "approve the draft first (`smith idea approve`)")
    return f"{COMMAND} {_clean(draft.get('text'))}"


__all__ = ["COMMAND", "approve", "check", "compose", "compose_text", "handoff", "store"]
