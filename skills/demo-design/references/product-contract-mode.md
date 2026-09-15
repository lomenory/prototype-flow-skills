# Product Contract Mode

当原型用于客户流程确认、开发交接、PRD 演示，或检查 Demo 与需求是否一致时，叠加 `product_contract` Mode。不要把自然语言需求直接翻译成 HTML；先创建规范化产品契约，再建立 UI 映射。

## Input And Readiness

- 文档、对话、仓库证据和明确假设都是合法来源；进入契约后统一用 `SRC-*` 引用。
- 对话输入不要求先补写 PRD。先提取已确认内容，只追问会改变流程、字段、状态、权限、破坏性影响或数据范围的缺项。
- 低影响未知项标记为 `assumption`；行为级未知项标记为 blocking `open_question`。
- `readiness: ready` 时不得保留 blocking open question。用户说“直接做”不能覆盖此门禁。

## Canonical Artifact

产物目录必须包含 `prototype-contract.json`。生成前读取 Runtime 随附的 `contracts/product-contract.schema.json`，不要猜测字段；核心结构为：

- `sources`：文档、对话、仓库或假设来源。
- `requirements`：`ACT-*`、`SCN-*`、`FIELD-*`、`STATE-*`、`PERM-*`、`RULE-*` 与 `QUESTION-*`。
- `realization`：`SCREEN-*` 与 `UI-*` 映射。
- `acceptance`：可执行 `TEST-*` 场景。

`prototype-contract.json` 是 AI 与验证器读取的旁路产物，不得内嵌到 HTML，也不得生成面向用户的契约、规格或调试界面。Contract Hash 是规范化 JSON 的 SHA-256，只写入验证报告。旧产物的 `schemaVersion: 1/2` 保持兼容；新建或业务模型、交互状态图发生变化的契约使用 `schemaVersion: 3`。

## Revision And Supersession

- Schema v2/v3 必须包含 `revision` 与 `changeSet`。`revision` 记录稳定的 `REV-*`、递增序号和本轮权威业务模型摘要。
- `changeSet.supersedesRequirementIds` 与 `removedRequirementIds` 只记录已退出当前模型的旧需求 ID；这些 ID 不得继续出现在当前 Requirements、UI bindings、Acceptance 或 HTML 追踪标记中。
- `decisionSummary` 用具体业务规则说明当前方向，不使用“已优化”“已更新”等抽象句子。
- Tier 3 生成前先完成一次业务模型 Delta：确认新增、保留、替代和删除项，再修改 HTML、状态、契约和测试。方向冲突未解决时保持 `readiness: blocked`。

## Requirement To UI Mapping

- 每个关键需求必须映射到至少一个 `UI-*` binding。
- 每个关键、可交互 `SCN-*` 必须由至少一个 `TEST-*` 的具体 Step 覆盖；Schema v3 不接受只在 Scenario 顶层声明覆盖。
- 功能组件使用 `data-ui-binding-id`、`data-requirement-ids`；可操作控件再提供稳定的 `data-action-id`。
- 页面和可见业务状态分别使用 `data-screen-id` 与 `data-state-id`。
- 功能组件不得没有需求来源。纯导航、帮助或布局辅助可标记为 `supporting_ui`，但必须说明理由。
- 字段必须明确输入、只读或仅后端使用；权限必须明确 hidden、disabled、message 或 request_access；状态转换必须有用户操作或系统事件。

Schema v3 使用 `interaction.transitions` 显式声明 `pending/success/failure/cancel/recovery` 状态转换，以及 action 或 system event 触发、Guard 和 Effect 对应的需求 ID。`interaction.reset` 必须说明 `function/reload/none`、持久化边界和 DOM、URL、Scroll、Focus、Timers、Storage 的重置范围。

Schema v2/v3 的 `TEST-*` 可使用场景级 `fixture`；`function` 重置由 Demo 的 `window.__DEMO_RESET__(fixture)` 建立可重复前置状态，验证器会等待同步返回或 Promise 完成。Schema v3 的每个 Step 用 `verifiesRequirementIds` 建立真实的逐步需求覆盖，并可在 action 前后断言和截取带 `stateId` 的状态截图。步骤支持 `click`、`fill`、`select`、`toggle`、键盘、Focus/Blur、Submit、Back、Escape、Reload、Wait 和 Assert；断言覆盖 Screen、State、Feedback、可见性、可用性、Text、Value、Count、Focus、Accessible Name、Role、Checked、ARIA State、Live Region 与 URL。首次进入、取消、恢复、权限拒绝和跨对象隔离等关键路径应直接写入契约，不再依赖未声明的项目脚本准备状态。

Schema v3 的 HTML 映射采用精确闭包：契约中的 `actionId`、`UI-*` binding 与 requirement IDs 必须和对应 DOM 标记一致；不得用“元素存在”代替“这个动作由这些需求驱动”的映射证据。

## Sidecar Contract

- `prototype-contract.json` 与 HTML 分离交付；HTML 不得复制完整契约、来源、假设或未决问题。
- HTML 只保留验证所需的稳定 `data-ui-binding-id`、`data-requirement-ids`、`data-action-id`、`data-screen-id` 与 `data-state-id`。
- 不得创建 Review Bar、规格按钮、规格 Dialog、常驻面板或其他产品契约前端 Runtime。
- Product Contract 验证以命令行传入的旁路 JSON 为唯一契约来源，并将 Contract Hash 与覆盖摘要写入机器可读报告。

## Validation

明确不改变字段、状态、权限、规则、场景或 UI binding 的文案 follow-up 可使用 Tier 0 静态路径；必须声明 `--changed-aspects copy --semantic-impact none` 并提供至少一个 `--expected-copy`。任何业务语义或追踪映射变化仍升级到 `tier_3_full_delivery`。

先运行静态契约验证：

```bash
python3 scripts/validate-product-contract.py prototype-contract.json --html prototype.html --report-json product-contract-report.json
```

默认使用内置 Browser 验证主要场景和关键状态。只有用户明确要求 Strict Regression 时，才运行全部 `TEST-*` 的自动语义验证。Product Contract 已拥有交互与验收场景时，不再同时维护或传入 `experience-checks.json`：

```bash
python3 scripts/verify.py prototype.html --profile product-contract --contract prototype-contract.json --report-json validation-report.json
```

交付证据必须分别报告：关键需求映射、交互场景、状态、字段、权限、未标记假设、阻塞问题和 Contract Hash。证据来自旁路契约与验证报告，不得通过产品界面展示。默认 Interactive Demo 使用内置 Browser 验证主要场景和关键状态；只有用户明确要求 Strict Regression 时才完整自动执行全部 `TEST-*`。内置 Browser 不可用时保留静态验证并只把交互证据标为 degraded；Python Playwright 缺失本身不覆盖已完成的 Interactive Demo 结果。
