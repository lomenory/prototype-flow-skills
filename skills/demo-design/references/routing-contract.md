<!-- generated-from: contracts/*.yaml; contract-hash: e0a96def6e9c; do-not-edit -->
# Routing Contract

先判断 Request Intent 与当前授权，再选择 Execution Tier 和 Delivery Route；最后叠加 0 个或多个 Mode 与 Facet。Request Intent 决定只读、提案或执行；Tier 决定读取、辅助产物和验证深度；Route 决定交付形态。

## Request Intent Gate

| Request intent | Representative signals | Authorization | Outcome | Required fields |
| --- | --- | --- | --- | --- |
| `inspect_only` | analyze<br>inspect<br>check<br>diagnose<br>why<br>is this feasible<br>分析<br>检查<br>看看原因<br>是否可行 | `read_only` | `inspect_and_report_without_writes` | `review_question`<br>`inspectable_scope` |
| `propose_only` | proposal<br>compare options<br>plan a solution<br>give me an approach<br>给方案<br>比较方案<br>规划一下 | `read_only` | `deliver_proposal_then_stop` | `decision_goal`<br>`current_context` |
| `execute_now` | implement<br>modify<br>fix<br>apply these annotations<br>do it directly<br>修改<br>实现<br>修复<br>按标注调整<br>直接做 | `explicit_implementation_request` | `execute_when_materially_ready_otherwise_propose` | `explicit_implementation_request`<br>`requested_outcome`<br>`protected_scope` |
| `resume_approved` | execute the approved proposal<br>implement the plan above<br>resume implementation<br>按方案修改<br>执行此计划<br>继续实施 | `explicit_implementation_request` | `execute_approved_scope` | `explicit_implementation_request`<br>`approved_artifact_or_conversation_scope` |
| `publish` | commit<br>push<br>create pull request<br>merge<br>提交<br>推送<br>创建 PR<br>合并 | `explicit_publish_request` | `perform_only_explicitly_requested_git_actions` | `explicit_publish_request`<br>`requested_git_actions`<br>`exact_target` |

判断顺序：`request_intent` → `material_readiness` → `execution_tier` → `delivery_route` → `modes_and_facets`。

只有同时满足以下条件才自动执行：

- intent is execute_now or resume_approved
- implementation authorization is explicit in the current user request
- required intent, tier, route, mode and facet fields are complete
- no material blocker or design-context conflict remains

以下情况先交付提案并停止：

- intent is propose_only
- intent is execute_now but implementation authorization or material readiness is incomplete
- a material business, state, permission, requirement-binding, migration or scope decision is unresolved
- the requested change cannot be bounded safely after bounded discovery

方案认可或一般性回应（`looks good`、`approved`、`the proposal is fine`、`方案没问题`、`可以`、`同意方案`）只确认内容，不授权修改。`commit`、`push`、`pull_request`、`merge` 始终需要分别明确授权。

## Execution Tier Policies

| Tier | Existing artifact | Required fields | Guidance | Design system | Default profile | Strict session | Verification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `tier_0_text_copy_only` | required | `inspectable_artifact`<br>`exact_target`<br>`requested_change`<br>`semantic_impact` | `unchanged` | `inherit_existing` | `static_only` | `off` | static artifact scan<br>exact target and requested copy |
| `tier_1_local_ui_patch` | required | `inspectable_artifact`<br>`exact_target`<br>`target_selectors`<br>`requested_change`<br>`expected_result`<br>`protected_scope` | `reuse_if_present_never_create` | `inherit_existing` | `interactive_demo` | `reuse` | one relevant viewport<br>visible target and expected result<br>unauthorized emoji<br>affected interaction when applicable<br>target screenshot |
| `tier_2_layout_or_interaction` | required | `inspectable_artifact`<br>`affected_layout_or_interaction`<br>`verification_targets`<br>`expected_result`<br>`affected_viewports_or_states` | `reuse_and_update_affected_fields_if_present` | `inherit_existing` | `interactive_demo` | `reuse` | affected viewports or states<br>named interactions<br>observable results<br>experience checks for multi-step interaction paths<br>key-state screenshots<br>portability when resources change<br>keep the HTML entry and changed resources together in the demo folder |
| `tier_3_full_delivery` | not required | selected Route schema | `create_or_fully_refresh_for_web_app_only` | `select_core_or_follow_authoritative_context` | `interactive_demo` | `off` | main user path<br>key visible states and screenshots<br>experience checks for applicable primary, error, cancel and recovery paths<br>one bounded rendered-quality correction loop<br>resource portability<br>primary share artifact is the complete demo folder containing its HTML entry and resources<br>main product scenarios when applicable<br>design-reference comparison when external fidelity applies |

## Verification Profiles

| Profile | Default | Activation | Browser surface | Navigation transport | Runner | Evidence | Unavailable status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `static_only` | no | `tier_0_or_review_default` | `none` | `none` | `dependency_free_validators` | inspectable artifact<br>requested copy or review evidence<br>applicable static contracts | `not_applicable` |
| `interactive_demo` | yes | `default_for_web_and_app_browser_evidence` | `codex_builtin_browser` | `loopback_http` | `agent_browser_workflow` | loopback preview URL<br>target viewport<br>visible initial state<br>named interactions<br>observable results<br>key screenshots | `degraded` |
| `strict_regression` | no | `explicit_user_request_only` | `local_playwright` | `loopback_http` | `scripts/verify.py` | repeatable TEST scenarios<br>actual console, page and request error arrays<br>required hard-rule completeness<br>hard-rule measurements<br>pixel diff when requested | `unavailable` |

## Delivery Routes

| Delivery route | Brief schema | Default verification | Required reads | Tier-specific reads |
| --- | --- | --- | --- | --- |
| `web_hi_fi` | `web_hi_fi` | `tier_3_full_delivery` / `interactive_demo` | `references/routes/web.md` | `tier_3_full_delivery`: `references/design-guidance.md`, `references/web-preflight.md` |
| `app_flow` | `app_flow` | `tier_3_full_delivery` / `interactive_demo` | `references/routes/app.md` | `tier_3_full_delivery`: `references/design-guidance.md`, `references/app-preflight.md` |
| `design_review` | `design_review` | `tier_0_text_copy_only` / `static_only` | `references/quality.md`<br>`references/routes/review.md` | — |

## Modes

| Mode | Applies to | Brief schema | Required reads |
| --- | --- | --- | --- |
| `data_viz` | `web_hi_fi`<br>`app_flow`<br>`design_review` | `data_viz` | `references/modes.md`<br>`references/dependencies.md`<br>`references/data-viz-preflight.md` |
| `product_contract` | `web_hi_fi`<br>`app_flow`<br>`design_review` | `product_contract` | `references/product-contract-mode.md`<br>`contracts/product-contract.schema.json` |

## Facets

- `design_context_dependency`：screenshot, URL, Figma, uploaded UI image, specified component library, existing page or code when design-language extraction is required。 Bound patch: `tier_0_and_tier_1_inherit_without_reextracting`。
- `ant_design_enterprise`：Ant Design, antd, ProComponents, ProTable, ProForm, Ant Design-style admin, management backend, operations backend, back-office, admin console, operations console, 管理后台, 运营后台, 中后台, 后台项目, 运维控制台, existing Ant Design project。

## Routing Rules

- Tier 必须在完整 Route 工作流前选择；先做有界定位，仍不能安全限定范围时才升级到 `tier_3_full_delivery`。
- 每个任务只能有一个 Delivery Route；Web、App 或 Review 冲突时，只询问决定交付形态的字段。
- Mode 不能单独替代 Route。
- 截图、URL、Figma、组件库或需要提取设计语言的现有代码会影响产物时才触发 Design Context Facet；Tier 0/1 有界修改直接继承现有设计语言。
- 外部设计源或中高风险多文件交付使用统一 `DESIGN.md`；旧 `design.md` 只读兼容，单文件低风险 Demo 可用 HTML 注释，Review-only 不创建文件。
- Web/App 的默认主分享格式是 `project_bundle`：入口 HTML 与 CSS、JavaScript、图片等资源集中在同一个独立文件夹，使用相对路径，发送整个文件夹；不另生成分享 HTML。
- Route、Mode 或 Facet 的 material blocker 未解决时停止；低影响未知项记录为 assumption。
- Tier 决定范围和证据深度，不决定浏览器引擎；Web/App 默认使用 `interactive_demo`，只有用户明确要求时才进入 `strict_regression`。
- Interactive Demo 验证本地 HTML 时先运行 `scripts/preview-server.py`，通过它输出的 `http://127.0.0.1:<port>/...` 地址访问；`file://` 只用于人工打开，不作为 Browser 自动化证据。

## Escalation

至少升级到 `tier_2_layout_or_interaction`：

- layout crosses a bounded parent container or changes responsive strategy
- navigation, interaction, or observable state changes
- multiple independent page regions are affected
- asset or resource paths change

至少升级到 `tier_3_full_delivery`：

- no inspectable existing artifact
- page goal or primary user task changes
- information architecture or design language changes
- business state, permission, requirement binding, or Product Contract changes
- multiple pages or core sections change
- external replication or brand-sensitive fidelity is required
- change scope still cannot be bounded safely after bounded discovery

## Verification Tiers

- `tier_0_text_copy_only`：static review or non-behavior text-only follow-up。
- `tier_1_local_ui_patch`：small local visual patch。
- `tier_2_layout_or_interaction`：layout, navigation, state or targeted interaction。
- `tier_3_full_delivery`：new delivery, major redesign or brand-sensitive work。

## Source

此文件由 Canonical Contracts 生成；Runtime 中为只读快照。
