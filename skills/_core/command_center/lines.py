"""The command center's paper lines: one board per kind, looked up by kind.

A workspace's line is its ``paper_kind`` (``.papersmith/config.json``, read
with ``paper_types.decision.current_line``). Each line the dashboard knows has
one :class:`Board` in :data:`BOARDS`: its steps in order, their labels,
actions, evidence and locks, its section order, its flow diagram and the hooks
the status view, ``/api/phase/run``, the AI history and the agents table call.
Every place that used to branch on ``kind == "review"`` asks :func:`board`.

* ``experimental`` (the applied-AI line) is built from ``phase_actions`` and
  the server's own phase computation, untouched.
* ``review`` is built from ``review_board``, untouched.
* A new line registers its board with :func:`register`: its board module
  (an ``empirical_board``) builds ``Board(kind="<kind>", build=..., ...)``
  and calls ``lines.register`` when imported, and this module imports that
  module at its end, so the registry is complete whenever it is read. The
  server, ``phase_actions``, ``state_extractor``, the AI history, the agents
  table and the page then need no change; a view only that line shows
  carries ``data-kinds="<kind>"``.
* A kind with no board is never silently shown as experimental:
  :func:`board` answers the experimental board with a ``notice`` the status
  payload, the AI history, the agents table and the page show, and lists the
  workspace's own section contracts (never the experimental ones as missing).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from . import phase_actions, review_board
from . import state_extractor as _ex

#: The line every unregistered kind falls back to.
BASE = "experimental"


def _no_artifacts(_root: Path) -> list[dict[str, Any]]:
    return []


@dataclass(frozen=True)
class Board:
    """One paper line's board. ``build``, ``section_metadata`` and
    ``telemetry`` left ``None`` mean the server's own experimental
    computation; ``shared_checks`` left ``None`` means each stage runs its own
    ``/api/phase/run`` check (the experimental phases)."""

    kind: str
    stages: tuple[str, ...]
    labels: Mapping[str, str]
    actions: Mapping[str, dict[str, Any]]
    evidence: Mapping[str, tuple[tuple[str, str], ...]]
    ungated: frozenset[str]
    phase_gates: Mapping[str, str]
    transversal: str
    #: The canonical section contracts, in rendering order (``()``: the
    #: contracts on disk, sorted).
    section_order: tuple[str, ...]
    #: The shipped flow diagram ``/api/flow`` serves (``static/<name>``).
    flow_html: str
    #: ``stage_for(phase_id)``: the step a ``/api/phase/run`` id names.
    stage_for: Callable[[str], str | None]
    #: ``build(root, facts) -> (fases, gates)``: the line's steps and gates.
    build: Callable[[Path, dict[str, Any]], tuple[list[dict[str, Any]], list[dict[str, Any]]]] | None = None
    artifacts: Callable[[Path], list[dict[str, Any]]] = _no_artifacts
    section_metadata: Callable[[Path], dict[str, dict[str, Any]]] | None = None
    telemetry: Callable[[list[dict[str, Any]], str], list[dict[str, Any]]] | None = None
    #: Step -> the server check it shares (``writing``, ``paper``, ``audit``);
    #: every other step runs from its card.
    shared_checks: Mapping[str, str] | None = None
    #: The manuscript's block count; ``None``: the contracts' own count.
    blocks_total: int | None = 46
    #: A ``/<verb_skill> <verb>`` command opens the step that runs ``verb``:
    #: a prompt action's prefix, a ``<verb_cli> <verb>`` command, or an alias.
    verb_skill: str | None = None
    verb_cli: str | None = None
    verb_aliases: Mapping[tuple[str, str], str] = field(default_factory=dict)
    #: ``decisions`` source -> the step its events belong to (AI history).
    decision_stages: Mapping[str, str] = field(default_factory=dict)
    #: The step the proposal revisions belong to; ``None``: no step.
    revisions_stage: str | None = None
    #: Shown when the workspace's kind has no board of its own.
    notice: str | None = None

    @property
    def is_base(self) -> bool:
        """Whether this is the experimental board, whose agents map to phases
        by their tramo; every other board derives them from its actions."""
        return self.kind == BASE


EXPERIMENTAL = Board(
    kind=BASE,
    stages=phase_actions.STAGES,
    labels=phase_actions.PHASE_LABELS,
    actions=phase_actions.ACTIONS,
    evidence=phase_actions.EVIDENCE,
    ungated=phase_actions.UNGATED,
    phase_gates=phase_actions.PHASE_GATES,
    transversal="audit",
    section_order=_ex.SECTION_ORDER,
    flow_html="papersmith-flow.html",
    stage_for=phase_actions.stage_for,
    decision_stages={
        "declarations": "declarations",
        "proposal": "proposal",
        "experiment": "poc_experiments",
        "remote-execution": "poc_experiments",
    },
    revisions_stage="proposal",
)

REVIEW = Board(
    kind="review",
    stages=review_board.REVIEW_STAGES,
    labels=review_board.REVIEW_LABELS,
    actions=review_board.REVIEW_ACTIONS,
    evidence=review_board.REVIEW_EVIDENCE,
    ungated=review_board.REVIEW_UNGATED,
    phase_gates=review_board.REVIEW_PHASE_GATES,
    transversal=review_board.REVIEW_TRANSVERSAL,
    section_order=_ex.REVIEW_SECTION_ORDER,
    flow_html="papersmith-review-flow.html",
    stage_for=review_board.stage_for,
    build=review_board.board,
    artifacts=review_board.artifacts,
    section_metadata=review_board.section_metadata,
    telemetry=review_board.telemetry,
    shared_checks={"writing": "writing", "paper": "paper", "reporting_audit": "audit"},
    blocks_total=None,
    verb_skill="systematic-review",
    verb_cli=review_board.REVIEW_CLI,
    # A `/systematic-review` verb the skill documents that no board action names.
    verb_aliases={("systematic-review", "extract"): "appraisal_extraction"},
    decision_stages={"declarations": "writing"},
    revisions_stage=None,
)

#: kind -> its board.
BOARDS: dict[str, Board] = {}


def register(entry: Board) -> Board:
    """Add ``entry`` as the board of ``entry.kind``; a kind has one board."""
    if not entry.kind or entry.kind in BOARDS:
        raise ValueError(f"paper line {entry.kind!r} already has a board" if entry.kind
                         else "a board needs a kind")
    BOARDS[entry.kind] = entry
    return entry


register(EXPERIMENTAL)
register(REVIEW)


def registered(kind: str) -> bool:
    return kind in BOARDS


def notice(kind: str) -> str:
    return (f'The paper line "{kind}" has no board yet: the dashboard shows the experimental '
            f"(applied-AI) board, whose phases and gates may not apply to this paper.")


def _no_metadata(_root: Path) -> dict[str, dict[str, Any]]:
    return {}


def board(kind: str | None) -> Board:
    """The board of ``kind``; for a kind with none, the experimental board
    with a :attr:`Board.notice`, the workspace's own contracts as its
    sections (no experimental ones reported missing, no experimental section
    guidance) and the contracts' own block count."""
    found = BOARDS.get(kind or BASE)
    if found is not None:
        return found
    return dataclasses.replace(EXPERIMENTAL, section_order=(), section_metadata=_no_metadata,
                               blocks_total=None, notice=notice(str(kind)))


def for_workspace(root: Path | str) -> tuple[str, Board]:
    """The workspace's line (read now: ``smith kind set`` can move it while
    the dashboard runs) and its board."""
    kind = _ex.decision.current_line(Path(root))
    return kind, board(kind)


__all__ = ["BASE", "BOARDS", "Board", "EXPERIMENTAL", "REVIEW", "board", "for_workspace", "notice",
           "register", "registered"]

# The empirical lines register their boards (one per line table) when their
# module is imported; it imports this one, so it is imported last.
from . import empirical_board  # noqa: E402,F401
