# Agent-Army: clone và cài trên máy mới

Hướng dẫn cho phiên bản 0.5.0. Bắt đầu với Codex; có thể cài thêm Claude Code sau. Không cần sao chép đường dẫn Python, file preview hay file `.cmd` của máy phát triển.

**Giới hạn đã biết:** ngày 2026-11-13, Codex CLI `0.167.0-alpha.4.1` chạy được cấu hình role research qua CLI trực tiếp, nhưng bài kiểm tra gọi custom subagent `army-research` trong project fixture trả `LOAD_FAILED`: giao diện spawn không có bộ chọn custom agent. Bật `multi_agent_v2` riêng cho lượt test cũng chưa giải quyết được. Chưa nghiệm thu custom subagents user-level hoặc Claude. Cài definitions đúng format chưa đảm bảo mọi phiên bản host nạp được chúng. Xem [báo cáo Codex](docs/CODEX-CHECK.vi.md).

## 1. Chuẩn bị

- Git để clone repo.
- Python **3.11 trở lên** có `venv` và `pip`. Dùng Python độc lập, không dùng Microsoft Store alias hoặc interpreter versioned đi kèm app Codex.
- Codex CLI/app đã đăng nhập; Claude Code là tùy chọn. Với Claude Windows, dùng phần **Code**, không coi chat thông thường là nghiệm thu agent local.
- Tài khoản host có quyền dùng model bạn cấu hình. Cài Agent-Army không cấp quyền model.

Repository: [giaminhgist/Agent-Army](https://github.com/giaminhgist/Agent-Army). Các lệnh clone bên dưới dùng repository này, không phải Research-Agent cũ.

Không đưa `.agent-army` chứa dữ liệu cá nhân, credentials, virtualenv, build, dist hoặc preview/log riêng của máy vào Git. Clone source **không đồng bộ memory giữa các máy**. Claude và Codex trên cùng máy sẽ dùng chung Army home; chuyển dữ liệu giữa máy là bước riêng có kiểm tra backup/migration.

## 2. Clone và cài package — Windows PowerShell

Mở PowerShell và chạy từng nhóm lệnh. Nếu `py` không có nhưng `python` là Python thật, thay `py -3` bằng `python`.

```powershell
git clone https://github.com/giaminhgist/Agent-Army.git Agent-Army
Set-Location Agent-Army
py -3 --version

# Venv nằm ngoài repo: xóa/di chuyển checkout không làm mất interpreter đã cài.
$armyVenv = Join-Path $env:USERPROFILE '.agent-army-venv'
py -3 -m venv $armyVenv
$armyPython = Join-Path $armyVenv 'Scripts\python.exe'
& $armyPython -m pip install '.[skills]'
& $armyPython -m agent_army --version
& $armyPython -m agent_army agents validate
& $armyPython -m agent_army doctor
```

`.[skills]` cài package này và PyYAML cho discovery, **không cài skills từ năm repo gợi ý**. Nếu chỉ cần core/KB/jobs, dùng `pip install .`; khi đó discovery YAML chưa sẵn sàng. Pip có thể cần mạng để tải build dependencies/PyYAML; bộ cài native definitions phía dưới hoạt động offline. Không cần activate venv hoặc đổi execution policy.

Chạy từ thư mục repo để lấy đúng source mới. Nếu có `PYTHONPATH` tùy chỉnh, kiểm tra nó không trỏ vào bản Agent-Army cũ. Kiểm tra package thật được import:

```powershell
& $armyPython -c 'import agent_army; print(agent_army.__file__)'
```

## 3. Tạo preview rồi cài Codex

```powershell
codex --version
codex login status

$armyHome = Join-Path $env:USERPROFILE '.agent-army'
$plan = Join-Path (Get-Location) 'install-codex.local.json'
& $armyPython -m agent_army install plan --host codex --scope user --home $armyHome --python $armyPython --output $plan
```

Mở `$plan` bằng editor, xem `conflicts`, `changes`, nội dung và đường dẫn. Preview chỉ được ghi vào **file mới**; nếu tên đã tồn tại, dùng tên khác. Không áp dụng preview lấy từ máy khác.

Khi đồng ý, tự chạy trong terminal tương tác:

```powershell
& $armyPython -m agent_army install apply --scope user --home $armyHome --python $armyPython --plan $plan --console
```

CLI hiện lại preview và yêu cầu nhập challenge. Người dùng nhập trực tiếp; không pipe câu trả lời, không dùng `--yes`, không nhờ agent giả lập consent. Nếu source, model config hoặc file đích thay đổi, tạo preview mới. Giữ nguyên các tham số home/interpreter/config giữa plan và apply.

Kết quả:

- Codex: `~/.codex/agents/army-*.toml` — 11 definitions; nếu có `CODEX_HOME` thì dùng thư mục đó.
- Runtime chung: `~/.agent-army/runtime/agent_army`.
- Launcher chung: `~/.agent-army/bin/army.py`.
- Ownership/backup: `~/.agent-army/installer/`.

Bộ cài không sửa Codex config, PATH hay AGENTS.md. Các agent có cùng launcher trong instructions; launcher đặt `AGENT_ARMY_HOME` cho process của nó. Không tự tạo store và không cài skills.

## 4. Kiểm tra Codex sau cài

```powershell
$armyLauncher = Join-Path $armyHome 'bin\army.py'
& $armyPython $armyLauncher agents validate
& $armyPython $armyLauncher models resolve --agent research --host codex
& $armyPython $armyLauncher skills doctor --host codex
```

Mở session Codex mới trong project thử nghiệm, yêu cầu:

> Dùng đúng custom agent army-research để trả lời vai trò của nó và xác nhận skills gợi ý có bắt buộc không. Không đọc dữ liệu cá nhân, không sửa file, không tìm web. Nếu không chọn được custom agent, báo LOAD_FAILED; không dùng agent thường để thay thế rồi báo pass.

**Đạt native smoke** khi log/thông tin host cho thấy đúng custom agent được gọi và có kết quả. Model tự nói tên mình hoặc file TOML parse được chưa đủ để chứng minh model thực tế. Nếu host không cung cấp telemetry, ghi “model requested”, không khẳng định “model actual”.

Nếu gặp lỗi selector như bản CLI đã thử: ghi native integration chưa đạt, kiểm tra tài liệu và bản host phù hợp; không bật quyền rộng hơn, không chỉnh approval/sandbox để chữa lỗi này. Việc chạy role bằng model + developer instructions qua CLI trực tiếp là bài kiểm tra khác, không thay thế native subagent smoke. Hiện chưa có runner tự động fallback cho trường hợp này.

## 5. Dùng knowledge và memory chung

Sau khi bạn chọn khởi tạo store:

```powershell
& $armyPython $armyLauncher store init --scope global

# Thay bằng project thật đã tồn tại.
$projectRoot = 'D:\work\my-project'
& $armyPython $armyLauncher --project $projectRoot store init --scope project
& $armyPython $armyLauncher --project $projectRoot kb search 'research question'
& $armyPython $armyLauncher --project $projectRoot memory search 'decision'
```

Global store nằm trong `$armyHome`; project store nằm tại `PROJECT/.agent-army`. Claude và Codex phải dùng **cùng launcher, cùng home và cùng project root** để thấy cùng dữ liệu. Native chat history không tự biến thành shared memory.

Nội dung project chỉ đi global qua `promotion prepare` → xem preview → người dùng duyệt `publish --console`. Không tự đồng bộ toàn bộ memory. Store project có identity gắn với đường dẫn; không di chuyển `.agent-army` sang máy/đường dẫn khác rồi giả định dùng được ngay. Xem [knowledge](docs/KNOWLEDGE.vi.md) và [migration](docs/INSTALL.vi.md).

## 6. Cài thêm Claude Code hoặc cả hai host

Giữ nguyên `$armyHome` và `$armyPython`, tạo plan mới:

```powershell
$planBoth = Join-Path (Get-Location) 'install-both.local.json'
& $armyPython -m agent_army install plan --host both --scope user --home $armyHome --python $armyPython --output $planBoth
& $armyPython -m agent_army install apply --scope user --home $armyHome --python $armyPython --plan $planBoth --console
```

Claude definitions ở `~/.claude/agents/army-*.md`, hoặc `CLAUDE_CONFIG_DIR/agents` nếu cấu hình biến đó. Mở session mới trong phần Code và kiểm tra agent tương tự Codex. Không cần cài lại runtime riêng cho Claude. Chưa nghiệm thu native Claude trên bản này.

Để cài riêng project thay vì user: thêm `--project PATH` **trước** `install`, dùng `--scope project` cho cả plan và apply. Native files sẽ vào `.codex/agents` và/hoặc `.claude/agents` của project; runtime vẫn dùng Army home chung.

## 7. Model và skills tùy chỉnh

Defaults trong source có ba tier light/medium/heavy. Không giả định model name luôn được mọi account hoặc host hỗ trợ. Dùng `models resolve` để xem cấu hình; lệnh này không gọi inference.

Nếu cần override, tạo file TOML, ví dụ `my-models.local.toml`:

```toml
schema_version = 1

[models.codex.light]
model = "MODEL_YOU_CAN_USE"
effort = "high"
```

Thay placeholder bằng model/effort host hỗ trợ. Thêm `--config my-models.local.toml` **trước** `install` ở cả plan và apply, rồi tạo preview mới. Không sửa tay native files nếu vẫn muốn installer quản lý chúng; hash thay đổi sẽ gây conflict bảo vệ chỉnh sửa của bạn.

Cài skills bạn muốn bằng công cụ riêng của host. Sáu gợi ý/role không phải dependencies hoặc whitelist. Skills từ nguồn khác vẫn được discovery; thiếu gợi ý có thể dùng skills/tools phù hợp khác. Kiểm tra `skills doctor` và `skills resolve`; unknown requirements không phải đã xác minh skill chạy được.

## 8. Update, gỡ cài và rollback

Từ checkout:

```powershell
git pull --ff-only
& $armyPython -m pip install --upgrade '.[skills]'
# Sau đó tạo install plan tên mới, xem thay đổi và apply như bước 3/6.
```

Không di chuyển/xóa venv đã dùng trong native instructions. Khi cần đổi interpreter, tạo plan mới với `--python` mới. Reinstall không thay đổi là no-op. File unowned hoặc sửa tay sẽ chặn giao dịch; không có --force ghi đè.

```powershell
$removePlan = Join-Path (Get-Location) 'uninstall-codex.local.json'
& $armyPython -m agent_army install plan --action uninstall --host codex --home $armyHome --python $armyPython --output $removePlan
& $armyPython -m agent_army install apply --home $armyHome --python $armyPython --plan $removePlan --console
```

Uninstall mặc định giữ runtime và KB/memory. `--remove-runtime` chỉ đặt trên uninstall plan khi không còn host nào phụ thuộc. Lỗi giữa chừng có journal; rollback cũng có preview và consent riêng. Chi tiết và lệnh migration/rollback: [INSTALL.vi.md](docs/INSTALL.vi.md). Không xóa thư mục host để “cài sạch”.

## 9. macOS/Linux — lệnh tương ứng, chưa nghiệm thu OS thật

```bash
git clone https://github.com/giaminhgist/Agent-Army.git Agent-Army
cd Agent-Army
python3 --version
python3 -m venv --copies "$HOME/.agent-army-venv"
army_python="$HOME/.agent-army-venv/bin/python"
army_home="$HOME/.agent-army"
"$army_python" -m pip install '.[skills]'
"$army_python" -m agent_army agents validate
"$army_python" -m agent_army install plan --host codex --scope user --home "$army_home" --python "$army_python" --output install-codex.local.json
"$army_python" -m agent_army install apply --scope user --home "$army_home" --python "$army_python" --plan install-codex.local.json --console
```

Nếu hệ điều hành chưa có module venv/pip, cài theo công cụ của hệ điều hành trước. Không dùng sudo để chạy bộ cài user-level. Thay `--host codex` bằng `both` nếu cần cả hai. Installer hiện từ chối symlink/junction/reparse-point trong đường dẫn quản lý; dùng native homes và Army home là thư mục local thông thường.

## 10. Những gì chưa tự động

- Source được phân phối qua GitHub; dữ liệu cá nhân không tự publish hoặc đồng bộ theo repo.
- Không tự đăng nhập host, cấp quyền model hoặc cài host applications.
- Không tự migrate dữ liệu, cài năm skills repos hoặc chia sẻ memory qua cloud.
- Auto mode vẫn disabled; console approval không phải OS isolation.
- 129 tests của bản 0.5.0 đã chạy: 128 pass, 1 Windows symlink skip. Tests fake homes không thay thế native host E2E.

Tài liệu host để đối chiếu phiên bản: [OpenAI — Custom subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Claude Code — Subagents](https://code.claude.com/docs/en/sub-agents).
