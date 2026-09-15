# Web Pre-flight：Web 高保真交付前机械检查

## Purpose

Web Pre-flight 是 Web hi-fi 页面交付前的最后一遍机械扫雷。它专门捕捉常见 AI 页面问题：hero 过载、三卡片重复、紫色渐变、CTA 换行、nested cards、假产品 UI（fake product UI）和装饰状态点；只有明确多 Viewport 范围时才检查移动端或断点适配。

它只适用于 Web hi-fi、landing、homepage、pricing、login、dashboard、docs、settings 等正常浏览器页面。不要把它硬套到 App 设备框或 Review-only 工作。

## 使用方式

在完成 HTML 后、最终回复前：

1. Tier 3 使用本文件全部检查；Tier 1/2 只检查受变更影响的章节。
2. 先按 `references/verification.md` 运行对应 Tier 验证。
3. 再完成适用的 Web 页面机械检查。
4. 任一适用高风险项失败，先修再交付。

Tier 1 默认检查精确目标、可见预期结果、目标截图、未授权 Emoji，以及变更维度直接影响的 Color、Typography、Component、Motion 或 Responsive 条目。Tier 2 追加所有受影响 Viewport、交互和布局章节。只有用户明确启用 Strict Regression 后才要求自动捕获 Console/Page Error；局部验证不得表述为全页审计。

## Hero Checks

- Hero 在 1366×768 或小笔记本首屏内能看到核心标题、说明和主 CTA。
- H1 在 desktop 不应变成 4 行以上。长文案先改短，其次调宽容器和字号。
- Hero 不同时塞入 eyebrow、长标题、长副标题、两个 CTA、trust strip、logo wall、stats、badge 和产品卡片。
- Logo wall 或 “Trusted by” 应放在 hero 下方独立区域，不塞进首屏主叙事。
- 不使用 `Scroll`、`Scroll to explore`、鼠标滚轮图标等滚动提示。
- 不用装饰性版本号、build number、invite-only、locale/time/weather strip，除非它是真实产品状态或场景事实。
- Web 页面首屏必须是页面本体，不默认包进浏览器窗口壳、Mac 窗口壳或 mockup 画板。

## CTA And Form Checks

- Primary CTA 在 desktop 上不换行。
- 同一转化意图只用一个稳定 label。例如 `Start free` 和 `Get started` 不要在同页混用成两个意图相同的 CTA。
- 按钮文字和背景有足够对比度，不出现白底白字、透明按钮无边框、图片背景上文字不可读。
- 表单 label 在输入框上方，不用 placeholder 代替 label。
- 表单至少考虑 default、focus、disabled、error、loading 或提交中状态中与任务相关的状态。
- 错误信息直接、清楚，不用 `Oops!` 之类空泛语气。

## Layout Repetition Checks

- 不连续出现 3 个以上 image/text zigzag section。
- 同一页面不要多个 section 使用完全相同的 layout family。
- 8 个 section 的页面至少有 4 种布局节奏。
- 三等分 feature card row 不是默认答案；需要它时必须有内容理由。
- Bento grid 的 cell 数量等于真实内容数量，不出现空格子或为了凑版式硬造内容。
- 长列表不要默认每行上下都加边框；选择 top group border 或 row divider 之一。

## Typography Checks

- 按 `references/quality.md` 的文字角色检查实际 CSS：标签、必要帮助、错误反馈和下一步都属于任务内容，不把它们统一降为小而淡的元数据。
- 正文与支持性文字分别绑定 DESIGN Token；检查真实输入值、Placeholder、错误/成功状态，不能只检查标题。
- 字号增大后同步检查换行、控件高度、列宽与纵向流；不为维持首屏高度缩小整页。

- Display 字体来自 `DESIGN.md`（或旧 `design.md`）、brand 或选定 design system；没有依据时不要默认 Inter/Roboto/Arial 做大标题。
- 大标题行高不会裁切 italic、中文或 descender。
- 正文宽度受控，长段落不超过约 65ch。
- 小 uppercase eyebrow 不要每个 section 都用；最多约每 3 个 section 出现 1 次。
- 不用 `SECTION 01`、`QUESTION 05`、`PHASE 01` 这类装饰编号当 section 标签。
- 页面可见文案避免 AI 常见空话，如 “Elevate”、“Unleash”、“Next-Gen”、“Seamless”。

## Color And Theme Checks

- 全页保持一个主主题，不无理由在中途突然从浅色跳到深色或反过来。
- Accent 色一致，不同 section 不随机换蓝、紫、绿、玫红。
- 不默认使用 AI 紫蓝渐变、霓虹深蓝背景、玻璃拟态堆叠。
- Premium consumer 任务不默认使用米色 + 黄铜 + espresso 黑，除非设计上下文支持。
- 纯黑 `#000000` 不作为大面积默认背景；用有控制的 near-black 或品牌色。
- 渐变、纹理、噪点要服务层级或品牌，不当作万能高级感。

## Component And Container Checks

- 不出现 cards inside cards inside outer rounded panel 的嵌套容器。
- 卡片只在表达层级或分组时使用；能用留白和分割线解决时不要滥用卡片。
- 圆角系统一致。按钮、卡片、输入框的 radius 有明确规则。
- 阴影方向和色调一致，不用默认纯黑大阴影。
- 图标来自同一套 icon vocabulary，不混用多套风格。
- 不用 emoji 做图标、feature bullet、CTA 或装饰，除非按 `SKILL.md` 明确允许。

## Image And Product UI Checks

- 品牌或产品页面优先使用真实 logo、产品图、UI 截图。
- 不用 CSS 剪影、手画 SVG 或假 div UI 冒充产品截图。
- Hero 中的 fake dashboard、fake terminal、fake task list 只有在明确是概念占位时才允许，并必须诚实标注。
- 图片上的装饰性 pill label、假摄影编号、假 field note 不默认使用。
- 图片有语义时必须有合理 alt text。

## Motion Checks

- 每个动效能说明目的：层级、叙事、反馈、状态变化。
- 不用 `top`、`left`、`width`、`height` 做高频动画；优先 transform 和 opacity。
- 使用 scroll、pinned、marquee 或持续动效时，必须有 reduced-motion fallback。
- 同页 marquee 不超过一个，除非 brief 明确要求 motion-heavy。
- Hover 和 active 反馈存在，但不要导致布局跳动。

## Conditional Responsive Checks

仅当用户或权威设计范围明确要求移动端、多个 Viewport 或断点适配时执行本节；默认单一目标交付跳过本节，也不声明其他尺寸可用。

- 多列布局在 `< 768px` 有明确单列或可用折叠策略。
- 移动端正文至少 16px。
- 点击目标至少 44×44px。
- 页面不出现横向滚动条，除非是明确设计的横向画廊并有可用提示。
- Hero 在移动端不被超大字号、固定高度或绝对定位挤坏。
- 使用 `min-height: 100dvh` 优先于 `h-screen` / `100vh` hero。

## Final Mechanical Sweep

交付前至少问自己：

- 这页看起来像当前 brief，而不是通用 AI landing page 吗？
- 是否有真实 context 或诚实 placeholder？
- 是否有未授权 emoji？
- 是否有 CTA 看不清或换行？
- 是否有重复 section 节奏？
- 是否有 nested cards？
- 是否有假产品 UI 冒充真实截图？
- 若明确要求多 Viewport，所有目标是否都可用？
- 是否已经按 `references/verification.md` 运行对应 tier 验证？

如果有一项不能诚实回答为“是/无问题”，先修再交付。
