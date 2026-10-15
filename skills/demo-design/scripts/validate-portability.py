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
CSS_DECLARATION_RE = re.compile(
    r"^\s*(--[\w-]+|(?:-webkit-)?mask(?:-image)?)\s*:\s*(.*?)\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _css_declarations(text: str) -> list[tuple[str, str]]:
    """Read mask and variable declarations without splitting quoted/data URLs."""
    declarations: list[tuple[str, str]] = []
    segment: list[str] = []
    quote = ""
    depth = 0
    index = 0

    def finish() -> None:
        match = CSS_DECLARATION_RE.match("".join(segment))
        if match:
            declarations.append((match.group(1), match.group(2)))
        segment.clear()

    while index < len(text):
        char = text[index]
        if quote:
            segment.append(char)
            if char == "\\" and index + 1 < len(text):
                index += 1
                segment.append(text[index])
            elif char == quote:
                quote = ""
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 1
            segment.append(" ")
        elif char in "\"'":
            quote = char
            segment.append(char)
        elif char == "(":
            depth += 1
            segment.append(char)
        elif char == ")":
            depth = max(0, depth - 1)
            segment.append(char)
        elif depth == 0 and char == "{":
            segment.clear()
        elif depth == 0 and char in ";}":
            finish()
        else:
            segment.append(char)
        index += 1
    finish()
    return declarations


def _css_function_arguments(value: str, name: str) -> list[str]:
    """Return balanced function arguments, including nested var() fallbacks."""
    arguments: list[str] = []
    pattern = re.compile(r"(?<![\w-])" + re.escape(name) + r"\(", re.IGNORECASE)
    for match in pattern.finditer(value):
        index = match.end()
        start = index
        depth = 1
        quote = ""
        while index < len(value):
            char = value[index]
            if quote:
                if char == "\\":
                    index += 1
                elif char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    arguments.append(value[start:index])
                    break
            index += 1
    return arguments


def _file_mask_errors(
    styles: list[tuple[str, str]],
) -> tuple[list[str], list[str]]:
    variables: dict[str, list[tuple[str, str]]] = {}
    masks: list[tuple[str, str]] = []
    for origin, style in styles:
        for property_name, value in _css_declarations(style):
            if property_name.startswith("--"):
                variables.setdefault(property_name, []).append((origin, value))
            else:
                masks.append((f"{origin} {property_name}", value))
    errors: set[str] = set()
    unresolved: set[str] = set()

    def inspect(origin: str, value: str, seen: set[str]) -> None:
        for argument in _css_function_arguments(value, "url"):
            url = argument.strip().strip("\"'").strip()
            parsed = urlsplit(url)
            if url and not url.startswith("#") and parsed.scheme.lower() in {"", "file"}:
                errors.add(
                    f"file opening cannot use an external local CSS mask from {origin}: {url}; "
                    "embed the mask as a data URI or an inline SVG fragment"
                )
        for argument in _css_function_arguments(value, "var"):
            name = argument.split(",", 1)[0].strip()
            if name in seen:
                unresolved.add(name)
                continue
            definitions = variables.get(name, [])
            if not definitions:
                unresolved.add(name)
            for variable_origin, variable_value in definitions:
                inspect(f"{origin} -> {name} ({variable_origin})", variable_value, seen | {name})

    for origin, value in masks:
        inspect(origin, value, set())
    return sorted(errors), sorted(unresolved)


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
        self.styles: list[tuple[str, str]] = []
        self.local_modules: list[tuple[str, str]] = []
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
        if tag == "script" and (attributes.get("type") or "").strip().lower() == "module" and attributes.get("src"):
            self.local_modules.append(("script[type=module]", str(attributes["src"])))
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
            if "modulepreload" in rel:
                self.local_modules.append(("link[rel=modulepreload]", str(attributes["href"])))
        style = attributes.get("style")
        if style:
            self.styles.append((f"{tag}[style]", style))
            for match in CSS_URL_RE.finditer(style):
                self.resources.append((f"{tag}[style]", match.group(2)))

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.styles.append(("style", data))
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
    *,
    opening_mode: str = "file",
) -> tuple[list[str], dict[str, Any]]:
    if opening_mode not in {"file", "http"}:
        raise ValueError("opening_mode must be 'file' or 'http'")
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
    styles = list(parser.styles)
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
            styles.append((f"css:{resolved.relative_to(html.parent).as_posix()}", resolved.read_text(encoding="utf-8", errors="ignore")))
            for css_origin, css_value in _css_resources(resolved):
                css_parsed = urlsplit(css_value)
                if css_parsed.scheme or css_parsed.netloc or css_value.startswith("/"):
                    queue.append((css_origin, css_value))
                else:
                    queue.append(
                        (css_origin, Path(relative.parent, css_value).as_posix())
                    )
    unresolved_mask_variables: list[str] = []
    if opening_mode == "file":
        mask_errors, unresolved_mask_variables = _file_mask_errors(styles)
        errors.extend(mask_errors)
        for origin, value in parser.local_modules:
            parsed = urlsplit(value.strip())
            if parsed.scheme.lower() in {"", "file"}:
                errors.append(
                    f"file opening cannot load a local ES module from {origin}: {value}; "
                    "bundle it into a classic script or inline its dependency-free code"
                )
    required_files = [html.name, *sorted(local_resources)]
    report = {
        "status": "failed" if errors else "passed",
        "requestedDeliveryFormat": "project_bundle",
        "deliveryMode": "directory",
        "openingMode": opening_mode,
        "evidenceLevel": "static",
        "fileOpenVerification": "unverified",
        "unresolvedMaskVariables": unresolved_mask_variables,
        "limitations": [
            "Static resource checks do not verify browser rendering or interactions.",
            "CSS variable mask checks inspect all declared values and fallbacks, not the computed cascade.",
            "JavaScript-generated masks, dynamic imports, fetch requests, and runtime CSS changes require actual opening checks.",
        ],
        "manualChecks": [
            "Extract the complete delivery folder, double-click the entry HTML, and verify icons and the main interaction path.",
            "Record actual file opening evidence separately; an HTTP preview does not verify file opening.",
        ] if opening_mode == "file" else [
            "Verify the declared HTTP entry and record the user's explicit HTTP delivery requirement.",
        ],
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
    parser.add_argument("--opening-mode", choices=("file", "http"), default="file", help="Default: unzip and double-click HTML; HTTP requires an explicit user delivery requirement")
    args = parser.parse_args(argv)
    try:
        errors, report = validate_portability(
            args.html,
            args.dependencies,
            opening_mode=args.opening_mode,
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
        print("OK: static demo resource checks passed; actual opening remains unverified")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
