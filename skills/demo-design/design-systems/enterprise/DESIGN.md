---
{
  "version": "alpha",
  "name": "Enterprise Workflow",
  "description": "Dense, dependable B2B interfaces for permissions, forms, and operational records.",
  "colors": {
    "primary": "#14528A",
    "on-primary": "#FFFFFF",
    "secondary": "#0B625F",
    "on-secondary": "#FFFFFF",
    "surface": "#FFFFFF",
    "on-surface": "#16202A",
    "surface-muted": "#E9EDF1",
    "status-danger": "#9C241D"
  },
  "typography": {
    "headline-lg": {
      "fontFamily": "system-ui",
      "fontSize": "30px",
      "fontWeight": 650,
      "lineHeight": 1.2,
      "letterSpacing": "-0.01em"
    },
    "title-md": {
      "fontFamily": "system-ui",
      "fontSize": "18px",
      "fontWeight": 650,
      "lineHeight": 1.3
    },
    "body-md": {
      "fontFamily": "system-ui",
      "fontSize": "14px",
      "fontWeight": 400,
      "lineHeight": 1.5
    },
    "label-sm": {
      "fontFamily": "system-ui",
      "fontSize": "13px",
      "fontWeight": 600,
      "lineHeight": 1.35
    }
  },
  "rounded": {
    "sm": "2px",
    "md": "4px",
    "lg": "6px"
  },
  "spacing": {
    "xs": "4px",
    "sm": "8px",
    "md": "12px",
    "lg": "16px",
    "xl": "24px"
  },
  "components": {
    "button-primary": {
      "backgroundColor": "{colors.primary}",
      "textColor": "{colors.on-primary}",
      "typography": "{typography.label-sm}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.md}",
      "height": "40px"
    },
    "button-secondary": {
      "backgroundColor": "{colors.secondary}",
      "textColor": "{colors.on-secondary}",
      "typography": "{typography.label-sm}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.md}",
      "height": "40px"
    },
    "record-surface": {
      "backgroundColor": "{colors.surface}",
      "textColor": "{colors.on-surface}",
      "typography": "{typography.body-md}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.lg}"
    },
    "selected-row": {
      "backgroundColor": "{colors.surface-muted}",
      "textColor": "{colors.on-surface}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.sm}"
    },
    "destructive-action": {
      "backgroundColor": "{colors.status-danger}",
      "textColor": "{colors.on-primary}",
      "typography": "{typography.label-sm}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.md}"
    }
  }
}
---

# Enterprise Workflow

## Overview

Reference an audited operations workstation: compact records, stable columns, visible scope, and predictable controls. Trust, scan speed, permissions, and recoverability outrank novelty.

## Colors

White and muted gray carry dense information. `{colors.primary}` commits the normal workflow; `{colors.secondary}` distinguishes a separate operational path. Destructive color is scarce and paired with explicit scope, consequences, and recovery information.

## Typography

Use a compact platform sans-serif with tabular numerals. Identifiers and immutable codes may use monospace. Labels use sentence case, and abbreviations appear only when the audience already knows the domain.

## Layout

Use a 4px base rhythm, stable table columns, persistent filters, and visible bulk selection. Narrow screens switch from wide tables to prioritized record summaries or a dedicated detail view; horizontal clipping is never the fallback strategy.

## Elevation & Depth

Hierarchy comes from rules, alignment, and tonal selection. Menus and confirmation dialogs may float; tables, forms, and persistent navigation remain flat.

## Shapes

Use restrained `{rounded.md}` corners and consistent control heights. Dense does not mean cramped: rows and controls retain readable hit areas and clear focus treatment.

## Components

Tables define loading, empty, error, overflow, and selection behavior. When narrow screens are explicitly in scope, they also define the target-specific layout behavior. Forms preserve permission context and validation near the affected field. Bulk and destructive actions state how many records will change.

## Do's and Don'ts

- Do preserve filter, selection, permission, and audit context during operations.
- Do show whether a mutation is pending, complete, partially complete, or recoverable.
- Do use text, iconography, or shape in addition to status color.
- Don't hide filters or bulk actions after selection.
- Don't use oversized cards or marketing hero patterns inside operational work.
- Don't mutate data silently or rely on a transient toast as the only evidence.
