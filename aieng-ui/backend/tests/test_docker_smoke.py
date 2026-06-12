"""Unit coverage for the Docker smoke helper script."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_docker_smoke_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "docker_smoke.py"
    spec = importlib.util.spec_from_file_location("docker_smoke", script)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_header_lookup_is_case_insensitive() -> None:
    docker_smoke = _load_docker_smoke_module()

    assert docker_smoke._header({"content-type": "text/html; charset=utf-8"}, "Content-Type") == "text/html; charset=utf-8"
    assert docker_smoke._header({"Content-Type": "text/event-stream"}, "content-type") == "text/event-stream"
    assert docker_smoke._header({"x-other": "value"}, "Content-Type") == ""


def test_body_looks_like_html_accepts_static_index_variants() -> None:
    docker_smoke = _load_docker_smoke_module()

    assert docker_smoke._body_looks_like_html(b"<!doctype html><html></html>")
    assert docker_smoke._body_looks_like_html(b" \n<HTML><body></body></HTML>")
    assert not docker_smoke._body_looks_like_html(b'{"status":"ok"}')


def test_wait_for_stream_retries_until_ready(monkeypatch) -> None:
    docker_smoke = _load_docker_smoke_module()
    attempts = {"count": 0}

    def fake_open_stream(url: str, *, timeout: float, headers: dict[str, str] | None):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionResetError("connection reset by peer")
        return 200, {"content-type": "text/event-stream"}

    monkeypatch.setattr(docker_smoke, "_open_stream", fake_open_stream)
    monkeypatch.setattr(docker_smoke.time, "sleep", lambda _seconds: None)

    status, headers = docker_smoke._wait_for_stream(
        "http://127.0.0.1:8765/sse",
        timeout=1.0,
        interval=0.01,
        headers={"Accept": "text/event-stream"},
    )

    assert status == 200
    assert headers["content-type"] == "text/event-stream"
    assert attempts["count"] == 3


def test_wait_for_request_retries_through_connection_reset(monkeypatch) -> None:
    docker_smoke = _load_docker_smoke_module()
    attempts = {"count": 0}

    def fake_request(*_args, **_kwargs):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionResetError("connection reset by peer")
        return 200, {"content-type": "text/html"}, b"<!doctype html><html></html>"

    monkeypatch.setattr(docker_smoke, "_request", fake_request)
    monkeypatch.setattr(docker_smoke.time, "sleep", lambda _seconds: None)

    status, headers, body = docker_smoke._wait_for_request(
        "http://127.0.0.1:8000/app/",
        timeout=1.0,
        interval=0.01,
        validate=lambda _status, _hdrs, bdy: docker_smoke._body_looks_like_html(bdy),
    )

    assert status == 200
    assert headers["content-type"] == "text/html"
    assert b"<!doctype html" in body
    assert attempts["count"] == 3


def test_wait_for_request_retries_project_create_until_json_id(monkeypatch) -> None:
    docker_smoke = _load_docker_smoke_module()
    attempts = {"count": 0}

    def fake_request(*_args, **_kwargs):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionResetError("connection reset by peer")
        return 200, {"content-type": "application/json"}, b'{"id": "proj-123"}'

    monkeypatch.setattr(docker_smoke, "_request", fake_request)
    monkeypatch.setattr(docker_smoke.time, "sleep", lambda _seconds: None)

    import json

    def _project_created(_status: int, _headers: dict[str, str], body: bytes) -> bool:
        try:
            project = json.loads(body)
        except json.JSONDecodeError:
            return False
        return isinstance(project.get("id"), (str, int))

    status, headers, body = docker_smoke._wait_for_request(
        "http://127.0.0.1:8000/api/projects",
        timeout=1.0,
        interval=0.01,
        headers={"Content-Type": "application/json"},
        data=b'{"name": "docker-smoke"}',
        method="POST",
        validate=_project_created,
    )

    assert status == 200
    assert headers["content-type"] == "application/json"
    assert json.loads(body)["id"] == "proj-123"
    assert attempts["count"] == 3
