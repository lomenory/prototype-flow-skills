# Design Context

当截图、URL、Figma、现有代码、现有页面或指定组件库会约束设计时使用本文件。

## Source Priority

按以下顺序确定权威来源：

1. 用户明确指定的目标截图、URL、Figma 节点或设计稿。
2. 当前代码库的 Token、组件、主题和同类页面。
3. 用户提供的 Design System、组件库或品牌规范。
4. 用户明确指定的参考产品。
5. 无上下文时，从 Core Design Systems 选择一个方向并记录 assumption。

冲突会改变视觉语言、组件接口或交付范围时停止询问；低影响差异记录为 assumption。

## Extraction

只提取会影响产物的内容：页面目标和信息架构；Color、Typography、Spacing、Grid、Radius、Border、Shadow；Component vocabulary、交互状态和响应式行为；内容语气、禁止修改项和 fallback。

提取精度标记为 `exact`、`approximate` 或 `assumption`。不要为了达到固定数量读取文件；优先读取主题入口、Token、代表组件和最接近的页面。

## Structured External Reference

外部复刻或明确要求还原度验证的 Tier 3 任务，在产物目录创建 `design-reference.json`，并按 Runtime 中的 `contracts/design-reference.schema.json` 填写：

- `sources`：精确的 Figma File/Page/Frame/Node、URL、截图或仓库来源，包含目标 Viewport 与 `deviceScaleFactor`。
- `componentMappings`：来源组件、Variant、Demo 实现 selector 与 `exact`/`approximate`/`assumption`。新建旁路使用 Schema v2；每个 `implementationSelector` 必须是唯一的稳定 `#id` 或 `[data-*=value]`，带 `sourceVariant` 时还必须提供唯一 `implementationStateId`。
- `referenceScreenshots`：项目相对 PNG 路径、Viewport 和可选 `STATE-*`。Schema v2 完成态至少包含一张默认状态截图；Variant 或关键状态使用 `stateId` 与 Experience Checks / Product Contract 的逐步状态截图关联。用户明确要求像素级结论时，Strict Regression 会对默认状态和每个声明状态分别 Diff；它不替代组件/行为验证。
- `referenceScreenshots[].comparison`：只有确有动态内容或只需比较稳定组件区域时使用。`regionSelector` 限定一个唯一可见区域；`maskSelectors` 最多 8 个且每个必须唯一可见。不得用大范围 Mask 隐藏布局或视觉偏差。
- `acquisition`：`complete`、`partial` 或 `blocked`，以及已完成、待读取节点和说明。

Figma 父级或 Section 返回稀疏内容时，不把空摘要当成完整设计上下文：先把已取得的子节点写入 `completedNodeIds`，把仍需逐个读取的节点写入 `pendingNodeIds`，保存 `partial` 后继续。恢复任务时先读该清单；存在待处理节点时不得将获取状态改为 `complete`。Tier 0/1 有界修改继续直接继承现有设计语言，不创建、刷新或验证此旁路产物。Schema v1 仅用于读取旧产物；新增或刷新外部设计证据时使用 v2，并以 `--html` 校验实现映射。

## DESIGN.md

外部设计源或中高风险多文件交付必须在产物目录创建大写 `DESIGN.md`。单文件低风险 Demo 可在 HTML 中写 `Design Context` 注释；Review-only 不创建文件。

新文件使用 DESIGN.md alpha 兼容子集：

- 首个 `---` 区块是 JSON-compatible YAML front matter，包含 `version`、`name`、`description`、`colors`、`typography`、`rounded`、`spacing` 与 `components`。
- Token 是规范值；正文解释为什么使用这些值、何时使用、以及不能如何使用。
- Component 中的 `{colors.primary}` 等引用必须可解析；前景/背景组合至少满足 WCAG AA 4.5:1。
- 正文章节依次为 `Overview`、`Colors`、`Typography`、`Layout`、`Elevation & Depth`、`Shapes`、`Components`、`Do's and Don'ts`。
- 项目可在标准章节后追加 `Sources and Provenance`、`Responsive Behavior`、`Interaction and Motion`、`Component Library Constraints`、`Assumptions and Open Questions`。

最小骨架：

```markdown
---
{
  "version": "alpha",
  "name": "<project design>",
  "description": "<specific visual reference and intended response>",
  "colors": {
    "primary": "#2859C5",
    "on-primary": "#FFFFFF"
  },
  "typography": {
    "body-md": {
      "fontFamily": "system-ui",
      "fontSize": "16px",
      "fontWeight": 400,
      "lineHeight": 1.5
    }
  },
  "rounded": {"md": "8px"},
  "spacing": {"md": "16px"},
  "components": {
    "button-primary": {
      "backgroundColor": "{colors.primary}",
      "textColor": "{colors.on-primary}",
      "typography": "{typography.body-md}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.md}"
    }
  }
}
---

## Overview
## Colors
## Typography
## Layout
## Elevation & Depth
## Shapes
## Components
## Do's and Don'ts
```

`DESIGN.md` 只负责可复用视觉身份、Token、设计原理和项目级视觉约束；`design-reference.json` 负责外部来源定位、组件映射、参考截图和获取进度；`design-guidance.json` 负责当前任务的用户目标、信息优先级、状态、设计决策与硬门禁适用性，不复制视觉 Token。命中 `product_contract` 时，产品语义与 UI binding 仍归 `prototype-contract.json`；实际通过/失败证据只归 `validation-report.json`。

指定组件库时，在扩展章节记录名称、固定版本、主题入口、允许组件和 fallback。组件库提供语义与实现约束，但视觉仍服从权威设计源或所选 Core system。明确指定 Ant Design、管理后台、运营后台、中后台、后台项目、运维控制台，或现有项目已经使用 Ant Design 时叠加 `ant_design_enterprise` 并读取 `references/ant-design-enterprise.md`；普通 Dashboard、数据看板、分析页、指标或图表不因页面类型自动命中。

使用 Ant Design 时，把 `DESIGN.md` 的规范 Token 映射到 `ConfigProvider.theme.token` 和 `ConfigProvider.theme.components`；页面壳、跨组件布局与 ECharts 主题使用同一组规范值。组件库未公开的内部 DOM 与哈希 class 不属于稳定映射接口。

## Legacy Compatibility

- 只有旧 `design.md` 时先读取并继续；Tier 0/1/2 不因文件名迁移扩大变更范围。
- Tier 3 已包含完整视觉刷新时创建或刷新 `DESIGN.md`。不得静默删除旧文件；如果两者同时存在，大写文件是权威来源，并在交付说明遗留路径。
- 新代码、文档和产物不得继续创建小写文件。

## No-context Work

- 中高风险任务先给简短方向或局部示例；用户明确直接做时记录 assumptions 后继续。
- 不默认使用 Ant、Material、紫色渐变、设备框或浏览器壳。
- 不编造产品 UI、客户证明或数据。
