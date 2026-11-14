"""Move project knowledge to the global store, only for items the user picks."""

from __future__ import annotations

from pathlib import Path

from army import frontmatter, store


def pending(project: Path) -> list[store.Item]:
    return [i for i in store.load_items("project", project) if i.meta.get("promote") == "pending"]


def _get(item_id: str, project: Path) -> store.Item:
    item = store.get_item(item_id, "project", project)
    if item is None:
        raise KeyError(item_id)
    return item


def promote(ids: list[str], project: Path) -> list[store.Item]:
    items = [_get(i, project) for i in ids]  # validate all before writing anything
    out: list[store.Item] = []
    for item in items:
        if item.meta.get("promote") == "yes":
            continue
        meta = {k: v for k, v in item.meta.items() if k != "promote"}
        meta["scope"] = "global"
        meta.setdefault("origin_project", str(project))
        d = store.type_dir("global", item.type, None)
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{item.id}.md"
        path.write_text(frontmatter.dump(meta, item.body), encoding="utf-8")
        store.update_meta(item, promote="yes")
        out.append(store.Item(item.id, item.type, item.title, "global", path, meta, item.body))
    return out


def reject(ids: list[str], project: Path) -> None:
    for item in [_get(i, project) for i in ids]:
        store.update_meta(item, promote="no")


def pick(project: Path, input_fn=input, print_fn=print) -> list[store.Item]:
    items = pending(project)
    if not items:
        print_fn("Nothing pending promotion.")
        return []
    for n, it in enumerate(items, 1):
        print_fn(f"{n}. [{it.type}] {it.title} ({it.id})")
    for _attempt in range(2):
        answer = input_fn("Promote which to global? (e.g. 1,3 | all | none): ").strip().lower()
        if answer in ("", "none", "n"):
            return []
        if answer == "all":
            return promote([i.id for i in items], project)
        try:
            nums = sorted({int(x) for x in answer.replace(" ", "").split(",") if x})
        except ValueError:
            print_fn("Could not read that; use numbers like 1,3 or 'all' / 'none'.")
            continue
        if nums and all(1 <= k <= len(items) for k in nums):
            return promote([items[k - 1].id for k in nums], project)
        print_fn(f"Numbers must be between 1 and {len(items)}.")
    return []
