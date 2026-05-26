from __future__ import annotations

import zipfile

import pytest

from aieng.cli import main
from aieng.geometry.backend import (
    GeometryBackend,
    MockGeometryBackend,
    OCCGeometryBackend,
    SUPPORTED_BACKENDS,
    detect_occ_runtime,
    get_backend,
)

_OCC_AVAILABLE = detect_occ_runtime()["available"]
from aieng.geometry.step_importer import import_step_package
from aieng.geometry.topology_extractor import (
    MockTopologyExtractor,
    OCCBasedTopologyExtractor,
    TOPOLOGY_MAP_PATH,
    extract_topology_package,
)

FAKE_STEP_CONTENT = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


def write_fake_step(path):
    path.write_bytes(FAKE_STEP_CONTENT)
    return path


def imported_package(tmp_path):
    step_path = write_fake_step(tmp_path / "bracket.step")
    package_path = tmp_path / "bracket_001.aieng"
    import_step_package(step_path, package_path)
    return package_path


def read_topology_map(package_path):
    import json
    with zipfile.ZipFile(package_path) as package:
        return json.loads(package.read(TOPOLOGY_MAP_PATH))


# ---------------------------------------------------------------------------
# get_backend / SUPPORTED_BACKENDS
# ---------------------------------------------------------------------------

def test_get_backend_mock_returns_mock_geometry_backend():
    backend = get_backend("mock")
    assert isinstance(backend, MockGeometryBackend)


def test_get_backend_occ_returns_occ_geometry_backend():
    backend = get_backend("occ")
    assert isinstance(backend, OCCGeometryBackend)


def test_get_backend_unknown_raises_value_error():
    with pytest.raises(ValueError, match="Unknown geometry backend"):
        get_backend("nonexistent")


def test_get_backend_unknown_lists_supported_backends():
    try:
        get_backend("bad_name")
    except ValueError as exc:
        assert "mock" in str(exc)
        assert "occ" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_supported_backends_contains_mock_and_occ():
    assert "mock" in SUPPORTED_BACKENDS
    assert "occ" in SUPPORTED_BACKENDS


# ---------------------------------------------------------------------------
# GeometryBackend protocol
# ---------------------------------------------------------------------------

def test_geometry_backend_protocol_satisfied_by_mock():
    assert isinstance(MockGeometryBackend(), GeometryBackend)


def test_mock_geometry_backend_name_is_mock():
    assert MockGeometryBackend().name == "mock"


def test_occ_geometry_backend_name_is_occ():
    assert OCCGeometryBackend().name == "occ"


# ---------------------------------------------------------------------------
# MockGeometryBackend.extract_topology
# ---------------------------------------------------------------------------

def test_mock_geometry_backend_returns_format_version():
    result = MockGeometryBackend().extract_topology(b"unused")
    assert result["format_version"] == "0.1.0"


def test_mock_geometry_backend_extraction_backend_field():
    result = MockGeometryBackend().extract_topology(b"unused")
    assert result["metadata"]["extraction_backend"] == "mock"


def test_mock_geometry_backend_extraction_mode_field():
    result = MockGeometryBackend().extract_topology(b"unused")
    assert result["metadata"]["extraction_mode"] == "mock_generated"


def test_mock_geometry_backend_real_step_parsing_is_false():
    result = MockGeometryBackend().extract_topology(b"unused")
    assert result["metadata"]["real_step_parsing"] is False


def test_mock_geometry_backend_source_geometry_field():
    result = MockGeometryBackend().extract_topology(b"unused")
    assert result["metadata"]["source_geometry"] == "geometry/normalized.step"


def test_mock_geometry_backend_entities_present():
    result = MockGeometryBackend().extract_topology(b"unused")
    entity_ids = {e["id"] for e in result["entities"]}
    assert "body_001" in entity_ids
    assert "face_base_top" in entity_ids
    assert "face_hole_001_cyl" in entity_ids


def test_mock_geometry_backend_ignores_step_bytes():
    result_a = MockGeometryBackend().extract_topology(b"content a")
    result_b = MockGeometryBackend().extract_topology(b"content b")
    assert result_a["entities"] == result_b["entities"]


# ---------------------------------------------------------------------------
# OCCGeometryBackend
# ---------------------------------------------------------------------------

def test_occ_geometry_backend_raises_not_implemented():
    # When OCP is unavailable: NotImplementedError. When available but bytes are invalid STEP: ValueError.
    with pytest.raises((NotImplementedError, ValueError)):
        OCCGeometryBackend().extract_topology(b"unused")


# ---------------------------------------------------------------------------
# MockTopologyExtractor (legacy wrapper)
# ---------------------------------------------------------------------------

def test_mock_topology_extractor_delegates_to_mock_geometry_backend():
    result = MockTopologyExtractor().extract(b"unused")
    assert result["metadata"]["extraction_backend"] == "mock"


def test_occ_based_topology_extractor_delegates_not_implemented():
    # When OCP is unavailable: NotImplementedError. When available but bytes are invalid STEP: ValueError.
    with pytest.raises((NotImplementedError, ValueError)):
        OCCBasedTopologyExtractor().extract(b"unused")


# ---------------------------------------------------------------------------
# extract_topology_package backend parameter
# ---------------------------------------------------------------------------

def test_extract_topology_default_uses_mock_backend(tmp_path):
    package_path = imported_package(tmp_path)
    extract_topology_package(package_path)
    topology_map = read_topology_map(package_path)
    assert topology_map["metadata"]["extraction_backend"] == "mock"


def test_extract_topology_backend_mock_explicit(tmp_path):
    package_path = imported_package(tmp_path)
    extract_topology_package(package_path, backend="mock")
    topology_map = read_topology_map(package_path)
    assert topology_map["metadata"]["extraction_backend"] == "mock"
    assert topology_map["metadata"]["real_step_parsing"] is False


def test_extract_topology_backend_occ_raises_not_implemented(tmp_path):
    # When OCP is unavailable: NotImplementedError. When available but STEP is empty/invalid: ValueError.
    package_path = imported_package(tmp_path)
    with pytest.raises((NotImplementedError, ValueError)):
        extract_topology_package(package_path, backend="occ")


def test_extract_topology_backend_unknown_raises_value_error(tmp_path):
    package_path = imported_package(tmp_path)
    with pytest.raises(ValueError, match="Unknown geometry backend"):
        extract_topology_package(package_path, backend="bad_name")


def test_extract_topology_legacy_extractor_param_still_works(tmp_path):
    package_path = imported_package(tmp_path)
    extract_topology_package(package_path, extractor=MockTopologyExtractor())
    topology_map = read_topology_map(package_path)
    assert "body_001" in {e["id"] for e in topology_map["entities"]}


# ---------------------------------------------------------------------------
# CLI --backend flag
# ---------------------------------------------------------------------------

def test_cli_extract_topology_backend_mock_explicit(tmp_path, capsys):
    package_path = imported_package(tmp_path)
    assert main(["extract-topology", str(package_path), "--backend", "mock"]) == 0
    output = capsys.readouterr().out
    assert "PASS extracted mock topology" in output
    assert "PASS geometry/topology_map.json written" in output


def test_cli_extract_topology_backend_occ_returns_error(tmp_path, capsys):
    package_path = imported_package(tmp_path)
    assert main(["extract-topology", str(package_path), "--backend", "occ"]) == 2
    captured = capsys.readouterr()
    assert "FAIL" in captured.err
    assert "OCC" in captured.err


def test_cli_extract_topology_backend_unknown_returns_error(tmp_path, capsys):
    package_path = imported_package(tmp_path)
    assert main(["extract-topology", str(package_path), "--backend", "bad_name"]) == 2
    captured = capsys.readouterr()
    assert "FAIL" in captured.err
    assert "Unknown geometry backend" in captured.err


@pytest.mark.skipif(
    _OCC_AVAILABLE,
    reason="OCC runtime detected; CLI auto-backend selects occ, not mock — "
           "covered by test_cli_extract_topology_backend_occ_returns_error",
)
def test_cli_extract_topology_default_backend_is_mock(tmp_path, capsys):
    package_path = imported_package(tmp_path)
    assert main(["extract-topology", str(package_path)]) == 0
    import json
    with zipfile.ZipFile(package_path) as package:
        topology_map = json.loads(package.read(TOPOLOGY_MAP_PATH))
    assert topology_map["metadata"]["extraction_backend"] == "mock"
