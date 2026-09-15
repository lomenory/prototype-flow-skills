#!/usr/bin/env python3
"""Validate product-contract artifacts and requirement-to-UI traceability."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROUTES = {"web_hi_fi", "app_flow", "design_review"}
STATUSES = {"confirmed", "assumption", "open_question"}
SOURCE_KINDS = {"document", "conversation", "repository", "assumption"}
DENIED_BEHAVIORS = {"hidden", "disabled", "message", "request_access"}
REQUIREMENT_GROUPS = {
    "scenarios": "SCN-",
    "fields": "FIELD-",
    "states": "STATE-",
    "permissions": "PERM-",
    "rules": "RULE-",
}
ID_RE = re.compile(r"^[A-Z]+-[A-Z0-9_-]+$")
ACTION_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REVISION_RE = re.compile(r"^REV-[A-Z0-9_-]+$")
REQUIREMENT_ID_RE = re.compile(r"^(SCN|FIELD|STATE|PERM|RULE)-[A-Z0-9_-]+$")
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
TRANSITION_PHASES = {"pending", "success", "failure", "cancel", "recovery"}
RESET_STRATEGIES = {"function", "reload", "none"}
PERSISTENCE_TYPES = {"none", "session", "local", "documented"}
RESET_SCOPES = {"dom", "url", "scroll", "focus", "timers", "storage"}
FORBIDDEN_FRONTEND_CONTRACT_ATTRIBUTES = {
    "data-contract-hash",
    "data-contract-review",
    "data-product-contract",
    "data-product-contract-close",
    "data-product-contract-locate",
    "data-product-contract-open",
    "data-product-contract-overlay",
    "data-product-contract-review-bar",
    "data-product-contract-runtime",
}


def canonical_json(contract: dict[str, Any]) -> str:
    return json.dumps(
        contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def contract_hash(contract: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(contract).encode("utf-8")).hexdigest()


def load_contract(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"contract does not exist: {source}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"contract is not valid JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError("contract root must be an object")
    return value


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _require_keys(value: dict[str, Any], keys: tuple[str, ...], label: str, errors: list[str]) -> None:
    for key in keys:
        if key not in value:
            errors.append(f"{label} is missing {key}")


def _validate_id(
    value: Any,
    prefix: str,
    label: str,
    seen: set[str],
    errors: list[str],
) -> str | None:
    if not _text(value) or not str(value).startswith(prefix) or not ID_RE.fullmatch(str(value)):
        errors.append(f"{label} has invalid id {value!r}; expected {prefix}*")
        return None
    identifier = str(value)
    if identifier in seen:
        errors.append(f"duplicate id: {identifier}")
    seen.add(identifier)
    return identifier


def _validate_trace(
    item: dict[str, Any],
    label: str,
    source_ids: set[str],
    errors: list[str],
) -> None:
    if not isinstance(item.get("critical"), bool):
        errors.append(f"{label} critical must be boolean")
    if item.get("status") not in STATUSES:
        errors.append(f"{label} has invalid status {item.get('status')!r}")
    if item.get("sourceRef") not in source_ids:
        errors.append(f"{label} references unknown source {item.get('sourceRef')!r}")


def _validate_expectation(
    expectation: dict[str, Any],
    label: str,
    screen_ids: set[str],
    requirements_by_id: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    kind = expectation.get("kind")
    if kind not in EXPECTATION_KINDS:
        errors.append(f"{label} has invalid kind {kind!r}")
        return
    if kind == "screen":
        if expectation.get("id") not in screen_ids:
            errors.append(
                f"{label} references unknown screen {expectation.get('id')!r}"
            )
    elif kind == "state":
        if expectation.get("id") not in requirements_by_id or not str(
            expectation.get("id", "")
        ).startswith("STATE-"):
            errors.append(
                f"{label} references unknown state {expectation.get('id')!r}"
            )
    elif kind == "feedback":
        if not _text(expectation.get("value")):
            errors.append(f"{label} feedback requires a text value")
    elif kind == "url":
        if not _text(expectation.get("value")):
            errors.append(f"{label} url requires a text value")
    else:
        if not _text(expectation.get("selector")):
            errors.append(f"{label} {kind} requires selector")
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
        } and "value" not in expectation:
            errors.append(f"{label} {kind} requires value")
        if kind == "count" and (
            not isinstance(expectation.get("count"), int)
            or isinstance(expectation.get("count"), bool)
            or expectation.get("count") < 0
        ):
            errors.append(f"{label} count requires a non-negative integer")
    for field in ("timeoutMs", "pollMs"):
        if field in expectation and (
            not isinstance(expectation[field], int)
            or isinstance(expectation[field], bool)
            or expectation[field] < (10 if field == "pollMs" else 0)
        ):
            errors.append(f"{label} {field} is invalid")


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    schema_version = contract.get("schemaVersion")
    required_contract_fields = [
        "schemaVersion",
        "product",
        "route",
        "readiness",
        "sources",
        "requirements",
        "realization",
        "acceptance",
    ]
    if schema_version == 3:
        required_contract_fields.append("interaction")
    _require_keys(
        contract,
        tuple(required_contract_fields),
        "contract",
        errors,
    )
    if schema_version not in {1, 2, 3}:
        errors.append("schemaVersion must be 1, 2 or 3")
    if not _text(contract.get("product")):
        errors.append("product must be a non-empty string")
    if contract.get("route") not in ROUTES:
        errors.append(f"route must be one of {', '.join(sorted(ROUTES))}")
    if contract.get("readiness") not in {"ready", "blocked"}:
        errors.append("readiness must be ready or blocked")

    revision = _object(contract.get("revision"))
    change_set = _object(contract.get("changeSet"))
    if schema_version == 1:
        if revision or change_set or contract.get("interaction"):
            errors.append(
                "schemaVersion 1 must not contain revision, changeSet or interaction"
            )
    elif schema_version in {2, 3}:
        if not revision:
            errors.append(f"schemaVersion {schema_version} requires revision")
        if not change_set:
            errors.append(f"schemaVersion {schema_version} requires changeSet")
        revision_id = revision.get("id")
        if not _text(revision_id) or not REVISION_RE.fullmatch(str(revision_id)):
            errors.append("revision.id must use REV-* format")
        sequence = revision.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            errors.append("revision.sequence must be a positive integer")
        if not _text(revision.get("summary")):
            errors.append("revision.summary must be non-empty")
        decisions = _list(change_set.get("decisionSummary"))
        if not decisions or any(not _text(item) for item in decisions):
            errors.append("changeSet.decisionSummary must contain non-empty decisions")
        if schema_version == 2 and contract.get("interaction"):
            errors.append("schemaVersion 2 must not contain interaction")

    retired_requirement_ids: set[str] = set()
    for key in ("supersedesRequirementIds", "removedRequirementIds"):
        values = _list(change_set.get(key))
        if len(values) != len(set(str(item) for item in values)):
            errors.append(f"changeSet.{key} must not contain duplicates")
        for value in values:
            if not _text(value) or not REQUIREMENT_ID_RE.fullmatch(str(value)):
                errors.append(f"changeSet.{key} contains invalid requirement id {value!r}")
            else:
                retired_requirement_ids.add(str(value))

    all_ids: set[str] = set()
    sources = _list(contract.get("sources"))
    if not sources:
        errors.append("sources must contain at least one source")
    source_ids: set[str] = set()
    for index, raw in enumerate(sources):
        item = _object(raw)
        label = f"sources[{index}]"
        identifier = _validate_id(item.get("id"), "SRC-", label, all_ids, errors)
        if identifier:
            source_ids.add(identifier)
        if item.get("kind") not in SOURCE_KINDS:
            errors.append(f"{label} has invalid kind {item.get('kind')!r}")
        if not _text(item.get("label")):
            errors.append(f"{label} label must be non-empty")

    requirements = _object(contract.get("requirements"))
    _require_keys(
        requirements,
        ("actors", "scenarios", "fields", "states", "permissions", "rules", "openQuestions"),
        "requirements",
        errors,
    )

    actor_ids: set[str] = set()
    for index, raw in enumerate(_list(requirements.get("actors"))):
        item = _object(raw)
        label = f"actors[{index}]"
        identifier = _validate_id(item.get("id"), "ACT-", label, all_ids, errors)
        if identifier:
            actor_ids.add(identifier)
        if not _text(item.get("name")):
            errors.append(f"{label} name must be non-empty")
        _validate_trace(item, label, source_ids, errors)

    requirement_ids: set[str] = set()
    requirements_by_id: dict[str, dict[str, Any]] = {}
    for group, prefix in REQUIREMENT_GROUPS.items():
        for index, raw in enumerate(_list(requirements.get(group))):
            item = _object(raw)
            label = f"{group}[{index}]"
            identifier = _validate_id(item.get("id"), prefix, label, all_ids, errors)
            if identifier:
                requirement_ids.add(identifier)
                requirements_by_id[identifier] = item
            _validate_trace(item, label, source_ids, errors)
            if group == "scenarios":
                if not _text(item.get("title")) or not _text(item.get("outcome")):
                    errors.append(f"{label} title and outcome must be non-empty")
                if not isinstance(item.get("interactive"), bool):
                    errors.append(f"{label} interactive must be boolean")
                referenced_actors = _list(item.get("actorIds"))
                if not referenced_actors:
                    errors.append(f"{label} actorIds must not be empty")
                for actor_id in referenced_actors:
                    if actor_id not in actor_ids:
                        errors.append(f"{label} references unknown actor {actor_id!r}")
                if not isinstance(item.get("preconditions"), list):
                    errors.append(f"{label} preconditions must be an array")
            elif group == "fields":
                for key in ("name", "valueType"):
                    if not _text(item.get(key)):
                        errors.append(f"{label} {key} must be non-empty")
                for key in ("required", "sensitive"):
                    if not isinstance(item.get(key), bool):
                        errors.append(f"{label} {key} must be boolean")
                for actor_id in _list(item.get("editableBy")):
                    if actor_id not in actor_ids:
                        errors.append(f"{label} references unknown editable actor {actor_id!r}")
                if not isinstance(item.get("validation"), list):
                    errors.append(f"{label} validation must be an array")
            elif group == "states":
                for key in ("subject", "name"):
                    if not _text(item.get(key)):
                        errors.append(f"{label} {key} must be non-empty")
                for key in ("entryConditions", "allowedActions", "exitConditions"):
                    if not isinstance(item.get(key), list):
                        errors.append(f"{label} {key} must be an array")
            elif group == "permissions":
                if item.get("actorId") not in actor_ids:
                    errors.append(f"{label} references unknown actor {item.get('actorId')!r}")
                for key in ("resource", "action", "scope"):
                    if not _text(item.get(key)):
                        errors.append(f"{label} {key} must be non-empty")
                if item.get("effect") not in {"allow", "deny"}:
                    errors.append(f"{label} effect must be allow or deny")
                if item.get("deniedBehavior") not in DENIED_BEHAVIORS:
                    errors.append(f"{label} deniedBehavior is invalid")
            elif group == "rules" and not _text(item.get("statement")):
                errors.append(f"{label} statement must be non-empty")

    for identifier in sorted(retired_requirement_ids & requirement_ids):
        errors.append(f"retired requirement remains active: {identifier}")

    blocking_questions = 0
    for index, raw in enumerate(_list(requirements.get("openQuestions"))):
        item = _object(raw)
        label = f"openQuestions[{index}]"
        _validate_id(item.get("id"), "QUESTION-", label, all_ids, errors)
        if not _text(item.get("question")):
            errors.append(f"{label} question must be non-empty")
        if item.get("status") != "open_question":
            errors.append(f"{label} status must be open_question")
        if item.get("sourceRef") not in source_ids:
            errors.append(f"{label} references unknown source {item.get('sourceRef')!r}")
        if not isinstance(item.get("blocking"), bool):
            errors.append(f"{label} blocking must be boolean")
        elif item["blocking"]:
            blocking_questions += 1
    if contract.get("readiness") == "ready" and blocking_questions:
        errors.append("ready contract cannot contain blocking open questions")

    realization = _object(contract.get("realization"))
    _require_keys(realization, ("screens", "bindings"), "realization", errors)
    screen_ids: set[str] = set()
    for index, raw in enumerate(_list(realization.get("screens"))):
        item = _object(raw)
        label = f"screens[{index}]"
        identifier = _validate_id(item.get("id"), "SCREEN-", label, all_ids, errors)
        if identifier:
            screen_ids.add(identifier)
        if not _text(item.get("title")):
            errors.append(f"{label} title must be non-empty")
    if contract.get("route") != "design_review" and not screen_ids:
        errors.append("generated product contract must define at least one screen")

    binding_ids: set[str] = set()
    action_ids: set[str] = set()
    mapped_requirement_ids: set[str] = set()
    bindings_by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_list(realization.get("bindings"))):
        item = _object(raw)
        label = f"bindings[{index}]"
        identifier = _validate_id(item.get("id"), "UI-", label, all_ids, errors)
        if identifier:
            binding_ids.add(identifier)
            bindings_by_id[identifier] = item
        if item.get("screenId") not in screen_ids:
            errors.append(f"{label} references unknown screen {item.get('screenId')!r}")
        if not _text(item.get("component")):
            errors.append(f"{label} component must be non-empty")
        kind = item.get("kind")
        if kind not in {"functional", "supporting_ui"}:
            errors.append(f"{label} kind must be functional or supporting_ui")
        references = _list(item.get("requirementIds"))
        if kind == "functional" and not references:
            errors.append(f"{label} functional UI must bind at least one requirement")
        if kind == "supporting_ui" and not _text(item.get("supportingReason")):
            errors.append(f"{label} supporting_ui must explain supportingReason")
        for requirement_id in references:
            if requirement_id in retired_requirement_ids:
                errors.append(f"{label} references retired requirement {requirement_id!r}")
            if requirement_id not in requirement_ids:
                errors.append(f"{label} references unknown requirement {requirement_id!r}")
            else:
                mapped_requirement_ids.add(requirement_id)
        action_id = item.get("actionId")
        if action_id is not None:
            if not _text(action_id) or not ACTION_RE.fullmatch(str(action_id)):
                errors.append(f"{label} actionId is invalid")
            elif action_id in action_ids:
                errors.append(f"duplicate actionId: {action_id}")
            else:
                action_ids.add(str(action_id))

    if schema_version == 3:
        interaction = _object(contract.get("interaction"))
        _require_keys(interaction, ("transitions", "reset"), "interaction", errors)
        transitions = _list(interaction.get("transitions"))
        if not transitions:
            errors.append("interaction.transitions must not be empty")
        transition_ids: set[str] = set()
        for index, raw in enumerate(transitions):
            transition = _object(raw)
            label = f"interaction.transitions[{index}]"
            identifier = _validate_id(
                transition.get("id"),
                "TRANS-",
                label,
                all_ids,
                errors,
            )
            if identifier:
                transition_ids.add(identifier)
            for field in ("fromStateId", "toStateId"):
                state_id = transition.get(field)
                if state_id not in requirements_by_id or not str(
                    state_id or ""
                ).startswith("STATE-"):
                    errors.append(f"{label}.{field} references unknown state {state_id!r}")
            trigger = _object(transition.get("trigger"))
            trigger_type = trigger.get("type")
            if trigger_type == "action":
                if trigger.get("actionId") not in action_ids:
                    errors.append(
                        f"{label}.trigger references unknown actionId "
                        f"{trigger.get('actionId')!r}"
                    )
                if "event" in trigger:
                    errors.append(f"{label}.trigger action must not contain event")
            elif trigger_type == "system_event":
                if not _text(trigger.get("event")):
                    errors.append(f"{label}.trigger system_event requires event")
                if "actionId" in trigger:
                    errors.append(
                        f"{label}.trigger system_event must not contain actionId"
                    )
            else:
                errors.append(f"{label}.trigger.type is invalid")
            if transition.get("phase") not in TRANSITION_PHASES:
                errors.append(f"{label}.phase is invalid")
            for field, prefixes in (
                ("guardRequirementIds", ("RULE-", "PERM-")),
                ("effectRequirementIds", ("SCN-", "STATE-", "RULE-", "PERM-")),
            ):
                values = _list(transition.get(field))
                if len(values) != len(set(values)):
                    errors.append(f"{label}.{field} must not contain duplicates")
                for requirement_id in values:
                    if requirement_id not in requirement_ids or not str(
                        requirement_id
                    ).startswith(prefixes):
                        errors.append(
                            f"{label}.{field} references invalid requirement "
                            f"{requirement_id!r}"
                        )
        reset = _object(interaction.get("reset"))
        reset_strategy = reset.get("strategy")
        if reset_strategy not in RESET_STRATEGIES:
            errors.append("interaction.reset.strategy is invalid")
        if (
            reset_strategy == "function"
            and reset.get("functionName") != "__DEMO_RESET__"
        ):
            errors.append(
                "interaction.reset.functionName must be __DEMO_RESET__"
            )
        if reset_strategy != "function" and "functionName" in reset:
            errors.append(
                "interaction.reset.functionName is only valid for function reset"
            )
        if reset.get("persistence") not in PERSISTENCE_TYPES:
            errors.append("interaction.reset.persistence is invalid")
        reset_scope = _list(reset.get("scope"))
        if len(reset_scope) != len(set(reset_scope)) or not set(
            reset_scope
        ).issubset(RESET_SCOPES):
            errors.append("interaction.reset.scope contains invalid or duplicate values")

    acceptance = _object(contract.get("acceptance"))
    _require_keys(acceptance, ("scenarios",), "acceptance", errors)
    tested_requirement_ids: set[str] = set()
    acceptance_ids: set[str] = set()
    for index, raw in enumerate(_list(acceptance.get("scenarios"))):
        item = _object(raw)
        label = f"acceptance.scenarios[{index}]"
        identifier = _validate_id(item.get("id"), "TEST-", label, all_ids, errors)
        if identifier:
            acceptance_ids.add(identifier)
        if not _text(item.get("title")) or not _text(item.get("expectedOutcome")):
            errors.append(f"{label} title and expectedOutcome must be non-empty")
        if "fixture" in item and not isinstance(item.get("fixture"), dict):
            errors.append(f"{label} fixture must be an object")
        if schema_version == 1 and "fixture" in item:
            errors.append(f"{label} fixture requires schemaVersion 2")
        references = _list(item.get("requirementIds"))
        if not references:
            errors.append(f"{label} requirementIds must not be empty")
        for requirement_id in references:
            if requirement_id in retired_requirement_ids:
                errors.append(f"{label} references retired requirement {requirement_id!r}")
            if requirement_id not in requirement_ids:
                errors.append(f"{label} references unknown requirement {requirement_id!r}")
            elif schema_version in {1, 2}:
                tested_requirement_ids.add(requirement_id)
        if schema_version == 3:
            for expectation_group in ("beforeExpectations", "afterExpectations"):
                expectations_group = _list(item.get(expectation_group))
                if not expectations_group:
                    errors.append(f"{label}.{expectation_group} must not be empty")
                for expectation_index, raw_expectation in enumerate(
                    expectations_group
                ):
                    _validate_expectation(
                        _object(raw_expectation),
                        f"{label}.{expectation_group}[{expectation_index}]",
                        screen_ids,
                        requirements_by_id,
                        errors,
                    )
        steps = _list(item.get("steps"))
        if not steps:
            errors.append(f"{label} steps must not be empty")
        scenario_step_coverage: set[str] = set()
        for step_index, raw_step in enumerate(steps):
            step = _object(raw_step)
            step_label = f"{label}.steps[{step_index}]"
            action_id = step.get("actionId")
            expect = _object(step.get("expect"))
            expectations = _list(step.get("expectations"))
            if not expect and not expectations:
                errors.append(f"{step_label} must contain an observable result")
            if schema_version == 1 and ("actionType" in step or "value" in step or expectations):
                errors.append(f"{step_label} rich actions and expectations require schemaVersion 2")
            action_type = step.get("actionType", "click")
            if action_type not in ACTION_TYPES:
                errors.append(f"{step_label} has invalid actionType {action_type!r}")
            if schema_version in {1, 2} or action_type in TARGET_ACTION_TYPES:
                if action_id not in action_ids:
                    errors.append(
                        f"{step_label} references unknown actionId {action_id!r}"
                    )
            elif action_id is not None:
                errors.append(
                    f"{step_label} {action_type} must not contain actionId"
                )
            if action_type in {"fill", "select"} and not isinstance(step.get("value"), str):
                errors.append(f"{step_label} {action_type} requires a string value")
            if action_type == "toggle" and not isinstance(step.get("value"), bool):
                errors.append(f"{step_label} toggle requires a boolean value")
            if action_type == "press" and not _text(step.get("key")):
                errors.append(f"{step_label} press requires key")
            if "screenId" in expect and expect["screenId"] not in screen_ids:
                errors.append(f"{step_label} references unknown expected screen {expect['screenId']!r}")
            if "stateId" in expect and expect["stateId"] not in requirements_by_id:
                errors.append(f"{step_label} references unknown expected state {expect['stateId']!r}")
            if "feedback" in expect and not _text(expect["feedback"]):
                errors.append(f"{step_label} feedback must be non-empty")
            for expectation_index, raw_expectation in enumerate(expectations):
                _validate_expectation(
                    _object(raw_expectation),
                    f"{step_label}.expectations[{expectation_index}]",
                    screen_ids,
                    requirements_by_id,
                    errors,
                )
            if schema_version == 3:
                verifies = _list(step.get("verifiesRequirementIds"))
                if not verifies:
                    errors.append(
                        f"{step_label}.verifiesRequirementIds must not be empty"
                    )
                for requirement_id in verifies:
                    if requirement_id not in references:
                        errors.append(
                            f"{step_label}.verifiesRequirementIds references "
                            f"undeclared scenario requirement {requirement_id!r}"
                        )
                    elif requirement_id in requirement_ids:
                        tested_requirement_ids.add(requirement_id)
                        scenario_step_coverage.add(str(requirement_id))
                screenshot = _object(step.get("screenshot"))
                if not _text(screenshot.get("label")) or not ACTION_RE.fullmatch(
                    str(screenshot.get("label", ""))
                ):
                    errors.append(f"{step_label}.screenshot.label is invalid")
                if "stateId" in screenshot and (
                    screenshot.get("stateId") not in requirements_by_id
                    or not str(screenshot.get("stateId", "")).startswith("STATE-")
                ):
                    errors.append(
                        f"{step_label}.screenshot.stateId references unknown state"
                    )
        if schema_version == 3:
            uncovered = set(references) - scenario_step_coverage
            for requirement_id in sorted(uncovered):
                errors.append(
                    f"{label} requirement is not verified by a step: {requirement_id}"
                )

    if schema_version == 3:
        reset_strategy = _object(_object(contract.get("interaction")).get("reset")).get(
            "strategy"
        )
        if len(_list(acceptance.get("scenarios"))) > 1 and reset_strategy == "none":
            errors.append("multiple acceptance scenarios require interaction reset")

    critical_ids = {
        identifier
        for identifier, item in requirements_by_id.items()
        if item.get("critical") is True
    }
    for identifier in sorted(critical_ids - mapped_requirement_ids):
        errors.append(f"critical requirement is not mapped to UI: {identifier}")
    critical_interactive_scenarios = {
        identifier
        for identifier, item in requirements_by_id.items()
        if identifier.startswith("SCN-")
        and item.get("critical") is True
        and item.get("interactive") is True
    }
    for identifier in sorted(critical_interactive_scenarios - tested_requirement_ids):
        errors.append(f"critical interactive scenario is not covered by acceptance: {identifier}")
    return errors


class ProductContractHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.binding_ids: list[str] = []
        self.action_ids: list[str] = []
        self.screen_ids: list[str] = []
        self.state_ids: list[str] = []
        self.requirement_ids: list[str] = []
        self.binding_records: list[dict[str, Any]] = []
        self.frontend_contract_markers: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        for name, value in attrs:
            if name in FORBIDDEN_FRONTEND_CONTRACT_ATTRIBUTES:
                self.frontend_contract_markers.append(name)
            if value and "product-contract-runtime." in value:
                self.frontend_contract_markers.append(f"{tag}[{name}]={value}")
        if "data-ui-binding-id" in attributes and attributes["data-ui-binding-id"]:
            binding_id = str(attributes["data-ui-binding-id"])
            self.binding_ids.append(binding_id)
            self.binding_records.append(
                {
                    "id": binding_id,
                    "actionId": (
                        str(attributes["data-action-id"])
                        if attributes.get("data-action-id")
                        else None
                    ),
                    "requirementIds": set(
                        str(attributes.get("data-requirement-ids") or "").split()
                    ),
                }
            )
        if "data-action-id" in attributes and attributes["data-action-id"]:
            self.action_ids.append(str(attributes["data-action-id"]))
        if "data-screen-id" in attributes and attributes["data-screen-id"]:
            self.screen_ids.append(str(attributes["data-screen-id"]))
        if "data-state-id" in attributes and attributes["data-state-id"]:
            self.state_ids.append(str(attributes["data-state-id"]))
        if "data-requirement-ids" in attributes and attributes["data-requirement-ids"]:
            self.requirement_ids.extend(str(attributes["data-requirement-ids"]).split())


def validate_html(contract: dict[str, Any], html_path: str | Path) -> list[str]:
    path = Path(html_path)
    try:
        html = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"HTML does not exist: {path}"]
    parser = ProductContractHTMLParser()
    parser.feed(html)
    errors: list[str] = []
    if parser.frontend_contract_markers:
        markers = ", ".join(sorted(set(parser.frontend_contract_markers)))
        errors.append(
            "HTML must not embed or render product-contract frontend data: "
            f"{markers}"
        )

    requirements = _object(contract.get("requirements"))
    known_requirement_ids = {
        str(item.get("id"))
        for group in REQUIREMENT_GROUPS
        for item in _list(requirements.get(group))
        if _text(_object(item).get("id"))
    }
    bindings = _list(_object(contract.get("realization")).get("bindings"))
    expected_bindings = {
        str(_object(item).get("id"))
        for item in bindings
        if _text(_object(item).get("id"))
    }
    expected_actions = {
        str(_object(item).get("actionId"))
        for item in bindings
        if _text(_object(item).get("actionId"))
    }
    expected_screens = {
        str(_object(item).get("id"))
        for item in _list(_object(contract.get("realization")).get("screens"))
        if _text(_object(item).get("id"))
    }
    expected_states = {
        str(_object(item).get("id"))
        for item in _list(requirements.get("states"))
        if _text(_object(item).get("id"))
    }
    for label, actual_values, expected_values in (
        ("binding", parser.binding_ids, expected_bindings),
        ("action", parser.action_ids, expected_actions),
        ("screen", parser.screen_ids, expected_screens),
        ("state", parser.state_ids, expected_states),
    ):
        actual = set(actual_values)
        for identifier in sorted(expected_values - actual):
            errors.append(f"HTML is missing declared {label}: {identifier}")
        for identifier in sorted(actual - expected_values):
            errors.append(f"HTML contains untracked {label}: {identifier}")
        duplicates = sorted({value for value in actual if actual_values.count(value) > 1})
        for identifier in duplicates:
            errors.append(f"HTML contains duplicate {label}: {identifier}")
    for requirement_id in sorted(set(parser.requirement_ids) - known_requirement_ids):
        errors.append(f"HTML references unknown requirement: {requirement_id}")
    expected_binding_records = {
        str(_object(binding).get("id")): {
            "actionId": (
                str(_object(binding).get("actionId"))
                if _text(_object(binding).get("actionId"))
                else None
            ),
            "requirementIds": set(_list(_object(binding).get("requirementIds"))),
        }
        for binding in bindings
        if _text(_object(binding).get("id"))
    }
    actual_binding_records = {
        str(record["id"]): record
        for record in parser.binding_records
        if parser.binding_ids.count(str(record["id"])) == 1
    }
    for binding_id in sorted(expected_bindings & set(actual_binding_records)):
        expected = expected_binding_records[binding_id]
        actual = actual_binding_records[binding_id]
        if actual["actionId"] != expected["actionId"]:
            errors.append(
                f"HTML binding {binding_id} actionId mismatch: "
                f"expected {expected['actionId']!r}, found {actual['actionId']!r}"
            )
        if actual["requirementIds"] != expected["requirementIds"]:
            errors.append(
                f"HTML binding {binding_id} requirementIds mismatch: "
                f"expected {sorted(expected['requirementIds'])}, "
                f"found {sorted(actual['requirementIds'])}"
            )
    return errors


def build_report(
    contract: dict[str, Any],
    errors: list[str],
    html_path: str | Path | None = None,
) -> dict[str, Any]:
    requirements = _object(contract.get("requirements"))
    requirement_items = [
        _object(item)
        for group in REQUIREMENT_GROUPS
        for item in _list(requirements.get(group))
    ]
    bindings = [_object(item) for item in _list(_object(contract.get("realization")).get("bindings"))]
    mapped = {
        requirement_id
        for binding in bindings
        for requirement_id in _list(binding.get("requirementIds"))
    }
    critical = {
        str(item.get("id"))
        for item in requirement_items
        if item.get("critical") is True and _text(item.get("id"))
    }
    interactive = {
        str(item.get("id"))
        for item in _list(requirements.get("scenarios"))
        if _object(item).get("critical") is True
        and _object(item).get("interactive") is True
        and _text(_object(item).get("id"))
    }
    if contract.get("schemaVersion") == 3:
        tested = {
            requirement_id
            for scenario in _list(_object(contract.get("acceptance")).get("scenarios"))
            for step in _list(_object(scenario).get("steps"))
            for requirement_id in _list(
                _object(step).get("verifiesRequirementIds")
            )
        }
    else:
        tested = {
            requirement_id
            for scenario in _list(_object(contract.get("acceptance")).get("scenarios"))
            for requirement_id in _list(_object(scenario).get("requirementIds"))
        }
    return {
        "status": "failed" if errors else "passed",
        "schemaVersion": contract.get("schemaVersion"),
        "contractHash": contract_hash(contract),
        "revision": contract.get("revision"),
        "retiredRequirementIds": sorted(
            {
                str(identifier)
                for key in ("supersedesRequirementIds", "removedRequirementIds")
                for identifier in _list(_object(contract.get("changeSet")).get(key))
                if _text(identifier)
            }
        ),
        "readiness": contract.get("readiness"),
        "sourceKinds": sorted(
            {
                str(_object(item).get("kind"))
                for item in _list(contract.get("sources"))
                if _text(_object(item).get("kind"))
            }
        ),
        "coverage": {
            "criticalRequirements": {"mapped": len(critical & mapped), "total": len(critical)},
            "interactiveScenarios": {"tested": len(interactive & tested), "total": len(interactive)},
            "screens": len(_list(_object(contract.get("realization")).get("screens"))),
            "bindings": len(bindings),
            "openQuestions": len(_list(requirements.get("openQuestions"))),
            "transitions": len(
                _list(_object(contract.get("interaction")).get("transitions"))
            ),
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
    parser = argparse.ArgumentParser(description="Validate a demo-design product contract")
    parser.add_argument("contract", type=Path)
    parser.add_argument("--html", type=Path)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--print-hash", action="store_true")
    args = parser.parse_args(argv)
    try:
        contract = load_contract(args.contract)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    errors = validate_contract(contract)
    if args.html:
        errors.extend(validate_html(contract, args.html))
    report = build_report(contract, errors, args.html)
    write_report(args.report_json, report)
    if args.print_hash:
        print(report["contractHash"])
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        "OK: product contract valid "
        f"({report['coverage']['criticalRequirements']['mapped']}/"
        f"{report['coverage']['criticalRequirements']['total']} critical mapped, "
        f"hash {report['contractHash'][:12]})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
