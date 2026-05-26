"""Tests for ``freecad_mcp.aieng_bridge.inspect_features`` (AIENG v0.17).

These tests are fully hermetic — they never invoke real FreeCAD. The
subprocess call is mocked, so the embedded inspection script is exercised
indirectly (its presence as a fixed constant is asserted) but never
executed. Real-FreeCAD integration tests would carry the
``@pytest.mark.freecad`` marker and skip automatically in CI.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from freecad_mcp.aieng_bridge import inspect_features as inspect_features_public
from freecad_mcp.aieng_bridge.feature_inspector import (
    FREECAD_FEATURE_INSPECT_SCRIPT,
    SUPPORTED_EXTENSIONS,
    inspect_features,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_fcstd(tmp_path: Path) -> Path:
    fcstd = tmp_path / "part.FCStd"
    # Real FCStd is a zip; the file contents are irrelevant to the unit
    # tests because FreeCAD is mocked. We write a few bytes so the file
    # exists.
    fcstd.write_bytes(b"PK\x03\x04")
    return fcstd


@pytest.fixture()
def fake_step(tmp_path: Path) -> Path:
    step = tmp_path / "part.step"
    step.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    return step


@pytest.fixture()
def fake_freecad_cmd(tmp_path: Path) -> Path:
    cmd = tmp_path / "FreeCADCmd.exe"
    cmd.write_bytes(b"")
    return cmd


_SAMPLE_RESULT = {
    "status": "ok",
    "schema_version": "0.1",
    "input_path": "/fake/part.FCStd",
    "freecad_version": "0.21.0",
    "feature_count": 2,
    "features": [
        {
            "id": "Pad",
            "label": "Pad",
            "type": "PartDesign::Pad",
            "source_object": "Pad",
            "parameters": [
                {
                    "name": "Length",
                    "value": 10.0,
                    "unit": "mm",
                    "kind": "quantity",
                    "editable": True,
                    "editor_mode": "editable",
                }
            ],
            "metadata": {"visibility": True, "has_shape": True, "property_count": 1},
        },
        {
            "id": "Fillet",
            "label": "Fillet",
            "type": "PartDesign::Fillet",
            "source_object": "Fillet",
            "parameters": [
                {
                    "name": "Radius",
                    "value": 2.5,
                    "unit": "mm",
                    "kind": "quantity",
                    "editable": True,
                    "editor_mode": "editable",
                }
            ],
            "metadata": {"visibility": True, "has_shape": True, "property_count": 1},
        },
    ],
}


def _make_fake_subprocess_run(result_payload: dict, *, returncode: int = 0):
    """Build a fake subprocess.run that writes ``result_payload`` to the
    result file expected by the embedded script.
    """

    def fake_run(cmd, *, env, capture_output, timeout):  # type: ignore[no-untyped-def]
        result_path = Path(env["AIENG_FEATURE_INSPECT_RESULT"])
        result_path.write_text(json.dumps(result_payload), encoding="utf-8")
        mock = MagicMock()
        mock.returncode = returncode
        mock.stderr = b""
        mock.stdout = b""
        return mock

    return fake_run


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def test_public_import_from_aieng_bridge() -> None:
    assert inspect_features_public is inspect_features


def test_supported_extensions_includes_common_cad_formats() -> None:
    lowered = {ext.lower() for ext in SUPPORTED_EXTENSIONS}
    assert {".fcstd", ".step", ".stp"} <= lowered


# ---------------------------------------------------------------------------
# Validation of inputs
# ---------------------------------------------------------------------------


def test_missing_source_path_raises_file_not_found(tmp_path: Path, fake_freecad_cmd: Path) -> None:
    with pytest.raises(FileNotFoundError):
        inspect_features(tmp_path / "does-not-exist.FCStd", freecad_cmd=fake_freecad_cmd)


def test_unsupported_extension_raises_value_error(tmp_path: Path, fake_freecad_cmd: Path) -> None:
    bad = tmp_path / "part.xyz"
    bad.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError):
        inspect_features(bad, freecad_cmd=fake_freecad_cmd)


def test_missing_freecad_cmd_raises_runtime_error(fake_fcstd: Path, tmp_path: Path, monkeypatch) -> None:
    """When no FreeCADCmd is configured and the env var is unset, the
    function must raise RuntimeError with a clear message — never crash
    deeper in the subprocess machinery.
    """
    monkeypatch.delenv("FREECAD_MCP_FREECAD_PATH", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        inspect_features(fake_fcstd)
    msg = str(exc_info.value).lower()
    assert "freecadcmd is not available" in msg


def test_pointing_freecad_cmd_at_missing_file_raises_runtime_error(fake_fcstd: Path, tmp_path: Path) -> None:
    ghost = tmp_path / "no-freecad" / "FreeCADCmd.exe"
    with pytest.raises(RuntimeError) as exc_info:
        inspect_features(fake_fcstd, freecad_cmd=ghost)
    assert "FreeCADCmd is not available" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Subprocess plumbing
# ---------------------------------------------------------------------------


def test_subprocess_command_uses_fixed_embedded_script_not_user_input(
    fake_fcstd: Path, fake_freecad_cmd: Path
) -> None:
    """The command line invoked by inspect_features must consist of exactly
    [freecad_cmd, script_path] where script_path points at a temp file
    holding the *fixed* FREECAD_FEATURE_INSPECT_SCRIPT constant. Caller
    input must not appear in the command line.
    """
    captured: dict = {}

    def fake_run(cmd, *, env, capture_output, timeout):  # type: ignore[no-untyped-def]
        captured["cmd"] = list(cmd)
        captured["script_contents"] = Path(cmd[1]).read_text(encoding="utf-8")
        captured["env_input"] = env.get("AIENG_FEATURE_INSPECT_INPUT")
        captured["env_result"] = env.get("AIENG_FEATURE_INSPECT_RESULT")
        Path(env["AIENG_FEATURE_INSPECT_RESULT"]).write_text(json.dumps(_SAMPLE_RESULT), encoding="utf-8")
        mock = MagicMock()
        mock.returncode = 0
        mock.stderr = b""
        mock.stdout = b""
        return mock

    with patch.object(subprocess, "run", side_effect=fake_run):
        inspect_features(fake_fcstd, freecad_cmd=fake_freecad_cmd)

    # The command is the binary + a script path — only two arguments.
    assert len(captured["cmd"]) == 2
    assert captured["cmd"][0] == str(fake_freecad_cmd)
    # The script content is the fixed embedded constant, not anything
    # influenced by the caller.
    assert captured["script_contents"] == FREECAD_FEATURE_INSPECT_SCRIPT
    # Caller input flows through the environment variable, never on argv.
    assert str(fake_fcstd) not in captured["cmd"][1]
    assert captured["env_input"].endswith("part.FCStd")
    assert captured["env_result"].endswith("result.json")


def test_valid_subprocess_output_is_parsed(
    fake_fcstd: Path, fake_freecad_cmd: Path
) -> None:
    with patch.object(subprocess, "run", side_effect=_make_fake_subprocess_run(_SAMPLE_RESULT)):
        result = inspect_features(fake_fcstd, freecad_cmd=fake_freecad_cmd)
    assert result["status"] == "ok"
    assert result["feature_count"] == 2
    assert len(result["features"]) == 2
    pad = result["features"][0]
    assert pad["id"] == "Pad"
    assert pad["parameters"][0]["name"] == "Length"
    assert pad["parameters"][0]["editable"] is True


def test_invalid_subprocess_json_raises_runtime_error(
    fake_fcstd: Path, fake_freecad_cmd: Path
) -> None:
    def fake_run(cmd, *, env, capture_output, timeout):  # type: ignore[no-untyped-def]
        Path(env["AIENG_FEATURE_INSPECT_RESULT"]).write_text("not json", encoding="utf-8")
        mock = MagicMock()
        mock.returncode = 0
        mock.stderr = b""
        mock.stdout = b""
        return mock

    with patch.object(subprocess, "run", side_effect=fake_run):
        with pytest.raises(RuntimeError) as exc_info:
            inspect_features(fake_fcstd, freecad_cmd=fake_freecad_cmd)
    assert "invalid JSON" in str(exc_info.value)


def test_subprocess_returns_no_result_file_raises_runtime_error(
    fake_fcstd: Path, fake_freecad_cmd: Path
) -> None:
    """Simulate a FreeCADCmd crash by not creating the result file."""

    def fake_run(cmd, *, env, capture_output, timeout):  # type: ignore[no-untyped-def]
        # Intentionally do NOT write the result file.
        mock = MagicMock()
        mock.returncode = 137
        mock.stderr = b"segfault"
        mock.stdout = b""
        return mock

    with patch.object(subprocess, "run", side_effect=fake_run):
        with pytest.raises(RuntimeError) as exc_info:
            inspect_features(fake_fcstd, freecad_cmd=fake_freecad_cmd)
    msg = str(exc_info.value)
    assert "did not produce a feature-inspection result file" in msg


def test_subprocess_timeout_maps_to_runtime_error(
    fake_fcstd: Path, fake_freecad_cmd: Path
) -> None:
    def fake_run(cmd, *, env, capture_output, timeout):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    with patch.object(subprocess, "run", side_effect=fake_run):
        with pytest.raises(RuntimeError) as exc_info:
            inspect_features(fake_fcstd, freecad_cmd=fake_freecad_cmd, timeout=1)
    assert "timed out" in str(exc_info.value)


def test_subprocess_reports_status_error_raises_runtime_error(
    fake_fcstd: Path, fake_freecad_cmd: Path
) -> None:
    """If the embedded script writes ``{"status": "error", "error": "..."}``
    (for example because FreeCAD is unimportable inside the subprocess), the
    Python-level caller must surface that as a clear RuntimeError.
    """
    payload = {"status": "error", "error": "FreeCAD module is not importable"}
    with patch.object(subprocess, "run", side_effect=_make_fake_subprocess_run(payload)):
        with pytest.raises(RuntimeError) as exc_info:
            inspect_features(fake_fcstd, freecad_cmd=fake_freecad_cmd)
    assert "FreeCAD inspection failed" in str(exc_info.value)
    assert "not importable" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Output shape compatible with aieng-ui v0.16
# ---------------------------------------------------------------------------


def test_output_features_are_normaliser_compatible(
    fake_fcstd: Path, fake_freecad_cmd: Path
) -> None:
    """aieng-ui v0.15 ``_normalize_feature`` accepts either a dict-of-name->value
    or a list-of-parameter-dicts under ``parameters``. The reader emits the
    list form. Test that each feature carries at minimum: id, type/kind,
    and a parameters list with name+value entries.
    """
    with patch.object(subprocess, "run", side_effect=_make_fake_subprocess_run(_SAMPLE_RESULT)):
        result = inspect_features(fake_fcstd, freecad_cmd=fake_freecad_cmd)

    for feature in result["features"]:
        assert "id" in feature
        assert "type" in feature
        params = feature["parameters"]
        assert isinstance(params, list)
        for p in params:
            assert "name" in p
            assert "value" in p


# ---------------------------------------------------------------------------
# Read-only invariants
# ---------------------------------------------------------------------------


def test_input_file_bytes_are_unchanged_after_inspection(
    fake_fcstd: Path, fake_freecad_cmd: Path
) -> None:
    before = fake_fcstd.read_bytes()
    before_mtime = fake_fcstd.stat().st_mtime_ns
    with patch.object(subprocess, "run", side_effect=_make_fake_subprocess_run(_SAMPLE_RESULT)):
        inspect_features(fake_fcstd, freecad_cmd=fake_freecad_cmd)
    assert fake_fcstd.read_bytes() == before
    assert fake_fcstd.stat().st_mtime_ns == before_mtime


def test_does_not_call_step_export_or_macro_runner(
    fake_fcstd: Path, fake_freecad_cmd: Path, monkeypatch
) -> None:
    """v0.17 reader must not reach into other freecad_mcp execution
    surfaces. If it accidentally imported ``step_exporter`` or
    ``macro_runner`` and called them, this test would fail loudly.
    """
    from freecad_mcp import macro_runner, step_exporter

    def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("read-only inspector must not call export/macro paths")

    monkeypatch.setattr(step_exporter, "run_step_export", boom, raising=False)
    monkeypatch.setattr(macro_runner, "run_macro", boom, raising=False)
    with patch.object(subprocess, "run", side_effect=_make_fake_subprocess_run(_SAMPLE_RESULT)):
        result = inspect_features(fake_fcstd, freecad_cmd=fake_freecad_cmd)
    assert result["status"] == "ok"


def test_embedded_script_never_calls_save_export_or_edit() -> None:
    """The fixed embedded script must not call any mutating FreeCAD API.
    This is a static-string check — guards against future edits that
    silently introduce mutation primitives.
    """
    script = FREECAD_FEATURE_INSPECT_SCRIPT
    forbidden_calls = [
        "doc.save(",
        ".saveAs(",
        ".exportAs(",
        ".addObject(",
        ".removeObject(",
        ".setExpression(",
        "FreeCAD.Console.PrintMessage",  # not forbidden but no console-side effects expected
    ]
    # We only assert truly mutating calls — console output is allowed.
    truly_forbidden = ["doc.save(", ".saveAs(", ".exportAs(", ".addObject(", ".removeObject(", ".setExpression("]
    for needle in truly_forbidden:
        assert needle not in script, f"script contains forbidden mutating call: {needle}"
    # Sanity: the script does open documents and does call closeDocument
    # (without saving), but it must not save them.
    assert "closeDocument" in script
    assert "FreeCAD.saveDocument" not in script
    assert "Part.export" not in script


def test_inspect_features_freecad_cmd_resolves_directory_to_binary(
    fake_fcstd: Path, tmp_path: Path
) -> None:
    """Passing a FreeCAD home directory should resolve to the binary
    inside it. Mirrors how aieng-ui passes ``settings.freecad_home``-style
    paths.
    """
    home = tmp_path / "freecad-home"
    (home / "bin").mkdir(parents=True)
    binary = home / "bin" / "FreeCADCmd.exe"
    binary.write_bytes(b"")

    captured: dict = {}

    def fake_run(cmd, *, env, capture_output, timeout):  # type: ignore[no-untyped-def]
        captured["binary"] = cmd[0]
        Path(env["AIENG_FEATURE_INSPECT_RESULT"]).write_text(json.dumps(_SAMPLE_RESULT), encoding="utf-8")
        mock = MagicMock()
        mock.returncode = 0
        mock.stderr = b""
        mock.stdout = b""
        return mock

    with patch.object(subprocess, "run", side_effect=fake_run):
        inspect_features(fake_fcstd, freecad_cmd=home)
    assert captured["binary"] == str(binary)


def test_inspect_features_falls_back_to_freecad_mcp_path_env_var(
    fake_fcstd: Path, tmp_path: Path, monkeypatch
) -> None:
    """If no ``freecad_cmd`` argument is given, the function must use
    ``FREECAD_MCP_FREECAD_PATH`` from the environment.
    """
    home = tmp_path / "env-freecad"
    (home / "bin").mkdir(parents=True)
    binary = home / "bin" / "FreeCADCmd.exe"
    binary.write_bytes(b"")
    monkeypatch.setenv("FREECAD_MCP_FREECAD_PATH", str(home))

    with patch.object(subprocess, "run", side_effect=_make_fake_subprocess_run(_SAMPLE_RESULT)):
        result = inspect_features(fake_fcstd)
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Optional real-FreeCAD integration test (skipped unless explicitly enabled)
# ---------------------------------------------------------------------------


@pytest.mark.freecad
def test_real_freecad_inspect_features_on_minimal_step(tmp_path: Path) -> None:
    """Integration test placeholder — runs only when FreeCAD is importable
    (see conftest.py for the marker-based skip). This test is intentionally
    permissive: it asserts the public function works end-to-end on a tiny
    STEP file without making assumptions about FreeCAD feature naming.
    """
    import os

    cmd_path = os.environ.get("FREECAD_MCP_FREECAD_PATH")
    if not cmd_path:
        pytest.skip("FREECAD_MCP_FREECAD_PATH not set")
    step = tmp_path / "cube.step"
    # A genuinely minimal STEP file would be needed for a real
    # integration run; here we only execute when explicitly opted in.
    if not step.exists():
        pytest.skip("no real STEP fixture provided for the integration run")
    result = inspect_features(step)
    assert result["status"] == "ok"
    assert isinstance(result["features"], list)
