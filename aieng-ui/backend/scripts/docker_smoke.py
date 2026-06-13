"""Docker all-in-one smoke test.

Assumes the container is already running with backend on port 8000 and MCP HTTP
server on port 8765. Exits non-zero if any check fails.
"""

from __future__ import annotations

import asyncio
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable

# Canonical MCP-facing tool names (runtime registers dotted names; the MCP
# server exposes them with dots replaced by underscores).
_CANONICAL_MCP_TOOLS = (
    "aieng_agent_readme",
    "aieng_list_projects",
    "cad_execute_build123d",
    "cae_prepare_solver_run",
)


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


def _retry_until(
    operation,
    *,
    timeout: float = 60.0,
    interval: float = 2.0,
    description: str = "endpoint",
) -> Any:
    """Call ``operation()`` until it returns without raising, or timeout expires.

    ``operation`` must raise an exception on non-success; the exception message
    becomes ``last_error`` in the final ``RuntimeError``.
    """
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(interval)
    raise RuntimeError(
        f"{description} did not become ready in {timeout}s: {last_error}"
    )


def _wait_for_health(
    base: str,
    timeout: float = 60.0,
    interval: float = 2.0,
    attempt_timeout: float = 5.0,
) -> dict[str, Any]:
    import json

    def _check() -> dict[str, Any]:
        status, _, body = _request(
            f"{base}/api/health", timeout=attempt_timeout
        )
        if status != 200:
            raise ConnectionError(f"status {status}")
        return json.loads(body)

    return _retry_until(
        _check,
        timeout=timeout,
        interval=interval,
        description="health endpoint",
    )


def _wait_for_stream(
    url: str,
    *,
    timeout: float = 60.0,
    interval: float = 2.0,
    attempt_timeout: float = 5.0,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str]]:
    def _check() -> tuple[int, dict[str, str]]:
        status, response_headers = _open_stream(
            url, timeout=attempt_timeout, headers=headers
        )
        if status != 200:
            raise ConnectionError(f"status {status}")
        return status, response_headers

    return _retry_until(
        _check,
        timeout=timeout,
        interval=interval,
        description="stream endpoint",
    )


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


def _result_text(result: Any) -> str:
    """Flatten an MCP call_tool result to searchable text."""
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        parts.append(repr(structured))
    if not parts:
        parts.append(repr(result))
    return "\n".join(parts)


async def _mcp_protocol_checks(mcp_base: str) -> tuple[bool, str]:
    """Real MCP handshake over the container SSE endpoint.

    Proves the server is *usable* (not just that /sse is reachable):
    initialize + tools/list + canonical tools + a read-only call + the
    managed-approval fail-safe. Returns (ok, category) so the caller can emit a
    failure message that distinguishes protocol / missing-tools / read-only /
    approval-surface failures.
    """
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client
    except Exception as exc:  # noqa: BLE001
        print(f"[docker-smoke] FAIL: mcp client library not installed: {exc}", file=sys.stderr)
        return False, "setup"

    sse_url = f"{mcp_base}/sse"
    # The /sse reachability was already retried in main(); a couple of connect
    # retries here cover the brief window before the session endpoint is ready.
    last_error = ""
    for attempt in range(5):
        try:
            async with sse_client(sse_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=30)
                    print("[docker-smoke] MCP initialize OK")

                    listed = await asyncio.wait_for(session.list_tools(), timeout=30)
                    names = {tool.name for tool in listed.tools}
                    print(f"[docker-smoke] MCP tools/list returned {len(names)} tools")
                    missing = [t for t in _CANONICAL_MCP_TOOLS if t not in names]
                    if missing:
                        print(
                            f"[docker-smoke] FAIL: tools/list missing canonical tools: {missing}",
                            file=sys.stderr,
                        )
                        return False, "missing_tools"

                    # Read-only call must succeed and return content.
                    readme = await asyncio.wait_for(
                        session.call_tool("aieng_agent_readme", {}), timeout=30
                    )
                    if getattr(readme, "isError", False) or not _result_text(readme).strip():
                        print(
                            "[docker-smoke] FAIL: read-only aieng_agent_readme returned no content",
                            file=sys.stderr,
                        )
                        return False, "read_only"
                    print("[docker-smoke] MCP read-only call OK")

                    # Managed-approval fail-safe: with no viewer connected, a
                    # gated call must fail safe rather than execute or stall.
                    # Clear the cae guide gate first so the approval gate is what
                    # we actually exercise.
                    await asyncio.wait_for(
                        session.call_tool("aieng_guide", {"topic": "cae"}), timeout=30
                    )
                    gated = await asyncio.wait_for(
                        session.call_tool(
                            "cae_run_solver", {"project_id": "docker-smoke-no-such-project"}
                        ),
                        timeout=30,
                    )
                    gated_text = _result_text(gated)
                    if "approval_surface_unavailable" not in gated_text:
                        print(
                            "[docker-smoke] FAIL: gated cae_run_solver did not fail safe with "
                            f"approval_surface_unavailable. Got: {gated_text[:500]}",
                            file=sys.stderr,
                        )
                        return False, "approval_surface"
                    print("[docker-smoke] MCP managed-approval fail-safe OK")
                    return True, "ok"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(2)
    print(
        f"[docker-smoke] FAIL: MCP protocol handshake failed: {last_error}",
        file=sys.stderr,
    )
    return False, "protocol"


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

    print("[docker-smoke] Running MCP protocol handshake over the container endpoint ...")
    ok, _category = asyncio.run(_mcp_protocol_checks(mcp_base))
    if not ok:
        return 1
    print("[docker-smoke] MCP protocol checks OK")

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


def persist_create(backend_base: str = "http://127.0.0.1:8000") -> int:
    """Create a project and print its bare id to stdout (logs to stderr).

    Used by the restart-persistence smoke: the workflow captures the id, restarts
    the container against the same mounted /data volume, then calls
    ``persist-verify`` to prove the project survived. stdout carries ONLY the id
    so it can be captured with ``$(...)``.
    """
    import json

    payload = json.dumps({"name": "docker-restart-persistence"}).encode()

    def _created(_s: int, _h: dict[str, str], body: bytes) -> bool:
        try:
            return isinstance(json.loads(body).get("id"), (str, int))
        except json.JSONDecodeError:
            return False

    print("[docker-smoke] persist: waiting for backend health ...", file=sys.stderr)
    _wait_for_health(backend_base)
    print("[docker-smoke] persist: creating project ...", file=sys.stderr)
    try:
        _, _, body = _wait_for_request(
            f"{backend_base}/api/projects",
            timeout=60.0,
            interval=2.0,
            headers={"Content-Type": "application/json"},
            data=payload,
            method="POST",
            validate=_created,
        )
    except RuntimeError as exc:
        print(f"[docker-smoke] FAIL: persist create did not become ready: {exc}", file=sys.stderr)
        return 1
    project_id = json.loads(body).get("id")
    print(f"[docker-smoke] persist: created project {project_id}", file=sys.stderr)
    print(project_id)  # bare id on stdout for the workflow to capture
    return 0


def persist_verify(project_id: str, backend_base: str = "http://127.0.0.1:8000") -> int:
    """Read ``project_id`` back after a container restart; assert it survived."""
    import json

    if not project_id:
        print("[docker-smoke] FAIL: persist-verify requires a project id", file=sys.stderr)
        return 1

    print(f"[docker-smoke] persist: waiting for backend health after restart ...", file=sys.stderr)
    _wait_for_health(backend_base)

    def _matches(status: int, _h: dict[str, str], body: bytes) -> bool:
        if status != 200:
            return False
        try:
            return str(json.loads(body).get("id")) == str(project_id)
        except json.JSONDecodeError:
            return False

    print(f"[docker-smoke] persist: reading project {project_id} back after restart ...", file=sys.stderr)
    try:
        _wait_for_request(
            f"{backend_base}/api/projects/{project_id}",
            timeout=60.0,
            interval=2.0,
            expected_status=200,
            validate=_matches,
        )
    except RuntimeError as exc:
        print(
            f"[docker-smoke] FAIL: project {project_id} did not survive restart: {exc}",
            file=sys.stderr,
        )
        return 1
    print(f"[docker-smoke] persist: project {project_id} survived restart OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Docker all-in-one smoke test")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("all", help="Full smoke (default if no subcommand)")
    sub.add_parser("persist-create", help="Create a project; print its id to stdout")
    verify = sub.add_parser("persist-verify", help="Verify a project id reads back after restart")
    verify.add_argument("--project-id", required=True)
    args = parser.parse_args()

    if args.command == "persist-create":
        raise SystemExit(persist_create())
    if args.command == "persist-verify":
        raise SystemExit(persist_verify(args.project_id))
    raise SystemExit(main())
