#!/usr/bin/env python3
"""Serve a local demo over bounded loopback HTTP for Codex Browser use."""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit


LOOPBACK_HOST = "127.0.0.1"


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_root(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"preview root is not a directory: {value}")
    return root


def resolve_entry(root: Path, value: str | Path) -> tuple[Path, str]:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("preview entry must be a safe path relative to --root")
    entry = (root / relative).resolve()
    if not _is_within(entry, root):
        raise ValueError("preview entry resolves outside --root")
    if not entry.is_file():
        raise ValueError(f"preview entry is not a file: {value}")
    return entry, entry.relative_to(root).as_posix()


class LoopbackPreviewHandler(SimpleHTTPRequestHandler):
    """Static handler that refuses paths resolving outside the selected root."""

    server_version = "DemoDesignPreview/1"

    def __init__(self, *args, directory: str, **kwargs):
        self.preview_root = Path(directory).resolve()
        super().__init__(*args, directory=directory, **kwargs)

    def translate_path(self, path: str) -> str:
        request_path = unquote(urlsplit(path).path, errors="surrogatepass")
        normalized = posixpath.normpath(request_path)
        parts = [part for part in normalized.split("/") if part not in ("", ".", "..")]
        candidate = self.preview_root.joinpath(*parts).resolve()
        if not _is_within(candidate, self.preview_root):
            return str(self.preview_root / ".demo-design-blocked-path")
        return str(candidate)

    def log_message(self, format: str, *args) -> None:
        print(
            f"preview-server: {self.address_string()} - {format % args}",
            file=sys.stderr,
        )


class LoopbackPreviewServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(root: Path, entry_relative: str, port: int) -> int:
    handler = partial(LoopbackPreviewHandler, directory=str(root))
    server = LoopbackPreviewServer((LOOPBACK_HOST, port), handler)
    selected_port = int(server.server_address[1])
    origin = f"http://{LOOPBACK_HOST}:{selected_port}"
    entry_url = f"{origin}/{quote(entry_relative, safe='/')}"
    payload = {
        "status": "ready",
        "origin": origin,
        "url": entry_url,
        "host": LOOPBACK_HOST,
        "port": selected_port,
        "root": str(root),
        "entry": entry_relative,
        "pid": os.getpid(),
    }
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serve one local demo root over loopback HTTP for Browser verification",
    )
    parser.add_argument("--root", required=True, help="directory containing the demo")
    parser.add_argument("--entry", required=True, help="HTML path relative to --root")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="loopback port; 0 selects an available port",
    )
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    try:
        root = resolve_root(args.root)
        _, entry_relative = resolve_entry(root, args.entry)
    except ValueError as error:
        parser.error(str(error))
    try:
        return serve(root, entry_relative, args.port)
    except OSError as error:
        parser.error(f"could not start loopback preview server: {error}")


if __name__ == "__main__":
    raise SystemExit(main())
