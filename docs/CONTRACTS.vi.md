# Hợp đồng dữ liệu v1 — dự thảo bước 1

Đây là thiết kế schema, chưa phải các schema/runtime đã triển khai. Tất cả bản ghi persisted có `schema_version = 1`, timestamp UTC ISO-8601; UI hiển thị theo timezone user. ID là UUID không suy ra từ số lượng records; content hash SHA-256. Paths tương đối với root có tên rõ ràng, chống traversal và symlink escape; không sử dụng prefix chuỗi thô để kiểm tra containment.

## AgentSpec và ModelProfile

| Field | Type / validation |
|---|---|
| id | slug unique `[a-z][a-z0-9-]*`; không chứa path separator |
| description, role | nonempty string |
| prompt_path | file trong prompt root, tồn tại khi build |
| default_tier | light / medium / heavy |
| capabilities | list capability IDs; host-independent |
| output_contract | tên artifact contract |
| recommended_skills | list source/name references; có thể rỗng, không bắt buộc installed |
| model_overrides | optional map host → tier → model/effort |
| policy | read/write intent + approval action classes; không phải bảo đảm OS sandbox |

Bundled defaults có 11 vai trò và 6 recommendations/role. User thêm role không phải đổi code validator. ModelProfile: host, tier, model, optional effort; cả ba tier có mapping sau merge. Validation không hardcode whitelist toàn bộ model ID; adapter chỉ kiểm tra cú pháp và known restrictions, availability riêng.

## SkillDescriptor và SkillResolution

SkillDescriptor: `id`, `name`, `description`, `origin`, `scope`, `path`, `content_hash`, `host_invocation`, `capabilities`, `compatibility`, `dependencies`, `requirements`, `enabled`, `metadata_status`. `origin` không giới hạn ở năm repo. `host_invocation` có thể null nếu chỉ đọc được metadata nhưng chưa biết cách gọi.

Resolution: `selected[]` với identity/hash/reason, `dependencies[]`, `unavailable[]` kèm reason, `ambiguous[]`, `fallback_mode = tools|skills|blocked`, `missing_capabilities[]`. Một recommendation absent không làm fallback_mode thành blocked. Skills cần requirement không rõ được ghi unknown. Chỉ trả required env names, không bao giờ đưa values vào trace.

## Plan, Task, Approval và Event

| Entity | Fields chính |
|---|---|
| Plan | id, project_id, revision, goal, steps, acceptance, content_hash |
| Task | id, plan_id/revision, agent_id, dependencies, state, expected_revision, model, inputs, outputs, policy_envelope, approval_id |
| ApprovalRequest | id, action, project_id, plan_hash, step_ids, preview_hash, scope, limits, requested_at |
| ApprovalGrant | id, request_id, exact scope/hash, expires_at, granted_at, actor_provenance, revoked_at |
| Event | id, entity_id, seq, timestamp, session_id, host, type, payload; append via DB transaction |

Grant được nhận từ trusted approval channel, không từ trường user truyền vào tùy ý. `scope` gồm action classes, roots, model tiers và allowed capability envelope. Plan revision hoặc promotion preview hash đổi thì grant cũ không dùng lại. Approval grant không được migrate từ hệ cũ. Task dependency graph phải acyclic; dependency missing báo lỗi. State transition dùng compare-and-swap để hai sessions không cùng claim task.

## Item, Chunk, RetrievalHit và Promotion

Item: id, project_id (null cho global), scope, kind (`knowledge|memory`), subtype, title, body_hash, revision, created_at, source metadata, evidence_status, tags, status. Knowledge thêm DOI/arXiv/BibTeX key/URL; memory thêm applies_to, expires_at, supersedes. DOI trùng không đồng nghĩa hai bản revision có body giống nhau.

Chunk: id, item_id, item_revision, body_hash, chunker_version, heading, start/end offset, optional page locator, text_hash. Khi text đổi phải rebuild chunks; không trỏ citation cũ vào nội dung mới.

RetrievalHit: item/revision/chunk IDs, scope, snippet, locator, rank, ranking_method, source metadata và evidence_status. Score là ranking nội bộ, không phải confidence khoa học.

Promotion: id, source item/revision/hash, selected spans hoặc prepared target body hash, target_scope=global, preview_hash, approval_id, status, target_item_id, origin_link_id. State: draft → pending → approved → applying → promoted; rejected/stale/failed/revoked là trạng thái riêng. Global unique promotion ID đảm bảo retry idempotent. Acknowledge project thất bại không undo global commit; retry đối chiếu ID.

## RunManifest, Review và AgentResult

RunManifest: run_id, task/revision, job_key, argv array, cwd, relevant config hashes, input data hashes hoặc explicit partial-hash policy, git commit/dirty diff hash, environment summary, seeds, device, output roots, started/ended, exit_code, status và resource/cost provenance. Không log secrets hoặc full environment. Command chạy argv với shell=false mặc định; shell script phải là artifact được duyệt riêng.

Review: id, task_id, reviewer_session_id, artifact paths/hashes, verdict, findings với severity/evidence/required fix, checks executed và limitations. Author/reviewer session phải khác nhau. Hash artifact đổi làm review stale.

AgentResult: task_id, artifact references/hashes, source/run evidence IDs, checks, summary, limitations, blockers, proposed_next_steps. Proposals không phải authorization. Kết quả sai schema được trả về để sửa, không coi là PASS.

## Errors và CLI

CLI hỗ trợ human output và `--json`; JSON có schema_version, ok, data hoặc error {code,message,details}. Mã dự kiến: 0 success; 2 invalid input/config; 3 missing capability; 4 needs approval; 5 conflict/stale revision; 6 job failure; 7 partial/unknown state. JSON không in log trộn lên stdout. Sensitive diagnostics được scrub trước export.

Ví dụ commands dự kiến (chưa hoạt động): `army agents build --host both --output build`; `army skills resolve --agent research --task "..."`; `army kb search --scope both "..."`; `army memory propose-global ITEM`; `army promotion preview ID`. Chưa chốt CLI grant cho đến khi trusted channel được kiểm thử; không cung cấp `--approved` để agent tự vượt gate.


## Cập nhật bước 5 (0.4.0)

Có supervised job runner và console consent tùy chọn cho publish/revoke; mặc định vẫn fail closed. Console không phải trusted native host channel. Xem JOBS.vi.md về state machine, limits, reviewer gate và các giới hạn còn thiếu; auto mode vẫn disabled.
