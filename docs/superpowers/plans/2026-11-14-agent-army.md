# Agent-Army Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Agent-Army: 9 sub-agents (commander + 8 workers) plus an `army` entry skill. It installs on both Claude Code and Codex CLI, and the two platforms share one knowledge/memory store with global and project tiers and user-approved promotion.

**Architecture:**
- One source of truth: `army.toml` (agents, tiers, recommended skills, options) plus `prompts/*.md`.
- A stdlib-only Python package `army` (CLI + hook handlers) does three things: renders agents for both platforms, runs the knowledge base (markdown files + SQLite FTS5 index), and serves the hooks.
- `install.py` deploys into `~/.agent-army`, `~/.claude` and `~/.codex`, and records everything in a manifest so uninstall is clean.

**Tech Stack:** Python ≥ 3.11 stdlib only (`tomllib`, `sqlite3` FTS5, `argparse`, `shlex`, `json`, `unittest`). No third-party deps. Tests: `python3 -m unittest discover -s tests -v` (pytest is not installed on this machine).

**Spec:** `docs/PLAN.md` (approved 2026-11-14, sections 1–11 incl. harness H1–H11).

## Global Constraints

- Repo root: `/home/hoang_giaminh190596/Army-Agent/Agent-Army`. Package lives at `src/army/`. Tests live at `tests/`.
- Runtime is stdlib-only and requires Python ≥ 3.11. Do not use pip, a venv, or a third-party import.
- Global store is `$ARMY_HOME` (default `~/.agent-army`). Project store is `<project>/.agent-army/`. A project is recognized **only** by `<dir>/.agent-army/project.toml`.
- Ship exactly 9 agents, in this order: `commander, scout, strategist, engineer, experimenter, writer, editor, reviewer, auditor`.
- Claude agent names are `army-<name>` and go in `~/.claude/agents/army-<name>.md`. Codex agent names are `army_<name>` and go in `~/.codex/agents/army_<name>.toml`.
- Tiers:
  - Claude: light=`sonnet`, medium=`opus`, heavy=`fable`.
  - Codex: light=effort `medium`, medium=effort `high`, heavy=effort `xhigh`. `model` is optional; when empty it is omitted from the file. The tier is fixed per agent and never escalated on Codex.
- Default tiers: commander heavy; scout, engineer, experimenter, editor light; strategist, writer, reviewer, auditor medium.
- Skills are **recommended, not preloaded**. Never emit a `skills:` frontmatter key. Missing skills only produce a doctor WARN.
- Do not use evidence labels (`[SOURCED]` etc.) anywhere.
- Do not build budget caps, an approval queue, automatic gate checks, or a headless runner.
- `cross_model_check` defaults to `false`.
- Every hook handler fails open: on any exception it exits 0, prints nothing, and appends the traceback to `$ARMY_HOME/hook-errors.log`.
- Supported platforms are Linux and macOS (Windows is a non-goal for v1; my call).
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

### CLI surface (all tasks agree on this)

| Command | Behavior |
|---|---|
| `army init [--raw DIR]... [--sensitive DIR]...` | H1. Create the project store in cwd. |
| `army kb add --type paper\|note --title T [--tags a,b] [--source S] [--global] [--body-file F]` | Add a knowledge item (body read from stdin if no `--body-file`). Prints the id. |
| `army kb search QUERY [--scope project\|global\|all] [--limit N] [--json]` | Search. Default scope `all`, limit 10. |
| `army mem add TEXT --kind decision\|progress\|lesson\|preference [--global]` | Add a memory item (title = first 80 chars of TEXT). |
| `army mem list [--scope project\|global] [--kind K]` / `army mem brief` | List / print the session brief. |
| `army promote --list \| --pick \| --reject ID... \| ID...` | Promote to global. |
| `army run [--seed N] [--out PATH] -- CMD...` | H5. Exit code equals CMD's exit code. |
| `army status` | H10 |
| `army doctor` | H11. Exit 1 if any FAIL. |
| `army build` | Re-render agents from `$ARMY_HOME/army.toml` and redeploy to installed platforms. |
| `army hook EVENT --platform claude\|codex` | EVENT ∈ `session-start, stop, pre-tool-use, pre-compact`. Reads the payload JSON from stdin. |

## Review Focus

1. **Home directory mistaken for a project.** Running from any subdirectory of `$HOME` must not treat `~/.agent-army` (the global store) as a project. Test → Task 1 `test_home_store_is_not_a_project`.
2. **Re-running `install.py`.** It must not duplicate hook entries or CLAUDE.md/AGENTS.md blocks, and must not overwrite a user-edited `~/.agent-army/army.toml`. Test → Task 10 `test_install_is_idempotent_and_keeps_user_config`.
3. **A broken hook must never block the user.** Garbage stdin, a missing `project.toml`, or a corrupt `index.sqlite` must all exit 0. Test → Task 6 `test_hooks_fail_open`.
4. **Stop hook fires every turn.** It must notify only when the pending count *increases* since the last notice. Test → Task 6 `test_stop_notifies_only_on_increase`.
5. **Search input.** Queries with FTS syntax characters (`"`, `-`, `:`, `*`, `(`) must not raise. Vietnamese without diacritics must match text with them ("kien thuc" finds "kiến thức"). Test → Task 2 `test_search_odd_queries_and_diacritics`.

---

### Task 1: Repo skeleton, paths, frontmatter, config

**Files:**
- Create: `army.toml`, `src/army/__init__.py` (`__version__ = "0.1.0"`), `src/army/__main__.py`, `src/army/paths.py`, `src/army/frontmatter.py`, `src/army/config.py`, `tests/__init__.py`, `tests/helpers.py`, `tests/test_core.py`, `.gitignore`

**Interfaces:**
- Produces:
  - `paths.army_home() -> Path`
  - `paths.find_project(start: Path | None = None) -> Path | None`. Walks up from start/cwd and returns the first dir containing `.agent-army/project.toml`. It skips the dir whose `.agent-army` resolves to `army_home()`.
  - `paths.state_dir(project: Path) -> Path`
  - `paths.scope_dir(scope: str, project: Path | None) -> Path`. Raises `ValueError` for scope `project` with `project=None`.
  - `frontmatter.parse(text: str) -> tuple[dict, str]` and `frontmatter.dump(meta: dict, body: str) -> str`. Values: str, int, bool, list[str] as inline `[a, b]`. Split on the first `": "`.
  - `config.load_config() -> dict`. Reads `$ARMY_HOME/army.toml` if present, else the repo default at `Path(__file__).resolve().parents[2] / "army.toml"`.
  - `config.agent_names(cfg) -> list[str]`
  - `config.tier_for(cfg, agent: str, platform: str) -> dict`. Returns `{"model": str|None, "effort": str|None}`.
  - `tests/helpers.py`: class `TempHome(unittest.TestCase)` with setUp/tearDown that set `HOME` and `ARMY_HOME` to fresh temp dirs and chdir into a temp project dir `self.proj`.

- [ ] **Step 1:** `git init` in the repo root. Add a `.gitignore` covering `__pycache__/`, `*.pyc`, `build/`.
- [ ] **Step 2: Write `army.toml`** with this schema. Use the 10 skills per agent and the tiers verbatim from spec §5 and Global Constraints. `description` is one sentence, taken from the spec §3 role column. `tools` per agent:
  - commander: `Agent, AskUserQuestion, Read, Write, Edit, Glob, Grep, Bash, Skill, TodoWrite, WebSearch, WebFetch`
  - scout, strategist, writer: `Read, Write, Edit, Glob, Grep, Bash, Skill, WebSearch, WebFetch`
  - engineer, experimenter: `Read, Write, Edit, Glob, Grep, Bash, Skill, NotebookEdit`
  - editor: `Read, Write, Edit, Glob, Grep, Bash, Skill`
  - reviewer, auditor: `Read, Write, Glob, Grep, Bash, Skill, WebSearch, WebFetch`
```toml
[options]
cross_model_check = false
[tiers.claude]
light = "sonnet"
medium = "opus"
heavy = "fable"
[tiers.codex.light]
effort = "medium"
model = ""
[tiers.codex.medium]
effort = "high"
model = ""
[tiers.codex.heavy]
effort = "xhigh"
model = ""
[agents.scout]
tier = "light"
description = "..."
tools = ["Read", "..."]
skills = ["research-lit", "arxiv", "semantic-scholar", "openalex", "alphaxiv", "research-wiki", "literature-review", "citation-management", "research-lookup", "paper-lookup"]
```
- [ ] **Step 3: Write failing tests** in `tests/test_core.py`:
  - `test_frontmatter_roundtrip`: meta `{"id":"a","tags":["x","y"],"n":3,"ok":True,"title":"a: b"}` round-trips exactly.
  - `test_config_has_nine_agents_with_ten_skills`: `agent_names` equals the order in Global Constraints, and each agent has `len(skills)==10`.
  - `test_tier_for`: `tier_for(cfg,"scout","claude")=={"model":"sonnet","effort":None}` and `tier_for(cfg,"auditor","codex")=={"model":None,"effort":"high"}`.
  - `test_find_project`: after creating `proj/.agent-army/project.toml`, `find_project(proj/"a"/"b")==proj`.
  - `test_home_store_is_not_a_project`: with `ARMY_HOME=$HOME/.agent-army` containing a `project.toml` file, `find_project($HOME/"x")` is `None`.
- [ ] **Step 4:** Run `python3 -m unittest discover -s tests -v`. Expected: FAIL (import errors). Run tests with `PYTHONPATH=src`. `tests/__init__.py` inserts `src` into `sys.path`.
- [ ] **Step 5:** Implement the modules listed in Interfaces. `__main__.py` calls `army.cli.main()`. Create a stub `cli.py` with `main()` that prints the version.
- [ ] **Step 6:** Run the tests. Expected: PASS.
- [ ] **Step 7:** Commit `feat: skeleton, paths, frontmatter, config`.

### Task 2: Item store + FTS5 search

**Files:**
- Create: `src/army/store.py`, `src/army/index.py`, `tests/test_store.py`

**Interfaces:**
- Consumes: `paths.scope_dir`, `frontmatter.parse/dump`.
- Produces:
  - `store.Item` dataclass. Fields: `id, type, title, scope, path: Path, meta: dict, body: str`.
  - `store.KNOWLEDGE_TYPES = ("paper","note")`, stored in `<scope>/knowledge/`.
  - `store.MEMORY_TYPES = ("decision","progress","lesson","preference")`, stored in `<scope>/memory/`.
  - `store.add_item(scope, type, title, body, tags=(), source="", project=None) -> Item`.
    - `id = f"{type}-{slug(title)[:40]}-{sha1(title+iso_now)[:6]}"`. `slug` is ASCII-folded with NFKD and joined by `-`.
    - Meta keys: `id, type, title, tags, source, created, scope`, plus `origin_project` (str path) and `promote` when scope=project.
    - `promote` default: `pending` for paper/note/lesson/preference, `no` for decision/progress.
    - Unknown type raises `ValueError`.
  - `store.load_items(scope, project=None, type=None) -> list[Item]`, sorted by `created` descending.
  - `store.get_item(item_id, scope, project=None) -> Item | None`
  - `store.update_meta(item, **changes) -> Item` (rewrites the file).
  - `index.Hit` dataclass. Fields: `scope, id, title, path: Path, snippet: str, score: float`.
  - `index.search(query, scope="all", project=None, limit=10) -> list[Hit]`. Project hits come before global hits.
- Index design:
  - One `index.sqlite` per scope dir.
  - Table `docs(path TEXT PRIMARY KEY, mtime REAL)` plus `fts USING fts5(path UNINDEXED, id, title, tags, body, tokenize="unicode61 remove_diacritics 2")`.
  - Refresh before each search: index new or changed files by mtime, delete rows for removed files.
  - Query: extract `\w+` tokens, quote each, join with ` OR `. Empty → `[]`. Rank by `bm25`. Snippet via `snippet(fts, 4, '[', ']', '…', 12)`.
  - If `index.sqlite` is corrupt (`sqlite3.DatabaseError`), delete it and rebuild once.

- [ ] **Step 1: Write failing tests:**
  - `test_add_and_load`: a project paper has `promote=="pending"` and a decision has `promote=="no"`. The file exists under `knowledge/` or `memory/`.
  - `test_search_project_before_global`: the same word in a project note and a global note returns the project hit first, `scope=="project"`.
  - `test_search_scope_isolation`: `scope="project"` never returns global items.
  - `test_index_updates_on_edit_and_delete`
  - `test_search_odd_queries_and_diacritics`:
    - Queries `'"'`, `'a-b:c*'`, `'('` return lists without raising.
    - A note with body "kiến thức nền" is found by `"kien thuc"`.
  - `test_corrupt_index_rebuilds`: write garbage bytes to `index.sqlite`; search still finds the item.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement per Interfaces.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: item store and FTS5 search`.

### Task 3: Promote, brief, and the kb/mem/promote CLI

**Files:**
- Create: `src/army/promote.py`, `src/army/brief.py`, `tests/test_promote.py`
- Modify: `src/army/cli.py` (argparse with subcommands `kb`, `mem`, `promote` per the CLI table)

**Interfaces:**
- Consumes: `store.*`, `index.search`, `paths.find_project`.
- Produces:
  - `promote.pending(project) -> list[Item]`
  - `promote.promote(ids: list[str], project) -> list[Item]`.
    - Copies each item into global with `scope=global`, keeps `origin_project`, drops the `promote` key, keeps the same `id`.
    - Sets the project item to `promote: yes`.
    - An already-`yes` item is skipped and not duplicated. An unknown id raises `KeyError`.
  - `promote.reject(ids, project) -> None` sets `promote: no`.
  - `promote.pick(project, input_fn=input, print_fn=print) -> list[Item]`. Prints a numbered list `"{n}. [{type}] {title} ({id})"`, then reads `"1,3"` / `"all"` / `"none"` / `""`. Bad input re-prompts once, then returns `[]`.
  - `brief.brief(project: Path | None, max_chars=4000) -> str`. Markdown sections, each omitted when empty:
    - `# Agent-Army memory`
    - `## Open tasks` (unchecked `- [ ]` lines of `plan.md`)
    - `## Recent decisions` (10)
    - `## Progress` (3, plus `snapshot.md` if it exists)
    - `## Global lessons & preferences` (10 titles)
    - A final line `N item(s) pending promotion → army promote --pick` when N>0.
    - Returns `""` when every section is empty. Truncates at `max_chars` with `…`.
  - CLI: when a project-scoped command runs outside a project, it exits 2 with `Not in an Agent-Army project. Run: army init` on stderr. `--global` writes work anywhere.

- [ ] **Step 1: Write failing tests:**
  - `test_promote_copies_with_origin_and_is_idempotent`
  - `test_promote_unknown_id_raises`
  - `test_reject`
  - `test_pick_parses_selection`: inputs `"1"`, `"all"`, `""`, and `"x"` then `"x"`.
  - `test_brief_empty_is_empty_string`
  - `test_brief_sections_and_pending_line`
  - `test_cli_kb_add_and_search`: call `cli.main([...])` and capture stdout.
  - `test_cli_outside_project_exits_2`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: promotion, session brief, kb/mem/promote CLI`.

### Task 4: Project init (H1) + raw-data guard logic (H4)

**Files:**
- Create: `src/army/project.py`, `src/army/guard.py`, `tests/test_guard.py`
- Modify: `src/army/cli.py` (`init`)

**Interfaces:**
- Produces:
  - `project.init_project(root: Path, raw_dirs: list[str], sensitive_dirs: list[str]) -> Path`.
    - Creates `.agent-army/{knowledge,memory,runs}`.
    - Writes `project.toml`: `name`, `created`, `raw_dirs`, `sensitive_dirs` (paths relative to root). It is hand-written TOML and must be readable by `tomllib`.
    - Creates `plan.md` (`# Plan\n\n| Task | Agent | Output | Done when | Status |\n|---|---|---|---|---|\n`) if missing.
    - Re-running keeps existing lists unless new values are given; new values are appended and deduplicated. Returns the state dir.
  - `project.load_project(root) -> dict`
  - `guard.check(payload: dict, project_root: Path, raw_dirs: list[str]) -> str | None`. Returns the deny reason `"Agent-Army: {path} is inside raw data dir {raw}; raw data is read-only."` or `None`.
- Guard rules:
  - Resolve paths against `payload["cwd"]`.
  - `tool_name` in `Write, Edit, MultiEdit, NotebookEdit`: check `tool_input.file_path` / `notebook_path`.
  - `apply_patch`: check paths from lines matching `^\*\*\* (Add|Update|Delete) File: (.+)$` and `^\*\*\* Move to: (.+)$` in `tool_input.command`.
  - `Bash`:
    - Split `tool_input.command` into segments on `; && || |` using `shlex.shlex(posix=True, punctuation_chars=True)`.
    - Per segment, for any non-flag arg under a raw dir:
      - `rm rmdir unlink shred truncate touch chmod chown mkdir ln tee` → deny.
      - `sed` with `-i*` → deny.
      - `mv` → deny on any arg.
      - `cp`, `rsync`, `install` → deny on the last arg only.
    - The token after `>`, `>>`, `>|` → deny. `dd` with `of=` → deny.
    - On `ValueError` from shlex: deny if any raw dir string appears in the command together with any of the write words above.
  - Anything else → `None`.

- [ ] **Step 1: Write failing tests** (raw dir `data/raw`):
  - These are **denied**:
    - `Write data/raw/a.csv`
    - `rm -rf data/raw`
    - `echo x > data/raw/a.csv`
    - `sed -i s/a/b/ data/raw/a.csv`
    - `mv data/raw/a.csv out/`
    - `cp x.csv data/raw/`
    - apply_patch with `*** Update File: data/raw/a.csv`
    - absolute path to the same file
  - These are **allowed**:
    - `cat data/raw/a.csv`
    - `cp data/raw/a.csv derived/`
    - `python train.py --data data/raw`
    - `Write data/rawish/a.csv` (prefix is not a parent)
    - any command when `raw_dirs=[]`
  - `test_init_project_idempotent`: re-running with a new `--raw` appends it, and `tomllib` parses the file.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: army init and raw-data guard`.

### Task 5: Run log (H5) + status (H10)

**Files:**
- Create: `src/army/runlog.py`, `src/army/status.py`, `tests/test_runlog.py`
- Modify: `src/army/cli.py` (`run`, `status`)

**Interfaces:**
- Produces:
  - `runlog.run(cmd: list[str], project: Path, seed: int | None = None, out: str | None = None) -> dict`.
    - `run_id = f"{%Y%m%d-%H%M%S}-{4 hex}"`.
    - Streams combined output to the terminal and to `.agent-army/runs/<run_id>.log`.
    - Sets env `ARMY_RUN_ID`, and `ARMY_SEED` when a seed is given.
    - Appends a record to `.agent-army/runs.jsonl` with keys `run_id, cmd (shlex.join), cwd, git_sha, git_dirty, seed, started, ended, duration_s, exit_code, log, out`.
    - `git_sha`/`git_dirty` are `None` outside a git repo.
    - A missing executable gives `exit_code 127` and is still recorded.
  - `runlog.recent(project, n=5) -> list[dict]`, newest first. Malformed lines are skipped.
  - `status.status_text(project) -> str`: project name, open tasks from plan.md, the last 5 runs (`run_id exit_code cmd`), pending-promotion count.

- [ ] **Step 1: Write failing tests:**
  - `test_run_records_success_and_failure`: `python3 -c "print(1)"` gives exit 0, and `python3 -c "import sys;sys.exit(3)"` gives record exit_code 3 and CLI exit 3.
  - `test_run_missing_executable`
  - `test_recent_skips_bad_lines`
  - `test_status_text_contains_sections`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: army run log and status`.

### Task 6: Hook handlers (H2, H3, H4, H9)

**Files:**
- Create: `src/army/hooks.py`, `tests/test_hooks.py`
- Modify: `src/army/cli.py` (`hook`)

**Interfaces:**
- Consumes: `brief.brief`, `promote.pending`, `guard.check`, `project.load_project`, `status.status_text`, `paths.find_project`.
- Produces: `hooks.handle(event: str, platform: str, stdin_text: str) -> tuple[int, str, str]` returning `(exit_code, stdout, stderr)`. The CLI writes the result out and exits with the code. The project is found via `find_project(Path(payload["cwd"]))`.
- Events:
  - `session-start`: stdout = `brief(project)` (when there is no project, `brief(None)`). Both platforms treat plain stdout as context. Claude's SessionStart also fires after compaction, which re-injects the snapshot (H9).
  - `stop`:
    - If `n = len(pending(project)) > last` (`last` is read from `.agent-army/.stop-notified`, default 0), write `n` to that file and output `{"systemMessage": "Agent-Army: {n} item(s) pending promotion to global — run `army promote --pick`."}`.
    - If `n < last`, store `n` silently. Otherwise output nothing.
    - Never emit `decision`/`continue`.
  - `pre-tool-use`: if `guard.check` returns a reason → `(2, "", reason)`. Otherwise `(0, "", "")`.
  - `pre-compact`: write `.agent-army/snapshot.md` = `"# Snapshot {iso}\n\n" + status_text(project)`. No stdout.
  - Everything is wrapped as described in Global Constraints (fail open + log). An unknown event also returns `(0,"","")`.

- [ ] **Step 1: Write failing tests:**
  - `test_session_start_outputs_brief`
  - `test_session_start_no_project_no_global_is_silent`
  - `test_stop_notifies_only_on_increase`: pending 1 → message; 1 again → silent; 2 → message; after a promote (0) → silent.
  - `test_pre_tool_use_denies_raw_write`
  - `test_pre_compact_writes_snapshot_and_brief_includes_it`
  - `test_hooks_fail_open`: stdin `"not json"`, a project without `project.toml`, and a corrupt `index.sqlite` each give exit 0, and the error log grows.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: shared hook handlers for claude and codex`.

### Task 7: Prompts (protocol + 9 roles)

**Files:**
- Create: `prompts/_protocol.md`, `prompts/{commander,scout,strategist,engineer,experimenter,writer,editor,reviewer,auditor}.md`, `tests/test_prompts.py`

**Content requirements:**

- **`_protocol.md`** (applies to every agent). Sections:
  - Honesty: say what you checked versus what you assume; never claim a run or citation you did not see.
  - Knowledge first: run `army kb search "<topic>"` before searching the web.
  - Save what you learn:
    - `army kb add --type paper|note ...` for papers and notes, with BibTeX in the body for papers.
    - `army mem add --kind lesson ...` for reusable lessons.
  - Data: raw-data dirs from `.agent-army/project.toml` are read-only; write derived data to new paths.
  - Runs: launch experiments with `army run [--seed N] -- <cmd>` and cite the `run_id` for every reported number.
  - Skills: the recommended list is a starting point; any installed skill may be used.
  - Handoff: every reply ends with the exact block below.
```
## Handoff
Status: completed | partial | blocked
Artifacts: <paths>
Checks performed: <what you ran or verified>
Open questions: <none | list>
```
- **Each role file** has these sections:
  - `# <Role>`, with one sentence of identity.
  - `## Responsibilities`: 5–8 bullets drawn from the source agents named in spec §3 for that row.
  - `## Working method`
  - `## Do not`
- **`auditor.md`:**
  - Treat every step as unverified until you re-check it yourself.
  - Use the domain checks of K-Dense statistical-reviewer, math-checker, ml-auditor (leakage, split), reproducibility-auditor, citation-checker, fact-checker and ethics-reviewer.
  - End with this block, before the Handoff:
```
Verdict: accept | repair | reject
First failing step: <step | none>
Confirmed steps: <list>
```
- **`reviewer.md`:** judgment-style critique (MUST_FIX / SHOULD_FIX / NICE_TO_HAVE), and comparative mode when given several attempts.
- **`commander.md`:** the orchestration procedure:
  1. Run `army mem brief` if not already injected.
  2. Clarify the goal and its constraints.
  3. Write the tasks into `.agent-army/plan.md` (agent, output, done-when, status).
  4. Dispatch with a self-contained brief (inputs, allowed edits, outputs, done-when, limits). Run independent tasks in parallel, and give parallel workers disjoint files.
  5. Send important results through the auditor gate. On `repair`, re-dispatch with the first failing step. Allow at most 3 rounds. Never overrule a `reject` on plausibility.
  6. Loops:
     - research = scout → strategist → reviewer
     - coding = engineer → experimenter → auditor
     - full = both
     - Stop on PASS/accept or after 3 iterations.
  7. Record decisions and progress with `army mem add --kind decision|progress`.
  8. At the end, run `army promote --list`, ask the user which items go global, then run `army promote <ids>` or `--reject`.
  - Tier rule `{{TIER_RULE}}` is a placeholder that build replaces per platform (Task 8).
  - The commander does not do the specialist work itself.

- [ ] **Step 1: Write failing test** `test_prompts_complete`:
  - Every agent in config has a prompt file containing `## Responsibilities`.
  - `_protocol.md` contains `## Handoff` and `army kb search`.
  - `auditor.md` contains `Verdict: accept | repair | reject`.
  - `commander.md` contains `{{TIER_RULE}}`.
  - No file matches `\[(SOURCED|RUN|INFERRED|HYPOTHESIS)`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Write the prompts.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: agent prompts and shared protocol`.

### Task 8: Renderer

**Files:**
- Create: `src/army/build.py`, `tests/test_build.py`

**Interfaces:**
- Consumes: `config.*`, `prompts/`.
- Produces:
  - `build.render_claude_agent(name, cfg, prompts_dir) -> str`.
    - Frontmatter: `name: army-<name>`, `description`, `model: <claude tier>`, `tools: <comma list>`.
    - Body: role prompt + protocol + skills section, plus a cross-model section when enabled.
  - `build.render_codex_agent(name, cfg, prompts_dir) -> str`. TOML with `name = "army_<name>"`, `description`, `model` (only if non-empty), `model_reasoning_effort`, and `developer_instructions` written as `json.dumps(body)` (valid TOML basic string).
  - `build.render_skill(cfg, prompts_dir, platform) -> str`. `SKILL.md` with frontmatter `name: army`, `description: "Agent-Army commander: plan a multi-step research/engineering goal and dispatch the army's specialist sub-agents (scout, strategist, engineer, experimenter, writer, editor, reviewer, auditor), with shared global/project memory."` Body: commander prompt + protocol + a roster table (platform agent name | tier | description) + the commander's 10 recommended skills.
  - `build.build_all(cfg, prompts_dir, out_dir) -> dict[str, list[Path]]` with keys `claude_agents, codex_agents, claude_skill, codex_skill`. Output layout: `out/claude/agents/*.md`, `out/codex/agents/*.toml`, `out/claude/skills/army/SKILL.md`, `out/codex/skills/army/SKILL.md`.
- Exact copy:
  - Skills section: `## Skills\nRecommended skills (use when installed and relevant): {comma list}. Names may carry a plugin prefix (e.g. `superpowers:brainstorming`). If one is not installed, skip it. If the task needs a skill not on this list, look through the installed skills and use the one that fits.`
  - `{{TIER_RULE}}` on claude: `Each agent has a default tier (light=sonnet, medium=opus, heavy=fable). Dispatch at the default; pass a higher \`model\` only when the task clearly needs deeper reasoning, and say why.`
  - `{{TIER_RULE}}` on codex: `Each agent runs at its fixed default tier; do not try to override the model when spawning.`
  - Cross-model section (only for reviewer and auditor when `cross_model_check=true`): `## Cross-model check\nFor important verdicts, also ask a different model: run {cmd} with a self-contained brief, and reconcile its findings with yours.`
    - Claude cmd: `` `codex exec --sandbox read-only "<brief>"` ``
    - Codex cmd: `` `claude -p --permission-mode plan "<brief>"` ``

- [ ] **Step 1: Write failing tests:**
  - `test_claude_agent_frontmatter`: parses; `model` is `sonnet` for scout and `fable` for commander; no `skills:` key; body has all 10 scout skills.
  - `test_codex_agent_toml_valid`: `tomllib.loads` works, `name=="army_scout"`, `model_reasoning_effort=="medium"`, the `model` key is absent, and `developer_instructions` round-trips a body containing `"""` and backslashes.
  - `test_tier_rule_per_platform`
  - `test_cross_model_only_when_enabled_and_only_reviewer_auditor`
  - `test_build_all_writes_9_plus_9_plus_2`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: render agents and entry skill for claude and codex`.

### Task 9: Doctor (H11)

**Files:**
- Create: `src/army/doctor.py`, `tests/test_doctor.py`
- Modify: `src/army/cli.py` (`doctor`)

**Interfaces:**
- Produces:
  - `doctor.find_skill(name, platform) -> Path | None`.
    - Claude roots: `~/.claude/skills/<name>/SKILL.md` and glob `~/.claude/plugins/cache/**/skills/<name>/SKILL.md`.
    - Codex roots: `~/.agents/skills/<name>`, `~/.codex/skills/<name>`, `~/.codex/plugins/cache/**/skills/<name>`.
    - Uses `Path.home()`.
  - `doctor.Check` dataclass with fields `status ("OK"|"WARN"|"FAIL"), name, detail`.
  - `doctor.run_checks(platforms: list[str]) -> list[Check]`, in this order:
    1. python ≥ 3.11 (FAIL)
    2. FTS5 (FAIL)
    3. `$ARMY_HOME` exists (FAIL)
    4. `army` on PATH (WARN)
    5. per platform: 9 agent files (FAIL), entry skill (FAIL), hooks registered (WARN)
    6. codex: `Trust the hooks once in Codex with /hooks` (WARN, informational)
    7. per platform: one WARN listing missing recommended skills, as `name (agents…)`
  - `platforms` = those recorded in the install manifest (Task 10), or an empty list.
  - Output lines are `[OK]   name — detail`.

- [ ] **Step 1: Write failing tests:**
  - `test_find_skill_bare_and_plugin_cache` (fake dirs under temp HOME)
  - `test_missing_skills_warn_not_fail`
  - `test_doctor_exit_code`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: army doctor`.

### Task 10: Installer, uninstaller, `army build` deploy

**Files:**
- Create: `src/army/install.py`, `install.py` (thin wrapper: puts `src` on `sys.path` and calls `army.install.main()`), `tests/test_install.py`
- Modify: `src/army/cli.py` (`build` → `install.redeploy()`)

**Interfaces:**
- Produces:
  - `install.main(argv: list[str] | None = None) -> int`. Flags: `--claude`, `--codex` (default: whichever of `claude`/`codex` is on PATH), `--uninstall`, `--purge` (with uninstall, also delete knowledge/memory), `--dry-run` (print actions, write nothing).
  - `install.redeploy() -> None`
  - Manifest at `$ARMY_HOME/install-manifest.json`: `{"version", "platforms": [...], "files": [...], "app": path}`.
- Install steps:
  1. Copy `src/army`, `prompts`, `army.toml` → `$ARMY_HOME/app/`. Copy `army.toml` → `$ARMY_HOME/army.toml` **only if missing**.
  2. Write the launcher `$ARMY_HOME/bin/army` (`#!/bin/sh\nPYTHONPATH="<app>/src" exec "<sys.executable>" -m army "$@"`, chmod 755). Symlink it to `~/.local/bin/army`, replacing only an existing symlink that points into `$ARMY_HOME`. Warn if `~/.local/bin` is not on PATH.
  3. Mkdir `$ARMY_HOME/{knowledge,memory}`.
  4. `build_all` into `$ARMY_HOME/app/build`, then copy to targets.
     - Claude → `~/.claude/agents/`, `~/.claude/skills/army/`
     - Codex → `~/.codex/agents/`, `~/.agents/skills/army/`
  5. Hooks. The command is `"<ARMY_HOME>/bin/army hook <event> --platform <p>"`.
     - Claude: merge into `~/.claude/settings.json` under `hooks`.
       - Events `SessionStart`, `Stop`, `PreCompact` without a matcher; `PreToolUse` with matcher `Write|Edit|MultiEdit|NotebookEdit|Bash`.
       - Back up to `settings.json.army-bak` once.
     - Codex: merge into `~/.codex/hooks.json`. Same events; `PreToolUse` matcher is `Bash|apply_patch`.
     - Before adding, remove any existing group whose command contains `/.agent-army/bin/army hook`.
     - Preserve all other keys and hooks.
  6. Write the instruction block between `<!-- agent-army:start -->` and `<!-- agent-army:end -->`, appended to `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`; replace it if already present. Text:
     > Agent-Army is installed. In a project with `.agent-army/`, its memory is injected at session start. Search knowledge with `army kb search "<query>"`, save with `army kb add` / `army mem add`, and use the `army` skill for multi-step research or engineering goals.
  7. Write the manifest, then run doctor and print it.
- Uninstall:
  - Delete the manifest's files plus `app/` and `bin/`.
  - Remove the agent-army hook groups and instruction blocks.
  - Remove the `~/.local/bin/army` symlink.
  - Keep `knowledge/`, `memory/` and `army.toml` unless `--purge` is given.

- [ ] **Step 1: Write failing tests**, all in a temp HOME with fake `~/.claude/settings.json` containing a user hook and an unrelated key:
  - `test_install_both_platforms_layout`: 9+9 agent files, both skills, launcher executable, manifest.
  - `test_install_is_idempotent_and_keeps_user_config`:
    - Install twice: exactly one agent-army group per event; one marker block in each md; the user hook and unrelated key are intact.
    - A user-edited `army.toml` (scout tier changed to medium) survives, and a subsequent `redeploy()` renders `model: opus` for scout.
  - `test_uninstall_restores`: no agent-army hooks, blocks, or agent files remain; knowledge is kept; `--purge` removes it.
  - `test_dry_run_writes_nothing`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: installer, uninstaller, army build`.

### Task 11: README + end-to-end smoke on this machine

**Files:**
- Create: `README.md` (Vietnamese and English)
  - Contents: what it is, install/uninstall, the 9-agent table with tiers and skills, usage in Claude (`/army ...`, `army-scout`) and Codex (`$army ...`, `army_scout`), the memory model and promotion, the harness list, how to edit `army.toml` and run `army build`, the Codex `/hooks` trust step.
- Test: `tests/test_e2e.py`

- [ ] **Step 1: Write failing test** `test_e2e_cli_flow`. In a temp HOME:
  1. `install.main(["--claude","--codex"])`
  2. In a temp project, run the launcher via subprocess: `init --raw data/raw`, `kb add` (stdin body), `kb search`, `mem add --kind decision`, `run -- python3 -c "print(42)"`, `status`.
  3. Pipe a SessionStart JSON into `hook session-start --platform codex`; stdout contains `Recent decisions`.
  4. Pipe a PreToolUse Write into `data/raw/x` through `hook pre-tool-use --platform claude`; it exits 2.
  5. `promote <id>`, then `kb search --scope global` finds it.
- [ ] **Step 2:** Run. Expected: FAIL until README/e2e are wired, then PASS. Run the full suite: `python3 -m unittest discover -s tests -v`. All pass.
- [ ] **Step 3: Real install on this machine.**
  - `python3 install.py --dry-run`, then `python3 install.py`, then `army doctor`.
  - Expected: no FAIL. WARNs for missing skills are listed (e.g. `humanizer` for claude).
  - Ask the user before the real install, since it edits `~/.claude/settings.json` and `~/.codex/hooks.json`.
- [ ] **Step 4:** Commit `docs: README; test: e2e`.
