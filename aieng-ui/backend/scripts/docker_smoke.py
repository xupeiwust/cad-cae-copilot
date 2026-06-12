"""Docker all-in-one smoke test.

Assumes the container is already running with backend on port 8000 and MCP HTTP
server on port 8765. Exits non-zero if any check fails.
"""

from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable


def _request(
    url: str,
    *,
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    method: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, headers=headers or {}, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def _open_stream(url: str, *, timeout: float = 10.0, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str]]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers)


def _header(headers: dict[str, str], name: str) -> str:
    """Return a response header case-insensitively.

    GitHub's Linux runner has observed uvicorn/static-file responses arriving as
    lower-case keys after ``dict(resp.headers)`` conversion, while local runs may
    preserve title-case. HTTP header names are case-insensitive, so the smoke
    check must be too.
    """

    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return ""


def _body_looks_like_html(body: bytes) -> bool:
    prefix = body[:256].lstrip().lower()
    return prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html")


def _wait_for_health(base: str, timeout: float = 60.0, interval: float = 2.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            status, _, body = _request(f"{base}/api/health", timeout=5.0)
            if status == 200:
                import json
                return json.loads(body)
            last_error = f"status {status}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(interval)
    raise RuntimeError(f"health endpoint did not become ready in {timeout}s: {last_error}")


def _wait_for_stream(
    url: str,
    *,
    timeout: float = 60.0,
    interval: float = 2.0,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str]]:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            status, response_headers = _open_stream(url, timeout=5.0, headers=headers)
            if status == 200:
                return status, response_headers
            last_error = f"status {status}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(interval)
    raise RuntimeError(f"stream endpoint did not become ready in {timeout}s: {last_error}")


def _wait_for_request(
    url: str,
    *,
    timeout: float = 60.0,
    interval: float = 2.0,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    method: str | None = None,
    expected_status: int = 200,
    validate: Callable[[int, dict[str, str], bytes], bool] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Retry a request until it succeeds and optionally passes validation.

    Retries on transient errors such as ``ConnectionResetError`` while the
    container is still binding its ports, matching the behaviour of
    ``_wait_for_health`` and ``_wait_for_stream``.
    """
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            status, response_headers, body = _request(
                url, timeout=5.0, headers=headers, data=data, method=method
            )
            if status == expected_status:
                if validate is None or validate(status, response_headers, body):
                    return status, response_headers, body
                last_error = "validation failed"
            else:
                last_error = f"status {status}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(interval)
    raise RuntimeError(f"request did not become ready in {timeout}s: {last_error}")


def main() -> int:
    backend_base = "http://127.0.0.1:8000"
    mcp_base = "http://127.0.0.1:8765"

    print("[docker-smoke] Waiting for backend health...")
    health = _wait_for_health(backend_base)
    print(f"[docker-smoke] Health OK: {health}")

    print("[docker-smoke] Checking viewer /app/ ...")

    def _viewer_looks_ok(_status: int, headers: dict[str, str], body: bytes) -> bool:
        content_type = _header(headers, "Content-Type")
        return "text/html" in content_type.lower() or _body_looks_like_html(body)

    try:
        _wait_for_request(
            f"{backend_base}/app/",
            timeout=60.0,
            interval=2.0,
            validate=_viewer_looks_ok,
        )
    except RuntimeError as exc:
        print(f"[docker-smoke] FAIL: viewer did not become ready: {exc}", file=sys.stderr)
        return 1
    print("[docker-smoke] Viewer OK")

    print("[docker-smoke] Checking MCP SSE endpoint ...")
    try:
        status, headers = _wait_for_stream(
            f"{mcp_base}/sse",
            timeout=60.0,
            headers={"Accept": "text/event-stream"},
        )
    except RuntimeError as exc:
        print(f"[docker-smoke] FAIL: MCP SSE endpoint not ready: {exc}", file=sys.stderr)
        return 1
    content_type = _header(headers, "Content-Type")
    if "text/event-stream" not in content_type.lower():
        print(f"[docker-smoke] WARN: MCP SSE content-type is {content_type}, expected text/event-stream")
    print("[docker-smoke] MCP SSE OK")

    print("[docker-smoke] Creating project via backend API ...")
    import json
    project_payload = json.dumps({"name": "docker-smoke"}).encode()

    def _project_created(_status: int, _headers: dict[str, str], body: bytes) -> bool:
        try:
            project = json.loads(body)
        except json.JSONDecodeError:
            return False
        return isinstance(project.get("id"), (str, int))

    try:
        _, _, body = _wait_for_request(
            f"{backend_base}/api/projects",
            timeout=60.0,
            interval=2.0,
            headers={"Content-Type": "application/json"},
            data=project_payload,
            method="POST",
            validate=_project_created,
        )
    except RuntimeError as exc:
        print(f"[docker-smoke] FAIL: create project did not become ready: {exc}", file=sys.stderr)
        return 1
    project = json.loads(body)
    project_id = project.get("id")
    print(f"[docker-smoke] Created project {project_id}")

    print("[docker-smoke] Reading project back ...")
    status, _, body = _request(f"{backend_base}/api/projects/{project_id}", timeout=10.0)
    if status != 200:
        print(f"[docker-smoke] FAIL: read project returned {status}", file=sys.stderr)
        return 1
    print("[docker-smoke] Project read OK")

    print("[docker-smoke] All checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
