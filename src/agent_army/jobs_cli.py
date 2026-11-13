"""No persisted grants, --yes, background dispatch or automatic retries."""
import json
from pathlib import Path

from .approvals import ConsoleAuthority
from .errors import ArmyError
from .jobs import Jobs
from .paths import find_project


def add_parsers(commands):
    sub = commands.add_parser("job").add_subparsers(dest="operation", required=True)
    sub.add_parser("create").add_argument("--spec", type=Path, required=True)
    for action in ("status", "preview", "stop", "run", "resume", "review-bundle", "review"):
        p = sub.add_parser(action)
        p.add_argument("job_id")
        if action in ("run", "resume", "review"):
            p.add_argument("--console", action="store_true", help="Person-operated supervised terminal consent; never agent automation")
        if action == "review":
            p.add_argument("--report", required=True, help="Project-relative review JSON")


def run(options):
    project = options.project or find_project(Path.cwd())
    if project is None:
        raise ArmyError("Jobs require an initialized project", 3)
    service = Jobs(project)
    if options.operation == "create":
        if options.spec.stat().st_size > 64000:
            raise ArmyError("Job specification exceeds 64k")
        try:
            spec = json.loads(options.spec.read_text(encoding="utf-8-sig"))
        except ValueError as exc:
            raise ArmyError("Invalid job JSON") from exc
        return service.create(spec)
    task_id = options.job_id
    if options.operation == "status":
        task = service.get(task_id)
        if task["state"] == "completed":
            try:
                service.review_bundle(task_id)
                task["review_current"] = True
            except (ArmyError, OSError):
                task["review_current"] = False
        return task
    if options.operation == "preview":
        return service.preview(task_id)
    if options.operation == "stop":
        return service.stop(task_id)
    if options.operation == "review-bundle":
        return service.review_bundle(task_id)
    preview = (service.review(task_id, options.report, preview_only=True) if options.operation == "review"
               else service.preview(task_id))
    authority = ConsoleAuthority(options.operation, task_id, preview["request_hash"], preview) if options.console else None
    if options.operation == "review":
        return service.review(task_id, options.report, authority)
    return service.run(task_id, authority, resume=options.operation == "resume")
