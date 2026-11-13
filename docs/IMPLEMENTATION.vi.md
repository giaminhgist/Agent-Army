# Kế hoạch triển khai và nghiệm thu

Trạng thái ngày 2026-11-13:

- Bước 0: user đã duyệt proposal và bổ sung skills ngoài năm repo được dùng bình thường.
- Bước 1: user đã duyệt thiết kế và yêu cầu tiếp tục bước tiếp theo.
- Bước 2: đã triển khai core, 11 agent definitions, model resolver, routing và hai renderers; xem STEP-2-REPORT.vi.md.
- Bước 3: user đã duyệt; đã triển khai discovery/resolver, xem STEP-3-REPORT.vi.md.
- Bước 4: user đã duyệt; đã triển khai store/retrieval/core promotion, xem STEP-4-REPORT.vi.md. Trusted publication adapter chưa có.
- Bước 5: user đã duyệt; triển khai supervised runner/console consent/review gate, xem STEP-5-REPORT.vi.md. Trusted native approval/isolation và auto chưa có.
- Bước 6: user đã duyệt; đã triển khai offline installer và import-copy migration, xem STEP-6-REPORT.vi.md. Chỉ test fake homes/fixtures, chưa cài/migrate thật.
- Bước 7: chưa bắt đầu; chờ duyệt. Real install/migration cần preview cụ thể được duyệt trước.

## Bước 2 — core và hai adapters

Files: pyproject, package core/config/paths/errors/registry/models/routing/adapters/CLI, registry mặc định, prompts của 11 vai trò, tests và fixtures.

Deliverable: `army agents list`, `validate`, `build --host both`, `models resolve`, `route`, `doctor` chạy được trong môi trường dev; generated definitions ở build, không cài vào host. Namespaced native agents; core không import research_agent cũ.

Checks: custom role thứ 12 không cần đổi code; duplicate ID/missing prompt/cycle bị bắt; TOML parse đúng; Claude frontmatter parse đúng; round-trip config; model override precedence; unsupported capability không bị bỏ im lặng; rendering deterministic; không xuất skills chưa cài thành mandatory preload. Build với registry không recommendation vẫn pass.

## Bước 3 — discovery/resolver

Fixtures có user/project/plugin/custom root; hai skills cùng tên; skill ngoài catalog; missing deps/cycle; skill unknown host; file changed và disabled. Sáu recommendation đều absent vẫn resolve được skill thứ ba từ nguồn bất kỳ. Skill mới phù hợp hơn thắng recommendation. Empty skill roots vẫn cho tools fallback. Không thực thi scripts hoặc tự cài dependencies trong discovery.

## Bước 4 — KB/memory/RAG

Fixtures project A/B + global; lexical retrieval bằng tiếng Việt/Anh; citation locator; dedup DOI/hash; expired memory; chọn một đoạn promote; content đổi sau duyệt; revoke; index rebuild. Test crash giữa global commit và project acknowledgement không tạo trùng. Hai sessions ghi cùng revision: chỉ một thành công. FTS5 missing phải báo degraded. Tất cả fixtures tổng hợp, không dùng dữ liệu cá nhân thật để test.

## Bước 5 — điều phối/approvals/jobs

Viết trust/enforcement integration trước khi bật auto. Test worker không tự cấp grant; grant hết hạn/revoked/stale không chạy; budget/iteration caps; artifact changed làm review stale; retry có giới hạn; crash/resume không spawn job trùng; user stop. Kiểm thử host thật quyết định capability nào được unattended; nếu thiếu channel tin cậy vẫn giao supervised workflow và ghi rõ auto chưa hỗ trợ, không báo hoàn tất auto.

Run smoke dùng chương trình CPU nhỏ có seed và output hash. Không thuê GPU hay gọi dịch vụ có phí để chạy tests mặc định. Review checks phân biệt citation tồn tại với claim được nguồn hỗ trợ.

## Bước 6 — installer/migration

Tests dùng fake homes trong temporary directory trước. Fresh install, reinstall, update, uninstall, user-edit conflict, partial failure/rollback; config ngoài Army giữ nguyên; không có clone/install commands của năm repo skills. Migration copy legacy fixtures, không grants/autonomy; count/hash/links khớp và original bytes giữ nguyên. Real install hoặc real migration chỉ thực hiện sau preview được user duyệt.

## Bước 7 — nghiệm thu host

Chạy task fixture từ plan tới review trên từng host đã có executable/account. Verify agent được load, model requested/actual (nếu host báo), skill discovery thật, policy và stop behavior. Một host chưa sẵn sàng phải ghi NOT TESTED, không đánh dấu pass từ unit tests. Windows kiểm tra local; macOS/Linux cần CI hoặc môi trường thật, ghi mức chứng cứ riêng.

## Ma trận yêu cầu và test quyết định

| Yêu cầu | Bước | Evidence phải có |
|---|---|---|
| Hai host | 2, 7 | generated parser checks + native smoke từng host |
| Agent/model mở | 2 | custom role + override/failure tests |
| Không phụ thuộc 5 repo | 3, 6 | empty roots + third-party skills + installer manifest |
| Knowledge và memory hai cấp | 4 | isolation/search/promotion/revoke tests |
| Duyệt trước từng bước | 5 | chưa grant/stale grant bị chặn ở runner và host support |
| Reproducibility | 5, 7 | run manifest + reproduce fixture |
| Migration giữ dữ liệu | 6 | byte/hash checks nguồn + destination mapping |
| Auto có giới hạn | 5, 7 | trust channel + stop/caps/resume integration |

## Điểm cần duyệt để bắt đầu bước 2

Core Python, CLI `army`, native files qua adapters, registry 11 vai trò, schemas ở CONTRACTS.vi.md và phạm vi bước 2 nêu trên. Bước 2 chỉ build/test local; không cần approve lại từng thao tác nằm trong phạm vi đó. Kết thúc bước 2 sẽ báo checks đã chạy và trình duyệt bước 3.
