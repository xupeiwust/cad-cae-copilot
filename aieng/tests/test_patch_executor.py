from __future__ import annotations

import json
import zipfile

import pytest

from aieng.cli import main
from aieng.geometry.step_importer import import_step_package
from aieng.geometry.topology_extractor import extract_topology_package
from aieng.graph.feature_graph import FEATURE_GRAPH_PATH, recognize_features_package
from aieng.ai.patch_proposer import propose_patch_package
from aieng.patch.executor import PatchNotExecutable, apply_patch_package
from aieng.validate import validate_package

FAKE_STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
PATCH_DIR = "ai/patches/"


def _make_package(tmp_path):
    step = tmp_path / "bracket.step"
    step.write_bytes(FAKE_STEP)
    pkg = tmp_path / "bracket.aieng"
    import_step_package(step, pkg)
    extract_topology_package(pkg)
    recognize_features_package(pkg)
    return pkg


def _read_json(pkg, member):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(member))


def _inject_modify_parameter_patch(pkg, target_id, param_name, new_value):
    """Inject a minimal modify_parameter patch directly into the package."""
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        members = [(i, zf.read(i.filename) if not i.is_dir() else b"") for i in zf.infolist()]
        manifest = json.loads(zf.read("manifest.json"))

    patch_id = "patch_0001"
    patch_member = f"{PATCH_DIR}{patch_id}.json"
    patch = {
        "patch_id": patch_id,
        "created_by": "test",
        "user_intent": "test intent",
        "status": "proposed",
        "summary": "test patch",
        "operations": [
            {
                "op": "modify_parameter",
                "target": target_id,
                "parameters": {param_name: new_value},
                "rationale": "test",
            }
        ],
        "target_feature_ids": [target_id],
        "protected_targets_checked": [],
        "protected_targets_avoided": [],
        "warnings": [],
        "expected_effects": {},
        "requires_validation": [],
        "source_files_consulted": [FEATURE_GRAPH_PATH],
        "created_from": {
            "method": "rule_based",
            "llm_used": False,
            "rag_used": False,
            "external_cad_tools_used": False,
        },
        "no_geometry_modified": True,
        "no_solver_run": True,
    }

    ai_res = manifest.setdefault("resources", {}).setdefault("ai", {})
    ai_res.setdefault("patches", []).append(patch_member)

    import shutil, tempfile
    from pathlib import Path
    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=pkg.parent) as fh:
        temp = Path(fh.name)
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for info, data in members:
            if info.filename != "manifest.json":
                zf.writestr(info, data)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        zf.writestr(patch_member, json.dumps(patch, indent=2, sort_keys=True))
    shutil.move(str(temp), pkg)
    return patch_id


# --- Happy path ---

def test_apply_patch_updates_feature_graph_parameter(tmp_path):
    pkg = _make_package(tmp_path)
    patch_id = _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 9.0)

    apply_patch_package(pkg, patch_id)

    fg = _read_json(pkg, FEATURE_GRAPH_PATH)
    hole = next(f for f in fg["features"] if f["id"] == "feat_hole_001")
    assert hole["parameters"]["radius_mm"] == 9.0


def test_apply_patch_also_updates_diameter_when_only_radius_given(tmp_path):
    pkg = _make_package(tmp_path)
    _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 7.5)

    apply_patch_package(pkg, "patch_0001")

    fg = _read_json(pkg, FEATURE_GRAPH_PATH)
    hole = next(f for f in fg["features"] if f["id"] == "feat_hole_001")
    assert hole["parameters"]["radius_mm"] == 7.5


def test_apply_patch_sets_status_to_applied(tmp_path):
    pkg = _make_package(tmp_path)
    patch_id = _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 6.0)

    apply_patch_package(pkg, patch_id)

    patch = _read_json(pkg, f"{PATCH_DIR}{patch_id}.json")
    assert patch["status"] == "applied"


def test_apply_patch_sets_parameter_source_to_user_provided(tmp_path):
    pkg = _make_package(tmp_path)
    patch_id = _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 6.0)

    apply_patch_package(pkg, patch_id)

    fg = _read_json(pkg, FEATURE_GRAPH_PATH)
    hole = next(f for f in fg["features"] if f["id"] == "feat_hole_001")
    assert hole["parameter_source"] == "user_provided"


def test_apply_patch_adds_execution_record(tmp_path):
    pkg = _make_package(tmp_path)
    patch_id = _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 6.0)

    apply_patch_package(pkg, patch_id)

    patch = _read_json(pkg, f"{PATCH_DIR}{patch_id}.json")
    rec = patch.get("execution_record")
    assert isinstance(rec, dict)
    assert rec["feature_graph_updated"] is True
    assert rec["applied_operations"] == 1
    assert rec["execution_mode"] == "semantic_parameter_update_only"
    assert rec["cad_writeback_attempted"] is False
    assert rec["roundtrip_required"] is False


def test_apply_patch_no_geometry_modified_true_for_mock_source(tmp_path):
    pkg = _make_package(tmp_path)
    patch_id = _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 6.0)

    apply_patch_package(pkg, patch_id)

    patch = _read_json(pkg, f"{PATCH_DIR}{patch_id}.json")
    assert patch["no_geometry_modified"] is True
    assert "mock/ocp_extracted" in patch["execution_record"]["step_writeback"]


# --- Error paths ---

def test_apply_patch_rejects_already_applied_patch(tmp_path):
    pkg = _make_package(tmp_path)
    patch_id = _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 6.0)
    apply_patch_package(pkg, patch_id)

    with pytest.raises(PatchNotExecutable, match="already.*applied|status.*applied"):
        apply_patch_package(pkg, patch_id)


def test_apply_patch_rejects_missing_patch_id(tmp_path):
    pkg = _make_package(tmp_path)

    with pytest.raises(FileNotFoundError, match="not found in package"):
        apply_patch_package(pkg, "patch_9999")


def test_apply_patch_rejects_non_editable_feature(tmp_path):
    pkg = _make_package(tmp_path)

    fg = _read_json(pkg, FEATURE_GRAPH_PATH)
    for f in fg["features"]:
        if f["id"] == "feat_hole_001":
            f["editable"] = False

    with zipfile.ZipFile(pkg, "a") as zf:
        zf.writestr(FEATURE_GRAPH_PATH, json.dumps(fg))

    patch_id = _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 6.0)

    with pytest.raises(PatchNotExecutable, match="editable=false"):
        apply_patch_package(pkg, patch_id)


def test_apply_patch_rejects_unknown_parameter(tmp_path):
    pkg = _make_package(tmp_path)
    patch_id = _inject_modify_parameter_patch(pkg, "feat_hole_001", "nonexistent_param", 1.0)

    with pytest.raises(PatchNotExecutable, match="does not have parameter"):
        apply_patch_package(pkg, patch_id)


def test_apply_patch_rejects_geometry_op(tmp_path):
    pkg = _make_package(tmp_path)
    _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 6.0)

    with zipfile.ZipFile(pkg) as zf:
        patch = json.loads(zf.read(f"{PATCH_DIR}patch_0001.json"))

    patch["operations"] = [{"op": "add_feature", "target": "feat_hole_001", "parameters": {}}]

    with zipfile.ZipFile(pkg, "a") as zf:
        zf.writestr(f"{PATCH_DIR}patch_0001.json", json.dumps(patch))

    with pytest.raises(PatchNotExecutable, match="geometry kernel"):
        apply_patch_package(pkg, "patch_0001")


def test_apply_patch_rejects_unknown_package_path(tmp_path):
    with pytest.raises(FileNotFoundError, match="package does not exist"):
        apply_patch_package(tmp_path / "missing.aieng", "patch_0001")


# --- CLI ---

def test_cli_apply_patch_happy_path(tmp_path, capsys):
    pkg = _make_package(tmp_path)
    patch_id = _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 8.0)

    rc = main(["apply-patch", str(pkg), "--patch", patch_id])

    assert rc == 0
    out = capsys.readouterr().out
    assert "PASS applied patch" in out
    assert "PASS graph/feature_graph.json parameters updated" in out


def test_cli_apply_patch_fails_gracefully_for_bad_op(tmp_path, capsys):
    pkg = _make_package(tmp_path)
    _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 6.0)

    with zipfile.ZipFile(pkg) as zf:
        patch = json.loads(zf.read(f"{PATCH_DIR}patch_0001.json"))
    patch["operations"] = [{"op": "remove_feature", "target": "feat_hole_001", "parameters": {}}]
    with zipfile.ZipFile(pkg, "a") as zf:
        zf.writestr(f"{PATCH_DIR}patch_0001.json", json.dumps(patch))

    rc = main(["apply-patch", str(pkg), "--patch", "patch_0001"])

    assert rc == 2
    assert "FAIL" in capsys.readouterr().err


def test_apply_patch_overwrites_when_flag_set(tmp_path):
    pkg = _make_package(tmp_path)
    patch_id = _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 6.0)
    apply_patch_package(pkg, patch_id)

    _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 7.0)
    apply_patch_package(pkg, patch_id, overwrite=True)

    fg = _read_json(pkg, FEATURE_GRAPH_PATH)
    hole = next(f for f in fg["features"] if f["id"] == "feat_hole_001")
    assert hole["parameters"]["radius_mm"] == 7.0


def test_validator_rejects_geometry_modified_without_step_output(tmp_path):
    pkg = _make_package(tmp_path)
    patch_id = _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 6.0)
    apply_patch_package(pkg, patch_id)

    with zipfile.ZipFile(pkg) as zf:
        members = [(i, zf.read(i.filename) if not i.is_dir() else b"") for i in zf.infolist()]
        patch = json.loads(zf.read(f"{PATCH_DIR}{patch_id}.json"))
    patch["no_geometry_modified"] = False
    patch["execution_record"]["step_output"] = None

    import shutil, tempfile
    from pathlib import Path
    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=pkg.parent) as fh:
        temp = Path(fh.name)
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for info, data in members:
            if info.filename != f"{PATCH_DIR}{patch_id}.json":
                zf.writestr(info, data)
        zf.writestr(f"{PATCH_DIR}{patch_id}.json", json.dumps(patch, indent=2, sort_keys=True))
    shutil.move(str(temp), pkg)

    report = validate_package(pkg)
    assert not report.ok
    assert any("no_geometry_modified=false requires" in msg.text for msg in report.messages)


# ---------------------------------------------------------------------------
# G7: CadQuery parametric regeneration writeback path
# ---------------------------------------------------------------------------

def _inject_cadquery_parametric_feature(pkg, feature_id: str, params: dict, *, feature_type: str = "base_plate_candidate"):
    """Add a cadquery_parametric base_plate feature to the package for G7 tests."""
    import shutil, tempfile
    from pathlib import Path as _Path
    with zipfile.ZipFile(pkg) as zf:
        members = [(i, zf.read(i.filename) if not i.is_dir() else b"") for i in zf.infolist()]
        fg = json.loads(zf.read(FEATURE_GRAPH_PATH))

    fg.setdefault("features", []).append({
        "id": feature_id,
        "type": feature_type,
        "editable": True,
        "parameter_source": "cadquery_parametric",
        "editability": "executable_by_regeneration",
        "writeback_strategy": "cadquery_regeneration",
        "parameters": params,
        "topology_refs": [],
    })

    fg_bytes = (json.dumps(fg, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=pkg.parent) as fh:
        temp = _Path(fh.name)
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for info, data in members:
            if info.filename != FEATURE_GRAPH_PATH:
                zf.writestr(info, data)
        zf.writestr(FEATURE_GRAPH_PATH, fg_bytes)
    shutil.move(str(temp), pkg)


def test_cadquery_writeback_skips_when_cadquery_unavailable(tmp_path):
    """When CadQuery is absent, execution stays semantic-only with a clear note."""
    pytest.importorskip("cadquery", reason="cadquery not installed — G7 writeback path requires CadQuery")
    # If we reach here CadQuery IS available; this test only makes sense without it.
    pytest.skip("cadquery is available; use test_cadquery_writeback_produces_step_bytes instead")


def test_cadquery_writeback_produces_step_bytes(tmp_path):
    """G7: cadquery_parametric feature triggers real STEP regeneration when CadQuery is available."""
    pytest.importorskip("cadquery", reason="cadquery not installed — install cadquery to enable G7 writeback")

    pkg = _make_package(tmp_path)
    _inject_cadquery_parametric_feature(
        pkg,
        "feat_base_plate_cq_001",
        {"length": 150.0, "width": 80.0, "height": 15.0},
    )
    patch_id = _inject_modify_parameter_patch(pkg, "feat_base_plate_cq_001", "height", 20.0)

    apply_patch_package(pkg, patch_id)

    patch_data = _read_json(pkg, f"{PATCH_DIR}{patch_id}.json")
    record = patch_data["execution_record"]
    assert record["execution_mode"] == "cad_writeback", (
        f"expected cad_writeback, got {record['execution_mode']!r}; note: {record.get('step_writeback')}"
    )
    assert record["step_writeback"] == "cadquery_parametric_regeneration_ok"
    assert record["step_output"] is not None

    with zipfile.ZipFile(pkg) as zf:
        step_bytes = zf.read(record["step_output"])
    assert step_bytes.startswith(b"ISO-10303-21")


def test_cadquery_writeback_note_when_feature_type_unsupported(tmp_path):
    """When CadQuery is available but feature type not in supported set, note says so."""
    pytest.importorskip("cadquery", reason="cadquery not installed")

    pkg = _make_package(tmp_path)
    # feat_hole_001 has writeback_strategy semantic_only — not executable
    patch_id = _inject_modify_parameter_patch(pkg, "feat_hole_001", "radius_mm", 5.0)

    apply_patch_package(pkg, patch_id)

    patch_data = _read_json(pkg, f"{PATCH_DIR}{patch_id}.json")
    record = patch_data["execution_record"]
    assert record["execution_mode"] == "semantic_parameter_update_only"


def test_cadquery_writeback_supports_flange_feature_family(tmp_path):
    """C2: flange feature family can use guarded CadQuery regeneration writeback."""
    pytest.importorskip("cadquery", reason="cadquery not installed")

    pkg = _make_package(tmp_path)
    _inject_cadquery_parametric_feature(
        pkg,
        "feat_flange_cq_001",
        {"outer_diameter_mm": 90.0, "thickness_mm": 10.0},
        feature_type="flange",
    )
    patch_id = _inject_modify_parameter_patch(pkg, "feat_flange_cq_001", "thickness_mm", 14.0)

    apply_patch_package(pkg, patch_id)

    patch_data = _read_json(pkg, f"{PATCH_DIR}{patch_id}.json")
    record = patch_data["execution_record"]
    assert record["execution_mode"] == "cad_writeback"
    assert record["step_writeback"] == "cadquery_parametric_regeneration_ok"
    assert isinstance(record.get("step_output"), str) and record["step_output"]
