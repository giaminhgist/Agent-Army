# Agent-Army — đề xuất để duyệt

Ngày khảo sát: 2026-11-13. Trạng thái: **ĐÃ TRIỂN KHAI CORE BƯỚC 4**. Xem `docs/STEP-4-REPORT.vi.md`; bước 5 trở đi chờ duyệt theo giai đoạn. Global publish/revoke thật chưa mở khi chưa có trusted approval adapter.

Đây là bản nâng cấp mạnh từ Research-Agent. Đã có core tĩnh và bộ sinh native agents ở bước 2; chưa cài vào host, chưa sửa bản Research-Agent cũ, chưa chạy auto mode. Các mục dưới đây lưu đề xuất thiết kế; trạng thái implementation xem báo cáo từng bước.

Thư mục mới: `<CHECKOUT>/Agent-Army`. Đã chuyển thành thư mục riêng trong Downloads theo yêu cầu user; có thể trở thành repo độc lập.

## 1. Kết quả khảo sát và hướng kế thừa

Nguồn chính: repo <LEGACY_CHECKOUT>/Research-Agent, gồm README.md, registry/agents.toml, config/default.toml, docs/ARCHITECTURE.md, install.py và src/research_agent/. Các nguồn giữ nguyên sau khi chuyển Agent-Army ra ngoài.

- Giữ 7 vai trò gốc: orchestrator, research, methodology, coding, experiment, writing, reviewer.
- Giữ evidence-first, run manifest, trace, quality gates, budget, checkpoint, CPU smoke test và reviewer ở context riêng.
- Registry hiện bắt buộc đúng 7 agent, tập model chủ yếu Claude, danh sách core/borrow skills phải có trong catalog. Chuyển thành registry mở và adapter theo host.
- Repo cũ đã có discovery skills và khả năng borrow; hạn chế là preload/catalog/routing vẫn phụ thuộc mạnh các repo biết trước. Nâng cấp resolver này, không coi nó là tính năng hoàn toàn mới.
- KB hiện là SQLite FTS5/BM25, có project/global và promotion queue. Memory hiện là project decisions/progress/state. Mở rộng retrieval theo đoạn và thêm global memory có chọn lọc.
- Bộ cài mới chỉ cài Agent-Army và dependencies tối thiểu của chính nó. Bỏ cài/update 4 repo skills, requirements-skills mặc định, bootstrap ARIS và MCP reviewer bắt buộc. Không gỡ các skills người dùng đã cài.

Nguồn bổ trợ: 14 định nghĩa trong `<REFERENCE_AGENTS>`.

| Nguồn bổ trợ | Áp dụng |
|---|---|
| agent-organizer | Chia việc, điều phối dựa trên khả năng có thật, không bịa số đo hiệu suất |
| scientific-literature-researcher, research-analyst | Trích xuất phương pháp/cỡ mẫu/giới hạn, tổng hợp nhiều nguồn |
| research-assistant | Phân biệt tra cứu, quick check, giải thích, chạy ý tưởng và brainstorm; giải thích trước việc tốn tài nguyên |
| data-engineer | Data Steward và lineage/schema/quality checks |
| data-scientist | Statistical Analyst; không sao chép yêu cầu máy móc p < 0.05 |
| python-pro, refactoring-specialist | Coding Agent, kiểm thử và refactor giữ hành vi |
| ml-engineer, machine-learning-engineer | Coding + Experiment; phục vụ mô hình chỉ khi project cần |
| documentation-engineer | Tài liệu tái lập, hướng dẫn và Knowledge Curator |
| ai-writing-auditor | Biên tập trong Writing Agent, giữ nghĩa khoa học |
| prompt-engineer | Checklist thiết kế/đánh giá prompt trong Coding và Methodology khi làm LLM research |
| agent-installer | Tham khảo discovery và preview; triển khai installer bằng CLI xác định, không thêm LLM agent chỉ để cài |

Không sao chép đường dẫn riêng của semantic-ID project, dịch vụ context-manager giả định, quyền MCP chưa tồn tại hoặc chỉ tiêu thành tích chưa đo.

## 2. Kiến trúc đề xuất

Một core Python dùng chung, một registry trung lập với host, hai adapter Claude Code và Codex. Không duy trì hai bản logic nghiên cứu riêng biệt.

```text
User → kế hoạch + duyệt → Orchestrator
                              ↓
             Agent registry + model profiles + skill discovery
                              ↓
       Research → Methodology → Data → Coding → Experiment
                                                    ↓
                                    Analysis → Visualization → Writing
                              ↓
                    Reviewer độc lập → Quality gate
                              ↓
                  Artifacts + Knowledge + Memory
                              ↓
               Chọn mục + xem nội dung + duyệt → Global
```

Đây là luồng đầy đủ; nhiệm vụ nhỏ chỉ gọi các agent cần thiết. Registry 11 vai trò không có nghĩa chạy đồng thời 11 agent. Đề xuất giới hạn ban đầu 3 worker đồng thời, điều chỉnh theo host và ngân sách.

- Claude adapter: sinh native agent definitions và entrypoints tương thích Claude Code.
- Codex adapter: sinh native custom-agent TOML và entrypoints tương thích phiên bản Codex đã kiểm tra.
- Kiểm tra khả năng host: model, effort, spawn, skills, hooks, permissions. Không coi hai nền tảng có mọi hook giống nhau.
- Enforcement dùng cơ chế native khi có và kiểm soát tại CLI/job runner. Prompt chỉ hướng dẫn, không được mô tả là rào bảo mật. Nếu host không chặn được hành động bắt buộc phải duyệt, không bật auto mode cho hành động đó.
- Hai host dùng cùng schema KB/memory/artifact. Ghi đồng thời có lock/transaction và định danh session.
- Cross-host reviewer tùy chọn khi cả hai công cụ đã sẵn sàng; reviewer cùng host ở context mới vẫn là chế độ hợp lệ.

## 3. Danh sách agent đề xuất

Tổng: **1 orchestrator + 10 sub-agent**. Bốn vai trò bổ sung được đánh dấu mới.

| ID | Vai trò và đầu ra | Default tier |
|---|---|---|
| orchestrator | Phân tích mục tiêu, task graph, duyệt, dispatch, ngân sách, checkpoint; đầu ra plan/status/handoff | medium |
| research | Literature search, systematic review, evidence table, khoảng trống; đầu ra evidence matrix + bibliography | light |
| methodology | Giả thuyết, novelty, baselines, splits, ablations, statistical plan; đầu ra protocol trước thí nghiệm | medium |
| data-steward — mới | Kiểm kê/schema/missingness/duplicates/leakage/lineage; đầu ra data card + split manifest | light |
| coding | Python/PyTorch, baseline, pipeline, debug, refactor; đầu ra code + kiểm thử phù hợp | light |
| experiment | Chạy và theo dõi jobs, seeds/configs/resource budget; đầu ra run manifest + logs + kết quả thô | light |
| statistical-analyst — mới | CI/effect size/tests/multiple comparisons/subgroups/error analysis; đầu ra phân tích gắn run_id | medium |
| visualization — mới | Figures, tables, sơ đồ, captions; đầu ra mã sinh hình + dữ liệu nguồn + hình xuất | light |
| writing | Manuscript/proposal/rebuttal, LaTeX, biên tập; đầu ra bản thảo gắn nguồn và số liệu | medium |
| reviewer | Review methodology/code/results/manuscript ở context mới; đầu ra PASS/PASS_WITH_FIXES/FAIL và MUST_FIX | medium |
| knowledge-curator — mới | Ingest, dedup, retrieval, memory curation, promotion preview; đầu ra KB items + hàng đợi duyệt | light |

Reviewer không tự sửa artifact đang review; đề xuất sửa được giao lại tác giả. Knowledge Curator không tự phê duyệt đưa dữ liệu lên global. Thống kê được thiết kế ở Methodology và thực hiện ở Statistical Analyst; Experiment tập trung vận hành runs.

## 4. Model profiles

Repo gốc dùng light/heavy/super_heavy, orchestrator cố định Opus và methodology/writing có hai mức. Đề xuất chuẩn hóa thành **light/medium/heavy**, giữ chủ trương dùng model mạnh hơn cho công việc cần suy luận sâu.

| Tier | Claude mặc định đề xuất | Codex mặc định đề xuất |
|---|---|---|
| light | sonnet | gpt-6-luna, effort high |
| medium | opus | gpt-6.1-sol, effort medium |
| heavy | fable | gpt-6.1-sol, effort high |

Đây là preset thiết kế, không phải khẳng định chất lượng/chi phí tương đương giữa hai hãng. Heavy trên Codex có thể tăng effort của cùng model. Có thể đổi heavy sang model khác được tài khoản hỗ trợ trong cấu hình.

- Tất cả vai trò có đủ ba profile; cột default ở trên chọn điểm xuất phát. Orchestrator/methodology/writing/reviewer/analysis ưu tiên medium; các nhiệm vụ hẹp dùng light.
- Thứ tự override: lựa chọn cho task đã duyệt → project/agent → global/agent → preset.
- Resolve model tại cài đặt và trước dispatch; ghi requested/resolved model, effort và tier vào trace.
- Thiếu model: báo rõ và xin chọn mapping thay thế; không âm thầm dùng model khác.
- Tăng tier phải nằm trong phạm vi được duyệt; heavy cần duyệt riêng nếu chưa có trong kế hoạch được duyệt.
- Giá tiền lấy từ cấu hình có ngày cập nhật; nếu host không cung cấp usage thì hiển thị unknown/estimate, không tuyên bố USD cap được đảm bảo tuyệt đối.
- Khi migrate: light cũ → light mới, heavy cũ → medium mới, super_heavy cũ → heavy mới; các vai trò hai mức cần preview mapping riêng để tránh đổi hành vi âm thầm.

## 5. Sáu skills gợi ý cho từng agent

Nguồn đã tham khảo đủ 5 repo:

- **KD**: [Scientific Agent Skills](https://github.com/k-dense-ai/scientific-agent-skills), `skills/<name>/SKILL.md`.
- **AR**: [ARIS](https://github.com/wanshuiyin/auto-claude-code-research-in-sleep), `skills/<name>/SKILL.md`; chọn biến thể Codex nếu skill có phụ thuộc host.
- **SV**: [Supervisor-Skills](https://github.com/HKUSTDial/Supervisor-Skills), `skills/<name>/SKILL.md`.
- **SP**: [Superpowers](https://github.com/obra/superpowers), `skills/<name>/SKILL.md`.
- **HU**: [Humanizer](https://github.com/blader/humanizer/blob/main/SKILL.md).

Các tiền tố dưới đây là ký hiệu nguồn trong đề xuất, **không phải tên lệnh invocation cam kết**. Adapter phải resolve tên thực tế từ bản skill người dùng đã cài.

| Agent | Đúng 6 skills gợi ý |
|---|---|
| orchestrator | SP:brainstorming; SP:writing-plans; SP:dispatching-parallel-agents; SP:verification-before-completion; AR:research-pipeline; SV:vibe-research-workflow |
| research | KD:literature-review; SV:deep-research; AR:research-lit; AR:semantic-scholar; AR:openalex; KD:citation-management |
| methodology | KD:hypothesis-generation; KD:experimental-design; AR:novelty-check; AR:experiment-plan; AR:ablation-planner; SV:idea-evaluator |
| data-steward | KD:exploratory-data-analysis; KD:polars; KD:dask; KD:datalad; KD:scikit-learn; SP:verification-before-completion |
| coding | SP:test-driven-development; SP:systematic-debugging; SP:requesting-code-review; AR:research-implement-feature; KD:pytorch-lightning; KD:scikit-learn |
| experiment | AR:run-experiment; AR:experiment-queue; AR:monitor-experiment; AR:training-check; AR:system-profile; AR:experiment-audit |
| statistical-analyst | KD:statistical-analysis; KD:statsmodels; KD:pymc; KD:shap; AR:analyze-results; AR:result-to-claim |
| visualization | KD:scientific-visualization; KD:matplotlib; KD:seaborn; AR:paper-figure; AR:figure-spec; SV:figure-designer |
| writing | KD:scientific-writing; AR:paper-writing; AR:rebuttal; SV:paper-writer; SV:paper-polish; HU:humanizer |
| reviewer | KD:peer-review; AR:research-review; AR:experiment-audit; AR:paper-claim-audit; AR:citation-audit; SV:pre-submission-reviewer |
| knowledge-curator | AR:research-wiki; AR:wiki-enrich; KD:citation-management; KD:markitdown; AR:citation-audit; SP:verification-before-completion |

Lý do phân bổ: Research ưu tiên truy xuất/tổng hợp; Methodology ưu tiên giả thuyết và thiết kế; Data ưu tiên tính đúng của dữ liệu và phép biến đổi; Coding ưu tiên triển khai/kiểm thử; Experiment ưu tiên vận hành; Analysis ưu tiên thống kê và giới hạn kết luận; Visualization ưu tiên hình truy vết được; Writing kết hợp viết khoa học và chỉnh văn phong; Reviewer kiểm tra độc lập; Curator chuẩn hóa và lưu tri thức.

Một số skills cần công cụ riêng: experiment-queue/monitor-experiment thiên về remote/SSH, training-check dùng W&B; các skill review ARIS có thể cần reviewer backend. Chúng là đề xuất có điều kiện, không phải yêu cầu bắt buộc cho chạy local/CPU. markitdown có các đường xử lý local và external; chỉ dùng đường phù hợp quyền đã cấp. SHAP hỗ trợ giải thích mô hình, không tự chứng minh nhân quả. Humanizer chỉ biên tập ngôn ngữ, không đảm bảo vượt bộ phát hiện AI.

Đã kiểm tra tên skills trong README/directory upstream, và đọc metadata của các skills khoa học/vận hành quan trọng. Chưa cài hay kiểm thử runtime các skills này trên máy. Khi triển khai resolver sẽ kiểm tra bản thực tế, dependencies và compatibility; 6 gợi ý có thể thay thế theo skills mới.

## 6. Skills mở, không cài mặc định

- **Yêu cầu user bổ sung:** cả 5 repo chỉ là nguồn gợi ý, không phải tập skills bắt buộc hay danh sách nguồn được phép duy nhất. Mọi sub-agent được chọn skills phù hợp từ bất kỳ nguồn nào người dùng đã cài/cho phép, kể cả khi không có một skill nào từ 5 repo này.
- Resolver đánh giá tất cả skills khả dụng theo mức phù hợp với task và khả năng thực tế. Recommendation chỉ là gợi ý khi phù hợp; skill ngoài 5 repo có thể được chọn ngay cả khi skill gợi ý đã có. Người dùng có thể chỉ định ưu tiên riêng.
- Nếu thiếu skill gợi ý, tìm skill thay thế trong toàn bộ danh mục đã discovery. Nếu không có skill phù hợp, agent vẫn làm bằng tools và năng lực sẵn có khi đủ khả năng; chỉ báo thiếu hoặc chờ bổ sung khi hành động thực sự cần capability chưa có. Không báo lỗi chỉ vì thiếu tên skill hoặc repo được gợi ý.
- Discovery từ host/plugin, global/project skill roots và custom roots người dùng đăng ký; hỗ trợ SKILL.md và nguồn host cung cấp.
- Registry lưu recommended_skills, capability tags, compatibility, dependencies, source và path/hash. Không bắt buộc nằm trong catalog dựng sẵn.
- Sáu skills là recommendations, không phải whitelist, không preload cả sáu mỗi lần. Chỉ tải skills phù hợp task.
- Sau khi người dùng tự cài skill mới: refresh discovery là đủ; không cần sửa prompt từng agent.
- Chọn skill theo nhiệm vụ + mô tả + khả năng + availability + preference; giải thích vì sao chọn. Tên trùng phải được resolve theo nguồn/scope, không chọn ngẫu nhiên.
- Chưa cài skill: tiếp tục bằng năng lực agent nếu đáp ứng task, hoặc báo capability thực sự thiếu. Không tự cài thêm repo/package/MCP.
- Doctor phân biệt suggestion chưa cài với dependency thật sự bắt buộc của hành động sắp chạy.
- Skills không được thay đổi approval scope hay tự kích hoạt whole-pipeline auto mode. Nếu skill đòi phạm vi lớn hơn task đã duyệt, dừng ở ranh giới đó.
- Chỉ lưu metadata/link khuyến nghị. Không vendor/copy toàn bộ nội dung các repo skills. Nếu về sau cần tái phân phối nội dung, kiểm tra license riêng, đặc biệt Supervisor-Skills khai báo CC BY-NC-SA 4.0.

## 7. Knowledge, memory và RAG hai cấp

Hai loại dữ liệu riêng biệt:

- Knowledge: papers, trích đoạn, evidence tables, phương pháp, ghi chú nguồn.
- Memory: quyết định, giả định, sở thích làm việc, bài học/debug notes, thất bại, trạng thái task.

```text
~/.agent-army/
  config.toml
  knowledge/       # tri thức global được người dùng chọn
  memory/          # memory global được người dùng chọn
  indexes/         # có thể tái dựng

<project>/.agent-army/
  project.toml
  plans/ tasks/ artifacts/ reviews/ runs/
  knowledge/ memory/ indexes/
  approvals/ promotions/ checkpoints/ trace/
```

- Mặc định dữ liệu sinh trong project lưu project; global không có nghĩa upload cloud, mà là dùng chung trên máy.
- Retrieval tìm project hiện tại + global, trả về scope, nguồn, vị trí đoạn/trang, thời gian và evidence ID. Cho phép lọc chỉ project hoặc chỉ global.
- Bản đầu dùng chunking + FTS5/BM25, metadata filters, dedup và context budget; có retrieval pack để agent viết câu trả lời gắn nguồn. Vector search/local embeddings là phần tùy chọn, không phải điều kiện cài đặt.
- Nếu bật semantic retrieval: index tách scope, chọn embedding provider rõ ràng, rebuild được; cloud embeddings cần duyệt dữ liệu gửi đi.
- DOI/arXiv ID/content hash giúp dedup; tách nguồn chưa kiểm chứng, giả thuyết và kết luận có bằng chứng.
- Promotion dùng cùng cơ chế cho knowledge và memory: chọn từng item hoặc đoạn → preview nội dung đích → loại thông tin riêng project nếu cần → duyệt → ghi global và provenance.
- Approval gắn item ID + content hash + phạm vi; chỉnh nội dung sau duyệt phải duyệt lại. Agent không được tự cấp approval.
- Có thể giữ local, đưa bản tóm tắt đã biên tập lên global, hoặc loại khỏi queue. Không tự đồng bộ toàn bộ project và không tự promote sau mỗi phiên.
- Memory global có scope áp dụng, nguồn, thời gian, trạng thái superseded/deprecated và xử lý xung đột. Quyết định project ưu tiên hơn gợi ý global; memory không vượt chỉ dẫn hiện tại của user.
- Có revoke/unpublish cho bản global và xóa khỏi index/context cache tương lai; giải thích rằng không xóa được thông tin đã được đọc trong context cũ.
- Dùng lại KB/ARIS research-wiki qua import hoặc connector; một bản nguồn canonical, tránh hai wiki tự sửa lẫn nhau.
- Migration từ .research-agent và ~/.research-agent: dry-run, backup, copy không phá dữ liệu gốc, kiểm chứng số item/metadata, chỉ thực thi sau duyệt riêng.

## 8. Duyệt trước auto mode

Áp dụng cho cả quá trình xây dựng Agent-Army và cách Agent-Army vận hành về sau.

```text
draft → awaiting_user_approval → approved → running → review → completed
                                      ↘ paused / failed / needs_new_approval
```

- Default: supervised. Mỗi bước có mục tiêu, agent, model tier, skills dự kiến, input/output, vùng được ghi, tiêu chí pass, tài nguyên và stop conditions để user duyệt trước khi chạy.
- Duyệt idea không tự động duyệt implementation, install, migration hay auto mode.
- Có thể duyệt một bước hoặc một nhóm bước xác định. Auto mode chỉ thực hiện phạm vi đã duyệt; không tự chuyển sang bước kế tiếp chưa được duyệt.
- Phạm vi/model/chi phí/dữ liệu thay đổi đáng kể → proposal revision và yêu cầu duyệt mới.
- Chạy lại sau gián đoạn phải kiểm tra approval còn hiệu lực, content hash và checkpoint; không tự rerun jobs đã hoàn tất.
- Headless gặp approval thiếu thì lưu pending và dừng. Reviewer PASS không thay thế user approval.
- Stop khi đạt mục tiêu, hết ngân sách/time/iteration cap, lỗi lặp, thiếu dữ liệu hoặc user yêu cầu dừng. Đề xuất mặc định tối đa 3 vòng và dừng sau 2 verdict FAIL liên tiếp.

## 9. Các bước triển khai để duyệt tuần tự

| Bước | Deliverable trình duyệt | Điều kiện hoàn tất |
|---|---|---|
| 0 — hiện tại | Đề xuất này: roles, model profiles, 6 skills/agent, scope | User duyệt hoặc chỉnh ý tưởng; chưa triển khai |
| 1 — thiết kế chi tiết | Schemas, cấu trúc thư mục, capability matrix Claude/Codex, approval contract, installer plan | Chốt thiết kế bằng user approval |
| 2 — core + adapters | Registry mở, render agent definitions, routing/models, CLI tối thiểu | Validate cả hai định dạng; round-trip config; không cài skill ngoài |
| 3 — skills discovery | Resolver mở, refresh, overrides, doctor | Skill mới dùng được không sửa source; missing/conflict/dependency có báo đúng |
| 4 — KB/memory/RAG | Hai cấp lưu trữ, chunk retrieval, promotion preview + approve + revoke | Không đọc project khác; promote đúng item/hash; index rebuild được |
| 5 — orchestration | Approval state machine, tasks/jobs, manifests, review, budgets, resume | Chưa duyệt không chạy; scope thay đổi bị chặn; resume không chạy trùng |
| 6 — packaging + migration | Installer Claude/Codex/both, dry-run, backup, uninstall, import dữ liệu cũ | Idempotent; giữ config ngoài phạm vi quản lý; không gỡ skills người dùng |
| 7 — nghiệm thu | Smoke test hai host + báo cáo limitations + hướng dẫn | User duyệt kết quả rồi mới chọn auto mode cho một nhiệm vụ cụ thể |

Mỗi bước chỉ bắt đầu khi user duyệt bước đó. Sau khi hoàn tất sẽ trình kết quả để duyệt bước tiếp theo. Kiểm thử kỹ thuật nằm trong phạm vi bước đã duyệt; cài vào môi trường thật, migration dữ liệu và bật auto mode có phạm vi duyệt riêng.

## 10. Tiêu chí nghiệm thu trọng tâm

- Cài fresh trên Claude và Codex với zero external skills vẫn khởi tạo, lập plan và dùng KB được.
- Thêm skill từ nguồn mới, refresh, task phù hợp tìm thấy mà không đổi code registry.
- Không có skills từ cả 5 repo tham khảo nhưng có skills tương đương từ nguồn khác: mọi agent vẫn resolve và sử dụng được. Skill ngoài 5 repo phù hợp hơn phải có thể được chọn ngay cả khi recommendation đã cài.
- Model theo tier/agent/project resolve đúng; unavailable không silent fallback.
- Synthetic project A/B kiểm tra isolation; chỉ items đã promote được tìm thấy từ global.
- Knowledge lẫn memory có chọn lọc, preview, approval, dedup, provenance và revoke.
- Sửa nội dung sau approval hoặc mở rộng task không được dùng approval cũ.
- Một pipeline nhỏ: literature fixture → protocol → baseline CPU → analysis → figure → report → review; phân biệt test fixtures với research thật.
- Ngắt/resume và chạy đồng thời Claude/Codex không hỏng state hoặc chạy trùng jobs.
- Installer không có bước cài/update skills repo hay reviewer MCP mặc định; uninstall chỉ gỡ phần do Agent-Army sở hữu.
- Chỉ tuyên bố tương thích host/OS đã kiểm tra; ma trận Windows/macOS/Linux ghi rõ verified, CI-only hoặc chưa kiểm thử.

## 11. Tài liệu host và nguồn khảo sát

- [Codex subagents: model/effort và cấu hình custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
- [Claude Code subagents: scope, models, skills và permissions](https://code.claude.com/docs/en/sub-agents).
- Các repo nguồn skills được liên kết trong mục 5. Đây là tham khảo thiết kế; chưa thực thi workflow của các skills đó trong lượt khảo sát.

User đã duyệt đề xuất, thiết kế và thực hiện bước 2. Thiết kế nằm trong `docs/DESIGN.vi.md`, `docs/CONTRACTS.vi.md` và `docs/IMPLEMENTATION.vi.md`; kết quả bước 2 trong `docs/STEP-2-REPORT.vi.md`. Chưa cho phép toàn bộ implementation; bước 4 store/retrieval/core promotion đã triển khai; bước kế tiếp là approval authority và orchestration.
