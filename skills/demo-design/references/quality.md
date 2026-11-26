# Demo 设计质量

按本次 Tier 和受影响区域选择检查。已有设计依据、截图和验收证据仍适用时直接复用。

## 设计和视觉检查

- 新页面或主要改版按[任务与设计依据](page-design/decisions.md)确定优先级。在已有产品中修改局部时继承原有设计语言。
- 读取[视觉与文案](page-design/visual.md)中适用的文字角色、配色、对齐、组件几何、文案与动效规则。Web 实现中的 CSS 尺度和可读性参考见 [Web 页面](page-design/web.md)；App Flow 的平台布局见[移动 App 页面](page-design/app.md)。把文本与颜色角色落实到实际 CSS。截图中的表单帮助、状态反馈、图表单位和详情正文应易读。
- 新交付使用已授权素材、可辨认的占位或空态。UI 默认无 emoji。按组件角色表达分组、操作和状态；一般风格偏好属于 Contextual 或 Advisory。
- 按[第一眼检查](page-design/visual.md#第一眼检查)审视当前状态的视觉重心，对照 HTML 中声明的 visual anchors 看可见性和裁切。检查文本对比时，区分已测的实际背景与需要视觉判断的情况。抽样结果只说明对应区域。

## Demo 的契约与证据

- Tier 3 Web/App 按 `references/design-guidance.md` 创建独立的 `design-guidance.json`，记录用户、任务、成功结果、必要状态和约束；Tier 2 只更新已有的相关字段。Tier 0/1 使用快路径。
- 命中外部设计时按 `references/design-context.md` 确定来源、组件映射与 `DESIGN.md`；必要来源冲突或不可用时明确受影响部分。产品契约模式使用已有业务语义和 UI binding，标记未确认的假设与有理由的 `supporting_ui`。
- 按 Route 使用适用的验证档位。Hard Rule 结果据实写入验证报告；静态 Review 保持只读，直接指出可见问题与影响。Strict Regression 按用户的明确要求启用。
