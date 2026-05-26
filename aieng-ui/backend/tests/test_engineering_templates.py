"""Tests for parametric CAD + FEA setup template authoring (v0.34).

Cover the safety contract:
  - preview is read-only;
  - save-draft writes only the four declared draft artifacts;
  - missing / invalid parameters return structured errors (not 500s);
  - unknown parameters surface as ignored warnings;
  - the generated CAD script preview carries the explicit safety header;
  - the FEA setup draft carries ``claim_advancement: "none"``;
  - save-draft never overwrites ``task/design_targets.yaml`` or any other
    non-draft package member;
  - save-draft never runs a subprocess.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.config import Settings
from app.engineering_templates import (
    DRAFT_CAD_SCRIPT_PATH,
    DRAFT_FEA_SETUP_PATH,
    DRAFT_MANIFEST_PATH,
    DRAFT_TARGET_SUGGESTIONS_PATH,
    GENERATED_CAD_FIXTURE_PATH,
    PROTECTED_PATHS,
    TEMPLATE_IDS,
)
from app.project_io import REVALIDATION_STATUS_PATH

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def _make_settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=workspace,
        data_root=tmp_path / "data",
        aieng_root=_WORKSPACE_ROOT / "aieng",
        sample_step=workspace / "sample.step",
    )


def _make_project(settings: Settings, name: str, package: str) -> tuple[str, Path]:
    from app.main import default_project, project_dir, save_project

    project = save_project(settings, default_project(name))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / package
    project["aieng_file"] = package
    save_project(settings, project)
    return project_id, pkg_path


def _make_minimal_package(pkg: Path, *, existing_targets: dict[str, Any] | None = None) -> None:
    pkg.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "tmpl-test", "resources": {}}))
        if existing_targets is not None:
            zf.writestr("task/design_targets.yaml", yaml.safe_dump(existing_targets, sort_keys=False))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _members(pkg: Path) -> set[str]:
    with zipfile.ZipFile(pkg, "r") as zf:
        return set(zf.namelist())


# ── list + detail ────────────────────────────────────────────────────────────


def test_list_engineering_templates_returns_known_ids(tmp_path: Path) -> None:
    client = TestClient(create_app(_make_settings(tmp_path)))
    resp = client.get("/api/engineering-templates")
    assert resp.status_code == 200
    body = resp.json()
    ids = {t["id"] for t in body["templates"]}
    assert {"cantilever_beam", "plate_with_hole"} <= ids
    assert body["claim_advancement"] == "none"
    assert body["claim_boundary"]


def test_get_engineering_template_detail_returns_parameter_schema(tmp_path: Path) -> None:
    client = TestClient(create_app(_make_settings(tmp_path)))
    resp = client.get("/api/engineering-templates/cantilever_beam")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "cantilever_beam"
    param_ids = {p["id"] for p in body["parameters"]}
    assert {"length_mm", "width_mm", "height_mm", "material", "tip_load_N"} <= param_ids
    assert any(p["kind"] == "select" and p["id"] == "material" for p in body["parameters"])
    assert any(m["id"] == "aluminum_6061_t6" for m in body["materials"])
    assert body["claim_boundary"]


def test_get_unknown_template_returns_404(tmp_path: Path) -> None:
    client = TestClient(create_app(_make_settings(tmp_path)))
    resp = client.get("/api/engineering-templates/no_such_template")
    assert resp.status_code == 404


# ── preview is read-only ─────────────────────────────────────────────────────


def test_preview_cantilever_beam_with_defaults(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "preview-cb", "p.aieng")
    _make_minimal_package(pkg)
    before = _digest(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/preview",
        json={"parameters": {}},
    )
    assert resp.status_code == 200, resp.text
    assert _digest(pkg) == before, "preview must not mutate the package"

    body = resp.json()
    assert body["ok"] is True
    assert body["errors"] == []
    assert body["parameters"]["length_mm"] == 200.0
    assert body["parameters"]["material"] == "aluminum_6061_t6"
    assert body["claim_advancement"] == "none"
    assert body["claim_boundary"]
    assert body["safety_note"]
    assert "Generated draft only. Not executed by AIENG" in body["cad_script_preview"]
    assert body["fea_setup_draft"]["claim_advancement"] == "none"
    assert any(s["metric"] == "max_von_mises_stress" for s in body["design_target_suggestions"])
    assert any(s["metric"] == "max_displacement" for s in body["design_target_suggestions"])


def test_preview_plate_with_hole_with_overrides(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "preview-pwh", "p.aieng")
    _make_minimal_package(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/plate_with_hole/preview",
        json={"parameters": {
            "length_mm": 300.0,
            "width_mm": 150.0,
            "thickness_mm": 6.0,
            "hole_diameter_mm": 25.0,
            "material": "steel_s235",
            "tensile_load_N": 8000.0,
            "allowable_stress_MPa": 180.0,
        }},
    )
    body = resp.json()
    assert body["ok"] is True, body
    assert body["parameters"]["material"] == "steel_s235"
    assert body["fea_setup_draft"]["material"]["name"] == "Steel S235"
    assert "hole_diameter_mm = 25.0" in body["cad_script_preview"]


def test_preview_missing_required_returns_structured_error(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "missing-required", "p.aieng")
    _make_minimal_package(pkg)

    # Override the default with an obviously missing value (None) — this exercises
    # the "value is None and required" branch.
    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/preview",
        json={"parameters": {"length_mm": None}},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is False
    codes = {e["code"] for e in body["errors"]}
    assert "missing_required" in codes
    assert all(e.get("field") for e in body["errors"])


def test_preview_invalid_numeric_returns_structured_error(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "invalid-numeric", "p.aieng")
    _make_minimal_package(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/preview",
        json={"parameters": {"length_mm": "not-a-number", "width_mm": -3}},
    )
    body = resp.json()
    assert body["ok"] is False
    codes = {e["code"] for e in body["errors"]}
    assert "invalid_value" in codes
    assert "out_of_range" in codes


def test_preview_unknown_parameter_becomes_warning(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "unknown-param", "p.aieng")
    _make_minimal_package(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/preview",
        json={"parameters": {"length_mm": 100.0, "what_is_this": "ignored"}},
    )
    body = resp.json()
    assert body["ok"] is True
    assert any("what_is_this" in w for w in body["warnings"])


def test_preview_plate_inconsistent_geometry_errors_not_500(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "bad-geom", "p.aieng")
    _make_minimal_package(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/plate_with_hole/preview",
        json={"parameters": {"length_mm": 100.0, "width_mm": 50.0, "hole_diameter_mm": 60.0}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert any(e["code"] == "inconsistent_geometry" for e in body["errors"])


def test_preview_invalid_material_choice_returns_structured_error(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "bad-material", "p.aieng")
    _make_minimal_package(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/preview",
        json={"parameters": {"material": "unobtanium"}},
    )
    body = resp.json()
    assert body["ok"] is False
    assert any(e["code"] == "invalid_choice" for e in body["errors"])


# ── save-draft writes only allowed artifacts ─────────────────────────────────


def test_save_draft_writes_only_declared_draft_artifacts(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "save-only", "p.aieng")
    _make_minimal_package(pkg)
    before = _members(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/save-draft",
        json={"parameters": {}},
    )
    body = resp.json()
    assert resp.status_code == 200 and body["ok"] is True, body

    after = _members(pkg)
    new = after - before
    expected = {
        DRAFT_MANIFEST_PATH,
        DRAFT_CAD_SCRIPT_PATH,
        DRAFT_FEA_SETUP_PATH,
        DRAFT_TARGET_SUGGESTIONS_PATH,
    }
    assert expected <= new, f"missing draft artifact(s): {expected - new}"
    leaked = new - expected
    assert not leaked, f"unexpected non-draft writes: {leaked}"


def test_save_draft_does_not_touch_existing_design_targets(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "preserve-targets", "p.aieng")
    existing_targets_doc = {
        "schema_version": "0.1",
        "targets": [{"target_id": "user_target", "metric": "max_displacement",
                     "operator": "<=", "value": 1.0, "unit": "mm"}],
    }
    _make_minimal_package(pkg, existing_targets=existing_targets_doc)
    before_targets = None
    with zipfile.ZipFile(pkg, "r") as zf:
        before_targets = zf.read("task/design_targets.yaml")

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/save-draft",
        json={"parameters": {}},
    )
    assert resp.status_code == 200 and resp.json()["ok"] is True

    with zipfile.ZipFile(pkg, "r") as zf:
        after_targets = zf.read("task/design_targets.yaml")
    assert before_targets == after_targets, "task/design_targets.yaml must not be modified by save-draft"

    new_members = _members(pkg)
    for protected in PROTECTED_PATHS:
        # The protected design_targets.* paths the user explicitly authored
        # must not be re-created or overwritten by template save.
        if protected == "task/design_targets.yaml":
            continue  # this one existed before
        assert protected not in new_members, f"save-draft must not create {protected}"


def test_save_draft_does_not_create_solver_or_mesh_artifacts(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "no-solver-art", "p.aieng")
    _make_minimal_package(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/save-draft",
        json={"parameters": {}},
    )
    assert resp.json()["ok"] is True
    members = _members(pkg)
    for member in members:
        assert not member.startswith("simulation/"), f"unexpected simulation/* write: {member}"
        assert not member.startswith("results/"), f"unexpected results/* write: {member}"
        assert not member.startswith("cad/"), f"unexpected cad/* write: {member}"
        assert not member.startswith("mesh/"), f"unexpected mesh/* write: {member}"


def test_save_draft_does_not_run_subprocess(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "no-subproc", "p.aieng")
    _make_minimal_package(pkg)

    def banned(*args, **kwargs):  # pragma: no cover - asserted not called
        raise AssertionError("subprocess.run must not be called from template save-draft")

    monkeypatch.setattr(subprocess, "run", banned)
    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/save-draft",
        json={"parameters": {}},
    )
    assert resp.status_code == 200 and resp.json()["ok"] is True


def test_save_draft_artifacts_carry_safety_metadata(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "safety-meta", "p.aieng")
    _make_minimal_package(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/save-draft",
        json={"parameters": {}},
    )
    assert resp.json()["ok"] is True

    with zipfile.ZipFile(pkg, "r") as zf:
        manifest = json.loads(zf.read(DRAFT_MANIFEST_PATH).decode("utf-8"))
        cad_script = zf.read(DRAFT_CAD_SCRIPT_PATH).decode("utf-8")
        fea = json.loads(zf.read(DRAFT_FEA_SETUP_PATH).decode("utf-8"))
        sugg = yaml.safe_load(zf.read(DRAFT_TARGET_SUGGESTIONS_PATH).decode("utf-8"))

    assert manifest["claim_advancement"] == "none"
    assert manifest["claim_boundary"]
    assert cad_script.startswith("# Generated draft only. Not executed by AIENG"), cad_script[:120]
    assert fea["claim_advancement"] == "none"
    assert sugg["claim_advancement"] == "none"
    assert isinstance(sugg["suggestions"], list) and len(sugg["suggestions"]) >= 1


def test_save_draft_validation_failure_does_not_write_anything(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "save-fail", "p.aieng")
    _make_minimal_package(pkg)
    before = _members(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/save-draft",
        json={"parameters": {"length_mm": -10}},
    )
    body = resp.json()
    assert body["ok"] is False
    assert any(e["code"] == "out_of_range" for e in body["errors"])
    after = _members(pkg)
    assert after == before, "no artifacts may be written when validation fails"


def test_save_draft_returns_artifact_paths(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "paths-back", "p.aieng")
    _make_minimal_package(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/save-draft",
        json={"parameters": {}},
    )
    body = resp.json()
    assert body["ok"] is True
    artifact_paths = {a["path"] for a in body["artifacts"]}
    assert {DRAFT_MANIFEST_PATH, DRAFT_CAD_SCRIPT_PATH, DRAFT_FEA_SETUP_PATH, DRAFT_TARGET_SUGGESTIONS_PATH} <= artifact_paths
    assert body["draft_paths"] == [
        DRAFT_MANIFEST_PATH,
        DRAFT_CAD_SCRIPT_PATH,
        DRAFT_FEA_SETUP_PATH,
        DRAFT_TARGET_SUGGESTIONS_PATH,
    ]


def test_adopt_target_suggestions_from_preview_writes_design_targets_only(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "adopt-preview-targets", "p.aieng")
    _make_minimal_package(pkg)
    before_members = _members(pkg)

    preview = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/preview",
        json={"parameters": {}},
    ).json()
    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/adopt-targets",
        json={"suggestions": preview["design_target_suggestions"]},
    )
    body = resp.json()
    assert resp.status_code == 200 and body["ok"] is True, body
    assert body["adopted_count"] >= 1
    assert body["artifact_path"] == "task/design_targets.yaml"
    assert body["claim_advancement"] == "none"

    new_members = _members(pkg) - before_members
    assert new_members == {"task/design_targets.yaml"}
    with zipfile.ZipFile(pkg, "r") as zf:
        doc = yaml.safe_load(zf.read("task/design_targets.yaml").decode("utf-8"))
    assert len(doc["targets"]) == body["adopted_count"]
    assert doc["metadata"]["template_handoff"]["claim_advancement"] == "none"


def test_adopt_target_suggestions_from_saved_draft(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "adopt-saved-targets", "p.aieng")
    _make_minimal_package(pkg)
    client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/save-draft",
        json={"parameters": {}},
    ).raise_for_status()

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/adopt-targets",
        json={},
    )
    body = resp.json()
    assert resp.status_code == 200 and body["ok"] is True, body
    assert body["adopted_count"] >= 1
    assert "task/design_targets.yaml" in _members(pkg)


def test_adopt_target_suggestions_skips_duplicates(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "adopt-dupes", "p.aieng")
    existing = {
        "schema_version": "0.1",
        "targets": [
            {
                "target_id": "cantilever_beam_max_stress",
                "label": "Existing stress target",
                "metric": "max_von_mises_stress",
                "operator": "<=",
                "value": 100.0,
                "unit": "MPa",
            }
        ],
    }
    _make_minimal_package(pkg, existing_targets=existing)

    preview = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/preview",
        json={"parameters": {}},
    ).json()
    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/adopt-targets",
        json={"suggestions": preview["design_target_suggestions"]},
    )
    body = resp.json()
    assert body["ok"] is True
    assert "cantilever_beam_max_stress" in body["skipped_duplicate_ids"]
    ids = [t["target_id"] for t in body["targets"]]
    assert ids.count("cantilever_beam_max_stress") == 1


def test_adopt_target_suggestions_no_saved_draft_returns_structured_error(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "adopt-no-suggestions", "p.aieng")
    _make_minimal_package(pkg)
    before = _digest(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/adopt-targets",
        json={},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is False
    assert any(e["code"] == "no_suggestions" for e in body["errors"])
    assert _digest(pkg) == before


def test_adopt_target_suggestions_does_not_run_subprocess(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "adopt-no-subprocess", "p.aieng")
    _make_minimal_package(pkg)
    preview = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/preview",
        json={"parameters": {}},
    ).json()

    def banned(*args, **kwargs):  # pragma: no cover - asserted not called
        raise AssertionError("subprocess.run must not be called from adopt-targets")

    monkeypatch.setattr(subprocess, "run", banned)
    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/adopt-targets",
        json={"suggestions": preview["design_target_suggestions"]},
    )
    assert resp.status_code == 200 and resp.json()["ok"] is True


def test_generate_cad_fixture_requires_approval_and_does_not_mutate(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "cad-fixture-no-approval", "p.aieng")
    _make_minimal_package(pkg)
    before = _digest(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/generate-cad-fixture",
        json={"parameters": {}},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is False
    assert body["status"] == "waiting_for_approval"
    assert body["requires_approval"] is True
    assert body["cad_execution_performed"] is False
    assert _digest(pkg) == before


def test_generate_cad_fixture_writes_geometry_and_stale_marker_only(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "cad-fixture-approved", "p.aieng")
    _make_minimal_package(pkg)
    before_members = _members(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/generate-cad-fixture",
        json={"parameters": {}, "approved": True},
    )
    body = resp.json()
    assert resp.status_code == 200 and body["ok"] is True, body
    assert body["status"] == "completed"
    assert body["artifact_path"] == GENERATED_CAD_FIXTURE_PATH
    assert body["revalidation_status_path"] == REVALIDATION_STATUS_PATH
    assert body["cad_execution_performed"] is False
    assert body["external_tool_execution_performed"] is False
    assert body["real_cad_file"] is False
    assert body["claim_advancement"] == "none"

    new_members = _members(pkg) - before_members
    assert new_members <= {GENERATED_CAD_FIXTURE_PATH, REVALIDATION_STATUS_PATH, "state/"}
    assert {GENERATED_CAD_FIXTURE_PATH, REVALIDATION_STATUS_PATH} <= new_members
    with zipfile.ZipFile(pkg, "r") as zf:
        fixture = json.loads(zf.read(GENERATED_CAD_FIXTURE_PATH).decode("utf-8"))
        revalidation = json.loads(zf.read(REVALIDATION_STATUS_PATH).decode("utf-8"))
    assert fixture["artifact_type"] == "template_cad_fixture"
    assert fixture["template_id"] == "cantilever_beam"
    assert fixture["geometry"]["primitive"] == "box"
    assert fixture["cad_execution_performed"] is False
    assert fixture["real_cad_file"] is False
    assert revalidation["requires_revalidation"] is True
    assert GENERATED_CAD_FIXTURE_PATH not in revalidation["affected_artifacts"]


def test_generate_cad_fixture_from_saved_draft(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "cad-fixture-saved-draft", "p.aieng")
    _make_minimal_package(pkg)
    client.post(
        f"/api/projects/{project_id}/engineering-templates/plate_with_hole/save-draft",
        json={"parameters": {"hole_diameter_mm": 30.0}},
    ).raise_for_status()

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/plate_with_hole/generate-cad-fixture",
        json={"approved": True},
    )
    body = resp.json()
    assert resp.status_code == 200 and body["ok"] is True, body
    fixture = body["fixture"]
    assert fixture["source"] == "saved_draft"
    assert fixture["geometry"]["primitive"] == "box_minus_cylinder"
    assert fixture["geometry"]["features"][0]["diameter_mm"] == 30.0


def test_generate_cad_fixture_invalid_parameters_do_not_write(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "cad-fixture-invalid", "p.aieng")
    _make_minimal_package(pkg)
    before = _digest(pkg)

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/plate_with_hole/generate-cad-fixture",
        json={"parameters": {"hole_diameter_mm": 9999.0}, "approved": True},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is False
    assert any(e["code"] == "out_of_range" or e["code"] == "inconsistent_geometry" for e in body["errors"])
    assert _digest(pkg) == before


def test_generate_cad_fixture_does_not_run_subprocess(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "cad-fixture-no-subprocess", "p.aieng")
    _make_minimal_package(pkg)

    def banned(*args, **kwargs):  # pragma: no cover - asserted not called
        raise AssertionError("subprocess.run must not be called from generate-cad-fixture")

    monkeypatch.setattr(subprocess, "run", banned)
    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/generate-cad-fixture",
        json={"parameters": {}, "approved": True},
    )
    assert resp.status_code == 200 and resp.json()["ok"] is True


def test_save_draft_when_no_package_returns_error_not_500(tmp_path: Path) -> None:
    from app.main import default_project, save_project

    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("no-pkg-draft"))
    project_id = project["id"]

    resp = client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/save-draft",
        json={"parameters": {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert any(e["code"] == "package_not_found" for e in body["errors"])


# ── template id coverage ─────────────────────────────────────────────────────


def test_all_declared_templates_preview_with_defaults(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "all-tpls", "p.aieng")
    _make_minimal_package(pkg)

    for tid in TEMPLATE_IDS:
        resp = client.post(
            f"/api/projects/{project_id}/engineering-templates/{tid}/preview",
            json={"parameters": {}},
        )
        body = resp.json()
        assert resp.status_code == 200 and body["ok"], (tid, body)
        assert "Generated draft only" in body["cad_script_preview"], tid
        assert body["fea_setup_draft"]["claim_advancement"] == "none", tid


# ── integrations: Project Health + Review Support Packet ─────────────────────


def test_project_health_includes_engineering_setup_draft_check_when_present(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "health-with-draft", "p.aieng")
    _make_minimal_package(pkg)
    client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/save-draft",
        json={"parameters": {}},
    ).raise_for_status()

    resp = client.get(f"/api/projects/{project_id}/health-check")
    assert resp.status_code == 200
    body = resp.json()
    draft_check = next(
        (c for c in body["checks"] if c.get("id") == "engineering_setup_draft"),
        None,
    )
    assert draft_check is not None, "engineering_setup_draft check missing from project health"
    # Per spec: informational/passed, not hard pass/fail. Status must be "passed".
    assert draft_check["status"] == "passed"
    assert "draft" in draft_check["summary"].lower()
    assert "certify" not in draft_check["summary"].lower() or "not" in draft_check["summary"].lower()


def test_project_health_omits_engineering_setup_draft_check_when_absent(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "health-without-draft", "p.aieng")
    _make_minimal_package(pkg)

    body = client.get(f"/api/projects/{project_id}/health-check").json()
    assert all(c.get("id") != "engineering_setup_draft" for c in body["checks"]), (
        "absent draft must not surface a warning — template authoring is optional"
    )


def test_review_support_packet_includes_engineering_setup_draft_section_when_present(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "packet-with-draft", "p.aieng")
    _make_minimal_package(pkg)
    client.post(
        f"/api/projects/{project_id}/engineering-templates/cantilever_beam/save-draft",
        json={"parameters": {}},
    ).raise_for_status()

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    section = next((s for s in body["sections"] if s["id"] == "engineering_setup_draft"), None)
    assert section is not None, "review packet must surface a section for the saved template draft"
    assert section["status"] == "included"
    md = body["preview_markdown"]
    assert "Engineering Setup Draft" in md
    assert "cantilever_beam" in md
    assert "informational only" in md.lower()


def test_review_support_packet_marks_engineering_setup_draft_missing_when_absent(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "packet-no-draft", "p.aieng")
    _make_minimal_package(pkg)

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    section = next((s for s in body["sections"] if s["id"] == "engineering_setup_draft"), None)
    assert section is not None
    assert section["status"] == "missing"
