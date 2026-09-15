#!/usr/bin/env python3
"""Optional strict regression for demo-design HTML artifacts.

The default demo workflow uses the Codex built-in Browser. This script is run
only when strict regression is explicitly requested. It launches bounded local
browser candidates, never installs dependencies, and records its profile in
every report.
"""

import argparse
import hashlib
import importlib.util
import json
import multiprocessing
import os
import queue
import re
import signal
import sys
import threading
import time
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from urllib.parse import quote


EXIT_PASSED = 0
EXIT_ARTIFACT_FAILED = 1
EXIT_BROWSER_UNAVAILABLE = 2
EXIT_INPUT_ERROR = 3
DEFAULT_LAUNCH_TIMEOUT_MS = 5000
DEFAULT_NAVIGATION_TIMEOUT_MS = 6000
DEFAULT_WALL_TIMEOUT_MS_BY_TIER = {
    "tier_0_text_copy_only": 0,
    "tier_1_local_ui_patch": 10000,
    "tier_2_layout_or_interaction": 10000,
    "tier_3_full_delivery": 30000,
}
TIERS = (
    "tier_0_text_copy_only",
    "tier_1_local_ui_patch",
    "tier_2_layout_or_interaction",
    "tier_3_full_delivery",
)
DEFAULT_VIEWPORTS_BY_TIER = {
    "tier_0_text_copy_only": "1440x900",
    "tier_1_local_ui_patch": "1440x900",
    "tier_2_layout_or_interaction": "1440x900",
    "tier_3_full_delivery": "1440x900",
}
DEFAULT_WAIT_BY_TIER = {
    "tier_0_text_copy_only": 0,
    "tier_1_local_ui_patch": 300,
    "tier_2_layout_or_interaction": 800,
    "tier_3_full_delivery": 1500,
}
CONTRACT_AFFECTING_ASPECTS = {
    "business",
    "permission",
    "permissions",
    "requirement",
    "requirements",
    "binding",
    "bindings",
    "business-state",
}
STATIC_ASPECTS = {"copy"}
TARGET_VISUAL_ASPECTS = {
    "color",
    "typography",
    "spacing",
    "size",
    "local-layout",
}
RESPONSIVE_ASPECTS = {"layout", "responsive"}
INTERACTION_ASPECTS = {"interaction"}
STATE_ASPECTS = {"state"}
ASSET_ASPECTS = {"asset", "assets", "resource", "resources"}
SUPPORTED_CHANGED_ASPECTS = (
    STATIC_ASPECTS
    | TARGET_VISUAL_ASPECTS
    | RESPONSIVE_ASPECTS
    | INTERACTION_ASPECTS
    | STATE_ASPECTS
    | ASSET_ASPECTS
    | CONTRACT_AFFECTING_ASPECTS
    | {"contract"}
)


class InputError(ValueError):
    """Raised for invalid command input or report configuration."""


class BrowserUnavailable(RuntimeError):
    """Raised when a previously probed browser can no longer be launched."""

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {
            "available": False,
            "status": "degraded",
            "source": None,
            "attempts": [{"source": "browser", "error": str(message)}],
        }


class VerificationTimeout(RuntimeError):
    """Raised when browser-backed verification exceeds its wall deadline."""

    def __init__(self, timeout_ms):
        super().__init__(f"浏览器验证超过 {timeout_ms}ms 截止时间")
        self.timeout_ms = timeout_ms


def _load_product_contract_validator():
    path = Path(__file__).with_name("validate-product-contract.py")
    if not path.is_file():
        raise InputError("product-contract validator is missing")
    spec = importlib.util.spec_from_file_location("demo_design_product_contract", path)
    if spec is None or spec.loader is None:
        raise InputError("product-contract validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_design_guidance_validator():
    path = Path(__file__).with_name("validate-design-guidance.py")
    if not path.is_file():
        raise InputError("design-guidance validator is missing")
    spec = importlib.util.spec_from_file_location("demo_design_guidance", path)
    if spec is None or spec.loader is None:
        raise InputError("design-guidance validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_experience_checks_validator():
    path = Path(__file__).with_name("validate-experience-checks.py")
    if not path.is_file():
        raise InputError("experience-checks validator is missing")
    spec = importlib.util.spec_from_file_location("demo_design_experience_checks", path)
    if spec is None or spec.loader is None:
        raise InputError("experience-checks validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_design_reference_validator():
    path = Path(__file__).with_name("validate-design-reference.py")
    if not path.is_file():
        raise InputError("design-reference validator is missing")
    spec = importlib.util.spec_from_file_location("demo_design_reference", path)
    if spec is None or spec.loader is None:
        raise InputError("design-reference validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_visual_diff():
    path = Path(__file__).with_name("visual-diff.py")
    if not path.is_file():
        raise InputError("visual-diff helper is missing")
    spec = importlib.util.spec_from_file_location("demo_design_visual_diff", path)
    if spec is None or spec.loader is None:
        raise InputError("visual-diff helper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_portability_validator():
    path = Path(__file__).with_name("validate-portability.py")
    if not path.is_file():
        raise InputError("portability validator is missing")
    spec = importlib.util.spec_from_file_location("demo_design_portability", path)
    if spec is None or spec.loader is None:
        raise InputError("portability validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_browser_session_manager():
    path = Path(__file__).with_name("browser-session.py")
    if not path.is_file():
        raise InputError("browser-session helper is missing")
    spec = importlib.util.spec_from_file_location("demo_design_browser_session", path)
    if spec is None or spec.loader is None:
        raise InputError("browser-session helper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_preview_server():
    path = Path(__file__).with_name("preview-server.py")
    if not path.is_file():
        raise InputError("preview-server helper is missing")
    spec = importlib.util.spec_from_file_location("demo_design_preview_server", path)
    if spec is None or spec.loader is None:
        raise InputError("preview-server helper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def loopback_preview(html_path):
    """Serve one HTML artifact over bounded loopback HTTP."""
    source = Path(html_path).resolve()
    preview = _load_preview_server()
    handler = partial(
        preview.LoopbackPreviewHandler,
        directory=str(source.parent),
    )
    try:
        server = preview.LoopbackPreviewServer((preview.LOOPBACK_HOST, 0), handler)
    except OSError as error:
        raise InputError(
            f"could not start strict-regression preview server: {error}"
        ) from error
    port = int(server.server_address[1])
    url = (
        f"http://{preview.LOOPBACK_HOST}:{port}/"
        f"{quote(source.name, safe='/')}"
    )
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.1},
        name="demo-design-strict-preview",
        daemon=True,
    )
    thread.start()
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def resolve_browser_session(
    policy,
    *,
    browser_executable=None,
    idle_timeout_seconds=900,
    launch_timeout_ms=DEFAULT_LAUNCH_TIMEOUT_MS,
):
    if policy == "off":
        return None, {"policy": policy, "status": "off", "error": None}
    manager = _load_browser_session_manager()
    try:
        state = manager.touch_session()
        if state:
            status = "reused"
        elif policy == "reuse":
            return None, {
                "policy": policy,
                "status": "not_running",
                "error": None,
            }
        else:
            state = manager.start_session(
                executable=browser_executable,
                idle_timeout_seconds=idle_timeout_seconds,
                launch_timeout_ms=launch_timeout_ms,
            )
            status = "started"
    except (OSError, RuntimeError, ValueError) as error:
        return None, {
            "policy": policy,
            "status": "cold_fallback",
            "error": str(error),
        }
    return state, {
        "policy": policy,
        "status": status,
        "error": None,
        "managerPid": state.get("managerPid"),
        "browserPid": state.get("browserPid"),
        "startedAt": state.get("startedAt"),
        "idleTimeoutSeconds": state.get("idleTimeoutSeconds"),
    }


def _perform_contract_action(locator, step, page=None):
    action_type = step.get("actionType", "click")
    if action_type == "click":
        locator.click()
    elif action_type == "fill":
        locator.fill(step.get("value", ""))
    elif action_type == "select":
        locator.select_option(step.get("value", ""))
    elif action_type == "toggle":
        if step.get("value"):
            locator.check()
        else:
            locator.uncheck()
    elif action_type == "focus":
        locator.focus()
    elif action_type == "blur":
        locator.evaluate("node => node.blur()")
    elif action_type == "submit":
        locator.press("Enter")
    elif action_type == "press":
        if page is None:
            raise InputError("press action requires a page")
        page.keyboard.press(step.get("key", ""))
    elif action_type == "back":
        if page is None:
            raise InputError("back action requires a page")
        page.go_back(wait_until="domcontentloaded")
    elif action_type == "escape":
        if page is None:
            raise InputError("escape action requires a page")
        page.keyboard.press("Escape")
    elif action_type == "reload":
        if page is None:
            raise InputError("reload action requires a page")
        page.reload(wait_until="domcontentloaded")
    elif action_type in {"waitFor", "assert"}:
        return
    else:
        raise InputError(f"unsupported contract actionType: {action_type}")


def _expectation_observation(page, expectation):
    kind = expectation.get("kind")
    if kind == "screen":
        locator = page.locator(f'[data-screen-id="{expectation.get("id")}"]')
        count = locator.count()
        ok = count == 1 and locator.first.is_visible()
        actual = {"count": count, "visible": ok}
    elif kind == "state":
        locator = page.locator(f'[data-state-id="{expectation.get("id")}"]')
        count = locator.count()
        ok = count == 1 and locator.first.is_visible()
        actual = {"count": count, "visible": ok}
    elif kind == "feedback":
        locator = page.get_by_text(
            str(expectation.get("value", "")),
            exact=bool(expectation.get("exact", False)),
        )
        count = locator.count()
        ok = count >= 1 and locator.first.is_visible()
        actual = {"count": count, "visible": ok}
    elif kind == "url":
        actual = str(page.url)
        expected = str(expectation.get("value", ""))
        ok = actual == expected if expectation.get("exact") else expected in actual
    else:
        selector = expectation.get("selector", "")
        locator = page.locator(selector)
        count = locator.count()
        target = locator.first if count else None
        if kind == "visible":
            ok = count >= 1 and target.is_visible()
            actual = {"count": count, "visible": bool(ok)}
        elif kind == "hidden":
            ok = count == 0 or not target.is_visible()
            actual = {"count": count, "hidden": bool(ok)}
        elif kind == "enabled":
            ok = count >= 1 and target.is_enabled()
            actual = {"count": count, "enabled": bool(ok)}
        elif kind == "disabled":
            ok = count >= 1 and not target.is_enabled()
            actual = {"count": count, "disabled": bool(ok)}
        elif kind == "text":
            actual = target.inner_text() if count else None
            expected = str(expectation.get("value", ""))
            ok = actual == expected if expectation.get("exact") else expected in (actual or "")
        elif kind == "value":
            actual = target.input_value() if count else None
            ok = actual == str(expectation.get("value", ""))
        elif kind == "count":
            actual = count
            ok = count == expectation.get("count")
        elif kind == "focused":
            actual = bool(
                count
                and target.evaluate("node => document.activeElement === node")
            )
            ok = actual == bool(expectation.get("value", True))
        elif kind == "accessibleName":
            actual = (
                target.get_attribute("aria-label") or target.inner_text()
                if count
                else None
            )
            expected = str(expectation.get("value", ""))
            ok = actual == expected if expectation.get("exact") else expected in (actual or "")
        elif kind == "role":
            actual = target.get_attribute("role") if count else None
            ok = actual == str(expectation.get("value", ""))
        elif kind == "checked":
            actual = target.is_checked() if count else None
            ok = actual == bool(expectation.get("value"))
        elif kind in {"pressed", "expanded", "invalid"}:
            attribute = {
                "pressed": "aria-pressed",
                "expanded": "aria-expanded",
                "invalid": "aria-invalid",
            }[kind]
            actual = target.get_attribute(attribute) if count else None
            expected = str(expectation.get("value")).lower()
            ok = str(actual).lower() == expected
        elif kind == "liveRegion":
            actual = target.inner_text() if count else None
            expected = str(expectation.get("value", ""))
            ok = actual == expected if expectation.get("exact") else expected in (actual or "")
        else:
            return False, None
    return bool(ok), actual


def evaluate_expectation(page, expectation):
    timeout_ms = int(expectation.get("timeoutMs", 0) or 0)
    poll_ms = int(expectation.get("pollMs", 50) or 50)
    started = time.monotonic()
    actual = None
    while True:
        ok, actual = _expectation_observation(page, expectation)
        if ok:
            break
        elapsed_ms = (time.monotonic() - started) * 1000
        if elapsed_ms >= timeout_ms:
            break
        page.wait_for_timeout(min(poll_ms, max(1, timeout_ms - int(elapsed_ms))))
    return {
        "kind": expectation.get("kind"),
        "id": expectation.get("id"),
        "selector": expectation.get("selector"),
        "expected": expectation.get("value", expectation.get("count")),
        "actual": actual,
        "status": "passed" if ok else "failed",
        "durationMs": round((time.monotonic() - started) * 1000, 2),
    }


def _contract_expectation_error(page, scenario_id, expectation):
    result = evaluate_expectation(page, expectation)
    if result["status"] == "passed":
        return None
    kind = expectation.get("kind")
    description = expectation.get("id") or expectation.get("selector") or expectation.get("value")
    return f"{scenario_id} expectation {kind} failed for {description!r}"


def _normalized_contract_expectations(step):
    expectations = list(step.get("expectations", []))
    legacy = step.get("expect", {})
    if legacy.get("screenId"):
        expectations.append({"kind": "screen", "id": legacy["screenId"]})
    if legacy.get("stateId"):
        expectations.append({"kind": "state", "id": legacy["stateId"]})
    if legacy.get("feedback"):
        expectations.append({"kind": "feedback", "value": legacy["feedback"]})
    return expectations


def _reset_demo(page, reset, fixture=None):
    strategy = reset.get("strategy", "function")
    if strategy == "none":
        return {"status": "not_applicable", "strategy": strategy}
    try:
        if strategy == "reload":
            page.reload(wait_until="domcontentloaded")
            return {"status": "passed", "strategy": strategy}
        if fixture is None:
            available = page.evaluate(
                """
                async () => {
                  if (typeof window.__DEMO_RESET__ !== "function") return false;
                  await window.__DEMO_RESET__();
                  return true;
                }
                """
            )
        else:
            available = page.evaluate(
                """
                async fixture => {
                  if (typeof window.__DEMO_RESET__ !== "function") return false;
                  await window.__DEMO_RESET__(fixture);
                  return true;
                }
                """,
                fixture,
            )
    except Exception as error:
        return {"status": "failed", "strategy": strategy, "error": str(error)}
    return {
        "status": "passed" if available else "failed",
        "strategy": strategy,
        "error": None if available else "window.__DEMO_RESET__ is unavailable",
    }


def _capture_step_screenshot(
    page,
    screenshot,
    *,
    output_dir,
    stem,
    viewport,
    scenario_id,
    step_index,
    timeout_ms,
    reference_screenshot=None,
):
    if output_dir is None or not screenshot:
        return None
    label = sanitize_screenshot_label(screenshot.get("label", "state"))
    scenario_label = sanitize_screenshot_label(scenario_id)
    viewport_suffix = (
        f"-{viewport['width']}x{viewport['height']}" if viewport else ""
    )
    path = Path(output_dir) / (
        f"{stem}-{scenario_label}-{step_index:02d}-{label}{viewport_suffix}.png"
    )
    selector = screenshot.get("selector")
    if reference_screenshot and (selector or screenshot.get("fullPage")):
        raise InputError(
            "design-reference state evidence requires a viewport screenshot"
        )
    comparison_geometry = (
        capture_reference_comparison_geometry(page, reference_screenshot)
        if reference_screenshot
        else None
    )
    if selector:
        locator = page.locator(selector)
        if locator.count() != 1 or not locator.first.is_visible():
            raise InputError(
                f"step screenshot selector must be unique and visible: {selector}"
            )
        locator.first.screenshot(path=str(path), timeout=timeout_ms)
    else:
        page.screenshot(
            path=str(path),
            full_page=bool(screenshot.get("fullPage", False)),
        )
    return {
        "path": str(path),
        "label": screenshot.get("label"),
        "stateId": screenshot.get("stateId"),
        "selector": selector,
        "fullPage": bool(screenshot.get("fullPage", False)),
        "viewport": viewport,
        "comparisonGeometry": comparison_geometry,
    }


def _resolve_step_locator(page, action_id=None, selector=None):
    if action_id:
        return page.locator(f'[data-action-id="{action_id}"]')
    if selector:
        return page.locator(selector)
    return None


def verify_experience_checks_profile(
    page,
    checks,
    scenario_results=None,
    *,
    output_dir=None,
    stem="prototype",
    viewport=None,
    screenshot_files=None,
    navigation_timeout_ms=DEFAULT_NAVIGATION_TIMEOUT_MS,
    design_reference=None,
):
    errors = []
    reset = checks.get("reset", {})
    for scenario in checks.get("scenarios", []):
        scenario_started = time.monotonic()
        scenario_errors = []
        step_results = []
        reset_result = _reset_demo(page, reset, reset.get("fixture"))
        if reset.get("betweenScenarios") and reset_result.get("status") != "passed":
            scenario_errors.append(
                f"{scenario.get('id')} reset failed: {reset_result.get('error')}"
            )
        reset_expectations = [
            evaluate_expectation(page, item)
            for item in reset.get("expectations", [])
        ]
        for result in reset_expectations:
            if result["status"] == "failed":
                scenario_errors.append(
                    f"{scenario.get('id')} reset expectation {result['kind']} failed"
                )
        for step_index, step in enumerate(scenario.get("steps", []), start=1):
            step_started = time.monotonic()
            action = step.get("action", {})
            action_type = action.get("type")
            locator = _resolve_step_locator(
                page,
                action.get("actionId"),
                action.get("selector"),
            )
            action_error = None
            if action_type in {
                "click",
                "fill",
                "select",
                "toggle",
                "focus",
                "blur",
                "submit",
            } and (locator is None or locator.count() != 1):
                action_error = (
                    f"action target is missing or not unique: "
                    f"{action.get('actionId') or action.get('selector')}"
                )
            else:
                try:
                    _perform_contract_action(
                        locator,
                        {
                            "actionType": action_type,
                            "value": action.get("value"),
                            "key": action.get("key"),
                        },
                        page,
                    )
                except Exception as error:
                    action_error = str(error)
            expectation_results = [
                evaluate_expectation(page, expectation)
                for expectation in step.get("expectations", [])
            ]
            screenshot_result = None
            try:
                screenshot_spec = step.get("screenshot") or {}
                state_reference = (
                    matching_reference_screenshot(
                        design_reference,
                        viewport or {},
                        state_id=screenshot_spec.get("stateId"),
                    )
                    if design_reference and screenshot_spec.get("stateId")
                    else None
                )
                screenshot_result = _capture_step_screenshot(
                    page,
                    screenshot_spec,
                    output_dir=output_dir,
                    stem=stem,
                    viewport=viewport,
                    scenario_id=scenario.get("id", "experience"),
                    step_index=step_index,
                    timeout_ms=navigation_timeout_ms,
                    reference_screenshot=state_reference,
                )
            except InputError as error:
                action_error = action_error or str(error)
            if screenshot_result and screenshot_files is not None:
                screenshot_files.append(screenshot_result["path"])
            failed_expectations = [
                result
                for result in expectation_results
                if result["status"] == "failed"
            ]
            if action_error:
                scenario_errors.append(
                    f"{scenario.get('id')} {step.get('id')} action failed: {action_error}"
                )
            for result in failed_expectations:
                scenario_errors.append(
                    f"{scenario.get('id')} {step.get('id')} expectation "
                    f"{result['kind']} failed"
                )
            step_results.append(
                {
                    "id": step.get("id"),
                    "action": action,
                    "actionStatus": "failed" if action_error else "passed",
                    "actionError": action_error,
                    "expectations": expectation_results,
                    "screenshot": screenshot_result,
                    "status": (
                        "failed"
                        if action_error or failed_expectations
                        else "passed"
                    ),
                    "durationMs": round(
                        (time.monotonic() - step_started) * 1000,
                        2,
                    ),
                }
            )
        result = {
            "id": scenario.get("id"),
            "pathType": scenario.get("pathType"),
            "status": "failed" if scenario_errors else "passed",
            "reset": {**reset_result, "expectations": reset_expectations},
            "steps": step_results,
            "errors": scenario_errors,
            "durationMs": round((time.monotonic() - scenario_started) * 1000, 2),
        }
        errors.extend(scenario_errors)
        if scenario_results is not None:
            scenario_results.append(result)
    return errors


def verify_product_contract_profile(
    page,
    contract,
    scenario_results=None,
    *,
    output_dir=None,
    stem="prototype",
    viewport=None,
    screenshot_files=None,
    navigation_timeout_ms=DEFAULT_NAVIGATION_TIMEOUT_MS,
    design_reference=None,
):
    """Execute sidecar product-contract interactions without frontend contract UI."""
    errors = []
    forbidden_selectors = (
        "[data-product-contract-runtime]",
        "[data-product-contract]",
        "[data-product-contract-open]",
        "[data-product-contract-overlay]",
        "[data-product-contract-review-bar]",
    )
    for selector in forbidden_selectors:
        if page.locator(selector).count():
            errors.append(
                f"product-contract frontend marker must not be present: {selector}"
            )

    schema_version = contract.get("schemaVersion")
    v3_reset = contract.get("interaction", {}).get("reset", {})
    scenarios = contract.get("acceptance", {}).get("scenarios", [])
    for scenario_index, scenario in enumerate(scenarios):
        scenario_started = time.monotonic()
        fixture = scenario.get("fixture")
        if schema_version == 3:
            reset_result = _reset_demo(page, v3_reset, fixture)
            reset_available = reset_result.get("status") == "passed"
        else:
            reset_result = _reset_demo(
                page,
                {"strategy": "function"},
                fixture,
            )
            reset_available = reset_result.get("status") == "passed"
        scenario_errors = []
        reset_required = (
            (schema_version == 3 and v3_reset.get("strategy") != "none")
            or scenario_index > 0
            or fixture is not None
        )
        if reset_required and not reset_available:
            scenario_errors.append(
                "multiple, fixture-backed or schemaVersion 3 product-contract "
                "scenarios require a working declared reset"
            )
            errors.extend(scenario_errors)
            if scenario_results is not None:
                scenario_results.append(
                    {
                        "id": scenario.get("id"),
                        "status": "failed",
                        "reset": reset_result,
                        "steps": [],
                        "errors": scenario_errors,
                    }
                )
            break

        before_results = [
            evaluate_expectation(page, expectation)
            for expectation in scenario.get("beforeExpectations", [])
        ]
        for result in before_results:
            if result["status"] == "failed":
                scenario_errors.append(
                    f"{scenario.get('id')} before expectation {result['kind']} failed"
                )

        step_results = []
        for step_index, step in enumerate(scenario.get("steps", []), start=1):
            step_started = time.monotonic()
            action_type = step.get("actionType", "click")
            action_id = step.get("actionId")
            action = (
                page.locator(f'[data-action-id="{action_id}"]')
                if action_id
                else None
            )
            action_error = None
            if action_type in {
                "click",
                "fill",
                "select",
                "toggle",
                "focus",
                "blur",
                "submit",
            } and (action is None or action.count() != 1):
                action_error = f"action {action_id!r} is missing or not unique"
            else:
                try:
                    _perform_contract_action(action, step, page)
                except Exception as error:
                    action_error = str(error)
            expectation_results = [
                evaluate_expectation(page, expectation)
                for expectation in _normalized_contract_expectations(step)
            ]
            screenshot_result = None
            if schema_version == 3:
                try:
                    screenshot_spec = step.get("screenshot") or {}
                    state_reference = (
                        matching_reference_screenshot(
                            design_reference,
                            viewport or {},
                            state_id=screenshot_spec.get("stateId"),
                        )
                        if design_reference and screenshot_spec.get("stateId")
                        else None
                    )
                    screenshot_result = _capture_step_screenshot(
                        page,
                        screenshot_spec,
                        output_dir=output_dir,
                        stem=stem,
                        viewport=viewport,
                        scenario_id=scenario.get("id", "scenario"),
                        step_index=step_index,
                        timeout_ms=navigation_timeout_ms,
                        reference_screenshot=state_reference,
                    )
                except InputError as error:
                    action_error = action_error or str(error)
                if screenshot_result and screenshot_files is not None:
                    screenshot_files.append(screenshot_result["path"])
            failed_expectations = [
                result
                for result in expectation_results
                if result["status"] == "failed"
            ]
            if action_error:
                scenario_errors.append(
                    f"{scenario.get('id')} step {step_index} {action_error}"
                )
            for result in failed_expectations:
                scenario_errors.append(
                    f"{scenario.get('id')} step {step_index} expectation "
                    f"{result['kind']} failed"
                )
            step_results.append(
                {
                    "index": step_index,
                    "actionId": action_id,
                    "actionType": action_type,
                    "verifiesRequirementIds": step.get(
                        "verifiesRequirementIds", []
                    ),
                    "actionStatus": "failed" if action_error else "passed",
                    "actionError": action_error,
                    "expectations": expectation_results,
                    "screenshot": screenshot_result,
                    "status": (
                        "failed"
                        if action_error or failed_expectations
                        else "passed"
                    ),
                    "durationMs": round(
                        (time.monotonic() - step_started) * 1000,
                        2,
                    ),
                }
            )

        after_results = [
            evaluate_expectation(page, expectation)
            for expectation in scenario.get("afterExpectations", [])
        ]
        for result in after_results:
            if result["status"] == "failed":
                scenario_errors.append(
                    f"{scenario.get('id')} after expectation {result['kind']} failed"
                )
        errors.extend(scenario_errors)
        if scenario_results is not None:
            base_result = {
                "id": scenario.get("id"),
                "status": "failed" if scenario_errors else "passed",
                "errors": scenario_errors,
            }
            if schema_version == 3:
                base_result.update(
                    reset=reset_result,
                    beforeExpectations=before_results,
                    steps=step_results,
                    afterExpectations=after_results,
                    durationMs=round(
                        (time.monotonic() - scenario_started) * 1000,
                        2,
                    ),
                )
            scenario_results.append(base_result)
    return errors


def verify_design_guidance_hard_gates(page, guidance):
    """Check objective browser-backed guidance rules for the current viewport."""
    route = guidance.get("deliveryRoute")
    validator = _load_design_guidance_validator()
    rule_applicabilities = validator.normalized_rule_applicabilities(guidance)
    active_rule_ids = [
        rule_id
        for rule_id, applicability in rule_applicabilities.items()
        if applicability == "required"
        and rule_id
        in {
            "GUIDE-FORM-LABELS",
            "GUIDE-FOCUS-VISIBILITY",
            "GUIDE-TARGET-SIZE",
            "GUIDE-HORIZONTAL-OVERFLOW",
            "GUIDE-IMAGE-ALTERNATIVES",
            "GUIDE-REDUCED-MOTION",
        }
    ]
    minimum_target = 44 if route == "app_flow" else 24
    findings = page.evaluate(
        """
        ({activeRuleIds, minimumTarget}) => {
          const active = new Set(activeRuleIds);
          const issues = [];
          const add = (ruleId, message) => issues.push({ruleId, message});
          const visible = element => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== "none" &&
              style.visibility !== "hidden" &&
              rect.width > 0 &&
              rect.height > 0;
          };

          if (active.has("GUIDE-FORM-LABELS")) {
            const controls = Array.from(
              document.querySelectorAll("input, select, textarea")
            ).filter(element =>
              !["hidden", "button", "submit", "reset", "image"].includes(
                (element.getAttribute("type") || "").toLowerCase()
              ) && visible(element)
            );
            for (const control of controls) {
              const labelledBy = (control.getAttribute("aria-labelledby") || "")
                .split(/\\s+/)
                .filter(Boolean)
                .some(id => {
                  const label = document.getElementById(id);
                  return label && (label.textContent || "").trim();
                });
              const named = (control.labels && control.labels.length > 0) ||
                (control.getAttribute("aria-label") || "").trim() ||
                labelledBy;
              if (!named) {
                add(
                  "GUIDE-FORM-LABELS",
                  `unlabelled ${control.tagName.toLowerCase()}${control.id ? `#${control.id}` : ""}`
                );
              }
            }
          }

          const focusableSelector =
            'a[href], button, input:not([disabled]), select:not([disabled]), ' +
            'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
          const focusables = Array.from(
            document.querySelectorAll(focusableSelector)
          ).filter(visible);

          if (active.has("GUIDE-FOCUS-VISIBILITY")) {
            for (const element of focusables.slice(0, 60)) {
              const beforeStyle = getComputedStyle(element);
              const before = {
                boxShadow: beforeStyle.boxShadow,
                borderColor: beforeStyle.borderColor,
                backgroundColor: beforeStyle.backgroundColor
              };
              element.focus({preventScroll: true});
              const after = getComputedStyle(element);
              const outlineVisible =
                after.outlineStyle !== "none" &&
                after.outlineWidth !== "0px" &&
                after.outlineColor !== "transparent";
              const changedIndicator =
                after.boxShadow !== before.boxShadow ||
                after.borderColor !== before.borderColor ||
                after.backgroundColor !== before.backgroundColor;
              if (document.activeElement !== element || (!outlineVisible && !changedIndicator)) {
                add(
                  "GUIDE-FOCUS-VISIBILITY",
                  `focus is not visibly exposed for ${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}`
                );
              }
            }
            if (document.activeElement && document.activeElement.blur) {
              document.activeElement.blur();
            }
          }

          if (active.has("GUIDE-TARGET-SIZE")) {
            for (const element of focusables) {
              if (
                element.tagName.toLowerCase() === "a" &&
                getComputedStyle(element).display === "inline"
              ) {
                continue;
              }
              const rect = element.getBoundingClientRect();
              let width = rect.width;
              let height = rect.height;
              if (element.labels) {
                for (const label of element.labels) {
                  const labelRect = label.getBoundingClientRect();
                  width = Math.max(width, labelRect.width);
                  height = Math.max(height, labelRect.height);
                }
              }
              if (width + 0.5 < minimumTarget || height + 0.5 < minimumTarget) {
                add(
                  "GUIDE-TARGET-SIZE",
                  `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""} is ${Math.round(width)}x${Math.round(height)}; minimum is ${minimumTarget}px`
                );
              }
            }
          }

          if (
            active.has("GUIDE-HORIZONTAL-OVERFLOW") &&
            document.documentElement.scrollWidth >
              document.documentElement.clientWidth + 1
          ) {
            add(
              "GUIDE-HORIZONTAL-OVERFLOW",
              `document width ${document.documentElement.scrollWidth}px exceeds viewport ${document.documentElement.clientWidth}px`
            );
          }

          if (active.has("GUIDE-IMAGE-ALTERNATIVES")) {
            for (const image of document.querySelectorAll("img:not([alt])")) {
              add(
                "GUIDE-IMAGE-ALTERNATIVES",
                `img${image.id ? `#${image.id}` : ""} is missing alt`
              );
            }
          }

          if (active.has("GUIDE-REDUCED-MOTION")) {
            const animated = Array.from(document.querySelectorAll("*")).some(
              element => {
                const style = getComputedStyle(element);
                return style.animationName !== "none" &&
                  style.animationDuration
                    .split(",")
                    .some(value => parseFloat(value) > 0);
              }
            );
            let reducedMotionRule = false;
            const inspectRules = rules => {
              for (const rule of Array.from(rules || [])) {
                if (
                  String(rule.conditionText || "")
                    .toLowerCase()
                    .includes("prefers-reduced-motion")
                ) {
                  return true;
                }
                if (rule.cssRules && inspectRules(rule.cssRules)) {
                  return true;
                }
              }
              return false;
            };
            for (const sheet of Array.from(document.styleSheets)) {
              try {
                if (inspectRules(sheet.cssRules)) {
                  reducedMotionRule = true;
                  break;
                }
              } catch (_) {
                // Cross-origin sheets are not inspectable; local output still
                // needs an explicit accessible fallback in inspectable CSS.
              }
            }
            if (animated && !reducedMotionRule) {
              add(
                "GUIDE-REDUCED-MOTION",
                "CSS Animation exists without an inspectable prefers-reduced-motion rule"
              );
            }
          }
          return issues;
        }
        """,
        {
            "activeRuleIds": active_rule_ids,
            "minimumTarget": minimum_target,
        },
    )
    if not isinstance(findings, list):
        return ["design-guidance browser check returned an invalid result"]
    return [
        f"{item.get('ruleId', 'GUIDE-UNKNOWN')}: {item.get('message', 'failed')}"
        for item in findings
        if isinstance(item, dict)
    ]


def build_guidance_rule_results(
    guidance,
    guidance_viewports,
    experience_results=None,
    contract_results=None,
):
    validator = _load_design_guidance_validator()
    applicability = validator.normalized_rule_applicabilities(guidance)
    declarations = validator.normalized_rule_declarations(guidance)
    results = []
    for rule_id in sorted(applicability):
        rule = validator.HARD_RULES.get(rule_id, {})
        rule_applicability = applicability[rule_id]
        if rule_applicability == "not_applicable":
            status = "not_applicable"
            evidence = "Design Guidance marks this rule not applicable"
        elif validator.rule_evidence_type(guidance, rule_id) == "authored":
            declaration = declarations.get(rule_id)
            status = "declared" if declaration else "not_run"
            evidence = declaration or "Authored declaration is required"
        elif validator.rule_evidence_type(guidance, rule_id) == "experience":
            state_results = list(experience_results or contract_results or [])
            if state_results:
                failures = [
                    item.get("id")
                    for item in state_results
                    if item.get("status") != "passed"
                ]
                status = "failed" if failures else "passed"
                evidence = {
                    "scenarioIds": [item.get("id") for item in state_results],
                    "failedScenarioIds": failures,
                }
            else:
                status = "not_run"
                evidence = "State or interaction evidence is required"
        elif validator.rule_evidence_type(guidance, rule_id) == "declared":
            status = "not_run"
            evidence = "State or interaction evidence is required"
        else:
            failures = [
                error
                for viewport in guidance_viewports
                for error in viewport.get("errors", [])
                if error.startswith(f"{rule_id}:")
            ]
            status = "failed" if failures else "passed"
            evidence = (
                failures
                if failures
                else [
                    {
                        "viewport": viewport.get("viewport"),
                        "status": viewport.get("status"),
                    }
                    for viewport in guidance_viewports
                ]
            )
        results.append(
            {
                "id": rule_id,
                "applicability": rule_applicability,
                "status": status,
                "evidence": evidence,
            }
        )
    return results


def verify_visual_anchor_gates(page, guidance):
    anchors = guidance.get("visualAnchors", [])
    if not anchors:
        return [], []
    evidence = page.evaluate(
        """
        anchors => anchors.map(anchor => {
          let elements;
          try {
            elements = Array.from(document.querySelectorAll(anchor.selector));
          } catch (error) {
            return {
              id: anchor.id,
              selector: anchor.selector,
              status: "failed",
              issues: [`invalid selector: ${error.message}`]
            };
          }
          const issues = [];
          if (anchor.checks.includes("unique") && elements.length !== 1) {
            issues.push(`expected one element, found ${elements.length}`);
          }
          const element = elements[0];
          if (!element) {
            issues.push("element not found");
          } else {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            const visible = style.display !== "none" &&
              style.visibility !== "hidden" &&
              Number(style.opacity || 1) > 0 &&
              rect.width > 0 && rect.height > 0;
            if (anchor.checks.includes("visible") && !visible) {
              issues.push("element is not visible");
            }
            if (
              anchor.checks.includes("no_clipping") &&
              (element.scrollWidth > element.clientWidth + 1 ||
                element.scrollHeight > element.clientHeight + 1)
            ) {
              issues.push(
                `content clips: ${element.scrollWidth}x${element.scrollHeight} ` +
                `inside ${element.clientWidth}x${element.clientHeight}`
              );
            }
            return {
              id: anchor.id,
              selector: anchor.selector,
              role: anchor.role,
              priority: anchor.priority,
              checks: anchor.checks,
              status: issues.length ? "failed" : "passed",
              issues,
              computed: {
                display: style.display,
                fontFamily: style.fontFamily,
                fontSize: style.fontSize,
                fontWeight: style.fontWeight,
                lineHeight: style.lineHeight,
                color: style.color,
                backgroundColor: style.backgroundColor,
                width: Math.round(rect.width * 100) / 100,
                height: Math.round(rect.height * 100) / 100
              }
            };
          }
          return {
            id: anchor.id,
            selector: anchor.selector,
            role: anchor.role,
            priority: anchor.priority,
            checks: anchor.checks,
            status: "failed",
            issues
          };
        })
        """,
        anchors,
    )
    if not isinstance(evidence, list):
        return ["GUIDE-VISUAL-ANCHORS: browser evidence is invalid"], []
    errors = [
        f"GUIDE-VISUAL-ANCHORS: {item.get('id')} {issue}"
        for item in evidence
        if isinstance(item, dict)
        for issue in item.get("issues", [])
    ]
    return errors, evidence


def guidance_completion_errors(rule_results):
    return [
        f"{item.get('id')}: required guidance rule was not run"
        for item in rule_results
        if item.get("applicability") == "required"
        and item.get("status") == "not_run"
    ]


class VerifyArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError(message)


def parse_viewport(value):
    match = re.fullmatch(r"([1-9]\d*)[xX]([1-9]\d*)", value.strip())
    if not match:
        raise InputError(f"非法 viewport: {value!r}，应为 WxH")
    width, height = (int(part) for part in match.groups())
    if width > 10000 or height > 10000:
        raise InputError(f"viewport 超出范围: {value!r}")
    return {"width": width, "height": height}


def parse_changed_aspects(value):
    if not value:
        return []
    aspects = []
    for raw in value.split(","):
        aspect = raw.strip().lower()
        if not aspect:
            continue
        if not re.fullmatch(r"[a-z0-9_-]+", aspect):
            raise InputError(f"非法 changed aspect: {raw!r}")
        if aspect not in aspects:
            aspects.append(aspect)
    return aspects


def validate_changed_aspects(aspects):
    unsupported = sorted(set(aspects) - SUPPORTED_CHANGED_ASPECTS)
    if unsupported:
        raise InputError(
            "不支持的 changed aspect: " + ", ".join(unsupported)
        )


def unique_nonempty(values, label):
    result = []
    for raw in values or []:
        value = raw.strip()
        if not value:
            raise InputError(f"{label} 不能为空")
        if value not in result:
            result.append(value)
    return result


def validate_expected_copy(html_path, expected_copies):
    text = Path(html_path).read_text(encoding="utf-8", errors="ignore")
    return [copy for copy in expected_copies if copy not in text]


def sanitize_screenshot_label(value):
    label = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return label[:48] or "target"


_DEFAULT_REFERENCE_STATE = object()


def reference_screenshots_for_viewport(
    design_reference,
    viewport,
    device_scale_factor=2,
    state_id=_DEFAULT_REFERENCE_STATE,
):
    matches = []
    for screenshot in design_reference.get("referenceScreenshots", []):
        target = screenshot.get("viewport", {})
        screenshot_state = screenshot.get("stateId")
        state_matches = (
            not screenshot_state
            if state_id is _DEFAULT_REFERENCE_STATE
            else screenshot_state == state_id
        )
        if (
            target.get("width") == viewport.get("width")
            and target.get("height") == viewport.get("height")
            and float(target.get("deviceScaleFactor", 0)) == float(device_scale_factor)
            and state_matches
        ):
            matches.append(screenshot)
    return matches


def matching_reference_screenshot(
    design_reference,
    viewport,
    device_scale_factor=2,
    state_id=_DEFAULT_REFERENCE_STATE,
):
    matches = reference_screenshots_for_viewport(
        design_reference,
        viewport,
        device_scale_factor,
        state_id,
    )
    if len(matches) != 1:
        return None
    return matches[0]


def _scaled_locator_region(page, selector, scale):
    locator = page.locator(selector)
    count = locator.count()
    if count != 1 or not locator.first.is_visible():
        raise InputError(
            f"design reference comparison selector must be unique and visible: {selector}"
        )
    box = locator.first.bounding_box()
    if not isinstance(box, dict):
        raise InputError(
            f"design reference comparison selector has no bounding box: {selector}"
        )
    return {
        "x": float(box["x"]) * scale,
        "y": float(box["y"]) * scale,
        "width": float(box["width"]) * scale,
        "height": float(box["height"]) * scale,
    }


def capture_reference_comparison_geometry(page, reference_screenshot):
    comparison = reference_screenshot.get("comparison", {})
    if not comparison:
        return None
    scale = float(
        reference_screenshot.get("viewport", {}).get("deviceScaleFactor", 1)
    )
    region_selector = comparison.get("regionSelector")
    mask_selectors = list(comparison.get("maskSelectors", []))
    return {
        "regionSelector": region_selector,
        "region": (
            _scaled_locator_region(page, region_selector, scale)
            if region_selector
            else None
        ),
        "maskSelectors": mask_selectors,
        "masks": [
            _scaled_locator_region(page, selector, scale)
            for selector in mask_selectors
        ],
    }


def _state_screenshot_evidence(*scenario_groups):
    evidence = []
    for scenarios in scenario_groups:
        for scenario in scenarios or []:
            for step in scenario.get("steps", []):
                screenshot = step.get("screenshot")
                if isinstance(screenshot, dict) and screenshot.get("stateId"):
                    evidence.append(
                        {
                            "scenarioId": scenario.get("id"),
                            "stepId": step.get("id") or step.get("index"),
                            "screenshot": screenshot,
                        }
                    )
    return evidence


def compare_design_reference_state_evidence(
    design_reference,
    design_reference_path,
    viewport,
    output_dir,
    experience_results,
    contract_results,
    *,
    channel_threshold,
    max_mismatch_ratio,
    screenshot_files=None,
):
    errors = []
    results = []
    base = Path(design_reference_path).resolve().parent
    evidence = _state_screenshot_evidence(
        experience_results,
        contract_results,
    )
    state_references = [
        screenshot
        for screenshot in design_reference.get("referenceScreenshots", [])
        if screenshot.get("stateId")
        and screenshot.get("viewport", {}).get("width") == viewport.get("width")
        and screenshot.get("viewport", {}).get("height") == viewport.get("height")
        and float(
            screenshot.get("viewport", {}).get("deviceScaleFactor", 0)
        )
        == 2.0
    ]
    for reference in state_references:
        state_id = reference["stateId"]
        actuals = [
            item
            for item in evidence
            if item["screenshot"].get("stateId") == state_id
            and item["screenshot"].get("viewport") == viewport
        ]
        if not actuals:
            result = {
                "status": "failed",
                "reason": "missing_state_evidence",
                "stateId": state_id,
                "viewport": viewport,
                "referencePath": str(base / reference["path"]),
            }
            results.append(result)
            errors.append(f"design reference state was not captured: {state_id}")
            continue
        for actual in actuals:
            screenshot = actual["screenshot"]
            geometry = screenshot.get("comparisonGeometry")
            if reference.get("comparison") and not geometry:
                result = {
                    "status": "failed",
                    "reason": "missing_comparison_geometry",
                    "stateId": state_id,
                    "viewport": viewport,
                    "scenarioId": actual.get("scenarioId"),
                    "stepId": actual.get("stepId"),
                }
            else:
                actual_path = Path(screenshot["path"])
                diff_path = Path(output_dir) / f"{actual_path.stem}-diff.png"
                try:
                    result = _load_visual_diff().compare_png(
                        base / reference["path"],
                        actual_path,
                        diff_path,
                        channel_threshold=channel_threshold,
                        max_mismatch_ratio=max_mismatch_ratio,
                        compare_region=(geometry or {}).get("region"),
                        ignore_regions=(geometry or {}).get("masks"),
                    )
                except (OSError, ValueError) as error:
                    result = {
                        "status": "error",
                        "reason": str(error),
                        "diffPath": None,
                    }
                result.update(
                    stateId=state_id,
                    viewport=viewport,
                    scenarioId=actual.get("scenarioId"),
                    stepId=actual.get("stepId"),
                    referencePath=str(base / reference["path"]),
                    actualPath=str(actual_path),
                    comparisonGeometry=geometry,
                )
            results.append(result)
            if result.get("diffPath") and screenshot_files is not None:
                screenshot_files.append(result["diffPath"])
            if result.get("status") != "passed":
                errors.append(
                    f"visual diff failed for {state_id}: "
                    f"{result.get('reason') or result.get('mismatchRatio')}"
                )
    return errors, results


def build_evidence_runs(previous_report, current_report):
    runs = []
    if isinstance(previous_report, dict):
        existing = previous_report.get("evidenceRuns")
        if isinstance(existing, list):
            runs.extend(item for item in existing if isinstance(item, dict))
        elif previous_report.get("status"):
            previous_execution = previous_report.get("execution", {})
            previous_artifact = previous_report.get("artifact", {})
            runs.append(
                {
                    "scope": previous_execution.get("tier", "environment"),
                    "status": previous_report.get("status"),
                    "verificationProfile": previous_report.get(
                        "verificationProfile", "strict_regression"
                    ),
                    "verificationProfileStatus": previous_report.get(
                        "verificationProfileStatus",
                        (
                            "unavailable"
                            if previous_report.get("status") == "degraded"
                            else previous_report.get("status")
                        ),
                    ),
                    "profile": previous_report.get("profile"),
                    "artifactSha256": previous_artifact.get("sha256") if isinstance(previous_artifact, dict) else None,
                    "checks": previous_artifact.get("checks", []) if isinstance(previous_artifact, dict) else [],
                }
            )
    execution = current_report.get("execution", {})
    artifact = current_report.get("artifact", {})
    runs.append(
        {
            "scope": execution.get("tier", "environment"),
            "status": current_report.get("status"),
            "verificationProfile": current_report.get(
                "verificationProfile", "strict_regression"
            ),
            "verificationProfileStatus": current_report.get(
                "verificationProfileStatus", current_report.get("status")
            ),
            "profile": current_report.get("profile"),
            "artifactSha256": artifact.get("sha256") if isinstance(artifact, dict) else None,
            "checks": artifact.get("checks", []) if isinstance(artifact, dict) else [],
        }
    )
    return runs[-20:]


def sha256_path(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_previous_report(path):
    if not path:
        return None
    source = Path(path)
    try:
        report = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise InputError(f"previous report does not exist: {source}") from None
    except json.JSONDecodeError as error:
        raise InputError(f"previous report is invalid JSON: {error.msg}") from error
    if not isinstance(report, dict):
        raise InputError("previous report root must be an object")
    return report


EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "\u2600-\u27BF"
    "]"
)


def find_unapproved_emoji(html_path):
    text = Path(html_path).read_text(encoding="utf-8", errors="ignore")
    if 'data-allow-emoji="true"' in text or "demo-design: allow emoji" in text:
        return []

    findings = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        matches = EMOJI_RE.findall(line)
        if matches:
            unique = "".join(dict.fromkeys(matches))
            findings.append((line_no, unique, line.strip()[:160]))
    return findings


def _load_playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright


def _default_browser_candidates():
    known_paths = (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        os.path.expandvars(r"$PROGRAMFILES\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"$PROGRAMFILES\Chromium\Application\chrome.exe"),
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    )
    candidates = []
    seen = set()
    for executable_path in known_paths:
        normalized = str(Path(executable_path)) if executable_path else ""
        if normalized and normalized not in seen and Path(normalized).is_file():
            seen.add(normalized)
            candidates.append(
                {"executable_path": normalized, "label": f"local:{normalized}"}
            )
    if candidates:
        return candidates
    return [{"channel": "chrome", "label": "local-chrome-channel"}]


def _browser_candidates(playwright, browser_candidates=None):
    if browser_candidates is not None:
        candidates = list(browser_candidates)
    else:
        bundled_path = getattr(playwright.chromium, "executable_path", None)
        candidates = []
        if bundled_path and Path(bundled_path).is_file():
            candidates.append(
                {
                    "executable_path": str(Path(bundled_path)),
                    "label": "bundled-chromium",
                }
            )
        candidates.extend(_default_browser_candidates())

    unique = []
    seen = set()
    for candidate in candidates:
        options = _candidate_launch_options(candidate)
        identity = tuple(sorted(options.items()))
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(candidate)
    return unique


def _candidate_launch_options(candidate):
    return {
        key: value
        for key, value in candidate.items()
        if key in ("channel", "executable_path")
    }


def _launch_browser_candidates(
    playwright,
    *,
    headless,
    launch_timeout_ms,
    browser_candidates=None,
    launch_options=None,
    browser_policy="full",
):
    if launch_options:
        candidates = [
            {
                **launch_options,
                "label": "preselected-browser",
            }
        ]
    else:
        candidates = _browser_candidates(
            playwright,
            browser_candidates=browser_candidates,
        )
        if browser_policy == "fast":
            candidates = candidates[:1]

    attempts = []
    for candidate in candidates:
        label = candidate.get("label", "local-browser")
        options = _candidate_launch_options(candidate)
        executable_path = options.get("executable_path")
        if executable_path and not Path(executable_path).is_file():
            attempts.append(
                {"source": label, "error": "executable not found"}
            )
            continue
        started = time.monotonic()
        try:
            browser = playwright.chromium.launch(
                headless=headless,
                timeout=launch_timeout_ms,
                **options,
            )
            return {
                "browser": browser,
                "source": label,
                "launch_options": options,
                "attempts": attempts,
                "launch_ms": round(
                    (time.monotonic() - started) * 1000,
                    2,
                ),
            }
        except Exception as error:
            attempts.append({"source": label, "error": str(error)})

    details = {
        "available": False,
        "status": "degraded",
        "source": None,
        "attempts": attempts,
    }
    reason = (
        attempts[-1]["error"]
        if attempts
        else "没有可用的本地浏览器候选"
    )
    raise BrowserUnavailable(reason, details=details)


def probe_browser(
    playwright_loader=_load_playwright,
    browser_candidates=None,
    launch_timeout_ms=DEFAULT_LAUNCH_TIMEOUT_MS,
):
    """Return a JSON-safe browser capability result without network activity."""
    try:
        sync_playwright = playwright_loader()
    except (ImportError, ModuleNotFoundError) as error:
        return {
            "available": False,
            "status": "degraded",
            "source": None,
            "launch_options": None,
            "attempts": [{"source": "python-playwright", "error": str(error)}],
        }

    attempts = []

    try:
        with sync_playwright() as playwright:
            try:
                launched = _launch_browser_candidates(
                    playwright,
                    headless=True,
                    launch_timeout_ms=launch_timeout_ms,
                    browser_candidates=browser_candidates,
                    browser_policy="full",
                )
            except BrowserUnavailable as error:
                return error.details
            browser = launched["browser"]
            browser.close()
            return {
                "available": True,
                "status": "passed",
                "source": launched["source"],
                "launch_options": launched["launch_options"],
                "attempts": launched["attempts"],
                "launch_ms": launched["launch_ms"],
            }
    except Exception as error:
        attempts.append({"source": "playwright", "error": str(error)})

    return {
        "available": False,
        "status": "degraded",
        "source": None,
        "launch_options": None,
        "attempts": attempts,
    }


def verify_html(
    html_path,
    viewports=None,
    slides=0,
    output_dir=None,
    show=False,
    wait=2000,
    launch_options=None,
    launch_timeout_ms=DEFAULT_LAUNCH_TIMEOUT_MS,
    playwright_loader=_load_playwright,
    profile=None,
    product_contract=None,
    experience_checks=None,
    design_guidance=None,
    design_reference=None,
    design_reference_path=None,
    visual_diff_channel_threshold=16,
    visual_diff_max_mismatch_ratio=0.01,
    portability=False,
    artifact_details=None,
    tier="tier_3_full_delivery",
    changed_aspects=None,
    ready_selector=None,
    browser_candidates=None,
    target_selectors=None,
    action_ids=None,
    result_selectors=None,
    browser_policy="full",
    browser_endpoint=None,
    navigation_timeout_ms=DEFAULT_NAVIGATION_TIMEOUT_MS,
):
    """Render and inspect an HTML artifact, preserving the legacy return API."""
    try:
        sync_playwright = playwright_loader()
    except (ImportError, ModuleNotFoundError) as error:
        raise BrowserUnavailable("Playwright Python 包不可用") from error

    html_path = Path(html_path).resolve()
    if not html_path.is_file():
        raise InputError(f"文件不存在: {html_path}")

    emoji_findings = find_unapproved_emoji(html_path)
    if output_dir is None:
        output_dir = html_path.parent / "screenshots"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = html_path.stem
    if viewports is None:
        viewports = [{"width": 1440, "height": 900}]

    console_errors = []
    console_warnings = []
    page_errors = []
    request_failures = []
    broken_images = []
    guidance_viewports = []
    changed_aspects = list(changed_aspects or [])
    target_selectors = list(target_selectors or [])
    action_ids = list(action_ids or [])
    result_selectors = list(result_selectors or [])
    launch_options = dict(launch_options or {})
    verification_started = time.monotonic()
    browser_details = None
    target_results = []
    action_results = []
    contract_scenario_results = []
    experience_scenario_results = []
    visual_diff_results = []
    screenshot_files = []
    phase_timings = {
        "browser_launch_ms": 0,
        "navigation_ms": 0,
        "stabilization_ms": 0,
        "checks_ms": 0,
        "screenshot_ms": 0,
        "cleanup_ms": 0,
    }

    try:
        with loopback_preview(html_path) as navigation_url, sync_playwright() as playwright:
            if browser_endpoint:
                started = time.monotonic()
                try:
                    browser = playwright.chromium.connect_over_cdp(
                        browser_endpoint,
                        timeout=launch_timeout_ms,
                    )
                except Exception as error:
                    raise BrowserUnavailable(
                        f"warm browser session connection failed: {error}",
                        details={
                            "available": False,
                            "status": "degraded",
                            "source": "warm-browser-session",
                            "attempts": [
                                {
                                    "source": "warm-browser-session",
                                    "error": str(error),
                                }
                            ],
                        },
                    ) from error
                launched = {
                    "browser": browser,
                    "source": "warm-browser-session",
                    "launch_options": None,
                    "attempts": [],
                    "launch_ms": round((time.monotonic() - started) * 1000, 2),
                }
            else:
                launched = _launch_browser_candidates(
                    playwright,
                    headless=not show,
                    launch_timeout_ms=launch_timeout_ms,
                    browser_candidates=browser_candidates,
                    launch_options=launch_options,
                    browser_policy=browser_policy,
                )
            browser = launched["browser"]
            browser_details = {
                "available": True,
                "status": "passed",
                "source": launched["source"],
                "launch_options": launched["launch_options"],
                "policy": browser_policy,
                "warm_session": bool(browser_endpoint),
                "attempts": launched["attempts"],
                "launch_ms": launched["launch_ms"],
            }
            phase_timings["browser_launch_ms"] = launched["launch_ms"]

            for viewport in viewports:
                context = browser.new_context(viewport=viewport, device_scale_factor=2)
                page = context.new_page()
                page.on(
                    "console",
                    lambda message: (
                        console_errors.append(f"[{message.type}] {message.text}")
                        if message.type == "error"
                        else console_warnings.append(
                            f"[{message.type}] {message.text}"
                        )
                        if message.type == "warning"
                        else None
                    ),
                )
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on(
                    "requestfailed",
                    lambda request: request_failures.append(
                        {
                            "url": request.url,
                            "failure": request.failure,
                        }
                    ),
                )

                print(
                    f"\n→ 打开 {navigation_url} "
                    f"@ {viewport['width']}x{viewport['height']}"
                )
                navigation_started = time.monotonic()
                page.goto(
                    navigation_url,
                    wait_until="domcontentloaded",
                    timeout=navigation_timeout_ms,
                )
                phase_timings["navigation_ms"] += round(
                    (time.monotonic() - navigation_started) * 1000,
                    2,
                )
                if ready_selector:
                    page.wait_for_selector(
                        ready_selector,
                        state="visible",
                        timeout=navigation_timeout_ms,
                    )
                stabilization_started = time.monotonic()
                page.wait_for_timeout(wait)
                phase_timings["stabilization_ms"] += round(
                    (time.monotonic() - stabilization_started) * 1000,
                    2,
                )

                if design_reference:
                    reference_capture_started = time.monotonic()
                    reference = matching_reference_screenshot(
                        design_reference,
                        viewport,
                        device_scale_factor=2,
                    )
                    if reference is None or not design_reference_path:
                        result = {
                            "status": "failed",
                            "reason": "missing_unique_reference_for_viewport",
                            "stateId": None,
                            "viewport": viewport,
                        }
                        visual_diff_results.append(result)
                        page_errors.append(
                            "visual diff requires one default-state reference for "
                            f"{viewport['width']}x{viewport['height']} at 2x"
                        )
                    else:
                        suffix = f"-{viewport['width']}x{viewport['height']}"
                        actual_path = (
                            output_dir / f"{stem}-reference-default{suffix}.png"
                        )
                        page.screenshot(path=str(actual_path), full_page=False)
                        screenshot_files.append(str(actual_path))
                        reference_path = (
                            Path(design_reference_path).resolve().parent
                            / reference["path"]
                        )
                        diff_path = (
                            output_dir
                            / f"{stem}-reference-default{suffix}-diff.png"
                        )
                        try:
                            geometry = capture_reference_comparison_geometry(
                                page,
                                reference,
                            )
                            result = _load_visual_diff().compare_png(
                                reference_path,
                                actual_path,
                                diff_path,
                                channel_threshold=visual_diff_channel_threshold,
                                max_mismatch_ratio=visual_diff_max_mismatch_ratio,
                                compare_region=(geometry or {}).get("region"),
                                ignore_regions=(geometry or {}).get("masks"),
                            )
                        except (OSError, ValueError, InputError) as error:
                            geometry = None
                            result = {
                                "status": "error",
                                "reason": str(error),
                                "diffPath": None,
                            }
                        result.update(
                            stateId=None,
                            viewport=viewport,
                            referencePath=str(reference_path),
                            actualPath=str(actual_path),
                            comparisonGeometry=geometry,
                        )
                        visual_diff_results.append(result)
                        if result.get("diffPath"):
                            screenshot_files.append(result["diffPath"])
                        if result.get("status") != "passed":
                            page_errors.append(
                                "visual diff failed for default state at "
                                f"{viewport['width']}x{viewport['height']}: "
                                f"{result.get('reason') or result.get('mismatchRatio')}"
                            )
                    phase_timings["screenshot_ms"] += round(
                        (time.monotonic() - reference_capture_started) * 1000,
                        2,
                    )

                checks_started = time.monotonic()
                if portability:
                    viewport_broken_images = page.evaluate(
                        """
                        () => Array.from(document.images)
                          .filter(image => {
                            const style = getComputedStyle(image);
                            const rect = image.getBoundingClientRect();
                            return style.display !== 'none' &&
                              style.visibility !== 'hidden' &&
                              rect.width > 0 && rect.height > 0 &&
                              (!image.complete || image.naturalWidth === 0);
                          })
                          .map(image => image.currentSrc || image.src || '<inline image>')
                        """
                    )
                    broken_images.extend(viewport_broken_images)
                    for source in viewport_broken_images:
                        page_errors.append(f"visible image failed to load: {source}")
                if profile == "product-contract":
                    if not product_contract:
                        page_errors.append("product-contract data is missing")
                    else:
                        page_errors.extend(
                            verify_product_contract_profile(
                                page,
                                product_contract,
                                contract_scenario_results,
                                output_dir=output_dir,
                                stem=stem,
                                viewport=viewport,
                                screenshot_files=screenshot_files,
                                navigation_timeout_ms=navigation_timeout_ms,
                                design_reference=design_reference,
                            )
                        )

                if experience_checks:
                    page_errors.extend(
                        verify_experience_checks_profile(
                            page,
                            experience_checks,
                            experience_scenario_results,
                            output_dir=output_dir,
                            stem=stem,
                            viewport=viewport,
                            screenshot_files=screenshot_files,
                            navigation_timeout_ms=navigation_timeout_ms,
                            design_reference=design_reference,
                        )
                    )

                if design_guidance:
                    guidance_errors = verify_design_guidance_hard_gates(
                        page,
                        design_guidance,
                    )
                    anchor_errors, anchor_evidence = verify_visual_anchor_gates(
                        page,
                        design_guidance,
                    )
                    guidance_errors.extend(anchor_errors)
                    guidance_viewports.append(
                        {
                            "viewport": viewport,
                            "status": "failed" if guidance_errors else "passed",
                            "errors": guidance_errors,
                            "visualAnchors": anchor_evidence,
                        }
                    )
                    page_errors.extend(guidance_errors)

                for selector in target_selectors:
                    locator = page.locator(selector)
                    count = locator.count()
                    target_result = {
                        "selector": selector,
                        "viewport": viewport,
                        "count": count,
                        "status": "passed",
                        "visible": False,
                        "horizontalOverflow": None,
                    }
                    if count == 0:
                        target_result["status"] = "failed"
                        page_errors.append(f"target selector not found: {selector}")
                    else:
                        target = locator.first
                        target_result["visible"] = target.is_visible()
                        if not target_result["visible"]:
                            target_result["status"] = "failed"
                            page_errors.append(f"target selector is not visible: {selector}")
                        if set(changed_aspects) & (
                            TARGET_VISUAL_ASPECTS | RESPONSIVE_ASPECTS
                        ):
                            overflow = target.evaluate(
                                "node => node.scrollWidth > node.clientWidth + 1"
                            )
                            target_result["horizontalOverflow"] = bool(overflow)
                            if overflow:
                                target_result["status"] = "failed"
                                page_errors.append(
                                    f"target has horizontal overflow: {selector}"
                                )
                    target_results.append(target_result)

                for action_id in action_ids:
                    selector = f'[data-action-id="{action_id}"]'
                    locator = page.locator(selector)
                    count = locator.count()
                    action_result = {
                        "actionId": action_id,
                        "viewport": viewport,
                        "status": "passed",
                    }
                    if count == 0:
                        action_result["status"] = "failed"
                        page_errors.append(f"action not found: {action_id}")
                    else:
                        locator.first.click(timeout=navigation_timeout_ms)
                        page.wait_for_timeout(min(100, wait))
                    action_results.append(action_result)

                for selector in result_selectors:
                    locator = page.locator(selector)
                    if locator.count() == 0 or not locator.first.is_visible():
                        page_errors.append(
                            f"observable result selector is not visible: {selector}"
                        )

                phase_timings["checks_ms"] += round(
                    (time.monotonic() - checks_started) * 1000,
                    2,
                )

                if design_reference and design_reference_path:
                    state_errors, state_results = (
                        compare_design_reference_state_evidence(
                            design_reference,
                            design_reference_path,
                            viewport,
                            output_dir,
                            experience_scenario_results,
                            contract_scenario_results,
                            channel_threshold=visual_diff_channel_threshold,
                            max_mismatch_ratio=visual_diff_max_mismatch_ratio,
                            screenshot_files=screenshot_files,
                        )
                    )
                    page_errors.extend(state_errors)
                    visual_diff_results.extend(state_results)

                screenshot_started = time.monotonic()
                if slides > 0:
                    for index in range(slides):
                        screenshot_path = output_dir / f"{stem}-slide-{index + 1:02d}.png"
                        page.screenshot(path=str(screenshot_path), full_page=False)
                        screenshot_files.append(str(screenshot_path))
                        print(f"  ✓ slide {index + 1} → {screenshot_path.name}")
                        if index < slides - 1:
                            page.keyboard.press("ArrowRight")
                            page.wait_for_timeout(500)
                elif target_selectors and tier in (
                    "tier_1_local_ui_patch",
                    "tier_2_layout_or_interaction",
                ):
                    for index, selector in enumerate(target_selectors, start=1):
                        locator = page.locator(selector)
                        if locator.count() == 0 or not locator.first.is_visible():
                            continue
                        label = sanitize_screenshot_label(selector)
                        suffix = (
                            f"-{viewport['width']}x{viewport['height']}"
                            if len(viewports) > 1
                            else ""
                        )
                        screenshot_path = (
                            output_dir / f"{stem}-target-{index:02d}-{label}{suffix}.png"
                        )
                        locator.first.screenshot(
                            path=str(screenshot_path),
                            timeout=navigation_timeout_ms,
                        )
                        screenshot_files.append(str(screenshot_path))
                        print(f"  ✓ 目标截图 → {screenshot_path.name}")
                else:
                    suffix = (
                        f"-{viewport['width']}x{viewport['height']}"
                        if len(viewports) > 1
                        else ""
                    )
                    screenshot_path = output_dir / f"{stem}{suffix}.png"
                    page.screenshot(path=str(screenshot_path), full_page=False)
                    screenshot_files.append(str(screenshot_path))
                    print(f"  ✓ 截图 → {screenshot_path.name}")
                    if tier == "tier_3_full_delivery":
                        full_path = output_dir / f"{stem}{suffix}-full.png"
                        page.screenshot(path=str(full_path), full_page=True)
                        screenshot_files.append(str(full_path))
                        print(f"  ✓ 完整页 → {full_path.name}")
                phase_timings["screenshot_ms"] += round(
                    (time.monotonic() - screenshot_started) * 1000,
                    2,
                )

                if show:
                    print("  (浏览器窗口保持打开，按Enter关闭...)")
                    input()
                cleanup_started = time.monotonic()
                context.close()
                phase_timings["cleanup_ms"] += round(
                    (time.monotonic() - cleanup_started) * 1000,
                    2,
                )

            cleanup_started = time.monotonic()
            if not browser_endpoint:
                browser.close()
                phase_timings["cleanup_ms"] += round(
                    (time.monotonic() - cleanup_started) * 1000,
                    2,
                )
    except BrowserUnavailable:
        raise

    for failure in request_failures:
        page_errors.append(
            f"resource request failed: {failure.get('url')} ({failure.get('failure')})"
        )

    guidance_rule_results = (
        build_guidance_rule_results(
            design_guidance,
            guidance_viewports,
            experience_scenario_results,
            contract_scenario_results,
        )
        if design_guidance
        else []
    )
    page_errors.extend(guidance_completion_errors(guidance_rule_results))

    print("\n" + "=" * 50)
    print("验证报告")
    print("=" * 50)

    if page_errors or console_errors:
        print(
            "\n❌ Runtime / Verification Errors "
            f"({len(page_errors) + len(console_errors)}):"
        )
        for error in page_errors:
            print(f"  - {error}")
        for error in console_errors:
            print(f"  - {error}")
    else:
        print("\n✅ 无 Console Error、Page Error 或验证错误")

    if console_warnings:
        print(f"\n⚠️  Console Warnings ({len(console_warnings)}):")
        for warning in console_warnings[:20]:
            print(f"  - {warning}")
        if len(console_warnings) > 20:
            print(f"  ... 还有{len(console_warnings) - 20}条")
    else:
        print("✅ 无 Console Warning")

    if emoji_findings:
        print(f"\n❌ 未授权 Emoji ({len(emoji_findings)} 行):")
        for line_no, chars, snippet in emoji_findings[:20]:
            print(f"  - line {line_no}: {chars} | {snippet}")
        if len(emoji_findings) > 20:
            print(f"  ... 还有{len(emoji_findings) - 20}行")
        print(
            '  如确属品牌/用户要求，请在 HTML 标注 data-allow-emoji="true" '
            "或 <!-- demo-design: allow emoji -->"
        )
    else:
        print("✅ 无未授权 Emoji")

    print(f"\n📸 截图保存至: {output_dir}")
    if artifact_details is not None:
        artifact_details["browser"] = browser_details
        artifact_details["tier"] = tier
        artifact_details["changedAspects"] = changed_aspects
        artifact_details["viewports"] = viewports
        artifact_details["targets"] = target_results
        artifact_details["actions"] = action_results
        artifact_details["contractScenarios"] = contract_scenario_results
        artifact_details["experienceScenarios"] = experience_scenario_results
        artifact_details["visualDiffs"] = visual_diff_results
        artifact_details["runtimeEvidence"] = {
            "consoleErrors": console_errors,
            "consoleWarnings": console_warnings,
            "pageErrors": page_errors,
            "requestFailures": request_failures,
        }
        artifact_details["navigation"] = {
            "transport": "loopback_http",
            "url": navigation_url,
        }
        artifact_details["portabilityBrowser"] = {
            "enabled": portability,
            "requestFailures": request_failures,
            "brokenImages": sorted(set(broken_images)),
        }
        artifact_details["screenshots"] = screenshot_files
        artifact_details["checks"] = [
            "basic-render",
            "console-and-page-errors",
            "unauthorized-emoji",
            *(["target-visibility"] if target_selectors else []),
            *(
                ["target-horizontal-overflow"]
                if set(changed_aspects)
                & (TARGET_VISUAL_ASPECTS | RESPONSIVE_ASPECTS)
                else []
            ),
            *(["named-interactions"] if action_ids else []),
            *(["observable-results"] if result_selectors else []),
            *(
                ["product-contract"]
                if profile == "product-contract"
                else []
            ),
            *(
                ["experience-checks"]
                if experience_checks
                else []
            ),
            *(
                ["design-guidance-hard-rules"]
                if design_guidance
                else []
            ),
            *(["reference-png-visual-diff"] if design_reference else []),
            *(["resource-request-and-image-load"] if portability else []),
        ]
        artifact_details["timings"] = {
            **phase_timings,
            "browser_total_ms": round(
                (time.monotonic() - verification_started) * 1000,
                2,
            ),
        }
        artifact_details["guidance"] = {
            "status": (
                "failed"
                if any(
                    item.get("status") == "failed"
                    for item in guidance_rule_results
                )
                else "incomplete"
                if any(
                    item.get("status") == "not_run"
                    for item in guidance_rule_results
                )
                else "passed"
            ),
            "viewports": guidance_viewports,
            "hardRules": guidance_rule_results,
        } if design_guidance else None
    return (
        EXIT_PASSED
        if not page_errors and not console_errors and not emoji_findings
        else EXIT_ARTIFACT_FAILED
    )


def _verification_worker(output_queue, kwargs):
    if os.name == "posix":
        try:
            os.setsid()
        except OSError:
            pass
    artifact_details = {}
    kwargs = dict(kwargs)
    kwargs["artifact_details"] = artifact_details
    try:
        code = verify_html(**kwargs)
        output_queue.put(
            {"kind": "result", "code": code, "artifact": artifact_details}
        )
    except BrowserUnavailable as error:
        output_queue.put(
            {
                "kind": "browser-unavailable",
                "message": str(error),
                "details": error.details,
            }
        )
    except InputError as error:
        output_queue.put({"kind": "input-error", "message": str(error)})
    except Exception as error:
        output_queue.put(
            {
                "kind": "error",
                "message": str(error),
                "errorType": type(error).__name__,
            }
        )


def _stop_verification_process(process):
    if not process.is_alive():
        return
    if os.name == "posix" and process.pid:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            process.terminate()
    else:
        process.terminate()
    process.join(0.5)
    if process.is_alive():
        if os.name == "posix" and process.pid:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                process.kill()
        else:
            process.kill()
        process.join(0.5)


def run_verification_with_deadline(kwargs, wall_timeout_ms):
    context = multiprocessing.get_context("spawn")
    output_queue = context.Queue()
    process = context.Process(
        target=_verification_worker,
        args=(output_queue, kwargs),
    )
    process.start()
    deadline = time.monotonic() + (wall_timeout_ms / 1000)
    payload = None
    try:
        while payload is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _stop_verification_process(process)
                raise VerificationTimeout(wall_timeout_ms)
            try:
                payload = output_queue.get(timeout=min(0.1, remaining))
            except queue.Empty:
                if not process.is_alive():
                    try:
                        payload = output_queue.get(timeout=0.2)
                    except queue.Empty as error:
                        raise InputError(
                            "验证子进程退出但未返回结果"
                            f"（exit {process.exitcode}）"
                        ) from error
        process.join(0.5)
        if process.is_alive():
            _stop_verification_process(process)
    finally:
        output_queue.close()

    if payload["kind"] == "result":
        return payload["code"], payload["artifact"]
    if payload["kind"] == "browser-unavailable":
        raise BrowserUnavailable(payload["message"], details=payload["details"])
    if payload["kind"] == "input-error":
        raise InputError(payload["message"])
    raise InputError(
        "验证脚本错误: "
        + payload.get("errorType", "Exception")
        + ": "
        + payload.get("message", "unknown error")
    )


def build_parser():
    parser = VerifyArgumentParser(
        description=(
            "Run explicitly requested strict regression with bounded "
            "Playwright probing"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("html_path", nargs="?", help="HTML file path")
    parser.add_argument(
        "--viewports",
        default=None,
        help="逗号分隔的 viewport 列表，格式 WxH；默认值由 Tier 决定",
    )
    parser.add_argument(
        "--slides", type=int, default=0, help="幻灯片模式：截取前 N 张"
    )
    parser.add_argument("--output", default=None, help="截图输出目录")
    parser.add_argument("--show", action="store_true", help="打开非 headless 浏览器")
    parser.add_argument(
        "--wait",
        type=int,
        default=None,
        help="页面稳定等待毫秒数；默认值由 Tier 决定",
    )
    parser.add_argument("--check-env", action="store_true", help="只检查浏览器能力")
    parser.add_argument(
        "--browser-executable",
        default=None,
        help="可选的本地 Chromium/Chrome 可执行文件路径",
    )
    parser.add_argument(
        "--launch-timeout-ms",
        type=int,
        default=DEFAULT_LAUNCH_TIMEOUT_MS,
        help=f"浏览器冷启动超时毫秒数（默认 {DEFAULT_LAUNCH_TIMEOUT_MS}）",
    )
    parser.add_argument(
        "--navigation-timeout-ms",
        type=int,
        default=DEFAULT_NAVIGATION_TIMEOUT_MS,
        help=f"页面导航和目标操作超时毫秒数（默认 {DEFAULT_NAVIGATION_TIMEOUT_MS}）",
    )
    parser.add_argument(
        "--wall-timeout-ms",
        type=int,
        default=None,
        help="浏览器验证总截止时间毫秒数；默认值由 Tier 决定",
    )
    parser.add_argument(
        "--browser-policy",
        choices=("fast", "full"),
        default=None,
        help="浏览器候选策略；Tier 1/2 默认 fast，Tier 3 默认 full",
    )
    parser.add_argument(
        "--browser-session",
        choices=("auto", "reuse", "off"),
        default=None,
        help="暖浏览器会话；Tier 1/2 默认 reuse，Tier 3 默认 off",
    )
    parser.add_argument(
        "--browser-session-idle-timeout-seconds",
        type=int,
        default=900,
        help="暖浏览器空闲自动退出秒数（默认 900）",
    )
    parser.add_argument(
        "--profile",
        choices=("product-contract",),
        default=None,
        help="定向验证配置",
    )
    parser.add_argument("--contract", default=None, help="product-contract JSON path")
    parser.add_argument(
        "--experience-checks",
        default=None,
        help=(
            "experience-checks JSON path; runs explicit primary/error/cancel/"
            "recovery interaction evidence without enabling product-contract mode"
        ),
    )
    parser.add_argument(
        "--guidance",
        default=None,
        help="design-guidance.json path; composes with product-contract",
    )
    parser.add_argument(
        "--design-reference",
        default=None,
        help="Tier 3 external design-reference.json path for reference PNG diff",
    )
    parser.add_argument(
        "--portability",
        action="store_true",
        help="explicitly run resource portability checks; Tier 3 enables them by default",
    )
    parser.add_argument(
        "--visual-diff-channel-threshold",
        type=int,
        default=16,
        help="per-channel PNG difference threshold, 0-255 (default 16)",
    )
    parser.add_argument(
        "--visual-diff-max-mismatch-ratio",
        type=float,
        default=0.01,
        help="maximum mismatched-pixel ratio, 0-1 (default 0.01)",
    )
    parser.add_argument(
        "--tier",
        choices=TIERS,
        default="tier_3_full_delivery",
        help="执行和验证 Tier（默认 tier_3_full_delivery）",
    )
    parser.add_argument(
        "--changed-aspects",
        default="",
        help="逗号分隔的修改维度，例如 spacing,color",
    )
    parser.add_argument(
        "--target-selector",
        action="append",
        default=[],
        help="受影响目标的 CSS selector；可重复",
    )
    parser.add_argument(
        "--action-id",
        action="append",
        default=[],
        help="受影响交互的 data-action-id；可重复",
    )
    parser.add_argument(
        "--result-selector",
        action="append",
        default=[],
        help="交互后的可观察结果 CSS selector；可重复",
    )
    parser.add_argument(
        "--expected-copy",
        action="append",
        default=[],
        help="Tier 0 静态检查必须出现的文案；可重复",
    )
    parser.add_argument(
        "--semantic-impact",
        choices=("none", "behavioral", "unknown"),
        default="unknown",
        help="文案是否改变产品语义；Product Contract Tier 0 必须为 none",
    )
    parser.add_argument(
        "--design-system",
        default=None,
        help="可选 DESIGN.md 路径，用于独立 Hash 与 previous-report 复用记录",
    )
    parser.add_argument(
        "--previous-report",
        default=None,
        help="可选的上次 validation-report.json，用于 Hash 匹配与可信复用记录",
    )
    parser.add_argument(
        "--ready-selector",
        default=None,
        help="可选的页面就绪 CSS selector",
    )
    parser.add_argument("--report-json", default=None, help="机器可读摘要路径")
    parser.add_argument(
        "--require-browser",
        action="store_true",
        help="标记当前任务要求浏览器；环境不可用时仍只降级，不安装",
    )
    return parser


def _write_report(report_path, report):
    if not report_path:
        return
    path = Path(report_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as error:
        raise InputError(f"无法写入 JSON 报告 {path}: {error}") from error


def _error_report(args, message):
    return {
        "status": "error",
        "exit_code": EXIT_INPUT_ERROR,
        "verificationProfile": "strict_regression",
        "verificationProfileStatus": "error",
        "profile": getattr(args, "profile", None),
        "browser_required": getattr(args, "require_browser", False),
        "error_type": "input",
        "message": message,
    }


def main(argv=None, probe_func=None, verify_func=verify_html):
    parser = build_parser()
    report_path = None
    try:
        command_started = time.monotonic()
        args = parser.parse_args(argv)
        report_path = args.report_json
        if not args.check_env and not args.html_path:
            raise InputError("普通验证需要提供 HTML 文件路径")
        if args.slides < 0:
            raise InputError("--slides 不能小于 0")
        if args.wait is not None and args.wait < 0:
            raise InputError("--wait 不能小于 0")
        if args.launch_timeout_ms <= 0 or args.launch_timeout_ms > 60000:
            raise InputError("--launch-timeout-ms 必须在 1 到 60000 之间")
        if not 0 <= args.visual_diff_channel_threshold <= 255:
            raise InputError("--visual-diff-channel-threshold 必须在 0 到 255 之间")
        if not 0 <= args.visual_diff_max_mismatch_ratio <= 1:
            raise InputError("--visual-diff-max-mismatch-ratio 必须在 0 到 1 之间")
        if not 30 <= args.browser_session_idle_timeout_seconds <= 86400:
            raise InputError(
                "--browser-session-idle-timeout-seconds 必须在 30 到 86400 之间"
            )
        if (
            args.navigation_timeout_ms <= 0
            or args.navigation_timeout_ms > 120000
        ):
            raise InputError("--navigation-timeout-ms 必须在 1 到 120000 之间")
        wall_timeout_ms = (
            args.wall_timeout_ms
            if args.wall_timeout_ms is not None
            else DEFAULT_WALL_TIMEOUT_MS_BY_TIER[args.tier]
        )
        if wall_timeout_ms < 0 or wall_timeout_ms > 300000:
            raise InputError("--wall-timeout-ms 必须在 0 到 300000 之间")
        browser_policy = args.browser_policy or (
            "fast"
            if args.tier in (
                "tier_1_local_ui_patch",
                "tier_2_layout_or_interaction",
            )
            else "full"
        )
        browser_session_policy = args.browser_session or (
            "reuse"
            if args.tier in (
                "tier_1_local_ui_patch",
                "tier_2_layout_or_interaction",
            )
            else "off"
        )
        if args.check_env:
            browser_session_policy = "off"
        if args.show:
            if args.browser_session not in (None, "off"):
                raise InputError("--show cannot use a headless warm browser session")
            browser_session_policy = "off"
        browser_candidates = (
            [
                {
                    "executable_path": str(
                        Path(args.browser_executable).expanduser()
                    ),
                    "label": f"explicit:{args.browser_executable}",
                }
            ]
            if args.browser_executable
            else None
        )

        viewport_spec = args.viewports or DEFAULT_VIEWPORTS_BY_TIER[args.tier]
        viewports = [parse_viewport(value) for value in viewport_spec.split(",")]
        wait = (
            args.wait
            if args.wait is not None
            else DEFAULT_WAIT_BY_TIER[args.tier]
        )
        changed_aspects = parse_changed_aspects(args.changed_aspects)
        validate_changed_aspects(changed_aspects)
        target_selectors = unique_nonempty(
            args.target_selector,
            "--target-selector",
        )
        action_ids = unique_nonempty(args.action_id, "--action-id")
        result_selectors = unique_nonempty(
            args.result_selector,
            "--result-selector",
        )
        expected_copies = unique_nonempty(args.expected_copy, "--expected-copy")
        previous_report = load_previous_report(args.previous_report)

        def write_current_report(report):
            report.setdefault("verificationProfile", "strict_regression")
            report.setdefault(
                "verificationProfileStatus",
                (
                    "unavailable"
                    if report.get("status") == "degraded"
                    and report.get("exit_code") == EXIT_BROWSER_UNAVAILABLE
                    else report.get("status")
                ),
            )
            report["evidenceRuns"] = build_evidence_runs(previous_report, report)
            _write_report(report_path, report)

        if (
            not args.browser_executable
            and previous_report
            and browser_policy == "fast"
        ):
            previous_browser = previous_report.get("browser")
            previous_launch_options = (
                previous_browser.get("launch_options")
                if isinstance(previous_browser, dict)
                else None
            )
            if isinstance(previous_launch_options, dict) and previous_launch_options:
                browser_candidates = [
                    {
                        **previous_launch_options,
                        "label": "previous-report-browser",
                    }
                ]
        if not args.check_env:
            html_path = Path(args.html_path).resolve()
            if not html_path.is_file():
                raise InputError(f"文件不存在: {html_path}")
            artifact_hash = sha256_path(html_path)
        else:
            artifact_hash = None
        if (
            args.tier == "tier_1_local_ui_patch"
            and changed_aspects
            and not target_selectors
        ):
            raise InputError(
                "tier_1_local_ui_patch with changed aspects requires --target-selector"
            )
        if args.experience_checks and (args.profile or args.contract):
            raise InputError(
                "--experience-checks cannot be combined with product-contract mode"
            )
        if args.experience_checks and args.tier not in {
            "tier_2_layout_or_interaction",
            "tier_3_full_delivery",
        }:
            raise InputError("--experience-checks requires tier 2 or tier 3")
        if set(changed_aspects) & INTERACTION_ASPECTS and not args.experience_checks:
            if not action_ids:
                raise InputError(
                    "interaction changes require --action-id or --experience-checks"
                )
            if not result_selectors:
                raise InputError(
                    "interaction changes require --result-selector or --experience-checks"
                )
        if set(changed_aspects) & ASSET_ASPECTS and args.tier not in {
            "tier_2_layout_or_interaction",
            "tier_3_full_delivery",
        }:
            raise InputError("asset/resource changes require tier 2 or tier 3")
        if args.tier == "tier_0_text_copy_only" and (
            set(changed_aspects) - STATIC_ASPECTS
        ):
            raise InputError("tier_0_text_copy_only only accepts the copy aspect")
        if (
            args.tier == "tier_0_text_copy_only"
            and args.semantic_impact == "behavioral"
        ):
            raise InputError("behavioral copy requires tier 1 or higher")
        if args.design_reference and args.tier != "tier_3_full_delivery":
            raise InputError("--design-reference requires tier_3_full_delivery")
        if args.design_reference and args.slides:
            raise InputError("--design-reference cannot be combined with --slides")
        if args.portability and args.tier == "tier_0_text_copy_only":
            raise InputError("--portability requires tier 1 or higher")
        portability_enabled = (
            args.portability
            or args.tier == "tier_3_full_delivery"
            or bool(set(changed_aspects) & ASSET_ASPECTS)
        )
        safe_contract_copy = (
            args.profile == "product-contract"
            and args.tier == "tier_0_text_copy_only"
            and changed_aspects == ["copy"]
            and args.semantic_impact == "none"
            and bool(expected_copies)
        )
        if (
            args.profile == "product-contract"
            and args.tier == "tier_0_text_copy_only"
            and not safe_contract_copy
        ):
            raise InputError(
                "product-contract Tier 0 requires changed-aspects=copy, "
                "--semantic-impact none, and at least one --expected-copy"
            )
        if (
            args.profile == "product-contract"
            and (CONTRACT_AFFECTING_ASPECTS | {"contract"}).intersection(
                changed_aspects
            )
            and args.tier != "tier_3_full_delivery"
        ):
            raise InputError(
                "Product Contract-affecting changes require tier_3_full_delivery"
            )
        product_contract = None
        static_contract_report = None
        experience_checks = None
        static_experience_report = None
        design_guidance = None
        static_guidance_report = None
        design_reference = None
        static_design_reference_report = None
        design_reference_hash = None
        static_portability_report = None
        guidance_hash = None
        contract_hash = None
        experience_hash = None
        design_system_hash = None
        if not args.check_env and args.design_system:
            design_system_path = Path(args.design_system).resolve()
            if not design_system_path.is_file():
                raise InputError(
                    f"design system does not exist: {design_system_path}"
                )
            design_system_hash = sha256_path(design_system_path)
        if not args.check_env and args.profile == "product-contract":
            if not args.contract:
                raise InputError("product-contract profile requires --contract")
            validator = _load_product_contract_validator()
            try:
                product_contract = validator.load_contract(args.contract)
            except ValueError as error:
                raise InputError(str(error)) from error
            contract_hash = sha256_path(args.contract)
            static_errors = validator.validate_contract(product_contract)
            static_errors.extend(
                validator.validate_html(product_contract, html_path)
            )
            static_contract_report = validator.build_report(
                product_contract,
                static_errors,
                html_path,
            )
            if static_errors:
                report = {
                    "status": "failed",
                    "exit_code": EXIT_ARTIFACT_FAILED,
                    "profile": args.profile,
                    "browser_required": args.require_browser,
                    "execution": {"tier": args.tier, "portability": portability_enabled},
                    "browser": None,
                    "static_contract": static_contract_report,
                    "artifact": {"status": "failed"},
                }
                write_current_report(report)
                for error in static_errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return EXIT_ARTIFACT_FAILED

        if not args.check_env and args.experience_checks:
            validator = _load_experience_checks_validator()
            try:
                experience_checks = validator.load_checks(args.experience_checks)
            except ValueError as error:
                raise InputError(str(error)) from error
            experience_hash = sha256_path(args.experience_checks)
            static_experience_errors = validator.validate_checks(experience_checks)
            static_experience_errors.extend(
                validator.validate_html(experience_checks, html_path)
            )
            static_experience_report = validator.build_report(
                experience_checks,
                static_experience_errors,
                html_path,
            )
            if static_experience_errors:
                report = {
                    "status": "failed",
                    "exit_code": EXIT_ARTIFACT_FAILED,
                    "profile": args.profile,
                    "browser_required": args.require_browser,
                    "execution": {
                        "tier": args.tier,
                        "portability": portability_enabled,
                    },
                    "browser": None,
                    "static_contract": static_contract_report,
                    "static_experience": static_experience_report,
                    "artifact": {"status": "failed"},
                }
                write_current_report(report)
                for error in static_experience_errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return EXIT_ARTIFACT_FAILED

        if not args.check_env and args.guidance:
            validator = _load_design_guidance_validator()
            try:
                design_guidance = validator.load_guidance(args.guidance)
            except ValueError as error:
                raise InputError(str(error)) from error
            static_guidance_errors = validator.validate_guidance(design_guidance)
            static_guidance_report = validator.build_report(
                design_guidance,
                static_guidance_errors,
            )
            guidance_hash = sha256_path(args.guidance)
            if static_guidance_errors:
                report = {
                    "status": "failed",
                    "exit_code": EXIT_ARTIFACT_FAILED,
                    "profile": args.profile,
                    "browser_required": args.require_browser,
                    "execution": {"tier": args.tier, "portability": portability_enabled},
                    "browser": None,
                    "static_contract": static_contract_report,
                    "static_experience": static_experience_report,
                    "static_guidance": static_guidance_report,
                    "artifact": {"status": "failed"},
                }
                write_current_report(report)
                for error in static_guidance_errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return EXIT_ARTIFACT_FAILED

        if not args.check_env and args.design_reference:
            validator = _load_design_reference_validator()
            try:
                design_reference = validator.load_reference(args.design_reference)
            except ValueError as error:
                raise InputError(str(error)) from error
            static_design_reference_errors = validator.validate_reference(
                design_reference,
                args.design_reference,
                check_paths=True,
            )
            static_design_reference_errors.extend(
                validator.validate_html(design_reference, html_path)
            )
            if design_reference.get("acquisition", {}).get("status") != "complete":
                static_design_reference_errors.append(
                    "design reference acquisition must be complete before fidelity verification"
                )
            static_design_reference_report = validator.build_report(
                design_reference,
                static_design_reference_errors,
                args.design_reference,
            )
            design_reference_hash = sha256_path(args.design_reference)
            if static_design_reference_errors:
                report = {
                    "status": "failed",
                    "exit_code": EXIT_ARTIFACT_FAILED,
                    "profile": args.profile,
                    "browser_required": args.require_browser,
                    "execution": {"tier": args.tier, "portability": portability_enabled},
                    "browser": None,
                    "static_contract": static_contract_report,
                    "static_experience": static_experience_report,
                    "static_guidance": static_guidance_report,
                    "static_design_reference": static_design_reference_report,
                    "artifact": {"status": "failed"},
                }
                write_current_report(report)
                for error in static_design_reference_errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return EXIT_ARTIFACT_FAILED

        if not args.check_env and portability_enabled:
            validator = _load_portability_validator()
            try:
                portability_errors, static_portability_report = validator.validate_portability(
                    html_path,
                )
            except ValueError as error:
                raise InputError(str(error)) from error
            if portability_errors:
                report = {
                    "status": "failed",
                    "exit_code": EXIT_ARTIFACT_FAILED,
                    "profile": args.profile,
                    "browser_required": args.require_browser,
                    "execution": {"tier": args.tier, "portability": portability_enabled},
                    "browser": None,
                    "static_contract": static_contract_report,
                    "static_experience": static_experience_report,
                    "static_guidance": static_guidance_report,
                    "static_design_reference": static_design_reference_report,
                    "static_portability": static_portability_report,
                    "artifact": {"status": "failed"},
                }
                write_current_report(report)
                for error in portability_errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return EXIT_ARTIFACT_FAILED

        previous_artifact = (
            previous_report.get("artifact", {})
            if previous_report
            and isinstance(previous_report.get("artifact"), dict)
            else {}
        )
        previous_artifact_hash = previous_artifact.get("sha256")
        reusable_evidence = {
            "artifact": previous_artifact_hash == artifact_hash,
            "contract": bool(contract_hash)
            and previous_artifact.get("contractSha256") == contract_hash,
            "experience": bool(experience_hash)
            and previous_artifact.get("experienceChecksSha256")
            == experience_hash,
            "guidance": bool(guidance_hash)
            and previous_artifact.get("guidanceSha256") == guidance_hash,
            "designSystem": bool(design_system_hash)
            and previous_artifact.get("designSystemSha256")
            == design_system_hash,
            "designReference": bool(design_reference_hash)
            and previous_artifact.get("designReferenceSha256")
            == design_reference_hash,
        }
        execution = {
            "tier": args.tier,
            "changedAspects": changed_aspects,
            "targetSelectors": target_selectors,
            "actionIds": action_ids,
            "resultSelectors": result_selectors,
            "expectedCopy": expected_copies,
            "semanticImpact": args.semantic_impact,
            "viewports": viewports,
            "waitMs": wait,
            "launchTimeoutMs": args.launch_timeout_ms,
            "navigationTimeoutMs": args.navigation_timeout_ms,
            "wallTimeoutMs": wall_timeout_ms,
            "browserPolicy": browser_policy,
            "browserSession": {
                "policy": browser_session_policy,
                "status": "pending" if browser_session_policy != "off" else "off",
                "error": None,
            },
            "browserExecutable": (
                str(Path(args.browser_executable).expanduser())
                if args.browser_executable
                else None
            ),
            "previousReport": (
                {
                    "path": str(Path(args.previous_report).resolve()),
                    "artifactHash": previous_artifact_hash,
                    "eligibleForReuse": previous_artifact_hash == artifact_hash,
                    "reusableEvidence": reusable_evidence,
                }
                if previous_report
                else None
            ),
            "designReference": (
                str(Path(args.design_reference).resolve())
                if args.design_reference
                else None
            ),
            "experienceChecks": (
                str(Path(args.experience_checks).resolve())
                if args.experience_checks
                else None
            ),
            "visualDiff": (
                {
                    "channelThreshold": args.visual_diff_channel_threshold,
                    "maxMismatchRatio": args.visual_diff_max_mismatch_ratio,
                }
                if args.design_reference
                else None
            ),
            "portability": portability_enabled,
            "deliveryFormat": "project_bundle",
            "primaryShareArtifact": (
                Path(args.html_path).resolve().parent.name if args.html_path else None
            ),
            "entryHtml": (
                Path(args.html_path).resolve().name if args.html_path else None
            ),
        }

        if args.check_env:
            browser = (
                probe_func()
                if probe_func
                else probe_browser(
                    browser_candidates=browser_candidates,
                    launch_timeout_ms=args.launch_timeout_ms,
                )
            )
            report = {
                "status": "passed" if browser.get("available") else "degraded",
                "exit_code": (
                    EXIT_PASSED
                    if browser.get("available")
                    else EXIT_BROWSER_UNAVAILABLE
                ),
                "profile": args.profile,
                "browser_required": args.require_browser,
                "execution": execution,
                "browser": browser,
                "static_contract": None,
                "static_experience": None,
                "static_guidance": None,
                "static_design_reference": None,
                "static_portability": None,
                "artifact": None,
            }
            if browser.get("available"):
                report["timings"] = {
                    "total_ms": round(
                        (time.monotonic() - command_started) * 1000,
                        2,
                    )
                }
                print(f"浏览器环境可用: {browser.get('source', 'unknown')}")
                write_current_report(report)
                return EXIT_PASSED
            report["timings"] = {
                "total_ms": round(
                    (time.monotonic() - command_started) * 1000,
                    2,
                )
            }
            print("浏览器环境不可用；验证已降级，未执行安装或网络操作。")
            write_current_report(report)
            return EXIT_BROWSER_UNAVAILABLE

        if args.tier == "tier_0_text_copy_only":
            emoji_findings = find_unapproved_emoji(html_path)
            missing_copies = validate_expected_copy(html_path, expected_copies)
            code = (
                EXIT_ARTIFACT_FAILED
                if emoji_findings or missing_copies
                else EXIT_PASSED
            )
            report = {
                "status": (
                    "failed" if emoji_findings or missing_copies else "passed"
                ),
                "exit_code": code,
                "profile": args.profile,
                "browser_required": args.require_browser,
                "execution": execution,
                "browser": None,
                "static_contract": static_contract_report,
                "static_experience": static_experience_report,
                "static_guidance": static_guidance_report,
                "static_design_reference": static_design_reference_report,
                "static_portability": static_portability_report,
                "artifact": {
                    "status": (
                        "failed"
                        if emoji_findings or missing_copies
                        else "passed"
                    ),
                    "sha256": artifact_hash,
                    "contractSha256": contract_hash,
                    "experienceChecksSha256": experience_hash,
                    "guidanceSha256": guidance_hash,
                    "designSystemSha256": design_system_hash,
                    "designReferenceSha256": design_reference_hash,
                    "checks": [
                        "static-artifact-scan",
                        "unauthorized-emoji",
                        *(["expected-copy"] if expected_copies else []),
                        *(
                            ["product-contract-static"]
                            if args.profile == "product-contract"
                            else []
                        ),
                    ],
                    "emojiFindings": len(emoji_findings),
                    "missingExpectedCopy": missing_copies,
                },
                "timings": {
                    "static_ms": round(
                        (time.monotonic() - command_started) * 1000,
                        2,
                    ),
                    "total_ms": round(
                        (time.monotonic() - command_started) * 1000,
                        2,
                    )
                },
            }
            write_current_report(report)
            return code

        browser_endpoint = None
        if verify_func is verify_html:
            warm_state, warm_report = resolve_browser_session(
                browser_session_policy,
                browser_executable=args.browser_executable,
                idle_timeout_seconds=args.browser_session_idle_timeout_seconds,
                launch_timeout_ms=args.launch_timeout_ms,
            )
            execution["browserSession"] = warm_report
            if warm_state:
                browser_endpoint = (
                    warm_state.get("webSocketUrl")
                    or warm_state.get("endpointUrl")
                )
        elif browser_session_policy != "off":
            execution["browserSession"] = {
                "policy": browser_session_policy,
                "status": "not_run_by_injected_verifier",
                "error": None,
            }

        browser = (probe_func or (lambda: None))()
        report = {
            "status": "passed",
            "exit_code": EXIT_PASSED,
            "profile": args.profile,
            "browser_required": args.require_browser,
            "execution": execution,
            "browser": browser,
            "static_contract": static_contract_report,
            "static_experience": static_experience_report,
            "static_guidance": static_guidance_report,
            "static_design_reference": static_design_reference_report,
            "static_portability": static_portability_report,
            "artifact": None,
        }

        if browser is not None and not browser.get("available"):
            print("浏览器环境不可用；验证已降级，未执行安装或网络操作。")
            report.update(
                status="degraded",
                exit_code=EXIT_BROWSER_UNAVAILABLE,
                timings={
                    "total_ms": round(
                        (time.monotonic() - command_started) * 1000,
                        2,
                    )
                },
            )
            write_current_report(report)
            return EXIT_BROWSER_UNAVAILABLE

        try:
            artifact_details = {}
            verify_kwargs = dict(
                html_path=args.html_path,
                viewports=viewports,
                slides=args.slides,
                output_dir=args.output,
                show=args.show,
                wait=wait,
                launch_options=(
                    browser.get("launch_options")
                    if browser is not None
                    else None
                ),
                launch_timeout_ms=args.launch_timeout_ms,
                profile=args.profile,
                product_contract=product_contract,
                experience_checks=experience_checks,
                design_guidance=design_guidance,
                design_reference=design_reference,
                design_reference_path=args.design_reference,
                visual_diff_channel_threshold=args.visual_diff_channel_threshold,
                visual_diff_max_mismatch_ratio=args.visual_diff_max_mismatch_ratio,
                portability=portability_enabled,
                artifact_details=artifact_details,
                tier=args.tier,
                changed_aspects=changed_aspects,
                ready_selector=args.ready_selector,
                browser_candidates=browser_candidates,
                target_selectors=target_selectors,
                action_ids=action_ids,
                result_selectors=result_selectors,
                browser_policy=browser_policy,
                browser_endpoint=browser_endpoint,
                navigation_timeout_ms=args.navigation_timeout_ms,
            )
            static_ms = round(
                (time.monotonic() - command_started) * 1000,
                2,
            )
            if verify_func is verify_html and wall_timeout_ms:
                verify_kwargs.pop("artifact_details")
                code, artifact_details = run_verification_with_deadline(
                    verify_kwargs,
                    wall_timeout_ms,
                )
            else:
                code = verify_func(**verify_kwargs)
        except BrowserUnavailable as error:
            report.update(
                status="degraded",
                exit_code=EXIT_BROWSER_UNAVAILABLE,
                browser=error.details,
                artifact={"status": "not_run", "reason": str(error)},
                timings={
                    "total_ms": round(
                        (time.monotonic() - command_started) * 1000,
                        2,
                    )
                },
            )
            write_current_report(report)
            return EXIT_BROWSER_UNAVAILABLE
        except VerificationTimeout as error:
            report.update(
                status="degraded",
                exit_code=EXIT_BROWSER_UNAVAILABLE,
                browser={
                    "available": False,
                    "status": "degraded",
                    "source": None,
                    "attempts": [
                        {"source": "wall-timeout", "error": str(error)}
                    ],
                },
                artifact={"status": "not_run", "reason": str(error)},
                timings={
                    "static_ms": static_ms,
                    "total_ms": round(
                        (time.monotonic() - command_started) * 1000,
                        2,
                    ),
                },
            )
            write_current_report(report)
            return EXIT_BROWSER_UNAVAILABLE
        except InputError:
            raise
        except Exception as error:
            raise InputError(f"验证脚本错误: {error}") from error

        code = EXIT_PASSED if code == EXIT_PASSED else EXIT_ARTIFACT_FAILED
        browser_details = artifact_details.pop("browser", None)
        browser_timings = artifact_details.get("timings", {})
        if browser_details:
            report["browser"] = browser_details
        report.update(
            status="passed" if code == EXIT_PASSED else "failed",
            exit_code=code,
            artifact={
                "status": "passed" if code == EXIT_PASSED else "failed",
                "sha256": artifact_hash,
                "contractSha256": contract_hash,
                "experienceChecksSha256": experience_hash,
                "guidanceSha256": guidance_hash,
                "designSystemSha256": design_system_hash,
                "designReferenceSha256": design_reference_hash,
                **artifact_details,
            },
            timings={
                "static_ms": static_ms,
                **browser_timings,
                "total_ms": round(
                    (time.monotonic() - command_started) * 1000,
                    2,
                )
            },
        )
        write_current_report(report)
        return code
    except InputError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        report = _error_report(locals().get("args"), str(error))
        try:
            _write_report(report_path, report)
        except InputError as report_error:
            print(f"ERROR: {report_error}", file=sys.stderr)
        return EXIT_INPUT_ERROR


if __name__ == "__main__":
    sys.exit(main())
