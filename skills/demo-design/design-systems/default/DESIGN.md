---
{
  "version": "alpha",
  "name": "Neutral Default",
  "description": "A quiet, reliable product baseline that prioritizes clarity before personality.",
  "colors": {
    "primary": "#2859C5",
    "on-primary": "#FFFFFF",
    "surface": "#FFFFFF",
    "on-surface": "#172033",
    "surface-muted": "#EEF2F7",
    "status-success": "#0F6B46",
    "status-warning": "#7A4A00",
    "status-danger": "#A32929"
  },
  "typography": {
    "headline-lg": {
      "fontFamily": "system-ui",
      "fontSize": "40px",
      "fontWeight": 650,
      "lineHeight": 1.15,
      "letterSpacing": "-0.02em"
    },
    "title-md": {
      "fontFamily": "system-ui",
      "fontSize": "20px",
      "fontWeight": 600,
      "lineHeight": 1.3
    },
    "body-md": {
      "fontFamily": "system-ui",
      "fontSize": "16px",
      "fontWeight": 400,
      "lineHeight": 1.6
    },
    "label-sm": {
      "fontFamily": "system-ui",
      "fontSize": "14px",
      "fontWeight": 600,
      "lineHeight": 1.4
    }
  },
  "rounded": {
    "sm": "4px",
    "md": "8px",
    "lg": "12px"
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
    "panel-default": {
      "backgroundColor": "{colors.surface}",
      "textColor": "{colors.on-surface}",
      "typography": "{typography.body-md}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.lg}"
    },
    "panel-muted": {
      "backgroundColor": "{colors.surface-muted}",
      "textColor": "{colors.on-surface}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.md}"
    },
    "status-success": {
      "backgroundColor": "{colors.status-success}",
      "textColor": "{colors.on-primary}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.sm}"
    },
    "status-warning": {
      "backgroundColor": "{colors.status-warning}",
      "textColor": "{colors.on-primary}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.sm}"
    },
    "status-danger": {
      "backgroundColor": "{colors.status-danger}",
      "textColor": "{colors.on-primary}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.sm}"
    }
  }
}
---

# Neutral Default

## Overview

Use the visual register of a mature productivity tool: quiet white work surfaces, blue reserved for action, and hierarchy created by type and spacing rather than decoration. It is the fallback when the brief has no credible brand direction, not a license to make every page look identical.

## Colors

The canvas is neutral and low-noise. `{colors.primary}` marks the primary action and current selection; status colors carry explicit labels or icons and never communicate meaning alone. Muted surfaces organize secondary regions without producing a stack of nested cards.

## Typography

Use the platform sans-serif stack so controls feel native to the environment. Headlines are compact and literal. Body copy stays near 66 characters per line; labels describe the action or state instead of using clever shorthand.

## Layout

Use an 8px rhythm, one primary alignment system, and a stable content width. Desktop layouts may introduce columns when they clarify relationships; narrow screens reorder content by task priority instead of shrinking the desktop composition.

## Elevation & Depth

Default depth is flat. Borders and tonal surfaces separate persistent regions; soft shadow is reserved for temporary layers such as menus, dialogs, and dragged objects.

## Shapes

Use `{rounded.md}` for controls and ordinary panels. Larger radii are reserved for prominent, low-density surfaces. Focus rings remain visible and must not be clipped by rounded containers.

## Components

Primary buttons use `button-primary`; secondary actions remain quieter and adjacent to their target. Forms preserve labels, help, error, disabled, loading, and success states. Cards are used only when containment expresses a real object or relationship.

## Do's and Don'ts

- Do let task hierarchy, labels, and spacing provide most of the visual structure.
- Do make empty, error, loading, and disabled states explicit where applicable.
- Do preserve keyboard focus and a minimum 44px target for App Flow controls.
- Don't add decorative gradients, generic logo walls, fake metrics, or ornamental dashboards.
- Don't nest cards to manufacture hierarchy.
- Don't use blue on every interactive element; reserve it for the most important action or state.
