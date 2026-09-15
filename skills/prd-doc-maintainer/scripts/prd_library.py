#!/usr/bin/env python3
"""Maintain a Markdown PRD document library."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Iterable


RELATED_START = "<!-- prdlib:related:start -->"
RELATED_END = "<!-- prdlib:related:end -->"
RELATED_EXTENSIONS = {".md", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf"}
DEFAULT_DIRS = [
    "00-ai-context",
    "01-active",
    "02-archive",
    "03-research",
    "04-decisions",
    "05-prototypes",
    "templates",
    "dashboard",
]
EXCLUDED_DOC_DIRS = {"00-ai-context", "templates", "dashboard"}


@dataclass
class Doc:
    path: Path
    rel: str
    title: str
    status: str = "unknown"
    owner: str = ""
    product: str = ""
    version: str = ""
    updated: str = ""
    tags: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    body: str = ""


@dataclass
class Asset:
    path: Path
    rel: str
    title: str


def today() -> str:
    return date.today().isoformat()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_scalar(value: str):
    value = value.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        raw = value[1:-1].strip()
        return [item.strip().strip("'\"") for item in raw.split(",") if item.strip()]
    return value.strip("'\"")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    block = text[4:end].strip("\n")
    body = text[text.find("\n", end + 1) + 1 :]
    data: dict[str, object] = {}
    current_key: str | None = None
    for line in block.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            data.setdefault(current_key, [])
            if isinstance(data[current_key], list):
                data[current_key].append(line[4:].strip().strip("'\""))
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            current_key = key.strip()
            data[current_key] = parse_scalar(value)
    return data, body


def format_list(values: Iterable[str]) -> str:
    return "\n".join(f"  - {item}" for item in values)


def update_frontmatter(text: str, updates: dict[str, object]) -> str:
    data, body = parse_frontmatter(text)
    data.update({key: value for key, value in updates.items() if value not in (None, "")})
    order = ["title", "status", "owner", "product", "version", "updated", "archived_at", "tags", "related"]
    keys = [key for key in order if key in data] + sorted(key for key in data if key not in order)
    lines = ["---"]
    for key in keys:
        value = data[key]
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.append(format_list(str(item) for item in value))
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body.lstrip("\n")


def title_from_body(path: Path, body: str, meta: dict) -> str:
    if meta.get("title"):
        return str(meta["title"])
    match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def load_docs(root: Path) -> list[Doc]:
    docs: list[Doc] = []
    for path in sorted(root.rglob("*.md")):
        rel_parts = path.relative_to(root).parts
        if path.name in {"INDEX.md", "README.md", "CHANGELOG.md"} or ".git" in path.parts or rel_parts[0] in EXCLUDED_DOC_DIRS:
            continue
        rel = path.relative_to(root).as_posix()
        text = read_text(path)
        meta, body = parse_frontmatter(text)
        docs.append(
            Doc(
                path=path,
                rel=rel,
                title=title_from_body(path, body, meta),
                status=str(meta.get("status", "unknown")),
                owner=str(meta.get("owner", "")),
                product=str(meta.get("product", "")),
                version=str(meta.get("version", "")),
                updated=str(meta.get("updated", "")),
                tags=as_list(meta.get("tags")),
                related=as_list(meta.get("related")),
                body=body,
            )
        )
    return docs


def load_assets(root: Path) -> list[Asset]:
    prototype_dir = root / "05-prototypes"
    if not prototype_dir.exists():
        return []
    assets: list[Asset] = []
    for path in sorted(prototype_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in RELATED_EXTENSIONS and path.name != "README.md":
            rel = path.relative_to(root).as_posix()
            assets.append(Asset(path=path, rel=rel, title=path.stem.replace("-", " ").replace("_", " ").title()))
    return assets


def ensure_scaffold(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for dirname in DEFAULT_DIRS:
        (root / dirname).mkdir(parents=True, exist_ok=True)
    config = root / ".prdlib.json"
    if not config.exists():
        write_text(
            config,
            json.dumps(
                {
                    "version": 1,
                    "created_at": today(),
                    "active_dir": "01-active",
                    "archive_dir": "02-archive",
                    "ai_context_dir": "00-ai-context",
                    "prototype_dir": "05-prototypes",
                },
                indent=2,
            )
            + "\n",
        )
    readme = root / "README.md"
    if not readme.exists():
        write_text(readme, "# PRD Library\n\nUse `INDEX.md` for the current catalog and `dashboard/index.html` for usage statistics.\n")
    changelog = root / "CHANGELOG.md"
    if not changelog.exists():
        write_text(changelog, "# PRD Library Changelog\n\n")
    ai_guide = root / "00-ai-context" / "AI_GUIDE.md"
    if not ai_guide.exists():
        write_text(
            ai_guide,
            """# AI Guide

Use this directory as the first stop before editing the PRD library.

## Read Order

1. Read `00-ai-context/DOC_MAP.md` to find relevant documents.
2. Read `INDEX.md` for the full catalog.
3. Open only the PRDs, research notes, decision records, and prototypes relevant to the task.
4. After edits, run `refresh --sync-related --dashboard` so links, index, AI map, and dashboard stay current.

## Editing Rules

- Preserve YAML frontmatter and update `updated` when content changes.
- Keep `related` paths current when a PRD depends on research, decisions, prototypes, or another PRD.
- Record major scope, workflow, metric, permission, billing, privacy, dependency, or launch changes in `CHANGELOG.md`.
- Store prototype images and design exports in `05-prototypes/`, then link them from the relevant PRD.
""",
        )
    prototype_readme = root / "05-prototypes" / "README.md"
    if not prototype_readme.exists():
        write_text(
            prototype_readme,
            """# Prototypes

Store prototype images, exported mockups, wireframes, flow screenshots, and design references here.

Recommended naming:

- `feature-name-flow-v1.png`
- `feature-name-mobile-v1.jpg`
- `feature-name-wireframe-v1.pdf`

Link prototype files from the related PRD using relative Markdown links.
""",
        )
    template = root / "templates" / "prd-template.md"
    if not template.exists():
        write_text(
            template,
            f"""---
title: New PRD
status: draft
owner:
product:
version: 0.1.0
updated: {today()}
tags: []
related: []
---

# New PRD

## Problem

## Goals

## Non-Goals

## Users

## Requirements

## Metrics

## Risks
""",
        )
    refresh(root, sync_related=False, dashboard=True)


def relation_map(docs: list[Doc], assets: list[Asset] | None = None) -> dict[str, set[str]]:
    assets = assets or []
    by_rel = {doc.rel: doc for doc in docs}
    by_name = {Path(doc.rel).stem.lower(): doc.rel for doc in docs}
    by_title = {doc.title.lower(): doc.rel for doc in docs if doc.title}
    asset_by_name = {Path(asset.rel).stem.lower(): asset.rel for asset in assets}
    rels: dict[str, set[str]] = {doc.rel: set() for doc in docs}
    link_re = re.compile(r"!?\[[^\]]*\]\(([^)]+)(?:#[^)]+)?\)")
    for doc in docs:
        for item in doc.related:
            target = (doc.path.parent / item).resolve()
            for other in docs:
                if other.path.resolve() == target or item.strip("./") == other.rel:
                    rels[doc.rel].add(other.rel)
                    rels[other.rel].add(doc.rel)
            for asset in assets:
                if asset.path.resolve() == target or item.strip("./") == asset.rel:
                    rels[doc.rel].add(asset.rel)
        for link in link_re.findall(doc.body):
            if Path(link).suffix.lower() not in RELATED_EXTENSIONS:
                continue
            target = (doc.path.parent / link).resolve()
            for other in docs:
                if other.path.resolve() == target:
                    rels[doc.rel].add(other.rel)
                    rels[other.rel].add(doc.rel)
            for asset in assets:
                if asset.path.resolve() == target:
                    rels[doc.rel].add(asset.rel)
        lowered = doc.body.lower()
        for stem, rel in by_name.items():
            if rel != doc.rel and stem in lowered:
                rels[doc.rel].add(rel)
                rels[rel].add(doc.rel)
        for title, rel in by_title.items():
            if rel != doc.rel and title in lowered:
                rels[doc.rel].add(rel)
                rels[rel].add(doc.rel)
        for stem, rel in asset_by_name.items():
            if stem in lowered:
                rels[doc.rel].add(rel)
    return rels


def relative_link(root: Path, from_doc: Doc, target_rel: str) -> str:
    return os.path.relpath(root / target_rel, start=from_doc.path.parent).replace(os.sep, "/")


def sync_related_blocks(root: Path, docs: list[Doc], rels: dict[str, set[str]]) -> None:
    by_rel = {doc.rel: doc for doc in docs}
    for doc in docs:
        related = sorted(rels.get(doc.rel, set()))
        if not related:
            continue
        lines = [RELATED_START, "## Related Documents", ""]
        for rel in related:
            target_title = by_rel[rel].title if rel in by_rel else Path(rel).name
            link = relative_link(root, doc, rel)
            lines.append(f"- [{target_title}]({link})")
        lines.append(RELATED_END)
        block = "\n".join(lines)
        text = read_text(doc.path)
        if RELATED_START in text and RELATED_END in text:
            text = re.sub(f"{re.escape(RELATED_START)}.*?{re.escape(RELATED_END)}", block, text, flags=re.S)
        else:
            text = text.rstrip() + "\n\n" + block + "\n"
        write_text(doc.path, text)


def render_index(root: Path, docs: list[Doc], rels: dict[str, set[str]]) -> None:
    active = [doc for doc in docs if doc.status not in {"archived", "superseded"} and "02-archive" not in doc.rel]
    archived = [doc for doc in docs if doc not in active]
    lines = ["# PRD Library Index", "", f"Generated: {today()}", "", "## Active Documents", ""]
    lines.extend(table(active, rels))
    lines.extend(["", "## Archived Documents", ""])
    lines.extend(table(archived, rels))
    write_text(root / "INDEX.md", "\n".join(lines).rstrip() + "\n")


def render_ai_doc_map(root: Path, docs: list[Doc], rels: dict[str, set[str]], assets: list[Asset]) -> None:
    status_counts = Counter(doc.status for doc in docs)
    lines = [
        "# AI Document Map",
        "",
        f"Generated: {today()}",
        "",
        "This file is generated for AI-assisted lookup and editing. Read it before opening individual PRDs.",
        "",
        "## Library Paths",
        "",
        "- `01-active/`: current PRDs",
        "- `02-archive/`: archived or superseded PRDs",
        "- `03-research/`: research notes and evidence",
        "- `04-decisions/`: decision records and ADRs",
        "- `05-prototypes/`: prototype images, mockups, wireframes, and design exports",
        "- `CHANGELOG.md`: major version and scope changes",
        "- `INDEX.md`: human-readable catalog",
        "",
        "## Status Counts",
        "",
    ]
    if status_counts:
        lines.extend(f"- `{status}`: {count}" for status, count in sorted(status_counts.items()))
    else:
        lines.append("- No documents found.")
    lines.extend(["", "## Query Table", "", "| Path | Title | Status | Owner | Product | Updated | Tags | Related |", "| --- | --- | --- | --- | --- | --- | --- | --- |"])
    for doc in docs:
        tags = ", ".join(doc.tags)
        related = ", ".join(sorted(rels.get(doc.rel, set())))
        lines.append(f"| `{doc.rel}` | {doc.title} | {doc.status} | {doc.owner} | {doc.product} | {doc.updated} | {tags} | {related} |")
    lines.extend(["", "## Prototype Assets", "", "| Path | Name |", "| --- | --- |"])
    if assets:
        for asset in assets:
            lines.append(f"| `{asset.rel}` | {asset.title} |")
    else:
        lines.append("| _None_ |  |")
    lines.extend(
        [
            "",
            "## AI Edit Checklist",
            "",
            "1. Locate candidate docs in the Query Table.",
            "2. Read related docs listed in the final column before changing requirements.",
            "3. Update frontmatter fields, especially `updated`, `version`, `tags`, and `related`.",
            "4. Link prototype images from `05-prototypes/` when they explain flows or UI states.",
            "5. Add a `CHANGELOG.md` entry for large scope, metric, workflow, privacy, billing, permission, dependency, or launch changes.",
            "6. Run `refresh --sync-related --dashboard` after edits.",
        ]
    )
    write_text(root / "00-ai-context" / "DOC_MAP.md", "\n".join(lines).rstrip() + "\n")


def table(docs: list[Doc], rels: dict[str, set[str]]) -> list[str]:
    lines = ["| Title | Status | Owner | Product | Updated | Related |", "| --- | --- | --- | --- | --- | --- |"]
    if not docs:
        lines.append("| _None_ |  |  |  |  |  |")
        return lines
    for doc in docs:
        lines.append(
            f"| [{doc.title}]({doc.rel}) | {doc.status} | {doc.owner} | {doc.product} | {doc.updated} | {len(rels.get(doc.rel, []))} |"
        )
    return lines


def parse_changelog(root: Path) -> list[dict[str, str]]:
    path = root / "CHANGELOG.md"
    if not path.exists():
        return []
    entries = []
    for match in re.finditer(r"^##\s+(\d{4}-\d{2}-\d{2})\s+-\s+(.+?)(?:\s+-\s+(.+))?$", read_text(path), re.M):
        entries.append({"date": match.group(1), "title": match.group(2), "version": match.group(3) or ""})
    return entries[:8]


def dashboard_data(root: Path, docs: list[Doc], rels: dict[str, set[str]]) -> dict:
    status_counts = Counter(doc.status for doc in docs)
    relation_pairs = {tuple(sorted((source, target))) for source, targets in rels.items() for target in targets}
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": {
            "total_docs": len(docs),
            "active_docs": sum(1 for doc in docs if doc.status not in {"archived", "superseded"} and "02-archive" not in doc.rel),
            "archived_docs": sum(1 for doc in docs if doc.status in {"archived", "superseded"} or "02-archive" in doc.rel),
            "related_links": len(relation_pairs),
        },
        "status_counts": dict(status_counts),
        "documents": [
            {
                "title": doc.title,
                "path": doc.rel,
                "status": doc.status,
                "owner": doc.owner,
                "product": doc.product,
                "updated": doc.updated,
                "related_count": len(rels.get(doc.rel, [])),
            }
            for doc in docs
        ],
        "recent_changes": parse_changelog(root),
    }


def write_dashboard(root: Path, docs: list[Doc], rels: dict[str, set[str]]) -> None:
    template_path = Path(__file__).resolve().parents[1] / "assets" / "dashboard-template.html"
    template = read_text(template_path)
    payload = json.dumps(dashboard_data(root, docs, rels), ensure_ascii=False).replace("<", "\\u003c")
    write_text(root / "dashboard" / "index.html", template.replace("__PRD_DATA__", payload))


def refresh(root: Path, sync_related: bool, dashboard: bool) -> None:
    docs = load_docs(root)
    assets = load_assets(root)
    rels = relation_map(docs, assets)
    if sync_related:
        sync_related_blocks(root, docs, rels)
        docs = load_docs(root)
        assets = load_assets(root)
        rels = relation_map(docs, assets)
    render_index(root, docs, rels)
    render_ai_doc_map(root, docs, rels, assets)
    if dashboard:
        write_dashboard(root, docs, rels)


def archive_doc(root: Path, doc_path: Path, reason: str) -> None:
    source = doc_path if doc_path.is_absolute() else root / doc_path
    if not source.exists():
        raise SystemExit(f"Document not found: {source}")
    year_dir = root / "02-archive" / str(date.today().year)
    target = year_dir / source.name
    counter = 2
    while target.exists():
        target = year_dir / f"{source.stem}-{counter}{source.suffix}"
        counter += 1
    text = update_frontmatter(read_text(source), {"status": "archived", "archived_at": today(), "updated": today()})
    write_text(source, text)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    record_change(root, title=f"Archived {target.name}", version="", summary=reason, docs=[target.relative_to(root).as_posix()], author="")
    refresh(root, sync_related=True, dashboard=True)


def record_change(root: Path, title: str, version: str, summary: str, docs: list[str], author: str) -> None:
    path = root / "CHANGELOG.md"
    if not path.exists():
        write_text(path, "# PRD Library Changelog\n\n")
    entry = [f"## {today()} - {title}" + (f" - {version}" if version else ""), "", f"- Summary: {summary or 'Updated PRD library.'}"]
    if docs:
        entry.append("- Affected docs:")
        entry.extend(f"  - `{doc}`" for doc in docs)
    if author:
        entry.append(f"- Author: {author}")
    entry.append("")
    current = read_text(path)
    if current.startswith("# PRD Library Changelog"):
        parts = current.split("\n", 1)
        text = parts[0] + "\n\n" + "\n".join(entry) + (parts[1].lstrip("\n") if len(parts) > 1 else "")
    else:
        text = "\n".join(entry) + "\n" + current
    write_text(path, text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain a PRD document library.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scaffold")
    p.add_argument("library_dir")

    p = sub.add_parser("refresh")
    p.add_argument("library_dir")
    p.add_argument("--sync-related", action="store_true")
    p.add_argument("--dashboard", action="store_true")

    p = sub.add_parser("dashboard")
    p.add_argument("library_dir")

    p = sub.add_parser("archive")
    p.add_argument("library_dir")
    p.add_argument("doc_path")
    p.add_argument("--reason", default="")

    p = sub.add_parser("record-change")
    p.add_argument("library_dir")
    p.add_argument("--title", required=True)
    p.add_argument("--version", default="")
    p.add_argument("--summary", default="")
    p.add_argument("--doc", action="append", default=[])
    p.add_argument("--author", default="")

    args = parser.parse_args()
    root = Path(getattr(args, "library_dir")).resolve()

    if args.command == "scaffold":
        ensure_scaffold(root)
    elif args.command == "refresh":
        refresh(root, sync_related=args.sync_related, dashboard=args.dashboard)
    elif args.command == "dashboard":
        docs = load_docs(root)
        rels = relation_map(docs, load_assets(root))
        write_dashboard(root, docs, rels)
    elif args.command == "archive":
        archive_doc(root, Path(args.doc_path), args.reason)
    elif args.command == "record-change":
        record_change(root, args.title, args.version, args.summary, args.doc, args.author)
        refresh(root, sync_related=True, dashboard=True)


if __name__ == "__main__":
    main()
