from __future__ import annotations

import re
import unicodedata

from .errors import ArmyError
from .registry import Registry


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in text if not unicodedata.combining(c))))


def route(registry: Registry, task: str, agent: str | None = None, task_type: str | None = None) -> dict:
    if not task.strip():
        raise ArmyError("Task must not be empty")
    if agent:
        registry.get(agent)
        return {"agent": agent, "reason": "Explicit user selection", "candidates": [], "needs_decomposition": False}
    words = f" {normalize(task)} "
    candidates = []
    for spec in registry.agents.values():
        hits = [key for key in spec.keywords if f" {normalize(key)} " in words]
        type_match = bool(task_type and task_type in spec.capabilities)
        if hits or type_match:
            candidates.append({"agent": spec.id, "score": len(hits) + (10 if type_match else 0), "keywords": hits, "capability_match": type_match})
    candidates.sort(key=lambda item: (-item["score"], item["agent"]))
    review = next((c for c in candidates if c["agent"] == "reviewer"), None)
    if review:
        selected, reason, ambiguous = "reviewer", "Explicit review/audit signal; independent reviewer", False
    elif candidates and (len(candidates) == 1 or candidates[0]["score"] > candidates[1]["score"]):
        selected, reason, ambiguous = candidates[0]["agent"], "Best deterministic keyword/capability match", False
    else:
        selected, reason, ambiguous = "orchestrator", "No unique match; clarify or decompose the task", True
        registry.get(selected)
    return {"agent": selected, "reason": reason, "candidates": candidates, "needs_decomposition": ambiguous,
            "score_meaning": "routing heuristic, not a probability"}


def validate_graph(dependencies: dict[str, list[str]]) -> None:
    visited, active = set(), set()

    def visit(node: str) -> None:
        if node not in dependencies:
            raise ArmyError(f"Missing dependency: {node}")
        if node in active:
            raise ArmyError(f"Dependency cycle at: {node}")
        if node in visited:
            return
        active.add(node)
        for child in dependencies[node]:
            visit(child)
        active.remove(node)
        visited.add(node)

    for node in dependencies:
        visit(node)
