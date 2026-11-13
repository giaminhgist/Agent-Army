# Jobs và phê duyệt — supervised, version 0.4.0

Army có runner CPU cho tiến trình đơn do người dùng trực tiếp giám sát. Đây chưa phải auto mode cho Claude/Codex. Cả hai host dùng cùng project state, nhưng chưa có host adapter xác thực người duyệt và cách ly worker. Agent không được dùng `--console`, tự tạo authority, giả lập nhập terminal hoặc gọi API nội bộ để bỏ qua phê duyệt.

## Phê duyệt cụ thể

Mặc định `job run/resume/review` và `promotion publish/revoke` từ chối nếu không có authority. Người dùng có thể tự chạy lệnh với `--console` trong terminal tương tác. CLI in nội dung JSON đã escape ký tự điều khiển, action, ID, hash và challenge ngẫu nhiên; Enter hoặc câu trả lời khác đều từ chối. Không có `--yes`, boolean approved, file grant tự khai người duyệt hay approval kéo dài qua lần chạy khác. Consent chỉ dùng một lần, đúng action/ID/hash và có thời hạn 5 phút. Stop hoặc thay đổi state trong lúc duyệt làm consent cũ mất hiệu lực.

TTY không phải chứng thực danh tính: PTY/UI automation và process cùng tài khoản vẫn có thể can thiệp. Actor audit ghi rõ `local-console:supervised-not-authenticated`. Chỉ dùng adapter này trong workflow người vận hành tự kiểm soát terminal. Không được quảng cáo là worker không thể tự cấp quyền ở mức hệ điều hành. API Python nhận authority phục vụ tích hợp trusted broker trong tương lai; quyền import Python/ghi SQLite không phải security boundary.

## Tạo và chạy job

Khởi tạo project bằng `army --project C:\path\project store init --scope project`. Tạo file JSON, ví dụ:

```json
{
  "title": "CPU reproducibility fixture",
  "argv": ["C:\\path\\python.exe", "experiment.py"],
  "inputs": ["experiment.py", "config.json", "data.csv"],
  "outputs": ["results.json"],
  "seed": 42,
  "device": "cpu",
  "timeout_seconds": 60,
  "wall_budget_seconds": 180,
  "max_attempts": 3,
  "max_failures": 2,
  "estimated_usd": 0
}
```

```powershell
army --project C:\path\project job create --spec job.json
army --project C:\path\project job preview JOB_ID
# Người dùng tự chạy, xem toàn bộ argv/side effects rồi duyệt:
army --project C:\path\project job run JOB_ID --console
army --project C:\path\project job status JOB_ID
# Terminal khác có thể yêu cầu dừng:
army --project C:\path\project job stop JOB_ID
# Một lần duyệt mới; không tự retry:
army --project C:\path\project job resume JOB_ID --console
```

Executable phải là đường dẫn tuyệt đối; dùng argv với `shell=False`, không nhận .bat/.cmd. Đây không ngăn chương trình được duyệt gọi shell/network: người dùng phải xem hành vi chương trình. Khai báo tất cả code/config/data làm inputs, bao gồm file được truyền trong argv. Army hash các file khai báo và executable; không suy ra mọi dependency runtime. Paths phải trong project, ngoài `.agent-army`; output đã tồn tại sẽ bị chặn, người dùng cần chủ động bảo toàn/chuyển chúng trước retry. Không tự xóa dữ liệu để chạy lại.

Seed được truyền qua `ARMY_SEED`, device qua `ARMY_DEVICE`; chương trình phải tự sử dụng chúng. Manifest ghi platform, Python điều phối, seed/device, argv, input/executable/output hashes, exit code, thời gian, log hashes và receipt. Không ghi toàn bộ environment vì có thể chứa secret. Muốn pin môi trường dependency, thêm lockfile/config vào inputs; không thể tuyên bố tái lập hoàn toàn chỉ từ manifest này.

## State, limits và recovery

`pending → running → review_pending → completed`. Lỗi → `failed`; stop/interrupt → `paused`. Resume chỉ từ paused/failed và phải duyệt lại; tối đa 3 attempts, 2 failures, wall budget tích lũy. Reviewer fail tính là failure. Có đúng 1 job running/project trong supervised mode, thấp hơn trần thiết kế 3 workers. Không có scheduler phân tán hoặc tự điều phối vòng lặp LLM.

SQLite transaction giữ claim, revision và events chung cho hai client. Crash sau claim giữ `running`; không suy đoán job đã chết, không tự respawn. Cần người vận hành kiểm tra tiến trình/artifacts trước recovery thủ công; chưa cung cấp lệnh tự sửa crash state. Stop flag lưu bền, poll khoảng 50 ms; timeout/stop kết thúc tiến trình trực tiếp và lưu logs. Budget thời gian không phải CPU/RAM quota. Stdout/stderr tối đa 1 MiB mỗi stream; vượt giới hạn làm attempt thất bại. `estimated_usd` chỉ là dự toán, không chặn provider billing.

Chỉ hỗ trợ chương trình leaf, không sinh tiến trình con/daemon. Chưa có Windows Job Object hoặc sandbox/process-group containment đa nền tảng; vì vậy stop không được coi là đảm bảo dừng toàn bộ cây tiến trình. Phát hiện pipe còn mở sau khi tiến trình cha kết thúc sẽ ghi `unknown`, không cho resume. Một worker cùng OS account có thể sửa file/DB: hash và SQLite không chống worker ác ý hoặc race ngoài giao thức.

## Reviewer gate

```powershell
army --project C:\path\project job review-bundle JOB_ID
# Giao bundle và artifacts cho reviewer ở context mới, không đưa worker chat.
army --project C:\path\project job review JOB_ID --report review.json --console
```

Report JSON có đúng ba fields: `bundle_hash` lấy từ request_hash của review-bundle; `verdict` là pass/fail; `findings` là giải thích không rỗng. CLI preview nội dung trước khi người dùng xác nhận. Artifact, log hoặc input đổi làm review bị stale; `job status` của completed job có `review_current=false` nếu evidence đổi. Review pass không tự promote global. Citation locator tồn tại không đồng nghĩa claim được nguồn hỗ trợ.

Bundle bỏ worker chat nhưng Army chưa mở/kiểm chứng native reviewer session; `fresh_context_verified=false` luôn rõ ràng. Đây là bàn giao và user gate, không phải bằng chứng đã có independent scientific review.

## Promotion global

Sau `promotion prepare` và `promotion preview`, người dùng trực tiếp chạy `promotion publish ID --console` hoặc `promotion revoke ID --console`. Nội dung, đích và hash phải khớp preview; source stale vẫn bị chặn. Project/global dùng cùng cơ chế lưu trữ bước 4. Không tự đồng bộ toàn bộ memory hoặc chat history.

## Chưa nghiệm thu

Native host trusted approval, worker isolation, process-tree kill, reviewer session attestation và provider cost telemetry vẫn thiếu. Auto mode cố ý disabled. Tests dùng authority/TTY giả và dữ liệu tổng hợp; không coi đó là người dùng thật đã duyệt hay Claude/Codex E2E. Installer/migration và native nghiệm thu thuộc bước 6–7, cần duyệt riêng.
