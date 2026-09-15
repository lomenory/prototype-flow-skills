# Experience Checks

`experience-checks.json` 是 Tier 2/3 交互 Demo 的轻量旁路验收文件。它不复制业务模型，也不进入产品 UI；只有命中 `product_contract` 时才改用更完整的 `prototype-contract.json`。

## When to Create

- Tier 2 修改导航、状态或交互，且一次 action/result selector 不能充分证明行为时创建或更新。
- Tier 3 Web/App 存在交互时创建。
- 纯静态页面、Tier 0/1 和 Review-only 不创建。
- Product Contract 已覆盖相同路径时不再维护 Experience Checks；复用 `TEST-*`。

## Contract

完整有效示例见 `examples/experience-checks.json`；仅在需要编写旁路文件时读取。示例由已校验 fixture 生成，根据本次真实场景替换内容，不要照搬不适用状态。

## Coverage Rules

- `primary | error | cancel | recovery` 每一种都必须出现在 `required` 或带理由的 `notApplicable`，且 `primary` 永远必需。
- 每个 required path 至少一个 Scenario；不得用同一个最终 selector 冒充所有中间反馈。
- 每一步都有稳定 `STEP-*`、一个 action、eventual expectations 和状态截图。
- `click/fill/select/toggle/focus/blur/submit` 优先使用唯一 `data-action-id`；只有不对应控件的结构性断言才使用 selector。
- 所有看起来可交互的 HTML 控件都必须具有稳定 `data-action-id` 并被至少一个步骤覆盖、明确 disabled，或使用 `data-demo-scope="out-of-scope"` 和 `data-demo-scope-reason` 说明边界。

## State and Reset

- 多 Scenario 默认使用 `window.__DEMO_RESET__`；验证器等待同步或 Promise 返回后再检查 DOM、URL、Scroll、Focus、Timers 与 Storage 的声明范围。
- `reload` 只适用于刷新确实定义为重置的 Demo；`none` 只允许单 Scenario 且 `betweenScenarios: false`。
- `persistence` 明确为 `none | session | local | documented`，不得把刷新后偶然保留误报为后端持久化。
- `timeoutMs` 只用于真实异步反馈；不要用长等待掩盖不稳定交互。

## Evidence

Strict Regression 报告每一步 action、expected、actual、timing、status 和 screenshot。默认 Interactive Demo 由内置 Browser 按同一 Sidecar 执行主要路径和适用的错误/恢复路径，并只报告实际观察到的证据。
