"""Phase 4's ordered steps, read from the workspace's own files.

The proposal is built in one order: the central problem and its pillars, then
the hypotheses each pillar predicts, then the mathematics, then the NeurIPS
judge. Each step passes from evidence on disk, never from the dashboard's
placeholder specification:

* ``problem_pillars``: a problem statement and at least one pillar, from
  ``.papersmith/model_spec.json`` (``novelty.problem_statement`` and
  ``novelty.pillars``) or from the latest revision's ``.sky.json`` overlay
  (a ``problem`` planet and its ``pillars`` list);
* ``hypotheses``: at least one hypothesis, from ``novelty.hypotheses`` or the
  overlay's ``hypotheses`` list;
* ``mathematics``: at least one ``$$ … \\tag{N} $$`` display block in the
  latest revision ``proposals/research-concept-<slug>-rNN.md``;
* ``neurips_review``: the paper-reviewer's valid ``contribution_type`` in
  ``.papersmith/model_spec.json``.

A step is ``LOCKED`` while the one before it has not passed, ``ACTIVE`` when it
is unlocked and its evidence is missing, and ``PASS`` once its own evidence
exists and the steps before it passed. Read-only, bounded and never raises.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import math_view, model_spec

#: The four steps in their one order; each requires the one before it.
STEP_IDS: tuple[str, ...] = ("problem_pillars", "hypotheses", "mathematics", "neurips_review")
SPEC_REL = ".papersmith/model_spec.json"


def _json(path: Path, root: Path) -> Any:
    try:
        return json.loads(math_view._read(path, root) or "null")
    except (ValueError, RecursionError):
        return None


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _items(value: Any, *fields: str) -> int:
    """How many entries of a list are objects with at least one non-blank field."""
    if not isinstance(value, list):
        return 0
    return sum(1 for item in value if isinstance(item, dict) and any(_text(item.get(f)) for f in fields))


def _evidence(root: Path) -> dict[str, Any]:
    spec = _json(root / SPEC_REL, root)
    novelty = spec.get("novelty") if isinstance(spec, dict) else None
    novelty = novelty if isinstance(novelty, dict) else {}
    proposal = math_view._latest_proposal(root)
    sky: Any = None
    text = ""
    if proposal is not None:
        text = math_view._read(proposal, root) or ""
        sky = _json(proposal.with_suffix(".sky.json"), root)
    sky = sky if isinstance(sky, dict) else {}
    system = sky.get("system") if isinstance(sky.get("system"), dict) else {}
    planets = system.get("planets") if isinstance(system.get("planets"), list) else []
    sky_problem = any(isinstance(p, dict) and p.get("slot") == "problem" and _text(p.get("label"))
                      for p in planets)
    sources: dict[str, str] = {}
    problem = _text(novelty.get("problem_statement"))
    if problem:
        sources["problem"] = SPEC_REL
    elif sky_problem:
        problem = True
    pillars = _items(novelty.get("pillars"), "name", "summary")
    if pillars:
        sources["pillars"] = SPEC_REL
    else:
        pillars = _items(sky.get("pillars"), "label", "detail")
    hypotheses = _items(novelty.get("hypotheses"), "title", "statement")
    if hypotheses:
        sources["hypotheses"] = SPEC_REL
    else:
        hypotheses = _items(sky.get("hypotheses"), "statement")
    sky_rel = proposal.with_suffix(".sky.json").relative_to(root).as_posix() if proposal else ""
    for key, found in (("problem", problem), ("pillars", pillars), ("hypotheses", hypotheses)):
        if found and key not in sources:
            sources[key] = sky_rel
    verdict = spec.get("contribution_type") if isinstance(spec, dict) else None
    kind = model_spec._contribution_type().normalize(verdict)
    return {
        "contribution_type": kind["type"] if kind else "",
        "problem": bool(problem),
        "pillars": pillars,
        "hypotheses": hypotheses,
        "equations": math_view.tagged_equation_count(text) if text else 0,
        "revision": proposal.relative_to(root).as_posix() if proposal else "",
        "sources": sources,
    }


def proposal_steps(root: Path | str) -> list[dict[str, Any]]:
    """The four Phase 4 steps in order, each ``{id, status, done, started,
    evidence, requires}``; ``evidence`` holds counts and file paths only, so
    the dashboard words it in its own language."""
    try:
        root = Path(root).expanduser().resolve()
        found = _evidence(root)
    except OSError:
        found = {"problem": False, "pillars": 0, "hypotheses": 0, "equations": 0,
                 "revision": "", "sources": {}, "contribution_type": ""}
    own = {
        "problem_pillars": (found["problem"] and found["pillars"] > 0,
                            found["problem"] or found["pillars"] > 0,
                            {"problem": found["problem"], "pillars": found["pillars"],
                             "source": found["sources"].get("pillars") or found["sources"].get("problem", "")}),
        "hypotheses": (found["hypotheses"] > 0, found["hypotheses"] > 0,
                       {"hypotheses": found["hypotheses"], "source": found["sources"].get("hypotheses", "")}),
        "mathematics": (found["equations"] > 0, bool(found["revision"]),
                        {"equations": found["equations"], "revision": found["revision"]}),
        "neurips_review": (bool(found["contribution_type"]), bool(found["contribution_type"]),
                           {"type": found["contribution_type"]}),
    }
    steps: list[dict[str, Any]] = []
    previous_passed = True
    for index, step_id in enumerate(STEP_IDS):
        done, started, evidence = own[step_id]
        if not previous_passed:
            status = "LOCKED"
        else:
            status = "PASS" if done else "ACTIVE"
        steps.append({"id": step_id, "status": status, "done": bool(done), "started": bool(started),
                      "evidence": evidence, "requires": STEP_IDS[index - 1] if index else None})
        previous_passed = status == "PASS"
    return steps


def sub_phase_status(step: dict[str, Any]) -> str:
    """A step as a phase-card sub-phase: ``PASS``, ``LOCKED``, ``ACTIVE`` when
    its evidence is partial, else ``PENDING``."""
    if step["status"] in ("PASS", "LOCKED"):
        return step["status"]
    return "ACTIVE" if step["started"] else "PENDING"


__all__ = ["STEP_IDS", "proposal_steps", "sub_phase_status"]
