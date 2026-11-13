from __future__ import annotations

import copy
import tomllib
from pathlib import Path

from .errors import ArmyError

HOSTS = ("claude", "codex")
TIERS = ("light", "medium", "heavy")


def read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ArmyError(f"Cannot read TOML {path}: {exc}") from exc


def only_keys(value: dict, allowed: set[str], label: str) -> None:
    if not isinstance(value, dict):
        raise ArmyError(f"{label}: expected table")
    unknown = set(value) - allowed
    if unknown:
        raise ArmyError(f"{label}: unknown keys {sorted(unknown)}")


def merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result


def validate_model_map(mapping: dict, label: str) -> None:
    only_keys(mapping, set(HOSTS), label)
    for host, tiers in mapping.items():
        only_keys(tiers, set(TIERS), f"{label}.{host}")
        for tier, profile in tiers.items():
            only_keys(profile, {"model", "effort"}, f"{label}.{host}.{tier}")
            for field, value in profile.items():
                if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
                    raise ArmyError(f"{label}.{host}.{tier}.{field}: expected nonempty single-line string")


def validate_config(config: dict, agents: set[str]) -> None:
    only_keys(config, {"schema_version", "models", "agents", "skills", "project", "extensions"}, "config")
    if type(config.get("schema_version", 1)) is not int or config.get("schema_version", 1) != 1:
        raise ArmyError("Unsupported config schema_version")
    if "project" in config:
        only_keys(config["project"], {"id", "root"}, "project")
        import uuid
        try:
            uuid.UUID(config["project"]["id"])
            if not Path(config["project"]["root"]).is_absolute():
                raise ValueError()
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise ArmyError("project requires UUID id and absolute root") from exc
    from .skills.commands import validate_settings
    validate_settings(config.get("skills", {}))
    validate_model_map(config.get("models", {}), "models")
    only_keys(config.get("agents", {}), agents, "agents")
    for name, options in config.get("agents", {}).items():
        only_keys(options, {"default_tier", "models"}, f"agents.{name}")
        if "default_tier" in options and options["default_tier"] not in TIERS:
            raise ArmyError(f"agents.{name}.default_tier: invalid tier")
        validate_model_map(options.get("models", {}), f"agents.{name}.models")
    if "extensions" in config and not isinstance(config["extensions"], dict):
        raise ArmyError("extensions must be a table")


def load_layers(paths: list[Path], agents: set[str]) -> list[tuple[str, dict]]:
    layers = []
    for path in paths:
        config = read_toml(path)
        validate_config(config, agents)
        layers.append((str(path), config))
    return layers
