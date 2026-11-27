"""The headless half of the prompt gate, for the dashboard's phase cards.

A prompt that failed the deterministic check (``prompt_gate.check``) is handed
to the ``prompt-reviewer`` agent through the tutors' headless runner
(``tutor.run_agent``: ``claude -p`` with a JSON schema, else ``agy``, else
``pi``). It answers one JSON object: ``improve`` with an improved prompt that
keeps every requirement of the original, or ``clarify`` with up to four
questions; called again with the operator's answers, it composes the prompt.

Read only: nothing here writes the workspace or sends anything to an agent
terminal. The operator launches from the card, and what the card launches
carries ``prompt_gate.APPROVED_MARKER`` so the in-agent gate lets it through.

The card shows the reviewer's answer, so it is written in the board language
the request names (``language``, English when absent, as the board's own
default is English), never in whatever language the operator typed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import phase_actions, prompt_gate, tutor

MAX_TEXT = 20000
MAX_QUESTIONS = 4
MAX_OPTIONS = 4
SKILL_DOC = Path("skills") / "prompt-gate" / "SKILL.md"
AGENT_DOC = Path(".claude") / "agents" / "prompt-reviewer.md"
#: Where the kit keeps the doctrine relative to this package, for a workspace
#: that is missing its copy (``skills/_core/command_center`` → ``skills/``).
_KIT_SKILLS = Path(__file__).resolve().parents[2]

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "verdict": {"type": "string", "enum": ["improve", "clarify"]},
        "issues": {"type": "array", "items": {"type": "string"}},
        "improved_prompt": {"type": "string"},
        "preserved_requirements": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "question": {"type": "string"},
                           "options": {"type": "array", "items": {"type": "string"}}},
            "required": ["id", "question", "options"]}},
    },
    "required": ["reply", "verdict", "issues", "improved_prompt", "preserved_requirements", "questions"],
}

FALLBACK = ("# Prompt Gate\n\nReview a phase prompt that failed the deterministic check. Return improve "
            "with a restructured prompt (task, object and scope, constraints, expected outcome) that keeps "
            "every requirement of the original and invents nothing, or clarify with 1 to 4 questions of 2 to "
            "4 options when a fact only the operator knows is missing.")

HEADLESS = ("You run headless inside the dashboard: the operator reads your JSON in the phase card and "
            "decides there. Return exactly one JSON object in the shape of the skill's Headless reviewer "
            "contract. The dashboard shows every field in the phase card: write `reply`, `issues`, "
            "`questions` and the improved prompt in the board language the request names (`Board language`), "
            "English when it names none, whatever language the operator wrote in; keep every requirement of "
            "the original, translated, never dropped. With answers, return "
            "`improve` and the composed prompt; return `clarify` again only if an answer still leaves a gap "
            "the skill cannot start without.")


class ReviewInvalid(ValueError):
    """The request names no skill or carries text out of bounds."""


def approved(text: str) -> str:
    """``text`` as the card launches it after the operator's approval."""
    return f"{prompt_gate.strip_marker(text)} {prompt_gate.APPROVED_MARKER}"


def _read(root: Path, rel: Path) -> str:
    for base in (root, _KIT_SKILLS.parent):
        try:
            return (base / rel).read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


def system_prompt(root: Path) -> str:
    skill = _read(root, SKILL_DOC) or FALLBACK
    agent = _read(root, AGENT_DOC)
    parts = [part for part in (agent, skill) if part]
    # The board language closes the prompt: in this headless turn it outranks "reply in the human's language".
    return ("\n\n---\n\n".join(parts) + "\n\n---\n\n" + tutor.REPLY_LANGUAGE_RULE + "\n\n" + HEADLESS)


def skill_guide(skill: str) -> list[str]:
    """The dashboard's input guide for ``/<skill>``, from every card that runs it."""
    slash = f"/{prompt_gate.normalize_skill(skill)}"
    guide: list[str] = []
    for entry in phase_actions.ACTIONS.values():
        for action in entry["actions"]:
            if action["kind"] == "prompt" and action["slash"] == slash:
                guide.extend(line for line in action["guide"] if line not in guide)
    return guide


def build_prompt(skill: str, text: str, check: dict[str, Any], language: str,
                 answers: list[dict[str, str]]) -> str:
    name = prompt_gate.normalize_skill(skill)
    shown = {k: check[k] for k in ("score", "threshold", "verdict", "critical", "issues", "needs")}
    guide = "\n".join(f"- {line}" for line in skill_guide(name)) or "- (no dashboard guide; read the skill)"
    lines = [
        f"Skill: /{name} (its input rules: skills/{name}/SKILL.md)",
        f"Board language: {language}",
        "",
        "Dashboard input guide for this skill:",
        guide,
        "",
        "Deterministic check of the original prompt:",
        json.dumps(shown, ensure_ascii=False),
        "",
        "The operator's prompt, verbatim:",
        "<<<",
        text,
        ">>>",
    ]
    if answers:
        lines += ["", "The operator's answers to your questions:"]
        lines += [f"- {a.get('question', a.get('id', ''))}: {a.get('answer', '')}" for a in answers]
        lines += ["", "Compose the improved prompt from the original and these answers."]
    return "\n".join(lines)


def _strings(value: Any, limit: int | None = None) -> list[str]:
    items = [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []
    return items[:limit] if limit else items


def normalize_turn(turn: Any) -> dict[str, Any] | None:
    """The reviewer's turn bounded to the contract, or None when unusable."""
    if not isinstance(turn, dict) or turn.get("verdict") not in ("improve", "clarify"):
        return None
    improved = str(turn.get("improved_prompt") or "").strip()
    questions = []
    for i, q in enumerate(turn.get("questions") or []):
        if not isinstance(q, dict) or not str(q.get("question") or "").strip():
            continue
        questions.append({"id": str(q.get("id") or f"q{i + 1}"), "question": str(q["question"]).strip(),
                          "options": _strings(q.get("options"), MAX_OPTIONS)})
    questions = questions[:MAX_QUESTIONS]
    if turn["verdict"] == "improve" and not improved:
        return None
    if turn["verdict"] == "clarify" and not questions:
        return None
    return {"verdict": turn["verdict"], "reply": str(turn.get("reply") or "").strip(),
            "issues": _strings(turn.get("issues")), "improved_prompt": improved,
            "preserved_requirements": _strings(turn.get("preserved_requirements")),
            "questions": questions if turn["verdict"] == "clarify" else []}


def _answers(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if isinstance(item, dict) and str(item.get("answer") or "").strip():
            out.append({"id": str(item.get("id") or ""), "question": str(item.get("question") or ""),
                        "answer": str(item["answer"]).strip()[:2000]})
    return out[:MAX_QUESTIONS]


def validate(payload: Any) -> tuple[str, str, bool | None]:
    payload = payload if isinstance(payload, dict) else {}
    skill = prompt_gate.normalize_skill(str(payload.get("skill") or ""))
    if not skill:
        raise ReviewInvalid("skill is required")
    text = payload.get("text")
    text = "" if text is None else str(text)
    if len(text) > MAX_TEXT:
        raise ReviewInvalid(f"text is longer than {MAX_TEXT} characters")
    optional = payload.get("optional")
    return skill, text, (bool(optional) if optional is not None else None)


def review(root: Path, payload: Any) -> dict[str, Any]:
    """Check, then (only on a failed check, or with answers) ask the reviewer."""
    skill, text, optional = validate(payload)
    payload = payload if isinstance(payload, dict) else {}
    language = "es" if str(payload.get("language") or "en").lower().startswith("es") else "en"
    answers = _answers(payload.get("answers"))
    check = prompt_gate.check(skill, text, optional=optional)
    base = {"ok": True, "skill": skill, "check": check}
    if check["verdict"] == "pass" and not answers:
        return {**base, "available": True, "verdict": "pass"}
    try:
        turn, agent = tutor.run_agent(Path(root), system_prompt(Path(root)),
                                      build_prompt(skill, check["text"], check, language, answers), [],
                                      schema=REVIEW_SCHEMA, tools=("Read", "Glob", "Grep"))
    except tutor.TutorError as error:
        return {**base, "available": False, "reason": str(error)[:300]}
    result = normalize_turn(turn)
    if result is None:
        return {**base, "available": False, "reason": "the reviewer answered no usable verdict"}
    out = {**base, "available": True, "agent": agent, **result}
    if result["improved_prompt"]:
        out["improved_check"] = prompt_gate.check(skill, result["improved_prompt"], optional=optional)
    return out


__all__ = ["MAX_TEXT", "REVIEW_SCHEMA", "ReviewInvalid", "approved", "build_prompt", "normalize_turn",
           "review", "skill_guide", "system_prompt", "validate"]
