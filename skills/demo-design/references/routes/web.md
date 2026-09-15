# Web Hi-Fi Route

交付普通、可滚动的浏览器页面；默认不是设备框、浏览器壳、Showcase Grid 或截图画板。

- Tier 3 Brief 必须明确页面目标、受众、主要用户任务、内容范围和 `viewport_strategy`。未指定时直接采用单一 `1440x900` 目标，不为默认交付追问移动端或断点策略。
- 只有用户或权威设计范围明确包含额外 Viewport、移动端或断点时，才生成对应适配并把它们纳入验证；单一目标不承诺其他尺寸可用。
- Tier 1 处理现有页面中单一父容器内可定位的颜色、字号、间距、尺寸、排列和局部布局，不重新 Brief、选择 Design System 或创建 Guidance；默认通过 `scripts/preview-server.py` 输出的 loopback HTTP URL 使用内置 Browser 检查稳定 selector 的可见结果并生成目标截图。
- Tier 2 处理跨容器布局、响应式、交互、状态与受影响 Viewport；已有 Guidance 只更新受影响字段，默认通过同一 loopback HTTP transport 使用内置 Browser 验证命名 action、可观察结果和关键状态截图。
- Tier 3 生成前按 `references/design-guidance.md` 建立 UX Intent、内容优先级、设计方向和旁路 `design-guidance.json`。
- 外部截图、URL、Figma、现有页面或组件库触发 `design_context_dependency`；其布局、Token、Typography、组件和禁区优先于通用系统。
- 命中 `product_contract` 时，页面中的功能组件必须绑定 `UI-*` 与需求 ID；关键交互提供稳定 `data-action-id` 和可观察结果。
- 无 Context 的高风险任务先给方向或局部示例；用户明确直接做时记录 assumptions。
- 使用 `references/dependencies.md` 的固定版本和 fallback；不让 CDN 默认皮肤决定设计语言。
- 默认把入口 HTML、CSS、JavaScript 和所需资产放在一个独立 Demo 文件夹中；使用相对路径，整个文件夹作为 `primaryShareArtifact`，入口页面作为 `entryHtml`。发送整个文件夹，不另生成分享 HTML。
- Tier 3 交付按 `references/verification.md` 通过 loopback HTTP 执行主要用户路径的 Interactive Demo 验收，并静态检查文件夹内入口页面的资源引用；`file://` 仅作为用户手动打开方式，不用于 Browser 自动化。浏览器直接验证最终文件夹内的入口。最终说明先列 Demo 文件夹与入口，再说明打开方式和状态或持久化边界。
- Tier 3 生成后执行完整 `references/web-preflight.md`；Tier 1/2 只执行其中与变更范围相关的检查，再按 `references/verification.md` 验证。
