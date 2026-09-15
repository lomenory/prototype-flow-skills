# App Flow Route

- 适用于一条可演示用户路径。
- Tier 3 必填：产品名、平台、主要用户任务、起点、触发操作和目标状态；异步或破坏性操作补充错误/取消路径。
- 默认只面向一个平台、设备框、方向和展示尺寸；不主动兼容其他手机尺寸、平板、横竖屏或 iOS/Android 双平台。
- 只有用户或权威设计范围明确包含额外设备、平台、方向或尺寸时，才生成并验证对应适配；单一目标不承诺其他环境可用。
- Tier 1 处理现有 Flow 中单一父容器内可定位的颜色、字号、间距、尺寸、排列和局部布局，不重新 Brief、选择 Design System 或创建 Guidance；默认通过 `scripts/preview-server.py` 输出的 loopback HTTP URL 使用内置 Browser 检查稳定 selector 的可见结果并生成目标截图。
- Tier 2 处理跨容器布局、受影响交互、状态和目标 Viewport；已有 Guidance 只更新受影响字段，默认通过同一 loopback HTTP transport 使用内置 Browser 验证命名 action、可观察结果和关键状态截图。
- Tier 3 生成前按 `references/design-guidance.md` 建立 UX Intent、平台设计方向、适用状态和旁路 `design-guidance.json`，并读取 `references/app-preflight.md` 完成平台化视觉与交互预检。
- iOS 使用 `assets/ios_frame.jsx`，Android 使用 `assets/android_frame.jsx`；不要重新绘制平台 Chrome。
- 使用单台目标设备和局部状态；Tier 3 的 Interactive Demo 必须从起始状态完成声明的主要任务并确认目标状态，不得用固定点击次数替代任务完成。Tier 2 验证受影响交互，Tier 1 只验证受影响目标。只有明确启用 Strict Regression 后才要求自动捕获 `pageerror`。

- 外部设计源、现有代码或组件库触发 `design_context_dependency`。
- 命中 `product_contract` 时，每个关键可交互场景必须提供可执行 `TEST-*`。
- Design Guidance 与 `product_contract` 同时使用时引用已有 `SCN-*`、`STATE-*` 与 `UI-*`，不复制业务身份。
- 组件库只约束内容区语义；平台 Chrome 和交互习惯服从目标平台。
- Web 响应式页面不属于 App Flow，改走 Web Route。
- 原型必须有可辨识 CSS fallback，CDN 失败不能白屏；`file://` 只用于用户手动打开，Browser 自动化必须使用 loopback HTTP。
- 默认把入口 HTML、CSS、JavaScript、设备框所需代码和资产放在一个独立 Demo 文件夹中；使用相对路径，整个文件夹作为 `primaryShareArtifact`，入口页面作为 `entryHtml`。发送整个文件夹，不另生成分享 HTML。
- Tier 3 检查 Demo 文件夹内入口页面的本地资源和远程依赖，并直接验证该入口。最终说明先列完整文件夹和入口，再说明打开方式，以及 `window.__DEMO_RESET__`、刷新重置和后端持久化边界。
