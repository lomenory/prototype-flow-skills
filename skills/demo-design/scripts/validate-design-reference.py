#!/usr/bin/env python3
"""Validate external design-reference sidecars and resumable acquisition state."""

from __future__ import annotations

import argparse
import json
import re
import struct
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


SOURCE_ID_RE = re.compile(r"^DSRC-[A-Z0-9_-]+$")
SOURCE_KINDS = {"figma", "screenshot", "url", "repository"}
PRECISIONS = {"exact", "approximate", "assumption"}
ROUTES = {"web_hi_fi", "app_flow"}
ACQUISITION_STATUSES = {"complete", "partial", "blocked"}
STATE_ID_RE = re.compile(r"^STATE-[A-Z0-9_-]+$")
ID_SELECTOR_RE = re.compile(r"^#([A-Za-z][A-Za-z0-9_-]*)$")
DATA_SELECTOR_RE = re.compile(
    r"^\[(data-[a-z0-9-]+)=(?:\"([^\"]+)\"|'([^']+)'|([A-Za-z0-9:_-]+))\]$"
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def load_reference(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"design reference does not exist: {source}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"design reference is not valid JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError("design reference root must be an object")
    return value


def _validate_viewport(value: Any, label: str, errors: list[str]) -> None:
    viewport = _object(value)
    width = viewport.get("width")
    height = viewport.get("height")
    scale = viewport.get("deviceScaleFactor")
    if not isinstance(width, int) or isinstance(width, bool) or width < 1:
        errors.append(f"{label}.width must be a positive integer")
    if not isinstance(height, int) or isinstance(height, bool) or height < 1:
        errors.append(f"{label}.height must be a positive integer")
    if not isinstance(scale, (int, float)) or isinstance(scale, bool) or scale <= 0:
        errors.append(f"{label}.deviceScaleFactor must be positive")


def _safe_project_path(value: Any) -> Path | None:
    if not _text(value):
        return None
    path = Path(str(value))
    if path.is_absolute() or ".." in path.parts:
        return None
    return path


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or not header.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG file")
    if header[12:16] != b"IHDR":
        raise ValueError("PNG is missing IHDR")
    return struct.unpack(">II", header[16:24])


def _stable_selector(value: Any) -> tuple[str, str] | None:
    if not _text(value):
        return None
    selector = str(value).strip()
    match = ID_SELECTOR_RE.fullmatch(selector)
    if match:
        return "id", match.group(1)
    match = DATA_SELECTOR_RE.fullmatch(selector)
    if match:
        return match.group(1), next(
            item for item in match.groups()[1:] if item is not None
        )
    return None


class ReferenceHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[dict[str, str | None]] = []

    def handle_starttag(
        self,
        _tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.elements.append(dict(attrs))


def _selector_count(elements: list[dict[str, str | None]], selector: Any) -> int | None:
    parsed = _stable_selector(selector)
    if parsed is None:
        return None
    attribute, expected = parsed
    return sum(1 for attributes in elements if attributes.get(attribute) == expected)


def _comparison_selectors(reference: dict[str, Any]) -> list[tuple[str, str]]:
    selectors: list[tuple[str, str]] = []
    for index, raw in enumerate(_list(reference.get("referenceScreenshots"))):
        comparison = _object(_object(raw).get("comparison"))
        if _text(comparison.get("regionSelector")):
            selectors.append(
                (
                    f"referenceScreenshots[{index}].comparison.regionSelector",
                    str(comparison["regionSelector"]),
                )
            )
        for mask_index, selector in enumerate(
            _list(comparison.get("maskSelectors"))
        ):
            selectors.append(
                (
                    "referenceScreenshots"
                    f"[{index}].comparison.maskSelectors[{mask_index}]",
                    str(selector),
                )
            )
    return selectors


def validate_html(reference: dict[str, Any], html_path: str | Path) -> list[str]:
    """Validate v2 stable selector mappings against the delivered HTML."""
    if reference.get("schemaVersion") != 2:
        return []
    path = Path(html_path)
    try:
        html = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"HTML does not exist: {path}"]
    parser = ReferenceHTMLParser()
    parser.feed(html)
    errors: list[str] = []
    selectors: list[tuple[str, str]] = []
    for index, raw in enumerate(_list(reference.get("componentMappings"))):
        mapping = _object(raw)
        selectors.append(
            (
                f"componentMappings[{index}].implementationSelector",
                str(mapping.get("implementationSelector", "")),
            )
        )
        state_id = mapping.get("implementationStateId")
        if _text(state_id):
            selectors.append(
                (
                    f"componentMappings[{index}].implementationStateId",
                    f"[data-state-id={state_id}]",
                )
            )
    selectors.extend(_comparison_selectors(reference))
    for label, selector in selectors:
        count = _selector_count(parser.elements, selector)
        if count is None:
            errors.append(
                f"{label} must be a stable #id or [data-*=value] selector"
            )
        elif count != 1:
            errors.append(
                f"{label} must match exactly one HTML element; found {count}: {selector}"
            )
    return errors


def validate_reference(
    reference: dict[str, Any],
    reference_path: str | Path | None = None,
    check_paths: bool = True,
) -> list[str]:
    errors: list[str] = []
    schema_version = reference.get("schemaVersion")
    if schema_version not in {1, 2}:
        errors.append("schemaVersion must be 1 or 2")
    if reference.get("deliveryRoute") not in ROUTES:
        errors.append("deliveryRoute must be web_hi_fi or app_flow")

    acquisition = _object(reference.get("acquisition"))
    status = acquisition.get("status")
    if status not in ACQUISITION_STATUSES:
        errors.append("acquisition.status must be complete, partial or blocked")
    completed = _list(acquisition.get("completedNodeIds"))
    pending = _list(acquisition.get("pendingNodeIds"))
    notes = _list(acquisition.get("notes"))
    for label, values in (("completedNodeIds", completed), ("pendingNodeIds", pending)):
        if len(values) != len(set(str(item) for item in values)):
            errors.append(f"acquisition.{label} must not contain duplicates")
        if any(not _text(item) for item in values):
            errors.append(f"acquisition.{label} must contain non-empty node IDs")
    overlap = sorted(set(str(item) for item in completed) & set(str(item) for item in pending))
    if overlap:
        errors.append("acquisition completed and pending node IDs overlap: " + ", ".join(overlap))
    if status == "complete" and pending:
        errors.append("complete acquisition must not contain pendingNodeIds")
    if status == "partial" and not pending:
        errors.append("partial acquisition requires pendingNodeIds")
    if status == "blocked" and not any(_text(item) for item in notes):
        errors.append("blocked acquisition requires a note")

    sources = _list(reference.get("sources"))
    if not sources:
        errors.append("sources must contain at least one source")
    source_ids: set[str] = set()
    figma_nodes: set[str] = set()
    for index, raw in enumerate(sources):
        source = _object(raw)
        label = f"sources[{index}]"
        source_id = source.get("id")
        if not _text(source_id) or not SOURCE_ID_RE.fullmatch(str(source_id)):
            errors.append(f"{label}.id must use DSRC-* format")
        elif str(source_id) in source_ids:
            errors.append(f"duplicate source id: {source_id}")
        else:
            source_ids.add(str(source_id))
        if source.get("kind") not in SOURCE_KINDS:
            errors.append(f"{label}.kind is invalid")
        if source.get("precision") not in PRECISIONS:
            errors.append(f"{label}.precision is invalid")
        for field in ("label", "locator"):
            if not _text(source.get(field)):
                errors.append(f"{label}.{field} must be non-empty")
        if source.get("kind") == "figma":
            for field in ("fileKey", "nodeId"):
                if not _text(source.get(field)):
                    errors.append(f"{label}.{field} is required for Figma")
            if _text(source.get("nodeId")):
                figma_nodes.add(str(source["nodeId"]))
            if source.get("precision") == "exact":
                _validate_viewport(source.get("viewport"), f"{label}.viewport", errors)

    known_acquisition_nodes = set(str(item) for item in completed + pending)
    for node_id in sorted(figma_nodes - known_acquisition_nodes):
        errors.append(f"Figma node is not tracked by acquisition state: {node_id}")
    if status == "complete":
        for node_id in sorted(figma_nodes - set(str(item) for item in completed)):
            errors.append(f"complete acquisition has unfinished Figma node: {node_id}")

    mapping_selectors: set[str] = set()
    variant_state_ids: set[str] = set()
    for index, raw in enumerate(_list(reference.get("componentMappings"))):
        mapping = _object(raw)
        label = f"componentMappings[{index}]"
        if mapping.get("sourceId") not in source_ids:
            errors.append(f"{label} references unknown source {mapping.get('sourceId')!r}")
        if mapping.get("fidelity") not in PRECISIONS:
            errors.append(f"{label}.fidelity is invalid")
        for field in ("sourceComponent", "implementationSelector"):
            if not _text(mapping.get(field)):
                errors.append(f"{label}.{field} must be non-empty")
        selector = mapping.get("implementationSelector")
        if _text(selector):
            if str(selector) in mapping_selectors:
                errors.append(f"duplicate component implementation selector: {selector}")
            mapping_selectors.add(str(selector))
        state_id = mapping.get("implementationStateId")
        if schema_version == 2 and _text(mapping.get("sourceVariant")):
            if not _text(state_id) or not STATE_ID_RE.fullmatch(str(state_id)):
                errors.append(
                    f"{label}.implementationStateId is required for a sourceVariant"
                )
            else:
                variant_state_ids.add(str(state_id))
        elif state_id is not None and (
            not _text(state_id) or not STATE_ID_RE.fullmatch(str(state_id))
        ):
            errors.append(f"{label}.implementationStateId must be a STATE-* ID")

    screenshots = _list(reference.get("referenceScreenshots"))
    if status == "complete" and not screenshots:
        errors.append("complete acquisition requires at least one reference screenshot")
    base = Path(reference_path).resolve().parent if reference_path else None
    screenshot_keys: set[tuple[Any, Any, Any, Any]] = set()
    screenshot_state_ids: set[str] = set()
    default_screenshots = 0
    for index, raw in enumerate(screenshots):
        screenshot = _object(raw)
        label = f"referenceScreenshots[{index}]"
        if screenshot.get("sourceId") not in source_ids:
            errors.append(f"{label} references unknown source {screenshot.get('sourceId')!r}")
        relative = _safe_project_path(screenshot.get("path"))
        if relative is None or relative.suffix.lower() != ".png":
            errors.append(f"{label}.path must be a safe project-relative PNG path")
        elif check_paths and base is not None and not (base / relative).is_file():
            errors.append(f"{label}.path does not exist: {relative.as_posix()}")
        _validate_viewport(screenshot.get("viewport"), f"{label}.viewport", errors)
        viewport = _object(screenshot.get("viewport"))
        state_id = screenshot.get("stateId")
        key = (
            viewport.get("width"),
            viewport.get("height"),
            viewport.get("deviceScaleFactor"),
            state_id or "default",
        )
        if key in screenshot_keys:
            errors.append(
                f"duplicate reference screenshot for viewport/state: {key}"
            )
        screenshot_keys.add(key)
        if _text(state_id):
            if not STATE_ID_RE.fullmatch(str(state_id)):
                errors.append(f"{label}.stateId must be a STATE-* ID")
            else:
                screenshot_state_ids.add(str(state_id))
        else:
            default_screenshots += 1
        comparison = _object(screenshot.get("comparison"))
        mask_selectors = _list(comparison.get("maskSelectors"))
        if len(mask_selectors) > 8:
            errors.append(f"{label}.comparison.maskSelectors exceeds 8")
        if len(mask_selectors) != len(set(str(item) for item in mask_selectors)):
            errors.append(f"{label}.comparison.maskSelectors contains duplicates")
        if "comparison" in screenshot and not (
            _text(comparison.get("regionSelector")) or mask_selectors
        ):
            errors.append(f"{label}.comparison must declare a region or mask")
        if (
            schema_version == 2
            and check_paths
            and base is not None
            and relative is not None
            and (base / relative).is_file()
        ):
            try:
                png_width, png_height = _png_dimensions(base / relative)
            except (OSError, ValueError) as error:
                errors.append(f"{label}.path is not a readable PNG: {error}")
            else:
                width = viewport.get("width")
                height = viewport.get("height")
                scale = viewport.get("deviceScaleFactor")
                if (
                    isinstance(width, int)
                    and isinstance(height, int)
                    and isinstance(scale, (int, float))
                    and not isinstance(scale, bool)
                    and (png_width, png_height)
                    != (round(width * scale), round(height * scale))
                ):
                    errors.append(
                        f"{label}.path dimensions {png_width}x{png_height} do not "
                        f"match viewport at scale {scale}"
                    )
    if schema_version == 2 and status == "complete" and default_screenshots == 0:
        errors.append("schemaVersion 2 complete acquisition requires a default-state screenshot")
    if schema_version == 2 and status == "complete":
        for state_id in sorted(variant_state_ids - screenshot_state_ids):
            errors.append(
                f"source variant state has no reference screenshot: {state_id}"
            )
    return errors


def build_report(reference: dict[str, Any], errors: list[str], path: str | Path | None) -> dict[str, Any]:
    acquisition = _object(reference.get("acquisition"))
    return {
        "status": "failed" if errors else "passed",
        "schemaVersion": reference.get("schemaVersion"),
        "deliveryRoute": reference.get("deliveryRoute"),
        "acquisition": {
            "status": acquisition.get("status"),
            "completedNodes": len(_list(acquisition.get("completedNodeIds"))),
            "pendingNodes": len(_list(acquisition.get("pendingNodeIds"))),
        },
        "sources": len(_list(reference.get("sources"))),
        "componentMappings": len(_list(reference.get("componentMappings"))),
        "referenceScreenshots": len(_list(reference.get("referenceScreenshots"))),
        "stateScreenshots": sum(
            1
            for item in _list(reference.get("referenceScreenshots"))
            if _text(_object(item).get("stateId"))
        ),
        "path": str(path) if path else None,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a demo-design external design reference")
    parser.add_argument("reference", type=Path)
    parser.add_argument("--html", type=Path)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--no-check-paths", action="store_true")
    args = parser.parse_args(argv)
    try:
        reference = load_reference(args.reference)
        errors = validate_reference(reference, args.reference, not args.no_check_paths)
        if args.html:
            errors.extend(validate_html(reference, args.html))
    except ValueError as error:
        errors = [str(error)]
        reference = {}
    report = build_report(reference, errors, args.reference)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("OK: design reference valid")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
