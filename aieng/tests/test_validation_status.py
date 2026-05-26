"""Tests for Phase 6B: validation/status.yaml generation and validation."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
import yaml

from aieng.cli import main
from aieng.package import create_package
from aieng.validate import validate_package
from aieng.validation.status_writer import (
    ALLOWED_CLAIMS,
    FORBIDDEN_CLAIMS,
    STATUS_PATH,
    VALIDATION_DIR,
    update_validation_status_package,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_package(tmp_path: Path, model_id: str = "test_model") -> Path:
    pkg = tmp_path / f"{model_id}.aieng"
    create_package(model_id, pkg)
    return pkg


def _read_status(pkg: Path) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return yaml.safe_load(zf.read(STATUS_PATH))


def _read_manifest(pkg: Path) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read("manifest.json"))


def _add_file_to_package(pkg: Path, name: str, content: bytes | str) -> None:
    """Append a file to an existing zip package."""
    if isinstance(content, str):
        content = content.encode()
    with zipfile.ZipFile(pkg, mode="a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, content)


# ---------------------------------------------------------------------------
# Basic contract
# ---------------------------------------------------------------------------

def test_update_validation_status_returns_package_path(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    result = update_validation_status_package(pkg)
    assert result == pkg


def test_update_validation_status_creates_status_file(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    with zipfile.ZipFile(pkg) as zf:
        assert STATUS_PATH in zf.namelist()


def test_update_validation_status_creates_validation_dir_entry(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    with zipfile.ZipFile(pkg) as zf:
        assert VALIDATION_DIR in zf.namelist()


def test_update_validation_status_registers_in_manifest(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    manifest = _read_manifest(pkg)
    assert manifest["resources"]["validation"]["status"] == STATUS_PATH


def test_status_yaml_is_valid_yaml(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert isinstance(status, dict)


# ---------------------------------------------------------------------------
# Required sections
# ---------------------------------------------------------------------------

def test_status_contains_all_required_top_level_sections(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    required = {
        "generated_by",
        "model_id",
        "package_format_version",
        "generated_at",
        "package_validation",
        "geometry_status",
        "topology_status",
        "feature_status",
        "engineering_context_status",
        "solver_mesh_status",
        "patch_status",
        "claim_policy",
    }
    missing = required - set(status.keys())
    assert not missing, f"Missing sections: {missing}"


def test_status_generated_by_contains_aieng(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert "aieng" in status["generated_by"]


def test_status_model_id_matches_manifest(tmp_path):
    pkg = _make_minimal_package(tmp_path, model_id="my_model")
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert status["model_id"] == "my_model"


def test_status_generated_at_is_utc_iso_string(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    ts = status["generated_at"]
    assert isinstance(ts, str)
    assert ts.endswith("Z"), f"expected UTC timestamp ending in Z, got {ts!r}"


# ---------------------------------------------------------------------------
# Claim policy
# ---------------------------------------------------------------------------

def test_status_forbidden_claims_matches_module_constant(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert status["claim_policy"]["forbidden_claims"] == FORBIDDEN_CLAIMS


def test_status_allowed_claims_matches_module_constant(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert status["claim_policy"]["allowed_claims"] == ALLOWED_CLAIMS


def test_forbidden_claims_does_not_include_safe_is_validated(tmp_path):
    """The design-is-safe claim must be forbidden."""
    assert any("safe" in c.lower() for c in FORBIDDEN_CLAIMS)


def test_allowed_claims_does_not_include_solver_ran():
    """No allowed claim should assert that a solver ran."""
    for claim in ALLOWED_CLAIMS:
        assert "solver" not in claim.lower() or "scaffold" in claim.lower()


# ---------------------------------------------------------------------------
# Presence flags reflect actual package contents
# ---------------------------------------------------------------------------

def test_geometry_flags_false_for_minimal_package(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert status["geometry_status"]["source_geometry_present"] is False
    assert status["geometry_status"]["normalized_geometry_present"] is False


def test_geometry_flags_true_when_step_files_present(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "geometry/source.step", b"STEP file content")
    _add_file_to_package(pkg, "geometry/normalized.step", b"STEP file content")
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert status["geometry_status"]["source_geometry_present"] is True
    assert status["geometry_status"]["normalized_geometry_present"] is True


def test_topology_status_not_generated_when_missing(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert status["topology_status"]["topology_map_present"] is False
    assert status["topology_status"]["status"] == "not_generated"


def test_topology_status_mock_generated_when_present(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "geometry/topology_map.json", b'{"entities": []}')
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert status["topology_status"]["topology_map_present"] is True
    assert status["topology_status"]["extraction_mode"] == "mock"
    assert status["topology_status"]["status"] == "mock_generated"


def test_feature_status_candidate_only_when_feature_graph_present(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "graph/feature_graph.json", b'{"features": []}')
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert status["feature_status"]["feature_graph_present"] is True
    assert status["feature_status"]["status"] == "candidate_only"
    assert status["feature_status"]["recognition_mode"] == "rule_based"


def test_solver_mesh_status_all_not_run(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    sm = status["solver_mesh_status"]
    assert sm["mesh_generation"] == "not_run"
    assert sm["solver_execution"] == "not_run"
    assert sm["stress_validation"] == "not_validated"
    assert sm["displacement_validation"] == "not_validated"
    assert sm["manufacturing_validation"] == "not_run"


def test_patch_status_no_patches_present_for_minimal(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    ps = status["patch_status"]
    assert ps["patch_proposals_present"] is False
    assert ps["patch_execution"] == "not_run"
    assert ps["geometry_modified_by_patch"] is False
    assert ps["solver_run_for_patch"] is False
    assert ps["patch_validation_required"] is False


# ---------------------------------------------------------------------------
# Overwrite behaviour
# ---------------------------------------------------------------------------

def test_raises_file_exists_error_without_overwrite(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    with pytest.raises(FileExistsError, match="already exists"):
        update_validation_status_package(pkg)


def test_overwrite_flag_replaces_existing_status(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    update_validation_status_package(pkg, overwrite=True)
    status = _read_status(pkg)
    assert "generated_by" in status


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_raises_file_not_found_for_missing_package(tmp_path):
    with pytest.raises(FileNotFoundError):
        update_validation_status_package(tmp_path / "nonexistent.aieng")


def test_raises_value_error_for_wrong_extension(tmp_path):
    wrong = tmp_path / "package.zip"
    wrong.write_bytes(b"")
    with pytest.raises(ValueError, match=".aieng"):
        update_validation_status_package(wrong)


def test_raises_value_error_for_missing_manifest(tmp_path):
    pkg = tmp_path / "no_manifest.aieng"
    with zipfile.ZipFile(pkg, mode="w") as zf:
        zf.writestr("geometry/", b"")
    with pytest.raises(ValueError, match="manifest.json"):
        update_validation_status_package(pkg)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

def test_cli_update_validation_status_exits_zero(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    rc = main(["update-validation-status", str(pkg)])
    assert rc == 0


def test_cli_update_validation_status_prints_pass(tmp_path, capsys):
    pkg = _make_minimal_package(tmp_path)
    main(["update-validation-status", str(pkg)])
    out = capsys.readouterr().out
    assert "PASS" in out
    assert "validation/status.yaml" in out


def test_cli_fails_without_overwrite_on_existing(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    main(["update-validation-status", str(pkg)])
    rc = main(["update-validation-status", str(pkg)])
    assert rc != 0


def test_cli_overwrite_flag_succeeds(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    main(["update-validation-status", str(pkg)])
    rc = main(["update-validation-status", "--overwrite", str(pkg)])
    assert rc == 0


# ---------------------------------------------------------------------------
# Validator integration
# ---------------------------------------------------------------------------

def test_validate_reports_pass_for_status_when_manifest_references_it(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    report = validate_package(pkg)
    rendered = report.render()
    assert "validation/status.yaml is valid YAML" in rendered


def test_validate_reports_pass_for_required_sections(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    report = validate_package(pkg)
    rendered = report.render()
    assert "all required sections" in rendered


def test_validate_reports_pass_for_solver_mesh_status_no_claims(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    report = validate_package(pkg)
    rendered = report.render()
    assert "does not claim solver execution" in rendered


def test_validate_reports_pass_for_no_geometry_modification(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    report = validate_package(pkg)
    rendered = report.render()
    assert "no geometry modification" in rendered


def test_validate_does_not_check_status_when_not_in_manifest(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, STATUS_PATH, b"generated_by: manual")
    report = validate_package(pkg)
    rendered = report.render()
    assert "validation/status.yaml is valid YAML" not in rendered


def test_validate_fails_for_status_with_false_solver_claim(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    update_validation_status_package(pkg)
    manifest = _read_manifest(pkg)
    bad_status = {
        "generated_by": "aieng test",
        "model_id": "test",
        "package_format_version": "0.1.0",
        "generated_at": "2026-01-01T00:00:00Z",
        "package_validation": {},
        "geometry_status": {},
        "topology_status": {},
        "feature_status": {},
        "engineering_context_status": {},
        "solver_mesh_status": {
            "mesh_generation": "done",
            "solver_execution": "done",
            "stress_validation": "validated",
        },
        "patch_status": {"geometry_modified_by_patch": False, "solver_run_for_patch": False},
        "claim_policy": {"allowed_claims": ["ok"], "forbidden_claims": ["bad"]},
    }
    bad_yaml = yaml.safe_dump(bad_status)
    import shutil
    import tempfile
    with zipfile.ZipFile(pkg, mode="r") as zf:
        members = [(info, b"" if info.is_dir() else zf.read(info.filename)) for info in zf.infolist()
                   if info.filename not in {STATUS_PATH, "manifest.json"}]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=pkg.parent) as fh:
        tmp = Path(fh.name)
    with zipfile.ZipFile(tmp, mode="w", compression=zipfile.ZIP_DEFLATED) as out:
        for info, data in members:
            out.writestr(info, data)
        out.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        out.writestr(STATUS_PATH, bad_yaml)
    shutil.move(str(tmp), pkg)

    report = validate_package(pkg)
    rendered = report.render()
    assert "FAIL" in rendered
    assert "unsupported claims" in rendered


# ---------------------------------------------------------------------------
# Phase 7B.2 stabilization: topology_status reflects mock vs OCP metadata
# ---------------------------------------------------------------------------

def _make_topology_map_json(metadata: dict) -> bytes:
    """Build minimal topology_map.json bytes with the given metadata dict."""
    import json as _json
    return _json.dumps({
        "format_version": "0.1.0",
        "metadata": metadata,
        "entities": [{"id": "body_001", "type": "solid"}],
    }).encode()


_MOCK_METADATA = {
    "extraction_backend": "mock",
    "extraction_mode": "mock_generated",
    "real_step_parsing": False,
    "source_geometry": "geometry/normalized.step",
}

_OCP_METADATA = {
    "extraction_backend": "occ",
    "runtime_provider": "OCP",
    "extraction_mode": "parsed_from_step",
    "real_step_parsing": True,
    "source_geometry": "geometry/normalized.step",
    "phase": "7B.2",
    "limitations": ["experimental"],
}


def test_topology_status_mock_when_metadata_says_mock(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "geometry/topology_map.json", _make_topology_map_json(_MOCK_METADATA))
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    ts = status["topology_status"]
    assert ts["topology_map_present"] is True
    assert ts["extraction_mode"] == "mock"
    assert ts["status"] == "mock_generated"


def test_topology_status_ocp_when_metadata_says_real_parsing(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "geometry/topology_map.json", _make_topology_map_json(_OCP_METADATA))
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    ts = status["topology_status"]
    assert ts["topology_map_present"] is True
    assert ts["extraction_mode"] == "parsed_from_step"
    assert ts["status"] == "experimental_real_extraction"


def test_topology_status_ocp_sets_real_step_parsing_true(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "geometry/topology_map.json", _make_topology_map_json(_OCP_METADATA))
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert status["topology_status"]["real_step_parsing"] is True


def test_topology_status_ocp_includes_runtime_provider(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "geometry/topology_map.json", _make_topology_map_json(_OCP_METADATA))
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert status["topology_status"]["runtime_provider"] == "OCP"


def test_topology_status_ocp_extraction_backend_is_occ(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "geometry/topology_map.json", _make_topology_map_json(_OCP_METADATA))
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert status["topology_status"]["extraction_backend"] == "occ"


def test_topology_status_ocp_warning_says_not_certified(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "geometry/topology_map.json", _make_topology_map_json(_OCP_METADATA))
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    warning = status["topology_status"]["warning"].lower()
    assert "review-required" in warning or "not been independently established" in warning


def test_topology_status_ocp_warning_says_experimental(tmp_path):
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "geometry/topology_map.json", _make_topology_map_json(_OCP_METADATA))
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert "experimental" in status["topology_status"]["warning"].lower()


def test_topology_status_mock_when_topology_has_no_metadata(tmp_path):
    """A topology_map.json with no metadata block defaults to mock_generated."""
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "geometry/topology_map.json", b'{"format_version":"0.1.0","entities":[]}')
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    ts = status["topology_status"]
    assert ts["extraction_mode"] == "mock"
    assert ts["status"] == "mock_generated"


def test_topology_status_mock_when_real_step_parsing_is_false(tmp_path):
    """real_step_parsing: false with any backend → mock_generated."""
    meta = {**_OCP_METADATA, "real_step_parsing": False}
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "geometry/topology_map.json", _make_topology_map_json(meta))
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    assert status["topology_status"]["status"] == "mock_generated"


def test_topology_status_ocp_does_not_claim_geometry_valid(tmp_path):
    """OCP topology status must not assert geometry has been certified."""
    pkg = _make_minimal_package(tmp_path)
    _add_file_to_package(pkg, "geometry/topology_map.json", _make_topology_map_json(_OCP_METADATA))
    update_validation_status_package(pkg)
    status = _read_status(pkg)
    # geometry_status must still say not_run
    geo = status["geometry_status"]
    assert geo["real_geometry_parsing"] == "not_run"
    assert geo["real_geometry_validity"] == "not_run"


def test_forbidden_claims_includes_feature_labels_claim():
    """Feature labels confirmed as engineering truth must be a forbidden claim."""
    assert any("feature labels" in c.lower() or "confirmed engineering truth" in c.lower()
               for c in FORBIDDEN_CLAIMS)


def test_allowed_claims_includes_experimental_backend_claim():
    """ALLOWED_CLAIMS must include the conditional OCP real_step_parsing claim."""
    assert any("experimental backend" in c.lower() or "real_step_parsing" in c.lower()
               for c in ALLOWED_CLAIMS)
