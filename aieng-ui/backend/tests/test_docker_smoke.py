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
