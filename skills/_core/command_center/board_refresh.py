"""The board refresh: regenerate every derived artifact the dashboard shows,
then say where the project stands.

``smith ui`` runs :func:`refresh_artifacts` once in the background when the
server starts (``--no-refresh`` skips it), and the topbar's "Update board"
button runs it again through ``POST /api/board/refresh``. Only local, keyless
steps run here: the ideas sync, the SOTA atlas page, the atlas manuscript layer,
the manuscript graph, the novelty graph's viewer copy and the wiring health. The
ideas sync runs first (``idea_sync.py``): it brings the pillars, hypotheses and
problem tree of ``.papersmith/model_spec.json`` to the latest proposal revision's
sky overlay, retiring what that revision dropped, so the graphs after it draw
the current iteration; its change report is the summary's ``ideas``. What an
agent writes (the proposal sky itself, the enrichment of each idea, the journal
ranks that need the network) is not regenerated; the summary reports what is
still owed instead.

Each generator is isolated: one that raises is reported as ``failed`` and the
others still run. Everything they write lands in watched folders, so the live
channel repaints the board on its own.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import atlas_build, atlas_manuscript, idea_sync, manuscript_graph, novelty_graph

#: The artifacts a refresh regenerates, in the order it runs them.
ARTIFACT_IDS = ("ideas", "atlas", "atlas_manuscript", "manuscript_graph", "novelty_graph", "health")

#: The cross-cutting audit runs beside every phase, so it is never "the
#: current phase" a project is in.
TRANSVERSAL_STAGES = frozenset({"audit"})

DETAIL_MAX = 300


def _entry(artifact: str, state: str, detail: str = "") -> dict[str, Any]:
    return {"id": artifact, "state": state, "detail": str(detail or "")[:DETAIL_MAX]}


#: The change report fields the summary carries for the ideas sync.
IDEAS_REPORT_KEYS = ("state", "detail", "revision", "previous_revision", "added", "pruned", "changed",
                     "unchanged", "kept", "written", "contribution_type_stale")


def _ideas(root: Path) -> dict[str, Any]:
    result = idea_sync.sync(root)
    state = {"synced": "ok", "unchanged": "ok"}.get(result["state"], result["state"])
    entry = _entry("ideas", state, result.get("detail", ""))
    entry["report"] = {key: result.get(key) for key in IDEAS_REPORT_KEYS if key in result}
    return entry


def _atlas(root: Path) -> dict[str, Any]:
    result = atlas_build.build(root)
    if result.get("ok"):
        return _entry("atlas", "ok", atlas_build.describe(result))
    if result.get("stage") == "absent":
        return _entry("atlas", "skipped", result.get("detail", ""))
    return _entry("atlas", "failed", atlas_build.describe(result))


def _from_refresh(artifact: str, result: dict[str, Any] | None, absent: str) -> dict[str, Any]:
    """A ``refresh()`` result: ``None`` means its input is missing."""
    if result is None:
        return _entry(artifact, "skipped", absent)
    if result.get("ok"):
        return _entry(artifact, "ok", result.get("path", ""))
    return _entry(artifact, "failed", result.get("warning") or result.get("detail") or result.get("status", ""))


def _atlas_manuscript(root: Path) -> dict[str, Any]:
    return _from_refresh("atlas_manuscript", atlas_manuscript.refresh(root),
                         "sota-pool/atlas.json not found")


def _manuscript_graph(root: Path) -> dict[str, Any]:
    return _from_refresh("manuscript_graph", manuscript_graph.refresh(root),
                         "papersmith.yaml not found")


def _novelty_graph(root: Path) -> dict[str, Any]:
    # The viewer keeps its copy in .papersmith/; without that folder there is
    # no workspace state to draw and nothing would be written.
    if not (root / ".papersmith").is_dir():
        return _entry("novelty_graph", "skipped", ".papersmith/ not found")
    novelty_graph.build_novelty_viewer_html(root)
    return _entry("novelty_graph", "ok", ".papersmith/novelty_graph.html")


def refresh_artifacts(root: Path | str, *,
                      health: Callable[[], Any] | None = None) -> list[dict[str, Any]]:
    """Regenerate each artifact of :data:`ARTIFACT_IDS`; one ``{id, state,
    detail}`` per artifact, ``state`` being ``ok``, ``skipped`` (its input is
    not there yet) or ``failed``; the ``ideas`` entry adds its change
    ``report``. ``health`` re-measures the wiring health (the server passes its
    cached measure, forced)."""
    root = Path(root).expanduser().resolve()

    def _health(_: Path) -> dict[str, Any]:
        if health is None:
            return _entry("health", "skipped", "no health probe")
        health()
        return _entry("health", "ok", "wiring health re-measured")

    steps = {"ideas": _ideas, "atlas": _atlas, "atlas_manuscript": _atlas_manuscript,
             "manuscript_graph": _manuscript_graph, "novelty_graph": _novelty_graph,
             "health": _health}
    results = []
    for artifact in ARTIFACT_IDS:
        try:
            results.append(steps[artifact](root))
        except Exception as exc:  # noqa: BLE001 - one generator never stops the others
            results.append(_entry(artifact, "failed", f"{type(exc).__name__}: {exc}"))
    return results


def _gate(gate: dict[str, Any]) -> dict[str, Any]:
    return {"id": gate.get("id", ""), "name": gate.get("name", ""),
            "status": gate.get("status", ""), "phase": gate.get("phase", "")}


def summarize(status: dict[str, Any],
              artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Where the project stands, from a ``/api/status`` payload.

    ``current`` is the first non-transversal phase that has not passed (``None``
    when all have), ``missing`` its sub-phases that have not passed, ``blocked``
    the phases still locked behind a phase or a gate, ``open_gates`` the gates
    not passed yet and ``failed_gates`` the failed ones. ``ideas`` is the ideas
    sync's change report (added, pruned, changed and unchanged ids, the revision,
    ``contribution_type_stale``), ``None`` without a refresh. ``tone`` is ``alert``
    when a gate failed, ``warn`` when an artifact failed to regenerate, ``done``
    when every phase passed and ``info`` otherwise.
    """
    fases = [phase for phase in status.get("fases") or [] if isinstance(phase, dict)]
    gates = [gate for gate in status.get("gates") or [] if isinstance(gate, dict)]
    current = next((phase for phase in fases
                    if phase.get("stage_id") not in TRANSVERSAL_STAGES
                    and phase.get("status") != "PASS"), None)
    missing = []
    if current is not None:
        missing = [{"id": step.get("id", ""), "name": step.get("name", ""),
                    "status": step.get("status", ""), "detail": step.get("detail", "")}
                   for step in current.get("subfases") or []
                   if isinstance(step, dict) and step.get("status") != "PASS"]
    blocked = [{"id": phase.get("id", ""), "name": phase.get("name", ""),
                "blocked_by": phase.get("blocked_by")}
               for phase in fases if phase.get("blocked_by")]
    open_gates = [_gate(gate) for gate in gates if gate.get("status") not in ("PASS", "FAIL")]
    failed_gates = [_gate(gate) for gate in gates if gate.get("status") == "FAIL"]
    failed_artifacts = [item["id"] for item in artifacts or [] if item.get("state") == "failed"]
    if failed_gates:
        tone = "alert"
    elif failed_artifacts:
        tone = "warn"
    elif current is None:
        tone = "done"
    else:
        tone = "info"
    return {
        "current": None if current is None else {
            "id": current.get("id", ""), "stage_id": current.get("stage_id", ""),
            "name": current.get("name", ""), "status": current.get("status", ""),
            "detail": current.get("detail", ""), "gate": current.get("gate", ""),
            "unlocked": current.get("unlocked", True),
            "blocked_by": current.get("blocked_by"),
            "cli_command": current.get("cli_command", ""),
        },
        "missing": missing,
        "blocked": blocked,
        "open_gates": open_gates,
        "failed_gates": failed_gates,
        "failed_artifacts": failed_artifacts,
        "ideas": next((item.get("report") for item in artifacts or []
                       if item.get("id") == "ideas" and isinstance(item.get("report"), dict)), None),
        "phases_completed": sum(1 for phase in fases if phase.get("status") == "PASS"),
        "phases_total": len(fases),
        "gates_passed": sum(1 for gate in gates if gate.get("status") == "PASS"),
        "gates_total": len(gates),
        "tone": tone,
    }


__all__ = ["ARTIFACT_IDS", "IDEAS_REPORT_KEYS", "TRANSVERSAL_STAGES", "refresh_artifacts", "summarize"]
