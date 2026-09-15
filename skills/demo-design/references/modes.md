# Data Viz Mode

`data_viz` 叠加在一个 Delivery Route 上，不改变交付形态。

进入本 Mode 后读取 `references/data-viz-preflight.md`，用其中的数据、视觉、交互和证据检查约束生成与评审。

- 适用于 Web/App 生成，以及 `design_review` 中的已有图表检查。
- Brief 必须明确受众、决策目标和数据来源状态。
- 使用 `references/dependencies.md` 中固定的 ECharts 版本，或提供诚实的静态 fallback。
- 标明来源、单位、Legend、Axis、Tooltip，以及 Loading、Empty、Error 状态。
- 未知或占位数据必须明确标注，不得伪造趋势、客户指标或预测。
- 验证非零容器、Resize、Tooltip/Legend/Axis 遮挡、颜色对比和不依赖颜色的区分方式。
