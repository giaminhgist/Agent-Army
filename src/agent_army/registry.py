from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path

from .config import TIERS, only_keys, read_toml, validate_model_map
from .errors import ArmyError
from .paths import contained


@dataclass(frozen=True)
class AgentSpec:
    id: str
    description: str
    role: str
    prompt_path: str
    default_tier: str
    capabilities: list[str]
    output_contract: str
    recommendations_ref: str
    keywords: list[str]
    model_overrides: dict
    policy: dict

    def to_dict(self) -> dict:
        return asdict(self)


def default_resources() -> Path:
    # Wheels are installed unpacked; all runtime data travels inside the package.
    return Path(str(files("agent_army").joinpath("resources")))


class Registry:
    def __init__(self, root: Path | None = None):
        self.root = (root or default_resources()).resolve()
        raw = read_toml(self.root / "registry" / "agents.toml")
        only_keys(raw, {"schema_version", "agents"}, "registry")
        if raw.get("schema_version") != 1 or not isinstance(raw.get("agents"), dict) or not raw["agents"]:
            raise ArmyError("Registry requires schema_version=1 and nonempty agents table")
        self.protocol = self._text("prompts/protocol.md")
        self.agents: dict[str, AgentSpec] = {}
        self.prompts: dict[str, str] = {}
        for name, entry in raw["agents"].items():
            if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
                raise ArmyError(f"Invalid agent id: {name}")
            only_keys(entry, {"description", "role", "prompt_path", "default_tier", "capabilities", "output_contract", "recommendations_ref", "keywords", "model_overrides", "policy"}, name)
            for key in ("description", "role", "prompt_path", "output_contract"):
                if not isinstance(entry.get(key), str) or not entry[key].strip():
                    raise ArmyError(f"{name}.{key} is required")
            if entry.get("default_tier") not in TIERS:
                raise ArmyError(f"{name}: invalid default_tier")
            for key in ("capabilities", "keywords"):
                values = entry.get(key, [])
                if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                    raise ArmyError(f"{name}.{key}: expected string array")
            if not entry["prompt_path"].replace("\\", "/").startswith("prompts/"):
                raise ArmyError(f"{name}: prompt must be under prompts/")
            path = contained(self.root / "prompts", entry["prompt_path"].replace("\\", "/")[8:])
            self.prompts[name] = self._text(str(path.relative_to(self.root)))
            validate_model_map(entry.get("model_overrides", {}), f"{name}.model_overrides")
            policy = entry.get("policy", {})
            only_keys(policy, {"write_intent", "approval_actions"}, f"{name}.policy")
            if policy.get("write_intent", "artifacts") not in ("artifacts", "project-code", "reviews", "proposals"):
                raise ArmyError(f"{name}: invalid write_intent")
            actions = policy.get("approval_actions", [])
            if not isinstance(actions, list) or any(not isinstance(a, str) or not a for a in actions):
                raise ArmyError(f"{name}: invalid approval_actions")
            ref = entry.get("recommendations_ref", name)
            if not isinstance(ref, str):
                raise ArmyError(f"{name}: invalid recommendations_ref")
            self.agents[name] = AgentSpec(name, entry["description"], entry["role"], entry["prompt_path"], entry["default_tier"], entry.get("capabilities", []), entry["output_contract"], ref, entry.get("keywords", []), entry.get("model_overrides", {}), policy)
        recommendation_file = self.root / "registry" / "recommendations.toml"
        recommendations = read_toml(recommendation_file) if recommendation_file.exists() else {}
        only_keys(recommendations, {"schema_version", "recommendations"}, "recommendations")
        if recommendations.get("schema_version", 1) != 1:
            raise ArmyError("Unsupported recommendation schema")
        self.recommendations = recommendations.get("recommendations", {})
        if not isinstance(self.recommendations, dict):
            raise ArmyError("recommendations must be a table")
        for ref, entries in self.recommendations.items():
            if not isinstance(entries, list):
                raise ArmyError(f"recommendations.{ref}: expected array")
            for item in entries:
                only_keys(item, {"source", "name", "reason"}, f"recommendations.{ref}")
                if any(not isinstance(item.get(k), str) or not item[k].strip() for k in ("source", "name", "reason")):
                    raise ArmyError(f"recommendations.{ref}: source, name, reason required")

    def _text(self, relative: str) -> str:
        try:
            text = contained(self.root, relative).read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeError) as exc:
            raise ArmyError(f"Cannot read {relative}: {exc}") from exc
        if not text:
            raise ArmyError(f"Empty prompt: {relative}")
        return text

    def get(self, name: str) -> AgentSpec:
        if name not in self.agents:
            raise ArmyError(f"Unknown agent: {name}")
        return self.agents[name]

    def suggestions(self, name: str) -> list[dict]:
        return self.recommendations.get(self.get(name).recommendations_ref, [])
