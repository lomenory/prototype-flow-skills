---
{
  "version": "alpha",
  "name": "Warm Editorial",
  "description": "Human, story-led composition with serif hierarchy and deliberate reading rhythm.",
  "colors": {
    "primary": "#963D2D",
    "on-primary": "#FFFFFF",
    "secondary": "#27504A",
    "on-secondary": "#FFFFFF",
    "surface": "#FFFDF8",
    "on-surface": "#2A211C",
    "surface-paper": "#F1E4D5",
    "highlight": "#7C5400"
  },
  "typography": {
    "display-lg": {
      "fontFamily": "Georgia",
      "fontSize": "64px",
      "fontWeight": 600,
      "lineHeight": 1.05,
      "letterSpacing": "-0.03em"
    },
    "headline-md": {
      "fontFamily": "Georgia",
      "fontSize": "42px",
      "fontWeight": 600,
      "lineHeight": 1.15,
      "letterSpacing": "-0.02em"
    },
    "body-md": {
      "fontFamily": "system-ui",
      "fontSize": "18px",
      "fontWeight": 400,
      "lineHeight": 1.7
    },
    "label-sm": {
      "fontFamily": "system-ui",
      "fontSize": "14px",
      "fontWeight": 650,
      "lineHeight": 1.4
    }
  },
  "rounded": {
    "none": "0px",
    "sm": "3px",
    "md": "6px"
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
    "button-secondary": {
      "backgroundColor": "{colors.secondary}",
      "textColor": "{colors.on-secondary}",
      "typography": "{typography.label-sm}",
      "rounded": "{rounded.md}",
      "padding": "{spacing.md}",
      "height": "48px"
    },
    "article-surface": {
      "backgroundColor": "{colors.surface}",
      "textColor": "{colors.on-surface}",
      "typography": "{typography.body-md}",
      "rounded": "{rounded.none}",
      "padding": "{spacing.lg}"
    },
    "paper-note": {
      "backgroundColor": "{colors.surface-paper}",
      "textColor": "{colors.on-surface}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.md}"
    },
    "highlight-label": {
      "backgroundColor": "{colors.highlight}",
      "textColor": "{colors.on-primary}",
      "rounded": "{rounded.sm}",
      "padding": "{spacing.sm}"
    }
  }
}
---

# Warm Editorial

## Overview

Reference a well-edited weekend journal printed on warm stock: strong headlines, readable body measure, documentary imagery, captions, and rules that support a narrative sequence. The interface should feel authored rather than decorated.

## Colors

Warm paper and ink form the foundation. `{colors.primary}` carries the editorial accent; `{colors.secondary}` supports navigation or utility. Texture is optional and must never reduce contrast or simulate age without a content reason.

## Typography

Use an expressive serif for display and a readable sans-serif for controls, metadata, and body support. Long text stays between 58 and 72 characters with generous line height. Italics are used for meaning, not as a default mood.

## Layout

Use editorial columns, pull quotes, captions, and rules only when they clarify reading order. Images need a narrative role. When multiple viewports are explicitly in scope, target-specific layouts collapse columns without changing story sequence or separating captions from media.

## Elevation & Depth

Treat the page as paper: hierarchy comes from type, crop, rule, and surface tone. Shadows are uncommon and reserved for temporary UI layers.

## Shapes

Editorial media and text surfaces are square or subtly rounded. Interactive controls may use `{rounded.md}` so they remain distinct from reading content.

## Components

Article modules preserve headline, deck, byline, body, media, and caption relationships. UI actions use the sans-serif layer and literal labels. Pull quotes are real quotations with attribution, never invented decoration.

## Do's and Don'ts

- Do preserve story order, captions, authorship, and source context.
- Do let display typography and image crop establish editorial character.
- Do use slow 220–320ms reveals only when content remains available without scrolling.
- Don't invent quotations, testimonials, awards, or publication metadata.
- Don't use magazine decoration without narrative value.
- Don't let texture, italics, or low contrast compromise reading.
