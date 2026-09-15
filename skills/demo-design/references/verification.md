# Verification

Tier 0/1 使用 `references/quick-patch.md`；Tier 2/3 读取 `references/routing-contract.md` 并选择 Execution Tier，再选择验证档位。Tier 决定范围和证据深度，不决定浏览器引擎。

- `static_only`：Tier 0 或 Review 默认；不打开浏览器。
- `interactive_demo`：Tier 1/2/3 Web/App 默认；本地 HTML 先由 `scripts/preview-server.py` 通过 loopback HTTP 提供，再使用 Codex 内置 Browser 验证界面和主要交互。
- `strict_regression`：仅在用户明确要求自动化回归、完整场景、错误捕获、像素 Diff、CI 或无人值守证据时启用；运行 `scripts/verify.py`。

任何档位都不得在生成流程中安装 Playwright、Chromium 或其他依赖。Python Playwright 缺失不影响已经由内置 Browser 完成的 Interactive Demo 验收，也不得把 `strict_regression: not_requested` 表述为 degraded。

## Local Preview Transport

内置 Browser 的自动化表面不得导航或读取 `file://`。本地 Demo 使用以下流程：

1. 以包含 HTML 和相对资源的最小公共目录作为 root，运行 `python3 scripts/preview-server.py --root <demo-root> --entry <relative-html>`。
2. 读取脚本首行 JSON 中的 `url`；它必须是 `http://127.0.0.1:<random-port>/...`。
3. Browser 只打开该 URL，并按当前 Tier 验证可见状态、命名交互、可观察结果与截图。
4. 验证结束立即停止预览服务。不得为了 Browser 验证监听 `0.0.0.0`、局域网地址或公网地址。

`file://` 仍可作为用户手动打开方式和离线可携带性检查入口，但不构成 Browser 自动化证据。不得尝试 Raw CDP、其他浏览器表面、`data:` URL 或间接执行来绕过 URL 安全策略。预览服务无法启动、URL 无法访问或 Browser 不可用时，保留静态证据并报告 `interactive_demo: degraded`；不自动进入 Strict Regression。

| Tier | Default profile | Minimum evidence |
| --- | --- | --- |
| `tier_0_text_copy_only` | `static_only` | 目标文案、静态扫描、未授权 Emoji |
| `tier_1_local_ui_patch` | `interactive_demo` | 一个相关 Viewport、目标可见、预期结果、目标截图 |
| `tier_2_layout_or_interaction` | `interactive_demo` | 受影响 Viewport/状态、命名交互、可观察结果；多步交互使用 Experience Checks 与关键状态截图 |
| `tier_3_full_delivery` | `interactive_demo` | 主要用户路径、适用的错误/取消/恢复路径、关键状态与截图、资源可携带性、适用的主要产品场景 |

## Default Interactive Demo

需要浏览器操作且当前会话列出 Browser skill 时，先读取并使用 `browser:control-in-app-browser`。它是浏览器执行表面，不改变 `demo-design` 对 Route、Tier、产品契约和交付范围的所有权；本地页面仍必须经上述 loopback HTTP transport 打开。

### Common flow

1. 先整理最终 Demo 文件夹：入口 HTML 位于根目录，CSS、JavaScript、图片等资源位于该目录或其子目录，全部使用相对路径。以该文件夹启动预览服务，Browser 打开最终入口的本地 URL，不为此安装依赖。
2. 使用 Brief 声明的唯一目标 Viewport；Web 未指定时为 1440×900，App Flow 使用唯一平台、设备框、方向和尺寸。
3. 确认初始界面可见、不是白屏，主要内容和关键入口存在。
4. 按 Tier 执行受影响交互或主要用户路径，检查可观察结果。
5. 在初始状态和关键结果状态保留截图；只增加明确要求的额外 Viewport 或状态。
6. 运行适用的依赖无关静态 Validator；资源变化或 Tier 3 默认检查文件夹内入口与已识别资源引用。发送的文件夹必须与浏览器验收的目录内容一致；修改页面、移动入口或调整资源路径后，重验受影响路径，不另生成分享 HTML。
7. 报告实际观察到的状态和证据，不推断未检查能力。

### Tier and route evidence

- Tier 1：检查目标 selector 的可见结果和一张目标截图；交互只有在本次修改影响交互时执行。
- Tier 2：执行命名 action，检查结果 selector、目标状态或反馈，并截取关键状态。
- Tier 3 Web：执行主要用户任务，从入口走到成功结果；只验证 Brief 声明的目标 Viewport。
- Tier 3 App Flow：从起始状态完成一个声明的主要任务，检查适用的 cancel/back/error/recovery、目标状态，以及设备框与内容不重叠；不得用固定点击次数代替任务完成。
- Review：已有截图、渲染或可静态检查代码时保持 `static_only`；URL 或动态页面需要可见证据时可使用 Browser，但不自动升级为 Strict Regression。
- Data Viz：观察非零容器、主要数据状态、Resize 后可见结果、Tooltip/Legend/Axis 遮挡和不依赖颜色的区分。
- Product Contract：先静态验证 Schema、来源、ID、关键映射和阻塞问题；Browser 默认执行主要场景与关键状态。完整自动执行全部 `TEST-*` 属于 Strict Regression。
- Experience Checks：Tier 2 多步交互与 Tier 3 非 Product Contract 的交互 Demo，先检查 `primary/error/cancel/recovery` 覆盖、重置边界和 HTML 控件闭包，再按 Step 记录 action、expected、actual、timing 与状态截图。
- Design Guidance：对适用规则记录 Browser 实际观察到的可见标签、焦点、目标尺寸、Overflow、图片替代文本和 Reduced Motion 结果；无法从当前 Browser 证明的规则写 `not_run`。
- 外部设计源：使用相同目标 Viewport 截图并对照 Design Reference 做人工可见比较；声明 `STATE-*` 时必须从 Experience Checks 或 Product Contract 的具体 Step 取得状态截图。只有用户明确要求像素级结论时才运行 Strict Regression，对默认状态与每个声明状态分别 PNG Diff；有界 region/mask 必须记录实际 selector 几何，不能静默忽略。

### 可读性证据

新交付或文字/颜色/密度发生变化时，在受影响的关键区域抽取正文、标签、必要帮助/反馈和单位等代表样本，记录 selector、文字角色、实际 computed 字号/字重、前景色与可确定的背景，并与 `DESIGN.md` 和 `references/quality.md` 对照。已有报告可放入 `readabilityObservations`，不引入新的必填 Schema。

先确认实际 CSS Viewport；截图像素、DPR 或浏览器缩放不能替代字号证据。SVG 文本还检查最终显示尺度。能解析纯色背景时计算对比；背景无法可靠解析时记录 unknown，不推断通过。保留初始和受影响关键状态的截图，检查增大字体后是否挤压标签、换行、图表或操作区域。只说明抽样范围，不把代表性检查说成全页无障碍认证。

### Interactive result states

- `interactive_demo: passed`：声明范围内的主要路径、目标状态和截图证据已完成。
- `interactive_demo: failed`：观察到界面、交互或目标状态不符合预期。
- `interactive_demo: degraded`：内置 Browser 不可用，或关键交互无法执行；保留静态证据并明确未运行项。
- `strict_regression: not_requested`：默认状态，不是降级。

如果创建或更新 `validation-report.json`，至少记录 `primaryShareArtifact`（Demo 文件夹名）、`entryHtml`（入口相对路径）、入口文件 Hash，以及 `verificationProfile: interactive_demo`、Browser surface、`navigationTransport: loopback_http`、预览 URL 的 origin（不得记录本地绝对文件路径）、目标 Viewport、已执行路径/动作、可观察结果、截图路径、未运行检查，以及 `strictRegression: not_requested`。不得声称未捕获的 Console/Page Error、请求失败、完整 `TEST-*` 或像素 Diff 已通过。

## 适用的静态校验

仅运行本次产物涉及的检查；命令中的文件路径替换为实际路径。

```bash
python3 scripts/validate-design-systems.py DESIGN.md
python3 scripts/validate-design-guidance.py design-guidance.json
python3 scripts/validate-experience-checks.py experience-checks.json --html prototype.html
python3 scripts/validate-product-contract.py prototype-contract.json --html prototype.html
python3 scripts/validate-design-reference.py design-reference.json --html prototype.html
python3 scripts/validate-portability.py demo/prototype.html --report-json portability-report.json
```

交付格式固定为 `project_bundle`，无需格式选项。`primaryShareArtifact` 是完整 Demo 文件夹，`entryHtml` 是根目录中的入口页面，`shareBoundary` 是资源边界。`requiredFiles` 列出入口和静态扫描已识别的本地资源引用，不是可裁剪文件夹的完整依赖证明；JavaScript 动态资源与模块链路还需主要路径的浏览器证据。发送时保留整个文件夹及子目录，不只发送入口 HTML。

本地 CSS、JavaScript、图片和字体允许分文件；已识别引用缺失、绝对路径或越出 Demo 根目录时失败。固定 CDN 仍按依赖契约与 fallback 规则处理，交付说明必须明确联网要求；文件夹交付不自动保证离线可用。普通页面可手动打开入口，需要模块或 HTTP 加载的页面应提供预览服务打开方式。

## 按需严格回归

只有明确要求严格回归证据时才读 `references/strict-regression.md`。默认流程不加载其命令和环境探测。
