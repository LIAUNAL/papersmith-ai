#!/usr/bin/env python3
"""The deterministic prompt quality gate of the phase skills.

Every prompt a phase skill receives (the ``$ARGUMENTS`` of ``/<skill>``) is
scored 0-100 before the skill runs, with no model call:

* a generic rubric drawn from published prompt-engineering guidance (a task
  stated clearly enough for a newcomer, no leftover example or placeholder,
  enough words to carry the task -- Anthropic's prompting best practices and
  The Prompt Report, arXiv 2406.06608); and
* the input contract of the skill it is sent to: what that skill needs to
  start (``/plausibility`` refuses ideas under two sentences, ``/paper-ingestion``
  needs a path or URL, ``/figure-review`` a figure id, ...).

An issue is ``critical`` (the skill cannot start: the gate fails whatever the
score), ``major`` (-25) or ``minor`` (-10). The prompt fails on a critical issue
or a score under :data:`THRESHOLD`. A failed prompt is where the gate doctrine
(``prompt_gate.md`` next to this file) has the agent, or the dashboard's
headless reviewer, propose an improved prompt or ask clarifying questions.

A prompt the operator already approved carries :data:`APPROVED_MARKER`; it
passes untouched (the marker is stripped from ``text``).

CLI, one JSON object on stdout::

    python -m skills._core.command_center.prompt_gate check --skill <name> [--text <prompt>] [--optional]

Without ``--text`` the prompt is read from stdin (safe for any quoting). The
check exits 0 whatever the verdict; a usage error prints
``{"ok": false, "error": "USAGE", ...}`` and exits 2.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Any

THRESHOLD = 60
#: Appended by an approval (dashboard "Approve and launch", or the agent after
#: the operator approved its proposal): the gate lets the prompt through.
APPROVED_MARKER = "[prompt-gate: approved]"
PENALTY = {"critical": 50, "major": 25, "minor": 10}
#: The dashboard's sentence rule (``phaseSentenceCount`` in phase-console.js):
#: a long run-on idea counts one sentence per this many words.
WORDS_PER_SENTENCE = 12
DEFAULT_MIN_WORDS = 4

_MARKER_RE = re.compile(r"\s*\[prompt-gate:\s*approved\]\s*", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"^\s*(e\.g\.|ej\.|ej:|por ejemplo:|for example:)|<[a-z][a-z /|-]{1,30}>",
                             re.IGNORECASE)
#: Words that carry no task on their own: a prompt made only of them is vague.
_VAGUE = frozenset("""
    hazlo haz hacer algo eso esto lo mismo mejora mejoralo mejoralo arregla arreglalo arreglalo ayuda ayudame
    ayudame sigue seguir continua continua continuar dale ok vale si si please por favor favor bien todo
    do it this that fix improve help continue go on again same thing stuff something ok yes now just make
    anything whatever etc
""".split())


@dataclass(frozen=True)
class Need:
    """One element a skill's prompt must carry."""
    id: str
    label: str
    pattern: str
    severity: str = "major"

    def found(self, text: str) -> bool:
        return re.search(self.pattern, fold(text), re.IGNORECASE) is not None


@dataclass(frozen=True)
class Contract:
    optional: bool = False
    min_words: int = DEFAULT_MIN_WORDS
    min_sentences: int = 0
    needs: tuple[Need, ...] = field(default_factory=tuple)


_EXPERIMENT_ANCHOR = (r"claim|\bC\d+\b|afirmaci|experiment|\bE\d+\b|metric|metric|baseline|linea base|protocol|"
                      r"dataset|design|disen|ablat|ablaci|first version|primera versi|revis|\br\d{2}\b|citation|cita")
_PROPOSAL_ANCHOR = (r"first version|primera versi|change|cambi|revis|\br\d{2}\b|discuss|discut|deliber|hypothes|"
                    r"hipotesis|hipotesis|\bH\d+\b|pillar|pilar|equation|ecuaci|mathemat|matemat|problem|"
                    r"citation|cita|judge|juez|novelty|novedad|layer|capa|concept|concepto|sota")

CONTRACTS: dict[str, Contract] = {
    "plausibility": Contract(min_words=15, min_sentences=2, needs=(
        Need("problem", "the problem or limitation the idea addresses",
             r"problem|issue|challenge|limitation|\black|\bgap\b|fail|\blos[es]|suffer|struggl|difficult|cannot|"
             r"\bpoor|degrad|costly|expensive|problema|limitaci|reto|desaf|carec|falta|brecha|falla|pierde|"
             r"dificult|no logra|no pued|deficien|costos|degrad"),
        Need("proposal", "what you propose (method, approach or hypothesis)",
             r"propos|we present|introduc|approach|method|framework|hypothes|leverag|combin|propon|propuesta|"
             r"plante|enfoque|metodo|metodo|hipotesis|hipotesis|aprovech|combinar"),
    )),
    "paper-ingestion": Contract(min_words=1, needs=(
        Need("source", "the path, glob or URL of the PDFs to ingest",
             r"https?://|doi\.org|\b10\.\d{4,}/|\S+\.pdf\b|[\w.*-]+/[\w*.-]+|\binbox\b|\btop ?\d+\b|accepted|aceptad",
             "critical"),
    )),
    "proposal-deliberation": Contract(min_words=6, needs=(
        Need("anchor", "what to deliberate: a first version, a change, a revision (rNN) or an element "
                       "(problem, pillar, hypothesis, equation)", _PROPOSAL_ANCHOR, "minor"),
    )),
    "experimental-deliberation": Contract(min_words=6, needs=(
        Need("anchor", "the claim, experiment, metric or baseline to design or revise", _EXPERIMENT_ANCHOR, "minor"),
    )),
    "proposal-implementation": Contract(optional=True, needs=(
        Need("target", "the target repository (e.g. ../my-poc) or the baseline to replicate",
             r"\.\./|implementations/|guidance/|[\w.-]+/[\w.-]+|\brepo|repositor|baseline|proof-of-concept"),
    )),
    "experimental-implementation": Contract(optional=True, needs=(
        Need("target", "the experiments (E1, E2...) or the target repository",
             r"\bE\d+\b|experiment|\.\./|implementations/|[\w.-]+/[\w.-]+|\brepo|repositor"),
    )),
    "figure-review": Contract(min_words=1, needs=(
        Need("figure", "the id of a compiled figure (paper/Figures/<id>.pdf), e.g. fig-architecture",
             r"\bfig[-_:][\w-]+|figures?/|\bfigur[ea]s?\s+[\w-]+", "critical"),
    )),
    "paper-writing": Contract(min_words=2, needs=(
        Need("target", "the verb or block to work on (skeleton, mark, write <block>, resolve, translate...)",
             r"skeleton|esqueleto|\bmark\b|\bwrite\b|escrib|redact|resolve|\bbib\b|translate|traduc|review|revis|"
             r"venue|apply|aplica|compile|compil|block|bloque|section|secci|\b[a-z]+\.[a-z_]+\b"),
    )),
    "skill-audit": Contract(min_words=2, needs=(
        Need("subject", "the subject to audit: a skill, a CLI or a closed set",
             r"skills?/|\bskill\b|\bcli\b|[\w-]+\.py|\bsmith\b|subcommand|subcomando|error code|codigo|"
             r"operation|operaci|[a-z]+-[a-z]+"),
    )),
    "datasets": Contract(optional=True, needs=(
        Need("verb", "the verb: synth, search, license, qc, prepare or publish",
             r"synth|search|busca|license|licenc|\bqc\b|quality|calidad|prepare|prepar|publish|public"),
    )),
    "remote-execution": Contract(optional=True, needs=(
        Need("verb", "the step: generate-job, submit, fetch, smoke, readiness, gate, status or poll",
             r"generate|genera|submit|env[ii]a|fetch|smoke|readiness|\bgate\b|status|estado|poll|launch|lanza"),
    )),
    "kaggle-accounts": Contract(optional=True, min_words=1, needs=(
        Need("verb", "the verb (validate)", r"validat|valida|inbox|account|cuenta"),
    )),
    "hyperparameter-search": Contract(optional=True, needs=(
        Need("anchor", "the arms, trial budget, space or evaluator",
             r"\barm|brazo|trial|ensayo|space|espacio|optuna|\bplan\b|report|evaluat|evalua|anova", "minor"),
    )),
    "remote-parallelism": Contract(optional=True, needs=(
        Need("anchor", "estimate (with timing.json) or assess the split",
             r"estimat|estim|assess|evalu|timing|owner|split|divid|repart", "minor"),
    )),
    "experiment-diagrams": Contract(optional=True, needs=(
        Need("target", "poc or experiments, and the product", r"\bpoc\b|experiment|product|producto|implementations/"),
    )),
    "upgrade-project": Contract(optional=True, min_words=1),
}


def fold(text: str) -> str:
    """``text`` without diacritics, so the patterns match "metodo" and its
    accented spelling alike (and stay plain ASCII)."""
    return "".join(c for c in unicodedata.normalize("NFD", str(text or "")) if not unicodedata.combining(c))


def normalize_skill(skill: str) -> str:
    return str(skill or "").strip().lstrip("/").strip().lower()


def strip_marker(text: str) -> str:
    return _MARKER_RE.sub(" ", str(text or "")).strip()


def sentence_count(text: str) -> int:
    clean = str(text or "").strip()
    parts = [p for p in re.split(r"(?<=[.!?])\s+", clean) if re.search(r"\w", p)]
    words = len([w for w in clean.split() if re.search(r"\w", w)])
    return max(len(parts), words // WORDS_PER_SENTENCE)


def _words(text: str) -> list[str]:
    return [w for w in text.split() if re.search(r"\w", w)]


def contract_for(skill: str) -> Contract:
    return CONTRACTS.get(normalize_skill(skill), Contract())


def check(skill: str, text: str, *, optional: bool | None = None,
          threshold: int = THRESHOLD) -> dict[str, Any]:
    """Score ``text`` as the prompt of ``/<skill>``; see the module doc."""
    name = normalize_skill(skill)
    contract = contract_for(name)
    raw = str(text or "")
    approved = _MARKER_RE.search(raw) is not None
    clean = strip_marker(raw)
    allow_empty = contract.optional if optional is None else optional
    issues: list[dict[str, str]] = []

    def add(issue_id: str, severity: str, message: str) -> None:
        issues.append({"id": issue_id, "severity": severity, "message": message})

    words = _words(clean)
    if approved:
        pass
    elif not words:
        if not allow_empty:
            add("empty", "critical", "The prompt is empty: the skill has nothing to work on.")
    else:
        tokens = [re.sub(r"[^\w]", "", fold(w).lower()) for w in words]
        tokens = [t for t in tokens if t]
        if tokens and len(tokens) <= 5 and all(t in _VAGUE for t in tokens):
            add("vague", "major", "The prompt names no task, object or goal: say what to do and on what.")
        if _PLACEHOLDER_RE.search(fold(clean)):
            add("placeholder", "major", "The prompt still holds the example prefix or an unfilled <placeholder>.")
        if len(words) < contract.min_words:
            add("short", "major", f"The prompt is too short for this skill (fewer than {contract.min_words} words).")
        if contract.min_sentences and sentence_count(clean) < contract.min_sentences:
            add("sentences", "critical",
                f"The skill needs at least {contract.min_sentences} sentences; it refuses shorter input.")
        for need in contract.needs:
            if not need.found(clean):
                add(need.id, need.severity, f"Missing: {need.label}.")

    score = max(0, 100 - sum(PENALTY[i["severity"]] for i in issues))
    critical = any(i["severity"] == "critical" for i in issues)
    verdict = "pass" if approved or (not critical and score >= threshold) else "fail"
    return {
        "ok": True, "skill": name, "score": score, "threshold": threshold, "verdict": verdict,
        "critical": critical, "approved": approved, "text": clean, "issues": issues,
        "needs": [need.label for need in contract.needs],
        "min_sentences": contract.min_sentences, "optional": allow_empty,
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # one JSON object, never argparse's stderr text
        sys.stdout.write(json.dumps({"ok": False, "error": "USAGE", "message": message}) + "\n")
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="python -m skills._core.command_center.prompt_gate",
                     description="Score a phase prompt (deterministic, no model call).")
    sub = parser.add_subparsers(dest="verb", required=True)
    verb = sub.add_parser("check", help="score one prompt; JSON on stdout")
    verb.error = parser.error  # type: ignore[method-assign]
    verb.add_argument("--skill", required=True, help="the phase skill, with or without the leading /")
    verb.add_argument("--text", help="the prompt; read from stdin when omitted")
    verb.add_argument("--optional", action="store_true", help="an empty prompt is allowed")
    verb.add_argument("--threshold", type=int, default=THRESHOLD)
    args = parser.parse_args(argv)
    text = args.text if args.text is not None else sys.stdin.read()
    result = check(args.skill, text, optional=True if args.optional else None, threshold=args.threshold)
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


__all__ = ["APPROVED_MARKER", "CONTRACTS", "THRESHOLD", "check", "contract_for", "main",
           "normalize_skill", "sentence_count", "strip_marker"]

if __name__ == "__main__":
    raise SystemExit(main())
