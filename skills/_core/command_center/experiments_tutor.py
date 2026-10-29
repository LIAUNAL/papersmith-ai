"""Backend of the experiments panel's tutor (the `experiments-tutor` skill).

A second profile of ``tutor``'s machinery: the same headless, read-only turn of
the reader's own agent CLI, its own thread under
``.papersmith/experiments-tutor/`` and its own lock, grounded in a size-capped
digest of the experiments instead of the paper's mathematics.

The digest is built from ``experiments_view``'s protocol, product and dataset
readers -- never the whole view, whose remote-accounts, services and
local-environment sections probe credentials and spawn processes -- and keeps
an explicit whitelist of fields: run counts but not the ledger, table headers
but not their rows. Every path it names passes ``_exposed`` first, so a
credential store, ``.papersmith/team.json``, a ``.remote-execution/`` file or a
token never reaches the agent through it, and no path it names is a link or
resolves outside the workspace. The CLI enforces the same boundary on the
agent's own reads: ``deny_rules`` hands ``claude -p`` Read deny rules for those
places and the home credential folders (``Read`` rules also bound its Grep
searches and listings). ``measured`` says whether any
product holds a measurement; when it is false the prompt says "nothing
measured yet" and the doctrine forbids supplying a number.

The agent never writes; a change of decision comes back as
``deliberation_prompt`` for ``/experimental-deliberation``, where the human
gate lives.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Callable

from . import experiments_view as ev
from .state_extractor import credentials_store, inbox_directory
from .terminal import REMOTE_MCP_TOKEN_DIR
from .tutor import HISTORY_IN_PROMPT, MAX_MESSAGE, Profile, TutorError, converse

FOLDER = (".papersmith", "experiments-tutor")
MODES = ("ask", "explain", "evaluate")
#: The decision areas the skill's doctrine covers, plus ``general``.
AREAS = ("architecture", "hyperparameters", "ablation", "significance", "toy-set", "training",
         "upper-bounds", "baselines", "validation", "compute", "reproducibility", "general")
LEVELS = ("sin-evidencia", "declarada", "justificada", "controlada", "defendible")
MAX_DIGEST_CHARS = 24_000
MAX_PRODUCTS = 12
MAX_ROWS = 20
MAX_TABLES = 12
MAX_STUDIES = 8
MAX_EXPERIMENTS = 20
MAX_DATASETS = 40
TEXT = 300

#: Path parts and file names that hold secrets; a path carrying one is dropped.
SECRET_PARTS = (".remote-execution", ".ssh")
SECRET_NAMES = ("team.json", "access_token", "token", "token.json", "credentials.json")
#: Read deny rules for the CLI: gitignore-style paths, ``./`` from the
#: workspace (the agent's working directory), ``~/`` from the home.
DENY_READ = ("./.remote-execution/**", "./**/.remote-execution/**", "./.papersmith/team.json",
             "./.env*", "./**/.env*", "./**/.ssh/**",
             *(f"./**/{name}" for name in SECRET_NAMES),
             "~/.ssh/**", f"~/{REMOTE_MCP_TOKEN_DIR}/**", "~/.config/**")
#: A declared prefix the rule list can carry verbatim: no parenthesis or comma
#: (the CLI splits its list there) and no glob character.
_PLAIN_PREFIX = re.compile(r"[\w.\- /]+/")

TURN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reply", "question", "assessment", "next_step", "decision_area", "evidence",
                 "risks", "deliberation_prompt"],
    "properties": {
        "reply": {"type": "string"},
        "question": {"type": "string"},
        "assessment": {
            "type": "object",
            "additionalProperties": False,
            "required": ["level", "label", "evidence", "gaps"],
            "properties": {
                "level": {"type": "integer", "minimum": 0, "maximum": 4},
                "label": {"type": "string", "enum": list(LEVELS)},
                "evidence": {"type": "string"},
                "gaps": {"type": "array", "items": {"type": "string"}},
            },
        },
        "next_step": {"type": "string"},
        "decision_area": {"type": "string", "enum": list(AREAS)},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "deliberation_prompt": {"type": "string"},
    },
}

_FALLBACK_DOCTRINE = (
    "You are a Socratic experiments tutor. Read the protocol, approvals, code and results the "
    "digest names before you speak, ask exactly one question per turn, assess the design 0-4 "
    "with quoted evidence, never invent a measured number (say 'nothing measured yet'), never "
    "read credentials, never write a file, and draft any change of decision as an instruction "
    "for /experimental-deliberation. Answer with one JSON object only."
)


# --------------------------------------------------------------------------
# digest
# --------------------------------------------------------------------------
def _secret_paths(root: Path) -> tuple[str, ...]:
    """Workspace-relative prefixes the workspace's own skills declare as secret."""
    out = []
    store = credentials_store(root)
    if store is not None:
        try:
            out.append(store.parent.resolve().relative_to(root).as_posix() + "/")
        except (OSError, ValueError):
            pass
    inbox = inbox_directory(root)
    if inbox:
        out.append(inbox.strip("/") + "/")
    return tuple(out)


def deny_rules(root: Path) -> tuple[str, ...]:
    """The Read rules ``claude -p`` refuses for this workspace: the fixed
    secrets and the credential store and inbox its own skills declare. A
    declared prefix the list cannot carry verbatim stays covered only by the
    digest's filter and the doctrine."""
    root = Path(root).expanduser().resolve()
    declared = (f"./{prefix}**" for prefix in _secret_paths(root) if _PLAIN_PREFIX.fullmatch(prefix))
    return tuple(f"Read({path})" for path in (*DENY_READ, *declared))


def _inside(root: Path, path: Path) -> bool:
    """``path`` exists, is no link, and resolves inside the workspace."""
    try:
        return not path.is_symlink() and path.resolve(strict=True).is_relative_to(root)
    except (OSError, RuntimeError):
        return False


def _exposed(rel: str, secret: tuple[str, ...]) -> bool:
    parts = rel.split("/")
    return (any(part in SECRET_PARTS or part.startswith(".env") for part in parts)
            or parts[-1] in SECRET_NAMES or any(rel.startswith(prefix) for prefix in secret))


def _clip(value: Any, limit: int = TEXT) -> str:
    return ev._clip(value, limit)


def _protocol(protocol: dict[str, Any] | None) -> dict[str, Any] | None:
    if protocol is None:
        return None
    return {"file": protocol["file"], "revision": protocol["revision"],
            "validation_scheme": protocol["validation_scheme"],
            "experiments": [{"id": e["id"], "title": e["title"], "priority": e["priority"],
                             "hypothesis": _clip(e["hypothesis"]),
                             "success_criterion": _clip(e["success_criterion"]), "cost": e["cost"],
                             "expected_reports": [{"title": r.get("title", ""), "headers": r.get("headers", [])}
                                                  for r in e["expected_reports"]]}
                            for e in protocol["experiments"][:MAX_EXPERIMENTS]]}


def _product(root: Path, view: dict[str, Any], secret: tuple[str, ...]) -> dict[str, Any]:
    folder = root / view["path"]
    keep = lambda rel: rel and not _exposed(rel, secret)  # noqa: E731
    read = [f"{view['path']}/{marker}" for marker in ("AGREED.md", "Experimental_AGREED.md")
            if (folder / marker).is_file() and _inside(root, folder / marker)]
    if (folder.parent / "src").is_dir() and _inside(root, folder.parent / "src"):
        read.append(f"implementations/{view['repo']}/src/")
    significance = [{k: row.get(k) for k in ("comparison", "test", "statistic", "p_value", "p_adjusted",
                                              "correction", "effect_size", "effect_size_name", "n", "alpha")}
                    | {"file": row["file"]}
                    for row in view["significance"] if keep(row.get("file"))][:MAX_ROWS]
    hpo = [{k: study.get(k) for k in ("study", "arm", "fold", "nTrials", "complete", "pruned", "failed",
                                       "bestValue", "bestParams", "objective", "importance", "file")}
           for study in view["hpo"] if keep(study.get("file"))][:MAX_STUDIES]
    timing = view["timing"]
    if timing is not None and not keep(timing.get("file")):
        timing = None
    return {
        "repo": view["repo"], "name": view["name"], "kind": view["kind"], "path": view["path"],
        "read": [rel for rel in read if keep(rel)],
        "significance": significance,
        "hpo": hpo,
        "tables": [{"path": t["path"], "headers": t["headers"], "rows": len(t.get("rows") or [])}
                   for t in view["tables"] if keep(t.get("path"))][:MAX_TABLES],
        "convergence": len(view["convergence"]),
        "figures": len(view["figures"]),
        "timing": timing,
        "runs": {"count": view["runs"]["count"], "by_state": view["runs"]["by_state"]},
        "diagrams": [{"kind": d["kind"], "validation": d["validation"]} for d in view["diagrams"]],
    }


def _measured(product: dict[str, Any]) -> bool:
    timing = product["timing"] or {}
    return bool(product["significance"] or product["convergence"] or timing.get("measurements")
                or any(t["rows"] for t in product["tables"])
                or any(s.get("bestValue") is not None or s.get("complete") for s in product["hpo"]))


#: Each step trims the digest further; they run in order until it fits.
_SHRINK: tuple[Callable[[dict[str, Any]], None], ...] = (
    lambda d: [p.update(significance=p["significance"][:5], tables=p["tables"][:5],
                        hpo=[{k: v for k, v in s.items() if k not in ("bestParams", "importance")}
                             for s in p["hpo"][:3]]) for p in d["products"]],
    lambda d: d["protocol"] and [e.update(expected_reports=[], hypothesis=_clip(e["hypothesis"], 120),
                                          success_criterion=_clip(e["success_criterion"], 120))
                                 for e in d["protocol"]["experiments"]],
    lambda d: d.update(products=d["products"][:6],
                       datasets={**d["datasets"], "items": d["datasets"]["items"][:10]}),
    lambda d: d.update(products=[{k: p[k] for k in ("repo", "name", "kind", "path", "read")}
                                 for p in d["products"]]),
    lambda d: d.update(protocol=d["protocol"] and {k: d["protocol"][k] for k in ("file", "revision")},
                       datasets={"registry": d["datasets"]["registry"], "items": []}),
)


def _fit(digest: dict[str, Any]) -> dict[str, Any]:
    for shrink in _SHRINK:
        if len(json.dumps(digest, ensure_ascii=False)) <= MAX_DIGEST_CHARS:
            return digest
        shrink(digest)
        digest["truncated"] = True
    if len(json.dumps(digest, ensure_ascii=False)) > MAX_DIGEST_CHARS:
        digest.update(products=[], datasets={"registry": None, "items": []},
                      read=digest["read"][:40])
    return digest


def digest(root: Path) -> dict[str, Any]:
    """What a turn is grounded in: the latest protocol, each product's evidence
    and the datasets registry, as a whitelist of fields under a size cap."""
    root = Path(root).expanduser().resolve()
    secret = _secret_paths(root)
    warnings: list[str] = []
    reader = ev._Reader(root, warnings)
    protocol = _protocol(ev._parse_protocol(root, reader))
    ledgers, _cut, _escaped = ev._discover_ledgers(root)
    by_folder = {path.parent.parent: path for path in ledgers}
    products = [_product(root, ev._product(root, repo, folder, by_folder.get(folder), warnings), secret)
                for repo, folder in ev._product_dirs(root, reader)[:MAX_PRODUCTS]]
    registry = ev._datasets(root, reader)
    datasets = {"registry": registry["registry"],
                "items": [{k: item[k] for k in ("slug", "role", "title", "license", "qc", "prepared",
                                                 "preparation_version")}
                          for item in registry["items"][:MAX_DATASETS]]}
    read = ([protocol["file"]] if protocol else []) + [rel for p in products for rel in p["read"]]
    return _fit({"measured": any(_measured(p) for p in products), "truncated": False,
                 "protocol": protocol, "products": products, "datasets": datasets,
                 "read": [rel for rel in read if not _exposed(rel, secret)]})


# --------------------------------------------------------------------------
# prompt and turn
# --------------------------------------------------------------------------
def build_prompt(root: Path, message: str, mode: str, area: str, thread: dict[str, Any]) -> str:
    context = PROFILE.context(root)
    history = []
    for turn in thread["turns"][-HISTORY_IN_PROMPT:]:
        if turn.get("role") == "reader":
            history.append(f"OPERATOR ({turn.get('mode')}, {turn.get('area')}): {turn.get('message', '')[:1500]}")
        else:
            a = turn.get("assessment") or {}
            history.append(f"TUTOR ({turn.get('decision_area')}): asked \"{turn.get('question', '')[:500]}\"; "
                           f"assessed {a.get('level')} ({a.get('label')}): {a.get('evidence', '')[:300]}"
                           + ("; drafted a change for the deliberation" if turn.get("deliberation_prompt") else ""))
    files = "\n".join(f"- {rel}" for rel in context["read"]) or "- (none yet)"
    measured = ("" if context["measured"] else
                "No product holds a measurement: nothing measured yet. Say so, and never supply a number.\n\n")
    return (
        f"mode: {mode}\ndecision area: {area}\n\n"
        f"{measured}"
        f"The experiments digest (from /api/experiments):\n{json.dumps(context, ensure_ascii=False)}\n\n"
        f"Files to read before answering (Read, Glob, Grep):\n{files}\n\n"
        f"Conversation so far (oldest first):\n" + ("\n".join(history) or "(first turn)") + "\n\n"
        f"The operator says:\n{message}\n"
    )


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _valid(turn: Any) -> dict[str, Any]:
    if not isinstance(turn, dict):
        raise TutorError("the tutor's answer was not a JSON turn")
    for key in ("reply", "question", "next_step", "deliberation_prompt"):
        if not isinstance(turn.get(key), str):
            raise TutorError(f"the tutor's answer has no text `{key}`")
    if turn.get("decision_area") not in AREAS:
        raise TutorError("the tutor's answer has no known `decision_area`")
    for key in ("evidence", "risks"):
        if not _strings(turn.get(key)):
            raise TutorError(f"the tutor's answer has no `{key}` list")
    a = copy.deepcopy(turn.get("assessment"))
    if not (isinstance(a, dict) and type(a.get("level")) is int and 0 <= a["level"] <= 4
            and isinstance(a.get("evidence"), str) and _strings(a.get("gaps"))):
        raise TutorError("the tutor's answer has no usable `assessment`")
    a["label"] = LEVELS[a["level"]]
    return {**{key: turn[key] for key in TURN_SCHEMA["required"]}, "assessment": a}


def run_turn(root: Path, message: Any, mode: Any, area: Any, *,
             runner: Callable[..., tuple[Any, str]] | None = None) -> dict[str, Any]:
    root = Path(root)
    if mode not in MODES:
        raise TutorError(f"mode must be one of {', '.join(MODES)}")
    if area not in AREAS:
        raise TutorError(f"area must be one of {', '.join(AREAS)}")
    if not isinstance(message, str) or not message.strip():
        raise TutorError("write a message")
    message = message.strip()[:MAX_MESSAGE]
    return converse(PROFILE, root, {"mode": mode, "area": area, "message": message},
                    lambda thread: build_prompt(root, message, mode, area, thread), [], runner)


PROFILE = Profile(
    name="experiments",
    folder=FOLDER,
    doctrine=(".claude/agents/experiments-tutor.md", "skills/experiments-tutor/SKILL.md"),
    fallback=_FALLBACK_DOCTRINE,
    headless=("You are running headless inside the dashboard's experiments panel as the "
              "experiments tutor. Answer with exactly one JSON object in the turn shape; write "
              "no file; a change of decision goes in `deliberation_prompt`, drafted for "
              "/experimental-deliberation."),
    schema=TURN_SCHEMA,
    modes=MODES,
    context=digest,
    valid=_valid,
    tools=("Read", "Glob", "Grep"),
    deny=deny_rules,
)


__all__ = ["PROFILE", "TURN_SCHEMA", "AREAS", "MODES", "LEVELS", "MAX_DIGEST_CHARS", "digest",
           "deny_rules", "build_prompt", "run_turn"]
