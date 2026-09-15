---
name: prd-doc-maintainer
description: Maintain AI-readable PRD document libraries for product teams. Use when Codex needs to scaffold a PRD repository optimized for AI lookup and editing, organize or archive PRD Markdown documents, update index catalogs and AI document maps, synchronize related-document links after edits, store prototype images or design exports, record version changelogs for major product-document changes, or generate a standalone HTML usage dashboard for a PRD doc library.
---

# PRD Doc Maintainer

## Overview

Use this skill to create and maintain a Markdown-based PRD document library with predictable folders, AI-readable document maps, indexes, relationship tracking, prototype storage, archive hygiene, major-change logging, and a static HTML dashboard that works without a server.

Prefer the bundled script for deterministic file operations:

```bash
python scripts/prd_library.py scaffold <library-dir>
python scripts/prd_library.py refresh <library-dir> --sync-related --dashboard
python scripts/prd_library.py archive <library-dir> <doc-path> --reason "Superseded by v2"
python scripts/prd_library.py record-change <library-dir> --title "Checkout PRD v2" --version "2.0.0" --summary "Expanded payment scenarios"
```

## Workflow

1. Inspect the target library before changing it. Start with `00-ai-context/DOC_MAP.md` when it exists, then use `INDEX.md` and only open the relevant source documents.
2. If no library exists, run `scaffold` to create the default structure.
3. For new or edited PRDs, normalize frontmatter where useful: `title`, `status`, `owner`, `product`, `version`, `updated`, `tags`, and `related`.
4. Run `refresh --sync-related --dashboard` after document edits, archive moves, or changelog updates.
5. For large changes, run `record-change` or update `CHANGELOG.md` with the same structure before refreshing the dashboard.
6. Verify the generated `00-ai-context/DOC_MAP.md`, `INDEX.md`, `CHANGELOG.md`, and `dashboard/index.html` enough to catch broken paths or obviously wrong metadata.

## Library Structure

Default scaffold:

```text
<library-dir>/
├── README.md
├── INDEX.md
├── CHANGELOG.md
├── .prdlib.json
├── 00-ai-context/
│   ├── AI_GUIDE.md
│   └── DOC_MAP.md
├── 01-active/
├── 02-archive/
├── 03-research/
├── 04-decisions/
├── 05-prototypes/
├── templates/
│   └── prd-template.md
└── dashboard/
    └── index.html
```

Keep AI-first lookup files in `00-ai-context/`. Keep active PRDs in `01-active/`. Move retired PRDs to `02-archive/<year>/`. Keep discovery notes in `03-research/`, decision records in `04-decisions/`, and prototype images, mockups, wireframes, flow screenshots, or design exports in `05-prototypes/`.

## AI Readability

Use `00-ai-context/DOC_MAP.md` as the first stop for AI agents. It is generated from source documents and contains library paths, status counts, a query table, related-document hints, and an edit checklist. Do not store canonical requirements only in `00-ai-context/`; keep authoritative content in PRDs, research, decisions, changelog, and prototype files.

After any edit that affects requirements, relationships, prototypes, or metadata, run:

```bash
python scripts/prd_library.py refresh <library-dir> --sync-related --dashboard
```

This keeps `DOC_MAP.md`, `INDEX.md`, generated related blocks, and `dashboard/index.html` aligned.

## Document Metadata

Use YAML frontmatter for machine-readable maintenance:

```markdown
---
title: Checkout Optimization PRD
status: draft
owner: Ada
product: Payments
version: 0.3.0
updated: 2026-06-08
tags: [checkout, payments]
related:
  - ../04-decisions/adr-payment-provider.md
  - ../05-prototypes/checkout-flow-v1.png
---
```

Supported `status` values are flexible, but prefer `draft`, `review`, `approved`, `active`, `paused`, `archived`, and `superseded`.

## Related Document Sync

When a document changes, find documents that reference it through `related`, Markdown links, or filename mentions. Use `refresh --sync-related` to update the generated relationship block in each Markdown file:

```markdown
<!-- prdlib:related:start -->
...
<!-- prdlib:related:end -->
```

Do not hand-edit inside this block unless the user explicitly asks. Put curated relationship notes elsewhere in the document.

## Changelog Rules

Treat these as large changes that need `CHANGELOG.md` entries:

- PRD version bumps that alter scope, requirements, launch criteria, metrics, dependencies, risks, permissions, billing, privacy, or user workflows.
- Archiving or superseding an approved or active PRD.
- Cross-document changes that alter assumptions in related PRDs, research, or decision records.

Use concise entries with date, version, affected docs, summary, and author when known.

## Dashboard

Generate a standalone dashboard with:

```bash
python scripts/prd_library.py dashboard <library-dir>
```

The output is `dashboard/index.html`. It embeds its data and CSS in one file, so it can be opened directly in a browser without Node, Python server, or external assets.

## References

Read `references/metadata-guide.md` when deciding how to normalize frontmatter, status values, relationship blocks, or changelog entries for a messy existing library.
