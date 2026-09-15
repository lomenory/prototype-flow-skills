---
{
  "version": "alpha",
  "name": "Focused Minimal",
  "description": "Restrained composition for quiet, premium, and single-purpose experiences.",
  "colors": {
    "primary": "#181816",
    "on-primary": "#FFFFFF",
    "accent": "#70442C",
    "on-accent": "#FFFFFF",
    "surface": "#FBFAF7",
    "on-surface": "#181816",
    "surface-muted": "#ECE8E0"
  },
  "typography": {
    "display-lg": {
      "fontFamily": "system-ui",
      "fontSize": "68px",
      "fontWeight": 600,
      "lineHeight": 1.05,
      "letterSpacing": "-0.04em"
    },
    "title-md": {
      "fontFamily": "system-ui",
      "fontSize": "28px",
      "fontWeight": 550,
      "lineHeight": 1.2,
      "letterSpacing": "-0.02em"
    },
    "body-md": {
      "fontFamily": "system-ui",
      "fontSize": "18px",
      "fontWeight": 400,
      "lineHeight": 1.65
    },
    "label-sm": {
      "fontFamily": "system-ui",
      "fontSize": "14px",
      "fontWeight": 600,
      "lineHeight": 1.4
    }
  },
  "rounded": {
    "none": "0px",
    "sm": "2px",
    "md": "8px"
  },
  "spacing": {
    "xs": "4px",
    "sm": "8px",
    "md": "16px",
    "lg": "32px",
    "xl": "64px"
  },
  "components": {
    "button-primary": {
      "backgroundColor": "{colors.primary}",
      "textColor": "{colors.on-primary}",
      "typography": "{typography.label-sm}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.md}",
      "height": "48px"
    },
    "button-accent": {
      "backgroundColor": "{colors.accent}",
      "textColor": "{colors.on-accent}",
      "typography": "{typography.label-sm}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.md}",
      "height": "48px"
    },
    "content-surface": {
      "backgroundColor": "{colors.surface}",
      "textColor": "{colors.on-surface}",
      "typography": "{typography.body-md}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.lg}"
    },
    "quiet-panel": {
      "backgroundColor": "{colors.surface-muted}",
      "textColor": "{colors.on-surface}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.md}"
    }
  }
}
---

# Focused Minimal

## Overview

Reference a small contemporary gallery catalogue: one clear subject, careful measure, hairline structure, and no decorative urgency. Minimal means fewer decisions and stronger editing, not missing controls or states.

## Colors

Warm paper-like surfaces and near-black text carry the composition. `{colors.accent}` is used only when a second emphasis is semantically necessary. Color never compensates for weak hierarchy.

## Typography

One precise sans-serif family is the default. A serif display face may replace the display token only when the content has a genuine editorial reason. Use size, weight, and spacing before adding visual effects.

## Layout

Use open composition, deliberate 48–96px section rhythm, and a controlled reading measure. The primary action remains visible despite low ornament. Narrow screens preserve hierarchy and readable margins rather than creating empty decorative space.

## Elevation & Depth

Depth is nearly absent. Hairline rules, surface tone, and spacing separate regions. Temporary overlays may use a restrained shadow, but persistent content stays on the same visual plane.

## Shapes

Editorial surfaces are square or use `{rounded.sm}`; controls may use `{rounded.md}` so affordance remains clear. Do not mix sharp and pill geometry without a semantic reason.

## Components

Buttons remain visibly interactive. Empty, error, loading, and disabled states retain the same typographic care as the default state. Content surfaces contain real relationships, not arbitrary fragments.

## Do's and Don'ts

- Do make the primary subject and action unmistakable.
- Do preserve explicit states and accessible focus even when ornament is sparse.
- Do use 180–260ms opacity or small translate transitions only when useful.
- Don't use beige as shorthand for luxury without a content reason.
- Don't create so much whitespace that task flow breaks.
- Don't add ornamental microcopy, invisible borders, parallax, or ambient motion.
