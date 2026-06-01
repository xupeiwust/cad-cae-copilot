"""Tests for StubFreecadExecutor — deterministic execution without FreeCAD."""

from __future__ import annotations

import pytest

from freecad_mcp.aieng_bridge.stub_executor import StubFreecadExecutor


class TestStubExecutorNoFreeCAD:
    def test_no_freecad_import(self) -> None:
        """Verify the stub module does not import FreeCAD."""
        import sys

        freecad_modules = [m for m in sys.modules if m.lower().startswith("freecad")]
        # The stub itself must not trigger a FreeCAD import.
        # Modules from other tests may linger, so we only assert the stub
        # module is clean by checking it has no FreeCAD references at import time.
        import freecad_mcp.aieng_bridge.stub_executor as stub_mod

        source = stub_mod.__loader__.get_source(stub_mod.__name__) if hasattr(stub_mod.__loader__, "get_source") else ""
        if source:
            assert "import FreeCAD" not in source
            assert "from FreeCAD" not in source

    @pytest.mark.asyncio
    async def test_get_version_async(self) -> None:
        stub = StubFreecadExecutor()
        version = await stub.get_version_async()

        assert version["version"] == "0.21.0-stub"
        assert version["gui_available"] is False
        assert "get_version" in stub.calls


class TestStubParameterSet:
    @pytest.mark.asyncio
    async def test_parameter_set_returns_old_and_new_value(self) -> None:
        feature_graph = {
            "features": {
                "Box": {
                    "freecad_object_name": "Box",
                    "parameters": [
                        {"name": "Length", "freecad_parameter_name": "Length", "current_value": 10.0}
                    ],
                }
            }
        }
        stub = StubFreecadExecutor(feature_graph=feature_graph)

        code = '''
import FreeCAD
doc = FreeCAD.ActiveDocument
obj = doc.getObject('Box')
old_value = getattr(obj, 'Length')
setattr(obj, 'Length', 20.0)
doc.recompute()
_result_ = {
    "object_name": obj.Name,
    "parameter_name": 'Length',
    "old_value": old_value,
    "new_value": 20.0,
}
'''
        resp = await stub.execute_async(code)

        assert resp["success"] is True
        result = resp["result"]
        assert result["object_name"] == "Box"
        assert result["parameter_name"] == "Length"
        assert result["old_value"] == 10.0
        assert result["new_value"] == 20.0

    @pytest.mark.asyncio
    async def test_parameter_set_updates_internal_state(self) -> None:
        feature_graph = {
            "features": {
                "Box": {
                    "freecad_object_name": "Box",
                    "parameters": [
                        {"name": "Length", "freecad_parameter_name": "Length", "current_value": 10.0}
                    ],
                }
            }
        }
        stub = StubFreecadExecutor(feature_graph=feature_graph)

        code1 = '''
import FreeCAD
doc = FreeCAD.ActiveDocument
obj = doc.getObject('Box')
setattr(obj, 'Length', 20.0)
_result_ = {
    "object_name": obj.Name,
    "parameter_name": 'Length',
    "old_value": getattr(obj, 'Length'),
    "new_value": 20.0,
}
'''
        await stub.execute_async(code1)

        # Second call should see the updated value as old_value
        code2 = '''
import FreeCAD
doc = FreeCAD.ActiveDocument
obj = doc.getObject('Box')
setattr(obj, 'Length', 30.0)
_result_ = {
    "object_name": obj.Name,
    "parameter_name": 'Length',
    "old_value": getattr(obj, 'Length'),
    "new_value": 30.0,
}
'''
        resp = await stub.execute_async(code2)

        assert resp["result"]["old_value"] == 20.0
        assert resp["result"]["new_value"] == 30.0
        assert stub.get_state()["Box"]["Length"] == 30.0

    @pytest.mark.asyncio
    async def test_parameter_set_with_initial_state(self) -> None:
        stub = StubFreecadExecutor(
            initial_state={"BasePlate": {"Thickness": 8.0}}
        )

        code = '''
import FreeCAD
doc = FreeCAD.ActiveDocument
obj = doc.getObject('BasePlate')
setattr(obj, 'Thickness', 12.0)
_result_ = {
    "object_name": obj.Name,
    "parameter_name": 'Thickness',
    "old_value": getattr(obj, 'Thickness'),
    "new_value": 12.0,
}
'''
        resp = await stub.execute_async(code)

        assert resp["result"]["old_value"] == 8.0
        assert resp["result"]["new_value"] == 12.0

    @pytest.mark.asyncio
    async def test_parameter_set_unknown_object_returns_none_old_value(self) -> None:
        stub = StubFreecadExecutor()

        code = '''
import FreeCAD
doc = FreeCAD.ActiveDocument
obj = doc.getObject('UnknownObj')
setattr(obj, 'Length', 20.0)
_result_ = {
    "object_name": obj.Name,
    "parameter_name": 'Length',
    "old_value": getattr(obj, 'Length'),
    "new_value": 20.0,
}
'''
        resp = await stub.execute_async(code)

        assert resp["result"]["old_value"] is None
        assert resp["result"]["new_value"] == 20.0

    @pytest.mark.asyncio
    async def test_parameter_set_string_value(self) -> None:
        stub = StubFreecadExecutor(
            initial_state={"Spreadsheet": {"A1": "old_text"}}
        )

        code = '''
import FreeCAD
doc = FreeCAD.ActiveDocument
obj = doc.getObject('Spreadsheet')
setattr(obj, 'A1', 'new_text')
_result_ = {
    "object_name": obj.Name,
    "parameter_name": 'A1',
    "old_value": getattr(obj, 'A1'),
    "new_value": 'new_text',
}
'''
        resp = await stub.execute_async(code)

        assert resp["result"]["old_value"] == "old_text"
        assert resp["result"]["new_value"] == "new_text"

    @pytest.mark.asyncio
    async def test_unrecognised_code_returns_empty_result(self) -> None:
        stub = StubFreecadExecutor()

        resp = await stub.execute_async("print('hello')")

        assert resp["success"] is True
        assert resp["result"] == {}


class TestStubExportOperations:
    @pytest.mark.asyncio
    async def test_export_step(self) -> None:
        stub = StubFreecadExecutor()

        code = '''
import FreeCAD
import Part
doc = FreeCAD.ActiveDocument
shape = doc.Objects[0].Shape
shape.exportStep('/tmp/test.step')
_result_ = {"file_path": '/tmp/test.step', "object_count": 1}
'''
        resp = await stub.execute_async(code)

        assert resp["success"] is True
        assert resp["result"]["file_path"] == "/tmp/test.step"
        assert resp["result"]["object_count"] == 1

    @pytest.mark.asyncio
    async def test_export_fcstd(self) -> None:
        stub = StubFreecadExecutor()

        code = '''
import FreeCAD
doc = FreeCAD.ActiveDocument
doc.saveAs('/tmp/test.FCStd')
_result_ = {"file_path": '/tmp/test.FCStd', "document": doc.Name}
'''
        resp = await stub.execute_async(code)

        assert resp["success"] is True
        assert resp["result"]["file_path"] == "/tmp/test.FCStd"
