#!/usr/bin/env python3
"""Validate lightweight interaction experience checks and HTML action coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROUTES = {"web_hi_fi", "app_flow"}
PATH_TYPES = {"primary", "error", "cancel", "recovery"}
RESET_STRATEGIES = {"function", "reload", "none"}
PERSISTENCE_TYPES = {"none", "session", "local", "documented"}
RESET_SCOPES = {"dom", "url", "scroll", "focus", "timers", "storage"}
ACTION_TYPES = {
    "click",
    "fill",
    "select",
    "toggle",
    "press",
    "focus",
    "blur",
    "submit",
    "back",
    "escape",
    "reload",
    "waitFor",
    "assert",
}
TARGET_ACTION_TYPES = {"click", "fill", "select", "toggle", "focus", "blur", "submit"}
EXPECTATION_KINDS = {
    "screen",
    "state",
    "feedback",
    "visible",
    "hidden",
    "enabled",
    "disabled",
    "text",
    "value",
    "count",
    "focused",
    "accessibleName",
    "role",
    "checked",
    "pressed",
    "expanded",
    "invalid",
    "liveRegion",
    "url",
}
ID_RE = re.compile(r"^EXP-[A-Z0-9_-]+$")
STEP_RE = re.compile(r"^STEP-[A-Z0-9_-]+$")
ACTION_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REQUIREMENT_RE = re.compile(r"^(SCN|STATE|RULE|PERM)-[A-Z0-9_-]+$")
STATE_RE = re.compile(r"^STATE-[A-Z0-9_-]+$")
SCREEN_RE = re.compile(r"^SCREEN-[A-Z0-9_-]+$")
INTERACTIVE_ROLES = {"button", "link", "tab", "switch", "checkbox", "radio", "menuitem"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def canonical_json(checks: dict[str, Any]) -> str:
    return json.dumps(checks, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def checks_hash(checks: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(checks).encode("utf-8")).hexdigest()


def load_checks(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"experience checks do not exist: {source}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"experience checks are not valid JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError("experience checks root must be an object")
    return value


def validate_expectation(value: Any, label: str, errors: list[str]) -> None:
    item = _object(value)
    kind = item.get("kind")
    if kind not in EXPECTATION_KINDS:
        errors.append(f"{label}.kind is invalid: {kind!r}")
        return
    if kind == "screen":
        if not _text(item.get("id")) or not SCREEN_RE.fullmatch(str(item.get("id"))):
            errors.append(f"{label}.id must be a SCREEN-* ID")
    elif kind == "state":
        if not _text(item.get("id")) or not STATE_RE.fullmatch(str(item.get("id"))):
            errors.append(f"{label}.id must be a STATE-* ID")
    elif kind == "feedback":
        if not _text(item.get("value")):
            errors.append(f"{label}.value must contain feedback text")
    elif kind == "url":
        if not _text(item.get("value")):
            errors.append(f"{label}.value must contain a URL expectation")
    else:
        if not _text(item.get("selector")):
            errors.append(f"{label}.selector must be non-empty")
        if kind in {
            "text",
            "value",
            "accessibleName",
            "role",
            "checked",
            "pressed",
            "expanded",
            "invalid",
            "liveRegion",
        } and "value" not in item:
            errors.append(f"{label}.value is required for {kind}")
        if kind == "count" and (
            not isinstance(item.get("count"), int)
            or isinstance(item.get("count"), bool)
            or item.get("count") < 0
        ):
            errors.append(f"{label}.count must be a non-negative integer")
    for field in ("timeoutMs", "pollMs"):
        if field in item and (
            not isinstance(item[field], int)
            or isinstance(item[field], bool)
            or item[field] < (10 if field == "pollMs" else 0)
        ):
            errors.append(f"{label}.{field} is invalid")


def validate_action(value: Any, label: str, errors: list[str]) -> str | None:
    action = _object(value)
    action_type = action.get("type")
    if action_type not in ACTION_TYPES:
        errors.append(f"{label}.type is invalid: {action_type!r}")
        return None
    action_id = action.get("actionId")
    selector = action.get("selector")
    if action_type in TARGET_ACTION_TYPES:
        targets = int(_text(action_id)) + int(_text(selector))
        if targets != 1:
            errors.append(f"{label} requires exactly one actionId or selector")
        if _text(action_id) and not ACTION_RE.fullmatch(str(action_id)):
            errors.append(f"{label}.actionId is invalid")
    elif action_id is not None or selector is not None:
        errors.append(f"{label} {action_type} must not declare actionId or selector")
    if action_type in {"fill", "select"} and not isinstance(action.get("value"), str):
        errors.append(f"{label} {action_type} requires a string value")
    if action_type == "toggle" and not isinstance(action.get("value"), bool):
        errors.append(f"{label} toggle requires a boolean value")
    if action_type == "press" and not _text(action.get("key")):
        errors.append(f"{label} press requires key")
    return str(action_id) if _text(action_id) else None


def validate_checks(checks: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("schemaVersion", "deliveryRoute", "pathCoverage", "reset", "scenarios"):
        if field not in checks:
            errors.append(f"experience checks are missing {field}")
    if checks.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")
    if checks.get("deliveryRoute") not in ROUTES:
        errors.append("deliveryRoute must be web_hi_fi or app_flow")

    coverage = _object(checks.get("pathCoverage"))
    required_paths = _list(coverage.get("required"))
    if "primary" not in required_paths:
        errors.append("pathCoverage.required must include primary")
    if len(required_paths) != len(set(required_paths)):
        errors.append("pathCoverage.required must not contain duplicates")
    for path_type in required_paths:
        if path_type not in PATH_TYPES:
            errors.append(f"pathCoverage.required contains invalid path {path_type!r}")
    omitted_paths: list[str] = []
    for index, raw in enumerate(_list(coverage.get("notApplicable"))):
        item = _object(raw)
        label = f"pathCoverage.notApplicable[{index}]"
        path_type = item.get("type")
        if path_type not in PATH_TYPES:
            errors.append(f"{label}.type is invalid")
        else:
            omitted_paths.append(str(path_type))
        if not _text(item.get("reason")):
            errors.append(f"{label}.reason must be non-empty")
    if len(omitted_paths) != len(set(omitted_paths)):
        errors.append("pathCoverage.notApplicable must not contain duplicates")
    overlap = set(required_paths) & set(omitted_paths)
    if overlap:
        errors.append("path coverage cannot be both required and not applicable: " + ", ".join(sorted(overlap)))
    missing_paths = PATH_TYPES - set(required_paths) - set(omitted_paths)
    if missing_paths:
        errors.append("path coverage is incomplete: " + ", ".join(sorted(missing_paths)))

    reset = _object(checks.get("reset"))
    strategy = reset.get("strategy")
    if strategy not in RESET_STRATEGIES:
        errors.append("reset.strategy is invalid")
    if strategy == "function" and reset.get("functionName") != "__DEMO_RESET__":
        errors.append("reset.functionName must be __DEMO_RESET__ for function reset")
    if strategy != "function" and "functionName" in reset:
        errors.append("reset.functionName is only valid for function reset")
    if not isinstance(reset.get("betweenScenarios"), bool):
        errors.append("reset.betweenScenarios must be boolean")
    if reset.get("persistence") not in PERSISTENCE_TYPES:
        errors.append("reset.persistence is invalid")
    scope = _list(reset.get("scope"))
    if len(scope) != len(set(scope)) or not set(scope).issubset(RESET_SCOPES):
        errors.append("reset.scope contains duplicates or invalid values")
    reset_expectations = _list(reset.get("expectations"))
    for index, expectation in enumerate(reset_expectations):
        validate_expectation(expectation, f"reset.expectations[{index}]", errors)

    scenarios = _list(checks.get("scenarios"))
    if not scenarios:
        errors.append("scenarios must not be empty")
    scenario_ids: set[str] = set()
    step_ids: set[str] = set()
    scenario_path_types: list[str] = []
    for scenario_index, raw in enumerate(scenarios):
        scenario = _object(raw)
        label = f"scenarios[{scenario_index}]"
        scenario_id = scenario.get("id")
        if not _text(scenario_id) or not ID_RE.fullmatch(str(scenario_id)):
            errors.append(f"{label}.id must be an EXP-* ID")
        elif scenario_id in scenario_ids:
            errors.append(f"duplicate scenario id: {scenario_id}")
        else:
            scenario_ids.add(str(scenario_id))
        if not _text(scenario.get("title")) or not _text(scenario.get("expectedOutcome")):
            errors.append(f"{label} title and expectedOutcome must be non-empty")
        path_type = scenario.get("pathType")
        if path_type not in required_paths:
            errors.append(f"{label}.pathType must be declared required")
        else:
            scenario_path_types.append(str(path_type))
        requirement_ids = _list(scenario.get("requirementIds"))
        for requirement_id in requirement_ids:
            if not _text(requirement_id) or not REQUIREMENT_RE.fullmatch(str(requirement_id)):
                errors.append(f"{label}.requirementIds contains invalid ID {requirement_id!r}")
        steps = _list(scenario.get("steps"))
        if not steps:
            errors.append(f"{label}.steps must not be empty")
        for step_index, raw_step in enumerate(steps):
            step = _object(raw_step)
            step_label = f"{label}.steps[{step_index}]"
            step_id = step.get("id")
            if not _text(step_id) or not STEP_RE.fullmatch(str(step_id)):
                errors.append(f"{step_label}.id must be a STEP-* ID")
            elif step_id in step_ids:
                errors.append(f"duplicate step id: {step_id}")
            else:
                step_ids.add(str(step_id))
            validate_action(step.get("action"), f"{step_label}.action", errors)
            expectations = _list(step.get("expectations"))
            if not expectations:
                errors.append(f"{step_label}.expectations must not be empty")
            for expectation_index, expectation in enumerate(expectations):
                validate_expectation(
                    expectation,
                    f"{step_label}.expectations[{expectation_index}]",
                    errors,
                )
            verifies = _list(step.get("verifiesRequirementIds"))
            for requirement_id in verifies:
                if requirement_id not in requirement_ids:
                    errors.append(
                        f"{step_label}.verifiesRequirementIds references "
                        f"undeclared scenario requirement {requirement_id!r}"
                    )
            screenshot = _object(step.get("screenshot"))
            if not _text(screenshot.get("label")) or not ACTION_RE.fullmatch(
                str(screenshot.get("label", ""))
            ):
                errors.append(f"{step_label}.screenshot.label is invalid")
            if "stateId" in screenshot and not STATE_RE.fullmatch(
                str(screenshot.get("stateId", ""))
            ):
                errors.append(f"{step_label}.screenshot.stateId must be STATE-*")
    for path_type in sorted(set(required_paths) - set(scenario_path_types)):
        errors.append(f"required path has no scenario: {path_type}")
    if len(scenarios) > 1 and (
        strategy == "none" or reset.get("betweenScenarios") is not True
    ):
        errors.append("multiple scenarios require reset between scenarios")
    return errors


class ExperienceHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.action_ids: list[str] = []
        self.controls: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        action_id = attributes.get("data-action-id")
        if action_id:
            self.action_ids.append(str(action_id))
        input_type = str(attributes.get("type") or "").lower()
        role = str(attributes.get("role") or "").lower()
        tabindex = attributes.get("tabindex")
        interactive = (
            tag in {"button", "select", "textarea"}
            or (tag == "input" and input_type != "hidden")
            or (tag == "a" and "href" in attributes)
            or role in INTERACTIVE_ROLES
            or (tabindex is not None and str(tabindex) != "-1")
        )
        if not interactive:
            return
        self.controls.append(
            {
                "tag": tag,
                "actionId": str(action_id) if action_id else None,
                "disabled": "disabled" in attributes
                or str(attributes.get("aria-disabled") or "").lower() == "true",
                "outOfScope": attributes.get("data-demo-scope") == "out-of-scope",
                "scopeReason": attributes.get("data-demo-scope-reason"),
            }
        )


def validate_html(checks: dict[str, Any], html_path: str | Path) -> list[str]:
    path = Path(html_path)
    try:
        html = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"HTML does not exist: {path}"]
    parser = ExperienceHTMLParser()
    parser.feed(html)
    errors: list[str] = []
    expected_actions = {
        str(action.get("actionId"))
        for scenario in _list(checks.get("scenarios"))
        for step in _list(_object(scenario).get("steps"))
        for action in [_object(_object(step).get("action"))]
        if _text(action.get("actionId"))
    }
    actual_actions = set(parser.action_ids)
    for action_id in sorted(expected_actions - actual_actions):
        errors.append(f"HTML is missing declared experience action: {action_id}")
    for action_id in sorted(actual_actions - expected_actions):
        controls = [item for item in parser.controls if item["actionId"] == action_id]
        if any(not item["disabled"] and not item["outOfScope"] for item in controls):
            errors.append(f"HTML contains untested active action: {action_id}")
    for action_id in sorted({value for value in actual_actions if parser.action_ids.count(value) > 1}):
        errors.append(f"HTML contains duplicate experience action: {action_id}")
    for index, control in enumerate(parser.controls):
        if control["disabled"]:
            continue
        if control["outOfScope"]:
            if not _text(control["scopeReason"]):
                errors.append(
                    f"interactive control {index + 1} marked out-of-scope needs data-demo-scope-reason"
                )
            continue
        if not control["actionId"]:
            errors.append(
                f"active {control['tag']} control {index + 1} needs data-action-id, disabled, or out-of-scope marker"
            )
    return errors


def build_report(
    checks: dict[str, Any],
    errors: list[str],
    html_path: str | Path | None = None,
) -> dict[str, Any]:
    required_paths = set(_list(_object(checks.get("pathCoverage")).get("required")))
    covered_paths = {
        str(_object(item).get("pathType"))
        for item in _list(checks.get("scenarios"))
        if _text(_object(item).get("pathType"))
    }
    action_ids = {
        str(action.get("actionId"))
        for scenario in _list(checks.get("scenarios"))
        for step in _list(_object(scenario).get("steps"))
        for action in [_object(_object(step).get("action"))]
        if _text(action.get("actionId"))
    }
    return {
        "status": "failed" if errors else "passed",
        "schemaVersion": checks.get("schemaVersion"),
        "checksHash": checks_hash(checks),
        "deliveryRoute": checks.get("deliveryRoute"),
        "coverage": {
            "requiredPaths": sorted(required_paths),
            "coveredPaths": sorted(required_paths & covered_paths),
            "scenarios": len(_list(checks.get("scenarios"))),
            "actions": len(action_ids),
        },
        "html": str(html_path) if html_path else None,
        "errors": errors,
    }


def write_report(path: str | Path | None, report: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate demo-design experience checks")
    parser.add_argument("checks", type=Path)
    parser.add_argument("--html", type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args(argv)
    try:
        checks = load_checks(args.checks)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    errors = validate_checks(checks)
    if args.html:
        errors.extend(validate_html(checks, args.html))
    report = build_report(checks, errors, args.html)
    write_report(args.report_json, report)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        "OK: experience checks valid "
        f"({len(report['coverage']['coveredPaths'])}/"
        f"{len(report['coverage']['requiredPaths'])} paths covered)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
