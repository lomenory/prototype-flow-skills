#!/usr/bin/env python3
"""Manage a bounded local Chrome CDP session for repeated demo verification."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


DEFAULT_IDLE_TIMEOUT_SECONDS = 15 * 60
DEFAULT_LAUNCH_TIMEOUT_MS = 10000


def default_state_dir() -> Path:
    user_id = getattr(os, "getuid", lambda: 0)()
    return Path(tempfile.gettempdir()) / f"demo-design-browser-session-{user_id}"


def ensure_private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def state_path(state_dir: str | Path | None = None) -> Path:
    return Path(state_dir) / "state.json" if state_dir else default_state_dir() / "state.json"


def _write_state(directory: Path, state: dict[str, Any]) -> None:
    ensure_private_directory(directory)
    temporary = directory / f"state-{os.getpid()}.tmp"
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(directory / "state.json")


def load_state(state_dir: str | Path | None = None) -> dict[str, Any] | None:
    path = state_path(state_dir)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def process_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    return True


def probe_endpoint(endpoint_url: str, timeout_seconds: float = 0.25) -> dict[str, Any] | None:
    try:
        with urlopen(
            endpoint_url.rstrip("/") + "/json/version",
            timeout=timeout_seconds,
        ) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(value, dict) or not value.get("webSocketDebuggerUrl"):
        return None
    return value


def active_session(state_dir: str | Path | None = None) -> dict[str, Any] | None:
    state = load_state(state_dir)
    if not state or state.get("status") != "ready":
        return None
    if not process_alive(state.get("managerPid")) or not process_alive(state.get("browserPid")):
        return None
    endpoint = state.get("endpointUrl")
    if not isinstance(endpoint, str) or not probe_endpoint(endpoint):
        return None
    return state


def touch_session(state_dir: str | Path | None = None) -> dict[str, Any] | None:
    state = active_session(state_dir)
    if not state:
        return None
    state["lastUsedAt"] = time.time()
    _write_state(state_path(state_dir).parent, state)
    return state


def default_browser_executable() -> Path | None:
    candidates = (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        os.path.expandvars(r"$PROGRAMFILES\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"$PROGRAMFILES\Chromium\Application\chrome.exe"),
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    )
    for raw in candidates:
        candidate = Path(raw)
        if raw and candidate.is_file():
            return candidate
    return None


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _terminate_process(process: subprocess.Popen[Any], timeout_seconds: float = 3.0) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)


def serve_session(
    executable: Path,
    directory: Path,
    idle_timeout_seconds: int,
    launch_timeout_ms: int,
) -> int:
    ensure_private_directory(directory)
    port = _free_local_port()
    endpoint_url = f"http://127.0.0.1:{port}"
    profile = directory / f"profile-{os.getpid()}"
    profile.mkdir(mode=0o700)
    log_path = directory / "chrome.log"
    stopping = False

    def request_stop(_signum=None, _frame=None):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    command = [
        str(executable),
        "--headless=new",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-default-browser-check",
        "--no-first-run",
        "--no-sandbox",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "about:blank",
    ]
    browser = None
    try:
        with log_path.open("ab") as log:
            browser = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        deadline = time.monotonic() + launch_timeout_ms / 1000
        while time.monotonic() < deadline and browser.poll() is None:
            endpoint_metadata = probe_endpoint(endpoint_url)
            if endpoint_metadata:
                now = time.time()
                _write_state(
                    directory,
                    state := {
                        "schemaVersion": 1,
                        "status": "ready",
                        "managerPid": os.getpid(),
                        "browserPid": browser.pid,
                        "endpointUrl": endpoint_url,
                        "webSocketUrl": endpoint_metadata["webSocketDebuggerUrl"],
                        "browserExecutable": str(executable),
                        "profilePath": str(profile),
                        "startedAt": now,
                        "lastUsedAt": now,
                        "idleTimeoutSeconds": idle_timeout_seconds,
                    },
                )
                print(json.dumps(state, ensure_ascii=False), flush=True)
                break
            time.sleep(0.05)
        else:
            return 1

        while not stopping and browser.poll() is None:
            state = load_state(directory)
            last_used = state.get("lastUsedAt", 0) if state else 0
            if time.time() - float(last_used) >= idle_timeout_seconds:
                break
            time.sleep(0.5)
        return 0
    finally:
        if browser is not None:
            _terminate_process(browser)
        current = load_state(directory)
        if current and current.get("managerPid") == os.getpid():
            try:
                (directory / "state.json").unlink()
            except FileNotFoundError:
                pass
        shutil.rmtree(profile, ignore_errors=True)


def start_session(
    *,
    executable: str | Path | None = None,
    state_dir: str | Path | None = None,
    idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
    launch_timeout_ms: int = DEFAULT_LAUNCH_TIMEOUT_MS,
) -> dict[str, Any]:
    if active := touch_session(state_dir):
        return active
    browser = Path(executable) if executable else default_browser_executable()
    if browser is None or not browser.is_file():
        raise RuntimeError("no supported local Chrome/Chromium executable was found")
    directory = ensure_private_directory(state_path(state_dir).parent)
    try:
        (directory / "state.json").unlink()
    except FileNotFoundError:
        pass
    manager_log = (directory / "manager.log").open("ab")
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "serve",
            "--browser-executable",
            str(browser),
            "--state-dir",
            str(directory),
            "--idle-timeout-seconds",
            str(idle_timeout_seconds),
            "--launch-timeout-ms",
            str(launch_timeout_ms),
        ],
        stdin=subprocess.DEVNULL,
        stdout=manager_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    manager_log.close()
    deadline = time.monotonic() + launch_timeout_ms / 1000 + 1
    while time.monotonic() < deadline:
        if active := active_session(directory):
            return active
        if process.poll() is not None:
            break
        time.sleep(0.05)
    if process.poll() is None:
        process.terminate()
    raise RuntimeError(f"warm browser session did not become ready; see {directory / 'manager.log'}")


def stop_session(state_dir: str | Path | None = None, timeout_seconds: float = 5.0) -> bool:
    state = active_session(state_dir)
    if not state:
        try:
            state_path(state_dir).unlink()
        except FileNotFoundError:
            pass
        return False
    manager_pid = state.get("managerPid")
    os.kill(manager_pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline and process_alive(manager_pid):
        time.sleep(0.05)
    if process_alive(manager_pid):
        raise RuntimeError("warm browser session did not stop within the deadline")
    try:
        state_path(state_dir).unlink()
    except FileNotFoundError:
        pass
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage a warm Chrome session for demo verification")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("start", "status", "stop"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--state-dir", type=Path)
        if command == "start":
            subparser.add_argument("--browser-executable", type=Path)
            subparser.add_argument(
                "--idle-timeout-seconds",
                type=int,
                default=DEFAULT_IDLE_TIMEOUT_SECONDS,
            )
            subparser.add_argument(
                "--launch-timeout-ms",
                type=int,
                default=DEFAULT_LAUNCH_TIMEOUT_MS,
            )
    serve = subparsers.add_parser("serve")
    serve.add_argument("--browser-executable", type=Path)
    serve.add_argument("--state-dir", type=Path)
    serve.add_argument(
        "--idle-timeout-seconds",
        type=int,
        default=DEFAULT_IDLE_TIMEOUT_SECONDS,
    )
    serve.add_argument(
        "--launch-timeout-ms",
        type=int,
        default=DEFAULT_LAUNCH_TIMEOUT_MS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        executable = args.browser_executable or default_browser_executable()
        if executable is None:
            print("ERROR: no supported local Chrome/Chromium executable was found", file=sys.stderr)
            return 1
        directory = state_path(args.state_dir).parent
        if active := touch_session(directory):
            print(json.dumps(active, ensure_ascii=False))
            print("ERROR: a warm browser session is already running", file=sys.stderr)
            return 2
        return serve_session(
            executable,
            directory,
            args.idle_timeout_seconds,
            args.launch_timeout_ms,
        )
    if args.command == "start":
        try:
            state = start_session(
                executable=args.browser_executable,
                state_dir=args.state_dir,
                idle_timeout_seconds=args.idle_timeout_seconds,
                launch_timeout_ms=args.launch_timeout_ms,
            )
        except RuntimeError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(json.dumps(state, ensure_ascii=False))
        return 0
    if args.command == "status":
        state = active_session(args.state_dir)
        print(json.dumps(state or {"status": "stopped"}, ensure_ascii=False))
        return 0 if state else 1
    try:
        stopped = stop_session(args.state_dir)
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("stopped" if stopped else "already stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
