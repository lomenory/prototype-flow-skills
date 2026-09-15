#!/usr/bin/env python3
"""Validate compatible DESIGN.md visual-system artifacts without dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "design-systems" / "index.json"
FRONT_MATTER_DELIMITER = "---"
REQUIRED_GROUPS = (
    "colors",
    "typography",
    "rounded",
    "spacing",
    "components",
)
SECTION_ORDER = (
    "Overview",
    "Colors",
    "Typography",
    "Layout",
    "Elevation & Depth",
    "Shapes",
    "Components",
    "Do's and Don'ts",
)
SECTION_ALIASES = {
    "Brand & Style": "Overview",
    "Layout & Spacing": "Layout",
    "Elevation": "Elevation & Depth",
}
TOKEN_REFERENCE = re.compile(r"^\{([A-Za-z0-9_.-]+)\}$")
DIMENSION = re.compile(r"^-?(?:\d+(?:\.\d+)?|\.\d+)(?:px|em|rem)$")
HEX_COLOR = re.compile(r"^#([0-9a-fA-F]{6})$")
CSS_COLOR = re.compile(
    r"^(?:#[0-9a-fA-F]{3,8}|rgba?\(.+\)|hsla?\(.+\)|hwb\(.+\)|"
    r"oklch\(.+\)|oklab\(.+\)|lch\(.+\)|lab\(.+\)|color-mix\(.+\)|"
    r"transparent|currentColor|[a-zA-Z]+)$"
)
TYPOGRAPHY_FIELDS = ("fontFamily", "fontSize", "fontWeight", "lineHeight")


@dataclass
class FileResult:
    path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return {
            "path": self.path.as_posix(),
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
            },
        }


def parse_front_matter(text: str, result: FileResult) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0] != FRONT_MATTER_DELIMITER:
        result.errors.append("missing JSON-compatible YAML front matter")
        return {}, text
    try:
        closing = lines.index(FRONT_MATTER_DELIMITER, 1)
    except ValueError:
        result.errors.append("front matter is missing its closing --- delimiter")
        return {}, text
    raw = "\n".join(lines[1:closing]).strip()
    if not raw:
        result.errors.append("front matter is empty")
        return {}, "\n".join(lines[closing + 1 :])
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        result.errors.append(
            f"front matter must be JSON-compatible YAML: line {error.lineno}, {error.msg}"
        )
        return {}, "\n".join(lines[closing + 1 :])
    if not isinstance(payload, dict):
        result.errors.append("front matter must decode to an object")
        return {}, "\n".join(lines[closing + 1 :])
    return payload, "\n".join(lines[closing + 1 :])


def resolve_reference(tokens: dict[str, Any], reference: str) -> Any:
    match = TOKEN_REFERENCE.fullmatch(reference)
    if not match:
        return None
    value: Any = tokens
    for segment in match.group(1).split("."):
        if not isinstance(value, dict) or segment not in value:
            raise KeyError(match.group(1))
        value = value[segment]
    return value


def all_references(value: Any) -> list[str]:
    if isinstance(value, dict):
        references: list[str] = []
        for child in value.values():
            references.extend(all_references(child))
        return references
    if isinstance(value, list):
        references = []
        for child in value:
            references.extend(all_references(child))
        return references
    if isinstance(value, str) and TOKEN_REFERENCE.fullmatch(value):
        return [value]
    return []


def relative_luminance(channel: int) -> float:
    normalized = channel / 255
    return normalized / 12.92 if normalized <= 0.04045 else ((normalized + 0.055) / 1.055) ** 2.4


def contrast_ratio(first: str, second: str) -> float | None:
    first_match = HEX_COLOR.fullmatch(first)
    second_match = HEX_COLOR.fullmatch(second)
    if not first_match or not second_match:
        return None

    def luminance(value: str) -> float:
        red, green, blue = (
            int(value[index : index + 2], 16)
            for index in (0, 2, 4)
        )
        return (
            0.2126 * relative_luminance(red)
            + 0.7152 * relative_luminance(green)
            + 0.0722 * relative_luminance(blue)
        )

    light, dark = sorted(
        (luminance(first_match.group(1)), luminance(second_match.group(1))),
        reverse=True,
    )
    return (light + 0.05) / (dark + 0.05)


def concrete_value(tokens: dict[str, Any], value: Any) -> Any:
    if isinstance(value, str) and TOKEN_REFERENCE.fullmatch(value):
        try:
            return resolve_reference(tokens, value)
        except KeyError:
            return None
    return value


def validate_tokens(tokens: dict[str, Any], result: FileResult) -> None:
    if tokens.get("version") != "alpha":
        result.errors.append("front matter version must be \"alpha\"")
    if not isinstance(tokens.get("name"), str) or not tokens["name"].strip():
        result.errors.append("front matter name must be a non-empty string")
    for group in REQUIRED_GROUPS:
        if not isinstance(tokens.get(group), dict) or not tokens[group]:
            result.errors.append(f"front matter {group} must be a non-empty object")

    colors = tokens.get("colors", {})
    if isinstance(colors, dict):
        if "primary" not in colors:
            result.errors.append("colors must define primary")
        for name, value in colors.items():
            if not isinstance(value, str) or not CSS_COLOR.fullmatch(value):
                result.errors.append(f"colors.{name} is not a supported CSS color")

    typography = tokens.get("typography", {})
    if isinstance(typography, dict):
        for name, value in typography.items():
            if not isinstance(value, dict):
                result.errors.append(f"typography.{name} must be an object")
                continue
            missing = [field for field in TYPOGRAPHY_FIELDS if field not in value]
            if missing:
                result.errors.append(
                    f"typography.{name} is missing fields: {', '.join(missing)}"
                )
            if "fontSize" in value and (
                not isinstance(value["fontSize"], str)
                or not DIMENSION.fullmatch(value["fontSize"])
            ):
                result.errors.append(f"typography.{name}.fontSize must be a dimension")
            if "lineHeight" in value and not (
                isinstance(value["lineHeight"], (int, float))
                or (
                    isinstance(value["lineHeight"], str)
                    and DIMENSION.fullmatch(value["lineHeight"])
                )
            ):
                result.errors.append(
                    f"typography.{name}.lineHeight must be a number or dimension"
                )

    for group in ("rounded", "spacing"):
        values = tokens.get(group, {})
        if not isinstance(values, dict):
            continue
        for name, value in values.items():
            valid = (
                isinstance(value, (int, float)) and group == "spacing"
            ) or (isinstance(value, str) and DIMENSION.fullmatch(value))
            if not valid:
                result.errors.append(
                    f"{group}.{name} must be a dimension"
                    + (" or number" if group == "spacing" else "")
                )

    for reference in all_references(tokens.get("components", {})):
        try:
            resolve_reference(tokens, reference)
        except KeyError:
            result.errors.append(f"broken token reference: {reference}")

    components = tokens.get("components", {})
    if not isinstance(components, dict):
        return
    for name, component in components.items():
        if not isinstance(component, dict):
            result.errors.append(f"components.{name} must be an object")
            continue
        background = concrete_value(tokens, component.get("backgroundColor"))
        text = concrete_value(tokens, component.get("textColor"))
        if isinstance(background, str) and isinstance(text, str):
            ratio = contrast_ratio(background, text)
            if ratio is not None and ratio < 4.5:
                result.errors.append(
                    f"components.{name} contrast ratio {ratio:.2f}:1 is below 4.5:1"
                )


def validate_sections(body: str, result: FileResult) -> None:
    headings = [
        match.group(1).strip()
        for match in re.finditer(r"^## (.+?)\s*$", body, flags=re.MULTILINE)
    ]
    canonical = [SECTION_ALIASES.get(heading, heading) for heading in headings]
    duplicates = sorted(
        {heading for heading in canonical if canonical.count(heading) > 1}
    )
    for heading in duplicates:
        result.errors.append(f"duplicate section heading: {heading}")

    for required in SECTION_ORDER:
        if required not in canonical:
            result.errors.append(f"missing required section: {required}")

    known = [heading for heading in canonical if heading in SECTION_ORDER]
    ordered = sorted(known, key=SECTION_ORDER.index)
    if known != ordered:
        result.errors.append("standard sections are not in canonical order")


def validate_file(path: Path) -> FileResult:
    result = FileResult(path=path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        result.errors.append("file does not exist")
        return result
    except UnicodeDecodeError:
        result.errors.append("file is not valid UTF-8")
        return result
    tokens, body = parse_front_matter(text, result)
    if tokens:
        validate_tokens(tokens, result)
    validate_sections(body, result)
    return result


def default_paths() -> list[Path]:
    try:
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError("design-systems/index.json is missing") from None
    except json.JSONDecodeError as error:
        raise ValueError(
            f"design-systems/index.json is invalid: {error.msg}"
        ) from error
    paths: list[Path] = []
    for system in index.get("systems", []):
        relative = system.get("path")
        if not isinstance(relative, str):
            raise ValueError("design-systems/index.json contains a missing path")
        paths.append(ROOT / relative)
    return paths


def report(results: list[FileResult]) -> dict[str, Any]:
    return {
        "files": [result.payload() for result in results],
        "summary": {
            "files": len(results),
            "errors": sum(len(result.errors) for result in results),
            "warnings": sum(len(result.warnings) for result in results),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    try:
        paths = args.paths or default_paths()
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    results = [validate_file(path.resolve()) for path in paths]
    payload = report(results)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.report_json:
        args.report_json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if payload["summary"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
