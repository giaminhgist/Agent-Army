from __future__ import annotations

from .config import HOSTS, TIERS, only_keys, read_toml, validate_model_map
from .errors import ArmyError
from .registry import Registry


def resolve(registry: Registry, agent: str, host: str, tier: str | None = None,
            layers: list[tuple[str, dict]] | None = None, task_profile: dict | None = None) -> dict:
    if host not in HOSTS:
        raise ArmyError(f"Unsupported host: {host}", 3)
    spec = registry.get(agent)
    layers = layers or []
    selected_tier = spec.default_tier
    for _, config in layers:
        selected_tier = config.get("agents", {}).get(agent, {}).get("default_tier", selected_tier)
    selected_tier = tier or selected_tier
    if selected_tier not in TIERS:
        raise ArmyError(f"Invalid tier: {selected_tier}")
    raw = read_toml(registry.root / "registry" / "models.toml")
    only_keys(raw, {"schema_version", "models"}, "model registry")
    if raw.get("schema_version") != 1:
        raise ArmyError("Unsupported model registry schema")
    validate_model_map(raw.get("models", {}), "models")
    for required_host in HOSTS:
        for required_tier in TIERS:
            if not raw.get("models", {}).get(required_host, {}).get(required_tier, {}).get("model"):
                raise ArmyError(f"Missing model profile: {required_host}.{required_tier}")
    result, origins = {}, {}

    def apply(profile: dict, origin: str) -> None:
        if "model" in profile and profile["model"] != result.get("model"):
            # Never carry a previous model's effort into a different model implicitly.
            result.pop("effort", None)
            origins.pop("effort", None)
        result.update(profile)
        origins.update({key: origin for key in profile})

    apply(raw["models"][host][selected_tier], "bundled.models")
    apply(spec.model_overrides.get(host, {}).get(selected_tier, {}), f"registry.agents.{agent}")
    for origin, config in layers:
        apply(config.get("models", {}).get(host, {}).get(selected_tier, {}), origin + ":models")
        apply(config.get("agents", {}).get(agent, {}).get("models", {}).get(host, {}).get(selected_tier, {}), origin + ":agent")
    if task_profile is not None:
        validate_model_map({host: {selected_tier: task_profile}}, "task_profile")
        apply(task_profile, "task-preview")
    effort = result.get("effort")
    supported = {"claude": {"low", "medium", "high", "max"}, "codex": {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}}
    if effort is not None and effort not in supported[host]:
        raise ArmyError(f"Unsupported {host} effort: {effort}", 3)
    return {"agent": agent, "host": host, "tier": selected_tier, **result, "origins": origins,
            "availability": "unknown", "resolved_model_id": None, "execution_authorized": False}
