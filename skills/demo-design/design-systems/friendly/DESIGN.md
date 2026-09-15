---
{
  "version": "alpha",
  "name": "Friendly Consumer",
  "description": "Warm, capable interfaces for onboarding, habits, and everyday personal tasks.",
  "colors": {
    "primary": "#B94331",
    "on-primary": "#FFFFFF",
    "secondary": "#2E6F64",
    "on-secondary": "#FFFFFF",
    "surface": "#FFFFFF",
    "on-surface": "#2E2421",
    "surface-warm": "#FFF0E6",
    "highlight": "#7A5800"
  },
  "typography": {
    "headline-lg": {
      "fontFamily": "ui-rounded",
      "fontSize": "42px",
      "fontWeight": 700,
      "lineHeight": 1.15,
      "letterSpacing": "-0.02em"
    },
    "title-md": {
      "fontFamily": "ui-rounded",
      "fontSize": "22px",
      "fontWeight": 650,
      "lineHeight": 1.3
    },
    "body-md": {
      "fontFamily": "system-ui",
      "fontSize": "17px",
      "fontWeight": 400,
      "lineHeight": 1.55
    },
    "label-sm": {
      "fontFamily": "system-ui",
      "fontSize": "15px",
      "fontWeight": 600,
      "lineHeight": 1.35
    }
  },
  "rounded": {
    "sm": "8px",
    "md": "14px",
    "lg": "20px",
    "full": "9999px"
  },
  "spacing": {
    "xs": "4px",
    "sm": "8px",
    "md": "16px",
    "lg": "24px",
    "xl": "40px"
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
    "personal-card": {
      "backgroundColor": "{colors.surface}",
      "textColor": "{colors.on-surface}",
      "typography": "{typography.body-md}",
      "rounded": "{rounded.lg}",
      "padding": "{spacing.lg}"
    },
    "orientation-panel": {
      "backgroundColor": "{colors.surface-warm}",
      "textColor": "{colors.on-surface}",
      "rounded": "{rounded.lg}",
      "padding": "{spacing.lg}"
    },
    "highlight-label": {
      "backgroundColor": "{colors.highlight}",
      "textColor": "{colors.on-primary}",
      "rounded": "{rounded.full}",
      "padding": "{spacing.sm}"
    }
  }
}
---

# Friendly Consumer

## Overview

Reference a thoughtfully designed neighborhood service: warm materials, direct language, generous touch targets, and small moments of reassurance. The interface should feel approachable without becoming childish or hiding meaningful choices.

## Colors

Warm neutrals create orientation; `{colors.primary}` marks the main next step and `{colors.secondary}` supports steady progress. Illustration and highlight color may guide attention, but never substitute for labels, state, or hierarchy.

## Typography

Rounded display typography can soften headings, while body and controls remain highly legible. Copy is direct, encouraging, and non-judgmental. Avoid novelty faces for instructions, forms, or longer reading.

## Layout

Use an 8px rhythm, generous touch targets, and one obvious next action per step. Personal objects can live in cards; onboarding steps should reveal only the information needed for the current decision. Narrow screens retain breathing room without pushing the action below unnecessary decoration.

## Elevation & Depth

Use warm tonal surfaces before shadows. A subtle lift may mark a selected personal object or temporary sheet; routine sections remain integrated with the page.

## Shapes

Controls use `{rounded.md}` and feature surfaces use `{rounded.lg}`. Rounded geometry should communicate safety and tactility, not turn every label into a pill.

## Components

Progress, empty states, and errors explain the next useful action. Primary and secondary buttons remain visually distinct. Illustration has an orientation or emotional-support role and receives honest alternative text when meaningful.

## Do's and Don'ts

- Do explain what happens next and how to recover from a problem.
- Do preserve generous 44px-or-larger touch targets.
- Do use soft 180–260ms feedback without layout jumps.
- Don't use emoji as default interface icons.
- Don't use babyish, congratulatory, or medicalized language.
- Don't add confetti, pulsing, or perpetual bouncing to routine actions.
