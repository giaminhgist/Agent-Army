import shutil
import sqlite3

from .models import resolve
from .registry import Registry


def inspect(registry: Registry, layers=None) -> dict:
    for agent in registry.agents:
        for host in ("claude", "codex"):
            for tier in ("light", "medium", "heavy"):
                resolve(registry, agent, host, tier, layers)
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
        fts5 = True
    except sqlite3.OperationalError:
        fts5 = False
    finally:
        connection.close()
    return {"registry": "valid", "agent_count": len(registry.agents), "fts5_available": fts5,
            "hosts": {host: {"executable": shutil.which(host), "native_agent_smoke": "not_tested", "model_access": "unknown"} for host in ("claude", "codex")},
            "skills": "use army skills doctor --host claude|codex; PyYAML is optional for the static core",
            "shared_memory": "local stores/retrieval and supervised console promotion available", "jobs": "supervised leaf-process runner; one active job per project", "approval_boundary": "local console only; native host trust not verified", "auto_mode": "disabled_missing_trusted_host_and_process_isolation", "deployment": "offline install/migration preview, supervised apply and rollback; see docs/INSTALL.vi.md", "check_type": "static_only"}
