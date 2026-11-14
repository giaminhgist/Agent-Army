"""Load army.toml (user copy in $ARMY_HOME wins over the shipped default)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from army import paths

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "army.toml"


def config_path() -> Path:
    user = paths.army_home() / "army.toml"
    return user if user.is_file() else DEFAULT_CONFIG


def load_config(path: Path | None = None) -> dict:
    with open(path or config_path(), "rb") as f:
        return tomllib.load(f)


def agent_names(cfg: dict) -> list[str]:
    return list(cfg["agents"].keys())


def tier_for(cfg: dict, agent: str, platform: str) -> dict:
    tier = cfg["agents"][agent]["tier"]
    if platform == "claude":
        return {"model": cfg["tiers"]["claude"][tier], "effort": None}
    if platform == "codex":
        t = cfg["tiers"]["codex"][tier]
        return {"model": t.get("model") or None, "effort": t.get("effort") or None}
    raise ValueError(f"unknown platform: {platform}")
