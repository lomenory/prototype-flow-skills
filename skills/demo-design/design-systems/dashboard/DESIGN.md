---
{
  "version": "alpha",
  "name": "Analytical Dashboard",
  "description": "Decision-oriented analytics with comparison, provenance, and explicit data states.",
  "colors": {
    "primary": "#8DC7F5",
    "on-primary": "#0F1720",
    "surface": "#17222E",
    "on-surface": "#F3F6F9",
    "surface-raised": "#233344",
    "series-teal": "#65D6B8",
    "series-amber": "#F2C45E",
    "series-coral": "#FF8B80",
    "series-violet": "#BDA7FF",
    "on-surface-secondary": "#B2C1D2"
  },
  "typography": {
    "metric-xl": {
      "fontFamily": "system-ui",
      "fontSize": "40px",
      "fontWeight": 700,
      "lineHeight": 1.1,
      "letterSpacing": "-0.02em"
    },
    "title-md": {
      "fontFamily": "system-ui",
      "fontSize": "20px",
      "fontWeight": 650,
      "lineHeight": 1.25
    },
    "body-md": {
      "fontFamily": "system-ui",
      "fontSize": "15px",
      "fontWeight": 400,
      "lineHeight": 1.5
    },
    "label-sm": {
      "fontFamily": "ui-monospace",
      "fontSize": "14px",
      "fontWeight": 550,
      "lineHeight": 1.35
    },
    "body-sm": {
      "fontFamily": "system-ui",
      "fontSize": "14px",
      "fontWeight": 400,
      "lineHeight": 1.6
    },
    "caption": {
      "fontFamily": "system-ui",
      "fontSize": "12px",
      "fontWeight": 400,
      "lineHeight": 1.5
    }
  },
  "rounded": {
    "sm": "2px",
    "md": "6px",
    "lg": "10px"
  },
  "spacing": {
    "xs": "4px",
    "sm": "8px",
    "md": "12px",
    "lg": "16px",
    "xl": "24px"
  },
  "components": {
    "action-primary": {
      "backgroundColor": "{colors.primary}",
      "textColor": "{colors.on-primary}",
      "typography": "{typography.label-sm}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.md}"
    },
    "chart-panel": {
      "backgroundColor": "{colors.surface}",
      "textColor": "{colors.on-surface}",
      "typography": "{typography.body-md}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.lg}"
    },
    "chart-panel-raised": {
      "backgroundColor": "{colors.surface-raised}",
      "textColor": "{colors.on-surface}",
      "rounded": "{rounded.lg}",
      "padding": "{spacing.lg}"
    },
    "series-teal-label": {
      "backgroundColor": "{colors.series-teal}",
      "textColor": "{colors.on-primary}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.xs}"
    },
    "series-amber-label": {
      "backgroundColor": "{colors.series-amber}",
      "textColor": "{colors.on-primary}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.xs}"
    },
    "series-coral-label": {
      "backgroundColor": "{colors.series-coral}",
      "textColor": "{colors.on-primary}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.xs}"
    },
    "series-violet-label": {
      "backgroundColor": "{colors.series-violet}",
      "textColor": "{colors.on-primary}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.xs}"
    },
    "supporting-copy": {
      "backgroundColor": "{colors.surface}",
      "textColor": "{colors.on-surface-secondary}",
      "typography": "{typography.body-sm}"
    },
    "supporting-copy-secondary-surface": {
      "backgroundColor": "{colors.surface-raised}",
      "textColor": "{colors.on-surface-secondary}",
      "typography": "{typography.body-sm}"
    }
  }
}
---

# Analytical Dashboard

## Overview

Reference an overnight network-operations console: aligned plots, stable time windows, calm dark surfaces, and color used to distinguish evidence rather than decorate the canvas. The purpose is to notice change, compare segments, and investigate anomalies.

## Colors

Dark neutral surfaces reduce glare and keep plots visually continuous. Series colors are selected for separation and pair with labels, shapes, or patterns. `{colors.primary}` marks an action or current query, not every chart.

## Typography

正文使用 `{typography.body-md}`；标签、关键帮助、反馈、图表轴/单位和说明使用 `{typography.label-sm}` 或 `{typography.body-sm}`。支持性文字使用 `{colors.on-surface-secondary}`，不要逐个 selector 发明更浅的灰色。`{typography.caption}` 只用于少量不影响操作或判断的元数据。

这些角色必须落实到实际 CSS；不要保留文档里的 14–16px Token，却在页面大量使用 9–12px 的操作说明。密度通过布局、分组和间距调节，必要时纵向滚动。

Use tabular numerals for metrics and compact monospace for timestamps, intervals, and identifiers. Units stay attached to values. Titles explain the decision represented by the chart rather than repeating a metric name.

## Layout

Align plot areas and comparison columns. Every chart keeps source status, unit, time range, aggregation, and loading/empty/error state visible. Narrow screens prioritize one decision signal at a time instead of shrinking a multi-column dashboard.

## Elevation & Depth

Use borders and tonal layers, not heavy shadows. Raised surfaces are reserved for inspectors, tooltips, or a selected analytic context. Plot grids remain quieter than data.

## Shapes

Use restrained corners so chart geometry stays precise. Series marks may vary by shape; focus and selection must remain legible against dark surfaces.

## Components

Legends, axes, annotations, and tooltips must not cover the decision signal. Tooltips repeat series labels and units. Metric cards are allowed only when they answer a distinct question and expose freshness or provenance.

## Do's and Don'ts

- Do state source, unit, range, aggregation, and freshness where they affect interpretation.
- Do use label, shape, or pattern in addition to color for important distinctions.
- Do animate only when value continuity improves; respect Reduced Motion.
- Don't use fake live dots, decorative sparklines, or unlabeled KPIs.
- Don't truncate baselines or manipulate scale to exaggerate change.
- Don't use a rainbow palette when fewer meaningful series are sufficient.
