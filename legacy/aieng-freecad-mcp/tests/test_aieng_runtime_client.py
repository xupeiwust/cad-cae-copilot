"""Tests for freecad_mcp.aieng_runtime_client.

All tests use mocked HTTP; no aieng-ui backend is required.
"""

from __future__ import annotations

import json
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from freecad_mcp.aieng_runtime_client import AiengRuntimeClient, AiengRuntimeError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(data: Any) -> MagicMock:
    """Return a MagicMock that behaves like urllib.request.urlopen's context manager."""
    mock = MagicMock()
    mock.__enter__ = lambda self: self
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = json.dumps(data).encode()
    return mock


def _mock_http_error(code: int, body: Any = None) -> urllib.error.HTTPError:
    import io
    payload = json.dumps(body or {"detail": "error"}).encode()
    return urllib.error.HTTPError(
        url="http://localhost:8000/api/test",
        code=code,
        msg="Error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(payload),
    )


# ---------------------------------------------------------------------------
# list_tools
# ---------------------------------------------------------------------------

class TestListTools:
    def test_returns_tool_list(self) -> None:
        tools_data = [
            {"name": "freecad.inspect_geometry", "requires_approval": False, "description": "Inspect"},
            {"name": "freecad.run_macro", "requires_approval": True, "description": "Run macro"},
        ]
        client = AiengRuntimeClient()
        with patch("urllib.request.urlopen", return_value=_mock_response(tools_data)):
            result = client.list_tools()
        assert len(result) == 2
        assert result[0]["name"] == "freecad.inspect_geometry"

    def test_returns_empty_list_on_non_list_response(self) -> None:
        client = AiengRuntimeClient()
        with patch("urllib.request.urlopen", return_value=_mock_response({"error": "bad"})):
            result = client.list_tools()
        assert result == []


# ---------------------------------------------------------------------------
# start_run
# ---------------------------------------------------------------------------

class TestStartRun:
    def test_sends_message_and_returns_run(self) -> None:
        run_data = {"run_id": "abc123", "status": "completed", "message": "inspect geometry"}
        client = AiengRuntimeClient()
        with patch("urllib.request.urlopen", return_value=_mock_response(run_data)) as mock_open:
            result = client.start_run("inspect geometry")
        assert result["run_id"] == "abc123"
        assert result["status"] == "completed"

    def test_sends_project_id_when_provided(self) -> None:
        captured_body: list[bytes] = []

        def fake_urlopen(req, timeout=None):
            captured_body.append(req.data)
            return _mock_response({"run_id": "r1", "status": "completed"})

        client = AiengRuntimeClient()
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.start_run("inspect geometry", project_id="proj-001")

        body = json.loads(captured_body[0].decode())
        assert body["message"] == "inspect geometry"
        assert body["project_id"] == "proj-001"

    def test_omits_project_id_when_none(self) -> None:
        captured_body: list[bytes] = []

        def fake_urlopen(req, timeout=None):
            captured_body.append(req.data)
            return _mock_response({"run_id": "r2", "status": "completed"})

        client = AiengRuntimeClient()
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.start_run("inspect geometry")

        body = json.loads(captured_body[0].decode())
        assert "project_id" not in body


# ---------------------------------------------------------------------------
# get_run / get_run_events
# ---------------------------------------------------------------------------

class TestGetRun:
    def test_returns_run_dict(self) -> None:
        run_data = {"run_id": "xyz", "status": "completed"}
        client = AiengRuntimeClient()
        with patch("urllib.request.urlopen", return_value=_mock_response(run_data)):
            result = client.get_run("xyz")
        assert result["run_id"] == "xyz"

    def test_get_run_events_returns_list(self) -> None:
        events = [{"type": "run_started"}, {"type": "run_completed"}]
        client = AiengRuntimeClient()
        with patch("urllib.request.urlopen", return_value=_mock_response(events)):
            result = client.get_run_events("xyz")
        assert len(result) == 2
        assert result[0]["type"] == "run_started"


# ---------------------------------------------------------------------------
# approve_run / reject_run
# ---------------------------------------------------------------------------

class TestApproveReject:
    def test_approve_run_calls_correct_endpoint(self) -> None:
        captured_urls: list[str] = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            return _mock_response({"run_id": "r3", "status": "completed"})

        client = AiengRuntimeClient(base_url="http://localhost:8000")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = client.approve_run("r3")

        assert "/api/runtime/runs/r3/approve" in captured_urls[0]
        assert result["status"] == "completed"

    def test_reject_run_calls_correct_endpoint(self) -> None:
        captured_urls: list[str] = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            return _mock_response({"run_id": "r4", "status": "rejected"})

        client = AiengRuntimeClient(base_url="http://localhost:8000")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = client.reject_run("r4")

        assert "/api/runtime/runs/r4/reject" in captured_urls[0]
        assert result["status"] == "rejected"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_http_error_raises_runtime_error(self) -> None:
        client = AiengRuntimeClient()
        with patch("urllib.request.urlopen", side_effect=_mock_http_error(404)):
            with pytest.raises(AiengRuntimeError) as exc_info:
                client.get_run("missing")
        assert exc_info.value.status_code == 404
        assert "HTTP 404" in str(exc_info.value)

    def test_connection_error_raises_runtime_error(self) -> None:
        import urllib.error
        client = AiengRuntimeClient(base_url="http://127.0.0.1:1")
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            with pytest.raises(AiengRuntimeError) as exc_info:
                client.list_tools()
        assert "Connection error" in str(exc_info.value)
        assert exc_info.value.status_code is None

    def test_runtime_error_stores_response_body(self) -> None:
        client = AiengRuntimeClient()
        err = _mock_http_error(422, body={"detail": "Validation failed"})
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(AiengRuntimeError) as exc_info:
                client.start_run("bad input")
        assert exc_info.value.response.get("detail") == "Validation failed"


# ---------------------------------------------------------------------------
# wait_for_run
# ---------------------------------------------------------------------------

class TestWaitForRun:
    def test_returns_immediately_when_already_completed(self) -> None:
        run_data = {"run_id": "w1", "status": "completed"}
        client = AiengRuntimeClient()
        with patch("urllib.request.urlopen", return_value=_mock_response(run_data)):
            result = client.wait_for_run("w1", timeout_seconds=5, poll_interval=0.01)
        assert result["status"] == "completed"

    def test_returns_on_awaiting_approval_without_auto_approve(self) -> None:
        run_data = {"run_id": "w2", "status": "awaiting_approval"}
        client = AiengRuntimeClient()
        with patch("urllib.request.urlopen", return_value=_mock_response(run_data)):
            result = client.wait_for_run("w2", timeout_seconds=5, poll_interval=0.01)
        assert result["status"] == "awaiting_approval"

    def test_polls_until_terminal_status(self) -> None:
        responses = [
            {"run_id": "w3", "status": "running"},
            {"run_id": "w3", "status": "running"},
            {"run_id": "w3", "status": "completed"},
        ]
        call_count = 0

        def fake_urlopen(req, timeout=None):
            nonlocal call_count
            resp = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return _mock_response(resp)

        client = AiengRuntimeClient()
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with patch("time.sleep"):  # don't actually sleep
                result = client.wait_for_run("w3", timeout_seconds=30, poll_interval=0.01)

        assert result["status"] == "completed"
        assert call_count == 3

    def test_raises_on_timeout(self) -> None:
        import time as _time
        run_data = {"run_id": "w4", "status": "running"}
        client = AiengRuntimeClient()

        # Make monotonic advance past deadline immediately on second call
        original_monotonic = _time.monotonic
        call_count = 0

        def fake_monotonic() -> float:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return 0.0   # start time
            return 100.0     # way past timeout

        with patch("urllib.request.urlopen", return_value=_mock_response(run_data)):
            with patch("time.monotonic", side_effect=fake_monotonic):
                with patch("time.sleep"):
                    with pytest.raises(AiengRuntimeError, match="Timed out"):
                        client.wait_for_run("w4", timeout_seconds=10, poll_interval=0.01)


# ---------------------------------------------------------------------------
# get_cae_preprocessing_summary / get_cae_simulation_run_summary
# ---------------------------------------------------------------------------

class TestGetCaeLifecycleSummaries:
    def test_get_cae_preprocessing_summary_calls_correct_path(self) -> None:
        captured_urls: list[str] = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            return _mock_response({"schema_version": "0.1", "status": {"ready_for_solver": False}})

        client = AiengRuntimeClient(base_url="http://localhost:8000")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = client.get_cae_preprocessing_summary("proj-abc")

        assert "/api/projects/proj-abc/cae-preprocessing-summary" in captured_urls[0]
        assert result["schema_version"] == "0.1"

    def test_get_cae_simulation_run_summary_calls_correct_path(self) -> None:
        captured_urls: list[str] = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            return _mock_response({"schema_version": "0.1", "status": {"run_count": 3}})

        client = AiengRuntimeClient(base_url="http://localhost:8000")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = client.get_cae_simulation_run_summary("proj-abc")

        assert "/api/projects/proj-abc/cae-simulation-run-summary" in captured_urls[0]
        assert result["status"]["run_count"] == 3


# ---------------------------------------------------------------------------
# base_url configuration
# ---------------------------------------------------------------------------

class TestConfiguration:
    def test_reads_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIENG_RUNTIME_BASE_URL", "http://myserver:9999")
        client = AiengRuntimeClient()
        assert client.base_url == "http://myserver:9999"

    def test_explicit_url_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIENG_RUNTIME_BASE_URL", "http://myserver:9999")
        client = AiengRuntimeClient(base_url="http://explicit:1234")
        assert client.base_url == "http://explicit:1234"

    def test_strips_trailing_slash(self) -> None:
        client = AiengRuntimeClient(base_url="http://localhost:8000/")
        assert not client.base_url.endswith("/")
