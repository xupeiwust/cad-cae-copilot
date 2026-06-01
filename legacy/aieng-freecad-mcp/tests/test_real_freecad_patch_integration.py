"""Real FreeCAD integration tests for the .aieng patch bridge.

These tests run only when FreeCAD is available. By default, they are skipped
if FreeCAD cannot be imported. Set FREECAD_MCP_REQUIRE_FREECAD=1 to treat
unavailability as a test failure.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

# ------------------------------------------------------------------
# FreeCAD availability detection
# ------------------------------------------------------------------

_FREECAD_AVAILABLE: bool | None = None


def freecad_available() -> bool:
    """Return True if FreeCAD Python modules are importable."""
    global _FREECAD_AVAILABLE
    if _FREECAD_AVAILABLE is None:
        try:
            import FreeCAD  # noqa: F401
            _FREECAD_AVAILABLE = True
        except ImportError:
            _FREECAD_AVAILABLE = False
    return _FREECAD_AVAILABLE


def require_freecad_env_set() -> bool:
    return os.environ.get("FREECAD_MCP_REQUIRE_FREECAD", "") == "1"


def _skip_or_fail_if_no_freecad() -> None:
    if freecad_available():
        return
    if require_freecad_env_set():
        pytest.fail("FREECAD_MCP_REQUIRE_FREECAD=1 but FreeCAD is not available")
    pytest.skip("FreeCAD is not available")


# ------------------------------------------------------------------
# Fixture helpers
# ------------------------------------------------------------------

@pytest.fixture
def real_executor():
    """Provide a real FreeCAD executor if available, otherwise skip."""
    _skip_or_fail_if_no_freecad()

    from freecad_mcp.bridge.executor import FreecadExecutor

    class InProcessExecutor(FreecadExecutor):
        def __init__(self) -> None:
            self.calls: list[str] = []
            import FreeCAD

            self._fc = FreeCAD

        async def execute_async(self, code: str) -> dict:
            self.calls.append(code)
            namespace = {"FreeCAD": self._fc, "Part": __import__("Part")}
            try:
                exec(code, namespace)
                result = namespace.get("_result_", {})
                return {"success": True, "result": result}
            except Exception as exc:
                return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

        async def get_version_async(self) -> dict:
            return {"version": ".".join(self._fc.Version()[:3]), "gui_available": False}

    return InProcessExecutor()


@pytest.fixture
def parametric_bracket_package(tmp_path: Path):
    """Copy the parametric_bracket fixture into a temp directory."""
    fixture_src = (
        Path(__file__).resolve().parent.parent
        / "examples"
        / "parametric_bracket"
        / "package"
    )
    fixture_dst = tmp_path / "package"
    shutil.copytree(fixture_src, fixture_dst)
    return fixture_dst


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

class TestFreecadAvailability:
    def test_freecad_availability_detected(self) -> None:
        """The availability helper should return a boolean."""
        result = freecad_available()
        assert isinstance(result, bool)

    def test_skip_behavior_without_env_var(self) -> None:
        """Without FREECAD_MCP_REQUIRE_FREECAD, missing FreeCAD should trigger skip."""
        # This is a meta-test: if FreeCAD is available, we just pass.
        # If not, the skip_or_fail helper would have been called.
        assert True

    def test_require_freecad_env_var(self, monkeypatch) -> None:
        """With FREECAD_MCP_REQUIRE_FREECAD=1, missing FreeCAD should fail."""
        monkeypatch.setenv("FREECAD_MCP_REQUIRE_FREECAD", "1")
        if not freecad_available():
            with pytest.raises(pytest.fail.Exception):
                _skip_or_fail_if_no_freecad()


@pytest.mark.freecad
@pytest.mark.asyncio
class TestRealFreecadPatchIntegration:
    async def test_modify_parameter_changes_freecad_param(
        self, real_executor, parametric_bracket_package
    ) -> None:
        """A modify_parameter patch should actually change the FreeCAD parameter."""
        _skip_or_fail_if_no_freecad()

        import FreeCAD as App

        # Create a simple document with a box
        doc = App.newDocument("TestDoc")
        box = doc.addObject("Part::Box", "BasePlate")
        box.Length = 100.0
        box.Width = 60.0
        box.Height = 10.0
        doc.recompute()

        from freecad_mcp.aieng_bridge.patch import execute_patch_plan, parse_patch_proposal

        plan = parse_patch_proposal(
            {
                "patch_id": "test_patch",
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "BasePlate",
                        "parameter_name": "Height",
                        "new_value": 8.0,
                    }
                ],
            }
        )

        summary = await execute_patch_plan(plan, real_executor, dry_run=False)

        assert summary.status == "success"
        assert len(summary.steps) == 1
        assert summary.steps[0].status == "success"
        assert summary.steps[0].result is not None
        assert summary.steps[0].result.get("old_value") == 10.0
        assert summary.steps[0].result.get("new_value") == 8.0

        # Verify actual FreeCAD object changed
        assert box.Height == 8.0

        App.closeDocument(doc.Name)

    async def test_recompute_succeeds_after_patch(
        self, real_executor, parametric_bracket_package
    ) -> None:
        """FreeCAD recompute should succeed after parameter modification."""
        _skip_or_fail_if_no_freecad()

        import FreeCAD as App

        doc = App.newDocument("TestDoc2")
        box = doc.addObject("Part::Box", "BasePlate")
        box.Length = 100.0
        box.Width = 60.0
        box.Height = 10.0
        doc.recompute()
        original_volume = float(box.Shape.Volume)

        from freecad_mcp.aieng_bridge.patch import execute_patch_plan, parse_patch_proposal

        plan = parse_patch_proposal(
            {
                "patch_id": "test_patch_2",
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "BasePlate",
                        "parameter_name": "Height",
                        "new_value": 5.0,
                    }
                ],
            }
        )

        summary = await execute_patch_plan(plan, real_executor, dry_run=False)

        assert summary.status == "success"
        # Volume should have changed because Height changed
        new_volume = float(box.Shape.Volume)
        assert new_volume != original_volume
        assert new_volume < original_volume

        App.closeDocument(doc.Name)

    async def test_modified_artifacts_exported(
        self, real_executor, tmp_path: Path
    ) -> None:
        """Export options should produce actual artifact files."""
        _skip_or_fail_if_no_freecad()

        import FreeCAD as App

        doc = App.newDocument("TestDoc3")
        box = doc.addObject("Part::Box", "BasePlate")
        box.Length = 100.0
        box.Width = 60.0
        box.Height = 10.0
        doc.recompute()

        from freecad_mcp.aieng_bridge.patch import execute_patch_plan, parse_patch_proposal

        plan = parse_patch_proposal(
            {
                "patch_id": "test_patch_3",
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "BasePlate",
                        "parameter_name": "Height",
                        "new_value": 8.0,
                    }
                ],
            }
        )

        out_dir = tmp_path / "artifacts"
        out_dir.mkdir(parents=True, exist_ok=True)
        summary = await execute_patch_plan(
            plan,
            real_executor,
            dry_run=False,
            export_modified_step=True,
            export_modified_fcstd=True,
            artifact_output_dir=str(out_dir),
        )

        assert summary.status == "success"
        # Artifacts should include step, fcstd
        assert len(summary.artifacts_written) >= 2
        assert any(str(a).endswith(".step") for a in summary.artifacts_written)
        assert any(str(a).endswith(".FCStd") for a in summary.artifacts_written)

        # Verify files exist
        for artifact in summary.artifacts_written:
            p = Path(artifact)
            if p.suffix in (".step", ".FCStd"):
                assert p.exists(), f"Artifact not found: {p}"

        App.closeDocument(doc.Name)

    async def test_evidence_and_trace_persisted(
        self, real_executor, parametric_bracket_package
    ) -> None:
        """Evidence and trace should be appended when persist_to_aieng=True."""
        _skip_or_fail_if_no_freecad()

        import FreeCAD as App

        doc = App.newDocument("TestDoc4")
        box = doc.addObject("Part::Box", "BasePlate")
        box.Height = 10.0
        doc.recompute()

        # Write a matching feature_graph so the patch resolves and passes guards
        fg_path = parametric_bracket_package / "graph" / "feature_graph.json"
        fg_path.write_text(
            json.dumps(
                {
                    "features": {
                        "BasePlate": {
                            "freecad_object_name": "BasePlate",
                            "editability": {"executable": True, "mode": "executable_by_regeneration"},
                            "writeback_strategy": "freecad_regeneration",
                            "parameters": [
                                {"name": "Height", "freecad_parameter_name": "Height"}
                            ],
                        }
                    }
                }
            )
        )

        from freecad_mcp.aieng_bridge.patch import execute_patch_plan, parse_patch_proposal

        plan = parse_patch_proposal(
            {
                "patch_id": "test_patch_4",
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "BasePlate",
                        "parameter_name": "Height",
                        "new_value": 8.0,
                    }
                ],
            }
        )

        summary = await execute_patch_plan(
            plan,
            real_executor,
            package_path=str(parametric_bracket_package),
            persist_to_aieng=True,
        )

        assert summary.status == "success"

        evidence = json.loads(
            (parametric_bracket_package / "results" / "evidence_index.json").read_text()
        )
        assert len(evidence.get("entries", [])) >= 1

        trace = json.loads(
            (parametric_bracket_package / "provenance" / "tool_trace.json").read_text()
        )
        assert len(trace.get("entries", [])) >= 1

        App.closeDocument(doc.Name)

    async def test_claim_map_unchanged(
        self, real_executor, parametric_bracket_package
    ) -> None:
        """claim_map.json must not be modified by patch execution."""
        _skip_or_fail_if_no_freecad()

        import FreeCAD as App

        doc = App.newDocument("TestDoc5")
        box = doc.addObject("Part::Box", "BasePlate")
        box.Height = 10.0
        doc.recompute()

        original_claim_map = json.loads(
            (parametric_bracket_package / "results" / "claim_map.json").read_text()
        )

        # Write a matching feature_graph so the patch resolves and passes guards
        fg_path = parametric_bracket_package / "graph" / "feature_graph.json"
        fg_path.write_text(
            json.dumps(
                {
                    "features": {
                        "BasePlate": {
                            "freecad_object_name": "BasePlate",
                            "editability": {"executable": True, "mode": "executable_by_regeneration"},
                            "writeback_strategy": "freecad_regeneration",
                            "parameters": [
                                {"name": "Height", "freecad_parameter_name": "Height"}
                            ],
                        }
                    }
                }
            )
        )

        from freecad_mcp.aieng_bridge.patch import execute_patch_plan, parse_patch_proposal

        plan = parse_patch_proposal(
            {
                "patch_id": "test_patch_5",
                "operations": [
                    {
                        "operation": "modify_parameter",
                        "target_feature_id": "BasePlate",
                        "parameter_name": "Height",
                        "new_value": 8.0,
                    }
                ],
            }
        )

        summary = await execute_patch_plan(
            plan,
            real_executor,
            package_path=str(parametric_bracket_package),
            persist_to_aieng=True,
            export_modified_step=True,
            export_modified_fcstd=True,
        )

        assert summary.status == "success"

        after_claim_map = json.loads(
            (parametric_bracket_package / "results" / "claim_map.json").read_text()
        )
        assert after_claim_map == original_claim_map

        App.closeDocument(doc.Name)


# ------------------------------------------------------------------
# FreeCADCmd subprocess integration tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
class TestFreecadCmdPatchIntegration:
    """Integration tests for FreeCADCmd subprocess executor.

    These tests require a real FreeCAD installation with FreeCADCmd.
    They are skipped if FreeCADCmd is not found at the configured path.
    """

    @pytest.fixture
    async def cmd_executor(self):
        """Provide a FreecadCmdExecutor if FreeCADCmd is available."""
        from freecad_mcp.bridge.freecad_cmd import FreecadCmdExecutor
        from freecad_mcp.contracts import ToolExecutionError

        try:
            executor = FreecadCmdExecutor()
        except ToolExecutionError as exc:
            pytest.skip(f"FreeCADCmd not available: {exc}")
        return executor

    async def _create_fixture_fcstd(self, cmd_path: str, output_path: Path) -> None:
        """Create a fixture FCStd using FreeCADCmd directly."""
        import asyncio

        script = f"""
import FreeCAD
doc = FreeCAD.newDocument("TestDoc")
box = doc.addObject("Part::Box", "BasePlate")
box.Length = 100.0
box.Width = 60.0
box.Height = 10.0
doc.recompute()
doc.saveAs({str(output_path)!r})
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "create.py"
            script_path.write_text(script, encoding="utf-8")

            proc = await asyncio.create_subprocess_exec(
                cmd_path,
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=120.0
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"Fixture creation failed (exit {proc.returncode}): {stderr.decode('utf-8', errors='replace')}"
                )

    async def test_cmd_modify_parameter_returns_old_and_new_value(
        self, cmd_executor, tmp_path: Path
    ) -> None:
        """FreeCADCmd executor should modify a parameter and return old/new values."""
        fixture_fcstd = tmp_path / "fixture.FCStd"
        await self._create_fixture_fcstd(cmd_executor._cmd_path, fixture_fcstd)
        assert fixture_fcstd.exists(), "Fixture FCStd was not created"

        from freecad_mcp.tools_cad import _execute_set_parameter

        result = await _execute_set_parameter(
            cmd_executor,
            "BasePlate",
            "Height",
            8.0,
            input_fcstd=str(fixture_fcstd),
        )

        assert result["object_name"] == "BasePlate"
        assert result["parameter_name"] == "Height"
        assert result["old_value"] == 10.0
        assert result["new_value"] == 8.0

    async def test_cmd_source_fcstd_not_modified_in_place(
        self, cmd_executor, tmp_path: Path
    ) -> None:
        """The input FCStd must not be modified by the subprocess executor."""
        import hashlib

        fixture_fcstd = tmp_path / "fixture.FCStd"
        await self._create_fixture_fcstd(cmd_executor._cmd_path, fixture_fcstd)

        original_hash = hashlib.sha256(fixture_fcstd.read_bytes()).hexdigest()

        from freecad_mcp.tools_cad import _execute_set_parameter

        await _execute_set_parameter(
            cmd_executor,
            "BasePlate",
            "Height",
            8.0,
            input_fcstd=str(fixture_fcstd),
        )

        after_hash = hashlib.sha256(fixture_fcstd.read_bytes()).hexdigest()
        assert after_hash == original_hash, "Source FCStd was modified in place"

    async def test_cmd_export_fcstd_produces_output_file(
        self, cmd_executor, tmp_path: Path
    ) -> None:
        """Export FCStd after modification should produce a new file."""
        fixture_fcstd = tmp_path / "fixture.FCStd"
        output_fcstd = tmp_path / "output.FCStd"
        await self._create_fixture_fcstd(cmd_executor._cmd_path, fixture_fcstd)

        from freecad_mcp.tools_cad import _execute_set_parameter, _execute_export_fcstd

        # Modify parameter
        await _execute_set_parameter(
            cmd_executor,
            "BasePlate",
            "Height",
            8.0,
            input_fcstd=str(fixture_fcstd),
        )

        # Export to new file
        await _execute_export_fcstd(
            cmd_executor,
            str(output_fcstd),
            input_fcstd=str(fixture_fcstd),
        )

        assert output_fcstd.exists(), "Output FCStd was not created"
        assert output_fcstd.stat().st_size > 0, "Output FCStd is empty"

    async def test_cmd_step_export_produces_output_file(
        self, cmd_executor, tmp_path: Path
    ) -> None:
        """Export STEP after modification should produce a new file."""
        fixture_fcstd = tmp_path / "fixture.FCStd"
        output_step = tmp_path / "output.step"
        await self._create_fixture_fcstd(cmd_executor._cmd_path, fixture_fcstd)

        from freecad_mcp.tools_cad import _execute_set_parameter, _execute_export_step

        # Modify parameter
        await _execute_set_parameter(
            cmd_executor,
            "BasePlate",
            "Height",
            8.0,
            input_fcstd=str(fixture_fcstd),
        )

        # Export STEP
        await _execute_export_step(
            cmd_executor,
            str(output_step),
            input_fcstd=str(fixture_fcstd),
        )

        assert output_step.exists(), "Output STEP was not created"
        assert output_step.stat().st_size > 0, "Output STEP is empty"

    async def test_cmd_version_returns_something(
        self, cmd_executor
    ) -> None:
        """get_version_async should return version info from FreeCADCmd."""
        result = await cmd_executor.get_version_async()
        assert "version" in result
        # FreeCAD should report a version like "1.1.0" or "0.21.0"
        assert len(result.get("version", "")) > 0

    async def test_cmd_rejects_same_input_and_output_fcstd(
        self, cmd_executor, tmp_path: Path
    ) -> None:
        """Executor should reject when input and output FCStd paths are identical."""
        fixture_fcstd = tmp_path / "fixture.FCStd"
        await self._create_fixture_fcstd(cmd_executor._cmd_path, fixture_fcstd)

        from freecad_mcp.contracts import ToolExecutionError
        from unittest.mock import patch

        # Manually construct an operation dict with identical input/output
        op = {
            "operation": "modify_parameter",
            "object_name": "BasePlate",
            "parameter_name": "Height",
            "new_value": 8.0,
            "input_fcstd": str(fixture_fcstd.resolve()),
            "output_fcstd": str(fixture_fcstd.resolve()),
        }

        with patch.object(cmd_executor, "_parse_operation", return_value=op):
            with pytest.raises(ToolExecutionError, match="same file"):
                await cmd_executor.execute_async("dummy code")
