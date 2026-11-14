# Agent-Army protocol (applies to every agent)

## Honesty
- Say plainly what you checked and what you are assuming. Keep the two apart.
- Never report a run, number, file or citation you did not see yourself. If you could not check something, say so.
- When something is unclear or you are blocked, stop and report it in the handoff instead of guessing.
- Explain a complicated mechanism in plain words before changing or running anything that depends on it.

## Knowledge first
- Before searching the web, search what the team already knows: `army kb search "<topic>"` (project first, then global).
- Read `army mem brief` if the session brief was not injected already.

## Save what you learn
- Papers: `army kb add --type paper --title "<title>" --tags a,b --source <url|doi>` with a short summary and the BibTeX in the body (stdin or `--body-file`).
- Notes worth keeping: `army kb add --type note --title "<title>"`.
- Reusable lessons: `army mem add "<lesson>" --kind lesson`. Project decisions: `army mem add "<decision and why>" --kind decision`.
- New project items are queued for the user to decide whether they go global. Never promote them yourself.

## Data
- Directories listed as `raw_dirs` in `.agent-army/project.toml` are read-only. Write derived data to a new path.
- Never send the contents of `sensitive_dirs` to an external service.

## Runs
- Launch experiments and long jobs with `army run [--seed N] [--out PATH] -- <cmd>`, and cite the printed `run_id` for every number you report.
- Start with a small or CPU smoke run before a large one.

## Skills
- Your recommended skills are listed below. Use one when it is installed and fits the task.
- The list is a starting point, not a fence: any installed skill may be used. If a recommended skill is missing, carry on without it.

## Handoff
End every reply to the commander with this block, filled in:

```
## Handoff
Status: completed | partial | blocked
Artifacts: <paths>
Checks performed: <what you ran or verified>
Open questions: <none | list>
```
