#!/usr/bin/env python3
"""Validate generation-time design-guidance sidecar artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ROUTES = {"web_hi_fi", "app_flow"}
SOURCE_STATUSES = {"exact", "approximate", "assumption"}
SCHEMA_VERSIONS = {1, 2, 3}
LEGACY_RULE_STATUSES = {"passed", "not_applicable"}
RULE_APPLICABILITIES = {"required", "not_applicable"}
DECISION_LEVELS = {"contextual", "advisory"}
STATE_IDS = {
    "default",
    "hover",
    "focus",
    "pressed",
    "disabled",
    "loading",
    "empty",
    "error",
    "success",
}
PRODUCT_CONTRACT_REF_RE = re.compile(r"^(SCN|STATE|UI)-[A-Z0-9_-]+$")
DESIGN_SOURCE_REF_RE = re.compile(r"^DSRC-[A-Z0-9_-]+$")
VISUAL_ANCHOR_RE = re.compile(r"^VANCHOR-[A-Z0-9_-]+$")
HARD_RULES = {
    "GUIDE-FORM-LABELS": {
        "routes": ["web_hi_fi", "app_flow"],
        "evidence_type": "browser",
        "allow_not_applicable": True,
    },
    "GUIDE-FOCUS-VISIBILITY": {
        "routes": ["web_hi_fi", "app_flow"],
        "evidence_type": "browser",
        "allow_not_applicable": True,
    },
    "GUIDE-TARGET-SIZE": {
        "routes": ["web_hi_fi", "app_flow"],
        "evidence_type": "browser",
        "allow_not_applicable": True,
        "minimum_css_pixels": {"web_hi_fi": 24, "app_flow": 44},
    },
    "GUIDE-HORIZONTAL-OVERFLOW": {
        "routes": ["web_hi_fi", "app_flow"],
        "evidence_type": "browser",
        "allow_not_applicable": False,
    },
    "GUIDE-IMAGE-ALTERNATIVES": {
        "routes": ["web_hi_fi", "app_flow"],
        "evidence_type": "browser",
        "allow_not_applicable": True,
    },
    "GUIDE-REDUCED-MOTION": {
        "routes": ["web_hi_fi", "app_flow"],
        "evidence_type": "browser",
        "allow_not_applicable": True,
    },
    "GUIDE-CRITICAL-STATES": {
        "routes": ["web_hi_fi", "app_flow"],
        "evidence_type": "experience",
        "allow_not_applicable": True,
    },
    "GUIDE-COLOR-INDEPENDENCE": {
        "routes": ["web_hi_fi", "app_flow"],
        "evidence_type": "authored",
        "allow_not_applicable": True,
    },
    "GUIDE-VISUAL-ANCHORS": {
        "routes": ["web_hi_fi", "app_flow"],
        "evidence_type": "browser",
        "allow_not_applicable": False,
        "since_schema_version": 3,
    },
}
INTENT_FIELDS = ("primaryUser", "primaryTask", "successOutcome", "contentPriority")
SOURCE_TRACKED_INTENT_FIELDS = ("primaryUser", "primaryTask", "successOutcome")
DIRECTION_FIELDS_LEGACY = (
    "designSystem",
    "rationale",
    "layoutStrategy",
    "hierarchyStrategy",
    "responsiveStrategy",
    "componentStrategy",
)
DIRECTION_FIELDS_V3 = (
    "designBasis",
    "visualDials",
    "rationale",
    "layoutStrategy",
    "hierarchyStrategy",
    "responsiveStrategy",
    "componentStrategy",
)
CONSTRAINT_FIELDS = ("must", "avoid", "accessibility")
DESIGN_BASIS_TYPES = {"core", "external", "existing"}
VISUAL_DIAL_VALUES = {
    "variance": {"restrained", "balanced", "expressive"},
    "density": {"spacious", "balanced", "dense"},
    "motion": {"none", "restrained", "expressive"},
}
VISUAL_ANCHOR_PRIORITIES = {"blocking", "important", "supporting"}
VISUAL_ANCHOR_CHECKS = {
    "visible",
    "unique",
    "no_clipping",
    "hierarchy",
    "rhythm",
    "state_distinct",
}
LEGACY_DECLARED_RULES = {
    "GUIDE-CRITICAL-STATES",
    "GUIDE-COLOR-INDEPENDENCE",
}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _require_keys(
    value: dict[str, Any],
    keys: tuple[str, ...],
    label: str,
    errors: list[str],
) -> None:
    for key in keys:
        if key not in value:
            errors.append(f"{label} is missing {key}")


def _validate_text_list(value: Any, label: str, errors: list[str], minimum: int = 1) -> list[str]:
    items = _list(value)
    if len(items) < minimum:
        errors.append(f"{label} must contain at least {minimum} item(s)")
    normalized: list[str] = []
    for index, item in enumerate(items):
        if not _text(item):
            errors.append(f"{label}[{index}] must be a non-empty string")
        else:
            normalized.append(str(item).strip())
    if len(normalized) != len(set(normalized)):
        errors.append(f"{label} must not contain duplicates")
    return normalized


def load_guidance(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"design guidance does not exist: {source}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"design guidance is not valid JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError("design guidance root must be an object")
    return value


def core_design_systems() -> set[str]:
    path = ROOT / "design-systems" / "index.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError("design-systems/index.json is missing") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"design-systems/index.json is invalid: {error.msg}") from error
    return {
        str(item.get("id"))
        for item in _list(payload.get("systems"))
        if _text(_object(item).get("id")) and _object(item).get("core") is True
    }


def applicable_rule_ids(route: str, schema_version: int = 3) -> set[str]:
    return {
        rule_id
        for rule_id, rule in HARD_RULES.items()
        if route in rule["routes"]
        and int(rule.get("since_schema_version", 1)) <= schema_version
    }


def rule_evidence_type(guidance: dict[str, Any], rule_id: str) -> str | None:
    if guidance.get("schemaVersion") in {1, 2} and rule_id in LEGACY_DECLARED_RULES:
        return "declared"
    rule = HARD_RULES.get(rule_id, {})
    value = rule.get("evidence_type")
    return str(value) if _text(value) else None


def normalized_rule_declarations(guidance: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    if guidance.get("schemaVersion") != 3:
        return result
    for raw in _list(guidance.get("hardRules")):
        item = _object(raw)
        rule_id = item.get("id")
        declaration = item.get("declaration")
        if _text(rule_id) and _text(declaration):
            result[str(rule_id)] = str(declaration).strip()
    return result


def normalized_rule_applicabilities(
    guidance: dict[str, Any],
) -> dict[str, str]:
    schema_version = guidance.get("schemaVersion")
    result: dict[str, str] = {}
    for raw in _list(guidance.get("hardRules")):
        item = _object(raw)
        rule_id = item.get("id")
        if not _text(rule_id):
            continue
        if schema_version == 1:
            status = item.get("status")
            if status in LEGACY_RULE_STATUSES:
                result[str(rule_id)] = (
                    "required" if status == "passed" else "not_applicable"
                )
        elif schema_version in {2, 3}:
            applicability = item.get("applicability")
            if applicability in RULE_APPLICABILITIES:
                result[str(rule_id)] = str(applicability)
    return result


def validate_guidance(guidance: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    schema_version = guidance.get("schemaVersion")
    required_guidance_fields = [
        "schemaVersion",
        "deliveryRoute",
        "intent",
        "direction",
        "states",
        "constraints",
        "decisions",
        "hardRules",
        "decisionSummary",
    ]
    if schema_version == 3:
        required_guidance_fields.append("visualAnchors")
    _require_keys(
        guidance,
        tuple(required_guidance_fields),
        "guidance",
        errors,
    )
    if schema_version not in SCHEMA_VERSIONS:
        errors.append("schemaVersion must be 1, 2 or 3")
    route = guidance.get("deliveryRoute")
    if route not in ROUTES:
        errors.append(f"deliveryRoute must be one of {', '.join(sorted(ROUTES))}")

    intent = _object(guidance.get("intent"))
    _require_keys(intent, INTENT_FIELDS, "intent", errors)
    for field in SOURCE_TRACKED_INTENT_FIELDS:
        item = _object(intent.get(field))
        if not _text(item.get("value")):
            errors.append(f"intent.{field}.value must be non-empty")
        if item.get("sourceStatus") not in SOURCE_STATUSES:
            errors.append(f"intent.{field}.sourceStatus is invalid")
    _validate_text_list(intent.get("contentPriority"), "intent.contentPriority", errors)

    direction = _object(guidance.get("direction"))
    direction_fields = (
        DIRECTION_FIELDS_V3 if schema_version == 3 else DIRECTION_FIELDS_LEGACY
    )
    _require_keys(direction, direction_fields, "direction", errors)
    try:
        known_systems = core_design_systems()
    except ValueError as error:
        errors.append(str(error))
        known_systems = set()
    if schema_version == 3:
        basis = _object(direction.get("designBasis"))
        basis_type = basis.get("type")
        if basis_type not in DESIGN_BASIS_TYPES:
            errors.append("direction.designBasis.type must be core, external or existing")
        elif basis_type == "core":
            if basis.get("systemId") not in known_systems:
                errors.append(
                    "direction.designBasis.systemId must reference a Core system: "
                    f"{basis.get('systemId')!r}"
                )
        elif basis_type == "external":
            source_ids = _list(basis.get("sourceIds"))
            if not source_ids:
                errors.append("direction.designBasis.sourceIds must not be empty")
            for index, source_id in enumerate(source_ids):
                if not _text(source_id) or not DESIGN_SOURCE_REF_RE.fullmatch(
                    str(source_id)
                ):
                    errors.append(
                        "direction.designBasis.sourceIds"
                        f"[{index}] must be a DSRC-* ID"
                    )
        elif basis_type == "existing":
            design_document = basis.get("designDocument")
            if not _text(design_document):
                errors.append(
                    "direction.designBasis.designDocument must be non-empty"
                )
            else:
                relative = Path(str(design_document))
                if relative.is_absolute() or ".." in relative.parts:
                    errors.append(
                        "direction.designBasis.designDocument must be a safe relative path"
                    )
        visual_dials = _object(direction.get("visualDials"))
        _require_keys(
            visual_dials,
            tuple(VISUAL_DIAL_VALUES),
            "direction.visualDials",
            errors,
        )
        for dial, allowed in VISUAL_DIAL_VALUES.items():
            if visual_dials.get(dial) not in allowed:
                errors.append(
                    f"direction.visualDials.{dial} is invalid: "
                    f"{visual_dials.get(dial)!r}"
                )
    elif direction.get("designSystem") not in known_systems:
        errors.append(
            f"direction.designSystem must reference a Core system: "
            f"{direction.get('designSystem')!r}"
        )
    for field in direction_fields[2 if schema_version == 3 else 1:]:
        if not _text(direction.get(field)):
            errors.append(f"direction.{field} must be non-empty")

    if schema_version == 3:
        anchors = _list(guidance.get("visualAnchors"))
        if not anchors:
            errors.append("visualAnchors must contain at least one anchor")
        seen_anchor_ids: set[str] = set()
        seen_anchor_selectors: set[str] = set()
        for index, raw in enumerate(anchors):
            item = _object(raw)
            label = f"visualAnchors[{index}]"
            anchor_id = item.get("id")
            selector = item.get("selector")
            if not _text(anchor_id) or not VISUAL_ANCHOR_RE.fullmatch(str(anchor_id)):
                errors.append(f"{label}.id must be a VANCHOR-* ID")
            elif anchor_id in seen_anchor_ids:
                errors.append(f"duplicate visual anchor id: {anchor_id}")
            else:
                seen_anchor_ids.add(str(anchor_id))
            if not _text(selector):
                errors.append(f"{label}.selector must be non-empty")
            elif selector in seen_anchor_selectors:
                errors.append(f"duplicate visual anchor selector: {selector}")
            else:
                seen_anchor_selectors.add(str(selector))
            if not _text(item.get("role")):
                errors.append(f"{label}.role must be non-empty")
            if item.get("priority") not in VISUAL_ANCHOR_PRIORITIES:
                errors.append(f"{label}.priority is invalid")
            checks = _list(item.get("checks"))
            if not checks:
                errors.append(f"{label}.checks must not be empty")
            for check in checks:
                if check not in VISUAL_ANCHOR_CHECKS:
                    errors.append(f"{label}.checks contains invalid value {check!r}")
            if len(checks) != len(set(checks)):
                errors.append(f"{label}.checks must not contain duplicates")

    seen_states: set[str] = set()
    for index, raw in enumerate(_list(guidance.get("states"))):
        item = _object(raw)
        label = f"states[{index}]"
        state_id = item.get("id")
        if state_id not in STATE_IDS:
            errors.append(f"{label}.id is invalid: {state_id!r}")
        elif state_id in seen_states:
            errors.append(f"duplicate state id: {state_id}")
        else:
            seen_states.add(str(state_id))
        if not isinstance(item.get("required"), bool):
            errors.append(f"{label}.required must be boolean")
        if not _text(item.get("realization")):
            errors.append(f"{label}.realization must be non-empty")

    constraints = _object(guidance.get("constraints"))
    _require_keys(constraints, CONSTRAINT_FIELDS, "constraints", errors)
    for field in CONSTRAINT_FIELDS:
        _validate_text_list(constraints.get(field), f"constraints.{field}", errors)

    decisions = _list(guidance.get("decisions"))
    if not decisions:
        errors.append("decisions must contain at least one decision")
    for index, raw in enumerate(decisions):
        item = _object(raw)
        label = f"decisions[{index}]"
        if item.get("level") not in DECISION_LEVELS:
            errors.append(f"{label}.level must be contextual or advisory")
        if not _text(item.get("decision")):
            errors.append(f"{label}.decision must be non-empty")
        if not _text(item.get("rationale")):
            errors.append(f"{label}.rationale must be non-empty")

    expected_rules = (
        applicable_rule_ids(str(route), int(schema_version))
        if route in ROUTES and schema_version in SCHEMA_VERSIONS
        else set()
    )
    seen_rules: set[str] = set()
    for index, raw in enumerate(_list(guidance.get("hardRules"))):
        item = _object(raw)
        label = f"hardRules[{index}]"
        rule_id = item.get("id")
        if rule_id not in HARD_RULES:
            errors.append(f"{label}.id is unknown: {rule_id!r}")
            continue
        if rule_id not in expected_rules:
            errors.append(f"{label}.id does not apply to {route}: {rule_id}")
        if rule_id in seen_rules:
            errors.append(f"duplicate hard rule: {rule_id}")
        seen_rules.add(str(rule_id))
        if schema_version == 1:
            status = item.get("status")
            if status not in LEGACY_RULE_STATUSES:
                errors.append(f"{label}.status must be passed or not_applicable")
            elif (
                status == "not_applicable"
                and not HARD_RULES[str(rule_id)]["allow_not_applicable"]
            ):
                errors.append(f"{rule_id} cannot be not_applicable")
            if not _text(item.get("evidence")):
                errors.append(f"{label}.evidence must be non-empty")
        elif schema_version in {2, 3}:
            applicability = item.get("applicability")
            if applicability not in RULE_APPLICABILITIES:
                errors.append(
                    f"{label}.applicability must be required or not_applicable"
                )
            elif (
                applicability == "not_applicable"
                and not HARD_RULES[str(rule_id)]["allow_not_applicable"]
            ):
                errors.append(f"{rule_id} cannot be not_applicable")
            if not _text(item.get("reason")):
                errors.append(f"{label}.reason must be non-empty")
            if "status" in item or "evidence" in item:
                errors.append(
                    f"{label} must not contain validation status or evidence"
                )
            evidence_type = rule_evidence_type(guidance, str(rule_id))
            if (
                schema_version == 3
                and applicability == "required"
                and evidence_type == "authored"
                and not _text(item.get("declaration"))
            ):
                errors.append(
                    f"{label}.declaration is required for authored evidence"
                )
            if evidence_type != "authored" and "declaration" in item:
                errors.append(
                    f"{label}.declaration is only valid for authored evidence"
                )
    for rule_id in sorted(expected_rules - seen_rules):
        errors.append(f"missing applicable hard rule: {rule_id}")

    summaries = _validate_text_list(
        guidance.get("decisionSummary"),
        "decisionSummary",
        errors,
        minimum=5,
    )
    if len(summaries) > 8:
        errors.append("decisionSummary must contain at most 8 items")

    for index, reference in enumerate(_list(guidance.get("productContractRefs"))):
        if not _text(reference) or not PRODUCT_CONTRACT_REF_RE.fullmatch(str(reference)):
            errors.append(
                f"productContractRefs[{index}] must be an SCN-*, STATE-* or UI-* ID"
            )
    return errors


def build_report(guidance: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    route = guidance.get("deliveryRoute")
    schema_version = guidance.get("schemaVersion")
    expected = (
        applicable_rule_ids(str(route), int(schema_version))
        if route in ROUTES and schema_version in SCHEMA_VERSIONS
        else set()
    )
    actual = {
        str(_object(item).get("id"))
        for item in _list(guidance.get("hardRules"))
        if _object(item).get("id") in expected
    }
    return {
        "status": "failed" if errors else "passed",
        "schemaVersion": guidance.get("schemaVersion"),
        "compatibility": (
            "legacy-v1"
            if schema_version == 1
            else "legacy-v2"
            if schema_version == 2
            else "current"
        ),
        "deliveryRoute": route,
        "designBasis": (
            _object(_object(guidance.get("direction")).get("designBasis"))
            if schema_version == 3
            else {
                "type": "core",
                "systemId": _object(guidance.get("direction")).get("designSystem"),
            }
        ),
        "visualDials": _object(guidance.get("direction")).get("visualDials"),
        "coverage": {
            "hardRules": {
                "required": len(expected),
                "declared": len(actual),
                "applicability": normalized_rule_applicabilities(guidance),
            },
            "visualAnchors": len(_list(guidance.get("visualAnchors"))),
            "decisionSummary": len(_list(guidance.get("decisionSummary"))),
        },
        "errors": errors,
    }


def write_report(path: str | Path, report: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("guidance_path")
    parser.add_argument("--report-json", default=None)
    args = parser.parse_args(argv)
    try:
        guidance = load_guidance(args.guidance_path)
        errors = validate_guidance(guidance)
        report = build_report(guidance, errors)
        if args.report_json:
            write_report(args.report_json, report)
    except (ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        "OK: design guidance valid "
        f"({report['coverage']['hardRules']['declared']} hard rules)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
