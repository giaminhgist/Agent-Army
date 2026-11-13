# Kiểm tra Codex thực tế — 2026-11-13

Codex CLI 0.167.0-alpha.4.1, đăng nhập ChatGPT. Tests dùng project fixture `build/codex-native-fixture`, không cài user-level. Không sửa global config hoặc quyền sandbox.

| Kiểm tra | Kết quả |
|---|---|
| Kết nối Codex, yêu cầu gpt-6.1-sol | PASS, trả marker |
| Parse/build 11 native definitions | Đã qua static checks; không đồng nghĩa load được |
| Gọi custom army-research qua native spawn | LOAD_FAILED, interface không có selector; không spawn agent thay thế |
| Thử multi_agent_v2=true riêng invocation | LOAD_FAILED tương tự; không lưu cờ global |
| Standalone CLI với cấu hình research từ TOML | PASS, role và chính sách skills đúng |
| User-level native agents | NOT TESTED, chưa cài |
| Shared memory qua hai native hosts | NOT TESTED |
| Claude | Hoãn theo yêu cầu ưu tiên Codex |

Standalone test đọc model/effort/developer_instructions từ file research đã sinh và truyền qua tham số CLI, yêu cầu không tools/đọc file/network. Requested model là gpt-6-luna, effort high. Kết quả trả đúng vai trò Literature and evidence specialist, xác nhận suggested skills là tùy chọn và thiếu gợi ý không chặn skills/tools khác, kết thúc bằng ARMY_ROLE_SMOKE_OK. Log không có actual model telemetry riêng nên không dùng self-report để khẳng định model actual.

Native test không yêu cầu generic agent giả vai research. Lượt đầu yêu cầu agent_type; lượt thứ hai dùng tên custom agent mà không ép tên parameter, vẫn không tìm được selector. Đây là bằng chứng integration chưa đạt trong môi trường CLI đã thử, không phải kết luận mọi bản Codex đều không hỗ trợ custom agents. Tài liệu [OpenAI custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents) mô tả standalone TOML trong .codex/agents; file layout ở fixture theo tài liệu, nhưng runtime hiện tại chưa xác nhận được việc chọn role.

Log local: CODEX-NATIVE.stdout.jsonl, CODEX-NATIVE-V2.stdout.jsonl, CODEX-ROLE.stdout.jsonl và stderr tương ứng. Các log/preview machine-specific đã được thêm vào .gitignore để không mặc định đưa vào repo khi publish. Bản hiện tại chưa có fallback runtime cho native selector thiếu; không quảng cáo là multi-agent E2E đã pass.

Hướng dẫn portable: [CAI_DAT.md](../CAI_DAT.md). Hướng dẫn dùng venv ổn định ngoài checkout, cài package từ source, tạo preview trên máy đích rồi người dùng xác nhận apply. Không tái dùng preview/Python path của máy phát triển. Repository phân phối: https://github.com/giaminhgist/Agent-Army; hướng dẫn đã dùng URL clone thật. Kết quả kiểm thử native ở trên không thay đổi khi publish.
