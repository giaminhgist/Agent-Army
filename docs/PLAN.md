# Agent-Army — Kế hoạch (bản nháp để duyệt)

Ngày: 2026-11-14 · Trạng thái: **chờ duyệt, chưa viết code**

## 1. Ý tưởng

Agent-Army là bản viết lại từ Research-Agent, theo hướng **đơn giản hơn**:

- Một đội sub-agent chuyên môn, gọi từ chat, chạy được trên **Claude Code** và **Codex CLI**.
- Mỗi agent có **tier mặc định** (light / medium / heavy). Commander được nâng tier khi task cần.
- Mỗi agent có **10 skill đề xuất**. Đây chỉ là gợi ý, không preload cứng: skill nào chưa cài thì bỏ qua, và agent vẫn được dùng mọi skill khác đã cài.
- **Không cài skill repo nào.** Người dùng tự cài skill. Agent-Army chỉ đọc những skill đang có.
- **Kiến thức + memory dùng chung giữa Claude và Codex**, có 2 tầng: global và project. Người dùng chọn mục nào từ project được đưa lên global.

## 2. Nguồn tham khảo đã đọc

| Nguồn | Lấy gì |
|---|---|
| Research-Agent | 7 vai trò (orchestrator, research, methodology, coding, experiment, writing, reviewer), cách chia tier, KB dạng SQLite FTS5, hàng chờ promote lên global |
| agents.zip (14 agent) | python-pro, refactoring-specialist, ml-engineer, data-scientist, data-engineer, research-analyst, scientific-literature-researcher, documentation-engineer, ai-writing-auditor, agent-organizer, research-assistant |
| K-Dense BYOK (23 specialist) | code-reviewer, statistical-reviewer, math-checker, ml-auditor, data-validator, reproducibility-auditor, pipeline-engineer, data-visualizer, literature-researcher, citation-checker, fact-checker, methodology-reviewer, peer-reviewer, comparative-reviewer, hypothesis-generator, investigator, experiment-designer, protocol-writer, results-interpreter, manuscript-editor, abstract-writer, ethics-reviewer; cơ chế **verification gate** (accept / repair / reject) |

## 3. Đội hình đề xuất (9 sub-agent)

| # | Agent | Tier mặc định | Vai trò | Gộp từ |
|---|---|---|---|---|
| 1 | **commander** | heavy | Hiểu mục tiêu, lập kế hoạch, giao việc, ghép kết quả, quản lý memory, hỏi người dùng nên promote mục nào lên global | RA orchestrator, agent-organizer |
| 2 | **scout** | light | Tìm và tổng hợp tài liệu, so sánh SOTA, tìm research gap, lưu paper vào KB | RA research, research-analyst, scientific-literature-researcher, K-Dense literature-researcher |
| 3 | **strategist** | medium | Ý tưởng, giả thuyết có thể bác bỏ, kiểm tra novelty, thiết kế thí nghiệm, kế hoạch thống kê, ablation, protocol | RA methodology, K-Dense hypothesis-generator, experiment-designer, protocol-writer, investigator |
| 4 | **engineer** | light | Code Python/PyTorch, pipeline dữ liệu/ML, TDD, debug, refactor, tối ưu | RA coding, python-pro, refactoring-specialist, ml-engineer, data-engineer, K-Dense pipeline-engineer |
| 5 | **experimenter** | light | Chạy thí nghiệm, theo dõi training, EDA, phân tích thống kê, vẽ hình, diễn giải kết quả | RA experiment, data-scientist, K-Dense data-validator, results-interpreter, data-visualizer |
| 6 | **writer** | medium | Bản thảo, proposal, rebuttal, abstract, tài liệu kỹ thuật, LaTeX, bibliography | RA writing, documentation-engineer, K-Dense manuscript-editor, abstract-writer |
| 7 | **editor** | light | Biên tập văn phong, xóa dấu vết văn AI, kiểm tra thống nhất thuật ngữ | ai-writing-auditor, humanizer |
| 8 | **reviewer** | medium | Phản biện độc lập trong context mới: method, code, bản thảo; so sánh nhiều phương án | RA reviewer, K-Dense peer-reviewer, methodology-reviewer, code-reviewer, comparative-reviewer |
| 9 | **auditor** | medium | Verification gate: kiểm tra lại thống kê, toán, leakage, reproducibility, trích dẫn, fact. Kết luận `accept / repair / reject` | K-Dense statistical-reviewer, math-checker, ml-auditor, reproducibility-auditor, citation-checker, fact-checker, ethics-reviewer |

**Không đưa vào (lý do):**
- agent-installer: Agent-Army không cài thứ gì từ bên ngoài.
- prompt-engineer, machine-learning-engineer (serving / production): ngoài phạm vi research.
- research-assistant: prompt riêng cho một project cụ thể. Giữ lại tinh thần trung thực, giải thích trước khi chạy, và đưa vào protocol chung.

Phân biệt **reviewer** và **auditor**: reviewer đưa ra *nhận định* (thiếu gì, yếu ở đâu). Auditor *kiểm chứng* (tự chạy lại, tra lại, rồi cho verdict). Cách chia này theo K-Dense, và thường nên chạy auditor trên model khác với model đã làm ra kết quả.

## 4. Tier → model

Bảng này nằm trong một file cấu hình, người dùng sửa được.

| Tier | Claude Code | Codex |
|---|---|---|
| light | sonnet | model mặc định của bạn + `model_reasoning_effort = "medium"` |
| medium | opus | model mặc định + `"high"` |
| heavy | fable | model mạnh nhất + `"xhigh"` |

**Đã duyệt:**
- Claude: light = sonnet, medium = opus, heavy = fable. `model:` trong frontmatter là tier mặc định. Commander nâng tier bằng tham số `model` của Agent tool.
- Codex: file `~/.codex/agents/<name>.toml` ghi cố định tier mặc định (model + effort). Codex không nâng tier.

## 5. Skill: đề xuất, không cứng

- Mỗi agent có `recommended_skills` (10 tên), viết **dạng tên trần**, ví dụ `brainstorming`, không phải `superpowers:brainstorming`. Lý do: Codex đọc skill dưới dạng tên trần trong `~/.agents/skills`, còn Claude có tiền tố plugin. Agent tự khớp tên, có hoặc không có tiền tố.
- Prompt của agent ghi: *"Nếu skill đề xuất đã cài thì dùng. Nếu chưa có thì bỏ qua. Nếu task cần skill khác thì tìm trong danh sách skill hiện có và dùng."*
- **Không dùng `skills:` preload** trong frontmatter Claude. Nhờ vậy không bị cứng, và hành vi giống nhau trên hai nền tảng.
- `army doctor` liệt kê skill đề xuất nào chưa cài. Đây chỉ là cảnh báo, không chặn chạy.
- Người dùng sửa danh sách trong `army.toml` (một file duy nhất), rồi chạy `army build` để tạo lại agent.

### 10 skill mặc định cho mỗi agent

Nguồn: **SP** = obra/superpowers · **ARIS** = auto-claude-code-research-in-sleep · **KD** = k-dense scientific-agent-skills · **HZ** = blader/humanizer. Đã đối chiếu tên với từng repo ngày 2026-11-14.

| Agent | 10 skill đề xuất |
|---|---|
| commander | `brainstorming` (SP), `writing-plans` (SP), `executing-plans` (SP), `dispatching-parallel-agents` (SP), `subagent-driven-development` (SP), `verification-before-completion` (SP), `research-pipeline` (ARIS), `idea-discovery` (ARIS), `research-refine-pipeline` (ARIS), `get-available-resources` (KD) |
| scout | `research-lit` (ARIS), `arxiv` (ARIS), `semantic-scholar` (ARIS), `openalex` (ARIS), `alphaxiv` (ARIS), `research-wiki` (ARIS), `literature-review` (KD), `citation-management` (KD), `research-lookup` (KD), `paper-lookup` (KD) |
| strategist | `idea-creator` (ARIS), `novelty-check` (ARIS), `research-refine` (ARIS), `experiment-plan` (ARIS), `ablation-planner` (ARIS), `hypothesis-generation` (KD), `experimental-design` (KD), `scientific-brainstorming` (KD), `statistical-power` (KD), `brainstorming` (SP) |
| engineer | `test-driven-development` (SP), `systematic-debugging` (SP), `requesting-code-review` (SP), `receiving-code-review` (SP), `using-git-worktrees` (SP), `verification-before-completion` (SP), `research-implement-feature` (ARIS), `experiment-bridge` (ARIS), `web-debug-search` (ARIS), `optimize-for-gpu` (KD) |
| experimenter | `run-experiment` (ARIS), `experiment-queue` (ARIS), `monitor-experiment` (ARIS), `training-check` (ARIS), `analyze-results` (ARIS), `result-to-claim` (ARIS), `exploratory-data-analysis` (KD), `statistical-analysis` (KD), `scientific-visualization` (KD), `matplotlib` (KD) |
| writer | `paper-writing` (ARIS), `paper-plan` (ARIS), `paper-figure` (ARIS), `paper-compile` (ARIS), `rebuttal` (ARIS), `grant-proposal` (ARIS), `scientific-writing` (KD), `venue-templates` (KD), `citation-management` (KD), `scientific-schematics` (KD) |
| editor | `humanizer` (HZ), `paper-claim-audit` (ARIS), `citation-audit` (ARIS), `citation-crosscheck` (ARIS), `auto-paper-improvement-loop` (ARIS), `writing-systems-papers` (ARIS), `scientific-writing` (KD), `venue-templates` (KD), `scientific-critical-thinking` (KD), `verification-before-completion` (SP) |
| reviewer | `research-review` (ARIS), `kill-argument` (ARIS), `auto-review-loop` (ARIS), `novelty-check` (ARIS), `experiment-audit` (ARIS), `proof-checker` (ARIS), `peer-review` (KD), `scientific-critical-thinking` (KD), `scholar-evaluation` (KD), `receiving-code-review` (SP) |
| auditor | `experiment-audit` (ARIS), `result-to-claim` (ARIS), `citation-audit` (ARIS), `citation-crosscheck` (ARIS), `paper-claim-audit` (ARIS), `integrity-forensics` (ARIS), `proof-checker` (ARIS), `statistical-analysis` (KD), `uncertainty-and-units` (KD), `verification-before-completion` (SP) |

Ghi chú: trên máy hiện tại, `humanizer` mới có ở `~/.agents/skills` (Codex), chưa có trong `~/.claude/skills`. `army doctor` sẽ báo cảnh báo này.

## 6. Kiến thức & memory dùng chung (Claude + Codex)

Cả hai nền tảng gọi cùng một CLI `army` qua shell, nên cùng đọc và ghi một kho.

```
~/.agent-army/                 # GLOBAL
  knowledge/  *.md (paper, note, có frontmatter) + library.bib
  memory/     *.md (preference, lesson, fact dùng lại giữa project)
  index.sqlite                 # FTS5 / BM25
<project>/.agent-army/         # PROJECT
  knowledge/  memory/  index.sqlite
  memory/decisions.md, progress.md
```

- Mỗi mục là một file markdown có frontmatter: `id, type (paper|note|memory|decision), title, tags, source, scope (project|global), promote: no|pending|yes`.
- `army kb add | search "<query>" [--scope project|global|all]`: tìm project trước, sau đó global. Không bao giờ đọc kho của project khác.
- `army mem add | list | brief`: `brief` in tóm tắt memory để agent đọc đầu phiên.
- **Promote lên global:**
  - `army promote --list` liệt kê các mục `pending`.
  - `army promote <id…>` hoặc `army promote --pick` (chọn tương tác) để đẩy lên global.
  - Commander hỏi người dùng ở cuối mỗi phiên research, review hoặc strategist.
  - Khi promote, mục được copy kèm `origin_project`. Không mục nào tự lên global.
- Tiêm memory đầu phiên:
  - Installer thêm một khối ngắn vào `~/.claude/CLAUDE.md` và `~/.codex/AGENTS.md`, dặn agent chạy `army mem brief` khi có `.agent-army/`.
  - Không dùng hook phức tạp.
- "RAG" v1 là tìm toàn văn BM25. Embedding / vector là tùy chọn cho v2 (xem phần 9).

## 7. Cài đặt & cách dùng

```
git clone … ~/Agent-Army && cd ~/Agent-Army
python3 install.py            # tự phát hiện claude và/hoặc codex
python3 install.py --claude | --codex | --uninstall | --dry-run
```

Installer chỉ làm 4 việc, và ghi manifest để gỡ sạch:

1. Tạo `~/.agent-army/` và cài CLI `army`. Dùng Python ≥ 3.11, chỉ stdlib, không cần venv.
2. Claude: render 9 file vào `~/.claude/agents/army-*.md`.
3. Codex: render 9 file vào `~/.codex/agents/army_*.toml`.
4. Cài skill điều phối `army` vào `~/.claude/skills/army/` và `~/.agents/skills/army/`. Một skill dùng chung làm cổng vào cho cả hai nền tảng.

Dùng trong chat:
- Claude: `/army <mục tiêu> [--loop research|coding|full]`, hoặc gọi tên `army-scout …`.
- Codex: `$army <mục tiêu>`, hoặc "have army_scout …".

Loop là **hướng dẫn trong prompt của commander**, không phải state machine:
- research = scout → strategist → reviewer
- coding = engineer → experimenter → auditor
- full = cả hai luồng
- Dừng khi reviewer/auditor PASS, hoặc sau tối đa 3 vòng.

## 8. Cấu trúc repo

```
Agent-Army/
  army.toml              # NGUỒN DUY NHẤT: agents, tier, recommended_skills, tier→model
  prompts/<agent>.md     # thân prompt từng agent
  prompts/_protocol.md   # luật chung: trung thực, brief/handoff, dùng KB
  skill/army/SKILL.md    # skill điều phối (commander entrypoint)
  src/army/              # cli.py, kb.py, memory.py, build.py, doctor.py  (~800 dòng)
  install.py
  tests/
  docs/PLAN.md
```

## 9. Bỏ gì so với Research-Agent (để đơn giản)

| Bỏ | Lý do |
|---|---|
| Cài 4 skill repo, `skills_catalog.toml`, `routing.toml`, `ra route`/`ra resolve` | Bạn tự cài skill. Agent tự chọn skill. |
| PreToolUse guard, approval queue, fable-dispatch guard | Dùng cơ chế permission sẵn có của Claude/Codex |
| Nhãn bằng chứng `[SOURCED]/[RUN]/[INFERRED]/[HYPOTHESIS]` | Người dùng yêu cầu bỏ |
| Budget caps, `ra job run` manifest, `ra gate check`, loop state machine | Thay bằng reviewer/auditor và run log nhẹ (mục 11) |
| Headless SDK runner, MCP `claude-review` | Chỉ hỗ trợ chạy trong chat |
| Domain checklists | Có thể thêm sau, dưới dạng skill |

Giữ lại: KB FTS5, promote có duyệt, reviewer trong context mới, project isolation.

## 10. Rủi ro / cần kiểm tra trong lúc làm

- Tên skill trùng nhau giữa các repo, ví dụ `scientific-writing`, `paper-writing`, `paper-write`. Agent dùng tên đầu tiên khớp được.
- Claude: subagent không tự spawn subagent khác, nên chỉ commander (luồng chính) điều phối.

## 11. Harness đề xuất (chờ duyệt)

Mọi hook dùng chung một script `army hook <event>`. Trên máy này đã kiểm tra: Claude có hook, Codex 0.169 có feature `hooks = stable`. Vì vậy cùng một logic chạy được cho cả hai nền tảng. Nếu Codex không hỗ trợ event nào, ta dùng dòng hướng dẫn trong `AGENTS.md` để thay.

| # | Harness | Làm gì | Đề xuất |
|---|---|---|---|
| H1 | `army init` | Tạo `.agent-army/` trong project. Hỏi 2 điều: thư mục raw data (chỉ đọc) và dữ liệu nhạy cảm (không gửi ra ngoài). Ghi vào `.agent-army/project.toml`. | **Bật** |
| H2 | Session-start brief (hook) | Đầu phiên: tiêm `army mem brief` (quyết định, tiến độ, top memory global liên quan) và in nhắc nếu đang có mục chờ promote. | **Bật** |
| H3 | Nhắc promote (Stop hook) | Cuối phiên, nếu có mục `pending`, nhắc chạy `army promote --pick`. Hook chỉ nhắc, không tự promote. | **Bật** |
| H4 | Bảo vệ raw data (PreToolUse hook) | Chặn lệnh ghi hoặc xóa vào các thư mục raw data khai báo ở H1. Đây là guard duy nhất được giữ lại. | **Bật** (chỉ khi project có khai báo raw data) |
| H5 | Run log nhẹ: `army run -- <cmd>` | Ghi một dòng vào `.agent-army/runs.jsonl`: `run_id`, lệnh, git sha, có thay đổi chưa commit hay không, seed, thời gian, exit code, đường dẫn output. Thay cho job manifest của Research-Agent. | **Bật** |
| H6 | Plan + handoff chuẩn | Commander ghi kế hoạch vào `.agent-army/plan.md` (mỗi task có agent, đầu ra, tiêu chí xong, trạng thái). Mỗi sub-agent trả handoff theo mẫu K-Dense: trạng thái (completed / partial / blocked), file tạo ra, kiểm tra đã làm, câu hỏi còn mở. Chỉ là quy ước trong prompt, không có CLI. | **Bật** |
| H7 | Verification gate | Kết quả quan trọng chỉ được chấp nhận khi auditor kết luận `accept`. Nếu `repair`, commander giao lại việc kèm lỗi đầu tiên auditor tìm ra. Tối đa 3 vòng. | **Bật** |
| H8 | Cross-model check (Claude ↔ Codex) | Auditor/reviewer có thể nhờ nền tảng kia kiểm tra lại: từ Claude gọi `codex exec`, từ Codex gọi `claude -p`. Mục đích: người kiểm tra là model khác với model làm ra kết quả (theo khuyến nghị của K-Dense). Tốn thêm chi phí. | **Tùy chọn**, tắt mặc định, bật trong `army.toml` |
| H9 | Lưu tiến độ trước compact (PreCompact hook, chỉ Claude) | Trước khi context bị nén, ghi tiến độ hiện tại vào `progress.md` để không mất trạng thái. | **Bật** |
| H10 | `army status` | In kế hoạch, task đang mở, các run gần nhất, số mục chờ promote. | **Bật** |
| H11 | `army doctor` | Kiểm tra: CLI có chạy không, agent đã render chưa, hook đã đăng ký chưa, FTS5 có sẵn không, skill đề xuất nào chưa cài (chỉ cảnh báo). | **Bật** |

**Không đề xuất:** budget cap, approval queue, gate check tự động, chạy headless. Lý do: các phần này làm Research-Agent nặng và nhiều ràng buộc, mà Claude và Codex đã có cơ chế permission riêng.
