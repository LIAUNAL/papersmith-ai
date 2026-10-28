"""What `remote_cli generate-jobs` and `generate-job --dataset` derive from
what the target and the workspace already declare (remote-preflight S2, S3).

Pure readers, no network and no writes: the target's `__steps__` (read with
`ast`, never imported, exactly as the implementation engine reads it), the
`schedule` output of the remote-parallelism skill, the target's pinned
requirements, and the datasets skill's registry (through that skill's own
`job_input`, so the registry has one reader). Names no service: every
service-specific fact is a class attribute of the adapter that declares it
(`CODE_BUNDLE_MAX_BYTES`, `INPUT_DATASETS_HOST`, `PROVIDED_REQUIREMENTS`).
"""
from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence


class JobPlanError(Exception):
    """A refusal, its message starting with its code."""


#: The `__steps__` keys this reader uses, spelled as the implementation
#: engine spells them (`STEP_KEYS` in `implementation_engine.py`).
STEPS_DECLARATION = "__steps__"
PLACEMENT_REMOTE = "remote"
NOTEBOOKS_ROOT = "Notebooks"


# ------------------------------------------------------------------ steps
def _read_literal(path: Path, name: str):
    if not path.is_file():
        return None
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise JobPlanError(f"STEPS_UNREADABLE: {path} does not parse: {exc}") from None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            value = node.value
        elif (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
              and node.target.id == name and node.value is not None):
            value = node.value
        else:
            continue
        try:
            return ast.literal_eval(value)
        except ValueError:
            raise JobPlanError(f"STEPS_UNREADABLE: {name} in {path} is not a literal") from None
    return None


def declared_steps(target: Path, product: str) -> dict:
    """The product's `__steps__`, read from `src/<Package>/__init__.py` then
    `config.py` (the package is the product name with `-` as `_`)."""
    root = target / "src" / product.replace("-", "_")
    for candidate in ("__init__.py", "config.py"):
        found = _read_literal(root / candidate, STEPS_DECLARATION)
        if isinstance(found, dict):
            return found
    return {}


def _text(entry: Mapping, key: str) -> str | None:
    value = entry.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def produces(entry: Mapping) -> list[str]:
    roots = entry.get("produces")
    return [r.strip().strip("/") for r in roots or [] if isinstance(r, str) and r.strip()] \
        if isinstance(roots, list) else []


def step_notebook(entry: Mapping) -> str | None:
    """The first notebook the step's `produces` names under `Notebooks/`."""
    for root in produces(entry):
        parts = root.split("/")
        if parts[0] == NOTEBOOKS_ROOT and root.endswith(".ipynb"):
            return root
    return None


def carry_paths(entry: Mapping) -> list[str]:
    """The step's `produces` roots that are data, not its notebooks: what a
    continuation session needs from the one before it."""
    return [root for root in produces(entry) if root.split("/")[0] != NOTEBOOKS_ROOT]


def remote_steps(steps: Mapping) -> tuple[list[tuple[str, dict]], list[dict]]:
    """`([(step, entry), ...] remote, [{step, reason}, ...] skipped)`, in
    declaration order."""
    remote, skipped = [], []
    for name, entry in steps.items():
        entry = entry if isinstance(entry, dict) else {}
        placement = entry.get("placement")
        if placement == PLACEMENT_REMOTE:
            remote.append((str(name), entry))
        else:
            skipped.append({"step": str(name), "reason": (
                f"placement {placement!r}" if placement else "no placement declared")})
    return remote, skipped


# --------------------------------------------------------------- schedule
def schedule_services(path: Path) -> dict[str, list[str]]:
    """`{step id: [services]}` from a `schedule` OUTPUT (its `steps[].id`
    and the `services` it chose). The schedule's input plan is refused: its
    `services` are the allowed ones, not a decision."""
    import json
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise JobPlanError(f"SCHEDULE_UNREADABLE: {path}: {exc}") from None
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise JobPlanError(f"SCHEDULE_UNREADABLE: {path} has no steps list")
    if "schema" in data and "makespanMinutes" not in data:
        raise JobPlanError(
            f"SCHEDULE_IS_A_PLAN: {path} is the schedule's input plan, whose services are only "
            "the allowed ones. Run `parallelism_cli.py schedule --plan "
            f"{path} ...` and pass its output to --from-schedule")
    chosen: dict[str, list[str]] = {}
    for item in data["steps"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise JobPlanError(f"SCHEDULE_UNREADABLE: {path}: a step has no id")
        services = item.get("services")
        if not isinstance(services, list) or not services or \
                not all(isinstance(s, str) and s for s in services):
            raise JobPlanError(f"SCHEDULE_UNREADABLE: {path}: step {item['id']!r} names no "
                               "service")
        chosen[item["id"]] = list(dict.fromkeys(services))
    return chosen


# ----------------------------------------------------------- requirements
_REQUIREMENT_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def requirement_name(spec: str) -> str:
    match = _REQUIREMENT_NAME.match(spec.strip())
    return re.sub(r"[-_.]+", "-", match.group(1)).lower() if match else spec.strip().lower()


def pinned_requirements(target: Path) -> list[str]:
    """The target's own requirement specifiers: `requirements.txt` lines
    (comments, blank lines and pip options left out), else
    `pyproject.toml`'s `[project].dependencies`. `[]` when it declares none."""
    path = target / "requirements.txt"
    if path.is_file():
        found = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split(" #", 1)[0].strip()
            if line and not line.startswith(("#", "-")):
                found.append(line)
        return found
    pyproject = target / "pyproject.toml"
    if pyproject.is_file() and sys.version_info >= (3, 11):
        import tomllib
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        deps = (data.get("project") or {}).get("dependencies") or []
        return [d for d in deps if isinstance(d, str) and d.strip()]
    return []


def without_provided(requirements: Sequence[str], provided: Sequence[str]) -> list[str]:
    """The requirements minus every distribution the worker image provides
    (an adapter's `PROVIDED_REQUIREMENTS`; empty means all are installed)."""
    names = {requirement_name(p) for p in provided or ()}
    return [r for r in requirements if requirement_name(r) not in names]


# ---------------------------------------------------------------- the repo
def _git(target: Path, *args: str) -> str | None:
    ran = subprocess.run(["git", "-C", str(target), *args], capture_output=True, text=True)
    return ran.stdout.strip() if ran.returncode == 0 and ran.stdout.strip() else None


def target_remote(target: Path) -> tuple[str | None, str | None]:
    """`(origin URL, current branch)` of the target, either `None` when git
    has none."""
    branch = _git(target, "rev-parse", "--abbrev-ref", "HEAD")
    return _git(target, "remote", "get-url", "origin"), (None if branch == "HEAD" else branch)


# ---------------------------------------------------------------- datasets
def _datasets_cli():
    name = "remote_execution_datasets_cli"
    if name not in sys.modules:
        script = Path(__file__).resolve().parents[2] / "datasets" / "scripts" / "datasets_cli.py"
        if not script.is_file():
            raise JobPlanError(f"DATASETS_SKILL_MISSING: {script} does not exist; run "
                               "`smith upgrade`")
        spec = importlib.util.spec_from_file_location(name, script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def dataset_inputs(workspace: Path, slugs: Sequence[str],
                   attach_host: str | None) -> tuple[list[str], dict]:
    """`(refs, datasetChecks)` for the named registry slugs, or a refusal.
    `attach_host` is the adapter's `INPUT_DATASETS_HOST`: a dataset another
    host serves is refused `DATASET_HOST_NOT_ATTACHABLE`."""
    module = _datasets_cli()
    refs, checks = [], {}
    for slug in slugs:
        try:
            found = module.job_input(Path(workspace), slug)
        except module.Refusal as exc:
            raise JobPlanError(f"{exc.code}: {exc.message}") from None
        if attach_host and found["host"] and found["host"] != attach_host:
            raise JobPlanError(
                f"DATASET_HOST_NOT_ATTACHABLE: {slug} resolves to {found['ref']} on the "
                f"{found['host']} dataset host, and this service attaches datasets from "
                f"{attach_host} only: publish it there with the operator's consent "
                "(`/datasets publish`), or run the job on a service that downloads it")
        if found["ref"] not in refs:
            refs.append(found["ref"])
            checks[found["ref"]] = found["check"]
    return refs, checks
