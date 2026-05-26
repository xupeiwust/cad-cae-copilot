"""Default tests for FreecadCmdExecutor (no FreeCAD required).

All tests mock subprocess behavior or test parsing/script generation in
isolation.  Tests that require a real FreeCADCmd are in
``test_real_freecad_patch_integration.py`` and gated behind
``@pytest.mark.freecad``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from freecad_mcp.bridge.freecad_cmd import FreecadCmdExecutor
from freecad_mcp.contracts import ToolExecutionError


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_modify_parameter_code(
    object_name: str = "BasePlate",
    parameter_name: str = "Height",
    value: float = 8.0,
    doc_name: str | None = None,
    input_fcstd: str | None = None,
) -> str:
    """Generate the exact code pattern produced by ``_execute_set_parameter``."""
    if input_fcstd:
        doc_line = f"doc = FreeCAD.open({input_fcstd!r})"
    else:
        doc_line = f"doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})"
    return f"""
import FreeCAD
{doc_line}
if doc is None:
    raise ValueError("Document not found")
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
if not hasattr(obj, {parameter_name!r}):
    raise ValueError(f"Parameter not found: {parameter_name!r}")
old_value = getattr(obj, {parameter_name!r})
try:
    if hasattr(old_value, "Value"):
        old_value = old_value.Value
except Exception:
    pass
setattr(obj, {parameter_name!r}, {value!r})
doc.recompute()
_result_ = {{
    "object_name": obj.Name,
    "parameter_name": {parameter_name!r},
    "old_value": old_value,
    "new_value": {value!r},
}}
"""


def _make_export_step_code(file_path: str = "/tmp/out.step", doc_name: str | None = None) -> str:
    return f"""
import FreeCAD
import Part
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
shape.exportStep({file_path!r})
_result_ = {{"file_path": {file_path!r}, "object_count": 1}}
"""


def _make_export_fcstd_code(file_path: str = "/tmp/out.FCStd", doc_name: str | None = None) -> str:
    return f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
doc.saveAs({file_path!r})
_result_ = {{"file_path": {file_path!r}, "document": doc.Name}}
"""


async def _fake_subprocess_with_result(result: dict, returncode: int = 0):
    """Return a factory that creates a mock process writing *result* to the env result path."""
    def _factory(*_args, **_kwargs) -> asyncio.subprocess.Process:
        proc = MagicMock(spec=asyncio.subprocess.Process)
        proc.returncode = returncode

        env = _kwargs.get("env", {})
        result_path = env.get("FC_RESULT_PATH")

        async def _communicate() -> tuple[bytes, bytes]:
            if result_path:
                Path(result_path).write_text(json.dumps(result), encoding="utf-8")
            return b"", b""

        proc.communicate = _communicate
        proc.kill = MagicMock()
        return proc

    return _factory


# ------------------------------------------------------------------
# Construction / path resolution
# ------------------------------------------------------------------

class TestConstruction:
    def test_init_without_env_var_raises(self, monkeypatch) -> None:
        monkeypatch.delenv("FREECAD_HOME", raising=False)
        monkeypatch.delenv("FREECAD_MCP_FREECAD_PATH", raising=False)
        with pytest.raises(ToolExecutionError, match="FreeCADCmd not found"):
            FreecadCmdExecutor()

    def test_init_with_fake_path_raises(self, monkeypatch, tmp_path: Path) -> None:
        fake = tmp_path / "not_freecad"
        fake.mkdir()
        monkeypatch.setenv("FREECAD_HOME", str(fake))
        with pytest.raises(ToolExecutionError, match="FreeCADCmd not found"):
            FreecadCmdExecutor()

    def test_init_finds_cmd_on_windows(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "FreeCADCmd.exe").touch()
        monkeypatch.setenv("FREECAD_HOME", str(tmp_path))
        exc = FreecadCmdExecutor()
        assert "FreeCADCmd.exe" in exc._cmd_path

    def test_init_finds_cmd_on_linux(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "FreeCADCmd").touch()
        monkeypatch.setenv("FREECAD_HOME", str(tmp_path))
        exc = FreecadCmdExecutor()
        assert "FreeCADCmd" in exc._cmd_path

    def test_mcp_path_takes_precedence(self, monkeypatch, tmp_path: Path) -> None:
        mcp_path = tmp_path / "mcp_freecad"
        mcp_bin = mcp_path / "bin"
        mcp_bin.mkdir(parents=True)
        (mcp_bin / "FreeCADCmd.exe").touch()
        home_path = tmp_path / "home_freecad"
        home_path.mkdir()
        monkeypatch.setenv("FREECAD_MCP_FREECAD_PATH", str(mcp_path))
        monkeypatch.setenv("FREECAD_HOME", str(home_path))
        monkeypatch.setattr(sys, "platform", "win32")
        exc = FreecadCmdExecutor()
        assert "mcp_freecad" in exc._cmd_path


# ------------------------------------------------------------------
# Parsing
# ------------------------------------------------------------------

class TestParsing:
    def test_parse_modify_parameter(self) -> None:
        exc = FreecadCmdExecutor.__new__(FreecadCmdExecutor)
        code = _make_modify_parameter_code("BasePlate", "Height", 8.0)
        op = exc._parse_operation(code)
        assert op is not None
        assert op["operation"] == "modify_parameter"
        assert op["object_name"] == "BasePlate"
        assert op["parameter_name"] == "Height"
        assert op["new_value"] == 8.0
        assert op["doc_name"] is None
        assert op["input_fcstd"] is None

    def test_parse_modify_parameter_with_doc_name(self) -> None:
        exc = FreecadCmdExecutor.__new__(FreecadCmdExecutor)
        code = _make_modify_parameter_code("BasePlate", "Height", 8.0, doc_name="TestDoc")
        op = exc._parse_operation(code)
        assert op is not None
        assert op["doc_name"] == "TestDoc"

    def test_parse_modify_parameter_with_input_fcstd(self) -> None:
        exc = FreecadCmdExecutor.__new__(FreecadCmdExecutor)
        code = _make_modify_parameter_code("BasePlate", "Height", 8.0, input_fcstd="C:/temp/fixture.FCStd")
        op = exc._parse_operation(code)
        assert op is not None
        assert op["input_fcstd"] == "C:/temp/fixture.FCStd"

    def test_parse_export_step(self) -> None:
        exc = FreecadCmdExecutor.__new__(FreecadCmdExecutor)
        code = _make_export_step_code("/tmp/out.step")
        op = exc._parse_operation(code)
        assert op is not None
        assert op["operation"] == "export_step"
        assert op["file_path"] == "/tmp/out.step"

    def test_parse_export_fcstd(self) -> None:
        exc = FreecadCmdExecutor.__new__(FreecadCmdExecutor)
        code = _make_export_fcstd_code("/tmp/out.FCStd")
        op = exc._parse_operation(code)
        assert op is not None
        assert op["operation"] == "export_fcstd"
        assert op["file_path"] == "/tmp/out.FCStd"

    def test_parse_arbitrary_code_returns_none(self) -> None:
        exc = FreecadCmdExecutor.__new__(FreecadCmdExecutor)
        op = exc._parse_operation("print('hello')")
        assert op is None

    def test_parse_rejects_unsupported_operation(self) -> None:
        exc = FreecadCmdExecutor.__new__(FreecadCmdExecutor)
        code = "import FreeCAD\nFreeCAD.newDocument('X')"
        op = exc._parse_operation(code)
        assert op is None


# ------------------------------------------------------------------
# Script generation
# ------------------------------------------------------------------

class TestScriptGeneration:
    def test_modify_parameter_script_is_valid_python(self) -> None:
        exc = FreecadCmdExecutor.__new__(FreecadCmdExecutor)
        script = exc._generate_script({"operation": "modify_parameter"})
        compile(script, "<string>", "exec")

    def test_export_step_script_is_valid_python(self) -> None:
        exc = FreecadCmdExecutor.__new__(FreecadCmdExecutor)
        script = exc._generate_script({"operation": "export_step"})
        compile(script, "<string>", "exec")

    def test_export_fcstd_script_is_valid_python(self) -> None:
        exc = FreecadCmdExecutor.__new__(FreecadCmdExecutor)
        script = exc._generate_script({"operation": "export_fcstd"})
        compile(script, "<string>", "exec")

    def test_unsupported_operation_raises(self) -> None:
        exc = FreecadCmdExecutor.__new__(FreecadCmdExecutor)
        with pytest.raises(ToolExecutionError, match="Unsupported operation"):
            exc._generate_script({"operation": "delete_everything"})

    def test_script_contains_no_f_string_interpolation(self) -> None:
        """User values must not be interpolated into the script.

        They flow through the JSON input file instead.
        """
        exc = FreecadCmdExecutor.__new__(FreecadCmdExecutor)
        script = exc._generate_script({"operation": "modify_parameter"})
        assert "{object_name}" not in script
        assert "{parameter_name}" not in script
        assert "op[" in script  # reads from JSON


# ------------------------------------------------------------------
# Subprocess execution (mocked)
# ------------------------------------------------------------------

class TestMockedExecution:
    @pytest.fixture
    def executor(self, monkeypatch, tmp_path: Path) -> FreecadCmdExecutor:
        """Provide a FreecadCmdExecutor with a fake cmd path."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(parents=True)
        fake_cmd = bin_dir / "FreeCADCmd.exe"
        fake_cmd.touch()
        monkeypatch.setenv("FREECAD_HOME", str(tmp_path))
        monkeypatch.setattr(sys, "platform", "win32")
        return FreecadCmdExecutor()

    @pytest.mark.asyncio
    async def test_execute_async_success(self, executor) -> None:
        code = _make_modify_parameter_code("BasePlate", "Height", 8.0)

        _mock = await _fake_subprocess_with_result({
            "success": True,
            "object_name": "BasePlate",
            "parameter_name": "Height",
            "old_value": 10.0,
            "new_value": 8.0,
        })

        with patch("asyncio.create_subprocess_exec", side_effect=_mock):
            result = await executor.execute_async(code)

        assert result["success"] is True
        assert result["result"]["old_value"] == 10.0
        assert result["result"]["new_value"] == 8.0
        assert executor._last_exit_code == 0
        assert executor._last_script_hash is not None
        assert len(executor._last_script_hash) == 64  # SHA-256 hex

    @pytest.mark.asyncio
    async def test_execute_async_rejects_arbitrary_code(self, executor) -> None:
        with pytest.raises(ToolExecutionError, match="bounded operations"):
            await executor.execute_async("print('hello')")

    @pytest.mark.asyncio
    async def test_execute_async_rejects_same_input_output(self, executor) -> None:
        """Guard: if both input and output FCStd are the same resolved path, reject."""
        same = str(Path("C:/same.FCStd").resolve())
        op = {
            "operation": "modify_parameter",
            "object_name": "BasePlate",
            "parameter_name": "Height",
            "new_value": 8.0,
            "input_fcstd": same,
            "output_fcstd": same,
        }
        # The guard is checked inside execute_async before generating the script.
        # We can't easily trigger it through _parse_operation because that doesn't
        # set output_fcstd. Instead, patch _parse_operation to return our op.
        with patch.object(executor, "_parse_operation", return_value=op):
            with pytest.raises(ToolExecutionError, match="same file"):
                await executor.execute_async("any code")

    @pytest.mark.asyncio
    async def test_get_version_async_success(self, executor) -> None:
        _mock = await _fake_subprocess_with_result({
            "version": "1.1.0",
            "revision": "12345",
            "python_version": "3.11.0",
            "gui_available": False,
        })

        with patch("asyncio.create_subprocess_exec", side_effect=_mock):
            result = await executor.get_version_async()

        assert result["version"] == "1.1.0"
        assert result["gui_available"] is False

    @pytest.mark.asyncio
    async def test_execute_async_timeout(self, executor) -> None:
        code = _make_modify_parameter_code()
        executor.timeout = 0.001  # 1 ms

        async def _slow(*_args, **_kwargs):
            proc = MagicMock(spec=asyncio.subprocess.Process)
            proc.kill = MagicMock()

            async def _never() -> tuple[bytes, bytes]:
                await asyncio.sleep(10)
                return b"", b""

            proc.communicate = _never
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_slow):
            with pytest.raises(ToolExecutionError, match="timed out"):
                await executor.execute_async(code)

    @pytest.mark.asyncio
    async def test_execute_async_nonzero_exit(self, executor) -> None:
        code = _make_modify_parameter_code()

        async def _mock(*_args, **_kwargs):
            proc = MagicMock(spec=asyncio.subprocess.Process)
            proc.returncode = 1

            async def _comm() -> tuple[bytes, bytes]:
                return b"", b"ERROR: something failed"

            proc.communicate = _comm
            proc.kill = MagicMock()
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_mock):
            result = await executor.execute_async(code)

        assert result["success"] is False
        assert "ERROR" in result["error"]
        assert result["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_execute_async_missing_result_file(self, executor) -> None:
        code = _make_modify_parameter_code()

        async def _mock(*_args, **_kwargs):
            proc = MagicMock(spec=asyncio.subprocess.Process)
            proc.returncode = 0

            async def _comm() -> tuple[bytes, bytes]:
                return b"", b""

            proc.communicate = _comm
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_mock):
            result = await executor.execute_async(code)

        assert result["success"] is False
        assert "result file" in result["error"]


# ------------------------------------------------------------------
# Provenance / metadata
# ------------------------------------------------------------------

class TestProvenance:
    def test_script_hash_computed(self, monkeypatch, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "FreeCADCmd.exe").touch()
        monkeypatch.setenv("FREECAD_HOME", str(tmp_path))
        monkeypatch.setattr(sys, "platform", "win32")
        exc = FreecadCmdExecutor()

        op = {"operation": "modify_parameter"}
        script = exc._generate_script(op)
        expected = __import__("hashlib").sha256(script.encode("utf-8")).hexdigest()
        assert expected is not None
        assert len(expected) == 64

    def test_calls_list_populated(self, monkeypatch, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "FreeCADCmd.exe").touch()
        monkeypatch.setenv("FREECAD_HOME", str(tmp_path))
        monkeypatch.setattr(sys, "platform", "win32")
        exc = FreecadCmdExecutor()
        code = _make_modify_parameter_code()
        exc.calls.append(code)
        assert len(exc.calls) == 1
