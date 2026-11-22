"""Characterization of the applied-AI (``experimental``) paper line.

The paper-type plan (``odd/tasks/paper-type-lines.md``, S1) adds paper types
without changing the applied-AI flow. This file pins what an ``experimental``
workspace receives today, so a refactor cannot move it silently:

* ``status-en.json`` / ``status-es.json``: the dashboard's ``/api/status`` for
  an empty workspace, English and Spanish (phases, sub-phases, cards, gates,
  sections, telemetry), with only the environment-dependent values normalized;
* ``phase-actions.json``: the phase definitions in ``phase_actions``;
* ``harness-flow.json``: the flow text the four harness entrypoints carry;
* ``kit.json``: the section contracts and skills an experimental workspace gets.

A change is accepted only when it is declared in ``DECLARED_ADDITIONS``: an
addition (a new key, list item or text line) under a declared path. Anything
removed or changed fails. To accept an intended change, update the goldens
on purpose and let the diff be reviewed:

    PAPERSMITH_UPDATE_CHARACTERIZATION=1 python -m pytest tests/test_experimental_line_characterization.py
"""

from __future__ import annotations

import difflib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import papersmith
from papersmith.core import manifest
from papersmith.generators import ALL_TOOLS, render_files
from papersmith.kit import resolve_and_validate
from skills._core.command_center import phase_actions, server

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "experimental_line"
UPDATE = os.environ.get("PAPERSMITH_UPDATE_CHARACTERIZATION") == "1"
ENTRYPOINTS = ("CLAUDE.md", "OPENCODE.md", ".pi/APPEND_SYSTEM.md", ".agents/AGENTS.md")
WORKSPACE = "characterized-paper"

#: Additions the paper-type plan may make to the experimental line, per golden:
#: a JSON path prefix (``/fases/1/subfases``) under which new keys or list items
#: may appear, or, for text, a regular expression an added line must match.
#: Empty until a task declares one (paper-type-lines S1).
DECLARED_ADDITIONS: dict[str, tuple[str, ...]] = {
    # T4: Phase 2's advisory sub-step 2.5 "Paper Type" (locks nothing).
    # T6a: the workspace's paper line (`paper_kind`), read on every request.
    "status-en.json": ("/fases/1/subfases/4", "/pipeline_stages/1/subfases/4", "/paper_kind"),
    # T4: Phase 2's advisory sub-step 2.5 "Paper Type" (locks nothing).
    # T6a: the workspace's paper line (`paper_kind`), read on every request.
    "status-es.json": ("/fases/1/subfases/4", "/pipeline_stages/1/subfases/4", "/paper_kind"),
    "phase-actions.json": (),
    # T3: plausibility hands over to /paper-type; three added lines in step 2.
    "harness-flow.json": (r"/\+:   On acceptance, `/paper-type` scores the idea against smith's paper types,$",
                          r"/\+:   discusses the suggestion and records the type the operator agrees in$",
                          r"/\+:   `\.papersmith/paper_type\.json`; the phases below do not change\.$"),
    # T3: the paper-type skill ships to every workspace; the AI flow does not call it.
    "kit.json": (r"^/skills/\+:paper-type$",),
}


def _normalize(value: Any, root: Path) -> Any:
    """The payload with the values that depend on where and when it ran replaced."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key == "generated_at":
                out[key] = "<generated_at>"
            else:
                out[key] = _normalize(item, root)
        return out
    if isinstance(value, list):
        return [_normalize(item, root) for item in value]
    if isinstance(value, str):
        return value.replace(str(root), "<root>").replace(root.name, "<workspace>")
    return value


def status(lang: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="characterization-") as tmp:
        root = Path(tmp) / WORKSPACE
        root.mkdir()
        client = TestClient(server.create_app(root))
        response = client.get("/api/status" + ("?lang=es" if lang == "es" else ""))
        assert response.status_code == 200, response.text
        return _normalize(response.json(), root)


def phase_definitions() -> dict:
    return json.loads(json.dumps({
        "STAGES": phase_actions.STAGES,
        "PHASE_LABELS": phase_actions.PHASE_LABELS,
        "ACTIONS": phase_actions.ACTIONS,
        "EVIDENCE": phase_actions.EVIDENCE,
        "UNGATED": sorted(phase_actions.UNGATED),
        "PHASE_GATES": phase_actions.PHASE_GATES,
        "LEGACY_IDS": phase_actions.LEGACY_IDS,
        "primary_command": {stage: phase_actions.primary_command(stage) for stage in phase_actions.STAGES},
    }))


def harness_flow() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        rendered = render_files(Path(tmp), {"name": WORKSPACE}, tools=ALL_TOOLS)
    version = papersmith.__version__
    return {path: rendered[path].replace(version, "<version>").splitlines() for path in ENTRYPOINTS}


def kit() -> dict:
    layout = manifest.kit_layout(resolve_and_validate(), "experimental")
    return {
        "default_kind": manifest.DEFAULT_PAPER_KIND,
        "sections": sorted(p for p in layout if p.startswith("sections/")),
        "skills": sorted({p.split("/")[1] for p in layout if p.startswith("skills/") and p.count("/") >= 2}),
        "identity_mapping": all(source == target for target, source in layout.items()),
    }


BUILDERS = {
    "status-en.json": lambda: status("en"),
    "status-es.json": lambda: status("es"),
    "phase-actions.json": phase_definitions,
    "harness-flow.json": harness_flow,
    "kit.json": kit,
}


def differences(golden: Any, current: Any, path: str = "") -> list[tuple[str, str]]:
    """``(kind, path)`` for every way ``current`` departs from ``golden``:
    ``added`` (a key or list item only in current), ``removed``, ``changed``.
    Lists of strings (text lines) are compared as text, item by item."""
    if isinstance(golden, dict) and isinstance(current, dict):
        out = []
        for key in golden:
            if key not in current:
                out.append(("removed", f"{path}/{key}"))
            else:
                out += differences(golden[key], current[key], f"{path}/{key}")
        out += [("added", f"{path}/{key}") for key in current if key not in golden]
        return out
    if isinstance(golden, list) and isinstance(current, list):
        if all(isinstance(x, str) for x in golden + current):
            out = []
            matcher = difflib.SequenceMatcher(a=golden, b=current, autojunk=False)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag in ("replace", "delete"):
                    out += [("removed", f"{path}/{i}:{golden[i]}") for i in range(i1, i2)]
                if tag in ("replace", "insert"):
                    out += [("added", f"{path}/+:{current[j]}") for j in range(j1, j2)]
            return out
        out = []
        for i, (g, c) in enumerate(zip(golden, current)):
            out += differences(g, c, f"{path}/{i}")
        out += [("removed", f"{path}/{i}") for i in range(len(current), len(golden))]
        out += [("added", f"{path}/{i}") for i in range(len(golden), len(current))]
        return out
    return [] if golden == current else [("changed", path)]


def undeclared(name: str, golden: Any, current: Any) -> list[str]:
    allowed = DECLARED_ADDITIONS.get(name, ())
    bad = []
    for kind, where in differences(golden, current):
        if kind == "added" and any(where.startswith(prefix) or re.search(prefix, where) for prefix in allowed):
            continue
        bad.append(f"{kind}: {where[:240]}")
    return bad


class ExperimentalLineCharacterizationTests(unittest.TestCase):
    def check(self, name: str) -> None:
        current = BUILDERS[name]()
        path = GOLDEN / name
        if UPDATE:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(current, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")
        golden = json.loads(path.read_text(encoding="utf-8"))
        problems = undeclared(name, golden, current)
        self.assertEqual(problems, [], f"the experimental line changed in {name} (see the module doc)")

    def test_dashboard_status_in_english(self) -> None:
        self.check("status-en.json")

    def test_dashboard_status_in_spanish(self) -> None:
        self.check("status-es.json")

    def test_phase_definitions(self) -> None:
        self.check("phase-actions.json")

    def test_harness_flow_text(self) -> None:
        self.check("harness-flow.json")

    def test_experimental_kit(self) -> None:
        self.check("kit.json")


class CharacterizationMechanicsTests(unittest.TestCase):
    """The comparison accepts a declared addition and nothing else."""

    def test_an_undeclared_change_or_removal_fails(self) -> None:
        golden = {"fases": [{"id": "Fase 2", "subfases": [{"id": "2.1"}]}]}
        changed = {"fases": [{"id": "Fase 2b", "subfases": [{"id": "2.1"}]}]}
        removed = {"fases": [{"id": "Fase 2", "subfases": []}]}
        self.assertEqual(undeclared("x", golden, changed), ["changed: /fases/0/id"])
        self.assertEqual(undeclared("x", golden, removed), ["removed: /fases/0/subfases/0"])

    def test_an_addition_passes_only_under_a_declared_path(self) -> None:
        golden = {"fases": [{"id": "Fase 2", "subfases": [{"id": "2.1"}]}]}
        added = {"fases": [{"id": "Fase 2", "subfases": [{"id": "2.1"}, {"id": "2.5"}]}]}
        self.assertEqual(undeclared("x", golden, added), ["added: /fases/0/subfases/1"])
        DECLARED_ADDITIONS["x"] = ("/fases/0/subfases",)
        self.addCleanup(DECLARED_ADDITIONS.pop, "x")
        self.assertEqual(undeclared("x", golden, added), [])

    def test_text_lines_compare_as_text(self) -> None:
        golden = {"CLAUDE.md": ["a", "b", "c"]}
        self.assertEqual(undeclared("t", golden, {"CLAUDE.md": ["a", "b", "new", "c"]}), ["added: /CLAUDE.md/+:new"])
        self.assertEqual(undeclared("t", golden, {"CLAUDE.md": ["a", "c"]}), ["removed: /CLAUDE.md/1:b"])
        DECLARED_ADDITIONS["t"] = (r"/\+:new$",)
        self.addCleanup(DECLARED_ADDITIONS.pop, "t")
        self.assertEqual(undeclared("t", golden, {"CLAUDE.md": ["a", "b", "new", "c"]}), [])


if __name__ == "__main__":
    unittest.main()
