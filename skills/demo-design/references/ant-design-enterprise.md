# Ant Design Enterprise Companion

`ant_design_enterprise` 是 `demo-design` 的条件 Facet，不是 Delivery Route、Mode、Core Design System 或生产代码生成器。它为企业中后台 HTML Demo 提供真实 Ant Design CDN 组件、页面组合与 `DESIGN.md` 主题适配规则。

## Activation

在以下任一条件成立时启用：

- 用户明确指定 Ant Design、antd、ProComponents、ProTable 或 ProForm。
- 用户明确要求管理后台、运营后台、中后台、后台项目、运维控制台、back-office、admin console 或 operations console；这些企业操作型上下文默认使用标准 Ant Design 组件，不要求用户再次点名 antd。
- 可检查的现有项目已经使用 Ant Design，当前 Demo 需要继承其组件语言。

普通 Dashboard，或只出现数据看板、分析页、指标、图表时，不得启用本 Facet；继续使用 `data_viz` 与现有 Dashboard/Enterprise Core system。外部截图、Figma、URL、现有代码或指定组件库同时命中时，叠加 `design_context_dependency`。

## Source and Availability

- Companion source: https://github.com/AntGroupDesign/Ant-Design-Skill
- Pinned upstream commit: `a79207836fa1e29b442cd3e88320b94e2a094da9`
- Upstream code license: MIT；设计资产、文档和指南：CC BY 4.0。

如果当前环境已提供 `ant-design-skill`，只按任务读取上游与布局、表格、列表、表单、描述列表或图表直接相关的章节和一个匹配模板；不得一次加载全部内容。若该 Skill 不可用，使用本文的稳定适配规则继续，不自动安装、不阻塞 Demo，也不得假装读取了上游内容。

## Ownership

| Concern | Owner |
| --- | --- |
| Request Intent、Execution Tier、Delivery Route 与授权 | `demo-design` |
| HTML Demo 交付形态、可携带性和浏览器证据 | `demo-design` |
| 用户任务、信息优先级与设计决策 | `design-guidance.json` |
| 数据来源、单位、口径、Loading/Empty/Error 与图表真实性 | `data_viz` |
| 产品场景、字段、状态、权限与 UI binding | `product_contract` |
| 视觉 Token 与皮肤 | 权威设计源或项目 `DESIGN.md` |
| 固定 CDN 版本与 fallback | `contracts/dependencies.yaml` |
| 中后台导航、筛选、KPI、表格、列表、表单和详情组合 | `ant_design_enterprise` |

Ant Design 组件负责企业控件语义、交互状态与实现词汇，但不拥有视觉皮肤。颜色、字体、圆角、间距、密度、页面布局和图表主题仍服从权威设计源或项目 `DESIGN.md`。

## Demo Runtime

新建且命中本 Facet 的 Demo 使用 `references/dependencies.md` 中固定的 React 18.3.1、dayjs 1.11.18、Ant Design 6.6.0 UMD、匹配版本 reset CSS 与可选 ECharts 5.6.0。HTML 中按以下依赖关系加载：

1. 在 `<head>` 加载 Ant Design reset CSS，并声明 `plain_html_css` fallback。
2. 依次加载 React、ReactDOM、dayjs、`antd.min.js`；Babel Standalone 在需要浏览器 JSX 时加载，ECharts 只在 `data_viz` 命中时加载。
3. 读取 `window.antd` 后再解构组件并渲染；初始化失败时不得继续调用未定义组件。
4. 远程依赖按 `references/dependencies.md` 声明 fallback，不自动安装、不使用 `latest` 或版本区间。

完整 UMD 只适用于 HTML Demo 的可移植交付取舍，不代表生产项目的依赖建议。现有 Ant Design 项目继承其已验证版本与公开 API；如果与固定 Runtime 不兼容，触发 `ant_design_runtime_version_conflict`，不得静默升级项目。

## DESIGN.md Token Adapter

`DESIGN.md` 是规范输入，Ant Design 主题是派生实现。生成时建立单一 Token Adapter，并保持以下映射：

| DESIGN.md | Ant Design 6 | 其他消费者 |
| --- | --- | --- |
| `colors` | `ConfigProvider.theme.token` 中的 primary、text、background、border、success、warning、error | 页面壳 CSS 与 ECharts palette |
| `typography` | `fontFamily`、`fontSize`、`lineHeight`、`fontWeightStrong` | 页面标题、图表标签、表格外说明 |
| `rounded`、`spacing` | 全局 radius、control height，以及明确的组件间距 | Grid、section、KPI 与页面 padding |
| `components` | `ConfigProvider.theme.components` 与组件公开的 `styles`/`classNames` 语义区域 | 必要的 wrapper class |

- 使用一个根级 `ConfigProvider`；全局 Token 与组件 Token 都从同一份解析后的 `DESIGN.md` 值派生。
- 动态 Token 是默认模式。首阶段不启用 `zeroRuntime`，也不加载完整 `antd.css`；只有明确的性能或离线目标并完成 CSS layer 验证后才可评估。
- 页面壳、跨组件布局、KPI 和图表不是 Ant Design Token 的隐式责任，必须显式复用相同规范值。
- 优先使用 Token、组件 Token 及公开 `styles`/`classNames`；不得把内部 DOM 层级、生成的哈希 class 或大范围 `.ant-*` 覆盖当成稳定接口。
- `message`、`notification`、`Modal` 等反馈使用根级 `App`、Hooks 或受同一主题上下文管理的 holder，避免静态调用脱离主题。
- 在项目 `DESIGN.md` 的 `Component Library Constraints` 中记录固定版本、主题入口、允许组件、Token 映射和 fallback；视觉来源冲突时仍以高优先级设计上下文为准。

## Translation Boundary

上游 React 19、ProComponents、Ant Design Charts、全局 CSS 和 TSX 模板只作为结构参考：

- 不复制上游 TSX 模板作为 Demo 入口。
- 不新增 React 19、ProComponents 或 Ant Design Charts Runtime 依赖；显式图标包也必须先进入固定依赖契约并与 Ant Design 6 匹配。
- 不直接引入上游模板全局 CSS；除固定 reset 外，把实际需要的布局、密度和状态规则放入当前 HTML/CSS/JS。
- 不因模板使用某个组件而改变用户指定的视觉来源、业务状态或交付范围。
- 用户要求生产级 React/Ant Design 实现时，退出 `demo-design` 交付边界；该任务应由 Ant Design Skill 或生产代码工作流独立负责。

## Selective Pattern Guidance

### Page shell

- 新建系统可从 Side、Top、Mixed 三种导航中选择一种；现有项目必须复用已有 Layout、导航和路由壳。
- 页面标题只保留一个来源。标题、全局操作、筛选区和业务内容使用稳定对齐线，避免重复 padding。
- 信息层级依靠分组、对齐、密度和状态，不依靠装饰性渐变、光效或营销式 Hero。

### Enterprise dashboard

推荐顺序为：Page Header → 可选筛选/口径区 → KPI Grid → 主图表或图表 Grid → 明细表格。只有真实业务需要的区块才出现：

- KPI 卡回答不同问题并公开口径或新鲜度；同组等高，少量 KPI 不横向拉满。
- 完整趋势图与 KPI mini chart 分开；需要坐标轴、图例、告警线或长时间范围时使用独立图表区块。
- 主图表承担主要决策信号，明细追踪使用表格或列表，不强行图表化。
- 页面级时间范围、筛选口径与数据状态保持单一、可见且一致。

### Tables, forms, lists, and details

- 表格声明排序、筛选、分页、选择、批量操作、溢出以及 Loading/Empty/Error 行为。
- 筛选条件一次性提交时使用查询筛选模式；即时生效与提交查询不得混在同一区域。
- 表单把校验放在受影响字段附近；长流程只有在业务步骤真实存在时才使用 Steps。
- 列表和详情页保留状态、权限、操作作用域与返回路径；破坏性操作明确影响数量、后果和恢复方式。

## Conflict and Fallback

- 权威设计源与 Ant Design 视觉建议冲突时，权威设计源优先；只保留不冲突的组件语义。
- 现有项目版本与上游模板版本冲突时，继承项目版本和公开 API，不升级 Demo Runtime。
- CDN 组件不可用时，使用契约声明的 `documented_component_vocabulary` 或 `plain_html_css` fallback，并清楚显示加载失败状态；不得伪装成已运行 Ant Design 组件。
- 上游 Skill 不可用时，继续使用本文、`references/design-context.md`、`references/modes.md` 和所选 Core system，不自动安装。
- 无明确 Ant Design 或企业后台信号时，不读取本文、不选择 Ant Design 组件，也不记录其为设计假设。

本文只记录来源和适配规则，没有复制上游模板、设计资产或大段文档。未来若引入实质性上游内容，必须保留来源、固定 revision、许可证归属与修改说明。
