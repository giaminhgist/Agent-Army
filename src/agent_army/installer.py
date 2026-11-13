"""Offline managed runtime + native agents, with preview and reversible updates."""
import json
import os
import re
from pathlib import Path
import shutil
import sys
import tomllib

from . import __version__
from .adapters import claude, codex
from .errors import ArmyError
from .models import resolve
from .paths import army_home
from .promotions import receipt
from .store import canonical, sha
from . import transactions as tx


class Installer:
    def __init__(self, registry, *, home=None, claude_home=None, codex_home=None, project=None, python=None, layers=None):
        self.registry, self.layers = registry, layers
        self.home = tx.safe(home or army_home()).resolve()
        self.project = tx.safe(project).resolve() if project else None
        self.python = tx.safe(python or sys.executable).resolve()
        if not self.python.is_file():
            raise ArmyError("Selected Python executable does not exist")
        self.homes = {"claude": tx.safe(claude_home or os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))).resolve(),
                      "codex": tx.safe(codex_home or os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()}
        if self.project:
            if not self.project.is_dir():
                raise ArmyError("Project install requires an existing directory")
            self.homes = {host: self.project / ("." + host) for host in self.homes}
        for root in self.homes.values():
            if self.home.is_relative_to(root) or root.is_relative_to(self.home):
                raise ArmyError("Runtime and native host roots must not overlap")
        if self.homes["claude"] == self.homes["codex"]:
            raise ArmyError("Claude and Codex homes must differ")
        self.state = self.home / "installer"
        self.manifest = self.state / "manifest.json"

    def _load(self):
        data = tx.read(self.manifest)
        if data is None:
            return {"owner": "agent-army", "schema_version": 1, "files": {}}
        try:
            value = json.loads(data)
            if value["owner"] != "agent-army" or value["schema_version"] != 1 or not isinstance(value["files"], dict):
                raise ValueError()
            for path, record in value["files"].items():
                if not Path(path).is_absolute() or not isinstance(record["hash"], str) or not isinstance(record["group"], str):
                    raise ValueError()
                candidate = tx.safe(path)
                if record["group"] == "runtime":
                    if candidate != self.home / "bin/army.py" and not candidate.is_relative_to(self.home / "runtime/agent_army"):
                        raise ValueError()
                else:
                    host, separator, folder = record["group"].partition(":")
                    if host not in ("claude", "codex") or not separator or not Path(folder).is_absolute():
                        raise ValueError()
                    ext = "md" if host == "claude" else "toml"
                    if candidate.parent != Path(folder) / "agents" or not re.fullmatch(r"army-[a-z0-9-]+\." + ext, candidate.name):
                        raise ValueError()
        except (ValueError, KeyError, TypeError) as exc:
            raise ArmyError("Invalid installer ownership manifest", 5) from exc
        return value

    def _render(self, hosts, tier):
        files = {}
        launcher = self.home / "bin/army.py"
        invocation = [str(self.python), str(launcher)]
        instructions = ("\n\n## Installed shared Army runtime\n"
                        + "Invoke this argv through the host's permitted process tool: " + json.dumps(invocation)
                        + ". Append Army CLI arguments; use --project with the active project for local data. "
                        + "The launcher sets AGENT_ARMY_HOME to " + json.dumps(str(self.home))
                        + ". Both hosts must use this same launcher for shared knowledge/memory. "
                        + "Do not automate --console consent or install missing skills.\n")
        for host in hosts:
            group = host + ":" + str(self.homes[host])
            for agent in sorted(self.registry.agents):
                profile = resolve(self.registry, agent, host, tier, self.layers)
                if host == "claude":
                    text, ext = claude.render(self.registry, agent, profile) + instructions, "md"
                else:
                    original = codex.render(self.registry, agent, profile)
                    fields = tomllib.loads(original)
                    fields["developer_instructions"] += instructions
                    text = original.splitlines()[0] + "\n" + "\n".join(k + " = " + json.dumps(v, ensure_ascii=False) for k, v in fields.items()) + "\n"
                    tomllib.loads(text)
                    ext = "toml"
                path = tx.safe(self.homes[host] / "agents" / f"army-{agent}.{ext}")
                files[str(path)] = (text.encode(), group)
        package = Path(__file__).parent
        for path in sorted(package.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix in (".py", ".toml", ".md"):
                data = tx.read(path)
                target = tx.safe(self.home / "runtime/agent_army" / path.relative_to(package))
                files[str(target)] = (data, "runtime")
        text = ("# Managed Agent-Army launcher; stdlib core, optional PyYAML for skills.\n"
                "import os, sys\nfrom pathlib import Path\n"
                "home = Path(__file__).resolve().parent.parent\n"
                "os.environ['AGENT_ARMY_HOME'] = str(home)\n"
                "sys.path.insert(0, str(home / 'runtime'))\n"
                "from agent_army.cli import main\nraise SystemExit(main())\n")
        files[str(launcher)] = (text.encode(), "runtime")
        return files, invocation

    def _plan(self, action="install", host="both", tier=None, remove_runtime=False):
        if action not in ("install", "uninstall") or host not in ("claude", "codex", "both"):
            raise ArmyError("Invalid install action/host")
        hosts = ("claude", "codex") if host == "both" else (host,)
        groups = {h + ":" + str(self.homes[h]) for h in hosts}
        current = self._load()
        owned = current["files"]
        desired, invocation = self._render(hosts, tier) if action == "install" else ({}, [str(self.python), str(self.home / "bin/army.py")])
        if action == "install":
            groups.add("runtime")
        elif remove_runtime:
            if any(record["group"] not in groups | {"runtime"} for record in owned.values()):
                raise ArmyError("Other installed host scopes still depend on the shared runtime", 5)
            groups.add("runtime")
        selected = {path for path, record in owned.items() if record["group"] in groups} | set(desired)
        conflicts, changes, entries = [], [], []
        updated = dict(owned)
        for path in sorted(selected):
            before = tx.read(path)
            record = owned.get(path)
            after, group = desired.get(path, (None, record["group"] if record else ""))
            if before is not None and (record is None or tx.digest(before) != record["hash"]):
                conflicts.append({"path": path, "reason": "unowned_or_user_edited"})
                continue
            # Deleted owned files may be repaired by install; uninstall treats absence as no-op.
            if after is None:
                updated.pop(path, None)
            else:
                updated[path] = {"hash": tx.digest(after), "group": group}
            if before != after:
                entries.append({"path": path, "before": before, "after": after})
                changes.append({"path": path, "operation": "delete" if after is None else "create" if before is None else "update",
                                "before_hash": tx.digest(before), "after_hash": tx.digest(after),
                                "content": after.decode("utf-8") if after is not None else None})
        manifest = {"owner": "agent-army", "schema_version": 1, "version": __version__, "files": updated}
        before = tx.read(self.manifest)
        after = canonical(manifest).encode()
        if before != after:
            entries.append({"path": str(self.manifest), "before": before, "after": after})
        preview = {"action": action, "host": host, "tier": tier, "remove_runtime": remove_runtime,
                   "scope": "project" if self.project else "user", "home": str(self.home),
                   "host_roots": {h: str(self.homes[h]) for h in hosts}, "python": str(self.python),
                   "python_hash": tx.digest(tx.read(self.python)), "launcher_argv": invocation,
                   "changes": changes, "conflicts": conflicts, "manifest_before": tx.digest(before),
                   "manifest_after": tx.digest(after), "native_runtime_verified": False,
                   "skills_installed": False, "knowledge_deleted": False}
        return {"preview": preview, "request_hash": sha(canonical(preview))}, entries

    def plan(self, **kwargs):
        return self._plan(**kwargs)[0]

    def apply(self, plan, authority=None, *, fault=None):
        p = plan["preview"]
        kwargs = {k: p[k] for k in ("action", "host", "tier", "remove_runtime")}
        fresh, _ = self._plan(**kwargs)
        if fresh != plan:
            raise ArmyError("Install preview is stale or belongs to another target", 5)
        if p["conflicts"]:
            raise ArmyError("Resolve ownership conflicts before installation", 5)
        approved = receipt(authority, p["action"], str(self.home), plan["request_hash"])
        with tx.lock(self.state):
            fresh, entries = self._plan(**kwargs)
            if fresh != plan:
                raise ArmyError("Installation changed during approval", 5)
            if not entries:
                return {"state": "unchanged", "changed_files": 0}
            return tx.commit(self.state, entries, approved, fault=fault)

    def rollback_plan(self, transaction):
        payload = tx.rollback_preview(self.state, transaction)
        return {"preview": payload, "request_hash": sha(canonical(payload))}

    def rollback(self, plan, authority=None):
        transaction = plan["preview"]["transaction"]
        if self.rollback_plan(transaction) != plan:
            raise ArmyError("Rollback preview changed", 5)
        receipt(authority, "install-rollback", transaction, plan["request_hash"])
        with tx.lock(self.state):
            if self.rollback_plan(transaction) != plan:
                raise ArmyError("Rollback changed during approval", 5)
            return tx.restore(self.state, transaction)
