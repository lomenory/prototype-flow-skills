# Quality Gate

在执行 Delivery Route 前，检查设计上下文和交付风险。

## Context And Evidence

- 优先使用可检查的截图、URL、Figma、代码 Token 和现有组件。
- 命中 Design Context Facet 时读取对应 Reference，并按风险决定使用 `DESIGN.md` 或 HTML 注释；旧 `design.md` 只读兼容。
- 必要设计来源不可访问或来源冲突时停止；“直接做”不覆盖设计上下文冲突。
- 命中 `product_contract` 时，文档与对话先规范化为带来源状态的产品契约；禁止把自然语言直接翻译为功能 HTML。

## UX Intent

- Tier 3 Web/App 生成前读取 `references/design-guidance.md`，明确主要用户、主要任务、成功结果和内容优先级。
- Tier 0/1 不创建 Guidance；Tier 2 只在已有 Guidance 中更新受影响字段，不能把局部修改扩大成全页重新设计。
- Page Goal、视觉风格或 Design System 不能替代用户任务；Token 不能替代信息架构、状态和交互决策。
- 异步、破坏性、表单或数据界面只声明适用状态，不凑齐无意义的 Loading、Empty、Error 或 Success。
- 指导结论区分 Hard Gate、Contextual 与 Advisory；不使用总分制造客观性。

## Visual Quality

- 不使用未授权 Emoji、伪造数据/客户/Quote/Logo、泛紫渐变或默认 AI Homepage 结构。
- 不用内容填满空白；每个区块、组件和状态都要服务用户任务。
- 组件视觉服从权威 Design Context 或所选 Core system；组件库默认皮肤不能压过设计语言。
- 图表使用真实数据，或明确 Placeholder、Empty State 和来源状态。
- Web/App 动效只用于层级、反馈、状态变化或叙事，并提供适用的 Reduced Motion fallback。

## 文字角色与可读性

适用于新交付，以及本次涉及文字、密度或颜色的区域；不把小改扩大为全页重排。已有权威设计优先：保真任务保留指定设计并报告可读性冲突；用户要求改善可读性时，更新本次受影响的 Token 与实现。

没有权威设计约束时，采用以下设计默认值；字号是建议尺度，不是所有页面的一刀切门槛。

| 文字角色 | 默认尺度 | 用途 |
| --- | --- | --- |
| 正文、输入值、操作步骤与长说明 | 15–16 CSS px，行高约 1.5–1.7 | 能连续阅读，长内容允许自然换行 |
| 表单标签、必要帮助、状态反馈、表头/行内容、图表轴/单位/图例 | 14 CSS px 起 | 直接影响操作或判断，不能当装饰性小字 |
| 时间戳、次要来源、辅助编号等非关键元数据 | 12 CSS px 起，少量使用 | 若决定时间范围、合规边界或下一步，应提升为上一类 |

- 在 `DESIGN.md` 中定义正文、支持性文字和元数据角色，并将这些 Token 用在实际 CSS。复制 Token 文档后再为每个 selector 任意设灰色与小字号，不构成落实设计系统。
- 次要文字用语义化 `on-surface-secondary` 色，并保留足够对比。普通文字与实际背景至少 4.5:1；大字和不活跃控件等例外按 [WCAG 对比度说明](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) 判断。Placeholder 承载信息时也要可读，disabled 例外不能借给一般说明。
- 优先用间距、字重、分组和位置区分层级。不要同时减小字号、降低字重和减淡颜色来处理整片辅助内容；对比值合格也不代表截图里一定舒适可读。
- 密度过高时先缩减重复内容、调整列宽与区块布局，允许纵向滚动；不通过整页 `scale/zoom`、缩小全局字体、挤压行高或隐藏必要帮助把内容塞进首屏。
- 在目标 CSS Viewport 检查真实页面、错误/成功反馈和详情区域。看实际 computed 字号、前景/背景与截图，不只看根元素或 Token；SVG `viewBox`/transform 的缩放也可能让标注实际变小。
- 纯色可计算对比；图片、渐变、透明叠层未解析时标为未测，并用截图判断。只报告已检查文字与状态，不能用代表性抽样声明整页 WCAG 通过。

## Scope And Delivery

- 小改继承现有设计语言并复用可信验证；新交付和外部复刻按 Route 执行对应 Tier 的默认验证档位，Strict Regression 仍需用户明确要求。
- Tier 1 必须能指出现有产物、精确目标、预期结果和保护范围；任何未限定影响都升级 Tier。
- Review-only 只输出基于证据的 Findings，不创建辅助文件或静默生成 Redesign。
- 产品契约模式下，每个关键需求必须有 UI binding；功能组件必须绑定需求或明确标记为有理由的 `supporting_ui`。
- 未确认的业务行为必须标记为 assumption 或 open question，不能伪装成 confirmed。
- 未通过适用验证的产物不得表述为完成。
- Tier 3 Web/App 的 `design-guidance.json` 必须与 HTML 分离；硬门禁失败时不得表述为完成。
