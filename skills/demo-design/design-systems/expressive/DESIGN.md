---
{
  "version": "alpha",
  "name": "Expressive Contrast",
  "description": "Bold campaign compositions with controlled asymmetry and a single dominant statement.",
  "colors": {
    "primary": "#F4D35E",
    "on-primary": "#11110F",
    "secondary": "#78A6FF",
    "on-secondary": "#11110F",
    "accent": "#FF837A",
    "on-accent": "#11110F",
    "surface": "#1C1B18",
    "on-surface": "#FFFDF5"
  },
  "typography": {
    "display-xl": {
      "fontFamily": "Impact",
      "fontSize": "96px",
      "fontWeight": 700,
      "lineHeight": 0.95,
      "letterSpacing": "-0.04em"
    },
    "headline-lg": {
      "fontFamily": "system-ui",
      "fontSize": "36px",
      "fontWeight": 750,
      "lineHeight": 1.1,
      "letterSpacing": "-0.02em"
    },
    "body-md": {
      "fontFamily": "system-ui",
      "fontSize": "18px",
      "fontWeight": 400,
      "lineHeight": 1.5
    },
    "label-sm": {
      "fontFamily": "system-ui",
      "fontSize": "14px",
      "fontWeight": 700,
      "lineHeight": 1.3
    }
  },
  "rounded": {
    "none": "0px",
    "md": "12px",
    "full": "9999px"
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
      "rounded": "{rounded.none}",
      "padding": "{spacing.md}",
      "height": "52px"
    },
    "button-secondary": {
      "backgroundColor": "{colors.secondary}",
      "textColor": "{colors.on-secondary}",
      "typography": "{typography.label-sm}",
      "rounded": "{rounded.none}",
      "padding": "{spacing.md}",
      "height": "52px"
    },
    "accent-label": {
      "backgroundColor": "{colors.accent}",
      "textColor": "{colors.on-accent}",
      "typography": "{typography.label-sm}",
      "rounded": "{rounded.full}",
      "padding": "{spacing.sm}"
    },
    "campaign-surface": {
      "backgroundColor": "{colors.surface}",
      "textColor": "{colors.on-surface}",
      "typography": "{typography.body-md}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.lg}"
    }
  }
}
---

# Expressive Contrast

## Overview

Reference a single-sheet cultural poster translated into a browser interface: one dominant statement, deliberate cropping, controlled asymmetry, and a repeated graphic motif. Use only when the brief explicitly asks for impact or a differentiated campaign direction.

## Colors

Near-black surfaces create the stage. `{colors.primary}` carries the primary action or dominant highlight; secondary and accent colors support distinct roles rather than forming an indiscriminate neon gradient.

## Typography

Display type may be oversized and tightly spaced, but body and controls remain conventional and readable. Use one dominant statement with short supporting copy. If Impact is unavailable or inappropriate, choose one licensed condensed grotesk and record the fallback.

## Layout

Allow asymmetry, cropping, overlap, and scale contrast while preserving reading order and the primary CTA. Reuse one graphic motif across the page. Mobile recomposes the hierarchy; it never merely shrinks a desktop poster.

## Elevation & Depth

Depth comes from crop, overlap, contrast, and motion, not a pile of glowing cards. Keep interactive controls on a stable plane so their affordance remains clear.

## Shapes

Choose either square geometry or a deliberate `{rounded.md}` system for major surfaces. Pills are reserved for compact labels. Do not mix unrelated radius styles as decoration.

## Components

Campaign CTAs are direct and high-contrast. Forms and product controls fall back to familiar behavior with visible focus, error, disabled, and loading states. Motion may reinforce hierarchy but cannot compete with the statement or action.

## Do's and Don'ts

- When multiple viewports are explicitly in scope, do preserve the statement, CTA, and reading order across those targets.
- Do reuse one motif and one geometry system.
- Do provide Reduced Motion fallback for transforms or scroll-linked effects.
- Don't use generic neon AI gradients, random stickers, or fake version labels.
- Don't overlap text until it becomes illegible or blocks interaction.
- Don't turn every section into a separate visual stunt.
