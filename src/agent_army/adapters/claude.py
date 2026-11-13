import json

from .base import fingerprint, instructions
from .. import __version__
from ..registry import Registry


def render(registry: Registry, agent: str, profile: dict) -> str:
    # JSON quoted strings are valid YAML scalars; no YAML dependency in the core.
    q = lambda value: json.dumps(value, ensure_ascii=False)
    fields = {"name": f"army-{agent}", "description": registry.get(agent).description, "model": profile["model"]}
    if "effort" in profile:
        fields["effort"] = profile["effort"]
    frontmatter = "\n".join(f"{key}: {q(value)}" for key, value in fields.items())
    return f"---\n{frontmatter}\n---\n\n<!-- Agent-Army {__version__}; source-sha256: {fingerprint(registry, agent, profile)} -->\n\n" + instructions(registry, agent)
