# Bước 6 — installer và migration

Ngày 2026-11-13. Version 0.5.0. Đã thực hiện theo phê duyệt bước 6; phạm vi chỉ development và tests với fake homes/legacy fixtures.

## Kết quả

- Installer offline render 11 agents/host, cài một hoặc cả hai host ở scope user/project, runtime và launcher chung. Cùng launcher đảm bảo cùng AGENT_ARMY_HOME.
- Không cài năm skills repos, không chạy pip/network hoặc sửa host config, PATH, AGENTS.md/CLAUDE.md. Optional PyYAML vẫn do user chọn cài.
- Read-only planning, file proposal riêng, supervised consent đúng hash/action/target; apply render lại và chặn stale plan.
- Ownership manifest, SHA-256, conservative conflicts, update/reinstall/uninstall. Core/memory giữ mặc định; chỉ gỡ runtime khi được yêu cầu và không host scope nào còn dùng.
- File transaction journal chứa before/after bytes; atomic mỗi file, OS cooperative lock, rollback lỗi thường và explicit rollback sau crash. Không ghi đè file user sửa.
- Migration đọc định dạng legacy thực tế: KB, wiki, memory text vào store; BibTeX/PDF/JSON/tasks/runs/reviews/artifacts archive exact bytes. Grants, sessions, loop/settings, promotion queue và index không import.
- Snapshot giữ cấu trúc relative paths, source hash, mapping source→snapshot→item ID, counts, BibTeX keys và báo links ngoài selection. Không tự resume job cũ hoặc biến archived state thành instructions.
- Import một SQLite transaction; retry cùng request không nhân bản. Rollback revoke item không đổi và không có reference khác, giữ nguồn, snapshot và preexisting data.
- Sửa lỗi store đọc blob CRLF bị Python chuẩn hóa newline, làm sai hash khi retry/rollback; hiện đọc UTF-8 bytes nguyên trạng.

## Ranh giới nghiệm thu

Không cài vào Claude/Codex thực tế; không initialize/migrate knowledge thật; không dispatch inference. Cài file đúng vị trí/format chưa phải native E2E. Python explicit khác interpreter hiện tại cần user kiểm tra >=3.11. Bản cài offline không tạo venv/PATH wrapper hoặc cài dependencies.

Console supervised không phải trusted host identity. Auto mode vẫn disabled. Transaction nhiều files có thể được host quan sát giữa chừng; journal/rollback không phải atomic filesystem toàn cây. Khóa không ngăn process tùy ý cùng OS user. Migration hỗ trợ UTF-8 text; các file khác được archive chứ không giả vờ index. Blob/snapshot mồ côi sau crash giữ lại, không tự xóa dữ liệu.

Nguồn format native: [OpenAI Docs](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Claude Code Docs](https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope). Chi tiết CLI và recovery: INSTALL.vi.md.

## Bước tiếp theo

Bước 7 cần user duyệt: kiểm tra executable/account, tạo preview cài thật cho từng host, trình user duyệt plan cụ thể trước apply, rồi chạy fixture native để kiểm chứng agent load/model/skills/shared memory. Host không sẵn sàng phải ghi NOT TESTED. Migration dữ liệu thật vẫn cần lựa chọn nguồn/đích và preview riêng.

## Kết quả nghiệm thu

- 129 tests: 128 pass, 1 skip (Windows symlink permission); không failures/errors.
- Rebuild 22 native definitions, wheel agent_army-0.5.0-py3-none-any.whl.
- Wheel smoke độc lập source/PyYAML: offline install vào fake homes, launcher cài riêng validate đủ 11 roles, tạo 22 native files và không tạo store ngầm.
- Chi tiết: STEP-6-VALIDATION.json.
