# Bước 5 — supervised approvals và jobs

Ngày 2026-11-13. Version 0.4.0. User đã duyệt bước 5; bản này bàn giao supervised workflow theo fallback đã nêu trong kế hoạch. Chưa hoàn thành trusted native enforcement hoặc unattended auto.

## Đã triển khai

- Console consent tương tác theo action/ID/hash, challenge một lần, receipt có expiry; mặc định thiếu authority thì chặn. Không nhận cờ tự khai approved.
- Promotion publish/revoke có tùy chọn console cho người dùng; không tự promote dữ liệu thật.
- Jobs JSON + SQLite state/revision/events, transaction claim chống hai runner cùng project, provenance và bounded logs.
- CPU leaf process, argv shell=False, input/executable hash kiểm tra lại, output mới và hashes; không tự xóa output cũ.
- Timeout, cumulative wall budget, 3 attempts/2 failures tối đa; stop/resume phải duyệt lại. Không auto retry hoặc tự khôi phục crash job.
- Reviewer bundle không có worker chat; report bind bundle hash, user gate, stale input/artifact/log invalidation.
- CLI job create/preview/run/status/stop/resume/review-bundle/review; doctor và 22 native definitions phản ánh capability thật.

## Giới hạn và bằng chứng

Console TTY chỉ cho supervised workflow; không xác thực người thật đối với PTY/UI automation cùng tài khoản. Không có host broker/capability enforcement; chưa chứng minh worker không tự cấp quyền ở OS level. Vì vậy auto luôn disabled.

Một active job/project. Không hỗ trợ tiến trình sinh child/daemon, GPU, OS sandbox, process-tree stop hay chi phí provider thực tế. Crash claim giữ running để tránh duplicate; recovery cần kiểm tra thủ công. Chưa mở reviewer session tự động; fresh_context_verified=false. Seed/environment manifest là provenance khai báo, chưa phải tái lập toàn bộ môi trường.

Unit/integration tests chỉ dùng CPU fixtures, temporary homes/stores và authority/TTY giả. Không có bằng chứng native Claude/Codex E2E hoặc người dùng thật đã thử console. Không cài host agent, không migrate dữ liệu thật và không bật auto trên dữ liệu người dùng.

## Bước kế tiếp cần duyệt

Bước 6: installer cho Claude/Codex và migration có preview, backup/hash, conflict preservation, rollback/uninstall. Kiểm thử bằng fake homes và legacy fixtures trước. Không cài năm repo skills; không real install/migration trước preview và duyệt riêng. Bước 7 mới nghiệm thu native host và đánh giá khả năng trust/isolation.

## Kết quả nghiệm thu

- 99 tests: 98 pass, 1 skip (Windows symlink permission); không failures/errors.
- Rebuild 22 native definitions và wheel agent_army-0.4.0-py3-none-any.whl.
- Wheel smoke độc lập source/PyYAML: job CLI hoạt động, thiếu authority bị chặn code 4, không spawn.
- Chi tiết: STEP-5-VALIDATION.json.
