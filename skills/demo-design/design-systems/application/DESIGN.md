---
{
  "version": "alpha",
  "name": "Product Application",
  "description": "Task-oriented interfaces for repeatable workflows and visible multi-state operations.",
  "colors": {
    "primary": "#3730A3",
    "on-primary": "#FFFFFF",
    "secondary": "#0F6B6D",
    "on-secondary": "#FFFFFF",
    "surface": "#FFFFFF",
    "on-surface": "#14213D",
    "surface-muted": "#E8EDF5",
    "selection": "#DDE3FF",
    "on-surface-secondary": "#53627A"
  },
  "typography": {
    "headline-lg": {
      "fontFamily": "system-ui",
      "fontSize": "32px",
      "fontWeight": 650,
      "lineHeight": 1.2,
      "letterSpacing": "-0.02em"
    },
    "title-md": {
      "fontFamily": "system-ui",
      "fontSize": "18px",
      "fontWeight": 600,
      "lineHeight": 1.35
    },
    "body-md": {
      "fontFamily": "system-ui",
      "fontSize": "16px",
      "fontWeight": 400,
      "lineHeight": 1.5
    },
    "label-sm": {
      "fontFamily": "system-ui",
      "fontSize": "14px",
      "fontWeight": 600,
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
    "sm": "4px",
    "md": "6px",
    "lg": "10px"
  },
  "spacing": {
    "xs": "4px",
    "sm": "8px",
    "md": "16px",
    "lg": "24px",
    "xl": "32px"
  },
  "components": {
    "button-primary": {
      "backgroundColor": "{colors.primary}",
      "textColor": "{colors.on-primary}",
      "typography": "{typography.label-sm}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.md}",
      "height": "44px"
    },
    "button-secondary": {
      "backgroundColor": "{colors.secondary}",
      "textColor": "{colors.on-secondary}",
      "typography": "{typography.label-sm}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.md}",
      "height": "44px"
    },
    "workspace-panel": {
      "backgroundColor": "{colors.surface}",
      "textColor": "{colors.on-surface}",
      "typography": "{typography.body-md}",
      "rounded": "{rounded.lg}",
      "padding": "{spacing.lg}"
    },
    "toolbar-muted": {
      "backgroundColor": "{colors.surface-muted}",
      "textColor": "{colors.on-surface}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.sm}"
    },
    "selection-row": {
      "backgroundColor": "{colors.selection}",
      "textColor": "{colors.on-surface}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.sm}"
    },
    "supporting-copy": {
      "backgroundColor": "{colors.surface}",
      "textColor": "{colors.on-surface-secondary}",
      "typography": "{typography.body-sm}"
    },
    "supporting-copy-secondary-surface": {
      "backgroundColor": "{colors.surface-muted}",
      "textColor": "{colors.on-surface-secondary}",
      "typography": "{typography.body-sm}"
    }
  }
}
---

# Product Application

## Overview

Reference the clarity of a well-maintained operations console: a persistent toolbar, a stable work area, and contextual details that stay close to the selected object. Completion speed, state clarity, and recovery matter more than marketing spectacle.

## Colors

Neutral surfaces carry the workflow. `{colors.primary}` is the main commit action; `{colors.secondary}` supports navigation or a distinct secondary operation. Selection uses a quiet tinted row so it remains visible without competing with the action hierarchy.

## Typography

正文使用 `{typography.body-md}`；标签、关键帮助、反馈、图表轴/单位和说明使用 `{typography.label-sm}` 或 `{typography.body-sm}`。支持性文字使用 `{colors.on-surface-secondary}`，不要逐个 selector 发明更浅的灰色。`{typography.caption}` 只用于少量不影响操作或判断的元数据。

这些角色必须落实到实际 CSS；不要保留文档里的 14–16px Token，却在页面大量使用 9–12px 的操作说明。密度通过布局、分组和间距调节，必要时纵向滚动。

Use a neutral platform sans-serif with tabular numerals for counts and timestamps. Headings name the task or current state. Labels are literal; identifiers may use the platform monospace stack in implementation.

## Layout

Prefer toolbar + work area + contextual detail. Preserve navigation, filter state, selection, and pending edits across transitions. On narrow screens, move detail into a dedicated step or sheet while maintaining the same task order.

## Elevation & Depth

Persistent work regions are flat and separated by rules or tonal change. Menus, dialogs, and temporary inspectors may float above the workspace; routine panels should not all become elevated cards.

## Shapes

Controls use `{rounded.md}` and panels use `{rounded.lg}`. Keep control heights aligned to 32, 40, or 44px families, with 44px used for App Flow touch targets.

## Components

Forms retain visible labels, help, validation, submission progress, and recovery. Async or destructive actions expose scope and resulting state. Toolbars group actions by object and frequency rather than filling every available slot.

## Do's and Don'ts

- Do keep the current object, selection, filter, and save state observable.
- Do provide cancellation or recovery when the workflow can safely support it.
- Do use motion only for 120–180ms state continuity.
- Don't hide the primary action behind an unlabeled icon.
- Don't insert decorative charts into task workflows.
- Don't treat a success toast as the only proof that persistent state changed.
