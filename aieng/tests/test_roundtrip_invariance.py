"""G8: Roundtrip invariance tests.

Verifies that the core semantic pipeline
  CAD artifact -> .aieng package -> apply-patch -> CAD writeback
preserves parameter semantics and produces a stable, auditable trail.

Tests in this file require CadQuery and are automatically skipped
when CadQuery is not installed.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from aieng.package import create_package
from aieng.graph.feature_graph import FEATURE_GRAPH_PATH
from aieng.patch.executor import apply_patch_package

PATCH_DIR = "ai/patches/"
FAKE_STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cq_package(tmp_path: Path) -> Path:
    """Create a minimal package with a cadquery_parametric base_plate feature."""
    step = tmp_path / "model.step"
    step.write_bytes(FAKE_STEP)

    pkg = tmp_path / "model.aieng"
    create_package("roundtrip_model", pkg)

    # Inject geometry and a cadquery_parametric feature graph
    feature_graph = {
        "format_version": "0.1.0",
        "model_id": "roundtrip_model",
        "features": [
            {
                "id": "feat_base_plate_cq_001",
                "type": "base_plate_candidate",
                "editable": True,
                "parameter_source": "cadquery_parametric",
                "editability": "executable_by_regeneration",
                "writeback_strategy": "cadquery_regeneration",
                "parameters": {
                    "length": 200.0,
                    "width": 100.0,
                    "height": 20.0,
                },
                "topology_refs": [],
            }
        ],
    }
    patch = {
        "patch_id": "patch_0001",
        "created_by": "test",
        "user_intent": "increase height to 30mm",
        "status": "proposed",
        "summary": "set height to 30",
        "operations": [
            {
                "op": "modify_parameter",
                "target": "feat_base_plate_cq_001",
                "parameters": {"height": 30.0},
                "rationale": "roundtrip test",
            }
        ],
        "target_feature_ids": ["feat_base_plate_cq_001"],
        "protected_targets_checked": [],
        "protected_targets_avoided": [],
        "warnings": [],
        "expected_effects": {},
        "requires_validation": [],
        "source_files_consulted": [FEATURE_GRAPH_PATH],
        "created_from": {"method": "rule_based", "llm_used": False, "rag_used": False, "external_cad_tools_used": False},
        "no_geometry_modified": True,
        "no_solver_run": True,
    }

    import shutil, tempfile
    with zipfile.ZipFile(pkg) as zf:
        members = [(i, zf.read(i.filename) if not i.is_dir() else b"") for i in zf.infolist()]
        manifest = json.loads(zf.read("manifest.json"))

    manifest.setdefault("resources", {}).setdefault("geometry", {})["source_step"] = "geometry/source.step"
    manifest["resources"].setdefault("ai", {}).setdefault("patches", []).append(f"{PATCH_DIR}patch_0001.json")
    manifest["resources"]["graph"] = {"feature_graph": FEATURE_GRAPH_PATH}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=tmp_path) as fh:
        temp = Path(fh.name)
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for info, data in members:
            if info.filename not in {"manifest.json"}:
                zf.writestr(info, data)
        zf.writestr("manifest.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
        zf.writestr(FEATURE_GRAPH_PATH, (json.dumps(feature_graph, indent=2, sort_keys=True) + "\n").encode())
        zf.writestr("geometry/source.step", FAKE_STEP)
        zf.writestr(f"{PATCH_DIR}patch_0001.json", (json.dumps(patch, indent=2, sort_keys=True) + "\n").encode())
    shutil.move(str(temp), pkg)
    return pkg


def _read_json(pkg: Path, member: str) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(member))


def _member_exists(pkg: Path, member: str) -> bool:
    with zipfile.ZipFile(pkg) as zf:
        return member in zf.namelist()


# ---------------------------------------------------------------------------
# Roundtrip invariance tests
# ---------------------------------------------------------------------------

def test_roundtrip_requires_cadquery(tmp_path: Path):
    pytest.importorskip("cadquery", reason="G8 roundtrip requires CadQuery")


def test_roundtrip_parameter_preserved_in_feature_graph(tmp_path: Path):
    """After patch, the updated parameter value is stable in feature_graph.json."""
    pytest.importorskip("cadquery", reason="G8 roundtrip requires CadQuery")
    pkg = _make_cq_package(tmp_path)

    apply_patch_package(pkg, "patch_0001")

    fg = _read_json(pkg, FEATURE_GRAPH_PATH)
    feature = next(f for f in fg["features"] if f["id"] == "feat_base_plate_cq_001")
    assert feature["parameters"]["height"] == 30.0, "height parameter must survive roundtrip unchanged"
    assert feature["parameters"]["length"] == 200.0, "unmodified length must not drift"
    assert feature["parameters"]["width"] == 100.0, "unmodified width must not drift"


def test_roundtrip_produces_step_artifact(tmp_path: Path):
    """Roundtrip must produce a geometry artifact inside the package."""
    pytest.importorskip("cadquery", reason="G8 roundtrip requires CadQuery")
    pkg = _make_cq_package(tmp_path)

    apply_patch_package(pkg, "patch_0001")

    patch_data = _read_json(pkg, f"{PATCH_DIR}patch_0001.json")
    step_member = patch_data["execution_record"]["step_output"]
    assert step_member is not None, "step_output must be recorded in execution_record"
    assert _member_exists(pkg, step_member), f"STEP artifact {step_member!r} must exist in package"

    with zipfile.ZipFile(pkg) as zf:
        step_bytes = zf.read(step_member)
    assert step_bytes.startswith(b"ISO-10303-21"), "STEP artifact must be valid ISO-10303-21 content"


def test_roundtrip_execution_record_is_complete(tmp_path: Path):
    """execution_record must carry all required audit fields after writeback."""
    pytest.importorskip("cadquery", reason="G8 roundtrip requires CadQuery")
    pkg = _make_cq_package(tmp_path)

    apply_patch_package(pkg, "patch_0001")

    record = _read_json(pkg, f"{PATCH_DIR}patch_0001.json")["execution_record"]
    assert record["execution_mode"] == "cad_writeback"
    assert record["feature_graph_updated"] is True
    assert record["cad_writeback_attempted"] is True
    assert record["step_writeback"] == "cadquery_parametric_regeneration_ok"
    assert record["roundtrip_required"] is True


def test_roundtrip_patch_status_is_applied(tmp_path: Path):
    """Patch status must be 'applied' after successful execution."""
    pytest.importorskip("cadquery", reason="G8 roundtrip requires CadQuery")
    pkg = _make_cq_package(tmp_path)

    apply_patch_package(pkg, "patch_0001")

    patch_data = _read_json(pkg, f"{PATCH_DIR}patch_0001.json")
    assert patch_data["status"] == "applied"



def test_roundtrip_source_step_unchanged(tmp_path: Path):
    """Roundtrip must not overwrite geometry/source.step — only modified_* is written."""
    pytest.importorskip("cadquery", reason="G8 roundtrip requires CadQuery")
    pkg = _make_cq_package(tmp_path)

    with zipfile.ZipFile(pkg) as zf:
        source_before = zf.read("geometry/source.step")

    apply_patch_package(pkg, "patch_0001")

    with zipfile.ZipFile(pkg) as zf:
        source_after = zf.read("geometry/source.step")

    assert source_before == source_after, "geometry/source.step must be immutable across patch execution"
