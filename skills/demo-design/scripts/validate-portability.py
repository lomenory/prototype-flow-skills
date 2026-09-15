#!/usr/bin/env python3
"""Validate an HTML entry and its resources inside a shareable demo folder."""

from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
FALLBACK_COMMENT_RE = re.compile(r"demo-design:\s*fallback=([a-z0-9_-]+)", re.IGNORECASE)
REMOTE_SCHEMES = {"http", "https"}
EMBEDDED_SCHEMES = {"data", "blob"}


def _srcset_urls(value: str) -> list[str]:
    separator = r",\s+" if "data:" in value.lower() else r",\s*"
    urls: list[str] = []
    for candidate in re.split(separator, value.strip()):
        if candidate.strip():
            urls.append(candidate.strip().split(maxsplit=1)[0])
    return urls


class ResourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.resources: list[tuple[str, str]] = []
        self.fallbacks: set[str] = set()
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value for name, value in attrs}
        fallback = attributes.get("data-demo-fallback")
        if fallback:
            self.fallbacks.update(item.strip() for item in fallback.split(",") if item.strip())
        if tag == "style":
            self._in_style = True
        if tag in {"img", "script", "source"} and attributes.get("src"):
            self.resources.append((f"{tag}[src]", str(attributes["src"])))
        if tag in {"img", "source"} and attributes.get("srcset"):
            self.resources.extend(
                (f"{tag}[srcset]", value)
                for value in _srcset_urls(str(attributes["srcset"]))
            )
        if tag == "video" and attributes.get("poster"):
            self.resources.append(("video[poster]", str(attributes["poster"])))
        if tag == "link" and attributes.get("href"):
            rel = set((attributes.get("rel") or "").lower().split())
            if rel & {"stylesheet", "icon", "preload", "modulepreload"}:
                self.resources.append(("link[href]", str(attributes["href"])))
        style = attributes.get("style")
        if style:
            for match in CSS_URL_RE.finditer(style):
                self.resources.append((f"{tag}[style]", match.group(2)))

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            for match in CSS_URL_RE.finditer(data):
                self.resources.append(("style[url]", match.group(2)))

    def handle_comment(self, data: str) -> None:
        self.fallbacks.update(FALLBACK_COMMENT_RE.findall(data))


def load_dependencies(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"dependencies contract does not exist: {source}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"dependencies contract is invalid JSON: {error.msg}") from error
    return value


def _safe_local_resource(raw: str) -> Path | None:
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        return None
    decoded = unquote(parsed.path)
    path = Path(decoded)
    if not decoded or path.is_absolute():
        return None
    return path


def _css_resources(path: Path) -> list[tuple[str, str]]:
    if path.suffix.lower() != ".css" or not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [(f"css:{path.name}", match.group(2)) for match in CSS_URL_RE.finditer(text)]


def validate_portability(
    html_path: str | Path,
    dependencies_path: str | Path | None = None,
) -> tuple[list[str], dict[str, Any]]:
    html = Path(html_path).resolve()
    dependencies_source = (
        Path(dependencies_path)
        if dependencies_path
        else Path(__file__).resolve().parents[1] / "contracts" / "dependencies.yaml"
    )
    dependencies = load_dependencies(dependencies_source).get("dependencies", {})
    approved_urls = {
        item.get("cdn"): {"id": dependency_id, "fallback": item.get("fallback")}
        for dependency_id, item in dependencies.items()
        if isinstance(item, dict) and item.get("cdn")
    }
    try:
        source = html.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ValueError(f"HTML does not exist: {html}") from None
    parser = ResourceParser()
    parser.feed(source)
    queue = list(parser.resources)
    local_resources: set[str] = set()
    embedded_resources: set[str] = set()
    remote_dependencies: list[dict[str, Any]] = []
    remote_assets: set[str] = set()
    errors: list[str] = []
    scanned_css: set[Path] = set()
    index = 0
    while index < len(queue):
        origin, raw = queue[index]
        index += 1
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        if scheme in EMBEDDED_SCHEMES:
            embedded_resources.add(scheme)
            continue
        if scheme in REMOTE_SCHEMES:
            approved = approved_urls.get(value)
            if approved:
                remote_dependencies.append({"url": value, **approved})
                fallback = approved.get("fallback")
                if fallback and fallback not in parser.fallbacks:
                    errors.append(
                        f"approved remote dependency {approved['id']} requires declared fallback {fallback!r}"
                    )
            else:
                remote_assets.add(value)
                errors.append(f"remote resource is not portable or approved: {value}")
            continue
        relative = _safe_local_resource(value)
        if relative is None:
            errors.append(f"unsafe or unsupported local resource from {origin}: {value}")
            continue
        resolved = (html.parent / relative).resolve()
        try:
            resolved.relative_to(html.parent)
        except ValueError:
            errors.append(f"resource escapes demo directory: {value}")
            continue
        local_resources.add(resolved.relative_to(html.parent).as_posix())
        if not resolved.is_file():
            errors.append(f"local resource does not exist: {relative.as_posix()}")
            continue
        if resolved.suffix.lower() == ".css" and resolved not in scanned_css:
            scanned_css.add(resolved)
            for css_origin, css_value in _css_resources(resolved):
                css_parsed = urlsplit(css_value)
                if css_parsed.scheme or css_parsed.netloc or css_value.startswith("/"):
                    queue.append((css_origin, css_value))
                else:
                    queue.append(
                        (css_origin, Path(relative.parent, css_value).as_posix())
                    )
    required_files = [html.name, *sorted(local_resources)]
    report = {
        "status": "failed" if errors else "passed",
        "requestedDeliveryFormat": "project_bundle",
        "deliveryMode": "directory",
        "primaryShareArtifact": html.parent.name,
        "entryHtml": html.name,
        "requiredFiles": required_files,
        "shareBoundary": html.parent.as_posix(),
        "declaredFallbacks": sorted(parser.fallbacks),
        "remoteDependencies": sorted(remote_dependencies, key=lambda item: item["id"]),
        "remoteAssets": sorted(remote_assets),
        "embeddedSchemes": sorted(embedded_resources),
        "errors": errors,
    }
    return errors, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the HTML entry and resources in a demo folder")
    parser.add_argument("html", type=Path)
    parser.add_argument("--dependencies", type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args(argv)
    try:
        errors, report = validate_portability(
            args.html,
            args.dependencies,
        )
    except ValueError as error:
        errors = [str(error)]
        report = {"status": "failed", "errors": errors}
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("OK: demo resources are portable")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
