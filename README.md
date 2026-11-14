# Agent-Army

**Đội sub-agent cho nghiên cứu và kỹ thuật, chạy trong chat của Claude Code và Codex CLI. Kiến thức và memory dùng chung giữa hai nền tảng.**

Agent-Army là bản viết lại từ [Research-Agent](https://github.com/giaminhgist/Research-Agent), theo hướng **đơn giản hơn và ít ràng buộc hơn**:

- **9 sub-agent chuyên môn.** Mỗi agent có tier model mặc định: light, medium hoặc heavy.
- **Không cài sẵn skill nào.** Bạn tự cài skill mình muốn. Mỗi agent có 10 skill *đề xuất*: agent dùng skill đề xuất khi đã cài, và vẫn được dùng mọi skill khác có trên máy.
- **Một kho kiến thức và memory dùng chung** cho Claude và Codex, chia hai tầng global và project. Bạn tự chọn mục nào từ project được đưa lên global.
- **Một bộ harness gọn:** tóm tắt memory đầu phiên, guard chặn ghi vào raw data, log mỗi lần chạy, cổng kiểm chứng `accept / repair / reject`.
- Chỉ dùng Python chuẩn (≥ 3.11): không cần pip, không cần venv. Hỗ trợ Linux và macOS.

---

## Đội hình

| Agent | Tier | Vai trò |
|---|---|---|
| **commander** | heavy | Hiểu mục tiêu, lập kế hoạch, giao việc, chạy cổng kiểm chứng và các vòng lặp, ghi memory, hỏi bạn mục nào đưa lên global |
| **scout** | light | Tìm và tổng hợp tài liệu, so sánh SOTA, tìm research gap, dataset, kiểm tra trích dẫn |
| **strategist** | medium | Ý tưởng, giả thuyết có thể bác bỏ, novelty, thiết kế thí nghiệm, kế hoạch thống kê, ablation |
| **engineer** | light | Code Python/PyTorch, pipeline, TDD, debug, refactor |
| **experimenter** | light | Chạy thí nghiệm có log, kiểm tra dữ liệu, EDA, thống kê, vẽ hình |
| **writer** | medium | Bản thảo, proposal, rebuttal, tài liệu kỹ thuật, LaTeX |
| **editor** | light | Biên tập văn phong, bỏ dấu vết văn AI, thống nhất thuật ngữ |
| **reviewer** | medium | Phản biện độc lập trong context mới, so sánh nhiều phương án |
| **auditor** | medium | Cổng kiểm chứng: tự kiểm tra lại thống kê, toán, leakage, reproducibility và trích dẫn, rồi kết luận `accept / repair / reject` |

**Tier → model:**

| Tier | Claude Code | Codex |
|---|---|---|
| light | sonnet | model mặc định, effort `medium` |
| medium | opus | model mặc định, effort `high` |
| heavy | fable | model mặc định, effort `xhigh` |

Trên Claude, commander được nâng tier cho một agent khi task cần. Trên Codex, mỗi agent cố định ở tier mặc định.

### Skill đề xuất (10 skill mỗi agent)

Skill lấy từ 4 repo: [superpowers](https://github.com/obra/superpowers) (SP), [ARIS](https://github.com/wanshuiyin/auto-claude-code-research-in-sleep) (ARIS), [K-Dense scientific-agent-skills](https://github.com/k-dense-ai/scientific-agent-skills) (KD) và [humanizer](https://github.com/blader/humanizer) (HZ). Agent-Army **không cài** các repo này; bạn cài repo nào thì agent dùng skill của repo đó.

| Agent | Skill đề xuất |
|---|---|
| commander | brainstorming, writing-plans, executing-plans, dispatching-parallel-agents, subagent-driven-development, verification-before-completion (SP) · research-pipeline, idea-discovery, research-refine-pipeline (ARIS) · get-available-resources (KD) |
| scout | research-lit, arxiv, semantic-scholar, openalex, alphaxiv, research-wiki (ARIS) · literature-review, citation-management, research-lookup, paper-lookup (KD) |
| strategist | idea-creator, novelty-check, research-refine, experiment-plan, ablation-planner (ARIS) · hypothesis-generation, experimental-design, scientific-brainstorming, statistical-power (KD) · brainstorming (SP) |
| engineer | test-driven-development, systematic-debugging, requesting-code-review, receiving-code-review, using-git-worktrees, verification-before-completion (SP) · research-implement-feature, experiment-bridge, web-debug-search (ARIS) · optimize-for-gpu (KD) |
| experimenter | run-experiment, experiment-queue, monitor-experiment, training-check, analyze-results, result-to-claim (ARIS) · exploratory-data-analysis, statistical-analysis, scientific-visualization, matplotlib (KD) |
| writer | paper-writing, paper-plan, paper-figure, paper-compile, rebuttal, grant-proposal (ARIS) · scientific-writing, venue-templates, citation-management, scientific-schematics (KD) |
| editor | humanizer (HZ) · paper-claim-audit, citation-audit, citation-crosscheck, auto-paper-improvement-loop, writing-systems-papers (ARIS) · scientific-writing, venue-templates, scientific-critical-thinking (KD) · verification-before-completion (SP) |
| reviewer | research-review, kill-argument, auto-review-loop, novelty-check, experiment-audit, proof-checker (ARIS) · peer-review, scientific-critical-thinking, scholar-evaluation (KD) · receiving-code-review (SP) |
| auditor | experiment-audit, result-to-claim, citation-audit, citation-crosscheck, paper-claim-audit, integrity-forensics, proof-checker (ARIS) · statistical-analysis, uncertainty-and-units (KD) · verification-before-completion (SP) |

---

## Cài đặt

### Yêu cầu

- Python ≥ 3.11 (`python3 --version`).
- git.
- Claude Code và/hoặc Codex CLI. Codex cần bản có hook, ví dụ 0.169 trở lên.
- Linux hoặc macOS.

### Các bước

```bash
git clone https://github.com/giaminhgist/Agent-Army.git ~/Agent-Army
cd ~/Agent-Army

python3 install.py --dry-run   # xem trước những gì sẽ thay đổi, không ghi gì
python3 install.py             # tự nhận claude và/hoặc codex có trên máy
# hoặc chỉ định:  python3 install.py --claude   |   python3 install.py --codex

army doctor                    # kiểm tra cài đặt và liệt kê skill đề xuất còn thiếu
```

Sau khi cài:

1. **Khởi động lại** Claude Code và Codex để chúng nạp agent và hook mới.
2. **Codex:** chạy `/hooks` một lần trong Codex để cho phép (trust) các hook của Agent-Army. Codex bắt buộc bước này.
3. Nếu shell báo không tìm thấy lệnh `army`, thêm `~/.local/bin` vào `PATH`.
4. (Tùy chọn) Cài các repo skill bạn muốn, theo README của từng repo. Chạy lại `army doctor` để xem còn thiếu skill nào.

### Bộ cài ghi vào đâu

Mọi file được ghi lại trong `~/.agent-army/install-manifest.json`.

| Gì | Ở đâu |
|---|---|
| App, launcher, kho global, cấu hình | `~/.agent-army/` (`app/`, `bin/army`, `knowledge/`, `memory/`, `army.toml`) |
| Lệnh `army` | `~/.local/bin/army` (symlink) |
| Claude Code | `~/.claude/agents/army-*.md`, `~/.claude/skills/army/`; hook trong `~/.claude/settings.json` (có backup `.army-bak`); một khối hướng dẫn trong `~/.claude/CLAUDE.md` |
| Codex | `~/.codex/agents/army_*.toml`, `~/.agents/skills/army/`; hook trong `~/.codex/hooks.json`; một khối hướng dẫn trong `~/.codex/AGENTS.md` |

Bộ cài chỉ thêm và gỡ phần của Agent-Army. Các cài đặt, hook và nội dung khác của bạn được giữ nguyên.

### Cập nhật

```bash
cd ~/Agent-Army && git pull && python3 install.py
```

File `~/.agent-army/army.toml` bạn đã sửa sẽ không bị ghi đè.

### Gỡ cài đặt

```bash
python3 install.py --uninstall           # giữ lại kiến thức và memory global
python3 install.py --uninstall --purge   # xóa hết, kể cả ~/.agent-army
```

---

## Cách dùng

### Bắt đầu một project

```bash
cd ~/my-project
army init --raw data/raw --sensitive data/phi   # raw: chỉ đọc; sensitive: không gửi ra ngoài
```

Lệnh này tạo `.agent-army/` gồm `project.toml`, `plan.md`, `knowledge/`, `memory/` và `runs/`.

### Trong chat

| | Claude Code | Codex |
|---|---|---|
| Giao mục tiêu cho commander | `/army <mục tiêu> [--loop research\|coding\|full]` | `$army <mục tiêu>` |
| Gọi trực tiếp một agent | "dùng army-scout để …" | "have army_scout …" |

Ví dụ:

- `/army khảo sát biomarker eye-tracking cho phát hiện sớm Alzheimer 2019–2026, bảng so sánh và research gap --loop research`
- `/army CPU pilot: logistic regression vs GRU trên gaze features, subject-level 5-fold CV --loop coding`
- `$army viết Methods và Results cho MICCAI từ các run đã qua auditor`

**Vòng lặp:**

| Loop | Thứ tự |
|---|---|
| research | scout → strategist → reviewer |
| coding | engineer → experimenter → auditor |
| full | research rồi coding |

Vòng lặp dừng khi reviewer cho PASS hoặc auditor cho accept, và tối đa 3 vòng.

### Kiến thức và memory (Claude và Codex dùng chung)

```
~/.agent-army/{knowledge,memory}/            GLOBAL
<project>/.agent-army/{knowledge,memory}/    PROJECT
```

| Lệnh | Tác dụng |
|---|---|
| `army kb add --type paper\|note --title "…" [--tags a,b] [--source URL] [--global]` | Thêm paper hoặc note. Nội dung lấy từ stdin hoặc `--body-file`. |
| `army kb search "câu hỏi" [--scope project\|global\|all]` | Tìm toàn văn (SQLite FTS5). Kết quả project đứng trước global. Gõ tiếng Việt không dấu vẫn tìm được. |
| `army mem add "…" --kind decision\|progress\|lesson\|preference [--global]` | Ghi memory. |
| `army mem list` / `army mem brief` | Liệt kê memory / in bản tóm tắt đầu phiên. |
| `army promote --list` | Xem các mục đang chờ đưa lên global. |
| `army promote --pick` | Chọn tương tác những mục đưa lên global. |
| `army promote <id…>` / `army promote --reject <id…>` | Đưa lên global / đánh dấu chỉ dùng trong project. |

Paper, note, lesson và preference mới tạo trong project ở trạng thái *pending*. **Không mục nào tự lên global**: commander sẽ hỏi bạn ở cuối phiên.

### Các lệnh khác

| Lệnh | Tác dụng |
|---|---|
| `army run [--seed N] [--out PATH] -- <lệnh>` | Chạy lệnh và ghi log: run_id, git sha, có thay đổi chưa commit không, seed, exit code, file log |
| `army status` | Xem kế hoạch, các run gần nhất, số mục chờ promote |
| `army doctor` | Kiểm tra cài đặt và skill đề xuất còn thiếu |
| `army build` | Tạo lại agent sau khi sửa `~/.agent-army/army.toml` |

---

## Harness

| | Làm gì |
|---|---|
| H1 `army init` | Tạo kho project, khai báo thư mục raw (chỉ đọc) và sensitive |
| H2 Tóm tắt đầu phiên | Hook tự đưa vào phiên: task đang mở, quyết định gần đây, tiến độ, lesson global |
| H3 Nhắc promote | Hook cuối lượt, chỉ nhắc khi số mục chờ tăng lên |
| H4 Guard raw data | Chặn ghi, xóa, di chuyển vào thư mục raw, kể cả các lệnh như `cd … && rm`, `sudo rm`, `find -delete` |
| H5 `army run` | Log mỗi lần chạy thí nghiệm |
| H6 Kế hoạch và bàn giao | File `.agent-army/plan.md`, và mỗi agent kết thúc bằng một khối Handoff cố định |
| H7 Cổng kiểm chứng | Auditor kết luận `accept / repair / reject`, tối đa 3 vòng |
| H8 Kiểm tra chéo model | Tắt mặc định. Bật bằng `cross_model_check = true` để reviewer và auditor hỏi thêm model của nền tảng kia |
| H9 Snapshot trước khi nén context | Lưu trạng thái trước khi context bị nén, rồi đưa lại vào phiên sau đó |
| H10 `army status` | Xem trạng thái project |
| H11 `army doctor` | Kiểm tra sức khỏe cài đặt |

Mọi hook **không bao giờ chặn bạn khi chính nó gặp lỗi**. Lỗi được ghi vào `~/.agent-army/hook-errors.log`.

---

## Tùy chỉnh

Sửa `~/.agent-army/army.toml`:

- Đổi tier của từng agent.
- Đổi danh sách skill đề xuất.
- Đặt model cụ thể cho Codex (`[tiers.codex.heavy] model = "…"`).
- Bật `cross_model_check`.

Sau đó chạy `army build` và khởi động lại Claude Code hoặc Codex.

## Phát triển

Cấu trúc thư mục:

- `army.toml`: nguồn duy nhất định nghĩa agent.
- `prompts/`: prompt của từng agent và luật chung.
- `src/army/`: CLI, kho kiến thức, hook, bộ render và bộ cài.
- `docs/PLAN.md`: thiết kế.
