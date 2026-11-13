# Knowledge và memory chung — v0.3.0

Core không phụ thuộc Claude hoặc Codex. Hai host dùng cùng project root và AGENT_ARMY_HOME thì đọc/ghi cùng dữ liệu. Chưa tự cài entrypoint vào host, chưa tự thu thập chat history.

## Dữ liệu ở đâu

- Global mặc định ~/.agent-army; override bằng AGENT_ARMY_HOME.
- Project: <project>/.agent-army.
- Mỗi scope có store.sqlite, SQLite WAL khi ghi, blobs/<sha256>.md.
- Project còn có project.toml chứa UUID và canonical root.
- Metadata/current revision/events/promotions lưu SQLite. Nội dung là blob immutable theo hash. Markdown views không phải nguồn chuẩn thứ hai.
- Không dùng cloud storage hay embedding API. Chỉ thử local filesystem; UNC shares bị từ chối, mapped network drives chưa tự phát hiện.
- Khi khởi tạo xong, hai sessions có thể ghi chung với SQLite transactions và revision checks. Khởi tạo lần đầu nên chạy một phiên.

Source files của Agent-Army ở <CHECKOUT>/Agent-Army. Kho thật không được tự tạo trong lượt phát triển; toàn bộ tests dùng thư mục tạm.

## CLI

Python >=3.11; core store không cần dependency ngoài. Từ source dùng PYTHONPATH=src; khi dùng skills cần thêm .dev-deps như README.

Các ví dụ dưới đây là thao tác user tự chọn, chưa được chạy lên dữ liệu thật:

~~~powershell
# Chọn project rõ ràng; không tạo project từ current directory ngầm.
python -m agent_army --project C:\my-project store init --scope project
python -m agent_army store init --scope global

python -m agent_army --project C:\my-project kb add --title "Paper A" --file C:\notes\paper-a.md --metadata C:\notes\paper-a.json
python -m agent_army --project C:\my-project memory add --title "Quyết định chia dữ liệu" --file C:\notes\decision.md

python -m agent_army --project C:\my-project kb search "eye tracking" --scope both --json
python -m agent_army --project C:\my-project memory search "chia dữ liệu" --context-chars 8000
python -m agent_army --project C:\my-project kb get ITEM_ID --revision 1
python -m agent_army --project C:\my-project memory update ITEM_ID --expected-revision 1 --file C:\notes\decision-v2.md
python -m agent_army --project C:\my-project memory update ITEM_ID --expected-revision 2 --status superseded
python -m agent_army --project C:\my-project kb rebuild --scope project
~~~

Ingest chỉ .md/.txt UTF-8, tối đa 4 MiB. PDF/Office/OCR cần chuyển đổi tường minh trước; không giả số trang. Metadata JSON tối đa 64k bytes ở CLI, có thể chứa doi, arxiv, url, source locator, evidence_status. Memory thêm memory_key, applies_to (UUID project hoặc "*"), expires timestamp có timezone. Không ghi secrets vào metadata.

Update phải gửi expected revision. Nếu Claude đã ghi revision 2 thì Codex đang giữ revision 1 nhận conflict thay vì ghi đè. Nội dung cũ vẫn đọc được theo revision khi item hiện còn active. Superseded/deprecated/revoked/expired bị loại khỏi retrieval mặc định; list --include-inactive để audit metadata. Update chưa có tùy chọn xóa expires_at; tạo entry thay thế rồi supersede entry cũ nếu cần bỏ hạn.

Global add/update trực tiếp bị chặn. Content global đi qua promotion service và approval adapter. Rebuild chỉ tái tạo index từ dữ liệu đã có, không xuất bản thêm nội dung.

## Retrieval và nguồn

Chunk theo paragraphs khoảng 2.000 ký tự, overlap tối đa 200, giữ heading/character offsets. Citation chứa item UUID, revision và offsets; không bịa page locator. Exact lookup theo UUID/DOI/arXiv, chuẩn hóa DOI/arXiv prefixes. Cùng DOI nhưng nội dung khác được giữ riêng và báo related_source_items; chỉ exact document fingerprint mới dedup.

FTS5/BM25 từng scope; normalize dấu tiếng Việt và query thành literal terms để tránh FTS syntax injection. Merge project/global bằng reciprocal-rank fusion, không so raw BM25 giữa hai DB. Nếu không có FTS5 dùng bounded text fallback có nhãn degraded. Mỗi scope xem tối đa 2.000 candidate chunks, báo truncated; không phải semantic vector search.

Context pack mặc định tối đa 16.000 ký tự (gồm citation/title), top 10 hits. Trường hits giữ đoạn đầy đủ để inspection; chỉ context là pack đã cắt theo budget. Nguồn chưa xác minh mang evidence_status=unverified; citation tồn tại không chứng minh claim đúng.

Memory global chỉ áp dụng khi applies_to phù hợp. Project memory đang active có cùng memory_key sẽ ưu tiên hơn global ngay cả khi query chỉ khớp text của global. Current user instructions luôn ưu tiên hơn memory. Project khác không được scan qua Knowledge API. Quyền shell/file read của host vẫn do host quản lý, không phải SQLite bảo vệ toàn máy.

Search không tạo global store khi chưa có. Store/project identities được kiểm tra; chuyển project đã init cần migration riêng, không tự sửa canonical root.

## Chọn nội dung lên global

~~~powershell
# Toàn bộ một item:
python -m agent_army --project C:\my-project promotion prepare ITEM_ID
# Chỉ một đoạn (character offsets Python Unicode, end exclusive):
python -m agent_army --project C:\my-project promotion prepare ITEM_ID --start 0 --end 240
# Hoặc bản tóm tắt/biên tập:
python -m agent_army --project C:\my-project promotion prepare ITEM_ID --summary-file C:\notes\public-summary.md
python -m agent_army --project C:\my-project promotion preview PROMOTION_ID
~~~

Preview lưu source revision/hash và exact target body/title/metadata/expiry cùng hash toàn snapshot, gắn đích global. Metadata tự chọn chỉ gồm nguồn công khai và memory_key; không tự copy private local paths. Memory promotion default applies_to=["*"] được hiển thị trong preview để user quyết định. Người dùng phải kiểm tra cả body/title/metadata; hệ thống không tự đảm bảo nội dung đã hết riêng tư.

Nguồn hoặc đích đổi sau preview → cần proposal/approval mới. Không được thêm --approved để vượt gate.

**Giới hạn tích hợp tại bước 4:** CLI publish/revoke fail closed với code 4 vì chưa kết nối trusted user-approval adapter. Core đã có prepare/preview/apply/revoke/reconcile và kiểm thử với SyntheticAuthority chỉ nằm trong tests. Việc ghi nhận approval thật và cưỡng chế worker không tự cấp quyền thuộc bước 5. SyntheticAuthority tuyệt đối không dùng production. Duyệt kế hoạch phát triển không đồng nghĩa duyệt xuất bản nội dung nghiên cứu.

Khi có adapter, receipt phải khớp action, promotion ID, preview hash, actor/receipt IDs và expiry. Hash không phải bằng chứng danh tính; authority phải xác minh user ngoài worker, không nhận JSON tự gắn by=user.

Apply giữ source revision ổn định trong transaction, global promotion ID unique. Lỗi sau global commit trước project acknowledgement có thể retry không trùng; reconcile chỉ đồng bộ acknowledgement của commit đã tồn tại, không tạo global content mới. Không có distributed transaction hai DB.

Revoke gỡ liên kết promotion; chỉ ẩn item khi không còn liên kết active và không có nguồn global độc lập cần giữ. Không xóa revision mới ngoài phạm vi promotion. Item bị thu hồi không được retrieve lại dù rebuild index; dữ liệu audit/blob vẫn còn để truy vết. Không thể xóa nội dung đã vào context chat cũ.

## Chưa có ở bước này

Trusted approval integration, native-host end-to-end, job/task runtime, vector embeddings, PDF converter tự động, migration dữ liệu cũ hoặc sync cloud. Không tuyên bố completed research workflow chỉ từ store tests.


## Cập nhật bước 5 (0.4.0)

Có supervised job runner và console consent tùy chọn cho publish/revoke; mặc định vẫn fail closed. Console không phải trusted native host channel. Xem JOBS.vi.md về state machine, limits, reviewer gate và các giới hạn còn thiếu; auto mode vẫn disabled.
