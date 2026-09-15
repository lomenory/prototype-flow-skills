<!-- generated-from: contracts/*.yaml; contract-hash: e0a96def6e9c; do-not-edit -->
# 局部修改快路径

只适用于已定位的 Tier 0 文案或 Tier 1 单父容器视觉修改。Review-only 读 `references/routes/review.md` 与 `references/quality.md`。这里只继承已有页面、组件与设计语言，不读取完整 Route、Brief Gate、设计系统或严格回归说明。

## 授权与定位

- 分析/检查只读；给方案后停止。修改必须由当前请求明确授权，方案认可不构成实施授权，Git 操作另行授权。
- 先看现有文件与差异，确认目标、期望结果和受保护范围；能从上下文取得的信息不重复询问。

| Tier | Required Fields | 默认验证 |
| --- | --- | --- |
| `tier_0_text_copy_only` | `inspectable_artifact`、`exact_target`、`requested_change`、`semantic_impact` | `static_only` |
| `tier_1_local_ui_patch` | `inspectable_artifact`、`exact_target`、`target_selectors`、`requested_change`、`expected_result`、`protected_scope` | `interactive_demo` |

## 执行

1. Tier 0 只改不影响产品语义的文案。Tier 1 只改一个父容器内可定位的颜色、字号、间距、尺寸、排列或局部布局。
2. 直接修改 Demo 文件夹内的入口或资源；不生成另一份分享文件，不扩展 Viewport，不新增 Guidance/Design Reference，不因旧辅助文件缺失重做页面。
3. Tier 0 核对预期文案和差异即可，不启动浏览器。已有 Product Contract 时保留 ID/映射；语义影响无法排除就升级。
4. Tier 1 用 `python3 scripts/preview-server.py --root <demo-root> --entry <relative-html>`，读取首行 JSON `url`。内置 Browser 只打开其 loopback HTTP 地址，在一个相关 Viewport 检查目标可见、预期结果和目标截图；结束停止服务。`file://` 仅供人工打开，不绕过 URL 策略，不安装依赖。Browser 不可用只降级交互证据。
5. 最终一段说明实际改动、文件夹/入口和已完成验证；不强制列 5–8 条设计决定，不重复未变的打开方式和边界。

## 升级

- 跨父容器、多个独立区域、响应式、交互/状态或资源路径变化至少 Tier 2；再读 `references/routing-contract.md`。
- 主要任务、信息架构、设计语言、业务状态/权限/需求绑定变化，外部高保真复刻，或有界定位后仍无法限定范围，进入 Tier 3。
- 只有明确要求严格回归证据时才读 `references/strict-regression.md`；默认 `strict_regression: not_requested` 不是降级。
