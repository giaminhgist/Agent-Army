# Agent-Army

An army of research and engineering sub-agents for **Claude Code** and **Codex CLI**. It runs inside the chat, and both tools share **one knowledge and memory store**.

Một đội sub-agent cho nghiên cứu và kỹ thuật, chạy trong chat của Claude Code và Codex. Kiến thức và memory dùng chung cho cả hai, chia thành tầng global và project. Người dùng tự chọn mục nào từ project được đưa lên global.

Agent-Army is a simplified rewrite of Research-Agent:

- **No skills are bundled or installed.** Install whichever skills you like. Each agent has 10 *recommended* skills: it uses them when they are installed and relevant, and it may use any other installed skill.
- Stdlib-only Python ≥ 3.11. No venv, no pip.
- Supports Linux and macOS.

## Install

```bash
git clone <this repo> ~/Agent-Army && cd ~/Agent-Army
python3 install.py --dry-run      # show what would change
python3 install.py                # auto-detects claude and/or codex; or pass --claude / --codex
army doctor                       # health check + which recommended skills are missing
```

The installer writes to these places, all listed in `~/.agent-army/install-manifest.json`:

| What | Where |
|---|---|
| App, launcher, global store | `~/.agent-army/` (`app/`, `bin/army`, `knowledge/`, `memory/`, `army.toml`) |
| CLI | `~/.local/bin/army` (symlink) |
| Claude Code | `~/.claude/agents/army-*.md`, `~/.claude/skills/army/`, hook groups in `~/.claude/settings.json`, a marked block in `~/.claude/CLAUDE.md` |
| Codex | `~/.codex/agents/army_*.toml`, `~/.agents/skills/army/`, hook groups in `~/.codex/hooks.json`, a marked block in `~/.codex/AGENTS.md` |

**Codex:** after installing, run `/hooks` once inside Codex to trust the Agent-Army hooks.

**Uninstall:** `python3 install.py --uninstall` keeps your global knowledge and memory. Add `--purge` to delete those too.

**Update:** run `git pull`, then `python3 install.py`. Your edited `~/.agent-army/army.toml` is never overwritten.

## Use

| | Claude Code | Codex |
|---|---|---|
| Hand a goal to the commander | `/army <goal> [--loop research\|coding\|full]` | `$army <goal>` |
| Call one specialist | "use army-scout to …" | "have army_scout …" |

In a project, start with `army init --raw data/raw --sensitive data/phi`. This creates `.agent-army/` and declares the raw-data directories as read-only.

## The army

| Agent | Tier | Role | Recommended skills |
|---|---|---|---|
| commander | heavy | Plans, dispatches, runs the verification gate and loops, keeps memory, asks what goes global | brainstorming, writing-plans, executing-plans, dispatching-parallel-agents, subagent-driven-development, verification-before-completion, research-pipeline, idea-discovery, research-refine-pipeline, get-available-resources |
| scout | light | Literature, SOTA, gaps, datasets, citations | research-lit, arxiv, semantic-scholar, openalex, alphaxiv, research-wiki, literature-review, citation-management, research-lookup, paper-lookup |
| strategist | medium | Ideas, hypotheses, novelty, experiment design, stats plan, ablations | idea-creator, novelty-check, research-refine, experiment-plan, ablation-planner, hypothesis-generation, experimental-design, scientific-brainstorming, statistical-power, brainstorming |
| engineer | light | Code, pipelines, TDD, debugging, refactoring | test-driven-development, systematic-debugging, requesting-code-review, receiving-code-review, using-git-worktrees, verification-before-completion, research-implement-feature, experiment-bridge, web-debug-search, optimize-for-gpu |
| experimenter | light | Runs, monitoring, data validation, analysis, figures | run-experiment, experiment-queue, monitor-experiment, training-check, analyze-results, result-to-claim, exploratory-data-analysis, statistical-analysis, scientific-visualization, matplotlib |
| writer | medium | Manuscripts, proposals, rebuttals, docs | paper-writing, paper-plan, paper-figure, paper-compile, rebuttal, grant-proposal, scientific-writing, venue-templates, citation-management, scientific-schematics |
| editor | light | Polish, AI-pattern removal, consistency | humanizer, paper-claim-audit, citation-audit, citation-crosscheck, auto-paper-improvement-loop, writing-systems-papers, scientific-writing, venue-templates, scientific-critical-thinking, verification-before-completion |
| reviewer | medium | Independent critique, side-by-side comparison | research-review, kill-argument, auto-review-loop, novelty-check, experiment-audit, proof-checker, peer-review, scientific-critical-thinking, scholar-evaluation, receiving-code-review |
| auditor | medium | Verification gate: re-checks and returns accept / repair / reject | experiment-audit, result-to-claim, citation-audit, citation-crosscheck, paper-claim-audit, integrity-forensics, proof-checker, statistical-analysis, uncertainty-and-units, verification-before-completion |

The skills come from [superpowers](https://github.com/obra/superpowers), [ARIS](https://github.com/wanshuiyin/auto-claude-code-research-in-sleep), [K-Dense scientific-agent-skills](https://github.com/k-dense-ai/scientific-agent-skills) and [humanizer](https://github.com/blader/humanizer).

**Tiers:**

| Tier | Claude Code | Codex |
|---|---|---|
| light | sonnet | effort medium |
| medium | opus | effort high |
| heavy | fable | effort xhigh |

On Claude, the commander may escalate an agent to a higher tier when a task needs it. On Codex, each agent always runs at its fixed tier.

**Change agents:** edit `~/.agent-army/army.toml` (tiers, skills, Codex model, `cross_model_check`), then run `army build` and restart Claude Code / Codex.

## Knowledge and memory (shared by Claude and Codex)

```
~/.agent-army/{knowledge,memory}/        GLOBAL
<project>/.agent-army/{knowledge,memory}/ PROJECT  (+ plan.md, runs.jsonl, project.toml)
```

| Command | What it does |
|---|---|
| `army kb add --type paper\|note --title T [--tags a,b] [--source S] [--global]` | Add an item. The body comes from stdin or `--body-file`. |
| `army kb search "query" [--scope project\|global\|all]` | SQLite FTS5 search. Project results come first, and Vietnamese works without diacritics. |
| `army mem add "text" --kind decision\|progress\|lesson\|preference [--global]` | Add a memory. |
| `army mem list` / `army mem brief` | List memories / print the session brief. |
| `army promote --list \| --pick \| <ids> \| --reject <ids>` | Move project items to global, only the ones you choose. |

New project papers, notes, lessons and preferences start as *pending*. Nothing reaches global until you promote it.

## Harness

| | |
|---|---|
| H1 `army init` | Creates the project store and declares raw (read-only) and sensitive dirs |
| H2 Session-start brief | Hook: injects open tasks, recent decisions, progress and global lessons |
| H3 Promote reminder | Stop hook, shown only when the pending count grows |
| H4 Raw-data guard | PreToolUse hook: blocks writes, deletes and moves into raw dirs |
| H5 `army run -- cmd` | Run log: run_id, git sha, dirty flag, seed, exit code, log file |
| H6 Plan and handoff | `.agent-army/plan.md` plus a fixed handoff block from every agent |
| H7 Verification gate | Auditor returns accept / repair / reject; at most 3 rounds |
| H8 Cross-model check | Off by default; reviewer/auditor ask the other platform (`codex exec` / `claude -p`) |
| H9 Pre-compact snapshot | Saves status before context compaction; it is re-injected afterwards |
| H10 `army status` | Plan, recent runs, pending count |
| H11 `army doctor` | Installation health and missing recommended skills |

Every hook fails open: on error it never blocks you, and it logs to `~/.agent-army/hook-errors.log`.

## Develop

```bash
python3 -m unittest discover -s tests -t .
```
