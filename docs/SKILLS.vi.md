# Skills discovery và resolver

Version 0.2.0. Các lệnh chỉ đọc metadata và đề xuất lựa chọn; không cài, chạy scripts hoặc cấp quyền thực thi.

## Sử dụng ở vị trí mới

<CHECKOUT>/Agent-Army. Python >=3.11; discovery cần optional extra agent-army[skills] (PyYAML>=6.0,<7). Môi trường dev hiện tại có PyYAML 6.0.3 tại .dev-deps, không cài global.

~~~powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src') + [IO.Path]::PathSeparator + (Join-Path (Get-Location) '.dev-deps')
python -m agent_army skills list --host codex
python -m agent_army skills refresh --host claude
python -m agent_army --isolated skills list --host codex --root C:\my-skills --json
python -m agent_army --isolated skills resolve --host codex --root C:\my-skills --agent research --task "systematic literature review" --max-selected 2
python -m agent_army skills doctor --host claude
~~~

Thay python bằng executable thật nếu PATH chỉ có Windows Store alias. Discovery không tự pip install khi parser thiếu; trả lỗi capability.

## Roots và ranh giới

- Claude user root: CLAUDE_CONFIG_DIR/skills hoặc ~/.claude/skills; project .claude/skills.
- Codex: ~/.agents/skills và .agents/skills từ current directory lên project root.
- Project boundary: --project; nếu không có thì Army project gần nhất, Git root gần nhất, cuối cùng current directory cho discovery read-only.
- --isolated bỏ default roots và auto config; --root và --config explicit vẫn dùng được.
- --root lặp lại để thêm directory được phép, gồm plugin/legacy skill directories.
- --plugin-index PATH đọc Claude installed_plugins.json khi được chỉ định; lọc entries của project khác. Installed không đồng nghĩa enabled trong host.
- Codex plugin layouts không được suy đoán; khai báo root thực tế qua --root hoặc config.
- Không scan toàn bộ home/ổ đĩa/project lân cận. Bỏ symlink/junction directory; chặn file symlink ra ngoài root. Nếu cần, đăng ký target root trực tiếp.
- Giới hạn: 2.000 SKILL.md, 10.000 directories, 1 MiB/file, 64 KiB/frontmatter. Roots chồng lấp dedup resolved path; root đầu xác định origin.
- list/refresh đều đọc mới, chưa có persistent cache. ID phụ thuộc origin/path/name; content_hash thay đổi khi sửa file.
- Built-in skills không có file không được tự bịa; chưa có adapter runtime inventory trực tiếp.

Nguồn đối chiếu: [Codex Build skills](https://learn.chatgpt.com/docs/build-skills), [Claude skills](https://code.claude.com/docs/en/skills). Đây là filesystem discovery, chưa kiểm thử native host load.

## Metadata

Dùng YAML SafeLoader, hỗ trợ multiline. Không thực thi custom tags/dynamic command text. Duplicate keys, aliases, YAML sai và oversized file được báo diagnostics. Body được hash, không đưa vào inventory hoặc thực thi.

Name/description bắt buộc. Compatibility giữ dạng text; không suy luận runtime chắc chắn từ văn xuôi. disable-model-invocation=true yêu cầu --pin để chọn.

Optional Army extension:

~~~yaml
---
name: my-paper-search
description: Search papers and extract experimental evidence.
compatibility: Requires a configured literature provider.
metadata:
  army:
    capabilities: [paper-search, evidence-extraction]
    hosts: [claude, codex]
    dependencies: []
    requires_env: [MY_PROVIDER_KEY]
    requires_tools: []
    enabled: true
---
~~~

Dependencies nhận skill ID, absolute SKILL.md path hoặc tên duy nhất. Thiếu/vòng lặp/trùng tên/disabled/incompatible/missing tool-env khiến candidate không được chọn. Closure giới hạn depth/count 64.

- unavailable: disabled, incompatible hoặc thiếu env/tool được khai báo.
- unknown: chưa khai báo đầy đủ dependency/env/tool requirements.
- declared_ready: requirements khai báo có sẵn; không có nghĩa chạy thật đã pass.

Không đọc/in API key values. Requirements chỉ nằm trong compatibility/body chưa được kiểm tra tự động. Unknown vẫn có thể là candidate, kèm caveat trước thực thi.

## Config không sửa skill nguồn

~~~toml
[skills]
max_selected = 3
roots = [
  {path = "my-skills", origin = "https://example.org/team/skills", scope = "custom"}
]

[skills.overrides."C:\\my-skills\\search\\SKILL.md"]
capabilities = ["paper-search"]
hosts = ["claude", "codex"]
dependencies = []
requires_env = []
requires_tools = []
enabled = true
~~~

Relative root giải theo thư mục config. Overrides dùng exact absolute path hoặc ID; ID ưu tiên path. Không dùng tên chung để tránh thay nhầm. Chỉ khai báo requirements rỗng khi đã kiểm tra thực tế. Invocation optional là host hint, không bảo đảm host đã đăng ký.

Global/project/explicit config merge; roots list thay toàn bộ ở lớp sau, overrides tables merge. Recommendation chỉ tie-break khi name và origin URL trùng; không suy đoán nguồn từ tên.

## Resolution

Xét toàn bộ inventory: user-selected --pin → task terms/required capabilities → agent capabilities → recommendation tie-break. Mặc định tối đa 3 direct candidates; dependencies trả riêng, dedup. Skill ngoài năm repo có thể được chọn cho mọi agent và được ưu tiên nếu phù hợp hơn.

--require chỉ định capability bắt buộc. --tool-capability chỉ định capability tools hiện có cung cấp.

- skills: có candidates và dependency closure hợp lệ.
- tools: không cần skill bắt buộc; dùng tools khi đủ năng lực.
- blocked: capability --require không được skills hoặc tools khai báo cung cấp.

Kết quả gồm selected, dependencies, unavailable, ambiguous, unresolved_pins, missing_capabilities, diagnostics. Không tìm thấy pin thì báo, không tự cài. Blocked là kết quả resolution (CLI exit 0); caller phải kiểm tra fallback_mode trước hành động.

Trùng tên không tự chọn. --pin exact ID/path xác định nội dung cần đọc, không thay host shadowing. Không có invocation rõ thì trả exact SKILL.md path để agent đọc bằng host tools đã có quyền.

Ranking là lexical heuristic, không phải semantic embedding; agent vẫn đánh giá suitability. Resolver không biết đầy đủ managed settings hoặc runtime enablement. Resolution không cấp quyền network/install/write, không tự kích hoạt pipeline hay thay user approval.

Shared memory/knowledge, approvals/job runtime và auto mode chưa triển khai.
