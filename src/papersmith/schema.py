"""Validation for the two JSON/YAML documents owned by a workspace.

The CLI validates the fields it consumes and leaves ``paper_ingestion`` (which
belongs to the paper-ingestion skill) opaque. This lets one
``papersmith.yaml`` serve both the orchestrator and the existing skill without
making either consumer own the other's schema.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import UserError

KNOWN_TOOLS = ("claude", "opencode", "pi", "antigravity")
KNOWN_SKILLS = (
    "paper-ingestion",
    "proposal-deliberation",
    "proposal-implementation",
    "remote-execution",
    "kaggle-accounts",
    "skill-audit",
)
KNOWN_PROVIDERS = ("local", "kaggle", "remote-ssh")
REMOTE_CHOICES = ("kaggle", "local", "slurm")
REMOTE_TARGETS = {
    "kaggle": "kaggle-gpu-pool",
    "local": "local-workstation",
    "slurm": "slurm-cluster",
}


def _fail(path: str, message: str) -> None:
    raise UserError(f"{path}: {message}")


def _mapping(value: Any, path: str) -> dict:
    if not isinstance(value, Mapping):
        _fail(path, "must be a mapping")
    return dict(value)


def _string(value: Any, path: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        _fail(path, "must be a non-empty string")
    return value


def _string_list(value: Any, path: str, *, allowed: tuple[str, ...] | None = None) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        _fail(path, "must be a list of non-empty strings")
    result = list(value)
    if allowed:
        unknown = [item for item in result if item not in allowed]
        if unknown:
            _fail(path, f"contains unsupported values: {', '.join(unknown)}")
    return result


def _number(value: Any, path: str, *, integer: bool = False) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "must be a number")
    if integer and not isinstance(value, int):
        _fail(path, "must be an integer")
    return value


TOOL_ALIASES: dict[str, str] = {
    "agy": "antigravity",
}


def validate_tools(tools: list[str] | tuple[str, ...]) -> list[str]:
    canonical = [TOOL_ALIASES.get(tool, tool) for tool in tools]
    unknown = [tool for tool in canonical if tool not in KNOWN_TOOLS]
    if unknown:
        _fail("tools", f"unsupported runtime(s): {', '.join(unknown)}")
    if len(set(canonical)) != len(canonical):
        _fail("tools", "must not contain duplicates")
    return canonical


def validate_papersmith_yaml(data: Any, *, require_compute: bool = True) -> dict:
    """Validate the orchestrator-owned portion of ``papersmith.yaml``."""
    root = _mapping(data, "papersmith.yaml")
    if "version" in root and root["version"] != "1":
        _fail("version", "must be the string '1'")
    if not require_compute and "version" not in root:
        return root

    for key in ("version", "name"):
        if key not in root:
            _fail(key, "is required")
    _string(root["version"], "version")
    _string(root["name"], "name")
    for key in ("title", "topic", "venue_target"):
        if key in root:
            _string(root[key], key, required=False)

    if "skills" in root:
        _string_list(root["skills"], "skills", allowed=KNOWN_SKILLS)
    if "environment" in root:
        environment = _mapping(root["environment"], "environment")
        for key, value in environment.items():
            _string(value, f"environment.{key}")

    targets_root = _mapping(root.get("compute_targets"), "compute_targets")
    default = _string(targets_root.get("default"), "compute_targets.default")
    targets = _mapping(targets_root.get("targets"), "compute_targets.targets")
    if default not in targets:
        _fail("compute_targets.default", f"does not name a configured target: {default!r}")
    for name, raw_target in targets.items():
        target = _mapping(raw_target, f"compute_targets.targets.{name}")
        provider = _string(target.get("provider"), f"compute_targets.targets.{name}.provider")
        if provider not in KNOWN_PROVIDERS:
            _fail(f"compute_targets.targets.{name}.provider", f"must be one of {KNOWN_PROVIDERS}")

    profiles = _mapping(root.get("execution_profiles"), "execution_profiles")
    for name, raw_profile in profiles.items():
        profile = _mapping(raw_profile, f"execution_profiles.{name}")
        profile_target = _string(profile.get("target"), f"execution_profiles.{name}.target")
        if profile_target not in targets:
            _fail(f"execution_profiles.{name}.target", f"does not name a configured target: {profile_target!r}")
        _string(profile.get("entrypoint"), f"execution_profiles.{name}.entrypoint")
        if "env_vars" in profile:
            env_vars = _mapping(profile["env_vars"], f"execution_profiles.{name}.env_vars")
            for key, value in env_vars.items():
                _string(key, f"execution_profiles.{name}.env_vars key")
                _string(value, f"execution_profiles.{name}.env_vars.{key}")
        if "timeout_seconds" in profile:
            _number(profile["timeout_seconds"], f"execution_profiles.{name}.timeout_seconds", integer=True)
        if "sharding" in profile:
            sharding = _mapping(profile["sharding"], f"execution_profiles.{name}.sharding")
            if "enabled" in sharding and not isinstance(sharding["enabled"], bool):
                _fail(f"execution_profiles.{name}.sharding.enabled", "must be boolean")
            if "strategy" in sharding:
                _string(sharding["strategy"], f"execution_profiles.{name}.sharding.strategy")
            if "parameter" in sharding:
                _string(sharding["parameter"], f"execution_profiles.{name}.sharding.parameter")
            if "values" in sharding and not isinstance(sharding["values"], list):
                _fail(f"execution_profiles.{name}.sharding.values", "must be a list")
            if "distribute_across_accounts" in sharding and not isinstance(sharding["distribute_across_accounts"], bool):
                _fail(f"execution_profiles.{name}.sharding.distribute_across_accounts", "must be boolean")
        if "artifacts" in profile:
            artifacts = _mapping(profile["artifacts"], f"execution_profiles.{name}.artifacts")
            if "collect" in artifacts:
                _string_list(artifacts["collect"], f"execution_profiles.{name}.artifacts.collect")
            if "destination" in artifacts:
                _string(artifacts["destination"], f"execution_profiles.{name}.artifacts.destination")
    return root


def validate_config_json(data: Any) -> dict:
    root = _mapping(data, ".papersmith/config.json")
    _string(root.get("project_name"), "config.project_name")
    validate_tools(_string_list(root.get("active_tools"), "config.active_tools"))
    models = _mapping(root.get("agent_models"), "config.agent_models")
    for name, model in models.items():
        _string(name, "config.agent_models key")
        _string(model, f"config.agent_models.{name}")
    engine = _mapping(root.get("execution_engine"), "config.execution_engine")
    _string(engine.get("active_compute_target"), "config.execution_engine.active_compute_target")
    _string(engine.get("active_profile"), "config.execution_engine.active_profile")
    _string(engine.get("accounts_store_path"), "config.execution_engine.accounts_store_path")
    _string(engine.get("ledger_path"), "config.execution_engine.ledger_path")
    if "auto_retry_failed_shards" in engine and not isinstance(engine["auto_retry_failed_shards"], bool):
        _fail("config.execution_engine.auto_retry_failed_shards", "must be boolean")
    if "max_retries" in engine:
        _number(engine["max_retries"], "config.execution_engine.max_retries", integer=True)
    _string(root.get("created_at"), "config.created_at")
    _string(root.get("updated_at"), "config.updated_at")
    if "paper_kind" in root and root["paper_kind"] not in ("experimental", "review"):
        _fail("config.paper_kind", "must be experimental or review")
    return root
