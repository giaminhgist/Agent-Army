# Bước 4 — shared knowledge và memory

Ngày: 2026-11-13. Vị trí: <CHECKOUT>/Agent-Army. Version 0.3.0.

## Đã triển khai

- SQLite store riêng global/project, UUID project, immutable content blobs, versions/events.
- Knowledge/memory add/get/list/update, optimistic revision check và concurrent-write tests.
- DOI/arXiv lookup, exact document dedup và related sources.
- Paragraph chunks với offsets/citations; FTS5/BM25, bounded fallback, scope merge/context budget.
- Memory expiry/status/applicability và project preference override theo memory_key.
- Promotion selection/summary/preview, snapshot hash, stale-source check, idempotent global commit, crash reconciliation và revoke có bảo toàn shared references.
- CLI store/kb/memory/promotion và native instructions dùng chung storage.
- Không tạo store thật, migrate hoặc promote dữ liệu thật trong lượt phát triển.

## Ranh giới với bước 5

Core publication/revoke được kiểm thử qua approval authority giả trong tests. CLI production không có authority nên cố ý từ chối publish/revoke với code 4. Còn thiếu trusted user-approval adapter và worker enforcement; đó là phần bước 5, không được thay bằng cờ approved hoặc file tự xưng user.

Vì vậy bước 4 hoàn tất storage/retrieval và promotion service ở mức core; chưa thể tuyên bố flow người dùng duyệt rồi publish thật đã hoạt động end-to-end.

## Kiểm chứng

Fixtures gồm project A/B/global, hai client cùng project, cập nhật đồng thời, source/blob/preview thay đổi, approvals giả sai hash/hết hạn, crash sau global commit, recovery khi nguồn đã đổi, multi-reference revoke và preexisting global data.

Báo cáo kết quả cuối cùng được ghi thêm sau nghiệm thu. Symlink integration test từ bước 3 có thể skip do Windows; mock containment test vẫn chạy.

## Bước tiếp theo

Bước 5: approval authority tin cậy, task/job state machine, provenance, budget/stop/resume và reviewer gates. User duyệt trước khi triển khai. Xem KNOWLEDGE.vi.md để dùng phần hiện có.

## Nghiệm thu cuối bước 4

- 75 tests: 74 pass, 1 skip; không failures/errors.
- Ca skip là Windows symlink integration; mock containment vẫn pass.
- Rebuild 22 native definitions và wheel agent_army-0.3.0-py3-none-any.whl thành công.
- Smoke từ wheel giải nén (không source checkout, không optional PyYAML) xác minh hai client đọc cùng memory; publication thiếu authority bị chặn đúng code 4.
- Không tạo global home/project state thật, không promote dữ liệu thật, chưa native host E2E.
- Chi tiết: STEP-4-VALIDATION.json.
