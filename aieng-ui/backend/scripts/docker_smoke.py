"""Docker all-in-one smoke test.

Assumes the container is already running with backend on port 8000 and MCP HTTP
server on port 8765. Exits non-zero if any check fails.
"""

from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _request(url: str, *, timeout: float = 10.0, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, headers=headers or {})
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


def main() -> int:
    backend_base = "http://127.0.0.1:8000"
    mcp_base = "http://127.0.0.1:8765"

    print("[docker-smoke] Waiting for backend health...")
    health = _wait_for_health(backend_base)
    print(f"[docker-smoke] Health OK: {health}")

    print("[docker-smoke] Checking viewer /app/ ...")
    status, headers, body = _request(f"{backend_base}/app/", timeout=10.0)
    if status != 200:
        print(f"[docker-smoke] FAIL: viewer returned {status}", file=sys.stderr)
        return 1
    content_type = headers.get("Content-Type", "")
    if "text/html" not in content_type:
        print(f"[docker-smoke] FAIL: viewer content-type is {content_type}, expected text/html", file=sys.stderr)
        return 1
    print("[docker-smoke] Viewer OK")

    print("[docker-smoke] Checking MCP SSE endpoint ...")
    status, headers = _open_stream(
        f"{mcp_base}/sse",
        timeout=10.0,
        headers={"Accept": "text/event-stream"},
    )
    if status != 200:
        print(f"[docker-smoke] FAIL: MCP SSE returned {status}", file=sys.stderr)
        return 1
    content_type = headers.get("Content-Type", "")
    if "text/event-stream" not in content_type:
        print(f"[docker-smoke] WARN: MCP SSE content-type is {content_type}, expected text/event-stream")
    print("[docker-smoke] MCP SSE OK")

    print("[docker-smoke] Creating project via backend API ...")
    import json
    req = urllib.request.Request(
        f"{backend_base}/api/projects",
        data=json.dumps({"name": "docker-smoke"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            project = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        print(f"[docker-smoke] FAIL: create project returned {exc.code}", file=sys.stderr)
        return 1
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
