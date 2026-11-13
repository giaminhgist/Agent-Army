# Agent-Army

Research-Agent nâng cấp cho Claude Code và Codex, tại **<CHECKOUT>/Agent-Army**.

Bản 0.5.0 có core, 11 agent definitions, ba model tiers, skills discovery, shared knowledge/memory, supervised jobs và installer/migration có preview/rollback. Auto vẫn disabled. Kiểm tra Codex thực tế: standalone research role chạy được; native custom-agent selection chưa đạt trên CLI 0.167.0-alpha.4.1. Chưa cài user-level hoặc nghiệm thu Claude.

**Bắt đầu trên máy mới:** [Clone và cài đặt](CAI_DAT.md). **Kết quả kiểm tra:** [Codex smoke tests](docs/CODEX-CHECK.vi.md).

- [Proposal](PROPOSAL.vi.md)
- [Thiết kế](docs/DESIGN.vi.md) và [hợp đồng dữ liệu](docs/CONTRACTS.vi.md)
- [Báo cáo bước 2](docs/STEP-2-REPORT.vi.md)
- [Skills: cách dùng và giới hạn](docs/SKILLS.vi.md)
- [Báo cáo bước 3](docs/STEP-3-REPORT.vi.md)
- [Shared knowledge/memory: cách dùng](docs/KNOWLEDGE.vi.md)
- [Báo cáo bước 4](docs/STEP-4-REPORT.vi.md)
- [Kế hoạch](docs/IMPLEMENTATION.vi.md)

Năm repo chỉ là gợi ý. Tất cả agent có thể dùng skills phù hợp từ nguồn khác đã cài/cho phép; thiếu skills gợi ý không chặn công việc khi tools/năng lực hiện có đủ.

## Chạy từ source

Python >=3.11. Core không có dependencies ngoài; discovery cần optional extra PyYAML. Dev environment tại đây dùng .dev-deps, không cài global.

~~~powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src') + [IO.Path]::PathSeparator + (Join-Path (Get-Location) '.dev-deps')
python -m agent_army --isolated agents validate --json
python -m agent_army --isolated models resolve --agent research --host codex
python -m agent_army --isolated route "tổng quan tài liệu"
python -m agent_army --isolated agents build --host both --output build
python -m agent_army skills list --host codex
python -m agent_army --isolated skills resolve --host codex --root C:\my-skills --agent research --task "literature review"
python -m agent_army skills doctor --host claude
python -m unittest discover -s tests -v
~~~

Thay python bằng executable thật nếu PATH chỉ có Windows Store alias. Army console entrypoint đã khai báo nhưng chưa cài global. --json có thể đứng cuối; global options khác đặt trước subcommand. --isolated bỏ default config/skill roots; --root và --config explicit vẫn được dùng.

## Nguồn chuẩn

src/agent_army/resources/registry/: agents.toml, models.toml, recommendations.toml.
src/agent_army/resources/prompts/: protocol chung và 11 prompts chuyên môn.

Có thể thêm role không sửa Python. Recommendations có thể rỗng; generated files không có mandatory skill preload. Config: bundled → global → project → explicit overrides. Model resolve không gọi inference hoặc silent fallback.

Build tạo 22 native Claude Markdown/Codex TOML, kèm manifest/hash. Chỉ ghi staging; từ chối native/state directories và file sửa tay. Dùng output riêng khi đổi tier. Build không concurrent-safe/transaction toàn thư mục, không tự xóa stale files.

## Trạng thái

| Chức năng | Trạng thái |
|---|---|
| Agent definitions, model tiers, routing | Có |
| Native renderers | Có; chưa host nghiệm thu |
| Skills discovery/resolver | Có; read-only metadata/planning |
| Shared global/project memory/knowledge | Có store/retrieval và promotion qua console supervised |
| Approvals, jobs, budgets | Có supervised runner + console consent; xem docs/JOBS.vi.md |
| Auto mode | Disabled: thiếu trusted host adapter và worker isolation |
| Installer/migration | Có preview/apply/rollback; đã test fake homes, chưa cài thật |
| Native host integration tests | Bước 7 |

Policies trong prompts là chỉ dẫn, chưa enforcement runtime. Resolution không phải authorization hay xác nhận skill chạy được. Research-Agent cũ giữ nguyên.

## Cài đặt và chuyển dữ liệu

Xem [INSTALL.vi.md](docs/INSTALL.vi.md): cài native definitions cho một hoặc cả hai host, runtime chung, ownership/backup/rollback và migration import-copy. Không cài repo skills, không sửa host configs/PATH, không khởi tạo hoặc xóa KB/memory ngầm. CLI `install plan` và `migration plan` chỉ tạo proposal; apply yêu cầu duyệt riêng.
