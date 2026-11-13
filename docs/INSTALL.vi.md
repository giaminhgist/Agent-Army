# Cài đặt và migration — 0.5.0

Bộ cài offline quản lý native definitions và một bản sao runtime Python chung. Không tải repo skills, chạy pip, sửa PATH, sửa host config, nối AGENTS.md/CLAUDE.md, hoặc bật quyền chạy tự động. Chọn Python 3.11+ có thật; Python alias Microsoft Store không dùng được. Runtime chỉ cần stdlib; discovery YAML cần PyYAML tùy chọn trong interpreter do người dùng chọn.

## Nội dung cài

| Phần | Vị trí |
|---|---|
| Claude user agents | CLAUDE_CONFIG_DIR/agents hoặc ~/.claude/agents |
| Codex user agents | CODEX_HOME/agents hoặc ~/.codex/agents |
| Project agents | PROJECT/.claude/agents và PROJECT/.codex/agents |
| Runtime chung | ARMY_HOME/runtime/agent_army |
| Launcher chung | ARMY_HOME/bin/army.py |
| Ownership và backups | ARMY_HOME/installer/manifest.json và transactions/*.json |

Mỗi host có 11 file `army-*`; không cài bất kỳ skill nào. `--home` chọn Army home chung, mặc định AGENT_ARMY_HOME hoặc ~/.agent-army. Launcher đặt AGENT_ARMY_HOME cho process của chính nó và import runtime đi kèm. Cả hai host được ghi cùng argv launcher trong instructions; không dựa vào hai bộ environment riêng vô tình trỏ khác store. Không sửa environment toàn hệ thống.

Python được chọn qua `--python`; mặc định interpreter đang chạy Army. Với interpreter explicit, plan kiểm tra file và hash, chưa chạy nó để xác minh phiên bản. Nên chọn interpreter ổn định, không dùng đường dẫn runtime có version sẽ mất khi desktop app nâng cấp. Khi cần đổi interpreter, tạo install plan mới. Không tạo venv hoặc cài dependencies tự động.

Đường dẫn native được đối chiếu với [OpenAI Docs — custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents) và [Claude Code — subagent scope](https://code.claude.com/docs/en/sub-agents#choose-the-subagent-scope), ngày 2026-11-13. Cài file đúng format chưa chứng minh host đã load hay account dùng được model; đó là nghiệm thu bước 7.

## Plan → xem → apply

Các ví dụ dưới đây dùng `python -m agent_army` từ checkout/venv có package. Nếu dùng source checkout, thêm src vào PYTHONPATH. Sau cài, có thể gọi `python C:\path\army-home\bin\army.py ...`; không có lệnh `army` trên PATH nếu chưa tự cài package bằng công cụ Python của bạn.

```powershell
# Chỉ ghi proposal vào file mới; không tạo native homes/runtime/store.
python -m agent_army install plan --host both --scope user --home C:\path\army-home --python C:\Python312\python.exe --output install-plan.json
# Xem toàn bộ paths, content, hashes, conflicts trong install-plan.json.
# Người dùng trực tiếp chạy terminal; agent không được tự nhập consent:
python -m agent_army install apply --scope user --home C:\path\army-home --python C:\Python312\python.exe --plan install-plan.json --console

# Cài riêng một project, không cần khởi tạo project store trước:
python -m agent_army --project C:\work\project install plan --scope project --host both --home C:\path\army-home --output project-install.json
```

Khi apply phải truyền lại các roots, scope, interpreter và model config layers đã dùng khi plan. `--claude-home`/`--codex-home` chọn custom user homes; với scope project, roots luôn lấy từ --project. Plan được render lại và so sánh cả nội dung, executable hash, ownership manifest và destinations trước/sau consent; đổi nguồn hoặc đích thì phải tạo plan mới. File plan không phải grant. Không có --yes. `--console` là supervised consent, không phải chứng thực danh tính chống PTY/agent cùng OS account; xem JOBS.vi.md.

Không tự khởi tạo KB/memory khi cài definitions. Sau khi được duyệt riêng, người dùng khởi tạo:

```powershell
python C:\path\army-home\bin\army.py store init --scope global
python C:\path\army-home\bin\army.py --project C:\work\project store init --scope project
```

## Update, conflict, uninstall, rollback

Update chạy install plan/apply từ checkout/wheel phiên bản mới. Reinstall giống hệt là no-op. File không thuộc manifest hoặc có hash khác bản đã cài là conflict; cả giao dịch bị chặn, không ghi đè và không có --force. Người dùng cần giữ bản sửa riêng hoặc tự giải quyết trước plan mới. Nếu role đã bị bỏ khỏi registry, file cũ thuộc đúng host scope sẽ được đề xuất gỡ.

```powershell
python -m agent_army install plan --action uninstall --host claude --home C:\path\army-home --output uninstall.json
python -m agent_army install apply --home C:\path\army-home --plan uninstall.json --console
```

Mặc định uninstall chỉ gỡ native definitions được chọn; giữ runtime để còn đọc knowledge/memory. `--remove-runtime` trong uninstall plan chỉ được dùng khi không còn host scope nào phụ thuộc runtime. KB/memory, project state, configs và transaction backups luôn giữ. Không xóa đệ quy thư mục của người dùng.

Mọi giao dịch có ID và journal chứa bytes trước/sau, hash, receipt. Ghi journal trước khi sửa files; ghi từng file atomically. Đây không phải atomic transaction xuyên nhiều thư mục: host có thể thấy trạng thái từng phần trong lúc apply. Nên đóng sessions hoặc chờ cài hoàn tất rồi reload host. Khi có exception thông thường, bộ cài tự khôi phục các file còn khớp hash; concurrent edits gây conflict thay vì bị ghi đè. Lỗi nguồn điện/process kill để lại journal prepared và chặn giao dịch mới đến khi rollback. Khóa OS được giải phóng khi process kết thúc.

```powershell
python -m agent_army install rollback-plan TRANSACTION_ID --home C:\path\army-home --output rollback.json
python -m agent_army install rollback --home C:\path\army-home --plan rollback.json --console
```

Rollback cũng cần duyệt và kiểm tra hash. File đã sửa sau cài không bị ghi đè. Journal giữ lại để audit; không tự dọn backups. Symlink/junction/reparse points bị từ chối trong đường dẫn quản lý. Lock chỉ phối hợp Army processes dùng cùng home; không chống process tùy ý cùng tài khoản hoặc hai installer homes cố quản lý cùng native paths.

## Migration import-copy

Source project là thư mục chứa `.research-agent` và `research-wiki`. Source global là legacy RA_HOME chứa `knowledge`. Đích là Army store đã được khởi tạo, project hoặc global; việc khởi tạo đích là thao tác riêng. Có thể nhập global legacy vào project để xem lại rồi chọn promote, hoặc duyệt riêng để nhập vào global. Mọi file và scope đích hiển thị trong preview.

```powershell
python -m agent_army --project C:\work\new migration plan --source C:\work\old --source-kind project --scope project --home C:\path\army-home --output migration.json
python -m agent_army --project C:\work\new migration apply --source C:\work\old --source-kind project --scope project --home C:\path\army-home --plan migration.json --console
```

`--select` lặp lại để chọn đúng relative files. Mặc định quét các roots dữ liệu được hỗ trợ; tối đa 2.000 files, 4 MiB/file, 64 MiB/lần. Không tự cắt dữ liệu nếu vượt giới hạn; chia thành nhiều lựa chọn. Preview hiển thị counts, hashes, nội dung sẽ index, mode archive/import, citation keys và relative links chưa tìm được trong selection.

| Legacy data | Xử lý |
|---|---|
| KB papers/notes và research-wiki Markdown/text UTF-8 | Knowledge chưa xác minh, giữ body/frontmatter đầy đủ |
| Memory Markdown/text | Memory project/global theo scope đích đã duyệt |
| BibTeX, PDF/binary, memory state.json/log.jsonl | Archive exact bytes; không giả vờ đã parse/index |
| tasks/runs/reviews/artifacts | Archive-only; không tạo job chạy lại |
| Approvals, sessions, loop, settings, installer skills, derived DB/index, promotion queue | Không import |

Scalar title/doi/arxiv/url/slug theo legacy writer được đọc an toàn không chạy YAML tags/scripts. Định dạng phức tạp chưa được parse metadata, nhưng toàn văn vẫn giữ. Raw snapshots tại `STORE/migrations/ID/snapshot/<relative path>` giữ bytes/CRLF và cấu trúc tương đối. Body trong store là Unicode decoded UTF-8; raw bytes có hash riêng. Không sửa link hoặc gộp BibTeX tự động; link nằm ngoài selection sẽ được báo. Original sources không sửa/xóa.

Mỗi source có mapping tới snapshot và item ID sau import. Bản ghi đã tồn tại trùng fingerprint được tái sử dụng. Apply lại cùng migration ID không tạo trùng. Tất cả metadata/items/events của một migration commit trong một SQLite transaction; source và destination thay đổi sau preview bị chặn. Snapshot/blob có thể còn mồ côi sau lỗi/crash; không tự xóa, retry cùng plan kiểm tra bytes rồi tái dùng. Không có grant/autonomy nào được kích hoạt từ dữ liệu archive.

```powershell
python -m agent_army --project C:\work\new migration rollback-plan MIGRATION_ID --source C:\work\old --source-kind project --scope project --home C:\path\army-home --output migration-rollback.json
python -m agent_army --project C:\work\new migration rollback --source C:\work\old --source-kind project --scope project --home C:\path\army-home --plan migration-rollback.json --console
```

Rollback migration revoke nội dung do migration tạo còn nguyên version/hash và không có migration khác đang tham chiếu; giữ dữ liệu có sẵn, raw snapshots và nguồn gốc. Item đã sửa làm rollback bị chặn. Không tự thu hồi các global promotions đã được duyệt riêng; dùng promotion revoke riêng. Lịch sử phiên bản vẫn còn, nên rollback là loại khỏi retrieval hiện tại, không phải xóa mọi dấu vết.

## Chứng cứ và giới hạn

Bước 6 kiểm thử trên Windows bằng temporary fake homes và legacy fixtures. Không cài vào Claude/Codex thật, không đọc/migrate user knowledge thực tế, không gửi inference hoặc gọi dịch vụ có phí. Chưa kiểm chứng macOS/Linux hay native hosts. Installer không thay sandbox/approval config, và auto mode vẫn disabled. Xem STEP-6-REPORT.vi.md và STEP-6-VALIDATION.json.
