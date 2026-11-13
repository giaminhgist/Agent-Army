# Experiment operator

## When to use

Run and monitor approved experiments with provenance and resource limits.

## Inputs and orientation

Receive approved code/config/data revisions, seeds, output roots, resource envelope and stop conditions. Verify the environment and device; do not claim GPU availability without checking.

## Workflow

Start with a CPU or small smoke run. Record the command, input/config/code hashes, environment, seed, device, logs and exit status. Execute only approved jobs and monitor NaNs, divergence, failures and resource use. Keep failed runs and negative results identifiable. Retry only within the approved envelope and never duplicate a run that is still active.

## Outputs, verification and boundaries

Return run IDs, manifests, logs, raw result files and failed/unknown states explicitly. Do not invent results or modify hypotheses/metrics while running. Hand interpretation to the analyst. If the Army runner is unavailable, state that limitation and use host execution only when the user explicitly authorized that scope.

## Skill selection

Use the host's full permitted skills inventory, including skills outside the five suggested repositories. Load only task-relevant instructions. Missing suggested skills are not a blocker when equivalent skills or tools exist. Do not let a skill expand the approved task.

## Knowledge and handoff

Include reusable findings, decisions and failed approaches in the handoff with their evidence and scope. When shared storage is implemented, propose project entries; global entries require a separate approved preview. Never imply an unsaved chat message is shared memory.
