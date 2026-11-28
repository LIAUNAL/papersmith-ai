"""The model each smith agent runs on, per harness, and the alerts about it.

``resolve_workspace(root)`` answers, for every ``.claude/agents/*.md`` of the
workspace and each harness the agent is projected to, whether the agent is
``pinned`` to a model there or ``inherits`` a harness-wide model, and which
model that is when a config file says so. ``smith`` writes ``model:`` only
into the Claude Code definitions; the OpenCode, Pi and Antigravity
projections drop it (``src/papersmith/generators.py``), so there the agent
inherits its session's model unless that harness's own config pins it.

Where each harness keeps the model (only the model keys are read; every other
key of a config file, credentials included, is ignored and never returned):

* Claude Code -- https://code.claude.com/docs/en/sub-agents ("Choose a
  model"): a subagent's model is the first of the per-invocation parameter,
  the definition's ``model`` field (``inherit`` included), the
  ``CLAUDE_CODE_SUBAGENT_MODEL`` variable, then the main conversation's model;
  ``CLAUDE_CODE_SUBAGENT_MODEL_FORCE`` makes Claude Code ignore the field.
  https://code.claude.com/docs/en/settings: ``model`` and ``env`` are read
  from ``.claude/settings.local.json`` over ``.claude/settings.json`` over
  ``~/.claude/settings.json`` (``CLAUDE_CONFIG_DIR`` moves ``~/.claude``);
  managed settings, ``--model`` and ``ANTHROPIC_MODEL`` can still override
  them at launch and are not read here.
* OpenCode -- https://opencode.ai/docs/agents/: a subagent "inherits the parent
  session's model when none is configured". https://opencode.ai/docs/config/:
  ``model`` (``provider/model``) from ``~/.config/opencode/opencode.json(c)``,
  overridden by the project's ``opencode.json(c)``, overridden by
  ``.opencode/opencode.json(c)``; the system config (``/etc/opencode``)
  overrides them all and is not read here.
* Pi -- https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/settings.md
  and configuration.md: ``defaultProvider`` and ``defaultModel`` in
  ``.pi/settings.json`` over ``<agent-dir>/settings.json`` (``~/.pi/agent``,
  moved by ``PI_CODING_AGENT_DIR``). Its agents need the third-party
  pi-subagents package; https://github.com/nicobailon/pi-subagents/blob/main/docs/models.md:
  ``subagents.agentOverrides.<name>.model`` wins over the agent file, then
  ``subagents.defaultModel``, then the parent session model, in the same two
  files ("project wins").
* Antigravity -- https://antigravity.google/docs/subagents: ``model`` defaults
  to ``inherit`` (values ``inherit``/``flash``/``pro``);
  https://antigravity.google/docs/models documents ``/model`` in ``agy``
  ("Your choice persists across sessions"), ``agy --model`` and ``agy
  models``, but no settings file for the default model, so it is unknown.

Run it in a terminal: ``python -m skills._core.command_center.agent_models
[<workspace>] [--json]``. Bounded and contained: it never raises on a bad
file; an unreadable config is a note, never a guess.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

#: Harnesses in the order the dashboard and the report list them.
HARNESSES: tuple[str, ...] = ("claude", "opencode", "pi", "antigravity")
#: The directory each harness's agent projection lives in.
PROJECTION_DIRS: dict[str, str] = {
    "claude": ".claude/agents", "opencode": ".opencode/agents",
    "pi": ".pi/agents", "antigravity": ".agents/agents",
}
LABELS: dict[str, str] = {
    "claude": "Claude Code", "opencode": "OpenCode", "pi": "Pi", "antigravity": "Antigravity",
}
#: The LLM judges, pinned to the strongest model (tests/test_agents.py JUDGE_AGENTS).
JUDGES = frozenset({"contract-auditor", "section-grounding-auditor", "ai-auditor", "paper-reviewer"})
#: A model whose name holds one of these is a top-tier one. ``opusplan`` runs
#: Sonnet outside plan mode, so it is not.
STRONG_MARKERS: tuple[str, ...] = ("opus", "fable")
STRONG_ALIASES = frozenset({"best"})
WEAK_ALIASES = frozenset({"opusplan"})

MAX_CONFIG_BYTES = 1_000_000

HOW_TO_SEE: dict[str, str] = {
    "claude": "run /model or /status in Claude Code to see it",
    "opencode": "OpenCode shows the session's model in its interface",
    "pi": "Pi shows the session's model; `defaultModel` in its settings.json sets it",
    "antigravity": "run /model in agy to see it; agy models lists the model ids",
}


def is_strong(model: str | None) -> bool:
    """True when ``model`` names a top-tier model (Opus, Fable, ``best``)."""
    text = (model or "").strip().lower()
    if not text or text in WEAK_ALIASES:
        return False
    return text in STRONG_ALIASES or any(marker in text for marker in STRONG_MARKERS)


def suggestion(harness: str, name: str) -> str:
    """How to pin another model for ``name`` in ``harness`` so `smith upgrade` keeps it."""
    if harness == "claude":
        return (f"Claude Code: `smith upgrade` rewrites `.claude/agents/{name}.md`, so an edited "
                "`model:` line there does not last, and there is no per-agent pin outside it. "
                "Set `CLAUDE_CODE_SUBAGENT_MODEL` (an alias such as `opus`) under `env` in "
                "`.claude/settings.local.json`, which smith never writes: every agent without its "
                "own `model:` runs on it; add `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` to put every "
                "agent, pinned ones included, on that model. `model` in that file, or "
                "`claude --model <alias>`, sets the session.")
    if harness == "opencode":
        return (f"OpenCode: `smith upgrade` regenerates `.opencode/agents/{name}.md` and "
                "`opencode.json`, and OpenCode's docs do not say whether an `agents` entry in a "
                "config file wins over a Markdown agent, so there is no documented per-agent pin "
                "that survives `smith upgrade`. The agent inherits the session's model: set "
                "`model` (`provider/model`) in `~/.config/opencode/opencode.json`.")
    if harness == "pi":
        return (f"Pi (pi-subagents): set `subagents.agentOverrides.{name}.model` (`provider/model`) "
                "in `.pi/settings.json`, which `smith upgrade` never overwrites, or in "
                "`~/.pi/agent/settings.json`; it wins over the agent file. "
                "`subagents.defaultModel` sets every agent without a pin, and `pi --model "
                "<pattern>` the session.")
    if harness == "antigravity":
        return (f"Antigravity: `smith upgrade` regenerates `.agents/agents/{name}.md`, whose "
                "`model` only takes `inherit`, `flash` or `pro`, so there is no per-agent pin "
                "that survives `smith upgrade`. Choose the session's model with /model in agy "
                "(it persists across sessions) or `agy --model <id>`; `agy models` lists the ids.")
    return ""


# ---- config reading ---------------------------------------------------------

def _strip_jsonc(text: str) -> str:
    """``text`` without ``//`` and ``/* */`` comments or trailing commas outside strings."""
    out: list[str] = []
    i, n, in_string = 0, len(text), False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_string = False
        elif c == '"':
            in_string = True
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        elif c in "}]":
            j = len(out) - 1
            while j >= 0 and out[j].isspace():
                j -= 1
            if j >= 0 and out[j] == ",":
                del out[j]
            out.append(c)
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _read_json(path: Path, notes: list[str], label: str) -> dict | None:
    """The JSON object at ``path``, or None (absent, or a note when unreadable)."""
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > MAX_CONFIG_BYTES:
            notes.append(f"{label}: larger than {MAX_CONFIG_BYTES} bytes, not read")
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(_strip_jsonc(text) if path.suffix == ".jsonc" else text)
    except (OSError, ValueError) as exc:
        notes.append(f"{label}: unreadable ({exc.__class__.__name__}), its model is unknown")
        return None
    return data if isinstance(data, dict) else None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _home_label(path: Path, home: Path, root: Path) -> str:
    for base, prefix in ((root, ""), (home, "~/")):
        try:
            return prefix + path.relative_to(base).as_posix()
        except ValueError:
            continue
    return str(path)


def harness_defaults(root: Path | str, *, home: Path | str | None = None,
                     env: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """The harness-wide model settings each harness's config files declare.

    ``env`` only locates config directories (``CLAUDE_CONFIG_DIR``,
    ``PI_CODING_AGENT_DIR``); it defaults to the process environment.
    """
    base = Path(root)
    home_dir = Path(home) if home is not None else Path.home()
    environ = os.environ if env is None else env
    label = lambda path: _home_label(path, home_dir, base)  # noqa: E731
    notes: list[str] = []

    claude_user = Path(environ["CLAUDE_CONFIG_DIR"]) if environ.get("CLAUDE_CONFIG_DIR") else home_dir / ".claude"
    claude: dict[str, Any] = {"session": None, "subagent": None, "force": None}
    # Highest precedence first; the first file that sets a key wins.
    for path in (base / ".claude" / "settings.local.json", base / ".claude" / "settings.json",
                 claude_user / "settings.json"):
        data = _read_json(path, notes, label(path))
        if not data:
            continue
        where = label(path)
        if claude["session"] is None and _text(data.get("model")):
            claude["session"] = (_text(data.get("model")), where)
        block = data.get("env") if isinstance(data.get("env"), dict) else {}
        if claude["subagent"] is None and _text(block.get("CLAUDE_CODE_SUBAGENT_MODEL")):
            claude["subagent"] = (_text(block.get("CLAUDE_CODE_SUBAGENT_MODEL")), where)
        if claude["force"] is None and "CLAUDE_CODE_SUBAGENT_MODEL_FORCE" in block:
            flag = str(block.get("CLAUDE_CODE_SUBAGENT_MODEL_FORCE")).strip().lower()
            claude["force"] = (flag in ("1", "true", "yes", "on"), where)

    opencode: dict[str, Any] = {"session": None}
    candidates = []
    for folder in (base / ".opencode", base, home_dir / ".config" / "opencode"):
        candidates += [folder / "opencode.jsonc", folder / "opencode.json"]
    for path in candidates:
        data = _read_json(path, notes, label(path))
        if data and _text(data.get("model")):
            opencode["session"] = (_text(data.get("model")), label(path))
            break

    pi_dir = Path(environ["PI_CODING_AGENT_DIR"]) if environ.get("PI_CODING_AGENT_DIR") else home_dir / ".pi" / "agent"
    pi: dict[str, Any] = {"session": None, "default": None, "overrides": {}}
    for path in (base / ".pi" / "settings.json", pi_dir / "settings.json"):
        data = _read_json(path, notes, label(path))
        if not data:
            continue
        where = label(path)
        if pi["session"] is None and _text(data.get("defaultModel")):
            model = _text(data.get("defaultModel"))
            provider = _text(data.get("defaultProvider"))
            pi["session"] = (f"{provider}/{model}" if provider and "/" not in model else model, where)
        block = data.get("subagents") if isinstance(data.get("subagents"), dict) else {}
        if pi["default"] is None and _text(block.get("defaultModel")):
            pi["default"] = (_text(block.get("defaultModel")), where)
        overrides = block.get("agentOverrides") if isinstance(block.get("agentOverrides"), dict) else {}
        for name, entry in overrides.items():
            model = _text(entry.get("model")) if isinstance(entry, dict) else None
            if model and name not in pi["overrides"]:
                pi["overrides"][name] = (model, where)

    return {"claude": claude, "opencode": opencode, "pi": pi, "antigravity": {}, "notes": notes}


# ---- resolution and alerts ----------------------------------------------------

def _entry(harness: str, status: str, value: tuple[str, str] | None) -> dict[str, Any]:
    model, source = value if value else (None, None)
    return {"harness": harness, "label": LABELS[harness], "status": status, "model": model,
            "source": source, "how_to_see": HOW_TO_SEE[harness]}


def agent_model_entries(name: str, pinned: str, harnesses: Iterable[str],
                        defaults: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One entry per harness in ``harnesses``: pinned or inherited, and which model."""
    entries = []
    own = (pinned or "").strip()
    for harness in [h for h in HARNESSES if h in set(harnesses)]:
        if harness == "claude":
            cfg = defaults.get("claude") or {}
            force, subagent = cfg.get("force"), cfg.get("subagent")
            if force and force[0] and subagent:
                entries.append(_entry(harness, "pinned", (
                    subagent[0], f"CLAUDE_CODE_SUBAGENT_MODEL with CLAUDE_CODE_SUBAGENT_MODEL_FORCE in {force[1]}")))
            elif own and own.lower() != "inherit":
                entries.append(_entry(harness, "pinned", (own, f".claude/agents/{name}.md")))
            elif subagent:
                entries.append(_entry(harness, "inherits", (subagent[0], f"CLAUDE_CODE_SUBAGENT_MODEL in {subagent[1]}")))
            else:
                entries.append(_entry(harness, "inherits", cfg.get("session")))
        elif harness == "pi":
            cfg = defaults.get("pi") or {}
            override = (cfg.get("overrides") or {}).get(name)
            if override:
                entries.append(_entry(harness, "pinned", override))
            else:
                entries.append(_entry(harness, "inherits", cfg.get("default") or cfg.get("session")))
        else:
            entries.append(_entry(harness, "inherits", (defaults.get(harness) or {}).get("session")))
    return entries


def model_alerts(name: str, entries: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """A warning for a judge not confirmed on a top-tier model, a note for each inheriting entry."""
    alerts = []
    for entry in entries:
        harness, label, model = entry["harness"], entry["label"], entry.get("model")
        if name in JUDGES and not is_strong(model):
            runs_on = model or "the session's model, which smith cannot read"
            alerts.append({"level": "warning", "harness": harness,
                           "message": (f"{name} is a judge and on {label} it runs on {runs_on}: "
                                       "not confirmed as a top-tier model."),
                           "suggestion": suggestion(harness, name)})
        if entry.get("status") == "inherits":
            if model:
                message = f"On {label}, {name} inherits {model} ({entry.get('source')})."
            else:
                message = (f"On {label}, {name} inherits the session's model; smith cannot read it: "
                           f"{entry['how_to_see']}.")
            alerts.append({"level": "info", "harness": harness, "message": message,
                           "suggestion": suggestion(harness, name)})
    return alerts


def _pinned_in(path: Path) -> str:
    """The top-level ``model:`` of an agent definition's front matter, or ''."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("model:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return ""


def projected_harnesses(root: Path, filename: str) -> list[str]:
    return [h for h in HARNESSES if (root / PROJECTION_DIRS[h] / filename).is_file()]


def resolve_workspace(root: Path | str, *, home: Path | str | None = None,
                      env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Every agent of the workspace with its model per harness and its alerts."""
    base = Path(root)
    defaults = harness_defaults(base, home=home, env=env)
    agents_dir = base / PROJECTION_DIRS["claude"]
    if not agents_dir.is_dir():
        return {"agents": [], "notes": ["no .claude/agents/ directory in this workspace", *defaults["notes"]]}
    agents = []
    for path in sorted(agents_dir.glob("*.md")):
        entries = agent_model_entries(path.stem, _pinned_in(path), projected_harnesses(base, path.name), defaults)
        agents.append({"name": path.stem, "models": entries, "alerts": model_alerts(path.stem, entries)})
    return {"agents": agents, "notes": defaults["notes"]}


def describe(entry: Mapping[str, Any]) -> str:
    """One entry as ``<harness>: <model> (<how>)``."""
    if entry["status"] == "pinned":
        return f"{entry['harness']}: {entry['model']} (pinned, {entry['source']})"
    if entry.get("model"):
        return f"{entry['harness']}: inherits {entry['model']} ({entry['source']})"
    return f"{entry['harness']}: inherits the session's model ({entry['how_to_see']})"


def format_report(payload: Mapping[str, Any]) -> str:
    lines: list[str] = []
    for agent in payload.get("agents", []):
        lines.append(agent["name"] + (" [judge]" if agent["name"] in JUDGES else ""))
        lines.extend(f"  {describe(entry)}" for entry in agent["models"])
        for alert in agent["alerts"]:
            lines.append(f"  {'WARNING' if alert['level'] == 'warning' else 'note'}: {alert['message']}")
            if alert["level"] == "warning":
                lines.append(f"    how to pin: {alert['suggestion']}")
    lines.extend(f"note: {note}" for note in payload.get("notes", []))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None, *, home: Path | str | None = None,
         env: Mapping[str, str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    if "-h" in args or "--help" in args:
        print("usage: python -m skills._core.command_center.agent_models [<workspace>] [--json]\n"
              "Lists the model each agent runs on per harness (pinned or inherited), warns about\n"
              "judges not confirmed on a top-tier model and says how to pin another one.")
        return 0
    positional = [a for a in args if not a.startswith("-")]
    payload = resolve_workspace(Path(positional[0] if positional else "."), home=home, env=env)
    print(json.dumps(payload, ensure_ascii=False, indent=2) if as_json else format_report(payload), end="" if not as_json else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
