from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

from ..errors import ArmyError

MAX_FILE_BYTES = 1024 * 1024
MAX_HEADER_BYTES = 64 * 1024


def string_list(value, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ArmyError(f"{label}: expected nonempty strings in an array")
    return list(dict.fromkeys(value))


def validate_options(options: dict) -> dict:
    allowed = {"capabilities", "hosts", "dependencies", "requires_env", "requires_tools", "enabled", "invocation"}
    if not isinstance(options, dict) or set(options) - allowed:
        raise ArmyError("Skill options must be a table with supported keys")
    result = dict(options)
    for key in allowed - {"enabled", "invocation"}:
        if key in result:
            result[key] = string_list(result[key], key)
    if "hosts" in result and not set(result["hosts"]) <= {"claude", "codex"}:
        raise ArmyError("Skill hosts must be claude and/or codex")
    if "enabled" in result and type(result["enabled"]) is not bool:
        raise ArmyError("Skill enabled must be boolean")
    if "invocation" in result and (not isinstance(result["invocation"], str) or not result["invocation"].strip()):
        raise ArmyError("Skill invocation must be a nonempty string")
    return result


def parser_module():
    try:
        import yaml
        return yaml
    except ImportError as exc:
        raise ArmyError("Skill discovery requires optional dependency PyYAML; install agent-army[skills] in your chosen environment", 3) from exc


def parse_header(text: str) -> dict:
    yaml = parser_module()
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ArmyError("SKILL.md requires YAML frontmatter")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ArmyError("Unterminated SKILL.md frontmatter")
    header = "\n".join(lines[1:end])
    if len(header.encode("utf-8")) > MAX_HEADER_BYTES:
        raise ArmyError("Skill frontmatter exceeds 64 KiB")

    class UniqueLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            self.flatten_mapping(node)
            result = {}
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                if not isinstance(key, str) or key in result:
                    raise ArmyError("Duplicate or non-string YAML metadata key")
                result[key] = self.construct_object(value_node, deep=deep)
            return result

    try:
        # Limit aliases before construction; no custom tags/object execution.
        tokens = list(yaml.scan(header))
        if any(isinstance(token, yaml.tokens.AliasToken) for token in tokens):
            raise ArmyError("YAML aliases are not supported in skill metadata")
        data = yaml.load(header, Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        # Parser errors may quote arbitrary file content; keep diagnostics bounded.
        raise ArmyError(f"Invalid YAML metadata ({type(exc).__name__})") from exc
    if not isinstance(data, dict):
        raise ArmyError("Skill metadata must be a mapping")
    return data


@dataclass
class SkillDescriptor:
    id: str
    name: str
    description: str
    origin: str
    scope: str
    path: str
    content_hash: str
    host_invocation: str | None
    capabilities: list[str]
    hosts: list[str]
    dependencies: list[str]
    requires_env: list[str]
    requires_tools: list[str]
    enabled: bool
    metadata_status: str
    compatibility: str
    requirements_known: bool
    manual_only: bool
    eligibility: str = "unknown"
    reasons: list[str] | None = None

    def to_dict(self):
        return asdict(self)


def read_skill(path: Path, origin: str, scope: str) -> SkillDescriptor:
    with path.open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ArmyError("SKILL.md exceeds 1 MiB")
    data = parse_header(raw.decode("utf-8-sig"))
    for key in ("name", "description"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ArmyError(f"Skill {key} must be a nonempty string")
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ArmyError("metadata must be a mapping")
    options = validate_options(metadata.get("army", {}))
    for key in ("disable-model-invocation",):
        if key in data and type(data[key]) is not bool:
            raise ArmyError(f"{key} must be boolean")
    compatibility = data.get("compatibility", "")
    if not isinstance(compatibility, str):
        raise ArmyError("compatibility must be text")
    identity = origin + "\0" + str(path.resolve()) + "\0" + data["name"]
    return SkillDescriptor(
        id="skill-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
        name=data["name"].strip(), description=data["description"].strip(), origin=origin,
        scope=scope, path=str(path.resolve()), content_hash=hashlib.sha256(raw).hexdigest(),
        host_invocation=options.get("invocation"), capabilities=options.get("capabilities", []),
        hosts=options.get("hosts", []), dependencies=options.get("dependencies", []),
        requires_env=options.get("requires_env", []), requires_tools=options.get("requires_tools", []),
        enabled=options.get("enabled", True), metadata_status="valid",
        compatibility=compatibility,
        requirements_known=all(k in options for k in ("dependencies", "requires_env", "requires_tools")),
        manual_only=data.get("disable-model-invocation", False))
