# PRD Library Metadata Guide

Use this reference when normalizing an existing PRD library.

## Frontmatter Fields

- `title`: Human-readable document title. Fall back to first H1 when absent.
- `status`: Prefer `draft`, `review`, `approved`, `active`, `paused`, `archived`, or `superseded`.
- `owner`: Person or team accountable for the document.
- `product`: Product, feature area, or platform.
- `version`: Semantic version when the team uses formal versions. Otherwise keep simple strings such as `v1`.
- `updated`: ISO date, `YYYY-MM-DD`.
- `tags`: Short list used for dashboard filtering.
- `related`: Relative paths to PRDs, research notes, decision records, specs, prototype images, wireframes, design exports, or PDF prototypes.

## Relationship Detection

Consider documents related when any of these are true:

- One document lists another in `related`.
- Markdown links point to another document.
- Markdown image/file links point to prototype assets in `05-prototypes/`.
- A document mentions another document's stem or title in body text.
- A document mentions a prototype asset stem in body text.

Generated related blocks should be clearly marked and repeatable:

```markdown
<!-- prdlib:related:start -->
## Related Documents

- [Document title](path.md) - linked from frontmatter
- [prototype-flow-v1.png](../05-prototypes/prototype-flow-v1.png)
<!-- prdlib:related:end -->
```

## Changelog Entry Shape

Use this format in `CHANGELOG.md`:

```markdown
## 2026-06-08 - Checkout Optimization PRD - 2.0.0

- Summary: Expanded payment scenarios.
- Affected docs:
  - `01-active/checkout-optimization.md`
- Author: Ada
```
