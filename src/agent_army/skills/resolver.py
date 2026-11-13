from __future__ import annotations

from ..errors import ArmyError
from ..registry import Registry
from ..routing import normalize

STOP = {"a", "an", "the", "and", "or", "for", "to", "of", "with", "use", "this", "in", "on",
        "va", "cho", "cua", "cac", "mot", "toi", "hay"}


def tokens(text: str) -> set[str]:
    return set(normalize(text).split()) - STOP


def resolve_skills(inventory: dict, registry: Registry, agent: str, task: str,
                   pinned: list[str] | None = None, required: list[str] | None = None,
                   tool_capabilities: list[str] | None = None, max_selected: int = 3) -> dict:
    spec = registry.get(agent)
    if not task.strip() or not 1 <= max_selected <= 20:
        raise ArmyError("Nonempty task and max_selected between 1 and 20 required")
    pinned, required = pinned or [], required or []
    skills = {s["id"]: s for s in inventory["skills"]}
    names = {}
    for skill in skills.values():
        names.setdefault(skill["name"], []).append(skill["id"])
    ambiguous, unavailable, unknown_pins = [], [], []
    pin_ids = set()

    def identify(ref: str) -> str | None:
        if ref in skills:
            return ref
        by_path = [s["id"] for s in skills.values() if s["path"] == ref]
        matches = by_path or names.get(ref, [])
        if len(matches) > 1:
            entry = {"reference": ref, "candidates": matches}
            if entry not in ambiguous:
                ambiguous.append(entry)
            return None
        return matches[0] if matches else None

    for ref in pinned:
        sid = identify(ref)
        if sid:
            pin_ids.add(sid)
        else:
            unknown_pins.append(ref)

    # Validate each complete dependency closure before returning a candidate.
    def closure(sid: str, stack: tuple[str, ...] = (), explicit: bool = False) -> list[str]:
        if len(stack) >= 64:
            raise ArmyError("dependency depth limit exceeded", 3)
        if sid in stack:
            raise ArmyError("dependency cycle: " + " -> ".join((*stack, sid)), 3)
        skill = skills[sid]
        if skill["eligibility"] == "unavailable":
            raise ArmyError("; ".join(skill["reasons"]), 3)
        if skill["manual_only"] and sid not in pin_ids:
            raise ArmyError("manual-only skill requires explicit user selection", 3)
        if len(names[skill["name"]]) > 1 and sid not in pin_ids and not explicit:
            # Do not silently select a same-named skill that the host might shadow.
            identify(skill["name"])
            raise ArmyError("ambiguous skill name; select exact ID or path", 3)
        result = []
        for ref in skill["dependencies"]:
            dep = identify(ref)
            if not dep:
                raise ArmyError(f"missing or ambiguous dependency: {ref}", 3)
            result.extend(closure(dep, (*stack, sid), ref in skills or ref == skills[dep]["path"]))
            if len(set(result)) > 64:
                raise ArmyError("dependency count limit exceeded", 3)
            result.append(dep)
        return list(dict.fromkeys(result))

    wanted = tokens(task)
    recommended = registry.suggestions(agent)
    ranked = []
    for skill in skills.values():
        text_hits = wanted & tokens(skill["name"] + " " + skill["description"])
        cap_hits = set(required) & set(skill["capabilities"])
        if skill["id"] not in pin_ids and not text_hits and not cap_hits:
            continue
        role_hits = set(spec.capabilities) & set(skill["capabilities"])
        # Source-aware recommendation is ONLY a tie-break after task relevance.
        suggested = any(r["name"] == skill["name"] and r["source"].rstrip("/") == skill["origin"].rstrip("/") for r in recommended)
        score = len(text_hits) * 2 + len(cap_hits) * 4 + min(len(role_hits), 2)
        ranked.append((skill["id"] not in pin_ids, -score, not suggested, skill["id"], text_hits, cap_hits))
    ranked.sort(key=lambda row: row[:4])
    selected, dependency_ids = [], []
    for _, neg_score, _, sid, text_hits, cap_hits in ranked:
        try:
            deps = closure(sid)
        except ArmyError as exc:
            unavailable.append({"id": sid, "name": skills[sid]["name"], "reason": str(exc)})
            continue
        if len(selected) >= max_selected:
            continue
        skill = skills[sid]
        selected.append({"id": sid, "name": skill["name"], "path": skill["path"],
                         "content_hash": skill["content_hash"], "host_invocation": skill["host_invocation"],
                         "load_method": "host invocation hint; confirm host availability" if skill["host_invocation"] else "read exact SKILL.md path with host tools",
                         "eligibility": skill["eligibility"], "compatibility": skill["compatibility"],
                         "score": -neg_score, "reason": {"task_terms": sorted(text_hits),
                         "required_capabilities": sorted(cap_hits), "user_selected": sid in pin_ids}})
        dependency_ids.extend(deps)
    selected_ids = {s["id"] for s in selected}
    deps = [skills[sid] for sid in dict.fromkeys(dependency_ids) if sid not in selected_ids]
    covered = set(tool_capabilities or [])
    for sid in selected_ids | {d["id"] for d in deps}:
        covered.update(skills[sid]["capabilities"])
    missing = sorted(set(required) - covered)
    mode = "blocked" if missing else ("skills" if selected else "tools")
    return {"agent": agent, "host": inventory["host"], "selected": selected, "dependencies": deps,
            "unavailable": unavailable, "ambiguous": ambiguous, "unresolved_pins": unknown_pins,
            "fallback_mode": mode, "missing_capabilities": missing,
            "tool_capabilities": tool_capabilities or [],
            "limitations": ["Metadata is not runtime validation. Unknown requirements and compatibility must be checked before use.",
                           "Tools fallback means no mandatory skill; tool availability is only asserted for explicitly supplied capabilities.",
                           "This resolver does not authorize network access, installation, writes, or execution."],
            "diagnostics": inventory["diagnostics"], "execution_authorized": False}
