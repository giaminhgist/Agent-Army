# Kết quả bước 2

Ngày: 2026-11-13. Trạng thái: hoàn tất phạm vi core tĩnh và renderers; chờ user duyệt bước 3.

## Đã triển khai

- Python package `agent_army` 0.1.0, CLI có console entrypoint `army` và `python -m agent_army`.
- Registry mở, 11 agent specs, protocol chung, 11 prompts chuyên môn, 66 recommendations (6/agent), ba tier cho hai host.
- Config layering global → project → explicit config; agent-specific overrides trong mỗi lớp; task model override chỉ là preview. Unknown keys được báo lỗi.
- Model resolver ghi nguồn cấu hình và availability unknown; không silent fallback, không xác nhận quyền chạy.
- Routing dựa vào keywords/capability, chuẩn hóa dấu tiếng Việt, explicit agent ưu tiên; tín hiệu review chuyển reviewer, mơ hồ chuyển orchestrator. Có validator dependency graph, chưa có task runtime.
- Claude renderer xuất Markdown với YAML quoted scalars; Codex renderer xuất TOML. Không preload skills bắt buộc, không thêm fields quyền không được hỗ trợ.
- Build manifest/hash, kiểm tra output conflict, atomic write từng file; staging-only, không cài vào host.
- Doctor kiểm tra registry/models, executable presence, FTS5; không gọi LLM hoặc network.

Nguồn chuẩn `src/agent_army/resources/` chứa registry và prompts. Đây là điều chỉnh vị trí vật lý so với cây thiết kế để package tự chứa resources; không tạo hai bản nguồn cần đồng bộ.

## Chứng cứ kiểm thử

Môi trường: Windows, Python 3.12.14 từ runtime đã có trên máy. Không cài Python hay dependencies ngoài. Lần chạy tests trong sandbox gặp Access denied ở Windows Temp; chạy lại ngoài sandbox theo approval đã thành công.

`python -m unittest discover -s tests -v`: **21 tests, OK**.

Bao phủ: defaults; ba tiers; model precedence và effort reset khi đổi model; custom agent thứ 12; không có recommendation catalog; config errors; missing/traversal prompt; unknown fields; deterministic build; file edited/unowned; corrupt manifest; source refresh; parser/escaping; English/Vietnamese routing; graph cycles; project/path boundaries; JSON CLI và isolated config.

Native syntax: Codex parse bằng tomllib; Claude kiểm tra subset YAML mà renderer phát ra (string keys + JSON-quoted string scalars). Chưa chạy Claude native validator hoặc host integration; không coi parser tests là nghiệm thu runtime.

Build source đã sinh **22 definitions** trong `build/claude/agents/` và `build/codex/agents/`, kèm manifest.

Build wheel offline thành công: `dist/agent_army-0.1.0-py3-none-any.whl`, chứa **15 resource files** (3 registry + 12 prompts). Smoke test giải nén wheel vào `build/wheel-smoke`, import từ bản đó thay vì source; nạp đủ 11 agents và sinh lại 22 definitions thành công. Chưa cài wheel vào môi trường global.

## Giới hạn còn lại

- Chưa skills discovery/resolver (bước 3), shared KB/memory/RAG (bước 4), jobs/approvals/enforcement (bước 5), installer/migration (bước 6), native-host nghiệm thu (bước 7).
- Ghi đồng thời Claude/Codex chưa được triển khai. Static build không hỗ trợ concurrent writers; manifest không phải cơ chế bảo mật.
- Build không transaction toàn thư mục, không tự dọn stale files khi bỏ agent; clean export dùng output mới.
- Không xác nhận account có quyền dùng các model mặc định; không gọi inference để dò model.
- Chưa chạy tests macOS/Linux hoặc xác minh agent definitions được host thật nạp/dispatch.
- CLI config bước này mới nhận model/agent override và extensions; schema project đầy đủ sẽ mở rộng ở bước lưu trữ.

## Bước tiếp theo đề nghị duyệt

**Bước 3: skills discovery và resolver mở**. Quét metadata từ roots được phép của Claude/Codex/project/custom, xử lý trùng tên/dependencies/compatibility, xếp hạng tất cả nguồn và trả tools fallback khi không có skill. Năm repo vẫn chỉ là recommendations. Kiểm thử bằng fixtures, không cài repo skills hay sửa cấu hình host thật.

Tài liệu host đã đối chiếu trong bước này: [Claude Code subagents](https://code.claude.com/docs/en/sub-agents), [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents). Native compatibility vẫn cần nghiệm thu thực tế ở bước 7.
