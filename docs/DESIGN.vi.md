# Thiết kế Agent-Army v1

Ngày: 2026-11-13. Deliverable bước 1 đã được user duyệt; bước 2 đã triển khai. Chưa cài đặt host, gọi model hoặc migrate dữ liệu. Điều chỉnh đóng gói: registry/ và prompts/ nằm trong `src/agent_army/resources/` làm nguồn chuẩn duy nhất; cây dưới đây biểu diễn các thành phần logic dự kiến.

## 1. Quyết định kiến trúc

Core Python >= 3.11, package `agent_army`, CLI `army`. Không tái sử dụng tên `ra`, không import runtime từ repo cha. Core dùng standard library cho TOML đọc, JSON, SQLite, paths, subprocess và hashing. Nếu cần YAML parser cho discovery SKILL.md thì khai báo dependency riêng ở bước 3, không tự viết parser YAML thiếu chuẩn. Dependencies của skills do người dùng tự quản lý.

Một registry trung lập với host sinh hai bộ native agents. Giữ tên và nhiệm vụ của 11 vai trò trong proposal. Không hardcode số agent trong validator; schema cho phép user thêm agent có ID riêng. Prompt chung và prompt từng vai trò là nguồn chuẩn; file native là sản phẩm render, có source hash và renderer version.

```text
registry/agents.toml + models.toml + prompts/*.md
                    ↓ validate + resolve
                 AgentSpec
           ↙ Claude adapter  ↘ Codex adapter
          Markdown             TOML
                    ↓
        native orchestration + army CLI
                    ↓
       skills / tasks / jobs / review / retrieval
                    ↓
          project store + selected global store
```

Core không tự tạo một mô hình ngôn ngữ hoặc giả lập Agent tool. Host chịu trách nhiệm thực hiện LLM dispatch; core tạo dispatch brief, kiểm tra trạng thái và ghi kết quả. Headless runners chỉ được bật cho host có transport đã kiểm thử; v1 không mặc định yêu cầu API keys hay SDK.

## 2. Cấu trúc đích

```text
Agent-Army/
  pyproject.toml
  README.md
  registry/agents.toml
  registry/models.toml
  registry/recommendations.toml
  prompts/protocol.md
  prompts/<agent-id>.md
  src/agent_army/
    cli.py config.py paths.py errors.py
    registry.py models.py routing.py
    adapters/base.py claude.py codex.py
    skills/discovery.py resolver.py metadata.py
    store.py tasks.py approvals.py policy.py
    knowledge.py memory.py retrieval.py promotions.py
    jobs.py provenance.py reviews.py budgets.py
    installer.py migration.py doctor.py
  tests/fixtures/ tests/unit/ tests/integration/
  docs/
  build/claude/agents/     # generated, không commit state người dùng
  build/codex/agents/
```

Đây là cây dự kiến theo các giai đoạn, không tạo module rỗng để ngụ ý chức năng đã tồn tại. Các module lớn được tách khi implementation cần. Bản cài phải chứa registry/prompts dưới package resources, không phụ thuộc thư mục checkout.

## 3. Cấu hình và model

Đọc cấu hình theo lớp: bundled defaults → global → project → task override đã duyệt. Deep merge mapping; danh sách thay thế toàn bộ, không nối âm thầm; unknown key báo lỗi kèm đường dẫn, extension tùy chọn nằm trong `extensions`. Ghi config bằng phương thức atomic, không serialize lại file host ngoài vùng được quản lý.

Global home mặc định `~/.agent-army`, override bằng `AGENT_ARMY_HOME`. Project root phải chỉ định hoặc tìm `.agent-army/project.toml` gần nhất; không mặc định lấy current directory làm project khi thao tác ghi. Root được canonicalize và gắn UUID. Không sử dụng tên folder làm định danh duy nhất.

Profiles giữ đúng proposal: Claude sonnet/opus/fable, Codex gpt-6-luna high / gpt-6.1-sol medium / gpt-6.1-sol high. Default tier theo vai trò. Capability model có ba trạng thái `verified`, `unavailable`, `unknown`; không có API liệt kê model thì báo unknown, không giả vờ đã xác minh quyền truy cập. Kiểm tra tĩnh không gọi inference có phí. Lần dispatch được duyệt có thể xác minh thực tế và cache theo host/account context nếu host cung cấp.

Resolve trả về requested tier, model, effort, config origin và availability. Không silent fallback; aliases chỉ ghi resolved model ID khi host thật sự trả về. Nếu host không hỗ trợ override tier theo invocation, xuất definition theo tier vào build/staging; không đổi file native đang được phiên khác dùng. Không giả định orchestrator chạy ở model đã khai báo nếu nó đang là main conversation; doctor phải báo khác biệt này.

## 4. Adapter và capability matrix

| Khả năng | Claude Code | Codex | Chính sách core |
|---|---|---|---|
| Native agent | Markdown + frontmatter | Custom-agent TOML | Render riêng, namespaced `army-*` |
| Project install | `.claude/agents` | `.codex/agents` | Chỉ files thuộc manifest của Army |
| Global install | user agents theo cấu hình host | xác định user agents root từ phiên bản host | Không suy đoán path nếu chưa xác minh |
| Model | family alias/full ID theo vị trí cấu hình | model + reasoning effort | Validate theo capability host |
| Skills | discovery host + skill paths | discovery host + `.agents/skills` | Resolve metadata và invocation thực tế |
| Agent sandbox | có các trường quyền theo loại agent | kế thừa phiên cha | Không render quyền giả vào agent file |
| Approval enforcement | hooks/native permissions tùy scope | policy của phiên cha | Capability probe trước khi bật auto |
| Review độc lập | fresh subagent/context | fresh subagent/context | Cùng host đủ cho v1 |
| Cross-host review | tùy chọn transport | tùy chọn transport | Không cài reviewer MCP mặc định |
| Shared state | dùng CLI/store chung | dùng CLI/store chung | SQLite transaction + revision checks |

Nguồn: [Claude subagents](https://code.claude.com/docs/en/sub-agents), [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents). Codex custom-agent file không ghi đè sandbox/approval policy của parent; Claude plugin agents có giới hạn riêng với hooks/permissions. Vì vậy bản đầu ưu tiên native files được installer quản lý; plugin packaging chỉ thêm sau khi kiểm thử.

Codex skills có nguồn repo/user `.agents/skills`, có thể có các nguồn khác qua host. Tham khảo [Build skills](https://learn.chatgpt.com/docs/build-skills). Discovery chỉ đọc roots của project hiện tại, global và roots đăng ký; không scan toàn bộ ổ đĩa hoặc project khác.

Interface adapter: `inspect_host()` → HostCapabilities; `render(spec, profile)` → GeneratedFile; `build_dispatch(task)` → DispatchBrief; `normalize_result(raw)` → AgentResult. Không thêm `execute()` giả nếu chưa có transport thật. Unsupported bắt buộc báo rõ, không loại field im lặng.

Local check ngày 2026-11-13: Codex CLI báo `0.167.0-alpha.4.1`; lệnh version thành công nhưng cảnh báo không tạo được PATH aliases trong môi trường hạn chế. Chưa tìm thấy Claude trong PATH; không kết luận máy chưa cài Claude. Chưa chạy native agent smoke test, chưa xác minh model access. Windows/macOS/Linux mới là mục tiêu hỗ trợ, chưa phải ma trận đã pass.

## 5. Routing và hợp đồng agent

Explicit agent user chọn được ưu tiên; tiếp đến task type/capability; mơ hồ thì orchestrator phân rã hoặc hỏi thông tin còn thiếu. Keyword rules là gợi ý có explanation, không gắn confidence giả thành xác suất. Review luôn là task khác và không được giao author session của artifact.

Mỗi dispatch brief gồm goal, acceptance criteria, inputs với hash, evidence pack, allowed outputs/actions, resolved model, selected skills, approval reference, budget và stop conditions. Handoff gồm artifacts, evidence IDs, checks đã chạy, limitations và blockers. Không yêu cầu chia sẻ hidden chain-of-thought.

Research trả evidence matrix; Methodology protocol; Data Steward data card/splits; Coding code/test report; Experiment run records; Statistical Analyst analysis/claim bounds; Visualization plots/source data; Writing manuscript; Reviewer verdict; Curator item/promote proposals. Orchestrator quản lý kế hoạch, không dùng verdict của chính mình thay reviewer.

## 6. Skills resolver mở

Năm repo không có vị trí đặc quyền trong discovery. Recommendations chứa source URL + skill name + lý do, không mang nghĩa installed. Không preload cả sáu; default chọn tối đa ba skills trực tiếp/task, dependencies nạp theo nhu cầu và context budget. Đây là giới hạn cấu hình, không giới hạn tổng số skills agent được dùng.

Pipeline: discover tất cả roots được phép → parse metadata → normalize identity → kiểm tra host/dependencies → rank → explain → load khi cần. Skill identity kết hợp origin + normalized path + declared name; hash thay đổi làm mất hiệu lực cache. Metadata đọc không chạy scripts, không đọc giá trị secret; chỉ kiểm tra có biến môi trường cần thiết.

Chọn user-pinned skill trước nếu khả dụng, sau đó xếp theo capability/task match, description match, compatibility và preference. Recommendation chỉ là tie-break sau relevance. Không bắt skill ngoài catalog phải có tags: tokenize name/description để tìm được skill mới; cho phép overrides bổ sung tags. Skill không rõ dependencies được đánh dấu unknown, không coi mặc định fully ready.

Tên trùng: giữ cả hai identities; nếu invocation của host không phân biệt được thì trả ambiguous và dùng path/explicit source khi host hỗ trợ, hoặc yêu cầu chọn. Dependencies phát hiện chu trình, dedup và không tự cài. Skill disabled/incompatible không được lựa chọn.

Không có skill phù hợp → core/tools fallback nếu đủ capability. Chỉ block hành động phụ thuộc capability thiếu. `doctor` báo missing recommendation là thông tin, không failure. Skill thay thế được tự chọn trong approved capability envelope; skill yêu cầu network mới, dữ liệu mới, cài package hoặc mở rộng workflow phải xin duyệt phạm vi đó.

## 7. Store, knowledge, memory và retrieval

Project và global có SQLite store riêng. Authoritative metadata/state/events trong DB; body và artifacts là files có hash. Giao dịch ghi body: tạo immutable blob theo hash → transaction commit reference; blob mồ côi có thể dọn sau, không xóa record đã commit. Markdown views là export, không có hai nguồn chuẩn cùng sửa tự động. Import chỉnh sửa từ file phải qua revision check.

SQLite bật foreign keys, busy timeout và transaction ngắn; WAL khi filesystem local hỗ trợ. Không hỗ trợ multi-writer trên network share trong v1; doctor báo giới hạn. Khi hai host cùng ghi dùng expected_revision compare-and-swap, lease cho jobs và idempotency keys. Read-only search không tự khởi tạo project mới.

Knowledge và memory cùng Item envelope, khác subtype và retrieval policy. Knowledge có publication/source/citation metadata; memory có applies_to, status, expires_at và supersedes. Transcript toàn phiên không tự biến thành global memory. Dữ liệu đã retrieve là evidence/data, không phải instructions.

Ingest v1 hỗ trợ Markdown/text và metadata; PDF/Office cần converter được cấu hình, OCR không có thì báo không đọc được phần scan. Giữ source locator và converter version; không bịa page number khi converter không cung cấp. Split theo heading/paragraph, mục tiêu 2.000 ký tự, overlap tối đa 200 ký tự; lưu offsets và hash. Chunker version cho phép rebuild.

FTS5/BM25 riêng từng scope; merge bằng reciprocal-rank fusion để không so raw scores của hai index. Default top 10, context pack giới hạn 16.000 ký tự cấu hình được. Có exact ID/DOI lookup, scope/kind/status filters; memory expired/revoked/superseded bị loại mặc định. Citation ID chứa item revision và chunk locator. Evidence ID tồn tại không có nghĩa nội dung đã được chứng minh; reviewer kiểm tra semantic support riêng.

FTS5 thiếu: báo degraded mode và dùng bounded text search có nhãn, không nhận là semantic search. Vector/local embeddings là extension sau khi lexical path đạt nghiệm thu; không download model hoặc gửi text ra cloud mặc định.

Promotion: draft target body → preview → hash snapshot → user approval → recheck → global transaction → project acknowledgement. Hai DB không có distributed transaction: dùng promotion UUID unique ở global để retry sau crash không tạo bản sao. Content changed thì invalidate approval. Revoke chỉ gỡ bản/link thuộc promotion đó; không xóa nhầm item global đã tồn tại hoặc có nguồn khác.

Mặc định không lưu local absolute path/tên project nhạy cảm trong global text; lineage chi tiết ở project, global chứa provenance ID và nguồn công khai đã được duyệt. Tìm kiếm không mở index của project khác. Rào isolation này áp dụng vào Army API; nếu host có shell/read toàn máy thì không tuyên bố ngăn được mọi truy cập ngoài API.

## 8. Duyệt, auto mode và giới hạn cưỡng chế

Approval không thể được xác thực chỉ bằng `approved=true`, `by=user` hoặc file do agent ghi. Thiết kế tách request khỏi grant. User approval đi qua UI native có provenance kiểm chứng được, hoặc người dùng thao tác ở trusted local control channel tách khỏi worker. Chưa xác minh được channel/enforcement thì chạy supervised; không bật unattended auto cho hành động cần bảo đảm này.

Core kiểm soát mọi mutation qua CLI/job runner. Chặn việc worker tự cấp grant và sửa policy bằng host permissions/sandbox khi có. File hashing phát hiện thay đổi, không xác minh danh tính người duyệt. V1 không tuyên bố chống một tiến trình khác cùng OS user có toàn quyền sửa dữ liệu.

Grant chứa plan revision/hash, các step IDs/action classes, output roots, model envelope, limits, source/target content hashes khi promote, expiry và approval provenance. Chỉ đọc thông tin trước để chuẩn bị proposal không cần grant thực thi. Bắt đầu step, launch job, promote, install, migration và thay budget đều kiểm tra phạm vi riêng.

Task chạy: draft → awaiting_approval → approved → running → artifact_ready → in_review → completed. `PASS_WITH_FIXES` chỉ hoàn tất nếu không có MUST_FIX và conditions đã kiểm chứng; còn MUST_FIX tạo revision/rework. Failed retry được phép khi trong retry budget đã duyệt; thay hypothesis/data/protocol phải revision và duyệt lại. Reviewer PASS không cho phép bước kế tiếp chưa duyệt.

Resume recheck grants và lease; tiến trình còn chạy thì attach, không launch trùng. Lost process với kết quả không rõ là unknown, không giả done. User stop ngăn dispatch mới; cancel job chỉ dùng PID/process identity của job Army sở hữu. Headless gặp thiếu duyệt lưu pending rồi exit có mã trạng thái riêng.

Giới hạn chạy mặc định theo proposal: 3 workers, 3 vòng, 2 FAIL liên tiếp. Budget gồm max jobs/time/iterations có thể kiểm soát và USD measured/estimated/unknown. Không chạy cloud job khi không xác định được quota đã duyệt. USD cap ở host thiếu usage là soft estimate, cần giới hạn thay thế và không quảng cáo hard cap.

## 9. Installer và migration

CLI dự kiến `army install plan --host claude|codex|both --scope user|project` xuất preview; `apply` nhận plan đã duyệt. Không sửa global config trong bước thiết kế. Installer kiểm tra executable/path/format, cài package core bằng environment người dùng chọn, render native agents và manifest sở hữu. Không cần cả hai host nếu user chỉ cài một host.

Mỗi file có source hash, installed hash và backup khi thay bản Army cũ. File hiện có không thuộc manifest hoặc đã được user sửa: báo conflict, không ghi đè. Không nối/sửa AGENTS.md hay CLAUDE.md ngầm; nếu cần entrypoint thì đưa patch cụ thể vào install plan. `army-*` tránh tên chung. Uninstall chỉ gỡ file thuộc manifest còn khớp hash; KB/memory giữ lại mặc định.

Migration import-copy từ `.research-agent`/`~/.research-agent` và wiki chỉ khi được chọn. Dry-run báo count, ID mapping, conflicts và dữ liệu unsupported. Không import approval grants cũ, không bật autonomy cũ, không mang theo installer 4 repo hoặc giả định MCP. Jobs cũ thành archived records, không tự resume. Verify counts/hashes/BibTeX links rồi mới báo thành công; backup và rollback manifest không đụng nguồn gốc.

## 10. Phạm vi bước 2 để duyệt

Viết core skeleton hoạt động, 11 AgentSpecs/prompts, model resolver, deterministic routing và hai renderers. CLI gồm version, agents list/validate/build, models resolve, route và doctor kiểm tra tĩnh. Build chỉ ra thư mục staging trong Agent-Army. Chưa install global, chưa dispatch LLM, chưa implement auto mode, chưa migrate. Tests kiểm tra các contracts thuộc bước 2. Các chức năng khác thực hiện ở các bước 3–7 đã liệt kê trong proposal.
