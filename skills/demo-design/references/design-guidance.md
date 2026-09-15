# Design Guidance

`web_hi_fi` 与 `app_flow` 的 Tier 3 默认执行本阶段。它不是 Delivery Route、Mode、Facet 或独立 Review；它把用户任务与设计决策连接起来，验证结果由独立报告记录。

## Generation Contract

Tier 3 生成 HTML 前，在产物目录创建旁路 `design-guidance.json`。Tier 0/1 不创建；Tier 2 只更新已有文件中的受影响字段。指导数据只供 AI 与验证器读取，不得渲染成产品内规格栏、评分面板或调试界面。

完整有效示例见 `examples/design-guidance.json`；仅在需要编写旁路文件时读取。示例由已校验 fixture 生成，根据本次真实场景替换内容，不要照搬不适用状态。

完整字段与 Rule ID 以 Runtime 随附的 `contracts/design-guidance.yaml` 为准，Validator 负责执行同一规则。Schema v1/v2 仅用于兼容旧产物；新的 Tier 3 交付使用 Schema v3。

## UX Intent Gate

- 必须明确 `primaryUser`、`primaryTask`、`successOutcome` 与有顺序的 `contentPriority`。
- Web/App Brief 中只把 `primary_user_task` 作为新增必填项。成功结果、内容优先级、关键状态与风险能够从现有需求可靠提取时直接记录；只有会改变设计时才询问。
- `primaryUser`、`primaryTask`、`successOutcome` 使用 `exact`、`approximate` 或 `assumption` 标记来源精度。
- 命中 `product_contract` 时，优先在 `value` 或决策说明中引用已有 `SCN-*`、`STATE-*`、`UI-*`；不要维护第二套场景、状态或 UI 身份。

## Direction and Visual Read

- `designBasis.type` 使用 `core | external | existing`。只有没有权威设计上下文时才使用 `core` 并从 `design-systems/index.json` 选择 `systemId`；外部设计使用 `sourceIds` 引用 `design-reference.json` 的 `DSRC-*`，已有项目使用相对 `designDocument` 指向 `DESIGN.md` 或等价 Token 入口。
- `visualDials` 明确三个任务级调节值：`variance` 控制视觉表达差异，`density` 控制信息与留白密度，`motion` 控制状态转场强度。它们用于改变实际布局、组件和状态决策，不是风格标签。
- 分别写明 Layout、Hierarchy、Responsive 与 Component strategy。为兼容 Schema 保留 `responsiveStrategy` 字段；默认写明唯一目标环境和不承诺的额外范围，不得把该字段理解为必须设计移动端。Token 不能替代任务、状态和交互决策。
- 只有用户或权威设计范围明确要求多个 Viewport、设备、平台、方向或断点时，`responsiveStrategy` 才描述对应适配规则；验证也只覆盖这些明确目标。
- `states` 只声明适用状态，不为了凑数量制造 Loading、Empty 或 Error；`required: true` 的状态必须说明可观察实现。
- `constraints.must`、`avoid` 与 `accessibility` 使用具体、可检查的语言。文字/密度相关任务在已有字段里记录正文、关键辅助内容和非关键元数据的角色、Token 与代表 selector，按 `references/quality.md` 落实；不新增一套旁路文件。
- `density` 调整布局、间距和信息组织，不代表可以缩小必要说明或把它们变淡；一屏放不下时保留可读内容并允许纵向阅读。
- `visualAnchors` 只标记主要任务区、主要动作和关键状态等少量高价值区域。每个锚点使用稳定 selector、职责、优先级与检查项；`visible`、`unique`、`no_clipping` 可由浏览器测量，`hierarchy`、`rhythm`、`state_distinct` 仍需要截图审视。

## Rule Levels

- `hardRules`：生成前的客观门禁适用性。所有 Rule ID 都必须出现；使用 `required` 或 Contract 允许的 `not_applicable`，并写清 `reason`。
- `contextual`：依赖产品与设计上下文的专业判断，例如层级、密度、布局和组件选择。
- `advisory`：非阻塞改进，例如更进一步的品牌表达或视觉节奏。

不要在 Guidance 中提前写 `passed` 或浏览器 evidence。硬门禁的 `passed`、`failed`、`not_run` 与实际证据只写入 `validation-report.json`。`authored` 规则可写 `declaration`，报告状态必须是 `declared` 而不是机器 `passed`；`experience` 规则必须由状态/交互证据满足。任何适用且必需的 `not_run` 都使 Strict Regression 不完整。不要输出总分；Contextual 与 Advisory 决策不能伪装成机器证明。

## Hard Gates

- `GUIDE-FORM-LABELS`：适用表单控件具有可访问名称。
- `GUIDE-FOCUS-VISIBILITY`：键盘可聚焦控件保留可见焦点。
- `GUIDE-TARGET-SIZE`：Web 非行内交互至少 24 CSS px；App Flow 控件至少 44 CSS px。
- `GUIDE-HORIZONTAL-OVERFLOW`：每个目标 Viewport 无意外横向溢出。
- `GUIDE-IMAGE-ALTERNATIVES`：`img` 明确提供 `alt`；装饰图使用空 `alt`。
- `GUIDE-REDUCED-MOTION`：使用 CSS Animation 时提供 `prefers-reduced-motion` fallback。
- `GUIDE-CRITICAL-STATES`：异步、破坏性、表单或数据状态有适用的 Loading、Empty、Error、Success 或恢复反馈。
- `GUIDE-COLOR-INDEPENDENCE`：重要状态或含义不只依赖颜色。
- `GUIDE-VISUAL-ANCHORS`：Schema v3 的关键视觉锚点在目标 Viewport 唯一、可见，并按声明检查裁切；层级与节奏仍通过截图人工审视。

## Bounded Rendered-quality Loop

Tier 3 在交付前执行一次有界闭环：

1. 截取初始、关键结果及适用的错误/恢复状态。
2. 对照 visual anchors 检查层级、构图、排版节奏、组件一致性、内容真实性与状态可辨识度；表单帮助/反馈、图表轴/单位和详情正文也在可读性检查范围内。
3. 只对阻塞或重要问题做一次集中修正。
4. 重跑受影响路径和截图；不形成默认无限 review-modify-review 循环。

## Delivery

- `design-guidance.json` 与 HTML 分离交付。
- `validation-report.json` 单独记录 Rule 结果、Viewport、浏览器来源和验证证据。
- Tier 3 最终回复总结 5–8 条 `decisionSummary` 中最重要的设计决定；Tier 2 只说明本次受影响的决定，Tier 0/1 简述改动与验证。不要复制完整契约。
- 验证通过只证明硬门禁和声明覆盖，不等于真实用户可用性研究或平台真机验收。
