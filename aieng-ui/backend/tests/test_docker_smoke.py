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


def test_wait_for_stream_timeout_raises_runtime_error(monkeypatch) -> None:
    docker_smoke = _load_docker_smoke_module()

    def fake_open_stream(url: str, *, timeout: float, headers: dict[str, str] | None):
        raise ConnectionResetError("connection reset by peer")

    monkeypatch.setattr(docker_smoke, "_open_stream", fake_open_stream)
    monkeypatch.setattr(docker_smoke.time, "sleep", lambda _seconds: None)

    try:
        docker_smoke._wait_for_stream(
            "http://127.0.0.1:8765/sse",
            timeout=0.05,
            interval=0.01,
        )
    except RuntimeError as exc:
        msg = str(exc)
        assert "stream endpoint did not become ready" in msg
        assert "connection reset by peer" in msg
    else:
        raise AssertionError("expected RuntimeError was not raised")


def test_open_stream_success(monkeypatch) -> None:
    docker_smoke = _load_docker_smoke_module()

    class _FakeResponse:
        status = 200
        headers = {"Content-Type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(req, *, timeout):
        return _FakeResponse()

    monkeypatch.setattr(docker_smoke.urllib.request, "urlopen", fake_urlopen)

    status, headers = docker_smoke._open_stream("http://127.0.0.1:8765/sse")
    assert status == 200
    assert headers["Content-Type"] == "text/event-stream"


def test_open_stream_http_error(monkeypatch) -> None:
    docker_smoke = _load_docker_smoke_module()

    class _FakeErrorResponse:
        code = 503
        headers = {"Content-Type": "text/plain"}

        def read(self):
            return b"Service Unavailable"

    def fake_urlopen(req, *, timeout):
        raise docker_smoke.urllib.error.HTTPError(
            "http://127.0.0.1:8765/sse", 503, "Service Unavailable",
            {"Content-Type": "text/plain"}, None
        )

    monkeypatch.setattr(docker_smoke.urllib.request, "urlopen", fake_urlopen)

    status, headers = docker_smoke._open_stream("http://127.0.0.1:8765/sse")
    assert status == 503
    assert headers["Content-Type"] == "text/plain"
