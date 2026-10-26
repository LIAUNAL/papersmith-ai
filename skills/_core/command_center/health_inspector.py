"""Multi-harness and skill-wiring diagnostics for a PaperSmith workspace.

``get_wiring_health(root)`` answers one question: *is this workspace's
operational wiring actually connected?* It checks four dimensions, each
independently and read-only:

1. **Harness sync** — the generated surfaces (``.claude/``, ``.opencode/``,
   ``.pi/``, ``.agents/``) are structurally current and their ``skills``
   links resolve. When the canonical generator is reachable, drift is measured
   by running it with ``--check`` instead of guessed at.
2. **Skill & CLI executability** — every skill ships a readable ``SKILL.md``,
   and every CLI front door answers ``--help`` with exit code 0.
3. **Agent integrity** — every persona file resolves the skill it names, and
   every tool it requests is a tool the harness vocabulary exposes.
4. **Environment** — the interpreter, a LaTeX engine, and the command center's
   own Python packages are present.

A dimension that cannot be measured reports ``UNKNOWN`` with a reason; it is
never silently reported healthy.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import toolchain

# --------------------------------------------------------------------------
# Static wiring tables
# --------------------------------------------------------------------------
#: Harness tool label -> the directory that carries its projection.
HARNESSES = {
    "claude": ".claude",
    "opencode": ".opencode",
    "pi": ".pi",
    "antigravity": ".agents",
}

#: Directory under a harness prefix that holds its projected slash commands.
#: Antigravity has none: it invokes `/name` from its skills links.
COMMAND_DIRS = {
    "claude": "commands",
    "opencode": "commands",
    "pi": "prompts",
}

#: Fallback for ``papersmith.core.manifest.HARNESS_SKILL_LINKS`` -- explicit
#: ``(tool, relpath)`` pairs. This module is stdlib-only and ships into
#: workspaces where the package may not be importable, so the pairs are
#: duplicated here and the real table wins whenever it can be imported.
_FALLBACK_SKILL_LINKS: tuple[tuple[str, str], ...] = (
    ("claude", ".claude/skills"),
    ("pi", ".pi/skills"),
    ("opencode", ".opencode/skills"),
    ("antigravity", ".agents/skills"),
)


def _skill_links() -> tuple[tuple[str, str], ...]:
    try:
        from papersmith.core.manifest import HARNESS_SKILL_LINKS  # type: ignore
    except Exception:
        return _FALLBACK_SKILL_LINKS
    return tuple(HARNESS_SKILL_LINKS)


def required_skill_links(tool: str) -> list[str]:
    """Every skills symlink a harness must resolve, from the manifest pairs."""
    return [relpath for owner, relpath in _skill_links() if owner == tool]


#: Fallbacks for ``papersmith.generators.AGENT_DIRS`` / ``PLUGIN_FILES``, which
#: derive the support matrix. Duplicated for the same stdlib-only reason as the
#: skill links; tests/test_harness_parity.py pins them to the real tables.
_FALLBACK_AGENT_DIRS: dict[str, str] = {
    "claude": ".claude/agents",
    "opencode": ".opencode/agents",
    "pi": ".pi/agents",
    "antigravity": ".agents/agents",
}
_FALLBACK_PLUGIN_FILES: dict[str, str] = {
    "opencode": ".opencode/plugins/refuse-offpath-push.js",
    "pi": ".pi/extensions/refuse-offpath-push.js",
}


def _generator_table(name: str, fallback: dict[str, str]) -> dict[str, str]:
    try:
        import papersmith.generators as generators  # type: ignore
        return dict(getattr(generators, name))
    except Exception:
        return fallback


def agent_dir(tool: str) -> str | None:
    """Where ``tool`` reads subagent definitions, or None if it has none."""
    return _generator_table("AGENT_DIRS", _FALLBACK_AGENT_DIRS).get(tool)


def plugin_file(tool: str) -> str | None:
    """The generated plugin/extension ``tool`` loads, or None if it has none."""
    return _generator_table("PLUGIN_FILES", _FALLBACK_PLUGIN_FILES).get(tool)


def enabled_tools(root: Path) -> list[str]:
    """Harnesses the workspace enabled, from ``.papersmith/config.json``.

    A workspace with no readable config (a bare checkout, a hand-built tree)
    declares nothing, so every harness is measured rather than none.
    """
    try:
        payload = json.loads((root / ".papersmith" / "config.json").read_text(encoding="utf-8"))
        active = payload["active_tools"]
    except (OSError, ValueError, KeyError, TypeError):
        return list(HARNESSES)
    if not isinstance(active, list):
        return list(HARNESSES)
    return [tool for tool in HARNESSES if tool in active]


#: The canonical generator a harness can be re-checked against, when present.
GENERATORS = {
    "opencode": "scripts/gen-opencode.py",
    "pi": "scripts/gen-pi.py",
    "antigravity": "scripts/gen-antigravity.py",
}

#: A skill's front door is `<name>_cli.py` under the skill's own `scripts/`
#: directory. Derived rather than listed: the roster this replaced was a five-row
#: tuple, and a roster restated by hand loses an entry the day somebody adds one
#: -- measured here, the tuple named five of the seven front doors the repository
#: ships. It also carried one target's own vocabulary into a surface every
#: workspace receives, which is what the forge's vocabulary guard exists to
#: refuse.
#:
#: **What this gives up, stated because it is a real trade.** A front door that
#: was DELETED leaves nothing to derive from, so this dimension can no longer
#: report it as missing. What remains is the signal that never depended on the
#: roster: `skill_manifests` walks the inventory itself, so a skill whose
#: `SKILL.md` is absent is still reported, and a workspace with no `skills/` at
#: all is reported as a warning rather than as an empty, healthy silence.
FRONT_DOOR_GLOB = "*/scripts/*_cli.py"


def front_door_skills(root: Path) -> list[tuple[str, str]]:
    """`[(skill, relative script)]` for every skill that ships a front door.

    Read from the workspace's own inventory, so the roster is whatever is
    installed rather than whatever this file remembers.
    """
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(
        (path.parent.parent.name, f"scripts/{path.name}")
        for path in skills_dir.glob(FRONT_DOOR_GLOB)
    )

#: Required persona definitions, per the spec's wiring contract.
REQUIRED_AGENTS = (
    "redactor.md",
    "diagram-author.md",
    "figure-auditor.md",
    "section-grounding-auditor.md",
    "contract-auditor.md",
    "insumos-observer.md",
)

#: Skill -> the quality gates it feeds. Used by the wiring matrix chain.
SKILL_GATES: dict[str, tuple[str, ...]] = {
    "paper-writing": (
        "writing-readiness",
        "coupling-verification",
        "grounding-style-leak",
        "diagram-raster",
    ),
    "figure-review": ("diagram-raster",),
    "proposal-deliberation": ("coupling-verification",),
    "experimental-deliberation": ("coupling-verification",),
    "experimental-implementation": ("coupling-verification",),
    "proposal-implementation": ("coupling-verification",),
    "paper-ingestion": (),
    "remote-execution": (),
    "skill-audit": (),
}
#: One skill used to appear here with an empty tuple. That entry was the
#: `.get(skill, ())` default spelled out, so removing it changes nothing except
#: the name it carried -- which is the point, and the reason it is not repeated
#: in this comment either.

#: A conservative harness tool vocabulary. An agent requesting a token outside
#: this set is flagged ``TOOL_UNBOUND`` rather than assumed harmless.
KNOWN_HARNESS_TOOLS = frozenset({
    "Read", "Write", "Edit", "Glob", "Grep", "Bash", "Task", "Agent",
    "WebFetch", "WebSearch", "NotebookEdit", "TodoWrite", "TodoRead",
    "MultiEdit", "LS", "BashOutput", "KillBash", "mcp", "Skill",
})

#: Python packages the command center itself depends on.
REQUIRED_PACKAGES = ("fastapi", "uvicorn", "watchfiles", "pydantic")
#: TeX engines, in preference order, and every TeX tool the environment row reports.
LATEX_ENGINES = ("pdflatex", "xelatex", "lualatex")
LATEX_TOOLS = LATEX_ENGINES + ("latexmk",)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_text(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _frontmatter(path: Path) -> dict[str, Any]:
    """Parse an agent's YAML frontmatter without requiring a YAML parser."""
    text = _read_text(path)
    if text is None:
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = next((i for i in range(1, len(lines)) if lines[i].strip() in ("---", "...")), None)
    if end is None:
        return {}
    data: dict[str, Any] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if not sep:
            continue
        data[key.strip()] = value.strip().strip("\"'")
    return data


def _run(command: list[str], cwd: Path, timeout: float = 25.0) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()


# --------------------------------------------------------------------------
# 1. harness sync
# --------------------------------------------------------------------------
def _measure_harness(root: Path, tool: str) -> tuple[str, str, str]:
    """Measure one harness's sync state, preferring the canonical generator.

    A generator that runs and answers is authoritative. When it cannot run at
    all -- no generator in the workspace, or the workspace config it needs is
    unreadable -- the structural comparison is the honest fallback, and the
    detail says so rather than presenting a guess as a measurement.
    """
    generator = root / GENERATORS[tool] if tool in GENERATORS else None
    if generator is not None and generator.is_file():
        code, output = _run([sys.executable, str(generator), "--check", "--root", str(root)], root)
        if code == 0:
            return "IN_SYNC", output or f"{tool}: clean", "generator"
        if code == 3:
            return "DRIFT_DETECTED", output or f"{tool}: drift", "generator"
        return _structural_or_unknown(root, tool, output or f"generator exited {code}")
    try:
        from papersmith.generators import check_generated  # type: ignore
    except Exception:
        state, detail = _structural_drift(root, tool)
        return state, detail, "structural"
    try:
        drifted = check_generated(root, tools=(tool,))
    except Exception as exc:
        return _structural_or_unknown(root, tool, f"check_generated failed: {exc}")
    if drifted:
        return "DRIFT_DETECTED", "drifted: " + ", ".join(sorted(drifted)), "generator"
    return "IN_SYNC", f"{tool}: clean", "generator"


def _structural_or_unknown(root: Path, tool: str, generator_detail: str) -> tuple[str, str, str]:
    """Fall back to the structural comparison when a generator cannot answer.

    A structural ``IN_SYNC`` is accepted with the generator's failure noted;
    a structural ``DRIFT_DETECTED`` is reported as drift; anything else stays
    ``UNKNOWN`` so an unmeasurable harness is never called healthy.
    """
    state, detail = _structural_drift(root, tool)
    if state == "IN_SYNC":
        return state, f"{detail} (generator unavailable: {generator_detail})", "structural"
    if state == "DRIFT_DETECTED":
        return state, detail, "structural"
    return "UNKNOWN", f"{detail} (generator: {generator_detail})", "structural"


def _structural_drift(root: Path, tool: str) -> tuple[str, str]:
    """Fallback: compare generated surfaces when no generator is reachable."""
    prefix = root / HARNESSES[tool]
    if not prefix.is_dir():
        return "UNKNOWN", f"{HARNESSES[tool]}/ is absent"
    for link in required_skill_links(tool):
        if not (root / link).exists():
            return "DRIFT_DETECTED", f"{link} does not resolve"
    commands_dir = COMMAND_DIRS.get(tool)
    if commands_dir is not None:
        commands = prefix / commands_dir
        if not commands.is_dir():
            return "DRIFT_DETECTED", f"{HARNESSES[tool]}/{commands_dir} is absent"
        on_disk = {p.stem for p in commands.glob("*.md")}
        expected = {
            d.name for d in (root / "skills").iterdir()
            if d.is_dir() and (d / "SKILL.md").is_file() and d.name != "_core"
        } if (root / "skills").is_dir() else set()
        if on_disk != expected:
            return "DRIFT_DETECTED", (
                f"{commands_dir} != skills: missing {sorted(expected - on_disk)}, "
                f"extra {sorted(on_disk - expected)}"
            )
    # Agents: `.claude/agents/*.md` is the source; every other tool that
    # projects them must hold at least one. Skipped when there is no source.
    agents = agent_dir(tool)
    source = root / ".claude" / "agents"
    if agents is not None and tool != "claude" and source.is_dir() \
            and any(source.glob("*.md")) and not any((root / agents).glob("*.md")):
        return "DRIFT_DETECTED", f"{agents} holds no projected agents"
    plugin = plugin_file(tool)
    if plugin is not None and not (root / plugin).is_file():
        return "DRIFT_DETECTED", f"{plugin} is absent"
    return "IN_SYNC", f"{HARNESSES[tool]}/ resolves structurally"


def harness_sync(root: Path) -> dict[str, Any]:
    harnesses: list[dict[str, Any]] = []
    for tool in enabled_tools(root):
        state, detail, source = _measure_harness(root, tool)
        harnesses.append({
            "tool": tool,
            "prefix": HARNESSES[tool],
            "state": state,
            "source": source,
            "detail": detail,
        })
    if not root.exists():
        overall = "UNKNOWN"
    elif any(h["state"] == "DRIFT_DETECTED" for h in harnesses):
        overall = "DRIFT_DETECTED"
    elif any(h["state"] == "UNKNOWN" for h in harnesses):
        overall = "UNKNOWN"
    else:
        overall = "IN_SYNC"
    return {"state": overall, "harnesses": harnesses}


# --------------------------------------------------------------------------
# 2. skills and CLI entrypoints
# --------------------------------------------------------------------------
def skill_manifests(root: Path) -> list[dict[str, Any]]:
    skills_dir = root / "skills"
    rows: list[dict[str, Any]] = []
    if skills_dir.is_dir():
        names = sorted(d.name for d in skills_dir.iterdir() if d.is_dir() and d.name != "_core")
    else:
        names = []
    # Derived from the same inventory the rows are, so a name can no longer be
    # reported as absent-but-core: what is not installed is not described. The
    # loop that used to append those rows went with the roster that made them
    # possible, and the absent inventory is reported as a warning instead.
    core_names = {name for name, _ in front_door_skills(root)}
    for name in names:
        manifest = skills_dir / name / "SKILL.md"
        text = _read_text(manifest)
        rows.append({
            "name": name,
            "path": f"skills/{name}/SKILL.md",
            "state": "WIRED" if text else "MISSING",
            "core": name in core_names,
            "bytes": len(text) if text else 0,
        })
    rows.sort(key=lambda row: row["name"])
    return rows


def cli_entrypoints(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, relative in front_door_skills(root):
        script = root / "skills" / name / relative
        if not script.is_file():
            rows.append({"skill": name, "path": f"skills/{name}/{relative}",
                         "state": "MISSING", "exit_code": None, "detail": "script absent"})
            continue
        code, output = _run([sys.executable, str(script), "--help"], root)
        state = "WIRED" if code == 0 else "TOOL_MISSING"
        rows.append({
            "skill": name,
            "path": f"skills/{name}/{relative}",
            "state": state,
            "exit_code": code,
            "detail": output.splitlines()[0] if code and output else "ok",
        })
    return rows


# --------------------------------------------------------------------------
# 3. agents
# --------------------------------------------------------------------------
def agent_integrity(root: Path) -> list[dict[str, Any]]:
    agents_dir = root / ".claude" / "agents"
    rows: list[dict[str, Any]] = []
    names = sorted(p.name for p in agents_dir.glob("*.md")) if agents_dir.is_dir() else []
    for required in REQUIRED_AGENTS:
        if required not in names:
            names.append(required)
    for filename in sorted(names):
        path = agents_dir / filename
        meta = _frontmatter(path)
        text = _read_text(path) or ""
        skills = _referenced_skills(text)
        tools = [token.strip() for token in str(meta.get("tools", "")).split(",") if token.strip()]
        unbound = [token for token in tools if token not in KNOWN_HARNESS_TOOLS]
        resolved = [skill for skill in skills if (root / "skills" / skill / "SKILL.md").is_file()]
        if not path.is_file():
            state, detail = "MISSING", "agent file absent"
        elif unbound:
            state, detail = "TOOL_UNBOUND", f"unbound tool(s): {', '.join(unbound)}"
        elif skills and len(resolved) != len(skills):
            state, detail = "MISSING", "referenced skill manifest absent"
        else:
            state, detail = "WIRED", "ok"
        rows.append({
            "name": path.stem,
            "path": f".claude/agents/{filename}",
            "state": state,
            "detail": detail,
            "skills": skills,
            "tools": tools,
            "unbound_tools": unbound,
            "stretch": meta.get("stretch"),
        })
    return rows


def _referenced_skills(text: str) -> list[str]:
    import re

    found: list[str] = []
    for match in re.finditer(r"\.claude/skills/([^/]+)/SKILL\.md", text):
        if match.group(1) not in found:
            found.append(match.group(1))
    return found


# --------------------------------------------------------------------------
# 4. environment
# --------------------------------------------------------------------------
def environment_health(root: Path) -> dict[str, Any]:
    # PATH first, then the fallback directories `smith doctor` also searches.
    tex_tools = {name: toolchain.find_tool(name) for name in LATEX_TOOLS}
    latex = next((tex_tools[name] for name in LATEX_ENGINES if tex_tools[name]), None)
    packages = []
    for name in REQUIRED_PACKAGES:
        try:
            present = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            present = False
        packages.append({"name": name, "state": "WIRED" if present else "TOOL_MISSING"})
    node = shutil.which("node")
    return {
        "python": {
            "executable": sys.executable,
            "version": ".".join(str(part) for part in sys.version_info[:3]),
            "state": "WIRED" if sys.version_info >= (3, 11) else "TOOL_MISSING",
        },
        "latex": {
            "engine": latex,
            "state": "WIRED" if latex else "TOOL_MISSING",
            "tools": tex_tools,
        },
        "node": {
            "executable": node,
            "state": "WIRED" if node else "TOOL_MISSING",
            "required": False,
        },
        "packages": packages,
    }


# --------------------------------------------------------------------------
# wiring matrix
# --------------------------------------------------------------------------
def wiring_matrix(root: Path, harness: dict[str, Any], agents: list[dict[str, Any]],
                  skills: list[dict[str, Any]], gates: list[str]) -> list[dict[str, Any]]:
    skill_state = {row["name"]: row["state"] for row in skills}
    harness_state = {h["tool"]: h["state"] for h in harness["harnesses"]}
    gate_ids = set(gates)
    rows: list[dict[str, Any]] = []
    for agent in agents:
        for skill in agent["skills"] or [None]:
            tool_states = {tool: state for tool, state in harness_state.items()}
            row_state = "WIRED"
            if agent["state"] == "TOOL_UNBOUND":
                row_state = "UNBOUND"
            elif skill is not None and skill_state.get(skill) != "WIRED":
                row_state = "TOOL_MISSING"
            elif any(state == "DRIFT_DETECTED" for state in tool_states.values()):
                row_state = "DRIFT"
            elif any(state == "UNKNOWN" for state in tool_states.values()):
                row_state = "UNVERIFIED"
            for tool, state in tool_states.items():
                mapped = [g for g in SKILL_GATES.get(skill or "", ()) if g in gate_ids]
                rows.append({
                    "harness": tool,
                    "harness_state": state,
                    "agent": agent["name"],
                    "skill": skill,
                    "gate": mapped[0] if mapped else None,
                    "state": row_state,
                })
    return rows


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------
def get_wiring_health(root: Path | str) -> dict[str, Any]:
    """Derive the read-only wiring-diagnostics payload for a workspace."""
    root_path = Path(root).expanduser()
    harness = harness_sync(root_path)
    skills = skill_manifests(root_path)
    clis = cli_entrypoints(root_path)
    agents = agent_integrity(root_path)
    environment = environment_health(root_path)

    gate_ids = ("writing-readiness", "coupling-verification", "grounding-style-leak", "diagram-raster")
    matrix = wiring_matrix(root_path, harness, agents, skills, gate_ids)

    components = 0
    healthy = 0
    for row in harness["harnesses"]:
        components += 1
        healthy += 1 if row["state"] == "IN_SYNC" else 0
    for row in skills:
        components += 1
        healthy += 1 if row["state"] == "WIRED" else 0
    for row in clis:
        components += 1
        healthy += 1 if row["state"] == "WIRED" else 0
    for row in agents:
        components += 1
        healthy += 1 if row["state"] == "WIRED" else 0
    packages = environment["packages"]
    for row in packages:
        components += 1
        healthy += 1 if row["state"] == "WIRED" else 0

    if healthy == components:
        state = "HEALTHY"
    elif healthy >= components * 0.6:
        state = "DEGRADED"
    else:
        state = "BLOCKED"

    warnings: list[str] = []
    if not (root_path / "skills").is_dir():
        warnings.append(
            "no skills/ inventory in this workspace, so no skill or front-door "
            "row could be derived -- every skill dimension below is empty, not "
            "clean")
    if harness["state"] == "DRIFT_DETECTED":
        warnings.append("harness drift detected: regenerate with scripts/sync-repo-harness.py")
    elif harness["state"] == "UNKNOWN":
        warnings.append("harness sync could not be measured (no generator and no readable workspace config)")
    missing_tools = [row["name"] for row in packages if row["state"] != "WIRED"]
    if missing_tools:
        warnings.append("missing Python package(s): " + ", ".join(missing_tools))
    if environment["latex"]["state"] != "WIRED":
        warnings.append("no LaTeX engine found (pdflatex/xelatex/lualatex): compilation will fail")

    return {
        "generated_at": _utc_now(),
        "summary": {
            "state": state,
            "components_total": components,
            "components_healthy": healthy,
            "warnings": warnings,
        },
        "harness_sync": harness,
        "skills": skills,
        "cli_entrypoints": clis,
        "agents": agents,
        "environment": environment,
        "matrix": matrix,
    }
