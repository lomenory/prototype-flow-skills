# App Flow Preflight

`app_flow` Tier 3 使用[移动 App 页面](page-design/app.md)决定导航、内容流、安全区域、键盘和状态反馈。结合[视觉与文案](page-design/visual.md)检查实际展示效果。用本次平台、方向与目标尺寸验证。

## 设备框与 HTML 实现

- 使用 Route 约定的设备框，检查状态栏、Dynamic Island／刘海、Home Indicator 或系统导航与主要内容的间距。检查长文本、键盘、Sheet、Dialog、Toast 出现时的操作可达性和滚动恢复。
- 将 Guidance 中的视觉方向、密度、动效落到具体组件和状态，检查内容区、主操作、关键反馈和导航锚点的可见性。App Flow 交互目标的硬门禁为 44 CSS px；HTML 文字、图标与分隔线按实际渲染核对。
- 从约定的起点操作到目标状态，按需验证等待、错误、取消和重试，核对返回层级与上下文恢复。支持外接键盘的路径按实际范围验证 Tab、Shift+Tab、Enter、Space 和 Escape。
- 核对刷新、`window.__DEMO_RESET__` 以及持久化边界。可见控件需可工作、disabled 或有范围说明。保存初始与关键结果截图，对照视觉锚点集中处理阻塞或重要问题，只复验受影响路径。设备框预览属于 HTML 证据。
