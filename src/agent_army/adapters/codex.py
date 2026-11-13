import json
import tomllib

from .base import fingerprint, instructions
from .. import __version__
from ..registry import Registry


def render(registry: Registry, agent: str, profile: dict) -> str:
    fields = {"name": f"army-{agent}", "description": registry.get(agent).description,
              "model": profile["model"], "developer_instructions": instructions(registry, agent)}
    if "effort" in profile:
        fields["model_reasoning_effort"] = profile["effort"]
    text = f"# Agent-Army {__version__}; source-sha256: {fingerprint(registry, agent, profile)}\n"
    text += "\n".join(f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in fields.items()) + "\n"
    tomllib.loads(text)
    return text
